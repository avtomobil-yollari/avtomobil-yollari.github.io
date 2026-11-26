"""Normativ hujjatlarni lex.uz (va iloji bo'lsa mc.uz) dan olib, saytga joylaydi.
GitHub Actions'da ishlaydi. Natija: docs/<id>.html (+ docs/img/), docs/<id>.pdf, data/docs.json yangilanadi,
docs/report.json — nima olindi/olinmadi."""
import json, os, re, ssl, socket, sys, time, hashlib, base64
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "docs"); IMGD = os.path.join(D, "img")
os.makedirs(IMGD, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (avtomobil-yollari.github.io normativ arxiv)"}
report = {"probe": {}, "lex": {}, "mc": {}}

def probe():
    for host in ["lex.uz", "mc.uz", "www.mc.uz"]:
        r = {}
        try:
            ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, 443), timeout=15) as s:
                with ctx.wrap_socket(s, server_hostname=host) as t:
                    der = t.getpeercert(binary_form=True)
            from cryptography import x509
            cert = x509.load_der_x509_certificate(der)
            try:
                r["san"] = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            except Exception: r["san"] = []
            r["subject"] = cert.subject.rfc4514_string(); r["notAfter"] = str(cert.not_valid_after)
        except Exception as e: r["certerr"] = repr(e)[:200]
        try:
            q = requests.get(f"https://{host}/", headers=UA, timeout=20); r["https"] = q.status_code
        except Exception as e: r["https"] = repr(e)[:160]
        report["probe"][host] = r

CSS_HEAD = '<!DOCTYPE html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{t}</title><link rel="stylesheet" href="doc.css"></head><body><header class="dh"><a href="../#/kutubxona/{id}">← Avtomobil Yoʻllari UZ · Normativlar</a><button onclick="print()">PDF / chop etish</button></header><main class="raw"><h1 class="dt">{t}</h1>'
CSS_FOOT = '</main><footer class="df">Rasmiy elektron matn manbasi: lex.uz · Arxiv: avtomobil-yollari.github.io</footer></body></html>'

def lex(docid, url):
    q = requests.get(url, headers=UA, timeout=60); q.raise_for_status()
    soup = BeautifulSoup(q.text, "html.parser")
    c = soup.select_one("#divCont")
    if not c or len(c.get_text(strip=True)) < 500: raise RuntimeError("divCont yo'q/bo'sh")
    for e in c.select("script,style,button,input"): e.decompose()
    for i in c.find_all("img"):
        src = i.get("src", "")
        if "/img/" in src or src.endswith(".svg"): i.decompose(); continue
        full = urljoin(url, src)
        try:
            b = b""
            for att in range(4):
                b = requests.get(full, headers=UA, timeout=60).content
                if b[:4] in (b"\x89PNG", b"GIF8") or b[:2] == b"\xff\xd8" or b[:2] == b"BM": break
                b = b""; time.sleep(5 * (att + 1))
            if not b: raise RuntimeError("rasm emas")
            ext = os.path.splitext(src)[1][:5] or ".png"
            name = hashlib.md5(b).hexdigest()[:12] + ext
            open(os.path.join(IMGD, name), "wb").write(b)
            i.attrs = {"src": "img/" + name, "loading": "lazy"}
        except Exception: i.decompose()
    for e in c.find_all(True):
        keep = {k: v for k, v in e.attrs.items() if k in ("src", "colspan", "rowspan", "id", "loading")}
        if e.name == "a":
            h = e.get("href", "")
            if h.startswith("#"): keep["href"] = h
            else: e.unwrap(); continue
        e.attrs = keep
    for e in c.find_all(["span", "font"]): e.unwrap()
    html = re.sub(r"\n{3,}", "\n\n", str(c))
    html = re.sub(r"<div>(<div>)?Ҳужжатга таклиф юбориш[^<]*</div>(</div>)?", "", html)
    title = (soup.title.string or docid).strip() if soup.title else docid
    open(os.path.join(D, docid + ".html"), "w", encoding="utf-8").write(CSS_HEAD.format(t=title, id=docid) + html + CSS_FOOT)
    return len(html)

def mc(docid, url):
    q = requests.get(url, headers=UA, timeout=90)  # sertifikat tekshiruvi YOQILGAN
    q.raise_for_status()
    if not q.content.startswith(b"%PDF"): raise RuntimeError("PDF emas")
    open(os.path.join(D, docid + ".pdf"), "wb").write(q.content); return len(q.content)

def main():
    probe()
    docs = json.load(open(os.path.join(ROOT, "data/docs.json"), encoding="utf-8"))
    mc_hosts = [h for h in ("mc.uz", "www.mc.uz") if isinstance(report["probe"].get(h, {}).get("https"), int)]
    for d in docs:
        for l in d["links"]:
            u = l[1]
            try:
                if "lex.uz/docs" in u and not os.path.exists(os.path.join(D, d["id"] + ".html")):
                    report["lex"][d["id"]] = lex(d["id"], u); time.sleep(2)
                elif "mc.uz/uploads" in u and mc_hosts and not os.path.exists(os.path.join(D, d["id"] + ".pdf")):
                    host = mc_hosts[0]; u2 = re.sub(r"https?://(www\.)?mc\.uz", "https://" + host, u)
                    report["mc"][d["id"]] = mc(d["id"], u2); time.sleep(1)
            except Exception as e:
                report["lex" if "lex.uz" in u else "mc"][d["id"]] = "ERR " + repr(e)[:150]
    # docs.json: saytdagi nusxa — birinchi tugma
    for d in docs:
        own = []
        if os.path.exists(os.path.join(D, d["id"] + ".pdf")): own.append(["PDF yuklab olish", "docs/" + d["id"] + ".pdf", 1])
        if os.path.exists(os.path.join(D, d["id"] + ".html")): own.append(["Toʻliq matn (saytda)", "docs/" + d["id"] + ".html", 1])
        rest = [l for l in d["links"] if not l[1].startswith("docs/")]
        if own: rest = [[l[0], l[1], 0] for l in rest]
        d["links"] = own + rest
    json.dump(docs, open(os.path.join(ROOT, "data/docs.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(report, open(os.path.join(D, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1)[:6000])

if __name__ == "__main__": main()
