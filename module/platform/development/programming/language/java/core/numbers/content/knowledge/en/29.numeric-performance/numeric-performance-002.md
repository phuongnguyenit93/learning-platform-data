# Boxing in Java Collections, Streams, and Loops

## 1. Understanding the Performance Problem Correctly

Java has two common groups of numeric types:

- **Primitive:** `byte`, `short`, `int`, `long`, `float`, `double`. A primitive variable directly holds a value of its corresponding type; for example, `int count = 42;`.
- **Wrapper (reference type):** `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`. For example, `Integer count = 42;` stores a reference to an object representing the numeric value.

**Boxing** is converting a primitive into a wrapper, such as `int` → `Integer`. **Unboxing** is converting a wrapper into a primitive, such as `Integer` → `int`. Java supports **autoboxing/unboxing** so the compiler inserts these conversions where syntax permits:

~~~java
int primitive = 42;
Integer boxed = primitive; // boxing, equivalent to Integer.valueOf(primitive)
int again = boxed;         // unboxing, equivalent to boxed.intValue()
~~~

Shorthand syntax does not make the two types one and the same. A wrapper is still a reference object, can hold `null` when used via a reference variable, carries storage/management overhead, and can create additional objects. In return, wrappers can be used in generic APIs such as `List<Integer>`, `Map<Integer, Long>`, or places where `null` is needed to represent absence.

The topic **"Boxing in Collections, Streams, and Loops"** focuses on both **correctness** and **performance**: where boxing occurs, its impact when element counts are large, and when to use `int[]`, `IntStream`, `LongStream`, or `DoubleStream`.

Not every boxing operation always allocates a new object. `Integer.valueOf` caches commonly used values; the JIT can optimize away some allocations via escape analysis. Therefore, the accurate statement is that **boxing can incur extra work, references, and allocation/GC**, while the actual cost must be measured on the target workload.

## 2. How Does Boxing/Unboxing Happen?

### 2.1. Automatic conversions in assignments and expressions

~~~java
Integer a = 10; // autobox: Integer.valueOf(10)
int b = a;      // unbox: a.intValue()

Integer sum = a + 5;
// unbox a to int -> add 5 -> box result to Integer

int next = a + 1;
// unbox a, primitive addition, assign to int: no need to box result
~~~

The comments describe the **conversion semantics**, not a claim that the virtual machine must allocate a separate object for every boxing operation. `Integer.valueOf(int)` is guaranteed by Java to cache at least values from `-128` to `127`; values outside this range may be cached more broadly depending on the JVM/configuration. You should not infer speed simply because an example like `10` falls within the cache.

### 2.2. Unboxing null throws NullPointerException

~~~java
Integer missing = null;
int n = missing; // NullPointerException at unboxing site
~~~

There is no `int` value representing `null`. Arithmetic operations can also implicitly unbox and fail:

~~~java
Integer count = null;
// int doubled = count * 2; // Throws NullPointerException
~~~

For instance, when you need to distinguish "no value" from `0`, decide on the policy before converting types: reject null, keep wrapper/`OptionalInt` at the boundary, or use an intentional default value. Do not silently turn every null into 0 if the two states have different meanings.

### 2.3. Comparing wrappers by value, not by identity

~~~java
Integer a = Integer.valueOf(127);
Integer b = Integer.valueOf(127);

System.out.println(a == b); // true: valueOf caches value 127
System.out.println(a.equals(b)); // true: same numeric value
~~~

`==` between two `Integer` variables checks **same object reference**, not numeric equality. For values not guaranteed to be cached, such as `1000`, the result of `==` is not a contract for checking equality. Use `a.equals(b)` if `a` is guaranteed non-null, or `Objects.equals(a, b)` when null is possible.

You must also distinguish the case where one side is `int`:

~~~java
Integer wrapped = 1000;
int primitive = 1000;
boolean same = wrapped == primitive; // true: wrapped is unboxed before comparison
~~~

When `wrapped == null`, the expression `wrapped == primitive` can throw `NullPointerException` due to unboxing. Do not use `==` for wrappers just because you have seen an example return `true`.

## 3. Collections: `List<Integer>` Is Not `int[]`

### 3.1. Generic collections require reference types

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>();
numbers.add(1);  // 1 is boxed when passed to add(Integer)
numbers.add(2);
int first = numbers.get(0); // retrieves Integer then unboxes
~~~

The syntax `List<int>` is **invalid** in Java 17: a generic type argument must be a reference type. Even when a list contains only numbers, `List<Integer>` still manages elements as references to wrappers. `ArrayList<Integer>` has an internal array of references, unlike `int[]`, which is an array of primitive values.

This has consequences:

- With `int[]`, each position directly contains an `int`; there is no `Integer` per element.
- With `ArrayList<Integer>`, positions hold references. Wrapper objects can bring memory overhead, reference dereferencing, and GC pressure, especially when many values fall outside the cache.
- `List<Integer>` can contain `null` (if the list implementation allows it), whereas `int[]` cannot.
- `List<Integer>` provides a convenient collection API: resizing, generic operations, and library interoperability; `int[]` has a fixed size and uses array operations.

You should not claim that every `ArrayList<Integer>` always uses an exact number of bytes per element: reference/object sizes depend on the JVM, pointer size, object alignment, and runtime optimizations. However, the **reference vs. primitive** structure is a fundamental difference.

### 3.2. `List.of`, `Arrays.asList`, and boxing cost

~~~java
List<Integer> fixedSize = java.util.Arrays.asList(1, 2, 3);
List<Integer> immutable = List.of(1, 2, 3);
~~~

Integer literals are boxed to become `Integer` elements in the list. `Arrays.asList` returns a fixed-size list backed by an array and **allows null values**; `List.of` creates an unmodifiable list and **disallows null**. Both are `List<Integer>` and do not turn into `int[]` just because the elements are numbers.

If primitive array processing is needed:

~~~java
int[] values = {1, 2, 3};
int first = values[0]; // no boxing
~~~

When data consists of millions of integers and is primarily used for sums/statistics, consider storing/reading it in primitive form. When data originates from a generic API, converting it to a primitive array also requires **unboxing each element once**; you cannot eliminate the wrapper storage cost that already occurred beforehand with a single stream call.

### 3.3. `Map` with numeric keys/values

~~~java
Map<Integer, Integer> counts = new java.util.HashMap<>();

counts.merge(7, 1, Integer::sum);
counts.merge(7, 1, Integer::sum);
// counts.get(7) -> Integer with value 2
~~~

In `Map<Integer, Integer>`, both key and value are wrappers. In `Integer::sum`, the two `Integer` values are unboxed for primitive addition and the result is boxed back according to the `BiFunction` signature required by `merge`. With frequent updates in a hot loop, managing wrappers can become a noticeable cost.

Do not automatically replace every map with an array because of this: an `int[] counts` array is only suitable when the key domain is small, contiguous, and maps directly to indices. For sparse keys, large domains, or complex collection features, `Map` is usually the right design choice. Evaluate memory, speed, simplicity, and API requirements before optimizing.

## 4. Boxing in Loops

### 4.1. Primitive loops avoid boxing on the counter variable

~~~java
int sum = 0;
for (int i = 0; i < 1_000; i++) {
    sum += i; // uses only int in this operation
}
~~~

Conversely:

~~~java
Integer sum = 0;
for (Integer i = 0; i < 1_000; i++) {
    sum += i;
}
~~~

The second loop performs many implicit conversions: the condition `i < 1000` must unbox, the step `i++` must unbox/increment/box, and `sum += i` must unbox both operands and then box the result back into `sum`. Those conversions are unnecessary if the goal is simply integer arithmetic.

Some objects may be optimized by the JIT and small values may come from the cache, so do not conclude "every iteration always creates exactly three new objects". Still, primitive code expresses intent more clearly and avoids offloading optimization of the entire operation onto the compiler/runtime.

### 4.2. Enhanced for on `List<Integer>`

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int total = 0;
for (Integer item : values) {
    total += item; // item is unboxed for addition
}
~~~

Elements retrieved from the list are `Integer`; even though the accumulator `total` is `int`, `item` must still be unboxed during addition. You can write `for (int item : values)` so unboxing occurs upon loop variable assignment, but this **does not remove** the wrapper elements inside the list.

In an enhanced for loop over a primitive array:

~~~java
int[] values = {1, 2, 3, 4};
int total = 0;

for (int item : values) {
    total += item; // no boxing/unboxing
}
~~~

With `List<Integer>`, Java generally uses the `Iterator<Integer>` mechanism for enhanced for; iterator overhead and collection operations are separate factors beyond boxing. With `int[]`, enhanced for traverses array elements directly. Do not equate loop overhead solely with boxing: bounds checks, branches, data layout, CPU cache, and JIT optimizations can all play a role.

### 4.3. Null in a list causes errors when summing

~~~java
List<Integer> values = java.util.Arrays.asList(1, null, 3);

int total = 0;
for (Integer item : values) {
    total += item; // NPE when reaching the null element
}
~~~

If null needs to be skipped, state so explicitly:

~~~java
int total = 0;
for (Integer item : values) {
    if (item != null) {
        total += item;
    }
}
~~~

If null is invalid data, validate and reject it instead of skipping it, to avoid silently altering the sum.

## 5. `Stream<Integer>` and `IntStream`: A Crucial Difference

### 5.1. Generic `Stream` holds wrappers

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 10
~~~

`values.stream()` has type `Stream<Integer>`. Each element is still an `Integer` from the collection. `mapToInt(Integer::intValue)` **unboxes** the values into a primitive stream `IntStream`. After this step, specialized operations like `sum()` operate on the primitive interface and do not need to re-box each value just to add them.

Why not write:

~~~java
Integer total = values.stream().reduce(0, Integer::sum);
~~~

Calling `reduce` on `Stream<Integer>` is valid, but updates to the accumulated value operate through `Integer` per the generic signature; intermediate unboxing/boxing can create extra overhead. `mapToInt(...).sum()` expresses the intent of integer summation more directly and is the common choice when only a primitive result is needed.

### 5.2. Primitive streams in Java 17

| Primitive stream | Element | Representative methods | When to use |
| --- | --- | --- | --- |
| `IntStream` | `int` | `range`, `rangeClosed`, `of`, `sum`, `average` | Indices, counts, 32-bit integer arithmetic |
| `LongStream` | `long` | `range`, `of`, `sum`, `average` | 64-bit integers, wider range |
| `DoubleStream` | `double` | `of`, `sum`, `average`, `map` | Floating-point arithmetic |

Java does not have a separate standard `IntegerStream`; `IntStream` is the primitive specialization for `int`. There are no standard primitive streams for every primitive such as `ByteStream` or `ShortStream` in Java 17.

Example of generating integers directly without going through a wrapper collection:

~~~java
import java.util.stream.IntStream;

int sumExclusive = IntStream.range(1, 4).sum(); // 1+2+3 = 6
int sumInclusive = IntStream.rangeClosed(1, 4).sum(); // 1+2+3+4 = 10
~~~

`range(startInclusive, endExclusive)` excludes the upper bound; `rangeClosed(startInclusive, endInclusive)` includes the upper bound. This is a common boundary mistake causing off-by-one algorithm errors, not a boxing bug.

### 5.3. Converting between primitive streams and boxed streams

~~~java
IntStream primitive = IntStream.rangeClosed(1, 4);
List<Integer> boxedList = primitive.boxed().toList();
// [1, 2, 3, 4]
~~~

`boxed()` intentionally turns each `int` element into an `Integer` to use generic APIs or collect into a `List<Integer>`. This is an explicit **boxing boundary**. `Stream.toList()` (Java 16+) returns an **unmodifiable** list; if a mutable list is desired, you can construct `new ArrayList<>(boxedList)`.

Conversely:

~~~java
List<Integer> boxed = List.of(1, 2, 3, 4);
int[] primitiveArray = boxed.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

Each `Integer` element needs to be unboxed when converting to `int[]`. Afterward, using `int[]` can prevent subsequent loops/calculations from maintaining per-element wrappers. However, copying/converting also has a cost; do not repeat it pointlessly within the same pipeline.

### 5.4. Choosing the right moment to convert to primitives

Two pipelines:

~~~java
List<Integer> values = List.of(1, 2, 3, 4);

int a = values.stream()
        .map(x -> x + 1)
        .mapToInt(Integer::intValue)
        .sum();

int b = values.stream()
        .mapToInt(Integer::intValue)
        .map(x -> x + 1)
        .sum();
~~~

Both produce the same result 14 on the list above. However, pipeline `a` uses `Stream<Integer>.map`: the lambda reads `Integer`, computes an integer, and produces a result according to the stream's wrapper type `Integer`. Pipeline `b` converts once to `IntStream` and then uses primitive `map`. When a processing chain is long and each step only does arithmetic, **converting to primitives early** usually clarifies intent and can reduce overhead.

Do not convert to `IntStream` prematurely if operations still need to represent `null` or complex objects. The null policy must be clearly decided before unboxing.

### 5.5. Handling null in `Stream<Integer>`

~~~java
List<Integer> values = java.util.Arrays.asList(1, null, 3);

// If null is defined by convention as skipped:
int total = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
~~~

If `filter` is omitted, `Integer::intValue` throws `NullPointerException` upon encountering null. When null represents a data source error, validate instead of silently filtering. For a single "present or absent integer" case, `OptionalInt` can help express absence without using a `null Integer`, though API design and semantics should be weighed.

## 6. Aggregation and Statistics on Primitive Streams

Primitive streams have operators designed for numbers:

~~~java
int[] values = {1, 2, 3, 4};

int total = java.util.Arrays.stream(values).sum(); // 10

java.util.IntSummaryStatistics stats =
        java.util.Arrays.stream(values).summaryStatistics();

// stats.getCount(): 4
// stats.getSum(): 10
// stats.getMin(): 1
// stats.getMax(): 4
// stats.getAverage(): 2.5
~~~

`IntSummaryStatistics` holds count, sum, min, max, and average. Its `getSum()` uses `long`, whereas `IntStream.sum()` returns `int`, so a primitive sum can still **overflow** if the total exceeds the 32-bit range:

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 due to int integer overflow

long safer = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648L
~~~

Converting to `LongStream` expands the range but does not rule out `long` overflow in all cases. If sums exceeding 64 bits or exact decimals are required, use an appropriate numeric model such as `BigInteger` or `BigDecimal`; they are **object types** and have no dedicated primitive stream in the JDK. Performance goals must not be placed above accuracy requirements.

`average()` returns `OptionalDouble` because a stream can be empty; `sum()` on an empty stream returns 0. You must handle the no-data case according to business policy rather than assuming `average` always has a value:

~~~java
double mean = IntStream.of(1, 2, 3, 4)
        .average()
        .orElseThrow(); // 2.5
~~~

The example is a snippet placed inside a method with `import java.util.stream.IntStream;`.

## 7. Runnable Java 17+ Program

Create the file `BoxingPerformanceDemo.java`:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;

public class BoxingPerformanceDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, 2, 3, 4);

        int loopSum = 0;
        for (Integer boxed : values) {
            loopSum += boxed; // unbox when adding
        }
        System.out.println("List<Integer> sum (loop): " + loopSum);

        System.out.println("Stream<Integer> sum: "
                + values.stream().mapToInt(Integer::intValue).sum());

        System.out.println("IntStream sum: "
                + IntStream.rangeClosed(1, 4).sum());

        System.out.println("Primitive -> boxed List: "
                + IntStream.rangeClosed(1, 4).boxed().toList());

        System.out.println("int[] sum: "
                + Arrays.stream(new int[] {1, 2, 3, 4}).sum());

        IntSummaryStatistics stats =
                IntStream.of(1, 2, 3, 4).summaryStatistics();
        System.out.println("stats: "
                + stats.getCount() + ", " + stats.getSum()
                + ", " + stats.getAverage());

        Integer small1 = Integer.valueOf(127);
        Integer small2 = Integer.valueOf(127);
        System.out.println("127 same reference: " + (small1 == small2));
        System.out.println("1000 equal value: "
                + Integer.valueOf(1000).equals(Integer.valueOf(1000)));

        Integer nullable = null;
        try {
            int n = nullable;
            System.out.println(n);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null: NullPointerException");
        }

        List<Integer> withNull = Arrays.asList(1, null, 3);
        try {
            System.out.println(withNull.stream()
                    .mapToInt(Integer::intValue).sum());
        } catch (NullPointerException ex) {
            System.out.println("stream null: NullPointerException");
        }

        System.out.println("range(1,4) sum: "
                + IntStream.range(1, 4).sum());
        System.out.println("rangeClosed(1,4) sum: "
                + IntStream.rangeClosed(1, 4).sum());
    }
}
~~~

Compile and run:

~~~bash
javac BoxingPerformanceDemo.java
java BoxingPerformanceDemo
~~~

Output:

~~~text
List<Integer> sum (loop): 10
Stream<Integer> sum: 10
IntStream sum: 10
Primitive -> boxed List: [1, 2, 3, 4]
int[] sum: 10
stats: 4, 10, 2.5
127 same reference: true
1000 equal value: true
unboxing null: NullPointerException
stream null: NullPointerException
range(1,4) sum: 6
rangeClosed(1,4) sum: 10
~~~

The output illustrates **behavior**, not speed measurement. `int[]`, `List<Integer>`, and the stream forms all produce a sum of 10 in the small example, yet have different storage/execution models. The two null-handling lines show that unboxing can fail in both loops and streams. The cache line only shows that `Integer.valueOf(127)` uses a shared reference per the caching contract; do not use `==` to compare wrapper values in general.

## 8. Practical Performance Considerations

### 8.1. Sources of overhead when boxing repeatedly

In large datasets, boxing can:

- Increase **references** and wrapper metadata compared to primitive arrays.
- Create new wrappers (especially values outside the cache), causing allocations and pressure on the garbage collector.
- Add unbox/box conversions in loops, lambdas, or generic methods.
- Lead to indirect data access through references, affecting memory locality and CPU cache.

These costs depend on whether wrappers live long enough to reside on the heap, collection structure, JIT escape analysis optimizations, warmup time, and hardware characteristics. There is no universal figure such as "List<Integer> is X times slower than int[]".

### 8.2. Optimizing at the right spot

When source data is already an `int[]` array and the task is repeated computation, using a primitive loop or `Arrays.stream(int[])` is usually suitable. If working with a `List<Integer>`, use `mapToInt` or convert once to `int[]` when the arithmetic work is long or resource-intensive enough to offset the conversion cost.

Conversely, replacing every `List<Integer>` with `int[]` can sacrifice API flexibility, introduce copying overhead when adding/removing elements, increase complexity, or cause bugs. If the bottleneck lies in I/O, networking, or the database, reducing boxing in a few loops rarely yields meaningful improvements.

For counters and accumulators in hot loops, choose primitives when null and generic wrappers are not needed. At library boundaries where objects are required, box only where necessary.

### 8.3. Meaningful benchmarks: JMH, not a single `System.nanoTime`

A trustworthy performance test should use a tool like **JMH (Java Microbenchmark Harness)**, with these characteristics:

- Includes warmup so the JIT optimizes; configures multiple iterations/forks.
- Uses `Blackhole` or a result-consuming mechanism to prevent computations from being eliminated by the compiler.
- Compares the same workload/data, input size, and computational goal; separates **collection construction cost** from **traversal/summation cost**.
- Measures throughput/latency alongside allocations and GC when relevant; evaluates numeric distribution, size, and the ratio of values inside the wrapper cache.
- Does not use a small result on a laptop as proof applicable to production.

Benchmark design idea: pre-build an `int[]` and an equivalent `List<Integer>` in the setup step, then separately measure `for-each` and `stream/mapToInt/sum` on each structure. If you create the list while measuring the calculation, the result no longer reflects only traversal cost. This is benchmark design guidance, **not complete JMH code**.

### 8.4. Parallel streams do not automatically solve boxing

`parallelStream()` adds task-splitting overhead, thread coordination, result combining, and requires operations without unsafe side effects. For small lists, there is usually no reason to use it merely for "speedup". Even in a parallel pipeline, if the data is in a `List<Integer>`, the input is still wrappers; parallelization does not turn it into a primitive array.

If parallelism is needed, verify that data is large enough, computation is CPU-intensive enough, the spliterator source is suitable, and the reduction operation is properly associative. Do not use an external `int sum` variable and increment it from multiple threads with `forEach`: that both creates a race condition and fails to leverage the built-in `sum` aggregation.

## 9. Common Mistakes

1. **Writing `List<int>`:** Java 17 generics require reference types, so use `List<Integer>` or use `int[]` when appropriate.
2. **Using `Integer` for every counter:** in arithmetic loops, primitive variables avoid unnecessary conversions.
3. **Thinking `List<Integer>` is an `int` array internally:** the list manages references to wrappers.
4. **Believing every boxing creates a new object:** `Integer.valueOf` caching and JIT optimizations can change actual allocations; measure before concluding.
5. **Believing boxing has zero cost because the compiler handles it:** reference representation, nullability, and pipeline boxing can still affect memory/GC/latency.
6. **Comparing wrappers with `==`:** compares identity, not guaranteed value equality; use `equals` or `Objects.equals`.
7. **Unboxing null without checking:** `Integer x = null; int y = x;` throws NPE.
8. **Using `Stream<Integer>.reduce` for every sum:** when only summing integers, consider `mapToInt(...).sum()` or a primitive stream from the start.
9. **Thinking `mapToInt` removes the storage overhead of an already boxed list:** it unboxes each element, but the original data remains wrappers.
10. **Calling `boxed()` and then continuing with multiple arithmetic steps:** if a generic API is not needed, stay in `IntStream`, `LongStream`, or `DoubleStream` as long as appropriate.
11. **Confusing `range` with `rangeClosed`:** the upper bound of `range` is excluded.
12. **Ignoring overflow when switching to primitive sum:** `IntStream.sum()` returns `int` and can overflow, even without boxing.
13. **Silently filtering null:** only use `filter(Objects::nonNull)` if this is an accepted data rule.
14. **Benchmarking with a few short runs:** JIT, warmup, GC, and dead-code elimination make measurements unreliable.

## 10. Self-Check

**Question 1.** Why can `List<Integer>` not use `List<int>`?

**Answer:** Generic type parameters in Java 17 must be reference types. `Integer` is the wrapper for `int`; primitive structures like `int[]` are not generic collections.

**Question 2.** What conversions occur in the loop `for (Integer i = 0; i < 1000; i++)`?

**Answer:** The initial value 0 is boxed. Checking `i < 1000` unboxes, and `i++` unboxes to increment then boxes back to assign to the `Integer` variable. Depending on the loop body, other conversions may also occur.

**Question 3.** What does `List.of(1,2,3).stream().mapToInt(Integer::intValue).sum()` evaluate to, and where does boxing still exist?

**Answer:** The sum is 6. The list elements are `Integer`; `mapToInt` unboxes into a primitive stream before summing.

**Question 4.** If `List<Integer>` has a null element, what happens when calling `mapToInt(Integer::intValue)`?

**Answer:** `NullPointerException` upon encountering null. Filter out or reject null depending on the data contract.

**Question 5.** How do `IntStream.range(1,4).sum()` and `IntStream.rangeClosed(1,4).sum()` differ?

**Answer:** They evaluate to 6 (1+2+3) and 10 (1+2+3+4), respectively.

**Question 6.** To collect an `IntStream` into a `List<Integer>`, what should you use, and when should you weigh the cost?

**Answer:** `stream.boxed().toList()`. Semantically, every primitive value is converted to a wrapper; when data is large or the pipeline is primarily numeric, check whether a generic list is truly necessary.

**Question 7.** Does using `IntStream` prevent a sum exceeding `Integer.MAX_VALUE` from overflowing?

**Answer:** No. `IntStream.sum()` performs `int` integer addition. You can switch to `asLongStream().sum()` if `long` range suffices, or use arbitrary-precision integers when needed.

## 11. Official Java Documentation

- [Autoboxing and Unboxing — Java Tutorials](https://docs.oracle.com/javase/tutorial/java/data/autoboxing.html): mechanism for converting primitives to wrappers and vice versa.
- [`Integer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `valueOf`, `intValue`, `equals`, and caching.
- [`List` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): generic collection API.
- [`Stream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `mapToInt`, `reduce`, and `toList` operators.
- [`IntStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html): `range`, `rangeClosed`, `boxed`, `sum`, and `summaryStatistics`.
- [`IntSummaryStatistics` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IntSummaryStatistics.html): statistics over integers.

**Takeaway:** Use `Integer` when you need object/generic semantics or nullability; use `int`, `int[]`, and `IntStream` when primarily processing integers in repeated calculations. Clearly see the boxing/unboxing boundaries, check for null and overflow, and measure on the real workload before trading off design solely out of concern for cost.
