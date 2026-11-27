# Maintaining Relationships with @Reference and Evaluating Extra Reads

In **Spring Data Redis**, an entity annotated with `@RedisHash` is typically stored as Redis data under the entity's key. When a related object needs to exist independently, the **`@Reference`** annotation lets an entity store a **reference to another Redis entity**, rather than embedding all of that object's data into the parent record.

This choice avoids duplicating the same object many times, at the trade-off of **extra data reads when resolving relationships**. For a list of many entities, the resulting number of reads can be much larger than the initial entity count. Therefore, `@Reference` should be evaluated alongside data access patterns, relationship cardinality, response latency, and key lifecycles.

## 1. Relationships in Redis Differ from Relational Database Relationships

In a relational database, an `orders` table may contain a `customer_id` pointing to the `customers` table. The database engine can use foreign keys to enforce integrity and execute a `JOIN` according to a query plan.

Redis is a key-value data store and does not natively provide SQL-style `JOIN`s or foreign-key constraints across Redis Hashes. Spring Data Redis provides object mapping to make working with entities easier in applications, but those annotations **do not turn Redis into a relational ORM**.

There are three common ways to represent a relationship:

| Representation | Data Stored in Parent Entity | How It Is Read | Best Suited When |
|---|---|---|---|
| **Embedded object** | Child object's properties mapped inside the parent aggregate | Usually fetched in the same read as the parent | Child belongs to parent's lifecycle, is small, and is rarely shared |
| **`@Reference`** | Reference information pointing to another entity's key | Framework must resolve and read the referenced entity | Target object has an independent identity and lifecycle, and must be accessed as an object |
| **Store ID only** | `customerId`, `productIds`, or similar key values | Application decides whether, when, and whether to batch-read the target | Large lists, summary screens, when strict performance control is needed |

**Aggregate design rule:** If an object is always created, modified, and deleted with its parent, embedding it is usually simpler. If the object has its own identity and is shared across multiple aggregates, referencing or storing the ID may be more appropriate.

## 2. What Does `@Reference` Do on Save and Read?

Suppose a customer has many orders. Each order needs to know its corresponding customer, while customer information is maintained independently.

### 2.1. Java Model Using Spring Data Redis Repositories

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;
    private String displayName;

    // Constructors, getters, and setters omitted to focus on mapping.
}
```

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.mapping.Reference;

@RedisHash("orders")
public class Order {
    @Id
    private String id;
    private String status;

    @Reference
    private Customer customer;

    // Constructors, getters, and setters omitted.
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository extends CrudRepository<Customer, String> {
}

public interface OrderRepository extends CrudRepository<Order, String> {
}
```

In this example:

- `Customer` is a Redis entity with its own identifier key, such as `customers:c42`.
- `Order` is another entity, such as `orders:o900`.
- The `customer` field annotated with `@Reference` tells the mapper this is a relationship to **an independently saved Redis entity**.
- When saving `Order`, link info pointing to `Customer`'s key is written inside `Order`'s data. The customer's content is not embedded in full like a regular value object.
- When reading and mapping `Order`, Spring Data Redis may need to additionally read `Customer`'s key to populate the `customer` property.

Conceptual diagram:

```text
Java: Order(id=o900)
      |
      +-- status = "CREATED"
      |
      +-- customer ----> Customer(id=c42, displayName="Lan")

Redis (conceptual description, not a fixed wire format):

orders:o900
   status   = CREATED
   customer = reference to customers:c42
                                |
                                v
customers:c42
   displayName = Lan
```

How Spring Data Redis encodes the reference field in Redis is a mapper detail and may change across versions. **Do not manually write a string `"customers:c42"` into a field expecting it to always match `@Reference`'s internal representation.**

### 2.2. The Target Entity Must Be Saved Separately

```java
Customer customer = new Customer();
// Assume appropriate setters or constructors exist.
customer.setId("c42");
customer.setDisplayName("Lan");
customerRepository.save(customer);

Order order = new Order();
order.setId("o900");
order.setStatus("CREATED");
order.setCustomer(customer);
orderRepository.save(order);

Order loaded = orderRepository.findById("o900").orElseThrow();
Customer loadedCustomer = loaded.getCustomer();
```

`@Reference` **does not provide JPA-style cascade-save behavior**. Calling `orderRepository.save(order)` does not mean the framework automatically ensures `Customer` has been saved. The application must manage creating, updating, and deleting referenced objects under their own lifecycles.

Similarly, deleting `Order` does not automatically delete `Customer`. Deleting `Customer` can leave remaining orders holding dangling references with no target. Redis also does not check foreign-key constraints to block that operation.

The snippets above illustrate structure; in a real project, declare constructors, accessors, ID types, and repositories matching your application's entity model.

## 3. Read Overhead Caused by `@Reference`

Consider the call:

```java
Order order = orderRepository.findById("o900").orElseThrow();
```

From the Java side there is only **one repository call**, yet restoring `Order` may require:

1. Locating and reading the order key's data.
2. Detecting that the `customer` field is mapped with `@Reference`.
3. Reading data from the referenced customer key.
4. Converting the customer data into a `Customer` object and attaching it to `Order`.

Thus, **one repository call does not equal one Redis read operation**.

Relationships via `@Reference` are typically resolved during object mapping; do not assume JPA-proxy-style lazy-loading behavior. Depending on the read path, library version, and entity structure, actual Redis commands may differ from the minimal diagram. What needs to be evaluated is **how many entities must be fetched to serve a request** and **how many network round-trips occur**.

### 3.1. Estimating Read Count by Relationship

Suppose a screen needs to load `N` orders. Each order references one customer and one salesperson. If each relationship is resolved independently without caching or deduplication, the logical number of entity reads is roughly:

```text
Entity reads = N Order reads
             + N Customer reads
             + N Salesperson reads
             = N × (1 + 2)
```

With `N = 200`:

```text
200 Orders
+ 200 Customers
+ 200 Salespersons
------------------
~600 entity reads
```

This is an **estimation model**, not a guarantee that one entity read always equals exactly one Redis command or one round-trip. Finding ID lists, reading secondary indexes, resolving relationships, and pipelining can change command counts or network round-trips.

| Scenario | Root Entities | References per Entity | Estimated Entity Fetches |
|---|---:|---:|---:|
| Viewing one order's details | 1 | 1 | 2 |
| List of 50 orders | 50 | 1 | 100 |
| List of 200 orders | 200 | 2 | 600 |
| List of 1,000 orders | 1,000 | 3 | 4,000 |

The numbers in the table assume every reference is loaded and no duplicate reads are reused. They help surface **potential load scale** before deciding to use `@Reference` on list read paths.

### 3.2. Deeply Nested Relationships Multiply Cost

Example:

```text
Order
  └── @Reference Customer
        └── @Reference AccountManager
              └── @Reference Team
```

One `Order` read can trigger a whole chain of additional reads. If each node references multiple child nodes, fetch volume can grow rapidly with graph depth.

Do not create cyclic relationships like `Order → Customer → Orders → Customer` assuming the framework will automatically break cycles or cache all loaded objects. Cyclic relationships, large graphs, or heavily branching data must be designed explicitly, depth-limited, and verified against the mapper's behavior in your running version.

### 3.3. Many Orders Pointing to the Same Customer

Suppose 200 orders belong to only 20 customers. If every `@Reference` resolution issues a separate fetch, the application still risks reading each customer multiple times.

```text
200 Orders ──> 20 unique Customer IDs

Loading each reference directly:
  ~200 Customer lookups

If the application batches IDs and reads each Customer once:
  ~20 Customer lookups
```

Repeated target keys are very common on listing pages, reports, and aggregation APIs. **Do not assume Spring Data Redis has an identity map or deduplication across a list result.** Actual efficiency must be measured at the Redis boundary.

## 4. N+1 in Redis: Spotting It by Usage Scenario

In SQL, N+1 is typically one list query followed by N related queries. In Redis, the same phenomenon happens when a request reading N parent entities triggers N or more reads of referenced keys.

```text
HTTP GET /orders?limit=100
          |
          v
Find 100 order IDs
          |
          v
Read 100 Orders
          |
          +--> Order 1 -> read Customer 1
          +--> Order 2 -> read Customer 2
          +--> Order 3 -> read Customer 3
          ...
          +--> Order 100 -> read Customer 100
          |
          v
Return JSON to client
```

Each Redis command can be very fast, yet hundreds or thousands of sequential commands still consume network time, serialization/deserialization CPU, memory, and Redis load. This effect becomes more pronounced when the application and Redis sit in different network zones, when Redis is busy, or when an object references several more objects.

Pay attention to **the screen's access pattern**. An order detail page may benefit from `@Reference` for clarity and convenience. An overview page displaying only `orderId`, status, and total amount may **not need to load any `Customer` object** at all.

Thus, a functionally valid mapping may still be unsuitable for every read flow.

## 5. When to Embed vs. When to Use `@Reference`?

Do not pick `@Reference` simply because a Java field has another class type. Examine which aggregate the child belongs to, whether it is shared, and what data the API needs.

### 5.1. Embedding Value Objects with the Same Lifecycle

```java
public class ShippingAddress {
    private String street;
    private String city;
    private String postalCode;

    // Getters/setters...
}

@RedisHash("orders")
public class Order {
    @Id
    private String id;
    private ShippingAddress shippingAddress;
}
```

A shipping address captured at order placement time should usually be stored **as a snapshot on the order**. If the customer's current default address later changes, historical order data should not change with it. Embedding data also avoids an extra read to resolve the relationship.

The trade-off is data duplication: if a value object is shared and must be updated across the board, embedding it in thousands of records makes bulk updates expensive. For historical snapshots, however, that independence is usually a business requirement.

### 5.2. Referencing Entities with Independent Identity

```java
@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Reference
    private Customer customer;
}
```

This makes sense when handling an order typically requires fetching independently managed customer information, the relationship graph is small, and the read cost is acceptable.

However, `@Reference` does not automatically handle scenarios where the customer is deleted, changes keyspace, changes ID, or expires before the order.

### 5.3. Storing IDs When You Need Explicit Control Over Loading Relationships

```java
@RedisHash("orders")
public class OrderSummary {
    @Id
    private String id;
    private String customerId;
    private String status;
    private long totalAmountInCents;

    // Getters/setters...
}
```

`customerId` is a scalar field of the aggregate. When reading `OrderSummary`, Spring Data Redis does not need to resolve a `Customer` to map that field.

The list read path can fetch orders only. The detail view can then call the customer repository or a relationship-fetching service. That way, the reads incurred match **the data actually needed for the response**.

There is no single right choice for every relationship: the same domain can use embedded snapshots for shipping addresses, `@Reference` for a few small links, and plain IDs for lists or large graphs.

## 6. Reducing Duplicate Reads by Storing IDs and Batching Data

Suppose an API displays 200 orders along with each order's customer name, and many orders share the same customer.

If `@Reference` is placed directly on the entity loaded for every row, mapping may issue repeated customer reads. Another option is to **store the ID in the order and collect unique customer IDs**.

### 6.1. Two-Stage Read Example

Assume `OrderSummary` has `id`, `customerId`, and `status`; `Customer` has `id` and `displayName`, and both classes have appropriate getters.

```java
import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class OrderQueryService {

    private final OrderSummaryRepository orders;
    private final CustomerRepository customers;

    public OrderQueryService(
            OrderSummaryRepository orders,
            CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public List<OrderListItem> load(Collection<String> orderIds) {
        List<OrderSummary> orderList = StreamSupport
                .stream(orders.findAllById(orderIds).spliterator(), false)
                .toList();

        Set<String> customerIds = orderList.stream()
                .map(OrderSummary::getCustomerId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());

        Map<String, Customer> byId = new HashMap<>();
        customers.findAllById(customerIds).forEach(customer ->
                byId.put(customer.getId(), customer));

        return orderList.stream()
                .map(order -> {
                    Customer customer = byId.get(order.getCustomerId());
                    return new OrderListItem(
                            order.getId(),
                            order.getStatus(),
                            order.getCustomerId(),
                            customer == null ? null : customer.getDisplayName());
                })
                .toList();
    }

    public record OrderListItem(
            String orderId,
            String status,
            String customerId,
            String customerName) {
    }
}
```

Corresponding repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface OrderSummaryRepository
        extends CrudRepository<OrderSummary, String> {
}
```

Execution sequence:

1. Read the orders to display.
2. Collect distinct `customerId` values.
3. Read each needed customer via the repository.
4. Join data in memory into DTOs returned to the client.
5. Define how to handle missing customer references; for example, `customerName = null` while keeping `customerId` for investigation.

In the case of 200 orders pointing to 20 unique customers, this can reduce the number of **logical customer entity fetches** from roughly 200 down to 20, if each reference was previously read separately.

**Important limitation:** `CrudRepository.findAllById(...)` does not automatically guarantee Redis receives a single command or a single network round-trip. It helps the application specify the set of IDs to read and remove duplicate IDs. To truly optimize round-trips, evaluate repository execution mechanics or proactively design pipelining/batching at the appropriate Redis layer.

### 6.2. Pipelining: Reduces Round-Trips, Doesn't Merge Keys into One Object

Redis pipelining lets you send multiple commands without waiting for each command's reply before sending the next. When reading many independent Redis Hashes, pipelining can reduce network latency compared to sequential commands.

However, distinguish carefully:

| Technique | Reduces Logical Objects to Read? | Reduces Redis Commands? | Can Reduce Network Round-Trips? |
|---|---|---|---|
| Omitting unneeded relationships from DTO | Yes | Yes | Yes |
| Deduplicating by ID | Yes, when references share IDs | Yes, on the deduplicated read path | Yes |
| Pipelining | No | Not necessarily | Yes |
| Caching target object lookups | Yes, on cache hit | Yes | Yes |
| Embedding snapshot | Avoids reading separate referenced key | Yes, for the parent read flow | Yes |

If using `RedisTemplate.executePipelined(...)`, ensure keyspace and serializers match the stored data, and convert Hashes through appropriate mapping. Do not read raw bytes assuming `@RedisHash` Hash data is a JSON string. Moving from repository to pipelining may require designing a dedicated read model; in return, the application gains explicit control over read operations.

`MGET` works on **string-value keys**, not as a bulk read command for arbitrary Redis Hashes. Do not use `MGET` instead of `HGETALL` for entities stored as Hashes by a repository.

## 7. Not Every Relationship Should Be Loaded When Serving an API

The same entity can serve multiple screens:

| Use Case | Data Actually Needed | Handling Approach |
|---|---|---|
| Viewing order details | Order and some customer details | `@Reference` may suffice if the graph is small |
| Listing 100 orders | ID, status, total amount | Scalar-only read model, avoid loading relationships |
| Revenue report by customer | Many orders, grouped by customer | Store IDs, batch by key; consider a separate aggregation model |
| Checking if customer is still active | Latest status of the customer | Read from the appropriate source, do not rely on stale snapshots |
| Delivery history | Address at order placement time | Embed snapshot inside the order |

A list API should usually use a DTO and query strictly what it needs. If the repository layer always resolves `@Reference` fields before the application converts to a DTO, dropping fields in JSON **does not reclaim the Redis cost already incurred**. To avoid reads, change how data is fetched before the mapping stage or use a different storage/read model.

## 8. TTL, Deleted Data, and Dangling References

Redis supports key expiration. Two entities linked via `@Reference` do not automatically synchronize lifecycles just because of the annotation.

Example:

```text
orders:o900 (TTL: 7 days)
   |
   +--> references customers:c42 (TTL: 30 minutes)

After 30 minutes:
orders:o900 still exists
customers:c42 may have expired
```

At that point `Order`'s data still exists, while the referenced object cannot be loaded. How the framework represents a dangling reference in the Java object should be verified against your specific version and configuration; **do not build business logic assuming relationships always exist**.

Possible handling strategies:

- **Align lifecycles:** long-lived entities should not directly point to short-lived cache keys if they must be resolved throughout the parent's lifetime.
- **Keep fallback identifiers:** store `customerId` as a scalar if you need to know who was referenced even when the target record is gone.
- **Minimal snapshot:** store historical attributes that must be preserved, such as recipient name or address at checkout.
- **Controlled deletion workflow:** when deleting a customer, decide per business rules whether to block deletion, anonymize details, unlink, or keep historical records.
- **Versioning and migration:** changing keyspace prefixes, ID formats, or entity classes can prevent old references from resolving as before. Plan migrations or backward compatibility.
- **Explicit response on missing target:** in ID-based flows, decide whether to return `null`, raise a business error, or fall back to a source-of-truth store.

Note that updating two related Redis Hashes with two separate save commands is not automatically a single consistent transaction across the whole aggregate. `@Reference` does not provide foreign-key referential integrity constraints.

## 9. Evaluating True Cost: Command Count, Latency, and Redis Load

Do not draw conclusions solely from lines of Java code. Measure on **a concrete use case** with a dataset realistic enough to resemble production.

### 9.1. Form a Cost Hypothesis Before Measuring

For example, an endpoint returns 100 orders, each with two references. Note down:

```text
Input load:                 100 orders / request
References per order:       2
Unique target IDs:          35 customers, 8 salespersons
Approx logical reads if resolved independently: 100 + 200 = 300
Logical reads when batching IDs:                100 + 35 + 8 = 143
```

The numbers `300` and `143` are **logical hypotheses for comparing designs**. Measured command counts, round-trips, and processing times may not match those numbers exactly.

In particular, measure **p95/p99** rather than only averages: a request that happens to hit many uncached keys or deep relationships can be dramatically slower.

### 9.2. What to Measure?

| Metric | Question to Answer |
|---|---|
| Total Redis commands per endpoint | How many commands does a single request trigger? |
| Hash or related-key read counts | Are there multiple separate reads for the same ID? |
| Round-trips and Redis latency | Do commands run sequentially or get pipelined? |
| Endpoint latency p50/p95/p99 | Does N+1 degrade experience as lists grow? |
| Redis CPU and bandwidth | Do numerous Hashes and serializers create bottlenecks? |
| App memory and mapping time | Is the object graph oversized relative to the DTO returned? |
| Dangling reference count | Are TTLs or deletions breaking relationships? |

For systems using Lettuce, you can configure command latency collection and integrate telemetry matching the application's observability stack. With Micrometer/Actuator, add service-layer timers and dashboards tied to endpoints. Measure **work generated by the mapper and repository** as well, not just handwritten relationship-loading code.

On Redis, these inspection commands help reveal overall trends:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

- `INFO commandstats` reflects per-command statistics across the **entire Redis instance**, so compute deltas over measurement windows and isolate noise from other requests.
- `SLOWLOG` shows commands whose Redis-side execution time exceeded a threshold; it **does not** list fast commands repeated thousands of times, nor does it include full network time.
- `MONITOR` can aid investigation in small test environments, but adds overhead and can expose command data; avoid enabling it on busy production Redis instances to measure full request traffic.

To attribute exact command counts to a single request, use time-bounded client-side Redis instrumentation alongside an isolated load scenario. Global Redis stats alone cannot prove how many reference reads one endpoint triggers.

### 9.3. How to Compare Two Designs

Test with the same dataset, same order count, and same concurrency level:

1. **Design A:** `@Reference Customer` and related references on the returned entity.
2. **Design B:** store IDs, deduplicate unique IDs, and build DTOs as needed.
3. If bottlenecks remain, try **Design C:** Design B combined with pipelining or a specialized read model.
4. Compare payload volume returned, Redis command counts, mapping time, and end-to-end latency.
5. Test both when customers repeat heavily and when nearly all IDs are distinct.

Do not attribute the entire performance difference to `@Reference` if the two designs use different Hash sizes, serializers, or caching strategies. Test under equivalent configurations and observe the root causes.

## 10. Situations That Commonly Skew Design

### 10.1. Using `@Reference` for Unbounded Lists

```java
@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Reference
    private List<Order> orders;
}
```

If a customer has tens of thousands of orders, reading the customer risks pulling in a massive graph. This list is also hard to paginate on an entity property. For large one-to-many relationships, usually store the relationship via **IDs or a paginated query index**, then fetch one page of orders separately.

### 10.2. Using References for Immutable Historical Data

If an order must preserve the recipient's name and address at checkout time, merely referencing the current customer profile will not reflect history accurately. Store critical snapshots on the order; you can keep `customerId` as well to identify the original customer.

### 10.3. Treating `@Reference` as an Existence-Guaranteeing Foreign Key

Writing a reference does not guarantee the target key exists forever. Redis does not check foreign keys. Enforce existence, TTLs, deletions, and ID changes in business logic.

### 10.4. Expecting the Repository to Auto-Optimize Every Fetch

Repositories make entity mapping and data APIs convenient. Calling `findAllById` or `findById` does not automatically imply the framework deduplicates repeated references, pipelines all queries, or lazy-loads on demand. Verify such assumptions through measurements in the real application.

### 10.5. Measuring Only HTTP Request Counts

One HTTP request can generate a few Redis commands or thousands of Redis commands. When optimizing, observe Redis read counts and latency at the data access layer.

## 11. Complete Case Study: Order Management Screen

A management system has 10,000 orders, 800 customers, and 40 salespersons. The admin page displays 100 orders at a time, along with customer name and salesperson name.

### Initial Design

```java
@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Reference
    private Customer customer;

    @Reference
    private Salesperson salesperson;

    // Other properties...
}
```

For a 100-order page, the simple read model fetches 100 order entities and potentially triggers 200 reference resolutions. Actual operations also depend on Spring Data Redis execution, caching layers, and duplicate IDs.

### Adjusted Design

```java
@RedisHash("orders")
public class OrderListRecord {
    @Id
    private String id;
    private String customerId;
    private String salespersonId;
    private String status;
    private long totalAmountInCents;
}
```

Retrieval workflow:

```text
Receive request for page of 100 OrderListRecords
                   |
                   v
           Read 100 orders
                   |
                   v
     Collect unique customerIds
     Collect unique salespersonIds
                   |
                   v
     Read required target entities
        (can batch/pipeline)
                   |
                   v
          Assemble into DTOs
                   |
                   v
              Return API
```

Suppose the 100 orders on this page point to only 28 customers and 7 salespersons:

- Under per-reference independent reading: roughly **100 + 100 + 100 = 300** entity fetches.
- After deduplicating by ID: roughly **100 + 28 + 7 = 135** entity fetches.
- If the page does not display customer or salesperson names, the read model only needs **100 orders**, resolving zero relationships.

If the order detail screen needs the full `Customer` object and only reads one order at a time, using `@Reference` in an appropriate model can still be a clean choice. You can maintain **different write and read models** for the same domain, provided the application has a clear way to keep them synchronized.

## 12. Checklist for Choosing Relationships

Before adding `@Reference` to a Redis entity, answer:

1. Does the target object have its own ID and lifecycle, or is it really a value object belonging to the parent aggregate?
2. When reading the parent, **is the full data of the target object always needed**?
3. What is the maximum number of parents a request can read, how many references per parent, and to what depth?
4. Do multiple parents point to **the same ID**? Can duplicate IDs be batched?
5. If the target object is deleted or its TTL expires before the parent, how must the business logic behave?
6. Are keyspace names, ID types, or mapping models likely to change during deployment/migration?
7. Have you measured Redis command counts, p95/p99 latency, and mapping cost on a realistic read flow?

**Technical conclusion:** `@Reference` is a tool for expressing relationships between independent Redis entities. It lets the Java model express direct links and avoid embedding shared data, but resolving relationships on read increases fetch counts. For single-entity read paths and small graphs, clarity benefits may outweigh the cost. For lists, many-to-many relationships, repeated references, or deep graphs, consider storing IDs, dedicated read models, deduplication, and appropriate pipelining. Base the final decision on **the actual Redis reads of the use case**, along with data consistency and lifecycle requirements.
