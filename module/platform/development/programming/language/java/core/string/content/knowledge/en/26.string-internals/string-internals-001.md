# Distinguishing the API's UTF-16 Model from the Internal Representation of Java String

When working with `String`, Java developers often hear two statements that seem contradictory:

- The `String` API uses **UTF-16 code unit indices**. Therefore, `length()`, `charAt()`, `substring()`, and many returned positions follow this indexing scheme.
- On modern **OpenJDK/HotSpot** builds, `String` typically uses **Compact Strings**: an internal `byte[]` array plus metadata indicating whether the data is stored in Latin-1 or UTF-16 form. An ASCII string may require only one byte per code unit in its backing data region.

These two statements are **not contradictory**: **what the API guarantees** differs from **how the JVM is allowed to optimize in-memory representation**. Programs must rely on the API contract; internal storage details should only be used to understand performance/memory and always depend on the JVM version and vendor.

## 1. Three concepts that must be distinguished

| Concept | Unit | Role |
| --- | --- | --- |
| **UTF-16 code unit** | A 16-bit value; represented in Java by `char` | Indexing unit for `String.length()`, `charAt()`, `substring()` |
| **Unicode code point** | A Unicode value such as U+0041 or U+1F600 | Common unit when processing Unicode characters, looking up `codePointAt()`, iterating with `codePoints()` |
| **Stored or transmitted byte** | 8 bits | Can be an internal byte chosen by the JVM, or an external byte produced by `getBytes(charset)`; the two cases are different |

**Do not equate these three units.** In UTF-16:

- A code point in the **BMP** (Basic Multilingual Plane), such as `A` (U+0041) or `Đ` (U+0110), normally occupies **one** UTF-16 code unit.
- A code point **outside the BMP**, such as the emoji `😀` (U+1F600), requires **two** consecutive UTF-16 code units: a **high surrogate** `U+D83D` and a **low surrogate** `U+DE00`.
- A **user-perceived character** (*grapheme cluster*) can even consist of **multiple code points**; for example, the letter `e` followed by the combining acute accent `U+0301` usually looks like `é`.

`String` is a sequence of UTF-16 `char` values under the API model. It can even contain an unpaired surrogate, even though a lone surrogate **is not a valid Unicode scalar value** to convert directly into standard UTF-8.

## 2. APIs are based on UTF-16 indices, not byte counts

Consider the Java value:

~~~java
String text = "A\uD83D\uDE00B"; // A😀B, written using Unicode escapes
~~~

The array of code units observed through the API:

~~~text
UTF-16 index:    0       1          2       3
charAt(index): U+0041  U+D83D     U+DE00   U+0042
Code point:    U+0041  <--- U+1F600 --->   U+0042
Display glyph:   A            😀               B
~~~

Therefore:

- `text.length()` is **4**: the total number of UTF-16 code units.
- `text.codePointCount(0, text.length())` is **3**: `A`, `😀`, `B`.
- `text.charAt(1)` is the **high surrogate** `\uD83D`, **not** the entire emoji.
- `text.codePointAt(1)` combines the surrogate pair starting at index 1 and returns `0x1F600`.
- `text.indexOf("B")` is **3**, because the result uses UTF-16 indices.
- `text.substring(1, 3)` takes the full surrogate pair, producing `😀` properly.
- `text.substring(1, 2)` takes only the first half of the surrogate pair, creating a `String` of length 1 code unit without a complete emoji code point.

### Standalone Java 17 program

~~~java
// Utf16ApiDemo.java
public class Utf16ApiDemo {
    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("length = " + text.length());
        System.out.println("codePointCount = "
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("charAt(%d) = U+%04X%n",
                    i, (int) text.charAt(i));
        }

        System.out.printf("codePointAt(1) = U+%04X%n",
                text.codePointAt(1));
        System.out.println("indexOf(B) = " + text.indexOf("B"));
        System.out.println("offsetByCodePoints(1, 1) = "
                + text.offsetByCodePoints(1, 1));

        String emoji = text.substring(1, 3);
        System.out.println("emoji slice equals original = "
                + emoji.equals("\uD83D\uDE00"));

        String half = text.substring(1, 2);
        System.out.println("half.length = " + half.length());
        System.out.println("half is high surrogate = "
                + Character.isHighSurrogate(half.charAt(0)));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 Utf16ApiDemo.java
java Utf16ApiDemo
~~~

Exact stdout:

~~~text
length = 4
codePointCount = 3
charAt(0) = U+0041
charAt(1) = U+D83D
charAt(2) = U+DE00
charAt(3) = U+0042
codePointAt(1) = U+1F600
indexOf(B) = 3
offsetByCodePoints(1, 1) = 3
emoji slice equals original = true
half.length = 1
half is high surrogate = true
~~~

Here `offsetByCodePoints(1, 1)` finds the UTF-16 index after **one code point** starting at index 1: it skips both code units of the emoji and returns 3. This method is useful when you need to process Unicode by code point while still interacting with APIs that accept UTF-16 indices.

## 3. `char`, `chars()`, `codePoints()`: similar names, different meanings

`char` is an **unsigned 16-bit** primitive type in Java. `String.charAt(i)` returns **one** `char`; therefore, it can return a surrogate rather than a complete visible character.

Two important stream methods:

~~~java
String text = "A\uD83D\uDE00B";

text.chars();      // IntStream of UTF-16 code units: 0x0041, 0xD83D, 0xDE00, 0x0042
text.codePoints(); // IntStream of code points:       0x0041, 0x1F600,       0x0042
~~~

This is an API call illustration snippet, not a standalone program. `chars()` widens each `char` into an `int` value; `codePoints()` merges a valid surrogate pair into one code point. If a surrogate lacks a valid partner, `codePoints()` may still emit that unpaired surrogate value according to API rules; do not assume this operation automatically "fixes" a malformed string into valid Unicode.

When you need to convert a code point into Java UTF-16 code units, use `Character.toChars(codePoint)`; when you need to compute how many `char` values a code point occupies, use `Character.charCount(codePoint)` (1 or 2 for valid code points). These calculations serve the **API's UTF-16 model**, not the internal byte count inside a `String` object.

## 4. Internal representation: history and Compact Strings

In many OpenJDK versions prior to Java 9, `String` content was held in a `char[]` array. Starting in Java 9, **JEP 254 — Compact Strings** switched to a `byte[]` array accompanied by internal encoding information (`coder`). If all code units lie within U+0000–U+00FF, the **LATIN1** representation can use one byte per code unit; if any unit lies outside that range, the **UTF16** representation requires two bytes per code unit in the backing array.

For example, `"café"` consists of 4 code units that all belong to Latin-1, whereas `"Đ"` contains U+0110 outside Latin-1. On HotSpot with Compact Strings enabled, the backing data of these two strings **can** use two different storage formats; `length()`, `charAt()`, and index-based slicing still retain UTF-16 semantics.

| Observation level | What is guaranteed |
| --- | --- |
| **Public API** | `length()` counts UTF-16 code units; `charAt()`, `substring()`, `codePointAt()` follow the API |
| **OpenJDK details** | `byte[]`, `coder`, LATIN1/UTF16, JIT optimizations, and memory-sharing strategies may change |
| **Exchanged byte count** | Determined by the charset passed to `getBytes(charset)`, not by `coder` |

Do not use reflection on `String`'s `private` fields to solve Unicode problems, and do not infer heap size from `length()`. The article on **Compact Strings and the LATIN1, UTF16 representations** goes deeper into coder selection rules, layout, VM options, and corresponding experiments.

## 5. Why changing the internal representation does not change `String.length()`

A key example:

~~~java
String latin = "café";  // 4 code units
String wide = "Đ";      // 1 code unit
~~~

On OpenJDK/HotSpot with Compact Strings, `latin` typically has internal data stored at one byte per code unit, while `wide` may need two bytes per code unit. **However**:

~~~java
System.out.println(latin.length()); // 4
System.out.println(wide.length());  // 1
~~~

The results `4` and `1` are always based on the **number of UTF-16 code units under the API**. Likewise, despite memory optimizations, `charAt()` still returns a single UTF-16 unit: the runtime decodes the value from the internal representation before exposing it through the API.

Do not imagine that a Java program directly observes the compacted bytes through `charAt()`. It sees the **logical value**; reading the physical data is the job of the standard library and the JVM.

## 6. Bytes produced by `getBytes(charset)` are a different matter

`String.getBytes(StandardCharsets.UTF_8)` generates data for **external output** in UTF-8. `String.getBytes(StandardCharsets.UTF_16BE)` produces bytes in UTF-16 big-endian. These are **two encoding operations**, not windows into the internal `byte[]`.

For `"A😀B"`:

| Perspective | Result |
| --- | --- |
| `String.length()` | 4 UTF-16 units |
| `codePointCount(...)` | 3 code points |
| `getBytes(UTF_8)` | 6 bytes: `41 F0 9F 98 80 42` |
| `getBytes(UTF_16BE)` | 8 bytes: `00 41 D8 3D DE 00 00 42` |
| Java's `getBytes(UTF_16)` | 10 bytes: `FE FF` (BOM) + 8 UTF-16BE bytes |
| Internal `String` memory in HotSpot | Not determinable from the APIs above alone; depends on implementation and object specifics |

### Standalone Java 17 program

~~~java
// StringBytesDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class StringBytesDemo {
    static void show(String name, byte[] bytes) {
        System.out.println(name + " = "
                + HexFormat.of().withUpperCase().formatHex(bytes)
                + " (" + bytes.length + " bytes)");
    }

    public static void main(String[] args) {
        String text = "A\uD83D\uDE00B";

        System.out.println("UTF-16 code units = " + text.length());
        show("UTF-8", text.getBytes(StandardCharsets.UTF_8));
        show("UTF-16BE", text.getBytes(StandardCharsets.UTF_16BE));
        show("UTF-16", text.getBytes(StandardCharsets.UTF_16));
    }
}
~~~

Run:

~~~bash
javac --release 17 StringBytesDemo.java
java StringBytesDemo
~~~

Stdout:

~~~text
UTF-16 code units = 4
UTF-8 = 41F09F988042 (6 bytes)
UTF-16BE = 0041D83DDE000042 (8 bytes)
UTF-16 = FEFF0041D83DDE000042 (10 bytes)
~~~

The bytes `FE FF` in the last example are the **Byte Order Mark (BOM)** emitted by Java's `StandardCharsets.UTF_16` according to this encoder's rules. `UTF_16BE` does not prepend a BOM as shown in the example. The **exported** byte array varies with the charset; you cannot infer from this that HotSpot stores the physical bytes of `String` with the same byte order or with a BOM in memory.

When sending text over the network or writing files, **always specify an agreed-upon charset**, such as `StandardCharsets.UTF_8`. Never treat internal `String` fields as an interchange data format.

## 7. Even a code point is not always a visible character

Beyond the difference between code units and code points, Unicode also has the **grapheme cluster**: a sequence that readers usually perceive as a single character. For example:

- `"\u00E9"`: `é` as **one code point** U+00E9; `length() == 1`.
- `"e\u0301"`: letter `e` + combining acute accent U+0301, **two code points** and **two code units**; visually it may look like `é`.
- Emojis built from components joined by a **zero-width joiner (ZWJ)** or skin-tone modifiers can span **multiple code points** while displaying as a single symbol.

Two `String` values that look identical do not necessarily cause `equals()` to return `true`. Java does not automatically normalize Unicode inside `String.equals()`. If a problem requires comparing normalized text, perform a separate step using `java.text.Normalizer`, and determine any additional language/locale rules as needed. Normalization is **not** part of Compact Strings.

### Java 17 example

~~~java
// UnicodeNormalizationDemo.java
import java.text.Normalizer;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";   // é, one code point
        String decomposed = "e\u0301"; // e + combining acute accent

        System.out.println("composed length = " + composed.length());
        System.out.println("decomposed length = " + decomposed.length());
        System.out.println("raw equals = " + composed.equals(decomposed));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals = " + composed.equals(normalized));
    }
}
~~~

Run commands:

~~~bash
javac --release 17 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Output:

~~~text
composed length = 1
decomposed length = 2
raw equals = false
NFC equals = true
~~~

`Normalizer.Form.NFC` converts eligible combining sequences into canonical precomposed form. It does **not** solve every problem involving counting visible characters, splitting emoji clusters, or natural-language processing.

## 8. Practical programming implications

### Slicing strings without splitting surrogate pairs

If a loop iterates via `charAt(i)`, you may be inspecting **half a code point**. When you need to iterate by code point, use `text.codePoints()` or the pair `codePointAt(i)` and `Character.charCount(cp)`:

~~~java
// Iterate over each code point without splitting a surrogate pair.
// Illustrative snippet placed inside a Java method with a String text variable.
for (int i = 0; i < text.length(); ) {
    int cp = text.codePointAt(i);
    // Process code point cp here.
    i += Character.charCount(cp);
}
~~~

If you need to handle **grapheme clusters**, code points are still not enough; you need a Unicode segmentation solution appropriate to your version and goals, along with tests for combining marks/emojis. Do not slice with `substring(0, n)` using an `n` derived from "number of visible characters" without first converting it to a safe UTF-16 index.

### Calculating storage size or input limits

`String.length()` **does not measure bytes** sent over HTTP or written to files. To check a byte limit for a specific charset:

~~~java
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
~~~

This is an illustrative snippet (requires importing `StandardCharsets` and having a `String text` variable). For large data, use an encoder/stream instead of allocating an entire byte array just to count. If a system imposes limits by **code points** or **graphemes**, implement the exact unit specified by the requirement.

### Performance and memory

Compact Strings can reduce the in-memory data region for many Latin-1 strings. However, simple math like `length * 1` or `length * 2` is only an **estimate of the backing storage** in a specific implementation, **not the actual object size**. Beyond the byte storage, there are object headers, references, metadata, alignment, GC/JIT behavior, and temporary overhead.

If you are optimizing memory on a specific JVM, measure with a **profiler/JOL** or an appropriate heap analysis tool; do not try to predict exact bytes from `String.length()` or by accessing private fields. On HotSpot builds supporting this flag, `-XX:-CompactStrings` can be used in experiments to disable Compact Strings, but this is an **implementation option**, not a Java SE requirement.

Example test on a compatible HotSpot JVM:

~~~bash
java Utf16ApiDemo
java -XX:-CompactStrings Utf16ApiDemo
~~~

**The API output must be identical**, even though internal storage and memory usage may differ. You neither need nor should change JVM flags to fix an application's Unicode handling logic.

### Distinguishing from `char[]` or `StringBuilder`

Calling `text.toCharArray()` returns a **public `char[]` array** containing the UTF-16 code units, meaning each array element is a 16-bit `char`. That **does not prove** the original `String` stored its data in a `char[]`. `StringBuilder` also provides an API based on `char` indices, but how it allocates and stores data internally is an implementation detail; never infer `String`'s representation from another API that happens to share the same return type.

## 9. Common mistakes and how to spot them

1. **"Java `String` always stores two bytes per character."** False because it confuses the UTF-16 API with the implementation. Java 9+ on common HotSpot/OpenJDK builds can store Latin-1 using one byte per code unit. And a code point outside the BMP even needs two code units.
2. **"`String.length()` is the number of visible characters."** False for surrogate pairs, combining marks, ZWJ clusters, and many other Unicode cases.
3. **"`charAt(i)` always returns a complete Unicode code point."** False: `char` is only 16 bits wide and can be a high or low surrogate.
4. **"`getBytes()` reveals the bytes on the heap."** False: it is an **encoding** operation into the specified or default charset; the output bytes are not a snapshot of how the JVM stores the `String`.
5. **"UTF-16BE and `StandardCharsets.UTF_16` always produce the same bytes."** False: `UTF_16` can emit a BOM such as `FE FF` in the example; you must distinguish specific charsets.
6. **"Having non-ASCII Unicode characters definitely requires two internal bytes per code unit."** Not necessarily: `é` belongs to Latin-1; `Đ` does not. You must consider the **set of code units across the whole string** and the implementation in use.
7. **"Slicing a string at any index is always safe."** `substring` can split a surrogate pair in half. If you need code point or grapheme units, you must convert indices or segment intentionally.
8. **"Two strings that render the same return true for `equals()`."** False if they use different code unit sequences, such as NFC versus a sequence with combining marks.
9. **"You can rely on `String`'s private fields in algorithms."** Those fields are not part of the Java SE contract and may be changed by the JVM or restricted by the module system.
10. **"Disabling Compact Strings changes `length()` or `charAt()`."** False for a Java SE–compliant implementation: internal representation optimizations must preserve API behavior.

## 10. Self-check questions

**Question 1.** For `String s = "A\uD83D\uDE00B";`, what are `s.length()`, `s.codePointCount(0, s.length())`, and the UTF-8 byte count?

**Answer:** `4` code units, `3` code points, `6` bytes. The emoji U+1F600 occupies two UTF-16 code units but four UTF-8 bytes.

**Question 2.** Why can `"café"` use the Compact Strings Latin-1 path, whereas `"Đ"` requires the UTF-16 representation in a typical HotSpot implementation?

**Answer:** All code units of `"café"` lie in U+0000–U+00FF, including `é` U+00E9; `Đ` U+0110 lies outside that range. This is the selection condition for the **in-memory representation**, without changing API semantics.

**Question 3.** What does `text.substring(1, 2)` contain when `text = "A\uD83D\uDE00B"`?

**Answer:** Only the high surrogate `U+D83D`, not the complete emoji. To extract the emoji, use `substring(1, 3)`.

**Question 4.** When encoding `"A😀B"` as `UTF_16BE`, why are there 8 bytes? When encoding as `UTF_8`, why are there 6 bytes?

**Answer:** Under the UTF-16 model there are 4 code units × 2 bytes = 8 bytes in UTF-16BE. UTF-8 uses 1 byte for `A`, 4 bytes for `😀`, and 1 byte for `B`, totaling 6. These are **encoded interchange bytes**, not the object size on the heap.

**Question 5.** Can you determine how many bytes a `String` uses in the JVM solely from `length()` or `getBytes(UTF_8).length`?

**Answer:** No. Those two values carry API/charset meanings; actual size also depends on the implementation, Compact Strings selection, headers, and memory management mechanisms.

## Key takeaways

**The API's UTF-16 model is the stable contract; internal representation is an optimizable JVM detail.** Read `length()` and `String` indices in terms of **UTF-16 code units**; use `codePoints()`, `codePointAt()`, and `offsetByCodePoints()` when you need code points; use a dedicated Unicode segmentation solution when you need **user-perceived characters**; and use `getBytes(charset)` to measure **transmitted/stored** bytes, not the internal bytes of a `String`.

References: [Java 17 `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [JEP 254 — Compact Strings](https://openjdk.org/jeps/254), and [Java 17 `Character` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).
