# `InputStream.nullInputStream()`, `OutputStream.nullOutputStream()` and Use Cases

## Objectives

In Java I/O, sometimes a program needs a byte source that **actively has no data** or a write destination that **actively discards every byte it receives**. Java provides two built-in factory methods:

- `InputStream.nullInputStream()`: creates an empty `InputStream` that is at EOF from the start.
- `OutputStream.nullOutputStream()`: creates an `OutputStream` that accepts write operations but **discards** the bytes, without storing or forwarding them to a file, memory, or network.

Both APIs appeared in **Java 11** and can be used directly in Java 17+. This lesson distinguishes them from a Java `null` reference, explains their behavior when opening/closing the stream, provides runnable examples, and points out when to use or not use them.

## 1. “Null stream” does not mean a variable equal to `null`

The two declarations below are completely different:

```java
InputStream missing = null;                    // No object exists.
InputStream empty = InputStream.nullInputStream(); // A valid InputStream object exists.
```

Calling `missing.read()` will cause a `NullPointerException`. With `empty`, the `read()` method exhibits the normal behavior of a source that has reached the end of data: returning `-1` (while the stream is still open).

Similarly:

```java
OutputStream missing = null;
OutputStream discard = OutputStream.nullOutputStream();
```

`missing.write(65)` causes a `NullPointerException`; `discard.write(65)` is accepted while the stream is open, but the byte `65` is not stored anywhere.

The name “null” here describes an **empty source** or a **destination that discards data**, not a null reference. The two factory methods return real objects that properly implement the contract of `InputStream` and `OutputStream`.

## 2. `InputStream.nullInputStream()`: an empty byte stream, immediate EOF

API signature:

```java
public static InputStream nullInputStream()
```

When **not yet closed**, this stream contains no bytes:

| Operation | Meaningful Result |
| --- | --- |
| `read()` | Returns `-1` (EOF). |
| `read(byte[])` or `read(byte[], off, len)` | For a read request with a positive length: EOF, typically represented by `-1`; a 0-byte read request returns `0`. |
| `available()` | Returns `0`. |
| `readAllBytes()` | Returns an empty byte array. |
| `readNBytes(n)` | No bytes to read; the result is an empty array when `n >= 0`. |
| `skip(n)` | Skips no bytes: returns `0` for `n > 0`. |
| `transferTo(out)` | Transfers no bytes: returns `0`, provided the destination argument is valid. |
| `markSupported()` | Returns `false`; `mark()` has no effect, `reset()` throws `IOException`. |

**EOF is not an error.** When not yet closed, a result of `read() == -1` means the source has run out of data according to the stream reading contract. It does not mean “waiting on the network” or “no data received yet”. Another `InputStream` might return `available() == 0` while still not at EOF; `nullInputStream()` specifically and intentionally represents that data has ended.

### Full example: empty source

Create the file **`NullInputDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;

public class NullInputDemo {
    public static void main(String[] args) throws IOException {
        try (InputStream in = InputStream.nullInputStream()) {
            System.out.println("available = " + in.available());
            System.out.println("read = " + in.read());
            System.out.println("bytes = " + in.readAllBytes().length);
            System.out.println("skip = " + in.skip(10));
            System.out.println("mark supported = " + in.markSupported());
        }
    }
}
```

Compile and run:

```bash
javac NullInputDemo.java
java NullInputDemo
```

Exact output:

```text
available = 0
read = -1
bytes = 0
skip = 0
mark supported = false
```

In this program, `available() == 0` accompanies EOF because the **specific source type** is `nullInputStream()`. Do not generalize that to sockets, pipes, or every type of `InputStream`.

## 3. `OutputStream.nullOutputStream()`: accepts writes without retaining bytes

API signature:

```java
public static OutputStream nullOutputStream()
```

When **not yet closed**, `write(int)`, `write(byte[])`, and `write(byte[], off, len)` operations produce no output. Bytes sent in are discarded. `flush()` has no work to do, because there is no buffered data to push out to a file or device.

### Full example: writes succeed without producing stored output

Create the file **`NullOutputDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class NullOutputDemo {
    public static void main(String[] args) throws IOException {
        try (OutputStream out = OutputStream.nullOutputStream()) {
            byte[] message = "Hello, Java".getBytes(StandardCharsets.UTF_8);
            out.write(message);
            out.write('!');
            out.flush();
            System.out.println("write operations completed");
        }
        System.out.println("no payload was stored");
    }
}
```

Compile and run:

```bash
javac NullOutputDemo.java
java NullOutputDemo
```

Exact output:

```text
write operations completed
no payload was stored
```

`System.out.println(...)` still appears on the console because that code writes directly to `System.out`. Only the bytes sent to the `out` object from `nullOutputStream()` are discarded.

**Performance note:** writing to this destination performs no actual storage I/O. However, any work *before writing* (generating data, encoding, compressing, computing, reading the source) can still consume time and memory. Therefore, “no output” does not mean the entire pipeline is free.

## 4. What happens after closing the stream?

Both factory methods return **open** streams. `close()` puts them into the closed state; calling `close()` again has no effect.

- **`InputStream.nullInputStream()`:** after closing, I/O methods such as `read()`, `available()`, `readAllBytes()`, `skip()`, and `transferTo()` throw `IOException`. The `-1` result only describes an empty stream **while still open**. `reset()` also throws `IOException`; `markSupported()` still does not support marking.
- **`OutputStream.nullOutputStream()`:** after closing, `write(...)` operations throw `IOException`. According to this factory's specification, `flush()` remains a no-op, even when there is no data to flush; you should not rely on `flush()` to verify that the stream is still open.
- **`try-with-resources`:** the standard way to ensure `close()` is called at the right time, especially when the same function might receive a real stream instead of a null stream.

### Verifying exceptions after closing

Create the file **`ClosedNullStreamsDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class ClosedNullStreamsDemo {
    public static void main(String[] args) throws IOException {
        InputStream in = InputStream.nullInputStream();
        in.close();
        in.close(); // Closing again is still valid.

        try {
            in.read();
        } catch (IOException e) {
            System.out.println("closed input: IOException");
        }

        OutputStream out = OutputStream.nullOutputStream();
        out.close();
        out.close(); // Closing again is still valid.

        try {
            out.write(42);
        } catch (IOException e) {
            System.out.println("closed output: IOException");
        }
    }
}
```

Run:

```bash
javac ClosedNullStreamsDemo.java
java ClosedNullStreamsDemo
```

Output:

```text
closed input: IOException
closed output: IOException
```

Distinguish **“empty”** from **“closed”**: an open empty stream still handles a read operation validly with EOF; a closed stream no longer allows reading/writing like that.

## 5. Practical use cases

### Case A: an optional `InputStream` parameter, wanting to represent “no data”

An API that accepts an `InputStream` does not necessarily need data in every case. When the business logic **truly allows an empty input**, you can replace `null` with an empty stream so the processing algorithm stays uniform:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class OptionalInputDemo {
    static String readText(InputStream in) throws IOException {
        return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        try (InputStream empty = InputStream.nullInputStream()) {
            String text = readText(empty);
            System.out.println("text length = " + text.length());
        }
    }
}
```

Run `javac OptionalInputDemo.java` then `java OptionalInputDemo`:

```text
text length = 0
```

This approach fits when “no content” is a valid business value, such as an optional body in a data processing flow. **Do not silently replace missing required data with `nullInputStream()`**, as that will hide errors and mislead the application into thinking it read a valid empty input.

### Case B: running a full pipeline while intentionally discarding output

When you need to test *reading, decoding, compressing, or transferring data* without wanting to create an output file, you can connect the pipeline to `OutputStream.nullOutputStream()`.

Create the file **`DiscardTransferDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class DiscardTransferDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "Java I/O".getBytes(StandardCharsets.UTF_8);

        try (InputStream source = new ByteArrayInputStream(payload);
             OutputStream sink = OutputStream.nullOutputStream()) {
            long consumed = source.transferTo(sink);
            System.out.println("bytes consumed = " + consumed);
            System.out.println("next read = " + source.read());
        }
    }
}
```

Run:

```bash
javac DiscardTransferDemo.java
java DiscardTransferDemo
```

Output:

```text
bytes consumed = 8
next read = -1
```

**Explanation:** `InputStream.transferTo(out)` reads from the source until EOF, writes the read bytes to `out`, and returns the number of bytes transferred. Here eight bytes passed through the pipeline so the source was consumed; the sink discarded them. `consumed == 8` **does not prove that eight bytes were saved to disk**.

Using this approach to test data reading logic or measure part of the processing cost is reasonable, but the measurement does not reflect the real cost of file writing or network transmission.

### Case C: a test suite needs an empty source or a sink that discards results

- Pass `InputStream.nullInputStream()` into a parse function to test the empty-file case and see whether the function returns an empty result or reports a missing-data format error.
- Pass `OutputStream.nullOutputStream()` into a report export function when the test only verifies the processing flow, record count, number of bytes transferred, or exception behavior.
- When you need to **assert the exact written byte contents**, you must use `ByteArrayOutputStream` or a readable destination. A discarding sink does not support assertions on the payload.

Example of designing a function that allows passing the output from outside:

```java
static void exportBytes(byte[] payload, java.io.OutputStream out)
        throws java.io.IOException {
    out.write(payload);
}
```

This is a **method illustration snippet**, not a standalone runnable program. Callers can pass `OutputStream.nullOutputStream()` when intentionally discarding output, or `ByteArrayOutputStream` when needing to retain data for verification.

### Case D: providing a well-defined default implementation for an optional branch

Suppose a component has `boolean shouldPersist`: only when `shouldPersist` is true does it need to write to a file. You can choose the output conditionally:

```java
// Illustrative snippet, assuming the target variable of type Path and shouldPersist already exist.
try (OutputStream out = shouldPersist
        ? java.nio.file.Files.newOutputStream(target)
        : OutputStream.nullOutputStream()) {
    produceReport(out);
}
```

`produceReport(OutputStream)` is an application method and has not been defined in the snippet. When the save-to-file branch is chosen, path handling, write permissions, and I/O errors must be handled properly. If output is a mandatory requirement, choosing `nullOutputStream()` when opening the file fails is **not** the right way to handle it: the error should be reported to the caller.

## 6. Comparison with common alternatives

| Option | Bytes to read/write? | Retains data? | Appropriate when |
| --- | --- | --- | --- |
| `InputStream.nullInputStream()` | Reading always returns EOF | No source data | Wanting to represent a valid empty input. |
| `new ByteArrayInputStream(new byte[0])` | Reading always returns EOF | Already has an empty byte array | Needing an array-backed source, extensible with real byte data. |
| `OutputStream.nullOutputStream()` | Accepts writes while open then discards bytes | No | Wanting to consume results without storing them. |
| `ByteArrayOutputStream` | Accepts writes | Yes, in RAM | Inspecting, transforming, or collecting payload to read again. |
| `Files.newOutputStream(path)` | Accepts writes to a file | Yes, on the filesystem when successful | Needing to save results to a file. |

These types may share an interface, yet possess different semantics. Therefore, choose them based on the **intent to retain or discard data**, not merely because they all compile.

## 7. Pitfalls and limitations

1. **Do not use an empty stream to legitimize missing data.** If the contract requires a real file or a mandatory payload, reject missing input instead of silently returning an empty result.
2. **Do not interpret the name `nullOutputStream` as “never fails”.** Writing to a closed stream will throw `IOException`; steps *before writing* can still throw their own exceptions.
3. **Do not expect the sink to store or replay content.** Bytes written to `nullOutputStream()` cannot be recovered; to inspect content you must use a storing sink.
4. **Do not confuse the number of bytes processed with bytes stored.** The byte count from `transferTo` measures the amount of data transferred through the call, even when the destination discards the data.
5. **Do not confuse `available() == 0` of null input with the general EOF rule.** For a network stream, `available() == 0` might only mean temporarily having no bytes ready. The general EOF rule remains checking the result of the `read()` operation.
6. **Do not use a null sink to benchmark file/network throughput.** Removing the storage/transmission step makes the measurement differ from real-world scenarios; clearly state which part of the pipeline you are measuring.
7. **Distinguish stream ownership.** A function receiving an `InputStream` from outside should generally not call `close()` on its own if the contract gives ownership to the caller; for internally created streams, `try-with-resources` is a reasonable default.
8. **Pay attention to size and processing limits.** Discarding the result does not limit the amount of source data that must be read; with large or user-submitted sources, you still need resource limits/timeouts appropriate for the source type.

## 8. Self-check questions

**1. Is `InputStream.nullInputStream()` equivalent to declaring `InputStream in = null`?**

No. It is a valid stream object. When not yet closed, `in.read()` returns `-1` instead of causing a `NullPointerException`.

**2. Does successfully writing 1 MiB to `OutputStream.nullOutputStream()` mean a 1 MiB file is created?**

No. The data has been discarded. No file and no buffer storing content are created by this factory.

**3. After calling `close()` on a null input stream, does `read()` return `-1` or throw an exception?**

Throws `IOException`. The value `-1` is the EOF of an **open** null input.

**4. Why can't `InputStream.nullInputStream()` replace validating required input data?**

Because an empty stream is always valid from an I/O standpoint and can cause processing logic to mistake missing data for an “empty file” in business terms. If data must exist, an explicit error should be reported.

**5. When should you use `ByteArrayOutputStream` instead of `OutputStream.nullOutputStream()`?**

When you need to read back, compare, or assert the written content. `nullOutputStream()` is only appropriate when intentionally discarding content.

## 9. Reference documentation

- Java 17 API: [`InputStream.nullInputStream()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#nullInputStream()).
- Java 17 API: [`OutputStream.nullOutputStream()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#nullOutputStream()).

**Key takeaway:** `nullInputStream()` is *a valid but empty input*; `nullOutputStream()` is *a valid output that intentionally discards bytes*. Both APIs help express clear intent in optional branches and in testing. They do not replace required data, real write mechanisms, or I/O error handling.