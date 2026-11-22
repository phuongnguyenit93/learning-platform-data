# Distinguishing Binary Data from Text Data in Java I/O

## 1. Same Storage as Bytes, Different Interpretation

In memory, on disk, and over the network, content is ultimately represented as **bytes**. **Text data** is data whose bytes are converted into characters according to a **charset (character encoding)**. **Binary data**, in I/O classification, is typically data interpreted according to the specific byte structure of a format: images, compressed files, integers, protocol records, fixed-length fields...

Therefore, **a text file is also a sequence of bytes**. The difference lies in the *interpretation contract*, not whether a file uses bits:

- For **text**, you must know the charset to encode characters into bytes and decode bytes into characters.
- For **structured binary**, you must know the byte rules: field order, size, endianness, version, or the appropriate parser.
- There are **mixed formats**: an HTTP message has text headers and a body that can contain JSON, ZIP, an image, or arbitrary bytes; a binary file can also contain UTF-8 string fields.

For example, “Aé” has two Unicode code points but occupies three bytes in UTF-8:

~~~text
Character        A        é
Code point       U+0041   U+00E9
UTF-8 hex        41       C3 A9
All bytes        41 C3 A9
~~~

Decoding the byte sequence 41 C3 A9 with UTF-8 produces “Aé”; decoding it with ISO-8859-1 produces “AÃ©”. **Bytes themselves do not indicate their charset**: the application must rely on conventions, specifications, or metadata to determine it.

## 2. Fundamental Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Bit/byte | Raw unit of data, each byte consists of 8 bits | Byte 0x41 |
| Unicode code point | Unicode code representing a character unit | é = U+00E9 |
| Charset/encoding | Rules for converting characters to bytes and vice versa | UTF-8, UTF-16LE, ISO-8859-1 |
| String in Java | Character sequence in memory, without an attached “file charset” | “Aé” |
| File format | Rules for organizing content | CSV, JSON, PNG, ZIP |
| Extension/MIME | Signal/declaration of file type, does not guarantee content | .txt, .png, image/png |

**Java's String.length() counts UTF-16 code units (char)**, not UTF-8 bytes and not always the number of Unicode code points. A code point outside the Basic Multilingual Plane can use two chars (a surrogate pair); a user-perceived character can also consist of multiple combining code points. Use codePointCount(...) to count code points; use getBytes(charset).length or read the actual bytes to know the encoded size.

UTF-8 encodes Unicode into 1–4 bytes per code point; ASCII characters use one corresponding byte. UTF-16LE/UTF-16BE use different rules and byte orders. **BOM (byte order mark)** is an optional marker: the UTF-8 BOM consists of the bytes EF BB BF, and **UTF-8 does not require a BOM**. For UTF-16, a BOM can be used to indicate byte order; without a BOM, the encoding must be known from another source.

Line endings are also bytes: LF = 0A hex, CRLF = 0D 0A hex. Two files displaying the same text can still differ in bytes. When a checksum or digital signature is needed, bytes must be considered; when comparing text semantically, you need to agree on the charset and line-ending/normalization rules.

## 3. In Java, Choose Byte Stream or Character Stream?

| Need | Java API | Key Considerations |
| --- | --- | --- |
| Copy any file while preserving exact bytes | InputStream, OutputStream, Files.copy | Do not go through String |
| Read/write byte data | Files.readAllBytes, Files.write | Does not automatically decode |
| Read/write text | Reader, Writer, Files.readString, Files.writeString | Choose charset explicitly |
| Bridge bytes and characters | InputStreamReader, OutputStreamWriter | Charset is a mandatory part of the contract |
| Read binary structures | DataInputStream, ByteBuffer, parser libraries | Know the schema, byte order, version |

**InputStream/OutputStream work with bytes**; **Reader/Writer work with characters**. InputStreamReader is the *byte → character* bridge, and OutputStreamWriter is the *character → byte* bridge. These bridges understand encoding, but they do **not** automatically decode PNG, ZIP, or protobuf formats.

For text specified as UTF-8, use StandardCharsets.UTF_8 in both directions. When the format requires another charset, use that exact charset. Avoid accidentally relying on the environment's default encoding if the data needs to travel across multiple systems.

## 4. Standalone Runnable Java 17+ Example

Save the following snippet as **BinaryVsTextDemo.java**, UTF-8 source encoding:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class BinaryVsTextDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-text-", ".txt");
        try {
            String original = "Aé";
            Files.writeString(file, original, StandardCharsets.UTF_8);

            byte[] raw = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("utf16Units=" + original.length());
            System.out.println("codePoints="
                    + original.codePointCount(0, original.length()));
            System.out.println("utf8Bytes=" + raw.length);
            System.out.println("hex=" + HexFormat.of().formatHex(raw));
            System.out.println("restored=" + restored);
            System.out.println("roundTrip=" + original.equals(restored));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 BinaryVsTextDemo.java
java BinaryVsTextDemo
~~~

Stdout:

~~~text
utf16Units=2
codePoints=2
utf8Bytes=3
hex=41c3a9
restored=Aé
roundTrip=true
~~~

**Files.writeString** encoded the String into UTF-8 bytes. **Files.readAllBytes** returned the exact three bytes in the file without interpreting them as characters. **Files.readString** used UTF-8 to decode the bytes back into a String. A length of 2 UTF-16 units and 3 UTF-8 bytes do not contradict each other at all. The example creates a temporary file and deletes it in finally, so no machine-dependent path is needed.

readAllBytes/readString are suitable when the data is small enough. For large files, reading the entire file at once can consume a lot of RAM; process sequentially using InputStream/Reader and buffers instead.

## 5. Practical Scenarios

### 5.1. Copying Images, ZIPs, or Any File

When the requirement is to copy the exact content, operate at the byte layer. This is an **illustrative code snippet** placed inside a method that already has two variables Path source and destination, imports Files, and handles IOException:

~~~java
try (var input = Files.newInputStream(source);
     var output = Files.newOutputStream(destination)) {
    input.transferTo(output);
}
~~~

transferTo transfers bytes without encoding or decoding. A PNG file starts with a signature consisting of the bytes **89 50 4E 47 0D 0A 1A 0A** (hex); if you process a PNG with Reader and Writer, bytes invalid under the charset can be replaced, corrupting the image file. Renaming .png to .txt does not turn image data into text either.

### 5.2. Reading CSV, JSON, and TXT

If the contract clearly states the data is UTF-8 text, decode the bytes into a String:

~~~java
String json = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is only a **code snippet** assuming Path path and appropriate imports are already present. It performs **decoding**, not **parsing**. JSON requires a JSON parser; CSV requires a parser that handles quotes, delimiters, and newlines inside a data field. Charset and format syntax are two separate responsibilities.

### 5.3. Reading Binary Numbers

The text string “1234” has UTF-8 bytes **31 32 33 34**. A 32-bit integer field in a binary format may also take four bytes, but carry a different value and have its own byte order. To read it, you need to know the field length, signed/unsigned, big-endian/little-endian, and version. DataInputStream or ByteBuffer can assist with those operations; they do not automatically guess the schema of an unknown-format file.

### 5.4. Embedding Binary in JSON

If you want to send an image in JSON, you can use **Base64** to convert a byte sequence into an ASCII character string, and then the receiving side decodes Base64 to restore the original bytes. Base64 **does not turn an image into text in terms of the underlying data**, is not compression, and is not security encryption. You should not create a String from arbitrary image bytes using a charset to put into JSON because of the risk of altering bytes.

### 5.5. Mixed Content

A binary format can contain file names, notes, or metadata as UTF-8 strings; conversely, a JSON document can contain a Base64 field of an image. In each case, use the format-appropriate parser first, then apply decoding to the fields that the specification defines as text.

## 6. Invalid Bytes and Detecting Charset Errors

If the bytes C3 A9 of “é” are decoded as ISO-8859-1, the character will appear as “Ã©” (mojibake). If an invalid UTF-8 byte sequence is passed through new String(bytes, StandardCharsets.UTF_8), the malformed character may be replaced with **U+FFFD**. If it is then re-encoded and written to a file, the original bytes may be unrecoverable.

To **reject** invalid bytes instead of accepting replacements, use CharsetDecoder with CodingErrorAction.REPORT.

Create the file **StrictUtf8Demo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Demo {
    public static void main(String[] args) {
        byte[] input = {(byte) 0xC3, (byte) 0x28};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            decoder.decode(ByteBuffer.wrap(input));
            System.out.println("valid UTF-8");
        } catch (CharacterCodingException e) {
            System.out.println("invalid UTF-8");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictUtf8Demo.java
java StrictUtf8Demo
~~~

Stdout:

~~~text
invalid UTF-8
~~~

Byte C3 requires a continuation byte according to UTF-8 rules; byte 28 is not a valid continuation byte. The decoder throws an error, and the program prints “invalid UTF-8”. However, **a valid UTF-8 byte sequence is not enough to prove it is text**: binary content can coincidentally consist of valid UTF-8 bytes.

## 7. Identifying File Types Without Complete Information

There is no 100% universal test based solely on byte content to assert “this is text” or “this is binary”. The bytes **41 42 43** could represent the letters “ABC” in ASCII/UTF-8, but could also be three bytes of a binary record.

A reasonable workflow:

1. **Check the data contract**: API documentation, schema, protocol, Content-Type and charset when trustworthy, or metadata from the file source.
2. **Verify the format**: header, magic bytes, version, parser; the extension is only a hint and can be changed.
3. **If determined to be text**, choose the required encoding; use a reporting decoder if integrity needs to be protected.
4. **If still unclear**, keep the original as bytes, inspect a hex dump, or ask for the specification; do not open it in a text editor and save it with a guessed encoding.

Characteristics such as 00 bytes, printable character ratio, control characters, and BOM are **only heuristics**. UTF-16 text can contain 00 bytes; binary files can contain many visible text strings. Checking UTF-8 validity tests *one encoding*, not a parser that recognizes all files.

## 8. Common Mistakes and How to Avoid Them

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Deciding based solely on .txt/.bin | Misclassification if the extension is changed | Use schema, metadata, and signature |
| Using Reader/Writer to copy images | May alter bytes, corrupting the image | Copy using a byte stream |
| Not specifying a charset for text | Vietnamese characters display incorrectly on other environments | Choose the charset for both reading and writing |
| Using String.length() as the byte count | Incorrect for multi-byte characters/surrogate pairs | Count bytes after encoding |
| Ignoring newlines and BOM | Different bytes/checksums despite identical visual display | Define conventions from the start |
| Treating valid UTF-8 as proof of text | Misidentifying the format | Use the contract and a parser |
| Reading a very large file into byte[] | High RAM usage | Stream/buffer in chunks |
| Treating Base64 as encryption | Misunderstanding security | Use Base64 only as a byte representation |

## 9. Self-Check with Answers

**Question 1.** “Aé” has 2 code points but 3 UTF-8 bytes: does Java lose data?  
**Answer:** No. A takes 1 byte and é takes 2 UTF-8 bytes; if written and read with the same charset, the string is restored accurately.

**Question 2.** Can you copy a ZIP file using a byte stream without understanding ZIP?  
**Answer:** Yes. Copying raw bytes does not require a format parser; understanding the structure is only needed when inspecting/modifying the contents inside the ZIP.

**Question 3.** Can a file without a BOM be UTF-8?  
**Answer:** Yes. A UTF-8 BOM is optional, not required.

**Question 4.** Is successful UTF-8 decoding enough to conclude a file is text?  
**Answer:** No. Binary data can also coincidentally be a valid UTF-8 sequence.

**Question 5.** Why shouldn't you use new String(imageBytes, UTF_8) to put an image into JSON?  
**Answer:** Invalid bytes can be replaced. Use Base64 to represent and accurately restore every byte.

**Question 6.** Does Files.readString(path, UTF_8) parse CSV/JSON syntax?  
**Answer:** No. The method only decodes bytes into a String; a separate parser is needed to understand the file's fields.

**Key takeaway:** Always determine the **format and charset** before interpreting bytes. Java byte streams are used to process/preserve bytes; Java character streams are used to process characters according to a chosen charset.