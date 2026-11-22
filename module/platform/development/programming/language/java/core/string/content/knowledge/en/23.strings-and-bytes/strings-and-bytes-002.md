# `String.getBytes(Charset)` with `Charset` and `StandardCharsets` in Java

In Java, a `String` represents **Unicode text**, while `byte[]` is a byte sequence for transmitting over a network, writing to a file, or feeding into a binary protocol. To convert a string into bytes, the program must choose a **character encoding (charset)**. The `getBytes(Charset)` method performs *encoding* (converting text to bytes); the chosen charset determines the exact output byte sequence.

This lesson explains how to use `String.getBytes(Charset)` together with `java.nio.charset.Charset` or the `java.nio.charset.StandardCharsets` constants, how to decode back, the effects of charsets, data loss, and cases where encoding errors must be controlled. Examples use Java 17+.

## 1. From `String` to `byte[]`: Two Different Representations

```java
import java.nio.charset.StandardCharsets;

String text = "Hello, Java";
byte[] data = text.getBytes(StandardCharsets.UTF_8);
```

The statement above uses **UTF-8** to convert each character of `text` into a byte sequence. `data` is a new `byte[]` array; it is **not** the same object or the same type as `String`. Modifying elements in `data` does not modify the original string.

To convert back to text, use the matching charset:

```java
String restored = new String(data, StandardCharsets.UTF_8);
boolean same = text.equals(restored); // true
```

Flow:

```text
String "Hello, Java"
      │ getBytes(StandardCharsets.UTF_8)
      ▼
    byte[]                 (encoding)
      │ new String(bytes, StandardCharsets.UTF_8)
      ▼
String "Hello, Java"       (decoding)
```

Important rule: **the encoder and decoder must agree on the charset**. Bytes do not carry complete self-identifying information indicating whether they are UTF-8, ISO-8859-1, or UTF-16. When different charsets are used at the two ends, the result can have garbled characters (*mojibake*) or replacement characters.

## 2. `getBytes` Syntax: Which Overload Should You Use?

| API | Behavior | Notes |
| --- | --- | --- |
| `text.getBytes(StandardCharsets.UTF_8)` | Encodes with an explicitly chosen `Charset`. | **Preferred approach** in applications needing predictable results. |
| `text.getBytes(charset)` | Encodes with a `Charset` variable. | Suitable when the charset comes from configuration or a protocol. |
| `text.getBytes("UTF-8")` | Selects the charset by `String` name. | Can throw the checked exception `UnsupportedEncodingException`. |
| `text.getBytes()` | Uses the JVM's **default charset**. | Environment-dependent; avoid for fixed storage/communication formats. |

Key signature to know:

```java
public byte[] getBytes(java.nio.charset.Charset charset)
```

- The `charset` argument must be non-null; passing `null` throws a `NullPointerException`.
- The result is a byte array encoded according to `charset`.
- If the string contains invalid Unicode input or characters that cannot be represented in the chosen charset, **the `getBytes(Charset)` overload defaults to replacing them with the charset's replacement byte sequence**, rather than throwing an exception by default. Therefore, there is a risk of data loss.
- If you need to **detect errors** instead of silently replacing them, use a `CharsetEncoder` configured with `CodingErrorAction.REPORT` (Section 7).

Historical note: the no-argument `getBytes()` uses the default charset; on Java 17 the default charset can depend on the system. Starting in Java 18, the default is UTF-8 under JEP 400 in standard configurations, but applications may run on different environments and settings. **Specifying the charset explicitly** remains the reliable way to satisfy a specific protocol.

## 3. `Charset` and `StandardCharsets`

`Charset` is the type representing a mapping between Unicode characters and bytes (and also provides encoders/decoders). `StandardCharsets` contains **`Charset` constants guaranteed to be available** on every standard Java implementation.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset utf8 = StandardCharsets.UTF_8;
Charset anotherUtf8 = Charset.forName("UTF-8");
boolean equivalent = utf8.equals(anotherUtf8); // true
```

### Common Constants

| Constant | Characteristics | Use Case |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, 1–4 bytes per valid Unicode code point; ASCII-compatible for ASCII characters. | Common choice for APIs, JSON, text files, and multilingual data. |
| `StandardCharsets.US_ASCII` | Represents only 7-bit ASCII characters. | Protocols restricted to the ASCII character set. |
| `StandardCharsets.ISO_8859_1` | Single-byte encoding representing Unicode U+0000–U+00FF. | Compatibility with legacy Latin-1 data. |
| `StandardCharsets.UTF_16` | UTF-16 encoding; Java writes a byte-order mark (BOM) according to this charset's rules. | When a protocol requires UTF-16 with byte-order detection. |
| `StandardCharsets.UTF_16BE` | Big-endian UTF-16, no automatic BOM when encoding. | Binary data explicitly specifying big-endian. |
| `StandardCharsets.UTF_16LE` | Little-endian UTF-16, no automatic BOM when encoding. | Binary data explicitly specifying little-endian. |

**UTF-8 differs from UTF-16:** the same `String` can produce a different byte count, different byte positions, and a different BOM. UTF-16BE/LE use 2 bytes per UTF-16 code unit; supplementary code points use a surrogate pair, corresponding to 4 bytes.

Use `StandardCharsets.UTF_8` instead of `Charset.forName("UTF-8")` when the charset name is known at compile time: clearer intent, no typos in the name, and no string lookup needed.

### When the Charset Name Comes from Configuration

```java
Charset charset = Charset.forName(configuredName);
byte[] payload = text.getBytes(charset);
```

This is an **illustrative snippet**, in which `configuredName` and `text` must already be defined. `Charset.forName(...)` can throw `IllegalCharsetNameException` if the name is invalid or `UnsupportedCharsetException` if the name is valid but unsupported. Charsets outside the standard constants may exist on one JDK but be missing on another; validate configured names.

## 4. Inspecting Actual Bytes: One String, Multiple Charsets

Consider the string `"Aé€"` containing three characters: `A` (U+0041), `é` (U+00E9), and `€` (U+20AC). The `€` character **is not** representable in ISO-8859-1.

| Charset | Output Bytes in Hex | Meaning |
| --- | --- | --- |
| UTF-8 | `41 c3 a9 e2 82 ac` | `A` uses 1 byte; `é` 2 bytes; `€` 3 bytes. |
| ISO-8859-1 | `41 e9 3f` | `A` and `é` are represented; `€` has no mapping so by default it is replaced with `?` (`3f`) in this case. |
| UTF-16BE | `00 41 00 e9 20 ac` | Three 16-bit code units in big-endian byte order. |
| UTF-16 | `fe ff 00 41 00 e9 20 ac` | Has BOM `fe ff` at the beginning per `UTF_16` encoding rules. |

To inspect bytes in a readable hex format in Java 17+, use `java.util.HexFormat`:

```java
String text = "A\u00E9\u20AC";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of().formatHex(bytes);
// "41c3a9e282ac"
```

The snippet above requires importing `java.nio.charset.StandardCharsets` and `java.util.HexFormat`. `HexFormat` only **formats bytes as hex digits for observation**; it does not change the charset or the underlying bytes.

Avoid using `Arrays.toString(bytes)` to read bytes as hex: Java `byte` is a signed integer from -128 to 127; for example, hex byte `c3` shows up as `-61` in decimal. When you need the unsigned byte value, you can use `b & 0xFF`.

## 5. Compilable and Runnable Java 17+ Program

Create the file `CharsetBytesDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetBytesDemo {
    public static void main(String[] args) {
        // Unicode escapes keep the source file independent of special-character input methods.
        String text = "A\u00E9\u20AC"; // A, é, €

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] latin1 = text.getBytes(StandardCharsets.ISO_8859_1);
        byte[] utf16be = text.getBytes(StandardCharsets.UTF_16BE);

        System.out.println("UTF-8: " + HexFormat.of().formatHex(utf8));
        System.out.println("Latin-1: " + HexFormat.of().formatHex(latin1));
        System.out.println("UTF-16BE: " + HexFormat.of().formatHex(utf16be));

        String restored = new String(utf8, StandardCharsets.UTF_8);
        String latin1Restored = new String(
                latin1, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 round trip: " + text.equals(restored));
        System.out.println("Latin-1 round trip: "
                + text.equals(latin1Restored));

        System.out.println("Latin-1 encodes euro: "
                + StandardCharsets.ISO_8859_1.newEncoder()
                        .canEncode("\u20AC"));

        // Emoji outside the BMP: 2 UTF-16 code units but 4 UTF-8 bytes.
        String emoji = "A\uD83D\uDE00";
        System.out.println("Emoji example String.length: " + emoji.length());
        System.out.println("Emoji example UTF-8 bytes: "
                + emoji.getBytes(StandardCharsets.UTF_8).length);

        CharsetEncoder strict = StandardCharsets.ISO_8859_1.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            ByteBuffer encoded = strict.encode(CharBuffer.wrap(text));
            System.out.println("Strict bytes: " + encoded.remaining());
        } catch (CharacterCodingException e) {
            System.out.println("Strict Latin-1: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 CharsetBytesDemo.java
java CharsetBytesDemo
```

Output:

```text
UTF-8: 41c3a9e282ac
Latin-1: 41e93f
UTF-16BE: 004100e920ac
UTF-8 round trip: true
Latin-1 round trip: false
Latin-1 encodes euro: false
Emoji example String.length: 3
Emoji example UTF-8 bytes: 5
Strict Latin-1: UnmappableCharacterException
```

Explanation:

1. `getBytes(StandardCharsets.UTF_8)` preserves the meaning of all three characters; decoding with the same charset yields `true`.
2. ISO-8859-1 can represent `A` and `é`, but cannot represent `€`. With `getBytes(Charset)`, the unmappable character is replaced: after decoding, the original string is gone.
3. `CharsetEncoder.canEncode(...)` returns `false` because the charset cannot encode `€`.
4. `CharsetEncoder` set to `CodingErrorAction.REPORT` detects the error and throws `UnmappableCharacterException`, letting the program stop or report an error instead of losing data.
5. `"A😀"` has `String.length() == 3` because it consists of one code unit for `A` and **two UTF-16 code units** for the emoji, whereas UTF-8 needs 1 + 4 = 5 bytes.

## 6. Measuring Output Bytes of `getBytes(Charset)`

`String.length()` counts UTF-16 code units, while `getBytes(charset).length` counts the number of bytes **after that exact encoding**. For example, `"A😀"` has `length() == 3` but `getBytes(StandardCharsets.UTF_8).length == 5`. If a protocol limits the byte payload, measure the actual `byte[]` about to be sent:

~~~java
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;
~~~

Measure the bytes of the entire JSON/body **after serialization** if the serialization layer may also add escapes or metadata. The lesson **UTF-8 Length Does Not Equal String.length()** shows how to compute byte limits and truncate strings on code point boundaries.

## 7. Unmappable Characters, Malformed Data, and Replacement Policies

### 7.1. `getBytes(Charset)` Replaces Instead of Throwing by Default

For example, `"€".getBytes(StandardCharsets.ISO_8859_1)` cannot accurately represent the euro sign. With the standard constants in the program above, the default output has the replacement byte `3f` (`?`). Once replaced, the original character cannot be recovered merely by decoding with the same charset.

Invalid Unicode input can also occur, such as a `String` containing an **unpaired surrogate** that does not form a valid pair. `getBytes(Charset)` also uses default replacement for that. The fact that Java `String` can hold a surrogate code unit does not mean it is a valid Unicode string to encode.

Do not generalize that the replacement byte is always `3f` for **every** charset; the replacement depends on the charset.

### 7.2. Rejecting Instead of Replacing: `CharsetEncoder`

When character replacement could corrupt business data, encode with an encoder:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ByteBuffer result = encoder.encode(CharBuffer.wrap("Café"));
    // result contains the byte sequence if every character is valid for ASCII.
} catch (CharacterCodingException e) {
    // Log the unencodable data and handle it according to business requirements.
}
```

This is an **illustrative snippet**, requiring imports for `java.nio.ByteBuffer`, `java.nio.CharBuffer`, and `java.nio.charset.*`; the complete program in Section 5 already provides a runnable example. With ASCII, `é` cannot be represented, so the `catch` branch executes.

Common encoder/decoder policies:

- `CodingErrorAction.REPORT`: detect and report an error.
- `CodingErrorAction.REPLACE`: use the configured replacement.
- `CodingErrorAction.IGNORE`: skip invalid input, which can lose content.

If no character loss is allowed, use `REPORT` and handle the exception explicitly.

### 7.3. Decoding Invalid Bytes

`new String(bytes, charset)` also replaces malformed byte sequences with a replacement character by default when needed. For instance, the bytes `c3 28` are not a valid UTF-8 sequence:

```java
byte[] broken = {(byte) 0xC3, (byte) 0x28};

String decoded = new String(broken, StandardCharsets.UTF_8);
// Contains the replacement character U+FFFD before the "(" sign.
```

When an invalid payload must be rejected:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String decoded = decoder.decode(ByteBuffer.wrap(broken)).toString();
} catch (CharacterCodingException e) {
    // Payload is not valid UTF-8; handle or return an error.
}
```

This is also an **illustrative snippet** and requires the relevant imports from `java.nio.*` and `java.nio.charset.*`. Use `CharsetDecoder` if input byte validity is mandatory; a silently replacing decode is not enough to detect corruption.

## 8. Application Use Cases

### 8.1. Sending Text Over the Network or Computing Request Size

```java
byte[] requestBody = jsonText.getBytes(StandardCharsets.UTF_8);
int contentLength = requestBody.length;
```

This snippet assumes `jsonText` is already **valid JSON**. `getBytes` only encodes to bytes; it **does not escape strings or construct JSON**. Pass the appropriate MIME/charset, such as `Content-Type: application/json; charset=utf-8` when required by the protocol/application; do not design a protocol without confirming the charset between parties.

### 8.2. Writing and Reading Text Data

```java
Path path = Path.of("message.txt");
String message = "Hello, Java";
Files.writeString(path, message, StandardCharsets.UTF_8);
String readBack = Files.readString(path, StandardCharsets.UTF_8);
```

This example requires importing `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`, and handling `IOException`. With byte streams, the charset-equivalent approach is writing `message.getBytes(StandardCharsets.UTF_8)` to the file and decoding the bytes when reading. Prefer `Files.writeString/readString` when the purpose is purely text I/O.

### 8.3. Data Requiring a Protocol Charset Other Than UTF-8

When a protocol requires Latin-1, ASCII, or UTF-16LE, use the exact specified charset:

```java
byte[] ascii = "OK".getBytes(StandardCharsets.US_ASCII);
byte[] utf16le = "OK".getBytes(StandardCharsets.UTF_16LE);
```

Both encode the same `"OK"`, yet `ascii` has two bytes `4f 4b`, while `utf16le` has four bytes `4f 00 4b 00`. **Do not arbitrarily substitute UTF-8 for the protocol charset** when the receiver specifies a format.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Calling `text.getBytes()` and assuming it is always UTF-8 | The default charset can depend on the JVM version/configuration. | Use `getBytes(StandardCharsets.UTF_8)`. |
| Encoding as UTF-8 and decoding as Latin-1, or vice versa | The bytes map to different characters. | Specify the charset explicitly and use it consistently on both ends. |
| Using `text.length()` as the number of bytes to send | `String.length()` measures UTF-16 code units. | Use `encoded.length`. |
| Using ISO-8859-1 for Vietnamese, emoji, or characters outside Latin-1 | Many characters cannot be represented; `getBytes(Charset)` may replace them and lose data. | Choose an appropriate charset; if data loss is unacceptable, use an encoder with `REPORT`. |
| Thinking a negative `byte` is an encoding bug | Java `byte` is signed; `-61` has the exact same bits as hex byte `c3`. | Use `HexFormat` or `b & 0xFF`. |
| Using `UTF_16` when the receiver expects raw UTF-16LE without a BOM | UTF-16 includes a BOM and charset-defined byte order by default. | Pick the exact `UTF_16LE` / `UTF_16BE` required by the protocol. |
| Calling `new String(bytes)` and forgetting the charset | The decoder uses the default charset. | Use `new String(bytes, StandardCharsets.UTF_8)`. |
| Using `Arrays.toString(bytes)` as a string to transmit/write to a file | That is a text representation of the array, not the raw byte data. | Send `byte[]` directly through a byte API, or use a binary-to-text encoding like Base64 when needed. |
| Using `getBytes` as a security encryption solution | Character encoding provides neither confidentiality nor authentication. | If security is needed, use appropriate cryptographic APIs after defining the input bytes. |

### Be Careful When Using Bytes for Matching or Hashing Content

Two visually identical strings can have different **sequences of code points**, such as `"\u00E9"` (one character `é`) and `"e\u0301"` (`e` plus a combining acute accent). When UTF-8 encoded, their bytes differ. If the system requires a normalized Unicode form before comparing/hashing/signing, you can use `java.text.Normalizer` per the protocol's specific rules before calling `getBytes`. Only normalize when that is an agreed requirement; do not silently alter original data.

## 10. Self-Check

**Question 1.** Why is `"A".getBytes(StandardCharsets.UTF_8).length == 1`, while `"😀".getBytes(StandardCharsets.UTF_8).length == 4`?

**Answer:** UTF-8 uses a variable number of bytes per code point. ASCII `A` uses one byte; the non-BMP emoji `😀` uses four bytes.

**Question 2.** Can `getBytes(StandardCharsets.ISO_8859_1)` convert every Unicode `String` without data loss?

**Answer:** No. ISO-8859-1 represents only a limited character set. `getBytes(Charset)` replaces unmappable characters; use another charset like UTF-8 or a `REPORT` encoder to detect them.

**Question 3.** Software receives bytes `41 c3 a9` from a source explicitly labeled UTF-8. How should it decode them?

**Answer:** `new String(bytes, StandardCharsets.UTF_8)` produces the string `"Aé"` if the byte array contains those exact three hex values.

**Question 4.** When do you choose `StandardCharsets.UTF_8` and when do you choose `Charset.forName(name)`?

**Answer:** Use the constant `StandardCharsets.UTF_8` when the charset is fixed in code. Use `Charset.forName(name)` when the charset name comes dynamically from configuration or a protocol, with validation that the name is supported.

**Question 5.** Why does `new String(text.getBytes(UTF_8), UTF_8)` not guarantee a round-trip for **every** `String` that Java can construct?

**Answer:** A string containing an unpaired surrogate is invalid Unicode input; `getBytes(Charset)` may replace it instead of preserving that code unit. For valid Unicode text with UTF-8 on both ends, round-tripping preserves content.

## 11. Takeaways When Applying

- Determine the **charset from the data specification**, typically UTF-8 when both sides agree.
- Encode with `text.getBytes(charset)` and decode with `new String(bytes, charset)`.
- Use `StandardCharsets` for common charsets guaranteed to be supported by Java.
- Do not equate `String` length with `byte[]` length; check payload size after encoding.
- When losing or replacing characters is not allowed, use `CharsetEncoder` / `CharsetDecoder` with `CodingErrorAction.REPORT`.

Java 17 standard documentation: [`String.getBytes(Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [`Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html), [`StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
