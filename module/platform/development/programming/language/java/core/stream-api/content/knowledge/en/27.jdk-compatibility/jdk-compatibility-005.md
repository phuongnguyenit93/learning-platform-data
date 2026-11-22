# `Stream.toList` and `mapMulti` Since Java 16

## 1. Objectives and JDK Compatibility Context

In the **`JAVA_STREAM_API`** module, pipelines typically flow from a data source through lazy operations like `filter`, `map`, and `flatMap` to terminal operations like `collect` and `reduce`. When learning newer JDK releases, it is essential to know **which Java version introduced an API**, and to understand contract differences before replacing legacy code.

Two major additions in **Java 16**:

- **`Stream.toList()`:** a terminal operation that collects stream contents into an **unmodifiable** `List`.
- **`Stream.mapMulti(...)`:** an intermediate operation allowing each input element to emit **0, 1, or more** output elements through a consumer, rather than creating sub-streams like `flatMap`.

This lesson belongs to the **JDK Compatibility** chapter and connects concepts of data transformation/collection, generic types, primitive streams, collectors, parallel processing, and limits around performance, state, and resources.

After this lesson, you will be able to:

1. Distinguish `Stream.toList()` from `Collectors.toList()`, `Collectors.toUnmodifiableList()`, and `Collectors.toCollection(ArrayList::new)`.
2. Predict unmodifiability, `null` tolerance, and encounter order of results.
3. Use `mapMulti` to filter/transform/flatten data with a callback emitting 0..n elements.
4. Decide when to use `mapMulti`, `flatMap`, `mapMultiToInt`, or primitive `mapMulti`.
5. Handle generic type inference, mutable objects, external resources, and parallel streams.
6. Write Java 8/11-compatible alternatives and verify differences when upgrading to Java 16+.

## 2. Version Milestones

| API | Available Since | Core Semantics |
| --- | --- | --- |
| `Stream.collect(Collectors.toList())` | Java 8 | Collects into a `List`, **without promising** implementation type or mutability. |
| `Stream.flatMap(...)` | Java 8 | Maps each element to a sub-`Stream` then flattens. |
| `Collectors.toCollection(ArrayList::new)` | Java 8 | Explicitly chooses a mutable target collection. |
| `Stream.ofNullable(...)` | Java 9 | Produces 0 or 1 element depending on null. |
| `List.of(...)` | Java 9 | Creates an unmodifiable list, rejecting `null`. |
| `Collectors.toUnmodifiableList()` | Java 10 | Collects an unmodifiable list, rejecting `null`. |
| `List.copyOf(...)` | Java 10 | Creates an unmodifiable list from a collection, rejecting `null`. |
| `Stream.toList()` | **Java 16** | Terminal operation returning an unmodifiable list, **allowing `null`**. |
| `Stream.mapMulti(...)` | **Java 16** | Emits 0..n elements from each input. |
| `Stream.mapMultiToInt/Long/Double(...)` | **Java 16** | Emits primitive results without a boxed stream. |
| `IntStream.mapMulti(...)` and `LongStream`, `DoubleStream` equivalents | **Java 16** | Emits multiple primitive results from each primitive input. |

The table reflects **standard library APIs**. A project running on a newer JDK while compiling with `--release 8` or `--release 11` still cannot use APIs introduced in Java 16. Upgrading the JDK runtime and source/bytecode release level must be considered together.

## 3. `Stream.toList()`: Terminal Operation with an Unmodifiable List

Basic signature:

```java
List<T> toList()
```

Java 16+ example:

```java
import java.util.Arrays;
import java.util.List;

public class ToListBasics {
    public static void main(String[] args) {
        List<String> source = Arrays.asList(
            "Java", "Go", "Kotlin", "Java"
        );

        List<String> result = source.stream()
            .filter(s -> s.length() >= 4)
            .map(String::toUpperCase)
            .toList();

        System.out.println(result);
        // [JAVA, KOTLIN, JAVA]
    }
}
```

`toList()` consumes the stream and creates a list in **encounter order if the stream is ordered**. It does not perform `distinct` automatically, so both `"JAVA"` entries remain. If the source is ordered and the stream runs in parallel, the list's contents still reflect encounter order, not thread completion order.

Most important trait: **the returned list does not allow modification**.

```java
import java.util.List;
import java.util.stream.Stream;

public class ToListUnmodifiable {
    public static void main(String[] args) {
        List<Integer> numbers = Stream.of(1, 2, 3).toList();

        System.out.println(numbers); // [1, 2, 3]

        try {
            numbers.add(4);
        } catch (UnsupportedOperationException expected) {
            System.out.println("Cannot add");
        }

        try {
            numbers.set(0, 10);
        } catch (UnsupportedOperationException expected) {
            System.out.println("Cannot set");
        }
    }
}
```

Output:

```text
[1, 2, 3]
Cannot add
Cannot set
```

`add`, `remove`, `set`, `clear`, `sort`, and other mutating operations are unsupported on the returned list. If subsequent code needs to add, remove, or sort in place, **do not mechanically replace `collect(Collectors.toList())` with `toList()`**.

### 3.1. No Concrete Implementation Guarantee

`Stream.toList()` has return type `List<T>`, without promising `ArrayList` or any specific class. Do not write code depending on the runtime class name or casting:

```java
// STATICALLY INVALID:
// ArrayList<String> values = Stream.of("A").toList();
```

If an `ArrayList` is genuinely needed:

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> values = Stream.of("A", "B")
    .collect(Collectors.toCollection(ArrayList::new));

values.add("C"); // Valid.
```

### 3.2. An Unmodifiable List Does Not Mean Immutable Elements

`toList` does not deep-copy objects in the stream:

```java
import java.util.List;
import java.util.stream.Stream;

public class MutableElement {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box box = new Box(1);
        List<Box> result = Stream.of(box).toList();

        box.value = 99;
        System.out.println(result.get(0).value); // 99

        // result.add(new Box(2)); // UnsupportedOperationException
    }
}
```

Only the **list structure through the List interface** is unmodifiable; the state of inner objects can still change if those objects are mutable. A deep snapshot requires a separate copying strategy or immutable elements.

## 4. Comparing `List` Collection Approaches

| Option | Minimum Java | Result List Mutability | Null | Concrete Type |
| --- | --- | --- | --- | --- |
| `collect(Collectors.toList())` | 8 | **No guarantee** | Accepts `null` | No guarantee |
| `collect(Collectors.toCollection(ArrayList::new))` | 8 | Mutable | Accepts `null` | `ArrayList` |
| `collect(Collectors.toUnmodifiableList())` | 10 | Unmodifiable | Rejects `null` | No guarantee |
| `Stream.toList()` | 16 | **Unmodifiable** | **Accepts `null`** | No guarantee |
| `List.copyOf(collection)` | 10 | Unmodifiable | Rejects `null` | No guarantee |

**Easy-to-miss point:** `Collectors.toList()` does not promise to return a mutable `ArrayList`, even though some current implementations happen to do so. Conversely, `Stream.toList()` **does promise** an unmodifiable list.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CompareListCollectors {
    public static void main(String[] args) {
        List<String> unspecified = Stream.of("A", "B")
            .collect(Collectors.toList());

        ArrayList<String> mutable = Stream.of("A", "B")
            .collect(Collectors.toCollection(ArrayList::new));

        List<String> unmodifiable = Stream.of("A", "B")
            .toList();

        mutable.add("C"); // OK
        System.out.println(mutable); // [A, B, C]
        System.out.println(unspecified); // [A, B]
        System.out.println(unmodifiable); // [A, B]
    }
}
```

### 4.1. When Java 8 Compatibility Is Required

Prior to Java 16, if you need an unmodifiable list **that still accepts null**, you can wrap a new copy:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> result = Collections.unmodifiableList(
    Stream.of("A", null, "B")
        .collect(Collectors.toCollection(ArrayList::new))
);

System.out.println(result); // [A, null, B]
```

This snippet goes inside a method with appropriate imports. `Collections.unmodifiableList` returns an unmodifiable view, so the example intentionally creates a new list **without exposing any mutable reference** externally. It does not make inner elements immutable.

If a **mutable** list is required, use `toCollection(ArrayList::new)` directly since Java 8 rather than `toList()`.

## 5. Differences in `null`, Identity, and Ordering

### 5.1. `toList` Accepts `null`

```java
import java.util.List;
import java.util.stream.Stream;

List<String> withNull = Stream.of("Java", null, "Go")
    .toList();

System.out.println(withNull); // [Java, null, Go]
System.out.println(withNull.size()); // 3
```

By contrast, `Collectors.toUnmodifiableList()` and `List.of(...)` reject `null`:

```java
// Each call below can throw NullPointerException.
// Stream.of("A", null)
//     .collect(Collectors.toUnmodifiableList());
// List.of("A", null);
```

Therefore, switching from `toUnmodifiableList` to `Stream.toList` **changes the null policy**. To filter out nulls:

```java
List<String> clean = Stream.of("Java", null, "Go")
    .filter(java.util.Objects::nonNull)
    .toList();

System.out.println(clean); // [Java, Go]
```

However, **dropping nulls** and **reporting null-data errors** are two different business requirements; do not silently filter nulls if they must be validated or logged.

### 5.2. Instances May Be Value-Based

`Stream.toList()` may return a **value-based instance**. Do not rely on:

- `==` to check list identity.
- `System.identityHashCode(list)` as a business identifier.
- `synchronized(list)` using the returned list itself as a synchronization lock.

Compare contents instead:

```java
List<Integer> first = Stream.of(1, 2).toList();
List<Integer> second = Stream.of(1, 2).toList();

System.out.println(first.equals(second)); // true
```

Do not infer any contract from whether `first == second` happens to hold in a specific JDK.

### 5.3. `toList` Does Not Define a New Order

```java
List<Integer> sorted = Stream.of(4, 1, 3, 2)
    .sorted()
    .toList();

System.out.println(sorted); // [1, 2, 3, 4]
```

A `List` or `IntStream.range` source has encounter order; `sorted` can establish a new sort order. Conversely, a `HashSet` source does not guarantee encounter order, and `unordered()` can drop that constraint. `toList()` preserves order if present; it **does not sort automatically** or restore an order that does not exist.

## 6. `toList()` Ends a Lazy Pipeline

```java
import java.util.Arrays;
import java.util.List;

List<String> source = Arrays.asList(
    "Kotlin", "Go", "Java", "Java"
);

List<String> result = source.stream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .sorted()
    .toList();

System.out.println(result);
// [JAVA, JAVA, KOTLIN]
```

`filter`, `map`, and `sorted` remain intermediate operations; they are evaluated when the `toList` terminal requires the result. If `distinct()` is added:

```java
List<String> unique = source.stream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .distinct()
    .sorted()
    .toList();

System.out.println(unique); // [JAVA, KOTLIN]
```

`toList` does not deduplicate, group, or sort on its own. It merely collects elements at the end of the pipeline into an unmodifiable list.

A `Stream` **can only be consumed once**. When multiple different reports are needed, create a new stream from the source or retain intermediate data if sensible. This does not change when switching from `collect` to `toList`.


## 7. `mapMulti`: One Element Can Emit 0, 1, or Many Results

`mapMulti` is an **intermediate operation** introduced in Java 16. On `Stream<T>`, its main signature is:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Meaning:

- `T`: input element type.
- `R`: output element type.
- `mapper` receives an input element and a consumer to **emit results**.
- Call `consumer.accept(value)` whenever there is a result to pass into the pipeline.
- If the callback never calls `accept`, 0 results are emitted; calling once emits 1; calling multiple times emits multiple results.

Comparison:

```text
map:
  T -> R                       1 input → exactly 1 output

flatMap:
  T -> Stream<R>               1 input → sub-stream with 0..n results

mapMulti:
  (T, Consumer<R>) -> void     1 input → call accept() 0..n times
```

### 7.1. Emitting Two Values from Each Number

```java
import java.util.List;
import java.util.stream.Stream;

public class MapMultiBasics {
    public static void main(String[] args) {
        List<Integer> result = Stream.of(1, 2, 3)
            .<Integer>mapMulti((n, emit) -> {
                emit.accept(n);
                emit.accept(n * 10);
            })
            .toList();

        System.out.println(result);
        // [1, 10, 2, 20, 3, 30]
    }
}
```

`emit` is the name chosen for the pipeline-provided consumer. `mapMulti` returns **`Stream<R>`**, without directly creating a list; the list is created only when the `toList()` terminal operation runs.

### 7.2. Emitting 0 or 1 Result

```java
List<Integer> evenTimesTen = Stream.of(1, 2, 3, 4)
    .<Integer>mapMulti((n, emit) -> {
        if (n % 2 == 0) {
            emit.accept(n * 10);
        }
    })
    .toList();

System.out.println(evenTimesTen); // [20, 40]
```

Equivalent in content:

```java
List<Integer> alternative = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10)
    .toList();
```

For simple filtering and mapping, `filter` combined with `map` is usually **more expressive**. `mapMulti` shines when one input needs to emit **multiple results** or involves custom conditional and looping logic.

### 7.3. One Element Emitting Multiple Records

```java
List<Integer> repeated = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        for (int i = 0; i < n; i++) {
            emit.accept(n);
        }
    })
    .toList();

System.out.println(repeated); // [1, 2, 2, 3, 3, 3]
```

On an ordered stream, the logical output order reflects the source order and the emission order inside the callback. **Result order** still differs from **lambda execution order** when running in parallel.

## 8. `mapMulti` or `flatMap`?

Requirement: for each positive `n` in `[1, 2, 3]`, emit the sequence `1..n`.

### 8.1. `flatMap` Approach

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

List<Integer> byFlatMap = Stream.of(1, 2, 3)
    .flatMap(n -> IntStream.rangeClosed(1, n).boxed())
    .toList();

System.out.println(byFlatMap); // [1, 1, 2, 1, 2, 3]
```

`flatMap` has existed since Java 8, though the `toList()` terminal in this example requires Java 16+. If targeting Java 8 source code, use `collect(Collectors.toList())` instead of this terminal.

### 8.2. `mapMulti` Approach

```java
List<Integer> byMapMulti = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        for (int i = 1; i <= n; i++) {
            emit.accept(i);
        }
    })
    .toList();

System.out.println(byMapMulti); // [1, 1, 2, 1, 2, 3]
```

With `mapMulti`, the callback does not need to create an explicit sub-`Stream`. The API is especially appropriate when each input emits a **small, possibly zero** number of elements, or when describing the logic with a loop is easier to read.

### 8.3. Comparison Table

| Criterion | `mapMulti` | `flatMap` |
| --- | --- | --- |
| First version | Java 16 | Java 8 |
| Mapper | Calls `Consumer.accept` zero or more times | Returns a sub-`Stream` |
| Output element count | 0..n | 0..n |
| Must create a sub-stream in callback? | No | Yes |
| When data is already a sub-stream | Can feel less natural | Usually very convenient |
| Need loops/branches to emit few results | Often concise | Can be more verbose |
| Managing sub-stream created by mapper | No sub-stream | `flatMap` closes sub-stream after consumption |
| Need to run on Java 8/11 | Cannot be used | Can be used |
| Always faster? | No guarantee | No guarantee |

`mapMulti` can reduce the overhead of allocating many short-lived sub-streams, **yet does not mean it is always faster than `flatMap`**. When a natural sub-stream already exists such as `group.stream()`, `flatMap` can still be clearer.

## 9. `mapMulti` Patterns in Data Processing

### 9.1. Flattening Sublists

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

List<List<String>> groups = Arrays.asList(
    Arrays.asList("A", "B"),
    Collections.<String>emptyList(),
    Arrays.asList("C", "D")
);

List<String> flattened = groups.stream()
    .<String>mapMulti((group, emit) -> {
        for (String value : group) {
            emit.accept(value);
        }
    })
    .toList();

System.out.println(flattened); // [A, B, C, D]
```

Each group is iterated, emitting 0..n elements. When you already have `List<List<T>>`, `flatMap(List::stream)` is also very natural; the choice should depend on clarity and measured performance needs.

### 9.2. Splitting Words and Normalizing

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

List<String> lines = Arrays.asList(
    " Java   Stream ",
    "",
    "mapMulti flatMap"
);

List<String> words = lines.stream()
    .<String>mapMulti((line, emit) -> {
        for (String word : line.trim().split("\\s+")) {
            if (!word.isEmpty()) {
                emit.accept(word.toLowerCase(Locale.ROOT));
            }
        }
    })
    .toList();

System.out.println(words);
// [java, stream, mapmulti, flatmap]
```

`split` still allocates arrays and strings as usual. `mapMulti` only avoids the requirement of **creating an explicit sub-stream**, without eliminating all text-parsing costs.

### 9.3. Filtering by Instance Type

```java
import java.util.List;
import java.util.stream.Stream;

List<String> strings = Stream.<Object>of(
        "Java", 42, "Go", 7.5, "Kotlin")
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String) {
            emit.accept((String) value);
        }
    })
    .toList();

System.out.println(strings); // [Java, Go, Kotlin]
```

An alternative is `filter(String.class::isInstance).map(String.class::cast)`. When there is only a simple type filter/cast, using two separate operations can be easier to read.

### 9.4. Generating Labels from Records with Sublists

Java 16+ example; the entire snippet below can be placed inside a method body of a class:

```java
class Order {
    final String id;
    final List<String> tags;

    Order(String id, List<String> tags) {
        this.id = id;
        this.tags = tags;
    }
}

List<Order> orders = Arrays.asList(
    new Order("D1", Arrays.asList("urgent", "paid")),
    new Order("D2", Arrays.asList("paid")),
    new Order("D3", Arrays.asList())
);

List<String> labels = orders.stream()
    .<String>mapMulti((order, emit) -> {
        for (String tag : order.tags) {
            emit.accept(order.id + ":" + tag);
        }
    })
    .toList();

System.out.println(labels);
// [D1:urgent, D1:paid, D2:paid]
```

The example assumes `java.util.Arrays` and `java.util.List` are imported. Child elements are emitted in `tags` order. If you want to deduplicate labels, add `distinct` before `toList`.

## 10. Generic Type Inference of `mapMulti`

Because `mapMulti`'s callback returns `void`, the compiler sometimes **struggles to infer the output type `R`** in lambdas with multiple branches or conditional emissions. The fix is providing a type witness:

```java
List<Integer> parsed = Stream.of("10", "X", "20")
    .<Integer>mapMulti((text, emit) -> {
        if (text.matches("\\d+")) {
            emit.accept(Integer.parseInt(text));
        }
    })
    .toList();

System.out.println(parsed); // [10, 20]
```

The syntax `.<Integer>mapMulti(...)` explicitly specifies `R = Integer`. It does not alter runtime logic.

```java
List<String> converted = Stream.of(10, 20)
    .<String>mapMulti((n, emit) -> {
        emit.accept("N=" + n);
    })
    .toList();

System.out.println(converted); // [N=10, N=20]
```

Here the input type is `Integer`, while the output type is `String`. The two types need not be the same.

### 10.1. `Stream.toList()` Does Not Automatically Widen Generics

```java
List<Number> numbers = Stream.<Number>of(1, 2.5)
    .toList();

System.out.println(numbers); // [1, 2.5]
```

You cannot directly assign `List<Integer>` to `List<Number>`: Java generics are invariant. For example, `Stream.of(1,2,3).toList()` creates `List<Integer>`; when you want `List<Number>`, supply type `Number` to the stream or apply a corresponding transformation.

## 11. Variants Returning Primitive Streams

On `Stream<T>`, Java 16 provides:

```java
IntStream mapMultiToInt(
    BiConsumer<? super T, ? super IntConsumer> mapper
);

LongStream mapMultiToLong(
    BiConsumer<? super T, ? super LongConsumer> mapper
);

DoubleStream mapMultiToDouble(
    BiConsumer<? super T, ? super DoubleConsumer> mapper
);
```

These methods emit `int`, `long`, and `double` directly, avoiding unnecessary boxing when processing numbers.

Example:

```java
import java.util.stream.Stream;

public class MapMultiToIntExample {
    public static void main(String[] args) {
        int sum = Stream.of("10,20", "", "30")
            .mapMultiToInt((text, emit) -> {
                if (!text.isEmpty()) {
                    for (String token : text.split(",")) {
                        emit.accept(Integer.parseInt(token));
                    }
                }
            })
            .sum();

        System.out.println(sum); // 60
    }
}
```

### 11.1. Primitive Streams Also Have `mapMulti`

`IntStream.mapMulti(IntMapMultiConsumer)` receives an `int` and an `IntConsumer`:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class IntStreamMapMultiExample {
    public static void main(String[] args) {
        int[] values = IntStream.of(1, 2, 3, 4)
            .mapMulti((n, emit) -> {
                if (n % 2 == 0) {
                    emit.accept(n);
                    emit.accept(n * 10);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [2, 20, 4, 40]
    }
}
```

Similarly, there are `LongStream.mapMulti(LongMapMultiConsumer)` and `DoubleStream.mapMulti(DoubleMapMultiConsumer)`.

| Method | Source | Result |
| --- | --- | --- |
| `Stream.mapMulti` | `Stream<T>` | `Stream<R>` |
| `Stream.mapMultiToInt` | `Stream<T>` | `IntStream` |
| `Stream.mapMultiToLong` | `Stream<T>` | `LongStream` |
| `Stream.mapMultiToDouble` | `Stream<T>` | `DoubleStream` |
| `IntStream.mapMulti` | `IntStream` | `IntStream` |
| `LongStream.mapMulti` | `LongStream` | `LongStream` |
| `DoubleStream.mapMulti` | `DoubleStream` | `DoubleStream` |

If the output is used for numeric sums or statistics, primitive streams can avoid the overhead of `Integer`/`Long`/`Double`. Even so, integer overflow and floating-point rounding errors still must be handled according to business requirements.


## 12. Consumer Lifecycle, Laziness, and Parallel Streams

`mapMulti` does not execute immediately when building the pipeline:

```java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n * 2);
    });

// No terminal operation yet; source consumption has not been requested.
List<Integer> values = pipeline.toList();

System.out.println(values); // [2, 4, 6]
```

Requirements match those of Stream mappers:

- **Non-interfering:** do not modify source structure during traversal.
- **Stateless:** do not use external counters or mutable lists to decide outputs depending on thread order.
- **Consumer used only inside the callback:** do not store `emit` to call later, nor hand it to another thread to invoke after the mapper returns.
- **Do not depend on side effects:** terminal operations or short-circuiting may not evaluate every callback as you expect.

### 12.1. Wrong: Storing the Consumer to Emit Results Later

```java
// DO NOT DO THIS:
// List<Consumer<Integer>> saved = new ArrayList<>();
//
// Stream.of(1, 2)
//     .<Integer>mapMulti((n, emit) -> saved.add(emit))
//     .toList();
//
// saved.forEach(consumer -> consumer.accept(100));
```

The consumer received by `mapMulti` belongs to the stream runtime's processing scope; it is **not an object that may be retained to emit results later**. Even when callbacks do not run in parallel, this still violates the API's contract.

### 12.2. `limit` Can Short-Circuit

```java
List<Integer> first = Stream.of(1, 2, 3, 4)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .limit(3)
    .toList();

System.out.println(first); // [1, 10, 2]
```

`limit(3)` keeps the first three elements of the **output stream**, not the first three elements of the source. Do not rely on how many times the mapper is invoked or how many `emit.accept` calls are processed internally; buffering and short-circuiting depend on the pipeline/implementation.

A mapper emitting many results per call can consume resources even when downstream only needs a few. Choosing `mapMulti` over `flatMap` must consider both **per-element output volume** and processing goals, not just line count.

### 12.3. Parallel Streams: Logical Order Differs from Execution Order

```java
List<Integer> result = Stream.of(1, 2, 3, 4)
    .parallel()
    .<Integer>mapMulti((n, emit) -> {
        if (n % 2 == 0) {
            emit.accept(n);
            emit.accept(n * 10);
        }
    })
    .toList();

System.out.println(result); // [2, 20, 4, 40]
```

In this example, the mapper stores no external state. `toList` respects the encounter order of an ordered source even when callbacks execute across multiple threads. By contrast, writing:

```java
// DO NOT DO THIS:
// List<Integer> external = new ArrayList<>();
// Stream.of(1,2,3,4).parallel()
//     .<Integer>mapMulti((n, emit) -> {
//         external.add(n); // Unsafe side effect.
//         emit.accept(n);
//     }).toList();
```

can cause race conditions or corrupt logic. Use collectors/terminal operations rather than updating a shared `ArrayList`.

### 12.4. I/O Sources Still Need Separate Closing

`mapMulti` does not close a source like `Files.lines`; nor does `toList` automatically release all I/O source resources. Java 16+ example:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<String> readWords(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines.<String>mapMulti((line, emit) -> {
            for (String word : line.split("\\s+")) {
                if (!word.isEmpty()) {
                    emit.accept(word);
                }
            }
        }).toList();
    }
}
```

Here `try-with-resources` closes `lines` upon completion or error. If the callback opens additional resources itself, it must manage closing them within the proper ownership scope. `mapMulti` is not a substitute for I/O resource management.

## 13. Relationship with Collectors, Grouping, and Stream Gatherers

`mapMulti` processes **one input element and emits 0..n elements**. It is not a collector or grouping mechanism:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<List<String>> groups = Arrays.asList(
    Arrays.asList("Java", "Go"),
    Arrays.asList("Java", "Kotlin")
);

Map<Integer, Long> counts = groups.stream()
    .<String>mapMulti((group, emit) -> {
        for (String value : group) {
            emit.accept(value);
        }
    })
    .collect(Collectors.groupingBy(
        String::length,
        Collectors.counting()
    ));

System.out.println(counts.get(4)); // 2 (Java, Java)
```

- `mapMulti` flattens the groups into a stream of strings.
- `groupingBy` is the collector for terminal `collect`.
- `counting` counts items per group.
- There is no `toList` in this pipeline because the desired result is `Map<Integer, Long>`.

Likewise, `mapMulti` does not replace `reduce`; to aggregate numbers, use `mapMultiToInt(...).sum()` or an appropriate downstream.

Stream Gatherers are a separate API group (in JDKs newer than Java 16) intended for stateful or complex windowing transformations. Do not treat `mapMulti` as a stateful collector or a gatherer: a `mapMulti` callback must obey the stateless/non-interfering rules of an intermediate operation.

## 14. Java 8/11 Compatibility and Upgrade Strategy

### 14.1. Java 16 Snippets Do Not Compile Under `--release 11`

```java
List<String> names = Stream.of("Java", "Go").toList();

List<Integer> output = Stream.of(1, 2)
    .<Integer>mapMulti((n, emit) -> emit.accept(n * 10))
    .toList();
```

Both `Stream.toList` and `mapMulti` were introduced in Java 16. If the project sets `--release 8` or `--release 11`, the compiler does not see those methods, even if the machine runs a newer JDK to invoke the compiler.

Code compiled for Java 16 must also run on an environment compatible with the **class-file version** and Java 16 APIs. Upgrading only the compiler without checking the deployment runtime can cause the application to fail on startup.

### 14.2. Data-Equivalent Java 8 Pattern

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Java8Fallback {
    public static void main(String[] args) {
        List<String> names = Stream.of("Java", "Go")
            .collect(Collectors.toList());

        List<Integer> output = Arrays.asList(1, 2)
            .stream()
            .flatMap(n -> Stream.of(n, n * 10))
            .collect(Collectors.toList());

        System.out.println(names);  // [Java, Go]
        System.out.println(output); // [1, 10, 2, 20]
    }
}
```

Data-equivalent, **yet `Collectors.toList()` does not promise unmodifiability**. When the hard requirement in Java 8 is an unmodifiable list that accepts null, wrap a newly created list with `Collections.unmodifiableList` without leaking external references.

If an explicitly mutable list is needed, use `Collectors.toCollection(ArrayList::new)` from Java 8. If an **unmodifiable list that rejects null** is needed, Java 10 has `Collectors.toUnmodifiableList`; Java 8 requires explicit null checks and an appropriate wrapper.

### 14.3. Compiling Java 16+ Code

From the terminal of a machine **with a JDK supporting Java 16 or newer installed**, using `Jdk16StreamCheck.java` from the next section:

```text
javac --release 16 Jdk16StreamCheck.java
java Jdk16StreamCheck
```

These are instructions to run yourself, **not compilation results verified inside this lesson**. In Gradle/Maven projects, ensure the toolchain, target release, and actual JDK runtime all support the APIs used.

When an application must run on Java 11, do not set `--release 16` expecting the bytecode to run under JDK 11. Instead, use compatible APIs or raise the application's platform requirement.

## 15. Comprehensive Verification Program (Java 16+)

Create a file `Jdk16StreamCheck.java` with the content below. The program checks:

- `toList` preserves order and duplicate values.
- The resulting list is unmodifiable.
- `toList` accepts null; `toUnmodifiableList` rejects null.
- `mapMulti` emits 0..n elements.
- `mapMultiToInt` and `IntStream.mapMulti`.
- Ordered parallel stream results.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class Jdk16StreamCheck {
    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> names = Stream.of("Java", "Go", "Java")
            .toList();

        check(names.equals(Arrays.asList("Java", "Go", "Java")),
            "toList wrong order or duplicate values");

        boolean rejectedAdd = false;
        try {
            names.add("Rust");
        } catch (UnsupportedOperationException expected) {
            rejectedAdd = true;
        }
        check(rejectedAdd, "toList must be unmodifiable");

        List<String> nullable = Stream.of(
            "A", (String) null, "B").toList();

        check(nullable.size() == 3 && nullable.get(1) == null,
            "toList must accept null");

        boolean rejectedNull = false;
        try {
            Stream.of("A", (String) null)
                .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            rejectedNull = true;
        }
        check(rejectedNull, "toUnmodifiableList must reject null");

        List<Integer> expanded = Stream.of(1, 2, 3)
            .<Integer>mapMulti((n, emit) -> {
                for (int i = 0; i < n; i++) {
                    emit.accept(n);
                }
            })
            .toList();

        check(expanded.equals(Arrays.asList(1, 2, 2, 3, 3, 3)),
            "mapMulti wrong element count");

        List<Integer> even = Stream.of(1, 2, 3, 4)
            .<Integer>mapMulti((n, emit) -> {
                if (n % 2 == 0) {
                    emit.accept(n * 10);
                }
            })
            .toList();

        check(even.equals(Arrays.asList(20, 40)),
            "mapMulti filtered incorrectly");

        int sum = Stream.of("1,2", "", "3")
            .mapMultiToInt((text, emit) -> {
                if (!text.isEmpty()) {
                    for (String token : text.split(",")) {
                        emit.accept(Integer.parseInt(token));
                    }
                }
            })
            .sum();

        check(sum == 6, "mapMultiToInt wrong sum");

        int[] primitive = IntStream.of(1, 2, 3)
            .mapMulti((n, emit) -> {
                emit.accept(n);
                if (n % 2 == 0) {
                    emit.accept(n * 10);
                }
            })
            .toArray();

        check(Arrays.equals(
                primitive, new int[] {1, 2, 20, 3}),
            "IntStream.mapMulti wrong");

        List<Integer> parallel = Stream.of(1, 2, 3, 4)
            .parallel()
            .<Integer>mapMulti((n, emit) -> {
                emit.accept(n);
                emit.accept(n * 10);
            })
            .toList();

        check(parallel.equals(Arrays.asList(
                1, 10, 2, 20, 3, 30, 4, 40)),
            "parallel mapMulti wrong encounter order");

        ArrayList<Integer> mutable = Stream.of(1, 2)
            .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(3);

        check(mutable.equals(Arrays.asList(1, 2, 3)),
            "toCollection must allow mutation");

        System.out.println("PASS: Stream.toList and mapMulti");
    }
}
```

When compiled and run successfully on Java 16+, the program prints:

```text
PASS: Stream.toList and mapMulti
```

This sample verifies selected contracts, not performance benchmarks or a proof that every custom callback is correct. Additional tests for boundary data, empty sources, nulls, and resource limits are needed for real applications.

## 16. Common Misconceptions and Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| `cannot find symbol: toList()` | Compiling against pre-Java 16 APIs | Use compatible `collect` or raise release level. |
| `cannot find symbol: mapMulti(...)` | Pre-Java 16 JDK APIs | Use `flatMap` on Java 8/11. |
| `list.add(...)` throws `UnsupportedOperationException` | `Stream.toList()` returns an unmodifiable list | Use `toCollection(ArrayList::new)` if mutation is needed. |
| Replacing `Collectors.toList()` with `toList` breaks downstream | The two do not share the same mutability contract | Audit all `add`, `remove`, `sort`, and `set` sites. |
| Assuming `toList()` always returns `ArrayList` | No implementation type is guaranteed | Use the `List` interface or an explicit collection factory. |
| Assuming `toList()` rejects null | Confused with `List.of` / `toUnmodifiableList` | Clarify the null policy explicitly. |
| Null data gets filtered out silently without error | Added `filter(Objects::nonNull)` automatically | Choose between dropping nulls or reporting errors per business rules. |
| Comparing two lists with `==` | Confusing identity with contents; value-based instances | Use `equals` to check values. |
| Using `List<Number>` for `Stream<Integer>.toList()` | Generic invariance | Declare `Stream.<Number>of(...)` or convert types. |
| `mapMulti` has type inference error | Compiler could not infer `R` from callback | Use `.<R>mapMulti(...)`. |
| `mapMulti` emits no values | Mapper never called the consumer | Check conditional branches and `accept` calls. |
| `mapMulti` emits unintended duplicate data | Called consumer multiple times | Clarify 0..n rules; use `distinct` if needed. |
| Expecting `mapMulti` to beat every `flatMap` | Performance depends on data and JDK | Benchmark on representative workloads. |
| Trying to save the consumer to call later | Violates consumer lifecycle | Only emit results inside the callback. |
| List corrupted when using parallel | Lambda writes to shared state | Use stateless functions and terminal collectors. |
| Miscounting callbacks with `limit`/`findFirst` | Short-circuiting and optimizations do not fix call counts | Never use side effects for mandatory logic. |
| Using `Stream.toList` to sort in place | Returned list is unmodifiable | Use `sorted` beforehand or collect into a mutable list. |
| Leaking I/O resources despite `toList` | Terminal operation does not replace closing the source | Use `try-with-resources` for I/O-backed sources. |
| Code runs on newer JDK but fails in older deployment | Runtime/release mismatch | Verify toolchain and actual execution version. |

## 17. Practice Exercises

### Exercise 1 — Which List Is Mutable?

Consider:

```java
List<Integer> a = Stream.of(1, 2).toList();
List<Integer> b = Stream.of(1, 2)
    .collect(Collectors.toList());
ArrayList<Integer> c = Stream.of(1, 2)
    .collect(Collectors.toCollection(ArrayList::new));
```

Among the three lists, which one is **guaranteed** mutable, which one is **guaranteed** unmodifiable, and which one has no mutability guarantee?

### Exercise 2 — `null`

Predict the outcome:

```java
List<String> a = Stream.of("A", null, "B").toList();
List<String> b = Stream.of("A", null, "B")
    .collect(Collectors.toUnmodifiableList());
```

Which succeeds and which throws an error? Explain the minimum JDK versions.

### Exercise 3 — Converting from `flatMap` to `mapMulti`

Use `mapMulti` to emit values from the following `List<List<Integer>>`:

```java
List<List<Integer>> batches = Arrays.asList(
    Arrays.asList(1, 2),
    Arrays.asList(),
    Arrays.asList(3, 4)
);
```

The result should be `[1, 2, 3, 4]`. Also write the corresponding `flatMap` version and explain version differences.

### Exercise 4 — Choose `map`, `filter`, or `mapMulti`?

Given `[1, 2, 3]`, each number `n` must produce `n` and `-n`. Write it using `mapMulti`. If the problem only asks for `n * 2`, which API is easier to read?

### Exercise 5 — Primitive Stream

Given strings `["5,10", "", "15"]`. Use `mapMultiToInt` to compute the sum. Why can this avoid boxing compared to `mapMulti` returning `Stream<Integer>`?

### Exercise 6 — Generic Inference

Write `mapMulti` from `Stream<Object>` keeping only `String` elements. Use a type witness to produce `List<String>` and explain why `R` must be unified.

### Exercise 7 — Java 11 Still Needs an Unmodifiable List

A project must run on Java 11 and requires an unmodifiable result that **accepts null**. Why can't `Stream.toList` or `Collectors.toUnmodifiableList` be used? Write a solution using `Collections.unmodifiableList` with a private list.

### Exercise 8 — Ordering and Short-Circuiting

```java
List<Integer> result = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .limit(4)
    .toList();
```

Predict the list contents. Can you assert that the callback is called exactly twice in every implementation?

## 18. Reference Solutions

**Exercise 1:** `a` is **unmodifiable** per `Stream.toList`'s contract. `b` has **no guarantee** on mutability (`Collectors.toList`); do not rely on observed behavior in a specific JDK. `c` is an `ArrayList` and is mutable.

**Exercise 2:** `a` succeeds on Java 16+, producing `[A, null, B]`. `b` throws `NullPointerException` because `Collectors.toUnmodifiableList` since Java 10 rejects null.

**Exercise 3:**

```java
List<Integer> withMapMulti = batches.stream()
    .<Integer>mapMulti((batch, emit) -> {
        for (Integer n : batch) {
            emit.accept(n);
        }
    })
    .toList();

List<Integer> withFlatMap = batches.stream()
    .flatMap(List::stream)
    .toList();
```

Both produce `[1, 2, 3, 4]` on Java 16+. If Java 8 is required, `flatMap` is available, though the terminal must change to `collect(Collectors.toList())`.

**Exercise 4:**

```java
List<Integer> output = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(-n);
    })
    .toList();

System.out.println(output); // [1, -1, 2, -2, 3, -3]
```

If only doubling is needed, `map(n -> n * 2)` is simpler and explicitly conveys a one-to-one relationship.

**Exercise 5:**

```java
int sum = Stream.of("5,10", "", "15")
    .mapMultiToInt((text, emit) -> {
        if (!text.isEmpty()) {
            for (String token : text.split(",")) {
                emit.accept(Integer.parseInt(token));
            }
        }
    })
    .sum();

System.out.println(sum); // 30
```

The output is an `IntStream`, avoiding creating boxed `Integer` objects for each number via `Stream<Integer>`.

**Exercise 6:**

```java
List<String> strings = Stream.<Object>of(
        "Java", 42, "Go", true)
    .<String>mapMulti((value, emit) -> {
        if (value instanceof String) {
            emit.accept((String) value);
        }
    })
    .toList();
```

Type witness `<String>` sets the output type `R`; non-`String` elements are not emitted.

**Exercise 7:**

```java
List<String> list = java.util.Collections.unmodifiableList(
    Stream.of("A", null, "B")
        .collect(Collectors.toCollection(
            java.util.ArrayList::new))
);
```

`Stream.toList` only exists since Java 16; `toUnmodifiableList` exists since Java 10 but rejects null. Wrapping a newly created list without exposing any mutable reference meets the structural requirement of the example, yet does not make inner objects immutable.

**Exercise 8:** `result = [1, 10, 2, 20]`. `limit(4)` bounds the output; it creates no contract that the callback runs exactly twice across all implementations. Never use side effects to assert how many times a callback must run.

## 19. Upgrade Checklist from Java 8/11 to Java 16+

Before replacing legacy code, check:

- [ ] Both the compile JDK and runtime environment support Java 16+ if using `toList`/`mapMulti`.
- [ ] The project's `--release` level or toolchain is no longer below Java 16.
- [ ] Whether downstream code calls `add`, `remove`, `sort`, or `set` on the resulting list.
- [ ] Whether the application requires a concrete list type (such as `ArrayList`) or a mutable list.
- [ ] Whether the `null` policy is clear: accept, skip, or error.
- [ ] Whether code relies on the returned list's object identity or uses the list as a synchronization lock.
- [ ] Whether `mapMulti`'s generic type `R` is inferred properly; add a type witness if needed.
- [ ] Whether the `mapMulti` callback only emits data while the mapper runs and never retains the consumer for later calls.
- [ ] Whether callbacks are stateless and non-interfering, never updating shared structures in parallel.
- [ ] Whether `mapMulti` emits enough results per element to raise memory or short-circuiting concerns.
- [ ] Whether primitive variants were considered to avoid boxing on numeric work.
- [ ] If code already uses `flatMap`, whether switching provides a clear benefit or just adds complexity.
- [ ] Whether I/O-backed source Streams are still closed with `try-with-resources`.
- [ ] Whether empty sources, single elements, nulls, multi-outputs, duplicates, ordered parallel runs, and short-circuiting are tested.
- [ ] If performance matters, whether representative workloads were benchmarked instead of guessed.

## 20. Summary

`Stream.toList()` and `Stream.mapMulti(...)` are both additions from **Java 16**, serving two distinct roles:

```java
// Terminal operation: collects an unmodifiable list.
List<String> values = Stream.of("A", "B").toList();

// Intermediate operation: each input emits 0..n results.
List<Integer> expanded = Stream.of(1, 2, 3)
    .<Integer>mapMulti((n, emit) -> {
        emit.accept(n);
        emit.accept(n * 10);
    })
    .toList();
```

- **`toList`:** preserves encounter order if the source is ordered, allows null, disallows list mutation, and makes no guarantees on implementation class or identity.
- **`Collectors.toList`:** Java 8-compatible, yet **makes no guarantees** on mutability or list type.
- **`Collectors.toUnmodifiableList`:** available since Java 10, disallows mutation, and **rejects null**.
- **`mapMulti`:** emits 0..n elements via a consumer, and can express loops/conditionals more clearly than `flatMap` in some problems.
- **Primitive variants:** `mapMultiToInt/Long/Double` and primitive `mapMulti` from Java 16 avoid unnecessary boxing.
- **Compatibility and performance:** choose APIs based on contract, JDK level, data, and tests; never swap code mechanically or assume `mapMulti` is always faster than `flatMap`.

Understanding these two additions thoroughly lets you upgrade Java Stream API code safely: writing clear pipelines, preserving output semantics, and controlling JDK compatibility before optimizing or deploying programs to production.