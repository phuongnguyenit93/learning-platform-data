# Translation Length, Line Wrapping, and UI Layer Responsibilities

## 1. Why is this a localization problem, not just CSS or LayoutManager?

In a multilingual application, the same meaning can be expressed by text segments of **widely varying lengths**. A short English label can become a much longer phrase when translated into German, French, or Vietnamese; another language may use fewer characters yet wider glyphs, or require a taller line height. These variations are not translation bugs.

Example labels serving the same purpose:

```text
en-US: Settings
vi-VN: Cài đặt
de-DE: Einstellungen
```

If a developer designs a button with a fixed width tailored strictly to `Settings`, the translation `Einstellungen` can overflow or get clipped. Shrinking the font size, forcing translators to abbreviate at all costs, or inserting `\n` into translations to fit current pixel bounds usually just **hides an inflexible UI design**.

**Key principle:** translators are responsible for **content, meaning, word order, and natural phrasing**; the UI layer and layout engine are responsible for **sizing, reflow, wrapping to fit the display area, text direction, and accessibility**. Both sides can coordinate via clear content constraints, but "patching the layout" must never become the translator's default job.

This lesson focuses on three topics:

1. **Translation length:** expansion/contraction, glyph-width differences, and line height.
2. **Line wrapping:** the difference between automatic line breaks and semantically meaningful newlines required by content.
3. **UI layer responsibilities:** adaptive layout, Unicode line breaking, RTL/BiDi, overflow testing, truncation, and accessibility.

The Java examples use **Java 17+**, particularly Swing to illustrate UI layer responsibilities; similar principles apply to web, mobile, and other UI technologies, though specific APIs will differ.

## 2. Character count does not determine translation width

You cannot multiply `String.length()` by a constant to calculate the pixels needed for display.

In Java:

- `String.length()` counts **UTF-16 code units**, not Unicode code points or glyphs.
- `String.codePointCount(0, s.length())` counts code points, yet one grapheme cluster can span multiple code points.
- Whether a font is **proportional** or **monospaced**, plus size, weight, kerning, ligatures, and text shaping all affect width.
- A CJK character, a Latin letter, combining marks, or a color emoji can each occupy different areas.
- Some scripts require enough line-height for tall diacritics or glyph extensions.
- An RTL paragraph mixing numbers and Latin needs a layout engine aware of the Unicode Bidirectional Algorithm (BiDi).

For example, `"WWWW"` and `"iiii"` both consist of four Latin letters, yet in many proportional fonts their widths differ dramatically. A string `"A🌍B"` has `length()==4` and `codePointCount()==3`, while rendered width is still determined by the font/renderer.

### Three frequently confused metrics

| Metric | What does it measure? | Enough to decide line breaks? |
| --- | --- | --- |
| `String.length()` | Number of UTF-16 code units | **No** |
| Code point/grapheme count | Unicode/user-perceived character units | **No**: lacks font, width, shaping |
| Post-layout dimensions | Glyph advance, wrapping, line-height, component space | **Directly relevant** yet depends on renderer and viewport |

If layout needs to know whether text fits, use **the UI framework's own text-measurement tools** once font, writing direction, screen scale, and display bounds are known. In Swing, `FontMetrics`/`TextLayout` can participate in measurement, while the layout manager remains responsible for allocating overall space. `FontMetrics.stringWidth` for a single line of text is not a universal solution for styled text, complex BiDi, or multi-line text with break opportunities.

### Java 17+ example: distinguishing UTF-16 and code points

Create the file `TextLengthDemo.java`:

```java
public class TextLengthDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F30D)) + "B";

        System.out.println("utf16=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("longer label length="
                + "Einstellungen".length());
    }
}
```

```bash
javac TextLengthDemo.java
java TextLengthDemo
```

Output:

```text
utf16=4
codePoints=3
longer label length=13
```

The example proves `char` count does not fully capture "translation length." It **does not** measure pixel width; to measure width you must pass the string to a concrete font and UI renderer.

## 3. Translation expansion/contraction: no fixed ratio

A short phrase can grow substantially after translation. A long sentence sometimes expands at a smaller ratio because grammatical structures differ. There is no reliable rule that "all translations are 30% longer than English" or "every field just needs +10px."

Contributing factors:

- **Word morphology:** one word in one language can become a multi-word phrase in another.
- **Politeness/register and context:** action buttons, error messages, assertions/questions, forms of address.
- **Noun classifiers, gender/case/plurals:** the entire sentence shifts, not just one suffix.
- **Characters and fonts:** glyph count and each glyph's width have no linear relationship to byte or `char` length.
- **Text direction:** LTR/RTL layouts can change icon placement, back buttons, arrows, and component order.
- **Number/date-time locales:** `1,234.5` can become `1.234,5`, another digit system, or a longer date string.
- **Screen width and accessibility:** larger text, DPI, zoom, font fallback, small devices, or narrowed windows.

**Designs should test both expansion and contraction cases**, not just average lengths. Using pseudo-localization to deliberately lengthen strings and add accented characters helps catch clipped components early before real translations arrive.

### A good placeholder policy

Messages should store **complete sentences** with meaningful placeholders rather than concatenating fixed fragments:

```properties
files.count={0} files selected
save.error=Could not save {0}
```

Translators have the freedom to reorder placeholders to fit grammar. Avoid:

```java
// Unsuitable if translation must reorder sentence structure:
String text = translate("prefix") + count
        + translate("suffix");
```

A complete message enables accurate translation, yet **does not guarantee automatic line wrapping**: that remains the component/layout's responsibility.

## 4. Line wrapping: automatic line breaks vs. meaningful newlines

Separate two kinds:

### 4.1. Soft wrap / automatic line break

When a piece of text exceeds available width, the UI can find a **break opportunity** and display the continuation on a new line. Break points can change when:

- the window is widened or narrowed;
- the language changes;
- font size/zoom changes;
- a device rotates from portrait to landscape;
- the user enables accessibility scaling;
- font fallback or ligatures change.

Soft wrap **does not alter the source string's content**. Reading text from the data model does not necessarily show `\n` characters at visually wrapped positions.

### 4.2. Hard break / intentional newline

An actual `\n` character present in the content. It can carry **semantic meaning**:

- separating paragraphs;
- multi-line address blocks;
- poetry, quotes, structured captions;
- separating a title and description when required by content specification.

Hard breaks must be **decided by the content model**, not just to squeeze a string into a 120px-wide button. If a translator inserts `\n` mid-sentence to work around a layout bug, wider screens will still force an awkward line break.

### 4.3. Responsibility table

| Scenario | Who should handle it? |
| --- | --- |
| Measuring whether text fits a button | UI/layout |
| Adapting width and line count to the viewport | UI/layout |
| Choosing line-break points valid for writing-system rules | Text engine/line-break algorithm |
| Choosing natural wording, sentence order, grammar | Translator/content |
| Content genuinely consists of two paragraphs | Content structure/resources |
| Very short button needing a dedicated approved label | Product design + content; resource has a short variant |
| Clipped text or icon overlapping text | UI/layout, without asking translators to drop essential info |
| Overly long text field from user input | UI with overflow/truncation policy and access to full content |

Sometimes a product has both a **full label** and a localized **short label**, such as for a narrow tab bar. In that case, they are **two intentionally designed resources**, not arbitrary chopping of one translation.

## 5. Line-breaking rules differ across writing systems

You cannot call `text.split(" ")` and treat every space as a valid word boundary or line-break boundary. W3C and Unicode describe many mechanisms:

- **English and many Latin/Cyrillic languages:** generally break at word boundaries and spaces, though punctuation and brackets still have rules.
- **Vietnamese:** spaces can separate **syllables**, not always whole words; natural line wrapping also depends on editorial phrasing and sentence structure.
- **Thai, Khmer, Lao:** many words are not separated by spaces; line breaking can require dictionary-based segmentation.
- **Chinese/Japanese:** can break between characters/syllables, yet rules such as **kinsoku shori** restrict placing certain punctuation marks at the start/end of a line.
- **Scripts with combining marks and complex clusters:** must not break inside a grapheme cluster or orthographic syllable.
- **Arabic/Hebrew (RTL):** have word-breaking rules alongside BiDi visual ordering.

Non-breaking characters such as **NO-BREAK SPACE** `U+00A0`, **NARROW NO-BREAK SPACE** `U+202F`, and **WORD JOINER** `U+2060` can affect break opportunities. They often play roles in numbers, proper names, or punctuation; do not replace all of them with ASCII spaces before layout.

**Use the framework's text measurement + wrapping facilities** once verified to support target languages. Hand-rolled algorithms based on `char` counts or spaces easily break combining marks, ZWJ emojis, RTL, and prose grammar.

## 6. `BreakIterator.getLineInstance`: finding break opportunities without deciding final line counts

Java SE provides:

```java
BreakIterator iterator =
        BreakIterator.getLineInstance(locale);
iterator.setText(text);
```

This is code inside a method, requiring `import java.text.BreakIterator;` and variables `locale`, `text`. `BreakIterator` returns **boundary positions** for line-break opportunities, yet **has no knowledge of pixel widths**, has no font metrics, and **does not lay out lines on screen itself**.

To extract each slice between boundaries:

```java
int start = iterator.first();
for (int end = iterator.next();
        end != BreakIterator.DONE;
        start = end, end = iterator.next()) {
    String part = text.substring(start, end);
}
```

Both `start` and `end` are **UTF-16 offsets** in the source `String`. `BreakIterator.DONE` has value `-1`; check it before calling `substring`. The UI software combines these break opportunities with width measurement, shaping, and container bounds to decide which points actually become new lines.

### Java 17+ example: listing break opportunities only

Create the file `LineBreakOpportunitiesDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBreakOpportunitiesDemo {
    public static void main(String[] args) {
        String text = "Hello world again";
        BreakIterator it =
                BreakIterator.getLineInstance(Locale.US);
        it.setText(text);

        int start = it.first();
        for (int end = it.next();
                end != BreakIterator.DONE;
                start = end, end = it.next()) {
            System.out.println("[" + start + "," + end + ")="
                    + text.substring(start, end));
        }
    }
}
```

```bash
javac LineBreakOpportunitiesDemo.java
java LineBreakOpportunitiesDemo
```

Stdout verified against `Locale.US` data:

```text
[0,6)=Hello 
[6,12)=world 
[12,17)=again
```

Here `[0,6)` includes the space after `Hello`, and `[6,12)` includes the space after `world`. These slices are **units from line-break analysis**, not three final UI lines. In a wide container, the whole string fits on one line; in a narrow container, it can wrap into multiple lines.

**Do not save newlines computed from `BreakIterator` back into translated content** just because of one viewport's layout; next time the font/window changes, break points can differ.

## 7. What is the UI framework responsible for?

So that a long translation still displays completely, the UI layer must manage:

1. **Flexible layout:** prefer component-requested sizes, sensible min/max bounds, and layout managers; never hardcode the same width for every locale.
2. **Appropriate wrapping:** allow multi-line text where semantics and space permit.
3. **Adaptive height:** when text wraps to two/three lines, let the container grow vertically instead of clipping it.
4. **Spacing:** padding, icon-to-text gaps, baseline alignment, line height; recompute after font/locale changes.
5. **Overflow/truncation policy:** when space is strictly constrained, distinguish where wrapping, scrolling, collapsing, or ellipsis is allowed and where clipping is forbidden.
6. **Text direction:** configure LTR/RTL on components/layouts, never reverse raw strings.
7. **Accessibility:** honor larger text sizes; ensure a path to read full content (screen readers, expanded views, appropriate accessible descriptions).
8. **Reflow:** when locale, DPI, font, or window size changes, recompute layout; never cache the width of the English translation.
9. **Input text:** user-entered content can be very long and contain emojis/combining marks/RTL; do not assume only resource strings need handling.
10. **Visual testing:** test short translations, long translations, other scripts, and realistic viewports.

These principles belong to the **presentation layer**. Resource bundles store linguistic data and should not hold pixel numbers, scroll states, component dimensions, or layout-decision logic.

## 8. Java Swing: `JLabel` is not equivalent to `JTextArea`

In Swing, component selection directly affects wrapping.

| Component | Key behavior | When to consider |
| --- | --- | --- |
| `JLabel` | Normally displays **a single line of plain text**; does not wrap long text by width like a text area | Short labels, headings with ample space |
| `JTextArea` | Multi-line text; `setLineWrap(true)` wraps by width; `setWrapStyleWord(true)` prefers word boundaries | Multi-line descriptions / plain prose |
| `JTextPane` / `JEditorPane` | Styled/rich text content, more flexible layout capabilities | Complex formatted content |
| `JScrollPane` | Provides a scrollable viewport when content exceeds available bounds | Long content that must remain fully readable |
| `JButton` | Action button, sized per Look & Feel/font | Buttons with short labels designed and tested |

`JTextArea.setLineWrap(false)` is the default for `JTextArea`. If text must wrap automatically inside a width-constrained area, enable wrapping and ensure the component actually receives a **sensible layout size**.

Note that `setWrapStyleWord(true)` prefers word boundaries where possible, yet is **not a complete guarantee** of every line-breaking rule across all scripts/Unicode and all Look & Feels. For complex international UIs, test thoroughly or use an appropriate text layout engine.

### Java 17+ example runnable even in headless environments

Create the file `SwingWrapConfigurationDemo.java`:

```java
import java.awt.ComponentOrientation;
import java.util.Locale;
import javax.swing.JLabel;
import javax.swing.JTextArea;

public class SwingWrapConfigurationDemo {
    public static void main(String[] args) {
        String message = "Save changes before closing";

        JLabel label = new JLabel(message);
        JTextArea area = new JTextArea(message);

        System.out.println("label text: " + label.getText());
        System.out.println("default wrap: " + area.getLineWrap());

        area.setLineWrap(true);
        area.setWrapStyleWord(true);
        area.setEditable(false);
        System.out.println("wrap enabled: " + area.getLineWrap());
        System.out.println("word wrap enabled: "
                + area.getWrapStyleWord());

        Locale arabic = Locale.forLanguageTag("ar-EG");
        area.setComponentOrientation(
                ComponentOrientation.getOrientation(arabic));
        System.out.println("arabic LTR: "
                + area.getComponentOrientation().isLeftToRight());
    }
}
```

```bash
javac -encoding UTF-8 SwingWrapConfigurationDemo.java
java SwingWrapConfigurationDemo
```

Stdout:

```text
label text: Save changes before closing
default wrap: false
wrap enabled: true
word wrap enabled: true
arabic LTR: false
```

This example **verifies component properties** without displaying a window. It does not prove a specific number of lines will render, because wrapping depends on **allocated width**, fonts, and the layout manager.

**Important:** `setEditable(false)` only makes the text non-editable; for a text area acting as a descriptive label, you may also need to configure background, border, focus, accessible name, and text-selection policy per design requirements. Do not treat it as an "action button" merely because it displays text.

## 9. Swing UI example: letting text adapt to layout

A complete example using `BorderLayout` and a wrapping `JTextArea` instead of pinning translation width in resources. Create `LocalizedPanelDemo.java`:

```java
import java.awt.BorderLayout;
import java.awt.ComponentOrientation;
import java.awt.Dimension;
import java.util.Locale;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingUtilities;

public class LocalizedPanelDemo {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            Locale locale = Locale.forLanguageTag("vi-VN");
            String description =
                    "Vui lòng kiểm tra các thay đổi của bạn trước khi "
                    + "đóng cửa sổ. Nội dung có thể tự xuống dòng "
                    + "khi người dùng thu hẹp cửa sổ.";

            JFrame frame = new JFrame("Localization layout");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

            JTextArea message = new JTextArea(description);
            message.setEditable(false);
            message.setLineWrap(true);
            message.setWrapStyleWord(true);
            message.setOpaque(false);
            message.setBorder(null);

            JPanel content = new JPanel(new BorderLayout(12, 12));
            content.setBorder(
                    javax.swing.BorderFactory.createEmptyBorder(
                            16, 16, 16, 16));
            content.add(new JScrollPane(message),
                    BorderLayout.CENTER);
            content.add(new JButton("Đóng"), BorderLayout.PAGE_END);

            content.applyComponentOrientation(
                    ComponentOrientation.getOrientation(locale));

            frame.setContentPane(content);
            frame.setMinimumSize(new Dimension(240, 180));
            frame.setSize(460, 250);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
```

Run in an environment **with a graphical UI**:

```bash
javac -encoding UTF-8 LocalizedPanelDemo.java
java LocalizedPanelDemo
```

The program opens a Swing window; there is no fixed stdout. When narrowing the window, the text area can wrap to the center region's width, and `JScrollPane` keeps content readable if it exceeds available space. The code runs on the **Swing Event Dispatch Thread (EDT)** via `SwingUtilities.invokeLater`.

**Important limitations of the example:** a production UI needs additional accessibility handling, keyboard navigation, font fallback, runtime locale switching, a resource bundle instead of hardcoded Vietnamese, a button with an actual action, and testing on the target Look & Feel. Do not treat a single-window illustration as a complete production layout suite.

**Do not fix one height for all labels** just because the example sets an initial window size. That size is an initial default, not the maximum length of translated sentences. If a product needs a non-scrolling layout, pick components/containers that can grow vertically with line count and re-test.

## 10. `JLabel`, HTML, and practical limitations

A plain-text `JLabel` is normally single-line. Swing can render a **subset of HTML** in certain components when text begins with `<html>`, for instance:

```java
JLabel label = new JLabel(
        "<html>This is a description<br>with a line break.</html>");
```

This is an **illustrative snippet inside a method**, requiring `import javax.swing.JLabel;`. Here `<br>` is an HTML tag interpreted by Swing's HTML renderer, not `\n` in a plain resource.

However, never take user-entered or untrusted translations and interpolate them directly into HTML: escaping/validation must match the rendering model. Pushing `<br>` and styling into translation strings also mixes **content semantics** with **presentation specifics**, raising maintenance costs.

If you need automatic width-based wrapping and vertical growth in Swing, usually prefer multi-line components/suitable layouts instead of injecting countless `<br>` tags into `JLabel`. When using HTML, test the tag subset supported by Swing and how layout updates, as it is not a modern web browser.

## 11. Separating language resources from layout decisions

Resource bundles should describe **prose and content variants**, not store newline-injected copies tailored to one screen size:

```properties
dialog.close.title=Đóng cửa sổ
dialog.close.description=Vui lòng lưu các thay đổi trước khi đóng.
dialog.close.action=Đóng
```

In the UI:

- `title` goes into an appropriate heading or label.
- `description` uses a component capable of wrapping.
- `action` is a button label with flexible sizing and event handling.
- Number, date/time, and proper-name placeholders are formatted by locale before entering the UI.

This is a Vietnamese `.properties` example illustrating key structure; in practice, bundle names and locale suffixes are decided by the project.

### When should a translation contain `\n`?

There are cases where **content requires fixed line breaks** as part of its meaning. For example, a multi-paragraph greeting, a message intentionally structured into two paragraphs, or a multi-line postal address. In `.properties`:

```properties
message.long=Đoạn thứ nhất.\nĐoạn thứ hai.
```

The `.properties` parser turns `\n` escapes into newlines in the Java string. The UI layer must use a multi-line component; a plain-text `JLabel` does not become a text area just because the string contains `\n`.

Do not insert `\n` escapes between word groups merely to enforce "20 characters per line," because fonts, languages, and viewports change.

**Distinguish semantic structure from visual lines:** content should use paragraph/list fields when structure is needed, while the final line count is a layout outcome. For text appearing in multiple UI contexts, consider distinct keys/resources with clear purposes rather than sharing one string and swapping newlines per call site.

## 12. Placeholder scenarios, plurals, and sudden length spikes

Not only static translations—messages with runtime data can also grow unexpectedly long:

```text
"Document saved"
"Document saved Quarterly Business Summary Report Q4..."
```

Filenames, person names, paths, email addresses, order codes, or monetary amounts can stretch text beyond expectations. Systems must also account for:

- filenames with CJK characters and no spaces;
- list counts and very long proper names;
- dates formatted with full month names;
- plural/gender sentence templates shifting with runtime arguments;
- escaped text or markup altering size if rendered differently.

For instance, `ResourceBundle` + `MessageFormat` can produce semantically accurate text; it **is not responsible for choosing break points and button widths**. Message formatters should build **meaningful strings**, while the layout layer analyzes and renders them.

Set **domain-level data limits** (e.g., max N graphemes/bytes on an entered name if justified) rather than placing arbitrary limits on translation resources. If the UI cannot display everything, define an explicit overflow policy for that content type.

## 13. RTL: do not reverse strings and do not hardcode icon positions

A multilingual UI may serve Arabic or Hebrew, written right-to-left (RTL). The UI layer's responsibility here goes beyond line wrapping.

- Paragraph direction and mixed LTR/RTL runs follow the Unicode Bidirectional Algorithm.
- Elements such as back navigation, directional icons, and field ordering may need mirroring per the design system.
- Numbers, URLs, product codes, and Latin words inside an RTL segment need a text shaping/BiDi engine.
- Never apply `new StringBuilder(text).reverse()` to "support RTL."
- Do not sprinkle BiDi control characters into resources indiscriminately when the framework already provides direction mechanisms; when embedding data of unknown direction, apply platform-appropriate bidi isolation.

Swing provides `java.awt.ComponentOrientation`:

```java
Locale locale = Locale.forLanguageTag("ar-EG");
ComponentOrientation orientation =
        ComponentOrientation.getOrientation(locale);
component.applyComponentOrientation(orientation);
```

This is an illustrative snippet inside a method, requiring `Locale` and `ComponentOrientation` along with a declared `component`.

**Note:** `ComponentOrientation` configures component layout orientation, yet does not guarantee every text string, icon, tooltip, popup, and layout manager automatically works right for RTL. Test directly with your UI library and active Look & Feel.

### Java 17+ orientation example

Create the file `OrientationDemo.java`:

```java
import java.awt.ComponentOrientation;
import java.util.Locale;

public class OrientationDemo {
    public static void main(String[] args) {
        for (String tag :
                new String[] {"en-US", "vi-VN", "ar-EG", "he-IL"}) {
            Locale locale = Locale.forLanguageTag(tag);
            boolean ltr = ComponentOrientation
                    .getOrientation(locale).isLeftToRight();
            System.out.println(tag + ": " + ltr);
        }
    }
}
```

```bash
javac OrientationDemo.java
java OrientationDemo
```

```text
en-US: true
vi-VN: true
ar-EG: false
he-IL: false
```

This reflects only **component orientation for a locale** in Java; it is not a substitute for rendering a mixed-script BiDi paragraph.

## 14. Truncation / ellipsis: a fallback, not the default

Some screens genuinely have tight area limits: tab bars, charts, narrow table columns, short toasts. There, an app may truncate text and append `…`, provided a clear policy exists.

### 14.1. Risks of slicing by `char`

`String.substring(0, maxLength)` slices by **UTF-16 code units**, which can corrupt a supplementary emoji if cut mid-surrogate-pair. Even `offsetByCodePoints` only avoids splitting surrogates and can still split a **grapheme** consisting of a base letter with combining marks, a ZWJ emoji, or a skin-tone modifier.

If the requirement is slicing by "user-perceived characters," choose a grapheme segmentation algorithm. Java 17 supports the `\X` regex for extended grapheme clusters; written `"\\X"` in a Java string literal. For apps with **pixel** limits, you still must measure width after shaping and wrapping, not just count graphemes.

### 14.2. Measuring pixels and choosing cut points

Conceptual workflow:

1. Measure text dimensions using the exact font, DPI scale, text direction, renderer, and viewport.
2. If it fits, display verbatim.
3. If it does not fit and the component allows multiple lines, prefer wrapping.
4. If wrapping is disallowed, consider scrolling, expanding, or ellipsis.
5. If using ellipsis, cut at an appropriate Unicode boundary and **re-measure** the full `prefix + ellipsis` string.
6. For RTL/BiDi, ellipsis direction and cut placement must be handled properly by the framework/UX.
7. Keep full content accessible if the information is important; a tooltip is a supplementary channel, not the sole mechanism.

**Never truncate critical information** such as legal terms, safety warnings, monetary amounts, actionable errors, or action buttons that could be misread. For essential labels that do not fit, redesign the layout/label instead of clamping them to 8 characters in code.

### 14.3. A grapheme-safe snippet

```java
static String truncateClusters(String s, int maxClusters) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("maxClusters");
    }
    java.util.regex.Matcher m =
            java.util.regex.Pattern.compile("\\X").matcher(s);
    int end = 0;
    int count = 0;
    while (count < maxClusters && m.find()) {
        end = m.end();
        count++;
    }
    return s.substring(0, end);
}
```

This is an **illustrative method** to be placed inside a Java class. It returns a prefix of at most N grapheme clusters according to the JDK's Unicode data, **without adding an ellipsis** and **without measuring pixels**. Using `m.end()` to slice the `String` yields a UTF-16 offset compatible with `substring`.

Note: if `maxClusters==0` the result is an empty string; if the text has fewer clusters than the limit, the whole text is returned. Unicode/grapheme rules can be updated across runtime releases, so test carefully when character limits are an important product contract.

## 15. Unicode line breaking and the difference between "characters" and "segments"

To understand the text engine's responsibilities, separate three concepts:

| Concept | Purpose | Common mistake |
| --- | --- | --- |
| Grapheme boundary | Never split a single visible character cluster | Cutting before a modifier/combining mark |
| Word boundary | Identify word/lexeme segments by locale | Treating every space as the only word boundary |
| Line-break opportunity | Legal place to wrap a line under script rules | Treating every opportunity as a mandatory newline |

A Unicode cluster cannot be split across lines even when made of multiple code points; conversely, a sentence can contain many line-break boundaries. A line-break engine must also respect punctuation forbidden at the start or end of a line. Some languages require hyphenation or dictionary segmentation.

In Java, `BreakIterator.getLineInstance(locale)` gives boundary positions, yet many UI frameworks have their own layout engines and final quality depends on engine/font/provider. **Do not try to pass `\n`-joined strings from the backend to "draw layout" for the frontend.**

## 16. Pseudo-localization testing and multiple UI sizes

Testing only English on a wide screen misses most bugs. A practical test plan should include:

| Test category | Test data | What to observe |
| --- | --- | --- |
| Short/long strings | 4-character labels and long prose | No overlap or improper truncation |
| Pseudo-localization | Expanded translation lengths, added accented chars | Container reflow |
| Font scaling | 100%, 150%, 200% | Content/actions are not obscured |
| Viewports | Wide, narrow, zoomed windows | Wrapping/scrolling/resizing |
| CJK | Chinese/Japanese, text without spaces | Line breaks, punctuation |
| Southeast Asia | Thai/Khmer, Vietnamese | Segmentation |
| RTL | Arabic/Hebrew, mixed Latin/numbers | Bidi, alignment, icon mirroring |
| Unicode | Combining marks, ZWJ emojis, flags | Grapheme-safe truncation |
| Dynamic data | Very long filenames/names/paths | Does not push buttons off-screen |
| Plurals/gender | Different branches in the same resource | Length shifts at runtime |
| Accessibility | Screen readers, keyboard-only, large fonts | Content remains reachable |
| Printing/export | PDFs/reports/UI screenshots | Line and page breaks do not cut wrongly |

**Pseudo-localization does not replace native-speaker review.** It is great for catching mechanical layout issues, while real translations must be reviewed for naturalness, grammar, and readability.

### Do not evaluate from screenshots on a single device alone

Fitting at one specific size does not mean layout passes. Test across multiple widths and font scales; if running automated UI screenshot tests, remember font fallback, anti-aliasing, DPI, and OS differences affect pixels. Combine automated layout constraints and accessibility checks rather than chasing pixel perfection for a single locale.

## 17. Suggested architecture: Domain → i18n → UI layout

```text
Domain values (count, date, username...)
             |
             v
i18n/message formatting:
  - Select resource by locale
  - Select plural/select branch
  - Format numbers/dates/times
  - Return complete message
             |
             v
UI text/layout engine:
  - Resolve font, direction, width, DPI
  - Compute line-break opportunities
  - Wrap, grow height/scroll, align baseline
  - Handle overflow/ellipsis if needed
             |
             v
Rendered UI + accessibility
```

### Responsibility boundaries

**The domain layer** holds real values and never stores text with pixel-driven newlines inserted. **The localization layer** turns values into meaningful, locale-appropriate text with placeholders and content structure. **The presentation layer** decides placement, sizing, and display. **The accessibility layer** must be able to read text and meaning even when the UI collapses or uses ellipsis.

For example, when resizing a window from 460px down to 280px, **resource bundles need no changes**; the layout engine should recompute boundaries and line count. Only when the product has a **genuinely distinct content variant**, such as a short tab label, is a separate edited and translated key justified.

## 18. Common pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Sizing buttons tightly to English labels | Long translations clip | Adaptive layout, prefer preferred sizes |
| Forcing translators to shorten to a fixed char count | Loses meaning, unnatural grammar | Design intentional short variants if needed |
| Using `text.length()` to estimate width | UTF-16 units differ from glyph widths | Measure via font/text layout engine |
| Inserting `\n` to patch the current viewport | Other window sizes break awkwardly | UI soft wrapping |
| Translating and concatenating sentence fragments | Hard to reorder words, broken grammar | One complete message with placeholders |
| Breaking lines only on spaces | Wrong for CJK/Thai/Khmer and some punctuation | Unicode line-break / locale-aware engine |
| Treating `BreakIterator` as a renderer | Knows nothing of pixels/widths/fonts | Let the UI decide soft wraps |
| Assuming plain-text `JLabel` wraps automatically | Long text overflows on one line | Pick `JTextArea`/multi-line component |
| Forgetting `JTextArea.setLineWrap` | Lines do not wrap | Enable wrapping and provide a proper viewport |
| Mixing arbitrary CSS/HTML/markup into strings | Blends content with presentation | Separate data and rendering; escape safely |
| Reversing text to support RTL | Corrupts logical order and BiDi | Component orientation, Unicode bidi |
| Truncating with `substring(0,n)` | Splits surrogates/graphemes, loses meaning | Grapheme boundaries + width measurement |
| Using tooltips as the sole way to view full text | Fails accessibility | Provide views/descriptions compatible with assistive tech |
| Testing only English desktop | Misses overflow in other locales | Pseudo-localization, CJK, RTL, font scaling |
| Hardcoding tiny font sizes to squeeze text | Hard to read, violates accessibility | Support text scaling and reflow |
| Capping labels due to unexpected dynamic data | Long names/paths break the UI | Overflow policy and domain validation |

## 19. Self-check questions

1. **Why can translating `Settings` to `Einstellungen` break a button?** Because the button hardcoded a width for one label; that is primarily a UI layout bug.
2. **Is there a rule that all translations are longer than English by the same percentage?** No; length depends on content, grammar, script, and font.
3. **Is `String.length()` enough to know whether text fits in 120px?** No; it counts UTF-16 code units, not glyph width.
4. **How does soft wrap differ from `\n`?** Soft wrap is a width-based rendering decision; `\n` is an actual character in content.
5. **Can `\n` in a resource ever be right?** Yes, when paragraph/line boundaries are an edited part of the meaning.
6. **Who is responsible for wrap points when the user narrows a window?** The text renderer/UI layout, not translators fixing newline positions.
7. **Why not use `split(" ")` to wrap all languages?** Many scripts do not use spaces as word delimiters; punctuation and combining marks have their own rules.
8. **Does `BreakIterator.getLineInstance` know screen width?** No; it returns break opportunities without computing display line counts.
9. **Does `JTextArea` wrap automatically by default?** No; `setLineWrap(false)` is the default.
10. **Does `setWrapStyleWord(true)` replace a full line-breaking engine for every locale?** No; you must test the framework/provider.
11. **How should a string containing ZWJ emojis be truncated?** Cut at grapheme boundaries and re-measure width if pixel limits apply.
12. **Should you reverse a `String` to display Arabic right-to-left?** No; let BiDi and the layout engine handle logical vs. visual order.
13. **If a short label is needed in a tab bar, can a dedicated key be added?** Yes, if product/content intentionally designs a short variant that is translated and tested.
14. **Why test at 200% font scaling?** Text can wrap onto multiple lines and requires containers to grow in height so content is not obscured.
15. **If an important error message is ellipsized, is a tooltip enough?** Usually no; full-content access and accessibility support are needed.
16. **If a backend already sends strings with hard newlines every 20 characters, what should be done?** Review the content contract, drop pixel/char-count line breaks if semantically meaningless, and let the UI wrap automatically.
17. **With French text containing `U+202F`, should all spaces be replaced with `U+0020` before wrapping?** No; non-breaking spacing may need to be preserved.
18. **When is pseudo-localization testing useful?** For catching clipped containers, missing reflow, text direction issues, and character expansion before real translations are finished.

## References

- [Java SE 17 — JTextArea](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JTextArea.html): `setLineWrap`, `setWrapStyleWord`, and text wrapping.
- [Java SE 17 — JLabel](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JLabel.html): single-line default label text.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): locale-aware line-break boundaries.
- [Java SE 17 — ComponentOrientation](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/ComponentOrientation.html): LTR/RTL orientation for UIs.
- [Java SE 17 — FontMetrics](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/FontMetrics.html): measuring text by font.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\X` (extended grapheme clusters).
- [W3C Internationalization — Approaches to Line Breaking](https://www.w3.org/International/articles/typography/linebreak.en.html): line breaking across scripts, CJK, Thai, RTL, and punctuation.
- [Unicode UAX #14 — Unicode Line Breaking Algorithm](https://www.unicode.org/reports/tr14/): line-break opportunities and Unicode rules.
- [Unicode UAX #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): grapheme/word segmentation.
- [W3C Internationalization — CSS3 and International Text](https://www.w3.org/International/articles/css3-text/index): multi-script line breaking and wrapping principles.
