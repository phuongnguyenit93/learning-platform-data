# Flattening Orders and Product Line Items

An order typically contains multiple product line items (*order lines*), whereas a revenue or inventory report usually needs to process **all product lines across all orders**. The Java Stream API provides `flatMap` to turn a nested structure such as `List<Order>`, where each `Order` holds a `List<OrderLine>`, into a flat stream of line items. If you also need to know which order each item came from, you can combine `flatMap` with `map` to **preserve parent order context**.

This practice lesson belongs to the **Beginner and Intermediate Exercises** chapter of the **JAVA_STREAM_API** module. The goal is to apply `filter`, `map`, `flatMap`, and `collect` to transform realistic data, then aggregate by product SKU using `groupingBy` or `toMap`. The lesson also builds practice in lazy pipelines, distinguishing line-item counts from total product unit quantities, handling empty/null sources, and preventing integer overflow when calculating revenue. Techniques such as custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers are optional extensions beyond the foundational solution.

## 1. Problem Statement and Input Data

A system maintains a list of orders. Each order has an order ID, a customer ID, and a list of line items. Each line item has a product code (SKU), product name, quantity, and unit price in **cents**.

| Order | Customer | Line Items |
|---|---|---|
| O1 | C01 | P01: Keyboard × 2, price 15.000; P02: Mouse × 1, price 8.000 |
| O2 | C02 | P01: Keyboard × 1, price 15.000; P03: Headphones × 3, price 20.000 |
| O3 | C03 | Empty line-item list |
| O4 | C04 | Null line-item list |
| O5 | C05 | P02: Mouse × 2, price 8.000 |

Problem rules:

- A line item must have a SKU and product name; integer quantity **greater than 0**, unit price **non-negative**.
- An empty or null line-item list is treated as having **no product lines** to flatten.
- Any `null` `OrderLine` element inside a list is **intentionally skipped**.
- The examples filter out `null` `Order` elements before accessing properties. In a real application, you might choose to throw an error instead of filtering.
- Monetary calculations use integer arithmetic in the smallest unit: `lineRevenueCents = quantity × unitPriceCents`.

**Practice task:** from the order list, produce a flat list of line items, calculate total quantity and revenue, aggregate by SKU, and compare how orders with no line items behave.

Expected summary results:

| SKU | Total Quantity | Total Revenue (cents) |
|---|---:|---:|
| P01 | 3 | 45.000 |
| P02 | 3 | 24.000 |
| P03 | 3 | 60.000 |
| **Total** | **9** | **129.000** |

There are **5 line items** flattened from **5 orders**, while the total product units equal **9**. These two metrics are not the same.

## 2. Reviewing `map` vs. `flatMap`: Different Output Shapes

Assume an `Order` type with a `getLines()` method returning `List<OrderLine>`.

### 2.1. `map` Preserves Nesting Levels

```java
Stream<List<OrderLine>> nested = orders.stream()
        .map(Order::getLines);
```

`map` turns each `Order` into **one `List<OrderLine>`**. The result is still a stream of lists, not a stream of line items.

When each order has its own list of items:

```text
Source:
  Order O1 -> [Line P01, Line P02]
  Order O2 -> [Line P01, Line P03]
  Order O3 -> []

map(Order::getLines):
  Stream<List<OrderLine>>
  [[P01, P02], [P01, P03], []]
```

To process individual product lines, you would still need to iterate over each inner list.

### 2.2. `flatMap` Flattens Inner Streams

```java
Stream<OrderLine> flat = orders.stream()
        .flatMap(order -> order.getLines().stream());
```

Each `Order` is mapped to **one `Stream<OrderLine>`**, and `flatMap` concatenates those sub-streams into a single stream:

```text
                  Stream<Order>
                  /     |     \
                O1      O2     O3
                 |       |      |
               [P01,   [P01,   []
                P02]    P03]
                  \      |     /
                       flatMap
                         |
       Stream<OrderLine>: P01, P02, P01, P03
```

This snippet is only safe when `orders` contains no null orders, `getLines()` never returns null, and the lines are valid for downstream processing. Because our dataset includes an order with a null list, we will write a **null-safe** version in Section 4.

### 2.3. Quick Comparison Table

| Expression | Resulting Element Type | Meaning |
|---|---|---|
| `orders.stream()` | `Order` | Traverses each order |
| `orders.stream().map(Order::getLines)` | `List<OrderLine>` | Traverses each line-item list |
| `orders.stream().map(o -> o.getLines().stream())` | `Stream<OrderLine>` | A stream of sub-streams |
| `orders.stream().flatMap(o -> o.getLines().stream())` | `OrderLine` | Traverses each line item |
| `orders.stream().flatMap(o -> o.getLines().stream().map(...))` | Type produced by `map(...)` | Line item paired with parent order context |

**Rule:** use `map` when one input element yields one output value; use `flatMap` when one input element yields **0, 1, or many output values** via a sub-stream.

## 3. Beginner Exercise: Flattening Line Items Directly

When you only need properties already stored inside `OrderLine`, a straightforward pipeline is:

```java
List<OrderLine> allLines = orders.stream()
        .filter(Objects::nonNull)
        .flatMap(order -> {
            List<OrderLine> lines = order.getLines();
            return lines == null
                    ? Stream.<OrderLine>empty()
                    : lines.stream();
        })
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

This illustration assumes `Order` and `OrderLine` are defined; the main imports are `java.util.List`, `java.util.Objects`, `java.util.stream.Stream`, and `java.util.stream.Collectors`.

Steps:

1. `orders.stream()`: creates the order Stream.
2. `filter(Objects::nonNull)`: drops null orders before calling getters.
3. `flatMap(...)`: returns a line-item stream per order; a null list becomes `Stream.empty()`.
4. `filter(Objects::nonNull)`: drops null line items if any exist.
5. `collect(toList())`: terminates the pipeline and gathers the line items.

On the problem dataset, the flat list has **5 elements** by SKU: `[P01, P02, P01, P03, P02]`. Orders O3 and O4 contribute no line items.

### 3.1. Empty Orders Are Not an Error in `flatMap`

`Stream.empty()` represents an order contributing **0 lines**; `flatMap` handles that naturally. If you later need to know which orders had no items, do not infer from the flat list that **those orders never existed**: flattening discards orders that emit no child elements.

### 3.2. One Line Item Differs from One Product Unit

Suppose line P01 in O1 has `quantity = 2`. After `flatMap`, it is still **one `OrderLine`**, not automatically expanded into two P01 elements.

```java
long numberOfRows = allLines.stream().count();

long numberOfUnits = allLines.stream()
        .mapToLong(line -> line.getQuantity())
        .sum();
```

When quantity is an attribute of the line, sum it with `sum` or a collector; do not duplicate rows by quantity unless the task genuinely requires processing individual physical units.

## 4. Intermediate Exercise: Preserving Order Context While Flattening

Once flattened directly into `Stream<OrderLine>`, you **no longer automatically know** which order a line belongs to if `OrderLine` does not store the order ID. Therefore, for reports needing `orderId` or `customerId`, create a result object representing the line item **together with parent order context**:

```java
static Stream<LineView> flattenOneOrder(Order order) {
    List<OrderLine> lines = order.getLines();
    if (lines == null) {
        return Stream.empty();
    }
    return lines.stream()
            .filter(Objects::nonNull)
            .map(line -> new LineView(order, line));
}

Stream<LineView> views = orders.stream()
        .filter(Objects::nonNull)
        .flatMap(MyClass::flattenOneOrder);
```

Here `MyClass` stands for the enclosing class; the complete example in Section 5 uses `OrderLineFlatteningDemo`. `LineView` is a result object that can hold:

```text
orderId
customerId
sku
productName
quantity
unitPriceCents
lineRevenueCents
```

As a result, every row knows both its **parent order** and **line details**, enabling grouping by customer, order ID, or SKU without reverse lookups.

### 4.1. Distinguishing Two Positions for `map`

```java
orders.stream()
        .map(Order::getLines)
        .flatMap(List::stream);
```

This pipeline flattens items but **loses the `Order` context** after `map(Order::getLines)`. It is also unsafe if any child list is null.

By contrast:

```java
orders.stream()
        .flatMap(order -> order.getLines().stream()
                .map(line -> new LineView(order, line)));
```

The second pipeline creates `LineView` **while `order` is still in scope** via the outer lambda. This is an essential technique for parent–child data problems. This short illustration assumes non-null child lists; use the null-safe version when handling the problem data.

## 5. Complete Java 8 Program

You can save the following program as `OrderLineFlatteningDemo.java` and run it on JDK 8 or later. It constructs the full problem dataset, flattens lines with context, collects into a `Map` by SKU, computes total quantity/revenue, and counts line items per order.

To prevent silent monetary errors when multiplying or summing integers, the example uses `Math.multiplyExact` and `Math.addExact`. The code assumes a single uniform currency and constructs data via validated constructors; this teaches safer arithmetic than using `double` for money.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class OrderLineFlatteningDemo {

    static final class OrderLine {
        private final String sku;
        private final String productName;
        private final int quantity;
        private final long unitPriceCents;

        OrderLine(String sku, String productName,
                int quantity, long unitPriceCents) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.productName = Objects.requireNonNull(
                    productName, "productName");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be greater than 0");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException(
                        "unitPriceCents must not be negative");
            }
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
        }

        String getSku() { return sku; }
        String getProductName() { return productName; }
        int getQuantity() { return quantity; }
        long getUnitPriceCents() { return unitPriceCents; }

        long getRevenueCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    static final class Order {
        private final String id;
        private final String customerId;
        private final List<OrderLine> lines;

        Order(String id, String customerId, List<OrderLine> lines) {
            this.id = Objects.requireNonNull(id, "id");
            this.customerId = Objects.requireNonNull(
                    customerId, "customerId");
            // Allow null list to demonstrate missing-data policy.
            this.lines = lines == null
                    ? null
                    : Collections.unmodifiableList(
                            new ArrayList<>(lines));
        }

        String getId() { return id; }
        String getCustomerId() { return customerId; }
        List<OrderLine> getLines() { return lines; }
    }

    // A flattened detail line retaining context from its parent order.
    static final class LineView {
        private final String orderId;
        private final String customerId;
        private final String sku;
        private final String productName;
        private final int quantity;
        private final long unitPriceCents;
        private final long lineRevenueCents;

        LineView(Order order, OrderLine line) {
            this.orderId = order.getId();
            this.customerId = order.getCustomerId();
            this.sku = line.getSku();
            this.productName = line.getProductName();
            this.quantity = line.getQuantity();
            this.unitPriceCents = line.getUnitPriceCents();
            this.lineRevenueCents = line.getRevenueCents();
        }

        String getOrderId() { return orderId; }
        String getCustomerId() { return customerId; }
        String getSku() { return sku; }
        String getProductName() { return productName; }
        int getQuantity() { return quantity; }
        long getUnitPriceCents() { return unitPriceCents; }
        long getLineRevenueCents() { return lineRevenueCents; }
    }

    // Immutable aggregate state per SKU.
    static final class ProductTotals {
        private final long quantity;
        private final long revenueCents;

        ProductTotals(long quantity, long revenueCents) {
            this.quantity = quantity;
            this.revenueCents = revenueCents;
        }

        static ProductTotals from(LineView view) {
            return new ProductTotals(
                    view.getQuantity(), view.getLineRevenueCents());
        }

        ProductTotals combine(ProductTotals other) {
            return new ProductTotals(
                    Math.addExact(quantity, other.quantity),
                    Math.addExact(revenueCents, other.revenueCents));
        }

        long getQuantity() { return quantity; }
        long getRevenueCents() { return revenueCents; }
    }

    // Each call creates a fresh pipeline; the source List can be reused.
    static Stream<LineView> flatten(List<Order> orders) {
        Objects.requireNonNull(orders, "orders");
        return orders.stream()
                .filter(Objects::nonNull)
                .flatMap(order -> {
                    List<OrderLine> lines = order.getLines();
                    Stream<OrderLine> children = lines == null
                            ? Stream.empty()
                            : lines.stream();
                    return children
                            .filter(Objects::nonNull)
                            .map(line -> new LineView(order, line));
                });
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "C01", Arrays.asList(
                        new OrderLine("P01", "Keyboard", 2, 15_000L),
                        new OrderLine("P02", "Mouse", 1, 8_000L))),
                new Order("O2", "C02", Arrays.asList(
                        new OrderLine("P01", "Keyboard", 1, 15_000L),
                        new OrderLine("P03", "Headphones", 3, 20_000L))),
                new Order("O3", "C03", Collections.emptyList()),
                new Order("O4", "C04", null),
                new Order("O5", "C05", Arrays.asList(
                        new OrderLine("P02", "Mouse", 2, 8_000L)))
        );

        // A. Inspect every flattened line in encounter order.
        List<LineView> rows = flatten(orders)
                .collect(Collectors.toList());

        System.out.println("Number of detail lines: " + rows.size());
        // 5

        rows.forEach(view -> System.out.println(
                view.getOrderId() + " | "
                + view.getSku() + " | "
                + view.getQuantity() + " | "
                + view.getLineRevenueCents()));
        // O1 | P01 | 2 | 30000
        // O1 | P02 | 1 | 8000
        // O2 | P01 | 1 | 15000
        // O2 | P03 | 3 | 60000
        // O5 | P02 | 2 | 16000

        // B. Aggregate by SKU using toMap and a merge function.
        Map<String, ProductTotals> bySku = flatten(orders)
                .collect(Collectors.toMap(
                        LineView::getSku,
                        ProductTotals::from,
                        ProductTotals::combine,
                        TreeMap::new));

        bySku.forEach((sku, totals) ->
                System.out.println(
                        sku + " -> quantity="
                        + totals.getQuantity()
                        + ", revenue="
                        + totals.getRevenueCents()));
        // P01 -> quantity=3, revenue=45000
        // P02 -> quantity=3, revenue=24000
        // P03 -> quantity=3, revenue=60000

        // C. Compute total units and revenue across all lines.
        long totalUnits = flatten(orders)
                .mapToLong(view -> view.getQuantity())
                .reduce(0L, Math::addExact);
        long totalRevenue = flatten(orders)
                .mapToLong(LineView::getLineRevenueCents)
                .reduce(0L, Math::addExact);

        System.out.println("Total units: " + totalUnits); // 9
        System.out.println("Total revenue: " + totalRevenue); // 129000

        // D. Count detail lines per order.
        Map<String, Long> rowsByOrder = flatten(orders)
                .collect(Collectors.groupingBy(
                        LineView::getOrderId,
                        TreeMap::new,
                        Collectors.counting()));

        System.out.println(rowsByOrder);
        // {O1=2, O2=2, O5=1}; O3 and O4 have no detail lines.
        System.out.println(rowsByOrder.containsKey("O3")); // false
    }
}
```

### 5.1. Why Does the Program Create Multiple Streams?

Each call to `flatten(orders)` creates **a new Stream instance** from the same `List<Order>`. Each Stream can only be consumed once. In this demo program, re-traversing the List is valid and lets us observe each operation independently.

If the source dataset is large or single-pass only, **decide which metrics are actually needed**, then accumulate them in a single collector rather than running multiple pipelines. Here, the SKU summary can be collected directly from `flatten(orders)` **without** materializing `rows` first; `rows` is only used to inspect the flattened output.

### 5.2. Why Does `TreeMap` Appear in `toMap`?

The four-argument overload:

```java
Collectors.toMap(
        keyMapper,
        valueMapper,
        mergeFunction,
        mapSupplier)
```

`TreeMap::new` ensures the resulting Map iterates over keys in natural SKU order. It does not control how quantities or revenues are added, nor does it fix an incorrect merge function. When key order does not matter, you can use the three-argument overload and avoid relying on default Map iteration order.

### 5.3. Why Is a Merge Function Required?

In the dataset, P01 appears in O1 and O2, while P02 appears in O1 and O5. Calling `toMap(LineView::getSku, ProductTotals::from)` without a merge function hits duplicate keys, causing `Collectors.toMap` to throw `IllegalStateException`.

`ProductTotals::combine` merges both **quantity** and **revenue**. Integer addition works naturally when splitting a source into branches as long as there is no overflow; the example uses `Math.addExact` to detect exceeding `long` bounds.

## 6. Alternative Aggregations: `groupingBy` and Downstream Collectors

Not every report needs a custom `ProductTotals` class. If you only need **total quantity** by SKU:

```java
Map<String, Long> unitsBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                TreeMap::new,
                Collectors.summingLong(
                        view -> view.getQuantity())));

System.out.println(unitsBySku);
// {P01=3, P02=3, P03=3}
```

If you only need **revenue** by SKU:

```java
Map<String, Long> revenueBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                TreeMap::new,
                Collectors.summingLong(
                        LineView::getLineRevenueCents)));
// P01=45000, P02=24000, P03=60000
```

`Collectors.summingLong` expresses the computation clearly, but does not automatically detect `long` overflow. In the complete example, `Math.addExact` is used during merging to detect overflow. If an application requires exact totals beyond `long`, consider `BigInteger` or `BigDecimal` rather than simply swapping collectors.

### 6.1. Counting Line Items per SKU

```java
Map<String, Long> lineCountBySku = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getSku,
                Collectors.counting()));
```

With the sample data, P01 appears on **2 lines**, P02 on **2 lines**, and P03 on **1 line**. This metric **differs from total quantity**: P03 has one line but `quantity = 3`.

### 6.2. Listing Order IDs Containing a SKU

```java
Map<String, java.util.Set<String>> orderIdsBySku =
        flatten(orders).collect(Collectors.groupingBy(
                LineView::getSku,
                Collectors.mapping(
                        LineView::getOrderId,
                        Collectors.toSet())));
```

For P01, the order ID set contains `{O1, O2}`. `toSet` deduplicates order IDs if one order has multiple lines for the same SKU, but **does not guarantee iteration order**. If you need both deduplication and appearance order, consider `toCollection(LinkedHashSet::new)` with an ordered source.

## 7. Flatten First or Group First?

This is an intermediate distinction that often affects reports directly.

### 7.1. Flattening First Then `groupingBy`

```java
Map<String, Long> linesPerOrder = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getOrderId,
                Collectors.counting()));
```

O3 and O4 **have no keys** in the result because they emitted zero `LineView` elements. That **does not mean orders O3/O4 do not exist**.

### 7.2. Grouping by Parent Order to Retain Empty Orders (Java 8)

If the report must show line counts for **every order**, including orders with empty line lists, count starting from `Order`:

```java
Map<String, Long> linesPerOrderIncludingEmpty =
        orders.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.groupingBy(
                        Order::getId,
                        TreeMap::new,
                        Collectors.summingLong(order -> {
                            List<OrderLine> lines = order.getLines();
                            return lines == null
                                    ? 0L
                                    : lines.stream()
                                            .filter(Objects::nonNull)
                                            .count();
                        })));

System.out.println(linesPerOrderIncludingEmpty);
// {O1=2, O2=2, O3=0, O4=0, O5=1}
```

If the system allows duplicate order IDs, `groupingBy` here would sum line counts across records sharing the same ID; verify whether that matches requirements. In this problem, order IDs are unique.

### 7.3. Parent Grouping with Downstream `flatMapping` (Java 9+)

Since Java 9, `Collectors.flatMapping` lets you flatten **inside an existing group**:

```java
Map<String, Long> counts = orders.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.groupingBy(
                Order::getId,
                TreeMap::new,
                Collectors.flatMapping(
                        order -> order.getLines() == null
                                ? Stream.<OrderLine>empty()
                                : order.getLines().stream()
                                        .filter(Objects::nonNull),
                        Collectors.counting())));

// {O1=2, O2=2, O3=0, O4=0, O5=1}
```

Unlike `Stream.flatMap` before `groupingBy`, downstream `flatMapping` does not drop parent orders before grouping. When a parent order exists with no line items, its group remains with a count of 0.

**Version note:** `Stream.flatMap` exists since Java 8, while `Collectors.flatMapping` was added in **Java 9**. The complete program in Section 5 requires only Java 8.

## 8. Filtering at Order Level vs. Line Level: Two Different Meanings

In nested data, where you place `filter` changes the meaning.

### 8.1. Filtering Orders Before Flattening

For example, consider only orders from customer C01:

```java
List<LineView> fromC01 = orders.stream()
        .filter(Objects::nonNull)
        .filter(order -> "C01".equals(order.getCustomerId()))
        .flatMap(order -> {
            List<OrderLine> lines = order.getLines();
            return (lines == null
                    ? Stream.<OrderLine>empty()
                    : lines.stream().filter(Objects::nonNull))
                    .map(line -> new LineView(order, line));
        })
        .collect(Collectors.toList());

System.out.println(fromC01.size()); // 2
```

Filtering on the parent object skips all child lines of non-matching orders **before** reading their line-item lists.

### 8.2. Filtering Line Items After Flattening

For example, select only SKU P01 lines regardless of customer:

```java
List<LineView> keyboardLines = flatten(orders)
        .filter(view -> "P01".equals(view.getSku()))
        .collect(Collectors.toList());

System.out.println(keyboardLines.size()); // 2
```

If a condition depends on both order and line fields, `LineView` lets you express it directly:

```java
List<LineView> selected = flatten(orders)
        .filter(view -> "C02".equals(view.getCustomerId())
                && view.getQuantity() >= 2)
        .collect(Collectors.toList());
// Only line P03 from O2.
```

To avoid scanning unnecessary details in large systems, prefer filtering early at the level where the predicate can be evaluated accurately. However, never push a line-level condition up to the parent level if it genuinely belongs to individual child items.

## 9. Ordering, Duplicates, and `distinct`

`List<Order>` preserves encounter order by order position; `List<OrderLine>` inside each order is also ordered. In a sequential pipeline:

```java
List<String> skus = flatten(orders)
        .map(LineView::getSku)
        .collect(Collectors.toList());

System.out.println(skus);
// [P01, P02, P01, P03, P02]
```

`flatMap` emits items in the order of each sub-stream when both the source and child lists are ordered. On a parallel stream with an ordered source, `collect(toList())` still preserves encounter order in the output, even if intermediate steps run on multiple workers.

### 9.1. Extracting Distinct SKUs

```java
List<String> distinctSkus = flatten(orders)
        .map(LineView::getSku)
        .distinct()
        .collect(Collectors.toList());

System.out.println(distinctSkus); // [P01, P02, P03]
```

Do not call `distinct()` directly on `LineView` expecting it to deduplicate by SKU. If `LineView` does not define `equals`/`hashCode` according to that business rule, distinct instances are treated as different. Here we map to `String sku` **before** calling `distinct`.

### 9.2. Repeated SKUs Are Not Redundant Records

P01 appearing in two orders is valid data: its quantities and revenues must be **summed**, not dropped with `distinct`. Only use `distinct` when the goal is genuinely a list of unique product codes or a report with an explicit deduplication rule.

### 9.3. `forEach` vs. `forEachOrdered` in Parallel

```java
flatten(orders)
        .parallel()
        .map(LineView::getSku)
        .forEachOrdered(System.out::println);
```

`forEachOrdered` preserves action order according to source encounter order. Using `forEach` on a parallel stream gives no ordering guarantee. Never use `forEach` to append to an external `ArrayList` concurrently from multiple workers; `collect(toList())` is safe and built for that purpose.

## 10. Null Data, Business Errors, and Explicit Policies

There are at least three kinds of null to distinguish:

| Case | Example Behavior | Business Alternative |
|---|---|---|
| `Order` element is null | Filtered with `Objects::nonNull` | Throw an error and log invalid source data |
| `order.getLines() == null` | Returns `Stream.empty()` | Distinguish "lines not loaded" from "truly no lines" |
| An `OrderLine` element is null | Filtered out of sub-stream | Report missing data or count corrupted lines |
| SKU or product name is null | Rejected by constructor | Normalize/reconcile source before collecting |
| Non-positive quantity | Rejected by constructor | Support return lines via a dedicated transaction type |
| Negative unit price | Rejected by constructor | Model discounts/adjustments with explicit rules |

**Key point:** if null in the line list means **data has not been loaded yet** rather than "an empty list", converting null to `Stream.empty()` silently under-reports data. The exercise rules permit this handling here; production systems must choose according to domain semantics.

### 10.1. An Empty Sub-Stream Does Not Emit a `null` Element

`Stream.empty()` is a Stream with **0 elements**. It differs from `Stream.of((OrderLine) null)`, which contains **one null element**. Do not assume `flatMap` automatically removes null elements inside child lists.

### 10.2. Overflow in Monetary Multiplication

Do not write:

```java
int revenue = line.getQuantity()
        * (int) line.getUnitPriceCents();
// Prone to overflow or data loss when narrowing to int.
```

In the complete example, `int` quantity is widened to `long` before multiplying:

```java
long revenue = Math.multiplyExact(
        (long) line.getQuantity(),
        line.getUnitPriceCents());
```

If the product cannot fit in `long`, `Math.multiplyExact` throws `ArithmeticException` instead of producing corrupted revenue. When summing totals, `Math.addExact` similarly detects sum overflow.

Unit prices and revenues are both in **cents**. When formatting currency with decimal places, convert and round using explicit monetary rules; `double` is not the default choice for exact monetary arithmetic.

## 11. Complexity, Memory, and Large Data Sources

Suppose there are `N` orders and `M` total line items. A `flatMap` traversal generally visits each order and each child line: roughly `O(N + M)` time, excluding downstream aggregation costs.

- `collect(toList())` retains all `M` lines in memory, so memory scales with total line count.
- `groupingBy` or `toMap` aggregating by SKU requires memory proportional only to the **number of distinct SKUs** (plus accumulator state), provided individual lines are not kept.
- If grouping into `List<LineView>` per SKU, total data memory still scales with line count.
- If the source is `Files.lines` or another I/O stream, manage the source Stream with `try-with-resources`; `collect` does not automatically close files.

Example without materializing a full `LineView` list:

```java
Map<String, ProductTotals> report = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                ProductTotals::from,
                ProductTotals::combine));
```

This still performs a single traversal of `flatten(orders)`, without creating an intermediate `rows` list. For repeated SKUs, the merge function must **combine partial aggregates** so results remain meaningful if the data is split into multiple branches.

### 11.1. Should You Enable `parallelStream`?

Simply adding `parallel()` does not guarantee faster execution. Check:

1. Can the source split efficiently?
2. Do lambdas avoid shared mutable state and source interference?
3. Do merge functions/collectors satisfy **identity, associativity, and compatibility**?
4. Are there ordering constraints, `LineView` allocation overhead, or resource contention?
5. Is the dataset and per-element work large enough to outweigh parallel overhead?

With `List` and immutable objects in the example, `ProductTotals::combine` uses overflow-checked integer addition, which is associative within valid numeric bounds. Thus parallel execution can be explored, though for five orders there is no performance reason to enable `parallel()` by default.

## 12. Common Mistakes

| Pitfall | Consequence | Fix |
|---|---|---|
| Using `map(Order::getLines)` expecting `OrderLine` | Remains `Stream<List<OrderLine>>` | Use `flatMap` |
| `order.getLines().stream()` when list is null | `NullPointerException` | Return `Stream.empty()` or handle missing data |
| Trying to read `orderId` after flattening `OrderLine` without order ID | Parent relationship lost | Create `LineView(order, line)` inside the `flatMap` lambda |
| Using `count()` on lines to compute total units | Counts lines instead of summing quantity | `mapToLong(LineView::getQuantity).sum()` |
| Using `distinct()` on lines before summing revenue | Can drop valid transactions | Aggregate with `groupingBy`/`toMap` by SKU |
| Calling `toMap` without merge function when SKUs repeat | `IllegalStateException` | Provide a function summing quantity/revenue |
| Summing quantity while forgetting revenue in merge | Incorrect report | Combine all metrics in `ProductTotals` |
| Using `int` to multiply large quantity × unit price | Integer overflow | Use `long` and `Math.multiplyExact` |
| Orders O3/O4 missing from `groupingBy` after flattening | No rows emitted for those keys | Group on `Order` or use downstream `flatMapping` (Java 9+) |
| Using `parallel().forEach(list::add)` on shared `ArrayList` | Data race under concurrent mutation | `collect(toList())` or an appropriate collector |
| Reusing a Stream after a terminal operation | `IllegalStateException` | Create a new Stream from a re-traversable source |

## 13. Applied Exercises with Solutions

### Exercise 1. Predict Output After `flatMap`

With O1 having two lines, O2 two lines, O3 empty, O4 null, and O5 one line, what does `flatten(orders).count()` return?

**Answer:** `5L`. Orders O3 and O4 contribute zero lines; counting on the flattened Stream counts **product lines**, not orders.

### Exercise 2. Total Product Units

Write a pipeline computing the sum of `quantity` across all valid lines.

```java
long units = flatten(orders)
        .mapToLong(view -> view.getQuantity())
        .sum();
```

**Answer:** `9L`. P01 has 3, P02 has 3, and P03 has 3 units.

### Exercise 3. Total Revenue for SKU P02

Write a pipeline selecting only P02 and summing revenue from those lines.

```java
long mouseRevenue = flatten(orders)
        .filter(view -> "P02".equals(view.getSku()))
        .mapToLong(LineView::getLineRevenueCents)
        .sum();
```

**Answer:** `24_000L` from O1 (8.000) and O5 (16.000). When overflow detection is required, replace `sum()` with `reduce(0L, Math::addExact)`.

### Exercise 4. Finding Distinct SKUs

```java
List<String> unique = flatten(orders)
        .map(LineView::getSku)
        .distinct()
        .collect(Collectors.toList());
```

**Answer:** `[P01, P02, P03]` given a List source and ordered pipeline. `distinct` on SKU strings does not discard transaction amounts because this query specifically asks for the **unique product codes**.

### Exercise 5. Counting Lines Including Empty Orders

Does `groupingBy(LineView::getOrderId, counting())` after `flatten` include keys O3 and O4?

**Answer:** No. To obtain `O3=0` and `O4=0`, aggregate from the `Order` level or use `Collectors.flatMapping` **inside** `groupingBy(Order::getId, ...)` in Java 9+. Section 7.2 shows the Java 8 solution.

### Exercise 6. Calculating Revenue by Customer

Instead of grouping by SKU, group by `customerId`.

```java
Map<String, Long> revenueByCustomer = flatten(orders)
        .collect(Collectors.groupingBy(
                LineView::getCustomerId,
                TreeMap::new,
                Collectors.summingLong(
                        LineView::getLineRevenueCents)));
```

**Answer:** `{C01=38000, C02=75000, C05=16000}`. Customers C03 and C04 have no line items, so they do not appear in this Map. For totals that might exceed `long`, use overflow-checked addition.

### Exercise 7. Why Does `toMap` Need a `mergeFunction`?

Is the following code valid when multiple orders contain the same SKU?

```java
Map<String, Long> quantities = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                view -> (long) view.getQuantity()));
```

**Answer:** Not for this dataset because SKUs repeat; this overload throws `IllegalStateException` on duplicate keys. Write:

```java
Map<String, Long> quantities = flatten(orders)
        .collect(Collectors.toMap(
                LineView::getSku,
                view -> (long) view.getQuantity(),
                Math::addExact));
// P01=3, P02=3, P03=3
```

### Exercise 8. Retaining Parent Orders and Handling Unloaded Lists

If `getLines() == null` actually means "line details have not been fetched from the system yet", should a revenue report silently treat it as an empty list?

**Answer:** No, if business rules require complete reporting. You should throw an error, load the missing details beforehand, or track missing-data status separately. `Stream.empty()` is purely a technical choice; **the business meaning of null must be decided first**.

## 14. Extension Exercise: Design a Richer Product Report

After running the sample program, extend `ProductTotals` into a report containing:

1. Representative `sku` and `productName`.
2. Total units sold.
3. Total revenue.
4. Number of distinct orders containing the SKU.
5. Set of customer IDs who purchased the SKU.

**Design hints:**

- Total quantity and revenue combine by addition.
- Distinct order count requires merging **sets of order IDs** and taking the size, not just counting lines: one order may contain multiple lines for the same SKU.
- Customer sets can be collected with `Collectors.mapping(LineView::getCustomerId, toSet())` inside `groupingBy` by SKU.
- To compute every metric in **one result per SKU**, consider a custom collector storing total quantity, total amount, an orderId set, and a customerId set, with a combiner merging all fields.
- Never share an external `HashSet` or `HashMap` and mutate it inside `parallelStream().forEach(...)`.

A beginner version can use separate collectors over a `List`; an advanced version can build a dedicated accumulator when single-pass execution and parallel compatibility are required.

## 15. Pre-Completion Checklist

Check yourself on these points:

1. How do `map` and `flatMap` differ in **Stream shape**?
2. How many rows does an order with an empty or null list contribute after `flatMap`?
3. How do you preserve `orderId` and `customerId` when child lines lack those fields?
4. Have you distinguished **line count**, **total quantity**, and **distinct SKU count**?
5. When SKU keys collide in `toMap`, does `mergeFunction` combine both quantity and revenue?
6. Should orders with no line items appear in per-order reports?
7. What rules govern null data, invalid quantities, negative unit prices, and numeric overflow?
8. For large datasets, do you really need to materialize all `LineView` objects in a `List` before aggregating?
9. If using a parallel Stream, do lambdas and collectors avoid shared mutable state and preserve encounter order where needed?

**Conclusion:** `flatMap` is the core tool for turning `List<Order>` containing nested `List<OrderLine>` collections into a flat stream of line items ready for filtering and aggregation. When reports need to know which order or customer a line belongs to, construct the enriched element inside the lambda that still has `Order` in scope. After flattening, choose `groupingBy` or `toMap` as required, and explicitly specify counting units, empty-group policy, duplicate-SKU merging, and overflow-safe arithmetic. This forms the foundation for building more complex order-analytics pipelines with the Java Stream API.
