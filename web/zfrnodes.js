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
        node.setSize(node.computeSize());
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
    uploadBtn.style.cssText =
        "padding:6px 10px;border:1px solid #555;border-radius:6px;background:#2a2a2a;" +
        "color:#eee;cursor:pointer;font-size:12px;width:100%;box-sizing:border-box;";
    uploadBtn.onmouseenter = () => (uploadBtn.style.background = "#383838");
    uploadBtn.onmouseleave = () => (uploadBtn.style.background = "#2a2a2a");

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
    const FOOTER_H = 96;        // buton + sayaç + mod select + border
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
        const sz = node.computeSize();
        // Genişlik en az 240px olsun ki satırlar sıkışmasın.
        sz[0] = Math.max(sz[0], 240);
        node.setSize(sz);
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

    fileInput.onchange = async () => {
        const files = Array.from(fileInput.files || []);
        fileInput.value = ""; // aynı dosya tekrar seçilebilsin.
        for (const file of files) {
            if (state.items.length >= RIL_MAX_IMAGES) break;
            try {
                const data = await uploadFile(file);
                state.items.push({
                    name: data.name,
                    subfolder: data.subfolder || "",
                    type: data.type || "input",
                    expanded: false,
                });
            } catch (err) {
                console.error("[ZFRNodes] Reference image upload failed:", err);
            }
        }
        writeValue();
        render();
        refreshOutputs();
        resize();
    };

    uploadBtn.onclick = () => {
        if (state.items.length >= RIL_MAX_IMAGES) return;
        fileInput.click();
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
