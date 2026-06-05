import { app } from "../../scripts/app.js";

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

const NODE_NAME = "Simple Image Generator (Multiple)";
const REF_PREFIX = "reference_image_";
const MAX_REFERENCE_IMAGES = 8;
const REF_TYPE = "IMAGE";

function isRefInput(name) {
    return typeof name === "string" && name.startsWith(REF_PREFIX);
}

function refIndex(name) {
    return parseInt(name.slice(REF_PREFIX.length), 10);
}

app.registerExtension({
    name: "ZFRNodes.DynamicReferenceImages",

    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) {
            return;
        }

        // Node üzerindeki mevcut referans inputlarını index'e göre sıralı döndürür.
        function getRefInputs(node) {
            const refs = [];
            const inputs = node.inputs || [];
            for (let i = 0; i < inputs.length; i++) {
                if (isRefInput(inputs[i].name)) {
                    refs.push({ slot: i, input: inputs[i], idx: refIndex(inputs[i].name) });
                }
            }
            refs.sort((a, b) => a.idx - b.idx);
            return refs;
        }

        function addRefInput(node, idx) {
            node.addInput(`${REF_PREFIX}${idx}`, REF_TYPE);
        }

        /*
         * Referans slotlarını "bağlı olanlar + tek boş slot" olacak şekilde ayarlar.
         * Eksikse boş slot ekler, fazlaysa sondaki boş slotları kaldırır.
         */
        function syncReferenceInputs(node) {
            let refs = getRefInputs(node);

            // Hiç referans inputu yoksa ilkini oluştur.
            if (refs.length === 0) {
                addRefInput(node, 1);
                node.setSize(node.computeSize());
                node.setDirtyCanvas(true, true);
                return;
            }

            // Bağlı en yüksek index'i bul.
            let lastConnected = 0;
            for (const r of refs) {
                if (r.input.link != null) {
                    lastConnected = Math.max(lastConnected, r.idx);
                }
            }

            // Olması gereken slot sayısı: bağlı olanlar + 1 boş (en fazla MAX).
            const desired = Math.min(lastConnected + 1, MAX_REFERENCE_IMAGES);

            // Mevcut en yüksek index.
            let highest = refs.length ? refs[refs.length - 1].idx : 0;

            // Eksik slotları ekle (1..desired aralığında boşluk bırakmadan).
            while (highest < desired) {
                highest += 1;
                addRefInput(node, highest);
            }

            // desired'ın üstündeki BOŞ (bağlı olmayan) slotları sondan kaldır.
            refs = getRefInputs(node);
            for (let k = refs.length - 1; k >= 0; k--) {
                const r = refs[k];
                if (r.idx > desired && r.input.link == null) {
                    // Slot index'i node.inputs içinde değişebileceğinden ada göre bul.
                    const slot = node.inputs.findIndex((inp) => inp.name === r.input.name);
                    if (slot !== -1) {
                        node.removeInput(slot);
                    }
                }
            }

            node.setSize(node.computeSize());
            node.setDirtyCanvas(true, true);
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            // ComfyUI, INPUT_TYPES'taki tüm optional referans slotlarını ekler.
            // Başlangıçta yalnızca reference_image_1 + boş slot mantığına indirgeyelim.
            requestAnimationFrame(() => syncReferenceInputs(this));
            return r;
        };

        const onConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info, ioSlot) {
            const r = onConnectionsChange
                ? onConnectionsChange.apply(this, arguments)
                : undefined;
            // Bağlantı durumu bu callback sonrasında tutarlı; bir sonraki frame'de uygula.
            requestAnimationFrame(() => syncReferenceInputs(this));
            return r;
        };

        // Workflow yüklenip bağlantılar geri yüklendikten sonra slotları hizala.
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => syncReferenceInputs(this));
            return r;
        };
    },
});
