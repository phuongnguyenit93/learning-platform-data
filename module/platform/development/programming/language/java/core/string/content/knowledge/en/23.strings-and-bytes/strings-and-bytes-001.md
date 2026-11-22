# Distinguishing Encoding Strings to Bytes from Decoding Bytes to Strings in Java

When Java exchanges text with files, networks, HTTP, databases, or other systems, data usually has to cross the boundary between **`String` (characters)** and **`byte[]` (bytes)**. The two operations go in **opposite directions**:

~~~text
                         ENCODE (character encoding)
String (Unicode characters) ---------------------> byte[]
       ^                                             |
       |                   DECODE                    |
       +---------------------------------------------+
                  (decode bytes into characters)

Example with the UTF-8 charset:
"café" --encode--> 63 61 66 C3 A9 --decode--> "café"
~~~

In this lesson, **encode** means *character encoding* (converting characters to bytes according to a character set, `Charset`); **decode** is the reverse direction, converting bytes to characters according to a `Charset`. This is **not security encryption** (encryption/decryption). If you want to secure data, you need separate cryptographic mechanisms; character encoding does not make data secret.

## 1. Definitions and Java APIs

| Item | Encode: String → Bytes | Decode: Bytes → String |
| --- | --- | --- |
| Input | `String` (text) | `byte[]` (binary data) |
| Output | `byte[]` | `String` |
| Conversion rules | Uses `CharsetEncoder` | Uses `CharsetDecoder` |
| Common API | `text.getBytes(charset)` | `new String(bytes, charset)` |
| `UTF-8` example | `"é"` → `C3 A9` | `C3 A9` → `"é"` |
| Error handling | Unmappable characters may be replaced or trigger an error | Malformed byte sequences may be replaced or trigger an error |

A **charset** specifies how characters are represented as byte sequences and how characters are recovered from byte sequences. In Java, use `java.nio.charset.Charset`, especially the standard constants in `java.nio.charset.StandardCharsets`:

- `StandardCharsets.UTF_8`: the widely used Unicode encoding with a variable number of bytes per character, ASCII-compatible for ASCII characters.
- `StandardCharsets.UTF_16BE`, `UTF_16LE`: UTF-16 with an explicit byte order.
- `StandardCharsets.UTF_16`: UTF-16 with BOM/byte-order rules that differ from the two endian-specific variants.
- `StandardCharsets.US_ASCII`: the ASCII range; cannot represent all Vietnamese characters.
- `StandardCharsets.ISO_8859_1`: a single-byte encoding for the Latin-1 character set; not full Unicode.

**A `String` is Unicode text in Java**, whereas bytes are an **external representation** according to a charset. Do not infer encoded bytes from how the JVM stores a `String` internally. The same `String` can produce **different** byte sequences when using UTF-8, UTF-16, or ISO-8859-1.

## 2. Encode: from `String` to `byte[]`

The familiar method is:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

The encoding process reads the character content of `text` and generates a byte sequence in UTF-8. For example:

- The letter `A` (U+0041) → UTF-8 byte `41`.
- The letter `é` (U+00E9) → two bytes `C3 A9`.
- The emoji `😀` (U+1F600) → four bytes `F0 9F 98 80`.

One visible character **does not necessarily equal one byte**. Even `String.length()` in Java returns the **number of UTF-16 code units**, not the number of Unicode code points, user-perceived characters, or encoded bytes. The emoji `😀` is one code point, yet occupies **two UTF-16 code units** and **four UTF-8 bytes**.

### Standalone Java 17 Example

~~~java
// EncodingDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class EncodingDemo {
    public static void main(String[] args) {
        String original = "Aé😀";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 hex = "
                + HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-16 units = " + original.length());
        System.out.println("Unicode code points = "
                + original.codePointCount(0, original.length()));
        System.out.println("UTF-8 bytes = " + utf8.length);

        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("Round-trip equal = " + original.equals(restored));
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 EncodingDemo.java
java EncodingDemo
~~~

Output:

~~~text
UTF-8 hex = 41C3A9F09F9880
UTF-16 units = 4
Unicode code points = 3
UTF-8 bytes = 7
Round-trip equal = true
~~~

`-encoding UTF-8` in the `javac` command only specifies the **charset of the `.java` source file**. The `StandardCharsets.UTF_8` argument inside the program is what specifies the **charset when encoding/decoding data**. These are two different places, even though both use UTF-8 in this example.

`HexFormat` (available since Java 17) only **displays bytes as hexadecimal digits for inspection**. The sequence `41 C3 A9 F0 9F 98 80` is still seven bytes, not seven characters of an original text string.

## 3. Decode: from `byte[]` to `String`

The commonly used method is:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

The decoder must know **how to interpret the bytes**. A `byte[]` by itself does not carry a "I am UTF-8" label; without an agreement or external metadata, the receiver **cannot reliably know the right charset** just by looking at the byte array.

For example, with the byte sequence `63 61 66 C3 A9`:

- Decoded with **UTF-8** → `"café"`.
- Decoded with **ISO-8859-1** → `"cafÃ©"` (the two bytes `C3` and `A9` are treated as two Latin-1 characters).

The bytes **do not change**; how they are interpreted into characters **changes**. Garbled text caused by encoding/decoding with the wrong charset is called **mojibake**.

### Example: Same Bytes, Two Ways to Decode

~~~java
// CharsetMismatchDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetMismatchDemo {
    public static void main(String[] args) {
        String original = "café";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(bytes, StandardCharsets.UTF_8);
        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);

        System.out.println("Bytes = "
                + HexFormat.of().withUpperCase().formatHex(bytes));
        System.out.println("Correct = " + correct);
        System.out.println("Wrong = " + wrong);
        System.out.println("Correct equal = " + original.equals(correct));
        System.out.println("Wrong equal = " + original.equals(wrong));
    }
}
~~~

Run `javac --release 17 -encoding UTF-8 CharsetMismatchDemo.java` and `java CharsetMismatchDemo`. On a terminal that displays Unicode properly, the output is:

~~~text
Bytes = 636166C3A9
Correct = café
Wrong = cafÃ©
Correct equal = true
Wrong equal = false
~~~

If the terminal or logging system also uses a different display charset, the printed text on screen may be further distorted. When investigating an issue, inspect the **hex of the input bytes**, the **declared charset**, the **decoded string**, and the **charset of the output display** as separate steps.

## 4. Why Must Both Sides Use the Same Charset?

The usual goal is:

~~~text
Original String
   | encode with charset X
   v
byte[]
   | store/transmit intact
   v
byte[]
   | decode with charset X
   v
Restored String
~~~

With valid Unicode data and UTF-8, a normal round-trip preserves the content:

~~~java
String input = "Café and 😀";
byte[] wire = input.getBytes(StandardCharsets.UTF_8);
String output = new String(wire, StandardCharsets.UTF_8);
System.out.println(input.equals(output)); // true
~~~

However, "encode then decode with the same charset always recovers 100%" is **not unconditionally true**:

1. **The charset may not be able to represent a character**: for example, `US_ASCII` cannot represent `é` or Vietnamese characters with diacritics. If the API uses replacement mode, the original data is lost right in the encode step.
2. **A Java string may contain unpaired UTF-16 surrogates**: such a string cannot be represented directly as valid Unicode scalar values in UTF-8; the encoder may replace them or report an error.
3. **Byte sequences can be corrupted or truncated mid-character** during transmission/storage, causing incorrect decoding or errors.
4. **Two endpoints using different charsets** will interpret the bytes incompatibly.
5. **Another transformation step** between the two sides (Unicode normalization, line-ending conversion, content editing, character replacement, etc.) can make the two `String`s differ even with the right charset.

UTF-8 is a good default choice for new protocols and text files when both sides agree on UTF-8. For legacy data using another charset, you must follow the charset **actually used when creating the bytes**, rather than arbitrarily switching to UTF-8 at the decode step.

## 5. When Encode/Decode Cannot Preserve Data

Even when writing the conversion direction correctly, a round-trip result is not guaranteed to equal the original if the data is invalid or the charset cannot represent the character. Distinguish these three scenarios:

| Scenario | What Happens | How to Handle |
| --- | --- | --- |
| `"café"` encoded with US-ASCII | `é` has no corresponding code; `getBytes(US_ASCII)` typically replaces it with the `?` byte | Choose a charset that can represent the data or use `CharsetEncoder` with `REPORT` |
| UTF-8 bytes `C3 28` decoded with UTF-8 | Byte `C3` lacks a valid continuation byte; `new String` typically inserts U+FFFD (`�`) | Use `CharsetDecoder` with `REPORT` if malformed bytes must be rejected |
| UTF-8 bytes `C3 A9` decoded with ISO-8859-1 | The bytes may be valid in Latin-1, producing `Ã©` instead of `é` (mojibake) | Re-verify the source charset; inspect the original bytes before converting |

Convenience constructors and methods usually use **replacement** mode, which can lose data without throwing an exception. The small example below contrasts a lenient decoder with a strict decoder:

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};
String lenient = new String(invalid, StandardCharsets.UTF_8);
System.out.println(lenient.codePointAt(0) == 0xFFFD); // true

try {
    StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(invalid));
} catch (CharacterCodingException ex) {
    System.out.println(ex.getClass().getSimpleName()); // MalformedInputException
}
~~~

This is a snippet to place inside a method, with imports `java.nio.ByteBuffer`, `java.nio.charset.CharacterCodingException`, `CodingErrorAction`, and `StandardCharsets`. The lesson **Malformed Data, Replacement Characters, and Data Loss** analyzes data-loss scenarios; the lesson **CharsetEncoder, CharsetDecoder, and the REPORT Policy** explains these two APIs, including chunk-by-chunk processing via `CoderResult`.

## 6. The Default Charset Is Not a Data Exchange Contract

`text.getBytes()` and `new String(bytes)` use the JVM's default charset. On JDK 17 and earlier, the default charset often depends on the operating system/locale; starting with JDK 18, JEP 400 specifies UTF-8 in standard configurations, though legacy data or compatibility modes still require attention. `Charset.defaultCharset()` returns the actual value of the running JVM.

In new protocols and files where UTF-8 has been chosen, always write `getBytes(StandardCharsets.UTF_8)` and `new String(bytes, StandardCharsets.UTF_8)`. If the source data uses another charset, you must **decode using the source charset** rather than arbitrarily forcing UTF-8. The lesson **Default Charset and Environment or JDK Version Effects** covers JEP 400, affected APIs, and how to test during upgrades.

## 7. Applying Encode/Decode at Real-World Boundaries

Example of text data passing through a file or network:

~~~text
Source String
   | getBytes(UTF_8)
   v
byte[] -- write file / send over network / store raw bytes --> byte[]
   | new String(bytes, UTF_8)
   v
Receiver String
~~~

- For text files, `Files.writeString(path, text, StandardCharsets.UTF_8)` and `Files.readString(path, StandardCharsets.UTF_8)` specify both directions directly in the I/O API. When comparing byte integrity, use `Files.write`/`readAllBytes` and compare `byte[]`.
- For HTTP/JSON, determine the charset according to the **format or protocol specification** and only measure `Content-Length` from the actual byte body being sent. JSON escaping, headers, or compression are separate steps that can make the final size differ from the initial string's size.
- For streams, a multi-byte UTF-8 character can be split across two reads. Use `InputStreamReader` with the chosen charset or a stateful decoder; decoding each byte chunk independently can produce replacement characters.

The lesson **Comparing Strings Across File, Console, and Wire Boundaries** provides a complete runnable example to inspect bytes at multiple checkpoints and distinguish data errors from terminal display errors.

## 8. A Few Non-Charset Factors to Distinguish

- **BOM**: A UTF-8 BOM `EF BB BF` often appears as U+FEFF after decoding; handle it only according to the file format's rules. UTF-16BE/LE require an agreement on byte order and BOM usage.
- **Unicode normalization**: `é` can be U+00E9 or `e` + U+0301. The two representations may look identical yet still differ in bytes; a charset does not normalize automatically.
- **Binary representations**: Images, ZIP files, and audio are not naturally text. Decoding them into a `String` can corrupt or lose bytes, even if encoded back afterward.
- **Base64 and escaping**: Base64 converts bytes into ASCII characters for transport; escaping preserves syntax in Java/JSON/HTML. Both are distinct from character encoding.

## 9. Checklist Before Integration

1. Does the producer have **text** or **binary bytes**?
2. What is the source charset, and where is it documented in the protocol/contract?
3. Before decoding, are the bytes preserved intact and should malformed input be rejected?
4. Before encoding, can the target charset represent every character that needs to be sent?
5. When a discrepancy occurs, have you inspected hex bytes, code points, and the display layer's charset separately?

## 10. Distinguishing the Right Path from the Wrong Path

~~~java
String input = "café";
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);
String right = new String(utf8, StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);

System.out.println(input.equals(right)); // true
System.out.println(input.equals(wrong)); // false
~~~

This is an illustrative snippet inside a method. Both `new String` calls read **the exact same byte sequence**; only the charset differs. Therefore, always start from the source byte contract, then verify each transformation layer as the application moves through files, networks, or new environments.

## 11. Self-Check Questions

**Question 1.** How many bytes does `"é".getBytes(StandardCharsets.UTF_8)` produce? If decoded with `ISO_8859_1`, what string does it produce?

**Answer:** Two bytes `C3 A9`; decoding as Latin-1 produces `"Ã©"` because the two bytes are interpreted as two separate characters.

**Question 2.** Why is `"😀".length()` equal to `2` in Java while UTF-8 encoding produces `4` bytes?

**Answer:** `String.length()` counts the **two UTF-16 code units** representing one code point U+1F600, whereas UTF-8 encodes that code point using **four bytes**.

**Question 3.** When Java reads two byte chunks from a socket, why should you not call `new String(chunk, UTF_8)` separately on each chunk?

**Answer:** A multi-byte UTF-8 character can straddle the boundary between chunks; an independent decoder on each chunk treats the incomplete bytes as an error. Use a stateful decoder or `InputStreamReader`.

**Question 4.** What problem can encoding `"café"` with US-ASCII cause? If you want an error instead of character replacement, what should you use?

**Answer:** `é` is not in ASCII; lenient encoding APIs may replace it, causing data loss. Use `CharsetEncoder` with `onUnmappableCharacter(CodingErrorAction.REPORT)`.

**Question 5.** If the bytes of a ZIP file are loaded into a `String` using UTF-8 and then encoded back, is the original file guaranteed to be preserved?

**Answer:** No. A ZIP file is binary data and may contain byte sequences that are invalid in UTF-8, which the decoder will replace. Keep it as raw bytes or a byte stream.

## Key Takeaways

**Encode** is `String → byte[]` using a charset; **decode** is `byte[] → String` using a charset. To restore data accurately, you need **intact bytes**, a **consistent charset**, and an **appropriate error-handling policy**. Use `StandardCharsets.UTF_8` explicitly for new text data when the protocol allows; inspect bytes in hex when errors happen; use `CharsetEncoder`/`CharsetDecoder` in `REPORT` mode when data loss is unacceptable.
