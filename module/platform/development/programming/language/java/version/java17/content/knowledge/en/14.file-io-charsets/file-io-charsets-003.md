# Explicitly Choosing a Charset for Data Exchange in Java 17

## 1. Why Must You Specify a Charset?

When a program writes strings to a file, sends them over a network, or reads data from another system, the data crosses the boundary between **characters** and **bytes**. Java represents text in a `String` using the UTF-16 model, whereas files and protocols typically transmit a sequence of bytes. A **charset** defines the mapping between characters and bytes during encoding or decoding.

If two sides use different charsets, the same byte sequence can be interpreted as different characters. Common symptoms include corrupted accented characters, characters replaced with `�`, unparseable content, or data silently changing when saved and read back.

For example, the string `"Xin chào"` can be encoded into UTF-8:

~~~java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text); // Xin chào
~~~

What matters is that both sides of the conversion use the same agreed-upon charset. For exchanged data, choose the charset specified by the protocol or file format, and pass it explicitly to Java APIs. Do not rely on the local machine's configuration to guess how a peer will read the data.

After this lesson, learners should be able to:

1. Distinguish characters, code points, `String`, bytes, and charsets.
2. Explain why the writer and reader must agree on a charset.
3. Use `StandardCharsets.UTF_8` and charset-accepting overloads of file and reader/writer APIs.
4. Identify APIs that use the platform's default charset and avoid them at data-exchange boundaries.
5. Choose an appropriate policy when input bytes are invalid or unrepresentable in the target charset.
6. Verify round-trips, BOMs, newlines, and real-world Unicode data cases.

## 2. Characters, Bytes, and Charsets Are Three Distinct Concepts

### 2.1. A Java String Is Not a Byte Array

`String` is a sequence of characters following Java's UTF-16 model. A `String` is not synonymous with a UTF-8 file or a byte array with a fixed encoding.

~~~java
String message = "Việt Nam";
int length = message.length();
byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
~~~

- `message` is text data inside Java.
- `message.length()` counts UTF-16 code units, not necessarily the number of user-perceived characters.
- `utf8` contains the bytes produced using the UTF-8 charset.
- A single `String` can be encoded into different byte sequences if different charsets are chosen.

Do not call `String.length()` to deduce the number of bytes that will be written. Byte count depends on both the charset and the content.

### 2.2. Encoding and Decoding

Two conversion directions:

~~~text
String (Java) --encode with Charset--> byte[]
byte[]         --decode with Charset--> String (Java)
~~~

Example:

~~~java
String original = "Tiếng Việt: ă, â, ê, ô, ơ, ư";

byte[] data = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);

System.out.println(original.equals(restored)); // true
~~~

If bytes were encoded with UTF-8, they must be decoded with UTF-8. Using another charset can produce an incorrect string even though the original bytes are unchanged.

### 2.3. A Charset Is an Exchange Contract

A protocol or file format should specify:

- Which charset is used (for example, UTF-8).
- Whether a BOM is allowed and how it is handled.
- How invalid byte sequences are handled.
- Conventions for newlines, delimiters, and special characters.
- Whether Unicode normalization is required.

Not all data has to use UTF-8, though UTF-8 is the common and suitable choice for most new text-exchange formats. If a protocol specifies another charset, follow the protocol rather than changing it arbitrarily.

## 3. UTF-8 and Built-in Charsets in Java

### 3.1. Using StandardCharsets

Java provides standard charset constants in `java.nio.charset.StandardCharsets`:

| Constant | Charset | General Characteristics |
|---|---|---|
| `StandardCharsets.UTF_8` | UTF-8 | Variable-length Unicode encoding from 1 to 4 bytes per code point; standard choice for data exchange |
| `StandardCharsets.UTF_16` | UTF-16 | Unicode encoding using one or two UTF-16 code units; byte-order conventions may involve a BOM |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | UTF-16 with big-endian byte order |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | UTF-16 with little-endian byte order |
| `StandardCharsets.ISO_8859_1` | ISO-8859-1 | Single-byte character set; cannot represent all Unicode characters |
| `StandardCharsets.US_ASCII` | US-ASCII | 7-bit ASCII character set; cannot represent accented characters such as Vietnamese |

In Java 17 applications, you should usually write:

~~~java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Constants in `StandardCharsets` prevent typos in charset names and make choices explicit in code. If another charset is needed by name, use `Charset.forName("...")` after verifying that the runtime supports it.

### 3.2. UTF-8 Does Not Mean One Character Equals One Byte

UTF-8 encodes code points in a variable number of bytes:

| Example | Code point | UTF-8 byte count |
|---|---|---:|
| `A` | U+0041 | 1 |
| `é` | U+00E9 | 2 |
| `ệ` | U+1EC7 | 3 |
| `😀` | U+1F600 | 4 |

Therefore, you must never slice a UTF-8 byte array at an arbitrary position and assume the remainder is still valid text. If splitting data by bytes, split on code point boundaries or use a proper framing protocol.

### 3.3. UTF-8 and ASCII

UTF-8 bytes for ASCII characters preserve the exact ASCII byte values. This allows many text formats and protocols structured around ASCII characters to work smoothly with Unicode payloads. However, non-ASCII characters may require multiple bytes.

Do not use `US_ASCII` for text with accented or non-ASCII characters such as Vietnamese. Characters unrepresentable in the target charset will cause an error or replacement depending on the API and encoder policy.

## 4. Explicitly Selecting a Charset When Working with Files

### 4.1. `Files.writeString` and `Files.readString`

`Files.writeString` and `Files.readString` were introduced in Java 11. The overloads without a charset parameter use UTF-8 by API contract; the overloads taking `Charset` let you state the choice directly at the data-exchange boundary.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");
        String content = "Xin chào Java 17";

        Files.writeString(path, content, StandardCharsets.UTF_8);
        String loaded = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println(content.equals(loaded)); // true
    }
}
~~~

Passing the charset explicitly lets code readers see the file's byte encoding immediately. Even though the charset-free overloads of these two methods use UTF-8, specifying the charset explicitly helps document the contract, especially when code handles multiple data formats.

### 4.2. `Files.newBufferedReader` and `Files.newBufferedWriter`

For line-by-line processing or large files, use buffered readers and writers:

~~~java
Path path = Path.of("report.txt");

try (var writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("First line");
    writer.newLine();
    writer.write("Second line");
}

try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

`try-with-resources` ensures the reader and writer are closed on completion or on error. `newLine()` writes the current OS line separator; if a protocol requires a fixed newline such as LF or CRLF, write the exact character sequence specified rather than relying on `newLine()`.

### 4.3. `Files.readAllLines`

~~~java
List<String> lines = Files.readAllLines(
        Path.of("input.txt"),
        StandardCharsets.UTF_8);
~~~

This method reads the entire file into a list of lines. For very large files, consider `Files.lines(path, charset)` to stream lines and close the stream properly:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

`Files.lines` returns a `Stream` backed by a file resource; it must be closed with `try-with-resources`. Simply calling a terminal operation does not fulfill the responsibility of closing the stream.

## 5. Selecting a Charset When Working with Reader and Writer

### 5.1. `InputStreamReader`

`InputStreamReader` bridges a byte stream to a character stream. Its constructor accepts an explicit charset:

~~~java
try (var reader = new InputStreamReader(
        inputStream, StandardCharsets.UTF_8)) {
    // Read characters decoded as UTF-8.
}
~~~

If you use the constructor taking only `InputStream`, the platform's default charset is used. That can cause the exact same byte sequence to be decoded differently across environments.

### 5.2. `OutputStreamWriter`

`OutputStreamWriter` converts characters into bytes:

~~~java
try (var writer = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
~~~

Close the writer or flush when appropriate to ensure data is pushed down to the byte stream. In real applications, stream ownership and closing responsibilities must be clear: if a wrapper owns the stream, closing the wrapper closes the underlying stream.

### 5.3. `FileReader` and `FileWriter`

With file-based reader/writer APIs, choose constructors that accept a charset:

~~~java
try (var reader = new FileReader(file, StandardCharsets.UTF_8);
     var writer = new FileWriter(outputFile, StandardCharsets.UTF_8)) {
    // Read/write characters using UTF-8.
}
~~~

Constructors accepting `Charset` are available in Java 17. When writing new code, `Files.newBufferedReader` and `Files.newBufferedWriter` are often more convenient because they operate directly on `Path` and have explicit charset overloads.

## 6. Avoiding the Platform Default Charset at Exchange Boundaries

### 6.1. Calls That Introduce Environment Dependencies

The following forms do not specify a charset:

~~~java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);

InputStreamReader reader = new InputStreamReader(inputStream);
OutputStreamWriter writer = new OutputStreamWriter(outputStream);
~~~

They rely on the platform's default charset or equivalent default mechanism. Across different Java 17 environments, that default may not match.

Replace them with:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);

InputStreamReader reader =
        new InputStreamReader(inputStream, StandardCharsets.UTF_8);
OutputStreamWriter writer =
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
~~~

### 6.2. Java 17 and the Default Change in Java 18

In Java 17, `Charset.defaultCharset()` reflects the runtime environment's default charset; do not assume it is always UTF-8. JEP 400 changed Java's default to UTF-8 starting in JDK 18, but an application targeting Java 17 must still treat the platform default as environment-dependent configuration.

You can inspect the current value for diagnostics:

~~~java
System.out.println(Charset.defaultCharset());
~~~

This is diagnostic information, not a way to determine which charset an external partner uses. Never design a protocol around "the sender uses its machine's default charset and the receiver uses its machine's default charset."

### 6.3. Do Not Fix Issues by Changing the JVM-Wide Default Charset

Global settings can affect other libraries and APIs in the same process. A more durable approach is to specify the charset at every read/write point that has a defined contract:

~~~java
Files.writeString(path, payload, StandardCharsets.UTF_8);
String payload = Files.readString(path, StandardCharsets.UTF_8);
~~~

One program may work with multiple formats simultaneously: UTF-8 exchange payloads, a legacy file in a specified charset, and other internal content. Do not force all data into a single encoding via a global default configuration.

## 7. Malformed Encoding Data and Error-Handling Policies

Not every byte sequence is valid UTF-8. A sequence may contain an invalid continuation byte, be truncated at the end, or encode a value disallowed by UTF-8.

### 7.1. Decoding with `new String` Can Replace Corrupted Data

The constructor:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

does not provide a detailed error-reporting mechanism for malformed input; invalid sequences are replaced with the replacement character according to the internal charset decoder's behavior. Therefore, if an application needs to **reject malformed data**, do not rely solely on constructing a `String` and inspecting it visually.

### 7.2. Using CharsetDecoder with REPORT

When strict validation is required, use `CharsetDecoder` and configure it to report errors:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String decoded = decoder.decode(ByteBuffer.wrap(bytes)).toString();
~~~

If the data contains malformed or unmappable sequences, decoding throws `CharacterCodingException`. This is appropriate when data comes from partners, import files, or protocols where encoding errors must be detected rather than silently replaced.

Policies of `CodingErrorAction`:

| Policy | Behavior |
|---|---|
| `REPORT` | Reports an error by throwing `CharacterCodingException` |
| `REPLACE` | Replaces malformed data with the replacement value |
| `IGNORE` | Drops malformed data |

`REPORT` is usually suitable when validating exchange data. `REPLACE` or `IGNORE` should only be used when business requirements permit data loss and the system intends that behavior.

### 7.3. Encoding with CharsetEncoder

Similarly, if a Java string contains characters unrepresentable in the target charset, the encoder can report an error, replace them, or ignore them depending on its policy.

~~~java
var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer encoded = encoder.encode(CharBuffer.wrap("Tiếng Việt"));
~~~

The snippet above throws an exception because US-ASCII cannot represent Vietnamese accented characters. This is the right outcome if the protocol truly only accepts ASCII: the program catches the violation rather than transmitting substituted characters.

If the protocol requires UTF-8, choose UTF-8 from the start instead of forcing Unicode text into ASCII.

## 8. BOM and Leading File Bytes

A BOM (*Byte Order Mark*) is a marker at the start of a byte stream, commonly seen in some Unicode files. For UTF-8, the BOM byte sequence is `EF BB BF`; it is unnecessary for determining byte order because UTF-8 has only one byte order, unlike UTF-16.

When using `StandardCharsets.UTF_8`, do not assume the BOM will be stripped automatically. Standard UTF-8 decoders may decode the three BOM bytes into the character U+FEFF at the start of the `String`. If the file format allows a BOM and the application wants to remove it, handle it explicitly at the read boundary:

~~~java
static String removeLeadingBom(String text) {
    if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
        return text.substring(1);
    }
    return text;
}
~~~

Do not strip U+FEFF everywhere in the text. Only handle a leading stream BOM according to the data specification; U+FEFF appearing elsewhere may be actual content or data requiring separate inspection.

With UTF-16, byte order and BOM play a different role; if a protocol specifies UTF-16BE or UTF-16LE, choose the exact charset specified.

## 9. Newlines and Text Formatting Are Also Part of the Contract

Choosing the right charset still does not guarantee both sides interpret content identically if newline conventions or formatting differ.

Common characters:

| Name | Java Literal | Code point | Meaning |
|---|---|---|---|
| LF | `\n` | U+000A | Line feed |
| CR | `\r` | U+000D | Carriage return |
| CRLF | `\r\n` | U+000D U+000A | Newline pair |

`BufferedReader.readLine()` strips line terminators from each returned line string. `BufferedWriter.newLine()` writes the current platform's line separator. If an exchange format requires specific LF or CRLF endings, write and verify them accurately:

~~~java
String payload = "first\nsecond\n";
Files.writeString(path, payload, StandardCharsets.UTF_8);
~~~

The snippet above writes LF characters in `payload`. Do not replace them with `newLine()` if the protocol mandates LF on all operating systems.

## 10. Complete Data-Exchange Example

The following example simulates writing and reading a UTF-8 file, verifying the content via string comparison, and printing the encoded bytes:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class Main {
    public static void main(String[] args) throws IOException {
        Path file = Path.of("exchange.txt");
        String message = "Xin chào — tiếng Việt: ă, â, ê, ô, ơ, ư";

        // Sender: choose UTF-8 according to the exchange contract.
        Files.writeString(file, message, StandardCharsets.UTF_8);

        // Receiver: use the exact agreed-upon charset.
        String received = Files.readString(file, StandardCharsets.UTF_8);

        System.out.println(message.equals(received)); // true
        System.out.println(received);

        byte[] encoded = message.getBytes(StandardCharsets.UTF_8);
        System.out.println(HexFormat.of().formatHex(encoded));
    }
}
~~~

Compile and run on JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Depending on the content and terminal encoding, console display of accented characters may vary by console setup. However, the comparison in the program verifies the `String` content after reading as UTF-8; the hex string shows the exact encoded bytes.

To simulate a charset mismatch, you can intentionally decode UTF-8 bytes with US-ASCII or another incompatible charset and compare with the original string. For unrepresentable characters, the result may contain replacement characters or raise an error when using a strict decoder.

## 11. Example with Byte Streams and Reader/Writer

When communicating over sockets, HTTP bodies, or APIs that only expose `InputStream`/`OutputStream`, bridge to characters with an explicit charset:

~~~java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

try (var writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)) {
    writer.write("status=ready\n");
    writer.flush();
}

try (var reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8)) {
    char[] buffer = new char[1024];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Process exactly `count` characters read.
    }
}
~~~

In real applications, you should not necessarily close the underlying stream here if it is managed by an outer layer. Respect the API's resource ownership rules. The key point is that **the charset is selected at the layer converting bytes to characters and back**, never guessed from the terminal or host machine.

## 12. Charsets in Protocols and Exchange Formats

### 12.1. HTTP

In HTTP, the charset can be defined by the content format and headers. When sending or receiving text, follow the contract of the media type and client/server API. Do not assume every body is UTF-8 if the protocol or headers specify otherwise; likewise, do not use the host machine's charset as a substitute for protocol metadata.

If an application produces a UTF-8 body:

~~~java
byte[] body = json.getBytes(StandardCharsets.UTF_8);
~~~

then the declared content type must be consistent with the body bytes, such as a JSON media type according to system conventions. When receiving, read the body bytes using the charset defined by the format.

### 12.2. JSON, CSV, and XML

- **JSON:** the modern ecosystem overwhelmingly uses UTF-8; adhere to the specification and the parser/serializer API in use. A text block or `String` does not automatically become valid JSON.
- **CSV:** you must agree on charset, delimiter, quoting rules, newlines, and headers. Two UTF-8 CSV files can still differ in structure.
- **XML:** the encoding declared in the XML declaration must match the actual bytes. A proper XML parser should be given the byte stream to inspect the declaration according to XML rules, rather than pre-decoding with the wrong charset and passing a corrupted `String`.

Do not choose a charset out of habit if the incoming data already has its own specification. The charset is part of the data contract alongside syntax and framing.

## 13. Testing and Validating Exchanged Data

### 13.1. Round-Trip Testing Alone Does Not Prove Protocol Compliance

If the same program encodes and decodes with the same charset, a round-trip can succeed:

~~~java
String original = "Café";
String decoded = new String(
        original.getBytes(StandardCharsets.UTF_8),
        StandardCharsets.UTF_8);
~~~

This proves the API pair is compatible for the test input. It does not prove that the external peer also uses UTF-8, nor does it validate BOM, newline, or normalization rules.

### 13.2. Verifying Actual Bytes

~~~java
byte[] bytes = "Aé".getBytes(StandardCharsets.UTF_8);
System.out.println(HexFormat.of().formatHex(bytes)); // 41c3a9
~~~

`A` has UTF-8 byte `41`; `é` (U+00E9) has UTF-8 bytes `C3 A9`. Using a byte dump verifies how data is encoded without depending on display fonts.

### 13.3. Checking Decode Errors

For external data, decide explicitly:

1. Should malformed data be rejected?
2. Is replacement with U+FFFD allowed?
3. Should the offending offset or source be logged?
4. Is there an input size limit to avoid reading oversized payloads?
5. Does the charset come from trusted configuration or protocol metadata?

For critical business data, it is usually best to use a strict decoder to detect errors early. Do not silently drop or replace characters if doing so could alter identifiers, signatures, monetary amounts, or control fields.

## 14. Common Mistakes

### 14.1. Using Parameterless `getBytes()` for Data Transmission

~~~java
byte[] bytes = message.getBytes(); // Depends on default charset.
~~~

Fix:

~~~java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
~~~

### 14.2. Writing UTF-8 but Reading with Another Charset

If you write with UTF-8 and read with a different charset, content will be corrupted. Maintain one charset contract throughout:

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

### 14.3. Assuming Java 17 Always Defaults to UTF-8

Java 17 does not yet have the universal UTF-8 default standardized in Java 18. Do not rely on the platform default when exchanging data.

### 14.4. Using ASCII for Non-ASCII / Vietnamese Text

ASCII cannot represent Vietnamese diacritics or other non-ASCII Unicode characters. Use an appropriate charset such as UTF-8 if the format allows it.

### 14.5. Confusing Bytes and Characters

A UTF-8 code point can occupy multiple bytes; do not slice a byte array using character indices. Process text after decoding or use well-defined byte framing.

### 14.6. Ignoring Malformed Input

If data is corrupted, replacing or ignoring errors can alter content without the system noticing. Choose a `CodingErrorAction` that matches the contract and integrity requirements.

### 14.7. Stripping BOM Anywhere in Text

Only handle a leading stream BOM according to the format. Never remove every U+FEFF character unconditionally from the content.

### 14.8. Assuming UTF-8 Solves All Text Differences

UTF-8 standardizes byte encoding, but does not standardize newlines, Unicode normalization, delimiters, quotes, BOMs, or data structure. Those rules must still be specified separately.

## 15. Practice Exercises

### Exercise 1 — Writing and Reading UTF-8

Write a program that writes the string `"Lập trình Java 17 — tiếng Việt"` to a file using UTF-8, then reads it back with UTF-8. Verify `original.equals(restored)`.

Hint:

~~~java
Files.writeString(path, original, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

### Exercise 2 — Inspecting Bytes

Encode `"Aé"` using UTF-8 and print its hex representation using `HexFormat.of().formatHex(bytes)`. Explain why the output is `41c3a9`.

### Exercise 3 — Detecting the Default Charset

Print `Charset.defaultCharset()` in your Java 17 environment. Explain why that value must not be used as a contract for files or protocols exchanged with another machine.

### Exercise 4 — Strict Decoder

Create an invalid UTF-8 byte array (for example, a standalone continuation byte), decode it with `CharsetDecoder` using `CodingErrorAction.REPORT`, and handle `CharacterCodingException`. Compare this with `new String(bytes, UTF_8)`.

### Exercise 5 — BOM

Create a byte sequence starting with `EF BB BF` followed by UTF-8 content. Decode it, check whether the first character is U+FEFF, and strip it only if the file format specifies a leading BOM.

### Exercise 6 — Protocol-Defined Newlines

Write content with explicit LF using `Files.writeString`. Read it back and verify `endsWith("\\n")`. Explain why `BufferedWriter.newLine()` can produce different line separators on different platforms.

## 16. Completion Criteria

Learners have mastered this lesson when they can:

1. Explain the role of charsets in converting between `String` and `byte[]`.
2. Use `StandardCharsets.UTF_8` on both the write and read sides of exchanged data.
3. Use charset-accepting overloads of `Files`, `InputStreamReader`, `OutputStreamWriter`, or corresponding readers/writers.
4. Identify APIs that depend on the default charset and explain why they should not be used at protocol boundaries.
5. Distinguish Java 17's default behavior from the UTF-8 default change in Java 18.
6. Handle malformed/unmappable input with `CharsetDecoder`/`CharsetEncoder` and an appropriate `CodingErrorAction`.
7. Explain BOMs, newlines, and the distinction between bytes, code units, and code points.
8. Verify round-trips and actual bytes rather than relying solely on console output or both sides running inside the same program.
9. Choose a charset based on the file/protocol specification and keep it consistent across systems.

## 17. Official Documentation

- [Java SE 17 API — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): built-in standard charsets.
- [Java SE 17 API — `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): charsets, canonical names, default charset, and factories.
- [Java SE 17 API — `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) and [`CharsetEncoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): decoding/encoding and error-handling policies.
- [Java SE 17 API — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): reading/writing strings, readers, writers, and streams with charsets.
- [Java SE 17 API — `InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) and [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): bridges between byte streams and character streams.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change in JDK 18; useful for understanding why Java 17 requires care with platform defaults.

**Remember:** exchanged data consists of bytes governed by a specific contract. Select the charset from the specification, declare it explicitly at encode/decode sites, validate malformed input, and inspect actual bytes. UTF-8 is a widespread choice, but correctness comes from both sides following the same contract—not from assumptions about the machine running the code.
