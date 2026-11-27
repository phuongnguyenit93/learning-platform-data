# Reading and Writing Text with `Files.readString` and `Files.writeString` in Java 17

Since Java 11, the `java.nio.file.Files` class provides two convenient methods for working with text files: `readString` reads the entire content of a file into a `String`, while `writeString` writes text to a file. Both are available and stable in Java 17.

These two methods make file-handling code more concise than manually creating a `BufferedReader` or `BufferedWriter`. When using them, you still need to explicitly decide on the **path**, **charset**, **file open options** (overwrite or append), and **I/O error handling**.

> **Scope:** This lesson focuses on `Files.readString(Path)` and `Files.writeString(Path, CharSequence)` along with overloads accepting `Charset` and `OpenOption`. The APIs were introduced in Java 11 and are not preview features.

## 1. What Do the Two Methods Do?

Main imports:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
~~~

Reading a file:

~~~java
Path path = Path.of("data", "message.txt");
String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
~~~

Writing a file:

~~~java
Path path = Path.of("data", "message.txt");
Files.writeString(path, "Hello Java 17", StandardCharsets.UTF_8);
~~~

`readString` returns the text content as a `String`. `writeString` accepts a `CharSequence` (for example, `String`) and writes those characters to the file.

These methods belong to `java.nio.file.Files` and work with NIO.2 `Path`. They open and close resources internally; you do not need to manage streams manually for each call.

### 1.1. Overloads Without a Charset Parameter

Java provides a shorthand form:

~~~java
String content = Files.readString(path);
Files.writeString(path, content);
~~~

**Both overloads that omit the charset parameter use UTF-8.** This is defined by the API specification itself and does not depend on the operating system's default charset or `Charset.defaultCharset()`.

If the file format is UTF-8, you can use the short overload. In data-processing code where the encoding contract should be explicit, writing `StandardCharsets.UTF_8` explicitly often helps readers immediately understand how bytes are interpreted.

### 1.2. Important Overloads

| Method | Meaning |
|---|---|
| `Files.readString(path)` | Reads the entire file using UTF-8 |
| `Files.readString(path, charset)` | Reads the entire file using the specified charset |
| `Files.writeString(path, text)` | Writes text using UTF-8 with default open options |
| `Files.writeString(path, text, charset)` | Writes text using the specified charset |
| `Files.writeString(path, text, options...)` | Writes using UTF-8 and custom open options |
| `Files.writeString(path, text, charset, options...)` | Writes using the specified charset and custom open options |

`readString` and `writeString` can throw `IOException` if a read, write, or encoding/decoding error occurs.

## 2. Constructing File Paths with Path

`Files` accepts a `Path` object, not a raw filename string directly. You can create a `Path` using `Path.of(...)`:

~~~java
Path relative = Path.of("data", "notes.txt");
Path inHome = Path.of(System.getProperty("user.home"), "notes.txt");
~~~

Using separate path components allows Java to insert the appropriate separator for the operating system. Avoid manual string concatenation like `"data/" + fileName` if you want portable code across Windows, Linux, and macOS.

### 2.1. Parent Directories Must Exist

`writeString` can create the target file when opened with default options, but it **does not automatically create missing parent directories**.

For example, if the `data` directory does not exist yet, writing to `data/notes.txt` may fail with `NoSuchFileException`.

Create the directories first:

~~~java
Path path = Path.of("data", "notes.txt");
Files.createDirectories(path.getParent());
Files.writeString(path, "Content written to file", StandardCharsets.UTF_8);
~~~

`createDirectories` creates any necessary parent directories; if a directory already exists, it does not fail merely because it is already present.

If the path is just a simple filename like `Path.of("notes.txt")`, `getParent()` can return `null`. When writing a helper that handles both paths with and without parent directories, check first:

~~~java
Path path = Path.of("notes.txt");
Path parent = path.getParent();

if (parent != null) {
    Files.createDirectories(parent);
}
~~~

### 2.2. Relative Paths Are Resolved Against the Working Directory

A relative path such as `Path.of("data", "notes.txt")` is resolved relative to the current working directory of the Java process. This directory may differ from the directory containing the `.java` or `.class` files.

When debugging, you can print:

~~~java
System.out.println(Path.of("data", "notes.txt").toAbsolutePath());
System.out.println(System.getProperty("user.dir"));
~~~

This helps determine exactly where the application is looking for or creating files.

## 3. Reading an Entire File with readString

Complete example:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadTextDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "message.txt");
        String content = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("File content:");
        System.out.println(content);
    }
}
~~~

If the file contains:

~~~text
Hello
Java 17
Reading text with Files
~~~

then `content` contains all of those lines in a single string.

### 3.1. readString Preserves Line Terminators

`readString` reads the text into a string; it does not split lines into a `List<String>` and does not strip newline characters.

For example, if the file content has a newline between two lines, `content` preserves the corresponding characters. A file using LF (`\n`) and a file using CRLF (`\r\n`) will produce different strings at line endings.

If you need line-by-line processing, you can call `String.lines()` after reading or switch to a streaming read API. `String.lines()` returns a stream of lines without keeping the line terminator of each line:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);

content.lines()
        .filter(line -> !line.isBlank())
        .forEach(System.out::println);
~~~

### 3.2. Empty Files

If a file exists but contains zero bytes, `readString` returns an empty string:

~~~java
String content = Files.readString(path);

if (content.isEmpty()) {
    System.out.println("The file has no content yet");
}
~~~

Do not confuse an empty string with `null`: the method never returns `null` to represent an empty file.

### 3.3. Reading Non-Existent or Unreadable Files

If the file does not exist, the path does not point to a readable file, or an I/O error occurs, the method throws an exception. `NoSuchFileException` is a common type of `IOException` when a path does not exist.

You can handle it with `try/catch`:

~~~java
try {
    String content = Files.readString(path, StandardCharsets.UTF_8);
    System.out.println(content);
} catch (IOException e) {
    System.err.println("Unable to read file: " + e.getMessage());
}
~~~

Or declare `throws IOException` on the calling method if an upper layer is responsible for error handling.

## 4. Writing Text with writeString

Example:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteTextDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "message.txt");
        Files.createDirectories(path.getParent());

        String content = "Hello Java 17" + System.lineSeparator()
                + "Writing text with Files.writeString";

        Files.writeString(path, content, StandardCharsets.UTF_8);

        System.out.println("File written: " + path.toAbsolutePath());
    }
}
~~~

`System.lineSeparator()` returns the platform-appropriate line separator string. If the file format mandates LF, write `\n` explicitly instead of using the OS line separator.

### 4.1. By Default, writeString Creates a File or Overwrites Old Content

When no `OpenOption` is passed, `writeString` behaves equivalently to the default options:

- `CREATE`: creates the file if it does not exist.
- `TRUNCATE_EXISTING`: truncates the existing file content before writing.
- `WRITE`: opens the file for writing.

Example:

~~~java
Files.writeString(path, "New content", StandardCharsets.UTF_8);
~~~

If the file previously contained "Very long content from the previous run", the old content is truncated; the resulting file contains only "New content".

Therefore, do not call `writeString(path, text)` assuming it automatically appends content. **The default is to replace existing content.**

### 4.2. Specifying Write Options Explicitly

You can list the options explicitly:

~~~java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        path,
        content,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
~~~

This is equivalent to the default behavior, but makes the intent to overwrite clearer. `StandardOpenOption` belongs to `java.nio.file`.

### 4.3. Appending Content with APPEND

If you want to add text to the end of a file while keeping old content, use `APPEND`:

~~~java
import java.nio.file.StandardOpenOption;

Files.writeString(
        path,
        "Appended line" + System.lineSeparator(),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND
);
~~~

- `CREATE` allows creating the file if it does not exist yet.
- `WRITE` opens write access.
- `APPEND` sets the write position to the end of the file.

Do not include `TRUNCATE_EXISTING` when your goal is to append data.

### 4.4. Writing a New File Without Overwriting an Existing One

If you want to create a new file and treat an already existing file as an error, use `CREATE_NEW`:

~~~java
Files.writeString(
        path,
        "Initial content",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE
);
~~~

If the file already exists, the operation fails rather than overwriting it. This is the right choice when replacing an existing file could cause unintended data loss.

## 5. Character Encoding and Charset

Files store bytes; a `String` in Java represents a sequence of characters. When reading, Java needs to **decode bytes into characters**; when writing, Java needs to **encode characters into bytes**. A charset defines that mapping.

### 5.1. UTF-8 Is the Default Choice of readString/writeString

You can read and write UTF-8 using the overloads without a charset:

~~~java
String text = Files.readString(path);
Files.writeString(path, text);
~~~

Or express it explicitly:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

For multilingual text and international characters (such as accented Vietnamese text), UTF-8 is typically the right choice. A Unicode character can be encoded as one or more UTF-8 bytes; never assume one character always corresponds to one byte.

### 5.2. Reading Files Using Another Charset

If a legacy file was created using a known charset, pass that exact charset:

~~~java
String content = Files.readString(
        path,
        StandardCharsets.ISO_8859_1
);
~~~

Example with a charset that has no constant in `StandardCharsets`:

~~~java
import java.nio.charset.Charset;

Charset windows1252 = Charset.forName("windows-1252");
String content = Files.readString(path, windows1252);
~~~

Only choose a charset after knowing the source format. Do not randomly try multiple charsets and pick whatever "looks right", because many byte sequences can decode into valid-looking characters with the wrong meaning.

### 5.3. Writing a File with a Specific Charset

~~~java
Files.writeString(
        path,
        "Text to write",
        StandardCharsets.UTF_8
);
~~~

If an integrating system requires a different charset, specify it accurately:

~~~java
Files.writeString(
        path,
        "Legacy text",
        StandardCharsets.ISO_8859_1
);
~~~

If a character in the string cannot be represented in the chosen charset, the operation may fail with `IOException`. Do not choose a narrow charset like US-ASCII for content that may contain non-ASCII or accented characters.

### 5.4. Do Not Confuse readString's Charset with the System Default Charset

| Call | Charset |
|---|---|
| `Files.readString(path)` | UTF-8 |
| `Files.writeString(path, text)` | UTF-8 |
| `Files.readString(path, charset)` | Passed charset |
| `Files.writeString(path, text, charset)` | Passed charset |

Do not infer that the overloads without a charset parameter use the machine's default charset. This behavior differs from some byte-to-string APIs such as `new String(bytes)` when no charset is specified.

## 6. Error Handling During Reads and Writes

File operations can fail due to invalid paths, access permissions, deleted files, device errors, or undecodable data.

### 6.1. IOException Is a Checked Exception

Both `readString` and `writeString` declare `throws IOException`. There are two common ways to handle it:

**Approach 1: declare throws**

~~~java
static String load(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

This approach fits when the calling layer can decide whether to report the error, retry, or return a response to the user.

**Approach 2: catch the exception at the handling site**

~~~java
try {
    Files.writeString(path, "Hello", StandardCharsets.UTF_8);
} catch (IOException e) {
    System.err.println("Failed to write file: " + e.getMessage());
}
~~~

Do not catch `IOException` and silently ignore it if a read/write failure affects program correctness.

### 6.2. Common Exceptions

| Exception | Possible Scenario | Resolution |
|---|---|---|
| `NoSuchFileException` | File does not exist when reading, or parent directory does not exist when writing | Check the path, create parent directories if needed |
| `AccessDeniedException` | Process lacks read/write permissions | Check file permissions and the account running the application |
| `MalformedInputException` | Bytes are invalid for the selected decoding charset | Determine the correct charset or handle corrupted data |
| `FileAlreadyExistsException` | Using `CREATE_NEW` when the file already exists | Choose another name or handle the duplicate case |
| `InvalidPathException` | Input string cannot form a valid path | Validate input before calling `Path.of` |

`MalformedInputException` belongs to the character-coding error hierarchy and is also a subclass of `IOException`. Do not work around it by switching charsets arbitrarily; determine the file's actual encoding.

### 6.3. Distinguishing I/O Errors from Path Errors

`Path.of(...)` can throw `InvalidPathException` immediately when constructing the path. `Files.readString(...)` or `writeString(...)` can throw `IOException` when performing filesystem operations.

If the path is supplied by a user, validate it against the root directory the application is permitted to access. Never concatenate an arbitrary path from a request directly into a storage location without boundary checks.

## 7. Reading and Writing Multiline Text

### 7.1. Writing Multiple Lines

You can construct a multiline string using a text block or by joining lines:

~~~java
String content = """
        id,name,status
        1,Alice,ACTIVE
        2,Bob,INACTIVE
        """;

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

A text block preserves newline characters according to language rules. `writeString` writes the exact string passed; it does not append an extra newline after the content.

If generating content dynamically:

~~~java
String content = String.join(
        System.lineSeparator(),
        "id,name,status",
        "1,Alice,ACTIVE",
        "2,Bob,INACTIVE"
) + System.lineSeparator();

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

The final line has a newline because we explicitly appended `System.lineSeparator()`.

### 7.2. Reading Content and Processing Line by Line

If the file is small, you can read it all and then use `lines()`:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);

content.lines()
        .map(String::strip)
        .filter(line -> !line.isEmpty())
        .forEach(System.out::println);
~~~

This is simple, though the entire file is still loaded into memory before processing.

### 7.3. Do Not Confuse readString with readAllLines

The two methods return different types:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

- `readString` returns a single string, preserving newline characters inside it.
- `readAllLines` returns a list of lines, without retaining line terminators at the end of each element.

If you need to work with text as a single block, `readString` is more convenient. If you need to iterate over lines of a small file, `readAllLines` can be appropriate.

## 8. When Should You Avoid readString/writeString?

`readString` reads the entire content into one `String`. Thus, file size and available memory are important factors.

Use them when:

- Small or medium configuration files.
- Small JSON, XML, or CSV files passed to a string-based parser.
- Templates or text documents of bounded, manageable size.
- The problem genuinely needs the entire content at once.

Consider streaming when:

- Very large log files.
- Data files with millions of lines.
- The application must process line by line without keeping everything in RAM.
- Files are generated or processed continuously.

### 8.1. Streaming Reads with BufferedReader

~~~java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;

    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

`BufferedReader` enables line-by-line processing. The `try-with-resources` block ensures the reader is closed even if processing throws an exception.

### 8.2. Streaming Writes with BufferedWriter

~~~java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedWriter writer =
             Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("id,name");
    writer.newLine();
    writer.write("1,Alice");
    writer.newLine();
}
~~~

`BufferedWriter` is suitable when content is generated incrementally. You do not need to concatenate everything into one large string before writing.

### 8.3. Files.lines and Closing the Stream

`Files.lines(path)` creates a `Stream<String>` to read lines lazily. This stream keeps a file resource open, so it must be closed, typically with `try-with-resources`:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> line.contains("ERROR"))
            .forEach(System.out::println);
}
~~~

Do not return the stream from a method after it has been closed, and do not forget to close it. For simple sequential line processing, `BufferedReader` is often easier to reason about.

## 9. Overwriting, Appending, and Data Safety

Your choice of `OpenOption` directly affects file contents.

| Requirement | Common Options |
|---|---|
| Create new or overwrite entire file | `CREATE, TRUNCATE_EXISTING, WRITE` |
| Append to the end | `CREATE, WRITE, APPEND` |
| Create only if it does not exist | `CREATE_NEW, WRITE` |

### 9.1. Overwriting Can Destroy Previous Data

If old content must be preserved, do not accidentally use the default overload. Choose append or an appropriate versioning strategy.

~~~java
Files.writeString(path, "Replacement content", StandardCharsets.UTF_8);
~~~

This is a content-replacement operation, not an in-place partial update.

### 9.2. writeString Does Not Guarantee Atomic Replacement

`writeString` does not guarantee that writing an entire file always appears atomic to every other process. If the application must prevent readers from seeing a partially written target file, design a workflow that writes to a temporary file on the same filesystem and then moves it via `Files.move` with `ATOMIC_MOVE` when supported by the filesystem. You must handle cases where atomic move is unsupported and define your own replacement policy.

This is an advanced requirement; for small configuration files not shared concurrently, `writeString` is usually simple enough.

## 10. Complete Example: Reading and Updating a Text File

Create the file **`TextFileWorkflow.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TextFileWorkflow {

    public static void main(String[] args) throws IOException {
        Path path = Path.of("data", "notes.txt");

        // Create parent directories if needed.
        Files.createDirectories(path.getParent());

        // Write new or replace all content.
        String initialContent = """
                Java 17
                Files.readString
                Files.writeString
                """;

        Files.writeString(
                path,
                initialContent,
                StandardCharsets.UTF_8
        );

        // Read the entire content.
        String loaded = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("Current content:");
        System.out.print(loaded);

        // Append a line.
        Files.writeString(
                path,
                "Read and write succeeded" + System.lineSeparator(),
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND
        );

        // Read again to see content after appending.
        String updated = Files.readString(path, StandardCharsets.UTF_8);

        System.out.println("Updated content:");
        System.out.print(updated);
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 TextFileWorkflow.java
java TextFileWorkflow
~~~

Illustrative output:

~~~text
Current content:
Java 17
Files.readString
Files.writeString
Updated content:
Java 17
Files.readString
Files.writeString
Read and write succeeded
~~~

The first write uses the default options, so it creates or replaces the content. The second write passes `APPEND`, so the new content is added to the end of the file. Both calls use UTF-8.

## 11. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `NoSuchFileException` when writing | Parent directory does not exist yet | Call `Files.createDirectories(path.getParent())` when parent is non-null |
| Old content disappears after writeString | Default overload truncates the existing file | Use `APPEND` if you want to append |
| Non-ASCII / accented text displays corrupted characters | Wrong charset compared to the file's encoding | Determine the actual encoding and pass the matching `Charset` |
| File lacks a trailing newline after writing | `writeString` does not automatically append a newline | Add `System.lineSeparator()` or `\n` according to format |
| Large file causes high RAM usage | `readString` loads the entire content into a single string | Use `BufferedReader` or `Files.lines` and close the resource |
| `MalformedInputException` | Invalid bytes for the chosen charset | Verify the encoding rather than switching charsets randomly |
| Calling `getParent()` and passing null to createDirectories | Path contains only a filename without an explicit parent | Check that parent is non-null first |
| Calling `readString` when the file does not exist | No data to read | Check existence or handle `NoSuchFileException` |
| Using `CREATE_NEW` on an existing file | Option requires the file not to exist | Pick another name or handle the existing-file case |

## 12. Practice Exercises

### Exercise 1: Writing and Reading Back a UTF-8 File

Create a program that writes the UTF-8 text `"Hello Java 17 — Xin chào"` to `hello.txt`, then reads it back and prints it to the console.

**Suggested solution:**

~~~java
Path path = Path.of("hello.txt");

Files.writeString(path, "Hello Java 17 — Xin chào", StandardCharsets.UTF_8);

String content = Files.readString(path, StandardCharsets.UTF_8);
System.out.println(content);
~~~

### Exercise 2: Why Was Previous Data Lost?

Given:

~~~java
Files.writeString(path, "First line", StandardCharsets.UTF_8);
Files.writeString(path, "Second line", StandardCharsets.UTF_8);
~~~

After these two statements, what is the content of the file?

**Answer:** Only `"Second line"` remains because the second write uses the default `TRUNCATE_EXISTING` option. To keep both lines, use `APPEND` on the second write.

### Exercise 3: Appending Content

Write a statement that appends `"New line"` to the end of a file, creating the file if it does not exist.

**Answer:**

~~~java
Files.writeString(
        path,
        "New line" + System.lineSeparator(),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE,
        StandardOpenOption.APPEND
);
~~~

### Exercise 4: Handling Missing Directories

Why might writing to `data/logs/app.txt` fail if `data/logs` does not exist yet?

**Answer:** `writeString` can create the target file, but it does not create parent directories. Call:

~~~java
Path path = Path.of("data", "logs", "app.txt");
Files.createDirectories(path.getParent());
~~~

### Exercise 5: Choosing a Charset

A file is known to be UTF-8. Which overload should you use?

**Answer:** You can use `Files.readString(path)` because its default overload uses UTF-8, or write `Files.readString(path, StandardCharsets.UTF_8)` explicitly to document the encoding contract.

### Exercise 6: When Do You Need BufferedReader?

A log file is several gigabytes in size, and the program only needs to count lines containing `"ERROR"`. Should you call `readString`?

**Answer:** No, because `readString` loads the entire file into a single string. Use `Files.newBufferedReader` to iterate line by line and increment a counter, closing the reader with `try-with-resources`.

## 13. Key Takeaways

When working with text files in Java 17:

1. Use `Path.of(...)` to construct paths.
2. Use `Files.readString(path)` to read the entire content into a string.
3. Use `Files.writeString(path, text)` to write UTF-8; by default it creates a new file or truncates existing content.
4. Pass `StandardCharsets.UTF_8` or a specific charset when you want the encoding made explicit.
5. Use `StandardOpenOption.APPEND` together with `CREATE` and `WRITE` when appending.
6. Create parent directories before writing if needed.
7. Handle `IOException` and path errors appropriately.
8. Switch to streaming APIs when files are large or require line-by-line processing.

`readString` and `writeString` are concise choices for text of bounded size. Choosing the right charset and open options is what determines whether data is read and written as expected.

## 14. References

- [Oracle Java SE 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): specification of `readString`, `writeString`, open options, and streaming read/write APIs.
- [Oracle Java SE 17 — Path API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): creating and manipulating paths.
- [Oracle Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets guaranteed to be available in Java.
- [Oracle Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `TRUNCATE_EXISTING`, `WRITE`, `APPEND`, and `CREATE_NEW`.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): background on Java's default charset; note that `readString`/`writeString` overloads without a charset already standardized on UTF-8 since Java 11.
