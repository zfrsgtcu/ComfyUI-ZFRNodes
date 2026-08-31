import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/*
 * ZFRNodes — dinamik referans görsel inputları.
 *
 * "Simple Image Generator (Multiple)" node'u için referans görsel inputları
 * (reference_image_1..8) runtime'da gerçekten eklenip kaldırılır:
 *
 *   - Node ilk oluştuğunda yalnızca reference_image_1 bulunur.
 *   - Bir referans bağlandığında, hemen altına yeni bir boş referans alanı
 *     (reference_image_N+1) otomatik eklenir — en fazla 8 adet.
 *   - Bir referans koptuğunda, en alttaki kullanılmayan fazla boş slotlar
 *     toplanır; her zaman "bağlı olanlar + tek bir boş slot" kalır.
 *   - Hiç referans bağlı değilse yalnızca reference_image_1 görünür.
 *
 * Python tarafı bu inputları **kwargs ile alır; bağlı olmayanlar hiç
 * gönderilmez. İsimlendirme (reference_image_N) iki taraf arasında ortaktır.
 *
 * Not: Python INPUT_TYPES yalnızca reference_image_1'i tanımlar; 2..8 burada
 * dinamik olarak eklenir. ComfyUI, JS ile eklenen inputları çalıştırırken
 * prompt'a otomatik dahil eder.
 */

/*
 * ZFRNodes — Simple Image Generator (Multiple) referans önizlemesi.
 *
 * Bu node artık tek bir "reference_images" girişi alır (IMAGE batch). Python
 * tarafı batch'i arkada image 1, image 2, ... olarak böler. Node çalıştıktan
 * sonra backend, kullanılan referansların küçük önizlemelerini gönderir ve
 * burada node'un üstünde "image N" etiketli kompakt bir thumbnail tablosu
 * olarak gösterilir.
 *
 * Not: Referans görselleri çalışma anında oluştuğundan önizleme yalnızca node
 * bir kez çalıştıktan SONRA görünür.
 */
const SIGM_NODE_NAME = "Simple Image Generator (Multiple)";

app.registerExtension({
    name: "ZFRNodes.MultipleRefPreview",

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== SIGM_NODE_NAME) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupRefPreviewUI(this);
            return r;
        };

        // Backend'den gelen önizleme verisini (executed event) yakala.
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const res = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            if (this._zfrRefPreview && message && message.ref_previews) {
                this._zfrRefPreview.update(message.ref_previews);
            }
            return res;
        };
    },
});

function setupRefPreviewUI(node) {
    const state = { node, items: [] };
    node._zfrRefPreview = state;

    const root = document.createElement("div");
    root.style.cssText =
        "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;" +
        "font-size:11px;color:#ddd;";

    const header = document.createElement("div");
    header.style.cssText = "color:#888;";
    header.textContent = "Reference images (after running)";

    const grid = document.createElement("div");
    grid.style.cssText =
        "display:flex;flex-wrap:wrap;gap:4px;width:100%;box-sizing:border-box;";

    root.appendChild(header);
    root.appendChild(grid);

    function render() {
        grid.innerHTML = "";
        if (!state.items.length) {
            const empty = document.createElement("div");
            empty.style.cssText = "color:#666;font-style:italic;";
            empty.textContent = "(no references yet)";
            grid.appendChild(empty);
        }
        state.items.forEach((src, idx) => {
            const cell = document.createElement("div");
            cell.style.cssText =
                "display:flex;flex-direction:column;align-items:center;gap:2px;";
            const img = document.createElement("img");
            img.src = src;
            img.style.cssText =
                "width:40px;height:40px;object-fit:cover;border-radius:4px;" +
                "border:1px solid #444;background:#000;";
            const label = document.createElement("span");
            label.textContent = `image ${idx + 1}`;
            label.style.cssText = "font-size:10px;color:#aaa;";
            cell.appendChild(img);
            cell.appendChild(label);
            grid.appendChild(cell);
        });
        // Boyutu zorla değiştirme — kullanıcının ayarladığı boyut kalsın.
        node.setDirtyCanvas(true, true);
    }

    // Backend ref_previews mesajı: data-URL veya /view URL listesi.
    state.update = function (srcs) {
        state.items = Array.isArray(srcs) ? srcs : [];
        render();
    };

    node.addDOMWidget("zfr_ref_preview", "div", root, {
        serialize: false,
        hideOnZoom: false,
    });

    render();
}

/*
 * ZFRNodes — Reference Image Loader.
 *
 * "Reference Image Loader" node'una, node içinden tek tek görsel yüklemeye
 * yarayan bir UI ekler:
 *
 *   - "Upload images" butonu → dosya seçici açar (çoklu seçim destekli).
 *   - Seçilen her görsel /upload/image ile input klasörüne yüklenir ve
 *     "image 1, image 2, ..." şeklinde sıralı bir tabloya eklenir (max 8).
 *   - Her satır küçük bir thumbnail + ad + sil (×) düğmesi içerir; yer
 *     kaplamaması için thumbnail küçüktür.
 *   - Bir satıra tıklanınca görsel büyür (satır genişler); tekrar tıklanınca
 *     kapanır.
 *   - Yüklenen dosya adları gizli "images" widget'ına JSON listesi olarak
 *     yazılır; Python tarafı (reference_image_loader.py) bunu okuyup batch'ler.
 */
const RIL_NODE_NAME = "Reference Image Loader";
const RIL_MAX_IMAGES = 8;

app.registerExtension({
    name: "ZFRNodes.ReferenceImageLoader",

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== RIL_NODE_NAME) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupReferenceLoaderUI(this);
            return r;
        };

        // Workflow yüklendiğinde kayıtlı dosya adlarından tabloyu geri çiz.
        // Çıkış slotlarını workflow zaten kaydettiği için yeniden inşa ETME
        // (applyOutputs=false) — sadece tablo + select değerini güncelle.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const res = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => {
                if (this._zfrRefLoader) this._zfrRefLoader.reload({ applyOutputs: false });
            });
            return res;
        };
    },
});

function setupReferenceLoaderUI(node) {
    // Python'un required "images" input'unu besleyen gerçek string widget.
    // node.widgets'ta TUTULUR (prompt'a değeri garanti gönderilsin) ama
    // "hidden" tipine çevrilip yer kaplamaz/çizilmez; ham JSON görünmez.
    const imagesWidget = node.widgets?.find((w) => w.name === "images");
    if (imagesWidget) {
        imagesWidget.type = "hidden";
        imagesWidget.computeSize = () => [0, 0];
        // Bazı frontend sürümlerinde gizli widget yine de canvas'a çizilmesin.
        imagesWidget.draw = () => {};
        imagesWidget.hidden = true;
    }

    // output_mode native combo widget'ını da gizle; yerine footer'da kendi
    // <select>'imizi gösterip değeri bu widget'a yazacağız (Python bunu okur).
    const modeWidget = node.widgets?.find((w) => w.name === "output_mode");
    if (modeWidget) {
        modeWidget.type = "hidden";
        modeWidget.computeSize = () => [0, 0];
        modeWidget.draw = () => {};
        modeWidget.hidden = true;
    }

    // ---- durum ----
    const state = {
        items: [],          // [{ name, subfolder, type, expanded }]
        node,
        imagesWidget,
        modeWidget,
    };
    node._zfrRefLoader = state;

    function readValue() {
        try {
            const parsed = JSON.parse((imagesWidget?.value) || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function writeValue() {
        if (imagesWidget) {
            imagesWidget.value = JSON.stringify(state.items.map((it) => it.name));
        }
    }

    function urlFor(item) {
        const params = new URLSearchParams({
            filename: item.name,
            subfolder: item.subfolder || "",
            type: item.type || "input",
        });
        return api.apiURL(`/view?${params.toString()}&t=${Date.now()}`);
    }

    // ---- DOM ----
    // Dikey yerleşim: ÜSTTE kaydırılabilir liste, ALTTA sabit buton+sayaç.
    const root = document.createElement("div");
    root.className = "zfr-ril-root";
    root.style.cssText =
        "display:flex;flex-direction:column;width:100%;height:100%;font-size:12px;" +
        "color:#ddd;box-sizing:border-box;overflow:hidden;";

    // Kaydırılabilir liste alanı (taşmayı engeller).
    const list = document.createElement("div");
    list.style.cssText =
        "flex:1 1 auto;display:flex;flex-direction:column;gap:4px;" +
        "overflow-y:auto;overflow-x:hidden;min-height:0;padding:2px;box-sizing:border-box;";

    // Tabanda sabit kalan kontrol çubuğu.
    const footer = document.createElement("div");
    footer.style.cssText =
        "flex:0 0 auto;display:flex;flex-direction:column;gap:4px;" +
        "padding-top:6px;border-top:1px solid #333;box-sizing:border-box;";

    const uploadBtn = document.createElement("button");
    uploadBtn.textContent = "⬆ Upload images";
    uploadBtn.title = "Click to choose files — or drag & drop images here, or select this node and press Ctrl+V";
    uploadBtn.style.cssText =
        "padding:6px 10px;border:1px solid #555;border-radius:6px;background:#2a2a2a;" +
        "color:#eee;cursor:pointer;font-size:12px;width:100%;box-sizing:border-box;";
    uploadBtn.onmouseenter = () => (uploadBtn.style.background = "#383838");
    uploadBtn.onmouseleave = () => (uploadBtn.style.background = "#2a2a2a");

    // Sürükle-bırak / yapıştır ipucu (buton altında, soluk).
    const hint = document.createElement("div");
    hint.textContent = "or drag & drop / paste (Ctrl+V)";
    hint.style.cssText = "font-size:10px;color:#666;text-align:center;";

    const counter = document.createElement("div");
    counter.style.cssText = "font-size:11px;color:#888;text-align:center;";

    // Çıkış modu seçimi (upload butonunun altında).
    const modeRow = document.createElement("div");
    modeRow.style.cssText =
        "display:flex;align-items:center;gap:6px;width:100%;box-sizing:border-box;";

    const modeLabel = document.createElement("span");
    modeLabel.textContent = "output:";
    modeLabel.style.cssText = "flex:0 0 auto;font-size:11px;color:#aaa;";

    const modeSelect = document.createElement("select");
    modeSelect.style.cssText =
        "flex:1 1 auto;min-width:0;padding:4px 6px;border:1px solid #555;border-radius:6px;" +
        "background:#2a2a2a;color:#eee;cursor:pointer;font-size:12px;box-sizing:border-box;";
    // Net, 2 kelimelik etiketler; value Python'un beklediği mod adı.
    const MODE_OPTIONS = [
        { value: "batch", label: "Single Batch" },
        { value: "separate", label: "Separate Images" },
        { value: "both", label: "Batch + Separate" },
    ];
    for (const opt of MODE_OPTIONS) {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        modeSelect.appendChild(o);
    }

    modeRow.appendChild(modeLabel);
    modeRow.appendChild(modeSelect);

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.multiple = true;
    fileInput.style.display = "none";

    footer.appendChild(uploadBtn);
    footer.appendChild(hint);
    footer.appendChild(counter);
    footer.appendChild(modeRow);
    root.appendChild(list);
    root.appendChild(footer);
    root.appendChild(fileInput);

    // ---- render ----
    function render() {
        list.innerHTML = "";
        state.items.forEach((item, idx) => {
            const row = document.createElement("div");
            row.style.cssText =
                "display:flex;flex-direction:column;border:1px solid #444;border-radius:6px;" +
                "background:#1f1f1f;overflow:hidden;width:100%;box-sizing:border-box;";

            const head = document.createElement("div");
            head.style.cssText =
                "display:flex;align-items:center;gap:8px;padding:4px 6px;cursor:pointer;" +
                "min-width:0;box-sizing:border-box;";

            const thumb = document.createElement("img");
            thumb.src = urlFor(item);
            thumb.style.cssText =
                "width:30px;height:30px;object-fit:cover;border-radius:4px;flex:0 0 auto;background:#000;";

            const label = document.createElement("span");
            label.textContent = `image ${idx + 1}`;
            label.style.cssText = "flex:0 0 auto;font-weight:600;color:#eee;white-space:nowrap;";

            const nameSpan = document.createElement("span");
            nameSpan.textContent = item.name;
            nameSpan.title = item.name;
            nameSpan.style.cssText =
                "flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;" +
                "white-space:nowrap;color:#888;font-size:11px;";

            const del = document.createElement("button");
            del.textContent = "✕";
            del.title = "Remove";
            del.style.cssText =
                "flex:0 0 auto;border:none;background:transparent;color:#d66;cursor:pointer;font-size:13px;padding:2px 4px;";
            del.onclick = (e) => {
                e.stopPropagation();
                state.items.splice(idx, 1);
                writeValue();
                render();
                refreshOutputs();
                resize();
            };

            // Büyüt/kapat alanı.
            const big = document.createElement("div");
            big.style.cssText = item.expanded
                ? "padding:6px;display:flex;justify-content:center;background:#151515;box-sizing:border-box;"
                : "display:none;";
            if (item.expanded) {
                const bigImg = document.createElement("img");
                bigImg.src = urlFor(item);
                bigImg.style.cssText =
                    "max-width:100%;max-height:260px;object-fit:contain;border-radius:4px;";
                big.appendChild(bigImg);
            }

            head.onclick = () => {
                item.expanded = !item.expanded;
                render();
                resize();
            };

            head.appendChild(thumb);
            head.appendChild(label);
            head.appendChild(nameSpan);
            head.appendChild(del);
            row.appendChild(head);
            row.appendChild(big);
            list.appendChild(row);
        });

        counter.textContent = `${state.items.length} / ${RIL_MAX_IMAGES} images`;
        uploadBtn.disabled = state.items.length >= RIL_MAX_IMAGES;
        uploadBtn.style.opacity = uploadBtn.disabled ? "0.5" : "1";
        uploadBtn.style.cursor = uploadBtn.disabled ? "not-allowed" : "pointer";
    }

    // Bir satırın (kapalı/açık) yaklaşık yüksekliği — node yüksekliği için.
    const ROW_H = 40;          // kapalı satır (thumbnail + padding)
    const ROW_EXPANDED_H = 280; // açık satır (büyük görsel)
    const FOOTER_H = 116;       // buton + ipucu + sayaç + mod select + border
    const PADDING_H = 12;

    // DOM widget'ın node içinde kaplayacağı yüksekliği hesaplar; böylece
    // node gövdesi içeriğe göre büyür, görseller dışarı taşmaz.
    function contentHeight() {
        let h = PADDING_H + FOOTER_H;
        for (const item of state.items) {
            h += (item.expanded ? ROW_EXPANDED_H : ROW_H) + 4;
        }
        // Min: en az footer + bir satırlık boşluk; Max: aşırı uzamayı sınırla
        // (liste kendi içinde kaydırılır).
        return Math.min(Math.max(h, FOOTER_H + PADDING_H + 30), 560);
    }

    function resize() {
        // Boyutu zorla değiştirme — kullanıcının ayarladığı genişlik/yükseklik
        // korunur. DOM widget yüksekliği getHeight/computeSize ile bildirilir;
        // ComfyUI içeriği o yüksekliğe göre yerleştirir (taşma/genişleme olmaz).
        node.setDirtyCanvas(true, true);
    }

    // ---- çıkış modu ----
    // Python'un sabit çıkış listesi: index 0 = batch, 1..8 = image_1..8, 9 = count.
    // Seçilen moda göre ilgili çıkışları gizler/gösterir. Bağlı bir çıkış
    // asla gizlenmez (link kopmasın). Gizleme = node.outputs'tan çıkarma.
    const OUTPUT_DEFS = [
        { name: "batch", type: "IMAGE" },
        ...Array.from({ length: RIL_MAX_IMAGES }, (_, i) => ({
            name: `image_${i + 1}`,
            type: "IMAGE",
        })),
        { name: "count", type: "INT" },
    ];

    function wantsOutput(name, mode) {
        if (name === "count") return true; // count her zaman görünür.
        if (name === "batch") return mode === "batch" || mode === "both";

        // image_N: yalnızca separate/both modunda VE yüklenen görsel sayısı
        // kadar görünür. Böylece çıkış sayısı eklenen resme göre artar/azalır.
        const isSeparateMode = mode === "separate" || mode === "both";
        if (!isSeparateMode) return false;

        const n = parseInt(name.slice("image_".length), 10);
        // En az 1 slot göster (boşken bile), üst sınır = yüklenen görsel sayısı.
        const shown = Math.max(1, state.items.length);
        return n <= shown;
    }

    // Bir çıkışın mevcut bağlantılarını {hedef node id, hedef slot} olarak topla.
    function captureLinks(outputName) {
        const graph = node.graph;
        const idx = (node.outputs || []).findIndex((o) => o.name === outputName);
        if (idx === -1 || !graph) return [];
        const out = node.outputs[idx];
        const links = out.links || [];
        const targets = [];
        for (const linkId of links) {
            const link = graph.links[linkId];
            if (link) {
                targets.push({ nodeId: link.target_id, slot: link.target_slot });
            }
        }
        return targets;
    }

    /*
     * Çıkışları moda göre yeniden inşa eder. ComfyUI bağlantıları çıkış
     * INDEX'iyle (origin_slot) takip ettiğinden, gizleyince index'ler kayar.
     * Bu yüzden: önce tüm bağlantıları İSİMLE kaydet → çıkışları kanonik
     * sırada (batch, image_1..8, count) yalnızca istenenlerle yeniden kur →
     * kaydedilen bağlantıları isimle doğru yeni slota geri bağla.
     */
    function applyOutputMode(mode) {
        const graph = node.graph;

        // 1) Mevcut bağlantıları isimle kaydet.
        const saved = {};
        for (const def of OUTPUT_DEFS) {
            const t = captureLinks(def.name);
            if (t.length) saved[def.name] = t;
        }

        // 2) Tüm çıkışları kaldır (sondan başa, index kaymasın).
        if (node.outputs) {
            for (let i = node.outputs.length - 1; i >= 0; i--) {
                node.removeOutput(i);
            }
        }

        // 3) Kanonik sırada istenen çıkışları ekle.
        for (const def of OUTPUT_DEFS) {
            if (wantsOutput(def.name, mode)) {
                node.addOutput(def.name, def.type);
            }
        }

        // 4) Bağlantıları isimle geri kur.
        if (graph) {
            for (const def of OUTPUT_DEFS) {
                const targets = saved[def.name];
                if (!targets) continue;
                const slot = node.outputs.findIndex((o) => o.name === def.name);
                if (slot === -1) continue; // bu mod'da gizli → bağlantı düşer.
                for (const tg of targets) {
                    const target = graph.getNodeById(tg.nodeId);
                    if (target) node.connect(slot, target, tg.slot);
                }
            }
        }

        node.setDirtyCanvas(true, true);
    }

    function setMode(mode) {
        if (modeWidget) modeWidget.value = mode;
        modeSelect.value = mode;
        applyOutputMode(mode);
        resize();
    }

    // Görsel sayısı değişince çıkış slotlarını (image_N) güncel modla yenile.
    function refreshOutputs() {
        applyOutputMode(modeSelect.value || "batch");
    }

    modeSelect.onchange = () => setMode(modeSelect.value);

    // ---- upload ----
    async function uploadFile(file) {
        const body = new FormData();
        body.append("image", file);
        body.append("type", "input");
        body.append("overwrite", "false");
        const resp = await api.fetchApi("/upload/image", { method: "POST", body });
        if (resp.status !== 200) {
            throw new Error(`upload failed (${resp.status})`);
        }
        return await resp.json(); // { name, subfolder, type }
    }

    /*
     * Bir dosya listesini (file picker / sürükle-bırak / yapıştır) tek tek
     * yükler ve tabloya ekler. MAX sınırını aşmaz, görsel olmayanları atlar.
     */
    async function addFiles(files) {
        const list = Array.from(files || []).filter(
            (f) => f && (f.type ? f.type.startsWith("image/") : true)
        );
        if (!list.length) return;
        let added = 0;
        for (const file of list) {
            if (state.items.length >= RIL_MAX_IMAGES) break;
            try {
                const data = await uploadFile(file);
                state.items.push({
                    name: data.name,
                    subfolder: data.subfolder || "",
                    type: data.type || "input",
                    expanded: false,
                });
                added++;
            } catch (err) {
                console.error("[ZFRNodes] Reference image upload failed:", err);
            }
        }
        if (added) {
            writeValue();
            render();
            refreshOutputs();
            resize();
        }
    }

    fileInput.onchange = async () => {
        const files = Array.from(fileInput.files || []);
        fileInput.value = ""; // aynı dosya tekrar seçilebilsin.
        await addFiles(files);
    };

    uploadBtn.onclick = () => {
        if (state.items.length >= RIL_MAX_IMAGES) return;
        fileInput.click();
    };

    // ---- sürükle-bırak ----
    // Görsel dosyalarını doğrudan node'un UI'ına bırakınca ekler. dragover'da
    // varsayılanı engellemek "drop"un tetiklenmesi için şart; ComfyUI canvas'ı
    // olayı kapmasın diye stopPropagation da yapılır.
    function isImageDrag(e) {
        const dt = e.dataTransfer;
        if (!dt) return false;
        if (dt.files && dt.files.length) return true;
        return Array.from(dt.items || []).some((it) => it.kind === "file");
    }
    root.addEventListener("dragover", (e) => {
        if (!isImageDrag(e)) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
        root.style.outline = "2px dashed #5a7da0";
        root.style.outlineOffset = "-2px";
    });
    root.addEventListener("dragleave", (e) => {
        e.stopPropagation();
        root.style.outline = "";
    });
    root.addEventListener("drop", async (e) => {
        if (!isImageDrag(e)) return;
        e.preventDefault();
        e.stopPropagation();
        root.style.outline = "";
        const files = e.dataTransfer.files;
        if (files && files.length) await addFiles(files);
    });

    // ---- yapıştır (Ctrl+V) ----
    // Bu node SEÇİLİYKEN (başlık çubuğu dahil) veya UI'ı üzerindeyken pano'daki
    // görseli ekler. CAPTURE fazında dinlenir ki ComfyUI'nin kendi paste
    // handler'ından ÖNCE çalışsın ve Load Image node'u oluşturmasını engellesin
    // (stopImmediatePropagation).
    let hovered = false;
    root.addEventListener("pointerenter", () => (hovered = true));
    root.addEventListener("pointerleave", () => (hovered = false));

    function isTargetNode() {
        if (hovered) return true;
        if (node.selected) return true;
        const sel = node.graph && node.graph.selected_nodes;
        if (sel) {
            // selected_nodes bir obje (id->node) veya dizi olabilir.
            if (Array.isArray(sel)) return sel.includes(node);
            return Object.values(sel).includes(node);
        }
        return false;
    }

    const onPaste = async (e) => {
        if (!isTargetNode()) return;
        // Metin alanına (textarea/input) yapıştırılıyorsa karışma.
        const t = e.target;
        if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT")) return;

        const items = (e.clipboardData && e.clipboardData.items) || [];
        const files = [];
        for (const it of items) {
            if (it.kind === "file" && it.type && it.type.startsWith("image/")) {
                const f = it.getAsFile();
                if (f) files.push(f);
            }
        }
        if (files.length) {
            // ComfyUI'nin global paste'ini (Load Image oluşturma) tamamen durdur.
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            await addFiles(files);
        }
    };
    // Capture = true: ComfyUI'nin document-level handler'ından önce yakalanır.
    document.addEventListener("paste", onPaste, true);
    // Node silinince listener'ı temizle (sızıntı olmasın). Capture'da
    // eklendiği için capture'da kaldırılmalı.
    const onRemovedPaste = node.onRemoved;
    node.onRemoved = function () {
        document.removeEventListener("paste", onPaste, true);
        return onRemovedPaste ? onRemovedPaste.apply(this, arguments) : undefined;
    };

    // Kayıtlı dosya adlarından tabloyu ve modu kur.
    // applyOutputs=false iken çıkış slotlarına dokunulmaz (workflow yüklemede,
    // slotlar zaten kayıtlı gelir; yeniden inşa bağlantıları riske atar).
    state.reload = function (opts) {
        const applyOutputs = !opts || opts.applyOutputs !== false;
        const names = readValue();
        state.items = names.slice(0, RIL_MAX_IMAGES).map((name) => ({
            name,
            subfolder: "",
            type: "input",
            expanded: false,
        }));
        // Mod'u native widget'tan oku; geçersizse "batch".
        let mode = (modeWidget && modeWidget.value) || "batch";
        if (!MODE_OPTIONS.some((o) => o.value === mode)) mode = "batch";
        modeSelect.value = mode;
        if (modeWidget) modeWidget.value = mode;
        if (applyOutputs) applyOutputMode(mode);
        render();
        resize();
    };

    // Sadece UI taşıyan DOM widget (değer gerçek "images" widget'ında durur).
    const domWidget = node.addDOMWidget("zfr_ref_loader_ui", "div", root, {
        serialize: false,
        hideOnZoom: false,
    });

    // DOM widget'ın node içindeki yüksekliğini içeriğe göre bildir
    // (ComfyUI sürümüne göre computeSize veya getHeight kullanılır).
    domWidget.computeSize = (width) => [width, contentHeight()];
    domWidget.getHeight = () => contentHeight();

    // SADECE ilk oluşturmada bir kez yeterli genişlik ver; sonra kullanıcının
    // ayarladığı boyuta dokunma.
    if (!node._zfrSizedOnce) {
        node._zfrSizedOnce = true;
        requestAnimationFrame(() => {
            if (node.size && node.size[0] < 300) {
                node.setSize([300, node.size[1]]);
                node.setDirtyCanvas(true, true);
            }
        });
    }

    // İlk kurulumda mevcut değeri ve modu yansıt.
    state.reload();
}

/*
 * ZFRNodes — Story Director dinamik sahne alanları.
 *
 * frame_count = "auto"  -> tek serbest "user_input" kutusu (hikâyeyi bütün yaz).
 * frame_count = N (3..) -> N adet ayrı "Sahne N" metin kutusu açılır; her biri
 *   o sahnenin direktifini alır. İçerikleri gizli "scenes" widget'ına JSON
 *   listesi olarak yazılır; Python tarafı "Scene 1: ... / Scene 2: ..." olarak
 *   user_prompt'a çevirir.
 */
const SD_NODE_NAME = "Story Director";

app.registerExtension({
    name: "ZFRNodes.StoryDirectorScenes",

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== SD_NODE_NAME) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupStoryDirectorUI(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const res = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => {
                if (this._zfrStoryDir) this._zfrStoryDir.reload();
            });
            return res;
        };
    },
});

function setupStoryDirectorUI(node) {
    const frameWidget = node.widgets?.find((w) => w.name === "frame_count");
    const userInputWidget = node.widgets?.find((w) => w.name === "user_input");

    // Gizli "scenes" widget'ı (Python ile paylaşılan veri).
    const scenesWidget = node.widgets?.find((w) => w.name === "scenes");
    if (scenesWidget) {
        scenesWidget.type = "hidden";
        scenesWidget.computeSize = () => [0, 0];
        scenesWidget.draw = () => {};
        scenesWidget.hidden = true;
    }

    // values: [{ text: "", type: "" }] — type "" = kullanıcı seçmedi (standart düzen).
    const state = { node, frameWidget, userInputWidget, scenesWidget, values: [] };
    node._zfrStoryDir = state;

    // Tek bir sahne satırının (label + textarea + type select + boşluk) yüksekliği.
    const SCENE_ROW_H = 110;
    const SCENES_HEADER_H = 26;
    const MIN_NODE_WIDTH = 320;

    // ---- DOM ----
    const root = document.createElement("div");
    root.style.cssText =
        "display:flex;flex-direction:column;gap:12px;width:100%;box-sizing:border-box;" +
        "padding:2px 2px 6px;font-size:12px;color:#ddd;";

    // Eski (düz string) ve yeni ({text,type}) formatı normalize eder.
    function normScene(s) {
        if (s && typeof s === "object") {
            return { text: String(s.text || ""), type: String(s.type || "") };
        }
        return { text: String(s || ""), type: "" };
    }

    function readScenes() {
        try {
            const v = JSON.parse(scenesWidget?.value || "[]");
            return Array.isArray(v) ? v.map(normScene) : [];
        } catch (e) {
            return [];
        }
    }

    function writeScenes() {
        if (scenesWidget) scenesWidget.value = JSON.stringify(state.values);
    }

    function currentCount() {
        const v = frameWidget ? frameWidget.value : "auto";
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? n : 0; // auto -> 0
    }

    function contentHeight() {
        const n = currentCount();
        if (n <= 0) return 0;
        return SCENES_HEADER_H + n * SCENE_ROW_H;
    }

    /*
     * Node boyutunu KÜÇÜLTMEDEN gerekli yüksekliğe yükseltir. Kullanıcının elle
     * genişlettiği/uzattığı boyut korunur; sadece sahne sayısı artıp içerik
     * sığmıyorsa yükseklik büyütülür. Genişlik en az MIN_NODE_WIDTH olur.
     */
    function growToFit() {
        const needed = node.computeSize();
        const cur = node.size || [0, 0];
        const w = Math.max(cur[0], needed[0], MIN_NODE_WIDTH);
        const h = Math.max(cur[1], needed[1]);
        if (w !== cur[0] || h !== cur[1]) {
            node.setSize([w, h]);
        }
        node.setDirtyCanvas(true, true);
    }

    function render() {
        root.innerHTML = "";
        const n = currentCount();

        // auto modunda sahne kutusu yok; user_input görünür kalır.
        if (n <= 0) {
            if (userInputWidget) userInputWidget.hidden = false;
            growToFit();
            return;
        }

        // N sahne modunda user_input gizlenir (sahneler onun yerine geçer).
        if (userInputWidget) userInputWidget.hidden = true;

        // values dizisini N'e ayarla; her eleman {text,type} objesi olmalı.
        for (let k = 0; k < state.values.length; k++) {
            state.values[k] = normScene(state.values[k]);
        }
        while (state.values.length < n) state.values.push({ text: "", type: "" });
        if (state.values.length > n) state.values.length = n;

        const header = document.createElement("div");
        header.style.cssText =
            "color:#7a7a7a;font-size:11px;letter-spacing:0.3px;padding-bottom:2px;";
        header.textContent = `${n} scenes · write the direction, pick the type (empty = auto)`;
        root.appendChild(header);

        for (let i = 0; i < n; i++) {
            const row = document.createElement("div");
            row.style.cssText = "display:flex;flex-direction:column;gap:5px;width:100%;box-sizing:border-box;";

            const label = document.createElement("span");
            label.textContent = `Scene ${i + 1}`;
            label.style.cssText =
                "font-size:11px;color:#9ab;font-weight:600;letter-spacing:0.2px;";

            const ta = document.createElement("textarea");
            ta.value = state.values[i].text || "";
            ta.placeholder = `Scene ${i + 1} direction...`;
            ta.rows = 2;
            ta.style.cssText =
                "width:100%;box-sizing:border-box;resize:vertical;min-height:44px;" +
                "background:#181818;color:#eee;border:1px solid #3a3a3a;border-radius:8px;" +
                "padding:7px 9px;font-size:12px;line-height:1.45;font-family:inherit;outline:none;";
            ta.addEventListener("focus", () => (ta.style.borderColor = "#5a7da0"));
            ta.addEventListener("blur", () => (ta.style.borderColor = "#3a3a3a"));
            ta.addEventListener("input", () => {
                state.values[i].text = ta.value;
                writeScenes();
            });
            // textarea içindeyken canvas'ın node'u sürüklemesini engelle.
            ta.addEventListener("pointerdown", (e) => e.stopPropagation());

            // ---- tür seçimi (text_to_image / image_to_image) ----
            const sel = document.createElement("select");
            sel.style.cssText =
                "width:100%;box-sizing:border-box;background:#181818;color:#ccc;" +
                "border:1px solid #3a3a3a;border-radius:8px;padding:4px 8px;font-size:11px;" +
                "cursor:pointer;outline:none;";
            const opts = [
                { value: "", label: i === 0 ? "Auto (text_to_image)" : "Auto (image_to_image)" },
                { value: "text_to_image", label: "text_to_image" },
                { value: "image_to_image", label: "image_to_image" },
            ];
            for (const o of opts) {
                const opt = document.createElement("option");
                opt.value = o.value;
                opt.textContent = o.label;
                sel.appendChild(opt);
            }
            sel.value = state.values[i].type || "";
            sel.addEventListener("change", () => {
                state.values[i].type = sel.value;
                writeScenes();
            });
            sel.addEventListener("pointerdown", (e) => e.stopPropagation());

            row.appendChild(label);
            row.appendChild(ta);
            row.appendChild(sel);
            root.appendChild(row);
        }

        writeScenes();
        growToFit();
    }

    state.reload = function () {
        const saved = readScenes();
        if (saved.length) state.values = saved.slice();
        render();
    };

    // frame_count değişince yeniden çiz (boyutu küçültmeden büyütür).
    if (frameWidget) {
        const origCb = frameWidget.callback;
        frameWidget.callback = function () {
            const r = origCb ? origCb.apply(this, arguments) : undefined;
            render();
            return r;
        };
    }

    const dom = node.addDOMWidget("zfr_story_scenes", "div", root, {
        serialize: false,
        hideOnZoom: false,
    });
    dom.computeSize = (width) => [width, contentHeight()];
    dom.getHeight = () => contentHeight();

    state.reload();
}

/*
 * ZFRNodes — Reference Image Loader (Path) carousel.
 *
 * "Select folder" butonu /zfr/browse-folder ile sunucuda native klasör seçer.
 * Seçilen klasördeki görseller /zfr/list-folder ile alınır ve bir carousel'de
 * gösterilir: otomatik kayar (slider), sol/sağ ok ile gezinilir, her görselin
 * adı + çözünürlüğü yazılır, tıklayınca büyür, yeni sekmede açılabilir.
 * Görsel verisi /zfr/view-file?path=<folder>&name=<file> ile sunulur.
 */
const RILP_NODE_NAME = "Reference Image Loader (Path)";

app.registerExtension({
    name: "ZFRNodes.ReferenceImageLoaderPath",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== RILP_NODE_NAME) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupPathLoaderUI(this);
            return r;
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const res = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => { if (this._zfrPathLoader) this._zfrPathLoader.reload(); });
            return res;
        };
    },
});

function setupPathLoaderUI(node) {
    // Gizli folder_path widget'ı (Python ile paylaşılır).
    const pathWidget = node.widgets?.find((w) => w.name === "folder_path");
    if (pathWidget) {
        pathWidget.type = "hidden";
        pathWidget.computeSize = () => [0, 0];
        pathWidget.draw = () => {};
        pathWidget.hidden = true;
    }

    const state = { node, pathWidget, items: [], folder: "", idx: 0, timer: null };
    node._zfrPathLoader = state;

    const fileURL = (name) =>
        api.apiURL(`/zfr/view-file?path=${encodeURIComponent(state.folder)}&name=${encodeURIComponent(name)}&t=${Date.now()}`);

    // ---- DOM ----
    const root = document.createElement("div");
    root.style.cssText =
        "display:flex;flex-direction:column;gap:8px;width:100%;height:100%;box-sizing:border-box;" +
        "padding:2px;font-size:12px;color:#ddd;overflow:hidden;";

    const topBar = document.createElement("div");
    topBar.style.cssText = "display:flex;gap:6px;align-items:center;flex:0 0 auto;";

    // Path girişi (yapıştır + Load) + sayaç.
    const pathInput = document.createElement("input");
    pathInput.type = "text";
    pathInput.placeholder = "Paste folder path here…";
    pathInput.style.cssText =
        "flex:1 1 auto;min-width:0;background:#181818;color:#eee;border:1px solid #3a3a3a;" +
        "border-radius:6px;padding:5px 8px;font-size:11px;outline:none;box-sizing:border-box;";
    pathInput.addEventListener("pointerdown", (e) => e.stopPropagation());
    pathInput.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") loadFolder(pathInput.value.trim());
    });
    const loadBtn = document.createElement("button");
    loadBtn.textContent = "Load";
    loadBtn.style.cssText =
        "flex:0 0 auto;border:1px solid #555;border-radius:6px;background:#2a2a2a;color:#eee;" +
        "cursor:pointer;font-size:11px;padding:5px 10px;";
    loadBtn.onpointerdown = (e) => e.stopPropagation();
    loadBtn.onclick = () => loadFolder(pathInput.value.trim());

    const countBadge = document.createElement("span");
    countBadge.style.cssText = "flex:0 0 auto;font-size:11px;color:#888;min-width:48px;text-align:right;";

    topBar.appendChild(pathInput);
    topBar.appendChild(loadBtn);
    topBar.appendChild(countBadge);

    const pathLabel = document.createElement("div");
    pathLabel.style.cssText =
        "flex:0 0 auto;font-size:10px;color:#666;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";

    // pathRow artık topBar'da; ayrı satıra gerek yok.
    const pathRow = document.createElement("div");
    pathRow.style.cssText = "display:none;";

    // Carousel gövdesi.
    const stage = document.createElement("div");
    stage.style.cssText =
        "flex:1 1 auto;position:relative;display:flex;align-items:center;justify-content:center;" +
        "background:#151515;border:1px solid #333;border-radius:8px;overflow:hidden;min-height:160px;";

    const img = document.createElement("img");
    img.style.cssText =
        "max-width:100%;max-height:100%;object-fit:contain;display:block;cursor:zoom-in;";
    img.title = "Click to enlarge";
    stage.appendChild(img);

    function navBtn(txt, side) {
        const b = document.createElement("button");
        b.textContent = txt;
        b.style.cssText =
            `position:absolute;${side}:6px;top:50%;transform:translateY(-50%);width:30px;height:30px;` +
            "border:none;border-radius:50%;background:rgba(0,0,0,0.5);color:#fff;cursor:pointer;" +
            "font-size:15px;display:flex;align-items:center;justify-content:center;z-index:2;";
        b.onpointerdown = (e) => e.stopPropagation();
        return b;
    }
    const prevBtn = navBtn("‹", "left");
    const nextBtn = navBtn("›", "right");
    stage.appendChild(prevBtn);
    stage.appendChild(nextBtn);

    const infoBar = document.createElement("div");
    infoBar.style.cssText =
        "flex:0 0 auto;display:flex;align-items:center;gap:8px;font-size:11px;color:#bbb;";
    const infoName = document.createElement("span");
    infoName.style.cssText = "flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
    const infoRes = document.createElement("span");
    infoRes.style.cssText = "flex:0 0 auto;color:#888;";
    const newTabBtn = document.createElement("button");
    newTabBtn.textContent = "↗ new tab";
    newTabBtn.style.cssText =
        "flex:0 0 auto;border:1px solid #444;border-radius:5px;background:#222;color:#9ab;" +
        "cursor:pointer;font-size:10px;padding:2px 6px;";
    newTabBtn.onpointerdown = (e) => e.stopPropagation();
    infoBar.appendChild(infoName);
    infoBar.appendChild(infoRes);
    infoBar.appendChild(newTabBtn);

    root.appendChild(topBar);
    root.appendChild(pathLabel);
    root.appendChild(pathRow);
    root.appendChild(stage);
    root.appendChild(infoBar);

    // ---- davranış ----
    function showCurrent() {
        const it = state.items[state.idx];
        if (!it) {
            img.removeAttribute("src");
            infoName.textContent = "(no images)";
            infoRes.textContent = "";
            countBadge.textContent = "0";
            return;
        }
        img.src = fileURL(it.name);
        infoName.textContent = it.name;
        infoRes.textContent = it.width ? `${it.width}×${it.height}` : "";
        countBadge.textContent = `${state.idx + 1}/${state.items.length}`;
    }

    function go(delta) {
        if (!state.items.length) return;
        state.idx = (state.idx + delta + state.items.length) % state.items.length;
        showCurrent();
    }
    prevBtn.onclick = () => { go(-1); restartAuto(); };
    nextBtn.onclick = () => { go(1); restartAuto(); };

    function restartAuto() {
        if (state.timer) clearInterval(state.timer);
        if (state.items.length > 1) {
            state.timer = setInterval(() => go(1), 3000);
        }
    }

    img.onclick = () => {
        const it = state.items[state.idx];
        if (!it) return;
        const ov = document.createElement("div");
        ov.style.cssText =
            "position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;" +
            "align-items:center;justify-content:center;cursor:zoom-out;";
        const big = document.createElement("img");
        big.src = fileURL(it.name);
        big.style.cssText = "max-width:92vw;max-height:92vh;object-fit:contain;";
        ov.appendChild(big);
        ov.onclick = () => ov.remove();
        document.body.appendChild(ov);
    };

    newTabBtn.onclick = () => {
        const it = state.items[state.idx];
        if (it) window.open(fileURL(it.name), "_blank");
    };

    async function loadFolder(folder) {
        state.folder = folder || "";
        if (pathWidget) pathWidget.value = state.folder;
        if (pathInput) pathInput.value = state.folder;
        pathLabel.style.color = "#666";
        pathLabel.textContent = state.folder || "(no folder selected)";
        if (!state.folder) { state.items = []; state.idx = 0; showCurrent(); return; }
        try {
            const resp = await api.fetchApi(`/zfr/list-folder?path=${encodeURIComponent(state.folder)}`);
            const data = await resp.json();
            state.items = Array.isArray(data.images) ? data.images : [];
        } catch (e) {
            state.items = [];
        }
        state.idx = 0;
        showCurrent();
        restartAuto();
        node.setDirtyCanvas(true, true);
    }


    state.reload = function () {
        const saved = pathWidget ? pathWidget.value : "";
        loadFolder(saved || "");
    };

    const dom = node.addDOMWidget("zfr_path_carousel", "div", root, {
        serialize: false, hideOnZoom: false,
    });
    const H = () => 290;
    dom.computeSize = (w) => [w, H()];
    dom.getHeight = () => H();

    // SADECE ilk oluşturmada (kayıtlı boyut yoksa) bir kez geniş başlat.
    // Workflow yüklemede / sonraki güncellemelerde kullanıcının boyutuna dokunma.
    if (!node._zfrSizedOnce) {
        node._zfrSizedOnce = true;
        requestAnimationFrame(() => {
            if (node.size && node.size[0] < 360) {
                node.setSize([360, node.size[1]]);
                node.setDirtyCanvas(true, true);
            }
        });
    }

    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        if (state.timer) clearInterval(state.timer);
        return onRemoved ? onRemoved.apply(this, arguments) : undefined;
    };

    state.reload();
}

/*
 * ZFRNodes — Caption Generator UI.
 *
 * folder_path için Reference Image Loader (Path) ile aynı carousel'i gösterir
 * (klasördeki görseller, otomatik kayma, büyütme). Ayrıca Ollama model listesini
 * /zfr/ollama-models?url=<base_url> ile çeken bir "Refresh models" butonu ekler;
 * gelen modeller 'model' combo widget'ına doldurulur.
 */
const CAP_NODE_NAME = "Caption Generator";

app.registerExtension({
    name: "ZFRNodes.CaptionGenerator",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== CAP_NODE_NAME) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupCaptionUI(this);
            return r;
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const res = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => { if (this._zfrCaption) this._zfrCaption.reload(); });
            return res;
        };
    },
});

// Provider -> varsayılan base_url (Python PROVIDER_INFO ile aynı tutulmalı).
const CAP_PROVIDER_BASEURL = {
    ollama: "http://127.0.0.1:11434",
    openai: "https://api.openai.com/v1",
    deepseek: "https://api.deepseek.com/v1",
    google: "https://generativelanguage.googleapis.com/v1beta/openai",
    openrouter: "https://openrouter.ai/api/v1",
    anthropic: "https://api.anthropic.com",
};

function setupCaptionUI(node) {
    const folderWidget = node.widgets?.find((w) => w.name === "folder_path");
    const modelWidget = node.widgets?.find((w) => w.name === "model");
    const baseUrlWidget = node.widgets?.find((w) => w.name === "base_url");
    const providerWidget = node.widgets?.find((w) => w.name === "provider");
    const apiKeyWidget = node.widgets?.find((w) => w.name === "api_key");

    // folder_path widget'ını gizle — path, carousel'in paste alanından gelir.
    if (folderWidget) {
        folderWidget.type = "hidden";
        folderWidget.computeSize = () => [0, 0];
        folderWidget.draw = () => {};
        folderWidget.hidden = true;
    }

    const state = { node, folderWidget, items: [], folder: "", idx: 0, timer: null };
    node._zfrCaption = state;

    // Bir widget'ı göster/gizle (ComfyUI'nin hidden tipiyle).
    function setWidgetHidden(w, hide) {
        if (!w) return;
        if (hide) {
            if (w._origType === undefined) w._origType = w.type;
            w.type = "hidden";
            w.computeSize = () => [0, 0];
            w.hidden = true;
        } else {
            if (w._origType !== undefined) w.type = w._origType;
            delete w.computeSize;
            w.hidden = false;
        }
    }

    // provider değişince: base_url'i otomatik doldur, api_key'i ollama'da gizle.
    function applyProvider(prov, forceUrl) {
        const def = CAP_PROVIDER_BASEURL[prov];
        if (baseUrlWidget && def) {
            // Sadece kullanıcı manuel değiştirmediyse / boşsa / başka bir provider'ın
            // varsayılanıysa güncelle (kullanıcının özel URL'sini ezme).
            const cur = baseUrlWidget.value || "";
            const isDefault = Object.values(CAP_PROVIDER_BASEURL).includes(cur) || cur === "";
            if (forceUrl || isDefault) baseUrlWidget.value = def;
        }
        const isOllama = prov === "ollama";
        setWidgetHidden(apiKeyWidget, isOllama);   // ollama'da api_key gizli
        refreshBtn.style.display = isOllama ? "" : "none"; // refresh sadece ollama
        // Boyutu zorla değiştirme — kullanıcının ayarladığı genişlik/yükseklik kalsın.
        node.setDirtyCanvas(true, true);
    }

    const fileURL = (name) =>
        api.apiURL(`/zfr/view-file?path=${encodeURIComponent(state.folder)}&name=${encodeURIComponent(name)}&t=${Date.now()}`);

    // ---- model refresh ----
    async function refreshModels() {
        const url = (baseUrlWidget && baseUrlWidget.value) || "http://127.0.0.1:11434";
        refreshBtn.textContent = "…";
        refreshBtn.disabled = true;
        try {
            const resp = await api.fetchApi(`/zfr/ollama-models?url=${encodeURIComponent(url)}`);
            const data = await resp.json();
            const models = Array.isArray(data.models) ? data.models : [];
            if (modelWidget) {
                modelWidget.options = modelWidget.options || {};
                modelWidget.options.values = models;
                if (models.length && !models.includes(modelWidget.value)) {
                    modelWidget.value = models[0];
                }
            }
            modelInfo.textContent = models.length ? `${models.length} models` : (data.error ? "Ollama error" : "no models");
            node.setDirtyCanvas(true, true);
        } catch (e) {
            modelInfo.textContent = "fetch failed";
        }
        refreshBtn.textContent = "⟳ Refresh models";
        refreshBtn.disabled = false;
    }

    // ---- DOM ----
    const root = document.createElement("div");
    root.style.cssText =
        "display:flex;flex-direction:column;gap:8px;width:100%;height:100%;box-sizing:border-box;" +
        "padding:2px;font-size:12px;color:#ddd;overflow:hidden;";

    // Model refresh satırı.
    const modelRow = document.createElement("div");
    modelRow.style.cssText = "display:flex;gap:6px;align-items:center;flex:0 0 auto;";
    const refreshBtn = document.createElement("button");
    refreshBtn.textContent = "⟳ Refresh models";
    refreshBtn.style.cssText =
        "flex:0 0 auto;border:1px solid #555;border-radius:6px;background:#2a2a2a;color:#eee;" +
        "cursor:pointer;font-size:11px;padding:5px 10px;";
    refreshBtn.onpointerdown = (e) => e.stopPropagation();
    refreshBtn.onclick = refreshModels;
    const modelInfo = document.createElement("span");
    modelInfo.style.cssText = "flex:1 1 auto;font-size:10px;color:#888;text-align:right;";
    modelRow.appendChild(refreshBtn);
    modelRow.appendChild(modelInfo);

    // Path girişi.
    const topBar = document.createElement("div");
    topBar.style.cssText = "display:flex;gap:6px;align-items:center;flex:0 0 auto;";
    const pathInput = document.createElement("input");
    pathInput.type = "text";
    pathInput.placeholder = "Paste image folder path here…";
    pathInput.style.cssText =
        "flex:1 1 auto;min-width:0;background:#181818;color:#eee;border:1px solid #3a3a3a;" +
        "border-radius:6px;padding:5px 8px;font-size:11px;outline:none;box-sizing:border-box;";
    pathInput.addEventListener("pointerdown", (e) => e.stopPropagation());
    pathInput.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") loadFolder(pathInput.value.trim());
    });
    const loadBtn = document.createElement("button");
    loadBtn.textContent = "Load";
    loadBtn.style.cssText =
        "flex:0 0 auto;border:1px solid #555;border-radius:6px;background:#2a2a2a;color:#eee;" +
        "cursor:pointer;font-size:11px;padding:5px 10px;";
    loadBtn.onpointerdown = (e) => e.stopPropagation();
    loadBtn.onclick = () => loadFolder(pathInput.value.trim());
    const countBadge = document.createElement("span");
    countBadge.style.cssText = "flex:0 0 auto;font-size:11px;color:#888;min-width:46px;text-align:right;";
    topBar.appendChild(pathInput);
    topBar.appendChild(loadBtn);
    topBar.appendChild(countBadge);

    // Carousel.
    const stage = document.createElement("div");
    stage.style.cssText =
        "flex:1 1 auto;position:relative;display:flex;align-items:center;justify-content:center;" +
        "background:#151515;border:1px solid #333;border-radius:8px;overflow:hidden;min-height:150px;";
    const img = document.createElement("img");
    img.style.cssText = "max-width:100%;max-height:100%;object-fit:contain;display:block;cursor:zoom-in;";
    stage.appendChild(img);
    function navBtn(txt, side) {
        const b = document.createElement("button");
        b.textContent = txt;
        b.style.cssText =
            `position:absolute;${side}:6px;top:50%;transform:translateY(-50%);width:28px;height:28px;` +
            "border:none;border-radius:50%;background:rgba(0,0,0,0.5);color:#fff;cursor:pointer;" +
            "font-size:14px;display:flex;align-items:center;justify-content:center;z-index:2;";
        b.onpointerdown = (e) => e.stopPropagation();
        return b;
    }
    const prevBtn = navBtn("‹", "left");
    const nextBtn = navBtn("›", "right");
    stage.appendChild(prevBtn);
    stage.appendChild(nextBtn);

    const infoBar = document.createElement("div");
    infoBar.style.cssText = "flex:0 0 auto;display:flex;align-items:center;gap:8px;font-size:11px;color:#bbb;";
    const infoName = document.createElement("span");
    infoName.style.cssText = "flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
    const infoRes = document.createElement("span");
    infoRes.style.cssText = "flex:0 0 auto;color:#888;";
    infoBar.appendChild(infoName);
    infoBar.appendChild(infoRes);

    root.appendChild(modelRow);
    root.appendChild(topBar);
    root.appendChild(stage);
    root.appendChild(infoBar);

    // ---- carousel davranışı ----
    function showCurrent() {
        const it = state.items[state.idx];
        if (!it) {
            img.removeAttribute("src");
            infoName.textContent = "(no images)";
            infoRes.textContent = "";
            countBadge.textContent = "0";
            return;
        }
        img.src = fileURL(it.name);
        infoName.textContent = it.name;
        infoRes.textContent = it.width ? `${it.width}×${it.height}` : "";
        countBadge.textContent = `${state.idx + 1}/${state.items.length}`;
    }
    function go(d) {
        if (!state.items.length) return;
        state.idx = (state.idx + d + state.items.length) % state.items.length;
        showCurrent();
    }
    prevBtn.onclick = () => { go(-1); restartAuto(); };
    nextBtn.onclick = () => { go(1); restartAuto(); };
    function restartAuto() {
        if (state.timer) clearInterval(state.timer);
        if (state.items.length > 1) state.timer = setInterval(() => go(1), 3000);
    }
    img.onclick = () => {
        const it = state.items[state.idx];
        if (!it) return;
        const ov = document.createElement("div");
        ov.style.cssText =
            "position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;" +
            "align-items:center;justify-content:center;cursor:zoom-out;";
        const big = document.createElement("img");
        big.src = fileURL(it.name);
        big.style.cssText = "max-width:92vw;max-height:92vh;object-fit:contain;";
        ov.appendChild(big);
        ov.onclick = () => ov.remove();
        document.body.appendChild(ov);
    };

    async function loadFolder(folder) {
        state.folder = folder || "";
        if (folderWidget) folderWidget.value = state.folder;
        if (pathInput) pathInput.value = state.folder;
        if (!state.folder) { state.items = []; state.idx = 0; showCurrent(); return; }
        try {
            const resp = await api.fetchApi(`/zfr/list-folder?path=${encodeURIComponent(state.folder)}`);
            const data = await resp.json();
            state.items = Array.isArray(data.images) ? data.images : [];
        } catch (e) {
            state.items = [];
        }
        state.idx = 0;
        showCurrent();
        restartAuto();
        node.setDirtyCanvas(true, true);
    }

    state.reload = function () {
        const saved = folderWidget ? folderWidget.value : "";
        loadFolder(saved || "");
        if (providerWidget) applyProvider(providerWidget.value, false);
    };

    // provider değişimini dinle (base_url otomatik + api_key görünürlüğü).
    if (providerWidget) {
        const origCb = providerWidget.callback;
        providerWidget.callback = function () {
            const r = origCb ? origCb.apply(this, arguments) : undefined;
            applyProvider(providerWidget.value, true);
            return r;
        };
    }

    const dom = node.addDOMWidget("zfr_caption_ui", "div", root, {
        serialize: false, hideOnZoom: false,
    });
    const H = () => 290;
    dom.computeSize = (w) => [w, H()];
    dom.getHeight = () => H();

    // SADECE ilk oluşturmada bir kez geniş başlat. Sonraki güncellemelerde /
    // workflow yüklemede kullanıcının ayarladığı boyuta dokunma.
    if (!node._zfrSizedOnce) {
        node._zfrSizedOnce = true;
        requestAnimationFrame(() => {
            if (node.size && node.size[0] < 360) {
                node.setSize([360, node.size[1]]);
                node.setDirtyCanvas(true, true);
            }
        });
    }

    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        if (state.timer) clearInterval(state.timer);
        return onRemoved ? onRemoved.apply(this, arguments) : undefined;
    };

    state.reload();
}

/*
 * ZFRNodes — Inpaint Studio arayüzü.
 *
 * Bu node'un çok sayıda ayarı var; düz liste yerine üstte SABİT bir görsel
 * bölmesi (upload + önizleme + MaskEditor), altında sekmeli (tab) ayar alanı
 * gösterilir. Her sekme yalnızca ilgili widget'ları görünür kılar.
 *
 * Görsel bölmesi neden native "image_upload" widget'ı DEĞİL, kendi DOM UI'ımız?
 *   Bu ComfyUI frontend sürümünde image_upload widget'ı bir Vue combo olarak
 *   çiziliyor; upload butonu ve önizleme her ortamda güvenilir görünmüyordu.
 *   Bunun yerine reference_image_loader'daki gibi kendi upload/önizleme/paste
 *   UI'ımızı kuruyoruz. Native "image" string widget'ı GİZLENİR ama node'da
 *   tutulur:
 *     - Python (generate) o widget'ın değerini (dosya adı) okur.
 *     - ComfyUI MaskEditor mask'i geri yazarken "image" adlı widget'ı arar ve
 *       değerini clipspace görseliyle günceller — o yüzden adı korunmalı.
 *   Önizleme aynı zamanda node.imgs'i doldurur; böylece:
 *     - isImageNode(node) true olur -> sağ tık menüsünde "Open in MaskEditor"
 *       çıkar,
 *     - önizleme node üzerinde de görünür.
 *
 *   - Sekmeler: Model · Inpaint · Generation · Output
 *   - Aktif sekme node'a kaydedilir (properties) — workflow yüklenince geri gelir.
 */
const IS_NODE_NAME = "Inpaint Studio (ZFRNodes)";

// Sekme -> o sekmede gösterilecek widget adları (sırasıyla).
const IS_TABS = [
    {
        id: "model", label: "Model",
        widgets: ["unet_name", "vae_name", "clip_name", "clip_type",
                  "lora_name", "lora_strength", "trigger_words", "use_references"],
    },
    {
        id: "inpaint", label: "Inpaint",
        widgets: ["denoise", "grow_mask", "feather_mask", "noise_mask",
                  "differential_diffusion", "composite_back"],
    },
    {
        id: "generation", label: "Generation",
        widgets: ["steps", "cfg", "guidance", "sampler_name", "scheduler",
                  "seed", "seed_mode"],
    },
    {
        id: "output", label: "Output",
        widgets: ["save_to_disk", "output_subdir", "filename_prefix"],
    },
];

// Sekmelerden bağımsız, her zaman görünen native widget. "image" native combo
// GİZLENİR (kendi UI'mız yönetir) — burada yalnızca prompt her sekmede kalır.
const IS_ALWAYS_VISIBLE = ["prompt"];

const IS_TABS_ENABLED = true;
app.registerExtension({
    name: "ZFRNodes.InpaintStudio",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!IS_TABS_ENABLED) return;
        if (nodeData.name !== IS_NODE_NAME) return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupInpaintStudioTabs(this);
            return r;
        };
    },
});

function setupInpaintStudioTabs(node) {
    const state = {
        node,
        active: "model",
        // Gizlenen native widget'ların orijinal ayarları (geri koymak için).
        origTypes: new Map(),
    };
    node._zfrInpaintTabs = state;

    // --- native "image" string widget'ı: gizle ama tut (Python + MaskEditor okur) ---
    const imageWidget = (node.widgets || []).find((w) => w.name === "image");

    // Bir widget'ı gizle/göster.
    function setHidden(w, hide) {
        if (!w) return;
        if (hide) {
            if (!state.origTypes.has(w)) {
                state.origTypes.set(w, {
                    type: w.type,
                    computeSize: w.computeSize,
                    getHeight: w.getHeight,
                });
            }
            w.type = "hidden";
            w.hidden = true;
            w.computeSize = () => [0, -4];
            w.getHeight = () => 0;
        } else {
            const orig = state.origTypes.get(w);
            if (orig) {
                w.type = orig.type;
                if (orig.computeSize) w.computeSize = orig.computeSize;
                else delete w.computeSize;
                if (orig.getHeight) w.getHeight = orig.getHeight;
                else delete w.getHeight;
                state.origTypes.delete(w);
            }
            w.hidden = false;
        }
        if (w.inputEl) {
            w.inputEl.style.display = hide ? "none" : "";
        }
    }

    if (imageWidget) setHidden(imageWidget, true);

    function applyVisibility(resize = true) {
        const tab = IS_TABS.find((t) => t.id === state.active) || IS_TABS[0];
        const visibleSet = new Set([...IS_ALWAYS_VISIBLE, ...tab.widgets]);
        for (const w of node.widgets || []) {
            if (w === tabWidget || w === imageBoxWidget) continue;
            if (w === imageWidget) continue;
            setHidden(w, !visibleSet.has(w.name));
        }
        renderTabBar();
        if (!resize) return;

        requestAnimationFrame(() => {
            const needed = node.computeSize();
            const curW = node.size ? node.size[0] : needed[0];
            const curH = node.size ? node.size[1] : needed[1];
            node.setSize([Math.max(curW, needed[0]), Math.max(curH, needed[1])]);
            node.setDirtyCanvas(true, true);
        });
    }

    function setActive(id) {
        state.active = id;
        node.properties = node.properties || {};
        node.properties._zfrInpaintTab = id;
        applyVisibility();
    }

    // ================= görsel bölmesi (upload + önizleme + MaskEditor) =================

    const imgRoot = document.createElement("div");
    imgRoot.style.cssText =
        "width:100%;box-sizing:border-box;display:flex;flex-direction:column;gap:6px;" +
        "padding:2px 0;";

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:6px;width:100%;box-sizing:border-box;";

    const uploadBtn = document.createElement("button");
    uploadBtn.textContent = "⬆ Load Image";
    uploadBtn.title = "Resim seç — ya da buraya sürükle-bırak, ya da node seçiliyken Ctrl+V";
    uploadBtn.style.cssText =
        "flex:1 1 0;min-width:0;height:28px;border-radius:6px;cursor:pointer;font-size:12px;" +
        "font-weight:600;box-sizing:border-box;background:#2f5c8a;color:#fff;border:1px solid #3d72a8;" +
        "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .12s;";
    uploadBtn.onmouseenter = () => (uploadBtn.style.background = "#3a6ea3");
    uploadBtn.onmouseleave = () => (uploadBtn.style.background = "#2f5c8a");

    const maskBtn = document.createElement("button");
    maskBtn.textContent = "🖌 Mask Editor";
    maskBtn.title = "Yüklenen görselde değiştirmek istediğin alanı fırçayla boya";
    maskBtn.style.cssText =
        "flex:1 1 0;min-width:0;height:28px;border-radius:6px;cursor:pointer;font-size:12px;" +
        "font-weight:600;box-sizing:border-box;background:#2a2a2a;color:#ddd;border:1px solid #3a3a3a;" +
        "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .12s;";
    maskBtn.onmouseenter = () => (maskBtn.style.background = "#383838");
    maskBtn.onmouseleave = () => (maskBtn.style.background = "#2a2a2a");

    btnRow.appendChild(uploadBtn);
    btnRow.appendChild(maskBtn);

    const previewBox = document.createElement("div");
    previewBox.style.cssText =
        "width:100%;box-sizing:border-box;min-height:150px;border-radius:8px;" +
        "border:1px dashed #3a3a3a;background:#151515;display:flex;align-items:center;" +
        "justify-content:center;overflow:hidden;position:relative;";

    const previewImg = document.createElement("img");
    previewImg.style.cssText =
        "max-width:100%;max-height:100%;object-fit:contain;display:none;";
    const previewHint = document.createElement("div");
    previewHint.textContent = "Resim yükle · sürükle-bırak · Ctrl+V yapıştır";
    previewHint.style.cssText =
        "color:#666;font-size:11px;text-align:center;padding:12px;pointer-events:none;";
    previewBox.appendChild(previewImg);
    previewBox.appendChild(previewHint);

    imgRoot.appendChild(btnRow);
    imgRoot.appendChild(previewBox);

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/*";
    fileInput.style.display = "none";
    imgRoot.appendChild(fileInput);

    // ---- önizleme + node.imgs senkronu ----
    // previewUrl: annotated path'ten /view URL'si oluşturur.
    function previewUrl(name) {
        let filename = name;
        let type = "input";
        let subfolder = "";
        const m = /^(.*)\s*\[(\w+)\]\s*$/.exec(name);
        if (m) {
            filename = m[1].trim();
            type = m[2];
        }
        const slash = filename.lastIndexOf("/");
        if (slash >= 0) {
            subfolder = filename.slice(0, slash);
            filename = filename.slice(slash + 1);
        }
        const params = new URLSearchParams({ filename, type, subfolder });
        return api.apiURL(`/view?${params.toString()}&t=${Date.now()}`);
    }

    // syncFromWidget: widget'taki değeri oku, önizlemeyi dene, başarısız olursa yeniden dene.
    let _syncSeq = 0;
    const MAX_TRIES = 20; // artırıldı

    function syncFromWidget() {
        const seq = ++_syncSeq;
        const name = imageWidget && imageWidget.value;
        if (!name) {
            previewImg.style.display = "none";
            previewHint.style.display = "";
            node.imgs = undefined;
            node.setDirtyCanvas(true, true);
            return;
        }

        const tryLoad = (attempt) => {
            if (seq !== _syncSeq) return;
            const url = previewUrl(name);

            previewImg.onload = () => {
                if (seq !== _syncSeq) return;
                previewImg.style.display = "";
                previewHint.style.display = "none";
                node.imgs = [previewImg];
                node.imageIndex = null;
                node.previewMediaType = "image";
                node.setDirtyCanvas(true, true);
            };

            previewImg.onerror = () => {
                if (seq !== _syncSeq) return;
                if (attempt < MAX_TRIES) {
                    // Kademeli bekleme: 200ms, 400ms, 600ms, ...
                    setTimeout(() => tryLoad(attempt + 1), 200 * attempt);
                } else {
                    console.warn("[ZFRNodes] Inpaint Studio önizleme yüklenemedi:", name);
                    previewImg.style.display = "none";
                    previewHint.style.display = "";
                    node.imgs = undefined;
                    node.setDirtyCanvas(true, true);
                }
            };

            previewImg.src = url;
        };

        tryLoad(1);
    }

    state.syncFromWidget = syncFromWidget;
    node._zfrInpaint = state;

    // Native alt-önizlemeyi bastır.
    const origOnDrawBackground = node.onDrawBackground;
    node.onDrawBackground = function (ctx, canvas) {
        const savedImgs = this.imgs;
        this.imgs = undefined;
        let r;
        try {
            r = origOnDrawBackground ? origOnDrawBackground.apply(this, arguments) : undefined;
        } finally {
            this.imgs = savedImgs;
        }
        return r;
    };

    // imageWidget değer değişikliğini yakala.
    //
    // defineProperty/callback/change-event denemelerinin HİÇBİRİ güvenilir
    // değil: MaskEditor "Save" sonrası ComfyUI widget değerini bazı sürümlerde
    // widgets_values dizisi üzerinden ya da widget objesini komple değiştirerek
    // günceller — bu durumda getter/setter veya callback override'ı hiç
    // tetiklenmez, sessizce atlanır (hata da vermez). Bu yüzden asıl güvenlik
    // ağı POLLING: ComfyUI'nin nasıl güncellediğinden tamamen bağımsız çalışır.
    if (imageWidget) {
        let _lastPolled = imageWidget.value;
        state._pollIntervalId = setInterval(() => {
            if (imageWidget.value !== _lastPolled) {
                _lastPolled = imageWidget.value;
                syncFromWidget();
            }
        }, 300);

        // defineProperty de dene (destekleniyorsa anında tepki için faydalı,
        // ama artık TEK dayanak noktası değil).
        try {
            let _val = imageWidget.value;
            Object.defineProperty(imageWidget, "value", {
                configurable: true,
                enumerable: true,
                get() { return _val; },
                set(v) {
                    _val = v;
                    _lastPolled = v;
                    requestAnimationFrame(syncFromWidget);
                },
            });
        } catch (err) {
            // yoksay — polling zaten yakalayacak.
        }
    }

    // ---- upload ----
    async function uploadImageFile(file) {
        const body = new FormData();
        body.append("image", file);
        body.append("type", "input");
        body.append("overwrite", "false");
        const resp = await api.fetchApi("/upload/image", { method: "POST", body });
        if (resp.status !== 200) throw new Error(`upload failed (${resp.status})`);
        return await resp.json();
    }

    async function handleFiles(files) {
        const list = Array.from(files || []).filter(
            (f) => f && (f.type ? f.type.startsWith("image/") : true)
        );
        if (!list.length) return;
        try {
            const data = await uploadImageFile(list[0]);
            let val = data.name;
            if (data.subfolder) val = `${data.subfolder}/${data.name}`;
            if (imageWidget) {
                const opts = imageWidget.options;
                if (opts && Array.isArray(opts.values) && !opts.values.includes(val)) {
                    opts.values.push(val);
                }
                imageWidget.value = val;
            } else {
                syncFromWidget();
            }
        } catch (err) {
            console.error("[ZFRNodes] Inpaint Studio image upload failed:", err);
        }
    }

    uploadBtn.onclick = (e) => { e.stopPropagation(); fileInput.click(); };
    fileInput.onchange = () => {
        if (fileInput.files && fileInput.files.length) handleFiles(fileInput.files);
        fileInput.value = "";
    };

    // ---- Mask Editor aç ----
    function openMaskEditor() {
        try {
            const cmd = app.extensionManager && app.extensionManager.command;
            if (cmd && typeof cmd.execute === "function") {
                app.canvas.selectNode(node);
                cmd.execute("Comfy.MaskEditor.OpenMaskEditor");
                return true;
            }
        } catch (err) {
            console.warn("[ZFRNodes] MaskEditor komutu başarısız, fallback deneniyor:", err);
        }
        try {
            const ComfyApp =
                (window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.ComfyApp) ||
                window.ComfyApp;
            if (ComfyApp && typeof ComfyApp.open_maskeditor === "function") {
                ComfyApp.clipspace_return_node = node;
                if (typeof ComfyApp.copyToClipspace === "function") {
                    ComfyApp.copyToClipspace(node);
                }
                ComfyApp.open_maskeditor();
                return true;
            }
        } catch (err) {
            console.error("[ZFRNodes] MaskEditor açılamadı:", err);
        }
        return false;
    }

    maskBtn.onclick = (e) => {
        e.stopPropagation();
        if (!node.imgs || !node.imgs.length) {
            previewBox.style.borderColor = "#a05a5a";
            setTimeout(() => (previewBox.style.borderColor = "#3a3a3a"), 800);
            console.warn("[ZFRNodes] Önce bir görsel yükle.");
            return;
        }
        if (!openMaskEditor()) {
            console.warn("[ZFRNodes] MaskEditor doğrudan açılamadı; " +
                "node'a sağ tıklayıp 'Open in MaskEditor' seçebilirsin.");
        }
    };

    // ---- sürükle-bırak ----
    imgRoot.addEventListener("dragover", (e) => {
        if (!e.dataTransfer) return;
        const hasFiles = Array.from(e.dataTransfer.items || [])
            .some((it) => it.kind === "file");
        if (!hasFiles) return;
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "copy";
        previewBox.style.borderColor = "#5a7da0";
    });
    imgRoot.addEventListener("dragleave", () => {
        previewBox.style.borderColor = "#3a3a3a";
    });
    imgRoot.addEventListener("drop", (e) => {
        if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
        e.preventDefault();
        e.stopPropagation();
        previewBox.style.borderColor = "#3a3a3a";
        handleFiles(e.dataTransfer.files);
    });

    // ---- yapıştır (Ctrl+V) ----
    function onPaste(e) {
        const selected = app.canvas && app.canvas.selected_nodes;
        if (!node.graph || !selected || !selected[node.id]) return;
        const items = (e.clipboardData || window.clipboardData)?.items;
        if (!items) return;
        const files = [];
        for (const it of items) {
            if (it.kind === "file" && it.type.startsWith("image/")) {
                const f = it.getAsFile();
                if (f) files.push(f);
            }
        }
        if (files.length) {
            e.preventDefault();
            e.stopPropagation();
            handleFiles(files);
        }
    }
    document.addEventListener("paste", onPaste, true);

    const onRemovedPaste = node.onRemoved;
    node.onRemoved = function () {
        document.removeEventListener("paste", onPaste, true);
        if (state._pollIntervalId) clearInterval(state._pollIntervalId);
        return onRemovedPaste ? onRemovedPaste.apply(this, arguments) : undefined;
    };

    // Görsel bölmesi DOM widget'ı
    const IMG_BOX_H = 200;
    const imageBoxWidget = node.addDOMWidget("zfr_inpaint_image", "div", imgRoot, {
        serialize: false,
        hideOnZoom: false,
    });
    imageBoxWidget.computeSize = (w) => [w, IMG_BOX_H];
    imageBoxWidget.getHeight = () => IMG_BOX_H;

    // ================= tab-bar =================

    const barWrap = document.createElement("div");
    barWrap.style.cssText = "width:100%;box-sizing:border-box;padding:4px 0;";
    const bar = document.createElement("div");
    bar.style.cssText =
        "display:flex;gap:4px;width:100%;box-sizing:border-box;align-items:stretch;margin-top:5px";
    barWrap.appendChild(bar);

    function renderTabBar() {
        bar.innerHTML = "";
        for (const t of IS_TABS) {
            const isActive = t.id === state.active;
            const btn = document.createElement("button");
            btn.textContent = t.label;
            btn.style.cssText =
                "flex:1 1 0;min-width:0;height:24px;padding:0 4px;border-radius:3px;cursor:pointer;" +
                "font-size:11px;font-weight:600;box-sizing:border-box;white-space:nowrap;" +
                "overflow:hidden;text-overflow:ellipsis;transition:background .12s;" +
                (isActive
                    ? "background:#5a7da0;color:#fff;border:1px solid #6b8fb5;"
                    : "background:#262626;color:#bbb;border:1px solid #3a3a3a;");
            btn.onpointerdown = (e) => e.stopPropagation();
            btn.onclick = (e) => { e.stopPropagation(); setActive(t.id); };
            if (!isActive) {
                btn.onmouseenter = () => (btn.style.background = "#333");
                btn.onmouseleave = () => (btn.style.background = "#262626");
            }
            bar.appendChild(btn);
        }
    }

    const TAB_H = 65;
    const tabWidget = node.addDOMWidget("zfr_inpaint_tabs", "div", barWrap, {
        serialize: false,
        hideOnZoom: false,
    });
    tabWidget.computeSize = (w) => [w, TAB_H];
    tabWidget.getHeight = () => TAB_H;

    // ---- widget sırası ----
    (function orderWidgets() {
        const ws = node.widgets;
        if (!ws || !ws.length) return;
        const take = (predicate) => {
            const i = ws.findIndex(predicate);
            return i >= 0 ? ws.splice(i, 1)[0] : null;
        };
        const imgBox = take((w) => w === imageBoxWidget);
        const promptW = take((w) => w.name === "prompt");
        const tabsW = take((w) => w === tabWidget);
        let at = 0;
        for (const w of [imgBox, promptW, tabsW]) {
            if (w) ws.splice(at++, 0, w);
        }
    })();

    const PROMPT_H = 84;
    const promptWidget = (node.widgets || []).find((w) => w.name === "prompt");
    if (promptWidget) {
        if (promptWidget.inputEl) {
            promptWidget.inputEl.style.height = PROMPT_H + "px";
            promptWidget.inputEl.style.minHeight = PROMPT_H + "px";
            promptWidget.inputEl.style.maxHeight = PROMPT_H + "px";
            promptWidget.inputEl.style.resize = "none";
        }
        promptWidget.computeSize = (w) => [w, PROMPT_H];
        promptWidget.getHeight = () => PROMPT_H;
    }

    // Kayıtlı aktif sekmeyi geri yükle.
    const saved = node.properties && node.properties._zfrInpaintTab;
    if (saved && IS_TABS.some((t) => t.id === saved)) state.active = saved;

    // İlk açılışta node'u ferah başlat (sadece bir kez).
    if (!node._zfrSizedOnce) {
        node._zfrSizedOnce = true;
        applyVisibility(false);
        requestAnimationFrame(() => {
            const needed = node.computeSize();
            const curW = node.size ? node.size[0] : 0;
            const w = Math.max(curW, needed[0], 460);
            node.setSize([w, needed[1]]);
            node.setDirtyCanvas(true, true);
            syncFromWidget();
        });
    } else {
        applyVisibility();
        syncFromWidget();
    }

    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        document.removeEventListener("paste", onPaste, true);
        return onRemoved ? onRemoved.apply(this, arguments) : undefined;
    };

    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
        const res = onConfigure ? onConfigure.apply(this, arguments) : undefined;
        requestAnimationFrame(() => {
            const s = node.properties && node.properties._zfrInpaintTab;
            if (s && IS_TABS.some((t) => t.id === s)) state.active = s;
            applyVisibility();
            syncFromWidget();
        });
        return res;
    };
}