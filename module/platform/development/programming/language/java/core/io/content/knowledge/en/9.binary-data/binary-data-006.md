# readUTF, writeUTF, and Modified UTF-8 in Java I/O

## 1. Reading and Writing Strings in Binary Data Formats

In Core Java, **DataOutputStream.writeUTF(String)** and **DataInputStream.readUTF()** are the API pair for writing and reading strings according to a specific binary convention. They typically appear alongside typed operations like **writeInt/readInt** and **writeBoolean/readBoolean** when a program defines its own binary protocol.

A crucial distinction: **writeUTF does not simply write standard UTF-8**. It writes **two length bytes** followed by the content encoded in **modified UTF-8** (the UTF-8 variant defined by Java DataInput/DataOutput). **readUTF** performs the reverse process.

Example:

~~~text
writeUTF("Hi") → 00 02 48 69

00 02  : payload byte count = 2 (unsigned short, big-endian)
48 69  : "Hi" content in modified UTF-8
~~~

By contrast, **"Hi".getBytes(StandardCharsets.UTF_8)** only produces **48 69**; it does **not** include the two-byte length prefix. Therefore, you cannot replace the writeUTF/readUTF pair with getBytes and new String without altering the wire format.

Article goals: understand the record layout, distinguish modified UTF-8 from standard UTF-8, check the 65,535-byte limit, classify read/write errors, and implement Java 17+ code accurately.

## 2. Binary Layout of writeUTF

When calling **DataOutputStream.writeUTF(text)**, the output written to the OutputStream has the form:

~~~text
┌─────────────────────────┬───────────────────────────────────────┐
│ unsigned 16-bit length  │       modified UTF-8 payload          │
│        2 bytes          │        exactly length bytes           │
└─────────────────────────┴───────────────────────────────────────┘
          big-endian
~~~

- **Length** is the **encoded** byte count of the content, **excluding the two prefix bytes**.
- The two length bytes are written in **big-endian**: high byte first, low byte second.
- The length range is **0 to 65,535**, corresponding to an unsigned 16-bit short.
- For an empty string, **writeUTF("")** writes exactly two bytes **00 00**.
- For **"A"**, the result is **00 01 41**.
- For **"é"** (U+00E9), the result is **00 02 C3 A9**.
- For a string consisting solely of the NUL character, the result is **00 02 C0 80**.

**String.length() is not the byte length**. Java Strings store contents as UTF-16 units; the number of modified UTF-8 bytes on the wire can be several times greater than String.length(). The length prefix is the payload byte count **after encoding**.

**DataInputStream.readUTF()** reads the two length bytes first, then consumes that exact number of payload bytes to decode into a **String**. It does not read a line, look for a text terminator, or read all remaining bytes of the stream.

## 3. How Does Modified UTF-8 Differ from Standard UTF-8?

Modified UTF-8 here encodes each **UTF-16 code unit** corresponding to a Java **char**:

| UTF-16 code unit value | Length | Byte form |
| --- | ---: | --- |
| U+0001 to U+007F | 1 byte | 0xxxxxxx |
| U+0000 or U+0080 to U+07FF | 2 bytes | 110xxxxx 10xxxxxx |
| U+0800 to U+FFFF | 3 bytes | 1110xxxx 10xxxxxx 10xxxxxx |

Here each x represents a bit taken from the code unit.

### 3.1. NUL: U+0000 Becomes C0 80

Standard UTF-8 encodes U+0000 as **00**. With Java DataOutput.writeUTF, that character is encoded as **C0 80** (two bytes). This is an **overlong** sequence under modern UTF-8 standards, so **it must not be treated as valid standard UTF-8**.

~~~text
String containing "A", NUL, "B"

Standard UTF-8 payload:      41 00 42
writeUTF modified payload:   41 C0 80 42
Full writeUTF record:        00 04 41 C0 80 42
~~~

A single NUL character makes the two encodings diverge even though the remaining ASCII bytes match.

### 3.2. Unicode Characters Outside BMP: 4 Bytes in UTF-8, 6 Bytes in Modified UTF-8

A supplementary code point such as **U+1F600** is represented in standard UTF-8 in **4 bytes: F0 9F 98 80**. A Java String represents it using a **UTF-16 surrogate pair D83D DE00**, i.e., two Java **char**s.

**writeUTF** encodes those two code units separately, 3 bytes each:

~~~text
U+1F600:
UTF-16 surrogate pair:   D83D DE00
Modified UTF-8 payload:  ED A0 BD ED B8 80    (6 bytes)
Standard UTF-8:          F0 9F 98 80          (4 bytes)
writeUTF full record:    00 06 ED A0 BD ED B8 80
~~~

After **readUTF** decodes it, it recreates the two code units in the Java String. Do not confuse **one Unicode code point** with **one Java char**.

### 3.3. When Are the Bytes Identical?

ASCII characters other than NUL are encoded in one byte just like standard UTF-8. Many BMP characters, such as **é** U+00E9, encode identically to standard UTF-8 (**C3 A9**).

However, **partial payload overlap does not make the two formats compatible**: **writeUTF** still has a length prefix and still differs on NUL/surrogates. Never use **StandardCharsets.UTF_8** as a general-purpose decoder for writeUTF payloads.

## 4. Standalone Java 17+ Example: Hex Representation and Round-Trip

Save file **ModifiedUtfDemo.java** with the following code:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class ModifiedUtfDemo {
    public static void main(String[] args) throws IOException {
        String first = "A" + '\0' + '\u00E9';
        String supplementary =
                new String(Character.toChars(0x1F600));

        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeUTF(first);
            out.writeUTF(supplementary);
        }

        byte[] wire = memory.toByteArray();
        System.out.println("wire=" + HexFormat.of().formatHex(wire));
        System.out.println("wireLength=" + wire.length);

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(wire))) {
            String a = in.readUTF();
            String b = in.readUTF();
            System.out.println("firstEqual=" + first.equals(a));
            System.out.println("supplementaryEqual=" +
                    supplementary.equals(b));
        }

        byte[] standard = first.getBytes(StandardCharsets.UTF_8);
        System.out.println("standardUtf8=" +
                HexFormat.of().formatHex(standard));
        System.out.println("firstLength=" + first.length());
        System.out.println("supplementaryLength=" +
                supplementary.length());
        System.out.println("differentWire=" +
                !Arrays.equals(standard, wire));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 ModifiedUtfDemo.java
java ModifiedUtfDemo
~~~

Stdout:

~~~text
wire=000541c080c3a90006eda0bdedb880
wireLength=15
firstEqual=true
supplementaryEqual=true
standardUtf8=4100c3a9
firstLength=3
supplementaryLength=2
differentWire=true
~~~

Analysis:

- **00 05**: first string's payload is 5 bytes.
- **41**: A; **C0 80**: NUL; **C3 A9**: é.
- **00 06**: second string's payload is 6 bytes.
- **ED A0 BD ED B8 80**: surrogate pair of U+1F600.
- Entire stream: **2 + 5 + 2 + 6 = 15 bytes**.
- The first string has **3 UTF-16 chars**, yet its modified UTF-8 payload is **5 bytes**.
- The second string has **2 UTF-16 chars**, representing **one Unicode code point**.
- The standard UTF-8 encoding of the first string is **41 00 C3 A9**, **4 bytes** long, clearly different from writeUTF's wire format.

**Calling readUTF twice** accurately decodes the two records created by writeUTF. This demonstrates symmetry between the two APIs, not that the payload is standard UTF-8.

## 5. Combining writeUTF with writeInt/writeBoolean

DataOutputStream writes fields in the exact order of calls. DataInputStream must read in the **exact same order and types**. There is no automatic schema in the stream.

Save example **DataRecordDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.HexFormat;

public class DataRecordDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeInt(7);
            out.writeUTF("OK");
            out.writeBoolean(true);
        }

        byte[] raw = memory.toByteArray();
        System.out.println("hex=" + HexFormat.of().formatHex(raw));

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(raw))) {
            int version = in.readInt();
            String name = in.readUTF();
            boolean enabled = in.readBoolean();

            System.out.println("version=" + version);
            System.out.println("name=" + name);
            System.out.println("enabled=" + enabled);
        }
    }
}
~~~

Run:

~~~bash
javac DataRecordDemo.java
java DataRecordDemo
~~~

Stdout:

~~~text
hex=0000000700024f4b01
version=7
name=OK
enabled=true
~~~

Wire format in order:

~~~text
00 00 00 07     int 7, big-endian, 4 bytes
00 02           UTF payload 2 bytes long
4F 4B           two bytes of "OK"
01              boolean true
~~~

If the reader calls **readUTF()** before **readInt()**, it can interpret the first two bytes of int 7 (**00 00**) as an empty string and misread all subsequent fields. Therefore, both sides must agree on **schema, version, field order, types, lengths, and error handling**.

## 6. Length Limit: Maximum 65,535 Payload Bytes

The **writeUTF** method cannot write a string whose modified UTF-8 payload exceeds **65,535 bytes**, because the length is encoded in an unsigned 16-bit integer. If exceeded, it throws **UTFDataFormatException**.

Illustrative table:

| String Value | String.length() | Modified UTF-8 Payload | writeUTF Result |
| --- | ---: | ---: | --- |
| "A".repeat(65535) | 65,535 | 65,535 bytes | Succeeds |
| "A".repeat(65536) | 65,536 | 65,536 bytes | UTFDataFormatException |
| String of 32,767 NUL chars | 32,767 | 65,534 bytes | Succeeds |
| String of 32,768 NUL chars | 32,768 | 65,536 bytes | UTFDataFormatException |
| "é".repeat(32768) | 32,768 | 65,536 bytes | UTFDataFormatException |

**This limit is in encoded bytes, not character count**. Even when String.length() is under 65,535, the payload can still exceed the limit when many code units encode to 2 or 3 bytes.

Save file **UtfLengthLimitDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UTFDataFormatException;

public class UtfLengthLimitDemo {
    private static void test(String s) throws IOException {
        ByteArrayOutputStream target = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(target)) {
            out.writeUTF(s);
        } catch (UTFDataFormatException ex) {
            System.out.println("too long");
            return;
        }

        System.out.println("written=" + target.size());
    }

    public static void main(String[] args) throws IOException {
        test("A".repeat(65535));
        test("A".repeat(65536));
        test("\0".repeat(32768));
    }
}
~~~

Run commands:

~~~bash
javac UtfLengthLimitDemo.java
java UtfLengthLimitDemo
~~~

Stdout:

~~~text
written=65537
too long
too long
~~~

The value **65,537** consists of **65,535 payload bytes + 2 prefix bytes**. For strings exceeding the limit, DataOutputStream.writeUTF rejects the write instead of emitting a string whose prefix cannot represent its true length.

## 7. Read Errors: UTFDataFormatException, EOFException, and IOException

**DataInputStream.readUTF()** can fail for several different reasons:

| Scenario | Exception / Symptom | Explanation |
| --- | --- | --- |
| Payload invalid for modified UTF-8 decoder | **UTFDataFormatException** | Malformed encoding, missing continuation byte, or unacceptable leading byte |
| File/socket ends before receiving 2 prefix bytes | **EOFException** | Could not read the full record length |
| Prefix present, but payload shorter than declared length | **EOFException** | Truncated record |
| Error reading from underlying stream | **IOException** | Non-EOF I/O read failure |
| Reader positioned at wrong offset in stream | Wrong content or exception | Prefix may be misread from another field's bytes |

**readUTF()** is not a self-resynchronizing parser when data is corrupted. If bytes on the wire are damaged or missing, subsequent reads will be misaligned. In real applications, stop processing the malformed record, log with proper context, and decide whether to close the connection or recover according to explicit protocol rules.

If data arrives from an untrusted source, add total message size limits, version checks, field-order checks, and network-layer timeouts. The two-byte prefix bounds each individual string, yet **does not automatically bound the total record count or total bytes of the entire stream**.

## 8. Why Can't getBytes(UTF_8) Be Used Directly with readUTF?

Three flows look similar at the user level yet differ in format:

| Write Approach | Produced Data | Corresponding Reader |
| --- | --- | --- |
| **DataOutputStream.writeUTF** | 2-byte prefix + modified UTF-8 | **DataInputStream.readUTF()** |
| **text.getBytes(StandardCharsets.UTF_8)** | Standard UTF-8 bytes, no prefix | **new String(bytes, UTF_8)** or standard decoder |
| **OutputStreamWriter(..., UTF_8)** | Standard UTF-8 bytes, no automatic prefix | **InputStreamReader(..., UTF_8)** |

If the sender writes **48 69** using UTF-8 getBytes, and the receiver calls **readUTF()**, those two bytes are interpreted as **length 0x4869 = 18,537** rather than "Hi"; if fewer payload bytes follow than declared by that length, readUTF throws EOFException.

If the sender calls writeUTF to produce **00 04 41 C0 80 42** and the receiver uses String with standard UTF-8, the reader will not know to skip the prefix; moreover, **C0 80** is invalid in standard UTF-8. The result may contain control characters or replacement characters instead of the original string.

Therefore:

- Use **writeUTF/readUTF** only when both sides agree on this specific format.
- Use **StandardCharsets.UTF_8** when the protocol or file requires standard UTF-8.
- Do not merely exchange a charset name; document **framing**, prefixes, endianness, field types, and limits.

Note that formats like JSON, CSV, HTTP, or UTF-8 text files generally **do not use** the writeUTF/readUTF pair.

## 9. Need Longer Strings or Cross-Language Interoperability?

One custom-designed option is **4-byte big-endian int length + standard UTF-8 bytes**. This is not readUTF's wire format and must not be read with readUTF.

Java 17+ example with a 1 MiB maximum per record. Save as **LengthPrefixedUtf8Demo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class LengthPrefixedUtf8Demo {
    private static final int MAX_BYTES = 1024 * 1024;

    static void writeText(DataOutputStream out, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_BYTES) {
            throw new IOException("String exceeds limit");
        }
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String readText(DataInputStream in) throws IOException {
        int count = in.readInt();
        if (count < 0 || count > MAX_BYTES) {
            throw new IOException("Invalid length");
        }
        byte[] bytes = new byte[count];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(memory)) {
            writeText(out, "Hello UTF-8");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            System.out.println(readText(in));
        }
    }
}
~~~

Run commands:

~~~bash
javac LengthPrefixedUtf8Demo.java
java LengthPrefixedUtf8Demo
~~~

Stdout:

~~~text
Hello UTF-8
~~~

The example specifies an **int length counted in UTF-8 bytes**, followed by the exact UTF-8 content. **readFully** must obtain all bytes or throw an error. It uses ordinary UTF-8 Strings, not modified UTF-8.

**Security and strictness:** validate length before allocating, forbid negative lengths, and do not accept arbitrary sizes from untrusted sources. **new String(bytes, UTF_8)** normally replaces invalid byte sequences; if your protocol must **reject** any malformed UTF-8, use a **CharsetDecoder** with **CodingErrorAction.REPORT**.

For plain text that needs no length prefix, **BufferedReader/BufferedWriter** and an explicit charset are usually more appropriate. For record-based binary data, document the version and framing format for all clients.

## 10. Combining Data Streams with Buffered Streams and Resource Management

For binary files, you can layer the classes:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(1);
    out.writeUTF("Hello");
}
~~~

Read in the exact same order:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int version = in.readInt();
    String message = in.readUTF();
}
~~~

Both snippets are **illustrative fragments**, assuming a `Path` variable **path** and required **java.io** and **java.nio.file** imports. **DataOutputStream/DataInputStream** handle the binary format; **BufferedOutputStream/BufferedInputStream** merely add buffering to reduce small I/O calls.

The outermost wrapper may close the underlying stream at the end of **try-with-resources**. If the underlying stream belongs to another component or is **System.out**, do not close it while the rest of the application still needs it.

Calling **flush()** on the output pushes bytes from Java buffers to the underlying stream; it is **not equivalent** to durable disk fsync or confirmation that the receiver has processed the message. When confirmation is needed, use a protocol or durability API suited to the requirement.

Never manually read the 2 prefix bytes and then call **readUTF()** on the remaining payload: **readUTF() always expects a fresh prefix at the current position**, so it will read incorrectly.

## 11. Common Mistakes and How to Avoid Them

1. **Thinking writeUTF equals standard UTF-8.** Wrong: it has a prefix and uses modified UTF-8.
2. **Using readUTF on getBytes(UTF_8).** The reader interprets the first bytes as length, risking EOF.
3. **Using String.length() as the payload byte count.** Each UTF-16 code unit uses 1, 2, or 3 bytes.
4. **Forgetting the 65,535 encoded-byte maximum.** Strings with fewer characters can still exceed the limit.
5. **Forgetting the two length bytes are excluded from payload.** Total record size is **2 + length**.
6. **Assuming modified UTF-8 uses 4 bytes for supplementary code points.** It encodes the two surrogates separately, typically 6 bytes total.
7. **Writing NUL wrongly.** writeUTF produces **C0 80**, unlike standard UTF-8's **00**.
8. **Using little-endian length when the reader expects big-endian.** Both sides must follow the exact format.
9. **Reading fields out of order.** When writing writeInt then writeUTF, you must read readInt then readUTF.
10. **Ignoring EOFException/UTFDataFormatException.** Corrupted records are not valid strings.
11. **Failing to limit total record count / total network bytes.** writeUTF's limit applies only to a single string payload.
12. **Using readUTF as a decoder for plain UTF-8 files.** It does not fit plain text formats.
13. **Thinking flush means synced to disk.** Java buffering and durability mechanisms are distinct.
14. **Using writeUTF in an interoperable protocol without documenting the format.** Clients on other platforms may only support standard UTF-8.

## 12. Self-Check Questions

**Q1.** What is the hex output of writeUTF("Hi")?  
**Answer:** **00 02 48 69**, consisting of a 2-byte length and a 2-byte payload.

**Q2.** How is the NUL character encoded by writeUTF?  
**Answer:** **C0 80**, whereas standard UTF-8 uses **00**.

**Q3.** Why can U+1F600 occupy 6 bytes in modified UTF-8?  
**Answer:** Java String uses two UTF-16 surrogates, each code unit encoded in 3 bytes.

**Q4.** Does writeUTF("A".repeat(65535)) succeed, and how many total bytes are written?  
**Answer:** Yes, **65,537 bytes** total consisting of a 2-byte prefix and a 65,535-byte payload.

**Q5.** Why can't "é".repeat(32768) be written with writeUTF?  
**Answer:** The 65,536-byte payload exceeds the 65,535-byte limit.

**Q6.** When readUTF encounters a payload shorter than the length declared by its prefix, what is usually thrown?  
**Answer:** **EOFException**.

**Q7.** If you write writeInt(7), writeUTF("OK"), writeBoolean(true), in what order do you read?  
**Answer:** **readInt(), readUTF(), readBoolean()**.

**Q8.** Should an HTTP protocol requiring standard UTF-8 be replaced with writeUTF?  
**Answer:** No, unless that protocol specifically mandates a 2-byte length + Java modified UTF-8.

## 13. Summary

**DataOutputStream.writeUTF()** produces a record with a **2-byte unsigned big-endian length** and a **modified UTF-8 payload** of that exact byte count. **DataInputStream.readUTF()** is its symmetric counterpart, reading the prefix and decoding to reconstruct a Java String.

Most common pitfalls: modified UTF-8 **encodes NUL as C0 80**, **encodes each UTF-16 code unit**, and can take **6 bytes for a supplementary code point**, unlike standard UTF-8. The maximum payload is **65,535 bytes**. Use this method pair when both sides agree on the Java binary format; for ordinary UTF-8 text or Strings exceeding the limit, choose another codec/framing per your protocol.

### Official References

- [Oracle Java SE 17 — DataOutput.writeUTF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html#writeUTF(java.lang.String)): structure and encoding rules.
- [Oracle Java SE 17 — DataInput.readUTF](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html#readUTF()): reading rules and exceptions.
- [Oracle Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): typed output stream.
- [Oracle Java SE 17 — DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): typed input stream.
- [Oracle Java SE 17 — UTFDataFormatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UTFDataFormatException.html): modified UTF-8 string error.
