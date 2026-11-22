# `Reader` EOF and the Actual Number of Characters Read in Java

When reading text with `java.io.Reader`, two rules determine correctness:

1. **EOF (end of file/end of stream)** is indicated by `-1` from the `read(...)` methods, meaning the character stream has ended.
2. **The number of characters read can be smaller than the destination buffer size.** The `int n` value returned by `read(...)` is the actual number of `char` units received, so only process the `n` new elements in the buffer.

**A short read is not EOF.** Even when the array is large enough, a single read may receive less data than requested, so you need to loop until `-1` when you want to read to completion. On the other hand, Java's `char` is a **UTF-16 code unit**; counting `char` values is not always the same as counting Unicode code points, user-perceived characters, or bytes.

## 1. What is `Reader` and what does each method return?

`Reader` is the API for reading **character** streams; `InputStream` reads **byte** streams. Common implementations:

- `StringReader`: reads data already in a `String`.
- `InputStreamReader`: decodes bytes from an `InputStream` using a `Charset` such as UTF-8.
- `BufferedReader`: adds buffering and supports `readLine()`.
- `Files.newBufferedReader(path, StandardCharsets.UTF_8)`: opens a text file with an explicitly specified charset.

| Method | Success value | End of stream | Meaning |
| --- | --- | --- | --- |
| `int read()` | One UTF-16 unit in the range `0..65535` | `-1` | Does not return `char` directly, reserving negative values to indicate EOF. |
| `int read(char[] dst)` | Number of new `char` units written, up to `dst.length` | `-1` when a positive read is requested and data is exhausted | Can be smaller than the array size. |
| `int read(char[] dst, int off, int len)` | Number of `char` units written into `dst` starting at index `off` | `-1` when a positive request is made and EOF is reached | `off` is the position in the array, **not the offset in the file**. |
| `int read(CharBuffer target)` | Number of new `char` units added to `target` | `-1` when a positive request is made and EOF is reached | Limited by `target.remaining()`. |
| `String readLine()` of `BufferedReader` | Line content, which can be `""` | `null` | Line terminators are stripped from the result. |

`Reader.read(...)` and `BufferedReader.readLine()` **do not share the same EOF signal**: the first group returns `int` with `-1`; `readLine()` returns `null`.

## 2. `Reader.read()` EOF must be checked while the result is still an `int`

`Reader.read()` returns `-1` when data is exhausted, whereas non-negative values from `0` to `65535` can all represent a `char` unit. Casting to `char` too early loses the ability to distinguish EOF.

Wrong (illustrative snippet, assuming `reader` already exists):

```java
char ch = (char) reader.read();
if (ch == -1) {
    // Cannot detect EOF because it has already been cast.
}
```

When casting `-1` to `char`, the result becomes `0xFFFF`. The right approach is to keep `int` until after checking:

```java
int value;
while ((value = reader.read()) != -1) {
    char ch = (char) value;
    // At this point, ch is guaranteed to be data that was read.
}
```

The following standalone Java 17+ program shows that the value `0xFFFF` is distinct from EOF:

```java
// ReaderEofDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderEofDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader =
                     new StringReader("A" + (char) 0xFFFF)) {
            System.out.println(reader.read());
            System.out.println(reader.read());
            System.out.println(reader.read());
        }
    }
}
```

```bash
javac ReaderEofDemo.java
java ReaderEofDemo
```

Output:

```text
65
65535
-1
```

`65` represents `A`; `65535` is the `char` value `0xFFFF`; `-1` is EOF. The value `0` can also be the content of a NUL character, **not meaning EOF** when calling the zero-argument `read()`.

### EOF is different from “no data received yet”

A `Reader` can read from a file, memory, socket, or interactive source. With a source such as a socket, a blocking `read` call may **wait** for data to arrive or for the sending side to finish. No bytes having arrived at that moment does not mean EOF. If the reader has a buffer, buffered data is still returned before EOF appears.

`Reader.ready()` **is not an EOF check**: `false` is not enough to conclude data is exhausted, while `true` refers to readiness to read according to the implementation's contract. Closing a reader with `close()` is also different from EOF; reading after closing usually throws `IOException`, not the standard way to receive `-1`.

## 3. `read(char[])`: `n` is the number of characters just written, not the buffer capacity

When calling `int n = reader.read(buffer)`:

- `n > 0`: `n` new UTF-16 units have been copied into `buffer[0]` through `buffer[n - 1]`.
- `n == -1`: EOF has been reached if the call requested a positive read.
- `n == 0`: can happen with a zero-length read request (see the next section); must not be used in place of EOF.

Example of an array of length 4 reading a string of length 5:

```java
// ReaderChunkDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderChunkDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("ABCDE")) {
            char[] buffer = new char[4];
            int n;

            while ((n = reader.read(buffer)) != -1) {
                System.out.println("n=" + n
                        + ", chunk=" + new String(buffer, 0, n));
            }
            System.out.println("next=" + reader.read(buffer));
        }
    }
}
```

```bash
javac ReaderChunkDemo.java
java ReaderChunkDemo
```

Output:

```text
n=4, chunk=ABCD
n=1, chunk=E
next=-1
```

On the second call, only the character `E` is new. The remainder of the array may still hold `BCD` from the previous read. Therefore `new String(buffer)` or `System.out.print(buffer)` will unintentionally print **stale data**. Use `new String(buffer, 0, n)` or `writer.write(buffer, 0, n)` to process only the newly received portion.

**Do not conclude EOF from a short read:** a single read returning 2 out of 4096 characters only tells you two characters were returned on that call. Subsequent calls can still receive more. When reading the entire stream, the termination condition is `-1`, not `n < buffer.length`.

Example of copying characters in chunks, assuming `reader` and `writer` are both already open:

```java
char[] buffer = new char[8192];
int n;
long total = 0;

while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
    writer.write(buffer, 0, n);
    total += n;
}
```

This is an **illustrative snippet**, not a standalone class. `writer.write` takes the `n` count just read, and `total` adds the actual number of `char` units. Adding `buffer.length` would make the total wrong on short reads.

### `off`, `len`, and the zero-length case

`read(dst, off, len)` requests at most `len` `char` units to be written into the array `dst`, starting at index `off`. With `off=3`, `len=4`, `n=2`, only elements `dst[3]` and `dst[4]` were just updated. `off` must not be understood as a position in the file.

A request with `len == 0` (when `off` is valid) returns `0` without consuming characters. You can receive `0` **even when the reader is at EOF**. Deterministic example with `StringReader`:

```java
// ReaderZeroLengthDemo.java
import java.io.Reader;
import java.io.StringReader;

public class ReaderZeroLengthDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("K")) {
            char[] buffer = new char[3];
            System.out.println("empty=" + reader.read(buffer, 0, 0));
            System.out.println("first=" + reader.read(buffer, 0, 3));
            System.out.println("eof=" + reader.read(buffer, 0, 3));
            System.out.println("emptyAfterEof=" + reader.read(buffer, 0, 0));
        }
    }
}
```

```bash
javac ReaderZeroLengthDemo.java
java ReaderZeroLengthDemo
```

Output:

```text
empty=0
first=1
eof=-1
emptyAfterEof=0
```

Similarly, `read(CharBuffer)` with a buffer that has no `remaining()` left does not request additional characters. If `off` or `len` is negative or the write range extends beyond the array, the arguments are invalid and may throw `IndexOutOfBoundsException`.

## 4. Reading exactly N characters requires looping until enough are read or early EOF occurs

A single `read(dst, off, len)` **does not guarantee** getting all `len` characters; this is especially important when a protocol or file structure specifies the number of characters to receive. To get exactly N UTF-16 units, accumulate `n`, and report an error if `-1` appears before enough are read.

Standalone Java 17+ example:

```java
// ReaderExactDemo.java
import java.io.EOFException;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class ReaderExactDemo {
    static String readExactly(Reader reader, int expected)
            throws IOException {
        if (expected < 0) {
            throw new IllegalArgumentException("expected must be >= 0");
        }

        char[] result = new char[expected];
        int filled = 0;

        while (filled < expected) {
            int n = reader.read(result, filled, expected - filled);

            if (n == -1) {
                throw new EOFException(
                        "expected=" + expected + ", actual=" + filled);
            }
            if (n == 0) {
                throw new IOException("Reader made no progress");
            }
            filled += n;
        }

        return new String(result);
    }

    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("ABC")) {
            System.out.println(readExactly(reader, 2));
            try {
                System.out.println(readExactly(reader, 2));
            } catch (EOFException ex) {
                System.out.println(ex.getMessage());
            }
        }
    }
}
```

```bash
javac ReaderExactDemo.java
java ReaderExactDemo
```

Output:

```text
AB
expected=2, actual=1
```

The first call reads all of `AB`. The next call gets `C` and then EOF, so the error clearly states only 1 of 2 characters was read. The `n == 0` branch avoids a busy loop if a custom `Reader` returns 0 on a positive read request without making progress; for implementations following the standard contract, reading with `len > 0` returns a positive number or `-1`. The `expected == 0` case returns `""` without reading; this must not be treated as an EOF signal.

If you only want to process **the entire stream**, you do not need `readExactly`: use a loop reading until `-1` and process each newly received chunk.

## 5. `char` count from `Reader` differs from byte count and Unicode code point count

Each Java `char` is **one 16-bit UTF-16 code unit**. Unicode code points outside the BMP (such as emojis) use **two** code units (a surrogate pair). Distinguish between:

- **Byte:** depends on how characters are encoded into bytes, such as UTF-8.
- **`char` / UTF-16 code unit:** the unit that `Reader.read` returns and `String.length()` counts.
- **Unicode code point:** may require one or two UTF-16 code units.
- **Grapheme cluster:** a character as perceived by a user; may consist of multiple code points, such as a letter with combining diacritics.

The string `"A😀B"` is an example: three code points, four `char` values, six UTF-8 bytes. Standalone example using `InputStreamReader` to decode UTF-8 and sum from the actual `n` value:

```java
// ReaderCharCountDemo.java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class ReaderCharCountDemo {
    public static void main(String[] args) throws Exception {
        String original = "A😀B";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        StringBuilder decoded = new StringBuilder();
        int actualChars = 0;

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(utf8),
                StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int n;

            while ((n = reader.read(buffer)) != -1) {
                decoded.append(buffer, 0, n);
                actualChars += n;
            }
        }

        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("readChars=" + actualChars);
        System.out.println("codePoints="
                + decoded.codePointCount(0, decoded.length()));
        System.out.println("roundTrip=" + original.contentEquals(decoded));
    }
}
```

```bash
javac -encoding UTF-8 ReaderCharCountDemo.java
java ReaderCharCountDemo
```

Output:

```text
utf8Bytes=6
readChars=4
codePoints=3
roundTrip=true
```

The code does not assume fixed chunking. When processing text in chunks, note that **a surrogate pair can fall on the boundary between two chunks**. If you need to process Unicode code points or re-encode individual chunks separately, you must maintain state so a pair is not split improperly. The example above assembles the complete text into a `StringBuilder` before counting code points.

`InputStreamReader` works through a **byte → char decoder**. One UTF-8 byte does not necessarily produce one `char`; the reader can read ahead multiple bytes into a buffer. Therefore, do not infer byte counts from `Reader`'s `read`, and do not infer reader EOF solely from how many bytes were fetched at the lower layer.

## 6. `BufferedReader.readLine()`: `null` is EOF, `""` is still a line

`BufferedReader.readLine()` returns the content of a line, stripping the delimiter `\n`, `\r`, or `\r\n`. An empty line is represented by `""` (a zero-length string). Only when there are no more lines to read does the method return `null`.

```java
// ReaderLinesDemo.java
import java.io.BufferedReader;
import java.io.StringReader;

public class ReaderLinesDemo {
    public static void main(String[] args) throws Exception {
        try (BufferedReader reader = new BufferedReader(
                new StringReader("alpha\n\nomega"))) {
            String line;
            int lineNumber = 0;

            while ((line = reader.readLine()) != null) {
                System.out.println(++lineNumber + ": <" + line + ">");
            }
            System.out.println("eof=" + (reader.readLine() == null));
        }
    }
}
```

```bash
javac ReaderLinesDemo.java
java ReaderLinesDemo
```

Output:

```text
1: <alpha>
2: <>
3: <omega>
eof=true
```

The second line is a **valid empty line**; do not skip it mistaking it for EOF. The `"alpha\n"` case returns `"alpha"` then `null`: the newline terminates the existing line without automatically creating a second empty line. The `"\n"` case returns `""` then `null`.

If you need to preserve line endings in the data, `readLine()` is unsuitable because it removes the delimiters; read `char` chunks or record line breaks in your own format.

## 7. Example with UTF-8 files and total actual character count

The standalone program below creates two temporary files, copies text via `Reader`/`Writer`, counts the exact `n` from each read, closes resources, and then compares the data:

```java
// ReaderFileDemo.java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReaderFileDemo {
    public static void main(String[] args) throws Exception {
        Path source = Files.createTempFile("reader-src-", ".txt");
        Path target = Files.createTempFile("reader-dst-", ".txt");

        try {
            Files.writeString(source, "Xin chào\nJava IO\n",
                    StandardCharsets.UTF_8);

            long copiedChars = 0;
            try (Reader reader = Files.newBufferedReader(
                         source, StandardCharsets.UTF_8);
                 Writer writer = Files.newBufferedWriter(
                         target, StandardCharsets.UTF_8)) {
                char[] buffer = new char[5];
                int n;

                while ((n = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, n);
                    copiedChars += n;
                }
            }

            System.out.println("copiedChars=" + copiedChars);
            System.out.println("sameText=" + Files.readString(
                    source, StandardCharsets.UTF_8).equals(
                    Files.readString(target, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
        }
    }
}
```

```bash
javac -encoding UTF-8 ReaderFileDemo.java
java ReaderFileDemo
```

Output:

```text
copiedChars=17
sameText=true
```

`"Xin chào\n"` consists of 9 UTF-16 code units, `"Java IO\n"` consists of 8; the total is **17 `char`s**. The buffer array has only 5 slots, yet the final result does not depend on how `Reader` splits the reads. `try-with-resources` ensures the writer is closed before reading the target file back, so all data has been flushed and written.

For large files, reading in chunks like this avoids loading the entire file into a single `String` in RAM. Since Java 10, there is also `Reader.transferTo(Writer)`, which copies until EOF and returns the total number of `char`s transferred, though it does not automatically close the reader or writer.

## 8. Common misconceptions and mistakes

| Mistake | Why it is wrong | How to fix it |
| --- | --- | --- |
| Casting `reader.read()` to `char` before comparing with `-1` | The EOF sentinel is lost upon casting | Check the `int` result first. |
| Calling `read(buffer)` and processing the entire `buffer` | Unwritten elements may still contain stale data | Only process `buffer[0..n)` when `n > 0`. |
| Treating `n < buffer.length` as EOF | A short read does not necessarily mean end of source | Loop until `-1`. |
| Adding `buffer.length` to the character count read | Counts regions without new data | Add the exact `n`. |
| Calling `read` only once to get N characters | May retrieve fewer than N | Loop and accumulate; handle early EOF. |
| Using `len == 0` to probe for EOF | Returns `0` even when the source is at EOF | Read with a positive request to receive `-1`. |
| Treating `readLine().isEmpty()` as the end | Empty lines differ from `null`, and EOF causes NPE | Check `line != null`. |
| Using `ready()` to probe for EOF | Readiness does not equal end of source | Read and inspect the return value. |
| Treating `char` count as byte or code point count | Unicode/charsets may use multiple units | Clearly identify the unit being counted. |
| Failing to close `Reader` | Leaks file descriptors/resources | Use `try-with-resources`. |

### Self-check

1. `char[] b = new char[100]`; `reader.read(b)` returns `7`. **Only the first seven characters of the array are new data**, not all 100.
2. A read into an array of length 100 returns `7`. Is the next read guaranteed to be `-1`? **No.** A short read does not prove EOF.
3. `readLine()` returns `""`. Has EOF been reached? **You cannot conclude that:** this is an empty line; EOF is represented by `null`.
4. `read(array, 5, 2)` returns `1`. Where is the new character located? In **`array[5]`**, not at position 5 in the file.
5. Can `read(array, 0, 0)` return `0` even at EOF? **Yes**, because no additional characters were requested.
6. How many UTF-8 bytes, `char`s, and code points does `"A😀B"` have? **6 bytes, 4 `char`s, 3 code points**.

**Core rule:** With `Reader.read(...)`, **`-1` is EOF; a non-negative value is the actual number of `char` units read** (returning 0 when a zero-length read is requested). With `BufferedReader.readLine()`, **`null` is EOF; the empty string `""` is still a valid line**. Always use the return value of the current read call itself to decide which slice of data gets processed.
