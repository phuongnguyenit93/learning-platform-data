# `InputStream.read()`: Byte Values 0–255 and EOF Marker `-1`

## 1. Return Value of `read()`

In Java I/O, `InputStream` reads data in **bytes**. The basic method is declared as:

```java
public abstract int read() throws IOException;
```

A call to `read()` has two kinds of results:

- **`0` to `255`:** a byte was read. The integer represents the **unsigned value** of the 8 bits in that byte.
- **`-1`:** **end of stream (EOF)**; there is no next byte provided by the stream according to the method's contract.

For example, reading the hex byte sequence `00 7F 80 FF`:

| Call | Actual byte | `read()` returns |
| --- | --- | ---: |
| 1 | `0x00` | `0` |
| 2 | `0x7F` | `127` |
| 3 | `0x80` | `128` |
| 4 | `0xFF` | `255` |
| 5 | No more bytes | `-1` |

**Do not confuse them:** `0` is a valid data byte; `255` is also a valid byte. Only `-1` signals EOF. The `-1` marker is **not** the `0xFF` byte stored in the stream and must not be processed as input data.

## 2. Why Read a Byte but Receive an `int`?

`byte` in Java is an 8-bit signed integer with the range **`-128..127`**. However, every byte read from a stream can carry any one of 256 bit patterns, conventionally represented as unsigned values from **`0..255`**.

If the return type were `byte`, a byte containing `11111111` (`0xFF`) would have the value `-1`, colliding with the EOF marker. Therefore, `InputStream.read()` uses `int`: 256 values reserved for data and one distinct value for the end of the stream.

| Bit pattern | Signed `byte` in Java | `int` returned by `read()` |
| --- | ---: | ---: |
| `0x00` | `0` | `0` |
| `0x7F` | `127` | `127` |
| `0x80` | `-128` | `128` |
| `0xFF` | `-1` | `255` |

Keep in mind:

- **Keep the result of `read()` in an `int` variable** until after checking for EOF.
- **Do not cast to `byte` and then compare with `-1`**, because `0xFF` data also turns into `(byte) -1`.
- When you already have a `byte b` and want to interpret it as an unsigned number, use `Byte.toUnsignedInt(b)` or `b & 0xFF`. For the `int` returned by `read()` in the range `0..255`, no conversion is needed.

## 3. Standalone Java 17+ Program

Create a file named **`ReadByteDemo.java`** with the following content:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadByteDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {0x00, 0x7F, (byte) 0x80, (byte) 0xFF};

        try (InputStream input = new ByteArrayInputStream(data)) {
            int value;
            while ((value = input.read()) != -1) {
                System.out.printf("%d -> 0x%02X%n", value, value);
            }

            System.out.println("Sau EOF: " + input.read());
        }
    }
}
```

Compile and run:

```bash
javac ReadByteDemo.java
java ReadByteDemo
```

**Exact** output:

```text
0 -> 0x00
127 -> 0x7F
128 -> 0x80
255 -> 0xFF
Sau EOF: -1
```

Explanation:

1. The array stores four bit patterns: `00`, `7F`, `80`, and `FF`. Casting with `(byte)` is needed for `0x80` and `0xFF` because those two int literals exceed the signed `byte` range.
2. `ByteArrayInputStream` provides the four bytes in order. Each `input.read()` returns an unsigned `int` in `0..255`, so `0x80` becomes `128` and `0xFF` becomes `255`.
3. `(value = input.read()) != -1` both assigns the new byte to `value` and stops **only at EOF**; it does not lose the `0x00` byte. Each iteration performs only one read.
4. `%02X` prints a two-digit hexadecimal number. This is only a display format; the actual data read is still binary bytes.
5. After four bytes, `ByteArrayInputStream` returns `-1`; with this specific class, subsequent calls after EOF continue to return `-1`. Do not treat the last line as a fifth byte.
6. `try-with-resources` closes the stream even if an exception occurs.

With `FileInputStream`, the `int` and `-1` loop condition still holds; when EOF occurs depends on the file length. The example array above makes the output deterministic without needing to prepare an external file.

## 4. Correct Loop Condition and Common Mistakes

Pattern for reading byte by byte:

```java
int value;
while ((value = input.read()) != -1) {
    // value is data in 0..255, process it here
}
```

This is an **illustrative snippet**, assuming `input` is an open `InputStream` and the enclosing code handles or declares `IOException`. The condition `>= 0` is also valid because the `read()` contract only produces `-1` or `0..255`; writing `!= -1` emphasizes the EOF meaning.

Incorrect ways to write it:

```java
// WRONG: stops when encountering the valid byte 0x00.
while ((value = input.read()) > 0) {
    // ...
}

// WRONG: 0xFF and EOF both turn into byte -1 after casting.
byte b = (byte) input.read();
if (b == -1) {
    // Cannot distinguish 0xFF from EOF.
}

// WRONG: using the value before checking.
int n = input.read();
// Must not treat n as a byte if n == -1.
```

If you need to store a byte into a `byte`, read into an `int`, check `n != -1`, and only then cast inside the success branch. When `n == 255`, `(byte)n` is `-1` under Java's signed representation, but **the data byte still exists**; EOF has already been checked beforehand.

## 5. EOF Is Not "No Data Yet" or an Error

`InputStream.read()` can **block**, depending on the stream type. If the next byte is not ready yet and EOF has not been reached, the call may wait for data, wait for the stream to end, or throw `IOException`. Distinguish among them:

- **`0..255`:** a byte was read, including a byte with value `0`.
- **`-1`:** the stream signals it has reached the end of input according to the `read()` contract.
- **Waiting:** no return value yet; you cannot infer EOF on your own.
- **`IOException`:** an I/O error occurred; you should not fake it as `-1` and silently swallow the error.

`input.available() == 0` **does not prove EOF**: `available()` only estimates the number of bytes that can be read without blocking. A socket, for instance, might temporarily have received no bytes yet while the peer continues sending data. EOF on a socket stream is typically tied to the peer closing its sending side; a read not receiving data immediately does not constitute an end-of-stream marker.

If the program needs to limit wait time or know the boundaries of individual messages, use a timeout mechanism or an appropriate format/protocol convention. `read()` itself and the `-1` marker only describe a stream of bytes and the end of the stream.

## 6. Distinguishing from `read(byte[])`

The return value **has different meanings** between the two styles of reading:

| Call | Return value |
| --- | --- |
| `input.read()` | **Byte value** `0..255` or `-1` at EOF |
| `input.read(buffer)` | **Number of bytes actually read** into the buffer or `-1` at EOF |
| `input.read(buffer, offset, length)` | **Number of bytes actually read** into the requested region; `0` if `length == 0`; `-1` if EOF occurs before any byte is read for a positive-length request |

When reading into an array, you must iterate from `buffer[0]` to `buffer[count - 1]`. Other slots may hold data from a previous read. A single `read(buffer)` call does not guarantee filling the entire array for all stream types.

Standalone Java 17+ example — create **`ReadBufferDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class ReadBufferDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = {(byte) 0xFF, 0x00, 0x2A};

        try (InputStream input = new ByteArrayInputStream(data)) {
            byte[] buffer = new byte[2];
            int count;

            while ((count = input.read(buffer)) != -1) {
                System.out.print("Đọc " + count + " byte:");
                for (int i = 0; i < count; i++) {
                    System.out.print(" " + Byte.toUnsignedInt(buffer[i]));
                }
                System.out.println();
            }
        }
    }
}
```

Compile and run:

```bash
javac ReadBufferDemo.java
java ReadBufferDemo
```

Output:

```text
Đọc 2 byte: 255 0
Đọc 1 byte: 42
```

The first time, `count == 2`; the buffer has the new data `255`, `0`. The next time, `count == 1`; only `buffer[0]` contains the new byte `42`, while `buffer[1]` retains the old value `0`. After that, EOF returns `-1`. The split of `2` bytes then `1` byte is guaranteed for the specific `ByteArrayInputStream` in this example; other streams may return fewer bytes than the buffer size in a single read.

When `length == 0`, `read(buffer, offset, length)` returns `0` without reading data. For a positive-length read request, the standard `InputStream` contract returns a positive byte count or `-1` at EOF. Therefore, **do not apply the EOF checking rule of `read()` to every return value from a method named "read" without checking the method signature**.

The utility methods `readNBytes` and `readAllBytes` have their own contracts regarding the amount of data read and memory allocation; they do not change the `0..255` and `-1` meaning of the no-argument `read()`.

## 7. Self-Check

Before finalizing a byte-reading loop, verify:

1. Does the variable receiving `read()` have type `int`?
2. Is `-1` checked **before** casting to `byte` or using it as data?
3. Are both `0x00` and `0xFF` bytes handled?
4. With a buffer, do you iterate only over the exact number of bytes actually read?
5. Is EOF distinguished from a waiting state and from `IOException`?
6. Is the stream closed when no longer needed, typically using `try-with-resources`?

**Mini exercise:** A stream contains exactly two bytes: `00 FF`. Three consecutive `read()` calls must return **`0`, `255`, `-1`**. If it stops at `0` or treats `255` as EOF, recheck your loop condition and type casting.

**Takeaway:** `InputStream.read()` returns `int` because it needs to hold all **256 unsigned byte values (`0..255`)** plus a **distinct EOF marker (`-1`)**. Always check for `-1` before processing the byte.