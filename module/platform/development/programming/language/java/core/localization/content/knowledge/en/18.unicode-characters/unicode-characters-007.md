# Distinguishing Unicode Code Space from External Encodings in Java

## 1. Why Must These Two Concepts Be Clearly Separated?

When a Java application reads personal names, Vietnamese translations, emojis, or JSON data from another system, we must answer **two independent questions**:

1. **Which character is being referred to?** Unicode identifies characters and text elements by **code point**, such as `U+0041` for `A`, `U+00E9` for `é`, and `U+1F600` for `😀`.
2. **How do those characters become bytes for storage or transmission?** A **character encoding/charset** (such as UTF-8, UTF-16BE, ISO-8859-1, or Windows-1252) defines the rules for representing or converting between character data and byte sequences.

**A Unicode code point is not a byte; UTF-8 is not "another language"; a Java `String` is not a UTF-8 file.**

For example, a string with content `Aé😀` is the exact same sequence of Unicode code points whether converted into:

- UTF-8 byte sequence: `41 C3 A9 F0 9F 98 80` (7 bytes).
- UTF-16BE byte sequence: `00 41 00 E9 D8 3D DE 00` (8 bytes, **excluding BOM**).
- With ISO-8859-1: **cannot be fully encoded**, because that charset has no representation for `😀`.

Choosing a different encoding does not change the characters we **intend** to represent; it changes the byte sequence and whether those characters can be represented accurately. If one end of a system writes UTF-8 while the other end decodes as Windows-1252, the text can turn into garbled characters (*mojibake*), even though no bytes were lost in transit.

### Lesson Objectives

After completing this lesson, you will be able to distinguish:

- **Unicode code point space**, Unicode scalar values, and code points written as `U+...`.
- **Java UTF-16 code units** (`char`, `String.length()`) from code point count, byte count, and visible characters.
- **Encoding** (UTF-8/UTF-16/legacy charsets) from **decoding**, and where conversions occur at I/O boundaries.
- **Unmappable character errors**, **wrong-charset decoding**, **malformed byte sequences**, **replacement characters**, and **normalization**.
- How to write/read bytes safely with `StandardCharsets`, enforce strict error handling, and build round-trip tests.

## 2. What Is the "Unicode Space"?

Unicode provides a universal identification system for text. Each **code point** has a numeric value written as `U+XXXX` or more digits (e.g., `U+1F600`). The code point value space spans:

```text
U+0000 ................................. U+10FFFF
```

Within that range:

- `U+0000` through `U+10FFFF` is the valid code point value range as defined by the Unicode code space.
- The range `U+D800`–`U+DFFF` is reserved for **UTF-16 surrogate code points**. They are **not Unicode scalar values** and must not be used as valid standalone Unicode characters for standard UTF-8 encoding.
- A **Unicode scalar value** is any code point outside the surrogate range.
- A code point can be assigned to a character, reserved for future use, serve a special function, or fall into a non-ordinary character group; **not every number in the space is a visible letter**.
- Some text representations consist of multiple code points, such as a letter followed by a combining mark (*combining mark*) or an emoji joined by a zero-width joiner.

Some examples:

| Representation | Code point | Notes |
| --- | --- | --- |
| `A` | `U+0041` | Latin letter A. |
| `é` | `U+00E9` | Letter e with acute accent in *precomposed* form. |
| `e◌́` | `U+0065` + `U+0301` | Letter e and combining acute accent: two code points, may look like `é`. |
| `😀` | `U+1F600` | Code point outside the Basic Multilingual Plane (BMP). |
| Ordinary space | `U+0020` | Differs from NBSP and many other Unicode whitespace characters. |
| `U+FEFF` | `U+FEFF` | Can appear at the start of text as a BOM or data containing this character; handle per protocol. |

**A "character" in everyday speech does not always correspond to one code point.** Unicode has the concept of a grapheme cluster (*a cluster of characters perceived by users as one unit*). A grapheme cluster can contain multiple code points, and a code point outside the BMP occupies two UTF-16 `char`s in Java.

### BMP and Supplementary Code Points

The **Basic Multilingual Plane (BMP)** is the range `U+0000`–`U+FFFF`. Unicode scalar values outside the BMP are called **supplementary code points** (`U+10000`–`U+10FFFF`). Representing one supplementary code point in UTF-16 requires **two code units**, called a **surrogate pair**.

`😀` (U+1F600) has the surrogate pair:

```text
High surrogate: U+D83D
Low surrogate:  U+DE00
```

Do not treat `U+D83D` as a complete `😀` character. If you process half of a surrogate pair as a standalone character, you can corrupt text when slicing, write invalid bytes, or lose data during encoding.

## 3. Java `String`, `char`, and Code Points Are Not Bytes

A Java `char` is **one 16-bit UTF-16 code unit**, not an arbitrary Unicode character and not a byte. Java `String` provides access by UTF-16 code unit position. Therefore:

- `String.length()` counts **UTF-16 code units**, not the number of Unicode code points or UTF-8 bytes.
- `String.charAt(index)` returns **one code unit**, which may be the high/low surrogate of a supplementary code point.
- `String.codePointAt(index)` can return the full code point when the index points to a high surrogate paired with a valid low surrogate.
- `String.codePointCount(beginIndex, endIndex)` counts code points in a UTF-16 range, while `String.codePoints()` provides an `IntStream` of code points.
- `Character.charCount(codePoint)` returns the number of UTF-16 code units needed for the code point (typically 1 or 2 depending on the range).
- `String.offsetByCodePoints(...)` can be used when advancing by code points instead of arbitrarily adding to `char` indices.

Example:

```java
String text = "A\u00E9\uD83D\uDE00"; // Aé😀

System.out.println(text.length());                 // 4
System.out.println(text.codePointCount(0, 4));      // 3
System.out.println(text.codePointAt(2) == 0x1F600); // true
```

In the string:

```text
UTF-16 index   0        1        2           3
code unit     0041     00E9     D83D        DE00
character     A        é        [two code units form 😀]
```

Therefore, when writing UIs:

- Do not truncate "100 characters" with `substring(0, 100)` assuming it means 100 user-perceived characters; it can slice between a surrogate pair or grapheme cluster.
- Data length limits must specify whether they refer to **bytes**, **UTF-16 code units**, **Unicode code points**, or **grapheme clusters**.
- Input forms for names, emojis, or messages often need counting by user-perceived character clusters. Java core includes `BreakIterator` for text segmentation, though detailed support for emoji/grapheme sequences can depend on version and algorithm; if full Unicode extended grapheme clusters are required in all cases, choose and test an appropriate implementation.

**Implementation detail:** Java does not guarantee that the internal byte layout inside a `String` object matches a UTF-16BE file. Modern JDKs can optimize string storage memory; what `charAt`/`length` APIs guarantee is **UTF-16 code unit semantics**, not a public byte format.

## 4. Encoding Is a Mapping Between Character Data and Bytes

A **charset/character encoding** defines how to encode characters into bytes and decode bytes into characters. In Java, the primary APIs are `java.nio.charset.Charset`, the classes `CharsetEncoder`/`CharsetDecoder`, and the constants in `StandardCharsets`.

The flow at the I/O boundary:

```text
                             ENCODE
Java String / char sequence ---------------> byte[]
        ^                                      |
        |                                      | file / socket / HTTP /
        |                                      | database driver / stream
        |                                      v
        +----------------------------------- byte[]
                             DECODE
```

The charset must be known on **both sides of the boundary**. If the sender uses UTF-8 while the receiver uses ISO-8859-1, the two sides disagree on how to interpret the bytes.

### Common Encodings

| Charset | Principle | Key characteristics to remember |
| --- | --- | --- |
| `UTF-8` | Encodes Unicode scalar values using 1–4 bytes per code point. | ASCII uses 1 byte; standard across the web, JSON, and modern text files. |
| `UTF-16BE` | UTF-16 code units written big-endian. | 2 bytes/code unit; supplementary code points use surrogate pairs = 4 bytes. |
| `UTF-16LE` | UTF-16 code units written little-endian. | Opposite byte order to BE; do not mix without a BOM/agreement. |
| `UTF-16` (Java charset) | UTF-16 with charset BOM/endianness rules. | Can emit/expect a BOM per UTF-16 rules; not identical to UTF-16BE. |
| `US-ASCII` | 7-bit character table. | Cannot represent accented Vietnamese or many non-ASCII characters. |
| `ISO-8859-1` | Single-byte legacy charset, mainly Western European Latin. | Represents `é` yet cannot represent emojis or most Vietnamese characters. |
| `windows-1252` | Legacy single-byte Western European Windows charset. | Differs from ISO-8859-1 in the `0x80`–`0x9F` byte range. |

**Unicode and UTF-8 are not competitors:** Unicode is the code space and text rules; UTF-8 is **an encoding form/encoding scheme for representing Unicode in bytes**. UTF-16 and UTF-32 are likewise ways of representing Unicode. Meanwhile, legacy charsets can only represent a limited character repertoire.

### Same Content, Different Bytes

Consider the string `Aé😀`:

| Unit | Result | Reason |
| --- | --- | --- |
| Unicode code points | `U+0041 U+00E9 U+1F600` | Three Unicode values. |
| Java UTF-16 code units | `0041 00E9 D83D DE00` | The emoji needs two code units. |
| UTF-8 bytes | `41 C3 A9 F0 9F 98 80` | Total 7 bytes. |
| UTF-16BE bytes, no BOM | `00 41 00 E9 D8 3D DE 00` | Total 8 bytes. |
| ISO-8859-1 | Cannot round-trip completely | `😀` is outside the charset's repertoire. |

Do not use `String.length()` to deduce UTF-8 file size, JSON body size, or database byte limits. To get the encoded byte count, use `text.getBytes(charset).length` with the charset actually used; also note that protocol structures and escaping can add bytes beyond the text string itself.

## 5. Encoding and Decoding Are Two Sides That Must Match

### Proper Encoding

`String.getBytes(StandardCharsets.UTF_8)` converts text to UTF-8 bytes; `new String(bytes, StandardCharsets.UTF_8)` decodes them back. Example:

```java
String message = "Xin chào!";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String copy = new String(bytes, StandardCharsets.UTF_8);
System.out.println(message.equals(copy)); // true
```

Both APIs above use an explicit charset. A successful round-trip proves data can be reconstructed along that path for the chosen string. It does not prove another system is actually using UTF-8, nor does it guarantee no transformations occur as text passes through other layers.

### Decoding with the Wrong Charset Causes Mojibake

For example, the character `é` (U+00E9) is UTF-8 encoded as two bytes `C3 A9`. If those two bytes are decoded as ISO-8859-1, they are interpreted as two different code points (`U+00C3` and `U+00A9`), producing a string looking like `Ã©`.

```text
Unicode U+00E9 "é"
        |
      UTF-8 encode
        v
bytes C3 A9
        |
      ISO-8859-1 decode (WRONG!)
        v
Unicode U+00C3 U+00A9 "Ã©"
```

The root cause is an **encoding mismatch** at the byte/text boundary, not Unicode "missing letters". If this corrupted string is re-encoded and stored in a database as real data, the problem can spread.

To fix it, identify the **original bytes, the charset used when encoding, the charset used when decoding, and which layer was wrong**. Do not run a global string replacement `"Ã" -> ...` over all data, as that can corrupt valid text or text legitimately containing that character.

### Default Charset Is Not a Data Exchange Contract

In Java, parameterless `String.getBytes()` uses the default charset of the Java environment. In Java 17, the result can depend on the OS/JVM and runtime configuration; from Java 18 onward, UTF-8 is the default under the new standardization policy, though some modes/configuration exceptions remain. **Data exchanged via files, APIs, or message queues should use an explicit charset** instead of relying on defaults.

`javac -encoding UTF-8` specifies the encoding of **Java source files**, and does not determine the encoding for files read by the application at runtime or bytes from HTTP.

## 6. Complete Java 17+ Example: Unicode, Bytes, and Charset Errors

Create the file **`UnicodeBoundaryDemo.java`** below. The program processes data purely in memory, writes no files, and does not depend on the console charset to print emojis. Bytes are printed using `HexFormat`, available since Java 17.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.Locale;

public class UnicodeBoundaryDemo {

    private static String hex(byte[] bytes) {
        return HexFormat.of().withUpperCase().formatHex(bytes);
    }

    public static void main(String[] args) {
        String text = "A\u00E9\uD83D\uDE00"; // Aé😀

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("emoji=U+"
                + Integer.toHexString(text.codePointAt(2))
                        .toUpperCase(Locale.ROOT));

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8=" + hex(utf8));
        System.out.println("utf16be="
                + hex(text.getBytes(StandardCharsets.UTF_16BE)));

        String roundTrip =
                new String(utf8, StandardCharsets.UTF_8);
        System.out.println("roundTrip="
                + text.equals(roundTrip));

        String wrongDecode =
                new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("wrongDecodeMatches="
                + text.equals(wrongDecode));

        CharsetEncoder latin1 = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            latin1.encode(CharBuffer.wrap(text));
            System.out.println("latin1=OK");
        } catch (CharacterCodingException ex) {
            System.out.println("latin1=UNMAPPABLE");
        }

        byte[] broken = {
                (byte) 0xC3, (byte) 0x28
        };
        CharsetDecoder strict = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT);

        try {
            strict.decode(ByteBuffer.wrap(broken));
            System.out.println("malformedUtf8=ACCEPTED");
        } catch (CharacterCodingException ex) {
            System.out.println("malformedUtf8=REJECTED");
        }

        String lenient =
                new String(broken, StandardCharsets.UTF_8);
        System.out.println("lenientHasReplacement="
                + lenient.contains("\uFFFD"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("directEqual="
                + composed.equals(decomposed));
        System.out.println("nfcEqual="
                + composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));
    }
}
```

Compile and run in the file's directory using JDK 17 or higher:

```bash
javac -encoding UTF-8 UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Exact stdout of the example:**

```text
utf16Units=4
codePoints=3
emoji=U+1F600
utf8=41C3A9F09F9880
utf16be=004100E9D83DDE00
roundTrip=true
wrongDecodeMatches=false
latin1=UNMAPPABLE
malformedUtf8=REJECTED
lenientHasReplacement=true
directEqual=false
nfcEqual=true
```

### Explanation of Each Check

1. `utf16Units=4` because `A` and `é` each occupy one UTF-16 code unit, while `😀` occupies two. `codePoints=3` is the code point count.
2. `emoji=U+1F600` thanks to `codePointAt(2)` reading the surrogate pair starting at UTF-16 index 2.
3. `utf8` and `utf16be` print actual bytes, illustrating different encodings of the **same character sequence**.
4. `roundTrip=true` because both encode and decode use UTF-8. `wrongDecodeMatches=false` because UTF-8 bytes were read as ISO-8859-1.
5. `latin1=UNMAPPABLE` shows that the legacy charset has no representation for the emoji. The encoder uses `CodingErrorAction.REPORT` to **report an error instead of silently substituting characters**.
6. `malformedUtf8=REJECTED` because the byte pair `C3 28` does not form a valid UTF-8 sequence. The strict decoder detects corrupted bytes.
7. `lenientHasReplacement=true` illustrates a decode path inserting replacement character `U+FFFD` on malformed input. Text already containing replacement characters usually cannot recover the original bytes.
8. `directEqual=false` between the two representations of `é`. `nfcEqual=true` because normalizing to NFC produces equivalent results in the example.

**Important:** this is an example of **representation boundaries**, not a way to classify "whether text is Vietnamese". An unsuitable charset may encode some Vietnamese letters while silently dropping other code points; testing must use the exact character set the product actually supports.

## 7. When Bytes or Characters Are Invalid: Replace or Report Errors?

### 7.1. An Encoder Can Encounter an Unmappable Character

Suppose you send `Aé😀` to a system accepting only ISO-8859-1. The character `😀` cannot be represented. Possible policies are:

- **REPORT:** stop and throw `UnmappableCharacterException` (via `CharsetEncoder` API).
- **REPLACE:** replace the character with a replacement byte sequence configured on the encoder; typically a question mark or equivalent replacement symbol.
- **IGNORE:** drop unrepresentable characters; very prone to silent data loss.

`String.getBytes(Charset)` uses replacement behavior when encountering input it cannot fully represent; for critical data, do not treat a successful `getBytes` call as proof that no information was lost. For strict control, use `CharsetEncoder` with `CodingErrorAction.REPORT` for `onMalformedInput(...)` and `onUnmappableCharacter(...)` per policy.

Illustrative example (placed in a Java method with appropriate imports):

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer result = encoder.encode(
        CharBuffer.wrap("A\u00E9\uD83D\uDE00"));
// Throws CharacterCodingException because the emoji cannot be encoded.
```

This snippet intentionally triggers an exception when run with that text. Not every exception during encoding means "bad UTF-8 bytes"; here it is an error of **not being able to represent a Unicode character in the target charset**.

### 7.2. A Decoder Can Encounter a Malformed Byte Sequence

A decoder must know which bytes constitute a valid sequence in its charset. In UTF-8, byte `C3` must be followed by a valid continuation byte. Byte `28` is `(` and is **not** a continuation byte, so `C3 28` is considered malformed.

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String text = decoder.decode(
        ByteBuffer.wrap(new byte[] {(byte) 0xC3, 0x28}))
        .toString();
// Throws CharacterCodingException.
```

This is an illustrative snippet with corresponding imports; not a standalone program. Depending on the task:

- **Transactional data, text requiring integrity:** consider REPORT to avoid silently substituting characters.
- **UI reading corrupted logs or legacy documents:** may display replacement characters, while recognizing that data is corrupted/unrecoverable.
- **Data from untrusted sources:** verify charset and enforce size limits; do not try to "guess" the encoding and swallow errors.

Detecting a decoding error does not mean the system knows the right charset for sure. It only proves the bytes are invalid **under the charset being attempted**. Many byte sequences are valid under the wrong charset yet decode into wrong characters (mojibake), so simply succeeding at decoding is insufficient to prove data is right.

### 7.3. Unpaired Surrogates Are a Special Case

A Java `String` can contain a lone surrogate UTF-16 code unit due to bad string slicing or receiving corrupted data. That is not a Unicode scalar value. When encoding to UTF-8, the encoder must treat it as **malformed input** per policy rather than inventing an independent code point.

You can check a string for surrogates by iterating code units/code points or validating strictly before exchanging critical data. Do not slice a `String` arbitrarily by code unit indices and expect a UTF-8 encoder to preserve "half an emoji".

## 8. Normalization Is Not Encoding

Unicode can have multiple code point sequences representing semantically equivalent text, for example:

```text
Precomposed é:           U+00E9
e + combining acute:     U+0065 U+0301
```

Both can look identical when rendered, yet their code point sequences differ, so:

```java
String a = "\u00E9";
String b = "e\u0301";

System.out.println(a.equals(b)); // false
System.out.println(a.equals(
        Normalizer.normalize(b, Normalizer.Form.NFC))); // true
```

This is an illustrative code snippet inside a Java method, requiring `import java.text.Normalizer;`.

**Normalization:** `Normalizer.Form.NFC`, `NFD`, `NFKC`, and `NFKD` are transformations between Unicode representation forms according to normalization rules. They do not convert UTF-8 bytes to UTF-16 bytes, do not detect right/wrong original charsets, and cannot recover mojibake.

- **NFC:** normalizes to canonically composed form; usually appropriate when storing/comparing text normalized per application contract.
- **NFD:** decomposes according to canonical equivalence rules; typically produces base character + combining marks where applicable.
- **NFKC/NFKD:** uses *compatibility equivalence* which can alter meaningful representation distinctions in some contexts; do not apply unconditionally to identifiers, passwords, or content that must remain unaltered.

Normalization **does not resolve every "looks alike" case**: visually similar Latin and Cyrillic letters can still be different code points; that is a confusable/security issue and identifier policy matter. Nor does every emoji combination or special character collapse into a single code point after NFC.

### Two Common Mistakes

1. "Two strings that look alike must return `true` for `String.equals`": false if their code point sequences differ or contain hidden characters/combining marks.
2. "To fix text showing `Ã©`, just run `Normalizer.normalize`": false because mojibake involves **bytes decoded with the wrong charset**, not merely differing Unicode normalization forms.

## 9. BOM, Byte Order, and Boundaries Outside Java

### 9.1. UTF-16 Byte Order

A UTF-16 code unit is 16 bits, so byte order must be specified:

- `UTF-16BE`: high byte first, e.g., `A` → `00 41`.
- `UTF-16LE`: low byte first, e.g., `A` → `41 00`.
- The `UTF-16` charset has its own BOM/endianness rules when reading/writing.

**BOM (Byte Order Mark)** is a byte sequence/marker at the start of a stream that can indicate byte order in UTF-16 variants. For UTF-8, the BOM `EF BB BF` is not needed to determine byte order; some files include a BOM for compatibility, yet applications/protocols have differing handling policies. Do not automatically add or strip a BOM without knowing the input format.

If you read a UTF-8 file with a BOM using an API that does not strip the BOM, the character `U+FEFF` can remain at the start of the string. That can affect key lookups, CSV headers, or string comparisons. Test BOM handling against real file formats instead of expecting every reader to "handle it automatically".

### 9.2. Writing and Reading Files with an Explicit Charset

Illustrative snippet inside a Java method:

```java
Path path = Path.of("message.txt");
String message = "Tiếng Việt – 😀";

Files.writeString(path, message, StandardCharsets.UTF_8);
String loaded = Files.readString(path, StandardCharsets.UTF_8);

System.out.println(message.equals(loaded)); // true
```

Requires importing `java.nio.file.Path`, `java.nio.file.Files`, and `java.nio.charset.StandardCharsets`; the calling method must handle or declare `IOException`. This snippet **actually writes a file** if executed; it is an illustration for a program with write permissions, not part of the standalone in-memory demo in Section 6.

A legacy application may use `InputStreamReader`, `OutputStreamWriter`, `BufferedReader`, or `Writer`; pass an explicit `Charset` wherever converting a byte stream to text, rather than using constructors relying on the default charset when the protocol specifies an encoding.

### 9.3. HTTP, JSON, CSV, and Databases

| Boundary | What to define | Common error |
| --- | --- | --- |
| HTTP request/response | Media type and framework charset conventions; charset parameter if supported by the protocol. | Encoding UTF-8 while server/client decodes with a different charset. |
| JSON | Modern inter-system JSON typically uses UTF-8 per standard; has its own escaping rules. | Confusing `\\uXXXX` in JSON with raw bytes or using an incompatible charset. |
| CSV | Encoding, BOM, delimiter, and quoting conventions of the file and importing system. | Spreadsheets opening a UTF-8 file as a legacy encoding; headers/Vietnamese get corrupted. |
| Database | Database, connection/driver, and text column charset/collation. | Driver or schema unable to store non-BMP code points; data gets replaced or lost. |
| Logs/console | Console charset, logging appender, display font. | Bytes are right yet terminal/renderer lacks glyphs; or vice versa. |
| Filenames/paths | How the OS and APIs handle path text and varying normalization. | Comparing filenames affected by Unicode form, invisible characters, or differing normalization. |

Do not claim "all font errors are encoding errors". A Unicode string can be completely valid and its bytes decoded accurately, yet the **font lacks the glyph** to render it. That is a different layer from character encoding. Inspect step by step: bytes → decode → code point sequence → font/layout.

### 9.4. JSON Escapes Are Not UTF-8 Encoding

A character can appear in JSON directly or escaped:

```json
{"message":"é"}
```

or:

```json
{"message":"\u00E9"}
```

Once a JSON parser processes it properly, both fields can produce the same Unicode value in `String`. However, JSON escape notation is **serialization syntax**, not how the charset of the byte stream carrying the JSON is determined. The resulting JSON data still must be encoded into bytes per the protocol.

For supplementary code points like `U+1F600`, JSON escapes can use the pair `\uD83D\uDE00`; the parser must interpret the two surrogate escapes as one code point when used together. Do not slice escaped strings and treat each surrogate half as a complete character.

## 10. Testing Unicode and Charsets Properly at Boundaries

A good test checks both the data and conversion conditions, not just "looks right on screen". The following matrix helps isolate issues:

| Case | Check | Expectation |
| --- | --- | --- |
| ASCII `A` | UTF-8, UTF-16BE | Different bytes, code point stays `U+0041`. |
| `é` | UTF-8 round-trip | `U+00E9` is reconstructed. |
| `😀` | `String.length` and `codePointCount` | 2 UTF-16 code units, 1 code point. |
| `Aé😀` | UTF-8 vs UTF-16BE bytes | 7 bytes vs 8 bytes, no BOM. |
| `Aé😀` to ISO-8859-1 | Strict encoder | Rejects unrepresentable character. |
| `C3 28` decoded as UTF-8 | Strict decoder | Reports malformed input. |
| `C3 28` via lenient decoder | Replacement behavior | May contain `U+FFFD`; recognize data loss occurred. |
| UTF-8 bytes read as ISO-8859-1 | Code point comparison | Different string, even though input bytes did not change. |
| `é` and `e` + combining accent | `String.equals` before/after NFC | Different before, equal after appropriate normalization. |
| String with unpaired surrogate | Strict UTF-8 encode | Not silently treated as a valid Unicode scalar. |
| UTF-8 file with BOM | Application reader | Policy to keep/strip BOM is explicitly tested. |
| JSON with emoji escapes | JSON parser | Code point and round-trip accurate when escapes are valid. |
| Field length/limit | Bytes/code points/graphemes | Matches the exact limit unit stated in the contract. |

### Input Safety Notes

- Bound byte sizes and text lengths in context to avoid excessive resource consumption during decoding, normalization, or grapheme processing.
- When verifying signatures or hashes, specify the exact **byte sequence** being signed; two semantically equivalent Unicode representations with different bytes will produce different hashes.
- When creating identifiers, paths, or usernames, account for normalization, casing, Unicode confusables, and invisible characters per policy; do not assume normalization solves all security issues.
- For legal data or text requiring byte-for-byte preservation, distinguish "Unicode content" from "original bytes" and store both if required.

## 11. Common Mistakes and Fixes

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "Unicode is UTF-8." | Confuses character identity with byte representation. | Unicode is the code point space; UTF-8 is an encoding. |
| "One Java char = one code point." | Corrupts emojis/surrogate pairs when slicing. | Distinguish UTF-16 code unit `char` and code point. |
| "`String.length()` is the UTF-8 byte count." | Wrong capacity limits and validation. | Count bytes after encoding in the right charset. |
| "UTF-16BE bytes are the in-memory `String` content." | Depends on internal JDK layout. | Rely only on API contracts and `getBytes(UTF_16BE)`. |
| "Every code point is a scalar value." | Surrogate values are not scalars. | Exclude `U+D800`–`U+DFFF` in Unicode scalar data. |
| "Legacy charsets can write all Vietnamese letters and emojis." | Characters can be replaced/dropped. | Use UTF-8 when the protocol permits, with strict error handling. |
| "Calling `getBytes()` without arguments always behaves identically." | Behavior can depend on runtime/default charset. | Pass `StandardCharsets.UTF_8` or the agreed charset. |
| "Decoding without throwing means the charset is right." | Byte-valid mojibake can occur. | Verify the charset contract and source data. |
| "`Normalizer` fixes mojibake." | Cannot recover a misinterpreted byte sequence through normalization alone. | Diagnose the actual encode/decode path. |
| "All visually identical characters are `equals`." | Differing code points or combining marks. | Use normalization and an appropriate comparison policy. |
| "UTF-8 BOM always disappears automatically." | `U+FEFF` may remain in the text. | Handle per format and test the actual reading API. |
| "Font glitches mean UTF-8 is wrong." | Text may be valid while lacking glyphs. | Inspect each layer: decode, code points, font. |
| "Unicode `\uXXXX` is four bytes." | That can be Java/JSON escape syntax, not UTF-8 bytes. | Distinguish escape syntax, code points, and encodings. |

## 12. Practice Exercises

**Exercise 1 — Count the right units:** given `"ABC"`, `"é"`, `"e\u0301"`, `"😀"`, and `"Aé😀"`. Print `String.length()`, `codePointCount(...)`, and `getBytes(UTF_8).length`. Record why all three numbers can differ.

**Exercise 2 — Trace the conversion path:** starting from `Aé😀`, list the code points, UTF-16 code units, and UTF-8 bytes. Try decoding the UTF-8 bytes as ISO-8859-1, print the corrupted string, and explain precisely which step used a mismatched charset.

**Exercise 3 — Legacy encoding:** test `US_ASCII` and `ISO_8859_1` on `"Hello"`, `"café"`, and `"Tiếng Việt"`. Use `CharsetEncoder` + `CodingErrorAction.REPORT`; distinguish *malformed* input from *unmappable* characters.

**Exercise 4 — Corrupted UTF-8 data:** construct the invalid bytes `C3 28`; compare `CharsetDecoder` REPORT against replacement decoding. Why can replacing with `U+FFFD` cause unrecoverable data loss?

**Exercise 5 — Normalization:** compare `"\u00E9"` and `"e\u0301"` before/after `Normalizer.Form.NFC`. Then test a string with two lookalike characters from different scripts and show why NFC does not resolve that confusion.

**Exercise 6 — UTF-8 files:** write a text file containing Vietnamese and emojis using `Files.writeString(..., UTF_8)`, and read it back with `Files.readString(..., UTF_8)`. Verify content equality and byte round-trip. Then try reading with the wrong charset on a test copy without overwriting the original file.

**Exercise 7 — API contract design:** specify an input field limited to 100 UTF-8 bytes instead of 100 user-perceived characters. Write a validator for the right unit, testing emojis, decomposed Vietnamese letters, composite characters, and surrogate pairs; state when a grapheme cluster limit is more suitable.

### Completion Checklist

- [ ] Distinguish Unicode code point space from external character encodings/charsets.
- [ ] Know `U+0000`–`U+10FFFF` and that surrogate range `U+D800`–`U+DFFF` are not scalar values.
- [ ] Understand `char`, `String.length`, code points, bytes, and grapheme clusters are distinct units.
- [ ] Explain why the same string `Aé😀` produces different UTF-8/UTF-16BE bytes.
- [ ] Use `StandardCharsets` explicitly when encoding/decoding across boundaries.
- [ ] Distinguish malformed bytes, unmappable characters, mojibake, and replacement characters.
- [ ] Understand normalization is a Unicode string transformation, not an encoding conversion.
- [ ] Control file/HTTP/database/console, BOM, and charset contracts per protocol.
- [ ] Write round-trip tests and validate the exact length unit per business requirements.

**Conclusion:** Unicode answers **"which character?"** using code points, while charset/encoding answers **"how is it represented as bytes?"** at storage and transmission boundaries. In Java, `String` operates in UTF-16 code units; to exchange data safely, specify charsets explicitly, handle decode/encode errors, and keep normalization separate from encoding.
