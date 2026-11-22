# Distinguishing Content, Index, Regex, and Encoding Errors in Java String Handling

A string-related bug does not necessarily mean “Java mishandled characters.” The same symptom—*unexpected output*—can stem from **different actual content**, **out-of-bounds indexing**, **regular expression (regex) syntax**, or **byte-and-charset transcoding**. Troubleshooting must start by identifying the error category; a misdiagnosis can produce a patch that hides symptoms while still corrupting data.

This lesson focuses on `String` in Java 17+: identifying symptoms, common exceptions, minimal reproduction, verification steps, and proper fixes across the four categories **content – index – regex – encoding**. Examples clearly separate illustrative snippets from a standalone Java program with deterministic output.

## 1. Quick Diagnostic Map

| Error Category | Question to Ask | Typical Symptoms | How to Inspect |
| --- | --- | --- | --- |
| **Content** | Do the two strings **actually hold the same data**? | `equals` returns `false`; invisible whitespace/Unicode marks; `==` misapplied to content; differing normalization or case | Print strings inside delimiters, inspect `length`, code points, compare with `equals`, examine Unicode |
| **Index** | Is the position or slice **within valid bounds**? | `StringIndexOutOfBoundsException`, off-by-one errors, slicing mid-surrogate | Print `length`, `begin`/`end`, confirm indices count UTF-16 code units |
| **Regex** | Is the pattern being interpreted as **regex syntax**? | `PatternSyntaxException`; `split` produces too many parts; `replaceAll` replaces unintended text; `$`/`\` issues in replacement | Separate string literals, regex patterns, and replacements; use `Pattern.quote` / `Matcher.quoteReplacement` when needed |
| **Encoding** | Were bytes **encoded and decoded with the same charset**? | Characters turn into `�`, `?`, or mojibake (e.g., `Ã©`); round-trip fails; malformed bytes | Print hex of `byte[]`, log `Charset` explicitly, use encoder/decoder in `REPORT` mode |

**Inspection priority:** determine actual inputs and outputs; if an exception occurs, read **the exception type and stack location** before changing code. Seeing `?` or `�` does not automatically tell you whether the sender or receiver caused it: data might already have been replaced in an earlier stage.

## 2. Identifying Each Kind with a Minimal Reproducible Case

When no exception is thrown yet the result is wrong, first **compare actual content and confirm which API is used**. Below are four scenarios with distinct outcomes even though all involve `String`:

~~~java
// Content: two distinct objects with the same text.
String a = "OK";
String b = new String("OK");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true

// Index: endIndex exceeds length() = 3.
// "abc".substring(2, 4); // IndexOutOfBoundsException

// Regex: dot is a wildcard; use replace for literal replacement.
System.out.println("a.b".replaceAll(".", "X")); // XXX
System.out.println("a.b".replace(".", "_"));    // a_b

// Encoding: sender uses UTF-8, reader uses a different charset.
byte[] bytes = "é".getBytes(java.nio.charset.StandardCharsets.UTF_8);
String wrong = new String(bytes, java.nio.charset.StandardCharsets.ISO_8859_1);
System.out.println("é".equals(wrong)); // false
~~~

- For **content**, check `equals`, `length`, code points, and invisible characters; `"e\u0301"` and `"\u00E9"` can look identical to the eye yet differ as strings—normalize Unicode only when the contract requires it.
- For **index**, verify `0 <= begin <= end <= length()` before `substring(begin,end)`. `charAt(index)` requires `index < length()`; indices are UTF-16, so avoid cutting inside a surrogate pair when preserving code points.
- For **regex**, distinguish `Pattern.compile`/`replaceAll`/`split` from literal replacement `replace`. `Pattern.quote` protects literal text in patterns; `Matcher.quoteReplacement` protects literal text in replacements, especially when `$` or backslashes appear.
- For **encoding**, inspect raw bytes in hex, charsets at both ends, and error-handling policies. `new String(bytes, UTF_8)` can replace malformed bytes with `U+FFFD`; if invalid bytes must be rejected, use `CharsetDecoder` configured with `CodingErrorAction.REPORT`. When characters cannot be represented in the target charset, use a `REPORT` encoder.

Dedicated tests for each category in earlier lessons cover deeper boundary matrices. This lesson uses observed results to **decide which layer to inspect next**, avoiding fixing content bugs by swallowing exceptions or guessing charsets.

## 3. Java 17+ Program Distinguishing the Four Error Categories

Save the code below as `StringErrorKindsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;
import java.util.stream.Collectors;

public class StringErrorKindsDemo {
    public static void main(String[] args) {
        // 1. Content: reference comparison and Unicode normalization.
        String same = new String("java");
        System.out.println("== same content: " + (same == "java"));
        System.out.println("equals: " + same.equals("java"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicode equals: "
                + composed.equals(decomposed));
        System.out.println("unicode NFC equals: "
                + composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        // 2. Index: exception and UTF-16 code units.
        try {
            "abc".substring(2, 4);
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("index error: "
                    + e.getClass().getSimpleName());
        }

        String emoji = "A\uD83D\uDE00";
        System.out.println("UTF-16 units: " + emoji.length());
        System.out.println("code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("high surrogate: "
                + Character.isHighSurrogate(emoji.charAt(1)));

        // 3. Regex: dot has special meaning.
        String dotted = "a.b";
        System.out.println("regex dot: "
                + dotted.replaceAll(".", "X"));
        System.out.println("literal dot: "
                + dotted.replace(".", "_"));
        System.out.println("quoted regex: "
                + Pattern.compile(Pattern.quote("."))
                        .matcher(dotted).replaceAll("_"));

        try {
            Pattern.compile("[");
        } catch (PatternSyntaxException e) {
            System.out.println("invalid regex: "
                    + e.getClass().getSimpleName());
        }

        // 4. Encoding: wrong charset, data loss, and strict decoder.
        byte[] utf8 = "\u00E9".getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8 hex: "
                + HexFormat.of().formatHex(utf8));
        System.out.println("wrong decode equal: "
                + "\u00E9".equals(new String(
                        utf8, StandardCharsets.ISO_8859_1)));

        byte[] latin = "\u20AC".getBytes(
                StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 replacement hex: "
                + HexFormat.of().formatHex(latin));
        System.out.println("round trip euro: "
                + "\u20AC".equals(new String(
                        latin, StandardCharsets.ISO_8859_1)));

        try {
            StandardCharsets.ISO_8859_1.newEncoder()
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("\u20AC"));
        } catch (CharacterCodingException e) {
            System.out.println("strict encode: "
                    + e.getClass().getSimpleName());
        }

        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
        String lossy = new String(
                invalidUtf8, StandardCharsets.UTF_8);
        String codePoints = lossy.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
        System.out.println("lossy decode code points: " + codePoints);

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));
        } catch (CharacterCodingException e) {
            System.out.println("strict decode: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 StringErrorKindsDemo.java
java StringErrorKindsDemo
```

Deterministic output of the program:

```text
== same content: false
equals: true
unicode equals: false
unicode NFC equals: true
index error: StringIndexOutOfBoundsException
UTF-16 units: 3
code points: 2
high surrogate: true
regex dot: XXX
literal dot: a_b
quoted regex: a_b
invalid regex: PatternSyntaxException
utf8 hex: c3a9
wrong decode equal: false
Latin-1 replacement hex: 3f
round trip euro: false
strict encode: UnmappableCharacterException
lossy decode code points: U+FFFD U+0028
strict decode: MalformedInputException
```

Verified cases:

- **Content:** same text `java` yet distinct references; composed/decomposed Unicode forms are unequal until normalized to NFC.
- **Index:** `substring(2, 4)` exceeds length `3` and throws `StringIndexOutOfBoundsException`; the emoji takes two code units yet one code point.
- **Regex:** `.` matches all three characters, while `replace` or `Pattern.quote` preserves literal dot semantics; pattern `[` is syntactically invalid.
- **Encoding:** `é` encodes to `c3a9` in UTF-8; mis-decoding as Latin-1 fails to preserve the string; the euro sign is replaced when encoding to ISO-8859-1; strict encoder/decoder throw the specific exception types.

The values in this example demonstrate **deterministic behavior** and root-cause categories. In real projects, reproduce on the actual failing data and I/O path.

## 4. A Repeatable Debugging Workflow

### Step 1 — Shrink the Failing Case

Keep the shortest input that still reproduces the bug: `"a.b"` for regex dot issues, `"abc"` with `charAt(3)` for bounds errors, `"é"` for UTF-8/Latin-1 mismatches. Minimizing isolates the root cause without unrelated logic masking it.

### Step 2 — Classify by Wrong Result vs. Exception

- **Wrong result without throwing:** inspect actual content, whether literal vs. regex APIs were used, and whether charsets match on both ends.
- **`StringIndexOutOfBoundsException`:** inspect `length` and `begin/end` formulas, `-1` from search methods, code points vs. code units.
- **`PatternSyntaxException`:** print the regex pattern (redacting sensitive data) and check escapes, brackets, and quantifiers; if the pattern is literal text, use `Pattern.quote`.
- **`CharacterCodingException` from strict encoder/decoder:** identify the invalid byte or code point, charset, and pipeline stage.
- **`NullPointerException`:** check API null contracts and input sources. This needs separate investigation rather than automatically forcing it into one of the four main categories.

### Step 3 — Observe Data at the Right Layer

**For content errors:** inspect length, `equals`, code points, whitespace. **For index errors:** log `begin`, `end`, `length()`, and boundary checks. **For regex errors:** log the escaped pattern, distinguish full-string (`matches`) from substring (`find`), and check replacement semantics. **For encoding errors:** inspect raw hex bytes **before** decoding, both source and target charsets, and any intermediate transcoding steps.

To reproduce and explain, use observation statements like these:

```java
// Standalone examples only, assuming variables are already available.
System.out.println("length=" + input.length());
System.out.println("hex=" + HexFormat.of().formatHex(bytes));
System.out.println("index=" + index + ", end=" + end);
```

In production code, avoid logging sensitive data or secrets; record only the minimal attributes needed for diagnosis.

### Step 4 — Define the Expected Contract Before Fixing

The contract must state which data is valid: should whitespace be stripped? are composed and decomposed Unicode both accepted? are indices in code points or code units? is a pattern user-configured regex or literal text? should malformed data be replaced or strictly rejected?

Once the contract is clear, the corresponding fix follows: `equals`, normalized input handling, bounds checks, `Pattern.quote`, `Matcher.quoteReplacement`, explicit charsets, strict decoders, or proper validation errors.

### Step 5 — Write Tests for Boundary Cases

Minimum tests to include:

| Category | Normal Case | Boundary / Error Case |
| --- | --- | --- |
| Content | Two identical strings where `equals` is true | Trailing space, `null`, combining marks, different locale/casing |
| Index | `substring` on valid range | Empty string, `begin=end`, `-1` from `indexOf`, `end>length`, surrogate pair |
| Regex | Simple pattern matches | Literal `.`, `$` in replacement, invalid pattern `[`, empty string on `split` |
| Encoding | UTF-8 round-trip with Vietnamese text | Unmappable character for charset, malformed UTF-8 bytes, wrong-charset decode, emojis |

There is no need to build an elaborate test harness just to verify JDK behavior; the real value is **verifying that application functions react properly as inputs vary**.

## 5. Anti-Patterns to Avoid

### Catching Exceptions and Continuing with Bad Data

```java
// Should not be used as a fix for every index error:
try {
    returnValue = input.substring(start, end);
} catch (IndexOutOfBoundsException e) {
    returnValue = "";
}
```

This is an illustrative snippet. Returning an empty string can turn a programming bug into silent fake-valid data. Better: define the contract for `start/end`, validate before calling, and report a meaningful error if invalid.

### Forcing Every String Through `replaceAll`

When replacing literal characters or substrings, use `String.replace`. Reserve regex for when you actually need pattern matching, and manage pattern and replacement under their two separate escaping rules.

### “Fixing Encoding” Arbitrarily with `new String(old.getBytes(...), ...)`

If `old` is already mojibake or lost characters to replacement, re-encoding across multiple charsets can corrupt it further. Track down the **original bytes** and source charset, and pinpoint the exact mismatched encode/decode step. Apply corrective transcoding only after verifying both the data and the exact inverse transformation.

### Comparing Strings with `==` to Be “Faster”

`==` checks reference identity; replacing `equals` with `==` changes check semantics. If performance needs improvement, measure first and pick an appropriate representation or algorithm while preserving semantics.

### Mixing Byte Indices and Unicode Indices

A UTF-8 file byte offset, a UTF-16 code unit index, and a code point count are three different coordinate systems. Never share one integer across all three without explicit conversion.

## 6. Self-Check Exercises

**Question 1.** `"name ".equals("name")` returns `false` with no exception. Which category is this?

**Answer:** **Content error**: the left-hand string has an extra trailing space. Inspect and decide per data rules whether trailing whitespace is significant.

**Question 2.** What error does `"abc".charAt(3)` trigger?

**Answer:** **Index error**, because valid indices run from 0 to 2. `charAt(3)` throws `StringIndexOutOfBoundsException`.

**Question 3.** Why does `"a.b".replaceAll(".", "X")` return `"XXX"`?

**Answer:** **Misapplied regex error**: the dot has special meaning in patterns. To replace a literal dot, use `replace(".", "X")` or pattern `"\\."`.

**Question 4.** A service sends `"é"` in UTF-8, and the receiver decodes with ISO-8859-1. What is the bug?

**Answer:** **Wrong charset on decode**. UTF-8 bytes `c3 a9` are interpreted under a different encoding; decode as UTF-8 and align explicit charsets on both sides.

**Question 5.** Why does `"e\u0301".equals("\u00E9")` return `false` even though both can look like the same letter?

**Answer:** **Unicode content assumption error**. The two strings have different code point sequences; normalize to NFC when data policy requires equivalence.

**Question 6.** A regex `[A-Z]+` is valid, yet `matcher.find()` returns `false`. Is this a `PatternSyntaxException`?

**Answer:** No. A valid pattern finding no match is a **normal search outcome**. Only syntactically invalid patterns throw `PatternSyntaxException` at compile time.

**Question 7.** When decoding malformed UTF-8 bytes, can Java be forced to throw an error instead of replacing characters?

**Answer:** Yes. Use `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`; on malformed bytes, `decode` throws a subclass of `CharacterCodingException`.

## 7. Checklist When a String Bug Appears

1. **Which category is it?** Unexpected value, bounds access, invalid pattern, or wrong encoding?
2. **Do you have the raw input?** Save a minimal reproducible input; if I/O is involved, capture raw bytes in tests.
3. **What is being compared?** Reference vs. content, UTF-16 index vs. code point, literal vs. regex, String vs. bytes?
4. **Where does data transform?** Trace read → decode → normalize → process → encode; inspect every boundary.
5. **Does the fix honor the contract?** Never strip characters, swallow exceptions, or guess charsets blindly.
6. **Do regression tests cover edge cases?** Include empty strings, Unicode, literal regex characters, malformed bytes, and start/end bounds.

Most importantly, **inspect the right unit of data**. For content errors, look at code points; for index errors, look at UTF-16 bounds; for regex, look at pattern and replacement; for encoding, look at **raw bytes and charsets**. Once properly classified, the fix becomes clearer and tests target the true root cause.

### Official Documentation

- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java SE 17 — `Pattern` and `Matcher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).
- [Java SE 17 — `Charset`, `CharsetEncoder`, and `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).
