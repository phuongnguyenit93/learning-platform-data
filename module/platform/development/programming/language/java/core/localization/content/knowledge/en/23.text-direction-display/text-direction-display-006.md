# Fonts, Glyphs, and Why Correct Encoding Does Not Guarantee Correct Display

## 1. The problem: Unicode is right, yet the screen still shows boxes

A Java application can read a UTF-8 file accurately, preserve the `String`, keep Vietnamese diacritics intact, and still display symbols like `□`, `�`, empty boxes commonly called *tofu*, misaligned diacritics, disconnected Arabic letters, or emojis split into multiple icons.

These are two different questions:

1. **Has the data been decoded into the right Unicode characters?** This is a matter of encoding/decoding, code points, and transmitting/storing strings.
2. **Can the display system turn those characters into the right shapes?** This is a matter of fonts, glyphs, glyph mapping, *text shaping*, *bidirectional layout*, rasterization, and the rendering environment.

Reading UTF-8 bytes properly **only completes the beginning of the pipeline**. Nothing in `StandardCharsets.UTF_8` guarantees that the user's machine has a font containing glyphs for every character, that the font can join Arabic letters, or that the renderer supports multi-code-point emojis.

A high-level pipeline:

```text
Bytes in file/network
      │ decode with the right charset
      ▼
Java String (UTF-16 code units)
      │ understand code points, normalization, combining characters
      ▼
Text segmentation + text direction + script/language runs
      │ select font, font fallback, shaping
      ▼
Glyph IDs + glyph positions + advance/metrics
      │ rasterize / draw by DPI, color, anti-aliasing
      ▼
Characters seen by the user on screen/PDF/image
```

Each layer can produce different errors. If Unicode data is already right and a font lacks a glyph, **switching UTF-8 to another encoding is not the right fix**. If the font has all the characters yet fails to handle shaping/text direction, picking a different charset will not make the text display properly either.

## 2. Distinguishing code points, UTF-16, grapheme clusters, and glyphs

These four concepts are easily confused when handling localization in Java:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Unicode code point** | A Unicode code unit value, commonly written `U+XXXX` | `U+1F600` is 😀 |
| **UTF-16 code unit** | A 16-bit `char` unit in a Java `String` | 😀 occupies **two** code units (a surrogate pair) |
| **Grapheme cluster** | A user-perceived character unit; can consist of multiple code points | `e` + combining acute accent usually looks like one `é` |
| **Glyph** | The actual visual shape chosen by the font/rendering engine to draw | A ligature can be one glyph for multiple code points; one code point can have contextual glyph forms |

**One code point does not necessarily equal one glyph**; nor is one grapheme always one code point. Several important examples:

- The letter `é` can be `U+00E9` (precomposed) or `U+0065 U+0301` (`e` plus a combining acute accent). Both strings can look nearly identical, yet differ in UTF-16 length and `String.equals` before normalization.
- The emoji 😀 is one non-BMP code point, yet `String.length()` returns **2** in Java.
- Family emojis, flags, and variant emojis can consist of multiple code points, variation selector `U+FE0F`, zero-width joiner `U+200D`, or regional indicator pairs. Whether they appear as a single symbol depends on the font/renderer.
- In Arabic script, a letter's shape can change based on position and neighboring letters; character sequences can be joined/shaped into different glyphs.
- For scripts with combining marks, mark placement is calculated from glyph metrics and shaping; merely checking whether a font can "display each code point individually" is not enough.

**Do not use `String.length()` to conclude how many characters the user sees.** Java provides `String.codePointCount(...)` to count code points, yet even that count is still not equivalent to the number of grapheme clusters or rendered glyphs.

## 3. Encoding and fonts solve two separate problems

### 3.1. UTF-8/UTF-16 are data encodings

UTF-8 describes how Unicode is represented as bytes; Java `String` uses a sequence of UTF-16 code units. When reading resources from files or the network, you must know the **actual charset of the source**:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
```

This snippet requires importing `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`, with variable `path` supplied; it is not a complete program.

If decoded wrongly, data in `String` is already corrupted and can show "mojibake" like `Tiáº¿ng Viá»‡t`. In that case, inspect the input stream's bytes and charset rather than rushing to change fonts.

If decoded properly, you can inspect code points, perform `String.equals`, `Normalizer`, and other Java operations. Yet Unicode **does not bind a final visual shape** for every character to a specific font.

### 3.2. Fonts supply glyphs and display instructions

A font can contain:

- A mapping table from character codes to glyphs (typically via an OpenType/TrueType `cmap` mechanism).
- Glyph shapes as outlines or bitmap/color data.
- Measurements (*metrics*) such as ascent, descent, advance, and kerning.
- Shaping/positioning feature tables (such as OpenType GSUB/GPOS), which can be required for ligatures, combining marks, and complex scripts.

If a font lacks an appropriate glyph, the system can:

1. Try an alternate font (*font fallback*) that supports the character.
2. Render a `missing glyph` placeholder — often looking like a box.
3. Skip the character, render improperly, or pull a glyph from another font with mismatched metrics.

**A missing glyph does not mean UTF-8 bytes are corrupted.** Use code point and font coverage diagnostics to locate which layer failed.

### 3.3. A glyph ID is not a Unicode code point

A renderer typically generates internal font **glyph IDs** after mapping/shaping. A glyph ID is meaningful only within the scope of that font and shaper; you must never store it in place of Unicode text or send it over a protocol as a character identifier.

For instance, a ligature feature can turn the three-character sequence `f`, `f`, `i` into the `ﬃ` glyph when rendered. The source string remains `ffi` if entered that way. Conversely, one Unicode character can use multiple contextual glyph shapes in cursive scripts. Thus **glyph count is not fixed equal to code point count**.

## 4. Why might font fallback still fall short?

An application may choose `SansSerif` or `Dialog`, or physical fonts like `Arial`, `Noto Sans`, `Serif`. Distinguish:

- **Physical font:** a concrete font installed/bundled with the app. Glyph coverage depends on the font file and version.
- **Java logical font:** logical names such as `Dialog`, `DialogInput`, `SansSerif`, `Serif`, `Monospaced`; Java maps them to one or more physical fonts depending on the system.
- **Font fallback:** the mechanism that picks another font when the preferred font does not support the character or cluster being rendered. Fallback order and quality depend on OS, runtime, app, installed fonts, rendering engine, and script.

If a character cluster combines a base letter and a combining mark from **two different fonts**, the mark can drift out of alignment. If a multi-part emoji splits across fonts or the engine does not handle ZWJ sequences, the result can be separate icons instead of one emoji. Font fallback widens coverage, yet **does not guarantee proper shaping, layout, and emoji styling**.

Adding a font with enough glyphs is still not enough to guarantee:

- Proper support for the script's OpenType features.
- Accurate placement of combining marks.
- Proper bidirectional algorithm execution when mixing RTL and LTR.
- Intended color vs. monochrome emoji presentation.
- Identical line height and width across desktop, mobile, servers, or PDF export.

Therefore, **human visual testing** and real locale screenshots remain essential.

## 5. Java 17+ program: verify Unicode data before blaming the font

This example uses `String`, `Normalizer`, and `codePointCount` to verify properties **independent of installed machine fonts**.

Create the file **`UnicodeTextInspectionDemo.java`**:

```java
import java.text.Normalizer;
import java.util.Locale;

public class UnicodeTextInspectionDemo {
    public static void main(String[] args) {
        String precomposed = "\u00E9";
        String decomposed = "e\u0301";
        String emoji = "\uD83D\uDE00";

        System.out.println("precomposedLength=" +
                precomposed.length());
        System.out.println("decomposedLength=" +
                decomposed.length());
        System.out.println("rawEqual=" +
                precomposed.equals(decomposed));

        String normalizedA = Normalizer.normalize(
                precomposed, Normalizer.Form.NFC);
        String normalizedB = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("nfcEqual=" +
                normalizedA.equals(normalizedB));
        System.out.println("emojiUtf16Length=" +
                emoji.length());
        System.out.println("emojiCodePoints=" +
                emoji.codePointCount(0, emoji.length()));
        System.out.println("emojiFirstCodePoint=U+" +
                Integer.toHexString(
                        emoji.codePointAt(0)).toUpperCase(Locale.ROOT));
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 UnicodeTextInspectionDemo.java
java -cp . UnicodeTextInspectionDemo
```

**Deterministic** output, independent of fonts and GUI:

```text
precomposedLength=1
decomposedLength=2
rawEqual=false
nfcEqual=true
emojiUtf16Length=2
emojiCodePoints=1
emojiFirstCodePoint=U+1F600
```

**Interpretation:** two representations of `é` differ as Java code sequences yet match after NFC; an emoji has one Unicode code point while occupying two UTF-16 units. Nothing in this example confirms whether **the emoji can actually render on screen** — that is a separate check.

When logging for debugging, printing code points via `String.codePoints()` can be better than looking only at rendered text in a terminal. On a console, a font missing glyphs can still fail to display characters even when Java code points are right.

## 6. `Font.canDisplay` and `canDisplayUpTo`: checking glyph coverage

Java2D/AWT provides `java.awt.Font` for working with fonts. Relevant methods:

```java
boolean Font.canDisplay(int codePoint)
int Font.canDisplayUpTo(String text)
```

- `canDisplay(codePoint)` asks whether the font can provide a glyph for that **code point**.
- `canDisplayUpTo(text)` returns **`-1`** if the font reports it can display every character in the string under this check; otherwise, it returns the **UTF-16 index** of the first undisplayable character.
- Results depend on the chosen font and runtime environment.
- **A coverage check does not prove text shaping/mark placement/ZWJ sequences/bidirectional ordering will be right.**

Create the file **`FontCoverageDemo.java`**:

```java
import java.awt.Font;
import java.util.Locale;

public class FontCoverageDemo {
    private static void inspect(Font font, String label, String text) {
        int firstMissing = font.canDisplayUpTo(text);

        if (firstMissing < 0) {
            System.out.println(label + ": all code points supported"
                    + " according to Font");
        } else {
            int codePoint = text.codePointAt(firstMissing);
            System.out.println(label + ": first missing at UTF-16 index "
                    + firstMissing + ", U+"
                    + Integer.toHexString(codePoint)
                            .toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        Font font = new Font("Dialog", Font.PLAIN, 20);

        inspect(font, "Vietnamese", "Tiếng Việt");
        inspect(font, "Arabic", "\u0645\u0631\u062D\u0628\u0627");
        inspect(font, "Emoji", "\uD83D\uDE00");
    }
}
```

Run:

```bash
javac -encoding UTF-8 FontCoverageDemo.java
java -cp . FontCoverageDemo
```

**Output is not fixed ahead of time:** machine A might report `all code points supported` on one line while machine B reports `first missing at UTF-16 index ...`. That difference is **expected behavior reflecting the font environment**, not a bug in the example.

Important notes:

1. `Dialog` is a **logical font** name, not necessarily a single physical font file.
2. `Font.canDisplayUpTo` returns a **UTF-16 position**, not a UTF-8 byte offset.
3. A font reporting support for all code points can still render **glyph clusters** incorrectly if the renderer lacks proper shaping/positioning.
4. For color emojis, `canDisplay` does not guarantee color, presentation style, or ZWJ combinations will look as designed.
5. If an app sends output to PDF, a browser, or an image service, the actual font and renderer of that output channel can differ from the environment running the check program.

### Does the font actually exist?

Constructing `new Font("FontName", Font.PLAIN, 20)` is not a strict check that a physical font file with that exact name is installed. Java may silently choose a default/fallback font. If you need to inspect the environment, use `GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames()` or the OS font manager, then test directly on the real runtime.

**Do not rely blindly on a font name in configuration.** Fonts can be silently substituted, especially on minimal Linux servers/containers.

## 7. Text shaping: having glyphs does not guarantee proper glyph layout

**Shaping** is the step that transforms a Unicode string into a **sequence of glyphs and glyph positions** matching writing-system rules. This step can determine:

- Initial/medial/final glyph forms when letters connect.
- Ligatures formed from multiple code points.
- Order and positioning of combining marks.
- Kerning and spacing adjustments.
- Script- or language-specific font features.

For example, Arabic usually needs joined glyph forms, while certain South Asian scripts have specialized consonant clusters and vowel-mark combinations. A renderer drawing **each `char` as an independent shape** can break those rules.

Approaches to avoid:

```java
// ANTI-PATTERN — do not use to draw multilingual sentences yourself:
for (int i = 0; i < text.length(); i++) {
    drawOneChar(text.charAt(i));
}
```

This is only **illustrative pseudocode**; `drawOneChar` is not a standard Java API. Iterating by `char` can also split an emoji's surrogate pair in half. More importantly, drawing one character at a time usually loses shaping and whole-cluster handling.

For Java desktop, prefer appropriate **text components/layout engines**; when precise positioning in Java2D is needed, you can use `java.awt.font.TextLayout` and `Graphics2D`. `Graphics2D.drawString` also uses Java2D text handling, yet when building a custom renderer avoid algorithms that place characters manually one by one. In particular, test RTL and complex strings on the exact JDK/OS where the app runs.

### You cannot deduce glyph count from code point count

A ligature may require fewer glyphs than code points; a combining mark may use a separate glyph positioned over a base letter; a multi-code-point emoji can become one glyph or multiple glyphs. Hence comparing `GlyphVector.getNumGlyphs()` with `text.length()` is solely **diagnostic**, never a condition meaning "renders right if equal."

## 8. Localization and bidirectional text (BiDi)

Vietnamese/English are read primarily left-to-right (*left-to-right*, LTR). Arabic and Hebrew have a primary writing direction of right-to-left (*right-to-left*, RTL). A single string can mix:

```text
RTL content + product code ABC-123 + number 2026 + punctuation
```

Character order in a `String` (*logical order*) and display order on screen (*visual order*) do not always match. The Unicode Bidirectional Algorithm (BiDi) handles how RTL/LTR segments are arranged.

Common mistakes:

- **Reversing the entire string** via `new StringBuilder(text).reverse()` to "support RTL." That can break numbers, emojis, combining marks, surrogate pairs, and logical order.
- Seeing an Arabic string with all code points intact and claiming RTL is supported. The layout engine still must resolve paragraph direction, digits, punctuation, and display order.
- Changing alignment to RIGHT without considering text direction, caret, icon placement, form structure, focus flow, or layout.
- Placing LTR data snippets such as URLs, IDs, or phone numbers inside an RTL sentence without testing punctuation and directional boundaries.

In Java, `java.text.Bidi` supports text-direction analysis. Some Swing components can apply `ComponentOrientation.RIGHT_TO_LEFT`, yet **setting orientation alone is not enough to localize an entire UI**; individual components, renderers, and mixed-script text still need testing.

## 9. Java 17+ program: checking text direction independently of fonts

Create **`BidiInspectionDemo.java`**:

```java
import java.text.Bidi;

public class BidiInspectionDemo {
    public static void main(String[] args) {
        String arabic = "\u0645\u0631\u062D\u0628\u0627";
        Bidi bidi = new Bidi(
                arabic, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("arabicIsRightToLeft=" +
                bidi.isRightToLeft());
        System.out.println("arabicRunCount=" +
                bidi.getRunCount());
        System.out.println("sourceUtf16Length=" +
                arabic.length());
    }
}
```

Run:

```bash
javac -encoding UTF-8 BidiInspectionDemo.java
java -cp . BidiInspectionDemo
```

Output:

```text
arabicIsRightToLeft=true
arabicRunCount=1
sourceUtf16Length=5
```

For the all-Arabic string in the example, the algorithm identifies one RTL run. **This does not prove attractive or accurate glyphs exist in a font** — `Bidi` assists with direction analysis, not font coverage checking.

When mixing text of different directions, run count can grow and base direction can affect results. To verify real-world layout, feed strings containing numeric codes, punctuation, URLs, and Unicode isolates/embeddings per UI policy into the final rendering environment.

## 10. Java2D example: generating a multilingual text test image

If you need to inspect a renderer, you can generate a PNG image with Java2D and **open it in an image viewer**. This example does not rely on a visible Swing UI and requires no GUI window; it uses `BufferedImage`, `Graphics2D`, and `TextLayout`.

Create the file **`MultilingualPreviewDemo.java`**:

```java
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.font.TextLayout;
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;

public class MultilingualPreviewDemo {
    public static void main(String[] args) throws Exception {
        BufferedImage image = new BufferedImage(
                1000, 310, BufferedImage.TYPE_INT_RGB);

        Graphics2D graphics = image.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(
                    0, 0, image.getWidth(), image.getHeight());

            graphics.setRenderingHint(
                    RenderingHints.KEY_TEXT_ANTIALIASING,
                    RenderingHints.VALUE_TEXT_ANTIALIAS_ON);

            Font font = new Font("Dialog", Font.PLAIN, 30);
            graphics.setColor(Color.BLACK);

            String[] samples = {
                    "Tiếng Việt: Trường, Đặng, Nguyễn",
                    "Arabic: \u0645\u0631\u062D\u0628\u0627",
                    "Emoji: \uD83D\uDE00  Café"
            };

            float baseline = 65f;

            for (String sample : samples) {
                TextLayout layout = new TextLayout(
                        sample, font,
                        graphics.getFontRenderContext());
                layout.draw(graphics, 35f, baseline);
                baseline += 80f;
            }
        } finally {
            graphics.dispose();
        }

        boolean written = ImageIO.write(
                image, "png", new File("font-preview.png"));

        if (!written) {
            throw new IllegalStateException(
                    "PNG writer is unavailable");
        }

        System.out.println("Created font-preview.png");
    }
}
```

Compile/run commands:

```bash
javac -encoding UTF-8 MultilingualPreviewDemo.java
java -cp . MultilingualPreviewDemo
```

When the runtime has Java2D and a working PNG writer, console output:

```text
Created font-preview.png
```

The program creates `font-preview.png` in the current working directory. **The image has no single fixed pixel output**: it depends on physical/fallback fonts, JDK, OS, layout engine, anti-aliasing, and glyph data. Open the image and inspect each line; if you see boxes, disconnected glyphs, or shifted marks, diagnose the environment.

The example uses `TextLayout` to pass the **entire string** to the shaper instead of drawing one `char` at a time. It still **does not guarantee** all ZWJ emojis, colors, scripts, or font fallbacks render cleanly on every machine. Especially when deploying to servers/containers with no fonts installed, check the environment and font licenses before packaging.

### Watch spacing and clipping

Even when glyphs are right, text can suffer **clipping** if containers are too narrow, baseline/line height is insufficient, or the UI hardcodes a height suited to only one font. That is a layout bug, not an encoding bug. Test with tall/deep diacritics, large font sizes, zoom/accessibility settings, and varying translation lengths.

## 11. Display across Swing, JavaFX, browsers, and PDF is not identical

A Java application may send strings through multiple display systems:

| Channel | What to check |
| --- | --- |
| **Swing/AWT** | Logical/physical fonts, font fallback, `ComponentOrientation`, `TextLayout`, rendering hints, component layout and sizing |
| **JavaFX** | Fonts, text control rendering capability, shaping, font variants, layout direction, and runtime version |
| **Browser (web HTML returned by Java server)** | CSS `font-family`, web-loaded fonts, browser/OS font fallback, `dir`, Unicode BiDi, line breaks |
| **Server-rendered images** | Fonts installed on server/container, DPI, anti-aliasing, Java2D version, glyph coverage |
| **PDF generated by Java libraries** | Whether fonts are embedded/subsetted, character-mapping encoding, text extraction, PDF library's shaping/RTL support |

Do not assume that because **`JLabel` renders cleanly on Windows**, a PDF from a Linux server will also be right. Each channel uses different fonts and rendering engines. A Java server returning valid Unicode JSON cannot force a client browser to use a font with full glyph coverage.

For web UIs, a conceptual CSS example:

```css
.message {
  font-family: "Noto Sans", "Arial Unicode MS", sans-serif;
}
```

This is an **illustrative priority list**; it does not mean those fonts are installed or licensed on every machine; the browser will pick an available fallback. In production, identify fonts you are licensed to use that support the scripts your product requires, rather than writing font names and treating the requirement as done.

When using web fonts, also consider load performance, caching, CORS, subset files, `unicode-range` ranges (if any), font licensing, and unstyled-text state before fonts finish loading. Do not treat a `font-family` list as test coverage.

## 12. Font coverage, glyph shaping, and direction must be tested separately

A useful diagnostic workflow when someone reports "text turned into boxes":

1. **Inspect the data source:** where do bytes come from, and what charset is used for decoding/encoding? For UTF-8, check for replacement character `U+FFFD` or mojibake strings.
2. **Print actual code points:** use `String.codePoints()` and `U+...` codes; do not rely only on looking at text in logs/consoles because log fonts can also lack glyphs.
3. **Check Unicode representation:** precomposed letters vs. combining marks; are ZWJ/variation selectors present? Is normalization applied per policy?
4. **Identify the rendering channel:** AWT, Swing, JavaFX, browser, server-side image, PDF, or terminal; do not treat one channel's result as valid for another.
5. **Check the actual font used:** preferred font, fallback font, version, available font files, and permissions. Do not just check a font name in CSS/Java.
6. **Check code point support:** try `Font.canDisplay`/`canDisplayUpTo` when using Java2D; if glyphs are missing, pick a suitable font.
7. **Check shaping:** for Arabic, Indic scripts, combining marks, ligatures; test whole words/sentences instead of single characters.
8. **Check BiDi/layout:** for RTL content and mixed LTR codes, test punctuation, numbers, links, alignment, and navigation.
9. **Check line metrics and clipping:** containers, line height, ascent/descent, fallback fonts changing text height; test long translations.
10. **Compare environments:** JDK, OS, installed fonts, browser, headless/container, mobile devices; capture screenshots of failing environments.
11. **Inspect exported output:** actual PDF/images, not just IDE or desktop previews.
12. **Automate regression:** use representative string sets per script/locale and visual/screenshot checks where high-value, without replacing review by fluent speakers.

If code points in Java are right and the same text displays properly on machine A yet fails on machine B, that is strong evidence to investigate **fonts/renderer/environment** rather than changing encodings across the system. Still, compare input data in both environments before concluding.

## 13. Special bugs when displaying Vietnamese

Vietnamese diacritics are a good illustration that **correct encoding does not equal correct mark placement**:

- A single letter can carry multiple combining marks and needs a font or renderer that positions marks according to Vietnamese rules.
- Some fonts have base glyphs yet poor *mark positioning*; as a result, marks stack unevenly or collide with adjacent letters.
- Font fallback splitting between a base character and a diacritic can produce mismatched height, advance, or mark placement.
- `Đ/đ` are separate code points; they do not turn into `D/d` under NFC/NFD normalization.
- Data from IMEs or copy/paste may arrive in NFC or NFD forms while remaining linguistically valid. Canonical normalization makes comparison more convenient, yet does not fix mark positioning bugs by itself.
- Displayed string length via `String.length()` can differ from "letter count"; do not truncate UI text at an arbitrary `char` when text contains combining marks or surrogate pairs.

When choosing a font for a Vietnamese product, do not test only ASCII letters and one short word. Test groups like `ă`, `â`, `ê`, `ô`, `ơ`, `ư`, `đ`, along with all tone marks and uppercase forms. Check small/large font sizes, bold/italic, and places with fixed line height.

**Do not strip diacritics to avoid font bugs.** Turning `Tiếng Việt` into `Tieng Viet` loses linguistic information and is generally unacceptable as a localization workaround. Fix the font/renderer or font selection properly.

## 14. Emojis, variation selectors, and ZWJ sequences

A common cross-platform UI issue is emojis rendering inconsistently:

- Some code points have both a *text presentation* and an emoji presentation; a **variation selector** can suggest the display style.
- A person or family emoji can consist of multiple code points and `U+200D` (zero-width joiner).
- Regional indicator pairs can form a national flag emoji if the environment supports them.
- One machine has color fonts/renderers supporting composite glyphs; another may show monochrome shapes, split parts, or boxes.

`Font.canDisplayUpTo` returning `-1` is **not enough** to confirm an entire ZWJ sequence turns into one intended emoji. Test directly on target platforms.

In Java, step through code points properly when handling emojis:

```java
String emoji = "\uD83D\uDE00";
int count = emoji.codePointCount(0, emoji.length());
```

This snippet yields `count == 1`. Calling `emoji.charAt(0)` and displaying it alone grabs **half of a surrogate pair**, not a complete emoji.

Do not slice text, move a caret, or delete characters by subtracting an arbitrary single UTF-16 unit. For editing features, pay attention to **grapheme cluster boundaries**, especially with emojis, combining marks, and complex scripts.

## 15. BiDi in the UI: not just flipping alignment

When supporting Arabic/Hebrew, separate:

- **Paragraph direction:** is the outer component intentionally RTL or LTR?
- **Inner segment direction:** Arabic, Latin, numbers, and punctuation can each have different directions.
- **Logical order:** `String` stores data in textual order; do not reverse elements yourself for visual effect.
- **UI layout:** icons before/after labels, menus, breadcrumbs, navigation bars, carets, arrow keys, and focus order.
- **Untrusted content insertion context:** names/order IDs/URLs may need *isolation* so they do not disturb the direction of surrounding sentences.

For example, if an Arabic sentence contains `ABC-123`, the code segment should generally keep its internal LTR order. Calling `reverse()` on the whole string can corrupt the code and punctuation. Use **Unicode BiDi-capable layout** and platform isolation mechanisms where appropriate.

In Swing, `ComponentOrientation.RIGHT_TO_LEFT` helps some components/layouts adapt, yet does not replace testing rendering on every component. Custom graphics or directional icons still require individual handling; not every icon should be mirrored (logos, play icons, clocks... depend on design semantics).

## 16. When you need to bundle fonts with the application

Sometimes the target platform does not guarantee suitable fonts. A desktop/server application can bundle fonts or use a product-managed font distribution mechanism.

In Java2D, `Font.createFont` can load a font from a file/stream in supported formats. Conceptual example:

```java
// Snippet: requires a real font resource and license/permission to use.
try (InputStream stream =
        MyClass.class.getResourceAsStream("/fonts/app-font.ttf")) {
    if (stream == null) {
        throw new IllegalStateException("Font resource missing");
    }

    Font font = Font.createFont(Font.TRUETYPE_FONT, stream)
            .deriveFont(20f);
}
```

This snippet requires importing `java.awt.Font`, `java.io.InputStream`, and a `MyClass` class in the project; it is not a standalone program because the font resource is assumed to exist. Do not commit fonts into a repository or redistribute them unless the license permits it.

Before choosing to bundle fonts:

1. Verify the font includes the scripts, glyphs, variants, and shaping features the product needs.
2. Verify the renderer and OS actually use the intended font; adding a font to the classpath does not guarantee every text component/PDF/browser will pick it up.
3. Review licensing for distribution/embedding, including PDF subsetting and commercial apps.
4. Test line height, bold/italic styles, Unicode variation selectors, and fallback behavior.
5. If using multiple font families per script, define a consistent fallback strategy to avoid size and weight jumps within a single word.

In web applications, embedding/loading web fonts via CSS is a separate pipeline from `Font.createFont` on a Java server. Having a font on the Java server does not automatically supply it to the browser.

## 17. Do not mistake encoding errors for display errors

| Symptom | Common causes to check | Appropriate fix |
| --- | --- | --- |
| String becomes `Tiáº¿ng Viá»‡t` | Wrong charset during decode/encode at some layer | Check bytes, UTF-8, and pipeline configuration |
| String has `U+FFFD` starting from decode | Bad input bytes or decoder replaced undecodable data | Inspect byte source and decode error handling |
| Right code points yet boxes/tofu | Font lacks glyphs or fallback failed | Choose/install proper font, check `canDisplay`, test render |
| Vietnamese diacritics shifted/overlapping | Font metrics, shaping, mark positioning, fallback | Use a font and renderer supporting Vietnamese |
| Arabic letters fail to join properly | Script shaping or rendering one character at a time | Use a proper text layout engine |
| Hebrew/Arabic text with Latin codes has flipped punctuation | BiDi direction/isolation/layout | Fix paragraph direction and BiDi handling; do not reverse `String` |
| Emojis split into separate icons | Renderer/font does not handle ZWJ/variation sequences | Check emoji font, engine, and target device |
| Fails only on PDF export | Font embedding/subsetting or PDF engine | Check PDF library fonts and shaping support |
| Text clipped when switching locales | Long translations, font metrics, container size | Design flexible layouts, test accessibility font sizes |
| Fails only on container server | Missing font packages / different JDK/OS | Inspect image/deployment and installed fonts |
| `String.equals` differs despite identical look | Precomposed vs. decomposed Unicode, or homoglyphs | Choose an appropriate normalization/identity policy |
| Data displays fine yet fails to search | Different normalization, collation, or search index | Align comparison contracts; do not change encodings ad hoc |

The "causes" column lists **diagnostic leads**, not the sole conclusion for a symptom. For example, shifted marks can also come from CSS or layout bugs; inspect the specific environment.

## 18. Testing display across locales and environments

A localization test suite should cover multiple layers:

### 18.1. Data tests

- Decode/encode UTF-8 accurately on sample strings.
- Inspect code points in `String` by `U+...` values.
- Ensure no accidental slicing inside surrogate pairs or grapheme clusters.
- Verify normalization policy if the app needs canonical matching; do not blindly normalize data where exact form is meaningful.

### 18.2. Font and shaping tests

- Font coverage for every supported script: Vietnamese, Arabic, Hebrew, Hindi, Thai, CJK if shipped by the product.
- Combining marks, ligatures, joined letters, glyph variants, ZWJ emojis, non-BMP characters.
- Small/large font sizes, bold/italic, zoom, high-DPI, fallback font changes.
- Realistic words and sentences, not only isolated character charts.

### 18.3. Direction and layout tests

- LTR, RTL, and mixed paragraphs.
- Numbers, URLs, order codes, punctuation inside RTL sentences.
- Alignment, input caret, selection, copy/paste, keyboard navigation.
- Labels, buttons, tooltips, dialogs, error messages, long text.
- Varying translation lengths, stretchability/line wrapping.

### 18.4. Export channel and deployment tests

- Major desktop OSes: Windows/macOS/Linux if supported.
- Headless servers/containers, actual font inventory when rendering images.
- Target browsers and mobile devices if Java returns web content.
- PDF/image/print output if the feature exports files.
- Java runtime/JDK updates, font versions, and shaping engines.

### 18.5. Readability and accessibility tests

- Enable larger text sizes, UI scaling, high-contrast modes.
- Inspect mark placement and legibility at small sizes.
- Do not rely on a glyph/icon alone to convey meaning if screen readers cannot interpret it.
- For mixed-script content, test screen readers and reading in logical order.
- Consult native-speaker feedback when reviewing glyphs, text direction, and punctuation.

**No single Java assertion proves "looks great for every locale."** Automated tests verify encoding/code points; `canDisplay` hints at coverage; screenshot tests and real reviews evaluate what users actually see.

## 19. Frequently asked questions

**The file is saved as UTF-8, so why are there still boxes?**

UTF-8 solves byte encoding. If the `String` already contains the right code points, boxes usually point to fonts, fallback, or the renderer. Analyze each layer instead of changing charsets at random.

**Does `Font.canDisplayUpTo(text) == -1` prove every character will look good?**

No. The result indicates the font reports support for those code points under that check; it does not guarantee shaping, mark placement, ligatures, color emojis, text direction, layout width, or PDF rendering.

**Does using `Dialog` mean the font always has every character?**

No. It is a logical font that maps to different physical fonts depending on the runtime/OS. Actual display depends on installed fonts and fallback behavior.

**Does `Normalizer.normalize(text, NFC)` fix a font missing glyphs?**

No. NFC converts canonically equivalent representations into a consistent form. It may alter composition code points, yet does not install fonts or supply missing glyphs.

**Why does Arabic still fail to read properly when code points are right?**

Text shaping and BiDi layout are needed. Drawing individual code points independently or reversing strings manually can break letter joining and paragraph direction.

**Is an emoji a single Java `char`?**

Not necessarily. The emoji 😀 is one code point yet occupies two UTF-16 code units; composite emojis can span multiple code points and multiple code units.

**Do we need to merge all fonts into one giant font covering all of Unicode?**

Usually impractical. Systems use fallback/per-script font stacks; what matters is picking fonts, shaping engines, and fallback strategies that behave consistently and are verified on target platforms.

**Should we strip unfamiliar characters or convert them to ASCII?**

Not automatically. That can lose data/meaning, especially personal names and non-Latin scripts. If a business field only allows a restricted character set, define clear validation rules and error messages; never use rendering bugs as an excuse to alter user content.

## 20. Takeaways

- **Correct encoding does not guarantee correct display.** UTF-8/UTF-16 address Unicode representation; fonts and renderers handle glyphs, shaping, metrics, BiDi, and rasterization.
- **Code points, UTF-16 code units, grapheme clusters, and glyphs are not identical.** Avoid treating each `char` as one "user character."
- **Font coverage is necessary but insufficient.** `Font.canDisplay` and `canDisplayUpTo` help diagnose missing glyphs; shaping and rendered output still require testing.
- **Font fallback is not a uniform display contract** across Windows, Linux, macOS, Java2D, browsers, servers, and PDFs. Select fonts and configurations for each real output channel.
- **RTL text cannot be handled by manual string reversal.** Use a Unicode BiDi-aware engine/layout and test strings mixing Latin, numbers, and punctuation.
- **Do not use normalization to cure font bugs** and never strip user diacritics/Unicode characters just to avoid boxes.
- **Test across layers:** code points → font coverage → shaping → text direction → rendered image/screenshot/PDF on the deployment environment; combine automated checks with review by fluent readers.
