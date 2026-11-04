"use strict";
window.HotelPhone = (() => {
  const countries = {"AR": ["Argentina", "54", [10, 11], "11 2345-6789 / 9 11 2345-6789"], "BZ": ["Belice", "501", [7], "222-1234"], "BO": ["Bolivia", "591", [8], "7123-4567"], "BR": ["Brasil", "55", [10, 11], "11 2345-6789 / 11 91234-5678"], "CL": ["Chile", "56", [9], "9 6123-4567"], "CO": ["Colombia", "57", [10], "300 123-4567"], "CR": ["Costa Rica", "506", [8], "8123-4567"], "CU": ["Cuba", "53", [8], "5123-4567"], "EC": ["Ecuador", "593", [8, 9], "2 234-5678 / 99 123-4567"], "SV": ["El Salvador", "503", [8], "7123-4567"], "GT": ["Guatemala", "502", [8], "5123-4567"], "GY": ["Guyana", "592", [7], "612-3456"], "HT": ["Haití", "509", [8], "3412-3456"], "HN": ["Honduras", "504", [8], "9123-4567"], "MX": ["México", "52", [10], "55 1234-5678"], "NI": ["Nicaragua", "505", [8], "8888-1234"], "PA": ["Panamá", "507", [7, 8], "234-5678 / 6123-4567"], "PY": ["Paraguay", "595", [9], "981 123-456"], "PE": ["Perú", "51", [8, 9], "1 234-5678 / 912 345-678"], "PR": ["Puerto Rico", "1", [10], "787 234-5678 / 939 234-5678"], "DO": ["República Dominicana", "1", [10], "809 234-5678 / 829 / 849"], "SR": ["Surinam", "597", [6, 7], "212-345 / 812-3456"], "UY": ["Uruguay", "598", [8], "9123-4567"], "VE": ["Venezuela", "58", [10], "412 123-4567"]};
  function attach(container) {
    const country = container.querySelector("select");
    const phone = container.querySelector('input[type="tel"]');
    const hint = container.querySelector(".phone-hint");
    const error = container.querySelector(".phone-error");
    for (const [key,[name,code]] of Object.entries(countries)) {
      const option = document.createElement("option");option.value=key;option.textContent=name+" (+"+code+")";country.append(option);
    }
    country.value="NI";
    function clear() {error.textContent="";phone.removeAttribute("aria-invalid");country.removeAttribute("aria-invalid");}
    function refresh() {
      const [name,code,lengths,example]=countries[country.value];
      phone.placeholder=example.split(" / ")[0];
      hint.textContent="Ejemplo: +"+code+" "+example+". Incluye el código de área cuando corresponda.";
      clear();
    }
    country.addEventListener("change",refresh);
    // Let a scrolling gesture move the page rather than change the selected country.
    country.addEventListener("wheel",event=>{country.blur();}, {passive:true});
    phone.addEventListener("input",clear);
    refresh();
    function value() {
      const region=country.value, raw=phone.value.trim();
      const profile=countries[region];
      let message="",digits=raw.replace(/[^0-9]/g,"");
      if(!profile) message="Selecciona el país del teléfono.";
      else if(!raw) message="El teléfono no puede quedar vacío.";
      else if(raw.length>30 || !/^\+?[0-9 ()-]+$/.test(raw)) message="Usa solo números, espacios, paréntesis y guiones.";
      else {
        const [name,code,lengths,example]=profile;
        if(raw.startsWith("+")) {
          if(!digits.startsWith(code)) message="El prefijo no coincide con el país seleccionado.";
          else digits=digits.slice(code.length);
        }
        if(!message && (!lengths.includes(digits.length)||digits[0]==="0"||(digits[0]==="1"&&!['AR','BR','PE'].includes(region)))) message="Revisa el teléfono de "+name+". Ejemplo: "+example+".";
        if(!message && ['PR','DO'].includes(region) && (!({PR:['787','939'],DO:['809','829','849']}[region]).some(area=>digits.startsWith(area))||'01'.includes(digits[3]))) message="Revisa el código de área y el número del teléfono.";
        if(!message && region==='AR'&&digits.length===11&&!digits.startsWith('9')) message="El móvil de Argentina debe comenzar con 9 después de +54.";
        if(!message && region==='BR'&&digits.length===11&&digits[2]!=='9') message="El móvil de Brasil lleva código de área y un número de 9 dígitos que comienza con 9.";
      }
      if(message){error.textContent=message;phone.setAttribute('aria-invalid','true');phone.focus();return null;}
      clear();return {phone:raw,phoneCountry:region};
    }
    function fill(saved) {
      if(!saved){phone.value="";return;}
      const digits=saved.replace(/[^0-9]/g,"");
      for(const key of Object.keys(countries).sort((a,b)=>countries[b][1].length-countries[a][1].length)) {
        const code=countries[key][1];
        if(!digits.startsWith(code))continue;
        const national=digits.slice(code.length);
        if(code==='1'&&!({PR:['787','939'],DO:['809','829','849']}[key]||[]).some(area=>national.startsWith(area)))continue;
        country.value=key;refresh();phone.value=national;return;
      }
      phone.value=saved;
    }
    return {value,fill};
  }
  return {attach};
})();
