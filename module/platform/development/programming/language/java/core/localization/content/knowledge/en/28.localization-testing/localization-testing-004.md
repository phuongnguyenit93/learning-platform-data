# Testing Single Quotes, Braces, and MessageFormat Patterns in Java

## 1. Why Is This Testing Important?

`java.text.MessageFormat` inserts data into localized sentences. Instead of manual string concatenation, a pattern such as:

```text
Xin chào, {0}! Bạn có {1,number,integer} thông báo.
```

allows translators to reorder parameters when needed. However, `MessageFormat` **does not treat a pattern like plain text**. Two kinds of characters have special syntactic roles:

- The straight single quote `'` (U+0027) starts/ends a literal region (*quoted text*).
- Opening `{` and closing `}` braces delimit a *format element*, such as `{0}` or `{1,number,integer}`.

Consequently, localized sentences containing `You're`, `It's`, JSON examples like `{"name": "{0}"}`, or literal `{0}` are easily mishandled. Especially dangerous: **an unclosed single quote does not necessarily throw an exception**. The parser can treat the end of the pattern as closing the quoted region and **stop substituting placeholders** silently.

This lesson belongs to the **testing and pitfalls** section of Java localization, focusing on:

1. Understanding `MessageFormat` syntax and quoting scope.
2. Writing single quotes, literal braces, and placeholders properly.
3. Verifying output for simple patterns, number patterns, `choice`, and nested patterns.
4. Detecting syntax errors, patterns that are valid yet produce the **wrong meaning**, and missing/mismatched arguments.
5. Testing patterns loaded from `ResourceBundle`, `.properties` files, and translation data.
6. Structuring a runnable Java 17+ test suite to prevent regressions when adding or editing translations.

Key takeaway: **a pattern that does not throw an exception is not guaranteed to format properly**. You must test **expected output** with representative data.

## 2. Basic MessageFormat Syntax

A format element has the general form:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Examples:

```text
Hello, {0}!
Amount: {1,number,#,##0.00}
Date: {2,date,short}
{3,choice,0#none|1#one|1<{3,number,integer} items}
```

Components:

| Component | Meaning |
|---|---|
| `argumentIndex` | Non-negative index into the `Object[]` array, starting at 0 |
| `formatType` | For example `number`, `date`, `time`, `choice` |
| `formatStyle` | For example `integer`, `short`, a `DecimalFormat` pattern, or `ChoiceFormat` rules |
| Text outside format elements | Literal string following `MessageFormat` quoting rules |
| `'` | Controls literal quoting in the pattern; `''` is needed to display one straight single quote |
| `{` | Opens a format element, unless quoted |
| `}` | Closes a format element, or acts as a literal depending on context and parser tolerance |

A standalone API example:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class HelloMessage {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Hello, {0}! You have {1,number,integer} messages.",
                Locale.US);

        System.out.println(
                message.format(new Object[]{"Mai", 2}));
    }
}
```

Run:

```bash
javac HelloMessage.java
java HelloMessage
```

Output:

```text
Hello, Mai! You have 2 messages.
```

`{0}` and `{1,number,integer}` are **pattern syntax**, not content printed verbatim. To print the literal string `{0}`, you must quote it properly.

`java.text.MessageFormat` is a different API from `String.format` (`%s` syntax) and `java.time.format.DateTimeFormatter` (date pattern letters). Do not apply one API's escaping rules to another.

## 3. Single-Quote Rules: ' and '' Are Not the Same

In `MessageFormat`, the **ASCII straight single quote** `'` serves two roles:

- A single quote begins or ends a quoted literal region.
- **Two consecutive single quotes `''`** represent **one** literal single quote in the output.

Examples:

| Pattern | Argument | Output | Explanation |
|---|---|---|---|
| `You''re invited, {0}.` | `Mai` | `You're invited, Mai.` | Two single quotes yield one quote |
| `You're invited, {0}.` | `Mai` | `Youre invited, {0}.` | Unclosed single quote turns the rest into a literal |
| `'{0}'` | `Mai` | `{0}` | Placeholder is quoted so it is not substituted |
| `''{0}''` | `Mai` | `'Mai'` | Two quotes on each side; placeholder still works |
| `It's {0}` | `Mai` | `Its {0}` | Valid pattern that yields the wrong result |
| `A '' B` | Not needed | `A ' B` | Prints a single quote |

**Do not use `\` as a substitute for `''` in `MessageFormat`.** Backslash is an escape character in many other languages/formats, not the direct quoting mechanism for single quotes in a `MessageFormat` pattern.

For instance, writing:

```text
You're invited, {0}.
```

looks right in a translation file yet fails when passed verbatim to `MessageFormat`. Changing it to:

```text
You''re invited, {0}.
```

preserves the apostrophe and substitutes `{0}`. Single quotes in translations must be tested because they appear naturally in English, French, and many other languages.

### Curly Quotes Differ from Straight Quotes

The character `’` (U+2019, *right single quotation mark*) is a distinct Unicode character from `'` (U+0027). It is **not a syntactic quote character** in `MessageFormat`.

Therefore, a translation using a curly apostrophe like `It’s {0}` does not trigger ASCII apostrophe quoting the way `It's {0}` does. However, **do not rely on swapping punctuation styles to dodge programming bugs**: typography, accessibility, and copy/paste conventions belong to content policy. For ASCII apostrophes, you still must escape them as `''` in patterns.

## 4. Unclosed Single Quotes Can Auto-Close at the End of a Pattern

A major hazard with `MessageFormat` is that a pattern with an unclosed quote may **not throw `IllegalArgumentException`**. The parser can treat the end of the pattern as implicitly closing the quoted span.

Example:

```java
MessageFormat message =
        new MessageFormat("It's {0}", Locale.US);

System.out.println(
        message.format(new Object[]{"Mai"}));
```

This snippet (requiring imports for `MessageFormat`, `Locale`) prints:

```text
Its {0}
```

Explanation:

1. `It` is normal text.
2. The `'` before `s` opens a literal region and **is not printed**.
3. The characters `s {0}` are treated as literal up to the end of the pattern.
4. Placeholder `{0}` is no longer replaced with `Mai`.
5. The pattern is accepted rather than rejected with a syntax exception.

Another case:

```text
Pattern: A ' B {0}
Output:  A  B {0}
```

You cannot simply run:

```java
new MessageFormat(pattern, locale);
```

and conclude a translation is sound. **Testing actual output or inspecting placeholder structure** is required to catch this silent failure mode.

The proper pattern fix:

```text
It''s {0}
```

Now `{0}` is once again substituted with the argument.

## 5. Braces and Literal Placeholders

In a pattern, `{` is normally interpreted as **opening a format element**. If a string contains technical examples, JSON, templates, or expressions like `{id}` that are not `MessageFormat` placeholders, the parser may try to parse them and fail.

### Printing Literal {0}

Use:

```text
'{0}'
```

Result:

```text
{0}
```

The placeholder sits **inside a quoted region**, so it is not substituted.

### Wrapping an Argument Value in Braces

Use:

```text
'{'{0}'}'
```

With argument `Mai`, output:

```text
{Mai}
```

Three distinct parts:

- `'{'`: literal opening brace.
- `{0}`: actual placeholder.
- `'}'`: literal closing brace.

This is the reliable way to display an argument inside braces without turning the braces into format-element syntax.

### Printing Single Quotes Around a Value

Use:

```text
''{0}''
```

With `Mai`, output:

```text
'Mai'
```

Do not use `'{0}'` if your goal is to **substitute the value and wrap it in quotes**; that pattern prints the literal `{0}`.

### Standalone Closing Brace

In the verified `MessageFormat` implementation, the pattern `Bad }` **does not throw an error** and prints `Bad }`. Do not infer that **all opening/closing braces are checked symmetrically by the parser**. For predictable behavior in translations and technical text examples, explicitly quote `'}'` whenever possible.

## 6. Complete Java 17+ Example: Key Quoting Cases

Save `MessageQuoteDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        Object[] values = {"Mai", 2, 1234.5};

        String[] patterns = {
                "You''re invited, {0}.",
                "Literal '{0}' plus {0}",
                "''{0}''",
                "'{'{0}'}'",
                "JSON: '{'\"name\": \"{0}\"'}'",
                "It's {0}"
        };

        for (String pattern : patterns) {
            MessageFormat message =
                    new MessageFormat(pattern, Locale.US);

            System.out.println(message.format(values));
        }
    }
}
```

Compile/run:

```bash
javac MessageQuoteDemo.java
java MessageQuoteDemo
```

JDK-verified output:

```text
You're invited, Mai.
Literal {0} plus Mai
'Mai'
{Mai}
JSON: {"name": "Mai"}
Its {0}
```

The last two lines deserve special attention:

- The JSON example uses `'{'` and `'}'` for the fixed braces while keeping `{0}` as a placeholder.
- The line `Its {0}` is an **intentionally wrong result** demonstrating an unclosed single-quote bug. A product test must treat this as **FAIL** if `It's Mai` is expected.

Using the `\"` escape in the **Java string literal** of the JSON example represents the double-quote character `"` in Java code. That belongs to the **Java source** syntax layer, completely separate from `MessageFormat`'s single-quote rules.

## 7. Two Syntax Layers: Java String Literals and MessageFormat Patterns

When a pattern lives in Java source code, distinguish:

**Layer A — Java compiler:** decodes Java string literal escapes, such as `\"` or `\\`.

**Layer B — MessageFormat:** receives the `String` after the Java compiler processes it, then parses `'`, doubled `''`, braces, and format elements.

Example:

```java
String pattern = "JSON: '{'\"name\": \"{0}\"'}'";
```

After Java decodes the string literal, `MessageFormat` sees:

```text
JSON: '{'"name": "{0}"'}'
```

After `MessageFormat` processes it with argument `Mai`, result:

```text
JSON: {"name": "Mai"}
```

**Do not count backslashes in Java source as if they were part of `MessageFormat` quoting rules.**

If a pattern comes from a `.properties` file, it does not pass through the Java source-string parser like `"..."`. However, `.properties` has **its own escape rules**, such as line-continuation backslashes or `\uXXXX`; after loading the file, the resulting pattern content is parsed by `MessageFormat`.

If a pattern comes from a JSON API, it passes through JSON string escaping instead. Hence, the same pattern across storage formats may require **different escapes at the storage layer**, while the final `MessageFormat` rules remain unchanged.

## 8. JSON and Text Containing Braces

A common task is displaying:

```text
JSON: {"name": "Mai"}
```

The unambiguous pattern is:

```text
JSON: '{'"name": "{0}"'}'
```

In Java source, escape double quotes when written inside `"..."`:

```java
String pattern = "JSON: '{'\"name\": \"{0}\"'}'";
String result = new MessageFormat(
        pattern, Locale.US).format(new Object[]{"Mai"});
```

Verified result:

```text
JSON: {"name": "Mai"}
```

If the entire JSON content comes from an already prepared argument:

```java
new MessageFormat("Payload: {0}", Locale.US)
        .format(new Object[]{"{\"name\":\"Mai\"}"});
```

the argument `{"name":"Mai"}` is inserted as **argument data**, not automatically parsed as `MessageFormat` syntax during normal substitution.

However, **inserting a string into JSON via `MessageFormat` does not guarantee valid JSON**: if the value contains double quotes, backslashes, newlines, or special content, use a proper JSON serializer. `MessageFormat` is not a JSON encoder and not a safe tool for building machine-to-machine data.

### Literal Braces and Invalid Opening Elements

These two patterns are not equivalent:

```text
User: '{0}'        -> Prints the characters {0}
User: {0}          -> Inserts the value of argument 0
```

Pattern `Bad {0` has an unclosed opening brace, so it is not a valid format element. Pattern `Bad {{0}}` has an invalid nested opening brace at the argument-index position, and is also rejected in the JDK example.

Do not use the "add another `{`" trick from some template engines to escape braces. **`{{0}}` is not `MessageFormat`'s brace-escaping syntax**.

## 9. Invalid Patterns and Behavior to Test

Some errors are caught immediately when constructing `MessageFormat`, typically via `IllegalArgumentException`:

| Pattern | Result |
|---|---|
| `Bad {0` | `IllegalArgumentException`: unclosed element |
| `Bad {abc}` | `IllegalArgumentException`: invalid argument index |
| `Bad {0,unknown}` | `IllegalArgumentException`: unsupported formatter type |
| `Bad {{0}}` | `IllegalArgumentException`: invalid nested opening brace |
| `Bad {0,number,#,##0.00` | `IllegalArgumentException`: missing closing brace on format element |

Cases that are **not necessarily errors**:

| Pattern | Verified behavior |
|---|---|
| `Bad }` | Prints `Bad }` literally |
| `It's {0}` | Prints `Its {0}` if argument is `Mai` |
| `X '{0}` | Prints `X {0}`; quote extends to end of pattern |
| `'{0}'` | Prints `{0}`, correct if literal is intended |
| `''{0}''` | Prints single quote, value, then single quote |

Note: **not every logic bug throws an API exception**. Correctness depends on message intent, not merely `new MessageFormat(pattern, locale)` succeeding.

### Argument Indexes and Missing Data

Pattern `Hi {2}, {0}.` with an array containing only one argument (index 0) can print:

```text
Hi {2}, Mai.
```

Unprovided placeholders can **remain verbatim** in the output instead of throwing an error. Therefore, when translations reorder parameters, verify the index set against the number of arguments actually passed.

Pattern `{0,number}` requires an argument whose type matches a number formatter. Passing a string like `oops` can throw `IllegalArgumentException` during formatting. **Nulls, missing values, and wrong types** belong in the test matrix alongside pattern quotes.

## 10. Runnable Java 17+: Checking Bad Pattern Syntax

Save `InvalidMessagePatternDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class InvalidMessagePatternDemo {
    public static void main(String[] args) {
        String[] invalid = {
                "Bad {0",
                "Bad {abc}",
                "Bad {0,unknown}",
                "Bad {{0}}"
        };

        for (String pattern : invalid) {
            try {
                new MessageFormat(pattern, Locale.US);
                System.out.println("ACCEPTED");
            } catch (IllegalArgumentException exception) {
                System.out.println("IllegalArgumentException");
            }
        }

        MessageFormat closing =
                new MessageFormat("Bad }", Locale.US);

        MessageFormat unterminatedQuote =
                new MessageFormat("It's {0}", Locale.US);

        System.out.println(
                closing.format(new Object[0]));
        System.out.println(
                unterminatedQuote.format(new Object[]{"Mai"}));
    }
}
```

Run:

```bash
javac InvalidMessagePatternDemo.java
java InvalidMessagePatternDemo
```

Output:

```text
IllegalArgumentException
IllegalArgumentException
IllegalArgumentException
IllegalArgumentException
Bad }
Its {0}
```

Takeaway: the first four patterns are blocked during pattern parsing, while the last two are accepted and must be **evaluated for output and meaning**. Never keep `It's {0}` in a translation expecting it to substitute a username.

In production, error logs can record the message key and locale to pinpoint broken translations; if patterns contain sensitive data or user input, avoid logging them verbatim unnecessarily.

## 11. Number Patterns and Quoting in Nested Patterns

Format elements can contain **subformat patterns**, for example:

```text
Amount: {0,number,#,##0.00}
```

With `Locale.US` and value `1234.5`, output:

```text
Amount: 1,234.50
```

Number formatting rules inside `{0,number,...}` can involve `DecimalFormat`. When using custom styles, distinguish:

1. Single quotes at the **`MessageFormat`** layer.
2. Single quotes of the **subformat** such as `DecimalFormat`.
3. Braces belonging to **`MessageFormat`** or appearing in literal text.

JDK-verified example:

```text
Pattern: {0,number,#,##0.00' kg'}
Output:  1,234.50 kg
```

The result shows two decimal digits and the suffix `kg`. Here the subformat pattern is passed to the number formatter per `MessageFormat` rules. Do not blindly pile on extra single quotes at every layer "just to be safe": doubling them in the wrong place can leak extra quotes into output.

Example:

```text
Pattern: {0,number,#,##0.00'' kg''}
Output:  1,234.50' kg'
```

This is a **testable difference**, not something to guess by counting quotes visually.

In real projects, prefer simple patterns and avoid nesting complex syntax when possible. For multi-layer formatting or complex locale policies, you can pre-format values with an appropriate formatter and pass the resulting string into `MessageFormat`. Just ensure translators are still free to reorder arguments.

## 12. ChoiceFormat and Nested MessageFormat

`ChoiceFormat` is supported via `MessageFormat`'s `choice` style. Example:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

With arguments 0, 1, 2, 5:

```text
0 -> no files
1 -> one file
2 -> 2 files
5 -> 5 files
```

Syntax:

- `0#no files` applies starting at threshold 0.
- `1#one file` applies starting at threshold 1.
- `1<...` defines the branch for values greater than 1.
- In the last branch, `{0,number,integer}` is a **nested** format element.

### Standalone Java 17+ Program

Save `ChoiceMessageDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceMessageDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "{0,choice,0#no files|1#one file|" +
                "1<{0,number,integer} files}",
                Locale.US);

        for (int n : new int[]{0, 1, 2, 5}) {
            System.out.println(
                    n + " -> " + message.format(new Object[]{n}));
        }
    }
}
```

Run:

```bash
javac ChoiceMessageDemo.java
java ChoiceMessageDemo
```

Output:

```text
0 -> no files
1 -> one file
2 -> 2 files
5 -> 5 files
```

### Critical Note on Quoting in Nested Patterns

When a `choice` branch contains placeholders or text with single quotes, formatting may interpret the pattern across **multiple layers**. The required number of single quotes can differ from a flat pattern, because quotes can be processed both when parsing the outer pattern and when processing the selected `choice` branch message.

Therefore:

- **Do not guess** by blindly doubling quotes.
- Write dedicated tests for every `choice` branch, including boundary values and values just above thresholds.
- Test translations containing apostrophes or literal braces directly inside branches.
- When plural logic has complex grammatical branches, consider designing separate message keys/formatting rather than cramming all logic into one hard-to-maintain pattern.

The `choice` pattern above was chosen to avoid complex quoting and has JDK-verified stdout. When adapting it for another language, test that language's exact thresholds and plural policies; `ChoiceFormat` does not automatically implement all modern plural rules.

## 13. Patterns from ResourceBundle and .properties Files

Application messages typically live in files like:

```properties
welcome=You''re invited, {0}.
quoted=Literal '{0}' plus {0}
braced=Result: '{'{0}'}'
files={0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

This is **`.properties` file content**, not Java source. When code executes:

```java
String pattern = bundle.getString("welcome");
MessageFormat message =
        new MessageFormat(pattern, locale);
```

`MessageFormat` receives the **string loaded by `ResourceBundle`**, then applies quoting rules as usual.

For `.properties`, the main processing layers are:

```text
.properties file
      |
      v
Properties/ResourceBundle parser
      |  decodes escapes and key=value structure
      v
Pattern String in Java
      |
      v
MessageFormat parser
      |  processes single quotes, braces, format elements
      v
Final string after inserting arguments
```

Do not use JSON escapes, Java source escapes, or Markdown escapes to predict the actual value after loading a `.properties` file. When unsure, test with the exact `ResourceBundle` mechanism your product uses.

### Java 9+ and ResourceBundle Properties Encoding

In Java 17, `.properties` resource bundles are read as UTF-8 by default in `ResourceBundle`, with API-defined fallback handling for invalid data. However, `java.util.Properties.load(InputStream)` and other loaders **do not necessarily share the same encoding rules**.

Consequently, tests on Vietnamese/French/Japanese data should use the **exact same loading path as production** to avoid drawing wrong conclusions from a different file reader. Checking encoding is separate from escaping apostrophes for `MessageFormat`.

### Not Every String in a Bundle Is a MessageFormat Pattern

If a message key has no placeholders and the application displays the bundle string verbatim **without calling `MessageFormat`**, single quotes `'` are not processed by `MessageFormat`.

However, if the same key goes through `MessageFormat` because a shared helper formats all messages, apostrophes regain syntactic significance. Agree on a **message catalog contract**: which keys are plain text, which are `MessageFormat` patterns, and which helpers are allowed to run the formatter.

Do not force translators to write `''` in pure plain-text strings that never pass through `MessageFormat`; equally, do not allow unescaped single `'` in patterns that actually get formatted.

## 14. Testing Patterns with Assertions, Not Just Eyeballing Console Output

A sustainable testing approach:

1. Each message has a **key** and applicable locales.
2. Test typical argument data as well as boundary cases.
3. Assert **exact** results, including quotes, braces, placeholder positions, spaces, and digits.
4. Assert that critical malformed patterns throw exceptions.
5. Assert that syntactically valid yet semantically broken patterns produce results QA treats as failures.
6. When patterns use `number`/`date`/`choice`, pin locale/timezone or settings that could alter output.
7. For real translations, test every key per supported locale with representative test vectors.

**Do not test only that the constructor succeeds.** `It's {0}` is the prime counterexample.

**Do not test only with name `A` or number `1`.** Strings containing quotes, braces, punctuation, and `choice` thresholds expose bugs. Also test multiple arguments to catch translations that swap positions incorrectly.

## 15. Complete Java 17+ Test Suite Without JUnit

Save `MessagePatternTests.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessagePatternTests {
    private static int passed;

    private static void equalsText(
            String name,
            String pattern,
            Object[] args,
            String expected) {

        String actual =
                new MessageFormat(pattern, Locale.US).format(args);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=[" + expected +
                    "] actual=[" + actual + "]");
        }

        System.out.println("PASS " + name + " => " + actual);
        passed++;
    }

    private static void rejects(String name, String pattern) {
        try {
            new MessageFormat(pattern, Locale.US);
            throw new AssertionError(
                    "Accepted invalid pattern: " + name);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "PASS " + name + " => IllegalArgumentException");
            passed++;
        }
    }

    public static void main(String[] args) {
        Object[] a = {"Mai", 2, 1234.5};

        equalsText(
                "escaped-apostrophe",
                "You''re invited, {0}.",
                a,
                "You're invited, Mai.");

        equalsText(
                "quoted-placeholder",
                "Literal '{0}' plus {0}",
                a,
                "Literal {0} plus Mai");

        equalsText(
                "apostrophes-around-value",
                "''{0}''",
                a,
                "'Mai'");

        equalsText(
                "braces-around-value",
                "'{'{0}'}'",
                a,
                "{Mai}");

        equalsText(
                "json",
                "JSON: '{'\"name\": \"{0}\"'}'",
                a,
                "JSON: {\"name\": \"Mai\"}");

        equalsText(
                "unmatched-quote",
                "It's {0}",
                a,
                "Its {0}");

        equalsText(
                "choice-nested",
                "{1,choice,0#none|1#one|" +
                "1<{1,number,integer} files}",
                a,
                "2 files");

        equalsText(
                "closing-brace-literal",
                "Bad }",
                a,
                "Bad }");

        rejects(
                "unclosed-opening-brace",
                "Bad {0");

        rejects(
                "nonnumeric-index",
                "Bad {abc}");

        rejects(
                "unknown-format-type",
                "Bad {0,unknown}");

        rejects(
                "unescaped-nested-opening-brace",
                "Bad {{0}}");

        System.out.println("TOTAL=" + passed);
    }
}
```

Compile/run:

```bash
javac MessagePatternTests.java
java MessagePatternTests
```

Output from the program compiled and run successfully on JDK:

```text
PASS escaped-apostrophe => You're invited, Mai.
PASS quoted-placeholder => Literal {0} plus Mai
PASS apostrophes-around-value => 'Mai'
PASS braces-around-value => {Mai}
PASS json => JSON: {"name": "Mai"}
PASS unmatched-quote => Its {0}
PASS choice-nested => 2 files
PASS closing-brace-literal => Bad }
PASS unclosed-opening-brace => IllegalArgumentException
PASS nonnumeric-index => IllegalArgumentException
PASS unknown-format-type => IllegalArgumentException
PASS unescaped-nested-opening-brace => IllegalArgumentException
TOTAL=12
```

This test suite illustrates two assertion styles:

- `equalsText(...)`: compares **final output** against a specific expectation.
- `rejects(...)`: verifies syntactically invalid patterns throw `IllegalArgumentException`.

In this lesson, the `unmatched-quote` case asserts the **actual API behavior** to explain the mechanism. In a real application where `It's Mai` is intended, the test should assert the right result and thus **fail** when the pattern is written as `It's {0}`. Do not copy intentionally broken demo expectations as product expectations.

### Limitations of the Harness

This harness uses a single `Locale.US` and a handful of illustrative patterns. Real projects must iterate over the **message catalog** of supported locales, testing critical message keys and subformat options (`number`, `date`, `choice`, etc.). For CI, JUnit 5 parameterized tests can manage larger suites, whereas the example above requires no libraries outside the JDK.

## 16. Testing Quotes in Argument Data vs. Quotes in Patterns

A common point of confusion: a user enters:

```text
O'Brien {1}
```

into a name field, and the app uses the pattern:

```text
User input: {0}
```

Normally, this argument is **inserted as data**, not reinterpreted as `MessageFormat` syntax at the outer pattern layer. Example:

```java
MessageFormat formatter =
        new MessageFormat("User input: {0}", Locale.US);

System.out.println(
        formatter.format(
                new Object[]{"O'Brien {1}"}));
```

Verified result:

```text
User input: O'Brien {1}
```

From this:

- **Do not turn every apostrophe in user names into `''` just to pass them through a simple `{0}`.**
- **Do fix literal apostrophes inside the pattern itself** before `MessageFormat` parses it.
- Never take a user-supplied pattern and pass it straight to `MessageFormat` without validation, because `{...}` syntax will be interpreted as formatting directives.
- `choice` branches can involve **re-parsing embedded patterns** during expansion, so do not overgeneralize "arguments can never interact with parsing" to every nested format string.

Clearly separating **templates/patterns** from **argument values** ensures tests do not double-escape data or corrupt user names, addresses, and natural text.

## 17. Nulls, Missing Arguments, and Wrong Types

A translation can be syntactically accepted yet fail at format time.

### Missing Argument

With pattern:

```text
Hi {2}, {0}.
```

and an argument array containing only `{"Mai"}`, observed output:

```text
Hi {2}, Mai.
```

Thus, **formatting without exception does not prove enough arguments were passed**. Translation QA should determine the pattern's index set and compare it against supplied data.

### Null

With pattern `Hi {0}` and `new Object[]{null}`, standard Java `MessageFormat` outputs:

```text
Hi null
```

If the product requires natural phrasing when a person's name is absent, handle `null` in business logic instead of accidentally displaying `null`. Separate resource keys per context may also be needed.

### Wrong Type

Pattern `{0,number}` cannot accept arbitrary `String` arguments. For instance, passing `"oops"` causes the number formatter to fail and may throw `IllegalArgumentException`.

Therefore, a message contract should specify:

- Count and indexes of arguments.
- Expected data type at each index.
- Whether `null` is allowed.
- Locale-specific format styles.
- Edge-case tests for numbers, dates, and special types.

Do not lump all errors into a broad `catch` that returns the raw pattern to users: that hides broken translations and exposes `{0}` placeholders.

## 18. Do Not Rely Absolutely on toPattern() to Fix Quote Bugs

`MessageFormat.toPattern()` returns a pattern representation reconstructed from the parser's stored configuration. This form can **differ from the original string** because the parser already interpreted quotes and normalized certain constructs.

For example, the pattern:

```text
You're welcome, {0}!
```

was misparsed: the single quote began a literal lasting to the end, so `{0}` was not recorded as an argument. Calling `toPattern()` cannot guess the **translator's intent** to repair it into `You''re welcome, {0}!`.

During QA:

1. Preserve the raw pattern from the bundle to report errors by message key and locale.
2. Instantiate `MessageFormat` and test output/test vectors.
3. Use `toPattern()` only as a debugging aid **knowing it is not the raw source**.
4. Do not rely on `toPattern()` looking quote-balanced to declare a translation valid.

If an app has a static pattern linter, it should distinguish syntax permitted by `MessageFormat` from **stricter product conventions** (such as mandatory placeholders and disallowing unclosed quotes). Linting does not replace output testing.

## 19. Locale, Punctuation, and Translated Text

When Vietnamese, French, English, or Japanese translations use `MessageFormat`, test with the **exact target `Locale`**:

```java
Locale locale = Locale.FRANCE;
MessageFormat formatter =
        new MessageFormat(
                "Total : {0,number,#,##0.00}",
                locale);
```

With `Locale.FRANCE`, grouping separators, decimal marks, and spaces differ from US. On the JDK environment used for verification, output for `1234.5` uses a narrow no-break space for grouping and a decimal comma, not `1,234.50`.

Do not copy US expected results to FR or `vi-VN`. Furthermore, CLDR data can update across JDK/provider versions, so tests depending on locale symbols must pin the runtime version or be reviewed upon upgrades.

### Placeholders Can Move Depending on Language

Example:

```text
English: {0} sent {1} a message.
Other locale: {1} đã nhận tin nhắn từ {0}.
```

This is a strength of `MessageFormat`: translators can reorder `{0}` and `{1}` for natural phrasing. Tests should verify **argument meaning and slots**, rather than forbidding all reordering.

Yet if a translator accidentally inserts `'` before `{1}`, the remainder can become quoted and stop substituting. Thus, full-sentence output testing per locale matters more than simple regex placeholder-index scanning.

### Apostrophes in Translated Text

For example, French uses ASCII apostrophes in elisions. If the string **goes through `MessageFormat`**, those apostrophes need `''` just like English. If a translation uses the curly quote `’`, syntax rules differ, though typographic consistency remains the responsibility of content guidelines.

Never "fix" issues by deleting all apostrophes: that breaks natural language and masks pattern bugs.

## 20. MessageFormat Is Mutable: Managing It in Tests

`java.text.MessageFormat` exposes methods such as `applyPattern(...)`, `setLocale(...)`, `setFormat(...)`, and `setFormats(...)`; subformatters may also hold state. Never share a single `static MessageFormat` instance and mutate its pattern/locale per request across threads.

Two straightforward approaches:

1. Create `new MessageFormat(pattern, locale)` per operation/test.
2. Cache prototypes keyed by **locale + pattern + configuration/version** and clone them per caller if benchmarks prove it necessary.

For unit tests, creating a fresh instance prevents one test from mutating state seen by the next. This is especially helpful when testing quoting, because `applyPattern` can completely alter how text is parsed.

`MessageFormat.format(String pattern, Object... arguments)` is a static convenience method, yet its locale choice differs from passing an explicit `Locale` to the constructor; when number/date output depends on locale, construct an instance with an explicit locale.

Do not share one mutable `MessageFormat` across threads just because the pattern is identical. Thread safety of a `ConcurrentHashMap` cache does not make the formatter inside thread-safe.

## 21. Round-Trip Parse Testing and Limits of MessageFormat.parse

`MessageFormat` provides `parse` methods, yet **not every formatted pattern can be parsed back losslessly**. Repeated placeholders, `choice`, literal text, and ambiguity between fields can prevent parsed values from matching the original inputs.

Moreover, a parse can succeed on a **prefix** of the string. Example:

```java
MessageFormat parser =
        new MessageFormat(
                "{0,number,integer} units", Locale.US);

ParsePosition position = new ParsePosition(0);

Object[] values =
        parser.parse("12 units extra", position);
```

This example requires imports for `java.text.MessageFormat`, `ParsePosition`, and `Locale`.

Observed result:

```text
values[0] = 12
position.getIndex() = 8
position.getErrorIndex() = -1
```

The input `"12 units extra"` is longer than 8. Therefore, if using `MessageFormat.parse` to **validate the entire input**, verify:

```java
values != null &&
position.getIndex() == input.length()
```

where `input` is the string being parsed. This **snippet** illustrates the acceptance condition, not a full business validation algorithm. `getErrorIndex()==-1` does not guarantee the entire string was consumed.

The main focus of this lesson remains **testing pattern formatting**, though parsing needs attention if an app uses `MessageFormat` bidirectionally. Never promise "formatting then parsing back will always recover the original `Object[]`."

## 22. Designing a Test Matrix for Production Translations

A minimal test vector table:

| Category | Pattern or scenario | Expectation |
|---|---|---|
| Plain text | `Hello, {0}!` | Placeholder is replaced |
| ASCII apostrophe | `You''re {0}.` | Single `'` appears in output |
| Unclosed quote | `You're {0}.` | QA detects semantically wrong output |
| Literal placeholder | `'{0}'` | Prints `{0}`, no substitution |
| Literal apostrophes around value | `''{0}''` | Prints `'Mai'` |
| Braces around value | `'{'{0}'}'` | Prints `{Mai}` |
| JSON-like text | `'{' ... ` / `'}'` | Literal braces and placeholders both work |
| Unclosed `{` | `Bad {0` | Throws `IllegalArgumentException` |
| Invalid index | `{abc}` | Throws `IllegalArgumentException` |
| Invalid format type | `{0,unknown}` | Throws `IllegalArgumentException` |
| `choice` thresholds | 0, 1, 2, 5 | Picks right branch and sub-placeholders |
| Locale numbers | US and FR | Digit grouping/decimals match each locale |
| Missing argument | `{2}` with 1 argument | QA detects unreplaced placeholder |
| Null argument | `{0}` with `null` | Output meets product policy |
| Type mismatch | `{0,number}` with non-numeric string | Tests expected runtime error |
| User data with `'`/`{...}` | Value passed to `{0}` | Data inserted without extra escaping |
| Bundle patterns | Every key/locale | Output is correct, not merely parseable |

A strong QA suite separates **assertions for syntax vs. semantics**:

- Syntax test: construct formatter from pattern.
- Semantic test: output matches the translated sentence accurately.
- Argument-contract test: every placeholder has a correctly typed value.
- Locale test: number/date formatting is not leaked from the default locale.
- Regression test: new and approved patterns are re-verified in CI.

## 23. Common Mistakes

**1. Using a single `'` to print an apostrophe.** Inside a `MessageFormat` pattern, a single quote starts/ends quoting; use `''` to render one straight apostrophe.

**2. Assuming an unclosed single quote is always a syntax error.** The parser can auto-close at the end of the pattern and leave `{0}` literal.

**3. Writing `'{0}'` when intending `'Mai'`.** That quotes the placeholder instead of substituting the value. Use `''{0}''`.

**4. Writing `{{0}}` to escape braces.** `MessageFormat` does not use doubled-brace escaping.

**5. Testing only that "the pattern compiles."** Many semantically broken patterns are accepted.

**6. Testing only English messages with no apostrophes.** Translations with apostrophes, curly quotes, or other languages expose bugs.

**7. Conflating Java source escaping with `MessageFormat` escaping.** They are two separate syntax layers.

**8. Conflating `.properties` escaping with `MessageFormat`.** The file is loaded first, then the resulting string reaches `MessageFormat`.

**9. Ignoring literal braces in JSON text.** `{` may be interpreted as a format element rather than fixed data.

**10. Forgetting arguments can be missing.** Output may retain the literal placeholder instead of throwing an exception.

**11. Passing strings to `{0,number}` without type checks.** The number formatter can throw at runtime.

**12. Testing only one `choice` branch.** Nested pattern bugs often trigger only on specific branches.

**13. Guessing quote counts in nested `choice` patterns.** Test each branch and layer explicitly.

**14. Using a locale-sensitive formatter for fixed test assertions.** Grouping/decimal marks may vary.

**15. Using `MessageFormat` to JSON-escape user data.** It is not a JSON serializer.

**16. Turning apostrophes in user names into `''` before passing them as normal arguments.** Unnecessarily corrupts real data.

**17. Treating `toPattern()` as recovering translator intent.** It only reflects the parsed/stored pattern, without fixing broken text.

**18. Sharing a mutable `MessageFormat` across threads and calling `applyPattern`.** Risks cross-request data/config corruption.

**19. Testing only `format` while ignoring `parse` when the app actually parses.** `parse` can succeed on a partial prefix.

**20. Using intentionally buggy demo results as production expected output.** Tests must assert **message intent**, not merely API quirks.

## 24. Self-Check Exercises

**Question 1.** In `MessageFormat`, what apostrophe does `You''re {0}` produce?

**Answer:** `''` in the pattern becomes one `'` in the output. `{0}` is still replaced by the argument.

**Question 2.** Why can `You're {0}` produce `Youre {0}`?

**Answer:** `'` opens a literal region lasting to the end of the pattern, disabling placeholder substitution. This is a silent semantic bug.

**Question 3.** To print the literal text `{0}`, how should the pattern be written?

**Answer:** `'{0}'`.

**Question 4.** To print `{Mai}` from argument `Mai`, what pattern should be used?

**Answer:** `'{'{0}'}'`.

**Question 5.** To print `'Mai'` (with single quotes around the value), what should be used?

**Answer:** `''{0}''`.

**Question 6.** Can you write `{{0}}` to escape braces like in some template engines?

**Answer:** No. In the JDK example, that pattern is rejected with `IllegalArgumentException`.

**Question 7.** Why is testing that the Java constructor succeeds not enough?

**Answer:** Patterns like `It's {0}` are valid to the parser yet print wrong text without substituting arguments.

**Question 8.** Does user input `O'Brien {1}` passed via `{0}` need quotes escaped to `''` beforehand?

**Answer:** No, if inserted as a normal argument; keep argument data distinct from pattern syntax.

**Question 9.** Why should `MessageFormat` with `Locale.FRANCE` not assert number output formatted for `Locale.US`?

**Answer:** Digit grouping, decimal separators, and whitespace characters differ between locales.

**Question 10.** With `MessageFormat.parse`, what checks that no trailing unparsed text remains?

**Answer:** Besides `parse` returning non-null, `position.getIndex() == input.length()` when `ParsePosition` starts at 0.

## 25. Summary

In `MessageFormat`, single quotes and braces are **part of the pattern language**, not just punctuation to display:

- `''` produces **one literal ASCII single quote**.
- `'{0}'` displays literal `{0}`; `''{0}''` displays single quotes around the **substituted value**.
- `'{'{0}'}'` wraps the value in braces.
- Unclosed single quotes can **auto-close at the end of the pattern**, silently disabling placeholders without throwing an error.
- `choice` patterns and subformats introduce nested syntax layers and must be tested with data for every branch.
- Do not confuse `.properties` content, Java string literals, and `MessageFormat` quoting rules.
- Test **output per locale, argument types, and argument sets**, not just `new MessageFormat(...)` construction.

**Official documentation:** [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html) · [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) · [ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html).
