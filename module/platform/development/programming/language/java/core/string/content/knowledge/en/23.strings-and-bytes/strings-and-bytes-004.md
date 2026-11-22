# UTF-8 Length Does Not Equal `String.length()` in Java

A Java `String` is a sequence of Unicode text represented by **UTF-16 code units**. In contrast, UTF-8 is a way to **encode text into bytes**. Therefore, the following two expressions measure two different quantities:

~~~java
int utf16Units = text.length();
int utf8Bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
~~~

`text.length()` returns the number of UTF-16 code units in the string; `getBytes(StandardCharsets.UTF_8).length` returns the number of bytes after encoding the string to UTF-8. You must distinguish them when enforcing data size limits, computing network payload sizes, storing data, or truncating strings.

## 1. Three Counts That Are Easy to Confuse

| Quantity | Java API | What It Measures |
| --- | --- | --- |
| UTF-16 code units | `text.length()` | Number of `char` values making up the `String` |
| Unicode code points | `text.codePointCount(0, text.length())` | Number of code points in the string; a non-BMP code point usually occupies two `char`s |
| UTF-8 byte count | `text.getBytes(StandardCharsets.UTF_8).length` | Length of the byte array after UTF-8 encoding |

**Do not equate any of these three with "the number of user-perceived characters."** For example, the letter `é` can be represented as one code point `U+00E9` or as `e` plus combining acute accent `U+0301` (two code points). Many family emojis, flags, or emojis with modifiers are formed from multiple code points yet render as a single character cluster. Counting *grapheme clusters* (visual character clusters) is a separate problem.

### Why Does Java `String.length()` Count UTF-16?

In Java, `length()` historically counts UTF-16 code units, not bytes on disk or Unicode code points.

- Code points in the BMP (`U+0000` to `U+FFFF`), excluding the surrogate range, normally take **one** UTF-16 code unit.
- A supplementary code point outside the BMP (`U+10000` to `U+10FFFF`), such as `😀` (`U+1F600`), takes **two** UTF-16 code units: a surrogate pair.
- A Java `String` can contain invalid unpaired surrogates; `length()` still counts code units, while byte encoding must handle the malformed UTF-16 sequence.

For example, `"A😀B"` contains three code points (`A`, `😀`, `B`), yet `length()` returns **4** because the emoji takes two UTF-16 code units.

### Why Does UTF-8 Have a Different Byte Count?

For a valid Unicode code point, UTF-8 uses variable-length encoding:

| Code Point Range | UTF-8 Bytes | Example |
| --- | ---: | --- |
| `U+0000`–`U+007F` | 1 | `A` |
| `U+0080`–`U+07FF` | 2 | `é` (`U+00E9`) |
| `U+0800`–`U+FFFF` (excluding surrogates) | 3 | `ệ` (`U+1EC7`) |
| `U+10000`–`U+10FFFF` | 4 | `😀` (`U+1F600`) |

Because a Java `char` is a UTF-16 code unit while UTF-8 bytes belong to a different encoding, **there is no general formula** such as `utf8Bytes = text.length()`, `text.length() * 2`, or `text.length() * 3`. You must use actual UTF-8 encoding or an algorithm based on each valid code point.

## 2. Easy-to-Verify Examples

| String | `length()` | Code Points | UTF-8 Bytes | Explanation |
| --- | ---: | ---: | ---: | --- |
| `"Hello"` | 5 | 5 | 5 | All characters are ASCII, 1 UTF-8 byte each |
| `"Việt"` | 4 | 4 | 6 | `V`, `i`, `t`: 1 byte each; `ệ`: 3 bytes |
| `"A😀B"` | 4 | 3 | 6 | `A`: 1 byte; `😀`: 4 bytes; `B`: 1 byte |
| `"e\u0301"` | 2 | 2 | 3 | `e` (1 byte) and combining acute accent `U+0301` (2 bytes) |
| `"\u00E9"` (`é`) | 1 | 1 | 2 | Precomposed `é` (`U+00E9`): 2 bytes |

In the last two rows, the Java literals `"\u0301"` and `"\u00E9"` use Unicode escape notation. Although a reader may see both representations of `é` as identical, the counts of code units, code points, and bytes still differ.

## 3. Java 17+ Program Measuring Each Value

Create a file `Utf8LengthDemo.java` with the content:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8LengthDemo {
    public static void main(String[] args) {
        inspect("ASCII", "Hello");
        inspect("Vietnamese", "Vi\u1EC7t");
        inspect("Emoji", "A\uD83D\uDE00B");
        inspect("Combining", "e\u0301");
        inspect("Precomposed", "\u00E9");
    }

    private static void inspect(String name, String text) {
        int utf16Units = text.length();
        int codePoints = text.codePointCount(0, text.length());
        int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

        System.out.printf(
                "%s: length=%d, codePoints=%d, utf8Bytes=%d%n",
                name, utf16Units, codePoints, utf8Bytes
        );
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 Utf8LengthDemo.java
java Utf8LengthDemo
~~~

Expected output:

~~~text
ASCII: length=5, codePoints=5, utf8Bytes=5
Vietnamese: length=4, codePoints=4, utf8Bytes=6
Emoji: length=4, codePoints=3, utf8Bytes=6
Combining: length=2, codePoints=2, utf8Bytes=3
Precomposed: length=1, codePoints=1, utf8Bytes=2
~~~

Here, accented characters and the emoji are written using Unicode escapes so the demo program can be copied easily regardless of terminal font or rendering differences. `StandardCharsets.UTF_8` specifies the charset explicitly, avoiding dependence on the environment's default charset.

Key observations from the table:

1. For ASCII, all three counts happen to match; that equivalence **does not** hold across all of Unicode.
2. For `ệ`, one code point is one UTF-16 code unit yet encodes as three UTF-8 bytes.
3. For `😀`, Java counts two UTF-16 code units, Unicode counts one code point, and UTF-8 uses four bytes.
4. The two representations of `é` show that identical visual appearance does not guarantee identical binary representation.

## 4. Counting Bytes Properly and Choosing the Charset

To find the UTF-8 byte count, **specify UTF-8 explicitly** right where the string is converted to bytes:

~~~java
import java.nio.charset.StandardCharsets;

String text = "Sample data";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;
~~~

This is an illustrative snippet to use inside a program. `payload.length` is the size of the **exact byte array just created**; the value is a byte count, not a character count.

Avoid:

~~~java
// Does not measure UTF-8 size:
int wrongBytes = text.length();

// Avoid letting the charset depend on the environment:
byte[] platformDependent = text.getBytes();
~~~

The no-argument `getBytes()` uses the JVM's default charset. The default charset can depend on the Java version, configuration, and startup options. When **UTF-8** is required, use the `getBytes(StandardCharsets.UTF_8)` overload to make the intent explicit.

**Limitation of this count:** it measures the string after UTF-8 encoding, not necessarily the actual byte count of an entire HTTP document, JSON payload, compressed file, or network message. Those layers may add quotes, escapes, delimiters, headers, a BOM, framing, or alter the representation. For example, Java string content `"😀"` encodes directly in UTF-8 as 4 bytes, but in a JSON format if a serializer chooses to escape it as `"\uD83D\uDE00"`, the byte count of the emitted JSON text will differ. Measure the **exact bytes of the final payload** if the protocol enforces limits on the transmitted payload.

### Invalid UTF-16 Strings

A Java `String` can hold an unpaired surrogate, such as `"\uD800"`. That is not a valid Unicode scalar value for direct UTF-8 encoding. `String.getBytes(StandardCharsets.UTF_8)` uses replacement behavior for invalid input; the resulting bytes reflect the replacement result rather than the UTF-8 encoding of a valid code point. If malformed data must be rejected, use `CharsetEncoder` with `CodingErrorAction.REPORT` instead of accepting silent replacement:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Demo {
    public static void main(String[] args) {
        String text = "Java \uD83D\uDE00";

        try {
            ByteBuffer bytes = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(text));
            System.out.println(bytes.remaining());
        } catch (CharacterCodingException ex) {
            System.out.println("Invalid Unicode input");
        }
    }
}
~~~

This is a standalone program `StrictUtf8Demo.java`; run commands:

~~~bash
javac -encoding UTF-8 StrictUtf8Demo.java
java StrictUtf8Demo
~~~

Output:

~~~text
9
~~~

Explanation: `"Java "` takes 5 UTF-8 bytes and the emoji takes 4 bytes. `remaining()` counts the remaining bytes in the `ByteBuffer` right after encoding. If you replace the valid string with a lone surrogate, the `REPORT`-configured encoder throws an error and the `catch` branch runs.

## 5. Truncating a String to a Byte Limit Without Breaking UTF-8

Suppose a system allows at most **5 UTF-8 bytes**. The string `"A😀B"` is 4 UTF-16 code units long yet occupies 6 bytes. Arbitrarily slicing the byte array or calling `substring(0, 5)` will fail: `substring` accepts **UTF-16 code unit** positions, not bytes, and index 5 even exceeds this string's length.

The safe approach for a **valid UTF-16 string** is to iterate code point by code point, add the exact UTF-8 byte width of each code point, and stop before exceeding the limit. For example, create `Utf8PrefixDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8PrefixDemo {
    public static void main(String[] args) {
        String input = "A\uD83D\uDE00B";

        String prefix = prefixWithinUtf8Bytes(input, 5);
        System.out.println(prefix.length());
        System.out.println(prefix.codePointCount(0, prefix.length()));
        System.out.println(prefix.getBytes(StandardCharsets.UTF_8).length);
        System.out.println(prefix.equals("A\uD83D\uDE00"));
    }

    public static String prefixWithinUtf8Bytes(String input, int maxBytes) {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes must be nonnegative");
        }

        StringBuilder result = new StringBuilder();
        int written = 0;

        for (int offset = 0; offset < input.length();) {
            int codePoint = input.codePointAt(offset);

            // An unpaired surrogate indicates invalid UTF-16.
            if (codePoint >= Character.MIN_SURROGATE
                    && codePoint <= Character.MAX_SURROGATE) {
                throw new IllegalArgumentException("Invalid UTF-16 input");
            }

            int utf8Width;
            if (codePoint <= 0x7F) {
                utf8Width = 1;
            } else if (codePoint <= 0x7FF) {
                utf8Width = 2;
            } else if (codePoint <= 0xFFFF) {
                utf8Width = 3;
            } else {
                utf8Width = 4;
            }

            if (utf8Width > maxBytes - written) {
                break;
            }

            result.appendCodePoint(codePoint);
            written += utf8Width;
            offset += Character.charCount(codePoint);
        }

        return result.toString();
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 Utf8PrefixDemo.java
java Utf8PrefixDemo
~~~

Output:

~~~text
3
2
5
true
~~~

The limit is 5 bytes, so the longest valid prefix **from the start of the string** is `"A😀"`: `A` needs 1 byte, the emoji needs 4 bytes, totaling 5. This string has 3 UTF-16 code units and 2 code points. The trailing `B` would exceed the limit.

The method above intentionally rejects unpaired surrogates; it checks `maxBytes - written` rather than adding to the written byte count to avoid `int` overflow for extreme limits. It stops on code point boundaries, so it never produces half a surrogate pair or half a UTF-8 byte sequence.

**However, "not splitting inside a code point" still does not guarantee "not splitting inside a user-perceived character cluster."** For instance, `e` and combining mark `U+0301` are two code points belonging to the same visible letter. When a UI requires splitting by grapheme cluster (or handling multi-component emojis), apply proper cluster-segmentation rules first, then check the byte budget per cluster. Avoid treating `codePointCount` as a universal solution for all UI character-counting problems.

## 6. Unicode Normalization: Looking Identical Yet Differing in Bytes

The following two strings usually render identically yet have different representations:

~~~java
String decomposed = "e\u0301"; // e + combining acute accent
String composed = "\u00E9";   // precomposed é
~~~

| Representation | UTF-16 units | Code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `decomposed` | 2 | 2 | 3 |
| `composed` | 1 | 1 | 2 |

When business rules require a normalized Unicode form, Java provides `java.text.Normalizer`:

~~~java
import java.text.Normalizer;

String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
boolean sameRepresentation = normalized.equals(composed); // true
~~~

This is an illustrative snippet inside a method. `NFC` can combine decomposed sequences into precomposed forms where Unicode defines them; as a result, it can change both the code point count and the byte count. **Normalize only when the data specification or business requirements permit it**; never silently normalize a payload that is digitally signed, hashed, compared byte-for-byte, or stored under a preserve-input contract.

To check byte-level equality, normalization (if needed) must be an agreed step on both the sender and receiver sides prior to comparison/encoding.

## 7. Practical Applications

### Length Limits When Storing Data

If a storage constraint says "at most 1,024 **UTF-8 bytes**", do not substitute `text.length() <= 1024`. Compare `getBytes(StandardCharsets.UTF_8).length` against 1,024 after deciding on normalization rules and invalid-input handling. A database "character" limit may have its own semantics, so read the documentation for the specific column and database engine before assuming a byte limit.

### HTTP or Network Payloads

For a request body consisting directly of `text.getBytes(StandardCharsets.UTF_8)`, the byte count can be taken from `payload.length`. The `Content-Length` field (when used by the protocol) refers to the byte count of the message body under the applicable framing, not the UTF-16 unit count of the source string. If a JSON serializer or transport layer alters the content, measure the final bytes produced by that layer.

### Reading Data and Decoding

When receiving UTF-8 bytes, the reverse conversion is:

~~~java
import java.nio.charset.StandardCharsets;

byte[] payload = /* bytes from data source */;
String decoded = new String(payload, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet where `payload` must come from an actual source. `decoded.length()` continues to be the number of UTF-16 code units, **not** `payload.length`. The decoder can replace invalid UTF-8 byte sequences; if bad input must be rejected, use `CharsetDecoder` with `CodingErrorAction.REPORT`.

### Testing Multilingual Data

Include test cases with ASCII, accented Vietnamese, non-BMP characters (emojis), combining marks, empty strings, and capacity boundaries (e.g., exactly 5 bytes and over 5 bytes). If the system accepts untrusted input, also test unpaired surrogates or malformed UTF-8 bytes according to the system's error contract.

## 8. Common Mistakes

1. **Using `length()` to check UTF-8 size.** For `"Việt"`, the check sees 4 while actual UTF-8 requires 6 bytes. Fix by encoding to UTF-8 explicitly or using a verified counting algorithm.
2. **Assuming every `char` is a Unicode character.** `😀` takes two `char`s. Iterating individual code units to encode or slice can split a surrogate pair; iterate code points when the task operates on code points.
3. **Using `codePointCount` instead of byte count.** `"A😀B"` has 3 code points yet requires 6 UTF-8 bytes.
4. **Slicing a UTF-8 byte array at an arbitrary index and decoding.** You can slice between the leading byte and continuation bytes of the same code point, producing invalid UTF-8 or replacement characters. Slice at code point boundaries; if displaying to users, also respect grapheme cluster boundaries.
5. **Calling `getBytes()` without specifying a charset.** The result does not explicitly enforce UTF-8. Use `getBytes(StandardCharsets.UTF_8)`.
6. **Assuming two visually identical strings always have identical bytes.** Precomposed/decomposed Unicode forms and strings with invisible characters can differ. Define normalization conventions and compare according to requirements.
7. **Counting bytes of a source string and treating that as the byte count of the full JSON/HTTP message.** Serialization can add escapes, quotes, and metadata. Payload limits must measure the final output.

## 9. Practice Exercises with Answers

**Exercise 1.** Given `String s = "A😀B";`, what are the values of these three expressions?

~~~java
s.length();
s.codePointCount(0, s.length());
s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
~~~

**Answer:** `4`, `3`, and `6`. UTF-16 uses two code units for the emoji; UTF-8 uses four bytes.

**Exercise 2.** A buffer allows at most 4 UTF-8 bytes. Can it hold `"A😀B"` intact? If a prefix must be kept on a code point boundary, what is the longest prefix?

**Answer:** No, the original string takes 6 bytes. The longest prefix from the start of the string is `"A"` (1 byte), because adding `😀` needs 4 more bytes and would exceed 4 bytes. You must never keep "half an emoji."

**Exercise 3.** `"e\u0301"` and `"\u00E9"` both render as `é`. Is `getBytes(UTF_8).length` guaranteed to be equal?

**Answer:** No. The decomposed form takes 3 bytes, while the precomposed form takes 2 bytes. You can normalize to NFC when the data contract allows it.

**Exercise 4.** An API accepts a JSON body limited to 100 bytes. Should you check `String.length()` of a property to decide if it exceeds the limit?

**Answer:** No. You must check the actual serialized JSON in the request body's encoding; a property value may contain escaped characters, and the body also includes field names, quotes, braces, and other fields.

## 10. Key Takeaways

- `String.length()` → **UTF-16 code units**.
- `codePointCount(...)` → **Unicode code points**.
- `getBytes(StandardCharsets.UTF_8).length` → **number of bytes after UTF-8 encoding**.
- None of the three counts automatically answers "how many characters the user sees."
- When enforcing a **byte** limit, check the **actual bytes**; byte truncation must respect Unicode boundaries and, when needed, character cluster boundaries.

API documentation: [`String.length()` and `codePointCount`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html), [`StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html), and [`Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).
