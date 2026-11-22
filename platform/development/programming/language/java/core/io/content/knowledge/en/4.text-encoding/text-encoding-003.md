# Charset, StandardCharsets, and Charset Names in Java I/O

## 1. What Is a Charset and What Problem Does It Solve?

Files and I/O streams store and transmit **bytes**, whereas `String` in Java represents Unicode text. To convert between the two forms, there must be a character encoding rule, called a **character encoding** or **charset**.

- **Encode:** Unicode characters → byte sequence according to the selected charset.
- **Decode:** byte sequence → Unicode characters using the exact corresponding rule.

For example, the character `é` (U+00E9) is represented as:

| Charset | Hex bytes of `é` |
| --- | --- |
| UTF-8 | `C3 A9` |
| ISO-8859-1 | `E9` |
| UTF-16BE | `00 E9` |
| UTF-16LE | `E9 00` |

The same character has different bytes across charsets. Conversely, the same byte sequence can be interpreted as different characters, or become invalid data, when the wrong charset is chosen.

For example, the sequence `41 C3 A9` is the string `Aé` when decoded with UTF-8, yet becomes `AÃ©` under ISO-8859-1. That is garbled-character corruption (*mojibake*), commonly encountered when an application sends UTF-8 while the receiver decodes with a different charset.

**A charset is not** a compression algorithm, security encryption, or file format. It only defines how text and bytes map to each other. It is also important to distinguish charsets from Vietnamese diacritics/Unicode normalization: two visually identical strings can use different code point sequences; encoding does not normalize them automatically.

## 2. `java.nio.charset.Charset`: An Object Describing an Encoding

`Charset` is a class in the `java.nio.charset` package representing a conversion between character sequences and bytes. In Java, a `Charset` object is usually passed directly to I/O APIs instead of a string name.

Useful methods:

| API | Purpose |
| --- | --- |
| `Charset.forName("UTF-8")` | Looks up a charset by canonical name or another name recognized by the runtime; throws an exception if the name is invalid/unsupported |
| `Charset.isSupported("UTF-8")` | Checks whether a valid name is supported |
| `charset.name()` | Gets the **canonical name** of the charset |
| `charset.aliases()` | Gets other names (*aliases*) published by the provider |
| `Charset.availableCharsets()` | Gets the available charsets on the runtime as a map of canonical name → object |
| `Charset.defaultCharset()` | Inspects the runtime's default charset |
| `charset.newEncoder()` and `charset.newDecoder()` | Creates converters to control how erroneous characters/bytes are handled |

There is no need to call `new Charset(...)`; this is an abstract class, and concrete instances are provided by the Java library and providers.

### Canonical names, aliases, and comparison

Charset names are strings, such as `UTF-8`, `US-ASCII`, and `ISO-8859-1`. The canonical name is the name returned by `charset.name()`. Other names (*aliases*) can be used to look up the same charset; for example, many JDKs accept `UTF8` for `UTF-8`, but **the set of aliases outside the canonical name can depend on the provider/runtime**.

Charset name lookup is **case-insensitive**, so `Charset.forName("uTf-8")` and `Charset.forName("UTF-8")` refer to the same charset semantically. Use `charset.equals(other)` to compare charset objects, or normalize via `charset.name()` when storing names; do not rely on `==` or arbitrary alias string comparisons.

Input names must conform to the syntax allowed by `Charset`; invalid characters can cause `isSupported` to throw `IllegalCharsetNameException` instead of returning `false`.

## 3. `StandardCharsets`: Using Constants Instead of String Names

`java.nio.charset.StandardCharsets` provides pre-defined `Charset` objects for the six charsets **guaranteed to be supported by every Java SE implementation**:

| Constant | Canonical Name | Key Notes |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | `UTF-8` | Unicode, variable-length encoding 1–4 bytes/code point; default choice for new communication/text files unless specified otherwise |
| `StandardCharsets.US_ASCII` | `US-ASCII` | 7-bit; directly represents only U+0000 through U+007F |
| `StandardCharsets.ISO_8859_1` | `ISO-8859-1` | One byte per character U+0000 through U+00FF; does not contain most Vietnamese characters |
| `StandardCharsets.UTF_16` | `UTF-16` | Unicode UTF-16; when encoding, typically writes a BOM to indicate byte order; decoder can recognize BOM |
| `StandardCharsets.UTF_16BE` | `UTF-16BE` | Big-endian UTF-16; does not automatically add a BOM |
| `StandardCharsets.UTF_16LE` | `UTF-16LE` | Little-endian UTF-16; does not automatically add a BOM |

**Java constant names** like `UTF_8` use underscores due to identifier rules; **canonical charset names** like `UTF-8` use hyphens. Do not pass the string `"UTF_8"` assuming it is synonymous with `"UTF-8"`; use the constant or exact canonical name.

Prefer:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Rather than looking it up by string every time:

```java
Charset charset = Charset.forName("UTF-8");
```

The two snippets above **are illustrative snippets**: `text` and `bytes` must be declared in an appropriate context. When the charset is fixed at compile time, `StandardCharsets` constants prevent typos, avoid handling unsupported-name exceptions, and state intent clearly right in the source code.

If the charset name comes from external configuration, an HTTP header string, or a metadata file, `Charset.forName(name)` remains useful; just validate the name and handle errors. `StandardCharsets` does not include all charsets a JDK may support.

## 4. Java 17+ Example: Name Lookup, Encoding, and Decoding

Create file **`CharsetNamesDemo.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetNamesDemo {
    public static void main(String[] args) {
        Charset utf8 = StandardCharsets.UTF_8;
        Charset fromName = Charset.forName("uTf-8");

        String original = "Aé";
        byte[] bytes = original.getBytes(utf8);

        System.out.println("Tên chuẩn: " + utf8.name());
        System.out.println("Cùng charset: " + utf8.equals(fromName));
        System.out.println("UTF-8 hex: " + HexFormat.of().formatHex(bytes));
        System.out.println("Giải mã UTF-8: " + new String(bytes, utf8));
        System.out.println("Giải mã Latin-1: "
                + new String(bytes, StandardCharsets.ISO_8859_1));
        System.out.println("Hỗ trợ UTF-8: " + Charset.isSupported("UTF-8"));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 CharsetNamesDemo.java
java CharsetNamesDemo
```

Logical/Unicode output of the program:

```text
Tên chuẩn: UTF-8
Cùng charset: true
UTF-8 hex: 41c3a9
Giải mã UTF-8: Aé
Giải mã Latin-1: AÃ©
Hỗ trợ UTF-8: true
```

Explanation:

1. `Charset.forName("uTf-8")` looks up UTF-8 case-insensitively, so `equals` returns `true`.
2. The letter `A` encodes to `41`; `é` encodes to `C3 A9`. `HexFormat` is included in Java 17 and prints lowercase hex by default.
3. Decoding properly with the same UTF-8 restores `Aé`. Mis-decoding with Latin-1 yields `AÃ©` because the two bytes `C3`, `A9` are interpreted as two separate Latin-1 characters.
4. `UTF-8` belongs to the mandatory Java SE charsets, so `isSupported("UTF-8")` returns `true`.

Save source files as UTF-8 so accented characters compile accurately. `javac -encoding UTF-8` specifies the charset of the **source file**; it does not automatically choose the charset for `getBytes` or `new String`. Displaying Vietnamese/`é` in the terminal also requires a terminal/font with Unicode support.

## 5. Dynamic Charset Names, Support, and Exceptions

For charsets coming from configuration, it is important to understand the difference between a “syntactically invalid name” and a “valid name not supported by the runtime”.

```java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;
import java.nio.charset.UnsupportedCharsetException;

public class ResolveCharsetDemo {
    public static void main(String[] args) {
        for (String name : new String[]{"UTF-8", "x-demo-unknown-charset", "bad name!"}) {
            try {
                Charset charset = Charset.forName(name);
                System.out.println(name + " => " + charset.name());
            } catch (IllegalCharsetNameException e) {
                System.out.println(name + " => tên không hợp lệ");
            } catch (UnsupportedCharsetException e) {
                System.out.println(name + " => không được hỗ trợ");
            }
        }
    }
}
```

This is a standalone program, though `"x-demo-unknown-charset"` is only an illustrative name: software with custom charset providers could support that name, so do not treat the output for the placeholder name as invariant across every runtime.

- `IllegalCharsetNameException`: the name string violates valid syntax (for example, containing spaces or exclamation marks disallowed in that position).
- `UnsupportedCharsetException`: the name has valid syntax, but no supporting provider is found.
- `Charset.isSupported(name)`: can check beforehand for **syntactically valid names**, yet syntax errors must still be handled and you must not assume every name exists in every environment.
- `NullPointerException`: can occur when passing `null` to name lookup APIs.

If a program only supports UTF-8 per protocol, it can **validate against an allowlist of names** and then use `StandardCharsets.UTF_8`; it does not have to accept every charset the host happens to have. When storing configuration, prefer `charset.name()` as the canonical representation and document the charset explicitly in metadata/protocols.

## 6. Converting Properly at I/O Boundaries

### Strings, byte arrays, and files

The following APIs accept a `Charset` directly:

| Purpose | Example |
| --- | --- |
| String → byte[] | `text.getBytes(StandardCharsets.UTF_8)` |
| byte[] → String | `new String(bytes, StandardCharsets.UTF_8)` |
| Read file into String | `Files.readString(path, StandardCharsets.UTF_8)` |
| Write String to file | `Files.writeString(path, text, StandardCharsets.UTF_8)` |
| Byte stream → reader | `new InputStreamReader(input, StandardCharsets.UTF_8)` |
| Writer → byte stream | `new OutputStreamWriter(output, StandardCharsets.UTF_8)` |

Example using `Files`, where `path` is a valid `Path` and `text` is a `String`:

```java
Files.writeString(path, text, StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
```

This is an **illustrative snippet**, not a standalone program; you must import `java.nio.file.Files`, `java.nio.file.Path` and handle `IOException`. For the written file, the default write operation can create or truncate the target file; avoid running on critical data without verifying the path.

With byte streams, specify the charset at the **bytes ↔ characters conversion step**. For example, when receiving an HTTP response or reading from a socket, reading the `InputStream` only yields bytes; only when creating an `InputStreamReader` or decoding data should you apply the charset matching the protocol. `BufferedReader` and `BufferedWriter` only add buffering/line-handling utilities and cannot fix errors caused by using the wrong charset.

### Do not depend on the default charset

APIs without a charset argument may use the **environment's default charset or the API's own contract**. On Java 17, the default charset usually depends on OS and JVM configuration; starting in Java 18, JEP 400 establishes UTF-8 as the default in most cases, with certain exceptions/compatibility modes. Therefore, working correctly on a personal machine is no guarantee when moving to another machine.

`Charset.defaultCharset()` is for **observing** the default choice; do not use it in place of a charset specified by a protocol/file. For new content controlled by the application, agree explicitly on UTF-8 on both the writing and reading sides.

Some formats/protocols mandate their own charset, or provide BOM/metadata. When reading existing content, follow the format's specific standard rather than forcing UTF-8 just because it is a good choice for new files.

## 7. Encoding Unmappable Characters and Malformed Byte Data

The difference between the two situations:

- **Unmappable character:** a Unicode string contains a character that cannot be represented in the target charset. For example, `é` cannot be encoded in US-ASCII.
- **Malformed input:** a byte sequence does not conform to the encoding rules during decoding. For example, `C3 28` is not a valid UTF-8 byte sequence because `C3` requires a continuation byte `80..BF`, whereas `28` is not a continuation byte.

Convenience APIs like `String.getBytes(Charset)` and `new String(bytes, Charset)` typically **replace invalid data with a replacement character/byte**. This simplifies handling yet can silently lose or alter data. When errors must be detected instead of replaced, use `CharsetEncoder`/`CharsetDecoder` with `CodingErrorAction.REPORT`.

Standalone example **`StrictCharsetDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictCharsetDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {(byte) 0xC3, 0x28};
        String replaced = new String(invalidUtf8, StandardCharsets.UTF_8);
        System.out.println("Có ký tự thay thế: "
                + (replaced.codePointAt(0) == 0xFFFD));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));
            System.out.println("Decode thành công");
        } catch (CharacterCodingException e) {
            System.out.println("UTF-8 không hợp lệ");
        }

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("é"));
            System.out.println("Encode thành công");
        } catch (CharacterCodingException e) {
            System.out.println("ASCII không mã hóa được é");
        }
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 StrictCharsetDemo.java
java StrictCharsetDemo
```

Output:

```text
Có ký tự thay thế: true
UTF-8 không hợp lệ
ASCII không mã hóa được é
```

The Unicode replacement character **U+FFFD** appears when decoding an invalid UTF-8 byte sequence with `new String(bytes, UTF_8)`. When `REPORT` is enabled, `decode` throws `CharacterCodingException` (or a subclass) so the program can decide how to handle it. With the ASCII encoder, `é` cannot be represented, so it reports an error instead of silently replacing it with `?`.

Do not use `CodingErrorAction.REPLACE` if the task requires preserving exact data; conversely, if business logic permits replacement, document clearly how erroneous data is handled.

## 8. UTF-8, UTF-16, BOM, and the Limits of `String.length()`

UTF-8 stores each Unicode code point in 1–4 bytes. UTF-16 stores a code point in one or two **16-bit code units**. One Java `char` is one **UTF-16 code unit**, not always a complete Unicode character.

For example, an emoji outside the Basic Multilingual Plane can have `String.length() == 2` (surrogate pair) while its UTF-8 encoding is 4 bytes. Do not use `String.length()` as the encoded byte count; to know the actual size, encode and check `byte[].length`.

A **BOM (Byte Order Mark)** can mark byte order in certain Unicode forms. `StandardCharsets.UTF_16` handles the BOM according to UTF-16 rules, while `UTF_16BE`/`UTF_16LE` specify byte order explicitly. UTF-8 **does not require a BOM**; a UTF-8 file with a BOM may start with the three bytes `EF BB BF`. Depending on the reader, a UTF-8 BOM may appear as the `U+FEFF` character in the resulting string instead of being automatically stripped. If a format allows or requires a BOM, handle it according to that format's specific contract.

Do not rely on “seeing Vietnamese text correctly” to prove both sides use the same charset: pure ASCII text often produces identical output under many charsets. Test with non-ASCII characters and compare bytes when diagnosing bugs.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Write UTF-8, read ISO-8859-1 | Corrupted accents, e.g. `é` becomes `Ã©` | Align the charset on both write and read |
| Convert String to bytes without passing a charset | Depends on API contract/runtime configuration | Pass `StandardCharsets.UTF_8` if the format allows |
| Use `StandardCharsets.UTF_8.toString()` to infer any syntax | Confuses charset name with constant name or alias | Use `name()` and canonical name `UTF-8` |
| Treat `String.length()` as byte count | Wrong for non-ASCII characters/emojis | Use `text.getBytes(charset).length` |
| Use ASCII/Latin-1 for arbitrary Unicode text | Characters outside the charset are replaced or throw errors | Use UTF-8 or choose the charset matching requirements |
| Decode invalid bytes with a replacing API without checking | Input information is silently lost | Use `CharsetDecoder` with `REPORT` when strictness is needed |
| Assume every alias is supported | Works on one machine yet fails on another | Use the six mandatory `StandardCharsets` and canonical names |
| Confuse UTF-8 BOM with content characters | String starts with an extra `U+FEFF` | Read and handle BOM according to the file specification |

**Practice exercise:** Encode `"Aé"` using `UTF_8` and `ISO_8859_1`. Compare the bytes: UTF-8 is `41 C3 A9`, ISO-8859-1 is `41 E9`. Then decode each array with its matching charset to recover `"Aé"`; try decoding with the wrong charset to observe the output. Change `é` to a Vietnamese character or emoji and see which charset cannot represent that character.

**Remember:** `Charset` is the object describing an encoding; `StandardCharsets` provides six guaranteed-available charsets; charset names have a **canonical name** and may have **aliases**. To preserve text during I/O, specify and align the charset on both the **encode** and **decode** sides; when data must be exact, handle malformed/unmappable cases explicitly.