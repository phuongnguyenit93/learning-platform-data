# Pagination, Sorting, and Practical Limits of Redis Repositories

## 1. The Problem: Why Is Pagination Still Hard Even with a Repository?

In Spring Data, developers are accustomed to APIs like `findAll(Pageable)`, `findAll(Sort)`, or derived methods such as `findByCategory(..., Pageable)`. With relational databases, these APIs usually translate into queries using `ORDER BY`, `LIMIT`, and `OFFSET`. However, **Spring Data Redis Repository** operates over key-value structures and Redis indexes, not a SQL query engine.

Therefore, when designing product listings, articles, sessions, or leaderboards, three requirements should be separated:

1. **Filtering**: finding keys matching a condition, such as `category = "book"`.
2. **Sorting**: establishing an order, such as `createdAt DESC, id ASC`.
3. **Pagination**: fetching a slice of that ordering, such as the next 20 items, and potentially a total count.

Redis Repositories support saving, reading, and certain queries backed by secondary indexes (`@Indexed`). However, **do not assume a `Pageable` or `Sort` signature guarantees efficient server-side sorting and pagination inside Redis**. Support, return types, and exact execution behavior depend on the Spring Data Redis version and query type.

A listing that works fine on a small dataset can become slow on a large dataset if the application must load all entities, sort them, and slice the page itself.

> Core idea throughout this lesson: **Redis Repository manages entities; an appropriate Redis data structure manages ordering and pagination positions when the system has specific performance requirements.** Both parts can work together.

## 2. How Does a Redis Repository Store and Find Entities?

Consider a product entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("product")
public class Product {

    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
    private long createdAtEpochMillis;
    private long priceInCents;

    public Product() { }

    public Product(String id, String category, String name,
                   long createdAtEpochMillis, long priceInCents) {
        this.id = id;
        this.category = category;
        this.name = name;
        this.createdAtEpochMillis = createdAtEpochMillis;
        this.priceInCents = priceInCents;
    }

    public String getId() { return id; }
    public String getCategory() { return category; }
    public String getName() { return name; }
    public long getCreatedAtEpochMillis() { return createdAtEpochMillis; }
    public long getPriceInCents() { return priceInCents; }

    public void setId(String id) { this.id = id; }
    public void setCategory(String category) { this.category = category; }
    public void setName(String name) { this.name = name; }
    public void setCreatedAtEpochMillis(long createdAtEpochMillis) {
        this.createdAtEpochMillis = createdAtEpochMillis;
    }
    public void setPriceInCents(long priceInCents) {
        this.priceInCents = priceInCents;
    }
}
```

A simple Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, String> {

    List<Product> findByCategory(String category);
}
```

Spring Data Redis stores entity data under keys and manages Repository-supporting structures. `@Indexed` declares a secondary index for querying by `category`. Conceptually:

```text
Product(id=p101, category=book, createdAt=..., price=...)
       |
       +--> entity data by ID
       |
       +--> ID set for category=book (secondary index)
```

A set of IDs tells you **which items satisfy the condition**, but does not tell you **which item is newest**, **cheapest**, or **ranked 21st**. If you only fetch a list from a set-based index, do not rely on the returned order as a business sorting rule.

### Redis Repository Is Not a General-Purpose Query Engine

Key characteristics to remember:

- `@Indexed` helps certain derived queries locate matching IDs, but does not automatically build multi-field sorting indexes.
- Redis has no SQL-equivalent `JOIN`, `GROUP BY`, or `ORDER BY` over Repository entity sets.
- A query combining multiple conditions may not be supported by Redis Repositories, even if similar syntax exists in another Spring Data module.
- `findAll()` may examine a large number of entities; using it as a data source for filtering/sorting is generally unsuitable for large lists.
- Implementing `PagingAndSortingRepository` does not imply every method style is supported at the module level or has good performance. Check the specific API version and backend execution behavior.

## 3. What Do `Page`, `Slice`, `Pageable`, and `Sort` Mean?

Spring Data's abstractions describe pagination **requests** and **results**; they do not automatically create a sorted index in Redis.

| Concept | Function | Practical question with Redis |
| --- | --- | --- |
| `Pageable` | Page number, page size, and `Sort` | Does the backend apply it fully, or must the application do it? |
| `Sort` | Property and ascending/descending direction | Is there a Redis structure maintaining order by that property? |
| `Page<T>` | Page content plus total element/page counts | Where is the total computed; does it require scanning data? |
| `Slice<T>` | Page content plus a flag for whether a next page exists | Can you fetch `size + 1` items to detect the next page? |
| Cursor/keyset | Fetch items appearing after a known marker | Is the marker unique, stable, and retrievable? |

Example of representing a standard request:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable requested = PageRequest.of(
    2, // third page, zero-based
    20,
    Sort.by(
        Sort.Order.desc("createdAtEpochMillis"),
        Sort.Order.asc("id")
    )
);
```

This snippet only constructs a `Pageable` object. It **does not prove** that a Redis Repository method can execute a server-side query sorted by `createdAtEpochMillis DESC, id ASC`.

### Notes When Choosing Repository Interfaces

In newer Spring Data generations, `PagingAndSortingRepository` and `CrudRepository` are separate interfaces. When the module supports the corresponding operations and both sets of methods are needed, you may need to extend both:

```java
// Illustrates Spring Data Commons API structure.
// Do not assume Redis supports every method with the same semantics/performance.
interface ExampleRepository extends
        org.springframework.data.repository.CrudRepository<Product, String>,
        org.springframework.data.repository.PagingAndSortingRepository<Product, String> {
}
```

Before building business APIs that depend on `findAll(Pageable)`, `findAll(Sort)`, or a query method returning `Page`, verify the **documentation and behavior of the exact Spring Data Redis version in use**. If a feature is unsupported or causes the application to materialize large datasets, switch to building explicit indexes as shown in the following sections.

## 4. Simple Approach: Load the List, Sort in Java, Then Slice the Page

For very small configuration sets or strictly bounded datasets, the simplest approach is loading all relevant entities:

```java
import java.util.Comparator;
import java.util.List;
import java.util.stream.StreamSupport;

public List<Product> smallCatalogPage(
        ProductRepository repository, int page, int size) {

    if (page < 0 || size <= 0) {
        throw new IllegalArgumentException("Invalid page or size");
    }

    long skip = Math.multiplyExact((long) page, (long) size);

    return StreamSupport
        .stream(repository.findAll().spliterator(), false)
        .sorted(
            Comparator.comparingLong(
                Product::getCreatedAtEpochMillis
            ).reversed().thenComparing(Product::getId)
        )
        .skip(skip)
        .limit(size)
        .toList();
}
```

The result has a deterministic order because the comparator specifies `id` as a tie-breaker when two products share the same creation timestamp.

However, suppose the system has 500,000 products and needs only the first 20:

- Redis and the application may still have to read **a huge number of** entities before selecting 20 items.
- Sorting in Java processes a large list, consuming memory and CPU proportional to dataset size.
- Every request repeats this work; concurrent requests quickly put pressure on Redis, the network, and the JVM.
- Ordering or total count can change between requests as data is added, deleted, or modified.

Thus, this approach fits when **the element count is strictly bounded and known to be small**, not as a default for unbounded growing lists.

## 5. Using a Redis Sorted Set to Maintain Order

A Redis Sorted Set (`ZSET`) stores **member + score** pairs, keeping members ordered by score. Commands to fetch elements by rank or score range solve the exact problem of "which ID comes before which ID?".

For example, creating a product ordering index:

```redis
ZADD product:order 101 p101 102 p102 103 p103 104 p104
ZCARD product:order
ZREVRANGE product:order 0 1 WITHSCORES
```

The output of `ZREVRANGE ... 0 1` returns the two highest-scoring members: `p104` and `p103`. These can represent the two newest products if scores are generated in insertion order.

Data layout:

```text
Redis Repository                  Redis Sorted Set
+------------------------+       +--------------------------+
| product:p101 -> fields  |       | product:order            |
| product:p102 -> fields  |       | (p104, 104)              |
| product:p103 -> fields  | <--+  | (p103, 103)              |
| product:p104 -> fields  |    |  | (p102, 102)              |
+------------------------+    |  | (p101, 101)              |
                              |  +--------------------------+
                         read IDs in order,
                         then load matching entities
```

Separating two responsibilities:

1. **Repository** manages products by ID.
2. **ZSET** determines ordering and supplies the IDs for the requested page.

This avoids loading all entities just to find the top 20 IDs.

### Choosing a Score for the ZSET

There are several choices:

| Score | Meaning | Points to note |
| --- | --- | --- |
| Unix timestamp (milliseconds) | Sort by creation/update time | Multiple entities may share the same timestamp |
| Product price | Sort by price | When price changes, the score must be updated |
| Views/ranking score | Top-N by popularity | Needs update and refresh policies |
| Monotonically increasing sequence | Unique insertion order | Requires consistent sequence generation; does not represent wall-clock time |

When two members share the same score, Redis breaks ties lexicographically by member. This rule is predictable, though not necessarily equivalent to `createdAt DESC, id ASC` required by the application.

**Numeric precision note:** ZSET scores are 64-bit floating-point numbers. Integers are represented exactly up to roughly `2^53`; if using long-lived sequences, keep this limit in mind. Do not combine large timestamps and IDs using ad-hoc multiplication and assume every value remains exact.

## 6. Position-Based Pagination (Offset/Rank Pagination) with ZSET

With zero-based page index `page` and page size `size`:

```text
start = page * size
stop  = start + size - 1
```

Example paginating 3 products per page:

```redis
ZREVRANGE product:order 0 2
ZREVRANGE product:order 3 5
ZREVRANGE product:order 6 8
```

With newer Redis versions, you can use the unified `ZRANGE ... REV` syntax:

```redis
ZRANGE product:order 0 2 REV
```

Note the distinction: `ZREVRANGE` returns a list of **IDs**, not full `Product` objects. The application must load those entities through the Repository and reassemble them in the exact ID order returned by the ZSET.

### Example Service Combining Repository and ZSET

The following example uses Spring Data Redis with `StringRedisTemplate`, `CrudRepository`, and Java 17. For simplicity, assume the application assigns unique IDs and the list is ordered by an insertion-time sequence number.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private static final String ORDER_KEY = "product:order";
    private static final String SEQ_KEY = "product:order:seq";
    private static final long MAX_EXACT_SCORE = 9_007_199_254_740_991L;

    private final ProductRepository products;
    private final StringRedisTemplate redis;

    public ProductCatalogService(
            ProductRepository products,
            StringRedisTemplate redis) {
        this.products = products;
        this.redis = redis;
    }

    public void add(Product product) {
        // Demo: each ID is inserted once.
        Long seq = redis.opsForValue().increment(SEQ_KEY);

        if (seq == null || seq < 1 || seq > MAX_EXACT_SCORE) {
            throw new IllegalStateException("Invalid sequence number");
        }

        products.save(product);

        // ZSET only stores ID and ordering; entities remain managed by Repository.
        redis.opsForZSet().add(
            ORDER_KEY,
            product.getId(),
            seq.doubleValue()
        );
    }

    public ProductPage readPage(int page, int size) {
        if (page < 0 || size <= 0 || size > 100) {
            throw new IllegalArgumentException("Invalid page or size");
        }

        long start = Math.multiplyExact((long) page, (long) size);
        long stop = Math.addExact(start, size - 1L);

        Set<String> ids = redis.opsForZSet()
            .reverseRange(ORDER_KEY, start, stop);

        Long zcard = redis.opsForZSet().zCard(ORDER_KEY);
        long total = zcard == null ? 0 : zcard;

        if (ids == null || ids.isEmpty()) {
            return new ProductPage(List.of(), total, page, size);
        }

        // findAllById must not be assumed to preserve input order.
        Map<String, Product> byId = new HashMap<>();
        products.findAllById(ids).forEach(
            product -> byId.put(product.getId(), product)
        );

        List<Product> ordered = new ArrayList<>();

        for (String id : ids) {
            Product product = byId.get(id);

            if (product != null) {
                ordered.add(product);
            }
        }

        return new ProductPage(
            List.copyOf(ordered),
            total,
            page,
            size
        );
    }

    public record ProductPage(
        List<Product> items,
        long totalIndexed,
        int page,
        int size
    ) { }
}
```

**Intentional limitation of the example:** `add()` executes sequential Redis/Repository commands without synchronous transactions or reconciliation cleanup. Later sections explain how to handle this for production. `totalIndexed` is the ZSET size, not necessarily the exact count of currently existing entities if the index contains stale IDs.

When calling `readPage(0, 20)`, the system selects at most 20 IDs from the Sorted Set and hydrates the corresponding entities. Processing cost is typically much lower than loading all data and calling `sort()` in Java.

### Cost of Rank-Based Pagination

With a ZSET, retrieving a range by rank typically costs around `O(log N + M)`, where `M` is the number of returned members. Then add the cost of loading `M` entities and converting them into Java objects.

Do not assume all types of offsets have the same cost: rank-based slicing differs from score-range queries using `LIMIT offset count`, where a large offset may have to skip more elements. Even when rank lookup is efficient, users paging through many pages still face shifting positions when underlying data changes.

## 7. Why Can Offset Pagination Duplicate or Skip Items?

Suppose the list is sorted in descending score order:

```text
Before insertion:
Page 1: [p105, p104, p103]
Page 2: [p102, p101, p100]

After client fetches Page 1, a new item p106 arrives:
List:   [p106, p105, p104, p103, p102, p101, p100]

Client fetches Page 2 using offset=3:
Page 2: [p103, p102, p101]
             ^
             p103 duplicated from Page 1
```

This is not a Redis-specific bug. Offset pagination is always affected when data changes between requests. If an item near the top of the list is deleted, the client can also skip an item.

When an API serves heavy traffic and continuously receives new items, **cursor/keyset pagination** is usually more suitable than numbered pages.

## 8. Score-Based Cursor Pagination

A simple approach is using a **unique, monotonically increasing** sequence number as the score:

```text
product:order
  p106 -> 106
  p105 -> 105
  p104 -> 104
  p103 -> 103
  p102 -> 102
```

First page: take up to three products with the highest scores.

```redis
ZRANGE product:order +inf -inf BYSCORE REV LIMIT 0 3 WITHSCORES
```

Suppose it returns `p106 (106)`, `p105 (105)`, `p104 (104)`. The next cursor is score `104`. The next page requests **scores strictly less than 104**, excluding the boundary:

```redis
ZRANGE product:order (104 -inf BYSCORE REV LIMIT 0 3 WITHSCORES
```

Redis uses `(` before a score value to indicate an open interval, meaning **exclusive of** `104`. Even if a new `p107` is inserted at the top, the next page still starts below `104` and does not repeat products already seen on the first page.

The API flow can look like:

```text
GET /products?size=3
  -> items: [p106, p105, p104]
  -> nextCursor: "104"

GET /products?size=3&before=104
  -> items: [p103, p102, p101]
  -> nextCursor: "101"
```

### Rules for Cursors to Work Correctly

- **Order must be stable and well-defined.** With unique scores, a single score value suffices to seek before/after. With duplicate scores, the cursor must also carry the member and tie-breaking logic.
- **Do not assume scores are always immutable.** When prices, ratings, views, or rankings change, an item can move between two requests; cursors do not create snapshots automatically.
- **Do not use a timestamp score as the sole cursor if multiple items share the same timestamp.** An exclusive interval on timestamp alone will skip other items with the same score.
- **Monotonic sequences fit "newly added" order**, but do not replace sorting by `updatedAt`, `price`, or multiple fields.
- **Cursors must be bound to the filter and sort mode.** A cursor from `category=book` must not be reused arbitrarily for `category=toy`.
- You can fetch `size + 1` items to determine `hasNext`, then return only `size` items and the corresponding cursor.

With large or fast-changing Redis datasets, cursors over an ordered index avoid many offset pitfalls, though deletions, updates, and synchronization still require clear policies.

## 9. Preserving Order After Loading Entities

A subtle bug is fetching IDs from the ZSET in the right order, then returning the entity list from the Repository directly:

```text
ZSET returned:         [p104, p103, p102]
findAllById returned:  [p102, p104, p103]  (order is not guaranteed)
API wrongly returns:   [p102, p104, p103]
```

Properly:

1. Fetch the sequence of IDs in the desired order.
2. Read the data for those IDs.
3. Build an `id -> entity` map.
4. Iterate back over the ID sequence, pick the matching entity, and skip missing entities.

That is why the service example builds a `Map` and then constructs `List<Product> ordered` following the ZSET ID list.

Additionally, when an ID is in the ZSET but the underlying entity was deleted or expired by TTL, the actual item count returned may be smaller than `size`. The system can **backfill-read** subsequent IDs and discard invalid IDs; bound the number of refill loops so requests do not stall if the index is heavily stale.

## 10. Filtering Combined with Sorting

Redis Repository can search using `@Indexed`, yet a requirement like "books, newest first" combines **membership** with **ordering**.

There are three common designs.

### 10.1. A Dedicated ZSET per Important Query Group

If the API primarily serves:

```text
GET /products?category=book&sort=createdAt_desc
GET /products?category=toy&sort=createdAt_desc
```

You can maintain:

```text
product:order:all
product:order:category:book
product:order:category:toy
```

Illustrative commands:

```redis
ZADD product:order:category:book 101 p101 104 p104
ZADD product:order:category:toy 102 p102 103 p103

ZREVRANGE product:order:category:book 0 19
```

**Pros:** relatively fast retrieval for predefined groups and orderings.

**Trade-off:** every insert, category change, score change, or deletion must update every relevant index. The number of structures grows with the supported filter/sort combinations.

### 10.2. Fetch IDs from an Index Set, Then Sort in the Application

If the candidate set is small and strictly bounded, you can:

1. Use a Repository method like `findByCategory("book")`.
2. Sort items in the application.
3. Slice one page.

This is simple, but reintroduces loading the entire candidate set. It fits small groups and is unsuitable when a category has hundreds of thousands of results.

### 10.3. Dedicated Query Engine

If the API requires arbitrary combinations:

- `category IN (...)`;
- price ranges, inventory status, tags, and multiple predicates;
- sorting by `price ASC` or `createdAt DESC`;
- full-text search;
- deep pagination, total aggregations, and many dynamic sort options;

then manually maintaining dozens of ZSETs drives up update cost and inconsistency risk. Consider **Redis Search** if supported by your infrastructure, or an appropriate query database such as PostgreSQL/OpenSearch depending on requirements. Standard Redis Repositories do not automatically translate arbitrary query methods into Redis Search.

## 11. Multi-Field Sorting, Nulls, and Changing Scores

In SQL, you can request:

```sql
ORDER BY created_at DESC, id ASC
```

In a ZSET, **each member has one score**. Sorting arbitrarily by two or more attributes is not as natural as an `ORDER BY` clause. Choose one of these strategies:

- If the second field is solely a tie-breaker, define a safe, deterministic encoding or apply explicit tie-breaking at query time.
- If the dataset is small, fetch the candidate set and sort in the application.
- If there are only a few fixed sorts, maintain multiple indexes (e.g., one ZSET for price, one for time).
- If many dynamic filters/sorts are needed, offload querying to an engine built for them.

Do not add/multiply scores to cram multiple fields into one `double` without analyzing value ranges, precision loss, and tie-breaking rules. A lossy encoding can invert the order of seemingly distinct items.

### Sorting by Mutable Fields

Example `priceInCents`:

```redis
ZADD product:price:asc 1999 p101
ZADD product:price:asc 2999 p102
ZRANGE product:price:asc 0 19
```

After changing the price of `p101` to 3,999 cents, you must update:

```redis
ZADD product:price:asc 3999 p101
```

`ZADD` updates the score of an existing member; forgetting to update it leaves the ZSET ordering out of sync with the entity's new data. Updating the entity and updating the ZSET are two operations that can fail independently.

## 12. `Page` and the Problem of Accurate Total Counts

Many UIs request:

```json
{
  "items": ["p104", "p103"],
  "page": 0,
  "size": 2,
  "totalElements": 42000,
  "totalPages": 21000
}
```

With a full ZSET, `ZCARD` returns the number of members in the index:

```redis
ZCARD product:order
```

However, `ZCARD` counts **members** without checking whether each ID still corresponds to an existing entity. If the index holds stale IDs, this number is not the exact count of valid entities. When data is written concurrently, a count read first and a page read afterward may also reflect two slightly different points in time.

Design choices:

| UI requirement | Option |
| --- | --- |
| Must display "Page 1/100" | Requires reliable counts and consistent rules |
| "Load more" button or infinite scroll | Use `Slice`/cursor; only need to know if more items remain |
| Leaderboard | Score-ordered ZSET; usually cares about top N rather than total pages |
| Large, rapidly changing dataset | Prefer cursors and avoid exact counts on every request |

If you must return the total page count, you can compute it from the total:

```java
long totalPages = total == 0
    ? 0
    : 1 + (total - 1) / size;
```

Only present this as an exact total when the **count source has matching semantics and is consistently maintained**.

## 13. TTL, Deletion, and Stale Indexes

This is a critical limitation when combining Redis Repositories with custom ZSETs.

Suppose `Product p101` is saved with a 30-minute TTL:

```text
T0:   Repository saves p101; ZSET contains p101
T+30: entity p101 expires
T+31: ZSET may still contain member p101
```

Redis **does not automatically know** that a member in an external ZSET should be removed when an entity key expires. Although Repositories have expiration tracking and secondary index mechanisms, **application-managed ZSETs require their own maintenance strategy**.

Commonly combined strategies:

1. On business deletion of a product, call `ZREM` on related indexes.
2. When updating a field that determines grouping/sorting, remove from the old index and add to the new index.
3. During entity hydration, when detecting an ID that no longer exists, omit it from results and optionally schedule index cleanup.
4. Run a **periodic reconciliation** job to fix missing/extra members if accurate counts and ordering are required.
5. You may use Redis keyspace notifications as an early cleanup signal, but they rely on Pub/Sub and can be delayed or missed if the app disconnects; do not make them the sole recovery mechanism.

### Illustrating Deletion

```java
public void delete(String productId) {
    products.deleteById(productId);
    redis.opsForZSet().remove("product:order", productId);
}
```

This pattern is easy to follow but not atomic: the process could crash between the two operations. If strong consistency is needed, design unified writes, retry/idempotency, and reconciliation proportional to actual risk.

### "Refill Reading" When Encountering Non-Existent IDs

Suppose page size = 3 and the ZSET returns `[p103, p102, p101]`, where `p102` has expired via TTL. Simply dropping `p102` leaves the client with two items. If the contract requires three items whenever enough data remains, fetch additional IDs from subsequent positions and check them. Prevent infinite loops by capping scanned IDs/refill iterations, and schedule background index cleanup.

## 14. Consistency, Concurrency, and Transactions

A write operation may include:

```text
Repository.save(product)
         |
         +--> HSET entity
         +--> update Repository-managed indexes
         |
         +--> ZADD custom order index
```

If the application crashes after saving the entity but before `ZADD`, the entity exists yet does not appear in paginated lists. Conversely, if the index is written first and saving the entity fails, the ZSET contains a dangling ID.

### Situations to Account For

- **Create:** how do you prevent a product ID from being assigned multiple scores when a request retries?
- **Update:** when changing categories, in what order do you remove from the old index and insert into the new index?
- **Delete:** is it acceptable for the index to hold stale entries briefly?
- **TTL:** when an entity disappears without an application callback running, how is the index cleaned up?
- **Concurrent writes:** when two threads update price or rank simultaneously, which update wins?
- **Replica reads:** when reading from a lagging replica, entities and indexes may reflect different points in time.

Mitigations depend on product strictness:

- **Best-effort display data:** idempotent writes, filter out stale IDs on read, periodic reconciliation.
- **High accuracy requirements:** group related updates within the same storage boundary/atomic operation when feasible; use transactions/Lua respecting Redis key design and cluster rules; maintain retry and reconciliation.
- **Business flows needing complex multi-entity transactions:** consider a dedicated transactional database, using Redis as a cache or read model.

Do not assume putting `@Transactional` on a method calling both a Repository and `StringRedisTemplate` automatically turns all related operations into an atomic Redis transaction. Actual behavior depends on the transaction manager, Spring Data Redis configuration, and commands invoked.

## 15. Redis Cluster and Actual Query Costs

In Redis Cluster, keys are distributed by hash slot. When an application requires multi-key operations (transactions, Lua, set intersections/unions, or specialized commands), same-slot constraints can affect index design.

For example:

```text
product:order                  -> one slot
product:p101                   -> another slot
product:p102                   -> yet another slot
```

Reading individual keys works through a cluster-aware client, but you cannot assume arbitrary multi-key operations execute atomically across different slots.

Hash tags (curly braces) can force related keys into the same slot:

```text
product:{category-book}:order
product:{category-book}:metadata
```

However, placing all application data under one hash tag concentrates load onto a single slot/node, forfeiting Cluster scaling benefits. Design hash tags only for operations that genuinely require co-location, rather than grouping all keys together.

### Complexity Goes Beyond the ZSET Command

A single page request can involve:

```text
Client -> API
          |
          +--> Redis: fetch IDs from ZSET
          +--> Redis: read N entity hashes
          +--> Java: assemble in the right order
          +--> Client: return JSON
```

Even if the ZSET query is fast, a request can still be slow due to excessive round trips, serialization, large entity payloads, or reads scattered across nodes. When optimizing, measure ID lookup, entity hydration, and conversion separately. Batching/pipelining can be applied in appropriate places once you understand the Repository path.

## 16. Designing a Clean Pagination API

A practical API should state **which pagination styles are supported**, rather than accepting arbitrary `page` and `sort` parameters and implicitly promising every combination.

### Offset When Jumping to Page Numbers Is Needed

```http
GET /api/products?page=0&size=20&sort=createdAt,desc
```

Example response:

```json
{
  "items": [
    {"id": "p104", "name": "Book A"},
    {"id": "p103", "name": "Book B"}
  ],
  "page": 0,
  "size": 20,
  "totalIndexed": 42000
}
```

`totalIndexed` should be named honestly when the count comes from a ZSET and may differ from live entity count.

### Cursor When Data Changes Frequently

```http
GET /api/products?size=20
GET /api/products?size=20&cursor=opaque-token
```

Response:

```json
{
  "items": [
    {"id": "p104", "name": "Book A"},
    {"id": "p103", "name": "Book B"}
  ],
  "nextCursor": "opaque-token",
  "hasNext": true
}
```

`opaque-token` can encode the last score, sort type, filter predicates, and schema version, formatted so clients do not depend on internal Redis structure. Upon decoding, the server must validate values, page size, and query scope. If the score contains sensitive data or tokens must resist tampering, add appropriate signing/authentication.

### Which Sorts Are Allowed?

Instead of accepting arbitrary field names, declare supported mappings explicitly:

```text
sort=created_desc   -> ZSET product:order
sort=price_asc      -> ZSET product:price:asc
sort=popular_desc   -> ZSET product:popularity
```

For unindexed sorts, the API can return a validation error or route the request to another search backend; never silently load all of Redis to sort on every request.

## 17. Choosing a Solution by Scale and Requirements

| Scenario | Starting approach | Limits to watch |
| --- | --- | --- |
| Very small, bounded dataset | Repository `findAll`/`findBy...` then sort in Java | Cost grows with the entire candidate set |
| Single top-N / newest list | ZSET + Repository for hydration | Must maintain scores and remove deleted IDs |
| List with a few fixed filters/sorts | Dedicated ZSET index per major filter/sort | Increases index count and write work |
| Continuously appended data, infinite scroll | Cursor/keyset on a stable ordering | Handle tied scores, updated/deleted items |
| Need arbitrary page jumps | Offset/rank on ZSET | May duplicate/skip items when data changes |
| Multi-condition filtering, many dynamic sorts | Redis Search or another query engine | Requires operating indexes and choosing the right engine |
| Transactional, complex relational data | Suitable transactional database | Use Redis as cache/read model when needed |

### Production Evaluation Criteria

**Dataset size.** Estimate total entities, IDs per index, and items per page. Do not rely solely on latency measured with a few hundred test records.

**Write churn.** With more writes than reads, maintaining many ZSETs can be costly. With read-heavy workloads and fixed sorts, ZSETs are often a sensible fit.

**Consistency.** Decide whether the UI tolerates approximate counts, temporary missing items, or requires immutable results across pages.

**Future queries.** If the product roadmap includes dynamic filtering, full-text search, or analytics, pick a suitable query engine before building too many custom indexes.

## 18. Common Mistakes

### Mistake 1: "Having `PageRequest` means Redis will LIMIT"

`PageRequest` only expresses a request. The storage module must support and implement it; if an API does not fit, the result can be an error or an expensive query. Do not extrapolate Redis capabilities from Spring Data JPA habits.

### Mistake 2: Relying on the Order of an ID Set

An index membership set is not a sorted list. To guarantee deterministic ordering, define an appropriate comparator or use an ordered structure such as a ZSET.

### Mistake 3: Fetching IDs from a ZSET but Losing Order in `findAllById`

Build a map by ID and reassemble items in the order returned by the ZSET. Otherwise, the API may return products out of order even though the ZSET was sorted.

### Mistake 4: Returning `ZCARD` as the Count of Live Products

If ZSET members are not cleaned up when entities expire via TTL or get deleted, `ZCARD` counts stale IDs too. Document count semantics clearly and maintain indexes.

### Mistake 5: Using Millisecond Timestamps as the Sole Cursor

Two products can share the same timestamp; querying the next page with an open interval will skip other items having the same score. Use full tie-breaking or a unique monotonic sequence.

### Mistake 6: Updating an Entity and Forgetting to Update the ZSET

Changing a field like `price` or `popularity` must update scores in the corresponding indexes. Centralize writes in a single service or clearly structured update pipeline.

### Mistake 7: Assuming Keyspace Notifications Keep Indexes Strictly Consistent

Redis expiration events can arrive late or be lost over Pub/Sub; cleaning indexes solely via callbacks will miss entries. Add reconciliation if exactness is essential.

## 19. Lab Exercise: Designing a Filterable, Sortable Product List

Suppose a system has 2 million products and needs to:

- View the 20 newest products with "Load more".
- Filter by a category.
- Display the top 100 most-viewed products.
- Remove expired products from lists.

Proposed design:

```text
                              +----------------------+
                              | Spring REST API      |
                              +----------+-----------+
                                         |
                  +----------------------+--------------------+
                  |                      |                    |
                  v                      v                    v
           product:order       product:category:X:order   product:views
           ZSET: ID/seq        ZSET: ID/seq              ZSET: ID/views
                  |                      |                    |
                  +----------------------+--------------------+
                                         |
                                         v
                                    ID list
                                         |
                                         v
                             ProductRepository.findAllById
                                         |
                                         v
                             assemble entities in ID order
                                         |
                                         v
                                    response
```

Operational rules:

1. Use a unique sequence generator for new products; apply score-based cursors for `created_desc`.
2. When adding a product, save the entity and update the global/category ZSETs.
3. When changing category, move the member between category ZSETs.
4. When incrementing views, update the score in `product:views` consistently.
5. When deletion or TTL removes an entity, the read path skips missing IDs; a reconciliation job fixes indexes.
6. Only expose indexed filter/sort options; broader query needs should route to another query engine.

A top-N leaderboard can be queried via:

```redis
ZREVRANGE product:views 0 99 WITHSCORES
```

A category listing can be queried via:

```redis
ZRANGE product:category:book:order +inf -inf BYSCORE REV LIMIT 0 20 WITHSCORES
```

These are representative Redis commands for **selecting ordered IDs**. For a complete API, the application must still hydrate entities, filter out missing IDs, handle cursors, enforce authorization, and update indexes as data changes.

## 20. Frequently Asked Questions

**Can `Pageable` be used directly in Redis Repositories?**

Check the Spring Data Redis version, Repository type, and query type in use. Do not assume Spring Data JPA behavior or server-side indexed execution in Redis. When efficient paging/sorting by a specific field is required, ZSETs or a dedicated query engine typically provide clearer control.

**Does `@Indexed` make `ORDER BY` faster?**

`@Indexed` mainly serves finding entities matching a condition. It does not automatically maintain orderings like `createdAt DESC` or `price ASC` on the result set.

**Why does `findByCategory(...)` return results in an unexpected order?**

Because index membership and business ordering are separate concerns. Define ordering explicitly instead of relying on arbitrary ID or container order.

**Should a ZSET store the entire `Product`?**

In practice, store the **ID** as the member and a score for sorting. The Repository remains the entity store; the application hydrates IDs into objects when needed. This avoids duplicating full payloads across indexes.

**Should a mobile app use `Page` or `Slice`?**

For infinite scroll and fast-changing data, cursors with `hasNext` metadata are usually a better fit; computing total counts on every fetch is unnecessary. `Page` is useful when the UI genuinely requires page numbers and accurate totals.

**What if a client requests page 10,000?**

Rank-based lookup on a ZSET still works, though data churn and total fetch/hydration costs remain. APIs should cap page sizes, consider capping maximum page depth, or switch to cursors for continuous browsing.

**Can you sort simultaneously by time and ID?**

You can design tie-breaking rules, though a ZSET holds only one score per member. On equal scores, Redis sorts lexicographically by member; verify whether that matches business rules or design a two-part cursor. Do not assume timestamps are unique.

**Are Redis Search and Redis Repository the same tool?**

No. Redis Repository is Spring Data Redis's entity/key-value mapping mechanism. Redis Search is a separate search/query capability on supported Redis deployments; using it requires designing appropriate indexes and clients/APIs.

## 21. Key Takeaways

- **Repositories return entities and support certain indexed queries**, but are not a general SQL engine with `ORDER BY`/`OFFSET`.
- **`Pageable` and `Sort` are abstractions**, not a guarantee that Redis has a matching execution plan.
- **ZSETs are a core structure** for maintaining ordered ID sets and fetching top-N items, rank-based pages, or score-based cursors.
- **Offset** is convenient for numbered pages but can duplicate/skip items when data changes; **cursor** works better for rapidly changing lists with stable ordering.
- **Indexes must be maintained on create/update/delete/expire**; do not confuse `ZCARD` with the live entity count.
- **Workloads with many dynamic filters/sorts** usually belong in an appropriate query engine rather than endlessly proliferating custom ZSETs.

## References

- [Spring Data Redis Reference – Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis Reference – Redis Repositories Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html)
- [Spring Data Redis Reference – Repository Query Methods](https://docs.spring.io/spring-data/redis/reference/repositories/query-methods-details.html)
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Redis – Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/)
- [Redis – ZRANGE](https://redis.io/docs/latest/commands/zrange/)
- [Redis – ZADD](https://redis.io/docs/latest/commands/zadd/)
