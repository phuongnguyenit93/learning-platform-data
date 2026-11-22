# Readable, Appendable, and API Composability in Java

In Java I/O, many **character**-processing APIs can be composed together without depending on a specific source or destination class. Two key interfaces for this design are `java.lang.Readable` (a source supplying characters) and `java.lang.Appendable` (a destination receiving appended characters). They are **minimal contracts**: one side knows how to read into a `CharBuffer`, and the other side knows how to append character content.

What is worth learning is not just memorizing method names, but how to write shared components that work across `StringReader`, `BufferedReader`, `CharBuffer`, `StringBuilder`, `Writer`, and more without rewriting the algorithm for each type.

## 1. Objectives

After this article, you can:

- Distinguish `Readable`, `Reader`, `Appendable`, `Writer`, and `CharSequence` by their exact roles.
- Explain the `read(CharBuffer)` and `append(...)` contracts, return values, and the possibility of throwing `IOException`.
- Connect a character source with a character destination by declaring parameters using interfaces.
- Use `CharBuffer` properly through the steps **write → flip → consume → clear**.
- Know when you additionally need `Closeable`, `Flushable`, a charset, data limits, or an I/O waiting mechanism.
- Recognize common mistakes: reading once and assuming it is enough, forgetting `flip()`, forgetting EOF, overusing `toString()`, or closing unowned resources.

## 2. Two Minimal Interfaces

### `Readable`: A Character Source

The `java.lang.Readable` contract has one main method:

~~~java
int read(java.nio.CharBuffer cb) throws java.io.IOException;
~~~

The method reads characters into `cb` starting at the `CharBuffer`'s **current position**; the position advances by the number of characters added. Return values:

- The number of characters actually placed into the buffer (may be **less than** the initial `cb.remaining()`).
- `-1` if **end of stream (EOF)** has been reached.
- `0` in certain cases where no characters were read, for example when the buffer has no remaining space or the source makes no progress right now. How to react to `0` depends on the source; never spin the CPU in an infinite loop.

`Readable` does not define `close()`, `mark()`, `reset()`, `ready()`, or byte-to-character conversion. Those capabilities, where present, belong to other types or API layers.

Implementation examples: `java.io.Reader` is an abstract class implementing `Readable`; `StringReader` and `BufferedReader` are concrete `Reader` types. `java.nio.CharBuffer` also implements `Readable`, so a character region can serve as a read source for APIs expecting this interface.

### `Appendable`: A Character-Appending Destination

`java.lang.Appendable` provides three overloads:

~~~java
Appendable append(CharSequence csq) throws java.io.IOException;
Appendable append(CharSequence csq, int start, int end)
        throws java.io.IOException;
Appendable append(char c) throws java.io.IOException;
~~~

These operations append characters to the destination and return `Appendable` so calls can be chained:

~~~java
sink.append("Hello").append(' ').append("Java");
~~~

`CharSequence` describes a sequence of **characters**, which can be represented by `String`, `StringBuilder`, `CharBuffer`, or another implementing type. In `append(csq, start, end)`, `start` is **inclusive**, `end` is **exclusive**, and indices are measured in **UTF-16 `char` units**, not Unicode code points.

By the `Appendable` contract, passing `null` as the `CharSequence` appends the four-character string `"null"`. That does not replace input validation when `null` is supposed to carry a different meaning.

Implementation examples: `StringBuilder`, `StringBuffer`, `java.io.Writer`, and `java.nio.CharBuffer`. `Appendable` does not promise data has reached disk, does not declare `flush()` or `close()` on the interface itself, and does not guarantee multi-threaded synchronization.

### Comparison Table

| Type | Role | Capabilities Beyond the Minimal Contract |
| --- | --- | --- |
| `Readable` | Reads characters into a `CharBuffer` | Guarantees only `read(CharBuffer)` |
| `Reader` | Java I/O character source | `read(char[])`, `close()`, and many utilities; is a `Readable` |
| `Appendable` | Receives characters via `append` | No mandatory `flush`/`close` |
| `Writer` | Java I/O character destination | `write(...)`, `flush()`, `close()`; is an `Appendable` |
| `CharSequence` | Represents an index-readable character sequence | `length()`, `charAt()`, `subSequence()`; not synonymous with an I/O source |
| `CharBuffer` | NIO character buffer with `position/limit` | Can act as `Readable`, `Appendable`, and `CharSequence` |

**Do not equate** `Readable` with `Reader`: an object can be a `Readable` without being a `Reader`; likewise, an `Appendable` is not necessarily a `Writer`. If a method only reads or appends, declaring minimal parameter types usually makes it more broadly reusable.

## 3. Composing APIs: Interchangeable Inputs and Outputs

You can write an algorithm that only knows:

~~~text
Readable (character source)
        |
        | read(CharBuffer)
        v
CharBuffer [written into free slots]
        |
        | flip() => exposes only the newly read characters
        v
Appendable (character-appending destination)
~~~

For instance, the exact same logic can read from a `StringReader` into a `StringBuilder` during testing, and then read from a `BufferedReader` into a `BufferedWriter` when processing files. The intermediary algorithm does not need to know whether the source lives in RAM or on disk.

However, this is **character-contract composition**. For raw bytes, use `InputStream`/`OutputStream` or byte channels. If data travels through files or sockets as bytes yet needs text processing, you must choose a charset to convert at the boundary via `InputStreamReader` and `OutputStreamWriter`.

## 4. Runnable Example: Copying Characters from `Readable` to `Appendable`

Create the file **`ReadableAppendableDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.nio.CharBuffer;

public class ReadableAppendableDemo {
    public static long copy(Readable source, Appendable destination)
            throws IOException {
        CharBuffer buffer = CharBuffer.allocate(4);
        long total = 0;

        while (true) {
            int count = source.read(buffer);

            if (count == -1) {
                break;
            }
            if (count == 0) {
                // Policy of this illustrative helper: require the source to make progress.
                // Non-blocking sources need a separate readiness-waiting mechanism.
                throw new IOException("Source made no progress");
            }

            buffer.flip();
            destination.append(buffer);
            total += count;
            buffer.clear();
        }

        return total;
    }

    public static void main(String[] args) throws IOException {
        StringBuilder result = new StringBuilder();

        try (StringReader source = new StringReader("Hello, Java!")) {
            long copied = copy(source, result);
            System.out.println("characters=" + copied);
        }

        System.out.println("text=" + result);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac ReadableAppendableDemo.java
java ReadableAppendableDemo
~~~

**Exact stdout:**

~~~text
characters=12
text=Hello, Java!
~~~

**Why it works:**

1. `StringReader` is a `Reader`, so it works as a `Readable`. `StringBuilder` implements `Appendable`.
2. `CharBuffer.allocate(4)` has a capacity of 4 characters; the 12-character string is processed across multiple passes. Each `read` returns the **actual number of characters received**, not a guarantee of reading all four.
3. `read` writes starting at `buffer.position()` and advances `position`; `flip()` switches to readable mode, sets `limit` to the written position, and resets `position` to 0.
4. `destination.append(buffer)` receives `CharBuffer` as a `CharSequence`; at this point the visible sequence consists solely of the newly read characters.
5. `clear()` resets `position=0` and `limit=capacity` for writing on the next pass. **`clear()` does not physically erase old characters**; they simply no longer belong to the valid data slice of the next pass.
6. When `read` returns `-1`, the helper terminates and returns the total number of **`char` units** copied. This number does not necessarily equal the UTF-8 byte count or Unicode code point count.

This snippet intentionally throws `IOException` when `read` returns `0` to avoid a non-progressing loop. **This is a limiting policy of the illustrative helper**, suitable for blocking sources that make progress such as `StringReader`. A general `Readable` may return `0`; for non-blocking sources you must integrate a readiness notification mechanism, cancellation/timeout, or proper retry rules—neither treating `0` as EOF nor spinning endlessly.

### What If You Forget `flip()`?

~~~java
CharBuffer buffer = CharBuffer.allocate(4);
int count = source.read(buffer);

// Wrong: buffer is still in write mode; position has advanced,
// remaining() may be 0 or contain unwritten slots.
destination.append(buffer);
~~~

If the array was filled, `position == limit` makes the visible `CharSequence` empty. If only part was read, the remaining region is actually the **unwritten** slots. You must call `flip()` before passing read data to the destination. Do not convert a `CharBuffer` to a `String` before checking its `position` and `limit`.

An alternative design could use a `char[]` array with `Reader.read(char[])` and `Writer.write(char[], 0, count)`, but that would require concrete **`Reader/Writer`** types, making it less general than the `Readable/Appendable` helper above.

## 5. Standard Library Composition Example: `Scanner` and `Formatter`

`java.util.Scanner` accepts a `Readable` as its token-parsing source; `java.util.Formatter` can accept an `Appendable` as its formatting destination. This allows you to connect parsers and formatters to different sources/destinations without forcing each one to be a file.

Create the file **`ScannerFormatterDemo.java`**:

~~~java
import java.io.StringReader;
import java.util.Formatter;
import java.util.Locale;
import java.util.Scanner;

public class ScannerFormatterDemo {
    public static void main(String[] args) {
        StringBuilder result = new StringBuilder();

        try (Scanner scanner = new Scanner(new StringReader("8 13"));
             Formatter formatter = new Formatter(result, Locale.ROOT)) {
            int a = scanner.nextInt();
            int b = scanner.nextInt();

            formatter.format("a=%d, b=%d, sum=%d", a, b, a + b);
        }

        System.out.println(result);
    }
}
~~~

Run:

~~~bash
javac ScannerFormatterDemo.java
java ScannerFormatterDemo
~~~

Stdout:

~~~text
a=8, b=13, sum=21
~~~

`Scanner` consumes a source implementing `Readable`; `Formatter` writes through a destination implementing `Appendable`. In the example above the destination is `StringBuilder`, so there is no disk-I/O `IOException`. If you pass a `Writer` as the destination to `Formatter`, note that `Formatter` can record I/O errors and expose them via `formatter.ioException()`; calling `format` does not replace output error checking.

**Resource lifecycle:** `Scanner.close()` closes its source if that source implements `Closeable`; `Formatter.close()` closes its destination if that destination implements `Closeable`. In the example, `StringBuilder` does not need closing. When a source or destination is **passed in** from outside into a utility, do not close it unilaterally unless the resource ownership contract grants that authority to the utility.

## 6. Designing Composable Methods from Small Building Blocks

Suppose the task is to write a greeting and name to multiple kinds of destinations. Declare parameter types according to the capability actually required:

~~~java
import java.io.IOException;

public final class GreetingWriter {
    private GreetingWriter() {}

    public static void writeGreeting(
            Appendable destination, CharSequence name) throws IOException {
        destination.append("Xin chào, ")
                   .append(name)
                   .append('!');
    }
}
~~~

This class compiles, though it **has no `main`**; it is meant to be called from another program. It works with `StringBuilder`, `StringBuffer`, or `Writer`. The return type of `append` calls is allowed to be **covariant**: an implementing class like `StringBuilder` can return `StringBuilder` instead of `Appendable` while still honoring the interface.

Similarly, declare `Readable` for an API that only needs to receive a character stream:

~~~java
static int firstCharacter(Readable source) throws IOException {
    java.nio.CharBuffer one = java.nio.CharBuffer.allocate(1);

    while (true) {
        int read = source.read(one);
        if (read == -1) {
            return -1; // End of data, no first character.
        }
        if (read > 0) {
            one.flip();
            return one.get();
        }
        throw new IOException("Source made no progress");
    }
}
~~~

This snippet needs to live inside a Java class with the appropriate `import java.io.*`. This also reflects a **fail-on-no-progress** policy, not advice that every `Readable` source should fail whenever it temporarily returns `0`.

**Selection guideline:** declare `Appendable` when you only need to append characters; use `Writer` when `write(char[])`, `flush()`, or `close()` are part of the operation's contract; use `Readable` when you only need `read(CharBuffer)`; use `Reader` when you need `read(char[])`, `read()`, `close()`, or `Reader`-specific methods. Do not force callers to turn every source into a `String` via `toString()`: large files or infinite streams cannot be handled effectively that way.

## 7. `append`, `CharSequence`, and Easily Confused Boundaries

### `append(csq, start, end)` Is Not an Automatic `substring`

~~~java
StringBuilder builder = new StringBuilder();
builder.append("012345", 1, 4);
System.out.println(builder); // 123
~~~

Start index **1** is inclusive; end index **4** is exclusive. If `start < 0`, `end > csq.length()`, or `start > end`, the operation can throw `IndexOutOfBoundsException` per the contract. Indices are in `char` (UTF-16) units: do not arbitrarily split a surrogate pair in half if you want to preserve a Unicode code point.

### `append` Only Promises to Accept Additional Characters

- The interface does not require an append operation to be **atomic**. If the I/O destination fails partway through, data may already be partially written.
- The interface does not promise thread safety. `StringBuilder` is unsynchronized; `StringBuffer` synchronizes individual operations, which still does not turn multiple consecutive appends into a single atomic transaction.
- The interface does not promise `flush()`; if the destination is a `BufferedWriter`, you must decide when to flush/close based on **the destination's owner**, not the `Appendable` type.
- The interface does not promise that one `append` equals one message or one line. Network/file protocols must define framing/formatting explicitly.

### A `CharSequence` May Mutate While in Use

`String` is immutable, whereas `StringBuilder` or `CharBuffer` has mutable state and bounds. Avoid modifying a source while another append operation is reading from it; the `Appendable` contract does not promise to take a snapshot of every `CharSequence` at every instant.

## 8. Bridging with Byte Streams Using the Right Charset

`Readable` and `Appendable` operate on Java characters (`char`/UTF-16). To read/write file or network data in byte form, an explicit conversion layer is required:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileBridge {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("source.txt");
        Path target = Path.of("target.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
            ReadableAppendableDemo.copy(reader, writer);
        }
    }
}
~~~

This example requires **`ReadableAppendableDemo.java`** from section 4 in the same directory to compile, and `source.txt` must exist before running. Compile both classes:

~~~bash
javac ReadableAppendableDemo.java TextFileBridge.java
java TextFileBridge
~~~

The result is **`target.txt`** receiving text from `source.txt` in UTF-8; the program prints nothing to stdout. `Files.newBufferedReader/newBufferedWriter` specify the charset explicitly; `try-with-resources` closes both source and destination to flush the destination on success or exception. In real applications, clearly define overwrite/creation behavior for the target file and safety requirements before running.

**Unicode caveat:** `Readable.read(CharBuffer)` counts **UTF-16 code units**, not UTF-8 bytes or user-perceived characters. A character outside the BMP can occupy two `char`s (a surrogate pair). Appending the entire sequence of `char`s in order into a compatible `Writer` lets the encoder handle pairs properly, whereas encoding incomplete chunks independently can easily split a character in half and corrupt data. When counting code points is required, use dedicated code-point APIs after understanding text boundaries.

## 9. When Should You Use Which Interface?

| Requirement | Recommended Input/Output Type | Reason |
| --- | --- | --- |
| Only need to consume characters into a buffer | `Readable` | The API accepts a wider range of sources |
| Need to read into character arrays or process line by line | `Reader` / `BufferedReader` | Provides convenient read operations |
| Only need to append characters | `Appendable` | Works with `StringBuilder` or `Writer` |
| Need to write char arrays, flush, or close | `Writer` | Expresses full I/O capabilities |
| Need to format data to multiple kinds of sinks | `Formatter(Appendable)` | Relies on the append contract |
| Need to parse tokens from diverse sources | `Scanner(Readable)` | Relies on the character-reading contract |
| Copy binary files, images, ZIPs | `InputStream` / `OutputStream` or byte channels | Avoids conversion through `char` |
| Need to process large content | Streaming with buffers | Avoids holding all content in RAM |

Do not choose `Readable` solely because the name sounds more general. If your problem needs protocol-level EOF detection, random access, exact byte counts, backpressure, or open/close lifecycle management, design those capabilities explicitly instead of assuming these two small interfaces provide them.

## 10. Common Mistakes and How to Fix Them

**Mistake 1 — Assuming one `read` fills the buffer.**  
Wrong: ignoring the returned character count and treating all of `buffer.capacity()` as valid data.  
Right: use the position/limit after `read`, call `flip()` before handing the buffer to the destination, then call `clear()`.

**Mistake 2 — Treating `0` as EOF or spinning in a loop whenever `0` is returned.**  
Wrong: `if (count == 0) break;` for any `Readable`, or `while (count == 0) read(...)` without a wait mechanism.  
Right: `-1` is EOF; `0` must be handled according to source semantics, especially for non-blocking sources. For utilities that only support sources making progress, throwing an explicit error as in the example is appropriate.

**Mistake 3 — Calling `append(buffer)` before `flip()`.**  
Wrong: the buffer is still in write mode, so the exposed `CharSequence` is not the newly read data.  
Right: switch the buffer to read mode before appending.

**Mistake 4 — Assuming `Appendable` also has `flush()` and `close()`.**  
Wrong: casting directly to `Writer` or closing a resource passed in by the caller.  
Right: use only the methods of the requested contract; require `Writer` or specific capabilities when the problem truly needs them, and define who owns closing.

**Mistake 5 — Converting a byte stream to text without specifying a charset.**  
Wrong: decoding with an unintended default charset, or treating each byte chunk as an independent string.  
Right: specify the charset, wrap the byte source/destination in `Reader`/`Writer`, and preserve decoder/encoder state.

**Mistake 6 — Assuming every `CharSequence` is an immutable `String`.**  
Wrong: assuming data cannot change while `StringBuilder` or `CharBuffer` is still being modified.  
Right: establish clear ownership/mutability rules; capture `toString()` when a snapshot is truly needed and the data is small enough.

## 11. Self-Check Questions

**1.** A method only needs to append text to an arbitrary destination; should the parameter be `Writer` or `Appendable`?  
**Answer:** `Appendable` is sufficient if it only calls `append`, allowing the method to accept `StringBuilder`, `Writer`, and other compatible types.

**2.** After `read(CharBuffer)`, why can't you append the buffer immediately?  
**Answer:** Its position is still in write mode; you must call `flip()` so `position=0` and `limit` points to the end of the newly read region.

**3.** Does `Readable` require `close()`?  
**Answer:** No. Some concrete classes like `Reader` support `close()`, but `Readable` itself does not require it.

**4.** What bounds does `append(CharSequence, 2, 5)` use?  
**Answer:** It takes indices 2, 3, and 4; `end=5` is exclusive, measured in UTF-16 `char` units.

**5.** How do `Scanner` and `Formatter` relate to these two interfaces?  
**Answer:** `Scanner` can take a `Readable` as its source; `Formatter` can write to an `Appendable`. They illustrate how standard library APIs compose via minimal contracts.

**Key takeaway:** `Readable` defines **how characters are received from a source**, and `Appendable` defines **how characters are added to a destination**. `CharBuffer` bridges both worlds through `read → flip → append → clear`. Their strength lies in source/destination interchangeability, provided you still explicitly manage actual character counts read, buffer state, encoding, and resource lifecycles.
