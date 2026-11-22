# Charset, StandardCharsets, and Explicit UTF-8 Selection in Java

A Java `String` can contain Vietnamese, Japanese, and emoji; however, when **writing to a file, sending over a network, or receiving bytes from another system**, the program must convert between **characters** and **bytes**. If both sides do not use the same character encoding, data can become corrupted into strings such as `"ChÃ o"`, question marks `?`, or the replacement character `�`. Localization is not only about choosing a `Locale` for numbers/dates: Unicode content must cross **charset boundaries** properly.

In Java 17+, `java.nio.charset.Charset` represents a character encoder/decoder; `java.nio.charset.StandardCharsets` provides predefined standard charset objects, most importantly **`StandardCharsets.UTF_8`**. Passing UTF-8 **explicitly** to APIs that accept a charset keeps file and API contracts independent of the host machine, locale, or JDK version.

**Core principle:** identify the exact boundary where data transitions from `String` to `byte[]` and vice versa. Every such boundary must use the charset defined by the **data contract**, rather than guessing from the appearance of text or `Locale.getDefault()`.

This lesson moves from the concept of `Charset` and the six required `StandardCharsets` to Java 17+ examples with `String`, `Files`, `Reader/Writer`, `InputStream/OutputStream`, encode/decode error handling, UTF-8 BOM, legacy `Properties`, differences between JDK 17 and JDK 18+, and round-trip testing.

## 1. Unicode Characters, String UTF-16, and UTF-8 Bytes Are Three Layers

Suppose a text source contains:

```text
Aé😀
```

This consists of **three Unicode code points**:

| Character | Code point | UTF-16 code units in Java String | UTF-8 bytes |
| --- | --- | --- | --- |
| `A` | `U+0041` | 1 | `41` |
| `é` | `U+00E9` | 1 | `C3 A9` |
| `😀` | `U+1F600` | 2 (surrogate pair) | `F0 9F 98 80` |

Thus this string has `String.length() == 4`, `codePointCount(0, length()) == 3`, while the byte count after UTF-8 encoding is **7**. You cannot use `String.length()` to predict UTF-8 file length or HTTP payload size.

`String` is a **sequence of characters**; in Java APIs, the indices of `charAt` and `substring` are based on **UTF-16 code units**, not UTF-8 bytes. Charset only comes into play when **encoding/decoding** between characters and bytes. Changing `Locale` does not automatically change byte encoding; changing charset does not automatically translate words or reformat dates/times.

### Bidirectional Diagram

```text
Java String                  byte[] / file / HTTP body
    |                                ^
    | encode with UTF-8              |
    +------------------------------->|
    |   String.getBytes(UTF_8)       |
    |                                |
    |<-------------------------------+
    | decode with UTF-8
    |   new String(bytes, UTF_8)
```

When the writer encodes as UTF-8 while the reader **decodes as ISO-8859-1 or Windows-1252**, the bytes still exist but are mapped to different characters: that is **mojibake**. When an encoding cannot represent a character (for example, an emoji in ISO-8859-1), the encoder may replace it with `?` or throw an error depending on the API and policy.

## 2. How Do Charset and StandardCharsets Differ?

`Charset` is an **object type** describing the mapping between byte sequences and characters. You can look up a charset by name:

```java
Charset utf8 = Charset.forName("UTF-8");
Charset latin1 = Charset.forName("ISO-8859-1");
```

This is a **Java fragment**, requiring `import java.nio.charset.Charset;`. Charset names have aliases and are case-insensitive in lookup; `charset.name()` returns the canonical name. When the name comes from configuration, verify support and handle `IllegalCharsetNameException` or `UnsupportedCharsetException` instead of assuming valid input.

`StandardCharsets` is a utility class containing **static Charset constants** for the six standard charsets that Java is required to support. No runtime string lookup is needed:

| Constant | Characteristics, use cases |
| --- | --- |
| `StandardCharsets.US_ASCII` | 7-bit ASCII; cannot directly represent accented Vietnamese characters |
| `StandardCharsets.ISO_8859_1` | Latin-1; each byte 0x00–0xFF maps to a character in the corresponding range |
| `StandardCharsets.UTF_8` | Variable-length Unicode byte encoding; the de facto standard choice for files/APIs |
| `StandardCharsets.UTF_16` | UTF-16, handling byte-order mark and byte order per the charset definition |
| `StandardCharsets.UTF_16BE` | UTF-16 big endian |
| `StandardCharsets.UTF_16LE` | UTF-16 little endian |

**When the contract requires UTF-8**, prefer `StandardCharsets.UTF_8` over `Charset.forName("UTF-8")`: it is a self-documenting constant, avoids mistyping the string name in multiple places, and is guaranteed by Java to be available.

**However**, `Charset.forName(...)` remains useful when you must support legacy input whose encoding name is declared in metadata—for example, a file sent by an external party in Windows-1258 or a specialized charset. Do not hardcode charset guessing if the file has no contract.

### First Demo — CharsetBasicsDemo.java

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetBasicsDemo {
    public static void main(String[] args) {
        String text = "A\u00E9\uD83D\uDE00";
        Charset utf8 = StandardCharsets.UTF_8;
        byte[] bytes = text.getBytes(utf8);

        System.out.println("Charset: " + utf8.name());
        System.out.println("Same charset: "
                + utf8.equals(Charset.forName("utf-8")));
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: " + bytes.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ")
                        .withUpperCase().formatHex(bytes));
        System.out.println("Round trip: "
                + text.equals(new String(bytes, utf8)));
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 CharsetBasicsDemo.java
java CharsetBasicsDemo
```

Stdout:

```text
Charset: UTF-8
Same charset: true
UTF-16 units: 4
Code points: 3
UTF-8 bytes: 7
Hex: 41 C3 A9 F0 9F 98 80
Round trip: true
```

Here `HexFormat` is a built-in API since **Java 17**. The sequence `\uD83D\uDE00` in the source code is a valid surrogate pair producing the emoji `U+1F600`. The hex output proves the byte count: **1 + 2 + 4 = 7**, independent of locale.

The `javac -encoding UTF-8` option only specifies the **charset of the `.java` source file** read by the compiler; it **does not automatically change** the charset of files the application reads or writes at runtime. These are two different encoding boundaries.

## 3. UTF-8 Is an Encoding, Not a Locale

A `Locale` such as `vi-VN`, `en-US`, or `ja-JP` describes the language/regional context for formatting numbers, dates, display-name rules, or selecting translation bundles. **UTF-8** describes how Unicode code points are encoded into bytes.

You can:

- Use `Locale.FRANCE` while **writing files in UTF-8**.
- Use `Locale.forLanguageTag("vi-VN")` while **reading JSON in UTF-8**.
- Display dates using `Locale.GERMANY` and then send an ISO date field `2026-10-28` as **UTF-8**.
- Read a legacy file in ISO-8859-1 if **the file contract says so**, even if the content is meant to be displayed in Vietnam.

**There is no mapping of “Vietnamese uses one dedicated encoding, Japanese uses another”** for modern Unicode applications. UTF-8 supports all encoded Unicode languages; choosing the locale for the UI is a separate decision.

In addition, **UTF-8 does not normalize Unicode automatically**. Two canonically equivalent strings, such as `U+00E9` and `U+0065 U+0301`, are both valid when encoded but produce different bytes. If business logic requires canonical equivalence, additionally use `java.text.Normalizer` according to policy—do not expect the encoder to perform NFC on its own.

## 4. Do Not Rely on the Default Charset for APIs with External Contracts

Java has `Charset.defaultCharset()`, which reflects the runtime default charset. However, when you write:

```java
byte[] bytes = text.getBytes();
String restored = new String(bytes);
```

both calls **omit the charset** and use the JVM's **default charset** for these overloads. If the file or bytes were produced in another environment, there is no guarantee the other side decodes with the same encoding.

For bytes under a UTF-8 contract, write:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

The snippets above are **fragments**, requiring `text` and the corresponding imports. For valid environments and strings, this UTF-8 pair can round-trip Unicode characters without depending on the default locale.

### How Does JDK 17 Differ from JDK 18+?

- **Java 17 and earlier:** the default charset typically depends on the operating system, locale, and runtime configuration; you must not assume it is always UTF-8.
- **Java 18 and later:** [JEP 400](https://openjdk.org/jeps/400) specifies UTF-8 as the default charset for Java SE APIs within its scope, with documented configuration options and exceptions. Therefore, many calls without an explicit charset behave more consistently on newer JDKs.
- **Even so, use explicit UTF-8 for protocols/files with contracts**: code may still be run on Java 17, older APIs have exceptions, legacy systems use other encodings, and consumers still need the contract to be clear.

**Do not infer the terminal/stdout encoding solely from `Charset.defaultCharset()`.** Consoles, shells, IDEs, and runtime environments can encode or render text differently. If a string inside the program holds valid Unicode but the terminal shows question marks or garbled characters, check the console encoding, font, terminal renderer, and output pipeline rather than blindly modifying the input file.

### Example Observing the Default Charset Without Assuming Output

**`DefaultCharsetInfo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class DefaultCharsetInfo {
    public static void main(String[] args) {
        System.out.println("Default: "
                + Charset.defaultCharset().name());
        System.out.println("Explicit: "
                + StandardCharsets.UTF_8.name());
    }
}
```

```bash
javac -encoding UTF-8 DefaultCharsetInfo.java
java DefaultCharsetInfo
```

The second line is always `Explicit: UTF-8`; the first line varies by JDK and environment configuration, so no single default value is listed as the stdout for every machine. This program is for **diagnostics**, not for choosing an encoding for new files by reading the default.

## 5. Files.writeString and Files.readString: Choosing UTF-8 Explicitly

Java NIO provides convenient APIs for text files:

```java
Files.writeString(path, content, StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);
```

This is a **fragment** where `path` is a `Path` and `content` is a `String`; it requires importing `java.nio.file.Files`, `Path`, and `java.nio.charset.StandardCharsets`.

**Important note about overloads:** `Files.writeString(path, content)` and `Files.readString(path)` in Java 17 **already use UTF-8 per their specification**, not the operating system's default charset. Passing `StandardCharsets.UTF_8` is still helpful to make the contract explicit and eases switching to other APIs. Do not claim that **every overload without a Charset** in Java uses the default charset: some newer NIO APIs default to UTF-8, whereas many older Reader/Writer/`String.getBytes()` constructors/methods take the default charset.

### Standalone Program — Utf8FilesDemo.java

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FilesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("utf8-demo-", ".txt");
        String original = "Tiếng Việt: Chào bạn!";

        try {
            Files.writeString(file, original, StandardCharsets.UTF_8);
            String restored =
                    Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Equal: "
                    + original.equals(restored));
            System.out.println("UTF-8 bytes: "
                    + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 Utf8FilesDemo.java
java Utf8FilesDemo
```

The output of the `Equal` line is always `true` if writing and reading succeed. The `UTF-8 bytes` line is the actual byte length of the string, which does **not** equal the number of UTF-16 units when accented Vietnamese characters are present. You can compute it directly in your IDE to compare with `original.getBytes(StandardCharsets.UTF_8).length`; the example above does not hardcode the stdout of the byte-count line because its goal is to illustrate the byte-counting principle.

**I/O error note:** in production, you must handle write permissions, paths, disk space, atomic file updates, and cleanup; the example only uses a temporary file and deletes it in `finally`. If data comes from an untrusted source, check size limits before reading an entire file into memory.

### BufferedReader and BufferedWriter

When files are large or need line-by-line processing, use:

```java
try (BufferedReader in =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = in.readLine()) != null) {
        // Process a line.
    }
}

try (BufferedWriter out =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    out.write("Chào");
    out.newLine();
}
```

This is a **fragment**; it requires `BufferedReader`, `BufferedWriter`, `Files`, `Path`, and `StandardCharsets`. `newLine()` uses the platform's line separator, so if a machine-readable format requires **fixed LF**, replace it with `out.write('\n')` and specify the newline in the contract.

**The overload `Files.newBufferedReader(path)` also uses UTF-8**, though the overload with a charset makes the code self-explanatory. Some APIs like `Files.lines(path, UTF_8)` return a stream that must be closed with try-with-resources when reading a file.

## 6. Byte Streams and Character Streams: Know the Exact Conversion Point

Java divides I/O into two main groups:

| Group | APIs | Data handled directly |
| --- | --- | --- |
| Byte stream | `InputStream`, `OutputStream`, `Files.readAllBytes` | Raw bytes; **not** inherently aware of UTF-8 text |
| Character stream | `Reader`, `Writer`, `BufferedReader`, `BufferedWriter` | Characters; must **decode/encode** when bridged to a byte stream |
| Bridge | `InputStreamReader`, `OutputStreamWriter` | Uses a `Charset` to convert byte ↔ char |

Use:

```java
Reader reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8);
```

This is a fragment with `inputStream`/`outputStream` already declared. Do not omit the `StandardCharsets.UTF_8` parameter if the contract requires UTF-8: the constructors `new InputStreamReader(inputStream)` or `new OutputStreamWriter(outputStream)` may pick the **default charset** instead of explicit UTF-8.

### Byte Stream ↔ Character Stream Example

Save **`Utf8StreamBridgeDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

public class Utf8StreamBridgeDemo {
    public static void main(String[] args) throws Exception {
        String expected = "Chào Việt Nam";
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (OutputStreamWriter writer = new OutputStreamWriter(
                buffer, StandardCharsets.UTF_8)) {
            writer.write(expected);
        }

        byte[] wire = buffer.toByteArray();
        StringBuilder result = new StringBuilder();

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(wire),
                StandardCharsets.UTF_8)) {
            char[] chars = new char[64];
            int n;
            while ((n = reader.read(chars)) != -1) {
                result.append(chars, 0, n);
            }
        }

        System.out.println("Round trip: "
                + expected.contentEquals(result));
        System.out.println("Bytes match UTF-8: "
                + java.util.Arrays.equals(
                        wire,
                        expected.getBytes(StandardCharsets.UTF_8)));
    }
}
```

```bash
javac -encoding UTF-8 Utf8StreamBridgeDemo.java
java Utf8StreamBridgeDemo
```

Stdout:

```text
Round trip: true
Bytes match UTF-8: true
```

You must `flush()` or `close()` the writer before retrieving all bytes, because the encoder may buffer data temporarily. In the example, the try-with-resources block closes the writer before `toByteArray()`. `ByteArrayOutputStream.toByteArray()` still works after the writer closes the stream because `ByteArrayOutputStream.close()` does not invalidate subsequent calls.

If input comes from a network, enforce length limits/timeouts and protocol framing; `Reader` does not determine JSON message or TCP record boundaries in place of a protocol parser.

## 7. APIs Without a Charset Parameter: Distinguish Each Case Properly

Do not apply a blanket rule that “omitting Charset is wrong” without checking the **API contract**. Here is an important checklist on Java 17:

| API/overload | Encoding rule to know | Choice under a UTF-8 contract |
| --- | --- | --- |
| `String.getBytes()` | Uses default charset | `getBytes(StandardCharsets.UTF_8)` |
| `new String(byte[])` | Uses default charset | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(stream)` | Uses default charset | `new InputStreamReader(stream, UTF_8)` |
| `new OutputStreamWriter(stream)` | Uses default charset | `new OutputStreamWriter(stream, UTF_8)` |
| `new FileReader(file)` (Java 17) | Uses default charset | Constructor taking Charset or `Files.newBufferedReader(path, UTF_8)` |
| `new FileWriter(file)` (Java 17) | Uses default charset | Constructor taking Charset or `Files.newBufferedWriter(path, UTF_8)` |
| `Files.readString(path)` | **UTF-8**, specified | `Files.readString(path, UTF_8)` to make contract clear |
| `Files.writeString(path, text)` | **UTF-8**, specified | `Files.writeString(path, text, UTF_8)` |
| `Files.newBufferedReader(path)` | **UTF-8**, specified | Overload with charset when clarity is desired |
| `Files.newBufferedWriter(path)` | **UTF-8**, specified | Overload with charset when clarity is desired |
| `Files.readAllBytes(path)` | **No decode**, returns bytes | Decode afterward with contract Charset |
| `Files.write(path, byte[])` | **No encode**, writes bytes | Encode beforehand if source is String |

The goal of **explicitly choosing UTF-8** is to clarify the byte/char boundary and preserve file/API reproducibility, not to claim that all methods missing a charset argument behave identically.

**Do not confuse** `Locale.getDefault(Locale.Category.FORMAT)` with `Charset.defaultCharset()`. Formatting locale and default charset are two different pieces of information; you should not define a charset solely from the user's locale.

## 8. Decoding with the Wrong Charset Causes Mojibake, Not Just a Font Bug

The same byte array can be interpreted as different code points depending on the charset. For example, the letter `é` in UTF-8 consists of two bytes `C3 A9`. If you decode those two bytes as `ISO-8859-1`, the result is the two characters `Ã©` instead of `é`.

**File `MojibakeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class MojibakeDemo {
    public static void main(String[] args) {
        String expected = "\u00E9";
        byte[] utf8 = expected.getBytes(StandardCharsets.UTF_8);

        String correct = new String(utf8, StandardCharsets.UTF_8);
        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 hex: "
                + HexFormat.ofDelimiter(" ")
                        .withUpperCase().formatHex(utf8));
        System.out.println("Correct: " + correct.equals(expected));
        System.out.println("Wrong: " + wrong.equals(expected));
        System.out.println("Wrong UTF-16 length: " + wrong.length());
        System.out.println("Wrong code points: "
                + wrong.codePointCount(0, wrong.length()));
    }
}
```

```bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
```

Stdout:

```text
UTF-8 hex: C3 A9
Correct: true
Wrong: false
Wrong UTF-16 length: 2
Wrong code points: 2
```

Explanation: wrong decoding does not make the input bytes disappear; it **produces a different string**. If that wrong string is encoded and saved again multiple times, the mojibake can compound. Find the true charset of the source and decode **once properly**; do not fix every text by replacing `"Ã"` or `"Â"` with regex.

**Note:** ISO-8859-1 maps every byte 0x00–0xFF, so it can produce “broken-looking” text without throwing an exception. UTF-8 has stricter byte validity rules and can report errors if input violates the encoding. However, a valid UTF-8 byte stream can still contain invalid business content; encoding validity ≠ data validity.

## 9. Malformed Input and Unmappable Characters: REPLACE vs. REPORT

There are two distinct error categories:

- **Malformed input on decode:** bytes do not conform to the declared charset's rules, such as a UTF-8 leading byte `C3` not followed by a valid continuation byte.
- **Unmappable character on encode:** a Unicode character cannot be represented in the target charset, such as an emoji when encoding to ISO-8859-1.

Some convenience APIs like `new String(bytes, StandardCharsets.UTF_8)` may **replace invalid byte sequences** with the Unicode replacement character `U+FFFD` instead of throwing an exception. `String.getBytes(charset)` may replace unrepresentable characters with a replacement byte. For data requiring exact preservation, silent replacement can be risky.

`CharsetDecoder` and `CharsetEncoder` let you configure the policy:

| Policy | Behavior |
| --- | --- |
| `CodingErrorAction.REPORT` | Reports error via `CharacterCodingException` and subtypes |
| `CodingErrorAction.REPLACE` | Replaces error with replacement character/byte |
| `CodingErrorAction.IGNORE` | Skips error; risk of data loss |

`Charset.newDecoder()`/`newEncoder()` create **stateful**, non-thread-safe objects; by default they handle errors with `REPORT`, and can be configured via `onMalformedInput` and `onUnmappableCharacter`.

### Strict UTF-8 Decoding

**File `StrictUtf8DecoderDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;

public class StrictUtf8DecoderDemo {
    public static void main(String[] args) {
        byte[] invalid = {(byte) 0xC3, (byte) 0x28};
        String replaced = new String(
                invalid, StandardCharsets.UTF_8);

        System.out.println("Has replacement: "
                + replaced.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalid));
            System.out.println("Unexpected acceptance");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict decoder rejected bytes");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictUtf8DecoderDemo.java
java StrictUtf8DecoderDemo
```

Stdout:

```text
Has replacement: true
Strict decoder rejected bytes
```

When you need to **forbid invalid UTF-8 data** in imports/APIs, use a `REPORT` decoder or an I/O API with an appropriate error-reporting contract instead of manually checking the resulting string for `�`. The `U+FFFD` character itself can legitimately appear in source text, so inspecting the decoded string alone cannot distinguish whether it came from bad bytes or was intentionally entered by a user.

### Encoding to a Charset Without Full Unicode Support

**File `StrictEncoderDemo.java`**:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;

public class StrictEncoderDemo {
    public static void main(String[] args) {
        String value = "A\uD83D\uDE00"; // A😀

        byte[] lossy = value.getBytes(
                StandardCharsets.ISO_8859_1);
        System.out.println("Lossy bytes: " + lossy.length);
        System.out.println("Lossy is A?: "
                + new String(lossy,
                        StandardCharsets.ISO_8859_1)
                        .equals("A?"));

        try {
            StandardCharsets.ISO_8859_1.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(value));
            System.out.println("Unexpected acceptance");
        } catch (CharacterCodingException ex) {
            System.out.println("Strict encoder rejected character");
        }
    }
}
```

```bash
javac -encoding UTF-8 StrictEncoderDemo.java
java StrictEncoderDemo
```

Stdout with Java's standard encoder:

```text
Lossy bytes: 2
Lossy is A?: true
Strict encoder rejected character
```

Emoji cannot be represented in ISO-8859-1, so convenience encoding can produce `?`; the strict encoder throws an error. **UTF-8** can encode every valid Unicode scalar value, though a Java `String` can also contain invalid lone surrogates; a strict encoder can still report malformed input when encountering them.

**Designing safe imports:** decide whether files with invalid bytes should be rejected, quarantined, repaired, or shown with replacement characters. Do not use `IGNORE` for identifiers/transaction codes that require exact preservation.

## 10. Byte Order Mark (BOM) in UTF-8

UTF-8 has no big/little byte order like UTF-16, so **a BOM is unnecessary to determine endianness**. Some UTF-8 files still start with three bytes:

```text
EF BB BF
```

When decoded as UTF-8, this sequence corresponds to the character **`U+FEFF`** at the start of the string. Many parsers or editors have policies to detect/strip the BOM, but **you should not assume every Java API strips it automatically**. If the file contract forbids a BOM, reject or handle it explicitly.

### BOM Detection Demo

**`Utf8BomDemo.java`**:

```java
import java.nio.charset.StandardCharsets;

public class Utf8BomDemo {
    public static void main(String[] args) {
        byte[] bytes = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                (byte) 'A'
        };

        String decoded = new String(
                bytes, StandardCharsets.UTF_8);

        System.out.println("Length: " + decoded.length());
        System.out.println("Starts with BOM char: "
                + decoded.startsWith("\uFEFF"));
        System.out.println("After explicit removal: "
                + decoded.substring(1).equals("A"));
    }
}
```

```bash
javac -encoding UTF-8 Utf8BomDemo.java
java Utf8BomDemo
```

Stdout:

```text
Length: 2
Starts with BOM char: true
After explicit removal: true
```

Only strip `U+FEFF` **if it appears at the leading position and the format's contract permits BOM handling**. Do not use `replace("\uFEFF", "")` across the entire text as a universal policy. For JSON and other protocols, follow the format/parser specification instead of mutating the payload without a contract.

**UTF-16 has a different BOM and byte-order story:** `UTF_16`, `UTF_16BE`, and `UTF_16LE` are not freely interchangeable. If an external system requires UTF-16LE without a BOM, use the exact constant and verify how the corresponding decoder handles it; do not think a UTF-8 BOM is mandatory like in some UTF-16 formats.

## 11. When Legacy APIs Do Not Use UTF-8 by Default

A common trap is **`java.util.Properties.load(InputStream)`**. By Java's contract, this method reads byte-oriented `.properties` files using ISO-8859-1, supporting Unicode via `\uXXXX` escapes in the traditional properties format. If you feed raw UTF-8 bytes directly, you can get **mojibake** without any exception thrown.

Conversely, `Properties.load(Reader)` accepts **characters already decoded by the Reader**, so you can use `InputStreamReader(..., StandardCharsets.UTF_8)` to read UTF-8 content matching the file configuration.

### Runnable Program — PropertiesEncodingDemo.java

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class PropertiesEncodingDemo {
    public static void main(String[] args) throws Exception {
        byte[] input = "title=caf\u00E9\n"
                .getBytes(StandardCharsets.UTF_8);

        Properties latin1 = new Properties();
        latin1.load(new ByteArrayInputStream(input));

        Properties utf8 = new Properties();
        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(input),
                StandardCharsets.UTF_8)) {
            utf8.load(reader);
        }

        System.out.println("InputStream correct: "
                + "caf\u00E9".equals(
                        latin1.getProperty("title")));
        System.out.println("Reader UTF-8 correct: "
                + "caf\u00E9".equals(
                        utf8.getProperty("title")));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesEncodingDemo.java
java PropertiesEncodingDemo
```

Stdout:

```text
InputStream correct: false
Reader UTF-8 correct: true
```

**Important:** do not apply the statement “Java 18+ defaults to UTF-8” to alter the fixed contract of `Properties.load(InputStream)`. This API specifies its own charset and does not depend on the JVM's default charset.

`ResourceBundle`/`PropertyResourceBundle` has its own special rules: on Java 9+, `PropertyResourceBundle(InputStream)` tries UTF-8 first and falls back to ISO-8859-1 if UTF-8 decoding hits malformed/unmappable bytes (unless an encoding configuration is specified). Therefore **do not equate `Properties.load(InputStream)` with `PropertyResourceBundle(InputStream)`** even though both can read `.properties` files. Always check the documentation for the exact API and version you deploy.

## 12. Choosing the Right Charset When Receiving External Content

Not all data is UTF-8. For example, a partner sends a legacy file declaring ISO-8859-1, or an older system exports in a Windows code page. The proper rules are:

1. **Identify the source's contract**: charset, format, schema, whether a BOM is present, and error handling.
2. **Validate/accept the charset**: if the charset name is in metadata, you may call `Charset.forName(...)` after checking a whitelist of supported encodings.
3. **Decode once from raw bytes** using the chosen charset, with `REPORT`/`REPLACE` error behavior per policy.
4. **Convert to the in-memory Unicode model**: `String`/typed objects; validate business rules.
5. **Encode on output** using the target protocol's charset, typically UTF-8 in modern systems.
6. **Log the conversion** if auditing is required; never silently replace unrepresentable characters.

**Do not pick an encoding by trying candidates until one throws no error and concluding it is right.** ISO-8859-1 can decode any byte, yet the result can still be semantically wrong. Successful UTF-8 decoding likewise does not guarantee the data has the intended content. Charset detection is heuristic without metadata; rely on authoritative sources or explicit rules.

For protocol content with mandatory charset rules (JSON, HTTP payloads per content-type and specification, fixed-encoding files), **follow the protocol** rather than letting users pick arbitrary charsets.

### Example When a Configurable Charset Is Needed

```java
Charset sourceCharset = Charset.forName(
        configuredCharsetName);
String text = Files.readString(path, sourceCharset);
```

This is a **fragment**, assuming `configuredCharsetName` has passed policy checks and importing `java.nio.charset.Charset`, `java.nio.file.Files`. Do not pass a charset name from user input directly into an unbounded pipeline without file-type/size limits; also handle unsupported charset and malformed input errors.

## 13. UTF-8 with JSON, CSV, HTTP, and Databases

### JSON and HTTP

When an application serializes JSON, use a **JSON library** instead of manual string concatenation. In modern HTTP systems, JSON is exchanged in **UTF-8** per format and protocol rules; `application/json` is the appropriate media type. Do not use a locale-dependent `NumberFormat` to write JSON numbers: JSON has its own numeric grammar and does not use grouping separators like `1.234,50`.

`Charset` handles **the bytes of JSON**, while the serializer handles **escaping, data types, and JSON structure**. UTF-8 does not replace JSON escaping and does not decide whether a field is a number, string, boolean, or ISO date.

### CSV and Tabular Text

CSV requires a complete contract: **UTF-8**, delimiter, quoting, newline, header, and schema. For instance, a person's name field containing a comma must be quoted according to CSV rules; using UTF-8 alone is not enough for a parser to split columns accurately. When the consumer is spreadsheet software with a different default locale, do not change decimal formatting in machine-readable columns to match the server's decimal separator.

### Database

In JDBC, pass **typed** data via `PreparedStatement`, such as `setString` for Unicode text, `setBigDecimal` for decimals, and `setObject` for `LocalDate` when supported by the driver, rather than formatting strings and concatenating SQL. Connection/database/driver charset and collation can affect storing and comparing Unicode, but that is a **separate infrastructure contract**; `StandardCharsets.UTF_8` when writing files does not by itself dictate the encoding of a database column.

### Network Streams

`Socket.getInputStream()` and `getOutputStream()` return **byte streams**. Wrapping them in UTF-8 `InputStreamReader`/`OutputStreamWriter` is only suitable for **text-based protocols** where protocol framing is clear. When sending length-prefixed messages in bytes, the length prefix must be the **encoded byte count**, not `String.length()`.

## 14. Charset and Performance When Processing Large Volumes of Data

`StandardCharsets.UTF_8` is a reusable `Charset`. However, **`CharsetEncoder` and `CharsetDecoder` are stateful objects**; do not share the same instance across threads without explicit synchronization. When processing many files, create a separate decoder/encoder per use or per task lifecycle.

Whole-file APIs like `Files.readString` are convenient, but unsuitable for very large files or unbounded untrusted inputs. `BufferedReader`/`BufferedWriter` or NIO channels with buffers support streaming; you must account for UTF-8 multibyte boundaries:

```text
Code point 😀 = F0 9F 98 80

Chunk 1: F0 9F
Chunk 2: 98 80

Cannot decode each chunk independently and concatenate Strings
without maintaining proper decoder state.
```

If you use `InputStreamReader`, Java maintains decoder state to handle characters whose bytes are split across stream reads. If you manually use `CharsetDecoder` on a `ByteBuffer` chunk by chunk, you must handle `CoderResult.UNDERFLOW`, leftover bytes, end-of-input, and `flush` properly. Do not apply `new String(chunkBytes, UTF_8)` independently to each chunk when a chunk may split a multibyte sequence.

**When speed matters:** measure with realistic workloads and specifically verify byte counts and error strings—do not revert to a legacy charset under the misconception that one byte/char is always faster; data safety and interoperability outweigh unproven micro-optimizations.

## 15. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| `getBytes()` and `new String(bytes)` without specifying charset for exchanged data | Depends on JVM default | Use `StandardCharsets.UTF_8` |
| Treating `Locale.forLanguageTag("vi-VN")` as UTF-8 | Locale is not an encoding | Choose Locale and Charset independently |
| Using `String.length()` as HTTP UTF-8 Content-Length | Wrong for accented letters/emoji | Compute actual byte length |
| Reading UTF-8 as ISO-8859-1 | Mojibake `Ã©` | Decode with the source's true charset |
| Encoding Vietnamese to ASCII/Latin-1 and ignoring replacement | Character loss | UTF-8 or strict `REPORT` encoder |
| Assuming all APIs without a charset behave alike | `Files.readString` differs from `FileReader` on Java 17 | Check overload contract |
| Assuming Java 18+ makes every library always use UTF-8 | Legacy APIs specify their own encodings | Analyze each API accurately |
| Using `Properties.load(InputStream)` directly for UTF-8 files | ISO-8859-1 decoding corrupts strings | `load(Reader)` with UTF-8 or proper bundle API |
| Using `InputStreamReader(stream)` on HTTP files with UTF-8 contract | Default charset is not guaranteed to be UTF-8 | Pass UTF-8 |
| Mixing up `UTF_16LE` and `UTF_16BE` | Wrong byte order | Use exact charset and BOM policy |
| Stripping `U+FEFF` everywhere | Improperly mutates data | Strip leading BOM only if contract permits |
| Relying on `Charset.isSupported(...)` to detect file encoding | Only tells if JVM supports charset, not if file uses it | Use source metadata/contract |
| Assuming UTF-8 automatically fixes Unicode NFC/NFD | Normalization differs from encoding | Use `Normalizer` separately when needed |
| Using `CodingErrorAction.IGNORE` on IDs | Silently drops bytes/characters | Use `REPORT` and validation |
| Decoding each network chunk independently | Can split multibyte characters | Use streaming Reader/stateful decoder |
| Sharing one `CharsetDecoder` across threads | Decoder is mutable | Create per-use or synchronize explicitly |
| Seeing garbled characters on console and immediately altering source data | Could be terminal/font/output encoding issue | Inspect each byte/char boundary |
| Mixing locale-formatted numbers into JSON numbers | Invalid JSON syntax | Serialize typed JSON data |
| Leaving CSV newlines/quoting undefined | UTF-8 file still parses incorrectly | Define full format contract |
| Not bounding file/user input sizes | Risks memory/resource exhaustion | Enforce byte limits, stream, check errors |

## 16. Practice Exercises

**Exercise 1 — Hex and length.** With `"Aé😀"`, use `String.length`, `codePointCount`, `getBytes(StandardCharsets.UTF_8).length`, and `HexFormat`. Predict `4`, `3`, `7` and the bytes `41 C3 A9 F0 9F 98 80`. Replace `é` with `e\u0301` and explain why the same typical visual rendering produces more bytes: Unicode normalization is a separate concern from charset.

**Exercise 2 — UTF-8 files via two overloads.** Create a temp file with `Files.writeString(path, "Chào", UTF_8)` and read it with `Files.readString(path, UTF_8)`. Compare with the `Files.readString(path)` overload in Java 17. Why are both valid for UTF-8, yet `new FileReader(file)` does not allow the same assumption in Java 17?

**Exercise 3 — Streams.** Run `Utf8StreamBridgeDemo`, then change `UTF_8` in the Reader to `ISO_8859_1` and observe that the string no longer matches the source. Switch back to the same charset on both ends and calculate byte size via `getBytes`.

**Exercise 4 — Invalid bytes.** Use the byte array `C3 28`. Compare `new String(bytes, UTF_8)` with a `REPORT` decoder. In a transaction import system, should you reject the file or replace characters? Write a policy with error codes and the offending byte offset when needed.

**Exercise 5 — Legacy properties.** Run `PropertiesEncodingDemo`. Explain precisely why `load(InputStream)` misreads UTF-8 bytes while `load(Reader UTF-8)` succeeds. Test a valid legacy ISO-8859-1 file and compare behavior; do not conclude that any JDK automatically detects encoding from `.properties`.

**Exercise 6 — BOM.** Take the byte array `EF BB BF 41`, decode as UTF-8, and compare `length`/first code point. Design a CSV file policy: accept a leading BOM or reject it? Never strip `U+FEFF` at arbitrary positions.

**Exercise 7 — Streaming.** Simulate splitting the four UTF-8 bytes of an emoji into two chunks `F0 9F` and `98 80`. Explain why `new String` on each chunk fails; write a version using `InputStreamReader` over a stream containing both chunks or a stateful `CharsetDecoder`.

## 17. Checklist for Explicitly Choosing UTF-8 in Applications

1. **Identify boundaries:** every file, payload, socket, queue, and archive containing text must have a contracted charset.
2. **Choose APIs:** use `InputStream/OutputStream` for bytes; use `Reader/Writer` or `Files` for text; specify UTF-8 at the bridge.
3. **Check overloads:** read docs before assuming defaults. `Files.readString` differs from `String.getBytes()`.
4. **Handle encoding errors:** decide to reject, replace, or migrate; avoid silent character loss.
5. **Control byte counts:** do not confuse UTF-16 length with UTF-8 bytes.
6. **Separate Locale:** format numbers/dates/UI by locale; encode files/APIs in UTF-8.
7. **Check BOM/newline:** does the protocol accept a BOM, require LF/CRLF, or specify an encoding?
8. **Run round-trip tests:** encode, decode, and compare Unicode content with Vietnamese, combining marks, emoji, and invalid bytes.
9. **Test other JDKs/runtimes:** especially where legacy code depends on Java 17's default charset.
10. **Keep config explicit:** use `StandardCharsets.UTF_8` in code or a whitelisted charset mapping when legacy support is needed.

## 18. Official Documentation

- [Java SE 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html): `defaultCharset`, `forName`, encode/decode, charset support.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): the six standard constants.
- [Java SE 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed input, REPORT/REPLACE/IGNORE.
- [Java SE 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html): unmappable characters and encoder state.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader`, and charset overloads.
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `getBytes(Charset)` and byte-array constructors.
- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): difference between `load(InputStream)` and `load(Reader)`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change starting in Java 18.

## 19. Key Takeaways

**`Charset` defines how to encode/decode between Unicode and bytes; `StandardCharsets.UTF_8` is a guaranteed built-in Java constant and should be used explicitly whenever the contract requires UTF-8.** Data in a Java `String` uses UTF-16 indexing, so **String length is not UTF-8 byte length**.

Not all overloads without a Charset share the same default: `String.getBytes()`/`InputStreamReader(stream)` and some legacy I/O depend on the default charset, whereas `Files.readString(path)`/`writeString(path,text)` already specify UTF-8. Java 18+ defaults to UTF-8 under JEP 400 for many APIs, but does not change specialized legacy contracts like `Properties.load(InputStream)`. Choose charsets according to the **data contract**, use strict decoders when character loss is unacceptable, control BOM, newlines, and streaming, and clearly distinguish **charset from locale, Unicode normalization, and JSON/CSV formatting**.
