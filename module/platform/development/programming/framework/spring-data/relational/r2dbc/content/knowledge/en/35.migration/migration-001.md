# Assessing a JDBC/JPA Application Before Migrating to R2DBC

## 1. Why Assess Before Migrating?

Migrating an application from JDBC or JPA to Spring Data Relational R2DBC is a change in data access architecture, not merely replacing a dependency or swapping a repository interface. JDBC uses a blocking I/O model; R2DBC provides a database access API based on Reactive Streams. JPA also adds an ORM model with a persistence context, dirty checking, lazy loading, cascades, and numerous entity management mechanisms.

An application can run well on JDBC/JPA for many years. If the workload is not constrained by threads waiting on the database, if the team does not need end-to-end reactivity, or if the application relies heavily on ORM features, migrating to R2DBC may increase complexity without delivering commensurate benefits.

A pre-migration assessment helps answer:

- Does the current problem actually stem from JDBC's blocking model?
- Is the application using JPA features for which R2DBC does not provide an equivalent?
- Can existing queries, transactions, locking, and batch operations be expressed with R2DBC?
- Do non-database libraries support reactive programming, or are they still blocking?
- Does the team have the capability to design, operate, and debug reactive pipelines?
- Which parts should be migrated, and which parts should remain on JDBC/JPA?
- Can it be rolled out incrementally by use case without disrupting the system?

The assessment outcome does not have to be “migrate everything.” You may choose to migrate certain flows with clear benefits, keep reporting or batch flows on JDBC, or hold off on migrating if the benefits do not outweigh the costs.

## 2. Distinguishing JDBC, JPA, and R2DBC

These technologies address different layers of concerns:

| Technology | Primary Role | Characteristics |
|---|---|---|
| JDBC | Standard Java database access API | Blocking; operations typically wait for results on the calling thread |
| JPA | ORM and persistence management specification | Typically runs on top of JDBC; has persistence context, dirty checking, entity lifecycle, and relationship mapping |
| Spring Data JPA | Repository abstraction over JPA | Provides repositories, query derivation, and integration with EntityManager |
| R2DBC | Reactive database access SPI | Non-blocking API based on Publisher |
| Spring Data R2DBC | Reactive relational mapping and repositories | Uses ConnectionFactory, MappingR2dbcConverter, DatabaseClient, and R2dbcEntityTemplate |

JPA is not a database driver. A Spring Data JPA application typically uses Hibernate or another provider on top of JDBC. When migrating to Spring Data R2DBC, the application usually drops the EntityManager/JPA model and works more directly with relational mapping.

This means there is no one-to-one replacement for every JPA behavior. R2DBC does not automatically provide a JPA-style persistence context, lazy-loading proxies, dirty checking, or automatic cascade operations across an object graph.

If the application only uses JdbcTemplate or JDBC DAOs, the assessment focuses more on blocking calls, transactions, SQL, row mapping, batching, and connection lifecycle. If the application uses JPA heavily, you also need to inventory ORM semantics and provider-dependent behaviors.

## 3. What Problems Does R2DBC Solve?

Blocking JDBC can hold a thread while waiting for the database to return results. In applications with high concurrency, thread count and stack memory can grow with the amount of work waiting on I/O. Connection pools and thread pools must be configured to avoid resource exhaustion.

R2DBC allows the application to dispatch database operations and continue processing signals when results are ready, without holding a blocking thread for each I/O wait. This model fits applications already using a reactive stack such as WebFlux, Reactor, and Reactive Streams.

R2DBC can be useful when:

- There are many concurrent requests and most time is spent waiting on the database/network.
- The application needs to stream data with backpressure.
- The HTTP, messaging, and downstream stack is already reactive.
- Thread blocking is a measured and proven bottleneck.
- The database's R2DBC driver supports the required features.
- The team can properly maintain reactive code.

R2DBC does not make SQL queries faster by itself. The database still executes queries, checks constraints, acquires locks, and reads/writes storage as before. A slow query remains slow; a transaction holding a connection too long still puts pressure on the pool. If the application is bound by CPU, missing indexes, poor queries, or database saturation, switching drivers will not solve the root cause.

## 4. Start with Goals and a Baseline

Before evaluating code, define the business or operational problem the migration needs to solve. Avoid starting with vague goals like “we want to use reactive.”

Questions to answer:

- What are the average and peak request rates?
- What are the current concurrent request counts and p95/p99 latencies?
- How much request time is spent inside database calls?
- Is the thread pool exhausted, or are many threads waiting on JDBC?
- Does the connection pool experience pending acquires or timeouts?
- What are the database CPU, memory, I/O, and active session levels?
- Are there other I/O operations such as HTTP, Redis, Kafka, or files?
- Which parts of a request are CPU-bound and which are I/O-bound?
- Is the post-migration goal to increase concurrency, reduce resource usage, improve tail latency, or unify a reactive stack?

Establish a baseline before making changes:

| Category | Metrics to Collect |
|---|---|
| HTTP/API | Request rate, p50/p95/p99, error rate |
| JVM | Thread count, heap, GC pause, CPU |
| JDBC pool | Active, idle, pending, acquire latency, timeout |
| Database | Active sessions, query latency, CPU, I/O, lock wait |
| Query | Slow queries, rows read/returned, execution plans |
| Transaction | Duration, rollback rate, lock duration |
| Batch | Batch size, throughput, completion time |

The baseline must be measured with a representative workload over a sufficiently long period. Without pre-migration metrics, it will be hard to prove what R2DBC improved after deployment.

## 5. Inventory Database Access Points

Create a list of all database access components, not just repository interfaces.

Sources to search in the codebase:

- Spring Data JPA repositories.
- EntityManager and Criteria API.
- JdbcTemplate and NamedParameterJdbcTemplate.
- JdbcClient in supported Spring versions.
- DataSource and DriverManager.
- Hibernate Session, query APIs, or native SQL.
- Stored procedures and functions.
- Batch updates/inserts.
- Direct JDBC in internal libraries.
- Database access inside schedulers, listeners, and background workers.
- Transaction managers and transaction annotations.
- Migration tools and schema initializers.

You can categorize by module/use case:

| Module | Current Technology | Queries/Flows | Complexity | Criticality |
|---|---|---:|---|---|
| Customer API | Spring Data JPA | 18 | Medium | High |
| Reporting | JdbcTemplate/native SQL | 30 | High | Medium |
| Import worker | JDBC batch | 5 | High | High |
| Reference data | Spring Data JPA | 6 | Low | Low |

This table is only an inventory sample. Document key queries, call frequency, row counts, transaction boundaries, and database features in use.

Do not judge difficulty solely by the number of repository methods. One method using complex native SQL or relying on locking can be harder to migrate than dozens of CRUD methods.

## 6. Inventory JPA Features in Use

If the application uses JPA, review the following features:

| JPA Feature | Questions to Ask When Migrating to R2DBC |
|---|---|
| Persistence context | Does the code rely on EntityManager tracking entities? |
| Dirty checking | Does it modify properties and expect automatic UPDATE on commit? |
| Lazy loading | Does it access associations after querying an entity? |
| Eager relationship | Does it rely on automatic fetching to load an object graph? |
| Cascade | Does it save/delete an object graph in a single operation? |
| Orphan removal | Does it rely on removing items from a collection to delete rows? |
| Entity lifecycle callback | Does it use @PrePersist, @PostLoad, or listeners? |
| Auditing | Does it use Spring Data JPA auditing listeners/providers? |
| Entity graph | Does it use @EntityGraph or fetch plans? |
| JPQL/HQL | Does it query based on entity names and associations? |
| Criteria API/Specification | Does it build dynamic queries based on the JPA object model? |
| Pessimistic/optimistic locking | Does it use LockModeType or @Version? |
| First-level cache | Does it rely on the same entity instance within a persistence context? |
| Second-level/query cache | Does it use Hibernate caching? |
| Inheritance mapping | Does it use JOINED, SINGLE_TABLE, or TABLE_PER_CLASS? |
| Embedded/value mapping | Does it use @Embedded, @ElementCollection, or complex converters? |

Not every feature has a direct equivalent in Spring Data R2DBC. Some must be rewritten into explicit SQL, service orchestration, or a different schema/domain design.

If a use case relies heavily on persistence context, lazy loading, and cascades, the migration cost may be high. Prototype that use case before committing to a broad migration.

## 7. Persistence Context and Dirty Checking

JPA's EntityManager maintains a persistence context. Entities loaded in the context can be tracked; when properties change, the provider detects the changes and generates an UPDATE on flush or commit.

JPA example:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Dirty checking may issue an UPDATE on flush/commit.
}
~~~

Spring Data R2DBC does not have a JPA-style persistence context to track every read object. Modifying an object in memory does not automatically write to the database.

With R2DBC, write operations usually must be expressed explicitly:

~~~java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .map(customer -> customer.withName(newName))
            .flatMap(customerRepository::save);
}
~~~

With an immutable entity, `withName` creates a new instance. The service calls `save` to issue the UPDATE. This is an important shift in mindset: reading an entity does not register it in a change-tracking context.

During the assessment, look for service methods that only mutate properties without explicitly calling `save`/`merge`/`update`. They will not preserve the same behavior when migrated to R2DBC.

## 8. Lazy Loading and Object Graphs

JPA can use proxies or collection wrappers to load associations when code accesses them. A snippet of code may look simple:

~~~java
@Transactional
public CustomerProfile getProfile(Long id) {
    Customer customer = customerRepository.findById(id).orElseThrow();
    List<Address> addresses = customer.getAddresses();
    return new CustomerProfile(customer, addresses);
}
~~~

If `addresses` is LAZY, calling the getter can trigger an additional query while the persistence context is open. This sometimes creates N+1 queries that are not obvious from the code.

R2DBC does not provide lazy-loading proxies for associations like JPA does. The application must decide what data to fetch and compose publishers/queries explicitly.

Example:

~~~java
public Mono<CustomerProfile> getProfile(Long id) {
    return customerRepository.findById(id)
            .flatMap(customer ->
                    addressRepository.findByCustomerId(id)
                            .collectList()
                            .map(addresses ->
                                    new CustomerProfile(customer, addresses)
                            )
            );
}
~~~

If two round-trips need to be avoided, a JOIN and an appropriate projection can be used. For one-to-many relationships, you must handle a customer appearing across multiple rows and group the data properly.

In the assessment, list current associations and fetch strategies. Record which endpoints need which object graphs, the number of queries generated, and the data actually returned. This serves as input for designing R2DBC queries rather than blindly translating a JPA entity graph into a chain of publishers without examining N+1 and data volume.

## 9. Cascade, Orphan Removal, and Entity Relationships

JPA can automatically cascade persist, merge, remove, or handle orphan removal according to mappings. R2DBC does not automatically orchestrate object graphs using JPA cascade semantics.

For example, JPA may save an aggregate with cascade:

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines;
~~~

When migrating to R2DBC, you must explicitly determine:

- Save the order first or order lines first?
- How is the generated ID of the order used?
- If an order line fails, should the whole operation roll back?
- When removing a line from the collection, must the row be deleted?
- When deleting an order, in what order must child rows be deleted?
- Which parts are handled by foreign keys and ON DELETE CASCADE?

An explicit implementation:

~~~java
public Mono<Order> saveOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved ->
                    orderLineRepository.deleteByOrderId(saved.id())
                            .thenMany(
                                    orderLineRepository.saveAll(
                                            order.lines().stream()
                                                    .map(line -> line.withOrderId(saved.id()))
                                                    .toList()
                                    )
                            )
                            .then(Mono.just(saved))
            );
}
~~~

This example needs to be wrapped in a transaction if business requirements demand saving the order and lines atomically. It illustrates explicit orchestration, not the only or optimal approach for every aggregate.

Evaluate existing cascade mappings and define the corresponding behavior in the service, SQL constraints, or stored procedures. Do not assume that removing JPA annotations means the database will automatically perform the same logic.

## 10. Query Inventory: JPQL, Criteria, Specification, and Native SQL

Categorize existing queries:

1. Derived query methods.
2. JPQL/HQL.
3. Criteria API or Specifications.
4. Native SQL.
5. Stored procedures/functions.
6. Dynamically built queries for filtering/sorting.
7. Pagination and aggregation queries.
8. Queries using locking or provider hints.

JPQL example:

~~~java
@Query("""
       select c
       from Customer c
       where c.status = :status
       order by c.createdAt desc
       """)
List<Customer> findRecentByStatus(String status);
~~~

When migrating to R2DBC, queries usually need to be written against table/column names and the SQL dialect:

~~~java
@Query("""
       SELECT id, name, status, created_at
       FROM customers
       WHERE status = :status
       ORDER BY created_at DESC
       """)
Flux<Customer> findRecentByStatus(String status);
~~~

Verify:

- Table/column names after Hibernate's naming strategy.
- Aliases and result mapping.
- Bind parameters and data types.
- Null semantics.
- Pagination syntax.
- Whether sorting is allowlisted.
- Whether the query uses database-specific functions.
- Whether results can be large enough to require streaming.

Do not mechanically translate JPQL by replacing entity names with table names. JPQL operates on the entity model; SQL operates on the relational schema. Association paths, inheritance, embedded fields, and functions may need to be rewritten.

### 10.1. Criteria API and Specification

JPA Criteria/Specification can construct dynamic queries using the entity metamodel. Spring Data R2DBC does not provide the same JPA Specification mechanism. R2dbcEntityTemplate has its own Criteria API for building relational conditions, but it is not a clone of JPA Criteria.

Inventory the number of filters, joins, sorts, and optional conditions. If queries are simple, they can be migrated to query methods or R2DBC Criteria. If queries are complex, consider DatabaseClient with explicit SQL and DTO mapping.

For dynamic sorting, allow only column names from a predefined list. Never concatenate user input directly into SQL identifiers.

## 11. Native SQL, Stored Procedures, and Database-Specific Features

Native SQL is often underestimated during migration. Queries may use:

- Window functions.
- CTEs and recursive CTEs.
- JSON/JSONB operators.
- Array operators.
- Full-text search.
- Partial indexes.
- Upserts and conflict handling.
- RETURNING or generated keys.
- Vendor-specific hints.
- Stored procedures, functions, and triggers.
- Temporary tables or session variables.

Group queries by database engine and flag dialect-dependent parts. The R2DBC driver must support the required database and data types; Spring Data cannot make a SQL feature portable if the engine does not support it.

If stored procedures are core to business logic, prototype calling procedures with the R2DBC API/DatabaseClient and verify results, parameter modes, transactions, and driver behavior. Do not assume every JDBC CallableStatement pattern has a direct drop-in replacement in R2DBC.

## 12. Transaction Boundaries and Propagation

JPA applications typically use `@Transactional` with `PlatformTransactionManager`/`JpaTransactionManager`. When migrating to R2DBC, the transaction manager is reactive and transaction context is propagated via the Reactor Context.

Questions to inventory:

- Do transactions start at the controller, service, or repository?
- Does a use case call multiple repositories?
- Are there multiple DataSources or databases?
- Are HTTP/message broker calls made inside a transaction?
- Is REQUIRES_NEW, NESTED, or read-only propagation used?
- Are specific transaction timeouts or isolation levels used?
- Does imperative code call reactive transactional methods?
- Is there self-invocation causing Spring proxies not to be applied?

Reactive transaction example:

~~~java
@Transactional
public Mono<Order> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(toLines(order.id(), command))
                            .thenReturn(order)
            );
}
~~~

Or use `TransactionalOperator` to express boundaries with publishers.

Never mix imperative and reactive transactions and assume they share the same context. `JpaTransactionManager` does not manage an R2DBC `ConnectionFactory`. If an atomic transaction across both JDBC/JPA and R2DBC is required, do not assume it can be achieved simply by putting both calls in one `@Transactional` method. Usually you must separate transactions, use outbox/saga, or keep the same data access technology within the boundary that needs atomicity.

## 13. Locking and Concurrency Control

JPA supports optimistic locking via `@Version` and EntityManager lock modes. Spring Data R2DBC can support optimistic locking via a version property in mapping, but semantics and queries must be verified for the specific version and driver. There is no automatic replacement for all JPA lock modes.

JPA example:

~~~java
@Version
private Long version;
~~~

When migrating, check:

- Does the version column exist with the right type?
- Does the UPDATE include a condition on the old version?
- When no rows are updated, how is the optimistic locking error represented?
- Does the service retry on conflict?
- Are PESSIMISTIC_WRITE or SELECT FOR UPDATE used?
- Are locking queries supported by the R2DBC dialect/driver?
- Do concurrent transactions preserve the same semantics?

Build integration tests against the actual production database for critical concurrency flows. A sequential test on H2 does not prove production deadlock, lock wait, or isolation behavior.

If existing code relies on pessimistic locking to protect inventory, balances, or quotas, this is a high migration risk. Prototype it before committing to a full migration.

## 14. Batch Processing and Bulk Operations

JDBC/JPA has many batch mechanisms, though effectiveness depends on the provider, JDBC driver, flush/clear strategy, and database. An application may use:

- Hibernate JDBC batching.
- `saveAll` on repositories.
- `JdbcTemplate` `batchUpdate`.
- Batch insert/update.
- Bulk JPQL UPDATE/DELETE.
- Large imports/exports.
- Scheduled jobs processing many rows.

R2DBC supports batch/statements through its SPI and drivers, but not every `saveAll` call produces a single bulk statement. Multiple statements may be sent over a publisher.

Measure:

- Batch size.
- Number of round-trips.
- Generated key behavior.
- Memory retained by entities.
- Transaction duration.
- Lock contention.
- Throughput and error recovery.
- Ability to resume after mid-batch failures.

For large datasets, split batches, use checkpoints, and ensure idempotency. Do not convert a JDBC batch job into a very high-concurrency `Flux.flatMap` without checking database capacity.

If existing batch jobs leverage Hibernate/JDBC-specific optimizations and are not a thread bottleneck, you can keep those batch jobs on JDBC while migrating interactive APIs to R2DBC.

## 15. Generated IDs, Sequences, and Entity Mapping

JPA providers offer many ID generation strategies: IDENTITY, SEQUENCE, TABLE, or custom generators. Spring Data R2DBC has its own mapping metadata and dialects for working with generated values, but it does not share Hibernate's extensive generator system.

Inventory:

- `@GeneratedValue` strategies.
- Sequence names and allocation sizes.
- Triggers generating IDs.
- Composite keys.
- UUID generators.
- Application-assigned IDs.
- IDs returned after INSERT.
- Whether entities use constructor mapping or property access.

Prototype each strategy against a real database. Test single-row inserts, batch inserts, and generated values immediately used to save child tables.

Beyond IDs, check `@Embedded`, `@ElementCollection`, inheritance mapping, enums, converters, JSON types, and naming strategies. Spring Data R2DBC mapping is simpler than JPA, but it requires clear schema/row mapping.

## 16. Auditing, Lifecycle Callbacks, and Events

JPA may use `@PrePersist`, `@PreUpdate`, `@PostLoad`, `EntityListener`, or Spring Data auditing. When migrating to R2DBC, determine which callbacks belong to the entity lifecycle, which are business logic, and which trigger side effects.

Spring Data R2DBC has `EntityCallback` types such as `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, and `AfterConvertCallback`. Auditing can also be configured for R2DBC. However, do not assume JPA listeners will be invoked or run in the same order after migration.

Classify them:

- Assigning `createdAt`/`updatedAt`.
- Assigning `createdBy`/`lastModifiedBy`.
- Normalizing fields.
- Validating entities.
- Publishing application events.
- Sending emails or HTTP requests.
- Publishing messages.
- Writing audit trails to the database.

Data changes that belong to the persistence lifecycle may fit `EntityCallback`. Business rules should live in the service/domain layer. Side effects that must be consistent with commits should consider a transactional outbox instead of sending directly inside a callback.

## 17. Transactional Events and Off-Database Side Effects

Many JPA applications use post-commit event listeners to publish messages or call external systems. When migrating to reactive, revisit the transaction event model and Reactor Context.

A callback after saving an entity does not mean the database transaction has committed. If a message is sent before commit and the transaction then rolls back, consumers may receive an event for data that does not exist.

For reliable message publishing:

1. Write business changes.
2. Write the outbox event in the same database transaction.
3. Commit both.
4. A worker/publisher reads the outbox and sends the message.
5. Mark as sent or handle retries.
6. Consumers support deduplication/idempotency.

If the application currently relies on JPA `@TransactionalEventListener(AFTER_COMMIT)`, design the equivalent for reactive transactions, verifying context and failure handling. Do not migrate annotations mechanically.

## 18. Blocking Dependencies Outside the Database

A migration that only swaps JDBC for R2DBC while still making many blocking API calls will not achieve end-to-end reactivity.

Inventory dependencies on the same request path:

- `RestTemplate` or blocking HTTP clients.
- Remaining JDBC DAOs.
- Blocking Redis clients.
- File I/O.
- Blocking cloud SDKs.
- LDAP or legacy services.
- Synchronous message producers.
- CPU-heavy transformations.
- `ThreadLocal` context/security/auditing.

If a service uses WebFlux yet calls JDBC or JPA on the event loop, requests can still block. Blocking work can be isolated on an appropriate scheduler during a transition period, but this is a temporary operational workaround and must be measured. Do not offload a blocking call onto `boundedElastic` and call it non-blocking.

To gain reactive benefits, the entire path must be evaluated. An endpoint may start reactively only to wait on a blocking SDK inside `flatMap`, losing concurrency gains and putting pressure on schedulers.

## 19. API Contracts: List/Optional vs. Flux/Mono

JPA repositories typically return synchronous types such as `Entity`, `Optional`, `List`, or `Page`. R2DBC repositories typically return `Mono` and `Flux`.

| Common Imperative Type | Common Reactive Type |
|---|---|
| Entity | Mono<Entity> |
| Optional<Entity> | Mono<Entity> empty when absent |
| List<Entity> | Flux<Entity> |
| Page<Entity> | Requires designing combination of data and count |
| void | Mono<Void> |
| int/long rows affected | Mono<Integer/Long> depending on API |
| Stream<Entity> | Flux<Entity>, requires lifecycle/cancel management |

This change propagates across services, controllers, schedulers, message handlers, and tests. Do not call `block()` immediately in services just to preserve synchronous signatures if the goal is end-to-end reactivity.

### 19.1. Pagination Does Not Map One-to-One Automatically

Spring Data JPA `Page` usually contains content, total elements, total pages, and paging metadata. With R2DBC, you may need separate content and count queries, combining results with `Mono.zip` or an appropriate publisher.

For large datasets, consider keyset pagination instead of offset pagination if the database and business logic support it. Verify stable sorting and last-page conditions.

### 19.2. Flux Can Stream Data

A `Flux` is not a `List` returned immediately. Callers must subscribe and consume items. Calling `collectList()` buffers the entire result in memory again.

Evaluate the API consumer: can it stream to the HTTP response, process in batches, or does it need the entire dataset aggregated? Choose the return type based on actual needs; do not convert `List` to `Flux` and immediately call `collectList()` everywhere.

## 20. Context, Security, and Transaction Propagation

Reactive pipelines can switch execution between threads. Information previously stored in `ThreadLocal` may not automatically follow the pipeline.

Inventory:

- `SecurityContext`.
- Tenant ID.
- MDC/log correlation.
- Locale.
- User/auditor identity.
- Transaction context.
- Request-scoped data.
- Custom `ThreadLocal`.

Spring Security reactive uses Reactor Context for the security context. Reactive transactions also rely on Reactor Context. If current code reads `ThreadLocal` directly inside callbacks or repository listeners, migrate it to an appropriate context-aware mechanism.

Do not use `ThreadLocal` arbitrarily to pass transaction or security identity across operators. Audit usages of `SecurityContextHolder`, `RequestContextHolder`, and MDC when moving to WebFlux/reactive.

## 21. Connection Pools and Operations

JDBC pools such as HikariCP and R2DBC pools manage two different types of connections via different APIs. You cannot copy `max pool size` verbatim from JDBC to R2DBC and assume equivalent performance.

Evaluate:

- Maximum number of replicas.
- Total connections across all pools and services.
- Database `max connections`.
- Acquire latency and pending queue.
- Connection hold duration.
- Transaction duration.
- Query latency p95/p99.
- Retries and timeouts.
- Database CPU, memory, locks, and I/O.

R2DBC does not make the database process infinite queries. An oversized pool can saturate the database. An undersized pool can build up queues. Load testing and a system-wide connection budget are required.

Startup operations such as migrations may still use JDBC. This means an R2DBC application may still need a JDBC driver and `DataSource` for Flyway/Liquibase, while runtime repositories use an R2DBC `ConnectionFactory`. Both connection paths must point to the correct database/schema.

## 22. Database and Driver Compatibility

Not every database or feature has an R2DBC driver with the same maturity and capabilities. Before migrating, verify:

- Database engine and version in use.
- Official/supported R2DBC driver.
- R2DBC SPI compatibility.
- Native data types.
- Generated keys and sequences.
- Stored procedures/functions.
- Large objects/BLOB/CLOB.
- Arrays, JSON, enums, UUIDs.
- Transaction isolation and locking.
- Cancellation behavior.
- SSL, authentication, and failover.
- Connection validation and pool integration.

If the application uses features specific to Oracle, SQL Server, or a PostgreSQL extension, prototype against the exact production driver and version. Do not extrapolate from a demo running on H2.

Check the driver's roadmap/support policy and your organization's ability to troubleshoot incidents. A driver may handle basic CRUD without supporting the application's full feature set.

## 23. Schema Migration and Data History

JPA may be using Hibernate DDL auto or a migration tool. Before migrating, determine who owns the schema:

- Hibernate auto-creating/updating schema.
- Flyway.
- Liquibase.
- Manual SQL scripts.
- Managed separately by a database team.
- Multiple tools coexisting.

For production, clear versioned migrations are required. Do not let Hibernate DDL auto and R2DBC mapping both infer schema in production environments.

Migrations must maintain compatibility with both old and new application versions during rolling deployments. When modifying columns or relationships, use expand-and-contract when needed:

1. Add new structures while old code can still operate.
2. Deploy code capable of compatible reads/writes.
3. Backfill data.
4. Cut over all instances to the new code.
5. Remove old structures in a later release.

Never edit migrations that have already run in shared environments; create new migrations instead. Test both from an empty schema and upgrading from the current schema.

## 24. Testing Before Migration

There should be three separate testing groups:

### 24.1. Unit Tests

Use mocks/fakes to verify:

- Business rules.
- Validation.
- Error mapping.
- Publisher orchestration.
- Empty/error handling.
- Retry policies.
- API response mapping.

Unit tests do not prove SQL or mapping correctness.

### 24.2. Data-Access Integration Tests

Use real repositories/templates/`DatabaseClient` with an R2DBC driver and database to verify:

- Entity mapping.
- Derived queries and custom SQL.
- Converters.
- Generated IDs/versions.
- Constraints.
- Transaction rollback.
- Pagination and sorting.
- `EntityCallback` and auditing.

### 24.3. Production Database Integration Tests

Use Testcontainers or a test database matching the production engine/version to verify:

- SQL dialect.
- Native types.
- Stored procedures.
- Migrations.
- Locking/concurrency.
- Transaction isolation.
- Driver-specific behavior.
- Error codes/SQLState.

H2 can help test common relational behavior, but it does not replace the production database. Never use mocked repositories to claim repositories have been tested.

## 25. Prototype a Vertical Slice Before Committing

Choose a representative, valuable use case that is neither too trivial nor overly complex. For example: look up a customer, update their profile, and record an audit entry.

The prototype should traverse the full path:

~~~text
HTTP endpoint
     |
     v
Reactive controller
     |
     v
Service / use case
     |
     v
R2DBC repository / template
     |
     v
Production R2DBC driver
     |
     v
Database
~~~

Evaluate the prototype against these criteria:

- Is API behavior preserved?
- Are queries and mapping accurate?
- Do transactions preserve atomicity?
- Are empty/error/cancel signals handled properly?
- Are any blocking calls left?
- Does it improve thread usage and latency under load?
- Are the pool and database stable?
- Is the code readable, debuggable, and testable?
- Can the team operate the new metrics/tracing?

Measure with the same workload and data before and after. If the prototype shows no benefit or significantly increases complexity, stop and revisit goals before expanding.

## 26. Readiness Assessment Matrix

Each use case can be scored against a matrix:

| Criterion | Low Risk | Medium Risk | High Risk |
|---|---|---|---|
| ORM features | Simple CRUD | Converters/callbacks | Lazy loading, deep cascades, complex inheritance |
| Queries | Simple derived queries | Criteria/dynamic queries | Database-specific native SQL/procedures |
| Transactions | Single repository call | Multiple operations in same DB | Multiple resources or complex locking |
| Data types | Common scalars | UUID/JSON requiring verification | Vendor-specific types/LOBs/arrays |
| Batching | Small volume | Bounded batches | Large batches, generator/provider-specific |
| Dependencies | Reactive end-to-end | A few blocking adapters | Many blocking SDKs on the critical path |
| Driver | Clearly supported features | Needs prototyping | Missing features/hard to operate |
| Tests | Integration tests exist | Partial test coverage | No tests against a real database |

This matrix is a discussion tool, not an absolute score. A single high-risk criterion—such as pessimistic locking or core stored procedures—can be enough to defer migrating a use case.

Also record owner, estimate, dependencies, rollback plan, and blast radius if migration fails.

## 27. Deciding Between Keeping JDBC/JPA, Migrating to R2DBC, or Going Hybrid

| Option | When Appropriate | Considerations |
|---|---|---|
| Keep JDBC/JPA | ORM features are critical, workload is stable, blocking is not a bottleneck | Keeps model simple; continue optimizing queries/pool |
| Migrate to R2DBC | I/O concurrency is a measured issue, stack is reactive, driver has needed features | Cost of rewriting transactions/queries and changing APIs |
| Hybrid by module/use case | Some flows need reactivity, others rely on JPA/batching | Two transaction models and connection pools to manage separately |
| Migrate API boundary only | Need reactive HTTP while database path stays blocking short-term | Must isolate blocking calls; do not treat as end-to-end reactive |
| Defer migration, optimize JDBC | Bottleneck is queries/indexes/DB rather than blocked threads | May achieve gains at much lower cost |

Hybrid can be a practical option. For example, interactive APIs use R2DBC while existing reporting or batch jobs stay on JDBC. However, never assume an atomic transaction can span both `JpaTransactionManager` and `R2dbcTransactionManager` via a single annotation.

If a use case must write to both data access paths, design clear boundaries. Use outbox/saga patterns or split the use case to avoid relying on unsupported distributed transactions.

## 28. Phased Migration Roadmap

A controlled roadmap:

### Phase 1: Discovery

- Collect baseline metrics.
- Inventory repositories/queries.
- Inventory JPA features.
- Verify driver and database capabilities.
- Flag blocking dependencies.
- Classify use cases by risk.

### Phase 2: Prototype

- Select a vertical slice.
- Design R2DBC entity mapping.
- Rewrite queries and transactions.
- Add integration tests on the production database.
- Load-test and observe pool behavior.
- Evaluate readability and supportability.

### Phase 3: Foundation

- Standardize `ConnectionFactory` and pooling.
- Set up the reactive transaction manager.
- Set up metrics, tracing, and logging.
- Standardize error handling and timeouts.
- Standardize migration and test infrastructure.

### Phase 4: Incremental Migration

- Migrate independent use cases/modules one by one.
- Maintain API contracts.
- Test side by side in staging.
- Monitor metrics and errors.
- Retain the ability to revert to the old version during transition.

### Phase 5: Stabilization

- Remove JDBC/JPA code only when no callers remain.
- Confirm connection pool and resource budgets.
- Run concurrency/load tests.
- Update runbooks and operational documentation.
- Train the team and hand over ownership.

Do not migrate all repositories in a single big-bang release if they can be split along business boundaries.

## 29. Coexistence Strategy and Avoiding Dangerous Dual-Writes

During transition, some modules may use JPA while others use R2DBC against the same database. This can work if schemas and transaction boundaries are clearly managed.

Risks:

- Two connection pools share the same database connection budget.
- JPA transactions and R2DBC transactions are independent.
- The same row is updated from both paths without a concurrency policy.
- JPA cache/persistence context holds stale data after R2DBC modifies a row.
- Inconsistent entity mapping and naming conventions.
- A use case accidentally requires an atomic write across both transaction managers.

If a JPA persistence context is open and R2DBC modifies the same row, managed JPA entities may not know the data changed. Refresh/clear explicitly or design boundaries so both paths do not manage the same state in one use case.

Avoid dual-writing across two databases or two transactional resources while assuming both will commit together. When event publishing or synchronization is needed, use outbox/saga and idempotency.

## 30. Rollback Plan and Stop Criteria

Before cutting over a production use case, determine:

- Can the old code version still run against the new schema?
- Are there destructive migrations?
- Can the application be rolled back without rolling back the schema?
- Can data written by the new version be read by the old version?
- Is there a feature flag to route traffic?
- Can the R2DBC path be turned off to revert to the JDBC path?
- Is reverse backfill or forward-fix needed?
- Who decides to halt the rollout and based on which metrics?

Stop criteria may include:

- Error rate exceeding threshold.
- p95/p99 latency worse than baseline.
- Sustained increase in acquire timeouts or pending pool requests.
- Database CPU/connections exceeding budget.
- Increase in transaction rollbacks/deadlocks.
- Data mismatches or mapping errors.
- Difficulty recovering due to schema incompatibility.

Rolling back code does not always mean rolling back the database. Prefer backward-compatible migrations and safe forward-fixes, especially once new data has been written by the new version.

## 31. Skill and Operational Costs

Reactive programming changes how stack traces are read, and how systems are debugged, tested, and observed. The team needs to understand:

- `Mono`/`Flux` and lazy subscription.
- Error signals, empty signals, and cancellation.
- Backpressure.
- Reactor Context.
- Reactive transactions.
- Avoiding blocking or manual subscriptions.
- Connection pools and acquire timeouts.
- Schedulers and blocking boundaries.
- Testing with `StepVerifier`.
- Tracing/metrics for publishers.

If most of the system still uses MVC, JDBC, synchronous SDKs, and blocking batch jobs, migrating a single database module to R2DBC can make the architecture harder to understand. Evaluate onboarding, on-call, and debugging costs before deciding.

Do not treat fewer lines of code or more modern-looking reactive APIs as proof of migration success. The criteria must be correct behavior, stable resources, improved latency/throughput where needed, and the team's ability to operate it.

## 32. Signs You Should Defer Migration

Consider deferring or scoping down migration when:

- Blocking JDBC has not been measured as a bottleneck.
- The database is already saturated by queries/CPU/locks.
- The application relies deeply on the JPA persistence context.
- Many use cases depend on lazy loading and complex cascades.
- Many stored procedures or native SQL features are unsupported by the driver.
- Transactions must coordinate multiple imperative resources.
- The R2DBC driver lacks required features or adequate support.
- Many blocking dependencies sit on the critical path.
- There are no integration tests against the production database.
- The team lacks reactive experience and has no time for training.
- Expected operational gains are lower than the cost of rewriting and maintaining two stacks.

Deferring migration does not mean doing nothing. You can optimize indexes/queries, eliminate N+1s, tune the JDBC pool, add targeted caching, apply pagination, or isolate blocking workloads to meet immediate goals.

## 33. Pre-Approval Assessment Checklist

### Goals and Baseline

- [ ] Specific problem the migration aims to solve is defined.
- [ ] Request latency, throughput, and concurrency have been measured.
- [ ] Thread usage and JDBC pool metrics have been measured.
- [ ] Database CPU, I/O, locks, and query plans have been inspected.
- [ ] Measurable post-migration success criteria exist.

### Code and ORM

- [ ] All JDBC/JPA access paths have been inventoried.
- [ ] Persistence context and dirty checking usage have been inventoried.
- [ ] Lazy/eager relationships and N+1 issues have been inventoried.
- [ ] Cascade and orphan removal usage have been inventoried.
- [ ] Callbacks, auditing, and event listeners have been inventoried.
- [ ] JPQL, Criteria, Specifications, and native SQL have been inventoried.
- [ ] ID generation, converters, and inheritance mapping have been inventoried.

### Database Behavior

- [ ] Transaction boundaries/propagation have been checked.
- [ ] Optimistic/pessimistic locking has been checked.
- [ ] Batch and bulk operations have been checked.
- [ ] R2DBC driver support for required data types has been verified.
- [ ] Critical stored procedures/native features have been prototyped.
- [ ] Migration strategy and rolling compatibility have been confirmed.

### Reactive Readiness

- [ ] Critical path has no unhandled blocking dependencies.
- [ ] API contracts are designed with appropriate `Mono`/`Flux`.
- [ ] Security, tenant, and logging contexts have been addressed.
- [ ] Team understands cancellation, backpressure, and reactive transactions.
- [ ] Connection pool sizing accounts for maximum replicas.

### Testing and Rollout

- [ ] Unit tests exist for business logic.
- [ ] Data-access integration tests exist with real R2DBC.
- [ ] Tests run against the exact production database engine/version.
- [ ] Migration tests exist from both empty and existing schemas.
- [ ] Load tests compare against the baseline.
- [ ] Incremental rollout and rollback plans exist.
- [ ] Operational dashboards, alerts, and runbooks are in place.

## 34. Conclusion

Assessing a JDBC/JPA application before migrating to R2DBC must start with goals and metrics, then inventory all queries, transactions, ORM features, data types, batch jobs, blocking dependencies, and operational requirements. JDBC and JPA are not just ways to send SQL: JPA also provides a persistence context, dirty checking, lazy loading, cascades, locking, and entity lifecycle management. Spring Data R2DBC has its own relational mapping and reactive repository model and does not automatically recreate all of those semantics.

R2DBC is a good fit when the application has clearly measured I/O concurrency needs, the driver supports required features, and most of the request path can be reactive. If bottlenecks lie in queries, indexes, database saturation, or non-database blocking dependencies, address those root causes first. For complex JPA applications, prototype a vertical slice, test on the production database, benchmark the same workload, and evaluate operational costs.

The assessment outcome may be a full migration, module-by-module migration, a hybrid JDBC/R2DBC setup, or keeping things as they are. A sound decision is one grounded in behaviors to preserve, measurable benefits, database risks, and the team's ability to maintain the system after migration.
