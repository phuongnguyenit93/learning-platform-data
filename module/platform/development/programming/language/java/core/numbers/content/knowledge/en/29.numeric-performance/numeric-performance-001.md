# Primitives vs. Wrappers: Allocation and Data Layout in Java

## 1. The Performance Problem to Understand

Java distinguishes **primitive** types such as `int`, `long`, and `double` from **wrapper** classes such as `Integer`, `Long`, and `Double`.

In terms of arithmetic value, an `int` holding 100 and an `Integer` representing 100 can serve the same calculation. However, in terms of data model, memory layout, and runtime cost, they are not equivalent:

- A primitive variable or array slot represents a **direct value** of the declared type; it does not require a separate wrapper object just to hold the number.
- A wrapper variable or array slot holds a **reference** to an object (or `null`). When a wrapper object is actually allocated, it requires object management storage alongside the numeric value.
- Converting between a primitive and a wrapper via **boxing/unboxing** can cause object allocations, increase the amount of data that must be read, increase GC pressure, and add conversion steps. However, the JVM may reuse wrappers or optimize away certain allocations; one cannot assume *every boxing operation always creates a new object*.

This lesson analyzes the differences in **allocation and data layout**, how they affect operations on large sets of numbers, and how to choose the right data structure. This is the Java Core model and the JVM characteristics you need to understand to measure performance on a solid foundation.

## 2. Primitives and Their Corresponding Wrappers

| Primitive | Wrapper | Primitive value size in Java | Characteristics |
| --- | --- | --- | --- |
| `byte` | `Byte` | 8 bits | Signed integer |
| `short` | `Short` | 16 bits | Signed integer |
| `int` | `Integer` | 32 bits | Signed integer |
| `long` | `Long` | 64 bits | Signed integer |
| `float` | `Float` | 32 bits | IEEE 754 floating-point number |
| `double` | `Double` | 64 bits | IEEE 754 floating-point number |
| `char` | `Character` | 16 bits | UTF-16 code unit |
| `boolean` | `Boolean` | Does not mandate a single byte storage size in every context | Two logical values `true`, `false` |

The bit counts in the table apply to the **primitive value range/representation**, **not the size of a wrapper object**. For example, `Integer` contains an `int` field, but an `Integer` object may require additional JVM object management overhead. Object size depends on the JVM, architecture, compressed reference configuration, and alignment.

Example of types:

```java
int direct = 42;
Integer reference = Integer.valueOf(42);

int[] directArray = {10, 20, 30};
Integer[] referenceArray = {10, 20, 30};
```

`direct` carries the value `42` of type `int`; `reference` is a reference of type `Integer`. With large volumes of numeric data, the difference is usually clearest between **primitive arrays** and **wrapper arrays** or collections storing wrappers.

## 3. Memory Layout of `int[]` and `Integer[]`

### 3.1. `int[]`: primitive value elements reside directly inside the array

`int[] values = new int[4]` creates **one array object** containing four `int` slots. The element data section of the array occupies a total of `4 × 4 = 16` bytes for the four `int` values, **excluding the array object's header and padding**.

Logical diagram:

```text
Variable values
      |
      v
+-----------------------------------------+
| int[]: header | 10 | 20 | 30 | 40 | ... |
+-----------------------------------------+
                4B   4B   4B   4B
```

The element slots lie contiguously in the element area of a single array object. The JVM can scan data sequentially with good locality, with multiple values residing in the same cache line. There is no **separate `Integer` object** just to hold each element.

Note: `int[]` is still an **object** in Java. The claim "primitives always live on the stack" is false. Where data is physically placed is decided by the JVM; a primitive local variable may reside in a register, in a stack frame, or be optimized away, whereas `int[]` elements belong to the data of the array object.

### 3.2. `Integer[]`: array stores references, values reside in wrappers

`Integer[] values = new Integer[4]` creates **one array object consisting of four references**. Initially, all four references are `null`. To store numeric values, the program must have `Integer` objects being referenced.

Logical diagram (does not represent actual sizes):

```text
Variable values
      |
      v
+------------------------------------+
| Integer[] header | ref | ref | ref |
+--------------------|-----|-----|---+
                     |     |     |
                     v     v     v
                  +----+ +----+ +----+
                  |1000| |2000| |3000|
                  +----+ +----+ +----+
                  Each slot is an Integer object
                  if not reused/optimized
```

The references lie contiguously inside the array, but the wrapper objects they point to **are not guaranteed by Java to lie adjacent to one another**. When iterating over the array, the CPU may need to access additional memory regions by following references, reducing locality compared to `int[]`. Wrappers also still count as objects that may be managed by GC if they actually exist on the heap.

For the example:

```java
int[] primitive = {1000, 2000, 3000};
Integer[] boxed = {1000, 2000, 3000};
```

- Both are **one array** and have `length = 3`.
- The `primitive` array directly holds three `int` values.
- The `boxed` array holds three `Integer` references; the syntax of assigning integer literals into `Integer[]` triggers autoboxing. The corresponding objects may already exist, be newly created, or be optimized by the JVM depending on context.
- Do not count `Integer[]` as "12 bytes of data for three numbers" because it holds **references**, while the numeric data belongs to the wrappers.

### 3.3. Estimation model, not absolute numbers

For `N` elements of type `int`:

- `int[]`: the element data section is **`4 × N` bytes**, plus one array header and padding.
- `Integer[]`: the array data section is **`N × reference size`**, plus the array header; in addition, there is the data of the **distinct wrapper objects that actually exist**, each having a header, an `int` field, padding, and potentially being shared across multiple slots.
- `ArrayList<Integer>`: in addition to the list object and its backing array of references, there are the wrappers for the stored elements if not shared; the backing array may have a capacity larger than its size.

There is no universal figure such as "every `Integer` is exactly 16 bytes on every JVM" or "a reference is always 8 bytes". For example, a 64-bit HotSpot JVM can typically use **compressed ordinary object pointers** (compressed oops) to store references smaller than machine pointer size; reference compression settings, headers, alignment, and other configurations will change the actual result.

A useful comparison is the **allocation structure and number of reference dereferences**, followed by measuring with appropriate tools on the application's JVM.

## 4. Autoboxing/Unboxing and Hidden Costs

**Boxing** converts a primitive to a wrapper. **Unboxing** extracts a primitive from a wrapper. Java often inserts these conversions automatically:

```java
int a = 7;
Integer b = a; // autoboxing: equivalent to Integer.valueOf(a)
int c = b;     // unboxing: equivalent to b.intValue()
```

Key points:

1. `Integer.valueOf(int)` can return a cached object instead of creating a new one.
2. Java requires supporting a certain cache range, including `Integer` values in the range **-128 to 127** for boxing/`valueOf`; values outside this range may have different reuse strategies depending on the JVM.
3. For a newly created wrapper that does not "escape" an optimization scope, the JIT can eliminate the allocation or boxing operation using techniques such as escape analysis and scalar replacement. This is an **optimization possibility**, not a guarantee for every execution path.
4. Unboxing `null` causes a `NullPointerException`.
5. When boxing occurs across millions of elements that do not benefit from caching or optimization, the amount of allocation can be significant.

Example:

```java
Integer smallA = Integer.valueOf(127);
Integer smallB = Integer.valueOf(127);
System.out.println(smallA == smallB);       // true: same cached object

Integer largeA = Integer.valueOf(1000);
Integer largeB = Integer.valueOf(1000);
System.out.println(largeA.equals(largeB)); // true: same value
// Do not rely on largeA == largeB: caching strategy may vary.
```

The `==` operator on **two `Integer` references** compares object identity, whereas `equals()` compares the `int` value held by the wrappers. When one side is an `int`, Java may unbox the other side and perform numeric comparison, causing code using `==` to have different semantics depending on operand types. You should use `equals()` when intentionally comparing two wrappers by value, and check for `null` when needed.

## 5. Standalone Java 17 Program with Verified Output

Create the file **`PrimitiveWrapperLayoutDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class PrimitiveWrapperLayoutDemo {
    public static void main(String[] args) {
        int[] primitive = {1000, 2000, 3000};
        Integer[] wrapper = {1000, 2000, 3000};

        System.out.println("primitiveType=" + primitive.getClass().getName());
        System.out.println("wrapperType=" + wrapper.getClass().getName());
        System.out.println("primitiveSum=" + Arrays.stream(primitive).sum());
        System.out.println("wrapperSum=" + Arrays.stream(wrapper)
                .mapToInt(Integer::intValue).sum());

        List<Integer> list = new ArrayList<>();
        for (int number : primitive) {
            list.add(number);
        }
        System.out.println("listSum=" + list.stream()
                .mapToInt(Integer::intValue).sum());

        int[] zeroDefaults = new int[2];
        Integer[] nullDefaults = new Integer[2];
        System.out.println("primitiveDefault=" + zeroDefaults[0]);
        System.out.println("wrapperDefault=" + nullDefaults[0]);

        Integer first = Integer.valueOf(127);
        Integer second = Integer.valueOf(127);
        System.out.println("cachedIdentity=" + (first == second));
        System.out.println("cachedEquality=" + first.equals(second));

        Integer[] nullable = {1, null, 3};
        System.out.println("wrapperCanContainNull="
                + Arrays.asList(nullable).contains(null));
        try {
            int invalid = nullable[1];
            System.out.println(invalid);
        } catch (NullPointerException exception) {
            System.out.println("unboxNull=NullPointerException");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac PrimitiveWrapperLayoutDemo.java
java PrimitiveWrapperLayoutDemo
```

Verified output with `javac --release 17`:

```text
primitiveType=[I
wrapperType=[Ljava.lang.Integer;
primitiveSum=6000
wrapperSum=6000
listSum=6000
primitiveDefault=0
wrapperDefault=null
cachedIdentity=true
cachedEquality=true
wrapperCanContainNull=true
unboxNull=NullPointerException
```

Explanation of each group:

- `[I` is the runtime name of an `int[]` array; `[Ljava.lang.Integer;` is the runtime name of an `Integer[]` reference array. Names in this format appear in `Class.getName()` per JVM conventions.
- All three summation paths produce 6000. Equal arithmetic results **do not mean** the three data structures are stored with the same amount of memory or run at the same speed.
- `new int[2]` initializes elements to `0`; `new Integer[2]` initializes elements to `null`.
- Two calls to `Integer.valueOf(127)` return the same object within the guaranteed cache range; both `==` and `equals()` return true in this example.
- `Integer[]` can store `null`. Passing `null` through a conversion to `int` causes a `NullPointerException`.
- The program does not measure heap directly because checking `Runtime.totalMemory() - freeMemory()` before/after a small loop is not a reliable measurement of object size; GC, JIT, and other allocations affect the numbers.

## 6. `ArrayList<Integer>` vs. `int[]` in Large Datasets

When you need one million numbers:

```java
int[] raw = new int[1_000_000];

List<Integer> items = new ArrayList<>();
// items.add(number) will box if number has type int.
```

**Primitive array**:
- `int` data resides in contiguous slots, giving good locality during sequential traversal.
- No possibility of `null` elements.
- Fixed length; does not grow automatically.
- Can update values at an index directly without boxing.

**`ArrayList<Integer>`**:
- The list manages a backing array holding references, whose capacity may exceed the actual number of elements.
- Elements are represented by `Integer`, which may involve shared, reused, or distinct wrapper objects.
- Provides a flexible `List` API, resizing, and integration with Collections/Generics.
- Accepts `null` and provides object-oriented lookup and manipulation operations.
- When calling `get(i)` to compute with `int`, an unboxing step typically occurs and may add indirect memory access.

If the size is known in advance, `new ArrayList<>(capacity)` can reduce backing array resizes, but it does not automatically eliminate reference/wrapper overhead. If dense numeric storage and arithmetic processing are needed, `int[]` is usually a reasonable starting choice.

The same applies to `long[]` and `double[]`. Primitive `long`/`double` values take 8 bytes per element, whereas `Long[]`/`Double[]` store references to objects. Do not use the `int[]` size table to infer the exact overhead of all wrapper types.

## 7. Primitive Streams: Reducing Boxing Needs in Pipelines

Java provides streams dedicated to primitive numbers:

- `IntStream` for `int`.
- `LongStream` for `long`.
- `DoubleStream` for `double`.

From `int[]`, you can create an `IntStream` with `Arrays.stream(intArray)`. From `Integer[]`, `Arrays.stream(wrapperArray)` creates a `Stream<Integer>` and usually requires unboxing during arithmetic processing:

```java
int[] numbers = {1, 2, 3};
Integer[] wrappers = {1, 2, 3};

int directSum = Arrays.stream(numbers).sum();
int unboxedSum = Arrays.stream(wrappers)
        .mapToInt(Integer::intValue)
        .sum();
// Both sums are 6.
```

`IntStream` also provides `average()`, `min()`, `max()`, `summaryStatistics()`, and `toArray()` for numeric processing steps, helping avoid creating a `Stream<Integer>` and boxing each value unnecessarily.

When objects are genuinely needed, you can use:

```java
List<Integer> boxed = Arrays.stream(new int[] {1, 2, 3})
        .boxed()
        .toList(); // Java 16+, returns List<Integer>
```

`boxed()` is the boundary converting primitives into wrappers: if the result retains the objects long-term, storage cost may increase. There is no claim that streams are always faster than loops: for very small pipelines, pipeline creation/dispatch overhead and JIT optimization levels can make loops faster. Measure on real workloads.

## 8. Where Does Allocation Happen, and How Can the JVM Optimize It?

### 8.1. Do not equate "wrapper" with "one allocation per expression"

`Integer.valueOf(42)` can return an object from the cache. Code creating temporary wrappers is sometimes completely optimized away by the JIT if object identity is not needed.

Conceptual example:

```java
static int compute(int x) {
    Integer boxed = Integer.valueOf(x);
    return boxed.intValue() * 2;
}
```

This is an **illustrative method** to place inside a class. The compiler or JIT may optimize away the boxing/unboxing since the object does not need to be retained. However, you should not claim that the call above **always** has its allocation eliminated on every JVM, optimization level, or execution mode.

### 8.2. When are wrappers hard to optimize away?

If a wrapper is stored long-term in a collection, returned from a method, or has its identity observed, the JIT has fewer opportunities to eliminate the object representation. For example:

```java
static List<Integer> makeList(int[] values) {
    List<Integer> result = new ArrayList<>(values.length);
    for (int value : values) {
        result.add(value); // autoboxing
    }
    return result;
}
```

With data outside the cache range and elements retained by the list, wrapper objects can generate significantly more allocations compared to `int[]`. You must measure retained heap (*retained size*) or actual allocations rather than deducing a fixed byte count from source code.

### 8.3. Heap, stack, and registers

Do not write "primitives live on the stack, objects live on the heap" as an absolute rule:

- A local `int` variable may be kept in a register or on the stack depending on JVM optimizations.
- An `int` field of an object is part of the data inside that object.
- Both `int[]` and `Integer[]` arrays are Java objects.
- A wrapper object can be eliminated by the JVM via optimization and no longer exist as an actual heap allocation.
- Header/alignment sizes, compressed references, and how GC moves objects are JVM implementation details.

In performance analysis, a better question is **"how many objects/references are storing and accessing this data at measured runtime?"** rather than guessing solely from whether a variable is declared inside a method.

## 9. Impact on CPU Cache and Garbage Collection

### CPU cache and sequential traversal

`int[]` stores `int` elements directly and contiguously, so when traversing a large range of numbers, the CPU generally benefits from locality and prefetching. `Integer[]` or `ArrayList<Integer>` must read a reference and then typically read the corresponding wrapper; if wrappers are scattered in memory, more cache lines and more memory accesses may be needed.

This often matters in statistics, numeric graphs, telemetry data, or computational pipelines over large datasets. However, concrete performance still depends on CPU, cache, array size, branch prediction, JIT, and the work done per loop iteration.

### GC pressure

If an application creates millions of short-lived wrappers, GC has more objects to track and reclaim. If wrappers live long-term in collections, they occupy retained heap and can increase GC marking/traversal overhead.

Do not automatically conclude "every occurrence of `Integer` in code causes an object allocation". Caching, scalar replacement, and other optimizations can make runtime allocation counts differ from boxing expressions in source code.

### Computation and memory are not always the same bottleneck

A simple loop summing an `int[]` may be heavily influenced by memory bandwidth, whereas complex calculations on each element may become CPU-bound first. Choosing wrappers or primitives must consider the total cost of the program, not just the speed of a single operation.

## 10. When Are Wrappers Required or Recommended?

Despite potential overhead, wrappers have legitimate roles:

1. **Generics/Collections:** `List<int>`, `Map<String, long>` are invalid in Java 17; `List<Integer>`, `Map<String, Long>` (or specialized arrays/structures) are required.
2. **Potentially absent values:** `Integer` can be `null`, whereas `int` cannot. However, do not use `null` arbitrarily if a clearer state representation can be designed.
3. **APIs requiring objects:** frameworks, reflection, generic processing, or APIs accepting `Object`/`Number` may require wrappers.
4. **Utility integration:** wrapper classes provide methods such as `Integer.parseInt`, `Integer.compare`, and `Long.parseLong`. These methods belong to the wrapper classes while still being able to return primitive values.
5. **Small datasets or non-hot paths:** prioritize clear, simple, domain-accurate APIs if the overhead is negligible.

When you need to represent a "present or absent" computation result without returning `null`, Java also provides `OptionalInt`, `OptionalLong`, and `OptionalDouble`. They are Optional objects, but they help avoid boxing numeric values into `Integer`/`Long`/`Double` inside those APIs.

**Do not trade correctness for performance:** if "no data" is different from zero, converting a `nullable Integer` into an `int` without designing an absence convention can corrupt business logic or cause `NullPointerException`.

## 11. Common Pitfalls

### 11.1. Null unboxing

```java
Integer amount = null;
// int x = amount; // Throws NullPointerException at runtime.
```

You must check for `null` before unboxing, use an appropriate default value, or define an explicit absence state.

### 11.2. Comparing references instead of values

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

boolean sameValue = a.equals(b); // true
boolean sameIdentity = a == b;   // do not rely on this result
```

Wrapper reuse is an implementation optimization; `==` between two references is not a numeric value comparison. Similarly, `Double` and `Float` have `equals()`/`compareTo()` rules you need to understand regarding `NaN` and the sign of zero.

### 11.3. Confusing a primitive array with a list of wrappers

```java
int[] values = {1, 2, 3};
List<int[]> oneArray = Arrays.asList(values);
// oneArray.size() == 1, not 3
```

`Arrays.asList(int[])` treats the entire primitive array as **a single array object**. If you want `List<Integer>`, you can use `Arrays.stream(values).boxed().toList()`.

### 11.4. Forgetting overflow or precision issues

Primitives being fast and compact does not mean every operation is exact:

- `int`/`long` can overflow during addition/multiplication, even inside `IntStream.sum()` or `LongStream.sum()`.
- `double` has binary floating-point inaccuracy. `Double` is the wrapper for the same `double` type, **not** a way to increase numeric precision.
- For exact decimal financial calculations, consider `BigDecimal` with explicit rounding rules; it is an object with allocation and algorithmic characteristics different from primitives.

Do not try to solve overflow or precision errors by replacing `int` with `Integer` or `double` with `Double`.

### 11.5. Assuming a fixed wrapper size

You should not use a fixed "`Integer` object size" to calculate heap usage across all JVMs. An `int[]` element is a 4-byte value, though the array object still has a header; `Integer[]` holds references whose size depends on JVM configuration. Wrapper size and caching/GC behavior make actual numbers vary.

### 11.6. Microbenchmarks are easily flawed

Do not measure by taking a single `System.nanoTime()` around a tiny loop and drawing conclusions. Factors that skew measurements include:

- The JVM has not warmed up for JIT optimization.
- GC runs during measurement, or allocations disappear due to optimization.
- Code may be eliminated because the result is unused (*dead code elimination*).
- Test data does not reflect real-world value distributions, cache hit rates, or `null` cases.
- The benchmark bundles data creation, boxing, computation, and collection together without distinguishing what is being measured.
- Differences in JVM modes, CPU architectures, thread counts, and data sizes.

For latency/throughput questions, use **JMH** or an appropriate benchmarking tool, state the JVM environment and parameters, and use proper warm-up/forks. To measure allocations or retained memory, use a profiler such as Java Flight Recorder/JDK Mission Control or an appropriate heap profiler. Do not report speed or byte/object numbers without measuring in that specific context.

## 12. Criteria for Choosing a Data Structure

| Need | Option to consider | Reason |
| --- | --- | --- |
| Large volume of integers, sequential scan/sum | `int[]` / `long[]` | Direct element data, no wrapper per element |
| Large volume of floating-point numbers | `double[]` | Stores doubles directly; must understand floating-point error |
| Variable element count, List API | `ArrayList<Integer>` / `ArrayList<Long>` | Satisfies collection API; accepts reference/boxing overhead |
| Need `null` to distinguish absence | `Integer` / `Long` | Can represent missing values, but requires null checks |
| Pipeline doing arithmetic on primitive arrays | `IntStream` / `LongStream` / `DoubleStream` | Avoids unnecessary boxing |
| API requires `Stream<Integer>` or `List<Integer>` | `boxed()` at the boundary | Converts types when objects are actually needed |
| Decimal precision required by business rules | `BigDecimal` | Correctness outweighs simple primitive-wrapper comparison |
| Hot path sensitive to allocation and cache | Measure multiple approaches | Layout, JIT, and GC determine actual effectiveness |

An effective decision workflow: **define semantics** (precision, nullability, required collections), **choose a simple numeric storage structure**, then **profile on real data** if performance is an issue. Do not replace all `List<Integer>` with `int[]` if doing so breaks interfaces or complicates processing without evidence of cost.

## 13. Self-Check Quiz

**Question 1.** For one million `int` values, why does `int[]` usually have better locality than `Integer[]`?  
**Answer:** `int` data is stored contiguously inside a single array; `Integer[]` stores references and typically must follow those references to wrapper objects that may be scattered in memory.

**Question 2.** What does `Integer[] refs = new Integer[2]` contain before assigning elements?  
**Answer:** two `null` references. Correspondingly, `int[] values = new int[2]` contains two `0` values.

**Question 3.** If source code calls `Integer.valueOf(x)` 1000 times, is it guaranteed that runtime allocates 1000 `Integer` objects?  
**Answer:** no. `valueOf` has caching and the JVM can optimize or reuse objects depending on context.

**Question 4.** Does `new ArrayList<Integer>()` immediately create an `Integer` for every slot of its anticipated capacity?  
**Answer:** no. The list manages a backing array of **references**; `Integer` elements are objects referenced when corresponding values are added.

**Question 5.** Why does `int[]` still have memory overhead?  
**Answer:** `int[]` is an array object with a header and padding, even though each `int` element slot takes 4 bytes.

**Question 6.** What does `Integer sum = null; int value = sum;` cause?  
**Answer:** `NullPointerException` during unboxing.

**Question 7.** If `double` is replaced with `Double`, does `0.1 + 0.2` become decimally exact?  
**Answer:** no. `Double` wraps a `double` value with the same binary floating-point semantics and does not create arbitrary decimal precision.

**Question 8.** When should `List<Integer>` be used even though `int[]` is usually more compact?  
**Answer:** when a Generic/Collection API is needed, when a resizable list is required, or when interfacing with components expecting objects, and the cost is acceptable for the requirements.

## 14. Key Takeaways

- Primitives are **direct values**; wrappers are **referenced objects** that can add overhead, dereferencing, boxing/unboxing, and GC pressure.
- `int[]` stores `int` elements directly inside one array; `Integer[]`/`ArrayList<Integer>` store **references to wrappers**.
- The JVM has caching and JIT optimizations: **not every boxing operation creates a new allocation**, nor is there a single exact wrapper size across all JVMs.
- Choose `int[]`, `long[]`, `double[]`, and primitive streams when processing large volumes of arithmetic; choose wrappers when object semantics, nullability, or Generics are required.
- Measure performance with appropriate benchmarks and profilers before drawing conclusions about speed or memory usage in a specific application.

Official references (Java SE 17): [Java Language Specification — Primitive Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html), [Boxing and Unboxing Conversions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7), [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html), [Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html), [IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).
