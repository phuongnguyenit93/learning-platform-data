# CharsetDecoder, CharsetEncoder, and CodingErrorAction in Java

## 1. Why Is Knowing UTF-8 Still Not Enough?

When a Java application reads a file, receives an HTTP payload, or ingests data from a legacy system, character strings must cross an **encoding boundary**:

- **Read:** bytes from a file/network → Unicode characters in Java.
- **Write:** Unicode characters from Java → bytes of a charset for sending/storage.

When the data is valid, conversion seems straightforward. Yet real-world data can contain **truncated bytes**, **invalid UTF-8 sequences**, **Unicode characters unrepresentable in the target charset**, or **split UTF-16 surrogate pairs**. When encountering such cases, the application must decide whether to **report an error, replace characters, or drop data**.

Java 17 provides a clearly configurable set of APIs:

- `CharsetDecoder`: converts **bytes → chars** according to a `Charset`.
- `CharsetEncoder`: converts **chars → bytes** according to a `Charset`.
- `CodingErrorAction`: chooses the error policy, with three options: `REPORT`, `REPLACE`, `IGNORE`.
- `CoderResult`: describes status during incremental conversion, including `UNDERFLOW`, `OVERFLOW`, `MALFORMED`, and `UNMAPPABLE`.

This lesson focuses on Java 17+, real-world I/O scenarios, and **internationalized data integrity**. The goal is not merely “fixing Vietnamese diacritic bugs,” but **never silently corrupting text** when the input or output charset does not fit.

## 2. Data Flow Diagram and Role of Each API

```text
File / Network / Legacy System                Java Application
        BYTES                                        Unicode
  54 69 E1 BA BF 6E 67      decode UTF-8     "Tiếng"
             -------------------------------> String/CharBuffer
             <-------------------------------
                 encode UTF-8                UTF-8 bytes

ByteBuffer          CharsetDecoder          CharBuffer / String
CharBuffer / String CharsetEncoder          ByteBuffer
```

Terminology:

| Concept | Type/API | Meaning |
| --- | --- | --- |
| Charset | `java.nio.charset.Charset` | Rules mapping bytes to Unicode text |
| Decoder | `CharsetDecoder` | Stateful decoder for a specific charset |
| Encoder | `CharsetEncoder` | Stateful encoder for a specific charset |
| Byte buffer | `ByteBuffer` | Memory holding source/target bytes, with `position/limit` |
| Character buffer | `CharBuffer` | Memory holding UTF-16 `char` code units |
| Error action | `CodingErrorAction` | Action when encountering malformed/unmappable data |
| Conversion result | `CoderResult` | UNDERFLOW, OVERFLOW, or error kind |
| Standard charsets | `StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1` | Built-in, standardly supported charsets |
| Unicode replacement | `U+FFFD` | Character commonly used to replace undecodable data |

`CharsetDecoder` and `CharsetEncoder` can be created from a `Charset`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder();
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder();
```

These two lines are illustrative code **inside a method**, requiring imports from `java.nio.charset`. Each instance holds state for one conversion; **do not share a single encoder/decoder across concurrent requests**.

### Very Important Point

`CharsetDecoder` is not a “language detector” and `CharsetEncoder` is not a “language translator.” UTF-8 is a **character encoding**, not Vietnamese/English/Japanese. Locale and charset are two distinct aspects of localization.

`Charset.forName("UTF-8")` or `StandardCharsets.UTF_8` describe the same standard charset. When UTF-8 is known upfront, `StandardCharsets.UTF_8` avoids typos in charset names and makes code clearer.

## 3. Two Error Kinds: Malformed and Unmappable

Java distinguishes two main errors during conversion.

### 3.1. Malformed Input

The input data is **structurally invalid** under the declared encoding.

For example, when decoding UTF-8:

- Byte `0xC3` requires a suitable following byte to form a two-byte UTF-8 sequence.
- If it precedes `0x28` (the ASCII `(` character), the sequence `C3 28` is not a valid UTF-8 byte sequence.
- If the stream ends immediately after `0xC3`, the input is missing its trailing byte, which also becomes malformed once end-of-input is confirmed.

For example, when encoding from a Java `String`: a lone UTF-16 **high surrogate** such as `"\uD83D"` does not represent a complete Unicode scalar value. It is **malformed UTF-16 input** to the encoder.

### 3.2. Unmappable Character

The input may be **structurally valid**, yet **the target charset has no byte sequence representing that character**.

For example:

- The Java string `"A€B"` is valid Unicode.
- The `ISO-8859-1` charset does not represent the `€` character (U+20AC).
- When encoding to ISO-8859-1, `€` is **unmappable**.
- Encoding the same string to UTF-8 represents `€` normally.

Some charsets can also report **unmappable** when decoding a structurally valid byte sequence that has no mapping to a Unicode character. Do not assume **all** decoder errors are malformed or **all** encoder errors are unmappable.

| Scenario | Direction | Typical kind |
| --- | --- | --- |
| Bytes `C3 28` when reading UTF-8 | Decode | Malformed |
| Byte `C3` at end of UTF-8 stream | Decode | Malformed when end-of-input is signaled |
| `"A€B"` converted to ISO-8859-1 | Encode | Unmappable |
| String containing a lone high surrogate converted to UTF-8 | Encode | Malformed |
| `"Tiếng Việt"` converted to UTF-8 | Encode | Valid |
| `"A€B"` converted to UTF-8 | Encode | Valid |

**Do not resolve a wrong charset by suppressing errors.** For instance, if a file actually uses Windows-1258 yet is read as UTF-8, `REPLACE` can produce `�` and lose information. The right action is identifying the source charset from trusted metadata and decoding again properly.

## 4. CodingErrorAction: REPORT, REPLACE, IGNORE

`java.nio.charset.CodingErrorAction` has three constants:

| Action | When encountering bad data | Trade-off |
| --- | --- | --- |
| `REPORT` | Reports error to caller via `CoderResult` or throws `CharacterCodingException` | Preserves the principle of never silently losing data |
| `REPLACE` | Discards bad input segment, writes replacement value to output, and continues | Pipeline keeps running, **but original data is lost** |
| `IGNORE` | Discards bad input segment, **writes no replacement character/byte** | Data loss, hard to tell where data was deleted |

Configure **independently** for the two error types:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
```

All of these are **method-body snippets** with appropriate imports.

**Per the Java SE 17 API, newly created encoders/decoders default to `REPORT` for both malformed and unmappable.** Explicitly configuring both as `REPORT` is still helpful to express policy in code and avoid confusion with convenience APIs that may apply replacement.

### 4.1. Default Differences Are Easy to Misread

These two decoding approaches can behave differently on errors:

```java
// Convenience String API may use a replacement character:
String convenient = new String(bytes, StandardCharsets.UTF_8);

// New decoder, defaults to REPORT:
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder();
CharBuffer decoded = strict.decode(ByteBuffer.wrap(bytes));
```

On malformed UTF-8 input, `new String(byte[], Charset)` replaces malformed/unmappable byte sequences with the charset's default replacement string, whereas `CharsetDecoder.decode(ByteBuffer)` with `REPORT` throws the appropriate `CharacterCodingException`. **Do not assume all Java APIs share the same error behavior merely because they use UTF-8.**

Similarly, `String.getBytes(Charset)` can emit replacement bytes for unrepresentable characters. When you must detect data-loss errors, use a `CharsetEncoder` configured with `REPORT`.

## 5. CharsetDecoder: Reading Invalid Bytes in a Controlled Way

Below is a standalone Java 17 example for the same byte sequence:

```text
41 C3 28 42

41 = 'A'
C3 = leading byte of a two-byte UTF-8 sequence, fails upon encountering 28
28 = '('
42 = 'B'
```

### Program 1 — Three Policies When Decoding

Save the file `DecoderActionsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public class DecoderActionsDemo {

    private static final byte[] BYTES = {
            0x41, (byte) 0xC3, 0x28, 0x42
    };

    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static String decode(CodingErrorAction action)
            throws CharacterCodingException {

        CharBuffer chars = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .decode(ByteBuffer.wrap(BYTES));

        return chars.toString();
    }

    public static void main(String[] args) throws Exception {
        try {
            decode(CodingErrorAction.REPORT);
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        String replaced = decode(CodingErrorAction.REPLACE);
        String ignored = decode(CodingErrorAction.IGNORE);

        System.out.println("REPLACE=" + codePoints(replaced));
        System.out.println("IGNORE=" + codePoints(ignored));
        System.out.println("convenience=" + codePoints(
                new String(BYTES, StandardCharsets.UTF_8)));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 DecoderActionsDemo.java
java DecoderActionsDemo
```

Deterministic stdout:

```text
REPORT=error
REPLACE=U+0041 U+FFFD U+0028 U+0042
IGNORE=U+0041 U+0028 U+0042
convenience=U+0041 U+FFFD U+0028 U+0042
```

Explanation:

- `REPORT` stops and throws an error with the `decode(ByteBuffer)` API.
- `REPLACE` inserts a `U+FFFD` character for the detected malformed input, then continues reading `(` and `B`.
- `IGNORE` drops the invalid byte, so the output becomes `A(B`.
- The `new String(BYTES, UTF_8)` constructor also applies replacement for corrupted data.

**A warning:** output `A�(B` does not confirm that the original text was recovered. The corrupted byte's information is already gone. In domains requiring data precision, choose `REPORT` and handle the file/network protocol properly.

### 5.1. Customizing Decoder Replacement

The default decoder replacement string is `"\uFFFD"`, though it can be changed:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("[invalid]");
```

This is illustrative code inside a method. `replaceWith(String)` requires the replacement string to be **non-null, non-empty, and no longer than the decoder's `maxCharsPerByte()`**. For UTF-8, `maxCharsPerByte()` is typically 1; therefore **a long replacement string like `"[invalid]"` is disallowed** and throws `IllegalArgumentException`. To avoid errors, use a single-character replacement such as `"?"` or `"\uFFFD"` for a UTF-8 decoder.

**Example valid configuration for UTF-8**:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");
```

When using a visible replacement such as `?`, you must still record that original data was replaced. Do not use a question-mark replacement in data contracts where it could be confused with genuine user question marks.

## 6. CharsetEncoder: Valid Character Unsupported by Target Charset

With Unicode `"A€B"`, UTF-8 can represent all of it. However, `ISO-8859-1` lacks the euro sign. When encoding to ISO-8859-1:

- `REPORT`: throws `UnmappableCharacterException` via the one-shot API.
- `REPLACE`: writes the replacement byte (typically `?`); you can configure `!` to recognize the output unmistakably.
- `IGNORE`: drops `€`, emitting only `AB`.

### Program 2 — ISO-8859-1 Encoding and Unmappable Errors

File `EncoderActionsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class EncoderActionsDemo {

    static String hex(ByteBuffer bytes) {
        StringBuilder result = new StringBuilder();
        while (bytes.hasRemaining()) {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format(
                    Locale.ROOT, "%02X",
                    Byte.toUnsignedInt(bytes.get())));
        }
        return result.toString();
    }

    static ByteBuffer encode(
            String text, CodingErrorAction action)
            throws CharacterCodingException {

        CharsetEncoder encoder = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .replaceWith(new byte[]{0x21}); // 0x21 = '!'

        return encoder.encode(CharBuffer.wrap(text));
    }

    public static void main(String[] args) throws Exception {
        String text = "A\u20ACB"; // A€B

        try {
            encode(text, CodingErrorAction.REPORT);
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        System.out.println("REPLACE=" +
                hex(encode(text, CodingErrorAction.REPLACE)));
        System.out.println("IGNORE=" +
                hex(encode(text, CodingErrorAction.IGNORE)));

        System.out.println("UTF8=" + hex(
                StandardCharsets.UTF_8.newEncoder()
                        .encode(CharBuffer.wrap(text))));
    }
}
```

```bash
javac -encoding UTF-8 EncoderActionsDemo.java
java EncoderActionsDemo
```

Deterministic stdout:

```text
REPORT=error
REPLACE=41 21 42
IGNORE=41 42
UTF8=41 E2 82 AC 42
```

`41 21 42` is `A!B`; `!` is simply the developer-configured replacement, **not the euro sign**. `41 E2 82 AC 42` is the valid UTF-8 representation of `A€B`.

**Remember:** valid input that the output charset cannot represent is still an **UNMAPPABLE** error, not a malformed error. If preserving multiple international scripts is required, use UTF-8 whenever the protocol permits, rather than forcing multilingual text into an encoding covering only a subset of Unicode.

### 6.1. Encoder Replacement Differs from Decoder Replacement

| Coder | Replacement API | Replacement unit |
| --- | --- | --- |
| Decoder | `CharsetDecoder.replaceWith(String)` | **`char` string** (Unicode characters) |
| Encoder | `CharsetEncoder.replaceWith(byte[])` | **Byte array** valid in the target charset |

The encoder does not accept `replaceWith("€")`; it requires **`byte[]`**. The replacement bytes must form a **valid** byte sequence in that charset, non-null/non-empty, and within `maxBytesPerChar()`. Do not pick an arbitrary byte when a charset is multi-byte or stateful; use the default replacement or verify encodability.

### 6.2. Can canEncode Replace Actual Encoding?

`CharsetEncoder.canEncode(char)` or `canEncode(CharSequence)` helps check whether a coder can represent a sequence. Yet it is not an error-handling mechanism replacing real encoding:

- Coders are stateful, and some encodings have special modes/restrictions.
- `canEncode` does not replace validating input content.
- The conversion policy must still handle `CharacterCodingException` under `REPORT`.
- For non-BMP Unicode, check the full string/surrogate pair rather than testing a lone high or low `char`.

Do not call `canEncode` per `charAt(i)` and conclude a two-code-unit emoji is two invalid characters; handle the full Unicode string or code points properly.

## 7. Malformed UTF-16 in String and Impact on the Encoder

A Java `char` is a **UTF-16 code unit**. A non-BMP character such as `😀` (U+1F600) is the pair `\uD83D\uDE00`:

```text
High surrogate = U+D83D
Low surrogate  = U+DE00
Full code point = U+1F600

Valid pair     : D83D DE00 → valid representation
Lone high      : D83D      → malformed UTF-16
Lone low       : DE00      → malformed UTF-16
```

A Java `String` can hold an unpaired surrogate `char`; it does not necessarily throw an error when constructed. **Encoding** is one of the boundaries that detects invalid input.

### Program 3 — Encoder Distinguishes Malformed Input

File `MalformedUtf16EncoderDemo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf16EncoderDemo {
    public static void main(String[] args) throws Exception {
        String validEmoji = "\uD83D\uDE00";
        String loneHigh = "\uD83D";

        byte[] utf8Valid = validEmoji.getBytes(
                StandardCharsets.UTF_8);

        System.out.println("validUtf8Bytes=" +
                utf8Valid.length);

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(loneHigh));
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        int remaining = StandardCharsets.UTF_8
                .newEncoder()
                .onMalformedInput(CodingErrorAction.IGNORE)
                .encode(CharBuffer.wrap(loneHigh))
                .remaining();

        System.out.println("IGNOREbytes=" + remaining);
        System.out.println("inputUnits=" + loneHigh.length());
    }
}
```

```bash
javac -encoding UTF-8 MalformedUtf16EncoderDemo.java
java MalformedUtf16EncoderDemo
```

Deterministic stdout:

```text
validUtf8Bytes=4
REPORT=error
IGNOREbytes=0
inputUnits=1
```

Although `loneHigh` has length 1, it is not a complete Unicode scalar value. `IGNORE` producing 0 bytes does not “fix” the string: the data was **dropped**.

### 7.1. Do Not Split Across a Surrogate Pair When Chunking Buffers

If a first stream/chunk ends with a **high surrogate** and the next chunk begins with a **low surrogate**, when processing with the same `CharsetEncoder` in incremental mode, you must **retain the incomplete code unit** to combine with the next part rather than treating it as malformed immediately.

Conversely, if encode is called with `endOfInput=true` and only a lone high surrogate remains, the coder can report malformed input.

This parallels a UTF-8 decoder when a byte sequence is split across two network packets: it is not an error merely because the **current packet** ends mid-character; an error arises once end-of-input is reached or invalid bytes are encountered.

## 8. Streaming and CoderResult States

For large streams or protocols where data arrives incrementally, an application does not necessarily have the entire input in a single buffer. Both decoder and encoder provide incremental APIs:

```java
CoderResult decoderResult = decoder.decode(
        ByteBuffer input,
        CharBuffer output,
        boolean endOfInput);

CoderResult encoderResult = encoder.encode(
        CharBuffer input,
        ByteBuffer output,
        boolean endOfInput);
```

These are **illustrative signatures**; in Java code, provide declared variables of the appropriate types. These methods take `endOfInput`, after which `flush` must typically be called to complete an operation.

`CoderResult` has four primary states:

| Result | Check method | Meaning | Typical handling |
| --- | --- | --- | --- |
| `UNDERFLOW` | `isUnderflow()` | Current input exhausted or insufficient input to form next unit | Feed more input; if truly finished, end operation |
| `OVERFLOW` | `isOverflow()` | Output buffer lacks space | Drain/read output, then retry |
| `MALFORMED` | `isMalformed()` | Input data is structurally invalid | REPORT/REPLACE/IGNORE per policy |
| `UNMAPPABLE` | `isUnmappable()` | Valid input cannot be mapped | REPORT/REPLACE/IGNORE per policy |

**UNDERFLOW does not mean an error.** For UTF-8, `0xC3` is not yet enough to determine a complete code point. With `endOfInput=false`, the decoder can return `UNDERFLOW` and leave the byte waiting for the rest; if the stream truly ends, a final call with `endOfInput=true` can turn it into malformed.

**OVERFLOW does not mean a charset error either.** It simply means the output buffer ran out of space. Drain/free the output buffer and call again; do not discard input or falsely set `endOfInput`.

### Standard Coder Lifecycle

```text
new Decoder/Encoder
      |
      v
reset() if coder was used previously
      |
      v
decode/encode(input, output, false)
      |        |
      |        +-- UNDERFLOW: wait for/feed more input
      |        +-- OVERFLOW: drain output, retry
      |        +-- ERROR: handle per policy
      v
decode/encode(input, output, true)  // signal end of input
      |
      v
flush(output)                       // may require multiple calls if OVERFLOW
      |
      v
Done; reset before next operation
```

Per Oracle Java 17, decoders/encoders are **stateful** and not thread-safe. After finishing one operation, reset before the next; do not treat them as pure functions callable concurrently across threads.

## 9. Streaming UTF-8 Decoder: Split Bytes Are Not an Error

We will feed the two UTF-8 bytes of `é` (U+00E9) in **two input batches**: `C3` then `A9`. In the first batch, a complete character cannot be decoded yet; after the second batch, enough data exists.

### Program 4 — ByteBuffer.compact and the Decoder

File `StreamingDecoderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StreamingDecoderDemo {
    public static void main(String[] args) throws Exception {
        CharsetDecoder decoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(4);
        CharBuffer output = CharBuffer.allocate(4);

        input.put((byte) 0xC3);
        input.flip();

        CoderResult first = decoder.decode(
                input, output, false);

        System.out.println("firstUnderflow=" +
                first.isUnderflow());
        System.out.println("bytesWaiting=" +
                input.remaining());

        // Keep unprocessed byte C3, append A9 from next chunk.
        input.compact();
        input.put((byte) 0xA9);
        input.flip();

        CoderResult second = decoder.decode(
                input, output, true);
        CoderResult flushed = decoder.flush(output);

        output.flip();
        char decoded = output.get();

        System.out.printf(Locale.ROOT,
                "decoded=U+%04X%n", (int) decoded);
        System.out.println("secondUnderflow=" +
                second.isUnderflow());
        System.out.println("flushedUnderflow=" +
                flushed.isUnderflow());
        System.out.println("bytesLeft=" +
                input.remaining());
    }
}
```

```bash
javac -encoding UTF-8 StreamingDecoderDemo.java
java StreamingDecoderDemo
```

Stdout:

```text
firstUnderflow=true
bytesWaiting=1
decoded=U+00E9
secondUnderflow=true
flushedUnderflow=true
bytesLeft=0
```

Walkthrough:

- On the first call with `endOfInput=false`, only byte `C3` is present; the decoder leaves the unprocessed byte and returns `UNDERFLOW`.
- `input.compact()` shifts **unconsumed bytes** to the start of the buffer; do not call `clear()` and lose them.
- After appending `A9`, the UTF-8 sequence `C3 A9` is valid and decoded into `é`.
- Only **on the final batch** do we call `decode(..., true)` followed by `flush`.
- The example uses sufficiently large buffers so no `OVERFLOW` occurs; production streaming code must handle full output buffers as well.

**A common bug:** assuming `input.remaining()==0` after `UNDERFLOW`. When a sequence lacks its trailing bytes, the decoder may **leave unconsumed bytes in place**. Inspect `position/limit` to see what remains before refilling. Do not rely solely on `CoderResult.isUnderflow()` and forget to preserve the input remainder.

## 10. Streaming Encoder: Two UTF-16 Surrogate Units Arriving in Two Batches

The encoder has analogous state. Suppose we want to write the emoji `😀` (code point U+1F600), represented in Java by two UTF-16 code units `\uD83D\uDE00`. If the first chunk contains only the high surrogate, the coder lacks complete data.

### Program 5 — Preserving a High Surrogate Across Chunk Boundaries

File `StreamingEncoderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StreamingEncoderDemo {

    private static String hex(ByteBuffer bytes) {
        StringBuilder result = new StringBuilder();
        while (bytes.hasRemaining()) {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format(
                    Locale.ROOT, "%02X",
                    Byte.toUnsignedInt(bytes.get())));
        }
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        CharsetEncoder encoder = StandardCharsets.UTF_8
                .newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT);

        CharBuffer input = CharBuffer.allocate(4);
        ByteBuffer output = ByteBuffer.allocate(8);

        input.put('\uD83D');
        input.flip();

        CoderResult first = encoder.encode(
                input, output, false);
        System.out.println("firstUnderflow=" +
                first.isUnderflow());
        System.out.println("charsWaiting=" +
                input.remaining());

        // Move remaining high surrogate to front, feed low surrogate.
        input.compact();
        input.put('\uDE00');
        input.flip();

        CoderResult second = encoder.encode(
                input, output, true);
        CoderResult flushed = encoder.flush(output);

        output.flip();
        System.out.println("secondUnderflow=" +
                second.isUnderflow());
        System.out.println("flushedUnderflow=" +
                flushed.isUnderflow());
        System.out.println("utf8=" + hex(output));
    }
}
```

```bash
javac -encoding UTF-8 StreamingEncoderDemo.java
java StreamingEncoderDemo
```

Stdout:

```text
firstUnderflow=true
charsWaiting=1
secondUnderflow=true
flushedUnderflow=true
utf8=F0 9F 98 80
```

Bytes `F0 9F 98 80` are the UTF-8 encoding of U+1F600. The coder must not “fix” a lone high surrogate in the first chunk with a replacement when **end-of-input has not been signaled**. In real applications, allocate adequate buffers or handle `OVERFLOW` and retain unconsumed `char`s.

### What If a Buffer Is Smaller Than a Single Output Unit?

- A UTF-8 encoder may need up to four bytes for one supplementary code point.
- An output `ByteBuffer` too small to hold even one output unit can cause the coder to return `OVERFLOW` **without consuming the corresponding input**.
- Retrying with a buffer that remains too small and never gains space can stall the loop.
- Use reasonable buffer sizes or a buffer management mechanism that can grow.

Those are **API/buffer usage bugs**, distinct from malformed or unmappable input. Setting `CodingErrorAction.IGNORE` will not fix output `OVERFLOW`.

## 11. CoderResult: Reporting Errors vs. Throwing Exceptions

When using one-shot APIs:

```java
CharBuffer result = decoder.decode(bytes);
ByteBuffer resultBytes = encoder.encode(chars);
```

Under `REPORT`, these methods can throw `CharacterCodingException`—more specifically `MalformedInputException` or `UnmappableCharacterException`.

When using incremental APIs:

```java
CoderResult result =
        decoder.decode(input, output, endOfInput);
```

The coder returns `CoderResult` to inform the caller of its status. Under `REPORT`, malformed or unmappable cases are described via an **error `CoderResult`**, **without throwing an exception from this call**. The caller can use:

```java
if (result.isMalformed()) {
    // Report malformed byte sequence.
}
if (result.isUnmappable()) {
    // Report unmappable character.
}
if (result.isError()) {
    result.throwException();
}
```

This is illustrative code inside a method; `throwException()` can throw `CharacterCodingException`, so the caller must declare or catch it appropriately.

### CoderResult API

| Method | Meaning |
| --- | --- |
| `isUnderflow()` | Insufficient available input or all input processed |
| `isOverflow()` | Output buffer lacks remaining capacity |
| `isMalformed()` | Input contains a structurally invalid sequence |
| `isUnmappable()` | Input is valid but cannot be mapped |
| `isError()` | True for malformed or unmappable |
| `length()` | Length of the **offending input segment** (in coder input units) |
| `throwException()` | Throws the exception matching the error state |

`CoderResult.length()` is meaningful only for error results; do not call it on `UNDERFLOW`/`OVERFLOW` expecting “how many bytes were read.” The number of bytes/chars consumed is tracked via the **buffer's `position`** before and after encode/decode.

**Watch the units:** a decoder takes a `ByteBuffer`, so error length is in input bytes; an encoder takes a `CharBuffer`, so error length is in input UTF-16 code units. Do not assume error length equals the number of Unicode graphemes.

## 12. REPORT, REPLACE, IGNORE in Business Design

Error decisions should not merely aim to “avoid throwing exceptions.” They affect correctness, security, and user experience.

| Context | Usually appropriate approach | Reason |
| --- | --- | --- |
| Reading config files, JSON, contract data | `REPORT` | Cannot silently corrupt key values or identifiers |
| Receiving API payloads with a defined charset | `REPORT` | Return 4xx/validation error on invalid bytes |
| Importing historical data needing error discovery | `REPORT` + log/report offset; separate repair pipeline | Detect and trace corrupted records |
| Showing an untrusted preview, best-effort priority | `REPLACE` may fit per policy | Readers see `�` indicating corrupted data |
| Fault-tolerant content search | Consider `REPLACE` if documented | Can display partial content without overwriting source |
| Dropping unimportant invalid sequences | Use `IGNORE` only when data loss is permitted | Impossible to know which data was deleted |
| Passwords, tokens, digital signatures, map keys | Avoid `REPLACE`/`IGNORE` | Silent mutations can cause collisions or auth failures |
| Exporting to a legacy charset | `REPORT` or an explicit transliteration path | Never silently turn customer names/data into `?` |

**Transliteration is not the same as charset replacement.** For instance, an application converting accented letters to ASCII via business rules is an **intentional linguistic transformation** that must be documented and tested separately; `CodingErrorAction.REPLACE` simply emits a replacement when encoding fails, rather than producing meaningful transliteration.

### 12.1. When Should Errors Be Logged?

With `REPORT`, you can report that a payload contains invalid bytes, logging the source name and byte offset if available. However, do not dump entire text payloads containing secrets or PII uncontrolled into logs. A good strategy is:

- Return a meaningful error to the data provider.
- Record decode/encode error metrics per source.
- Retain the original payload for reprocessing if policy allows.
- Do not blindly try multiple charsets sequentially and pick “the first one that does not throw” as proof you found the right charset.

Picking a valid yet wrong charset can still decode into nonsensical text (**mojibake**) without the coder reporting any error. Rely on metadata/protocol contracts and semantic checks, not merely absence of exceptions.

## 13. File and Network I/O: Attaching Decoder/Encoder to Reader/Writer

When reading from a stream, you can pass a configured decoder to `InputStreamReader`, and a configured encoder to `OutputStreamWriter`:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// Example inside a method:
InputStreamReader reader = new InputStreamReader(
        inputStream,
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT));

OutputStreamWriter writer = new OutputStreamWriter(
        outputStream,
        StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT));
```

This is illustrative code assuming `inputStream` and `outputStream` come from outside; in applications, use `try-with-resources` when owning the stream.

With streaming I/O, reader/writer classes manage buffers and coder state internally; you do not have to write `ByteBuffer.compact()`/`CoderResult` yourself just to read an ordinary file. Yet **configuring error actions** still matters.

### 13.1. Runnable Strict Reader Example

File `StrictReaderDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictReaderDemo {
    public static void main(String[] args) throws Exception {
        byte[] badUtf8 = {0x41, (byte) 0xC3, 0x28};

        boolean rejected = false;
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(badUtf8),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT))) {

            char[] buf = new char[8];
            while (reader.read(buf) != -1) {
                // Read solely to validate the source.
            }
        } catch (CharacterCodingException ex) {
            rejected = true;
        }

        System.out.println("rejected=" + rejected);
    }
}
```

```bash
javac -encoding UTF-8 StrictReaderDemo.java
java StrictReaderDemo
```

Stdout:

```text
rejected=true
```

If you use the convenience overload `InputStreamReader(input, StandardCharsets.UTF_8)`, its policy on malformed/unmappable input may not match an explicitly passed `REPORT` decoder. When strict input validation is required, supply a configured decoder so characters are never silently replaced.

### 13.2. Files.readString and Files.writeString

The `Files.readString(path, charset)` and `Files.writeString(path, text, charset)` APIs provide convenient file operations. In Java 17, `Files.readString` reports errors on malformed/unmappable byte sequences with an appropriate `IOException`, and `Files.writeString` likewise fails when text cannot be encoded in the chosen charset. However, **do not equate** all file API overloads with `new String(bytes, charset)` or `String.getBytes(charset)`: each API has its own contract for invalid data.

When large streaming is needed, manage buffered readers/writers and explicit charsets; when exact control over every action is needed, use configurable coders/readers/writers. On multilingual servers, never let the host's default charset decide how data is read when the protocol specifies UTF-8.

## 14. Do Not Confuse Charset, BOM, and Locale

Several production bugs are mislabeled as “Vietnamese bugs”:

- **Wrong charset:** a UTF-8 file read as Windows-1252, causing mojibake.
- **Malformed byte data:** a truncated UTF-8 sequence missing bytes.
- **BOM:** a byte-order mark at the start of a stream may require detection/stripping rules aligned with the charset and parser; a coder does not automatically detect all BOM kinds.
- **Wrong Unicode normalization:** `"é"` can be precomposed or `"e\u0301"`, looking alike yet differing in `String.equals`.
- **Wrong locale:** number, date, month-name, or case-mapping rules not matching the user's language.
- **Wrong font/rendering:** missing glyph or shaping support; Unicode text can be completely valid yet still render as boxes.

`CharsetDecoder`/`CharsetEncoder` primarily solve **byte ↔ character conversion**. They do **not** translate languages, automatically convert decomposed characters to NFC, select fonts, or perform locale-sensitive collation.

For example, after decoding UTF-8 accurately, you may call `Normalizer.normalize(text, Normalizer.Form.NFC)` **if the data contract requires it**. That is a separate step; do not normalize passwords, signatures, or tokens when the protocol forbids it.

## 15. UTF-8 and Supplementary Characters

Java `String` uses UTF-16 code units. A supplementary Unicode code point like `😀` (U+1F600) has:

- **Two UTF-16 code units**: `D83D DE00`.
- **Four UTF-8 bytes**: `F0 9F 98 80`.
- **One Unicode code point**.
- Usually **one grapheme cluster** for a standalone emoji, though composite emoji can contain multiple code points.

Do not use `String.length()` to predict UTF-8 byte size. Do not arbitrarily slice a UTF-8 byte stream and call `new String(chunk, UTF_8)` per chunk: a code point can be split between two chunks, and each isolated decode can emit replacement characters, **corrupting data even though the whole stream was valid**.

**Streaming rules:**

1. Retain incomplete byte sequences after `UNDERFLOW` and prepend them to the next chunk.
2. Only signal end-of-input on the true final chunk.
3. Flush the coder after completion.
4. Do not treat output `OVERFLOW` as an invalid-data signal.
5. Maintain the **same Charset and coder state** throughout a single operation.

For text containing combining marks or ZWJ emoji, accurate decoding only guarantees Unicode code points; slicing/grapheme segmentation belongs to a separate text-processing layer.

## 16. An Effective Testing Checklist

### 16.1. Decoder Tests

| Input | Charset | Action | Expected |
| --- | --- | --- | --- |
| `41 42` | UTF-8 | REPORT | `AB` |
| `C3 A9` | UTF-8 | REPORT | U+00E9 |
| `41 C3 28 42` | UTF-8 | REPORT | Malformed error |
| `41 C3 28 42` | UTF-8 | REPLACE | `A\uFFFD(B` |
| `41 C3 28 42` | UTF-8 | IGNORE | `A(B` |
| `C3`, then `A9` across two chunks | UTF-8 | REPORT + incremental | U+00E9 |
| `C3` at **true end** of stream | UTF-8 | REPORT | Malformed error |

### 16.2. Encoder Tests

| Input | Charset | Action | Expected |
| --- | --- | --- | --- |
| `"AB"` | ISO-8859-1 | REPORT | Bytes `41 42` |
| `"A€B"` | UTF-8 | REPORT | `41 E2 82 AC 42` |
| `"A€B"` | ISO-8859-1 | REPORT | Unmappable error |
| `"A€B"` | ISO-8859-1 | REPLACE + `!` | `41 21 42` |
| `"A€B"` | ISO-8859-1 | IGNORE | `41 42` |
| Lone high surrogate | UTF-8 | REPORT | Malformed error |
| Valid high + low surrogate across two chunks | UTF-8 | REPORT + incremental | `F0 9F 98 80` |

### 16.3. Business Tests

- File import/export must specify a standard charset rather than relying on system defaults.
- Under `REPORT`, errors must not be caught and silently ignored or turned into empty files.
- Under `REPLACE`/`IGNORE`, UI or logs must surface potential data loss where required.
- Input split into multiple chunks must decode identically to unchunked input across varied chunk boundaries.
- Never determine charset solely from user locale; language tag `vi-VN` does not specify whether a file uses UTF-8 or Windows-1258.
- Test Vietnamese diacritics, CJK, emoji, and non-BMP characters.
- For legacy charsets, verify encodability for characters that actually occur.
- Test malformed UTF-8, isolated surrogates, overlong encodings, and illegal code point sequences; never accept malformed bytes just because they “look okay.”
- Preserve the original payload when pipelines require auditing or source-level repair.
- Verify exact exception types and ensure error actions never mutate across flows.

### 16.4. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `new String(bytes)` without explicit charset | Depends on default charset/JDK context | Pass `StandardCharsets.UTF_8` per contract |
| Calling `new String(bytes, UTF_8)` and assuming input is always valid | Malformed bytes can become U+FFFD | Use a `REPORT` decoder when strictness is needed |
| Using `String.getBytes(ISO_8859_1)` for multilingual data | Unrepresentable characters are replaced | Use a `REPORT` encoder or UTF-8 |
| Configuring only `onMalformedInput`, forgetting `onUnmappableCharacter` | Inconsistent error policy | Configure both per policy |
| Treating `UNDERFLOW` as an error | Rejects streams with code points split across chunks | Keep remainder, feed more input |
| Treating `OVERFLOW` as an error | Halts merely because output buffer filled | Drain output and retry |
| Calling `clear()` with unconsumed input remainder | Loses bytes/chars of a character | Use `compact()` then append more |
| Passing `endOfInput=true` before the final chunk | Incomplete sequence may be flagged malformed | Signal end only at true end of stream |
| Forgetting `flush` after final call | Risk of losing data in stateful charsets | Complete full coder lifecycle |
| Using `IGNORE` to “fix font bugs” | Irreversibly deletes data | Fix source charset/font, never hide errors |
| Sharing a coder across multiple threads | Race conditions/state corruption | One coder per operation |
| Mixing Unicode normalization with decoding | Wrong layer, may illegally mutate data | Keep layers cleanly separated |
| Predicting UTF-8 bytes via `String.length()` | Wrong for diacritics, CJK, emoji | Count encoded bytes |
| Treating error-free decode as proof of right charset | Mojibake can still be valid | Rely on metadata/protocol and semantic checks |

## 17. Exercises and Answers

**Exercise 1 — Error classification.** Bytes `C3 28` are declared UTF-8 yet are not valid UTF-8. Is this malformed or unmappable?

**Answer:** Malformed, because the byte sequence violates UTF-8 structure.

**Exercise 2 — Error classification.** The string `"A€B"` is encoded to ISO-8859-1. The euro character is valid Unicode yet absent from that character set. What is this?

**Answer:** Unmappable. Switching to UTF-8 encodes this string cleanly.

**Exercise 3 — Policy.** When receiving accounting data files from a vendor, should you use `IGNORE` to avoid throwing errors?

**Answer:** Generally no. When integrity matters, use `REPORT`, report the invalid file, and fix the source. `IGNORE` silently deletes bytes/characters and can alter account numbers, codes, or names.

**Exercise 4 — Defaults.** Which action does `StandardCharsets.UTF_8.newDecoder()` use by default for malformed/unmappable under Java 17? Is `new String(bytes, UTF_8)` identical?

**Answer:** A new decoder defaults to `REPORT`. The convenience `String` constructor uses replacement for malformed/unmappable bytes, so they are not equivalent.

**Exercise 5 — Streaming.** One chunk ends with byte `0xC3`; the next starts with `0xA9`. Should you report an error on the first chunk?

**Answer:** Not if the stream has not ended. With an incremental decoder, `endOfInput=false` keeps the pending byte; once `A9` arrives, it decodes to `é`.

**Exercise 6 — CoderResult.** A decoder returns `OVERFLOW`. Is the data badly encoded?

**Answer:** No. The output buffer is full; drain/read the output and call again.

**Exercise 7 — Replacement.** Does `CharsetEncoder.replaceWith` take a `String` or a `byte[]`? What about `CharsetDecoder.replaceWith`?

**Answer:** The encoder takes `byte[]`; the decoder takes `String`.

**Exercise 8 — Unicode.** Emoji U+1F600 has two UTF-16 code units. What can happen if the two halves are encoded in two independent requests?

**Answer:** Each half is a lone surrogate and may be flagged malformed or replaced. To encode as `F0 9F 98 80`, keep both units together in one operation or carry the pending unit in a stateful encoder.

**Exercise 9 — Exceptions.** The incremental API has `CoderResult.isError()`; when is `throwException()` used?

**Answer:** With `REPORT`, the caller can explicitly call `throwException()` to turn an error `CoderResult` into the corresponding exception. One-shot `decode(ByteBuffer)`/`encode(CharBuffer)` throw directly.

**Exercise 10 — Charset and locale.** A user selects `vi-VN`. Can you infer from that that their file's bytes are definitely UTF-8?

**Answer:** No. Locale is language/region; a file's charset is determined by its contract, metadata, or producer. It could be UTF-8 or a legacy charset.

**Exercise 11 — I/O.** When using `InputStreamReader(inputStream, decoder)` with `REPORT`, are malformed bytes replaced with U+FFFD and continued, or do they raise an error?

**Answer:** They raise the appropriate `CharacterCodingException` (typically `MalformedInputException`) from the read operation; it does not fall back to replacement because `REPORT` was specified.

**Exercise 12 — Practical testing.** Why are ASCII-only tests insufficient to verify a charset pipeline?

**Answer:** Many charsets encode ASCII identically. You need Vietnamese, CJK, euro signs, supplementary characters, malformed bytes, and streaming boundary conditions to reveal differences.

## 18. Summary

- **`CharsetDecoder` = bytes → UTF-16 chars**, **`CharsetEncoder` = UTF-16 chars → bytes**. Both require a specific `Charset` and maintain state during conversion.
- The two main errors are **MALFORMED** (structurally invalid input) and **UNMAPPABLE** (valid input that cannot be represented in the target charset/mapping).
- `CodingErrorAction.REPORT` reports errors; `REPLACE` substitutes a replacement; `IGNORE` drops the bad segment. **REPLACE and IGNORE can cause data loss.**
- New Java 17 encoders/decoders default to **REPORT**, whereas convenience APIs like `new String(bytes, charset)` and `String.getBytes(charset)` may use replacement: **verify each API's contract**.
- One-shot coders can throw `CharacterCodingException`; incremental coders return `CoderResult`. `UNDERFLOW` and `OVERFLOW` are normal buffer states, not charset errors.
- For chunked data, **keep remainders**, never signal end-of-input prematurely, handle `OVERFLOW`, and perform final encode/decode and `flush` in order.
- UTF-8 is an encoding, **not a language**; never use `Locale` as a method to determine charset.
- For critical data, prefer **REPORT + explicit error handling**; never hide errors or silently alter bytes.
- Never share mutable coders across threads; create one per operation or manage ownership properly.

### Official Java SE 17 Documentation

- [CharsetDecoder — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CharsetEncoder — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [CodingErrorAction — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [CoderResult — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [String — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Files — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
