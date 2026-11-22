# Single Quote, Curly Braces, and Escaping Rules in Java `MessageFormat` Patterns

## 1. Why `MessageFormat` Patterns Break Easily Even When the String Looks "Right"

`java.text.MessageFormat` builds parameterized messages according to a `Locale`. For example:

```java
MessageFormat format =
        new MessageFormat("Xin chào {0}!", Locale.forLanguageTag("vi-VN"));
System.out.println(format.format(new Object[] {"Lan"}));
```

Output:

```text
Xin chào Lan!
```

The `{0}` notation is a **placeholder** for the argument at index 0. However, `MessageFormat` does not treat a pattern string as ordinary plain text: the **single quote `'`** has syntactic meaning, braces **`{` and `}`** delimit format elements, and the **backslash `\` is not a general escape mechanism in `MessageFormat` syntax**.

Because of this, a message like `It's {0}` may fail to substitute the argument as the author intended. An example containing `{0}` to explain documentation can also be treated as an argument placeholder. When a pattern lives in Java code or a `.properties` file, you must distinguish **two processing layers**: string-storage syntax and `MessageFormat` syntax.

This lesson focuses on **single quotes, curly braces, escaping, and how to test patterns**; do not confuse it with `String.format` or string interpolation in other languages.

## 2. Basic Form of a Format Element

An element in a pattern takes the form:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

For example:

```text
Hello {0}; you have {1,number,integer} notifications.
```

- `{0}` is the first argument, `{1}` is the second argument (indices start at **0**).
- `number`, `date`, `time`, and `choice` can extend formatting per `Locale`; valid types and styles depend on the kind.
- Commas and curly braces inside format element syntax are handled specially by the parser.
- If you only want to print the **literal text `{0}`** instead of inserting an argument, you must **quote it as literal text**.

**Curly braces are not variable-name substitution syntax.** Standard `MessageFormat` uses non-negative integer argument indices like `{0}`, and does not recognize `{username}`. Malformed patterns can throw `IllegalArgumentException` when constructed or applied.

## 3. Single-Quote Rules: Three Behaviors to Remember

In `MessageFormat`, a **single standalone quote `'`** starts or ends **a quoted segment**, meaning a span of characters treated as plain text. The quote characters used to open and close the span **do not appear** in the output.

**Two consecutive single quotes `''`** represent **one literal single quote** in the output.

**An unclosed opening single quote** is treated as automatically closed at the end of the pattern, usually causing subsequent placeholders to print verbatim instead of being substituted.

| Pattern passed to `MessageFormat` | Argument `{0}` | Output | Explanation |
| --- | --- | --- | --- |
| `Hello {0}` | `Lan` | `Hello Lan` | Normal placeholder |
| `It''s {0}` | `Lan` | `It's Lan` | `''` produces one `'` character |
| `It's {0}` | `Lan` | `Its {0}` | The `'` before `s` opens a quote to the end of the pattern; `{0}` loses placeholder role |
| `'Hello' {0}` | `Lan` | `Hello Lan` | `Hello` is quoted; syntactic `'` characters are stripped |
| `''{0}''` | `Lan` | `'Lan'` | Two `''` pairs create single quotes around the **formatted value** |
| `'{0}'` | `Lan` | `{0}` | The entire `{0}` is quoted, so it is **not** substituted |
| `'abc {0}` | `Lan` | `abc {0}` | Unclosed quote; Java implicitly closes it at the end of the pattern |

**Critical distinction:**

- `'{0}'` → prints literally **`{0}`** (does not insert data).
- `''{0}''` → prints **`'Lan'`** when `{0}` is `Lan` (inserts data, wrapped in real single quotes).

Many bugs happen simply because an author puts a pair of single quotes around a placeholder thinking they are decorative characters. In `MessageFormat`, that is a **syntactic quoting directive**.

### Quotes in Input Data Differ from Quotes in Patterns

If an argument is the name `O'Brien`, pass it directly:

```java
Object[] args = {"O'Brien"};
```

Single quotes inside **replacement data** do not cause the parser to re-parse the pattern. Therefore, never double single quotes in person names, addresses, or input data as if they were `MessageFormat` patterns. Only escape **single quotes located in the pattern**.

## 4. Printing Literal Curly Braces with `'{'` and `'}'`

An opening brace `{` starts a format element; `}` closes it. When you need to print a brace as ordinary text, place it inside a single-quoted span:

| Intent | Pattern | Result with `{0} = OK` |
| --- | --- | --- |
| Print `{` | `'{' ` | `{ ` |
| Print `}` | `'}'` | `}` |
| Print literal `{0}` | `'{0}'` | `{0}` |
| Wrap **value** in `{...}` | `'{'{0}'}'` | `{OK}` |
| Explain typing braces | `Type '{' and '}' to wrap {0}` | `Type { and } to wrap OK` |

In the first row, the space after `'{'` is only to show a character following it; the pattern `'{'` itself outputs a single `{` character.

The pattern `'{'{0}'}'` combines **three parts**: a literal opening `{`, the real placeholder `{0}`, and a literal closing `}`. Writing `'{0}'` turns the entire placeholder into literal text.

**Do not** use a backslash to "escape braces" out of habit from regex or JavaScript:

```text
\{0\}     ← not MessageFormat brace-escaping syntax
```

`MessageFormat` has no such "backslash neutralizes curly braces" rule. A backslash in a pattern is typically treated as a literal character; the curly braces are still processed by the parser according to its rules.

## 5. Java 17+ Program Verifying All Basic Cases

Create the file **`MessageFormatEscapingDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatEscapingDemo {
    private static void show(String label, String pattern, String value) {
        MessageFormat format = new MessageFormat(pattern, Locale.ROOT);
        String result = format.format(new Object[] {value});
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        show("basic", "Hello {0}!", "Lan");
        show("apostrophe", "It''s {0}.", "OK");
        show("literal-placeholder", "Pattern '{0}' and value {0}", "Lan");
        show("quoted-value", "Value: ''{0}''.", "OK");
        show("literal-braces", "Open '{', close '}', content {0}.", "OK");
        show("around-value", "'{'{0}'}'", "OK");

        // Semantically wrong, yet still a parseable pattern:
        show("wrong-apostrophe", "It's {0}.", "OK");
        show("unclosed-quote", "Error 'word {0}", "OK");

        try {
            new MessageFormat("Invalid {0", Locale.ROOT);
            System.out.println("invalid: unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid: IllegalArgumentException");
        }
    }
}
```

Compile and run in the directory containing the file with JDK 17+ (the terminal should support Unicode):

```bash
javac -encoding UTF-8 MessageFormatEscapingDemo.java
java -cp . MessageFormatEscapingDemo
```

Output when the terminal renders UTF-8 properly:

```text
basic: Hello Lan!
apostrophe: It's OK.
literal-placeholder: Pattern {0} and value Lan
quoted-value: Value: 'OK'.
literal-braces: Open {, close }, content OK.
around-value: {OK}
wrong-apostrophe: Its {0}.
unclosed-quote: Error word {0}
invalid: IllegalArgumentException
```

The two lines `wrong-apostrophe` and `unclosed-quote` **intentionally demonstrate logic errors**: a pattern does not necessarily throw an exception, yet can produce an unintended string. Therefore, testing "creating `MessageFormat` succeeds without error" is insufficient; you must assert actual formatted results, especially for translations containing quotes.

The `show(...)` helper uses `Locale.ROOT` and string arguments to avoid locale-specific differences in number/date formatting; this example tests quoting and placeholder rules in isolation.

## 6. Escaping Exists at Multiple Layers: Java Source, `.properties`, `MessageFormat`

A very common mistake is seeing a quote or brace fail and adding a backslash `\`. Before fixing it, you must know **where the string is being read from**.

### 6.1. Patterns Written Directly in Java Code

Suppose you need to display `It's Lan`:

```java
String pattern = "It''s {0}";
String output =
        new MessageFormat(pattern, Locale.ROOT)
                .format(new Object[] {"Lan"});
System.out.println(output); // It's Lan
```

Here:

- The `"` pair opens/closes the **Java string literal**.
- The two `''` characters are preserved in the Java string; when `MessageFormat` parses it, they produce one real `'`.
- `{` and `}` do not need escaping in a Java string literal.
- Double quotes `"` inside the Java string itself must be written `\"` per Java rules; double quotes are **not** special quoting characters in `MessageFormat`.

To include a **real** backslash in a Java string, use `\\` at the **Java source layer**. However, a backslash produced by Java does not neutralize braces in `MessageFormat`.

For example, these two strings are not functionally equivalent:

```java
String literalBracePattern = "'{'{0}'}'"; // MessageFormat quote
String backslashPattern = "\\{0}";      // Java escape for a literal \
```

With argument `OK`, the first pattern returns `{OK}`, whereas the second returns `\OK`. In the second pattern, `{0}` remains a placeholder and `\` is simply printed verbatim.

### 6.2. Patterns Read from `.properties` Files

Suppose **`messages.properties`** contains:

```properties
welcome=Xin chào {0}!
notice=It''s {0}.
quoted=Giá trị: ''{0}''.
braced=Nhập '{' và '}' để bao {0}.
literal=Mẫu '{0}' và giá trị {0}.
```

When read via `ResourceBundle` on Java 17+, these lines become **`MessageFormat` pattern strings**. In properties files, the `''` pair must still be preserved because it is required by **`MessageFormat`**, not by the properties parser.

Three things to remember about `.properties`:

1. In properties syntax, the single quote `'` **is not a default escape character**. The line `notice=It's {0}.` can still be read into the string `It's {0}.`, but **`MessageFormat` will misinterpret it**. You must write `It''s {0}.` when you want to display `It's ...`.
2. In properties files, the backslash **does** have its own escape role—for instance, `\n` can be converted to a newline character and `\\` represents a literal `\`. These rules execute **before** the string is passed to `MessageFormat`.
3. Writing `\'` in a properties file **is not a safe substitute** for `''`. After the properties parser runs, the single quote may still remain in the pattern and retain its special meaning to `MessageFormat`.

For Java 9+ (including Java 17), `PropertyResourceBundle` supports UTF-8 by default under the modern specification, with a legacy encoding compatibility mechanism. Store resources consistently in UTF-8 and verify your build/runtime pipeline; `MessageFormat`'s single-quote rules **do not change** just because a file uses UTF-8.

### 6.3. Patterns Passing Through More Formats

If a pattern passes through JSON, YAML, SQL, HTML templates, or a translation platform, **multiple escaping layers** may exist. For instance, double quotes `"` and backslashes `\` in JSON have their own rules; only the decoded string is parsed by `MessageFormat`. Do not guess how many times to double characters at each layer; inspect the **actual Java string received** right before `new MessageFormat(pattern, locale)`.

Document each layer clearly:

```text
Source file / Java string / JSON / properties
        ↓ (format-specific decoding rules)
Actual pattern String in the JVM
        ↓ (MessageFormat parser)
FormatElement + literal text
        ↓ (format with Object[])
Output message
```

This is why escaping in **Java source** is neither identical to **`MessageFormat`** escaping nor identical to **properties** escaping.

## 7. Complete Example: `ResourceBundle` Combined with `MessageFormat`

A localized project typically places patterns in bundles. This example uses the root bundle `messages.properties` at the classpath root so all results can be verified independently of the JVM's default language.

Create exactly two files:

```text
workspace/
├── BundleMessageFormatDemo.java
└── messages.properties
```

**`messages.properties`** (saved as UTF-8):

```properties
welcome=Xin chào {0}!
notice=It''s {0}.
quoted=Giá trị: ''{0}''.
braced=Nhập '{' và '}' để bao {0}.
literal=Mẫu '{0}' và giá trị {0}.
```

**`BundleMessageFormatDemo.java`:**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleMessageFormatDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", Locale.ROOT);
        Locale outputLocale = Locale.forLanguageTag("vi-VN");

        for (String key : new String[] {
                "welcome", "notice", "quoted", "braced", "literal"
        }) {
            String pattern = bundle.getString(key);
            MessageFormat formatter =
                    new MessageFormat(pattern, outputLocale);
            System.out.println(key + ": " +
                    formatter.format(new Object[] {"Lan"}));
        }
    }
}
```

From the `workspace` directory, run:

```bash
javac -encoding UTF-8 BundleMessageFormatDemo.java
java -cp . BundleMessageFormatDemo
```

Expected logical output (with a terminal properly displaying Unicode):

```text
welcome: Xin chào Lan!
notice: It's Lan.
quoted: Giá trị: 'Lan'.
braced: Nhập { và } để bao Lan.
literal: Mẫu {0} và giá trị Lan.
```

This example shows that a pattern can be translated as **text with placeholders** and loaded from a bundle while preserving quoting. When creating a bundle for another locale, verify that the new pattern has the right placeholder count and that `'`, `{`, and `}` are interpreted properly, rather than only diffing surrounding text.

**Note:** `ResourceBundle` has its own resource fallback mechanism; `MessageFormat` only receives the **value string** from `bundle.getString(key)` and parses the pattern. A bundle loading successfully does not prove every string inside it has valid `MessageFormat` syntax.

## 8. Subtle Bugs and How to Prevent Them

### 8.1. Confusing Natural-Language Apostrophes with Quoting Syntax

English frequently uses `don't`, `it's`, `user's`, and `you're`; French often has `l'utilisateur` and `d'accord`. If these sentences are placed directly into a `MessageFormat` pattern, the single quote can **swallow subsequent placeholders**.

Example:

```text
Wrong:   It's {0}.     → Its {0}.
Right:   It''s {0}.    → It's Lan.   (with {0} = Lan)
```

This can be a **silent bug** with no exception thrown. Testing actual rendered content is mandatory.

### 8.2. Quoting the Whole Placeholder When Only Quotes Around the Value Are Wanted

`'{0}'` renders the literal token `{0}` instead of the value. If you want a person's name inside single quotes, use `''{0}''`. If you want to print a placeholder in help documentation, `'{0}'` is the right form.

### 8.3. Using Backslash to Escape Single Quotes or Braces

`\` can carry meaning in Java source and properties files, but **it is not `MessageFormat`'s basic escape character**. Use `''` for a literal single quote, and `'{'` and `'}'` for literal braces.

### 8.4. Trying to Work Around Malformed Patterns by Catching Exceptions and Replacing Strings

A pattern like `Invalid {0` is invalid and can throw `IllegalArgumentException`. Treat syntax errors in bundles as **resource/translation bugs to fix**, rather than silently falling back to string replacement like `pattern.replace("{0}", value)`, because such replacement bypasses locale, format types, parent/bundle logic, and escaping rules.

### 8.5. Confusing Argument Data with Patterns

`MessageFormat` parses the **pattern**; it does not re-parse data passed into `format` as another pattern in standard substitution. If the data contains `O'Brien` or `{0}`, you do not need to quote it according to pattern syntax. Conversely, never pass **untrusted text** directly as a pattern without control, as it can alter placeholder behavior or cause parser errors.

### 8.6. Complex Patterns and Subformats

With syntax like `{0,number,...}`, `{0,date,...}`, or `{0,choice,...}`, the **format style** part has its own syntax (such as `DecimalFormat`, `SimpleDateFormat`, `ChoiceFormat`). `ChoiceFormat` can also contain subpatterns and special characters `|`, `#`, and `<`.

Therefore, when a pattern contains **nested subformats**, mechanically applying an outer-layer quoting table is not enough: you must understand **the subformat parser as well**. Test both branches that contain placeholders and branches that do not, especially when translations change quotes or braces. If complex plural/gender rules are required, consider a dedicated localization system built for the product's supported languages instead of stuffing hard-to-maintain conditional strings.

### 8.7. Double Quotes Differ from Single Quotes

In `MessageFormat`, a normal `"` is just a text character and **does not** substitute for `'` in patterns. However, if the pattern is written inside a **Java string literal**, `"` must be escaped according to Java syntax (`\"`). In a properties file, double quotes are handled differently from Java source. Always clarify which layer is being discussed.

### 8.8. Do Not Rely on `toPattern()` for Verbatim Comparison

`MessageFormat.toPattern()` returns a **pattern representation** of the object; it may normalize quoting. It is not guaranteed to match the input string character-for-character. Use `toPattern()` for diagnostics, while the final criterion remains **formatted output and actual placeholder behavior**.

## 9. How to Test Patterns in a Translation System

An effective validation workflow when supporting multiple locales:

1. **Identify the source pattern:** retrieve the exact value from `ResourceBundle`, distinct from keys and already-substituted strings.
2. **Validate structure:** construct `new MessageFormat(pattern, locale)` to catch many brace/format syntax errors early.
3. **Validate formatted content:** call `format` with representative arguments and assert expected output; do not merely check whether the parser accepts it.
4. **Test apostrophes in prose:** test words with real apostrophes (`don't`, `l'utilisateur`) and confirm trailing placeholders are still substituted.
5. **Test literal braces:** test patterns that must display `{`, `}`, or `{0}` as documentation or value delimiters.
6. **Test special-data arguments:** pass values like `O'Brien` and `{0}` as arguments; verify they are not misparsed as pattern syntax.
7. **Test every translation:** a valid Vietnamese version does not guarantee valid French or English versions; a translator may introduce a single quote that alters syntax.
8. **Test storage layers:** UTF-8, properties/JSON escaping rules, bundle caching, and the application build pipeline.
9. **Test subformat branches:** if `choice`, date/time, or numbers are used, test values exercising all critical branches. Formatting across locales/JDKs can differ, so snapshots should be tied to the tested runtime.

You can write unit tests for key patterns:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatAssertions {
    private static String apply(String pattern, Object value) {
        return new MessageFormat(pattern, Locale.ROOT)
                .format(new Object[] {value});
    }

    private static void require(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        require("It's Lan", apply("It''s {0}", "Lan"));
        require("{0}", apply("'{0}'", "Lan"));
        require("'Lan'", apply("''{0}''", "Lan"));
        require("{Lan}", apply("'{'{0}'}'", "Lan"));
        require("O'Brien", apply("{0}", "O'Brien"));
        System.out.println("5 checks passed");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 MessageFormatAssertions.java
java -cp . MessageFormatAssertions
```

When all conditions pass:

```text
5 checks passed
```

This example deliberately uses a custom assertion helper rather than Java's `assert` statement so checks always run, even without `-ea`.

## 10. Quick Reference Table

| Desired output | `MessageFormat` pattern | Note |
| --- | --- | --- |
| `Lan` from argument 0 | `{0}` | Normal value substitution |
| `It's Lan` | `It''s {0}` | Two single quotes in pattern produce one literal quote |
| `'Lan'` | `''{0}''` | Two quote pairs produce quotes wrapping the value |
| Literal `{0}` | `'{0}'` | Quote the whole placeholder to print the token |
| `{` | `'{'` | Quote opening brace |
| `}` | `'}'` | Quote closing brace |
| `{Lan}` | `'{'{0}'}'` | Quote both braces, not the placeholder |
| `O'Brien` as argument data | `{0}` with value `O'Brien` | Do not re-escape argument data as a pattern |

**Takeaway:** in `MessageFormat`, the single quote is a **quoting operator**; `''` is how you print a real single quote. Curly braces are reserved for placeholders, so use `'{'` and `'}'` to print them as literal text. Backslashes do not replace these two rules. Inspect patterns **after** Java/properties decoding and test **actual formatted output**, because many quoting mistakes throw no exception yet prevent placeholders from being substituted.
