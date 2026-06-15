> ## Documentation Index
> Fetch the complete documentation index at: https://docs.bfl.ml/llms.txt
> Use this file to discover all available pages before exploring further.

# Use Cases

> Real-world applications from marketing and design to e-commerce and image editing

export const ImageGridQuilted = ({images, cols = 4, rowHeight = 120, gap = 4, width = "100%", preserveAspectRatio = false}) => {
  const [hoveredIdx, setHoveredIdx] = useState(-1);
  const items = images || [{
    img: "https://images.unsplash.com/photo-1551963831-b3b1ca40c98e",
    title: "Breakfast",
    prompt: "A cozy breakfast spread on a wooden table, golden morning light, fresh berries and granola",
    colSpan: 2,
    rowSpan: 2
  }, {
    img: "https://images.unsplash.com/photo-1551782450-a2132b4ba21d",
    title: "Burger",
    prompt: "Juicy gourmet burger with melted cheese, crispy lettuce, studio lighting on dark background",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1522770179533-24471fcdba45",
    title: "Camera",
    prompt: "Vintage film camera on a wooden desk, soft natural light from a window, shallow depth of field",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1444418776041-9c7e33cc5a9c",
    title: "Coffee",
    prompt: "Steaming cup of black coffee, minimalist ceramic mug, morning atmosphere, warm tones",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1533827432537-70133748f5c8",
    title: "Hats",
    prompt: "Collection of straw summer hats hanging on a white wall, bright and airy, Mediterranean vibes",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1558642452-9d2a7deb7f62",
    title: "Honey",
    prompt: "Golden honey dripping from a wooden dipper, macro close-up, warm backlight, sticky texture",
    colSpan: 1,
    rowSpan: 2
  }, {
    img: "https://images.unsplash.com/photo-1516802273409-68526ee1bdd6",
    title: "Basketball",
    prompt: "Basketball on an outdoor court at sunset, dramatic orange sky, long shadows on concrete",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1518756131217-31eb79b20e8f",
    title: "Fern",
    prompt: "Lush green fern leaves, tight botanical composition, soft diffused forest light, dewdrops",
    colSpan: 2,
    rowSpan: 2
  }, {
    img: "https://images.unsplash.com/photo-1597645587822-e99fa5d45d25",
    title: "Mushrooms",
    prompt: "Wild mushrooms on the forest floor, moody autumn light, earthy tones, shallow focus",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1567306301408-9b74779a11af",
    title: "Tomato basil",
    prompt: "Fresh tomatoes and basil leaves, rustic kitchen setting, vibrant red and green contrast",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1471357674240-e1a485acb3e1",
    title: "Sea star",
    prompt: "Orange sea star on wet sand, turquoise ocean waves in background, golden hour beach light",
    colSpan: 1,
    rowSpan: 1
  }, {
    img: "https://images.unsplash.com/photo-1589118949245-7d38baf380d6",
    title: "Bike",
    prompt: "Vintage bicycle leaning against a pastel colored wall, Mediterranean street, cinematic tones",
    colSpan: 1,
    rowSpan: 1
  }];
  const renderCard = (item, idx) => {
    const hovered = hoveredIdx === idx;
    const cSpan = item.colSpan || 1;
    const rSpan = item.rowSpan || 1;
    const Wrapper = item.href ? "a" : "div";
    const wrapperProps = item.href ? {
      href: item.href,
      style: {
        textDecoration: "none"
      }
    } : {};
    return <Wrapper key={item.img} {...wrapperProps} onMouseEnter={() => setHoveredIdx(idx)} onMouseLeave={() => setHoveredIdx(-1)} style={{
      ...wrapperProps.style,
      position: "relative",
      overflow: "hidden",
      borderRadius: "4px",
      cursor: item.prompt || item.href ? "pointer" : "default",
      ...preserveAspectRatio ? {
        breakInside: "avoid",
        marginBottom: `${gap}px`,
        display: "block"
      } : {
        gridColumn: `span ${cSpan}`,
        gridRow: `span ${rSpan}`
      }
    }}>
        <img src={preserveAspectRatio ? `${item.img}?w=800&auto=format` : `${item.img}?w=${rowHeight * cSpan * 2}&h=${rowHeight * rSpan * 2}&fit=crop&auto=format`} srcSet={preserveAspectRatio ? `${item.img}?w=1600&auto=format&dpr=2 2x` : `${item.img}?w=${rowHeight * cSpan * 2}&h=${rowHeight * rSpan * 2}&fit=crop&auto=format&dpr=2 2x`} alt={item.title} loading="lazy" style={{
      display: "block",
      width: "100%",
      height: preserveAspectRatio ? "auto" : "100%",
      objectFit: preserveAspectRatio ? "cover" : "cover",
      pointerEvents: "none",
      transition: "transform 300ms ease",
      transform: hovered ? "scale(1.05)" : "scale(1)"
    }} />
        <div style={{
      position: "absolute",
      bottom: 0,
      left: 0,
      right: 0,
      padding: hovered ? "0.6rem 0.75rem" : "0.4rem 0.6rem",
      background: hovered ? "rgba(0,0,0,0.75)" : "linear-gradient(transparent, rgba(0,0,0,0.6))",
      backdropFilter: hovered ? "blur(4px)" : "none",
      pointerEvents: "none",
      transition: "all 250ms ease"
    }}>
          <span style={{
      color: "#fff",
      fontSize: "0.7rem",
      fontWeight: 600,
      display: "flex",
      alignItems: "center",
      gap: "0.35rem"
    }}>
            {item.title}
            {item.href && <span style={{
      opacity: hovered ? 1 : 0,
      transform: hovered ? "translateX(0)" : "translateX(-4px)",
      transition: "all 250ms ease",
      fontSize: "0.8rem"
    }}>→</span>}
          </span>
        </div>
      </Wrapper>;
  };
  if (preserveAspectRatio) {
    return <div className="not-prose" style={{
      columnCount: cols,
      columnGap: `${gap}px`,
      width,
      borderRadius: "0.75rem"
    }}>
        {items.map((item, idx) => renderCard(item, idx))}
      </div>;
  }
  return <div className="not-prose" style={{
    display: "grid",
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    gridAutoRows: `${rowHeight}px`,
    gap: `${gap}px`,
    width,
    overflow: "hidden",
    borderRadius: "0.75rem"
  }}>
      {items.map((item, idx) => renderCard(item, idx))}
    </div>;
};

Explore what's possible with FLUX. Each use case below demonstrates a real-world application — from product photography and marketing creatives to style transfer and multi-image compositing. Click any image to see examples and prompts.

## Text-to-Image Use Cases

<ImageGridQuilted
  cols={3}
  gap={6}
  preserveAspectRatio
  images={[
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/4088463e10bb2a5d7591d30b26bdb5f8775d6167-1440x752.png", title: "Photorealistic", prompt: "At high noon on a blustery day, capture the surreal presence of a sentient tree, seemingly rooted underwater just off a tumultuous ocean shore.", href: "/guides/usecases_t2i_photorealistic" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/bf14460ae86f1758ac515d8919f7dd25fad01f32-2048x1312.png", title: "HEX Color Prompting", prompt: "A vintage illustration of an apple in color #0047AB with a heart-shaped cutout in the middle, on a white background", href: "/guides/usecases_t2i_hex_color_prompting" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/1402aeece02e4025af9c78c66ce8e5deb5c0853d-1248x832.png", title: "Product Mockups", prompt: "Create a perfume bottle designed in the shape of a lollipop, with glossy candy-like texture, a stick handle, and elegant perfume-bottle detailing.", href: "/guides/usecases_t2i_product_mockups" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/7730d0482ee19d0d3207b5cbbb55074c3b66d554-1456x1920.png", title: "Typography & Design", prompt: "Samsung Galaxy S25 Ultra product advertisement, 'Ultra-strong titanium' headline, close-up of phone edge showing titanium frame, dark gradient background", href: "/guides/usecases_t2i_typography_design" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/0be71156d3d086117506a054cee29f83eafec85a-1040x1040.png", title: "Infographics", prompt: "Create a clear colorful infographic that explains step by step how to make a sandwich. Use simple icons and minimal text.", href: "/guides/usecases_t2i_infographics" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/75b4ec7dcf50c3731e820524f5bf863666cb1d45-2048x1312.png", title: "Multi-Language", prompt: "Un marché alimentaire dans la campagne normande, des marchands vendent divers légumes, fruits. Lever de soleil, temps un peu brumeux", href: "/guides/usecases_t2i_multi_language" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/e9a562af9dc1703faf1ceb1b6ea7c346b25ba564-1920x1072.png", title: "World Knowledge", prompt: "Iconic Icelandic landscape with volcanic terrain and northern lights", href: "/guides/usecases_t2i_world_knowledge" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/42fd4141b1a5684e7866adad65cdd4b9f6a83990-720x1280.png", title: "UI Mockups", prompt: "Sophisticated landing page for 'Catwalk' artisanal cat clothing brand featuring British Shorthair wearing custom-fitted cashmere sweater", href: "/guides/usecases_t2i_ui_mockups" },
{ img: "https://cdn.sanity.io/images/2gpum2i6/production/327357c01c579a3ccef7e86910dafc95e28cf6ce-1408x1408.png", title: "JSON Prompting", prompt: "Structured JSON prompt for precise brand color matching on an Adidas sweatshirt — each component assigned an exact hex color.", href: "/guides/usecases_t2i_json_prompting" },
]}
/>

