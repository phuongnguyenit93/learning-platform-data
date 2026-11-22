# Testing `trim`, `strip`, NBSP, and Line Endings in Java

## 1. Problem: “Whitespace” Has No Single Definition

In Java applications, data received from forms, CSVs, files, APIs, the clipboard, or multilingual text can contain many characters that look like whitespace. Two strings that appear nearly identical on screen can still differ in Unicode values and in how `trim()`, `strip()`, or line splitting behaves.

Three concepts to distinguish:

- **Whitespace per `String.trim()`:** `char` values at **both ends** no greater than `U+0020`. This is a historical rule, not full Unicode whitespace.
- **Whitespace per `String.strip()`:** code points at **both ends** considered whitespace by `Character.isWhitespace(int)`. This broader rule covers many Unicode characters, yet **deliberately excludes** three non-breaking spaces: NBSP (`U+00A0`), FIGURE SPACE (`U+2007`), and NARROW NO-BREAK SPACE (`U+202F`).
- **Line terminators:** depending on the API, may be LF, CR, CRLF, or Unicode line breaks such as NEL, LINE SEPARATOR, and PARAGRAPH SEPARATOR. Stripping leading/trailing whitespace and *splitting lines* are two separate problems.

When testing, clarify whether you want to **strip edge whitespace**, **split into lines**, or **normalize line-ending characters**. Never treat these three tasks as equivalent.

## 2. `trim()` and `strip()`: Mechanics and Examples

`String.trim()` dates back to older Java releases; it returns a string with leading and trailing sequences of `char` values `<= U+0020` removed. Characters in the middle of the string are untouched. Because the criterion uses raw `char` codes, `trim()` can remove certain control characters that users would not necessarily call spaces.

`String.strip()` (Java 11+) removes leading and trailing code points satisfying `Character.isWhitespace(int)`. This is usually a better choice for Unicode text, yet it **does not** mean “remove every visually blank character.”

| Leading/trailing character | Code | `trim()` | `strip()` | Explanation |
| --- | --- | --- | --- | --- |
| Regular SPACE | `U+0020` | Removes | Removes | Recognized by both. |
| TAB, LF, CR | `U+0009`, `U+000A`, `U+000D` | Removes | Removes | Control characters in both sets. |
| EM SPACE | `U+2003` | Keeps | Removes | `Character.isWhitespace` returns `true`. |
| IDEOGRAPHIC SPACE | `U+3000` | Keeps | Removes | A non-ASCII example removed by `strip`. |
| NBSP (NO-BREAK SPACE) | `U+00A0` | Keeps | **Keeps** | `Character.isWhitespace` returns `false`. |
| FIGURE SPACE | `U+2007` | Keeps | **Keeps** | Non-breaking space per API. |
| NARROW NO-BREAK SPACE | `U+202F` | Keeps | **Keeps** | Non-breaking space per API. |
| LINE SEPARATOR | `U+2028` | Keeps | Removes | Whitespace per `Character.isWhitespace`, yet not a delimiter for `String.lines()`. |
| NEL (NEXT LINE) | `U+0085` | Keeps | Keeps | Recognized as a line break by regex `\R`, not in `strip`'s Java whitespace definition. |

**Common point of confusion:** `Character.isSpaceChar(codePoint)` and `Character.isWhitespace(codePoint)` are **different** checks. NBSP, FIGURE SPACE, and NARROW NO-BREAK SPACE are recognized by `isSpaceChar` yet intentionally excluded from `isWhitespace`. Since `strip` relies on `isWhitespace`, it does not remove them.

Other helpful APIs (Java 11+):

- `stripLeading()`: removes whitespace per `Character.isWhitespace` at the **start** only.
- `stripTrailing()`: removes it at the **end** only.
- `isBlank()`: returns `true` if the string is empty or all code points are Java whitespace. For example, a string containing only NBSP is **not** considered blank by `isBlank()`.
- `String.stripIndent()` / text blocks address indentation in other contexts; they do not replace defining which characters to sanitize in input data.

For business data, if the specification requires stripping **NBSP as well** at both ends, write an explicit rule and test it separately. Do not silently change the application-wide definition of “blank” just because one UI renders NBSP like SPACE.

## 3. Line Breaks: LF, CR, CRLF, and Unicode

Lines of text do not necessarily use the same terminating character sequence:

| Name | Java representation / Unicode code | Common occurrence |
| --- | --- | --- |
| LF (Line Feed) | `"\n"` / `U+000A` | Unix/Linux files, many APIs, Git |
| CR (Carriage Return) | `"\r"` / `U+000D` | Legacy data, some communication sources |
| CRLF | `"\r\n"` / `U+000D U+000A` | Many Windows files/formats and protocols |
| VT (Vertical Tab) | `U+000B` | Control data / special formats |
| FF (Form Feed) | `"\f"` / `U+000C` | Page breaks or legacy data |
| NEL (Next Line) | `U+0085` | Some Unicode / legacy sources |
| LINE SEPARATOR | `U+2028` | Unicode line separator |
| PARAGRAPH SEPARATOR | `U+2029` | Unicode paragraph separator |

**API distinctions:**

- `String.lines()` (Java 11+) splits **only** on LF, CR, and CRLF. `"\r\n"` is **one** line terminator. Returned lines do not include the line terminator.
- `String.lines()` **does not** split on `U+0085`, `U+2028`, or `U+2029`. Nor does it produce an extra empty line after a trailing line terminator; an empty string yields **zero lines**.
- In `java.util.regex.Pattern`, `\R` matches any line-break sequence: `\r\n` or any character in LF, VT, FF, CR, NEL, LS, PS. In a **Java string literal**, write `"\\R"` to pass the regex token `\R`.
- `text.split("\\R", -1)` splits on Unicode line breaks and **keeps trailing empty elements** thanks to the negative limit `-1`. Using the `split("\\R")` overload (limit = 0) discards trailing empty elements.
- `text.replaceAll("\\R", "\n")` normalizes regex-recognized line-ending sequences to LF. Do not apply it indiscriminately to binary data, digitally signed strings, or formats where original line endings carry specific meaning.

**Special note:** `\s`, `\h`, `\v`, `\R`, and `Character.isWhitespace` each have their own definitions; using `split("\\s+")` to handle line breaks or NBSP without checking regex flags can yield unexpected results. `\R` represents an **entire line-ending sequence**, treating CRLF as a single unit, making it a clear choice when splitting across multiple line-ending styles.

## 4. Standalone Java 17+ Test Program

Create **`StringWhitespaceChecks.java`**, saving source code as UTF-8. The program uses concrete comparisons rather than relying on visual inspection; `cp(int)` builds characters from code points so NBSP and hidden line separators are not altered by an editor.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class StringWhitespaceChecks {
    private static int passed;

    private static void check(String name, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + " | expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    private static String cp(int value) {
        return new String(Character.toChars(value));
    }

    public static void main(String[] args) {
        String em = cp(0x2003);
        String nbsp = cp(0x00A0);
        String figure = cp(0x2007);
        String narrow = cp(0x202F);
        String ls = cp(0x2028);
        String ps = cp(0x2029);
        String nel = cp(0x0085);

        // Test trim/strip at both ends.
        String ascii = " \tA\r\n ";
        check("trim ASCII", "A", ascii.trim());
        check("strip ASCII", "A", ascii.strip());

        String emWrapped = em + "A" + em;
        check("trim keeps EM SPACE", emWrapped, emWrapped.trim());
        check("strip removes EM SPACE", "A", emWrapped.strip());

        String nbspWrapped = nbsp + "A" + nbsp;
        check("trim keeps NBSP", nbspWrapped, nbspWrapped.trim());
        check("strip keeps NBSP", nbspWrapped, nbspWrapped.strip());

        String figureWrapped = figure + "A" + figure;
        String narrowWrapped = narrow + "A" + narrow;
        check("strip keeps FIGURE SPACE", figureWrapped, figureWrapped.strip());
        check("strip keeps NARROW NBSP", narrowWrapped, narrowWrapped.strip());

        check("NBSP isWhitespace", false, Character.isWhitespace(0x00A0));
        check("NBSP isSpaceChar", true, Character.isSpaceChar(0x00A0));
        check("FIGURE SPACE isWhitespace",
                false, Character.isWhitespace(0x2007));
        check("NARROW NBSP isWhitespace",
                false, Character.isWhitespace(0x202F));
        check("EM SPACE isWhitespace", true, Character.isWhitespace(0x2003));

        check("stripLeading", "A" + em, emWrapped.stripLeading());
        check("stripTrailing", em + "A", emWrapped.stripTrailing());
        check("trim does not change internal whitespace",
                "A \t B", (" A \t B ").trim());

        // Test line-ending styles.
        String crLfOnly = "a\r\nb\nc\rd";
        check("String.lines CRLF LF CR",
                List.of("a", "b", "c", "d"),
                crLfOnly.lines().toList());

        String unicodeLineBreaks = "a" + ls + "b" + ps + "c" + nel + "d";
        check("lines keeps Unicode separators",
                List.of(unicodeLineBreaks),
                unicodeLineBreaks.lines().toList());
        check("regex R splits Unicode separators",
                List.of("a", "b", "c", "d"),
                Arrays.asList(unicodeLineBreaks.split("\\R", -1)));

        String mixed = "A\r\nB\nC\rD" + ls + "E" + nel + "F" + ps + "G";
        check("regex R splits mixed line endings",
                List.of("A", "B", "C", "D", "E", "F", "G"),
                Arrays.asList(mixed.split("\\R", -1)));
        check("split negative limit keeps trailing empty",
                List.of("x", ""),
                Arrays.asList("x\n".split("\\R", -1)));
        check("String.lines does not add trailing empty",
                List.of("x"), "x\n".lines().toList());
        check("String.lines keeps actual blank line",
                List.of("a", "", "b"), "a\n\nb".lines().toList());
        check("empty string has no lines",
                List.of(), "".lines().toList());

        String lsWrapped = ls + "A" + ls;
        check("trim keeps LINE SEPARATOR", lsWrapped, lsWrapped.trim());
        check("strip removes LINE SEPARATOR", "A", lsWrapped.strip());

        check("normalize all recognized line endings",
                "A\nB\nC\nD\nE\nF\nG",
                mixed.replaceAll("\\R", "\n"));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringWhitespaceChecks.java
java StringWhitespaceChecks
```

**Stdout when all tests pass** on Java 17+:

```text
PASS: 27 checks
```

If behavior differs from expectations, `check` throws `AssertionError` with the name of the first failing test and halts before printing the `PASS` line. Values like NBSP, LS, and NEL are built from code points so tests do not depend on whether the terminal can render them.

### Takeaways from the Test Suite

- Edge SPACE and TAB are removed by both `trim` and `strip`; EM SPACE is removed only by `strip`.
- NBSP and the two other non-breaking variants are removed by neither `trim` nor `strip`. `isSpaceChar` can be `true` while `isWhitespace` is `false`.
- `String.lines()` handles CR/LF/CRLF; `"\\R"` additionally handles Unicode line breaks.
- An empty line **between** terminators can be meaningful data; an empty element **after** a final terminator is handled differently by `String.lines()` versus `split` with limit `-1`.
- Line-ending normalization should be an intentional step, separate from stripping edge whitespace.

## 5. Matrix-Based Test Design Instead of Only Regular Spaces

Do not only test `" text ".trim()` and assume all data is safe. Cover at least these dimensions:

| Test Axis | Required Cases | What to Verify |
| --- | --- | --- |
| Position | Start, end, both ends, middle of string | Only targeted positions are altered. |
| Length | Empty string, whitespace-only, multiple consecutive characters | No data lost outside scope. |
| ASCII whitespace | SPACE, TAB, LF, CR, CRLF | `trim`/`strip` handle start/end properly. |
| Unicode whitespace | EM SPACE, IDEOGRAPHIC SPACE, LINE SEPARATOR | Distinguish `trim` and `strip`. |
| Non-breaking | NBSP, FIGURE SPACE, NARROW NBSP | Characters preserved per contract. |
| Line-ending style | LF, CR, CRLF, NEL, LS, PS | Right choice between `lines` and regex `\R`. |
| Empty lines | Two adjacent terminators, start of string, end of string | No dropped/added lines from misunderstanding `split`/`lines`. |
| Unicode data | Vietnamese text, emojis, combining characters | Internal content not accidentally stripped/modified. |

With JUnit 5, you can convert the `check` calls into `@ParameterizedTest` or `@MethodSource` cases, use `assertEquals(expected, actual)`, and include code points (such as `U+00A0`) in test names. That is the path to extend the suite; the program above runs standalone on JDK 17+ with **no extra dependencies**.

Some tests need to run across multiple environments, especially when reading from files or HTTP. Still, once a `String` already holds the right code points, `trim`, `strip`, and `lines` rules must follow API contracts rather than arbitrarily depending on the OS line separator.

## 6. Reading Files or Receiving External Data

A Windows file typically uses CRLF and a Unix file typically uses LF, yet not every file follows the runtime environment's convention. Do not use `System.lineSeparator()` to guess the delimiter of an arbitrary file. `System.lineSeparator()` reports the **current platform's default** line separator, mainly useful when **generating** text for that platform; it does not auto-detect the line-ending style of source data.

**Illustrative** normalization example (placed inside a method that already has `text`):

```java
String normalized = text.replaceAll("\\R", "\n");
List<String> lines = Arrays.asList(normalized.split("\n", -1));
```

This snippet uses `java.util.Arrays` and `java.util.List`. `-1` preserves a trailing empty element if the text ends with LF. Choose this when business data needs to retain information about a trailing line terminator; otherwise choose another policy and write corresponding tests.

When cleaning the start/end of individual fields:

```java
String cleaned = field.strip();  // NBSP is still preserved
```

This is a **Java-whitespace rule**, not a universal filter for every space-like character. If product requirements state “NBSP must also be stripped,” write a helper with a published predicate:

```java
// Illustrative snippet: use inside a class and pass a valid String.
static boolean isBoundarySpace(int cp) {
    return Character.isWhitespace(cp)
            || cp == 0x00A0
            || cp == 0x2007
            || cp == 0x202F;
}

static String stripIncludingNbsp(String value) {
    int start = 0;
    int end = value.length();
    while (start < end) {
        int cp = value.codePointAt(start);
        if (!isBoundarySpace(cp)) break;
        start += Character.charCount(cp);
    }
    while (start < end) {
        int cp = value.codePointBefore(end);
        if (!isBoundarySpace(cp)) break;
        end -= Character.charCount(cp);
    }
    return value.substring(start, end);
}
```

This illustrative code works by **code point**, so it never splits a surrogate pair. It strips only at both ends, preserving internal content. Stripping NBSP is an application choice and needs dedicated tests; never attribute it to `String.strip()`'s default behavior.

If data was decoded with the wrong charset before becoming a `String`, neither `strip` nor `trim` can fix mojibake. Know the real encoding of the file/protocol (typically UTF-8 when you define it), decode properly, and only then process whitespace.

## 7. Common Bugs to Catch Early

**Bug 1 — assuming `strip()` removes NBSP.** Text copied from websites or documents can contain leading/trailing `U+00A0`; `strip()` returns the string with NBSP intact. Inspect actual code points instead of eyeballing whitespace on screen.

**Bug 2 — using `trim()` instead of `strip()` for Unicode whitespace.** `trim()` keeps `U+2003` and `U+3000`. If inputs require handling those spaces, `strip()` is usually more appropriate.

**Bug 3 — using `String.lines()` to split all Unicode line breaks.** `lines()` only recognizes LF/CR/CRLF. Use `split("\\R", -1)` or a dedicated parser if the spec requires NEL, LS, or PS.

**Bug 4 — thinking CRLF counts as two blank lines.** Both `String.lines()` and regex `\R` treat CRLF as **one** terminator, so `"A\r\nB"` has two lines `A` and `B`.

**Bug 5 — forgetting `-1` in `split`.** `"A\n".split("\\R")` drops the trailing empty element, whereas `split("\\R", -1)` keeps it. Decide the expected output before writing tests.

**Bug 6 — stripping all whitespace without checking semantics.** In names, addresses, legal text, formatted numbers, or structured data, NBSP and blank lines may carry presentation meaning. Automatically replacing all whitespace with SPACE can alter data that must be preserved.

**Bug 7 — verifying via console output.** U+00A0, U+2003, LF, and CR are hard to tell apart when printed directly. Use `U+XXXX` notation or assert `codePointAt`/`equals`; never judge by visual appearance alone.

**Bug 8 — depending on platform defaults when generating test data.** Writing `"\n"`/`"\r\n"` literals or building code points makes tests deterministic. Avoid generating reference data with `System.lineSeparator()` when the goal is comparing line endings across operating systems.

## 8. Production Readiness Checklist

1. Clarify the policy: `trim`-style whitespace removal, `strip`-style, or also NBSP/custom characters.
2. List supported code points, especially `U+00A0`, `U+2007`, `U+202F`, `U+2003`, `U+0085`, `U+2028`, `U+2029`.
3. Choose the line-splitting API per requirements: `lines()` for CR/LF/CRLF; `"\\R"` when broader Unicode line breaks are needed.
4. Decide whether to keep or drop trailing empty lines; if using `split`, specify the limit explicitly.
5. Test data at the start, middle, and end of strings, including empty strings and consecutive delimiters.
6. When normalizing, replace only intended characters and keep originals if raw data matters.

## Official Documentation

- [Java 17 `String.trim`, `strip`, `lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java 17 `Character.isWhitespace` and `Character.isSpaceChar`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).
- [Java 17 `Pattern`: `\R`, line terminators, and `split`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).
