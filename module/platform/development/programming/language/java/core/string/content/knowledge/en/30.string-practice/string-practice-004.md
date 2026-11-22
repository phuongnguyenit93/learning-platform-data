# Splitting Data with Empty Elements and Preserving Exact Delimiters in Java

## Goal and problem

When reading a structured data line, **an empty element is still a valid element**. For example, the comma-delimited string `,A,,B,` has **5 fields**, in order: `""`, `"A"`, `""`, `"B"`, `""`. A leading comma creates an empty first field; two adjacent commas create an empty middle field; a trailing comma creates an empty final field. Dropping any field can shift column positions out of alignment.

There are two needs to distinguish:

1. **Preserve empty fields** in the resulting array, while delimiters can be discarded. Use `String.split(regex, -1)`.
2. **Preserve the exact delimiters that appeared** (for instance when a string has both `,` and `;`, or when the count/characters of delimiters carry meaning). Use `Matcher` to extract fields and delimiter strings separately, or `splitWithDelimiters` on Java 21+.

Do not assume by default that `split` both preserves trailing empty fields and returns the delimiters. Those are two separate properties.

## 1. Understanding `String.split` and the `limit` parameter accurately

`String.split(String regex)` is equivalent to `split(regex, 0)`: **trailing** empty fields are discarded from the result. A leading empty field caused by a positive-width match and middle empty fields are still preserved.

| Call | Result (empty strings written explicitly) | Meaning |
| --- | --- | --- |
| `",A,,B,".split(",")` | `["", "A", "", "B"]` | Trailing empty field is lost |
| `",A,,B,".split(",", 0)` | `["", "A", "", "B"]` | Same as the one-argument call |
| `",A,,B,".split(",", -1)` | `["", "A", "", "B", ""]` | Preserves the trailing empty field as well |
| `"A,,B,".split(",", 2)` | `["A", ",B,"]` | Splits at most once; remainder is kept intact |
| `",,".split(",", -1)` | `["", "", ""]` | Two delimiters produce three empty fields |
| `"abc".split(",", -1)` | `["abc"]` | No delimiter present |
| `"".split(",", -1)` | `[""]` | Empty input string, result has one element |

Three `limit` modes:

- `limit > 0`: at most `limit - 1` splits; the last element holds the entire unsplit remainder. Use when intentionally keeping the rest, e.g., splitting `key=value=more` with `split("=", 2)`.
- `limit == 0`: split completely and **discard consecutive trailing empty fields**.
- `limit < 0`: split completely and **keep all empty fields**, including trailing ones. `-1` is the conventional value; `-2` behaves the same regarding preserving empty fields.

**Practical rule:** record-oriented data where field ordinal positions must be exact should usually use `split(delimiterRegex, -1)`. Do not `trim()` or `filter(s -> !s.isEmpty())` after splitting if whitespace/empty fields are meaningful.

## 2. Delimiters are interpreted as regex, not literal characters by default

The first argument of `split` is a **regular expression**. Therefore:

- Comma `,` and semicolon `;` have no special regex meaning in this simple context.
- Pipe `|`, dot `.`, asterisk `*`, square brackets, etc., can carry regex meaning. Writing `text.split("|", -1)` to split on `|` is wrong.
- For **fixed/literal** delimiters, especially from configuration or user input, use `Pattern.quote(delimiter)`. For example, `"a|b||".split(Pattern.quote("|"), -1)` returns `["a", "b", "", ""]`.
- For delimiters that are **an intentional regex rule**, write the regex explicitly: `"a,b;c".split("[,;]", -1)` splits on each comma or semicolon. However, the resulting array does not tell you which delimiter was used at which position.
- When wanting to collapse consecutive delimiters into **one** split, regex `[,;]+` drops empty field structures between delimiters. Only use it if business logic truly permits it.

A regex can match a zero-length string (zero-width match), leading to unintuitive splits. For splitting records with tangible delimiters, choose a pattern that always consumes at least one character. It is also impossible to recover all original delimiters solely from a `String[]` split with a regex matching multiple delimiter characters.

## 3. Java 17+ example: preserving empty fields and exact delimiters

The program below illustrates both approaches: `split(..., -1)` for a fixed delimiter, and `Matcher.find()` when each matched delimiter must be kept. The `Tokenized` class holds two lists in order; for `n` delimiters there will be `n + 1` fields, including empty fields.

Create the file `SplitPreservingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SplitPreservingDemo {
    public static void main(String[] args) {
        String line = ",A,,B,";
        String[] defaultFields = line.split(",");
        String[] allFields = line.split(",", -1);

        System.out.println("Default: " + quoted(defaultFields));
        System.out.println("Preserved: " + quoted(allFields));
        System.out.println("Field count: " + allFields.length);
        System.out.println("Same text: " + String.join(",", allFields).equals(line));

        String pipeLine = "red|blue||";
        String[] pipeFields = pipeLine.split(Pattern.quote("|"), -1);
        System.out.println("Pipe: " + quoted(pipeFields));

        String mixed = "A,,B;C;";
        Tokenized tokens = tokenize(mixed, Pattern.compile("[,;]"));
        System.out.println("Fields: " + quoted(tokens.fields.toArray(new String[0])));
        System.out.println("Separators: " + quoted(tokens.separators.toArray(new String[0])));
        System.out.println("Mixed same text: " + rebuild(tokens).equals(mixed));
    }

    // For illustration: makes empty string positions clear in the output.
    private static String quoted(String[] fields) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < fields.length; i++) {
            if (i > 0) {
                out.append(", ");
            }
            out.append('"').append(fields[i]).append('"');
        }
        return out.append(']').toString();
    }

    private static Tokenized tokenize(String text, Pattern separatorPattern) {
        Matcher matcher = separatorPattern.matcher(text);
        List<String> fields = new ArrayList<>();
        List<String> separators = new ArrayList<>();
        int from = 0;

        while (matcher.find()) {
            if (matcher.start() == matcher.end()) {
                throw new IllegalArgumentException(
                    "Separator pattern must consume at least one character"
                );
            }
            fields.add(text.substring(from, matcher.start()));
            separators.add(matcher.group());
            from = matcher.end();
        }
        fields.add(text.substring(from));
        return new Tokenized(fields, separators);
    }

    private static String rebuild(Tokenized tokens) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < tokens.fields.size(); i++) {
            out.append(tokens.fields.get(i));
            if (i < tokens.separators.size()) {
                out.append(tokens.separators.get(i));
            }
        }
        return out.toString();
    }

    private static class Tokenized {
        final List<String> fields;
        final List<String> separators;

        Tokenized(List<String> fields, List<String> separators) {
            this.fields = fields;
            this.separators = separators;
        }
    }
}
```

Compile and run:

```bash
javac SplitPreservingDemo.java
java SplitPreservingDemo
```

Expected output:

```text
Default: ["", "A", "", "B"]
Preserved: ["", "A", "", "B", ""]
Field count: 5
Same text: true
Pipe: ["red", "blue", "", ""]
Fields: ["A", "", "B", "C", ""]
Separators: [",", ",", ";", ";"]
Mixed same text: true
```

Explanation:

- `split(",", -1)` returns all 5 fields; joining with **the same fixed comma** reconstructs the input string.
- `Pattern.quote("|")` ensures `|` is treated as a literal delimiter; the two trailing `|` characters generate two empty elements at the end (after `blue`).
- In `"A,,B;C;"`, the second field and the last field are empty. The `separators` list preserves each `,`/`;`, so `rebuild` can restore the exact original string.
- With a character-consuming pattern, `matcher.start()` is the start index of the delimiter and `matcher.end()` is the position right after it; `substring(from, matcher.start())` gets the exact field before the delimiter, including empty strings. `matcher.group()` holds the **actual matched string**, which is useful even when the delimiter is longer than one character.
- The `quoted` method is only meant to display elements transparently in the example; if data contains quotes or control characters, use appropriate escaping when printing.

### Why preserve the list of delimiters?

For example, `a,b;c` using regex `[,;]` splits into `["a", "b", "c"]`, but joining back with a comma becomes `a,b,c`, losing the original semicolon. `String.join` only preserves the original text when **every delimiter is actually the same fixed string** and all fields are kept intact without complex escape/quote rules.

In the `Matcher` snippet above, `fields.size() == separators.size() + 1` is an invariant worth checking. Do not normalize whitespace, change delimiters, or drop empty fields if the goal is storing/reconstructing data verbatim.

## 4. Java 21+: `String.splitWithDelimiters`

Java 21 adds `String.splitWithDelimiters(String regex, int limit)` and `Pattern.splitWithDelimiters(CharSequence input, int limit)`. The result **alternates field, delimiter, field, delimiter...**, instead of returning only fields.

Java 21 example (illustrative snippet, placed inside a method):

```java
String input = "A,,B;";
String[] pieces = input.splitWithDelimiters("[,;]", -1);
// pieces: ["A", ",", "", ",", "B", ";", ""]
boolean same = String.join("", pieces).equals(input); // true
```

Use `limit = -1` to keep trailing empty parts too; `limit = 0` still drops trailing empty parts per API rules. With `limit > 0`, at most `limit - 1` splits occur and the final element keeps the unsplit remainder; the array has at most `2 * limit - 1` elements. This API **does not exist in Java 17**; on Java 17 use the `Matcher` approach above.

If business logic needs to work per field, the `fields`/`separators` list pair is usually easier to understand than an alternating array; if only verbatim reconstruction is needed, Java 21's alternating array is very convenient.

## 5. Traps that corrupt data

1. **Omitting `-1`**: trailing empty fields disappear, making the column count wrong. Try `"id,name,"`.
2. **Using regex incorrectly**: `split(".")` does not mean splitting on a dot; use `split(Pattern.quote("."), -1)` or a properly escaped regex.
3. **Using `[,;]+` instead of `[,;]`**: consecutive delimiters become a single split, losing empty fields in between.
4. **Dropping empty fields after splitting**: `filter(s -> !s.isBlank())` also removes whitespace-only fields; this alters both data and column positions.
5. **Automatically calling `trim()`**: `" A "` and `"A"` are not identical if the protocol treats whitespace as data.
6. **Joining with one fixed delimiter when the source uses multiple**: round-trip preservation cannot be guaranteed when the source mixes `,` and `;`.
7. **Confusing simple delimited data with full CSV**: `A,"B,C",D` has a comma **inside a quoted field**; `split(",", -1)` still splits it wrongly. Real CSV has escaping, doubled quotes, and even newlines inside fields. Use a format-compliant parser (such as Apache Commons CSV), while explicitly specifying dialect/quote/escape.
8. **Trusting default array printing**: `Arrays.toString` can display empty elements in a way that is hard to distinguish; when inspecting, print `length` and wrap each value in quotes.

`String.split` also has a special rule for zero-width regex matches at the start of a string: it does **not** produce a leading empty field like a positive-length delimiter does. Therefore, do not extrapolate the behavior of zero-width regexes from comma examples.

## 6. Checklist and self-check exercises

For each delimited data line, answer four questions:

1. Is the delimiter a **fixed string** or an intentionally designed **regex**?
2. Must empty fields at the **beginning, middle, and end** be preserved?
3. Is it necessary to preserve the **characters and length of the actual delimiters** to reconstruct the original string?
4. Does the input have **quotes/escapes/nested syntax** that make simple regex splitting violate the specification?

Self-check: with `"|a||"` and literal delimiter `|`, `split(Pattern.quote("|"), -1)` must produce `["", "a", "", ""]`, with a field count of 4. With `"a|b;c|"`, if preserving the encountered delimiters is required, `"|", ";", "|"` must be recorded in order; storing only the fields is not enough.

**Technical conclusion:** use `split(Pattern.quote(delimiter), -1)` when you need to preserve all empty fields with a fixed delimiter. When you need to preserve each mixed delimiter accurately, use `Matcher` (Java 17+) or `splitWithDelimiters(regex, -1)` (Java 21+), then verify by reconstructing the original string.

## API references

- Java 17 `String.split`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java 17 `Pattern.quote` and `Matcher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- Java 21 `Pattern.splitWithDelimiters`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html