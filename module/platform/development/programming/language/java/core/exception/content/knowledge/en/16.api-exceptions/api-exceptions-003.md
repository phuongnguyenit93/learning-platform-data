# EOFException and Handling Premature End of Data in Java

> **Java Core – Exception** · Group: **API Exceptions** · Focus: distinguishing normal stream termination from data truncated mid-structure/record, reading the exact number of required bytes, and preserving errors when processing files or binary streams. Complete example compatible with **Java 17+**.

## 1. Understanding EOF and EOFException Correctly

**EOF** stands for *end of file*, or more broadly, **reaching the end of an input data source**. A source can be a file, memory, a socket, or a stream wrapped by another API.

`java.io.EOFException` is a **checked exception** that extends `IOException`. It is typically thrown by APIs that read structured data when **the remaining bytes are insufficient to complete the requested read operation**.

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.io.IOException
        └── java.io.EOFException
~~~

The most common misconception is that **“reaching the end of a stream” is not always an exception**.

~~~java
InputStream in = new ByteArrayInputStream(new byte[] {65});
System.out.println(in.read()); // 65
System.out.println(in.read()); // -1: EOF reached, does not throw EOFException.
~~~

This is an illustrative snippet requiring `InputStream` and `ByteArrayInputStream` imports, and can be placed inside a method that declares/handles `IOException`. With `InputStream.read()`, **`-1` is the value indicating EOF**, while an actual byte is returned as an integer in the range 0–255.

In contrast:

~~~java
DataInputStream in =
        new DataInputStream(new ByteArrayInputStream(new byte[] {1, 2}));
int value = in.readInt(); // EOFException: readInt requires 4 bytes.
~~~

This is an illustrative snippet requiring `DataInputStream` and `ByteArrayInputStream` imports and `IOException` handling. `readInt()` requires **a full four bytes** to construct an `int` value. Because the source only has two bytes, ending early **violates the requirement of the read operation itself**.

**Rule of thumb:** If the API is asking “is there another byte?”, EOF may be signaled with `-1` or another sentinel. If the API is requesting **a complete value/record with a defined size**, running out of data **midway** must usually be an error and may appear as an `EOFException`.

## 2. Distinguishing APIs That Signal End of Data Differently

Do not assume that all methods named `read` share the same EOF contract.

| API | When reaching end of data | Practical meaning |
| --- | --- | --- |
| `InputStream.read()` | Returns `-1` | No next single byte |
| `InputStream.read(byte[])` | May return `-1`; before EOF may return fewer bytes than buffer size | A single read is not guaranteed to fill the buffer |
| `Reader.read()` | Returns `-1` | No next character |
| `BufferedReader.readLine()` | Returns `null` if no more lines remain | A final line without a newline character is still returned normally |
| `DataInputStream.readInt()` | Throws `EOFException` if fewer than 4 bytes remain | Requires a complete binary `int` value |
| `DataInputStream.readUnsignedByte()` | Throws `EOFException` if no byte remains | Requires exactly 1 byte |
| `DataInputStream.readFully(byte[])` | Throws `EOFException` if unable to read the full array length | Requires filling the entire buffer |
| `DataInputStream.readUTF()` | May throw `EOFException` if UTF data in this format is truncated | Requires length header and full content |
| `Scanner.nextInt()` | May throw `NoSuchElementException` when no matching token remains | Token parsing API, does not use `EOFException` as a general rule |

**Important:** `InputStream.read(byte[])` can return a positive number **smaller than the buffer size without having reached EOF**. A single “short read” does not prove that the data has ended; the API may return the remaining bytes on a subsequent read.

Other APIs, such as `InputStream.readNBytes(len)`, have a contract to return **an array shorter than the requested length when reaching EOF** rather than necessarily throwing `EOFException`. Always read the exact **Javadoc of the method you are using**.

## 3. When Is EOF Normal, and When Is It an Error?

The situation depends on the **data format/protocol**, not just the stream type.

### 3.1. Normal EOF at a Valid Boundary

Suppose a file contains an arbitrary sequence of bytes and the task is to read until the end:

~~~java
try (InputStream in = Files.newInputStream(path)) {
    int next;
    while ((next = in.read()) != -1) {
        process(next);
    }
}
~~~

This is an illustrative snippet requiring `InputStream`, `Files`, and `Path` imports; `path` and `process` must be defined, and the method must handle/declare `IOException`. In this problem, `read() == -1` is the **normal loop termination** condition, not corrupted data.

### 3.2. Abnormal EOF in the Middle of a Required Value

A file is defined to always contain **a 4-byte int code**, but in reality only 2 bytes remain:

~~~java
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {0, 1}))) {
    in.readInt(); // Throws EOFException.
}
~~~

This is an illustrative snippet requiring the corresponding imports and `IOException` handling. Because the format **requires a complete value**, you cannot take the 2 available bytes and treat them as a valid `int`.

### 3.3. EOF at the Start of a Record vs. EOF in the Middle of a Record

Consider a record protocol:

~~~text
Each record = [4-byte payload length] [payload of the exact declared byte count]
Records are consecutive; there is no record-count at the start of the stream.
~~~

There are three cases:

- **No bytes remaining immediately before the next record's header:** can be treated as **clean EOF**, meaning all complete records have been read.
- **First byte of the header has been read, but fewer than 4 bytes remain:** **truncated header**. This is corrupted data.
- **Valid header declares a payload of N bytes, but the source ends before N bytes are read:** **truncated payload**. This is corrupted data.

If the format has a **mandatory record count**—for example, 10 records were declared but only 9 were received—then EOF right at the boundary after the 9th record is still **an error according to that protocol**. Clean EOF vs. unexpected EOF **cannot be decided solely by seeing that the stream has ended**.

## 4. DataInputStream Contract and Methods That Commonly Throw EOFException

`DataInputStream` provides methods for reading **binary primitive types** and format-specific data. For each method, the number of bytes required depends on the format.

| Method | Data requirement | When bytes are missing |
| --- | --- | --- |
| `readBoolean()` | 1 byte | `EOFException` |
| `readByte()` / `readUnsignedByte()` | 1 byte | `EOFException` |
| `readShort()` / `readUnsignedShort()` | 2 bytes | `EOFException` |
| `readChar()` | 2 bytes | `EOFException` |
| `readInt()` / `readFloat()` | 4 bytes | `EOFException` |
| `readLong()` / `readDouble()` | 8 bytes | `EOFException` |
| `readFully(buffer)` | Full number of bytes requested by buffer | `EOFException` |
| `readUTF()` | Length header and modified UTF-8 data | `EOFException` if incomplete; `UTFDataFormatException` for invalid encoding per format |

Note: these are read operations following the **DataInput format**, not reading digit strings as text. A file containing characters `'1'`, `'2'`, `'3'`, `'4'` does not automatically mean the integer 1234 when calling `readInt()`. The method reads four bytes in DataInput's big-endian binary representation.

### 4.1. readInt Reads All Four Bytes, Rejecting a “Half int”

~~~java
byte[] twoBytes = {1, 2};
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(twoBytes))) {
    in.readInt();
} catch (EOFException ex) {
    System.out.println("Truncated integer");
}
~~~

This is an illustrative snippet requiring `DataInputStream`, `ByteArrayInputStream`, and `EOFException` imports and appropriate `IOException` handling/declaration. When calling `readInt()`, the two available bytes are **not enough** to construct an `int`.

**Do not** catch `EOFException` and substitute 0, because 2 bytes of data do not represent the value 0 in the protocol. If the format allows missing values, there must be an explicit rule for representing them.

### 4.2. readFully Differs from read(byte[])

~~~java
byte[] data = new byte[8];
in.readFully(data);
~~~

This is an illustrative snippet requiring `in` of type `DataInputStream` and `IOException` handling. `readFully(data)` requires **all 8 bytes**, looping reads as needed; if EOF occurs before then, the method throws `EOFException`.

Meanwhile:

~~~java
int n = in.read(data);
~~~

a single read via `InputStream`/`DataInputStream` may return a count **less than 8 but greater than 0**, even when more data follows. Therefore, to read a payload of a fixed length, `readFully` avoids the common bug of “calling read once and assuming the buffer is full”.

**Caution:** When `readFully` has read part of the data and then encounters `EOFException`, the buffer may **already be partially written**. Do not continue using it as a complete payload after catching the exception.

## 5. Complete Java 17 Program: Distinguishing Clean EOF from Truncated Data

Create the file **`EarlyEOFExceptionDemo.java`**. The program uses in-memory byte arrays to reproduce **seven scenarios** without depending on the filesystem or network:

1. Multiple complete binary records followed by clean EOF.
2. Empty stream: clean EOF before the first record.
3. Truncated payload.
4. Truncated length header.
5. Header with a length exceeding the format limit.
6. Difference between `readInt`, `read()`, and `readFully` when bytes run out.
7. Successful `readUTF` and reading a truncated UTF string.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EarlyEOFExceptionDemo {
    private static final int MAX_PAYLOAD = 1024;

    private static byte[] frame(String value) throws IOException {
        byte[] payload = value.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);
            out.write(payload);
        }
        return buffer.toByteArray();
    }

    private static byte[] concat(byte[] first, byte[] second) {
        byte[] result = Arrays.copyOf(first, first.length + second.length);
        System.arraycopy(second, 0, result, first.length, second.length);
        return result;
    }

    private static String readRecord(DataInputStream in) throws IOException {
        int first = in.read();
        if (first == -1) {
            return null; // Clean EOF: no header byte consumed.
        }
        // Once the first header byte exists, remaining 3 bytes are required.
        int length = ((first & 0xFF) << 24)
                | (in.readUnsignedByte() << 16)
                | (in.readUnsignedByte() << 8)
                | in.readUnsignedByte();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload); // Throws EOFException for truncated payload.
        return new String(payload, StandardCharsets.UTF_8);
    }

    private static void consume(String label, byte[] input) {
        System.out.println("== " + label + " ==");
        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(input))) {
            int count = 0;
            while (true) {
                String record = readRecord(in);
                if (record == null) {
                    System.out.println("clean-eof after " + count + " record(s)");
                    break;
                }
                System.out.println("record[" + count + "]=" + record);
                count++;
            }
        } catch (EOFException ex) {
            System.out.println("truncated=" + ex.getClass().getSimpleName());
        } catch (IOException ex) {
            System.out.println("io-error=" + ex.getMessage());
        }
    }

    private static void primitiveAndRawRead() throws IOException {
        System.out.println("== primitive and raw read ==");
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(new byte[] {1, 2}))) {
            in.readInt();
        } catch (EOFException ex) {
            System.out.println("readInt=" + ex.getClass().getSimpleName());
        }

        try (ByteArrayInputStream in =
                     new ByteArrayInputStream(new byte[] {65})) {
            System.out.println("read-first=" + in.read());
            System.out.println("read-end=" + in.read());
        }

        byte[] target = new byte[4];
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(new byte[] {65, 66}))) {
            in.readFully(target);
        } catch (EOFException ex) {
            System.out.println("readFully=" + ex.getClass().getSimpleName());
            System.out.println("partial-buffer=" + Arrays.toString(target));
        }
    }

    private static void utfSample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeUTF("Hello");
        }
        byte[] encoded = bytes.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(encoded))) {
            System.out.println("readUTF-ok=" + in.readUTF());
        }
        byte[] truncated = Arrays.copyOf(encoded, encoded.length - 1);
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            in.readUTF();
        } catch (EOFException ex) {
            System.out.println("readUTF-short=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        consume("complete records", concat(frame("A"), frame("BC")));
        consume("empty stream", new byte[0]);
        byte[] original = frame("HELLO");
        consume("truncated payload",
                Arrays.copyOf(original, original.length - 2));
        consume("truncated header", new byte[] {0, 0});
        consume("invalid length", new byte[] {0, 0, 8, 0});
        primitiveAndRawRead();
        utfSample();
    }
}
~~~

### How to Compile and Run

~~~bash
javac --release 17 -encoding UTF-8 EarlyEOFExceptionDemo.java
java EarlyEOFExceptionDemo
~~~

**Exact stdout verified by compiling and running:**

~~~text
== complete records ==
record[0]=A
record[1]=BC
clean-eof after 2 record(s)
== empty stream ==
clean-eof after 0 record(s)
== truncated payload ==
truncated=EOFException
== truncated header ==
truncated=EOFException
== invalid length ==
io-error=invalid frame length: 2048
== primitive and raw read ==
readInt=EOFException
read-first=65
read-end=-1
readFully=EOFException
partial-buffer=[65, 66, 0, 0]
readUTF-ok=Hello
readUTF-short=EOFException
~~~

The program does not need real files, does not open sockets, and does not rely on JVM-generated `EOFException` messages. Therefore, stdout demonstrates the error branches consistently. If running on systems with different JVM flags or versions, syntax and API contracts should still be checked against the corresponding Javadoc; the example has been specifically verified with `--release 17` compilation.

## 6. How to Read Length-Prefixed Records Without Swallowing Truncated Data

The core of the program is:

~~~java
private static String readRecord(DataInputStream in) throws IOException {
    int first = in.read();
    if (first == -1) {
        return null; // No header byte consumed: clean EOF.
    }

    int length = ((first & 0xFF) << 24)
            | (in.readUnsignedByte() << 16)
            | (in.readUnsignedByte() << 8)
            | in.readUnsignedByte();

    if (length < 0 || length > MAX_PAYLOAD) {
        throw new IOException("invalid frame length: " + length);
    }

    byte[] payload = new byte[length];
    in.readFully(payload);
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

This is **a method extracted from the full program**, requiring the corresponding imports and `MAX_PAYLOAD` constant.

### 6.1. Reading the First Byte Separately to Distinguish Clean EOF

At the moment of preparing to read a new record, `in.read()` returning `-1` means **no header byte has been consumed**. For the “multiple records until end of stream” protocol in the example, that is a valid boundary to stop the loop.

The method returns `null` to indicate **no next record**. Because the payload is converted to a `String` via `new String(...)`, a record with a 0-length payload returns an empty string `""`, which is **distinct from `null`** and is not mistaken for EOF.

If the format allows a `null` payload value in another way, use a result type with an explicit state (such as a wrapper with `present`, a sealed result, or a non-conflicting sentinel), instead of conflating a `null` data value with a `null` termination signal.

### 6.2. After the First Byte, the Remaining Header Bytes Are Mandatory

When `first != -1`, a record **has started**. The remaining three length bytes are read with `readUnsignedByte()`; this method throws `EOFException` if a required byte cannot be read. Thus, the input `{0, 0}` produces:

~~~text
== truncated header ==
truncated=EOFException
~~~

If you simply called `readInt()` for the entire header, caught `EOFException`, and “stopped reading normally”, you would not be able to distinguish **an empty stream/clean EOF** from **a header that started but was truncated**. That distinction is why the first byte must be read separately.

Note on the length assembly expression: `read()` returns an integer value from 0–255, so the code uses `first & 0xFF` and bit-shifts in **big-endian** order matching `DataOutputStream.writeInt`. With the highest sign bit set, the resulting `int` can be negative; the bounds check will reject it.

### 6.3. Validating Length Before Allocating the Buffer

A four-byte header is a 32-bit integer. If you blindly trust any length from an untrusted source, the program may attempt to allocate a huge array, causing **out-of-memory** errors or denial of service.

Protection example:

~~~java
if (length < 0 || length > MAX_PAYLOAD) {
    throw new IOException("invalid frame length: " + length);
}
~~~

The sample protocol sets a limit of `MAX_PAYLOAD = 1024`. The header `{0,0,8,0}` represents a length of 2048, so it prints:

~~~text
io-error=invalid frame length: 2048
~~~

This is an **invalid length**, not an `EOFException`: the parser rejects it before attempting to read the payload. In a real system, the limit value must be based on the format, memory budget, and security risks—do not hardcode 1024 for every application.

### 6.4. readFully Detects Missing Payload Bytes

After checking the length, the code creates a buffer of the exact size and calls:

~~~java
byte[] payload = new byte[length];
in.readFully(payload);
~~~

If the header states the payload must be 5 bytes long but the stream only has 3 bytes left, `readFully` throws `EOFException`. The example created the record `"HELLO"` and truncated the last two bytes to test this exact condition.

**Do not** use the 3 available bytes as a valid record, as doing so violates the format. If the application needs partial data recovery, design a **dedicated recovery mode** with clear logging and boundaries, rather than disguising an error path as success.

## 7. readFully May Have Partially Written to the Buffer Before Throwing

In the program:

~~~java
byte[] target = new byte[4];
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(new byte[] {65, 66}))) {
    in.readFully(target);
} catch (EOFException ex) {
    System.out.println("partial-buffer=" + Arrays.toString(target));
}
~~~

This is an excerpt from the runnable method. The buffer is created with four elements initially set to 0. Two bytes, `65` and `66`, are copied before EOF is encountered. Output on the executed JVM:

~~~text
readFully=EOFException
partial-buffer=[65, 66, 0, 0]
~~~

**Implication:** An exception does not mean the buffer is **rolled back** to its initial state. It may contain partial data, even though `readFully` reported a failure.

Handling principles:

1. Only publish or commit data once **the entire record has been read and validated**.
2. If a read fails, mark the current buffer/record as **incomplete** and do not reuse it as a valid value.
3. When a retry is needed, you must know **how many bytes the stream position has consumed**; a failed read may have advanced the cursor.
4. Do not assume you can retry the same method on the same stream and have the data automatically rewind to the start of the record.
5. If recovery is required, the format must support identifying record boundaries, offsets, checksums, or appropriate seek/reopen operations.

A `readFully` call guarantees **either read in full or fail**; it **does not guarantee atomicity of side effects on the array or stream state**.

## 8. readUTF and EOFException: Do Not Confuse with Standard UTF-8

`DataOutputStream.writeUTF(String)` and `DataInputStream.readUTF()` use **modified UTF-8 with an unsigned short length header**, which differs from simply writing `String.getBytes(StandardCharsets.UTF_8)` bytes.

In the program:

~~~java
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
try (DataOutputStream out = new DataOutputStream(bytes)) {
    out.writeUTF("Hello");
}
byte[] encoded = bytes.toByteArray();
~~~

Then `readUTF()` on the full encoded data returns `"Hello"`. If the last byte is removed, `readUTF()` no longer has the declared content and throws `EOFException`:

~~~text
readUTF-ok=Hello
readUTF-short=EOFException
~~~

### Corrupted UTF Without Missing Bytes

If the data has enough bytes but the **modified UTF-8 encoding is invalid**, the API may throw `UTFDataFormatException`, which is also a subclass of `IOException`. This is an **encoding format** error and must be distinguished from missing bytes.

Furthermore, the length header of `writeUTF/readUTF` limits the byte count per the format (up to 65535 encoded bytes); it is not a mechanism for reading UTF-8 files of arbitrary size.

**When building a custom protocol**, if you want standard UTF-8, you can design a byte length-prefix and use `StandardCharsets.UTF_8` as in the `readRecord` example. The writer and reader must agree on the exact format. Do not write with `writeUTF` and assume the reader can use `new String(input, UTF_8)` over the entire byte stream equivalently.

## 9. Reading Text: BufferedReader.readLine Returns null, Does Not Throw EOFException by Default

For line-delimited text files:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

This is illustrative code requiring `BufferedReader`, `Files`, `Path`, and `StandardCharsets` imports, and `IOException` declaration/handling. `processLine` must be defined.

According to the `readLine()` contract:

- When a line is available, returns a `String` (possibly empty).
- If the stream has ended and **no characters remain to form a new line**, returns `null`.
- A final line without a newline character **is still returned as a line**, not silently dropped.
- A genuine I/O error can still throw `IOException`; it is not always represented by `null`.

If a format requires exactly 10 lines and only 9 are received, `readLine() == null` on the 10th line is a **format violation**, even though the API signals EOF with `null` rather than throwing `EOFException`. The caller must decide how to handle it, for example:

~~~java
String header = reader.readLine();
if (header == null) {
    throw new EOFException("missing required header line");
}
~~~

This is an illustrative snippet with an appropriate `reader` variable and `EOFException` import. Here, **the application actively throws `EOFException`** to express a “missing required line”; `readLine()` itself does not throw `EOFException`.

## 10. InputStream.read(byte[]) Returning Fewer Bytes Is Not Necessarily EOF

A common misconception:

~~~java
byte[] buffer = new byte[1024];
int n = input.read(buffer);
if (n < buffer.length) {
    // Wrong if assuming data has ended or is corrupted.
}
~~~

This is an illustrative snippet requiring an `input` variable of type `InputStream` and `IOException` handling. A single `read(buffer)` call may return **fewer bytes than requested**, especially on network streams or wrapped streams, while subsequent reads still yield more bytes.

Therefore:

- `n > 0`: `n` bytes were read; **do not conclude** the stream has ended just because `n` is smaller than the buffer.
- `n == -1`: signals EOF per the `InputStream` API.
- `n == 0`: for certain overloads and special cases (such as `len = 0`), zero bytes may be read; handle according to the exact Javadoc.
- If you need exactly N bytes, use a **looping read until N bytes are obtained**, such as `DataInputStream.readFully`.
- If the format allows reading until EOF, handle the sentinel; if the format requires N bytes, reaching EOF before N is an error.

Do not rely on `InputStream.available()` as “the total number of remaining bytes in the file/stream”. According to the API, it is only **an estimate of the number of bytes that can be read or skipped without blocking** under the documented conditions; especially for network streams, it does not tell you whether future data will arrive.

## 11. Reading from Sockets: Close, EOF, and Timeout Mean Different Things

On a network stream, reads can produce outcomes that must be distinguished:

- **`read() == -1`**: no more data from the input according to the stream state; in TCP, this can reflect that the sender has closed its sending side normally. However, if the protocol is waiting for the rest of a message, it is still an **unexpected end** at the protocol layer.
- **`SocketTimeoutException`**: an I/O operation exceeded the configured timeout. This **does not mean** the sender has definitely closed the stream or that the data is permanently truncated.
- **`EOFException`**: typically thrown by higher-level APIs requesting a complete structure/value when the stream ends before fulfilling the request.
- **`SocketException`/other `IOException`**: connection errors, resets, I/O issues; do not treat all of them as EOF.

For example, a peer sends a 100-byte length header, sends only 60 payload bytes, and closes the connection. If the parser uses `readFully(100 bytes)`, it reports `EOFException` because the message is **incomplete**. If the code only checks `read() == -1` and treats it as a normal end, it might accidentally accept a truncated record.

**The right action depends on the protocol**: log the packet/frame id, reject the record, close the faulty connection, consider retrying the request **if the operation is safe/idempotent**, or resume from a checkpoint if the format supports it. Do not retry infinitely just because EOF occurred.

## 12. Parser States That Should Be Clearly Distinguished

A record parser typically has the following states:

| State | Data received | Appropriate outcome |
| --- | --- | --- |
| Record not started; stream reports EOF | No new header byte | Clean EOF if format allows |
| Incomplete header | Partial header | Truncated header error |
| Complete header, but negative/out-of-bounds length | Full header, invalid value | Format/validation error |
| Insufficient payload compared to length | Partial payload | Truncated payload error |
| Complete payload, but invalid encoding | Full bytes, invalid decode | Encoding format error |
| Valid payload | Full header and full content | Commit/emit a record |
| Stream ends after a complete record | At the next boundary | Clean EOF if required record count is met |

This table describes **an application parser model**; it does not claim that Java provides built-in separate exception classes for every row. Some systems create custom exceptions like `TruncatedRecordException` or `InvalidLengthException` and keep the original `EOFException`/`IOException` as the cause so callers can apply different policies.

### 12.1. Do Not Apply One Error Policy to Every Context

Depending on the application:

- **Configuration files/business records:** missing data should fail fast; do not return an unvalidated object.
- **Continuous streaming:** clean EOF at a packet boundary can be completely normal.
- **Network request-response:** a payload shorter than content-length can be a protocol error requiring controlled retry.
- **Recovery/forensic files:** may save up to the last complete record and log a warning about the truncated record; do not silently treat the whole file as valid.
- **Append-only files while a writer is still active:** seeing EOF while reading does not mean the writer is finished; coordination/tailing mechanisms and record commit rules are needed rather than drawing conclusions from the read API alone.

The format design must specify **when EOF is valid**. Without that specification, catching `EOFException` risks hiding data corruption.

## 13. Catching EOFException in the Right Place

Because `EOFException extends IOException`, place the specific handler **before the general handler** when both are present:

~~~java
try {
    readExpectedRecord();
} catch (EOFException ex) {
    reportTruncatedData(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
~~~

This is an illustrative pattern; the methods must be defined. If you place `catch (IOException)` before `catch (EOFException)` in the same chain, the `EOFException` branch is shadowed and **the compiler will reject it** as an unreachable handler.

A dangerous anti-pattern:

~~~java
while (true) {
    try {
        processNextRecord();
    } catch (EOFException ex) {
        break; // Wrong if a mid-record truncation also goes through here.
    }
}
~~~

This is illustrative code, not a standalone program. It is only valid when **the contract of `processNextRecord()` guarantees that `EOFException` strictly acts as the termination sentinel between two records**, with no possibility of mid-record truncation. With `DataInputStream.readInt()`, `EOFException` alone **cannot** distinguish running out of bytes right before a value from running out of bytes in the middle of a value.

A better approach for a length-prefixed protocol without a record count is:
1. Check for clean EOF at **the start of the header**, before consuming any byte.
2. Once a record has started, let `EOFException` propagate as a truncation error.
3. Catch `EOFException` at **the file/connection processing boundary**, mark the input as faulty, and do not accidentally continue to a next record.

In the sample program, `readRecord` returns `null` for clean EOF and throws `EOFException` when the header/payload is truncated. This separates **normal** and **abnormal** conditions through the parser's own contract.

## 14. EOFException Is Not a Way to “Patch” Missing Data

Some wrong choices and their consequences:

~~~java
try {
    return in.readInt();
} catch (EOFException ex) {
    return 0; // Two missing bytes do not mean the number 0.
}
~~~

This is an anti-pattern inside a method returning `int`, with an appropriate `in` variable and `IOException` declaration. If the format specifies 4 bytes and only 2 are received, there is no evidence that the value is 0.

A similar pattern with strings:

~~~java
byte[] payload = new byte[size];
try {
    in.readFully(payload);
} catch (EOFException ex) {
    return new String(payload, StandardCharsets.UTF_8);
}
~~~

This is an illustrative anti-pattern with a method returning `String` and corresponding variables/imports. The buffer may still contain unread portions, defaulted to zero; converting it to a `String` turns **truncated/corrupted input** into a result that looks valid.

Better handling:

- Rethrow the exception with context (offset, record index, expected/actual bytes if known).
- Only publish **records that have been fully read and validated**.
- If the application allows partial recovery, provide a recovery result **clearly marked as incomplete**.
- When persisting state, use transactions/checkpoints: data from an incomplete record must not be automatically committed.
- Do not use `EOFException` in place of normally handleable missing business data if the API already has an appropriate result type.

## 15. Designing Exceptions with Context for Easier Debugging

`EOFException` may not carry a sufficiently detailed message. When encountering truncated data, callers often want to know:
- Which **file/stream** was being read, and from what **offset**?
- Which **record index**, and was it in the **header or payload**?
- How many bytes were expected?
- How many bytes were read before the error, if known?
- Can it be safely retried or resumed?

One way to attach context while preserving the original error:

~~~java
try {
    in.readFully(payload);
} catch (EOFException ex) {
    throw new IOException(
            "Truncated payload in record " + recordIndex
                    + ", expected " + payload.length + " bytes",
            ex);
}
~~~

This is illustrative code; appropriate variables and `IOException` handling are required. The new wrapper is an `IOException` with **cause = the original `EOFException`**. Callers can log the cause's stack trace along with the application-level message.

If callers need to catch **truncated data** specifically as a stable contract branch, you can create a custom `IOException` subclass with structured fields. Do not rely on comparing message strings like `"Unexpected EOF"` because messages can change.

A similar principle applies to `try-with-resources`: if the read operation fails and `close()` also fails, the exception from `close()` may be attached in `getSuppressed()`. Logging the entire `Throwable`, not just `ex.getMessage()`, preserves both the cause and cleanup errors.

## 16. DataInputStream, readUTF, and ObjectInputStream: Do Not Mix Formats

`DataInputStream` and `DataOutputStream` are a matching pair for reading/writing binary primitives with the same encoding. `ObjectInputStream` and `ObjectOutputStream` use a different **object serialization stream format**, with its own markers and metadata.

In some cases, reading an object stream to the end may produce `EOFException`. However, do not assume:

- Any `ObjectInputStream.readObject()` throwing `EOFException` means the end of a valid object list.
- Every exception when reading objects is `EOFException`.
- A truncated serialization file only needs `EOFException` caught and treated as finished reading.

Besides `EOFException`, object serialization can throw `StreamCorruptedException`, `OptionalDataException`, `ClassNotFoundException`, or other error types depending on the API and data. If the format does not provide **an object count, termination sentinel, or explicit framing**, relying solely on `EOFException` to accept a file can mask truncation.

For long-lived data or network transmission, Java native serialization also carries version compatibility and security concerns. Choose a clear format/protocol with size limits, schema validation, and proper record boundaries.

### Do Not Equate UTF-8 and Modified UTF-8

The `writeUTF/readUTF` pair matches each other per the `DataOutput`/`DataInput` Javadoc. However, a custom format using `writeInt(length) + UTF-8 bytes` must be read using the exact length-prefix + UTF-8 logic; you cannot swap in `readUTF()` because the header and encoding differ.

## 17. Performance, Memory, and Untrusted Data

When reading length-prefixed data from external sources:

1. **Enforce size limits** before allocating arrays; reject negative or excessively large lengths.
2. **Limit the number of records** and total bytes when necessary, not just a single record.
3. **Do not hold all records in memory** if each complete record can be processed individually.
4. **Do not allocate based on `available()`** as if it were the true length.
5. **Do not treat `read()` returning fewer bytes than requested as corrupted data** when the API allows partial reads; only confirm truncation after actually hitting EOF before the required length.
6. **Validate encoding** when input must be valid UTF-8. Standard `new String(bytes, StandardCharsets.UTF_8)` can replace malformed byte sequences with replacement characters; if the format requires strict UTF-8, use a `CharsetDecoder` configured with `CodingErrorAction.REPORT`.
7. **Avoid infinite retries** on a stream that has already hit EOF. Reading the same stream again may keep returning `-1`; retrying requires a new source, seek/reopen, or a designed resume mechanism.
8. **Handle cancellation/timeout** separately from EOF errors, especially in network environments.
9. **Close streams properly** using `try-with-resources` and preserve cleanup/suppressed exceptions.
10. **Intentionally test corrupted data**, not just the happy path.

A header allowing huge data reads without limits can cause resource exhaustion before the parser even has a chance to detect a truncated payload. Therefore, length validation and total limits are an essential part of a safe parser.

## 18. Common Misconceptions

1. **“Reaching EOF always throws EOFException.”** False: `InputStream.read` typically returns `-1`; `Reader.readLine` returns `null`.
2. **“EOFException is unchecked.”** False: it extends `IOException`, so it is a checked exception.
3. **“Catching EOFException and breaking out of any record-reading loop is safe.”** False if missing bytes in the middle of a header/payload also throw `EOFException`.
4. **“readInt just reads until data runs out; 2 bytes still produce a number.”** False: all 4 bytes are required.
5. **“Because readFully threw an error, the buffer is guaranteed to be unmodified.”** False: it may have been partially written.
6. **“A single read(byte[]) call must fill the buffer.”** False: the API may return fewer bytes than requested.
7. **“One partial read proves EOF.”** False: more bytes may arrive on the next read.
8. **“available() gives the total remaining bytes in the stream.”** False: there is no such guarantee in the general contract.
9. **“A truncated header is clean EOF because some bytes were read.”** False: if a record has started, an incomplete header is an error.
10. **“Ending right after a complete record is always an error.”** No: it depends on the protocol; it may be a clean EOF boundary.
11. **“If record-count declares 10, receiving 9 and hitting EOF still counts as complete.”** False under a format with a mandatory count.
12. **“With length N, receiving N-1 bytes can still emit a normal record.”** False if the format requires all N bytes.
13. **“For a large length header, just allocate and try reading.”** Dangerous: validate limits first.
14. **“UTFDataFormatException and EOFException are the same.”** False: one is an encoding error, the other is missing bytes (depending on method and context).
15. **“readUTF understands all forms of UTF-8 files.”** False: it uses modified UTF-8 and a specific header.
16. **“writeInt(length) and writeUTF have the same header.”** False: `writeInt` uses 4 bytes; `writeUTF` has a 2-byte length header.
17. **“SocketTimeoutException definitely means the peer closed the connection.”** False: a timeout is a wait limit, not synonymous with EOF.
18. **“Catching IOException before EOFException still catches EOF separately.”** False: the more specific branch afterward will be unreachable.
19. **“You should default to returning 0 when bytes are missing for an int.”** False: that legitimizes corrupted data.
20. **“Closing the stream makes partially read data valid.”** False: cleanup does not repair the format.
21. **“EOFException always has a fixed message.”** False: do not depend on JVM/API messages.
22. **“If readObject throws EOFException, the entire object stream is definitely valid.”** False: format and completeness must be determined by appropriate framing/metadata.
23. **“If EOFException is caught, there is no need to catch IOException.”** False: the parser can still encounter other I/O, format, or length errors.
24. **“EOF from a socket and EOF from reading a binary file need the exact same retry policy.”** No: policy depends on the source, side effects, and protocol.
25. **“A truncated record can be treated as an empty record.”** False unless that representation exists in the format.

## 19. Self-Check Exercises

**Question 1.** `InputStream in` contains one byte, and `in.read()` is called twice. What is the result?

*Answer:* The first call returns the byte value 0–255, and the second returns `-1` at EOF; this scenario alone does not throw `EOFException`.

**Question 2.** How many bytes does `DataInputStream.readInt()` require, and what happens if only two bytes remain?

*Answer:* It requires four bytes per the `DataInput` format; when bytes are missing, it throws `EOFException`.

**Question 3.** A protocol has a 4-byte header, and the stream is empty before reading a header: can this be a normal termination?

*Answer:* Yes, if the protocol allows a sequence of multiple records to end at a boundary where no record has started. If the format requires at least one record or has an unmet record-count, it is still a protocol error.

**Question 4.** 1 byte of the header has been read, and the stream ends. Should the loop stop normally?

*Answer:* No; the header has started but is incomplete, so it must be treated as a truncated header.

**Question 5.** The header declares a 100-byte payload, while only 60 bytes remain. What does `readFully(payload)` do?

*Answer:* It attempts to read the full amount and throws `EOFException` when insufficient; the buffer may already contain the 60 bytes and must not be treated as a complete record.

**Question 6.** `InputStream.read(buffer)` returns 60 for a 100-byte buffer. Can you conclude with certainty that it is truncated?

*Answer:* Not yet. A single read can return fewer bytes before EOF; you must continue reading per the contract to determine whether all 100 bytes are received.

**Question 7.** Should `available() == 0` be used to conclude that a file/socket has reached EOF?

*Answer:* No. `available()` is not a general end-of-stream indicator for all streams.

**Question 8.** How does `readUTF()` differ from `new String(bytes, UTF_8)`?

*Answer:* `readUTF` expects a length header and modified UTF-8 per `DataInput`. `new String` decodes bytes as standard UTF-8 and does not handle that header.

**Question 9.** For a final text line without a newline character, does `readLine()` return this line?

*Answer:* Yes. Only when no characters remain for the next line does `readLine` return `null`.

**Question 10.** A program has `catch (IOException)` before `catch (EOFException)` in the same `try` block: what is the result?

*Answer:* A compile-time error because `catch (EOFException)` is shadowed by the preceding `catch (IOException)`.

**Question 11.** A length header is read as 2048, but the format limit is 1024: `EOFException` or validation error?

*Answer:* Length validation error. The example throws `IOException` with the message `invalid frame length` before attempting to read the payload.

**Question 12.** Why shouldn't you catch `EOFException` and return a short payload as if it were fully read?

*Answer:* Because the record has not met the required size; the buffer may contain partial data, is missing bytes, and has not passed validation.

**Question 13.** If a peer does not respond and `read()` times out, does that mean the peer closed the connection?

*Answer:* No. A timeout is an expiration of the wait limit, distinct from EOF signaled by `-1` or confirmed missing bytes.

**Question 14.** When sending a record containing multi-byte UTF-8 characters intact, should the length be written as the character count or byte count?

*Answer:* For a protocol defining the payload as a UTF-8 byte array, the length must be calculated in **encoded bytes**, not the number of Unicode characters in the `String`.

**Question 15.** A parser has received a full header and payload, then encounters EOF before a new record header. Does it need to throw `EOFException`?

*Answer:* Not necessarily. If the format allows consecutive records until EOF, this is clean EOF. If more records are required by a count, it is a format error.

## 20. Checklist for Implementing an Unexpected-EOF-Resistant Parser

Before putting a parser into production:

1. **Document the byte-level format:** header, byte order, length, encoding, checksum, record count, termination sentinel.
2. **Define at which boundary clean EOF is valid:** before a header, after a sentinel, or once the record count is reached?
3. **Use APIs that read the exact required number of bytes:** `readFully` or an equivalent loop, not a single hopeful `read`.
4. **Validate length and resource limits** before allocation.
5. **Distinguish header, payload, encoding, checksum, and I/O errors** according to handling needs.
6. **Do not emit partial records** unless the format allows it.
7. **Only commit business side effects after validating a complete record.**
8. **Preserve cause/stack trace and context** when wrapping exceptions.
9. **Be careful with stream state after an error:** it may have been partially consumed and does not automatically rewind.
10. **Test empty input, complete input, missing 1/2/3 header bytes, missing payload, invalid length, length 0, multiple records, trailing bytes, invalid encoding, and I/O errors.**
11. **Test both clean EOF and truncated input paths**, ensuring they do not take the same success branch.
12. **Check timeouts and cancellation** for network streams; do not retry infinitely.
13. **Close resources safely** with `try-with-resources` and inspect suppressed exceptions if `close` also fails.
14. **Do not rely on the default message** of `EOFException` to classify behavior.

## 21. Official Java 17 Documentation

- [Java SE 17 API – EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): exception indicating end of input before reading all required data.
- [Java SE 17 API – IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked superclass of `EOFException` and many other I/O errors.
- [Java SE 17 API – InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read()` returns `-1` at EOF; overloads may read fewer bytes than requested.
- [Java SE 17 API – DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): primitive reads, `readFully`, `readUTF`.
- [Java SE 17 API – DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html): describes data formats, `readFully`, and EOF cases.
- [Java SE 17 API – DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): `writeInt`, `writeUTF` compatible with `DataInput`.
- [Java SE 17 API – BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` returns `null` at end of input.
- [Java SE 17 API – UTFDataFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html): invalid modified UTF-8 format error.
- [Java SE 17 API – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): for distinguishing asynchronous task waiting errors from EOF in data when concurrency is involved.
- [JLS Java SE 17 Chapter 11 – Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): foundation of checked/unchecked exceptions.

**Conclusion:** `EOFException` is a **checked `IOException`** that typically signals an API was requesting a complete binary value, but the stream ended before reading enough bytes. Meanwhile, `InputStream.read() == -1` or `BufferedReader.readLine() == null` can simply be **normal** EOF. Define record boundaries, detect **whether a header or payload has already started**, read the exact required size, validate lengths, and only accept complete records. Never catch `EOFException` and blindly treat all prematurely terminated data as valid.
