# Do Not Arbitrarily Split Byte or `char` Sequences in the Middle of a Character

## 1. The Problem: A Visible Character Is Not Necessarily One Byte or One `char`

In Java I/O, files and connections transmit **bytes**, whereas `String`, `Reader`, and `Writer` work with character data. When converting text into bytes (encoding), a single Unicode character may require multiple bytes. When representing text in a Java `String` (UTF-16), a single Unicode code point may likewise require **two `char`s**.

Therefore, the phrase “slice a segment of N characters” must clarify which unit is being counted:

1. **Byte**: storage/transmission unit; in UTF-8 one Unicode code point can occupy 1–4 bytes.
2. **UTF-16 code unit**: one Java `char` value, 16 bits wide; a code point outside the BMP occupies two code units.
3. **Unicode code point**: Unicode value (e.g., U+1F600 for 😀); one code point can occupy one or two `char`s.
4. **Grapheme cluster**: a unit readers perceive as a single character, sometimes composed of multiple code points (e.g., `e` with a combining acute accent, or an emoji joined by ZWJ).

If slicing at an arbitrary position, a program can split UTF-8 bytes in half, break apart a UTF-16 surrogate pair, or keep code points intact while still cutting across a **visible character cluster**.

### Illustration with `A😀B`

| Representation | Units | Length |
| --- | --- | ---: |
| Unicode code point | `A` · `😀` · `B` | 3 code points |
| Java UTF-16 `char` | `0041` · `D83D` · `DE00` · `0042` | 4 code units |
| UTF-8 bytes (hex) | `41` · `F0 9F 98 80` · `42` | 6 bytes |

The letter `A` occupies one UTF-8 byte and one `char`; the emoji 😀 occupies **four UTF-8 bytes** and **two UTF-16 `char`s**. Thus:

- Slicing the UTF-8 array after byte `F0`, `9F`, or `98` cuts through the emoji's encoded sequence.
- `"A😀B".substring(0, 2)` keeps `A` plus the **first half** of the surrogate pair; the result is a UTF-16 string invalid in pair structure.
- `"A😀B".substring(0, 3)` keeps the two code points `A` and 😀 intact.

This principle applies to every block read, packet send, field size limit, chunk split, content truncation, or `String` slice.

## 2. Why Must UTF-8 Never Be Cut at an Arbitrary Byte Offset?

UTF-8 is a variable-length encoding: ASCII code points use one byte, many Vietnamese characters typically use 2–3 bytes, and code points outside the BMP like 😀 use four bytes. A leading byte indicates the encoded sequence length; subsequent bytes are **continuation bytes**, having bit pattern `10xxxxxx`.

Example with emoji 😀 (U+1F600):

```text
Unicode code point:    U+1F600
Full UTF-8:            F0 9F 98 80
Split after 1 byte:    F0 | 9F 98 80
Split after 2 bytes:   F0 9F | 98 80
Split after 3 bytes:   F0 9F 98 | 80
Valid boundaries:      | F0 9F 98 80 |
```

With the three invalid cuts, neither piece on its own is a valid UTF-8 sequence corresponding to the original emoji. If each piece is decoded **separately** and the resulting `String`s are concatenated, the decoder may return the replacement character `U+FFFD` (�), throw an error, or drop data depending on configuration. Concatenating the bytes **before decoding** restores the original cleanly because the bytes have not been altered.

**Rule:** **Byte transmission/read** chunk boundaries may fall anywhere as long as the decoder preserves state and leftover bytes; **independently decoded text** boundaries must respect the encoding. You cannot force each `InputStream.read(byte[])` call to stop at the end of a Unicode code point: `InputStream` knows nothing about charsets.

### Checking only the `10xxxxxx` bits is not enough to validate text

In UTF-8 data **already known to be valid**, an offset immediately before a leading byte (or EOF) is a candidate code-point boundary. Yet scanning for non-continuation bytes **does not replace a validating decoder**: input can still contain overlong encodings, illegally encoded surrogates, out-of-range code points, or missing trailing bytes. When handling untrusted data, use a `CharsetDecoder` with an explicit error policy.

## 3. UTF-16 in Java: A `char` Is Not Always a Complete Character

Java `String` is accessed in **UTF-16 code units**:

- `String.length()` is the number of UTF-16 code units, **not** the number of code points or visible characters.
- `String.charAt(index)`, `substring(begin, end)`, `StringBuilder.delete(...)`, and `char[]` arrays operate by **code unit index**.
- For code points from U+10000 to U+10FFFF, UTF-16 uses a **surrogate pair**: a high surrogate (`D800–DBFF`) followed by a low surrogate (`DC00–DFFF`).
- A lone surrogate `char` is not a valid Unicode scalar value; encoding it standalone can trigger replacement or errors.

Example:

```java
String text = "A😀B";
System.out.println(text.length());                       // 4 UTF-16 units
System.out.println(text.codePointCount(0, text.length())); // 3 code points
```

This is a **contextual illustrative snippet**: the two lines print `4` and `3` respectively. To process whole code points, use `codePointAt`, `codePointBefore`, `offsetByCodePoints`, `codePoints()`, `Character.charCount`, and `StringBuilder.appendCodePoint`.

### Why doesn't `substring` guard surrogate pairs automatically?

`substring(begin, end)` accepts code-unit offsets, so Java allows constructing a `String` ending with an unpaired high surrogate. That does not make the Java program fail immediately. Failures usually surface **later**: when encoding to UTF-8, writing files, transmitting over the network, running algorithms expecting valid Unicode text, or rendering.

The code below risks corrupting text:

```java
// Wrong for the intent of “keep the first two code points.”
String result = "A😀B".substring(0, 2);
```

If you need the **first two code points**, locate the UTF-16 boundary with `offsetByCodePoints`:

```java
String text = "A😀B";
int end = text.offsetByCodePoints(0, 2);
String firstTwoCodePoints = text.substring(0, end); // "A😀"
```

`String.offsetByCodePoints` steps past complete surrogate pairs; however, if the input string **already contains unpaired surrogates**, validate the data before treating it as valid Unicode text.

## 4. Java 17 Example: Wrong Cut vs. Right Cut

The standalone program below demonstrates both UTF-8 byte boundaries and UTF-16 code-unit boundaries, with output independent of console fonts.

**File `UnicodeBoundaryDemo.java`** (save source in UTF-8):

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class UnicodeBoundaryDemo {
    public static void main(String[] args) {
        String text = "A😀B";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 hex: "
                + HexFormat.of().withUpperCase().formatHex(bytes));
        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: "
                + text.codePointCount(0, text.length()));

        // Slice after two UTF-16 code units: A + high surrogate.
        String wrongCharPrefix = text.substring(0, 2);
        System.out.println("Ends with high surrogate: "
                + Character.isHighSurrogate(
                        wrongCharPrefix.charAt(wrongCharPrefix.length() - 1)));

        // Slice properly after two Unicode code points: A + emoji.
        int safeEnd = text.offsetByCodePoints(0, 2);
        String left = text.substring(0, safeEnd);
        String right = text.substring(safeEnd);
        System.out.println("Safe substring round-trip: "
                + (left + right).equals(text));

        // Slice after byte 3: A + first two bytes of the four-byte emoji.
        byte[] invalidPrefix = Arrays.copyOfRange(bytes, 0, 3);
        boolean rejected = false;
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidPrefix));
        } catch (CharacterCodingException expected) {
            rejected = true;
        }
        System.out.println("Incomplete UTF-8 rejected: " + rejected);
        System.out.println("Full UTF-8 round-trip: "
                + text.equals(new String(bytes, StandardCharsets.UTF_8)));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 UnicodeBoundaryDemo.java
java UnicodeBoundaryDemo
```

**Exact stdout:**

```text
UTF-8 hex: 41F09F988042
UTF-16 units: 4
Code points: 3
Ends with high surrogate: true
Safe substring round-trip: true
Incomplete UTF-8 rejected: true
Full UTF-8 round-trip: true
```

Why did the strict decoder report an error in the example? Because the convenience `CharsetDecoder.decode(ByteBuffer)` method is invoked as an **entire-input decode**, so the segment `A F0 9F` ends while the UTF-8 sequence for 😀 still lacks all four bytes. That is **truncated data at EOF**. During streaming reads, an incomplete byte tail between reads **is not yet EOF** and must be retained for the next read.

## 5. Reading a Byte Stream into Text: Decoder State Must Carry Across Reads

Suppose a network stream returns the first two UTF-8 bytes in the first `read`, then returns the remaining two bytes in the next read. The byte stream **is not wrong**: `read` boundaries are transport details. The wrong way to handle it is:

```java
// Erroneous illustrative code: only makes sense if byteChunks is a list
// of byte blocks received from I/O.
for (byte[] chunk : byteChunks) {
    text.append(new String(chunk, StandardCharsets.UTF_8));
}
```

Each `new String(chunk, UTF_8)` creates a new decoder, treating the chunk as an **independent** UTF-8 text. If the chunk stops mid-sequence, the incomplete data is never joined to the next pass.

**Common safe approach:** wrap `InputStream` in **`InputStreamReader`** with `StandardCharsets.UTF_8` or a configured `CharsetDecoder`, then read `char[]`. The reader handles decoder state across byte pulls from the underlying stream. `BufferedReader` can be used for line-oriented text reading.

```java
// Illustrative snippet; InputStream source is already open and caller transfers ownership.
try (Reader reader = new InputStreamReader(source, StandardCharsets.UTF_8)) {
    char[] buffer = new char[2048];
    int count;
    while ((count = reader.read(buffer)) != -1) {
        // Process buffer[0 .. count) accurately, continuing to account for surrogates.
    }
}
```

`Reader` **does not automatically turn every `char[]` array into a complete displayed character cluster**. It decodes bytes accurately into UTF-16 code units, yet a surrogate pair can still be split at a `read(char[])` boundary. If you simply copy and concatenate all code units in order, data is preserved; if you treat each chunk **as an independent Unicode string**, you must still handle surrogate pairs at boundaries.

### Runnable example: an `InputStream` always returning at most one byte

The program creates a simulated stream that returns at most **one byte** whenever asked to read a byte array. This intentionally splits the UTF-8 bytes of Vietnamese characters and emojis.

**File `FragmentedUtf8Read.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

public class FragmentedUtf8Read {
    static class OneByteAtATime extends FilterInputStream {
        OneByteAtATime(InputStream delegate) {
            super(delegate);
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (len == 0) {
                return 0;
            }
            return in.read(b, off, Math.min(len, 1));
        }
    }

    public static void main(String[] args) throws IOException {
        String original = "Hà Nội 😀";
        byte[] sourceBytes = original.getBytes(StandardCharsets.UTF_8);
        StringBuilder restored = new StringBuilder();

        try (Reader reader = new InputStreamReader(
                new OneByteAtATime(new ByteArrayInputStream(sourceBytes)),
                StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }
        }

        System.out.println("Round-trip equal: "
                + original.contentEquals(restored));
        System.out.println("Unicode code points equal: "
                + (original.codePointCount(0, original.length())
                == restored.codePointCount(0, restored.length())));
    }
}
```

Run:

```bash
javac -encoding UTF-8 FragmentedUtf8Read.java
java FragmentedUtf8Read
```

**Exact stdout:**

```text
Round-trip equal: true
Unicode code points equal: true
```

Each read of a byte array from the source may return only one byte; `InputStreamReader` still decodes into valid Unicode by retaining decoder state. `StringBuilder.append(buffer, 0, count)` appends **the exact number of `char`s received** and preserves order. In the example, we neither decode each byte individually nor independently encode each `char[]` chunk.

## 6. Processing Code Points One by One from a `Reader` Without Splitting Surrogate Pairs

Some algorithms must process one code point at a time, such as allowlist character checks, Unicode classification, or custom code-point logic. Reading **one `char`** and treating it as the entire code point fails whenever encountering an emoji or another code point outside the BMP.

You must read and pair a high surrogate with the immediately following low surrogate:

```java
static int nextCodePoint(Reader reader) throws IOException {
    int first = reader.read();
    if (first == -1) {
        return -1; // EOF
    }

    char ch = (char) first;
    if (Character.isLowSurrogate(ch)) {
        throw new IOException("Unexpected low surrogate");
    }
    if (!Character.isHighSurrogate(ch)) {
        return first;
    }

    int second = reader.read();
    if (second == -1 || !Character.isLowSurrogate((char) second)) {
        throw new IOException("Broken surrogate pair");
    }
    return Character.toCodePoint(ch, (char) second);
}
```

This is an **illustrative method**, requiring `import java.io.Reader` and `java.io.IOException`; it is not a standalone program. It returns `-1` at EOF and a valid code point otherwise. In the high-surrogate branch, reading the next unit is mandatory to verify whether the pair is valid. If the data contains a lone low surrogate or a high surrogate without a low surrogate, the example chooses to **report an error** rather than silently substituting characters.

When a `String` is already in memory and known to be valid Unicode text, `String.codePoints()` or `offsetByCodePoints` is usually enough without writing a manual loop.

## 7. Slicing a `String` by Code Point Count, Not Blindly Taking `substring(0, n)`

`String.substring(0, n)` takes **n UTF-16 code units**, whereas “take n code points” means something else. A code-point-based slicing function can be written as:

```java
// Contextual method: requires String value and a valid count n.
static String prefixByCodePoints(String value, int n) {
    int count = value.codePointCount(0, value.length());
    if (n < 0 || n > count) {
        throw new IllegalArgumentException("Invalid code-point count");
    }
    int end = value.offsetByCodePoints(0, n);
    return value.substring(0, end);
}
```

This function will not split **properly paired surrogates**. However, `codePointCount` and `offsetByCodePoints` still step over an unpaired surrogate as its own code point per API rules; therefore, if Unicode validity is a security or data requirement, validate the string first.

When splitting a `String` into multiple segments, compute **each boundary by code point** and take `substring(start, end)` slices. Do not compute offsets with `index += n` code units, and do not divide `text.length() / parts` to slice directly.

### Code-point boundaries are still not display-character boundaries

For example, the letter `é` can be represented by **two code points**: `e` (U+0065) + combining acute accent (U+0301). Splitting after `e` keeps both code points valid, yet leaves the accent stranded at the start of the next segment. A family emoji joined with zero-width joiners (ZWJ) or a flag symbol can likewise span multiple code points.

If the requirement is “do not cut inside a character the user sees,” the unit to preserve is an **extended grapheme cluster**, not merely a Unicode code point. Java provides `BreakIterator.getCharacterInstance(locale)` for character break rules; however, you must verify Unicode/emoji compatibility on the **specific JDK version**. When an application depends strictly on modern emoji clusters, use a segmentation library conforming to Unicode UAX #29 and test combinations (for example, ICU4J). Never claim `codePoints()` alone suffices for all UI text-truncation tasks.

## 8. When a Data Field Limits UTF-8 Byte Count: Compute Code Point by Code Point

A common bug is enforcing a “maximum 5 bytes” payload limit by calling `Arrays.copyOf(utf8, 5)` without checking whether the fifth byte sits inside a sequence. Instead, for **valid Unicode text**, iterate code point by code point, compute its UTF-8 encoded byte count, and include the whole code point only if enough budget remains.

**File `Utf8ByteBudget.java`:**

```java
import java.nio.charset.StandardCharsets;

public class Utf8ByteBudget {
    static String prefixWithinUtf8Bytes(String text, int maxBytes) {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Negative byte budget");
        }

        StringBuilder result = new StringBuilder();
        int used = 0;

        for (int offset = 0; offset < text.length();) {
            int codePoint = text.codePointAt(offset);
            // Reject an unpaired surrogate.
            if (codePoint >= Character.MIN_SURROGATE
                    && codePoint <= Character.MAX_SURROGATE) {
                throw new IllegalArgumentException("Unpaired surrogate");
            }

            String single = new String(Character.toChars(codePoint));
            int byteCount = single.getBytes(StandardCharsets.UTF_8).length;

            if (byteCount > maxBytes - used) {
                break;
            }
            result.appendCodePoint(codePoint);
            used += byteCount;
            offset += Character.charCount(codePoint);
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String text = "A😀B";
        String at3 = prefixWithinUtf8Bytes(text, 3);
        String at5 = prefixWithinUtf8Bytes(text, 5);
        String at6 = prefixWithinUtf8Bytes(text, 6);

        System.out.println("Budget 3 bytes: "
                + at3.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 5 bytes: "
                + at5.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 6 bytes: "
                + at6.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("Budget 5 is A+emoji: " + at5.equals("A😀"));
        System.out.println("Budget 6 is all text: " + at6.equals(text));
    }
}
```

Run:

```bash
javac -encoding UTF-8 Utf8ByteBudget.java
java Utf8ByteBudget
```

**Exact stdout:**

```text
Budget 3 bytes: 1
Budget 5 bytes: 5
Budget 6 bytes: 6
Budget 5 is A+emoji: true
Budget 6 is all text: true
```

Because `A` takes one byte and 😀 takes four bytes, a three-byte budget keeps only `A`; a five-byte budget keeps `A😀`; a six-byte budget keeps all of `A😀B`. This function keeps a **contiguous prefix**: if the next code point does not fit, it stops rather than skipping it to grab later characters.

The code deliberately favors readability: allocating a temporary `String` and byte array per code point can be costly for very long strings. When optimizing, you can write a UTF-8 byte counter based on validated code-point ranges or use a `CharsetEncoder` with a bounded buffer. Never optimize by slicing a byte array at an arbitrary index and hoping the decoder fixes it.

**Scope note:** this function keeps each Unicode code point intact, yet can still cut inside a **grapheme cluster** such as a letter with combining marks. If a byte limit comes with a requirement not to split visible characters, segment by grapheme first and then encode/count bytes for the entire cluster.

## 9. Streaming Decoding Technique Using `CharsetDecoder`

When working at a lower layer (such as a parser receiving `ByteBuffer` from the network), `CharsetDecoder` gives precise control over handling incomplete byte input:

```text
Chunk 1: [F0 9F]             -- not enough UTF-8 bytes for 😀
                |
                v
    Decoder (endOfInput=false)
                |
    UNDERFLOW: retain F0 9F
                |
                v
Chunk 2: [98 80] + remaining bytes
                |
                v
    Decoder completes F0 9F 98 80 -> UTF-16 surrogate pair
```

Key concepts:

- `CharsetDecoder.decode(input, output, false)` can return `CoderResult.UNDERFLOW` when no more bytes suffice to produce another character; if `input` still holds partial bytes, **retain** them and combine with the next chunk.
- `CoderResult.OVERFLOW` means the output buffer is out of space; drain/process `CharBuffer` and call `decode` again with the remaining bytes.
- Once true EOF is reached, call `decode(..., true)`, then `flush(output)` per the decoder lifecycle to handle trailing state. Only then are truncated UTF-8 bytes classified as malformed per the error policy.
- After a decode pass, `ByteBuffer.compact()` shifts unconsumed bytes to the start of the buffer; then write new bytes and `flip()` before the next decode call.
- `onMalformedInput(CodingErrorAction.REPORT)` and `onUnmappableCharacter(CodingErrorAction.REPORT)` report errors instead of substituting; the other two `CodingErrorAction` choices are `REPLACE` or `IGNORE`.

The snippet above is a **workflow diagram**, not standalone program code. When using a stateful decoder, execute `decode`/`flush` in proper order, distinguish true EOF from chunk boundaries, and handle both `UNDERFLOW` and `OVERFLOW`. For most text-file tasks, using `InputStreamReader` with the right charset is simpler and less error-prone.

### How should invalid data be handled?

If the decoder is configured with `REPORT`, a bad UTF-8 sequence can cause `MalformedInputException` or `UnmappableCharacterException`. With `REPLACE`, replacement characters can appear and **the original data cannot be recovered** from the replaced text. With `IGNORE`, bad data can be silently dropped.

Context matters: logs may accept `REPLACE` to keep displaying, whereas config files, signed payloads, or integrity-critical systems should normally use `REPORT` and log/handle errors. Never treat a `String` appearing without a runtime exception as proof that the original bytes matched the charset.

## 10. Writing Text in Chunks: Never Encode Half a Surrogate Pair Independently

The symmetrical mistake to byte-decoding bugs is **encoding each `String`/`char[]` slice with a new encoder** when a slice cuts between a high surrogate and a low surrogate:

```java
// Error illustration: assume halves were sliced at an arbitrary char offset.
byte[] part1 = halves[0].getBytes(StandardCharsets.UTF_8);
byte[] part2 = halves[1].getBytes(StandardCharsets.UTF_8);
// Concatenating part1 and part2 will not necessarily equal encoding the original string.
```

The two `getBytes` calls perform two independent complete encodings. If `halves[0]` ends with a high surrogate and `halves[1]` starts with a low surrogate, each pass sees only **half a pair**, potentially replacing data or throwing an error. The fixes are:

1. If you already have the full `String`, use `offsetByCodePoints` boundaries (or graphemes when needed) before splitting into segments to encode **independently**.
2. If writing a continuous text stream, keep **one `Writer`/`CharsetEncoder`** across the stream lifecycle and close it properly; never spin up new encoders for arbitrary chunks.
3. If transferring data from `Reader` to `Writer`, use a continuous text pipeline; if processing chunks by code point, carry any trailing unpaired high surrogate over to the next chunk.
4. If the initial data is already UTF-8 bytes and only needs forwarding, it is best to keep the raw bytes and avoid unnecessary decode-then-re-encode passes.

A continuous writer can hold encoding state; however, do not assume calling `flush()` at an arbitrary boundary suffices to validly close out a dangling half-surrogate. For manually managed encoders, you must specify accurately when input has truly ended (`endOfInput`) and when more characters follow.

## 11. When Is Splitting “Allowed” vs. “Not Allowed”?

| Task | Can split at any offset? | Right Principle |
| --- | --- | --- |
| Sending UTF-8 bytes over a socket in multiple writes | Yes, if the receiver keeps continuity and decodes afterward / with a streaming decoder | TCP/byte chunk boundaries are not character boundaries |
| Saving raw bytes in blocks and reassembling in exact order | Yes | Do not decode individual blocks as standalone text |
| Creating multiple UTF-8 files where each must be readable standalone | No | Cut at UTF-8 code-point or higher text boundaries |
| `substring` to cap code point count | No | Call `offsetByCodePoints` before `substring` |
| Splitting display segments in UI without breaking joined emojis | No, not even at code-point boundaries | Grapheme cluster boundaries are required |
| Reading a text file into `char[]` chunks and concatenating in order | Yes, if individual arrays are not altered/corrupted | `Reader` decodes bytes; join all code units |
| Enforcing DB column limits measured in UTF-8 bytes | No | Count encoded bytes per valid code point/cluster |
| Splitting into chunks to call `String.getBytes(UTF_8)` independently | No, if cut inside a surrogate pair | Split at safe boundaries first, then encode |
| Needing exact byte-for-byte identity after copying | Can split blocks anywhere | Use byte streams; do not convert to text unnecessarily |

In other words, **splitting buffers itself is not the bug**. The bug is treating incomplete fragments of **a single encoded representation** as standalone characters or texts, or altering fragments and losing the information needed to reassemble them.

## 12. Common Bugs and How to Spot Them

### 12.1 A character is replaced with �

The usual cause is decoding an incomplete UTF-8 fragment as a complete text or choosing the wrong charset. Inspect the original bytes in hex, the producer's charset, and the chunking logic. Use a `REPORT` decoder in tests to catch errors early instead of defaulting to replacement.

### 12.2 `String.length()` is smaller/larger than the visible letter count

`String.length()` is the UTF-16 code unit count. For emojis outside the BMP, this number **exceeds the code point count**; for accented combining sequences or joined emojis, **even the code point count can exceed the grapheme count**. Do not rely on `length()` alone to measure visible characters in UI.

### 12.3 Text looks right in ASCII tests yet fails with Vietnamese/emojis

ASCII is a subset of UTF-8 where every code point occupies one byte and one UTF-16 code unit. Testing `"Hello"` never exposes boundary bugs. Test suites must include ASCII, accented Vietnamese, 2–3 byte characters, four-byte emojis, combining marks, and arbitrary chunk boundaries.

### 12.4 Reading a small `char` buffer and treating each array as a “complete sentence”

`Reader.read(char[])` returns only the number of code units actually read, which can stop in the middle of a surrogate pair. Carry over incomplete fragments or process through a stateful code-point iterator; avoid calling `new String(buffer, 0, count)` and encoding **each fragment independently** without checking surrogate boundaries.

### 12.5 Calling `CharsetDecoder.decode` independently on every `ByteBuffer`

The convenience `decode(ByteBuffer)` method means decode-entire-input, so a split block triggers an end-of-input error. For streaming, reuse the decoder across chunks with `decode(..., false)` and terminate with `true` only at real EOF. For routine text reading, use `InputStreamReader`.

### 12.6 Cutting at code points yet still breaking glyphs on screen

Words with combining marks, ZWJ emojis, or flag emojis can contain multiple code points within one grapheme. Splitting at a code-point boundary can still tear apart a visible character. For UI requirements, segment graphemes using an appropriate Unicode algorithm.

## 13. Boundary and Integrity Testing Strategy

When building a text I/O system or chunking API, test **invariants** instead of relying on visual inspection alone:

- **Byte invariant:** for pure byte split/join operations, `Arrays.equals(originalBytes, joinedChunks)` must be `true`.
- **Text invariant:** for valid UTF-8 input, continuous decoding with the same charset must reproduce the exact original string: `original.equals(decoded)`.
- **Surrogate-pair invariant:** substrings claimed to be valid Unicode must never end with a lone high surrogate or start with a lone low surrogate.
- **Byte-budget invariant:** `prefix.getBytes(UTF_8).length <= maxBytes`, and `prefix` must be a contiguous prefix of the input in the chosen unit.
- **Display-cluster invariant:** for UI requirements, never split inside a grapheme cluster, including combining marks and composite emojis.
- **EOF invariant:** a chunk temporarily running out of bytes does not mean stream end; invoke decoder end-of-input only at true EOF.

The most important boundary tests split **immediately after every byte** of multi-byte UTF-8 sequences and **right between high/low surrogates**. For `A😀B`, test every split offset from byte 1 to byte 5 and from UTF-16 offset 1 to 3; compare decoding fragments separately against decoding the reassembled stream.

For untrusted data, add malformed UTF-8 cases: continuation byte missing a starter, starter missing a continuation, overlong sequences, surrogate code points, and out-of-range code points. `CharsetDecoder` in `REPORT` mode helps verify consistent error behavior.

## 14. Practice Exercises

1. For the string `"Xé😀Y"`, write down `length()`, `codePointCount(0, length())`, and the UTF-8 byte count. Explain why the numbers differ.
2. Manually slice the UTF-8 bytes of emoji 😀 at three wrong positions, decode each slice with `new String(bytes, UTF_8)`, observe the replacement characters, then try joining **bytes** before decoding.
3. Using `String.offsetByCodePoints(0, n)`, write a function returning the first `n` code points, then test it with Vietnamese text, emojis, and combining accents.
4. Modify `FragmentedUtf8Read` so each read returns at most two bytes. Verify that `Round-trip equal: true` still holds.
5. Test `Utf8ByteBudget` for budgets of 0, 1, 4, 5, and 6 bytes; write an assertion that the returned slice always decodes cleanly as UTF-8.
6. Build an example containing `"e\u0301"` (letter `e` plus combining acute accent). Explain why slicing by one code point still fails to preserve the displayed character cluster.
7. Suppose a system sends UTF-8 content over the network in variable-sized chunks. Compare three approaches: decoding each chunk with `new String`, buffering all bytes then decoding once, and using `InputStreamReader`/a streaming decoder. Choose the right approach when content can be very large.
8. Given a `byte[]` containing invalid UTF-8 data, write a method that raises an error upon hitting bad bytes using `newDecoder().onMalformedInput(REPORT)`, and explain why this avoids silent data loss.

## 15. Takeaways and Further Reading

The core point is not avoiding every buffer split, but **respecting the boundaries of the unit being processed**:

1. **Byte streams** may be split into arbitrary blocks provided bytes are reassembled in order before decoding, or a stateful decoder is used.
2. **Standalone UTF-8 text** must keep each code point's byte sequence intact; an incomplete byte fragment is not a valid character.
3. **Java `char` is a UTF-16 code unit**; never split high/low surrogates when slicing by code point. Use `String.offsetByCodePoints`/`codePoints`.
4. **Visible characters** can consist of multiple code points; segment by grapheme when the application/UI must not tear apart what the user sees.
5. **Decoding/encoding errors** require explicit policies (`REPORT`, `REPLACE`, `IGNORE`) and testing with multi-byte inputs, not ASCII alone.

Official documentation for reference: [`String` in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [`Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html), and [Unicode Text Segmentation (UAX #29)](https://unicode.org/reports/tr29/).