# InputStream, Reader, and Concrete Subclasses in Java

Java provides two primary API families for reading data: `InputStream` reads **bytes**, whereas `Reader` reads **characters**. Choosing the right API family helps handle binary files, accented text, large data, and system resources accurately.

## 1. Distinguishing Byte Streams and Character Streams

| Criterion | `InputStream` | `Reader` |
|---|---|---|
| Read unit | Byte, with the return value in the range 0–255 when reading a single byte | UTF-16 code unit (`char`), with the return value in the range 0–65535 when reading a single character |
| Common purpose | Images, PDFs, audio, compressed files, binary data, or undecoded bytes | Text that needs to be decoded into characters |
| Basic read methods | `int read()`, `int read(byte[] b)` | `int read()`, `int read(char[] cbuf)` |
| End-of-data indicator | `-1` | `-1` |
| Key conversion class | `InputStreamReader` converts bytes into characters using a charset | `OutputStreamWriter` is the writing class in the reverse direction, converting characters into bytes |

A Java `char` is a UTF-16 code unit, which is not always equivalent to a complete Unicode character. Some characters outside the Basic Multilingual Plane are represented by a surrogate pair. For typical text processing, use `Reader` and the string APIs; do not assume that the number of bytes, the number of `char` values, and the number of user-perceived characters are always equal.

**Quick selection rule:** use `InputStream` when you need raw bytes; use `Reader` when you need decoded text. Do not pass binary data through a `Reader`, because the decoding process can alter the meaning of the bytes.

## 2. Common InputStream Classes

The classes in the JDK serve different roles:

- **`FileInputStream`** reads bytes from a file. It is suitable when direct byte access is needed; if the goal is text, combine it with `InputStreamReader` or use the `Files` API.
- **`ByteArrayInputStream`** reads from a byte array in memory. It is useful for examples, testing, and processing already-available data.
- **`BufferedInputStream`** adds buffering to reduce the number of accesses to the data source when reading in small chunks.
- **`DataInputStream`** reads binary primitive data types such as `int`, `long`, and `boolean` according to a format agreed upon by the program. It does not automatically turn bytes into text and is not a schema-based storage format.
- **`ObjectInputStream`** reads objects serialized using Java Serialization. Only use trusted data or apply an appropriate filter; do not treat arbitrary serialization data as safe.
- **`PipedInputStream`** receives bytes from a `PipedOutputStream`, typically used when two execution threads need to exchange data.
- **`SequenceInputStream`** reads sequentially from multiple `InputStream` sources as if they were concatenated.

Example of reading bytes from memory:

```java
byte[] data = {10, 20, 30};

try (InputStream input = new ByteArrayInputStream(data)) {
    int value;
    while ((value = input.read()) != -1) {
        System.out.println(value);
    }
}
```

Output:

```text
10
20
30
```

`read()` returns `int` instead of `byte` so it can represent every unsigned byte value from 0 to 255 and reserve `-1` for EOF (end of stream). If you immediately cast the result to `byte`, values greater than 127 can become negative numbers.

## 3. Common Reader Classes

- **`InputStreamReader`** is the bridge between a byte stream and a character stream. It decodes bytes using the specified charset.
- **`FileReader`** reads characters from a file. For new code, you should specify the charset explicitly using a constructor that accepts a charset (Java 11+) or use `Files.newBufferedReader(path, charset)`.
- **`BufferedReader`** adds buffering and provides `readLine()`, which is convenient when processing text line by line.
- **`StringReader`** reads text from a `String` object, which is useful when testing a parser without creating a file.
- **`CharArrayReader`** reads from a `char` array.
- **`PushbackReader`** allows pushing some recently read characters back into the stream, which is often useful when writing a parser that needs to look ahead by a character.

Example of reading line by line from a string:

```java
String text = "alpha\nbeta\n";

try (BufferedReader reader = new BufferedReader(new StringReader(text))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

Output:

```text
alpha
beta
```

`readLine()` strips line terminators from the returned value. It returns `null` when the end of the stream is reached and there are no more lines to read; therefore, the correct loop typically takes the form `while ((line = reader.readLine()) != null)`.

## 4. Charset: A Critical Step When Reading Text

Text files store bytes according to a specific encoding, such as UTF-8. `Reader` works with characters, so bytes must be decoded using the matching charset. If a different charset from the one used for writing is applied, the text may become corrupted characters or mojibake.

You should specify the charset explicitly:

```java
Path path = Path.of("message.txt");

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

This snippet requires the imports `java.io.BufferedReader`, `java.nio.charset.StandardCharsets`, `java.nio.file.Files`, and `java.nio.file.Path`.

Another approach when the source is already an `InputStream`:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
    // Read text from reader
}
```

In the second example, `inputStream` must be an open and properly managed `InputStream` variable. `InputStreamReader` performs the decoding; `BufferedReader` adds buffering and line-reading convenience.

Do not rely on the machine's default charset to read data with a known format. When reading files produced by another system, the charset is part of the data protocol and needs to be agreed upon explicitly.

## 5. Reading in Chunks and Using Buffering

Reading one byte or one character at a time can cause many method calls. For large data, it is generally better to read into an array or use a buffered class.

```java
try (InputStream input = new BufferedInputStream(
        Files.newInputStream(Path.of("image.bin")))) {
    byte[] buffer = new byte[8192];
    int count;

    while ((count = input.read(buffer)) != -1) {
        // Process buffer[0] through buffer[count - 1].
        // Do not process the entire array if count is less than buffer.length.
    }
}
```

`count` is the number of valid bytes in the current read. The final read may read fewer bytes than the array size. The bytes after `count - 1` may still hold leftover data from the previous read, so process only the portion just reported as read.

For text, use buffering at the appropriate layer, such as `BufferedReader`. It can reduce I/O operations and provides `readLine()`. There is no need to mechanically stack multiple buffering layers; choose a simple structure suited to the source and reading pattern.

Some convenient methods available since Java 9:

- `InputStream.readAllBytes()` reads all remaining bytes into a byte array.
- `InputStream.readNBytes(n)` reads at most the requested number of bytes.
- `InputStream.transferTo(out)` transfers bytes to an `OutputStream`.
- `Reader.transferTo(writer)` transfers characters to a `Writer`.

Methods that read everything at once should only be used when the data size fits in memory. For large files or streams without a clear size bound, reading in chunks is generally safer.

## 6. Resource Management with try-with-resources

Streams can hold file descriptors, sockets, or other system resources. Closing a stream when finished is part of proper handling.

```java
try (InputStream input = Files.newInputStream(Path.of("data.bin"))) {
    // Read data
}
```

When leaving the `try` block, Java automatically calls `close()`, even if an exception occurs. `Reader` also implements `Closeable`/ `AutoCloseable` and can be used in the same way.

Closing a wrapper usually closes the underlying stream as well. For example, closing `BufferedReader` closes the `InputStreamReader` and `InputStream` it wraps. Therefore, avoid redundantly closing nested layers over and over; clearly identify what owns and is responsible for closing the resource.

Do not swallow I/O exceptions and pretend the data was read successfully. Depending on the application, handle or propagate `IOException` so the caller can respond to file, permission, or connection errors.

## 7. Complete Runnable Java 17+ Example

The program below uses the same UTF-8 content to demonstrate that `InputStream` counts bytes while `Reader` decodes them into text. Save the file as `StreamReaderDemo.java`.

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class StreamReaderDemo {
    public static void main(String[] args) throws Exception {
        String text = "Xin chào\nJava 17\n";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

        int totalBytes = 0;
        try (InputStream input = new ByteArrayInputStream(encoded)) {
            byte[] buffer = new byte[4];
            int count;
            while ((count = input.read(buffer)) != -1) {
                totalBytes += count;
            }
        }
        System.out.println("UTF-8 bytes: " + totalBytes);

        try (Reader decoded = new InputStreamReader(
                    new ByteArrayInputStream(encoded),
                    StandardCharsets.UTF_8);
             BufferedReader reader = new BufferedReader(decoded)) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("Line: " + line);
            }
        }
    }
}
```

Compile and run:

```bash
javac StreamReaderDemo.java
java StreamReaderDemo
```

Exact stdout:

```text
UTF-8 bytes: 18
Line: Xin chào
Line: Java 17
```

Explanation:

1. `getBytes(StandardCharsets.UTF_8)` encodes the string into UTF-8 bytes.
2. The `InputStream.read(buffer)` loop adds the number of bytes actually read, rather than adding the entire array size each time.
3. `InputStreamReader` decodes the same byte array with UTF-8.
4. `BufferedReader.readLine()` returns each line without retaining newline characters.
5. `try-with-resources` automatically closes the streams. In the second block, closing `BufferedReader` also closes the `Reader` it wraps.

The sample string contains the letter `à`, which is UTF-8 encoded as two bytes; therefore, the number of UTF-8 bytes does not necessarily equal the number of characters in the text.

## 8. Common Mistakes

- **Using `InputStream` as if it reads text:** bytes are not automatically characters. Decode them using `InputStreamReader` with the proper charset.
- **Not specifying a charset:** the result may depend on the environment or fail to match the file's format. Use UTF-8 when that is the data's encoding.
- **Assuming a single `read(byte[])` call will fill the array:** a single read may return fewer bytes than expected. Always use the return value to determine the valid portion.
- **Forgetting EOF:** `read()` returns `-1` when there is no more data; failing to check for EOF can cause incorrect loops or infinite loops.
- **Treating `available()` as the remaining file size:** this method only estimates the number of bytes that can be read or skipped without blocking; do not use it to allocate an array to hold all the data.
- **Not closing streams:** resources may be held longer than necessary. Use try-with-resources.
- **Reading an entire large file into memory:** `readAllBytes()` and similar approaches can consume significant memory. Prefer reading in chunks for large data.
- **Using `readLine()` and expecting the newline character back:** the method strips line terminators. If the format requires preserving exact bytes or newlines, process at the byte level or use an appropriate API.
- **Trusting Java Serialization data from unknown sources:** `ObjectInputStream` can instantiate objects during reading. Do not deserialize untrusted data without proper safeguards.

## 9. API Selection Checklist

- Need the exact bytes of an image, PDF, compressed file, or binary data: `InputStream`.
- Need to read characters from bytes in UTF-8: `InputStreamReader` with an explicit charset.
- Need to read text line by line: wrap a `Reader` with `BufferedReader`.
- Need to read from a text file: consider `Files.newBufferedReader(path, charset)`.
- Need to read from an in-memory string: `StringReader`.
- Need to read from an in-memory byte array: `ByteArrayInputStream`.
- Need to process large data: read in chunks, use only the number of bytes or characters actually returned, and close resources with try-with-resources.

The core takeaway is to determine whether the data is in byte or text form, choose the right conversion class, declare the charset when decoding, and manage stream lifecycles explicitly.
