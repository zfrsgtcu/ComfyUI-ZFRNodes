> ## Documentation Index
> Fetch the complete documentation index at: https://docs.bfl.ml/llms.txt
> Use this file to discover all available pages before exploring further.

# Technical Parameters

> Aspect ratios and working without negative prompts

export const PromptCarousel = ({slides = [], height = "500px"}) => {
  const [activeIdx, setActiveIdx] = useState(0);
  const items = slides.length > 0 ? slides : [{
    img: "https://images.unsplash.com/photo-1551963831-b3b1ca40c98e?w=800&fit=crop",
    prompt: "A cozy breakfast spread on a wooden table"
  }];
  const goTo = idx => {
    const next = Math.max(0, Math.min(items.length - 1, idx));
    setActiveIdx(next);
  };
  return <div className="not-prose" style={{
    borderRadius: "0.75rem",
    overflow: "hidden",
    border: "1px solid rgba(255,255,255,0.08)",
    background: "#000000",
    marginTop: 0
  }}>
      {}
      <div style={{
    position: "relative",
    width: "100%",
    height,
    overflow: "hidden"
  }}>
        <div style={{
    display: "flex",
    transition: "transform 400ms cubic-bezier(0.25, 1, 0.5, 1)",
    transform: `translateX(-${activeIdx * 100}%)`,
    height: "100%"
  }}>
          {items.map(item => <div key={item.img} style={{
    flex: "0 0 100%",
    height: "100%"
  }}>
              <img src={item.img} alt={item.prompt?.slice(0, 80) || ""} draggable={false} style={{
    display: "block",
    width: "100%",
    height: "100%",
    objectFit: "contain",
    pointerEvents: "none"
  }} />
            </div>)}
        </div>

        {items.length > 1 && <>
            <button onClick={() => goTo(activeIdx - 1)} style={{
    position: "absolute",
    top: "50%",
    left: "12px",
    transform: "translateY(-50%)",
    width: "40px",
    height: "40px",
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.5)",
    backdropFilter: "blur(4px)",
    color: "#fff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
    opacity: activeIdx === 0 ? 0.3 : 1,
    transition: "opacity 200ms"
  }} disabled={activeIdx === 0}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 2L4 7L9 12" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
            <button onClick={() => goTo(activeIdx + 1)} style={{
    position: "absolute",
    top: "50%",
    right: "12px",
    transform: "translateY(-50%)",
    width: "40px",
    height: "40px",
    borderRadius: "50%",
    border: "none",
    background: "rgba(0,0,0,0.5)",
    backdropFilter: "blur(4px)",
    color: "#fff",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
    opacity: activeIdx === items.length - 1 ? 0.3 : 1,
    transition: "opacity 200ms"
  }} disabled={activeIdx === items.length - 1}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 2L10 7L5 12" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </>}
      </div>

      {}
      {items.length > 1 && items[0]?.title ? <div style={{
    display: "flex",
    justifyContent: "center",
    gap: "4px",
    padding: "12px 8px 4px",
    flexWrap: "wrap"
  }}>
          {items.map((item, idx) => <button key={idx} onClick={() => goTo(idx)} style={{
    padding: "4px 12px",
    borderRadius: "6px",
    border: "none",
    cursor: "pointer",
    fontSize: "0.7rem",
    fontWeight: activeIdx === idx ? 700 : 500,
    background: activeIdx === idx ? "rgba(255,255,255,0.15)" : "transparent",
    color: activeIdx === idx ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.45)",
    transition: "all 200ms ease"
  }}>
              {item.title}
            </button>)}
        </div> : items.length > 1 && <div style={{
    display: "flex",
    justifyContent: "center",
    gap: "8px",
    padding: "12px 0 4px"
  }}>
          {items.map((_, idx) => <button key={idx} onClick={() => goTo(idx)} style={{
    width: activeIdx === idx ? "24px" : "8px",
    height: "8px",
    borderRadius: "4px",
    border: "none",
    padding: 0,
    cursor: "pointer",
    background: activeIdx === idx ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.3)",
    transition: "all 300ms ease"
  }} />)}
        </div>}

      {}
      <div style={{
    padding: "0.5rem 0.5rem 0.6rem"
  }}>
        <div style={{
    padding: "0.6rem 0.75rem",
    borderRadius: "6px",
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.10)",
    fontFamily: "monospace",
    fontSize: "0.75rem",
    lineHeight: 1.6,
    color: "rgba(255,255,255,0.7)",
    minHeight: "2.4rem",
    transition: "opacity 200ms ease"
  }}>
          <span style={{
    color: "rgba(255,255,255,0.35)",
    fontSize: "0.65rem",
    marginRight: "6px"
  }}>prompt:</span>
          {items[activeIdx]?.prompt || ""}
        </div>
      </div>
    </div>;
};

## Aspect Ratios

Choose the ratio that matches the compositional intent of your scene. Mismatched ratios force the model to either crop or pad the composition.

| Ratio    | Format         | Best For                               |
| -------- | -------------- | -------------------------------------- |
| **1:1**  | Square         | Social media, profiles, product shots  |
| **16:9** | Landscape      | Widescreen, web headers, presentations |
| **9:16** | Portrait       | Mobile, stories, vertical editorial    |
| **4:3**  | Standard       | Classic photography                    |
| **3:2**  | Photo standard | DSLR-style portrait and landscape      |
| **21:9** | Ultra-wide     | Cinematic, panoramic scenes            |

<Tip>A landscape-oriented prompt benefits from 16:9; a portrait prompt from 9:16.</Tip>

## Working Without Negative Prompts

Most FLUX models do not support negative prompts. Even when they can process them, AI models generally struggle with negation — writing *"a person without glasses"* causes the model to focus on "glasses" and often generate exactly what you were trying to avoid.

### The Replacement Strategy

When you catch yourself writing negative phrases, use this mental process:

1. **Identify** the unwanted element: *"no crowds"*
2. **Ask** what would fill that space: *"What would I see there?"*
3. **Describe** the positive: *"peaceful solitude"* or *"empty pathways"*

**Common replacements:**

| Instead of...        | Write...                                       |
| -------------------- | ---------------------------------------------- |
| "no people"          | "empty", "deserted", "solitary"                |
| "without clothes"    | "bare skin", "natural form"                    |
| "no colors"          | "monochrome", "black and white", "grayscale"   |
| "no text"            | "clean surfaces", "unmarked", "blank"          |
| "no modern elements" | "traditional", "historical", "period-accurate" |
| "not dark"           | "brightly lit", "sun-drenched"                 |
| "not sad"            | "joyful", "content"                            |
| "not running"        | "walking peacefully", "standing still"         |
| "not many"           | "few", "single", "minimal"                     |

### Practical Examples

<AccordionGroup>
  <Accordion title="Context & Setting">
    * **Instead of**: "a street with no cars"
      **Write**: "a quiet pedestrian walkway with cobblestones"

    * **Instead of**: "a landscape without buildings"
      **Write**: "pristine wilderness with untouched natural terrain"

    * **Instead of**: "a room with no furniture"
      **Write**: "a spacious empty room with polished wooden floors"
  </Accordion>

  <Accordion title="Character & Portrait">
    * **Instead of**: "a person without a hat"
      **Write**: "a person with natural hair flowing freely"

    * **Instead of**: "a portrait with no glasses"
      **Write**: "a portrait showing clear, unobstructed eyes"
  </Accordion>

  <Accordion title="Mood and Atmosphere">
    * **Instead of**: "not dark or scary"
      **Write**: "peaceful, welcoming, and warm atmosphere with soft golden lighting"

    * **Instead of**: "not too realistic"
      **Write**: "stylized illustration with simplified forms and bold color blocks"
  </Accordion>

  <Accordion title="Compositional Control">
    * **Instead of**: "portrait with no background distractions"
      **Write**: "portrait with smooth gradient background transitioning from deep blue to black"
  </Accordion>
</AccordionGroup>

### The Beach Progression

Positive framing combined with specificity consistently produces better results:

<PromptCarousel
  height="400px"
  slides={[
{
  img: "https://cdn.sanity.io/images/gsvmb6gz/production/4fc2c5a86463f31bca29cb1b4ee502b5d713ccfe-1392x752.jpg",
  prompt: "A beach"
},
{
  img: "https://cdn.sanity.io/images/gsvmb6gz/production/ca548a2e74e7372b485c9d9ba72914487d196d60-1392x752.jpg",
  prompt: "Empty beach with palm trees and gentle waves"
},
{
  img: "https://cdn.sanity.io/images/gsvmb6gz/production/ca91ec2d49372239d56bb13b18a8d50bc1180305-1392x752.jpg",
  prompt: "Empty beach with palm trees and gentle waves, golden sunset, IMAX-quality look"
},
]}
/>

### When Positive Alternatives Don't Work

If you're still getting unwanted elements despite positive framing:

1. **Be more specific** about what you do want in that space
2. **Front-load the positive description** — word order signals priority
3. **Add more descriptive detail** to strengthen the positive alternative
4. **Use environmental context** to make the positive element feel natural

<Tip>Think visually about what you want to see, not what to avoid.</Tip>

## Prompt Upsampling

FLUX.2 \[pro], \[max], and \[flex] automatically enhance short prompts by adding visual detail and context while preserving your original intent. This is useful for:

* Quick iterations without crafting detailed prompts
* Exploring creative variations from a short concept
* Generating richer output from a basic idea

<Tip>
  On FLUX.2 \[klein], what you write is what you get — be descriptive. Other FLUX.2 variants are more forgiving with short prompts.
</Tip>
