# Avoiding Cartesian Products and Aggregating on Multiplied Rows

When writing Cypher in Neo4j, a query can **return the right node and relationship types yet produce wrong aggregation numbers**. A frequent cause is an unexpected spike in intermediate row counts: two independent patterns create a **Cartesian product**, or two relationship branches attached to the same entity cause rows to be **multiplied** (*row multiplication / fan-out*). If you then call `count()`, `sum()`, or `collect()` without re-examining the data unit, reports may count and sum monetary amounts multiple times.

This lesson belongs to the **Query Optimization** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. In the context of using Neo4j to model property graphs and query nodes, relationships, and paths with Cypher, this lesson connects **semantic correctness** with **performance**: identifying row multiplication, choosing how to isolate aggregations, verifying with `EXPLAIN` / `PROFILE`, and applying these patterns in the Java Driver or Spring Data Neo4j.

## 1. First, Distinguish a "Row" from an "Entity"

Each `MATCH` in Cypher can produce **multiple result rows**, even when a node variable repeats across rows. A row is a combination of bound variable values currently under consideration, not a single distinct node or relationship.

For example, suppose a customer has two orders and three support tickets:

```text
                         (Order O1, amount=100)
                       /
(Customer C1) --PLACED
                       \
                         (Order O2, amount=100)

(Customer C1) --OPENED--> (Ticket T1)
              --OPENED--> (Ticket T2)
              --OPENED--> (Ticket T3)
```

Suppose the goal is to return:

| Customer | Order Count | Total Order Amount | Ticket Count |
| --- | ---: | ---: | ---: |
| C1 | 2 | 200 | 3 |

A query that joins both the order and support ticket branches at the same time can produce **2 × 3 = 6 rows**, turning `count(o)` into 6 and `sum(o.amount)` into 600.

**Rule:** before every aggregation, explicitly answer **"what does a single current row represent?"** Is it a customer, an order, a relationship, or a combination of an order and a support ticket?

## 2. How Do Cartesian Products Arise?

### 2.1. Two Patterns Without a Shared Variable

In Cypher, a comma between patterns in `MATCH` does not implicitly link them:

```cypher
MATCH (o:DemoOrder), (t:DemoTicket)
RETURN o.orderId AS orderId, t.ticketId AS ticketId;
```

If the database has `m` `:DemoOrder` nodes and `n` `:DemoTicket` nodes, the maximum row count from two independent patterns is:

\[
\text{Row count} = m \times n
\]

For example, 2 orders and 3 tickets yield 6 combinations:

| orderId | ticketId |
| --- | --- |
| O1 | T1 |
| O1 | T2 |
| O1 | T3 |
| O2 | T1 |
| O2 | T2 |
| O2 | T3 |

With 100,000 orders and 50,000 tickets, an unconstrained join creates a space of **5 billion combinations**. The query can consume huge CPU, RAM, and time, or hit resource limits before the user receives any result.

Not every Cartesian product is a bug. A screen generating **all candidate pairs** may intentionally need a Cartesian product. The problem lies in producing unintended combinations without bounding input sizes.

### 2.2. Matching Two Independent Entities to Create a Relationship

There are cases where two independent patterns are used to locate **two endpoints** of a relationship:

```cypher
MATCH (from:Person {personId: $fromId})
MATCH (to:Person {personId: $toId})
MERGE (from)-[:KNOWS]->(to);
```

When `personId` has a **uniqueness constraint**, each lookup finds at most one node: pairing `1 × 1` is harmless. If you omit the identifying predicate or the identifier is not unique, the query risks creating relationships across **every combination** of the two node sets.

Thus, you cannot conclude "seeing `CartesianProduct` means the query is definitely wrong." Examine the **row counts on both sides**, the purpose of the join, and entity uniqueness constraints.

## 3. Row Multiplication Even When Patterns Share a Node

This is a subtler bug: every part of the query passes through the **same customer**, yet each branch yields multiple matches.

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId, o.orderId, t.ticketId;
```

Because `c` has 2 orders and 3 support tickets, the rows for one customer contain every pairing of `o` and `t`. This is **row multiplication across relationship branches**, even if the execution plan does not always display a `CartesianProduct` operator.

Across multiple customers, the intermediate row count is approximately:

\[
\sum_{c \in \text{Customers}} O_c \times T_c
\]

Here `O_c` is the number of orders and `T_c` is the number of tickets associated with customer `c`, assuming both branches match. With `OPTIONAL MATCH`, an unmatched branch can still yield a row containing `null`; total rows depend on how optional patterns combine.

Distinguish these cases:

| Situation | Example | Risk |
| --- | --- | --- |
| **Independent Cartesian product** | `MATCH (a:Author), (p:Product)` | Pairs every author with every product |
| **Branch-based row multiplication** | `MATCH (c)-[:PLACED]->(o) MATCH (c)-[:OPENED]->(t)` | Each order repeats per ticket and vice versa |
| **Multi-path multiplication** | `MATCH p=(a)-[:KNOWS*1..3]->(b)` | Same destination can appear via multiple paths |
| **Multiplication via `UNWIND`** | `UNWIND a AS x UNWIND b AS y` | Two lists produce multi-row combinations |
| **Parallel relationship multiplication** | Two different relationships connecting to the same node | `count(node)` can exceed the distinct node count |

In all cases, damage to `sum()` occurs when **a business value is repeated across intermediate rows**.

## 4. Setting Up Sample Data to Observe the Bug

Run the following example **once in a separate practice database**. The labels `:DemoCustomer`, `:DemoOrder`, and `:DemoTicket` prevent confusion with real production entities:

```cypher
CREATE
  (c:DemoCustomer {customerId: 'C1'}),
  (o1:DemoOrder {orderId: 'O1', amount: 100}),
  (o2:DemoOrder {orderId: 'O2', amount: 100}),
  (t1:DemoTicket {ticketId: 'T1'}),
  (t2:DemoTicket {ticketId: 'T2'}),
  (t3:DemoTicket {ticketId: 'T3'}),
  (c)-[:PLACED]->(o1),
  (c)-[:PLACED]->(o2),
  (c)-[:OPENED]->(t1),
  (c)-[:OPENED]->(t2),
  (c)-[:OPENED]->(t3);
```

The two orders **intentionally share the same amount** `100`. This detail is crucial: it exposes the bug when someone tries to use `sum(DISTINCT o.amount)` to fix repeated aggregation.

First, observe the actual rows:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       o.orderId AS orderId,
       o.amount AS amount,
       t.ticketId AS ticketId
ORDER BY orderId, ticketId;
```

There are 6 rows; the value `amount=100` appears **6 times**. Multiplication happens before `RETURN`, so the same node `o1` participates in multiple rows.

### 4.1. Incorrect Aggregation Query

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       count(o) AS orderCount,
       sum(o.amount) AS totalAmount,
       count(t) AS ticketCount;
```

Result on the sample data:

| customer | orderCount | totalAmount | ticketCount |
| --- | ---: | ---: | ---: |
| C1 | 6 | 600 | 6 |

All three aggregations compute over the **6 paired rows**. In each row, the same order or ticket is still the original node, repeated alongside variables from the other branch.

### 4.2. Why `DISTINCT` Does Not Always Save `sum`

Someone writing the query might try:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN count(DISTINCT o) AS orderCount,
       sum(DISTINCT o.amount) AS totalAmount,
       count(DISTINCT t) AS ticketCount;
```

Result:

| orderCount | totalAmount | ticketCount |
| ---: | ---: | ---: |
| 2 | 100 | 3 |

`count(DISTINCT o)` and `count(DISTINCT t)` count **unique nodes**, giving 2 and 3. However, `sum(DISTINCT o.amount)` only sums **distinct monetary amounts**, so two orders both costing `100` collapse into **a single 100**. The correct sum must be `100 + 100 = 200`.

**The unit to deduplicate is the order, not the dollar amount.** The same applies to `avg(DISTINCT price)`, `collect(DISTINCT property)`, or any aggregation that uses a property value as the uniqueness key when the business logic counts entities.

## 5. Approach 1: Aggregate Each Branch Before Joining the Next

A pure-Cypher solution is to close the order branch with `WITH`, collapsing each customer back to **one row** before processing the support ticket branch.

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
WITH DISTINCT c, o
WITH c,
     count(o) AS orderCount,
     sum(o.amount) AS totalAmount
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       count(DISTINCT t) AS ticketCount;
```

Correct result on the sample data:

| customer | orderCount | totalAmount | ticketCount |
| --- | ---: | ---: | ---: |
| C1 | 2 | 200 | 3 |

Step-by-step breakdown:

1. `MATCH (c...)` selects the root customer.
2. `OPTIONAL MATCH` fetches orders; if none exist, variable `o` is `null`.
3. `WITH DISTINCT c, o` ensures each **customer–order** pair has only one row. This step is especially helpful if the same order can be reached via multiple relationships or paths while the business rule counts each order once.
4. `WITH c, count(o), sum(o.amount)` produces exactly **one aggregated row per customer**. Do not carry variable `o` into subsequent steps.
5. `OPTIONAL MATCH` on the ticket branch only repeats already-fixed **aggregated values**; `count(DISTINCT t)` counts unique tickets. `totalAmount` is never summed again.

**Warning:** if you include `o` in the same `WITH` that aggregates by customer—for instance `WITH c, o, sum(o.amount) AS total`—then `o` becomes a **grouping key**. The result will again have multiple rows per customer; rows are not collapsed to one row.

### Using Grouping Keys Properly

```cypher
MATCH (c:DemoCustomer)-[:PLACED]->(o:DemoOrder)
RETURN c.customerId AS customer,
       sum(o.amount) AS totalAmount;
```

Here `c.customerId` is the grouping key. If the data contains two distinct customer nodes sharing the same `customerId`, they get merged into one row: that is only valid if the identifier is business-unique. Grouping by the node variable `c` or a constrained unique ID makes the intent clearer.

## 6. Approach 2: Use Subqueries to Isolate Aggregations

When there are multiple data branches, chaining several `WITH` clauses can become hard to read and make it easy to accidentally keep a variable that inflates rows. `CALL { ... }` subqueries allow **each branch to compute independently** and return clean results to the outer customer row.

With Neo4j 5.23+, prefer the variable import syntax `CALL (c) { ... }`:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
CALL (c) {
  OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
  WITH DISTINCT o
  RETURN count(o) AS orderCount,
         sum(o.amount) AS totalAmount
}
CALL (c) {
  OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
  RETURN count(DISTINCT t) AS ticketCount
}
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       ticketCount;
```

Each subquery runs per outer customer `c`. The first subquery returns exactly one row with `orderCount` and `totalAmount`; the second returns exactly one row with `ticketCount`. Therefore, the order and ticket sets are never multiplied into 6 combinations.

In older Neo4j 5 releases, the legacy import syntax can be used, though it is deprecated in newer versions:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
  WITH DISTINCT o
  RETURN count(o) AS orderCount,
         sum(o.amount) AS totalAmount
}
CALL {
  WITH c
  OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
  RETURN count(DISTINCT t) AS ticketCount
}
RETURN c.customerId AS customer,
       orderCount,
       totalAmount,
       ticketCount;
```

Both styles illustrate the same goal; use the syntax matching your running Neo4j/Cypher version. A subquery that **returns zero rows** drops the outer row; thanks to `OPTIONAL MATCH` and ungrouped aggregation, this example still returns one row for a customer without orders or tickets.

**Benefit:** each aggregation has its own isolated scope and data unit. When adding a third branch like `(:Customer)-[:HAS]->(:Address)`, there is no need to mix orders, tickets, and addresses in a single intermediate row table.

**Limitation:** subqueries do not magically fix inefficient queries. If each subquery scans millions of relationships due to missing filters or indexes, cost remains high. The goal is both **correct cardinality** and avoiding unnecessary graph expansions.

## 7. Approach 3: Use `EXISTS` When Only Checking Existence

Sometimes a requirement does not need the list of support tickets, only **whether the customer has at least one ticket**. Joining all tickets into rows and applying `DISTINCT` is unnecessary work.

Use an existence expression:

```cypher
MATCH (c:DemoCustomer)
WHERE EXISTS {
  MATCH (c)-[:OPENED]->(:DemoTicket)
}
RETURN c.customerId AS customer;
```

This query returns each qualifying customer from the input `MATCH`, **without creating a row per ticket**. You can also use `EXISTS` in `RETURN` to emit a boolean flag instead of filtering:

```cypher
MATCH (c:DemoCustomer)
RETURN c.customerId AS customer,
       EXISTS {
         MATCH (c)-[:OPENED]->(:DemoTicket)
       } AS hasTickets;
```

When counting matching relationship patterns, modern Cypher also provides `COUNT { ... }` subqueries:

```cypher
MATCH (c:DemoCustomer)
RETURN c.customerId AS customer,
       COUNT {
         MATCH (c)-[:OPENED]->(:DemoTicket)
       } AS ticketRelationships;
```

Note: this count reflects **matching patterns/relationships**, so if two different relationships go from the same customer to a single ticket, the count can be 2. If the business logic wants the **number of distinct ticket nodes**, use `count(DISTINCT t)` in a dedicated branch. Distinguish whether the **counting unit is relationships, nodes, or paths**.

## 8. `OPTIONAL MATCH` and `null` Values Can Cause Misunderstandings

`OPTIONAL MATCH` preserves the driving row and assigns `null` to unmatched variables. This keeps customers without orders in reports, but also creates a difference between `count(*)` and `count(o)`.

```cypher
MATCH (c:DemoCustomer)
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
RETURN c.customerId AS customer,
       count(*) AS rowsAfterOptional,
       count(o) AS orders;
```

If a customer **has no orders**, `count(*)` will be **1** (the customer row remains), while `count(o)` equals **0** (`null` is ignored).

Similarly, misplacing a `WHERE` clause can turn an "optional" query into one that filters out the customer:

```cypher
// Keep customers, selecting only orders with status PAID.
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN c.customerId, count(o);
```

In this case, `WHERE` belongs to `OPTIONAL MATCH` itself. If moved to `WITH c, o WHERE o.status = 'PAID'`, customers with only invalid orders or no orders at all get **dropped from the input rows**. When writing reports, decide clearly whether zero-count entities must be kept or only matching ones returned.

Furthermore, `sum(o.amount)` ignores `null` values. If orders exist but lack `amount`, a seemingly valid total can hide incomplete data. You can report `count(o.amount)` alongside order counts and validate input data quality before computing financial totals.

## 9. Why a Final `DISTINCT` Is Usually Too Late

Consider the query:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN DISTINCT c.customerId AS customer;
```

Only one row `C1` comes back, yet **six intermediate rows may still have been generated** before `DISTINCT` deduplicated them. If millions of rows flow through intermediate steps, time and memory have already been spent.

Likewise, if summing amounts **before** deduplicating:

```cypher
MATCH (c:DemoCustomer {customerId: 'C1'})
MATCH (c)-[:PLACED]->(o:DemoOrder)
MATCH (c)-[:OPENED]->(t:DemoTicket)
WITH c, sum(o.amount) AS totalAmount
RETURN DISTINCT c.customerId AS customer, totalAmount;
```

`totalAmount` is still **600**. The final `DISTINCT` only removes identical output rows; it **cannot undo** an already-inflated `sum`.

Two core optimization principles apply:

1. **Reduce row counts early:** filter via keys/indexes, bound pattern scope, and aggregate each branch before expanding the next.
2. **Deduplicate the right entity:** `DISTINCT o` if business rules require each order once; `DISTINCT r` if each relationship once; never blindly use `DISTINCT o.amount`.

A well-placed `WITH DISTINCT` is generally more efficient than emitting all rows and applying `RETURN DISTINCT`, though deduplication itself carries a cost and must be measured against actual execution plans.

## 10. Reading Execution Plans to Find Root Causes of Row Multiplication

Cypher provides two primary tools:

- `EXPLAIN`: displays the **estimated plan** without running the query workload.
- `PROFILE`: **executes the query** and records metrics such as rows, DB hits, and memory/timing depending on the runtime.

Use `EXPLAIN` when checking an approach without executing it:

```cypher
EXPLAIN
MATCH (o:DemoOrder), (t:DemoTicket)
RETURN o.orderId, t.ticketId;
```

For independent patterns, a plan may show a `CartesianProduct` operator. Per Neo4j's documentation, this operator combines **each row from the left with every row from the right**. On real data, the planner may pick different plans and operators depending on query structure, version, and statistics; do not infer correctness solely from whether a specific operator name appears.

For the two-branch customer example:

```cypher
PROFILE
MATCH (c:DemoCustomer {customerId: 'C1'})
OPTIONAL MATCH (c)-[:PLACED]->(o:DemoOrder)
OPTIONAL MATCH (c)-[:OPENED]->(t:DemoTicket)
RETURN c.customerId, count(o), sum(o.amount), count(t);
```

When reading the plan, focus on:

| Plan Information | Question to Answer |
| --- | --- |
| `Rows` | After which operator do rows spike sharply? |
| `Estimated Rows` | How far off is the planner's estimate from reality? |
| `DB Hits` | Where is the query reading the most data? |
| `CartesianProduct` | Is it unintentionally joining two independent sets? |
| `Expand` / `OptionalExpand` / `Apply` | Which branch is fanning out from 1 row to many rows? |
| `EagerAggregation` / `OrderedAggregation` | Does aggregation happen before or after rows are multiplied? |
| `NodeByLabelScan`, `NodeIndexSeek` | Is locating the starting point reasonable? |
| `Memory (Bytes)` | Which operator consumes high memory in runtimes that report this metric? |

**How to read a typical signature:** 1 customer node → 2 order rows → 6 rows after ticket expansion. If `Aggregation` receives 6 rows and sums `o.amount`, the total gets multiplied right there.

To compare, `PROFILE` the isolated-subquery or early-aggregation version and inspect the input row counts to each aggregation. Do not judge from a sub-millisecond run on a tiny graph; use a representative workload to compare DB hits, rows, memory, and latency.

**Warning:** `PROFILE` executes for real. Applying it to `CREATE` / `MERGE` / `SET` / `DELETE` queries **can modify data**. For write queries, start with `EXPLAIN` and test in a safe environment.

## 11. Combining Indexes, Constraints, and Early Filtering

A 1 × 1 Cartesian product between two uniquely identified nodes is usually harmless; the danger is when one side returns thousands of nodes due to missing predicates. Indexes and constraints are therefore crucial.

Example in the customer model:

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
```

When querying:

```cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customer,
       count(DISTINCT o) AS orderCount;
```

The planner can use the uniqueness-backing index to locate a single customer. Meanwhile, passing `$customerId` as a parameter from the application gives the query a clear starting anchor.

However, an index **does not** prevent row multiplication between `:PLACED` and `:OPENED` branches by itself. It lowers node lookup cost, while aggregation correctness depends on **query structure**.

When both ends of a relationship are looked up by key:

```cypher
MATCH (a:Person {personId: $sourceId})
MATCH (b:Person {personId: $targetId})
MERGE (a)-[:FOLLOWS]->(b);
```

Ensure each key is unique per specification; otherwise `MERGE` may operate across unintended pairs of nodes. For write operations, the consequence of row multiplication is not just wrong reports, but also **corrupted graph mutations**.

## 12. Row Repetition When Analyzing Paths

Variable-length path patterns can produce **multiple paths to the same node**:

```cypher
MATCH (p:Person {personId: $startId})
MATCH path = (p)-[:KNOWS*1..3]->(friend:Person)
RETURN friend.personId AS friendId,
       length(path) AS hops;
```

If two distinct paths lead to the same `friend`, that node appears in multiple rows. The business question is:

- "How many **paths** of length up to 3?" → count `path`.
- "How many **unique people** are reachable?" → count `DISTINCT friend`.
- "How many **relationships** lie on the routes?" → needs a rule for counting relationships that may repeat across paths.
- "Total transaction value of reachable people?" → **deduplicate people or transactions** by monetary unit before summing.

Example:

```cypher
MATCH (p:Person {personId: $startId})
MATCH (p)-[:KNOWS*1..3]->(friend:Person)
RETURN count(DISTINCT friend) AS distinctReachablePeople;
```

In this case, `count(DISTINCT friend)` is right if you need the count of **distinct nodes**, whereas `count(*)` counts rows from matching paths. Still, on a deep traversal, generating vast numbers of paths only to deduplicate them can be expensive; consider traversal algorithms or alternative query models if reachability over large networks is required.

## 13. Beware of `UNWIND` and Write Queries

Row multiplication can happen without `MATCH`:

```cypher
WITH ['A', 'B'] AS warehouses,
     ['P1', 'P2', 'P3'] AS products
UNWIND warehouses AS warehouse
UNWIND products AS product
RETURN warehouse, product;
```

Two consecutive `UNWIND` clauses generate 6 combinations. If followed by `MERGE` or `CREATE`, the query can create **6 relationships or nodes** depending on the pattern. This might be intentional (every warehouse stocks every product) or a logic bug (intended to pair elements 1-to-1).

For a pre-defined list of pairs, pass each pair as a single data element:

```cypher
UNWIND $pairs AS pair
MATCH (w:Warehouse {code: pair.warehouseCode})
MATCH (p:Product {sku: pair.productSku})
MERGE (w)-[:STOCKS]->(p);
```

If `$pairs` contains three pairs, each row corresponds to one pair. You still need uniqueness constraints on `Warehouse.code` and `Product.sku`, duplicate-payload checks, and proper `MERGE` rules to avoid creating erroneous relationships.

Do not use `collect()` to "fix" every row multiplication problem in write workloads. Collecting millions of nodes into a single list can bloat transaction memory. Structure data flows by business unit, batch writes, and collect lists only when genuinely needed.

## 14. Applying in Java Driver and Spring Data Neo4j

The application layer typically reads aggregation results and maps them to DTOs. If the query already double-counted monetary amounts, Java receives **a completely type-valid number** that is nonetheless business-wrong. Therefore, fix it in Cypher—never "divide back" total revenue by ticket count in Java: changing branch counts and relationship states will break such hacks.

Java Driver example using isolated-aggregation subqueries:

```java
String query = """
    MATCH (c:Customer {customerId: $customerId})
    CALL (c) {
      OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
      WITH DISTINCT o
      RETURN count(o) AS orderCount,
             sum(o.amount) AS totalAmount
    }
    CALL (c) {
      OPTIONAL MATCH (c)-[:OPENED]->(t:Ticket)
      RETURN count(DISTINCT t) AS ticketCount
    }
    RETURN c.customerId AS customerId,
           orderCount, totalAmount, ticketCount
    """;

try (var session = driver.session()) {
    var summary = session.executeRead(tx -> {
        var record = tx.run(
            query,
            java.util.Map.of("customerId", "C1")
        ).single();

        return java.util.Map.of(
            "customerId", record.get("customerId").asString(),
            "orderCount", record.get("orderCount").asLong(),
            "totalAmount", record.get("totalAmount").asLong(),
            "ticketCount", record.get("ticketCount").asLong()
        );
    });
    System.out.println(summary);
}
```

This snippet assumes every `Order.amount` is an integer (smallest currency unit) and non-missing; in production data, check currency rules, `INTEGER` vs. `FLOAT` types, and the possibility of a missing customer (where `single()` fails). The `CALL (c)` syntax requires a supporting Neo4j version.

In **Spring Data Neo4j**, you can place a custom Cypher query in a repository/service and map `orderCount`, `totalAmount`, and `ticketCount` into a DTO. Importantly, **do not load two full relationship collections and sum them in Java over multiplied results**, especially with large collections; that increases data transfer, application memory, and risk of miscounting.

For reporting APIs across many customers, avoid firing a separate query per customer if it introduces an **N+1 queries** problem. One aggregated Cypher query over a pre-filtered customer set, or a sensible batching strategy, is usually easier to manage. Still, watch the total cost of per-customer subqueries when customer counts are high.

## 15. Checklist for Auditing a Query with Anomalous Numbers

When a Cypher report returns "total revenue three times higher than expected," audit systematically:

1. **Define the business unit:** is revenue summed per **unique order** or per order line item? Is a customer one unique node or one row per relationship?
2. **Check independent `MATCH` clauses:** do two patterns share a variable or explicit join condition? If not, how large are the input sets?
3. **Count rows at each stage:** run temporary read-only checks returning only `count(*)`/`count(DISTINCT ...)` to see which step inflates row counts.
4. **Identify fan-out:** how many orders, tickets, and paths does one customer have? Are those branches combined into a single row table?
5. **Inspect aggregations:** does `sum(amount)` see each order once or multiple times? Could `sum(DISTINCT amount)` fail when two orders have the same amount?
6. **Isolate aggregations early:** use `WITH` with the right grouping key or per-branch subqueries; use `EXISTS` when only existence matters.
7. **Read `EXPLAIN`/`PROFILE`:** compare `Rows`, `DB Hits`, `Expand` steps, and aggregation operators before and after fixing.
8. **Test edge cases:** customers with no orders, multiple orders of identical value, parallel relationships to the same node, `null` values, multiple paths to one destination.
9. **Verify in the application:** parameters passed via Java Driver, DTO mappings, and result limits must preserve the intended aggregation granularity.

### Quick Decision Table

| Need | Recommended Implementation | Avoid |
| --- | --- | --- |
| Link two uniquely identified nodes | Two index/constraint lookups then `MERGE` relationship | Matching two large sets without predicates |
| Only check whether a link exists | `EXISTS { MATCH ... }` | Joining all relationships then `DISTINCT` |
| Count distinct nodes across multiple paths | `count(DISTINCT node)` | `count(*)` when the target is node count |
| Sum order amounts and count tickets | Isolate branches with `WITH` or `CALL` subqueries | `sum(order.amount)` over order × ticket rows |
| Two orders with the same amount | Deduplicate by **order** before `sum` | `sum(DISTINCT amount)` |
| Write from a list of source–target pairs | `UNWIND $pairs` with unique keys | Two `UNWIND`s generating unintended combinations |
| Very deep path queries | Bound targets, depth, predicates, and consider algorithms | Generating all paths then filtering/deduplicating at the end |

## 16. Self-Check Exercises

**Exercise 1 — Explaining the Error.** A customer has 4 orders, each costing 50, and 5 tickets. What will a query that joins both branches and computes `sum(o.amount)` return without deduplication? What is the right value? Why?

**Exercise 2 — The `DISTINCT` Trap.** Two distinct orders have amounts `200` and `200`. Why is `sum(DISTINCT o.amount)` wrong? Write a query that deduplicates by order before aggregating.

**Exercise 3 — Distinguishing Cartesian Products and Fan-Out.** Given two queries:

```cypher
MATCH (a:Author), (b:Book)
RETURN a, b;

MATCH (a:Author)-[:WROTE]->(b:Book)
MATCH (a)-[:LIVES_IN]->(city:City)
RETURN a, b, city;
```

Which query has independent patterns? Which shares one author yet can multiply rows across two branches? If an author wrote 3 books and lives in 2 cities in the data, how many combinations will appear for that author?

**Exercise 4 — Reading a Plan.** A `PROFILE` plan shows 100 node rows, then 1,000 rows after a relationship expansion, then 20,000 rows after a second branch. Identify where row count spikes, which aggregations are likely to go wrong, and where the aggregation step should be placed.

**Exercise 5 — Existence vs. Count.** Write a query returning customers who have at least one ticket using `EXISTS`. Then write a variant returning the number of **unique** tickets per customer. Explain the difference if multiple relationships connect to the same ticket.

**Exercise 6 — Real-World API.** A Spring Data Neo4j service returns `customerId`, `orderCount`, `revenue`, and `followerCount`. Design how to isolate aggregations so that a customer with 20 orders and 50 followers does not have their revenue multiplied 50 times.

## 17. Reference Documentation

To verify Cypher syntax and execution plan behavior on your exact running Neo4j version:

- [Cypher Manual — Query tuning / Operators in detail](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/operators-detail/): describes `CartesianProduct`, expansion operators, and aggregations.
- [Cypher Manual — CALL subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/): `CALL (variable)` variable importing, behavior, and impact on row counts.
- [Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `count()`, `sum()`, `DISTINCT`, and grouping keys.
- [Cypher Manual — EXPLAIN and PROFILE](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/): inspecting plans and actual row counts.
- [Cypher Manual — Subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/): subquery forms and usage conditions.

**Takeaway:** a Cypher query can multiply rows **without displaying `CartesianProduct` in the plan**. Before summing or counting, identify the **data unit being aggregated**, reduce cardinality right in the generating branch, and inspect the execution plan. `count(DISTINCT entity)` is often useful for counting entities, whereas `sum(DISTINCT property)` is no substitute for **aggregating exactly once per business entity**.
