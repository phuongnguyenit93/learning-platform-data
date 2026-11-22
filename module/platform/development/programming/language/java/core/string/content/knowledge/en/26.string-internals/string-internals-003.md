# Object Cost, Backing Arrays, and Temporary Strings in Java String

## 1. Lesson objectives

When looking at a `String` variable, we usually think of the sequence of characters it displays. At runtime, however, a string also involves a **Java object**, a **backing content storage area**, metadata, and overhead incurred during concatenation, slicing, formatting, or conversion. Many programs only run into trouble when strings are created in huge numbers or manipulated inside hot loops.

This article focuses on three practical questions:

1. How does a `String` occupy memory across its **object** and its **character data**?
2. Why can different modern JDK versions hold the same number of characters while using different amounts of memory, and where is the boundary between **API guarantees** and **implementation details**?
3. Which operations create **temporary strings**, when do they impact GC, and how do you measure and optimize them verifiably?

The examples target **Java 17+**, with clear notes whenever discussing how HotSpot/OpenJDK stores `String`. Do not treat a fixed byte count as "the size of every String" because JVM flags, architecture, alignment, and JDK version can all change the result.

## 2. Distinguishing the reference variable, the String object, and internal data

Consider this code:

```java
String name = "Java";
```

There are three distinct concepts:

- **The variable `name`**: holds a reference to an object, rather than directly containing all four characters like an inline character array inside the variable.
- **The `String` object**: a normal heap object in Java's object model, carrying an object header and the internal fields needed to manage the string.
- **The string content**: the encoded character/code-unit data, which may be stored in an internal array or another structure depending on the implementation.

In modern OpenJDK/HotSpot, a `String`'s content data usually lives in a separate `byte[]` array. Consequently, the total cost can include both the `String` object and its backing array object; however, **the `String` API specification does not guarantee a specific field layout or exact byte count**.

Several distinctions must be kept separate:
- `name.length()` returns the **number of UTF-16 code units**, not memory bytes.
- The number of Unicode code points can differ from `length()`; for example, an emoji outside the BMP uses two UTF-16 code units.
- `name.getBytes(StandardCharsets.UTF_8).length` returns the byte count **of a newly created UTF-8 representation**, not the in-memory size of the `String`.
- Heap memory measurements also include object overhead, alignment, and sometimes related buffers/objects that may be shared.

Calling `length()` alone does not let you reliably multiply that value by 2 to determine the bytes allocated for a string.

## 3. From storage structure to object footprint

In many OpenJDK builds prior to Java 9, `String` held its content in a `char[]` array. With **Compact Strings** (JEP 254) starting in Java 9, common OpenJDK/HotSpot builds can store a `byte[]` along with a `coder`: the data portion takes about `n` bytes when all code units belong to Latin-1, or about `2n` bytes when UTF16 form is needed, where `n = text.length()`.

The key point when analyzing the heap is that **the backing array and the `String` object each have their own overhead**. On a specific JVM, the footprint also depends on object/array headers, references, alignment, buffer sharing, and whether multiple objects hold the same data. Thus, `n` or `2n` only describes the *content portion* under one implementation strategy; it is **not the total heap cost**.

```text
String reference → String object → backing data (e.g., byte[])
                       |                     |
                  header/fields         array header + data
```

To study the exact rules for choosing LATIN1/UTF16 and how they differ from off-heap/wire UTF-8, see the **Compact Strings** article. This article builds on that structure to cover `shallow size`, `retained size`, allocation rate, and GC pressure—the metrics that directly affect operations.

## 4. Shallow size, retained size, and heap dumps

Three terms commonly used when analyzing Java memory:

| Term | Meaning | For String |
| --- | --- | --- |
| Shallow size | Memory size of **the object itself** | Usually counts only the `String` object and its header/fields, excluding referenced arrays |
| Retained size | Memory that would be freed if the object became unreachable, based on reference ownership | May include a backing array exclusively held by the `String`, but must not double-count shared objects |
| Allocation rate | Rate at which the JVM creates new objects/bytes over time | Reveals the impact of intermediate strings even when they are very short-lived |

For instance, a new `String` created only to build a log line and immediately discarded may not increase **live heap** over the long term, yet still drives up **allocation rate**. Conversely, a cache holding millions of small strings long-term can increase retained heap, lengthen GC pauses, or exhaust memory.

Size measurements also depend on:
- JVM vendor, bitness, Compressed Oops (ordinary object pointers), and compressed class pointers.
- Object and header alignment.
- The internal storage format in a specific JDK version.
- Whether strings share the same reference, are distinct objects with identical content, or share backing data.
- The GC and runtime optimizations.

**Do not add the shallow size of a `String` plus the entire shared array along every reference path** if multiple objects share the same backing data: that leads to double counting.

## 5. Immutable strings: why operations can create new objects

`String` is immutable: once created, an object's character sequence cannot be modified by ordinary `String` methods. Therefore, operations that **change the content** typically return a new `String` object, such as when the content genuinely needs alteration.

```java
String value = "Java";
String result = value.concat(" 17");

System.out.println(value);  // Java
System.out.println(result); // Java 17
```

Methods like `replace`, `toUpperCase`, `substring`, `strip`, or `repeat` can produce a new string representation when the result differs from the source. However, **never assert that every call always allocates a new object**: cases requiring no change can return the original string itself, and the JIT can eliminate intermediate allocations when provably safe.

For example:

```java
String source = "abcdef";
String cut = source.substring(1, 4); // "bcd"
```

In modern OpenJDK, `substring` typically needs a new content representation for the sliced portion. Earlier JDK history included a mechanism that shared the backing array between a substring and its parent string; do not apply that old rule of thumb to Java 17. In application code, rely on the **API contract for the returned content**, not on internal fields or object identity expectations.

Even when an operation creates a temporary string, the GC reclaims it once it is no longer reachable; performance impact depends on **creation frequency**, size, lifetime, and JVM optimizations.

## 6. Pooling, string duplicates, and object counts

Two literals with the same content share the canonical reference, whereas `new String(existing)` creates a separate `String` object, even if character data may be shared depending on the implementation:

```java
String canonical = "Java";
String sameLiteral = "Java";
String fresh = new String("Java");

System.out.println(canonical == sameLiteral); // true
System.out.println(canonical == fresh);       // false
System.out.println(canonical.equals(fresh));  // true
```

In terms of **footprint**, separate the count of **`String` objects** from the count of **backing content arrays**. `intern()` returns the canonical object; *String deduplication* in certain GCs can share backing data among objects that remain distinct references. Both mechanisms carry their own costs, eligibility rules, and effects on data lifetime; do not intern every random ID or assume deduplication is always enabled.

The **Constant Pool and Constable/ConstantDesc** article explains the interning contract; the article on **JDK version differences** covers the history of interning and deduplication. When the goal is saving heap, measure retained memory, actual duplicate counts, and allocation rate instead of counting `new String` by eye.

## 7. Common sources of temporary strings

### 7.1. String concatenation with the + operator

```java
String id = "42";
String message = "order-" + id + "-ready";
```

At the language level, `+` produces the concatenated string result. However, **do not assume** this example creates exactly three intermediate `String` objects. Since Java 9, the compiler/runtime can use `invokedynamic`-based concatenation (JEP 280); JIT optimizations and constant folding can further reduce allocations.

An expression containing only constants:

```java
String label = "Java" + " " + "17";
```

can be **folded into a compile-time constant**. Therefore, benchmarking constant string literals does not represent loops concatenating dynamic data.

### 7.2. Iterative accumulation

Be careful with the following pattern when `part` varies across iterations:

```java
String output = "";
for (String part : parts) {
    output += part;
}
```

Semantically, each iteration must produce a new concatenated result because `String` is immutable. The runtime may optimize part of this, yet this accumulation pattern often increases repeated content copying, especially as the resulting string grows.

A more intentional approach:

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String output = builder.toString();
```

`StringBuilder` maintains mutable state in a buffer and grows its capacity as needed; `append` does not require creating an intermediate immutable `String` on every iteration. Keep in mind that `StringBuilder` itself and its buffer **are also objects with memory cost**, and `toString()` produces the immutable result.

### 7.3. Conversion and formatting

Operations such as:

```java
String a = String.valueOf(12345);
String b = String.format(java.util.Locale.US, "%.2f", 12.5);
String c = "prefix" + java.util.UUID.randomUUID();
```

can allocate strings, helper objects, or internal buffers. `String.format` generally involves richer formatting logic, appropriate when you need width/precision/locale control; do not replace it with raw concatenation if doing so breaks formatting requirements solely to reduce allocations.

For high call volumes on a hot path, measure the difference between `StringBuilder`, `+` concatenation, and formatters **on real data and your target environment**, rather than guessing from syntax alone.

### 7.4. split, replace, substring, strip, and streams

Pipelines can create additional intermediate objects or arrays:

```java
String input = " red , blue , green ";
String[] tokens = input.split(",");
String first = tokens[0].strip();
String upper = first.toUpperCase(java.util.Locale.ROOT);
```

There can be the token array, individual token `String` objects, normalized `String` instances, and helper structures used by the algorithm. Actual counts depend on input, JDK version, and optimizations. Never assume `split` allocates only an array without component strings.

If you only need to locate a single delimiter and inspect a small slice of text, `indexOf`, `substring`, or an index-based parser can avoid some objects. However, hand-written parsers require edge-case testing and can hurt maintainability. Optimize only when a profiler proves this spot is significant.

## 8. StringBuilder: buffer and capacity management

`StringBuilder` is a mutable class for building strings incrementally. Two distinct concepts:

- `length()`: number of UTF-16 code units **currently in use**.
- `capacity()`: number of UTF-16 code units the buffer **can hold before needing expansion**, per the API specification.

```java
StringBuilder builder = new StringBuilder(128);
builder.append("id=").append(42);

System.out.println(builder.length()); // 5
System.out.println(builder.capacity() >= 128); // true
```

Pre-sizing capacity large enough can reduce buffer reallocations when the result size is predictable. However, `capacity()` is **not the number of heap bytes**. In OpenJDK Java 17, `StringBuilder`'s backing storage also uses character-representation optimizations, so multiplying capacity by 2 to infer bytes used is unreliable.

Over-preallocating can also backfire:

```java
StringBuilder huge = new StringBuilder(1_000_000);
huge.append("OK");
```

The snippet above requests a huge initial buffer even though the data is only two characters; if repeated often, memory usage and GC pressure can increase. Estimate capacity only when backed by data characteristics or profiling results.

After `toString()` returns the resulting string, `StringBuilder` can still be modified, while **the returned string remains unchanged**:

```java
StringBuilder builder = new StringBuilder("item=");
builder.append(42);
String snapshot = builder.toString();

builder.append("!");
System.out.println(snapshot); // item=42
System.out.println(builder);  // item=42!
```

`StringBuffer` serves a similar string-building purpose but has synchronized methods; do not choose it automatically for single-threaded code under the mistaken belief that its memory buffer is smaller.

## 9. Runnable Java 17+ example

Create `StringMemoryDemo.java` and save it as UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StringMemoryDemo {
    public static void main(String[] args) {
        String first = "alpha";
        String sameLiteral = "alpha";
        String freshObject = new String("alpha");

        System.out.println("same literal reference: "
                + (first == sameLiteral));
        System.out.println("fresh object reference: "
                + (first == freshObject));
        System.out.println("same text: "
                + first.equals(freshObject));

        String source = "abcdefgh";
        String part = source.substring(2, 5);
        System.out.println("substring: " + part);

        StringBuilder builder = new StringBuilder(32);
        builder.append("item=").append(42);
        String snapshot = builder.toString();
        builder.append("!");
        System.out.println("snapshot: " + snapshot);
        System.out.println("builder: " + builder);

        String ascii = "ABC";
        String emoji = new String(Character.toChars(0x1F600));
        System.out.println("ASCII length: " + ascii.length());
        System.out.println("emoji UTF-16 units: " + emoji.length());
        System.out.println("emoji code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("ASCII UTF-8 bytes: "
                + ascii.getBytes(StandardCharsets.UTF_8).length);

        List<String> parts = List.of("A", "B", "C");
        String joined = String.join("-", parts);
        System.out.println("joined: " + joined);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringMemoryDemo.java
java StringMemoryDemo
```

Expected stdout:

```text
same literal reference: true
fresh object reference: false
same text: true
substring: cde
snapshot: item=42
builder: item=42!
ASCII length: 3
emoji UTF-16 units: 2
emoji code points: 1
ASCII UTF-8 bytes: 3
joined: A-B-C
```

This example **verifies Java semantics**, not direct byte counts of each `String`. The expression `getBytes(UTF_8)` creates a UTF-8 representation to count output size; do not use it as a way to inspect internal arrays. Observing that `new String("alpha")` yields a different reference is guaranteed by the API, but do not deduce from it that the same number of underlying character-data bytes had to be duplicated.

## 10. Reducing string and temporary object counts

### 10.1. Choosing the right concatenation tool

| Situation | Usually appropriate approach | Notes |
| --- | --- | --- |
| Combining a few fields in one expression | `"id=" + id + ", status=" + status` | Readable syntax; modern JDKs optimize expression concatenation |
| Accumulating many parts in a loop | `StringBuilder` + `append` | Maintains a growing buffer, avoiding an immutable result every iteration |
| Joining a collection with a delimiter | `String.join(delimiter, values)` | Avoids manual leading/trailing delimiter handling |
| Joining strings in a Stream | `Collectors.joining(delimiter)` | Clean when you already have a Stream pipeline |
| Alignment, decimal precision, locale | `String.format`, `Formatter` | Choose for formatting correctness; measure if called very frequently |
| Scanning/parsing small slices | `indexOf` and index math if appropriate | Can reduce temporary arrays/tokens; trades off code complexity |

Often the best optimization is **avoiding unnecessary work**: do not repeatedly format a message nobody reads, do not call `split` when you only need a prefix check, and do not recreate the same converted string on every iteration if the value does not actually change.

### 10.2. Avoid building output when unused

Example of conditional logging:

```java
// Illustrates the conditional structure only; logEnabled/log are application APIs.
if (logEnabled) {
    String message = "Total=" + total + ", code=" + code;
    log(message);
}
```

By checking the condition first, we avoid constructing the message in the unused branch. With logging frameworks, use the placeholder/lazy logging features they provide where appropriate; calling `String.format` before passing to a logger can still do the formatting work even when logging is disabled.

### 10.3. Reusing data does not mean interning everything

If the same fixed set of keywords/labels appears very frequently, reusing objects can help. However, calling `intern()` on every ID, URL, or random value with low repetition adds management overhead. When caching is needed, define a clear lifetime and size limit; otherwise, short-term allocation savings can turn into long-term retained heap growth.

### 10.4. Bounded StringBuilder reuse

You can reuse a `StringBuilder` within a controlled processing flow by calling `setLength(0)` to clear it. However, **a large capacity stays allocated** after resetting, so one unusually large request can keep an oversized buffer pinned for too long. Moreover, `StringBuilder` is not thread-safe; never share a mutable builder across threads without proper synchronization. Avoid keeping gigantic builders in `ThreadLocal` or unbounded caches.

## 11. Measure instead of guessing object counts

### 11.1. Questions a profiler should answer

When noticing heavy GC activity, latency spikes, or high heap usage, look for:
- Which object types are **allocated most frequently**, especially `String`, `byte[]`, and related arrays?
- Which call paths create them? Is it loop concatenation, formatting, parsing, or conversion?
- Is it a high **allocation rate** of short-lived objects, or high **retained heap** from caches and long-lived references?
- Are many strings with identical content being retained? Are they truly causing a measurable impact on the application?
- After the change, do throughput, latency, allocation counts, and GC improve on representative data?

Useful tools include **Java Flight Recorder (JFR)**, **Java Mission Control (JMC)**, **VisualVM**, **Eclipse Memory Analyzer (MAT)**, and other environment-appropriate profilers. JFR provides allocation events/sampling; heap dumps show retained heap and reference retention paths. Results depend on recording configuration and tooling, so read metric definitions carefully.

### 11.2. Observing allocations with JFR

An example on a JDK that includes the `jfr` tooling:

```bash
java -XX:StartFlightRecording=filename=string-profile.jfr,settings=profile \
     -jar application.jar
```

This command is **illustrative** for a real application `application.jar`; the shell line continuation only works in shells supporting that escape syntax, whereas on Windows PowerShell you can write the command on a single line. You can inspect the `.jfr` file with JMC or an appropriate `jfr` CLI tool. Whether the recording captures the exact allocation events desired depends on the JFR profile and settings.

When you need reliable numbers for a small operation, avoid comparing `Runtime.totalMemory() - freeMemory()` before and after **a single call**. GC, JIT, escape analysis, framework allocations, and other threads make such measurements far too noisy.

### 11.3. Controlled benchmarking

For concatenation/formatting on a hot path, use **JMH** rather than hand-rolled timing loops. When benchmarking:
1. State a clear hypothesis: reduce allocations/op, increase throughput, or lower latency?
2. Use **controlled varying inputs** to prevent constant folding of the entire operation.
3. Warm up so the JVM optimizes before measurement, and run multiple iterations/forks appropriately.
4. Consume results to prevent dead-code elimination (JMH provides dedicated mechanisms).
5. Measure bytes allocated per operation if memory is the goal, and check application-level GC impact.

A microbenchmark can show that a specific operation is faster under a given setup, but that is not enough to claim every program should replace `+` with `StringBuilder`.

## 12. JVM flags and related optimizations

### Compact Strings

OpenJDK/HotSpot Java 17 normally enables Compact Strings by default. Some JVMs allow controlling it via implementation flags such as `-XX:-CompactStrings`; this is a **VM-dependent option**, not standard Java syntax or a default tuning recommendation. Changing flags can increase footprint or alter performance; use them only for controlled research or benchmarks.

### String deduplication

Some garbage collectors, notably G1 configurations, support **String deduplication** via JVM mechanisms/flags such as `-XX:+UseStringDeduplication` on supporting releases. The idea is to share the backing content array among `String` objects with identical contents while keeping **distinct `String` objects**. This optimization does not help every workload and adds scanning/hashing overhead; check your target GC/JDK and measure before enabling it.

### JIT and escape analysis

HotSpot can optimize certain string concatenations, inline methods, and even eliminate allocations that do not "escape" the observable scope of computation. Therefore:
- Seeing `new` or string creation in Java source does not mean the runtime necessarily allocates a separate heap object on every execution.
- Overly simple benchmarks can produce misleading numbers because the JIT constant-folded or eliminated the work.
- Do not change code solely based on object counts **inferred** from reading source code; combine a profiler with an understanding of the runtime.

JVM flags and algorithmic details vary across JDKs, GCs, and vendors; check your exact version before copying tuning guides.

## 13. Common misconceptions and mistakes

**1. "A String of N characters always takes 2N bytes."** False if used as a total footprint formula. `N = length()` is UTF-16 code units; there is object overhead and Compact Strings. In-heap data is also not identical to UTF-8 bytes.

**2. "Unicode/emoji always has length 1."** False for non-BMP code points: an emoji can occupy two UTF-16 code units, so `length()` can be 2. When counting code points, use `codePointCount(...)`, and remember a code point still does not necessarily match a visible *grapheme cluster*.

**3. "Every + operator always creates an extra intermediate String."** The expression evaluates to a string, but the compiler/JIT can constant-fold, fuse work, and reduce allocations. The real concern is cumulative loop concatenation and measured allocation rates.

**4. "StringBuilder uses no memory."** False. It is an object with a buffer; growing the buffer or over-preallocating both have costs. `toString()` produces an immutable result per the API.

**5. "Java 17 substring always keeps the entire huge parent array alive."** That was an observation from some older JDKs with a different layout; do not apply it to Java 17. Profile the actual JVM heap if you need to know about backing data sharing.

**6. "intern and String deduplication are the same thing."** `intern` canonicalizes the String reference, whereas deduplication (where supported) targets sharing the backing buffers of distinct String objects.

**7. "The heap has few live strings, so there cannot be a String problem."** A system can have low live heap alongside a high allocation rate, causing frequent GC and lower throughput.

**8. "getBytes(UTF_8).length is the String's size on the heap."** That is the byte length of an exported encoded representation, excluding object overhead and not reliably reflecting internal JVM storage.

**9. "Adding a cache always saves memory."** A cache can raise retained heap and extend object lifetimes. Cache only values reused often enough, with appropriate bounds.

**10. "Benchmarking concatenation on a constant is enough to pick an optimization."** Constant folding and JIT optimizations can make results unrepresentative; use JMH and profile the real application.

## 14. Practice exercises

### Exercise 1. Distinguishing length and UTF-8

```java
String ascii = "ABC";
String emoji = new String(Character.toChars(0x1F600));
```

Question: What are `ascii.length()`, `emoji.length()`, and `emoji.codePointCount(0, emoji.length())`? Can you multiply those numbers by 2 to deduce heap bytes?

**Answer:** **3**, **2**, and **1**, respectively. You cannot deduce heap bytes because these are content counts; heap usage also depends on storage representation, overhead, and the JVM.

### Exercise 2. Object identity

```java
String x = "value";
String y = "value";
String z = new String("value");
```

Question: What are `x == y`, `x == z`, and `x.equals(z)`?

**Answer:** `true`, `false`, `true`. Both literals refer to the same canonical string; `new String(...)` creates a distinct object with equal content.

### Exercise 3. Replacing a multi-part concatenation loop

Given a list `parts` of type `List<String>`, rewrite:

```java
String result = "";
for (String part : parts) {
    result += part;
}
```

into a string-building approach using a mutable buffer:

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
```

Explanation: the second version avoids requiring a new immutable `String` result on each iteration structurally; actual runtime cost should still be confirmed with a profiler.

### Exercise 4. Checking the cost of a pipeline

```java
String[] values = input.split(",");
String joined = String.join("|", values);
```

Question: Can you be sure this allocates strictly two objects (one array and one string)?

**Answer:** No. There can be token `String` objects, arrays, and other internal objects; actual allocations are also subject to JVM optimizations. Profile if this is on a hot path.

### Exercise 5. Choosing the right metric

A service creates millions of temporary strings per second, yet retained heap does not visibly grow. Should you inspect the **shallow size** of one `String`, or **allocation rate, GC activity, and call paths**?

**Answer:** Prioritize allocation rate, GC, and call paths to locate where short-lived objects are created. The shallow size of a single object does not reflect allocation pressure over time.

## 15. Key takeaways

- **`String` has multiple layers of cost:** the object, internal data, array overhead, alignment, and reference lifetime; `length()` is not heap size.
- **Compact Strings** in OpenJDK/HotSpot Java 9+ typically uses `byte[]` with Latin-1 or UTF-16 to reduce the data portion; that is an **implementation detail**.
- **Immutable strings:** operations creating new content can allocate new `String` objects and arrays; the compiler/JIT can optimize some of this away, so never count objects by syntax alone.
- **Literals/intern** and **string deduplication** are two distinct techniques with different effects on references and backing data.
- **Loop concatenation:** consider `StringBuilder`; joining a few values in one expression with `+` is usually clean and readable.
- **Target the right bottleneck:** distinguish live heap size from temporary object allocation rate; measure with appropriate profilers, JFR, heap dumps, and JMH.
- **Never optimize blindly:** VM flags, GC, memory, and runtime must be verified on real workloads.

References:
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [OpenJDK JEP 254 — Compact Strings](https://openjdk.org/jeps/254)
- [OpenJDK JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280)
- [OpenJDK JEP 192 — String Deduplication in G1](https://openjdk.org/jeps/192)
