# Distinguishing Encode from Decode in Java: Charset and I/O

## 1. Why Must We Distinguish the Two Conversion Directions?

Vietnamese text, a username, or JSON content is a **character string** to a program, but when writing to a file or sending over a network, the computer must represent it as a **sequence of bytes**. At the destination, that sequence of bytes must be interpreted back into text. These two directions have distinct names:

- **Encode (character encoding):** converts **Unicode text → bytes** according to a chosen `Charset`.
- **Decode (character decoding):** converts **bytes → Unicode text** using the corresponding `Charset`.

For example, with the string `"Café"`:

~~~text
Text:             C a f é
       encode UTF-8
Bytes (hex):      43 61 66 C3 A9
       decode UTF-8
Text:             C a f é
~~~

If that same UTF-8 byte sequence is **decoded as ISO-8859-1**, we get `"CafÃ©"` instead of `"Café"`. This error is commonly called **mojibake**: the bytes are not necessarily corrupted; rather, **the decoder used the wrong charset**.

This lesson explains the directions, APIs, error detection, policies for replacing or rejecting invalid data, file operations, and practical rules in Java 17+. The content falls under the topic of **Charset and I/O**: the goal is to properly handle conversion between **`String`** and **`byte[]`**, without confusing it with cryptographic encryption or Base64 data.

## 2. General Model: Text, Charset, and Bytes

### 2.1. Unicode and String

A Java `String` represents text content as UTF-16 code units; `char` is a 16-bit code unit. `String.length()` returns the number of code units, not the number of bytes written to a file, the number of Unicode code points, or the number of characters visible to the user.

Examples:

| String | UTF-16 code units in `String.length()` | Unicode code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| Precomposed `é` | 1 | 1 | 2 |
| `😀` | 2 | 1 | 4 |
| `Café 😀` | 7 | 6 | 10 |

The byte count of text cannot be inferred from `text.length()` without knowing the charset. The letter `é` takes 2 bytes in UTF-8 but 1 byte in ISO-8859-1; the emoji 😀 requires 4 bytes in UTF-8 and **cannot be represented** in ISO-8859-1.

**Unicode** defines code point values and many text rules; **UTF-8**, **UTF-16**, and **UTF-16LE/BE** are encoding schemes that represent text as bytes. A `Charset` in Java describes a specific conversion between characters and bytes, with a canonical name and aliases.

### 2.2. Encode and Decode Are Inverse Directions

~~~text
                         encode
String / Unicode text  ------------>  byte[]
                      CharsetEncoder
                                        |
                                        | write file / send socket / HTTP body
                                        v
String / Unicode text  <------------  byte[]
                         decode
                      CharsetDecoder
~~~

Both directions require **agreeing on the charset**. If the sender encodes in UTF-8, the receiver must decode in UTF-8, unless a protocol defines another explicit conversion rule.

This can be written as a simple rule:

~~~text
bytes = encode(text, UTF-8)
text2 = decode(bytes, UTF-8)
~~~

For **valid, representable input text** with no mid-transit byte alterations, `text2.equals(text)` is normally `true`. However, if the decoder/encoder replaces invalid data, bytes are truncated, or the two sides use incompatible charsets, this condition is no longer guaranteed.

Do not loosely use phrases like “encode a UTF-8 string into text”: in Java, if a variable is a `String`, it is **text** inside the program; calling `getBytes(UTF_8)` is what produces **UTF-8 bytes**.

## 3. Common Java APIs

| Task | API | Result type |
| --- | --- | --- |
| Encode a String | `text.getBytes(StandardCharsets.UTF_8)` | `byte[]` |
| Decode a byte sequence | `new String(bytes, StandardCharsets.UTF_8)` | `String` |
| Encode using a Charset object | `charset.encode(text)` | `ByteBuffer` |
| Decode using a Charset object | `charset.decode(buffer)` | `CharBuffer` |
| Customize encode errors | `charset.newEncoder()` | `CharsetEncoder` |
| Customize decode errors | `charset.newDecoder()` | `CharsetDecoder` |
| Write text to a file | `Files.writeString(path, text, charset)` | `Path` |
| Read text from a file | `Files.readString(path, charset)` | `String` |
| Write/read raw bytes | `Files.write(path, bytes)` / `Files.readAllBytes(path)` | byte-level |

`StandardCharsets` provides constants such as `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`, `US_ASCII`, and `ISO_8859_1`. Using the constant `StandardCharsets.UTF_8` instead of an arbitrary string `"UTF8"` avoids typos and makes the I/O contract explicit.

**Distinction:** `Charset.forName("UTF-8")` looks up a charset by name, but does not perform encoding/decoding until the corresponding API is called. `StandardCharsets.UTF_8` is a predefined `Charset`.

## 4. Complete Java 17+ Example: Encode UTF-8 Then Decode Back

Create the file `EncodeDecodeDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class EncodeDecodeDemo {
    public static void main(String[] args) {
        String original = "Caf\u00E9 \uD83D\uDE00";

        byte[] encoded =
                original.getBytes(StandardCharsets.UTF_8);
        String decoded =
                new String(encoded, StandardCharsets.UTF_8);

        System.out.println("utf8 hex="
                + HexFormat.of().formatHex(encoded));
        System.out.println("roundtrip="
                + original.equals(decoded));
        System.out.println("chars=" + original.length()
                + ", points=" + original.codePointCount(
                        0, original.length())
                + ", bytes=" + encoded.length);
    }
}
~~~

Save as `EncodeDecodeDemo.java`, and compile/run with JDK 17+:

~~~bash
javac -encoding UTF-8 EncodeDecodeDemo.java
java EncodeDecodeDemo
~~~

Verified stdout on the JVM:

~~~text
utf8 hex=436166c3a920f09f9880
roundtrip=true
chars=7, points=6, bytes=10
~~~

Detailed explanation:

- `C`, `a`, `f`: bytes `43 61 66` in UTF-8.
- `é` (U+00E9): two bytes `C3 A9` in UTF-8.
- Space: byte `20`.
- Emoji 😀 (U+1F600): four bytes `F0 9F 98 80`.
- Total 10 bytes. Inside `String`, this emoji uses **two UTF-16 code units**, so `String.length()` is 7, while the code point count is 6.

`HexFormat` was introduced in Java 17, matching the JDK version of the example. A hex string is a **way to display bytes for inspection**, not UTF-8 text automatically understood by Java.

The syntax `"\u00E9"` and `"\uD83D\uDE00"` in Java source code are **source-code Unicode escapes**. They keep the example stable when copied in environments where entering emoji fails; they do not mean the program has already encoded text into UTF-8. The actual encoding happens at `getBytes(StandardCharsets.UTF_8)`.

## 5. When Using the Wrong Charset: Mojibake Occurs at the Decode Step

Suppose the bytes of `Café` were **encoded with UTF-8**:

~~~text
43 61 66 C3 A9
~~~

If the decoder interprets them as ISO-8859-1, bytes `C3` and `A9` become two separate characters `Ã` and `©`, producing the string `CafÃ©`.

Standalone program `WrongCharsetDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        String original = "Caf\u00E9";
        byte[] utf8 =
                original.getBytes(StandardCharsets.UTF_8);

        String correct =
                new String(utf8, StandardCharsets.UTF_8);
        String wrong =
                new String(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("correct=" + correct);
        System.out.println("wrong=" + wrong);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 WrongCharsetDemo.java
java WrongCharsetDemo
~~~

Stdout, when the console renders Unicode properly:

~~~text
correct=Café
wrong=CafÃ©
~~~

Key point: `wrong` is **not a byte[]**; it is already a **Java String** containing the wrong characters. When rendered to a UI, the output can show mojibake even if the display layer introduces no new errors.

**Do not fix it mechanically by calling encode/decode two or three times.** First determine where the string went wrong, whether the original bytes are still preserved, whether the data source was tagged with the right charset, and whether double-encoding occurred.

If the original bytes are still `43 61 66 C3 A9`, the correct fix is to **decode again from the original bytes using UTF-8**. If the bytes were replaced/truncated or the string went through multiple faulty conversions, recovery may no longer be reliable.

### 5.1. Double Encoding Differs from Single Wrong Decoding

If `"CafÃ©"` is already a `String` and gets **encoded as UTF-8** again, the new bytes correspond to the characters `Ã` and `©`, rather than directly to the initial `C3 A9`:

~~~text
"Café" UTF-8 bytes:   43 61 66 C3 A9
"CafÃ©" UTF-8 bytes:  43 61 66 C3 83 C2 A9
~~~

Once the corruption has propagated across a database or multiple services, a simple `new String(bytes, UTF_8)` is insufficient if `bytes` are no longer the original bytes. “Fixing mojibake” must be based on the source and the exact sequence of steps that actually occurred.

## 6. Encoding Can Fail If the Charset Cannot Represent a Character

UTF-8 can encode every valid Unicode scalar value. Some older charsets cover only a finite character set. For example, `ISO-8859-1` represents `é`, but **cannot represent the emoji 😀**.

This differs from **decoding invalid bytes**:

- **Unmappable character on encode:** a character exists in the text, but the target charset has no representation for it.
- **Malformed input on decode:** a byte sequence is invalid according to the rules of the selected charset.
- **Malformed UTF-16 on encode:** the input `String` has an unpaired high/low surrogate or broken UTF-16 structure.

The converter may **REPLACE**, **REPORT**, or **IGNORE** depending on the API/configuration. For critical data, silently replacing characters with `?` or `�` can cause data loss without the system noticing.

`String.getBytes(Charset)` is not the right API if you need strict control over unmappable/malformed errors in all situations; to **report errors instead of replacing**, create a `CharsetEncoder` and configure `CodingErrorAction.REPORT`.

### 6.1. Strict Encoding Example on Java 17+

Create `StrictEncodingDemo.java`:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictEncodingDemo {
    public static void main(String[] args) {
        CharsetEncoder encoder =
                StandardCharsets.ISO_8859_1.newEncoder()
                        .onMalformedInput(
                                CodingErrorAction.REPORT)
                        .onUnmappableCharacter(
                                CodingErrorAction.REPORT);

        String emoji = "\uD83D\uDE00";
        System.out.println("canEncode="
                + encoder.canEncode(emoji));

        try {
            encoder.encode(CharBuffer.wrap(emoji));
            System.out.println("encoded");
        } catch (CharacterCodingException error) {
            System.out.println("strict="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StrictEncodingDemo.java
java StrictEncodingDemo
~~~

Stdout:

~~~text
canEncode=false
strict=UnmappableCharacterException
~~~

For unrepresentable data, `canEncode` returns `false`, and strict encoding throws `UnmappableCharacterException`. This is the right signal for the business layer to decide whether to reject, ask the user to fix it, or pick another suitable charset.

If the data contains an unpaired surrogate, `MalformedInputException` can occur during strict encoding; that is distinct from a **valid code point not supported by the target charset**.

Do not treat `encoder.canEncode` as an all-purpose security or language validator: it only evaluates encodability for a specific charset and does not guarantee the text meets application requirements.

## 7. Decoding Can Encounter Invalid or Truncated Byte Sequences

In UTF-8, the character `é` is represented by **two bytes** `C3 A9`. If only `C3` is received without a following byte, that is an incomplete UTF-8 sequence. If `C3 28` is received, byte `28` (the `(` character) is not a valid continuation byte after `C3`.

For invalid input, there are two main approaches:

1. **Lenient / replacement:** replace the malformed part with the replacement character `U+FFFD` or another replacement configured on the decoder.
2. **Strict / report:** throw an exception or return an error status so the program rejects invalid data.

Do not mistake `new String(bytes, UTF_8)` for a strict validator. This constructor uses a replacement policy for malformed/unmappable byte sequences. If you need to require **100% valid UTF-8**, use a `CharsetDecoder` with `CodingErrorAction.REPORT` or a file API with a verified error-rejection policy.

### 7.1. Full Example: Lenient and Strict Decoding

Create `StrictDecodingDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodingDemo {
    public static void main(String[] args) {
        byte[] invalid = {
                (byte) 0xC3, (byte) 0x28
        };

        String lenient =
                new String(invalid, StandardCharsets.UTF_8);
        System.out.println("lenient=" + lenient);

        CharsetDecoder decoder =
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(
                                CodingErrorAction.REPORT)
                        .onUnmappableCharacter(
                                CodingErrorAction.REPORT);

        try {
            decoder.decode(ByteBuffer.wrap(invalid));
            System.out.println("decoded");
        } catch (CharacterCodingException error) {
            System.out.println("strict="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 StrictDecodingDemo.java
java StrictDecodingDemo
~~~

Stdout with a standard Unicode console:

~~~text
lenient=�(
strict=MalformedInputException
~~~

In this example, `new String` replaces the invalid byte part with `�` (U+FFFD), while the character `(` is still interpreted. The strict decoder reports `MalformedInputException`, allowing the application to halt processing.

**Policy evaluation:** if you are displaying a file with encoding errors for a user's reference, replacement can be helpful; if you are reading an identifier, legal data, official configuration, or input requiring an exact 100% match, consider rejecting errors rather than silently losing information.

Note that `�` can also be a U+FFFD character **legitimately included in the original data**. Therefore, simply seeing `�` in a `String` is not enough to confirm it was generated by the decoder.

## 8. `ByteBuffer`, `CharBuffer`, and the Two Conversion Engines

In NIO, `CharsetEncoder` and `CharsetDecoder` operate on buffers:

~~~text
Encode: CharBuffer -> CharsetEncoder -> ByteBuffer
Decode: ByteBuffer -> CharsetDecoder -> CharBuffer
~~~

Use this low-level layer when you need:

- Control over `CodingErrorAction`: `REPORT`, `REPLACE`, `IGNORE`.
- Incremental conversion with bounded buffers.
- Integration with `ByteBuffer`/channels or verified performance requirements.
- Distinguishing malformed and unmappable errors by policy.

Simple example using `Charset` APIs:

~~~java
ByteBuffer bytes = StandardCharsets.UTF_8.encode(text);
CharBuffer chars = StandardCharsets.UTF_8.decode(bytes);
String restored = chars.toString();
~~~

This is **only an illustrative snippet inside a method**, requiring imports for `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.StandardCharsets`, and a `String text` variable. It is not a standalone program with `main`.

**Watch buffer positions:** a `ByteBuffer` has `position`, `limit`, and `remaining`. A decoder reads from `position` to `limit`; if a byte buffer has already been consumed and you reuse it without calling `flip`/`rewind` properly, the result may be empty or incomplete. Do not confuse resetting buffer positions with a data transcoding operation.

In streaming, a multi-byte UTF-8 sequence can be split across the boundary between two buffers. A stateful decoder must follow the proper `decode` / `flush` protocol, or you should use `InputStreamReader`/higher-level APIs so they manage boundaries for you. Do not decode each chunk independently with `new String(chunk, UTF_8)` and concatenate them: if a chunk splits between `C3` and `A9`, two separate decodes can produce replacement characters.

## 9. Why Are Character Encoding/Decoding Not Base64, Compression, or Encryption?

Terms meaning “encoding/encryption” are often overloaded:

| Operation | Input → output | Purpose |
| --- | --- | --- |
| **Character encoding** | `String -> byte[]` in UTF-8 | Represent text as bytes |
| **Character decoding** | `byte[] -> String` in UTF-8 | Interpret bytes as text |
| **Base64 encoding** | `byte[] -> ASCII Base64 string` | Transport bytes over text channels |
| **Compression** | bytes -> typically shorter bytes | Reduce size |
| **Encryption** | plaintext bytes -> ciphertext bytes | Protect confidentiality with algorithm/key |

`StandardCharsets.UTF_8` **does not secure** content: any recipient who knows UTF-8 can decode the data. Base64 is **not encryption** either. If an application transmits sensitive data, TLS, data encryption, access control, and log sanitization belong to a different layer.

Example of handling Base64 in the proper order:

~~~text
Text "Café"
    -> UTF-8 encode to bytes
    -> Base64 encode bytes to "Q2Fmw6k="
    -> Base64 decode back to bytes
    -> UTF-8 decode bytes to "Café"
~~~

Each step solves a distinct task. Do not pass a Base64 string into `new String(..., UTF_8)` expecting the original text: you must Base64-decode it to bytes first.

## 10. Reading and Writing Text Files: Choose the Charset Explicitly

When working with files, the charset must be applied at the **exact conversion point**.

### 10.1. Writing Text to a File

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

This call encodes `text` into UTF-8 bytes and writes them to the file. The file on disk stores **bytes**, not a Java `String` object.

### 10.2. Reading a File into a String

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

This call reads bytes from the file and decodes them using UTF-8. If the file was actually written with another charset, reading it with UTF-8 will not automatically convert it properly.

These snippets are **illustrative code** requiring imports `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, and variables `path`, `text`. To see a complete program with cleanup, use the example below.

### 10.3. Java 17+ Example: UTF-8 File Write/Read Round Trip

Create `FileCharsetDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class FileCharsetDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile(
                "charset-demo-", ".txt");

        try {
            Files.writeString(path, "Caf\u00E9",
                    StandardCharsets.UTF_8);

            String content = Files.readString(
                    path, StandardCharsets.UTF_8);
            byte[] bytes = Files.readAllBytes(path);

            System.out.println("content=" + content);
            System.out.println("hex="
                    + HexFormat.of().formatHex(bytes));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Save `FileCharsetDemo.java` and run:

~~~bash
javac -encoding UTF-8 FileCharsetDemo.java
java FileCharsetDemo
~~~

Stdout:

~~~text
content=Café
hex=436166c3a9
~~~

`Files.createTempFile` creates a temporary file with a different path on each run, but the example **does not print the path**, so the data stdout is deterministic. The `finally` block deletes the temporary file even if read/write steps fail.

**Difference in error behavior:** `Files.readString(path, charset)` can throw `MalformedInputException` when the file does not contain valid text for the chosen charset. This differs from the `new String(bytes, charset)` constructor, which may replace malformed parts. Do not assume every text-reading API shares the same error policy.

### 10.4. Reader/Writer and Streams

When reading a text stream, prefer declaring the charset explicitly:

~~~java
try (var reader = new java.io.InputStreamReader(
        inputStream, StandardCharsets.UTF_8)) {
    // Read characters from reader.
}
~~~

~~~java
try (var writer = new java.io.OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8)) {
    // Write String/char through writer.
}
~~~

Both snippets above are **for illustration inside a method**, assuming an existing `InputStream inputStream` or `OutputStream outputStream`. They are not standalone programs. The reader **decodes a byte stream into characters**; the writer **encodes characters into a byte stream**.

To operate on files by path, you can use `Files.newBufferedReader(path, StandardCharsets.UTF_8)` and `Files.newBufferedWriter(path, StandardCharsets.UTF_8)`. For large data, streaming avoids loading the entire content into RAM, but requires using the decoder/reader consistently across chunks.

## 11. Matching Charsets at Both Ends Is Not Enough If Bytes Were Altered

The rule “encode and decode with the same charset” is necessary, yet you must also ensure:

1. The byte sequence is not truncated, mis-concatenated, or altered in transit.
2. Input characters are representable in the target charset.
3. Conversion does not silently use `REPLACE` mode and lose characters.
4. The file/message encoding is agreed upon or declared accurately.
5. No intermediate layer re-converts the bytes or text incorrectly.

For example, an application might send UTF-8 via an API, yet a proxy, message queue, or database driver in the middle might interpret the bytes with a different charset and corrupt data before the final application decodes it. When handling important Unicode data, inspect **bytes at system boundaries** alongside the declared charset, not only the final displayed string.

For HTTP protocols, `Content-Type`, file metadata, and actual content must be consistent. Do not believe that merely putting `charset=UTF-8` in a header will fix bytes written in another encoding.

## 12. The Environment's Default Charset Can Lead to Bugs

A misleadingly short way to write this is:

~~~java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
~~~

Both overloads omit a charset and use the **default charset** determined by Java for the environment. On JDK 18+, JEP 400 standardizes the default charset to UTF-8 in most default setups, but applications running on other JDKs, custom configurations, legacy libraries, or external tools can still behave differently.

**Do not rely on the default charset for protocols or data that must be exchanged reliably.** Write:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet inside a method**; the variable `text` must exist beforehand. The explicit overload shows that the charset is part of the data contract.

You must also distinguish **Java source file encoding** from **data file encoding** and **console encoding**:

- `javac -encoding UTF-8` tells the compiler to read **`.java` source files** as UTF-8.
- `StandardCharsets.UTF_8` in `getBytes`, `new String`, `Files.writeString` controls **runtime data conversion**.
- A terminal may render characters incorrectly even when the in-program strings and bytes are completely right; font/code page/console configuration is a separate display concern.

Do not alter a valid string just because PowerShell/the terminal displays mojibake; inspect the bytes, code points, and charset at each step.

## 13. UTF-16, BOM, and Byte Order

Java's `String` itself is indexed by UTF-16 code units, yet that does not mean every file Java writes contains **UTF-16 bytes**.

For example:

~~~java
text.getBytes(StandardCharsets.UTF_8);
text.getBytes(StandardCharsets.UTF_16LE);
text.getBytes(StandardCharsets.UTF_16BE);
~~~

These produce three **potentially different byte sequences** for the same text. UTF-16LE and UTF-16BE differ in the order of the two bytes in each code unit, whereas Java's `UTF_16` charset has rules involving the byte-order mark (BOM).

A **BOM** can help some decoders identify byte order or a Unicode encoding variant, but not every UTF-8 file has a BOM. Do not use the BOM as a universal charset auto-detector. If UTF-16 files are required, explicitly specify UTF-16LE/UTF-16BE, BOM or no BOM, and how participating systems read them.

To avoid confusion in typical projects, UTF-8 without a BOM is usually the simplest choice for interchanged text, though **the protocol/file format specification takes precedence** if it mandates a specific encoding.

## 14. Inspect Bytes Instead of Guessing from Text Appearance

When suspecting an encoding bug, an effective debugging workflow is:

1. Pick a short text sample containing non-ASCII characters, such as `é`, `ấ`, or emoji.
2. Determine **whether the data is a String or bytes** at each point.
3. For bytes, print hex using `HexFormat`; for Strings, print code points if needed.
4. Compare the declared charsets at the source and destination.
5. Check whether there was a step decoding to a String with the wrong charset or a second encoding step.
6. Decide on the earliest point to fix without destroying source data.
7. Add regression tests containing real Unicode, not just ASCII.

**ASCII-only tests are insufficient.** For the letter `A`, UTF-8 and ISO-8859-1 both use byte `41`, so charset bugs stay hidden. A test containing `Café` or Vietnamese text exposes mismatches much earlier.

For example, the byte sequence `C3 A9` can mean:

| Decoded as | Result |
| --- | --- |
| UTF-8 | `é` |
| ISO-8859-1 | `Ã©` |

If the original bytes were `E9` in ISO-8859-1, that could represent `é` in that charset, yet it is not a valid UTF-8 sequence. A common mistake is seeing garbled characters and “guessing” the encoding from already-misdecoded text; prioritize **original bytes and metadata** instead of speculation.

## 15. Distinguishing Encode/Decode from Normalization

`java.text.Normalizer` operates at the **Unicode text layer**, for example turning `e + combining acute` into `é` in NFC. It does **not** replace `CharsetEncoder` or `CharsetDecoder`.

There are three distinct transformations to keep separate:

~~~text
UTF-8 bytes -- decode UTF-8 --> String
String -- normalize NFC --> String
String -- encode UTF-8 --> UTF-8 bytes
~~~

If inputs are two canonically equivalent strings with different code point representations, normalization can change the byte count after encoding. Thus even when encoding/decoding are performed correctly, you cannot assume the initial bytes will remain identical if a normalization step is added.

If you need **byte-for-byte preservation**, keep the original bytes before decoding and before any transformation. If you only need **text equivalence**, you can choose normalization according to the data contract. Do not use `new String(bytes, UTF_8)` to fix Unicode normalization issues, nor use NFC to repair bytes decoded with the wrong charset.

## 16. How to Choose a Charset When Designing an Application

In new Java projects, **UTF-8** is generally the right choice for text files and machine-to-machine communication because it supports all Unicode scalar values, represents multilingual text, and is standard across modern ecosystems.

However, when working with legacy data:

- Do not assume all files are UTF-8.
- Look up the encoding specified in the contract, system documentation, metadata, or file producer.
- Some older encodings cannot be reliably identified from bytes alone.
- If a source uses Windows-1252, Shift_JIS, or another charset, configure the decoder to match the source (if supported by the environment), and then you can re-encode to UTF-8 for storage/exchange per policy.
- Avoid decoding with the wrong charset and then encoding as UTF-8, which turns mojibake into “valid” data that is hard to recover.

When converting a legacy file to UTF-8, the proper process is:

~~~text
bytes in legacy charset
       |
       | decode using legacy charset
       v
Unicode String
       |
       | encode using UTF-8
       v
UTF-8 bytes
~~~

This is **transcoding**: decoding with the source charset and then encoding with the target charset. It is not merely renaming a file extension or changing a `charset` header without converting the bytes.

## 17. Common Pitfalls and Fixes

| Pitfall | Consequence | Resolution |
| --- | --- | --- |
| Thinking encode/decode is a single operation | Hard to pinpoint where errors happen | Clarify direction: `String -> bytes` vs. `bytes -> String` |
| Decoding UTF-8 as ISO-8859-1 | `Café` becomes `CafÃ©` | Use the true charset of the original bytes |
| Using `text.length()` to compute byte size | Wrong for Vietnamese/emoji | Compute `getBytes(charset).length` |
| Using `new String(bytes, UTF_8)` as a strict validator | May replace invalid bytes with U+FFFD | Use `CharsetDecoder` with `REPORT` |
| Encoding emoji with Latin-1 without error handling | Character loss due to unmappable chars | Check support or use strict encoder |
| Reading each UTF-8 chunk into a separate String | Splits multibyte sequences | Use stateful streaming decoder/reader |
| Testing only ASCII | Hidden charset bugs | Test Vietnamese diacritics, `é`, emoji |
| Omitting charset on I/O calls | Depends on runtime/system | Use `StandardCharsets.UTF_8` explicitly |
| Assuming `javac -encoding` sets data file charset | Confuses compile-time with runtime | Specify charset in read/write APIs |
| Trusting a charset header when actual bytes differ | Still displays incorrectly | Ensure both metadata and bytes match |
| Re-encoding mojibake once more | Corruption becomes harder to fix | Trace steps back from source bytes |
| Treating UTF-16 code units as UTF-8 bytes | Wrong lengths/buffers | Separate String representation from encoding |
| Confusing Base64 with UTF-8 or encryption | Decoding at the wrong layer | Handle Base64, charset, crypto at proper layers |
| Saving only the post-error String when provenance matters | Original bytes may be unrecoverable | Preserve original bytes/metadata when needed |

## 18. Testing Checklist

A reliable encode/decode test suite should cover:

1. **ASCII**: `"A"` → `41` in UTF-8.
2. **Accented Latin**: `"é"` → `C3 A9` in UTF-8.
3. **Vietnamese**: strings with multiple diacritics and multiple code points within one grapheme.
4. **Non-BMP emoji**: `"😀"` → `F0 9F 98 80` in UTF-8.
5. **Round-trip**: `decode(encode(text, UTF_8), UTF_8)` must equal valid text.
6. **Wrong charset**: UTF-8 bytes of `Café` decoded as ISO-8859-1 yield `CafÃ©`.
7. **Malformed UTF-8**: `C3 28` is rejected by a strict decoder.
8. **Replacement**: `new String` constructor may return `�(` instead of throwing.
9. **Unmappable**: an ISO-8859-1 encoder cannot encode 😀 and reports an error in strict mode.
10. **File I/O**: write/read UTF-8 with `Files.writeString/readString` and verify bytes.
11. **Streaming**: multibyte sequences split at buffer boundaries decode properly when handled statefully.
12. **Default charset**: avoid relying on default when protocols require reproducibility.
13. **UTF-16/BOM**: verify exact byte order and BOM if using this format.
14. **Byte-level integrity**: distinguish normalized data from original bytes.
15. **Error policy**: every malformed/unmappable input has a documented rejection or replacement policy.

### Practice Exercises

- Replace `Café 😀` in `EncodeDecodeDemo` with a heavily accented Vietnamese string, predict the difference between `String.length()` and byte count, and verify in Java.
- Write a `hexUtf8(String text)` function using `HexFormat` to display the byte sequence, then explain why a single code point can require multiple bytes.
- Change `WrongCharsetDemo` from `ISO_8859_1` to another legacy charset (if supported by the JDK) and compare the mojibake representation.
- Create a byte array `{(byte) 0xC3}`; test `new String` and a strict decoder, and explain the missing continuation byte case.
- Call `StandardCharsets.ISO_8859_1.newEncoder().canEncode("😀")` and try encoding with `REPORT`. If you want to write emoji, which charset should you choose?
- Write a file in UTF-8 and try reading it as ISO-8859-1, then compare with reading it back as UTF-8. Afterward, preserve the source bytes and fix it by decoding properly.
- Describe the workflow to convert a legacy file to UTF-8 via **decode legacy charset → encode UTF-8**, explaining why changing only the header is insufficient.
- For a protocol requiring strict UTF-8 text validation, choose a strict decoder and add malformed tests; do not use a lenient constructor as a validator.

## 19. Key Takeaways

**Encode = String/characters → bytes. Decode = bytes → String/characters.** `Charset` is the contract defining the bidirectional mapping, and both ends must agree for data to round-trip accurately. UTF-8 is usually the best choice for multilingual data, though legacy files require their actual source charset.

In Java 17+, use `getBytes(StandardCharsets.UTF_8)` and `new String(bytes, StandardCharsets.UTF_8)` for common cases; use `CharsetEncoder` and `CharsetDecoder` with `CodingErrorAction.REPORT` when you must **detect errors rather than silently replacing them**. When reading/writing files, specify the charset in `Files.readString`, `Files.writeString`, or reader/writer; debug using **byte hex and String code points** rather than guessing from garbled characters.

Do not confuse character encoding with Base64, encryption, compression, normalization, or console rendering. Preserve source bytes when exact integrity is required, and guard conversions at every system boundary.

## Official Documentation

- [Oracle Java 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Oracle Java 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [Oracle Java 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [Oracle Java 21 — CodingErrorAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [Oracle Java 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
