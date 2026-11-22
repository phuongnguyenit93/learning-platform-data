# BOM, Console, Terminal, and the Origins of Garbled Characters in Java

## Objectives

When a Java program reads a Vietnamese file and prints `Tiáº¿ng Viá»‡t`, `CafÃ©`, boxes, or `�` symbols, the root cause is not necessarily the font. Character data travels through multiple layers: **bytes on disk/network → charset decoder → Java `String` → charset encoder → stdout/terminal or file → display decoder and font**. If just one layer applies the wrong convention, text can turn into *mojibake* (garbled text) or replacement characters.

A BOM (*Byte Order Mark*) is a byte marker at the **beginning of certain Unicode text formats** that helps identify UTF-16/UTF-32 byte order and is sometimes used as a UTF-8 signature. A BOM does not replace explicitly specifying the charset. Meanwhile, consoles/terminals have their own decoding, code page, and font mechanisms; the JVM's default charset is not necessarily the charset used by whatever consumes stdout.

After this lesson, you will be able to:

- Distinguish **bytes**, **Unicode code points**, **UTF-8/UTF-16**, **charset**, **BOM**, **stdout**, and **font rendering**.
- Recognize common BOM byte sequences: `EF BB BF` (UTF-8), `FE FF`, and `FF FE` (UTF-16).
- Analyze when a UTF-8 BOM becomes the `U+FEFF` character in a `String`, and why it should only be stripped at the right data boundary.
- Understand the path `System.out.println` takes to terminals, IDEs, pipelines, log files, or CI.
- Use `StandardCharsets.UTF_8` and explicit-charset read/write APIs in Java 17+.
- Recognize the limits of `Charset.defaultCharset()` and differences between JDK 17 and newer JDKs.
- Distinguish **wrong decode**, **wrong encode**, **data loss from replacement**, **double encoding**, and **missing font glyphs**.
- Write byte-level tests, compare hex/code points, use `REPORT` decoders, and fix errors at the right layer instead of “trying character replacements.”
- Determine sound fixes for files, JSON/HTTP, CSV, console windows, and build pipelines.

This lesson belongs to **Charset and I/O**. The core takeaway is not memorizing a single terminal command, but pinpointing **which side produces bytes, which charset interprets bytes, and where characters are rendered**.

## 1. The Right Model: Characters and Bytes Are Two Separate Layers

In Java, a `String` is an API-level sequence of Unicode characters. When writing to a file or byte stream, Java must **encode** the string into bytes using a charset. When reading bytes into a `String`, Java must **decode** the bytes using a charset.

```text
      Java character source               Byte destination
       String "Tiếng Việt"
              |
        encode UTF-8
              |
       54 69 E1 BA BF ...
              |
         file / socket
              |
        decode UTF-8
              |
       String "Tiếng Việt"
              |
          render/font
              v
        Characters seen by user
```

The correct path requires both writer and reader to agree on the charset, or the protocol to provide a reliable charset identification mechanism.

For example, the character `ế` has code point `U+1EBF`. When UTF-8 encoded, it becomes three bytes `E1 BA BF`. If those three bytes are read as ISO-8859-1, the result is no longer `ế`; they are interpreted as three different code points. If that misread string is forwarded and re-encoded as UTF-8, the system can produce a valid UTF-8 file **whose content is already corrupted**.

Distinguish carefully:

| Term | Meaning |
| --- | --- |
| **Unicode code point** | Numeric identifier of a character/mark, e.g., `U+1EBF` |
| **Charset** | Rules mapping between character sequences and byte sequences, e.g., UTF-8 |
| **Encoding** | Converting characters into bytes |
| **Decoding** | Converting bytes into characters |
| **BOM** | A leading byte sequence used as an identifier/byte-order marker in some encodings |
| **Mojibake** | Garbled text caused by bytes being decoded/transformed under the wrong charset |
| **Replacement character** | `U+FFFD`, commonly appearing when a decoder replaces invalid byte data |
| **Font/glyph issue** | Valid Unicode characters, yet the renderer lacks glyphs or proper shaping |

**Changing the font cannot fix a `String` already decoded into the wrong code points.** Conversely, if the `String` is right yet the font lacks characters, changing the file's charset will not solve the display problem.

## 2. UTF-8, UTF-16, and Byte Order Mark

### 2.1. UTF-8 Needs No Byte Order

UTF-8 encodes a code point in one to four bytes with a fixed structure, so there is **no big-endian or little-endian choice** per code unit as in UTF-16. Therefore UTF-8 **does not need a BOM to determine byte order**.

Some UTF-8 files are written starting with three bytes:

```text
EF BB BF
```

This is the **UTF-8 BOM**—essentially the UTF-8 representation of `U+FEFF`. It is occasionally used as a signature for software needing to recognize UTF-8. However, a UTF-8 BOM is not mandatory, and in many protocols or data tools it causes trouble by being treated as a leading content character.

For example, a CSV file with a UTF-8 BOM can cause a BOM-unaware parser to read the first column name as `"\uFEFFid"` instead of `"id"`. Humans viewing the file in an editor usually cannot see this character.

**Do not write a UTF-8 BOM out of habit.** Check whether the file/consumer contract requires a BOM. When communicating between services or storing JSON/CSV, the charset should be declared and agreed upon rather than relying on an optional byte marker.

### 2.2. UTF-16 Requires Considering Endianness

UTF-16 uses 16-bit code units. When serialized to bytes, each code unit must be written in a byte order:

- **Big-endian (BE)**: most significant byte first.
- **Little-endian (LE)**: least significant byte first.

Common BOMs for UTF-16 are:

| Form | Leading bytes | Meaning |
| --- | --- | --- |
| UTF-16BE with BOM | `FE FF` | Big-endian byte order |
| UTF-16LE with BOM | `FF FE` | Little-endian byte order |
| UTF-8 with BOM | `EF BB BF` | UTF-8 signature; unrelated to endianness |

For example, code point `U+FEFF` yields `FE FF` in UTF-16BE and `FF FE` in UTF-16LE. If software guesses the wrong byte order for UTF-16 data, it can produce different code points or decoding failures.

`StandardCharsets.UTF_16` handles UTF-16 with a BOM to determine byte order; `UTF_16BE` and `UTF_16LE` select an explicit order. Differences among these charsets affect whether a BOM is treated as metadata or as a `U+FEFF` character. Do not treat all three as interchangeable aliases.

### 2.3. UTF-32 and Other Leading Markers

UTF-32 also has BE/LE forms, with common BOMs `00 00 FE FF` (BE) and `FF FE 00 00` (LE). However, `java.nio.charset.StandardCharsets` **does not declare UTF-32 constants** as mandatory standard charsets; if code depends on UTF-32, verify actual charset/provider support before use.

This lesson focuses primarily on UTF-8 and UTF-16 since both are common in Java systems. Do not guess a file's encoding from just the first few bytes without a BOM: a byte sequence can be valid under multiple encodings. Without metadata, statistical charset detection is only a **guess**, never 100% guaranteed.

## 3. How Does Java Handle a UTF-8 BOM?

This often surprises developers: when decoding `EF BB BF` with `StandardCharsets.UTF_8`, several general Java APIs **keep `U+FEFF` as the first character of the string** instead of stripping it automatically.

Example:

```java
byte[] bytes = {
    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
    (byte) 'A', (byte) 'B', (byte) 'C'
};

String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text.length());
System.out.println((int) text.charAt(0));
```

This is a method-body snippet importing `java.nio.charset.StandardCharsets`. Output:

```text
4
65279
```

`65279` is the decimal value of `U+FEFF`. Even though a screen might look like it only displays `ABC`, `text` internally contains four code units; this string is not `equals` to `"ABC"`.

Similarly, `Files.readString(path, StandardCharsets.UTF_8)` reading a file with a UTF-8 BOM may return a string starting with `U+FEFF`. Java APIs have no universal contract to strip all BOMs for all charsets; handling depends on the decoder, library, and format.

### Stripping BOM in the Right Place

If a format **permits a UTF-8 BOM as a signature** and specifies it is not content data, you can strip **a single leading `U+FEFF`** after decoding:

```java
static String stripLeadingBom(String s) {
    return s.startsWith("\uFEFF") ? s.substring(1) : s;
}
```

This is a helper method inside a Java class, not a standalone program. Never unconditionally strip `U+FEFF` everywhere in text with `replace(...)`: if data allows meaningful formatting/control characters, that alters content.

**Important:** strip a BOM only if the *file format/application* defines the BOM as metadata. For protocols that forbid a BOM, it may be more appropriate to **reject the input** and report a clear error. Do not silently sanitize schema-violating inputs into acceptance.

### Why Does a BOM Appear Inside Header Names?

If a CSV file is:

```text
EF BB BF 69 64 2C 6E 61 6D 65 ...
BOM       i  d  ,  n  a  m  e ...
```

and the parser does not strip the BOM, the first column name becomes `"\uFEFFid"`. When code accesses `columns.get("id")`, lookup fails even though the user opens the file and sees an `id` column.

Proper handling: determine the encoding from the schema, read with the right charset, handle the BOM **at the start of the stream or file** per format rules, and only then parse CSV; do not rename columns ad hoc to mask the issue.

## 4. Origin of Garbled Text: Mojibake

A simple example:

```text
Original string:   Café
UTF-8 bytes:       43 61 66 C3 A9
Misread Latin-1:   CafÃ©
```

Here `é` is UTF-8 encoded as `C3 A9`, yet if those two bytes are decoded as ISO-8859-1/Latin-1, they become `Ã` and `©`. The result is **two wrong characters**; afterward, even displaying with a good font still shows `CafÃ©`, because the internal `String` is no longer `Café`.

With Vietnamese, a similar pattern produces fragments like `Tiáº¿ng`, `Viá»‡t`. Depending on the single-byte encoding and exact bytes, control characters or different punctuation appear; not every system produces **the exact same mojibake string**. For instance, Windows-1252 and ISO-8859-1 differ on several bytes from `80` to `9F`.

### Common Error Symptoms

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `CafÃ©`, `Tiáº¿ng` | UTF-8 bytes decoded as a single-byte charset | File hex / reading charset |
| `���` or `�` | Wrong-encoding bytes or decoder replaced malformed data | Original bytes, `CodingErrorAction` |
| `?` replacing Unicode letters | Encoder could not represent characters and substituted `?` | Writing charset, data already lost |
| Leading `ï»¿` characters | UTF-8 BOM misdecoded as Windows-1252 | Leading three bytes `EF BB BF` |
| Invisible leading `U+FEFF` | UTF-8 BOM kept after UTF-8 decode | `codePointAt(0)` |
| Editor works, terminal fails | Mismatched stdout/terminal charset or missing font glyphs | Redirect stdout to a file and inspect hex |
| File reads fine, JSON/HTTP breaks | Wrong header/schema, extra decode/encode at gateway | Raw network bytes, content type |
| Only some characters are boxes | Likely missing font/glyph | Check whether code points are still right |

This table guides investigation rather than proving root cause by sight alone. Sometimes text has been mis-encoded/decoded **multiple times**, making the garbled string look more complex.

### Wrong Decode Differs from Wrong Encode

**Wrong decode:** original bytes are right, yet interpreted into wrong characters.

```text
UTF-8 bytes of é: C3 A9
        |
decode ISO-8859-1
        v
Characters: Ã©
```

**Wrong encode or replacement:** the Java string holds the right characters, yet is written using a charset that does not support them. The encoder may replace them with byte `3F` (`?`). At that point data is lost, and the original character cannot be recovered reliably from `?` alone.

**Wrong display:** the byte stream and `String` are both right, yet the terminal/renderer uses the wrong charset or lacks glyphs in its font. This can usually be fixed at the display layer **without touching the original data**.

## 5. A Wrong Code Point Cannot Be Fixed with Normalizer

`java.text.Normalizer` handles Unicode normalization such as NFC/NFD. It resolves canonical equivalence between a precomposed character and a sequence of combining marks, such as Vietnamese `ế` vs. `e + circumflex + acute`.

However, `"CafÃ©"` is not an NFD form of `"Café"`. It contains **semantically different** code points caused by decoding with the wrong charset. Therefore:

```java
Normalizer.normalize(broken, Normalizer.Form.NFC)
```

is not a general fix for recovering mojibake text.

Sometimes a mojibake string can be “recovered” by re-encoding with the wrong charset that was used and then decoding with the original charset. Yet this is safe only when **you know the exact prior transformation and no bytes were lost**. If the system already replaced data with `?` or `U+FFFD`, or applied multiple transformation steps, exact recovery may be impossible.

**Prefer retrieving the original source bytes** and reading with the right charset; do not batch-fix by manually replacing `Ã` or `áº`.

## 6. Java 17 and Newer JDKs: How Does the Default Charset Change?

Certain Java APIs use the **default charset** when no charset is passed. On Java 17 and older JDKs, the default charset can depend on the operating system, locale, and environment settings. Thus the same program may read/write different bytes on different machines.

Starting in **JDK 18**, JEP 400 standardizes the default of relevant Java APIs to UTF-8 under the new policy, with documented compatibility options. Yet this change **does not mean all byte input/output in every Java program automatically becomes UTF-8**, nor does it prove stdout, terminals, legacy files, and external APIs are aligned.

Things to distinguish:

- `Charset.defaultCharset()` reports the runtime default charset per its contract.
- `System.getProperty("file.encoding")` may reflect default settings, yet should not be used to control every stream across the application; supported behavior depends on the JDK version.
- `System.console()` can be `null` when running in an IDE, background service, pipeline, or when stdout is redirected.
- `Console.charset()` (available in Java 17) reports the attached console's charset **when a console exists**.
- `System.out` is a `PrintStream` created by the runtime with stdout-environment mechanisms; **do not assume it always shares the same charset as `Charset.defaultCharset()`** everywhere.
- `System.err` and `System.out` may go to different destinations, each with its own write/display policy.

### An Environment Diagnostic Snippet

```java
import java.io.Console;
import java.nio.charset.Charset;

System.out.println("defaultCharset="
        + Charset.defaultCharset().name());

Console console = System.console();
System.out.println("hasConsole=" + (console != null));

if (console != null) {
    System.out.println("consoleCharset="
            + console.charset().name());
}
```

This is a method-body snippet. **No fixed stdout is shown** because output depends on the runtime environment; use it for live inspection.

If `console == null`, the program cannot infer that no display terminal exists or that stdout definitely uses UTF-8. Inside IDEs, pseudo-terminals, CI runners, or redirected commands, Java's `Console` object may not exist even though something consumes output.

Do not rely on internal system properties not guaranteed by the Java API as a portable contract to claim all stdout across all JDKs is fixed.

## 7. Console and Terminal: Which Layers Does Stdout Pass Through?

A string printed with:

```java
System.out.println("Tiếng Việt");
```

goes through at least these steps:

```text
Java source/bytecode
        |
String with Unicode code points
        |
System.out / PrintStream: encode characters to bytes
        |
stdout stream
        |
  +-------------------------+
  | terminal / IDE / CI     |
  | decode bytes to text    |
  | select font and render  |
  +-------------------------+
        |
Text seen by user
```

Additionally, if stdout is redirected:

```text
java App > output.txt
```

the bytes go into a **file**, not directly to the terminal renderer. When opening `output.txt`, the editor must also pick the right encoding. If the bytes are right yet the editor guesses the wrong encoding, you can see mojibake even though the program wrote the right bytes.

### Terminal, Shell, and Console Are Not the Same Thing

- **Shell** such as PowerShell, `cmd.exe`, or Bash parses commands, quoting, pipelines, and certain stdin/stdout conversions.
- **Terminal emulator/console host** renders glyphs, handles input/output, and may be tied to a code page.
- **JVM** encodes characters written to `System.out` into bytes before emitting to stdout.
- **Font renderer** draws glyphs from Unicode code points. Missing glyphs produce boxes even when bytes and code points are 100% right.

Thus saying “I switched the terminal to UTF-8” covers only **part** of the path; you must still check the JVM, shell, and tools in the pipeline.

### Windows: Code Pages and PowerShell

In Windows environments, the command:

```powershell
chcp
```

displays the console host's active code page in appropriate contexts; some environments allow selecting UTF-8 via `chcp 65001`. However, **a code page does not define the charset of every child program or file write operation**.

PowerShell also has version-dependent settings and differences, such as:

- `[Console]::OutputEncoding` relates to the .NET console output encoding in certain paths.
- `$OutputEncoding` can affect how PowerShell encodes text sent to a native command's stdin.
- `Out-File` and the `>` redirection operator have different encoding behaviors between Windows PowerShell 5.1 and newer PowerShell versions.
- Windows PowerShell 5.1 uses UTF-16LE with BOM by default for certain file-writing operations, while other paths use different encodings. **Do not assume every file-writing command in PowerShell 5.1 shares the same default.**

For example, piping source code or commands into a Java tool's stdin from a PowerShell pipeline can emit BOM/encoding bytes unexpected by the tool. If `U+FEFF` is parsed as a source character rather than a file marker, a parser can report `illegal character: '\ufeff'`.

There is no single Windows command guaranteed to fix every issue. Identify the **exact path**: Java output, stdin via PowerShell, redirected files, or rendered text.

### Linux, macOS, Docker, and CI

Many modern environments use UTF-8, yet never treat that as a universal contract for every container/pipeline. One process may emit UTF-8 bytes to stdout while a log collector/terminal assumes another encoding. CI may capture stdout into a file and serve it via a web UI, adding another decode layer.

When running in Docker, inspect environment metadata and how log drivers/collectors read bytes; changing `LANG` or OS locale will not automatically fix a file already misdecoded earlier.

## 8. Choosing Java APIs with Explicit Charsets

### 8.1. Recommended APIs for UTF-8 Text Files

In Java 17+, prefer:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("messages.txt");

Files.writeString(path, "Tiếng Việt", StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);
```

This is a snippet inside a method declaring or handling `IOException`. Specifying `UTF_8` states the intent clearly: independent of the JVM default charset and needing no BOM for Java to know the encoding.

`Files.writeString(path, text)` and `Files.readString(path)` already default to **UTF-8 per the API contract** since they were added in Java 11; passing the charset parameter is still recommended to make the contract explicit or stay consistent with other APIs.

Common APIs to watch:

| API | Policy to remember |
| --- | --- |
| `Files.readString(path, UTF_8)` | Explicit UTF-8 decode |
| `Files.writeString(path, text, UTF_8)` | Explicit UTF-8 encode; does not automatically add a UTF-8 BOM |
| `Files.newBufferedReader(path, UTF_8)` | Reader with explicit charset |
| `Files.newBufferedWriter(path, UTF_8)` | Writer with explicit charset |
| `new InputStreamReader(in, UTF_8)` | Decodes stream bytes to characters |
| `new OutputStreamWriter(out, UTF_8)` | Encodes characters to stream bytes |
| `new FileReader(file)` on Java 17 | Uses default charset if omitted |
| `new FileReader(file, charset)` | Uses the passed charset |
| `new String(bytes, UTF_8)` | Decodes bytes as UTF-8 |
| `text.getBytes(UTF_8)` | Encodes string as UTF-8 |

Be careful not to claim “all `Files` APIs use the default charset”: `readString`/`writeString` default to UTF-8 by contract, whereas other APIs require checking the exact overload.

### 8.2. StandardCharsets Instead of String Names

Instead of writing:

```java
new String(bytes, "UTF-8");
```

use:

```java
new String(bytes, StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` is a standard constant guaranteed by Java, avoiding typos in encoding names and making intent clear. Certain legacy charsets can be accessed via `Charset.forName("windows-1252")` if genuinely required and supported by the environment, yet never use such a charset instead of UTF-8 for new data merely because a terminal displays errors.

### 8.3. JSON, HTTP, CSV, and Properties Have Separate Contracts

Do not convert API or database text to another charset just to make a terminal look pretty.

- **Modern JSON exchange:** mandates UTF-8 per protocol and uses a standard JSON library; BOM presence/absence follows the spec. RFC 8259 requires UTF-8 for JSON exchanged outside closed ecosystems, and senders must not add a BOM.
- **HTTP:** charset can be governed by media type, specification, and `Content-Type`. Do not assume every body is UTF-8 text if another protocol says otherwise.
- **CSV:** the name CSV itself guarantees no charset; both sides must agree on charset, delimiter, escaping, and BOM policy.
- **Java `Properties`:** `Properties.load(InputStream)` has an ISO-8859-1 contract with Unicode escapes, whereas `Properties.load(Reader)` uses the `Reader`'s charset. Do not confuse these two APIs with `ResourceBundle`/`PropertyResourceBundle` resource loading on modern JDKs.
- **Database/JDBC:** pass text via character-typed APIs, configure client/server encoding and schema properly; never encode a `String` into arbitrary bytes and store them in a text column to dodge console glitches.

The charset of **stored data** and the charset of **displayed logs** must be controlled independently.

## 9. Strict Decoders and the U+FFFD Replacement Character

A byte array can be **invalid UTF-8**. For instance, bytes `C3 28` have a multi-byte leading byte followed by a byte that is not a continuation byte.

Two common policies exist:

1. **Replace errors with a replacement character** so the program still constructs text and continues displaying.
2. **Fail immediately** because data must strictly conform to UTF-8.

In Java:

```java
byte[] malformed = {(byte) 0xC3, (byte) 0x28};

String permissive = new String(
        malformed, StandardCharsets.UTF_8);

System.out.println(permissive.contains("\uFFFD"));
```

This is a method-body snippet; printing `true` shows the decoder applied replacement.

If ingestion requires **rejecting malformed UTF-8**, use `CharsetDecoder`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

try {
    StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(malformed));
} catch (CharacterCodingException ex) {
    // Reject payload that is not valid UTF-8.
}
```

This is a snippet inside a method where `malformed` is already declared. `REPORT` prevents an invalid payload from being “accepted” by silently replacing invalid bytes.

**You cannot always recover the original character from `U+FFFD`.** Once original bytes are gone and multiple different byte sequences map to the same replacement character, the information is lost. Likewise, a `3F` byte emitted by an encoder as `?` offers no reliable way to recover the original code point.

Do not arbitrarily delete every `U+FFFD` and consider the data clean; that can hide critical transmission errors.

## 10. Standalone Java 17+ Example: Bytes, BOM, and Decode Errors

This example creates a temporary file and deletes it when done, avoiding modifying project data. It prints **hex and code points** rather than relying on whether the terminal renders Vietnamese properly.

Create `CharsetAndBomDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.Locale;
import java.util.stream.Collectors;

public class CharsetAndBomDemo {
    private static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) throws Exception {
        String original = "Ti\u1EBFng Vi\u1EC7t";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 hex: "
                + HexFormat.of().formatHex(utf8));

        String correct = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 round-trip: "
                + original.equals(correct));

        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 equals original: "
                + wrong.equals(original));
        System.out.println("Latin-1 code points: "
                + codePoints(wrong));

        byte[] bom = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF
        };
        byte[] withBom = new byte[bom.length + utf8.length];
        System.arraycopy(bom, 0, withBom, 0, bom.length);
        System.arraycopy(utf8, 0, withBom, bom.length, utf8.length);

        Path file = Files.createTempFile("charset-demo-", ".txt");
        try {
            Files.writeString(
                    file, original, StandardCharsets.UTF_8);
            byte[] clean = Files.readAllBytes(file);

            boolean hasBom = clean.length >= 3
                    && (clean[0] & 0xFF) == 0xEF
                    && (clean[1] & 0xFF) == 0xBB
                    && (clean[2] & 0xFF) == 0xBF;

            System.out.println("writeString adds BOM: " + hasBom);

            Files.write(file, withBom);
            String read = Files.readString(
                    file, StandardCharsets.UTF_8);

            System.out.println("UTF-8 BOM first cp: "
                    + String.format(
                        Locale.ROOT, "U+%04X", read.codePointAt(0)));
            System.out.println("strip BOM works: "
                    + read.substring(1).equals(original));
        } finally {
            Files.deleteIfExists(file);
        }

        byte[] malformed = {
                (byte) 0xC3, (byte) 0x28
        };
        String replacement = new String(
                malformed, StandardCharsets.UTF_8);

        System.out.println("replacement occurs: "
                + replacement.contains("\uFFFD"));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("strict decoder: accepted");
        } catch (CharacterCodingException ex) {
            System.out.println("strict decoder: rejected");
        }

        byte[] utf16 = original.getBytes(StandardCharsets.UTF_16);
        System.out.println("UTF-16 header: "
                + HexFormat.of().formatHex(utf16, 0, 2));
        System.out.println("UTF-16 round-trip: "
                + original.equals(
                    new String(utf16, StandardCharsets.UTF_16)));
    }
}
```

Compile and run commands using JDK 17+:

```bash
javac -encoding UTF-8 CharsetAndBomDemo.java
java CharsetAndBomDemo
```

Verified stdout, independent of console font:

```text
UTF-8 hex: 5469e1babf6e67205669e1bb8774
UTF-8 round-trip: true
Latin-1 equals original: false
Latin-1 code points: U+0054 U+0069 U+00E1 U+00BA U+00BF U+006E U+0067 U+0020 U+0056 U+0069 U+00E1 U+00BB U+0087 U+0074
writeString adds BOM: false
UTF-8 BOM first cp: U+FEFF
strip BOM works: true
replacement occurs: true
strict decoder: rejected
UTF-16 header: feff
UTF-16 round-trip: true
```

### Exact Output Explanation

- `UTF-8 hex` is the byte sequence of `Tiếng Việt`. Letter `ế` corresponds to `E1 BA BF`; letter `ệ` corresponds to `E1 BB 87`.
- `UTF-8 round-trip: true` proves encoding and decoding with the same UTF-8 recovers the exact string.
- `Latin-1 equals original: false` and the code point list show misdecoding bytes turns them into **different characters** rather than a font bug.
- `writeString adds BOM: false` proves normal UTF-8 writing does not automatically prepend `EF BB BF`.
- When the program **explicitly prepends a BOM** and reads back as UTF-8, the first character is `U+FEFF`; stripping that leading character matches the original data.
- `replacement occurs: true` illustrates how default decoding of malformed bytes can substitute `U+FFFD`.
- `strict decoder: rejected` shows a `CharsetDecoder` configured with `REPORT` detects malformed bytes.
- `UTF-16 header: feff` proves `StandardCharsets.UTF_16` writes the default UTF-16BE BOM at the start; the matching UTF-16 decoder reads the string back.

The primary goal of the example is inspecting **bytes and code points**. If the terminal renders Vietnamese incorrectly, stdout containing hex and `U+...` values still lets you pinpoint where the data changed.

## 11. Compiling Java Sources and Source File Charset

The **source code** path must be kept separate from stdout and runtime data charsets.

```text
.java file bytes
     |
javac decodes source per encoding
     |
Class file with String constants
     |
JVM runs program
     |
System.out encodes on print
     |
Terminal decodes/renders
```

If a `.java` file contains literal Vietnamese characters (not Unicode escapes) yet `javac` reads the source with the wrong encoding, the bytecode can contain wrong characters **right from compile time**. Fixing the terminal afterward will not fix the compiled class file.

On JDK 17, the explicit option is:

```bash
javac -encoding UTF-8 Main.java
```

Ensure the source file is actually saved as UTF-8. That command only tells the compiler how to read the source; it does not convert a file from Windows-1258, UTF-16, or another legacy charset into UTF-8.

In build systems like Maven/Gradle, declare source encoding and resource-filtering charsets explicitly. Never treat a `.java` or `.properties` filename extension as proof the contents inside are UTF-8.

### Unicode Escapes in Examples Help, Yet Do Not Replace Pipeline Checks

Writing:

```java
String name = "Ti\u1EBFng Vi\u1EC7t";
```

lets the literal source stay ASCII while creating proper Vietnamese text at runtime. This reduces terminal/editor dependency in educational examples, yet you should not escape every translated string in real applications. For i18n content, prefer properly encoded resource files, reliable build pipelines, and round-trip tests.

## 12. Diagnose Layer by Layer, Never Fix by Guessing

When encountering garbled text, follow this order:

### Step 1 — Identify Where the Data Originates

The source could be:

- A text/CSV/JSON file read from disk.
- An HTTP request or response from another service.
- A database record returned via JDBC.
- A properties file or resource bundle.
- A literal compiled into a `.class` file.
- Text typed by a user via console/stdin.

You cannot provide an accurate “wrong UTF-8” diagnosis without knowing the **byte source**, sender, and declared format.

### Step 2 — Preserve Original Bytes Before Fixing

If reading a file, inspect the leading bytes and a few bytes around the garbled character. For example, in Java:

```java
byte[] raw = Files.readAllBytes(path);
System.out.println(HexFormat.of().formatHex(raw));
```

This is a method-body snippet with `path` of type `Path` and `Files`/`HexFormat` imports. For large files, print only the relevant byte window and never dump sensitive data into logs.

Seeing `EF BB BF` at offset 0 indicates a leading UTF-8 BOM; seeing `E1 BA BF` indicates bytes matching `ế` in UTF-8. Yet **a few matching bytes do not prove the entire file is valid UTF-8**: if needed, run a strict decoder across the entire payload.

### Step 3 — Decode Using the Contracted Charset

Do not pick a charset based on “this machine runs Windows” or “the file has Vietnamese text.” Choose per metadata/specification: UTF-8, UTF-16, or the legacy charset published by the data provider.

If metadata is absent, use charset detection tools as **hints** and verify against the producer and expected content; never treat statistical charset detection as infallible truth.

### Step 4 — Inspect the String Before Printing

Compare code points instead of relying solely on the console:

```java
String value = ...; // Value received from the read source
value.codePoints()
     .forEach(cp -> System.out.printf("U+%04X%n", cp));
```

This is a method-body snippet with `value` already declared. Because `U+XXXX` formatting uses ASCII, the output reveals whether the `String` holds the right characters or already contains mojibake.

If the `String` is already wrong, fix the decode/source step. If the `String` is right yet the terminal displays wrong characters, focus on the stdout encoder, terminal decoder, and font.

### Step 5 — Separate Stdout from the Terminal

Try redirecting output to a file and inspecting its hex. Note that the shell/redirection itself may apply its own encoding behavior, so for absolute verification have Java write a file directly using `Files.writeString(..., UTF_8)` and inspect the raw bytes.

If the file explicitly written by Java in UTF-8 is right while the terminal screen is wrong, do not alter data in the database. If the stdout file has wrong bytes, inspect `System.out`'s encoder or pipeline conversion layers.

### Step 6 — Check Error Replacement Mode

When encountering `�` or `?`, identify which step produced it. If a decoder or encoder substituted it, inspect the earliest source bytes. A step that already replaced data may render exact recovery impossible.

### Step 7 — Add Regression Tests

Build fixtures containing:

- Accented Vietnamese: `Tiếng Việt`, `đ`, `ắ`, `ệ`.
- Accented Latin such as `Café`.
- A non-BMP character such as an emoji to test surrogates / 4-byte UTF-8.
- UTF-8 files with and without BOM.
- UTF-16BE/LE files with BOM per supported specifications.
- Malformed UTF-8 bytes to test `REPORT`.
- Data whose first CSV column name is affected by `U+FEFF`.
- Stdout/CI redirection scenarios if the application depends on logs.

Test assertions should verify **bytes, code points, charset names, and exceptions**, not just a screenshot that looks right.

## 13. Common Wrong Fixes

### “Strip BOM Everywhere”

Wrong: a file without a BOM needs no stripping, whereas `U+FEFF` in the middle of content may require a specific policy. UTF-16 BOMs differ from UTF-8. Only strip or reject a leading BOM per the exact format and charset.

### “Just Change the Font”

If a `String` has already become `CafÃ©`, changing the font cannot restore `é`. Fonts only fix **missing glyph rendering** when code points are still right.

### “Just Change `file.encoding`”

Across JDKs, `file.encoding` and the default charset follow version-specific mechanisms; JVM runtime, console, shell, build tools, and file I/O can still be out of sync. Even when changing the default charset, calls already passing `StandardCharsets.UTF_8` keep using UTF-8; previously corrupted files do not repair themselves either.

### “Just Switch PowerShell to UTF-8”

Changing the encoding of one layer in the path does not guarantee fixing other layers, especially native stdin, stdout, file redirection, and editors reading files. Inspect actual bytes at every boundary.

### “If It Decoded to a String, It Must Be Right”

A `String` can hold Unicode-valid mojibake. A replacing decoder can return a string despite bad source bytes. API success does not prove **text semantics** were preserved accurately.

### “Broken Diacritics? Run NFC”

NFC/NFD unifies **canonical** representations of Unicode accents, not code points produced by decoding UTF-8 as Latin-1. When mojibake exists, normalizing keeps the wrong-charset error intact.

### “Reading UTF-8 Always Removes the BOM Automatically”

False for many common Java APIs: `new String(bytes, UTF_8)` and `Files.readString(path, UTF_8)` can retain `U+FEFF` in the text. Check the library/format contract and handle it deliberately.

### “Whenever You See `�`, Fix It with replaceAll”

`U+FFFD` can represent many distinct malformed situations. Deleting it masks data-loss errors. Use a strict decoder when data integrity is required and trace back to the source bytes.

## 14. Checklist for Real-World Java Projects

| Question | Approach |
| --- | --- |
| Which charset stores/exchanges data? | Document in schema, HTTP/file contracts, and tests |
| Which Java APIs read/write it? | Pass `StandardCharsets.UTF_8` or the specified charset |
| Is a BOM present? | Define policy on leading bytes; never delete all invisible characters |
| Which JVM version? | Distinguish JDK 17 defaults from JDK 18+ |
| Is the default charset used implicitly? | Avoid when data must be stable across environments |
| Does `System.console()` exist? | Do not infer all redirected stdout behavior from it |
| How do shell/terminal/CI read stdout? | Check encoder → bytes → decoder → font |
| Do `U+FFFD` or `?` appear? | Find the replacement step before information is lost |
| Does a CSV header have hidden chars? | Check leading `U+FEFF` after decoding |
| Is data ingested from legacy charsets? | Convert at the boundary where source charset is known |
| Are bytes/strings signed or hashed? | Never alter encoding or normalization outside contract |
| Is multilingual Unicode tested? | Verify bytes, code points, and round-trips |
| Do raw-byte logs contain secrets? | Avoid data leaks; log only controlled slices/snapshots |

## 15. Self-Check Exercises

**Exercise 1 — Bytes and characters.** What are the UTF-8 bytes of `é`? Why does decoding `C3 A9` as Latin-1 yield `Ã©`? Distinguish this bug from a font failing to draw `é`.

**Exercise 2 — BOM.** State the leading bytes of UTF-8 BOM, UTF-16BE BOM, and UTF-16LE BOM. Why does UTF-8 need no BOM for byte order? When can a UTF-8 BOM be considered a useful identifier, and when should it be forbidden?

**Exercise 3 — Java reading files.** Write code using `Files.readString(path, UTF_8)`. Given a file starting with `EF BB BF`, what is `codePointAt(0)`? Propose how to strip only a single leading BOM if the format allows it.

**Exercise 4 — Printf and stdout.** A Java literal has valid Unicode yet a Windows terminal displays it wrong. In what order would you inspect the `String` before printing, bytes sent through stdout, code page, font, and redirection path?

**Exercise 5 — JDK.** Compare default-charset risks on Java 17 with JEP 400 changes starting in Java 18. Why does `Charset.defaultCharset() == UTF_8` still not prove the console or all legacy files are UTF-8?

**Exercise 6 — Malformed UTF-8.** With two bytes `C3 28`, try `new String(bytes, UTF_8)` and `UTF_8.newDecoder().onMalformedInput(REPORT)`. Which can return a string containing `U+FFFD`, and which must report an error?

**Exercise 7 — CSV.** An `id,name` file has a leading UTF-8 BOM. Why might a parser fail to find the `id` column? If a product supports files both with and without a BOM, where would you place the handling step?

**Exercise 8 — Build.** A UTF-8 Java file containing Vietnamese literals is read by the compiler with the wrong charset. Is fixing the terminal's output encoding enough? Explain how to compile with `-encoding UTF-8` and test literal code points.

**Exercise 9 — Multi-layer pipeline.** A service receives UTF-8, decodes it with the wrong charset, and writes it back out as UTF-8. How can the output file be valid UTF-8 yet have corrupted text? When is fixing by re-encoding/decoding still feasible?

**Exercise 10 — Data protection.** One payload has `U+FFFD` and another has missing glyphs in a font. Do these two cases differ in data integrity? Design a test to pinpoint the cause.

## 16. Conclusion

Garbled characters are not a single terminal issue. To get accurate Vietnamese text, you must control the **charset at every byte ↔ character boundary**. A Java `String` can be right or wrong independently of the font rendering it. When UTF-8 is read as Latin-1, valid bytes produce wrong code points; when writing with a charset unable to represent characters, an encoder can substitute `?`; when decoding malformed bytes, data can be replaced with `U+FFFD` and become impossible to recover accurately.

A **BOM** helps identify byte order in UTF-16 and is sometimes used as a UTF-8 signature, yet must never be applied or stripped blindly across all formats. `Files.readString(..., UTF_8)` can still retain `U+FEFF` at the start of content if UTF-8 BOM bytes are present.

In Java 17+, prefer APIs with `StandardCharsets.UTF_8` or schema-declared charsets; specify source encoding in builds; when diagnosing bugs, inspect **raw bytes → decoder → String code points → encoder → stdout/terminal → font**. For strict payloads, configure `CharsetDecoder` with `CodingErrorAction.REPORT` so malformed data is never silently masked.

**Core principle:** *Do not fix garbled text by guessing encodings or swapping fonts. Find the exact layer that turned bytes into wrong characters, and fix the charset contract at that boundary.*

### References

- [`Charset` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html)
- [`StandardCharsets` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [`CharsetDecoder` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [`Files` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Console.charset()` – Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Console.html#charset())
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400)
- [Unicode FAQ: UTF-8, UTF-16, UTF-32 and BOM](https://www.unicode.org/faq/utf_bom.html)
