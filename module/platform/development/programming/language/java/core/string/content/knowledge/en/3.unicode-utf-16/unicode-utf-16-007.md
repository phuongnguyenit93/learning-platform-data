# Java's `String` UTF-16 Model Differs from File Charsets

When learning Java, people often say “`String` uses UTF-16”, yet a text file may have a charset like UTF-8, UTF-16LE, or another charset. **These two statements describe two different layers**: the character-manipulation model inside Java and how text is represented as **bytes** when saved to a file or transmitted over a network. Confusing these two layers leads to length-counting bugs, broken string slicing, garbled Vietnamese text, replacement character issues, and choosing the wrong charset.

## 1. Distinguishing Unicode, the `String` Model, and Charsets

| Concept | Meaning | Example |
| --- | --- | --- |
| Unicode code point | An identifying value for a Unicode character element | `U+0041` is A, `U+00E9` is é, `U+1F600` is 😀 |
| UTF-16 code unit | A 16-bit code unit; a code point can take one or two units | Emoji 😀 needs the surrogate pair `D83D DE00` |
| Java `String` model | Indices and APIs like `length()`, `charAt()` are defined in terms of UTF-16 code units | `"😀".length() == 2` |
| File charset | Rules for encoding/decoding text to/from bytes | UTF-8, UTF-16LE, UTF-16BE, Windows-1252 |

**The `String` model** is how Java APIs view a string. A `char` is one UTF-16 code unit; `length()` counts the number of code units; `charAt()` and `substring()` indices are also measured in these code units. **A file's charset** is the choice made at the point of converting a string to bytes (encode) or bytes to a string (decode).

Therefore, the exact same `String` object can be saved as a UTF-8 file or a UTF-16LE file. When reading both files with their respective charsets, you can recover **the same `String` content**. The charset used to save a file does not become a permanent property of the `String`.

### “`String` uses UTF-16” does not mean “memory is always `char[]`”

Do not infer that every JVM always holds an array of two bytes per `char` inside a `String` object. Since Java 9, OpenJDK includes the **Compact Strings** optimization, allowing a more compact representation for strings that fit in Latin-1. Internal memory layout is an implementation detail, whereas behavior observed through `String.length()`, `charAt()`, and `codePointCount()` still follows the UTF-16-based API contract. In particular, the internal bytes of a `String` are **not** the bytes written to a file.

## 2. Illustration: One String, Three Ways to Measure

Consider the string:

~~~java
String text = "Aé😀";
~~~

| Character | Unicode code point | UTF-16 code unit | UTF-8 bytes |
| --- | --- | --- | --- |
| A | `U+0041` | `0041` (1 unit) | `41` (1 byte) |
| é | `U+00E9` | `00E9` (1 unit) | `C3 A9` (2 bytes) |
| 😀 | `U+1F600` | `D83D DE00` (2 units) | `F0 9F 98 80` (4 bytes) |
| **Total** | **3 code points** | **4 UTF-16 units** | **7 UTF-8 bytes** |

Hence:

- `text.length()` equals **4**, because UTF-16 requires four code units.
- `text.codePointCount(0, text.length())` equals **3**.
- `Character.isHighSurrogate(text.charAt(2))` equals `true`: position 2 is the first half of the emoji's surrogate pair.
- `text.getBytes(StandardCharsets.UTF_8).length` equals **7**.
- `text.getBytes(StandardCharsets.UTF_16LE).length` equals **8** (4 units times 2 bytes).

**Do not equate code points with user-perceived characters.** A displayed character cluster can contain multiple code points, such as a base letter plus a combining mark or a joined emoji. For Unicode data, UTF-16 code units, code points, and *grapheme clusters* are three distinct concepts.

## 3. Conversion Flow from `String` to File and Back

~~~text
Unicode content, e.g. "Aé😀"
               |
               v
     Java String (UTF-16 API)
     length() / charAt() / substring()
               |
               | ENCODE: getBytes(charset)
               | or Files.writeString(path, text, charset)
               v
     Byte sequence in the chosen charset
     UTF-8   : 41 C3 A9 F0 9F 98 80
     UTF-16LE: 41 00 E9 00 3D D8 00 DE
               |
               v
         File on disk
               |
               | DECODE: new String(bytes, charset)
               | or Files.readString(path, charset)
               v
     Java String (API still UTF-16)
~~~

Encoding and decoding are **data conversion operations**, not operations that change the “type” of a `String`. Bytes generated from UTF-8 and UTF-16LE can look completely different, yet decoding with **the right charset and valid data** yields the same string again.

A `.txt` file extension does not guarantee a charset on its own. You must know the charset from the format specification, protocol, metadata, or agreement with the system that produced the data. You cannot reliably guess a charset with 100% accuracy for arbitrary byte sequences.

## 4. Standalone Runnable Java 17+ Example: Inspecting UTF-16 and Actual Bytes

Create the file **StringCharsetDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

public class StringCharsetDemo {
    public static void main(String[] args) throws Exception {
        String text = "Aé😀";

        System.out.println("UTF-16 units = " + text.length());
        System.out.println("Unicode code points = "
                + text.codePointCount(0, text.length()));
        System.out.println("high surrogate at index 2 = "
                + Character.isHighSurrogate(text.charAt(2)));

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] utf16le = text.getBytes(StandardCharsets.UTF_16LE);
        byte[] utf16 = text.getBytes(StandardCharsets.UTF_16);
        HexFormat hex = HexFormat.ofDelimiter(" ").withUpperCase();

        System.out.println("UTF-8 bytes = " + utf8.length);
        System.out.println("UTF-8 hex = " + hex.formatHex(utf8));
        System.out.println("UTF-16LE bytes = " + utf16le.length);
        System.out.println("UTF-16LE hex = " + hex.formatHex(utf16le));
        System.out.println("UTF-16 bytes = " + utf16.length);
        System.out.println("UTF-16 hex = " + hex.formatHex(utf16));

        String decoded = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 decode equals original = "
                + text.equals(decoded));

        Path tempFile = Files.createTempFile("string-charset-", ".txt");
        try {
            Files.writeString(tempFile, text, StandardCharsets.UTF_8);
            String loaded = Files.readString(tempFile, StandardCharsets.UTF_8);

            System.out.println("file round-trip = " + text.equals(loaded));
            System.out.println("file bytes equal UTF-8 = "
                    + Arrays.equals(Files.readAllBytes(tempFile), utf8));
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Compile with JDK 17 or newer and run:

~~~bash
javac -encoding UTF-8 StringCharsetDemo.java
java StringCharsetDemo
~~~

**Expected output:**

~~~text
UTF-16 units = 4
Unicode code points = 3
high surrogate at index 2 = true
UTF-8 bytes = 7
UTF-8 hex = 41 C3 A9 F0 9F 98 80
UTF-16LE bytes = 8
UTF-16LE hex = 41 00 E9 00 3D D8 00 DE
UTF-16 bytes = 10
UTF-16 hex = FE FF 00 41 00 E9 D8 3D DE 00
UTF-8 decode equals original = true
file round-trip = true
file bytes equal UTF-8 = true
~~~

Explanation of each result:

1. **4 UTF-16 units** reflects `String`'s API model, not 4 bytes in a file.
2. **7 UTF-8 bytes** and **8 UTF-16LE bytes** both encode the same three code points.
3. With `StandardCharsets.UTF_16`, the Java encoder writes the BOM `FE FF`, followed by UTF-16 big-endian: `00 41 00 E9 D8 3D DE 00`. Hence **10 bytes** in total. The BOM lives in **the byte output**, not as two hidden bytes inside every `String`.
4. `new String(utf8, StandardCharsets.UTF_8)` decodes back to text, so `equals()` returns `true`.
5. `Files.writeString` saves **UTF-8 bytes** according to the passed charset; the program reads the file as UTF-8, compares both the content and the actual bytes, and deletes the temporary file in `finally`.

The `javac -encoding UTF-8` flag only tells the compiler that **Java source files** are saved in UTF-8. It does not automatically set the charset for data files created by your program; the file charset in the example comes from the `StandardCharsets.UTF_8` argument passed to the I/O API.

## 5. How Do API UTF-16 and File Charset UTF-16 Differ?

| Charset | When outputting data as bytes | Details to note |
| --- | --- | --- |
| UTF-8 | Each code point typically uses 1–4 bytes | No byte order for 16-bit units |
| UTF-16LE | Each UTF-16 code unit uses 2 bytes, low byte first | `U+0041` becomes `41 00`; Java's encoder does not write a BOM |
| UTF-16BE | Each UTF-16 code unit uses 2 bytes, high byte first | `U+0041` becomes `00 41`; Java's encoder does not write a BOM |
| UTF-16 (`StandardCharsets.UTF_16`) | Uses a convention with BOM to determine byte order when decoding | Java encodes by default with BOM `FE FF` and big-endian content; decoder uses big-endian if BOM is absent |

A **BOM** (*byte order mark*) is a byte marker used to identify byte order in certain encodings. For instance, `FE FF` indicates big-endian in UTF-16 and `FF FE` indicates little-endian. That does not mean every UTF-8 or UTF-16LE file must have a BOM. Follow the conventions of the data source and the APIs in use.

For example, the letter A is represented differently:

- `UTF-8`: `41`.
- `UTF-16LE`: `41 00`.
- `UTF-16BE`: `00 41`.
- `UTF-16` written by Java's encoder: `FE FF 00 41` (including BOM).

All four cases can decode into `String "A"` with `length() == 1`. The UTF-16 charset used to **store/read bytes** introduces byte-order concerns, unlike the `charAt()`, `length()` contract when operating on `String`.

## 6. Reading and Writing Files with an Explicit Charset

Example using `Files.writeString()` and `Files.readString()`, available since Java 11. Create the file **Utf8FileExample.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8FileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes-utf8.txt");

        String original = "Xin chào Java 😀";
        Files.writeString(path, original, StandardCharsets.UTF_8);

        String restored = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(original.equals(restored));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 Utf8FileExample.java
java Utf8FileExample
~~~

Stdout:

~~~text
true
~~~

The program creates/overwrites `notes-utf8.txt` in the working directory. In real applications, control paths, permissions, and overwrite policies. While in `String original`, the content still has UTF-16 semantics per the Java API; it **is encoded into UTF-8 at the file-writing call**.

For a file known to be UTF-16LE, the following snippet must read using UTF-16LE:

~~~java
String text = Files.readString(
        Path.of("external-utf16le.txt"),
        StandardCharsets.UTF_16LE);
~~~

This is only an **illustrative code snippet** inside a method that handles or declares `IOException` and imports `Files`, `Path`, and `StandardCharsets`. Choose the charset matching the file's actual data. Once decoded, `text` is an ordinary Java `String`.

**Note on defaults:** The two overloads `Files.readString(path)` and `Files.writeString(path, text)` use UTF-8 under the Java 11+ API contract. However, other APIs such as `FileReader`, `InputStreamReader`, `FileWriter`, or `String.getBytes()` have overloads that use the **default charset** if unspecified. Since JDK 18, JEP 400 standardizes UTF-8 as the default charset in most standard configurations, yet that does not guarantee legacy data or data provided by other systems is UTF-8. For reliable integration, **pass an explicit charset according to the data contract**.

## 7. Misreading Charsets: Mojibake and Replacement Characters

Suppose a file stores the string `café` in UTF-8. The letter `é` is encoded as `C3 A9`. If a Windows-1252 decoder is applied to these bytes, users may see `cafÃ©`. This phenomenon is called **mojibake**: bytes are interpreted under rules different from the charset used to create them. The resulting Java string is still a `String` with UTF-16 API semantics; **the content was corrupted right at the decoding step**.

There are two kinds of errors:

- Byte data valid under the **wrong** charset: the decoder can produce different characters without throwing an error.
- Bytes invalid under the active charset: the decoder may replace invalid characters with `U+FFFD` (the replacement character), or throw an exception, depending on the API and configuration.

If you need to detect invalid UTF-8 bytes **instead of silently replacing them**, use `CharsetDecoder` and configure `CodingErrorAction.REPORT`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// Code snippet placed inside a Java method:
byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
try {
    String decoded = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(invalidUtf8))
            .toString();
    System.out.println(decoded);
} catch (CharacterCodingException ex) {
    System.out.println("Invalid UTF-8");
}
~~~

Stdout of the snippet when executed inside a method:

~~~text
Invalid UTF-8
~~~

Byte `C3` starts a UTF-8 sequence requiring a continuation byte, yet `28` is not a valid continuation byte. The `REPORT` configuration detects corrupted data. When using the convenience API `new String(bytes, StandardCharsets.UTF_8)`, invalid byte sequences are typically replaced with the replacement character under the constructor's contract, so not throwing an exception should not be taken as proof that the original data was valid.

### String slicing can break a surrogate pair

The following snippet proves `substring()` also uses UTF-16 indices:

~~~java
String s = "A😀B";
System.out.println(s.length()); // 4
System.out.println(s.substring(1, 3).equals("😀")); // true
System.out.println(s.substring(1, 2).length()); // 1, only takes the high surrogate
~~~

This is an **illustrative code snippet** placed inside a method. Slicing `[1, 3)` keeps both UTF-16 units of the emoji; slicing `[1, 2)` takes an unpaired surrogate, leaving no complete emoji. If the scope requires operating by code points, refer to `codePointCount()`, `offsetByCodePoints()`, and `codePoints()`. If the requirement is not to split user-perceived character clusters, you need additional segmentation by *grapheme clusters*.

## 8. Common Mistakes and How to Fix Them

| Misconception or improper operation | Consequence | Fix |
| --- | --- | --- |
| “`String` uses UTF-16 so the file must be UTF-16” | Choosing the wrong way to read/write bytes | Specify the right charset during I/O |
| Using `s.length()` as the UTF-8 byte count | Wrong size for accented letters, emojis, and many other characters | `s.getBytes(StandardCharsets.UTF_8).length` |
| Calling `substring()` arbitrarily inside a surrogate pair | Creates a string with an unpaired surrogate | Set boundaries aligned with code points or display clusters |
| Writing UTF-8 but reading as UTF-16LE | Garbled text or decoding failure | Use the charset matching the original bytes |
| Using `new String(bytes)` without knowing the default charset | Results can vary across configs/environments or data may use a different charset | `new String(bytes, expectedCharset)` |
| Thinking `javac -encoding UTF-8` determines the file charset at runtime | Output data may differ from expectations | Source code charset and data charset are two separate decisions |
| Thinking a BOM is mandatory for all UTF-8/UTF-16LE | Adding/omitting a BOM against the protocol | Follow the format specification and charset name |
| Believing the `.txt` extension determines the charset | Misdecoding files lacking metadata | Obtain the charset from agreement or format |
| Believing `char` is always a complete character | Splits non-BMP code points | Use code point APIs when appropriate |
| Treating the JVM's internal bytes as file data | Depends on implementation details | Rely solely on encode/decode APIs |

## 9. Troubleshooting Checklist for Garbled Vietnamese or Emojis in Files

1. **Clarify the byte source:** which program created the file, what charset does it use, and is there a BOM or metadata?
2. **Check the reading step:** does `Files.readString(path, charset)` or `InputStreamReader(input, charset)` use the exact source charset?
3. **Inspect the `String` after decoding:** compare code points, `equals()`, and expected values; do not use `length()` as byte size.
4. **Check the writing step:** does `Files.writeString(path, content, charset)` or `getBytes(charset)` use the charset required by the receiving system?
5. **Inspect the actual bytes:** print hex or read bytes via `Files.readAllBytes()`, observing the BOM and UTF-8/UTF-16 byte sequences.
6. **Round-trip:** with samples containing ASCII letters, accented Vietnamese, and emojis, try encoding and then decoding with the same charset; verify `original.equals(restored)`.
7. **Define error reporting:** for critical files, decide on using a strict reporting decoder instead of silently replacing corrupted characters.

## 10. Self-Check

**Question 1.** Given `String s = "😀";`, what is `s.length()` and how many bytes are needed to save `s` as UTF-8 (without BOM)?

**Answer:** `length() == 2` because the emoji uses two UTF-16 code units; the UTF-8 encoding of the emoji uses **4 bytes**, `F0 9F 98 80`.

**Question 2.** The string `"Aé"` has two Unicode code points. Is its UTF-8 byte count equal to 2?

**Answer:** No. A takes 1 byte, é takes 2 bytes; **3 bytes** in total.

**Question 3.** After `Files.writeString(path, s, StandardCharsets.UTF_8)`, does variable `s` change type into a “UTF-8 String”?

**Answer:** No. Only the byte output is encoded as UTF-8; `String` APIs still operate on UTF-16 units.

**Question 4.** Why do the bytes `FE FF 00 41` read through charset UTF-16 produce a string containing A?

**Answer:** `FE FF` is the BOM indicating big-endian, and `00 41` is the UTF-16 code unit for A.

**Question 5.** Is reading a file saved in UTF-8 using `StandardCharsets.UTF_16LE` guaranteed to recover it properly?

**Answer:** No; encoding and decoding must use the same convention (or compatible conventions per the specification). A mismatched charset can produce wrong characters or be treated as invalid data.

## References

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 conventions in string APIs, `length`, `charAt`, `getBytes`, `codePointCount`.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charset names and properties.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `writeString`, `readString`, `readAllBytes`.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): handling malformed bytes and `CodingErrorAction`.
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254): optimizing internal `String` representation.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): changing the default charset starting in JDK 18.