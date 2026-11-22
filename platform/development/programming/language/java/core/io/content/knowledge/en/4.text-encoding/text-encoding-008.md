# Malformed Input, Unmappable Characters, and Error-Handling Policies in Java

In Java applications, converting text between **bytes** and **characters** does not always succeed. Two important error categories in the Java Charset API are **malformed input** (an input unit sequence that is invalid under the encoding rules) and **unmappable character** (valid input data that has no corresponding representation in the target charset). Java lets you decide whether to **report**, **replace**, or **ignore** each error category.

This lesson belongs to the **Text Encoding** section of Java I/O. The goal is to distinguish the two error types accurately, understand when they arise during encoding/decoding, configure `CharsetDecoder` / `CharsetEncoder` with `CodingErrorAction`, and choose an appropriate policy to prevent silently losing or corrupting data.

## 1. Setting the Right Boundaries: Bytes, UTF-16, and Charset

Java objects such as `String`, `char[]`, and `CharBuffer` hold **UTF-16 code units**. Meanwhile, files, sockets, or `ByteBuffer` hold **bytes**. A `Charset` defines how to transform between the two representations:

```text
DECODE:
byte[] / ByteBuffer -- CharsetDecoder (e.g., UTF-8) --> char / CharBuffer / String

ENCODE:
String / CharBuffer -- CharsetEncoder (e.g., US-ASCII) --> byte[] / ByteBuffer
```

A Java `char` is 16 bits wide. A Unicode character outside the BMP such as `😊` consists of **two UTF-16 code units** forming a surrogate pair. Charset encoders read code units and must interpret these pairs properly to produce bytes. You cannot assume every `char` is a Unicode code point, nor can you assume each code point occupies only one byte.

In Java, the core APIs are:

- `java.nio.charset.Charset`: describes a character encoding, such as `StandardCharsets.UTF_8` or `StandardCharsets.US_ASCII`.
- `CharsetDecoder`: interprets bytes into characters.
- `CharsetEncoder`: interprets characters into bytes.
- `CoderResult`: low-level result during incremental encoding/decoding; distinguishes success, underflow (missing input), overflow (insufficient space), or errors.
- `CodingErrorAction`: specifies how to handle **each error category**, consisting of `REPORT`, `REPLACE`, and `IGNORE`.
- `MalformedInputException` and `UnmappableCharacterException`: exceptions reporting the corresponding error type when using `REPORT` mode and appropriate one-shot methods.

Encodings such as UTF-8 and US-ASCII are two examples that clearly illustrate both error types, yet the handling principles apply across many other charsets.

## 2. Malformed Input: Invalid Input Data

**Malformed input** means the input bytes or UTF-16 code units **violate the structural rules** of the encoding in use. That content is not a valid encoded sequence for complete processing.

### When decoding (byte → char)

Suppose the program is decoding as UTF-8. Byte `0xC3` starts a two-byte UTF-8 sequence, yet the next byte `0x28` (`(`) is **not a valid continuation byte**. The pair `C3 28` therefore has a structural error.

Example byte sequence:

```text
43 C3 28 44
 C  ?  (  D
```

- `43` is the letter `C` in ASCII/UTF-8.
- `C3` requires a valid continuation byte yet lacks one, so this is **malformed input**.
- `28` by itself is a valid `(` character in UTF-8, and the decoder may continue processing after the damaged input depending on the algorithm, as shown in the Java example below.
- `44` is a valid letter `D`.

Other examples of malformed UTF-8 include a standalone continuation byte, overlong encoded sequences, invalid leading bytes, data ending while a multi-byte sequence is incomplete, and byte sequences encoding surrogates or code points beyond the Unicode limit.

Do not “fix” this by treating each byte as a `char` or blindly dropping bytes with the high bit set. You must analyze the exact charset and error policy.

### When encoding (char → byte)

Malformed input can also occur in an **encoder**. A UTF-16 **high surrogate** not followed by a matching low surrogate (or a standalone low surrogate) is an invalid UTF-16 sequence. For example, `"\uD83D!"` contains a lone high surrogate followed by `!`. Even when the target charset is UTF-8, the encoder cannot turn this broken UTF-16 string into valid Unicode text.

Note the distinction: the character `😊` has **two** `char`s yet is still valid when they form a properly ordered surrogate pair. Do not treat “two `char`s for one character” as an error.

## 3. Unmappable Character: Valid Input That Cannot Be Represented

**Unmappable** means the input data is valid in its source form, yet **the target encoding cannot represent that character**.

A familiar example:

- `"Café"` is a valid Java `String`.
- `US-ASCII` represents only characters with code points `U+0000..U+007F`.
- The letter `é` (U+00E9) lies outside the US-ASCII range, so encoding `"Café"` to US-ASCII encounters an **unmappable character**; it is **not** malformed UTF-16.

**A decoder can also report unmappable** if a byte sequence is structurally valid for the charset yet that charset does not map it to any character. Whether a specific byte sequence is classified as malformed or unmappable depends on **the charset rules and the encoder/decoder**, and cannot be concluded merely from a byte being “greater than 127.” In UTF-8, invalid byte sequences are typically reported as malformed.

### Comparing the two error types

| Aspect | Malformed input | Unmappable character |
|---|---|---|
| Nature | Input violates the **syntax/structure** of the representation | Input is **valid**, yet has no mapping to the target representation |
| Decoder example | UTF-8 `C3 28` | Structurally valid byte sequence with no mapping to Unicode in a specific charset |
| Encoder example | Lone UTF-16 high surrogate when converting to UTF-8 | `é` when converting from Java text to US-ASCII |
| Result under `REPORT` | `MalformedInputException` | `UnmappableCharacterException` |
| Configuration method | `onMalformedInput(...)` | `onUnmappableCharacter(...)` |
| Risk if replaced/ignored | Masks corrupted input bytes | Loses original characters when converting to an unsupported encoding |

Do not use `UnmappableCharacterException` as a generic name for all “Unicode errors,” nor use `MalformedInputException` to refer to a font failing to render an emoji. **Missing glyphs in a font** is a display issue, distinct from whether charset encoding/decoding succeeded.

## 4. Three Handling Policies: REPORT, REPLACE, IGNORE

`java.nio.charset.CodingErrorAction` defines three options configured separately for **malformed** and **unmappable**:

| Policy | Behavior | Consequence |
|---|---|---|
| `REPORT` | Reports an error to the caller; in typical one-shot encode/decode, throws the corresponding `CharacterCodingException` | Detects bad data and keeps the caller in control of handling |
| `REPLACE` | Replaces the offending input sequence with the configured replacement string or bytes | Allows continuing yet can **lose original information** |
| `IGNORE` | Drops the offending input portion and continues with the remainder | Easily causes **silent data loss** and alters content |

**The default for a newly created `CharsetDecoder` and `CharsetEncoder` is `REPORT` for both error types.** However, convenience wrapper APIs around charsets may default to **replacement**. Therefore, check the contract of the API you are calling; do not assume every conversion path shares the same policy.

Configure via:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

This is an **illustrative snippet**, placed in a class that imports `java.nio.charset.*` or the required types. The two configurations are **independent**. For instance, you can `REPORT` malformed input while using `REPLACE` for unmappable characters when exporting to a legacy charset, if business requirements dictate so. Still, any replacement or dropping of data should be clearly explained to users or logged/flagged when integrity matters.

### What does REPLACE actually substitute?

- `CharsetDecoder` normally uses the Unicode replacement character `U+FFFD` (displayed as `�`). You can change the replacement string with `decoder.replaceWith("...")` if valid within the decoder's limits.
- `CharsetEncoder` substitutes one or more **bytes**; `US_ASCII.newEncoder()` normally uses the `?` byte (`0x3F`) as the replacement. You can configure `encoder.replaceWith(byte[])`, provided the replacement bytes are accepted by the charset per the encoder's contract.
- Seeing `?` or `�` in output **does not prove** exactly what the original corrupted data was: that character may also have existed natively in the original content.

After replacement, **you cannot automatically recover** lost bytes or characters from the output alone. `IGNORE` is even riskier because it leaves no trace of the erroneous portion at all.

## 5. Example 1 — Malformed UTF-8 Under All Three Policies

Create file `MalformedUtf8Demo.java` (Java 17+):

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf8Demo {
    private static String decode(byte[] bytes, CodingErrorAction action)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = {'C', (byte) 0xC3, '(', 'D'};
        try {
            decode(bytes, CodingErrorAction.REPORT);
        } catch (CharacterCodingException e) {
            System.out.println("REPORT=" + e.getClass().getSimpleName());
        }
        String replaced = decode(bytes, CodingErrorAction.REPLACE);
        System.out.println("REPLACE=" + replaced.replace("\uFFFD", "<U+FFFD>"));
        System.out.println("IGNORE=" + decode(bytes, CodingErrorAction.IGNORE));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 MalformedUtf8Demo.java
java MalformedUtf8Demo
```

Verified output:

```text
REPORT=MalformedInputException
REPLACE=C<U+FFFD>(D
IGNORE=C(D
```

Here `C3` is the problematic byte. With `REPORT`, `CharsetDecoder.decode(ByteBuffer)` throws `MalformedInputException`, a subclass of `CharacterCodingException`. With `REPLACE`, the malformed part is replaced by `U+FFFD`; the code **only converts `U+FFFD` to the string `<U+FFFD>` when printing** so the output does not depend on terminal fonts. With `IGNORE`, the malformed part is dropped from the output.

In a different dataset, how many bytes are considered part of one error and how the decoder recovers afterward depend on the specific charset/sequence. Do not generalize a rule of “skipping exactly one byte” from this example.

A decoder is stateful; each independent pass in the example calls `newDecoder()` so state is not reused after an error or after decoding finishes.

## 6. Example 2 — Unmappable US-ASCII and Broken Surrogate

Create file `EncoderActionsDemo.java` (Java 17+):

```java
import java.nio.CharBuffer;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class EncoderActionsDemo {
    private static String ascii(String input, CodingErrorAction action)
            throws CharacterCodingException {
        CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);
        ByteBuffer bytes = encoder.encode(CharBuffer.wrap(input));
        byte[] result = new byte[bytes.remaining()];
        bytes.get(result);
        return new String(result, StandardCharsets.US_ASCII);
    }

    public static void main(String[] args) throws Exception {
        String text = "Caf\u00E9";
        try {
            ascii(text, CodingErrorAction.REPORT);
        } catch (CharacterCodingException e) {
            System.out.println("ASCII REPORT=" + e.getClass().getSimpleName());
        }
        System.out.println("ASCII REPLACE=" + ascii(text, CodingErrorAction.REPLACE));
        System.out.println("ASCII IGNORE=" + ascii(text, CodingErrorAction.IGNORE));

        String broken = "\uD83D!";
        try {
            StandardCharsets.UTF_8.newEncoder()
                    .encode(CharBuffer.wrap(broken));
        } catch (CharacterCodingException e) {
            System.out.println("UTF-8 broken surrogate=" + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EncoderActionsDemo.java
java EncoderActionsDemo
```

```text
ASCII REPORT=UnmappableCharacterException
ASCII REPLACE=Caf?
ASCII IGNORE=Caf
UTF-8 broken surrogate=MalformedInputException
```

For `"Café"`, `é` is valid Unicode yet US-ASCII has no representation, so `REPORT` throws `UnmappableCharacterException`. In this Java US-ASCII encoder, `REPLACE` uses the `?` byte; `IGNORE` drops `é` from the output. Turning `"Café"` into `"Caf?"` or `"Caf"` is clearly a **lossy transformation**.

The variable `broken` contains the high surrogate `\uD83D` without a matching low surrogate. That is **malformed input for the encoder**, even when the target charset is UTF-8, which can represent every valid Unicode scalar value. You cannot “fix” this bug merely by switching the target encoding from ASCII to UTF-8.

**Source code note:** Java compiles the escape `\u00E9` into `é`, while `\uD83D` intentionally creates a lone high surrogate to demonstrate broken UTF-16 data; do not inject `broken` into live data flows and treat it as valid text.

## 7. Example 3 — Error Policy Varies by Reader API

A common misconception: observing that `CharsetDecoder.newDecoder()` defaults to `REPORT`, and inferring that every `Reader` using UTF-8 also reports errors by default. **That is not true for every constructor.**

Create file `ReaderPolicyDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.io.StringWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;

public class ReaderPolicyDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {'A', (byte) 0xC3, '(', 'B'};
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            StringWriter output = new StringWriter();
            reader.transferTo(output);
            System.out.println("simple reader="
                    + output.toString().replace("\uFFFD", "<U+FFFD>"));
        }

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT))) {
            reader.transferTo(new StringWriter());
        } catch (MalformedInputException e) {
            System.out.println("strict reader=" + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ReaderPolicyDemo.java
java ReaderPolicyDemo
```

```text
simple reader=A<U+FFFD>(B
strict reader=MalformedInputException
```

Both blocks read **the exact same byte sequence**. The `InputStreamReader(InputStream, Charset)` constructor handles malformed/unmappable input by replacing; the `InputStreamReader(InputStream, CharsetDecoder)` constructor uses the **caller-configured decoder**, so `REPORT` is preserved and the exception surfaces **during reading**, specifically inside `transferTo`.

If an application must *fail reading a file immediately upon invalid text*, choose a read path/configuration with `REPORT`. If the application is a file viewer intentionally permitting replacement characters, `REPLACE` may make sense. Do not let a convenience constructor inadvertently dictate the integrity policy for critical data.

With `InputStreamReader`, closing the `Reader` also closes the underlying `InputStream`. Transcoding errors may be thrown inside the read loop or at the end of reading, not necessarily at reader construction time.

## 8. Some “Convenience” APIs Have Different Defaults

| API or Call Pattern | Policy / What to Check |
|---|---|
| `charset.newDecoder().decode(buffer)` | New decoder defaults to `REPORT` for malformed and unmappable; can be changed before decoding |
| `charset.newEncoder().encode(buffer)` | New encoder defaults to `REPORT` for both error types; each can be configured |
| `new String(bytes, charset)` | Java API replaces malformed/unmappable byte sequences with replacement characters; do not use when all errors must be detected |
| `string.getBytes(charset)` | Java API replaces unencodable character sequences with replacement bytes; not a strict error-reporting path |
| `new InputStreamReader(input, charset)` | Handles malformed/unmappable input via replacement |
| `new InputStreamReader(input, decoder)` | Preserves the policy of the passed `CharsetDecoder` |
| `new OutputStreamWriter(output, charset)` | Handles malformed/unmappable input via replacement |
| `new OutputStreamWriter(output, encoder)` | Preserves the policy of the passed `CharsetEncoder` |

**Do not confuse “finished writing” with “data was written accurately.”** For instance, `text.getBytes(StandardCharsets.US_ASCII)` can finish successfully with a `?` byte replacing `é`. To guarantee lossless conversion across encodings, use a strict encoder/decoder or validate input/representability explicitly.

For `Files.newBufferedReader(path, charset)`, `Files.readString(path, charset)`, and other high-level file APIs, read the malformed/unmappable contract of **that specific method**. When the policy must be tightly controlled, using `InputStreamReader` with an explicitly configured `CharsetDecoder` makes the intent unmistakable.

## 9. Explicit REPLACE Configuration and Choosing Replacement Characters

To make a decoder use `?` instead of `U+FFFD` for malformed errors (when configuration allows):

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .replaceWith("?");
```

This is **illustrative code**: import `CharsetDecoder`, `CodingErrorAction`, and `StandardCharsets`. The decoder's replacement string must obey the length constraint of `maxCharsPerByte()`; you cannot pass an arbitrarily long string. It is inserted into the **output character stream**, not bytes.

For a US-ASCII encoder, you can instruct it to replace unmappable characters with the byte representing `?`:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith(new byte[] {(byte) '?'});
```

This is also **illustrative code**, requiring imports for `CharsetEncoder`, `CodingErrorAction`, and `StandardCharsets`. The replacement array must be valid for the charset and within size limits. In practice, you might set `REPLACE` for unmappable characters yet `REPORT` for malformed input to avoid ignoring broken Unicode structure while supporting transcoding under an agreed lossy policy.

**Warning:** Using `?` as the replacement makes it impossible to distinguish genuine question marks that were already in the text from question marks caused by transcoding errors. Do not write an algorithm that “counts `?` characters to find the error count” without additional metadata.

## 10. When to Choose Which Policy?

### REPORT — preferred when data integrity is required

Choose **`REPORT`** for situations where bad data must be detected and handled:

- Config files, primary archival data, and packets under protocols mandating strict UTF-8.
- Identifiers, field names, signature codes, lookup keys, or content where altering one character changes meaning.
- Data ingestion pipelines that must report data quality, log errors, and allow reprocessing from the **original bytes**.
- When converting to a target charset unable to represent the text, the caller must decide to use UTF-8, reject the operation, or apply an approved transformation.

Catch `MalformedInputException` and `UnmappableCharacterException` at the boundary where the program has context to handle them. The exception carries the **length of the erroneous segment** via `inputLength()`; it does not itself provide the full file path, absolute byte offset, or original bytes. Attach context safely from the source owned by the application.

For incremental processing, `CharsetDecoder.decode(input, output, endOfInput)` can return `CoderResult.malformedForLength(n)` or `unmappableForLength(n)` instead of throwing directly; the caller must inspect the result and may call `throwException()` if strict behavior is desired. `CoderResult.UNDERFLOW`/`OVERFLOW` are buffer operational states, **not inherently data errors**.

### REPLACE — suitable when continuing matters and loss is acceptable

Choose **`REPLACE`** when tolerantly displaying corrupted content is more valuable than halting completely, such as a damaged-log viewer or an exploratory tool for foreign text. In that case, document clearly:

- The source charset and how it was detected/declared.
- The replacement character/byte, and the replaced positions if the system needs traceability.
- That the original data source is retained if error analysis is needed.
- That the output is only a **policy-sanitized presentation**, not guaranteed equal to the original data.

Do not silently use `REPLACE` before computing hashes, signing data, or comparing identifiers where exact bytes/characters are essential.

### IGNORE — use only when intentionally dropping bad data

`IGNORE` deletes the offending input segment. It can turn `"Café"` into `"Caf"` or strip bad bytes between two valid segments, merging words or identifiers that were originally separate. Use it only when business requirements **accept deletion**, proper monitoring is in place, and the impact has been evaluated. If the goal is “keep reading without hiding errors,” `REPLACE` with a warning is usually easier to diagnose.

**No single policy is always optimal.** Base the decision on the data contract and risk of loss, not on whether one option throws an exception.

## 11. Streaming Data and Errors at Buffer Boundaries

When reading via `InputStreamReader`, `Reader`, or NIO buffers, transcoding errors often appear only **during actual reading/writing**. When a multi-byte UTF-8 sequence is split across two chunks, the decoder must retain state to wait for the next chunk. **Missing bytes at the end of a chunk are not necessarily malformed**, unless **end of input** has been signaled while the sequence remains incomplete.

If calling the incremental version of `CharsetDecoder` directly, follow this state sequence:

1. Prepare `ByteBuffer` and `CharBuffer`; call `decode(input, output, false)` while more input remains.
2. On `UNDERFLOW`, check whether more bytes are needed or input has ended; `OVERFLOW` means the output buffer needs more space.
3. When no more bytes remain, call `decode(input, output, true)` so the decoder confirms termination; trailing incomplete data may now be reported as malformed.
4. Complete `flush(output)` and handle the result. Call `reset()` before a new content stream if reusing the decoder under valid state rules.
5. If using `REPORT`, check `CoderResult.isError()` and handle/report the error; do not ignore the result and proceed as if decoding succeeded.

The workflow above is a **mechanism description, not a complete program**. For ordinary text reading, `InputStreamReader`/`BufferedReader` with a preconfigured decoder avoids managing coder state manually. If writing a custom chunk processor, never create a fresh decoder for **each** arbitrary byte chunk: a valid sequence split across two chunks would be falsely flagged as malformed.

Another example: a high surrogate at the end of one `CharBuffer` and a low surrogate in the next buffer can be valid when encoded in the same session. Do not treat each `CharBuffer` as an independent string if you want to preserve Unicode across buffer boundaries.

## 12. Error Recording, Recovery, and Data Quality Checks

A reliable text ingestion pipeline should be able to answer:

1. **What is the charset?** The charset is part of the file/protocol contract; do not assign UTF-8 or Windows-1252 merely because the bytes look “readable.”
2. **Is the original byte source preserved?** If only text after `REPLACE`/`IGNORE` is kept, old data cannot be recovered accurately.
3. **Is the error type distinguished?** `MalformedInputException` indicates invalid input structure; `UnmappableCharacterException` indicates a missing mapping. In UI/logs, record the error type and operation (encode vs. decode).
4. **Who controls the policy?** Convenience reader/writer classes may replace data implicitly. When strictness matters, pass an explicitly configured `CharsetDecoder` / `CharsetEncoder`.
5. **Can the same bytes be reprocessed after an error?** Data saved in memory or a file can be reprocessed with a new decoder or a controlled retry pipeline; never reuse a coder left in an invalid state.
6. **Is round-trip verification performed?** With a limited charset, encode followed by decode may not return the original text if replacement occurred. When losslessness matters, verify charset suitability and use `REPORT` before saving.

### A real-world scenario

A system exports customer data to US-ASCII while names contain diacritics. If `getBytes(US_ASCII)` silently replaces `é` with `?`, stored names can become permanently corrupted without any error reported. Better approaches are:

- If the target format accepts UTF-8, **choose UTF-8** and declare the charset explicitly.
- If the format strictly requires US-ASCII, encode using a `CharsetEncoder` with `REPORT`; notify users of unexportable fields or apply an approved and tested transliteration rule.
- Use `REPLACE`/`IGNORE` only when the export contract permits character loss.

**Transliteration** such as turning `"é"` into `"e"` is a language-specific transformation rule, **not synonymous** with `CodingErrorAction.REPLACE` and not built into the ASCII charset.

## 13. Common Pitfalls

1. **Confusing malformed and unmappable.** `C3 28` is malformed UTF-8; `é` in Java text converted to US-ASCII is unmappable.
2. **Assuming UTF-8 handles every `String`.** UTF-8 encodes Unicode scalar values; a `String` can contain lone UTF-16 surrogates, which are malformed.
3. **Ignoring the charset.** The same bytes can be valid in one charset and invalid in another. Error analysis always depends on the actual charset.
4. **Assuming `newDecoder()` and `new String(bytes, charset)` handle errors identically.** A new decoder defaults to `REPORT`; this `String` constructor replaces bad data.
5. **Using `IGNORE` to “fix encoding errors.”** It drops data rather than restoring original bytes or fixing the charset.
6. **Treating replacement as lossless.** A `?` or `U+FFFD` is insufficient to reconstruct what was replaced.
7. **Forgetting to handle errors during reading/writing.** Strict configuration may throw exceptions inside the I/O loop or at completion, not at constructor time.
8. **Creating a new decoder on every chunk.** Multi-byte sequences spanning a chunk boundary will appear spuriously broken. Use a single stateful decoder across continuous data.
9. **Ignoring `CoderResult`.** In incremental APIs, `UNDERFLOW`/`OVERFLOW` must be handled properly, and `isError()` needs explicit handling.
10. **Logging raw sensitive data while investigating errors.** Log error type, position/range, and necessary metadata; avoid exposing source bytes if they may contain private data.
11. **Mistaking a font problem for a charset problem.** Properly decoded data can still display boxes if the font lacks glyphs; that belongs to the rendering layer.
12. **Using a legacy charset instead of confirming requirements.** When Vietnamese and emojis must be preserved, UTF-8 is usually the right choice; choose a restricted charset only when required by a protocol/system.

## 14. Self-Check

**Question 1.** A UTF-8 decoder encounters bytes `E2 82` and then input ends. Which error type applies?  
**Answer:** Malformed, because a three-byte UTF-8 sequence is missing its final byte at actual EOF. If it is only the end of a *chunk* with more bytes in the next chunk, the coder must wait for additional data.

**Question 2.** A US-ASCII encoder encounters the valid string `"Hòa"`. Which error type occurs at the accented letter?  
**Answer:** Unmappable. It is not broken Unicode; the US-ASCII charset simply cannot represent that code point.

**Question 3.** How does `REPORT` differ from `REPLACE`?  
**Answer:** `REPORT` surfaces the error to the caller, whereas `REPLACE` inserts a substitute character/byte and continues, usually losing the ability to recover original data.

**Question 4.** An application reads a file with `new String(bytes, UTF_8)` and gets no exception. Does that guarantee the file contains valid UTF-8?  
**Answer:** No. That API replaces invalid sequences; a strict decoder is needed to verify validity.

**Question 5.** A file contains important names; can you strip bad bytes with `IGNORE` before saving?  
**Answer:** You should not. If the data contract demands accuracy, use `REPORT` to handle it at the source or request corrected data.

**Question 6.** When can `InputStreamReader(input, UTF_8.newDecoder().onMalformedInput(REPORT))` throw an error?  
**Answer:** When a read operation actually asks the decoder to process the malformed bytes, such as during `read()` or `transferTo()`.

## Conclusion

**Malformed input** is input data with **invalid encoding structure**; an **unmappable character** is valid data that **has no mapping in the target charset**. Java separates the two categories to allow independent configuration via `onMalformedInput(...)` and `onUnmappableCharacter(...)`. Choose `REPORT` when integrity and detecting bad data are required; `REPLACE` when continuing/displaying with accepted loss is intentional; and `IGNORE` only when deletion is explicitly specified. You must also understand the contract of the high-level API in use, because `CharsetEncoder`/`CharsetDecoder` and convenience constructors do not necessarily share the same defaults.

### Java SE 17 Documentation

- [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [`CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [`CoderResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [`MalformedInputException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html), [`UnmappableCharacterException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)