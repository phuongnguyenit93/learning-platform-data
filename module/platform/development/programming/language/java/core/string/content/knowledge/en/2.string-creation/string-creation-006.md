# Creating a `String` from `byte[]` with Character Encodings in Java

When receiving data from files, networks, databases, or APIs, we often get a byte array (`byte[]`). To turn that data into text, Java must **decode the bytes using the exact character encoding (charset)** that the producer used. The common, explicit, and consistency-safe approach is `new String(bytes, StandardCharsets.UTF_8)`.

## 1. Distinguishing Bytes, Characters, and Charsets

- **`byte[]`** is a sequence of 8-bit values. The byte array itself does not declare whether it is UTF-8 text, an image, a ZIP archive, or other binary data.
- A **Charset** defines how Unicode character sequences map to bytes when *encoding*, as well as how text is recovered from bytes when *decoding*.
- **`String`** stores text according to Java's Unicode model. Creating a `String` from bytes requires knowing the charset; you cannot reliably infer an arbitrary charset from a `byte[]` alone.
- **UTF-8** is the dominant encoding on the web, APIs, JSON, and many file formats. A character can occupy from 1 to 4 bytes in UTF-8.

Processing flow:

```text
String -- getBytes(charset) --> byte[]
String <-- new String(bytes, charset) -- byte[]
```

Round-trip conversion preserves data intact only when the appropriate charset is used and the data is validly encoded, transmitted, and decoded. Do not confuse **byte** count with **character** count: for instance, `"é"` (U+00E9) occupies 2 bytes in UTF-8 while `String.length()` is 1; an emoji outside the BMP typically occupies 4 UTF-8 bytes and 2 UTF-16 code units in `String.length()`.

## 2. APIs to Use

| Call | Meaning | When to use |
| --- | --- | --- |
| `new String(bytes, StandardCharsets.UTF_8)` | Decodes the entire array using UTF-8 | Default choice when the **data specification** defines UTF-8 |
| `new String(bytes, offset, length, charset)` | Decodes only `length` bytes starting at index `offset` | When a packet has a header or only a complete byte slice is needed |
| `new String(bytes, Charset.forName("..."))` | Uses a configured or protocol-mandated charset name | When a protocol requires a charset other than the common constants |
| `new String(bytes)` | Decodes using the Java runtime's default charset | Only when the protocol explicitly specifies using the default charset |
| `text.getBytes(charset)` | Encodes a `String` back into a `byte[]` | When writing or sending text externally |

Common import:

```java
import java.nio.charset.StandardCharsets;
```

`StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16`, and `UTF_16LE`/`UTF_16BE` are standard built-in charsets. Using `Charset` constants avoids spelling mistakes in charset names and makes the encoding contract more explicit than string literals like `"UTF-8"`. The constructor `new String(byte[], String charsetName)` also exists, though it can throw `UnsupportedEncodingException`; modern applications generally prefer the `Charset` overload.

**Key point:** Do not pick UTF-8 just because it is popular if the data source is declared as ISO-8859-1, UTF-16LE, or another charset; follow the file format, protocol header, or API contract.

## 3. Complete Example: UTF-8 Encoding and Decoding

Save the following file as `DecodeBytesDemo.java` in UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class DecodeBytesDemo {
    public static void main(String[] args) {
        String original = "Tiếng Việt";
        byte[] payload = original.getBytes(StandardCharsets.UTF_8);

        String decoded = new String(payload, StandardCharsets.UTF_8);
        System.out.println(decoded);
        System.out.println(Arrays.equals(
                payload, decoded.getBytes(StandardCharsets.UTF_8)));

        byte[] packet = {88, 72, 105, 89}; // XHiY in ASCII
        String middle = new String(
                packet, 1, 2, StandardCharsets.US_ASCII);
        System.out.println(middle);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 DecodeBytesDemo.java
java DecodeBytesDemo
```

Output:

```text
Tiếng Việt
true
Hi
```

Explanation:

1. `getBytes(StandardCharsets.UTF_8)` generates UTF-8 bytes from the original text.
2. `new String(payload, StandardCharsets.UTF_8)` interprets the bytes properly and restores `"Tiếng Việt"`.
3. `Arrays.equals(...)` compares byte array contents, confirming the round-trip of valid data in this example (you cannot use `payload.equals(...)` to compare the contents of two arrays).
4. In the `offset`/`length` overload, `offset = 1` starts at the second byte (`H`), and `length = 2` reads exactly two bytes (`H`, `i`). `length` is measured in **bytes**, not characters.

Array slice boundary conditions: `offset >= 0`, `length >= 0`, and the range `[offset, offset + length)` must fit within the array; otherwise Java throws `IndexOutOfBoundsException`. If you slice in the middle of a multi-byte UTF-8 character's byte sequence, the decoded result may become corrupted data with replacement characters.

## 4. Choosing the Wrong Charset: Garbled Text (Mojibake)

Bytes encoded with UTF-8 need to be decoded with UTF-8. The exact same bytes can be interpreted completely differently by another charset:

```java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        byte[] utf8Bytes = "Café".getBytes(StandardCharsets.UTF_8);

        System.out.println(new String(
                utf8Bytes, StandardCharsets.UTF_8));
        System.out.println(new String(
                utf8Bytes, StandardCharsets.ISO_8859_1));
    }
}
```

Output:

```text
Café
CafÃ©
```

`"é"` is represented by the two UTF-8 bytes `C3 A9`. When those two bytes are read as two separate ISO-8859-1 characters, the result becomes `"Ã©"`. This is a **wrong-charset decoding bug**, distinct from a display font issue. No `new String(...)` call can reliably auto-detect all charsets; you must check the data's origin or specification.

In real systems, check `Content-Type` and any protocol `charset` parameter (if present), file format configuration, partner specifications, and the encoding step on the byte-producing side. Do not blindly try decoding with multiple charsets and treat a string that "looks right" as definitive proof.

## 5. Invalid UTF-8 Bytes: Replace or Fail?

A byte array can contain an invalid UTF-8 sequence, such as `C3 28`: byte `C3` starts a two-byte sequence, but `28` is not a valid continuation byte.

With `new String(bytes, charset)`, Java **replaces** malformed or unmappable byte sequences with the decoder's replacement character; for UTF-8 this is typically `�` (U+FFFD). This is convenient for displaying faulty text, but it can hide the fact that data was corrupted.

If the problem requires detecting and rejecting invalid bytes (critical data ingestion, integrity checks, strict protocol parsing), use `CharsetDecoder` with `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

        String lenient = new String(
                invalidUtf8, StandardCharsets.UTF_8);
        System.out.println(lenient.equals("\uFFFD("));

        CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(invalidUtf8));
            System.out.println("Valid data");
        } catch (CharacterCodingException e) {
            System.out.println(e.getClass().getSimpleName());
        }
    }
}
```

Run `javac -encoding UTF-8 StrictDecodeDemo.java` then `java StrictDecodeDemo`, producing:

```text
true
MalformedInputException
```

`lenient` contains U+FFFD followed by `(`, so the comparison returns `true`. Conversely, a decoder configured with `REPORT` throws `MalformedInputException` (a subclass of `CharacterCodingException`). `onUnmappableCharacter(REPORT)` also handles bytes that are structurally valid but cannot be mapped in the given charset. If a different policy is needed, `CodingErrorAction.REPLACE` explicitly replaces and `IGNORE` skips invalid data; ignoring risks silent data loss.

## 6. Common Pitfalls and How to Handle Them

- **Forgetting to specify a charset:** `new String(bytes)` depends on the runtime's default charset. Since Java 18, UTF-8 is the default under JEP 400 in most configurations, but older versions and runtime options may differ. For data exchanged across systems, always specify the charset explicitly.
- **Confusing binary data with text:** images, compressed payloads, encrypted data, and random bytes should not be arbitrarily passed through `new String(...)` and then `getBytes(...)`; the transformation can alter the bytes. Use `byte[]`/streams to preserve raw binary data; use Base64 only when binary needs a character representation.
- **Splitting a multi-byte character:** `new String(bytes, offset, length, UTF_8)` is only valid when the selected slice is a complete encoded byte sequence. Do not split network chunks and decode each separately if a chunk boundary might land inside a UTF-8 character.
- **Decoding large data at once:** for text streams, wrap with `InputStreamReader(input, StandardCharsets.UTF_8)` and `BufferedReader` when appropriate. A reader handles decoding across read boundaries; when processing `ByteBuffer` in pieces, use a `CharsetDecoder` that maintains state across chunks.
- **Comparing the wrong length:** `bytes.length`, `String.length()`, and `codePointCount(...)` measure three different things: bytes, UTF-16 code units, and Unicode code points. Do not use `String.length()` to compute protocol byte lengths.
- **Re-encoding corrupted data:** once mis-decoded into replacement characters, the original bytes cannot be recovered automatically. Fix the charset/byte source upstream; preserve raw bytes when diagnosing issues.
- **BOM / format prefixes:** if the source includes a byte order mark or header, determine whether it is encoding metadata to strip or part of the protocol. Do not blindly trim the first three bytes of all UTF-8 data; data may not have a BOM.

## 7. Application Checklist

1. **Verify it is text** and identify where the bytes originate (file, HTTP response, database, message queue, etc.).
2. **Read the encoding contract**: use the charset declared by the protocol/format; prefer `StandardCharsets.UTF_8` when the source genuinely uses UTF-8.
3. **Collect complete text byte sequences**, avoiding cuts in the middle of multi-byte characters.
4. **Decode:** for standard cases use `new String(bytes, charset)`; when corrupted data must be caught, use `CharsetDecoder` with `REPORT`.
5. **Test with accented letters, non-ASCII characters, and invalid data:** do not test only ASCII text, because many charsets produce identical ASCII results.
6. **When writing/sending back**, use `getBytes(charset)` with the exact charset defined for the receiver; never rely implicitly on the default charset.

**Remember:** `byte[]` is just bytes; **a charset is the mandatory contract to interpret them as text**. For valid UTF-8 bytes, `new String(bytes, StandardCharsets.UTF_8)` is the direct approach; for untrusted data where invalid bytes must be rejected, use a decoder with the `REPORT` policy.
