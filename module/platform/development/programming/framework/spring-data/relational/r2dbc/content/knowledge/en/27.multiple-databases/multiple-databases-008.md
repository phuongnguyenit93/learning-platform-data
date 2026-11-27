# Read/Write Query Splitting with Replica Lag Considerations

When a Spring Data R2DBC application holds multiple connections to the same database cluster, write operations can be routed to the primary node (primary/writer) and a portion of read operations to replica nodes (replica/reader). The goal is to reduce read load on the primary and increase scalability. However, replicas are usually updated asynchronously, so data on a replica may lag behind the primary. A read query executed immediately after a write may not yet see the just-committed change.

Read/write splitting is therefore not merely picking one `ConnectionFactory` for SELECT and another factory for UPDATE. The application must decide which queries require strong consistency, keep a transaction on the right node, handle read-after-write, monitor replication lag, and define an explicit fallback policy. Spring Data R2DBC provides abstractions for routing connections, but choosing primary or replica remains an application architectural decision.

## 1. Primary and Read Replicas Model

A common topology has one primary receiving writes and one or more replicas serving reads:

~~~mermaid
flowchart TD
    APP[Spring WebFlux / Spring Data R2DBC]
    ROUTER[Read-write connection routing]
    PRIMARY[(Primary / Writer)]
    REPLICA1[(Read replica 1)]
    REPLICA2[(Read replica 2)]
    PRIMARY -->|Replication stream| REPLICA1
    PRIMARY -->|Replication stream| REPLICA2
    APP --> ROUTER
    ROUTER -->|INSERT / UPDATE / DELETE| PRIMARY
    ROUTER -->|Eligible SELECT| REPLICA1
    ROUTER -->|Eligible SELECT| REPLICA2
~~~

The primary is where data changes are received. Replicas receive changes replicated from the primary. Depending on the DBMS and configuration, replication can be synchronous or asynchronous; many read-scaled systems use asynchronous replication to reduce write latency.

In the asynchronous model:

1. The application sends an UPDATE to the primary.
2. The primary commits the transaction and returns success.
3. The change is written to the replication log.
4. Replicas receive and apply the change afterward.
5. During the waiting window, a replica can still return old data.

The delay between when the primary commits and when a replica finishes applying the change is called replication lag.

## 2. What Benefits Does Read/Write Splitting Bring?

When workloads have significantly more reads than writes, replicas can distribute load:

- The primary focuses on writes and reads requiring the latest data.
- Replicas serve listings, reports, or lag-tolerant queries.
- Additional replicas can be added to scale read capacity when supported by the database.
- Separating connection credentials allows read accounts to carry only SELECT privileges.
- Different topologies can be chosen per environment.

For example, an e-commerce system may read product catalogs from a replica, while reading account balances or recently updated order statuses from the primary.

Read/write splitting does not inherently make every SELECT faster. Replicas still have CPU, I/O, cache, network, and log-apply capacity limits. Heavy queries can increase replica lag or slow down other read queries.

## 3. Replication Lag and Stale Data

Suppose a user updates their shipping address:

| Time | Primary | Replica |
| --- | --- | --- |
| T0 | Old address | Old address |
| T1 | UPDATE and COMMIT new address | Old address |
| T2 | New address | Receiving/applying log |
| T3 | New address | New address |

If the application reads from a replica at T1 or T2, the user may see the old address even though the UPDATE returned success.

This is eventual consistency: replicas converge if replication continues operating normally, but they are not guaranteed to be identical immediately after every commit.

Do not interpret "low-lag replica" as "replica always returns the freshest data." Lag can spike when primary writes surge, a replica is overloaded, network disruptions occur, large transactions run, or replication encounters errors.

## 4. Read-After-Write Consistency

Read-after-write is the requirement that a client sees changes it just wrote itself. This is an important consistency requirement in interactive flows:

1. The user updates their profile name.
2. The API returns success.
3. The frontend calls the profile read API immediately afterward.
4. If the query is routed to a replica that has not caught up, the old name appears.

Several ways to handle this:

- Read from primary after write operations.
- Use sticky routing: for a window or logical session after a write, continue routing related reads to primary.
- Use replication tokens/positions to wait until a replica applies up to the required commit position, if supported by the database and architecture.
- Return the just-written data from the write result itself, avoiding an immediate re-query.
- Accept eventual consistency on screens that do not require read-after-write.

Choose the strategy according to business requirements. Not every read query needs primary, yet flows that immediately display write outcomes need an explicit policy.

## 5. Classifying Queries Before Routing

Do not classify solely by SQL keywords SELECT/UPDATE. A SELECT query may still require primary:

- SELECT FOR UPDATE or queries acquiring pessimistic locks.
- Reading data immediately after writing.
- Reading state used to decide a financial or sensitive business operation.
- Reading data inside a transaction needing the same snapshot as write operations.
- Reading from tables or views not yet fully applied by replicas.

Conversely, some read queries can run on replicas:

- Product catalogs or public content.
- Lag-tolerant reports.
- Search and statistics not requiring instantaneous freshness.
- Read queries independent of a just-occurred write.

Routing decisions should originate from the use case's consistency requirement, not just the SQL statement type.

## 6. Two Common Implementation Approaches in Spring Data R2DBC

Two approaches are commonly used:

**Approach A — explicitly separate read/write clients or templates**

- Create separate connection factories and `R2dbcEntityTemplate` beans for primary and replica.
- Services select the right template per use case.
- Easy to understand and test, with no dynamic router needed.
- Must manage repositories/templates for each side if using repositories.

**Approach B — use a routing ConnectionFactory**

- An `AbstractRoutingConnectionFactory` picks the target factory by route key.
- The route key is passed in Reactor Context or another context-aware mechanism.
- Can use a single group of repositories/templates backed by the routing factory.
- Requires close attention to connection acquisition timing and transaction boundaries.

No single option fits every application. Explicit client separation is usually easier to operate in systems with fewer use-case types. A routing factory can be useful when keeping a single shared persistence API with clear routing rules.

## 7. Separating Two ConnectionFactory Beans and Two R2dbcEntityTemplate Beans

With explicit separation, two connections can be configured:

~~~java
@Configuration
public class DatabaseConfiguration {

    @Bean
    @Qualifier("writerConnectionFactory")
    ConnectionFactory writerConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://writer-host:5432/shop"
        );
    }

    @Bean
    @Qualifier("readerConnectionFactory")
    ConnectionFactory readerConnectionFactory() {
        return ConnectionFactories.get(
                "r2dbc:postgresql://reader-host:5432/shop"
        );
    }

    @Bean
    @Qualifier("writerTemplate")
    R2dbcEntityTemplate writerTemplate(
            @Qualifier("writerConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    @Qualifier("readerTemplate")
    R2dbcEntityTemplate readerTemplate(
            @Qualifier("readerConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

This is a skeleton example. In real applications, configure pools, credentials, timeouts, converters, and mapping contexts appropriately for each factory. Do not open a new connection per request by calling `ConnectionFactories.get(...)` inside a service.

Services can explicitly choose where to read:

~~~java
@Service
public class ProductQueryService {

    private final R2dbcEntityTemplate readerTemplate;
    private final R2dbcEntityTemplate writerTemplate;

    public ProductQueryService(
            @Qualifier("readerTemplate") R2dbcEntityTemplate readerTemplate,
            @Qualifier("writerTemplate") R2dbcEntityTemplate writerTemplate) {
        this.readerTemplate = readerTemplate;
        this.writerTemplate = writerTemplate;
    }

    public Flux<Product> browseProducts() {
        return readerTemplate.select(Product.class).all();
    }

    public Mono<Product> findFreshProduct(Long id) {
        return writerTemplate.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Product.class
        );
    }
}
~~~

The browse method accepts eventual consistency and uses the replica. findFreshProduct requires the freshest data and uses primary. Method names and template selection make consistency requirements explicit.

## 8. Writes Always Go Through Primary

Operations that mutate data must go to primary or a writable node according to the topology:

~~~java
public Mono<Product> updatePrice(Long id, BigDecimal price) {
    return writerTemplate.selectOne(
                    Query.query(Criteria.where("id").is(id)),
                    Product.class
            )
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
            .map(product -> new Product(
                    product.id(),
                    product.name(),
                    price
            ))
            .flatMap(writerTemplate::update);
}
~~~

The example above illustrates selecting the writer template for the entire read-modify-write operation. If the business logic needs concurrency protection, wrap the whole chain in a writer connection factory transaction. Do not read from a replica and use potentially stale data to update primary when logic requires the latest state.

In real systems, a conditional UPDATE statement is often better than reading an entity and writing it back when business rules can be expressed in SQL. That reduces round trips and narrows the contention window.

## 9. Routing ConnectionFactory with AbstractRoutingConnectionFactory

Spring Framework provides `AbstractRoutingConnectionFactory` in the Spring R2DBC module. This class picks a target `ConnectionFactory` based on a lookup key resolved at connection creation time.

Routes can be defined as:

~~~java
public enum DatabaseRoute {
    WRITE,
    READ
}
~~~

The router can read the route key from Reactor Context:

~~~java
public class ReadWriteRoutingConnectionFactory
        extends AbstractRoutingConnectionFactory {

    public static final String ROUTE_CONTEXT_KEY =
            ReadWriteRoutingConnectionFactory.class.getName() + ".ROUTE";

    @Override
    protected Mono<Object> determineCurrentLookupKey() {
        return Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(
                        ROUTE_CONTEXT_KEY,
                        DatabaseRoute.WRITE
                ))
        );
    }
}
~~~

Defaulting to WRITE ensures operations without an explicit route still go to primary. This is a safer default than sending all queries to replicas.

Registering target factories:

~~~java
@Bean
@Primary
ConnectionFactory routingConnectionFactory(
        @Qualifier("writerConnectionFactory")
        ConnectionFactory writer,
        @Qualifier("readerConnectionFactory")
        ConnectionFactory reader) {

    ReadWriteRoutingConnectionFactory routing =
            new ReadWriteRoutingConnectionFactory();

    routing.setTargetConnectionFactories(Map.of(
            DatabaseRoute.WRITE, writer,
            DatabaseRoute.READ, reader
    ));
    routing.setDefaultTargetConnectionFactory(writer);
    routing.setLenientFallback(false);

    return routing;
}
~~~

`AbstractRoutingConnectionFactory` is a Spring abstraction; exact signatures and configuration details must be verified against your project's Spring Framework version. Each target factory should be created and managed as a separate bean with appropriate pools and drivers.

## 10. Setting the Route Key in Reactor Context

With the router above, a read operation can be designated as:

~~~java
public Flux<Product> browseProducts() {
    return productRepository.findAll()
            .contextWrite(context -> context.put(
                    ReadWriteRoutingConnectionFactory.ROUTE_CONTEXT_KEY,
                    DatabaseRoute.READ
            ));
}
~~~

Context propagates upstream when subscription occurs. The router reads the route key from context when it needs to acquire a connection. If no key is present, the router uses WRITE per the default configuration.

For a standalone query outside a transaction, the route key must be in the context of the publisher executing the query. For transactions, the route key must be established before the transaction manager acquires a connection.

Do not use ThreadLocal to store routes in reactive applications. A pipeline can run across multiple threads; ThreadLocal does not follow Reactor Context automatically and can leak routes across requests.

## 11. Transaction Routing: Selecting the Node Before Starting

A transaction typically acquires one connection and holds that connection until commit/rollback. Therefore, the route is decided when the transaction manager acquires the connection. You cannot start a transaction on a replica and switch to primary midway just by changing the route key.

With `TransactionalOperator`, place the route context outside the operator:

~~~java
public Mono<Product> readProductInReadTransaction(Long id) {
    Mono<Product> work = productRepository.findById(id);

    return readOnlyTransactionalOperator.transactional(work)
            .contextWrite(context -> context.put(
                    ReadWriteRoutingConnectionFactory.ROUTE_CONTEXT_KEY,
                    DatabaseRoute.READ
            ));
}
~~~

In this structure, the route key resides in the context that the transaction operator uses when requesting a connection. The transaction manager uses the routing factory; the router picks the replica at connection acquisition time. Subsequent queries in the transaction keep using the connection bound to that transaction.

Do not change the route key between operations in the same transaction expecting the connection to switch nodes. Once the transaction has started, the connection is held fixed by the transaction manager.

## 12. @Transactional(readOnly = true) Does Not Automatically Guarantee Replica Routing

`@Transactional(readOnly = true)` expresses read-only transaction intent. The read-only attribute can be used by the transaction manager/database as a hint or transaction setting, but it does not automatically mean Spring Data R2DBC will choose a replica.

To route based on read-only transaction metadata, you must implement a routing strategy aligned with the transaction lifecycle of your Spring Framework version. Check when `AbstractRoutingConnectionFactory` calls `determineCurrentLookupKey()` relative to when the transaction manager sets up the transaction synchronization context. Do not copy a ThreadLocal-based example or assume metadata is already available before the connection is created.

A more controllable option is setting the route key explicitly in Reactor Context before calling `TransactionalOperator`, as shown in the previous section, or injecting separate read/write templates.

If choosing automatic annotation-based routing, write integration tests proving:

- Read-only transactions actually acquire connections from the replica.
- Write transactions acquire connections from primary.
- One transaction uses only one node from start to finish.
- Flows with different routes do not leak context to one another.
- Proxies/AOP and advice ordering do not set the route key too late.

## 13. Do Not Route SELECT FOR UPDATE to a Replica

A SELECT statement may acquire locks:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

This query is part of a write workflow and must run on primary. Read-only replicas typically disallow row locking like this or cannot provide locking semantics equivalent to primary.

Likewise, operations that need the latest data to make a write decision—checking balances, checking stock, or verifying payment status—should use primary or an explicit consistency mechanism.

Do not route every SELECT statement to a replica. The SQL verb alone is insufficient to determine consistency requirements.

## 14. Sticky Routing After Writes

A simple strategy to support read-after-write is sticky routing: after a request or logical session performs a successful write, subsequent related reads are routed to primary for a period of time or until the workflow ends.

Conceptual example:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderService.create(command)
            .doOnSuccess(order ->
                    consistencyState.markWriterRequired(
                            command.sessionId()
                    )
            );
}
~~~

When handling a read request:

~~~java
if (consistencyState.requiresWriter(sessionId)) {
    return writerTemplate.selectOne(query, Order.class);
}

return readerTemplate.selectOne(query, Order.class);
~~~

This is pseudocode for a state manager; state can be stored in a session store, a request context token, or another consistency mechanism. Do not use a shared mutable singleton variable to flag that a user just wrote, as concurrent requests can interfere with one another.

Time-based sticky routing is only a heuristic if there is no signal that the replica has applied the commit. If lag exceeds the sticky window, reads can still be stale. For strict requirements, keep routing to primary until the workflow completes or use replication-position confirmation.

## 15. Returning Just-Written Data Instead of Re-Reading

A simple way to avoid read-after-write through a replica is returning the result of the write operation:

~~~java
public Mono<Customer> updateProfile(
        Long id,
        UpdateProfileCommand command) {

    return writerTemplate.selectOne(
                    Query.query(Criteria.where("id").is(id)),
                    Customer.class
            )
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .map(customer -> new Customer(
                    customer.id(),
                    command.name(),
                    command.email()
            ))
            .flatMap(writerTemplate::update);
}
~~~

After save/update, the publisher typically returns the written entity. The controller can use that value to build the response without issuing another SELECT through a replica.

With custom DML, `RETURNING` can be used on supported databases to retrieve the new values in the same statement. This reduces round trips and avoids reading from an out-of-date replica.

## 16. Waiting for Replicas to Catch Up via Replication Position

Some database engines expose a log position or token to compare replication progress. The general idea:

1. After committing on primary, retrieve a replication position/token.
2. Pass the token to the read step or store it in the request/session.
3. On the replica, wait until the applied position reaches or exceeds the token.
4. Only then execute the query requiring read-your-writes.

For example, PostgreSQL provides WAL LSN functions such as `pg_current_wal_lsn()` and `pg_last_wal_replay_lsn()`, allowing replay progress checks on replicas. Function names, privileges, and semantics must be verified for your PostgreSQL version. Other databases have their own replication position mechanisms.

There is no portable Spring Data R2DBC API to wait for every type of replica to reach a commit token. This is database-specific logic and typically requires a consistency coordinator component.

If the system lacks a token mechanism, routing sensitive reads to primary is simpler and easier to reason about.

## 17. Load Balancing Across Multiple Replicas

When there are multiple replicas, the router can select a factory from the reader group. Common strategies:

- Round robin.
- Random.
- Weighted routing based on capacity.
- Selecting a replica by region or network proximity.
- Selecting a replica with low lag and healthy status.

Do not distribute traffic evenly without monitoring node health. A replica applying logs slowly or under heavy load can return stale data and increase query latency.

A production system typically needs health checks, separate connection pools, lag metrics, circuit breakers, and a policy to eject unhealthy replicas from the pool. A health check that merely confirms TCP connectivity does not prove the replica is caught up on data.

## 18. Fallback from Replica to Primary

If replicas are unavailable, reads can fall back to primary, with strict limits:

- Only fall back read queries that are safe to run on primary.
- Cap fallback concurrency and load so primary does not become overloaded.
- Never silently switch an already-open transaction from a replica to primary.
- Distinguish replica connection failures from query/data/schema errors.
- Do not retry every SQL error on primary, since syntax or permission errors will still fail.

Fallback can improve availability but increases writer load. When multiple replicas fail simultaneously, all read traffic shifting onto primary can cause a cascading failure. Circuit breakers, bulkheads, or rate limits are essential.

For queries needing the freshest data, routing directly to primary from the start is clearer than trying a replica and falling back after discovering stale data.

## 19. Read/Write Splitting and Transaction Managers

If using two independent connection factories, transaction managers must be bound to the right factory:

| Use case | ConnectionFactory | Transaction manager |
| --- | --- | --- |
| Write transaction | Primary | Writer R2dbcTransactionManager |
| Read transaction on replica | Selected replica | Corresponding Reader R2dbcTransactionManager |
| Read not needing a long transaction | Reader | May not need an explicit transaction |

One `R2dbcTransactionManager` manages one `ConnectionFactory`. You cannot use a writer transaction manager to roll back statements executed on an independent replica connection factory.

With a routing factory, the transaction manager manages the routing factory and the route is selected at connection acquisition time. Once the connection is bound in Reactor Context, all operations in the transaction use that connection.

If a use case needs to read from a replica and then write to primary, treat these as two separate phases. Do not assume they form one atomic transaction when using two independent database connections. If strong consistency is needed, perform both the read and the write on primary in the same transaction.

## 20. Read-Your-Writes and Consistency Levels

Use cases can be categorized as follows:

| Requirement | Recommended Route |
| --- | --- |
| Read immediately after the user just wrote | Primary or token-based replica wait |
| Check stock/balance before writing | Primary inside a transaction |
| SELECT FOR UPDATE | Primary |
| Public listing page tolerating lag | Replica |
| Aggregated reports not needing real-time freshness | Replica/warehouse depending on load |
| Reading sensitive configuration requiring latest state | Primary |
| Long read-only flow needing a snapshot | A single replica transaction/connection with suitable isolation, if needed |

A "latest read" requirement must be defined precisely: latest at query time, latest after this request's own commit, or consistent across multiple queries in the same workflow. Each requirement may demand a different strategy.

## 21. Replica Lag and Operations

Metrics to monitor:

- Replication lag by time or log position.
- Log apply/replay time.
- Number of transactions not yet applied by the replica.
- Reader connection pool: active, idle, pending acquire.
- Query latency and error rate per replica.
- Number of queries falling back to primary.
- Percentage of requests sticky-routed to primary.

Do not rely solely on an average lag figure. A replica may show low average lag yet spike suddenly during a large transaction. You can set thresholds to remove lagging replicas from the read pool or shift specific workloads back to primary.

Lag metrics and observation queries vary across PostgreSQL, MySQL, SQL Server, and managed database services. Use the official monitoring tools of your DBMS/provider.

## 22. Securing Read Replica Connections

Create a separate database account for readers:

- Grant only SELECT on required schemas/tables.
- Grant no DDL privileges.
- Grant no INSERT/UPDATE/DELETE unless needed.
- Restrict read access to sensitive data per security requirements.

The writer account with write permissions must be managed separately. Never share a single superuser account across primary and replicas.

However, read-only permissions do not replace route policies. A SELECT query may still require primary for consistency or locking. Conversely, a misrouted UPDATE sent to a replica should be rejected by the database rather than silently redirected.

## 23. Testing Read/Write Routing

Integration tests should prove routes actually reach the intended node, not merely inspect the route key value in Reactor Context:

1. Configure separate test primary and replica instances, or two observable simulated endpoints.
2. Write a record via the writer.
3. Verify the write executed on primary.
4. Read an eventual-consistent use case and verify routing to reader.
5. Read immediately after write and verify routing to primary or replica-wait per policy.
6. Start a transaction and verify every statement in the transaction uses the same node.
7. Simulate replica lag and verify the stale-read policy.
8. Simulate reader unavailability and verify fallback/limiters.
9. Run concurrent read/write requests to verify Reactor Context does not leak between subscriptions.

Do not use a single database and assume two connection factories pointing to the same node have tested replication lag. You need a real primary/replica setup or a test harness simulating lag.

## 24. Common Mistakes

1. **Routing every SELECT to a replica.** SELECT FOR UPDATE and read-after-write may require primary.
2. **Assuming replicas are always up-to-date after commit.** Asynchronous replication creates a stale-data window.
3. **Using @Transactional(readOnly = true) and expecting automatic replica selection.** Read-only does not automatically route connections.
4. **Changing the route key mid-transaction.** The connection is already held fixed by the transaction manager.
5. **Using ThreadLocal in reactive routing.** Threads change between operators; use Reactor Context or explicit routes.
6. **Setting the route context too late.** The transaction manager may already have acquired a connection before the route key is seen.
7. **Reading from a replica and using stale data to write to primary.** Checks and updates may be based on outdated state.
8. **Falling back every replica error to primary.** Can mask SQL bugs and overload the writer.
9. **Not monitoring replication lag.** A lagging replica continues receiving traffic.
10. **Sharing one high-privilege account for reader and writer.** Increases security risk.
11. **Assuming two independent factories share a transaction.** Each transaction manager manages its own resource.
12. **Having no sticky/read-your-writes policy.** Users may see stale data right after a write operation.

## Quick Selection Rules

- Send INSERT, UPDATE, DELETE, and locking operations to primary.
- Only send SELECT to replicas when the use case accepts eventual consistency.
- Use separate read/write templates if you want explicit, easy-to-control routing.
- Use `AbstractRoutingConnectionFactory` when selecting factories via Reactor Context and after testing connection acquisition timing.
- Set the route key before the transaction starts; once a transaction acquires a connection, never switch nodes midway.
- Do not treat `@Transactional(readOnly = true)` as an automatic replica-routing mechanism.
- Return the entity from the write operation or use primary for read-after-write.
- Use sticky routing or replication-position tokens when reading from replicas must still observe prior commits.
- Monitor replication lag, health, pools, and fallback rates.
- Rate-limit fallback to protect primary when replicas fail.
- Test against a realistic primary/replica topology.

Splitting read and write queries can increase scalability in Spring Data R2DBC systems, but it adds a design requirement: defining the consistency level each use case needs. Primary is right for writes, locks, and reads requiring the freshest data; replicas suit lag-tolerant queries. When using a routing connection factory, the route must be chosen before the transaction acquires a connection and remain stable throughout the entire transaction. Combining read/write splitting with a read-after-write policy, replication lag monitoring, bounded fallback, and multi-node testing lets an application leverage replicas without showing users stale data in critical flows.
