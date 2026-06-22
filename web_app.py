import asyncio
import base64
import urllib.parse
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
import markdown
from fastmcp import Client

MCP_SERVER_URL = "http://127.0.0.1:8001/mcp"

app = FastAPI(title="Recherche Sémantique")


async def fetch_tags_from_mcp():
    print("[Python] Récupération des tags...", flush=True)
    try:
        async with Client(MCP_SERVER_URL) as client:
            res = await asyncio.wait_for(client.call_tool("get_available_tags", {}), timeout=10.0)
            data = res.structured_content
            if isinstance(data, dict):
                if "tags" in data: return data["tags"]
                if "result" in data and isinstance(data["result"], dict): return data["result"].get("tags", [])
                if "result" in data and isinstance(data["result"], list): return data["result"]
            if isinstance(data, list): return data
            return []
    except Exception as e:
        print(f"[Erreur Python] Tags : {e}", flush=True)
        return []


async def fetch_search_from_mcp(query: str, tags: list):
    print(f"[Python] Recherche en cours: '{query}' | Filtres: {tags}", flush=True)
    try:
        async with Client(MCP_SERVER_URL) as client:
            args = {"search_terms": query, "limit": 20}
            if tags:
                args["tags"] = tags
            # TIMEOUT PASSE A 120 SECONDES DE SÉCURITÉ POUR LE RERANKING LOURD
            res = await asyncio.wait_for(client.call_tool("retrieve_search_documents", args), timeout=120.0)
            
            # 🚨 PARSING BLINDÉ (Comme dans chat_tab.py)
            data = None
            
            # 1. Essai avec l'attribut natif
            if hasattr(res, "structured_content") and res.structured_content:
                data = res.structured_content
            
            # 2. Si échec, extraction forcée depuis le contenu texte brut
            elif hasattr(res, "content"):
                import json
                text = "".join(getattr(c, "text", str(c)) for c in (res.content or []))
                if text:
                    try:
                        data = json.loads(text)
                    except:
                        pass
                        
            # 3. Récupération finale de la clé 'result' générée par le serveur
            if isinstance(data, dict):
                if "result" in data: return data["result"]
                return data
            if isinstance(data, list):
                return data
                
            return []
    except Exception as e:
        print(f"[Erreur Python] Search : {e}", flush=True)
        return []


async def fetch_document_file_from_mcp(chunk0_id: str):
    print(f"[Python] Demande de fichier pour l'ID : {chunk0_id}", flush=True)
    try:
        async with Client(MCP_SERVER_URL) as client:
            res = await asyncio.wait_for(
                client.call_tool("get_document_file", {"document_id": chunk0_id}),
                timeout=15.0
            )
            data = res.structured_content
            if isinstance(data, dict) and "result" in data:
                data = data["result"]
            if isinstance(data, dict) and data.get("success"):
                b64_str = data["file_base64"]
                filename = data.get("filename", "document")
                ext = data.get("extension", "").lower()
                file_bytes = base64.b64decode(b64_str)
                mime_type = "text/plain; charset=utf-8"
                if ext == ".pdf":
                    mime_type = "application/pdf"
                elif ext in [".html", ".htm"]:
                    mime_type = "text/html; charset=utf-8"
                elif ext == ".json":
                    mime_type = "application/json; charset=utf-8"
                safe_filename = urllib.parse.quote(filename)
                return Response(
                    content=file_bytes,
                    media_type=mime_type,
                    headers={"Content-Disposition": f"inline; filename*=utf-8''{safe_filename}"}
                )
            else:
                err = data.get("error") if isinstance(data, dict) else "Document introuvable ou erreur de l'outil"
                return HTMLResponse(f"<h3>Erreur de récupération: {err}</h3>", status_code=404)
    except Exception as e:
        return HTMLResponse(f"<h3>Erreur serveur lors du téléchargement : {e}</h3>", status_code=500)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recherche Sémantique</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        html, body { height: 100%; scrollbar-gutter: stable; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

        @property --angle {
            syntax: "<angle>";
            initial-value: 0deg;
            inherits: false;
        }

        @property --mouse-x { syntax: "<length>"; initial-value: 0px; inherits: false; }
        @property --mouse-y { syntax: "<length>"; initial-value: 0px; inherits: false; }
        @property --glow-size { syntax: "<length>"; initial-value: 0px; inherits: false; }

        @keyframes spin-halo { to { --angle: 360deg; } }

        @keyframes blink {
            0%, 80%, 100% { opacity: 0; }
            40%            { opacity: 1; }
        }

        @keyframes fadeSlideUp {
            from { opacity: 0; transform: translateY(12px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeSlideDown {
            from { opacity: 1; transform: translateY(0); }
            to   { opacity: 0; transform: translateY(8px); }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        @keyframes textPulse {
            0%, 100% { opacity: 0.3; }
            50%       { opacity: 1; }
        }

        @keyframes btnOut {
            to { opacity: 0; transform: scale(0.85); }
        }
        @keyframes btnIn {
            from { opacity: 0; transform: scale(0.85); }
            to   { opacity: 1; transform: scale(1); }
        }

        #submit-btn .btn-label {
            display: inline-block;
            animation: btnIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        #submit-btn .btn-label.leaving {
            animation: btnOut 0.15s ease-in forwards;
        }

        h1 a { font-size: clamp(1.25rem, 2.5vw, 2.25rem); }

        .interactive-title {
            display: inline-block;
            position: relative;
            text-decoration: none;
            cursor: pointer;
        }

        .title-glow {
            display: inline-block;
            background-color: #111827;
            background-image: radial-gradient(
                circle var(--glow-size) at var(--mouse-x) var(--mouse-y),
                rgba(255, 255, 255, 0.85) 0%,
                rgba(255, 255, 255, 0) 100%
            );
            background-repeat: no-repeat;
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            color: transparent;
            transition: --glow-size 0.3s ease;
        }

        #search-input {
            font-size: clamp(0.875rem, 1.3vw, 1.125rem);
            padding-top: clamp(0.6rem, 1vw, 0.875rem);
            padding-bottom: clamp(0.6rem, 1vw, 0.875rem);
            padding-left: clamp(0.875rem, 1.8vw, 1.5rem);
            padding-right: clamp(4.5rem, 9vw, 8rem);
        }

        #submit-btn {
            font-size: clamp(0.75rem, 1.1vw, 1rem);
            padding-left: clamp(0.875rem, 1.8vw, 1.5rem);
            padding-right: clamp(0.875rem, 1.8vw, 1.5rem);
            background-color: #111827;
            display: flex;
            align-items: center;
            justify-content: center;
            background-image: radial-gradient(
                circle var(--glow-size) at var(--mouse-x) var(--mouse-y),
                rgba(255, 255, 255, 0.6) 0%,
                transparent 100%
            );
            transition: --glow-size 0.3s ease,
                        background-color 0.4s ease,
                        width 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
            white-space: nowrap;
        }

        #submit-btn.loading {
            background-color: #6b7280;
            background-image: none;
            pointer-events: none;
            cursor: not-allowed;
        }

        .result-item { opacity: 0; }
        .result-item.visible { animation: fadeSlideUp 0.35s ease forwards; }
        .results-hiding { animation: fadeSlideDown 0.2s ease forwards; }

        #results-header {
            opacity: 0;
            animation: fadeIn 0.4s ease 0.1s forwards;
        }

        #page-wrapper {
            margin-inline: auto;
            transition: padding-top 0.55s cubic-bezier(0.4, 0, 0.2, 1),
                        padding-bottom 0.55s cubic-bezier(0.4, 0, 0.2, 1);
        }

        #search-container { width: 100%; }

        .search-wrapper {
            position: relative;
            border-radius: 9999px;
            isolation: isolate;
            width: 100%;
        }

        .search-wrapper::before {
            content: '';
            position: absolute;
            inset: -6px;
            border-radius: 9999px;
            filter: blur(10px);
            z-index: -1;
            transition: opacity 0.6s ease;
            opacity: 0;
            pointer-events: none;
            will-change: opacity;
        }

        .search-wrapper.loading::before {
            background: conic-gradient(
                from var(--angle),
                rgba(244, 114, 182, 0.35),
                rgba(129, 140, 248, 0.35),
                rgba(56, 189, 248, 0.35),
                rgba(52, 211, 153, 0.35),
                rgba(251, 191, 36, 0.35),
                rgba(244, 114, 182, 0.35)
            );
            animation: spin-halo 3s linear infinite;
            opacity: 1;
        }

        .dot-btn {
            animation: blink 1.4s infinite both;
            line-height: 1;
            color: rgba(255, 255, 255, 0.45);
        }
        .dot-btn:nth-child(2) { animation-delay: 0.2s; }
        .dot-btn:nth-child(3) { animation-delay: 0.4s; }

        #loading-indicator { display: none; }
        #loading-indicator.visible {
            display: block;
            animation: textPulse 3s ease-in-out infinite;
        }

        .tag-label span {
            font-size: clamp(0.7rem, 1vw, 0.875rem);
            padding: clamp(0.3rem, 0.55vw, 0.5rem) clamp(0.55rem, 1vw, 1rem);
            display: inline-block;
            position: relative;
            overflow: hidden;
        }

        .tag-label input:not(:checked) ~ span {
            background-color: #ffffff;
            background-image: radial-gradient(
                circle var(--glow-size, 0px) at var(--mouse-x, 50%) var(--mouse-y, 50%),
                rgba(0, 0, 0, 0.15) 0%,
                transparent 100%
            );
            transition: --glow-size 0.25s ease, background-color 0.2s ease, border-color 0.2s ease;
        }

        .tag-label input:checked ~ span {
            background-color: #111827;
            background-image: radial-gradient(
                circle var(--glow-size, 0px) at var(--mouse-x, 50%) var(--mouse-y, 50%),
                rgba(255, 255, 255, 0.6) 0%,
                transparent 100%
            );
            transition: --glow-size 0.25s ease, background-color 0.2s ease, border-color 0.2s ease;
        }

        /* --- STYLES MARKDOWN POUR LE RÉSUMÉ --- */
        .markdown-body { color: #1f2937; }
        .markdown-body p { margin-bottom: 0.75rem; }
        .markdown-body p:last-child { margin-bottom: 0; }
        .markdown-body ul { list-style-type: disc; padding-left: 1.5rem; margin-top: 0.5rem; margin-bottom: 0.75rem; }
        .markdown-body ol { list-style-type: decimal; padding-left: 1.5rem; margin-top: 0.5rem; margin-bottom: 0.75rem; }
        .markdown-body li { margin-bottom: 0.25rem; }
        .markdown-body strong { font-weight: 700; color: #111827; }
        .markdown-body em { font-style: italic; }
        .markdown-body code { font-family: monospace; background-color: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 0.25rem; font-size: 0.9em; }
    </style>
</head>
<body class="bg-white text-gray-900 font-sans antialiased selection:bg-gray-300">

    <div class="px-4 sm:px-6" id="page-wrapper">

        <h1 class="font-bold tracking-tight text-center text-black mb-5 sm:mb-8">
            <a href="?" title="Réinitialiser la recherche" class="interactive-title">
                <span class="title-glow">Recherche Sémantique</span>
            </a>
        </h1>

        <form method="POST" action="?" class="mb-4" id="search-form">
            <div id="search-container">
                <div class="search-wrapper" id="search-wrapper">
                    <input type="text" name="q" value="{{query_value}}" placeholder="Entrez votre recherche..." required
                        class="w-full rounded-full border-2 border-gray-300 focus:outline-none focus:border-black font-medium transition-colors placeholder-gray-500"
                        id="search-input">
                    <button type="submit" id="submit-btn"
                        class="absolute right-2 top-2 bottom-2 text-white rounded-full font-bold disabled:bg-gray-400 whitespace-nowrap overflow-hidden">
                        Chercher
                    </button>
                </div>

                <div class="mt-5 flex flex-wrap gap-2 justify-center">
                    {{tags_html}}
                </div>
            </div>
        </form>

        <div id="loading-indicator" class="text-center mt-2 mb-6">
            <span class="text-xs font-bold tracking-widest uppercase text-gray-400">
                Recherche en cours
            </span>
        </div>

        <div id="results-container" class="mt-4">
            {{results_html}}
        </div>

    </div>

    <script>
        const wrapper = document.getElementById('page-wrapper');
        const IS_CENTERED = {{is_centered}};

        (function() {
            const vw = window.innerWidth;
            wrapper.style.maxWidth = (vw <= 1440 ? Math.min(690, vw * 0.82) : 768) + 'px';
        })();

        function applyCentering() {
            if (!IS_CENTERED) {
                wrapper.style.paddingTop = '2rem';
                wrapper.style.paddingBottom = '2rem';
                return;
            }
            document.body.style.overflow = 'hidden';
            const pad = Math.max(48, (window.innerHeight - wrapper.offsetHeight) / 2 - 60);
            wrapper.style.paddingTop = pad + 'px';
            wrapper.style.paddingBottom = pad + 'px';
        }

        wrapper.style.transition = 'none';
        applyCentering();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                wrapper.style.transition = 'padding-top 0.55s cubic-bezier(0.4, 0, 0.2, 1), padding-bottom 0.55s cubic-bezier(0.4, 0, 0.2, 1)';
            });
        });

        document.getElementById('search-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const form = this;
            const resultsContainer = document.getElementById('results-container');
            const hasResults = resultsContainer.children.length > 0;

            document.body.style.overflow = '';
            wrapper.style.paddingTop = '2rem';
            wrapper.style.paddingBottom = '2rem';

            const triggerSubmit = () => {
                document.getElementById('loading-indicator').classList.add('visible');
                document.getElementById('search-wrapper').classList.add('loading');

                const btn = document.getElementById('submit-btn');
                btn.style.setProperty('--glow-size', '0px');
                btn.disabled = true;

                const ghost = btn.cloneNode(false);
                ghost.style.cssText = 'position:absolute;visibility:hidden;width:auto;pointer-events:none;';
                ghost.innerHTML = `<span class="dot-btn">.</span><span class="dot-btn">.</span><span class="dot-btn">.</span>`;
                document.body.appendChild(ghost);
                const targetWidth = ghost.offsetWidth + 'px';
                document.body.removeChild(ghost);

                btn.style.width = btn.offsetWidth + 'px';

                btn.innerHTML = `<span class="btn-label leaving">Chercher</span>`;

                setTimeout(() => {
                    btn.innerHTML = `<span class="btn-label">
                        <span class="dot-btn">.</span>
                        <span class="dot-btn">.</span>
                        <span class="dot-btn">.</span>
                    </span>`;

                    requestAnimationFrame(() => {
                        btn.style.width = targetWidth;
                    });

                    setTimeout(() => { btn.classList.add('loading'); }, 50);

                    requestAnimationFrame(() => { requestAnimationFrame(() => { form.submit(); }); });
                }, 150);
            };

            const fadeOutThenSubmit = () => {
                if (!hasResults) { triggerSubmit(); return; }
                resultsContainer.classList.add('results-hiding');
                resultsContainer.addEventListener('animationend', () => {
                    resultsContainer.style.visibility = '';
                    resultsContainer.style.display = 'none';
                    triggerSubmit();
                }, { once: true });
            };

            if (hasResults) {
                window.scrollTo({ top: 0, behavior: 'smooth' });
                const onScrollEnd = () => {
                    if (window.scrollY <= 5) {
                        window.removeEventListener('scroll', onScrollEnd);
                        clearTimeout(fallback);
                        fadeOutThenSubmit();
                    }
                };
                const fallback = setTimeout(() => {
                    window.removeEventListener('scroll', onScrollEnd);
                    fadeOutThenSubmit();
                }, 600);
                window.addEventListener('scroll', onScrollEnd);
            } else {
                if (IS_CENTERED) {
                    wrapper.addEventListener('transitionend', fadeOutThenSubmit, { once: true });
                } else {
                    fadeOutThenSubmit();
                }
            }
        });

        const interactiveTitle = document.querySelector('.interactive-title');
        const titleGlow = document.querySelector('.title-glow');
        const submitBtn = document.getElementById('submit-btn');

        if (interactiveTitle && titleGlow) {
            interactiveTitle.addEventListener('mousemove', (e) => {
                const rect = interactiveTitle.getBoundingClientRect();
                titleGlow.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
                titleGlow.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
            });
            interactiveTitle.addEventListener('mouseenter', () => {
                titleGlow.style.setProperty('--glow-size', '55px');
            });
            interactiveTitle.addEventListener('mouseleave', () => {
                titleGlow.style.setProperty('--glow-size', '0px');
            });
        }

        if (submitBtn) {
            submitBtn.addEventListener('mousemove', (e) => {
                const rect = submitBtn.getBoundingClientRect();
                submitBtn.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
                submitBtn.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
            });
            submitBtn.addEventListener('mouseenter', () => {
                submitBtn.style.setProperty('--glow-size', '30px');
            });
            submitBtn.addEventListener('mouseleave', () => {
                submitBtn.style.setProperty('--glow-size', '0px');
            });
        }

        document.querySelectorAll('.tag-label').forEach(label => {
            const span = label.querySelector('span');
            if (!span) return;

            label.addEventListener('mousemove', (e) => {
                const rect = span.getBoundingClientRect();
                span.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
                span.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
            });

            label.addEventListener('mouseenter', () => {
                span.style.setProperty('--glow-size', '30px');
            });

            label.addEventListener('mouseleave', () => {
                span.style.setProperty('--glow-size', '0px');
            });
        });

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                document.querySelectorAll('.result-item').forEach((el, i) => {
                    setTimeout(() => { el.classList.add('visible'); }, i * 80);
                });
            });
        });
    </script>
</body>
</html>
"""


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def serve_page(request: Request):

    download_id = request.query_params.get("download")
    if download_id:
        return await fetch_document_file_from_mcp(download_id)

    query = ""
    selected_tags = []

    if request.method == "POST":
        try:
            form_data = await request.form()
            query = str(form_data.get("q", "")).strip()
            selected_tags = form_data.getlist("t")
        except Exception as e:
            print(f"[Erreur form] {e}")

    tags_data = await fetch_tags_from_mcp()

    results_data = []
    if query:
        results_data = await fetch_search_from_mcp(query, selected_tags)

    tags_html = ""
    if not tags_data:
        tags_html = '<span class="text-gray-500 font-medium text-sm">Aucune source disponible.</span>'
    else:
        for t in tags_data:
            tag_name = t.get("tag", t) if isinstance(t, dict) else str(t)
            is_checked = "checked" if tag_name in selected_tags else ""
            tags_html += f"""
            <label class="cursor-pointer select-none tag-label">
                <input type="checkbox" name="t" value="{tag_name}" class="peer hidden" {is_checked}>
                <span class="inline-block rounded-full font-bold border-2 border-gray-200 text-gray-700 peer-checked:bg-black peer-checked:text-white peer-checked:border-black hover:border-gray-400 transition-colors">
                    {tag_name}
                </span>
            </label>
            """

    results_html = ""
    is_centered = "true"

    if not query:
        is_centered = "true"
    elif query and not results_data:
        is_centered = "false"
        results_html = """
        <div class="text-center py-20 text-black font-bold text-lg">
            <p>Aucun document ne correspond à cette recherche.</p>
        </div>
        """
    else:
        is_centered = "false"
        results_html = f'<p id="results-header" class="text-sm font-bold text-gray-500 mb-8 border-b-2 border-gray-200 pb-4">{len(results_data)} RÉSULTAT(S)</p>'

        for i, row in enumerate(results_data):
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue

            filename = str(row[0])
            summary = str(row[2])
            chunk0_id = str(row[3])
            score = f"{float(row[4]):.4f}"
            doc_tags = row[5] if isinstance(row[5], list) else []

            tags_badges = " • ".join(doc_tags) if doc_tags else "Aucun tag"
            
            preview = summary
            if len(preview) > 600:
                preview = preview[:600] + "..."
                
            # Conversion du Markdown en HTML
            preview_html = markdown.markdown(preview)

            safe_filename = urllib.parse.quote(filename)

            results_html += f"""
            <div class="py-8 border-b border-gray-200 last:border-0 result-item">
                <h3 class="text-xl font-bold mb-3">
                    <a href="{safe_filename}?download={chunk0_id}" target="_blank" class="text-black hover:text-blue-600 hover:underline transition-colors" title="Ouvrir le document">
                        {filename}
                    </a>
                </h3>
                <div class="text-base text-gray-800 font-medium leading-relaxed mb-4 markdown-body">
                    {preview_html}
                </div>
                <div class="flex flex-wrap gap-4 text-sm font-bold text-gray-500">
                    <span title="Score de pertinence">Score: {score}</span>
                    <span>Source: {tags_badges}</span>
                    <span class="font-mono text-xs mt-0.5" title="{chunk0_id}">ID: {str(chunk0_id)[:8]}...</span>
                </div>
            </div>
            """

    final_page = HTML_TEMPLATE.replace("{{query_value}}", query.replace('"', '&quot;'))
    final_page = final_page.replace("{{tags_html}}", tags_html)
    final_page = final_page.replace("{{results_html}}", results_html)
    final_page = final_page.replace("{{is_centered}}", is_centered)

    return HTMLResponse(content=final_page)


if __name__ == "__main__":
    import uvicorn
    print("="*60, flush=True)
    print("🚀 Serveur Web SSR Multi-instances démarré (Port 8000)", flush=True)
    print("="*60, flush=True)
    
    # Lancement de 4 "instances" (workers) en parallèle
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, workers=4)
