# Creating a ConcurrentMap with Collectors.toConcurrentMap

## 1. Why Do We Need a Collector That Returns a ConcurrentMap?

In **JAVA_STREAM_API**, we typically start from a data source, chain steps like `filter`, `map`, `flatMap`, and then use the terminal operation `collect` to gather the results. When mapping each element to a **key–value** pair and optionally merging elements with duplicate keys, `Collectors.toMap` is a familiar tool. However, for some parallel processing pipelines, we want a collector capable of **accumulating concurrently into a ConcurrentMap**.

`Collectors.toConcurrentMap` is the family of collectors built for that need. It:

- Converts elements `T` into key `K` and value `U` pairs.
- Collects the results into a `ConcurrentMap<K, U>`.
- Provides overloads to choose the **policy when keys collide**.
- Provides an overload to choose the **type of ConcurrentMap** via `mapFactory`.
- Is a collector with **`CONCURRENT` and `UNORDERED`** characteristics; it can leverage parallel processing when the Collector API conditions are met.

For example, consider an order-line ingestion system. Multiple lines may share the same product code (`sku`), and we only need the **total units per SKU**:

~~~text
Stream<OrderLine>
    │
    ├─ ("BOOK", 2)
    ├─ ("PEN",  3)
    ├─ ("BOOK", 1)
    └─ ("PAD",  4)
    │
    ▼
toConcurrentMap(
    OrderLine::sku,
    OrderLine::quantity,
    Integer::sum
)
    │
    ▼
ConcurrentMap<String, Integer>
    ├─ "BOOK" → 3
    ├─ "PEN"  → 3
    └─ "PAD"  → 4

Key iteration order is not guaranteed in the default collector.
~~~

**Key point to understand:** `ConcurrentMap` is a **result data type** with a concurrent operations protocol, whereas `CONCURRENT` is a **Collector characteristic**. The two concepts are related, but they do not mean that all code outside the pipeline or all objects placed inside the Map automatically become thread-safe.

This lesson belongs to the **Concurrent Collection** chapter of the Java Stream API, using Java 17+ examples and combining lazy pipeline semantics, Spliterator-splittable sources, merge contracts, state safety, and performance limits.

## 2. The Three Overloads of toConcurrentMap

Conceptual signatures in `java.util.stream.Collectors`:

~~~java
// 1. Keys are required to be unique.
static <T, K, U>
Collector<T, ?, ConcurrentMap<K, U>> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper
);

// 2. Includes a merge policy when keys collide.
static <T, K, U>
Collector<T, ?, ConcurrentMap<K, U>> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction
);

// 3. Includes a merge policy and a factory for creating the ConcurrentMap.
static <T, K, U, M extends ConcurrentMap<K, U>>
Collector<T, ?, M> toConcurrentMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
);
~~~

Comparison table:

| Component | Function | Example |
| --- | --- | --- |
| `keyMapper` | Converts each `T` into key `K` | `Item::sku` |
| `valueMapper` | Converts each `T` into value `U` | `Item::quantity` |
| `mergeFunction` | Merges two values `U` with the same key | `Integer::sum` |
| `mapFactory` | Supplies a new empty ConcurrentMap | `ConcurrentSkipListMap::new` |

The return value of all three overloads is a **Collector**, not a Map created immediately when the method is called. The Map is constructed when the terminal `collect(...)` executes.

**Key characteristics:**

- The **two-parameter** form rejects duplicate keys and throws `IllegalStateException` if a collision occurs.
- The **three-parameter** form allows duplicate keys, applying `mergeFunction`.
- The **four-parameter** form also allows choosing a specific Map type, but the factory must return a **`ConcurrentMap`** type, not a regular `HashMap` or `LinkedHashMap`.

`Collectors.toConcurrentMap` does not guarantee the exact Map class returned if no factory is passed. In common JDKs, the default Map is typically `ConcurrentHashMap`; **you should not rely on that implementation class as an API contract** if the application requires a specific class.

## 3. Example 1: Mapping Unique Keys with the Two-Parameter Overload

Suppose a list of users has unique identifiers, and we want to build a lookup table from id to name:

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class UsersToConcurrentMap {
    record User(String id, String name) {}

    public static void main(String[] args) {
        List<User> users = List.of(
            new User("U01", "An"),
            new User("U02", "Bình"),
            new User("U03", "Chi")
        );

        ConcurrentMap<String, String> nameById = users.parallelStream()
            .collect(Collectors.toConcurrentMap(
                User::id,
                User::name
            ));

        System.out.println(nameById.get("U01")); // An
        System.out.println(nameById.get("U03")); // Chi
        System.out.println(nameById.size());     // 3
    }
}
~~~

Explanation:

1. `users.parallelStream()` requests a pipeline that can be processed in parallel.
2. `keyMapper` is `User::id`, returning a `String` key.
3. `valueMapper` is `User::name`, returning a `String` value.
4. `collect` produces a `ConcurrentMap<String, String>`.

This is an appropriate case for the two-parameter overload **when identifiers are genuinely unique**.

### What If Keys Are Duplicated?

~~~java
import java.util.List;
import java.util.stream.Collectors;

record User(String id, String name) {}

List<User> duplicates = List.of(
    new User("U01", "An"),
    new User("U01", "An alternate version")
);

// Throws IllegalStateException because two elements have the same key "U01":
duplicates.stream().collect(
    Collectors.toConcurrentMap(User::id, User::name)
);
~~~

There is no default “take the last value” mechanism. Failing on duplicate keys is designed to prevent accidental data loss.

If duplicate keys represent **invalid data**, keep the two-parameter overload and handle the exception according to your data ingestion policy. If duplicate keys are **normal**, you must choose an explicit `mergeFunction`.

## 4. Example 2: Merging Duplicate-Key Rows with mergeFunction

One SKU can appear in many orders. The goal is the total quantity by SKU, not an arbitrary representative record.

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class SumUnitsBySku {
    record OrderLine(String orderId, String sku, long quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("O1", "BOOK", 2L),
            new OrderLine("O2", "PEN",  3L),
            new OrderLine("O3", "BOOK", 1L),
            new OrderLine("O4", "PAD",  4L)
        );

        ConcurrentMap<String, Long> unitsBySku = lines.parallelStream()
            .collect(Collectors.toConcurrentMap(
                OrderLine::sku,
                OrderLine::quantity,
                Long::sum
            ));

        System.out.println(unitsBySku.get("BOOK")); // 3
        System.out.println(unitsBySku.get("PEN"));  // 3
        System.out.println(unitsBySku.get("PAD"));  // 4
        System.out.println(unitsBySku.size());      // 3
    }
}
~~~

`Long::sum` takes two values for **the same key** and adds them. You can picture it as:

~~~text
BOOK -> 2
BOOK -> 1

merge(2, 1) -> 3

PEN -> 3
PAD -> 4
~~~

In a parallel stream, two values with the same key may come from different processing branches; **you must not assume the call order of `mergeFunction`**. For integer addition that does not care “which value came first”, the result is stable under Java arithmetic semantics if the input range fits.

**Limitation:** `Long::sum` can overflow `long`. If the result must be an overflow-free mathematical sum, constrain the value range or use an appropriate numeric type (such as `BigInteger`); do not treat `ConcurrentMap` as an automatic overflow detector.

### 4.1. BigDecimal Totals for Monetary Data

When monetary amounts require exact decimal precision and all values share the same currency, `BigDecimal::add` is typically a reasonable merge function:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class RevenueBySku {
    record Sale(String sku, BigDecimal amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("BOOK", new BigDecimal("19.90")),
            new Sale("PEN",  new BigDecimal("5.25")),
            new Sale("BOOK", new BigDecimal("10.10"))
        );

        ConcurrentMap<String, BigDecimal> revenue = sales.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Sale::sku,
                Sale::amount,
                BigDecimal::add
            ));

        System.out.println(revenue.get("BOOK")); // 30.00
        System.out.println(revenue.get("PEN"));  // 5.25
    }
}
~~~

`BigDecimal.add` does not round when no `MathContext` is passed. Even so, a financial report still needs policies for currency, scale, exchange rates, and null values; addition does not automatically know whether two amounts are in the same currency.

## 5. What Properties Must a Merge Function Satisfy?

`mergeFunction` is a part very easy to get wrong under concurrent execution. It must be **non-interfering with the source**, must not rely on shared mutable state, and must work properly as elements are combined in varying ways.

### 5.1. Associativity

For values `a`, `b`, and `c`:

~~~text
merge(merge(a, b), c) = merge(a, merge(b, c))
~~~

If this condition fails, different ways of merging branches can yield different results.

For example, **you should not use subtraction** to aggregate:

~~~java
// Unsuitable for parallel aggregation requiring a stable result:
ConcurrentMap<String, Integer> result = rows.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Row::key,
        Row::value,
        (left, right) -> left - right
    ));
~~~

In this snippet, `Row` and `rows` are an application-provided model and list. Subtraction is not associative: `(10 - 3) - 2` differs from `10 - (3 - 2)`.

### 5.2. Commutativity Helps Keep Results Order-Independent

Because `toConcurrentMap` is an **UNORDERED** collector, the order in which two values are passed to merge does not necessarily follow encounter order. If the same result is required **regardless of execution schedule**, choose a merge operation that is also commutative:

~~~text
merge(a, b) = merge(b, a)
~~~

Examples matching intent:

| Merge Operation | Associative? | Commutative? | Notes |
| --- | --- | --- | --- |
| `Long::sum` | Yes under Java `long` addition | Yes | Watch for overflow if an unbounded mathematical range is needed |
| `BigDecimal::add` without `MathContext` | Yes numerically | Yes numerically | Scale can affect `equals` or display |
| `Integer::max` | Yes | Yes | Takes the maximum value |
| String concatenation `left + right` | Yes by string grouping | **No** | Result order is nondeterministic when unordered |
| `(a,b) -> b` | Yes | **No** | “Last value” depends on execution schedule |
| Subtraction | **No** | No | Unsuitable for reductions needing stability |

**BigDecimal note:** In terms of *numerical value*, unrounded addition is associative and commutative. However, `BigDecimal.equals` also considers `scale`; if the business cares about exact representation/scale, normalize the data or choose an explicit policy instead of reasoning solely from mathematical value.

### 5.3. Does Not Mean It Must Always Be Commutative

The Collector API focuses on contract-compliant accumulation and combination. `toConcurrentMap` does not guarantee ordering; if a merge operation is order-sensitive, the program may still run, yet the result may no longer be **deterministic with respect to encounter order**. When the requirement is “keep the first record” or “concatenate text in source sequence”, choose an ordered collector or define order using a business key rather than expecting `toConcurrentMap` to preserve order.

## 6. Distinguishing “Latest Record” from “Last to Arrive”

A common mistake is using:

~~~java
// Does not guarantee selecting the latest record by business logic:
(left, right) -> right
~~~

On a parallel stream, `right` is merely the second argument of **one merge call**, not necessarily the element with the largest timestamp or the latest position in the source.

It is better to select the record using a **version/time field**, with a clear enough tie-breaker rule:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

public class LatestEvents {
    record Event(String key, long version, String payload) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("BOOK", 10, "old"),
            new Event("PEN",  12, "blue"),
            new Event("BOOK", 15, "new"),
            new Event("BOOK", 12, "middle")
        );

        Comparator<Event> byVersionThenPayload =
            Comparator.comparingLong(Event::version)
                .thenComparing(Event::payload);

        ConcurrentMap<String, Event> latest = events.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Event::key,
                event -> event,
                BinaryOperator.maxBy(byVersionThenPayload)
            ));

        System.out.println(latest.get("BOOK").payload()); // new
        System.out.println(latest.get("BOOK").version()); // 15
    }
}
~~~

With this comparison rule, any Events sharing a key are selected by **highest version**, then `payload` to break ties. If two Events can share the same version and payload while differing in other business attributes, define additional criteria if picking a specific representative matters.

This is a general design principle: **thread processing order is not business order**. When you need the “latest”, store a reliable timestamp/sequence/version and encode that comparison directly into the algorithm.

## 7. Choosing the ConcurrentMap Type via mapFactory

If you need a specific Map type, use the four-parameter overload:

~~~java
toConcurrentMap(
    keyMapper,
    valueMapper,
    mergeFunction,
    mapFactory
)
~~~

`mapFactory` is a `Supplier<M>` where `M extends ConcurrentMap<K,U>`. It must supply a suitable container, typically **a new and empty Map** for each collection run.

### 7.1. ConcurrentSkipListMap: Sorted by Key

`ConcurrentSkipListMap` supports both concurrent operations and iterating keys in comparison order:

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.stream.Collectors;

public class SortedConcurrentMap {
    record Item(String sku, long quantity) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
            new Item("PEN", 2),
            new Item("BOOK", 3),
            new Item("PAD", 1),
            new Item("BOOK", 1)
        );

        ConcurrentSkipListMap<String, Long> units = items.parallelStream()
            .collect(Collectors.toConcurrentMap(
                Item::sku,
                Item::quantity,
                Long::sum,
                ConcurrentSkipListMap::new
            ));

        System.out.println(units.keySet()); // [BOOK, PAD, PEN]
        System.out.println(units.get("BOOK")); // 4
    }
}
~~~

`ConcurrentSkipListMap` is sorted by **key**. That does not mean the collector stores records in encounter order or calls `mergeFunction` in source order. Two different properties:

- **Key iteration order:** provided by the Map implementation.
- **Order in which values are merged:** the UNORDERED collector makes no guarantee regarding source order.

If the comparator treats two distinct keys as equivalent (comparison returns 0), the Map may consider them the same key; configure a comparator consistent with your business key definition.

### 7.2. ConcurrentHashMap: Choice When Key Sorting Is Not Needed

~~~java
import java.util.concurrent.ConcurrentHashMap;

ConcurrentHashMap<String, Long> units = items.parallelStream()
    .collect(Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum,
        ConcurrentHashMap::new
    ));
~~~

This snippet assumes `Item` and `items` from the previous example. Use `ConcurrentHashMap::new` if that specific Map class is required. `ConcurrentHashMap` does not guarantee key iteration order.

### 7.3. Do Not Use a Regular HashMap as the Factory

~~~java
// Does not satisfy the type bound M extends ConcurrentMap<K, U>:
// Collectors.toConcurrentMap(
//     Item::sku, Item::quantity, Long::sum, HashMap::new
// );
~~~

`HashMap` and `LinkedHashMap` do not implement `ConcurrentMap`. If the requirement is a Map that preserves insertion order and does not need a concurrent collector, consider `Collectors.toMap(..., LinkedHashMap::new)` instead of trying to force a factory into `toConcurrentMap`.

## 8. CONCURRENT and UNORDERED: Characteristics of the Collector

`Collector.Characteristics` describes how a collector can be used. `Collectors.toConcurrentMap` is a **concurrent** and **unordered** collector.

- `CONCURRENT` permits the framework to call the accumulator concurrently from multiple threads **on the same result container**, per the contract.
- `UNORDERED` indicates that accumulation does not need to preserve source order.
- Results from this kind of collector can be used directly as a Map without complex final type conversion; however, do not build logic depending on Map identity or callback execution order.

### 8.1. Inspecting Collector Characteristics

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

record Item(String sku, long quantity) {}

Collector<Item, ?, ConcurrentMap<String, Long>> collector =
    Collectors.toConcurrentMap(
        Item::sku,
        Item::quantity,
        Long::sum
    );

System.out.println(
    collector.characteristics().contains(
        Collector.Characteristics.CONCURRENT
    )
); // true

System.out.println(
    collector.characteristics().contains(
        Collector.Characteristics.UNORDERED
    )
); // true
~~~

Having `CONCURRENT` **does not** mean terminal `collect` runs in parallel when the Stream source is sequential. A sequential Stream can still use `toConcurrentMap`; it just means the result has a ConcurrentMap interface and the collector is capable of concurrent accumulation if the system uses it accordingly.

### 8.2. How Does a Parallel Stream Work?

With a concurrent, unordered collector, a parallel stream implementation can have branches **accumulate directly into one concurrent container** rather than being forced to create multiple separate Maps and merge them in encounter order. The API permits the appropriate strategy, but does not guarantee a specific thread count, merge count, callback timing, or speedup.

~~~text
            Parallel Stream processing branches
                │         │         │
                ▼         ▼         ▼
           accumulator accumulator accumulator
                │         │         │
                └─────────┼─────────┘
                          ▼
                    ConcurrentMap

             (Conceptual diagram; not a mandatory thread schedule)
~~~

Even with an ordered source like `List`, an `UNORDERED` collector is still allowed to ignore encounter order. Thus, it is unsuitable when the final value depends on which records arrive earlier or later.

## 9. Null Policy: Must Control Both Keys and Values

A common `ConcurrentMap` like `ConcurrentHashMap` **does not accept `null` keys or `null` values**. `ConcurrentSkipListMap` also rejects null values and rejects null keys in standard usage.

Therefore, when using `toConcurrentMap`:

- Do not let `keyMapper` return null.
- Do not let `valueMapper` return null.
- Do not return null from `mergeFunction` to “represent an absent value” without fully understanding `Map.merge` semantics.
- Choose a business policy upfront: **filter out**, **normalize to a valid value**, or **report an error**.

Example sanitizing data before collect:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class NullSafeConcurrentMap {
    record Product(String sku, String name) {}

    public static void main(String[] args) {
        List<Product> raw = Arrays.asList(
            new Product("P01", "Pen"),
            new Product(null, "Missing code"),
            new Product("P02", null)
        );

        ConcurrentMap<String, String> names = raw.parallelStream()
            .filter(p -> p.sku() != null && p.name() != null)
            .collect(Collectors.toConcurrentMap(
                Product::sku,
                Product::name
            ));

        System.out.println(names.size()); // 1
        System.out.println(names.get("P01")); // Pen
    }
}
~~~

The snippet above chooses the policy of **dropping incomplete records**. If missing data must be recorded or flagged as an error, return a result type with an error status, collect a discrepancy report, or throw an exception. Dropping data must not be treated as the default in every business domain.

### 9.1. Why Is a mergeFunction Returning Null Dangerous?

Common implementations rely on `Map.merge` semantics: if the remapping function returns `null`, the key mapping can be **removed** from the Map. Thus:

~~~java
// Do not use null as a valid aggregated result:
(left, right) -> null
~~~

This does not mean “keep the key with an empty value”. When merging multiple lines with the same key, it can cause the entry to be deleted, and then a later line recreates the key, making results unpredictable. Use a value object holding state or an explicit merge policy instead of relying on null.

## 10. Thread Safety: A Safe Map Does Not Mean Safe Callbacks

`ConcurrentMap` provides concurrent operations at the Map level. However, if `keyMapper`, `valueMapper`, or `mergeFunction` accesses or mutates shared mutable data, they can still cause race conditions or nondeterministic results.

### 10.1. Incorrect Example: Shared Counter Inside the Mapper

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Collectors;

// Contraindicated if you want key order to match input order.
AtomicInteger counter = new AtomicInteger();

var result = IntStream.range(0, 1000)
    .parallel()
    .boxed()
    .collect(Collectors.toConcurrentMap(
        n -> "K" + counter.getAndIncrement(),
        n -> n
    ));
~~~

`AtomicInteger` makes the increment operation atomic, but **the sequence number attached to each element depends on scheduling**. If you want keys `K0`, `K1` ... to correspond to source indices, use `n -> "K" + n` directly. This is a **business semantics** bug, even though there is no data race on the increment itself.

### 10.2. Incorrect Example: Merging by Mutating a Shared ArrayList

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

record Row(String key, String value) {}

List<Row> rows = List.of(
    new Row("A", "x"),
    new Row("A", "y")
);

// Do not use a mutable list as a value that may be
// read/written concurrently outside the pipeline without proper synchronization.
var map = rows.parallelStream().collect(
    Collectors.toConcurrentMap(
        Row::key,
        row -> new ArrayList<>(List.of(row.value())),
        (left, right) -> {
            left.addAll(right); // Mutation-style merge: hard to use safely outside collector scope.
            return left;
        }
    )
);
~~~

Operations on the List may execute under per-key synchronization of the ConcurrentMap implementation, yet **the resulting Lists are not inherently thread-safe** when other tasks access or mutate them concurrently. Moreover, mutation inside merge increases the complexity of proving associativity and reusing the reducer. If the goal is to **collect a list of records per key**, using `groupingByConcurrent` with a collector-managed downstream expresses the intent far more clearly.

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, List<Row>> grouped = rows.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Row::key,
        Collectors.toList()
    ));
~~~

**Note:** Each `List<Row>` value inside the `ConcurrentMap` is not guaranteed to be safe for arbitrary concurrent modifications **after** collect. `groupingByConcurrent` manages accumulation according to the Collector contract during collection; it does not turn all nested values into concurrent collections.

### 10.3. What Should You Do with mergeFunction?

- Prefer **pure** functions that do not interfere with the source and hold no external mutable state.
- Ensure **associativity**, and if order-independent stability is required, choose a **commutative** operation or a deterministic representative selection rule.
- Do not use merge functions to send emails, write mandatory business audit logs, call external services, or mutate another Map.
- For expensive computations, consider contention levels on hot keys and test realistically.

## 11. Comparing toMap, toConcurrentMap, and groupingByConcurrent

These three collectors share the fact that they return a Map, but they solve three different needs.

| Criterion | `toMap` | `toConcurrentMap` | `groupingByConcurrent` |
| --- | --- | --- | --- |
| Output type | `Map<K,U>` | `ConcurrentMap<K,U>` | `ConcurrentMap<K,D>` |
| Collector has `CONCURRENT`? | No | Yes | Yes |
| Collector `UNORDERED`? | Not by default | Yes | Yes |
| Duplicate keys | Error or uses merge function | Error or uses merge function | Multiple elements are placed into **the same group** |
| Group value | A single `U` after mapping/merging | A single `U` after mapping/merging | Result of the downstream collector |
| Map customization | `mapFactory`, requires `Map` | `mapFactory`, requires `ConcurrentMap` | `mapFactory`, requires `ConcurrentMap` |
| Need to preserve encounter order semantics | Can consider `toMap` with suitable Map/merge | No | No |

### 11.1. When Only One Aggregated Value Per Key Is Needed

~~~java
ConcurrentMap<String, Long> units = lines.parallelStream()
    .collect(Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum
    ));
~~~

`toConcurrentMap` is clear when each key maps to **one final value**, produced by a meaningful merge operation.

### 11.2. When a Full List Per Key Is Needed

~~~java
ConcurrentMap<String, List<OrderLine>> linesBySku =
    lines.parallelStream().collect(
        Collectors.groupingByConcurrent(OrderLine::sku)
    );
~~~

`groupingByConcurrent` automatically manages accumulating multiple elements into each group. Note that `groupingByConcurrent` does not guarantee encounter order within each group's list.

### 11.3. When First-Seen Order or an Insertion-Ordered Map Is Needed

If the output requirement is a Map that iterates keys in order of first appearance in the source, `toConcurrentMap` is not the right choice. Use an ordered collector and an appropriate factory:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> ordered = lines.stream()
    .collect(Collectors.toMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum,
        LinkedHashMap::new
    ));
~~~

`LinkedHashMap` stores key insertion order, suited for sequential pipelines with encounter order. It **is not a ConcurrentMap**. If you only need **key-sorted** order, you can use `ConcurrentSkipListMap` with `toConcurrentMap` as shown in section 7.

## 12. Combining toConcurrentMap with Multi-Level Collectors

We can also use `toConcurrentMap` as a **downstream** of a grouping collector. This is a way to build a hierarchical report consisting of a region Map containing inner Maps of SKU and total quantity.

~~~java
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class NestedConcurrentReport {
    record OrderLine(String region, String sku, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("South", "BOOK", 2),
            new OrderLine("South", "BOOK", 1),
            new OrderLine("South", "PEN",  1),
            new OrderLine("North", "PEN",  4)
        );

        ConcurrentMap<String, ConcurrentMap<String, Integer>> report =
            lines.parallelStream().collect(
                Collectors.groupingByConcurrent(
                    OrderLine::region,
                    Collectors.toConcurrentMap(
                        OrderLine::sku,
                        OrderLine::quantity,
                        Integer::sum
                    )
                )
            );

        System.out.println(report.get("South").get("BOOK")); // 3
        System.out.println(report.get("South").get("PEN"));  // 1
        System.out.println(report.get("North").get("PEN"));  // 4
    }
}
~~~

There are two key levels:

- `region` is the key of the outer `ConcurrentMap`.
- `sku` is the key of the inner `ConcurrentMap`.
- `Integer::sum` merges quantities of lines sharing the same region and SKU.

The return type is `ConcurrentMap<String, ConcurrentMap<String, Integer>>`. This structure is useful when the system needs fast two-level lookups, though it also carries Map and object allocation costs; if you only need a small one-off report, sequential `groupingBy` or a composite key record may be simpler.

## 13. Nulls, Hot Keys, Performance, and Resource Limits

### 13.1. Hot Keys Reduce Useful Parallelism

Suppose millions of records all belong to a single SKU `"BOOK"`. Even though multiple threads read the source concurrently, updates to **one key** must be coordinated to prevent lost data.

~~~text
Multiple parallel branches ─────► same key "BOOK"
                                │
                                ▼
                      Coordinated update/merge
                                │
                                ▼
                           One final value
~~~

Thus, collector concurrency does not guarantee that every merge workload scales linearly with core count. When the number of groups is very small and distribution is skewed, contention can become a bottleneck.

### 13.2. Large Group Counts Consume Memory

Each distinct key creates an entry in the Map. If keys are generated from nearly unique data, such as a UUID per record, `toConcurrentMap` can create a huge Map, even when no keys need merging. `ConcurrentMap` is not infinite storage; account for RAM limits, GC pressure, and batch processing strategies if output size is large.

### 13.3. Do Not Measure Performance with a Single Run

To compare `toMap` and `toConcurrentMap`:

1. Use the same data and the same output requirements, without silently switching from “ordered” to “any order”.
2. Verify correctness first using `Map.equals` or business invariants.
3. Measure both sequential and parallel modes, across multiple runs and under stable conditions.
4. Vary source size, distinct key count, key collision rate, and mapper cost.
5. Measure elapsed time, allocations/GC, and CPU utilization when needed.

There is no fixed threshold where “above n elements, toConcurrentMap is always faster”. Effectiveness depends on `Spliterator`, pre-collect steps, hash functions and key comparisons, data distribution, merge function, and machine resources.

### 13.4. I/O Sources and Side Effects Still Require Separate Management

If the Stream source is built from `Files.lines` or sockets, manage resources via `try-with-resources`; `collect` does not automatically close resource-backed sources. Parallel streams may execute callbacks on multiple threads, so HTTP calls or DB writes inside mappers require retry/timeout/backpressure and idempotency designs rather than relying merely on `toConcurrentMap`.

## 14. Testing: Results Independent of Execution Schedule

A good test does not compare the string printed by `ConcurrentMap.toString()` because default iteration order is not guaranteed. Compare key and value contents instead.

The following standalone example verifies totals across 10 groups, each with 1,000 elements from the range 0 to 9,999:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ConcurrentMapChecks {
    static ConcurrentMap<Integer, Long> countByRemainder(
        boolean parallel
    ) {
        IntStream stream = IntStream.range(0, 10_000);
        stream = parallel ? stream.parallel() : stream.sequential();

        return stream.boxed().collect(Collectors.toConcurrentMap(
            number -> number % 10,
            number -> 1L,
            Long::sum
        ));
    }

    public static void main(String[] args) {
        ConcurrentMap<Integer, Long> serial =
            countByRemainder(false);

        ConcurrentMap<Integer, Long> parallel =
            countByRemainder(true);

        if (!serial.equals(parallel)) {
            throw new AssertionError("Both modes produced different results");
        }

        if (parallel.size() != 10) {
            throw new AssertionError("Missing or extra groups");
        }

        for (int key = 0; key < 10; key++) {
            if (parallel.get(key) != 1000L) {
                throw new AssertionError("Wrong count for group " + key);
            }
        }

        System.out.println("PASS");
    }
}
~~~

This check proves correctness for **the test dataset**, not that every merge function is associative or every workload is fast. Additional test cases should include:

- Empty stream: empty Map result.
- A single key appearing many times.
- Many distinct keys, both uniform and skewed distributions.
- Duplicate keys in the two-parameter overload: throws as expected.
- Null in key/value: handled according to policy.
- Numeric overflow, comparator ties, and record versions.
- Repeated sequential/parallel runs to catch schedule sensitivity.

## 15. Common Mistakes

### Mistake 1: Using the Two-Parameter Overload When Keys Can Collide

~~~java
// May throw IllegalStateException:
lines.parallelStream().collect(
    Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity
    )
);
~~~

If the goal is total quantity, add `Long::sum`; if keys are supposed to be unique, keep this form and treat duplicate keys as bad data.

### Mistake 2: Using (left, right) -> right to Pick the “Latest Row”

~~~java
// Unreliable if you want the row with the latest timestamp/version:
(left, right) -> right
~~~

Because the collector is unordered, merge order is not guaranteed to follow source order. Select using a comparator on a business field like `version` or `timestamp`.

### Mistake 3: Using HashMap::new as the Factory

~~~java
// Does not compile due to the bound M extends ConcurrentMap<K,U>:
// toConcurrentMap(keyMapper, valueMapper, mergeFn, HashMap::new)
~~~

Choose `ConcurrentHashMap::new` or `ConcurrentSkipListMap::new` when a specific ConcurrentMap type is needed.

### Mistake 4: Treating List Values Inside the Map as Thread-Safe

~~~java
// ConcurrentMap<String, List<String>> does not make each List<String>
// a thread-safe collection for concurrent modification.
~~~

Use an appropriate collector to gather lists, publish the data only after collect completes, and establish a synchronization policy if the Lists will be mutated later.

### Mistake 5: Ignoring Nulls

~~~java
// Do not let keyMapper/valueMapper return null when collecting into
// common ConcurrentMaps like ConcurrentHashMap.
~~~

Filter or convert null into a valid state before the terminal operation. If null is a business error, raise an error instead of silently dropping data.

### Mistake 6: Merge Function with Side Effects

~~~java
// Bad idea: updating shared variables or sending requests inside merge.
// merge can run on multiple threads and in unpredictable order.
~~~

Write a pure merge function; perform side effects after collecting and verifying the result.

### Mistake 7: Thinking a Concurrent Collector Automatically Enables Parallel

~~~java
// The Stream remains sequential, even though the collector has CONCURRENT:
var serial = lines.stream().collect(
    Collectors.toConcurrentMap(
        OrderLine::sku,
        OrderLine::quantity,
        Long::sum
    )
);
~~~

Execution mode is determined by `stream()`, `parallelStream()`, `parallel()`, and `sequential()`. Collector concurrency only describes accumulation capability, without switching modes automatically.

### Mistake 8: Assuming the ConcurrentMap Is Unmodifiable

The result is a ConcurrentMap that can support `put`, `remove`, `compute`, `merge`. It is **not** an immutable snapshot. If the API should only return an unmodifiable view, decide how to create a published copy:

~~~java
import java.util.Map;

// Collection has finished, no other threads are mutating values:
Map<String, Long> snapshot = Map.copyOf(units);
~~~

`Map.copyOf` returns an unmodifiable Map and forbids null keys/values, though it does **not** guarantee preserving `ConcurrentSkipListMap`'s key iteration order. Mutable value objects inside the Map can still be modified; for a deeply immutable snapshot, copy/normalize child objects as well.

## 16. Quick Selection Guide

| Requirement | Recommended Choice | Reason |
| --- | --- | --- |
| Convert records with unique keys into a lookup Map | `toConcurrentMap(key, value)` if a ConcurrentMap is needed | Fails on duplicate keys |
| Sum quantities by SKU on a parallel stream | `toConcurrentMap(key, value, Long::sum)` | Associative merge, order-independent |
| Pick the latest record by version | `toConcurrentMap(key, event, maxBy(comparator))` | Deterministic rule by business key |
| Need a Map sorted by key with concurrency support | `toConcurrentMap(..., ConcurrentSkipListMap::new)` | Ordered by key comparison |
| Need an insertion-ordered Map | `toMap(..., LinkedHashMap::new)` | Not a concurrent collector |
| Need multiple records per group | `groupingByConcurrent(key)` | Downstream group accumulation |
| Need totals or stats by group without needing ConcurrentMap | `groupingBy(key, summingX(...))` | Can be cleaner for sequential reports |
| Null keys/values possible | Filter, normalize, or fail before collect | Prevents wrong results and NPEs |
| Only need an immutable set of values after computation | Collect then `Map.copyOf` if suitable | Separates processing state from published API |
| Large data, many hot keys | Benchmark and inspect distribution | Contention may limit speed |

## 17. Self-Check Questions

1. **Does `Collectors.toConcurrentMap` immediately return a ConcurrentMap or a Collector?** It returns a Collector; the Map is created when terminal `collect` executes.
2. **What does the two-parameter overload do when two elements share a key?** Throws `IllegalStateException`.
3. **When do you need the three-parameter overload?** When keys can collide and you want to specify how to merge values.
4. **What is the fourth parameter used for?** `mapFactory` selects a specific `ConcurrentMap` implementation.
5. **Can `LinkedHashMap::new` be used as the factory?** No; that Map does not implement `ConcurrentMap`.
6. **What are the two key Collector characteristics of `toConcurrentMap`?** `CONCURRENT` and `UNORDERED`.
7. **Does `UNORDERED` guarantee shuffled/randomized key order?** No; it only drops the encounter order constraint.
8. **What does `ConcurrentSkipListMap` order?** **Key** order via comparator/natural ordering, not record processing order.
9. **Why doesn't `(a,b) -> b` accurately represent the “latest record”?** Merges can happen according to thread scheduling and source splitting; compare version/timestamp fields instead.
10. **Does `ConcurrentMap<String,List<T>>` make inner Lists safe when multiple threads mutate them together?** No.
11. **If keyMapper returns null, how should it be handled?** Filter, replace the key with a valid state, or fail before collect.
12. **Can mergeFunction return null to keep the key with a missing value?** No. `Map.merge` semantics can remove the mapping.
13. **Does a concurrent collector automatically turn `stream()` into a parallel stream?** No; execution mode is determined by the Stream.
14. **Why is `Long::sum` usually better suited than string concatenation for merging in an unordered collector?** Addition is order-independent, whereas concatenation changes the result if order is reversed.
15. **When should you use `groupingByConcurrent` instead of `toConcurrentMap`?** When each key needs to accumulate a group/list or its own downstream collector.
16. **Can two ConcurrentMap results be compared with `Map.equals`?** Yes, when the goal is the same set of key–value pairs and values implement `equals` properly; do not compare print order.
17. **If one SKU accounts for most of the data, what can happen?** Updates to the same key create contention and reduce the benefits of parallel execution.
18. **Why isn't the returned Map automatically immutable?** `ConcurrentMap` supports mutation; if a published snapshot is needed, create a copy or appropriate view after collect.

**Remember:** `Collectors.toConcurrentMap` creates a **ConcurrentMap** from Stream elements, with options to detect duplicate keys, merge values, and select a specific ConcurrentMap type. This collector has **CONCURRENT** and **UNORDERED** characteristics, so do not use encounter order as the rule for picking “first/last value”. Design an associative `mergeFunction` free of shared state, control nulls, use the proper mapFactory, and evaluate key distribution and real performance before choosing parallel collection.
