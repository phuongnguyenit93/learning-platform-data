# Comparing Strings Across File, Console, and Wire Boundaries in Java

## Objectives

When a Vietnamese string or emoji looks right inside a program yet breaks after saving to a file, printing to a terminal, or sending to another service, the question to ask is: **what rule did the sender use to turn characters into bytes, and what rule is the receiver using to turn bytes back into characters?**

After this lesson, you will be able to inspect a string at three levels—**Unicode characters, UTF-16 code units, and bytes**—verify results across file/console/wire boundaries, detect charset mismatches, BOMs, line-ending differences, and Unicode normalization issues, and design a verifiable send-and-receive workflow in Java 17+.

## 1. Three Layers to Distinguish When Comparing Strings

In Java, a `String` is an immutable sequence represented by **UTF-16 code units**. When writing to a file or transmitting over a network, the program must **encode** (`encode`) the string into `byte[]`; on the receiving end, bytes are **decoded** (`decode`) according to a `Charset` to reconstruct a string.

```text
String in Java ── encode with charset ──> byte[] ── write file / transmit
String in Java <── decode with charset ─── byte[] <── read file / receive
```

Here are the distinct comparisons:

| Question | Java API Used | Meaning |
| --- | --- | --- |
| Do two strings have the same UTF-16 code unit sequence? | `a.equals(b)` | Exact `String` content comparison, sensitive to case and different Unicode forms |
| Do two strings have the same Unicode code point sequence? | `s.codePoints()` | Inspects characters by code point, avoiding mistaking one emoji for two UTF-16 units |
| Do two records have the exact same bytes? | `Arrays.equals(bytesA, bytesB)` | Verifies that stored/transmitted binary data is genuinely identical |
| Are the bytes valid under the expected charset? | `CharsetDecoder` with `CodingErrorAction.REPORT` | Detects malformed byte sequences before accepting content |

**Example:** the string `"A😀"` has `String.length() == 3` (one unit for `A`, two UTF-16 units for the emoji), yet has only **2 Unicode code points**. UTF-8 encoding yields **5 bytes**: `41 f0 9f 98 80`. `String` length is not the number of user-perceived characters, and certainly not the byte count.

```java
String text = "A\uD83D\uDE00";
System.out.println(text.length());                        // 3 UTF-16 units
System.out.println(text.codePointCount(0, text.length())); // 2 code points
System.out.println(text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length); // 5 bytes
```

The snippet above can be run in `jshell`; `\uD83D\uDE00` is the surrogate pair for emoji 😀. Never slice a `String` at an arbitrary index that could split a surrogate pair; in real text, a "user-perceived character" (grapheme cluster) can also consist of multiple code points.

## 2. Charset Is the Contract Across Boundaries

`java.nio.charset.StandardCharsets.UTF_8` unambiguously defines the Unicode ↔ byte mapping. If you write UTF-8 and read with `ISO_8859_1` or Windows-1252, the bytes may remain intact yet the **decoded characters differ**, often appearing as `"Ã..."` strings (mojibake). Conversely, if you encode with a charset that lacks the source character, data may be replaced with question marks or replacement characters and cannot be recovered merely by switching charsets on read.

| Content | UTF-8 | UTF-16BE | Remarks |
| --- | --- | --- | --- |
| `A` (U+0041) | `41` | `00 41` | Same character, different byte counts |
| `é` (U+00E9) | `c3 a9` | `00 e9` | Reading `c3 a9` as Latin-1 will not yield `é` |
| 😀 (U+1F600) | `f0 9f 98 80` | `d8 3d de 00` | UTF-16 uses a surrogate pair |
 
In modern practice, **choose UTF-8 as the default exchange contract** unless a specific protocol format dictates otherwise; both sides must agree on the same charset. In Java 17, never assume every API uses the same charset. Overloads taking an explicit `Charset` make code clearer and prevent machine-dependent discrepancies.

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

This is an illustrative snippet assuming `text` already exists. `getBytes(UTF_8)` encodes; `new String(bytes, UTF_8)` decodes. This pair must preserve the **exact bytes crossing the boundary**, rather than encoding to bytes and converting back to a string using a different charset in between.

## 3. Runnable Example: Verifying Both File and "Wire Payload"

The following program creates source data, obtains UTF-8 bytes as a wire payload, writes those exact bytes to a temporary file, and checks both bytes and `String` upon reading back. It also performs a wrong-charset decode to show why **unchanged bytes can still display incorrectly**.

Save as `BoundaryRoundTrip.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.HexFormat;

public class BoundaryRoundTrip {
    public static void main(String[] args) throws IOException {
        // \u00E0 is à; \uD83D\uDE00 is 😀; \n is LF.
        String original = "Xin ch\u00E0o \uD83D\uDE00\n";

        // Simulate the payload placed onto the wire by the sender.
        byte[] wire = original.getBytes(StandardCharsets.UTF_8);
        String received = new String(wire, StandardCharsets.UTF_8);

        Path file = Files.createTempFile("string-boundary-", ".txt");
        try {
            Files.write(file, wire);
            byte[] disk = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("file-bytes-match=" + Arrays.equals(wire, disk));
            System.out.println("file-text-match=" + original.equals(restored));
            System.out.println("wire-text-match=" + original.equals(received));

            String wrong = new String(disk, StandardCharsets.ISO_8859_1);
            System.out.println("wrong-charset-match=" + original.equals(wrong));

            String composed = "\u00E9";
            String decomposed = "e\u0301";
            System.out.println("unicode-equal-before=" + composed.equals(decomposed));
            System.out.println("unicode-equal-after=" + composed.equals(
                    Normalizer.normalize(decomposed, Normalizer.Form.NFC)));

            String probe = "A\uD83D\uDE00";
            byte[] encodedProbe = probe.getBytes(StandardCharsets.UTF_8);
            System.out.println("utf16-units=" + probe.length());
            System.out.println("code-points=" + probe.codePointCount(0, probe.length()));
            System.out.println("utf8-length=" + encodedProbe.length);
            System.out.println("utf8-hex=" + HexFormat.of().formatHex(encodedProbe));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac BoundaryRoundTrip.java
java BoundaryRoundTrip
```

Expected output (independent of terminal emoji rendering because it prints only ASCII labels and numbers):

```text
file-bytes-match=true
file-text-match=true
wire-text-match=true
wrong-charset-match=false
unicode-equal-before=false
unicode-equal-after=true
utf16-units=3
code-points=2
utf8-length=5
utf8-hex=41f09f9880
```

Explanation: `wire` is the byte data an actual transport protocol would carry; `disk` is the bytes stored in the file. `Arrays.equals(wire, disk)` confirms byte-for-byte identity. `original.equals(restored)` confirms decoded text matches the source data. `original.equals(wrong)` is `false` because the same bytes were decoded under a different charset.

In a real system, replace "simulate payload" with the actual bytes received **after crossing the network/queue/message broker**; calling `getBytes(UTF_8)` on the receiving side from the original string would miss modifications that happened in transit.

## 4. Verifying Across File Boundaries

### Writing and Reading Strings with an Explicit Charset

Java 11+ provides `Files.writeString` and `Files.readString`; they use UTF-8 if no charset is passed. To make the contract visible right in the code, pass it explicitly:

```java
Files.writeString(path, source, StandardCharsets.UTF_8);
String actual = Files.readString(path, StandardCharsets.UTF_8);
boolean sameText = source.equals(actual);
```

This snippet assumes existing `path` (`Path`) and `source` (`String`) variables, along with `IOException` handling. For binary data or exact byte verification, use `Files.write(path, byte[])` and `Files.readAllBytes(path)`.

Some older APIs or overloads without an explicit charset, such as `new FileReader(file)` in Java 17, use the runtime's default charset. Do not mix default-based reading/writing arbitrarily with fixed UTF-8. Java 18+ standardizes UTF-8 as the default for many APIs via JEP 400, yet that does not automatically make all console streams and legacy files UTF-8.

### BOM, Line Endings, and Unintended Transformations

- **BOM (Byte Order Mark):** A UTF-8 file may start with three bytes `ef bb bf`. When decoded as UTF-8 into a string, this mark can appear as leading character `U+FEFF`; `"header".equals(text)` is then `false` even though the screen shows no visible mark. Strip a BOM only according to an agreed file-format policy, and never strip every `U+FEFF` arbitrarily inside content.
- **Line endings:** `\n` (LF) and `\r\n` (CRLF) are different sequences in both `String` and bytes. `readAllLines` returns lines **without line terminators**; joining them back can alter the data. When exact comparison is required, prefer `readString` or raw bytes.
- **Leading/trailing text changes:** `trim()`, `strip()`, extra `println` calls, or newline-conversion filters can alter content. Record all such transformation steps when tracking down discrepancies.
- **Charset-incompatible bytes:** Convenience `String` constructors can replace malformed bytes with `U+FFFD`. A readable string does not by itself prove all bytes complied with the agreed format.

When you know the file format allows a leading BOM, you can check:

```java
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1);
}
```

This is only an illustrative snippet after reading a file into `text`. BOM removal should happen **once at the input boundary**, with the rule clearly documented.

## 5. Verifying Across the Console

`System.out.println(text)` passes through a `PrintStream`, the console/terminal character encoder, and the display software. The text seen on screen is a **presentation result**, not proof that the underlying UTF-8 bytes or Unicode characters remain intact.

Discrepancies can arise at: the terminal or output stream's charset, shell/IDE Unicode handling, fonts lacking a glyph, stdout redirection settings to a file, and the newline appended by `println`. For instance, an emoji may appear as a box due to a missing glyph even though the bytes are valid. Conversely, when code writes a valid string to the console but redirects it to a file under a different encoding, reading that file as UTF-8 can fail.

A more reliable check is printing an **ASCII diagnostic dump** alongside the content:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String text = "A\uD83D\uDE00";
System.out.println("utf8=" +
        HexFormat.of().formatHex(text.getBytes(StandardCharsets.UTF_8)));
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

This snippet can be run in `jshell`. For this string, the output is:

```text
utf8=41f09f9880
U+0041
U+1F600
```

`codePoints()` shows the Unicode value of each code point; `HexFormat` shows the bytes when **explicitly UTF-8 encoded**. These values are not necessarily the exact bytes sent by `System.out` to the terminal. To inspect a redirected stdout file, examine the raw bytes of that file directly.

For reading from `System.in`, do not accidentally use a default reader that differs from the charset the terminal sends. Once you confirm input is UTF-8, you can create `new InputStreamReader(System.in, StandardCharsets.UTF_8)` (inside a `BufferedReader`); if the terminal actually sends another charset, forcing UTF-8 in Java will not fix the data. `System.console()` can return `null` inside an IDE or when redirected, so never assume an interactive console is always attached.

## 6. Verifying Across Wire Data (HTTP, Sockets, Messages)

A byte transport protocol does not inherently know what a "Java string" is. The sender must **specify payload encoding**; the receiver must decode consistently. For text content sent over HTTP, the charset can be declared in `Content-Type`, for example:

```http
Content-Type: text/plain; charset=UTF-8
```

If no `charset` is present or the protocol format sets its own rule, the receiver must follow that protocol's specification; do not guess the charset from how text renders. In the Java HTTP Client (Java 11+), a pair of explicit-charset choices is:

```java
// Illustrative snippet; assumes HttpRequest.Builder builder,
// HttpResponse<byte[]> response, and String text already exist.
builder.header("Content-Type", "text/plain; charset=UTF-8")
       .POST(HttpRequest.BodyPublishers.ofString(text, StandardCharsets.UTF_8));

byte[] receivedBytes = response.body();
String receivedText = new String(receivedBytes, StandardCharsets.UTF_8);
```

These two fragments illustrate opposite sides; this is **not** a standalone request-sending program. In real connections, inspect the response headers returned by the service before deciding the decoding charset. Alternatively, choose `BodyHandlers.ofString(StandardCharsets.UTF_8)` when the receiving contract is already certain. For sockets, use `OutputStreamWriter` and `InputStreamReader` with the same charset; for binary protocols, handle framing and lengths at the byte level.

**Payload length** is the byte count, not `String.length()`. For example, `"A😀"` is 3 UTF-16 units long yet occupies 5 UTF-8 bytes. Frame lengths, payload sizes, hashes, and `Content-Length` must be computed from the actual bytes sent. HTTP libraries usually calculate the length when sending a body; avoid manually supplying `text.length()`.

Also distinguish **charset** (bytes ↔ characters) from **other transport/format transformations**: gzip compression, JSON escaping, Base64, and turning `\n` into the two characters `\\n` inside JSON are separate layers. JSON payload bytes can differ from the displayed string after a parser unescapes it while still conveying the same protocol text value.

## 7. Validating Bytes Right at the Receiving Boundary

For example, `new String(bytes, StandardCharsets.UTF_8)` can replace invalid UTF-8 bytes with U+FFFD. If a message must preserve exact content, validate the **received bytes** before passing them to a parser or overwriting source data:

~~~java
byte[] malformed = {(byte) 0xC3, 0x28};
try {
    String value = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(malformed))
            .toString();
    System.out.println(value);
} catch (CharacterCodingException error) {
    System.out.println("valid-utf8=false");
}
~~~

Place this inside a method and import `java.nio.ByteBuffer` along with the relevant `java.nio.charset.*` classes. The output for the data above is `valid-utf8=false`. A strict decode proves the bytes conform to the **chosen** charset, but does not by itself prove the sender chose the right charset under the protocol. The lesson **CharsetEncoder, CharsetDecoder, and the REPORT Policy** covers strict conversion in depth, including streaming decoders.

## 8. Two Visually Identical Strings Can Still Differ

Unicode can represent accented characters in multiple ways. For example, `"\u00E9"` (single code point `é`) and `"e\u0301"` (`e` plus combining acute accent) usually look identical yet:

- `String.equals` is initially `false` because their UTF-16 unit sequences differ.
- UTF-8 bytes also differ: `c3 a9` versus `65 cc 81`.
- After `Normalizer.normalize(value, Normalizer.Form.NFC)`, the two strings become equal.

```java
import java.text.Normalizer;

String first = "\u00E9";
String second = "e\u0301";
boolean rawEqual = first.equals(second); // false
boolean normalizedEqual = first.equals(
        Normalizer.normalize(second, Normalizer.Form.NFC)); // true
```

The snippet above is illustrative. **Normalization must be a data-contract decision**, never performed haphazardly in the middle of signed payloads, file paths, identifiers, or payloads requiring byte-integrity checks: it changes the source representation. When the goal is display or normalization-insensitive search, agree on normalizing **before comparison** on both sides.

## 9. Diagnostic Workflow Across Multiple Layers

When data differs across files, console, and receiver, proceed in this order:

1. **Establish a baseline:** capture the original `String` at the sender and the `byte[]` right before leaving the process. If a file is the baseline, read raw bytes with `Files.readAllBytes`.
2. **Confirm the contract:** record the charset, payload format, whether BOM is allowed, newline conventions, Unicode normalization, and any compression/escaping layers.
3. **Compare bytes at each boundary:** use `Arrays.equals` when you have both byte arrays, or log sizes and hex/hashes of sent and received bytes. A hash only proves byte identity up to the algorithm's strength; it does not prove the characters are right.
4. **Decode with the agreed charset:** use `new String(bytes, charset)` for trusted input; use a strict `CharsetDecoder` when malformed bytes must be rejected.
5. **Compare Unicode content:** compare with `String.equals`, inspect `codePoints()` when needed, and check BOM/newlines/normalization if bytes or text do not match.
6. **Evaluate display last:** compare terminal, editor, and log viewer behavior. Font or rendering issues can differ from actual byte bugs.

| Symptom | Check First | Likely Cause and Fix |
| --- | --- | --- |
| File shows `Ã` or strange characters | Inspect hex bytes, write charset, and read charset | Wrong charset; standardize on UTF-8 across the endpoints involved |
| Emoji renders as a square box in console | Check code points and UTF-8 hex before printing | Likely terminal/font issue; do not alter bytes if source data is valid |
| File read differs at the start of the string | Check for `ef bb bf`, `U+FEFF` | BOM; agree on handling policy |
| Two visually identical strings fail `equals` | Inspect code points, combining marks, spaces/newlines | Unicode normalization or hidden characters/different line endings |
| API receives wrong byte count or truncates payload | Count `byte[].length` and inspect framing | Use byte count, not `String.length()` |
| Receiver sees `�` (U+FFFD) | Strict decode from raw bytes | Malformed bytes or charset mismatch; do not accept silent data loss |
| Content is fine in IDE, broken when stdout is redirected | Inspect bytes of the redirected file and terminal encoding | Console/redirected stream uses a different encoding configuration |

## 10. Self-Check Exercises

1. For `String s = "A\uD83D\uDE00";`, what is `s.length()`? How many code points does it have? How many bytes when UTF-8 encoded?
2. A file stores bytes `c3 a9`. Does reading it as UTF-8 vs. ISO-8859-1 produce the same characters? Do the original bytes change merely from reading?
3. Two systems transmit `"e\u0301"` and `"\u00E9"`. Why can the UI render them identically even though `String.equals` is `false`? When should you normalize before comparing?
4. If `System.out.println(text)` prints garbled characters, should you check `String.codePoints()` and UTF-8 hex first, or immediately change the file's encoding? Why?
5. When sending `"A😀"` in a UTF-8 HTTP body, can you use `String.length()` as the body length?

**Answer hints:** (1) 3 UTF-16 units, 2 code points, 5 bytes; (2) different characters because they are decoded with different charsets, while raw bytes are unchanged; (3) different Unicode representations, normalize only when the contract permits; (4) inspect code points and hex first to distinguish a data error from a display error; (5) no, the UTF-8 body is 5 bytes.

### References

- [`String` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`StandardCharsets` and `CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/package-summary.html)
- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [`Normalizer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
