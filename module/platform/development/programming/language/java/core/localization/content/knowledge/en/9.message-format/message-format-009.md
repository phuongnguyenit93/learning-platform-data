# MessageFormat: Missing Arguments, Null Values, Parsing, and Message Reversibility Limits

## Objectives

`java.text.MessageFormat` builds messages with numbered arguments like `{0}`, `{1}` and options for formatting numbers, dates, times, or choices. When displaying messages to users, it is easy to overlook that **missing or null inputs do not necessarily throw an exception**, and `parse(...)` is not a reliable inverse of `format(...)`.

After this lesson, you will be able to:

- Distinguish between **a missing argument element** and **an element that is present but `null`** in `Object[]`.
- Predict `MessageFormat` output when a placeholder points to an index beyond the supplied arguments.
- Understand how `MessageFormat.parse(...)` uses a pattern to extract an `Object[]` array and when it fails.
- Inspect `ParsePosition` and distinguish partial parse success from consuming the entire string.
- Explain cases where exact input recovery is impossible: repeated placeholders, rounding, `choice`, delimiter-containing inputs, and arguments unreferenced in the pattern.
- Design error handling and testing for localization without assuming `parse(format(args)) == args`.

This lesson focuses on **edge-case behavior of MessageFormat in Java 17+**. Mechanisms for selecting `Locale`, translating source text, and managing `ResourceBundle` are mentioned only where they affect pattern correctness.

## 1. What Does MessageFormat Do with Arguments?

A message pattern:

```text
Hello {0}! Your order {1} is ready.
```

Components:

- Static text `Hello` and `Your order ... is ready.` is copied to the output per the pattern.
- `{0}` reads the argument at index **0** in the argument array.
- `{1}` reads the argument at index **1**.
- Extended elements like `{2,number,integer}` or `{3,date,short}` invoke the corresponding formatter.

Example:

```java
MessageFormat mf = new MessageFormat(
        "Hello {0}! Your order {1} is ready.",
        Locale.US
);
String text = mf.format(new Object[] {"Ana", "A-42"});
```

This is an in-method illustrative snippet with `import java.text.MessageFormat;` and `import java.util.Locale;`. The value of `text` is:

```text
Hello Ana! Your order A-42 is ready.
```

Indices in a pattern are not variable names. They specify positions in the `Object[]` array supplied to `format`. Patterns can reverse display order: `{1}` can appear before `{0}`; this is helpful for language grammar.

**MessageFormat's contract is to render a string according to a pattern**, not to guarantee that the resulting string can be parsed back to recover the original data.

## 2. Missing Arguments: Keeps `{n}` Intact Without Throwing

Suppose a pattern references `{0}` and `{1}`, yet the caller passes only one element:

```java
MessageFormat mf = new MessageFormat(
        "Hello {0}! State={1}.", Locale.US);

System.out.println(mf.format(new Object[] {"Ana"}));
```

Output:

```text
Hello Ana! State={1}.
```

`{1}` is **not substituted** because the array has no element at index 1. Under the Java 17 `MessageFormat` contract, if an argument is unavailable (the array is `null` or lacks enough elements), the corresponding format element is emitted as `{argumentIndex}`.

Cases worth distinguishing:

| Array passed | Output with pattern `Hello {0}! State={1}.` |
| --- | --- |
| `new Object[] {"Ana", "ready"}` | `Hello Ana! State=ready.` |
| `new Object[] {"Ana"}` | `Hello Ana! State={1}.` |
| `new Object[] {}` | `Hello {0}! State={1}.` |
| `new Object[] {"Ana", null}` | `Hello Ana! State=null.` |
| `new Object[] {null, "ready"}` | `Hello null! State=ready.` |

**Do not confuse this with `String.format` or `Formatter`.** Those APIs use different format syntax (such as `%s`) and have their own contract for missing arguments. With `MessageFormat`, missing placeholders in the cases above remain as `{n}`; do not assume it will throw `MissingFormatArgumentException`.

Implications:

1. If a screen unexpectedly displays `{1}`, inspect both the argument array and the translated pattern.
2. Do not treat `format(...)` completing without error as proof that the application supplied all required data.
3. Do not treat the appearance of `{1}` as the sole check for missing arguments: static text can also contain similar characters if the pattern has valid escaping.

### Detecting Missing Arguments Before Formatting

When the content contract is fixed, the clearest approach is to validate input count and types at the business API:

```java
static String orderNotice(String customer, String orderId, Locale locale) {
    if (customer == null || orderId == null) {
        throw new IllegalArgumentException("Customer and orderId are required");
    }

    MessageFormat mf = new MessageFormat(
            "Hello {0}, order {1} is ready.", locale);
    return mf.format(new Object[] {customer, orderId});
}
```

This is an **illustrative method**, placed in a class importing `MessageFormat` and `Locale`. Validate inputs based on business semantics, not on whether `MessageFormat` throws an exception.

With patterns loaded from `ResourceBundle` where translators can reorder indices, do not count "whether two brace pairs exist" with simple regex. Patterns support escaping, nested formats (especially with `choice`), and repeated indices. Define an independent **parameter contract**, use an appropriate pattern parser/validator, and test each locale.

## 3. Null Arguments: A Different Case from Missing Arguments

`new Object[] {"Ana"}` has no element at index 1. By contrast, `new Object[] {"Ana", null}` has two elements, with **the value at index 1 being `null`**.

By `MessageFormat.format` rules, an argument that is present and `null` is rendered as the string `"null"`.

```java
MessageFormat mf = new MessageFormat(
        "Item={0}; Quantity={1,number,integer}",
        Locale.US);

System.out.println(mf.format(new Object[] {null, null}));
```

Stdout:

```text
Item=null; Quantity=null
```

Before applying a specific subformat such as `number`, `MessageFormat` converts a `null` argument into the text `null`. Thus a `null` at `{1,number,integer}` in this example does not automatically produce `0` or force a type error.

This has several implications:

- `null` does not mean "use an empty string".
- `null` does not mean "omit this message element".
- `null` does not mean "fall back to a default value from ResourceBundle".
- The string `"null"` appearing in a message is a sign to investigate data, **not a user-friendly message to display**.

If the domain requires a different message when data is absent, choose explicitly at the application layer:

```java
String nameToShow = (name == null || name.isBlank())
        ? "guest"
        : name;

String text = new MessageFormat(
        "Hello {0}", Locale.US)
        .format(new Object[] {nameToShow});
```

This is an illustrative snippet inside a method, where `name` is declared as a `String`. In a multilingual application, the word `guest` should come from localized resources or use a separate message pattern rather than hardcoding English in production code.

### `null` and the String `"null"` Are Indistinguishable in Output

Compare:

```java
MessageFormat mf = new MessageFormat("{0}", Locale.US);
String fromNull = mf.format(new Object[] {null});
String fromText = mf.format(new Object[] {"null"});
```

Both resulting strings are `"null"`. Information about "whether this was `null` or an original four-letter string n-u-l-l" has been lost. Even with a parser, there is no reliable way to work backward from this output to recover the original object.

This is a simple example showing that formatting is not necessarily a one-to-one mapping.

## 4. How Do `parse(String)` and `parse(String, ParsePosition)` Differ?

`MessageFormat` supports **parsing**: analyzing a string against the static text segments and format elements in a pattern to return an `Object[]`.

Three related APIs:

| API | On success | On failure |
| --- | --- | --- |
| `parse(String source)` | Returns `Object[]` parsed from the beginning of the string | Throws `ParseException` if unable to parse from the start of input |
| `parse(String source, ParsePosition pos)` | Returns `Object[]` and advances `pos.getIndex()` | Returns `null`, sets `pos.getErrorIndex()`; current index does not advance past the error |
| `parseObject(String, ParsePosition)` | Also parses into an `Object[]`, with return type `Object` per `Format` contract | Returns `null` when parsing fails |

Simple example:

```java
MessageFormat fmt = new MessageFormat(
        "ID={0};", Locale.US);

Object[] values = fmt.parse("ID=42;");
System.out.println(values[0]);
```

This is an illustrative snippet inside a method declaring or handling `ParseException`, importing `MessageFormat`, `ParseException`, and `Locale`. Stdout is `42` (a `String` because `{0}` specifies no subformat).

If the pattern uses `{0,number}`, the parsed result may be a `Number` object determined by the numeric formatter; do not cast unconditionally to `String`.

### `parse` May Consume Only a Prefix

With `ParsePosition`:

```java
MessageFormat fmt = new MessageFormat("ID={0};", Locale.US);
String input = "ID=42;tail";
ParsePosition pos = new ParsePosition(0);
Object[] values = fmt.parse(input, pos);

System.out.println(values[0]);
System.out.println(pos.getIndex());
System.out.println(input.length());
```

This is an illustrative snippet inside a method importing `java.text.ParsePosition` and related types. Stdout:

```text
42
6
10
```

The parser matches `ID=42;` (6 characters) and **leaves `tail` unconsumed**. `parse(String)` likewise **does not promise** to consume the entire input: it only parses starting from the beginning of the string.

If the application requires the entire input to match, use `ParsePosition` and check:

```java
ParsePosition pos = new ParsePosition(0);
Object[] parsed = fmt.parse(input, pos);
boolean complete = parsed != null && pos.getIndex() == input.length();
```

This is only a **necessary condition for full-string parsing**, not a guarantee that the original arguments are faithfully recovered; information-loss cases are covered below.

### When Parsing Fails

Suppose the pattern is `"ID={0};"` and the input is `"BAD=42;"`. The prefix does not match `ID=`, so:

```java
ParsePosition pos = new ParsePosition(0);
Object[] parsed = fmt.parse("BAD=42;", pos);

System.out.println(parsed == null);
System.out.println(pos.getIndex());
System.out.println(pos.getErrorIndex());
```

With `fmt` created above, the output is:

```text
true
0
0
```

`getErrorIndex()` indicates the position where the parser detected the error (here, the first character). When using complex subformats, the error index is not a complete semantic diagnostic: it aids troubleshooting, rather than replacing application-defined error messages.

If you use `parse(String)` instead of the `ParsePosition` overload, this same case throws `ParseException`. Catch the error and report an appropriate reason when handling real inputs.

## 5. Why `parse` Is Not a Reliable Inverse of `format`

A transformation is fully invertible only if the original input can be uniquely determined from the final output. `MessageFormat` does not guarantee this property because it is designed for **message display**, and format elements can truncate or collapse multiple values into the same string.

There are five important categories of issues.

### 5.1. Elements Absent from the Pattern Are Lost

Suppose the original array has three elements:

```java
Object[] args = {"Ana", "A-42", "hidden"};
MessageFormat mf = new MessageFormat(
        "Hello {0}, order {1}", Locale.US);
String result = mf.format(args);
```

There is no `{2}` in the pattern, so `hidden` never appears in the output. The parser cannot reconstruct that element from the string. **Every unrepresented element loses its information.**

Likewise, two distinct arrays can produce the exact same message because some arguments are unused.

### 5.2. An Argument Appearing Multiple Times: Last Parse Wins

A pattern can reuse `{0}` multiple times:

```java
MessageFormat repeated = new MessageFormat("{0}|{0}", Locale.US);
Object[] parsed = repeated.parse("A|B");
System.out.println(Arrays.toString(parsed));
```

This is an illustrative snippet inside a method importing `java.util.Arrays`, handling or declaring `ParseException`. Stdout:

```text
[B]
```

The same index `{0}` is parsed twice; **the later match supplies the final value**. The parser does not verify that `A` and `B` are equal. Nor is this a validation rule for repeated data; check consistency explicitly if the input requires both positions to match.

Format elements sharing the same index with different formats lose data even more easily; only one parsed result is returned per index.

### 5.3. Delimiters Inside Data Cause Ambiguity

Given the pattern:

```text
{0},{1}
```

If `args[0]` is `"a,b"` and `args[1]` is `"c"`, the formatted output is:

```text
a,b,c
```

When parsing back, however, the first comma can be interpreted as the pattern's delimiter:

```java
MessageFormat mf = new MessageFormat("{0},{1}", Locale.US);
String rendered = mf.format(new Object[] {"a,b", "c"});
Object[] restored = mf.parse(rendered);

System.out.println(rendered);
System.out.println(restored[0] + "|" + restored[1]);
```

Output:

```text
a,b,c
a|b,c
```

The original arguments were `["a,b", "c"]`, yet parsing returns `["a", "b,c"]`. Both splits produce the exact same rendered message. It is impossible to determine the intended split when delimiters are permitted inside values without an explicit escaping or length-prefixing scheme.

If the application needs to transmit structured data, use JSON or a data format with a clear parsing contract; never use localized messages as a protocol.

### 5.4. Subformats Lose Precision or Type Identity

`{0,number,integer}` can produce a rounded number or discard fractional digits; `{0,number,#.##}` can drop digits past the second decimal place. `{0,date,short}` can omit hours, minutes, seconds, and original time zone information.

For example, formatting both `3.141` and `3.142` with a pattern limited to one decimal place yields `3.1`. Parsing `3.1` cannot tell which number was the original input.

`MessageFormat` can delegate to subformats that return `Number` or `Date` when parsing. However, **identical displayed values do not imply identical Java types or precision**. Do not assume the returned object has the exact original Java type (`BigDecimal`, `Integer`, `Long`, etc.).

### 5.5. ChoiceFormat Collapses Ranges of Values into One Message

A `choice` pattern can map an entire range of values to a single label:

```java
MessageFormat choice = new MessageFormat(
        "{0,choice,0#none|1#one|2#many}",
        Locale.US
);

String text = choice.format(new Object[] {999});
Object[] parsed = choice.parse(text);

System.out.println(text);
System.out.println(parsed[0]);
```

This is an illustrative snippet inside a method handling `ParseException`. Stdout:

```text
many
2.0
```

Input `999` becomes `many`, yet when parsing, Java returns the threshold value bound to that branch (`2.0`), **not `999`**. This is intentional information loss from interval-based message selection.

`ChoiceFormat` also has cases where subpatterns reference placeholders like `{0}`. The `MessageFormat` documentation warns that the parser does not fully handle recursive cases; do not build symmetric round-trip parsing contracts on complex nested `choice` patterns.

## 6. `null` Also Limits Reversibility

Consider:

```java
MessageFormat plain = new MessageFormat("{0}", Locale.US);

String a = plain.format(new Object[] {null});
String b = plain.format(new Object[] {"null"});

System.out.println(a.equals(b));
```

Output:

```text
true
```

Calling `plain.parse("null")` with an untyped placeholder yields the string `"null"`, which cannot prove the prior input was a `null` reference. Conversely, if the pattern is `"{0,number,integer}"`, formatting a `null` argument still produces the text `null`, while parsing the literal text `null` with a numeric subformat may fail.

In other words:

- **Being formatable** does not mean **parseable back to the original form**.
- **Being parseable** does not mean **preserving `null` semantics**.
- Even typed patterns provide no perfect round-trip guarantee.

For input data with states such as "unknown", "not provided", or "not applicable", model that state explicitly (e.g., `Optional` or a dedicated status field) and select the corresponding sentence pattern. Never ask users or other systems to infer state from the word `null` in the UI.

## 7. Comprehensive Java 17+ Example: Observing Edge Cases

Create the file `MessageFormatEdgeDemo.java`:

```java
import java.text.MessageFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Arrays;
import java.util.Locale;

public class MessageFormatEdgeDemo {
    public static void main(String[] args) throws ParseException {
        Locale locale = Locale.US;

        MessageFormat greeting = new MessageFormat(
                "Hello {0}! State={1}.", locale);

        System.out.println(greeting.format(new Object[] {"Ana"}));
        System.out.println(greeting.format(new Object[] {"Ana", null}));
        System.out.println(greeting.format(new Object[] {}));

        MessageFormat repeated = new MessageFormat("{0}|{0}", locale);
        System.out.println(Arrays.toString(repeated.parse("A|B")));

        MessageFormat ambiguous = new MessageFormat("{0},{1}", locale);
        String message = ambiguous.format(new Object[] {"a,b", "c"});
        Object[] recovered = ambiguous.parse(message);
        System.out.println(message);
        System.out.println(recovered[0] + "|" + recovered[1]);

        MessageFormat choice = new MessageFormat(
                "{0,choice,0#none|1#one|2#many}", locale);
        String text = choice.format(new Object[] {999});
        System.out.println(text + " -> " + choice.parse(text)[0]);

        MessageFormat id = new MessageFormat("ID={0};", locale);
        String input = "ID=42;tail";
        ParsePosition pos = new ParsePosition(0);
        Object[] values = id.parse(input, pos);
        System.out.println("value=" + values[0]
                + ", consumed=" + pos.getIndex()
                + "/" + input.length());

        ParsePosition bad = new ParsePosition(0);
        Object[] failed = id.parse("BAD=42;", bad);
        System.out.println("failed=" + (failed == null)
                + ", errorIndex=" + bad.getErrorIndex());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 MessageFormatEdgeDemo.java
java MessageFormatEdgeDemo
```

Deterministic stdout with the patterns and `Locale.US` above:

```text
Hello Ana! State={1}.
Hello Ana! State=null.
Hello {0}! State={1}.
[B]
a,b,c
a|b,c
many -> 2.0
value=42, consumed=6/10
failed=true, errorIndex=0
```

Observations:

1. `{1}` stays intact when the array lacks index 1; when that index exists and is `null`, the output shows `null`.
2. `parse("A|B")` returns only `B` for the two uses of index 0.
3. `"a,b,c"` is parsed into `a` and `b,c`, differing from the original array.
4. `choice` turns a large number into the label `many`; parsing the label yields `2.0`, not `999`.
5. `ParsePosition` stops at index 6 in a 10-character string; a partial parse must not automatically count as fully valid input.
6. `BAD=42;` does not match static text `ID=`, so `parse` returns `null` with `errorIndex=0`.

This example demonstrates API behavior, not a recommendation to use `MessageFormat.parse` to handle user input in production applications.

## 8. Properly Validating Parse Success

When you genuinely need `parse` for a relatively simple structured message, verify at least:

1. **A result exists:** `parsed != null` (with the `ParsePosition` overload).
2. **Entire input consumed:** `position.getIndex() == input.length()`.
3. **Value count and types:** the result includes the required arguments with expected types; remember that indices absent from the pattern cannot be recovered.
4. **Business rules:** e.g., quantities within valid bounds, well-formed IDs, valid dates/times per domain rules.
5. **No design ambiguity:** patterns where values can contain delimiters or subformats lose data can make parsing "succeed" with wrong results.

You can write a helper that enforces a full-string parse:

```java
import java.text.MessageFormat;
import java.text.ParsePosition;

public final class CompleteMessageParse {
    private CompleteMessageParse() {}

    public static Object[] parseFully(
            MessageFormat format, String input) {
        if (input == null) {
            throw new IllegalArgumentException("Input is required");
        }

        ParsePosition position = new ParsePosition(0);
        Object[] result = format.parse(input, position);

        if (result == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException(
                    "Message does not match the full pattern");
        }
        return result;
    }
}
```

This is a compilable class `CompleteMessageParse.java`, though it has no `main` method to run directly. This function helps **reject inputs that do not match completely**; it **does not solve** ambiguous delimiters, precision loss, repeated arguments, or `null`. Do not call it a lossless general-purpose parser.

For critical inputs (APIs, persistence, finance, configuration), use schemas, parsers, and data types designed specifically for input. Translated messages are a **presentation format**, editable by translators and varying by locale; they are not a stable data protocol.

## 9. MessageFormat, ResourceBundle, and Localization Risks

Applications typically load patterns by locale:

```properties
# messages.properties
order.status=Order {0} contains {1,number,integer} items.
```

```properties
# messages_vi.properties
order.status=Đơn hàng {0} có {1,number,integer} sản phẩm.
```

When formatting in code:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("messages", locale);
String pattern = bundle.getString("order.status");
String text = new MessageFormat(pattern, locale)
        .format(new Object[] {"A-42", 3});
```

This is an illustrative snippet inside a method with `locale` of type `Locale`; the properties files must reside on the classpath with base name `messages`.

There are specific risks related to missing/null/parsing:

- Translators may accidentally delete `{1}` or change it to `{2}`. At runtime, a missing placeholder can appear verbatim; if a placeholder is omitted from the pattern, the corresponding element disappears.
- Translators may change punctuation placement, word order, or separators. The pattern still formats properly, yet parsing a translated message can alter splits and returned objects.
- Single quotes `'` and curly braces have special meaning in `MessageFormat` syntax. A translated string containing an unescaped apostrophe can turn placeholders into static text. In `MessageFormat`, a literal single quote typically requires `''`; test with the real parser rather than just eyeing the file.
- Numbers/dates depend on locale and formatting data. A string emitted under `Locale.US` is not guaranteed to parse properly under `Locale.FRANCE`.
- A `null` input can print the word `null` in any locale; choose dedicated fallback messages fitting the application's tone.

Therefore, your test pipeline must evaluate **each locale's patterns**, index counts, subformats, repeated placeholders, and missing/null cases. Specifically, never use "trial formatting succeeds" as the sole check: the API can accept missing inputs and leave `{n}` placeholders behind.

### Managing Parameter Contracts

A solid contract for message keys should document:

| Key | Argument | Meaning |
| --- | --- | --- |
| `order.status` | `{0}` | Order ID, `String`, required |
| `order.status` | `{1}` | Item count, `Number`, required, integer format |
| `account.greeting` | `{0}` | Display name, required; separate branch for unauthenticated guests |

This helps catch translations that accidentally drop an index or expect the wrong data type. Argument count **cannot be fully validated merely by running `format`** because missing indices do not always throw exceptions.

When users can submit names containing commas, quotes, or arbitrary characters, messages can still display normally; avoiding reverse parsing becomes all the more important. If machine-readable data is needed, keep the original objects alongside the formatted message.

## 10. Common Mistakes and Fixes

| Mistake | Result / risk | Correct approach |
| --- | --- | --- |
| Assuming missing `{1}` throws an exception | `MessageFormat` may display `{1}` literally | Validate the parameter contract before formatting |
| Assuming a `null` argument yields an empty string | Java typically prints the text `null` | Choose a fallback message or handle missing values explicitly |
| Treating the text `null` as proof the original data was `null` | Literal string `"null"` renders identically | Preserve source state in the model |
| Calling `parse(String)` without checking remaining characters | Parser may consume only a prefix | Use `ParsePosition` and verify the final index |
| Treating parse success as an exact inverse | Delimiters, `choice`, and rounding lose data | Use structured data for operations needing round-tripping |
| Mentioning `{0}` twice and trusting the parser to verify equality | Later parsed value overwrites earlier one | Validate consistency explicitly if needed |
| Seeing `parse` return `Number` and casting unconditionally to `Integer` | `NumberFormat`/`ChoiceFormat` may return other numeric types | Check type/value and convert safely |
| Using translated patterns as a protocol | Translators can alter punctuation, order, and grammar | Separate UI formatting from data protocols |
| Using `MessageFormat`'s parser to verify complete placeholders in translations | The parser does not enforce an i18n content contract | Lint patterns and check argument contracts per locale |
| Ignoring single quotes or `{ }` | Placeholders can become literals or cause pattern errors | Test actual patterns through `MessageFormat` |
| Relying on an implicit default locale in tests | Number/date outputs can differ on CI | Pass `Locale` explicitly |
| Sharing and mutating one `MessageFormat` across threads | Format instances hold mutable state; format/parse are not thread-safe | Use separate instances, proper synchronization, or avoid sharing mutable objects |

## 11. Self-Check Exercises

**Exercise 1 — Missing vs. null.** Given the pattern `"Name={0}; Age={1,number,integer}"`, predict the output when passing `new Object[] {"Linh"}` versus `new Object[] {"Linh", null}`. Why do the outputs differ even though both mean "no age" from a business perspective?

**Exercise 2 — Unconsumed tail in parse.** Given the pattern `"ID={0};"` and the string `"ID=42;ignored"`, use `ParsePosition` to determine how many characters are consumed. Why is checking `parsed != null` alone insufficient?

**Exercise 3 — Repeated index.** With the pattern `"{0}|{0}"`, what does parsing `"A|B"` return? Is there any automatic mechanism requiring both occurrences of `{0}` to be equal?

**Exercise 4 — Delimiters.** Use `"{0},{1}"` to format `["x,y", "z"]`. Why can parsing the output not reliably recover the original array? Name a more suitable data format for exchange between two services.

**Exercise 5 — Precision.** Use `{0,number,#.#}` with `3.14` and `3.11`. Both outputs can become `3.1`; when parsing, can the dropped fractional digits be recovered?

**Exercise 6 — Choice.** Given the pattern `"{0,choice,0#none|1#one|2#many}"` and input `999`, what are the format and parse results? Why does the parser return a branch threshold instead of the original number?

**Exercise 7 — Localization.** A translator replaces `"Order {0}: {1,number,integer} items"` with `"Đơn hàng {0}: {2} sản phẩm"`. Identify which argument contract rule is broken and how to catch it in tests.

## 12. Key Takeaways

`MessageFormat` is designed to **produce formatted messages**, not to serve as a lossless, fully invertible data encoder/decoder. If the argument array lacks a referenced index, Java may leave `{n}` intact; if the element exists and is `null`, Java displays the text `null`. Both cases have distinct meanings and must be handled at the business layer.

`parse` can extract some arguments matching a pattern, yet **success does not imply a complete match, much less lossless recovery**. Always check `ParsePosition` when full-string consumption is required, and recognize ambiguity, repeated indices, rounding subformats, `choice`, omitted data, and `null`. For data that must stay intact, transmit and store **structured source objects**, use `MessageFormat` at the presentation layer, and test every translated pattern against its parameter contract.

API documentation: [`MessageFormat` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html), [`ParsePosition` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html).
