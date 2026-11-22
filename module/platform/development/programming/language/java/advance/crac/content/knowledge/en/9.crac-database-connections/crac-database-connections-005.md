# EntityManager, Hibernate Session, and Data Access Resources

In a Java application using JPA or Hibernate, database access does not depend on a single connection object alone. A request may pass through an EntityManager, Hibernate Session, persistence context, transaction manager, JDBC connection, connection pool, statement, result set, and cache. Some objects live within the scope of a single transaction; others live for the entire application lifecycle. When using CRaC (Coordinated Restore at Checkpoint), it is necessary to distinguish these lifecycles to know which components can be retained, which must be terminated before checkpoint, and which need to be reinitialized or revalidated after restore.

EntityManager and Hibernate Session typically represent a data access unit of work. They hold a persistence context, track managed entities, and coordinate with transactions to synchronize changes to the database. They are usually short-lived and must not be shared arbitrarily across threads. Meanwhile, EntityManagerFactory and Hibernate SessionFactory are long-lived factories used to create new units of work and are typically shared within the application.

At checkpoint, an active request or transaction may leave unfinished state in memory and connections. Therefore, the application needs to stop accepting new work, complete or roll back running transactions, close application-owned EntityManagers/Sessions, and handle the connection pool according to supported integrations. After restore, new requests need to create new persistence contexts and transactions while using valid connections.

## 1. EntityManager in JPA

JPA (Jakarta Persistence, formerly commonly known as Java Persistence API) defines a standard API for mapping Java objects to relational data. EntityManager is the primary interface for the application to interact with the persistence context.

An EntityManager typically provides the following operations:

- Find an entity by primary key using find().
- Place a new entity into the persistence context using persist().
- Mark an entity for deletion using remove().
- Synchronize entity state with the database using flush().
- Find entities using JPQL, Criteria API, or native queries.
- Refresh or detach an entity from the persistence context using refresh() and detach().
- Close an application-created EntityManager using close().

EntityManager is not merely a wrapper around a JDBC Connection. It manages a persistence context, tracks entities, relationships between entities, dirty checking state, and how changes are synchronized with the database. When the application calls persist() or modifies a managed entity, the SQL statement might not be sent immediately. The provider usually holds changes in memory and executes SQL upon flush or at an appropriate point in the transaction.

Example:

```java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product();
    product.setName("Keyboard");
    product.setPrice(45.00);

    em.persist(product);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

The example illustrates an application-created and application-closed EntityManager. In a container-based or Spring application, EntityManager may be injected as a proxy and its actual lifecycle managed by the framework or transaction manager. In that case, this manual create/close code must not be mechanically applied to a container-managed EntityManager.

## 2. Hibernate Session

Hibernate ORM is a popular persistence provider that implements JPA and also provides its own native API. Hibernate Session is the primary working interface in the native API. Conceptually, Session and EntityManager serve a similar role: representing a persistence context and a unit of work with the database.

Depending on the Hibernate version and integration approach, an application may work through JPA's EntityManager or through the Session API. When using Hibernate as the JPA provider, EntityManager is typically implemented on top of Hibernate's Session mechanism. However, one should refer to the API of the exact version rather than assuming all versions have identical type relationships or behavior.

Session provides native operations such as:

- get() or find() to load an entity.
- persist(), save(), or corresponding APIs to save an entity, depending on the version.
- remove()/delete() to delete an entity, depending on the API.
- createQuery() to create HQL/JPQL or queries via Hibernate APIs.
- flush() to synchronize the persistence context with the database.
- clear() to detach all entities from the persistence context.
- close() to end the Session.

Example using the Session API:

```java
Session session = sessionFactory.openSession();
Transaction tx = null;

try {
    tx = session.beginTransaction();

    Product product = new Product();
    product.setName("Keyboard");
    product.setPrice(45.00);

    session.persist(product);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx != null && tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    session.close();
}
```

In the example, the application opens a Session, begins a transaction, performs changes, commits or rolls back, and finally closes the Session. One must use the exact API and transaction type of the Hibernate version in the project.

## 3. How do EntityManager and Session differ?

EntityManager is the standard Jakarta Persistence API. Session is Hibernate's native API. When using Hibernate as the provider, both usually lead to the same persistence context mechanism, but Session can provide additional Hibernate-specific capabilities.

| Criterion | JPA EntityManager | Hibernate Session |
|---|---|---|
| API Source | Jakarta Persistence standard | Hibernate native API |
| Goal | Portability across JPA providers | Hibernate-specific capabilities and features |
| Persistence context | Yes | Yes |
| Dirty checking and first-level cache | Yes | Yes |
| Transaction | Coordinates with resource-local or JTA transactions | Coordinates with transactions per Hibernate/JTA configuration |
| Query | JPQL, Criteria, native SQL | HQL/JPQL and Hibernate query APIs |
| Lifecycle | Managed by application or container depending on creation method | Managed by application or integration framework |
| Interchangeability | Standard API, suitable when reducing provider coupling | Suitable when native API and Hibernate features are needed |

One should not create both an EntityManager and a Session independently for the same task just thinking they are two mandatory layers. If the application uses JPA, prefer EntityManager in business code and only obtain Session via the unwrap mechanism when Hibernate features are truly needed. If the application uses native Hibernate, manage Session according to Hibernate's lifecycle.

## 4. What is a persistence context?

A persistence context is the scope within which the provider manages entities. A managed entity (*managed*) is tracked. When attributes change, the provider can detect changes via dirty checking and synchronize them to the database during an appropriate flush.

A persistence context typically has a first-level cache. If an entity has already been loaded in the same context, a subsequent access by the same key can return the same Java instance without re-reading the database. This helps guarantee entity identity within a unit of work.

Entity states are commonly described as follows:

| State | Meaning |
|---|---|
| New / transient | New object, not yet managed by a persistence context |
| Managed / persistent | Entity is in the persistence context and is being tracked |
| Detached | Entity was previously managed but has been detached from the context or the context has closed |
| Removed | Entity is marked for deletion in the persistence context |

Example:

```java
Product product = em.find(Product.class, 10L); // managed
product.setPrice(49.00);                       // dirty checking
em.flush();                                    // synchronize SQL
em.detach(product);                            // detached
```

When an EntityManager or Session closes, its persistence context ends. Entities are no longer managed in that context. This is important for CRaC: one should not keep a long-lived persistence context containing entities, lazy proxies, or unfinished transaction state across a checkpoint and assume it can continue working as before.

## 5. EntityManager/Session are not application-wide shared objects

A typical EntityManager or Hibernate Session is not thread-safe. It represents a unit of work with a stateful persistence context. Multiple threads using the same Session concurrently can cause race conditions, entity state errors, transaction errors, or JDBC resource errors.

The common model is:

- EntityManagerFactory or SessionFactory is shared across the application.
- Each request, transaction, or unit of work has its own EntityManager/Session.
- The transaction is started and ended within a clear scope.
- The EntityManager/Session is closed or returned to the framework after the unit of work finishes.

In a container environment, the application may inject an EntityManager proxy. The proxy looks up or obtains the EntityManager appropriate for the current transaction/thread. This does not mean the actual persistence context object can be shared across all threads. Follow the framework's transaction and concurrency rules.

Do not store an EntityManager or Session in a static field, shared singleton, or application-wide object cache for reuse across requests. Also do not pass them into an executor for another thread to continue operating on unless the framework explicitly supports that model.

## 6. EntityManagerFactory and SessionFactory have a different lifecycle

EntityManagerFactory and SessionFactory are factories that create EntityManagers or Sessions. They are usually created once when the application starts and used throughout the application lifecycle.

These factories may hold:

- Entity mapping and schema metadata.
- Provider configuration and internal services.
- Query plan cache or metadata cache.
- Second-level cache if enabled.
- Connection provider or reference to a DataSource.
- Transaction management components and framework integrations.
- Certain threads or internal resources depending on the provider and configuration.

Typically, factories are designed to be shared across multiple threads, whereas EntityManager/Session are short-lived objects. Factories have significant initialization overhead and should not be recreated per request.

When using CRaC, one should not assume EntityManagerFactory or SessionFactory must be closed before every checkpoint by default. It is necessary to review the CRaC integration of the exact provider version, cache, connection provider, and framework. In some cases, the factory can be retained after restore once all dependent resources are handled properly. In other cases, the integration requires closing or recreating certain components. The decision must be based on documentation and testing, not general assumptions.

## 7. Data resources behind EntityManager and Session

An ORM operation may use multiple underlying resources:

### 7.1. DataSource and connection pool

DataSource provides JDBC Connections. The connection pool holds physical connections and lends connections to transactions. The pool typically outlives an EntityManager or Session.

Physical connections may be closed by the database, time out, lose their socket, or become invalid after the process is checkpointed and restored. Therefore, use the pool's CRaC integration if available; otherwise, determine how the pool pauses, closes connections, and creates new connections after restore.

### 7.2. JDBC Connection

A Connection is typically acquired when a transaction begins or when the provider needs to access the database. The Connection is tied to the transaction, isolation level, auto-commit, session variables, and database-side state.

One should not checkpoint while a transaction is active and assume the connection will continue as before after restore. Active transactions must be completed or rolled back before checkpoint according to application rules.

### 7.3. Statement, PreparedStatement, and ResultSet

These JDBC objects may hold driver-side or database-side resources. An open ResultSet may depend on a server-side cursor, connection, and read position. Close or complete them before checkpoint. For streaming queries or large batch processing, persist progress durably and create a new query after restore instead of keeping the old cursor.

### 7.4. Transaction and transaction manager

A transaction has state across the application, driver, and database. An active transaction should not be treated as state that can be safely cloned. Before checkpoint, stop creating new transactions and wait for running transactions to finish or roll back according to policy. If using JTA or distributed transactions, comply with the corresponding coordinator and transaction manager.

### 7.5. Cache

Hibernate has a first-level cache within each persistence context. The second-level cache may reside in application memory or use an external cache provider. The query cache also has its own lifecycle and invalidation rules.

The first-level cache ends along with the EntityManager/Session. The second-level cache may be retained if the provider supports it and the data remains valid, but invalidation, cluster consistency, and cache provider resources must be considered. Do not treat an in-heap cache of a single process as the authoritative source of data.

## 8. What can happen if checkpointing while EntityManager or Session is still active?

Suppose a request performs:

1. Opens an EntityManager.
2. Begins a transaction.
3. Loads an entity and modifies some properties.
4. The provider holds the entity in the persistence context and may have acquired a JDBC Connection.
5. The application is checkpointed before the transaction commits.

After restore, many things are likely no longer in their original state:

- The database may have rolled back the transaction when the connection was dropped.
- Connections in the pool may have been closed by the server or become invalid.
- The persistence context in the heap may still contain entities with uncommitted changes.
- The provider may hold references to old JDBC resources or transactions.
- Lazy proxies or collections may require the old closed Session.
- The in-flight request may not be able to resume from the exact business boundary.

If the application continues using that persistence context, it may encounter exceptions, stale data, invalid transactions, or duplicate write operations. CRaC does not turn database transactions into transactions that can be paused and resumed across all environments.

The safe design is to take checkpoints when no data unit of work is active. After restore, each new request or job creates a new persistence context and transaction.

## 9. Flush, commit, and close in JPA/Hibernate

These three operations have different meanings:

| Operation | Meaning |
|---|---|
| flush() | Synchronizes persistence context changes to the database via SQL |
| commit() | Completes the transaction via the transaction manager/database |
| close() | Ends the EntityManager/Session and releases resources within its scope |

flush() is not synonymous with commit(). SQL may have been sent to the database, yet the transaction is still uncommitted. If the transaction rolls back, changes can still be discarded. Conversely, commit usually triggers a flush before completing the transaction, depending on flush mode and provider.

Before checkpoint, one should not simply call em.flush() and consider the data safe. Identify the transaction owner and commit or roll back according to business boundaries. After the transaction ends, close application-owned EntityManagers/Sessions.

Example:

```java
EntityManager em = entityManagerFactory.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    // Perform changes within a unit of work.
    updateProduct(em, 10L);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

In real applications, the transaction manager may own the transaction and EntityManager. In that case, let the framework complete the transaction and close the persistence context according to its configured lifecycle. Do not manually call commit/close on a container-managed object if the framework's contract does not allow it.

## 10. Managing EntityManager across application models

### 10.1. Application-managed EntityManager

The application calls EntityManagerFactory.createEntityManager() and is responsible for closing the EntityManager. This model makes the lifecycle easy to see and can suit Java SE applications or certain standalone components.

Each unit of work should create an EntityManager, start a transaction, process, and close in a finally or equivalent try/finally block. Do not store the EntityManager after the unit of work completes.

### 10.2. Container-managed EntityManager

In Jakarta EE applications or container environments, EntityManager is injected and its lifecycle is managed by the container. The persistence context may be bound to a transaction or specified scope. The application does not manually close a container-managed EntityManager.

When using CRaC, work through the container's lifecycle integration. The coordinator must prevent new requests and wait for current transactions to finish; the container or provider performs the corresponding operations on the persistence context.

### 10.3. Spring-managed EntityManager

In Spring applications, EntityManager is typically injected via a proxy and bound to the current transaction. @Transactional controls the transaction boundary; Spring manages binding/unbinding the appropriate resources.

Do not hold an EntityManager proxy or transaction-scoped object in a background thread and use it after the transaction has ended. With CRaC, stop ingress and background tasks, let the transaction manager finish transactions, and let Spring/provider perform cleanup according to the corresponding integration.

### 10.4. Hibernate Session opened per request

If the application uses native Session, identify where the Session is opened and where it is closed. A common pattern is one Session per unit of work, with the transaction explicitly ended and the Session closed immediately afterward. Do not use Session as a singleton.

## 11. Procedure for preparing JPA/Hibernate resources before checkpoint

A general procedure should coordinate requests, the transaction manager, the persistence provider, and the connection pool.

1. Stop accepting new requests and stop consumers/schedulers that generate database access work.
2. Wait for running requests, jobs, and message handlers to finish within a timeout.
3. Confirm no active transactions remain within the application scope.
4. Close remaining open application-managed EntityManagers/Sessions; let container-managed contexts be cleaned up by the container per its lifecycle.
5. Close any remaining cursors, ResultSets, stream queries, and JDBC resources.
6. Handle the connection pool and clients according to the CRaC integration of the exact version.
7. Confirm whether the factory/cache can be retained or needs recreation per provider documentation.
8. Allow checkpointing only when the coordinator receives confirmation from the components owning data resources.

Do not write a generic callback that blindly calls close() on every object named EntityManager. Some objects may be container-managed proxies; some may already be closed; some may belong to active transactions. Owners and lifecycle types must be distinguished.

## 12. Role of CRaC Resource and coordinator

CRaC provides the Resource API with two callbacks:

- beforeCheckpoint(...): prepare resources before saving process state.
- afterRestore(...): restore or recreate resources after recovery.

For database access, multiple components usually must coordinate. A coordinator can stop ingress, wait for transactions to finish, and ask owners of pools/clients to prepare resources. Each owner manages the details of the objects it created.

Responsibility model:

| Component | Pre-checkpoint responsibility | Post-restore responsibility |
|---|---|---|
| HTTP server / message listener | Stop accepting new work, drain requests/messages | Reopen traffic after readiness |
| Transaction manager | Wait for transactions to finish or roll back per policy | Start new transactions for new work |
| EntityManager/Session owner | Close application-owned persistence contexts | Create new contexts when units of work arrive |
| DataSource/connection pool owner | Stop lending connections, close or prepare pool per integration | Create/validate new connections |
| EntityManagerFactory/SessionFactory owner | Verify factory can be retained per provider | Recreate if required by integration |
| Cache provider owner | Flush/invalidate or retain cache per policy | Validate cache health and connections |
| Coordinator | Confirm components have quiesced | Allow readiness only when dependencies are ready |

The example below illustrates a coordinator adapter at a high level. The methods of DatabaseLifecycle are an application-defined contract; they are not standard JPA or Hibernate APIs.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseCheckpointResource implements Resource {
    private final DatabaseLifecycle lifecycle;

    public DatabaseCheckpointResource(DatabaseLifecycle lifecycle) {
        this.lifecycle = lifecycle;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        lifecycle.stopNewWork();
        lifecycle.awaitTransactionsToFinish();
        lifecycle.closeApplicationManagedPersistenceContexts();
        lifecycle.prepareConnectionProvider();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        lifecycle.restoreConnectionProvider();
        lifecycle.validatePersistenceInfrastructure();
        lifecycle.allowNewWork();
    }

    public interface DatabaseLifecycle {
        void stopNewWork() throws Exception;
        void awaitTransactionsToFinish() throws Exception;
        void closeApplicationManagedPersistenceContexts() throws Exception;
        void prepareConnectionProvider() throws Exception;
        void restoreConnectionProvider() throws Exception;
        void validatePersistenceInfrastructure() throws Exception;
        void allowNewWork() throws Exception;
    }
}
```

This example describes coordination responsibilities rather than an implementation that can be plugged directly into every application. In practice, ensure allowNewWork() runs only after all essential resources have recovered. If a step fails, the application must remain unready and report errors clearly. Traffic must not be opened simply because the afterRestore() callback has started.

## 13. EntityManagerFactory and SessionFactory after restore

Factories are typically used throughout the application lifecycle and may contain valuable metadata/caches. However, they may reference a connection provider, cache provider, transaction platform, or internal services. Therefore, the question is not just "is the factory in the heap?" but "are all dependencies used by the factory valid after restore?".

There are three design approaches, depending on provider and version:

- **Retain the factory and restore dependencies:** Only suitable when the provider and integrations are confirmed to support CRaC, and underlying connections or services are restored properly.
- **Recreate certain dependencies:** Retain metadata/factory if supported, but recreate the pool or clients used by the factory.
- **Close and recreate the factory:** Choose only when required by provider documentation or test results. Account for initialization cost, lost cache, and recreation order of dependent beans.

Do not arbitrarily close SessionFactory/EntityManagerFactory inside a callback if the framework manages them. Closing the factory may break services holding references or prevent the container from continuing operation. Place responsibility on the component that creates the factory and follow the framework's lifecycle.

## 14. Cache and data consistency

Hibernate has a first-level cache within each Session. JPA has the corresponding persistence context in EntityManager. These caches are tied to a unit of work and end when the context closes.

The second-level cache is typically shared across Sessions within the same factory. It may reside in the process heap or be managed by an external cache provider. During checkpoint/restore, answer:

- Does the cache contain data that changed after the checkpoint?
- Can the database be updated by another process while the image is stored?
- Does the cache provider support CRaC?
- Does the cache need to reconnect or rejoin the cluster after restore?
- Do TTL and invalidation continue accurately?
- Do multiple instances restored from the same checkpoint create identical local caches that later diverge?

If the cache holds regenerable data, invalidating or warming up again after restore may be simpler than trying to preserve all state. If using a distributed cache, restore connections and check cluster membership. Do not use an in-heap cache as the source of truth for business state.

## 15. Streaming queries, cursors, and large data processing

Some APIs return streams or cursors to process large datasets without loading the entire result into memory. For example, Hibernate may support scroll or stream queries depending on the API; JDBC ResultSet may hold a database-side cursor.

These resources typically depend on the Session, transaction, and connection. Do not keep open cursors across a checkpoint. Instead:

1. Stop accepting new work.
2. Complete or close open streams/cursors.
3. Save processing progress by a durable key or sequence.
4. Close the persistence context and transaction.
5. After restore, open a new transaction and query from the confirmed position.

Be careful with offset pagination on tables with concurrent changes. If data is inserted/deleted during checkpointing, offsets may skip or double-read rows. Keyset pagination by a stable key or an appropriate snapshot/lease mechanism may be safer, depending on business requirements.

## 16. Transactions and risks of data loss or duplication

Checkpointing does not create a distributed transaction between the Java heap and the database. A request may commit to the database successfully without recording the result in application state, or update state in the heap before the transaction commits.

Example with duplication risk:

1. Request creates an order and the database commit succeeds.
2. The application has not yet recorded that the request completed.
3. The process is checkpointed or stopped in an unsynchronized state.
4. After restore, the work is re-submitted.
5. Without an idempotency key, a second order may be created.

Example with loss risk:

1. The application increments a progress counter in the heap.
2. The database transaction has not committed yet.
3. The checkpoint saves the incremented counter.
4. After restore, the application continues from the next record.
5. The uncommitted database change was rolled back and is not re-submitted.

Mitigation:

- Use stable idempotency keys for operations with side effects.
- Save progress in the same transaction as business changes whenever possible.
- Use a transactional outbox when coordinating database updates and event publishing.
- Acknowledge messages or advance offsets only after the transaction has committed per contract.
- Do not include active transactions in a checkpoint.
- When commit outcome is ambiguous, look up state by operation ID before retrying.

## 17. Common mistakes when using JPA/Hibernate with CRaC

**Keeping EntityManager or Session in a singleton.** Persistence contexts are stateful and not thread-safe. Create contexts per transaction or unit of work and end them per lifecycle.

**Sharing a Session across multiple threads.** This can cause race conditions and transaction errors. Each unit of work needs its own context.

**Checkpointing while a transaction is active.** The database may roll back or the connection may become invalid. Drain work and end transactions before checkpointing.

**Assuming flush() is commit().** Flush only synchronizes the persistence context to the database; the transaction can still roll back. Let the transaction manager commit or roll back.

**Manually closing a container-managed EntityManager.** This can break the framework-managed lifecycle. Distinguish application-managed from container-managed.

**Keeping a ResultSet or stream query across a checkpoint.** Cursors depend on the connection/session and may become invalid. Close cursors and save progress durably.

**Closing the factory without coordinating with the framework.** SessionFactory or EntityManagerFactory may be used by multiple beans. Manage them at the proper owner and per the provider's integration.

**Keeping a connection pool with old sockets.** Connections may have been closed by the database. Use a supported integration or recreate the pool/connections per guidelines.

**Trusting that an in-heap cache is always fresh.** The database may change while the checkpoint is stored. Verify TTL, invalidation, and consistency after restore.

**Opening traffic before the database is ready.** Restore callbacks may not have finished creating the pool or validating connections. Readiness must wait for the persistence infrastructure to be operational.

## 18. Testing procedure for JPA/Hibernate after restore

A test should use the exact CRaC JDK, provider version, connection pool, database, and target deployment environment.

### Basic lifecycle test

1. Start the application and confirm EntityManagerFactory/SessionFactory is created.
2. Send a request to create or update data, confirming the transaction commits.
3. Instruct the application to quiesce and take a checkpoint.
4. Restore the process from the checkpoint.
5. Confirm the connection pool or connection provider has recovered.
6. Send a new request, create a new EntityManager/Session, and execute a query.
7. Check database results, logs, metrics, and readiness.

### In-flight transaction test

Create a request that holds a transaction for a controllable duration. Request a checkpoint while the request is running. The coordinator must stop accepting new work and wait for the transaction to complete or roll back per policy. Confirm checkpointing does not occur while the transaction is active.

### Database disconnect test

After taking a checkpoint, proactively close or expire connections in the test environment before restoring. Confirm the application creates new connections, does not reuse old sockets, and does not report ready while the pool is not operational.

### Stream query test

Open a streaming query, process part of the data, and then request quiesce. Confirm the cursor is closed, progress is saved properly, and after restore a new query resumes from the appropriate position without unexpected skips or duplicate processing.

### Multi-instance test

If restoring multiple instances from the same image, confirm each instance creates its own persistence contexts and connections. Verify the total connection pool does not exceed database limits, transactions are not shared, and caches remain consistent by design.

Metrics to collect:

- Time from restore until DataSource is ready.
- Time until the first successful query.
- Active/idle connection count and connection validation failure count.
- Active transaction count at checkpoint preparation time.
- EntityManager/Session error count and SQL error count after restore.
- EntityManagerFactory/SessionFactory creation time if recreation is required.
- Cache hit/miss and invalidation.
- p95/p99 latency of database-accessing requests.
- Transaction rollback, retry, and duplicate business operation counts.

## 19. Checklist for EntityManager, Session, and data resources

- [ ] Have EntityManager/Session been distinguished from EntityManagerFactory/SessionFactory?
- [ ] Has it been identified which EntityManager/Session are application-managed and which are container-managed?
- [ ] Does each persistence context have a clear transaction or unit-of-work scope?
- [ ] Is any EntityManager/Session held in a static field, singleton, or passed across threads?
- [ ] Have the owners of DataSource, connection pool, transaction manager, and cache provider been identified?
- [ ] Are requests, consumers, and schedulers drained before checkpoint?
- [ ] Are there no active transactions or open cursors/ResultSets/stream queries at checkpoint?
- [ ] Are application-owned EntityManagers/Sessions closed properly?
- [ ] Do the connection pool and provider have CRaC integration suitable for the version in use?
- [ ] Is the decision to retain or recreate EntityManagerFactory/SessionFactory based on provider documentation?
- [ ] Does the cache have an invalidation policy and freshness check after restore?
- [ ] Do transaction progress and side effects have idempotency or durability mechanisms?
- [ ] Does readiness wait for database connections and a successful test query?
- [ ] Have restore, database disconnect, transaction drain, and stream query scenarios been tested?

## Conclusion

EntityManager and Hibernate Session represent a persistence context and are typically tied to a short-lived transaction or unit of work. They track entities, dirty checking, first-level cache, and coordinate data synchronization with the database. EntityManagerFactory and SessionFactory are long-lived factories, typically shared, with a different lifecycle. Behind these objects lie DataSource, connection pools, JDBC connections, transaction managers, cursors, caches, and background services.

To use CRaC safely, finish active units of work before checkpointing, do not carry unfinished EntityManagers/Sessions or transactions across restore, and manage the connection pool according to supported integrations. After restore, create new persistence contexts for new requests, verify connections and caches, and only then open traffic. When the owner and lifecycle of each component are clearly defined, applications can leverage checkpoint/restore while preserving data consistency.
