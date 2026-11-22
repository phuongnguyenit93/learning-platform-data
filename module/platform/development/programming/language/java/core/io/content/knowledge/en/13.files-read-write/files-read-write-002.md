# Files.readString(), Files.writeString() and the API's Default UTF-8

## 1. Lesson Objectives

In Java 11 and later (including Java 17+), **java.nio.file.Files** provides two convenient methods for **reading or writing an entire text content**:

- **Files.readString(Path)**: reads the entire file and returns a **String**, **decoding UTF-8 by the API's own default**.
- **Files.writeString(Path, CharSequence, OpenOption...)**: writes character content to a file using **UTF-8 by the API's own default**.
- Both have overloads accepting a **Charset** to handle files with encodings other than UTF-8.

The focus is not just short syntax. What matters is understanding that **bytes on disk differ from characters in a String**, that charset choice affects correctness, and that single-call whole-file read/write methods have limits regarding memory, I/O errors, and overwrite policies.

> Remember: **the default UTF-8 of Files.readString/writeString is specified by these two APIs**, not inferred from the default charset of the operating system, terminal, or JVM.

## 2. From File Bytes to String: What Role Does Charset Play?

Files store **bytes**. A Java String holds Unicode character content (represented internally by UTF-16 code units). A **charset** defines how to convert between those two domains:

~~~text
Files.readString(path)
    file bytes ──decode UTF-8──> Java String

Files.writeString(path, text)
    Java CharSequence ──encode UTF-8──> file bytes
~~~

Example:

| Character in text | Unicode code point | UTF-8 bytes (hex) |
| --- | --- | --- |
| **A** | U+0041 | **41** |
| **é** | U+00E9 | **C3 A9** |
| **€** | U+20AC | **E2 82 AC** |
| Line feed LF | U+000A | **0A** |

One visible character does not necessarily occupy one byte. Therefore, **Files.size(path)** returning the file's byte count can differ from **text.length()** (which counts UTF-16 code units), and also differ from the count of full Unicode characters when surrogate pairs are present.

**UTF-8** is ASCII-compatible for the U+0000–U+007F range, while characters outside ASCII can take 2–4 bytes. For example, the string **"Café\n€"** has **6 Java char units**, whereas writing it in UTF-8 produces **9 bytes**:

~~~text
43 61 66 C3 A9 0A E2 82 AC
C  a  f  é     LF € 
~~~

Therefore, **do not use String or readString() to copy images, ZIPs, PDFs, or binary data**. Use **Files.readAllBytes**, **Files.copy**, or appropriate InputStream/OutputStream APIs.

## 3. Files.readString(Path): Reading an Entire File as UTF-8 Text

Typical signatures:

~~~java
public static String readString(Path path) throws IOException
public static String readString(Path path, Charset cs) throws IOException
~~~

Example:

~~~java
Path path = Path.of("notes.txt");
String text = Files.readString(path);
~~~

This is an **illustrative snippet**; you need to import **java.nio.file.Files**, **java.nio.file.Path**, and handle **IOException**. **Path.of(...)** only creates a path representation; it does not create a file.

**Files.readString(path)** reads all bytes of the file, decodes them using **StandardCharsets.UTF_8** per the API specification, and builds a **String**. It does not use **Charset.defaultCharset()** to choose the encoding when no charset argument is passed. The **Path** parameter specifies the file to read; the internal stream resource is managed by the API, so the caller does not have to call close for this method.

**There is no "auto-detect encoding" step**: if the file is actually Windows-1252, ISO-8859-1, or UTF-16, calling readString without a charset parameter may fail or return unexpected results. You must know or determine the source encoding from the data contract, then pass the matching charset.

### 3.1. When the File Is Not Valid UTF-8

If the byte data is invalid for the charset, **Files.readString** can throw an **IOException**, typically a **MalformedInputException** or related transcoding error. By the API contract, malformed input is not treated as valid text and is not simply replaced silently with the replacement character (**U+FFFD**).

For example, a file containing only the byte **E9** (valid for the **é** character in ISO-8859-1) is not a valid complete UTF-8 sequence:

~~~java
Path legacy = Path.of("legacy.txt");
String text = Files.readString(legacy, StandardCharsets.ISO_8859_1);
~~~

This is an **illustrative snippet** assuming the file is actually encoded in ISO-8859-1 and requires importing **java.nio.charset.StandardCharsets**. If you **do not know** the file's actual charset, do not guess blindly: many encodings map the same bytes to different characters.

### 3.2. Do Not Read Large Data Without Considering Memory

**Files.readString** reads the **entire** text into a single String. When a file is large, the memory needed for intermediate bytes, decoding, and the String can be substantial; the call may throw errors due to insufficient RAM or size limits imposed by the API/JVM. The API also notes that it is **not intended for very large files**.

For multi-GB logs or large data sources, use **Files.newBufferedReader(path, charset)**, **Files.lines(path, charset)**, or a streaming parser that reads and processes line by line or chunk by chunk and closes resources properly. Do not call readString and then split millions of lines if you only need sequential processing.

## 4. Files.writeString(Path, CharSequence): Default UTF-8 Writing

Key overloads:

~~~java
public static Path writeString(Path path, CharSequence csq,
                               OpenOption... options) throws IOException

public static Path writeString(Path path, CharSequence csq,
                               Charset cs, OpenOption... options)
                               throws IOException
~~~

Example:

~~~java
Path path = Path.of("notes.txt");
Files.writeString(path, "Xin chào!\nDòng thứ hai");
~~~

This is an **illustrative snippet**; you need to import **Files/Path** and handle **IOException**. **writeString** accepts a **CharSequence**, so a String or any suitable CharSequence implementation works. It encodes the content using **UTF-8 when no Charset is passed** and writes the bytes to the file. The method returns **the same Path passed in**, which is useful for chaining operations, though it does not return the number of bytes written.

### 4.1. Default Behavior: Create New or Overwrite Content

When **no OpenOption is specified**, the behavior of **Files.writeString(path, text)** is equivalent to opening the file for writing with the **CREATE**, **TRUNCATE_EXISTING**, and **WRITE** options:

- If the file does not exist yet while the parent path exists and has permissions, the method **creates a new file**.
- If the file already exists, the old content is **truncated** and the new content is written.
- If the parent directory does not exist yet, **writeString does not automatically create parent directories**.
- The method does not automatically insert a newline before/after the text; it only writes characters present in the **CharSequence**.
- If a write error occurs mid-way, the target file may be partially modified; the method **does not guarantee that replacing the content is an atomic transaction**.

Therefore, do not use **writeString** habitually on critical files while overlooking the overwrite policy. For configuration files needing safer updates, consider writing to a temporary file, verifying the data, and then moving it into the final location according to filesystem capabilities.

### 4.2. Explicitly Choosing Policies with StandardOpenOption

| Purpose | Example | Meaning |
| --- | --- | --- |
| Create if absent, overwrite if present | **Files.writeString(path, text)** | Default CREATE + TRUNCATE_EXISTING + WRITE |
| Append to end of file | **Files.writeString(path, text, CREATE, APPEND)** | Does not erase prior content; creates file if absent |
| Create only, fail if file exists | **Files.writeString(path, text, CREATE_NEW, WRITE)** | Suitable when overwriting is forbidden |
| Use a non-UTF-8 charset | **Files.writeString(path, text, charset)** | Encodes using the specified charset |

In real code, the constants are written as **StandardOpenOption.CREATE**, **StandardOpenOption.APPEND**, **StandardOpenOption.CREATE_NEW**, **StandardOpenOption.WRITE**, or intentionally via static imports.

Append example:

~~~java
Files.writeString(
        path, "\nDòng bổ sung",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

This is a **code snippet**, assuming **path** of type Path already exists and **java.nio.file.StandardOpenOption** is imported. In this example, the newline **\n** is **explicitly included by the programmer**. If you omit `\n`, the new text is appended immediately at the end of the existing content without inserting a new line.

**Do not combine APPEND with TRUNCATE_EXISTING** expecting to "truncate first then append"; the two behaviors conflict and may be rejected by the system. In applications writing from multiple processes, a single append is not necessarily equivalent to an application-level atomic record: atomicity, call ordering, and synchronization must be designed separately if needed.

## 5. API Default UTF-8 Differs from JVM Default Charset

A common misconception:

~~~java
Charset systemDefault = Charset.defaultCharset();
String content = Files.readString(path);
~~~

This snippet requires importing **java.nio.charset.Charset** and the Files/Path types. The two expressions **have no relationship like "readString automatically uses systemDefault"**. **Files.readString(path)** always uses UTF-8 per its method contract since the API was introduced.

This is especially significant when applications run across environments or JDK versions:

- Other APIs, such as creating a **FileReader** or **InputStreamReader** without specifying a charset, can depend on the default charset depending on the JDK version and configuration.
- Since Java 18 (JEP 400), Java SE's default charset was standardized to UTF-8 under standard conditions, with certain exceptions/configurations. However, **Files.readString/writeString have specified UTF-8 by API contract since Java 11**, not just since Java 18.
- Which encoding **System.out** or the terminal uses to display characters is a separate issue: file bytes can be valid UTF-8 even if the console displays them incorrectly.

To make code express requirements clearly, you can use the explicit charset overload:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

The encoding result is equivalent to omitting the charset. However, passing the charset explicitly is helpful when the team wants the contract visible right at the call site, or when switching to ISO-8859-1, UTF-16, etc. Do not expect these two overloads to auto-detect encodings.

## 6. Complete Java 17+ Example: Reading UTF-8, Inspecting Bytes, Append, Overwrite, and Invalid Encoding

The program below creates files in a **new temporary directory**, without touching any learner files. It uses **Unicode escapes** in the source code so the result does not depend on the source file encoding and avoids printing Vietnamese characters to the console.

Save as **TextFilesDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class TextFilesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("text-files-demo-");
        Path note = directory.resolve("note.txt");
        Path legacy = directory.resolve("legacy.txt");

        try {
            // Café + LF + euro sign, represented with Unicode escapes.
            String content = "Caf\u00E9\n\u20AC";

            // No charset passed: Java Files uses UTF-8.
            Files.writeString(note, content);
            String readBack = Files.readString(note);
            byte[] raw = Files.readAllBytes(note);

            System.out.println("chars=" + readBack.length());
            System.out.println("bytes=" + raw.length);
            System.out.println("hex=" + HexFormat.of().formatHex(raw));
            System.out.println("equal=" + content.equals(
                    Files.readString(note, StandardCharsets.UTF_8)));

            // APPEND: append content, does not automatically add a newline character.
            Files.writeString(note, "!",
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
            System.out.println("append=" + HexFormat.of().formatHex(
                    Files.readAllBytes(note)));

            // No option specified: truncate old content then write "OK".
            Files.writeString(note, "OK");
            System.out.println("overwrite=" + Files.readString(note));

            // Standalone E9 byte: valid in Latin-1, invalid in UTF-8.
            Files.write(legacy, new byte[] {(byte) 0xE9});
            try {
                Files.readString(legacy);
                System.out.println("unexpected-success");
            } catch (MalformedInputException ex) {
                System.out.println("invalid-utf8=true");
            }
            System.out.println("latin1=" + Files.readString(
                    legacy, StandardCharsets.ISO_8859_1)
                    .equals("\u00E9"));
        } finally {
            // Clean up only the temporary paths created by the program.
            Files.deleteIfExists(legacy);
            Files.deleteIfExists(note);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac TextFilesDemo.java
java TextFilesDemo
~~~

Output in a normal filesystem environment:

~~~text
chars=6
bytes=9
hex=436166c3a90ae282ac
equal=true
append=436166c3a90ae282ac21
overwrite=OK
invalid-utf8=true
latin1=true
~~~

**Result explanation:**

1. **Café\n€** has 6 Java char units, but 9 bytes when written in UTF-8. The hex bytes are **43 61 66 C3 A9 0A E2 82 AC**.
2. **readString(note)** and **readString(note, UTF_8)** return the same content, verifiable with `equals`.
3. When appending **!**, byte **21** is added, so the hex string grows by one byte at the end.
4. **writeString(note, "OK")** passes no options, so it **truncates the old content**. Reading back returns **OK**.
5. Byte **E9** is invalid when read as standalone UTF-8 text; hence the example catches **MalformedInputException**. Only by specifying **ISO_8859_1** is this byte interpreted as **é**.

Numeric, hex, and boolean outputs were chosen to be independent of console character rendering. The example **does not claim** that any arbitrary file always has the same byte count or encoding. Any real file operation can throw `IOException` on missing permissions, disk errors, or interference from another process; the program actively cleans up temporary paths in **finally**.

## 7. Do readString/writeString Preserve Line Endings?

These two APIs **do not automatically normalize** CRLF to LF or vice versa just by being called. If a String contains **\r\n**, writing with UTF-8 yields **0D 0A** bytes; if it contains **\n**, the resulting byte is **0A**. When `readString` decodes valid content, line terminator characters are returned just as they appear in the decoded data.

~~~java
String text = "A\r\nB\nC\rD";
Files.writeString(path, text, StandardCharsets.UTF_8);
String roundTrip = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(text.equals(roundTrip)); // true
~~~

This is an **illustrative code snippet** assuming `path` has been created, and must handle `IOException`. Note: when an application **operates line by line** using **BufferedReader.readLine()**, `readLine` **strips line terminators** from the returned String; using **BufferedWriter.newLine()** can introduce a new line-ending convention. Those changes belong to **line-based processing logic**, not the default effect of `Files.readString/writeString`.

**Files.writeString does not automatically add a BOM (Byte Order Mark) for UTF-8.** If the String content itself contains the BOM character U+FEFF or the original file starts with a BOM, the application must decide explicitly how to handle it. Do not assume a BOM is "always automatically detected and stripped". UTF-8 does not require a BOM for decoding.

## 8. Reading Encodings Other Than UTF-8: Specify Charset on Solid Grounds

Not all text files are UTF-8. Some legacy software uses ISO-8859-1, Windows-1252, or UTF-16. When you know the encoding for certain from metadata, protocol standards, or agreement with the file producer, use the Charset overload:

~~~java
String latin1Text = Files.readString(
        Path.of("legacy.txt"), StandardCharsets.ISO_8859_1);

Files.writeString(
        Path.of("export.txt"),
        latin1Text,
        StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet** requiring imports for **Files**, **Path**, **StandardCharsets** and handling `IOException`. If the read step uses the right charset, the write step can **convert the text to UTF-8** while preserving the meaning of representable characters. However, the target file's bytes are not necessarily identical to the source file's bytes, because this is **text transcoding**, not byte copying.

**Not every charset can represent every character.** If you try to write characters outside the target charset's supported range, the API can report a transcoding error rather than silently delivering complete text. Do not simply "try UTF-8, and if it fails use Latin-1" as a reliable detection algorithm: Latin-1 maps every possible byte, so a file in another encoding can be misread as wrong characters without throwing an error.

For files with unknown encoding, determine the origin, ask the producer to declare the charset, or use encoding detection tools with clear awareness of their reliability limits.

## 9. Important Notes on Files, Errors, and Resources

### 9.1. Paths and Parent Directories

**Path.of("data", "note.txt")** is a relative path to the process working directory. If the parent **data** does not exist yet, `writeString` **does not create the parent automatically**. Create it beforehand:

~~~java
Path directory = Path.of("data", "notes");
Files.createDirectories(directory);
Files.writeString(directory.resolve("today.txt"), "Hello UTF-8");
~~~

This is an illustrative snippet; with real data you need to decide filename policies, write permissions, and the case where the target file already exists. **Files.createDirectories** operates at the directory level, while **Files.writeString** operates at the file level.

### 9.2. Access Permissions and I/O Errors

The **readString** and **writeString** methods throw **IOException** or its subclasses on I/O failures, such as missing file, permission error, path being a directory, disk failure, or invalid encoding. Which exact exception appears depends on the operating system and filesystem.

Do not simply catch **Exception** and ignore it: that leaves the application thinking it saved successfully even though the file might be missing or truncated. For critical configuration files, report specific errors and consider backup/safe replacement writes.

### 9.3. Files Are Not Atomically Read/Written as a Whole

A single **Files.readString** call does not permanently "lock a snapshot" of the file against concurrent modifications; if another process is editing the file, the result depends on the system and read timing. Similarly, **writeString** is not a multi-byte atomic commit; if an error happens after the file has been truncated or partially written, the content can be incomplete.

If you need to preserve the old version when updating a file, write to a temporary file on the same filesystem, close/sync according to the required durability level, and then attempt **Files.move** with an appropriate replace/atomic policy. **ATOMIC_MOVE** may not be supported; handle **AtomicMoveNotSupportedException**.

### 9.4. Size and Data Streaming Considerations

If you want to read line by line instead of loading into a String:

~~~java
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line one by one.
    }
}
~~~

This is an **illustrative snippet**, assuming `path` is already declared and inside a method handling `IOException`. Choosing **Files.lines(path, charset)** can also be appropriate, but you must **close the `Stream<String>`** when done, typically via try-with-resources. Both options allow sequential processing without forcing the entire text content into one large String.

If you want to preserve a binary file or simply copy data: **Files.copy(...)** or byte streams are the right choice. **readString** makes no sense for files containing bytes that are invalid for the selected charset.

### 9.5. Concurrency and Appending

**APPEND** is only a file write option, not a distributed locking mechanism or a guarantee that a multi-byte text record will not interleave with writes from another process. If multiple threads/processes write concurrently, you need a serialization strategy, file locking, or a writing service with the required consistency guarantees.

## 10. Common Mistakes

1. **Thinking `Files.readString(path)` uses `Charset.defaultCharset()`.** Wrong: the overload without a charset parameter specifies **UTF-8** by API contract.
2. **Thinking UTF-8 only applies from Java 18.** Wrong: these charset-less overloads have defaulted to UTF-8 since Java 11; the JEP 400 change concerns the general default charset.
3. **Reading ISO-8859-1 with `readString` without passing a charset.** Can throw `MalformedInputException` or return wrong text; choose the charset according to the data contract.
4. **Using `String`/`readString` to copy binary data.** Invalid bytes for the charset can cause failures or corrupt data; use byte APIs.
5. **Calling `writeString` assuming the old file content stays intact.** Default behavior is to create new or **truncate** an existing file.
6. **Using `APPEND` and forgetting to include a newline.** `Files.writeString` does not add LF/CRLF automatically; to start a new line, include the newline character in the text.
7. **Assuming `writeString` creates parent directories automatically.** Call **Files.createDirectories(parent)** before writing to a non-existent directory.
8. **Assuming `readString` saves RAM like `BufferedReader.readLine`.** It reads all content and returns a single String; unsuitable for very large data.
9. **Ignoring BOM bytes and newline conventions.** It does not strip/write BOMs or normalize newlines by default; verify the receiving system's requirements.
10. **Reading a file with charset A, writing with B, and comparing bytes directly.** Transcoding can change bytes even for equivalent characters; verify content according to your goal.
11. **Assuming `writeString` is an atomic overwrite.** Mid-write I/O errors can leave a partial file; use a safe update strategy for critical data.
12. **Not managing large files or untrusted input.** Consider size limits, memory, permissions, and read policies.
13. **Comparing byte count with `String.length()` and treating any difference as an error.** UTF-8 is variable-length, while `String.length()` measures UTF-16 code units.
14. **Relying on console display encoding to judge a file's encoding.** Inspect bytes (`Files.readAllBytes`/`HexFormat`) or use a viewer with an explicit charset.
15. **Forgetting explicit charsets in other APIs.** The UTF-8 default in `readString`/`writeString` does not mean every `Reader`/`Writer` or third-party library uses the same charset.

## 11. Self-Check Questions

**Q1.** Java 17 is running on a system whose default charset is not UTF-8. Which charset does **Files.readString(path)** use by default?  
**A:** Still **UTF-8**, as defined by the API itself.

**Q2.** A UTF-8 file containing **"Café\n€"** has how many Java chars and how many UTF-8 bytes?  
**A:** **6 chars** per `String.length()` and **9 bytes** when UTF-8 encoded.

**Q3.** What happens when calling **Files.writeString(path, "ABC")** if the existing file contains "LONG TEXT"?  
**A:** Under default behavior, the file is **truncated** and **ABC** is written, discarding the old text.

**Q4.** Which option should be used to create a file only if it does not already exist, without overwriting?  
**A:** **StandardOpenOption.CREATE_NEW** along with an appropriate write mode, such as **WRITE**.

**Q5.** If you want to append "hello" on a new line, can you just write **writeString(path, "hello", APPEND)**?  
**A:** It will not add a newline automatically. If you want LF, include **\n** in the text, and configure CREATE if the file might not exist yet.

**Q6.** If **Files.readString(path)** throws `MalformedInputException`, is the file definitely corrupted?  
**A:** Not necessarily. The file may be valid under a **charset other than UTF-8**, such as ISO-8859-1, and simply be decoded with the wrong charset.

**Q7.** For a multi-GB video file, should you use `readString` for convenience?  
**A:** No. Video is binary data and large in size; use `Files.copy` or chunked byte streams.

**Q8.** If you want to read a large log line by line, which API is more suitable?  
**A:** **Files.newBufferedReader(path, charset)** or **Files.lines(path, charset)** with proper resource management.

## 12. Summary

**Files.readString(Path)** and **Files.writeString(Path, CharSequence)** are convenient APIs for reading/writing **entire text files**. Their own default is **UTF-8**, **independent** of whatever `Charset.defaultCharset()` the JVM reports. If the source/destination data uses another charset, pass a `Charset` explicitly and accept that transcoding can alter the byte representation.

When writing files, remember that **writeString creates or truncates existing content by default**, while `APPEND`/`CREATE_NEW` are deliberate choices. When reading, handle **`IOException` and invalid-charset data**, and avoid loading massive files into RAM. These methods are for text; exact byte copying or handling binary data requires byte stream APIs or `Files.copy`.

### Official References

- [Oracle Java SE 17 — Files.readString / Files.writeString](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): default UTF-8 overloads, Charset, OpenOption, IOException.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF_8, ISO_8859_1, UTF_16.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): CREATE, TRUNCATE_EXISTING, APPEND, CREATE_NEW.
- [Oracle Java SE 17 — MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html): bytes that do not form valid input for the charset.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): changing Java SE's default charset since JDK 18, distinct from the fixed UTF-8 of `readString`/`writeString`.