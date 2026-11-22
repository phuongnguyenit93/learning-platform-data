# Reading and Writing char[], String, and Data Chunks in Java Character Streams

## 1. Objectives and Big Picture

In Java I/O, **character streams** (`Reader` and `Writer`) allow applications to read and write text content in Java `char` units. When data may be long, arrive slowly, or be split into multiple parts, we typically use a **`char[]` array as a buffer** instead of reading the entire text into a single `String`.

This article addresses practical questions:

- How many characters does `Reader.read(char[])` read in one call? Why must you not assume the array is always full?
- How do `char[]`, `String`, and `StringBuilder` play different roles when storing, processing, and writing data?
- What do `off` and `len` in `read`/`write` mean? How do you avoid confusing a start index with an end index?
- How do you copy text in chunks without appending old characters, losing data, or corrupting content?
- When do you need to pay attention to Unicode, charsets, buffering, and closing streams?

A typical data flow:

~~~text
Text source (file or string)
          │
          ▼
      Reader
          │ read(char[], off, len)
          ▼
   Reused char[] buffer
          │ write(char[], 0, count)
          ▼
      Writer
          │
          ▼
Text destination (file or memory)
~~~

`Reader` and `Writer` operate on **Java characters**; if the actual input or output is a file or network connection, bytes are decoded/encoded via a charset at the I/O boundary. `char[]` is just an intermediate memory buffer. Reading in chunks keeps memory usage bounded, independent of document length.

## 2. Three Ways to Represent Text: char[], String, and Character Streams

| Component | Role | Key Takeaways |
| --- | --- | --- |
| `char` | A 16-bit UTF-16 code unit | Does not always represent a full Unicode character in the sense of a code point |
| `char[]` | Mutable character array of fixed length | Can be reused as a buffer; old positions do not disappear automatically |
| `String` | Immutable text string | Suitable for collected text segments or parameters to pass around |
| `StringBuilder` | Mutable in-memory character accumulator | Suitable when concatenating multiple chunks into a final string |
| `Reader` | Abstract class interface for receiving characters sequentially | `read` may return fewer than requested; `-1` means end of data |
| `Writer` | Abstract class interface for sending characters to a destination | `write` does not return the number of characters written; may throw `IOException` |

For example, the expression `new char[1024]` creates an array holding 1024 `char` units. Each read pass may overwrite only the beginning of the array. If a single read gets only 7 units, **only the first 7 elements are new data from that pass** when using `read(buffer)`.

`String` cannot be mutated in place. If you need to turn the newly read portion into a string, use `new String(buffer, 0, count)`; this string contains **exactly `count` elements**. Avoid `new String(buffer)` when only part of the array is valid, because the string may then include leftover characters or unwritten `\u0000` values.

When processing large data, it is not necessary to create a `String` on every read: you can pass `char[]` directly from `Reader` to `Writer`, or process the valid portion and write it. Repeatedly concatenating `result += chunk` can create many intermediate `String` objects.

## 3. Reading Contract: Reader.read() and Reader.read(char[])

### 3.1. Reading a Single char Unit

`Reader.read()` returns an `int`:

- A non-negative value represents a single character unit read (0–65535).
- `-1` represents **end of stream** (EOF).
- I/O errors are normally signaled with `IOException`.

`int` is used instead of `char` so that the `-1` sentinel can be preserved:

~~~java
int codeUnit;
while ((codeUnit = reader.read()) != -1) {
    char ch = (char) codeUnit;
    // Process ch.
}
~~~

This is an illustrative snippet: `reader` is an already-opened `Reader` and must be closed according to ownership rules. Reading one unit at a time is easy to understand, but it is usually not optimal for large streams compared to reading into an array.

### 3.2. Reading into an Array

`read(char[] cbuf)` can read **at most** `cbuf.length` characters; the return value is the number of elements actually filled with new data, or `-1` if the stream has ended. For a positive requested length, the `Reader` contract waits until data, EOF, or an error occurs, but **does not promise to read the entire requested length**.

~~~java
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer)) != -1) {
    writer.write(buffer, 0, count);
}
~~~

In this illustrative snippet, `reader` and `writer` are objects created externally. The line `writer.write(buffer, 0, count)` is the key point: **write only the slice of data just read**.

The `count` values can vary:

~~~text
Buffer length 4; source "ABCDEFGHIJ"

Pass 1: count=4, new data ABCD
Pass 2: count=4, new data EFGH
Pass 3: count=2, new data IJ; remaining two slots may still hold GH
Pass 4: count=-1, EOF
~~~

If pass 3 called `writer.write(buffer)`, the two old elements could be written too, producing `IJGH`. If `new String(buffer)` were called and appended to the result, the same bug would occur.

### 3.3. Empty Array Case

`read(new char[0])` requests reading 0 elements and can return `0` immediately, even before EOF. Therefore, **do not use a zero-length buffer** in a normal read loop. Even with a positive-length buffer, you should write your algorithm based on the actual character count returned rather than guessing from buffer size or file size.

Reading a character stream can block the thread when data is not yet available. Do not use `reader.ready() == false` to conclude EOF: `ready()` only indicates whether the next read can proceed without blocking under the class contract; it does not mean all data has been read.

## 4. Read Range: read(char[] buffer, int off, int len)

The three-parameter form allows writing into **a slice** of the destination array:

~~~java
int count = reader.read(buffer, off, len);
~~~

- `buffer` is the array receiving the data.
- `off` is the **starting** index in the array (0-based).
- `len` is the **maximum number of characters to read**, not an ending index.
- The return value `count` is the actual number of characters read, or `-1` at EOF when the request has a positive length.

Validity conditions: `off >= 0`, `len >= 0`, and mathematically `off + len <= buffer.length`. To avoid integer overflow when checking manually, you can evaluate `off <= buffer.length` and then `len <= buffer.length - off`.

A standalone example illustrating where data is placed:

~~~java
import java.io.StringReader;
import java.util.Arrays;

public class ReadSliceDemo {
    public static void main(String[] args) throws Exception {
        char[] destination = {'_', '_', '_', '_', '_'};

        try (StringReader reader = new StringReader("ABC")) {
            int count = reader.read(destination, 1, 3);
            System.out.println("count=" + count);
            System.out.println(Arrays.toString(destination));
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ReadSliceDemo.java
java ReadSliceDemo
~~~

Output:

~~~text
count=3
[_, A, B, C, _]
~~~

Two things to note: data is placed only at indices 1 through 3; the two elements outside the read range are untouched. If `count` were 2, the valid new slice would only be `destination[1]` and `destination[2]`. When writing it onward, use `writer.write(destination, 1, count)`, **not** `writer.write(destination, 1, 3)` using the requested length.

Reading with `off` and `len` is useful when an array contains multiple regions, when appending after existing content, or when a processing protocol allows writing only into a specific slice. In whole-stream copying examples, `read(buffer)` is more concise.

## 5. Writing char[], String, and Slices

### 5.1. Writer.write(char[])

`writer.write(charArray)` writes the **entire array**, from index 0 to `charArray.length - 1`. This method is appropriate when every element is meaningful.

`writer.write(charArray, off, len)` writes only `len` elements starting at `off`. This is the right approach when the array holds only `count` valid characters from a read pass.

~~~java
char[] chars = {'J', 'a', 'v', 'a', '!', '?'};

writer.write(chars, 0, 5); // Writes "Java!"
writer.write(chars, 2, 3); // Writes "va!"
~~~

This snippet is illustrative with an already provided `writer`. `write` returns `void`; if the operation fails, it throws an error instead of returning a count of characters written. Do not assume `write` adds a line terminator automatically; if a line break is needed, write `"\n"`, `System.lineSeparator()`, or use a line method suited to your purpose.

### 5.2. Writer.write(String)

`writer.write(text)` writes the entire `String`. `writer.write(text, off, len)` writes the exact slice starting at index `off` with length `len`, also measured in **UTF-16 units**.

Example:

~~~java
writer.write("abcdef", 2, 3); // "cde", not "c"
~~~

Because the last parameter is a **length**, not an ending index. Compare with `String.substring(beginIndex, endIndex)`: the last parameter of `substring` is an exclusive index, so `"abcdef".substring(2, 3)` produces only `"c"`. Confusing these two contracts can drop or over-write characters.

### 5.3. How append Differs from write in Index Pairs

`writer.append("abcdef", 2, 5)` uses `start` and `end` (exclusive end), per the `Appendable` contract; the result is `"cde"`. Conversely, `writer.write("abcdef", 2, 5)` requests **5** units starting at index 2, exceeding the 6-character string and failing as invalid.

| Call | Parameter Interpretation | Slice Taken |
| --- | --- | --- |
| `write("abcdef", 2, 3)` | off=2, len=3 | `cde` |
| `append("abcdef", 2, 3)` | start=2, end=3 | `c` |
| `"abcdef".substring(2, 3)` | begin=2, end=3 | `c` |
| `write(new char[]{'a','b','c'}, 1, 2)` | off=1, len=2 | `bc` |

**Do not reuse a variable named `end` for the `len` parameter without converting it first**; choose names like `offset`, `length` or `start`, `endExclusive` to make the meaning clear.

### 5.4. Runnable Example on Writing Slices

~~~java
import java.io.StringWriter;

public class WriteSliceDemo {
    public static void main(String[] args) throws Exception {
        try (StringWriter writer = new StringWriter()) {
            writer.write("abcdef", 1, 3);           // bcd
            writer.write(new char[]{'1','2','3','4'}, 1, 2); // 23
            writer.append("XYZ", 1, 3);             // YZ
            System.out.println(writer.toString());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 WriteSliceDemo.java
java WriteSliceDemo
~~~

Output:

~~~text
bcd23YZ
~~~

`StringWriter` writes to an in-RAM character buffer, so the example runs without opening a file. `StringWriter.close()` has no effect that discards accumulated content; with `FileWriter` or a `Writer` attached to a file/socket, closing the resource is much more critical.

## 6. Copying in Chunks and Reusing the Buffer

The foundational technique when processing large text is a loop:

1. Create a fixed-size character array with **positive length**.
2. Read into the array; obtain `count`.
3. If `count == -1`, stop because EOF has been reached.
4. Process or write **exactly `count` characters**; do not touch the remainder.
5. Repeat until the end of data, then close resources according to ownership.

A complete example where you can observe the element count per read:

~~~java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;

public class CharChunkDemo {
    public static void main(String[] args) throws Exception {
        try (Reader reader = new StringReader("abcdefg");
             Writer writer = new StringWriter()) {

            char[] buffer = new char[3];
            int count;

            while ((count = reader.read(buffer)) != -1) {
                System.out.println("read=" + count
                        + " segment=" + new String(buffer, 0, count));
                writer.write(buffer, 0, count);
            }

            System.out.println("result=" + writer);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CharChunkDemo.java
java CharChunkDemo
~~~

Exact output:

~~~text
read=3 segment=abc
read=3 segment=def
read=1 segment=g
result=abcdefg
~~~

On the last pass, the physical array may hold `g` alongside leftover characters from the previous pass, yet `new String(buffer, 0, 1)` and `write(buffer, 0, 1)` use only `g`. Because `StringReader` reads from already-present memory, this example has predictable chunking; with real file or network streams, the number of characters per read can vary across passes and environments.

You do not need to clear the array with `Arrays.fill(buffer, '\0')` after every read to ensure data correctness, as long as your algorithm strictly respects `count` and never reads the stale region. Depending on sensitive data requirements, clearing after use may be a separate requirement, but it does not replace the rule of reading/writing by valid length.

### 6.1. If You Need to Accumulate into a String

When you genuinely need to collect the full content for in-memory processing:

~~~java
StringBuilder result = new StringBuilder();
char[] buffer = new char[1024];
int count;

while ((count = reader.read(buffer)) != -1) {
    result.append(buffer, 0, count);
}

String text = result.toString();
~~~

This illustrative snippet uses an existing `Reader reader`. `StringBuilder.append(char[], off, len)` also takes `off` and `len`. The ability to hold all data depends on heap memory. For large files, streaming directly from Reader to Writer or processing each block directly is usually more appropriate.

To capture a string from a known small source, `StringWriter` is also an in-memory option. Utility APIs such as `Reader.transferTo(Writer)` (Java 10+) can automatically transfer all data and return the number of `char` units transferred; it **does not close** the Reader and Writer, so lifecycle management is still needed outside.

## 7. Java 17 Example: Reading and Writing a Text File in char[] Chunks

The following example creates a temporary directory, writes UTF-8 text as source data, then copies it using `BufferedReader` and `BufferedWriter` across read passes. The destination is read back to verify content; all self-opened streams are closed via `try-with-resources`.

Save to **CopyTextChunksDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyTextChunksDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("char-chunks-");
        Path source = directory.resolve("source.txt");
        Path target = directory.resolve("target.txt");
        String text = "Chào Java!\nDòng 2";

        try {
            Files.writeString(source, text, StandardCharsets.UTF_8);

            long copiedUnits = 0;
            try (BufferedReader reader =
                         Files.newBufferedReader(source, StandardCharsets.UTF_8);
                 BufferedWriter writer =
                         Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {

                char[] buffer = new char[4];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    writer.write(buffer, 0, count);
                    copiedUnits += count;
                }
            }

            String copied = Files.readString(target, StandardCharsets.UTF_8);
            System.out.println("UTF-16 units: " + copiedUnits);
            System.out.println("Equal content: " + text.equals(copied));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CopyTextChunksDemo.java
java CopyTextChunksDemo
~~~

Output:

~~~text
UTF-16 units: 17
Equal content: true
~~~

Why the result is `17`: `"Chào Java!"` has 10 UTF-16 units, the newline `\n` has 1, and `"Dòng 2"` has 6. The `copiedUnits` value records the **number of `char` units**, not the number of UTF-8 bytes on disk. Accented characters in the text can occupy multiple UTF-8 bytes even though each character here uses one UTF-16 unit.

Explanation of how the program keeps data accurate:

- `newBufferedReader` decodes UTF-8 bytes from the file into a character stream; `newBufferedWriter` encodes characters back into UTF-8.
- `char[4]` is an intentionally small buffer to demonstrate chunking. In a real program, you can choose a larger buffer and benchmark performance with realistic data.
- `writer.write(buffer, 0, count)` writes the exact slice just read, including the final partially filled pass.
- After exiting `try-with-resources`, the writer has been closed and its buffered content has been flushed to the underlying stream; only then is the destination file opened for verification.
- `finally` cleans up the test files and directory. In applications requiring strong error diagnostics, handle cleanup exceptions separately so they do not mask earlier exceptions.

Because this is a **text** copy, decoding and re-encoding is intentional. If you need to preserve every byte of an arbitrary file verbatim, use a byte stream or `Files.copy`; do not arbitrarily use `Reader`/`Writer` for binary data.

## 8. Data Arriving in Multiple Parts: What Is Guaranteed?

Suppose a protocol sends the string `"HELLO"`, but only `"HE"` is available at the source at the moment of reading. `read(buffer)` may return 2; the next call returns 3. **A single read does not necessarily correspond to one message, one line, or one chunk the sender wrote.**

Therefore, assumptions like "one read gives all 100 characters" or "one read is one record" are unsafe without rules defining boundaries. There are generally three strategies:

1. **Read until EOF** when the entire source represents a single piece of content. Use a `read` loop as shown in the examples above.
2. **Read an exact specified length** when the data has a length header or the contract requires exactly N units. Loop and accumulate the count read, treating early EOF as an incomplete-data error per the contract.
3. **Read by delimiter** when data is structured into lines or delimited records. `BufferedReader.readLine()` is an API for text lines, though it strips line terminators from the result.

Illustrative snippet for a requirement to read exactly `required` `char` units:

~~~java
char[] data = new char[required];
int offset = 0;

while (offset < required) {
    int count = reader.read(data, offset, required - offset);
    if (count == -1) {
        throw new java.io.EOFException("Văn bản kết thúc trước độ dài yêu cầu");
    }
    offset += count;
}
~~~

This assumes `required` has been validated as non-negative and `reader` is valid. The snippet is not a standalone Java program. A special source could repeatedly return `0` even for a positive-length request; when working with non-standard `Reader` implementations or streams with custom contracts, design a progress check to avoid infinite loops. For Readers following the standard contract, a positive-length read normally waits until data, EOF, or an error occurs.

**Do not look for `available()` to decide how many characters to read**: that is a method on `InputStream` (byte stream), not a tool for determining final data length. Likewise, a Reader's `ready()` is not an EOF indicator.

### 8.1. Do Not Confuse "One Write" with "One Read"

The writer side might call `writer.write("HELLO")` once, yet the reader side may still receive the data in multiple parts. This is especially true with continuous data transport protocols and intermediate buffering layers. If message boundaries matter, the protocol must encode boundaries using lengths, delimiters with escaping rules, or an appropriate record structure.

## 9. Unicode: One char Is Not Always One User-Perceived Character

Java's `char` is **a UTF-16 code unit**. Most common characters such as `A` or `à` are represented by one `char` unit; many characters outside the Basic Multilingual Plane, such as certain emojis, require a **surrogate pair** of two `char` units.

Example:

~~~java
public class UnicodeUnitsDemo {
    public static void main(String[] args) {
        String text = "A😀B";
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: " + text.codePointCount(0, text.length()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnicodeUnitsDemo.java
java UnicodeUnitsDemo
~~~

Output:

~~~text
UTF-16 units: 4
Code points: 3
~~~

The string contains three code points (`A`, the emoji, `B`) but four `char` units. **A single `read(char[])` call can split data at the boundary between two surrogate units**; when copying all data sequentially without transforming it, passing it in order through an appropriate Reader/Writer preserves the sequence of code units, but if you process each chunk independently by reversing, slicing, filtering, or re-decoding, you must preserve state across chunks so you do not split a surrogate pair into detached halves.

Do not treat `count` from `read` or `Writer.write` as the number of "visible characters" or code points. To count or manipulate code points on a `String`, you can use `codePoints()` or `Character.codePointAt` as appropriate. Even a code point does not always equal a complete visible character: combining marks can attach to a preceding letter.

### 9.1. Charsets Live at the Byte Read/Write Boundary

`StringReader` and `StringWriter` only process characters in RAM; they do not choose UTF-8 or UTF-16 for files. For files, specify the charset explicitly using APIs such as:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Read char units decoded from UTF-8 bytes.
}
~~~

When data is already available as bytes, `InputStreamReader(input, UTF_8)` bridges bytes → characters; `OutputStreamWriter(output, UTF_8)` bridges characters → bytes. When source and destination charsets differ, text can be transcoded intentionally. If the read charset is wrong, `char[]` may already contain corrupted text before write logic even begins.

### 9.2. If You Must Process Chunks Independently

An algorithm like "for every chunk of 4 chars, reverse it and write immediately" can break surrogate pairs or combining marks near boundaries. The solution depends on your goal: process by code point, carry incomplete trailing units into the next chunk, or use a Unicode-aware text processor. **Buffer boundaries are a data-transfer detail, not naturally a semantic text boundary**.

## 10. Reading Lines, Preserving Line Endings, and Chunk Processing

`BufferedReader.readLine()` returns a `String` for one line and **strips the line terminator** (`\n`, `\r`, or `\r\n`) at the end. It is convenient when processing log lines, simple CSVs, or data where exact line endings do not need to be preserved.

However, in an **exact text copying** tool, reading line by line and calling `writer.write(line)` loses all line terminators. Adding `writer.newLine()` may also normalize line endings to the platform default, differing from the original source. When you need to preserve exact character content, copy using `read(char[])` and `write(char[], off, count)` as shown above.

Example input:

~~~text
alpha\r\nbeta\n
~~~

If the notation above represents data containing `\r\n` after `alpha` and `\n` after `beta`, reading and writing in `char[]` chunks preserves the exact sequence of line-ending characters. Reading with `readLine()` and calling `newLine()` can alter the representation. If the goal is to **normalize** line endings, that is intentional processing and should be stated clearly in the program contract.

## 11. Buffering, flush, and close When Writing Data in Chunks

`BufferedReader` reduces the number of fetches from the underlying source using a character buffer; `BufferedWriter` batches small writes before pushing them to the underlying layer. Even when you already have `BufferedReader` or `BufferedWriter`, using an application-level `char[]` array remains valid: it lets you operate in chunks and control the valid slice of data.

**A successful `writer.write(...)` call does not mean the data is durably on disk.** If the writer is buffered, data may still be waiting in memory.

- `flush()` pushes content currently held in the writer's buffer to the next layer according to the class contract; it does not guarantee data has been durably synced to the physical device.
- `close()` ends resource usage; with `BufferedWriter`, closing also flushes remaining buffered data to the underlying writer and closes it.
- `try-with-resources` ensures `close()` is called on both normal and exception paths; if both the `try` body and `close()` fail, the close error can be attached as a suppressed exception.
- With `StringWriter`, data lives in RAM and `close()` does not affect the content, yet consistent ownership style should still be maintained.

If a method **receives** a `Writer` from a caller, it generally should not close it unless ownership transfer is explicitly part of the contract. Closing a wrapper like `BufferedWriter` usually closes the underlying writer as well; this is especially important when the caller continues using the resource after the method returns.

## 12. Common Mistakes When Processing Chunks

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| `writer.write(buffer)` after each `read(buffer)` | The final pass may read fewer than the array length; writes leftover old elements | `writer.write(buffer, 0, count)` |
| `new String(buffer)` on every pass | Includes portions of the array without new data | `new String(buffer, 0, count)` |
| Using `len` as an end index for `write(String, off, len)` | The API expects length, not end index | Compute `len = endExclusive - start` |
| Assuming `read(buffer)` definitely fills the array | Reader may return a positive count smaller than requested | Loop until EOF or protocol length is met |
| Treating `ready() == false` as finished | "Not ready" does not mean EOF | Rely on `read() == -1` |
| Concatenating chunks with `result += chunk` | Creates many intermediate Strings, wasting memory | Use `StringBuilder` or write directly |
| Writing from `readLine()` and forgetting line breaks | `readLine` strips line terminators | Use `char[]` to preserve them or write line breaks intentionally |
| Treating every `char` as a complete code point | Emojis and non-BMP characters have surrogate pairs | Apply stateful Unicode-aware operations |
| Relying on the default charset across platforms | Accented text may decode/encode differently | Specify `StandardCharsets.UTF_8` or the format's charset |
| Not closing `BufferedReader`/`BufferedWriter` | Can leak resources or lose buffered data | Use `try-with-resources` according to ownership |
| Holding very large text in a single `String` | Consumes RAM and may exceed array/heap limits | Process directly in chunks |

### Checklist When Writing Your Own Read/Write Loop

Answer these before running your code:

1. Is the array size greater than 0?
2. Do you check for `-1` to terminate?
3. Do you use only the `[offset, offset + count)` slice just read?
4. If you must read exactly N units, do you handle early EOF?
5. If text must be preserved verbatim, do you avoid operations that alter line endings and Unicode?
6. If the source is bytes/a file, is the charset explicitly specified?
7. Who opens the Reader/Writer and who is responsible for closing it?
8. Do you distinguish UTF-16 unit counts, code point counts, and byte counts when reporting results?

## 13. Self-Check Exercises

**Exercise 1 — Partially filled buffer.** Given `char[] buffer = new char[5]`, the final read returns `2`. If you write the whole array, what happens? **Answer:** only the first two elements are new data; the last three elements may contain old data or default characters. Write only `write(buffer, 0, 2)`.

**Exercise 2 — off/len.** Given `String text = "ABCDEFGHIJ"`, what does `writer.write(text, 3, 4)` write? **Answer:** `"DEFG"`; `off=3` is the position of `D`, and `len=4` is the slice length. If you use `append(text, 3, 4)`, it writes only `"D"`.

**Exercise 3 — Unexpected EOF.** A protocol requires reading exactly 10 characters, but the Reader ends after 7. Should 7 be considered sufficient? **Answer:** no, if the contract requires exactly 10; you must report an incomplete-data error. If the goal is merely "read whatever is available," 7 characters before EOF can be a valid result.

**Exercise 4 — Unicode.** What is `"A😀B".length()`, and why? **Answer:** 4 UTF-16 units; the emoji occupies two units. If you want the code point count, use `codePointCount(0, text.length())`, which gives 3.

**Exercise 5 — Preserving line endings.** Why is `readLine` → `write(line)` not a verbatim copy algorithm? **Answer:** `readLine` strips line terminators, so the output stream never receives them; adding `newLine` manually can change the line-ending style.

**Extended practice:** Modify `CharChunkDemo` so the buffer has length 2 and the source is a string with accents/emojis; observe each read pass without assuming chunk boundaries are code point boundaries. Next, modify `CopyTextChunksDemo` to handle text containing both `\r\n` and `\n`, then compare `text.equals(copied)`. Finally, try replacing the copy loop with `reader.transferTo(writer)`, still using `try-with-resources` for both resources.

## Core Knowledge Summary

- `read(char[])` accepts up to the array size and returns the **number of character units actually read**, or `-1` at EOF. There is no guarantee that every read fills the array.
- `read(char[], off, len)`, `write(char[], off, len)`, and `write(String, off, len)` use **offset and length**; `append(CharSequence, start, end)` and `substring(begin, end)` use an **exclusive end index**.
- Reusing a `char[]` with `write(buffer, 0, count)` is the fundamental way to process long text in chunks without accidentally appending stale characters.
- `String` suits already-collected data; `StringBuilder` is for concatenating chunks in RAM; whenever possible, stream directly from Reader to Writer to avoid holding the entire content.
- `char`/`count` measure **UTF-16 units**; Unicode characters may span multiple `char` values, and buffer boundaries are not text boundaries.
- Charset, line endings, buffering, `flush`, and `close` determine correctness when data moves between memory and the filesystem.

### API Reference Documentation

- [Reader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html)
- [Writer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html)
- [BufferedReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [StringBuilder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
