# Stream.toList(), collect(), and reduce(): Choosing a Terminal Operation by Result Type

## Lesson Objectives

In the Java Stream API, **`toList()`, `collect()`, and `reduce()` are all terminal operations**: they trigger pipeline processing to produce a result. However, the three APIs are not the same:

- **`toList()`**: collects the elements of a Stream into an **unmodifiable `List<T>`**.
- **`collect()`**: performs **mutable reduction** or uses a `Collector` to produce the desired result type, such as a `List`, `Set`, `Map`, joined string, grouped data, or summary statistics.
- **`reduce()`**: combines multiple elements into a single result through an **associative reduction**, typically a sum, product, maximum, or an immutable aggregated value.

Choosing the right operation does not just determine whether a statement is short or long. It determines **the return data type, mutability, empty Stream handling, correctness in parallel execution, and storage cost**.

After this lesson, you will be able to read the key signatures, design a pipeline with a clear result type, apply common `Collectors`, avoid the `reduce` mistake with a mutable accumulator, and verify a Java 17 program from input data to stdout.

## 1. Terminal Operations End a Pipeline

A Stream pipeline typically has three parts:

```text
Data source
    → intermediate operations (map / filter / sorted / ...)
    → terminal operation (toList / collect / reduce / ...)
    → result
```

Example:

```java
List<String> names = products.stream()
        .filter(p -> p.active())
        .map(p -> p.name())
        .toList();
```

This is **illustrative code**, requiring `products` and an element type with appropriate `active()` and `name()` methods to be defined. `filter` and `map` build the pipeline description; `toList` is the terminal operation that requests data processing to produce the list.

After using a terminal operation, **the same Stream must not be reused** as a new source:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3);
List<Integer> list = numbers.toList();

// Do not do this: numbers has already been consumed.
// long count = numbers.count();
```

If the source is a re-traversable collection, create a new Stream with `collection.stream()`. If the source is I/O or an infinite Stream, a separate design must be considered.

### Choose the Output Before Choosing the Method

| Business Result Needed | Usually Suitable Tool |
| --- | --- |
| A list of elements that does not need to be modified afterward | `stream.toList()` |
| A list where elements can be added/removed after collecting | `collect(toCollection(ArrayList::new))` |
| A set without duplicate elements | `collect(toSet())` or `toCollection(...)` |
| A Map by key and value | `collect(toMap(...))` |
| A Map grouping elements by a criterion | `collect(groupingBy(...))` |
| A string joined from multiple strings | `collect(joining(...))` or an appropriate reduce approach |
| Sum, product, min, max, a single aggregated value | `reduce(...)` or a primitive stream terminal such as `sum()` |
| Multiple numeric statistics | `collect(summarizingInt(...))` or `mapToInt(...).summaryStatistics()` |

The table is a selection guide, not a requirement to use only one API. A result can be produced in multiple ways; prioritize **type contract, business meaning, and correctness**.

## 2. Stream.toList(): Unmodifiable List Result

### 2.1. Syntax and Return Type

Since Java 16, `Stream<T>` has the terminal operation:

```java
List<T> toList()
```

Example:

```java
List<String> names = Stream.of("Lan", "An", "Mai")
        .toList();

System.out.println(names); // [Lan, An, Mai]
```

`toList()` collects elements into a `List<T>`, preserving **encounter order if the Stream has an encounter order**. For example, the source `Stream.of("Lan","An","Mai")` is ordered, so the result follows that same order. If the source is unordered, do not attach business meaning to an unguaranteed order.

**Important point:** the list from `Stream.toList()` is **unmodifiable**. Operations such as `add`, `remove`, `clear`, or `set` that mutate the list will throw `UnsupportedOperationException`:

```java
List<String> names = Stream.of("Lan", "An").toList();
names.add("Mai"); // UnsupportedOperationException
```

"Unmodifiable" refers to **the structure of the List**, and does not automatically make the element objects immutable. If an element is a mutable object, code holding a reference to that object can still mutate the object's internal state.

Java does not require `toList()` to return a specific `ArrayList`, nor does it promise that the list is serializable or has a stable identity suitable for synchronization. Do not depend on the implementation class name or identity comparison `==`.

### 2.2. Does Stream.toList() Accept null?

`Stream.toList()` does not enforce a ban on null elements like `List.of(...)` does. Example with a reference Stream:

```java
List<String> values = Stream.of("A", null, "B").toList();
System.out.println(values); // [A, null, B]
```

The example above is valid in Java 17. However, **allowing null does not mean null should be included in business results**. A pipeline containing null can cause an NPE in `map(String::length)`, upon dereferencing, or when passed to an API that disallows null.

If a list without null is required, you can filter intentionally:

```java
List<String> safe = Stream.of("A", null, "B")
        .filter(Objects::nonNull)
        .toList(); // [A, B]
```

This snippet requires importing `java.util.Objects`. Only filter if dropping elements with missing data is a valid policy; if null is a data error, validate and report an error instead of silently ignoring it.

### 2.3. toList() Does Not Automatically Create a Deep Snapshot

If the source is a `List<Person>` with mutable `Person` objects, the returned list may contain **the same references** to those objects. The List itself does not allow `set` or `add`, but updating `person.setName(...)` through an existing reference can still change the content observed when reading the object. If truly immutable data is needed, create immutable value objects or copy intentionally.

### 2.4. When to Prefer toList()?

Use `toList()` when the result is a list for reading, returning from a service, displaying in the UI, or passing across layers without needing structural modification. It is concise, states intent clearly, and avoids false expectations about mutability. If the caller is allowed to modify the list, provide a mutable collection type according to the contract rather than letting the caller hit an unexpected exception.

## 3. collect(): Producing Many Result Types via Collector

`collect()` has two main forms on `Stream<T>`. The common form uses a `Collector`:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

Where:

- `T` is the input element type.
- `A` is the **intermediate accumulation** container type used by the Collector; it does not have to be the same as the final result.
- `R` is the **result type** obtained.
- A Collector describes how to create an accumulator, add elements, combine partial results, and optionally transform the container into the final result.

`Collectors` in `java.util.stream.Collectors` provides many factories for standard Collectors. Therefore, `collect` is not limited to lists.

### 3.1. Collectors.toList() and Differences from Stream.toList()

```java
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());
```

Requires importing `java.util.List`, `java.util.stream.Stream`, and `java.util.stream.Collectors`. The result has type `List<String>`, but **the contract of `Collectors.toList()` does not guarantee the concrete List type, mutability, serializability, or thread-safety**. Do not assume "`collect(toList())` is definitely a mutable `ArrayList`" just because a particular JDK returned one.

Comparison:

| Usage | List Contract |
| --- | --- |
| `stream.toList()` | **Unmodifiable** `List<T>`, preserves encounter order if present |
| `stream.collect(Collectors.toList())` | `List<T>`, **no guarantee** of mutability |
| `stream.collect(Collectors.toUnmodifiableList())` | Unmodifiable `List<T>`, **disallows null elements** |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Exact collection type created, e.g., mutable `ArrayList<T>` |

If it is read-only, `toList()` is a great fit. If **mutability is required**, request it explicitly with `toCollection`:

```java
ArrayList<String> names = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));
names.add("C"); // valid
```

This example requires importing `java.util.ArrayList`. `toCollection` is also useful if you need a `LinkedHashSet` to deduplicate in encounter order in specific situations.

### 3.2. Collectors.toSet() and Element Order

```java
Set<String> tags = Stream.of("java", "api", "java")
        .collect(Collectors.toSet()); // contains "java" and "api"
```

`toSet()` removes duplicates according to Set equality; **it does not guarantee the Set type, mutability, or iteration order**. Do not print a default Set and assert a specific order in tests.

If you need to preserve the encounter order of an ordered source:

```java
LinkedHashSet<String> tags = Stream.of("java", "api", "java")
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

With `LinkedHashSet`, the result iterates in the order elements first appeared in the provided data. This snippet requires importing `java.util.LinkedHashSet`.

### 3.3. Collectors.toMap(): Map Result

```java
Map<String, Integer> lengths = Stream.of("Java", "Go")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length
        ));
```

Requires importing `Map`, `Function`, `Collectors`, and `Stream`. The result maps `"Java" -> 4` and `"Go" -> 2`. **Do not rely on the print order of a default Map as a contract**, because `toMap` does not promise any implementation type or order for the resulting Map.

If multiple elements produce the **same key**, the standard `toMap(keyMapper, valueMapper)` overload throws `IllegalStateException` on duplicate keys, rather than silently keeping one value. You must specify a resolution policy:

```java
Map<String, Integer> latest = Stream.of("aa", "ab")
        .collect(Collectors.toMap(
                s -> s.substring(0, 1),
                String::length,
                (oldValue, newValue) -> newValue
        )); // key "a" has value 2
```

If source order affects a first/last policy, you need to understand encounter order and parallel processing; the callback should satisfy the requirements related to associativity. If the goal is to store **all** values per key, `groupingBy` is usually more appropriate than keeping only one value.

You can request a Map with insertion order:

```java
Map<String, Integer> counts = Stream.of("A", "BB")
        .collect(Collectors.toMap(
                Function.identity(),
                String::length,
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));
```

The example requires importing `java.util.LinkedHashMap`. The last argument is `mapFactory`, which determines the resulting Map type. This is useful for verifiable output and reports that require a chosen order.

### 3.4. Collectors.groupingBy(): Grouping Data

`groupingBy(classifier)` is used to group elements by a key:

```java
Map<String, List<String>> groups = Stream.of(
                "java", "javascript", "go")
        .collect(Collectors.groupingBy(s -> s.substring(0, 1)));
```

The result has group `"j"` containing `"java"` and `"javascript"`, and group `"g"` containing `"go"`. Do not rely on the print order of a default Map. You can pass a downstream Collector so that instead of storing the whole object, only a property is stored:

```java
Map<String, List<String>> groupedNames = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                LinkedHashMap::new,
                Collectors.mapping(
                        Product::name,
                        Collectors.toList()
                )
        ));
```

This is an illustrative snippet; the `Product` class is fully defined in the main program. `groupingBy` splits by category, `mapping` extracts the product name, and the downstream `toList` collects the names. Using `LinkedHashMap::new`, the resulting Map has key insertion order in the sequential example; **do not assume the downstream lists are mutable**.

Some common downstream Collectors:

- `counting()`: counts the number of elements per group, returning `Long`.
- `summingInt(...)` or `summingLong(...)`: sums a numeric property per group.
- `mapping(mapper, downstream)`: transforms elements and passes them to the inner Collector.
- `collectingAndThen(downstream, finisher)`: applies a finishing step after collecting.

### 3.5. Collectors.joining(): A Single String Result

```java
String text = Stream.of("Java", "Stream", "API")
        .collect(Collectors.joining(" | "));

System.out.println(text); // Java | Stream | API
```

`joining` is only for Streams of `CharSequence` elements (such as `String`); for Streams of other objects, use `map` first to obtain a string representation. This is a Collector that produces a `String` result, not a List.

## 4. Three-Argument collect(): Mutable Reduction

In addition to the form that accepts a Collector, `Stream<T>` also has:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner)
```

The purpose is to create a **mutable container**, then sequentially insert elements and combine partial containers. Example:

```java
ArrayList<String> result = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(result); // [A, B, C]
```

This is valid illustrative code inside a method with `ArrayList` and `Stream` imported. `supplier` creates an empty ArrayList; `accumulator` adds an element; `combiner` merges data from the second container into the first when needed. With a parallel Stream, partial containers can be combined according to the Collector rules. **Do not create a single shared ArrayList for all threads and skip synchronization**.

The three-argument form is suitable when there is a natural mutable accumulation approach. When a standard Collector already exists, `collect(Collectors.toCollection(...))` or `groupingBy(...)` is usually easier to read and less error-prone.

## 5. reduce(): Combining Elements into a Single Result

`reduce` is used to **combine elements through an operation suitable for associative reduction**. For a numeric reduction:

```java
int sum = Stream.of(1, 2, 3)
        .reduce(0, Integer::sum); // 6
```

Here:

- `0` is the **identity** of addition: `0 + x = x`.
- `Integer::sum` is the combining operation that yields the sum of two elements.
- Addition in Java's integer domain (with `int` overflow rules) is associative under modulo arithmetic at the `int` representation level, but **does not guarantee the mathematical sum will not overflow**. If values can be large, choose an appropriate numeric type or overflow-checking mechanism.

Do not confuse `reduce` with `collect`: `reduce` typically builds a **result value** from previous values, whereas `collect` typically **mutates an accumulation container**. Using `reduce` to `add` into an `ArrayList` and return the same list is an anti-pattern, especially in a parallel Stream.

### 5.1. reduce(identity, accumulator) Returning T

Signature:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

Example:

```java
int count = Stream.of(2, 3, 1)
        .reduce(0, Integer::sum); // 6
```

With an empty source, the result is `identity` — for example, the sum of an empty Stream with identity `0` is `0`. You must choose a **neutral** identity for the combination operation:

- Sum: `0`.
- Product: `1`.
- String concatenation: `""` if the combination is appropriate string concatenation.
- Do not pick an arbitrary identity just to avoid handling the empty case.

If the identity is wrong, the result of a parallel reduction can be wrong even when the sequential version looks right.

### 5.2. reduce(accumulator) Returning Optional<T>

Signature:

```java
Optional<T> reduce(BinaryOperator<T> accumulator)
```

There is no identity, so if the Stream is empty, the result is `Optional.empty()`:

```java
Optional<Integer> maximum = Stream.of(4, 8, 3)
        .reduce(Integer::max); // Optional[8]

boolean empty = Stream.<Integer>empty()
        .reduce(Integer::max)
        .isEmpty(); // true
```

This is the natural choice when **there is no meaningful identity** for the case with no elements. For example, "the max of an empty list" is different from "max equals 0". For summation, identity `0` can be used if the statistical contract expects an empty sum to be 0.

**Note on `null`:** `reduce(BinaryOperator<T>)` is not suitable for using `null` as a meaningful reduction result; a `null` result from the combining operation can cause a `NullPointerException`. When processing data that may contain null, clarify the policy at the source or use a suitable structure to represent absence.

### 5.3. reduce(identity, accumulator, combiner) Returning U

Signature:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
```

This form allows the result type `U` to **differ from the element type `T`**. Example with `Product`:

```java
long revenue = products.stream().reduce(
        0L,
        (total, p) -> total + p.units() * p.unitPriceCents(),
        Long::sum
);
```

If `products` is a `Stream<Product>`, `U = Long` and `T = Product`. The identity is `0L`; the accumulator takes the running total and a Product and returns a **new total**; the combiner merges two partial totals. The goal is to obtain a `long` value, not to build a List.

In the case of a primitive numeric sum, a simpler and often more efficient approach is:

```java
long revenue = products.stream()
        .mapToLong(p -> p.units() * p.unitPriceCents())
        .sum();
```

These are two **separate** ways to compute the same data. `mapToLong().sum()` is usually shorter, avoids intermediate wrapper objects from generic reduce, and expresses intent clearly; the three-argument `reduce` example helps illustrate when changing the result type is needed.

## 6. Why Does reduce Require Associativity and a Correct Identity?

For a Stream to split work across multiple data partitions, `reduce` requires an **associative accumulator** and a suitable neutral identity.

For elements `a,b,c`, grouping `(a ⊕ b) ⊕ c` and `a ⊕ (b ⊕ c)` must yield equivalent results within the scope of the chosen operation. Integer addition, integer multiplication, and ordered string concatenation are associative under their appropriate semantics; subtraction does not have this property:

```java
int result = Stream.of(10, 3, 2)
        .reduce(0, (a, b) -> a - b);
```

The snippet above compiles, but using subtraction as the accumulator for a parallel reduction **violates the associativity requirement**, so the result of a parallel pipeline should not be treated as a reliable business value. Replace it with an associative reduction or another design that clearly expresses the computation.

### 6.1. Do Not Use a Wrong Identity

```java
int total = Stream.of(1, 2, 3)
        .reduce(10, Integer::sum);
```

This is an example of a **non-neutral identity**. When run sequentially, the value is `16`; however, `10` is not the identity of addition, and when split/merged in parallel it may be applied across multiple branches, producing a non-equivalent result. The correct version is `reduce(0, Integer::sum)` if you want to compute the sum.

### 6.2. The Combiner Must Be Compatible with the Accumulator

With three-argument `reduce`, `combiner` is not an arbitrary function. It must properly combine two intermediate results and be compatible with how `accumulator` incorporates each element into the aggregated state.

For the revenue problem:

- Identity `0L` is neutral.
- Accumulator adds the monetary value of one Product to the total.
- Combiner `Long::sum` merges two totals.
  
All three components express addition, so they are suitable for parallel processing in this example. If the accumulator computes a sum but the combiner multiplies two totals, the result will be wrong when the pipeline is split into multiple parts.

### 6.3. Avoid Mutable State in reduce

The following approach is an anti-pattern:

```java
// Do not use to build a List in a parallel Stream:
List<String> wrong = names.stream().reduce(
        new ArrayList<String>(),
        (list, name) -> {
            list.add(name);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

This is an **illustrative snippet that should not be used**, assuming `names` is available and appropriate imports are present. It mutates the accumulator instead of creating a new result. With reduce, the identity can be shared across processing branches; mutating the object used as the identity violates the assumption required for safe reduction and can cause incorrect results or data races.

To create a list, use `toList()` or `collect(toCollection(...))`; do not try to replace a Collector with a mutable reduce.

## 7. Comparing All Three Approaches Side by Side on the Same Data

Suppose we have product data:

```java
record Product(String name, String category, int units,
               long unitPriceCents) {}

List<Product> products = List.of(
        new Product("Book", "office", 2, 1250),
        new Product("Pen", "office", 3, 200),
        new Product("Tea", "food", 1, 700)
);
```

This is the data portion of the complete program below.

### 7.1. Need an Unmodifiable List of Names

```java
List<String> names = products.stream()
        .map(Product::name)
        .toList(); // [Book, Pen, Tea]
```

Use `toList()` because only a read-only list is needed.

### 7.2. Need a List for Further Updates

```java
ArrayList<String> editable = products.stream()
        .map(Product::name)
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("Extra"); // valid
```

Use `toCollection(ArrayList::new)` so the mutable contract is explicit.

### 7.3. Need a Map Grouping Names by Category

```java
Map<String, List<String>> groups = products.stream().collect(
        Collectors.groupingBy(
                Product::category,
                LinkedHashMap::new,
                Collectors.mapping(Product::name, Collectors.toList())
        )
);
```

The result in insertion order for the example is `{office=[Book, Pen], food=[Tea]}`. Use a Collector because a **Map containing Lists** is needed rather than a single value.

### 7.4. Need Total Revenue

```java
long revenue = products.stream().reduce(
        0L,
        (sum, p) -> sum + p.units() * p.unitPriceCents(),
        Long::sum
); // 3800
```

Use `reduce` because only a single aggregated numeric value is needed. You can also use `mapToLong(...).sum()` to express the goal more clearly and avoid boxing where appropriate.

## 8. Complete Java 17 Program

The example below is designed to verify **three types of output**, including an unmodifiable List, a mutable ArrayList, an ordered Map, reduce operations, and empty/null Stream cases.

Create the file **`StreamTerminalResultsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamTerminalResultsDemo {
    record Product(String name, String category,
                   int units, long unitPriceCents) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Book", "office", 2, 1250),
                new Product("Pen", "office", 3, 200),
                new Product("Tea", "food", 1, 700)
        );

        List<String> names = products.stream()
                .map(Product::name).toList();
        System.out.println("toList: " + names);
        try {
            names.add("Extra");
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList mutable: false");
        }

        ArrayList<String> editable = products.stream()
                .map(Product::name)
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Extra");
        System.out.println("Mutable: " + editable);

        Map<String, List<String>> grouped = products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Product::name, Collectors.toList())
                ));
        System.out.println("Grouped: " + grouped);

        Map<String, Integer> unitsByName = products.stream().collect(
                Collectors.toMap(
                        Product::name,
                        Product::units,
                        (oldValue, newValue) -> oldValue,
                        LinkedHashMap::new
                ));
        System.out.println("Map: " + unitsByName);

        int unitCount = products.stream()
                .map(Product::units)
                .reduce(0, Integer::sum);
        long revenue = products.stream().reduce(
                0L,
                (total, p) -> total + p.units() * p.unitPriceCents(),
                Long::sum);
        System.out.println("Units reduce: " + unitCount);
        System.out.println("Revenue reduce: " + revenue);
        System.out.println("Max price: " + products.stream()
                .map(Product::unitPriceCents)
                .reduce(Long::max).orElseThrow());

        System.out.println("Joined: " + products.stream()
                .map(Product::name)
                .collect(Collectors.joining(", ")));

        System.out.println("Parallel units: " + products.parallelStream()
                .map(Product::units)
                .reduce(0, Integer::sum));

        System.out.println("Empty reduce: "
                + Stream.<Integer>empty()
                        .reduce(Integer::sum).isEmpty());

        System.out.println("Null in toList: "
                + Stream.of("A", null, "B").toList());
    }
}
```

Compile/run with JDK 17 or newer:

```bash
javac StreamTerminalResultsDemo.java
java StreamTerminalResultsDemo
```

**Exact stdout:**

```text
toList: [Book, Pen, Tea]
toList mutable: false
Mutable: [Book, Pen, Tea, Extra]
Grouped: {office=[Book, Pen], food=[Tea]}
Map: {Book=2, Pen=3, Tea=1}
Units reduce: 6
Revenue reduce: 3800
Max price: 1250
Joined: Book, Pen, Tea
Parallel units: 6
Empty reduce: true
Null in toList: [A, null, B]
```

### Result Analysis

1. `products.stream().map(Product::name).toList()` returns `[Book, Pen, Tea]`. Adding `"Extra"` throws `UnsupportedOperationException` and is caught; thus it prints `toList mutable: false`.
2. `Collectors.toCollection(ArrayList::new)` creates a new `ArrayList`. Calling `editable.add("Extra")` is valid, so the list has four strings.
3. `groupingBy` splits by `category`. `LinkedHashMap` keeps groups in first-appearance order: `office` before `food`. The downstream `mapping` extracts product names and collects a list for each group.
4. `toMap` creates a Map from name to unit count. Names in the sample are unique; the merge function `(old,new) -> old` merely demonstrates a fallback policy for duplicate keys. `LinkedHashMap` gives the Map output a deterministic order.
5. Total units is `2+3+1=6`. Revenue is `2*1250 + 3*200 + 1*700 = 3800` cents.
6. `reduce(Long::max)` returns an `Optional<Long>` with the maximum value `1250`, and then `orElseThrow()` retrieves that value.
7. `joining(", ")` produces a single string `Book, Pen, Tea`.
8. `parallelStream().reduce(0,Integer::sum)` still computes the sum `6` because the identity and combining operation fit this problem; **do not infer that every reduce lambda is parallel-safe**.
9. `Stream.empty().reduce(Integer::sum)` has no identity, so it yields an empty Optional; `isEmpty()` is `true`.
10. `Stream.toList()` accepts null elements as shown in the example and displays `[A, null, B]`.

The example code uses only APIs available in Java 17, requiring no network or input files. The output was compiled with `--release 17` and run with fixed values.

## 9. Key Differences in Type and Empty State

| Criterion | `toList()` | `collect(...)` | `reduce(...)` |
| --- | --- | --- | --- |
| Result type | `List<T>` | Depends on Collector, can be any valid `R` | `T`, `Optional<T>`, or `U` |
| Main purpose | Collect elements into a list | Structured result or mutable reduction | Combine into a single value |
| Mutability | Unmodifiable List | Depends on Collector and specific contract | Typically uses immutable/value results |
| With empty Stream | Empty list | Depends on Collector: empty List, empty Map, counting=0... | With identity → identity; without identity → Optional.empty |
| Common usage | `.toList()` | `.collect(groupingBy(...))` | `.reduce(0,Integer::sum)` |
| Combiner needed for parallel | Handled by Stream implementation | Collector/combiner per contract | Combining function and identity must be correct |
| Used to build a mutable list | No | `toCollection(ArrayList::new)` | Should not use mutable reduce |

If business requirements need to distinguish between "no data" and "sum equals 0", `reduce(0,Integer::sum)` does not express absence on its own. Use `reduce(Integer::sum)` to receive an Optional, or also compute `count`/appropriate statistics.

If you do not need to keep all elements in memory, summing with `reduce` or primitive `sum()` can save memory compared to calling `toList()` and then iterating to sum. However, if you need to display and reprocess the same data, storing the list may be acceptable to avoid re-reading an expensive I/O source.

## 10. Performance, Lazy Evaluation, and Associativity

### 10.1. Terminal Operations Trigger Traversal

`map` and `filter` are intermediate operations. They build the pipeline, typically running the body on elements only when a terminal operation needs data:

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> {
            System.out.println("map " + n);
            return n * 2;
        });

// At this point, usually no "map ..." has been printed yet.
List<Integer> values = pipeline.toList();
```

With a finite ordered source and `toList()`, the pipeline needs to produce the list elements. But in general, **do not place important side effects inside mappers**, because a Stream may use short-circuiting or optimizations that change how many times certain callbacks are executed. `toList`, `collect`, and `reduce` do not turn external side effects into a transaction.

### 10.2. reduce: Performance and Boxing

`Stream<Integer>.reduce(0,Integer::sum)` processes `Integer` wrappers. If the source is primitive numeric values or can be converted to primitives, `IntStream.sum()` is usually shorter and can reduce boxing:

```java
int sum = products.stream()
        .mapToInt(Product::units)
        .sum();
```

For `mapToLong`/`mapToDouble`, there are corresponding `sum()` methods. Actual performance optimization depends on the JIT, data source, Stream size, and computation cost; do not conclude one version is always faster without measuring.

### 10.3. Parallel Reduction Does Not Mean "Faster Addition"

For parallel reduction to be correct, the accumulator must be associative and the identity must be neutral; the three-argument form also needs a compatible combiner. Complex structural merging may require synchronization or a custom Collector mechanism. A small Stream is usually not worth the thread coordination overhead.

With `collect`, standard Collectors are generally designed according to the appropriate contract; however, **mutable object values inside the resulting Map/List** are not automatically thread-safe when used after collecting. Do not assume that running `parallelStream()` makes every collected container or object safe across multiple threads.

### 10.4. Infinite Streams and Memory

`Stream.generate(...)` can create an infinite source. Calling `toList()` on an infinite source without a stopping condition will not produce a normal finite list; it may never terminate or may run out of memory. Use `limit`, a finite source, or an appropriate terminal algorithm.

`reduce` also cannot "solve" all infinite Streams; most reductions need to process all data to produce a result. Choose the right source and stopping condition before worrying about the terminal type.

## 11. Rules for null, Duplicate Keys, and Callback Exceptions

### 11.1. null Elements

- `Stream.toList()` can contain null; it does not automatically filter out elements.
- `Collectors.toUnmodifiableList()` **rejects null elements**.
- `Collectors.toMap(...)` is not a place to rely on a mapper returning null as a valid value; standardize/choose a clear Map contract.
- `reduce` needs a suitable combining operation; if a callback produces a null result or dereferences a null element, it can cause errors.

If data can be null, decide whether to filter, replace, represent with Optional, or report an error. Do not just pick a Collector that "happens" to skip null.

### 11.2. Duplicate Keys with toMap

`Collectors.toMap(keyMapper,valueMapper)` does not automatically resolve duplicate keys. When two elements map to the same key, it usually throws `IllegalStateException`, even when both values are equal.

You can choose an explicit merge function:

```java
Map<String, Integer> totalByCategory = products.stream()
        .collect(Collectors.toMap(
                Product::category,
                Product::units,
                Integer::sum
        ));
```

The result based on the content includes `office -> 5` and `food -> 1`. If you need to store every Product per category, `groupingBy` is more suitable because it does not lose individual items.

### 11.3. Checked Exceptions in Callbacks

`Function`, `BinaryOperator`, `BiConsumer`, and standard functional interfaces in Stream do not declare checked exceptions such as `IOException` on their functional method. Lambdas in `map`, `reduce`, or Collectors cannot let checked exceptions escape without handling them per contract.

For example, when a mapper reads a file, separate I/O from pure transformations or have a transparent exception-catching/wrapping policy. Do not use an arbitrary `catch (Exception) { return null; }` to force the pipeline to finish, as that corrupts results and hides system errors.

### 11.4. Do Not Mutate the Source Being Traversed

With standard collections, traversing a Stream from a collection while modifying that collection via pipeline side effects can break the source's assumptions, causing errors or undefined results. To create new output, use `toList()` or `collect` instead of mutating the same source inside `map` or `reduce`.

## 12. Common Mistakes and How to Fix Them

1. **Assuming `toList()` returns a mutable ArrayList:** it returns an unmodifiable List. To mutate, use `collect(toCollection(ArrayList::new))`.
2. **Assuming `Collectors.toList()` guarantees mutability:** there is no guarantee; do not rely on a JDK that happens to return an ArrayList.
3. **Assuming `toUnmodifiableList()` and `toList()` behave identically with null:** `toUnmodifiableList()` does not accept null, whereas `Stream.toList()` can contain null.
4. **Using `toMap` without handling duplicate keys:** a merge function or `groupingBy` is needed.
5. **Using `reduce` to build a List and calling `add` on the identity:** wrong mutable reduction model; use `collect`.
6. **Choosing the wrong identity in `reduce`:** for example, using `10` when summing with `Integer::sum` will be wrong, especially in parallel.
7. **Using a non-associative operation in parallel reduce:** subtraction or operations that depend on grouping order can produce unexpected results.
8. **Combiner inconsistent with accumulator:** the three-argument reduce form will fail when splitting/merging branches.
9. **Forgetting Optional when reduce has no identity:** `reduce(BinaryOperator)` returns an Optional, which is empty if there are no elements.
10. **Reusing the same Stream:** after a terminal operation, create another Stream from a recreatable source.
11. **Using a List to compute a sum without needing to store elements:** you can use `mapToLong().sum()`, `reduce`, or statistics to avoid intermediate storage.
12. **Assuming Set/Map output has a fixed order:** choose `LinkedHashSet`/`LinkedHashMap` when order is part of the contract.
13. **Ignoring null in mappers:** `String::length` on null causes an NPE; define the missing-data policy before processing.
14. **Thinking parallelStream guarantees faster execution:** overhead can be high, and callbacks and associativity rules must be correct.
15. **Using a terminal operation on an infinite Stream without a limit:** it may never terminate or may exhaust resources.
16. **Confusing statistics results with collection results:** `Collectors.summarizingInt` creates a summary object; `toList` creates a list of elements—two different goals.

## 13. Practice Exercises

**Exercise 1.** Given `Stream.of("a","bb","ccc")`, write a pipeline to produce a `List<Integer>` of string lengths. Should you use `toList()` or `collect()` if the list is read-only?

**Exercise 2.** Create a list of names from `List<Product>` using `collect(Collectors.toCollection(ArrayList::new))`, then add `"New"`. Why is the same operation not allowed with `Stream.toList()`?

**Exercise 3.** From `Stream.of("java","api","java")`, create a `Set<String>` without duplicate elements. If you need to preserve first-appearance order, which Collector should you use?

**Exercise 4.** From `List<Product>` with category and units, compute a Map of total units per category. Should you use `toMap(..., Integer::sum)` or `groupingBy(..., summingInt(...))`? Explain why both can be appropriate.

**Exercise 5.** From a list of products, group names by category into `Map<String,List<String>>`. Why cannot `toList()` create this structure directly?

**Exercise 6.** Use `reduce(0,Integer::sum)` to sum `[1,2,3]`. What is the result on an empty Stream? If there is no identity, what is the return type?

**Exercise 7.** State two important requirements for the identity and accumulator when using `parallelStream().reduce(...)`. Why is subtraction usually unsuitable?

**Exercise 8.** Given `Stream.of("Book","Pen","Tea")`, create the string `"Book, Pen, Tea"` using a Collector. Compare this with string-concatenation reduce.

**Exercise 9.** Why is `Stream.of("A",null,"B").toList()` valid while a pipeline `collect(Collectors.toUnmodifiableList())` on a similar source will fail?

**Exercise 10.** Write a three-argument `reduce` to compute `long` revenue from a `Stream<Product>` with `units` and `unitPriceCents`. Choose an appropriate identity, accumulator, and combiner.

**Exercise 11.** Why should you not use `reduce(new ArrayList<>(), (list,x) -> {list.add(x); return list;}, ...)` to collect elements from a parallel stream?

**Exercise 12.** If you want to return a report containing count/min/max/sum/average for `units`, should you consider `mapToInt(...).summaryStatistics()` or calling multiple terminal operations on the same Stream?

### Suggested Answers

1. `Stream.of("a","bb","ccc").map(String::length).toList()` returns `[1,2,3]`; use `toList()` if no modification is needed.
2. `toCollection(ArrayList::new)` returns a mutable ArrayList; `toList()` is unmodifiable.
3. `collect(toSet())` removes duplicates without promising order; `collect(toCollection(LinkedHashSet::new))` preserves insertion order.
4. `toMap(Product::category, Product::units, Integer::sum)` or `groupingBy(Product::category, summingInt(Product::units))` both express the sum per group; choose the more readable form with the right type contract.
5. `toList()` only collects elements into a single List; `groupingBy` creates a Map and a list within each group.
6. With identity `0` → result `0`; without identity → empty `Optional<Integer>`.
7. Identity must be neutral, accumulator associative; the three-argument combiner must be compatible. Subtraction is not associative.
8. `stream.collect(Collectors.joining(", "))` is readable; reducing strings via reduce can create many temporary objects and is usually less expressive of intent than joining.
9. `Stream.toList()` allows null elements; `Collectors.toUnmodifiableList()` rejects null.
10. `reduce(0L, (total,p) -> total + p.units()*p.unitPriceCents(), Long::sum)`, with appropriate multiplication and long value range.
11. Mutating a mutable identity violates the reduction contract, and it can be shared and cause data races or incorrect duplication; use `collect`.
12. `summaryStatistics()` collects multiple metrics with a single terminal operation; a Stream cannot run a terminal operation a second time.

## 14. Summary

All three terminal operations trigger the pipeline, but they answer three different questions:

- **`toList()`:** "I need all elements as a List for reading."
- **`collect()`:** "I need a structure/result built according to specific rules: mutable List, Set, Map, groups, string, statistics…"
- **`reduce()`:** "I need to combine elements into **one value** based on a proper identity and associative operation."

Decide on the **result type and mutability**, then consider **empty sources, null, duplicate keys, associativity in parallel execution, and resources**. Concise Stream syntax is only truly good when it accurately expresses the application's data-processing contract.
