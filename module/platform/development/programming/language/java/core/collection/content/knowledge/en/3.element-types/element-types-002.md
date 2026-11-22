# Autoboxing, Unboxing, and the Cost of Wrapper Types

In the Java Collections Framework, the following snippet looks as though it stores integers directly:

```java
List<Integer> scores = new ArrayList<>();
scores.add(10);
int first = scores.get(0);
```

However, the element type of the list is `Integer`, while the literal `10` and the variable `first` have the type `int`. Java allows this concise syntax through automatic conversions between primitive types and wrapper types.

This convenience does not erase the differences between primitive values and object references. Those differences show up in `null` handling, comparison semantics, overload resolution, data footprint, and processing overhead.

This article uses Java 17 and focuses on how boxing and unboxing arise when working with collections. A complete program with compilation commands and expected output is provided in the experimental section. Other short snippets illustrate specific points; any snippet explicitly noted as "does not compile" is an intentional error example.

## 1. Why Do Numeric Collections Need Wrapper Types?

### 1.1. Primitive Types and Reference Types

`int` represents an integer value. `Integer` is a wrapper class that represents an `int` value inside an object.

In Java 17 generics, type arguments must be reference types. Therefore:

```java
List<Integer> scores = new ArrayList<>();
```

is valid, whereas the declaration below does not compile:

```java
List<int> scores;
```

A collection such as `ArrayList<Integer>` organizes its elements as references to `Integer` objects, not as a specialized array holding `int` values directly.

### 1.2. Common Type Pairs

| Primitive type | Wrapper type |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

The class name is not always formed merely by capitalizing the first letter: `int` pairs with `Integer`, and `char` pairs with `Character`.

### 1.3. Why Not Just Use Primitive Arrays?

`int[]` works well for many numerical problems, but it does not share the same API and data organization model as `List<Integer>`, `Set<Integer>`, or `Map<String, Integer>`.

Wrapper types allow numeric values to participate in a unified framework: they can serve as elements, keys, and values, and be passed through APIs that accept objects. The benefit is interoperability and expressive data modeling; the cost is the conversion layers and object representation that must be clearly understood.

## 2. Boxing and Autoboxing

**Boxing** converts a primitive value into its corresponding wrapper type. **Autoboxing** is the common term for when Java performs this conversion automatically in an allowed context.

For example:

```java
int raw = 42;
Integer boxed = raw;
```

You can think of the value-equivalent form as:

```java
Integer boxed = Integer.valueOf(raw);
```

This is a conceptual way to understand the conversion; the language contract should not be replaced by an assumption that every compiler must emit one fixed bytecode sequence.

### 2.1. When Adding Numbers to a Collection

Illustrative snippet:

```java
List<Integer> values = new ArrayList<>();
values.add(42);
```

The element parameter expects `Integer`, while `42` has type `int`; boxing occurs at this boundary.

With a map:

```java
Map<Integer, Integer> counts = new HashMap<>();
counts.put(7, 1);
```

Both the key and the value are represented using wrapper types. You should not look at the two primitive literals and conclude that the map stores two `int` values directly in a specialized structure.

### 2.2. Boxing Does Not Always Mean Allocating a New Object

A value may reuse a cached object. Under certain circumstances, the JVM may also optimize away intermediate objects as long as observable behavior is preserved.

Therefore, the statement "every time a number is written into a `List<Integer>`, a new object is guaranteed to be created" is too strong. It is important to distinguish between:

- Whether a boxing conversion occurs semantically.
- Whether a call or mechanism produces a boxed value.
- Whether a new object is actually allocated at runtime.
- How long that object remains alive.

The conversion rules are specified in [JLS 17, Section 5.1.7: Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).

## 3. Unboxing: From Reference Back to Primitive Value

**Unboxing** extracts the primitive value from its corresponding wrapper type.

For example:

```java
Integer boxed = Integer.valueOf(42);
int raw = boxed;
```

This can be understood analogously as:

```java
int raw = boxed.intValue();
```

When reading from a collection:

```java
int score = scores.get(0);
```

`get` returns `Integer`; assigning it to `int` requires unboxing.

### 3.1. Unboxing in Loops

Illustrative snippet:

```java
int sum = 0;
for (int value : values) {
    sum += value;
}
```

If `values` is a `List<Integer>`, each element is read as a reference and then used as an `int`.

Changing the loop variable to `Integer` does not automatically eliminate unboxing if the loop body still performs arithmetic:

```java
for (Integer value : values) {
    sum += value;
}
```

Here, using `value` in the addition still requires a primitive value.

### 3.2. Unboxing Does Not Create a New Wrapper

Unboxing reads the value from a wrapper; this conversion itself is not a wrapper allocation step.

The actual runtime cost can include dereferencing, reading the value, and performing necessary checks. The JVM can inline or optimize some of these steps. You should not lump the entire cost of a numerical code path under "unboxing overhead" if that code also involves allocation, collection lookups, or other algorithmic work.

### 3.3. Unboxing Can Be Followed by Primitive Widening

For example:

```java
Integer boxed = 42;
long total = boxed;
```

In this case, `Integer` can be unboxed to `int` and then widened to `long`.

That is different from automatically converting one wrapper type into another wrapper type. An `Integer` does not automatically turn into a `Long` simply because both classes represent numbers.

## 4. null: The Most Critical Pitfall When Unboxing

### 4.1. A Wrapper Can Be null, a Primitive Cannot

An `Integer` variable may not refer to any object:

```java
Integer count = null;
int primitive = count;
```

The second assignment throws a `NullPointerException`. There is no rule that automatically converts `null` into `0`.

The same applies to other pairs, such as `Boolean` to `boolean`. This rule is stated directly in [JLS 17, Section 5.1.8: Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

### 4.2. Map.get Can Return null

With a `Map<String, Integer>`:

```java
int count = counts.get("missing");
```

this can fail at the unboxing step if there is no mapping for the key, or if the map permits `null` values and the key is currently mapped to `null`.

You should separate the read step from your handling policy:

```java
Integer result = counts.get("missing");
int count = result == null ? 0 : result;
```

The example above deliberately treats both a missing entry and a `null` value as `0`. That is a domain decision, not a universal rule for every program.

If you need to distinguish "key not present" from "key present with an unknown quantity," you must preserve that distinction through your data model or additional checks.

### 4.3. getOrDefault Does Not Replace Every null with the Default Value

Illustrative snippet:

```java
Map<String, Integer> counts = new HashMap<>();
counts.put("unknown", null);

int count = counts.getOrDefault("unknown", 0);
```

Because the key `"unknown"` is already mapped to `null`, `getOrDefault` returns the value currently associated with that key (`null`). Assigning the result to `int` still causes an unboxing failure.

Do not let the word "default" in the method name lead you to assume it replaces every `null`. See [Map.getOrDefault in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,V)).

### 4.4. Boolean in Conditions

Illustrative snippet:

```java
Boolean enabled = settings.get("enabled");
if (enabled) {
    startFeature();
}
```

An `if` condition requires a `boolean`; if `enabled` is `null`, an unboxing failure occurs.

If the policy is genuinely "enable only when explicitly true," you can use `Boolean.TRUE.equals(enabled)`. That approach deliberately treats `null` as not enabled; it should not be used when a missing configuration setting is an error that must be reported.

### 4.5. The Ternary Operator Can Unbox Before Assigning to a Wrapper

Illustrative snippet:

```java
Integer nullable = null;
boolean useNullable = true;
Integer chosen = useNullable ? nullable : 0;
```

Even though `chosen` has type `Integer`, the two branches of the conditional operator have different types: one branch is `Integer` and the other is `int`. The rules for numeric conditional expressions can require unboxing the `nullable` branch and then boxing the resulting value for the assignment. When that branch is selected and its value is `null`, the program throws a `NullPointerException`.

If you want to keep a reference type and allow `null`, write the branches to match that intent—for example, by using a default value that is already an `Integer`, or by splitting the logic into an explicit `if`–`else`.

If you want to replace `null` with `0`, check `nullable == null` explicitly before any unboxing takes place. The rules for determining the type of `?:` are defined in [JLS 17, Section 15.25: Conditional Operator ? :](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25).

## 5. Immutable Wrapper Types and Increment/Addition Operations

### 5.1. Integer Is Not an In-Place Mutable Number Cell

Illustrative snippet:

```java
Integer counter = 1000;
Integer previous = counter;
counter++;
```

After this runs, `previous` still represents `1000`, while `counter` represents `1001`.

To understand why, break down the meaning of the increment operation:

1. Extract the `int` value from `counter`.
2. Compute the incremented result.
3. Convert the result back to the required wrapper type.
4. Reassign the reference to the variable `counter`.

The increment does not mutate the internal value of the object held by `previous`.

### 5.2. Wrapper Accumulator Variables Create Extra Conversion Boundaries

Compare these two illustrative snippets:

```java
Integer boxedSum = 0;
for (int value : values) {
    boxedSum += value;
}
```

and:

```java
int primitiveSum = 0;
for (int value : values) {
    primitiveSum += value;
}
```

If `values` is a `List<Integer>`, both loops still unbox the input elements.

However, the first snippet also manages the accumulator variable as a wrapper: on each iteration it extracts the current value to perform the addition and then represents the result as an `Integer` again. The second snippet keeps the running total as a primitive and only needs boxing if and when the value crosses an API boundary that requires an object.

This is why local computation variables should generally be primitive when `null` semantics are not needed and no API mandates a wrapper. Still, do not claim an exact number of allocated objects purely from the iteration count, because caching and JVM optimizations can influence actual allocations.

### 5.3. A Wrapper Does Not Expand the Numeric Range of Its Primitive Type

Addition after unboxing an `Integer` still obeys `int` arithmetic rules. Using `Integer` does not automatically protect against integer overflow.

For large sums, choose an appropriate type for the calculation—such as accumulating in a `long`—or perform explicit overflow checks as required. Simply changing the type of the receiving variable at the end does not always fix an calculation that has already overflowed at an earlier step.

## 6. ==, equals, and Caching

### 6.1. Two Wrapper Operands Are Compared by Reference

Illustrative snippet:

```java
Integer a = 100;
Integer b = 100;
boolean sameReference = a == b;
```

Here, `==` compares object references because both operands have type `Integer`.

For two constant literals of `100`, reference sharing is guaranteed by the boxing rules for specified value ranges. Getting `true` here does not turn `==` into a general value comparison operator for all wrapper instances.

### 6.2. Do Not Rely on Reference Equality Outside the Guaranteed Range

`Integer.valueOf(int)` always caches values from `-128` to `127` and may cache additional values outside that range. Consequently, never write tests or business logic that depend on `==` returning `false` for two wrappers holding the value `1000`.

There are two distinct layers of guarantees to keep separate:

- The JLS specifies conditions under which reference sharing is required when boxing values of certain constant values/ranges.
- The `Integer.valueOf` API specification describes the caching policy of that method.

Neither layer justifies using object identity as a substitute for value equality. See [Integer.valueOf in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

### 6.3. Comparing Values of the Same Type

If two values have type `Integer` and you want a `null`-safe value comparison, you can use:

```java
boolean sameValue = Objects.equals(a, b);
```

Alternatively, call `a.equals(b)` when `a` is guaranteed not to be `null`.

`Integer.equals` requires its argument to be an `Integer` with the same numeric value, so:

```java
Integer.valueOf(1).equals(Long.valueOf(1L))
```

evaluates to `false`. `Objects.equals` does not automatically normalize different numeric wrapper types to a common type.

### 6.4. When One Side Is a Primitive

Illustrative snippet:

```java
Integer boxed = 10;
boolean equal = boxed == 10;
```

In this numeric comparison expression, the boxed operand is unboxed so the comparison is performed on primitive values. If `boxed` is `null`, this throws a `NullPointerException`.

Thus, changing one side of a comparison from `Integer` to `int` can change both the kind of comparison performed and whether an exception can be thrown.

### 6.5. Do Not Use Wrappers as Identity-Based Synchronization Locks

Wrapper objects may be shared and are designed to represent values. Using them as lock objects or relying on their object identity to represent ownership creates dependencies that conflict with the purpose of these types.

Choose an explicit synchronization mechanism or a dedicated lock object with clear ownership semantics instead of locking on a boxed numeric value.

## 7. Overloading: Java Selects the Method at Compile Time

### 7.1. The remove Pitfall on `List<Integer>`

`List` declares both:

```java
E remove(int index);
boolean remove(Object value);
```

These are two method declarations shown for contract comparison, not statements to place directly inside `main`.

Given:

```java
List<Integer> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);
```

the argument `1` has type `int`, so the index-based removal method `remove(int)` is selected. The element removed is `20`.

To remove the value `30`:

```java
boolean removed = values.remove(Integer.valueOf(30));
```

Do not write `values.remove(30)` expecting it to remove the number `30`; that requests removal at index `30` and can throw an out-of-bounds exception.

### 7.2. Changing a Variable's Type Can Change the Selected Overload

Illustrative snippet:

```java
int index = 1;
Integer value = 1;
```

Passing `index` to `remove` selects a different overload than passing `value`. When reading code, always check the compile-time type of the argument rather than just noting that both print out as `1`.

### 7.3. Primitive Widening Does Not Combine Arbitrarily with Boxing

Valid snippet:

```java
List<Long> values = new ArrayList<>();
values.add(1L);
```

The snippet below does not compile:

```java
List<Long> values = new ArrayList<>();
values.add(1);
```

The literal `1` is an `int`; method invocation conversion does not automatically chain primitive widening and boxing (`int → long → Long`) to satisfy a `Long` parameter.

You can use the literal `1L`, cast/convert the expression to `long` before boxing, or call an appropriate factory method. Always examine the conversion context rather than treating autoboxing as a universal numeric converter.

## 8. Numeric Keys in Map and Elements in Set

### 8.1. Lookups Accepting Object Still Require the Matching Value Type

Given:

```java
Map<Integer, String> names = Map.of(1, "one");
```

`names.get(1)` boxes the argument into an `Integer`, matching the existing key type.

However:

```java
names.get(1L);
```

passes a `Long` through the `Object`-typed parameter. It does not automatically convert that `Long` into an `Integer` to match the intended lookup.

In the example map, there is no matching `Long` key, so the result is `null`. The lookup compiles because the method signature accepts `Object`, not because the two numeric types have been unified.

### 8.2. Same Mathematical Value Does Not Imply Equal Wrapper Objects

A `Set<Number>` can contain both `Integer.valueOf(1)` and `Long.valueOf(1)`. Under the equality contracts of these two wrapper classes, they are not equal object values.

If your domain requires treating different numeric representations as equivalent, you must normalize the types or define an explicit comparison relation. Do not rely on boxing to do that for you.

### 8.3. Cost on Each Lookup

Passing a primitive key to a lookup method on a map with wrapper keys creates a boxing boundary at the source level. Depending on the value and the JVM, the temporary wrapper may come from a cache or be optimized.

Do not conclude merely from seeing a `get` call that a long-lived new object is necessarily allocated. Conversely, do not ignore this cost when a hot path performs millions of lookups and profiling measurements show that boxing overhead is significant.

## 9. What Makes Up the Cost of Wrapper Types?

### 9.1. Data Representation

You can visualize the structural difference between a primitive array and a wrapper list as follows:

```text
int[]:
    a single array object holding int values directly

ArrayList<Integer>:
    ArrayList object
        -> internal array storing references
              -> referenced Integer objects
```

This is a conceptual model of the representational components, not an exact byte layout for every JVM.

An `ArrayList` may have a capacity larger than the number of elements currently stored. Beyond the wrapper objects themselves, you must account for the list object structure and its backing reference array. Similarly, `Integer[]` is an array of references to wrapper objects; it is not laid out like `int[]`.

### 9.2. Memory Footprint Has No Fixed Ratio Across All JVMs

An `int` has a 32-bit value range, but from that fact alone you cannot deduce the exact number of bytes that one million `Integer` elements will occupy across every configuration.

The actual footprint depends on:

- Object headers and array headers.
- Reference size (e.g., compressed oops vs. 64-bit references).
- Object alignment and padding.
- Unused capacity in the collection.
- The number of distinct wrapper instances actually referenced.
- Shared instances from caches or elsewhere.
- JVM memory layout and runtime optimizations.

Two collection slots referencing the same `Integer` instance do not create two separate wrapper objects. Conversely, the same numeric value outside the cache range may be represented by multiple distinct wrapper objects. You must distinguish between the number of elements, the number of distinct numeric values, and the number of distinct wrapper objects.

### 9.3. Allocation and Garbage Collection

If a computation creates many short-lived wrapper objects, it can increase the allocation rate and the volume of young-generation garbage to collect.

If a collection retains many wrapper objects over a long period, they increase the live set size and heap occupancy. These two effects are distinct: high short-term allocation churn is not the same problem as high long-term memory retention.

Not every temporary wrapper survives JVM optimization. However, objects stored into an externally observable data structure cannot simply be assumed away.

### 9.4. Data Access and Locality

For large numeric datasets, traversing references to separate heap objects can exhibit very different memory access characteristics compared to scanning a contiguous primitive array. CPU cache utilization and the total volume of memory traffic can significantly affect execution time.

This is why the cost of wrapper types is not just a single `intValue()` call. It often lies in the overall shape and layout of the data in memory.

### 9.5. Big-O Does Not Capture Every Cost

A loop summing an `int[]` and a loop summing a `List<Integer>` are both `O(n)`. That does not guarantee similar wall-clock time, memory footprint, or allocation behavior.

Conversely, an efficient hash or tree lookup on a wrapper-based map can still outperform a linear scan over a primitive array. Before optimizing away boxing, make sure you have chosen the right data structure and algorithm for the problem.

## 10. Reducing Cost While Preserving the Right Data Model

### 10.1. Keep Local Calculations Primitive

When you do not need to represent `null`, counters and accumulators should normally be primitive types such as `int` or `long`, chosen according to the required value range.

Box only when crossing an object-based API boundary. Doing so makes conversion boundaries obvious and avoids trapping intermediate variables in an unnecessary unbox–compute–box cycle.

### 10.2. Choose Primitive Arrays When the Problem Fits

`int[]`, `long[]`, or `double[]` are a good fit when:

- The data primarily serves numerical computation.
- Sizing and updates fit an array model.
- Per-element `null` representation is not needed.
- You do not directly need set or map collection semantics.

Do not rewrite every `List<Integer>` into an array simply because you heard boxing has a cost. Weigh code clarity, flexibility, and the cost of converting back and forth at API boundaries.

### 10.3. Use Primitive Streams Where Appropriate

`IntStream`, `LongStream`, and `DoubleStream` provide specialized streams for primitive numbers.

For example:

```java
int sum = IntStream.of(1, 2, 3).sum();
```

There is no need to represent each intermediate element as an `Integer` inside a `Stream<Integer>` just to compute a sum.

If the source is already a list of wrappers:

```java
int sum = values.stream().mapToInt(Integer::intValue).sum();
```

unboxing still has to happen when going from each `Integer` element to `int`. This idiom does not magically erase wrappers already stored in the source collection, and you still need a clear policy if the collection can contain `null`.

If the sum requires a `long`, use the appropriate reduction or `LongStream` conversion; `IntStream.sum()` returns an `int` and does not automatically prevent overflow.

### 10.4. boxed() Brings Data Back to Object Form

Illustrative snippet:

```java
List<Integer> result = IntStream.of(1, 2, 3).boxed().toList();
```

The `boxed()` method converts a primitive stream into a wrapper stream so that it can be collected into a reference-based collection.

Avoid switching to a primitive stream to save boxing only to call `boxed()` immediately afterward for no reason. However, if the output API requires a `List<Integer>`, `boxed()` at the final boundary is completely reasonable. See [IntStream in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).

### 10.5. Initial Capacity Does Not Eliminate Boxing

`new ArrayList<Integer>(expectedSize)` can reduce backing-array resizing and reference-array copying when adding many elements.

It does not turn the backing storage into an `int[]`, does not pre-create wrapper objects, and does not eliminate boxing conversions at the element boundary.

Keep collection capacity tuning separate from element representation tuning.

### 10.6. Specialized Primitive Collections Are a Separate Option

When numeric datasets are large and profiling shows that wrappers are a genuine bottleneck, you can evaluate specialized primitive data structures—either custom array-backed structures or suitable third-party libraries.

Selecting such a library requires evaluating its API design, missing-value semantics, ecosystem integration, and boundary conversion costs. Primitive specialization does not automatically fit every domain requirement.

## 11. Measuring Performance So Your Conclusions Hold Up

### 11.1. Ask a Specific Question

Do not merely ask "how slow is boxing?". Pick a concrete workload:

- Build a collection once and read it many times.
- Continuously add and remove elements.
- Compute a sum over existing data.
- Look up numeric keys in a map.
- Update frequency counters.
- Pass numeric data across API boundaries.

Each workload can have a very different dominant cost source.

### 11.2. Separate Data Construction from Data Processing

If you are measuring a summation loop, building the `List<Integer>` outside the timed region versus inside it represents two completely different experiments.

If your goal is to measure an end-to-end application pipeline, data construction cost may belong inside the measurement. If your goal is to compare read/traversal costs, isolate the read phase explicitly.

### 11.3. Use Representative Data

Vary key experimental factors deliberately:

- Dataset size.
- Values inside versus outside the standard wrapper cache range.
- Iteration count and degree of object reuse.
- Presence or absence of `null`.
- Read-to-write ratio.
- Whether results are retained or returned externally.

An experiment that only uses small cached integers can easily produce allocation conclusions that fail to represent real production data.

### 11.4. Avoid Misleading Ad-Hoc Timing

First-run timing is heavily skewed by class loading, initialization, and JIT warm-up/compilation. Dead-code elimination can also optimize away computations whose results are never consumed, causing an experiment to no longer measure the intended work.

When you need a JVM microbenchmark, use a purpose-built harness such as [OpenJDK JMH](https://github.com/openjdk/jmh) with proper warm-up iterations, measurement iterations, and result consumption (`Blackhole` / return values). Also track allocation rates and GC metrics when the question involves memory overhead.

This article deliberately omits fixed time-ratio or memory-ratio numbers because such numbers depend on the exact hardware, JVM configuration, and workload shape. Measurement is what tells you whether a representation change is worth making.

## 12. Complete Java Program

The following program observes boxing, unboxing, overload selection, and `null`-related failures. It is not a benchmark and does not use execution time to infer performance costs.

Save as `BoxingInCollectionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.IntStream;

public class BoxingInCollectionsDemo {
    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(10);
        scores.add(20);

        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        System.out.println("scores: " + scores);
        System.out.println("primitive sum: " + sum);

        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("small cached identity: " + (smallA == smallB));

        Integer largeA = 1000;
        Integer largeB = 1000;
        System.out.println("large value equality: "
                + Objects.equals(largeA, largeB));

        Integer counter = 1000;
        Integer previous = counter;
        counter++;
        System.out.println("previous: " + previous + ", counter: " + counter);

        List<Integer> ids = new ArrayList<>(List.of(10, 20, 30));
        int removedByIndex = ids.remove(1);
        boolean removedByValue = ids.remove(Integer.valueOf(30));
        System.out.println("removed by index: " + removedByIndex);
        System.out.println("removed by value: " + removedByValue);
        System.out.println("remaining ids: " + ids);

        Map<String, Integer> counts = new HashMap<>();
        counts.put("known", 2);

        Integer missing = counts.get("missing");
        try {
            int count = missing;
            System.out.println("unexpected count: " + count);
        } catch (NullPointerException ex) {
            System.out.println("missing value unboxing: NullPointerException");
        }

        counts.put("unknown", null);
        try {
            int count = counts.getOrDefault("unknown", 0);
            System.out.println("unexpected default: " + count);
        } catch (NullPointerException ex) {
            System.out.println("mapped null with default: NullPointerException");
        }

        Integer optionalCount = counts.get("unknown");
        int safeCount = optionalCount == null ? 0 : optionalCount;
        System.out.println("explicit null policy: " + safeCount);

        Map<Integer, String> names = Map.of(1, "one");
        System.out.println("Integer key: " + names.get(1));
        System.out.println("Long key present: " + names.containsKey(1L));

        int streamSum = IntStream.of(1, 2, 3).sum();
        List<Integer> boxedValues = IntStream.of(1, 2, 3).boxed().toList();
        System.out.println("IntStream sum: " + streamSum);
        System.out.println("boxed stream values: " + boxedValues);

        List<Long> longValues = new ArrayList<>();
        longValues.add(1L);
        System.out.println("Long elements: " + longValues);

        Integer nullable = null;
        boolean useNullable = true;
        try {
            Integer chosen = useNullable ? nullable : 0;
            System.out.println("unexpected chosen: " + chosen);
        } catch (NullPointerException ex) {
            System.out.println("mixed conditional: NullPointerException");
        }
    }
}
```

Compile and run:

```shell
javac --release 17 BoxingInCollectionsDemo.java
java BoxingInCollectionsDemo
```

Expected output:

```text
scores: [10, 20]
primitive sum: 30
small cached identity: true
large value equality: true
previous: 1000, counter: 1001
removed by index: 20
removed by value: true
remaining ids: [10]
missing value unboxing: NullPointerException
mapped null with default: NullPointerException
explicit null policy: 0
Integer key: one
Long key present: false
IntStream sum: 6
boxed stream values: [1, 2, 3]
Long elements: [1]
mixed conditional: NullPointerException
```

### 12.1. Conversion Boundaries

`scores.add(10)` and `scores.add(20)` require boxing. The loop using `int score` requires unboxing each element read from the list.

The variable `sum` stays primitive throughout the addition, avoiding maintaining the running total as an `Integer` on every iteration.

### 12.2. Deliberate Comparisons

The `small cached identity` line uses two constant literals of `100`, which fall within the range guaranteed to share references.

For `1000`, the program prints only value equality via `Objects.equals`; it deliberately avoids hardcoding an `==` result, which should never be relied upon as a business rule for this case.

### 12.3. null Failures in Different Places

Three separate `try` blocks demonstrate distinct failure sites:

- Unboxing a missing lookup result from a map.
- Unboxing a `null` value preserved by `getOrDefault` because the key is present and mapped to `null`.
- Unboxing inside a mixed wrapper–primitive conditional (`?:`) expression.

Catching `NullPointerException` here only serves the demonstration so the program can continue printing subsequent cases. In production code, decide on a clear data policy upfront and check explicitly rather than catching `NullPointerException` as normal control flow for missing values.

### 12.4. Object-Accepting APIs Do Not Unify Numeric Types

A map with `Integer` keys finds `1`, but has no `Long` key matching `1L`. Both calls compile cleanly; the different outcomes stem from runtime type semantics and `equals`.

### 12.5. Primitive Streams and Output Boundaries

Summing via `IntStream` operates on a primitive pipeline. When calling `boxed().toList()`, the program explicitly converts the elements into wrapper objects to satisfy the list output type.

Do not use the printed output `[1, 2, 3]` to infer how many objects were actually allocated at runtime. Only profiling/measurement tools on a specific JVM can answer that question.

## 13. Mistakes to Spot When Reviewing Numeric Collection Code

### 13.1. Using Wrappers Everywhere Just Because the Collection Uses Wrappers

The fact that a list requires `Integer` does not mean every counter, loop index, or intermediate calculation variable should also be declared as `Integer`.

Keep variables primitive wherever a value is always present, and box only when crossing a reference-based API boundary.

### 13.2. Replacing null with 0 Without Considering Domain Meaning

`0` can be an actual measured quantity, whereas `null` can mean unknown, missing data, or not applicable.

Conflating these states may prevent an exception while silently producing wrong business results. Choose your data semantics before reaching for a terse fallback expression.

### 13.3. Using == Because a Small-Number Example Happened to Work

Wrapper caching makes reference-equality bugs easy to miss on small test inputs. Always choose the comparison operator according to your intent: reference identity, same-type value equality, or normalized numeric comparison.

Never generalize the behavior of a single small value into a rule for all wrapper instances.

### 13.4. Assuming ++ Mutates an Integer Object In Place

Wrapper instances are immutable values. Incrementing a wrapper variable updates that variable (or target slot) to refer to a different wrapper value; it does not mutate the existing object seen by other references.

In a `for-each` loop with an `Integer value` loop variable, writing `value++` does not update the element inside the list. To modify collection contents, use an appropriate collection update operation.

### 13.5. Optimizing the Wrong Cost Source

A program that is slow due to repeated linear searches will not necessarily be fixed by eliminating boxing. A program that consumes excessive memory might be suffering from oversized collection capacities, outer wrapper objects, or unnecessary data retention.

Measure and analyze the entire processing path, and preserve exact domain behavior whenever you change data representations.

## 14. Exercises and Self-Check Criteria

### Exercise 1: Mark the Conversion Boundaries

Given the following code:

```java
List<Integer> values = new ArrayList<>();
values.add(5);
values.add(8);

long sum = 0;
for (int value : values) {
    sum += value;
}

Integer result = values.get(0) + values.get(1);
```

Identify where boxing and unboxing occur.

Guided answer:

- The two `add` calls with `int` literals require boxing to match the `Integer` element type.
- The `int` loop variable requires unboxing each element from `values` (followed by widening to `long` when added to `sum`).
- The final addition unboxes both elements retrieved by `get`, adds them as `int`, and then boxes the result into `Integer` for `result`.
- Do not infer the exact number of runtime object allocations purely from the number of conversion sites.

### Exercise 2: Design a Policy for Missing Data

Suppose a map contains:

```text
"known"   -> 3
"unknown" -> null
"missing" -> no mapping
```

Design two versions of a lookup routine:

1. Treat both `unknown` and `missing` as `0`.
2. Distinguish a missing key from a present key whose value is unknown (`null`).

Both versions must avoid unintentional `null` unboxing. Explain why a single `getOrDefault` call is insufficient to implement both policies cleanly.

### Exercise 3: Remove the Intended Number

Starting from the list `[1, 2, 3]`:

- Remove the element at index `1`.
- On a fresh copy of the list, remove the value `1`.

The resulting lists must be `[1, 3]` and `[2, 3]`, respectively. State the compile-time argument type that selects each `remove` overload.

### Exercise 4: Null-Safe Value Comparison

Design a check that tests whether two `Integer` references represent the same value when either or both may be `null`.

Then test an `Integer` and a `Long` representing the same mathematical number. Explain why `Objects.equals` does not automatically treat them as equal.

### Exercise 5: Analyze Instead of Guessing Costs

Suppose one million numeric values need to be summed repeatedly. Compare the following options:

- `int[]`.
- `List<Integer>`.
- A primitive stream over an array.
- Streaming a `List<Integer>` with `mapToInt`.

Before measuring, specify clearly whether data construction cost is included, what return type the sum uses, whether `null` values must be supported, and whether the data values fall inside or outside the standard wrapper cache range.

Do not state a conclusion claiming a fixed speedup factor without representative measurements.

## 15. Questions You Should Be Able to Answer

1. Why is `List<Integer>` valid while `List<int>` is invalid in Java 17?
2. Where do conversions happen when adding an `int` to a collection and later reading it back into an `int`?
3. Why doesn't boxing necessarily allocate a brand-new object every time?
4. Why does unboxing `null` throw an exception instead of producing `0`?
5. Why can `getOrDefault` still lead to an unboxing `NullPointerException`?
6. Why does comparing two wrappers with `==` behave differently from comparing a wrapper with a primitive?
7. Does wrapper caching make `==` a reliable value comparison?
8. Are an `Integer` and a `Long` that both represent `1` equal according to `equals`?
9. Why does `remove(1)` on a `List<Integer>` remove by index rather than by value?
10. Why isn't `List<Long>.add(1)` automatically converted via primitive widening followed by boxing?
11. Why does an `Integer sum` accumulator inside a loop introduce extra conversion boundaries compared to `int sum`?
12. What structural components make the memory footprint of a wrapper collection different from that of a primitive array?
13. When does `mapToInt` help keep processing in the primitive domain, and when does `boxed()` bring data back into object form?
14. What factors must a microbenchmark control to avoid misleading conclusions?

The goal is to recognize the boundary between primitive values and object references, handle `null` according to domain meaning, and evaluate costs across your entire data layout and processing pipeline. Autoboxing makes code concise; it does not merge the two models into one.
