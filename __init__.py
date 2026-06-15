from .py.convert_to_integer import ConvertToInteger
from .py.convert_to_float import ConvertToFloat
from .py.convert_to_string import ConvertToString
from .py.convert_to_boolean import ConvertToBoolean
from .py.json_frame_extractor import JsonFrameExtractor
from .py.story_frame_generator import StoryFrameGenerator
from .py.simple_image_generator import SimpleImageGenerator
from .py.simple_image_generator_multiple import SimpleImageGeneratorMultiple
from .py.prompt_guide import PromptGuide
from .py.reference_image_loader import ReferenceImageLoader
from .py.story_director import StoryDirector
from .py.asset_sheet_director import AssetSheetDirector
from .py.sheet_compositor import SheetCompositor


NODE_CLASS_MAPPINGS = {
    "Convert To Integer": ConvertToInteger,
    "Convert To Float": ConvertToFloat,
    "Convert To String": ConvertToString,
    "Convert To Boolean": ConvertToBoolean,
    "JSON Frame Extractor": JsonFrameExtractor,
    "Story Frame Generator": StoryFrameGenerator,
    "Simple Image Generator": SimpleImageGenerator,
    "Simple Image Generator (Multiple)": SimpleImageGeneratorMultiple,
    "Prompt Guide": PromptGuide,
    "Reference Image Loader": ReferenceImageLoader,
    "Story Director": StoryDirector,
    "Asset Sheet Director": AssetSheetDirector,
    "Sheet Compositor": SheetCompositor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Convert To Integer": "Convert To Integer",
    "Convert To Float": "Convert To Float",
    "Convert To String": "Convert To String",
    "Convert To Boolean": "Convert To Boolean",
    "JSON Frame Extractor": "JSON Frame Extractor",
    "Story Frame Generator": "Story Frame Generator",
    "Simple Image Generator": "Simple Image Generator",
    "Simple Image Generator (Multiple)": "Simple Image Generator (Multiple)",
    "Prompt Guide": "Prompt Guide",
    "Reference Image Loader": "Reference Image Loader",
    "Story Director": "Story Director",
    "Asset Sheet Director": "Asset Sheet Director",
    "Sheet Compositor": "Sheet Compositor",
}

# Dinamik referans inputları için web (frontend) eklentisi dizini.
WEB_DIRECTORY = "./web"

__version__ = "1.1.0"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY", "__version__"]
