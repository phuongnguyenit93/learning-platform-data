# DTOs, Projections, and Controlling Loaded Graph Breadth in Spring Data Neo4j

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **entities**, **interface-based projections**, **DTO/record projections**, and manually mapped Cypher results in Spring Data Neo4j.
- Explain why reading a single root node can pull in many relationships and related nodes, increasing query breadth and cost.
- Design APIs that return only required fields without accidentally loading an entire **property graph**.
- Use repository projections, **dynamic projections**, `@Query`, and `Neo4jClient` according to each use case.
- Control fan-out, traversal depth, pagination, N+1 queries, and result limits when relationships have high cardinality.
- Inspect actual queries using `EXPLAIN`/`PROFILE`, query logs, and integration tests instead of guessing performance from Java return types.

This lesson belongs to the **Spring Data Neo4j** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. Neo4j models nodes, relationships, and properties as a **property graph**, while Cypher queries relationships and paths. Spring Data Neo4j (SDN) maps graph data to Java objects and provides repositories. Mapping is convenient for domain logic, but an entity with many relationships can produce a **massive object graph** even when an endpoint only needs a few fields.

> **Scope:** Examples follow common patterns in Spring Data Neo4j 6/7 and Spring Data Commons; exact query generation and projection capabilities depend on Spring Boot, SDN version, entity declarations, and query type. Never treat choosing an interface or DTO as proof that the database read less data: inspect the **actual executed Cypher**. Entity/repository snippets show only relevant members; getters, constructors, and application configuration may be omitted where noted.

## 1. The Problem: Small API, Large Graph

Consider an e-commerce application with three node types:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, displayName"] -->|PLACED 1:N| O["Order<br/>orderId, status, totalCents"]
    O -->|CONTAINS N:M| P["Product<br/>sku, name"]
~~~

Suppose a `Customer` has **10,000** orders, and each order averages **8** products. A "customer profile" screen only needs:

~~~json
{
  "customerId": "C-101",
  "displayName": "Lan"
}
~~~

If the data access layer builds both `Customer.orders` and `Order.products`, the system can process huge numbers of nodes/relationships and construct a giant Java object graph just to return two strings. This is **over-fetching** or **loading a broader graph than needed**.

Three dimensions to control:

| Dimension | Meaning | Example |
| --- | --- | --- |
| **Breadth** | Number of nodes/relationships fetched in one step | One customer having 10,000 `PLACED` edges |
| **Depth** | Number of relationship hops traversed | `Customer → Order → Product` is two hops |
| **Payload/shape** | Number of properties and bytes returned | Returning full `Product.description` instead of `sku` |

Breadth and depth compound each other. If each node averages `d` neighbors, a `k`-hop traversal can generate massive intermediate row counts; cycles, shared nodes, and filter predicates make the actual count differ from a naive `d^k` estimate.

**Key takeaway:** Controlling graph loading involves **two distinct tasks**:

1. Limiting how many nodes, edges, and properties **Cypher reads and returns**.
2. Limiting how much data **Java mapping/serialization** transfers into objects and HTTP responses.

Optimizing only the second step while letting Cypher traverse millions of relationships may yield little improvement.

## 2. Entity Mapping: Convenient, but Understand Its Scope

Simple Java model:

~~~java
import java.util.HashSet;
import java.util.Set;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;   // Business-assigned ID
    private String displayName;

    @Relationship(
        type = "PLACED",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Order> orders = new HashSet<>();

    // Constructors and getters/setters omitted.
}

@Node("Order")
public class Order {
    @Id
    private String orderId;
    private String status;
    private long totalCents;

    @Relationship(
        type = "CONTAINS",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Product> products = new HashSet<>();

    // Constructors and getters/setters omitted.
}

@Node("Product")
public class Product {
    @Id
    private String sku;
    private String name;

    // Constructors and getters/setters omitted.
}
~~~

The three entities use `@Node` for labels, `@Id` for keys, and `@Relationship` for directed edges. The code assumes matching nodes/relationships exist in Neo4j. In real applications, include proper constructors/property accessors, constraints on business IDs, and clear aggregate lifecycles.

Basic repository:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {
}
~~~

`findById("C-101")` returns `Customer`—an **entity graph** shaped by the query/mapping strategy SDN generates for this model. Do not assume this means "fetch only customer properties," nor assume every version infinitely traverses all paths. The **actual query shape** depends on relationship mappings, projections, query methods, and SDN version.

Unlike common JPA expectations, do not assume "unneeded relationships will lazy-load automatically after the session closes." Modern SDN constructs queries to map graphs according to its own rules; explicitly define the data scope needed for each use case.

### A Common Anti-Pattern

~~~java
public Customer showCustomer(String id) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Then returning the entity directly from a controller. The risks:

- The query may fetch relationships the screen never uses.
- The JSON serializer traverses relationship getters, inflating payloads or hitting circular references.
- Domain entities inadvertently expose internal attributes.
- The API becomes tightly coupled to entity modeling, making response contract changes difficult.

Prefer **response DTOs** designed for API needs rather than exposing full entity graphs as the default HTTP contract.

## 3. Interface-Based Projections: Selecting Properties via Getters

Spring Data supports **interface projections**: the application declares an interface containing only the properties to read.

~~~java
public interface CustomerCard {
    String getCustomerId();
    String getDisplayName();
}
~~~

The repository can declare a dedicated projection method:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    Optional<CustomerCard> findProjectedByCustomerId(
            String customerId);
}
~~~

Usage:

~~~java
CustomerCard card = customerRepository
        .findProjectedByCustomerId("C-101")
        .orElseThrow();

String label = card.getDisplayName();
~~~

Advantages:

- The return type clearly documents that the API needs only `customerId` and `displayName`.
- Eliminates manual entity → DTO converters for simple read cases.
- Multiple views can project over the same node without proliferating display-only entities.

**Important limitation:** A projection is a **mapping and result-shape convention at the SDN layer**. Derived queries can leverage projections to narrow fetched data, but not every path or custom Cypher query is guaranteed to optimize automatically. Always inspect the executed Cypher and plan.

### 3.1. Closed vs. Open Projections

`CustomerCard` is a **closed projection**: every accessor matches an entity property and can be statically analyzed by the framework.

An **open projection** can use expressions:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerDisplay {
    @Value("#{target.customerId + ' - ' + target.displayName}")
    String getTitle();
}
~~~

Open projections evaluate expressions against `target`. The framework cannot easily infer all dependencies as with closed projections and **may need to load a fuller entity**. Avoid open projections when your primary goal is reducing properties/relationships read; prefer computing in Java after fetching minimal fields or returning the needed fields directly in Cypher.

### 3.2. Nested Projections: Watch Out for Multi-Element Relationships

You can express nested data:

~~~java
public interface OrderCard {
    String getOrderId();
    String getStatus();
}

public interface CustomerWithOrders {
    String getCustomerId();
    java.util.Set<OrderCard> getOrders();
}
~~~

`CustomerWithOrders` indicates that the client wants related orders too. **It contains no `LIMIT 5` or pagination rule on the `orders` collection**. For a customer with 10,000 orders, a nested projection can still pull a massive relationship set.

Moreover, nested projections change the Cypher/mapping structure generated by SDN. Never assume `getOrders()` lazy-loads or fetches only a handful of orders on demand during serialization.

When you need "the 20 most recent orders," a **clearly scoped Cypher query** is far better than putting an unbounded `Set<OrderCard>` in the response.

## 4. DTO/Record Projections: Read-Only Data, Clear Contracts

A **Data Transfer Object (DTO)** is a Java type designed to carry data across layers. In modern Java, `record` is a concise choice for immutable read results.

~~~java
public record CustomerSummary(
        String customerId,
        String displayName
) {}

public record OrderRow(
        String orderId,
        String status,
        long totalCents
) {}
~~~

Unlike the `Customer` entity, `CustomerSummary` carries no `@Node`, `@Relationship`, or object-graph persistence mechanics. It does not represent an aggregate for `save(...)`; it is a **data snapshot serving one use case**.

### 4.1. Class-Based DTO Projections in Repositories

Spring Data Commons supports constructor-based **class projections**, including Java records. For example, declaring a query method aligned with the domain:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    java.util.Optional<CustomerSummary>
            findSummaryByCustomerId(String customerId);
}
~~~

For query methods derived from entity properties, the framework uses constructor/property metadata to map matching fields when supported by your SDN version. If property/constructor names do not match, mapping can fail.

**Do not conflate** repository DTO projections with **custom Cypher returning arbitrary tuples**. For aggregated values, aliased scalars, relationship properties, or multiple node types, explicit mapping via `Neo4jClient` (next section) is usually more predictable.

### 4.2. Dynamic Projections: One Method, Multiple Return Types

When several callers need different result shapes for the same lookup criteria, use a **dynamic projection**:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    <T> java.util.Optional<T> findByCustomerId(
            String customerId, Class<T> projectionType);
}
~~~

Example:

~~~java
CustomerCard card = repository
        .findByCustomerId("C-101", CustomerCard.class)
        .orElseThrow();

CustomerSummary summary = repository
        .findByCustomerId("C-101", CustomerSummary.class)
        .orElseThrow();
~~~

Dynamic projections enable query method reuse, but **do not turn a repository into an arbitrary catch-all for every graph shape**. Every projection still requires valid mapping, testing on your actual SDN version, and protection against unbounded relationships.

### 4.3. DTOs Do Not Automatically Mean "Zero Graph Cost"

Even when the response is `CustomerSummary`, three scenarios exist:

1. **Good:** The query locates only the root node and fetches two properties; both database and mapping process minimal data.
2. **Suboptimal:** The query still loads a wide graph, and Java discards everything except two properties to construct the DTO; the HTTP payload is small, yet the database still pays the full cost.
3. **Semantically broken:** The query returns only scalar properties, while code attempts to map into an entity with mandatory relationships, yielding missing data or broken mappings.

Therefore, the optimization target is **query shape + mapping shape**, not merely picking a Java type.

## 5. Precise Control with `Neo4jClient` and Cypher

For screens/APIs needing flat data or a tiny slice of the graph, `Neo4jClient` lets you write transparent Cypher and map each row to a DTO.

### 5.1. Reading an Order List Without Loading the Entire Customer Graph

Example service returning at most 20 orders in `PAID` status:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderReadService {
    private final Neo4jClient neo4jClient;

    public OrderReadService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(readOnly = true)
    public List<OrderRow> findPaidOrders(
            String customerId, int requestedLimit) {
        int limit = Math.max(1, Math.min(requestedLimit, 50));

        var result = neo4jClient.query("""
                MATCH (c:Customer {customerId: $customerId})
                      -[:PLACED]->(o:Order)
                WHERE o.status = 'PAID'
                RETURN o.orderId AS orderId,
                       o.status AS status,
                       o.totalCents AS totalCents
                ORDER BY o.orderId
                LIMIT $pageSize
                """)
                .bind(customerId).to("customerId")
                .bind(limit).to("pageSize")
                .fetchAs(OrderRow.class)
                .mappedBy((typeSystem, record) -> new OrderRow(
                        record.get("orderId").asString(),
                        record.get("status").asString(),
                        record.get("totalCents").asLong()))
                .all();

        return new ArrayList<>(result);
    }
}
~~~

Here `OrderRow` is the Java record defined earlier. `Neo4jClient` uses the Spring-configured Neo4j driver and transaction infrastructure; `mappedBy` converts each Cypher result record into a DTO. This method **does not instantiate `Customer`/`Order` entities** and never traverses `Order.products`. Returned data contains strictly the columns listed in `RETURN`.

Note one detail: `ORDER BY o.orderId` sorts only by ID; **it does not represent order creation time by default**. If the requirement is "most recent," sort by `createdAt` plus a deterministic tie-breaker (see pagination below).

### 5.2. Why Not Always Use `@Query` on a Repository?

`@Query` works well for declaring fixed Cypher next to a repository method:

~~~java
import org.springframework.data.neo4j.repository.query.Query;

public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    @Query("""
        MATCH (c:Customer {customerId: $customerId})
        RETURN c
        """)
    java.util.Optional<Customer>
            findCustomerNodeOnly(String customerId);
}
~~~

However, **`RETURN c` returns only the root node in Cypher**, while the method signature promises a **`Customer` entity** with relationship mappings. The result can be an entity **missing its relationships**, differing from the full entity graph generated by standard repository methods. Never take a truncated entity and pass it to `save(...)` without understanding relationship update semantics: you risk corrupting related data or breaking the aggregate.

For custom queries returning scalars/aggregations, prefer **DTOs and explicit mapping**. For custom queries returning entities + relationships, follow the return shape SDN expects to reconstruct the object graph accurately; a read-only projection is never meant to re-save an entire aggregate.

### 5.3. Inspecting Actual Queries Instead of Guessing

Whether choosing repository projections or `Neo4jClient`:

1. Enable **Cypher query/statement logging** appropriate to your environment and security posture.
2. Inspect the exact query SDN executes for each method.
3. Run `EXPLAIN` or `PROFILE` safely with representative parameter values.
4. Compare `Rows`, `DB Hits`, query duration, returned record count, and JSON payload size.

Do not judge solely by whether Java returns `CustomerCard` vs. `Customer`, because the expensive work may lie inside Neo4j `Expand` or `Sort` operators.

## 6. Relationship Breadth: Fan-Out and Intermediate Row Explosion

### 6.1. A Customer with Very Many Orders

An unbounded query:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN c, o;
~~~

If a customer has 10,000 orders, Cypher can return 10,000 rows. When the caller only needs "total order count," never pull 10,000 Java objects just to count them:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount;
~~~

`count(DISTINCT o)` avoids double-counting an `Order` node if duplicate `PLACED` edges exist. It does not repair duplicate data; enforce proper constraints/modeling if business rules mandate one customer per order.

**Do not assume counts are always cheap:** a filtered count query may still traverse huge numbers of relationships. The immediate gain is shrinking **the returned result payload**, while the execution plan itself must be measured separately.

### 6.2. Traversing Two Relationship Hops Can Multiply Rows

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
      -[:CONTAINS]->(p:Product)
RETURN o.orderId, p.sku;
~~~

If a customer has 10,000 orders and each order has 8 products, the intermediate row set can reach around **80,000** rows before filtering or aggregation—even for **one** starting customer. `DISTINCT` or DTOs can deduplicate returned rows but do not automatically eliminate the traversal work done beforehand.

If an endpoint only needs order IDs and totals, **omit `CONTAINS` from the query**. Eliminating an unnecessary relationship hop often matters far more than switching the Java return type from entity to DTO.

### 6.3. Labels/Types and Selective Keys

~~~cypher
// Too broad if only one customer is needed:
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.orderId;

// Much smaller starting set:
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

Place a uniqueness constraint on `Customer.customerId` to protect the business key and enable index seeks:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

The query can start with `NodeUniqueIndexSeek` followed by `Expand(All)`. Still, **an index seek to one node** can fan out into thousands of relationships; optimize both the **starting point and the fan-out**.

## 7. Pagination: Root-Level LIMIT Is Not Collection Pagination

### 7.1. Pitfall When Paginating Repository Entities

Consider a repository returning `Page<Customer>`:

~~~java
Page<Customer> page = customerRepository.findAll(
        org.springframework.data.domain.PageRequest.of(0, 20));
~~~

The limit of 20 applies to the **root `Customer` set**, not to capping each customer at 20 `Order` items. If one customer has 100,000 orders, root pagination does **not solve** relationship breadth.

Similarly, `CustomerWithOrders.getOrders()` has no built-in per-parent pagination. When a client needs a slice of a child collection, design a **dedicated operation with its own query and response**.

### 7.2. Querying the First Page of Orders

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

Here `createdAt` is assumed to be a **temporal** property suitable for sorting, not an arbitrary string format. `orderId` serves as a **tie-breaker** so ordering remains deterministic when multiple orders share the same timestamp. Cap `pageSize` in the application rather than forwarding unbounded values from clients.

**Note:** `LIMIT 20` caps the number of rows **emitted** after preceding operators. It does not guarantee Neo4j expands only 20 relationships or sorts only 20 orders, especially when `ORDER BY` is present. Check `PROFILE` to see row counts entering `Sort`.

### 7.3. Keyset Pagination for Subsequent Pages

For page two, pass a cursor from the **last record of the previous page**:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.createdAt < datetime($cursorCreatedAt)
   OR (
        o.createdAt = datetime($cursorCreatedAt)
        AND o.orderId < $cursorOrderId
   )
RETURN o.orderId AS orderId,
       o.createdAt AS createdAt,
       o.status AS status
ORDER BY o.createdAt DESC, o.orderId DESC
LIMIT $pageSize;
~~~

This example expects `$cursorCreatedAt` in timezone-aware ISO 8601 format and `$cursorOrderId` from the final row of the prior page. It assumes `o.createdAt` is stored as a compatible temporal type and the cursor has been validated.

**Benefits:** Avoids deep offset penalties at the API layer and preserves stable page ordering when paired with a unique tie-breaker. **Limitation:** For queries that start at a customer and expand all edges, keyset pagination **does not automatically reduce** the number of edges traversed. Inspect the plan and consider alternative access paths/indexes when relationship counts are massive. Also, if data changes between requests, separate pages do not share a single transactional snapshot by default.

## 8. Avoiding N+1 Queries and Choosing Multi-Customer Strategies

Anti-pattern:

~~~java
for (CustomerCard customer : customers) {
    // Hits the database once per customer to fetch order count.
    long count = orderService.countOrders(
            customer.getCustomerId());
    // Assemble DTO ...
}
~~~

If a screen displays 100 customers, the code executes **1 query for customers + 100 queries for order counts**. This N+1 pattern multiplies network round trips, transactions, and connection pool pressure.

One solution is querying by a batch of IDs:

~~~cypher
UNWIND $customerIds AS id
MATCH (c:Customer {customerId: id})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
RETURN c.customerId AS customerId,
       count(DISTINCT o) AS orderCount
ORDER BY customerId;
~~~

The application passes a bounded `List<String> customerIds` and maps results to `CustomerOrderCount`:

~~~java
public record CustomerOrderCount(
        String customerId,
        long orderCount
) {}
~~~

Result: one query round trip instead of N. Still, a single batch query can become heavy if each customer has millions of orders. Balance batch size, row count, and relationship scope.

### Fetching Top-N for **Each** Customer

Do not put `LIMIT 3` after `UNWIND` expecting 3 orders **per customer**: an outer `LIMIT` caps **total output rows**.

One approach is a **per-root-node subquery**. On Neo4j versions supporting variable-scope `CALL (c)` syntax (Neo4j 5.23+ and modern releases):

~~~cypher
UNWIND $customerIds AS id
MATCH (c:Customer {customerId: id})
CALL (c) {
    MATCH (c)-[:PLACED]->(o:Order)
    WITH o
    ORDER BY o.createdAt DESC, o.orderId DESC
    LIMIT 3
    RETURN collect(o.orderId) AS recentOrderIds
}
RETURN c.customerId AS customerId,
       recentOrderIds;
~~~

Each subquery invocation runs in its own `c` scope, so `LIMIT 3` applies to the **corresponding customer's** orders. Check semantics for customers with zero orders and choose `OPTIONAL MATCH` or response shaping when customers without orders must still appear. In older Neo4j versions, passing variables into subqueries uses `CALL { WITH c ... }`; verify syntax against your Cypher version.

This is still not necessarily a cheap query: Neo4j may have to traverse and sort many orders for **each** customer. Never skip `PROFILE`.

## 9. Summary DTOs, Nested Responses, and Aggregate Endpoints

An API may require:

~~~json
{
  "customerId": "C-101",
  "displayName": "Lan",
  "orderCount": 128,
  "recentOrders": [
    {"orderId": "O-500", "status": "PAID"},
    {"orderId": "O-499", "status": "CREATED"}
  ]
}
~~~

There does not have to be a `Customer` entity matching that exact JSON tree. A clean strategy:

1. **Read `CustomerSummary`** via projection (just two root properties).
2. **Read `orderCount`** via an aggregation query.
3. **Read at most N `OrderRow` items** via a query with `ORDER BY` and `LIMIT`.
4. **Assemble the response DTO** in the service/controller instead of returning entities directly.

Running more than one small query is **not automatically bad**: for a single-customer endpoint, three focused queries can be cheaper and clearer than one giant query hydrating the whole graph. Conversely, for a list of hundreds of customers, **batch** queries to prevent N+1. Decide with measurements.

### Choosing Response Shapes by Use Case

| Use case | Data shape to consider | Characteristics |
| --- | --- | --- |
| Customer list page | `CustomerCard` interface projection | Few fields from root node |
| Simple single-customer detail | `CustomerSummary` record/DTO | Explicit response contract |
| 20 recent orders | `OrderRow` from Cypher + `Neo4jClient` | Controls ordering/limit/returned fields |
| Order count report per customer | Aggregate DTO from `count(...)` | Avoids building `Order` entities just to count |
| Editing an aggregate with links | Full entity graph matching write scope | Focuses on atomicity and `save` semantics |
| Complex path queries | Custom-shaped DTO / custom mapping | Returns exact nodes, edges, and depth needed |

## 10. Avoiding Confusion Around the Word "Projection"

In the Neo4j ecosystem, **projection** carries several distinct meanings:

| Concept | Meaning | Creates a separate graph? |
| --- | --- | --- |
| **Spring Data interface projection** | Selects Java accessors for fields to read | No |
| **Spring Data DTO projection** | Constructs a result class/record from needed fields | No |
| **Cypher map projection** | Builds a map directly in Cypher, e.g. `c { .customerId, .displayName }` | No |
| **GDS graph projection** | Projects nodes/relationships into an **in-memory graph catalog** for algorithms | **Yes**, for Graph Data Science |

Cypher map projection example:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN c {
    .customerId,
    .displayName
} AS customerCard;
~~~

This is a map constructed and returned by Cypher; it is **not** an automatic SDN Java interface projection. With `Neo4jClient`, you can explicitly decode the map into a DTO. Do not confuse `RETURN c { ... }` with `RETURN c` or `gds.graph.project(...)`.

## 11. Transactions, Consistency, and Risks of Saving Incomplete Entities

### 11.1. Projections Are Primarily for Reads

Interface/DTO projections are built for **read-only** data retrieval. When updates are needed:

- Write directly using `MATCH ... SET ...` Cypher in an appropriate transaction; or
- Load/map an entity graph **complete enough for the write operation** and call repository `save` with a clear grasp of aggregate semantics.

Never take a DTO holding only `customerId` and `displayName`, pretend it is a full `Customer`, and persist it back as an entity—relationships and properties absent from the view may be mishandled.

### 11.2. Do Multiple Read Queries Share the Same Snapshot?

The three-query response assembly in Section 9 can observe data at different points in time if concurrent transactions commit writes in between. By default, Neo4j uses **read committed** isolation and does not promise a fixed snapshot across multiple reads within a single transaction.

If business invariants require strict consistency across values, decide:

- Should the queries be combined inside **one Spring transaction** (or one Cypher statement)?
- Do concurrent writers require versioning, conditional predicates, or locking?
- Is brief skew between `orderCount` and `recentOrders` acceptable on the UI?

`@Transactional(readOnly = true)` declares a read boundary and binds to the transaction manager; **it does not automatically upgrade isolation to serializable**.

### 11.3. Be Careful Across Multiple Databases and External Sources

An API DTO may combine Neo4j data with REST services, Kafka, or another database. Neo4j transactions **do not automatically span** those external systems. When cross-system consistency is required, design versioning, idempotency, outbox/events, or orchestration—do not treat a transaction annotation as a distributed transaction.

## 12. Measuring Real Performance: Cypher, Mapping, Payload, and Memory

To determine whether a projection or DTO actually reduces load, measure under the **same workload and parameters**:

| Metric | Meaning | How to interpret |
| --- | --- | --- |
| `Rows` | Row count flowing through each plan operator | Did 1 customer expand into tens of thousands of orders? |
| `DB Hits` | Storage access operations in Neo4j | Is it scanning too many nodes/relationships? |
| `Estimated Rows` | Planner's cardinality estimate | Large misestimates can lead to poor plans |
| Neo4j query duration | Cypher execution cost | Small DTOs will not help if scans/expands remain huge |
| Returned rows and bytes | Bolt transport and mapping cost | Is `RETURN` emitting too many properties or nodes? |
| App CPU/heap/GC | Mapping and serialization overhead | Large object graphs cause memory pressure |
| Endpoint p50/p95/p99 latency | End-user experience | Validate performance under concurrent load |

For the order list query:

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status, o.totalCents
ORDER BY o.orderId
LIMIT 20;
~~~

When safe to run:

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId, o.status, o.totalCents
ORDER BY o.orderId
LIMIT 20;
~~~

Look for operators like `NodeUniqueIndexSeek`, `NodeByLabelScan`, `Expand(All)`, and `Sort`, and inspect intermediate row counts. `EXPLAIN` does not execute the query; `PROFILE` **executes it for real**, so be cautious with write queries.

**Empirical note:** Warm/cold caches, per-customer relationship counts, data distribution, and concurrency all affect measurements. Never benchmark only a customer with 2 orders and extrapolate to a customer with 100,000 orders.

### Four Measurements Worth Comparing

1. Repository returning full `Customer` entity.
2. Repository returning `CustomerCard` projection.
3. DTO record via `Neo4jClient` returning only two properties.
4. Aggregated/limited `LIMIT` DTO when the use case needs relationships.

Each option must return the **exact business data required for comparison**. If option 1 loads every order while option 3 returns only a name, the numbers reveal over-fetching, but they do not constitute an apples-to-apples comparison for **the same data requirement**.

## 13. Testing in Spring Data Neo4j

Integration tests must run against a real Neo4j database or a Testcontainers environment compatible with your project's Spring/SDN versions; graph query behavior cannot be verified by mocking repositories.

### Test Fixture Data

Prepare:

- `C-001` with 0 orders; `C-002` with 3 orders; `C-003` with 500 orders.
- Several orders sharing the same `createdAt` to test pagination tie-breakers.
- An order with multiple `CONTAINS` edges; some orders in `PAID` status, others in `CREATED`.
- Uniqueness constraints on `Customer.customerId`, `Order.orderId`, and `Product.sku` as business identifiers.

### Key Test Cases

| Test | Expectation |
| --- | --- |
| `findProjectedByCustomerId` | Returns exact ID and name without exposing extra fields via the interface contract |
| `CustomerSummary` DTO | Constructor/record parameters match field names accurately |
| Dynamic projection | Same ID maps cleanly to both `CustomerCard` and `CustomerSummary` |
| `Neo4jClient` returning `OrderRow` | Excludes `Product` and returns only the bounded row count |
| Nonexistent customer | Returns empty/404 intentionally; never fabricates a placeholder entity |
| Customer with 0 orders | Count = 0, empty order list |
| Customer with 500 orders, limit 20 | Only 20 rows returned to the API; check plan for large fan-out |
| Two orders with identical timestamps | Keyset pagination neither duplicates nor skips rows due to missing tie-breaker |
| Multi-customer listing | No unintended 1+N query burst |
| Nested projection | Explicit data bounds exist; never dumps massive collections over HTTP |
| Entity from custom `RETURN c` | Never re-saved as a complete aggregate with missing relationships |
| Multi-read transaction | Required consistency level defined; never assumes snapshot isolation by default |

**Measure query counts too**: enable query logging or instrumentation in test environments while avoiding logging PII/sensitive parameters. A test that asserts only JSON output can still miss executing 100 queries or scanning millions of edges.

## 14. Anti-Patterns to Avoid

### "Changing the Return Type to a DTO Guarantees Lower DB Hits"

**False.** DTOs shrink the Java shape; the underlying query can still traverse vast numbers of relationships or fetch extra columns before discarding them. Measure with `PROFILE`.

### "Nested Projections Fetch Only the First Few Orders"

**False without an explicit query/limit.** A `getOrders()` accessor defines no pagination; the collection can grow arbitrarily large.

### "`Page<Customer>` Means Each Customer Has 20 Orders"

**False.** Root entity pagination does not bound child relationships per parent. Extract a dedicated operation for orders with `ORDER BY`/`LIMIT`.

### "With `LIMIT 20`, the Database Only Traverses 20 Edges"

**Not guaranteed.** `Sort` or `Expand` may process far more rows before `LIMIT`, especially when finding the 20 newest orders across a large edge set.

### "A Custom Query Returning One Node Is Enough to Save the Full Entity"

**Never assume this.** SDN entity and relationship mapping follows specific rules. A partial entity loaded for reading is not a full aggregate safe for writing back.

### "One Query Is Always Better Than Three Queries"

**Not always.** One query building an enormous graph can cost more than three targeted queries; yet N+1 is also expensive. Compare based on domain requirements, graph size, and measurements.

### "Just Like JPA, Unneeded Relationships Lazy-Load on Access"

**Do not apply that assumption.** SDN's graph query/mapping model differs from traditional JPA; verify which relationships are actually loaded from executed queries.

### "`@Transactional(readOnly=true)` Makes Multiple Reads an Immutable Snapshot"

**No.** It does not upgrade Neo4j's default read committed isolation; use version checks or locking when business invariants require it.

## 15. Practice Lab: Designing an Endpoint Without Over-Fetching

**Requirement:** Endpoint `GET /customers/{id}/overview` returns:

- `customerId`, `displayName`;
- total order count;
- up to 5 most recent orders, containing only `orderId` and `status`.

**Step 1 — Design the response DTOs.**

~~~java
import java.util.List;

public record CustomerOverview(
        String customerId,
        String displayName,
        long orderCount,
        List<OrderMini> recentOrders
) {}

public record OrderMini(String orderId, String status) {}
~~~

**Step 2 — Choose appropriate queries.** Use `CustomerCard` for root info, `count(DISTINCT o)` for total orders, and a query with `LIMIT 5` for recent orders. When serving a single customer, 2–3 focused queries are often easier to control and test than hydrating an entire entity graph.

**Step 3 — Define missing-data contracts.** A missing customer must return 404; a customer with 0 orders must return `orderCount=0` and `recentOrders=[]`. Never call `single()` on an empty result without explicit error handling.

**Step 4 — Check breadth.** Test with a customer having 500 orders and observe `Rows` in `Expand(All)`. Bound the output query and evaluate how many orders are inspected before picking the top 5.

**Step 5 — Check correctness.** With multiple orders sharing the same `createdAt`, ensure `orderId` acts as a secondary sort key; the query must return 5 deterministic rows matching the sort rules.

**Step 6 — Test multi-customer pages.** If an admin screen needs 100 overviews, avoid looping 3 queries 100 times without measuring. Consider batch queries and per-root bounded subqueries.

**Step 7 — Measure before and after.** Compare full entity mapping against DTOs + bounded Cypher, recording query counts, DB Hits, bytes returned, and p95 latency. Accept optimizations only when **business results remain identical** and cost drops on representative workloads.

### Self-Check Questions

**1. How do interface projections differ from DTO records?**

Interface projections declare accessors and are typically backed by SDN proxies/mappings over entity metadata; DTO records have fixed constructors/fields suited for immutable data contracts. Both still require compatible queries and mappings.

**2. Why is `CustomerWithOrders` dangerous when a customer has 100,000 orders?**

Because a nested projection only declares which relationships to read without bounding collection size. It can increase queried nodes/edges, allocate massive Java objects, and produce oversized responses.

**3. Does `LIMIT 5` after `ORDER BY` guarantee only 5 orders are scanned?**

No. Neo4j may have to inspect and sort many orders to identify the top 5; inspect the execution plan and evaluate better indexes or access paths.

**4. Why should you avoid calling `save(...)` on an entity mapped from a custom query missing relationships?**

Because the entity does not reliably represent the complete graph aggregate, risking confusion over link state and save semantics. Use DTOs for read models or update specific properties explicitly with Cypher.

**5. If query logs show a repository projection and a DTO query emit the exact same Cypher, what can you conclude?**

The projection and DTO may still differ in Java mapping and payload overhead, but you cannot assume lower DB Hits merely because the Java return type changed.

## 16. Pre-Release Checklist for SDN APIs

- [ ] Design **response DTOs** around required fields rather than returning entity graphs by habit.
- [ ] Identify **breadth, depth, and fan-out** of relationships for every use case.
- [ ] Use **closed interface projections** for simple views; use DTO/records or `Neo4jClient` for flat or aggregated results.
- [ ] Check whether nested projections expand overly large collections.
- [ ] Do not treat `Page<Root>` as per-relationship pagination; write dedicated queries for top-N children.
- [ ] Use deterministic `ORDER BY`, bounded `LIMIT`, and proper cursors when paginating.
- [ ] Distinguish rows **returned** from rows **processed** in the execution plan.
- [ ] Prevent N+1 queries; for multiple roots, evaluate `UNWIND` batches or per-root subqueries.
- [ ] Use appropriate labels, relationship types, business keys, and constraints/indexes to optimize entry points.
- [ ] Never re-save partially loaded entities without verifying SDN mapping/saving semantics.
- [ ] Never infer isolation or lazy-loading behavior from JPA habits; verify actual Neo4j/SDN behavior.
- [ ] Measure `EXPLAIN`/`PROFILE`, query count, DB Hits, bytes returned, heap/GC, and API latency.
- [ ] Write integration tests with **high-degree nodes**, duplicate timestamps, and empty query results.

## References

- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
- [Spring Data Neo4j — Repositories](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
- [Spring Data Neo4j — Object Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping.html)
- [Spring Data Neo4j — Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/neo4j-client.html)
- [Neo4j Cypher — Execution Plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)

**Conclusion:** In Spring Data Neo4j, optimizing graph APIs goes beyond picking a Java DTO or interface projection. You must control **which graph is queried**, **how many nodes and relationships are traversed**, **which properties are returned**, and **how results are mapped**. Combining projections/DTOs with selective Cypher, bounded relationships, proper pagination semantics, and empirical measurements keeps API contracts clean while avoiding loading overly broad graphs.
