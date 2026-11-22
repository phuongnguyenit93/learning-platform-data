# Charset Reference Table and Byte-to-Character Conversion Rules in Java I/O

## 1. Purpose and Mental Model to Remember

When reading files, network streams, or binary data containing text, a program receives **bytes**, whereas the application wants to process **Unicode characters**. To convert accurately, you must know the **charset (character set / encoding)** used by the data producer. A single byte sequence can yield different text depending on the charset; in many cases, the charset cannot be reliably inferred from the bytes alone.

Conversion flow:

~~~text
Unicode text  --[encoder + charset]--> byte sequence
Byte sequence --[decoder + charset]--> Unicode text
~~~

- **Charset** specifies how to encode characters into bytes and decode bytes into characters.
- **Unicode code point** is the identifier of an abstract character, for example U+0041 (A), U+00E9 (é), U+4E2D (中), U+1F600 (😀).
- **Java String and char** represent strings using **UTF-16** code units. A code point outside the BMP, such as 😀, uses **two chars** (a surrogate pair); therefore, the byte count, char count, and code point count can differ.
- **CharsetDecoder** transforms bytes into a sequence of UTF-16 units. **CharsetEncoder** does the reverse.
- **Malformed input** is a byte sequence that violates the charset's structure; an **unmappable character** is input that cannot be represented in the target. These two error types must be distinguished and handled intentionally.

Mental formula: **bytes + charset + error handling rule → text**. There is no universal lookup for arbitrary bytes when the charset is missing.

## 2. Reference Table of Common Charsets

| Charset in Java | Rules and representable range | How many bytes per character / code point? | What to watch out for |
|---|---|---|---|
| **US-ASCII** (StandardCharsets.US_ASCII) | Codes 0x00–0x7F map to U+0000–U+007F | 1 byte for representable characters | Bytes 0x80 and above are invalid in standard ASCII |
| **ISO-8859-1** (StandardCharsets.ISO_8859_1) | Each byte 0x00–0xFF maps directly to code point U+0000–U+00FF | Always 1 byte when encoding characters in this set | Byte 0x80 is U+0080 (a control character), **not** the € sign |
| **windows-1252** (Charset.forName("windows-1252")) | Windows Western European 8-bit code page; several positions in 0x80–0x9F differ from Latin-1 | 1 byte for representable characters | Byte 0x80 is €; some bytes such as 0x81 are unassigned |
| **UTF-8** (StandardCharsets.UTF_8) | Variable-length, preserves ASCII 0x00–0x7F | 1–4 bytes per valid Unicode code point | Continuation bytes 0x80–0xBF cannot start a character on their own |
| **UTF-16BE** (StandardCharsets.UTF_16BE) | UTF-16 with high byte first | 2 or 4 bytes per code point | Does not require a BOM; byte order must be known |
| **UTF-16LE** (StandardCharsets.UTF_16LE) | UTF-16 with low byte first | 2 or 4 bytes per code point | Differs from UTF-16BE in byte order |
| **UTF-16** (StandardCharsets.UTF_16) | UTF-16 with BOM recognition rules to determine byte order when decoding | 2 or 4 bytes per code point, plus BOM if present | Decoder recognizes BOM; if absent, Java defaults to big-endian |

**UTF-8 and UTF-16 are Unicode Transformation Formats**, capable of representing all valid Unicode scalar values. Conversely, ASCII/Latin-1/Windows-1252 only cover finite character sets; not every Unicode string can be encoded into them without error handling.

Using "ANSI" in legacy documentation does not identify a single charset. You must clarify the exact code page (for example windows-1252, windows-1258) and the environment that produced the data.

## 3. Example Table: Same Character, Different Bytes

The hex sequences below show **only the bytes of the character itself**, without a BOM:

| Character | Unicode | UTF-8 | ISO-8859-1 | windows-1252 | UTF-16BE | UTF-16LE |
|---|---|---|---|---|---|---|
| A | U+0041 | 41 | 41 | 41 | 00 41 | 41 00 |
| é | U+00E9 | C3 A9 | E9 | E9 | 00 E9 | E9 00 |
| € | U+20AC | E2 82 AC | Not representable | 80 | 20 AC | AC 20 |
| 中 | U+4E2D | E4 B8 AD | Not representable | Not representable | 4E 2D | 2D 4E |
| 😀 | U+1F600 | F0 9F 98 80 | Not representable | Not representable | D8 3D DE 00 | 3D D8 00 DE |

**Explanation of easily confused cases:**

1. UTF-8 encodes A as 41 just like ASCII, but **é** requires two bytes C3 A9.
2. Byte **E9** in ISO-8859-1/windows-1252 is é; a standalone byte E9 **is not valid UTF-8**.
3. Byte **80** in windows-1252 is €, in ISO-8859-1 it is U+0080, and in UTF-8 it is a misplaced continuation byte.
4. UTF-16 represents 😀 using the surrogate pair **D83D DE00**. Java's **String.length()** returns 2 for this character, while **codePointCount(...)** returns 1.
5. "Not representable" means a standard encoder with the **REPORT** policy must report an error; there is no valid byte to fill into the table. An encoder in replace mode may emit a replacement character such as a question mark.

**Reverse lookup from bytes requires knowing the charset:** byte 0xE9 is not automatically é in UTF-8; the sequence E2 82 AC is € only when decoded as UTF-8, not when decoded as Latin-1.

## 4. UTF-8 Bit-Level Decoding Rules

UTF-8 encodes a Unicode code point in 1–4 bytes. The bit patterns:

| Byte count | First byte | Following bytes | Code point range |
|---|---|---|---|
| 1 | 0xxxxxxx | None | U+0000–U+007F |
| 2 | 110xxxxx | 10xxxxxx | U+0080–U+07FF |
| 3 | 1110xxxx | 10xxxxxx 10xxxxxx | U+0800–U+FFFF, excluding surrogate range |
| 4 | 11110xxx | 10xxxxxx 10xxxxxx 10xxxxxx | U+10000–U+10FFFF |

Steps to decode one code point:

1. Inspect the first byte to determine whether 1, 2, 3, or 4 bytes are needed; check that enough bytes remain.
2. For multi-byte sequences, every subsequent byte must start with the bit prefix **10**.
3. Strip the prefix bits and concatenate the payload bits from left to right.
4. Check the minimum value for that byte length, disallowing **overlong** forms, surrogate code points U+D800–U+DFFF, or values exceeding U+10FFFF.
5. Convert the resulting code point into one or two UTF-16 units to place into a Java String.

Example **é = U+00E9**: C3 (11000011) and A9 (10101001) have payload bits **00011 101001** → binary 11101001 → U+00E9. Example **€ = U+20AC**: E2 82 AC → U+20AC.

Common UTF-8 errors: leading byte 0x80–0xBF (valid only in continuation positions); sequences missing continuation bytes; C0/C1 leading to overlong encodings; invalid F5–FF; three-byte patterns encoding a surrogate; four-byte patterns exceeding U+10FFFF. A strict decoder must report an error rather than guessing a character.

## 5. UTF-16 Decoding Rules, Byte Order, and BOM

UTF-16 consists of **16-bit code units**:

- Code points U+0000–U+D7FF and U+E000–U+FFFF are encoded as a single 16-bit unit.
- Code points U+10000–U+10FFFF are encoded as two units: a **high surrogate** (D800–DBFF) followed by a **low surrogate** (DC00–DFFF).
- A lone surrogate is not a valid Unicode scalar value.
- In **UTF-16BE**, unit 0x0041 becomes 00 41; in **UTF-16LE**, it becomes 41 00.

**BOM (Byte Order Mark)** is a byte-order indicator at the beginning of data:

| Data | BOM bytes | Meaning |
|---|---|---|
| UTF-8 | EF BB BF (optional) | Not needed for byte order; if present, handle consistently |
| UTF-16BE | FE FF | Commonly used as a big-endian marker |
| UTF-16LE | FF FE | Commonly used as a little-endian marker |

In Java, **StandardCharsets.UTF_16** interprets a BOM when decoding; if no BOM is present, the UTF-16 decoder defaults to big-endian. The **UTF_16BE** and **UTF_16LE** charsets have fixed byte order: they do not rely on a BOM to switch order. When encoding with Java's **UTF_16**, output usually begins with BOM FE FF; if you want bytes without a BOM in a known byte order, choose **UTF_16BE** or **UTF_16LE**.

A UTF-8 BOM is neither mandatory nor a reliable way to detect the charset of every file. Depending on the reader and data format, EF BB BF may become U+FEFF at the start of the String; if the input specification requires stripping the BOM, handle it intentionally. Do not blindly delete U+FEFF in the middle of text.

## 6. Java 17+: Decoding Correctly and Verifying Results

The following example is **standalone, compiles, and runs** on Java 17+. Each decode uses an explicit charset and **REPORT** to avoid silently replacing corrupted bytes with another character.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetLookupDemo {
    private static String decodeStrict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        CharsetDecoder decoder = charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        return decoder.decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws CharacterCodingException {
        byte[] utf8 = HexFormat.of().parseHex("41C3A9E4B8ADF09F9880");
        String text = decodeStrict(utf8, StandardCharsets.UTF_8);

        System.out.println("text=" + text);
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));

        byte[] latin1 = HexFormat.of().parseHex("E9");
        System.out.println("latin1=" +
                decodeStrict(latin1, StandardCharsets.ISO_8859_1));

        byte[] cp1252 = HexFormat.of().parseHex("80");
        System.out.println("cp1252=" +
                decodeStrict(cp1252, Charset.forName("windows-1252")));

        String hex = HexFormat.of().withUpperCase()
                .formatHex(text.getBytes(StandardCharsets.UTF_8));
        System.out.println("hex=" + hex);

        byte[] invalidUtf8 = HexFormat.of().parseHex("C328");
        try {
            decodeStrict(invalidUtf8, StandardCharsets.UTF_8);
        } catch (MalformedInputException e) {
            System.out.println("invalidUtf8=" +
                    e.getClass().getSimpleName());
        }
    }
}
~~~

Save as **CharsetLookupDemo.java** in UTF-8 and run:

~~~bash
javac -encoding UTF-8 CharsetLookupDemo.java
java CharsetLookupDemo
~~~

Output:

~~~text
text=Aé中😀
utf8Bytes=10
utf16Units=5
codePoints=4
latin1=é
cp1252=€
hex=41C3A9E4B8ADF09F9880
invalidUtf8=MalformedInputException
~~~

Note that **HexFormat.parseHex(...)** accepts a contiguous hex string in the example above. If the input contains spaces such as "41 C3 A9", strip spaces or parse with an appropriate delimiter; do not pass it directly assuming the method ignores all whitespace.

Compare **new String(bytes, StandardCharsets.UTF_8)**: convenient for already validated data, but constructors like this can replace malformed/unmappable sequences with replacement strings. When integrity is required (configuration, protocols, content requiring exact byte verification), use **CharsetDecoder** with **CodingErrorAction.REPORT** to receive **CharacterCodingException**.

## 7. Applying in I/O: Always State the Charset When Reading/Writing

For UTF-8 text files, Java's high-level APIs accept an explicit charset:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample-utf8.txt");
        Files.writeString(path, "Tiếng Việt và 😀",
                StandardCharsets.UTF_8);

        String result = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(result);
    }
}
~~~

Save **TextFileUtf8Demo.java** in UTF-8, run **javac -encoding UTF-8 TextFileUtf8Demo.java** then **java TextFileUtf8Demo**. Stdout is:

~~~text
Tiếng Việt và 😀
~~~

Pattern for reading a stream with a Reader when processing incrementally: **new InputStreamReader(inputStream, StandardCharsets.UTF_8)**. For data requiring strict validation, use the constructor taking a **CharsetDecoder** configured with REPORT. Because a Reader may hold a partial UTF-8 sequence at the end of a buffer while waiting for the next byte, do not split each chunk into a separate String using **new String(chunk, UTF_8)**: if you split mid-character across bytes, the character will be corrupted. Keep a single decoder across the stream or read through an appropriate Reader.

If the data is **binary** (ZIP, images, protobuf, raw byte files), do not decode the whole thing as text. Only fields specified as text use a charset.

Do not let reading/writing depend on the system's default charset: **new String(bytes)** and **String.getBytes()** without a charset can depend on the runtime/configuration. Since JDK 18, the default charset per JEP 400 is typically UTF-8, yet data and environments still have exceptions; on Java 17 especially, do not guess. Specify explicitly the charset required by the file format/protocol.

## 8. Error Handling: REPORT, REPLACE, and IGNORE

| Action | When data is invalid | When to use |
|---|---|---|
| **CodingErrorAction.REPORT** | Throws an exception (e.g., MalformedInputException, UnmappableCharacterException) | Reading protocols/configs, imports needing corrupted data detection, testing |
| **CodingErrorAction.REPLACE** | Inserts the replacement string configured on the decoder/encoder | Displaying data where information loss is acceptable, with user warning |
| **CodingErrorAction.IGNORE** | Skips the invalid portion | Only when the specification permits data loss; risky for critical data |

For example, C3 28 is not a valid UTF-8 sequence: C3 is a leading byte expecting another byte of the form 10xxxxxx, whereas 28 is the ASCII opening parenthesis. If the decoder replaces errors, the usual result is **�(** (U+FFFD followed by the parenthesis); with REPORT, Java throws **MalformedInputException**.

Encoding can also fail: a string containing **€** or **中** cannot be represented in ISO-8859-1. An encoder with REPORT throws **UnmappableCharacterException**; if replaced, the resulting bytes can no longer reproduce the original Unicode text verbatim. Any pipeline requiring an exact round-trip should use a charset capable of representing the data, usually UTF-8, with explicit error handling.

## 9. Mojibake: Characters Turning into "Ã©", "â‚¬" and How to Diagnose

**Mojibake** is garbled text caused by bytes created in one charset being decoded with another. For example, the letter **é** has UTF-8 hex **C3 A9**. If those two bytes are decoded as windows-1252, they become the two characters **Ã©**, no longer é. Similarly, **€** has UTF-8 **E2 82 AC**, which misread as windows-1252 typically displays as **â‚¬**.

Root-cause diagnosis workflow:

1. Preserve the **original bytes**; inspect the hex bytes around the corrupted region and check the data's origin (file, HTTP, database, message queue).
2. Obtain the charset from **reliable conventions/metadata** (file spec, Content-Type header with a valid charset, schema/protocol, writer configuration).
3. Test decoding with the declared charset and inspect representative non-ASCII characters; do not look only at English text because ASCII 0x00–0x7F is identical across many charsets.
4. If the data has been mis-decoded and re-encoded multiple times, you must know **each transformation step** to recover it; merely "changing the display charset" may not be enough.
5. When you see U+FFFD or question marks already persisted as bytes, the original information may **already be lost**. Fix the bug at the reader/writer and regenerate the data from the source bytes if they still exist.

No charset detector guarantees accuracy for all byte sequences. Use heuristics only when specifications are missing and the risk of misdetection is acceptable; for critical data, require the producer to supply the exact charset.

**Do not confuse charset with normalization.** A character looking like **é** may be U+00E9 or the combining sequence U+0065 U+0301; UTF-8 produces different bytes even though both decode cleanly. A charset does not guarantee NFC/NFD, and Unicode normalization is a separate step when business logic requires it.

## 10. Quick Reference Checklist

- Identify the **original bytes** and **source charset** before writing decoding code.
- If you need direct byte → String conversion in Java: **new String(bytes, charset)** for normal cases; **charset.newDecoder() + REPORT** when detecting errors.
- If you need String → byte conversion: **text.getBytes(charset)**; use **CharsetEncoder + REPORT** when character loss is unacceptable.
- Reading/writing files: prefer **Files.readString/writeString** with **StandardCharsets.UTF_8** or the specified charset.
- When encountering UTF-16 data: check byte order, BOM, and surrogate pairs.
- When encountering Vietnamese text corruption: inspect the charset on both the byte-producing side and the decoding side; do not patch it by replacing displayed characters.
- When logging for diagnostics: print hex bytes, code points (e.g., **text.codePoints()**), charset, and error handling mode; distinguish **String.length()** from the code point count.
- For multi-chunk or streaming data: keep the decoder across reads so a UTF-8 character is never split.
- Only convert text; binary data does not have a general charset.

## 11. Standard References

- [Java 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): encode/decode rules and charsets.
- [Java 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed/unmappable handling and CodingErrorAction.
- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): supported standard charsets.
- [Unicode — UTF-8 / UTF-16 (Unicode Standard)](https://www.unicode.org/versions/latest/core-spec/chapter-3/): encoding formats and validity checks.
