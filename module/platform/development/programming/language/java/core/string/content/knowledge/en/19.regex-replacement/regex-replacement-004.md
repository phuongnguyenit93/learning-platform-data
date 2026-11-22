# Matcher.quoteReplacement: Preserving Literal Replacement Content in Java

## Lesson Objectives

When using regular expressions to replace content in a `String`, Java interprets the **search pattern** (*regex*) and the **replacement string** (*replacement*) according to two different sets of rules. This lesson helps you:

- Explain why `$` and `\` in a replacement string can be interpreted by Java as special syntax.
- Use `Matcher.quoteReplacement(String s)` to pass replacement content into `String.replaceAll`, `String.replaceFirst`, or `Matcher.appendReplacement` **literally**.
- Distinguish `Matcher.quoteReplacement` from `Pattern.quote`, from `String.replace`, and from group reference syntax like `$1` or `${name}`.
- Write compilable Java 17+ examples while recognizing common errors and applicability limits.

## 1. The Problem: Replacement Is Not Plain Text

Consider the call:

~~~java
String result = input.replaceAll(regex, replacement);
~~~

The `regex` argument is the pattern used to **find** matching segments in `input`. After finding each matching segment, Java also interprets the `replacement` argument:

| Symbol in replacement | Meaning when used directly |
| --- | --- |
| `$0` | The entire matched segment |
| `$1`, `$2`, ... | Content of the corresponding *capturing group* |
| `${name}` | Content of the capturing group named `name`, if the pattern declares that group |
| `\` | Escapes the next character in replacement syntax, e.g., turning `$` into an ordinary character |

Therefore, if you want to replace a segment with the exact text `$1\docs`, passing that content directly into `replaceAll` will not mean "copy literally": `$1` is treated as a capturing group reference, while `\` can strip the backslash or throw an error depending on its position. When group `1` does not exist, `$1` can cause the replacement operation to throw an exception.

**`Matcher.quoteReplacement(s)` solves this exact problem.** This static method in `java.util.regex.Matcher` returns a *replacement* string corresponding to the **literal content of `s`**. When the returned string is used as the replacement argument of a regex API, every `$` and `\` originating from `s` is treated as an ordinary character. It does not change the content to be inserted and does not control the search regex.

API signature:

~~~java
public static String quoteReplacement(String s)
~~~

This is a `static` method, so call `Matcher.quoteReplacement(s)` without needing to create a `Matcher` object. A `null` value is not a valid replacement string; passing `null` throws a `NullPointerException`.

## 2. Java 17+ Example: Replacing with Content Containing $ and \

Save the entire following program to the file `QuoteReplacementDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QuoteReplacementDemo {
    public static void main(String[] args) {
        String source = "A1 B2";
        String literalReplacement = "$5\\bin";

        // Replace every matching segment with the exact content "$5\bin".
        String all = source.replaceAll(
                "[A-Z]\\d",
                Matcher.quoteReplacement(literalReplacement));
        System.out.println(all);

        // Replace only the first matching segment.
        String first = source.replaceFirst(
                "[A-Z]\\d",
                Matcher.quoteReplacement(literalReplacement));
        System.out.println(first);

        // When you want to use capturing groups, DO NOT quote the whole template.
        System.out.println(
                source.replaceAll("([A-Z])(\\d)", "$2-$1"));

        // When you want the exact characters "$2-$1" to appear, DO quote.
        System.out.println(
                source.replaceAll("([A-Z])(\\d)",
                        Matcher.quoteReplacement("$2-$1")));

        // Protect both the literal search string and the literal replacement string.
        String text = "a.b|a.b";
        String needle = "a.b";
        String replacement = "$1\\dst";
        System.out.println(text.replaceAll(
                Pattern.quote(needle),
                Matcher.quoteReplacement(replacement)));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 QuoteReplacementDemo.java
java QuoteReplacementDemo
~~~

Expected output:

~~~text
$5\bin $5\bin
$5\bin B2
1-A 2-B
$2-$1 $2-$1
$1\dst|$1\dst
~~~

Interpretation:

1. `"[A-Z]\\d"` matches `A1` and `B2` in turn; `quoteReplacement` causes `$5\bin` to be inserted identically, even though there is no group 5.
2. `replaceFirst` interprets the replacement the same way as `replaceAll` but replaces only the first match, so `B2` remains.
3. In `"([A-Z])(\\d)"`, group `1` is the letter and group `2` is the digit. The replacement `"$2-$1"` intentionally pulls groups and changes `A1` to `1-A`.
4. After wrapping `"$2-$1"` with `quoteReplacement`, this string is inserted literally; capturing groups are no longer substituted into `$1` or `$2`.
5. `Pattern.quote("a.b")` removes the special meaning of `.` in the **search pattern**; `Matcher.quoteReplacement("$1\\dst")` removes the special meaning of `$` and `\` in the **replacement**.

**Two escaping layers to remember:** The Java code `"$5\\bin"` produces the actual value `$5\bin` because two `\\` characters in source code produce one `\` in the runtime string. `Matcher.quoteReplacement` then builds the appropriate representation for the replacement processor, ensuring the runtime `\` is preserved in the result.

## 3. Distinguishing Pattern, Replacement, and API Calls

Do not mix up the roles of the data:

| Requirement | Approach | Reason |
| --- | --- | --- |
| Search pattern is regex, replacement content is plain string | `input.replaceAll(regex, Matcher.quoteReplacement(literal))` | Regex still works; replacement is preserved |
| Search pattern is plain text, replacement content is plain string | `input.replace(literalTarget, literalReplacement)` | No regex or quoting needed |
| Must use regex API but need to find literal string | `input.replaceAll(Pattern.quote(target), Matcher.quoteReplacement(replacement))` | Quote **both arguments**, each according to its own grammar |
| Need to insert capturing group values | `input.replaceAll(regex, "$2-$1")` | Allows the replacement engine to expand capturing groups |
| Need per-match replacement workflow | `matcher.appendReplacement(builder, Matcher.quoteReplacement(value))` then `matcher.appendTail(builder)` | Each match can have its own replacement, preserving generated values |

**`Pattern.quote` and `Matcher.quoteReplacement` are not interchangeable:**

- `Pattern.quote(literalTarget)` creates a regular expression that matches `literalTarget` literally. It handles special regex characters such as `.`, `*`, `[`, `(`.
- `Matcher.quoteReplacement(literalReplacement)` creates replacement syntax representing the literal content `literalReplacement`. It handles `$` and `\` in **replacement text**.
- `String.replace(target, replacement)` performs literal substring replacement without using regex for either `target` or `replacement`; it is usually the shortest choice when regex is unnecessary.

If **only** the replacement content needs protection, do not wrap `regex` in `Pattern.quote`: doing so turns intended regex symbols into literal text and changes the search logic.

## 4. Comparing Capturing Group Expansion vs. Literal Insertion

Suppose a pattern has two groups:

~~~java
String source = "id=42";
String regex = "([a-z]+)=(\\d+)";
~~~

The three replacements below have different meanings:

| Call | Result | Explanation |
| --- | --- | --- |
| `source.replaceAll(regex, "$2:$1")` | `42:id` | `$2` and `$1` are expanded from capturing groups |
| `source.replaceAll(regex, Matcher.quoteReplacement("$2:$1"))` | `$2:$1` | Content with `$` is inserted literally |
| `source.replaceAll(regex, Matcher.quoteReplacement("USD $5\\tmp"))` | `USD $5\tmp` | Preserves both `$` and `\` |

Therefore **do not wrap the entire capturing-group template in `quoteReplacement`** if your intention is to use `$1`, `$2`, or `${name}` to build output from matched data. Conversely, if a replacement value comes from a text input field, configuration, or dynamic content where the user wants exact characters preserved, `quoteReplacement` is the proper safeguard.

You can mix capturing-group data and literal text by **building the final result value for each match**, then calling `quoteReplacement` on that final value before passing it to `appendReplacement`; an example appears in the next section. This approach also avoids ambiguities like concatenating `"$1" + "2"` into `"$12"`: the processor might interpret `$12` as group 12 if that group exists.

## 5. Per-Match Dynamic Replacement with Matcher.appendReplacement

`String.replaceAll` takes one common replacement for every match. When the replacement needs to depend on the matched segment itself or custom logic, use `Matcher.find()` with `appendReplacement` and `appendTail`.

Example: for each code consisting of two uppercase letters and two digits, wrap it in `[` and `]`, and add a literal suffix containing `$` and `\`.

Save to `DynamicReplacementDemo.java`:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class DynamicReplacementDemo {
    public static void main(String[] args) {
        Pattern pattern = Pattern.compile("[A-Z]{2}[0-9]{2}");
        Matcher matcher = pattern.matcher("AB12 and CD34");
        StringBuilder result = new StringBuilder();

        while (matcher.find()) {
            String text = "[" + matcher.group() + " $5\\log]";
            matcher.appendReplacement(
                    result,
                    Matcher.quoteReplacement(text));
        }
        matcher.appendTail(result);

        System.out.println(result);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 DynamicReplacementDemo.java
java DynamicReplacementDemo
~~~

Result:

~~~text
[AB12 $5\log] and [CD34 $5\log]
~~~

Execution sequence:

1. `find()` locates `AB12`, then `CD34`.
2. `group()` returns the matched segment and lets the program build a separate replacement each time.
3. `quoteReplacement(text)` ensures that `$` and `\` in the final value are treated as literal data.
4. `appendReplacement` appends the unprocessed text and the replacement for the current match to the `StringBuilder`.
5. `appendTail` appends the remaining text after the final match. If you forget this step, the trailing text can be lost; if there are no matches, this step still preserves the entire original text.

`appendReplacement(StringBuilder, String)` has been available since Java 9, so it works in Java 17+. For a pattern reused many times, calling `Pattern.compile` once and creating a `Matcher` per input avoids unnecessary repeated regex compilation. Do not share the same `Matcher` across multiple threads without synchronization because it holds mutable state for each match search.

## 6. Common Mistakes

### 6.1. Inserting user-provided replacement without quoting

Incorrect example when `userReplacement` is `"$10"` or `"C:\\new"`:

~~~java
// Wrong if you want to replace with the exact string entered by the user:
String result = input.replaceAll(regex, userReplacement);
~~~

`$10` may be interpreted as a group reference (group numbering rules depend on existing groups); `\` may be consumed to escape the following character. If `$` is in an invalid position or the referenced group does not exist, the program can throw `IllegalArgumentException` or `IndexOutOfBoundsException` depending on the case.

The right way to insert literally:

~~~java
String result = input.replaceAll(
        regex, Matcher.quoteReplacement(userReplacement));
~~~

### 6.2. Confusing Java escapes with replacement escapes

The two layers have different roles:

- **Java string layer:** `"\\"` represents **one** `\` in the runtime value. In the code example, `"$1\\docs"` is a value containing the characters `$`, `1`, `\`, `d`, `o`, `c`, `s`.
- **Regex replacement layer:** The `replaceAll` processor assigns special meaning to `$` and `\` in the runtime value. `quoteReplacement` makes them literal without requiring manual escaping.

Note: when reading a regex or string from a variable or file, **Java source** escapes have already been processed (or do not apply); you should not arbitrarily add `\` before calling `quoteReplacement`.

### 6.3. Using quoteReplacement to fix an invalid regex

`Matcher.quoteReplacement` only protects the **replacement** string. It does not fix a regex missing a `]`, does not turn `.*` into a literal search pattern, and does not handle `PatternSyntaxException` thrown by the search argument. If you want to match exact input text, use `Pattern.quote` for the regex argument or `String.replace` when regex is not needed.

### 6.4. Over-quoting when intending to use capturing groups

~~~java
// Want to swap two groups: right
String ok = "A1".replaceAll("([A-Z])(\\d)", "$2$1");

// Want "$2$1" to appear literally: right
String literal = "A1".replaceAll(
        "([A-Z])(\\d)", Matcher.quoteReplacement("$2$1"));
~~~

The value of `ok` is `"1A"`, while `literal` is `"$2$1"`. The difference comes from the **intended use of the replacement**, not because one syntax is "better" in every situation.

### 6.5. Forgetting to handle null, large inputs, or regex complexity

- `Matcher.quoteReplacement(null)` throws `NullPointerException`; check for null or define a missing-data policy before calling it.
- If the regex matches nothing, `replaceAll` returns the entire original content; `quoteReplacement` does not force a match.
- `quoteReplacement` only handles special characters in the replacement. It does not protect against overly expensive regexes (such as certain nested repetitions causing *catastrophic backtracking*), does not validate formats, and does not automatically limit input size.

## 7. Practice Exercise

Predict the output:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReplacementQuiz {
    public static void main(String[] args) {
        System.out.println("aa".replaceAll("a", Matcher.quoteReplacement("$0")));
        System.out.println("a1".replaceAll("([a-z])(\\d)", "$2$1"));
        System.out.println("a1".replaceAll("([a-z])(\\d)",
                Matcher.quoteReplacement("$2$1")));
        System.out.println("x.y".replaceAll(
                Pattern.quote("."), Matcher.quoteReplacement("$")));
        System.out.println("aaa".replaceFirst("a",
                Matcher.quoteReplacement("\\dir")));
    }
}
~~~

Save `ReplacementQuiz.java`, run `javac -encoding UTF-8 ReplacementQuiz.java` then `java ReplacementQuiz`. Answer:

~~~text
$0$0
1a
$2$1
x$y
\diraa
~~~

Why: both `a` characters are replaced by the literal string `$0`; unquoted `$2$1` swaps the groups; quoted preserves the characters; `Pattern.quote(".")` finds the literal dot; and `replaceFirst` replaces only the first `a` with `\dir`.

## Summary and Application Checklist

- Ask clearly: **should the replacement value be kept literal or expand capturing groups?** Only use `Matcher.quoteReplacement` for parts that must remain literal.
- With a regex to search and arbitrary content to replace: `replaceAll(regex, Matcher.quoteReplacement(text))`.
- When both search string and replacement string are literal: prefer `String.replace(target, replacement)`; if a matcher is needed, combine `Pattern.quote(target)` and `Matcher.quoteReplacement(replacement)`.
- For replacement content that varies per match: compute the value to insert based on `group()`, pass it through `quoteReplacement` before `appendReplacement`, and finally call `appendTail`.
- Test cases with `$`, `\`, no match, multiple matches, empty strings, capturing groups, and `null` values.

## References

- [Java SE 17 — Matcher.quoteReplacement(String)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html#quoteReplacement(java.lang.String))
- [Java SE 17 — Matcher.appendReplacement and appendTail](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
- [Java SE 17 — Pattern.quote(String)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html#quote(java.lang.String))
- [Java SE 17 — String.replaceAll, replaceFirst, replace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
