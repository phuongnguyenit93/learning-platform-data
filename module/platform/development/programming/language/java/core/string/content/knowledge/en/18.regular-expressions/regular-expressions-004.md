# Character Classes, Quantifiers, Anchors, and Capturing Groups in Java Regex

A regular expression (regex) describes a character pattern for **validating**, **searching**, **extracting**, or **replacing** strings. Four key components are: **character classes**, which decide which characters are allowed at a position; **quantifiers**, which decide how many times a unit occurs; **anchors/boundaries**, which constrain where matches occur; and **capturing groups**, which group subpatterns and store matched text for retrieval or backreferencing. In Java, these patterns are executed via `java.util.regex.Pattern` and `Matcher`.

## 1. Reading Regexes Properly in Java

There are two syntax layers to distinguish:

- **Regex**: `\d{2}` means two digits; `\b` means a word boundary.
- **Java string literal**: `\` must be written as `\\`. Therefore, the regex `\d{2}` is passed via the Java string `"\\d{2}"`, and the regex `\b` via `"\\b"`. If you write `"\b"`, Java creates a backspace character instead of a word boundary.

| Actual regex pattern | Corresponding Java string | Meaning |
| --- | --- | --- |
| `\d+` | `"\\d+"` | One or more digits |
| `\bcat\b` | `"\\bcat\\b"` | Standalone word `cat` |
| `^[A-Z]{2}\d{3}$` | `"^[A-Z]{2}\\d{3}$"` | Entire string is two uppercase letters then three digits |
| `\.` | `"\\."` | A literal dot, not the regex `.` wildcard |

`Pattern.compile(regex)` compiles a pattern; `pattern.matcher(input)` creates a `Matcher` for an input. Three common matching methods:

- `matcher.matches()` requires the **entire input** to match the pattern.
- `matcher.find()` finds the **next subsequence** matching the pattern; call repeatedly to iterate through matches.
- `matcher.lookingAt()` requires a match **from the start of the search region**, without requiring it to reach the end.

For example, with regex `\d+` and input `"abc123xyz"`, `find()` succeeds and extracts `123`, whereas `matches()` and `lookingAt()` both return `false`. Only call `group()`, `start()`, or `end()` after a match operation succeeds; otherwise `IllegalStateException` may be thrown.

## 2. Character Classes

A character class normally matches **one character** from an allowed set; a trailing quantifier is what makes it repeat multiple times.

| Regex syntax | Meaning | Match example |
| --- | --- | --- |
| `[abc]` | One of `a`, `b`, `c` | `b` |
| `[^abc]` | One character not in `a`, `b`, `c` | `x` |
| `[a-z]` | One character in the range from `a` to `z` | `m` |
| `[A-Za-z0-9_]` | One Latin letter, ASCII digit, or `_` | `T`, `7`, `_` |
| `[a-f&&[^b-d]]` | Intersection of `a`–`f` with the complement of `b`–`d` | `a`, `e`, `f` |
| `\d` / `\D` | Digit / non-digit | `5` / `Z` |
| `\s` / `\S` | Whitespace character / non-whitespace character | space / `A` |
| `\w` / `\W` | *Word* character / non-*word* character | `a` / `!` |
| `\p{L}` | One Unicode character in the Letter category | `Đ`, `ê`, `A` |

Negation inside a character class is `^` **immediately after `[`**: `[^0-9]` accepts one character that is not an ASCII digit. A `^` outside a character class is a line/region start anchor (section 4), not negation. The hyphen `-` can form a range: `[a-z]`; if you want a literal `-`, you can place it at the start/end such as `[-+]` or escape it appropriately. Characters `]`, `\`, `^`, `-` have position-dependent meanings inside a class, so check placement/escaping rather than assuming they are always plain characters.

**Note on Unicode:** by default in Java, `\d`, `\w`, and many shorthand classes follow ASCII-oriented semantics; do not assume `\w+` covers all Vietnamese names. Use `\p{L}` when Unicode letters are needed, or enable `Pattern.UNICODE_CHARACTER_CLASS` (embedded flag `(?U)`) so shorthand and POSIX classes are interpreted according to Unicode. Data rules matter even more than regex: personal names can contain spaces, apostrophes, hyphens, or combining marks; a letter class alone is not enough to serve as a complete name validator.

**Dot `.` is not `[.]`:** `.` matches almost any character, but by default **does not match line terminators**; the `Pattern.DOTALL` flag (`(?s)`) allows `.` to match those characters as well. Only `\.` or `[.]` matches a literal dot. The class `[\s\S]` can match both whitespace and non-whitespace characters, but is usually harder to read than an explicit pattern with `DOTALL`.

## 3. Quantifiers

A quantifier applies to **the unit immediately preceding it**: a single character, a character class, or a group. For example, `ab+` is `a` followed by one or more `b`, whereas `(ab)+` repeats the pair `ab`.

| Quantifier | Number of occurrences | Example |
| --- | --- | --- |
| `X?` | 0 or 1 | `colou?r` matches `color`, `colour` |
| `X*` | 0 or more | `a*` matches even an empty string |
| `X+` | 1 or more | `a+` matches `a`, `aaa` |
| `X{n}` | Exactly `n` | `\d{4}` matches four digits |
| `X{n,}` | At least `n` | `[A-Z]{2,}` |
| `X{n,m}` | From `n` to `m` (inclusive) | `\d{2,4}` |

A quantifier has three strategies:

1. **Greedy**, e.g., `.*`, `a+`, `a{2,4}`: tries to consume as much as possible, **and can backtrack** so the remainder matches.
2. **Reluctant/lazy**, e.g., `.*?`, `a+?`, `a{2,4}?`: tries to consume as little as possible first, then expands if needed.
3. **Possessive**, e.g., `.*+`, `a++`, `a{2,4}+`: consumes as much as possible **and never gives characters back** via backtracking.

For the input `<a><b>`, the pattern `<.*>` matches all of `<a><b>` because it is greedy; the pattern `<.*?>` causes `find()` to return `<a>` then `<b>`. However, properly parsing XML/HTML tags requires a corresponding parser: this illustrative regex does not handle nested tags, quoted strings, and markup language structure.

~~~java
// QuantifierDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QuantifierDemo {
    public static void main(String[] args) {
        String input = "<a><b>";
        Matcher greedy = Pattern.compile("<.*>").matcher(input);
        if (greedy.find()) {
            System.out.println("Greedy: " + greedy.group());
        }

        Matcher reluctant = Pattern.compile("<.*?>").matcher(input);
        while (reluctant.find()) {
            System.out.println("Reluctant: " + reluctant.group());
        }

        System.out.println("a+a on aaa: " + Pattern.matches("a+a", "aaa"));
        System.out.println("a++a on aaa: " + Pattern.matches("a++a", "aaa"));
    }
}
~~~

Run with `javac --release 17 QuantifierDemo.java` then `java QuantifierDemo`:

~~~text
Greedy: <a><b>
Reluctant: <a>
Reluctant: <b>
a+a on aaa: true
a++a on aaa: false
~~~

In the last two lines, `a+a` can give back one `a` so the trailing `a` matches. `a++a` consumes all of `aaa` and does not backtrack, so it fails. `*?` does not mean "never take more": it still expands when the rest of the pattern requires it.

## 4. Anchors and Boundaries

Anchors check **positions** and normally consume no characters. Thus `^\d+$` describes a digit sequence spanning the entire string in typical checks; plain `\d+` can find a digit sequence sitting in the middle of text.

| Regex symbol | Matched position |
| --- | --- |
| `^` | Start of input/region; with `MULTILINE`, also the start of each line |
| `$` | End of input/region, with special handling before a final line terminator; with `MULTILINE`, also the end of each line |
| `\A` | Absolute start of input for the active region |
| `\z` | Absolute end of input for the active region |
| `\Z` | End of input, possibly just before a final line terminator |
| `\b` | Word boundary: transition between a *word* character and a non-*word* character |
| `\B` | Non-word-boundary position |
| `\G` | End of the previous match (useful when requiring contiguous `find()` matches) |

`Pattern.MULTILINE` (flag `(?m)`) changes how `^` and `$` behave around lines. For example, `Pattern.compile("^foo$", Pattern.MULTILINE).matcher("foo\nbar").find()` is `true` because it matches the `foo` line; yet `matches()` on that entire string is still `false`. `DOTALL` alters the behavior of **`.`**, not the role of `^` and `$`.

`\bcat\b` finds the standalone word `cat` in `"a cat!"`, whereas the pattern `cat` can also match inside `"concatenate"`. A word boundary **is not the same as a space**: punctuation, digits, underscores, combining marks, and Unicode can make results differ from natural-language intuition. If a business rule defines "word" in a specific language, test it on real strings.

When validating an **entire string**, prefer `matcher.matches()` because the intent is explicit; when reading **line by line** with `find()`, use `MULTILINE` intentionally; when needing an absolute end anchor in a pattern that might be used with `find()`, consider `\A` and `\z` rather than assuming `$` always has the same meaning.

## 5. Capturing Groups and Non-Capturing Groups

Parentheses do two things: **group branches/units for a quantifier to apply to** and, by default, **remember the matched text**.

| Syntax | Purpose |
| --- | --- |
| `(ab)+` | Capturing group for `ab`, repeated at least once |
| `(?:ab)+` | **Non-capturing** group: groups `ab` for repetition without creating a group index |
| `(cat|dog)` | Capturing group matching either branch |
| `(?<day>\d{2})` | Named capturing group `day` |
| `\1` | Backreference to the **content** matched by capturing group 1 |
| `\k<day>` | Backreference to the content of the named group `day` |

Capturing groups are numbered **1, 2, ...** in the order of opening `(` parentheses of capturing groups when scanning the pattern left to right; group `0` is the **entire match**. `(?:...)` does not increment the group count. After `find()` or `matches()` succeeds, `group(1)`, `group("day")`, `start(1)`, `end(1)` retrieve the content and positions; `end()` is an **exclusive** index. Java positions use UTF-16 indices, so with supplementary Unicode characters (outside the BMP) they do not match visible character indices. `groupCount()` returns the number of capturing groups, excluding group `0`.

If a branch or optional group does not participate in a match, `group(n)` for that group is `null` (and `start(n)`, `end(n)` are `-1`). Distinguish "did not participate" from a group that matched the **empty string**. If a group sits under a quantifier and matches multiple times, `group(n)` is not a list of all captures; typically it retains the last captured value. To obtain all occurrences, design the pattern and `find()` loop accordingly.

Group names in Java are Latin alphanumeric names starting with a letter, followed by letters/digits; e.g., `day`, `year2`. Do not reuse the same name within a single pattern. Non-capturing groups are appropriate when only grouping is needed, such as `(?:https?://)?`, keeping capturing group indices stable.

### Runnable Example: Validation, Named Capturing Groups, and Positions

~~~java
// RegexDemo.java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexDemo {
    public static void main(String[] args) {
        Pattern username = Pattern.compile("^[A-Za-z][A-Za-z0-9_]{2,11}$");
        for (String value : List.of("an", "anh_2026", "3abc", "abc_DEF012")) {
            System.out.println(value + " -> " + username.matcher(value).matches());
        }

        Pattern date = Pattern.compile("(?<day>\\d{2})/(?<month>\\d{2})/(?<year>\\d{4})");
        Matcher matcher = date.matcher("Due: 03/11/2026; 25/12/2026.");
        while (matcher.find()) {
            System.out.println(matcher.group(0) + " -> "
                    + matcher.group("day") + "/" + matcher.group("month")
                    + "/" + matcher.group("year")
                    + " [" + matcher.start() + ", " + matcher.end() + ")");
        }
    }
}
~~~

Run `javac --release 17 RegexDemo.java` and `java RegexDemo`:

~~~text
an -> false
anh_2026 -> true
3abc -> false
abc_DEF012 -> true
03/11/2026 -> 03/11/2026 [5, 15)
25/12/2026 -> 25/12/2026 [17, 27)
~~~

The username pattern uses **character classes** and the **quantifier `{2,11}`**: the first character is a Latin letter, and the remaining 2–11 characters are letters/digits/`_`, meaning **3–12 characters** total. `matches()` checks the entire string. The date pattern uses three named groups; `find()` locates each subsequence. This is an example of **extracting by `dd/MM/yyyy` shape**, not validating calendar dates: `99/99/2026` still matches the regex; use `java.time` to check actual date values.

### Backreferences: Finding Repeated Words

The regex `\b(?<word>[A-Za-z]+)\s+\k<word>\b` finds two identical words separated by whitespace. The second word must have **the exact content just captured by group `word`**, not merely any arbitrary word. The `CASE_INSENSITIVE` flag is needed if `Go go` should match:

~~~java
// BackreferenceDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class BackreferenceDemo {
    public static void main(String[] args) {
        Pattern repeatedWord = Pattern.compile(
                "\\b(?<word>[A-Za-z]+)\\s+\\k<word>\\b",
                Pattern.CASE_INSENSITIVE);
        Matcher matcher = repeatedWord.matcher("Go go, step ahead, Java java.");
        while (matcher.find()) {
            System.out.println(matcher.group());
        }
    }
}
~~~

Run `javac --release 17 BackreferenceDemo.java` and `java BackreferenceDemo`:

~~~text
Go go
Java java
~~~

**Distinction:** backreferences `\1` or `\k<word>` require repeating **the exact value already matched**; whereas `([A-Za-z]+)\s+([A-Za-z]+)` only requires any two words. In a Java string literal, write group 1 backreference as `"\\1"` and named backreference as `"\\k<word>"`.

## 6. Combining Components to Solve a Problem

A testable pattern-building workflow:

1. Write down the **data format** and valid/invalid strings clearly; decide whether to match the full string or find substrings.
2. Choose **character classes** for each position (`[A-Z]`, `\d`, `\p{L}`, ...), considering Unicode.
3. Add **quantifiers** expressing lengths (`{4}`, `{2,8}`, `+`), wrapping units to repeat in parentheses (`(?:ab){3}`).
4. Add **anchors/boundaries** when truly needed, then pick `matches()` or `find()` accordingly.
5. Create **capturing groups** only for data to extract/compare; use `(?:...)` for remaining grouping.
6. Test empty strings, overly long inputs, unusual characters, newlines, Unicode, and strings causing heavy backtracking.

For example, expressing a code with two uppercase Latin letters, a `-`, and four digits is `^[A-Z]{2}-\d{4}$` (Java string: `"^[A-Z]{2}-\\d{4}$"`). The pattern accepts `AB-1234` and rejects `A-1234`, `AB_1234`, and `AB-12345` when using `matches()`. To capture the parts for separate processing: `^([A-Z]{2})-(\d{4})$`; retrieve the letter code via `group(1)` and the digits via `group(2)` after a successful match.

## 7. Common Mistakes and How to Avoid Them

- **Forgetting two levels of escaping**: Java `"\\d"` passes the regex `\d`; Java `"\b"` is backspace. If a regex comes from a config file or is read from input, **Java source** escaping rules no longer apply directly.
- **Confusing `find()` with `matches()`**: `find()` can accept part of the input. For full-string format validation, use `matches()` to avoid letting invalid prefixes/suffixes slip through.
- **Confusing `.` with a literal dot**, `^` inside/outside `[]`, or `ab+` with `(ab)+`; identify the exact regex unit each operator applies to.
- **Assuming lazy always captures structure cleanly**: `<.*?>` illustrates the difference from greedy, not a replacement for an HTML/XML/JSON parser. Regex cannot reliably validate complex nested structures on its own.
- **Using too many capturing groups**: replace grouping-only parentheses with `(?:...)` so `group(1)` and `group(2)` do not shift meaning when editing the pattern.
- **Not handling optional groups**: `group(n)` can be `null`; do not call `group()` when `find()`/`matches()` fails.
- **Equating Unicode with ASCII**: `[A-Z]`, `\w`, and `\d` have different scopes; test accented data, supplementary characters, combining marks, and enable Unicode flags when appropriate.
- **Expensive backtracking**: ambiguous nested quantifiers like `(a+)+$` can become very slow on long near-matching strings. Bound inputs, use specific character classes, unambiguous structure, or possessive quantifiers when preserving exact semantics. A compiled `Pattern` is reusable and thread-safe; each `Matcher` holds its own state and must not be shared concurrently across threads.
- **Embedding user text into a regex**: if searching for a **literal** string, use `Pattern.quote(userText)` rather than concatenating special characters straight into the regex. When replacing and inserting replacement text literally, consider `Matcher.quoteReplacement(replacementText)` because `$` and `\` have special meaning in replacements.

## 8. Self-Check Questions

1. Why is `Pattern.matches("a+", "baaa")` `false` while `Pattern.compile("a+").matcher("baaa").find()` is `true`?
2. For the string `"abab"`, do `(ab){2}` and `ab{2}` give the same result with `matches()`? Which unit does the quantifier apply to?
3. On `<a><b>`, how do `.*` and `.*?` cause `<...>` to capture different spans, and why can `.*+` make the pattern fail?
4. Write a pattern that captures `year`, `month`, and `day` separately in `"2026-10-23"` and explain why a format regex still does not replace calendar date validation.
5. When checking that a string ends **strictly** at the very end of the input, why is `\z` clearer than `$`?

**Takeaway:** character class = *what character*; quantifier = *how many times*; anchor/boundary = *at what position*; capturing group = *what part to group/capture*. Pick `matches()` for full-string validation, `find()` for searching/extracting, and test with real data examples to verify each layer of rules.
