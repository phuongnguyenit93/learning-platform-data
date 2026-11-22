# Specifying Index Units or Length Limits in Java `String` APIs

## 1. The problem: "position 3" and "at most 20 characters" are not clear enough

An API accepting `String` often has parameters like `start`, `end`, `maxLength`, or `maxChars`. Without specifying the **unit**, callers may misunderstand it as the number of characters visible on screen, while the Java code performs `String.length()` or `substring()` using **UTF-16 code units**.

For example, consider a string consisting of the letter `A`, the emoji `😃`, and the letter `e` with a combining acute accent (`e\u0301`):

~~~text
Displayed:          A | 😃 | é
UTF-16 code unit:   1 +  2 + 2 = 5
Unicode code point: 1 +  1 + 2 = 4
UTF-8 byte:         1 +  4 + 3 = 8
Grapheme cluster:   1 +  1 + 1 = 3 (per standard Unicode segmentation)
~~~

Thus, the exact same data can be described as having length **5**, **4**, **8**, or **3** depending on the criterion. If the API documentation only states "maximum length 4 characters", users will not know whether this string is valid or rejected.

**Design principle:** every index, slice range, cursor position, and length limit must be tied to an **explicitly defined counting unit**.

## 2. Four common units

| Unit | Meaning | Related Java APIs | Use when |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Each 16-bit `char` of `String` | `length()`, `charAt()`, `substring()`, `indexOf()` | Compatibility with `String` APIs, internal Java offsets |
| **Unicode code point** | Unicode code represented by `int`; non-BMP characters use two code units | `codePoints()`, `codePointCount()`, `codePointAt()`, `offsetByCodePoints()` | Processing rules per code point |
| **Grapheme cluster** | A sequence of characters a user normally perceives as a single character | Unicode grapheme-boundary segmentation library | Deleting/selecting/cutting characters in user interfaces |
| **Encoded bytes** | Number of bytes after encoding, such as UTF-8 | `getBytes(StandardCharsets.UTF_8)`, `CharsetEncoder` | Protocols, networking, storage, payload limits |

**Note:** a grapheme cluster can contain multiple code points (base letter + combining mark; emoji with ZWJ, variation selectors, or skin tones). Conversely, the number of display columns in a terminal does not necessarily equal the number of grapheme clusters; rendering also depends on fonts, terminals, and environments.

If an API uses `int` for both UTF-16 indices and code point counts, **the `int` type does not express the unit**. Variable names, method names, contract documentation, or distinct value types must be used to make it clear.

## 3. How Java `String` indexes: UTF-16 code units

Most indexing APIs on `String` use **UTF-16 code units**:

~~~java
String s = "A\uD83D\uDE03B"; // A😃B
System.out.println(s.length());          // 4
System.out.println(s.charAt(0) == 'A');   // true
System.out.println(s.charAt(3) == 'B');   // true
~~~

The two `char` values at indices 1 and 2 are the **high surrogate** and **low surrogate** of `😃`, respectively. Therefore `substring(1, 2)` takes only half of the surrogate pair, causing the resulting string to contain an unpaired surrogate:

~~~java
String broken = s.substring(1, 2);
System.out.println(broken.length());                  // 1
System.out.println(Character.isHighSurrogate(
        broken.charAt(0)));                           // true
~~~

`substring(beginIndex, endIndex)` extracts the **half-open** range `[beginIndex, endIndex)`: inclusive of start, exclusive of end, and both parameters are UTF-16 indices, **not code point or grapheme indices**.

An API should clearly describe both the **unit** and the **boundary rule**:

> `sliceUtf16(String input, int beginUtf16Inclusive, int endUtf16Exclusive)` accepts offsets in UTF-16 code units and uses the range [begin, end). The caller must choose appropriate boundaries if a code point or grapheme must be preserved.

If the API is intended for end users, forcing them to pass UTF-16 offsets may be inappropriate; consider a code-point or grapheme-based API instead.

## 4. When the contract requires code points

`String.codePointCount(beginIndex, endIndex)` counts code points within a **UTF-16 index** range. `String.codePoints().count()` counts across the entire string. In both cases, a valid surrogate pair is counted as **one** code point; an unpaired surrogate is counted individually and does not vanish on its own.

~~~java
String s = "A\uD83D\uDE03B";
System.out.println(s.length());                     // 4
System.out.println(s.codePointCount(0, s.length())); // 3
System.out.println(s.codePoints().count());         // 3
~~~

To convert code point indices into **UTF-16 indices** for `substring`, use `offsetByCodePoints`:

~~~java
String s = "A\uD83D\uDE03B";

int beginUtf16 = s.offsetByCodePoints(0, 1);
int endUtf16 = s.offsetByCodePoints(beginUtf16, 1);

String secondCodePoint = s.substring(beginUtf16, endUtf16);
System.out.println(secondCodePoint.equals("\uD83D\uDE03")); // true
~~~

`beginUtf16` is 1, `endUtf16` is 3: the exact surrogate pair of the emoji. Never assume `substring(1, 2)` will extract "the second character".

### Building an API that slices by code point count

The following is a standalone method example that can be placed inside a Java class:

~~~java
static String takeCodePoints(String input, int maxCodePoints) {
    java.util.Objects.requireNonNull(input, "input");
    if (maxCodePoints < 0) {
        throw new IllegalArgumentException("maxCodePoints < 0");
    }

    int count = input.codePointCount(0, input.length());
    int numberToKeep = Math.min(maxCodePoints, count);
    int endUtf16 = input.offsetByCodePoints(0, numberToKeep);
    return input.substring(0, endUtf16);
}
~~~

The name `maxCodePoints` explicitly states the unit. The function will not split a valid surrogate pair in half, though it can still cut **between code points belonging to the same grapheme cluster** (e.g., letter `e` and its combining mark). When the requirement is "do not corrupt displayed characters", dedicated grapheme segmentation is required.

**Do not confuse:** the second parameter of `offsetByCodePoints(index, codePointOffset)` is the number of code points to move; its return value is still a **UTF-16 offset**.

## 5. When the contract requires grapheme clusters

For example, `"e\u0301"` consists of **two code points** (`e` and the combining acute accent) but usually renders as **one** accented letter. Certain family emojis also consist of multiple code points joined by ZWJ, while the user sees a single icon.

Therefore:

- `String.length()` does **not** count visible characters.
- `codePoints().count()` also does **not** always count visible characters.
- `substring` or taking exactly `n` code points can cut between components of a grapheme.

For input-field length limits, deleting one character via Backspace, or UI cursor positioning, determine whether **extended grapheme cluster** is the desired unit.

In Java, `java.text.BreakIterator.getCharacterInstance()` exists, but its grapheme segmentation capability per Unicode depends on the version and supported rules; do not assume it matches all latest extended grapheme cluster rules on every JDK. If requirements demand strict compliance with Unicode UAX #29, use a library with explicit grapheme boundary support (such as ICU4J), document the library's Unicode version, and test with real data.

An API can be named explicitly such as:

~~~java
// Illustrative design signatures; implementation requires a grapheme segmenter.
int countGraphemeClusters(String text);

// Returns at most N grapheme clusters, without cutting inside a cluster.
String takeGraphemeClusters(String text, int maxClusters);
~~~

The two signatures above only illustrate the **API contract**, not a standalone runnable program.

## 6. When limits are measured in bytes

Network protocols, storage fields, or file formats often constrain length in **bytes**. In such cases `String.length()` does not answer the right question.

In UTF-8, `A` takes 1 byte, `😃` takes 4 bytes, `e` takes 1 byte, and the combining acute accent U+0301 takes 2 bytes. The string `A😃e\u0301` therefore occupies **8 UTF-8 bytes** even though `length()` is only 5.

~~~java
String value = "A\uD83D\uDE03e\u0301";
int bytes = value.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;

System.out.println(bytes); // 8
~~~

Defining a limit should state it completely, for example:

- `maxUtf8Bytes = 255`: at most 255 bytes **after UTF-8 encoding**.
- `maxCodePoints = 50`: at most 50 code points in `String`.
- `maxUtf16Units = 100`: at most 100 UTF-16 code units; equivalent to `String.length() <= 100`.

If an API sends data as JSON, a limit on "bytes of the **serialized and UTF-8 encoded JSON payload**" can differ from "UTF-8 bytes of the string value before serialization": double quotes, escapes, property names, and JSON structural tokens can take extra bytes.

**Encoding is part of the contract.** Saying "255 bytes" without mentioning UTF-8, UTF-16, or the wire format is an incomplete specification.

### Inputs with invalid surrogates

A Java `String` can still contain unpaired surrogates. `getBytes(StandardCharsets.UTF_8)` may use a replacement character when it cannot encode the input, so counting bytes with `getBytes` is not the same as **validating well-formed UTF-16**. If the system must reject malformed data, validate surrogate pairs first or use `CharsetEncoder` with `CodingErrorAction.REPORT` and handle `CharacterCodingException` per application policy.

Do not slice a UTF-8 byte array directly at an arbitrary index and decode it back: the cut can fall in the middle of a multi-byte code point sequence. To limit bytes while preserving characters, slice at **code point or grapheme boundaries** and check the encoded byte count.

## 7. Designing unambiguous API contracts

### 7.1. Include the unit in names

Compare:

~~~java
// Ambiguous: what limit, what kind of index?
String truncate(String value, int limit);

// Clearer: how many Unicode code points at most?
String takeCodePoints(String value, int maxCodePoints);

// Clearer: positions in UTF-16.
String sliceUtf16(String value,
                  int beginUtf16Inclusive,
                  int endUtf16Exclusive);

// Clearer: data must fit within the UTF-8 byte limit.
boolean fitsUtf8Bytes(String value, int maxUtf8Bytes);
~~~

These signatures express **design intent**; the implementation must honor the stated unit instead of naming a parameter `maxCodePoints` and then checking `value.length()`.

You should also specify:

1. **Is the limit inclusive of the boundary?** "at most 20" usually means `<= 20`.
2. **Are indices 0-based or 1-based?** In Java `String`, indices are 0-based.
3. **Is the interval `[begin,end)` or `[begin,end]`?** `substring` uses a half-open interval.
4. **Truncate or reject?** For instance, validation returns an error when over the limit, while truncate intentionally cuts. Do not silently truncate data when the contract only says "validate".
5. **How are `null`, negative limits, out-of-range indices, and malformed surrogates handled?** Clearly specify exceptions or return values.
6. **Is input normalized before measuring?** For example, Unicode NFC, trim, or case conversion can change length; the processing order must be defined.

### 7.2. Use distinct types when multiple units coexist

If the same system frequently handles both byte offsets and UTF-16 offsets, separate types can prevent passing the wrong one:

~~~java
record Utf16Index(int value) {}
record CodePointIndex(int value) {}
record Utf8ByteLimit(int value) {}
~~~

These are **illustrative** type declarations (Java 17). The records themselves do not guarantee a valid index; bounds checking is needed when using them with a specific string. However, a signature taking `Utf16Index` is far less likely to be confused with `CodePointIndex` than when all take `int`.

### 7.3. Document rules in API docs and examples

An example contract can be written as:

> `takeCodePoints(text, n)` returns the prefix consisting of at most `n` Unicode code points of `text`, preserving the original order without splitting valid surrogate pairs. `n` must be non-negative. The method does not promise to preserve extended grapheme clusters, does not normalize Unicode, and does not constrain UTF-8 byte count.

This description can be verified via unit tests. The phrase "take at most n characters" cannot fully convey such commitments.

## 8. Complete compilable and runnable Java 17+ example

Save the file `StringUnitContractDemo.java`. The example uses Unicode escape notation in source so it does not depend on emoji keyboard input when copying code:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public class StringUnitContractDemo {
    static String takeCodePoints(String input, int maxCodePoints) {
        Objects.requireNonNull(input, "input");
        if (maxCodePoints < 0) {
            throw new IllegalArgumentException("maxCodePoints < 0");
        }
        int available = input.codePointCount(0, input.length());
        int endUtf16 = input.offsetByCodePoints(
                0, Math.min(maxCodePoints, available));
        return input.substring(0, endUtf16);
    }

    static boolean fitsUtf8Bytes(String input, int maxUtf8Bytes) {
        Objects.requireNonNull(input, "input");
        if (maxUtf8Bytes < 0) {
            throw new IllegalArgumentException("maxUtf8Bytes < 0");
        }
        return input.getBytes(StandardCharsets.UTF_8).length
                <= maxUtf8Bytes;
    }

    static boolean isWellFormedUtf16(String input) {
        Objects.requireNonNull(input, "input");
        for (int i = 0; i < input.length(); i++) {
            char unit = input.charAt(i);
            if (Character.isHighSurrogate(unit)) {
                if (i + 1 == input.length()
                        || !Character.isLowSurrogate(input.charAt(i + 1))) {
                    return false;
                }
                i++; // Skip the low surrogate of the checked pair.
            } else if (Character.isLowSurrogate(unit)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        // A + emoji 😃 + e + combining acute accent U+0301
        String text = "A\uD83D\uDE03e\u0301";

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePoints().count());
        System.out.println("utf8Bytes=" +
                text.getBytes(StandardCharsets.UTF_8).length);

        int beginUtf16 = text.offsetByCodePoints(0, 1);
        int endUtf16 = text.offsetByCodePoints(beginUtf16, 1);
        System.out.println("emojiEquals=" + text.substring(
                beginUtf16, endUtf16).equals("\uD83D\uDE03"));

        System.out.println("prefixEquals=" +
                takeCodePoints(text, 2).equals("A\uD83D\uDE03"));

        String broken = text.substring(0, 2);
        System.out.println("brokenWellFormed=" +
                isWellFormedUtf16(broken));
        System.out.println("originalWellFormed=" +
                isWellFormedUtf16(text));

        System.out.println("within4CodePoints=" +
                (text.codePointCount(0, text.length()) <= 4));
        System.out.println("within7Utf8Bytes=" +
                fitsUtf8Bytes(text, 7));

        System.out.printf("emojiCodePoint=U+%X%n",
                text.codePointAt(1));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 StringUnitContractDemo.java
java StringUnitContractDemo
~~~

`stdout` output:

~~~text
utf16Units=5
codePoints=4
utf8Bytes=8
emojiEquals=true
prefixEquals=true
brokenWellFormed=false
originalWellFormed=true
within4CodePoints=true
within7Utf8Bytes=false
emojiCodePoint=U+1F603
~~~

**Explanation:**

- `length()` gives `5` because the emoji takes two `char`s, while the letter `e` and the combining acute accent are two separate code units.
- `codePoints().count()` gives `4`: `A`, emoji, `e`, combining acute accent.
- `getBytes(UTF_8).length` gives `8`; thus a **7-byte** limit is exceeded, even though a **4-code-point** limit still fits.
- Using `offsetByCodePoints` to compute the two UTF-16 bounds extracts the full emoji.
- `substring(0, 2)` accidentally ends right after the **high surrogate**, so `isWellFormedUtf16` detects corrupted slicing.
- Checking well-formed UTF-16 in the example is a separate step and is not replaced by checking `length()` or code point count.

`fitsUtf8Bytes` illustrates measuring bytes for valid input; if the application strictly forbids malformed input, call `isWellFormedUtf16` or use a reporting encoder before accepting data.

## 9. Order of normalization, validation, and storage

A string processing pipeline should establish the order of steps before setting limits:

1. **Decode input** according to the agreed encoding (e.g., UTF-8), with a clear policy for malformed data.
2. **Validate** characters or business rules; decide whether unpaired surrogates are accepted.
3. **Normalize if required by the contract**: e.g., Unicode NFC or consistent whitespace handling rules.
4. **Measure in the published unit**: code points, graphemes, or UTF-8 bytes after encoding.
5. **Reject or truncate** per API policy, then store/transmit in the desired format.

Do not assume `Normalizer.normalize`, `strip()`, `toLowerCase()`, or serializers are "length-neutral" operations. They can change the number of code points, UTF-16 units, or bytes. If length is checked on the **pre-processed** value while storing the **post-processed** value, the contract must clearly explain the unit and measurement stage.

For example, `"é"` in U+00E9 form and `"e\u0301"` (U+0065 + U+0301) may look identical, but before NFC they have **1** and **2** code points respectively; their UTF-8 byte counts also differ. If both forms must be accepted as the same data, normalizing before validation is a design decision that must be stated explicitly.

## 10. Essential test cases

| Data | UTF-16 unit | Code point | UTF-8 byte | What to verify |
| --- | ---: | ---: | ---: | --- |
| `"ABC"` | 3 | 3 | 3 | ASCII: all units match |
| `"é"` (U+00E9) | 1 | 1 | 2 | BMP, yet UTF-8 requires two bytes |
| `"e\u0301"` | 2 | 2 | 3 | Two code points usually form one grapheme |
| `"😃"` | 2 | 1 | 4 | Supplementary code point uses a surrogate pair |
| `"A😃e\u0301"` | 5 | 4 | 8 | Limits differ by unit |
| Empty string `""` | 0 | 0 | 0 | Boundary case |
| Unpaired surrogate | Depends on input | Emitted individually by `codePoints()` | Depends on encoder policy | Requires validation for malformed Unicode data |

To test a string-slicing API, you also need cases for:

- Limit equal to 0, equal to length, less than length, and greater than length.
- Negative limits and out-of-bounds indices.
- Cut points immediately **before**, **inside**, and **after** a surrogate pair.
- Cut points between a base letter and a combining mark.
- Multi-code-point emoji with ZWJ/variation selector; tested against the chosen Unicode version.
- Data with characters of 1-, 2-, 3-, and 4-byte UTF-8 lengths.
- Strings with different Unicode normalization forms that look visually identical.
- Byte-limit boundaries computed on the **actual value sent or stored**.

## 11. Checklist when publishing an API

- **Which unit?** `utf16Unit`, `codePoint`, `graphemeCluster`, `utf8Byte`, or serialized payload byte count?
- **Which indexing?** 0-based/1-based and closed/open interval?
- **Measured at which step?** Before or after normalize, trim, encode, escape, or serialize?
- **What happens when exceeding the limit?** Return an error or truncate? Preserve graphemes?
- **What about malformed data?** Unpaired surrogates, invalid encoding, `null`, negative limits?
- **Compatibility with other APIs?** `substring()` requires UTF-16 offsets; grapheme segmenters have specific Unicode versions.
- **Tested on real Unicode?** Supplementary characters, combining marks, composite emojis, multi-byte characters.

**Conclusion:** in Java APIs, the word "character" is usually too ambiguous to serve as an index or limit unit. `String.length()` and `substring()` use **UTF-16 code units**; `codePoints()` uses **Unicode code points**; display length requires **grapheme clusters**; transmission/storage limits usually require **encoded bytes**. Name and write contracts that specify the exact unit, boundary rules, and normalization order, and test with Unicode strings where each unit yields a different result.