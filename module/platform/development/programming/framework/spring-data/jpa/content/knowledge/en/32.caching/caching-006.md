# Query Hints and `CacheRetrieveMode`, `CacheStoreMode` in Spring Data JPA

In Spring Data JPA, a **query hint** is an instruction passed alongside a query to the JPA provider (for example, Hibernate). The two standard hints `CacheRetrieveMode` and `CacheStoreMode` control how a read/write operation interacts with the **second-level cache (L2)**. Understanding them properly helps you decide when cached data can be leveraged, when stale L2 data should be bypassed, and when L2 should be refreshed after reading from the database.

The focus of this lesson is **Spring Data JPA repositories**, Jakarta Persistence values, coordination with `EntityManager`, and commonly overlooked limitations. Examples use **Java 17+, Spring Boot 3.x/Spring Data JPA 3.x, and `jakarta.persistence`**; if a project uses Spring Boot 2/JPA 2, the package name and hint key prefixes are `javax.persistence.*`.

## 1. Placing query hints accurately within the caching system

Before applying a hint, distinguish three mechanisms:

| Mechanism | Scope | What does it store? | How do the two standard cache modes affect it? |
|---|---|---|---|
| **First-level cache (L1)** | One persistence context/`EntityManager` | Managed entities, by identifier | **Not disabled** by `CacheRetrieveMode.BYPASS` or `CacheStoreMode.BYPASS` |
| **Second-level cache (L2)** | Typically shared across `EntityManager` instances belonging to the same `EntityManagerFactory` | Cache-eligible entity/collection state per provider | **This is the target controlled** by retrieve/store modes |
| **Query result cache** | Provider-specific query cache, e.g., Hibernate | Results or identifier lists of a query with its parameters | Requires separate configuration/hints; **not enabled automatically** by `CacheRetrieveMode.USE` |

For example: within the same transaction, you call `findById(10L)` twice. The second call can be served from L1 even when L2 is bypassed, because the persistence context already holds the managed object for that ID. Therefore, a `BYPASS` hint **does not guarantee** returning the latest state from the database in all situations.

A JPQL query `select p from Product p where p.category = :category` normally still has to run SQL to identify matching rows, even when L2 already caches the entities. The L2 entity cache and Hibernate's query result cache solve two different problems; to avoid re-running a repeated query, you must look into the query result cache separately.

Query hints also **do not replace** data consistency policies, transaction isolation, locking, or synchronization mechanisms when multiple applications update the same database.

## 2. `CacheRetrieveMode`: choosing how to read from L2

`jakarta.persistence.CacheRetrieveMode` has exactly **two** values:

- **`USE` (default):** allows the provider to read entity data from L2 when a valid cached entry exists. If none exists or the cache cannot be used, the provider may need to query the database. `USE` does not guarantee a cache hit.
- **`BYPASS`:** bypasses **reading from L2** for the operation carrying the hint; the provider fetches data from the database instead of reading from L2. L1 still remains active, and an entity already managed in the same persistence context can still be reused.

Standard property name used in Spring Boot 3+/Jakarta Persistence:

```text
jakarta.persistence.cache.retrieveMode
```

Java enum values: `CacheRetrieveMode.USE` and `CacheRetrieveMode.BYPASS`. Do not confuse `BYPASS` in this mode with disabling all caches.

## 3. `CacheStoreMode`: choosing how to write to or refresh L2

`jakarta.persistence.CacheStoreMode` has **three** values:

| Value | Meaning for L2 | Case to remember |
|---|---|---|
| `USE` (default) | Allows placing entities read from the database into L2 and updating the cache on writes; does not force refreshing already-cached items on every database read | Standard mode |
| `BYPASS` | Does not put or update entities into L2 for this operation; the provider may **invalidate** cache entries on database writes | When wanting to avoid populating the cache in a special flow |
| `REFRESH` | When reading data from the database or writing data, puts/updates entity state into L2 even if L2 already holds an entry | When wanting to repopulate cache entries from newly read data |

Standard property name:

```text
jakarta.persistence.cache.storeMode
```

Important notes:

- `REFRESH` **does not automatically force** an object already managed in L1 to reload its data. It describes how **L2 is handled when data is fetched from the database** or written.
- `REFRESH` is a value of **store mode**; `CacheRetrieveMode` **does not** have a `REFRESH` value.
- `BYPASS` in store mode does not mean wiping all L2 entries. For write operations, the provider is allowed to invalidate affected entries to maintain consistency.
- If L2 is not enabled or the entity is not cache-eligible, cache modes **have no L2 effect**.

## 4. Combining both modes: where to read and how to handle the cache

| Retrieve mode | Store mode | Practical interpretation |
|---|---|---|
| `USE` | `USE` | Can read from L2; when reading the database, can populate L2. This is the default. |
| `BYPASS` | `USE` | Does not read L2; when loading data from the database, can populate/update L2 per `USE` policy. |
| `USE` | `BYPASS` | Can read from L2; does not populate/update L2 during the applied operation. |
| `BYPASS` | `BYPASS` | Neither reads from L2 nor populates/updates L2 during the operation; does not mean disabling L1. |
| `BYPASS` | `REFRESH` | Bypasses L2 on read and refreshes L2 with data fetched from the database. Useful when you need to re-read and update the cache. |
| `USE` | `REFRESH` | Allows reading L2; if data is actually loaded from the database, refreshes L2. **Does not guarantee** forcing a database re-query. |

In Hibernate, these pairs correspond conceptually to `CacheMode` values such as `NORMAL`, `PUT`, `GET`, `IGNORE`, and `REFRESH`; when writing Spring Data JPA code, you can use the standard Jakarta Persistence enum pairs for easier provider portability.

A practical rule of thumb: to **skip L2 data and update L2 from that database read**, consider **`BYPASS + REFRESH`**. To run a query that **neither reads from nor adds to L2**, use **`BYPASS + BYPASS`**. Both still require accounting for L1 and transaction context.

## 5. Attaching query hints on Spring Data JPA repository methods

Spring Data JPA provides `org.springframework.data.jpa.repository.QueryHints` to place multiple `jakarta.persistence.QueryHint` annotations on a repository method. It applies to queries written with `@Query` as well as many derived query methods.

The example below shows a **cache-eligible entity**. File `Product.java` (in the application's entity package):

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Cacheable
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String category;

    @Column(nullable = false)
    private String name;

    protected Product() { }

    public Product(String category, String name) {
        this.category = category;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getCategory() {
        return category;
    }

    public String getName() {
        return name;
    }
}
```

`@Cacheable` in this snippet is **`jakarta.persistence.Cacheable`**, distinct from **`org.springframework.cache.annotation.Cacheable`** in Spring Cache. It expresses entity cacheability under JPA; **this annotation alone is not enough to ensure a working L2 cache**. You still need to configure a cache provider, cache regions, and an appropriate shared-cache mode.

File `ProductRepository.java`:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {

    @Query("""
           select p
           from Product p
           where p.category = :category
           """)
    @QueryHints(
        value = {
            @QueryHint(
                name = "jakarta.persistence.cache.retrieveMode",
                value = "BYPASS"
            ),
            @QueryHint(
                name = "jakarta.persistence.cache.storeMode",
                value = "REFRESH"
            )
        },
        forCounting = false
    )
    Page<Product> findFreshByCategory(
            @Param("category") String category,
            Pageable pageable);
}
```

**How to read the code:**

1. `@Query` defines the JPQL statement. Spring Data JPA creates a paginated query returning `Product` records by `category`.
2. `@QueryHints` attaches two standard hints: do not read entities from L2 during this query, and instruct updating L2 with entities read from the database.
3. `@QueryHint.value` is a **String**, so the annotation takes `"BYPASS"` and `"REFRESH"`. Hint names and values must be exact; when integrating a specific provider, verify it parses those strings into the expected enums.
4. `forCounting = false` tells Spring Data JPA **not to apply those two hints to the count query** backing `Page`. A count query does not load entities, so entity cache retrieve/store modes generally do not help. A count query may be skipped by pagination optimizations when enough data is already known, but when generated, these two hints will not apply to it.
5. Hints apply only to **this query method**; `findById`, `findAll`, or another query does not automatically inherit that annotation.

These are valid source classes inside a Spring Boot 3.x project with `spring-boot-starter-data-jpa`, a database driver, and datasource configuration. They are **not** standalone plain Java programs runnable by `javac Product.java`, because Jakarta Persistence and Spring Data must be on the classpath.

### A derived query method can also use `@QueryHints`

If custom JPQL is unnecessary, the syntax is even shorter:

```java
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.QueryHints;

import java.util.List;

public interface ProductLookupRepository
        extends JpaRepository<Product, Long> {

    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.cache.retrieveMode",
            value = "BYPASS"
        ),
        @QueryHint(
            name = "jakarta.persistence.cache.storeMode",
            value = "BYPASS"
        )
    })
    List<Product> findByCategory(String category);
}
```

Spring Data JPA derives the query from `findByCategory`, while the two hints affect only that query's L2 interaction.

## 6. Applying hints when using `EntityManager` directly

For a single `find` operation, you can use a `Map<String, Object>` to pass the actual enum values. This avoids representing enums as annotation strings:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Service
public class ProductReadService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public Product findByIdBypassingL2(Long id) {
        Map<String, Object> hints = Map.of(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS,
            "jakarta.persistence.cache.storeMode",
            CacheStoreMode.REFRESH
        );
        return entityManager.find(Product.class, id, hints);
    }
}
```

Intended behavior: the `find` operation does not read the entity from L2, and if loaded from the database, the provider refreshes the appropriate cache entry. However, **if an entity with the same ID is already managed in that `EntityManager`**, L1 can still return the existing instance. Do not name a method "always fetch latest data" solely because of this hint pair.

Modes can also be passed to a `TypedQuery`:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
import jakarta.persistence.TypedQuery;

TypedQuery<Product> query = entityManager.createQuery(
    "select p from Product p where p.category = :category",
    Product.class
);
query.setParameter("category", "Laptop");
query.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);
query.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.REFRESH
);
var products = query.getResultList();
```

This is a **code snippet inside a method that already has an `entityManager` variable**, not a standalone runnable file. A hint set on a `TypedQuery` applies only to executing that query; it takes precedence over the `EntityManager`'s general mode values for that operation.

If you already hold a managed entity and need to reload its state from the database, consider **`entityManager.refresh(managedEntity)`** within an appropriate transaction context. `refresh` reads from the database rather than L2; cache retrieve mode is not the decisive factor in `refresh`. Calling `clear()` or opening a new persistence context can isolate L1 effects during tests, but **`clear()` detaches every managed entity** and can discard unflushed changes if used carelessly.

## 7. Standard query hints differ from Hibernate's query result cache

`@QueryHints` is a **mechanism for attaching metadata**; it does not mean every hint controls caching. Some hints affect timeouts, fetching behavior, read-only mode, or execution properties depending on the JPA standard and provider. For the standard cache keys in this lesson, the controlled target is the **L2 entity cache**.

Hibernate has a separate **query result cache** feature. Example of a Hibernate-specific hint:

```java
@QueryHints({
    @QueryHint(
        name = "org.hibernate.cacheable",
        value = "true"
    )
})
```

This is only an **illustrative annotation snippet** and must be placed on the corresponding repository method. It does not activate the entire caching infrastructure by itself: Hibernate's query cache feature (`hibernate.cache.use_query_cache=true`) must be enabled, a suitable cache region/provider must be present, and entity/collection caching must be configured when needed. The query result cache can cache query identifier lists/results, while loading entity state still involves L1/L2 and the database.

**Do not infer** "setting `CacheRetrieveMode.USE` ⇒ the JPQL query will not execute SQL". L2 hints do not enable Hibernate's query cache, and count queries, pagination, and data updates also affect how much SQL is emitted.

When using Hibernate-specific APIs, prefer the official hint constants for the Hibernate version in use (such as `HibernateHints.HINT_CACHEABLE`) instead of scattering magic strings across repositories. Using provider-specific hints reduces portability; JPA may ignore hints it does not recognize.

## 8. Prerequisites for the two cache modes to take effect

A real project must simultaneously verify:

1. **Shared cache is enabled** for the persistence unit. JPA supports modes such as `NONE`, `ALL`, `ENABLE_SELECTIVE`, and `DISABLE_SELECTIVE`. Under `ENABLE_SELECTIVE`, only eligible entities such as those annotated with `@jakarta.persistence.Cacheable` participate.
2. **An L2 cache provider is genuinely installed and enabled.** For example, with Hibernate, a compatible cache region factory/cache implementation must be configured; toggling a flag without a provider invalidates cache measurements.
3. **Specific entities/associations are cache-eligible.** Do not assume every result from DTO projections, native scalar queries, or collections has an L2 entry.
4. **Measure in contexts isolated from L1.** Re-reading in the same `EntityManager` easily creates false positives due to the L1 identity map. Measurements should use distinct persistence contexts and test data with clear state.
5. **Verify behavior with provider tooling.** With Hibernate, you can enable statistics (`hibernate.generate_statistics=true`) and inspect second-level cache hits/misses/puts, actual SQL statements, and query result cache hits/misses if query caching is used.

Crucially, do not draw conclusions from **SQL logs alone**: a JPQL query may still run `SELECT` while entities come from L2; conversely, seeing no `SELECT` does not prove L2 is working if the entity was already in L1.

## 9. Before–after scenarios for choosing modes

### Scenario A: rarely changing reference data

A `Product` catalog is read by many requests and rarely modified. Proper L2 configuration with `USE/USE` mode generally allows leveraging the cache. There is no need to attach `BYPASS` hints to every query just to "play it safe"; that throws away cache reuse.

### Scenario B: an administrator just modified data outside the application

A system outside Hibernate updated the database directly, leaving `Product`'s L2 entry potentially stale. For a **re-read in a fresh persistence context**, `CacheRetrieveMode.BYPASS` combined with `CacheStoreMode.REFRESH` is an option that can read from the database and repopulate the L2 entry. However, a sustainable solution requires reviewing **synchronization/invalidation processes**, because a single query cannot clean up stale caches across all nodes or concurrent transactions.

If you only want to skip L2 once without repopulating the entry, use `BYPASS/BYPASS`. Note that the stale entry may still remain in L2 for other flows to read; bypassing cache in one place **does not fix data consistency errors by itself**.

### Scenario C: needing to re-read an already-managed entity

`Product` was already loaded in the same `EntityManager`, and then data changed externally. `BYPASS/REFRESH` does not guarantee overwriting state in L1. If business requirements demand a fresh read, evaluate `entityManager.refresh(entity)`; always consider flush/transaction state, isolation, and potentially overwriting pending in-memory changes.

### Scenario D: paginated queries with count

`Page<Product>` can generate both a data query and a count query. Cache retrieve/store hints on the data query matter for entities, but do not help `SELECT COUNT`. Therefore `@QueryHints(..., forCounting = false)` keeps the hints off the count query; do not confuse `forCounting = false` with "do not execute the count query".

## 10. Common pitfalls and verification checklist

| Mistake | Consequence | Fix |
|---|---|---|
| Using `CacheRetrieveMode.REFRESH` | Value **does not exist**; wrong enum | Use `CacheStoreMode.REFRESH` |
| Thinking `retrieveMode=BYPASS` disables L1 too | Managed entity can still be returned | Separate persistence contexts during testing, or use `refresh` if appropriate |
| Thinking `storeMode=BYPASS` purges L2 | Does not issue a full cache clear | Use intentional eviction/invalidation if needed |
| Thinking `@Cacheable` alone makes caching run | L2 provider/config may not be enabled | Check shared-cache mode, region factory, and cache backend |
| Thinking `USE` always produces a cache hit | Query may still hit the DB; entity may be ineligible | Measure cache hits/misses and eligibility rules |
| Thinking `BYPASS/REFRESH` always reads the latest value | L1, transaction isolation, and external writers still affect results | Check persistence context, transaction, and freshness requirements |
| Enabling query result cache via just the two standard modes | JPQL queries can still execute SQL | Enable/measure query result cache separately if truly needed |
| Applying hints to the count query as well | Unnecessary for entity caching | Set `forCounting = false` when using `Page` |
| Mistakenly using `javax.persistence.*` in Boot 3+ | Wrong property/package name; hints may be ignored | Use `jakarta.persistence.*` matching the version |
| Setting hints unrecognized by the provider | Hints may be ignored; unexpected behavior | Use standard hints, check provider docs and integration tests |

### Practical checklist

- Confirm whether you need to control the **L2 entity cache** or actually want to **cache query results**.
- Confirm L2 is enabled and the entity is eligible.
- Choose retrieve mode by asking "may L2 cached data be read?".
- Choose store mode by asking "may L2 be written to or refreshed?".
- Apply hints to the specific query/repository method, avoiding global changes when only one flow needs them.
- For pagination, decide whether `forCounting` should be `false`.
- Test across separate persistence contexts, measuring SQL and L2/query cache statistics. Also test flows where data changes outside the application if that is the reason for bypassing.

## 11. Quick takeaways

- `CacheRetrieveMode` has only **`USE`** and **`BYPASS`**: *read from L2 or skip L2*.
- `CacheStoreMode` has **`USE`**, **`BYPASS`**, and **`REFRESH`**: *write to L2, do not write, or refresh L2*.
- `BYPASS/REFRESH` is useful for re-reading the database and refreshing L2 in an appropriate context; it **does not disable L1**.
- `@QueryHints` + `@QueryHint` attach these modes to a Spring Data JPA method; `forCounting = false` excludes hints from the pagination count query.
- Hibernate's query result cache is a separate feature from the entity L2 cache; standard cache modes do not replace query cache configuration.

## Official references

1. Spring Data JPA, *Applying Query Hints*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
2. Spring Data JPA, `@QueryHints` API (`forCounting`): https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/QueryHints.html
3. Jakarta Persistence, `CacheRetrieveMode`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheRetrieveMode.html
4. Jakarta Persistence, `CacheStoreMode`: https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/CacheStoreMode.html
5. Jakarta EE Tutorial, *Using a Second-Level Cache*: https://jakarta.ee/learn/docs/jakartaee-tutorial/current/persist/persistence-cache/persistence-cache.html
6. Hibernate ORM User Guide, *Managing the cached data* and query result caching: https://docs.hibernate.org/orm/current/userguide/html_single/
