# Combining Query Conditions and Verifying Supported Capabilities

## 1. The Problem: Finding Data by Multiple Conditions in Redis

Suppose a Spring Boot application stores order information in Redis. Users want to find:

- Orders with **status PAID** and belonging to **channel WEB**.
- Orders with **status PAID** or belonging to **channel MOBILE**.
- Orders that are **active**, have a **total amount greater than 500,000 VND**, sorted from newest to oldest.
- Orders with status PAID whose **delivery location is near** a given coordinate.

All of the requirements above are "multi-condition queries", yet they do not share the same level of support in Spring Data Redis. The difference stems from how Redis stores data and how Spring Data Redis constructs queries.

In a relational database, we are familiar with:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
  AND channel = 'WEB'
ORDER BY created_at DESC;
~~~

Standard Redis has no mechanism to execute SQL like this over Repository Redis Hashes. **Spring Data Redis Repositories** solve some queries using **secondary indexes**, typically represented by Redis Sets containing entity identifiers. Simple conditions such as equality, `AND`, and `OR` reduce to set operations. Other kinds of conditions require checking actual feature support.

The goal of this lesson in the **Indexes and Queries** chapter is to know when conditions can be combined via Repositories, when not to extrapolate from general Spring Data syntax, and how to choose an appropriate solution when Redis Repositories alone do not cover the requirement.

## 2. Foundation: Secondary Indexes Link Values to ID Sets

### 2.1. Entities Stored as Redis Hashes

Let's use an illustrative entity:

~~~java
package com.example.orders;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orders")
public class Order {

    @Id
    private String id;

    @Indexed
    private String status;

    @Indexed
    private String channel;

    @Indexed
    private Boolean active;

    private long totalAmount;
    private Instant createdAt;

    public Order() {
    }

    public Order(
            String id,
            String status,
            String channel,
            Boolean active,
            long totalAmount,
            Instant createdAt) {
        this.id = id;
        this.status = status;
        this.channel = channel;
        this.active = active;
        this.totalAmount = totalAmount;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getChannel() {
        return channel;
    }

    public void setChannel(String channel) {
        this.channel = channel;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }

    public long getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(long totalAmount) {
        this.totalAmount = totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

In this case:

- `@RedisHash("orders")` defines the entity's keyspace.
- `@Id` defines the identifier.
- `@Indexed` on `status`, `channel`, and `active` instructs Spring Data Redis to maintain corresponding indexes.
- `totalAmount` and `createdAt` are still stored inside the entity, but **do not yet have indexes for querying by their values**.

With several orders, the logical data might look like:

| ID | Status | Channel | Active | Total amount |
|---|---|---|---|---:|
| o-101 | PAID | WEB | true | 700000 |
| o-102 | PAID | MOBILE | true | 400000 |
| o-103 | PENDING | WEB | true | 300000 |
| o-104 | CANCELLED | STORE | false | 900000 |
| o-105 | PAID | WEB | false | 200000 |

When `repository.save(order)` is called, Spring Data Redis stores the entity and updates the configured secondary index keys. An illustrative model of the Sets is:

~~~text
orders:status:PAID      = {o-101, o-102, o-105}
orders:status:PENDING   = {o-103}
orders:status:CANCELLED = {o-104}

orders:channel:WEB      = {o-101, o-103, o-105}
orders:channel:MOBILE   = {o-102}
orders:channel:STORE    = {o-104}

orders:active:1         = {o-101, o-102, o-103}
orders:active:0         = {o-104, o-105}
~~~

The example key names show basic Spring Data Redis indexing conventions; value representation and metadata may vary by property type, converter, and library version. These Sets contain **IDs**, not entire `Order` objects.

If the program merely stores JSON via `RedisTemplate.opsForValue().set(...)` without using the Repository mechanism, `@Indexed` **does not automatically create** these index sets.

### 2.2. An Equality Lookup Is Essentially Reading an ID Set

To find orders with `status = PAID`:

~~~text
Query: status = PAID
           |
           v
Set: orders:status:PAID
           |
           v
{o-101, o-102, o-105}
           |
           v
Read Hashes orders:o-101, orders:o-102, orders:o-105
           |
           v
List of Order objects
~~~

This is the basis for combining multiple conditions: operate on **candidate ID sets** first, then materialize the entities.

## 3. AND Condition: Taking the Intersection of Index Sets

Requirement: fetch orders with `status = PAID` **and** `channel = WEB`.

Set representation:

~~~text
A = {o-101, o-102, o-105}     (status = PAID)
B = {o-101, o-103, o-105}     (channel = WEB)

A ∩ B = {o-101, o-105}
~~~

In Redis, set intersection corresponds to `SINTER`:

~~~redis
SINTER orders:status:PAID orders:channel:WEB
~~~

In a **Redis Repository**, you can express the condition using a derived query method:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByStatusAndChannel(
            String status,
            String channel
    );
}
~~~

Invocation:

~~~java
List<Order> paidWebOrders =
        repository.findByStatusAndChannel("PAID", "WEB");
~~~

The method name can be understood as:

~~~text
findBy + Status + And + Channel
         equality      equality
~~~

**Prerequisite:** both `status` and `channel` must have suitable Redis Repository indexes. If only `status` is indexed, adding `AndChannel` to the method name does not magically grant querying by `channel`.

At the data level, intersection shrinks the set of IDs to load. That is a major difference from fetching all `PAID` orders, reading every Hash, and checking `channel` in Java.

## 4. OR Condition: Taking the Union of Index Sets

Requirement: find orders with `status = PAID` **or** `channel = WEB`.

~~~text
A = {o-101, o-102, o-105}     (status = PAID)
B = {o-101, o-103, o-105}     (channel = WEB)

A ∪ B = {o-101, o-102, o-103, o-105}
~~~

Redis provides the union command `SUNION`:

~~~redis
SUNION orders:status:PAID orders:channel:WEB
~~~

The repository can declare:

~~~java
List<Order> findByStatusOrChannel(
        String status,
        String channel
);
~~~

Example:

~~~java
List<Order> orders =
        repository.findByStatusOrChannel("PAID", "WEB");
~~~

An ID present in both Sets appears only **once** in the Redis set union result. However, remember that sets have no default business ordering. If a specific order is required, consider a dedicated sorting mechanism.

Semantically:

| Condition | Set Operation | Example Result |
|---|---|---|
| `status = PAID AND channel = WEB` | Intersection: `SINTER` | `o-101, o-105` |
| `status = PAID OR channel = WEB` | Union: `SUNION` | `o-101, o-102, o-103, o-105` |

An `OR` condition generally **widens** the result set. A two-condition query using `OR` can still return a huge number of records and consume considerable memory and entity-loading time.

## 5. Verifying Exact Keyword Support

### 5.1. You Cannot Assume Redis Supports Every Spring Data Keyword

Spring Data Commons provides general syntax for parsing method names, but **parser recognition does not mean Redis Repositories can execute that query**.

For example, in other datastore modules, learners may encounter:

~~~java
findByTotalAmountGreaterThan(...)
findByCreatedAtBetween(...)
findByCustomerNameContaining(...)
findByStatusNot(...)
findByStatusIn(...)
~~~

Do not assume these methods behave as they do in Spring Data JPA. Consult the **Spring Data Redis-specific support table** for the exact version in use.

For Spring Data Redis 3.5, the query keyword groups directly listed in the Redis-specific documentation include:

| Group | Method Example | Mechanism or Meaning |
|---|---|---|
| Equality | `findByStatus(...)` | Look up by index of a single value |
| `Is`, `Equals` | `findByStatusIs(...)`, `findByStatusEquals(...)` | Alternative ways to express equality |
| `And` | `findByStatusAndChannel(...)` | Intersection of indexed ID sets |
| `Or` | `findByStatusOrChannel(...)` | Union of indexed ID sets |
| `IsTrue` | `findByActiveIsTrue()` | Look up by boolean property index with value true |
| `IsFalse` | `findByActiveIsFalse()` | Look up by boolean property index with value false |
| `Top`, `First` | `findFirst10ByStatus(...)` | Limit result count per Repository capabilities |

Keywords such as `GreaterThan`, `LessThan`, `Between`, `Containing`, `Like`, `Regex`, `Not`, and `In` **are not in the basic query keyword table for Redis Repositories 3.5**. Before using them, verify actual support in your version and data model; if unavailable, choose another query approach.

Do not overgeneralize by claiming Redis as a whole "cannot" filter ranges or do full-text search. Redis has specialized data types/commands and can offer Redis Query Engine (formerly commonly called RediSearch). It is simply that **Spring Data Redis Repositories built on standard Set indexes do not automatically turn all those operations into supported queries**.

### 5.2. Boolean Condition Example

Declaration:

~~~java
List<Order> findByActiveIsTrue();

List<Order> findByActiveIsFalse();
~~~

Invocation:

~~~java
List<Order> activeOrders = repository.findByActiveIsTrue();
List<Order> inactiveOrders = repository.findByActiveIsFalse();
~~~

With `@Indexed private Boolean active;`, boolean values are mapped into the corresponding index mechanism. This query pattern fits when looking up by a specific flag.

If you want to combine a boolean with other conditions, check the exact method generated by Spring Data Redis. A clear way to express a two-property indexed query is using explicit equality conditions, for example:

~~~java
List<Order> findByStatusAndActive(
        String status,
        Boolean active
);
~~~

### 5.3. Decision Table by Business Requirement

| Requirement | Redis Repository with Standard Indexes | What to Verify |
|---|---|---|
| `status = PAID` | Yes, if indexed | Index values and entity data are consistent |
| `status = PAID AND channel = WEB` | Yes, via `And` | Both properties are indexed |
| `status = PAID OR channel = WEB` | Yes, via `Or` | Result set size |
| `active = true` | Yes, via `IsTrue` | Boolean is indexed |
| `totalAmount > 500000` | Not guaranteed by basic keyword table | Need another structure/handler for range conditions |
| `createdAt BETWEEN a AND b` | Not guaranteed by basic keyword table | Need time-based index and suitable range query |
| `name CONTAINING 'abc'` | Should not be assumed | Text search requires a suitable solution |
| `status != CANCELLED` | Do not assume `Not` works | Need to define candidate set and exclusion logic |
| Filter by nearby coordinates | Separate geo query path with `@GeoIndexed` | Does not freely combine `near`/`within` with other conditions |
| Filter then sort by time | Sorting methods exist | Ordering may be computed application-side after loading results |
| Filtered pagination | Repository has paging support | Cost of fetching and sorting candidate sets |

The key point is **checking each operation against Redis and Spring Data Redis execution capabilities**, rather than merely looking at whether a method name appears valid.

## 6. Combining Multiple `AND`/`OR`s and Method-Name Expressiveness Limits

For two-property conditions, `And` and `Or` are relatively straightforward. However, business queries are often more complex:

~~~text
(status = PAID AND channel = WEB)
OR
(status = PENDING AND channel = MOBILE)
~~~

Or:

~~~text
status = PAID
AND
(channel = WEB OR channel = MOBILE)
~~~

Mathematically, these can be expressed as:

~~~text
(A ∩ B) ∪ (C ∩ D)

A ∩ (B ∪ C)
~~~

Redis Sets allow combining intersections and unions at the data level. However, parsing combined expressions in **long Repository method names** may follow fixed precedence rules, and the API itself has no direct SQL-like parenthesization syntax.

Do not assume that:

~~~java
findByStatusAndChannelOrActive(...)
~~~

always matches the grouping intended by business logic. When conditions go beyond simple forms, write out the **truth table** or desired set expression explicitly and pick a verifiable implementation.

Set example:

~~~text
A = status:PAID
B = channel:WEB
C = channel:MOBILE

Need: A ∩ (B ∪ C)
~~~

You can split it into two simple Repository queries and merge by ID in the service layer **if the result set is size-bounded**:

~~~java
public List<Order> paidWebOrMobile(
        OrderRepository repository) {

    List<Order> web =
            repository.findByStatusAndChannel("PAID", "WEB");
    List<Order> mobile =
            repository.findByStatusAndChannel("PAID", "MOBILE");

    Map<String, Order> unique = new LinkedHashMap<>();

    for (Order order : web) {
        unique.put(order.getId(), order);
    }
    for (Order order : mobile) {
        unique.put(order.getId(), order);
    }

    return new ArrayList<>(unique.values());
}
~~~

Required `import`s for the method snippet above:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
~~~

This example demonstrates **explicit combining logic** and ID deduplication. It works well for learning or small sets. For large datasets, running two queries and loading all objects into memory can become expensive. In those cases, look into combining **IDs via Sets in Redis**, or changing the index model.

## 7. Combining IDs with Redis Sets and Re-Loading Entities

Suppose two index sets exist:

~~~redis
SMEMBERS orders:status:PAID
SMEMBERS orders:channel:WEB
~~~

For `status = PAID AND channel = WEB`:

~~~redis
SINTER orders:status:PAID orders:channel:WEB
~~~

For `status = PAID OR channel = WEB`:

~~~redis
SUNION orders:status:PAID orders:channel:WEB
~~~

To illustrate manual operations, you can use `StringRedisTemplate` when you know for sure that index keys store string IDs under your current configuration:

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class IndexedOrderLookup {

    private final StringRedisTemplate redis;
    private final OrderRepository orders;

    public IndexedOrderLookup(
            StringRedisTemplate redis,
            OrderRepository orders) {
        this.redis = redis;
        this.orders = orders;
    }

    public List<Order> findPaidWebOrders() {
        Set<String> ids = redis.opsForSet().intersect(
                "orders:status:PAID",
                "orders:channel:WEB"
        );

        if (ids == null || ids.isEmpty()) {
            return List.of();
        }

        List<Order> result = new ArrayList<>();
        orders.findAllById(ids).forEach(result::add);
        return result;
    }
}
~~~

Workflow:

~~~text
SINTER index-A index-B
           |
           v
      intersected IDs
           |
           v
 repository.findAllById(ids)
           |
           v
     matching Orders
~~~

Points to understand:

- This is a **Set index illustration**. Default index key names, ID encoding, and metadata managed by Spring Data Redis can vary by configuration. If the project customizes keyspaces or serializers, derive conventions properly instead of hardcoding key names.
- `findAllById` does not guarantee an order matching the ID set. Redis Sets have no stable ordering.
- There may be a moment when an ID is still in the index set while the entity has been deleted or expired. Applications must tolerate missing objects on retrieval.
- `SINTER` and `SUNION` may still process and return huge ID sets. Moving the combination to Redis does not automatically make the query cheap.
- When custom queries are needed, Spring Data Redis also provides `RedisCallback` or access via `RedisTemplate`/`RedisConnection`. These offer direct control over Redis commands, though maintaining index consistency must still be designed carefully.

In this example, choosing **Repository `findByStatusAndChannel`** is usually simpler. Only drop down to manual Set operations when there is a clear requirement that Repositories cannot express.

## 8. Sorting and Top/First Do Not Mean Redis Creates a Sort Index

### 8.1. Sorting Query Results

Spring Data Redis Repositories support sorting syntax such as:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByStatusOrderByCreatedAtDesc(String status);

    List<Order> findByStatus(String status, Sort sort);
}
~~~

Invocation:

~~~java
List<Order> newestPaid =
        repository.findByStatusOrderByCreatedAtDesc("PAID");

List<Order> oldestPaid = repository.findByStatus(
        "PAID",
        Sort.by(Sort.Direction.ASC, "createdAt")
);
~~~

Under Redis Repository mechanics, index sets do not provide ordering by `createdAt`. Consequently, Spring Data Redis may construct a `Comparator` to **sort results on the application side** after loading matching entities.

This differs from queries using sorted indexes in a relational database management system. When hundreds of thousands of orders match, reading all records and sorting them can consume significant CPU and memory.

A common misconception: `@Indexed` on `status` is an index for **filtering**, not turning `createdAt` into a time index or making `ORDER BY` execute for free inside Redis.

### 8.2. Limiting Result Counts

Spring Data Redis also supports `Top` or `First` in method names, for example:

~~~java
List<Order> findFirst10ByStatus(String status);

List<Order> findTop5ByChannel(String channel);
~~~

These names request capping the number of returned elements. However:

- Limiting the count does not guarantee the results are "the 10 newest records" unless an ordering is defined.
- Capping elements does not mean Redis only reads that exact number of IDs or objects across the whole query process.
- If sorting is involved, check where sorting runs and how much data must be loaded before capping.

For **"the 10 newest orders with status = PAID"** over a large dataset, a dedicated Sorted Set by timestamp (such as `ZADD` scored by creation time) or a search engine with an appropriate index is usually worth considering.

### 8.3. Pagination Can Have Hidden Costs

Spring Data Redis Repositories support queries returning collections of entities with pagination. API example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Order> findByStatus(String status, Pageable pageable);
~~~

However, `Pageable` does not turn a Redis Set into a list pre-sorted by multiple attributes. When using pagination and sorting, consider:

- Total number of candidate elements in the index.
- Cost of reconstructing entities.
- Application-side sorting cost.
- Determining total element counts for `Page`.
- Data mutating between page requests; it is not a consistent snapshot.

If the application repeatedly needs page `N` ordered by `createdAt` across a very large dataset, having `Pageable` in the method signature is not enough to guarantee good response times.

## 9. Range and Text Conditions: Choose Different Structures

### 9.1. Numeric or Time Range Queries

Example:

~~~text
totalAmount >= 500000
createdAt in [start, end]
~~~

Standard `@Indexed` indexes are based on **exact equality**; they do not automatically build a structure ordered by amount or time to scan a continuous interval.

A Redis Sorted Set (`ZSET`) can work well when querying by score:

~~~redis
ZADD orders:by-created-at 1760000000 o-101
ZADD orders:by-created-at 1760000300 o-102
ZADD orders:by-created-at 1760000600 o-103

ZRANGE orders:by-created-at 1760000000 1760000500 BYSCORE
~~~

The example uses epoch seconds as scores and queries between two timestamps. In real applications, handle timestamp precision, duplicate IDs, updates, and removals from the ZSET.

For monetary ranges:

~~~redis
ZADD orders:by-amount 700000 o-101
ZADD orders:by-amount 400000 o-102
ZADD orders:by-amount 300000 o-103

ZRANGE orders:by-amount 500000 +inf BYSCORE
~~~

However, this is a **custom index** managed by the application. Simply placing `@Indexed` on `totalAmount` and writing `findByTotalAmountGreaterThan` does not automatically give you a ZSET query like this.

Combining `status = PAID` with an amount range may require intersecting the status index ID set with the score-based ID list, or designing another query structure. Implementation and consistency costs must be evaluated upfront.

### 9.2. Text Queries

Requirements:

~~~text
Find orders whose notes contain "express delivery"
Find products with names similar to "headphones"
Search across multiple fields and rank by relevance
~~~

An equality-index Redis Set cannot natively perform substring matching, approximate matching, or full-text search. These problems typically require specialized text-indexing mechanisms, such as Redis Query Engine when supported by the deployment, or another search engine.

Also distinguish **Spring Data Redis** from other libraries built on Redis Query Engine, such as Redis OM Spring. Both use Redis and Repository syntax, yet **the supported operator sets are not automatically identical**.

## 10. Geospatial Queries: Dedicated Support but No Arbitrary Combinations

Spring Data Redis supports the `@GeoIndexed` index type for appropriate coordinate properties.

Illustrating an entity with a location:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.GeoIndexed;

@RedisHash("stores")
public class Store {

    @Id
    private String id;

    @GeoIndexed
    private Point location;

    public Store() {
    }

    public Store(String id, Point location) {
        this.id = id;
        this.location = location;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Point getLocation() {
        return location;
    }

    public void setLocation(Point location) {
        this.location = location;
    }
}
~~~

Repository searching by location:

~~~java
import java.util.List;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.repository.CrudRepository;

public interface StoreRepository
        extends CrudRepository<Store, String> {

    List<Store> findByLocationNear(
            Point point,
            Distance distance
    );

    List<Store> findByLocationWithin(Circle area);
}
~~~

Key point from Spring Data Redis documentation: **you cannot arbitrarily combine `Near` and `Within` with other criteria** in these Repository queries.

For example, do not assume a signature like:

~~~java
// Do not treat this as a query natively supported by Redis Repositories.
List<Store> findByLocationNearAndStatus(
        Point location,
        Distance distance,
        String status
);
~~~

will translate into "nearby location **and** matching status". If requirements need both geo filtering and status filtering, you may need custom index/query structures, or a query engine supporting combined criteria.

**Principle:** a system supporting individual conditions independently does not mean it automatically supports every combination of those conditions.

## 11. Conditions on Nested Properties and Reference Limitations

An entity can contain nested properties:

~~~java
public class ShippingAddress {

    @Indexed
    private String city;

    // Constructor, getter, setter...
}
~~~

When `Order` has a `shippingAddress` field and Spring Data Redis maps the nested object, the index can correspond to a path like:

~~~text
orders:shippingAddress.city:HaNoi
~~~

Then a query method of the form:

~~~java
List<Order> findByShippingAddressCity(String city);
~~~

must be understood via property paths and entity mapping rules. When property names could be ambiguous, Spring Data supports underscores in method names to guide path splitting, though the final syntax must still align with the data model.

Important condition: **indexing nested properties is supported in appropriate cases, but indexes cannot automatically resolve across all kinds of object references**. According to Spring Data Redis documentation on secondary indexes, indexes are not resolved across `references`.

Consequently, a model storing relationships as references does not mean you can query across multiple entities like an SQL `JOIN`.

## 12. Index Consistency in Combined Queries

Redis Repositories maintain secondary indexes when saving, deleting, and managing object lifecycles through their own mechanism. If an application alters data while **bypassing the Repository**, indexes can become stale.

For example, a direct Redis command changes the `status` field:

~~~redis
HSET orders:o-101 status CANCELLED
~~~

while the status index still contains `o-101` in:

~~~text
orders:status:PAID
~~~

then the query:

~~~java
repository.findByStatusAndChannel("PAID", "WEB");
~~~

may find an ID that no longer reflects the real data. Reading the final Hash may show `status = CANCELLED`; the result is confusing because the index and entity are no longer consistent.

This reminds us that secondary indexes in Redis Repositories are **maintained data**, not a formula automatically recomputed on every query.

Specifically, watch out for:

1. **Changing an indexed property:** update via a write path that manages indexes.
2. **Deleting keys with direct commands:** consider leftover index entries.
3. **TTL and expiration events:** distinguish the primary Hash lifecycle from secondary indexes; expiration notification settings can affect cleanup.
4. **Multiple concurrent writers:** avoid assuming the entire update sequence across the Hash and all index Sets is an atomic multi-key transaction.
5. **Changing index configuration after data exists:** adding `@Indexed` to a property does not guarantee existing records have had indexes rebuilt. An index rebuild process may be required.
6. **Data serialized as JSON:** saving the same content via `RedisTemplate.opsForValue()` does not make objects appear in Repository indexes.

## 13. When Should You Avoid Full Key Scans or Manual Filtering?

An initial implementation might be:

~~~java
// Unsuitable for frequent queries on large Redis instances:
Set<String> keys = redisTemplate.keys("orders:*");
~~~

Then the application reads every key, filters `status`, `channel`, and `createdAt`, and sorts manually.

This approach has several problems:

- `KEYS` scans the entire keyspace and can block other requests.
- The pattern `orders:*` can also match **secondary index keys**, not just entity Hashes.
- Loading and decoding large batches of objects consumes network bandwidth, CPU, and application memory.
- Mutating data means the inventory is not a consistent snapshot.
- Repeated high-load queries can turn Redis into a bottleneck.

`SCAN` is more appropriate than `KEYS` for **administrative traversal** split across iterations, yet it is still a scan rather than a business query index. Replacing `KEYS` with `SCAN` does not turn "fetch all keys and filter in Java" into an efficient search solution.

If a condition appears frequently in APIs, consider designing an index specifically for that condition.

## 14. Choosing a Solution by Query Complexity

### 14.1. Case A — Multiple Simple Equality Conditions

Requirement:

~~~text
status = PAID AND channel = WEB
~~~

Appropriate approach: index `status` and `channel`, and use:

~~~java
List<Order> findByStatusAndChannel(String status, String channel);
~~~

Mandatory conditions: each property is backed by an index, indexes are kept consistent, and result counts stay within processing capacity.

### 14.2. Case B — Multiple Well-Structured AND/OR Condition Groups

Requirement:

~~~text
(status = PAID AND channel = WEB)
OR
(status = PENDING AND channel = MOBILE)
~~~

Options to consider:

- Run two simple queries, merge and deduplicate IDs if the set is small.
- Combine Sets in Redis when appropriate indexes exist and result retrieval cost is understood.
- Maintain a combined index for common queries—for instance, status–channel—if the update cost is acceptable.

Do not write ever-longer method names without verifying the exact logical expression that will actually execute.

### 14.3. Case C — Numeric/Time Ranges, Ordering, and Large Pagination

Requirement:

~~~text
status = PAID
AND createdAt >= start
ORDER BY createdAt DESC
LIMIT 20
~~~

Consider a time-ordered Sorted Set or a dedicated query structure. Standard equality indexes are insufficient for optimally finding **ranges** or retrieving **the 20 newest items** out of millions of records.

### 14.4. Case D — Text or Geo Search Combined with Multiple Filters

If queries combine hard-to-compose operator types such as full-text, numeric ranges, geo, and multiple filters, evaluate Redis Query Engine with an appropriate client/library, or a more suitable search system.

This is a decision about query capabilities and data modeling, not simply renaming a `findBy...` method to another name.

## 15. Practice Exercise: Build a Capability Matrix Before Writing APIs

Using the five orders from Section 2, determine the results and query tool:

| Requirement | Expression | Approach |
|---|---|---|
| PAID orders via WEB | `status = PAID AND channel = WEB` | `findByStatusAndChannel` |
| PAID orders or via MOBILE | `status = PAID OR channel = MOBILE` | `findByStatusOrChannel` |
| Active orders | `active = true` | `findByActiveIsTrue` |
| Orders over 500,000 | `totalAmount > 500000` | Cannot be derived from equality indexes; consider ZSET or another search solution |
| Newest PAID orders | `status = PAID ORDER BY createdAt DESC` | Sort methods can be used, but check cost; for large sets consider a time index |

**ID Answers, based on the sample data table:**

1. `PAID AND WEB` → `o-101` and `o-105`.
2. `PAID OR MOBILE` → `o-101`, `o-102`, and `o-105`.
3. `active = true` → `o-101`, `o-102`, and `o-103`.
4. `totalAmount > 500000` → `o-101` and `o-104`. This is the **logical result on the example data**, not an indication that Redis Repositories natively support `GreaterThan`.
5. `PAID` is filtered by index; picking the newest order requires the `createdAt` property and a sorting mechanism. The sample table did not list timestamps, so which ID is newest cannot be determined.

### Extended Exercise

Suppose the application needs:

~~~text
(status = PAID OR status = PENDING)
AND channel = WEB
AND createdAt >= 2026-01-01
ORDER BY createdAt DESC
LIMIT 20
~~~

Answer before writing code:

1. Which fields currently have equality indexes?
2. Which parts of the query can be expressed via Redis Set intersections/unions?
3. Which conditions require a range index or another search mechanism?
4. If results contain 500,000 IDs, is loading and sorting in Java viable?
5. Who is responsible for updating indexes when an order changes status or timestamp?
6. Must results be consistent at a single point in time, or are changes between requests acceptable?
7. Does the deployment need to support Redis Cluster or data distributed across nodes?

Answering these questions helps choose the right API and data design from the start.

## 16. Key Takeaways

- In Spring Data Redis Repositories, `@Indexed` typically creates Redis Sets containing entity IDs for **equality queries**.
- `And` and `Or` in derived queries can correspond to **intersection `SINTER`** and **union `SUNION`** of index sets.
- **Spring Data Commons' keyword table is general-purpose**; do not assume Redis Repositories support every operator like `GreaterThan`, `Between`, `Like`, or `In`.
- `Top`, `First`, sorting, and pagination must be evaluated alongside entity-loading costs; sorting may occur on the application side.
- Geospatial indexes `@GeoIndexed` support standalone `Near`/`Within` queries; they do not freely combine with arbitrary other conditions.
- When criteria exceed Repository capabilities, Set operations, ZSETs, custom indexes, or suitable search engines can be used; each option carries consistency maintenance costs.
- Answering **"What conditions does Redis support, using which structure, and at what cost?"** matters far more than trying to write a long method name.

### References

- [Spring Data Redis 3.5 — Redis-specific Query Methods](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/queries.html).
- [Spring Data Redis 3.5 — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/3.5/redis/redis-repositories/indexes.html).
- [Spring Data Redis — Repository Query Keywords](https://docs.spring.io/spring-data/redis/reference/repositories/query-keywords-reference.html).
- [Spring Data Redis — Defining Query Methods](https://docs.spring.io/spring-data/redis/reference/repositories/query-methods-details.html).
- [Redis — SINTER](https://redis.io/docs/latest/commands/sinter/) and [SUNION](https://redis.io/docs/latest/commands/sunion/).
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/).
