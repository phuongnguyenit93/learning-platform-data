# Converting to Object Streams with `boxed` and `mapToObj`

## 1. When do you need to leave a primitive stream?

The Java Stream API provides three specialized stream types for processing primitive numbers:

- `IntStream` holds `int` values.
- `LongStream` holds `long` values.
- `DoubleStream` holds `double` values.

Primitive streams let you write declarative pipelines with `filter`, `map`, `reduce`, `sum`, `average`, and `summaryStatistics` without typically wrapping every number in an object. Even so, many processing steps require **object types**: putting numbers into a `List<Integer>`, building DTO records, formatting each number as a string, or using `Collector`s such as `groupingBy`.

In those cases, two essential methods are:

- **`boxed()`**: wraps each primitive value into its corresponding wrapper (`Integer`, `Long`, `Double`).
- **`mapToObj(mapper)`**: uses a function to transform each primitive value into **an object of a chosen type**.

First example:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 4)
    .boxed()
    .toList();
// [1, 2, 3, 4]

List<String> labels = IntStream.rangeClosed(1, 4)
    .mapToObj(number -> "Code-" + number)
    .toList();
// [Code-1, Code-2, Code-3, Code-4]
```

Both pipelines start from `IntStream`, yet end up as `Stream<Integer>` and `Stream<String>` before `toList()` is called.

After this lesson, you will be able to read the signatures of these conversion operations, choose the right point to switch types, combine them with `collect` and grouping, and recognize boxing costs, laziness, state, and arithmetic or performance limits.

## 2. Identifying pipeline types before and after conversion

Common stream types in the **Primitive Streams** chapter:

| Initial stream | Element type | After `boxed()` | `mapToObj` examples |
| --- | --- | --- | --- |
| `IntStream` | `int` | `Stream<Integer>` | `Stream<String>`, `Stream<Item>` |
| `LongStream` | `long` | `Stream<Long>` | `Stream<BigInteger>`, `Stream<Invoice>` |
| `DoubleStream` | `double` | `Stream<Double>` | `Stream<String>`, `Stream<Measurement>` |

Diagram:

```text
IntStream (int)
   │
   ├── boxed() ──────────────> Stream<Integer>
   │
   ├── mapToObj(n -> "...") ─> Stream<String>
   │
   └── mapToObj(n -> new R(n)) ─> Stream<R>
                                  │
                                  └── collect(...), toList(), groupingBy(...)
```

Keep in mind:

1. `boxed()` **does not** return `List<Integer>`; it returns a `Stream<Integer>` that still needs a terminal operation.
2. `mapToObj` **does not** automatically collect results into a collection; it produces a `Stream<U>`.
3. `IntStream` has `toArray()` returning `int[]` yet **lacks** a `toList()` method. To get a `List<Integer>`, you typically use `boxed().toList()`.
4. After converting to an object stream, `map`, `filter`, `flatMap`, and `collect(Collector)` on `Stream<T>` operate on objects.

Example tracking types directly in code:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

IntStream source = IntStream.range(0, 3); // int: 0, 1, 2
Stream<Integer> objects = source.boxed(); // Integer: 0, 1, 2

System.out.println(objects.toList());    // [0, 1, 2]
// Cannot reuse source: the pipeline has already been consumed.
```

`IntStream.range(startInclusive, endExclusive)` includes the start and excludes the end; `rangeClosed(a, b)` includes both endpoints when elements exist in the range.

## 3. `boxed()`: wrapping values without changing data meaning

Method signatures:

```java
// On IntStream:
Stream<Integer> boxed()

// On LongStream:
Stream<Long> boxed()

// On DoubleStream:
Stream<Double> boxed()
```

`boxed()` is an **intermediate operation** used to create an object stream containing wrappers of the primitive values.

### 3.1. From `IntStream` to `List<Integer>`

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> scores = IntStream.of(70, 90, 80)
    .boxed()
    .toList();

System.out.println(scores); // [70, 90, 80]
```

In JDK 16 and later, `Stream.toList()` creates an **unmodifiable** list; calling `scores.add(100)` throws `UnsupportedOperationException`. If you need a modifiable collection under an explicit contract, specify the collection type:

```java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<Integer> mutableScores = IntStream.of(70, 90, 80)
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

mutableScores.add(100); // Valid.
```

`Collectors.toList()` is also an option for collecting, yet it **makes no guarantees** on the list type, mutability, or serializability. Do not rely on its current implementation when designing API contracts.

### 3.2. From `LongStream` and `DoubleStream`

```java
import java.util.List;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

List<Long> ids = LongStream.of(10L, 20L, 30L)
    .boxed()
    .toList();

List<Double> temperatures = DoubleStream.of(21.5, 23.0, 20.75)
    .boxed()
    .toList();

System.out.println(ids);          // [10, 20, 30]
System.out.println(temperatures); // [21.5, 23.0, 20.75]
```

`boxed()` preserves the **numeric value** and changes its representation to a wrapper; it does not format by locale, round, attach units, or validate value domains. If your problem requires those operations, use an explicit mapper with `mapToObj` or an earlier transformation step.

### 3.3. Why is it called boxing?

`int` is a primitive type, whereas `Integer` is a wrapper object. Converting:

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(primitive);
int again = wrapper.intValue();
```

is called **boxing** and **unboxing**, respectively. Java can perform these automatically (autoboxing/unboxing) where needed. `IntStream.boxed()` is the API-defined way to perform this conversion *across an entire data stream*.

Do not compare wrappers with `==` to test value equality: `==` between two objects compares references and can be affected by caching mechanisms. Use `equals` or unbox to compare values; for data that could be `null`, establish a null policy before unboxing.

## 4. `mapToObj`: mapping numbers to arbitrary objects

Corresponding signatures:

```java
// IntStream:
<U> Stream<U> mapToObj(IntFunction<? extends U> mapper)

// LongStream:
<U> Stream<U> mapToObj(LongFunction<? extends U> mapper)

// DoubleStream:
<U> Stream<U> mapToObj(DoubleFunction<? extends U> mapper)
```

`U` is the new object type inferred by the compiler. `IntFunction<U>` takes an `int` and returns an object `U`, `LongFunction<U>` takes `long`, and `DoubleFunction<U>` takes `double`. When the mapper is evaluated, each source element produces **one result value**, even if that value is `null`.

### 4.1. Turning numbers into meaningful strings

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(index -> "Page " + index)
    .toList();

System.out.println(labels); // [Page 1, Page 2, Page 3]
```

If you use `boxed().map(...)`, you still produce the result, yet converting to a wrapper is merely an intermediate step:

```java
List<String> alsoLabels = IntStream.rangeClosed(1, 3)
    .boxed()
    .map(index -> "Page " + index)
    .toList();
```

Semantically, both approaches yield the same result. `mapToObj` directly expresses the `int → String` mapping without requiring boxing to `Integer` as a separate API step. This can reduce intermediate overhead, though actual optimization depends on the JDK and JVM.

### 4.2. Turning numbers into records/DTOs

```java
import java.util.List;
import java.util.stream.IntStream;

record PageLink(int pageNumber, String path) {}

List<PageLink> links = IntStream.rangeClosed(1, 3)
    .mapToObj(page -> new PageLink(page, "/catalog?page=" + page))
    .toList();

System.out.println(links.get(1));
// PageLink[pageNumber=2, path=/catalog?page=2]
```

The strength of `mapToObj` is that **the result type is determined by the business domain**. Instead of wrapping numbers and parsing them in multiple places, you can construct named objects with valid fields convenient for downstream processing.

### 4.3. Mapping `long` and `double`

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.DoubleStream;
import java.util.stream.LongStream;

List<String> orderIds = LongStream.of(101L, 102L)
    .mapToObj(id -> "ORD-" + id)
    .toList();
// [ORD-101, ORD-102]

record Measurement(double value, String unit) {}

List<Measurement> lengths = DoubleStream.of(2.5, 3.25)
    .mapToObj(value -> new Measurement(value, "m"))
    .toList();

List<String> formatted = DoubleStream.of(2.5, 3.25)
    .mapToObj(value -> String.format(Locale.ROOT, "%.2f m", value))
    .toList();
// [2.50 m, 3.25 m]
```

The formatting example uses `Locale.ROOT` so output has a consistent decimal separator. For prices, binary floating-point `double` can introduce rounding errors; consider storing monetary amounts as integer minor units (`long` cents/VND) or using `BigDecimal` with explicit rounding rules.

### 4.4. Method references

When you have a method taking a primitive number and returning an object, `mapToObj` can accept a method reference:

```java
import java.util.List;
import java.util.stream.IntStream;

static String formatTicket(int number) {
    return "TICKET-" + number;
}

List<String> tickets = IntStream.rangeClosed(1, 3)
    .mapToObj(YourClass::formatTicket)
    .toList();
```

The snippet above is an example **placed inside a class** named `YourClass` containing the `formatTicket` method. In real code, substitute the actual class name. If a method reference hurts readability due to overloads or generic inference, a short lambda such as `number -> formatTicket(number)` is often clearer.

## 5. Choosing `boxed` or `mapToObj`?

| Criterion | `boxed()` | `mapToObj(...)` |
| --- | --- | --- |
| Goal | Put primitive values into wrappers | Transform primitive values into objects by a rule |
| Must supply a mapper? | No | Yes |
| Return type from `IntStream` | `Stream<Integer>` | `Stream<U>` determined by the mapper |
| Changes value meaning? | No; only changes representation | Can transform, label, build DTOs, apply rules |
| Example | `IntStream.range(1, 5).boxed()` | `IntStream.range(1, 5).mapToObj(n -> "P" + n)` |
| Grouping by the numeric value itself | Convenient | Possible, though no custom mapper is needed |
| Needing a business object | Requires adding `map(...)` after `boxed()` | Direct mapping |

A practical rule of thumb:

- **Need `List<Integer>`, `Set<Long>`, or want to use `Collectors` on wrappers:** usually choose `boxed()`.
- **Need `String`, DTOs, immutable entities, values with units, or complex objects:** choose `mapToObj(...)`.
- **Only need sum, average, min/max, or numeric statistics:** **keep the primitive stream** and use dedicated terminal operations.

Example needing no boxing:

```java
int total = java.util.stream.IntStream.of(10, 20, 30)
    .sum(); // 60

double mean = java.util.stream.IntStream.of(10, 20, 30)
    .average()
    .orElseThrow(); // 20.0
```

Do not switch to an object stream only to return to numeric addition when `sum()` is already available on the primitive stream.

## 6. Combining `boxed` with `Collectors`, grouping, and deduplication

`IntStream` has its own `collect(Supplier<R>, ObjIntConsumer<R>, BiConsumer<R,R>)` method, yet does not accept `Collector<T,A,R>` like `Stream<T>`. If you need factory collectors from `java.util.stream.Collectors`, you usually have to convert to an object stream.

Example grouping even and odd numbers:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, List<Integer>> groups = IntStream.rangeClosed(1, 8)
    .boxed()
    .collect(Collectors.groupingBy(
        value -> value % 2 == 0 ? "even" : "odd"
    ));

System.out.println(groups.get("even")); // [2, 4, 6, 8]
System.out.println(groups.get("odd"));  // [1, 3, 5, 7]
```

`Collectors.groupingBy` does not guarantee the `Map` implementation type or **key** iteration order. On a stream with an encounter order like `IntStream.rangeClosed`, the `List<Integer>` values collected by the default downstream collector preserve element order within each group per the collector contract on ordered streams.

Example building a `Set<Integer>`:

```java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Set<Integer> unique = IntStream.of(3, 1, 3, 2, 1)
    .distinct()
    .boxed()
    .collect(Collectors.toSet());

System.out.println(unique.containsAll(Set.of(1, 2, 3))); // true
```

`Collectors.toSet()` does not guarantee iteration order or implementation type. If the goal is merely removing duplicates before numeric aggregation, calling `distinct()` directly on the primitive stream avoids early boxing:

```java
int sumUnique = IntStream.of(3, 1, 3, 2, 1)
    .distinct()
    .sum(); // 6
```

### 6.1. Why is `boxed` required for certain collectors?

Suppose you want to collect numbers into a list with `Collectors.toList()`:

```java
List<Integer> values = IntStream.rangeClosed(1, 4)
    .boxed()
    .collect(Collectors.toList());
```

You cannot write `IntStream.rangeClosed(1, 4).collect(Collectors.toList())` because `IntStream.collect` has no overload taking a `Collector`. The compiler will report incompatible parameter types.

If your JDK supports `Stream.toList()` and no special collector is needed, `IntStream.rangeClosed(1,4).boxed().toList()` is more concise.

## 7. Practical example: using integer indices to build DTOs and aggregate

An application has two parallel data sources: a list of product SKUs and amounts in VND. It needs to build report lines with sequence number, SKU, and amount, and then aggregate revenue by SKU.

Here `IntStream.range` supplies **indices**, `mapToObj` builds **report objects**, and `collect(groupingBy(...))` aggregates:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class PrimitiveToObjectReport {

    public record SaleLine(int lineNo, String sku, long amountVnd) {}

    public static void main(String[] args) {
        List<String> skus = List.of("PEN", "BOOK", "PEN", "BAG");
        long[] amountsVnd = {12_000L, 85_000L, 8_000L, 150_000L};

        if (skus.size() != amountsVnd.length) {
            throw new IllegalArgumentException("Source element counts do not match");
        }

        List<SaleLine> report = IntStream.range(0, skus.size())
            .mapToObj(i -> new SaleLine(
                i + 1,
                skus.get(i),
                amountsVnd[i]
            ))
            .toList();

        // On JDK 17+, toList() produces an unmodifiable List.
        System.out.println(report.get(0));
        // SaleLine[lineNo=1, sku=PEN, amountVnd=12000]

        Map<String, Long> totalsBySku = report.stream()
            .collect(Collectors.groupingBy(
                SaleLine::sku,
                Collectors.summingLong(SaleLine::amountVnd)
            ));

        System.out.println(totalsBySku.get("PEN"));  // 20000
        System.out.println(totalsBySku.get("BOOK")); // 85000
        System.out.println(totalsBySku.get("BAG"));  // 150000

        long grandTotal = report.stream()
            .mapToLong(SaleLine::amountVnd)
            .sum();
        System.out.println(grandTotal); // 255000
    }
}
```

Type tracking:

| Step | Result type | Meaning |
| --- | --- | --- |
| `IntStream.range(0, skus.size())` | `IntStream` | Primitive indices from 0 to n − 1 |
| `.mapToObj(i -> new SaleLine(...))` | `Stream<SaleLine>` | Creates one DTO per index |
| `.toList()` | `List<SaleLine>` | Collects results, triggering pipeline |
| `report.stream()` | `Stream<SaleLine>` | Opens a new pipeline from resulting data |
| `.mapToLong(SaleLine::amountVnd)` | `LongStream` | Returns to primitive stream for summing |
| `.sum()` | `long` | Terminal operation computing sum |

The `IntStream.range(...).mapToObj(...)` pattern is especially useful when constructing records with an **index**, though it has limitations:

- Both `skus` and `amountsVnd` must have the same size, which is checked beforehand.
- If a source is mutated concurrently, indices may no longer match the data. In real applications, consider immutable snapshots or a unified model per line.
- `long` avoids decimal rounding errors when representing whole minor-unit currency amounts, yet can still **overflow**. `Collectors.summingLong` and `LongStream.sum()` do not detect overflow automatically; for amounts that could exceed the limit, use an appropriate type or validate the data range.
- Do not enable `parallel()` casually if the mapper reads data that might be modified elsewhere; read safety depends on the source and the whole pipeline.

## 8. Returning from an object stream to a primitive stream

In many pipelines, switching to an object stream is only one stage. After creating DTOs, you can **convert back** to a primitive stream for arithmetic calculations.

### 8.1. From `Stream<Integer>` to `IntStream`

```java
import java.util.List;

List<Integer> values = List.of(4, 5, 6);

int sum = values.stream()
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sum); // 15
```

Specialized methods on `Stream<T>`:

| Method | Mapper input | Result |
| --- | --- | --- |
| `mapToInt(ToIntFunction<? super T>)` | `T → int` | `IntStream` |
| `mapToLong(ToLongFunction<? super T>)` | `T → long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<? super T>)` | `T → double` | `DoubleStream` |

If a `Stream<Integer>` contains `null`, `Integer::intValue` throws `NullPointerException` when it encounters that element. Define a null data policy, such as `filter(Objects::nonNull)` if skipping values is allowed, or validate beforehand.

### 8.2. Not every conversion is boxing

Conversions like `IntStream.asLongStream()` or `IntStream.asDoubleStream()` still produce a **primitive stream** with a different numeric type, not wrapper objects. Do not confuse them with `boxed()`:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

LongStream widened = IntStream.of(1, 2, 3)
    .asLongStream(); // int -> long, still primitive.

System.out.println(widened.sum()); // 6
```

For calculations requiring a range larger than `int`, consider widening the type before adding or multiplying; boxing to `Integer` **does not** expand the value range.

## 9. Arrays, lists, generics, and type inference

### 9.1. `int[]` differs from `Integer[]` and `List<Integer>`

A primitive array source can become an `IntStream`:

```java
import java.util.Arrays;
import java.util.List;

int[] source = {7, 8, 9};

int[] primitiveArray = Arrays.stream(source)
    .toArray(); // int[]

Integer[] objectArray = Arrays.stream(source)
    .boxed()
    .toArray(Integer[]::new); // Integer[]

List<Integer> list = Arrays.stream(source)
    .boxed()
    .toList(); // List<Integer>
```

The structures have distinct characteristics:

| Structure | Elements | Can contain `null`? | Is a generic collection? |
| --- | --- | --- | --- |
| `int[]` | `int` | No | No |
| `Integer[]` | `Integer` | Yes | Not a `Collection` |
| `List<Integer>` | `Integer` | Depends on implementation/factory | Yes |

Special note: `Stream.of(source)` when `source` has type `int[]` creates a stream containing **one element which is the `int[]` array itself** (of type `Stream<int[]>`), not the sequence of numbers inside the array. To traverse each number, use `Arrays.stream(source)` or `IntStream.of(source)`.

### 9.2. How is the generic type `U` inferred?

With `mapToObj`, `U` comes from the expression inside the mapper:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<String> names = IntStream.of(1, 2, 3)
    .mapToObj(n -> "Item-" + n);

Stream<Integer> boxedEquivalent = IntStream.of(1, 2, 3)
    .mapToObj(Integer::valueOf);
```

The second example yields the same `Stream<Integer>` type as `boxed()`, yet `boxed()` is clearer when the only goal is wrapping primitives.

Sometimes an explicit type witness is needed to keep the compiler from inferring an overly broad type:

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<Number> numericObjects = IntStream.of(1, 2, 3)
    .<Number>mapToObj(Integer::valueOf);
```

`<Number>mapToObj` specifies `U` as `Number`; the mapper returns `Integer`, which is a valid subtype. Choosing overly broad types like `Object` everywhere discards type information and makes results harder to use. Keep concrete types until polymorphism is genuinely needed.

### 9.3. `mapToObj` does not flatten automatically

If a mapper returns a `List<String>`, the result is `Stream<List<String>>`, because each element still yields **one List object**. When you need to flatten inner elements:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> flattened = IntStream.rangeClosed(1, 2)
    .mapToObj(n -> List.of("A" + n, "B" + n))
    .flatMap(List::stream)
    .toList();

System.out.println(flattened); // [A1, B1, A2, B2]
```

`flatMap` is a separate step on the object stream to flatten the structure; `mapToObj` only specifies how to map each primitive to an object.

## 10. Laziness, side effects, and stream lifecycle

Both `boxed()` and `mapToObj` are **lazy** intermediate operations. The mapper is evaluated only when a terminal operation requests elements, and the number of times the mapper executes should not be relied upon as a business contract.

```java
import java.util.List;
import java.util.stream.IntStream;

var pipeline = IntStream.range(1, 5)
    .mapToObj(n -> "ID-" + n);

List<String> ids = pipeline.toList();
System.out.println(ids); // [ID-1, ID-2, ID-3, ID-4]
```

An example that should not rely on side effects:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

AtomicInteger calls = new AtomicInteger();

long count = IntStream.range(0, 10)
    .mapToObj(n -> {
        calls.incrementAndGet();
        return "Value-" + n;
    })
    .count();

System.out.println(count); // 10
// Do not rely on calls.get() definitely equaling 10.
```

With a sized source like `IntStream.range`, Stream optimizations may determine `count()` without executing the mapper. Thus, if you need to record the actual number of processed records, tie the count to the business result or a properly designed observation mechanism.

Mappers should be **non-interfering** and **stateless**: do not modify the source data being traversed, and do not depend on shared counters or mutable collections. Example:

```java
// Mapper that can be tested independently:
record Code(int value, String label) {}

static Code toCode(int value) {
    return new Code(value, "C-" + value);
}

// Inside another method:
// List<Code> codes = IntStream.range(0, 3)
//     .mapToObj(YourClass::toCode)
//     .toList();
```

`boxed()` or `mapToObj` do not open resources themselves. However, a primitive stream can originate from I/O or a closeable source; when the source holds resources, close the stream according to the source's contract (typically via `try-with-resources`). Do not reuse a stream already consumed by a terminal operation; create a new pipeline from a re-traversable source.

## 11. Performance: box when needed, not prematurely

Primitive streams are often helpful for heavy numeric workloads because they avoid wrapper overhead across multiple steps. When `boxed()` is used, each number is represented as a wrapper in the object stream segment; this can increase allocation pressure, memory usage, and garbage collection, though the JVM may optimize or cache certain wrappers.

Comparing three ways to compute a sum:

```java
import java.util.stream.IntStream;

long primitiveSum = IntStream.rangeClosed(1, 1_000_000)
    .asLongStream()
    .sum();

long boxedSum = IntStream.rangeClosed(1, 1_000_000)
    .boxed()
    .mapToLong(Integer::longValue)
    .sum();

long mappedSum = IntStream.rangeClosed(1, 1_000_000)
    .mapToLong(n -> n)
    .sum();

System.out.println(primitiveSum); // 500000500000
System.out.println(boxedSum);     // 500000500000
System.out.println(mappedSum);    // 500000500000
```

All three produce the same result on this dataset. `asLongStream` and `mapToLong` keep primitive types throughout the summation, express intent more clearly, and can avoid boxing/unboxing steps. `boxedSum` illustrates an unnecessary object conversion step.

**Overflow note:** the sum from 1 to 1,000,000 exceeds `int` range, so the example widens to `long` **before** summing. `IntStream.sum()` returns `int` and would overflow; calling `boxed()` does not fix that.

### 11.1. Measuring performance properly

Do not conclude `mapToObj` is always faster than `boxed().map(...)` or vice versa from code structure alone. Efficiency also depends on:

- Element count and output object creation cost.
- Degree of JIT optimization, mapper shape, and allocation elimination.
- Whether a terminal operation allows intermediate steps to be elided.
- Ordered sources, `sorted`/`distinct`/`limit` costs, collectors, and GC.
- Sequential vs. `parallel()` mode; splitting and combining overhead.

For realistic evaluation, use a warmed-up, controlled benchmark (e.g., JMH in a dedicated optimization workflow). A single `System.nanoTime()` timing run easily misleads due to JIT, GC, and system noise. In this lesson, the rule is **keep primitives while doing numeric math, and switch to objects at the point object data is needed**.

### 11.2. Parallel streams

`IntStream.range(...).parallel().mapToObj(...)` is valid if the mapper uses no shared mutable state and the source supports safe traversal. Yet parallel streams are not automatically faster:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> codes = IntStream.range(0, 1_000)
    .parallel()
    .mapToObj(i -> "C-" + i)
    .toList();

System.out.println(codes.get(0)); // C-0
```

Because `IntStream.range` has an encounter order, `toList()` preserves that order in the output even though element processing times may vary. Never treat lambda execution order as proof of encounter order.

## 12. Specific pitfalls when converting to object streams

| Pitfall | Why it is wrong or hard to maintain | Fix |
| --- | --- | --- |
| Calling `.toList()` directly on `IntStream` | `IntStream` lacks this API | `.boxed().toList()` or `.toArray()` if `int[]` is needed |
| Using `Stream.of(intArray)` to iterate numbers | Creates `Stream<int[]>` with a single array element | `Arrays.stream(intArray)` |
| Using `boxed()` to convert to `Stream<String>` | `boxed()` returns wrappers, not formatted strings | `mapToObj(n -> "...")` |
| Boxing numbers then immediately unboxing to `sum()` | Adds unnecessary conversion steps | Stay on `IntStream`/`LongStream` |
| Treating `Integer` as if never `null` | Object streams can contain null | Define a null policy before unboxing |
| Comparing wrappers with `==` | May compare object references | `equals` or primitive comparison |
| Assuming `toList()` is always modifiable | `Stream.toList()` is unmodifiable | Use a collector creating a mutable collection when needed |
| Expecting `mapToObj` to emit multiple results per element | Each primitive maps to one object value | Use `flatMap`/`mapMulti` for 0–n problems |
| Treating `mapToObj` as a terminal operation | It is still a lazy step | Use `toList`, `collect`, `count`, etc. to consume |
| Using `int` for a sum that may exceed `Integer.MAX_VALUE` | `IntStream.sum()` can overflow | Widen to `long` before summing or use a more precise type |

### 12.1. Null data and mapper results

`IntStream`, `LongStream`, and `DoubleStream` **cannot contain null**. However, a `mapToObj` mapper can return `null` because the output is an object:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

List<String> nonNullLabels = IntStream.rangeClosed(1, 4)
    .mapToObj(n -> n % 2 == 0 ? null : "N-" + n)
    .filter(Objects::nonNull)
    .toList();

System.out.println(nonNullLabels); // [N-1, N-3]
```

This example merely illustrates the type boundary. If “no label” is a valid state, the mapper can produce `Optional<String>` followed by `flatMap(Optional::stream)`; if a missing label is a business error, throw an explicit error during validation.

### 12.2. `DoubleStream` and special values

`double` supports `NaN`, `Infinity`, `-Infinity`, and distinguishes `0.0` from `-0.0` at the bit level. `DoubleStream.boxed()` preserves numeric values as `Double` without removing these values:

```java
import java.util.List;
import java.util.stream.DoubleStream;

List<Double> values = DoubleStream.of(
    0.0, -0.0, Double.NaN, Double.POSITIVE_INFINITY
).boxed().toList();

System.out.println(values);
// [0.0, -0.0, NaN, Infinity]
```

When using boxed `Double` as a `Map` key or `Set` element, check the rules of `Double.equals` and `hashCode`: `NaN` equals `NaN` on the wrapper; `0.0` and `-0.0` are not `equals`. These rules differ from the mathematical semantics of primitive `==`. If the data requires finite values, check `Double.isFinite(value)` before building DTOs or invoking collectors.

## 13. Testing converted values

With JUnit 5 and JDK 17+, you can directly test the output of both methods:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import org.junit.jupiter.api.Test;

class PrimitiveObjectConversionTest {

    @Test
    void boxedKeepsValuesAndOrder() {
        assertEquals(
            List.of(2, 3, 4),
            IntStream.rangeClosed(2, 4).boxed().toList()
        );
    }

    @Test
    void mapToObjBuildsLabels() {
        assertEquals(
            List.of("ID-1", "ID-2", "ID-3"),
            IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "ID-" + n)
                .toList()
        );
    }

    @Test
    void emptySourceProducesEmptyObjectStream() {
        assertEquals(
            List.of(),
            LongStream.empty().boxed().toList()
        );
    }

    @Test
    void primitiveAndBoxedArrayHaveDifferentTypes() {
        int[] primitive = IntStream.of(1, 2).toArray();
        Integer[] boxed = IntStream.of(1, 2)
            .boxed()
            .toArray(Integer[]::new);

        assertArrayEquals(new int[]{1, 2}, primitive);
        assertArrayEquals(new Integer[]{1, 2}, boxed);
    }

    @Test
    void arithmeticAfterMappingRemainsCorrect() {
        long sum = IntStream.rangeClosed(1, 100_000)
            .mapToLong(n -> n)
            .sum();

        assertEquals(5_000_050_000L, sum);
    }
}
```

Other useful tests include: single element, data with negative numbers, boundary values `Integer.MIN_VALUE`/`MAX_VALUE`, `Long.MAX_VALUE`, empty arrays, special `Double` values, a mapper returning `null`, and grouping by boxed values. Test **expected values and types**, without asserting how many times a lambda runs unless guaranteed by the API.

## 14. Practice exercises

**Exercise 1 — Wrappers and collections.** Create a `List<Long>` from the numbers `5, 6, 7, 8` using `LongStream.rangeClosed` and `boxed()`. Then create a modifiable `ArrayList<Long>` using `Collectors.toCollection`. Explain why `Stream.toList()` is unsuitable if you want to call `add()`.

**Exercise 2 — Mapping labels.** Use `IntStream.rangeClosed(1, 5)` and `mapToObj` to build a `List<String>` containing `"Chapter-1"` through `"Chapter-5"`. Write an alternative version using `boxed().map(...)` and identify the stream type at each step.

**Exercise 3 — Creating DTOs.** Define `record ProductId(long value, String label)`. Use `LongStream.of(101, 102, 103)` with `mapToObj` to create objects with labels `"PRD-101"`, `"PRD-102"`, `"PRD-103"`. From the resulting list, use `mapToLong(ProductId::value).sum()` to sum the IDs.

**Exercise 4 — Even/odd grouping.** From `IntStream.rangeClosed(1, 12)`, group into a `Map<String, List<Integer>>` with two keys `"even"` and `"odd"`. Explain why `boxed()` is needed before `Collectors.groupingBy`. If only the sum of even numbers is needed, write a pipeline that stays primitive.

**Exercise 5 — Distinguishing arrays.** From `int[] numbers = {2, 4, 6}`, create a new `int[]` and a `List<Integer>`. Compare the result of `Stream.of(numbers)` with `Arrays.stream(numbers)` via compile-time types.

**Exercise 6 — Large sum.** Compute the sum of numbers from `1` to `1_000_000`. Compare the return type of `IntStream.sum()` with `IntStream.asLongStream().sum()`, point out the overflow case, and write a unit test for the exact value `500000500000L`.

**Exercise 7 — State and optimization.** A developer creates `AtomicInteger counter = new AtomicInteger()` and writes `IntStream.range(0, 100).mapToObj(n -> { counter.incrementAndGet(); return n; }).count()`, expecting the counter to equal 100. Analyze why this expectation is not part of the Stream contract and rewrite it with a side-effect-free pipeline. If changed to a local `int counter` variable with `counter++` inside the lambda, the compiler also rejects it because captured variables must be `final` or *effectively final*.

## 15. Cheat sheet for pipeline design

| Task | Typical API choice | Output type |
| --- | --- | --- |
| Create wrapper objects from `int` | `IntStream.boxed()` | `Stream<Integer>` |
| Create wrapper objects from `long` | `LongStream.boxed()` | `Stream<Long>` |
| Create wrapper objects from `double` | `DoubleStream.boxed()` | `Stream<Double>` |
| Create labels/DTOs from `int` | `IntStream.mapToObj(IntFunction)` | `Stream<U>` |
| Create labels/DTOs from `long` | `LongStream.mapToObj(LongFunction)` | `Stream<U>` |
| Create labels/DTOs from `double` | `DoubleStream.mapToObj(DoubleFunction)` | `Stream<U>` |
| Collect into `List<Integer>` (JDK 16+) | `intStream.boxed().toList()` | `List<Integer>` |
| Use `Collectors.groupingBy` on numbers | `intStream.boxed().collect(...)` | `Map<K, V>` |
| Obtain `int[]` | `intStream.toArray()` | `int[]` |
| Sum `int` values that may exceed `int` range | `intStream.asLongStream().sum()` | `long` |
| Sum a `long` field on DTOs | `stream.mapToLong(Dto::amount).sum()` | `long` |
| Turn numbers into objects then flatten collections | `mapToObj(...).flatMap(...)` | `Stream<R>` |

`boxed()` and `mapToObj()` bridge primitive numeric processing and the object type system of the Java Stream API. Choose `boxed()` when only wrappers are needed, choose `mapToObj()` when constructing a new object value, and stay on primitive streams while numeric computations do not yet require collections or DTOs. This decision process keeps `JAVA_STREAM_API` pipelines readable, testable, and controlled in boxing cost, state, and performance before expanding to `filter`, `reduce`, `collect`, grouping, or parallel processing.
