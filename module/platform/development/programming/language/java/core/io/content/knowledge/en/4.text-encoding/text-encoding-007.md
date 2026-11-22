# Mojibake Errors When Encoding and Decoding Use Different Charsets

## 1. What Is Mojibake?

**Mojibake** is the phenomenon where text displays as wrong, garbled, or unreadable characters because **byte data was decoded using a different charset than the one used to encode it**, or because an intermediate conversion step used an incompatible charset.

Typical example:

- Correct data: `café`.
- Encoded as UTF-8: bytes `63 61 66 C3 A9`.
- Mis-decoded entirely as ISO-8859-1: displays `cafÃ©`.
- Decoded **correctly** as UTF-8: displays `café`.

In Java I/O, the key point to remember is that **a `String` in memory and bytes on disk/network live at two different layers**. The charset determines how conversion happens between those two layers.

~~~text
String "café"
    |
    | encode UTF-8
    v
Bytes: 63 61 66 C3 A9
    |
    +--- decode UTF-8 --------> "café"   (correct)
    |
    +--- decode ISO-8859-1 ---> "cafÃ©" (mojibake)
~~~

The word “mojibake” describes the **symptom of garbled characters**, not the name of a charset or a specific file format. Text with Vietnamese diacritics turning into `Ã`, `Â`, `áº`, `á»`... is a common sign, yet **you cannot diagnose the exact bug solely from the appearance of a few characters**.

Mojibake differs from a font issue: if the underlying character string is already wrong due to mis-decoding, changing the font usually will not fix it. If the code points are right yet the font lacks a glyph, the issue belongs to rendering; inspect both to tell them apart.

## 2. Encode, Decode, and Charset Must Be Compatible

**Encode** converts Unicode characters into bytes per a charset; **decode** converts bytes into characters per a charset.

For example, the Unicode code point of `é` is U+00E9:

| Charset | Bytes representing `é` |
| --- | --- |
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| UTF-16BE | `00 E9` |
| UTF-16LE | `E9 00` |

A byte can carry different meanings depending on the charset. When an ISO-8859-1 decoder receives `C3 A9`, it interprets them as two characters U+00C3 (`Ã`) and U+00A9 (`©`). When a UTF-8 decoder receives those exact same two bytes, it produces one code point U+00E9 (`é`). That is the exact mechanism behind `é → Ã©`.

**There is no “charset of a Java `String`” in the sense of a file charset**: `String` is Java's Unicode character model. Only when calling `getBytes(charset)` to send a `String` to a file/network, or `new String(bytes, charset)` to read it back in, do we choose a transformation rule. A Java `char` is a UTF-16 code unit; `String.length()` counts UTF-16 code units, not UTF-8 bytes.

The same message must have a **unified contract**:

~~~text
Writer                    Reader
String --encode UTF-8--> Bytes --decode UTF-8--> String
~~~

If the writer uses UTF-8 and the reader uses ISO-8859-1 or Windows-1252, character data can be corrupted even while the bytes in the file or packet remain intact. If the writer uses ISO-8859-1 while the reader uses UTF-8, a byte such as `E9` is invalid as a standalone UTF-8 character; the decoder may report an error or generate a replacement character depending on the API/policy.

**Note:** A charset is not a file format. JSON, CSV, XML, and text logs have their own syntax rules while also needing an encoding to turn bytes into characters. Reading with the right charset is not yet equivalent to parsing the data properly.

## 3. Java 17 Example: Creating Mojibake and Recovering When Information Remains Intact

Create file **MojibakeDemo.java** (save source as UTF-8):

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class MojibakeDemo {
    public static void main(String[] args) {
        String original = "café";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(bytes, StandardCharsets.UTF_8);
        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);

        // Only feasible because the ISO-8859-1 mapping in the erroneous step
        // preserved each byte's value and the String has not yet been altered.
        byte[] recoveredBytes =
                wrong.getBytes(StandardCharsets.ISO_8859_1);
        String recovered =
                new String(recoveredBytes, StandardCharsets.UTF_8);

        System.out.println("utf8Hex=" + HexFormat.of().formatHex(bytes));
        System.out.println("correct=" + correct);
        System.out.println("wrong=" + wrong);
        System.out.println("recovered=" + recovered);
        System.out.println("sameBytes=" + Arrays.equals(bytes, recoveredBytes));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
~~~

Output when the terminal displays Unicode properly:

~~~text
utf8Hex=636166c3a9
correct=café
wrong=cafÃ©
recovered=café
sameBytes=true
~~~

Step-by-step explanation:

1. `getBytes(UTF_8)` encodes `café` into `63 61 66 C3 A9`.
2. `new String(bytes, UTF_8)` interprets `C3 A9` as one character `é`.
3. `new String(bytes, ISO_8859_1)` interprets `C3` and `A9` as two characters `Ã©`: mojibake.
4. Because ISO-8859-1 maps every byte value 0–255 one-to-one to the corresponding code point, `wrong.getBytes(ISO_8859_1)` reconstructs the original bytes.
5. Decoding the recovered bytes with UTF-8 yields `café` again. The assertion `sameBytes=true` confirms this in the example.

**Do not generalize the recovery step in step 4 to every corrupted string.** It works only when the exact transformation history is known and the bytes were preserved. If the system has already replaced characters with `?`, the U+FFFD replacement character (`�`), stripped diacritics, normalized, or edited the string, reverse-encoding may not recover the original bytes.

Additional note: printing to the terminal is also a step that outputs characters to bytes. If the console picks an unsuitable encoding/font, terminal output can look wrong even when the Java `String` is completely right. Inspect hex bytes and `equals` results alongside visual appearance.

## 4. Where Does Mojibake Appear in Java I/O Flows?

Errors commonly arise at **String ↔ byte boundaries**, especially if one side uses an implicit charset:

~~~text
Java String
   -> Writer / OutputStreamWriter / getBytes(charset)
   -> bytes on file, network, queue, DB driver
   -> Reader / InputStreamReader / new String(bytes, charset)
   -> Java String
   -> logger / terminal / browser
~~~

If a file is written in UTF-8 yet read back in another charset:

~~~java
// Code snippet inside a method that has Path path and handles IOException.
Files.writeString(path, "café", StandardCharsets.UTF_8);

String correct = Files.readString(path, StandardCharsets.UTF_8);
String wrong = Files.readString(path, StandardCharsets.ISO_8859_1);
~~~

`correct` holds `café`, while `wrong` holds `cafÃ©`. `readString` only decodes the file; it does not auto-detect which charset created the file.

For streams, place the charset at the exact bridge:

~~~java
// Code snippet with InputStream input and a Reader closed within scope.
try (var reader = new java.io.InputStreamReader(
        input, StandardCharsets.UTF_8)) {
    // Read characters from reader.
}
~~~

The writing side uses `OutputStreamWriter(output, StandardCharsets.UTF_8)`. When working purely with bytes to copy a file, use `InputStream`/`OutputStream` directly; do not convert to `String`.

For HTTP communication, inspect `Content-Type`, the `charset` parameter when applicable, media-type rules, and how the framework/SDK decodes payloads. For CSV export/import and legacy systems, the sender and receiver charset settings must match. **Do not blindly assign ISO-8859-1 or UTF-8 merely because the system “usually uses” that charset.**

## 5. Symptoms and Limits of Guessing the Error

| Symptom | Likely Possibility | What to Check |
| --- | --- | --- |
| `é` becomes `Ã©`; `à` becomes `Ã ` | UTF-8 interpreted as Latin-1/Windows-1252 | Source bytes, charset at the decode step |
| Some characters become `�` | Decoder replaced malformed byte sequences with U+FFFD | Bytes before decode; error-handling policy |
| Unsupported letters become `?` | Encoder replaced unmappable characters with `?` | Charset at encode time and byte `3F` |
| File starts with `ï»¿` | UTF-8 BOM interpreted as Latin-1 characters | First three bytes `EF BB BF`, BOM policy |
| Correct in file, wrong in terminal | Console encoding or font | Actual bytes and `String` before printing |
| Letters right yet diacritics render/combine oddly | May be normalization, font/rendering, or mark order | Actual code points, Unicode normalization |

The table above is a set of **diagnostic clues**, not conclusive proof: many distinct error chains can look alike. For instance, `Ã©` may have been stored *as literal content* by an upstream system; in that case, the current UTF-8 file decodes accurately, yet the text itself was already corrupted earlier.

**Mojibake and data loss are two different issues:**

- If the original bytes remain intact in files/logs/protocols, they can usually be re-read using the right charset.
- If only the `cafÃ©` `String` remains yet you know it was mis-decoded as ISO-8859-1, you can sometimes reconstruct the bytes as in the example.
- If the system replaced unmappable bytes/characters with `?` or `�`, multiple original values collapse into the same replacement character; exact recovery usually cannot be guaranteed without the original copy.
- If data went through multiple erroneous encode/decode passes, reconstruct *each step* before attempting a fix; applying a generic formula blindly easily corrupts the data again.

## 6. Data Loss Example: Character Outside the Target Charset

Using US-ASCII to encode `é` is wrong when accents must be preserved, because US-ASCII cannot represent that code point. Convenience APIs may substitute a replacement byte.

~~~java
// Illustrative snippet; StandardCharsets is already imported.
String original = "é";
byte[] bytes = original.getBytes(StandardCharsets.US_ASCII);
String after = new String(bytes, StandardCharsets.US_ASCII);

System.out.println(java.util.HexFormat.of().formatHex(bytes));
System.out.println(after);
~~~

Default output of `String.getBytes(StandardCharsets.US_ASCII)` for an unmappable character:

~~~text
3f
?
~~~

Byte `3F` represents the question mark `?`. It is impossible to tell whether the original character was `é`, `€`, or another character from byte `3F` alone. This is **loss during the encode step**, unlike when UTF-8 bytes remain intact yet are mis-decoded.

When you need to **detect** errors instead of silently replacing them, use `CharsetEncoder`/`CharsetDecoder` with `CodingErrorAction.REPORT`.

Create **StrictDecodeDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodeDemo {
    public static void main(String[] args) {
        // E9 is 'é' in ISO-8859-1 yet does not by itself form
        // a valid UTF-8 character when standing alone.
        byte[] sourceBytes = {(byte) 0xE9};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            decoder.decode(ByteBuffer.wrap(sourceBytes));
            System.out.println("valid UTF-8");
        } catch (CharacterCodingException exception) {
            System.out.println("invalid UTF-8");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictDecodeDemo.java
java StrictDecodeDemo
~~~

Stdout:

~~~text
invalid UTF-8
~~~

A single `E9` byte cannot form a valid UTF-8 sequence; the decoder reports an error. Instead of continuing to process data with replaced characters, this lets the program stop and report the encoding contract violation early.

**Note:** Checking UTF-8 validity only answers “can it be decoded as UTF-8?” It does not prove a file is definitely text, because arbitrary binary data might happen to contain valid UTF-8 byte sequences.

## 7. Double Encoding: Why Do Multiple Layers of Garbled Characters Sometimes Appear?

Mojibake can be **saved back as a String** and then encoded into a new UTF-8 file. The new file is then valid UTF-8, yet its contents are the corrupted characters from the previous decode step.

Example with a single `é`:

~~~text
Original:               é
Original UTF-8:         C3 A9
Mis-decoded Latin-1:    Ã©
Saved "Ã©" as UTF-8:    C3 83 C2 A9
Read new file as UTF-8: Ã©  (still semantically wrong)
~~~

If those UTF-8 bytes are again misinterpreted, the string can become distorted by yet another layer. This is why some logs or exports contain repeated `Ãƒ`, `Â` clusters. Each erroneous processing layer must be identified from actual logs/bytes; merely changing the charset of the final read step will not fix content already saved incorrectly in an earlier step.

When reading a file produces `cafÃ©` yet the bytes of the current file are the UTF-8 encoding of the exact string `cafÃ©`, the application read the current bytes **accurately**. The bug happened before saving, so you must trace back to where the `String` was constructed from bytes using the wrong charset.

## 8. Controlled Investigation and Remediation Workflow

**Step 1 — Preserve the original bytes.** Before fixing anything, keep the original file or an immutable copy. Avoid opening and saving in a text editor with a guessed charset. For network data, capture the byte payload or hex dump at the appropriate I/O boundary.

**Step 2 — Pinpoint where the text was still right.** Compare the `String` before encode, bytes after encode, bytes before decode, `String` after decode, and finally the display layer. If the `String` is right before `System.out.println` yet the terminal is wrong, do not rush to change file-reading logic.

**Step 3 — Measure the actual bytes and charsets.** Use `HexFormat` in Java 17 to inspect bytes; verify `StandardCharsets.UTF_8`, `ISO_8859_1`, API/framework charsets, HTTP `charset`, CSV export settings, and the integrator's decoder/encoder. Do not use `String.length()` as the byte count.

**Step 4 — Reproduce with minimal data.** A word like `café`, `cà phê`, or an accented name is enough to isolate the bug. Compare both the displayed string and the byte hex before/after each step.

**Step 5 — Fix at the faulty boundary.** If a UTF-8 file was read as Latin-1, change the charset choice at the *read step*. If the source produced the wrong bytes, fix the encoder/export settings. If a file already stores mojibake `String`s saved in UTF-8, restore from the original source or verify the transformation history before building a migration tool.

**Step 6 — Verify and prevent.** Test round-trips with Vietnamese characters, diacritics, non-ASCII characters, and malformed input cases. Compare bytes when data must remain unchanged; for text, verify Unicode strings after parsing. Place integration tests along the actual flow (file → service → API → consumer) to catch mismatches across systems.

A proactive diagnostic pattern in Java:

~~~java
// Code snippet given byte[] payload and String candidate.
String hex = java.util.HexFormat.of().formatHex(payload);
String decoded = new String(payload, StandardCharsets.UTF_8);
boolean same = candidate.equals(decoded);
// Write hex/charset to appropriate technical logs; do not log sensitive data.
~~~

Hex only describes bytes; it does not by itself tell you which charset should decode those bytes. When a product processes user data, take care not to write personal content or sensitive payloads to logs.

## 9. Designing Applications to Prevent Mojibake

- **Specify the charset at every conversion point.** For UTF-8 text, use `StandardCharsets.UTF_8` with `Files.readString`, `Files.writeString`, `InputStreamReader`, `OutputStreamWriter`, or `String.getBytes`/`new String`.
- **Define encoding explicitly in integration contracts.** CSV files, emails, HTTP APIs, queue messages, and database imports/exports require agreed charsets and matching metadata.
- **Separate text from binary.** For images, ZIPs, or binary payloads, pass bytes directly; do not use `String` as an arbitrary byte container.
- **Keep Unicode end-to-end.** Keep `String` in the business layer, encode only when exiting to I/O and decode only when entering from I/O; avoid pointless extra encode/decode passes.
- **Do not rely unconsciously on the default charset.** Modern Java has default-behavior changes across versions and environments; explicitly specified charsets are far easier to control.
- **Report errors when data preservation is required.** Use `CharsetDecoder`/`CharsetEncoder` with `CodingErrorAction.REPORT` when invalid inputs or unmappable characters must be rejected.
- **Test with multilingual data.** Do not test with ASCII alone: ASCII shares identical bytes across UTF-8 and many other charsets, hiding mismatches; include Vietnamese, accented characters, and characters outside legacy charsets.
- **Avoid “fixing” data via blind conversions.** Before re-encoding a garbled `String`, verify the original charset, the broken step, reversibility, and impact on records that were already correct.

## 10. Self-Check Exercises

**Question 1.** The true data is `café`; after receiving `cafÃ©`, can you conclude that the original dataset has been lost?  
**Answer:** Not necessarily. If the UTF-8 bytes `63 61 66 C3 A9` remain intact and were merely mis-decoded as ISO-8859-1, they can be decoded properly again. If characters were already replaced and the original bytes are gone, information may be lost.

**Question 2.** Why is `new String(bytes, StandardCharsets.UTF_8)` only correct when `bytes` is known to be UTF-8?  
**Answer:** Because the decoder interprets bytes according to UTF-8 rules. If the bytes were encoded with another charset, the result can be wrong or trigger errors; the constructor does not discover the original charset automatically.

**Question 3.** The character `é` is encoded using US-ASCII into `?`. Can re-encoding `?` as UTF-8 fix it?  
**Answer:** No. The original character was already replaced with `?` in the first encoding step; UTF-8 simply encodes the existing `?` character faithfully.

**Question 4.** A current UTF-8 file contains the string `cafÃ©`. Does changing `readString(path, UTF_8)` to `readString(path, ISO_8859_1)` always fix it?  
**Answer:** No. The file may already store the exact UTF-8 bytes of the mojibake string from a prior step. You must trace the data history, identifying original bytes and the charset of each step.

**Question 5.** Why should you inspect hex bytes instead of only looking at rendered text?  
**Answer:** The console/font can make text look wrong even when the `String` is right; hex shows the actual bytes that crossed the I/O boundary, helping pinpoint whether encoding or decoding failed.

**Question 6.** When you need to reject invalid UTF-8 bytes instead of displaying `�`, which API should you use?  
**Answer:** `CharsetDecoder` with `CodingErrorAction.REPORT`, then handle `CharacterCodingException`.

**Lesson conclusion:** Mojibake typically arises when writer and reader **do not use the same charset**, or when an intermediate step saved a mis-decoded `String`. To fix it accurately, distinguish **original bytes**, **decoded `String`**, **the charset at each I/O boundary**, and the possibility of **data loss from character replacement**. In Java, prefer explicit charsets and verify bytes/round-trips before modifying live data.