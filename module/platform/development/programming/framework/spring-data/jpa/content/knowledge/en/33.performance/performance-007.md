# Bounding PersistenceContext Size and Application Memory in Spring Data JPA

## Objectives

After this lesson, you will be able to explain why the persistence context grows with the number of loaded entities; distinguish the first-level cache from the second-level cache and application heap; use `flush`, `clear`, and `detach` properly; process write batches with bounded size; read large datasets via DTO projections and keyset pagination; and profile memory to identify exactly where objects are retained.

Examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). Certain batching properties are noted as Hibernate-specific. Code snippets belong to illustrative packages and should be integrated with your application's entities, repositories, and database configuration.

## 1. What Is the Persistence Context?

The persistence context is the working area of an `EntityManager`. It tracks entities in the managed state, maintains an identity map so a given identity within that context is represented by the same object instance, and retains state needed for change detection (dirty checking).

When a query returns entities, they are typically placed into the persistence context. If a job reads hundreds of thousands of entities within the same `EntityManager`, those read entities can remain managed until the context is cleared or the transaction/context ends.

This means `Stream<T>` or row-by-row iteration does not automatically guarantee constant memory. Even without collecting results into a `List`, the persistence context can still hold entities and their snapshots.

JPA refers to the persistence context as the first-level cache. It is scoped to a single `EntityManager` and is not an application-wide shared cache.

## 2. Distinguishing Three Sources of Memory Usage

When investigating heap growth during a JPA task, separate at least three sources:

| Source | Examples of retained objects | Primary control |
| --- | --- | --- |
| Persistence context (first-level cache) | Managed entities, dirty-checking snapshots, and loaded associations | `clear()`, `detach()`, batched transactions, DTO/scalar queries |
| Memory held by application code | Large `List`s, maps, collected DTOs, queues, closures, or static fields | Process in chunks, discard old results, bound queues and reference scope |
| Second-level/query cache and app caches | Shared entity/cache entries, query results, Redis, or custom caches | Configure eviction/TTL/size separately; measure cache hits and capacity |

Clearing the persistence context does not release a `List` your code still holds. Conversely, dropping references to a list does not guarantee entities have left the persistence context.

The second-level cache (if enabled) has a shared scope across `EntityManagerFactory`. `EntityManager.clear()` only detaches entities in the current persistence context; it does not clear the second-level cache. Jakarta Persistence provides `EntityManagerFactory.getCache()` for standard cache operations, while provider or application caches have their own APIs.

## 3. How flush, clear, and detach Differ

These three operations solve different problems:

| API | Effect | Does not mean |
| --- | --- | --- |
| `entityManager.flush()` | Synchronizes pending changes from the persistence context to the database within the current transaction | Commits the transaction or frees entities from memory |
| `entityManager.clear()` | Detaches all managed entities in the persistence context | Removes objects from application collections/variables or clears the second-level cache |
| `entityManager.detach(entity)` | Detaches one specific entity | Detaches related entities or clears references to the object |

### 3.1. Flush Is Not Commit

`flush()` tells JPA to emit the SQL statements needed to synchronize managed state with the database. The transaction remains open; changes are not yet committed and can still be rolled back.

Flushing can cause the database to check constraints or raise SQL errors earlier than commit time. It can also cause database locks to be held longer until the transaction finishes.

### 3.2. Clear Detaches All Managed Entities

`clear()` turns managed entities in the persistence context into detached entities. Unflushed changes on those entities will no longer be synchronized automatically by dirty checking. Therefore, in write batches, the standard order is:

```java
entityManager.flush();
entityManager.clear();
```

Flush first to send the current batch's changes to the database; clear afterward so the persistence context does not keep retaining that batch's entities.

Do not call `clear()` before `flush()` if pending changes need to be saved. After `clear()`, Java objects may still exist in variables or collections, but they are detached and no longer tracked automatically by JPA.

### 3.3. Detaching Individual Entities

When you only need to stop tracking one object, call:

```java
entityManager.detach(customer);
```

The entity must belong to the current persistence context. Related entities are not automatically detached with it. This is useful when processing isolated objects, though for large batches, periodic `clear()` is usually easier to manage. Be careful if lazy associations still need loading or the entity needs updating after detachment.

## 4. Why Write Batches Need flush and clear

Consider a loop creating and persisting 100,000 entities in one transaction without clearing:

```java
for (ImportRow row : rows) {
    entityManager.persist(new Customer(row.email(), row.name()));
}
```

New entities stay managed in the persistence context. Hibernate also keeps tracking state to handle flushing. As the count grows, heap usage and dirty-checking time can increase dramatically.

You can split work into fixed-size groups, such as 500 entities per batch:

```java
private static final int BATCH_SIZE = 500;

public void persistRows(Iterator<ImportRow> rows) {
    int count = 0;

    while (rows.hasNext()) {
        ImportRow row = rows.next();
        entityManager.persist(
            new Customer(row.email(), row.name())
        );
        count++;

        if (count % BATCH_SIZE == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

This snippet illustrates the processing body inside a transactional service. `Iterator<ImportRow>` must stream or chunk data; if `rows` comes from a `List` holding an entire file, that input list itself still occupies memory.

### 4.1. Example Service Writing a Chunk

Minimal entity and input record:

```java
package com.example.learning.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SequenceGenerator(name = "customer_seq_gen", sequenceName = "customer_seq", allocationSize = 50)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "customer_seq_gen")
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getName() { return name; }
}
```

```java
package com.example.learning.customer;

public record ImportRow(String email, String name) {
}
```

Writer accepting a bounded chunk:

```java
package com.example.learning.customer;

import java.util.List;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerBatchWriter {
    private static final int BATCH_SIZE = 500;

    private final EntityManager entityManager;

    public CustomerBatchWriter(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void writeChunk(List<ImportRow> chunk) {
        if (chunk.size() > BATCH_SIZE) {
            throw new IllegalArgumentException("chunk exceeds batch size");
        }

        for (ImportRow row : chunk) {
            entityManager.persist(new Customer(row.email(), row.name()));
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

The caller sends a bounded `chunk`. `@Transactional` defaults to `REQUIRED` propagation. When `writeChunk` is called through the Spring proxy from another bean and no transaction is active, Spring opens a transaction for the call; if the coordinator already has an active transaction, the method joins the existing transaction. Therefore, with default propagation, a chunk commits independently only when the coordinator has no active transaction while calling `writeChunk` (typically the coordinator is not annotated with `@Transactional` and is not called from a transactional caller). After `flush()`/`clear()`, the writer-opened transaction commits when the method finishes normally and is not marked rollback-only.

In cases where the coordinator must maintain an outer transaction yet each chunk requires its own transaction, you can place `@Transactional(propagation = Propagation.REQUIRES_NEW)` on `writeChunk` (importing `org.springframework.transaction.annotation.Propagation`). Spring suspends the outer transaction, opens a new transaction for the chunk, and resumes the outer transaction after the chunk commits/rolls back. This means committed chunks persist even if the outer transaction rolls back; the inner transaction also cannot see uncommitted changes from the outer transaction. The outer transaction may keep holding a connection while the inner transaction needs another connection, increasing connection pool pressure and the risk of waiting for connections. Only use `REQUIRES_NEW` when the atomicity, visibility, and connection resource trade-offs are acceptable.

To process a large file, a job coordinator can read 500 rows, call `writeChunk(chunk)`, drop the reference to `chunk`, and read the next group. That way, the input chunk, persistence context, and transaction all have clear bounds.

The sequence generator in this example requires the database to have a `customer_seq` sequence or a schema migration creating it. With Hibernate, the IDENTITY strategy usually restricts JDBC insert batching because IDs must be retrieved after each insert. If using a database without sequences, pick a suitable ID strategy and verify the provider's batching capabilities.

If the entire import must be atomic, splitting transactions into chunks changes semantics: one chunk can commit before a later chunk fails. When all-or-nothing is required, weigh a larger transaction with memory limits, or design a staging table/status tracking to support resume and compensation.

### 4.2. Flush/clear in a Long Transaction Does Not End the Transaction

Calling `flush()` and `clear()` periodically bounds the persistence context, but the transaction can still span from start to finish of the job. The database may continue holding locks, undo/version data, and a connection throughout that duration.

For very large jobs, per-chunk transactions are often easier to operate. Place `@Transactional` on a dedicated writer bean and invoke it from a separate coordinator bean so the call passes through the proxy; with default `REQUIRED` propagation, the coordinator must have no active transaction for each chunk to commit independently. If the coordinator or caller already has a transaction, the writer joins it; when separate transactions are needed, use `REQUIRES_NEW` only after weighing the trade-offs in section 4.1. Avoid self-invocation because internal calls can bypass the transactional proxy.

## 5. Configuring Hibernate JDBC Batching

`flush()` and `clear()` control the persistence context. JDBC batching is a separate mechanism: Hibernate groups compatible statements into batches sent over JDBC to reduce round trips.

Example Hibernate settings in `application.properties`:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

`hibernate.jdbc.batch_size` is Hibernate-specific. `order_inserts` and `order_updates` help group identical statement types for more effective batching, though they can alter SQL execution order; verify constraints and business ordering before enabling them.

JDBC batching and persistence context batching are separate concerns. Setting JDBC batch size to 50 while keeping 100,000 entities managed still lets the persistence context grow huge. Conversely, flushing/clearing every 500 entities does not ensure the driver actually batches SQL if Hibernate/JDBC batching is unconfigured.

With Hibernate, `IDENTITY` ID generation typically disables JDBC insert batching because IDs must be fetched per insert. For large batch inserts, consider sequence-based IDs when supported by the database/provider and configure appropriate sequence allocation.

Do not assume Hibernate properties take effect on other JPA providers. Verify your application's actual provider.

## 6. Do Not Hold Both Input and Output in Memory

Even when the persistence context is cleared properly, application code can still inflate the heap by holding large collections:

```java
List<Customer> all = repository.findAll();
List<CustomerDto> result = all.stream()
    .map(CustomerDto::from)
    .toList();
```

In this example, both the entity list and the DTO list can coexist on the heap. On large datasets, avoid `findAll()` followed by converting everything into another list.

Better approaches:

- Read one chunk, process it, write output, and drop references before reading the next chunk.
- Use DTO projections so the database returns only needed columns.
- Stream results directly to a file or an output sink with backpressure instead of collecting everything.
- Bound queues between producers and consumers; an unbounded queue just moves the memory problem elsewhere.
- Do not retain processed entities/DTOs in maps or caches unless the use case requires it.

## 7. Reading Large Datasets via Projections and Keyset Pagination

For read-only tasks, DTO projections are usually better than entities because DTO results do not become managed entities in the persistence context.

DTO:

```java
package com.example.learning.customer;

public record CustomerExportRow(Long id, String email, String name) {
}
```

Repository using a JPQL constructor expression:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Query("""
        select new com.example.learning.customer.CustomerExportRow(
            c.id, c.email, c.name
        )
        from Customer c
        where c.id > :afterId
        order by c.id asc
        """)
    List<CustomerExportRow> findNextExportBatch(
        @Param("afterId") Long afterId,
        Pageable pageable
    );
}
```

The caller requests up to 500 rows per call via `PageRequest.of(0, 500)`, processes the list, and updates `afterId` to the last ID. The `id > :afterId` predicate combined with ordering by `id` implements keyset pagination, avoiding increasing offset costs on deep pages and reducing the risk of skipped/duplicated rows caused by inserts before the offset.

Keyset pagination needs a deterministic order with a unique tie-breaker. If sorting by `createdAt`, append `id` to the sort order and include both values in the continuation predicate. Data modified while a job runs still needs a consistency policy, such as snapshots/versions, time cutoffs, or job statuses.

### 7.1. Reading Each Chunk in Its Own Transaction

You can place the read query in a separate service:

```java
package com.example.learning.customer;

import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportReader {
    private final CustomerRepository customers;

    public CustomerExportReader(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public List<CustomerExportRow> nextChunk(long afterId) {
        return customers.findNextExportBatch(
            afterId, PageRequest.of(0, 500)
        );
    }
}
```

The coordinator calls `nextChunk` via the bean proxy, processes the chunk, and discards the list before fetching the next chunk. Because the method returns DTOs, the persistence context does not have to retain managed `Customer` entities just for export. If entities were used instead of DTOs, ending the transaction detaches them, though the returned list still holds objects on the heap until the caller drops references.

Avoid offset pagination with unstable ordering. If records are inserted or deleted while a job is running, offsets can skip or duplicate rows. Keyset pagination fits well when a monotonic sort key or stable cursor exists.

## 8. Stream<T> Does Not Automatically Bound the PersistenceContext

Spring Data JPA can return `Stream<T>` from a repository, but distinguish carefully:

- Java Stream allows sequential result consumption.
- JDBC fetch size provides a hint for how many rows the driver retrieves per round-trip.
- The persistence context may still retain hydrated entities.

Thus, streaming entities across hundreds of thousands of records can still bloat the first-level cache. Streams must be consumed inside an open transaction and closed with `try-with-resources`:

```java
public interface CustomerStreamRepository extends JpaRepository<Customer, Long> {
    Stream<Customer> findAllByOrderByIdAsc();
}
```

```java
@Transactional(readOnly = true)
public void exportEmails(Consumer<String> sink) {
    try (Stream<Customer> stream = repository.findAllByOrderByIdAsc()) {
        stream.map(Customer::getEmail).forEach(sink);
    }
}
```

This service snippet requires importing `java.util.stream.Stream` and `java.util.function.Consumer`. It demonstrates transaction/resource management; it does not guarantee constant heap usage.

Fetch size is a hint to the JDBC driver, not a cap on entities inside the persistence context. Check your provider, driver, and database. For large reads, DTO projections combined with chunked keyset/page reads are usually easier to bound in memory than entity streams.

If you plan to call `EntityManager.clear()` while iterating an entity stream, test thoroughly with your specific provider/driver: clearing detaches all managed entities and can break lazy loading or remaining processing logic. Do not apply this pattern mechanically.

## 9. Lazy Associations and N+1 Also Consume Memory

When accessing lazy associations on each entity, the ORM may emit extra queries and populate additional entities/collections inside the persistence context. For instance, reading each customer and accessing orders can trigger N+1 queries and enlarge the context.

If only a few attributes from a relationship are needed, prefer a DTO query with explicit join/select. If an entity graph is needed, bound chunk row counts and monitor query counts. Batch fetching (`hibernate.default_batch_fetch_size` or `@BatchSize` in Hibernate) can reduce round trips when loading associations, but it does not cap persistence context size.

## 10. Second-Level Cache Is Not the PersistenceContext

The first-level cache is mandatory in the EntityManager model and scoped to one persistence context. The second-level cache is optional, shared across `EntityManagerFactory`, and managed by the provider.

`entityManager.clear()` detaches entities in the current first-level cache. It does not remove shared cache entries. Jakarta Persistence provides `entityManagerFactory.getCache().evict(...)` and `evictAll()`; these operations affect the shared cache and should only be used for clear reasons.

Caching does not replace application heap control. Even a size/TTL-bounded cache consumes memory; monitor capacity and evictions per its configuration.

## 11. Common Mistakes

- **Assuming `Stream<T>` alone bounds memory.** Entities can still remain retained in the persistence context.
- **Calling `flush()` without `clear()`.** SQL is synced, but entities remain managed and keep occupying heap.
- **Calling `clear()` before flushing.** Pending changes can be lost from dirty checking; flush first if they must be saved.
- **Thinking `clear()` removes all objects from the heap.** Lists, maps, DTOs, and application variables still hold references.
- **Calling `saveAll()` with a giant collection.** Both input and returned results can retain many objects; split into bounded chunks.
- **Configuring JDBC batching without clearing the persistence context.** JDBC batching does not limit managed entity counts.
- **Clearing while lazy loading is still needed.** Entities become detached and associations may fail to load.
- **Using a single transaction for an hours-long job.** Flush/clear does not end the transaction or release locks.
- **Using deep offset pagination or unstable sorting.** Prefer keyset pagination with unique ordering where applicable.
- **Confusing batch fetching with persistence context bounding.** Batch fetching reduces round trips; it does not cap retained entities.
- **Evicting the second-level cache to fix first-level cache growth.** Both caches have different scopes and management APIs.
- **Holding processed results in unbounded queues.** Use bounded queues and backpressure.

## 12. Measuring and Diagnosing Memory

Do not pick a batch size by guesswork. Measure on production-like data:

1. Record heap before, during, and after each batch; watch post-GC trends.
2. Use Java Flight Recorder (JFR), heap dumps, or Memory Analyzer to identify object types and retaining reference paths.
3. Check managed entity counts, query counts, lazy loads, collections, and persistence context size if provider statistics expose them.
4. Observe GC pauses, allocation rates, old-generation occupancy, and processing time per batch.
5. Monitor connection pools, transaction durations, and lock waits; optimizing heap must not cause transactions to hold connections too long.
6. Change one factor at a time—batch size, projection, fetch size, or transaction chunk—and compare results.

With Hibernate, you can enable statistics in test/measurement environments using `hibernate.generate_statistics=true` and read `SessionFactory` statistics. Avoid leaving verbose SQL logging/statistics on continuously in production if overhead or log volume is excessive.

Smaller batch sizes increase flush/round-trip frequency while reducing concurrently held entities. Larger batch sizes reduce database call overhead while increasing heap usage and flush time. Choose values based on entity size, associations, driver, database, and heap limits.

## 13. When Should You Use Hibernate StatelessSession?

Hibernate provides `StatelessSession` as a separate API for bulk processing that needs little persistence context functionality. It is not a standard Jakarta Persistence API and lacks the first-level cache, dirty checking, cascades, lifecycle callbacks, and identity management of a regular `Session`.

`StatelessSession` can fit specialized imports/exports once semantic differences have been evaluated. Do not replace EntityManager with this API solely to shrink heap if business logic depends on cascades, entity lifecycles, or association management.

## 14. Checklist Before Deploying Large-Data Jobs

- [ ] Identify whether heap growth stems from the persistence context, application collections, or shared caches.
- [ ] Choose entities or DTO projections based on processing requirements.
- [ ] Set size bounds on input/output chunks.
- [ ] For write batches, flush then clear after each bounded group.
- [ ] Ensure changes needing persistence are flushed before clearing.
- [ ] Configure JDBC batching separately if using Hibernate and measure real effectiveness.
- [ ] Decide between whole-job or per-chunk transactions based on atomicity/resume requirements.
- [ ] For large reads, use keyset or deterministic paging; avoid collecting all results.
- [ ] Do not assume Stream or fetch size automatically bounds the first-level cache.
- [ ] Check lazy loading, N+1, and associations retained in context.
- [ ] Bound queues/caches and drop references after processing each chunk.
- [ ] Measure heap, GC, transaction duration, connection pool, and throughput under realistic load.

## Conclusion

The persistence context can grow with every loaded entity, even when code processes rows sequentially. `flush()` synchronizes changes to the database without releasing entities; `clear()` detaches all managed entities; `detach()` stops tracking a single entity. For large writes, split input into chunks, flush then clear, and consider per-chunk transactions. For large reads, DTO projections paired with keyset pagination usually control memory better than retaining entities or collecting full result sets. Finally, distinguish the first-level cache, second-level cache, and application-held collections, then profile heap/GC to locate the true source of memory consumption.