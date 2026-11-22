# Estimating `StringBuilder` `capacity` in Java

## Objective

When joining many strings in a loop, creating a `StringBuilder` with an appropriate initial capacity can reduce the number of intermediate buffer expansions. However, choosing too large a value holds unnecessary resources. This lesson explains what `capacity` is, how to estimate it from input data, when to use `new StringBuilder(capacity)` or `ensureCapacity()`, and how to verify assumptions with Java 17+.

## 1. Distinguishing `length` and `capacity`

`StringBuilder` is an object that stores a mutable sequence of characters. Two easily confused properties are:

- `length()`: the number of **UTF-16 code units currently containing content** in the builder.
- `capacity()`: the number of **UTF-16 code units that can be held before expansion is needed**. Capacity can be greater than `length()`.

It is always true that `0 <= length() <= capacity()`. When `append()` adds content, `length()` increases by the amount of text actually added; if more space is needed, the builder automatically increases `capacity()`. When `toString()` is called, the returned string has content matching `length()`, without the unused capacity.

For example, if a builder currently has `length() == 5` and `capacity() == 20`, you can append up to 15 more UTF-16 units before the storage needs to expand. **Capacity is not a byte count**, is not necessarily a Unicode code point count, and is not a permanent maximum length of the `StringBuilder`.

### Common Initial Values

| Call | Initial `length()` | Initial `capacity()` |
| --- | ---: | ---: |
| `new StringBuilder()` | 0 | 16 |
| `new StringBuilder(100)` | 0 | 100 |
| `new StringBuilder("")` | 0 | 16 |
| `new StringBuilder("abc")` | 3 | 19 |
| `new StringBuilder(existingSeq)` | `existingSeq.length()` | `existingSeq.length() + 16` |

Constructing from a `String` or `CharSequence` both **copies the content** and reserves extra capacity. Conversely, constructing with an integer only creates a buffer with the requested capacity, without adding any text. `new StringBuilder(-1)` throws `NegativeArraySizeException`. When the input is already a known string, `new StringBuilder(existingString)` makes more sense than appending that string manually again.

## 2. Why Estimate Capacity?

Suppose you build a resulting string tens of thousands of UTF-16 units long from thousands of small segments. If you start with a very low capacity, the builder may have to allocate a larger buffer and copy existing content whenever it exceeds the limit. Pre-allocating close to the final size often helps reduce expansions, especially when processing large volumes frequently.

Even so, `StringBuilder` **expands automatically when needed**; not guessing the capacity upfront does not make the string incorrect. The goal is to reduce allocations and copying if this is genuinely a time-consuming part of the work.

Two common usage patterns:

```java
// Simple, usually good enough for small strings or unknown lengths.
StringBuilder message = new StringBuilder();
message.append("Hello, ").append("Java");

// When the approximate result size is already known.
int expectedLength = 1024;
StringBuilder buffer = new StringBuilder(expectedLength);
```

These are illustrative snippets within the context of a method. Capacity does **not** cap the content at 1024: further appends can still grow the buffer.

### How Capacity Grows When Full

In the OpenJDK implementation used in Java 17, automatic capacity growth typically chooses at least:

```text
newCapacity ≈ max(minimumCapacity, oldCapacity * 2 + 2)
```

Here `minimumCapacity` is the number of UTF-16 units needed after the operation. The formula includes branches for overflow handling and array limits; therefore this is a **description of the implementation's typical growth rule**, not a guarantee that every JDK or every case returns this exact formula. According to the API, what matters is that the builder ensures enough room for the content if it can allocate it.

For example: starting from capacity 4, an `append` that pushes length past 4 will expand it. You should not rely on the exact capacity after growth for program correctness.

## 3. Estimation Formula from the Parts to Be Joined

If the text segments and separators are known, you can compute the **exact number of UTF-16 units of the result** before creating the builder:

```text
estimatedCapacity = total length() of the data parts
                  + total length of the separators
                  + length of fixed prefix/suffix/labels
                  + length of conditionally added characters
```

For example, joining `n` strings with a comma between every two parts, **with no trailing comma**:

```text
estimatedCapacity = sum(part.length()) + max(0, n - 1)
```

With an arbitrary `String separator`:

```text
estimatedCapacity = sum(part.length())
                  + max(0, n - 1) * separator.length()
```

In the formula above, `length()` measures **UTF-16 units**; this is the exact unit needed for capacity. If appending `\n` once after each line, add one unit per `\n`. For `\r\n` line endings, add two units each time. For `System.lineSeparator()`, use `separator.length()` instead of assuming it is exactly one character.

### Complete Example: Joining Data with a Separator

Save as `CapacityEstimateDemo.java`:

```java
import java.util.List;

public class CapacityEstimateDemo {
    public static void main(String[] args) {
        List<String> parts = List.of("Java", "17", "StringBuilder");
        String separator = ",";

        int estimate = 0;
        for (String part : parts) {
            estimate = Math.addExact(estimate, part.length());
        }
        int separatorCount = Math.max(0, parts.size() - 1);
        int separatorsLength = Math.multiplyExact(
                separatorCount, separator.length());
        estimate = Math.addExact(estimate, separatorsLength);

        StringBuilder result = new StringBuilder(estimate);
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) {
                result.append(separator);
            }
            result.append(parts.get(i));
        }

        System.out.println("estimated=" + estimate);
        System.out.println("length=" + result.length());
        System.out.println("capacity=" + result.capacity());
        System.out.println("text=" + result);
    }
}
```

Run on Java 17+:

```bash
javac CapacityEstimateDemo.java
java CapacityEstimateDemo
```

Output:

```text
estimated=21
length=21
capacity=21
text=Java,17,StringBuilder
```

`"Java"` has length 4, `"17"` has length 2, and `"StringBuilder"` has length 13; adding 2 commas = 21. Because the builder was created with the exact capacity needed, the program does not need to expand while joining this data. When `parts` is empty, the formula yields 0 and the builder has capacity 0; when there is only one part, there is no separator.

The two methods `Math.addExact` and `Math.multiplyExact` help detect `int` overflow when summing sizes, instead of silently producing a negative or too-small number. They throw `ArithmeticException` on overflow. However, an extremely large capacity even within `int` range may still fail to allocate due to VM or memory limits.

**Trade-off:** computing the exact total length of all inputs costs an extra traversal pass. If the data is already being traversed for validation or statistics, it is nearly free; if all parts are tiny, the cost of pre-measuring may outweigh the benefit of avoiding a few expansions. Measure in the actual scenario.

## 4. When the Exact Output Size Is Unknown

Some text segments are produced from numbers or formatting conversions. Distinguish the **value** from the **character count after conversion**:

- `builder.append(12345)` adds 5 UTF-16 units, not 12,345 units.
- `builder.append(-12)` adds 3 units: the `-` sign and two digits.
- `builder.append(true)` adds 4 units, `false` adds 5.
- `builder.append((String) null)` adds the 4-character string `"null"`.
- `builder.append('\n')` adds 1 unit; `builder.append("\r\n")` adds 2.
- `builder.append("😀")` adds 2 UTF-16 units even though the user sees one emoji.

If arguments come from `String.valueOf(x)`, `toString()`, `String.format()`, a JSON serializer, or a locale-aware formatter, the size depends on the **actual output** (e.g., thousands separators, digit count, escaping, whitespace, optional fields). Do not use UTF-8 byte counts or the number of data fields directly as capacity.

When the exact size is unknown, you can estimate by record count:

```java
int rowCount = 500;
int estimatedUnitsPerRow = 48;
int estimate = Math.multiplyExact(rowCount, estimatedUnitsPerRow);
StringBuilder report = new StringBuilder(estimate);
```

This is an illustrative snippet, assuming an average estimate of 48 UTF-16 units per row **already including separators or newlines**. With 500 rows, the estimate equals 24,000. If the actual output is longer, the builder still expands automatically; if the actual output is shorter, the excess does not appear in the resulting string, though the backing buffer may occupy memory.

### Choosing Between Exact and Approximate Estimation

| Data | Appropriate calculation | Reason |
| --- | --- | --- |
| Existing list of `String`s | Sum `length()`, prefix, suffix, and separator | Can be calculated exactly |
| Appending fixed `char`s or newlines | Sum insertion count times each element's length | Usually calculable exactly |
| CSV rows requiring quote escaping | Calculate after escaping, or estimate from data | Source data may grow longer |
| Locale-formatted numbers, dates, percentages | Measure formatted string length if exactness is needed | Size depends on formatting representation |
| Known record count with variable content | Average length times record count | Approximation is sufficient |
| Stream with unknown end | Start modestly, expand as needed, optionally `ensureCapacity` | No reliable total length available |

An overly complex formula that duplicates the string-joining logic itself can be error-prone and add overhead. Estimation should serve optimization, not become a source of business-logic bugs.

## 5. How Do `ensureCapacity`, `setLength`, and `trimToSize` Differ?

`StringBuilder` has three easily misunderstood APIs:

| API | Effect on `length()` | Effect on `capacity()` |
| --- | --- | --- |
| `ensureCapacity(minimum)` | Unchanged | Ensures at least the requested number of UTF-16 units if growth is needed; may grow more |
| `setLength(newLength)` | Changes to exactly `newLength` | May grow if `newLength` exceeds capacity; added positions have value `\u0000` |
| `trimToSize()` | Unchanged | Attempts to reduce unused capacity; the API does not guarantee always reaching exact `length()` |

`ensureCapacity` is appropriate when **the builder has already been created and a larger need becomes known later**:

```java
StringBuilder builder = new StringBuilder();
builder.append("header:");
builder.ensureCapacity(1000);
builder.append("data");

System.out.println(builder.length());           // 11
System.out.println(builder.capacity() >= 1000); // true
```

This snippet can be run in `jshell` or inside a method. Calling `ensureCapacity(1000)` does not add 1000 characters; it only requests space. If the passed value is less than or equal to 0, `ensureCapacity` does not need to change capacity. It is not a promise that "capacity equals exactly 1000": after expansion, capacity may be larger.

Do not use `setLength(1000)` to "reserve capacity", because it makes the string genuinely 1000 units long by appending `\u0000` units. Those NUL units are **real content**, corrupting data if sent or written to a file. To reserve space, use the constructor or `ensureCapacity`.

`trimToSize()` can help release large excess space after a string-building phase if the builder must be kept alive long-term, though it may also force the next append to expand again. Do not call it after every `append()`.

## 6. Observing Capacity Growth in Java

Save as `BuilderGrowthDemo.java`:

```java
public class BuilderGrowthDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(4);
        System.out.println("initial=" + builder.length() + "/" + builder.capacity());

        builder.append("abcd");
        System.out.println("filled=" + builder.length() + "/" + builder.capacity());

        builder.append('e');
        System.out.println("expanded=" + builder.length() + "/" + builder.capacity());

        builder.append("0123456789");
        System.out.println("expanded-again=" + builder.length()
                + "/" + builder.capacity());

        StringBuilder initial = new StringBuilder();
        StringBuilder fromText = new StringBuilder("abc");
        System.out.println("default=" + initial.capacity());
        System.out.println("from-text=" + fromText.capacity());
    }
}
```

Run:

```bash
javac BuilderGrowthDemo.java
java BuilderGrowthDemo
```

On common OpenJDK builds (verified against the OpenJDK implementation), the output is:

```text
initial=0/4
filled=4/4
expanded=5/10
expanded-again=15/22
default=16
from-text=19
```

Initially, the builder has 4 slots. After `"abcd"`, it is full but has not grown yet. Appending `'e'` raises length to 5, so capacity expands to 10. Appending the next 10 characters brings length to 15, at which point capacity becomes 22. **The expanded values after append are implementation observations**, not conditions application code should depend on. Constructor capacities are more explicitly specified in Java documentation and can be used directly to verify estimates.

## 7. Unicode: Why Not Use Bytes or Code Point Count as Capacity?

For `StringBuilder`, `length()` and `capacity()` are measured in **UTF-16 code units**, not UTF-8 bytes. For example:

```java
import java.nio.charset.StandardCharsets;

String value = "A\uD83D\uDE00";
StringBuilder builder = new StringBuilder(value.length());
builder.append(value);

System.out.println(builder.length());
System.out.println(builder.capacity());
System.out.println(value.codePointCount(0, value.length()));
System.out.println(value.getBytes(StandardCharsets.UTF_8).length);
```

This can be run in `jshell`; the outputs in order are:

```text
3
3
2
5
```

`"A😀"` consists of 3 UTF-16 units, 2 code points, and 5 UTF-8 bytes. Therefore, the capacity needed to append exactly one copy of `value` is 3. If you use 2 (code point count), the builder still works but has to expand. If you use 5 (UTF-8 bytes), the builder over-allocates capacity units.

A combining mark or complex emoji sequence can also contain multiple code points while being perceived by the reader as one character. Do not use grapheme cluster count to size capacity. When adding Unicode code points via `appendCodePoint(int)`, the number of units added is `Character.charCount(codePoint)`: 1 for a valid BMP character, 2 for a supplementary character.

Do not infer actual heap memory using a rigid `capacity * 2` formula. Modern Java implementations may use Compact Strings and internal JVM storage mechanisms; there is also object, array, alignment, and internal encoding overhead. `capacity()` is a useful indicator for predicting **logical storage slots**, not a RAM byte meter.

## 8. Optimizing in the Right Place

Specifying capacity is an optimization worth considering when:

1. Joining very many parts in a loop and the final size is fairly predictable.
2. Every request or processing step creates a large builder; allocation and copy costs show up in a profiler.
3. The output always follows a stable template: known labels, separators, or record counts.
4. A large builder is used on a hot path and choosing capacity has been proven beneficial by benchmarks.

You do not need to specify capacity on every statement joining a few words. Default `StringBuilder()` already provides a small amount of space; the compiler can also optimize many `+` concatenation expressions in its own way. Do not replace every string concatenation with a builder just because you believe a sized constructor is always faster.

Watch out for cases that backfire:

- **Under-estimating:** still expands multiple times, potentially causing intermediate allocations and copies.
- **Over-estimating:** wastes buffer space, increases memory pressure, or leads to `OutOfMemoryError`.
- **Miscalculation/overflow:** negative values cause `NegativeArraySizeException`; unchecked `int` addition/multiplication can overflow. Use `Math.addExact`/`multiplyExact` when summing many parts and enforce appropriate domain bounds.
- **Using source `String.length()` before escaping:** data after escaping may be longer.
- **Using capacity as network byte count:** UTF-8 payload length must be calculated from the actual `byte[]` sent.
- **Calling `toString()` repeatedly in a loop:** creates unnecessary intermediate `String`s; normally finish appending and convert to `String` once.
- **Sharing a builder across threads:** `StringBuilder` is unsynchronized and does not guarantee safety under concurrent modification by multiple threads; keep ownership local to a task or synchronize appropriately.

### How Should You Check Performance?

Checking `builder.length()` and `builder.capacity()` after construction verifies whether your estimate is far too small or too large. However, capacity **does not by itself prove the program runs faster**. When you need to compare strategies, benchmark with JMH using representative data, warm-up, multiple runs, and prevent the JVM from optimizing away the result. Monitor total time, allocation rate, and GC with a profiler when appropriate; if you have to traverse the data an extra time to compute capacity, include that traversal cost as well.

A pragmatic approach is to start with `new StringBuilder()`, specify capacity when the problem provides a reasonable prediction, and tune after measurement rather than applying a fixed multiplier to every string.

## 9. Self-Check Exercises

**Exercise 1.** You need to join three strings `"abc"`, `"Java"`, `"17"` with the separator `" | "` (3 UTF-16 units) between them. What is the minimum capacity to avoid resizing during concatenation?

**Exercise 2.** You need to generate 100 lines, each exactly 30 UTF-16 units long and ending with `"\r\n"`. What is the minimum capacity? What is the result if the newline changes to `"\n"`?

**Exercise 3.** Why is `new StringBuilder(100)` completely different from `new StringBuilder().setLength(100)`? Do both have an initial `length()` of 0?

**Exercise 4.** Given `String text = "A\uD83D\uDE00";`, what are the results of `text.length()` and `text.getBytes(StandardCharsets.UTF_8).length`? Which number should you pass to the constructor when appending `text` just once?

**Exercise 5.** An application always joins 10 short words. Is computing the exact length before joining guaranteed to improve performance? What must you measure to conclude?

**Answer hints:** (1) 3 + 4 + 2 + 2×3 = **15**; (2) 100×(30+2) = **3200**, with LF it is **3100**; (3) the integer constructor sets capacity 100 and length 0, whereas `setLength(100)` appends NUL content so length is 100; (4) length 3, UTF-8 bytes 5, capacity **3**; (5) not guaranteed: you must measure the capacity-calculation cost, number of expansions/allocations, time, and GC under the actual workload.

### References

- [`StringBuilder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`AbstractStringBuilder` — OpenJDK source](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/AbstractStringBuilder.java) (growth rule is at the implementation level and may change across versions).
- [`Character.charCount` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#charCount(int)).
