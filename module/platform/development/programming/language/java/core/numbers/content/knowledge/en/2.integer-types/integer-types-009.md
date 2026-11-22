# Choosing `int` or `long` for Counts, Indices, and Sizes in Java

In Java, when working with **element counts**, **access indices**, or **data sizes**, the question to answer is not merely “is this number big?”. You need to know **the maximum possible value range**, **intermediate calculations**, and **the types required by Java APIs**. An array is always indexed with `int`, whereas the total number of elements processed across many arrays or a file's size may require `long`. Choosing the right type keeps results accurate, bounds explicitly checked, and APIs easy to use.

## 1. Practical Limits of Both Types

| Property | `int` | `long` |
| --- | --- | --- |
| Bit width | 32-bit, signed | 64-bit, signed |
| Minimum value | −2,147,483,648 | −9,223,372,036,854,775,808 |
| Maximum value | 2,147,483,647 | 9,223,372,036,854,775,807 |
| Bound constants | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | `Long.MIN_VALUE`, `Long.MAX_VALUE` |
| Literal | `100` (defaults to `int`) | `100L` (`L` suffix) |
| Suitable examples | Array/list indices, counts with a moderate 32-bit upper bound | Large cumulative sums, byte offsets, file sizes, large durations/lengths when APIs use `long` |

Both are **signed** primitive types. In counting and sizing problems, usually only non-negative values are allowed, but not using the negative range **does not automatically turn `int` into an unsigned 32-bit type**. The positive limit of `int` remains `2_147_483_647`, not `4_294_967_295`.

`long` has a larger range than `int`, yet is **still finite**. In both types, ordinary `+`, `-`, and `*` operations can overflow without throwing an exception. `long` does not magically solve calculations exceeding `Long.MAX_VALUE`.

**First principle:** determine the maximum value **of each variable and intermediate result**, then pick a type that fits the range; when depending on a specific API, respect the parameter/return types of that API.

## 2. Choosing by Meaning: index, count, size, offset

Four common terms are not completely synonymous:

- **Index:** an access position within a structure, usually in `0..size-1`.
- **Count:** the number of occurrences, records, or objects processed; may accumulate across multiple batches or sources.
- **Size/length:** the number of elements in a collection, bytes in a file, or other measurement units; the **unit** must be specified.
- **Offset:** a relative position from the start of data; an offset within an array can be `int`, whereas an offset within a multi-gigabyte file requires `long`.

For example, when sequentially processing 500 files, each containing 10 million records: each file can read individual elements with `int`, but the **total of 5 billion records** exceeds `Integer.MAX_VALUE` and should be accumulated in `long`.

### Decision Table by API and Value Range

| Situation | Type to Use | Why |
| --- | --- | --- |
| `array[index]`, `for` loop over an array | `int` for `index` | Java requires an `int`-compatible array index; `array.length` returns `int` |
| `List.get(index)`, `List.size()` | `int` for API index/size | API signatures `get(int)` and `size()` |
| Element count of a small structure with a clear upper bound fitting `int` | `int` | Concise, matches the required range |
| Total element count across multiple lists, batches, or files | `long` | The total can exceed the size of any single list |
| `Stream.count()`, `Files.size(path)` | `long` | API returns `long` |
| Byte offset in a large file, number of bytes read/written | `long` | Byte offsets can exceed 2 GiB |
| Quantities beyond `Long.MAX_VALUE` or huge combinatorial calculations | `BigInteger` | Exceeds `long` capacity |
| Counter updated concurrently by multiple threads | `AtomicInteger`/`AtomicLong` or `LongAdder` per range and requirements | Concurrency must be handled separately; changing the type alone does not create atomicity |

Note that `Collection.size()` has return type `int`. The `Collection` contract permits returning `Integer.MAX_VALUE` when it contains more than that limit; thus `size()` **is not a general-purpose API for accurately measuring arbitrarily huge collections**. Most standard Java arrays and collections already have their own capacity constraints based on implementation or memory.

## 3. Array and `List` Indices: Use `int` Because of the API Contract

```java
int[] prices = {120, 240, 360};

for (int i = 0; i < prices.length; i++) {
    System.out.println("prices[" + i + "] = " + prices[i]);
}
```

The variable `i` is `int` because `prices.length` has type `int` and array access uses an integer index compatible with `int`. `List.get(int index)` also uses `int`.

You cannot use `long` directly as an array index:

```java
int[] values = {5, 10};
long index = 1L;
// int value = values[index]; // Does not compile: long is not a valid array index type.
int value = values[Math.toIntExact(index)]; // Valid when index fits within the int range.
```

`Math.toIntExact` only checks whether `long` fits in the `int` range; **it does not check whether the index is valid for the array**. You still need `0 <= index && index < values.length` before accessing. If `index` is 100 while the array has 2 elements, the type conversion succeeds but the access still throws `ArrayIndexOutOfBoundsException`.

A Java array does not gain more than 2 billion indices just because an index variable is changed to `long`. `array.length` has type `int`; usable array size is further bounded by the JVM implementation, memory, and overhead. If data needs more elements than can fit in one array, consider **segmentation**, streaming/batch processing, disk storage, or a specialized structure with a `long`-indexed API.

### Loops and Safe Bounds

The following standard form is valid for arrays, even when empty:

```java
for (int i = 0; i < array.length; i++) {
    use(array[i]); // use(...) is only an illustrative call, not a standalone program.
}
```

The condition `i < array.length` terminates before the index goes out of bounds. Avoid `i <= array.length` because the last element has index `length - 1`. When `array.length == 0`, there is no valid index; `length - 1` is `-1` and must not be used for access.

Do not write loops ending at `Integer.MAX_VALUE` with the condition `i <= Integer.MAX_VALUE` and `i++`: after the maximum value, `int` overflows to a negative number and can make the loop run forever. If you genuinely need to iterate a counter beyond the `int` range, use `long` and define the stopping condition clearly.

## 4. Total Counts and Sizes May Need `long` Even When Inputs Are `int`

A batch of 10,000 elements can use `int batchSize`. Yet summing element counts across 500,000 batches can exceed `int`. Check the type **of the addition itself**, not just the type of the receiving variable.

### Mistake: Assigning to `long` After Overflow Has Already Occurred

```java
int previous = 2_000_000_000;
int incoming = 500_000_000;

long wrong = previous + incoming;         // -1794967296: int addition first.
long correct = (long) previous + incoming; // 2500000000: long addition.
```

The expression `previous + incoming` has type `int`, so the addition overflows **before** being assigned to `long`. Cast at least one operand to `long` upfront; when a counter needs to accumulate repeatedly, declare the accumulator variable as `long` and add directly:

```java
long totalRecords = 0;
for (int batchRecords : new int[] {1_500_000_000, 1_500_000_000}) {
    totalRecords += batchRecords;
}
// totalRecords = 3000000000
```

`totalRecords += batchRecords` uses `long` addition because the left-hand operand is `long`. To detect overflow of `long` itself rather than accepting wraparound, use `Math.addExact(totalRecords, batchRecords)`.

### Similar Mistake When Multiplying Sizes

```java
int rows = 70_000;
int columns = 70_000;

long wrongCells = rows * columns;             // 605032704: int overflowed.
long correctCells = (long) rows * columns;    // 4900000000.
long checkedCells = Math.multiplyExact((long) rows, columns);
```

When computing capacities, `rows * columns`, `itemCount * bytesPerItem`, and `width * height * channels` all require checking **intermediate results**. For instance, if `width` and `height` are `int`, the expression `(long) (width * height)` is still too late. If a result computed in `long` still risks exceeding bounds, use `Math.multiplyExact(long, long)` or an appropriate `BigInteger` model.

## 5. Converting Between `long` and `int` at API Boundaries

The widening conversion `int -> long` preserves every `int` value. Java performs it implicitly:

```java
int count = 1_000_000;
long total = count; // No data loss.
```

Conversely, the narrowing conversion `long -> int` **can lose data**. Java requires an explicit cast and keeps only the low 32 bits of the `long` value; the result can be negative or much smaller:

```java
long size = 3_000_000_000L;
int silentlyWrong = (int) size;
System.out.println(silentlyWrong); // -1294967296
```

Use `Math.toIntExact(long)` when an API requires `int` and the value must be checked:

```java
long fileBytes = 3_000_000_000L;
try {
    int bytesAsInt = Math.toIntExact(fileBytes);
    System.out.println(bytesAsInt);
} catch (ArithmeticException ex) {
    System.out.println("Size does not fit int");
}
```

`Math.toIntExact` throws `ArithmeticException` if outside the `int` range. This method **does not check** whether the size is non-negative, fits in available memory, or lies within the bounds of a specific array/list.

If the source is a large file size while an operation processes `int` elements at a time, the right approach is usually to **split into multiple chunks** of a valid `int` size rather than forcing the entire size down to `int`. For example, use a `long remainingBytes` variable to track total remaining bytes, while reading one buffer at a time with `int chunkSize`.

## 6. Java API Return Types Help Guide the Decision

### APIs That Usually Return `int`

- `array.length`: number of array elements.
- `String.length()`: number of **UTF-16 code units**, not identical to user-perceived characters.
- `List.size()`, `Collection.size()`, `Map.size()`: count per API contract, type `int`.
- `List.get(int)`, `String.charAt(int)`: `int` index parameter.

### APIs That Usually Return `long`

- `java.nio.file.Files.size(Path)`: file size in bytes.
- `java.io.File.length()`: length in bytes per `File` contract.
- `java.util.stream.Stream.count()`: number of elements in the stream; return type is `long`.
- `java.nio.channels.SeekableByteChannel.position()` and `size()`: position/size in bytes as `long`.

Do not change an API's return type just because “data is usually small”. If `Files.size(path)` returns `long`, keep the value in `long` until a real API boundary requires another type.

Example:

```java
// API usage example (not a standalone program):
long bytes = java.nio.file.Files.size(path); // path is an already-created Path.
long matches = records.stream().filter(record -> matchesRule(record)).count();
// records/matchesRule are defined in the application.
```

The `Files.size` line can throw `IOException` and needs appropriate handling. `Stream.count()` returns `long` even when the stream has only a few elements. Do not confuse the number of **elements** in a stream with the total **bytes** or total **size** of those elements.

## 7. Performance and Memory: Do Not Default to `long` for Everything

For arrays of primitive values, each `int` element holds 32 bits while `long` holds 64 bits; a `long[]` array usually requires roughly twice as much storage for **elements** as an `int[]` of the same length. Object layout, padding, headers, and actual memory organization are decided by the JVM, so do not deduce total RAM simply by multiplying by 4 or 8 bytes.

Choosing `int` for array/list indices matches the APIs, avoids constant casting, and makes the range clear. Choosing `long` for large totals/capacities prevents overflow. Do not pick `int` just to save a few bytes when the upper bound can exceed 2.1 billion; nor should you use `long` to index APIs that only support `int`.

With `Integer` and `Long` (wrappers), beyond the value range there are also **boxing, unboxing, `null`, and object identity**. Do not compare two wrappers with `==` to check whether they have the same numeric value; when comparing values, use `equals` or convert to primitives with `null` handling.

### Counters in Multithreaded Environments

Both `count++` on `int` and `long` fail to guarantee atomic increments when multiple threads modify them concurrently. Depending on the case, use `AtomicInteger`, `AtomicLong`, `LongAdder`, or synchronization. Choose `AtomicLong` when the value range needs `long` and clear atomic operations are required; `LongAdder` often suits high-frequency contended counters, though `sum()` is not an atomic snapshot during concurrent updates. They **do not automatically detect overflow**: you still need a bounds policy.

## 8. Complete Java 17+ Example

The following program shows combining `int` for indices and `long` for total counts, along with detecting unsafe narrowing conversions.

Create the file `IntOrLongDemo.java`:

```java
import java.util.List;

public class IntOrLongDemo {
    public static void main(String[] args) {
        int[] samples = {5, 10, 15};
        long total = 0;

        for (int i = 0; i < samples.length; i++) {
            total += samples[i];
        }
        System.out.println("Array length: " + samples.length);
        System.out.println("Array sum: " + total);

        int previous = 2_000_000_000;
        int incoming = 500_000_000;
        long wrong = previous + incoming;
        long correct = (long) previous + incoming;
        System.out.println("Overflow before widening: " + wrong);
        System.out.println("Widen before adding: " + correct);

        int rows = 70_000;
        int columns = 70_000;
        long cells = Math.multiplyExact((long) rows, columns);
        System.out.println("Grid cells: " + cells);

        List<String> words = List.of("Java", "int", "long");
        System.out.println("List size: " + words.size());
        System.out.println("Stream count: " + words.stream().count());

        long requestedIndex = 2L;
        int index = Math.toIntExact(requestedIndex);
        if (index >= 0 && index < samples.length) {
            System.out.println("Sample at index 2: " + samples[index]);
        }

        try {
            Math.toIntExact(3_000_000_000L);
            System.out.println("Unexpected: conversion succeeded");
        } catch (ArithmeticException ex) {
            System.out.println("Long value does not fit int");
        }
    }
}
```

Compile and run:

```bash
javac IntOrLongDemo.java
java IntOrLongDemo
```

Exact output:

```text
Array length: 3
Array sum: 30
Overflow before widening: -1794967296
Widen before adding: 2500000000
Grid cells: 4900000000
List size: 3
Stream count: 3
Sample at index 2: 15
Long value does not fit int
```

Explanation: `samples.length` and `index` use `int` to access the array; `total` is `long` to accumulate more safely as the sum grows large. `wrong` shows that assigning an overflowed result to `long` does not fix the bug. `Math.multiplyExact` detects multiplication overflow if the result exceeds `long` capacity; `Math.toIntExact` prevents silent narrowing.

## 9. Selection Workflow in Projects

1. **Identify the quantity and unit:** number of elements, cumulative record count, byte count, duration, or index? Do not use vague variable names like `size` when measuring different units; choose `fileSizeBytes`, `totalRecords`, `recordIndex`.
2. **Estimate upper bounds of values and intermediate expressions:** per-batch counts may be small, yet sums or products can be huge. For external input, validate upper bounds rather than assuming “it will never be big”.
3. **Confirm the API contract:** array indices and `List.get` require `int`; `Files.size` and `Stream.count` return `long`. Keep the API's native type whenever possible.
4. **Choose storage and computation types:** `int` for indices in structures supporting `int` indexing; `long` for totals or offsets that can exceed `int`. Cast an operand to `long` **before** addition/multiplication when needed.
5. **Place checked conversion boundaries:** use `Math.toIntExact`, non-negative checks, `index < length` checks, or chunking; use `Math.addExact`/`multiplyExact` if overflow is a business error.
6. **Verify under data growth or multithreading:** choose primitives, atomic counters, or `BigInteger` based on range, concurrency, and atomicity requirements; test values near `Integer.MAX_VALUE` and `Long.MAX_VALUE`.

### Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `long total = intA + intB;` | Addition already overflowed before assignment | `long total = (long) intA + intB;` |
| `long bytes = intCount * intBytesPerItem;` | Multiplication runs in `int` | `Math.multiplyExact((long) intCount, intBytesPerItem)` |
| `(int) fileSizeBytes` | Truncates bits, result can be negative | Keep `long`, split into chunks; only use `Math.toIntExact` when sure it fits |
| Using `long` directly for `array[index]` | Does not compile | Use `int` and check index bounds |
| Treating `array.length` as RAM or byte size | Confuses element count with bytes | Specify unit clearly; compute bytes checking overflow and overhead |
| Using `<= array.length` | Accesses index equal to length, out of bounds | Use `< array.length` |
| Using `int` for cumulative records over a long period | Can overflow even if each batch is small | Use `long`/check with `addExact` |
| Using `long` expecting normal arrays/lists to hold arbitrarily huge data | APIs and memory still impose limits | Segment, stream, or store off-heap/on-disk |

## 10. Self-Check Questions

- A `List` currently has 500,000 elements, yet you need to compute the total number of elements processed over several years. Which types should be used for `listIndex` and `totalProcessed`? Why?
- With `int rows = 70_000`, `int cols = 70_000`, what is the difference between `long total = rows * cols` and `long total = (long) rows * cols`?
- Why does `Math.toIntExact(longIndex)` not yet guarantee `array[index]` is safe?
- When `Files.size(path)` returns 5,000,000,000 bytes, should you cast it to `int` to allocate a single buffer? If not, how should you process it incrementally?
- In a multithreaded task, does changing `int` to `long` prevent race conditions? When should you use `AtomicLong` or `LongAdder`?

**Practical conclusion:** use `int` when the value range is bounded and access APIs require `int`; use `long` when totals, sizes, or offsets can exceed the `int` range. Always check **the type of the operation before assignment**, validate data bounds, and convert safely between the two types at API boundaries.
