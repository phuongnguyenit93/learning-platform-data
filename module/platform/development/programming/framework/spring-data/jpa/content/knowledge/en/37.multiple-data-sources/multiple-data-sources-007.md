# Read/Write Routing, Replica Lag, and Read-Your-Writes Consistency in Spring Data JPA

## 1. Why does an application need read/write routing?

When an application handles heavy read traffic and a single primary database handles writes, one or more read replicas can be added to offload reads. The application sends write operations to the primary, while suitable read queries are sent to replicas.

This architecture scales read capacity, but introduces a critical issue: replicas typically receive data from the primary via asynchronous replication. After the primary commits a change, a replica may not have replayed that change yet. A read query executed immediately after a write may observe stale data.

In Spring Data JPA, three parts must be designed together:

- **Read/write routing:** selecting the primary or replica DataSource based on the transaction's intent.
- **Replica lag management:** measuring and handling replica synchronization delay.
- **Consistency policy:** deciding which use cases require the freshest data and which can tolerate delayed data.

Not every SELECT query can be sent to a replica. Pessimistic locking queries, operations needing read-your-writes, or permission/status checks immediately after a write usually need to read from the primary.

## 2. Primary and read replica architecture

A common topology:

~~~text
                    Spring Boot application
                              |
                    Spring Data JPA / Hibernate
                              |
                    Routing DataSource
                       /           \
                 PRIMARY           REPLICA
                    |                 |
              Write + Read       Read-only traffic
                    |                 ^
                    +---- replication+
                         (async)
~~~

**Primary** is the database receiving write transactions. It can also serve read queries.

**Read replica** receives changes from the primary through the database's replication mechanism. Replicas are usually configured as read-only at the database or connection user level.

**Routing DataSource** is the layer that chooses the appropriate DataSource before a physical JDBC connection is acquired. Spring provides **AbstractRoutingDataSource** to map a routing key to a target DataSource.

Each target DataSource usually has its own connection pool. For example, primary has a pool for writes and consistent reads; replica has a pool for read queries that accept eventual consistency.

Routing occurs when a connection is acquired. A JDBC connection already allocated from the primary remains on the primary for the entire lifecycle of that connection/transaction. You cannot switch a transaction already using a primary connection to a replica mid-flight just by changing a routing key.

## 3. Asynchronous replication and replica lag

With asynchronous replication, the primary can confirm a commit before replicas apply the corresponding changes.

For example:

1. A user updates their shipping address.
2. The transaction commits successfully on the primary.
3. The API returns success.
4. A subsequent read request is routed to a replica.
5. The replica has not replayed the committed transaction yet, so it returns the old address.
6. After some time, the replica receives and applies the change; later queries return the new address.

The gap between the primary's state and the replica's state is called **replica lag**.

Lag can arise from:

- Slow or interrupted networking between primary and replica.
- Insufficient CPU, I/O, or WAL/binlog processing capacity on the replica.
- Long-running queries or transactions on the replica delaying replay.
- Heavy write bursts on the primary.
- Paused replication, misconfiguration, or a replica undergoing recovery.
- A replica that recently restarted or is catching up.

Lag is not always a fixed number of milliseconds. Some databases report distance by byte/log sequence, while others report time or log position. Use the metrics appropriate to the engine being run.

### Eventual consistency

When asynchronous replication operates normally, the replica eventually converges with the primary as the system continues transmitting and replaying logs successfully. This is the eventual consistency model.

A query read from a replica can return stale data for a period of time. Therefore, never assume every SELECT after a commit immediately sees the newly written change.

## 4. Defining a consistency policy before configuring routing

Before writing code, classify your use cases:

| Use case | Appropriate Read Source | Reason |
|---|---|---|
| Updating profile then returning updated profile | Primary or already-updated entity in transaction | Needs read-your-writes |
| Checking balance right after a transaction | Primary or source with equivalent consistency guarantee | Stale balance is unacceptable |
| Reading order status immediately after creation | Primary within an appropriate pinning window | User expects to see the new order |
| Aggregated dashboards where a few seconds of delay is fine | Replica | Eventual consistency acceptable |
| Heavy analytical reporting | Replica/reporting database | Offloads primary |
| Reading rarely changing catalog data | Replica if stale window is acceptable | Can offload traffic |
| Reading to decide a subsequent update | Primary | Avoids decisions based on stale state |
| SELECT FOR UPDATE or pessimistic locking | Primary | Replicas usually disallow writes/locks with required semantics |

Do not route solely based on whether SQL starts with SELECT. A SELECT query might use FOR UPDATE, invoke a stored procedure with write side effects, or participate in a workflow needing the latest state.

## 5. Routing based on Spring transaction readOnly

Spring transactions have a **readOnly** attribute. When a service declares:

~~~java
@Transactional(readOnly = true)
public CustomerProfile getProfile(Long customerId) {
    return customerRepository.findProfile(customerId);
}
~~~

Spring marks the current transaction as read-only. This attribute is a hint to the transaction manager, JDBC driver, and JPA provider to optimize read processing. It does not automatically pick a replica unless the application has configured routing.

A common approach is having the routing DataSource inspect the transaction's read-only attribute:

~~~java
public enum DataSourceRoute {
    PRIMARY,
    REPLICA
}
~~~

~~~java
public class ReadWriteRoutingDataSource
        extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        boolean readOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();

        return readOnly
            ? DataSourceRoute.REPLICA
            : DataSourceRoute.PRIMARY;
    }
}
~~~

Meaning:

- Read-only transactions are routed to the replica.
- Write transactions, or calls without a read-only transaction, are routed to the primary.
- Primary should be the default target so operations without a routing context remain safe.

This approach only works when the application has confirmed that queries inside read-only transactions can tolerate replica lag. If a use case needs the freshest read, explicitly route it to the primary.

## 6. Configuring AbstractRoutingDataSource

Example configuration of two target DataSources and a routing DataSource:

~~~java
@Configuration
public class DataSourceConfiguration {

    @Bean
    public ReadWriteRoutingDataSource routingDataSource(
            @Qualifier("primaryDataSource") DataSource primary,
            @Qualifier("replicaDataSource") DataSource replica) {

        ReadWriteRoutingDataSource routing =
            new ReadWriteRoutingDataSource();

        Map<Object, Object> targets = new HashMap<>();
        targets.put(DataSourceRoute.PRIMARY, primary);
        targets.put(DataSourceRoute.REPLICA, replica);

        routing.setTargetDataSources(targets);
        routing.setDefaultTargetDataSource(primary);
        return routing;
    }
}
~~~

In this example, the two beans primaryDataSource and replicaDataSource are separate connection pools, typically HikariCP. Configuration of URLs, credentials, pool sizes, timeouts, and drivers is omitted because it depends on the database and environment.

**setTargetDataSources** declares routing keys and their corresponding DataSources. **setDefaultTargetDataSource** chooses the primary when no key matches.

Configure a fallback to primary. If a route key is missing or code calls a repository outside a transaction, the operation still goes to a database capable of reading and writing. However, fallback does not replace access control and consistency policies.

In real applications, ensure the routing DataSource is used consistently by both the EntityManagerFactory and transaction manager. Do not let Hibernate use primary directly while the transaction manager uses a different routing DataSource.

## 7. Why is LazyConnectionDataSourceProxy needed?

This is a critical detail when routing via TransactionSynchronizationManager.isCurrentTransactionReadOnly().

A Spring transaction manager may acquire a JDBC connection when starting a transaction. Transaction synchronization state, including the read-only flag, is published during transaction setup. If the routing DataSource decides between primary and replica too early, it may not yet see the read-only flag and always pick primary.

**LazyConnectionDataSourceProxy** delays acquiring the physical connection until the application actually needs to execute a JDBC statement. By the time the first SQL statement runs, the transaction has been established and the read-only state can be read accurately.

Typical configuration:

~~~java
@Bean
@Primary
public DataSource dataSource(
        @Qualifier("routingDataSource") DataSource routingDataSource) {

    return new LazyConnectionDataSourceProxy(routingDataSource);
}
~~~

In this architecture:

1. The transaction manager obtains a lazy connection proxy.
2. Spring sets up transaction attributes and read-only state.
3. Hibernate/JDBC executes the first statement.
4. The lazy proxy requests a real connection from the routing DataSource.
5. The routing DataSource reads the transaction read-only flag and picks primary or replica.

If you omit the lazy proxy layer in a routing setup driven by transaction metadata, verify the connection acquisition order of your specific transaction manager/provider. Never assume the routing key is always ready when DataSource.getConnection() is called.

LazyConnectionDataSourceProxy also supports configuring a dedicated read-only DataSource in Spring Framework versions providing that API. That mechanism can replace custom routing when the policy is simply selecting targets based on JDBC connection read-only status. Check your application's Spring Framework version before using newer APIs.

## 8. Integrating with Spring Boot, JPA, and the transaction manager

In Spring Boot, the routing DataSource is typically the primary DataSource seen by JPA and the transaction manager.

Configuration guidelines:

- Mark the routing/lazy wrapper as the **@Primary** bean when the application has multiple DataSources.
- Primary pool and replica pool are separate beans with explicit qualifiers.
- EntityManagerFactory uses the wrapper DataSource.
- JpaTransactionManager uses that same EntityManagerFactory.
- Do not inject the raw primary or replica pool directly into normal repositories or services.
- Only health check or migration components should access individual DataSources when there is a clear reason.
- Configure connection pools, timeouts, and monitoring separately for primary and each replica.

When declaring multiple DataSources manually, Spring Boot may no longer infer a single DataSource for auto-configuration. Explicitly configure JPA, transaction manager, and migration tool beans according to your actual topology.

## 9. Using @Transactional at the right boundaries

Example service distinguishing read and write operations:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer getCustomer(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                "Customer not found"
            ));
    }

    @Transactional
    public Customer changeEmail(Long id, String email) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException(
                "Customer not found"
            ));

        customer.changeEmail(email);
        return customer;
    }
}
~~~

The read method has a read-only transaction and can be routed to the replica. The write method uses a default read-write transaction and is routed to the primary.

In the write method, `findById()` must also read from the primary because it participates in the write transaction. This is desirable: the application inspects and modifies state against the same consistent data source.

With Spring Data JPA, inherited CRUD methods carry default transaction configuration. Declared query methods typically need transactions defined at the service layer or suitable repository configuration. Declaring transactions on services ensures the entire use case uses the same data source and transaction boundary.

## 10. Transaction propagation and routing keys

Routing is determined by the actually active transaction, not merely by the annotation on the most recently called method.

With default **REQUIRED** propagation:

- If no transaction exists, Spring creates a new transaction using the method's attributes.
- If a transaction already exists, the method joins the current transaction.
- A read-only method called inside a write transaction does not turn that transaction into read-only.
- A write method called inside an existing read-only transaction does not automatically upgrade that transaction to a write transaction.

Example:

~~~java
@Transactional(readOnly = true)
public CustomerProfile loadProfile(Long id) {
    return customerRepository.findProfile(id);
}

@Transactional
public void updateCustomer(Long id, String email) {
    customerProfileService.loadProfile(id);
    customerRepository.updateEmail(id, email);
}
~~~

If `loadProfile()` joins the outer write transaction via REQUIRED, both operations still use the current transaction and route to the primary. The inner read-only annotation does not switch the already-acquired connection to a replica.

Do not design a single use case expecting both replica read-only access and writes within the same transaction while hoping routing switches DataSources automatically. If an independent transaction is needed, consider another propagation like **REQUIRES_NEW**, while understanding that it suspends the outer transaction, acquires a new connection, and impacts atomicity.

Never change the routing key after a transaction has acquired a connection. Determine the consistency policy before starting the transaction.

## 11. Read-your-writes consistency

**Read-your-writes** guarantees that users read back changes they just wrote themselves.

For example, a user changes their display name from "An" to "Bình". After the update API returns success, the next request fetching the profile must show "Bình".

If the next request is routed to a replica that has not replayed the change, the user may see "An". This is an application-level read-your-writes violation even though replication is working properly under eventual consistency.

Common strategies:

### 11.1. Read from primary after a write

The simplest and strongest approach is routing queries that need immediate post-write reads to the primary. You can keep the read and write in the same write transaction or invoke a service method marked read-write.

### 11.2. Pin the user/session to primary for a window of time

After a successful write, the application marks the user/session/request context to read from primary for a brief duration. Subsequent requests from the same user are routed to primary until the pin expires or the replica catches up.

Design the TTL, storage, and pinning scope clearly. Do not use ThreadLocal for state that must survive across multiple HTTP requests; ThreadLocal lives only on the current thread and does not transfer across separate requests.

### 11.3. Use a replication watermark or consistency token

Some databases expose a log/commit position such as an LSN, GTID, or equivalent token. After a write, the application can retain the token and only read from a replica once the replica has replayed up to at least that token.

This is a database-specific implementation. Understand what commit the token represents, how to retrieve the position after commit, how to compare it on the replica, and how to handle timeouts when a replica lags behind. Do not apply a single generic LSN/GTID comparison across different databases.

### 11.4. Use synchronous replication where appropriate

Some databases can be configured for synchronous replication or wait for a replica to acknowledge replay before confirming a commit. This can increase consistency at the cost of higher write latency and coupling to topology/failure policies.

Distinguish between a replica receiving logs, flushing logs, and replaying logs. An acknowledgement that only confirms receipt/flush does not necessarily guarantee read queries on the replica see the data immediately. Verify your specific database's semantics.

## 12. Where is eventual consistency acceptable?

Not every screen requires millisecond-fresh data.

Replicas are usually well suited for:

- Aggregated metrics dashboards.
- Operational reports.
- Historical lists that do not need to reflect a commit instantaneously.
- Rarely changing catalogs or content.
- Searches and filters that tolerate a short stale window.
- Analytical tasks that do not influence an immediate subsequent write decision.

Do not default to routing to a replica for:

- Balances, limits, or payment statuses immediately after a transaction.
- Inventory, reservation, or resource allocation decisions.
- Recently modified access permission checks.
- Idempotency or processing-state checks inside a write workflow.
- Locking queries using PESSIMISTIC_WRITE or SELECT FOR UPDATE.
- Use cases requiring strict read-your-writes or monotonic reads.

Document consistency requirements in API/use-case designs rather than letting developers guess from method names.

## 13. Replica lag and how to monitor it

Do not measure replica lag solely as a single number on a dashboard. Monitor both replication health and application impact.

Recommended metrics:

- Replication lag by time or log position.
- Byte/log distance between primary and replica.
- Time elapsed since the last replay.
- Streaming/recovery state or replication thread status.
- Log receive rate and replay rate.
- Query latency and error rate broken down per DataSource.
- Pool active/idle/pending counts and connection acquisition time.
- Count of requests pinned to primary for consistency requirements.
- Count of fallbacks due to replica errors or exceeding lag thresholds.

Metric names and calculation methods depend on the database. For instance, PostgreSQL exposes replication sender/receiver and replay LSN statistics; MySQL provides replication source/replica status and GTID/worker metrics. Use the engine's native metrics as the source of truth for lag.

### Lag thresholds

Set thresholds according to business requirements:

- A dashboard tolerating a 10-second delay can keep using the replica while lag stays below that threshold.
- A payment confirmation page may require the primary immediately.
- Heavy reports may use a dedicated replica with its own refresh schedule.

Do not apply a single lag threshold to every endpoint. If a replica exceeds its threshold, you can temporarily route sensitive queries back to primary or return an error/indicator that data is updating, depending on the API contract.

## 14. Health checks and failover

A replica may be reachable yet not replaying logs or lagging far behind. A simple TCP health check is insufficient to conclude a replica is safe for every query.

Check:

- Connectivity and authentication.
- Replication status.
- Read-only mode of the replica.
- Replication lag and most recent replay timestamp.
- Ability to execute a lightweight health check query.
- Connection pool health and timeouts.
- Whether the replica is undergoing recovery or paused.

When a replica fails, two policies are common:

1. **Fallback to primary:** increases read availability but can overload the primary.
2. **Fail closed for replica workloads:** reject or pause certain read queries, preserving the primary for critical workloads.

Do not automatically fail over all read traffic to the primary without load limiting. When multiple replicas fail together, the primary can become a bottleneck and bring down the entire system.

Promoting a primary during failover is a separate procedure from read routing. You must identify the new primary, update endpoints/service discovery, fence the old node to prevent split-brain, and verify replication topology before accepting writes.

## 15. Persistence context and caches can also produce stale data

Replica lag is not the only reason an application sees stale data.

### First-level cache

JPA's persistence context holds managed entities. If an entity has already been loaded earlier, calling find() again in the same EntityManager typically returns the managed object without necessarily querying the database.

Thus, even when routed to primary, a managed entity may hold stale state if changes occurred outside the persistence context.

Within a write transaction, after modifying a managed entity, use that same object or flush as needed. If native/bulk updates occur, understand that the persistence context does not synchronize automatically; consider refreshing or clearing the appropriate scope.

### Second-level cache and query cache

Hibernate second-level cache and query cache can retain data across Sessions. If cache invalidation or cache coordination across nodes is misconfigured, the application can read stale state even when queries go to the primary.

Monitor cache hits/misses, eviction, invalidation, and concurrency strategy configuration. Do not blame every stale read on the replica.

### Application cache

Redis, Caffeine, or service-level caches may hold stale values after a database commit. Ensure cache invalidation/update policies align with consistency requirements.

Read-your-writes must account for the entire read path: primary/replica, persistence context, Hibernate caches, and application caches.

## 16. Locking queries and queries with write side effects

Never route queries based solely on SQL SELECT.

Spring Data JPA example:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from Order o where o.id = :id")
Optional<Order> findForUpdate(@Param("id") Long id);
~~~

This query requires database locking support and must run on the primary inside a write transaction. Replicas generally do not permit locking for business updates.

Similarly, queries with @Modifying, native stored procedures, SELECT FOR UPDATE, or state-check queries driving write decisions must be routed according to write intent.

When routing by readOnly=true, ensure such use cases are not marked read-only. Do not write a custom SQL parser to guess intent from query strings; define the policy at the service/transaction boundary.

## 17. Manual routing state with ThreadLocal

Some applications need to override routing per use case rather than relying solely on the read-only flag. A dedicated routing context can be used, but its lifecycle must be carefully managed.

Example context skeleton:

~~~java
public final class DataSourceContext {

    private static final ThreadLocal<DataSourceRoute> ROUTE =
        new ThreadLocal<>();

    private DataSourceContext() {
    }

    public static void usePrimary() {
        ROUTE.set(DataSourceRoute.PRIMARY);
    }

    public static void useReplica() {
        ROUTE.set(DataSourceRoute.REPLICA);
    }

    public static DataSourceRoute current() {
        return ROUTE.get();
    }

    public static void clear() {
        ROUTE.remove();
    }
}
~~~

The routing DataSource can prioritize an explicit route if present, falling back to transaction read-only status:

~~~java
@Override
protected Object determineCurrentLookupKey() {
    DataSourceRoute explicit = DataSourceContext.current();

    if (explicit != null) {
        return explicit;
    }

    return TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        ? DataSourceRoute.REPLICA
        : DataSourceRoute.PRIMARY;
}
~~~

Set the explicit route before the transaction acquires a connection and clean up the context in finally:

~~~java
public Customer loadFromPrimary(Long id) {
    DataSourceContext.usePrimary();
    try {
        return transactionalCustomerReader.load(id);
    } finally {
        DataSourceContext.clear();
    }
}
~~~

This example assumes `transactionalCustomerReader` is another bean invoked through a Spring proxy and that the physical connection is acquired after the context has been set. Do not invoke a transactional method via self-invocation expecting a proxy to start a transaction.

ThreadLocal can leak routes to subsequent requests if `remove()` is forgotten. Nor does it propagate automatically across executors, async tasks, or reactive pipelines. In reactive applications, use Reactor Context and appropriate reactive transaction routing instead of ThreadLocal.

When consistency can be expressed through read-only/write transactions and service boundaries, prefer that approach as it involves less hidden state.

## 18. Do not switch routes mid-transaction

A JPA transaction typically binds to a single EntityManager and a single JDBC connection. The routing key is read when acquiring the physical connection.

Unsafe example:

~~~java
@Transactional
public void processOrder(Long id) {
    DataSourceContext.useReplica();
    Order order = repository.findById(id).orElseThrow();

    DataSourceContext.usePrimary();
    order.confirm();
    repository.save(order);
}
~~~

Even though the context changes, a connection already obtained from the replica does not switch to the primary. Write statements may fail because the replica is read-only or violate transaction semantics.

Determine the data source before starting the transaction. If a use case needs to read and then write, route the entire transaction to the primary.

## 19. Pagination and multiple queries needing shared consistency

A `Page` endpoint may execute both a content query and a count query. If the two statements are routed to different replicas or to a replica at different replay points, the page content and total count may mismatch.

When consistency is required within a single response:

- Run the content query and count query within the same transaction/read snapshot where appropriate.
- Use the same routing policy and the same replica/connection for statements in the use case.
- Route to primary if the total count and content must reflect the latest commit.
- Consider `Slice` or keyset pagination if total count is not needed.
- Never pick a random replica per SQL statement inside the same transaction.

Routing should happen at the transaction/connection level, not by randomly picking a replica per SQL statement.

## 20. Migrations and schemas on primary/replica

Flyway or Liquibase typically runs migrations against the primary. Replication then propagates corresponding DDL/DML changes to replicas according to database capabilities and replication configuration.

Do not run the same migration independently on both primary and replica if the replica is managed via replication from primary. Doing so can cause schema mismatches or replication errors.

A typical workflow is:

1. Designate a single migration authority.
2. Run migrations on the primary or designated migration endpoint.
3. Verify migration completion and schema version.
4. Monitor replicas replaying DDL/data changes.
5. Return replicas to the read pool only when schema and replication state are compatible with the application.
6. Deploy code using backward-compatible strategies if old and new application versions run concurrently.

For breaking schema changes, use expand-and-contract: add the new structure, deploy compatible code, backfill data, switch reads/writes, and only then drop the old structure.

## 21. Protecting read replicas at the database level

Application-level routing is one layer of defense, but should not be the only layer.

Configure replicas with:

- Database user accounts granted only necessary read privileges.
- Database-level read-only mode if supported by the engine.
- No DDL or DML permissions for the application user on replicas.
- Network policies allowing only authorized applications and monitoring tools.
- Distinct credentials from the primary.
- Monitoring for rejected write statements and replication state.

**@Transactional(readOnly = true)** is only Spring metadata/hint. It is neither an authorization mechanism nor a guarantee that the database rejects all writes. Database privileges are the actual enforcement layer.

## 22. Testing read/write routing

You need integration tests proving routing actually hits the intended database, not merely checking annotations.

Set up a test topology with two distinguishable databases or schemas:

- Write a record and verify it appears in primary.
- Call a read-only service and verify the query hits replica.
- Call a write service and verify even SELECTs inside the write transaction hit primary.
- Verify a read-only method joining an outer write transaction still uses primary.
- Verify explicit primary override and ThreadLocal cleanup.
- Verify missing route context defaults to primary.
- Verify replica unavailability and fallback policy.
- Verify read-after-write during replica lag.
- Verify queries with pessimistic locks hit primary.
- Verify migrations run only on primary.

Testcontainers can spin up the target database engine. If real replication needs testing, configure an actual primary/replica topology or use a dedicated integration environment; two independent database containers do not simulate replication lag.

A simple way to verify routing is having each database return a distinct marker from a test query or expose hostname/server identity. Do not rely solely on logs from `determineCurrentLookupKey()`, as connection pools can obscure which DataSource was actually used.

## 23. Observability and operations

Monitor primary and each replica separately:

| Metric | Purpose |
|---|---|
| Query count by route | Shows how read/write load is distributed |
| Query latency p50/p95/p99 | Compares primary and replica performance |
| Connection pool active/idle/pending | Detects pool exhaustion or overload |
| Connection acquisition time | Detects connection wait times |
| Replica lag/time since replay | Detects overly stale replica data |
| Replication errors/reconnects | Detects unstable topology |
| Primary CPU, I/O, lock waits | Evaluates write load and remaining read load |
| Read fallback/pinning count | Shows how often consistency policy routes reads to primary |
| Stale-read incidents | Measures real user impact |

Use low-cardinality metric tags such as datasource, route, operation, or query name. Do not put customer IDs, order IDs, or raw parameterized SQL into metric labels.

Logs and traces should include route names and trace IDs to identify whether a request went to primary or replica. Mask sensitive data in SQL bind logs.

## 24. Common pitfalls

### 24.1. Thinking readOnly automatically routes to replica

**@Transactional(readOnly = true)** only provides transaction metadata/hints. You must configure a routing DataSource or read-only target for actual routing to occur.

### 24.2. Routing picks primary because connection is acquired too early

When using TransactionSynchronizationManager to check the read-only flag, acquiring a physical connection before transaction metadata is ready causes misrouting. Use LazyConnectionDataSourceProxy and test with your exact transaction manager/provider.

### 24.3. Using replica for read-after-write

Asynchronous replicas may not have replayed the latest commit yet. Pin to primary or use a consistency token/watermark when guarantees are needed.

### 24.4. Changing ThreadLocal after transaction has started

Once a connection is selected, the DataSource does not switch mid-transaction. Determine the route before the connection is acquired.

### 24.5. Assuming read-only transactions forbid writes

Read-only is typically a hint; enforcement depends on provider, driver, and database. Use dedicated database users/privileges to prevent writes on replicas.

### 24.6. Calling transactional methods via self-invocation

Internal calls within the same object normally bypass the Spring proxy, so transaction attributes may not be applied. Separate beans or invoke properly through a proxy.

### 24.7. Ignoring propagation

A read-only method nested inside a write transaction joins the write transaction under REQUIRED. Likewise, a write method nested inside a read-only transaction does not automatically upgrade that transaction.

### 24.8. Failing over all replica errors to primary

Failing over all read load can overwhelm the primary. Enforce rate limits, circuit breakers, health policies, and the ability to shed non-critical workloads.

### 24.9. Checking only whether the replica is reachable

A replica may be reachable yet lagging or not replaying. Monitor replication state and replay position.

### 24.10. Overlooking caches when investigating stale data

First-level, second-level, query caches, and application caches can all return stale state. Pinpoint exactly which layer served the data.

## 25. Recommended design

A practical design for a Spring Data JPA application with primary and replicas:

1. Use one primary pool and one or more replica pools.
2. Place AbstractRoutingDataSource in front of the target pools.
3. Use LazyConnectionDataSourceProxy so routing by transaction read-only happens at the right time.
4. Set primary as the default target.
5. Use `@Transactional(readOnly = true)` for read use cases accepting eventual consistency.
6. Use read-write transactions for write use cases and any reads depending on the latest changes.
7. Define a read-your-writes policy: primary pinning, session stickiness, or replication watermarks.
8. Never route locking queries, write queries, or sensitive business decisions to replicas.
9. Monitor lag, routes, latency, and pools separately per DataSource.
10. Test topology and failure modes on a production-like database.
11. Run migrations on primary and wait for replicas to replay schema changes.
12. Protect replicas with read-only database credentials and privileges.

You do not need to route every read query to a replica from day one. Measure primary load, identify use cases accepting stale data, and expand routing under clear policies.

## 26. Key takeaways

- Primary receives write transactions; read replicas serve eligible read queries.
- Asynchronous replication introduces replica lag; queries immediately after a commit may see stale data.
- Eventual consistency fits dashboards/reports, but not all business decisions.
- @Transactional(readOnly = true) is a transaction hint, not automatic replica selection and not an authorization mechanism.
- AbstractRoutingDataSource selects a DataSource by routing key; primary should be the default.
- LazyConnectionDataSourceProxy delays physical connection acquisition so read-only transaction metadata is ready before routing.
- Routing is decided when acquiring a connection; you cannot switch DataSources mid-transaction.
- REQUIRED joins an existing transaction; nested read-only annotations do not change the outer transaction's route.
- Read-your-writes can be ensured via primary routing, user/session pinning, or waiting for a replica to reach a replication watermark.
- LSN/GTID/watermarks are database-specific; understand the exact semantics of logs received, flushed, and replayed.
- Locking queries, write stored procedures, or business-critical decisions need an appropriate data source, usually primary.
- First-level, second-level, query caches, and application caches can also cause stale data.
- Migrations typically run on primary; replicas receive changes via replication.
- Monitor replica lag, query latency, pool usage, fallbacks, and stale-read incidents.
- Test routing, transaction propagation, failover, and read-after-write on a production-like topology.

Read/write routing is only valuable when paired with a clear consistency policy. Primary/replica setups distribute load, while transaction boundaries, replica lag, caches, and read-your-writes determine what data users actually observe after each operation.

## References

- [Spring Framework — AbstractRoutingDataSource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/AbstractRoutingDataSource.html)
- [Spring Framework — LazyConnectionDataSourceProxy](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/LazyConnectionDataSourceProxy.html)
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [PostgreSQL — Monitoring Database Activity and Replication](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [MySQL — Replication Status](https://dev.mysql.com/doc/refman/8.4/en/replication-administration-status.html)