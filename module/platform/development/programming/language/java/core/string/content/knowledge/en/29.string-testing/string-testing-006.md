# Testing Regex with Dots, Slashes, Dollar Signs, and Groups in Java

When writing regex in Java, the **dot `.`**, **slash `/`**, **dollar sign `$`**, and **grouping parentheses `(...)`** carry different meanings depending on whether they appear in a **regex pattern**, a **Java string**, or a **replacement string**. An expression that looks right can sometimes match invalid data, extract the wrong group, or produce unintended replacement output.

This lesson focuses on how to **test those symbols** with `java.util.regex.Pattern` and `Matcher` on Java 17+, including positive/negative tests, runnable snippets, and how to interpret results. Two guiding principles apply throughout: separate **regex syntax** from **Java String literal escaping**; separate **search patterns** from **replacement string syntax**.

## 1. Meaning Map of the Four Symbol Groups

| Symbol in **regex** | Meaning in a normal position | To match the literal character |
| --- | --- | --- |
| `.` | Matches any single character, excluding line terminators unless `DOTALL` is enabled | `\.` |
| `/` (forward slash) | Ordinary forward slash; Java `Pattern` does not use `/` to delimit regexes | Simply write `/` |
| `\` (backslash) | Escape character or start of shorthand classes like `\d`; useful when testing Windows paths | Regex `\\` |
| `$` | End-of-input/region anchor, with special rules around line endings | `\$` |
| `(...)` | Capturing group; groups subpatterns and captures content | `\(` and `\)` to match literal parentheses |
| `(?:...)` | **Non-capturing** group, only groups subpatterns | Does not create a group number |
| `(?<name>...)` | Named capturing group | Retrieve via `group("name")` |

**Important:** The table above describes **regex patterns**, not how Java strings are written. In Java source code, each `\` in a regex must be written as `\\`. For example, regex `\.` must be passed to Java as `"\\."`. Meanwhile, regex `/` only needs the Java string `"/"`.

In Java documentation, `Pattern.compile(regex)` compiles a pattern, `Matcher` performs matching, and `String.matches(regex)` checks the **entire** string. To avoid confusion when authoring tests, record both the regex and input clearly, and decide upfront whether you want a **full-string** match or a **substring** match before running.

## 2. The Dot: Wildcard `.` vs. Literal Dot `\.`

In regex, `.` is a **metacharacter**. The pattern `report.txt` means the letters `report`, **any single character**, then `txt`. Therefore it matches `reportXtxt`, `report-txt`, or `report/txt` when calling `matches()`.

To accept only a literal dot, escape it as `\.` in regex and write `"\\."` in Java:

~~~java
Pattern.matches("report.txt",  "reportXtxt"); // true: . is a wildcard
Pattern.matches("report\\.txt", "report.txt"); // true: literal dot
Pattern.matches("report\\.txt", "reportXtxt"); // false
~~~

The three lines above are **illustrative calls only** (requiring `import java.util.regex.Pattern` inside a Java method).

By default, `.` **does not match line terminators** such as `\n`. The `Pattern.DOTALL` flag (or `(?s)` in the regex) allows `.` to match line terminators too:

~~~java
Pattern.matches("a.b", "a\nb"); // false
Pattern.compile("a.b", Pattern.DOTALL)
       .matcher("a\nb").matches(); // true
~~~

Do not confuse `DOTALL` with `MULTILINE`: `DOTALL` changes how `.` matches line breaks; `MULTILINE` changes how the `^` and `$` anchors apply to lines.

Another way to write a literal dot is the character class `[.]`. Both regex `\.` and `[.]` match a single `.` character in this context. When splitting a filename on dots, also remember that `String.split(...)` takes a **regex**:

~~~java
String[] parts = "a.b".split("\\."); // ["a", "b"]
~~~

This is an illustrative snippet. Writing `"a.b".split(".")` causes regex `.` to match every character instead of acting as the `.` separator; the result is not the intended array.

### Minimal Tests for the Dot

| Regex written in Java | Input | `matches()` | Why |
| --- | --- | --- | --- |
| `"file.txt"` | `fileXtxt` | `true` | `.` accepts `X` |
| `"file\\.txt"` | `file.txt` | `true` | `\.` accepts only a dot |
| `"file\\.txt"` | `file-txt` | `false` | Missing literal dot |
| `"a.b"` | `a` + newline + `b` | `false` | `.` skips newlines by default |
| `"(?s)a.b"` | `a` + newline + `b` | `true` | DOTALL enabled |

If the input contains **user-supplied characters** like a filename `report.2026`, do not manually replace every dot inside a complex regex; `Pattern.quote(userText)` is safer for quoting the whole literal value (section 8).

## 3. Slashes: `/` Is Not a Delimiter in Java Regex

Some languages or tools write patterns in `/pattern/flags` form (such as JavaScript regex literals), leading learners to think every regex needs enclosing `/` characters. In Java, `Pattern.compile("api/v1/users")` uses the string's contents **directly** as the pattern, so a single `/` matches a literal forward slash in a path.

~~~java
Pattern.matches("api/v\\d+/users", "api/v2/users"); // true
Pattern.matches("api/v\\d+/users", "api\\v2\\users"); // false
~~~

These two lines are illustrative calls. The regex `api/v\d+/users` has ordinary forward slashes, while `\d+` is the special regex construct. Wrapping it in extra slashes, like `Pattern.compile("/api/v1/")`, makes Java search for **those slashes as part of the pattern itself**; it does not treat them as delimiters.

Distinguish **both kinds of slashes**:

- `/` (*forward slash*): normally needs no escaping in Java regex, very common in URLs and Unix-style paths.
- `\` (*backslash*): is the escape character of regex **and** of Java strings. To match **one** literal backslash, the regex needs `\\`; the Java string literal passed to `Pattern` must be written `"\\\\"`.

Illustrative Windows path example in Java:

~~~java
String path = "C:\\temp\\x.txt";              // data: C:\temp\x.txt
String regex = "C:\\\\temp\\\\x\\.txt";        // regex matching literal \ and literal .
boolean correct = Pattern.matches(regex, path); // true
~~~

This snippet uses `Pattern` once imported. Writing `"C:\temp\x.txt"` in Java source can introduce unintended escapes (like `\t`) or fail to compile due to invalid escapes. When handling **textual file paths**, consider `Path`/`Files` instead of regex if the goal is file operations; path separators depend on OS context and data source.

## 4. The Dollar Sign: End Anchor `$` or Currency Symbol `\$`?

In a **regex pattern**, `$` is a **position anchor**, consuming no characters. For example:

~~~java
Pattern.matches("^AB\\d{2}$", "AB12");  // true
Pattern.matches("^AB\\d{2}$", "xAB12"); // false
~~~

`^` anchors the start and `$` anchors the end per Java regex rules. `matches()` already requires the **entire string** to match; in this case, the anchors clarify intent for readers though they are not strictly required. By contrast, when using `find()`, `^`/`$` change which substring positions can match.

To match a **literal `$`** currency symbol, write regex `\$` and Java literal `"\\$"`:

~~~java
Pattern.matches("total=\\$\\d+", "total=$25"); // true
~~~

The regex here is `total=\$\d+`: match `total=`, a literal `$`, then one or more digits. Omitting the backslash before `$` completely changes the meaning.

**Watch out for trailing newlines:** `$` can match just before a trailing line terminator; with `Pattern.MULTILINE`, it also matches at the end of each line. `\z` denotes the **absolute end of input** when strict positioning is needed in a regex; `\z` must be written `"\\z"` in Java. `Pattern.matches(...)` and `Matcher.matches()` remain the clearest way to validate the **whole** input.

### Testing `MULTILINE`

~~~java
Pattern p = Pattern.compile("^cat$", Pattern.MULTILINE);
boolean foundLine = p.matcher("cat\nbird").find();    // true
boolean wholeText = p.matcher("cat\nbird").matches(); // false
~~~

`find()` matches the `cat` line alone because `^`/`$` are evaluated per line. `matches()` refuses to ignore the remaining `\nbird`.

## 5. Capturing and Non-Capturing Groups: `(...)`, `(?:...)`, and `(?<name>...)`

Parentheses serve two main roles:

1. **Grouping subpatterns** so quantifiers or alternation `|` apply to the whole group, e.g., `(ab)+` vs. `ab+`.
2. **Capturing the matched slice** to retrieve it via `Matcher.group(...)` or reference it in a replacement string.

By default, capturing groups are numbered **1, 2, ...** in left-to-right order of their opening `(`. Group `0` is the **entire match**. `(?:...)` only groups, **without incrementing the group counter**. A named group `(?<ext>txt|csv)` both captures and can be retrieved by `"ext"`.

Simple file example:

~~~java
Pattern pattern = Pattern.compile(
        "^(?<base>[a-z]+)\\.(?<ext>txt|csv)$");
Matcher m = pattern.matcher("notes.txt");

if (m.matches()) {
    System.out.println(m.group(0));      // notes.txt
    System.out.println(m.group("base")); // notes
    System.out.println(m.group("ext"));  // txt
}
~~~

This is an illustrative snippet (requiring `Pattern`/`Matcher` imports). Note that `m.group("base")` is an API call using the **group name declared in the regex**. `(?<base>[a-z]+)` uses parentheses to capture `notes`, while `\\.` in Java matches the dot before the extension.

**Only call `group()`, `start()`, or `end()` after `find()` or `matches()` succeeds.** Without a current match, `Matcher` throws `IllegalStateException`. For an optional group that did not participate, `group(n)` can be `null` and `start(n)`/`end(n)` are `-1`. `start/end` indices are **UTF-16 indices**, and `end` is exclusive.

When you only need grouping without extraction, use a non-capturing group such as `(?:txt|csv)`. This reduces the risk of accidentally shifting `group(1)` numbering when editing the regex:

~~~java
Pattern noCapture = Pattern.compile("^[a-z]+\\.(?:txt|csv)$");
boolean okay = noCapture.matcher("notes.txt").matches(); // true
~~~

## 6. Group Names and Dollar Signs in Replacements: Different Rules from Regex

One of the most common traps: inside a **regex pattern**, `$` is an **anchor**; inside a **replacement string** of `Matcher.replaceAll`, `$1` or `${name}` means **insert the captured group's text**.

| Context | Syntax | Meaning |
| --- | --- | --- |
| Regex | `$` | End anchor |
| Regex | `\$` | Literal dollar sign |
| Regex | `(abc)` | Capture content into group 1 |
| Regex | `(?<name>abc)` | Capture named group `name` |
| Replacement in `Matcher`/`String.replaceAll` | `$1` | Insert group 1's content into output |
| Replacement | `${name}` | Insert named group's content into output |
| Replacement | `\$` | Escape a literal `$` in a **replacement string**, not an anchor |
| Replacement | `Matcher.quoteReplacement(text)` | Treat `text` literally, including `$` and `\` |

Example:

~~~java
String result = Pattern.compile("id=(\\d+)")
        .matcher("id=42; id=7")
        .replaceAll("item[$1]");
// item[42]; item[7]
~~~

The pattern `(\\d+)` (in a Java literal) captures a digit sequence as group 1. The replacement `"item[$1]"` inserts that group's content. **`$1` has special meaning only in replacements**, not as a backreference inside a regex pattern. To backreference a group inside a regex pattern, use `\1` (Java literal `"\\1"`) or `\k<name>` (Java literal `"\\k<name>"`).

With named groups:

~~~java
String reordered = Pattern.compile("(?<word>[a-z]+)-(?<num>\\d+)")
        .matcher("abc-12")
        .replaceAll("${num}:${word}");
// 12:abc
~~~

**If replacement data comes from users**, passing `"$9\\temp"` straight into `replaceAll` can cause the regex engine to reference a nonexistent group or treat `\` as an escape. Use `Matcher.quoteReplacement(...)`:

~~~java
String rawReplacement = "$9\\temp";
String safe = Pattern.compile("TOKEN")
        .matcher("path=TOKEN")
        .replaceAll(Matcher.quoteReplacement(rawReplacement));
// path=$9\temp
~~~

In Java, `String.replace(old, new)` replaces **literal** substrings; `String.replaceAll(regex, replacement)` uses **regex** and replacement syntax. If you only want to replace dots with dashes, `text.replace(".", "-")` is simpler than `text.replaceAll("\\.", "-")`.

## 7. Java 17 Program: Testing Dots, Slashes, and Dollar Signs

The following program intentionally includes both **cases to accept** and **cases to reject**, avoiding testing only happy-path inputs:

~~~java
// RegexSymbolsDemo.java
import java.util.regex.Pattern;

public class RegexSymbolsDemo {
    static void check(String name, String regex, String input) {
        System.out.println(name + " = " + Pattern.matches(regex, input));
    }

    public static void main(String[] args) {
        check("literal dot", "report\\.txt", "report.txt");
        check("reject fake dot", "report\\.txt", "reportXtxt");
        check("wildcard dot", "report.txt", "reportXtxt");
        check("slash path", "api/v\\d+/users", "api/v2/users");
        check("reject backslashes", "api/v\\d+/users", "api\\v2\\users");
        check("literal dollar", "total=\\$\\d+", "total=$25");
        check("end anchor", "^AB\\d{2}$", "AB12");
        check("reject prefix", "^AB\\d{2}$", "xAB12");
        check("dot not newline", "a.b", "a\nb");

        boolean dotAll = Pattern.compile("a.b", Pattern.DOTALL)
                .matcher("a\nb")
                .matches();
        System.out.println("dotall newline = " + dotAll);

        Pattern line = Pattern.compile("^cat$", Pattern.MULTILINE);
        System.out.println("multiline find = "
                + line.matcher("cat\nbird").find());
        System.out.println("multiline matches = "
                + line.matcher("cat\nbird").matches());
    }
}
~~~

Save as `RegexSymbolsDemo.java`, then run:

~~~bash
javac --release 17 RegexSymbolsDemo.java
java RegexSymbolsDemo
~~~

Stdout:

~~~text
literal dot = true
reject fake dot = false
wildcard dot = true
slash path = true
reject backslashes = false
literal dollar = true
end anchor = true
reject prefix = false
dot not newline = false
dotall newline = true
multiline find = true
multiline matches = false
~~~

**How to read the test:** `"wildcard dot = true"` is **correct according to regex semantics**, yet it represents **wrong behavior if business rules require a literal dot**. That is why regex tests need **negative cases** alongside positive ones. `"multiline find"` and `"multiline matches"` do not contradict each other: they ask two different questions about match scope.

## 8. Java 17 Program: Groups, Replacements, and Data Needing Escaping

~~~java
// RegexGroupsAndReplacementDemo.java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexGroupsAndReplacementDemo {
    public static void main(String[] args) {
        Pattern file = Pattern.compile(
                "^(?<base>[a-z]+)\\.(?<ext>txt|csv)$");
        Matcher m = file.matcher("notes.txt");

        System.out.println("matches = " + m.matches());
        System.out.println("full = " + m.group(0));
        System.out.println("base = " + m.group(1));
        System.out.println("extension = " + m.group("ext"));
        System.out.println("base range = "
                + m.start("base") + ".." + m.end("base"));

        String byNumber = Pattern.compile("id=(\\d+)")
                .matcher("id=42; id=7")
                .replaceAll("item[$1]");
        System.out.println("by number = " + byNumber);

        String byName = Pattern.compile(
                "(?<word>[a-z]+)-(?<num>\\d+)")
                .matcher("abc-12")
                .replaceAll("${num}:${word}");
        System.out.println("by name = " + byName);

        String literal = "$9\\temp";
        String safe = Pattern.compile("TOKEN")
                .matcher("path=TOKEN")
                .replaceAll(Matcher.quoteReplacement(literal));
        System.out.println("safe replacement = " + safe);
    }
}
~~~

Run command:

~~~bash
javac --release 17 RegexGroupsAndReplacementDemo.java
java RegexGroupsAndReplacementDemo
~~~

Stdout:

~~~text
matches = true
full = notes.txt
base = notes
extension = txt
base range = 0..5
by number = item[42]; item[7]
by name = 12:abc
safe replacement = path=$9\temp
~~~

In this program, `group(0)` returns the entire `notes.txt`, group `base` returns `notes`, and `ext` returns `txt`. `base range = 0..5` is a **start-inclusive, end-exclusive** range. The replacement test shows that to place `$`/backslash characters literally into output, `Matcher.quoteReplacement` bypasses group substitution rules.

## 9. Java 17 Program: Testing Dynamic Literal Strings and Backslashes

If a user-provided value only needs to be matched **literally** in data, use `Pattern.quote(...)`. Writing:

~~~java
Pattern.matches("v1.2/$", "v1.2/$");
~~~

does not guarantee literal matching, because `.` is a wildcard and `$` is an anchor (it does not match a literal dollar sign). Use `Pattern.quote` when the whole string must be treated as literal:

~~~java
// RegexLiteralInputDemo.java
import java.util.regex.Pattern;

public class RegexLiteralInputDemo {
    public static void main(String[] args) {
        String literal = "v1.2/$";
        String regex = "^" + Pattern.quote(literal) + "$";
        System.out.println("literal = "
                + Pattern.matches(regex, "v1.2/$"));

        String windows = "C:\\temp\\x.txt";
        String windowsRegex = "C:\\\\temp\\\\x\\.txt";
        System.out.println("windows = "
                + Pattern.matches(windowsRegex, windows));

        String price = "Cost: $25";
        String changed = Pattern.compile("\\$")
                .matcher(price)
                .replaceAll("USD ");
        System.out.println("changed = " + changed);

        String kept = Pattern.compile("\\$")
                .matcher(price)
                .replaceAll("\\$");
        System.out.println("kept = " + kept);
    }
}
~~~

Run command:

~~~bash
javac --release 17 RegexLiteralInputDemo.java
java RegexLiteralInputDemo
~~~

Stdout:

~~~text
literal = true
windows = true
changed = Cost: USD 25
kept = Cost: $25
~~~

`Pattern.quote` turns `v1.2/$` into a full literal search pattern for the quoted segment; the outer `^...$` expresses whole-string matching intent (even though `matches()` already enforces it). The Windows path example verifies escaping across **two layers**. The last two lines intentionally use `\\$` in the pattern to find a literal dollar sign, then apply **two different replacement policies**.

## 10. Designing Meaningful Regex Tests

Before accepting a regex, categorize tests by these questions:

| Test Type | Sample Input | What to Verify |
| --- | --- | --- |
| **Valid format** | `report.txt`, `api/v2/users` | Pattern accepts valid text |
| **Special characters with different meaning** | `reportXtxt`, `api\v2\users` | Dots/slashes are not misread |
| **Literal dollar vs. anchor** | `total=$25`, `total=25` | `\$` matches currency, `$` constrains position |
| **Prefixes/suffixes** | `xAB12`, `AB12x` | Whole-string vs. substring check |
| **Line breaks** | `a\nb`, `cat\nbird` | DOTALL/MULTILINE behavior matches requirements |
| **Capturing groups** | `notes.txt`, `notes.exe` | `matches()` and `group(...)` return exact content |
| **Optional groups** | With and without optional part | Handle `null`, avoid using wrong group |
| **Untrusted replacement** | Strings containing `$` and `\` | No unintended group substitution or exceptions |
| **Unicode, empty/long input** | Accented names, empty string, very long string | Matches per spec without assuming ASCII or running too slowly |

A few practical guidelines:

1. **State expectations clearly:** a test named `shouldRejectWrongExtensionSeparator` beats a vague `testRegex`.
2. **Use `matches()` for full-string formats and `find()` for extraction**; if testing both, name the outcomes clearly.
3. **Avoid claiming a string “matches” just because `find()` returns true** when business rules require every character to be valid.
4. **Verify group opening/closing pairs** and numbering; changing `(...)` to `(?:...)` can shift group numbers.
5. **Test both regex and replacement:** a valid match can still emit wrong output if `$1`, `${name}`, or backslashes in the replacement are interpreted unexpectedly.
6. **Never concatenate untrusted input directly into a regex** if you only want a literal search. Use `Pattern.quote`, enforce length/complexity limits, and watch for catastrophic backtracking on loose patterns.
7. **Use real data and regression tests** after modifying patterns: a short regex does not mean it is predictable in every edge case.

### JUnit 5 Testing Illustration

If a project already uses JUnit 5, assertions can be written concisely as follows. **These are test methods inside a project test class**, not a standalone Java program; JUnit 5 dependencies and imports are required.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.regex.Pattern;

class RegexSymbolsTest {
    @Test
    void literalDotMustNotAcceptOtherSeparators() {
        String regex = "file\\.txt";
        assertTrue(Pattern.matches(regex, "file.txt"));
        assertFalse(Pattern.matches(regex, "fileXtxt"));
    }

    @Test
    void slashAndDollarAreDifferentFromRegexAnchors() {
        assertTrue(Pattern.matches("api/v\\d+", "api/v2"));
        assertTrue(Pattern.matches("price=\\$\\d+", "price=$12"));
        assertFalse(Pattern.matches("price=\\$\\d+", "price=12"));
    }

    @Test
    void namedGroupCapturesCorrectExtension() {
        var matcher = Pattern.compile(
                "^(?<stem>[a-z]+)\\.(?<ext>txt|csv)$")
                .matcher("notes.csv");
        assertTrue(matcher.matches());
        assertEquals("notes", matcher.group("stem"));
        assertEquals("csv", matcher.group("ext"));
    }
}
~~~

Tests are easier to read when **each assertion checks one specific trait**. Avoid suites containing only valid examples, as the wildcard `.` easily lets near-matches slip through.

## 11. Common Mistakes to Avoid

- **Writing `"\\. "` instead of `"\\."`** (extra space) or `"."` (wildcard dot) when trying to match a literal dot. The Java string must produce the exact intended regex.
- **Confusing JavaScript's `/regex/` syntax with Java `Pattern`:** in Java, those two slashes become part of the pattern content; they are not delimiters.
- **Confusing forward slash and backslash:** `/` is normally literal; `\` starts a regex escape and must itself be escaped in Java strings.
- **Using `$` to represent currency dollars:** inside a pattern, `$` is an anchor; for a literal sign use `\$`, written `"\\$"` in a Java literal.
- **Using `"$1"` inside a pattern expecting a group backreference:** `$1` is **replacement** syntax, not a regex backreference. Inside a pattern, numbered backreferences use `\1` (Java `"\\1"`).
- **Passing replacement data with `$`/`\` directly:** `replaceAll` interprets group/escape syntax; use `Matcher.quoteReplacement` for literals.
- **Calling `group(1)` before a match exists:** throws `IllegalStateException`; check `matches()` or `find()` first.
- **Accidentally adding capturing groups:** shifting group numbers changes what `$1`/`group(1)` refers to. Use `(?:...)` for grouping only.
- **Forgetting to test line breaks:** DOTALL and MULTILINE are separate flags; do not extrapolate from single-line inputs.
- **Assuming correctness from a single `true` result:** tests need near-miss invalid strings, punctuation strings, newlines, optional groups, and replacement data.
- **Parsing complex grammars with regex alone:** paths, URLs, JSON, and HTML have dedicated syntax rules; when full structural parsing is needed, choose a dedicated parser or API.

## 12. Practice Exercises

**Exercise 1.** Why does regex `a.b` accept `a/b` under `matches()`? Write a Java regex that accepts only `a.b`.

**Answer:** `.` is a wildcard, matching even a slash. Use `Pattern.matches("a\\.b", "a.b")`.

**Exercise 2.** Write a Java regex validating a full string of the form `/user/123` (exact two forward slashes, the letters `user`, and three digits).

**Answer:** `Pattern.matches("/user/\\d{3}", "/user/123")`. Forward slashes are not special escape characters.

**Exercise 3.** Given the Java regex `"^\\$\\d+$"`, does `"$15"` match? Does `"15$"` match?

**Answer:** `"$15"` matches; `"15$"` does not. The regex requires a dollar sign at the **start** of the string, followed by one or more digits to the end.

**Exercise 4.** Given the regex pattern `(?<first>[a-z]+)-(?<second>\d+)` (Java literal needs `\\d`), what replacement turns `"abc-42"` into `"42:abc"`?

**Answer:** `"${second}:${first}"`. Named group references in replacements follow `$` enclosed in `{...}`.

**Exercise 5.** A user-supplied replacement string is `"$2\folder"`. Why should you not pass it straight to `Matcher.replaceAll(...)`?

**Answer:** `$2` can be interpreted as a reference to group 2 and `\` has escape semantics in replacements. Use `Matcher.quoteReplacement(userReplacement)` to insert it literally.

**Exercise 6.** Why can the pattern `"report\\.txt"` still return true via `find()` on `"backup_report.txt.old"`?

**Answer:** `find()` locates a **substring** `report.txt` inside the longer string. When validating an **entire filename**, use `matches()` or appropriate anchors in the pattern.

## Takeaway

- **`.` in regex**: wildcard; **`\.`**: literal dot; Java literal for the latter is `"\\."`.
- **`/` in Java regex**: ordinary character, not a pattern delimiter. **`\`**: escape character in both regex and Java source.
- **`$` in regex**: end anchor; **`\$`**: literal dollar sign. **`$1` or `${name}` in replacement**: captured group content.
- **`(...)`**: capturing group; **`(?:...)`**: non-capturing group; **`(?<name>...)`**: named group.
- **Practical testing**: combine valid/invalid inputs, `matches()`/`find()`, line breaks, special replacements, and punctuation-heavy strings.

For full reference, see the [Java 17 Pattern API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html) and [Java 17 Matcher API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html).
