# Designing Pure Functions and Testable Mapping Functions

## 1. Why Should Mapping Functions Be Easy to Test?

In the Java Stream API, a pipeline typically takes the form **data source → intermediate operations → terminal operation**. For example, `filter` selects orders, `map` transforms orders into display data, and `reduce` or `collect` aggregates results. Intermediate operations are mostly executed **lazily**: Java only evaluates them when a terminal operation needs data.

That sets an important requirement: the function passed to `map` must behave predictably even when Java invokes it at an unexpected time, skips some invocations due to optimizations, or splits work across multiple threads. A **pure function** is an appropriate design choice: given the same inputs, it returns the same result and produces no externally observable side effects.

Lesson objectives:

- Distinguish pure functions, stateful functions, and functions with side effects in Java.
- Design `T → R` mappings as small methods with clear input/output contracts.
- Turn dependencies like time, tax rates, and configuration into explicit inputs.
- Combine `Function`, `map`, `mapToLong`, and `flatMap` without sacrificing testability.
- Unit-test each function directly with JUnit 5, then test integration within a pipeline.
- Recognize limits regarding mutable data, errors, ordering, parallel execution, and performance.

## 2. Understanding "Pure" Precisely in Java

A pure function must satisfy two core conditions:

1. **Output depends solely on inputs**: given the same data and passed-in context, the function always returns a result with the same value.
2. **No observable side effects**: the function does not mutate external state, modify input objects, write files, send network requests, update databases, emit logging as business behavior, or alter shared counters.

Example:

```java
static int square(int value) {
    return value * value;
}

static String normalizeRegion(String region) {
    return region.strip().toUpperCase(java.util.Locale.ROOT);
}
```

`square(4)` always yields `16`. `normalizeRegion(" hn ")` always yields `"HN"` because the locale is fixed to `Locale.ROOT`. Both functions produce results from their inputs without mutating external state.

By contrast:

```java
static int counter = 0;

static int nextSequence(int value) {
    return value + ++counter;
}

static String normalizeUsingCurrentLocale(String value) {
    return value.toUpperCase(); // Depends on the environment's default locale.
}
```

`nextSequence(4)` returns different results across calls. `normalizeUsingCurrentLocale` can produce different results if the default locale changes. To make behavior explicit and testable, pass `Locale` into the function or choose `Locale.ROOT` when business logic requires locale-independent normalization.

**Distinguishing commonly confused properties:**

| Property | Meaning | Equivalent to a pure function? |
| --- | --- | --- |
| Deterministic | Same inputs produce same output in a defined context | Not enough: the function might still log or increment counters |
| Stateless | Does not depend on mutable state across invocations | Not enough: the function might still mutate input data |
| Non-interfering | Does not interfere with the data source being traversed by the Stream | An essential Stream requirement, yet does not cover all side effects |
| Thread-safe | Can be called concurrently without corrupting state | Not enough: `AtomicInteger.incrementAndGet()` is thread-safe yet mutates state |
| Pure | Output depends on inputs, no observable side effects | Satisfies both determinism and absence of side effects |

A function may use **local variables**, allocate new objects, or use local buffers and still remain pure, as long as they do not leak mutable state or mutate external data. Purity concerns **observable behavior**, not an absolute ban on memory allocation.

Also, **idempotent** differs from **pure**: `f(f(x)) == f(x)` defines idempotence, whereas purity concerns determinism and side effects. `square` is pure but not idempotent because `square(square(2)) == 16` differs from `square(2) == 4`.

## 3. Reading Signatures Before Writing a Mapper

The fundamental method on `Stream<T>` has the signature:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

- `T`: the input element type of the current stream.
- `R`: the output element type after mapping.
- `Function<T,R>`: represents a transformation from one value of type `T` to one value of type `R`.
- `? super T` and `? extends R`: allow compatible supertypes/subtypes when passing functions.
- `Stream<R>`: the result is a new stream, not yet automatically executing the pipeline.

`map` is a **one-element-to-one-result** transformation whenever the mapper is evaluated. If you want to drop elements, normally use `filter`; if one element can produce zero, one, or many results, consider `flatMap` or `mapMulti`. Do not use `null` to implicitly mean "drop element" when you can express the policy more explicitly.

Common functional interfaces in the **Behavioral Functions and Types** chapter:

| Interface | Function shape | Common usage in Streams |
| --- | --- | --- |
| `Function<T,R>` | `T → R` | `map`, converting records into DTOs |
| `UnaryOperator<T>` | `T → T` | Same-type normalization |
| `Predicate<T>` | `T → boolean` | `filter`, `anyMatch` |
| `ToIntFunction<T>` / `ToLongFunction<T>` | `T → int/long` | `mapToInt`, `mapToLong` |
| `BinaryOperator<T>` | `(T,T) → T` | `reduce` with same-type combining |
| `BiFunction<T,U,R>` | `(T,U) → R` | Expressing mappings that require two inputs |
| `Consumer<T>` | `T → void` | `forEach`; often contains side effects |
| `Supplier<T>` | `() → T` | Supplying values/accumulators on demand |

Do not assume every `Consumer` or `Supplier` is impure: evaluate the implementation. However, mappers transforming input data to output values are usually easier to keep pure than functions primarily meant for I/O.

## 4. A Business Mapper with a Clear Contract

Suppose incoming sales data contains order ID, region, quantity, and unit price. The system wants to produce a display object with normalized region and computed total amount. We design the mapping:

```text
RawOrder(id, region, quantity, unitPrice)
              │
              ▼
      OrderMapper.toView
              │
              ▼
OrderView(id, normalizedRegion, amount)
```

The complete code below runs on **JDK 17 or later** (using `record` and `Stream.toList()`):

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class OrderMapper {

    public record RawOrder(
        String id,
        String region,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record OrderView(
        String id,
        String region,
        BigDecimal amount
    ) {}

    public static OrderView toView(RawOrder raw) {
        Objects.requireNonNull(raw, "raw");

        if (raw.id() == null || raw.id().isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (raw.region() == null || raw.region().isBlank()) {
            throw new IllegalArgumentException("region must not be blank");
        }
        Objects.requireNonNull(raw.unitPrice(), "unitPrice");
        if (raw.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (raw.unitPrice().signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }

        String normalizedRegion = raw.region()
            .strip()
            .toUpperCase(Locale.ROOT);
        BigDecimal amount = raw.unitPrice()
            .multiply(BigDecimal.valueOf(raw.quantity()));

        return new OrderView(
            raw.id().strip(),
            normalizedRegion,
            amount
        );
    }

    public static void main(String[] args) {
        List<RawOrder> rows = List.of(
            new RawOrder("O-1", " hn ", 2, new BigDecimal("100.00")),
            new RawOrder("O-2", "HN", 1, new BigDecimal("50.00")),
            new RawOrder("O-3", "hcm", 3, new BigDecimal("20.00"))
        );

        List<OrderView> views = rows.stream()
            .map(OrderMapper::toView)
            .toList();

        Map<String, BigDecimal> revenueByRegion = views.stream()
            .collect(Collectors.groupingBy(
                OrderView::region,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    OrderView::amount,
                    BigDecimal::add
                )
            ));

        System.out.println(views.get(0));
        // OrderView[id=O-1, region=HN, amount=200.00]
        System.out.println(revenueByRegion.get("HN"));  // 250.00
        System.out.println(revenueByRegion.get("HCM")); // 60.00
    }
}
```

**Why is `toView` easy to test?**

1. **Single input:** `RawOrder`, without accessing a database, clock, or global variables.
2. **Strongly typed output:** `OrderView`, rather than returning ambiguous structures like `Object[]` or `Map<String,Object>`.
3. **Does not mutate input:** creates a new `OrderView` without writing to `RawOrder`.
4. **Consistent normalization:** `strip()` and `Locale.ROOT` produce outputs independent of the default locale.
5. **Explicit data rules:** non-positive quantity, negative price, and blank ID/region are intentionally rejected.
6. **Callable standalone:** no `Stream` is needed to test `toView`.

In this example, both `String` and `BigDecimal` are *immutable*, so the components held inside both records are safe against mutation. However, **`record` is only shallowly immutable at the field-reference level**: if a field is a `List` or mutable object, perform defensive copying on construction and exposure if true immutability is required.

`BigDecimal` is more suitable than `double` for monetary calculations to avoid binary representation errors. The calculation `quantity × unitPrice` here performs no rounding; if business rules require tax or discounts, specify **when and how rounding occurs**. Per-line rounding can differ from rounding on the total.

## 5. Extracting Business Functions from Pipelines

Writing the entire formula inline inside `map` can make code brief, yet harder to name, reuse, and test:

```java
// Hard to unit-test independently as the expression grows more complex.
List<OrderMapper.OrderView> views = rows.stream()
    .map(row -> new OrderMapper.OrderView(
        row.id().strip(),
        row.region().strip().toUpperCase(Locale.ROOT),
        row.unitPrice().multiply(BigDecimal.valueOf(row.quantity()))
    ))
    .toList();
```

This lambda also **skips the data validation** in `toView`. As business logic evolves, logic scattered across multiple pipelines easily drifts out of sync. A clearer way:

```java
List<OrderMapper.OrderView> views = rows.stream()
    .map(OrderMapper::toView)
    .toList();
```

The pure method handles transformation; the pipeline is responsible for **selecting sources, filtering, grouping, and collecting results**. A mapper with an intent-revealing name helps readers see what type data is transforming from and to without dissecting a long lambda.

### 5.1. Composing Pure Steps with `Function`

`Function` has `compose`, `andThen`, and `identity`:

```java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> strip = String::strip;
Function<String, String> uppercase = s -> s.toUpperCase(Locale.ROOT);

Function<String, String> normalize = strip.andThen(uppercase);
Function<String, String> alsoNormalize = uppercase.compose(strip);

System.out.println(normalize.apply(" hn "));     // HN
System.out.println(alsoNormalize.apply(" hn ")); // HN
System.out.println(Function.<String>identity().apply("A")); // A
```

With `f.andThen(g)`, Java performs `g(f(x))`; with `g.compose(f)`, it is also `g(f(x))`. When the component functions are pure, their composition remains pure while keeping each transformation easy to unit-test.

Not every composition is commutative: `strip.andThen(uppercase)` may work either way, yet swapping two other processing steps can alter the result. Test against the **business contract** rather than assuming order is arbitrary.

### 5.2. Choosing the Right Mapping Operation

| Need | Operation | Example |
| --- | --- | --- |
| Each order → one DTO | `map` | `.map(OrderMapper::toView)` |
| Each order → one `long` value | `mapToLong` | `.mapToLong(OrderMapper.RawOrder::quantity)` |
| Each group holds multiple elements → flat sequence | `flatMap` | `.flatMap(List::stream)` |
| Each element may emit 0–n results via `Consumer` | `mapMulti` (JDK 16+) | Useful when avoiding creating a sub-stream per element |
| Keep only records matching a rule | `filter` | `.filter(row -> row.quantity() > 0)` |

Example distinguishing `map` and `flatMap`:

```java
List<List<String>> groups = List.of(
    List.of("A", "B"),
    List.of("C")
);

List<Integer> groupSizes = groups.stream()
    .map(List::size)
    .toList(); // [2, 1]

List<String> members = groups.stream()
    .flatMap(List::stream)
    .toList(); // [A, B, C]
```

## 6. Making Varying Dependencies Explicit Parameters

A mapper should not look up exchange rates, the current clock, or tax rates on its own while traversing data:

```java
// Design depends on external state; hard to produce deterministic results in tests.
// .map(order -> convert(order, rateService.currentRate()))
```

If business rules allow using **a tax rate snapshotted at the start of processing**, read the tax rate at the I/O boundary first, then pass the fixed value into the function:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

static BigDecimal priceWithTax(
    BigDecimal amount,
    BigDecimal taxRate
) {
    if (amount == null || taxRate == null) {
        throw new IllegalArgumentException("amount/taxRate must not be null");
    }
    if (amount.signum() < 0 || taxRate.signum() < 0) {
        throw new IllegalArgumentException("values must not be negative");
    }
    return amount
        .multiply(BigDecimal.ONE.add(taxRate))
        .setScale(2, RoundingMode.HALF_UP);
}

BigDecimal fixedTaxRate = new BigDecimal("0.08");
List<BigDecimal> amountsWithTax = rows.stream()
    .map(OrderMapper::toView)
    .map(view -> priceWithTax(view.amount(), fixedTaxRate))
    .toList();
```

The snippet above illustrates the `priceWithTax` method placed inside an appropriate enclosing class/method using `rows` from the previous example. `BigDecimal` is immutable; `fixedTaxRate` does not change within the pipeline, so the mapper does not depend on time-varying values. To support different tax types, exchange rates, or rounding modes, add parameters or an **immutable configuration value object**, and test each case.

For time, pass `Instant`, `LocalDate`, or `Clock` intentionally. If you accept `Clock` and call `instant()` inside the mapper, results still depend on invocation timing; to map purely with "processing timestamp", capture a single fixed `Instant` before constructing the pipeline and pass it directly into the mapper. Similarly, if output depends on time zone, pass `ZoneId` instead of silently relying on the default time zone.

**Distinguishing safe capture from risky capture:**

```java
String prefix = "ORDER-"; // Immutable String, fixed value.
List<String> ids = List.of("1", "2").stream()
    .map(id -> prefix + id)
    .toList(); // [ORDER-1, ORDER-2]
```

A variable captured by a lambda must be `final` or *effectively final*; this **does not guarantee that the object referenced by the variable is immutable**. For example, `final List<String> shared` can still be modified via `shared.add(...)`. Ensure both **the captured reference and its contents** are stable if you need a pure function.

## 7. Common Anti-Patterns

### 7.1. Mutating an Output List Inside a Mapper

```java
import java.util.ArrayList;
import java.util.List;

List<String> sharedResults = new ArrayList<>();
List<String> names = List.of("An", "Bình", "Chi");

// Avoid this approach:
names.stream()
    .map(name -> {
        sharedResults.add(name.toUpperCase());
        return name;
    })
    .toList();

// Use mapping to produce the result:
List<String> uppercaseNames = names.stream()
    .map(name -> name.toUpperCase(java.util.Locale.ROOT))
    .toList();
```

`sharedResults` is mutated from inside the lambda; switching to `parallelStream()` makes `ArrayList` unsafe for concurrent writes. Even with a concurrent collection, the function still has side effects and is difficult to unit-test standalone. Let `map` return values, and let terminal operations like `toList` or `collect` assemble the results.

### 7.2. Relying on How Many Times the Mapper Is Called

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();
long count = List.of("a", "b", "c").stream()
    .map(value -> {
        calls.incrementAndGet();
        return value.toUpperCase();
    })
    .count();

System.out.println(count); // 3
// Do not assert calls == 3; map may be skipped
// if count() can determine the size directly from the source.
```

Streams are permitted to optimize away intermediate steps when doing so does not affect the guaranteed result. `AtomicInteger` makes counter updates thread-safe, yet does not make the mapper pure. Therefore, test **return values**, not `map` invocation counts as a mandatory contract.

### 7.3. Mutating Source Elements

```java
class MutableOrder {
    String region;
    MutableOrder(String region) { this.region = region; }
}

List<MutableOrder> source = new ArrayList<>();
source.add(new MutableOrder(" hn "));

// Avoid: mutating source objects right inside the mapping step.
List<MutableOrder> changed = source.stream()
    .map(order -> {
        order.region = order.region.strip();
        return order;
    })
    .toList();
```

Returning the exact same `order` reference after mutation gives the mapping step side effects on external data. Even though mutating a field does not always alter the **structure** of the collection, it makes the mapper impure and can affect other operations reading the shared object. Construct a new result object with normalized data instead.

### 7.4. Calling I/O from a Mapper

```java
// Anti-pattern example: each element triggers a remote query.
// .map(order -> remotePriceService.lookupPrice(order.id()))
```

This kind of mapper has network-dependent latency, can fail, causes N+1 requests, and yields results that vary depending on when it runs. When external data is needed, prefer fetching and handling errors at the I/O layer, building an explicit data snapshot, and then purely mapping from the snapshot to the result. Not every query can be batched ahead of time; when it cannot, treat the I/O step as an explicit operation with retry, timeout, and error-observability policies rather than disguising it as a pure transformation.

## 8. Designing Error Contracts and Missing Data Handling

A testable mapping function needs to specify **valid inputs**, `null` handling, out-of-range values, and failure behavior.

There are three common approaches:

| Policy | When to use | What to test |
| --- | --- | --- |
| Fail fast with exceptions | Invalid data makes business results untrustworthy | Exception type, trigger conditions, no silent wrong results |
| Return `Optional<R>` | "No result" is an intentional, valid state | Presence/absence of result, record-dropping policy |
| Return a result type with success/failure | Need to collect structured errors instead of aborting everything | Success values, error codes, causes, and processing order |

`toView` above chooses **fail fast** for invalid quantities, negative prices, and blank required fields. Do not turn every exception into `Optional.empty()` and silently drop records, as that could cause revenue to be miscalculated without anyone noticing. If the business requirement truly is "drop records missing optional data", you can use:

```java
import java.util.List;
import java.util.Optional;

static Optional<String> normalizedOptionalRegion(String region) {
    if (region == null || region.isBlank()) {
        return Optional.empty();
    }
    return Optional.of(region.strip().toUpperCase(java.util.Locale.ROOT));
}

List<String> validRegions = List.of(" hn ", " ", "hcm").stream()
    .map(region -> normalizedOptionalRegion(region))
    .flatMap(Optional::stream)
    .toList(); // [HN, HCM]
```

Here, the "drop blank regions" policy is stated explicitly. `Optional::stream` has been available since JDK 9. If you want to retain failure reasons per row, a structured result type is a clearer choice than `Optional`.

Note that `List.of(...)` **does not accept `null` elements**; the example above contains a blank string, not `null`. A `Stream` can be built from sources containing `null`, so if real data can miss values, test that case at the ingestion boundary.

## 9. Testing Functions First, Pipelines Second

With pure functions, unit tests need minimal setup: construct inputs, call the function directly, and compare output values. No database or HTTP mocks are needed to test region normalization and amount calculation.

JUnit 5 example; assume the `OrderMapper` class from section 4 is in the same package as the test class:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderMapperTest {

    @Test
    void normalizesRegionAndComputesAmount() {
        var input = new OrderMapper.RawOrder(
            " O-1 ", " hn ", 2, new BigDecimal("100.00")
        );

        var actual = OrderMapper.toView(input);

        assertEquals(
            new OrderMapper.OrderView(
                "O-1", "HN", new BigDecimal("200.00")
            ),
            actual
        );
        assertEquals(" hn ", input.region()); // Does not mutate source.
        assertEquals(" O-1 ", input.id());
    }

    @Test
    void sameInputHasSameValue() {
        var input = new OrderMapper.RawOrder(
            "O-2", "hcm", 3, new BigDecimal("20.00")
        );

        assertEquals(OrderMapper.toView(input), OrderMapper.toView(input));
    }

    @Test
    void rejectsInvalidQuantityAndRegion() {
        var invalidQuantity = new OrderMapper.RawOrder(
            "O-3", "HN", 0, new BigDecimal("10.00")
        );
        var blankRegion = new OrderMapper.RawOrder(
            "O-4", " ", 1, new BigDecimal("10.00")
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderMapper.toView(invalidQuantity)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderMapper.toView(blankRegion)
        );
    }

    @Test
    void worksInsideStreamPipeline() {
        List<OrderMapper.RawOrder> input = List.of(
            new OrderMapper.RawOrder(
                "O-1", " hn ", 2, new BigDecimal("100.00")
            ),
            new OrderMapper.RawOrder(
                "O-2", "hcm", 1, new BigDecimal("20.00")
            )
        );

        List<OrderMapper.OrderView> actual = input.stream()
            .map(OrderMapper::toView)
            .toList();

        assertEquals(
            List.of(
                new OrderMapper.OrderView(
                    "O-1", "HN", new BigDecimal("200.00")
                ),
                new OrderMapper.OrderView(
                    "O-2", "HCM", new BigDecimal("20.00")
                )
            ),
            actual
        );
    }
}
```

### 9.1. Valuable Test Matrix

| Test group | Sample data | Expected |
| --- | --- | --- |
| Happy path | `" hn "`, quantity `2`, price `100.00` | `HN` and `200.00` |
| Normalization | `"hcm"`, `" Hn "` | Consistent region output |
| Domain boundaries | Quantity `0` or negative | Exception per contract |
| Invalid values | Negative price, blank ID/region, `null` price | Explicit error |
| Immutability | Keep `RawOrder` reference before/after | No input field modified |
| Determinism | Call same mapper twice | Equal result values |
| Pipeline | Multiple orders, empty source, combined with `filter`/`collect` | Correct list or aggregation |
| Monetary contract | Decimals, rounding rules | Results match agreed precision and scale |

When testing `BigDecimal`, `equals` also compares **scale**: `new BigDecimal("2.0")` and `new BigDecimal("2.00")` have equal numeric value yet are not `equals`. Use `compareTo` if the requirement only compares numeric magnitude; use `equals` if scale is part of the contract. Avoid switching comparison strategies arbitrarily across tests.

### 9.2. Property-Based Testing Mindset

Beyond concrete examples, identify **invariants**:

- Valid input with `quantity > 0` and `unitPrice >= 0` always yields non-negative `amount`.
- `toView` never modifies the input `RawOrder`.
- The same input returns the same `OrderView`, regardless of how many other elements are in the pipeline.
- For the same region and non-negative prices, the sum of two rows equals the sum of their respective `amount` values (unless a per-row rounding policy alters the total).
- Traversal order does not affect `BigDecimal` addition; by contrast, string concatenation can depend on order.

These properties can be tested across many datasets, including with property-based testing tools if the project uses them. Do not write tests asserting lambda call counts or execution order in `parallel()` when that is not part of the API contract.

## 10. How Does Purity Help Parallel Streams and Advanced APIs?

### 10.1. Parallel Is Not Automatically Faster

```java
List<OrderMapper.OrderView> views = rows.parallelStream()
    .map(OrderMapper::toView)
    .toList();
```

`OrderMapper.toView` holds no shared state, so it is behaviorally suited to concurrent calls from multiple threads. However, `parallelStream()` does not guarantee speedup: small sources, splitting overhead, result synchronization, ordered operations, and object allocation can make it slower. Benchmark on realistic data volumes. For a `List` source with encounter order, `toList()` still preserves encounter order in the output, even though individual elements are processed at different times.

**Pure functions only solve part of the parallel-safety puzzle.** The data source must still not be mutated concurrently against contract; collectors must also have proper accumulators and combiners. Operations like `sorted`, `distinct`, `limit`, and `findFirst` can increase cost in parallel streams or require preserving order.

### 10.2. `reduce`, `collect`, and Merging

`map` turns each element into a new result; `reduce` aggregates results using a suitable operation. The combiner in `reduce` must be *associative*, use an appropriate identity, and avoid mutating a shared accumulator:

```java
BigDecimal total = rows.stream()
    .map(OrderMapper::toView)
    .map(OrderMapper.OrderView::amount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal::add` creates a new result object and is mathematically associative for exact decimal addition. `Collectors.groupingBy(...)` in the main example may use mutable accumulators **internally managed by the collector**; that does not give `toView` side effects. For **custom collectors**, carefully examine `supplier`, `accumulator`, `combiner`, `finisher`, as well as `Collector.Characteristics` before using them in parallel pipelines.

### 10.3. `Spliterator`, State, and Stream Gatherers

`Spliterator` controls how a source is traversed and split; characteristics such as `ORDERED`, `SIZED`, `IMMUTABLE`, or `CONCURRENT` affect optimization opportunities and safety. Immutability in a mapper cannot substitute for the source/spliterator contract.

**Stream Gatherers**, standardized in **JDK 24**, provide intermediate transformations that can **intentionally hold state**, such as windowing via `Gatherers.windowFixed(...)`. When using `gather`, separate pure element-mapping logic from the gatherer's windowing or accumulation state management. `Gatherer` requirements for initializer, integrator, combiner, and finisher must be verified separately; code using `gather` will not compile on JDK 17/21.

## 11. Process for Designing a Testable Mapper

When given a new mapping problem, follow these steps:

1. **Lock down the type contract:** determine `T` and `R`; should the output be a new value object/DTO?
2. **List required data:** primary input, configuration, locale, processing date, exchange rate, rounding policy.
3. **Externalize varying dependencies:** read I/O, timestamps, and mutable data at boundaries, passing appropriate snapshots into the mapping function.
4. **Define valid data and errors:** `null`, blank strings, value ranges, exceptions vs. explicit result types.
5. **Write small business-named functions:** compute and construct outputs only; never mutate sources or shared state.
6. **Test directly:** happy paths, boundaries, errors, immutability, determinism, numeric rules.
7. **Plug into the Stream:** use method references like `.map(OrderMapper::toView)`; use `filter`, `flatMap`, `reduce`, and `collect` with proper semantics.
8. **Review pipeline contracts:** is encounter order needed, is there a terminal operation, is there an I/O source to close, is there a reason to run in parallel?

### Practice Exercises

**Exercise 1.** Write a pure function `normalizeCode(String code)`: trim leading/trailing whitespace, convert to uppercase using `Locale.ROOT`, and reject blank strings. Write at least three tests: normal input, whitespace-only input, and `null`.

**Exercise 2.** Given `List<RawOrder>`, obtain a list of `OrderView` only for orders with `quantity >= 2`. Place `filter` before `map` so the quantity condition lives at the source-data layer; keep `toView` as an independent mapping function. Test an empty source and a case where no order qualifies.

**Exercise 3.** Add `discountRate` to a new function `discountedAmount(BigDecimal amount, BigDecimal rate)`. Explicitly define the valid range `0 ≤ rate ≤ 1` and rounding strategy. Write tests for `0`, `1`, an in-range value, and out-of-range values. Avoid reading the discount rate from a global configuration variable inside the function.

**Exercise 4.** A colleague suggests `orders.parallelStream().map(o -> { count++; return toView(o); }).toList()`. Identify the issues regarding shared state, race conditions, and why a mapper call counter is not part of the Stream contract. Rewrite it using a pure transformation, then use the terminal operation's result to count elements if genuinely needed.

A good mapper can be tested as an `input → output` operation without creating streams, mocking services, or relying on execution order. When combining pure mappers, Java Stream API pipelines retain the advantages of declarative data processing—easily extending to `filter`, `reduce`, `collect`, and grouping—while reducing risks around state, resources, and parallel execution.
