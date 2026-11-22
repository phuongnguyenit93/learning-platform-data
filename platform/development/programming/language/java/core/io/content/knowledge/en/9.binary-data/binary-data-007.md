# Length Limit of `writeUTF` in Java

`DataOutputStream.writeUTF(String)` is a way to write a string to a Java **binary data stream** so that `DataInputStream.readUTF()` can read it back. Each record consists of a **2-byte length prefix** followed by content encoded in **Modified UTF-8** (Java's variant of UTF-8). Because the prefix is an unsigned 2-byte integer, **the encoded payload can be at most 65,535 bytes**. If a string exceeds this limit, `writeUTF` throws `UTFDataFormatException`.

The easiest point to get wrong: **65,535 is the number of Modified UTF-8 bytes, not the number of characters, not `String.length()`, and does not include the 2 prefix bytes.** Depending on the character, a Java `char` unit occupies 1, 2, or 3 bytes; an emoji outside the BMP typically occupies **6 bytes** in Modified UTF-8.

This article belongs to the **Binary Data** section of Java Core I/O. We will understand the wire format, compute the limit accurately, recognize exceptions, verify with Java 17+, and choose other ways to write data when strings exceed the limit.

## 1. What Does `writeUTF` Write to OutputStream?

Commonly used APIs:

```java
DataOutputStream out = new DataOutputStream(outputStream);
out.writeUTF(text);

DataInputStream in = new DataInputStream(inputStream);
String restored = in.readUTF();
```

This is an **illustrative snippet**: `outputStream`/`inputStream` are two appropriate byte sources/sinks, `text` is a `String`; `java.io.*` imports and `IOException` handling are needed. The reader must be positioned at the exact start of the record and use the exact `writeUTF` format.

Record structure:

```text
+------------------------+-------------------------------------+
| 2-byte length          | Payload: Modified UTF-8             |
| unsigned short,        | exactly N bytes                     |
| big-endian, value N    | (N from 0 to 65535)                 |
+------------------------+-------------------------------------+

Total bytes of a successful writeUTF call = 2 + N
Maximum N = 65535
Maximum total record size = 65537 bytes
```

- The first two bytes represent `N` in **most-significant byte first, least-significant byte second** (*big-endian*) order. Interpret them as an unsigned 16-bit integer in `0..65535`.
- `N` is the **number of payload bytes** after encoding the *entire string* in Modified UTF-8.
- `DataInputStream.readUTF()` reads the prefix automatically, then reads the exact number of payload bytes and decodes back to `String`. The reader does **not** pass the string length separately.
- If the payload requires **65,536 bytes or more**, `DataOutputStream.writeUTF` throws `UTFDataFormatException` (a subclass of `IOException`) instead of writing a valid record.
- An empty string still produces **2 bytes** `00 00`, because the payload has length 0.

Example: writing `"ABC"` produces these record bytes:

```text
00 03 41 42 43
|---| |------|
  3   "ABC" in Modified UTF-8
```

Thus `writeUTF("ABC")` differs from `out.write("ABC".getBytes(UTF_8))`: the first **automatically prepends a 2-byte length**, whereas the second only writes the bytes you supply.

## 2. Why Is the Limit Exactly 65,535 Bytes?

The length field is represented in **2 bytes**, i.e., 16 bits, so it can hold at most:

\[
2^{16} - 1 = 65535
\]

Under the `DataOutput.writeUTF` specification, Java must compute the **total Modified UTF-8 byte count of the string** before deciding whether it can write. If the total exceeds 65,535 bytes, calling `writeUTF` fails. This is a **binary format** limit, not a `String` memory limitation or `OutputStream` capability limit.

Distinguish clearly:

| Quantity | Meaning |
| --- | --- |
| `s.length()` | Number of UTF-16 `char` units in the Java string |
| `s.codePointCount(0, s.length())` | Number of Unicode code points (not synonymous with user-visible characters) |
| `s.getBytes(UTF_8).length` | Number of bytes in **standard UTF-8** |
| `modifiedUtf8Length(s)` | Number of **Modified UTF-8** bytes required by `writeUTF` |
| `2 + modifiedUtf8Length(s)` | Size of the entire `writeUTF` record when valid |

If a string contains only ASCII characters from `U+0001` to `U+007F`, each `char` needs 1 byte, so a 65,535-character string is still valid. If all characters need 3 bytes, only 21,845 `char`s fit the limit. For mixed data, you must sum the byte length of each `char` unit.

Do not work around this by "subtracting 2 bytes first" from 65,535: the two prefix bytes are **outside** the payload and are already accounted for separately in total record size.

## 3. Modified UTF-8 Is Not Identical to Standard UTF-8

`DataOutputStream.writeUTF` uses **Modified UTF-8 of the `DataInput`/`DataOutput` protocol**, not `StandardCharsets.UTF_8` directly.

Encoding is based on each Java `char` (one UTF-16 code unit):

| `char` value | Bytes in Modified UTF-8 | Notes |
| --- | ---: | --- |
| `U+0001` to `U+007F` | 1 | ASCII other than NUL |
| `U+0000` (NUL) | 2 | Encoded as `C0 80` |
| `U+0080` to `U+07FF` | 2 | For example `é` = `C3 A9` |
| `U+0800` to `U+FFFF` | 3 | Each **`char` unit**, including surrogates |
| Unicode code point outside BMP, e.g. `😀` | **6** | Java represents as **two surrogate `char`s**, each becoming 3 bytes |

Important differences:

1. **NUL:** Standard UTF-8 encodes `\u0000` as `00` (1 byte); Modified UTF-8 encodes it as `C0 80` (2 bytes).
2. **Emojis / non-BMP code points:** Standard UTF-8 uses one 4-byte sequence; Modified UTF-8 treats the UTF-16 surrogate pair as **two 3-byte sequences** (6 bytes total).
3. **Modified UTF-8 is not standard UTF-8 for general text exchange**. Do not assume `new String(payload, UTF_8)` or `InputStreamReader(..., UTF_8)` will read a `writeUTF` payload properly, especially when NUL or non-BMP characters are present.
4. Because surrogate pairs are encoded per `char` unit, counting "code points" is not sufficient to determine Modified UTF-8 size.

### A Concrete Record

Writing a string containing **NUL**, `A`, and the emoji `😀` causes Modified UTF-8 to produce the payload:

```text
C0 80                NUL: 2 bytes
41                   A:   1 byte
ED A0 BD ED B8 80    😀:  6 bytes (two UTF-16 surrogates)
--------------------------------
Payload: 9 bytes

Whole record:
00 09 C0 80 41 ED A0 BD ED B8 80
|---| |-------------------------|
  9      9-byte payload
```

Java's `readUTF()` reads this record and restores the exact original string. A standard UTF-8 decoder may consider those bytes representing NUL/surrogates to be invalid.

## 4. Numeric Examples at Critical Boundaries

Suppose `repeat(n)` repeats a string `n` times, counting only the payload of one `writeUTF` call:

| Content | Modified UTF-8 bytes per element | Repeat count | Payload size | Result |
| --- | ---: | ---: | ---: | --- |
| `"A"` | 1 | 65,535 | 65,535 | Succeeds |
| `"A"` | 1 | 65,536 | 65,536 | `UTFDataFormatException` |
| `"\u0000"` | 2 | 32,767 | 65,534 | Succeeds |
| `"\u0000"` | 2 | 32,768 | 65,536 | `UTFDataFormatException` |
| `"中"` | 3 | 21,845 | 65,535 | Succeeds |
| `"中"` | 3 | 21,846 | 65,538 | `UTFDataFormatException` |
| `"😀"` | 6 | 10,922 | 65,532 | Succeeds |
| `"😀"` | 6 | 10,923 | 65,538 | `UTFDataFormatException` |

For the emoji specifically: `"😀".length() == 2` because it is a surrogate pair. Repeating 10,922 emojis creates a `String` of **21,844 `char`s**, yet its Modified UTF-8 payload is **65,532 bytes**. Adding one more emoji increases `String.length()` by only 2, but increases the payload by **6 bytes**, exceeding the limit.

Hence, **`s.length() <= 65535` is necessary but not sufficient** for `writeUTF` to succeed. Across characters represented as UTF-16 units, each `char` needs at most 3 bytes in Modified UTF-8. If `s.length() > 65535`, it is guaranteed over the limit; below that threshold, you still need to compute the encoded size.

## 5. Java 17+: Program Verifying Success, Failure, and readUTF

Create file `WriteUtfLimitDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UTFDataFormatException;
import java.util.HexFormat;

public class WriteUtfLimitDemo {

    private static void probe(String label, String text)
            throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            try {
                out.writeUTF(text);

                byte[] record = buffer.toByteArray();
                int payloadLength = ((record[0] & 0xff) << 8)
                        | (record[1] & 0xff);

                try (DataInputStream in = new DataInputStream(
                        new ByteArrayInputStream(record))) {
                    String restored = in.readUTF();
                    System.out.println(label + ": payload="
                            + payloadLength + " total=" + record.length
                            + " equal=" + text.equals(restored));
                }
            } catch (UTFDataFormatException e) {
                System.out.println(label
                        + ": UTFDataFormatException written="
                        + buffer.size());
            }
        }
    }

    public static void main(String[] args) throws IOException {
        String nul = String.valueOf((char) 0);
        String cjk = "\u4E2D"; // 中
        String emoji = new String(Character.toChars(0x1F600));

        probe("ASCII max", "A".repeat(65535));
        probe("ASCII over", "A".repeat(65536));

        probe("NUL max", nul.repeat(32767));
        probe("NUL over", nul.repeat(32768));

        probe("CJK max", cjk.repeat(21845));
        probe("CJK over", cjk.repeat(21846));

        probe("Emoji max", emoji.repeat(10922));
        probe("Emoji over", emoji.repeat(10923));

        ByteArrayOutputStream tinyBuffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(tinyBuffer)) {
            out.writeUTF(nul + "A" + emoji);
        }
        String hex = HexFormat.ofDelimiter(" ").withUpperCase()
                .formatHex(tinyBuffer.toByteArray());
        System.out.println("Wire example: " + hex);
    }
}
```

Compile/run with JDK 17+:

```bash
javac WriteUtfLimitDemo.java
java WriteUtfLimitDemo
```

Verified stdout on JDK:

```text
ASCII max: payload=65535 total=65537 equal=true
ASCII over: UTFDataFormatException written=0
NUL max: payload=65534 total=65536 equal=true
NUL over: UTFDataFormatException written=0
CJK max: payload=65535 total=65537 equal=true
CJK over: UTFDataFormatException written=0
Emoji max: payload=65532 total=65534 equal=true
Emoji over: UTFDataFormatException written=0
Wire example: 00 09 C0 80 41 ED A0 BD ED B8 80
```

Explanation of output:

- The `payload` field is the two prefix bytes reassembled as an unsigned integer. `total` is the size of the entire record in `ByteArrayOutputStream`.
- For strings within the threshold, `readUTF()` restores the exact string and `equals` is `true`.
- For strings over the threshold, `UTFDataFormatException` occurs because the payload exceeds 65,535 bytes; **in this example and JDK implementation**, `writeUTF` calculates the size beforehand, so `ByteArrayOutputStream` still holds 0 bytes from the failed write. Do not generalize this observation into a guarantee that every I/O error on every stream rolls back written data.
- `tinyBuffer` demonstrates the actual byte layout, including the `00 09` prefix, NUL byte as `C0 80`, and the 6-byte emoji.

The program uses `HexFormat` (Java 17), `String.repeat` (Java 11+), and `Character.toChars`. It does not depend on console emoji rendering support: output is hex and booleans.

## 6. Computing Modified UTF-8 Byte Count Before Writing

If you want to check the limit before creating a record, you can compute the byte count per `char` unit:

```java
static long modifiedUtf8Length(String s) {
    long length = 0;
    for (int i = 0; i < s.length(); i++) {
        char c = s.charAt(i);
        if (c >= 0x0001 && c <= 0x007f) {
            length += 1;
        } else if (c <= 0x07ff) {
            length += 2;
        } else {
            length += 3;
        }
    }
    return length;
}
```

This is a **code snippet** to place inside a Java class; `s` must be non-`null`. Using `long` prevents overflow if the application processes extremely long strings. The algorithm visits each `char` once: `O(s.length())` time and `O(1)` auxiliary space.

Why are these three branches right?

1. `c` in `0x0001..0x007F` needs 1 byte.
2. `c == 0` or `c` in `0x0080..0x07FF` needs 2 bytes.
3. The rest `0x0800..0xFFFF` needs 3 bytes. The two surrogate units of a non-BMP code point add **twice × 3**.

Validation check:

```java
long encodedLength = modifiedUtf8Length(s);
if (encodedLength > 65535) {
    throw new IllegalArgumentException(
            "writeUTF payload exceeds 65535 bytes: " + encodedLength);
}
out.writeUTF(s);
```

This is a snippet: `s` and `out` are prepared beforehand, and `IOException` must be handled. Pre-computing is useful for giving meaningful error messages, picking another encoding, or rejecting oversized values before starting a large record. However, **`writeUTF` checks the size itself**; you are not forced to write this counter just to avoid an exception.

**Do not use** `s.getBytes(StandardCharsets.UTF_8).length` as an equivalent check for `writeUTF`. Standard UTF-8 and Modified UTF-8 differ in byte count on NUL, surrogates, and non-BMP code points.

### Avoid Arbitrarily Truncating Strings When Over the Limit

`s.substring(0, 65535)` slices by `char` units, not by Modified UTF-8 bytes. Even if the new slice is shorter than 65,535 `char`s, it may still require more than 65,535 bytes. Slicing in the middle of a surrogate pair can also split Unicode data improperly. Truncating strings just to fit the format can also lose critical data.

When all content must be preserved, choose **another record format** rather than slicing/truncating data. If a protocol strictly mandates `writeUTF`, you may split into multiple records **only when both writer and reader are designed upfront to understand multi-part records**, with explicit ordering, lengths, and part counts. Never split into multiple `writeUTF` calls expecting a single `readUTF` to reassemble them.

## 7. Handling UTFDataFormatException

An exception-catching example:

```java
try {
    out.writeUTF(value);
} catch (UTFDataFormatException e) {
    // value cannot fit inside a single writeUTF record.
    // Return a proper message, choose an alternative protocol, or reject the data.
}
```

This is a snippet: `out` is a `DataOutputStream` and `value` is a `String`; `java.io.UTFDataFormatException` must be imported.

Points to note:

- `UTFDataFormatException` does not mean `String` exceeded Java memory limits. It reports that the data does not fit the **2-byte prefixed Modified UTF-8 contract**.
- Other `IOException`s can arise from a closed source/target, full disk, dropped network, etc. Do not lump every `IOException` together as a length error.
- `UTFDataFormatException` can also occur **when reading** `DataInputStream.readUTF()` if the data section is not a valid Modified UTF-8 string. When reading fails due to missing bytes mid-record, `EOFException` can occur.
- With a multi-field binary stream, if a write fails mid-way due to an I/O error, the destination state may already have been mutated. Do not rely on any default stream rollback mechanism.
- Applications should not catch `UTFDataFormatException` and retry `writeUTF` on the same unmodified value or blindly truncate the string to "make it pass".
- When technical format constraints are exposed to users (e.g., a description field must fit in one `writeUTF` record), validate upon receiving input to return an accurate error early.

## 8. Alternative for Longer Strings: 4-Byte Length Prefix + Standard UTF-8

If you **design your own binary protocol**, you can replace `writeUTF` with the format:

```text
[int32 length N, big-endian] [N bytes standard UTF-8]
           4 bytes                   N bytes
```

Advantages: not bound by `writeUTF`'s 65,535-byte limit and uses **standard UTF-8**, making cross-system interoperability easier. However, **this format is incompatible with `readUTF`**. The reader must use `readInt`, `readFully`, and decode using the agreed charset.

Standalone Java 17+ example, save as `LongTextFrameDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class LongTextFrameDemo {
    private static final int MAX_PAYLOAD = 1_000_000;

    static void writeText(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_PAYLOAD) {
            throw new IOException("Payload too large");
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String readText(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid payload length: " + length);
        }
        byte[] bytes = new byte[length];
        in.readFully(bytes);

        // Strict decoding: reject invalid UTF-8 bytes.
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new IOException("Invalid UTF-8 payload", e);
        }
    }

    public static void main(String[] args) throws IOException {
        String text = "A".repeat(70_000);
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(buffer)) {
            writeText(out, text);
        }

        byte[] record = buffer.toByteArray();
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(record))) {
            String recovered = readText(in);
            System.out.println("Payload bytes: " + (record.length - 4));
            System.out.println("Record bytes: " + record.length);
            System.out.println("Round trip: " + text.equals(recovered));
        }
    }
}
```

Compile/run:

```bash
javac LongTextFrameDemo.java
java LongTextFrameDemo
```

Expected stdout:

```text
Payload bytes: 70000
Record bytes: 70004
Round trip: true
```

Important details:

1. `getBytes(StandardCharsets.UTF_8)` encodes into **standard UTF-8**. NUL bytes will be `00` and emojis typically use 4 bytes — differing from Modified UTF-8.
2. `writeInt` writes a 4-byte prefix (big-endian) representing the **payload byte count**, not `String.length()`.
3. `readInt` reads the size, **checks non-negativity and maximum limit**, then `readFully` reads the exact byte count; if bytes are missing, `readFully` throws `EOFException`.
4. A decoder with `REPORT` rejects corrupted UTF-8 byte sequences; for instance, preventing silent character replacement when valid data is mandatory.
5. `MAX_PAYLOAD` is an **application-defined limit**, reducing the risk of huge memory allocations from untrusted message lengths. It does not mean a one-million-byte buffer is automatically safe in every system.
6. The example gathers data into a `byte[]` because the size is small and bounded. If content spans hundreds of MB/GB, design streaming, chunking, and size controls instead of creating one gigantic byte array.

If the protocol is already fixed by an external library or spec, you **cannot unilaterally switch `writeUTF` to `writeInt + write`** while keeping compatibility. Reader, writer, and wire-format docs must all be updated together.

## 9. How Does `writeUTF` Differ from Other String-Writing Methods?

| Write Method | Written Data Form | Has Own Length? | Key Limits |
| --- | --- | --- | --- |
| `DataOutputStream.writeUTF(s)` | Modified UTF-8 | **Yes: 2 bytes** | Max 65,535 payload bytes |
| `DataOutputStream.writeChars(s)` | Each `char` as 2 bytes, high byte first | **No** | No 65,535-byte `writeUTF` limit; reader must know char count |
| `DataOutputStream.writeBytes(s)` | Only low byte of each `char` | **No** | Can lose Unicode data |
| `out.write(s.getBytes(UTF_8))` | Standard UTF-8 | **No** | Must manage framing/length |
| `out.writeInt(n); out.write(bytes)` | Application-defined | **Yes: 4 bytes** | Bound by int range, memory, and app limits |
| `OutputStreamWriter(out, UTF_8)` | Chars → Standard UTF-8 | Not a `writeUTF` record | Manage text/resource boundaries |

`writeBytes(String)` is usually **not** the right choice for writing Unicode because it only uses the low byte of each `char`. `writeChars(String)` keeps each `char` unit as two bytes, yet provides no length prefix; the reader needs a separate contract, e.g., calling `readChar()` the exact number of times. Do not treat these methods as ways to "bypass the limit while preserving `writeUTF`'s output".

For text-exchange files (UTF-8), you can use `Files.writeString(path, text, UTF_8)` or `BufferedWriter` instead of designing custom binary records. For binary protocols read by `DataInputStream`, pick a clear wire format with explicit framing.

## 10. Practical Questions About the Limit

### 10.1. Is `"A".repeat(65535)` Valid?

Yes, because each `A` is 1 byte in Modified UTF-8, making the payload exactly 65,535 bytes, and the two prefix bytes are `FF FF`. Total record bytes equal 65,537.

### 10.2. Does Java Automatically Truncate `"A".repeat(65536)` to 65,535 Bytes?

No. `writeUTF` **throws `UTFDataFormatException`**. It does not truncate, does not split into two records, and does not write a number larger than 65,535 into the 2-byte length field.

### 10.3. Is `String.length() == 30000` Guaranteed to Succeed?

No. If all `char`s encode to 3 bytes, payload = 90,000 bytes, exceeding the limit. If all are non-NUL ASCII, payload = 30,000 bytes, valid.

### 10.4. What About Strings Containing Vietnamese?

Several Vietnamese letters in UTF-16 fall in `U+0080..U+07FF` and typically take **2 bytes**; some combining marks or other characters can take **2–3 bytes** per `char` unit. Never deduce byte length from visible character count alone. Count per `char` or let `writeUTF` check.

### 10.5. Are Emojis 4 Bytes Like in Ordinary UTF-8?

Not in `writeUTF`. An emoji like `😀` has two UTF-16 surrogate units and typically requires **6 bytes** in Modified UTF-8. However, when using `StandardCharsets.UTF_8` for standard text encoding, this code point takes 4 bytes.

### 10.6. Is the Prefix `FF FF` a Negative Number If Read with `readShort()`?

It would be interpreted as `-1` if read with `readShort()`, because `short` is a signed type. `DataInputStream.readUTF()` interprets the prefix per format, equivalent to reading an **unsigned short**. If you ever inspect the length manually, use `readUnsignedShort()` and do not confuse it with `readShort()`.

### 10.7. Can `readUTF` Read Bytes Produced by `writeInt + UTF-8`?

No. `readUTF` expects **2-byte length + Modified UTF-8**, whereas the custom format above uses **4-byte length + standard UTF-8**. Even though a short ASCII string might look similar in the payload portion, the record framing differs and the decoder can misread offsets.

### 10.8. Can `writeUTF` Write Large JSON or Long HTML Text?

Only if the entire Modified UTF-8 encoded content does not exceed 65,535 bytes **and** the reader understands that exact format. For JSON/HTTP/general text, it is usually better to use standard UTF-8 and protocol-appropriate framing rather than relying on `writeUTF`.

## 11. Common Mistakes

| Mistake | Consequence | How to Avoid |
| --- | --- | --- |
| Treating `s.length() <= 65535` as sufficient | Strings with multi-byte chars still exceed limit | Compute Modified UTF-8 bytes |
| Computing `s.getBytes(UTF_8).length` as `writeUTF` size | Wrong for NUL/emojis | Compute per `char` in Modified UTF-8 |
| Subtracting 2 from 65,535 for the prefix | Misunderstands maximum threshold | 65,535 is payload only; total max is 65,537 |
| Treating `writeUTF` like raw UTF-8 `write` | Reader misreads bytes, charset/framing errors | Pair with `readUTF` |
| Using `new String(payload, UTF_8)` on Modified UTF-8 | NUL and surrogates may decode wrongly | Use `DataInputStream.readUTF()` |
| Assuming over-limit strings are truncated | No valid record is written | Catch `UTFDataFormatException` and handle explicitly |
| Calling `writeUTF` multiple times and `readUTF` once | Only one record is read | Design record counts/sequences |
| Splitting `String` blindly at 65,535 chars | May split a surrogate pair or still exceed byte cap | Count bytes and determine valid chunks |
| Switching one end to `writeInt + UTF_8`, leaving `readUTF` on the other | Protocol breaks | Upgrade wire format in sync |
| Reading 4-byte external length and allocating immediately | Risk of excessive memory allocation | Validate non-negative/max before `new byte[length]` |
| Confusing `EOFException` on read with `UTFDataFormatException` | Misdiagnoses record failure | EOF = missing bytes; format = invalid Modified UTF-8 |
| Using `writeBytes` to preserve Unicode | Loses high byte of each `char` | Use UTF-8/appropriate encoding |
| Assuming any I/O error rolls back the stream | Record may be partially written | Design application-level transactions/framing/recovery |

## 12. Self-Check Exercises

1. **What is the limit of `writeUTF`?** 65,535 **Modified UTF-8 payload bytes**, excluding the 2 prefix bytes.
2. **Can a string of 65,535 `'A'` characters be written?** Yes; 65,535-byte payload, 65,537-byte total record.
3. **Can a string of 32,768 NUL characters be written?** No; it requires 65,536 Modified UTF-8 bytes.
4. **Why does `"😀".repeat(10923)` fail?** Each emoji uses 6 Modified UTF-8 bytes, totaling 65,538 bytes.
5. **What does the prefix `FF FF` mean?** Unsigned payload length of 65,535 bytes; not `-1`.
6. **Which method reads a `writeUTF` record compatibly?** `DataInputStream.readUTF()` (or a compatible `DataInput.readUTF` API).
7. **Is `StandardCharsets.UTF_8` the charset of `writeUTF`?** No; `writeUTF` uses Modified UTF-8 under the `DataOutput` contract.
8. **What if a string is too long yet all data must be kept?** Design a format supporting larger lengths (e.g., `int` prefix and standard UTF-8), or split records using framing agreed by both ends.
9. **Does `UTFDataFormatException` only occur when writing overly long strings?** No; reading malformed Modified UTF-8 content can also throw this exception.
10. **Can `getBytes(UTF_8).length` check the Modified UTF-8 limit?** No, because NUL, surrogates, and emojis have different sizes.

## Official Java 17 Documentation

- [`DataOutput.writeUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html#writeUTF(java.lang.String)).
- [`DataOutputStream.writeUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html#writeUTF(java.lang.String)).
- [`DataInput.readUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html#readUTF()).
- [`DataInputStream.readUTF` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html#readUTF()).
- [`UTFDataFormatException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html).
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).

**Practical conclusion:** Use `writeUTF` when data must match a Java binary protocol with `readUTF` and **the Modified UTF-8 payload is at most 65,535 bytes**. To write longer text or interoperate with systems using standard UTF-8, choose a format with an appropriate length prefix/framing and validate length when reading.
