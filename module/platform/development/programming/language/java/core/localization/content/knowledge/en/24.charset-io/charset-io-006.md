# MalformedInputException, Replacement Characters, and Data Loss

Reading or writing text in Java is not merely converting a byte array into a `String`. Between bytes and characters sit a **charset** (character encoding), a `CharsetDecoder`, a `CharsetEncoder`, and an **error-handling policy**. If a byte sequence is invalid for the chosen charset, Java can **report an error**, **replace the bad segment with another character**, or **skip that segment**. These choices make a huge difference to data integrity.

A program can appear to read “successfully” while the content has already suffered **irreversible information loss**. For example, the byte sequence `41 C3 28 42` is not valid UTF-8. A lenient reading API may produce a string containing:

~~~text
A�(B
~~~

The `�` symbol here is typically **U+FFFD REPLACEMENT CHARACTER**. Meanwhile, a UTF-8 decoder configured in `REPORT` mode will throw `MalformedInputException` instead of silently altering the bytes.

This lesson belongs to **Java core - localization / Charset and I/O**, focusing on:

- Distinguishing **syntactically invalid bytes** (*malformed input*) from **unrepresentable characters** (*unmappable character*).
- Understanding `MalformedInputException`, `UnmappableCharacterException`, `CharacterCodingException`, and the three policies `CodingErrorAction.REPORT`, `REPLACE`, and `IGNORE`.
- Knowing which APIs **replace by default** and which **report errors** on Java 17+.
- Understanding the `U+FFFD` character, question marks `?` when encoding, and *mojibake*.
- Designing file-reading/writing, HTTP payload, or data-import pipelines that **detect wrong charsets**, preserve original bytes when needed, and avoid turning lost data into content treated as valid.

**Core message:** The fact that a `String` was created **does not prove the input byte data is valid**, and the absence of U+FFFD in a string **does not prove the right charset was chosen**.

## 1. Mechanism: Bidirectional Bytes ↔ Unicode

Basic diagram:

~~~text
Read:
byte[] / file / network
      ↓ [CharsetDecoder + charset + error policy]
Unicode text (String/CharBuffer)
      ↓
process, display, store in database

Write:
Unicode text (String/CharBuffer)
      ↓ [CharsetEncoder + charset + error policy]
byte[] / file / network
~~~

In the **read** direction, a UTF-8 decoder checks whether bytes follow UTF-8 structure; structurally invalid byte sequences can raise `MalformedInputException`. In the **write** direction, a US-ASCII encoder cannot represent `à` or `ộ`; this is normally an **unmappable character** error, which can raise `UnmappableCharacterException`.

Key points:

1. **Charsets cannot simply be “seen” from raw bytes.** Many byte formats contain no charset metadata; you must know it from the protocol, configuration, valid BOM, or system specification.
2. **Unicode text** and **encoded bytes** are two separate layers. A Java `String` is not “a UTF-8 string”; UTF-8 is one encoding of strings into bytes.
3. **Replacement** can prevent downstream code from knowing what the original segment was.
4. **Error reporting** lets you retain original bytes and decide how to remediate before data is altered.

An internationalized application usually prefers **explicit UTF-8**, yet using UTF-8 is not enough if the actual source is Windows-1252, Shift_JIS, or another format without a clear contract.

## 2. What Is Malformed Input?

`Malformed input` is a byte sequence **syntactically invalid under the selected charset**. In UTF-8, certain leading bytes require valid continuation bytes. If a continuation byte is wrong or the sequence is truncated, the decoder cannot turn it into a valid Unicode code point.

Example:

~~~text
41 C3 28 42
^^ ^^ ^^ ^^
 A  ?  (  B
~~~

`0x41` is `A`. Byte `0xC3` in UTF-8 normally starts a two-byte sequence, yet `0x28` is the `(` character rather than a `10xxxxxx` continuation byte. Thus the sequence violates UTF-8 structure.

- Under **`REPORT`**, the decoder reports an error upon hitting the bad byte.
- Under **`REPLACE`**, the decoder inserts the replacement string, typically `U+FFFD`, and continues.
- Under **`IGNORE`**, the decoder skips the invalid segment and continues.

Do not equate “malformed” with “a character unreadable by the font.” A valid code point can render as a box due to missing glyphs; that is a **rendering issue**, not a decoding error.

### A Complete Java Example

Create **`MalformedUtf8Demo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

public class MalformedUtf8Demo {
    public static void main(String[] args) {
        byte[] bytes = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };

        String forgiving =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(forgiving.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        try {
            String strict = StandardCharsets.UTF_8
                    .newDecoder()
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
            System.out.println(strict);
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac MalformedUtf8Demo.java
java MalformedUtf8Demo
~~~

Output on Java 17:

~~~text
[U+0041, U+FFFD, U+0028, U+0042]
MalformedInputException
~~~

We print **code points** to avoid depending on whether the console font renders `�` uniformly. The first line proves an API **produced Unicode data after replacement**, not that the initial bytes were decoded intact.

## 3. Where Does `MalformedInputException` Fit?

`java.nio.charset.MalformedInputException` belongs to the Charset API exception hierarchy:

~~~text
java.lang.Exception
  └── java.io.IOException
       └── java.nio.charset.CharacterCodingException
            ├── MalformedInputException
            └── UnmappableCharacterException
~~~

`MalformedInputException` provides `getInputLength()`, which gives the length of the **erroneous input segment** reported by the coder, typically in input units of the encoding/decoding process: bytes for a decoder, `char` input units for an encoder.

Do not treat `getInputLength()` as a **position in the file**. It does **not** supply a global byte offset or the offending bytes themselves. If you must investigate errors in a long stream, track offsets and relevant bytes with your own I/O logic while ensuring sensitive data is not leaked to logs.

A single `catch (CharacterCodingException ex)` catches both fundamental coding errors. To distinguish them specifically:

~~~java
try {
    decoder.decode(ByteBuffer.wrap(bytes));
} catch (MalformedInputException ex) {
    // Input byte/char sequence is invalid for the charset.
} catch (UnmappableCharacterException ex) {
    // Input unit is valid but cannot be mapped.
}
~~~

This is a **method-body snippet**; it requires importing `java.nio.charset` classes and `java.nio.ByteBuffer`, with `decoder` and `bytes` already defined.

Do not catch `Exception` and ignore it as a “font bug.” It signals input data quality issues or a wrong charset.

## 4. Malformed vs. Unmappable: How Do They Differ?

These two error types are often conflated:

| Concept | Nature | Example |
| --- | --- | --- |
| **Malformed input** | Input units do not form a valid sequence under the charset or input UTF-16 | UTF-8 leading byte without a valid continuation byte |
| **Unmappable character** | Valid input sequence, yet **no mapping exists in the target charset** | Attempting to encode `à` into US-ASCII |
| **Mojibake** | Bytes decoded **validly under the wrong charset**, producing strange text | UTF-8 bytes of `é` read as ISO-8859-1 producing `Ã©` |
| **Missing glyph** | Valid Unicode text, yet font lacks a suitable representation | Boxes/tofu in the application |
| **Normalization difference** | Two canonically equivalent Unicode forms with different code point sequences | `é` vs. `e` + U+0301 |

`MalformedInputException` is not a catch-all exception for all “broken-looking” content. Text showing `Ã©` may have gone through **100% successful decoding**. Converting a string to a narrower charset can fail in the **encoder** rather than the decoder.

Pinpointing the exact error layer is the first step to avoid fixing data the wrong way.

## 5. `CharsetDecoder` and the Three `CodingErrorAction`s

`java.nio.charset.CharsetDecoder` lets you choose policies for **two separate error categories**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

The actions:

- **`REPORT`:** detects the error, returns an error `CoderResult` in the *incremental* API, or throws `CharacterCodingException` in `CharsetDecoder`'s convenience decode. Use when **data integrity matters**.
- **`REPLACE`:** skips the bad segment, inserts the corresponding replacement string, and continues. Recovers the rest of the valid text, yet **loses information**.
- **`IGNORE`:** discards the bad segment completely and continues. Can concatenate two text segments previously separated by corrupted data, altering meaning.

Create **`DecodePoliciesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class DecodePoliciesDemo {
    private static String decode(
            byte[] input, CodingErrorAction action) throws Exception {

        CharsetDecoder decoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);

        return decoder.decode(ByteBuffer.wrap(input)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] bad = {0x41, (byte) 0xC3, 0x28, 0x42};

        System.out.println(decode(bad, CodingErrorAction.REPLACE)
                .codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        System.out.println(decode(bad, CodingErrorAction.IGNORE));
    }
}
~~~

~~~bash
javac DecodePoliciesDemo.java
java DecodePoliciesDemo
~~~

Output:

~~~text
[U+0041, U+FFFD, U+0028, U+0042]
A(B
~~~

**`IGNORE` is not a way to fix charsets**: it only drops corrupted segments. If data is personal names, payment descriptions, or legal text, dropping a character can change meaning without leaving a trace.

## 6. A New Decoder Defaults to `REPORT`

The biggest source of confusion is that **`StandardCharsets.UTF_8.newDecoder()`** defaults to **`REPORT`** for malformed and unmappable, whereas many convenience APIs use **`REPLACE`**.

Example:

~~~java
CharsetDecoder decoder =
        StandardCharsets.UTF_8.newDecoder();

System.out.println(decoder.malformedInputAction());
System.out.println(decoder.unmappableCharacterAction());
~~~

This is a method-body snippet importing `java.nio.charset.*`. Output:

~~~text
REPORT
REPORT
~~~

Calling:

~~~java
decoder.decode(ByteBuffer.wrap(bytes));
~~~

on error throws `CharacterCodingException`, specifically `MalformedInputException` when applicable.

Yet:

~~~java
new String(bytes, StandardCharsets.UTF_8);
~~~

with invalid UTF-8 bytes **normally does not throw a coding exception**. The `Charset` constructor is documented by Java to **replace malformed/unmappable sequences with the default replacement string**.

Likewise, `StandardCharsets.UTF_8.decode(ByteBuffer.wrap(bytes))` is a `Charset` convenience API documented to operate with replacement. **Do not infer the default of every API from `newDecoder()`'s default.**

## 7. `new String(byte[], Charset)` Can Mask Errors

Create **`StringDecodeReplacementDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;

public class StringDecodeReplacementDemo {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xC3, (byte) 0x28};

        String value =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(value.length());
        System.out.println(value.codePointAt(0) == 0xFFFD);
        System.out.println(value.codePointAt(1) == '(');
    }
}
~~~

~~~bash
javac StringDecodeReplacementDemo.java
java StringDecodeReplacementDemo
~~~

Output:

~~~text
2
true
true
~~~

The string is valid at the `String` layer, yet the start was replaced with `U+FFFD`. If the application stores it in a database and discards the original bytes, **it is impossible to know for sure which bytes produced that replacement**.

### Distinguishing Real Replacements from Data Containing U+FFFD

A `String` containing U+FFFD **does not prove** the input source was corrupted. A user may intentionally submit a U+FFFD character validly encoded in UTF-8. Conversely, a stream may have had characters replaced with `?` or dropped before reaching the application, so a final string **without U+FFFD** can still have lost data.

Therefore, checking:

~~~java
text.indexOf('\uFFFD') >= 0
~~~

is useful only as a **suspicion flag**, not a validator of original byte data. To prove source data is valid, you must **validate strictly at decode time**, before replacement happens.

## 8. `Files.readString`: Strict on Invalid Bytes

An important API difference in Java 17:

- `Files.readString(path)` defaults to UTF-8.
- `Files.readString(path, charset)` uses an explicit charset.
- Per the Java 17 Javadoc, they can throw `IOException` when encountering **malformed or unmappable byte sequences**.

This is **not** the “automatic replacement like `new String(bytes, charset)`” behavior.

Example **`StrictFileReadDemo.java`**:

~~~java
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StrictFileReadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("utf8-demo-", ".bin");

        try {
            Files.write(file, new byte[]{
                    0x41, (byte) 0xC3, 0x28, 0x42
            });

            try {
                System.out.println(
                        Files.readString(file, StandardCharsets.UTF_8));
            } catch (MalformedInputException ex) {
                System.out.println("Invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac StrictFileReadDemo.java
java StrictFileReadDemo
~~~

Output when run on Java 17:

~~~text
Invalid UTF-8
~~~

The program creates a temporary file, writes corrupted bytes, attempts to read as UTF-8, and deletes the file in `finally`. The lesson is that not all Java file APIs behave alike; **you must read the contract of the specific method**.

If you need fine-grained control over `REPORT/REPLACE/IGNORE`, configure a `CharsetDecoder` explicitly instead of guessing a convenience API's behavior.

## 9. `InputStreamReader` May Replace Errors by Default

`InputStreamReader(InputStream, Charset)` bridges a byte stream to a character stream. With the constructor taking a `Charset`, malformed/unmappable sequences are normally handled by **replacement** per the Reader's contract.

Example **`ReaderReplacementDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ReaderReplacementDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {

            for (int c; (c = reader.read()) != -1;) {
                System.out.print("U+%04X ".formatted(c));
            }
            System.out.println();
        }
    }
}
~~~

~~~bash
javac ReaderReplacementDemo.java
java ReaderReplacementDemo
~~~

Output:

~~~text
U+0041 U+FFFD U+0028 U+0042
~~~

If you need an **error-reporting Reader**, use the constructor taking a **configured `CharsetDecoder`** instead of the `Charset` overload:

~~~java
CharsetDecoder strict =
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(inputStream, strict);
~~~

This is a **method-body snippet**, requiring imports for `java.io.Reader`, `java.io.InputStreamReader`, and `java.nio.charset` classes. `inputStream` is an existing input stream; close the Reader with try-with-resources when used.

## 10. Encoding Errors When Writing: `UnmappableCharacterException`

The reverse direction also carries risk. A Java `String` can contain Unicode characters that **the target charset does not support**.

Example:
- US-ASCII represents only the 7-bit ASCII set.
- The letters `à` (U+00E0) and `ộ` (U+1ED9) cannot be represented as corresponding US-ASCII bytes.
- A `CharsetEncoder` created via `newEncoder()` defaults to **`REPORT`**, and can throw `UnmappableCharacterException`.

Create **`UnmappableEncodingDemo.java`**:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

public class UnmappableEncodingDemo {
    public static void main(String[] args) {
        String text = "H" + (char) 0x00E0
                + " N" + (char) 0x1ED9 + "i";

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .encode(CharBuffer.wrap(text));
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac UnmappableEncodingDemo.java
java UnmappableEncodingDemo
~~~

Output:

~~~text
UnmappableCharacterException
~~~

This is neither a UTF-8 bug nor a Java compiler bug. The target encoding **US-ASCII has no representation** for those source characters.

### Why Use `CharsetEncoder` When Data Preservation Matters?

Using a strict encoder detects unconvertible characters **before writing the file**. Using a replacing API can turn original text into `?`, losing the original if it is not saved separately.

## 11. `String.getBytes(Charset)` and the `?` Character

Like the convenience decoder, `String.getBytes(Charset)` may **replace unencodable characters** with the target charset's default replacement byte.

Create **`QuestionMarkLossDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class QuestionMarkLossDemo {
    public static void main(String[] args) {
        String vietnamese = "H" + (char) 0x00E0
                + " N" + (char) 0x1ED9 + "i";

        byte[] output =
                vietnamese.getBytes(StandardCharsets.US_ASCII);

        System.out.println(Arrays.toString(output));
        System.out.println(new String(
                output, StandardCharsets.US_ASCII));
    }
}
~~~

~~~bash
javac QuestionMarkLossDemo.java
java QuestionMarkLossDemo
~~~

Output:

~~~text
[72, 63, 32, 78, 63, 105]
H? N?i
~~~

Decimal byte `63` corresponds to the ASCII question mark `?`. Two Vietnamese characters could not be represented; once only these ASCII bytes remain, there is no way to know they were originally `à` and `ộ`.

**Note:** Each charset's replacement byte can differ; never assume every encoding replaces errors with `?`. For the `UTF-8` decoder, the replacement character is typically U+FFFD; for the US-ASCII encoder in the example, the replacement is the byte for `?`.

When data integrity is required, **do not use a silently replacing conversion path** where encoding can fail.

## 12. What Is the U+FFFD Replacement Character?

**U+FFFD REPLACEMENT CHARACTER** is a Unicode code point used to represent **character data that cannot be interpreted accurately** in many pipelines.

It typically renders as:

~~~text
�
~~~

However, its visual glyph depends on the font, and a string containing U+FFFD only shows that **the Unicode value is present**. It does not prove the current application generated the replacement, because the data may have been replaced in an earlier step.

Finding U+FFFD:

~~~java
boolean containsReplacement =
        text.codePoints().anyMatch(cp -> cp == 0xFFFD);
~~~

This is a **snippet**, where `text` is an existing `String`. For data passing through multiple layers, you can record:
- source bytes;
- declared charset;
- decoder/policy used;
- count and offsets of errors if designed to capture them;
- hash of original bytes for verification.

Do not log raw sensitive data directly to “debug U+FFFD.” Byte offsets and incident codes are usually safer than logging full PII/secret content.

## 13. Invalid Bytes, Wrong Charset, and *Mojibake* Are Three Separate Issues

Suppose you have the letter `é`. Its UTF-8 encoding is two bytes:

~~~text
C3 A9
~~~

If these two bytes are decoded as **ISO-8859-1**, they correspond to U+00C3 and U+00A9 respectively. The resulting string typically appears as `Ã©`.

**Key takeaway:** both bytes have valid mappings in ISO-8859-1, so decoding **does not necessarily throw `MalformedInputException`**. The semantically wrong output stems from **choosing the wrong charset**, not from bytes violating the chosen charset's rules.

Create **`WrongCharsetDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        byte[] bytes = {
                (byte) 0xC3, (byte) 0xA9
        };

        String correct = new String(
                bytes, StandardCharsets.UTF_8);
        String wrong = new String(
                bytes, StandardCharsets.ISO_8859_1);

        System.out.println(correct.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        System.out.println(wrong.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());
    }
}
~~~

~~~bash
javac WrongCharsetDemo.java
java WrongCharsetDemo
~~~

Output:

~~~text
[U+00E9]
[U+00C3, U+00A9]
~~~

This is **mojibake** caused by wrong charset metadata. A strict decoder cannot infer on its own that `C3 A9` “must be UTF-8” if we instructed it to decode as ISO-8859-1 and the input is valid under that charset.

**Conclusion:** Strict error reporting is necessary to catch **invalid bytes**, yet **insufficient** to guarantee you picked **the true encoding of the source**.

## 14. Valid UTF-8 Does Not Mean Right Language

A byte sequence can be valid simultaneously under multiple charsets. Even decoding under the wrong charset can produce seemingly “normal” Unicode characters.

Examples:
- ASCII byte `41` represents `A` in both UTF-8 and US-ASCII.
- Multi-byte UTF-8 sequences can overlap with valid codes in ISO-8859-1, yielding different characters.
- A file saved in Windows-1252 can be read as UTF-8 and fail as malformed at isolated high bytes.
- Double-encoded UTF-8 content can produce **valid UTF-8 bytes yet corrupted text**.

To pick the right charset, rely first on the **data contract**: HTTP `Content-Type`/charset when applicable, file format, source configuration, partner protocol, BOM, and format rules.

Do not invent a heuristic “no error means it must be UTF-8” to replace system metadata. For legacy data, an encoding detector only yields an **estimate**, requiring verification and sometimes human review.

## 15. When to Use `REPORT`, `REPLACE`, `IGNORE`?

| Policy | What happens | Better suited for | Risk |
| --- | --- | --- | --- |
| **REPORT** | Halts or reports coding error | Business data imports, payments, identifiers, auditing, migrations | Requires error-handling workflow |
| **REPLACE** | Turns bad segment into replacement | Intentional previews/logs, tools inspecting corrupted data | Readers may mistakenly think content is intact |
| **IGNORE** | Drops bad segment | Non-critical exploratory pipelines, explicitly flagged as lossy | Silent character loss, unwanted text merging |

**Never use IGNORE by default** for important content due to the risk of dropping characters or field delimiters.

When corrupted data must be previewed temporarily, an application can:
1. Store the **original bytes** in quarantine.
2. Record the decode error and charset used.
3. Generate a **preview** using `REPLACE`, clearly labeled “incomplete data.”
4. Never use the character-replaced preview to automatically decide invoices, amounts, personal names, or identifier keys.

The goal is ensuring a **lossy** processing path is never mistaken for a clean import.

## 16. Configuring the Replacement String on a Decoder

`CharsetDecoder` provides `replaceWith(String)` to choose replacement text, provided the value is valid for the decoder.

Example:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");

String output = decoder.decode(
        ByteBuffer.wrap(badBytes)).toString();
~~~

This is a **snippet**; it requires importing `CharsetDecoder`, `StandardCharsets`, `CodingErrorAction`, `ByteBuffer`, with `badBytes` as an existing byte array.

Using a question mark on decode makes diagnostics **harder** than U+FFFD, because real input data may legitimately contain question marks. Whether the replacement is U+FFFD, `?`, or another string, **original content is still not preserved**.

For an encoder, `CharsetEncoder.replaceWith(byte[])` sets **replacement bytes** for unencodable errors; replacement strings and replacement bytes are two separate concepts for the two directions.

## 17. Checking the Encoder Before Writing

You can use:

~~~java
CharsetEncoder encoder =
        StandardCharsets.US_ASCII.newEncoder();

boolean supported = encoder.canEncode(text);
~~~

This is a snippet; `text` is a `CharSequence`. `canEncode` helps determine whether Unicode text can be represented in the target charset, yet should not be treated as a complete substitute for final strict encoding in concurrent pipelines or when data can change after validation.

A solid design **encodes with a strict encoder right at the byte-generation step**:

~~~java
ByteBuffer buffer = StandardCharsets.US_ASCII
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(CharBuffer.wrap(text));
~~~

This is a snippet with `CharBuffer`, `ByteBuffer`, and charset imports. `encode` can throw `CharacterCodingException`; handle it in a method with `throws` or `try/catch`. On success, the remaining bytes in `ByteBuffer` are the output to write.

Do not call `String.getBytes(StandardCharsets.US_ASCII)` after a strict check assuming both processes always share the same policy; keep the entire conversion step consistent.

## 18. Side-by-Side Strict and Replacement Encoding Example

Create **`EncodePoliciesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EncodePoliciesDemo {
    private static byte[] bytes(ByteBuffer buffer) {
        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        return result;
    }

    public static void main(String[] args) throws Exception {
        String input = "H" + (char) 0x00E0 + " Noi";

        CharsetEncoder strict =
                StandardCharsets.US_ASCII.newEncoder();

        try {
            strict.encode(CharBuffer.wrap(input));
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        CharsetEncoder replacing =
                StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE);

        ByteBuffer encoded =
                replacing.encode(CharBuffer.wrap(input));

        System.out.println(Arrays.toString(bytes(encoded)));
    }
}
~~~

~~~bash
javac EncodePoliciesDemo.java
java EncodePoliciesDemo
~~~

Output:

~~~text
UnmappableCharacterException
[72, 63, 32, 78, 111, 105]
~~~

The second output shows `à` became a question mark. If a recipient sees only those bytes, there is no trace that the original had a diacritic. For important data, treat a strict error as a signal to **preserve the original** or switch to an appropriate charset, usually UTF-8.

## 19. Not Only U+FFFD: Question Marks and Dropped Bytes Are Data Loss

There are at least three common corruption modes:

1. **UTF-8 decoding with replacement**: one or more corrupted bytes become `U+FFFD`.
2. **Encoding to a narrow charset**: unrepresentable Unicode characters become replacement bytes, such as `?` in US-ASCII.
3. **IGNORE**: offending bytes or characters vanish completely.

Once converted to a lossy result, reverse encoding cannot recover the original input. Example:

~~~java
byte[] malformed = {
        (byte) 0xC3, (byte) 0x28
};

String repaired = new String(
        malformed, StandardCharsets.UTF_8);

byte[] roundTrip = repaired.getBytes(
        StandardCharsets.UTF_8);
~~~

This is a snippet; `roundTrip` holds valid UTF-8 bytes for `U+FFFD` and `(`, rather than matching the initial `malformed` array.

**There is no unique “recovery” from U+FFFD**: many different byte sequences map to the same replacement character. Likewise, `?` could appear because the real source contained `?` or because an encoder substituted an unrepresentable character.

Hence only **original bytes**, backups, or trusted source metadata enable accurate recovery.

## 20. Round-Trip Checks and Their Limits

A check to detect specific data loss:

~~~java
byte[] original = {/* original bytes */};

String value = strictDecode(original, charset);
byte[] encoded = strictEncode(value, charset);

boolean identical = Arrays.equals(original, encoded);
~~~

This is **Java-style pseudocode snippet**, where `strictDecode` and `strictEncode` are application-defined functions; it illustrates a strategy rather than a complete program.

If input uses a charset with **multiple ways to encode the same content**, or a pipeline applies Unicode normalization, newline conversion, BOM alteration, or different serialization rules, a **byte-identical round-trip** may not be the right contract. Distinguish:

- **Byte-for-byte preservation**: files/archives/digital signatures require byte equality.
- **Unicode value preservation**: equivalent text content after decode/encode may suffice, provided equivalence is defined.
- **Business meaning preservation**: text must also pass validation, not merely be valid Unicode.

Do not use round-trip equality as absolute proof against choosing the wrong charset: when a byte sequence is valid under the wrong charset, decoding and re-encoding under that same wrong charset can still return identical bytes even though the text was misinterpreted.

## 21. File Charset and JVM Default in Java 17

Java 17 **does not default to UTF-8 uniformly across all operating systems and configurations**. APIs relying on `Charset.defaultCharset()` can be environment-dependent. Starting in Java 18, JEP 400 makes UTF-8 the default charset for many Java SE APIs under a defined policy, yet specific APIs and exceptions still require attention.

In Java 17+ code, the clearest practice is **passing the charset explicitly**:

~~~java
Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
new String(bytes, StandardCharsets.UTF_8);
text.getBytes(StandardCharsets.UTF_8);
~~~

Note that these four calls **do not share the same error policy** merely because they all take UTF-8. The two `String` calls normally replace errors; `Files.readString` can fail on invalid bytes.

Additionally, `Files.writeString` handles encoding differently from `String.getBytes` in certain cases. For data requiring strictness, verify the write method's contract or explicitly use a `CharsetEncoder` with `REPORT`.

**Never treat the default `file.encoding` as the charset metadata of an existing file.** A file may have been generated earlier by another system with an independent charset.

## 22. BOM, UTF-8, and Truncated Data

A **BOM (byte order mark)** can help identify byte order for UTF-16/UTF-32 or appear in some UTF-8 files. However:
- Not every file has a BOM.
- Do not trust a BOM if the protocol specifies another encoding.
- Data starting with a BOM does not mean all following bytes are valid.
- A file truncated mid-way through a multi-byte UTF-8 sequence still causes malformed input.
- How an API handles or preserves U+FEFF depends on the charset and reader/configuration.

If data arrives in **streams/chunks**, a UTF-8 character can span two chunks. Reading a single chunk and decoding it as **complete text** can misclassify a trailing partial sequence as malformed, even though the continuation byte sits in the next chunk.

The right approach is:
- Keep a stateful `CharsetDecoder` across chunks;
- Use the incremental decode API with `endOfInput=false` until the true source ends;
- Set `endOfInput=true` only when no more bytes remain;
- Handle `CoderResult.UNDERFLOW`, `OVERFLOW`, malformed, and unmappable per contract;
- Call `flush` per the decoder's lifecycle.

Never arbitrarily split a `byte[]` and call `new String(chunk, UTF_8)` repeatedly if your goal is reassembling the original text **without losing bytes**.

## 23. Streaming Decoder and `CoderResult`

`CharsetDecoder.decode(ByteBuffer in, CharBuffer out, boolean endOfInput)` is an **incremental** API. Instead of always throwing an exception, it can return a `CoderResult`:

| Result | Meaning |
| --- | --- |
| `UNDERFLOW` | Available input processed; more bytes may be needed |
| `OVERFLOW` | Output buffer is out of space |
| `isMalformed()` | Input sequence is syntactically invalid for the charset |
| `isUnmappable()` | Input is valid but cannot be mapped |
| `length()` | Number of input units in the offending segment per the coder |
| `throwException()` | Converts an error result into its corresponding exception |

In `REPORT` mode, an error is not necessarily thrown immediately inside the incremental overload; the caller must **inspect `CoderResult`**. If code calls `decode(in,out,endOfInput)` and ignores the result, data can be mishandled or the loop can stall.

For applications without large streaming needs, using `CharsetDecoder.decode(ByteBuffer)` with a strict decoder is usually simpler and clearer.

## 24. UTF-16 Surrogate Issues When Encoding

A `String` holds UTF-16 code units and can contain an **unpaired surrogate** (a high or low surrogate without a valid partner), for example due to truncated data or unsafe `char`-level manipulation.

An unpaired surrogate **does not form a valid Unicode scalar value** representable in UTF-8. In the encoding direction, `CharsetEncoder` can treat this as **malformed input**.

Example:

~~~java
String broken = String.valueOf((char) 0xD800);

CharsetEncoder strict = StandardCharsets.UTF_8.newEncoder();
strict.encode(CharBuffer.wrap(broken));
~~~

This is an **error-illustration snippet**; calling `encode` can throw `MalformedInputException`. You can use `Character.isHighSurrogate`, `isLowSurrogate`, and code-point iteration logic to validate UTF-16 structure when needed.

**Not every encoder error is `UnmappableCharacterException`**: if the input Unicode itself has malformed UTF-16 structure, that is malformed input; if the code point is valid yet unrepresentable by the target charset, that is an unmappable character.

## 25. Strict Decoding Example for Services

Create **`StrictTextDecoder.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.util.Objects;

public final class StrictTextDecoder {
    private StrictTextDecoder() {}

    public static String decode(byte[] bytes, Charset charset)
            throws CharacterCodingException {

        Objects.requireNonNull(bytes, "bytes");
        Objects.requireNonNull(charset, "charset");

        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    public static void main(String[] args) {
        byte[] good = {
                (byte) 0x43, (byte) 0x61,
                (byte) 0x66, (byte) 0xC3, (byte) 0xA9
        };
        byte[] bad = {(byte) 0xC3, (byte) 0x28};

        try {
            String result = decode(
                    good, java.nio.charset.StandardCharsets.UTF_8);
            System.out.println(result.codePointCount(
                    0, result.length()));
        } catch (CharacterCodingException ex) {
            System.out.println("Good input rejected");
        }

        try {
            decode(bad, java.nio.charset.StandardCharsets.UTF_8);
            System.out.println("Bad input accepted");
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac StrictTextDecoder.java
java StrictTextDecoder
~~~

Output:

~~~text
4
MalformedInputException
~~~

In this program, `good` is the UTF-8 encoding of `Café` consisting of four code points; `bad` contains byte `0xC3` without a valid UTF-8 continuation byte.

Design points:
- The caller passes the charset explicitly;
- All coding errors are handled via `REPORT`;
- Uncorrupted data can be used as text;
- Corrupted data is routed to error handling **before any replacement copy is saved**.

This helper **does not auto-detect the true charset** of bytes. If bytes were encoded in ISO-8859-1 and the caller passes ISO-8859-1, decoding succeeds yet still requires verifying the source protocol.

## 26. Business Bugs Caused by Replacement

In real systems, character loss can create failures far beyond “ugly text”:

- **Personal names/addresses**: `Nguyễn` or accented international names turn into `?` or `�`, making record matching difficult.
- **Product codes**: if special characters are dropped or replaced, two distinct codes can collapse into the same code.
- **Invoices/payments**: a lost character in payment details can complicate auditing.
- **CSV imports**: a row is accepted as valid even though a field was corrupted; downstream fixes can no longer tell the original data.
- **Search**: replacements break keyword matching or introduce meaningless new tokens.
- **Legal data**: a replaced copy is not verbatim equivalent to original evidence.
- **Security logs**: replacement or `IGNORE` can erase traces of input bytes; however, logs must not expose PII unless permitted.

When designing an import pipeline, clearly define the **acceptable data-loss boundary**. For core data, the right policy is usually **rejecting the batch or quarantining the record**, reporting the error with its location, and preserving original bytes per policy.

## 27. Beyond Charset: Distinguish Encoding, Normalization, and Rendering

There are three separate layers:

1. **Encoding/decoding:** bytes ↔ Unicode; can involve `MalformedInputException`, `UnmappableCharacterException`, and replacement.
2. **Unicode normalization:** `Normalizer` NFC/NFD/NFKC/NFKD converts to canonical/compatibility equivalents under Unicode rules, **not fixing misencoded bytes**.
3. **Rendering:** fonts, layout, Unicode bidi, and grapheme shaping determine how content looks on screen.

For example, `e` + U+0301 and `é` have different code points yet both are **valid UTF-8**. `Normalizer` handles canonical equivalence; this is not `MalformedInputException`.

Valid UTF-8 text containing rare code points can render as boxes because a font lacks glyphs; do not “change the charset” to make glyphs appear. Pick a suitable font/rendering engine.

**Never call Unicode normalization on U+FFFD to recover original characters.** Once bytes have been replaced, normalization has no knowledge of the lost bytes.

## 28. Logging and Observing Errors Without Leaking Data

When handling charset errors in servers/imports:
- Log the **declared charset**, metadata source, pipeline name, and error code.
- Log **input length, relative offset, and error count** if accurately measured and controlled.
- Retain **raw bytes** in quarantine with appropriate access controls and retention limits when legally/operationally allowed.
- In general logs, you can log a **bounded/redacted hex sample** rather than full payloads containing sensitive info.
- Distinguish **malformed**, **unmappable**, and **wrong-but-decodable charset** in metrics.

Example of a useful error message:

~~~text
Text import rejected:
declaredCharset=UTF-8
error=MalformedInputException
record=42
action=QUARANTINED
~~~

This is a message template, not stdout from a Java demo. Never log “record 42 repaired” if the decoder only detected an error or a preview substituted replacement characters.

## 29. Strategies to Prevent Data Loss in I/O

A practical checklist:

1. **Use explicit charsets** per contract, e.g., `StandardCharsets.UTF_8`, on both producer and consumer.
2. **Retain original bytes** when the source is untrusted or forensics/retries are needed.
3. **Decode strictly** with `CharsetDecoder.newDecoder()` + `REPORT` for critical content.
4. **Handle errors explicitly**: reject, quarantine, ask the producer to resend, or allow a flagged preview.
5. **Never convert malformed input into question marks** and overwrite the original content.
6. **Encode strictly** when exporting to a target charset not guaranteed to represent all characters.
7. **Do not equate “read succeeded” with “right charset”**; verify metadata/protocol.
8. **Never split bytes arbitrarily** before decoding in streaming.
9. **Compare round-trips per contract** when byte equality is required.
10. **Test with Vietnamese, emoji, surrogates, BOMs, broken UTF-8, and legacy charsets**.
11. **Separate technical error codes from user messages**; users need to know a file is invalid or must be resent, not a stack trace.
12. **Ensure upstream steps have not already replaced data** before starting strict decoding; if bytes were lost upstream, the decoder cannot recover them.

## 30. Exercises with Answers

**Question 1.** What does `MalformedInputException` indicate?

**Answer:** Input units are invalid under the structure of the active charset/encoding, such as UTF-8 with an invalid continuation byte sequence.

**Question 2.** How does `UnmappableCharacterException` differ?

**Answer:** The input is valid, yet has no valid mapping in the target charset, such as trying to encode `à` into US-ASCII.

**Question 3.** Does `new String(invalidUtf8, UTF_8)` throw a coding error by default?

**Answer:** For the `Charset` constructor, Javadoc specifies replacing malformed/unmappable sequences with the replacement string; do not use it for strict validation.

**Question 4.** Which action does `StandardCharsets.UTF_8.newDecoder()` use by default?

**Answer:** `REPORT` for both malformed and unmappable.

**Question 5.** What can `Files.readString(path, UTF_8)` throw on malformed UTF-8?

**Answer:** `IOException`, which in the demonstrated case can be `MalformedInputException`.

**Question 6.** Does `CodingErrorAction.IGNORE` preserve data?

**Answer:** No. It drops the bad segment; it can alter data and lost bytes cannot be recovered.

**Question 7.** Does having U+FFFD in a string guarantee the byte source was corrupted?

**Answer:** No; U+FFFD could have legitimately appeared as a character in the source.

**Question 8.** Does the absence of U+FFFD prove the charset was right?

**Answer:** No. Mojibake can produce entirely valid characters, or an earlier step may have replaced characters with question marks.

**Question 9.** The UTF-8 bytes of `é` are `C3 A9`; what happens if read as ISO-8859-1?

**Answer:** You get two code points `U+00C3` and `U+00A9`, typically rendered as `Ã©`, without necessarily throwing an exception.

**Question 10.** Vietnamese data was turned into question marks by `getBytes(US_ASCII)`. Can it be recovered from the output?

**Answer:** It cannot be uniquely recovered if only the replaced bytes remain. You need the original copy or trusted source data.

**Question 11.** If a UTF-8 character is split across two network reads, what should you do?

**Answer:** Maintain decoder state or buffer incomplete bytes; do not decode each chunk as terminated input.

**Question 12.** When importing critical identifier data, should you choose `REPORT` or `IGNORE`?

**Answer:** Usually choose `REPORT` and handle errors via workflow to avoid silent content loss.

## 31. Quick API Selection Table

| Need | Recommended usage | Preservation level |
| --- | --- | --- |
| Decode bytes known to be valid and accept replacement in exceptional cases | `new String(bytes, charset)` | Can lose data |
| Decode and **report all coding errors** | `charset.newDecoder().decode(ByteBuffer.wrap(bytes))` with `REPORT` | Error detection |
| Decode a small UTF-8 file and report invalid bytes | `Files.readString(path, UTF_8)` | Error detection per API contract |
| Read a byte stream with customized policy | `InputStreamReader` with `CharsetDecoder` | Depends on decoder |
| Preview a corrupted file with warnings | `CharsetDecoder` with `REPLACE` | Preview only, not lossless |
| Encode strictly to a target charset | `charset.newEncoder().encode(CharBuffer.wrap(text))` | Detects unmappable/malformed |
| Fast encode for already-valid data accepting replacement | `text.getBytes(charset)` | Can lose data |
| Read UTF-8 text yet get garbled letters | Verify source charset, inspect raw bytes | Strictness does not guarantee right charset |
| Debug original payload | Store bytes + source metadata per access policy | Enables reprocessing |

Note: the policy of a **specific API** matters more than the charset name. `UTF-8` does not guarantee reading is strict; `US_ASCII` does not guarantee writing will throw if the API chooses replacement.

## 32. Summary

**Separate three layers to prevent bugs:**

~~~text
Malformed bytes?
    → CharsetDecoder REPORT → MalformedInputException
    → REPLACE/IGNORE → data may be lost

Unencodable character?
    → CharsetEncoder REPORT → UnmappableCharacterException
    → REPLACE/IGNORE → character may be lost

Valid bytes but wrong charset chosen?
    → May throw NO exception
    → Corrupted text (mojibake)
~~~

**Five essential takeaways:**

1. `MalformedInputException` means the input sequence is **invalid** under the active charset/coder; `UnmappableCharacterException` means the input is **valid yet unmappable**.
2. `CharsetDecoder.newDecoder()` defaults to `REPORT`, whereas `new String(bytes, charset)` and some convenience APIs may **silently replace** errors.
3. `U+FFFD` is a **marker in a string that already contains a replacement character**, not a mechanism to restore lost bytes.
4. `CodingErrorAction.IGNORE` and `REPLACE` are **potentially lossy policies** that must be chosen deliberately and labeled appropriately.
5. **Right charset + appropriate error policy + retaining raw bytes when needed** produce a reliable multilingual I/O system; merely obtaining a `String` does not prove it.

**Standard Java SE 17 Documentation:**
- [MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html)
- [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).