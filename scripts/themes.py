import logging
import os
from scripts.utilities import Colour

Image = None
Image_loaded = False

def loadPilImageModule():
    global Image, Image_loaded
    try:
        from PIL import Image
    except:
        return False
    Image_loaded = True
    return True

def getPixelHex(pixels, x, y):
    r,g,b = pixels[x,y]
    return Colour.rgbToHex(r,g,b)

class CSSTheme(object):
    def __init__(
            self,
            name:str="default",
            themed_dark="#004c9d",
            themed_mid="#007bff",
            themed_light="#56a8ff",
            set_white="#ffffff",
            set_gray_light="#c3c3c3",
            set_gray_dark="#7f7f7f",
            set_black="#000000",
            alert_important="#ca0000"
        ):
        self.name = name
        self.colours = {
            "themed_dark": themed_dark,
            "themed_mid": themed_mid,
            "themed_light": themed_light,
            "set_white": set_white,
            "set_gray_light": set_gray_light,
            "set_gray_dark": set_gray_dark,
            "set_black": set_black,
            "alert_important": alert_important,
        }
        self.generateExtraColours()
    
    def generateExtraColours(self):
        """
        Generates new related colours
        and adds them to the colours dict
        """
        for key in [
                "themed_dark",
                "themed_mid",
                "themed_light"
            ]:
            # generate desaturated versions of these
            value = self.colours[key]
            r,g,b = Colour.hexToRgb(value)
            h,s,v = Colour.rgbToHsv(r,g,b)

            r2,g2,b2 = Colour.hsvToRgb(h,s*0.1,v)
            value2 = Colour.rgbToHex(r2,g2,b2)
            self.colours[key+'_desat_10'] = value2

            r2,g2,b2 = Colour.hsvToRgb(h,s*0.3,v)
            value2 = Colour.rgbToHex(r2,g2,b2)
            self.colours[key+'_desat_30'] = value2

            r2,g2,b2 = Colour.hsvToRgb(h,s*0.6,v)
            value2 = Colour.rgbToHex(r2,g2,b2)
            self.colours[key+'_desat_60'] = value2

def imageToTheme(theme_name, image_filename:str):
    # maybe move this function into
    # a utility file rather than something bundled,
    # since it relies on an external module
    loadPilImageModule()
    if not Image_loaded:
        return
    img = Image.open(image_filename).convert('RGB')
    pixels = img.load()
    colours = {
        "themed_dark": getPixelHex(pixels, 0, 0),
        "themed_mid": getPixelHex(pixels, 1, 0),
        "themed_light": getPixelHex(pixels, 2, 0),
        "alert_important": getPixelHex(pixels, 3, 0),
        "set_black": getPixelHex(pixels, 0, 1),
        "set_gray_dark": getPixelHex(pixels, 1, 1),
        "set_gray_light": getPixelHex(pixels, 2, 1),
        "set_white": getPixelHex(pixels, 3, 1)
    }
    theme_code = ''
    theme_code += f'// this theme file was auto-generated\n'
    theme_code += '\n'
    theme_code += f'// theme name\n'
    theme_code += f'_theme_name {theme_name}\n'
    theme_code += '\n'
    theme_code += f'// theme colours, in hex\n'
    for key, value in colours.items():
        theme_code += f'{key} {value}\n'
    # save this theme's code to a file
    with open(f'./resources/themes/{theme_name}.theme'.lower(), 'w') as f:
        f.write(theme_code)

def loadThemeFile(theme_filename:str):
    if not os.path.exists(theme_filename):
        return False
    
    theme = CSSTheme()
    with open(theme_filename, 'r') as f:
        lines = [l.strip() for l in f.readlines()]
        for line in lines:
            if not line:
                # this is a blank line, ignore it
                continue
            if line.startswith('//'):
                # this is a commented line, ignore it
                continue
            try:
                key, value = line.split(' ',1)
            except:
                continue
            
            if key.startswith('_'):
                # this is a special variable, handle
                # separate from other variables
                if key == '_theme_name':
                    theme.name = value.title()
            else:
                if key in theme.colours:
                    theme.colours[key] = value
    
    theme.generateExtraColours()

    return theme

def getThemeByName(theme_name:str):
    theme_name = theme_name.title()
    for theme in themes:
        if theme.name == theme_name:
            return theme
    return None


themes = []
themes_dir = os.path.join(
    os.getcwd(),
    './resources/themes/')
for filename in os.listdir(themes_dir):
    if not filename.endswith('.theme'):
        continue
    filepath = os.path.join(themes_dir, filename)
    theme = loadThemeFile(filepath)
    if theme == None:
        logging.warn(f"failed to load theme, filename {filename}")
        continue
    logging.debug(f"loaded theme, filename {filename}")
    themes.append(theme)


def applyTheme(theme:CSSTheme=themes[0]):
    """
    rebuilds the variables.css file.
    Can be used to change the colour themes.
    """
    if type(theme) == str:
        theme = getThemeByName(theme)
        if theme == None:
            return False
    
    definitions_dict = theme.colours

    new_css = (
        f'/* \n'
        f'\n'
        f'THIS FILE IS AUTO-GENERATED BY A SCRIPT\n'
        f'scripts/themes.py\n'
        f'\n'
        f'ANY CHANGES MADE TO THIS FILE WILL BE LOST\n'
        f'\n'
        f'*/\n'
        f'\n'
        f'\n'
         ':root {\n'
        f'    /*\n'
        f'    colours used for styling, provided here\n'
        f'    for easy changing later on in the design\n'
        f'    process, or according to user feedback.\n'
        f'    */\n'
        # the rest of this is generated below
    )

    for key, value in definitions_dict.items():
        key_css = '--'+key.replace('_','-')
        new_css += '\n'
        new_css += '    '+key_css+': '+value+';'
    
    new_css += '\n}'

    file_location = './resources/html/css/variables.css'

    with open(file_location, 'w') as f:
        f.write(new_css)

    return True

def test():
    import random

    print("rebuilding theme files from images...")
    imageToTheme('Cool', 'resources/icons/colormap_cool.png')
    imageToTheme('Warm', 'resources/icons/colormap_warm.png')
    imageToTheme('Pink', 'resources/icons/colormap_pink.png')
    imageToTheme('Green', 'resources/icons/colormap_green.png')
    imageToTheme('Gray', 'resources/icons/colormap_gray.png')
    # imageToTheme('Dark', 'resources/icons/colormap_dark.png')

    print("applying theme...")
    input('set random theme...')
    while 1:
        for theme in themes:
            applyTheme(theme)
            print(f"applied {theme.name}")
            x = input('... cycle ...')
            if x:
                break