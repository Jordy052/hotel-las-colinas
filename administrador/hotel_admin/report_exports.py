"""Filtered hotel exports; monetary totals are signed cashflow, not fee duplicates."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from xml.sax.saxutils import escape
from sqlalchemy import select, cast, BigInteger
from sqlalchemy.orm import joinedload
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from hotel_admin import billing
from hotel_admin.models import Payment, Reservation, Room
from hotel_admin.exporters import _style_sheet

def period_dates(period, today=None):
    today = today or billing.hotel_now().date()
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    if period == "Hoy": return today, today
    if period == "Ayer": return today-timedelta(days=1), today-timedelta(days=1)
    if period == "Esta semana": return week, week+timedelta(days=6)
    if period == "Semana pasada": return week-timedelta(days=7), week-timedelta(days=1)
    if period == "Este mes": return month, billing.add_months(month,1)-timedelta(days=1)
    if period == "Mes pasado": return billing.add_months(month,-1), month-timedelta(days=1)
    raise ValueError("Selecciona un período válido.")

def collect(session_factory, options):
    kind = options["kind"]
    start, end = options.get("start"), options.get("end")
    status = options.get("status", "Todos")
    search = options.get("search", "").strip().casefold()
    if kind not in {"Habitaciones", "Reservas", "Ingresos"}:raise ValueError("Tipo de reporte no válido.")
    if kind != "Habitaciones" and (start is None or end is None or start > end):raise ValueError("Revisa las fechas del reporte.")
    summary = f"Estado: {status}" if kind == "Habitaciones" else f"Del {start:%d/%m/%Y} al {end:%d/%m/%Y} · Estado: {status}"
    if kind == "Reservas":summary += " · Fecha: " + options.get("basis", "Entrada")
    if search:summary += " · Búsqueda: " + search
    if options.get("method", "Todos") != "Todos":summary += " · Método: " + options["method"]
    report = {"kind": kind, "filters": summary, "headers": [], "rows": [], "net": None, "fees": None}
    with session_factory() as session:
        if kind == "Habitaciones":
            query = select(Room).where(Room.active.is_(True)).order_by(cast(Room.number,BigInteger),Room.number)
            if status != "Todos": query = query.where(Room.status == status)
            rooms=session.scalars(query).all()
            report["headers"]=["Habitación", "Tipo", "Capacidad", "Camas", "Precio por noche (C$)", "Estado"]
            report["rows"]=[[r.number,r.category,r.capacity,f"{r.bed_count} · {r.bed_type}",float(r.nightly_rate),r.status] for r in rooms if not search or search in (r.number+" "+r.category).casefold()]
        elif kind == "Reservas":
            basis=options.get("basis","Entrada")
            if basis not in {"Entrada","Fecha de reserva"}:raise ValueError("Selecciona la fecha que filtra las reservas.")
            field=Reservation.check_in if basis=="Entrada" else Reservation.created_at
            lower=start if basis=="Entrada" else datetime.combine(start,time.min)
            upper=end+timedelta(days=1) if basis=="Entrada" else datetime.combine(end+timedelta(days=1),time.min)
            query=select(Reservation).options(joinedload(Reservation.guest),joinedload(Reservation.room)).where(field>=lower,field<upper).order_by(field,Reservation.code)
            if status!="Todos":query=query.where(Reservation.status==status)
            rows=session.scalars(query).all()
            report["headers"]=["Reserva", "Huésped", "Habitación", "Entrada", "Salida", "Total (C$)", "Estado", "Pago"]
            report["rows"]=[[r.code,r.guest.username,r.room.number,f"{r.check_in:%d/%m/%Y}",f"{r.check_out:%d/%m/%Y}",float(r.total_amount),r.status,r.payment_status] for r in rows if not search or search in (r.code+" "+r.guest.username).casefold()]
        else:
            lower=datetime.combine(start,time.min);upper=datetime.combine(end+timedelta(days=1),time.min)
            query=select(Payment).options(joinedload(Payment.reservation).joinedload(Reservation.guest)).where(Payment.paid_at>=lower,Payment.paid_at<upper,Payment.status.in_([*billing.CASHFLOW_STATES,billing.FEE_STATE])).order_by(Payment.paid_at,Payment.id)
            if status!="Todos":query=query.where(Payment.status==status)
            method=options.get("method","Todos")
            if method == billing.CARD_WEB:
                query=query.where(Payment.method == "Tarjeta", Payment.reservation.has(Reservation.source == "Web"))
            elif method == billing.CARD_POS:
                query=query.where(Payment.method == "Tarjeta", Payment.reservation.has(Reservation.source.in_(["Administración", "Presencial"])))
            elif method != "Todos":
                query=query.where(Payment.method == method)
            report["headers"]=["Fecha", "Referencia", "Reserva", "Huésped", "Método", "Estado", "Movimiento (C$)", "Cargo retenido (C$)"]
            net=fees=Decimal("0")
            for payment in session.scalars(query).all():
                r=payment.reservation
                if search and search not in ((payment.reference or "")+" "+r.code+" "+r.guest.username).casefold():continue
                is_fee=payment.status==billing.FEE_STATE
                movement=Decimal("0") if is_fee else billing.money(payment.amount)
                fee=billing.money(payment.amount) if is_fee else Decimal("0")
                net+=movement;fees+=fee
                report["rows"].append([f"{payment.paid_at:%d/%m/%Y %H:%M}",payment.reference or "—",r.code,r.guest.username,billing.payment_channel(payment.method,r.source),payment.status,float(movement),float(fee)])
            report.update(net=float(net),fees=float(fees))
    return report

def export_file(report, destination, format):
    if format == "Excel":
        workbook=Workbook();sheet=workbook.active;sheet.title=report["kind"]
        sheet.append(report["headers"])
        for row in report["rows"]:
            sheet.append(row)
            # Prevent user-entered names/references becoming spreadsheet formulas.
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value,str):cell.data_type="s"
        _style_sheet(sheet)
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,float):cell.number_format='#,##0.00;[Red]-#,##0.00'
        meta=workbook.create_sheet("Filtros y totales")
        for row in [["Hotel","Hotel Las Colinas"],["Ubicación","Puerto Cabezas, Nicaragua"],["Reporte",report["kind"]],["Filtros",report["filters"]],["Generado",f"{billing.hotel_now():%d/%m/%Y %H:%M}"],["Registros",len(report["rows"])]]:
            meta.append(row)
            for cell in meta[meta.max_row]:
                if isinstance(cell.value,str):cell.data_type="s"
        if report["net"] is not None:
            meta.append(["Ingresos netos (C$)",report["net"]]);meta.append(["Cargos retenidos (C$)",report["fees"]]);meta.append(["Nota","Los cargos retenidos forman parte del pago original; no se suman otra vez a los ingresos."])
        _style_sheet(meta);meta.column_dimensions['B'].width=90
        workbook.save(destination)
    elif format == "PDF":
        styles=getSampleStyleSheet();small=styles["BodyText"].clone('ReportCell');small.fontSize=7;small.leading=10
        doc=SimpleDocTemplate(destination,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=24,bottomMargin=24)
        tabledata=[[Paragraph(escape(str(c)),small) for c in report["headers"]]]
        for row in report["rows"]:
            tabledata.append([Paragraph(escape(f"{c:,.2f}" if isinstance(c,float) else str(c)),small) for c in row])
        if len(tabledata)==1:tabledata.append([Paragraph("Sin registros para los filtros seleccionados.",small)]+['']*(len(report["headers"])-1))
        table=Table(tabledata,repeatRows=1,colWidths=[doc.width/len(report["headers"])]*len(report["headers"]))
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4f0f0')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f7f7')]),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#c6dcdd')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story=[Paragraph('Hotel Las Colinas · '+report['kind'],styles['Title']),Paragraph(escape(report['filters']),styles['Normal']),Paragraph(f"Puerto Cabezas, Nicaragua · {billing.hotel_now():%d/%m/%Y %H:%M} · {len(report['rows'])} registros",styles['Normal']),Spacer(1,12),table]
        if report['net'] is not None:story += [Spacer(1,12),Paragraph(f"Ingresos netos: C$ {report['net']:,.2f} · Cargos retenidos: C$ {report['fees']:,.2f} (ya incluidos en el pago original)",styles['Normal'])]
        doc.build(story)
    else:raise ValueError("Formato de exportación no válido.")
    return destination
