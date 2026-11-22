# Why shouldn't you use character streams to copy binary data?

## 1. The core issue: copying data must preserve every byte

When copying a **PNG, JPEG, PDF, ZIP, JAR, MP3, video, compressed archive, database file, or binary content from the network**, the most important requirement is that **the output byte sequence must match the input byte sequence**, in the exact order and exact count.

For example, if the source bytes are:

~~~text
41 FF 00 0D 0A 42
~~~

Then a valid copy result must still be **41 FF 00 0D 0A 42**. No byte may be added, dropped, or altered, including the **00** byte, the **FF** byte, or the **0D 0A** byte pair.

A binary file does not necessarily represent text in any character encoding. Its data can contain any value from **00** to **FF**, many combinations of which **are not valid character sequences** in UTF-8 or another charset.

In Java, **InputStream/OutputStream** handles bytes close to their raw representation, whereas **Reader/Writer** handles characters. Using Reader/Writer to copy a binary file adds a step that interprets the data as text. This step **has no basis** when the content is not text in the first place and can compromise data integrity.

> Rule: **copying bytes → use byte streams**. **Reading, processing, or writing text according to a charset → use character streams**.

## 2. Differences in data units and work performed

| Criterion | Byte streams | Character streams |
| --- | --- | --- |
| Typical Java APIs | **InputStream**, **OutputStream** | **Reader**, **Writer** |
| Processing unit | **byte** (8 bits) | Java **char** character unit (UTF-16 code unit, 16 bits) |
| Charset interpretation? | Not needed | Yes, when converting between bytes and characters |
| Examples | **FileInputStream**, **FileOutputStream**, **BufferedInputStream**, **BufferedOutputStream** | **FileReader**, **FileWriter**, **BufferedReader**, **BufferedWriter** |
| Suitable for | Images, ZIP/JAR, PDF, audio, binary data, any file requiring exact copying | Text content that needs to be read by character or by line |
| Primary goal | Preserving the original byte sequence | Preserving character meaning under a chosen encoding |

**char** in Java represents a UTF-16 code unit, which does not always correspond to a complete Unicode character. Some Unicode characters outside the Basic Multilingual Plane require **two chars** (a surrogate pair). This difference further demonstrates that **one char does not correspond fixedly to one byte**.

An application using **BufferedInputStream** is still working at the byte level, because buffering only accumulates bytes to reduce I/O overhead; by itself, it **does not turn bytes into characters**. Conversely, **BufferedReader** is a character stream and is unsuitable for binary copying despite sharing the word “Buffered”.

## 3. Why can Reader and Writer alter bytes?

### 3.1. Decoding: byte → character

When data from an **InputStream** passes through an **InputStreamReader**, the bytes are **decoded** according to a charset:

~~~text
Binary file
  │
  ▼
original byte[]
  │
  ▼
InputStreamReader (decode by charset)
  │
  ▼
Java character (char)
~~~

For example, in UTF-8:

- Byte **41** can represent the character **A**.
- The sequence **C3 A9** represents the character **é**.
- Byte **FF** standing alone is **invalid** in UTF-8.

With the common configuration using **InputStreamReader(..., StandardCharsets.UTF_8)**, malformed byte sequences can be replaced by the replacement character **U+FFFD ()**. Once the original byte information has been replaced, **you cannot reliably recover the original FF byte** from that replacement character.

A **CharsetDecoder** can be configured to **REPORT** and throw an error instead of replacing invalid characters, but that still does not make Reader an appropriate tool for binary copying: many valid binary byte sequences are still **not valid UTF-8 text**.

### 3.2. Encoding: character → byte

When characters pass through an **OutputStreamWriter**, they are **encoded** into bytes according to the output charset:

~~~text
Reader                   Writer
source byte[]            decoded characters           target byte[]
     └── decode ──────────►     char[]      ── encode ───►     │
     (input charset)                     (output charset)
~~~

If the Reader encounters byte **FF** and turns it into U+FFFD, the Writer encodes U+FFFD in UTF-8 as **EF BF BD**. **One byte FF** has turned into **three bytes EF BF BD**, corrupting the data even when UTF-8 is used on **both input and output**.

If the input and output encodings differ, a text document can be intentionally converted between charsets. But for binary data, that is an action that transforms bytes, **not copying**.

### 3.3. Line-based operations can lose line-ending bytes

**BufferedReader.readLine()** reads a line of text and **does not preserve line terminators** in the returned String. It treats **LF (\n)**, **CR (\r)**, and **CRLF (\r\n)** as end-of-line markers.

If **BufferedWriter.newLine()** or **PrintWriter.println()** is called afterward, the program writes line breaks back according to a new rule, often platform-dependent. The sequence **0D 0A** can turn into **0A**, or other line boundaries can be altered. This also happens on pure ASCII content, without needing any invalid UTF-8 bytes.

In addition, **readLine()** does not itself retain the specific boundary information of each line. When a file contains both CRLF and LF, the program can no longer tell which line-ending style each line previously used from the received String alone.

**Important:** Reader/Writer themselves do not automatically alter all CRLF bytes when using only **read(char[])** and **write(char[])**. Line-ending transformation happens when the application uses line-level APIs or rewrites line breaks manually; one must distinguish errors caused by *decoding/encoding* from errors caused by *text-oriented content processing*.

## 4. Java 17+ example: seeing bytes get altered firsthand

The following code creates byte data containing an **FF** value that is invalid in UTF-8, then contrasts two copying approaches:

1. **Wrong for binary:** decode with **InputStreamReader**, then encode with **OutputStreamWriter**.
2. **Right:** copy directly from **InputStream** to **OutputStream** using **transferTo**.
3. Also try **readLine()** to see how CRLF/CR can be lost when rewriting line by line.

Save as **BinaryCopyDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class BinaryCopyDemo {
    public static void main(String[] args) throws IOException {
        byte[] original = {
                0x41, (byte) 0xFF, 0x00, 0x0D, 0x0A, 0x42
        };

        // WRONG for binary data: converts byte -> char -> byte.
        ByteArrayOutputStream textTarget = new ByteArrayOutputStream();
        try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(original),
                    StandardCharsets.UTF_8);
             Writer writer = new OutputStreamWriter(
                    textTarget, StandardCharsets.UTF_8)) {
            char[] chars = new char[16];
            int count;
            while ((count = reader.read(chars)) != -1) {
                writer.write(chars, 0, count);
            }
        }
        byte[] viaCharacters = textTarget.toByteArray();

        // CORRECT: byte -> byte, without going through a charset.
        ByteArrayOutputStream byteTarget = new ByteArrayOutputStream();
        try (InputStream input = new ByteArrayInputStream(original)) {
            input.transferTo(byteTarget);
        }
        byte[] viaBytes = byteTarget.toByteArray();

        System.out.println("original=" +
                HexFormat.of().formatHex(original));
        System.out.println("characters=" +
                HexFormat.of().formatHex(viaCharacters));
        System.out.println("bytes=" +
                HexFormat.of().formatHex(viaBytes));
        System.out.println("characters equal=" +
                Arrays.equals(original, viaCharacters));
        System.out.println("bytes equal=" +
                Arrays.equals(original, viaBytes));

        // CRLF and CR will be lost when readLine() strips line terminators.
        byte[] newlines =
                "A\r\nB\rC\n".getBytes(StandardCharsets.US_ASCII);
        ByteArrayOutputStream lineTarget = new ByteArrayOutputStream();
        try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            new ByteArrayInputStream(newlines),
                            StandardCharsets.UTF_8));
             Writer writer = new OutputStreamWriter(
                    lineTarget, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                writer.write(line);
                writer.write('\n'); // Intentionally use LF to demonstrate transformation.
            }
        }
        System.out.println("lines original=" +
                HexFormat.of().formatHex(newlines));
        System.out.println("lines rewritten=" +
                HexFormat.of().formatHex(lineTarget.toByteArray()));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac BinaryCopyDemo.java
java BinaryCopyDemo
~~~

Expected stdout, deterministic because the charset and line terminators are explicitly specified in the code:

~~~text
original=41ff000d0a42
characters=41efbfbd000d0a42
bytes=41ff000d0a42
characters equal=false
bytes equal=true
lines original=410d0a420d430a
lines rewritten=410a420a430a
~~~

Part-by-part explanation:

- **41** corresponds to **A** and is preserved.
- **FF** is an invalid UTF-8 byte and is replaced by the character ****; UTF-8 encodes that character as **EF BF BD**.
- **00**, **0D**, **0A**, and **42** are not automatically lost simply by decoding/encoding with UTF-8 in the first example. This part shows that **not every byte necessarily changes**; having even a single byte altered is enough for the file to no longer match the original.
- **transferTo** transfers the byte sequence intact, so **Arrays.equals** returns **true**.
- The string **A\r\nB\rC\n** is read as three lines “A”, “B”, “C”. Each line is written back with **LF (\n)**, so the original **0D 0A** and **0D** data are replaced with **0A**.

The example uses **ByteArrayInputStream/ByteArrayOutputStream** to reproduce the result without needing to create actual files. The same principle applies to **FileInputStream/FileOutputStream** when working with files on disk.

## 5. The right ways to copy binary data in Java

### 5.1. The shortest way to copy a file: Files.copy

For two paths on disk, the **java.nio.file.Files.copy** API is the direct choice:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyBinaryFile {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.bin");
        Path destination = Path.of("copy.bin");

        // Only copy if the destination does not already exist.
        Files.copy(source, destination);

        // -1 means the contents of the two files are identical byte-for-byte.
        System.out.println("identical=" +
                (Files.mismatch(source, destination) == -1L));
    }
}
~~~

Save as **CopyBinaryFile.java**, place a source file named **source.bin** in the same working directory, then:

~~~bash
javac CopyBinaryFile.java
java CopyBinaryFile
~~~

When the copy succeeds and no other process modifies the files during the check, the result is:

~~~text
identical=true
~~~

**Files.copy(Path, Path)** throws an error by default if the destination file already exists; the example does not actively overwrite. If the business logic wants to replace the destination file, the **StandardCopyOption.REPLACE_EXISTING** option can be used, but you must weigh the risk of losing the old destination data. Copying identical byte content does not mean all file metadata (such as owner, timestamp, permissions) is completely preserved; that is a separate requirement.

### 5.2. Copying between two streams with InputStream.transferTo

When the source/destination are not necessarily files, such as streams from a connection, blob, or resource:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(destination)) {
    long copiedBytes = in.transferTo(out);
}
~~~

This is an **illustrative code snippet**, assuming existing **source** and **destination** variables of type **Path** and the necessary class imports. **transferTo(OutputStream)** reads until EOF and writes the bytes to the OutputStream, without going through Reader/Writer and without requiring application code to hold all the data in a large array. The return value is the total number of bytes transferred. Both the InputStream and OutputStream still need to be closed when finished; the example uses **try-with-resources**.

### 5.3. Buffered copying when manual control is needed

The chunked copy pattern typically uses **InputStream.read(byte[])** followed by **OutputStream.write(byte[], off, len)**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedBinaryCopy {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.bin");
        Path destination = Path.of("copy.bin");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(destination)) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }
        }
    }
}
~~~

Save as **BufferedBinaryCopy.java**, then compile with **javac BufferedBinaryCopy.java** and run **java BufferedBinaryCopy** when **source.bin** exists and destination **copy.bin** does not yet exist. **count** is the actual number of bytes read in each iteration, which may be less than **buffer.length**. If you mistakenly write **out.write(buffer)** instead of **out.write(buffer, 0, count)**, a final read shorter than the buffer may write extra stale bytes from the un-updated region.

The buffer pattern is suitable when you want to update progress, compute a hash while reading, enforce a total byte limit, or process each chunk before writing. For untrusted data sources, besides integrity, you also need size limits, timeouts, and handling for mid-copy failures.

## 6. Cases where Reader/Writer are actually appropriate

Reader/Writer are **not wrong**: they are designed for processing **text**. If the task is to **read a UTF-8 file, search/replace strings, normalize lines, or convert from one charset to another**, character streams are the right tool.

For example, if a requirement is to convert all line breaks to LF or remove certain lines from a configuration file: reading line by line with **BufferedReader**, processing **String**, and then writing back with **BufferedWriter** makes sense. The output in this case is intentionally produced as a **new text document**; there is no requirement to preserve the original bytes.

If you want to **copy the exact bytes of a text file**, such as saving a backup with a known digital signature or hash, you should still use **byte streams**. A file with a **.txt** extension can also have a BOM, a legacy charset, CRLF, or special bytes that need to be preserved. **The .txt extension does not give an application permission to alter bytes**.

| Requirement | What to choose | Reason |
| --- | --- | --- |
| Clone **photo.png**, **document.pdf**, **archive.zip**, **app.jar** | **Files.copy** or InputStream/OutputStream | Preserves byte content intact |
| Save an exact received HTTP payload for hash comparison | **InputStream/OutputStream** | Avoids decode/encode, keeps original content |
| Read a UTF-8 configuration file to parse line by line | **BufferedReader** with an explicit charset | The subject to process is text |
| Convert a document from UTF-8 to UTF-16 | **Reader + Writer** with matching input/output charsets | Intentionally changes the byte representation of text |
| Back up a text file **preserving every byte** | **Files.copy** | Hash and original bytes must be preserved |
| Export CSV data from Strings in a program | **Writer** with an explicit charset | Generates new structured text |
| Read binary data by field (integers, byte arrays) | **DataInputStream** or ByteBuffer by format | Interprets binary according to a defined protocol, not a charset |

## 7. Are there any exceptions where copying through characters still preserves bytes?

There are cases that can **coincidentally or conditionally** produce identical bytes, such as when all input bytes are valid in the same charset, no string modifications occur, and they are re-encoded in a compatible manner. Some charsets map every byte value one-to-one, so a matching conversion round-trip can restore the original bytes.

However, **that is not the general contract of Reader/Writer**, and there is no reason to rely on it to copy binary files. With UTF-8, the **FF** byte in the example above already demonstrated a counterexample. And with **readLine/println**, even completely valid character data can still have its line endings altered.

Points to distinguish:

- **Working on one test dataset** does not mean working on all files.
- **Having the same charset on both ends** does not guarantee no information loss when the input data contains byte sequences invalid for that charset.
- **Choosing ISO-8859-1 or another charset** to force bytes into characters still introduces unnecessary operations; it is only acceptable if the program is genuinely performing **text conversion** with a clear data contract.
- **Preserving visible text** is not synonymous with preserving bytes; two text documents can look identical to the user while using different encodings, BOMs, or line endings.

## 8. Verifying integrity after copying

For data where accuracy must be guaranteed, verify the result by **bytes**, rather than relying on opening the file and seeing that it displays normally.

**Files.mismatch(source, copy)** (Java 12+) returns **-1L** if no differing byte position is found; if they differ, the result indicates the position of the first differing byte (or the point where one file ends while the other still has bytes). It is useful when you have two local files and want an exact byte comparison.

A hash like **SHA-256** is a practical way to compare content across two different systems or points in time; matching hashes provide very strong evidence that the contents are equivalent, though mathematically it remains a check with an extremely small collision probability rather than an absolute byte-by-byte comparison. Choose SHA-256 or a strong hash algorithm accepted in your system instead of comparing file sizes alone.

Comparing **Files.size(...)** alone is insufficient: two files can have the same size yet different contents. At the same time, a copy will **not necessarily be complete** if reading or writing encounters an IOException midway; the application needs a policy for handling incomplete destination files (deleting them or writing to a temporary file and replacing when appropriate).

## 9. Common mistakes and how to avoid them

1. **Copying images/PDFs with FileReader and FileWriter.** Charset conversion can alter bytes. Use **Files.copy**, **InputStream/OutputStream**, or byte-based NIO APIs.
2. **Assuming setting the same UTF-8 on both Reader and Writer is safe.** Binary data contains bytes invalid for UTF-8; the decoder may replace them or throw errors, making the process different from copying.
3. **Using BufferedReader.readLine() to split binary data into lines.** This is a text API that strips line terminators, not a binary framing mechanism.
4. **Using println() when expecting to preserve bytes.** println formats text and can append platform-dependent line breaks; write bytes with **OutputStream.write**.
5. **Using String as a container for binary data.** Creating a String from bytes and getting bytes back goes through a charset; use **byte[]** or **ByteBuffer**.
6. **Reading into a buffer and writing the entire buffer regardless of the actual bytes received.** You must use **out.write(buffer, 0, count)** with **count** from **in.read(buffer)**.
7. **Assuming every 0 byte terminates data.** In Java, **0x00** is valid binary data; **InputStream.read(...)** signals EOF with **-1**, not 0.
8. **Not verifying the copied file.** If accuracy matters, use **Files.mismatch** or a hash to confirm.
9. **Thinking buffering turns binary data into text.** **BufferedInputStream** is safe for bytes; **BufferedReader** serves a completely different purpose.
10. **Not handling an existing destination file or mid-copy errors.** Clearly define an overwrite policy, close resources, and verify the destination file is complete when required by the business logic.

## 10. Self-check questions

**Question 1:** Can a ZIP file containing arbitrary bytes be safely copied using **BufferedReader + BufferedWriter** if both use UTF-8?  
**Answer:** There is no guarantee. ZIP data is not guaranteed to be valid UTF-8 sequences; decoding/encoding can replace bytes that are invalid for the charset. Use byte streams.

**Question 2:** Why did byte FF turn into EF BF BD in the example?  
**Answer:** **FF** is invalid on its own in UTF-8, so the default decoder replaces it with the character **U+FFFD**, and then the UTF-8 encoder produces **EF BF BD**.

**Question 3:** Does **BufferedReader.readLine()** preserve the **0D 0A** sequence?  
**Answer:** No. It returns the line content without the line terminator. If written back with **newLine()**, a new line break is generated.

**Question 4:** Do text files require using Reader for backups?  
**Answer:** No. If you need an exact byte-for-byte copy, use **Files.copy** even for text files. If you need to modify character content, Reader/Writer are appropriate.

**Question 5:** Why must we use **out.write(buffer, 0, count)**?  
**Answer:** **read(buffer)** can read fewer bytes than the buffer's capacity, especially on the final read. **count** indicates the exact amount of bytes just received; writing the whole buffer could insert leftover garbage bytes.

## 11. Summary

Character streams **Reader/Writer** serve text: they **decode bytes into characters**, allow character-level content processing, and then **encode back into bytes**. Because binary data **has no obligation to conform to any charset**, decoding can replace invalid bytes; line processing can also alter line terminators. Changing even **a single byte** makes the copy invalid.

To copy binary data accurately, use **Files.copy(...)**, **InputStream.transferTo(OutputStream)**, or an **InputStream.read(buffer) / OutputStream.write(buffer, 0, count)** loop. If certainty is needed, verify afterward with **Files.mismatch(...)** or an appropriate hash.

### Official references

- [Oracle Java SE 21 — InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html): converting bytes to characters and charsets.
- [Oracle Java SE 21 — OutputStreamWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStreamWriter.html): converting characters to bytes.
- [Oracle Java SE 21 — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html#readLine()): handling line terminators.
- [Oracle Java SE 21 — InputStream.transferTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)): byte-based copying.
- [Oracle Java SE 21 — Files.copy and Files.mismatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): copying and comparing files by byte.