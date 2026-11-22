# Unicode, UTF-8, UTF-16, and Common Charsets

## Lesson Objectives

After this lesson, you will be able to explain the differences between **Unicode**, **code point**, **code unit**, **byte**, **glyph**, and **grapheme cluster**; read UTF-8/UTF-16 encoding rules; choose a charset when reading/writing Java text; recognize BOM, endianness, encoding-corrupted text (*mojibake*), invalid Unicode data, and normalization issues; and use Java 17 APIs to handle text safely.

**Core takeaway:** Unicode defines character code numbers and properties; **UTF-8/UTF-16 are encoding schemes** for Unicode used to store and transmit data. You cannot look at a few arbitrary bytes and claim they form a valid text string without knowing how to decode them.

## 1. Concepts to Keep Separate

| Term | Meaning | Example |
|---|---|---|
| **Character** | Concept of a letter/symbol in text; meaning depends on context | letter `é`, letter `A`, emoji |
| **Unicode code point** | Integer value denoted `U+XXXX`, from `U+0000` to `U+10FFFF` | `U+0041` is `A`; `U+1F600` is 😀 |
| **Unicode scalar value** | Code point **excluding** the surrogate range `U+D800..U+DFFF` | `U+1F600` is valid; `U+D83D` by itself is not a scalar value |
| **Code unit** | Unit an encoding uses to represent a sequence | UTF-8: 8 bits; UTF-16: 16 bits; UTF-32: 32 bits |
| **Byte** | 8-bit unit in file/network data | `0xC3`, `0xA9` are the two UTF-8 bytes of `é` |
| **Grapheme cluster** | Cluster of characters a reader typically treats as one displayed character | `e` + combining acute accent can display as “é” |
| **Glyph** | Shape drawn by a font/rendering engine | One code point can have multiple shapes; one glyph can represent multiple code points |
| **Charset / character encoding** | Rules converting between character sequences and byte sequences | UTF-8, UTF-16LE, windows-1252, Shift_JIS |

**A visible character does not necessarily equal one code point, one `char`, or one byte.** For example, the letter “é” can be represented by `U+00E9` (precomposed character) or by `U+0065 U+0301` (letter e and combining acute accent). Two strings may look identical when displayed yet not be equal when comparing code points.

Unicode also contains unassigned code points; “lying in the range `U+0000..U+10FFFF`” does not automatically guarantee it is an assigned character or valid for use in every context. **Surrogate code points** in `U+D800..U+DFFF` are reserved exclusively for UTF-16 representation and must not be encoded individually into a valid UTF-8 sequence.

### Data Relationship in a Program

```text
Text at the conceptual level
  ↓ choose sequence of Unicode code points / scalar values
Code point sequence
  ↓ apply a specific charset/encoding
Code unit sequence
  ↓ arrange bytes by encoding and byte order (if any)
Byte sequence on file/network
  ↓ decode using the same encoding
Code point sequence → text rendered with font, layout, normalization...
```

The path from text to bytes is called **encoding**; the reverse direction is **decoding**. A decoder must know the charset (from protocol standards, metadata, headers, BOM, or an agreed configuration). Guessing a charset from bytes is only a heuristic and cannot be certain for all inputs.

## 2. UTF-8: Variable-Length, ASCII-Compatible

UTF-8 represents a Unicode scalar value using **1–4 bytes**. The number of bytes depends on the code point range:

| Unicode scalar value range | UTF-8 bytes | Bit pattern |
|---|---:|---|
| `U+0000..U+007F` | 1 | `0xxxxxxx` |
| `U+0080..U+07FF` | 2 | `110xxxxx 10xxxxxx` |
| `U+0800..U+FFFF` (excluding surrogates) | 3 | `1110xxxx 10xxxxxx 10xxxxxx` |
| `U+10000..U+10FFFF` | 4 | `11110xxx 10xxxxxx 10xxxxxx 10xxxxxx` |

The `x` bits hold the code point value. Continuation bytes have the `10` prefix. A conformant UTF-8 decoder must **reject** sequences longer than the shortest form (*overlong encoding*), invalid continuation bytes, surrogate values, and values greater than `U+10FFFF`.

Concrete examples:

| Text | Code point | UTF-8 bytes (hex) | Length |
|---|---|---|---:|
| `A` | `U+0041` | `41` | 1 |
| `é` | `U+00E9` | `C3 A9` | 2 |
| `中` | `U+4E2D` | `E4 B8 AD` | 3 |
| 😀 | `U+1F600` | `F0 9F 98 80` | 4 |

Standard ASCII uses bytes `00..7F`, so text containing only ASCII characters has the exact same bytes in UTF-8. This is why UTF-8 is pervasive in modern protocols, source code, JSON, and file systems. **However**, a lone `0xE9` byte (the letter é in ISO-8859-1) is not a complete UTF-8 sequence.

UTF-8 **has no byte order**; an optional UTF-8 BOM is the sequence `EF BB BF` representing `U+FEFF` at the start of a file. A UTF-8 BOM sometimes helps legacy tools recognize the encoding, but many protocols/tools do not need or expect a BOM. Do not add a BOM if the format does not allow it. In Java, when decoding `EF BB BF` with `StandardCharsets.UTF_8`, `U+FEFF` may remain in the `String`; do not blindly assume every API strips it automatically.

UTF-8 is a Unicode encoding, **not an encoding that always outputs one byte per letter**. When writing a payload length for HTTP/sockets/binary files, you must count **bytes after encoding**, not use `String.length()`.

## 3. UTF-16: 16-Bit Code Units, Surrogate Pairs

UTF-16 uses **16-bit code units**, with each unit corresponding to **2 bytes**.

- For Unicode scalar values from `U+0000` to `U+FFFF` outside the surrogate range (BMP), UTF-16 normally uses **one code unit**.
- For values from `U+10000` to `U+10FFFF`, UTF-16 uses a **surrogate pair**, consisting of a *high surrogate* (`D800..DBFF`) and a *low surrogate* (`DC00..DFFF`), totaling **two code units = 4 bytes**.
- A high surrogate not properly paired with a low surrogate, or a standalone low surrogate, is an **ill-formed UTF-16 sequence** when interpreted as Unicode text.

For example, 😀 = `U+1F600` becomes the pair `D83D DE00` in UTF-16. Converting a code point `U+10000` or higher into a surrogate pair can be understood as:

1. Take `U = codePoint - 0x10000`.
2. High surrogate = `0xD800 + (U >> 10)`.
3. Low surrogate = `0xDC00 + (U & 0x3FF)`.

This example explains why an emoji can occupy **two `char` positions in Java**, even though it is a single Unicode code point.

### Endianness and BOM of UTF-16

| Encoding | Bytes of `A` (`U+0041`) | Bytes of 😀 (`U+1F600`) |
|---|---|---|
| `UTF-16BE` | `00 41` | `D8 3D DE 00` |
| `UTF-16LE` | `41 00` | `3D D8 00 DE` |
| `UTF-8` | `41` | `F0 9F 98 80` |

**BE** (*big-endian*) stores the high byte first; **LE** (*little-endian*) stores the low byte first. `UTF-16` without BE/LE specified in the name can use BOM `FE FF` (BE) or `FF FE` (LE) for detection; when there is no BOM, the reading policy must be defined by the protocol/API specification, not guessed from the operating system. For Java's standard charsets, `StandardCharsets.UTF_16` detects the BOM and defaults to big-endian when no BOM is present; the corresponding encoder may emit a BOM. `UTF_16BE`/`UTF_16LE` select the byte order explicitly and do not automatically emit a BOM solely because of the chosen encoding.

Do not confuse UTF-16 with “16 bits for every character”: emojis outside the BMP require 4 bytes. And **a UTF-16 code unit is not a Unicode code point**.

## 4. UTF-32, ASCII, and Non-Unicode Charsets

UTF-32 uses **one 32-bit code unit per Unicode scalar value**, with BE/LE byte order. It makes locating code points by fixed units easy, but typically costs 4 bytes/character and is not as common as UTF-8 for data exchange. UTF-32 still does not guarantee that one code point corresponds to one grapheme cluster.

Common charset names:

| Charset | Characteristics | Usage Notes |
|---|---|---|
| **US-ASCII** | 7-bit, bytes `00..7F` | Cannot represent accented Vietnamese or emojis |
| **ISO-8859-1 (Latin-1)** | One byte for `U+0000..U+00FF` | Many bytes have different meanings than windows-1252 |
| **windows-1252** | Western European single-byte encoding | Bytes `0x80..0x9F` differ from Latin-1; common in legacy Windows data |
| **UTF-8** | Unicode 1–4 bytes, ASCII-compatible | Preferred for new data exchange |
| **UTF-16/UTF-16LE/UTF-16BE** | Unicode, 16-bit code units | Must be clear on byte order/BOM |
| **UTF-32LE/UTF-32BE** | Unicode, 32-bit code units | Not among the six mandatory charsets in `StandardCharsets` |
| **Shift_JIS**, **EUC-JP** | Legacy Japanese charsets | Must know the exact variant/data source |
| **GB18030**, **GBK**, **Big5** | Charsets/variants used in Chinese data | Not synonymous with UTF-8 |
| **EUC-KR**, **windows-949** | Legacy Korean charsets | Do not assume they are equivalent |

Some historical names do not cover all of Unicode and cannot represent every character. Two “similar-looking” charsets can still map bytes to different characters, causing hard-to-spot bugs. For instance, byte `0x80` in windows-1252 usually represents `€`, whereas in ISO-8859-1 it is the control character `U+0080`. This is a common reason text displays strange characters.

Aliases such as `UTF8`, `utf-8`, and `ISO8859_1` may be recognized by Java through the charset registry; during development, use standard constants or official names instead of inventing variants. Support for some historical charsets depends on the JDK/provider. **The six charsets always present in Java SE `StandardCharsets`**: `US_ASCII`, `ISO_8859_1`, `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`.

### Unicode Differs from UTF-8/UTF-16

| Statement | Assessment |
|---|---|
| “Unicode is UTF-8” | False: Unicode is a character code system; UTF-8 is one encoding of Unicode |
| “UTF-16 always uses 2 bytes per character” | False: code points outside the BMP need 4 bytes; a grapheme can have multiple code points |
| “UTF-8 and UTF-16 contain different characters” | False for valid Unicode scalar sequences: the same set of values can be represented; byte storage differs |
| “ASCII is a byte-compatible subset of UTF-8” | True for standard ASCII data `00..7F` |
| “The same bytes must decode to the same text” | False if different charsets are used |
| “A BOM is mandatory in UTF-8” | False |
| “Java String length equals the number of visible characters” | False |

## 5. Unicode in Java: `String`, `char`, Code Points

Java `String` exposes strings in **UTF-16 units** at the API layer. `char` is a **16-bit** value, which may be one code unit of a surrogate pair and does not inherently guarantee a complete code point. Important methods:

| Java API | What does it count/access? |
|---|---|
| `String.length()` | Number of **UTF-16 code units** |
| `String.charAt(index)` | One `char` (code unit) at index |
| `String.codePointAt(index)` | One code point at the specified code unit position; combines valid surrogate pairs |
| `String.codePointCount(begin, end)` | Number of code points in the UTF-16 index range |
| `String.codePoints()` | `IntStream` of code points (unpaired surrogates may still appear as standalone values) |
| `Character.toChars(codePoint)` | UTF-16 `char`s representing the code point |
| `String.getBytes(charset)` | Encodes `String` to bytes using the charset |
| `new String(bytes, charset)` | Decodes bytes using the charset |

### Example 1 — `char` count, code points, and bytes are completely different

Save as **`UnicodeBasicsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public class UnicodeBasicsDemo {
    public static void main(String[] args) {
        String text = "Aé😀";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: " +
            text.codePointCount(0, text.length()));
        System.out.println("Code points: " +
            text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", ")));

        System.out.println("UTF-8: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_8)));
        System.out.println("UTF-16BE: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_16BE)));
        System.out.println("UTF-16LE: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_16LE)));
    }
}
```

Run on Java 17+:

```bash
javac UnicodeBasicsDemo.java
java UnicodeBasicsDemo
```

Exact stdout:

```text
UTF-16 units: 4
Code points: 3
Code points: U+0041, U+00E9, U+1F600
UTF-8: 41c3a9f09f9880
UTF-16BE: 004100e9d83dde00
UTF-16LE: 4100e9003dd800de
```

Analysis: `A` = one `char`; `é` = one `char`; 😀 = **two** `char`s (high/low surrogate), so `length() == 4`, yet there are only three code points. UTF-8 requires 1 + 2 + 4 = **7 bytes**. `HexFormat` was added in Java 17. Do not arbitrarily use `charAt`/substring to slice in the middle of a surrogate pair.

> If the task needs to count **user-visible characters**, code point count is also not enough: the string `e\u0301`, some emojis with tone modifiers, flags, and ZWJ emojis can be a single grapheme cluster composed of multiple code points. You can use Unicode text segmentation algorithms supported by libraries, such as ICU4J for full grapheme requirements; do not assume iterating by code point iterates by displayed character.

## 6. Encoding and Decoding in Java 17

### Choose an explicit charset when converting bytes ↔ text

Examples of common operations:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

This is an **illustrative snippet** where `text` is of type `String`; `java.nio.charset.StandardCharsets` must be imported. If the string is valid Unicode and uses the same charset in both directions, the result usually matches. If the `String` contains an invalid lone surrogate or the charset cannot represent a character, the encoder/decoder error handling may lose information.

For text files, `Path`/`Files` (NIO.2) is usually the right starting point:

```java
Files.writeString(path, content, StandardCharsets.UTF_8);
String result = Files.readString(path, StandardCharsets.UTF_8);
```

This is an **illustrative snippet**: `path` is a `Path`, `content` is a `String`, and the calling method handles `IOException`. Large files should be read/written incrementally using `Files.newBufferedReader` and `Files.newBufferedWriter`, or `InputStreamReader`/`OutputStreamWriter` with the charset explicitly specified:

```java
try (var reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process a line; readLine() strips the line termination characters
    }
}
```

`reader` closes automatically. `readLine()` returns data without `\\r`, `\\n`, or `\\r\\n`; if you want to preserve exact bytes, line endings, or BOM, operate on the raw bytes before altering them.

### Default charset can be a source of bugs

APIs that allow omitting the charset may depend on the version/runtime:

- On **Java 17**, `Charset.defaultCharset()` depends on the environment; it may differ across developer machines, CI runners, or operating systems.
- Starting in **Java 18**, JEP 400 specifies UTF-8 as the default charset in standard cases, along with compatibility modes; you should not build protocols on implicit runtime defaults.
- When there is a data standard such as HTTP responses, exchanged CSVs, configuration files, or message protocols, **specify and pass the exact charset**.

`new String(bytes)` or `string.getBytes()` without a charset argument easily leads to tasks working on machine A yet failing on machine B. Use `StandardCharsets.UTF_8` if the specification permits UTF-8.

## 7. When Bytes Are Corrupted or the Wrong Charset Is Chosen

### Distinguish two cases

1. **Bytes valid in charset X but decoded as Y** → usually produces garbled text (*mojibake*). For example, UTF-8 of `é` (`C3 A9`) interpreted under ISO-8859-1 becomes `Ã©`.
2. **Bytes invalid in the decoding charset** → the decoder may report an error or replace them with `U+FFFD` (replacement character ``). For example, a single byte `E9` from Latin-1 is not a valid UTF-8 sequence.

Do not try converting back and forth across multiple charsets to “fix” text if you do not know the **original bytes** and the encoding/decoding steps that were performed; replacement with `` may have already lost information.

### Example 2 — strict decoding vs. replacement on error

Save as **`CharsetErrorDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CharsetErrorDemo {
    public static void main(String[] args) {
        // "café" encoded in ISO-8859-1
        byte[] latin1 = {
            (byte) 0x63, (byte) 0x61,
            (byte) 0x66, (byte) 0xE9
        };

        System.out.println("Latin-1: " +
            new String(latin1, StandardCharsets.ISO_8859_1));
        System.out.println("UTF-8 replacement: " +
            new String(latin1, StandardCharsets.UTF_8));

        try {
            var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
            decoder.decode(ByteBuffer.wrap(latin1));
        } catch (CharacterCodingException ex) {
            System.out.println("Strict UTF-8: " +
                ex.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac CharsetErrorDemo.java
java CharsetErrorDemo
```

Stdout:

```text
Latin-1: café
UTF-8 replacement: caf�
Strict UTF-8: MalformedInputException
```

`new String(bytes, UTF_8)` uses replacement behavior for invalid UTF-8 bytes with the replacement character; whereas `CharsetDecoder` with `CodingErrorAction.REPORT` surfaces the error. In data-ingestion systems requiring accuracy—especially IDs, audit logs, or digitally signed data—a strict decoder is usually preferable to silently replacing characters.

The `CodingErrorAction` options:
- `REPORT`: reports an error; with `decode(ByteBuffer)`, typically throws `MalformedInputException` or `UnmappableCharacterException`.
- `REPLACE`: inserts a replacement string/character when an error occurs.
- `IGNORE`: drops invalid data, which can lose information and is usually unsuitable for storing critical data.

**Malformed input** is a byte/code unit sequence that violates the encoding; an **unmappable character** is a valid character that the target charset has no way to represent. For example, encoding `"Tiếng Việt"` as Latin-1 encounters many unencodable characters: the encoder may replace, ignore, or report an error depending on configuration. Do not treat `getBytes(ISO_8859_1)` as a lossless conversion for Vietnamese.

### When UTF-8 arrives in multiple chunks

A UTF-8 character can span a read boundary from a socket or file. For example, 😀 is `F0 9F 98 80`: the first read might receive only `F0 9F`, and the next read receives `98 80`. Calling `new String(chunk, UTF_8)` separately on each chunk can produce replacement characters.

With multi-chunk data, retain unprocessed bytes via `ByteBuffer.compact()` or an equivalent buffering structure, and use a **stateful `CharsetDecoder`** across multiple `decode(input, output, endOfInput)` calls followed by `flush(output)` at EOF. Check `CoderResult.UNDERFLOW`, `OVERFLOW`, errors, and `CharBuffer` capacity. Avoid treating TCP `read()` boundaries as text/message boundaries. A simpler approach when the input is a sequential byte stream: use `InputStreamReader` wrapping `InputStream`, which is already designed to decode incrementally arriving data.

## 8. Unicode Normalization: Same Appearance, Different Bytes

A string can represent the same textual content using multiple code point sequences. For example:

- `café` with `é = U+00E9` (composed)
- `cafe\u0301` with `e = U+0065`, combining acute accent `U+0301` (decomposed)

In Java, `String.equals` compares the actual UTF-16 contents and does not automatically normalize Unicode.

**Normalization forms** (Unicode Standard Annex #15):

| Form | Description | Example Usage |
|---|---|---|
| **NFC** | Canonical decomposition followed by composition | Unifying canonically equivalent representations |
| **NFD** | Canonical decomposition | Certain processing workflows that separate accents |
| **NFKC** | Compatibility decomposition followed by composition | Certain search/compatibility normalization tasks, mindful of changing presentation semantics |
| **NFKD** | Compatibility decomposition | Analyzing character forms that have compatibility variants |

The `NFKC`/`NFKD` forms can lose meaningful presentation distinctions (such as certain compatibility characters). Do not use them indiscriminately for source text, digital signatures, or identifiers with their own standards.

### Example 3 — NFC and string comparison

Save as **`NormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class NormalizationDemo {
    public static void main(String[] args) {
        String composed = "café";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: " +
            composed.equals(decomposed));
        System.out.println("NFC equals: " +
            composed.equals(
                Normalizer.normalize(
                    decomposed, Normalizer.Form.NFC
                )));
        System.out.println("Raw code points: " +
            decomposed.codePointCount(0, decomposed.length()));
    }
}
```

Run:

```bash
javac NormalizationDemo.java
java NormalizationDemo
```

Stdout:

```text
Raw equals: false
NFC equals: true
Raw code points: 5
```

The string `cafe\u0301` has `c`, `a`, `f`, `e`, combining acute accent = **5 code points**; it usually displays identically to precomposed “café” with 4 code points. Comparing, searching, hashing, or generating Unicode keys may require normalization rules **agreed upon at data boundaries**. Do not normalize only one side before verifying a signature/HMAC over raw bytes.

**Normalization differs from case folding:** `toLowerCase()` does not solve all case-insensitive Unicode comparisons. If language/search handling is required, define the locale and semantics explicitly; `String.toLowerCase(Locale.ROOT)` can suit certain non-linguistic identifiers, but it is not a universal solution for all Unicode rules.

## 9. Proper Read/Write Workflow for Files and APIs

### Reading from bytes into Java text

```text
Byte source → verify encoding via protocol contract/metadata
            → detect BOM when specified by the format
            → CharsetDecoder (REPORT or explicit error policy)
            → String / Reader in Java UTF-16 code units
            → process code points / graphemes per business requirements
```

Do not “read text” by casting each byte to `char`. When bytes contain UTF-8, one code point can take four bytes; when a UTF-16LE file is decoded as UTF-8, even interleaved `00` bytes can corrupt how the data displays.

### Writing Java text to bytes

```text
String → apply normalization if required by the protocol
       → CharsetEncoder with an explicit error policy
       → byte[]/OutputStream/Files
       → BOM/metadata/media type consistent with the charset
```

If choosing UTF-8, APIs like `Files.writeString(path, text, UTF_8)` are sufficient. For binary data with a “length” field, compute `text.getBytes(UTF_8).length`. If using a `Writer`, it encodes characters into bytes; `BufferedWriter` is only a buffer and does not choose the right charset for the application.

### BOM, newlines, and file markers

Three independent concepts:

- **BOM**: leading bytes indicating byte order or encoding signature, e.g., `EF BB BF` in UTF-8, `FE FF` in UTF-16BE, `FF FE` in UTF-16LE.
- **Newline**: `LF`, `CRLF` are text content; the charset determines their corresponding bytes, but does not dictate which line ending a system must use.
- **Binary file marker / magic bytes**: can help identify a file format, not necessarily a charset.

A file without a BOM **does not mean ASCII or UTF-8**. A file containing a BOM must also be checked against the format contract and specific decoding API, because not every decoder strips the BOM automatically.

## 10. Real-World Scenarios: When to Choose What?

| Scenario | Appropriate Choice | Reason |
|---|---|---|
| New config/JSON/log files | UTF-8 per spec, usually without BOM | Ubiquitous, ASCII-compatible, stores Unicode |
| CSV exchanged across multiple systems | Standardize on UTF-8, state charset in contract; BOM policy per consumer | CSV does not self-identify its encoding |
| Legacy system UTF-16 files | Use exact UTF-16LE/BE or UTF-16 per BOM/spec | Avoid misdecoding as UTF-8 |
| Legacy Latin-1 / windows-1252 files | Specify the actual charset, process and convert with verification | Prevent mojibake on non-ASCII bytes |
| TCP socket receiving UTF-8 incrementally | `InputStreamReader` or streaming decoder with clear framing | Do not split characters on individual byte reads |
| Unicode identifiers/comparison | Specify normalization + case/locale + character policy | Avoid two visually identical strings having different bytes |
| Signing, hashing text content | Fix byte encoding and normalization before signing | Hash/HMAC operates on bytes; different bytes yield different signatures |
| Truncating/limiting text in UI | Consider grapheme clusters instead of `String.length()` | Avoid splitting surrogates, combining marks, or joined emojis |

**Practice for Vietnamese data:** UTF-8 fully represents accented characters, including combining marks. ISO-8859-1 and US-ASCII cannot fully represent Vietnamese; do not convert Vietnamese data into them with default replacement and expect to recover the original text.

## 11. Common Pitfalls and How to Check Them

1. **Declaring UTF-8 when the bytes are not UTF-8.** Compare input hex bytes against actual metadata. ASCII-only content makes mismatches hard to detect; test with `Tiếng Việt`, `é`, `中`, and emojis.
2. **Using `String.length()` as byte payload length.** Use `text.getBytes(UTF_8).length` or count bytes during encoding.
3. **Splitting a surrogate pair in half.** When code-point processing is needed, use `codePoints()`, `offsetByCodePoints()`, and `Character.charCount()` appropriately. When displayed-character processing is needed, use grapheme segmentation.
4. **Decoding an entire chunk right after a single socket `read`.** Bytes of a multi-byte character may be split; preserve decoder state and handle framing.
5. **Decoding with the wrong encoding and then re-encoding again.** Mojibake strings may get permanently stored; keep the original bytes for diagnosis rather than experimenting on production data.
6. **Ignoring the BOM.** Leading bytes can introduce `U+FEFF`, breaking the first CSV header, configuration keys, or string comparisons. Strip the BOM only when the format permits, checking the exact leading bytes/character.
7. **Assuming every charset is Unicode.** Legacy charsets may not represent a character; use an encoder with `REPORT` if information loss is strictly unacceptable.
8. **Comparing strings without considering normalization.** Visually identical strings may have different code points; apply NFC/NFD per contract before building keys or searching when appropriate.
9. **Equating normalization with security.** *Confusable* characters, bidirectional control characters (bidi), zero-width characters, and mixed scripts can mislead users; identifier policies require separate checks. Do not assume NFC alone eliminates those risks.
10. **Relying on the runtime's default charset.** Use an explicit charset when reading/writing data exchanged between machines.
11. **Confusing Java `char` with Unicode scalar value.** A `char` can be a surrogate. A code point may not correspond to one grapheme, and multiple code points can combine into one glyph.
12. **Not distinguishing data encoding from escaping.** JSON `"\u00E9"` is an *escape* representation in JSON syntax; the byte stream of the JSON file still has its own encoding (usually UTF-8). URL percent-encoding, HTML entities, and Base64 are likewise not charsets replacing UTF-8.

### Quick checklist for diagnosing corrupted data

1. Find the **original bytes** and their source, and save a raw sample to reproduce.
2. Inspect the actual protocol/file parameters: charset, BOM, byte order, media type, and connection settings.
3. Print limited hex bytes in a test environment to compare `C3 A9` (UTF-8 for é) with `E9` (Latin-1 for é).
4. Decode strictly using the designated charset; report errors on invalid data. If decoding succeeds yet yields strange characters, verify whether the source charset is right.
5. Check normalization when text looks identical yet comparison fails; distinguish font/glyph rendering issues from byte encoding bugs.
6. Lock in regression tests for Vietnamese characters, emojis, combining marks, invalid bytes, BOM, and buffer boundaries.

## 12. Self-Check

**Question 1.** For `String s = "A😀";`, what are `s.length()`, `codePointCount(0, s.length())`, and its UTF-8 byte length?

**Answer:** `length() == 3` because `A` uses one `char` and 😀 uses a two-`char` surrogate pair; there are **2 code points**; UTF-8 is **5 bytes** (`41 F0 9F 98 80`).

**Question 2.** Why can the byte sequence `C3 A9` turn into `Ã©`?  
**Answer:** Those are the UTF-8 bytes of `é`, but decoding byte-by-byte as ISO-8859-1 yields `U+00C3` (Ã) and `U+00A9` (©).

**Question 3.** What bytes does UTF-16LE encode 😀 into? What about UTF-16BE?  
**Answer:** Surrogate pair `D83D DE00`; UTF-16LE is `3D D8 00 DE`, UTF-16BE is `D8 3D DE 00`.

**Question 4.** Why can `String.equals` return false for two identical-looking “é” characters?  
**Answer:** One string uses `U+00E9`; the other uses `U+0065 U+0301`. They have different code points/code units; NFC may be needed per the data contract.

**Question 5.** Which API should be used to avoid silently losing bytes when receiving a malformed UTF-8 file?  
**Answer:** `CharsetDecoder` from `StandardCharsets.UTF_8` configured with `CodingErrorAction.REPORT`; handle `CharacterCodingException`.

**Question 6.** Can you assume a single `InputStream.read(byte[])` call receives a complete UTF-8 character or a complete TCP message?  
**Answer:** No. UTF-8 can be split across reads and TCP does not preserve message boundaries. A streaming reader/decoder and a framing protocol are required.

**Remember:** Unicode describes code points; UTF-8/UTF-16/UTF-32 specify how to represent those values in code units/bytes. In Java 17, `String` is indexed by UTF-16 code units; use explicit charsets when converting `String ↔ byte[]`, and control decoding errors, BOM, normalization, and data boundaries to avoid corrupted text or lost information.