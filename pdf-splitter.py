# pdf_splitter_generic.py
import os
import re
import unicodedata
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pypdf import PdfReader, PdfWriter
from difflib import SequenceMatcher
from collections import defaultdict
from datetime import datetime

# ---------- CONFIG ----------
FUZZY_THRESHOLD = 0.65  # Limite de similaridade (0..1)

# Lista de usuários genérica (qualquer pessoa pode editar/adicionar)
usuarios = [
    ("01", "Usuario Um"),
    ("02", "Usuario Dois"),
    ("03", "Usuario Tres"),
    ("04", "Usuario Quatro"),
    ("05", "Usuario Cinco"),
]

# ---------- Funções auxiliares ----------
def remove_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFD', text)
    return "".join([c for c in nfkd if not unicodedata.combining(c)])

def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = remove_accents(text)
    t = t.lower()
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def normalize_code(code: str) -> str:
    if not code:
        return ""
    return re.sub(r'\s+', '', code).lower()

def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ---------- Interface gráfica ----------
root = tk.Tk()
root.title("Separador de PDFs por Usuário")
root.geometry("900x650")
root.configure(bg="#E8F0FE")

# Título
tk.Label(root, text="Separador de PDFs por Usuário", font=("Arial", 18, "bold"), bg="#E8F0FE", fg="#0B3D91").pack(pady=15)

# Caixa de log
log_box = scrolledtext.ScrolledText(root, width=110, height=22, font=("Arial", 11))
log_box.pack(padx=10, pady=8)

# Área de botões
frame = tk.Frame(root, bg="#E8F0FE")
frame.pack(pady=10)

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    log_box.insert(tk.END, f"[{ts}] {msg}\n")
    log_box.see(tk.END)

def processar():
    log_box.delete("1.0", tk.END)
    arquivo_pdf = filedialog.askopenfilename(title="Selecione o PDF", filetypes=[("PDF files", "*.pdf")])
    if not arquivo_pdf:
        return
    output_dir = filedialog.askdirectory(title="Pasta para salvar PDFs separados")
    if not output_dir:
        return

    # Criar pasta de saída
    os.makedirs(output_dir, exist_ok=True)

    try:
        reader = PdfReader(arquivo_pdf)
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível abrir o PDF:\n{e}")
        return

    # Normalização e indexação de usuários
    usuarios_norm = []
    by_code = defaultdict(list)
    for idx, (cod, nome) in enumerate(usuarios):
        cod_norm = normalize_code(cod)
        nome_norm = normalize_text(nome)
        usuarios_norm.append({
            "idx": idx,
            "code": cod,
            "cod_norm": cod_norm,
            "name": nome,
            "name_norm": nome_norm,
            "key": f"{cod}_{idx}_{re.sub(r'[^A-Za-z0-9]', '_', nome)}"
        })
        by_code[cod_norm].append(idx)

    writers = {u["key"]: PdfWriter() for u in usuarios_norm}
    counts = defaultdict(int)
    pagina_nao_associada = []

    total_pages = len(reader.pages)
    log(f"Iniciando processamento: {total_pages} páginas encontradas no PDF.")

    for i, page in enumerate(reader.pages, start=1):
        try:
            texto = page.extract_text() or ""
        except Exception:
            texto = ""
        texto_norm = normalize_text(texto)
        header_sample = texto_norm[:400]
        assigned = False

        # 1) Casamento pelo nome completo
        for u in usuarios_norm:
            if u["name_norm"] and u["name_norm"] in header_sample:
                writers[u["key"]].add_page(page)
                counts[u["key"]] += 1
                assigned = True
                log(f"Página {i}: atribuído por NOME → {u['code']} / {u['name']}")
                break
        if assigned:
            continue

        # 2) Casamento por código
        matched_u = None
        best_ratio = 0.0
        for cod_norm, idxs in by_code.items():
            if re.search(r'\b' + re.escape(cod_norm) + r'\b', header_sample):
                for idx in idxs:
                    u = usuarios_norm[idx]
                    r = similar(u["name_norm"], header_sample[:200])
                    if r > best_ratio:
                        best_ratio = r
                        matched_u = u
                break
        if matched_u:
            writers[matched_u["key"]].add_page(page)
            counts[matched_u["key"]] += 1
            assigned = True
            log(f"Página {i}: atribuído por CÓDIGO → {matched_u['code']} / {matched_u['name']} (ratio {best_ratio:.2f})")
        if assigned:
            continue

        # 3) Fuzzy matching
        best_ratio = 0.0
        best_u = None
        for u in usuarios_norm:
            r = similar(u["name_norm"], header_sample[:200])
            if r > best_ratio:
                best_ratio = r
                best_u = u
        if best_ratio >= FUZZY_THRESHOLD and best_u:
            writers[best_u["key"]].add_page(page)
            counts[best_u["key"]] += 1
            log(f"Página {i}: atribuído por FUZZY ({best_ratio:.2f}) → {best_u['code']} / {best_u['name']}")
            continue

        # 4) Não associado
        pagina_nao_associada.append(i)
        log(f"Atenção: página {i} não associada a nenhum usuário.")

    # Salvar PDFs
    arquivos_gerados = 0
    for u in usuarios_norm:
        key = u["key"]
        writer = writers[key]
        if len(writer.pages) > 0:
            safe = re.sub(r'[^A-Za-z0-9_]', '_', f"{u['code']}_{u['name']}")
            out_path = os.path.join(output_dir, f"{safe}.pdf")
            try:
                with open(out_path, "wb") as f:
                    writer.write(f)
                arquivos_gerados += 1
            except Exception as e:
                log(f"Erro ao salvar {out_path}: {e}")

    # Salvar log
    log_file = os.path.join(output_dir, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(log_file, "w", encoding="utf-8") as lf:
        lf.write(f"Arquivo origem: {arquivo_pdf}\n")
        lf.write(f"Páginas totais: {len(reader.pages)}\n")
        lf.write("\nPáginas não associadas:\n")
        for p in pagina_nao_associada:
            lf.write(f"{p}\n")
        lf.write("\nResumo por usuário (arquivo gerado e número páginas):\n")
        for u in usuarios_norm:
            key = u["key"]
            lf.write(f"{u['code']} - {u['name']} -> páginas: {len(writers[key].pages)}\n")

    log(f"Processo concluído: {arquivos_gerados} PDFs gerados.")
    log(f"Log salvo em: {log_file}")
    messagebox.showinfo("Concluído", f"{arquivos_gerados} arquivos gerados.\nVeja o log para detalhes.")

# Botões
tk.Button(frame, text="Selecionar PDF e Processar", font=("Arial", 12), bg="#0B3D91", fg="white", relief="flat",
          padx=15, pady=5, command=processar).grid(row=0, column=0, padx=10)
tk.Button(frame, text="Sair", font=("Arial", 12), bg="#B22222", fg="white", relief="flat",
          padx=15, pady=5, command=root.quit).grid(row=0, column=1, padx=10)

root.mainloop()
