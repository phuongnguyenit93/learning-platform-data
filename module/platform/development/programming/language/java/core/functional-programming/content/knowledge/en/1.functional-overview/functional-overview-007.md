# End-to-End Example: Filtering, Transforming, and Aggregating Orders with Java Stream

## 1. Problem Statement and Goals

A store has a list of orders. Each order consists of an order ID, customer, status, and order lines (SKU, quantity, unit price). We need to go from raw data to a verifiable report:

1. **Filter** paid orders (`PAID`), skipping pending (`PENDING`) and cancelled (`CANCELLED`) orders.
2. **Transform** each order line into a subtotal, each order into a total, and sort the paid orders by value in descending order.
3. **Aggregate** revenue from `PAID` orders, revenue by customer, and quantity of products sold by SKU.
4. Keep the input data intact, encapsulate business logic in small functions, and verify the results by hand.

This example belongs to **Java core – functional programming**: practicing `Predicate`, `Function`, lambdas, method references, `Stream`, `map`, `flatMap`, `filter`, `sorted`, `reduce`, and `Collectors`. The entire program uses Java 17 or higher, requiring no libraries outside the JDK.

> **Business convention for this example:** "revenue" here is the total merchandise amount of orders with status `PAID`, without considering taxes, shipping fees, discounts, returns, or accounting revenue recognition timing. When building a real-world product, those rules must be defined and checked separately.

## 2. Sample Data and Expected Results

| Order ID | Customer | Status | Order Lines | Total |
| --- | --- | --- | --- | ---: |
| A01 | Lan | PAID | BOOK × 2 × 120000; PEN × 3 × 10000 | 270000 |
| A02 | Minh | PENDING | BOOK × 1 × 120000 | 120000 |
| A03 | Lan | PAID | BAG × 1 × 200000 | 200000 |
| A04 | An | PAID | PEN × 5 × 10000 | 50000 |
| A05 | Minh | CANCELLED | BAG × 2 × 200000 | 400000 |
| A06 | An | PAID | BOOK × 1 × 120000; BAG × 1 × 200000 | 320000 |

For example: order A01 total = `2 × 120000 + 3 × 10000 = 270000`. There are **4 PAID orders**: A01, A03, A04, A06. The totals of A02 and A05 are not added to the report. Based on the dataset above:

- Total revenue: **840000** (= 270000 + 200000 + 50000 + 320000).
- Revenue by customer: **An: 370000**; **Lan: 470000**.
- SKU quantities: **BAG: 2**, **BOOK: 3**, **PEN: 8**. These are quantities sold, not revenue per SKU.
- Order ranking by descending total: **A06 → A01 → A03 → A04**.

Data flow diagram:

```text
List<Order>
    │
    ├── filter(status == PAID) ──> List<Order> paidOrders
    │                                 │
    │                                 ├── sorted(total DESC) ─> display list
    │                                 ├── map(total) + reduce ─> total revenue
    │                                 ├── groupingBy(customer,
    │                                 │       reducing(total)) ─> revenue/customer
    │                                 └── flatMap(lines)
    │                                         + groupingBy(sku,
    │                                           summingInt(quantity))
    │                                                      └── quantity/SKU
    └── original data remains intact
```

## 3. Complete Java 17 Program

Create a file named **`OrderPipelineDemo.java`** with the following content. The file name must match the `public class` name.

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class OrderPipelineDemo {
    enum Status {
        PAID, PENDING, CANCELLED
    }

    record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        BigDecimal subtotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Order(String id, String customer, Status status, List<OrderLine> lines) {
        Order {
            lines = List.copyOf(lines);
        }

        BigDecimal total() {
            return lines.stream()
                    .map(OrderLine::subtotal)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A01", "Lan", Status.PAID, List.of(
                        new OrderLine("BOOK", 2, money("120000")),
                        new OrderLine("PEN", 3, money("10000")))),
                new Order("A02", "Minh", Status.PENDING, List.of(
                        new OrderLine("BOOK", 1, money("120000")))),
                new Order("A03", "Lan", Status.PAID, List.of(
                        new OrderLine("BAG", 1, money("200000")))),
                new Order("A04", "An", Status.PAID, List.of(
                        new OrderLine("PEN", 5, money("10000")))),
                new Order("A05", "Minh", Status.CANCELLED, List.of(
                        new OrderLine("BAG", 2, money("200000")))),
                new Order("A06", "An", Status.PAID, List.of(
                        new OrderLine("BOOK", 1, money("120000")),
                        new OrderLine("BAG", 1, money("200000"))))
        );

        // 1. Predicate function passed to filter.
        Predicate<Order> isPaid = order -> order.status() == Status.PAID;
        List<Order> paidOrders = orders.stream()
                .filter(isPaid)
                .toList();

        // 2. Mapping function Order -> BigDecimal, reusable.
        Function<Order, BigDecimal> totalOf = Order::total;
        List<Order> ranked = paidOrders.stream()
                .sorted(Comparator.comparing(totalOf)
                        .reversed()
                        .thenComparing(Order::id))
                .toList();

        System.out.println("Đơn PAID theo tổng tiền giảm dần:");
        ranked.forEach(order -> System.out.printf(
                "%s | %s | %s%n",
                order.id(),
                order.customer(),
                order.total().toPlainString()
        ));

        // 3. Sum the BigDecimal values.
        BigDecimal revenue = paidOrders.stream()
                .map(totalOf)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("Tổng doanh thu: " + revenue.toPlainString());

        // 4. Group by customer and sum the order totals in each group.
        Map<String, BigDecimal> revenueByCustomer = paidOrders.stream()
                .collect(Collectors.groupingBy(
                        Order::customer,
                        TreeMap::new,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                Order::total,
                                BigDecimal::add
                        )
                ));

        System.out.println("Doanh thu theo khách:");
        revenueByCustomer.forEach((customer, total) ->
                System.out.printf("%s: %s%n",
                        customer, total.toPlainString()));

        // 5. Flatten all order lines of PAID orders, then group by SKU.
        Map<String, Integer> quantityBySku = paidOrders.stream()
                .flatMap(order -> order.lines().stream())
                .collect(Collectors.groupingBy(
                        OrderLine::sku,
                        TreeMap::new,
                        Collectors.summingInt(OrderLine::quantity)
                ));

        System.out.println("Số lượng theo SKU:");
        quantityBySku.forEach((sku, quantity) ->
                System.out.printf("%s: %d%n", sku, quantity));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac --release 17 OrderPipelineDemo.java
java OrderPipelineDemo
```

Expected output (stdout):

```text
Đơn PAID theo tổng tiền giảm dần:
A06 | An | 320000
A01 | Lan | 270000
A03 | Lan | 200000
A04 | An | 50000
Tổng doanh thu: 840000
Doanh thu theo khách:
An: 370000
Lan: 470000
Số lượng theo SKU:
BAG: 2
BOOK: 3
PEN: 8
```

Values are printed using `BigDecimal.toPlainString()` to avoid scientific notation. `TreeMap` ensures customer and SKU keys are traversed in lexicographical order, so the order of the corresponding lines is deterministic. The `sorted` call ensures the order list is traversed by descending total; on ties, `thenComparing(Order::id)` uses the order ID as a tie-breaker so the result does not depend on input data ordering.

## 4. Step-by-Step Pipeline Analysis

### Step 1 — Data Modeling and Subtotal Calculation

- `OrderLine` is a **record** representing an order line. `subtotal()` computes `unitPrice × quantity` and returns a `BigDecimal`.
- `Order` stores order details and the list of order lines. The compact constructor `Order { lines = List.copyOf(lines); }` creates a defensive copy of the list, preventing external list modifications after the order is created. The `OrderLine` elements are records, though this copy only copies the list structure, not a deep copy of every object.
- `Order.total()` processes each line in an order with `map(OrderLine::subtotal)`, followed by `reduce(BigDecimal.ZERO, BigDecimal::add)`. If an order has an empty list of lines, the `reduce` result is `BigDecimal.ZERO`.
- `money("120000")` takes a string and constructs a `BigDecimal` with the exact decimal value. For monetary calculations, avoid creating `BigDecimal` from a `double` literal such as `new BigDecimal(0.1)` because `double` has binary representation inaccuracies.

In a real-world application, you should validate `quantity > 0`, `unitPrice >= 0`, required fields, and valid SKU codes right at the data creation boundary. This example focuses on the pipeline, so it uses already-valid data.

### Step 2 — Filtering Orders with `Predicate` and `filter`

```java
Predicate<Order> isPaid = order -> order.status() == Status.PAID;
List<Order> paidOrders = orders.stream()
        .filter(isPaid)
        .toList();
```

`Predicate<Order>` describes a test function from `Order` to `boolean`. `filter(isPaid)` only lets orders returning `true` pass through. Using `==` here is correct because `Status` is an `enum`. Use `equals` for values like strings when comparing content; do not use `==` to compare two strings.

`stream()` creates a stream from `orders`; `filter` is an *intermediate operation*, so it is executed when `toList()` (a *terminal operation*) runs. `toList()` in Java 17 returns an **unmodifiable** list via `add`/`remove`; do not confuse this with freezing all referenced objects inside. `filter` does not remove any orders from `orders`.

### Step 3 — Transforming and Sorting

```java
Function<Order, BigDecimal> totalOf = Order::total;
List<Order> ranked = paidOrders.stream()
        .sorted(Comparator.comparing(totalOf)
                .reversed()
                .thenComparing(Order::id))
        .toList();
```

`Function<Order, BigDecimal>` is a function that converts an `Order` into its total amount. `Order::total` is a *method reference* equivalent to `order -> order.total()`. `Comparator.comparing(totalOf)` compares the `BigDecimal` results in ascending order, `reversed()` flips it to descending, and `thenComparing` handles ties.

`sorted` produces a new ordered stream without permuting `orders` or `paidOrders`. Every call to `total()` iterates through the order's lines again; for large datasets and expensive computations, you can store a projection `(order, total)` to compute the total **once** before sorting.

### Step 4 — Summing Revenue with `map` and `reduce`

```java
BigDecimal revenue = paidOrders.stream()
        .map(totalOf)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`map(totalOf)` converts `Stream<Order>` into `Stream<BigDecimal>`. `reduce` combines multiple values into one: starting with `0` and adding each order total. `BigDecimal` addition produces a new value without mutating either operand. This addition has the identity element `ZERO` and is numerically associative, making it suitable for stream reduction.

**Distinction:** `map` transforms **each element into exactly one result element**; `filter` may keep or drop elements; `reduce` produces **a single aggregated value**. Do not use `map` merely to mutate an external counter variable, as that creates side effects and hinders parallel processing.

### Step 5 — Grouping and Aggregating by Customer with `Collectors.groupingBy`

```java
Map<String, BigDecimal> revenueByCustomer = paidOrders.stream()
        .collect(Collectors.groupingBy(
                Order::customer,
                TreeMap::new,
                Collectors.reducing(
                        BigDecimal.ZERO, Order::total, BigDecimal::add
                )
        ));
```

The three parameters of `groupingBy` are, in order:

1. **Classifier function:** `Order::customer`. For example, both A01 and A03 go into the `Lan` group.
2. **Map supplier:** `TreeMap::new` so key traversal order is deterministic according to the natural ordering of `String`.
3. **Downstream collector:** `reducing` converts each `Order` to `Order.total()` and then sums all orders in each group.

The result is `Map<String, BigDecimal>`: each customer is mapped to their **total revenue**, not a list of orders. If you only use `groupingBy(Order::customer)`, the default value is `List<Order>`; if you use `counting()`, the value is the **order count**, not revenue. Choose the downstream collector that matches the exact business question.

### Step 6 — Flattening Order Lines with `flatMap` and Counting SKU Quantities

```java
Map<String, Integer> quantityBySku = paidOrders.stream()
        .flatMap(order -> order.lines().stream())
        .collect(Collectors.groupingBy(
                OrderLine::sku,
                TreeMap::new,
                Collectors.summingInt(OrderLine::quantity)
        ));
```

Each `Order` has a list of `OrderLine`. If you used `map(Order::lines)`, the result type would be `Stream<List<OrderLine>>`: still nested lists. `flatMap(order -> order.lines().stream())` produces a single `Stream<OrderLine>`, concatenating the lines of **the filtered orders** into one stream.

`summingInt(OrderLine::quantity)` sums `quantity` by SKU. Among paid orders, BAG appears in A03 and A06, giving `1 + 1 = 2`; BOOK has `2 + 1 = 3`; PEN has `3 + 5 = 8`. If you want **revenue by SKU**, you must aggregate `OrderLine::subtotal` using `BigDecimal`; `summingInt` here is only appropriate for **quantities**. In systems with very large total quantities, check for `int` overflow risk and consider `summingLong` or an appropriate numeric type.

## 5. Why Is This Style Functional Programming?

Each transformation expresses a small decision that can be named, reused, and tested independently:

| Component | Role in this example | Representative type |
| --- | --- | --- |
| `Predicate<Order>` | Check whether an order is paid | `Order -> boolean` |
| `Function<Order, BigDecimal>` | Compute the total amount of an order | `Order -> BigDecimal` |
| `filter` | Select eligible orders | `Stream<Order> -> Stream<Order>` |
| `map` | Transform an order into its total | `Stream<Order> -> Stream<BigDecimal>` |
| `flatMap` | Flatten order lines from multiple orders | `Stream<Order> -> Stream<OrderLine>` |
| `sorted` | Sort the orders | `Stream<Order> -> Stream<Order>` |
| `reduce` | Sum into a single total | `Stream<BigDecimal> -> BigDecimal` |
| `collect(groupingBy(...))` | Group elements by key and accumulate results | `Stream<T> -> Map<K, V>` |

A stream follows the **source → intermediate operations → terminal operation** model. Operations like `filter`, `map`, and `sorted` do not produce a report until a terminal operation (`toList`, `reduce`, or `collect`) consumes the stream. A `Stream` instance should only be consumed **once**; to produce multiple reports, as in the program above, create a new stream from `paidOrders` each time. Reusing a `List<Order>` as the source for multiple streams is completely normal.

The example intentionally uses side-effect-free functions: it neither mutates the source list inside `map`/`filter` nor updates a shared `revenue` variable inside `forEach`. `forEach` is only used to **print results at the final boundary of the program**. When collecting results, prefer `reduce` or `collect` rather than mutating external state outside the pipeline.

## 6. Edge Cases and Common Pitfalls

**Empty orders or no PAID orders.** `filter(...).toList()` may return an empty list; `reduce(BigDecimal.ZERO, ...)` returns `0`; `groupingBy` returns an empty map. If you need a report for all customers including unpaid ones, you must add a business definition and an independent customer source. Do not fabricate results for customers with no data.

**A pipeline may traverse data multiple times.** The program creates `paidOrders` once and then generates three reports from it. `Order.total()` is recomputed during sorting, printing, revenue calculation, and grouping; for large datasets, you can use an intermediate record like `record PricedOrder(Order order, BigDecimal total) {}` and transform the filtered orders into a list of `PricedOrder` to avoid recomputing totals. Weigh readability before optimizing.

**Grouping order is not guaranteed by default.** `groupingBy(classifier)` typically returns a `HashMap`, so do not rely on default iteration order when comparing stdout. `TreeMap::new` was chosen intentionally; if you need encounter order, consider `LinkedHashMap::new` with a predictable source stream order.

**Distinguish orders from order lines.** Summing order totals (`Order.total()`) gives total order revenue. Summing line quantities (`OrderLine.quantity()`) gives the total number of items. Calling `count()` after `flatMap` only returns the number of *order lines*, not the total quantity; for example, A01 has two lines but five items.

**Do not compare money using `double`.** `BigDecimal` enables exact decimal arithmetic for the entered values; if computing tax/discount rates or non-terminating divisions, you must define `scale` and `RoundingMode` according to business requirements. `BigDecimal.equals` also checks scale (`1.0` differs from `1.00` under `equals`), whereas `compareTo` compares numeric values; the comparator in this example uses `compareTo` via `Comparator.comparing`.

**Avoid `null` in the source.** `List.of` does not accept `null` elements; `TreeMap` with natural ordering does not accept `null` keys either. Data coming from an API/DB may have missing fields: validate upfront at the input boundary, and agree on rules to filter out, raise an error, or substitute; do not silently assume unit price or customer is `0`/empty string.

**Do not parallelize unconditionally.** `parallelStream()` is not guaranteed to be faster; it adds coordination overhead and can change the execution order of side effects. With a few orders, a sequential stream is easier to reason about and verify. If parallelization is needed, first ensure functions do not depend on shared state, the aggregation is suitable, and benchmark on real data.

**Do not reuse an already-operated Stream.** The following snippet is invalid because it invokes two terminal operations on the same stream:

```java
// Error illustration: do not put this in the runnable program above.
var paidStream = orders.stream().filter(isPaid);
long count = paidStream.count();
// paidStream.toList(); // IllegalStateException: stream has already been operated upon or closed
```

The right approach: store the intermediate result as `paidOrders` or create a new `orders.stream()` for the second pipeline.

## 7. Self-Check and Problem Extensions

1. **Test filtering:** remove order A06 from the input. There will be 3 PAID orders left; total revenue must be `520000`, customer An becomes `50000`, SKU BAG becomes `1`, and BOOK becomes `2`.
2. **Test quantities:** add a line `PEN × 2 × 10000` to A04. PEN quantity becomes `10`, total revenue becomes `860000`, customer An becomes `390000`; the status and count of PAID orders remain unchanged.
3. **Test deterministic ordering:** create two orders with equal totals. `thenComparing(Order::id)` must determine ascending order ID order within the tied-total group.
4. **Test empty case:** change every status to `PENDING`; stdout still prints the headers, `Tổng doanh thu: 0`, and the two grouped reports have no data rows.
5. **Extension:** add revenue by SKU using `flatMap` and `Collectors.reducing(BigDecimal.ZERO, OrderLine::subtotal, BigDecimal::add)`. Verify that the output is derived only from PAID orders, then cross-check the sum of revenue by SKU against `840000`.

When moving to real data, a sensible sequence is: confirm payment conditions and monetary definitions → normalize/validate order lines → filter the right set of orders → transform and aggregate by order or SKU → verify total amounts and quantities → present the results. By splitting the work into clear functions, you can swap the data source from a `List` to a repository/API while keeping most of the analytical logic intact, provided the data is loaded and preserves the right semantics.