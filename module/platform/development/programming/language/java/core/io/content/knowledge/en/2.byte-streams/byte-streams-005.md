# Writing the Exact Number of Bytes Actually Read in Java Byte Streams

When copying data from an `InputStream` to an `OutputStream`, **write only the number of bytes that the `read` call just returned**. A buffer may contain many positions that have not been newly written, so writing the entire buffer after each read can result in extra or incorrect output data.

## 1. Key Takeaways

- `read(buffer)` returns **the number of bytes actually read in the current call**, not the size of the buffer.
- For a buffer with length greater than 0, the return value is normally a positive number from `1` to `buffer.length`; `-1` signals end of data (EOF). Do not interpret a short read as EOF.
- Use `output.write(buffer, 0, bytesRead)` to write the exact valid slice of the buffer, starting at position `0` and having length `bytesRead` bytes.
- Continue reading until `read` returns `-1`. Do not use `available()`, an expected byte count, or the buffer size as an end signal.

This rule applies to binary files, images, ZIP archives, network data, and even text when processing at the byte level.

## 2. Which Part of the Buffer Did `read` Modify?

For example, take an 8-byte buffer where the source has only the last 2 bytes remaining:

```text
buffer.length = 8

Previous read:  [A B C D E F G H]     -> bytesRead = 8
Last read:      [I J C D E F G H]     -> bytesRead = 2
                 ^ ^ |
          only 2 new bytes; C..H is old data in the buffer
```

The two valid new bytes are `I` and `J`. The remaining six positions **must not be written out**, even though they still contain characters from the previous read. After `read` returns `2`, calling `write(buffer)` will write all 8 bytes, turning 10 input bytes into 16 output bytes in this scenario.

Distinguish between these three quantities:

| Quantity | Meaning |
| --- | --- |
| `buffer.length` | Allocated buffer capacity |
| `bytesRead` | Number of valid bytes in the **current read** |
| `totalBytes` | Sum of positive `bytesRead` values written across the entire process |

`read(buffer)` may return fewer than `buffer.length` bytes even when the source has **not** ended. This can happen with network streams, devices, wrapped streams, or sources that limit the number of bytes per read.

## 3. Typical Mistake and How to Fix It

**Wrong: writing the entire buffer after each read.**

```java
byte[] buffer = new byte[8192];
int bytesRead;

while ((bytesRead = input.read(buffer)) != -1) {
    output.write(buffer);  // Wrong when bytesRead < buffer.length
}
```

`OutputStream.write(byte[])` writes the entire array; this method does not know how many bytes `read` just placed into the array. Stale data can be repeated at the end, corrupting the destination file, checksum, or protocol payload.

**Correct: writing only the slice just read.**

```java
byte[] buffer = new byte[8192];
int bytesRead;

while ((bytesRead = input.read(buffer)) != -1) {
    output.write(buffer, 0, bytesRead);
}
```

This is **an illustrative snippet inside a method that already has `input` and `output`**, not a standalone program. The parameters of `write(buffer, 0, bytesRead)` mean:

- `buffer`: the array containing the bytes just received.
- `0`: the starting position of the valid data.
- `bytesRead`: the number of bytes to write, taken directly from the `read` result.

If reading with `input.read(buffer, offset, length)`, the valid region just read starts at `offset`; in that case, the corresponding call is `output.write(buffer, offset, bytesRead)`. Do not assume the offset is always 0 in every program.

## 4. Runnable Java 17+ Program: Intentionally Producing Short Reads

A direct `ByteArrayInputStream` can usually return the full requested number of bytes. To verify that a single `read` call is **not required** to fill the buffer, this example wraps the source stream and intentionally limits each read to at most 3 bytes, while the buffer has length 8.

Save all of the following code to **`ReadActualBytesDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReadActualBytesDemo {

    public static void main(String[] args) throws IOException {
        byte[] original = "ABCDEFGHIJ".getBytes(StandardCharsets.UTF_8);

        try (InputStream input = new MaxChunkInputStream(
                 new ByteArrayInputStream(original), 3);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {

            long copied = copy(input, output);
            byte[] result = output.toByteArray();

            System.out.println("Total bytes: " + copied);
            System.out.println("Result: " +
                    new String(result, StandardCharsets.UTF_8));
            System.out.println("Same bytes: " +
                    Arrays.equals(original, result));
        }
    }

    static long copy(InputStream input, OutputStream output)
            throws IOException {
        byte[] buffer = new byte[8];
        long total = 0;
        int bytesRead;

        while ((bytesRead = input.read(buffer)) != -1) {
            output.write(buffer, 0, bytesRead);
            total += bytesRead;
            System.out.println("Read: " + bytesRead);
        }

        output.flush();
        return total;
    }

    static final class MaxChunkInputStream extends FilterInputStream {
        private final int maxChunk;

        MaxChunkInputStream(InputStream source, int maxChunk) {
            super(source);
            if (maxChunk <= 0) {
                throw new IllegalArgumentException("maxChunk must be > 0");
            }
            this.maxChunk = maxChunk;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            return super.read(b, off, Math.min(len, maxChunk));
        }
    }
}
```

Compile and run (the file name must match the `public class` name):

```bash
javac -encoding UTF-8 ReadActualBytesDemo.java
java ReadActualBytesDemo
```

**Exact stdout:**

```text
Read: 3
Read: 3
Read: 3
Read: 1
Total bytes: 10
Result: ABCDEFGHIJ
Same bytes: true
```

Loop-by-loop walkthrough:

1. The buffer has 8 positions, but the wrapper only allows reading the first `3` bytes (A–C); only 3 bytes are written.
2. The next two iterations read D–F and G–I respectively, writing exactly 3 bytes each time.
3. In the final iteration, only J remains, so `read` returns `1`; only byte J is written. The next call returns `-1`, ending the loop.
4. Total bytes written is `3 + 3 + 3 + 1 = 10`, equal to the source length. `Arrays.equals` proves that every byte of the output matches the input.

The data-limiting wrapper is only for testing the short-read scenario reproducibly. In practice, the number of bytes returned per read depends on the specific `InputStream`; the correctness of the loop does not depend on the buffer being filled.

## 5. Applying This to Copy Files

When working with files, open and close both streams with `try-with-resources`. For example, the following method can be placed inside a class along with its corresponding `import` statements:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static long copyFile(Path source, Path destination) throws IOException {
    try (InputStream input = Files.newInputStream(source);
         OutputStream output = Files.newOutputStream(destination)) {
        byte[] buffer = new byte[8192];
        long totalBytes = 0;
        int bytesRead;

        while ((bytesRead = input.read(buffer)) != -1) {
            output.write(buffer, 0, bytesRead);
            totalBytes += bytesRead;
        }

        return totalBytes;
    }
}
```

The snippet above is an **illustrative method**, not a standalone Java file: place the `import` statements at the top of the class file, then put `copyFile` inside the class. `Files.newOutputStream(destination)` with default options creates a new file or truncates an existing destination file; choose a destination path different from the source path and decide clearly on your overwrite policy before running.

Closing the `OutputStream` with `try-with-resources` releases resources and ensures the stream is closed even if an error occurs. When copying network data or binary data, do not convert individual byte chunks to a `String`: a UTF-8 character can span the boundary between two `read` calls, and arbitrary binary data is not text.

## 6. Important Boundaries and Distinctions

### EOF Is Not the Same as an Underfilled Buffer Read

The termination condition is `bytesRead == -1`. A value of `1`, `2`, or any positive number smaller than the buffer size **is still valid data**. Do not stop the loop after a short read, or subsequent data will be lost.

With a standard `InputStream`, when reading into a buffer of size greater than 0, the blocking `read(byte[])` method waits for bytes, EOF, or an error; `0` is a valid result when requesting length `0` via `read(b, off, 0)`. If you must integrate another adapter that could return `0` repeatedly, understand the adapter's contract and avoid an infinite CPU spin loop; the example above strictly follows the `InputStream` contract.

### A Single `write` Call and the Number of Bytes Written

`OutputStream.write(buffer, off, len)` is required to write all `len` bytes or report failure via an exception; it returns `void`, so there is no “number of bytes written” return value to add. In the loop above, `totalBytes` is incremented by `bytesRead` after the write call succeeds. Do not confuse this API with channel APIs that may return the number of bytes written, such as `WritableByteChannel.write`.

### When *Exactly N Bytes* Are Needed Instead of Reading Until EOF

If a protocol format requires reading a full `N` bytes (such as a fixed-length header), a single call to `read(buffer)` does not guarantee all `N` bytes. You can use `DataInputStream.readFully(buffer)` to read all bytes or throw `EOFException` if the source ends early; or use `InputStream.readNBytes(N)`, check the returned array length, and handle a shortfall. This is a different problem from copying an entire stream until EOF.

### Built-in Copy APIs Are Available

Since Java 9, `input.transferTo(output)` transfers all remaining bytes from an `InputStream` to an `OutputStream` and returns the total number of bytes transferred. This API is useful when you only need to copy, while writing the loop yourself helps clarify the rule of using the `read` result to determine the region of data to write.

## 7. Common Mistakes to Avoid

| Approach | Consequence | Correct Approach |
| --- | --- | --- |
| `output.write(buffer)` on every iteration | May write old bytes or bytes not belonging to new data | `output.write(buffer, 0, bytesRead)` |
| Assuming `read` always returns `buffer.length` | Fails with many stream types; lost or corrupted data | Use the actual `bytesRead` value |
| Exiting when `bytesRead < buffer.length` | Truncates data on a short read | Terminate only when `bytesRead == -1` |
| Using `while (input.available() > 0)` | `available()` only estimates non-blocking readable bytes, not EOF | Loop based on the `read` result |
| Calling `write(buffer, 0, buffer.length)` | Equivalent to writing the entire buffer even when fewer bytes were read | Pass `bytesRead` as the third argument |
| Treating the buffer as a character string | Can split characters in half or corrupt binary data | Keep bytes intact during copy operations |
| Forgetting to close file streams | Resource leaks, buffered data may be incomplete | Use `try-with-resources` |

## 8. Self-Check

1. A buffer has 8 bytes, and `read` returns `8`, `2`, then `-1`. What is the total number of bytes to write? **10 bytes**, split into two calls: `write(buffer, 0, 8)` and `write(buffer, 0, 2)`.
2. A `read` call returns `3` on an 8192-byte buffer: has the stream ended? **No**; continue calling `read`.
3. The output is larger than the input after copying an image file: what should you check first? **Check whether `write(buffer)` is called anywhere or `buffer.length` is mistakenly passed instead of `bytesRead`.**
4. To copy binary data and guarantee byte-for-byte accuracy, what should you verify with? **Compare bytes directly (e.g., `Arrays.equals` for small data) or compare checksum/hash and file size for large files.**

**Practical rule:** `read` determines *how many bytes are newly valid*; `write(buffer, offset, bytesRead)` must write only that exact number of bytes.