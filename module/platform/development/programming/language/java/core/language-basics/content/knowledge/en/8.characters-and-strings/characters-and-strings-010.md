# Choosing Explicit Encoding When Converting Between Text and Bytes in Java

> **Java core — language-basics / Characters and Strings**  
> **Environment:** JDK 17+, standard library only.  
> **Goal:** Distinguish `String` content from bytes, choose the right `Charset` in both encoding and decoding directions, avoid Vietnamese text / emoji corruption, validate malformed data, and apply this rule to files or network communication.

## 1. Text and bytes are two different representations

A Java `String` represents text using UTF-16 code units. A `byte[]` only holds 8-bit integers; **a sequence of bytes does not carry its charset with it** for the receiver to know how to interpret it.

To convert between the two forms, both sides must agree on a **character encoding / charset**:

~~~text
String --getBytes(UTF_8)--> byte[]
String <--new String(bytes, UTF_8)-- byte[]
~~~

For example, the string `"Aé😀"` consists of **3 Unicode code points** and **4 UTF-16 code units**, yet becomes **7 UTF-8 bytes**:

| Component | Code point | UTF-8 (hex) | Byte count |
| --- | --- | --- | ---: |
| `A` | U+0041 | `41` | 1 |
| `é` | U+00E9 | `C3 A9` | 2 |
| `😀` | U+1F600 | `F0 9F 98 80` | 4 |
| **Whole string** | 3 code points | `41 C3 A9 F0 9F 98 80` | **7** |

Therefore `String.length()` does **not** tell you how many bytes need to be transmitted or stored. `length()` counts UTF-16 units; byte count must be determined using the **chosen charset**.

## 2. Always pass an explicit `Charset`

Java provides charset constants in `java.nio.charset.StandardCharsets`; **UTF-8** is a sensible default for most modern text formats when no other convention applies.

~~~java
import java.nio.charset.StandardCharsets;

String text = "Tiếng Việt";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(payload, StandardCharsets.UTF_8);
~~~

**Rule:** Whichever charset is used to encode, decoding must use the charset matching that data. Both sender and receiver need to agree on the charset in the data contract or protocol metadata.

Comparing key APIs:

| Task | Should write | Avoid environment dependency |
| --- | --- | --- |
| `String` → `byte[]` | `s.getBytes(StandardCharsets.UTF_8)` | `s.getBytes()` |
| `byte[]` → `String` | `new String(bytes, StandardCharsets.UTF_8)` | `new String(bytes)` |
| Write text to file | `Files.writeString(path, s, StandardCharsets.UTF_8)` | Relying on another API's default charset |
| Read text from file | `Files.readString(path, StandardCharsets.UTF_8)` | Guessing encoding based on the OS |

In Java 17, `Files.writeString`/`Files.readString` **without** a charset parameter already default to UTF-8; passing it explicitly still makes the data contract easier to verify. Not all older I/O APIs share that default.

`StandardCharsets.UTF_16LE` or `ISO_8859_1` is also useful **if the format genuinely requires it**. Do not blindly choose UTF-8 to read data specified as UTF-16LE.

## 3. Runnable Java 17+ program

Create the file **EncodingDemo.java** containing the following code:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class EncodingDemo {
    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase()
                .formatHex(bytes);
    }

    public static void main(String[] args) {
        String original = "Aé😀";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        byte[] utf16le = original.getBytes(StandardCharsets.UTF_16LE);
        String decoded16 = new String(
                utf16le, StandardCharsets.UTF_16LE);

        System.out.println("utf16Units=" + original.length());
        System.out.println("codePoints="
                + original.codePointCount(0, original.length()));
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf8Hex=" + hex(utf8));
        System.out.println("utf8RoundTrip=" + original.equals(decoded));

        System.out.println("utf16leBytes=" + utf16le.length);
        System.out.println("utf16leHex=" + hex(utf16le));
        System.out.println("utf16leRoundTrip="
                + original.equals(decoded16));

        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);
        System.out.println("wrongCharsetEqual="
                + original.equals(wrong));

        byte[] malformed = {(byte) 0xC3};
        String replaced = new String(
                malformed, StandardCharsets.UTF_8);
        System.out.printf("replacement=U+%04X%n",
                (int) replaced.charAt(0));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("strictUtf8=accepted");
        } catch (CharacterCodingException ex) {
            System.out.println("strictUtf8=rejected");
        }
    }
}
~~~

In the directory containing `EncodingDemo.java`, use Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 EncodingDemo.java
java EncodingDemo
~~~

**Exact expected output:**

~~~text
utf16Units=4
codePoints=3
utf8Bytes=7
utf8Hex=41 C3 A9 F0 9F 98 80
utf8RoundTrip=true
utf16leBytes=8
utf16leHex=41 00 E9 00 3D D8 00 DE
utf16leRoundTrip=true
wrongCharsetEqual=false
replacement=U+FFFD
strictUtf8=rejected
~~~

**Reading the output:**

1. `"Aé😀"` has 3 code points and 4 UTF-16 code units; UTF-8 uses 7 bytes, while UTF-16LE uses 8 bytes.
2. `UTF_16LE` writes two bytes in little-endian order for each code unit, **without adding a BOM**; the emoji is split into surrogates `D83D DE00` and then into bytes `3D D8 00 DE`.
3. Round-tripping with the same charset yields `true`. Decoding UTF-8 bytes as ISO-8859-1 produces a string with different content, because each byte is interpreted as a Latin-1 code point.
4. A standalone byte `C3` is **incomplete** UTF-8. The `new String(bytes, UTF_8)` constructor replaces the malformed sequence with the replacement character **U+FFFD**. A decoder with `CodingErrorAction.REPORT` rejects that data so the program can handle the error.

Use `HexFormat` (available since Java 17) to inspect the **actual bytes**, instead of only looking at characters that terminals sometimes render improperly.

## 4. Wrong decoding produces garbled text, not “self-corrupting strings”

Suppose the sender uses UTF-8 to encode `é` into two bytes `C3 A9`, while the receiver uses ISO-8859-1. The data may then display as a sequence of wrong characters (commonly called **mojibake**).

Key points to remember:

- Bytes **remain** bytes; changing how they are interpreted is what changes the resulting string.
- `new String(bytes, charset)` does not magically “auto-detect the original charset”.
- Do not blindly convert back and forth across charsets by guessing; first determine the **charset in the data contract**.
- If decoding has already replaced invalid bytes with `U+FFFD`, inspecting only the decoded string may not recover the original data.

Some formats carry encoding metadata or a BOM. A BOM can appear in UTF-8/UTF-16 data, yet **not every file has one**; do not treat a BOM as a mandatory part of UTF-8. If a protocol specifies presence or absence of a BOM, follow that format specification.

## 5. Malformed data: replace or reject?

If input data has the wrong encoding or a truncated byte sequence, two policies are common:

| Policy | When to use? | Result |
| --- | --- | --- |
| **Replace** invalid sequences with `U+FFFD` | “Best effort” text viewing, accepting partial data loss | `new String(bytes, UTF_8)` typically replaces malformed input |
| **Report an error** if bytes are invalid | Data must be exact, strict input validation, protocol checking | `CharsetDecoder` with `CodingErrorAction.REPORT` throws `CharacterCodingException` |

Strict mode example (as in the main program):

~~~java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

This snippet requires `bytes` as `byte[]` and the `ByteBuffer` and `CodingErrorAction` imports as in the main example; place it inside a method declaring `throws CharacterCodingException` or handle the exception.

**Two-way note:** an **encoder** (`String` → bytes) can also lose data if the charset cannot represent a character (for example, an emoji with ISO-8859-1). If character loss is unacceptable, use a `CharsetEncoder` configured with `REPORT` or choose UTF-8 when the format supports it.

## 6. Applying to files, APIs, and runtime environments

When data must be written to / read from a file, configure the charset in **both directions**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");
Files.writeString(path, "Tiếng Việt 😀", StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is a **file-operation illustration**, not part of the `EncodingDemo` program; if you run this snippet, it will create/write `message.txt`. No file I/O is needed to run the main demo.

With HTTP, JSON, CSV, or databases, know clearly which charset the protocol, API documentation, or driver uses. Avoid trying to build a `String` from bytes that are actually **binary data** such as images, archives, or hashes: to represent binary data as text, use an appropriate encoding such as Base64 or hex.

**Three distinct encoding layers to separate:**

1. **Source file encoding:** the command `javac -encoding UTF-8 EncodingDemo.java` instructs the compiler to read `.java` using UTF-8.
2. **Text ↔ byte encoding inside the program:** `StandardCharsets.UTF_8` or the charset specified by the format.
3. **Encoding when the terminal displays/prints text:** determined by the environment and console configuration. Garbled screen output **does not prove** the underlying bytes are wrong.

Because `EncodingDemo`'s output contains only ASCII characters and hex, you can verify it accurately even if the console's Unicode configuration is imperfect.

## 7. Common mistakes and exercises

| Mistake | How to avoid |
| --- | --- |
| `text.getBytes()` / `new String(bytes)` at data exchange boundaries | Pass an explicit `Charset` instead of relying on environment defaults |
| Encoding as UTF-8 then decoding as Latin-1 | Both sides must agree on the encoding |
| Using `String.length()` as the number of bytes to send | Use `text.getBytes(charset).length` or measure the actual `byte[]` |
| Decoding “succeeds” and assuming the text must be right | A wrong charset can produce no error yet wrong content |
| Assuming UTF-16 files always have a BOM | Distinguish UTF-16 with BOM from UTF-16LE/BE per file contract |
| Using ISO-8859-1 to store any Unicode character | That charset cannot represent all code points; data loss can occur |
| Changing console charset to “fix” original bytes | Inspect source file, byte payload, decoding charset, and terminal separately |

**Exercise 1:** Count the UTF-8 bytes of `"ABC"`, `"é"`, and `"😀"` using `getBytes(StandardCharsets.UTF_8).length`. Why do the three cases not have the same byte count per code point?

**Exercise 2:** Try encoding `"Việt"` with `UTF_8`, decoding with the same charset, and comparing with `equals`. Then try decoding with `ISO_8859_1` and observe the difference.

**Exercise 3:** Given `byte[] invalid = {(byte) 0xC3};`, predict the result of the `new String(invalid, UTF_8)` constructor versus a `REPORT` decoder.

**Exercise 4:** If an API specifies UTF-16LE, update the program to use `StandardCharsets.UTF_16LE` in both directions; measure the byte length and print hex.

**Exercise 5:** When receiving bytes from the network without charset information, can you prove the original text was definitely UTF-8 from the appearance of the string alone? How would you clarify the protocol requirement?

### Key takeaway

**Encoding is the convention for converting between text and bytes.** Always choose and pass an **explicit `Charset` in both encoding and decoding directions**; for modern text, UTF-8 is usually appropriate unless the format specifies otherwise. Use hex bytes and round-trip checks to verify data; use a `REPORT` decoder when invalid bytes must be rejected, without depending on the default charset or terminal rendering.
