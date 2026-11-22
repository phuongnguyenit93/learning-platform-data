# BOM and Differences Between UTF-16, UTF-16BE, and UTF-16LE in Java

## Lesson Objectives

When reading or writing text using **byte streams**, the charset name does not only determine how Unicode characters map to bytes: for UTF-16, it also determines the **byte order** and how a **BOM (Byte Order Mark)** is handled. After this lesson, you will:

- Be able to explain why the same text produces different byte sequences when using UTF-16BE vs. UTF-16LE.
- Recognize the `FE FF` and `FF FE` BOMs and distinguish a BOM from ordinary character data.
- Understand accurately how Java's `StandardCharsets.UTF_16`, `UTF_16BE`, and `UTF_16LE` encode/decode data.
- Write Java 17+ programs capable of inspecting actual bytes, handling files with or without a BOM, and avoiding misreading content.

## 1. Background: UTF-16 Encodes *Code Units* into Bytes

Unicode defines **code points**, such as `U+0041` for the letter `A` and `U+1F600` for the emoji 😀. UTF-16 represents a code point as one or two **16-bit code units**:

- For characters in the Basic Multilingual Plane (BMP), excluding the surrogate range, UTF-16 normally uses a single 16-bit code unit. For example, `A` is `0x0041`.
- For code points outside the BMP, UTF-16 uses a **surrogate pair** consisting of two code units. For example, `U+1F600` is represented as `D83D DE00`.
- **16 bits = 2 bytes**, yet the order of the two bytes within each code unit can differ. Therefore, UTF-16 does not mean “every character always occupies two bytes.”

When converting code unit `0x0041` into bytes:

| Storage Order | Byte Order | Hex Sequence |
| --- | --- | --- |
| Big-endian (BE) | High byte first | `00 41` |
| Little-endian (LE) | Low byte first | `41 00` |

For the string `A😀`, the code units are `0041 D83D DE00`:

- **UTF-16BE:** `00 41 D8 3D DE 00`.
- **UTF-16LE:** `41 00 3D D8 00 DE`.

The two sequences differ in byte order within **each code unit**, yet both can represent the exact same string when the decoder knows the byte order.

## 2. What Is a BOM and Where Does It Live?

A **BOM (Byte Order Mark)** is a marker at the **beginning of byte data** that helps a reader detect the byte order of UTF-16 when the format does not fix BE or LE beforehand. The BOM corresponds to code point `U+FEFF`, encoded differently depending on byte order:

| First two bytes | Meaning in UTF-16 |
| --- | --- |
| `FE FF` | BOM for UTF-16 big-endian |
| `FF FE` | BOM for UTF-16 little-endian |

Thus, a file containing the letter `A` might look like:

```text
UTF-16 BE with BOM:    FE FF | 00 41
UTF-16 LE with BOM:    FF FE | 41 00
UTF-16 BE without BOM: 00 41
UTF-16 LE without BOM: 41 00
```

The `|` symbol only separates the **BOM** from the **payload**; it is not a byte in the file.

Several very important points:

1. **Not all UTF-16 data is required to have a BOM.** A protocol or format may explicitly declare UTF-16BE/UTF-16LE, in which case the byte order is already known and no BOM is needed.
2. **A BOM does not carry data length.** It only assists in identifying how to decode at the start of the byte stream.
3. **A BOM is not an ordinary visible character.** When a UTF-16 decoder recognizes the BOM as a byte-order signature, that signature typically does not become a character in the decoded result.
4. **A BOM may be interpreted as the character `U+FEFF` if a fixed-byte-order decoder is used.** That is why a string can start with an invisible character after being read in the wrong mode.
5. **Do not confuse it with the UTF-8 BOM `EF BB BF`.** UTF-8 does not have two byte orders; a UTF-8 BOM is a separate issue, not a BE/LE choice.

## 3. How Do the Three UTF-16 Charsets in Java Differ?

Java provides three constants in `java.nio.charset.StandardCharsets`:

| Java Charset | When **encoding** (`String → byte[]`) | When **decoding** (`byte[] → String`) |
| --- | --- | --- |
| `StandardCharsets.UTF_16` | Emits BOM `FE FF` and encodes content in **big-endian**. | If BOM `FE FF` / `FF FE` is present at the start, detects BE/LE accordingly and consumes the BOM; if **no BOM is present**, defaults to decoding as **big-endian**. |
| `StandardCharsets.UTF_16BE` | Encodes big-endian; **does not automatically add a BOM**. | Decodes strictly as big-endian; **does not automatically strip a BOM** as a byte-order signature. |
| `StandardCharsets.UTF_16LE` | Encodes little-endian; **does not automatically add a BOM**. | Decodes strictly as little-endian; **does not automatically strip a BOM** as a byte-order signature. |

This is the **behavior of these Java charsets**, not a guarantee that every text reader in every language chooses BE when no BOM is present. When exchanging data between systems, follow the format or protocol specification.

### Intuitive example

If you receive `41 00` **without a BOM**:

- Decoding with `UTF_16LE`: yields `A` (`U+0041`).
- Decoding with `UTF_16`: Java defaults to BE, so the two bytes become code unit `0x4100` (`U+4100`), **not** `A`.

There is no general way to guess the meaning with certainty from the two bytes `41 00` alone; the encoding decision must come from a valid BOM, reliable metadata, or a protocol specification.

## 4. Java 17+ — Observing Encoded Bytes

Create file **`Utf16BytesDemo.java`** (standalone source):

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf16BytesDemo {
    private static void show(String name, Charset charset, String text) {
        byte[] bytes = text.getBytes(charset);
        System.out.println(name + " = " + HexFormat.of().formatHex(bytes));
    }

    public static void main(String[] args) {
        String text = "A" + new String(Character.toChars(0x1F600));

        show("UTF-16", StandardCharsets.UTF_16, text);
        show("UTF-16BE", StandardCharsets.UTF_16BE, text);
        show("UTF-16LE", StandardCharsets.UTF_16LE, text);

        System.out.println("UTF-16 code units = " + text.length());
        System.out.println("Unicode code points = "
                + text.codePointCount(0, text.length()));
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 Utf16BytesDemo.java
java Utf16BytesDemo
```

Exact output:

```text
UTF-16 = feff0041d83dde00
UTF-16BE = 0041d83dde00
UTF-16LE = 41003dd800de
UTF-16 code units = 3
Unicode code points = 2
```

Explaining the numbers:

- `feff` at the beginning of the UTF-16 line is the big-endian BOM, generated automatically by the `UTF_16` encoder.
- The big-endian content portion `0041d83dde00` matches the UTF-16BE line. The UTF-16LE line reverses the byte order of each code unit to `41003dd800de`.
- The string `A😀` has **two Unicode code points** yet **three UTF-16 code units**: `A` uses one code unit, and 😀 uses two code units (a surrogate pair).
- Because of the BOM, the UTF-16 line contains **8 bytes**; both BOM-less BE/LE lines contain **6 bytes**. You should not compute byte length simply as `String.length() * 2`.

`HexFormat` has existed since Java 17; the example uses it so hex output can be compared accurately across machines.

## 5. Java 17+ — How Does Java Read a BOM?

Create file **`Utf16DecodeDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf16DecodeDemo {
    public static void main(String[] args) {
        HexFormat hex = HexFormat.of();
        byte[] beWithBom = hex.parseHex("feff0041");
        byte[] leWithBom = hex.parseHex("fffe4100");
        byte[] leWithoutBom = hex.parseHex("4100");

        System.out.println("BE BOM with UTF-16 = "
                + new String(beWithBom, StandardCharsets.UTF_16));
        System.out.println("LE BOM with UTF-16 = "
                + new String(leWithBom, StandardCharsets.UTF_16));

        String wrong = new String(leWithoutBom, StandardCharsets.UTF_16);
        System.out.println("LE without BOM using UTF-16 = U+"
                + String.format("%04X", wrong.codePointAt(0)));

        System.out.println("LE without BOM using UTF-16LE = "
                + new String(leWithoutBom, StandardCharsets.UTF_16LE));
    }
}
```

Run:

```bash
javac -encoding UTF-8 Utf16DecodeDemo.java
java Utf16DecodeDemo
```

Exact output:

```text
BE BOM with UTF-16 = A
LE BOM with UTF-16 = A
LE without BOM using UTF-16 = U+4100
LE without BOM using UTF-16LE = A
```

Both cases with a BOM produce `A` because `UTF_16` **reads the leading signature** and picks the right BE or LE order. Without a BOM, Java's `UTF_16` cannot know that `4100` was written in LE, so it applies BE by default. Switching to `UTF_16LE` decodes it properly.

**Be careful with fixed-byte-order decoders:** using `UTF_16LE` to read `FF FE 41 00` can place `U+FEFF` at the beginning of the string because this charset does not automatically strip the BOM like `UTF_16`. Do not blindly remove the first character of every file; only handle a BOM at the start when the protocol/charset expects it.

## 6. Writing and Reading a UTF-16LE File With a BOM Per Format Requirements

Suppose an external non-Java system requires a file encoded in **UTF-16LE with an `FF FE` BOM**. If you only write:

```java
Files.writeString(path, text, StandardCharsets.UTF_16LE);
```

Java writes the content in LE but **does not add a BOM automatically**. Conversely, `StandardCharsets.UTF_16` emits an `FE FF` BOM and uses BE, which **cannot satisfy** the specific requirement of “UTF-16LE with BOM.”

You can prepend the two leading bytes yourself according to the format contract. The following program creates the file, reads back its bytes, and decodes it:

Create file **`Utf16LeFileDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class Utf16LeFileDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample-utf16le.txt");
        String text = "A";

        byte[] payload = text.getBytes(StandardCharsets.UTF_16LE);
        byte[] bytes = new byte[payload.length + 2];
        bytes[0] = (byte) 0xFF;
        bytes[1] = (byte) 0xFE;
        System.arraycopy(payload, 0, bytes, 2, payload.length);

        Files.write(path, bytes);

        byte[] saved = Files.readAllBytes(path);
        System.out.println("file bytes = " + HexFormat.of().formatHex(saved));
        System.out.println("decoded = " + Files.readString(path, StandardCharsets.UTF_16));

        String explicitLe = Files.readString(path, StandardCharsets.UTF_16LE);
        System.out.println("fixed LE sees U+FEFF = "
                + (explicitLe.codePointAt(0) == 0xFEFF));
    }
}
```

Run in a directory where the application has permission to create/write files:

```bash
javac -encoding UTF-8 Utf16LeFileDemo.java
java Utf16LeFileDemo
```

Exact output:

```text
file bytes = fffe4100
decoded = A
fixed LE sees U+FEFF = true
```

Because an LE BOM is present, `Files.readString(path, StandardCharsets.UTF_16)` detects the byte order accurately and returns the string `A`. With fixed `UTF_16LE`, the first two bytes are interpreted as code point `U+FEFF` in the string, so the check above returns `true`.

The example writes a physical file `sample-utf16le.txt`. If run again in the same directory, `Files.write` overwrites that file with new content by default. This is the behavior of the demo program; no file is created merely by reading this lesson.

## 7. Choosing a Charset When Using `Reader` and `Writer`

`InputStream` / `OutputStream` work with bytes; `Reader` / `Writer` work with characters. Encoding occurs at the conversion boundary:

```java
// Illustrative snippet, assuming inputStream and outputStream have already been created.
Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_16);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_16LE);
```

The two lines above are not a standalone program. In practice, select the charset based on the **actual data** and manage stream closing according to resource ownership:

- **Data has a UTF-16 BOM and needs automatic BE/LE detection:** read with `UTF_16`.
- **Data is explicitly UTF-16BE without BOM:** read/write with `UTF_16BE`.
- **Data is explicitly UTF-16LE without BOM:** read/write with `UTF_16LE`.
- **Format requires UTF-16LE with BOM:** write bytes `FF FE` followed by `UTF_16LE` payload; when reading, use `UTF_16` to detect the BOM or handle stripping the BOM before decoding with fixed LE per contract.
- **Format states only “UTF-16” and accepts BOM-indicated byte order:** Java's `UTF_16` is the appropriate choice under Java's encoding rules.

`Files.readString`, `Files.writeString`, `InputStreamReader`, and `OutputStreamWriter` all provide ways to supply a charset; **specify the charset explicitly** instead of relying on the machine's default charset when exchanging data across systems.

## 8. Common Errors and How to Diagnose Them

### Error 1: Reading BOM-less UTF-16LE with `UTF_16` and getting wrong characters

Cause: Java's `UTF_16` defaults to **BE** when no BOM is recognized. For data known to be LE, specify `StandardCharsets.UTF_16LE`.

### Error 2: Prepending a BOM manually and also encoding with `UTF_16`

`String.getBytes(StandardCharsets.UTF_16)` already prepends `FE FF`. If you also manually prepend another BOM, you can produce extra bytes or insert an additional `U+FEFF` marker in the text after the initial BOM. Use one clear strategy: **`UTF_16` automatically emits the BOM and BE**, or **fixed `UTF_16BE`/`UTF_16LE` with a manually written BOM when needed**.

### Error 3: Always deleting the first character of every string if `U+FEFF` is seen

Do not arbitrarily delete user data. `U+FEFF` can result from decoding a BOM signature with a fixed charset, yet it can also be a genuine code point in data. Treat leading bytes as a BOM only per the rules of the format being read; do not alter content merely because “this character looks invisible.”

### Error 4: Assuming UTF-16 always has two bytes per character

Emojis and many code points outside the BMP require **two code units**, meaning **four bytes** before counting any BOM. Even `String.length()` counts UTF-16 code units, not code points or bytes.

### Error 5: Decoding wrongly without noticing because of replacement characters

UTF-16 data with an odd byte count, invalid surrogates, or wrong byte order can cause decoding errors. Convenience APIs such as `new String(bytes, charset)` may replace invalid byte sequences with a replacement character. If you need to **detect corrupted data rather than silently replacing it**, use `CharsetDecoder` with `CodingErrorAction.REPORT` and handle `CharacterCodingException`. However, a wrong-endian sequence can still yield valid code points; even a strict decoder **cannot guess the right charset on its own** in that case.

### Error 6: Relying solely on a BOM when the protocol explicitly declares a charset

Not every file has a BOM. If metadata says “UTF-16LE”, follow the format specification on whether a BOM is allowed to appear. For external data, check the metadata/specification first, then use the corresponding decoder and verify with actual bytes.

## 9. Quick Decision Table

| Scenario | Appropriate Choice |
| --- | --- |
| Starts with `FE FF`, want UTF-16 decoding with auto endianness | `StandardCharsets.UTF_16` |
| Starts with `FF FE`, want UTF-16 decoding with auto endianness | `StandardCharsets.UTF_16` |
| No BOM, sender confirms big-endian | `StandardCharsets.UTF_16BE` |
| No BOM, sender confirms little-endian | `StandardCharsets.UTF_16LE` |
| Need Java to write UTF-16 with default BOM automatically | `StandardCharsets.UTF_16` (BE BOM) |
| Must write UTF-16LE with `FF FE` BOM | Manually write `FF FE` bytes + `UTF_16LE` payload |
| Need to reconcile data between systems | Record hex byte sequence, BOM, declared charset, and decoded code points |

## 10. Self-Check

**Question 1.** Are the bytes `00 41` the letter `A` in UTF-16BE or UTF-16LE?

**Answer:** UTF-16BE. The same letter `A` in LE is `41 00`.

**Question 2.** A file starts with `FF FE 41 00`; what do you get when reading it with `StandardCharsets.UTF_16`?

**Answer:** `A`. `FF FE` is the LE BOM, so the two data bytes `41 00` are interpreted as LE.

**Question 3.** Does `text.getBytes(StandardCharsets.UTF_16LE)` automatically write the `FF FE` BOM?

**Answer:** No. The `UTF_16LE` charset specifies a fixed byte order without automatically adding a BOM.

**Question 4.** Why does `new String(new byte[]{0x41, 0x00}, StandardCharsets.UTF_16)` not produce `A`?

**Answer:** Without a BOM, Java's `UTF_16` defaults to BE, so the two bytes form code unit `0x4100`.

**Question 5.** How many code points, UTF-16 code units, and bytes does the string `A😀` have when encoded with Java's `StandardCharsets.UTF_16`?

**Answer:** Two code points; three code units; six payload bytes + two BE BOM bytes = **eight bytes**.

## Key Takeaways

- **`UTF_16`:** Java automatically writes the `FE FF` BOM when encoding; when decoding, it uses the BOM to choose BE/LE, and **without a BOM it defaults to BE**.
- **`UTF_16BE` and `UTF_16LE`:** fixed byte order, **do not automatically write/consume a BOM via auto-detection**.
- **A BOM only has meaning when decoded according to the data source's contract.** Inspect raw bytes, know where the charset/format comes from, and test with strings containing both BMP and supplementary characters to prevent hidden bugs.