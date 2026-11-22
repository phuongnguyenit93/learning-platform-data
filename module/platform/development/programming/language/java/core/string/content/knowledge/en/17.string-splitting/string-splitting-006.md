# `Pattern.quote()`: splitting strings with literal delimiters

## 1. Why is `Pattern.quote` needed?

Java's `String.split(String regex)` always interprets its argument as a **regular expression** (regex). Therefore, the string `"."` does not mean a period: in regex, `.` stands for any single character (normally excluding line terminators). Likewise, `|` is alternation, `*`, `+`, `?` are quantifiers, and `\\` is the escape character. If a delimiter provided by configuration, a user, or input data contains these characters, `split(delimiter)` may split incorrectly or throw `PatternSyntaxException`.

`java.util.regex.Pattern.quote(String s)` converts the string `s` into **a regex that matches the entire string literally**. Thus, when the delimiter is data rather than a regex rule, write:

```java
import java.util.regex.Pattern;

String[] parts = text.split(Pattern.quote(delimiter));
```

For example, `"a.b".split(".")` returns an empty array because `.` matches each character in turn and `split` discards trailing empty elements by default. By contrast, `"a.b".split(Pattern.quote("."))` returns `["a", "b"]`.

Inside a regex, a quoted region typically takes the form `\\Q...\\E`, but **do not manually concatenate** `"\\Q" + delimiter + "\\E"`: `Pattern.quote` also handles cases where the data itself contains `\\E`.

## 2. Standalone Java 17+ example

Create a file `LiteralDelimiterSplitDemo.java` with the following contents:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class LiteralDelimiterSplitDemo {
    public static void main(String[] args) {
        // Dot: a regex operator differs from a literal period.
        String dotText = "a.b";
        System.out.println("Regex dot: "
                + Arrays.toString(dotText.split(".")));
        System.out.println("Literal dot: "
                + Arrays.toString(dotText.split(Pattern.quote("."))));

        // Multi-character delimiter containing regex operators.
        String delimiter = ".$.";
        String compositeText = "red.$.green.$.blue";
        System.out.println("Composite delimiter: "
                + Arrays.toString(compositeText.split(Pattern.quote(delimiter))));

        // Pipe character with various limit values.
        String pipeText = "a|b||";
        String pipeRegex = Pattern.quote("|");
        System.out.println("Default limit: "
                + Arrays.toString(pipeText.split(pipeRegex)));
        System.out.println("Keep trailing: "
                + Arrays.toString(pipeText.split(pipeRegex, -1)));
        System.out.println("At most two: "
                + Arrays.toString("a|b|c".split(pipeRegex, 2)));

        // Backslash: special character in both Java literals and regex.
        String windowsPath = "C:\\temp\\docs";
        System.out.println("Backslash: "
                + Arrays.toString(windowsPath.split(Pattern.quote("\\"))));

        // When splitting multiple strings with the same delimiter.
        Pattern marker = Pattern.compile(Pattern.quote("<E>"));
        System.out.println("Compiled: "
                + Arrays.toString(marker.split("A<E>B<E>C")));
    }
}
```

Compile and run:

```bash
javac LiteralDelimiterSplitDemo.java
java LiteralDelimiterSplitDemo
```

Output:

```text
Regex dot: []
Literal dot: [a, b]
Composite delimiter: [red, green, blue]
Default limit: [a, b]
Keep trailing: [a, b, , ]
At most two: [a, b|c]
Backslash: [C:, temp, docs]
Compiled: [A, B, C]
```

On the `Keep trailing` line, the actual array contains four elements: `"a"`, `"b"`, `""`, `""`. `Arrays.toString` represents empty strings as empty spaces between commas. `String.split` does not insert extra characters into the result.

## 3. `limit` decides whether empty elements are kept

`Pattern.quote` only makes the delimiter match **literally**; it does not alter the `limit` rules of `String.split(regex, limit)`.

| Call on `"a|b||"` | Resulting elements | Mechanism |
| --- | --- | --- |
| `split(Pattern.quote("|"))` | `["a", "b"]` | Same as default `limit = 0`; discards trailing empty elements. |
| `split(Pattern.quote("|"), 0)` | `["a", "b"]` | Also discards trailing empty elements. |
| `split(Pattern.quote("|"), -1)` | `["a", "b", "", ""]` | Preserves all trailing empty elements. |
| `split(Pattern.quote("|"), 2)` | `["a", "b||"]` | Splits into at most two parts; the last element holds the remainder. |

When `limit > 0`, at most `limit - 1` splits occur. When `limit = 0` or negative, splitting can happen as many times as possible; the difference is that `limit = 0` discards trailing empty elements whereas `limit < 0` keeps them. Empty elements **between** consecutive delimiters can still be preserved.

If the data has columns that may be empty at the end, such as `"id|name||"`, use `split(Pattern.quote("|"), -1)` to preserve the field count; using the default risks losing trailing fields.

## 4. Delimiters prone to errors

| Data used as delimiter | Appropriate call | Problem when treated as regex |
| --- | --- | --- |
| Dot `.` | `split(Pattern.quote("."))` | `.` matches any character. |
| Pipe `|` | `split(Pattern.quote("|"))` | `|` is alternation. |
| Asterisk `*` or plus `+` | `split(Pattern.quote(delimiter))` | Quantifiers can cause regex syntax errors. |
| String `.$.` | `split(Pattern.quote(".$."))` | Contains multiple regex operators at once. |
| Backslash `\\` | `split(Pattern.quote("\\"))` | Backslash is also the regex escape character. |
| String `<END>` | `split(Pattern.quote("<END>"))` | Literal pattern reflects intent even if data changes. |

When special characters appear inside a **Java string literal**, there is also the Java language escaping layer. For instance, to represent **one** backslash in a Java string you must write `"\\"`; to turn that string into a literal regex, use `Pattern.quote("\\")`. Java source escaping and regex escaping are two separate steps.

`Pattern.quote` does not change case, strip whitespace, or normalize Unicode. It searches for the exact delimiter string provided. If that string does not appear in the text, `split` normally returns a one-element array containing the original text.

## 5. When should you not use `Pattern.quote`?

If the goal is to split by a **rule**, such as one or more whitespace characters, use a real regex:

```java
String line = "Java   regex\tbasics";
String[] words = line.split("\\s+");  // One or more whitespace characters
```

Here, `\\s+` is intentional regex syntax. Calling `Pattern.quote("\\s+")` would make the pattern look for the exact three characters `\\`, `s`, `+` in the text instead of whitespace.

The two approaches serve different purposes:

- **The delimiter is a specific string:** `text.split(Pattern.quote(delimiter))`.
- **The delimiter describes a pattern class:** `text.split(regex)`, when the regex is constructed intentionally.

When the same literal delimiter is used repeatedly, you can precompile it:

```java
Pattern literalDelimiter = Pattern.compile(Pattern.quote(delimiter));
String[] first = literalDelimiter.split(firstText, -1);
String[] second = literalDelimiter.split(secondText, -1);
```

This is an illustrative snippet using variables `delimiter`, `firstText`, `secondText` supplied by the program, not a standalone runnable file. `Pattern.split(input, limit)` follows the same `limit` rules as `String.split(regex, limit)`. Precompiling is useful when reusing a pattern repeatedly.

## 6. Common mistakes and limitations

**Escaping only a few individual characters manually.** Replacing only `.` with `\\.` misses `|`, `[`, `(`, `*`, and other cases. Building `\\Q...\\E` by hand also carries risks if the data contains `\\E`. `Pattern.quote` handles the entire string consistently.

**Losing trailing empty fields by default.** `Pattern.quote` does not change this rule. When column order or count matters, use `limit = -1` and check `array.length` in code rather than only inspecting the `Arrays.toString` output.

**Empty or `null` delimiters.** `Pattern.quote(null)` throws `NullPointerException`. With `delimiter = ""`, the literal pattern has zero width, so splitting becomes position-based splitting rather than splitting on a specific delimiter. If an API only accepts non-empty delimiters, validate `delimiter != null && !delimiter.isEmpty()`. Avoid `isBlank()` for this requirement: a single space `" "` can still be a valid delimiter.

**Mistaking literal splitting for CSV parsing.** For the string `a,"b,c",d`, `split(Pattern.quote(","))` still splits on the comma inside the quotes of `"b,c"`. CSV has rules for quotes, escaping, and line breaks; use a proper CSV parser when conformance to that format is required.

**Misusing it for regex replacement strings.** `Pattern.quote` is only for **patterns**. When the replacement string of `Matcher.replaceAll` contains `$` or `\\` and must be treated literally, the corresponding API is `Matcher.quoteReplacement`, which serves a different purpose.

## 7. Self-check

1. To split `"left.$.middle.$.right"` into `["left", "middle", "right"]`, use `"left.$.middle.$.right".split(Pattern.quote(".$."))`.
2. To preserve all four fields of `"name|email||"`, use `"name|email||".split(Pattern.quote("|"), -1)`.
3. When configuration contains `"."`, `split(delimiter)` treats it as a regex operator; `split(Pattern.quote(delimiter))` matches the literal dot.

**Key takeaway:** The first argument of `String.split` is a regex. When the delimiter comes from **literal data**, use `Pattern.quote`; when trailing empty elements must be preserved, add `limit = -1`.