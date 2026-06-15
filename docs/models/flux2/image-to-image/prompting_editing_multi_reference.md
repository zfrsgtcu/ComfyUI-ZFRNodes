> ## Documentation Index
> Fetch the complete documentation index at: https://docs.bfl.ml/llms.txt
> Use this file to discover all available pages before exploring further.

# Multi-Reference Editing

> Combine multiple input images for style transfer, composites, and editorial scenes

export const MultiRefMasonry = ({inputs = [], result = {}, prompt = ""}) => {
  const [hoveredInput, setHoveredInput] = useState(-1);
  const colors = [{
    bg: "rgba(99,182,137,0.22)",
    border: "#63b689",
    text: "#63b689"
  }, {
    bg: "rgba(130,170,255,0.22)",
    border: "#82aaff",
    text: "#82aaff"
  }, {
    bg: "rgba(255,180,107,0.22)",
    border: "#ffb46b",
    text: "#ffb46b"
  }, {
    bg: "rgba(199,140,230,0.22)",
    border: "#c78ce6",
    text: "#c78ce6"
  }, {
    bg: "rgba(255,130,130,0.22)",
    border: "#ff8282",
    text: "#ff8282"
  }, {
    bg: "rgba(130,220,220,0.22)",
    border: "#82dcdc",
    text: "#82dcdc"
  }, {
    bg: "rgba(220,200,120,0.22)",
    border: "#dcc878",
    text: "#dcc878"
  }, {
    bg: "rgba(200,160,180,0.22)",
    border: "#c8a0b4",
    text: "#c8a0b4"
  }];
  const renderPrompt = () => {
    if (!prompt) return null;
    const parts = [];
    let lastIndex = 0;
    const re = /\b(image\s+(\d))\b/gi;
    let m;
    while ((m = re.exec(prompt)) !== null) {
      if (m.index > lastIndex) parts.push({
        text: prompt.slice(lastIndex, m.index),
        idx: -1
      });
      parts.push({
        text: m[1],
        idx: parseInt(m[2], 10) - 1
      });
      lastIndex = m.index + m[0].length;
    }
    if (lastIndex < prompt.length) parts.push({
      text: prompt.slice(lastIndex),
      idx: -1
    });
    return parts.map((p, i) => {
      if (p.idx >= 0 && p.idx < colors.length) {
        const c = colors[p.idx];
        return <span key={i} style={{
          color: c.text,
          fontWeight: 700,
          padding: "1px 5px",
          borderRadius: "3px",
          background: hoveredInput === p.idx ? c.bg : "transparent",
          transition: "background 200ms"
        }}>
            {p.text}
          </span>;
      }
      return <span key={i}>{p.text}</span>;
    });
  };
  const n = inputs.length;
  const useLeftRight = n <= 4;
  const inputItem = (img, idx) => {
    const c = colors[idx % colors.length];
    const isHovered = hoveredInput === idx;
    return <div key={idx} onMouseEnter={() => setHoveredInput(idx)} onMouseLeave={() => setHoveredInput(-1)} style={{
      position: "relative",
      overflow: "hidden",
      borderRadius: "4px",
      cursor: "default",
      outline: isHovered ? "2px solid " + c.border : "2px solid transparent",
      outlineOffset: "-2px",
      transition: "outline-color 150ms ease"
    }}>
        <img src={img.src} alt={img.label || "Input " + (idx + 1)} style={{
      display: "block",
      width: "100%",
      height: "auto",
      pointerEvents: "none"
    }} />
        <div style={{
      position: "absolute",
      top: "4px",
      left: "4px",
      width: "22px",
      height: "22px",
      borderRadius: "50%",
      background: c.border,
      color: "#000",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "0.65rem",
      fontWeight: 800,
      boxShadow: "0 1px 4px rgba(0,0,0,0.5)"
    }}>
          {idx + 1}
        </div>
      </div>;
  };
  const resultItem = <div style={{
    position: "relative",
    overflow: "hidden",
    borderRadius: "4px"
  }}>
      <img src={result.src} alt={result.label || "Result"} style={{
    display: "block",
    width: "100%",
    height: "auto",
    pointerEvents: "none"
  }} />
      <div style={{
    position: "absolute",
    top: "6px",
    right: "6px",
    padding: "3px 10px",
    borderRadius: "5px",
    background: "rgba(0,0,0,0.6)",
    backdropFilter: "blur(4px)",
    color: "#fff",
    fontSize: "0.65rem",
    fontWeight: 600
  }}>
        Result
      </div>
    </div>;
  const inputRows = n <= 2 ? n : n <= 4 ? 2 : n;
  const inputColsInner = n <= 3 ? 1 : 2;
  return <div className="not-prose" style={{
    borderRadius: "0.75rem",
    border: "1px solid rgba(255,255,255,0.08)",
    background: "#000000"
  }}>

      {useLeftRight ? <div style={{
    display: "grid",
    gridTemplateColumns: "1fr 2fr",
    gap: "3px",
    padding: "3px",
    alignItems: "start"
  }}>
          {}
          <div style={{
    display: "grid",
    gridTemplateColumns: "repeat(" + inputColsInner + ", 1fr)",
    gridTemplateRows: "repeat(" + inputRows + ", auto)",
    gap: "3px"
  }}>
            {inputs.map((img, idx) => inputItem(img, idx))}
          </div>
          {}
          {resultItem}
        </div> : <div style={{
    display: "flex",
    flexDirection: "column",
    gap: "3px",
    padding: "3px"
  }}>
          <div style={{
    display: "grid",
    gridTemplateColumns: "repeat(" + Math.min(n, 6) + ", 1fr)",
    gap: "3px"
  }}>
            {inputs.map((img, idx) => inputItem(img, idx))}
          </div>
          {resultItem}
        </div>}

      {}
      {prompt && <div style={{
    padding: "0.5rem 0.5rem 0.6rem"
  }}>
          <div style={{
    padding: "0.6rem 0.75rem",
    borderRadius: "6px",
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.10)",
    fontFamily: "monospace",
    fontSize: "0.72rem",
    lineHeight: 1.6,
    color: "rgba(255,255,255,0.7)"
  }}>
            <span style={{
    color: "rgba(255,255,255,0.35)",
    fontSize: "0.6rem",
    marginRight: "5px"
  }}>prompt:</span>
            {renderPrompt()}
          </div>
        </div>}
    </div>;
};

Multi-reference editing combines multiple input images into a single generated output. Use it for fashion composites, interior design, product scenes, and character-consistent variations. When using several references, describe the role of each image so the model knows what to pull from where.

<Note>
  **\[pro] API has a 9MP total limit for input + output.** At 1MP output you can use up to 8 reference images, at 2MP output up to 7, and so on. FLUX.2 \[klein] supports up to 4 references.
</Note>

Multi-reference works well for:

* **Fashion shoots**: Combine clothing items into styled outfits
* **Interior design**: Place furniture and decor in rooms
* **Product composites**: Combine multiple products in scenes
* **Character consistency**: Maintain identity across variations

## Example 1

<MultiRefMasonry
  inputs={[
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/1115a1438ca3daaad5b54b95ea2b174db57b03f4-500x333.png", label: "Chickens" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/e27fe799702fe6df233cbf76e44af09f0babe0f6-500x750.png", label: "Mat A" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/b215d41ffba47fa273687db0a2c3ba854e8fdf19-500x333.png", label: "Pillow" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/dad25402f86c0e338f430679ea7253d38309fd71-421x750.png", label: "Mat B" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/9606b80fdb30699eef8876d51a2d958b5489f56b-500x333.png", label: "Wood" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/4e3452cf324b7a9a1bd04c46861ba1bbf7d94433-500x333.png", label: "Eggs" },
]}
  result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/4bd08e6e18e3ef9dc1a0a153ff304e38f8a4d233-496x320.png" }}
  prompt="Create a house for the chickens from image 1 using materials from images 2, 3, 4, and 5. Use the wood from image 5 for the base, the materials from images 2 and 4 for the walls and floor, and the material from image 3 for a small pillow nest. Place the chickens from image 1 in their new home, sitting on the pillow nest. Next to them, include the eggs from image 6. Apply the style of image 1 to the entire new scene."
/>

## Example 2

<MultiRefMasonry
  inputs={[
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/bb9e891629e8938743b8a68b4ce77290c8ec65c0-2160x2700.jpg", label: "Swing" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/b93671c8254ee4e1822195fd0938c08c6ad227ef-1033x1549.jpg", label: "Woman" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/d25f8febe3187a9462d7d82b145b986309de7386-3090x4633.jpg", label: "Cat" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/63d0711eb27f5f4383a83d4286db94971c71c4c1-736x912.png", label: "Style" },
]}
  result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/1ef99a1d7b06e57da0facc18ff3ca8b44ced2339-1152x1440.png" }}
  prompt="A photograph of the woman in image 2 sitting on the swing in image 1 and the cat from image 3 sitting on her lap, all in the style of image 4"
/>

## Example 3

<MultiRefMasonry
  inputs={[
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/4914d39ec46fa9cd1878e10674081b3959703694-1033x1549.jpg", label: "View" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/ba45c02ec73c084540b0801688954e0722c989d9-949x1686.jpg", label: "Couple" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/9a490f3d6ef69278ffaa972c358c376c37c4e3d0-3848x4810.jpg", label: "Food" },
{ src: "https://cdn.sanity.io/images/2gpum2i6/production/8c547b9eed565e9ef993448ab59ad397aa9689dc-1033x1549.jpg", label: "Room" },
]}
  result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/3161e52aa3afefd2546633b6d437bebe6f99935c-960x1440.png" }}
  prompt="Place the view from image 1 inside the window of image 4, making it the new background seen through the glass. Then place the couple from image 2 seated naturally at the table in image 4, matching scale, lighting, and perspective. Finally, put the food from image 3 on the table in front of them, arranged so it looks like they are sharing the meal together."
/>

## Use Cases

Multi-reference editing covers a wide range of creative and professional tasks. Below are the most common categories with real prompt examples.

***

### Scene Compositing

Combine elements from multiple source images into a single coherent scene.

<AccordionGroup>
  <Accordion title="Animal placed in scene">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/35bbfd4cb834b4b441e76c2aba8025a8d85b29f0-1200x800.jpg", label: "Bathtub" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/6d4accd102227c63a70e516d0e5d76b0cf3f5745-960x1200.jpg", label: "Alpaca" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/68d5eefdcd9931d9536b15b26a0505c9ffcc72d5-1200x800.jpg" }}
      prompt="Take the animal from image 2 and place it naturally inside the bathtub from image 1. Fill the tub with water and bubbles, and add a rubber duck on the animal's head."
    />
  </Accordion>

  <Accordion title="Underwater room">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/02393cf9968cbf103195b9eb0343c8ab826a1ae2-799x1200.jpg", label: "Room" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/eff4cc5d02f21e4ffd09e649445637e806e56d42-900x1200.jpg", label: "Underwater" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/451bc541700469e4618645a5c887bf5e04a5b183-786x1200.jpg" }}
      prompt="Using the corals and fish from the underwater image, place them inside the vintage room as if the entire room is submerged deep in the ocean. The specific coral formations from the first image should grow along the walls, ceiling, and floor, keeping their original shapes and colors."
    />
  </Accordion>
</AccordionGroup>

***

### Style & Material Transfer

Apply the visual style, texture, or material of one image onto the content of another.

<AccordionGroup>
  <Accordion title="Impasto style transfer">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/0cd2bc72448e9be220cd5de5558f2f6b5973441f-699x750.jpg", label: "Cat photo" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/f2779c2086110676494152f9bf4ef7a22d4fd787-360x237.jpg", label: "Style" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/f9ea604a7f73e7e2f4d185d2d83390221e5adbe2-688x736.jpg" }}
      prompt="An impasto painting of a gigantic fluffy ginger-and-white cat walking through a narrow New York alley. Thick textured brushstrokes, bold color layers, expressive painterly details, and a dramatic sense of scale."
    />
  </Accordion>

  <Accordion title="Animal pattern transfer">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/09d279847b8ff443b7214f5eca5db019053c6246-500x750.jpg", label: "Cat" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/ab0dfc97c6e7640a73d57b69daee2891e6fecbdc-502x750.jpg", label: "Pattern source" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/e54cc75458e0ad0e4d3da6e1062dd6b22db29a51-496x736.jpg" }}
      prompt="Apply the colors, patterns, and surface tones of the animal in Image 2 to the animal in Image 1. Keep the pose, lighting, and overall composition of Image 1 unchanged."
    />
  </Accordion>

  <Accordion title="Pattern onto plate">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/d39856ac7f347609b515a27949a3a92e43dcc4e2-1200x800.jpg", label: "Plate" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/baf2e03f89390f6940a5ce2d0f6f3835262efc22-800x1200.jpg", label: "Pattern" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/d1b7e8fba2fbfa40e4cfe3c32fcedc0721baaaf9-1200x800.jpg" }}
      prompt="Apply the pattern from image 2 onto the plate in image 1"
    />
  </Accordion>
</AccordionGroup>

***

### Object Replacement

Replace or fill objects with elements from another reference image.

<AccordionGroup>
  <Accordion title="Fill bottles with liquid">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/079050c86be377a68dfcfb17f28acc430a93a54d-1200x1200.jpg", label: "Bottles" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/8d0259eee11952faa21e39334ea4acf99da32382-1200x800.jpg", label: "Liquid" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/e7687996aa1138fbd8a74bc51a555288112c985b-1200x1200.jpg" }}
      prompt="Fill the bottles in image 1 with the liquid from image 2, matching the color, texture, and translucency of the liquid. Then replace the pile of foam in image 1 with a realistic puddle of the liquid from image 2."
    />
  </Accordion>
</AccordionGroup>

***

### Logo & Branding

Place logos from one image onto objects or scenes in another.

<AccordionGroup>
  <Accordion title="Logo engraved in tree">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/83125b7b2b5fbe84b55c7031b52dadb8a640a1b1-1200x800.jpg", label: "Tree" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/6e754bd689a380d5683120d8054185d365b2070a-1200x675.jpg", label: "Logo" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/14f4a81efe558ffbeeda7e94dbbadd5279be3f4a-1200x800.jpg" }}
      prompt="Engrave the logo from image 2 into the tree trunk in image 1"
    />
  </Accordion>

  <Accordion title="Smoke shaped as logo">
    <MultiRefMasonry
      inputs={[
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/31d47345b8ee244203ff291ed7ca9e33fc19aa96-1200x675.jpg", label: "Smoke" },
    { src: "https://cdn.sanity.io/images/2gpum2i6/production/6e754bd689a380d5683120d8054185d365b2070a-1200x675.jpg", label: "Logo" },
  ]}
      result={{ src: "https://cdn.sanity.io/images/2gpum2i6/production/3c30e4c007520b47ed79974d023386b9d4190d04-1200x675.jpg" }}
      prompt="Shape the smoke in image 1 so that it forms the logo from image 2"
    />
  </Accordion>
</AccordionGroup>

***

## Writing Effective Multi-Reference Prompts

<Tip>
  Be **specific** about what changes and **clear** about the target state. Reference image locations when needed (e.g., "image 1", "image 2") and let the references provide visual context.
</Tip>

<CardGroup cols={2}>
  <Card title="Good prompts">
    * "Add dramatic storm clouds to the sky"
    * "Change her dress from blue to deep burgundy"
    * "Age this portrait by 30 years"
    * "Change image 1 to match the style of image 2"
  </Card>

  <Card title="Avoid">
    * "Make it better"
    * "Improve the lighting"
    * "Make it more professional"
    * "Fix the image"
  </Card>
</CardGroup>
