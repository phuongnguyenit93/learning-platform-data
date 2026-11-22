# Java Core I/O Scope and JDK Version Differences

> **Context:** Java Core – I/O, under the **I/O Overview** group. This lesson identifies which parts of I/O belong to Java SE, how to choose an API by data type, and the differences to check when running or compiling with different JDK versions. The milestones below are representative changes, not an exhaustive catalog of every change in each JDK release.

## 1. Learning Objectives

After this lesson, you will be able to:

- Identify the Java SE packages that provide I/O, distinguishing them from frameworks or external libraries.
- Choose between **byte** streams, **character** streams, **file/path** operations, **channel/buffer**, and blocking/asynchronous mechanisms.
- Recognize APIs available in Java 8, those introduced in Java 9/10/11/12, and the **default charset** change starting in JDK 18.
- Write file read/write code with an explicit charset, close resources properly, and verify compilation against the target Java version.
- Understand the difference between APIs permitted at compile time, the runtime environment, and the impact of virtual threads in JDK 21.

## 2. What Is the Scope of Java Core I/O?

**I/O (Input/Output)** is the operation of receiving data into or sending data out of the computation part: files, memory, standard devices, network connections, and file systems. Here, **Java Core** refers to the standard APIs in Java SE provided by the JDK; you do not need to add any Maven/Gradle dependency to use the following classes.

| Standard API | Primary Purpose | Examples |
| --- | --- | --- |
| `java.io` | Byte streams, character streams, buffering, primitive data, serialization | `InputStream`, `OutputStream`, `Reader`, `Writer`, `BufferedReader`, `DataInputStream` |
| `java.nio` | Buffers and data structures supporting I/O | `ByteBuffer` |
| `java.nio.channels` | Channels, positional access, non-blocking I/O for supported channels | `FileChannel`, `SocketChannel`, `Selector` |
| `java.nio.file`, `java.nio.file.attribute` | Paths, file reading/writing, directory management, file metadata | `Path`, `Files`, `FileVisitor`, `BasicFileAttributes` |
| `java.nio.charset` | Byte ↔ character encoding rules | `Charset`, `StandardCharsets`, `CharsetDecoder` |
| `java.util.zip` | Compression/decompression on streams | `ZipInputStream`, `GZIPOutputStream` |

The standard streams `System.in`, `System.out`, and `System.err` also belong to Java SE; `System.out` is a `PrintStream`. Network I/O has the standard `java.net` API, though detailed socket/HTTP analysis belongs to networking topics. JDBC, servlet containers, Spring Web, and framework utility classes are not Java Core I/O APIs merely because they also read or write data.

### 2.1. Byte streams, character streams, and file APIs

- **Byte streams** (`InputStream`/`OutputStream`) work with raw bytes: images, PDFs, ZIPs, binary protocols. `InputStream.read()` returns a value from 0–255 or `-1` at end of data; `read(byte[])` may return fewer bytes than the buffer length.
- **Character streams** (`Reader`/`Writer`) work with characters. When connected to a file or socket, bytes must be decoded according to a charset; a single Unicode character may take multiple UTF-8 bytes. For example, `InputStreamReader` bridges a byte stream to a reader.
- **`Path` and `Files`** manage paths and the filesystem: creating, reading, writing, moving, and checking file attributes. `Path.of("data.txt")` only creates a relative path; it does not create a file and does not check whether the file exists. `java.io.File` is the legacy API, which can be converted to `Path` using `file.toPath()`.
- **Channel/Buffer** supports block-based data, random-position access, non-blocking operations on appropriate channels, and advanced options. Not every class in the `java.nio` package is non-blocking: `Files.readAllBytes` still blocks while reading.
- **NIO.2** includes the `Path`, `Files`, `WatchService`, and `AsynchronousFileChannel` APIs, available since **Java 7**; you do not need Java 11 or 21 to have them.

### 2.2. General Principles Independent of JDK Version

I/O can fail due to a missing file, insufficient permissions, device failure, out of disk space, invalid paths, or network errors; handle `IOException` according to application policy. Close `InputStream`, `Reader`, `Writer`, `FileChannel`, and streams returned by `Files.list`/`Files.walk`/`Files.lines` when done; typically use **try-with-resources**. For large data, avoid loading everything into RAM with `readAllBytes` or `readString`; process line by line or use a fixed-size buffer.

Distinguish **blocking I/O** (a call may wait for data) from non-blocking/asynchronous I/O (which provides a mechanism to track progress without blocking in the traditional way). The `nio` package name alone is not enough to determine the execution mechanism.

## 3. Key JDK Version Milestones

| Version | Representative API / Change | Significance |
| --- | --- | --- |
| **Java 7** | NIO.2: `Path`, `Files`, `WatchService`, `AsynchronousFileChannel`; try-with-resources | The modern file API foundation and automatic resource closing mechanism have existed since before Java 8. |
| **Java 8** | `Files.lines`, `Files.list`, `Files.walk`, `Files.find` | Integrates file/directory APIs with the Stream API; returned streams hold resources that must be closed properly. |
| **Java 9** | `InputStream.readAllBytes()`, `readNBytes(byte[],int,int)`, `transferTo(OutputStream)`; `javac --release` | More convenient stream operations, and target API verification at compile time. |
| **Java 10** | `Reader.transferTo(Writer)` | More concise copying of character content from a reader to a writer. |
| **Java 11 (LTS)** | `Path.of(...)`, `Files.readString`, `Files.writeString`, `InputStream.readNBytes(int)`, `InputStream.nullInputStream()` | Simpler string/file/byte APIs, though unavailable on Java 8. |
| **Java 12** | `Files.mismatch(Path,Path)`, `InputStream.skipNBytes(long)` | Finds the position of the first differing byte between two files; skips the exact number of bytes if enough remain. |
| **Java 17 (LTS)** | Common deployment baseline, inheriting the APIs above | Do not assume that all I/O APIs or the default charset changed at Java 17. |
| **Java 18** | **JEP 400: UTF-8 by Default** | Java SE APIs that rely on the default charset use UTF-8 in the default configuration; behavior may differ compared to JDK 8/11/17. |
| **Java 21 (LTS)** | **Virtual threads** finalized under JEP 444 | Provides an option to scale concurrent I/O-waiting tasks; does not replace `Files`/`InputStream` entirely. |

**Two different kinds of checks:** If a project targets Java 8, a call introduced in Java 11 is **invalid at compile time against the Java 8 API**. Conversely, the same compiled source can still change behavior when upgrading the **runtime**, for example when relying on the default charset.

## 4. Charsets and Differences Before/After JDK 18

Data in files consists of **bytes**, whereas `String`/`Reader` represents **characters**. When converting between them, the program must use a charset such as UTF-8. If the writer encodes with UTF-8 but the reader decodes with a different charset, Vietnamese text may become corrupted or the read operation may report invalid data.

- **JDK 17 and earlier:** `Charset.defaultCharset()` typically depends on the operating system/locale/configuration; the same program can behave differently across machines.
- **From JDK 18 onward:** JEP 400 specifies **UTF-8 as the default charset for relevant Java SE APIs in the default configuration**. This does not mean all external bytes are UTF-8, or that upgrading the runtime will automatically re-encode old files.
- **Very important exception:** Certain `Files` overloads have **mandated UTF-8 independently of the default charset** since before JDK 18, such as `Files.newBufferedReader(path)` and `Files.newBufferedWriter(path)`; since Java 11, `Files.readString(path)`/`writeString(path, text)` also use UTF-8. Meanwhile, `new InputStreamReader(input)`, `new String(bytes)`, and `text.getBytes()` (without a charset argument) depend on the default charset.
- For consistent behavior across JDKs/OSes, use overloads that take `StandardCharsets.UTF_8`: `new InputStreamReader(input, StandardCharsets.UTF_8)`, `new String(bytes, StandardCharsets.UTF_8)`, `text.getBytes(StandardCharsets.UTF_8)`, and `Files.readString(path, StandardCharsets.UTF_8)`.
- For legacy data repositories using another charset, you must determine the **actual charset** before migrating; forcing UTF-8 when reading old data does not convert the bytes into UTF-8.

**Example where you should not rely on the default charset:** reading bytes from an old file and calling `new String(bytes)`. The result may differ between Java 8/17 and Java 18/21. The right approach is to know the charset used to write the file and pass that charset when decoding.

## 5. Java 8 Example: File APIs and Consistent UTF-8

Create **`IoJava8.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoJava8 {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-java8-", ".txt");
        try {
            byte[] data = "Xin chào Java".getBytes(StandardCharsets.UTF_8);
            Files.write(file, data);

            byte[] restored = Files.readAllBytes(file);
            System.out.println(new String(restored, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run:

~~~bash
javac IoJava8.java
java IoJava8
~~~

Exact stdout:

~~~text
Xin chào Java
~~~

`Files.createTempFile` creates a file with a random name, and `finally` attempts to delete the file after use, even if an error occurs. `Files.write` writes bytes and therefore does not involve the default charset; the charset is specified when converting `String` to bytes and vice versa. This example runs on **Java 8** and newer JDKs because it only uses APIs available since Java 7–8. `readAllBytes` is used here because the content is small; do not use it as a pattern for reading multi-gigabyte files.

## 6. Java 11+ Example: `Files.readString` and `Files.writeString`

Create **`IoJava11.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class IoJava11 {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-java11-", ".txt");
        try {
            Files.writeString(file, "Dữ liệu UTF-8\n", StandardCharsets.UTF_8);
            String text = Files.readString(file, StandardCharsets.UTF_8);
            System.out.print(text);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac IoJava11.java
java IoJava11
~~~

Stdout:

~~~text
Dữ liệu UTF-8
~~~

`Files.writeString/readString` are available since **JDK 11**. Do not use this code if the project still targets Java 8. `Files.readString` reads the entire file at once, which can consume significant memory for large files; it manages opening and closing the file internally. Without an `OpenOption` argument, `Files.writeString` creates the file if needed and overwrites existing content; in real applications, explicitly specify whether "append" or "overwrite" is required.

For large text files, **Java 8 also provides** `Files.newBufferedReader` to read line by line:

~~~java
// Illustration placed inside a method that can throw IOException.
// path is a Path variable pointing to a UTF-8 text file.
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(
             path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process the line here; do not collect the entire content into a List/String.
    }
}
~~~

This is an **illustrative fragment**, not a standalone program, because `path` and the line-processing logic are supplied by the caller. `readLine` strips line-termination characters, which you must keep in mind if the original file formatting needs to be preserved.

## 7. Copying Byte Streams: Java 8 and Java 9

To copy binary content, do not convert it into a `String`. With Java 8:

~~~java
// in is an open InputStream and out is an open OutputStream.
byte[] buffer = new byte[8192];
int n;
while ((n = in.read(buffer)) != -1) {
    out.write(buffer, 0, n);
}
~~~

The value `n` is the **actual number of bytes read**. Writing `out.write(buffer)` instead of `out.write(buffer,0,n)` may write leftover bytes from the previous read, especially on the final iteration. The caller is responsible for closing `in` and `out` properly.

From Java 9 onward, this can be shortened:

~~~java
// in: InputStream, out: OutputStream (API since Java 9).
long count = in.transferTo(out);
~~~

`InputStream.transferTo` copies all remaining bytes and returns the number of bytes transferred; it **does not automatically close** the two streams. `InputStream.readAllBytes()` is also from Java 9, but it reads everything into RAM. `InputStream.readNBytes(byte[],off,len)` from Java 9 attempts to read until the requested count is reached or EOF occurs, unlike `read(byte[])`, which may return fewer bytes even before EOF. These options do not eliminate the need to handle `IOException`.

## 8. Choosing an API by Task, Not Just by Version

| Task | API to Consider | Notes |
| --- | --- | --- |
| Read small text, JDK 11+ | `Files.readString(path, UTF_8)` | Easy to understand, avoids system charset dependency; loads the entire file into RAM. |
| Write small text, JDK 11+ | `Files.writeString(path, text, UTF_8)` | Explicitly specify file creation, overwrite, or append with `OpenOption` when needed. |
| Read large text, including Java 8 | `Files.newBufferedReader(path, UTF_8)` | Use try-with-resources and process line by line. |
| Read/write images, ZIP, binary | `InputStream`/`OutputStream` or `Files.newInputStream`/`newOutputStream` | Copy bytes intact; do not decode as text. |
| List/traverse directories | `Files.list`, `Files.walk`, or `Files.walkFileTree` | Handle permissions, symlinks, and errors; close streams when needed. |
| Random positions in a file | `FileChannel` or `RandomAccessFile` | Manage position/buffer; does not equate to async. |
| Thousands of waiting sockets | Channels/selectors or an appropriate threading model | This is a networking/concurrency design choice; benchmark real workloads. |
| Java 8 deployment | `Files`/`Path`/buffered stream APIs available before Java 9 | Avoid accidentally using newer `readString` or `transferTo`. |

`Files.lines(path)` returns a `Stream<String>` that can be read lazily and must be closed to release resources; `Files.readAllLines(path)` reads all lines into a `List<String>`. The Stream API **does not automatically make I/O non-blocking**. Nor should `Files.readAllBytes` be considered optimal merely because the method call is short.

## 9. API Compatibility and Runtime Compatibility

### 9.1. Compiling Against the Target API

If distributing an application to run on Java 8, verify that no newer methods are used. On `javac` versions supporting `--release` (JDK 9+), compile the Java 8 example as follows:

~~~bash
javac --release 8 IoJava8.java
java IoJava8
~~~

If you try `javac --release 8 IoJava11.java`, compilation fails because `Files.readString/writeString` do not exist in the Java 8 API. `--release` constrains the language level, bytecode, and Java SE API so the build matches the target. It is not a substitute for running tests on an actual Java 8 runtime, especially regarding permissions, OS/file system providers, and real data.

### 9.2. Checking the Runtime and Environment

Upgrading from JDK 8/11/17 to 21 may not touch any API in the source code yet still expose bugs due to **the default charset change in JDK 18**, relative paths, the working directory, file permissions, symbolic links, and file system interactions. You should test with Vietnamese data, Unicode file names, empty files, missing/oversized files, and read/write failure scenarios.

Commands to identify the environment:

~~~bash
java -version
javac -version
~~~

In Gradle/Maven, do not confuse the **JDK used to run the build tool**, the **compilation JDK/toolchain**, the **target release/API**, and the **production runtime**. They can differ. The specific configuration must match the target JDK, and tests should then be run in the actual deployment environment.

## 10. How Do Virtual Threads in Java 21 Affect I/O?

Java 21 finalized **virtual threads** (JEP 444), helping applications with many concurrent I/O-waiting tasks use thread resources more efficiently in runtime-supported scenarios. However, this **does not make files or networks faster**, does not turn `Files.readString` into an API returning a `Future`, and does not require replacing all existing code.

A virtual thread can temporarily yield its carrier thread during runtime-supported blocking I/O; you must still account for operations inside `synchronized` blocks or native calls, because in JDK 21 **pinning** scenarios can hold the carrier thread while waiting. **NIO selectors**, **AsynchronousFileChannel**, and **virtual threads** serve different concurrency models and should be chosen based on workload. For this overview lesson, the focus remains on choosing the data type, charset, error handling, and resource closing; threading has its own dedicated lesson.

## 11. Common Mistakes

1. **"NIO is always non-blocking."** False: `Files.readAllBytes` can block. Check the specific method/channel contract.
2. **"A single `read(buffer)` fills the entire buffer."** False: use the returned byte count; `-1` indicates EOF.
3. **"Using Reader to copy a ZIP file works fine."** False: decoding text can alter the original bytes.
4. **"The system charset is always UTF-8."** Not true across all JDKs/configurations; choose the charset explicitly.
5. **"Upgrading to JDK 21 will automatically read legacy-encoded files correctly."** No: you must know the actual encoding of the stored data.
6. **"Files.lines/list/walk do not need to be closed."** These streams can hold system resources; use try-with-resources.
7. **"readAllBytes is suitable for any file size."** There is a risk of running out of heap memory; use buffers or line-by-line reading for large data.
8. **"A method available on a JDK 21 machine will run on Java 8."** Check `--release 8` and the target runtime.
9. **"Writing a string automatically appends."** `Files.writeString` overwrites content by default; specify open options as needed.
10. **"Path.of creates the file immediately."** It only creates a path object. A relative path also depends on the working directory.
11. **"Failed I/O never leaves partial data behind."** Partial reads/writes may have occurred before the failure; define a cleanup, backup, or write-to-temp + replace strategy when atomicity is needed.

## 12. Self-Check

1. Should you use `InputStream` or `Reader` to copy a PNG image? Why?
2. Why cannot a project targeting Java 8 compile `Files.readString`?
3. How many bytes should a `read(buffer)` loop write on each iteration?
4. Which JDK changed the default charset to UTF-8, and does that automatically resolve data stored in older charsets?
5. How do `Files.lines` and `Files.readAllLines` differ in data loading timing, memory usage, and resource management?

**Answer hints:** (1) byte stream to preserve raw bytes; (2) the method was introduced in Java 11; (3) the exact number of bytes `n` returned; (4) JDK 18, it does not automatically re-encode files; (5) a lazy stream that must be closed vs. a `List` holding all lines.

## Official References by JDK

- [Oracle Java SE 11: InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html) — check the "Since" section for `readAllBytes`, `readNBytes`, `transferTo`.
- [Oracle Java SE 11: Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html) — string read/write overloads and UTF-8.
- [Oracle Java SE 21: Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html) — file API contract on modern JDKs.
- [OpenJDK JEP 400 – UTF-8 by Default](https://openjdk.org/jeps/400) — change introduced in JDK 18.
- [OpenJDK JEP 444 – Virtual Threads](https://openjdk.org/jeps/444) — JDK 21 release and its relationship with blocking I/O.

**Practical rule:** choose an API based on **data type**, **size**, **charset**, **concurrency mechanism**, and **minimum JDK**. When upgrading the JDK, verify both compile-time APIs and runtime behavior; proper error handling and resource closing remain essential.