# Understanding the Role of NumericShaper and Java SE Text Input Mechanisms

## 1. The problem: how are digits displayed and how do users enter text?

A multilingual Java application often has to handle at least three distinct tasks:

1. **Numeric values and representation:** a value like `123` must be formatted according to `Locale`, such as decimal separators, thousands grouping separators, and the digits of the requested script.
2. **Displaying digits inside a multi-script line of text:** when text contains Latin letters and Arabic letters, the application may need to render ASCII digits `0–9` using digit characters suited to the surrounding script segment.
3. **Entering text from a keyboard/input method:** a user may type accented Vietnamese, Japanese, Chinese, or another script through an uncommitted editing phase (*composition/preedit*) before confirming the string into an input box.

Java SE provides APIs with separate responsibilities:

- `java.awt.font.NumericShaper`: **converts ASCII digits** into digit characters of a selected script, optionally contextually.
- `java.awt.font.TextAttribute.NUMERIC_SHAPING`: attaches digit-shaping instructions to **attributed text** in AWT/Java 2D presentation pipelines.
- `java.awt.im.InputContext`, `java.awt.event.InputMethodEvent`, `java.awt.event.InputMethodListener`, and related APIs: enable text input methods to coordinate with AWT/Swing UI components.
- `java.text.NumberFormat` and `DecimalFormat`: used when **formatting numeric values by locale**, and should not be replaced with `NumericShaper`.

**Key point:** `NumericShaper` is not an input method and does not format currencies by itself; an input method is not a digit-conversion operation. They may appear together in one multilingual application, yet they operate at **different layers**.

## 2. Distinguishing numeric data, text, and glyphs

Suppose we have an integer value:

```java
int count = 123;
```

This is a **numeric value**, containing no `'1'`, `'2'`, `'3'` characters. When converted to text:

```java
String text = Integer.toString(count); // "123"
```

we now have Unicode characters `U+0031 U+0032 U+0033`, i.e., ASCII/European digits. If presentation in Arabic-Indic digits is requested, the text result can use `U+0661 U+0662 U+0663`.

Distinguish clearly:

| Layer | Common types/APIs | Responsibility |
| --- | --- | --- |
| Value | `int`, `long`, `BigDecimal` | Arithmetic, precision, and business rules |
| Text | `String`, `char[]` | Stored or transmitted code points/digits |
| Numeric shaping | `NumericShaper` | Converting ASCII `0–9` to a target digit set |
| Locale formatting | `NumberFormat` / `DecimalFormat` | Grouping, decimal marks, currency symbols, precision |
| Layout/bidi | Java 2D text layout, `Bidi` | Arranging and presenting directional text lines |
| Input | AWT/Swing input method framework | Creating, editing, and committing typed content |

**Shaping does not change arithmetic value**: `123` is still the number 123. However, when `NumericShaper.shape(...)` runs on a `char[]`, it **mutates the text character codes in the array**, not merely the font or glyph shape. A `String` constructed back from that array will contain different Unicode digits.

A rendering layer can use a shaping attribute to control presentation without forcing you to store the transformed text; that is why you must distinguish direct array shaping from shaping inside text layout.

## 3. What is NumericShaper?

`java.awt.font.NumericShaper` is a class that replaces European/ASCII digits `'0'` through `'9'` with the corresponding digits of another script. It has two primary modes:

- **Non-contextual shaping:** always converts encountered digits to a fixed target script.
- **Contextual shaping:** chooses the digit script based on **text context** and permitted script ranges.

Modern, readable factory methods use the `NumericShaper.Range` enum:

```java
NumericShaper fixed =
        NumericShaper.getShaper(NumericShaper.Range.ARABIC);

NumericShaper contextual =
        NumericShaper.getContextualShaper(
                EnumSet.of(
                        NumericShaper.Range.EUROPEAN,
                        NumericShaper.Range.ARABIC));
```

This is an **illustrative code snippet**, requiring imports for `java.awt.font.NumericShaper` and `java.util.EnumSet`. Standalone programs follow in later sections.

Several digit scripts are supported by the API via `Range`, such as `ARABIC`, `EASTERN_ARABIC`, `DEVANAGARI`, `THAI`, `BENGALI`, and other ranges. Do not assume all languages or every Unicode numbering system share the same mapping or a single shaping rule.

Java also retains historical APIs using bit masks like `NumericShaper.ARABIC`, `NumericShaper.EUROPEAN`, and overloads accepting `int`. When writing new code, the `NumericShaper.Range` enum and `Set<Range>` are usually easier to read and avoid bit-mask mistakes. Legacy APIs may still be needed when maintaining older applications.

## 4. Non-contextual shaping: converting all ASCII digits to one digit set

Example:

```java
char[] characters = "Order 1203".toCharArray();

NumericShaper.getShaper(
        NumericShaper.Range.ARABIC)
        .shape(characters, 0, characters.length);
```

In the array after shaping, the `1203` portion becomes the code points:

```text
U+0661 U+0662 U+0660 U+0663
```

`U+0660` is Arabic-Indic digit zero, `U+0661` is digit one, and so on. The digit set changed, yet **the word `Order` is not affected by this conversion**.

The `shape(char[] text, int start, int count)` method performs conversion **in place** on a slice of the array:

- `text` is the mutable character array.
- `start` is the starting index in Java `char`/UTF-16 units.
- `count` is the **number of elements** to process, not the ending index.
- `start + count` must stay within the array length.

A common bug is calling `shape(chars, 5, chars.length)` when intending to process from index 5 to the end: the right `count` is `chars.length - 5`, not `chars.length`.

### What does NumericShaper handle?

- Converts European digit characters `'0'–'9'` within the shaped range.
- Does not translate letters, punctuation, whitespace, grouping separators, or decimal marks.
- Does not round numeric values, validate monetary amounts, or infer an input `Locale`.
- Does not convert digits of arbitrary scripts back into ASCII, nor is it a general reverse converter.

If you only need to format **a number** for a locale, `NumberFormat` is the better API; if you need to convert digits **inside a multi-script line of text**, `NumericShaper` can help.

## 5. Complete Java 17+ example: non-contextual NumericShaper

Save the file `FixedNumericShaperDemo.java`:

```java
import java.awt.font.NumericShaper;
import java.util.Locale;
import java.util.stream.Collectors;

public class FixedNumericShaperDemo {
    private static String digitCodes(char[] characters) {
        return new String(characters)
                .codePoints()
                .filter(Character::isDigit)
                .mapToObj(cp ->
                        String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        char[] arabic = "Order 1203".toCharArray();

        NumericShaper.getShaper(NumericShaper.Range.ARABIC)
                .shape(arabic, 0, arabic.length);

        char[] thai = "Total 789".toCharArray();

        NumericShaper.getShaper(NumericShaper.Range.THAI)
                .shape(thai, 0, thai.length);

        System.out.println("arabic=" + digitCodes(arabic));
        System.out.println("thai=" + digitCodes(thai));
    }
}
```

Compile and run:

```bash
javac FixedNumericShaperDemo.java
java FixedNumericShaperDemo
```

Output verified on the JDK (printing Unicode codes so it does not depend on console fonts):

```text
arabic=U+0661 U+0662 U+0660 U+0663
thai=U+0E57 U+0E58 U+0E59
```

The output shows source digits `1,2,0,3` and `7,8,9` became digit characters in their respective ranges. The program intentionally **does not print Arabic/Thai glyphs directly** so stdout remains stable when a terminal lacks fonts or script support.

`String` in Java is immutable, so `shape(...)` does not modify an existing `String` variable. The workflow when you need new text is taking `toCharArray()`, shaping the array, then creating `new String(chars)`. If you want to retain original ASCII data in a database, **do not unconditionally overwrite it with shaped text**.

## 6. Contextual shaping: deciding based on surrounding script

In a line mixing Latin and Arabic, an application sometimes wants:

```text
abc 123 [Arabic letters] 456
```

The desired result may be:

- `123` in the Latin context stays ASCII digits.
- `456` following strong Arabic characters switches to Arabic-Indic digits.

Here you use `getContextualShaper(...)`. A contextual shaper examines script context and permitted ranges rather than forcing all digits to one fixed range.

```java
NumericShaper contextual =
        NumericShaper.getContextualShaper(
                EnumSet.of(
                        NumericShaper.Range.EUROPEAN,
                        NumericShaper.Range.ARABIC));
```

`Range.EUROPEAN` represents the European digits `0–9`; `Range.ARABIC` provides Arabic-Indic digits. *Strong directional characters* can influence the context of subsequent digits. This is a specific rule-based mechanism, not a language model understanding prose meaning.

The API also provides overloads to specify a **starting context**. Defining the initial context matters if a paragraph is shaped starting mid-line in a long run: digits appearing before any strong letter can depend on that initial context.

### Standalone Java 17+ example

Save `ContextualNumericShaperDemo.java`:

```java
import java.awt.font.NumericShaper;
import java.util.EnumSet;
import java.util.Locale;
import java.util.stream.Collectors;

public class ContextualNumericShaperDemo {
    private static String digitCodes(String text) {
        return text.codePoints()
                .filter(Character::isDigit)
                .mapToObj(cp ->
                        String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String input =
                "abc 123 \u0627\u0644\u0639\u0631\u0628\u064A\u0629 456";

        char[] characters = input.toCharArray();

        NumericShaper shaper =
                NumericShaper.getContextualShaper(
                        EnumSet.of(
                                NumericShaper.Range.EUROPEAN,
                                NumericShaper.Range.ARABIC));

        shaper.shape(characters, 0, characters.length);

        System.out.println(
                "digits=" + digitCodes(new String(characters)));
    }
}
```

Compile/run:

```bash
javac ContextualNumericShaperDemo.java
java ContextualNumericShaperDemo
```

Verified result:

```text
digits=U+0031 U+0032 U+0033 U+0664 U+0665 U+0666
```

The first three digits stay ASCII `1,2,3`; the three digits after Arabic characters belong to the Arabic-Indic range. This result comes from **the shaper's contextual rules**, not from an Arabic input method or `Locale.getDefault()` acting automatically.

**Do not equate contextual shaping with automatic language detection.** It does not recognize the semantic purpose of a number or the writer's nationality; it relies on permitted ranges and character context. Complex multilingual prose must be tested with real data.

## 7. Range and legacy bit masks

The two factory families should be read carefully:

| API | Input | Suggestion |
| --- | --- | --- |
| `NumericShaper.getShaper(Range)` | One `NumericShaper.Range` | Non-contextual, easy to read |
| `NumericShaper.getContextualShaper(Set<Range>)` | Set of ranges | Contextual, more type-safe |
| `NumericShaper.getContextualShaper(Set<Range>, Range)` | Set of ranges and default context | Contextual with explicit initial context |
| `NumericShaper.getShaper(int)` | One legacy bit mask | Legacy code |
| `NumericShaper.getContextualShaper(int)` | Bit mask of legacy ranges | Legacy code |

Legacy example:

```java
NumericShaper oldStyle =
        NumericShaper.getContextualShaper(
                NumericShaper.EUROPEAN | NumericShaper.ARABIC);
```

This is an illustrative snippet. Do not confuse `NumericShaper.Range.ARABIC` with the `NumericShaper.ARABIC` constant: the former is an **enum**, the latter is an **int mask**.

When implementing, pick one style consistently to avoid mixing up bit masks and enums or accidentally omitting a required range. A contextual shaper only supports the ranges you allow; it does not automatically support every script present in the input.

## 8. TextAttribute.NUMERIC_SHAPING in Java 2D

Numeric shaping can also be used as a **text formatting attribute** instead of manually mutating a `char[]`.

`java.awt.font.TextAttribute.NUMERIC_SHAPING` is the attribute key; its value can be a `NumericShaper` instance. Example:

```java
import java.awt.font.NumericShaper;
import java.awt.font.TextAttribute;
import java.text.AttributedString;

AttributedString attributed =
        new AttributedString("Price 123");

attributed.addAttribute(
        TextAttribute.NUMERIC_SHAPING,
        NumericShaper.getShaper(NumericShaper.Range.ARABIC));
```

This is an **illustrative Java snippet**. `AttributedString` supplies an iterator with attributes that Java 2D's presentation pipeline can consume in appropriate layout APIs, such as `TextLayout`.

Important points:

- Creating an `AttributedString` with `NUMERIC_SHAPING` is **not** calling `shape(char[])` and does not modify the source string.
- This attribute passes a **shaping hint** to presentation when the layout API honors the attribute.
- Final glyphs also depend on the font, layout mechanism, and environment's rendering support.
- If you write data to a file or send JSON, do not assume the renderer converted source data into target-script digit characters.

`TextAttribute.NUMERIC_SHAPING` is helpful at the display layer; if you actively need to transform a character array into concrete digits, use `NumericShaper.shape(...)` and remember that Unicode code points in the output have changed.

## 9. NumericShaper is not an RTL/LTR direction tool

In Arabic/Hebrew text mixed with Latin and numbers, there are at least **three independent issues**:

1. **Digit conversion:** `NumericShaper` can turn `0–9` into digits of the chosen script.
2. **Text direction and visual ordering:** the bidirectional (Bidi) algorithm handles right-to-left/left-to-right ordering of character runs.
3. **Glyph drawing and letter joining:** the glyph engine, cursive shaping, and fonts render the actual text.

`NumericShaper` solves **digit conversion**; it does not put an Arabic segment into the right visual order on screen and does not perform Arabic cursive joining. Java SE also provides `java.text.Bidi` and AWT/Java 2D text layout capabilities for those other concerns, though proper UI rendering also depends on the component and renderer in use.

For example, do not write:

```java
new String(chars); // after NumericShaper
```

and conclude that the app has "full RTL support." It may contain Arabic-Indic digits, yet there is no guarantee regarding visual ordering, fonts, caret, or selection.

When using Swing with text components, test component orientation, caret ordering, selection, symbols, and behavior when users switch input methods, rather than reversing strings with `StringBuilder.reverse()`.

## 10. NumericShaper differs from NumberFormat/DecimalFormat

If the task is presenting monetary amounts, prices, percentages, or decimal numbers according to locale, use `NumberFormat` or `DecimalFormat`.

Example:

```java
java.text.NumberFormat formatter =
        java.text.NumberFormat.getNumberInstance(
                java.util.Locale.forLanguageTag("ar-EG"));

String shown = formatter.format(1234.5);
```

The result depends on the locale, numbering system, and JDK data/providers. The formatter is responsible for choosing **grouping separators, decimal marks, digit counts, and rounding rules** per configuration. `NumericShaper` lacks that information; it only processes ASCII digits within the shaped text range.

Comparison:

| Requirement | Appropriate choice |
| --- | --- |
| Format numeric value `1234.5` by locale | `NumberFormat` / `DecimalFormat` |
| Convert ASCII digits in a sentence to a fixed digit set | `NumericShaper.getShaper(...)` |
| Choose digits based on script context within a sentence | `NumericShaper.getContextualShaper(...)` |
| Attach shaping hint to text layout | `TextAttribute.NUMERIC_SHAPING` |
| Receive characters from IME, manage composing text | AWT/Swing input method APIs |
| Read/validate Unicode digits from input | Parser and input validation per contract |

Do not take a shaped string and assume it can be parsed with `Integer.parseInt` or sent to every machine-to-machine API. Some parsers accept Unicode decimal digits, yet a protocol may allow only ASCII. **Display localization** and **data exchange formats** must stay separate.

## 11. Java SE text input mechanisms (*input methods*)

An input method/IME can turn multiple keystrokes into one or more final characters. For example, a user types Vietnamese using a diacritic input scheme, or types Japanese by entering a Latin sequence to select Kanji characters.

The flow can involve:

```text
Key events / device input
            |
            v
  Input Method / IME
            |
            +--> Composed text (being edited, uncommitted)
            |
            v
   Commit / confirm
            |
            v
   Text component/document
```

Therefore, **do not equate a `KeyEvent` with "one character entered by the user."** One keystroke may not yet produce a final character, multiple keystrokes may yield one character, or the user may pick a candidate from an IME popup.

In Java SE, the AWT input method framework coordinates the IME with text input components; Swing text components build on this mechanism to support composed text and committed text.

This concerns **receiving and committing input content**. It is distinct from `NumericShaper`, which processes digits in existing text or in a display pipeline.

## 12. Text input APIs to recognize

| API | Role |
| --- | --- |
| `java.awt.im.InputContext` | Manages the input method context, selecting/coordinating input methods for a component |
| `java.awt.event.InputMethodEvent` | Event notifying changes to composing text or caret position |
| `java.awt.event.InputMethodListener` | Listener receiving notifications of composed text and caret changes |
| `java.awt.im.InputMethodRequests` | Interface allowing an input method to query text/caret positions, selection, and committed text per contract |
| `java.awt.font.TextHitInfo` | Represents hit/position info in text for events/caret |
| `java.awt.im.spi.InputMethod` | SPI for input method implementations integrating with Java |
| `java.awt.im.spi.InputMethodDescriptor` | Describes capabilities and creation of an input method in the SPI |
| `javax.swing.text.JTextComponent` | Base class for Swing text components such as `JTextField`, `JTextArea` supporting text entry/editing |

`InputContext` is not the text string entered by the user. `InputMethodEvent` is not a numeric event and does not require `NumericShaper` to function. `InputMethodRequests` supports coordination between the IME and the text display area, especially for **inline composition**.

Java SE's input method APIs belong to the desktop/AWT environment. In a server/headless application, you cannot assume a keyboard, window, or interactive IME exists. If handling HTTP input from a browser, the IME normally runs **on the client side**, and the server receives the string after submission.

## 13. Composed text vs. committed text: what is the difference?

Two key states:

- **Composed text (preedit):** the string currently being composed by the user via an IME; it may change, be canceled, or be replaced by another candidate.
- **Committed text:** the portion of characters the IME has confirmed and delivered to the application. Only this portion should enter the document per component policy.

`InputMethodEvent.INPUT_METHOD_TEXT_CHANGED` signals a change in input text; `InputMethodEvent.CARET_POSITION_CHANGED` signals a change in caret/selection position within the text being entered.

`InputMethodEvent.getText()` returns an `AttributedCharacterIterator` for the event's text, which may contain both the committed part and the composing part. `getCommittedCharacterCount()` reports how many characters at the beginning of the event text have been committed; the remainder is composed text. For some event types, `getText()` can be `null`, so never dereference it unconditionally.

Logical example:

```text
Event text:       abc
Committed count:    1
Committed:        a
Composing:         bc
```

Both parts must be handled properly. If a listener writes **the entire event text** directly to a database or document before the IME commits, temporary characters can be saved by mistake or inserted repeatedly.

## 14. Standalone Java 17+ example: reading InputMethodEvent state

The following example creates a **simulated event to illustrate the API structure**; it does not start a real IME or emulate the full input-method lifecycle.

Save as `InputMethodEventDemo.java`:

```java
import java.awt.Canvas;
import java.awt.event.InputMethodEvent;
import java.awt.font.TextHitInfo;
import java.text.AttributedCharacterIterator;
import java.text.AttributedString;
import java.text.CharacterIterator;

public class InputMethodEventDemo {
    public static void main(String[] args) {
        AttributedCharacterIterator text =
                new AttributedString("abc").getIterator();

        InputMethodEvent event = new InputMethodEvent(
                new Canvas(),
                InputMethodEvent.INPUT_METHOD_TEXT_CHANGED,
                text,
                1,
                TextHitInfo.leading(1),
                null);

        AttributedCharacterIterator iterator = event.getText();
        int begin = iterator.getBeginIndex();
        int committedEnd =
                begin + event.getCommittedCharacterCount();

        StringBuilder committed = new StringBuilder();
        StringBuilder composing = new StringBuilder();

        for (char c = iterator.first();
             c != CharacterIterator.DONE;
             c = iterator.next()) {

            if (iterator.getIndex() < committedEnd) {
                committed.append(c);
            } else {
                composing.append(c);
            }
        }

        System.out.println("committed=" + committed);
        System.out.println("composing=" + composing);
        System.out.println(
                "caret=" + event.getCaret().getInsertionIndex());
    }
}
```

Compile and run in a Java SE environment with the `java.desktop` module:

```bash
javac InputMethodEventDemo.java
java InputMethodEventDemo
```

Verified output:

```text
committed=a
composing=bc
caret=1
```

Understand the limitations of this example:

1. `AttributedString("abc")` merely creates sample text; it is **not real IME output**.
2. The `InputMethodEvent` constructor takes a source `Component`, event ID, iterator, committed character count, and caret info.
3. `TextHitInfo.leading(1)` is used in the example to supply a caret position.
4. Splitting committed/composing relies on the **committed character count**, not on whether something looks like a finished word.
5. The example creates an event and reads its data; it **does not dispatch the event into a `JTextField`** and does not prove real user typing occurred.

On minimal JVMs lacking `java.desktop`, AWT/IME classes will not be available. On a typical Java SE desktop environment, the program only constructs basic objects and does not need to open a window.

## 15. Swing text components and input method support

Standard `JTextComponent` subclasses like `JTextField` and `JTextArea` already have built-in support for editing, caret, selection, and input methods. When building a Swing application, let **the text component** handle composing content rather than writing a `KeyListener` that converts keystrokes into characters manually.

A standalone UI example, runnable on a machine with a desktop UI:

```java
import java.awt.BorderLayout;
import java.awt.event.InputMethodEvent;
import java.awt.event.InputMethodListener;
import javax.swing.JFrame;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;

public class SwingInputDemo {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java input method");
            frame.setDefaultCloseOperation(
                    JFrame.EXIT_ON_CLOSE);

            JTextField field = new JTextField(28);

            field.addInputMethodListener(
                    new InputMethodListener() {
                        @Override
                        public void inputMethodTextChanged(
                                InputMethodEvent event) {

                            System.out.println(
                                    "committedCount=" +
                                    event.getCommittedCharacterCount());
                        }

                        @Override
                        public void caretPositionChanged(
                                InputMethodEvent event) {
                            // Track the caret if the application needs it.
                        }
                    });

            frame.add(field, BorderLayout.CENTER);
            frame.pack();
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
```

Run in a GUI environment:

```bash
javac SwingInputDemo.java
java SwingInputDemo
```

**There is no fixed stdout** for this example: it depends on the input method, user actions, focus, and how the runtime delivers events. The goal is observing the listener, not replacing Swing's text input system.

Practical notes:

- The listener in the example **only observes**; it does not re-insert all of `event.getText()` into the `JTextField`.
- Do not rely on `KeyEvent.KEY_TYPED` as the sole source of characters when an IME is active.
- Work on Swing components must run on the **Event Dispatch Thread**, e.g. via `SwingUtilities.invokeLater(...)`.
- When an app only needs the final value after user input, use document/field APIs and appropriate validation; there is no need to build a custom composition handler.
- You may need to test focus, text selection, and real keyboard interactions on each OS.

**Note:** running this demo in a headless environment will have no interactive window; do not try to diagnose a headless error as a `NumericShaper` bug.

## 16. InputContext: coordinating the input method without generating characters itself

`InputContext` represents an input method context in AWT. For instance, a component can access its input context through the corresponding component API, and an application can request selecting an input method by locale.

Illustrative snippet:

```java
java.awt.im.InputContext context =
        component.getInputContext();

if (context != null) {
    boolean selected = context.selectInputMethod(
            java.util.Locale.JAPANESE);
    // selected indicates whether the request to select the input method
    // succeeded in the running environment.
}
```

The `component` variable must be a `java.awt.Component` created in an appropriate GUI context. **Do not assume** every environment has an IME installed for `Locale.JAPANESE`; the outcome depends on the platform and installed input methods.

The API can help enable/disable input methods and manage composition according to the capabilities of the component and IME. Yet `InputContext` does not mutate a `String` you pass in, does not format dates/times, and does not guarantee any arbitrary locale can be selected.

In particular, **the UI formatting Locale** and **the input method's Locale** do not have to match. A user may be using a Vietnamese UI while typing Japanese or English text in the same form.

## 17. InputMethodRequests and InputMethod SPI: for advanced cases

Most Swing applications use built-in text components and do not need to implement `InputMethodRequests` directly or write a new input method.

`java.awt.im.InputMethodRequests` matters when a **custom-built** text component needs inline composition support and the IME must query:

- The on-screen location of the text being composed.
- The caret/selection position corresponding to display coordinates.
- The committed portion of text.
- Certain operations related to returning committed text back to edit mode (*reconversion*), when supported.

`java.awt.im.spi.InputMethod` and `InputMethodDescriptor` belong to the **Service Provider Interface** for IME developers integrating with the AWT input method framework—not an API every ordinary form needs to call.

Recognize the three layers:

```text
Application / JTextComponent
        |
        | InputMethodEvent, InputMethodRequests
        v
AWT InputContext / dispatch mechanism
        |
        v
Platform or provider Input method / IME
```

Different platforms integrate differently. Developing a new input method must follow the SPI and handle focus, event dispatch, locales, language selection, and lifecycle; never start by merely implementing a `KeyListener`.

## 18. Boundary between presentation and input

Consider the following sequence of tasks:

1. A user uses an IME to enter text containing Arabic letters and numbers.
2. The text component receives composition events, then places committed text into the document.
3. The application validates and stores the text per its data contract.
4. On display, text layout can handle bidi, fonts, and context-based numeric shaping.

Here:

- **IME** handles the user **getting content into the application**.
- **NumericShaper** handles **converting ASCII digits** in text or within a layout pipeline.
- **Bidi/text layout** handles **visual order and shape**.
- **Validation/parser** handles **whether that data is valid**.

No single API replaces the entire workflow.

One design mistake is applying `NumericShaper` to all text while the user is still composing. If the app alters Unicode codes of the preedit segment mid-composition, the IME can lose track of expected positions and content. If shaping is needed in the UI, prefer integrating at the appropriate **rendering layer**, and transform stored values only when data policy explicitly requires it.

## 19. Text direction, caret, selection, and Unicode issues

Java `String.length()` and many event/caret APIs use **positions in UTF-16 code units**. In Arabic text, characters with combining marks, emojis, or RTL segments:

- One visible character is not necessarily one UTF-16 `char`.
- Character order in memory is not necessarily left-to-right order on screen.
- Carets can involve **text hit/affinity** at glyph boundaries, especially in bidirectional text.
- Composition can carry attributes distinguishing currently edited text from selected text.

`TextHitInfo` represents hit/caret information at the text layer, not merely a column count from the left. For RTL-capable UIs, test actual navigation and selection.

If an application transforms or normalizes a string after computing caret positions, offsets may no longer align with the new text. `NumericShaper` maps corresponding digit characters one-to-one, yet other text steps such as Unicode normalization can change code unit counts. Do not use indices from one text representation to slice or highlight another without proper mapping.

## 20. Reading digits after shaping: values, validation, and security

After `NumericShaper` converts `"123"` into digits of another script, the application must decide **whether the resulting data is display text or a numeric value**.

In Java, `Character.digit(codePoint, 10)` can recognize the decimal numeric value of many Unicode digit characters:

```java
int digit = Character.digit('\u0662', 10);
// digit == 2
```

However, from recognizing a Unicode digit, **do not conclude every parser, regex, or protocol accepts that string**. For instance, a protocol specifying ASCII `[0-9]+` must be validated strictly against that grammar; usernames, contract IDs, or card-number strings may require rules preventing mixed scripts and confusable characters.

If users enter locale-formatted numbers, use a parser like `NumberFormat` with an explicit `Locale`, while validating the entire input and value range. If machine-to-machine data requires ASCII, never alter payload bytes just because the UI displays Arabic digits.

Safe principles:

- **Store numeric values as numeric types** when data is truly numeric.
- **Preserve original source text** when business rules require keeping user content intact.
- **Format at the display boundary** per locale and text-shaping policies.
- **Validate explicitly** when accepting Unicode digits from untrusted sources.
- **Do not use shaping to erase Unicode differences**, prevent username spoofing, or perform hidden canonicalization.

Shaping is not a Unicode normalizer (`Normalizer`) and not a security filter.

## 21. Common mistakes

**1. Thinking NumericShaper is an input method.** It processes digits already present in text; it does not accept keystrokes or perform composition.

**2. Using NumericShaper to format currency.** It does not add currency symbols, grouping separators, decimal marks, or rounding.

**3. Confusing `Range.ARABIC` with the `NumericShaper.ARABIC` mask.** One is an enum; the other is a legacy `int` constant.

**4. Mistaking the `count` parameter for an ending index.** `shape(chars,start,count)` takes an element count, not an end index.

**5. Thinking `shape(char[])` only swaps glyphs.** This call mutates `char` elements directly in the array; any new string created from it has changed code points.

**6. Thinking attaching `TextAttribute.NUMERIC_SHAPING` mutates the source `String`.** It is a presentation attribute, not an in-place transformation on stored strings.

**7. Thinking contextual shapers know the user's language.** They rely on character script context and range sets, not semantics or the overall UI locale.

**8. Thinking numeric shaping solves RTL/Bidi by itself.** Text direction and glyph layout require separate mechanisms.

**9. Saving shaped numbers into machine-to-machine protocols.** This can violate ASCII contracts or break parsers.

**10. Using `KeyListener` as the sole source for all IME characters.** Text may remain in composition across multiple keystrokes before committing.

**11. Inserting composed text into the document before commit.** Risks duplication, corrupted content, or broken IME state.

**12. Using `InputMethodEvent.getText()` without checking event type/`null`.** Not every event carries text.

**13. Re-implementing an entire IME when `JTextField` already supports it.** Leverage the standard input method framework and text components.

**14. Assuming every machine has an IME for the requested locale.** Availability depends on OS, input method providers, and GUI state.

**15. Sharing mutable editor state/iterators across threads.** UI and event dispatch have threading rules; Swing must run on the EDT.

**16. Confusing UTF-16 indices with visual positions.** RTL text and composite glyphs can have caret positions differing from code unit order.

**17. Assuming Unicode digits are "safe" because `Character.digit` reads them.** Input validation and security policies remain mandatory.

## 22. Scenarios for picking the right API

| Scenario | Appropriate API/policy |
| --- | --- |
| Display a price for `ar-EG` | Locale-based `NumberFormat` |
| Convert `123` in a string to fixed Arabic-Indic digits | `NumericShaper.getShaper(Range.ARABIC)` |
| Mix Latin/Arabic and pick digits by text run | `NumericShaper.getContextualShaper(...)` |
| Attach shaping to attributed text presentation | `TextAttribute.NUMERIC_SHAPING` |
| TextField accepting Vietnamese/Japanese IME | `JTextField`/`JTextComponent` and input method framework |
| Observe preedit and committed character count | `InputMethodListener` / `InputMethodEvent` |
| Build a custom component supporting inline IME | `InputMethodRequests`, text layout, and event handling |
| Create an input method provider | `java.awt.im.spi` |
| Handle RTL characters in the right direction | Bidi/text layout plus component capabilities |
| Validate entered numbers | Parser/validator per grammar/locale |

If a product has both input forms and Arabic/Latin text display, **multiple rows in the table may apply at once**. Do not try to turn `NumericShaper` into a catch-all localization solution.

## 23. Practical testing checklist

- **Fixed NumericShaper:** `1203` becomes `U+0661 U+0662 U+0660 U+0663` when selecting the Arabic range.
- **Other ranges:** test Thai/Devanagari and inspect code point output independently of fonts.
- **Mixed-script text:** leading Latin digits and digits after an Arabic segment produce the expected contextual result.
- **Array bounds:** verify `start/count`; elements outside the range must not be altered.
- **Source data:** compare the original string against a string built from the char array after shaping; know exactly where code points actually changed.
- **TextAttribute:** verify whether the renderer honors `NUMERIC_SHAPING` and the font has glyphs.
- **Bidi:** test visual order, caret/selection between Arabic and Latin.
- **IME:** type, choose candidates, commit, cancel composition; never insert temporary text twice.
- **Focus:** switch between multiple text fields, switch input methods, select text, undo/redo.
- **Locale:** UI locale and input locale can differ; never rely on server default locale.
- **Headless:** separate data logic that needs no AWT GUI from tests requiring a desktop.
- **Security:** Unicode digits from external sources must satisfy protocol grammar and script-mixing rules.
- **Accessibility:** check fonts, screen readers, and digit display with real users.
- **Versions:** JDK/Unicode upgrades, font changes, or platform IME updates can alter presentation output.

## 24. Self-check questions

**Q1.** What is `NumericShaper.getShaper(Range.ARABIC)` used for?  
**A:** Converting ASCII digits in the shaped text range into Arabic-Indic digits, without formatting monetary values.

**Q2.** How does `getContextualShaper(...)` differ from `getShaper(...)`?  
**A:** A contextual shaper picks a range based on script context and permitted ranges; a non-contextual shaper uses one fixed range.

**Q3.** Does `shape(chars, 4, 3)` process up to index 3 or how many elements?  
**A:** Three elements starting at index 4—that is, indices 4, 5, and 6 if the array is long enough.

**Q4.** Does `TextAttribute.NUMERIC_SHAPING` automatically mutate the `String` used to create `AttributedString`?  
**A:** No. It attaches a shaping instruction for a compatible presentation pipeline.

**Q5.** Does `NumericShaper` solve bidi and all Arabic glyphs?  
**A:** No. It is a digit conversion; bidi and layout are separate responsibilities.

**Q6.** Why shouldn't you use a single `KeyEvent` to determine one final Japanese/Vietnamese character?  
**A:** An input method may require multiple actions, a preedit stage, and a commit step; `KeyEvent` does not capture that full lifecycle.

**Q7.** If an `InputMethodEvent` has 1 committed character and 2 composing characters, should you save all 3 immediately?  
**A:** Not by default. You must respect composition handling, and standard components already handle inserting committed text.

**Q8.** When should you use `NumberFormat` instead of `NumericShaper`?  
**A:** When formatting a **numeric value** by locale with decimal marks, grouping separators, precision, or currency symbols.

**Q9.** Can you select a Japanese IME with `InputContext.selectInputMethod(Locale.JAPANESE)` on every machine?  
**A:** Not guaranteed; it depends on the platform and available input methods.

**Q10.** Why must shaped digits be validated if sent to a machine-to-machine API?  
**A:** An API may only allow strict ASCII/canonical syntax; shaping produces different Unicode characters.

## 25. Summary

`NumericShaper` helps **convert ASCII digit characters into digits of a target script**, either using one fixed range or choosing contextually. `TextAttribute.NUMERIC_SHAPING` brings that role into the text presentation layer; `NumberFormat` remains the right tool for formatting **numeric values** by locale.

Java SE's text input mechanism belongs to AWT/Swing: `InputContext` coordinates the input method, `InputMethodEvent` carries composing and committed text information, and text components manage caret/document/focus. When building multilingual applications, **separate data, shaping, bidi/layout, IME, and validation** so each layer maintains a clear contract.

**Official documentation:** [Java SE 17 — NumericShaper](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/NumericShaper.html) · [TextAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextAttribute.html) · [InputContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/InputContext.html) · [InputMethodEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/event/InputMethodEvent.html) · [InputMethodListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/event/InputMethodListener.html) · [InputMethodRequests](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/InputMethodRequests.html) · [InputMethod SPI](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/im/spi/package-summary.html).
