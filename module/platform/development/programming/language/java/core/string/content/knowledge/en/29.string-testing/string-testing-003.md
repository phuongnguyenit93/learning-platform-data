# Testing Surrogate Pairs, Unpaired Surrogates, and Combining Marks in Java String

A string can look normal on screen yet contain Unicode structures that cause length counting, slicing, UTF-8 encoding, comparisons, and tests to behave unexpectedly. Three input categories that must be tested separately are **valid surrogate pairs**, **unpaired surrogates**, and **combining marks**. They are not the same:

- A valid surrogate pair is how UTF-16 represents **one Unicode code point outside the BMP** using **two code units**.
- An unpaired surrogate is a lone surrogate code unit missing its matching partner, forming an **ill-formed UTF-16 sequence** even though Java `String` can still hold it.
- A combining mark is a valid Unicode code point that can combine with a preceding character to form a single visible glyph; multiple code points can belong to the **same grapheme cluster**.

The goal of this lesson is to build a test suite distinguishing these three cases, verify `String`/`Character` behavior, handle malformed encoded input proactively, and avoid corrupting text when slicing or normalizing.

## 1. Four Units to Distinguish Before Writing Tests

| Unit | Typical API | Example with `"A😀B"` |
| --- | --- | ---: |
| **UTF-16 code unit** | `s.length()`, `s.charAt(i)`, `substring` indices | 4 |
| **Unicode code point** | `s.codePointCount(0, s.length())`, `s.codePoints()` | 3 |
| **Grapheme cluster** (visible character cluster) | An appropriate Unicode segmenter, e.g. `BreakIterator` within its supported scope | 3 in this simple example |
| **Encoded bytes** | `s.getBytes(StandardCharsets.UTF_8).length` | 6 UTF-8 bytes |

`String.length()` counts UTF-16 code units by Java's contract, **not code points, grapheme clusters, or UTF-8 bytes**. The JVM may optimize internal `String` storage, but the meaning of `length()` never changes.

A reliable test suite should decide up front which unit a requirement constrains. For instance, “at most 20 UTF-8 bytes” requires measuring encoded bytes, “do not cut inside an emoji” requires preserving grapheme cluster boundaries, and “`charAt` position” is a UTF-16 code unit index.

## 2. Valid Surrogate Pairs

Surrogate values are divided into:

- **High surrogate:** `U+D800`–`U+DBFF`.
- **Low surrogate:** `U+DC00`–`U+DFFF`.

A high surrogate immediately followed by a low surrogate in proper order represents a Unicode code point from `U+10000` to `U+10FFFF`. For example, `😀` (`U+1F600`) is written in a Java literal as `"\uD83D\uDE00"`. These two consecutive `char` values form **one** code point.

Illustrative snippet (placed inside a Java method):

~~~java
String s = "A\uD83D\uDE00B";

System.out.println(s.length());                       // 4
System.out.println(s.codePointCount(0, s.length()));   // 3
System.out.println(Character.isHighSurrogate(s.charAt(1))); // true
System.out.println(Character.isLowSurrogate(s.charAt(2)));  // true
System.out.println(Character.isSurrogatePair(
        s.charAt(1), s.charAt(2)));                    // true
System.out.printf("U+%X%n", s.codePointAt(1));         // U+1F600
~~~

Here index `1` points to the high surrogate and `2` points to the low surrogate. `codePointAt(1)` combines the two code units into `U+1F600`, whereas `charAt(1)` returns only **one** `char` (the high surrogate).

**Slicing bug to catch:**

~~~java
String broken = s.substring(1, 2); // contains only the high surrogate
String intact = s.substring(1, 3); // contains the complete surrogate pair
~~~

`substring(begin, end)` uses UTF-16 code unit indices. Thus both statements are valid with respect to indices, yet `broken` contains ill-formed UTF-16. To slice at code point boundaries, consider `offsetByCodePoints`:

~~~java
int end = s.offsetByCodePoints(0, 2); // end == 3
String firstTwoCodePoints = s.substring(0, end); // "A😀"
~~~

This still operates by **code point**. For emojis composed of multiple code points joined by ZWJ, code point boundaries do not necessarily match grapheme cluster boundaries.

## 3. Unpaired Surrogates: `String` Can Still Hold Malformed Input

Java allows creating the following two strings, even though they do not represent valid sequences of Unicode scalar values:

~~~java
String highOnly = "\uD83D";
String lowOnly = "\uDE00";
~~~

Both have `length() == 1`. More surprisingly, `codePointCount(0, 1)` still returns `1`, and `codePointAt(0)` can return an unpaired surrogate value such as `0xD83D`. **Never use `codePointCount` as a UTF-16 validator.** `Character.isHighSurrogate` and `Character.isLowSurrogate` help inspect code unit kinds; you must verify they appear in properly ordered pairs.

| Input | Valid UTF-16? | `length()` | `codePointCount(...)` | Worth Testing |
| --- | --- | ---: | ---: | --- |
| `"\uD83D\uDE00"` | Yes | 2 | 1 | High/low pair in right order |
| `"\uD83D"` | No | 1 | 1 | High without trailing low |
| `"\uDE00"` | No | 1 | 1 | Lone low surrogate |
| `"\uD83D\uD83D"` | No | 2 | 2 | High followed by high |
| `"\uDE00\uD83D"` | No | 2 | 2 | Low before high |
| `"X\uD83D\uDE00Y"` | Yes | 4 | 3 | Surrogate pair inside a string |

A simple validator iterates over each `char`: when it sees a high surrogate, a low surrogate must follow immediately, and the pair is skipped; if a low surrogate appears unpaired, the input is invalid. The full program in section 6 implements this exact rule.

### What Happens During UTF-8 Encoding?

`String.getBytes(StandardCharsets.UTF_8)` can **replace malformed encoded data** with replacement bytes; that is not strict input validation and can silently lose information. If unpaired surrogates must be rejected, use `CharsetEncoder` with `CodingErrorAction.REPORT` to get `CharacterCodingException`.

~~~java
StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(CharBuffer.wrap(highOnly)); // throws CharacterCodingException
~~~

This snippet belongs to the method example with proper imports in section 6. Avoid asserting that the byte array from replacement encoding “still holds the original character”: an unpaired surrogate **has no valid UTF-8 representation**. Define an application policy: reject, sanitize using an agreed rule, or replace with notification.

## 4. Combining Marks and Unicode Normalization

For instance, the letter `é` has at least two common Unicode representations:

- **Composed/precomposed:** `"\u00E9"` consisting of one code point `U+00E9`.
- **Decomposed:** `"e\u0301"` consisting of `U+0065` (e) and `U+0301` (combining acute accent).

The two strings usually **look identical**, yet `String.equals` compares code unit sequences and returns `false`:

~~~java
String decomposed = "e\u0301";
String composed = "\u00E9";

System.out.println(decomposed.length()); // 2
System.out.println(composed.length());   // 1
System.out.println(decomposed.equals(composed)); // false
System.out.println(Normalizer.normalize(
        decomposed, Normalizer.Form.NFC
).equals(composed)); // true
~~~

This illustrative snippet uses `java.text.Normalizer`. When UTF-8 encoded, `decomposed` takes 3 bytes while `composed` takes 2 bytes. Normalizing to NFC can change both code unit count and byte count while visual appearance remains virtually unchanged.

**Surrogate pairs and combining marks require different tests.** `"e\u0301"` is completely valid UTF-16, containing two code points that typically form **one grapheme cluster**. Slicing with `substring(0, 1)` keeps `"e"` without producing invalid UTF-16, yet **drops the acute accent**. Conversely, slicing between high and low surrogates produces ill-formed UTF-16.

`Normalizer.Form.NFC` performs canonical composition; if a system needs canonical decomposition, use `NFD`. `NFKC`/`NFKD` also apply compatibility transformations that can alter representation semantics for many characters; do not use them casually. Normalization **is not a step that fixes all malformed surrogates**; validate well-formed UTF-16 separately.

When normalizing before storage, comparison, search, checksums, or digital signatures, all parties must agree on the **exact normalization form and when it is applied**. Never silently normalize after computing a hash or signature.

## 5. Essential Test Matrix

| Case | Test String | What to Verify |
| --- | --- | --- |
| ASCII | `"ABC"` | `length` = code point count = UTF-8 byte count |
| Valid pair | `"A\uD83D\uDE00B"` | 4 units, 3 code points, 6 UTF-8 bytes; pair is valid |
| Split pair | `"A\uD83D\uDE00B".substring(1, 2)` | Produces lone high surrogate; validator must report invalid |
| Lone high | `"\uD83D"` | Invalid UTF-16; strict UTF-8 encoder must reject |
| Lone low | `"\uDE00"` | Invalid UTF-16; strict UTF-8 encoder must reject |
| Reversed order | `"\uDE00\uD83D"` | Cannot pair; detects lone low and lone high |
| Two highs | `"\uD83D\uD83D"` | Not a valid pair |
| Combining mark | `"e\u0301"` | 2 code points, one grapheme cluster in this scenario; 3 UTF-8 bytes |
| Precomposed letter | `"\u00E9"` | 1 code point, 2 UTF-8 bytes; compare with decomposed form |
| Empty string | `""` | No error; all counts are 0 |
| Start/end boundaries | `"\uD83D\uDE00A"` and `"A\uD83D\uDE00"` | No index errors; avoid cutting half a pair |
| Joined / variation emoji | Strings with ZWJ, variation selectors, or regional indicators | Test **grapheme cluster** segmentation separately; do not assume one code point equals one emoji |

The first group tests Java's UTF-16 contract. The second group tests malformed-data handling policies. The third group tests display and normalization behavior. When writing automated tests, include both fixed examples and controlled generated inputs.

## 6. Automated Java 17+ Test Program

Create `UnicodeEdgeCasesTest.java`. This is a **standalone program, requiring no JUnit**: each `check` increments a counter and throws `AssertionError` if a condition fails, so tests still run even without the `-ea` JVM flag. Beyond counts, the program checks valid/invalid UTF-16, strict UTF-8 encoding, NFC, combining-mark segmentation, and round-trip behavior.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.BreakIterator;
import java.text.Normalizer;
import java.util.Locale;

public class UnicodeEdgeCasesTest {
    private static int assertions;

    public static void main(String[] args) throws Exception {
        testSurrogatePair();
        testUnpairedSurrogates();
        testCombiningMarks();
        testUtf8RoundTrip();
        System.out.println("PASS: " + assertions + " checks");
    }

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }

    private static boolean wellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= s.length() ||
                        !Character.isLowSurrogate(s.charAt(i + 1))) return false;
                i++;
            } else if (Character.isLowSurrogate(c)) {
                return false;
            }
        }
        return true;
    }

    private static int strictUtf8Size(String s) throws CharacterCodingException {
        ByteBuffer buffer = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(s));
        return buffer.remaining();
    }

    private static void expectMalformed(String s) throws Exception {
        try {
            strictUtf8Size(s);
            throw new AssertionError("Expected malformed UTF-16");
        } catch (CharacterCodingException expected) {
            check(true, "Malformed UTF-16 rejected by encoder");
        }
    }

    private static int graphemes(String s) {
        BreakIterator iterator = BreakIterator.getCharacterInstance(Locale.ROOT);
        iterator.setText(s);
        int count = 0;
        for (int end = iterator.first(), next = iterator.next();
                next != BreakIterator.DONE;
                end = next, next = iterator.next()) {
            count++;
        }
        return count;
    }

    private static void testSurrogatePair() {
        String text = "A\uD83D\uDE00B";
        check(text.length() == 4, "UTF-16 units");
        check(text.codePointCount(0, text.length()) == 3, "Code points");
        check(Character.isHighSurrogate(text.charAt(1)), "High surrogate");
        check(Character.isLowSurrogate(text.charAt(2)), "Low surrogate");
        check(Character.isSurrogatePair(text.charAt(1), text.charAt(2)), "Pair");
        check(text.codePointAt(1) == 0x1F600, "Combined code point");
        check(text.offsetByCodePoints(0, 2) == 3, "Code point index");
        check(wellFormedUtf16(text), "Valid text");
        check(wellFormedUtf16(text.substring(1, 3)), "Safe substring");
        check(!wellFormedUtf16(text.substring(1, 2)), "Split pair");
    }

    private static void testUnpairedSurrogates() throws Exception {
        String high = "\uD83D";
        String low = "\uDE00";
        check(high.length() == 1 && low.length() == 1, "Single units");
        check(high.codePointCount(0, 1) == 1, "High counted");
        check(low.codePointCount(0, 1) == 1, "Low counted");
        check(high.codePointAt(0) == 0xD83D, "Unpaired high codePointAt");
        check(low.codePointAt(0) == 0xDE00, "Unpaired low codePointAt");
        check(!wellFormedUtf16(high) && !wellFormedUtf16(low), "Invalid UTF-16");
        expectMalformed(high);
        expectMalformed(low);
    }

    private static void testCombiningMarks() {
        String decomposed = "e\u0301";
        String composed = "\u00E9";
        check(decomposed.length() == 2, "Two UTF-16 units");
        check(decomposed.codePointCount(0, decomposed.length()) == 2, "Two points");
        check(composed.length() == 1, "Single precomposed code unit");
        check(!decomposed.equals(composed), "Different code units");
        check(Normalizer.normalize(decomposed, Normalizer.Form.NFC).equals(composed), "NFC");
        check(decomposed.getBytes(StandardCharsets.UTF_8).length == 3, "3 bytes");
        check(composed.getBytes(StandardCharsets.UTF_8).length == 2, "2 bytes");
        check(wellFormedUtf16(decomposed), "Combining well-formed");
        check(graphemes(decomposed) == 1, "One grapheme");
        check(decomposed.substring(0, 1).equals("e"), "Split combining sequence");
    }

    private static void testUtf8RoundTrip() throws Exception {
        String valid = "A\uD83D\uDE00B";
        byte[] bytes = valid.getBytes(StandardCharsets.UTF_8);
        check(bytes.length == 6, "UTF-8 encoded bytes");
        check(new String(bytes, StandardCharsets.UTF_8).equals(valid), "Round trip");
        check(strictUtf8Size(valid) == 6, "Strict encoding");
        String loneHigh = "\uD83D";
        check(!new String(loneHigh.getBytes(StandardCharsets.UTF_8),
                StandardCharsets.UTF_8).equals(loneHigh), "Replacement loses malformed unit");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 UnicodeEdgeCasesTest.java
java UnicodeEdgeCasesTest
~~~

Exact output when all checks pass:

~~~text
PASS: 32 checks
~~~

**How the tests work:**

1. `testSurrogatePair` verifies `charAt` returns the individual high/low parts, `Character.isSurrogatePair` recognizes the pair, `codePointAt` returns `U+1F600`, and `substring(1, 2)` causes an unpaired surrogate. `offsetByCodePoints(0, 2)` returns UTF-16 index `3`.
2. `testUnpairedSurrogates` intentionally creates lone high and low surrogates. `codePointCount` still counts them, yet `wellFormedUtf16` returns `false`, and the UTF-8 encoder configured with `REPORT` rejects them.
3. `testCombiningMarks` separates “valid Unicode” from “same visual appearance”: `decomposed` and `composed` are not `equals`; NFC brings them to the same form, while their initial UTF-8 byte sizes differ.
4. `testUtf8RoundTrip` confirms a string with a valid surrogate pair survives UTF-8 encoding and decoding intact; for an unpaired high surrogate, the replacement encoding path does not preserve the original string.

`wellFormedUtf16` walks each code unit, **skips the low surrogate once a high surrogate is validated**, and rejects any lone low surrogate. `strictUtf8Size` encodes to UTF-8 via `CharsetEncoder`: for valid input, `ByteBuffer.remaining()` gives the byte count; for malformed input, `CharacterCodingException` lets the test assert failure instead of ignoring it.

`graphemes` demonstrates `BreakIterator.getCharacterInstance(Locale.ROOT)` on the **simple case** of `e` + combining acute accent. `BreakIterator` depends on the JDK version's segmentation data/rules and is not automatically a complete solution for every ZWJ emoji sequence or the newest Unicode grapheme rules. If your product requires slicing/counting grapheme clusters for complex emojis, pick a segmentation engine that satisfies the required Unicode version and real-world test cases (e.g. a library like ICU4J when appropriate), and cross-check against sample data.

## 7. Testing Indices and Boundaries When Slicing Strings

For `"A😀B"`, the most useful test creates **both the intact result and the corrupted result**:

~~~java
String input = "A\uD83D\uDE00B";

String bad = input.substring(1, 2);  // high surrogate only
String good = input.substring(1, 3); // complete surrogate pair
~~~

Both `substring` calls are API-valid and **do not throw exceptions on their own**. Errors appear later when the broken data is transcoded or processed. For computed indices, check:

- Within `0..length()` and not reversed (`begin/end`).
- Does not land between high and low surrogates when preserving code points.
- Does not split a combining mark from its base character or split a ZWJ sequence when preserving **visible character clusters**.
- The round trip `UTF-16 String → UTF-8 bytes → String` preserves valid input with the right charset, and handles invalid input according to policy.

You can compute boundaries by code points using `offsetByCodePoints`, keeping in mind that **this call does not validate unpaired surrogates** and does not guarantee grapheme boundaries. Display policy and encoding policy are two separate testing layers.

## 8. Encoding Tests: `getBytes`, Strict Encoder, and Strict Decoder

For valid text:

~~~java
String input = "A\uD83D\uDE00B";
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);
String restored = new String(utf8, StandardCharsets.UTF_8);

// utf8.length == 6; restored.equals(input) == true
~~~

This snippet sits inside a method with `StandardCharsets` imported. It verifies the result by **UTF-8 bytes**, not `String.length()`.

When encoding an unpaired surrogate, ordinary `getBytes(StandardCharsets.UTF_8)` performs replacement, **failing to preserve** the original value. When valid Unicode data is required, use a `REPORT` encoder as in section 6.

Similarly, when **receiving external UTF-8 bytes**, `new String(bytes, UTF_8)` can replace invalid bytes with the replacement character. To reject them, use a strict decoder:

~~~java
String strictDecoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

This snippet belongs inside a method that already has `bytes` and the necessary imports; if the input bytes are malformed, it can throw `CharacterCodingException`. Do not confuse the two cases: **an unpaired surrogate in a Java String is malformed UTF-16**, whereas a **malformed UTF-8 byte sequence** is an error at decode time; both need appropriate test cases at data ingress/egress boundaries.

## 9. Testing Semantic Equivalence and Normalization

`String.equals` compares string representations, so:

~~~java
String a = "e\u0301";
String b = "\u00E9";
boolean rawEqual = a.equals(b); // false

String nfcA = Normalizer.normalize(a, Normalizer.Form.NFC);
String nfcB = Normalizer.normalize(b, Normalizer.Form.NFC);
boolean normalizedEqual = nfcA.equals(nfcB); // true
~~~

This illustrative snippet uses `Normalizer`. Tests should pick one clear policy:

- **Exact byte/representation comparison:** two encodings are not equivalent if their code units differ; e.g., signed payloads or byte-specified identifiers.
- **Comparison after Unicode normalization:** standardize on a form (NFC/NFD/... per contract), normalizing before comparing and before related operations such as key generation or checksums.
- **Fuzzy matching for user search:** may require additional rules beyond normalization, such as case folding or locale-sensitive collators; do not treat `Normalizer` as a full linguistic comparator.

Do not assume two visually identical strings share the same `length()`, UTF-8 bytes, or code point sequence. Tests should reflect the system's exact contract rather than forcing one universal rule onto all data.

## 10. Common Mistakes in Unicode Testing

**Mistake 1 — Running tests with ASCII only.** With ASCII, `length()`, code point count, and UTF-8 byte count are equal, hiding most Unicode bugs. Add emojis, characters beyond Latin-1, and combining marks.

**Mistake 2 — Testing `codePointCount` to assert “valid UTF-16.”** Unpaired surrogates are still counted as one code point by Java's string-traversal APIs. Use a surrogate-pair validator or an encoder configured with `REPORT`.

**Mistake 3 — Assuming `substring` succeeding means text is intact.** Cutting inside a surrogate pair creates a broken string even though the call succeeds. Cutting between a base character and combining mark produces valid UTF-16 yet loses display meaning.

**Mistake 4 — Normalizing in tests but not in production.** Test results fail to reflect real behavior. Identify exactly where normalization happens and test that actual code path.

**Mistake 5 — Treating one code point as one screen character.** `e\u0301` has 2 code points yet usually renders as one letter. Complex emojis can also span multiple code points; test grapheme cluster segmentation when cursor position, display width, or text truncation is involved.

**Mistake 6 — Counting characters with `String.length()` for UTF-8 byte limits.** For `"A😀B"`, `length()` is 4, while UTF-8 requires 6 bytes. Measure the actual byte array after applying the protocol's encoding.

**Mistake 7 — Testing a replacement decoder while thinking the system rejects invalid bytes.** Replacement mode and `REPORT` mode are different contracts; test both success cases and error-throwing cases per requirements.

**Mistake 8 — Relying on fonts, terminals, or screenshots to draw conclusions.** Rendering depends on fonts and renderers. Test code points, lengths, UTF-8 bytes, and normalization with comparable values; use visual checks only as a supplement for UI needs.

## 11. Self-Check Questions

**1.** For `"\uD83D\uDE00"`, what do `length()` and `codePointCount` return?

**Answer:** **2** UTF-16 code units and **1** code point (`U+1F600`), respectively.

**2.** For `"\uD83D"`, why does `codePointCount(0, 1) == 1` not prove the data is valid?

**Answer:** The API counts an unpaired surrogate as one element when traversing; a high surrogate without a paired low surrogate is ill-formed UTF-16. Surrogate structure must be checked explicitly.

**3.** Why is `"e\u0301".substring(0, 1)` different from slicing mid-surrogate pair?

**Answer:** `"e"` is still a valid Unicode string, though it lost its combining mark; half of a surrogate pair is **ill-formed UTF-16**. Encoding validity and grapheme integrity are two separate criteria.

**4.** Should `String.equals` be used to assert that `"e\u0301"` and `"\u00E9"` are equal?

**Answer:** No: `equals` directly returns `false`. If the contract allows canonical equivalence, normalize both to the same form, such as NFC, before comparing.

**5.** When an application rejects unpaired surrogates before emitting UTF-8, should you choose `String.getBytes(UTF_8)` or a `CharsetEncoder` configured with `REPORT`?

**Answer:** Choose the strict encoder with `REPORT` to detect errors rather than silently replacing them.

## 12. Project Application Checklist

When fixing garbled characters, wrong lengths, search misses, or clipped emojis, identify in order: whether source data is UTF-16 or UTF-8 bytes; the policy for rejecting/replacing malformed input; the intended measurement unit (code units, code points, graphemes, or bytes); when normalization occurs; cut boundaries; and test cases with concrete Unicode values. The test suite in section 6 can run on JDK 17+, and you can then add cases specific to your application's data.

References: [`String` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html), [`Character` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html), [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html), [`Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html), [`BreakIterator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html).
