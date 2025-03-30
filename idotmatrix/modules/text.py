from typing import Union, List
from ..connectionManager import ConnectionManager
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps

from typing import Tuple, Optional, Union
import zlib

class Text:
    """Manages text processing and packet creation for iDotMatrix devices. With help from https://github.com/8none1/idotmatrix/ :)"""

    logging = logging.getLogger(__name__)
    # must be 16x32 or 8x16
    image_width = 16
    image_height = 32
    # must be x05 for 16x32 or x02 for 8x16
    separator = b"\x05\xff\xff\xff"

    def __init__(self) -> None:
        self.conn: ConnectionManager = ConnectionManager()

    async def setMode(
        self,
        text: str,
        font_size: int = 16,
        font_path: Optional[str] = None,
        text_mode: int = 1,
        speed: int = 95,
        text_color_mode: int = 1,
        text_color: Tuple[int, int, int] = (255, 0, 0),
        text_bg_mode: int = 0,
        text_bg_color: Tuple[int, int, int] = (0, 255, 0),
    ) -> Union[bool, bytearray]:
        try:
            data = self._buildStringPacket(
                text_mode=text_mode,
                speed=speed,
                text_color_mode=text_color_mode,
                text_color=text_color,
                text_bg_mode=text_bg_mode,
                text_bg_color=text_bg_color,
                text_bitmaps=self._StringToBitmaps(
                    text=text,
                    font_size=font_size,
                    font_path=font_path,
                ),
            )
            if self.conn:
                await self.conn.connect()
                chunks = self._splitIntoChunks(data, 512)
                for chunk in chunks:
                    await self.conn.send(data=chunk)
                    #await self.conn.send(data=data)
            return data
        except BaseException as error:
            self.logging.error(f"could send the text to the device: {error}")
            return False
        
    def _splitIntoChunks(self, data: bytearray, chunk_size: int) -> List[bytearray]:
        """Split the data into chunks of specified size.

        Args:
            data (bytearray): data to split into chunks
            chunk_size (int): size of the chunks

        Returns:
            List[bytearray]: returns list with chunks of given data input
        """
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def _buildStringPacket(
        self,
        text_bitmaps: bytearray,
        text_mode: int = 1,
        speed: int = 96,
        text_color_mode: int = 1,
        text_color: Tuple[int, int, int] = (255, 0, 0),
        text_bg_mode: int = 0,
        text_bg_color: Tuple[int, int, int] = (0, 255, 0),
    ) -> bytearray:
        """Constructs a packet with the settings and bitmaps for iDotMatrix devices.

        Args:
            text_bitmaps (bytearray): bitmap list of the text characters
            text_mode (int, optional): Text mode. Defaults to 0. 0 = replace text, 1 = marquee, 2 = reversed marquee, 3 = vertical rising marquee, 4 = vertical lowering marquee, 5 = blinking, 6 = fading, 7 = tetris, 8 = filling
            speed (int, optional): Speed of Text. Defaults to 95.
            text_color_mode (int, optional): Text Color Mode. Defaults to 1. 0 = white, 1 = use given RGB color, 2,3,4,5 = rainbow modes
            text_color (Tuple[int, int, int], optional): Text RGB Color. Defaults to (255, 0, 0).
            text_bg_mode (int, optional): Text Background Mode. Defaults to 0. 0 = black, 1 = use given RGB color
            text_bg_color (Tuple[int, int, int], optional): Background RGB Color. Defaults to (0, 0, 0).

        Returns:
            bytearray: _description_
        """
        num_chars = text_bitmaps.count(self.separator)

        text_metadata = bytearray(
            [
                0,
                0,  # Placeholder for num_chars, to be set below
                0,
                1,  # Static values
                text_mode,
                speed,
                text_color_mode,
                *text_color,
                text_bg_mode,
                *text_bg_color,
            ]
        )
        text_metadata[:2] = num_chars.to_bytes(2, byteorder="little")

        packet = text_metadata + text_bitmaps

        header = bytearray(
            [
                0,
                0,  # total_len placeholder
                3,
                0,
                0,  # Static header values
                0,
                0,
                0,
                0,  # Placeholder for packet length
                0,
                0,
                0,
                0,  # Placeholder for CRC
                0,
                0,
                12,  # Static footer values
            ]
        )
        total_len = len(packet) + len(header)
        header[:2] = total_len.to_bytes(2, byteorder="little")
        header[5:9] = len(packet).to_bytes(4, byteorder="little")
        header[9:13] = zlib.crc32(packet).to_bytes(4, byteorder="little")

        return header + packet

    def _ConstructBitMap(self, image: Image):
        """Converts screen images (16x32) to bitmap images suitable for iDotMatrix devices."""
        bitmap = bytearray()
        for y in range(32):
            for x in range(16):
                if x % 8 == 0:
                    byte = 0
                pixel = image.getpixel((x, y))
                byte |= (pixel & 1) << (x % 8)
                if x % 8 == 7:
                    bitmap.append(byte)
        
        return bitmap

    
    # Pack smaller characters together more tightly in the text module
    # Fix inspired by zhs628 https://github.com/derkalle4/python3-idotmatrix-client/issues/29#issue-2159220874
    def _StringToBitmaps(self,text: str,font_path: Optional[str] = None, font_size: Optional[int] = 20) -> bytearray:
        font_path = font_path or "./fonts/Rain-DRM3.otf"
        font_size = font_size or 20
        font = ImageFont.truetype(font_path, font_size)

        char_images = []
        bbox = font.getbbox("6") # :TODO: should figure out how to get good widths
        
        char_width = bbox[2] - bbox[0]
        ascent, descent  = font.getmetrics()
        char_height = ascent + descent  
        
        total_width = 0
        for c in text: # :TODO: should support variable widths 
            char_image = Image.new("1", (char_width, 32), 0)            
            draw = ImageDraw.Draw(char_image)
            draw.text((0, 0), c, fill=1, font=font)
            char_images.append(char_image)
            total_width = total_width + char_width 

        # Make the width of final image evenly divisible by 16
        padded_width = total_width + (-total_width % 16) 
        
        width, height = char_images[0].size

        full_image = Image.new('1', (padded_width, 32), color=0)  # 0: black
    
        x = 0
        y =  (16 - char_height // 2) # Center text vertically

        for i, char in enumerate(char_images):
            full_image.paste(char, (x, y))
            x = x + width

        left = 0
        i=0
        results = []

        while left < padded_width:
            result = full_image.crop((left, 0, left+16, 32))
#            result.save(f"characters_%s.png"%i)
            i = i + 1
            results.append( self._ConstructBitMap(result) )
            left = left + 16

        bytestream = bytearray()
        
        for bitmap in results:
            bytestream = bytestream + b"\x05\xff\xff\xff" + bitmap
        
        return bytestream
    
