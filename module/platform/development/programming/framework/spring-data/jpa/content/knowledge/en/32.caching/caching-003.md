# Cache Access Policies for Mutable Entities in Spring Data JPA

## Objectives

After this lesson, you will be able to:

1. Distinguish **first-level cache (persistence context)**, Hibernate's **second-level cache**, **query cache**, and **Spring Cache**.
2. Choose a cache concurrency strategy for **mutable entities**: `READ_WRITE`, `NONSTRICT_READ_WRITE`, or `TRANSACTIONAL`, and understand why `READ_ONLY` is unsuitable.
3. Explain the read–modify–`flush`–`commit` lifecycle and how cache regions are updated or invalidated.
4. Coordinate `@Version`, transaction boundaries, cache eviction, and handling updates outside Hibernate to reduce the risk of stale data.
5. Verify behavior using a Java 17+, Spring Data JPA, Hibernate, H2, and JCache provider application.

The focus is **Spring Data JPA using Hibernate as the JPA provider**. JPA defines some general cache operations, whereas strategies `READ_WRITE`, `NONSTRICT_READ_WRITE`, `READ_ONLY`, and `TRANSACTIONAL` are **Hibernate-specific** mechanisms, not `JpaRepository` keywords.

## 1. Understanding cache layers before choosing a policy

| Layer | Scope | When is it used? | Key takeaways |
| --- | --- | --- | --- |
| **L1 / Persistence Context** | One `EntityManager` (Hibernate `Session`) | Automatically manages loaded entities, `persist`, `merge`, and dirty checking | Always bound to the persistence context; no L2 policy annotation replaces L1. |
| **L2 / Second-level cache** | `EntityManagerFactory` / Hibernate `SessionFactory`, shareable across a cluster by the provider | Re-reading a cacheable entity by ID across different sessions | Requires a cache provider + opt-in config + concurrency strategy; has concurrency concerns to manage. |
| **Query cache** | Caches query results marked cacheable | Must be enabled separately and opted in per query | Not equivalent to caching entire entities; data changes can invalidate query cache results. |
| **Spring Cache** (`@Cacheable`, `@CacheEvict`) | Spring/service method return values by key | When code uses the Spring Cache abstraction | Independent of Hibernate L1/L2 caches; requires its own invalidation policy. |

Diagram illustrating lookup by primary key:

```text
TX A / EntityManager A
  findById(10)
    ├─ L1 has Entity? → return managed instance
    └─ L1 miss → L2 has valid data? → reconstruct Entity in L1
                   └─ L2 miss → SELECT database → put Entity into L1
                                                   └─ may put into L2

TX B / EntityManager B
  findById(10)
    ├─ B's L1 (different from A's L1)
    └─ L2 shared within same SessionFactory → potential cache hit
```

**Important:** When calling `findById` twice within the **same transaction/`EntityManager`**, the absence of SQL on the second call can be caused entirely by **L1**, and does not prove L2 is working. To measure L2, test across **two separate transactions/persistence contexts** and inspect Hibernate statistics or SQL.

When calling conditional query methods like `findByStatus(...)`, Hibernate typically still executes the query to find matching IDs; having an L2 cache on the entity **does not automatically turn every query into a cached query**.

## 2. Why do mutable entities need a concurrency policy?

Suppose `Product` has ID `10`, `price=100`, and is in the L2 cache. Two transactions occur:

```text
Time           TX A: update Product #10         TX B: read Product #10
t0             —                                L2 holds price=100
t1             LOAD / change price to 120       —
t2             Not yet committed                Reads while A is writing
t3             COMMIT succeeds                  —
t4             —                                Reads again after A commits
```

If L2 still returns stale data after commit, TX B could use `price=100` even though the database already has `120`. Issues also arise when one transaction reads data while another transaction is updating it. The cache strategy determines **whether cache reads are allowed, cache writes are temporarily blocked, or invalidation occurs** at these moments.

No L2 policy can completely replace **database isolation**, **data locks**, **`@Version`**, or proper transaction design. In particular, reading within an `EntityManager` that already manages `Product#10` may still return the old object from L1, regardless of whether L2 was evicted.

## 3. Hibernate's four strategies: choosing by update frequency and consistency requirements

Hibernate uses `org.hibernate.annotations.Cache` with the `org.hibernate.annotations.CacheConcurrencyStrategy` enum.

| Policy | Allows updating a cached entity? | Core mechanism | Best suited for |
| --- | --- | --- | --- |
| `READ_ONLY` | **No** — intended for immutable data | Simple cache access, does not support updating cached records | Immutable catalogs / reference data that almost never changes |
| `NONSTRICT_READ_WRITE` | **Yes** | No soft locks; invalidation around the time of update | Heavy reads, very rare updates; tolerates a window of stale reads |
| `READ_WRITE` | **Yes** | Uses **soft locks** in the cache while completing updates, so other transactions avoid reading/writing unsafe entries | Mutable entities, not excessively write-heavy, need to reduce stale data risk |
| `TRANSACTIONAL` | **Yes**, if supported by provider | Relies on a **transactional cache provider** integrated with JTA/XA | Systems with coordinated cache–database transactions and genuine provider support |

### 3.1. READ_ONLY — do not use for mutable entities

```java
@Cache(usage = CacheConcurrencyStrategy.READ_ONLY)
```

Intended for objects that do not change. If you attempt to update an entity cached with `READ_ONLY`, Hibernate may throw an exception. Do not pick `READ_ONLY` just for better performance on an entity whose price, status, or quantity can be edited. `@Immutable` (Hibernate) also has its own semantics regarding dirty checking/mutability and should not be added to an entity designed to be written.

### 3.2. NONSTRICT_READ_WRITE — simple but allows a stale window

```java
@Cache(usage = CacheConcurrencyStrategy.NONSTRICT_READ_WRITE)
```

Suitable when updates are very rare and the business **tolerates eventual consistency** over a short window. Hibernate invalidates the entry around the update; because there is no soft-lock mechanism, another transaction may read or populate the cache with a non-latest version while the update is completing. **TTL only limits how long an entry is kept per provider policy**, and does not guarantee a read will see new data immediately after commit.

Acceptable examples: rarely changing secondary display settings that only need to update relatively quickly. Examples to avoid: inventory, balances, payment status, or limits requiring high accuracy.

### 3.3. READ_WRITE — the first option usually considered for mutable entities

```java
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
```

During the completion phase of a modifying transaction, Hibernate uses a **soft lock** (a marker in the cache) to prevent other transactions from reading a stale entry from the cache or putting a potentially stale entry back into the cache. When encountering a soft lock, a reader may **cache miss and query the database**, rather than necessarily blocking like an SQL row lock.

`READ_WRITE` reduces stale cache errors for updates made through Hibernate, but **soft locks are not database locks**, do not replace `@Version`, and do not guarantee `SERIALIZABLE` isolation. According to Hibernate documentation, `READ_WRITE` and `NONSTRICT_READ_WRITE` are incompatible with serializable transaction isolation. If the business requires very strong consistency on write-heavy data, first consider **not using L2 for that entity**.

### 3.4. TRANSACTIONAL — only when infrastructure genuinely supports it

```java
@Cache(usage = CacheConcurrencyStrategy.TRANSACTIONAL)
```

Requires a cache provider supporting **transactional caching** and coordination between cache and database via **JTA/XA** or an equivalent mechanism declared by the provider. Merely switching the enum to `TRANSACTIONAL` does not turn standard Caffeine/Ehcache into an XA cache. In standard Spring Boot + JPA transaction applications (`JpaTransactionManager`) without a compatible transactional cache provider, **do not select** this strategy speculatively.

## 4. Configuring a mutable entity with READ_WRITE

Example of an entity that updates an item's description, with a version column to protect against concurrent overwrites:

```java
package com.example.cache;

import jakarta.persistence.Cacheable;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "inventory_items")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "inventory-items"
)
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private String description;

    protected InventoryItem() {
        // JPA requires a no-arg constructor.
    }

    public InventoryItem(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public String getDescription() {
        return description;
    }

    public void rename(String newDescription) {
        this.description = newDescription;
    }
}
```

In this example:
- `@Cacheable` is the **JPA** annotation indicating the object is eligible for the shared cache depending on cache mode/provider.
- `@Cache(usage = READ_WRITE)` is the **Hibernate** annotation choosing the concurrency policy and the `inventory-items` region.
- `@Version` provides optimistic locking at the **database**, protecting against two updates based on the same data version. It is **different from L2 soft locks**.
- `description` is mutable state; the `rename` method modifies the managed object. Hibernate dirty checking detects and flushes it when a write transaction commits.

Place the Hibernate `@Cache` annotation on the root entity for an inheritance hierarchy; do not arbitrarily place it on subclasses. Adding `@Cache` only declares eligibility: for L2 to run, you must configure a **cache provider** (JCache, Infinispan, or a compatible provider).

## 5. Standalone runnable example: Spring Boot + Hibernate L2 + Caffeine JCache + H2

This example uses **Java 17**, Maven, **Spring Boot 3.5.16**, Spring Boot–managed Hibernate, **Caffeine JCache 3.2.4**, and in-memory H2. The goal is to observe an entity after renaming and measure L2 hits across transactions. This is a **single-JVM learning configuration**; the automatic region creation below lacks memory/TTL limits needed for production.

Structure:

```text
mutable-cache-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cache/
    │   ├── InventoryItem.java
    │   ├── InventoryItemRepository.java
    │   └── CacheDemoApplication.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mutable-cache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-jcache</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>jcache</artifactId>
            <version>3.2.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/com/example/cache/InventoryItem.java`**: use the exact entity code from section 4, with the same `com.example.cache` package.

**`src/main/java/com/example/cache/InventoryItemRepository.java`**

```java
package com.example.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {
}
```

**`src/main/java/com/example/cache/CacheDemoApplication.java`**

```java
package com.example.cache;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            InventoryItemRepository repository,
            PlatformTransactionManager transactionManager,
            EntityManagerFactory entityManagerFactory) {

        return args -> {
            TransactionTemplate tx = new TransactionTemplate(transactionManager);

            Long id = tx.execute(status ->
                    repository.saveAndFlush(new InventoryItem("Old")).getId());

            // Evict L2 right after creation so the first read is a cache miss.
            entityManagerFactory.getCache().evict(InventoryItem.class, id);

            Statistics stats = entityManagerFactory
                    .unwrap(SessionFactory.class)
                    .getStatistics();
            stats.clear();

            // Two different transactions => two different persistence contexts.
            String first = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            String second = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            long l2HitsAfterReads = stats.getSecondLevelCacheHitCount();

            long oldVersion = tx.execute(status ->
                    repository.findById(id).orElseThrow().getVersion());

            tx.executeWithoutResult(status -> {
                InventoryItem managed =
                        repository.findById(id).orElseThrow();
                managed.rename("New");
                // No need to call save: dirty checking runs on transaction commit.
            });

            String afterUpdate = tx.execute(status ->
                    repository.findById(id).orElseThrow().getDescription());

            long newVersion = tx.execute(status ->
                    repository.findById(id).orElseThrow().getVersion());

            System.out.println("first=" + first);
            System.out.println("second=" + second);
            System.out.println("l2HitAfterTwoReads=" + (l2HitsAfterReads > 0));
            System.out.println("afterUpdate=" + afterUpdate);
            System.out.println("versionIncreased=" + (newVersion > oldVersion));
        };
    }
}
```

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:cachedemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=false

spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
spring.jpa.properties.hibernate.javax.cache.provider=com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider
spring.jpa.properties.hibernate.javax.cache.missing_cache_strategy=create
spring.jpa.properties.hibernate.generate_statistics=true
```

**Run:**

```bash
mvn spring-boot:run
```

After the startup logs, the following diagnostic lines appear when the JCache configuration runs properly:

```text
first=Old
second=Old
l2HitAfterTwoReads=true
afterUpdate=New
versionIncreased=true
```

Explanation:

1. The creation transaction saves `Old`; `evict(InventoryItem.class, id)` clears the L2 copy so the experiment starts from a clean state.
2. The first read transaction misses the cache and fetches `Old` from the DB; when eligible, Hibernate puts the data into L2.
3. The second read transaction uses a new persistence context; if the provider works, `getSecondLevelCacheHitCount()` increases. The variable `l2HitsAfterReads` is measured before subsequent read/write transactions so hit counts do not mix.
4. The write transaction loads the managed entity and calls `rename("New")`; on flush/commit, Hibernate updates the DB and the cache region according to `READ_WRITE`.
5. The post-commit transaction sees `New`; `@Version` is incremented when an actual change occurs.

Absolute cache hit/miss/put counts, SQL counts, and log ordering depend on the provider, version, and optimizations; the output above only converts **having at least one hit** into a boolean. If `l2HitAfterTwoReads=false` appears, check the `hibernate-jcache` dependency, provider, region, cache status, and persistence context separation; do not infer L2 solely from the absence of SQL.

**Demo configuration limitation:** `hibernate.javax.cache.missing_cache_strategy=create` allows auto-creating undeclared cache regions; default regions may lack entry count limits and TTL. In production, declare cache regions, size limits, expiry/eviction, and monitoring per provider; consider `missing_cache_strategy=fail` to catch missing region configurations.

## 6. Timeline of modifying an entity with READ_WRITE

```text
TX1: READ Product#10
  EntityManager/L1 miss → L2 hit or DB → managed object

TX2: UPDATE Product#10
  load in L1 → modify property → dirty checking on flush
  → SQL UPDATE (checks @Version if present)
  → commit succeeds
  → Hibernate/provider handles L2 entry using READ_WRITE, soft lock
     and updates/invalidates per the transaction completion cycle

TX3: READ Product#10 after TX2 commits
  New L1 → if L2 is valid, use L2; if miss, SELECT DB
```

Important timing points:
- **Modified but not yet flushed:** the object in L1 has the new value; the database may still hold the old copy.
- **Flush does not equal commit:** SQL may have been sent, yet other transactions are still governed by transaction isolation. Do not use `flush()` as a signal to emit external invalidation events when a write could still roll back.
- **After a successful commit:** only then does Hibernate have grounds to finalize cache synchronization per policy, though there is no absolute guarantee on observation ordering across different systems/instances and different cache mechanisms.
- **Rollback:** DB data is not considered successfully updated; do not design manual cache puts containing uncommitted data.

## 7. @Version protects concurrent updates — not replaced by cache

Suppose two transactions both read `Product#10, version=3`:

```text
TX A                                    TX B
reads version=3                         reads version=3
changes price=120                       changes price=130
UPDATE ... WHERE id=10 AND version=3    —
DB writes price=120, version=4          UPDATE ... WHERE id=10 AND version=3
COMMIT                                  0 rows updated → optimistic locking failure
```

When using `@Version`, Hibernate checks the version during update/flush and detects that the record was modified by another transaction. Spring can translate JPA/Hibernate errors into an `ObjectOptimisticLockingFailureException`; it may surface at `flush` or `commit`. The handling approach is to roll back and reload data so the user/caller can decide to retry or resolve the conflict; **do not blindly retry** a payment transaction.

**`READ_WRITE`'s soft lock** protects the use of an L2 entry during the update window; **`@Version` optimistic locking** prevents overwriting data based on stale versions in the database. The two mechanisms solve two different problems.

## 8. Bulk UPDATE/DELETE, native SQL, and external system changes

### 8.1. JPQL bulk updates do not modify already-managed objects

```java
package com.example.cache;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryItemRepository
        extends JpaRepository<InventoryItem, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update InventoryItem i
           set i.description = :description
         where i.id = :id
        """)
    int bulkRename(
            @Param("id") Long id,
            @Param("description") String description);
}
```

This is an **extended variant of the repository in the demo**; do not add a second interface with the same name to the project. Call `bulkRename` inside a write transaction (e.g., a service annotated with `@Transactional`).

Bulk JPQL runs directly against the database: **it does not invoke setters on entities currently in the persistence context and does not dirty-check individual objects**. `clearAutomatically=true` helps clear potentially stale objects from L1 after the bulk operation; `flushAutomatically=true` flushes pending changes before running the bulk query. Hibernate has an L2/query cache invalidation mechanism for the table space affected by bulk HQL/JPQL, but exact behavior depends on statement type and provider — do not treat it as a synchronization mechanism for all custom caches.

A subtle bug: a bulk JPQL update like the one above **does not automatically increment `@Version`** the way regular managed entity updates do. If the business requires optimistic locking with bulk updates, you must explicitly write the version condition and increment the version, or avoid bulk updates for that flow. Conceptual version-checking example:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update InventoryItem i
       set i.description = :description,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
    """)
int bulkRenameIfVersionMatches(
        @Param("id") Long id,
        @Param("expectedVersion") long expectedVersion,
        @Param("description") String description);
```

Check the `int updated` result: if `0`, either the ID does not exist or the version changed; the application must detect and handle the conflict. **Do not use bulk statements like this concurrently with manual updates on the same row without a clear transaction strategy.**

### 8.2. Native SQL and updates outside Hibernate

SQL statements executed by another JDBC connection, trigger, job, ETL, or another service can modify data **without the current L2 cache knowing**. Hibernate does not automatically detect all out-of-process changes. Hibernate-managed native queries have their own synchronization/invalidation mechanisms, but do not apply that assumption to SQL executed outside Hibernate.

When you know for sure a specific entity has changed **after commit**, you can proactively evict L2:

```java
entityManagerFactory.getCache().evict(InventoryItem.class, itemId);
```

Or clear all data belonging to a class/region via the corresponding API if multiple IDs are affected. **Evicting L2 does not clear L1 objects that are already managed**. When the same `EntityManager` has already read the old object, consider:

```java
entityManager.refresh(managedItem); // reload state from the database
// or entityManager.clear();       // detach all managed entities
```

`refresh` can overwrite unflushed state on that entity; `clear` detaches all entities and unflushed changes may be lost. Only use them when you understand transaction boundaries and managed objects.

The `EntityManagerFactory.getCache().evict(...)` API evicts entries **immediately**; it is not itself a commit/rollback coordination mechanism. If the requirement is "only evict when the update succeeds," publish an event handled **after commit** or use a compatible transaction synchronization mechanism. In multi-node systems, events must reach every instance/provider needing invalidation; local caches on individual JVMs do not synchronize automatically just because of `@Cache(READ_WRITE)`.

## 9. Do Query Cache and Spring Cache need separate updates?

**Hibernate's query cache** is enabled with:

```properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
```

However, this flag **does not cause all queries to be cached**; each query must be marked cacheable (via compatible Hibernate/JPQL hints). Hibernate uses query result regions together with a logical table-update timestamp tracking mechanism, such as internal regions `default-query-results-region` and `default-update-timestamps-region`, to decide which results are stale. Do not configure expiry on the timestamp region in a way that causes timestamp-tracking records to disappear earlier than query results; Hibernate warns that the update timestamps region should not expire/evict under normal policies. Queries with constantly changing parameters or frequently written tables may suffer low hit rates, extra memory consumption, and invalidation overhead.

**Spring Cache** is a separate system. For instance, a service using `@Cacheable("item-view")` to cache DTOs can still return stale DTOs even if Hibernate updated L2 when Spring Cache has not been evicted. You need `@CacheEvict` / cache updates with the right key and at commit time; avoid caching managed entities directly via Spring Cache when objects can be mutated/detached or carry lazy-loading associations. Spring Cache is generally better suited for immutable DTOs with explicit key/TTL/invalidation strategies.

## 10. Process for choosing a safe policy

1. **Determine whether the entity is immutable.** If truly immutable with no update paths, `READ_ONLY` may fit; if updates exist in business logic, do not use it.
2. **Measure read/write ratio and SELECT-by-ID cost.** L2 is most useful for repeated reads by ID across multiple `EntityManager`s with rare writes. If writes are frequent or queries involve varied criteria, L2 benefit may be low.
3. **Determine how much stale data the business tolerates.** No stale data allowed for critical balances/inventory/limits → rely on DB transactions, `@Version`, proper locking, and possibly **do not cache that entity**.
4. **If mutable, not overly write-heavy, and cache coordination is needed on Hibernate updates**, start by evaluating `READ_WRITE` with a supporting provider.
5. **If writes are extremely rare and a short window of stale data is acceptable**, consider `NONSTRICT_READ_WRITE` after concurrency testing.
6. **Only choose `TRANSACTIONAL`** after verifying the provider/transaction manager supports JTA/XA or an end-to-end compatible cache–DB transaction model.
7. **List all write paths:** `save` on managed entities, bulk JPQL, native SQL, batch jobs, other services, and direct database operations. For writes outside Hibernate, design after-commit invalidation or suitable cache TTL/consistency constraints.
8. **Define cache regions:** memory caps, eviction policies, TTL, serializers, monitoring, behavior on node disconnects, post-deploy data compatibility, and multi-node impact.
9. **Test with separate transactions and concurrent updates.** Verify results, version conflicts, hit/miss/put counts, SQL counts, rollbacks, and external writes; do not just run a single read.

## 11. Common pitfalls

| Pitfall | Why it is wrong | Resolution |
| --- | --- | --- |
| Putting `READ_ONLY` on editable items | Strategy treats cached data as immutable | Switch to a write-supporting strategy or remove L2 |
| Having `@Cache` without a provider | Hibernate lacks an L2 backend | Add `hibernate-jcache` and a JCache provider, verify at runtime |
| Calling `findById` twice in one transaction to "prove L2 hit" | Both may use L1 | Read across two separate persistence contexts, enable statistics |
| Using `NONSTRICT_READ_WRITE` when immediate fresh reads are required | Has a stale window due to no soft locks | Use an appropriate consistency level, usually `READ_WRITE` or no cache |
| Assuming soft locks prevent double updates in the DB | Soft locks protect cache entries | Add `@Version` / appropriate DB locks |
| Confusing `flush()` with commit | Flush does not end the transaction | Attach external events/invalidation to **successful commit** |
| Running bulk JPQL then reading stale entities in the same persistence context | Bulk does not sync managed objects | Flush/clear/refresh within safe boundaries |
| Ignoring writers outside Hibernate | L2 is not notified that data changed | After-commit events + evict/refresh/TTL, consider distributed cache |
| Assuming Hibernate L2 syncs Spring `@Cacheable` | Two independent caches | Invalidate the right Spring Cache keys separately |
| Auto-creating unbounded regions | Can cause unbounded memory growth or hard-to-control TTLs | Declare production cache region configs and monitor |
| Using a local cache across multiple instances and assuming cluster consistency | Each JVM can hold different copies | Use a tested cluster/invalidation provider or remove L2 |
| Enabling query cache everywhere | Frequent updates and varying queries degrade cache efficiency | Enable only for stable queries, measure hit rate, preserve timestamp region |

## 12. Comprehension exercises

**Scenario A.** Entity `ExchangeRate` updates every few minutes, APIs read it heavily, and occasionally a brief rate lag is acceptable. Do you choose `NONSTRICT_READ_WRITE` or `READ_WRITE`? What additional conditions are needed?

**Hint:** If staleness is allowed by the business contract and update/conflict frequency is confirmed to be very low, `NONSTRICT_READ_WRITE` can be considered; if minimizing staleness across transactions is preferred, evaluate `READ_WRITE` first. Both still require a provider, TTL/region policy, and testing. For financial transactions applying an exact exchange rate, you may need an explicit snapshot/version rather than relying on the "latest" cache entry.

**Scenario B.** `Product` has `@Cache(READ_WRITE)` and `@Version`, and a separate JDBC cron job updates prices. The API still returns old prices even though each request opens a new transaction. Why?

**Answer:** The job does not notify the L2 cache inside Hibernate; `READ_WRITE` cannot observe external writers. You need after-commit invalidation or another synchronization mechanism; if an independent Spring Cache/Redis is also used, that cache must be evicted too.

**Scenario C.** After `@Modifying @Query("update ...")`, you read the entity again in the same `EntityManager` and see the old value. Where does the root issue lie?

**Answer:** L1/the persistence context holds the old managed object; bulk JPQL does not automatically update these Java objects. Appropriate `refresh`/`clear` is needed, alongside evaluating L2/query cache and version handling.

**Scenario D.** Does configuring `READ_WRITE` + a local cache provider guarantee correctness when three application instances write to the same table?

**Answer:** You cannot assume so. Soft locks/cache regions in local JVMs do not synchronize automatically; you need a suitable cluster provider/architecture, or read from the DB for flows requiring strong consistency. `@Version` still helps protect against lost updates in the DB.

## 13. Key takeaways

- **L1** belongs to `EntityManager`; **L2** belongs to `SessionFactory`/provider; **Query cache** and **Spring Cache** are separate mechanisms.
- **Mutable entities:** `READ_WRITE` is the Hibernate strategy usually evaluated first; `NONSTRICT_READ_WRITE` only when staleness is acceptable; `READ_ONLY` for immutable data; `TRANSACTIONAL` requires genuine infrastructure support.
- Cache soft locks **do not replace** transaction isolation or `@Version`.
- Updates via Hibernate, bulk JPQL, native SQL, and external writers have different invalidation paths.
- Test L2 using **two persistence contexts**, while measuring hits/misses/puts and verifying data **after commit**.

### Official documentation

- Hibernate ORM 6.6 – second-level cache, concurrency strategies, providers, and query cache: https://docs.hibernate.org/orm/6.6/introduction/html_single/#caching
- Hibernate ORM 6.6 – User Guide, Caching section: https://docs.hibernate.org/orm/6.6/userguide/html_single/
- Hibernate ORM – `CacheConcurrencyStrategy` JavaDoc: https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/CacheConcurrencyStrategy.html
- Hibernate JCache – `ConfigSettings` JavaDoc: https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/cache/jcache/ConfigSettings.html
- Spring Boot – Caching reference: https://docs.spring.io/spring-boot/3.5/reference/io/caching.html
