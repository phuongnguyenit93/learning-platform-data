# Checking Associativity and Order Effects in Merge Functions

When collecting a Stream into a `Map<K, V>` using `Collectors.toMap`, two input elements can produce the **same key**. At that point, the `merge` function decides whether to keep, replace, or combine the two values. A merge function that appears correct when run sequentially may still produce a different result if the Stream is split into multiple chunks and merged in parallel. To design it properly, you must distinguish **associativity**, **commutativity**, and **encounter order**.

This lesson belongs to the **Collecting to Maps** chapter of the **JAVA_STREAM_API** module. It builds upon declarative programming with lazy pipelines, `filter`, `map`, `reduce`, `collect`, and collectors such as `groupingBy`. Understanding merge functions also helps when writing custom collectors, evaluating parallel processing via `Spliterator`, and recognizing limits around state, performance, resources, and precision.

## 1. When Does toMap Call the Merge Function?

In Java 8+, a common overload of `Collectors.toMap` has the signature:

```java
static <T, K, U> Collector<T, ?, Map<K, U>> toMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction)
```

The parameters mean:

| Parameter | Role | Example |
|---|---|---|
| `keyMapper` | Extracts the key from each input element | `Order::getCustomerId` |
| `valueMapper` | Extracts the value to place in the Map | `Order::getAmount` |
| `mergeFunction` | Combines the **old value** and **new value** when two elements have duplicate keys | `BigDecimal::add` |

`mergeFunction` has type `BinaryOperator<U>`: it accepts two values of type `U` and returns one value of type `U`. In the common case, think of it by the rule:

```text
Existing in Map: K -> oldValue
New element:     K -> newValue
                      |
                      v
K -> mergeFunction(oldValue, newValue)
```

If the key is not yet present, the value is inserted into the Map without merging against an old value. If two elements have different keys, `mergeFunction` does not need to be invoked for that pair.

### 1.1. Omitting mergeFunction when duplicate keys exist

The overload `toMap(keyMapper, valueMapper)` **throws `IllegalStateException` on duplicate keys** by default.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("apple", "apricot", "banana");

// Wrong if the requirement allows multiple words with the same initial letter.
// Both "apple" and "apricot" produce key "a".
Map<String, String> byFirstLetter = words.stream()
        .collect(Collectors.toMap(
                word -> word.substring(0, 1),
                word -> word));
// IllegalStateException when encountering duplicate key "a".
```

If the data truly requires each key to be unique, this error is useful because it catches data violating the rule. If **duplicate keys are valid**, define an explicit merge policy:

```java
Map<String, String> firstWordByLetter = words.stream()
        .collect(Collectors.toMap(
                word -> word.substring(0, 1),
                word -> word,
                (oldValue, newValue) -> oldValue));

System.out.println(firstWordByLetter.get("a")); // apple
```

In this sequential example, when `"apricot"` arrives after `"apple"`, merging keeps the old value `"apple"`. This is a valid policy, though it has an **input-order dependency**.

## 2. Associativity Is the Core Requirement of Merging

A merge operation `f(a, b)` is **associative** when:

\[
f(f(a,b),c)=f(a,f(b,c))
\]

Simply put: **for the same sequence of values, changing the parenthesization when merging does not change the result**. This is essential so that combining partial collector results yields the same meaning as sequential processing. With a parallel Stream, the library is allowed to accumulate elements across multiple branches and then call the combiner to merge branch Maps.

Suppose three orders share the product code `P01` with quantities `2, 3, 4`. The merge function is addition:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Integer> quantityBySku =
        Arrays.asList(2, 3, 4).stream()
                .collect(Collectors.toMap(
                        quantity -> "P01",
                        quantity -> quantity,
                        Integer::sum));

System.out.println(quantityBySku.get("P01")); // 9
```

With addition, both `(2 + 3) + 4` and `2 + (3 + 4)` equal `9`. Thus, grouping does not alter the meaning of the sum (with separate caveats regarding numeric range, overflow, and floating-point arithmetic).

### 2.1. A non-associative merge: pairwise averaging

This is a common bug when trying to "compute the average per key":

```java
// WRONG when used as an overall average for multiple duplicate-key elements.
Map<String, Double> wrongAverage =
        Arrays.asList(10, 20, 40).stream()
                .collect(Collectors.toMap(
                        value -> "P01",
                        value -> value.doubleValue(),
                        (a, b) -> (a + b) / 2.0));

System.out.println(wrongAverage.get("P01")); // 27.5 in this order.
```

Consider the two ways of parenthesizing:

```text
f(f(10, 20), 40) = f(15, 40) = 27.5
f(10, f(20, 40)) = f(10, 30) = 20.0
Correct average: (10 + 20 + 40) / 3 = 23.333...
```

Not only is it non-associative, this approach also **fails to compute the true overall average**, even when run sequentially. If the Stream is split into different chunks, the merged result can change as well.

**The right way** is to maintain both **sum and element count** in the accumulation state, then divide once after merging. You can use `groupingBy(..., averagingInt(...))` or a collector storing a `(sum, count)` pair; you cannot compute a true weighted average solely by merging group averages without retaining group sizes.

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Double> correctAverage =
        Arrays.asList(10, 20, 40).parallelStream()
                .collect(Collectors.groupingBy(
                        value -> "P01",
                        Collectors.averagingInt(Integer::intValue)));

System.out.println(correctAverage.get("P01"));
// 23.333333333333332 (approximate double representation).
```

### 2.2. Subtraction is also non-associative

```java
java.util.function.BinaryOperator<Integer> subtraction =
        (a, b) -> a - b;

System.out.println(subtraction.apply(
        subtraction.apply(20, 5), 3)); // 12
System.out.println(subtraction.apply(
        20, subtraction.apply(5, 3))); // 18
```

Avoid using subtraction or division as a `mergeFunction` for an aggregation whose result must be independent of partitioning. If the business logic genuinely requires sequential event-by-event updates, model order and state explicitly rather than implicitly relying on a non-associative merge.

## 3. Associativity Differs from Commutativity: Valid Yet Order-Dependent

A merge operation is **commutative** when `f(a,b) = f(b,a)`. Commutativity and associativity are **two different properties**.

| Merge function | Associative? | Commutative? | Consequence |
|---|---|---|---|
| `Integer::sum` | Yes under Java `int` addition | Yes | Result is permutation-invariant, though `int` can overflow |
| `BigDecimal::add` | Yes for standard exact decimals | Yes numerically | Sound for summing money when non-null values are used |
| `(oldValue, newValue) -> oldValue` | Yes | No | Keeps the first-seen element under a defined order |
| `(oldValue, newValue) -> newValue` | Yes | No | Keeps the last-seen element under a defined order |
| `(a, b) -> a + "|" + b` | Yes | No | Ordered string concatenation; reversing elements reverses string order |
| `(a, b) -> (a + b) / 2.0` | No | Expression-symmetric, aside from special values | Result varies with partitioning |
| `(a, b) -> a - b` | No | No | Easily diverges in parallel pipelines |

Example testing the two value-selection merges:

```java
import java.util.function.BinaryOperator;

BinaryOperator<String> keepFirst = (oldValue, newValue) -> oldValue;
BinaryOperator<String> keepLast  = (oldValue, newValue) -> newValue;

System.out.println(keepFirst.apply(
        keepFirst.apply("A", "B"), "C")); // A
System.out.println(keepFirst.apply(
        "A", keepFirst.apply("B", "C"))); // A

System.out.println(keepLast.apply(
        keepLast.apply("A", "B"), "C"));  // C
System.out.println(keepLast.apply(
        "A", keepLast.apply("B", "C")));  // C

System.out.println(keepFirst.apply("A", "B")); // A
System.out.println(keepFirst.apply("B", "A")); // B
```

**Conclusion on first/last wins:** both operators are associative. They **do not need to be commutative** to be valid when merging segments in encounter order. However, once a defined encounter order is absent, they **cannot guarantee** which business value is "first" or "last".

## 4. How Does Encounter Order Affect Merge Results?

**Encounter order** is the element order prescribed by the source and pipeline. `List.stream()` has encounter order matching list positions. `HashSet.stream()` has no guaranteed encounter order. Calling `unordered()` can relax ordering constraints, giving the library more execution freedom.

Suppose updates arrive for the same code `P01` in order:

```text
Event 1: P01 -> "draft"
Event 2: P01 -> "approved"
Event 3: P01 -> "delivered"
```

When collecting **sequentially on a List in that exact order**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> statuses = Arrays.asList(
        "draft", "approved", "delivered");

Map<String, String> first = statuses.stream()
        .collect(Collectors.toMap(
                status -> "P01",
                status -> status,
                (oldValue, newValue) -> oldValue));

Map<String, String> last = statuses.stream()
        .collect(Collectors.toMap(
                status -> "P01",
                status -> status,
                (oldValue, newValue) -> newValue));

System.out.println(first.get("P01")); // draft
System.out.println(last.get("P01"));  // delivered
```

The result changes if **the input order is reversed**. That does not mean `mergeFunction` lacks associativity; it means **the semantics of the selection depend on order**, just like "pick first/last record".

With an **ordered** Stream and an appropriate collector, merging segments must still respect the collector's ordering semantics; yet you should not treat the order of **invocations** of `mergeFunction` as a stable programming interface for logging or mutating external variables. When switching to an unordered source, calling `unordered()`, or using a concurrent/unordered collector, do not rely on `keepFirst`/`keepLast` to determine the business-wise "latest record".

### 4.1. Entry order in the Map is a separate issue

Default `Collectors.toMap(...)` **makes no guarantees** about the concrete Map type or `entrySet()` iteration order. Selecting a value via a merge rule does not mean Map keys will print in appearance order.

If a policy for **key order in the result** is needed, use the four-argument overload:

```java
Map<String, String> byInsertionOrder = statuses.stream()
        .collect(Collectors.toMap(
                status -> status.substring(0, 1),
                status -> status,
                (oldValue, newValue) -> oldValue,
                java.util.LinkedHashMap::new));
```

In this **sequential** example, `LinkedHashMap` preserves insertion order of distinct keys. `TreeMap::new` fits when you want keys sorted by natural order or a configured comparator. **The Map supplier only determines how keys are stored/iterated**; it does not make `mergeFunction` associative or define "latest" among records sharing the same key.

## 5. When an Order-Invariant Result Is Needed: Select by Comparison Rule

In transactional data, "latest record" should usually be defined by **timestamp or version number**, not an incidental position in a Stream. Given two events with the same key, pick the one with the higher version; on equal versions, use a unique secondary key to break ties.

```java
import java.util.Comparator;
import java.util.function.BinaryOperator;

Comparator<Event> byVersionThenId =
        Comparator.comparingLong(Event::getVersion)
                .thenComparing(Event::getEventId);

BinaryOperator<Event> chooseLatest =
        BinaryOperator.maxBy(byVersionThenId);
```

This snippet assumes an `Event` type with non-null `getVersion()` and `getEventId()`, and a comparator establishing a consistent ordering. `maxBy` merges two events by picking the greater one according to the comparator; if the secondary key uniquely identifies a maximum, permuting the source will not change the chosen event.

If only version is compared and multiple records share the same version, the result can still depend on tie-breaking. Adding `eventId` (or another business rule) uniquely identifies a winning record. Choosing the "highest version" is not equivalent to "last-appearing record".

## 6. Complete Java 8 Example: Summing Totals and Selecting Records by Key

The following example models sales lines. A product code may appear multiple times with different amounts, priorities, and update timestamps. We compute **total amount per code** and select **the record with the highest priority, then the latest timestamp**, both via appropriate merge functions.

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class MapMergeContractsDemo {
    static final class Sale {
        private final String sku;
        private final String ticket;
        private final BigDecimal amount;
        private final int priority;
        private final long receivedAt;

        Sale(String sku, String ticket, String amount,
                int priority, long receivedAt) {
            this.sku = sku;
            this.ticket = ticket;
            this.amount = new BigDecimal(amount);
            this.priority = priority;
            this.receivedAt = receivedAt;
        }

        String getSku() {
            return sku;
        }

        String getTicket() {
            return ticket;
        }

        BigDecimal getAmount() {
            return amount;
        }

        int getPriority() {
            return priority;
        }

        long getReceivedAt() {
            return receivedAt;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
                new Sale("P01", "A-old",  "12.50", 1, 100),
                new Sale("P02", "B-only", "7.25",  3, 150),
                new Sale("P01", "A-new",  "2.75",  4, 130),
                new Sale("P01", "A-mid",  "10.00", 4, 120)
        );

        // BigDecimal.add: adds monetary amounts accurately in decimal.
        Map<String, BigDecimal> totalBySku = sales.parallelStream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getAmount,
                        BigDecimal::add));

        System.out.println(totalBySku.get("P01")); // 25.25
        System.out.println(totalBySku.get("P02")); // 7.25

        // Tie-break by timestamp, then ticket for a deterministic maximum.
        Comparator<Sale> byPriorityTimeTicket =
                Comparator.comparingInt(Sale::getPriority)
                        .thenComparingLong(Sale::getReceivedAt)
                        .thenComparing(Sale::getTicket);

        Map<String, Sale> chosenBySku = sales.parallelStream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Function.identity(),
                        BinaryOperator.maxBy(byPriorityTimeTicket)));

        System.out.println(chosenBySku.get("P01").getTicket());
        // A-new (same priority=4, but receivedAt=130 is greater than 120)

        // Input-order policy is expressed clearly when running sequentially.
        Map<String, String> firstBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getTicket,
                        (oldValue, newValue) -> oldValue,
                        LinkedHashMap::new));

        Map<String, String> lastBySku = sales.stream()
                .collect(Collectors.toMap(
                        Sale::getSku,
                        Sale::getTicket,
                        (oldValue, newValue) -> newValue,
                        LinkedHashMap::new));

        System.out.println(firstBySku.get("P01")); // A-old
        System.out.println(lastBySku.get("P01"));  // A-mid
        System.out.println(firstBySku.keySet());   // [P01, P02]
    }
}
```

**Reading the output:**

- The total for `P01` is `12.50 + 2.75 + 10.00 = 25.25`; decimal addition does not depend on the recording order of rows in the example.
- The winner by **priority and receivedAt** is `A-new`; this differs from `A-mid`, which is the last record in the list.
- `keepFirst` and `keepLast` offer two valid order-based selection rules, yet cannot replace "latest by time" if the list may be reordered or assembled from different sources.
- `LinkedHashMap` gives both sequential Maps the key order `[P01, P02]`. That is a **Map iteration order** policy, distinct from the **value-merging** policy for duplicate keys.

For monetary totals, prefer `BigDecimal` or the smallest currency unit with a safe range. `int`/`long` addition can overflow; `double` addition introduces rounding errors and can yield bitwise-different results depending on merge order even though real-number addition is mathematically associative.

## 7. Self-Testing Associativity and Order with Small Expressions

Before putting a `mergeFunction` into a pipeline, test at least three values `a`, `b`, `c` and compare **the two parenthesizations of the merge**.

### 7.1. A function that is associative yet still order-sensitive

```java
import java.util.function.BinaryOperator;

BinaryOperator<String> concatenate =
        (left, right) -> left + "|" + right;

String groupLeft = concatenate.apply(
        concatenate.apply("A", "B"), "C");
String groupRight = concatenate.apply(
        "A", concatenate.apply("B", "C"));
String reversed = concatenate.apply("B", "A");

System.out.println(groupLeft);  // A|B|C
System.out.println(groupRight); // A|B|C
System.out.println(reversed);   // B|A
```

String concatenation is **associative**, so splitting `["A", "B", "C"]` into branches and merging in the same order yields the same result. However, it is not commutative: swapping element order changes the string. If you truly want a set of values independent of order, collect into a `Set` or sort values before joining, depending on business needs.

### 7.2. A function that fails associativity

```java
BinaryOperator<Double> pairAverage = (a, b) -> (a + b) / 2.0;

double leftGrouped =
        pairAverage.apply(pairAverage.apply(10.0, 20.0), 40.0);
double rightGrouped =
        pairAverage.apply(10.0, pairAverage.apply(20.0, 40.0));

System.out.println(leftGrouped);  // 27.5
System.out.println(rightGrouped); // 20.0
```

If the two groupings produce different results on meaningful inputs, `mergeFunction` fails the requirements of a splittable aggregation.

### 7.3. Testing on duplicate-key datasets

A small test suite should cover:

1. **Empty source**: `collect(toMap(...))` returns an empty Map; `mergeFunction` has no data to invoke on.
2. **One value per key**: no key collisions; tests `keyMapper`/`valueMapper` only.
3. **Two or three duplicate-key values**: explicitly tests old/new rules and associativity.
4. **Interleaved keys** (e.g. `P01, P02, P01, P02`): checks that each key aggregates independently.
5. **Reversed input order**: confirms which cases are allowed to change and which must remain invariant.
6. **Sequential vs. parallel**: compare Map values rather than only `entrySet` print order; if a discrepancy appears, inspect the merge logic and data before blaming the runtime.

Testing on a few samples only helps catch bugs; **it does not prove** an operation is associative for all inputs. Whenever possible, reason from mathematical properties and business rules.

## 8. toConcurrentMap and Parallel Execution: When Is Order No Longer Appropriate?

`Collectors.toConcurrentMap` creates a concurrent, unordered collector. When elements with the same key accumulate concurrently, the order in which they merge can depend on execution scheduling. **Do not use "keep old" or "keep new" to implicitly select records by time** in this kind of collector.

```java
import java.math.BigDecimal;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, BigDecimal> totals = sales.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Sale::getSku,
                Sale::getAmount,
                BigDecimal::add));
```

The snippet above uses the `sales` list and `Sale` class from the complete example. `BigDecimal::add` fits monetary summation semantics, so it works in both `toMap` and `toConcurrentMap` given valid inputs. Conversely, a "first wins" policy is meaningful only when **"first" is defined**, whereas `toConcurrentMap` provides no encounter order to interpret "first" relative to the input list.

| Scenario | Choice |
|---|---|
| Every merge must yield the same sum or deterministic maximum | Associative merge function; if order is not guaranteed, pick a permutation-invariant rule |
| Want first/last value from an ordered List | Establish encounter order; use `toMap` on an ordered pipeline and avoid dropping ordering |
| Want to optimize parallel collection without needing order | Consider `toConcurrentMap` with a concurrency-safe merge |
| Need to group all values per key instead of picking one | `groupingBy` or `groupingByConcurrent` with a suitable downstream collector |
| Need Map keys displayed in order | Choose `LinkedHashMap` or `TreeMap` as required; do not rely on default Map |

**Performance note:** `toMap` on a parallel stream may have to merge intermediate Maps, incurring overhead. `toConcurrentMap` can avoid some merging overhead via concurrent updates, yet is not automatically faster in all scenarios: many values hitting the same key can cause contention. Switch only when ordering is genuinely unneeded and after benchmarking on representative data.

## 9. Special Cases of Map.merge

Collectors rely on per-key value merging. Therefore, understand these additional limits:

### 9.1. Null values and null merge results

`Map.merge(key, value, remappingFunction)` does not accept a null input `value`. Thus, if `toMap`'s `valueMapper` returns null, the collector typically throws `NullPointerException` instead of treating null as "no value". Filter or normalize data before collecting.

```java
Map<String, String> byCode = sales.stream()
        .filter(sale -> sale.getTicket() != null)
        .collect(Collectors.toMap(
                Sale::getSku,
                Sale::getTicket,
                (oldValue, newValue) -> newValue));
```

If **`mergeFunction` itself returns null**, `Map.merge` has the semantics of **removing the mapping for that key**. For example, colliding on two values could delete the key, and then a subsequent element could re-insert a new key. This differs from "skip invalid values", and easily makes results depend on how the Stream is split and merged. If the goal is dropping invalid records, use `filter` before `collect`.

For null keys, Map implementations have varying contracts. Do not rely on null-key behavior observed accidentally from a default Map; in particular, `ConcurrentHashMap` and natural-ordered `TreeMap` reject null keys. It is best to normalize or exclude null keys per business rules before collecting.

### 9.2. Side effects in mergeFunction

`mergeFunction` can be called multiple times and may be invoked as the collector combines branch results. Do not use it to increment an external counter, send transactions, call external APIs, or mutate source data:

```java
// Avoid mutating a shared mutable variable inside mergeFunction,
// especially when the pipeline runs in parallel.
// (oldValue, newValue) -> {
//     externalCounter++;
//     return oldValue + newValue;
// }

// Prefer expressing a pure merge:
java.util.function.BinaryOperator<Integer> add = Integer::sum;
```

Do not use side effects in `mergeFunction` to count records: invocations can happen across different merge stages and on different workers; if merging deletes keys by returning null, inferring record counts from call counts is even more error-prone. To **count records per key**, use `groupingBy(..., counting())` or merge a count of `1` directly per element.

```java
Map<String, Long> countBySku = sales.parallelStream()
        .collect(Collectors.toMap(
                Sale::getSku,
                sale -> 1L,
                Long::sum));

System.out.println(countBySku.get("P01")); // 3
```

### 9.3. Floating-point precision and numeric overflow

`double` addition is not **bitwise** associative due to rounding errors. For example, `(1e16 + -1e16) + 1` can differ from `1e16 + (-1e16 + 1)`. When results must be stable and exact for currency, use `BigDecimal` for decimal amounts or integers in the smallest currency unit within safe bounds. Integer addition is associative under Java's overflow semantics, yet the resulting sum may no longer match the desired mathematical value; do not mistake order invariance for overflow safety.

## 10. Common Pitfalls and How to Fix Them

| Pitfall | Consequence | Fix |
|---|---|---|
| `toMap(key, value)` when duplicate keys exist | `IllegalStateException` | Enforce unique keys or supply a `mergeFunction` |
| `(a, b) -> (a + b) / 2` to compute an average | Non-associative, wrong average | Accumulate sum and count; use `averaging...` |
| `(a, b) -> a - b` | Depends on partitioning and order | Redesign as an associative aggregation |
| Using `keepFirst`/`keepLast` after `unordered()` | Retained record may be business-nondeterministic | Establish order or pick by version/time with tie-breaking |
| Using `toConcurrentMap` to find the "last record" | Worker order is not event order | Select max by timestamp/version with a tie-breaker |
| Trusting `HashMap` traversal order as input order | Output order may change | Use `LinkedHashMap`/`TreeMap` as appropriate |
| `valueMapper` returns null | Fails during collection | Filter or normalize beforehand |
| Merge returns null to "skip" | May delete keys and produce unexpected results | Use `filter` for skipping policies |
| Merge mutates a shared variable | Data races, unpredictable side effects | Write a pure function; collect counts/sums as values |
| Using `int`/`double` for precision-sensitive currency | Overflow or rounding error | Use `BigDecimal` or a controlled numeric range |

## 11. Self-Check Exercises with Answers

### Exercise 1. Checking keep-old merge

```java
java.util.function.BinaryOperator<String> f = (a, b) -> a;
```

Compare `f(f("A", "B"), "C")` and `f("A", f("B", "C"))`. Then swap `"A"` and `"B"`.

**Answer:** Both parenthesizations return `"A"`, so the operator is associative; `f("A", "B")` returns `"A"` while `f("B", "A")` returns `"B"`, so it is not commutative.

### Exercise 2. Pairwise averaging

Given values `10, 20, 40` sharing the same key, does merging with `(a, b) -> (a + b) / 2` compute the right average?

**Answer:** No. Left-first grouping gives `27.5`, right-first grouping gives `20.0`; the true average is about `23.333...`. Keep `sum` and `count` or use downstream `averagingInt`.

### Exercise 3. Last record vs. latest record

Three events sharing code `P01` have timestamps `100, 130, 120` in sequence. If selected with `(oldValue, newValue) -> newValue` on a sequential Stream in this order, which timestamp results? What if the latest timestamp is needed?

**Answer:** Keep-last picks `120` because it appears last. To get the latest timestamp `130`, pick the maximum by timestamp (with a tie-breaker if ties are possible).

### Exercise 4. Map key order and merge order

Does `Collectors.toMap(..., LinkedHashMap::new)` automatically make a non-associative `mergeFunction` correct on a parallel stream?

**Answer:** No. `LinkedHashMap` only provides a key insertion-order policy. Associativity of merged values is an independent requirement.

### Exercise 5. Can a non-commutative merge be used in toMap?

**Answer:** Yes, when the merge is associative and the business logic has an order to preserve. For example, `(a, b) -> a + "|" + b` is associative but not commutative. Without an encounter order, string concatenation results can change order.

### Exercise 6. Summing counts by key

Given rows with codes `A, B, A, A`, which merge function can be used with `toMap` to count elements per code?

```java
Map<String, Long> counts = codes.stream()
        .collect(Collectors.toMap(
                code -> code,
                code -> 1L,
                Long::sum));
// A -> 3, B -> 1
```

The snippet assumes `codes` is a `List<String>` containing non-null `"A", "B", "A", "A"`. Because count addition is associative and commutative, the result is independent of code order.

## 12. Principles for Designing a Correct mergeFunction

Before using `Collectors.toMap` or `toConcurrentMap` on data with duplicate keys, determine: **why keys may collide**, **whether the desired output is a sum, a selected element, or all elements**, **whether the merge operation is associative**, **whether input order changes the meaning of the result**, and **whether the output Map needs a specific key order**. For order-dependent merges, establish encounter order and avoid losing that constraint; for order-independent merges, design deterministic selection rules or appropriate commutative aggregations. Test empty inputs, duplicate keys, reversed orderings, parallel execution, and numeric bounds to ensure the final result truly matches business requirements.
