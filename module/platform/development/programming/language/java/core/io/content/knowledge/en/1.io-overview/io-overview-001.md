# What is I/O? The roles of source, destination, and data

In Java, **I/O (Input/Output)** is the operation in which a program **receives data from outside** or **sends data outside** its processing boundary. “Outside” does not necessarily mean the Internet or a physical device: a file, keyboard, network connection, another process, and a memory region already containing bytes can all participate in I/O.

An I/O operation should always be described in terms of three components:

- **Source:** where data is read or received from.
- **Data:** the content moving from source to destination; its format, size, and encoding need to be understood.
- **Destination:** where data is written or sent to.

**The “input” and “output” directions are determined from the perspective of the program under consideration**, not by device names.

## 1. Distinguishing input and output

- **Input:** data flowing **into the program**. For example: the program reads the contents of `config.txt`, receives a line typed by the user, or reads bytes from a connection.
- **Output:** data flowing **out of the program**. For example: the program writes `report.txt`, displays results to standard output, or sends a response over the network.
- The same program often does both: reading a source file, transforming the content, and then writing to a destination file.

```text
                                  INPUT                           OUTPUT
[Source: file/keyboard/network] --------> [PROGRAM] ---------> [Destination: file/screen/network]
                             data flowing in         data flowing out
```

For example, a text conversion application: `raw.txt` is the **source**, and the bytes/strings read from it are the **input data**; the program converts them to uppercase; `upper.txt` is the **destination** containing the **output data**. The output content can differ from the input content because the program has processed it.

I/O is not synonymous with computation. The operation `sum = a + b` processes data already in memory, but by itself does not read from an external source or write to an external destination. Conversely, `System.out.println(sum)` performs output.

## 2. Source: where does the program get data from?

A source can be:

| Source | Java example | What the program receives |
|---|---|---|
| Keyboard or standard input | `System.in` | Bytes entering the standard input stream; can be decoded into characters |
| File on the filesystem | `Files.newInputStream(path)` or `Files.readString(path)` | Bytes or text read from a file |
| Network connection | `socket.getInputStream()` | Bytes transmitted by the other end |
| Memory region | `ByteArrayInputStream` | Bytes already placed in an array |
| Data produced by another component | An `InputStream` provided by a library | Bytes received through a reading interface |

A source does not necessarily “push” data into Java on its own: the program usually actively calls `read()` or a reading API. A read call may need to wait for data, reach the end of the stream, or throw an error. Do not assume a single read is enough for the entire content.

**Source is a role at a specific step, not a fixed property of a file.** `fileA.txt` is a source when being read; if another step writes to that same file, it becomes the destination of that write step.

## 3. Destination: where is data sent?

A destination can be:

| Destination | Java example | Effect |
|---|---|---|
| Standard output | `System.out` | Prints information to the standard output stream, commonly seen in the terminal |
| Standard error | `System.err` | Sends error messages to the standard error stream |
| File | `Files.newOutputStream(path)` or `Files.writeString(path, text)` | Saves data to a file |
| Network connection | `socket.getOutputStream()` | Sends bytes to the other end |
| Memory region | `ByteArrayOutputStream` | Collects output bytes in memory |

`System.out` **is not always synonymous with the screen**. When running `java Main > output.txt`, the shell redirects standard output to a file; from Java’s perspective, the program still writes to `System.out`.

When writing, the program needs to know **whether the destination allows writing**, **whether to overwrite or append**, and **when the data has been transferred from the buffer to the underlying layer**. Writing to a stream does not by itself guarantee that the data has been durably saved on disk or that the receiving side has processed it.

## 4. Data: what is actually transmitted

I/O transports **data**, not necessarily Java objects directly in their raw in-memory form. Two important perspectives:

1. **Bytes (binary):** suitable for images, compressed files, audio, protocol data, or copying arbitrary files. `InputStream` reads bytes; `OutputStream` writes bytes.
2. **Characters/text:** suitable for prose, configuration lines, and text data. `Reader` reads characters; `Writer` writes characters. When storing or transmitting text as bytes, a **character encoding** (charset) such as UTF-8 is needed.

For example, the Java string `"Xin chào"` is text, whereas when writing a UTF-8 file, the string is **encoded into bytes**. When reading a file into a string, the bytes need to be **decoded with the right charset**. If written using UTF-8 but read using a different charset, Vietnamese characters may become corrupted. For binary files, do not arbitrarily convert all bytes into a `String`.

Beyond the content itself, you need to know **data boundaries**: a file has an end, a network message may require a length rule or delimiter, and reading a few bytes does not necessarily yield a complete “message”.

```text
TEXT                              BYTE                         TEXT
"Xin chào" --encode UTF-8--> [byte sequence] --decode UTF-8--> "Xin chào"
```

## 5. I/O flow in Java

For a file copy operation:

```text
source.txt  --read bytes-->  buffer in Java  --write bytes-->  destination.txt
  SOURCE                          DATA                           DESTINATION
```

- `InputStream.read(byte[])` requests fetching bytes from the source into a buffer. The return value is the **actual number of bytes read**, or `-1` when the stream ends. You must not assume each read fills the buffer completely.
- `OutputStream.write(buffer, 0, count)` writes only the `count` valid bytes just read. Writing the entire array can introduce stale or invalid data.
- The buffer is a temporary holding area for data between reading and writing. **The buffer is not the final source or destination** in this example.
- `try-with-resources` closes the streams when exiting the block, even if an exception occurs. `IOException` represents I/O errors that must be handled or declared.

In Java there are multiple API levels. `Files.readString(path, UTF_8)`/`Files.writeString(path, text, UTF_8)` are convenient for text of a size that fits in memory; `InputStream`/`OutputStream` allow processing data in chunks, suitable when copying bytes independently of format. `Reader`/`Writer` are suitable when you need to process characters rather than bytes.

## 6. Runnable example: file source, file destination, byte data

This example uses Java 17+, creates two temporary files, writes UTF-8 text into the source file, **copies the bytes** from source to destination using I/O streams, and then reads the destination to verify. The source and destination files are deleted when the program finishes.

Save the following code as **`IoRolesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class IoRolesDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("io-source-", ".txt");
        Path destination = Files.createTempFile("io-destination-", ".txt");

        try {
            Files.writeString(source, "Xin chào I/O\n", StandardCharsets.UTF_8);

            try (InputStream input = Files.newInputStream(source);
                 OutputStream output = Files.newOutputStream(destination)) {
                byte[] buffer = new byte[8192];
                int count;

                while ((count = input.read(buffer)) != -1) {
                    output.write(buffer, 0, count);
                }
            }

            System.out.print(Files.readString(destination, StandardCharsets.UTF_8));
            System.out.println("Cùng dữ liệu: " +
                    Arrays.equals(Files.readAllBytes(source),
                                  Files.readAllBytes(destination)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(destination);
        }
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac -encoding UTF-8 IoRolesDemo.java
java IoRolesDemo
```

Expected output when the program runs successfully:

```text
Xin chào I/O
Cùng dữ liệu: true
```

Reading the example by **source → data → destination**:

1. `Files.writeString` prepares the content in the **source file**. In this preparation step, `source` is the **destination of the write operation**.
2. `Files.newInputStream(source)` opens a stream **reading from the source file**; in the copy step, `source` plays the **source** role.
3. `input.read(buffer)` receives up to `buffer.length` bytes at a time; the `count` variable indicates the number of valid bytes. At this point, the data resides only temporarily in `buffer`.
4. `Files.newOutputStream(destination)` opens a stream writing to the **destination file**; `output.write(buffer, 0, count)` writes the bytes just read to it.
5. `Files.readString(destination, UTF_8)` reads **back the destination file** as text to print to standard output. At this point `destination` switches roles to become the **source of the verification step**, while `System.out` is the **destination of the print step**.
6. `Arrays.equals` compares the actual bytes in both files; `true` proves the byte contents are equal in this run. Closing the streams and deleting the temporary files makes the resource lifecycle explicit.

Key takeaway: **an I/O pipeline can consist of multiple steps; source and destination roles are determined separately for each step**. “Data” can transform between steps, though the byte-copying example above intentionally keeps it unchanged.

## 7. Short example: user input, program returns a result

`System.in` is the **source**; the input line decoded into a `String` is the **data**; `System.out` is the **destination**. The snippet below is a **method body**, which must be placed inside a Java method with `throws IOException` or exception handling and the corresponding imports.

```java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));

System.out.print("Nhập tên: ");
String name = reader.readLine();
System.out.println("Chào, " + name);
```

Required imports: `java.io.BufferedReader`, `java.io.InputStreamReader`, and `java.nio.charset.StandardCharsets`. If the user types `Lan` and presses Enter, the response line is `Chào, Lan`; the prompt and the text typed by the user should not be confused with the data read or output by the program. In this example, `System.in` is not closed because it is a standard stream that other parts of the program commonly continue to use.

If input has been redirected from a file, `reader.readLine()` still reads standard input. Similarly, standard output can be redirected to a file without modifying the `println` statement.

## 8. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| “Input is only keyboard entry; output is only printing to the screen.” | Files, networks, memory, and standard streams can all act as sources or destinations. |
| “Source/destination is a fixed property of an object.” | The role depends on the **operation**: a file can be a destination when written and a source when read back. |
| “A single `read` retrieves all the data.” | `read` can return fewer bytes than requested; you must loop until the end or until the desired length is reached. |
| “`read` returning `0` means the end of the stream.” | For `InputStream.read(byte[])` with a non-empty buffer, the end-of-stream indicator is **`-1`**. |
| “`write(buffer)` is always right after `read(buffer)`.” | You need to write only the valid portion: `write(buffer, 0, count)`. |
| “Text and bytes are the same.” | Text requires a charset when converting to/from bytes; UTF-8 helps control the result. |
| “Printing to `System.out` definitely displays on the screen.” | Standard streams can be redirected to a file or another recipient. |
| “Once writing is done, you can skip closing resources.” | Use `try-with-resources` for streams opened from files/sockets; resources are released according to their lifecycle. |
| “Successful output means the receiver has already used the data.” | Writing successfully to a stream does not prove a destination at another layer has processed it or that the data is durable. |

## 9. Self-check

**Scenario A:** A program reads `orders.csv`, calculates the total amount, and writes `total.txt`. Identify the components.

- Read step: **source** = `orders.csv`; **input data** = the bytes/characters representing the orders.
- Sum calculation step: processing data inside the program, not an I/O operation by itself.
- Write step: **destination** = `total.txt`; **output data** = the total amount after being converted into a representation for storage.

**Scenario B:** A program downloads data from the network and saves it to a file. Is the network connection a source or a destination?

- For the **receiving** data step: the connection (input stream) is the **source**, and the file being written is the **destination**.
- For the preceding **sending request** step: the connection (output stream) is instead the **destination**. The same connection can participate in both directions.

**Scenario C:** Why must UTF-8 be specified when writing and reading Vietnamese text?

- Because characters in a `String` must be **encoded** into bytes when writing and **decoded** from bytes when reading. Using the same charset prevents errors caused by different assumptions across environments.

### Remember

When facing any I/O task, ask: **Is the program reading or writing? What is the source? What is the destination? Is the data bytes or characters, and how is it represented and encoded?** Answering these four questions helps choose the appropriate Java API and pinpoint errors in the right place.