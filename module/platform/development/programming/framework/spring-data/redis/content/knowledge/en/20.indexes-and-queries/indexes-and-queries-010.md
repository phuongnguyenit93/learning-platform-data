# Limitations of Joins, Arbitrary Queries, and Full-Text Search

Spring Data Redis enables Java applications to interact with Redis through `RedisTemplate`, Redis data structures, and **Redis Repositories**. When using `@RedisHash`, a Java object can be stored as a Redis Hash; when annotating properties with `@Indexed`, the framework also manages secondary indexes supporting certain property-based queries.

However, **Redis Repositories are not a general-purpose relational query engine**. Declaring a repository and a few annotations does not automatically provide `JOIN`, `GROUP BY`, `LIKE '%keyword%'`, arbitrary multi-condition queries, or relevance-ranked full-text search like relational databases and dedicated search engines do.

This lesson raises three design questions:

1. When data spans multiple Redis Hashes, how does the application combine entities without SQL `JOIN`s?
2. With `@Indexed` and Repository queries, where is the boundary of conditions that can execute efficiently?
3. When keyword search, natural-language matching, or result ranking is required, should you use Redis Search/Query Engine or a separate search system?

## 1. Accurately Understanding Data Access Layers in Spring Data Redis

Redis is a data store supporting multiple structure types such as String, Hash, Set, Sorted Set, List, and Stream. Most basic operations are designed to access keys or manipulate a known data structure. Redis does not automatically turn every Hash into a SQL table capable of querying arbitrary columns.

Spring Data Redis provides different abstraction layers:

| Access Approach | Source of Strength | Key Limitation |
| --- | --- | --- |
| `RedisTemplate` / `StringRedisTemplate` | Direct operations on Redis commands and data types | Application must organize keys, relationships, and queries manually |
| `CrudRepository` for `@RedisHash` | Entity mapping; ID lookup; queries on indexed properties | No SQL `JOIN` or full arbitrary query language |
| Spring Data Redis `@Indexed` | Maintains Redis Sets mapping property values to entity IDs | Primarily for supported index lookups; not a full-text index |
| Redis Search / Redis Query Engine | Indexes and executes search queries on supported data types | Requires Redis with corresponding support, schema definition, and suitable API/commands |
| External search engine | Text queries, language analysis, ranking, and aggregations per product capabilities | Must synchronize data between primary write store and search system |

A crucial principle: **these approaches do not automatically substitute for one another**. For example, saving JSON via `opsForValue().set(...)` does not automatically create Redis Repository secondary indexes; adding `@Indexed` does not automatically create an `FT.SEARCH` index.

## 2. How Does SQL `JOIN` Differ from Relationships Across Redis Hashes?

In a relational database, two tables can link via a foreign key:

~~~sql
SELECT c.id, c.name, o.id AS order_id, o.total_amount
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE c.id = 'c-101';
~~~

The SQL engine knows how to build a query plan, leverage suitable indexes, and join rows from both tables.

With Redis Hashes, if we store:

~~~text
customers:c-101
  id = c-101
  name = Nguyễn Lan

orders:o-9001
  id = o-9001
  customerId = c-101
  totalCents = 125000

orders:o-9002
  id = o-9002
  customerId = c-101
  totalCents = 87000
~~~

Redis has no built-in command like `JOIN customers ON orders.customerId = customers.id`. The application must have a way to **discover the order IDs belonging to the customer** and then load the related entities.

Query flow diagram:

~~~text
            API: GET /customers/c-101/orders
                           |
                           v
                 CustomerOrderService
                    /           \
                   v             v
      CustomerRepository     OrderRepository
       findById("c-101")    findByCustomerId("c-101")
                   |             |
                   v             v
            Customer Hash     Secondary index
                                  |
                                  v
                              Order IDs
                                  |
                                  v
                             Order Hashes
                   \             /
                    v           v
                  Combine results in Java
                           |
                           v
                      Response DTO
~~~

This is an **application-side join**, meaning Java code combines the fetched results. It works well when relationships are explicit and related entity counts stay within manageable bounds, yet it lacks the semantics and join optimization tools SQL typically offers.

### `@Reference` Does Not Turn Redis into SQL

Spring Data Redis provides `@Reference` to represent a reference to a separately stored entity. It can resolve references during object mapping, but **does not provide general `JOIN` operations** and does not automatically index properties inside referenced entities.

For instance, suppose an order holds a `customer` reference. That does not mean the repository understands a query like:

~~~text
Find every Order where order.customer.address.city = "Hà Nội"
~~~

as a SQL JOIN traversing `Order → Customer → Address`. For such queries, the application must design suitable indexes, multi-step queries, copy certain properties into a read model, or use a query system matching the requirement.

## 3. Concrete Example: Querying Customers and Orders

To support finding orders by customer without scanning all Hashes, store `customerId` on `Order` and index that property.

**`Customer.java`**

~~~java
package com.example.redis.query;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {
    @Id
    private String id;

    @Indexed
    private String email;

    private String name;

    public Customer() {
    }

    public Customer(String id, String email, String name) {
        this.id = id;
        this.email = email;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getName() {
        return name;
    }
}
~~~

**`Order.java`**

~~~java
package com.example.redis.query;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orders")
public class Order {
    @Id
    private String id;

    @Indexed
    private String customerId;

    private String status;

    private long totalCents;

    public Order() {
    }

    public Order(String id, String customerId,
                 String status, long totalCents) {
        this.id = id;
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getStatus() {
        return status;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

**Repositories**:

~~~java
package com.example.redis.query;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByEmail(String email);
}

public interface OrderRepository
        extends CrudRepository<Order, String> {

    List<Order> findByCustomerId(String customerId);
}
~~~

In a real Java project, each `public interface` should live in its own correspondingly named file. They are shown side by side here to clarify the relationship between both repositories.

**Service combining both results**:

~~~java
package com.example.redis.query;

import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;

@Service
public class CustomerOrderQueryService {
    private final CustomerRepository customers;
    private final OrderRepository orders;

    public CustomerOrderQueryService(CustomerRepository customers,
                                     OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    public CustomerOrders loadCustomerOrders(String customerId) {
        Customer customer = customers.findById(customerId)
            .orElseThrow(() -> new NoSuchElementException(
                "Customer does not exist: " + customerId
            ));

        List<Order> customerOrders =
            orders.findByCustomerId(customerId);

        return new CustomerOrders(customer, customerOrders);
    }

    public record CustomerOrders(Customer customer, List<Order> orders) {
    }
}
~~~

Saving and querying sample data:

~~~java
customers.save(new Customer(
    "c-101", "lan@example.test", "Nguyễn Lan"
));

orders.save(new Order("o-9001", "c-101", "PAID", 125000));
orders.save(new Order("o-9002", "c-101", "NEW", 87000));

CustomerOrderQueryService.CustomerOrders result =
    service.loadCustomerOrders("c-101");

System.out.println(result.customer().getName()); // Nguyễn Lan
System.out.println(result.orders().size());      // 2
~~~

For `findByCustomerId` to work in Redis Repositories, `customerId` must be annotated with `@Indexed` and records must go through the index-creating write path. If the annotation is added after legacy data already exists, plan to rebuild indexes for existing records.

### What Are the Limitations of Application-Side Joins?

- **Multiple reads:** At least one lookup for the customer and one lookup for the order set, followed by reading multiple Hashes.
- **Result size:** If a customer has hundreds of thousands of orders, loading all of them into a `List<Order>` consumes excessive memory and time.
- **Consistency:** The customer could be modified or deleted between the two reads. Combined results do not automatically form a transactional snapshot.
- **Condition limits:** If you also need to filter orders by `status`, sort by `totalCents`, and paginate, a `customerId` index alone may not suffice.
- **Reusability:** Each data-combination pattern may require custom query code; Redis Repositories do not automatically optimize JOIN trees.

Therefore, only use this kind of join for well-understood relationships and bounded result sizes.

## 4. What Queries Repositories Can and Cannot Solve

`@Indexed` in Spring Data Redis builds secondary indexes using Redis Sets, typically mapping **property value → entity ID set**.

For example:

~~~text
customers:email:lan@example.test → { c-101 }
orders:customerId:c-101          → { o-9001, o-9002 }
~~~

For exact-match queries on an indexed property, the framework retrieves the matching ID set and loads the entities. Certain combinations supported by Redis Repositories can leverage operations over ID sets.

That **does not mean every Spring Data derived query keyword from other databases works in Redis**. Method name parsing and operator execution depend on the store module. You cannot take an arbitrary JPA method, swap the repository to Redis, and expect identical semantics.

| Query Need | Spring Data Redis Repository with Secondary Indexes | Recommendation |
| --- | --- | --- |
| Look up by ID | Well suited | Use `findById` |
| Look up by exact email | Well suited if email is indexed | `@Indexed` and supported derived query |
| Look up by a status property | Can be suitable | Evaluate result set volume |
| Combine certain conditions on indexed fields | Depends on operators supported by Redis Repositories | Test the specific query |
| JOIN multiple entity types | No automatic SQL `JOIN` | Join in application or design a read model |
| Query by property of a `@Reference` target entity | Does not automatically become a JOIN | Index on the queried entity or run multi-step queries |
| Find names containing arbitrary substring | No default full-text substring search | Search index / search engine |
| Typos, stemming, relevance ranking | Not a feature of `@Indexed` | Appropriate search engine |
| Flexible pagination/sorting on large data | Not equivalent to a SQL query planner | Design ordered indexes/read models around access patterns |
| Arbitrary grouping and aggregation | Not a general Redis Repository query feature | Pre-compute metrics or use an appropriate data store |

### Avoid Inferring Behavior from Method Return Types

Writing:

~~~java
List<Order> findByCustomerIdOrderByTotalCentsDesc(String customerId);
~~~

does not automatically create an efficient `totalCents` sort structure in Redis. Before relying on a derived method with multiple operators or sorting, verify that your version of Redis Repository genuinely supports that query. Otherwise, use another query structure, such as an application-managed Sorted Set.

Likewise, adding a `Pageable` parameter does not automatically guarantee Redis can fetch page `N` across arbitrary filters and sorts without scanning a large dataset.

## 5. Arbitrary Queries: Why Full Key Scans Are Usually a Bad Choice

A naive approach is:

1. Fetch all keys with prefix `orders:*`.
2. Read each Hash.
3. Use Java `stream().filter(...)` to filter conditions.
4. Sort and paginate in memory.

Mental model:

~~~java
// Anti-pattern pseudo-code; do not run on large datasets:
List<Order> results = loadAllOrdersFromRedis()
    .stream()
    .filter(o -> "PAID".equals(o.getStatus()))
    .filter(o -> o.getTotalCents() >= 100_000)
    .sorted((a, b) -> Long.compare(
        b.getTotalCents(), a.getTotalCents()))
    .toList();
~~~

The flaw is that work scales with the **total number of stored objects**, rather than the number of matching objects. On production Redis, this query pattern easily drives up network traffic, CPU, memory, and latency.

### Why Not Use `KEYS orders:*` to Solve It?

The `KEYS` command scans the entire keyspace and can block Redis for a long time when key counts are large. `SCAN` supports incremental cursor-based iteration, which fits controlled administrative/traversal tasks better, yet:

- `SCAN` **does not** turn scanning into a property-based query index.
- A full `SCAN` pass still has to traverse the keyspace to find everything.
- While data changes, duplicates or skipped keys between iterations must be accounted for.
- `SCAN` does not natively support `JOIN`, relevance scoring, or sorting across fields.

Use `SCAN` for intentional traversal, maintenance, or migration jobs; do not treat it as the default foundation for frequently called search endpoints.

## 6. Designing Purpose-Built Queries with Redis Sets and Sorted Sets

When frequent queries exceed repository capabilities yet follow predictable shapes, the application can proactively maintain a **read model** using Redis data types.

### 6.1. Sets for Relationships and Exact-Value Filters

Example storing the set of orders belonging to a customer:

~~~redis
SADD customer:orders:c-101 o-9001 o-9002
SMEMBERS customer:orders:c-101
~~~

Or storing order sets by status:

~~~redis
SADD orders:status:PAID o-9001 o-9008
SADD orders:customer:c-101 o-9001 o-9002
SINTER orders:status:PAID orders:customer:c-101
~~~

`SINTER` produces the IDs present in both Sets—for example, paid orders of customer `c-101`.

This is a **manual key convention**. The application must ensure memberships are updated whenever an order changes owner, changes status, or is deleted. It does not auto-sync with Redis Repository-managed indexes if both systems write independently.

### 6.2. Sorted Sets for Rankings or Score Queries

Suppose the UI needs to show a customer's newest orders. You can use a Sorted Set scored by timestamp:

~~~redis
ZADD customer:orders:recent:c-101 1732000000 o-9001
ZADD customer:orders:recent:c-101 1732010000 o-9002
ZREVRANGE customer:orders:recent:c-101 0 19
~~~

The result returns up to 20 IDs from highest score to lowest. Then the application loads order details by ID.

If you also need to filter `status=PAID`, design how results and ordering combine, or maintain a dedicated Sorted Set for the hot query pattern—for example, `customer:paid-orders:recent:c-101`. There is no guarantee that an arbitrary collection of Sets/Sorted Sets efficiently supports every SQL-like filter combination.

For stable pagination as new data streams in continuously, score-based cursors with a suitable tie-breaker can be more useful than offset pagination; the application still needs to handle elements sharing identical scores and updates occurring between pages.

### 6.3. Read Models and Synchronization Costs

Purpose-built query models optimize the read path while introducing update obligations:

~~~text
              Command: create/update order
                           |
                           v
                      Write Order
                           |
              +------------+------------+
              |                         |
              v                         v
       update status Set         update timestamp Sorted Set
              |                         |
              +------------+------------+
                           |
                           v
                Read model ready for endpoint
~~~

When a command updates multiple keys, define consistency guarantees. Redis transactions or Lua scripts can help perform atomic updates within supported command scope and topology, though sequential Java calls must not be assumed to form a single transaction. In Redis Cluster, multi-key commands and Lua are constrained by hash slots.

If choosing asynchronous updates via events, the read model can be **eventually consistent**: search results may lag behind primary data briefly. Depending on business requirements, design retries, idempotency, event ordering, and index rebuild mechanisms for failure recovery.

## 7. Denormalization: Trading Some Write Cost for Read Speed

To avoid loading `Customer` for every order listing, you can store a few display fields directly inside `OrderSummary`:

~~~java
public record OrderSummary(
    String orderId,
    String customerId,
    String customerNameSnapshot,
    String status,
    long totalCents
) {
}
~~~

When creating an order, the application reads `customerNameSnapshot` from customer data and writes it into the read model. Order-listing endpoints can read everything needed without repeated joins.

However, choose **data semantics** explicitly:

- If the customer name on an invoice must remain frozen at purchase time, `customerNameSnapshot` is intentional historical data.
- If the screen must always display the current name, copied data must be updated when the customer changes name, or fetched from the authoritative source.

Denormalization fits when query patterns are known upfront and read volume justifies update overhead. Continuously copying many mutable fields into every related entity sharply increases sync costs and drift risk.

## 8. How Does Full-Text Search Differ from `@Indexed`?

**Exact property lookup** and **full-text search** answer different kinds of questions.

For example, a product has:

~~~text
id          = p-501
title       = Spring Data Redis Guide
description = Building caches, repositories, and data search in Java
category    = programming
price       = 250000
~~~

| Requirement | Example Question | Appropriate Mechanism |
| --- | --- | --- |
| Exact match | Is category equal to `programming`? | Secondary index or TAG index |
| Multi-word match | Does title contain the words `Spring` and `Redis`? | Full-text index |
| Inflections/variants | `caching` vs `cache`? | Analyzer/stemming per search engine support |
| Typo tolerance | User misspells a couple of characters | Fuzzy query if search engine supports it |
| Ranking | Which article is most relevant to the query? | Scoring/ranking |
| Filter plus text search | Word `Redis` in title, category `programming`, price 100k–300k | Search query with `TEXT`, `TAG`, `NUMERIC` |

`@Indexed` in Redis Repositories does not build an inverted index over tokens inside `title` or `description`. It is a mechanism mapping property values to IDs, with its own design and limits.

**You cannot solve full-text search needs merely by adding `@Indexed` to a long `String`.** Matching an entire string by exact equality is fundamentally different from finding words inside text.

## 9. Redis Search / Redis Query Engine for Content Queries

When the running Redis distribution and version support **Redis Search / Redis Query Engine**, applications can create search indexes and run commands such as `FT.CREATE` and `FT.SEARCH`. This capability is available in Redis environments with the corresponding search component—such as Redis Stack or newer Redis releases integrating Query Engine; verify actual capabilities of your Redis server and provider.

### 9.1. Creating a Search Index over Hashes

Suppose the application writes Hashes with key prefix `product:`:

~~~redis
HSET product:p-501 title "Spring Data Redis in Practice" description "Cache and repository in Java" category "programming" price 250000
HSET product:p-502 title "Spring Security Basics" description "Application authentication and authorization" category "programming" price 180000
HSET product:p-503 title "Everyday Cooking" description "Family meals and recipes" category "cooking" price 120000
~~~

Create the search index:

~~~redis
FT.CREATE idx:products ON HASH PREFIX 1 "product:" SCHEMA title TEXT WEIGHT 3 description TEXT category TAG price NUMERIC SORTABLE
~~~

Meaning of the components:

| Component | Purpose |
| --- | --- |
| `idx:products` | Name of the search index |
| `ON HASH` | Indexes Redis Hashes |
| `PREFIX 1 "product:"` | Includes only keys starting with this prefix |
| `title TEXT WEIGHT 3` | Text field with boosted weight for relevance scoring |
| `description TEXT` | Searchable text field |
| `category TAG` | Tag field suited for exact filtering |
| `price NUMERIC SORTABLE` | Numeric field supporting range filters and sorting |

The index creation command above is **independent of Spring Data Redis's `@Indexed` annotation**. `FT.CREATE` is a Query Engine command maintaining a separate search indexing system.

### 9.2. Executing Search Queries

Find documents containing the word `Redis` in the title:

~~~redis
FT.SEARCH idx:products "@title:Redis"
~~~

Combine word search, category filter, and price range:

~~~redis
FT.SEARCH idx:products "(@title:Redis | @description:Redis) @category:{programming} @price:[100000 300000]" LIMIT 0 20
~~~

Syntax breakdown:

- `@title:Redis`: searches for the word in the `title` field.
- `|`: expresses logical OR inside the search expression.
- `@category:{programming}`: filters for Tag value `programming`.
- `@price:[100000 300000]`: inclusive numeric range filter.
- `LIMIT 0 20`: retrieves a slice of results, capping returned records.

This is a **search query over indexed data**, distinct from Spring Data Redis Repositories parsing `findBy...` method names. Depending on the client, a Java application may need a library supporting Redis Query Engine or send search commands via an appropriate Redis API. Do not assume every `RedisTemplate` version directly provides a repository API with the full `FT.SEARCH` DSL.

### 9.3. Considerations for Vietnamese Search

Searching Vietnamese text with diacritics and compound words is not simply substring matching. Pay attention to:

- **Word segmentation:** Vietnamese uses spaces between syllables, while a single word can consist of multiple syllables; tokenizer strategies affect results.
- **Diacritics and Unicode:** Unicode normalization rules, keeping vs. stripping diacritics, and case handling must be decided explicitly.
- **Stop words, synonyms, stemming:** Not every search engine's analyzers fit or fully support Vietnamese.
- **Typos:** Some forms of fuzzy search improve typo tolerance, yet precision and recall still need measurement.
- **Ranking:** `title` vs. `description` weights, field boosts, and click signals can influence result quality.

Do not assume simply creating a `TEXT` index yields high-quality Vietnamese tokenization, semantic understanding, or synonym matching. For large Vietnamese search systems, build a sample query benchmark and evaluate analyzers/engines against real data.

### 9.4. Search Indexes Do Not Create Arbitrary `JOIN`s

Having a search index does not mean having SQL `JOIN`s. Search Query Engine lets you search and filter indexed data according to its schema and capabilities; relationships across entities still require design. You can flatten key fields from multiple entities into a single **search document** tailored to a specific use case.

For example, to search orders by customer name and status, create a document:

~~~text
search:order:o-9001
  orderId      = o-9001
  customerId   = c-101
  customerName = Nguyễn Lan
  status       = PAID
  totalCents   = 125000
~~~

This is a **denormalized search document**. When the customer changes name, the search document may need updating. Update propagation and synchronization must be designed explicitly; the search engine does not infer joins from `customerId` alone.

## 10. When to Use a Dedicated Search Engine?

If Redis serves mainly as a cache or TTL-bound state store while canonical data lives in another database, consider letting the **primary database** or a **dedicated search engine** handle queries unsuited to Redis Repositories.

Example read/write architecture:

~~~text
                        Application
                            |
                +-----------+-----------+
                |                       |
                v                       v
           Command Service         Search API
                |                       |
                v                       v
       Primary Source DB          Search Engine
                |                       ^
                v                       |
          Change Event / Outbox / CDC --+
                |
                v
       Redis cache for hot keys
~~~

Depending on the use case, the search tool can be Redis Query Engine or a standalone engine such as OpenSearch/Elasticsearch. When syncing asynchronously from the primary database to a search index, accept an observable lag between writes and search visibility.

Problems favoring a dedicated tool:

- Multi-field full-text search across diverse data types with deep language analysis.
- Relevance ranking, autocomplete, fuzzy matching, and typo tolerance.
- Constantly changing multi-field filter combinations; complex sorting/faceting/aggregations.
- Search dashboards, analytical queries, and queries over massive document volumes.
- Independent control over relevance tuning, schemas, and reindexing lifecycles.

Conversely, if you only need to look up `customerId` to fetch a small set of orders, a Redis Set or `@Indexed` may be simpler and more efficient.

## 11. Synchronization Mechanisms and Query Consistency

Choosing additional indexes or read models means data can exist in multiple representations:

~~~text
Canonical data source
   |
   +-- Redis Hash
   |
   +-- Redis Repository secondary index (Set)
   |
   +-- Manual read model (Set / Sorted Set)
   |
   +-- Search document / search index
~~~

If branches update independently, an operation can alter primary data without updating related indexes. For example:

1. Order `o-9001` changes status from `NEW` to `PAID`.
2. Hash updates successfully.
3. The search-index update event fails or is delayed.
4. A user searches for `PAID` orders and temporarily misses `o-9001`.

The design should answer:

| Question | Design Implication |
| --- | --- |
| Where is the canonical source of truth? | Determines which data recovers drifted indexes |
| Write indexes synchronously or asynchronously? | Trade-off between write latency and result freshness |
| What if a partial update fails? | Retries, idempotency, and data reconciliation |
| How are legacy records reindexed? | Checkpointed backfill/rebuild without missing concurrent changes |
| Does deletion or TTL expiration remove index entries? | Avoids orphaned memberships or stale search documents |
| Are search results treated as final business truth? | May require reloading and validating canonical state before critical actions |

### Do Not Assume Redis Repositories Enforce Relational Transactions

The term `Repository` in Spring Data denotes a data-access abstraction. It **does not guarantee** the same transaction, foreign key, JOIN, or isolation properties as JPA.

When multi-key invariants are needed, design within Redis command atomicity and deployment topology. Operations in Redis Cluster also face hash slot constraints on many multi-key commands. Some problems can be solved with appropriately scoped Lua scripts/transactions, whereas workflows spanning Redis and another store typically require application-level consistency patterns.

### TTL and Lingering Index Records

Redis Hashes can expire without auxiliary index sets being cleaned immediately if keyspace notifications or cleanup logic fail to fire properly. Spring Data Redis provides expiration event support, yet do not assume every environment delivers every event—especially when listeners briefly stop.

If an index holds IDs of expired Hashes, queries may have to skip missing entities and a dedicated cleanup process may be required. For search documents built from TTL-bound data, specify explicitly whether search documents also expire, are deleted by events, or are pruned by a reconciliation job.

## 12. Testing Important Boundaries

Tests should not merely prove `save` and `findById` work. They need to verify the behavior of the query architecture itself.

Example Spring Data Redis integration test combining two repositories:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CustomerOrderQueryIntegrationTest {

    @Autowired CustomerRepository customers;
    @Autowired OrderRepository orders;
    @Autowired CustomerOrderQueryService service;

    @Test
    void loadsOrdersThroughIndexedCustomerId() {
        String suffix = UUID.randomUUID().toString();
        String customerId = "c-" + suffix;
        String orderId = "o-" + suffix;

        try {
            customers.save(new Customer(
                customerId, suffix + "@example.test", "Nguyễn Lan"
            ));
            orders.save(new Order(
                orderId, customerId, "PAID", 125000
            ));

            CustomerOrderQueryService.CustomerOrders result =
                service.loadCustomerOrders(customerId);

            assertThat(result.customer().getId())
                .isEqualTo(customerId);
            assertThat(result.orders())
                .extracting(Order::getId)
                .contains(orderId);
        } finally {
            orders.deleteById(orderId);
            customers.deleteById(customerId);
        }
    }
}
~~~

Tests should run in a Spring Boot context with Redis Repositories enabled and connected to a real test Redis instance, such as one provided by Testcontainers. The snippet above assumes test Redis connection infrastructure is configured; never run against production Redis.

Beyond happy paths, scenarios needing proper integration or system-level verification include:

- Changing `customerId` or `status` and confirming index queries reflect the update.
- Deleting records or letting TTL expire and observing how indexes or read models behave.
- Adding a new index over existing data, running backfill, and confirming older records become searchable.
- Testing queries using only operators/fields supported by Redis Repositories; catching config errors or unsupported queries at startup/runtime.
- For search engines, verifying new/updated/deleted documents appear or vanish within acceptable consistency lag.
- For Vietnamese search features, testing datasets with diacritics, without diacritics, and multi-syllable words to measure actual quality.

If a workload filters tens of thousands of results, measure query latency, Redis command counts, memory usage, and key/index counts in a representative dataset—not just correctness. A test with two records reveals very little about production costs.

## 13. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Expecting `@Reference` to auto-JOIN multiple entities | References only model relationships at the mapping layer | Multi-step queries or design a read model |
| Expecting `@Indexed` to match substrings in text | Redis Repository secondary indexes are not full-text indexes | Use a search index / suitable search engine |
| Writing JPA-style derived queries and getting errors or wrong results | Redis Repositories support their own subset of operators/queries | Verify store module support |
| Fetching all Hashes and filtering in Java | Missing index suited to the question | Design lookup keys, Sets/Sorted Sets, or a query engine |
| Using `KEYS` for a search endpoint | Scans the entire keyspace | Avoid `KEYS` on production paths; build indexes |
| Hash data is right, but field lookup is wrong | Secondary index missing, stale, or bypassed on direct writes | Unify write path; plan rebuilds |
| After adding `@Indexed`, legacy data is not found | Annotation does not backfill automatically | Run controlled reindex/backfill |
| Pagination results shift between reads | Underlying dataset changed; unstable index/order | Define ordering, cursors, and consistency level |
| Created `FT.CREATE` yet repository ignores search index | Two separate indexing mechanisms | Query via the corresponding Search/Query Engine API |
| Vietnamese search results miss expectations | Unsuitable tokenizer/analyzer/normalization | Choose and benchmark Vietnamese analysis strategy |
| Search results lag behind new writes | Asynchronous index synchronization | Define SLA for index lag, retries, and reconciliation |
| High Redis memory growth after adding indexes | Each field and distinct value creates index structures | Index only needed queries; monitor memory |

## 14. Which Strategy Should You Pick for Each Need?

| Primary Need | Preferred Strategy | When Scaling Further |
| --- | --- | --- |
| Fetch entity by ID | `findById` / key lookup | Cache / batch reads if needed |
| Find email or status by exact value | `@Indexed` for Redis Repository | Move to read model if filter combinations grow complex |
| Find orders for a customer | Index on `customerId` or relationship Set | Sorted Set if ordering/ranges are needed frequently |
| Display customer name in order list | Application-side join for small counts | Denormalized read model on hot read paths |
| Find orders by many flexible filters | Read model aligned to dominant queries | Query engine or flexible query store |
| Search products by keyword, relevance, and price range | Redis Search/Query Engine if supported by infra | Dedicated search engine if requirements are complex |
| Large-scale grouping/aggregation reports | Pre-computed metrics, OLAP, or suitable DB | Never scan all Redis keys per request |
| Multi-word Vietnamese search, autocomplete, fuzzy | Engine with suitable analyzers and queries | Evaluate real quality before rollout |

No single index is optimal for every query. Start from **the actual questions users need answered**, query frequency, record volumes, sort order, acceptable latency, and consistency requirements; choose the data model and indexes accordingly.

## 15. Summary

Spring Data Redis Repositories fit ID-based retrieval and certain queries over indexed properties. They do not provide general SQL `JOIN`s, do not automatically support arbitrary query criteria, and do not turn `@Indexed` into a full-text index.

When data spans multiple entities, applications can **combine results at the service layer** or build **read models / denormalized documents** suited to the use case. When predictable ordering and ranking are needed, Redis Sets and Sorted Sets support pre-designed access patterns. For text search, complex filtering, scoring, or language analysis, evaluate Redis Search/Query Engine or a dedicated search system.

The core boundary lies not only in query syntax: **every index and duplicated data copy has a lifecycle**, covering creation, updates, deletions, expiration, backfills, and reconciliation on failures. Good design picks the right tool for the business question and clearly defines who owns keeping all those representations consistent.
