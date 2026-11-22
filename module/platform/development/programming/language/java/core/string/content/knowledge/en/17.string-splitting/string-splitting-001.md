# `String.split(regex)`: regex is the rule for finding delimiters

In Java, `String.split(...)` finds **substrings matching a regular expression (regex)** and splits the string at those matches. The argument is not necessarily a literal delimiter character. Therefore, `"a.b.c".split(".")` does **not** produce `["a", "b", "c"]`: in regex, `.` is a wildcard that matches almost any character.

This lesson focuses on **how to write regexes** and **Java's two layers of escaping**. Subsequent lessons cover `limit`, empty elements, zero-width matches, `Pattern.quote`, streams, and CSV data separately.

## 1. The `String.split` contract

Two overloads:

```java
public String[] split(String regex)
public String[] split(String regex, int limit)
```

Both return a `String[]` containing the segments **between regex matches**; the matched segment acting as the delimiter is not kept as a separate token. The one-argument overload is equivalent to `split(regex, 0)`: by default, it discards all **trailing** empty elements. If you need to control the number of parts or preserve trailing empty fields, use the overload with `limit`.

```java
String[] colors = "red,green,blue".split(",");
// ["red", "green", "blue"]
```

A comma is not a Java regex metacharacter, so the pattern `","` is also a literal comma. However, many other characters carry syntactic meaning:

| Target | Argument in Java source | Resulting regex |
| --- | --- | --- |
| Literal comma | `","` | `,` |
| Literal dot | `"\\."` | `\.` |
| Literal pipe | `"\\|"` | `\|` |
| One or more whitespace characters | `"\\s+"` | `\s+` |
| Comma or semicolon | `"[,;]"` | Character class |
| One or more colons | `":+"` | `:+` |
| Dynamic literal delimiter | `Pattern.quote(delimiter)` | Matches the exact configured string |

Symbols such as `.`, `|`, `+`, `*`, `?`, `[ ]`, `( )`, `\` have special roles in certain regex contexts. Do not pass an external delimiter directly into `split` if the goal is a literal match.

## 2. Java's two layers of escaping

To match a **literal dot**, the regex engine needs `\.`. However, `\` is also the escape character in Java string literals; for a Java string to contain `\`, you must write `\\`. Thus, Java code needs `split("\\.")`.

- `split(".")`: Valid Java, regex matches most ordinary characters, wrong for matching a dot.
- `split("\\.")`: Valid Java, regex matches the exact `.` character.
- `split("\.")`: Invalid Java source because the literal escape `\.` does not exist.
- `split("\\s+")`: Java passes the regex `\s+`, matching one or more whitespace characters depending on the regex mode.

Note: Java 15+ has the **string literal escape** `\s`, which means a single space. Therefore, writing `split("\s+")` in modern Java creates the regex ` +` (one or more spaces) instead of the `\s+` whitespace class that writers usually expect.

## 3. Running an example to verify regexes

Save `RegexSplitDemo.java` and compile with JDK 17+:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class RegexSplitDemo {
    public static void main(String[] args) {
        String dots = "a.b.c";
        System.out.println(dots.split(".").length);
        System.out.println(Arrays.toString(dots.split("\\.")));

        String pipes = "red|green|blue";
        System.out.println(Arrays.toString(pipes.split("\\|")));
        System.out.println(Arrays.toString("red   green\tblue".split("\\s+")));
        System.out.println(Arrays.toString("a,b;c".split("[,;]")));

        String delimiter = "|+|";
        String input = "left|+|middle|+|right";
        System.out.println(Arrays.toString(
                input.split(Pattern.quote(delimiter))));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RegexSplitDemo.java
java RegexSplitDemo
```

```text
0
[a, b, c]
[red, green, blue]
[red, green, blue]
[a, b, c]
[left, middle, right]
```

The first line is `0` because the regex `.` matches every character in the example string and `limit=0` discards all trailing empty parts by default. That is an example of a **syntactically valid pattern with the wrong data semantics**.

For `"a,,b"`, `split(",")` preserves the middle empty element, whereas `split(",+")` treats the pair of commas as **one** match and does not produce an empty column in between. Which one is right depends on the data: whitespace groups between words can be collapsed, whereas two commas in columnar data usually represent an empty field.

## 4. Limitations and error handling

- An unclosed regex, such as `"["`, causes `split` to throw `PatternSyntaxException`; it does not return an empty array to signal an error.
- `"a,b".split(null)` or calling `split` on a `null` source string reference throws `NullPointerException`.
- Java's default `\s` regex does not necessarily cover all Unicode whitespace. When broad Unicode coverage is needed, consider `Pattern.UNICODE_CHARACTER_CLASS` and test the exact character set.
- Overly complex regexes from untrusted input can cause CPU-intensive backtracking. When the delimiter is literal text, `Pattern.quote` prevents misinterpretation as regex syntax.
- `split("")` is not a Unicode grapheme cluster splitter; a user-perceived character may contain multiple code points or UTF-16 code units.
- `String.split(",")` does not understand CSV quotes, even with `limit=-1`. For real CSV, you need a parser that tracks quote state and multi-line records.

When the same pattern is used frequently, `Pattern.compile(regex).split(input, limit)` allows reusing the `Pattern`. The rules for `limit` are the same as for `String.split`.

## 5. Self-check

1. Why does `"api.example.org".split(".")` not split on dots? Write two ways to fix it.
2. Which regex splits `"one;two,three"` at `;` or `,`?
3. Why does `"a,,b".split(",+")` produce fewer tokens than `split(",")`?
4. If a delimiter from configuration has the value `"|+|"`, how should you prepare the regex?

**Answers:** (1) `.` is a wildcard; use `"\\."` or `Pattern.quote(".")`. (2) `"[,;]"`. (3) `+` collapses consecutive delimiters; this can lose empty fields. (4) Use `Pattern.quote(delimiter)`.

**Remember:** Before counting tokens, you must know **the exact regions of the input that the regex will match**.