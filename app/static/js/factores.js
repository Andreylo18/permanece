// Vista previa en vivo del puntaje mientras se diligencian los factores.
// El cálculo real y definitivo siempre lo hace el servidor al guardar.
(function () {
  const form = document.getElementById("form-factores");
  if (!form) return;
  const url = window.PERMANECE_PREVIEW_URL;
  const $p = document.getElementById("pv-puntaje");
  const $n = document.getElementById("pv-nivel");
  const $f = document.getElementById("pv-factores");
  const ETIQ = {
    bajo: ["success", "Riesgo bajo"], medio: ["warning", "Riesgo medio"], alto: ["danger", "Riesgo alto"],
  };
  let t;

  async function actualizar() {
    const datos = new FormData(form);
    try {
      const r = await fetch(url, {
        method: "POST", body: datos, headers: { "X-CSRFToken": datos.get("csrf_token") || "" },
      });
      if (!r.ok) return;
      const j = await r.json();
      $p.textContent = j.puntaje + "/100";
      const [c, txt] = ETIQ[j.nivel];
      $n.innerHTML = "";
      const b = document.createElement("span");
      b.className = "badge rounded-pill text-bg-" + c;
      b.textContent = txt;
      $n.appendChild(b);
      if (j.incompleto) {
        const i = document.createElement("span");
        i.className = "badge rounded-pill bg-light text-dark border ms-1";
        i.textContent = "Datos incompletos";
        $n.appendChild(i);
      }
      $f.innerHTML = "";
      (j.factores.length ? j.factores : ["Ningún factor suma puntos"]).forEach(txt => {
        const li = document.createElement("li");
        li.textContent = txt;
        $f.appendChild(li);
      });
    } catch (e) { /* la vista previa es opcional */ }
  }

  form.addEventListener("input", () => { clearTimeout(t); t = setTimeout(actualizar, 250); });
  form.addEventListener("change", actualizar);
  actualizar();
})();
