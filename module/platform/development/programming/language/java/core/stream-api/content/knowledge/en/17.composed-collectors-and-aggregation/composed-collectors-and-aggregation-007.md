# Reducing Each Group with reducing

## 1. From grouping to a single aggregated value per group

In the **Composed Collectors and Aggregation** chapter of **JAVA_STREAM_API**, `Collectors.groupingBy` can do more than collect records into a `List`. Each group can also be **reduced directly to a single value**: a revenue figure, the largest order, a concatenated code string, or a summary object with multiple metrics.

For example, a sales system wants to generate a regional report. For each region, instead of keeping all orders and iterating over the list afterward, we can use a *downstream collector* to compute the result right during collection:

~~~text
Stream<Order>
     │
     ▼
groupingBy(Order::region, downstream)
     │
     ├─ Region "Nam"   ──► reducing(...) ──► Region Nam summary
     ├─ Region "Bắc"   ──► reducing(...) ──► Region Bắc summary
     └─ Region "Trung" ──► reducing(...) ──► Region Trung summary
     │
     ▼
Map<String, GroupResult>
~~~

`Collectors.reducing` acts as a **downstream reduction**: combining the elements within a group into one result, honoring the identity and combining operation. The result of `groupingBy` is still `Map<K,D>`, yet `D` does not have to be `List<T>`.

This lesson focuses on the three overloads of `reducing`, composing with `groupingBy`, handling empty groups, building immutable results, and conditions for a reduction to be valid in parallel pipelines. Examples use Java 17+; `Collectors.reducing` and `groupingBy` have been available since Java 8.

## 2. The three overloads of Collectors.reducing

Conceptual signatures in `java.util.stream.Collectors`:

~~~java
// 1. No identity: may have no result.
static <T> Collector<T, ?, Optional<T>> reducing(
    BinaryOperator<T> op
);

// 2. With identity, element and result share the same type T.
static <T> Collector<T, ?, T> reducing(
    T identity,
    BinaryOperator<T> op
);

// 3. With identity, maps element T to U before combining.
static <T, U> Collector<T, ?, U> reducing(
    U identity,
    Function<? super T, ? extends U> mapper,
    BinaryOperator<U> op
);
~~~

| Form | Input per group | Result per group | Typical use cases |
| --- | --- | --- | --- |
| `reducing(op)` | `T` | `Optional<T>` | Picking the best element, combining when no suitable identity element exists |
| `reducing(identity, op)` | `T` | `T` | Summing numbers or combining values of the same type |
| `reducing(identity, mapper, op)` | `T` | `U` | Summing revenue from `Order`, building summary value objects |

**Difference from `Stream.reduce`:** `Stream.reduce(...)` is a terminal operation called directly on a Stream; `Collectors.reducing(...)` returns a **Collector**, typically passed as the `downstream` argument of `groupingBy` or `partitioningBy`. For example, a stream-wide sum can be written with `stream.reduce(...)`, whereas a sum **for each key** is typically written with `stream.collect(groupingBy(key, reducing(...)))`.

`reducing` does not directly take three parameters `identity, accumulator, combiner` like `Stream.reduce(identity, accumulator, combiner)`. The three-parameter overload of the **collector** is `identity, mapper, binaryOperator`; confusing the two signatures easily leads to compilation errors.

## 3. Dataset used throughout the lesson

The following example runs standalone. Money is stored as `BigDecimal` to avoid floating-point errors when adding decimal values; all orders are assumed to share the same currency unit.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class OrderData {
    record Order(
        String id,
        String region,
        String sku,
        int quantity,
        BigDecimal unitPrice
    ) {
        BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    static List<Order> orders() {
        return List.of(
            new Order("O1", "Nam",   "BOOK", 2, new BigDecimal("50.00")),
            new Order("O2", "Bắc",   "PEN",  3, new BigDecimal("10.00")),
            new Order("O3", "Nam",   "PEN",  1, new BigDecimal("10.00")),
            new Order("O4", "Trung", "PAD",  1, new BigDecimal("30.00")),
            new Order("O5", "Bắc",   "BOOK", 1, new BigDecimal("50.00"))
        );
    }

    public static void main(String[] args) {
        System.out.println(
            orders().stream().map(Order::lineTotal).toList()
        );
        // [100.00, 30.00, 10.00, 30.00, 50.00]
    }
}
~~~

In the short snippets below, `Order` and `orders` refer to `OrderData.Order` and the result of `OrderData.orders()`, or equivalent declarations in the same class. Three groups have data:

| Region | Order IDs | Line count | Total revenue |
| --- | --- | ---: | ---: |
| Nam | O1, O3 | 2 | 110.00 |
| Bắc | O2, O5 | 2 | 80.00 |
| Trung | O4 | 1 | 30.00 |

Results are checked by key using `Map.get(...)`; **do not rely on the print order of the default Map**, because `groupingBy` does not guarantee a Map implementation or key iteration order.

## 4. First form: reducing(BinaryOperator) returning Optional per group

When you want **the highest-value order** in each region, there is no natural “zero” order to serve as an identity. Therefore, use the single-parameter overload:

~~~java
import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

// Given List<Order> orders in scope:
Comparator<Order> byValueThenId = Comparator
    .comparing(Order::lineTotal)
    .thenComparing(Order::id);

Map<String, Optional<Order>> biggestOrderByRegion =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(BinaryOperator.maxBy(byValueThenId))
    ));

System.out.println(biggestOrderByRegion.get("Nam").orElseThrow().id()); // O1
System.out.println(biggestOrderByRegion.get("Bắc").orElseThrow().id()); // O5
System.out.println(biggestOrderByRegion.get("Trung").orElseThrow().id()); // O4
~~~

Explanation:

1. `Order::region` produces the group key.
2. `BinaryOperator.maxBy(byValueThenId)` compares two orders by line total, then by order ID to break ties.
3. `Collectors.reducing(...)` uses this “greater-than” selection to combine orders within **one group**.
4. The value associated with each key has type `Optional<Order>`.

Why does the Map hold `Optional` even though groups are formed from actual records? Because this collector must support **receiving zero elements**, especially when combined with downstream `filtering`. Do not blindly call `get()` on `Optional`; use `orElseThrow` when non-emptiness is guaranteed by business logic, or handle the empty branch explicitly.

### 4.1. When to use maxBy instead of reducing?

For selecting a maximum, the library already provides a dedicated collector:

~~~java
Map<String, Optional<Order>> biggest = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.maxBy(byValueThenId)
    ));
~~~

`Collectors.maxBy(comparator)` is semantically equivalent to `Collectors.reducing(BinaryOperator.maxBy(comparator))`. The dedicated form is usually shorter and states intent more clearly. Similarly, use `Collectors.minBy(...)` for minimum selection.

Use `reducing(BinaryOperator)` when the combining operation has custom business semantics, such as selecting a version via multi-field rules or merging two value objects using a custom operator.

### 4.2. Note on records tied under the comparator

If the comparator treats two distinct records as equal, which **representative record** is retained can depend on encounter order and combining order. When record identity matters, design the comparator with a stable tie-breaker (such as a unique ID) or define an explicit selection policy.

## 5. Second form: reducing(identity, op) on values of the same type

If the downstream input is already `BigDecimal`, we can use `BigDecimal.ZERO` as the identity and `BigDecimal::add` to combine:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::lineTotal,
            Collectors.reducing(
                BigDecimal.ZERO,
                BigDecimal::add
            )
        )
    ));

System.out.println(revenueByRegion.get("Nam"));   // 110.00
System.out.println(revenueByRegion.get("Bắc"));   // 80.00
System.out.println(revenueByRegion.get("Trung")); // 30.00
~~~

Here there are **two nested downstream collectors**:

- `mapping(Order::lineTotal, ...)` converts each `Order` in the group into a `BigDecimal`.
- `reducing(BigDecimal.ZERO, BigDecimal::add)` sums the converted amounts.

The result of `groupingBy` is `Map<String, BigDecimal>`, not a Map of lists or Optionals.

`BigDecimal.ZERO` is a valid **numeric-value** identity for addition. `BigDecimal.add` does not round when no `MathContext` is supplied, making it suitable for summing amounts in the same currency in this example. When a system has multiple currencies, you must group by currency or convert under an explicit exchange-rate policy; addition will not do that automatically.

### 5.1. Same meaning using the third form, with fewer nested layers

~~~java
Map<String, BigDecimal> revenueByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

This form is usually clearer when only one mapping step followed by addition is needed: `reducing(identity, mapper, op)` already incorporates turning `Order` into `BigDecimal`.

### 5.2. When only an integer sum is needed

If money is properly modeled as `long` in minor units and there is no overflow risk, a specialized collector is usually simpler:

~~~java
// Assume Order has a method long totalInMinorUnits().
Map<String, Long> sums = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.summingLong(Order::totalInMinorUnits)
    ));
~~~

This snippet illustrates a different model with a `totalInMinorUnits` method; it is not part of the `Order` record declared in section 3. `summingLong` can overflow `long` if the sum is too large; it does not check for overflow automatically. Choose numeric types and validation policies suited to the business domain.

## 6. Third form: reducing(identity, mapper, op) when result type differs from source type

This form is very useful when `groupingBy` needs an **aggregated value object** per group, instead of merely counting or summing a single field.

Suppose each region needs three metrics: order count, total units, and revenue. We define `Summary` as an immutable record.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class GroupedSalesSummary {
    record Order(
        String id,
        String region,
        int quantity,
        BigDecimal unitPrice
    ) {
        BigDecimal revenue() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Summary(
        long orderCount,
        long unitCount,
        BigDecimal revenue
    ) {
        static Summary zero() {
            return new Summary(0L, 0L, BigDecimal.ZERO);
        }

        static Summary from(Order order) {
            return new Summary(
                1L,
                order.quantity(),
                order.revenue()
            );
        }

        Summary merge(Summary other) {
            return new Summary(
                orderCount + other.orderCount(),
                unitCount + other.unitCount(),
                revenue.add(other.revenue())
            );
        }
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O1", "Nam", 2, new BigDecimal("50.00")),
            new Order("O2", "Bắc", 3, new BigDecimal("10.00")),
            new Order("O3", "Nam", 1, new BigDecimal("10.00")),
            new Order("O4", "Trung", 1, new BigDecimal("30.00")),
            new Order("O5", "Bắc", 1, new BigDecimal("50.00"))
        );

        Map<String, Summary> report = orders.stream()
            .collect(Collectors.groupingBy(
                Order::region,
                TreeMap::new,
                Collectors.reducing(
                    Summary.zero(),
                    Summary::from,
                    Summary::merge
                )
            ));

        System.out.println(report.get("Nam"));
        // Summary[orderCount=2, unitCount=3, revenue=110.00]

        System.out.println(report.get("Bắc"));
        // Summary[orderCount=2, unitCount=4, revenue=80.00]

        System.out.println(report.get("Trung"));
        // Summary[orderCount=1, unitCount=1, revenue=30.00]
    }
}
~~~

How the components work together:

| Component | Role | Type |
| --- | --- | --- |
| `Order::region` | Computes group key | `Order → String` |
| `TreeMap::new` | Creates a Map with sorted keys | `TreeMap<String, Summary>` |
| `Summary.zero()` | Neutral result for each group | `Summary` |
| `Summary::from` | Converts one order into a single-element summary | `Order → Summary` |
| `Summary::merge` | Combines two summary results | `(Summary, Summary) → Summary` |

Because `Summary` is not mutated in place, each `merge` produces a new record. This design avoids situations where multiple processing branches mutate a shared accumulator object.

**Data bounds:** The example assumes valid quantities and unit prices, a single currency, and `long` additions without overflow. In a real system, validate those conditions. When additions must not round arbitrarily, `BigDecimal` is a useful choice for decimal sums.

## 7. Empty groups: distinguishing missing key, Optional.empty, and identity

This is an important distinction among the overloads of `reducing`.

### 7.1. A key that never appeared does not exist in groupingBy

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Row(String region, int value) {}

Map<String, Integer> sums = List.of(
    new Row("Nam", 5),
    new Row("Bắc", 7)
).stream().collect(Collectors.groupingBy(
    Row::region,
    Collectors.reducing(0, Row::value, Integer::sum)
));

System.out.println(sums.containsKey("Trung")); // false
~~~

`groupingBy` **does not create** the `"Trung"` key if the source has no rows for that region, even though the downstream has identity `0`.

### 7.2. Downstream filtering can create a group with 0 matching elements

`Collectors.filtering` (Java 9+) operates **inside** the group, after the classifier has recognized the key:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;

record Row(String region, int value) {}

List<Row> rows = List.of(
    new Row("Nam", 5),
    new Row("Nam", 9),
    new Row("Bắc", 2)
);

Map<String, Optional<Integer>> qualifiedMax = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.mapping(
                Row::value,
                Collectors.reducing(BinaryOperator.maxBy(Integer::compare))
            )
        )
    ));

System.out.println(qualifiedMax.get("Nam"));   // Optional[9]
System.out.println(qualifiedMax.get("Bắc"));   // Optional.empty
System.out.println(qualifiedMax.containsKey("Trung")); // false
~~~

`"Bắc"` **is present in the Map** because an element carried that key, yet downstream `filtering` excluded it. Because the reducer has no identity, its result is `Optional.empty()`. Meanwhile, `"Trung"` never appeared and thus has no key in the Map.

### 7.3. With an identity, a filtered-empty group receives the identity

~~~java
Map<String, Integer> qualifiedSum = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.reducing(
                0,
                Row::value,
                Integer::sum
            )
        )
    ));

System.out.println(qualifiedSum.get("Nam")); // 14
System.out.println(qualifiedSum.get("Bắc")); // 0
System.out.println(qualifiedSum.containsKey("Trung")); // false
~~~

The form with an identity fits when `0` represents the valid sum of a **present group with no selected elements**. However, “no observations” and “an observed value of 0” must sometimes be distinguished; in that case, the `Optional` form may be more appropriate.

### 7.4. Upstream and downstream filtering are not equivalent

~~~java
// May eliminate the Bắc group completely.
Map<String, Integer> upstream = rows.stream()
    .filter(row -> row.value() >= 5)
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.reducing(0, Row::value, Integer::sum)
    ));

// Keeps the Bắc key with sum 0.
Map<String, Integer> downstream = rows.stream()
    .collect(Collectors.groupingBy(
        Row::region,
        Collectors.filtering(
            row -> row.value() >= 5,
            Collectors.reducing(0, Row::value, Integer::sum)
        )
    ));
~~~

If a dashboard must display groups that had input data even when the post-filter aggregate is 0, use `filtering` as a downstream. If only groups with qualifying elements should appear, filtering before `groupingBy` is better.

## 8. Combining reducing with mapping and multi-level groupingBy

Downstreams can be **nested** to build different reports without constructing Maps manually.

### 8.1. mapping before reducing

For example, concatenating order IDs per region into a string without a delimiter:

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, String> idsByRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(
            Order::id,
            Collectors.reducing("", String::concat)
        )
    ));

System.out.println(idsByRegion.get("Nam")); // O1O3
~~~

`String::concat` has identity `""` and is associative when string order is preserved. However, concatenating many immutable strings via a reducer can allocate many intermediate strings and incur copying overhead. When you only need to join text, `Collectors.joining(delimiter)` is usually shorter, more efficient, and more self-descriptive:

~~~java
Map<String, String> prettyIds = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.mapping(Order::id, Collectors.joining(", "))
    ));

System.out.println(prettyIds.get("Nam")); // O1, O3
~~~

String concatenation is **not commutative**: `"O1O3"` differs from `"O3O1"`. If a deterministic order is needed, preserve encounter order or sort explicitly; do not call `unordered()` before an order-dependent reduction.

### 8.2. Multi-level groupingBy with reducing at the leaf level

Problem: revenue for each SKU **within each region**.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, BigDecimal>> byRegionAndSku =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        TreeMap::new,
        Collectors.groupingBy(
            Order::sku,
            TreeMap::new,
            Collectors.reducing(
                BigDecimal.ZERO,
                Order::lineTotal,
                BigDecimal::add
            )
        )
    ));

System.out.println(byRegionAndSku.get("Nam").get("BOOK")); // 100.00
System.out.println(byRegionAndSku.get("Nam").get("PEN"));  // 10.00
~~~

Here there are three independent decisions: the **outer group key** is region, the **inner group key** is SKU, and the **final reduction** sums line totals. `TreeMap` ensures Map keys are sorted by `String.compareTo`; it **does not** alter the monetary addition rule.

If nesting makes the code hard to read, extract the downstream into an explicitly typed collector variable or a business-named helper method:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<Order, ?, BigDecimal> revenueCollector =
    Collectors.reducing(
        BigDecimal.ZERO,
        Order::lineTotal,
        BigDecimal::add
    );

Map<String, Map<String, BigDecimal>> report =
    orders.stream().collect(Collectors.groupingBy(
        Order::region,
        Collectors.groupingBy(Order::sku, revenueCollector)
    ));
~~~

Naming `revenueCollector` clarifies its purpose and makes it easy to reuse across other pipelines.

## 9. Identity and associativity: requirements for correct results

A downstream reducer can be split into parts and combined when a pipeline executes in parallel. `identity` and `op` must form an operation **with a neutral identity element and associativity** over the supported value domain.

For all valid results `a`, `b`, `c` and identity `e`:

~~~text
op(e, a) = a
op(a, e) = a
op(op(a, b), c) = op(a, op(b, c))
~~~

| Combining op | Identity | Valid when |
| --- | --- | --- |
| `BigDecimal::add` | `BigDecimal.ZERO` | Same currency/domain, without rounding policies that break associativity |
| `Integer::sum` | `0` | Java integer semantics is acceptable; for overflow-free math sums, pick suitable types/checks |
| `String::concat` | `""` | Encounter order must be preserved when character order matters |
| `Summary::merge` | `Summary.zero()` | All summary fields have compatible identities and merge operations |

### 9.1. Wrong: choosing a non-neutral identity

~~~java
import java.util.List;
import java.util.stream.Collectors;

int wrong = List.of(2, 3).stream()
    .collect(Collectors.reducing(10, Integer::sum));

System.out.println(wrong); // 15; not the sum 5.
~~~

`10` is not an identity for addition. With `groupingBy`, this value would also add an unwanted offset to every group.

### 9.2. Wrong: using subtraction or division as an associative combiner

~~~java
int wrong = List.of(10, 3, 2).stream()
    .collect(Collectors.reducing(0, (left, right) -> left - right));
~~~

Subtraction is not associative and `0` is not a two-sided identity. Observing a result in sequential execution does not make this formula a valid reduction contract for parallel streams.

If you need “10 minus the sum of discounts”, sum **the discounts** first, then subtract the total once at the final business step.

### 9.3. Wrong: using a mutable object as identity and mutating it

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

// ANTI-PATTERN: illustrates wrong usage.
List<String> broken = List.of("A", "B").parallelStream()
    .collect(Collectors.reducing(
        new ArrayList<String>(),
        value -> new ArrayList<>(List.of(value)),
        (left, right) -> {
            left.addAll(right); // Mutates the accumulator object.
            return left;
        }
    ));
~~~

`reducing(identity, mapper, op)` is not designed to mutate a single shared identity across branches. When the combiner mutates a List, duplicate entries, race conditions, or wrong results can occur. Use `toList`/`toCollection` or a contract-compliant custom collector when mutable reduction is needed:

~~~java
List<String> good = List.of("A", "B").parallelStream()
    .collect(Collectors.toList());
~~~

Similarly, do not increment global counters or perform I/O inside `classifier`, `mapper`, or `op` to count callback invocations. Streams may optimize and partition work; such side effects are not a valid accumulation mechanism.

## 10. Ordering, output Maps, and parallel execution

`Collectors.groupingBy` and `Collectors.reducing` can be used on **parallel streams**, yet `groupingBy` is not a concurrent collector. In parallel, the implementation may create intermediate Maps and merge them, incurring coordination and allocation overhead.

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> parallelRevenue = orders.parallelStream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

Because monetary addition in this example has a valid identity and is associative on numeric values, splitting orders across branches still produces the right total. However, correctness does not automatically imply faster performance: small sources, skewed groups, and Map merge cost can make parallel slower than sequential.

### 10.1. Where ordering constraints apply

The default Map from `groupingBy` does not guarantee **key** iteration order. If keys must be in comparable order, pass `TreeMap::new` to the three-parameter overload. If first-seen group order on a sequential pipeline with encounter order is needed, use `LinkedHashMap::new`.

**Map key** iteration order is a separate issue from the encounter order of **elements fed into the reducer**. When `op` is string concatenation, element order can affect the result; when `op` is numeric addition in an appropriate domain, order usually does not affect the mathematical sum.

### 10.2. Can groupingByConcurrent be used with reducing?

`Collectors.reducing` can be used as the downstream of `groupingByConcurrent` provided the reduction obeys the contract:

~~~java
import java.math.BigDecimal;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, BigDecimal> totals = orders.parallelStream()
    .collect(Collectors.groupingByConcurrent(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

`groupingByConcurrent` returns a `ConcurrentMap` and is an **unordered** collector; it is unsuitable when the reducer result depends on preserving source element order. Placing downstream `reducing` inside `groupingByConcurrent` does not grant permission to arbitrarily mutate shared state.

Whether parallel accumulation helps also depends on key contention across groups, dataset size, mapper cost, and element counts per group. Never assume concurrent is always faster.

## 11. When should you use a specialized collector instead of reducing?

`reducing` is general-purpose and very useful for producing domain value objects. However, when the task is a standard statistical operation, a specialized collector is usually shorter, avoids boxing, or works more efficiently.

| Goal per group | Usually preferred choice | Equivalent reducing form |
| --- | --- | --- |
| Element count in group | `counting()` | `reducing(0L, x -> 1L, Long::sum)` |
| Sum of `int` quantities | `summingInt(Order::quantity)` | `reducing(0, Order::quantity, Integer::sum)` |
| Sum of `long` quantities | `summingLong(...)` | `reducing(0L, mapper, Long::sum)` |
| Maximum value | `maxBy(comparator)` | `reducing(BinaryOperator.maxBy(comparator))` |
| Minimum value | `minBy(comparator)` | `reducing(BinaryOperator.minBy(comparator))` |
| Join strings with delimiter | `mapping(mapper, joining(", "))` | `mapping(mapper, reducing(...))` (usually verbose and allocates extra strings) |
| Standard count/min/max/sum/average | `summarizingInt/Long/Double(...)` | Building a custom statistics object then `reducing(...)` |
| Two metrics forming one record | `teeing(...)` | Building an intermediate record then `reducing(...)` |
| Merging a domain value object | `reducing(identity, mapper, op)` | Typically the most natural use case |

`Collectors.summingDouble` and `DoubleSummaryStatistics` are also affected by floating-point arithmetic and addition order. Do not rely on exact mathematical associativity of `double`: rounding can cause sequential and parallel results to differ.

Example using `teeing` to combine two metrics into a record per group without writing a manual record merge operator:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

record Totals(long count, BigDecimal revenue) {}

Map<String, Totals> totals = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.reducing(
                BigDecimal.ZERO,
                Order::lineTotal,
                BigDecimal::add
            ),
            Totals::new
        )
    ));
~~~

`teeing` has existed since Java 12; it feeds each record in a group to two downstreams and combines their results with `Totals::new`. If a system has several closely related metrics, an immutable summary like in section 6 can express the business domain more clearly.

## 12. Testing correctness with groups, empty sources, and ordering

The best way to test is not just eyeballing `Map.toString()`, because the default Map does not guarantee order. Assert directly on the value for each key and distinguish three cases:

1. **Group with data:** verify the computed sum or selected representative.
2. **Group that appeared but downstream filtered everything out:** verify the identity or `Optional.empty()`.
3. **Nonexistent group:** verify `Map.containsKey(...) == false`.

Quick verification example in plain Java:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupedReducingChecks {
    record Item(String group, BigDecimal amount) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
            new Item("A", new BigDecimal("2.50")),
            new Item("A", new BigDecimal("1.25")),
            new Item("B", new BigDecimal("4.00"))
        );

        Map<String, BigDecimal> serial = items.stream()
            .collect(Collectors.groupingBy(
                Item::group,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Item::amount,
                    BigDecimal::add
                )
            ));

        Map<String, BigDecimal> parallel = items.parallelStream()
            .collect(Collectors.groupingBy(
                Item::group,
                Collectors.reducing(
                    BigDecimal.ZERO,
                    Item::amount,
                    BigDecimal::add
                )
            ));

        if (serial.get("A").compareTo(new BigDecimal("3.75")) != 0) {
            throw new AssertionError("Wrong sum for group A");
        }

        if (serial.get("B").compareTo(new BigDecimal("4.00")) != 0) {
            throw new AssertionError("Wrong sum for group B");
        }

        if (serial.containsKey("C")) {
            throw new AssertionError("Must not invent group C");
        }

        if (!serial.equals(parallel)) {
            throw new AssertionError("Sequential and parallel results differ");
        }

        System.out.println("PASS");
    }
}
~~~

In this example, given the same `BigDecimal` inputs and non-rounding addition, sums stay consistent across parallel splitting. If the real domain has null values, negative amounts, multiple currencies, or integer arithmetic prone to overflow, add corresponding tests and business guards.

## 13. Common mistakes when reducing per group

### Mistake 1: reducing the whole Stream before thinking about groups

~~~java
// Computes ONE total for the entire Stream:
BigDecimal overall = orders.stream()
    .map(Order::lineTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

// Computes ONE total PER region:
Map<String, BigDecimal> perRegion = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BigDecimal.ZERO,
            Order::lineTotal,
            BigDecimal::add
        )
    ));
~~~

`Stream.reduce` does not group elements; to get per-key results, compose `groupingBy` with a downstream collector.

### Mistake 2: expecting the no-identity overload to return T directly

~~~java
// reducing(BinaryOperator<T>) returns Optional<T> for each group.
Map<String, Optional<Order>> selected = orders.stream()
    .collect(Collectors.groupingBy(
        Order::region,
        Collectors.reducing(
            BinaryOperator.maxBy(Comparator.comparing(Order::lineTotal))
        )
    ));
~~~

`Map<String, Order>` is not the right type for the expression above. If you need to unwrap `Optional`, define a policy for empty cases (especially when using downstream `filtering`).

### Mistake 3: setting identity to a non-neutral business value

~~~java
// Wrong for a normal sum: every group gets an extra 100 added.
Collectors.reducing(
    new BigDecimal("100"),
    Order::lineTotal,
    BigDecimal::add
);
~~~

Use `BigDecimal.ZERO` for sums, or define the proper identity for your specific value object.

### Mistake 4: corrupting results with mutable identity and side effects

~~~java
// Do not increment a mutable counter outside mapper/operator to build reports;
// do not mutate a shared List/Map from a reducing combiner in a parallel stream.
~~~

Let the collector manage accumulation, or use `toList` / `toMap` / `groupingBy` / a contract-compliant custom collector when mutable reduction is truly needed.

### Mistake 5: placing the filter at the wrong layer

If all previously seen groups must be preserved, place `Collectors.filtering` **inside** `groupingBy`. If only groups with matching elements should appear, filter **before** `groupingBy`. The two forms can differ even when the sums of remaining groups match.

### Mistake 6: assuming parallel will always speed things up

Custom reductions can allocate many intermediate objects; grouping also pays Map merging overhead. On small sources or heavily skewed groups, parallel can be slower. Measure on representative data and verify associativity before optimizing.

## 14. Decision table

| Question | Option to consider |
| --- | --- |
| Need one value across the whole source? | `Stream.reduce` or an appropriate terminal collector |
| Need one value per key? | `groupingBy(classifier, reducing(...))` |
| No valid identity exists? | `reducing(BinaryOperator)` → `Optional<T>` |
| Have identity, elements and result share the same type? | `reducing(identity, op)` |
| Need to map element `T` to result type `U`? | `reducing(identityU, mapper, op)` |
| Only need standard count/sum/min/max? | `counting`, `summingX`, `minBy`, `maxBy` |
| Need combinable multi-field statistics? | `reducing` with immutable record or `teeing` |
| Want to keep empty filtered groups? | `groupingBy(key, filtering(predicate, reducing(...)))` |
| Need a two-level report? | `groupingBy(key1, groupingBy(key2, reducing(...)))` |
| Need Map key iteration order? | Pass `LinkedHashMap::new` or `TreeMap::new` |
| Want order-independent parallel processing? | Verify combining laws; consider `groupingByConcurrent` and benchmark |

## 15. Self-check questions

1. **How do the three overloads of `Collectors.reducing` differ?** The first returns `Optional<T>`, the second uses an identity for `T` elements, and the third adds a mapper from `T` to `U`.
2. **Why does `groupingBy(region, reducing(...))` differ from `stream.reduce(...)`?** The former produces a separate result per key; the latter produces one result for the entire source.
3. **When using `reducing(BinaryOperator.maxBy(...))`, what type is each Map value?** `Optional<T>`.
4. **Does a nonexistent group automatically appear with the reducer's identity?** No; `groupingBy` creates keys only for elements seen by the classifier.
5. **If a group has elements but downstream `filtering` rejects all of them, what does the no-identity `reducing` form return?** `Optional.empty()`.
6. **What about the same case if the reducer has identity `0`?** The group's value is `0` (when the identity is 0 and the combining op is compatible).
7. **Why is `BigDecimal.ZERO` a reasonable identity when summing same-currency revenue?** Because adding 0 does not change the numeric value of the sum.
8. **Why not use subtraction to merge summaries when parallelism is needed?** Subtraction is not associative and generally lacks a suitable two-sided identity.
9. **In `reducing(identity, mapper, op)`, does the mapper receive Order or Summary?** It receives Order (the input element) and returns Summary or the corresponding `U` type.
10. **What does `groupingBy(..., TreeMap::new, reducing(...))` change?** Map key iteration order; it does not change how the reducer computes each group's value.
11. **When you only need order count per region, which form is shorter?** `groupingBy(Order::region, counting())`.
12. **When a result needs two independent metrics, what tool replaces manually writing a record merge?** `Collectors.teeing` combining two downstreams.
13. **Does `groupingByConcurrent` guarantee source element order inside each group?** No; it is a concurrent, unordered collector.
14. **Why not use a mutable `StringBuilder` as the identity in `reducing`?** It breaks value-based accumulation assumptions; use a dedicated collector like `joining` for string concatenation.
15. **How do you verify a reducer is correct on a parallel stream?** Check identity, associativity, value domain, empty groups, and compare sequential vs. parallel results on representative datasets.

**Key takeaway:** `Collectors.reducing` enables **direct per-group aggregation** when used as a downstream of `groupingBy`. The no-identity form yields `Optional`; the identity form yields the value directly; the mapper form helps combine `Order` into revenue or immutable summaries. Choose an operation with a valid identity and associativity, distinguish missing keys from filtered-empty groups, and evaluate specialized collectors and parallel overhead before optimizing.
