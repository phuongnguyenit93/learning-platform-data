# Joining Data Through a Map Index Instead of Expensive Nested Loops

In the **Practical Data Processing Patterns** chapter of the **Java Stream API**, many pipelines process one list and need to enrich elements from another list. For instance, from each order we need the customer's name; from each sales line we need product details; or from each event we need service configuration. This is a **key-based join**.

The simplest approach is searching the second list for every element of the first list. Yet with hundreds of thousands of orders and tens of thousands of customers, repeated linear scans become a bottleneck. A better pattern is **indexing into a `Map` once**, then looking up by key inside a `map`, `filter`, or `flatMap` pipeline.

This lesson shows how to improve lookup cost from **O(N × M)** to **O(N + M)** *on average under hash-based lookup*, while preserving join semantics: missing keys, duplicate keys, one-to-one/one-to-many joins, result ordering, and memory limits. The goal is not merely "running faster", but **never silently dropping or mis-joining business data**.

## 1. Sample Problem: Orders and Customers

Suppose we have two sources:

~~~java
record Customer(String id, String name) {}

record Order(
        String id,
        String customerId,
        java.math.BigDecimal amount
) {}
~~~

Data:

~~~text
customers:
  C-01 -> An
  C-02 -> Bình
  C-03 -> Chi

orders:
  O-1 -> C-01, 100.00
  O-2 -> C-02,  50.00
  O-3 -> C-01,  20.00
  O-4 -> C-99,  35.00
~~~

Primary requirement: for every order with a matching customer, produce a record:

~~~text
(orderId, customerId, customerName, amount)
~~~

Expected output for an **inner join**:

~~~text
O-1 -> C-01 -> An    -> 100.00
O-2 -> C-02 -> Bình  -> 50.00
O-3 -> C-01 -> An    -> 20.00
~~~

Order `O-4` references `C-99`, which is absent from the customer list, so it does not appear in the **inner join**. However, in a data-control report, we must not pretend that order does not exist: we need a way to record or separately query **unmatched** records.

Because `C-01` appears in two orders, the relationship in the `Order -> Customer` direction is **many-to-one**: multiple orders reference one customer. When building the customer index, each `customerId` must correspond to exactly one customer by contract.

## 2. Easy to Write, Costly to Run: Linear Search Inside a Loop

A common sequential implementation:

~~~java
import java.util.ArrayList;
import java.util.List;

List<EnrichedOrder> result = new ArrayList<>();

for (Order order : orders) {
    for (Customer customer : customers) {
        if (customer.id().equals(order.customerId())) {
            result.add(new EnrichedOrder(
                    order.id(),
                    customer.id(),
                    customer.name(),
                    order.amount()
            ));
            break;
        }
    }
}
~~~

`EnrichedOrder` is the result record declared in the complete program later.

The outer loop iterates `N` orders; the inner loop can scan up to `M` customers per order. When a key is missing, it must typically inspect the entire customer list.

A Stream version with the same poor complexity:

~~~java
List<EnrichedOrder> joined = orders.stream()
        .flatMap(order -> customers.stream()
                .filter(c -> c.id().equals(order.customerId()))
                .limit(1)
                .map(c -> new EnrichedOrder(
                        order.id(), c.id(), c.name(), order.amount()))
        )
        .toList();
~~~

This expresses the lookup with `flatMap`/`filter`, yet **still performs a scan over `customers` for each order**. Writing declaratively does not automatically turn linear search into indexed lookup.

### Cost Analysis

Notation:

- `N`: number of orders.
- `M`: number of customers.
- `K`: number of output records produced.

With nested loops or nested Streams as above:

- **Worst-case time:** O(N × M) to locate customers.
- **Auxiliary lookup memory:** near O(1), excluding O(K) for results.
- If every order happens to find its customer near the front of the list, actual time may be lower; however, there is no guarantee as data grows or order changes.

For instance, `N = 200,000` orders and `M = 50,000` customers can trigger a huge number of ID comparisons. Never dismiss the cost as "negligible" just because a tiny test dataset of a few dozen rows runs quickly.

## 3. Optimal Pattern: Build a Map Index Once

When each customer has a unique `id`, convert the customer list into:

~~~text
Map<CustomerId, Customer>

"C-01" -> Customer("C-01", "An")
"C-02" -> Customer("C-02", "Bình")
"C-03" -> Customer("C-03", "Chi")
~~~

You can use `Collectors.toMap`:

~~~java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

Map<String, Customer> customerById = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

Explanation:

1. `Customer::id` supplies the `String` key.
2. `Function.identity()` keeps the `Customer` object itself as the value.
3. `collect(Collectors.toMap(...))` materializes the `Map` index **once**.
4. Each order afterward only needs `customerById.get(order.customerId())` to look up customer details.

With a typical `HashMap`, `get` has expected O(1) complexity when `hashCode`/`equals` and key distribution behave well. Thus overall cost becomes:

~~~text
Build customer index: O(M) average
Lookup for N orders:  O(N) average
Create K results:     O(K)

Total:                O(M + N + K)
Index memory:         O(M)
~~~

In a many-to-one join where each order emits at most one record, `K <= N`, so this is often summarized as **O(M + N)** expected time. That is not an absolute worst-case bound for every `Map`: real performance depends on Map implementation, hashing, collisions, and key-computation cost.

**Key trade-off:** We trade O(M) extra memory to eliminate repeated scans of the customer list. If the indexed side does not fit comfortably in memory, choose another strategy such as a database join, batched processing, or external join.

## 4. Complete Program with Inner Join, Left Join, and Anti Join

The code below is a self-contained program for **Java 17+**, using `record` and `Stream.toList()` (Java 16+). Save it as `MapJoinDemo.java` to run.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MapJoinDemo {

    record Customer(String id, String name) {}

    record Order(String id, String customerId, BigDecimal amount) {}

    record EnrichedOrder(
            String orderId,
            String customerId,
            String customerName,
            BigDecimal amount
    ) {}

    record LeftJoinedOrder(Order order, Optional<Customer> customer) {}

    static Map<String, Customer> indexCustomers(
            List<Customer> customers) {

        return customers.stream()
                .collect(Collectors.toMap(
                        Customer::id,
                        Function.identity()
                ));
    }

    // Inner join: keep only orders with a matching customer.
    static List<EnrichedOrder> innerJoin(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .flatMap(order -> {
                    Customer customer =
                            customerById.get(order.customerId());

                    if (customer == null) {
                        return Stream.<EnrichedOrder>empty();
                    }

                    return Stream.of(new EnrichedOrder(
                            order.id(),
                            customer.id(),
                            customer.name(),
                            order.amount()
                    ));
                })
                .toList();
    }

    // Left join: keep every order, even without a customer.
    static List<LeftJoinedOrder> leftJoin(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .map(order -> new LeftJoinedOrder(
                        order,
                        Optional.ofNullable(
                                customerById.get(order.customerId()))
                ))
                .toList();
    }

    // Anti join: take only orders referencing non-existent customers.
    static List<Order> unmatchedOrders(
            List<Order> orders,
            Map<String, Customer> customerById) {

        return orders.stream()
                .filter(order -> !customerById.containsKey(
                        order.customerId()))
                .toList();
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
                new Customer("C-01", "An"),
                new Customer("C-02", "Bình"),
                new Customer("C-03", "Chi")
        );

        List<Order> orders = List.of(
                new Order("O-1", "C-01", new BigDecimal("100.00")),
                new Order("O-2", "C-02", new BigDecimal("50.00")),
                new Order("O-3", "C-01", new BigDecimal("20.00")),
                new Order("O-4", "C-99", new BigDecimal("35.00"))
        );

        Map<String, Customer> customerById =
                indexCustomers(customers);

        List<EnrichedOrder> matched =
                innerJoin(orders, customerById);

        List<LeftJoinedOrder> allOrders =
                leftJoin(orders, customerById);

        List<Order> unmatched =
                unmatchedOrders(orders, customerById);

        System.out.println("Inner count: " + matched.size());
        // 3

        matched.forEach(item ->
                System.out.println(
                        item.orderId() + " -> " +
                        item.customerName() + ": " +
                        item.amount()
                ));

        System.out.println("Left count: " + allOrders.size());
        // 4

        System.out.println("Missing order IDs: " +
                unmatched.stream().map(Order::id).toList());
        // [O-4]

        System.out.println(
                allOrders.get(3).customer().isEmpty());
        // true: O-4 could not find C-99.
    }
}
~~~

The example uses `Optional<Customer>` in the result record **to explicitly model customer presence/absence**, rather than substituting a fake name like `"UNKNOWN"` that could collide with a real name. In production storage models, you can also use a dedicated result type representing `Matched`/`Missing` or a status flag with error details.

Run:

~~~bash
javac MapJoinDemo.java
java MapJoinDemo
~~~

Key output:

~~~text
Inner count: 3
O-1 -> An: 100.00
O-2 -> Bình: 50.00
O-3 -> An: 20.00
Left count: 4
Missing order IDs: [O-4]
true
~~~

`get` and `containsKey` calls on `customerById` are **index reads**. The Map is fully built before the orders Stream runs, and no keys are added or removed during the join.

## 5. Three Join Types and Missing-Key Policies

Joining two sources has no single universal meaning. Define the join type before writing the pipeline.

| Type | Condition for Including an Order | Example with `O-4` |
| --- | --- | --- |
| **Inner join** | At least one matching customer exists | Excluded from joined output |
| **Left join** | Keeps every order; customer side may be absent | Keeps `O-4` marked as missing customer |
| **Anti join** | No matching customer exists | Retains only `O-4` in an audit list |

### 5.1. Inner Join: Never Hide Bad Data

`innerJoin(...)` fits when only successfully matched pairs are needed. However, if the system requires reporting on all orders, `O-4` must not vanish silently.

A safe design **also outputs the unmatched count**, or runs an anti join against the same prebuilt index Map. This separates "no input data" from "data present with broken relationships".

### 5.2. Left Join: Preserve One Result per Order

`leftJoin(...)` preserves the exact count and order of `orders` when using an ordered `List` source and an order-preserving pipeline. `Optional.empty()` represents the missing relationship.

Do not inject a placeholder name like `"Unknown"` inside aggregation logic and treat it as a real customer. If a UI needs a fallback label, apply that placeholder at the presentation layer.

### 5.3. Anti Join: Detecting Orphan Data

~~~java
List<Order> missing = orders.stream()
        .filter(order -> !customerById.containsKey(
                order.customerId()))
        .toList();
~~~

This pattern checks *referential integrity*. It is widely useful in ETL, migrations, data sync, and source-quality testing.

Using `containsKey` distinguishes an **absent** key from a key mapped to `null` in Maps that permit nulls. This lesson intentionally builds a Map of non-null `Customer` values, so `get(...) == null` also implies absence; still, `containsKey` states key-existence intent clearly.

## 6. Duplicate Keys: You Cannot Build a Unique Index by Ignoring Data

`Collectors.toMap(Customer::id, Function.identity())` **throws `IllegalStateException` when two customers share the same ID**:

~~~java
List<Customer> duplicated = List.of(
        new Customer("C-01", "An"),
        new Customer("C-01", "Anh")
);

// IllegalStateException: duplicate key
Map<String, Customer> invalidIndex = duplicated.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

This may be **exactly what you want** if `Customer.id` is contracted to be unique. The exception surfaces contract-violating source data rather than silently picking an arbitrary customer.

### 6.1. Distinguish Conflicts from One-to-Many Relationships

- If every ID must be unique: **raise an error or reject invalid records via the validation workflow**.
- If an ID may have multiple record versions: **define a selection rule** using a reliable timestamp/version, or keep all versions via `groupingBy`.
- If the true key is `(tenantId, customerId)`: **construct a composite key**, rather than treating customers in different tenants as one person.
- If normalization causes collisions: **define how to resolve post-normalization duplicates**, rather than overwriting arbitrarily.

You can use the three-argument `toMap` overload to merge:

~~~java
Map<String, Customer> chosen = duplicated.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity(),
                (first, next) -> first
        ));
~~~

Yet `(first, next) -> first` is valid only when business rules allow **keeping the first element in a defined encounter order**. With unordered sources or when the latest record is required, this can return stale data. Never add a merge function merely to "silence the duplicate key error" without checking for data loss.

### 6.2. When You Need the Latest Version, Use a Deterministic Tie Criterion

Suppose you have:

~~~java
import java.time.Instant;

record CustomerVersion(
        String id,
        String name,
        Instant updatedAt,
        long version
) {}
~~~

Pick the record with the higher `version`:

~~~java
Map<String, CustomerVersion> latestById =
        versions.stream()
                .collect(Collectors.toMap(
                        CustomerVersion::id,
                        Function.identity(),
                        (a, b) -> {
                            if (a.version() > b.version()) return a;
                            if (b.version() > a.version()) return b;
                            throw new IllegalStateException(
                                    "Conflicting versions for " + a.id());
                        }
                ));
~~~

This snippet assumes `versions` is a collection of `CustomerVersion`. The rule intentionally rejects two records with the **same ID and same version** instead of picking arbitrarily based on execution schedule. In another system, you might use timestamp plus a deterministic tie-breaker; the policy must always come from the business.

## 7. One-to-Many: Use groupingBy to Build a List Index

`toMap` with a single value per key cannot directly represent **each customer having multiple orders** if you want to retain all orders.

When you need all orders per customer, invert the index:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> ordersByCustomerId = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));

System.out.println(ordersByCustomerId.get("C-01").size());
// 2
~~~

Here, the Map value is `List<Order>`, not a single `Order`. `groupingBy` preserves every order sharing a `customerId`.

Suppose an application needs **every customer paired with all their orders** for a report:

~~~java
record CustomerOrder(Customer customer, Order order) {}

List<CustomerOrder> pairs = customers.stream()
        .flatMap(customer -> ordersByCustomerId
                .getOrDefault(customer.id(), List.of())
                .stream()
                .map(order -> new CustomerOrder(customer, order)))
        .toList();

System.out.println(pairs.size()); // 3
~~~

The sample data yields three paired orders for existing customers. Customer `C-03` has no orders and does not appear in the pairs list; order `O-4` references `C-99` with no customer and also does not appear.

**Important regarding order:** With the pipeline above, results are ordered **by customer first, then orders within each customer's group** according to the source's encounter order. This may differ from streaming `orders` as the outer source. If the report requires preserving the original order list sequence, stream `orders` against the customer index instead.

### One-to-Many Cost

With `N` orders, `M` customers, and `K` emitted pairs, `groupingBy` typically builds the index in O(N) average time; scanning `M` customers and their groups adds O(M + K) work. Expected total is **O(N + M + K)**, with O(N) memory for grouped lists plus O(K) for output.

In **many-to-many** joins that can generate large pair counts, `K` can grow dramatically—up to the product of group sizes. No Map optimization eliminates the cost of actually materializing and processing `K` pairs when the business requires every combination.

## 8. Composite Keys: tenantId and customerId

A common join bug is using an **under-specified key**. For example, customer `C-01` may exist across multiple tenants. Keying by `customerId` alone cross-contaminates data.

Since Java 16, `record` offers a concise immutable composite key:

~~~java
record CustomerKey(String tenantId, String customerId) {}

record TenantCustomer(
        String tenantId,
        String customerId,
        String name
) {}

record TenantOrder(
        String id,
        String tenantId,
        String customerId
) {}
~~~

Build the index:

~~~java
Map<CustomerKey, TenantCustomer> byKey = tenantCustomers.stream()
        .collect(Collectors.toMap(
                c -> new CustomerKey(c.tenantId(), c.customerId()),
                Function.identity()
        ));
~~~

Lookup:

~~~java
List<String> names = tenantOrders.stream()
        .map(order -> byKey.get(
                new CustomerKey(order.tenantId(), order.customerId())))
        .filter(java.util.Objects::nonNull)
        .map(TenantCustomer::name)
        .toList();
~~~

`tenantCustomers` and `tenantOrders` are collections of those two records. A `record` automatically provides `equals` and `hashCode` over its components, making it ideal for Map keys **provided the components are immutable/stable**.

If your system uses mutable keys, mutating fields used by `equals`/`hashCode` after Map insertion breaks subsequent `get` lookups. Prefer immutable identifiers.

## 9. Key Normalization: Must Be Symmetric on Both Sides

Data from two systems may format IDs differently:

~~~text
Customer source: " c-01 "
Order source:    "C-01"
~~~

If business rules declare case and surrounding whitespace insignificant, normalize keys **the exact same way** both when building the Map and when querying it:

~~~java
import java.util.Locale;

static String canonicalId(String raw) {
    if (raw == null) {
        throw new IllegalArgumentException("Missing customer ID");
    }

    String result = raw.trim().toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException("Blank customer ID");
    }
    return result;
}
~~~

Index:

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                c -> canonicalId(c.id()),
                Function.identity()
        ));
~~~

Lookup:

~~~java
List<EnrichedOrder> joined = orders.stream()
        .flatMap(order -> {
            Customer customer = index.get(
                    canonicalId(order.customerId()));

            return customer == null
                    ? Stream.<EnrichedOrder>empty()
                    : Stream.of(new EnrichedOrder(
                            order.id(),
                            order.customerId(),
                            customer.name(),
                            order.amount()));
        })
        .toList();
~~~

ID normalization is a **business decision**, not a universal optimization trick. Some identifiers are case-sensitive or carry meaningful whitespace. If normalization collapses two previously distinct IDs into one, `toMap` throws duplicate key—a signal to resolve the conflict, not an exception to hide.

For complex Unicode, `trim`/`toUpperCase(Locale.ROOT)` is also not a universal canonicalization across all scripts or standards. Follow the canonicalization rule defined by your data system.

## 10. Never Silently Turn Null into a "Valid Key"

A join needs an explicit policy for missing keys:

- **`null` key in orders:** bad data, unassigned order, or a special customer type?
- **`null` key in customer table:** is a record without an ID allowed to exist?
- **Mapper returning `null` value:** `Collectors.toMap` does not behave identically to arbitrary custom Maps, and `null` values commonly cause collection to fail.
- **Key absent from Map:** a different data condition than the source key itself being `null`.

In problems with referential integrity constraints, validate non-null keys:

~~~java
import java.util.Objects;

Map<String, Customer> customerById = customers.stream()
        .collect(Collectors.toMap(
                customer -> Objects.requireNonNull(
                        customer.id(), "Customer ID is required"),
                Function.identity()
        ));
~~~

During lookup:

~~~java
String id = Objects.requireNonNull(
        order.customerId(), "Order customerId is required");

Customer customer = customerById.get(id);
~~~

Avoid doing this:

~~~java
String key = String.valueOf(order.customerId());
~~~

If `customerId == null`, that expression returns the string `"null"`, which could collide with a real ID and cause a false join. Similarly, replacing null with an empty string or default customer name is valid only when backed by an explicit business rule.

If the goal is not to reject data, route orders missing an ID into a **separate audit bucket** rather than mixing them with orders that have an ID but no matching customer.

## 11. Combining Lookup with Aggregation Without Storing Every Pair

In revenue reports, you sometimes only need totals per verified customer, not a `List<EnrichedOrder>` of every individual order.

Using the same index Map:

~~~java
import java.math.BigDecimal;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigDecimal> revenueByCustomer = orders.stream()
        .filter(order -> customerById.containsKey(
                order.customerId()))
        .collect(Collectors.toMap(
                Order::customerId,
                Order::amount,
                BigDecimal::add
        ));
~~~

Here:

- `filter` retains only orders whose customer ID is verified.
- `Order::customerId` supplies the aggregation key.
- `Order::amount` supplies the monetary amount.
- `BigDecimal::add` combines amounts per customer **with exact decimal arithmetic** when inputs come from exact decimal strings.
- The resulting Map keeps **one total per key**, without materializing all joined pairs.

With the sample data:

~~~text
C-01 -> 120.00
C-02 ->  50.00
~~~

Order `O-4` lacks a matching customer and is excluded from the **verified-customer** revenue report. If financial reporting requires the sum of all orders, do not silently drop `O-4`: sum the unmatched bucket separately or raise a data-quality error before finalizing the report.

### Do Not Round Inside the Merge Function

When summing money with `BigDecimal`, choose the **business rounding point** explicitly. If you need to sum all amounts accurately and round at the customer/invoice level, keep `BigDecimal::add` in the collector and apply `setScale(scale, mode)` in the final step. Rounding after every addition can make results depend on grouping order and diverge under parallel streams.

## 12. Build the Index Once and Reuse It Appropriately

A performance-killing bug is **rebuilding the Map inside every order step**:

~~~java
// Very expensive: rebuilds the entire Map inside every map step.
List<String> names = orders.stream()
        .map(order -> {
            Map<String, Customer> index = customers.stream()
                    .collect(Collectors.toMap(
                            Customer::id,
                            Function.identity()));
            Customer c = index.get(order.customerId());
            return c == null ? null : c.name();
        })
        .toList();
~~~

This can cost **O(N × M)** time plus repeated O(M) Map allocations, failing to solve the original bottleneck.

Build the index **outside** the pipeline:

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

List<String> names = orders.stream()
        .map(order -> index.get(order.customerId()))
        .filter(java.util.Objects::nonNull)
        .map(Customer::name)
        .toList();
~~~

Condition for reuse: customer data must remain valid/stable for the report's scope. If customers are updated after building the index, the Map does not automatically synchronize with the source list.

- If the application processes **snapshots**: build a fresh index per snapshot, or bind cached indexes to data versions.
- If the application reads **live mutable state**: establish synchronization, invalidation, or consistent source queries.
- If Map values are mutable objects: reading the index does not guarantee those objects' fields remain unchanged.

Avoid keeping a long-lived `static Map` without explicit refresh rules, because joined data can go stale even though lookups are fast.

## 13. Result Ordering: The Map Index Does Not Dictate Output Order

When `orders` is an ordered `List` and you write:

~~~java
List<EnrichedOrder> result = orders.stream()
        .flatMap(order -> {
            Customer customer = customerById.get(
                    order.customerId());

            if (customer == null) {
                return Stream.<EnrichedOrder>empty();
            }

            return Stream.of(new EnrichedOrder(
                    order.id(), customer.id(),
                    customer.name(), order.amount()));
        })
        .toList();
~~~

`toList()` preserves the encounter order of matched orders from the ordered Stream. **The fact that `HashMap` does not guarantee key iteration order does not disrupt this ordering**, because the pipeline iterates `orders` and only uses the Map for lookups.

Conversely:

~~~java
List<Customer> list = customerById.values().stream().toList();
~~~

The order of this list depends on the Map's iteration order; with `HashMap`, never rely on it. If you want customers sorted by ID, use `sorted(Comparator.comparing(Customer::id))`. If you need Map insertion order, supply `LinkedHashMap::new` when constructing the Map and iterate according to its contract.

**Derive ordering from business requirements**, not from incidental observations on one JDK run.

## 14. Parallelization: Read-Only Maps Are Safer Than Shared Mutable State

An index Map completely constructed **before** the pipeline starts and never modified during execution can be read concurrently across parallel tasks provided its values are also used safely without interference.

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));

List<EnrichedOrder> result = orders.parallelStream()
        .flatMap(order -> {
            Customer customer = index.get(order.customerId());

            if (customer == null) {
                return Stream.<EnrichedOrder>empty();
            }

            return Stream.of(new EnrichedOrder(
                    order.id(), customer.id(),
                    customer.name(), order.amount()));
        })
        .toList();
~~~

Here, the mapper only reads `index` and constructs new records; it never adds to or removes from the Map. Because `orders` is a `List` with encounter order, `toList` preserves the output order of matched orders even though internal element processing may execute out of order.

**Never do this:**

~~~java
Map<String, Long> counts = new java.util.HashMap<>();

orders.parallelStream().forEach(order ->
        counts.merge(order.customerId(), 1L, Long::sum));
~~~

Concurrent updates to a shared `HashMap` are **unsafe**. To aggregate counts by key, use `Collectors.groupingBy(..., counting())` or an appropriate concurrent collector:

~~~java
Map<String, Long> counts = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::customerId,
                Collectors.counting()
        ));
~~~

Do not assume `parallelStream()` is guaranteed to be faster. Splitting overhead, object allocations, hashing, and result merging can outweigh gains on small datasets or lightweight lambdas. For I/O or external API calls, parallel streams also require managing concurrency limits, timeouts, and idempotency.

## 15. Data Larger Than Memory: Do Not Try to Build One Giant HashMap

The Map-index pattern fits when the **indexed side** fits comfortably in memory. If both sides contain hundreds of millions of records, a `HashMap` holding all customers can exhaust heap memory.

Alternative strategies:

| Context | Approach |
| --- | --- |
| Data already resides in a database | Let the DBMS handle `JOIN`/indexes via queries instead of pulling whole tables into the JVM |
| One side small, one side huge | Build a Map for the small side; stream the large side in batches or sequentially |
| Both sides exceed RAM | External hash join, sort-merge join, or distributed data-processing engines |
| Data changes often and requires consistency | Use transactions/snapshots or versioned/invalidated caches |
| Millions of output pairs expected | Stream/write output incrementally instead of calling `toList()` on everything |
| Low-cardinality keys or many-to-many | Estimate output pair count `K` first; a Map index does not stop output explosion |

### Large I/O Source Example

Suppose order inputs are read from a file. You can build the customer index in memory once, then read orders **line by line** inside `try-with-resources`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// parseOrder is a parser function for a specific file format.
try (Stream<String> lines =
             Files.lines(Path.of("orders.txt"), StandardCharsets.UTF_8)) {

    long matchedCount = lines
            .map(line -> parseOrder(line))
            .filter(order -> customerById.containsKey(
                    order.customerId()))
            .count();

    System.out.println(matchedCount);
}
~~~

This is an **architectural illustration**, not a standalone program: `parseOrder` must be defined according to the actual file format and error contract. The key point is avoiding `Files.readAllLines(...)` and materializing a `List` of every order. `count()` here retains only a counter; calling `toList()` on all results still grows memory with output size.

The `Files.lines` resource must be closed; terminal operation `count` does not call `close()` automatically. If lazy I/O fails, surface the error clearly instead of treating failed reads as "unmatched".

## 16. HashMap Characteristics, Memory, and Key Correctness

### 16.1. O(1) Is an Expectation, Not an Absolute Law

A `HashMap` relies on key `hashCode` and `equals`. With good keys and reasonable load, `get` is very fast on average. Excessive hash collisions, expensive hash computations, or pathological data layouts can degrade performance.

If you use `TreeMap`, key lookups typically cost O(log M), in exchange for sorted keys and an explicit comparator. Choose a Map based on the **data contract** and real benchmarks.

### 16.2. Never Mutate Keys

If a key object contains fields used by `equals`/`hashCode`, modifying those fields after Map insertion can prevent `get` from finding the entry at its old hash bucket. Stick to `String`, numbers, enums, or records with stable components.

### 16.3. Do Not Assume a Map Is a Deep Snapshot

~~~java
Map<String, Customer> index = customers.stream()
        .collect(Collectors.toMap(
                Customer::id,
                Function.identity()
        ));
~~~

This Map holds **references to the original Customer objects**. With a `Customer` record having immutable `String` fields, the example is safe; if values are mutable classes, mutating them elsewhere alters what lookups return. `Map.copyOf(index)` only makes the Map structure unmodifiable, without deep-copying value objects.

### 16.4. Duplicate Keys Can Break Both Performance and Correctness

A single-valued Map per key cannot model "multiple entities per key" when identifiers are non-unique. The issue is not that Streams or Maps are slow, but the **data model**. Switch to `Map<K, List<V>>` via `groupingBy`, or fix key uniqueness before optimizing.

## 17. Comparing Approaches and Choosing One

| Approach | Expected Time | Extra Memory | Best When |
| --- | --- | --- | --- |
| Nested `for` loops | O(N × M) | O(1) besides output | Tiny datasets, complex matching logic, no index needed |
| `orders.stream()` + `customers.stream().filter(...)` per item | O(N × M) | O(1) besides output | Declarative syntax without fixing the lookup bottleneck |
| `toMap` customer index + lookup | O(N + M + K) | O(M) plus output | Unique customer keys, customer side fits in memory |
| `groupingBy` Map key → list | O(N + M + K) for matching sides and output | O(grouped elements) plus output | Multiple records per key must be retained |
| `TreeMap` index | Typically O(M log M + N log M + K) | O(M) plus output | Sorted keys or comparator-based lookup needed |
| Database join | Depends on engine, indexes, sizes, query plan | Server/query dependent | Data already lives in DB; filter/join near source |

Never overlook output-creation cost `K`. If the result is all many-to-many pairs in a huge group, building the output can dominate runtime even when the index builds fast.

## 18. Verify Correctness Before Benchmarking

A join optimization can run faster while **dropping unmatched records** or choosing wrongly on duplicate keys. Verify equivalence against a simple reference algorithm on small datasets first.

### 18.1. Key Invariants

When **each Order matches at most one Customer by key**:

~~~text
leftJoin.size() = orders.size()

innerJoin.size() + unmatchedOrders.size() = orders.size()

every EnrichedOrder has a valid customerId
every EnrichedOrder corresponds to an input Order
~~~

For the sample data:

~~~text
orders.size() = 4
innerJoin.size() = 3
unmatchedOrders.size() = 1
leftJoin.size() = 4
~~~

If multiple Customers are allowed per key, these count invariants **no longer hold** for many-to-many joins; that is why cardinality must be defined upfront.

### 18.2. Boundary Test Cases

| Case | Expectation |
| --- | --- |
| No customers, some orders | Inner join empty, anti join holds all orders, left join keeps all orders |
| Some customers, no orders | All order-driven outputs are empty |
| One customer, many orders | Every order joins cleanly with that customer |
| Duplicate customer key under unique contract | Indexing fails clearly |
| Order referencing missing ID | Recorded per missing-key policy |
| `null` or blank ID | Handled by validation, never coerced into another ID |
| Two tenants sharing a customerId | Composite key prevents cross-tenant joins |
| Keys differing in case or whitespace | Normalized only if contract allows, applied symmetrically |
| Ordered source | Result list preserves order if contract requires it |
| Parallel execution | Result content stays identical, no shared Map writes |
| Very large datasets | Measure Map build time, heap, and output creation cost |

### 18.3. Sample Logic Test

In the same class or with access to `MapJoinDemo`'s records:

~~~java
Map<String, Customer> index =
        MapJoinDemo.indexCustomers(customers);

var inner = MapJoinDemo.innerJoin(orders, index);
var left = MapJoinDemo.leftJoin(orders, index);
var missing = MapJoinDemo.unmatchedOrders(orders, index);

if (inner.size() != 3 ||
        left.size() != 4 ||
        missing.size() != 1 ||
        !"O-4".equals(missing.get(0).id())) {
    throw new AssertionError("Join result does not match specification");
}
~~~

On arbitrary datasets, also check equivalence **by key and pair counts**, not just collection size. Two mismatched records can still produce the same total element count.

### 18.4. Meaningful Benchmarking

To compare nested loops against a Map index, measure all of:

1. **Map build** time, not just lookup time.
2. **Lookup and result-construction** time, using identical datasets and join policies.
3. Map memory and materialized output memory.
4. Skewed cases where orders repeat one customer ID vs. cases where most IDs are absent.
5. Warm-up/JIT and GC costs; use JMH for rigorous evaluation.

A single `System.nanoTime()` measurement on 100 elements cannot predict production speed. When datasets have only a handful of elements, Map construction overhead can exceed lookup savings.

## 19. Practice Exercises

### Exercise 1 — Convert Nested Loops to a Map Lookup

Given `List<Product> products` and `List<OrderLine> lines`, where `OrderLine` has `productId` and `quantity`, and `Product` has `id` and `unitPrice`. Write a pipeline computing line totals in O(M + N) average lookup time.

**Hint/Solution:**

~~~java
Map<String, Product> productById = products.stream()
        .collect(Collectors.toMap(
                Product::id,
                Function.identity()
        ));

List<BigDecimal> amounts = lines.stream()
        .map(line -> {
            Product product = productById.get(line.productId());

            if (product == null) {
                throw new IllegalArgumentException(
                        "Unknown product: " + line.productId());
            }

            return product.unitPrice().multiply(
                    BigDecimal.valueOf(line.quantity()));
        })
        .toList();
~~~

`Product` and `OrderLine` are exercise assumptions; declare matching types and fields. The example chooses to **fail on missing products** because a line total cannot be calculated accurately without a unit price.

### Exercise 2 — Pick the Right Join Type

Using the customers and orders from section 1:

- Revenue report covering only existing customers: which join?
- Audit list of orders missing a customer: which join?
- Export table of all orders with customer details when available: which join?

**Answer:** Inner join or validated aggregation; anti join; left join, respectively. Do not use inner join for the all-orders audit table because it drops `O-4`.

### Exercise 3 — Handling Duplicate Keys

The source contains two customers with ID `C-01`. Should you add `(old, next) -> next` to silence the exception?

**Answer:** Only when business rules explicitly permit choosing the later-processed record **and** source order carries that meaning. If IDs must be unique, let the error surface. If IDs have multiple versions, use version/timestamp criteria with a deterministic tie-breaker, or `groupingBy` to retain all versions.

### Exercise 4 — Complexity Calculation

Suppose `N = 100,000` orders and `M = 20,000` customers, each order having one customer key. Compare the complexity of repeated linear search vs. building a Map.

**Answer:** Nested loops have worst-case time O(N × M); a hash Map index has expected time O(M + N) for indexing and lookup, plus O(K) to build output. The Map uses O(M) extra memory. Never extrapolate exact millisecond timings without measuring.

### Exercise 5 — One Customer, Many Orders

You need to build `Map<String, List<Order>>` without losing duplicate-key orders. Should you use `toMap(Order::customerId, Function.identity())` or `groupingBy(Order::customerId)`?

**Answer:** `groupingBy(Order::customerId)`. Two-argument `toMap` throws duplicate key; a merge function keeping one order loses data.

### Exercise 6 — Composite Key Case

Two tenants both have a customer with ID `C-01`. Why is a Map keyed by `customerId` insufficient?

**Answer:** The key does not uniquely identify a customer system-wide. Use a composite key `(tenantId, customerId)`, such as `record CustomerKey`, and construct/query using the exact same key type on both sides.

### Exercise 7 — Parallel Safety Check

A developer builds a customer `HashMap`, then calls `orders.parallelStream().map(order -> index.get(order.customerId()))`. Is switching the Map to `ConcurrentHashMap` mandatory?

**Answer:** No, if the Map is fully constructed, safely published, and **strictly read-only** during processing, and its values remain stable by contract. `ConcurrentHashMap` is needed when concurrent updates are designed, not merely for concurrent reads.

### Exercise 8 — Large Datasets

Why can `orders.stream().map(...).toList()` still run out of memory even after optimizing the Map lookup?

**Answer:** `toList()` retains all result elements in memory. The Map optimizes **key lookup cost**, not output storage size. When outputs are huge, process in batches, stream results out, or aggregate only needed metrics.

## 20. Key Takeaways

- **Spot nested loops:** whenever each element of list A scans list B for a matching key, consider building an index.
- **Build the Map once, look up many times:** with unique keys and a suitable hash Map, expected time typically drops from O(N × M) to O(N + M) in exchange for O(M) extra memory.
- **Choose the right join semantics:** inner join drops unmatched records; left join retains left-side records; anti join isolates broken references.
- **Never mask duplicate keys:** two-argument `toMap` flags duplicate keys; use a merge function only with an explicit selection/merge policy, or `groupingBy` to keep multiple values.
- **Keep keys accurate and stable:** define unique keys, composite keys, normalization rules, `null` handling, and avoid mutable keys.
- **Output order follows the pipeline:** `HashMap` lookups do not disturb an ordered order Stream's encounter order; however, iterating `HashMap.values()` has no guaranteed order.
- **Reading a Map differs from writing to it:** a read-only index can be shared in parallel pipelines; never mutate a shared `HashMap` inside `parallelStream().forEach`.
- **Avoid materializing everything needlessly:** Map keys, join pairs, and `toList()` can still consume large memory; for datasets exceeding RAM, move joins to the DB or use out-of-core processing.
- **Test semantics before optimizing:** verify result counts, unmatched records, duplicate keys, and monetary accuracy before benchmarking.

**Main point:** The "**build an index once and look up by Map key**" pattern turns repeated linear scans into a one-time preparation phase and fast lookups. Yet an optimization truly succeeds only when it **preserves required record counts, never drops missing keys silently, and never confuses one-to-one with one-to-many relationships**.
