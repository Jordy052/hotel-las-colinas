from datetime import datetime
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TEAL = "087986"
INK = "173E46"


def export_rooms_xlsx(rows: Iterable[dict], destination: str) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Habitaciones"
    sheet.append(["N.º", "Tipo", "Capacidad", "Camas", "Precio por noche", "Estado", "Fotos"])
    for row in rows:
        sheet.append([
            row["number"], row["category"], row["capacity"],
            f"{row['bed_count']} · {row['bed_type']}", row["rate"],
            row["status"], len(row.get("photos", [])),
        ])
    _style_sheet(sheet)
    workbook.save(destination)
    return destination


def export_reservations_xlsx(rows: Iterable[dict], destination: str) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reservas"
    sheet.append(["Código", "Huésped", "Habitación", "Fechas", "Total", "Estado", "Pago"])
    for row in rows:
        sheet.append([row["code"], row["guest"], row["room"], row["dates"], row["total"], row["status"], row["payment"]])
    _style_sheet(sheet)
    workbook.save(destination)
    return destination


def _style_sheet(sheet) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor=TEAL)
        cell.font = Font(name="Aptos", bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 26
    for column in sheet.columns:
        letter = column[0].column_letter
        sheet.column_dimensions[letter].width = min(max(max(len(str(c.value or "")) for c in column) + 3, 13), 34)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = Font(name="Aptos", color=INK)
            cell.alignment = Alignment(vertical="center")


def export_reservations_pdf(rows: Iterable[dict], destination: str) -> str:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="HotelTitle", parent=styles["Title"], textColor=colors.HexColor(f"#{INK}"), fontName="Helvetica-Bold", fontSize=18, alignment=0, spaceAfter=5))
    styles.add(ParagraphStyle(name="HotelMeta", parent=styles["Normal"], textColor=colors.HexColor("#71868B"), fontSize=9, spaceAfter=12))
    data = [["Código", "Huésped", "Habitación", "Fechas", "Total", "Estado"]]
    for row in rows:
        data.append([row["code"], row["guest"], row["room"], row["dates"], f"C$ {row['total']:,.2f}", row["status"]])
    if len(data) == 1:
        data.append(["Sin reservas", "", "", "", "", ""])
    table = Table(data, repeatRows=1, colWidths=[0.95*inch, 1.35*inch, 1.2*inch, 1.55*inch, 0.9*inch, 0.95*inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{TEAL}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DCE8E8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7F7")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    doc = SimpleDocTemplate(destination, pagesize=landscape(letter), rightMargin=0.55*inch, leftMargin=0.55*inch, topMargin=0.55*inch, bottomMargin=0.55*inch)
    doc.build([
        Paragraph("Hotel Las Colinas · Reservas", styles["HotelTitle"]),
        Paragraph(f"Reporte generado el {datetime.now():%d/%m/%Y %H:%M} · Puerto Cabezas, Nicaragua", styles["HotelMeta"]),
        Spacer(1, 7), table,
    ])
    return destination
