# BufferedReader and BufferedWriter in Java I/O

`BufferedReader` and `BufferedWriter` are two **buffered character stream** classes in the `java.io` package. They wrap another `Reader` or `Writer` to batch small operations into larger data exchanges, reducing the overhead of repeated calls down to the underlying source or destination. `BufferedReader` also provides `readLine()` for reading text line by line; `BufferedWriter` provides `newLine()` to write the line terminator appropriate for the runtime environment.

What matters is understanding that **the buffer belongs to the character stream**, **how lines are delimited**, **when to flush/close**, and what data can be altered if you read with `readLine()` and write with `newLine()`.

## 1. Learning Objectives

After this lesson, you will be able to:

- Describe how buffered character streams reduce I/O overhead and distinguish the internal buffer from a caller-allocated `char[]` array.
- Construct `BufferedReader` and `BufferedWriter` from a `Reader`/`Writer` or via `Files.newBufferedReader/newBufferedWriter` with an explicit charset.
- Use `readLine()`, `read(char[])`, `write(...)`, `append(...)`, `newLine()`, and `flush()` according to their contracts.
- Correctly handle `null` (EOF) and the empty string `""` (blank line), while understanding that a single `read` may return fewer characters than requested.
- Choose between line-by-line copying and character-block copying depending on whether line-ending characters must be preserved.
- Manage resource closing, memory limits, and common pitfalls when working with Unicode text.

## 2. Where Both Classes Sit in Java I/O

The two classes do not directly represent files or network connections: they are **wrappers (decorators)** that accept an existing character stream.

~~~text
Reading a file or byte source:
bytes from file/socket
    -> InputStream / underlying byte layer
    -> InputStreamReader (decodes bytes by charset)
    -> BufferedReader (character buffer, readLine)
    -> application

Writing a file or byte destination:
application
    -> BufferedWriter (character buffer, newLine)
    -> OutputStreamWriter (encodes characters by charset)
    -> OutputStream / underlying byte layer
    -> bytes to file/socket
~~~

With `Files.newBufferedReader(path, charset)` and `Files.newBufferedWriter(path, charset)`, Java assembles the required underlying chain for you; you do not have to wire each layer manually. For in-memory text, `StringReader` and `StringWriter` can stand in for the file/byte layers.

| Component | Data Unit | Primary Role |
| --- | --- | --- |
| `InputStream` / `OutputStream` | Byte | Read/write binary data |
| `InputStreamReader` / `OutputStreamWriter` | Byte ↔ character conversion | Decode/encode using a charset |
| `Reader` / `Writer` | Java character (UTF-16 `char`) | Abstract contract for reading/writing characters |
| `BufferedReader` | Character, line | Buffer for reading and `readLine()` |
| `BufferedWriter` | Character | Buffer for writing and `newLine()` |

**Note:** wrapping an `InputStream` directly with `BufferedReader` is a type mismatch: `BufferedReader`'s constructor takes a `Reader`. Similarly, `BufferedWriter` takes a `Writer`, not an `OutputStream`. If byte–character conversion is needed, add an `InputStreamReader` or `OutputStreamWriter` with an appropriate charset.

### Constructors

~~~java
BufferedReader reader = new BufferedReader(existingReader);
BufferedReader customReader = new BufferedReader(existingReader, 16 * 1024);

BufferedWriter writer = new BufferedWriter(existingWriter);
BufferedWriter customWriter = new BufferedWriter(existingWriter, 16 * 1024);
~~~

This is a **code fragment**: `existingReader` and `existingWriter` must be already declared variables. The value `16 * 1024` is the **number of characters** in the internal buffer, not bytes. The size-taking constructor requires `size > 0`; otherwise it throws `IllegalArgumentException`. The single-argument constructor picks an implementation-supplied default capacity; do not build correctness logic around a specific default buffer number.

## 3. `BufferedReader`: Reading Characters and Lines

`BufferedReader` extends `Reader`, so it can be used like any ordinary `Reader` while adding important utilities:

- `int read()`: reads a single `char` unit (non-negative integer value), or `-1` on EOF.
- `int read(char[] cbuf, int off, int len)`: reads up to `len` characters into the array starting at index `off`; returns the actual number of characters read, `-1` if the source is exhausted, or `0` when `len == 0`.
- `String readLine()`: reads one line; returns a string **without** the line-ending characters, or `null` when the end of data is reached with no more characters forming another line.
- `boolean ready()`: indicates whether the next read operation can proceed without blocking under the reported conditions; **not an EOF check**.
- `mark(int readAheadLimit)` and `reset()`: marks and returns to a previously read position within the allowed limit; not an arbitrary rewind of the entire source.
- `Stream<String> lines()`: creates a lazy stream of lines; the underlying resource still must be managed, and I/O errors during traversal may surface as `UncheckedIOException`.

### The Contract of `readLine()`

`readLine()` treats **LF** (`\n`), **CR** (`\r`), or **CRLF** (`\r\n`) as line boundaries. The terminator is not included in the returned `String`.

| Source Content | Values `readLine()` Returns in Sequence |
| --- | --- |
| `"red\nblue"` | `"red"`, `"blue"`, then `null` |
| `"red\r\nblue\n"` | `"red"`, `"blue"`, then `null` |
| `"\n"` | `""` (empty line), then `null` |
| `""` | `null` on the very first call |
| `"red\n\nblue"` | `"red"`, `""`, `"blue"`, then `null` |

Specifically:

- **`null`** indicates there are no more lines to read; **`""`** is a real line containing zero characters.
- The final line **does not need** to end with a newline to be returned.
- A trailing newline at the end of the source terminates the preceding line; it does not implicitly create an extra empty line after it.
- You cannot use `readLine()` to tell whether the preceding line ended with LF, CR, CRLF, or no terminator: that information has been stripped.

Standard loop:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    process(line);
}
~~~

This is a code fragment where `reader` is an already constructed `BufferedReader` and `process` is an application-specific operation. Do not write `while (!line.isEmpty())`, because a blank line **is not EOF**. Also do not use `reader.ready()` as the loop condition for reading all lines.

## 4. `BufferedWriter`: Writing Characters, Newlines, and Flushing the Buffer

`BufferedWriter` extends `Writer` and supports the following methods:

- `write(int c)`: writes a single `char` unit, the low-order 16 bits of `c`.
- `write(char[] cbuf, int off, int len)`: writes the exact requested slice of characters.
- `write(String s)` and `write(String s, int off, int len)`: writes a string or a substring slice.
- `append(CharSequence)`, `append(CharSequence, start, end)`, and `append(char)`: appends characters per the `Appendable` contract.
- `newLine()`: writes the line separator string defined by the environment.
- `flush()`: requests pushing characters currently held in the buffer down to the underlying `Writer`, and flushes that underlying object as well.
- `close()`: flushes remaining data and then closes the underlying writer; calling it multiple times is allowed per the `Writer` contract.

Example:

~~~java
writer.write("Xin chào");
writer.newLine();
writer.append("Java");
writer.flush();
~~~

This is a code fragment with an already declared `writer` variable. If you want to produce a text file without waiting for `close()` to push data to the next layer, you can call `flush()` at checkpoints where data needs to be observed. However, **flush does not mean data has been durably synced to hardware**; operating system and storage device buffers still exist.

### `newLine()` vs. the `'\n'` Character

`newLine()` uses the line separator defined by the runtime environment, typically corresponding to `System.lineSeparator()`. If a file format or protocol mandates an exact `LF` byte/character, write `'\n'` per that specification rather than relying on the OS newline.

Example of an LF-standardized file:

~~~java
writer.write("header");
writer.write('\n'); // Exact LF in the character stream
writer.write("value");
writer.write('\n');
~~~

Conversely, for text files intended for ordinary use on the current machine, `newLine()` may be more appropriate.

## 5. Runnable Java 17+ Program: Line-by-Line Reading and Buffered Writing

This example uses an in-memory source and destination so you can observe exactly how `readLine()` strips terminators, recognizes blank lines, and how `newLine()` produces new terminators.

Create **`BufferedTextDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;

public class BufferedTextDemo {
    public static void main(String[] args) throws IOException {
        String input = "alpha\r\n\r\nbeta\n";
        StringWriter result = new StringWriter();
        int lines = 0;

        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input), 4);
             BufferedWriter writer =
                     new BufferedWriter(result, 4)) {

            String line;
            while ((line = reader.readLine()) != null) {
                writer.write('[');
                writer.write(line);
                writer.write(']');
                writer.newLine();
                lines++;
            }
        }

        String visible = result.toString()
                .replace("\r\n", "\n")
                .replace('\r', '\n')
                .replace("\n", "\\n");

        System.out.println("lines=" + lines);
        System.out.println("content=" + visible);
    }
}
~~~

Compile and run:

~~~bash
javac BufferedTextDemo.java
java BufferedTextDemo
~~~

**Exact stdout, independent of Windows/Linux/macOS newlines because the printed output is normalized:**

~~~text
lines=3
content=[alpha]\n[]\n[beta]\n
~~~

Explanation:

1. The source has three lines: `alpha`, an empty line, and `beta`. The fourth `readLine()` call returns `null`, so the loop terminates.
2. An internal buffer capacity of 4 **does not limit** line length. `readLine()` can stitch multiple reads together to build a string longer than the buffer.
3. Each line is written with `[ ]` brackets followed by `newLine()`. `BufferedWriter` may hold data temporarily before passing it down to `StringWriter`.
4. `try-with-resources` closes `writer` and flushes any remaining characters. Reading `result.toString()` afterward is valid for `StringWriter`: this class still allows accessing its buffer via `toString()` after `close()`.
5. `replace("\r\n", "\n").replace('\r', '\n')` normalizes line endings for console presentation; it is only for demonstration and does not alter the original source.

Choosing buffer size 4 is only to make buffering clear; do not conclude that 4 is an optimal size. In production work, prefer the default size unless performance measurements prove a change is needed.

## 6. Program to Copy a UTF-8 File While Preserving Line Endings

When using the `readLine()` / `newLine()` pair, the source's line boundaries are rewritten in a new format. If the goal is to **copy the exact sequence of decoded characters**, including CR, LF, and CRLF as they appear, read into a `char[]` and write back the exact number of characters read.

Create **`BufferedFileCopy.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedFileCopy {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("Usage: java BufferedFileCopy <source> <target>");
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]);

        // Only use when source and target are two distinct files.
        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

            char[] buffer = new char[4096];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }
    }
}
~~~

Compile and run with an existing `source.txt` file:

~~~bash
javac BufferedFileCopy.java
java BufferedFileCopy source.txt copy.txt
~~~

The program **prints nothing to stdout** on success. The file `copy.txt` contains the source text read and rewritten in UTF-8; the sequence of `char` units, including CR and LF, is preserved. Because both input and output specify UTF-8, this is a **text** copy. It is **not a binary byte-copy tool** and does not promise the result will always match every byte of the source (for example, in the case of a BOM or data handled by the decoder/encoder according to charset policy).

### Notes on Usage

- `Files.newBufferedReader(source, UTF_8)` returns a `BufferedReader`. `Files.newBufferedWriter(target, UTF_8)` returns a `BufferedWriter`.
- When no `OpenOption` is passed, `newBufferedWriter` defaults to creating the file if absent, or overwriting by **truncating** an existing target file's content. Therefore, **you must ensure the two paths point to two different files**; if they refer to the same file (including aliases/hard links), the source file's content can be wiped. This is a safety limitation of the example.
- For output that needs to **append** to the end of a file, use the proper open options such as `StandardOpenOption.CREATE` and `StandardOpenOption.APPEND`; do not assume `BufferedWriter` decides to append on its own.
- `char[4096]` is an **application buffer**, distinct from the separate buffers inside `BufferedReader` and `BufferedWriter`.
- A single `reader.read(buffer)` **is not guaranteed to fill the array**. Only `buffer[0]` through `buffer[count - 1]` belong to that read; `writer.write(buffer, 0, count)` avoids writing stale characters from a previous iteration.
- For binary files or requirements to preserve every byte identically, use `Files.copy(...)` or byte streams. When you intentionally want to normalize line endings, you can choose `readLine()` and write an explicit terminator.
- `try-with-resources` ensures both streams are closed when the block exits, even if an error occurs. On a write error, the target file may already contain **partial data**; writing to a temporary file and moving it after success may suit workflows requiring atomicity/integrity.

## 7. Character Streams, Bytes, and Unicode: Choosing the Right Layer

`BufferedReader`/`BufferedWriter` operate on Java `char` units—that is, **UTF-16 code units**, not UTF-8 bytes and not necessarily matching Unicode code point counts. For example, an emoji outside the BMP takes **two** `char` units but is only one code point.

- When reading via `read(char[])`, a surrogate pair can be split across two consecutive reads. If you simply pass the character slices in order to a `Writer` within the same encoding pipeline, do not assume every chunk contains complete code points.
- Avoid constructing a `String` and processing Unicode by code points from arbitrary chunks if a chunk could split inside a surrogate pair.
- UTF-8 decoding belongs to `InputStreamReader` or the reading layer created by `Files.newBufferedReader`, **not** to `BufferedReader`'s buffering mechanism itself.
- If you use `new FileReader(path)` or `new FileWriter(path)` overloads that rely on the default charset, results may vary by environment/JDK. Prefer specifying `StandardCharsets.UTF_8` explicitly at the byte–text boundary so data keeps consistent meaning.

For example, with a socket:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

// Code fragment inside a method that has a socket variable of type Socket:
BufferedReader reader = new BufferedReader(
        new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8));
~~~

This is a **code fragment**, not a standalone program. `readLine()` waits until it receives a line terminator, EOF, or an error; if the peer keeps the socket open without sending a newline, the call can block. When designing a network protocol, define framing, maximum line length, and appropriate timeouts.

## 8. `flush()`, `close()`, and the Difference Between "Written" and "Reached the Destination"

Visualize it as:

~~~text
Application calls write("abc")
        |
        v
BufferedWriter [buffer holds "abc"]
        |
        | full or flush()/close()
        v
Underlying Writer -> encoder/file/socket -> OS/device
~~~

`BufferedWriter.write(...)` can often complete after writing only to its internal buffer, while `flush()` transfers pending data to the underlying writer. `close()` also flushes necessary data and then closes the underlying writer. `flush()` is not a promise of durable persistence to the device or confirmation that a peer has read the bytes over the network.

Standalone program demonstrating `flush` with an in-memory target, **`FlushDemo.java`**:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringWriter;

public class FlushDemo {
    public static void main(String[] args) throws IOException {
        StringWriter target = new StringWriter();

        try (BufferedWriter writer = new BufferedWriter(target, 8)) {
            writer.write("abc");
            writer.flush();
            System.out.println("afterFlush=" + target);
        }

        System.out.println("afterClose=" + target);
    }
}
~~~

Run:

~~~bash
javac FlushDemo.java
java FlushDemo
~~~

Output:

~~~text
afterFlush=abc
afterClose=abc
~~~

Buffer size 8 is larger than the string `abc`. After `flush()`, the data has reached `StringWriter` and is observable before closing. In file-writing applications, use `try-with-resources` and **avoid calling `flush` after every character/line** unless immediate output visibility is truly required, because constant flushing diminishes the batching benefit.

If passing a caller-owned `Writer` into a helper, the design must agree on **who is responsible for closing the destination**. Do not arbitrarily close the caller's writer just because the helper temporarily wrapped it in a `BufferedWriter`. Closing the wrapper normally closes the underlying destination as well.

## 9. `readLine()` vs. Block Reading with `char[]`

| Criterion | `readLine()` | `read(char[])` |
| --- | --- | --- |
| Unit received by app | One `String` line | Actual character count read into array |
| Source newlines | Stripped from string | Can preserve CR/LF |
| End condition | `null` on EOF | `-1` on EOF when a positive read was requested |
| Blank line | `""` | Line-agnostic unit |
| Memory bound | May have to accumulate an **entire line** in RAM | Bounded by program-chosen buffer |
| Suitable use cases | Config files, newline-delimited text records | Character copying, streaming processing, and separator preservation |

If a file contains abnormally long lines from untrusted data, **`readLine()` provides no maximum length parameter**. Checking `line.length()` after `readLine()` has finished can be too late to prevent large memory consumption. For untrusted protocols, use a character/chunk reader with an **accumulation limit**, a dedicated parser, or another framing mechanism.

If exact per-line separators must be preserved, `readLine()` is insufficient because it discards `\r`/`\n`/`\r\n` information. Read in blocks and handle separators with state tracking, or use an API that supports preservation if needed.

## 10. `ready()`, `mark()`, `reset()`, and `lines()`

### `ready()` Does Not Mean "More Data Remaining"

~~~java
if (reader.ready()) {
    int ch = reader.read();
}
~~~

This snippet only checks whether a read can proceed **without blocking** at that instant; it does not determine how many lines/characters remain, nor does it detect EOF. A socket source that has no immediate bytes available yet has not ended can report not ready; you must not infer "finished" from that. File reading loops should rely on the `-1` or `null` return value of the actual read operation.

### `mark()/reset()`: Peeking Ahead and Re-reading Within Limits

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class MarkResetDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("ABCDE"))) {
            reader.mark(3);
            System.out.println((char) reader.read());
            System.out.println((char) reader.read());
            reader.reset();
            System.out.println((char) reader.read());
        }
    }
}
~~~

Run:

~~~bash
javac MarkResetDemo.java
java MarkResetDemo
~~~

Stdout:

~~~text
A
B
A
~~~

`mark(3)` sets the limit of characters to retain for `reset()`. If you read well past `readAheadLimit`, resetting is no longer guaranteed; `reset()` may throw `IOException`. Do not use `mark` as a mechanism for rewinding an entire file of arbitrary size.

### `lines()` Is a Lazy Stream

~~~java
try (BufferedReader reader = java.nio.file.Files.newBufferedReader(
        java.nio.file.Path.of("source.txt"),
        java.nio.charset.StandardCharsets.UTF_8)) {
    reader.lines().filter(line -> !line.isBlank()).forEach(System.out::println);
}
~~~

This snippet is runnable **when placed inside a method that declares handling `IOException`**, such as `main(String[] args) throws IOException`, with `source.txt` existing. `lines()` does not eagerly read everything upfront. Traverse the stream **while the reader is still open**; closing the stream does not replace the responsibility of closing `BufferedReader`. Do not interleave `readLine()` calls on the reader with consuming `lines()` before completion, because both consume from the same read position. I/O errors occurring during traversal can surface as `UncheckedIOException`.

## 11. Common Mistakes

**Mistake 1 — Treating an empty line as end of data.**

~~~java
// Wrong: stops early when a blank line appears.
while (!(line = reader.readLine()).isEmpty()) {
    // ...
}
~~~

The snippet above can also throw `NullPointerException` when `readLine()` returns `null`. The right approach is to compare against `null`, and then decide per business logic whether to process or skip empty lines.

**Mistake 2 — Forgetting `flush()` or `close()`.**  
If you only write a few characters into the buffer and the program stops using the writer without closing/flushing, the data may remain in RAM and never reach the underlying writer. Use `try-with-resources` for owned resources; call `flush()` when immediate output is genuinely needed.

**Mistake 3 — Assuming one `read(char[])` fills the array.**

~~~java
// Wrong: count may be less than buffer.length.
char[] buffer = new char[1024];
int count = reader.read(buffer);
if (count != -1) {
    writer.write(buffer); // Writes unread characters/stale values as well.
}
~~~

The right call is `writer.write(buffer, 0, count)`. The buffer is capacity; `count` is the number of valid characters.

**Mistake 4 — Assuming `readLine()/newLine()` preserves source content identically.**  
Line-based reading strips line terminators, and `newLine()` writes an environment-chosen separator. Only use this when **normalizing** line endings and adding a trailing newline is acceptable; to preserve the exact character sequence, use `read(char[])`/`write(char[],off,len)`.

**Mistake 5 — Choosing the wrong level of abstraction.**  
Do not use character buffers to copy ZIPs, images, compressed data, or binary payloads. Use byte streams or `Files.copy` for bytes. Also do not create a `BufferedReader` to query total file length: there is no such contract.

**Mistake 6 — Assuming buffering cures every performance problem.**  
Buffering reduces many small calls to the lower layer, but it does not eliminate network latency, CPU-heavy parsing, or charset encoding cost. An overly large buffer wastes memory; an overly small buffer can increase interaction counts. Choose based on measurements and workload.

**Mistake 7 — Using the same file for source and destination when copying.**  
If the destination is truncated on open, it can destroy data before reading finishes. Verify source and destination differ; if safe overwriting is a critical requirement, use a temporary file and an appropriate replacement step.

**Mistake 8 — Leaving network protocols without line limits.**  
`readLine()` can block while no newline/EOF arrives and can consume huge amounts of RAM on a single long line. For external data, specify framing, maximum length, timeouts, charset, and error policy.

## 12. Practice Checklist

- [ ] Is the data **text** with an explicitly defined charset, such as `UTF-8`?
- [ ] Are you using `BufferedReader`/`BufferedWriter` on the proper `Reader`/`Writer` layer?
- [ ] Does the `readLine()` loop check for `null`, not confusing it with `""`?
- [ ] When reading into `char[]`, are you writing only the **`count`** characters just received?
- [ ] Are you intentionally preserving or normalizing CR/LF/CRLF?
- [ ] Have you accounted for very long lines and streams that may block?
- [ ] Do `flush()` and `close()` match resource ownership, using `try-with-resources` where appropriate?
- [ ] Are you avoiding using `ready()` to infer EOF and not treating buffer size as a guaranteed read count?
- [ ] When writing files, have you accounted for create/truncate/append behavior and avoided overwriting the source?

### Self-Check Questions

**1.** `readLine()` returns `""`. Is the source exhausted?  
**Answer:** Cannot conclude that. That is a valid empty line; only `null` indicates no more lines remain.

**2.** The internal buffer holds 8192 characters, but a line is 100,000 characters long. What will `readLine()` return?  
**Answer:** It can return the entire 100,000-character string (assuming a valid line and sufficient data and memory), because it stitches across multiple reads; the buffer does not cap line length.

**3.** Why can `readLine()` followed by `newLine()` fail to preserve a file character-for-character?  
**Answer:** `readLine()` removes CR/LF/CRLF markers and `newLine()` writes a new environment-dependent separator, and may also add a terminator to the final line.

**4.** When should `flush()` be called?  
**Answer:** When data needs to be pushed down to the underlying writer before closing, such as a response that must be sent immediately. When using `try-with-resources` on a file closed after writing finishes, `close()` already includes flushing the buffer.

**5.** Is the buffer made of characters or bytes?  
**Answer:** The buffers of these two classes hold **characters**; when paired with a byte-backed file, the encoding/decoding layer underneath converts between Java's UTF-16 `char`s and bytes according to the charset.

**Takeaway:** `BufferedReader` makes reading text and lines convenient; `BufferedWriter` batches write operations and supports line breaks. **Buffering only improves how characters are transported**; the application still must handle EOF, actual read counts, charsets, line boundaries, flushing, and resource ownership.