# Evaluating String Memory and Results on ASCII, Vietnamese, and Emoji Data

**String.length() does not return the number of bytes.** In Java, ASCII strings, Vietnamese text, and emojis can differ in their UTF-16 code unit count, Unicode code point count, UTF-8 encoded byte size, and object memory footprint in the JVM. Evaluating String performance requires clearly specifying the **unit of measurement**, **input data**, **operation**, and **JVM version**.

This lesson builds a comparison runnable on Java 17+, explains Compact Strings, highlights error-prone Unicode cases, and outlines proper heap and performance measurement practices. Encoded byte counts are determined directly from the data; internal payload figures are **conditional estimates**, while actual runtime and heap usage must be measured with tools.

## 1. Quantities to Distinguish

| Quantity | How to obtain in Java | What it represents |
| --- | --- | --- |
| **UTF-16 code unit** | **s.length()** | Number of **char** units in the Java String API model |
| **Unicode code point** | **s.codePointCount(0, s.length())** | Number of Unicode code points, not necessarily visible characters |
| **UTF-8 bytes** | **s.getBytes(StandardCharsets.UTF_8).length** | Byte size when transmitting or storing in UTF-8 format |
| **Grapheme cluster** | Unicode-compliant grapheme segmenter | User-perceived character unit; may consist of multiple code points |
| **Heap memory** | Profiler / heap dump / JOL depending on goal | Object header, internal byte[], references, padding, and retained data |
| **Allocation/op** | Benchmark / GC profiler | Temporary memory allocated per operation |

Do not infer heap size from **getBytes(UTF_8).length**. Calling **getBytes** may also allocate a new byte array for the encoded data.

### How Do UTF-16 Units and Code Points Differ?

A **char** in Java stores a 16-bit code unit, which is not always a complete Unicode code point. Many characters in the BMP need one unit; a code point outside the BMP, such as the emoji **🙂**, needs **two units** called a *surrogate pair*. Thus **"🙂".length() is 2** while codePointCount is **1**.

Conversely, a displayed emoji sequence such as **👩‍💻** contains **three code points**: 👩, ZWJ (joiner character U+200D), and 💻. Because the two component emoji symbols lie outside the BMP, the string requires **five UTF-16 code units**, while a renderer may draw it as **one** symbol.

## 2. Representative Dataset and Exact Figures

We use six test cases:

- **ASCII**: five ASCII letters.
- **café**: contains **é** U+00E9, outside ASCII but within Latin-1.
- **Việt**: contains **ệ** U+1EC7, outside Latin-1.
- **🙂**: one code point outside the BMP.
- **👩‍💻**: an emoji sequence with ZWJ joining three code points.
- **Việt**: Unicode decomposed form, consisting of **V, i, e, combining dot below U+0323, combining circumflex U+0302, t**. NFC normalization yields the equivalent form **Việt**.

| Data | **length()** | **codePointCount()** | **UTF-8 bytes** |
| --- | ---: | ---: | ---: |
| ASCII | 5 | 5 | 5 |
| café | 4 | 4 | 5 |
| Việt | 4 | 4 | 6 |
| 🙂 | 2 | 1 | 4 |
| 👩‍💻 | 5 | 3 | 11 |
| Decomposed Việt | 6 | 6 | 8 |

**Explanation:**

- ASCII: each ordinary character corresponds to one code unit and one UTF-8 byte.
- The letter **é** encodes in UTF-8 as two bytes yet only one UTF-16 unit.
- The letter **ệ** encodes in UTF-8 as three bytes and one UTF-16 unit.
- **🙂** uses two UTF-16 units yet only one code point; UTF-8 uses four bytes.
- **👩‍💻** has three code points: 4 UTF-8 bytes for 👩, 3 bytes for ZWJ, and 4 bytes for 💻, totaling 11.
- Two combining marks in **Việt** increase both the code unit/code point counts and the byte size, even though visual rendering may look identical to the precomposed form.

You cannot take a single number of **“characters”** and treat it simultaneously as length, code points, graphemes, and bytes.

## 3. Runnable Java 17+ Example

Create the file **StringMemoryComparison.java** with the following content:

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class StringMemoryComparison {
    public static void main(String[] args) {
        String vietnamese = "Vi\u1EC7t";
        String decomposed = "Vie\u0323\u0302t";

        describe("ASCII", "ASCII");
        describe("Latin1", "caf\u00E9");
        describe("Vietnamese", vietnamese);
        describe("Emoji", "\uD83D\uDE42");
        describe("EmojiZWJ", "\uD83D\uDC69\u200D\uD83D\uDCBB");
        describe("Decomposed", decomposed);

        System.out.println("raw equal: "
                + decomposed.equals(vietnamese));
        System.out.println("NFC equal: "
                + Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)
                        .equals(vietnamese));
    }

    private static void describe(String name, String value) {
        int units = value.length();
        int points = value.codePointCount(0, units);
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;

        boolean latin1 = value.chars()
                .allMatch(unit -> unit <= 0xFF);
        int payloadEstimate = units * (latin1 ? 1 : 2);

        System.out.println(name + ": utf16=" + units
                + ", codePoints=" + points
                + ", utf8Bytes=" + utf8Bytes
                + ", compactPayloadEstimate=" + payloadEstimate);
    }
}
~~~

Unicode escapes accurately represent the Vietnamese characters and emojis, even when a console font cannot render them. The program prints ASCII labels so stdout does not depend on terminal Unicode rendering.

Run:

~~~bash
javac -encoding UTF-8 StringMemoryComparison.java
java StringMemoryComparison
~~~

Stdout (verified with Java):

~~~text
ASCII: utf16=5, codePoints=5, utf8Bytes=5, compactPayloadEstimate=5
Latin1: utf16=4, codePoints=4, utf8Bytes=5, compactPayloadEstimate=4
Vietnamese: utf16=4, codePoints=4, utf8Bytes=6, compactPayloadEstimate=8
Emoji: utf16=2, codePoints=1, utf8Bytes=4, compactPayloadEstimate=4
EmojiZWJ: utf16=5, codePoints=3, utf8Bytes=11, compactPayloadEstimate=10
Decomposed: utf16=6, codePoints=6, utf8Bytes=8, compactPayloadEstimate=12
raw equal: false
NFC equal: true
~~~

The **compactPayloadEstimate** column is computed by the program using the rule **one byte per UTF-16 unit when all units fall within Latin-1, otherwise two bytes per unit**. This is an **estimate of the payload alone** in JVMs that use Compact Strings, **not a measurement of String size on the heap**.

## 4. Compact Strings and Understanding Internal Memory Properly

In many **OpenJDK/HotSpot builds since Java 9**, String uses **Compact Strings**: content can reside in a **byte[]** array with one of two internal encodings.

**LATIN1:** all UTF-16 units have values at most U+00FF. The JVM can store one byte per unit.

**UTF16:** when any unit exceeds U+00FF, the JVM uses two bytes per unit in the string payload.

Estimated table for the **internal data array alone**:

| String | Candidate coder | Estimated payload bytes |
| --- | --- | ---: |
| ASCII | LATIN1 | 5 |
| café | LATIN1 | 4 |
| Việt | UTF16 | 8 |
| 🙂 | UTF16 | 4 |
| 👩‍💻 | UTF16 | 10 |
| Decomposed Việt | UTF16 | 12 |

The **café** case is very helpful for catching misconceptions. It has **5 UTF-8 bytes** while its LATIN1 payload is only around **4 bytes**. Conversely, **Việt** has **6 UTF-8 bytes** while its UTF16 payload can be **8 bytes**. Thus, **wire/transmission encoding** and **heap storage layout** cannot be equated.

Limitations that must be explicitly stated in reports:

1. **Compact Strings is an implementation detail**, not a Java specification guarantee. Do not infer byte counts this way for every JVM or when Compact Strings is disabled.
2. The **String object** and **byte[] object** also have object headers, references, alignment, and metadata. Total shallow size exceeds the payload.
3. Multiple variables may point to the same String, literals may be interned, and the JVM may apply data sharing or String deduplication. Do not multiply payload blindly by variable count.
4. A single character outside Latin-1 can force the **entire payload** to use UTF16, not just that character.
5. Shallow and retained sizes depend on the object graph. Bytes freshly allocated by an operation also differ from memory still retained after garbage collection.
6. The JVM may change representation or string concatenation optimizations across versions, flags, and compiler/JIT behavior.

**Example:** in a mixed string of thousands of ASCII letters with one **ệ**, the estimated String payload with Compact Strings under the simple model is **two bytes per UTF-16 unit**. That does not mean the entire application doubles in memory, because other objects and data sharing still exist.

## 5. Special Notes for Emojis and Grapheme Clusters

When iterating over a String by **char**, a non-BMP emoji is split into two surrogates:

~~~java
String smile = "\uD83D\uDE42";
System.out.println(smile.length()); // 2
System.out.println(smile.codePointCount(0, smile.length())); // 1
System.out.println(Character.isHighSurrogate(smile.charAt(0))); // true
System.out.println(Integer.toHexString(smile.codePointAt(0))); // 1f642
~~~

This is an illustrative snippet to place inside a Java method when running; the complete program is in section 3.

A **common mistake** is using **substring(0, 1)** to get “the first emoji”. For **🙂**, this takes only half of a surrogate pair and can produce invalid Unicode data. When slicing by code points, use **offsetByCodePoints** or code-point APIs instead of arbitrary char indices.

However, **code points still do not necessarily match visible characters**. A ZWJ emoji sequence like **👩‍💻** has three code points even though it may render as one glyph. Vietnamese combining marks can also combine with a base letter to form a single grapheme cluster. When a UI enforces a “20 visible characters” limit, you need a Unicode-compliant **grapheme** segmentation rule.

Do not assume **BreakIterator.getCharacterInstance** on every JDK version handles all modern ZWJ emoji sequences accurately according to Unicode UAX #29. When an application must slice or position a cursor by graphemes, test on realistic data and consider an up-to-date grapheme segmentation library, such as ICU4J where appropriate.

## 6. Unicode Normalization Affects Both Results and Memory

String.equals compares stored code units; two strings with identical visual appearance but different Unicode forms are usually **not equal** under equals.

~~~java
String a = "Vi\u1EC7t";       // Precomposed form of Việt
String b = "Vie\u0323\u0302t"; // e with combining marks

System.out.println(a.equals(b)); // false
System.out.println(
        java.text.Normalizer.normalize(
                b, java.text.Normalizer.Form.NFC)
                .equals(a)); // true
~~~

This is also a snippet to place inside a method. Form a is **4 UTF-16 units** and **6 UTF-8 bytes**. Form b is **6 units** and **8 UTF-8 bytes**. After NFC, form b can become the shorter precomposed form.

If a benchmark includes Vietnamese data, specify clearly **whether inputs are already NFC/NFD-normalized**. If the real application must normalize before every operation, measure the normalization cost separately or measure the entire pipeline rather than omitting that cost while claiming end-to-end performance.

NFC does not automatically make all visually similar strings equal: letter variants, locale rules, and diacritics must be handled according to business rules. Nor should normalization be mixed with payload-byte comparisons without disclosing the transformation step.

## 7. Memory Evaluation: What to Measure and With Which Tools?

Separate three questions:

**Question A: How many bytes is the UTF-8 payload?** Use **getBytes(StandardCharsets.UTF_8).length** as in the section 3 program. This is a reproducible figure for encoded data, very useful for request or file size limits.

**Question B: How many bytes does a String occupy on the heap?** Use an object-layout inspection tool such as **JOL (Java Object Layout)** or a heap dump/profiler, inspecting both the String and its internal byte array. Distinguish **shallow size** (size of the object itself) from **retained size** (memory kept alive solely through that object).

**Question C: How much memory does each operation allocate?** Use an allocation profiler or **B/op** counters in a reliable microbenchmark. For example, creating new strings, UTF-8 encoding, and normalizing can allocate different numbers of temporary objects even when the output has the same byte count.

Do not take the difference between **Runtime.totalMemory() - Runtime.freeMemory()** before and after a short operation as “the exact size of a String”. That number also depends on GC, allocation buffers, class loading, the string pool, JIT, and background objects.

When measuring heap across ASCII/Vietnamese/emoji groups:

1. Fix the **JDK version, HotSpot/JVM, architecture, heap settings**, and Compact Strings setting; record actual parameters.
2. Create the same number of elements under each comparison policy: equal UTF-16 units, equal code points, equal UTF-8 bytes, or equal graphemes.
3. Construct real objects at runtime and retain live references in a collection during measurement; avoid measuring interned or constant-folded literals.
4. Pick the right metric: shallow bytes, retained bytes, allocation rate, or encoded byte size; state explicitly whether collection overhead is included.
5. Repeat measurements and inspect across sample sizes; check sharing, deduplication, and object alignment before concluding.

**One payload byte is not one heap byte.** Especially for millions of very short strings, object and reference overhead can dominate total memory far more than the difference between one and two payload bytes per code unit.

## 8. CPU Performance Evaluation: Designing a Fair Comparison

Specify exactly which operation is being measured:

| Operation | Performance implication |
| --- | --- |
| **length()** | Returns UTF-16 code unit count; does not count graphemes |
| **charAt(i)** | Accesses a UTF-16 unit; may return a surrogate |
| **codePointAt() / codePoints()** | Traverses Unicode code points; behaves differently from char traversal |
| **getBytes(UTF_8)** | Encodes UTF-8; typically allocates a byte array |
| **new String(bytes, UTF_8)** | Decodes UTF-8 into a String |
| **Normalizer.normalize(..., NFC)** | Normalizes Unicode; cost depends on input |
| **StringBuilder.append()** | Appends string segments into an expandable buffer |

There is no universal law that “ASCII is always faster than Vietnamese” or “emojis are always slower”. **length()** behaves very differently from **UTF-8 encoding**, and results also depend on data, JVM version, JIT, warm-up, and workload consistency.

### Fixing the Same Workload Basis

At minimum, run multiple experiment groups:

- **Equal UTF-16 code units:** appropriate when comparing operations tied to String.length or charAt.
- **Equal Unicode code points:** appropriate when operations traverse code points.
- **Equal UTF-8 bytes:** appropriate for payload-size constraints.
- **Equal grapheme clusters:** appropriate for UI operations on perceived characters, using a proper segmenter.

A string of 5 ZWJ emojis carries far more data than a string of 5 ASCII letters in bytes and code units; you cannot call that comparing the same “5 characters” without defining what a character means.

### Benchmarking Java Methodically

For microbenchmarks, use **JMH (Java Microbenchmark Harness)** instead of single-shot System.nanoTime. A standard process requires:

1. Warming up the JVM/JIT and using multiple independent runs (**forks**).
2. Pre-building data in **@State** when measuring only the String operation; if measuring creation too, define a separate benchmark.
3. Consuming results to prevent **dead-code elimination** (e.g., JMH **Blackhole**).
4. Choosing proper units: **ns/op**, **ops/s**, and for allocations **B/op** when supported by the profiler.
5. Recording JDK, GC, heap, CPU, thread count, sizes, and string-type ratios.
6. Reporting mean along with spread/error bounds, and checking whether measurements scale linearly or exhibit anomalies.

For example, a benchmark encoding 1,000 UTF-16 units across the three content groups answers **encoding cost at equal unit counts**. Another benchmark fixing 4,096 UTF-8 bytes answers **encoding cost at equal payload size**. Both need not produce the same speed ranking, because they evaluate different workloads.

Beyond microbenchmarks, real web/API/file services must also be measured **end-to-end**: normalization, encode/decode, String handling, I/O reads/writes, and auxiliary steps. A few nanoseconds' difference in one API may be negligible when I/O dominates.

## 9. Production Application Examples

### 9.1. Byte-Based Request Limits

If an endpoint allows at most 1,024 UTF-8 bytes, do not check **text.length() <= 1024**. With Vietnamese and emojis, a single code point can take multiple UTF-8 bytes.

~~~java
int utf8Bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length;
boolean withinLimit = utf8Bytes <= maxUtf8Bytes;
~~~

This snippet is illustrative; **text** and **maxUtf8Bytes** must be declared in the appropriate scope. If strings are very large or streaming is required, an encoder can be used to avoid allocating an entire byte[] just to measure size.

### 9.2. Truncating Content by Visible Character Limit

If the UI limits input to 20 “user-perceived characters”, substringing at **20 chars** can split a surrogate pair; slicing at **20 code points** can still split a ZWJ emoji sequence or combining marks. Determine an appropriate grapheme algorithm before truncating.

### 9.3. Generating Keys and Comparing Vietnamese Text

If one data source uses precomposed characters and another uses combining marks, **String.equals** and hashCode can differ. Normalize consistently to one canonical form **both on write and on lookup** before inserting into HashMap/HashSet to avoid keys that “look identical to the eye yet do not match”.

### 9.4. Joining Many String Segments

When joining very many segments in a loop, you can use **StringBuilder**:

~~~java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
~~~

This snippet is illustrative with an existing collection/array **parts**. Do not assert StringBuilder is always faster than string `+` concatenation: the compiler and JIT have their own optimizations, so compare on the actual workload.

## 10. Common Mistakes

| Mistake or misconception | Consequence | Fix |
| --- | --- | --- |
| Using **length()** as network byte count | Wrong byte limit for Unicode | Measure UTF-8 bytes directly |
| Treating one emoji = one char | Splits surrogate pairs | Traverse code points; segment graphemes when needed |
| Treating one code point = one visible character | ZWJ emojis and combining marks are miscounted | Use a proper grapheme algorithm |
| Assuming every Vietnamese character = two UTF-8 bytes | Wrong for different accents and code points | Measure actual code points |
| Assuming **café** must use UTF16 payload | é belongs to Latin-1 | Distinguish ASCII from Latin-1 |
| Treating Compact String payload as UTF-8 bytes | Confuses two encoding mechanisms | Separate internal bytes from serialized bytes |
| Treating payload estimate as heap object size | Ignores header, byte[], and sharing | Use JOL / profiler / heap dump |
| Single-run **nanoTime** benchmark | JIT/GC noise and dead-code elimination | Use JMH with warm-up, forks, Blackhole |
| Ignoring NFC/NFD when comparing | Visually identical Vietnamese strings fail equals | Normalize consistently per business rules |
| Comparing short ASCII against longer emoji directly | Unfair workload | Fix the comparison criterion |

## 11. Reproducible Evaluation Report Template

A reliable technical report should include:

**Data:** the six groups (ASCII / Latin-1 / precomposed Vietnamese / decomposed Vietnamese / single emoji / ZWJ emoji); element counts, group proportions, normalization, and sample generation method.

**Encoding:** for each group, a table of **UTF-16 units**, **code points**, and **UTF-8 bytes** as in section 2. If measuring graphemes, specify the segmenter, version, and Unicode rules.

**JVM:** Java 17 or 21 or another version, HotSpot or another JVM, Compact Strings enabled/disabled, heap/GC flags, CPU, and runtime environment.

**Memory:** state explicitly whether measuring **encoded bytes**, **estimated internal payload**, **shallow size**, **retained size**, or **allocation/op**; never lump them together as “String size”.

**Performance:** record the operation, shared workload unit, warm-up/forks, results with units, variance, and full-pipeline runtime if relevant.

**Conclusion:** draw findings **under the measured conditions**, reproducible and without overgeneralizing into an invariant property of every JVM.

## 12. Self-Check Questions

**1. Why does "café" use 5 UTF-8 bytes yet need only 4 bytes for a Compact String payload?**

Because **é U+00E9** encodes in UTF-8 using two bytes yet still falls inside the Latin-1 range to fit in one byte under Compact Strings. The two numbers belong to **two different encodings**.

**2. Why does "Việt" have length 4, codePointCount 4, yet 6 UTF-8 bytes?**

Because **ệ** is a single BMP code point that requires three UTF-8 bytes; the remaining three characters require one byte each.

**3. The string "🙂" has length 2; does that mean two emojis?**

No. It consists of one non-BMP code point and two UTF-16 code units.

**4. If the emoji "👩‍💻" has three code points, do users always see three symbols?**

No. ZWJ can join the parts into a single glyph; visual rendering depends on the environment. Code points differ from graphemes.

**5. Can we conclude "emojis use double heap" from the two payload tables?**

No. You must fix sample size, content, JVM mechanism, and measure object overhead/sharing as well. The payload table does not measure actual heap.

**6. When comparing speed across three string types, which measurement conditions must be fixed?**

Fix the operation type together with the appropriate **workload unit** (UTF-16 units, code points, graphemes, or UTF-8 bytes), while also controlling JIT, warm-up, allocations, and machine environment.

**Takeaway:** multilingual String performance is meaningful only when distinguishing **UTF-16 length**, **Unicode code points/graphemes**, **UTF-8 bytes**, **internal payload**, and **actual heap**. Valid conclusions are tied to **well-defined data and measurements**.
