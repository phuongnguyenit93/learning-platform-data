# Avoiding Intermediate Strings When Processing Step by Step in Java

## Objective

When normalizing data, building messages, generating CSV, joining multiple fields, or transforming text in a loop, a Java program can create many `String` objects that are used only very briefly. This lesson helps you identify when intermediate strings increase memory allocation, choose techniques to reduce string copying/concatenation, and preserve the semantics of the transformation. The goal is to reduce unnecessary work in code that genuinely needs optimization, not to eliminate every temporary `String` at all costs.

## 1. Why Do Intermediate Strings Occur?

`String` in Java is **immutable**: once created, the contents of a `String` object are not modified directly. Methods such as `replace(...)`, `toUpperCase(...)`, `substring(...)`, or string concatenation can return a new string to represent the result. Depending on the case, some methods are allowed to return the existing object if the content is unchanged; therefore, you should not claim that “every call is guaranteed to create a new `String`”.

For example:

```java
String source = "  Java-Core  ";
String a = source.trim();
String b = a.replace('-', ' ');
String c = b.toUpperCase(java.util.Locale.ROOT);
System.out.println(c);
```

Output:

```text
JAVA CORE
```

`a` and `b` are intermediate values serving the next step. The code above is readable, functionally correct, and can be a completely good choice for small data or infrequent execution. However, if this processing runs millions of times or on very long text, the copies and temporary objects can cause extra **allocation**, memory traffic, and garbage collector (GC) pressure. They may also have to scan the content multiple times.

Distinguish three costs:
- **Allocation:** creating `String` objects or auxiliary buffers, especially when repeated very many times.
- **Copying/traversal:** moving content from input to new results or re-inspecting each character across multiple stages.
- **Memory retention:** holding references to many temporary results or keeping buffers with excessively large capacity for a long time.

The JVM performs runtime optimizations, such as optimizing string concatenation or eliminating certain allocations in suitable cases. Even so, you cannot rely on speculation that the JIT always eliminates every intermediate string. When performance matters, measure on the exact JDK version and workload.

## 2. Identifying Intermediate Strings in Loops

In a `result += part` loop, each immutable result can contain the entire preceding prefix again; if the string grows steadily, the total data that must be created under a sequential concatenation model can grow quadratically with the number of iterations. `StringBuilder` lets you accumulate in a single buffer and call `toString()` when finished. The lesson on repeated `+=` concatenation analyzed this cost formula; here, focus on identifying **temporary values created solely to be immediately copied into another result**.

Useful questions when reviewing a pipeline:

- Are you creating a formatted string with `prefix + value + suffix` only to pass it immediately to `builder.append(...)`? If so, you can append each component directly.
- Are you creating `text.substring(begin, end)` just to append that slice to a buffer? The `append(text, begin, end)` overload can avoid this temporary value.
- Do you genuinely need to keep a `String` after every step? If intermediate results only serve the next step, consider merging output-building operations; if Unicode transformations, normalization, or complex escaping are involved, standard semantics must still be preserved.

You cannot conclude something is faster solely from having fewer temporary variables. After ensuring identical output, measure allocations and time on representative data. The examples in the next sections focus directly on removing temporary strings when formatting or copying a slice.

## 3. Merging Multiple Output-Building Steps into One `StringBuilder`

Suppose a program needs to join parts formatted as `[value]`. The following approach builds a formatted string for each part before appending the result:

```java
StringBuilder out = new StringBuilder();
for (String value : values) {
    String formatted = "[" + value + "]";
    out.append(formatted);
}
```

You can append each part directly into the buffer:

```java
StringBuilder out = new StringBuilder();
for (String value : values) {
    out.append('[').append(value).append(']');
}
String result = out.toString();
```

Now, the intermediate `formatted` string is no longer needed. `append(char)` adds a character, and `append(String)` adds string content without creating a new combined string at the source-code level.

Complete example — save as `DirectAppendDemo.java`:

```java
public class DirectAppendDemo {
    public static void main(String[] args) {
        String[] values = {"A", "B", "C"};

        StringBuilder out = new StringBuilder();
        for (String value : values) {
            out.append('[').append(value).append(']');
        }

        System.out.println(out.toString());
    }
}
```

```bash
javac -encoding UTF-8 DirectAppendDemo.java
java DirectAppendDemo
```

```text
[A][B][C]
```

A similar approach fits building message bodies, command lines, conditional log formatting, simple templates, or text data export. A builder should have clear ownership and only produce an immutable result when a step genuinely needs one.

## 4. Avoiding `substring` When Only Copying a Slice into the Result

Suppose you have text containing a portion to extract within an index range. The following creates a temporary string to insert into the builder:

```java
String fragment = text.substring(begin, end);
builder.append(fragment);
```

If you only need to copy characters from `text`, use the overload:

```java
builder.append(text, begin, end);
```

`StringBuilder.append(CharSequence, int start, int end)` copies the content in the range **[start, end)** directly into the builder, avoiding the need to create a `String` object from `substring`. Indices are measured in **UTF-16 code units**, just like `String.length()` and `String.substring(...)`.

Standalone runnable example — save as `AppendRangeDemo.java`:

```java
public class AppendRangeDemo {
    public static void main(String[] args) {
        String source = "prefix:payload:suffix";
        int begin = "prefix:".length();
        int end = source.indexOf(":suffix");

        StringBuilder builder = new StringBuilder();
        builder.append("value=");
        builder.append(source, begin, end);

        System.out.println(builder.toString());
    }
}
```

```bash
javac -encoding UTF-8 AppendRangeDemo.java
java AppendRangeDemo
```

```text
value=payload
```

Validate `begin` and `end` before appending when indices come from untrusted data (for example, `indexOf` may return `-1`). If slicing could fall inside a surrogate pair of a supplementary Unicode character, choose boundaries by code point to avoid producing strings containing unpaired surrogates. When an API requires an independent `String` at that exact step, not every conversion to `String` can be eliminated.

## 5. When Should You Process Directly in a Single Pass?

A familiar pipeline:

```java
String output = input.trim()
        .toLowerCase(java.util.Locale.ROOT)
        .replace('-', '_')
        .replace(' ', '_');
```

Each step may create a new result and scan the content again. If business logic only requires a small set of rules, you can traverse the input once and write the result directly into a `StringBuilder`. However, **do not change the algorithm and accidentally change the output**: `trim()`, `strip()`, Unicode casing, and `char` operations are not equivalent in all cases.

The following example has a clearly defined scope: it only converts **ASCII letters A–Z to a–z** and replaces ASCII spaces and hyphens with `_`. This is **not** a general rewrite of `toLowerCase(Locale.ROOT)` or `strip()` for arbitrary Unicode text.

Save as `SinglePassAsciiDemo.java`:

```java
public class SinglePassAsciiDemo {
    static String normalizeAscii(String input) {
        StringBuilder out = new StringBuilder(input.length());
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            if (ch == '-' || ch == ' ') {
                out.append('_');
            } else if (ch >= 'A' && ch <= 'Z') {
                out.append((char) (ch + ('a' - 'A')));
            } else {
                out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(normalizeAscii("A-B C"));
        System.out.println(normalizeAscii("Java 17"));
    }
}
```

```bash
javac -encoding UTF-8 SinglePassAsciiDemo.java
java SinglePassAsciiDemo
```

```text
a_b_c
java_17
```

**Advantages:** a single traversal loop and a single builder, without creating separate strings at each transformation step. **Limitations:** this function leaves non-ASCII Unicode characters unchanged, does not trim leading/trailing whitespace, does not handle language-specific casing rules, and does not handle tokens/locales. If full Unicode rules are needed, use the standard APIs or design a code-point/locale-aware algorithm and test thoroughly. Memory optimization never justifies breaking business correctness.

An optimization that is often safer than rewriting an entire pipeline is **merging only the output-building steps**: while scanning/tokenizing the input, append delimiters and needed segments into one builder. Keep tricky Unicode transformations in standard APIs if their cost has not been measured as a bottleneck.

## 6. Choosing the Right Tool for String-Joining Needs

| Need | Sensible tool | Notes |
| --- | --- | --- |
| Joining a few values in one expression | `+` operator | Concise; modern JVMs optimize string concatenation |
| Accumulating data in a loop or across branches | `StringBuilder` | Create a builder for one unit of work; call `toString()` once when done |
| Joining parts with a delimiter | `String.join(...)` or `StringJoiner` | Good when strings already exist; balances readability and allocation |
| Joining elements from a stream | `Collectors.joining(...)` | Readable; each `map(...)` producing a `String` can still create intermediates |
| Formatting many values with a complex template | `String.format(...)` / `formatted(...)` | Expressive formatting; has parse/format cost, so measure if on a hot path |
| Writing large amounts of text to file/network | `Writer`, `BufferedWriter`, or appropriate streaming API | Write incrementally to avoid holding the entire result string in RAM |
| Buffer accessed across multiple threads | Establish ownership and synchronization | `StringBuilder` is not thread-safe; `StringBuffer` synchronizes individual methods without making a multi-step workflow atomic |

Example of delimiter joining with `StringJoiner`:

```java
java.util.StringJoiner joiner = new java.util.StringJoiner(", ", "[", "]");
joiner.add("red").add("green").add("blue");
System.out.println(joiner.toString());
```

```text
[red, green, blue]
```

`StringJoiner` works well when elements are already strings. However, `String.join` or `Collectors.joining` does not automatically eliminate temporary strings produced by earlier steps such as `stream.map(x -> expensiveTransform(x))`. For very large data, you can write each record directly to a `Writer` instead of accumulating everything into a `StringBuilder`.

## 7. Managing `StringBuilder` Capacity

`StringBuilder` has `capacity()` as its current buffer capacity and `length()` as the number of UTF-16 code units currently held. When appending exceeds capacity, the buffer must expand; expansion may require allocation and copying. If you have a reliable estimate of the output size, you can initialize capacity:

```java
int estimatedChars = 128;
StringBuilder builder = new StringBuilder(estimatedChars);
builder.append("prefix:").append("data");
```

Choose capacity based on actual data, such as the sum of part lengths and delimiters. If you only know the element count without knowing individual lengths, do not multiply by an excessively large constant that causes over-allocation. `capacity()` is in UTF-16 units, not Unicode code points or UTF-8 bytes. `StringBuilder.length()` also does not equal user-perceived characters in all languages.

Practical notes:

- `new StringBuilder()` can already grow its capacity; not every case requires predicting capacity.
- `ensureCapacity(...)` can help when a substantially larger requirement becomes known upfront.
- `setLength(0)` clears the logical content to reuse the buffer **but may retain the large allocated backing array**. Reusing a builder that once grew huge in a long-lived cache can hold memory too long.
- `toString()` returns an immutable `String`. Do not call `toString()` repeatedly inside a loop just to check length or simple contents; use `builder.length()`, `charAt(...)`, or dedicated state when appropriate.
- Do not keep a shared static `StringBuilder` across requests/threads. Beyond the risk of race conditions, it can retain unwanted capacity; prefer local builders.

## 8. Avoiding Intermediate Strings at Processing Boundaries

### 8.1. Only Build Messages When Actually Needed

For example, loggers supporting parameterized messages typically allow:

```java
logger.debug("Processed id={}, size={}", id, size);
```

When the DEBUG level is disabled, the framework can avoid formatting the final text. Exact syntax depends on the logging library in use. For expensive operations performed before calling the logger (such as `expensiveToString()`), parameterization does not automatically prevent that method from being evaluated first; check lazy/supplier APIs or enabled checks according to the framework.

### 8.2. Stream Reads/Writes If the Output Is Very Large

Creating a huge `StringBuilder` for millions of records may reduce the count of intermediate `String`s while still holding the entire result in RAM. If the final destination is a file or socket, use a `BufferedWriter` (with an explicit charset) to write incrementally:

```java
try (java.io.BufferedWriter writer = java.nio.file.Files.newBufferedWriter(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    for (String value : values) {
        writer.write(value);
        writer.newLine();
    }
}
```

The snippet above **is a pattern to place inside a method** that already has a `Path path` variable and an `Iterable<String> values` source, not a standalone program. Handle I/O errors, permissions, and resource closing according to application requirements. Streaming writes avoid creating a single resulting `String` containing the entire file; the writer API may still use an internal buffer.

### 8.3. Leverage Existing Data

When you only need to check a prefix, suffix, character at a position, or search for a substring, prefer `startsWith`, `endsWith`, `charAt`, and `indexOf` instead of slicing many `substring`s to compare. For example:

```java
if (value.startsWith("ID:")) {
    // Further processing depends on business logic.
}
```

For portions accessible by an index range, `append(value, begin, end)` avoids creating an intermediate `substring`. Still, do not hold a reference to a huge source just to avoid creating a small string if long-term storage calls for an independent copy.

## 9. When Chaining Multiple Transformation Methods Is Still the Right Choice

Operations such as Unicode normalization, locale-sensitive case folding, JSON/XML escaping, complex regex, parsing, or injection safety have subtle rules. Writing a manual loop solely to use `StringBuilder` can compromise correctness. For example:

- `String.toLowerCase(Locale.ROOT)` handles Unicode mappings that are not equivalent to adding a numeric offset to a `char`.
- `String.strip()` uses Unicode whitespace criteria different from `trim()`; the two methods cannot be swapped arbitrarily.
- Regular expressions have specific semantics; `replaceAll(...)`, `replace(...)`, and matching with a precompiled `Pattern` are not equivalent in all cases.
- Escaping structured data should be delegated to an appropriate serializer/library to avoid security bugs, even if it creates temporary strings or buffers.
- Unicode sequences can contain surrogate pairs and combining marks; each `char` is not necessarily one code point, let alone one user-perceived grapheme.

Keep a readable pipeline when it is already fast enough or when the transformation is tricky. If profiling shows cost in a specific step, optimize that step first. Calls to `replace(...)` that find no match may return the original string; actual allocations must be confirmed with measurement tools.

## 10. Measuring Performance and Allocations Properly

A simple test using `System.nanoTime()` is easily skewed by JIT warmup, GC, caches, data sizes, dead-code elimination, and how inputs are prepared. To compare string-processing approaches:

1. **Verify identical outputs first:** test empty cases, `null` if the API allows it, delimiters, string boundaries, Vietnamese diacritics, supplementary Unicode characters, and large inputs. If semantics change, speed numbers no longer compare the same functionality.
2. **Define the workload:** element count, average length, ASCII/Unicode distribution, call frequency, heap limits, and proportion of data actually needing transformation.
3. **Profile the application:** use Java Flight Recorder (JFR), a profiler, or an allocation measurement tool to find where objects are created; observe throughput, latency, allocation rate, and GC pauses.
4. **Benchmark hot segments:** use JMH with warmup, multiple measurement iterations, and result consumption to prevent dead-code elimination; compare on the same Java version, hardware, and data. Track both `ops/s` or `ns/op` and allocated bytes per operation when possible.
5. **Test small changes in the real application:** re-measure end-to-end. Microbenchmark gains may not improve request latency if time is dominated by I/O, locks, or the database.

An optimization is worthwhile when it **preserves correctness, achieves a measurable cost reduction, and does not hurt maintainability more than it helps**. Prioritize replacing high-iteration `result += item` loops with a builder or streaming directly to a writer before optimizing small expressions.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `result += part` inside a large loop | Repeatedly creates new accumulated result strings | Use `StringBuilder` or `Writer` |
| `builder.append(prefix + value + suffix)` per iteration | May create a `prefix + value + suffix` string before appending | Call `append(prefix).append(value).append(suffix)` |
| `builder.toString().isEmpty()` per iteration | Requires creating/checking the result string repeatedly | Use `builder.length() == 0` |
| `builder.append(text.substring(a, b))` just to copy a slice | May create a temporary `String` copy | Use `builder.append(text, a, b)` |
| Reusing a global builder or a huge builder | Race conditions, mixed data, retained memory | Use a local builder per unit of work |
| Rewriting Unicode handling manually to be “faster” | Wrong case mappings, wrong whitespace, split surrogates | Keep standard Unicode APIs; optimize with evidence |
| Over-estimating capacity | Unnecessary RAM allocation | Use realistic estimates or let the builder grow |
| Using `StringBuilder` for every `+` | More verbose code with uncertain benefit | Only change identified hot code |

A small tip: if you want to insert a delimiter between parts, check the builder before appending:

```java
if (builder.length() > 0) {
    builder.append(", ");
}
builder.append(value);
```

This avoids creating intermediate strings and avoids a leading delimiter; however, you need a clear policy when `value` is an empty string, `null`, or a filtered-out element.

## 12. Practice Exercises

**Exercise 1 — joining results:** from an array of 10,000 strings, build comma-separated text in two ways: a `+=` loop and `StringBuilder`. Compare the results with `equals`, then benchmark properly; distinguish “both outputs are equal” from “proving which way is faster”.

**Exercise 2 — removing temporary formatted strings:** rewrite `builder.append("(" + id + ":" + value + ")")` as chained `append(...)` calls. Test negative `id`, empty `value`, and Unicode characters.

**Exercise 3 — avoiding `substring`:** given `"before[content]after"`, find the positions between `[` and `]` and append directly into a builder using `append(source, start, end)`. Test the case where the closing bracket is missing.

**Exercise 4 — pipeline:** define your own set of ASCII rules and write a single-pass function producing output equivalent to a chain of `replace` calls. Write comparison tests across many inputs before measuring allocations.

**Exercise 5 — large data:** replace a pattern that builds one huge CSV string with writing row by row through `BufferedWriter`. Measure heap usage and write time for both on a controlled dataset.

### Practical Conclusion

For repetitive text-building steps, consider **appending parts directly into one `StringBuilder`**, using index ranges to avoid `substring` just for copying, and switching to streaming writes when outputs become too large. Complex Unicode transformations must prioritize correctness. Choose where to optimize based on a profiler, result tests, and allocation measurements, not merely by counting `+` signs in the code.