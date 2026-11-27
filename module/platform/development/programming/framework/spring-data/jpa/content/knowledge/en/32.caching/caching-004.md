# Query Result Cache and Its Relationship with Entity Cache

## 1. Why distinguish the cache types in JPA?

When a Spring Data JPA application reads data, Hibernate can retrieve data from multiple cache layers before querying the database. These layers differ in scope, contents, and purpose. If you simply refer to all of them as "JPA cache", it is very easy to mistakenly assume that the query result cache also stores full entity state, or that enabling entity caching will automatically cache every `SELECT` statement.

Three key mechanisms to distinguish:

1. **First-level cache (L1):** the cache residing in the persistence context of an `EntityManager`. This is a mandatory entity management mechanism in JPA; each persistence context maintains a single entity object for a given identifier.
2. **Second-level cache (L2) / entity cache:** an optional cache at the `EntityManagerFactory` or Hibernate `SessionFactory` level, shareable across multiple persistence contexts. It stores entity state by identifier.
3. **Query cache:** an optional Hibernate feature that stores the results of a specific query along with its parameter and pagination information. For queries returning entities, the query cache typically stores entity identifiers and relies on the entity cache to retrieve entity state.

Spring Data JPA does not automatically cache all repository results. The query cache is a Hibernate feature; whereas Spring Cache is a separate abstraction for caching method return values at the application layer.

## 2. First-level cache: cache within the persistence context

Each `EntityManager` manages a persistence context. When an entity is loaded into the persistence context, Hibernate tracks that entity and maintains an identity map: the same entity type and primary key within the same persistence context correspond to the same managed instance.

Example:

~~~java
Product first = entityManager.find(Product.class, 10L);
Product second = entityManager.find(Product.class, 10L);

System.out.println(first == second); // true within the same persistence context
~~~

After the first `find`, Hibernate typically does not need to run another `SELECT` for the next `find` with the same ID within the same persistence context. The second call can return the exact managed instance from the L1 cache.

Characteristics of L1:

- Scoped to a single persistence context, not shared automatically across `EntityManager` instances.
- Used by default; no cache property is needed to enable it.
- Maintains identity and tracks entity changes.
- Released when the persistence context closes; can be cleared via `EntityManager.clear()`.
- Not a query cache: it looks up entities by identifier and does not store arbitrary query result sets for reuse across `EntityManager` instances.

L1 can skew measurements if you simply run the same query repeatedly within the same `EntityManager`. The second result may come from the persistence context rather than proving that the query cache or L2 is active.

## 3. Second-level cache: caching entity state

L2 is an optional cache outside a specific persistence context. When configured, multiple `EntityManager` instances can share this cache through the Hibernate `SessionFactory`. Its purpose is to reduce database reads for entity state when the same entity is accessed repeatedly across multiple transactions or persistence contexts.

For example, transaction A loads `Product` with ID 10. Once the entity is placed into the L2 cache, transaction B using a different `EntityManager` can retrieve the entity state from L2 without re-reading the corresponding row from the database, provided the cache entry is still valid and the cache strategy permits it.

The L2 cache is managed by entity type and identifier. It does not automatically cache arbitrary search results like "all products in category BOOK". That is the job of the query cache or an application-level cache.

### 3.1. Declaring an entity as cacheable

JPA provides the `jakarta.persistence.Cacheable` annotation to mark an entity as eligible for the shared cache. Hibernate additionally provides `org.hibernate.annotations.Cache` to specify the concurrency strategy and cache region.

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "products")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "product"
)
public class Product {
    @Id
    @SequenceGenerator(
        name = "product_seq_gen",
        sequenceName = "product_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_seq_gen"
    )
    private Long id;

    private String name;
    private String category;

    protected Product() {
    }

    public Product(String name, String category) {
        this.name = name;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }
}
~~~

Using `SEQUENCE` for the ID in this example is solely to illustrate entity mapping; the ID generation strategy is not a prerequisite for enabling the L2 cache.

Key points to understand:

- `@Cacheable` is a standard JPA annotation that marks an entity as eligible to participate in the shared cache according to the persistence unit's cache mode configuration.
- `@Cache` is a Hibernate-specific annotation specifying the concurrency strategy and region.
- `region = "product"` places the entity in a cache region named `product` so it can be configured, monitored, or evicted separately.
- Adding the annotations alone is not enough if the application has not configured a second-level cache provider and enabled L2 cache in Hibernate.
- If an entity has collection associations, caching the entity does not automatically mean collection membership is cached. Collections may require their own cache configuration.

### 3.2. Common concurrency strategies

Hibernate provides cache strategies representing the consistency guarantees the application accepts:

| Strategy | When suitable | Notes |
|---|---|---|
| `READ_ONLY` | Data immutable after creation, e.g., fixed catalogs | Best suited when the entity is genuinely never or almost never updated. |
| `NONSTRICT_READ_WRITE` | Data changes rarely and tolerates a brief window where stale values may be read | Does not provide strong consistency guarantees at every moment during updates. |
| `READ_WRITE` | Mutable entities requiring cache coordination with transactional updates | Uses Hibernate/provider soft-lock mechanisms; you still must understand cache provider and distributed environment limits. |
| `TRANSACTIONAL` | Cache needs to participate in transactions with corresponding guarantees | Depends on the cache provider and transaction integration, often requiring more complex infrastructure. |

Do not use `READ_ONLY` for entities that the application still updates. Also, do not treat `READ_WRITE` as a replacement for database constraints, locks, or optimistic locking. A cache strategy is a cache synchronization policy, while data correctness still needs protection at the transaction and database layers.

## 4. What does Hibernate's query cache store?

The query cache stores the results of a query that has been marked cacheable. The cache key depends on the query text, parameters, pagination, and certain execution contexts. The same JPQL query with different parameter values or page bounds produces different entries.

Two result types must be distinguished:

- **Queries returning scalars or simple values:** the query cache can store the resulting values directly, such as product names, counts, or totals.
- **Queries returning entities:** Hibernate typically caches the entity identifiers in the query result, along with any other selected values if present. Entity state is retrieved from the L2 cache if a valid entry exists; if L2 does not have the data, Hibernate still must read the entity state from the database using those IDs.

Therefore, the query cache is not a second copy of the entire entity cache. It answers the question "which results did this query produce?", whereas L2 answers "what is the state of the entity with this ID?".

### 4.1. Why does the query cache usually need to pair with the entity cache?

Consider the query:

~~~sql
select p from Product p where p.category = 'BOOK'
~~~

On the first run, Hibernate executes SQL to find products in `BOOK` and places the query result into the query cache. For entity results, the query cache stores the matching `Product` IDs.

On a subsequent run, if the query cache entry is still valid, Hibernate can skip executing the SQL search by category. However, Hibernate still needs to materialize the `Product` instances to return to the application:

- If the corresponding `Product` is in L1, use the managed instance.
- If not in L1 but present in L2, fetch the entity state from L2.
- If not in L2, Hibernate must access the database to fetch the entity state by ID.

Consequently, **a query cache hit does not mean zero database access**. If the entity cache is not enabled or entities are frequently evicted, the query cache may skip the query that finds the ID list yet still emit `SELECT` statements to load each entity or group of entities.

The query cache generally delivers higher value when query results repeat and the corresponding entities are also retained in the L2 cache. For queries returning only scalars or aggregates, the query cache can be beneficial even without caching entity state.

## 5. Enabling L2 cache and query cache in Hibernate

Both the L2 cache and query cache are optional features in Hibernate. Basic configuration example in `application.properties`:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.use_query_cache=true
spring.jpa.properties.hibernate.generate_statistics=true
~~~

In addition to these properties, the application must configure a cache provider compatible with the Hibernate version in use. You can use Hibernate JCache integration with a JCache implementation like Ehcache, or another Hibernate-supported provider. Dependencies and the region factory value must match the Hibernate version; do not copy a factory class name from a guide for a different version.

For instance, when using JCache, a project typically needs the matching Hibernate integration module and a provider library. The cache provider handles entry storage, capacity limits, expiry, eviction, and cache sharing per configuration. Setting `use_second_level_cache=true` alone without an appropriate provider/region factory can cause startup failures or prevent the cache from working as expected.

The query cache must be enabled separately via `use_query_cache`. Enabling the L2 cache does not automatically enable the query cache; marking a query as cacheable also does not automatically make all entities L2-cacheable.

### 5.1. Marking a query in Spring Data JPA

Spring Data JPA allows passing JPA query hints to Hibernate via `@QueryHints`. Hibernate recognizes the `org.hibernate.cacheable` hint to mark a query as eligible for the query cache.

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.QueryHint;

public interface ProductRepository extends JpaRepository<Product, Long> {
    @Query("""
        select p
        from Product p
        where p.category = :category
        order by p.name
        """)
    @QueryHints(
        value = @QueryHint(
            name = "org.hibernate.cacheable",
            value = "true"
        )
    )
    List<Product> findCachedByCategory(
        @Param("category") String category
    );
}
~~~

This is a Hibernate-specific hint, not a mandatory JPA query-caching feature. If you switch JPA providers, the hint may be ignored or have a different meaning.

You can specify a query cache region using the corresponding Hibernate hint if you want to partition caches by query type. Verify the exact hint name and region configuration against the running Hibernate version. When no custom region is specified, Hibernate uses the default query cache region.

Do not mark every repository method as cacheable. Prioritize queries whose results are reused repeatedly, whose parameters have a reasonable number of combinations, and whose underlying data changes infrequently.

## 6. Relationship between query cache and entity cache

The two mechanisms work together yet have different lifecycles:

| Aspect | Entity cache (L2) | Query cache |
|---|---|---|
| Primary contents | Entity state by entity type and ID | Query results by query, parameters, and pagination |
| Lookup key | Entity type + primary key | Query key and execution context |
| Usage scope | Can serve multiple different queries that need the same entity | Only serves the query matching the cache key |
| Enabling | Annotate/configure entities and configure an L2 provider | Enable query cache and mark individual queries cacheable |
| Entity-returning queries | Provides entity state once IDs are known | Typically provides the IDs of matching entities |
| Scalar queries | Not its primary purpose | Can store result values directly |
| Invalidation | By entity entry and cache strategy | By query result entry and update timestamps of related tables |

The entity query read flow can be visualized as follows:

~~~text
Repository query
      |
      v
Hibernate query cache
      |
      +-- Cache miss --> Execute SELECT query --> Store query result
      |
      +-- Cache hit --> Retrieve entity identifiers
                              |
                              v
                    Persistence context (L1)
                              |
                     L1 miss / entity absent
                              |
                              v
                       Entity cache (L2)
                              |
                    L2 miss / entry absent
                              |
                              v
                         Database
~~~

This diagram shows a conceptual flow. For scalar queries, Hibernate can return cached values directly without the entity-loading step. For entity queries involving joins, projections, or collections, the actual steps also depend on the result type and mappings.

A query cache hit can save the cost of re-evaluating filter predicates or joins, but if L2 does not hold the entity state, the database still has to supply the entity data. Conversely, the L2 cache can speed up loading an entity with a known ID without needing the query cache. Thus, the two caches solve different kinds of work.

## 7. How is the query cache refreshed and invalidated?

Query results can become stale when data in the underlying tables changes. Hibernate uses update timestamps to track when query spaces/tables were modified and to evaluate whether a query's cache entry is still valid.

When a transaction modifies data through Hibernate, Hibernate can mark the affected query spaces as updated. Query cache entries depending on a table with a newer update timestamp are no longer treated as valid results; Hibernate re-executes the query and caches the new results.

This mechanism has several consequences:

- Query cache invalidation can be broader than a single row. A single table modification can invalidate many query cache entries referencing that table.
- Frequently updated tables cause low query cache hit ratios and increase cache management overhead.
- The query cache relies on both the query-result storage region and the timestamp-tracking region. Both regions need proper cache provider and eviction policies configured.
- Updates made by other applications, direct JDBC, admin scripts, or external systems may not be known to Hibernate for cache invalidation. In such cases, appropriate synchronization, eviction, or TTL mechanisms are needed.
- Bulk JPQL/SQL and native queries have different semantics from regular entity operations. Check persistence context synchronization and query space/cache invalidation behavior per provider; do not assume all SQL executed outside Hibernate automatically updates all related caches.

If multiple applications modify the same database, design a consistent cache policy across nodes and writers. Do not enable the query cache without a strategy for handling external data changes.

## 8. Caching collections and entity associations

The entity cache stores an entity's state by ID, but does not automatically store all association collections. For example, if `Product` has a `reviews` collection, caching `Product` does not guarantee the list of reviews is stored and restored from cache.

Hibernate can cache collections separately via the `@Cache` annotation on an association if the relationship type and provider support it appropriately. When using collection caching, consider element additions/removals, collection ordering, filters, and invalidation. Caching collection membership also differs from caching the state of each individual `Review` entity.

The query cache can store results of join queries or queries involving associations, but it does not replace a fetch strategy. If an application suffers from N+1 queries, review fetch joins, entity graphs, batch fetching, or projections. Enabling the query cache does not fix an inefficient data-loading mapping.

## 9. Distinguishing Hibernate query cache from Spring Cache

The annotation name `@Cacheable` appears in two different APIs and is very easy to confuse:

- `jakarta.persistence.Cacheable`: standard JPA annotation on an entity, indicating eligibility to participate in the shared second-level cache.
- `org.springframework.cache.annotation.Cacheable`: Spring Cache annotation on a method, caching the method's return value by cache name and key.

Spring Cache example in a service:

~~~java
import java.util.List;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {
    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "productsByCategory",
        key = "#category"
    )
    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

To use Spring Cache, the application must enable caching with `@EnableCaching` and configure an appropriate `CacheManager`/provider. The example above caches the method's return value at the Spring layer; it does not enable Hibernate's query cache and does not require the query to carry the `org.hibernate.cacheable` hint.

Comparison:

| Mechanism | Where it is marked | What does it cache? | Who manages it? |
|---|---|---|---|
| JPA/Hibernate L2 | Entity annotation/configuration | Entity state by ID | Hibernate and the L2 provider |
| Hibernate query cache | Hibernate query hint/configuration | Query results | Hibernate query cache |
| Spring Cache | Annotation on service methods | Method return values | Spring Cache and `CacheManager` |

Spring Cache can cache DTOs or result lists at the application layer. However, the application must actively design keys and invalidation. For example, when updating a `Product`, you must evict or update the related `productsByCategory` entry; Hibernate query cache invalidation does not automatically clear Spring Cache. Similarly, Spring's `@CacheEvict` does not automatically evict the L2 cache unless the corresponding mechanism is invoked.

Do not layer multiple caches over the same data without clearly defining the source of truth, TTL, eviction, and write handling. Overlapping caches can leave stale data in one layer even after another layer has been updated.

## 10. When should you use query cache and entity cache?

The query cache is usually appropriate when:

- The exact same query runs repeatedly with the same parameters and pagination.
- Underlying data changes rarely relative to read frequency.
- Result sets are reasonably sized and do not produce excessive distinct cache keys.
- The application can observe hits/misses and manage invalidation.
- For entity-returning queries, the L2 cache is also capable of serving those entities.

The entity L2 cache is usually appropriate when:

- A set of entities is read repeatedly by ID across multiple transactions.
- Data changes infrequently or has a suitable concurrency strategy.
- A stable cache provider can be configured consistently across instances.
- Caching substantially reduces database read round trips.

Avoid indiscriminate caching for:

- Data that changes constantly or requires strict latest-read guarantees.
- Queries with huge combinations of parameters, sorts, and pages that fragment cache keys.
- Large result sets with low reuse.
- Entities with complex relationships and hard-to-control invalidation.
- Data frequently modified by multiple writers outside Hibernate without a cache synchronization mechanism.

Caching is a trade-off among performance, memory, and data freshness. Do not enable caching just because it is available; identify which queries are expensive, have high enough reuse, and have clear invalidation rules.

## 11. Verifying that caching actually works

To verify behavior, you must distinguish query cache hits, L2 cache hits, and L1 cache hits. Simply seeing a repository return results faster is not enough to prove which mechanism actually worked.

You can enable Hibernate statistics in test environments:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Then unwrap `SessionFactory` from `EntityManagerFactory` and read `Statistics`:

~~~java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateCacheMetrics {
    private final Statistics statistics;

    public HibernateCacheMetrics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public void printCacheStatistics() {
        System.out.println(
                "Query cache hits: " + statistics.getQueryCacheHitCount()
        );
        System.out.println(
                "Query cache misses: " + statistics.getQueryCacheMissCount()
        );
        System.out.println(
                "L2 cache hits: " + statistics.getSecondLevelCacheHitCount()
        );
        System.out.println(
                "L2 cache misses: " + statistics.getSecondLevelCacheMissCount()
        );
    }
}
~~~

This is an example of reading statistics; in real applications, export metrics through a monitoring system rather than printing directly to the console. The `Statistics` API belongs to Hibernate and is not a portable JPA API.

Recommended verification workflow:

1. Use a database engine and JDBC driver close to production, such as Testcontainers.
2. Enable L2 cache, query cache, and statistics; configure a real cache provider.
3. Create committed data and execute a query marked cacheable for the first time to populate the query cache entry.
4. Close or clear the persistence context, then re-run the same query with the same parameters to eliminate L1 cache effects.
5. Observe query cache hits/misses and L2 hits/misses; inspect SQL logs to verify whether the database still executes the search query or entity-loading `SELECT`s.
6. Update an entity via Hibernate and re-run the query to verify invalidation.
7. Try updating data via JDBC or an external process to verify the system's synchronization/eviction policy.
8. Measure latency, database access counts, memory, and data freshness; compare against the uncached baseline.

When testing entity queries, seeing a query cache hit alongside `SELECT` statements loading entities can be normal behavior if the L2 cache misses. Do not conclude the query cache is broken solely because entity-loading SQL still appears; distinguish SQL finding the result set from SQL loading entity state.

## 12. Common misconceptions

- **L1 is not L2:** L1 belongs to a single persistence context; L2 is shared at the `SessionFactory`/provider scope as configured.
- **L2 is not the query cache:** L2 stores entity state by ID; the query cache stores results of a specific query.
- **A query cache hit does not mean zero database access:** entity results still require entity state from L1, L2, or the database.
- **Enabling L2 does not enable the query cache:** you must enable the query cache and mark each appropriate query.
- **`saveAll()` does not mean batch insert:** it saves each entity via the repository; batching depends on Hibernate, identifier strategy, flushing, and JDBC.
- **Spring `@Cacheable` differs from JPA `@Cacheable`:** one caches method return values, while the other marks an entity eligible for the shared cache.
- **Cache invalidation must be designed:** changes outside Hibernate may not automatically reflect in caches.
- **The query cache does not replace fetch optimization:** you still need to address N+1 issues, projections, and proper fetch plans.

When designing caching in Spring Data JPA, clearly identify which data needs caching by ID, which queries have repeated results, who the data writers are, and how much staleness is acceptable. Use L2 to reuse entity state, the query cache to reuse query results, and Spring Cache when caching method return values at the application layer. Verify hits/misses and invalidation against the actual database and provider before promoting the configuration to production.
