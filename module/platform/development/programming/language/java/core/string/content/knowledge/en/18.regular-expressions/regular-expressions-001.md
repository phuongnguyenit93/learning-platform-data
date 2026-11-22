# String.matches(): Validating the Entire String with Regular Expressions

## Objectives

After this lesson, you will be able to explain why `String.matches(regex)` returns `true` only when the **entire** `String` value matches the regex; write regexes in Java string literals properly; distinguish full-string validation from substring searching; and choose between `String.matches` and `Pattern`/`Matcher` for each situation.

## 1. Principle: Full-String Match, Not Substring Search

The method has the signature:

~~~java
public boolean matches(String regex)
~~~

`regex` is a regular expression; the return type is `boolean`. `text.matches(regex)` produces the same result as `Pattern.matches(regex, text)` from `java.util.regex.Pattern`.

The condition for success is that **the regex must cover the entire input string**, from the first character to the last. For example:

| String | Java Regex | Result | Reason |
| --- | --- | --- | --- |
| `"abc123"` | `"[a-z]+\\d+"` | `true` | Lowercase letters followed by one or more digits, with no extra characters |
| `"abc123!"` | `"[a-z]+\\d+"` | `false` | The `!` character is not part of the pattern |
| `"12345"` | `"\\d+"` | `true` | The entire string consists of digits |
| `"ID-42"` | `"\\d+"` | `false` | Has the prefix `ID-` |
| `"abcXYZdef"` | `"XYZ"` | `false` | `XYZ` appears only in the middle |
| `"abcXYZdef"` | `".*XYZ.*"` | `true` | The parts before and after `XYZ` are allowed by the regex |

You can think of `matches` as checking **does the whole string have this exact form?**, whereas `Matcher.find()` checks **is there any match somewhere in the string?**. There is no need to add `^` and `$` just to force `String.matches` to match the entire string: the API itself already requires that. However, `^`/`$` are anchors with their own semantics in regex (especially when using the multiline flag), so adding anchors should not be treated as an always-equivalent transformation in every case.

## 2. Standalone Runnable Java 17+ Example

Save to `StringMatchesDemo.java`:

~~~java
public class StringMatchesDemo {
    public static void main(String[] args) {
        System.out.println("abc123".matches("[a-z]+\\d+"));
        System.out.println("abc123!".matches("[a-z]+\\d+"));
        System.out.println("123".matches("\\d+"));
        System.out.println("ID-42".matches("ID-\\d{2}"));
        System.out.println("42".matches("\\d"));
        System.out.println("42".matches("\\d+"));

        System.out.println("".matches("a*"));
        System.out.println("".matches("a+"));

        System.out.println("abcXYZdef".matches("XYZ"));
        System.out.println("abcXYZdef".matches(".*XYZ.*"));

        System.out.println("a\nb".matches("a.b"));
        System.out.println("a\nb".matches("(?s)a.b"));
    }
}
~~~

Run from the terminal in the directory containing the file:

~~~bash
javac -encoding UTF-8 StringMatchesDemo.java
java StringMatchesDemo
~~~

Standard output (in exact order of the `println` statements):

~~~text
true
false
true
true
false
true
true
false
false
true
false
true
~~~

Explanation of easily confused cases:

- `"42".matches("\\d")` returns `false` because `\d` matches **one** digit, whereas the string has two; `\d+` allows one or more digits.
- `"".matches("a*")` is `true` because `*` allows **0 occurrences**; `a+` requires at least one `a`.
- `"abcXYZdef".matches("XYZ")` is `false` because the `abc` and `def` parts are not covered by the pattern.
- By default, the dot `.` does not match the newline character in the example; `(?s)` enables DOTALL mode, so `"a\nb"` matches `(?s)a.b`.

## 3. Two Syntax Layers: Java String and Regex

A regex is passed as a **Java string**, so the backslash `\` must go through two layers of interpretation: Java processes the string literal first, and then the regex engine reads the pattern. For example, for the regex to see `\d+`, the Java source code must write `"\\d+"`.

| What to match | Meaningful regex pattern | Written in Java code |
| --- | --- | --- |
| One or more digits | `\d+` | `"\\d+"` |
| Exactly three digits | `\d{3}` | `"\\d{3}"` |
| A literal dot | `\.` | `"\\."` |
| A regex whitespace character | `\s` | `"\\s"` |
| A code with 2 uppercase letters, a hyphen, and 3 digits | `[A-Z]{2}-\d{3}` | `"[A-Z]{2}-\\d{3}"` |

Some commonly used components:

- `[abc]`: one character from the set `a`, `b`, `c`; `[A-Z]`: one uppercase Latin letter in the specified range.
- `\d`, `\w`, `\s`: predefined character classes; Unicode semantics may be affected by regex flags.
- `?`: 0 or 1 time; `*`: 0 or more times; `+`: 1 or more times; `{n}`: exactly n times; `{m,n}`: from m to n times.
- `(...)`: group; `|`: alternation; `.`: any character except certain line terminators unless DOTALL is enabled.
- `[0-9]` explicitly matches ASCII digits; `\d` by default uses Java's regex digit class and can expand when `UNICODE_CHARACTER_CLASS`/`(?U)` is enabled.

For example, `"v1x2".matches("v1.2")` is `true` because `.` represents any single character (`x` here). To match a literal dot, use `"v1\\.2"`. If the string to match comes from user input and must be interpreted **literally**, use `Pattern.quote(text)` instead of embedding it directly into the regex.

## 4. Comparing matches, find, lookingAt, and contains

`String.matches` and `Matcher.matches()` both require matching the entire string (or the entire *region* configured in `Matcher`). `Matcher.lookingAt()` checks a prefix, while `Matcher.find()` scans for a matching subsequence. `String.contains` only searches for a **literal** character sequence and does not interpret regex syntax.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class MatchVsFindDemo {
    public static void main(String[] args) {
        String text = "Order 42";
        Pattern digits = Pattern.compile("\\d+");

        System.out.println(digits.matcher(text).matches());
        System.out.println(digits.matcher(text).lookingAt());

        Matcher matcher = digits.matcher(text);
        System.out.println(matcher.find());
        System.out.println(matcher.group());

        System.out.println(text.contains("42"));
        System.out.println(text.matches(".*\\d+"));
    }
}
~~~

Save as `MatchVsFindDemo.java`, compile with `javac -encoding UTF-8 MatchVsFindDemo.java`, and run `java MatchVsFindDemo`. Output:

~~~text
false
false
true
42
true
true
~~~

`matches()` fails because `"Order "` is left over; `lookingAt()` fails because the beginning of the string is not a digit; `find()` finds `42`, and `group()` returns the matched substring. The example creates a separate `Matcher` for each check so it does not depend on the state of previous match attempts.

| Requirement | Appropriate API |
| --- | --- |
| Validate whether the entire value conforms to a regex format | `value.matches(regex)` or `pattern.matcher(value).matches()` |
| Find a regex match anywhere inside text | `pattern.matcher(value).find()` |
| Check the beginning of the string against a regex | `pattern.matcher(value).lookingAt()` |
| Check for the presence of a fixed literal substring | `value.contains(literal)` |
| Compare the entire string with a fixed literal value | `value.equals(literal)` |

## 5. Application: Validating Data Formats

Suppose a code has the form **two uppercase ASCII letters, one `-`, and exactly three ASCII digits**. The appropriate regex is `[A-Z]{2}-[0-9]{3}`. Use `matches` to prevent leading or trailing extra characters from being accidentally accepted.

~~~java
import java.util.regex.Pattern;

public class CodeValidationDemo {
    private static final Pattern CODE = Pattern.compile("[A-Z]{2}-[0-9]{3}");

    public static boolean isValidCode(String value) {
        return value != null && CODE.matcher(value).matches();
    }

    public static void main(String[] args) {
        String[] candidates = {"AB-123", "AB-1234", "ab-123", " AB-123", "XY-000"};
        for (String candidate : candidates) {
            System.out.println(candidate + " -> " + isValidCode(candidate));
        }
        System.out.println("null -> " + isValidCode(null));
    }
}
~~~

Save as `CodeValidationDemo.java` and run:

~~~bash
javac -encoding UTF-8 CodeValidationDemo.java
java CodeValidationDemo
~~~

Output:

~~~text
AB-123 -> true
AB-1234 -> false
ab-123 -> false
 AB-123 -> false
XY-000 -> true
null -> false
~~~

In this example, `Pattern.compile(...)` is called once and reused: this makes sense when checking the same regex many times. `String.matches(regex)` is convenient for short, infrequent checks; each call performs an operation equivalent to `Pattern.matches(regex, value)`, so avoid recompiling the expression unnecessarily inside a large loop.

This is **syntactic validation**; it does not confirm that a code actually exists in the system. Similarly, a regex for an email or URL rarely replaces all business rules or real verification steps.

## 6. Common Mistakes and How to Handle Them

**1. Confusing full-string matching with substring searching.** If you want to find the number in `"Order 42"`, use `find()`. If you must validate a format consisting of both a prefix and digits, write a pattern covering both, such as `"Order \\d+"`.

**2. Forgetting to escape backslashes in Java.** The code `"\\d+"` produces the regex `\d+`. Writing `"\d+"` directly in a Java string is a compile error (*illegal escape character*). For a literal dot, you must write `"\\."`, not `"."`.

**3. Assuming `.` matches everything including newlines.** By default, the dot does not match line terminators. Use `(?s)` when you intentionally want DOTALL mode, or choose a stricter character set if you are validating data.

**4. Overlooking leading/trailing whitespace.** `" AB-123 "` does not match `[A-Z]{2}-[0-9]{3}`. Only call `strip()` before `matches` if the input rules allow ignoring whitespace; if whitespace is invalid data, keep the input unchanged so it is rejected.

**5. Not accounting for `null` or invalid regexes.** Calling `matches` on a `null` `String` variable causes a `NullPointerException`. A syntactically invalid regex like `"[abc"` causes a `PatternSyntaxException`. If the regex comes from an external source, handle syntax errors and limit complexity before running it.

**6. Accepting overly broad input.** The pattern `".*"` matches even an empty string; `".+"` does not match an empty string, but is still far too broad for an identifier. Write the exact character classes and lengths actually needed (for example, `[A-Z]{2}-[0-9]{3}`).

**7. Treating regex as a validator for all languages/characters.** `[A-Z]` only refers to letters from A to Z; `(?i)` can enable case-insensitive matching according to regex rules, but Unicode/other-language requirements may need appropriate character classes and flags. Do not assume an ASCII pattern covers Vietnamese or all of Unicode.

**8. Feeding untrusted regexes into long input processing.** Some expressions with nested repetitive branches cause huge execution time (*catastrophic backtracking*) on near-matching strings. Prefer simple, bounded regexes; consider input limits, performance, and specialized parser solutions if needed.

## 7. Self-Check

Without running the code, predict the results:

1. `"A12".matches("[A-Z]\\d{2}")`
2. `"A123".matches("[A-Z]\\d{2}")`
3. `"".matches("\\d*")`
4. `"x42y".matches("\\d+")`
5. `"x42y".matches(".*\\d+.*")`

**Answers:** (1) `true`; (2) `false` because there is one extra digit; (3) `true` because `*` allows 0 occurrences; (4) `false` because of `x` and `y`; (5) `true` because `.*` on both sides covers the non-digit characters.

When designing a pattern for validation yourself, always test at least four categories of values: **valid**, **extra prefix/suffix**, **missing or invalid characters**, and **empty/null**. This is a quick way to catch confusion between full-string validation and partial matching.

## Official References

- [Java SE 17 — String.matches(String regex)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#matches(java.lang.String))
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 17 — Matcher: matches(), lookingAt(), find()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html)
