# Preserving Data Context When Flattening Parent-Child Relationships

In the **Filtering and Transforming Elements** chapter of the **Java Stream API**, `flatMap` helps turn a structure of many parent objects, each containing a collection of child objects, into a flat stream of elements. This is a common operation when processing orders and line items, departments and employees, lessons and questions, or multi-level tree structures.

A common pitfall is that **child elements often do not contain enough information about the parent**. If you only extract child elements using `flatMap`, downstream steps may no longer know which order a line item belongs to, which department a person belongs to, or which branch generated a record. This lesson shows how to **attach parent context during flattening**, choose an appropriate output data structure, and handle situations such as empty child lists, filtering, duplicate keys, ordering, and processing cost.

## 1. The Problem: One Parent Can Have Many Children

Suppose a sales system stores a list of orders. Each order has an order ID, a customer ID, and multiple line items; each line item has a product SKU, quantity, and unit price.

~~~text
Order O-100 (customer C-01)
  ├─ Pen  (PEN): 2 × 10.000
  └─ Book (BOOK): 1 × 50.000

Order O-101 (customer C-02)
  └─ Pen  (PEN): 1 × 12.000

Order O-102 (customer C-03)
  └─ (no line items)
~~~

If we need to export a table of line items for reporting, we want results like:

| Order ID | Customer ID | Product | Quantity | Amount |
| --- | --- | --- | ---: | ---: |
| O-100 | C-01 | PEN | 2 | 20.000 |
| O-100 | C-01 | BOOK | 1 | 50.000 |
| O-101 | C-02 | PEN | 1 | 12.000 |

Each row in the table is **one child element together with parent info**. Three orders produce three output rows; order `O-102` has no line items so it does not appear. The number of output rows from flattening is the total number of children across parents, not the number of parents.

This is an important distinction when transforming hierarchical data into flat records for filtering, grouping, summing, exporting CSV, or passing through an API.

## 2. Distinguishing `map` and `flatMap`

Both `map` and `flatMap` are *intermediate operations* in a lazy pipeline. However, their result types differ:

| Transformation | Function applied per parent | Output type |
| --- | --- | --- |
| `map` | Parent → one value, such as a `List<Line>` or `Stream<Line>` | `Stream<List<Line>>` or `Stream<Stream<Line>>`: still has one nesting layer |
| `flatMap` | Parent → a `Stream<Line>` of 0, 1, or many children | `Stream<Line>`: merges sub-Streams into a flat stream |
| `flatMap` preserving context | Parent → a `Stream<Row>`, each `Row` containing parent and child info | `Stream<Row>`: flat stream still knows each child's origin |

Illustrated with simple Java types:

~~~java
// Assume orders has type List<Order> and each Order has lines().
Stream<Stream<Line>> nested = orders.stream()
        .map(order -> order.lines().stream());

Stream<Line> flattened = orders.stream()
        .flatMap(order -> order.lines().stream());
~~~

The `flattened` version only contains `Line`. If `Line` does not carry `orderId` itself, we have lost the parent–child relationship for subsequent processing steps.

**Practical rule:** When an output element needs to know its parent, construct a result object combining parent and child information **inside the function passed to `flatMap`**:

~~~java
orders.stream()
    .flatMap(order -> order.lines().stream()
        .map(line -> /* build result from both order and line */));
~~~

The `order` variable is captured in the *lexical scope* of the outer lambda; the inner lambda uses it to construct each record. This is a clean way to preserve context without looking up the parent from the child after flattening.

## 3. Complete Example: From Orders to Context-Aware Records

The example below uses **Java 17+** for `record` and `Stream.toList()`. Each output row includes `orderId`, `customerId`, product details, and line amount.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class OrderFlatteningDemo {

    record Line(String sku, int quantity, BigDecimal unitPrice) {}

    record Order(String id, String customerId, List<Line> lines) {}

    record LineRow(
            String orderId,
            String customerId,
            String sku,
            int quantity,
            BigDecimal amount
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-100", "C-01", List.of(
                        new Line("PEN", 2, new BigDecimal("10000")),
                        new Line("BOOK", 1, new BigDecimal("50000"))
                )),
                new Order("O-101", "C-02", List.of(
                        new Line("PEN", 1, new BigDecimal("12000"))
                )),
                new Order("O-102", "C-03", List.of())
        );

        List<LineRow> rows = orders.stream()
                .flatMap(order -> order.lines().stream()
                        .map(line -> new LineRow(
                                order.id(),
                                order.customerId(),
                                line.sku(),
                                line.quantity(),
                                line.unitPrice().multiply(
                                        BigDecimal.valueOf(line.quantity())
                                )
                        )))
                .toList();

        rows.forEach(System.out::println);
    }
}
~~~

Output:

~~~text
LineRow[orderId=O-100, customerId=C-01, sku=PEN, quantity=2, amount=20000]
LineRow[orderId=O-100, customerId=C-01, sku=BOOK, quantity=1, amount=50000]
LineRow[orderId=O-101, customerId=C-02, sku=PEN, quantity=1, amount=12000]
~~~

Reading the pipeline from outside in:

1. `orders.stream()` creates a Stream of orders.
2. For each `order`, `order.lines().stream()` creates a Stream of line items for that exact order.
3. `map(line -> new LineRow(...))` creates **one result object per line item**, pulling data from both `order` and `line`.
4. `flatMap` concatenates the resulting line streams into a single Stream.
5. `toList()` is the terminal operation, triggering processing and collecting results into a list.

By keeping `orderId` and `customerId` right during transformation, downstream steps can group by order or customer without looking up another table. Using `BigDecimal` for money avoids rounding inaccuracies typical of binary floating-point numbers in financial calculations.

> **Version note:** `record` has been officially supported since Java 16 and `Stream.toList()` since Java 16. On Java 8–15, replace `record`s with regular DTO/POJO classes and replace `toList()` with `collect(Collectors.toList())`. The `flatMap` + `map` pattern for preserving context stays the same.

## 4. Three Ways to Represent Parent–Child Context

There are several ways to design output records. The choice depends on what information downstream genuinely needs to consume.

### 4.1. Copying Required Fields into a Flat DTO

Like `LineRow` in the example above:

~~~java
record LineRow(
        String orderId,
        String customerId,
        String sku,
        int quantity,
        BigDecimal amount
) {}
~~~

**Suitable when** exporting reports, sending over an API, saving snapshots, or transferring data across system layers. A DTO explicitly defines the data contract and prevents downstream code from having to know the parent object model.

The advantage is easy control over which fields are exposed; in return, some parent values may be repeated across multiple child records. If the DTO contains computed values, define snapshot timing and consistency rules when sources change.

### 4.2. Keeping Parent and Child References in One Object

When processing internally and many properties of both objects are needed, you can retain the references directly:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> pairs = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new LineWithOrder(order, line)))
        .toList();

// Downstream steps still have access to both parent and child:
pairs.forEach(pair -> System.out.println(
        pair.order().id() + ": " + pair.line().sku()
));
~~~

This avoids copying many fields and is convenient when business logic still needs the parent object. However, the result record **holds a reference to the entire parent**, which can drag along a larger object graph, mutable state, and unneeded data. If `Order` is an ORM-managed entity, passing the entity outside transaction boundaries can also trigger lazy-loading errors or leak persistence-layer details.

### 4.3. Using Key–Value Pairs for Short Operations

You can use `Map.entry` (Java 9+):

~~~java
var pairs = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> java.util.Map.entry(order.id(), line)))
        .toList();
~~~

Here each element is a `Map.Entry<String, Line>`; `getKey()` is the order ID, and `getValue()` is the line item. This is just a **pair of values**, not a single `Map`. `Map.entry` does not accept `null` keys or values.

Value pairs suit short pipelines with few fields; when context involves multiple properties or needs clear field names, a dedicated `record` or DTO is usually easier to read and maintain.

## 5. Placing `filter` in the Right Spot to Preserve Business Meaning

In a parent–child pipeline, you can filter **parents**, filter **children**, or filter by conditions combining both:

~~~java
// Based on OrderFlatteningDemo above:
List<LineRow> selected = orders.stream()
        .filter(order -> order.customerId().equals("C-01"))
        .flatMap(order -> order.lines().stream()
                .filter(line -> line.quantity() >= 2)
                .map(line -> new LineRow(
                        order.id(),
                        order.customerId(),
                        line.sku(),
                        line.quantity(),
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        )
                )))
        .toList();
~~~

This pipeline only traverses lines for customer `C-01` and only keeps lines with quantity at least 2. The result is the `PEN` line belonging to order `O-100`.

A few guidelines for placing filters:

- **Filter parents before `flatMap`** if no children of a non-qualifying parent need processing. This avoids creating unnecessary sub-Streams and DTOs.
- **Filter children before `map` to DTO** if the condition only relies on child data, such as quantity or SKU. That avoids constructing DTOs only to discard them.
- **Filter after creating the DTO** when the condition genuinely requires aggregated data from both parent and child or a computed DTO field.
- **Order is not always interchangeable**: filtering by the number of lines in a parent before flattening differs from filtering individual lines and then counting.

Be careful when using `filter` with side-effecting lambdas: the Stream API may optimize execution, especially under certain terminal operations; do not use side effects to record parent–child relationships. Put context directly into the output value produced by `map`.

## 6. Parents Without Children: Flattening vs Keeping All Parents

`flatMap` produces **0 elements** when the mapping function returns an empty Stream. That is why order `O-102` does not appear in the `LineRow` table.

~~~java
List<LineRow> rows = orders.stream()
        .flatMap(order -> order.lines().stream()
                .map(line -> new LineRow(
                        order.id(),
                        order.customerId(),
                        line.sku(),
                        line.quantity(),
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        )
                )))
        .toList();

// rows contains no entry for O-102.
~~~

If the task is **one report row per child**, this behavior is right. If the requirement is **one row per parent, including parents with no children**, do not expect `flatMap` to automatically fabricate an empty parent row.

For example, calculating total amount **per order**, including empty orders:

~~~java
import java.math.BigDecimal;
import java.util.List;

record OrderTotal(String orderId, BigDecimal amount) {}

List<OrderTotal> totals = orders.stream()
        .map(order -> new OrderTotal(
                order.id(),
                order.lines().stream()
                        .map(line -> line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity())
                        ))
                        .reduce(BigDecimal.ZERO, BigDecimal::add)
        ))
        .toList();
~~~

The `totals` result includes `O-100 = 70000`, `O-101 = 12000`, and **`O-102 = 0`**. Here `map` creates exactly one `OrderTotal` per order; the inner `reduce` returns the identity value 0 when there are no line items.

If you need results where every parent appears at least once like a SQL **left outer join**, design an explicit representation for the childless case, such as a row with an empty `Optional<Line>`. Do not fabricate a dummy `Line` with an arbitrary product code: fake data is easily miscounted as a real line item.

## 7. Going from a Flat List Back to Grouping by Parent

One benefit of retaining the parent ID in each DTO is that you can perform further aggregations using Java Stream API collectors.

Suppose we have `rows` of type `List<LineRow>` from the initial example:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> amountByOrder = rows.stream()
        .collect(Collectors.groupingBy(
                LineRow::orderId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        LineRow::amount,
                        BigDecimal::add
                )
        ));

System.out.println(amountByOrder.get("O-100")); // 70000
System.out.println(amountByOrder.get("O-101")); // 12000
~~~

`groupingBy` groups lines by `orderId` and `reducing` sums the amount of each line. This is **re-grouping by key** of flattened data; it does not restore the entire original structure if other fields were dropped.

Two limitations to keep in mind:

1. **Parents without children do not appear in `rows`**, so `groupingBy` on `rows` will not generate a key for `O-102`. If results for all orders are required, aggregate on the `orders` list like in the `OrderTotal` example, or explicitly add empty keys.
2. **Keys must uniquely identify the parent.** If `orderId` is only unique within a store or tenant, grouping solely by `orderId` can accidentally merge data. Use a composite key such as `(tenantId, orderId)` when required by business rules.

Similarly, you can group by customer or product if the DTO already holds the corresponding fields. Using `Collectors.groupingByConcurrent` for parallel optimization is only appropriate when ordering, collector, and key constraints of the problem are satisfied; grouping data itself never allows ignoring key correctness.

## 8. Flattening Multiple Levels While Preserving the Full Path

With multi-level data, such as company → department → employee, decide which ancestor fields remain useful after each flattening step.

~~~text
Company
  └─ Department
       └─ Employee
~~~

You can nest `flatMap` calls and reference parent variables from outer lambda scopes:

~~~java
// Assume Company::departments, Department::employees exist
// and each object has an id() method.
record EmployeeRow(
        String companyId,
        String departmentId,
        String employeeId
) {}

List<EmployeeRow> people = companies.stream()
        .flatMap(company -> company.departments().stream()
                .flatMap(department -> department.employees().stream()
                        .map(employee -> new EmployeeRow(
                                company.id(),
                                department.id(),
                                employee.id()
                        ))))
        .toList();
~~~

At the moment `EmployeeRow` is constructed, all three variables—`company`, `department`, and `employee`—are in scope, so we preserve the full path. Likewise, for order → line item → extra attribute, you can carry order ID, line ID, and attribute key.

Each `flatMap` layer can drop parents that have no children at the next level. For reports needing full statistics across every level, consider preserving the hierarchical structure or building result tables with explicit rules for empty branches.

## 9. Order, Cardinality, and Identity of Output Elements

Several invariants help verify flattening results:

**Cardinality.** With no filtering, no skipped elements, and no `null` in child lists, the total row count equals:

~~~text
totalRows = sum(order.lines().size() for each order)
~~~

For the introductory example: `2 + 1 + 0 = 3`. If `filter` is added, row count equals the number of child elements matching the selected conditions.

**Order.** With an encounter-ordered `List` source, a sequential pipeline of `flatMap` and `map` preserves parent order as well as child order within each parent. If using an unordered source or calling `unordered()`, do not rely on output order. Under parallel execution, `forEach` does not guarantee observed order, whereas terminal operations with an encounter-order contract like `toList()` can still produce a list in source order when the stream is ordered.

**Identity.** Two orders can share the same `PEN` product. Keeping only `sku` is insufficient to distinguish two different lines. Retain `orderId` and, if multiple lines with the same `sku` can exist in one order, add `lineId` or a stable line-item identifier.

**Consistency.** DTO records copy parent fields at the moment the pipeline executes; if parents and child lists are mutated concurrently, results can be inconsistent or throw errors like `ConcurrentModificationException`. Use snapshots or proper concurrency controls instead of mutating source collections while a Stream is traversing them.

## 10. `null` Child Lists, `null` Child Elements, and Data Contracts

In Java models you design yourself, standardize on: **no children is represented by an empty list**, rather than `null`. This lets `order.lines().stream()` run safely.

If legacy data may return `null` for an entire child list, handle it explicitly at the boundary:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> safeRows = orders.stream()
        .flatMap(order -> {
            List<Line> lines = order.lines();
            return (lines == null
                    ? java.util.stream.Stream.<Line>empty()
                    : lines.stream())
                    .map(line -> new LineWithOrder(order, line));
        })
        .toList();
~~~

This adopts the convention that a `null` child list means **no line items**. Apply it only when the data contract genuinely permits that interpretation. If `null` indicates corrupt data, validating and throwing a descriptive error may be more appropriate.

If **an element inside a child list itself is `null`**, calling `line.sku()` will fail. Do not silently add `filter(Objects::nonNull)` if dropping rows skews reports; decide whether to discard, log errors, or reject inputs according to business requirements.

The `record` types in the examples are concise data containers, yet by default they **do not validate** inputs automatically. In particular, a record holding `List<Line>` does not make the inner list immutable if the caller passes a mutable list. Use `List.copyOf(lines)` and validate data in the constructor when stronger immutability is needed.

## 11. Optimization and Scalability

### 11.1. Processing Is Lazy, Yet the Terminal Operation Decides Materialization

`flatMap` and `map` are intermediate operations, so they do not collect all result rows upon declaration. The pipeline processes elements when a terminal operation like `toList()`, `collect()`, `count()`, `reduce()`, or `forEach()` executes.

~~~java
long rowsCount = orders.stream()
        .flatMap(order -> order.lines().stream())
        .count();
~~~

This counts child lines without requiring DTO list creation to store them, though the JDK may apply optimizations suited to the source and pipeline. If the final goal is just an aggregate, consider a collector or direct operation instead of calling `toList()` and iterating again.

For very large datasets, `toList()` holds all output rows in memory. Using a pipeline with an appropriate terminal operation or processing in batches helps bound the memory held for results.

### 11.2. Keep Lambdas Free of Shared State

A common trap is using a mutable external variable to "remember" the current parent:

~~~java
// Unsafe approach, especially under parallel processing:
Order[] current = new Order[1];

orders.stream()
        .peek(order -> current[0] = order)
        .flatMap(order -> order.lines().stream())
        .map(line -> current[0].id() + ":" + line.sku())
        .toList();
~~~

In some pipeline execution modes, especially parallel ones, `current[0]` can be overwritten by work on another parent; moreover, side effects inside `peek` are not a reliable mechanism for holding context. Replace this with nested lambdas that build the DTO from **that iteration's own `order`**.

Pure or side-effect-free functions also make parallel processing and testing far more predictable.

### 11.3. `mapMulti` Is an Option When Suitable (Java 16+)

`mapMulti` allows one input element to emit 0, 1, or many output elements via a consumer, without creating a sub-`Stream` on each mapping step:

~~~java
record LineWithOrder(Order order, Line line) {}

List<LineWithOrder> rows = orders.stream()
        .<LineWithOrder>mapMulti((order, sink) -> {
            for (Line line : order.lines()) {
                sink.accept(new LineWithOrder(order, line));
            }
        })
        .toList();
~~~

`mapMulti` also preserves context by including `order` in every output element. This form can reduce sub-Stream creation overhead in certain cases, though `flatMap` is often more readable when the operation is naturally expressed with `stream()`. Prioritize clarity and only optimize based on real measurements.

### 11.4. Database Relationships and Resources

With JPA/Hibernate or similar ORMs, calling `order.lines()` may trigger a query to load the child list. Iterating over many orders can cause **N+1 queries** or lazy-loading failures outside a transaction. Using `flatMap` does not automatically optimize database queries.

If large volumes of data need flattening, consider query projections or database joins, appropriate fetch/batch strategies, and pagination. Check for duplicate parent rows caused by joins, composite keys, and childless-parent behavior. Avoid loading entire entity graphs into memory just to export a few fields.

If a Stream is created from a resource-backed source such as `Files.lines`, adhere to resource-closing lifecycles with `try-with-resources`. Plain `List` collections themselves do not need closing. Although `flatMap`'s contract closes Streams returned by its mapper once processed, do not use that as a substitute for explicitly managing I/O source lifecycles where the source is created.

## 12. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cannot identify which order a child line belongs to | `flatMap` returns `Line` directly, dropping parent info | Construct `LineRow` or `LineWithOrder` right inside `flatMap`'s lambda. |
| Empty orders vanish from the report | `flatMap` on an empty list emits 0 rows | If all orders are needed, aggregate from the parent Stream or define a representation for childless parents. |
| Two lines get merged when grouping or putting into a Map | Grouping key only uses `sku` or `orderId`, which is not unique enough | Identify the business key; may need `tenantId`, `orderId`, and `lineId`. |
| Unexpected order changes | Unordered source or `forEach` terminal on a parallel Stream | Preserve encounter order per source/terminal contract or sort output by an explicit key. |
| `NullPointerException` | `lines` or a child element is `null` | Standardize on empty collections; validate data and handle `null` intentionally. |
| Memory spikes | Creating too many DTOs or retaining whole parent entities; materializing all with `toList()` | Carry only needed fields, aggregate directly, process in batches. |
| Wrong results under parallelism | Storing current parent in an external mutable variable | Capture parent in nested lambda and build independent results per child. |
| Unexpectedly many SQL queries | `order.lines()` lazily loads associations per order | Review query strategy, projections, and batching in the persistence layer. |

## 13. Self-Check Exercises

### Exercise 1. Identifying Where Context Is Lost

~~~java
List<Line> lines = orders.stream()
        .flatMap(order -> order.lines().stream())
        .toList();
~~~

**Question:** Why can you not reliably infer `orderId` from each `Line` in the result?

**Answer:** Because the `Line` type in the model does not contain `orderId`. After flattening, there is no explicit link from a child line back to its `Order` object. Construct `LineRow(order.id(), ...)` or `LineWithOrder(order, line)` while `order` is still in lambda scope.

### Exercise 2. Choosing `map` or `flatMap`

**Requirement:** Produce a report containing **one total-amount row per order**, including orders with no line items.

**Answer:** Use `orders.stream().map(order -> new OrderTotal(...))`, and use `reduce(BigDecimal.ZERO, BigDecimal::add)` over that order's own line items. If you flatten first and then group, you would need an extra step to add back orders with no line items.

### Exercise 3. Counting Rows and Identifying Customers

Given data:

~~~text
O-1 / C-A: [PEN, BOOK]
O-2 / C-B: []
O-3 / C-A: [PEN]
~~~

**Question:** How many rows does `flatMap` carrying parent IDs produce? How many rows belong to customer `C-A`?

**Answer:** **3 rows** in total: two from `O-1` and one from `O-3`; customer `C-A` has **3 rows**. Order `O-2` produces no rows because its child list is empty.

### Exercise 4. Replacing a Shared State Variable

**Requirement:** Export `(departmentId, employeeId)` across multiple departments in a parallel pipeline. Should you use an external `currentDepartmentId` variable updated while iterating each department?

**Answer:** No. An external variable can be overwritten by multiple tasks, attaching the wrong department ID to employees. Use:

~~~java
record EmployeeRef(String departmentId, String employeeId) {}

List<EmployeeRef> refs = departments.parallelStream()
        .flatMap(department -> department.employees().stream()
                .map(employee -> new EmployeeRef(
                        department.id(),
                        employee.id()
                )))
        .toList();
~~~

Context data is taken directly from the `department` variable of that exact mapping step, without relying on shared state.

## 14. Takeaways and Application

- **Preserve context during flattening:** `flatMap(parent -> children.stream().map(child -> result(parent, child)))` is the core pattern.
- **Choose output structures by purpose:** flat DTOs for reports/APIs; parent–child pairs for internal processing; composite keys for grouping or unique identification.
- **Understand element counts:** flattening yields 0..N results per parent; empty parents disappear unless the application explicitly defines how to retain them.
- **Filter and aggregate at the right level:** filter parents before `flatMap` when possible; use `map` on parents if every parent requires one record even without children.
- **Respect pipeline contracts:** lambdas should avoid shared state; consider encounter order, null handling, materialization cost, and how data sources are loaded.

**Main idea:** `flatMap` solves *merging* child data into a single Stream, while the **identity, context, and business meaning of the parent–child relationship** must be captured in the result element you design. Keeping full context from the start makes downstream `filter`, `collect`, `groupingBy`, parallel processing, and data export clearer, easier to verify, and less error-prone.
