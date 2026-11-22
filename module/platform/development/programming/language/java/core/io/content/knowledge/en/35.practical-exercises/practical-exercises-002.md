# Transcoding Text Between Two Charsets with Error Checking (Java 17+)

## 1. Problem Statement and Expected Outcome

A text file contains **bytes**, not Java `char` values directly. When migrating data from a legacy system using ISO-8859-1, Windows-1252, Shift_JIS, or UTF-16 to a new system using UTF-8, the application must **decode** the source bytes into Unicode characters and then **encode** those characters into bytes of the target charset.

Practice problem:

> Convert text content from a specified source charset to a specified target charset, **without silently replacing invalid characters**. If the source bytes are malformed, or if a character cannot be represented in the target charset, report an error and **do not publish a partial output file**.

Example with ISO-8859-1 input:

```text
Source bytes (hex):       43 61 66 E9
Source charset:           ISO-8859-1
Unicode chars after decode: C a f é
Target charset:           UTF-8
Target bytes (hex):       43 61 66 C3 A9
```

This is a **transcoding** process, not renaming the file extension, copying bytes verbatim, or calling `String.replace`.

Correct flow:

```text
                  DECODE                         ENCODE
source byte[] ─────────────────▶ Unicode chars ─────────────────▶ target byte[]
  ISO-8859-1        CharsetDecoder      chars       CharsetEncoder       UTF-8
                      REPORT                           REPORT
                       │                                │
                       └── malformed                    └── unmappable
                           or unmappable error              or malformed error
```

The two error-checking stages are **independent**. Input bytes may decode validly while the resulting characters still cannot be encoded into the target charset; conversely, the target charset may support every valid character while the input bytes are already corrupted before the encoding step.

## 2. Concepts to Distinguish

| Term | Meaning | Example |
|---|---|---|
| `Charset` | Mapping rules between bytes and Unicode characters | `StandardCharsets.UTF_8` |
| `CharsetDecoder` | Converts bytes to chars with an explicit error-handling policy | UTF-8 → Unicode |
| `CharsetEncoder` | Converts chars to bytes with an explicit error-handling policy | Unicode → ISO-8859-1 |
| `CharacterCodingException` | Base exception for encoding/decoding errors | Parent of the two exceptions below |
| `MalformedInputException` | Input is structurally invalid under the encoding | UTF-8 bytes `C3 28` |
| `UnmappableCharacterException` | A valid input character/unit has no valid mapping in the target or source charset | Unicode `é` to US-ASCII |
| `CodingErrorAction.REPORT` | Reports an error instead of silently replacing/dropping | Suitable for data requiring accuracy |
| `CodingErrorAction.REPLACE` | Replaces erroneous parts with the codec's replacement string/bytes | May lose information |
| `CodingErrorAction.IGNORE` | Skips erroneous parts | Easily loses data silently |

**Distinguishing decoder and encoder errors:**

- **Malformed at decoder**: the source bytes do not form a valid code sequence. For example, the two bytes `C3 28` are not a valid UTF-8 code point.
- **Unmappable at decoder**: a byte sequence valid under the source format's structure but lacking a corresponding Unicode character in that charset's mapping; the distinction varies by charset.
- **Unmappable at encoder**: Unicode has a character that the target encoding cannot store; for example `é` or `☃` into US-ASCII.
- **Malformed at encoder**: an invalid char sequence, such as an unpaired UTF-16 surrogate in a `CharBuffer`, even when the target charset is UTF-8.

Do not use a single catch-all like `IOException` and interpret everything as "corrupt file". Preserve the details: which charset, which step, which error type, and the data position if tracked.

## 3. Why Must the Charset Be Declared Explicitly?

A byte file does not carry universal standard metadata guaranteeing which decoder is right. Statements relying on the **default charset** can produce different results across JDKs, runtime configurations, or platforms:

```java
// Avoid relying on the default charset in protocols and stored data.
new InputStreamReader(inputStream);
new OutputStreamWriter(outputStream);
```

This is an API illustration snippet assuming streams are already declared. Starting with Java 18, the JDK's default charset moved toward UTF-8 per JEP 400, yet exceptions and configurations still exist; applications reading historical data or exchanging with other systems must not expect the default to magically recognize ISO-8859-1, Windows-1252, or Shift_JIS.

**Always determine the charset origin** from contracts, trusted metadata, validated user selection, or protocol rules.

```java
Charset source = StandardCharsets.ISO_8859_1;
Charset target = StandardCharsets.UTF_8;
```

These two constants reside in `java.nio.charset.StandardCharsets` and are always supported in Java SE. If the source file actually uses Windows-1252, you can use `Charset.forName("windows-1252")` if supported by the JDK/provider; **do not assume Windows-1252 and ISO-8859-1 are identical**, especially at bytes 0x80–0x9F.

### 3.1. Is Absolute Automatic Charset Detection Possible?

No general algorithm guarantees inferring the right charset for **every** byte sequence. A byte sequence can be valid in multiple charsets while producing different text.

For example, the UTF-8 bytes for `é` are `C3 A9`. If mistakenly decoded as ISO-8859-1, the program produces `Ã©`; both bytes are valid in ISO-8859-1, so **the `REPORT` decoder throws no error**.

```text
43 61 66 C3 A9
   UTF-8      → Café
   ISO-8859-1 → CafÃ©
```

Therefore, "no exception thrown" only proves **the input is valid under the chosen charset**, **not that the charset is the true original one**. For sources with unknown charsets, you need metadata, verification workflows, or human confirmation; heuristics only provide limited confidence.

## 4. Why Convenience APIs Can Hide Bad Data

Concise statements such as:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] converted = text.getBytes(StandardCharsets.US_ASCII);
```

are valid Java syntax inside a method where `bytes` is a `byte[]` and `StandardCharsets` is imported. However, convenience APIs like these **default to a replacement policy** for parts that cannot be decoded/encoded; they do not provide detailed error reporting like `CharsetDecoder` and `CharsetEncoder` with `REPORT`.

For files requiring **lossless** transcoding, you should not rely solely on them. Similarly:

```java
Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(target, text, StandardCharsets.US_ASCII);
```

High-level methods have their own error-handling contracts (for instance, `readString` can throw `MalformedInputException` per its API); **do not infer that every convenience utility uses REPLACE**. The key point is to read the contract of the **exact overload** and choose a mechanism that actively sets `REPORT` on both **input and output** when strict verification is required.

### 4.1. Three Policies and Their Data Impact

Suppose UTF-8 input contains `C3 28`:

- `REPORT`: the decoder throws `MalformedInputException`; it does not produce a "best-guess fixed" result.
- `REPLACE`: the codec substitutes a replacement character, usually `U+FFFD` (the `�` symbol), and continues processing remaining valid bytes. The content has **changed**.
- `IGNORE`: the codec drops erroneous parts; content may **lose bytes/characters**.

Which policy is permitted is a business decision. For backups, financial data, identifiers, source files used in builds, or migrations needing verification, `REPORT` is usually the sensible default; if REPLACE/IGNORE is required, the data loss should be recorded.

## 5. `CharsetDecoder`: From Bytes to Unicode

Create a new decoder with explicit error policies:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

This is valid code inside a method, requiring imports for `CharsetDecoder`, `CodingErrorAction`, and `StandardCharsets`.

Decoding a complete `ByteBuffer`:

```java
byte[] source = {
        0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9
};

CharBuffer chars = decoder.decode(ByteBuffer.wrap(source));
System.out.println(chars);
```

This snippet belongs inside a method with `decoder` from the previous step and `ByteBuffer`/`CharBuffer` imported. The output displays `Café` when the input is valid UTF-8. The convenience `decode(ByteBuffer)` method on a **configured decoder** reports errors according to `CodingErrorAction.REPORT`.

**Invalid input example:**

```java
byte[] invalid = { (byte) 0xC3, (byte) 0x28 };

try {
    decoder.reset(); // Reset if reusing after a previous decode pass.
    decoder.decode(ByteBuffer.wrap(invalid));
} catch (MalformedInputException ex) {
    System.out.println("UTF-8 malformed");
}
```

This snippet is inside a method with a suitable decoder and `MalformedInputException` imported. In production programs, **creating a fresh decoder per operation** is usually simpler than sharing/reusing stateful decoders; never use the same `CharsetDecoder` concurrently across threads.

### 5.1. Stateful Decoders

Some charsets are stateful, and even UTF-8 can have multi-byte sequences split across I/O boundaries. Therefore, a streaming decoder must maintain state across chunks:

```text
Chunk 1: ... E2 82
Chunk 2: AC ...
                └─ three bytes E2 82 AC form the character €
```

If two UTF-8 chunks are decoded **independently** with two fresh decoders, chunk 1 may be reported as malformed/truncated and chunk 2 will also break. You must not arbitrarily split a file into byte chunks and call `new String(chunk, UTF_8)` per chunk when preserving text intact.

`InputStreamReader` is built on `CharsetDecoder` and handles reading ahead and preserving decoder state across byte chunks. This is usually a simpler choice than managing `CoderResult`/`ByteBuffer.compact` manually for streaming exercises.

## 6. `CharsetEncoder`: From Unicode to Target Charset

Output also has its own errors. For example, to encode a `String` into ISO-8859-1:

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharBuffer chars = CharBuffer.wrap("Caf\u00E9");
ByteBuffer bytes = encoder.encode(chars);
```

This snippet is inside a method with `CharsetEncoder`, `CharBuffer`, and `ByteBuffer` imported; Java processes the escape `\u00E9` as the character é.

Case where the destination cannot represent a character:

```java
CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ascii.encode(CharBuffer.wrap("Caf\u00E9"));
} catch (UnmappableCharacterException ex) {
    System.out.println("ASCII unmappable");
}
```

On Java 17+, the exact error thrown is `UnmappableCharacterException`, because US-ASCII cannot encode `é`.

**Rule:** validly reading the source **does not** mean every character can be written to the destination. UTF-8 can encode every valid Unicode scalar value; other charsets usually have narrower character sets. Converting from UTF-8 to US-ASCII or ISO-8859-1 can lose information even when the input is completely valid.

### 6.1. Does `canEncode` Replace Error Handling?

`encoder.canEncode(...)` can answer whether a character or sequence can be encoded by that encoder. However, when converting very large files, **there is no need to read the entire file into a String** just to pre-check with `canEncode`. A `CharsetEncoder` configured with `REPORT` on the write stream will detect errors when the encoder actually processes the input.

Furthermore, if the source data changes between a precheck step and the encode step, the precheck result is no longer reliable. The simple, solid approach is to run **one transcoding pipeline**, catch and report errors where they occur, and publish the target only after all decoding/encoding succeeds.

## 7. From Small Demos to Transcoding Large Files

There are two main strategies:

| Strategy | Advantages | Limitations |
|---|---|---|
| `Files.readAllBytes` → `decoder.decode` → `encoder.encode` → `Files.write` | Clear step-by-step flow, easy for learning errors, fits small bounded payloads | Must hold all bytes/chars in memory; unsuitable for large files |
| `InputStreamReader` with `REPORT` decoder + `OutputStreamWriter` with `REPORT` encoder | Streaming with a fixed char array, no need to hold the entire file | Must manage lifecycle/errors/staging; detailed error offsets require a byte counter or custom decoder |

**Simple version example for small data:**

```java
byte[] sourceBytes = Files.readAllBytes(sourcePath);

CharsetDecoder decoder = sourceCharset.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = targetCharset.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharBuffer characters = decoder.decode(
        ByteBuffer.wrap(sourceBytes));

ByteBuffer encoded = encoder.encode(characters);

byte[] result = new byte[encoded.remaining()];
encoded.get(result);

Files.write(targetPath, result);
```

This snippet is **only an illustration inside a method** with the corresponding imports, Paths/Charsets declared, and checked exceptions handled. It is not safe for arbitrarily large files; nor does it **guarantee** that the target is not partially written if an error occurs during `Files.write`. To preserve the old target file and avoid publishing broken output, use staging as in the complete example below.

## 8. Complete Practice Example: Streaming + Strict Decode/Encode + Staging

The application below converts from **ISO-8859-1 to UTF-8**, then separately tests two error branches:

1. Malformed UTF-8 source file: converting to UTF-8 is **rejected**.
2. Valid UTF-8 source file containing characters absent from US-ASCII: encoding to US-ASCII is **rejected**.

On each transcode:

- Creates fresh `CharsetDecoder` and `CharsetEncoder` instances with both error actions set to `REPORT`.
- Uses `InputStreamReader`/`OutputStreamWriter` for **streaming**.
- Reads/writes in `char[]` chunks, without loading the whole file.
- Writes to a **staging file in the same target directory**.
- Only runs `Files.move(staging, target)` **after** the streams close successfully and both decoder and encoder report no errors.
- Deletes staging when conversion fails; a target that did not exist will never appear.

**Filename:** `StrictTranscodeDemo.java`

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class StrictTranscodeDemo {

    public static void convert(
            Path source,
            Path target,
            Charset inputCharset,
            Charset outputCharset) throws IOException {

        CharsetDecoder decoder = inputCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharsetEncoder encoder = outputCharset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        // Place staging in the target's parent directory to avoid creating partial output
        // under the target name when decode/encode fails.
        Path parent = target.toAbsolutePath().getParent();
        Path staging = Files.createTempFile(
                parent, ".transcoding-", ".tmp");

        boolean published = false;

        try {
            try (Reader reader = new BufferedReader(
                        new InputStreamReader(
                                Files.newInputStream(source), decoder));
                 Writer writer = new BufferedWriter(
                        new OutputStreamWriter(
                                Files.newOutputStream(
                                        staging,
                                        StandardOpenOption.WRITE,
                                        StandardOpenOption.TRUNCATE_EXISTING),
                                encoder))) {

                char[] chunk = new char[4096];
                int n;

                while ((n = reader.read(chunk)) != -1) {
                    writer.write(chunk, 0, n);
                }
            }

            // Publish only after both reader and writer have closed successfully.
            // In this demo the target does not exist yet; move without options
            // does not guarantee atomic replacement or durability.
            Files.move(staging, target);
            published = true;

        } finally {
            if (!published) {
                Files.deleteIfExists(staging);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("transcode-");

        try {
            Path latin1 = directory.resolve("latin1.txt");
            Path utf8 = directory.resolve("utf8.txt");

            Files.write(
                    latin1,
                    "Caf\u00E9".getBytes(StandardCharsets.ISO_8859_1));

            convert(
                    latin1, utf8,
                    StandardCharsets.ISO_8859_1,
                    StandardCharsets.UTF_8);

            System.out.println(
                    "converted exact: "
                    + Files.readString(
                            utf8, StandardCharsets.UTF_8)
                            .equals("Caf\u00E9"));

            System.out.println(
                    "input bytes: " + Files.size(latin1));
            System.out.println(
                    "output bytes: " + Files.size(utf8));

            Path invalid = directory.resolve("invalid.bin");
            Path invalidTarget = directory.resolve("invalid-out.txt");

            // C3 28: malformed UTF-8 sequence.
            Files.write(invalid, new byte[]{
                    (byte) 0xC3, (byte) 0x28
            });

            try {
                convert(
                        invalid, invalidTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.UTF_8);
            } catch (MalformedInputException ex) {
                System.out.println(
                        "malformed input: "
                        + ex.getClass().getSimpleName());
            }

            System.out.println(
                    "invalid target exists: "
                    + Files.exists(invalidTarget));

            Path unicode = directory.resolve("unicode.txt");
            Path asciiTarget = directory.resolve("ascii.txt");

            Files.writeString(
                    unicode, "Caf\u00E9 \u2603",
                    StandardCharsets.UTF_8);

            try {
                convert(
                        unicode, asciiTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.US_ASCII);
            } catch (UnmappableCharacterException ex) {
                System.out.println(
                        "unmappable output: "
                        + ex.getClass().getSimpleName());
            }

            System.out.println(
                    "unmappable target exists: "
                    + Files.exists(asciiTarget));

        } finally {
            try (Stream<Path> files = Files.list(directory)) {
                for (Path file : files.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac StrictTranscodeDemo.java
java StrictTranscodeDemo
```

**Expected stdout (verified on JDK):**

```text
converted exact: true
input bytes: 4
output bytes: 5
malformed input: MalformedInputException
invalid target exists: false
unmappable output: UnmappableCharacterException
unmappable target exists: false
```

### 8.1. Step-by-Step Explanation

1. `latin1.txt` is written using `ISO_8859_1`, containing byte `E9` for the character `é`; size is 4 bytes.
2. `InputStreamReader` receives a `CharsetDecoder` with `REPORT` enabled and decodes into Unicode characters. `OutputStreamWriter` receives a `CharsetEncoder` also with `REPORT` enabled, writing in UTF-8: `é` becomes the two bytes `C3 A9`, totaling 5 bytes.
3. The code uses a `char[4096]` buffer yet still handles multi-byte characters because **the Reader/Writer maintain encoding state across read/write calls**. A new decoder is not created per chunk.
4. If the input bytes are corrupted, `InputStreamReader` throws `MalformedInputException` while reading. The try-with-resources block closes resources; because the move has not run, the target never appears.
5. With Unicode input containing `é`/`☃` and a `US_ASCII` target, the `REPORT` encoder throws `UnmappableCharacterException` during writing (or upon flush/close).
6. The `published` flag allows `finally` to delete staging in every error branch before publishing. Once moved successfully, staging no longer exists at its old path.
7. `Files.move(staging,target)` omits `REPLACE_EXISTING`; the demo uses a non-existent target. **Do not** call that behavior an "atomic commit" or "durable commit" across all OSes.
8. The demo cleans up files inside the temporary directory it created, without touching user files. If an abnormal filesystem state causes a cleanup error, the exception is surfaced; the demo does not hide failures.

### 8.2. Why Are Escapes `\u00E9` and `\u2603` Used in the Source Code?

That is Java's Unicode escape syntax for `é` and `☃`, respectively, allowing the example's source file to be saved in ASCII even when a terminal/editor uses a different charset. The program does not "force characters into ASCII"; the escapes are resolved by the Java compiler into the actual Unicode characters before the program runs.

### 8.3. What the Example Does **Not** Guarantee

- No source file authentication or limit on total input bytes/chars.
- No checksum or content manifest written.
- No guarantee that the source is not modified by another actor while being read.
- No built-in transaction or power-loss durability mechanism.
- No atomic replacement of an already-existing target file.
- Does not report the exact **byte offset** of the erroneous character in the file; the exception identifies the error type, and obtaining offsets requires a byte counter or handling `CoderResult` directly.
- Does not guard against symlink/path races if paths come from untrusted users.

This is an example of **strict transcoding and preventing publication of partial output on encoding errors**, not a full-featured production ETL tool.

## 9. Transcoding Real Files from the Command Line

When applying this to a real problem, design the program to accept:

```text
transcode <sourcePath> <targetPath> <sourceCharset> <targetCharset>
```

At the CLI layer you should:

- Parse and validate the exact argument count.
- Use `Charset.forName(name)` while handling `IllegalCharsetNameException`/`UnsupportedCharsetException` or `IllegalArgumentException` appropriately.
- Never guess the source charset if business rules specify it.
- Verify the source is a regular file, the target path lies in an allowed area, and accidental overwrites are disallowed.
- Call the `convert` logic from the example after validation.
- Print clear error messages: malformed input, unmappable output, permissions, out of disk space, existing target, or invalid path.
- Return a failing exit code and never claim the result was published if `Files.move` has not completed.

### 9.1. Helper for Handling Charset Names

```java
static Charset parseCharset(String name) {
    try {
        return Charset.forName(name);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Unsupported or illegal charset: " + name, ex);
    }
}
```

This is a helper inside a class with `import java.nio.charset.Charset`. In a real CLI program, error messages should not concatenate arbitrary untrusted input into sensitive logs without sanitization; the helper illustrates failing fast on unsupported charsets.

Some valid names include `UTF-8`, `ISO-8859-1`, `US-ASCII`, `UTF-16LE`; for Windows-1252 you can use `Charset.forName("windows-1252")` when supported by the runtime's provider. A **valid** charset name does not prove the file actually uses that charset.

## 10. UTF-8 and UTF-16: BOM, Byte Order, and Charset Selection

### 10.1. What Is a Byte Order Mark (BOM)?

Some text files begin with a BOM marker:

| Common Encoding | BOM bytes (hex) |
|---|---|
| UTF-8 | `EF BB BF` |
| UTF-16BE | `FE FF` |
| UTF-16LE | `FF FE` |
| UTF-32BE | `00 00 FE FF` |
| UTF-32LE | `FF FE 00 00` |

A BOM can provide hints about encoding or byte order, but **not every file has a BOM**, and you must not rely on a BOM to conclude encoding with certainty if the file comes from an untrusted source.

### 10.2. `UTF_16` vs. `UTF_16LE` and `UTF_16BE`

- `StandardCharsets.UTF_16` has BOM/byte-order handling semantics per the Java contract. When encoding, it may emit a BOM per charset rules; when decoding, it may use a BOM to determine byte order, falling back to its default rule if the BOM is absent.
- `StandardCharsets.UTF_16LE` and `StandardCharsets.UTF_16BE` fix the byte order. They do not convert files into UTF-8 or arbitrarily guess from a BOM.
- If a protocol requires UTF-16LE **without BOM**, select the exact charset and define a BOM policy.

Do not mix UTF-16LE bytes with a UTF-16BE decoder just because both have "UTF-16" in their names. The result can be garbled characters or a malformed-input error.

### 10.3. A UTF-8 BOM Can Become U+FEFF

If a UTF-8 stream starts with `EF BB BF`, many UTF-8 decoders represent it as the Unicode character `U+FEFF` in the data. In Java, `StandardCharsets.UTF_8` **is not considered a general BOM-stripping API**.

If you want to remove a UTF-8 BOM from an input file, define that in the format contract and handle it only at the **start of the stream**, before consuming text. Do not strip every `\uFEFF` character anywhere in the file, as that may alter valid data per the application format.

### 10.4. Newlines Also Need Their Own Policy

During charset conversion, the program may need to preserve `\r\n`, `\n`, or `\r`. The `StrictTranscodeDemo` example uses Reader/Writer with `read(char[])` and `write(char[],0,n)`, **not `readLine()`**, so it does not convert all line breaks into the OS separator.

If you use `BufferedReader.readLine()` followed by `BufferedWriter.newLine()`, you are also performing **newline conversion**, which can make the output file differ character-wise even when encoding is valid.

## 11. How Long Can One Unicode Character Be?

Distinguish between:

- **Byte**: the storage unit of a charset.
- **UTF-16 code unit (`char`)**: a Java `char` is 16 bits, not always a complete Unicode character.
- **Unicode code point**: a Unicode value; a code point outside the BMP can require **two chars** (a surrogate pair).
- **Grapheme cluster**: a visually perceived character on screen may consist of multiple code points, such as a base letter + combining mark.

Example:

```java
String snowman = "\u2603";
String emoji = "\uD83D\uDE00";

System.out.println(snowman.length()); // 1 UTF-16 code unit.
System.out.println(emoji.length());   // 2 UTF-16 code units.
```

This snippet can run inside a method; `☃` in the BMP uses one char, while the emoji 😀 outside the BMP uses two chars.

### 11.1. Why Can a Chunk Boundary Split a Surrogate Pair?

A `Reader.read(char[])` call may end immediately after the high surrogate of a non-BMP code point. `Writer`/`CharsetEncoder` holds appropriate state to process the remaining char on the next `write` call. However, **if you call `CharsetEncoder.encode(CharBuffer)` independently on each chunk**, a chunk ending with a lone high surrogate can be flagged as malformed even though the complete character spans into the next chunk.

Therefore:

- Use **one** persistent Reader/Writer pipeline across chunks, or
- Implement the `CharsetDecoder.decode`/`CharsetEncoder.encode` state machine manually with `endOfInput` and `flush` per the API.

Do not "fix" the error by replacing a trailing high surrogate at a chunk boundary with a question mark — that is self-inflicted data loss.

## 12. When Do You Need to Manage `CoderResult` Manually?

At an advanced level, you can call:

```java
CoderResult result = decoder.decode(
        inputBytes, outputChars, false);
```

This is an illustrative snippet: `decoder` is already created, `inputBytes` is a ByteBuffer, and `outputChars` is a CharBuffer; `CoderResult` must be imported.

`CoderResult` has the following cases:

- `UNDERFLOW`: the decoder needs more input or has processed all current input; at end of stream, end-of-input must be handled per contract.
- `OVERFLOW`: the output CharBuffer has no remaining space; flip/consume it and continue.
- `isMalformed()`: invalid byte sequence.
- `isUnmappable()`: valid input structure but no character mapping.
- `throwException()`: turns the error result into the corresponding `CharacterCodingException`.

When using `REPORT` with the low-level streaming API, you can track `inputBytes.position()` to compute the offending byte position relative to the window, while adding the **file offset** and retaining unprocessed bytes between chunks. This is the right path when the system must log "Malformed UTF-8 at byte offset 1,234,567" or process huge datasets with deep diagnostics.

### 12.1. Correct State Machine at End of Input

A low-level decoder cycle typically requires:

1. `decode(in,out,false)` for non-final chunks.
2. `compact()` unprocessed bytes, then read more bytes into the remaining buffer space.
3. At EOF: `decode(in,out,true)` to confirm input has truly ended.
4. `flush(out)` for any remaining state.
5. Handle `OVERFLOW` by consuming output and calling again.
6. When building a low-level encoder, perform the corresponding `encode(...,endOfInput)` and `flush` cycle.

Omitting `endOfInput=true` at EOF can prevent a truncated UTF-8 sequence at the end from being properly detected as malformed. Forgetting to preserve underflow bytes can cause false errors or replacements for characters split across two reads.

For standard exercise goals, `InputStreamReader`/`OutputStreamWriter` provide this state machine with less risk than hand-rolling a decoder loop.

## 13. Handling Errors with Appropriate Precision

### 13.1. Which Exceptions Typically Appear?

| Step | Symptom | Example |
|---|---|---|
| Input decoder | `MalformedInputException` | UTF-8 `C3 28` |
| Input decoder | `UnmappableCharacterException` | Charset has a valid byte sequence with no mapping to Unicode |
| Output encoder | `UnmappableCharacterException` | `é` → US-ASCII |
| Output encoder | `MalformedInputException` | Unpaired UTF-16 surrogate |
| Source I/O | `NoSuchFileException`, `AccessDeniedException`, `IOException` | Unable to open file |
| Target/staging I/O | `IOException` | Disk full, missing permissions, filesystem error |
| Staging publish | `FileAlreadyExistsException` or `IOException` | Target exists or move failed |

**Do not** assume every `MalformedInputException` means "the file uses another charset" — the source could genuinely be corrupted, truncated during transfer, or the application chose the wrong charset.

### 13.2. Should You Try Another Charset After an Error?

If the source format is declared as UTF-8, malformed input should be **rejected** or routed to an error queue rather than guessing another charset and continuing.

Only use a fallback when **business rules specify** an allowed set of charsets and there is a way to distinguish valid results. For example, a legacy system allows Windows-1252/ISO-8859-1 with source metadata; the code should record the applied charset and any ambiguous cases.

Never replace all malformed bytes with `?` and declare conversion 100% successful, because the data will no longer reflect the original.

### 13.3. When a Controlled Replacement Policy Is Needed

Some log-display applications may accept replacement. For example:

```java
CharsetDecoder permissive = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith("\uFFFD");
```

This is a snippet inside a method, with corresponding imports. For an encoder, replacement bytes must be valid in the target charset and usually use the default replacement byte sequence; choosing `?` may be acceptable in US-ASCII, though it cannot be treated as the original representation of unsupported Unicode.

If choosing REPLACE, you should count replacements or record them at the business layer, since `CodingErrorAction.REPLACE` **does not automatically report each error location**.

## 14. Data Integrity: What Must Be Verified?

A **correct** transcoding does not mean before/after bytes are identical. On the contrary, bytes usually differ even for the exact same text.

| Check | What It Confirms | What It Does Not Confirm |
|---|---|---|
| No exception from `REPORT` decoder | Input is valid under the chosen source charset | That the source charset is semantically the true original |
| No exception from `REPORT` encoder | Decoded Unicode can be represented by the target charset | That business content is valid |
| Decode output with target charset | Output text can be read back | Whether it is byte-for-byte identical to source |
| Compare decoded source Unicode with decoded output Unicode | Degree of character preservation per policy | Normalization/newlines/file metadata may differ |
| Compare input/output bytes | Appropriate only if encoding is the same and no transforms occur | Do not use for transcoding between different charsets |
| Byte checksum | Detects changed bytes against a reference | Does not prove source bytes were decoded with the right charset |

For critical migrations, consider writing a manifest containing source charset, target charset, size, SHA-256 checksum, record count, timestamp, and validation outcome. If business rules allow normalization, Unicode normalization rules must be applied explicitly rather than assuming encoding changes normalize text.

### 14.1. Round-Trip Testing

Test model:

```text
sourceBytes --decode(sourceCharset)--> characters
characters --encode(targetCharset)--> targetBytes
targetBytes --decode(targetCharset)--> restoredCharacters
assert characters.equals(restoredCharacters)
```

This is a good test when both encoder and decoder are strict, input is not modified concurrently, and no other transformations occur. However, a passing round trip **does not guarantee** the chosen source charset was historically right (a mojibake string can still round-trip as itself).

### 14.2. Text Transcoding vs. Binary Copying

Do not run transcoding on images, ZIPs, PDFs, class files, or arbitrary byte streams just to change an extension. `CharsetDecoder` interprets bytes as characters; binary data can contain invalid byte sequences and fail or become corrupted.

If the goal is to keep bytes unchanged, choose `Files.copy` or byte streams/`FileChannel`; if the goal is to preserve **characters** while changing byte encoding, use decoder/encoder.

## 15. Memory and Performance When Converting Large Files

### 15.1. Cost Relative to File Size

- `Files.readAllBytes` scales temporary memory with file size, plus a potentially large `CharBuffer` and target `ByteBuffer`.
- A `Reader`/`Writer` pipeline with `char[4096]` keeps application buffer memory nearly constant, independent of total characters in the file.
- Output byte size can be **smaller or larger** than source: `é` is one byte in Latin-1 but two bytes in UTF-8; conversely, converting UTF-16LE to UTF-8 has a different ratio.
- `BufferedReader`/`BufferedWriter` maintain internal char buffers as well; you can increase chunk size if benchmarks show a benefit, but never assume bigger is automatically faster.
- Encoding/decoding consumes CPU, especially when validating malformed input; throughput also depends on disk/network and charset type.

### 15.2. What If the File Has Only One Extremely Long Line?

The example reads chunks with `char[]`, **never calling `readLine()`**, so a line hundreds of MB long will not allocate a giant `String` just because newlines are absent. That is an advantage for large files with unbounded lines.

If the application must parse records after transcoding, enforce your own record length limits and handle line delimiters/CSV quoting per format rather than relying on charset conversion to cap record size.

### 15.3. Progress Tracking vs. Byte Offset Accuracy

When using `Reader`, the returned count `n` is in **UTF-16 char units**, not source bytes read. With UTF-8, you cannot sum char counts to get the exact byte offset when an error happens.

If byte-level progress is needed, you can wrap `InputStream` with a counter; however, due to buffering/read-ahead, bytes pulled from the stream do not necessarily match **the byte currently being processed by the decoder** at the instant of an exception. For exact error offsets, manage `ByteBuffer` position/`CoderResult` and unprocessed bytes manually, or design a decoder with dedicated tracking.

## 16. Safely Publishing the Target File and Handling Errors

### 16.1. Why Not Write Directly to an Important Target?

If you open the target with `TRUNCATE_EXISTING` and start writing, and halfway through the decoder encounters invalid UTF-8, the destination file has already been truncated or holds half-valid text. A failed migration can destroy an important original/target file.

```text
Direct write:
target (old version) → truncate → write 50% → MALFORMED → target is left partial

Staging write:
target (old version) ─────────── kept intact during conversion
                       staging (new version) → error → delete staging
                       or
                       complete staging → publish per policy
```

**Staging** prevents placing partial converted content under the final filename, though by itself it does not solve **atomicity, concurrency, or durability**. Separate policies are needed for overwriting, renaming, file syncing, and directory syncing if required by the application.

### 16.2. What If the Target File Already Exists?

The `StrictTranscodeDemo` example uses `Files.move(staging,target)` without `REPLACE_EXISTING` and creates new target filenames. In real applications:

- If **overwriting is forbidden**, use an appropriate create/move policy and handle `FileAlreadyExistsException`. Do not call `Files.delete(target)` first and then move, as that creates a window where the target is missing.
- If **replacement is allowed**, consider `Files.move(staging,target,REPLACE_EXISTING)`, though the move is **not** guaranteed to be atomic.
- If **atomic replacement** is required, you can attempt `Files.move(staging,target,ATOMIC_MOVE)` on a supporting provider; when `ATOMIC_MOVE` is specified, Java ignores other options, and behavior with an existing target can be **implementation-specific**.
- If **crash durability** is required, after finishing staging content you must also sync/force the file and potentially sync the directory per OS contracts before declaring committed; `Files.move` is not `fsync`.
- If multiple processes write to the same target, use ownership/locking/versioning; checking `Files.exists` alone has race conditions.

### 16.3. Cleanup Must Not Delete a Valid Target

When conversion fails, delete only the staging file created by the operation, not a pre-existing target from a previous version. When publishing succeeds, update the `published` state and do not attempt to delete staging as if it still lived at the old path.

In production applications, if staging cleanup also fails, log it and schedule orphan cleanup. Java try-with-resources can attach close errors as suppressed exceptions; when handling errors, do not lose the decoder's original exception.

## 17. Testing Important Cases

A useful test suite should include:

| Input / Scenario | Source → Target | Expected |
|---|---|---|
| Pure ASCII | UTF-8 → UTF-8 | Identical bytes and characters |
| `é` | ISO-8859-1 → UTF-8 | Byte `E9` becomes `C3 A9` |
| Accented Vietnamese text | UTF-8 → UTF-16LE | Unicode preserved when decoded back |
| Non-BMP emoji | UTF-8 → UTF-8 | Surrogate pair preserved across chunk splits |
| UTF-8 `C3 28` | UTF-8 → UTF-8, REPORT | `MalformedInputException` |
| UTF-8 multi-byte sequence missing trailing bytes | UTF-8 → UTF-8, REPORT | `MalformedInputException` at EOF |
| `é` | UTF-8 → US-ASCII, REPORT | `UnmappableCharacterException` |
| String with lone surrogate (custom char input) | Unicode → UTF-8, REPORT | `MalformedInputException` at encoder |
| UTF-8 bytes misdeclared as Latin-1 | Latin-1 → UTF-8 | May **not error** but produces mojibake |
| Empty file | Charset A → Charset B | Empty target per contract; check BOM if target charset emits one |
| Target already exists | Replacement disallowed | Must fail and preserve existing target |
| Disk full/permission denied | Any | Corrupted staging must not be published |
| Large input | UTF-8 → UTF-16 | Memory does not grow with total file size |
| Source modified while reading | Any | Must test per snapshot/ownership policy |
| Source has BOM | UTF-8/UTF-16 | Handled per chosen format contract |

### 17.1. Testing Multi-Byte UTF-8 Splitting

Prepare a string with emojis or `€` positioned near read-buffer boundaries. Convert using Reader/Writer with small chunks and compare Unicode after reading back. If you decode **each byte array independently**, this test will expose bugs where a code point spans two I/O reads.

### 17.2. Testing Failures After Partially Writing Staging

Place an unmappable character near the end of a file (e.g., over 10 MB of valid ASCII followed by `☃`, targeting US-ASCII). The encoder may already have written many bytes to staging before encountering the error. Test assertions:

- The method must throw an exception.
- The **target** still does not exist or remains the old version.
- The operation's staging file is cleaned up or explicitly logged if cleanup fails.
- No "SUCCESS/COMMITTED" log entry appears.
- Do not auto-retry with `REPLACE`/`IGNORE` when the policy is strict.

## 18. Common Mistakes

1. **Renaming `.txt` to `.utf8` and assuming the charset changed.** Bytes are untouched.
2. **Copying bytes verbatim with `Files.copy` when source/target charsets differ.** That is binary copying, not transcoding.
3. **Using the system default charset** instead of the specified charset.
4. **Confusing ISO-8859-1 with Windows-1252** in byte ranges where they differ.
5. **Assuming a detector always knows the true source charset.** Byte sequences can be valid in many encodings.
6. **Using `new String(bytes, charset)` then `getBytes(other)` expecting every error to be reported.** Many convenience overloads substitute invalid characters.
7. **Setting `REPORT` only on the decoder while forgetting the encoder.** Unmappable characters at the destination can still be silently replaced.
8. **Setting `REPORT` only on the encoder while forgetting the decoder.** Malformed source data can be lost at the read step.
9. **Using `IGNORE` to "get past errors"** when data accuracy is required.
10. **Using `REPLACE` and logging "100% lossless".** Replacement itself alters the data.
11. **Decoding each byte chunk into a separate String**, breaking UTF-8 multi-byte sequences.
12. **Encoding each `char[]` chunk with a fresh encoder**, corrupting surrogate pairs spanning boundaries.
13. **Omitting end-of-input/flush in a low-level decoder**, failing to detect malformed EOF sequences.
14. **Forgetting `ByteBuffer.flip()`/`compact()` when hand-rolling a `CoderResult` loop.**
15. **Counting bytes from `char[].length`.** UTF-8 byte counts differ from UTF-16 code units.
16. **Assuming `String.length()` equals the number of Unicode code points or visual characters.** False for surrogate pairs and combining marks.
17. **Assuming a UTF-8 BOM is always stripped automatically.** Define an explicit BOM policy.
18. **Using `UTF_16LE` when the file is actually UTF-16BE.** Wrong byte order.
19. **Using `readLine`/`newLine` in a pipeline meant to preserve exact newlines.** Can unintentionally normalize CRLF/LF.
20. **Writing directly to the target and leaving a partial target when decoding fails.** Use staging and publish after success.
21. **Deleting the old target before converting.** If conversion fails, the valid version is lost.
22. **Assuming `Files.move` without options is atomic replacement/durable.** Not promised by the API.
23. **Not checking for existing targets or concurrent writes.** Introduces races and overwrite risks.
24. **Not closing the Writer on exceptions.** Buffered encoder state/bytes may remain unflushed and resources leak.
25. **Not validating output after conversion.** Include appropriate round-trip/semantic verification.
26. **Comparing source and target bytes and flagging a bug because they differ.** Differing bytes are normal when changing charsets.
27. **Treating "no exception" as proof of the right source charset.** Mojibake can be completely valid structurally.
28. **Reading tens of GB into the heap** when streaming transcoding suffices.
29. **Sharing `CharsetDecoder`/`CharsetEncoder` across threads** without proper ownership and reset.
30. **Confusing malformed UTF-8 with unmappable target-charset errors**, leading to the wrong fix.
31. **Failing to test non-BMP characters**, testing only ASCII and missing surrogate-boundary bugs.
32. **Returning success even when cleanup/publish fails**, causing job status to misrepresent actual files.
33. **Assuming charset conversion protects against untrusted data**, skipping input size limits, path validation, and security layers.
34. **Using `InputStream.available()` as the remaining file/network size** and allocating buffers arbitrarily.
35. **Assuming `UTF-16` and `UTF-16LE` have identical BOM behavior.** Choose policies explicitly.
36. **Silently replacing unreadable characters with `?` without recording it**, erasing signs of data corruption.
37. **Allowing the source file to be modified concurrently during conversion**, producing output from an inconsistent snapshot.
38. **Catching only `IOException` and masking the specific error type**, leaving users unsure whether to fix the source charset or change the target charset.
39. **Failing to handle empty files, files without trailing newlines, or text with NUL characters**, assuming they are all corrupted text.
40. **Using raw byte CRC/checksums before/after to conclude Unicode was preserved.** Byte hashes change when encoding changes; verify according to migration semantics.

## 19. Self-Check Questions

**1.** Why isn't converting ISO-8859-1 → UTF-8 the same as `Files.copy`?  
**Answer:** `Files.copy` preserves raw bytes, whereas transcoding must decode source bytes into Unicode and re-encode them into target bytes.

**2.** What does decoding `C3 28` as UTF-8 with `REPORT` produce?  
**Answer:** `MalformedInputException`, because the byte sequence is invalid under UTF-8.

**3.** A `Café` string is valid, yet writing it to US-ASCII with a `REPORT` encoder will do what?  
**Answer:** Throw `UnmappableCharacterException`, because `é` has no US-ASCII mapping.

**4.** Where must `REPORT` be configured?  
**Answer:** On both `CharsetDecoder` and `CharsetEncoder`, for both malformed and unmappable actions when strict conversion is required.

**5.** If source bytes are UTF-8 for `é` but ISO-8859-1 is mistakenly chosen, will a `REPORT` decoder always detect it?  
**No.** It can decode as `Ã©` without error because every individual byte is valid in Latin-1.

**6.** Why is encoding each chunk with a fresh encoder a potential bug?  
**Because** surrogate pairs or charset shift state can span chunk boundaries; creating a new encoder drops state.

**7.** What unit does `Reader.read(char[])` return in `n`?  
**Answer:** The number of UTF-16 `char` units read, not necessarily source bytes or Unicode code points.

**8.** Does `CodingErrorAction.REPLACE` preserve every Unicode character?  
**No.** It substitutes replacements and can lose original information.

**9.** How many bytes are needed to convert Latin-1 `Café` from 4 bytes to UTF-8?  
**Answer:** 5 bytes (`é` changes from `E9` to `C3 A9`).

**10.** If the source has an invalid UTF-8 byte after the writer has written many bytes to staging, what should happen?  
**Answer:** Fail, close streams, clean up or handle staging per cleanup policy, and do not publish a partial target.

**11.** Does `Files.move(staging,target)` without options guarantee atomic replacement and power-loss durability?  
**No.** Separate contracts are needed for atomicity and sync/durability.

**12.** Is `UTF_16LE` identical to `UTF_16` regarding BOM?  
**No.** One fixes little-endian order; the other has specific BOM/byte-order semantics.

**13.** Why does the example use `char[4096]` without splitting and corrupting emojis during streaming?  
**Answer:** Reader and Writer with their decoder/encoder maintain state across read/write calls within the same pipeline.

**14.** After converting UTF-8 to UTF-16LE, should `Files.mismatch(source,target)` equal `-1`?  
**No.** The two byte streams use different encodings; compare Unicode after decoding.

**15.** Should `Files.readAllBytes` be used to convert a file hundreds of GBs in size?  
**No.** It allocates for the entire file and hits heap/array limits; prefer streaming.

**16.** How can you report the exact byte offset of an invalid byte in a very large UTF-8 file?  
**Answer:** Track a byte counter and `CoderResult`/ByteBuffer positions with proper underflow/overflow handling; Reader-level exceptions do not automatically provide absolute byte offsets.

## 20. Summary and Official References

**Standard formula:**

```text
[Source bytes + known source charset]
     → CharsetDecoder (malformed=REPORT, unmappable=REPORT)
     → Unicode chars (state preserved across chunks)
     → CharsetEncoder (malformed=REPORT, unmappable=REPORT)
     → Target bytes in staging
     → Clean close + validate + publish per policy
```

Key takeaway: **transcoding preserves text, not raw bytes**; check errors on both *decode* and *encode*. When the source is invalid or the target charset cannot represent a character, **report the error and avoid publishing a partial output file**. Accurate data also requires correct charset metadata, BOM/newline contracts, stateful streaming, business validation, and proper file lifecycle policies.

Java SE 21 sources:

- `Charset` — charset description, `forName`, conversion helpers: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html
- `CharsetDecoder` — `onMalformedInput`, `onUnmappableCharacter`, `decode`, `CoderResult`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- `CharsetEncoder` — `encode`, `canEncode`, handling malformed/unmappable chars: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `CodingErrorAction` — `REPORT`, `REPLACE`, `IGNORE`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html
- `InputStreamReader` — stream decoder and charset decoder constructor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html
- `OutputStreamWriter` — stream encoder and charset encoder constructor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStreamWriter.html
- `MalformedInputException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/MalformedInputException.html
- `UnmappableCharacterException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html
- `Files.move` and `Files.readString/writeString`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Unicode Standard, UTF encoding forms and BOM: https://www.unicode.org/versions/latest/
