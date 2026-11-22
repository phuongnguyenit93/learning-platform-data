# Cost of Traversing, Searching, Comparing, and Copying String by Length in Java

The performance of operations on `String` often depends on **the length of data to be read** and **the amount of data that must be created**, not just on the number of method calls. A short-looking expression such as `text.indexOf(pattern)`, `a.equals(b)`, or `text.substring(from, to)` can process thousands or millions of character units. Understanding these costs helps you choose algorithms, avoid repeated copying, and accurately evaluate bottlenecks.

This lesson examines Java 17+ `String`, focusing on the cost of **traversing, searching, comparing, and copying by length**. Big-O notation describes how cost grows as data size increases, **not a fixed number of milliseconds**. Some optimizations depend on the JDK version, JIT, charset, string content, and how the JVM is implemented; therefore, it is necessary to distinguish the algorithmic model from Java API guarantees.

## 1. Defining Input Sizes Properly

Use the following notation:

| Symbol | Meaning |
| --- | --- |
| `n` | `text.length()`: number of **UTF-16 code units** in the source string. |
| `m` | `pattern.length()`: number of UTF-16 code units in the pattern to search for. |
| `k` | Length of the segment being compared, traversed, or copied; for example, `endIndex - beginIndex`. |
| `r` | Number of iterations or number of additional parts created. |
| `L` | Total length of the parts to be joined into the result. |

In Java, `String.length()` returns the number of UTF-16 code units, **not** the number of Unicode code points, user-perceived characters (*grapheme clusters*), or UTF-8 bytes.

```java
String x = "A\uD83D\uDE00"; // A and emoji 😀
int units = x.length();                            // 3
int points = x.codePointCount(0, x.length());     // 2
int bytes = x.getBytes(StandardCharsets.UTF_8).length; // 5
```

This is an **illustrative snippet**; `java.nio.charset.StandardCharsets` must be imported. An emoji is stored as a surrogate pair, corresponding to **two** UTF-16 code units and **four** UTF-8 bytes. When analyzing the complexity of `charAt`, `indexOf`, `substring`, or `compareTo`, Java indices are typically measured in UTF-16 code units.

Distinguish between:

- **Time:** the work that must be performed as `n`, `m`, or `k` increases.
- **Auxiliary memory:** new memory created by the operation, excluding already-existing input objects.
- **Cumulative cost:** an `O(n)` operation repeated `r` times can become `O(rn)`; if the string length grows on each iteration, the total is even larger.

## 2. Overview Table of Costs to Remember

The table below is an **academic and practical model commonly seen on Java 17**, not a guaranteed complexity requirement for every JVM/version. Operations may terminate early or be optimized by the JIT.

| Operation | Common time cost | Common auxiliary memory | Notes |
| --- | --- | --- | --- |
| `s.length()` | `O(1)` | `O(1)` | Length is stored in the object/data; not counted by traversing on every call. |
| `s.isEmpty()` | `O(1)` | `O(1)` | Equivalent to checking whether length is 0. |
| `s.charAt(i)` | `O(1)` | `O(1)` | Accesses a single UTF-16 code unit after an index bounds check. |
| A single loop from `0` to `n - 1` | `O(n)` | `O(1)` if only accumulating variables | Can exit early when a condition is met. |
| `s.codePointCount(a, b)` | `O(k)` in general | `O(1)` | Must identify surrogate pairs in a segment of length `k`; Latin-1 strings have an optimized path. |
| `s.indexOf(ch)` / `lastIndexOf(ch)` | `O(n)` when scanning the whole string is required | `O(1)` typical | Best case can find the character immediately. |
| `s.indexOf(pattern)` / `s.contains(pattern)` | Depends on the string-search algorithm and pattern; a simple matching model has worst case `O(nm)` | Implementation-dependent | Do not blindly label it `O(n)` or `O(nm)` as an API guarantee across all JDKs. |
| `s.startsWith(prefix)` | `O(m)` at most for a prefix of length `m` | `O(1)` typical | Can stop at the first differing character. |
| `s.endsWith(suffix)` | `O(m)` at most for a suffix of length `m` | `O(1)` typical | Does not need to scan the leading portion when checking only the suffix. |
| `s.equals(t)` | `O(n)` worst case for two strings of equal length; can exit early | `O(1)` typical | Different lengths return quickly; identical contents must be compared throughout. |
| `s.compareTo(t)` | `O(min(n,m))` for the compared prefix | `O(1)` typical | Stops at the first differing character or the end of the shorter string. |
| `s.regionMatches(..., len)` | `O(len)` worst case | `O(1)` typical | Compares only the specified region. |
| `s.substring(a, b)` | `O(k)` when creating a copy of a segment of length `k` on modern OpenJDK | `O(k)` when copying is required | Empty or full-string cases may be optimized; do not treat allocation details as an API contract. |
| `s.toCharArray()` | `O(n)` | `O(n)` | Creates a `char[]` array with `n` UTF-16 code units. |
| `s.getBytes(charset)` | Depends on charset; at minimum needs to create/write the output bytes, typically linear in the data | `O(b)` for `b` output bytes | Do not use `n` as the byte count because UTF-8 is variable-length. |

**Key takeaway:** a short statement in source code does not equate to an `O(1)` operation. `charAt(i)` retrieves only a single character unit; `equals`, `indexOf`, or `toCharArray` may need to process most of the string.

## 3. String Traversal: Single Scan vs. Multiple Scans

### 3.1. The `charAt` Loop

```java
int digits = 0;
for (int i = 0; i < text.length(); i++) {
    if (text.charAt(i) >= '0' && text.charAt(i) <= '9') {
        digits++;
    }
}
```

This is an **illustrative snippet**, assuming `text` has already been declared. `length()` and each `charAt(i)` have a small cost, typically `O(1)`; the loop runs `n` times, so the total is **`O(n)` time and `O(1)` auxiliary memory**. It is not `O(n²)` merely because `length()` is called in the loop condition.

If the problem only needs to find the **first character** satisfying a condition, use `break` or return early. The worst case is still `O(n)`, but real-world data may finish early.

### 3.2. Code Units Differ from Code Points

`charAt` accesses a **UTF-16 code unit**, so when a string contains emojis or characters outside the BMP, each `charAt` does not necessarily represent a complete Unicode code point. If the logic requires reading code point by code point:

```java
int count = 0;
for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    count++;
    offset += Character.charCount(cp);
}
```

The snippet above iterates over each code point. At each step, `codePointAt` inspects only one or two code units near the current position; the total is still **`O(n)`** in terms of the number of UTF-16 code units. You can use `text.codePoints()` when a stream pipeline makes the code clearer, though streams add dispatch/object overhead and are not automatically faster than a loop in all cases.

### 3.3. Calling Full-String Scans Inside a Loop

```java
// Incurs many additional searches:
for (int i = 0; i < queries.size(); i++) {
    boolean present = bigText.contains(queries.get(i));
    // ...
}
```

Suppose there are `r` queries. Each `contains` call may search across a text of length `n` and a pattern of length `m_i`; you must **not** count the whole loop as just `O(r)`. The total is the sum of the costs of each individual search, depending on the data. If the same query is repeated many times, consider caching results; if you need to look up a large number of words/patterns, an index structure or multi-pattern algorithm can help, but you should measure before investing in it.

## 4. Searching: Single Character and Substring

### 4.1. `indexOf(int)`, `lastIndexOf(int)`

```java
String s = "ababaX";

int firstA = s.indexOf('a');         // 0
int lastA = s.lastIndexOf('a');      // 4
int absent = s.indexOf('z');        // -1
```

These methods can stop as soon as they find the target; if the character does not exist, they typically have to check to the end of the search range. Therefore, use the **`O(n)` worst-case** model with `O(1)` auxiliary memory. `indexOf(int)` also supports Unicode code points outside the BMP (matching surrogate pairs); the returned position is still a UTF-16 index.

### 4.2. `indexOf(String)`, `contains(String)`

Assume a source of length `n` and a pattern of length `m`:

```java
String s = "ababaX";
int a = s.indexOf("aba");     // 0
int b = s.indexOf("aba", 1);  // 2
boolean found = s.contains("baba"); // true
```

You should not assert a single Big-O for every implementation and every pattern. A simple substring search tries up to `n - m + 1` positions and may compare up to `m` units at each position, giving a **worst case of `O(nm)`**. Libraries/JVMs may optimize for specific string representations, short patterns, or specific content. `contains` checks for the presence of a substring, not a regex match. In Java, `s.contains(x)` uses substring search (equivalent to checking `indexOf(x) >= 0`).

**Example of repeated matching:** a source consisting of many `a`s and a pattern starting with many `a`s followed by `b` can force a naive matching algorithm to re-compare many positions. This is an algorithmic analysis model, not a claim about a fixed runtime on HotSpot 17.

### 4.3. When Checking Only the Start or End

If the requirement is only to check a **prefix**, use `startsWith(prefix)`; if only to check a **suffix**, use `endsWith(suffix)`. They only need to compare the corresponding region, at most `O(m)` where `m` is the prefix/suffix length after checking lengths, rather than searching the entire string. For example:

```java
String path = "/api/orders/123";
boolean apiPath = path.startsWith("/api/");
boolean endsWithId = path.endsWith("/123");
```

Do not write `indexOf(prefix) == 0` when `startsWith(prefix)` states the intent more clearly; any specific performance benefit also depends on the environment.

### 4.4. Regex Differs from Plain String Search

`String.matches(regex)`, `split(regex)`, and `replaceAll(regex, replacement)` use **regex** and incur pattern parsing and matching costs. Regex complexity depends on the expression, especially with backtracking and nested branches; some patterns exhibit very large growth when the input does not match. Therefore, you cannot infer from `indexOf` that all regex searches are linear.

If you only need to find a **literal** character sequence, prefer `indexOf`/`contains`; if you need a regex repeatedly, consider compiling a `Pattern` once and using a new `Matcher` per input. Measuring on representative data matters more than generic optimization tips.

## 5. Comparing: Early Mismatch Is Cheap, Long Shared Prefixes Are Costly

### 5.1. `equals`

```java
boolean x = "prefix-a".equals("prefix-b"); // false
boolean y = "same".equals(new String("same")); // true
```

`equals` checks whether the contents are equal. If the two `String` objects are the exact same reference, or have different lengths, it can return quickly. If they have the same length and share many leading characters, it must compare further; two genuinely equal long strings require comparing all content to confirm, so the worst-case model is **`O(n)`**.

Note that `==` checks **object references**, not content equality. Replacing `equals` with `==` as an "optimization" changes semantics and easily causes bugs.

### 5.2. `compareTo`

`s.compareTo(t)` compares lexicographical order by the UTF-16 value of each character unit. It returns a negative number, 0, or a positive number; you should not assume it always returns only -1, 0, or 1.

- If the first character differs, it can finish early.
- If `s` and `t` share a long identical prefix, it must compare deeper.
- If one string is a prefix of the other, after comparing through the end of the shorter string it examines the length difference.

With lengths `n` and `m` respectively, the maximum number of elements compared is proportional to **`min(n,m)`**, so the model is `O(min(n,m))` for comparison time and `O(1)` typical auxiliary memory. The cost can grow substantially when sorting a list of many very long strings with shared prefixes.

### 5.3. `regionMatches`, `equalsIgnoreCase`

`regionMatches` compares a segment of length `k` without needing to create a `substring` first:

```java
String s = "prefixVALUEsuffix";
boolean same = s.regionMatches(6, "VALUE", 0, 5); // true
```

When you only need to check a slice, this approach **avoids creating an intermediate substring/object**. Region comparison cost is around `O(k)` worst case; it stops early on mismatch.

`equalsIgnoreCase` compares case-insensitively according to the API's Unicode rules, not locale-sensitive linguistic comparison; it may still need to read many character units. If you need natural-language ordering or semantics, use `Collator` with the appropriate locale.

## 6. Copying: Time and Memory Grow with the Data Created

### 6.1. `substring(begin, end)`

```java
String s = "hello-world";
String piece = s.substring(6, 11); // "world"
```

With `k = end - begin`, OpenJDK 17 typically creates character data for the result of length `k`, so **the cost is roughly `O(k)` in time/memory** when a copy is needed. This is an **implementation** property, not a contract saying every `substring` call allocates; for instance, taking the entire string or an empty string may be optimized.

Do not carry over assumptions from very old JDKs that every substring is a "view" sharing the backing array of the original string. On modern JVMs, keeping a small substring typically does not force retaining the entire long original character array; however, the cost of slicing many substrings still needs to be accounted for.

If you only need to **check** a segment, `regionMatches` often avoids creating a substring. If you genuinely need to store and use the text slice long-term, `substring` may be the right and readable choice; do not avoid copying with complex structures before a real problem exists.

### 6.2. `toCharArray`, `getBytes`, `getChars`

- `toCharArray()` creates a new `char[]` with `n` code units: **`O(n)` time, `O(n)` auxiliary memory** for the array.
- `getBytes(StandardCharsets.UTF_8)` encodes into a new `byte[]`: typically has cost proportional to the number of input units and output bytes. For `b` output bytes, memory for the result data is **`O(b)`**.
- `getChars(srcBegin, srcEnd, dst, dstBegin)` copies `k` code units into a **caller-provided array**: `O(k)` time; it does not need to allocate a returned `char[]` per call, though you must ensure the destination has enough room.

Two strings with the same `length()` do not necessarily produce the same number of UTF-8 bytes: ASCII uses one byte per code point, whereas many Vietnamese characters or emojis need more. Therefore, payload size and transmission cost must look at `getBytes(...).length`, not rely solely on `String.length()`.

### 6.3. Strings Are Immutable; Transformed Results May Create New Data

`String` is immutable; operations that produce transformed text values, such as `toUpperCase`, `replace`, or `repeat`, do not mutate the original content. If the result differs from the input and is materialized, there must be space to store the result data; the minimum cost relates to **the number of output characters/bytes**. However, you should not assign a single exact Big-O to every `replace` overload and every regex expression: searching, replacement, and normalization algorithms can differ.

For example, `"ab".repeat(4)` creates `"abababab"`, which is eight code units long. If the repeat count is `r` and the source string has length `n`, a product of size `n × r` must be created (except for special cases like `r = 0` or `1`).

## 7. Repeated String Concatenation: Cumulative Cost

The complexity of **a single concatenation** differs from the total cost when repeatedly concatenating onto the same prefix. Consider a loop over an existing list `parts`:

```java
String result = "";
for (String part : parts) {
    result += part;
}
```

Because `String` is immutable, each iteration can create a new result containing the entire accumulated prefix. With `r` parts, each of length `c` UTF-16 units, the total length of intermediate results under a sequential copying model is `c × (1 + 2 + … + r) = c × r(r + 1)/2`, which is **`Θ(c·r²)`**. Meanwhile, the final string is only `L = c·r` long. This is a model of work, not the exact number of bytes allocated by every JVM.

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
```

With a proportionally growing buffer, building with `StringBuilder` usually has a total append cost **close to `O(L)` in the amount of data appended**, plus the cost of creating the final result. If a reasonable size is known, you can pre-size capacity to reduce resizes. Distinguish this from a single expression like `a + b + c`: modern compilers/JVMs can optimize it effectively, so there is no need to replace every `+` with a builder.

The calculation of total copied data for uneven segments, runnable examples, and the difference between theoretical character counts and actual allocations are covered in the dedicated lesson on repeated `+=` concatenation. Here, the point to keep in mind is that **cumulative cost depends on how many times old data has to be reprocessed**.

## 8. Standalone Runnable Java 17+ Example

Create the file `StringCostDemo.java` with the following code:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StringCostDemo {
    public static void main(String[] args) {
        String text = "ababaX";
        String pattern = "aba";

        System.out.println("length: " + text.length());
        System.out.println("charAt(3): " + text.charAt(3));
        System.out.println("first pattern: " + text.indexOf(pattern));
        System.out.println("pattern after 0: " + text.indexOf(pattern, 1));
        System.out.println("last pattern: " + text.lastIndexOf(pattern));
        System.out.println("missing char: " + text.indexOf('z'));
        System.out.println("startsWith: " + text.startsWith("aba"));
        System.out.println("endsWith: " + text.endsWith("X"));
        System.out.println("equals: " + text.equals(new String("ababaX")));
        System.out.println("compareTo: " + text.compareTo("ababaY"));
        System.out.println("regionMatches: "
                + text.regionMatches(2, pattern, 0, 3));

        String piece = text.substring(2, 5);
        char[] copy = text.toCharArray();
        System.out.println("substring: " + piece);
        System.out.println("copied chars: " + copy.length);

        int sum = 0;
        for (int i = 0; i < text.length(); i++) {
            sum += text.charAt(i);
        }
        System.out.println("code-unit sum: " + sum);

        String unicode = "A\uD83D\uDE00"; // A and emoji
        System.out.println("UTF-16 units: " + unicode.length());
        System.out.println("code points: "
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("UTF-8 bytes: "
                + unicode.getBytes(StandardCharsets.UTF_8).length);

        List<String> parts = List.of("[0]", "[1]", "[2]", "[3]");
        StringBuilder builder = new StringBuilder(12);
        for (String part : parts) {
            builder.append(part);
        }
        System.out.println("built: " + builder);
        System.out.println("built length: " + builder.length());
    }
}
```

Compile and run from the directory containing the file:

```bash
javac -encoding UTF-8 StringCostDemo.java
java StringCostDemo
```

Output:

```text
length: 6
charAt(3): b
first pattern: 0
pattern after 0: 2
last pattern: 2
missing char: -1
startsWith: true
endsWith: true
equals: true
compareTo: -1
regionMatches: true
substring: aba
copied chars: 6
code-unit sum: 575
UTF-16 units: 3
code points: 2
UTF-8 bytes: 5
built: [0][1][2][3]
built length: 12
```

Cost-based explanation:

1. `charAt(3)` retrieves only a single code unit; the character-summing loop must traverse six code units, making it an `O(n)` scan.
2. `indexOf("aba")` and `lastIndexOf("aba")` yield different positions; search time depends on the source and pattern content, not just the length of the returned value.
3. `regionMatches(2, pattern, 0, 3)` compares exactly three code units without requiring a substring to be created.
4. `substring(2, 5)` creates the content `"aba"`; `toCharArray()` creates a copy of six code units.
5. `unicode.length()` equals 3, yet it has 2 code points and 5 UTF-8 bytes.
6. `StringBuilder` joins four parts into 12 characters without needing to rebuild the prefix string after each `append`.

This is a **behavior-explaining example**. The output demonstrates correct values, **not directly runtime or Big-O**; evaluating actual performance requires methodical measurement.

## 9. Sorting Many Strings: Cumulative Comparison Cost

When sorting `q` strings using a comparator based on `String.compareTo`, a comparison-based sort typically requires around `O(q log q)` comparisons. However, **a single string comparison** may read up to `O(min(n_i, n_j))` code units. If all strings have maximum length `M`, a high-level estimate is typically **`O(q log q × M)`**, not merely `O(q log q)`. This is a bound under the common comparator-based model, not a claim that every dataset always reaches it.

For example, a list of codes with very long common prefixes will perform many more character reads than a list whose first characters differ widely, even with similar element counts and comparator call counts.

When comparing according to locale/Vietnamese linguistic semantics, `String.compareTo` is not equivalent to language-rule sorting; consider `Collator`. Generating sort keys or caching can improve certain workloads, but memory and key-creation costs must be accounted for.

## 10. Special Cases That Change Real-World Cost

### Empty Strings and Same-Reference Objects

Some methods have fast paths: `isEmpty()`, checking length before `equals`, or returning for an empty `substring`. Thus, an operation with `O(n)` worst case does not mean every call scans `n` characters.

### Compact Strings and How the JVM Stores Data

Modern OpenJDK/HotSpot features **Compact Strings** (JEP 254): if the content can be represented in Latin-1, the backing storage can use one byte per code unit; otherwise, it uses a UTF-16 representation. This affects memory consumption, memory bandwidth, and internal optimized branches. This is an **implementation detail**, does not change the meaning of `String.length()` or `String`'s Unicode contract, and should not be used to infer that every Java string always uses exactly one or two bytes per character (because of object headers, alignment, and other memory overhead).

### Temporary Memory and Garbage Collector Pressure

An algorithm that produces many substrings, `char[]` arrays, byte arrays, or intermediate strings can cause heavy allocation and GC, even when its asymptotic complexity matches an alternative. For instance, `s.substring(a, b).equals(target)` may both allocate a new slice and compare it; `s.regionMatches(a, target, 0, target.length())` avoids creating the intermediate slice when the goal is only checking.

The JIT can sometimes eliminate allocations via escape analysis when it proves an object does not escape, but that optimization depends on the JVM and workload; do not treat it as guaranteed in algorithm design.

### Cache, Unicode, and Data Characteristics

An ASCII-heavy string may execute differently from a string with many surrogates, even with the same number of code units. Data where a search pattern appears early often behaves differently from data without the pattern; comparing strings that differ at the first character differs from comparing strings with long shared prefixes. These variations affect real-world cost without contradicting worst-case Big-O.

## 11. Measuring Performance Properly

You should not run a few lines with `System.nanoTime()` once and conclude method A is always faster than B. On the JVM, you must account for JIT warmup, allocation/GC, CPU variability, data content, and the possibility that the JVM optimizes away unused results.

To measure reliably:

1. **Define the workload:** length `n`, pattern size `m`, character set, hit/miss ratio, and iteration count.
2. **Preserve semantic equivalence:** compare two approaches that produce the exact same result; avoid cases where one approach includes extra normalization/data-creation steps.
3. **Start the JVM and warm up sufficiently:** avoid measuring class loading/JIT compilation instead of the operation itself.
4. **Use JMH** (Java Microbenchmark Harness) for microbenchmarks, consuming results via JMH-supported mechanisms to prevent dead-code elimination.
5. **Measure throughput, latency, and allocation/GC as appropriate**; repeat across multiple input sizes to observe growth.
6. **Evaluate readability and real-world impact:** if an optimization only saves a few nanoseconds on a rare code path, it may not be worth the added code complexity.

A meaningful test is comparing joining 10, 100, and 10,000 parts with a `String +=` loop versus `StringBuilder` while keeping total content identical; or comparing `substring(...).equals(...)` with `regionMatches(...)` under the same true/false conditions. Avoid benchmarking constants that the compiler/JIT folds before measurement.

## 12. Common Analysis Mistakes

| Misconception | Correct analysis |
| --- | --- |
| “`length()` has `n` characters so it must be `O(n)`.” | The length is already stored; `length()` is typically `O(1)`. |
| “`charAt` is `O(1)`, so looping `n` times is still `O(1)`.” | Summing `n` calls yields `O(n)`. |
| “`equals` always checks the entire string.” | It can check reference/length or stop at an early mismatch; only long matching strings are linear worst case. |
| “`compareTo` takes time proportional to the longer string.” | It only needs to compare up to the common prefix through the end of the shorter string: `O(min(n,m))`. |
| “`indexOf(String)` is always `O(n)` like searching for one character.” | Longer patterns incur additional matching work; the underlying algorithm determines the worst case. |
| “`substring` is always `O(1)` and never copies.” | On modern OpenJDK, a distinct result slice typically requires copying proportional to length `k`. |
| “`+=` concatenation in a long loop is as cheap as a single append.” | Copying the accumulated prefix can lead to quadratic cost in the number of parts. |
| “`String.length()` is the number of Unicode characters or UTF-8 bytes.” | It is the number of UTF-16 code units. |
| “Reducing Big-O is enough to prove it is faster.” | Constants, allocation, GC, JIT, data, and small sizes can change the outcome; benchmark properly. |
| “There is a single fixed Big-O for every regex.” | Complexity depends on the expression, regex engine, and input. |

## 13. Self-Check Exercises

**Exercise 1.** Given `n` code units, each iteration calls `s.charAt(i)` once and only increments a counter. What are the time and auxiliary memory complexities?

**Answer:** `O(n)` time, `O(1)` auxiliary memory if no structure growing with `n` is created.

**Exercise 2.** Two strings both have length 100,000 and differ only at the first character. Must `equals` and `compareTo` compare all the way to the last character?

**Answer:** No. They can stop at the first differing position (after necessary checks). The linear worst case applies when they are identical or differ very late.

**Exercise 3.** Build 5,000 parts of 10 characters each using a `result += part` loop. How long is the final output, and why does the quadratic model matter?

**Answer:** The output is 50,000 code units long. If each concatenation creates a new result and copies the entire prefix, the total data copied is proportional to `10(1 + ... + 5000)`, growing quadratically with the number of parts.

**Exercise 4.** You only need to check whether a 20-character region at offset 100 of a large string equals a 20-character `target`. Which method avoids creating a substring?

**Answer:** `s.regionMatches(100, target, 0, 20)`. It compares the existing region directly, bounded by the region length.

**Exercise 5.** Searching for `'x'` in a string of length `n` that does not contain `'x'`. Which time case is this?

**Answer:** It typically has to scan the entire search range, so it is the `O(n)` case of `indexOf('x')`.

## 14. Choosing the Right Operation for Your Need

- **Reading a single position:** `charAt(i)`, near-constant cost; use `codePointAt` if you want a Unicode code point.
- **Checking a property across the whole string:** scan once, stopping as soon as the condition is decided; avoid redundant full-string scans.
- **Finding one character:** `indexOf(int)` or `lastIndexOf(int)`.
- **Finding a substring:** `indexOf(String)` / `contains`; consider pattern length and query count.
- **Checking a prefix/suffix/region:** `startsWith`, `endsWith`, `regionMatches` instead of creating a substring just to compare.
- **Comparing contents:** `equals` or `compareTo` with the right semantics; watch out for long shared prefixes.
- **Needing a data copy:** `substring`, `toCharArray`, `getBytes` with cost proportional to result size.
- **Joining multiple parts:** `StringBuilder`, `String.join`, or `Collectors.joining`; avoid incremental `+=` in large loops.

Remember: **the number of elements read, the number of re-reads, and the amount of data created** usually dominate the cost. Set the sizes `n, m, k, L` accurately, distinguish worst cases from early-exit paths, and measure on real data before deep optimization.

### References

- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java SE 17 — `StringBuilder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html).
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254).

