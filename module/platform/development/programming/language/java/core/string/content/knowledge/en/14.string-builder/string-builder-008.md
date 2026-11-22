# StringBuilder: ensureCapacity(), trimToSize(), and Memory Allocation Costs in Java

`StringBuilder` is a **mutable** character buffer for building text via `append`, `insert`, `delete`, `replace`, and `setLength`. Unlike immutable `String`, `StringBuilder` can reuse **already-allocated capacity** across many concatenation operations without creating an intermediate `String` object on every edit.

Two APIs that are especially important for managing memory and performance are:

- **`ensureCapacity(int minimumCapacity)`:** asks the builder to prepare at least the expected minimum capacity, reducing the number of buffer expansions during subsequent content additions.
- **`trimToSize()`:** asks to **attempt** shrinking excess buffer space after building or editing content finishes; this is a *best-effort* operation with no strict guarantee that `capacity()` will equal `length()`.

Understanding `length`, `capacity`, and the cost of **buffer expansion/copying** helps you choose the right approach instead of calling these two APIs mechanically everywhere.

## 1. length and capacity: Two Different Quantities

A `StringBuilder` has two concepts:

| Concept | API | Meaning |
|---|---|---|
| **Used length** | `length()` | Number of UTF-16 code units (**`char`**) currently in the builder's content |
| **Buffer capacity** | `capacity()` | Number of UTF-16 code units the builder can hold before needing to grow under the API model |

The invariant `capacity() >= length()` always holds. The difference `capacity() - length()` is **unused reserve capacity**. Capacity is neither the number of visible characters nor the number of bytes on the heap.

Example:

```java
StringBuilder sb = new StringBuilder(10);
sb.append("Java");

System.out.println(sb.length());   // 4
System.out.println(sb.capacity()); // 10
```

`new StringBuilder(10)` only sets the **initial capacity**; it **does not** pre-create ten characters, does not pad the string with spaces, and does not make `length()` equal 10. After appending `"Java"`, length is 4 and capacity remains 10.

### UTF-16 Units, Not Unicode Code Points

`length()` and `capacity()` are counted in **UTF-16 code units**. With a non-BMP emoji:

```java
StringBuilder emoji = new StringBuilder(2);
emoji.appendCodePoint(0x1F600); // U+1F600
System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
```

The emoji is represented by **two** code units (high surrogate + low surrogate), yet is only **one** code point. If estimating capacity from "user-perceived characters", sum the actual estimated UTF-16 units rather than assuming each emoji needs only one code unit.

## 2. Initial Capacity of StringBuilder

In Java 17, the common constructors have these meanings:

| Constructor | Meaning |
|---|---|
| `new StringBuilder()` | Empty builder, initial capacity **16** |
| `new StringBuilder(int capacity)` | Empty builder, initial capacity set to the specified integer |
| `new StringBuilder(String str)` | Initially contains all of `str`, initial capacity equals `str.length() + 16` |
| `new StringBuilder(CharSequence seq)` | Initially contains `seq`, with capacity equal to sequence length plus 16 per constructor contract |

Illustration:

```java
StringBuilder a = new StringBuilder();
StringBuilder b = new StringBuilder(32);
StringBuilder c = new StringBuilder("Java");

System.out.println(a.length());    // 0
System.out.println(a.capacity());  // 16
System.out.println(b.length());    // 0
System.out.println(b.capacity());  // 32
System.out.println(c.length());    // 4
System.out.println(c.capacity());  // 20
```

Notes:

- `new StringBuilder(0)` is valid: initially no spare capacity; the first append may have to expand.
- `new StringBuilder(-1)` throws `NegativeArraySizeException`, because the constructor cannot create a negative capacity.
- The `String`/`CharSequence` constructors already contain text and spare capacity; the `int` constructor **creates no content**.
- Spare capacity is managed internally; there is no need to fill dummy characters to "hold space".

**Do not confuse `capacity()` with RAM bytes.** Modern JDKs can use different memory representations for strings/builders (for example *compact strings* optimizations in HotSpot). Object overhead, internal arrays, encoding, alignment, and GC mean capacity in code units **does not translate directly into one exact byte formula across all JVMs**.

## 3. What Does ensureCapacity(minimumCapacity) Do?

Syntax:

```java
sb.ensureCapacity(minimumCapacity);
```

For a builder with current capacity `oldCapacity`:

1. If `minimumCapacity <= oldCapacity`, the requirement is already met, so no expansion is needed for this call.
2. If `minimumCapacity > oldCapacity`, the builder prepares capacity **at least equal to** `minimumCapacity`.
3. Actual capacity may be **larger than** the requested value due to internal growth policy.
4. Existing content, `length()`, and character order **do not change** merely from calling `ensureCapacity`.

Example:

```java
StringBuilder sb = new StringBuilder(4);
sb.append("ab");

sb.ensureCapacity(20);
System.out.println(sb.length());          // 2
System.out.println(sb.capacity() >= 20);  // true
System.out.println(sb.toString());        // ab
```

Do not assert `sb.capacity() == 20` across all cases and JVM versions. Application contracts should rely on **`>= minimumCapacity`**, not on an exact post-growth number.

### Common Growth Policy

In OpenJDK/HotSpot implementations, the new capacity is typically computed using an **exponential growth** strategy roughly like `oldCapacity * 2 + 2`, then ensuring it is not less than the minimum needed (with bounds/checks for huge arrays). For example, starting at capacity 16, a typical expansion might yield about 34 code units rather than exactly 17.

This is an **implementation detail**, not a formula for business logic. Other JVMs/versions may use different strategies; do not write tests checking `capacity() == 34` just because one JDK returns that value. When a stable contract is needed, rely only on `capacity >= demand`.

### Zero or Negative minimumCapacity

`ensureCapacity(0)` or a negative request allocates no extra capacity; it does not mean "shrink buffer". This differs from `new StringBuilder(-1)` — constructing with a negative capacity is invalid.

```java
StringBuilder sb = new StringBuilder(8);
sb.ensureCapacity(0);
sb.ensureCapacity(-5);
System.out.println(sb.capacity()); // 8
```

Do not use `ensureCapacity` to reduce memory. It serves only to **reserve capacity**, not to trim content or discard spare storage.

## 4. When Should You Call ensureCapacity?

When you know or can reasonably estimate the UTF-16 length to be built, pre-reserving capacity often reduces the number of internal array expansions.

Example joining a list of words with a delimiter:

```java
import java.util.List;

List<String> words = List.of("Java", "Core", "StringBuilder");

int estimated = 0;
for (String word : words) {
    estimated += word.length();
}
estimated += Math.max(0, words.size() - 1); // Spaces between words

StringBuilder out = new StringBuilder();
out.ensureCapacity(estimated);

for (int i = 0; i < words.size(); i++) {
    if (i > 0) {
        out.append(' ');
    }
    out.append(words.get(i));
}

System.out.println(out.toString()); // Java Core StringBuilder
```

This example is presented as a **code snippet used inside a method** with `java.util.List` imported, not a standalone program. If the list could contain `null` elements or the total length could exceed `Integer.MAX_VALUE`, define a policy and check for overflow before allocating.

For large or untrusted inputs, compute requirements using `long` and impose a reasonable limit per application needs; a bad estimate caused by integer overflow can lead to negative capacity, under-allocation, or exceeding memory budgets.

### You Can Use the Constructor to Reserve Upfront

If the demand is known at creation time, you can write:

```java
StringBuilder out = new StringBuilder(estimated);
```

instead of:

```java
StringBuilder out = new StringBuilder();
out.ensureCapacity(estimated);
```

Both prepare capacity. Passing the expected size to the constructor is usually more concise if you **have not created the builder yet**, and can avoid creating an initial buffer that is too small and immediately expanding it. `ensureCapacity` fits when the builder **already exists** and future demand grows, or when the estimate can only be made after reading more information.

**Do not overuse it:** if a builder only receives a few characters and the default capacity of 16 is already enough, `ensureCapacity` brings no measurable benefit; it only makes the code longer.

## 5. Allocation Cost as StringBuilder Grows

Distinguish two situations:

### Adding Content While Space Remains

When `length() + appendedUnits <= capacity()`, the builder can use its existing reserve. At the buffer level, there is no need to allocate a larger container **just because the old length was exceeded**.

Example:

```java
StringBuilder sb = new StringBuilder(8);
sb.append("abc"); // length 3, capacity 8
sb.append("de");  // length 5, capacity 8
```

The append still spends CPU to process data, and some APIs may perform auxiliary allocations; however, it does not need to **expand the main buffer** when capacity is sufficient.

### Adding Content Beyond Capacity

When new content no longer fits in the current capacity, the builder must obtain a sufficiently large internal storage region. In a typical implementation, this operation may involve:

1. Determining the new capacity.
2. Allocating a larger internal character/byte array.
3. Copying the old content to the new array.
4. Appending the new data into the remaining space.
5. Leaving the old array eligible for garbage collection once unreferenced.

Thus, a single expansion can cost **O(n)** in the amount of content copied at that moment, plus allocation/GC overhead. Exponential growth creates spare room specifically to **reduce the frequency** of repeating that expensive step.

### Why Does append Typically Have Good Amortized Cost?

If capacity grows by a factor greater than 1, expansions become progressively rarer as data grows. The total number of code units copied across multiple growth steps stays on the same order as the final total size under a geometric growth model. Consequently, when appending large amounts of content to a builder, total memory-management cost can be **amortized O(n)** in the output size (excluding special content processing), rather than copying the entire prefix on **every** append.

However:

- **A single append call is not guaranteed to be O(1)**, because it may trigger expansion and copying or append a very long string.
- **O(n)** is an amortized cost analysis under a specific model, not an exact execution time on every JVM.
- Reserving with `ensureCapacity` can reduce expansions, yet **does not make writing n characters O(1)**; data still must be copied into the result at some level.
- Over-allocating capacity wastes memory, increases allocation pressure, and can trigger `OutOfMemoryError` sooner.

### Compared to String Concatenation with + in a Loop

`String` is immutable. Code creating new strings by repeated concatenation **can** allocate and copy intermediate prefixes, making total work expensive, whereas `StringBuilder` can reuse its buffer. Therefore, for loops with many incremental appends, `StringBuilder` is usually the clear choice.

Still, do not assume every `"a" + x + y` expression creates many `String` objects: modern compilers/JVMs can optimize concatenation using `invokedynamic` or other strategies. Choose based on the structure of the work, then measure with a benchmarking tool (such as JMH) if performance truly matters.

## 6. trimToSize(): Only **Attempts** to Shrink Reserve Storage

Syntax:

```java
sb.trimToSize();
```

According to the `AbstractStringBuilder`/`StringBuilder` documentation, `trimToSize()` **attempts to reduce storage used**: if the internal backing array is larger than the actual character count, the implementation **may** shrink capacity. However, the API **does not guarantee** `capacity() == length()` after the call.

Points to remember:

- `trimToSize()` **does not delete or modify content**. `length()` stays unchanged.
- This operation **does not append** characters.
- If much unused space remains, the implementation may allocate a smaller container and copy the data there.
- If the JVM does not change capacity, that can still comply with the *best-effort* contract.
- There is no guarantee that calling `trimToSize` immediately returns heap memory to the OS. The lifecycle of the old array, GC, and actual memory allocation depend on the JVM.
- After shrinking, **the next append may have to expand again**, causing extra allocation and copying.

Example:

```java
StringBuilder sb = new StringBuilder(128);
sb.append("done");

int before = sb.capacity(); // 128
sb.trimToSize();

System.out.println(sb.toString());        // done
System.out.println(sb.length());          // 4
System.out.println(sb.capacity() >= 4);   // true
```

Do not write a JVM-portable test demanding `sb.capacity() == 4` after `trimToSize`. The API's primary purpose is **suggesting a reduction in spare memory**, not guaranteeing an exact number.

### When Is trimToSize Useful?

A fitting scenario: you have finished building a `StringBuilder` that will likely be retained for a **very long time** inside an application object; actual content is much smaller than the previously reserved capacity; and you want to **attempt** reducing its footprint before keeping the object long-term.

Example:

```java
StringBuilder cacheValue = new StringBuilder(10_000);
cacheValue.append("small result");
cacheValue.trimToSize(); // Request attempting to reduce spare space
```

If you only need the **final immutable string**, calling `toString()` and dropping the reference to `StringBuilder` usually makes more sense than keeping the builder just to call `trimToSize`. `toString()` yields a `String` representing the content at the moment of the call; the builder buffer and the resulting string are different concepts.

### Why Shouldn't You Call trimToSize After Every Append?

Suppose a builder repeatedly does:

```text
append -> trimToSize -> append -> trimToSize -> append -> ...
```

If each `trimToSize` actually shrinks the container close to the current length, the reserve disappears after every step. Each subsequent append may have to reallocate and re-copy, causing poor performance and extra GC. **Avoid a continuous shrink–expand cycle** if you still plan to add data.

Rule of thumb: **reserve before a growth phase**, and consider shrinking **only after growth ends and when memory savings genuinely matter**.

## 7. How trimToSize Differs from setLength, delete, and Clear

| API | Changes length? | Changes content? | Primary Effect on Capacity |
|---|---|---|---|
| `ensureCapacity(n)` | No | No | Ensures at least n when needed |
| `trimToSize()` | No | No | Attempts to reduce excess capacity; shrinking not guaranteed |
| `setLength(n)` | Yes | May truncate or pad with `\u0000` when growing | Not a "return memory" API; may expand if n is large |
| `delete(start, end)` | Yes | Deletes content in range | Not required to shrink capacity |
| `setLength(0)` | Yes, becomes 0 | Clears logical content | Usually **keeps capacity** for reuse |

Example:

```java
StringBuilder sb = new StringBuilder(64);
sb.append("abcdef");

sb.setLength(3);
System.out.println(sb.toString()); // abc
System.out.println(sb.capacity()); // 64

sb.setLength(0);
System.out.println(sb.length());   // 0
System.out.println(sb.capacity()); // 64
```

`setLength(0)` is useful for **reusing a builder** across multiple string constructions. If you subsequently append similar sizes, keeping capacity can be an advantage. Never call `trimToSize` to "clear content": that is **not** what this method means.

If `setLength(n)` increases length, the new positions are filled with `\u0000` (NUL) rather than ordinary spaces. Do not use increasing length to "reserve" capacity instead of `ensureCapacity`, because doing so actually alters the logical text.

## 8. Complete Java 17+ Program: Observing Invariants

The example intentionally prints only **values guaranteed by the API contract**, avoiding assumptions about exact capacity after growth or shrinking. Save to **`StringBuilderCapacityDemo.java`**:

```java
public class StringBuilderCapacityDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder(4);

        System.out.println("initial capacity: " + sb.capacity());

        sb.append("ab");
        System.out.println("after 2 chars: "
                + sb.length() + ", capacity=" + sb.capacity());

        sb.ensureCapacity(20);
        System.out.println("ensured >= 20: " + (sb.capacity() >= 20));

        sb.append("cd");
        System.out.println("after append: " + sb);

        sb.trimToSize();
        System.out.println("trim kept data: " + sb.toString().equals("abcd"));
        System.out.println("after trim >= length: "
                + (sb.capacity() >= sb.length()));

        sb.setLength(2);
        System.out.println("shortened: " + sb);

        StringBuilder emoji = new StringBuilder(2);
        emoji.appendCodePoint(0x1F600);
        System.out.println("emoji units: " + emoji.length());
        System.out.println("emoji codePoints: "
                + emoji.codePointCount(0, emoji.length()));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 StringBuilderCapacityDemo.java
java StringBuilderCapacityDemo
```

**Stdout:**

```text
initial capacity: 4
after 2 chars: 2, capacity=4
ensured >= 20: true
after append: abcd
trim kept data: true
after trim >= length: true
shortened: ab
emoji units: 2
emoji codePoints: 1
```

**Output explanation:**

1. Constructor `(4)` creates an empty builder with capacity 4.
2. `append("ab")` uses two UTF-16 code units within capacity 4, so capacity remains 4.
3. `ensureCapacity(20)` guarantees capacity **at least 20**; the boolean check is always `true` by contract.
4. `append("cd")` brings content to `"abcd"`, without needing to know the exact capacity.
5. `trimToSize()` may reduce capacity, yet **must not corrupt content**. `capacity() >= length()` always holds.
6. `setLength(2)` changes the **logical content** to `"ab"`.
7. `appendCodePoint(0x1F600)` adds a code point represented by two UTF-16 units, so `length() == 2` and `codePointCount(...) == 1`.

The example highlights writing resilient tests: checking **invariants guaranteed by the API**, rather than hardcoding optimization details of one JVM version.

## 9. Measuring and Estimating Memory Costs Properly

Suppose you plan to join n strings `parts[i]` with total UTF-16 units:

\[
L = \sum_{i=0}^{n-1} \mathrm{parts}[i].\mathrm{length}()
\]

If adding `n - 1` single-code-unit delimiters, the expected capacity is:

\[
C = L + \max(0, n-1)
\]

This is an estimate of **UTF-16 unit count**, not heap bytes. For multi-character delimiters, add `delimiter.length() * (n-1)`. If any transformation step increases or decreases length, adjust the estimate accordingly.

In code handling large inputs, avoid `int` overflow when summing and set a limit to reject over-budget inputs:

```java
long needed = 0;
for (String part : parts) {
    needed += part.length();
}
if (needed > 1_000_000L) {
    throw new IllegalArgumentException("Text too large");
}

StringBuilder sb = new StringBuilder((int) needed);
```

This is an **illustrative snippet**; it assumes `parts` is a non-null collection of strings and excludes delimiters. In a real application, add delimiter costs and limits based on business rules. With `long` variables, avoid overflow if data could be huge, though application limits usually rule out that case earlier.

### Practical Factors to Measure

- **Expansion count**: repeated capacity increases cause extra allocations and copies.
- **Spare capacity vs. actual data**: large lingering empty space can waste heap if the builder is long-lived.
- **Builder lifecycle**: short-lived allocate-and-discard differs from keeping builders in caches or long-lived objects.
- **Number of `toString()` calls**: creating an independent `String` copy has a cost; calling repeatedly without modifying content can increase allocations depending on JVM optimizations.
- **Character data type**: Latin-1 vs. Unicode text may have different byte representations on JVMs with compact strings.
- **Garbage collector and heap settings**: affect observed latency, throughput, and footprint.

If performance optimization is a real requirement, measure with a profiler and proper microbenchmark (commonly JMH). Do not draw conclusions from a few `System.nanoTime()` calls before the JVM warms up.

## 10. Situational Choices

| Context | Usually Appropriate Approach | Reason |
|---|---|---|
| Short string joining just a few values | Clear `+` operator | Compiler/JVM can optimize well; readable code |
| Loop appending many parts | `StringBuilder` | Reuses buffer instead of creating many intermediate strings |
| Total length known fairly accurately upfront | `new StringBuilder(estimated)` | Reserves upfront from the start |
| Existing builder about to receive lots of data | `ensureCapacity(neededTotal)` | Reduces risk of repeated expansions |
| Finished builder kept long-term with huge excess capacity | Consider `trimToSize()` | Attempts to reduce footprint |
| Builder only a temporary tool to produce a `String` | `toString()` then discard builder | No need to maintain spare buffer |
| Reusing a builder across independent rounds | `setLength(0)` | Clears logical content, usually keeps capacity for reuse |
| Multiple threads needing the same buffer | Clear synchronization/ownership design; consider `StringBuffer` if appropriate | `StringBuilder` **does not** synchronize operations |

Do not treat the table as an absolute rule. If inputs vary widely in length, preallocating for a rare maximum case can leave many builders wasting memory. Good estimation based on actual data distribution usually works better than setting a huge capacity "just to be safe".

## 11. Common Mistakes

| Misconception / Mistake | Consequence | Correct Practice |
|---|---|---|
| "`new StringBuilder(100)` has length 100" | Confuses capacity with content | New builder is empty, `length() == 0` |
| "`ensureCapacity(100)` makes length 100" | No new characters are added | Use `append` to add content |
| "`ensureCapacity` always sets capacity to the exact requested number" | Growth policy may allocate more | Rely only on `capacity() >= minimumCapacity` |
| "`ensureCapacity` reduces capacity when passed a small number" | Fails to reduce memory | `ensureCapacity` only reserves; consider `trimToSize` |
| "`trimToSize` always makes capacity == length" | Implementation-dependent | The API is *best-effort* |
| "`trimToSize` deletes trailing content" | Actually changes neither characters nor length | Use `setLength`/`delete` to remove content |
| "`setLength(0)` definitely returns RAM" | Usually keeps the allocated buffer | Only length resets to 0 |
| Calling `trimToSize` after **every** append | Can cause shrink–expand churn, increasing allocations/copies | Consider only after building finishes and if builder lives long |
| Estimating by emoji count instead of UTF-16 units | Capacity falls short of actual need | Use `String.length()` or `Character.charCount(cp)` |
| "Capacity 100 means 200 bytes of RAM" | Ignores compact strings, overhead, alignment, JVM | Measure in practice; do not apply a rigid byte formula |
| `int` estimate overflows | Wrong capacity or allocation error | Sum in `long`, bound input, then cast |
| Assuming every `append` is always O(1) | May copy buffer or append large data | Understand amortized cost and appended data length |

## 12. Self-Check Exercises

### Exercise 1 — Length and Capacity

```java
StringBuilder b = new StringBuilder(8);
b.append("abc");
b.ensureCapacity(20);
```

Question: What are `b.length()` and the guaranteed condition on `b.capacity()`?

**Answer:** `length() == 3`; `capacity() >= 20`. You cannot conclude capacity equals exactly 20 across all implementations.

### Exercise 2 — Trimming

```java
StringBuilder b = new StringBuilder(100);
b.append("xyz");
b.trimToSize();
```

Question: What is guaranteed unchanged and what may change?

**Answer:** content `"xyz"` and `length() == 3` remain unchanged. `capacity` may decrease if the implementation shrinks it, but the API does not require it to equal 3.

### Exercise 3 — Buffer Reuse

```java
StringBuilder b = new StringBuilder(32);
b.append("First");
b.setLength(0);
b.append("Next");
```

**Answer:** final content is `"Next"`, length is 4; `setLength(0)` does not discard reserved capacity. Reuse is often beneficial when strings are rebuilt repeatedly.

### Exercise 4 — Unicode

A string has 10 non-BMP emojis, each represented by a surrogate pair. How many UTF-16 code units do the emojis alone require?

**Answer:** 20 code units (2 per emoji). Total capacity must also account for other characters and delimiters.

### Exercise 5 — Cost

You are building several strings, each tens of thousands of characters long. After **every** `append`, the code calls `trimToSize`. Why might this be slow even though you wanted to save memory?

**Answer:** after shrinking the reserve buffer, the next append can force allocating a larger array and copying the data again. Repeatedly shrinking and expanding increases total allocation/GC and copy overhead. It is better to reserve according to need and only consider shrinking after building finishes **if the builder is kept long-term**.

## 13. Official References

- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): constructors, `capacity`, `length`, `ensureCapacity`, `trimToSize`, `setLength`, and `appendCodePoint`.
- [Java SE 17 — StringBuilder.ensureCapacity(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#ensureCapacity(int)): minimum capacity guarantee and growth mechanism.
- [Java SE 17 — StringBuilder.trimToSize()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#trimToSize()): the *attempts to reduce storage* contract.
- [Java SE 17 — Character.charCount(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#charCount(int)): number of UTF-16 units used for a Unicode code point.

**Key takeaway:** `length()` is the number of UTF-16 code units **currently present**, while `capacity()` is how many can be held **before expanding**. `ensureCapacity(n)` prepares at least `n` code units without altering content; `trimToSize()` only **attempts** to discard excess reserve after building. Reasonable pre-allocation reduces reallocations, whereas excessive pre-allocation or repeated shrink–expand cycles waste memory and CPU.
