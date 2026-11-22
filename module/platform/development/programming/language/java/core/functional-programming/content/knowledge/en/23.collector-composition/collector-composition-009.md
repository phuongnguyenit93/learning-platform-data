# Composing Collectors Clearly and Avoiding Deeply Nested Structures in Java

## 1. Goal: Making the Meaning of Each Collector Level Clear

In the Java Stream API, `Collectors.groupingBy()`, `mapping()`, `filtering()`, `flatMapping()`, `collectingAndThen()`, `teeing()`, and statistical collectors can be **nested** to compute many kinds of reports. However, a collector expression that is valid at the type level is not necessarily **easy to read, easy to test, and easy to maintain**.

For example, to build a map of `region → list of paid product names`, you could write everything in a single expression:

```java
Map<String, List<String>> result = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.toList()))));
```

This is a **snippet inside a method body**; it uses the `Sale` record and the imports shown in the complete program in section 6. The code **may be correct**, but it forces the reader to trace multiple pairs of parentheses to recognize three separate goals:

1. **Group** by `region`.
2. **Within each group**, select only `Sale` elements with `paid == true`.
3. **Transform** each `Sale` into `product` and collect into a `List`.

If extended to also include total amount, count, list of names, priority level, and multiple grouping levels, the expression becomes deeper and harder to pinpoint where a bug comes from.

The goal is not to forbid nesting collectors. The goal is that **each level must have an easily expressible responsibility**, and when logic has a clear business name, it should be extracted into a variable/method or an appropriate result data type.

## 2. Understanding Collectors Before Composing Them

`Collector<T,A,R>` represents a rule for **accumulating** elements of type `T`, with an internal accumulation state `A`, to produce a result of type `R`. In typical applications, `A` is an implementation detail, so many examples declare `Collector<T, ?, R>`.

For example:

```java
Collector<Sale, ?, Long> countSales = Collectors.counting();
Collector<Sale, ?, Integer> sumAmount =
        Collectors.summingInt(Sale::amount);
```

These are two statements in a class that has the `Sale` record and imports `java.util.stream.Collector`, `Collectors`. `counting` produces a `Long` counting the number of elements; `summingInt` sums an `int` property into an `Integer` (and can overflow `int` if the data is large).

Some collectors have easy-to-visualize **inputs/outputs**:

| Collector | Meaning | Typical result type |
| --- | --- | --- |
| `toList()` | Collects elements | `List<T>` |
| `counting()` | Counts elements | `Long` |
| `summingInt(mapper)` | Sums integer values from each element | `Integer` |
| `mapping(mapper, downstream)` | Changes element type before passing down to the downstream collector | Result of `downstream` |
| `filtering(predicate, downstream)` | Passes only elements matching the condition down to the downstream collector | Result of `downstream` |
| `groupingBy(classifier, downstream)` | Groups elements and then collects per group | `Map<K,D>` |
| `collectingAndThen(downstream, finisher)` | Transforms the final result of the downstream collector | Return type of `finisher` |
| `teeing(down1, down2, merger)` | Computes two collector results in parallel conceptually and then combines them | Return type of `merger` |

Read collectors by following the **data flow**. An expression like `groupingBy(region, mapping(name, toList()))` means: `Sale` elements are grouped by `region`, and then within each group, **names** are collected into a `List`.

Do not confuse downstream `mapping` with upstream `Stream.map`. They can produce the same result in some situations, but **the order of operations and how groups are preserved** can differ, especially when `filtering` is added.

## 3. Signs That a Collector Is Nested Too Deeply

There is no maximum nesting depth that Java or Javadoc prescribes as “correct.” The issue is **cognitive load**: if a reader has to count many parentheses and manually infer all generic types just to understand the business rule, you should consider extracting it.

Notable warning signs:

- `collect(...)` spans dozens of lines with multiple downstream collectors and unnamed lambdas.
- The same `filtering(..., mapping(..., toList()))` combination is duplicated across multiple reports.
- The result type becomes `Map<String, Map<String, Map<String, List<...>>>>` while the end user only needs a few report columns.
- Multiple business conditions, string conversions, access checks, and exception handling are buried inside `keyMapper`, `valueMapper`, or `merger`.
- Changing a filter condition makes it unclear which groups are **dropped** and which remain with empty values.
- It is hard to write a unit test for a small transformation without running the entire pipeline.
- The returned result is a nested map that is awkward to use, whereas a record would express the meaning much better.
- There are too many `get(...).get(...).get(...)` chains at call sites, making `null` errors likely and domain data types missing.

A practical rule of thumb: if you cannot give a concise name to each level of the collector, you should split it or reconsider the result model. Conversely, `groupingBy(Category::id, counting())` is very concise and **does not need to be mechanically extracted** just to avoid nesting.

## 4. Approach 1: Naming Downstream Collectors

Instead of always writing the full expression inline:

```java
Map<String, List<String>> paidProducts = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.toList()))));
```

Give meaningful logic a name:

```java
static Collector<Sale, ?, List<String>> paidProductNames() {
    return Collectors.filtering(
            Sale::paid,
            Collectors.mapping(Sale::product, Collectors.toList()));
}
```

Then use it:

```java
Map<String, List<String>> paidProducts = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region, TreeMap::new, paidProductNames()));
```

These two snippets are **extracted from the class and method structure** in the `ReadableCollectorDemo.java` program below; when integrating into an application, the `Sale` record and corresponding imports are required.

This approach improves several aspects:

1. The `groupingBy` call reads almost like a plain English sentence: “group by region, collect paid product names.”
2. The filtering and mapping logic can be tested independently.
3. The name `paidProductNames` expresses business intent without forcing the caller to read the `filtering(mapping(...))` details.
4. When the payment policy changes, you update it in one place.
5. The type `Collector<Sale, ?, List<String>>` accurately describes the contract: accepts `Sale`, produces a `List` of `String`.

**Generics note:** the `?` for the accumulation parameter `A` is intentional. Do not try to “guess” the internal state type of `Collectors.mapping`, because that type is usually not a business detail you should care about.

## 5. filter() Before groupingBy() Differs from filtering() Inside groupingBy()

This is an important semantic difference, not just a matter of code formatting.

**Approach A — filter before grouping:**

```java
Map<String, List<String>> filteredFirst = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.mapping(Sale::product, Collectors.toList())));
```

**Approach B — group first, filter downstream:**

```java
Map<String, List<String>> downstreamFiltered = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(Sale::product, Collectors.toList()))));
```

Both snippets assume `sales: List<Sale>` and the appropriate imports. In the dataset of the complete program, the `West` region has only one **unpaid** `Sale`.

Output:

```text
filteredFirst={North=[A, C], South=[E]}
downstreamFiltered={North=[A, C], South=[E], West=[]}
```

Explanation:

- In **Approach A**, the `West` record is discarded **before** a group entry is created, so the map **does not contain the `West` key**.
- In **Approach B**, the `Sale::region` classifier creates/identifies the `West` group first, and the downstream `filtering` adds no `Sale` into the `List`, so `West=[]`.

Similarly, `groupingBy(region, filtering(paid, counting()))` can preserve `West=0`. This matters in dashboards and reports: “a group with 0 paid sales” is different from “a group that does not exist at all.”

Do not replace `Collectors.filtering` with `Stream.filter` just to reduce nesting depth when the business requirement is to **keep groups with empty results**.

## 6. Runnable Example: Extracting Logic into Named Collectors

Save the following content as `ReadableCollectorDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ReadableCollectorDemo {
    record Sale(String region, String product, int amount, boolean paid) {}

    static Collector<Sale, ?, List<String>> paidProductNames() {
        return Collectors.filtering(
                Sale::paid,
                Collectors.mapping(Sale::product, Collectors.toList()));
    }

    static Collector<Sale, ?, Long> paidCount() {
        return Collectors.filtering(Sale::paid, Collectors.counting());
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "A", 10, true),
                new Sale("South", "B", 20, false),
                new Sale("North", "C", 30, true),
                new Sale("West", "D", 5, false),
                new Sale("South", "E", 40, true),
                new Sale("North", "F", 12, false));

        Map<String, Long> counts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, Collectors.counting()));
        System.out.println("counts=" + counts);

        Map<String, Long> paidCounts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, paidCount()));
        System.out.println("paidCounts=" + paidCounts);

        Map<String, List<String>> paidProducts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, paidProductNames()));
        System.out.println("paidProducts=" + paidProducts);

        Map<String, List<String>> filteredFirst = sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(Sale::region,
                        TreeMap::new,
                        Collectors.mapping(Sale::product, Collectors.toList())));
        System.out.println("filteredFirst=" + filteredFirst);

        Collector<Sale, ?, Integer> sumAmount =
                Collectors.summingInt(Sale::amount);
        Map<String, Integer> sums = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, sumAmount));
        System.out.println("sums=" + sums);
    }
}
```

Compile and run with Java 17:

```bash
javac --release 17 -encoding UTF-8 ReadableCollectorDemo.java
java ReadableCollectorDemo
```

Exact output from the tested program:

```text
counts={North=3, South=2, West=1}
paidCounts={North=2, South=1, West=0}
paidProducts={North=[A, C], South=[E], West=[]}
filteredFirst={North=[A, C], South=[E]}
sums={North=52, South=60, West=5}
```

Details:

- `counts` uses downstream `counting()` to count **all** `Sale` items by region.
- `paidCounts` uses a named collector `paidCount()`, producing `West=0` because the `West` group was created by `groupingBy`.
- `paidProducts` uses `paidProductNames()`, keeping `West=[]`.
- `filteredFirst` places `filter` before grouping, so `West` is absent.
- `sums` uses a separate `sumAmount` collector variable to express another aggregation criterion. The example uses small values so `int` does not overflow; for totals that can exceed `int`, choose another sum type according to the business domain.

`TreeMap::new` ensures the output is ordered by keys `North`, `South`, `West`. Using `HashMap`/the default overload may work correctly for mapping, but **does not guarantee the print order** shown in this example.

## 7. Approach 2: Using a Record Instead of Multi-Level Maps

A common design mistake is turning every data axis into a nested `Map`:

```text
Map<Region, Map<Status, Map<Product, List<Sale>>>>
```

This structure is not always wrong. It fits if the caller genuinely needs to query by **three key levels**. However, if the screen only displays:

```text
Region | Paid orders | Total value
North  | 2           | 52
South  | 1           | 60
West   | 0           | 5
```

then `Map<String, RegionSummary>` is usually easier to use:

```java
record RegionSummary(long paidCount, int amountTotal) {}
```

This is the record declaration in the `StructuredCollectorDemo` class in section 10. Callers can read `summary.paidCount()`, `summary.amountTotal()` instead of `map.get("paid").get(...)`. The compiler checks field names/types at compile time.

A **record**:

- Names the meaning and type of each metric.
- Allows changing the calculation inside the collector without forcing callers to know a nested `Map` structure.
- Makes it easy to write tests like `assertEquals(new RegionSummary(2,52), result.get("North"))`.
- Avoids “stringly typed” keys—strings like `"paidCount"` and `"amount"` are easy to mistype and only caught at runtime.

However, a record does not automatically validate all invariants and does not make references to mutable objects in its components deeply immutable. In the example, both components are primitive numbers, so a record is very convenient.

## 8. Approach 3: teeing() for Two Metrics from the Same Source

When you need to compute **two results** from the same group, `Collectors.teeing` (Java 12+) expresses this clearly:

```java
record RegionSummary(long paidCount, int amountTotal) {}

static Collector<Sale, ?, RegionSummary> summaryForRegion() {
    Collector<Sale, ?, Long> paidCount =
            Collectors.filtering(Sale::paid, Collectors.counting());
    Collector<Sale, ?, Integer> amountTotal =
            Collectors.summingInt(Sale::amount);
    return Collectors.teeing(
            paidCount,
            amountTotal,
            RegionSummary::new);
}
```

These declarations are placed in a class with the `Sale` record and imports for `Collector`, `Collectors`. The two downstream collectors have distinct roles:

1. `paidCount`: counts paid `Sale` elements.
2. `amountTotal`: sums `amount` of **all** `Sale` elements in the group, not only paid ones.
3. `RegionSummary::new`: combines the two results into a concrete return type.

Used in `groupingBy`:

```java
Map<String, RegionSummary> byRegion = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region, TreeMap::new, summaryForRegion()));
```

Now the caller immediately sees the result structure `Map<String,RegionSummary>` without having to decipher nested generics. `teeing` does not mean “open two source streams and run the terminal operation twice”: it is **a single collector** combining two downstream collectors under the collection mechanism.

**Do not confuse it with an arbitrary merge operation:** `teeing` takes `downstream1`, `downstream2`, and a `merger` for **the two final results**, rather than a merge function for two elements with the same key like `toMap(..., mergeFunction)`.

## 9. Avoiding Overusing teeing() Everywhere

`teeing` works well when **two metrics genuinely belong to the same report object**; if the metrics are only used on two different screens, you may not need to combine them in the same collector.

When the number of metrics grows to five or ten, multiple levels of `teeing(teeing(...), teeing(...), ...)` will make the code hard to read again. In that case, consider:

- A **custom collector** with a dedicated accumulator/report if multiple related metrics are computed together.
- An intermediate statistics object with clear method names, updated in a single loop.
- Multiple separate computations if the data is small, the source can be traversed again, and that approach is easier to test.
- Grouping the data first and then processing each group into a record, if the computation requires complex logic beyond what downstream collectors can express clearly.

**Do not trade understandability for “a single pipeline” at all costs.** A single pass can be useful for large sources or one-shot I/O, but three clear computations over a small `List` are sometimes safer and easier to maintain than an overly deep collector structure.

## 10. Runnable Example: teeing, collectingAndThen, and Meaningful DTOs

Save the entire following program to `StructuredCollectorDemo.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class StructuredCollectorDemo {
    record Sale(String region, String product, int amount, boolean paid) {}
    record RegionSummary(long paidCount, int amountTotal) {}
    record OverallSummary(long saleCount, int amountTotal) {}

    static Collector<Sale, ?, RegionSummary> summaryForRegion() {
        Collector<Sale, ?, Long> paidCount =
                Collectors.filtering(Sale::paid, Collectors.counting());
        Collector<Sale, ?, Integer> amountTotal =
                Collectors.summingInt(Sale::amount);

        return Collectors.teeing(
                paidCount,
                amountTotal,
                RegionSummary::new);
    }

    static Collector<Sale, ?, Map<String, RegionSummary>> immutableByRegion() {
        Collector<Sale, ?, Map<String, RegionSummary>> grouped =
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, summaryForRegion());
        return Collectors.collectingAndThen(
                grouped, Collections::unmodifiableMap);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "A", 10, true),
                new Sale("South", "B", 20, false),
                new Sale("North", "C", 30, true),
                new Sale("West", "D", 5, false),
                new Sale("South", "E", 40, true),
                new Sale("North", "F", 12, false));

        Map<String, RegionSummary> report =
                sales.stream().collect(immutableByRegion());
        System.out.println("regions=" + report);
        try {
            report.put("Other", new RegionSummary(0, 0));
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable=" + e.getClass().getSimpleName());
        }

        Collector<Sale, ?, OverallSummary> overallCollector =
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::amount),
                        OverallSummary::new);
        System.out.println("overall=" + sales.stream().collect(overallCollector));

        Map<Boolean, List<String>> partitioned = sales.stream().collect(
                Collectors.partitioningBy(Sale::paid,
                        Collectors.mapping(Sale::product, Collectors.toList())));
        System.out.println("unpaid=" + partitioned.get(false));
        System.out.println("paid=" + partitioned.get(true));

        Map<String, List<String>> copied = sales.stream().collect(
                Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.collectingAndThen(
                                        Collectors.toList(), List::copyOf))));
        System.out.println("copiedNorth=" + copied.get("North"));
        try {
            copied.get("North").add("X");
        } catch (UnsupportedOperationException e) {
            System.out.println("listImmutable=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 StructuredCollectorDemo.java
java StructuredCollectorDemo
```

Output verified with `javac --release 17` and `java`:

```text
regions={North=RegionSummary[paidCount=2, amountTotal=52], South=RegionSummary[paidCount=1, amountTotal=60], West=RegionSummary[paidCount=0, amountTotal=5]}
immutable=UnsupportedOperationException
overall=OverallSummary[saleCount=6, amountTotal=117]
unpaid=[B, D, F]
paid=[A, C, E]
copiedNorth=[A, C, F]
listImmutable=UnsupportedOperationException
```

Key parts:

- `summaryForRegion()` builds a `RegionSummary` per group with **two different metrics**.
- `immutableByRegion()` separates the grouping step and the output finalization step. `collectingAndThen(grouped, Collections::unmodifiableMap)` creates a `Map` that does not allow modification through the returned reference.
- `overallCollector` computes two metrics at the **entire list level** and returns `OverallSummary`.
- `partitioningBy(Sale::paid, mapping(...))` splits data by the two `true`/`false` states without needing a multi-level nested `Map`.
- `collectingAndThen(toList(), List::copyOf)` creates an unmodifiable list of values **within each group**; it should only be used when the data satisfies the constraints of `List.copyOf`.

**Note on “immutability”:** `Collections.unmodifiableMap` is an **unmodifiable view** of the backing `Map`; if code still holds a reference to the original `Map` and mutates it, the view will reflect the changes. In this program, the backing `Map` is created inside the collector and is not exposed externally; `RegionSummary` instances are records containing primitives. `List.copyOf` creates an unmodifiable `List` and rejects `null` elements, but if elements are mutable objects, the objects themselves can still be mutated.

## 11. When Should You Use collectingAndThen()?

`Collectors.collectingAndThen(downstream, finisher)` takes the result from the downstream collector and applies a **finishing step**. It helps avoid mixing output normalization logic with per-element accumulation logic:

```java
Collector<String, ?, List<String>> immutableNames =
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf);
```

This declaration can be placed inside a method that imports `Collector`, `Collectors`, `List`. The result is a `List` that disallows adding/removing elements; use it when input data **contains no nulls**, because `List.copyOf` throws `NullPointerException` if any element is `null`.

In multi-group reports, using `collectingAndThen` to convert the result into a clear **final data type** can be better than adding another meaningless `Map` layer.

Consider the composition order carefully:

```text
groupingBy(region, collectingAndThen(toList(), finisher))
→ finisher runs on each group's list

collectingAndThen(groupingBy(region, toList()), finisher)
→ finisher runs on the entire resulting Map
```

Both expressions are only **structural illustrations**, not standalone statements; `region` and `finisher` must be defined in concrete code. This is an important semantic difference: the placement of `collectingAndThen` determines the **scope** of the finishing step.

Do not use a finisher with mandatory business side effects just to avoid an explicit processing step; a terminal collector can execute in a parallel environment, and transaction/idempotency requirements must still be designed separately.

## 12. partitioningBy() Can Be Clearer Than groupingBy(Boolean)

If the requirement is only to split into **two groups based on a boolean**, `partitioningBy(predicate, downstream)` often expresses intent better than grouping by `true`/`false` with `groupingBy`:

```java
Map<Boolean, List<String>> groups = sales.stream().collect(
        Collectors.partitioningBy(
                Sale::paid,
                Collectors.mapping(Sale::product, Collectors.toList())));
```

This is part of the program in section 10. The data produces:

```text
false → [B, D, F]
true  → [A, C, E]
```

By contract, `partitioningBy` provides **both keys** `true` and `false` in the result, even if one side has no elements (producing the downstream output for an empty group). In contrast, `groupingBy(Sale::paid,...)` on data containing only `true` will not automatically create the `false` key.

If an API returning `Map<Boolean,List<...>>` already expresses the structure well, do not turn it into `Map<Boolean, Map<String, List<...>>>` just because you can. Ask whether the caller truly needs **two indexing dimensions** or if returning a record like `PaidUnpaidSummary` would be easier to use.

## 13. map(), filtering(), flatMapping(): Separating Transformation and Grouping

These tools serve different roles:

- **Upstream `Stream.map`** transforms each element **before** grouping, which can lose key information if the type is changed too early.
- **Downstream `Collectors.mapping`** preserves grouping by the original element and then **transforms the element type within each group**.
- **Downstream `Collectors.filtering`** selects elements passed to the child collector **after group keys have been identified**. Therefore, it can retain empty group results.
- **Downstream `Collectors.flatMapping`** converts each element into a small `Stream` and flattens it into the child collector, which is useful when one element has **multiple child values** (for example, multiple labels/tags).

Syntax example for data with a list of tags:

```java
record TaggedSale(String region, List<String> tags) {}
Collector<TaggedSale, ?, List<String>> allTags =
        Collectors.flatMapping(
                sale -> sale.tags().stream(),
                Collectors.toList());
```

This is an **in-class illustration** with `record TaggedSale`; if used standalone, import `List`, `Collector`, `Collectors`. A `TaggedSale` containing three tags contributes **three strings** to the downstream collector; if you only used `mapping(TaggedSale::tags, toList())`, the result would be `List<List<String>>`, adding an unwanted level of nesting.

Do not use `flatMapping` when there is only **one** value to map: `mapping` is clearer. And whether using `flatMapping` or `mapping`, grouping/collecting does not replace a mandatory business side-effect processing step.

## 14. Generics Issues: Do Not Hide Meaning with Casts

Types can look long:

```java
Collector<Sale, ?, Map<String, RegionSummary>> reportCollector =
        immutableByRegion();
```

This is a statement in the `StructuredCollectorDemo` class. This type can help readers understand that **the input is `Sale` and the output is a `Map` of `region` → `RegionSummary`**.

A few best practices:

1. **Extract steps with explicit types:** `Collector<Sale, ?, Long> paidCount`, `Collector<Sale, ?, Integer> amountTotal`, and then use `teeing`.
2. **Prefer method references** for clear getters/classifiers: `Sale::region`, `Sale::paid`, `Sale::amount`.
3. **Avoid raw types** such as `Collector raw` or `(Map) result` to “bypass” generics errors; this easily causes runtime errors.
4. **Use meaningful names:** `summaryForRegion` communicates policy better than `collector3`.
5. When a lambda becomes too complex (null checks, formatting, multiple conditions), extract methods like `normalizeRegion(Sale sale)`, `isBillable(Sale sale)` so they can be tested separately.

The `?` in `Collector<T, ?, R>` does not sacrifice type safety of the input or output data. It only hides the accumulator detail `A` from calling code, which is suitable for methods returning custom collectors.

## 15. When Should You Avoid Creating Nested Maps?

A nested `Map` is useful if you genuinely need queries like **region → department → status → list of events**. But if the immediately following code only computes total count and completed count, a multi-level structure can cause:

- Having to remember the exact key order `region`, `department`, `status`.
- Multiple places handling `null` when a key does not exist.
- Difficulty ensuring groups with no elements still appear.
- Difficulty distinguishing which structure is the **public API** and which is only a collector detail.
- Awkwardness when serializing to JSON or putting into a response DTO.

Three alternative design approaches:

**Use a summary record:** `Map<String,RegionSummary>` gives each region a concrete set of metrics.

**Use a list of report rows:** `List<RegionReportRow>` with `record RegionReportRow(String region, long count, int total) {}` for easy display/filtering/sorting. This is an illustrative record declaration.

**Group once and then process groups with a clear method:** `groupingBy(..., toList())` returns `Map<K,List<T>>`, and then each group is converted into a DTO. This approach may consume additional memory and requires clearly defining its cost, but is sometimes easier to understand than a giant collector tree.

Choose the model based on **how the caller queries the data**, not just on which way takes the fewest lines.

## 16. An Explicit Loop Is Also a Valid Solution

Streams and Collectors are useful, but not every problem needs to be written as a single expression. If the report update rules require step-by-step checks, state logging, and error handling, an explicit loop can be clearer:

```java
Map<String, Long> counts = new TreeMap<>();
for (Sale sale : sales) {
    counts.merge(sale.region(), 1L, Long::sum);
}
```

These statements are placed inside a method that has `Sale`, `sales`, `Map`, `TreeMap`. They express “count the number of `Sale` items in each region” similarly to `groupingBy(Sale::region, TreeMap::new, counting())`.

Advantages of a loop:

- Clear exactly when the map is updated.
- Easy to handle multiple conditional branches and specific errors.
- Easy to set breakpoints and inspect accumulation state.
- Avoids creating deeply nested collectors.

Trade-off: if accumulating multiple metrics, you must ensure the accumulator is correct yourself and may need a more complex mutable structure. For parallel Streams, do not share a mutable `TreeMap` across multiple threads without synchronization; framework-managed collectors handle the combiner according to their contract.

A solution with **fewer parentheses** does not automatically have better algorithmic complexity; consider memory, number of passes, grouping overhead, and scalability.

## 17. Performance Trade-Offs: One collect or Multiple?

In the section 6 program, `sales.stream()` is called multiple times to compute `counts`, `paidCounts`, `paidProducts`, and `sums` **separately**. This is valid because `sales` is a `List` that can create new streams; each stream is consumed only once.

If the data is large or the source is one-shot I/O, traversing the source multiple times can be expensive or impossible. In that case:

- Use `teeing` or a composite collector to compute multiple metrics in **a single terminal operation**.
- Use a custom collector with a specialized accumulator if the number of metrics is large and associativity must be guaranteed.
- Materialize the source in a controlled way if enough memory is available and multiple passes are needed to build different reports.
- Push appropriate filtering/grouping down to the underlying data system when application-side processing is too resource-intensive.

However, **a single `collect`** does not mean “fewest operations”; a collector like `teeing` still allocates and updates two downstream collectors on every element, and `groupingBy` requires a map and accumulators for each group.

Practical rule: start with **business correctness and readability**, measure real performance with a benchmark/profiler when needed, and then optimize **confirmed bottlenecks**. Do not build a six-level nested collector just because you guess it is faster than three clear collections.

## 18. Nulls, Ordering, and Edge Cases

Composed collectors can fail or produce confusing results when edge-case data is not considered.

**Null keys:** `Collectors.groupingBy` does not allow a classifier that returns a `null` key under the implementation/contract used in Java 17; it typically throws `NullPointerException`. Normalize keys to a non-null representation, filter out invalid records, or throw a clear business error.

**Null values:** `List.copyOf` does not accept `null`; if the downstream collector can produce `null`, check and decide on a policy before freezing the list. `Collectors.mapping` does not automatically filter out `null`.

**Map ordering:** `TreeMap::new` sorts by key; `LinkedHashMap::new` preserves insertion order; `groupingBy` overloads without a `mapFactory` do not guarantee a specific `Map` type or iteration order.

**List ordering within a group:** with a source that has encounter order and a sequential pipeline as in the example, `mapping(..., toList())` produces a `List` in the order of elements within the group. Do not assume concurrent/unordered collection produces the same observed order.

**Empty groups:** `groupingBy(region, filtering(..., toList()))` can produce `region=[]` if the region has records but none match the predicate; if the source does not contain that region at all, `groupingBy` will not create the key automatically.

**Empty stream:** `groupingBy` on an empty source returns an empty `Map`; `partitioningBy` returns both `true`/`false` branches; `teeing(counting(), summingInt(...), merger)` on an empty source can produce a `(0,0)` report depending on the chosen downstream collectors.

These constraints **are not solved by adding more collector nesting**. Document them clearly in the API and write dedicated tests for them.

## 19. Parallel Collectors and Safety

When using `parallelStream()`, a collector can create separate **accumulators** and then combine them. That makes the following rules important:

1. `classifier`, `predicate`, and `mapper` functions should be **stateless** and **non-interfering**—do not mutate the source or external shared state.
2. A custom collector must have a `combiner` that satisfies its contract, not just work when run sequentially.
3. The merge function and aggregation logic should have properties compatible with regrouping, especially when dealing with ordering and floating-point numbers.
4. Do not assume `groupingBy(...)` is a **concurrent collector** just because the stream runs in parallel.
5. `groupingByConcurrent` has different concurrent/unordered semantics; do not substitute it mechanically if explicit ordering is required.
6. Do not write to a database, send emails, or perform mandatory business operations inside `mapping`/`filtering`/finisher just to “piggyback on one pass”; keep a clear business step with proper error control.
7. If results must be reproducible, choose data/collectors/order definitions and merge operations with stable outcomes, and test under the actual execution mode.

These principles take higher priority than reducing line count: one-line code with a data race or unstable merge is not good code.

## 20. Step-by-Step Refactoring Process for Deeply Nested Collectors

When encountering a hard-to-read expression, you can refactor in the following order:

**Step 1 — Write down the desired output type first.** For example `Map<String,RegionSummary>`, not “a Map containing lots of things.”

**Step 2 — Name the metrics.** `paidCount`, `amountTotal`, `productNames`; confirm exactly what each metric counts or filters.

**Step 3 — Determine the scope of filtering.** Filter the source globally, or filter downstream to still preserve empty group keys?

**Step 4 — Choose the right collector for each role.** `groupingBy` for grouping, `mapping` for transformation, `filtering` for selection, `teeing` for two metrics, `collectingAndThen` for the final result.

**Step 5 — Extract named logic.** Move downstream combinations into `static Collector<T, ?, R> readableName()` or explicitly typed local variables, avoiding raw types and casts.

**Step 6 — Choose an easy-to-use result type.** If `Map<K,Map<K2,R>>` does not reflect the needed API, use a record DTO or a list of report rows.

**Step 7 — Test edge cases.** Groups with only non-matching records, empty source, null keys, ordering, duplicate keys, and parallel execution if applicable.

**Step 8 — Measure performance if needed.** Only after having unit tests and a clear contract should you optimize pass counts/combiners and memory allocations.

Small, short, and expressive examples **do not need refactoring just to follow the process**. The goal is to clarify structure, not to create dozens of useless tiny methods.

## 21. Common Mistakes and How to Avoid Them

| Design mistake | Why it is harmful | How to improve |
| --- | --- | --- |
| Nesting four–five collectors with complex unnamed lambdas | Hard to reason about processing order and result types | Extract sub-collectors into business-named variables/methods |
| Blindly using `Stream.filter` instead of `Collectors.filtering` | Can cause groups with no matching elements to disappear | Choose filter placement based on group-retention requirements |
| Returning `Map<K,Map<K2,List<V>>>` for everything | Callers depend on deep structure; handling missing keys is verbose | Use a result record or a flat report model when appropriate |
| Using multi-level `teeing` to compute all metrics | Just as hard to read and maintain as the original expression | Use a custom collector or explicit computation steps |
| Confusing `counting` and `filtering(..., counting())` | One counts everything; the other counts only matching elements | Name the collector according to the actual condition |
| `collectingAndThen(toList(),List::copyOf)` on a list containing `null` | `List.copyOf` throws `NullPointerException` | Handle `null` beforehand and document the policy |
| Assuming `Collections.unmodifiableMap` is a deep copy | Returns only a view and does not freeze mutable value objects | Use an appropriate snapshot/defensive copy |
| Trusting default `HashMap`/groupingBy to preserve iteration order | The API does not guarantee that order | Choose a `mapFactory` like `TreeMap::new`/`LinkedHashMap::new` |
| Using raw `Collector` to silence generics errors | Loses type safety and hides structural issues | Declare `Collector<T, ?, R>` |
| Using `parallel` assuming complex collectors will automatically be faster | Combiner overhead and ordering constraints can cost more | Benchmark and test semantics |
| Putting mandatory side effects into mapper/filter/finisher | Business workflow is hard to verify/trace | Separate actions into a controllable business step |
| Using one `Stream` for multiple terminal collects | A `Stream` can only be consumed once | Create a new stream per pass from a traversable source |

## 22. Practice Exercises with Answers

**Exercise 1 — Collector naming.** Given `List<Sale>`, you need a `Map<String,Long>` counting paid `Sale` items by region, **keeping regions that have no paid `Sale`**. Write a readable collector.

Suggested answer in the context of a class containing `Sale` and importing `Collectors`, `Map`, `TreeMap`:

```java
Collector<Sale, ?, Long> paidCount =
        Collectors.filtering(Sale::paid, Collectors.counting());
Map<String, Long> result = sales.stream().collect(
        Collectors.groupingBy(Sale::region, TreeMap::new, paidCount));
```

If the `West` region has only unpaid `Sale` items, it still appears with `0`.

**Exercise 2 — Upstream or downstream?** With a source containing `North` (paid) and `West` (unpaid), does `stream().filter(Sale::paid).collect(groupingBy(...))` create a `West` group?

Answer: **No**. The `West` record is discarded before `groupingBy`'s classifier sees it. If you want `West=[]` or `West=0`, use downstream `Collectors.filtering`.

**Exercise 3 — Return type.** If you use `groupingBy(Sale::region, TreeMap::new, mapping(Sale::product,toList()))`, what is the result type?

Answer: `Map<String,List<String>>`. `groupingBy` creates `String` keys; `mapping` turns `Sale` into `String`; `toList` collects `List<String>`.

**Exercise 4 — teeing.** A region needs `paidCount` and `amountTotal`. Which return type makes the API clearer than `Map<String,Object>`?

Answer: `record RegionSummary(long paidCount,int amountTotal) {}`; use `teeing(filtering(paid,counting()),summingInt(amount),RegionSummary::new)` as the downstream collector of `groupingBy`.

**Exercise 5 — Immutability.** Does `collectingAndThen(toList(), List::copyOf)` accept `null` elements? Does it automatically make objects inside the `List` deeply immutable?

Answer: **No** to both. `List.copyOf` rejects `null`, and mutable elements can still be modified through other references.

**Exercise 6 — Two states.** You want `Map<Boolean,List<String>>` by `paid` status; is there a clearer API than `groupingBy(sale -> sale.paid(), mapping(...))`?

Answer: `partitioningBy(Sale::paid, mapping(Sale::product, toList()))`. The result contains both `true` and `false` keys, even when one side is empty.

**Exercise 7 — Finisher scope.** Distinguish `groupingBy(region, collectingAndThen(toList(), f))` and `collectingAndThen(groupingBy(region,toList()), f)`.

Answer: the first form runs `f` **on each group's `List`**, while the second runs `f` **on the entire grouped `Map`**; the input types of `f` also differ. The two forms are not arbitrarily interchangeable.

**Exercise 8 — Multi-metric problem.** If ten metrics per region are needed, should you nest nine levels of `teeing`?

Answer: usually **no**. Consider a clear accumulator/report type, a custom collector, or splitting into simple steps. Choose based on readability, allowed number of passes, and actual computation cost.

## 23. Code Review Checklist

- [ ] Looking at the result type, is it immediately clear what the caller receives?
- [ ] Does each downstream collector have a clear single responsibility and a name when needed?
- [ ] Does the placement of `filter`/`filtering` match the semantics of retaining empty groups?
- [ ] Does `mapping`/`flatMapping` match the number of output values per element?
- [ ] Does `teeing` only combine metrics that belong together?
- [ ] Is `collectingAndThen` applied at the right **scope** (per group or entire result)?
- [ ] Is the `Map` type explicitly chosen if ordering or special properties are needed?
- [ ] Have `null` data, empty sources, and groups with no matching elements been tested?
- [ ] Are there no mandatory business side effects inside downstream collectors?
- [ ] If the source is large/parallel, have pass count, combiner, and safety been considered?

## 24. Conclusion

- **Collector composition is a powerful tool**, but its power does not lie in how many functions you can nest in one expression.
- A readable collector answers: **what to group by, which elements to select, how to transform, what to aggregate, and what the result type is**.
- **Naming downstream collectors** and **returning a record/report type** reduce the burden of understanding multi-level `Map` structures and improve testability.
- **Downstream `filtering`** differs from `Stream.filter` before `groupingBy`; it can retain group keys with empty or `0` results.
- `teeing` fits two metrics, `collectingAndThen` fits a finishing step, `partitioningBy` fits boolean grouping, and `mapping`/`flatMapping` fit value transformation.
- When there are too many nesting levels, **a loop or a custom collector with a dedicated accumulator** can be clearer; do not force every business rule into a single expression.
- Design for **clarity, type accuracy, semantic contracts, and performance measurements**, not just line count.

Official documentation: [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html), [Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).
