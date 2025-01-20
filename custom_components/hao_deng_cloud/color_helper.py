import math


def hsl_to_rgb(hue: int, saturation: float, luminosity: float):
    """Converts HSL color values to RGB color values."""

    if not 0 <= hue <= 360:
        raise ValueError("Hue value must be between 0 and 360")
    if not 0.1 <= saturation <= 1.0:
        raise ValueError("Saturation value must be between 0.1 and 1.0")
    if not 0.1 <= luminosity <= 1.0:
        raise ValueError("Luminosity value must be between 0.1 and 1.0")

    hue /= 360
    if luminosity <= 0.5:
        q = luminosity * (1 + saturation)
    else:
        q = luminosity + saturation - luminosity * saturation
    p = 2 * luminosity - q
    r = _hue_to_rgb(p, q, hue + 1 / 3)
    g = _hue_to_rgb(p, q, hue)
    b = _hue_to_rgb(p, q, hue - 1 / 3)
    return (round(r * 255), round(g * 255), round(b * 255))


def _hue_to_rgb(hue, q, t):
    """Helper function for hsl_to_rgb."""
    if t < 0:
        t += 1
    if t > 1:
        t -= 1
    if t < 1 / 6:
        return hue + (q - hue) * 6 * t
    if t < 1 / 2:
        return q
    if t < 2 / 3:
        return hue + (q - hue) * (2 / 3 - t) * 6
    return hue


def get_rgb_distance(rgb1, rgb2):
    """Get the 'distance' between two RGB colors."""
    r1, g1, b1 = rgb1
    r2, g2, b2 = rgb2
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
