# Reviewing Result Semantics When Upgrading JDKs or Replacing Operations

Upgrading the JDK version or rewriting a Java Stream API pipeline can result in a program that **compiles cleanly and runs without errors, yet no longer satisfies the business contract**. A seemingly harmless change—such as replacing `collect(Collectors.toList())` with `toList()`, switching `findFirst()` to `findAny()`, replacing `filter` with `takeWhile`, or collecting a Map with a concurrent collector—can alter **result mutability, null handling, element selection, ordering, or which data is kept or dropped**.

Conversely, not every difference observed between two runs is a compatibility bug: iteration order from a `HashMap`, the implementation class name of a `List`, or the timing of a lambda with side effects may **not have been guaranteed by the API in the first place**. What must be protected are **semantics with an explicit contract**, not incidental behavior of a particular JDK release.

This lesson belongs to the **JDK Compatibility** chapter of the `JAVA_STREAM_API` module. We will audit changes involving lazy pipelines, `filter`, `map`, `reduce`, `collect`, grouping, custom collectors, parallel processing, `Spliterator`, resource management, and newer APIs such as Stream Gatherers. The end goal is a verification process **before and after a JDK upgrade or refactor**, complete with examples and hands-on exercises.

## 1. Distinguishing Four Types of Compatibility

When speaking of "upgrading the JDK without breaking Streams", first clarify which concern is being checked:

| Compatibility Type | Question to Answer | Example |
|---|---|---|
| **Source** | Does the code compile at the target Java level? | `Stream.toList()` does not exist in Java 8 |
| **Binary/runtime** | Do `.class` files and libraries run on the target JRE? | Bytecode compiled for a newer JDK fails on an overly old JRE |
| **Semantic (behavioral)** | Do returned values, exceptions, ordering, and states remain right? | Changing `findFirst` to `findAny` may pick a different element |
| **Non-functional** | Are performance, memory, resources, and parallelism still acceptable? | `parallel()` increases contention or overhead |

This lesson focuses on **semantic compatibility**, though the other three categories also require their own checks. Code compiling successfully **does not prove** results are right; a unit test passing on a few sample elements **does not prove** performance or resource safety.

### 1.1. Which Semantics Must Be Preserved?

For every pipeline, explicitly document:

1. **Which input elements count?** Are null elements included, or only valid data?
2. **Is ordering required?** If so, is it source order, sorted order, or business timestamp order?
3. **How is an empty result represented?** Number 0, `Optional.empty()`, empty Map, or absent group keys?
4. **Are duplicates allowed?** One SKU may appear across many orders; should values be summed, or which record kept?
5. **May the result be mutated?** Do callers invoke `list.add(...)` or update the Map?
6. **How are rounding errors and overflow handled?** `int`, `long`, `double`, or `BigDecimal`?
7. **Who is responsible for closing I/O sources?** Does the terminal operation close files automatically?

If these remain unanswered, a "cleaner-looking" replacement can silently alter the contract.

## 2. Important API Milestone Table When Reviewing JDK Versions

The milestones below help identify methods available by version. These are **API introduction milestones**, not a claim that similarly purposed methods are interchangeable.

| Java/JDK Version | Notable API or Change | Points to Audit |
|---|---|---|
| **Java 8** | `Stream`, `map`, `flatMap`, `filter`, `reduce`, `collect`, `Collectors.toList`/`toMap`/`groupingBy`, primitive streams | Foundation for Java 8-compatible code |
| **Java 9** | `takeWhile`, `dropWhile`, `Stream.ofNullable`, `Stream.iterate(seed, hasNext, next)`, `Optional.stream`, `Collectors.flatMapping`/`filtering` | Stopping conditions, nulls, group retention, and element-set changes |
| **Java 10** | `Collectors.toUnmodifiableList`/`toUnmodifiableSet`/`toUnmodifiableMap`; `List.copyOf` | Result mutability, nulls, and duplicate keys |
| **Java 12** | `Collectors.teeing` | Combining two collections, empty-source handling, and finisher |
| **Java 16** | `Stream.toList()`, `Stream.mapMulti(...)` | Unmodifiable lists; expanding one element into 0..n results |
| **Java 24** | Stream Gatherers (`Stream.gather`, `Gatherer`) finalized as standard feature | API absent on older JDKs; check framing, state, and execution |

In Java 22 and 23, Stream Gatherers were in preview; code using them on those releases has separate preview-flag requirements. For code that must run on Java 8, 11, 17, or 21, do not directly use Java 24's `Stream.gather`.

**Important:** Never assume a newer method "fixes" all older versions. Adopting a newer API must be evaluated against the **result contract**, **`--release` level**, and real data.

## 3. Most Error-Prone Case: toList(), Collectors.toList(), and toUnmodifiableList()

Three ways of collecting into a list look similar:

```java
// Java 8+
List<String> a = stream.collect(Collectors.toList());

// Java 10+
List<String> b = stream.collect(Collectors.toUnmodifiableList());

// Java 16+
List<String> c = stream.toList();
```

These lines are **three separate examples**; a new Stream must be created for each call because a Stream is consumed only once.

### 3.1. Contract Comparison

| API | Minimum Java | Is List Mutability Guaranteed? | Null Policy | Ordering |
|---|---:|---|---|---|
| `collect(Collectors.toList())` | 8 | **No guarantee** on mutability or List type | Should not design around a specific implementation | Preserves encounter order if source is ordered |
| `collect(Collectors.toUnmodifiableList())` | 10 | **Unmodifiable** | **Rejects null elements** | Preserves encounter order if present |
| `Stream.toList()` | 16 | **Unmodifiable** | **Allows null elements** in returned List | Preserves encounter order if present |

Most crucial differences when refactoring:

- Replacing `collect(toList())` with `toList()` can cause **downstream code to throw `UnsupportedOperationException`** if callers previously relied on `add` or `remove` working.
- Replacing with `toUnmodifiableList()` can cause **code to throw `NullPointerException`** when the source contains null elements.
- Merely renaming the method without re-running tests for nulls, ordering, and mutability can miss bugs.

### 3.2. Example Runnable Since Java 16

```java
import java.util.List;
import java.util.stream.Stream;

public class ToListSemanticDemo {
    public static void main(String[] args) {
        List<String> values = Stream.of("A", null, "B").toList();

        System.out.println(values); // [A, null, B]
        System.out.println(values.size()); // 3

        try {
            values.add("C");
            throw new AssertionError("Must not modify List");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List is unmodifiable");
        }
    }
}
```

If a **mutable list** is needed, explicitly request a concrete type:

```java
// Java 8+: the result is an ArrayList as requested.
List<String> mutable = stream.collect(
        Collectors.toCollection(ArrayList::new));
```

Or, in Java 16+, you can copy:

```java
List<String> mutable = new ArrayList<>(stream.toList());
```

The promise of a "mutable List" comes from choosing `ArrayList`, **not** from incidental behavior of `Collectors.toList()` in a particular JDK release.

### 3.3. Do Not Depend on Implementation Classes

Do not write tests like:

```java
// Do not do this:
// assert result.getClass() == ArrayList.class;
```

`Collectors.toList()` does not promise a specific List class; `Stream.toList()` likewise promises no specific implementation class name and the result may be *value-based*. Test values, ordering, and unmodifiability **when those are part of the contract**, instead of relying on class names, object identity, or synchronizing on the returned List.

## 4. Distinguishing null Values from an Empty Stream

Java 9 added `Stream.ofNullable(value)`:

```java
// Java 9+
Stream<String> none = Stream.ofNullable(null); // 0 elements
Stream<String> one = Stream.ofNullable("A");   // 1 element
```

Yet `Stream.of((String) null)` contains **one null element**, not an empty Stream:

```java
// Java 8+
long withNull = Stream.of((String) null).count(); // 1

// Java 9+
long withoutValue = Stream.<String>ofNullable(null).count(); // 0
```

This is a clear semantic difference. If refactoring `Stream.of(value)` to `Stream.ofNullable(value)`, when `value == null`, **the element count changes from 1 to 0**. That can affect `count`, `collect`, dropped-record counts, and data quality reports.

### 4.1. Optional Does Not Replace Empty Metrics with 0

A few results:

| Operation | Empty Stream | Stream with One Element 0 |
|---|---|---|
| `IntStream.sum()` | `0` | `0` |
| `IntStream.average()` | `OptionalDouble.empty()` | `OptionalDouble[0.0]` |
| `IntStream.reduce(Integer::sum)` | `OptionalInt.empty()` | `OptionalInt[0]` |
| `IntStream.reduce(0, Integer::sum)` | `0` | `0` |
| `IntStream.count()` | `0L` | `1L` |

Replacing `reduce(Integer::sum)` with `sum()` **loses the "no elements" state** if the caller cares about `OptionalInt.empty()`. Conversely, if business rules define an empty source's sum as 0, `sum()` is the clearer choice.

### 4.2. findFirst() and null Values

`findFirst()` returns `Optional<T>`. If the selected element is `null`, this operation can throw `NullPointerException`; do not use it as a way to "return an empty Optional for a null element":

```java
// WRONG if the first element is null:
// Stream.of((String) null, "A").findFirst();

Optional<String> safe = Stream.of((String) null, "A")
        .filter(Objects::nonNull)
        .findFirst();
System.out.println(safe.orElse("(empty)")); // A
```

In Java 9+, `Optional.stream()` can flatten Optionals:

```java
// Java 9+
List<String> present = Stream.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B"))
        .flatMap(Optional::stream)
        .collect(Collectors.toList());
// [A, B]
```

In Java 8, you can use `filter(Optional::isPresent).map(Optional::get)` when the `Optional` objects themselves are non-null. Whichever approach is chosen, explicitly decide **whether absent elements should remain tracked in statistics**.

## 5. filter Differs from takeWhile and dropWhile

Java 9 provides `takeWhile` and `dropWhile`, yet they are **not equivalent replacements** for `filter`.

- `filter(p)` evaluates the predicate **on elements** and keeps all matching elements.
- `takeWhile(p)` on an **ordered** Stream keeps the **longest contiguous leading slice** where every element satisfies the predicate; it stops upon hitting the first non-matching element.
- `dropWhile(p)` on an **ordered** Stream drops the **longest contiguous leading slice** satisfying the predicate, then keeps the remainder.

```java
// Java 9+
List<Integer> data = Arrays.asList(1, 2, 0, 3, 4);

List<Integer> filtered = data.stream()
        .filter(n -> n > 0)
        .collect(Collectors.toList());
// [1, 2, 3, 4]

List<Integer> taken = data.stream()
        .takeWhile(n -> n > 0)
        .collect(Collectors.toList());
// [1, 2]

List<Integer> dropped = data.stream()
        .dropWhile(n -> n > 0)
        .collect(Collectors.toList());
// [0, 3, 4]
```

Replacing `filter(n -> n > 0)` with `takeWhile(n -> n > 0)` loses positive numbers appearing after `0`. This replacement is only valid if **the source is sorted or satisfies an invariant guaranteeing all non-matching elements come after all matching elements**, and business logic genuinely wants the leading prefix.

### 5.1. Unordered Streams

On an **unordered** Stream, `takeWhile` does not promise a specific prefix in encounter order and may return a **subset** of predicate-matching elements per the operation's contract; `dropWhile` also has freedoms differing from ordered sources. Do not use them to express "pick the first N records" or "stop at the exact first event" when input order is undefined.

### 5.2. Three-Parameter iterate Is Also a Stopping Condition

Java 9 provides:

```java
// Java 9+: seed, hasNext, next
Stream<Integer> numbers = Stream.iterate(
        1, n -> n <= 5, n -> n + 1);
// 1, 2, 3, 4, 5
```

Previously, Java 8 often combined `Stream.iterate(seed, next)` with `limit(n)`:

```java
// Java 8+
Stream<Integer> firstFive = Stream.iterate(1, n -> n + 1)
        .limit(5);
```

Both examples happen to yield the same sequence, yet `limit(5)` counts elements whereas `n -> n <= 5` checks element values. With a different step, source, or condition, they may not be equivalent. When upgrading JDKs, keep clear whether the requirement is **"take exactly N elements"** or **"take until a stopping condition occurs"**.

## 6. Ordering, findFirst, findAny, and Map/Set Collection

### 6.1. Do Not Confuse findFirst with findAny

With an encounter-ordered source:

```java
OptionalInt first = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findFirst();
// OptionalInt[7]

OptionalInt any = IntStream.rangeClosed(1, 100)
        .parallel()
        .filter(n -> n % 7 == 0)
        .findAny();
// Present, though not guaranteed to be 7.
```

`findAny` allows greater optimization freedom, yet is wrong when the requirement is **"the first matching record in source order"**. A test asserting that `findAny` always returns 7 tests unguaranteed behavior, not correctness.

### 6.2. forEach Does Not Guarantee Action Order

`parallel().forEach(action)` does not guarantee actions run in encounter order. `forEachOrdered(action)` preserves action order per encounter order if the source is ordered, at the potential cost of reduced parallelism.

```java
IntStream.rangeClosed(1, 4)
        .parallel()
        .forEachOrdered(System.out::print);
// 1234
```

Do not replace `forEachOrdered` with `forEach` merely for speed when log order, file output order, or event processing order is a business requirement.

### 6.3. Maps and Sets Do Not Have Implicit Iteration Order

`Collectors.toSet()` does not promise element order; `Collectors.toMap(...)` and `groupingBy(...)` do not promise Map implementation type or key iteration order. Changing JDK versions or switching to parallel mode can make printed order **differ without violating the API contract**.

```java
Map<String, Long> totals = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                Collectors.counting()));

// RIGHT: compare values by key.
long bac = totals.getOrDefault("BAC", 0L);

// DO NOT DO THIS: rely on totals.toString() print order
// to determine region ordering.
```

This snippet assumes an `Order` type and an `orders` list. If business logic wants Map keys in ascending order, use the overload allowing `TreeMap::new`:

```java
Map<String, Long> sorted = orders.stream()
        .collect(Collectors.groupingBy(
                Order::getRegion,
                TreeMap::new,
                Collectors.counting()));
```

To preserve key insertion order in a sequential collection, consider `LinkedHashMap::new` in the overload accepting a map supplier. **Key ordering inside a Map** and **which element wins when two values share a key** are two separate concerns.

## 7. toMap, groupingBy, and Merge Functions When Changing Algorithms

With duplicate keys, `Collectors.toMap(keyMapper, valueMapper)` throws `IllegalStateException` by default. Refactoring from `groupingBy(..., toList())` to `toMap` can lose the ability to represent **multiple values per key**, or cause the code to throw an exception.

```java
List<String> data = Arrays.asList("P01:A", "P01:B", "P02:C");

Map<String, List<String>> grouped = data.stream()
        .collect(Collectors.groupingBy(
                item -> item.substring(0, 3)));
// P01 has two strings, P02 has one string.

// WRONG with duplicate key P01:
// data.stream().collect(Collectors.toMap(
//         item -> item.substring(0, 3), item -> item));

Map<String, String> latestByEncounter = data.stream()
        .collect(Collectors.toMap(
                item -> item.substring(0, 3),
                item -> item,
                (oldValue, newValue) -> newValue));
// P01 -> P01:B with this source List and ordered collection.
```

### 7.1. Merge Operations Must Be Associative

A merge function used in parallel reduction must preserve meaning regardless of how groups are associated. Example:

```text
(10 + 20) + 40 = 70
10 + (20 + 40) = 70

((10 + 20) / 2 + 40) / 2 = 27.5
(10 + (20 + 40) / 2) / 2 = 20
```

`(a, b) -> (a + b) / 2` is **not** a valid merge function to compute the average of all duplicate-key records. For an exact average, retain **sum and count** in state or use `Collectors.averagingInt` appropriately.

### 7.2. toConcurrentMap Loses "First/Last Seen" Meaning

`Collectors.toConcurrentMap` is a concurrent and unordered collector. When switching from `toMap` to `toConcurrentMap`, merge functions keeping old or new values:

```java
(oldValue, newValue) -> oldValue
(oldValue, newValue) -> newValue
```

are no longer a reliable way to pick **the first/last record in the source List**. When the newest record is needed, select by `timestamp`, `version`, and an explicit tie-breaker; never rely on worker execution scheduling.

### 7.3. Empty Groups and Null Keys

`groupingBy` does not automatically create keys for groups **absent from the source**. When flattening parent–child data, `flatMap` before `groupingBy` can drop parent groups that have zero children, whereas `Collectors.flatMapping` (Java 9+) **inside** `groupingBy` can retain encountered parent groups with empty downstream results.

Do not rely on Map collectors accepting `null` as keys/values. `groupingBy` requires a valid classifier key and normally throws `NullPointerException` on null keys; `toConcurrentMap` rejects null keys/values. Normalize or reject missing data **before** collecting.

## 8. Arithmetic Checks: sum, average, Overflow, and double

Changing Stream types or swapping collectors can keep the same element count while changing **arithmetic meaning**.

### 8.1. Empty Sources: Optional Differs from Default Values

```java
OptionalDouble primitiveAverage = IntStream.empty().average();
double collectorAverage = Stream.<Integer>empty()
        .collect(Collectors.averagingInt(Integer::intValue));

System.out.println(primitiveAverage.isPresent()); // false
System.out.println(collectorAverage);              // 0.0
```

The two APIs differ **on empty sources**. If you want to keep distinguishing "no data" from "an average of 0", do not switch from `average()` to `averagingInt(...)` while testing only non-empty sources.

`IntSummaryStatistics` and `LongSummaryStatistics` return `getAverage() == 0.0` when `count == 0`. Min/max of empty statistics also hold sentinel values; check `getCount()` before displaying them.

### 8.2. Integer Overflow Can Go Unnoticed

```java
int wrongForBusiness = IntStream.of(Integer.MAX_VALUE, 1).sum();
// int overflow: value is not the mathematical sum 2147483648.

long widened = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(value -> (long) value)
        .sum();
// 2147483648
```

For sums that can exceed `long`, use `BigInteger`/`BigDecimal` or overflow-checked addition like `Math.addExact` depending on policy. Switching from `sum` to `reduce` does not automatically prevent overflow; you must change the type or validation rules.

### 8.3. Floating-Point Rounding Error and Parallel Combining

`double` is not bitwise associative:

```java
double a = (1.0e16 + -1.0e16) + 1.0; // 1.0
double b = 1.0e16 + (-1.0e16 + 1.0); // 0.0
```

Consequently, changing branching or summation algorithms can cause floating-point sums/averages to **differ in rounding**. `DoubleStream.sum()` may use compensated summation to improve accuracy, yet does not promise a single combining order or bitwise identity across all implementations.

For approximate statistics, test within **business-meaningful tolerances** and handle `NaN` and infinities explicitly. For currency, prefer `BigDecimal` or integers in the smallest unit, with clear rounding rules.

## 9. Side Effects: Why Upgrading JDKs Can Change Logs or Counters

Intermediate operations such as `map`, `filter`, and `peek` are lazy. Stream implementations are permitted to optimize away operations that are unnecessary to determine a valid result. Specifically, `count()` on a sized source can return the result **without traversing every element**, provided pipeline operations do not alter element count in a way requiring inspection.

```java
List<String> names = Arrays.asList("A", "B", "C");

long count = names.stream()
        .peek(name -> System.out.println("Saw " + name))
        .count();

System.out.println(count); // 3
// Does NOT guarantee all three "Saw ..." lines are printed.
```

Since Java 9, the API documentation explicitly mentions this `count` optimization example. An implementation may skip calling `peek` when the source size is known and element traversal is unnecessary. This is **not a bug in `count`**; the design flaw lies in relying on `peek`'s side effect for business recording.

### 9.1. Do Not Count Side Effects from map/peek

Avoid:

```java
AtomicInteger processed = new AtomicInteger();

long count = names.stream()
        .map(name -> {
            processed.incrementAndGet();
            return name.toUpperCase();
        })
        .count();

// Do not treat processed.get() as a reliable business record count.
```

Replace with an aggregation directly expressing the needed result:

```java
long numberOfNames = names.stream().count();

Map<Integer, Long> countsByLength = names.stream()
        .collect(Collectors.groupingBy(
                String::length, Collectors.counting()));
```

If the requirement is to **perform an action on every element**, use an appropriate terminal operation such as `forEach` with ordering and thread-safety considerations; if the requirement is to **aggregate metrics**, use collectors/reductions. Never base correctness on `peek` always being called.

## 10. flatMap, mapMulti, and Gatherers: Same Shape Does Not Mean Same Contract

### 10.1. flatMap vs. mapMulti

`Stream.flatMap` has existed since Java 8. It requires the mapper to return a sub-`Stream`:

```java
// Java 8+
List<String> words = sentences.stream()
        .flatMap(sentence -> Arrays.stream(sentence.split(" ")))
        .collect(Collectors.toList());
```

`Stream.mapMulti` from Java 16 lets the mapper **emit 0..n elements directly** through a consumer:

```java
// Java 16+
List<String> words = sentences.stream()
        .<String>mapMulti((sentence, emit) -> {
            for (String word : sentence.split(" ")) {
                emit.accept(word);
            }
        })
        .toList();
```

This assumes `sentences` is a `List<String>` with no null elements. Considering only **the sequence of emitted words**, the two approaches may be equivalent. However, the example also changed `collect(toList())` to `toList()`, changing **list mutability**. Thus, when refactoring, test **both the transformation and the terminal step**, not only printed output.

`mapMulti` does not need to allocate a sub-stream per source element, so it **may** help on overhead when each element emits few values; do not assume it is faster in all cases. When `flatMap` returns I/O-backed sub-streams, you must also understand the contract of closing sub-streams once their contents enter the pipeline. Never change resource management based purely on result shape.

### 10.2. Gatherers Belong to a Different JDK Level

Stream Gatherers enable stateful intermediate transformations, windowing, and coordination shapes beyond `map` or `flatMap`. The `Stream.gather` and `Gatherer` APIs were standardized in Java 24. That has two consequences to audit:

1. **JDK level:** code using `gather` cannot run on Java 8/11/17/21 JREs.
2. **Pipeline contract:** when replacing `limit`, `map`, `flatMap`, or custom collectors with a gatherer, verify state, ordering, stopping conditions, and result equivalence—especially on empty sources, parallel execution, and unordered Streams.

Do not move every pipeline to Gatherers merely because of a JDK upgrade. Prefer the simplest operation that expresses the requirement accurately and matches the system's compatibility level.

## 11. I/O Resources: Upgrading JDKs Does Not Make Terminal Operations Auto-Close Streams

Sources such as `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` can hold open file or directory handles. Whether calling `count()`, `findFirst()`, or `collect()`, you still need to **close resource-backed Streams** with `try-with-resources`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public static Optional<String> firstError(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .findFirst();
    }
}
```

`findFirst` can stop early, yet **the source must still be closed**. Do not change a method returning a computed `List` into a method returning an open `Stream` without defining **who closes it**. Conversely, never return a pipeline created inside a `try-with-resources` block that has already exited; the caller would receive a closed Stream.

With `Stream.concat(first, second)`, closing the combined Stream closes the input Streams by contract, yet if opening the second source fails **before `concat` is created**, the first source still needs `try-with-resources` protection. JDK upgrades do not remove these resource ownership and lifecycle requirements.

## 12. Complete Java 8 Example: Foundational Semantic Audit Suite

The following audit suite **uses no post-Java 8 APIs**, so it compiles on JDK 8. It does not test speed or implementation class names. Instead, it tests what business logic truly requires: post-filter results, guaranteed ordering, empty metrics, Optionals, duplicate-key merging, and sequential/parallel equivalence.

Save as `StreamBehaviorAudit.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.Set;
import java.util.HashSet;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamBehaviorAudit {
    private static int checks;

    static void check(boolean condition, String name) {
        checks++;
        if (!condition) {
            throw new AssertionError("FAILED: " + name);
        }
    }

    static final class Sale {
        final String region;
        final String sku;
        final long cents;

        Sale(String region, String sku, long cents) {
            this.region = region;
            this.sku = sku;
            this.cents = cents;
        }
    }

    public static void main(String[] args) {
        List<Integer> data = Arrays.asList(3, 1, 3, 2);

        // 1) Preserve order with an encounter-ordered List source.
        List<Integer> unique = data.parallelStream()
                .distinct()
                .collect(Collectors.toList());
        check(unique.equals(Arrays.asList(3, 1, 2)),
                "distinct preserves encounter order");

        // 2) Do not require iteration order on Set.
        Set<Integer> asSet = data.stream()
                .collect(Collectors.toSet());
        check(asSet.equals(new HashSet<>(Arrays.asList(1, 2, 3))),
                "element set instead of print order");

        // 3) Distinguish empty from an actual sum of 0.
        check(IntStream.empty().sum() == 0,
                "sum on empty source");
        OptionalDouble average = IntStream.empty().average();
        check(!average.isPresent(),
                "average on empty source");
        OptionalInt reduced = IntStream.of(-5, 5)
                .reduce(Integer::sum);
        check(reduced.isPresent() && reduced.getAsInt() == 0,
                "non-empty data reduces to 0");
        check(!IntStream.empty().reduce(Integer::sum).isPresent(),
                "reduce without identity on empty source");

        // 4) True count differs from element count after flattening.
        List<List<Integer>> nested = Arrays.asList(
                Arrays.asList(1, 2),
                Collections.<Integer>emptyList(),
                Arrays.asList(3));
        List<Integer> flattened = nested.stream()
                .flatMap(List::stream)
                .collect(Collectors.toList());
        check(flattened.equals(Arrays.asList(1, 2, 3)),
                "flatMap skips empty sublists");

        // 5) Map: check contents by key only.
        List<Sale> sales = Arrays.asList(
                new Sale("BAC", "P01", 100L),
                new Sale("NAM", "P02", 200L),
                new Sale("BAC", "P01", 300L));

        Map<String, Long> seqTotals = sales.stream()
                .collect(Collectors.toMap(
                        sale -> sale.sku,
                        sale -> sale.cents,
                        Long::sum));

        Map<String, Long> parallelTotals = sales.parallelStream()
                .collect(Collectors.toMap(
                        sale -> sale.sku,
                        sale -> sale.cents,
                        Long::sum));

        check(seqTotals.equals(parallelTotals),
                "sequential and parallel toMap match");
        check(seqTotals.get("P01") == 400L,
                "merge sums duplicate keys");

        Map<String, Long> byRegion = sales.parallelStream()
                .collect(Collectors.groupingBy(
                        sale -> sale.region,
                        Collectors.counting()));
        check(byRegion.get("BAC") == 2L
                && byRegion.get("NAM") == 1L,
                "groupingBy counts each group accurately");

        // 6) toMap without merge must reject duplicate keys.
        boolean duplicateRejected = false;
        try {
            Stream.of("P01:A", "P01:B").collect(Collectors.toMap(
                    item -> item.substring(0, 3),
                    item -> item));
        } catch (IllegalStateException expected) {
            duplicateRejected = true;
        }
        check(duplicateRejected, "toMap rejects duplicate keys");

        // 7) Request ArrayList explicitly when a mutable result is needed.
        List<Integer> mutable = data.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(99);
        check(mutable.size() == 5 && mutable.get(4) == 99,
                "toCollection(ArrayList::new) is mutable");

        // 8) findFirst differs from findAny in element selection guarantee.
        OptionalInt first = IntStream.rangeClosed(1, 100)
                .parallel()
                .filter(n -> n % 7 == 0)
                .findFirst();
        check(first.isPresent() && first.getAsInt() == 7,
                "findFirst respects encounter order");

        System.out.println("PASS " + checks + " semantic checks");
    }
}
```

**Expected output:** the program prints `PASS 13 semantic checks` and throws no `AssertionError`. What matters is not an arbitrary log string, but **the invariants verified via `check`**. If a check fails after a JDK upgrade or refactor, investigate whether business logic changed or expectations were placed on behavior not guaranteed by the API.

### 12.1. How to Use the Audit Suite During Version Migration

On **JDK 9 or later**, you can compile the program with:

```bash
javac --release 8 StreamBehaviorAudit.java
java StreamBehaviorAudit
```

`--release 8` instructs the compiler to allow only APIs available at Java 8 level and emit target-compatible bytecode. On **JDK 8 itself**, use `javac StreamBehaviorAudit.java` because the `--release` option appeared in JDK 9.

When rolling out an upgrade, run the suite on **both the old runtime and the new runtime** in isolated environments, while also benchmarking performance and testing real library versions. `--release` checks source/target-API compatibility, yet **does not replace running the code on the target runtime**.

## 13. Building a Pre- and Post-Upgrade Test Matrix

A "happy path" test suite with a few positive integers is insufficient. Build a matrix covering the following boundaries and semantic properties:

| Test Group | Datasets / Conditions | Expectations to Document |
|---|---|---|
| **Empty source** | `[]`; all elements removed by `filter` | Sum, average, Optional, empty Map/list |
| **Nulls** | Null in source, inside sublists, mapper returning null | Filter, accept, reject, or throw error? |
| **Duplicate keys** | Multiple records with the same SKU | Sum, keep first/last, pick max, or throw exception? |
| **Ordering** | Ordered List; unordered Set; `unordered()` pipeline | When must encounter order be preserved? |
| **Parallel** | `parallelStream()`; different `Spliterator` splits | Equivalent values, no reliance on side effects |
| **Precision / overflow** | Huge sums, `Double.NaN`, infinity, decimals | Acceptable tolerance, overflow detection, special values |
| **Mutability** | Caller invokes `add`/`remove` on result | Is mutability part of the API contract? |
| **Single-use source** | Consumed Stream; reading from files | Any invalid Stream reuse or forgotten close? |
| **Stopping condition** | Predicate flips true/false multiple times | `filter` differs from `takeWhile`, `dropWhile`, and `limit` |
| **Versioned APIs** | Java 8/11/17/21/24 per system | Any new features exceeding supported level? |

### 13.1. Golden Tests and Invariant Testing

Combine two approaches:

- **Golden tests:** on small known datasets, record exact business-meaningful results, e.g., `P01 -> 400`, `count -> 3`, `[A,B]` when order is required.
- **Property/invariant tests:** verify properties across many datasets, e.g., sum of group counts equals total valid records, sequential and parallel `sum` match when addition does not overflow, or `distinct` never introduces new elements.

Do not save `Map.toString()` or `HashSet` iteration order as golden output if the contract does not mandate that order. When comparing Maps and Sets, compare **contents**, not console print order.

### 13.2. Testing Both Source Level and Runtime

For a project supporting Java 8 while developed on a newer JDK, you should:

1. Compile targeting the minimum supported API/bytecode level (e.g., `javac --release 8` on a recent enough JDK).
2. Run on the actual minimum supported JRE.
3. Run the same test suite on the upgraded target JRE.
4. Test with real libraries and realistic data, checking exceptions, resources, memory, and performance.
5. Replace operations only after clearly establishing the semantic contract and boundary tests.

Do not skip step 2 merely because the program already runs on the newer JDK. The goal of `--release` is controlling API/bytecode versions, not proving every behavior on the older runtime.

## 14. Process for Reviewing a Stream Refactoring Pull Request

Before approving a "code simplification" change, compare both pipelines on these aspects:

| Proposed Change | Mandatory Questions |
|---|---|
| `collect(toList())` → `toList()` | Does the caller mutate the List? Is minimum JDK ≥ 16? |
| `collect(toList())` → `toUnmodifiableList()` | Can the source contain nulls? Is minimum JDK ≥ 10? |
| `Stream.of(value)` → `ofNullable(value)` | Should a null element be retained as a record? |
| `filter(p)` → `takeWhile(p)` | Can the predicate go true → false → true? |
| `limit(n)` → `iterate(seed, hasNext, next)` | Bounded by **element count** or by **value**? |
| `findFirst()` → `findAny()` | Is the first element in encounter order needed? |
| `reduce(op)` → `sum()` | Must an empty source be distinguished from a sum of 0? |
| `average()` → `averagingInt(...)` | Is an average of 0.0 acceptable on an empty source? |
| `toMap(...)` → `toConcurrentMap(...)` | Does merging depend on order? |
| `flatMap(...)` → `mapMulti(...)` | Does it emit the same count/order and handle nulls/resources identically? |
| `sequential()` → `parallel()` | Do reducer/collector follow valid contracts with no shared side effects? |
| `collect(toList())` after `Files.lines` → an API returning a Stream | Who closes the file? Can the Stream be used after closing? |

### 14.1. Example Review of a Small Change

**Legacy code, supporting Java 8:**

```java
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .collect(Collectors.toList());
```

**New proposal, requiring Java 16+:**

```java
List<String> selected = names.stream()
        .filter(name -> name.startsWith("A"))
        .toList();
```

To approve accurately, verify:

1. Does the product's minimum JDK level **already** allow Java 16+?
2. Does any subsequent code call `selected.add(...)` or `selected.remove(...)`? If so, the refactor alters the contract.
3. If `names` contains null, `name.startsWith("A")` already throws an exception; changing the terminal operation **does not fix** this.
4. When `names` has encounter order, both produce the same content order with the same pipeline; there is **no** need to lock down the List implementation class.

If the caller genuinely needs a mutable List, keep the explicitly requested `ArrayList` construction rather than choosing based on a shorter method name.

## 15. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "Compiling on a newer JDK means it runs on all older JDKs." | Bytecode/API level must be checked and run on the target runtime. |
| "`Collectors.toList()` always returns a mutable `ArrayList`." | The API does not promise implementation type or mutability. |
| "`Stream.toList()` is identical to `Collectors.toList()`." | `toList()` since Java 16 returns an unmodifiable List; audit callers. |
| "`toUnmodifiableList()` matches `toList()` on nulls too." | `toUnmodifiableList()` rejects nulls, while `Stream.toList()` may contain nulls. |
| "`Stream.ofNullable(null)` holds one null element." | It creates an empty Stream; `Stream.of((T) null)` holds one null element. |
| "`takeWhile` is just another way to write `filter`." | On ordered Streams, `takeWhile` takes only the leading contiguous prefix matching the predicate. |
| "`findAny` will return the first element for small data." | The API makes no promise; use `findFirst` when the first element is required. |
| "Changing JDK makes `HashMap` print in a different order—a regression." | Without an ordering contract, this can be permitted behavior. |
| "`peek` is called once per element before `count`." | Implementations may elide operations unnecessary for the result. |
| "`average` and `Collectors.averagingInt` behave the same on empty sources." | One returns an empty Optional; the other returns `0.0`. |
| "Running parallel is automatically safe and faster." | Valid reduction contracts, avoiding shared state, and benchmarking are required. |
| "Terminal operations close `Files.lines` automatically." | I/O sources must be closed via `try-with-resources` or clear ownership contracts. |

## 16. Practice Exercises With Solutions

### Exercise 1. Switching to toList

A legacy method returns a list and the caller has `result.add("NEW")`. Should `collect(Collectors.toList())` be switched immediately to `Stream.toList()`?

**Answer:** No, if the caller contract requires a mutable List. `Stream.toList()` from Java 16 is unmodifiable. Use `Collectors.toCollection(ArrayList::new)` or `new ArrayList<>(stream.toList())` when mutability must be guaranteed.

### Exercise 2. Nulls and Empty Sources

Do `Stream.of((String) null).count()` and `Stream.<String>ofNullable(null).count()` return the same result?

**Answer:** No. The first has **1** null element; the second has **0** elements. `ofNullable` is only available since Java 9.

### Exercise 3. filter vs. takeWhile

Given `[1, 2, 0, 3]`, what are the results of `filter(n -> n > 0)` and `takeWhile(n -> n > 0)` respectively?

**Answer:** `filter` yields `[1, 2, 3]`, while `takeWhile` yields `[1, 2]` on an ordered source. The two operations are not equivalent replacements.

### Exercise 4. Checking Optional on Empty Sources

A refactor replaces `IntStream.empty().average()` with `Stream.<Integer>empty().collect(Collectors.averagingInt(Integer::intValue))`. Is the missing-data contract preserved?

**Answer:** No. `average()` returns `OptionalDouble.empty()`, while the collector returns `0.0`. If business logic must distinguish missing data, keep the Optional or include a count.

### Exercise 5. Replacing toMap with toConcurrentMap

Using merge function `(oldValue, newValue) -> newValue` to select the last element of an ordered List. Can you switch to `toConcurrentMap` and still expect the last element to always win?

**Answer:** No. `toConcurrentMap` is unordered; update order need not follow encounter order. If the latest record is needed, use a timestamp or version property plus a tie-breaker rule.

### Exercise 6. count and peek

Does `List.of("A", "B").stream().peek(System.out::println).count()` always print two lines?

**Answer:** No. `List.of` is from Java 9; `count` may deduce the size and skip traversal if unnecessary. Use `peek` for observation/debugging, never as a mandatory business step.

### Exercise 7. Integer Overflow

Why does `IntStream.of(Integer.MAX_VALUE, 1).sum()` not return the expected mathematical sum? How do you fix it?

**Answer:** `int` summation overflows. You can use `mapToLong(n -> (long) n).sum()` for this example; if sums can still exceed `long`, another numeric type/overflow-control strategy is needed.

### Exercise 8. Ordered Golden Tests

Should `Collectors.toSet().toString()` be compared against `"[A, B]"` across different JDKs?

**Answer:** No. `toSet` does not guarantee element order. Compare using `Set.equals` or sort explicitly if business output requires ordering.

### Exercise 9. Upgrading JDK and Changing APIs Simultaneously

A project simultaneously moves from JDK 8 to JDK 21 and replaces `flatMap` with `mapMulti` and `collect(toList())` with `toList()`. If tests fail, in what order should you investigate?

**Guided answer:** Separate the two kinds of changes: first run the business test suite on the new JDK **with the old logic** where still compatible; then swap operations one by one, verifying post-flattening counts and order, nulls, exceptions, result unmodifiability, and memory cost. Stepping incrementally isolates causes far better than changing multiple behaviors at once.

## 17. Checklist Before Accepting a JDK Upgrade or Stream Refactor

1. **Identify minimum JDK and target runtime.** Do newer APIs exceed the supported level? Are `--release` or preview strategies needed?
2. **State the data contract clearly.** How are empty sources, nulls, duplicate keys, ordering, and stopping conditions handled?
3. **Check result properties.** Are Lists/Maps mutable? Is ordering guaranteed? Was an `Optional` replaced with a default number?
4. **Cross-check transformations.** Do `map`/`flatMap`/`mapMulti`, `filter`/`takeWhile`, and `limit` keep the intended element set?
5. **Cross-check terminal operations.** Do `findFirst`/`findAny`, `reduce`/`sum`, `average`/`averaging...`, and Map collectors alter semantics?
6. **Audit parallelism.** Do accumulators/combiners associate properly without relying on unguaranteed ordering or shared mutable state?
7. **Audit arithmetic.** Are `int`/`long` overflow, `double` rounding error, `NaN`, and `BigDecimal` policies controlled?
8. **Audit resources.** Does every closeable I/O-backed Stream have `try-with-resources` or explicit ownership?
9. **Run tests across supported runtimes.** Compare results by business invariants, not incidental implementations or ordering.
10. **Benchmark separately after verifying correctness.** Never alter semantics merely to optimize without measurement evidence.

**Conclusion:** When upgrading JDKs or replacing Stream operations, preserve the **result contract** rather than merely keeping code compiling or log lines looking similar. Critical differences to audit are **processed element sets, ordering, result mutability, nulls, empty sources, duplicate keys, merge functions, arithmetic precision, and resource lifecycles**. Using a test matrix with boundary cases and comparing strictly against what the Java API actually guarantees allows you to leverage newer Stream features without trading away application correctness.