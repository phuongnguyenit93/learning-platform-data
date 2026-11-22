# Malformed Data, Replacement Characters, and Data Loss in Java

## Lesson Objectives

After this lesson, you will be able to distinguish invalid byte sequences, data decoded with the wrong encoding, and data that lost characters during conversion; identify when Java inserts replacement characters; detect errors using `CharsetDecoder`/`CharsetEncoder`; and choose handling strategies that avoid silently corrupting data.

## 1. From Bytes to Strings: Where Do Errors Occur?

`byte[]` holds raw bytes. `String` in Java represents Unicode text using UTF-16 code units; it does not store metadata indicating whether the original data came from UTF-8, UTF-16, ISO-8859-1, or another encoding. When exchanging data with files, networks, databases, or APIs, a program must **decode** bytes into characters and **encode** characters back into bytes.

```text
byte[] --[decode with charset]--> String --[process text]-->
String --[encode with charset]--> byte[]
```

Both sides must agree on the encoding and follow its rules:

- **Malformed input:** a byte sequence that is not valid under the active charset—for example, a UTF-8 leading byte missing its continuation byte—or a Java string containing an unpaired surrogate when Unicode encoding is required.
- **Unmappable character:** a valid character that has no corresponding representation in the target encoding, such as `€` or `á` when encoding with US-ASCII. Some decoders can also report unmappable input when a charset does not map a valid byte sequence to a character.
- **Mojibake (garbled text from charset mismatch):** valid bytes decoded with a different charset than the one used to create them; the result consists of valid Unicode characters that read as gibberish, e.g., `café` becoming `cafÃ©`.
- **Data loss (lossy conversion):** original bytes or characters are replaced with another character, skipped, or transformed irreversibly. The `�` character (U+FFFD, REPLACEMENT CHARACTER) and `?` are two common symptoms, though their mere presence does not by itself prove data was corrupted.

Distinguish **invalid bytes** from **characters that look wrong**. A byte sequence may be valid in ISO-8859-1 while invalid in UTF-8; and the text `cafÃ©` contains no malformed UTF-8 bytes once it has become a `String`.

## 2. Common Symptoms

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| `�` appears mid-sentence | Decoder replaced malformed bytes with U+FFFD; or it was already present in the source | Preserve raw bytes; verify charset; decode in `REPORT` mode |
| `?` instead of accented letters or emoji | Encoder could not represent the character and used its replacement byte, often `0x3F` in ASCII | Check the writing charset and test encoder with `REPORT` |
| `Ã©`, `Â`, `â€™`, or gibberish without `�` | Bytes read with the wrong charset, or encoded/decoded multiple times | Trace the charset at each step and compare hex bytes |
| Missing characters or words merged together | System skipped errors with `IGNORE`, sliced bytes, sliced strings, or mishandled streams | Check lengths and data boundaries; avoid `IGNORE` |
| Unusual character at the start of text | BOM not handled properly or interpreted as content | Inspect leading bytes, file format, and BOM policy |
| Visually identical letters fail equality | Different Unicode code point sequences (e.g., precomposed vs. combining) | Print code points; consider Unicode normalization when business rules require it |

For instance, the UTF-8 bytes of `é` are `C3 A9`. Interpreting them as two ISO-8859-1 characters yields `Ã©`. This is a **misinterpretation of bytes**, not a UTF-8 syntax error caught by the decoder.

## 3. What Does a Malformed UTF-8 Sequence Look Like?

UTF-8 encodes a Unicode code point in one to four bytes. Continuation bytes start with bits `10`; a multi-byte leading byte must be followed by the exact number of continuation bytes while obeying Unicode range constraints.

Examples:

- `41` is a valid `A` character.
- `C3 A9` is a valid `é`.
- `C3 28` is **invalid**: `C3` requires a continuation byte, yet `28` is `(`, which does not match `10xxxxxx`.
- `E2 82` is **truncated**: insufficient bytes to complete a three-byte sequence.
- A lone continuation byte such as `80`, overlong encodings, encoded surrogate code points, or code points above `U+10FFFF` are all invalid UTF-8.

A decoder can report an error or apply a handling policy. When **REPLACE** is chosen, the decoder substitutes the malformed portion with its replacement string, typically U+FFFD for UTF-8; how many `�` characters appear depends on error segmentation, so never use the count of `�` marks to deduce exactly how many bytes were corrupted.

A `String` already containing U+FFFD can be validly UTF-8 encoded into three bytes `EF BF BD`. Re-encoding such a string does not restore the original bad bytes, and validating UTF-8 on the newly encoded bytes **cannot prove the original data was never lost**.

## 4. Default Behavior and the Three Error-Handling Policies

In Java:

- `new String(bytes, StandardCharsets.UTF_8)` converts bytes to text and **replaces** invalid byte sequences; therefore, it may not throw an exception.
- `text.getBytes(StandardCharsets.US_ASCII)` replaces unrepresentable characters with the charset's replacement byte, so it can return a byte array even though the text lost characters.
- `CharsetDecoder` created via `charset.newDecoder()` and `CharsetEncoder` created via `charset.newEncoder()` let you set two separate policies using `onMalformedInput(...)` and `onUnmappableCharacter(...)`.

| `CodingErrorAction` | Behavior | When to Use |
| --- | --- | --- |
| `REPORT` | Reports an error instead of altering data | Integrity-critical input, identifiers, protocols, testing |
| `REPLACE` | Uses a replacement string/byte | Displaying corrupted content when loss is acceptable and logged |
| `IGNORE` | Skips the erroneous portion | Rarely appropriate: can silently delete data without a trace |

`REPORT` is the safe choice when **preserving exact content is mandatory**. `REPLACE` fits readable display of a stream already known to contain errors, provided the result is never saved back as the authoritative source.

Note: decoder and encoder replacement behaviors differ. A UTF-8 decoder typically produces `�` (Unicode U+FFFD). A US-ASCII encoder typically produces byte `3F`, which reads back as `?`. Since `?` can also be a valid character typed by a user, looking only at the converted `String` is not enough to tell the difference.

## 5. Java 17+ Example: Detecting Instead of Silently Losing Data

Save `CharsetLossDemo.java` with UTF-8 source encoding:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CharsetLossDemo {
    public static void main(String[] args) {
        byte[] invalidUtf8 = {0x43, 0x61, (byte) 0xC3, 0x28};
        System.out.println("Replacement decode: "
                + new String(invalidUtf8, StandardCharsets.UTF_8));

        try {
            String strict = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8))
                    .toString();
            System.out.println("Valid UTF-8: " + strict);
        } catch (CharacterCodingException e) {
            System.out.println("Error reported: invalid UTF-8");
        }

        String original = "Giá €";
        byte[] ascii = original.getBytes(StandardCharsets.US_ASCII);
        System.out.println("Replacement ASCII encode: "
                + new String(ascii, StandardCharsets.US_ASCII));

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(original));
            System.out.println("ASCII can represent all characters");
        } catch (CharacterCodingException e) {
            System.out.println("Error reported: ASCII cannot represent character");
        }
    }
}
```

Compile and run in a terminal supporting UTF-8:

```bash
javac -encoding UTF-8 CharsetLossDemo.java
java CharsetLossDemo
```

Output (the `�` mark is a Unicode character, not `?`):

```text
Replacement decode: Ca�(
Error reported: invalid UTF-8
Replacement ASCII encode: Gi? ?
Error reported: ASCII cannot represent character
```

**Explanation:** the first two bytes `43 61` become `Ca`. Byte `C3` lacks a valid continuation byte so the string constructor inserts U+FFFD; `28` still becomes `(`. A decoder with `REPORT` throws a `CharacterCodingException` (specifically `MalformedInputException` here). Likewise, `á` and `€` lie outside US-ASCII; `getBytes(US_ASCII)` replaces both with `?`, whereas the strict encoder reports an unmappable error.

Do not use `try/catch` to proceed with saving the replacement version as if no error happened. Log the source location, expected charset, and error type; depending on the data contract, request retransmission, reject the record, or quarantine the corrupted data.

## 6. Wrong Charset While Bytes Are Still Valid: Mojibake

Save `MojibakeDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class MojibakeDemo {
    public static void main(String[] args) {
        byte[] utf8 = "café".getBytes(StandardCharsets.UTF_8);
        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
        System.out.println("Wrong charset: " + wrong);

        String recovered = new String(
                wrong.getBytes(StandardCharsets.ISO_8859_1),
                StandardCharsets.UTF_8);
        System.out.println("Recovered: " + recovered);
    }
}
```

```bash
javac -encoding UTF-8 MojibakeDemo.java
java MojibakeDemo
```

```text
Wrong charset: cafÃ©
Recovered: café
```

Here `wrong` contains only valid Unicode characters. The decoder cannot automatically know the byte author originally used UTF-8. Recovery works **in this specific case** because the misdecoded string preserved every byte value under ISO-8859-1 without being replaced, truncated, or normalized.

**Do not apply a charset-reversal formula blindly.** If `�`, `?`, or lossy operations already replaced original bytes/characters; if the content went through multiple transcoding passes; or if the assumed charset is wrong, reversing cannot reliably restore the data and can corrupt it further. To fix properly, go back to the source bytes/file/record and the actual charset metadata.

## 7. Can Lost Data Be Recovered?

Distinguish three cases:

1. **Original bytes remain and have not been overwritten:** you can usually try decoding again with the right charset; use a `REPORT` decoder to verify validity. If the charset is not self-describing, rely on metadata, protocol specs, or the data provider.
2. **Only a mojibake `String` remains, and the recent conversion was lossless:** sometimes reversible as in the `cafÃ©` example, after verifying the source and transformation chain.
3. **Bytes/characters were replaced with `�`/`?`, skipped, truncated, or overwritten:** the original data usually cannot be deduced accurately from the final output. Obtain the source again, restore from backup, or request retransmission; character-guessing heuristics do not guarantee integrity.

`U+FFFD` can appear **legitimately** in an original document, just as `?` can be punctuation. Therefore, never write rules like "delete every U+FFFD" or "replace every `?` with an accented letter." When input validation is required, validate while you still have the original byte array.

Beyond encoding, data loss can also stem from arbitrary Unicode normalization, slicing strings by UTF-16 code units, database column length truncation, business rules stripping diacritics, or converting to a narrower charset. Treat those as intentional transformations with their own tests, separate from malformed-byte handling.

## 8. Step-by-Step Diagnosis

When garbled text appears, check in this order:

1. **Isolate the boundary where corruption occurred:** reading a file, HTTP response bytes, queue message, database record, CSV/JSON conversion, logging, or file export. Do not patch the UI if the bytes were already broken upstream.
2. **Preserve bytes before decoding:** save a small sample in hex or a controlled binary file; avoid logging sensitive data. With `43 61 C3 28`, you can pinpoint that `C3` lacks a continuation byte.
3. **Verify the charset contract:** file/API charset parameters, HTTP `Content-Type`, JDBC configuration, and producer encoding. Never rely solely on the machine's default charset or guess from a few characters.
4. **Decode strictly before transforming:** `newDecoder().onMalformedInput(REPORT).onUnmappableCharacter(REPORT)` tells you whether input violates the chosen charset. A decoder only checks **validity under the chosen charset**; it cannot automatically catch every wrong-charset choice.
5. **Compare code points and bytes:** Java 17 provides `HexFormat.of().formatHex(bytes)` for hex inspection; `text.codePoints()` iterates Unicode code points. `String.length()` counts UTF-16 units and can differ from code point count, especially with emojis.
6. **Check round-trips where appropriate:** `decode(encode(text))` or `encode(decode(bytes))` can expose lossy steps, though it does not prove the chosen charset is right; mojibake data can round-trip cleanly under a wrong charset too.
7. **Trace the earliest mutation:** if the data was already wrong before entering Java, fix the producer or integration layer; if broken inside Java, fix the relevant configuration/I/O code and test with real bytes.

A small diagnostic snippet to use **inside a method** (given an existing `byte[] bytes` variable):

```java
System.out.println(java.util.HexFormat.of().formatHex(bytes));
String text = new String(bytes, StandardCharsets.UTF_8);
text.codePoints().forEach(cp ->
        System.out.printf("U+%04X ", cp));
System.out.println();
```

Note that `java.nio.charset.StandardCharsets` must be imported when using this snippet. The hex dump of input bytes and the code points of the decoded string provide **two distinct pieces of evidence**; neither can substitute for the other.

## 9. Reading and Writing Safely at I/O Boundaries

**Reading files:** if data must be valid UTF-8, configure a decoder to report errors before building strings. When working with streams, use a single decoder across the stream, such as passing a `REPORT`-configured `CharsetDecoder` to `InputStreamReader(InputStream, CharsetDecoder)`; handle `IOException`/`MalformedInputException` appropriately. Avoid decoding independent `byte[]` chunks because a UTF-8 character can span the boundary between two reads.

**Writing files:** set the charset explicitly when writing, such as `Files.writeString(path, text, StandardCharsets.UTF_8)` when the format requires UTF-8. If you must export to a restricted charset, use `CharsetEncoder` with `REPORT` to detect unmappable characters before writing; guard against partial writes and overwrites.

**HTTP, JSON, databases:** follow the agreed charset/format at each boundary. JSON over modern UTF-8 channels should be handled consistently; HTTP request/response bodies must match `Content-Type` and actual configuration. Never patch frontend issues with ad-hoc `new String(text.getBytes(...), ...)` conversions. With JDBC, prefer proper Unicode string APIs and inspect connection charset/collation/driver and the full I/O path, instead of applying a "band-aid" charset conversion after querying.

**BOM and Unicode:** a BOM is a leading signature in some formats; not every API strips it automatically, and UTF-8 does not require a BOM. Distinguish a leading U+FEFF from malformed data and handle it strictly per the file spec. NFC/NFD differences are a Unicode normalization concern, not invalid UTF-8 bytes.

## 10. Pitfalls to Avoid

- Relying on `Charset.defaultCharset()` or charset-less constructors at data-exchange boundaries; different environments can interpret bytes differently.
- Assuming Java always throws when `new String(bytes, UTF_8)` encounters bad bytes: that constructor can replace them silently.
- Using `CodingErrorAction.IGNORE` to "clean" data: bad bytes disappear, words can be joined incorrectly, and debugging becomes harder.
- Overwriting source data with a string containing replacement characters, destroying the chance to re-decode the original bytes.
- Confusing `�` with `?`, or automatically replacing all occurrences with a character guessed from context.
- Treating "no `�`" or "byte round-trip equality" as proof that the charset is right. Mojibake can occur without any exception.
- Splitting a byte stream into chunks and decoding each chunk separately, or slicing a `String` mid-surrogate pair; both can introduce boundary errors.
- Merging three distinct concerns—byte validation, text transcoding, and content normalization—into a single untested step.

## 11. Decision Rules and Self-Check Exercises

| Scenario | Appropriate Action |
| --- | --- |
| Receiving binary data declared as UTF-8, strict accuracy required | Keep source bytes, decode with `REPORT`, reject or quarantine on error |
| Only need to display old already-corrupted messages | `REPLACE` may be used, but log it and do not overwrite the original |
| Exporting Unicode text to US-ASCII | Check with `CharsetEncoder` using `REPORT`; switch format to UTF-8 or apply intentional transliteration |
| Seeing `cafÃ©` | Find the encoding charset and the reading charset; recover from source bytes when possible |
| Only `?` remains where original letters were | Check backups or original source; never assume you can recover from `?` |

Self-practice:

1. Change the example byte sequence to `E2 82` and `C3 A9`. Predict which case throws under `REPORT` and which yields `é`; then run it to verify.
2. Try encoding `"Xin chào 👋"` with `US_ASCII` and `UTF_8`. Identify which step risks data loss, then verify with a strict encoder.
3. Simulate sending UTF-8 bytes but reading with ISO-8859-1. Record the original hex, garbled text, and properly decoded text; explain the condition required for recovery.
4. Write a method that reads UTF-8 from an `InputStream` using a `REPORT` decoder and test a multi-byte sequence split across a buffer boundary.

**Principle:** raw bytes and the agreed charset are the anchor for diagnosis. Check for errors **before** replacing or ignoring; accept lossy conversions only when it is an intentional, tested decision.
