# Compact Strings and the LATIN1 and UTF16 Representations in OpenJDK

Since Java 9, OpenJDK builds have used **Compact Strings** (JEP 254) to reduce the memory required to store the contents of many `String` objects. A string containing only code units within the Latin-1 range can be stored using **1 byte per code unit**; a string containing any code unit outside that range uses the **UTF16 representation, 2 bytes per code unit**. This is an **internal implementation detail** of OpenJDK/HotSpot and does not change the semantics of the `String` API.

This article explains why it was introduced, how OpenJDK chooses between `LATIN1` and `UTF16`, its impact on memory and speed, how to verify it yourself with Java 17+ examples, and common misconceptions when comparing Compact Strings to UTF-8 or `String.length()`.

## 1. Background: from `char[]` to `byte[]`

Before Java 9, common OpenJDK builds represented `String` contents using a `char[]` array. Each `char` is a 16-bit (2-byte) **UTF-16 code unit**, even when the string contains only ASCII such as `"Hello"`. When ASCII or Latin-1 strings make up a large share of data, most of the 16 bits per code unit go unused.

JEP 254 (implemented in JDK 9) switched the backing content to a `byte[]` array paired with **an internal encoding identifier field**, commonly called `coder`:

~~~text
                    String in OpenJDK since Java 9
                  ┌───────────────────────────────┐
                  │ value: byte[]                 │
                  │ coder: LATIN1 or UTF16        │
                  │ other internal metadata       │
                  └───────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              coder = LATIN1            coder = UTF16
             1 byte/code unit          2 bytes/code unit
             (eligible content)        (content outside Latin-1)
~~~

This is a **conceptual diagram**. The `byte[]` array is a separate object on the heap; beyond the character data itself, there are header overhead, memory alignment, and reference costs. The diagram cannot be used to calculate the exact size of the entire object.

**Version note:** this is an OpenJDK implementation mechanism starting in Java 9, not a mandatory requirement of the Java Language Specification. Another JVM or a future Java release may implement storage differently while adhering to the same `String` API.

## 2. Rules for choosing `LATIN1` or `UTF16`

In OpenJDK with Compact Strings enabled:

- **`LATIN1`:** every UTF-16 code unit in the string falls in the range `U+0000`–`U+00FF`. Each code unit can be represented in one byte. This range corresponds to ISO-8859-1/Latin-1, including ASCII and characters such as `é` (`U+00E9`) and `ñ` (`U+00F1`).
- **`UTF16`:** at least one code unit lies outside `U+00FF`; the entire content of the string is stored in the internal UTF-16 representation at two bytes per code unit. Examples include `€` (`U+20AC`), `ệ` (`U+1EC7`), Han characters, and emojis.
- For non-BMP characters such as `😀` (`U+1F600`), one Unicode code point requires a **surrogate pair** of two UTF-16 code units; the internal `UTF16` representation uses a total of four bytes for that pair.

The condition applies to the **entire string**. `"ABCé"` still qualifies for `LATIN1`, whereas `"ABC€"` forces `UTF16` for the whole string—not the first three characters in Latin-1 and the last character in UTF-16 within the same `String`.

### Quick comparison table

| Content | `String.length()` | Eligible for `LATIN1` with Compact Strings enabled? | Backing array content bytes in the corresponding format |
| --- | ---: | --- | ---: |
| `"Hello"` | 5 | Yes | 5 |
| `"café"` | 4 | Yes | 4 |
| `"Euro €"` | 6 | No, because `€` is greater than `U+00FF` | 12 |
| `"Việt"` | 4 | No, because `ệ` is `U+1EC7` | 8 |
| `"A😀B"` | 4 | No, because the emoji is a surrogate pair | 8 |

The last column **only shows the theoretical content byte count in the `value` array**, assuming the string is constructed in the format listed in the table. It excludes the size of the `String` object, the `byte[]` array object, headers, alignment, potential data sharing, or other JVM optimizations.

**Two important misconceptions:**

1. `LATIN1` does not mean ASCII-only: `é` still qualifies, even though UTF-8 for `é` uses 2 bytes.
2. `LATIN1` is the Unicode range `U+0000`–`U+00FF`, **not Windows-1252**. The curly apostrophe `’` is `U+2019`; even though Windows-1252 encodes it in one byte, OpenJDK Compact Strings still cannot store it in `LATIN1` form.

## 3. How do `byte[] value` and `coder` work?

In the `java.lang.String` source code of OpenJDK versions with Compact Strings, you can find equivalent internal members:

~~~java
private final byte[] value;
private final byte coder;
static final boolean COMPACT_STRINGS;
~~~

This is an **illustrative excerpt of internal field declarations**, not a standalone compilable Java program and not part of the public API.

- `value` holds the bytes representing the string's content.
- `coder` indicates whether `value` should be interpreted as `LATIN1` or `UTF16`. In the OpenJDK versions discussed, typical internal values are `LATIN1 = 0` and `UTF16 = 1`; application code should not depend on these internal constants.
- `COMPACT_STRINGS` is an internal flag that the JIT can use to optimize execution branches. When compaction is disabled at the VM level, the UTF16 execution path is used.

OpenJDK provides internal helper classes such as `StringLatin1` and `StringUTF16` to implement operations for each storage format. Many `String` operations have dedicated code paths or optimized intrinsics corresponding to `coder`. These classes reside in `java.lang`, but **they are not public APIs for applications to depend on**.

You can inspect the field names in the JDK you are using with:

~~~bash
javap -private java.lang.String
~~~

In OpenJDK builds with this layout, the declarations show `byte[] value`, `byte coder`, and `COMPACT_STRINGS`. The `javap` command is a class-structure inspection tool; it **does not determine the `coder` of a specific runtime `String` object**.

Do not write business logic using reflection on `String.value`/`String.coder`: `private` fields can change across JDKs, the Java Module System restricts deep access, and mutating internal contents breaks `String` immutability.

## 4. Runnable Java 17+ experiment: checking Latin-1 eligibility

The public API does not expose `coder` directly, but we can check whether **content is eligible** for Latin-1 storage. This is different from measuring the actual state of JVM memory.

Create the file `CompactStringsDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class CompactStringsDemo {
    public static void main(String[] args) {
        inspect("ASCII", "Cafe");
        inspect("Latin1", "caf\u00E9");
        inspect("Vietnamese", "Vi\u1EC7t");
        inspect("Euro", "Euro \u20AC");
        inspect("Emoji", "A\uD83D\uDE00B");
    }

    private static void inspect(String label, String text) {
        int utf16Units = text.length();
        int codePoints = text.codePointCount(0, text.length());
        int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;

        // chars() iterates over each UTF-16 code unit, not code points.
        boolean latin1Eligible = text.chars()
                .allMatch(codeUnit -> codeUnit <= 0xFF);

        System.out.printf(
                "%s: units=%d, codePoints=%d, utf8Bytes=%d, latin1Eligible=%s%n",
                label, utf16Units, codePoints, utf8Bytes, latin1Eligible
        );
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CompactStringsDemo.java
java CompactStringsDemo
~~~

Output:

~~~text
ASCII: units=4, codePoints=4, utf8Bytes=4, latin1Eligible=true
Latin1: units=4, codePoints=4, utf8Bytes=5, latin1Eligible=true
Vietnamese: units=4, codePoints=4, utf8Bytes=6, latin1Eligible=false
Euro: units=6, codePoints=6, utf8Bytes=8, latin1Eligible=false
Emoji: units=4, codePoints=3, utf8Bytes=6, latin1Eligible=false
~~~

Explanation:

- `"Cafe"` consists of 4 ASCII characters: it is Latin-1 eligible and also requires exactly 4 UTF-8 bytes.
- `"café"` consists of 4 UTF-16 code units, none exceeding `U+00FF`, so it is Latin-1 eligible; however, UTF-8 for `é` takes **2 bytes**, so the entire string takes 5 UTF-8 bytes.
- `"Việt"` has `ệ` (`U+1EC7`), which lies outside Latin-1. `length()` is 4, while UTF-8 encoding requires 6 bytes.
- `"Euro €"` contains the euro sign `U+20AC`, so it is not Latin-1 eligible even though the leading characters are ASCII.
- `"A😀B"` contains 3 code points but 4 UTF-16 code units: the emoji occupies 2 code units and 4 UTF-8 bytes.

`text.chars()` returns an `IntStream` of **UTF-16 code units**, so checking `<= 0xFF` here accurately expresses the Latin-1 compaction condition. If you used `codePoints()`, you would be iterating by code point; for valid strings you could still deduce the condition, but you must understand the difference when dealing with unpaired surrogates.

The `latin1Eligible` variable only answers "can this content fit in Latin-1?". If run with Compact Strings **disabled**, the expression is still `true` for `"café"`, while the VM will use the internal `UTF16` representation. Do not treat this as a way to inspect the exact `String.coder` value.

## 5. Testing the `-XX:-CompactStrings` JVM option

On HotSpot/OpenJDK builds supporting this flag, Compact Strings is enabled by default starting in Java 9. You can run the program above in both modes:

~~~bash
java CompactStringsDemo
java -XX:-CompactStrings CompactStringsDemo
~~~

In the second run, HotSpot disables compaction and uses the internal `UTF16` representation for strings. **Both runs must still print the exact same output** as shown above: `String.length()`, `codePointCount()`, UTF-8 bytes, and `latin1Eligible` all come from the characters/Unicode data, not the internal `coder` state.

This demonstrates that Compact Strings is designed to **preserve public API behavior**. You can use the disable flag to study memory/performance effects, but you should not disable it by default without benchmarks or regression evidence on real workloads.

Note on VM flag syntax: `-XX:-CompactStrings` must appear **before the class name** when invoking `java`, because it is a JVM option, not an argument passed to `main(String[] args)`.

## 6. Distinguishing three concepts: internal storage, UTF-16, and UTF-8

This is a common point of confusion when learning about Compact Strings.

| Question | Appropriate mechanism/API |
| --- | --- |
| How many code units are in the `String`? | `text.length()`: always counts UTF-16 code units per the API contract |
| How many Unicode code points? | `text.codePointCount(0, text.length())` |
| How many UTF-8 bytes when exporting the string? | `text.getBytes(StandardCharsets.UTF_8).length` |
| Can OpenJDK store this string's content in Latin-1 form? | Every UTF-16 code unit is `<= U+00FF`, with Compact Strings enabled |
| What is the actual heap size? | Measure on the specific VM using a heap profiler/layout tool, including overhead and GC interactions |

**Internal `LATIN1` does not mean wire protocols use ISO-8859-1.** For instance, a Java `String` holding `"café"` may occupy 4 bytes in its internal `value` array, yet:

~~~java
String text = "caf\u00E9";
int utf8Size = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8
).length; // 5
~~~

The snippet above illustrates a Java expression inside a method; the output in the UTF-8 protocol is still **5 bytes**. Conversely, calling `getBytes(StandardCharsets.ISO_8859_1)` is a **request to encode external data** to ISO-8859-1, not an action that "extracts the internal `value` array" of the `String`.

**Internal `UTF16` does not mean external data must use UTF-16.** `"A😀B"` may be in `UTF16` form on the heap, but when sent in an HTTP body or written to a file as UTF-8, the output is still UTF-8 according to the specified charset. Never infer UTF-8 size directly from `coder` or `length()`.

## 7. Real-world memory impact

### Where are the savings?

When a string has `n` UTF-16 code units and fits in Latin-1:

- The `LATIN1` format needs approximately `n` bytes for the **character data portion**.
- The `UTF16` format needs approximately `2n` bytes for the **character data portion**.
- For the content portion alone, Latin-1 data uses about **half** the space of a two-byte-per-code-unit UTF-16 representation.

For example, a 1,000-character ASCII string can use roughly 1,000 bytes for its content instead of roughly 2,000 bytes. This is **not** a claim that the entire `String` object or the application's total heap will shrink by 50%. Total memory also depends on headers, alignment, arrays, the `coder` field, references, the String pool, GC, deduplication, and other components.

### When do the benefits diminish?

A string with a single non-Latin-1 character, such as `"report-2026-€"`, must use the `UTF16` representation for the entire string in this Compact Strings model. The proportion of such strings, string lengths, object lifetimes, and the amount of string reuse all affect the overall benefit.

For multilingual applications, **do not conclude that "Vietnamese always uses 2 bytes per character."** Some Vietnamese characters like `ê` (`U+00EA`) belong to Latin-1, while many like `ệ` (`U+1EC7`) fall outside it. The coder is chosen on a per-string basis, and emojis also involve surrogate pairs. Therefore, you should analyze real data.

### Does processing speed always increase?

There is no guarantee that every operation is faster. Compact Strings can reduce memory bandwidth and relieve cache/GC pressure when most strings fit in Latin-1. At the same time, it introduces separate code paths/branches or conversions between representations; HotSpot uses intrinsics and JIT optimizations to reduce overhead for many operations. Results depend on the operation and workload.

To evaluate properly:

1. Keep the test application/data identical; compare the default against `-XX:-CompactStrings` on the **same JDK version and machine configuration**.
2. Measure allocation rate, live heap, GC, throughput, and latency representative of production.
3. Warm up the JVM, use an appropriate benchmarking tool (such as JMH for microbenchmarks), and avoid timing a single uncontrolled loop.
4. Do not deduce performance gains solely from the `n` vs `2n` formula or from an example of a few short strings.

## 8. Why does `String.length()` stay unchanged?

Under the Java API, `length()` always returns the number of **UTF-16 code units** in the string. OpenJDK may internally store Latin-1 at one byte per code unit, yet Java still must return the same `length()` as before JDK 9.

Example:

~~~java
String latin1 = "caf\u00E9";
String emoji = "A\uD83D\uDE00B";

System.out.println(latin1.length()); // 4
System.out.println(emoji.length());  // 4
System.out.println(emoji.codePointCount(0, emoji.length())); // 3
~~~

This is an illustrative snippet inside a method, not a standalone class; the values are `4`, `4`, and `3`. Compact Strings mode does not change those results.

For non-BMP characters, Java still represents a code point as a **surrogate pair at the UTF-16 API layer**. Even though the underlying storage mechanism changed, `charAt`, `substring`, `codePointAt`, and `codePointCount` must preserve the API contract. Keep in mind that `substring` and `charAt` indices use positions of **UTF-16 code units**; you can slice in the middle of a surrogate pair if you choose inappropriate indices.

## 9. Behavior when creating and transforming strings

Operations such as creating strings from literals, concatenating, converting from `StringBuilder`, changing case, or taking substrings can produce **a different `String` object**. The internal representation of the resulting object can be chosen based on the **result's content**, independent of the input object's format.

A content-level example:

~~~java
String original = "ABC\u20AC";
String onlyAscii = original.substring(0, 3);

System.out.println(original); // ABC€
System.out.println(onlyAscii); // ABC
~~~

This is an illustrative snippet that can be placed in a method. With Compact Strings enabled, a new `String` containing only `"ABC"` is eligible for Latin-1 even though `original` contains `€`. However, **do not rely on details of which arrays an object shares/copies or the exact timing of coder selection**: those are implementation-version decisions. What matters is that APIs return the correct text.

`StringBuilder` and `StringBuffer` in OpenJDK versions supporting JEP 254 also have related internal content representation optimizations, though a builder's capacity management strategy is not identical to immutable `String`. Avoid assuming that `append` or `toString()` always copies, always shares arrays, or always has a fixed cost.

## 10. Common misconceptions

**Misconception 1 — "Java switched String to UTF-8 starting in Java 9."** False. Compact Strings uses **LATIN1 or UTF16** for internal storage, not UTF-8 as its two main coder formats.

**Misconception 2 — "Because the array is `byte[]`, `String.length()` counts bytes."** False. `length()` still counts UTF-16 code units, regardless of which internal storage format Java uses.

**Misconception 3 — "Every non-ASCII character uses UTF16."** False. `é`, `ñ`, and `ÿ` all lie within the Latin-1 range. Meanwhile, `€` and most Unicode characters above `U+00FF` require UTF16.

**Misconception 4 — "Only characters beyond Latin-1 take 2 bytes."** False at the level of **a single `String` object**: when one code unit does not fit in Latin-1, the entire string switches to UTF16 format.

**Misconception 5 — "You can read `coder` to optimize application logic."** This field is internal and subject to change. Do not use reflection/`Unsafe` to write logic that depends on `coder`; process strings through the public API.

**Misconception 6 — "Disabling Compact Strings makes a program output different text."** False for valid public API behavior. The flag affects representation and may impact memory/performance, not content or `length()` counting.

**Misconception 7 — "If a String is Latin-1 eligible, its UTF-8 data also has only one byte per character."** False: `"café"` has 4 code units and is Latin-1 eligible, yet requires 5 bytes when encoded as UTF-8.

**Misconception 8 — "Saving 50% of character data means saving 50% of the entire heap."** False. The total heap includes many objects and overhead; you must measure in practice.

## 11. Knowledge check

**Question 1.** Can `"ABC\u00E9"` use the `LATIN1` format? Why?

**Answer:** Yes, because all four UTF-16 code units lie within `U+0000`–`U+00FF`. In an environment with Compact Strings enabled, the content is eligible to be compacted to 4 bytes.

**Question 2.** Can `"ABC\u20AC"` store the first 3 characters in LATIN1 and the last character in UTF16 inside the same `String` object?

**Answer:** Not under OpenJDK's JEP 254 model: `coder` selects a single format for the entire object's content. Because `€` lies outside Latin-1, the UTF16 format is required.

**Question 3.** Run the same Java program with `-XX:-CompactStrings`. Does the value of `"A😀B".length()` change?

**Answer:** No. The value remains `4`, consisting of `A` (1), the emoji (2 UTF-16 code units), and `B` (1).

**Question 4.** A service sends UTF-8 over the network. Should it use the byte length of the internal `String.value` array as `Content-Length`?

**Answer:** No. You must use the byte count of the **final payload** being sent. Compact Strings is an internal storage detail; when exporting UTF-8, the string is encoded to UTF-8 independently of its internal coder.

**Question 5.** Why should you evaluate using heap profiling instead of using `text.length() * 1` or `* 2` to report how much RAM a `String` occupies?

**Answer:** Those formulas only approximate the **data portion** inside the backing array, ignoring object headers, array headers, alignment, references, reuse, and many other optimizations. Actual size also depends on JVM configuration.

## 12. Conclusion and how to apply it

Compact Strings is an OpenJDK storage optimization introduced in Java 9: `String` uses `byte[] value` along with `coder` to choose **LATIN1 when all code units fall in `U+0000`–`U+00FF`**, or **UTF16 when any code unit falls outside that range**. On many workloads dominated by Latin-1 strings, the character data portion can drop by nearly half compared to fixed UTF-16 storage. Still, this is an optimization beneath the API; in applications, continue using `String.length()`, code point APIs, and byte encoding with `StandardCharsets.UTF_8` according to each requirement's exact semantics.

When optimizing the heap, measure real data and applications and only consider `-XX:-CompactStrings` if measurements reveal a specific reason; when implementing file formats, HTTP, or databases, rely on **the charset and output format**, never on the internal coder.

References:

- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254).
- [Oracle JDK 21 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).
- [OpenJDK: `java.lang.String` source code](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/String.java) and [`StringUTF16`](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/StringUTF16.java).
