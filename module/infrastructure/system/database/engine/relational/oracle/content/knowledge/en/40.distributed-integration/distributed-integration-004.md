# XA Transactions from Java and Global Transaction Management Options

## 1. Why Do Java Applications Need XA Transactions?

An ordinary transaction typically modifies data within a single database connection. For example, an application updating orders and inventory in the same Oracle Database can use a local transaction managed by the JDBC connection:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        updateOrder(connection);
        updateInventory(connection);
        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
```

When a business workflow must update multiple independent resource managers, a local transaction on a single connection is insufficient to guarantee that all commit together or all roll back together. For example:

- Writing an order to Oracle Database and sending a message to a JMS broker.
- Updating data in two independent Oracle Databases.
- Writing data to Oracle and another database within the same business operation.

If the application commits Oracle first and then sending the message fails, the database and message broker become inconsistent. If it sends the message first and the database rolls back, a consumer may receive a notification about an uncommitted transaction.

**XA (eXtended Architecture)** defines the protocol for coordinating transactions between a transaction manager and multiple resource managers. In Java, JTA/Jakarta Transactions provides the global transaction management API; JDBC XA provides the interface for the database to participate in that transaction.

The goal of XA is to allow the transaction manager to coordinate participating resources toward a unified commit/rollback decision, typically via two-phase commit (2PC).

## 2. Components in an XA Architecture

An XA system has three primary roles:

| Component | Role | Example in Java/Oracle |
|---|---|---|
| Transaction Manager (TM) | Creates global transactions, enlists resources, orchestrates prepare/commit/rollback, and recovers incomplete transactions | JTA implementation in an application server or standalone TM |
| Resource Manager (RM) | Manages data/resources and executes transaction branches per TM commands | Oracle Database, XA-capable JMS provider |
| Application | Defines business boundaries and executes operations on resources | Java service, EJB, Spring application |

Overall flow:

```text
Java application
       |
       | begin / commit / rollback
       v
Transaction Manager (JTA)
       |
       +-------------------------+
       |                         |
       v                         v
Oracle XA resource          JMS XA resource
       |                         |
       v                         v
Oracle Database             Message Broker
```

The application asks the TM to begin a global transaction. When the application uses an XA connection, the TM enlists the corresponding `XAResource` into the transaction. Upon commit, the TM coordinates all enlisted resources. The application does not commit each database/broker independently.

### 2.1. Transaction Manager

The Transaction Manager is the coordinator of the global transaction. It is responsible for:

- Creating global transaction identifiers (`Xid`) and managing transaction state.
- Enlisting/delisting participating XA resources.
- Setting timeouts and coordinating transaction boundaries.
- Executing prepare and then commit/rollback per the XA protocol.
- Writing durable logs of decisions and transaction states for crash recovery.
- Running recovery when the TM or an RM restarts.

The TM may live inside an application server or run as a standalone service/library. The choice of TM affects datasource configuration, transaction log persistence, failover, and operational procedures.

### 2.2. Resource Manager

A Resource Manager owns the resources protected by the transaction. Oracle Database is one RM; a JMS broker is another RM if the broker supports XA. Each RM must have an XA implementation so the TM can start, end, prepare, and complete transaction branches.

A standard JDBC `DataSource` only provides local JDBC connections. To participate in JTA/XA, the application needs an XA-capable datasource managed by the TM, usually configured from the driver's `XADataSource`.

### 2.3. Application and Transaction Boundaries

The application decides where a business operation starts and ends. For instance, creating an order might include inserting the order, reserving inventory, and sending a message. These operations belong in the same global transaction if the business requirement demands atomicity across resources.

The application calls the JTA API or uses declarative transactions such as EJB container-managed transactions or Spring transaction abstractions configured with a JTA transaction manager. The TM handles XA communication with each resource.

## 3. XA in Java: Key APIs

### 3.1. JTA / Jakarta Transactions

JTA is the Java API for applications or containers to work with global transactions. Depending on the platform:

- Older Java EE/Jakarta EE versions use the `javax.transaction` namespace.
- Jakarta EE 9 and later moved the JTA API to the `jakarta.transaction` namespace.
- Java SE XA interfaces such as `javax.transaction.xa.XAResource` and `javax.transaction.xa.Xid` remain in the `javax.transaction.xa` package.

Do not confuse `jakarta.transaction` with `javax.transaction.xa`: the JTA namespace change did not move Java SE XA interfaces into `jakarta.transaction.xa`.

Common JTA APIs:

| API | Role |
|---|---|
| `UserTransaction` | Allows the application to programmatically begin, commit, or roll back transactions |
| `TransactionManager` | API for managing transaction association, suspend/resume, and resource enlistment; typically for containers/frameworks |
| `Transaction` | Represents the current transaction, supporting resource enlistment/delistment per the JTA contract |
| `Synchronization` | Callbacks before/after transaction completion |
| `Status` | States such as active, marked rollback, preparing, committed, or rolled back |

In container-managed applications, business code normally does not need to call `TransactionManager` directly. The container or framework manages transaction context and resource enlistment.

### 3.2. JDBC XA Interfaces

JDBC XA interfaces reside in Java SE:

- `javax.sql.XADataSource`: factory creating XA connections.
- `javax.sql.XAConnection`: wrapper providing a connection and an `XAResource`.
- `javax.transaction.xa.XAResource`: resource interface used by the TM to coordinate the XA branch.
- `javax.transaction.xa.Xid`: identifier of a global transaction branch.

Relationship model:

```text
XADataSource
    |
    +-- XAConnection
            |
            +-- getConnection() -> JDBC Connection
            |
            +-- getXAResource() -> XAResource
```

In production environments, the application server or XA pool typically holds the `XAConnection` and enlists the `XAResource`. Business code normally receives a TM-managed JDBC `Connection`, rather than calling `XAResource.start()`, `prepare()`, or `commit()` itself.

### 3.3. Xid and Transaction Branches

`Xid` identifies a transaction branch. It consists of:

- `formatId`: Xid format identifier.
- `globalTransactionId`: global transaction identifier.
- `branchQualifier`: branch identifier at a resource manager.

A single global transaction can have multiple branches—for example, one branch for Oracle and one branch for JMS. The TM stores the mapping of branches to the overall transaction decision. `Xid` is technical metadata for TM and RM coordination, not a business ID for applications to construct and commit arbitrarily.

## 4. Two-Phase Commit (2PC)

### 4.1. Phase 1: Prepare

When the application requests to commit the global transaction, the TM asks each RM to prepare to commit via `prepare` on the `XAResource`.

- The RM checks whether the transaction branch can commit.
- The RM records the prepared state durably enough to complete after a restart.
- The RM votes `XA_OK` if ready to commit, or `XA_RDONLY` if the branch is read-only and requires no further commit phase.
- If an RM reports an error or fails to prepare, the TM can decide to roll back the entire transaction.

### 4.2. Phase 2: Commit or Rollback

If all RMs that need to commit prepare successfully, the TM durably logs the commit decision and sends commit to all branches. If preparation fails, the TM decides rollback and sends rollback to all branches.

```text
Application requests commit
            |
            v
Transaction Manager records transaction state
            |
            v
       PREPARE phase
            |
      +-----+------+
      |            |
  All vote OK   A branch fails
      |            |
      v            v
  COMMIT decision  ROLLBACK decision
      |            |
      v            v
  Commit branches  Roll back branches
      |            |
      +-----+------+
            v
       Completion
```

### 4.3. Why Is Prepare Needed Before Commit?

If the TM sent commit immediately to Oracle and then to JMS, a network failure in between could leave one resource committed while the other never received the decision. Prepare creates a durable state where the RM commits to being able to complete the branch once the TM issues the global decision.

2PC provides atomicity across XA resources assuming the RMs/TM follow the protocol properly and recovery is operated correctly. It does not turn external systems into XA resources; an ordinary HTTP API, filesystem, or email service does not automatically participate in 2PC.

### 4.4. One-Phase Optimization

If a global transaction has only one XA resource actually participating, the TM can use one-phase commit optimization instead of two-phase prepare and commit. This is an optimization supported by XA; it does not mean the application can arbitrarily bypass the TM.

When multiple resource managers exist, 2PC is typically required to synchronize the decision. Some TMs offer last-resource optimization to coordinate one non-XA resource, but this mechanism has atomicity limitations and depends on the TM. It should not be treated as equivalent to a system where every resource supports XA.

## 5. Configuring Oracle JDBC XA

### 5.1. Oracle XADataSource

Oracle JDBC provides an XA datasource implementation, commonly used via `oracle.jdbc.xa.client.OracleXADataSource` in client-side configurations. API example for initializing the datasource:

```java
import oracle.jdbc.xa.client.OracleXADataSource;

OracleXADataSource xaDataSource = new OracleXADataSource();
xaDataSource.setURL(
    "jdbc:oracle:thin:@//db-host.example.com:1521/app_service"
);
xaDataSource.setUser("APP_USER");
xaDataSource.setPassword(secretFromVault);
```

This snippet illustrates datasource configuration only. In real applications, do not manage the `XAConnection` lifecycle yourself with this code and commit each resource manually. Register the XA datasource with a supported transaction manager/XA connection pool; the TM manages borrowing connections, enlisting resources, preparing, committing, rolling back, and recovery.

Class names, constructors, configuration methods, and driver artifacts must be verified against the deployed Oracle JDBC version. Use a driver compatible with your Oracle Database, JDK, and application server. Never mix different driver JAR versions arbitrarily.

### 5.2. Registering the XA Datasource with the Transaction Manager

In an application server, the datasource is typically declared as an XA datasource and bound to a JNDI name. The TM uses the `XADataSource` to create connections and enlist `XAResource` automatically when the application accesses the resource inside a global transaction.

For standalone Java applications, you need a compatible TM and XA pool that integrate together. Components to configure include:

- Oracle XA datasource/driver.
- A unique and stable resource name in the TM configuration.
- Connection pool managing XA connections.
- Transaction manager and durable transaction log store.
- Securely managed database credentials.
- Timeouts, recovery credentials, and Oracle reachability after restart.

Do not create a regular `DriverManager.getConnection()` and expect the TM to automatically turn that local JDBC connection into an XA resource. The datasource must genuinely support XA and be properly registered with the TM.

### 5.3. Transaction Boundary Example Using UserTransaction

In an environment providing `UserTransaction`, code can begin and complete a global transaction:

```java
import jakarta.transaction.UserTransaction;

public final class OrderService {
    private final UserTransaction userTransaction;
    private final DataSource oracleXaDataSource;
    private final ConnectionFactory xaJmsConnectionFactory;

    public void placeOrder(Order order) throws Exception {
        userTransaction.begin();
        try {
            try (Connection connection = oracleXaDataSource.getConnection()) {
                insertOrder(connection, order);
                reserveInventory(connection, order);
            }

            try (JMSContext context = xaJmsConnectionFactory.createContext()) {
                context.createProducer().send(
                    context.createQueue("orders.created"),
                    toMessage(order)
                );
            }

            userTransaction.commit();
        } catch (Exception ex) {
            try {
                userTransaction.rollback();
            } catch (Exception rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}
```

This is an architectural example, not a standalone runnable class: `DataSource` and `ConnectionFactory` must be TM-managed XA-capable resources; helpers, JNDI lookup/injection, and exception mapping depend on the runtime. In some Jakarta Messaging setups, a container-configured XA connection factory is required; `JMSContext` and resource management must follow the application server/provider contract. Never manually call `commit()` on a local session/connection participating in a global transaction.

In a container, declarative transactions can avoid manual `begin/commit` calls:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);
    inventoryRepository.reserve(order);
    orderEventPublisher.publish(order);
}
```

Annotations only create a global transaction if the application is configured with a JTA transaction manager and all datasources/messaging resources to coordinate are XA-enlisted. If Spring is using a local `DataSourceTransactionManager` or `JpaTransactionManager` for a single datasource, the annotation does not automatically combine multiple resources into an XA transaction.

### 5.4. Do Not Call the XAResource Protocol Directly in Business Code

Methods like `XAResource.start`, `end`, `prepare`, `commit`, `rollback`, `recover`, and `forget` belong to the protocol controlled by the TM. Business code must not call them directly on pooled connections. Doing so can break transaction association, leave the TM unaware of branch state, or corrupt recovery.

Business code should only define transaction boundaries through JTA/container APIs; resource enlistment and the XA branch lifecycle are managed by the TM.

## 6. Transaction Management in Spring and Jakarta EE

### 6.1. Spring with a JTA Transaction Manager

Spring supports global transactions via `JtaTransactionManager` when a JTA provider and XA datasources are configured. When used:

```java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    inventoryRepository.reserve(order);
    messagePublisher.publishCreated(order);
}
```

Spring coordinates transaction boundaries via JTA. Whether the Oracle datasource and JMS connection factory join the global transaction depends on XA configuration and integration with the TM. `@Transactional` alone is not enough to guarantee 2PC.

In Spring Boot, verify which transaction manager is actually injected/auto-configured. If the application has multiple transaction managers, specify the appropriate manager or configure explicitly; avoid letting a service accidentally run under a local manager while developers assume JTA is in use.

### 6.2. Jakarta EE Container-Managed Transactions

In Jakarta EE, EJBs or container-managed components can use container-managed transactions. The container begins/commits/rolls back transactions based on transaction attributes and automatically enlists XA datasources/JMS resources when accessed.

EJB example:

```java
@Stateless
public class OrderBean {
    @TransactionAttribute(TransactionAttributeType.REQUIRED)
    public void placeOrder(Order order) {
        // Access XA-managed database and messaging resources.
    }
}
```

`REQUIRED` joins an existing transaction if present; if none exists, the container starts a new transaction. Other attributes like `REQUIRES_NEW`, `MANDATORY`, `SUPPORTS`, `NOT_SUPPORTED`, and `NEVER` alter how a method participates in a transaction. They are container propagation rules, not different commit algorithms.

### 6.3. Transaction Propagation and Multiple Transaction Managers

When one method calls another, understand propagation:

- `REQUIRED`: uses the current transaction or creates a new one.
- `REQUIRES_NEW`: suspends the current transaction and runs a new independent transaction.
- `MANDATORY`: requires the caller to already have an active transaction.
- `SUPPORTS`: joins if a transaction exists, otherwise runs without a transaction.
- `NOT_SUPPORTED`: suspends the current transaction while executing the method.
- `NEVER`: throws an error if the caller has an active transaction.

If two repositories use two independent transaction managers, `@Transactional` by default does not automatically coordinate them into a global transaction. There must be one shared JTA TM and XA resources enlisted into the same transaction.

### 6.4. Transaction Context Across Threads and Async Execution

JTA transaction association is typically bound to a thread/context managed by the TM. Never assume a transaction automatically propagates to `new Thread`, executors, `CompletableFuture`, schedulers, or reactive pipelines. If work runs asynchronously, use a runtime-supported context propagation mechanism or design it as a separate transaction triggered via durable messages/commands.

Never hold a global transaction open while waiting on network calls or long async work. Doing so holds locks, connections, and prepared branches for too long.

## 7. Recovery and In-Doubt Transactions

### 7.1. Why Does XA Need a Recovery Log?

2PC has a window where an RM has prepared but does not yet know the TM's final decision. If the TM crashes after an RM prepares, the RM may keep the transaction in an in-doubt state. It cannot commit or roll back on its own because it does not know the global decision.

The TM must write a durable log before/at the moment of the commit decision so that after restart it can restore transaction states and deliver decisions to RMs. RMs must also retain prepared state until they receive the decision or are processed per the recovery protocol.

Therefore, the TM's transaction log is critical data. Putting logs on an ephemeral filesystem or deleting logs on restart can make the TM lose the ability to determine which transactions must commit or roll back.

### 7.2. XA Recovery Scan

On startup or during recovery runs, the TM invokes `XAResource.recover()` to query RMs for Xids in prepared/in-doubt state. The TM matches those Xids against its durable transaction log and issues the appropriate commit/rollback.

Recovery depends on:

- The TM's transaction log being intact and readable.
- XA resources keeping consistent identifiers/configuration so the TM finds the right RMs again.
- Oracle Database and network availability.
- Recovery credentials remaining valid with sufficient privileges.
- Drivers/providers properly supporting XA recovery.

Never rename resources, alter resource identities, or delete transaction logs arbitrarily while incomplete transactions exist.

### 7.3. Oracle In-Doubt Transactions

Oracle provides views for DBAs to inspect distributed transactions awaiting decisions:

```sql
SELECT local_tran_id,
       global_tran_id,
       state,
       mixed,
       advice,
       fail_time,
       retry_time
FROM dba_2pc_pending
ORDER BY fail_time;
```

You can view details of related nodes:

```sql
SELECT local_tran_id,
       in_out,
       database,
       dbuser_owner,
       interface
FROM dba_2pc_neighbors
ORDER BY local_tran_id;
```

These views assist DBAs in investigating distributed/in-doubt transactions. Not every XA transaction appears in the exact same form in every scenario; cross-check TM and RM states.

### 7.4. Do Not Arbitrarily FORCE COMMIT or FORCE ROLLBACK

Oracle provides `COMMIT FORCE` and `ROLLBACK FORCE` syntax to resolve certain in-doubt distributed transactions after the DBA confirms the right decision. This is an administrative action that can break atomicity if Oracle's forced outcome disagrees with the decision recorded by the TM.

Never run force commit/rollback simply to clear rows from `DBA_2PC_PENDING`. First, you must:

1. Identify the global transaction ID and transaction coordinator.
2. Inspect the TM's transaction/recovery logs.
3. Determine whether the TM decided commit or rollback.
4. Check which branches other RMs have completed.
5. Coordinate with DBAs and system owners to act according to Oracle/TM guidance.

Force resolution is only a last resort in a controlled procedure, not the default recovery method.

## 8. Timeouts, Locking, and Performance

### 8.1. Global Transaction Timeout

The TM usually enforces a timeout for global transactions. If a transaction exceeds the allowed duration, the TM may mark it rollback-only or request rollback depending on implementation. Timeouts must be aligned with:

- JTA/TM transaction timeout.
- JDBC query timeout.
- Network/socket timeout.
- JMS provider timeout.
- Lock wait and database processing time.
- Connection pool borrow timeout.

These timeouts serve different purposes. A pool borrow timeout is not a transaction timeout; a query timeout also does not automatically prove every RM has finished rolling back.

### 8.2. Locks and Transaction Hold Duration

In 2PC, RMs may hold locks/transaction state until receiving the final decision. If one participant is slow or unreachable, completion time can stretch and affect other transactions.

Keep XA transactions short; avoid making HTTP calls, file I/O, waiting for user input, or performing long computations inside a transaction. Only enlist resources genuinely needed for atomicity.

### 8.3. 2PC Overhead

Compared to local transactions, XA adds prepare/commit round trips, transaction logging, recovery state, and coordination overhead. When all resources reside in a single Oracle Database, a local transaction on one connection is simpler and more efficient than XA. Use XA only when atomicity across independent RMs is genuinely required.

Do not use XA merely because a workflow calls multiple repositories if all repositories use the same database and the same local transaction manager.

## 9. Limitations and Caveats with Oracle

### 9.1. DDL and Implicit Commit

Oracle DDL executes an implicit commit before and after the statement per Oracle rules. Never place DDL like `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE` inside an XA workflow expecting it to roll back like DML. Separate migrations/schema changes from business transactions.

### 9.2. Sequences Do Not Roll Back

Values fetched from an Oracle sequence are not returned when a transaction rolls back. Therefore, sequence gaps are normal and do not indicate an un-atomic XA commit.

### 9.3. External Side Effects

Calling HTTP APIs, sending emails, writing files, or interacting with non-XA systems is not automatically protected by 2PC. Calling an external service while a transaction is open can result in completed side effects even if the database rolls back.

For these systems, consider transactional outbox, inbox/idempotency, controlled retries, or Sagas rather than assuming XA covers everything.

### 9.4. XA Does Not Eliminate the Need for Idempotency

After a timeout or network error, the client may not know whether the transaction committed. Retrying a business request can create duplicate data if the API lacks an idempotency key or duplicate-detection mechanism. XA guarantees coordination within the RM/TM boundary; it does not automatically make application request retries idempotent.

## 10. Global Transaction Management Options

### 10.1. Application Server Transaction Manager

Application servers such as Oracle WebLogic or Jakarta EE servers provide a JTA transaction manager integrated with datasources, JMS providers, naming, security, and recovery services.

Advantages:

- Integrated XA datasource/JMS support via container configuration.
- Server/domain-level management of transaction logs, recovery, and timeouts.
- Administrative tools for monitoring transactions and in-doubt states.
- Suits applications deployed in the application server model.

Considerations:

- Depends on the application server runtime and deployment model.
- Requires operating a durable transaction log store and proper failover configuration.
- Datasource/JMS configurations and resource identities must remain consistent across nodes.

### 10.2. Standalone JTA Transaction Manager

Java applications not running inside a Jakarta EE application server can use a standalone JTA implementation, such as Narayana or Atomikos, paired with a compatible XA datasource/pool.

A standalone TM fits Spring/Java SE services needing global transactions without relying on a full application server. However, the operations team must ensure:

- Proper TM initialization and shutdown lifecycle.
- Durable storage for transaction logs.
- Recovery runs on restart and can reach every RM.
- Resource identities do not change unexpectedly.
- Runbooks exist for monitoring, alerting, and handling in-doubt transactions.
- Compatibility across TM version, JDBC driver, and application framework.

Simply adding a JTA dependency to the build does not give you XA. You must configure the TM, XA datasources, pools, and recovery together.

### 10.3. Comparing Options

| Criterion | Application Server TM | Standalone TM |
|---|---|---|
| Where managed | Inside Jakarta EE/application server | Inside the Java process/service or integrated runtime |
| Resource configuration | Usually via admin console/config server/JNDI | Via framework/TM-specific configuration |
| Recovery log | Managed by server, needs durable storage | Application/ops team configures durable storage |
| JMS/Oracle integration | Via container adapters and configuration | Depends on supporting XA provider/pool |
| Best fit | Applications deployed on an app server | Spring/Java SE or standalone services |
| Operational risks | Domain, cluster, and log store configuration | Managing lifecycle, recovery, and resource identity in the app |

No single option fits every system. Choose based on your runtime, operational capability, number of RMs, RTO requirements, and driver/provider XA support.

## 11. When Should You Not Use XA?

XA is not the default choice for every distributed workflow. Alternative approaches include:

### 11.1. Local Transactions

If all changes live in one Oracle Database, use a local transaction over a single connection. This is the simplest, lowest-overhead, and easiest-to-operate solution within a single RM.

### 11.2. Transactional Outbox

If you need to update Oracle and emit an event, write the business data and an outbox row in the same local transaction. A publisher reads the outbox and sends the message; consumers process idempotently.

```text
Local Oracle transaction
      |
      +-- update business tables
      +-- insert OUTBOX event
      |
      v
     COMMIT
      |
      v
Outbox publisher sends message
      |
      v
Consumer processes idempotently
```

Outbox does not provide simultaneous atomic commit between Oracle and the broker; it guarantees the event is durably saved alongside the data and retried until processed. The design must handle duplicate delivery, retries, and ordering.

### 11.3. Saga

A Saga breaks a long workflow into local transactions. Each step commits independently; if a later step fails, the system executes compensating actions to offset prior effects.

Sagas suit long-running workflows, microservices, and systems where resources lack XA support. Compensation is a new business action rather than a physical rollback; explicitly design behavior when compensation itself fails.

### 11.4. Event-Driven Eventual Consistency

If the business tolerates consistency lag, an event-driven architecture can reduce coupling between services. Retries, dead-letter handling, idempotency, observability, and reconciliation procedures are required.

## 12. XA Implementation and Testing Workflow

1. Identify all participating resource managers and verify the cross-resource atomicity requirement.
2. Verify Oracle JDBC driver, Oracle Database release, JMS provider, and TM have compatible XA support.
3. Choose one JTA transaction manager matching the runtime; never configure multiple independent TMs for one global transaction.
4. Register the Oracle `XADataSource` and other XA resources with the TM; configure pools, resource names, credentials, and recovery.
5. Establish short transaction boundaries, aligned timeouts, and exception rollback rules.
6. Ensure TM transaction logs reside on durable storage and are backed up/monitored.
7. Test successful commits across all RMs.
8. Test exceptions before prepare, failures during prepare, failures mid-commit, and TM/RM restarts at various points.
9. Test recovery scans, in-doubt transactions, and DBA handling procedures when the coordinator is unavailable.
10. Test connection pools, transaction timeouts, failovers, duplicate requests, and idempotency.
11. Measure throughput, latency, lock duration, connection usage, and transaction log growth under realistic load.
12. Write runbooks for restarts, recovery, force-resolution escalation, and configuration rollback.

## 13. Checklist for Choosing XA vs. Alternatives

| Question | If Yes/No | Direction to Consider |
|---|---|---|
| Does a transaction only update one Oracle database? | Yes | Local JDBC/JTA transaction is usually sufficient |
| Is atomic commit needed between Oracle and JMS/another XA database? | Yes | XA/JTA is a suitable candidate |
| Do all resources have supported XA implementations? | No | Look at outbox, saga, or eventual consistency |
| Does the workflow span long durations across many services? | Yes | Saga/outbox is usually better than holding long XA transactions |
| Is eventual consistency acceptable? | Yes | Event-driven/outbox reduces coupling |
| Are a TM log store and recovery operator in place? | No | Not ready to operate XA in production |
| Does the app need to retry after timeouts? | Yes | Design idempotency and transaction status lookup |
| Can transactions be kept short with few resources? | Yes | XA is manageable; still measure overhead |

## 14. Key Principles to Remember

- XA is the protocol coordinating transactions between a TM and multiple RMs; JTA is the Java API for managing global transactions.
- Oracle JDBC requires an XA-capable datasource; an ordinary JDBC connection does not automatically become an XA resource.
- The TM creates `Xid`s, enlists `XAResource`s, orchestrates 2PC, and manages recovery; business code never calls the `XAResource` protocol directly.
- 2PC consists of prepare and commit/rollback; the TM must durably persist transaction decisions.
- The `@Transactional` annotation only uses XA when the active transaction manager is JTA and resources are properly configured/enlisted.
- The TM recovery log and working `XAResource.recover()` are mandatory for production operations.
- Oracle's `DBA_2PC_PENDING` aids in investigating in-doubt transactions; never arbitrarily run `FORCE COMMIT`/`ROLLBACK`.
- XA adds coordination overhead and lock duration; use it only when cross-RM atomicity is required.
- DDL, sequences, HTTP, files, and email have their own semantics; do not assume XA rolls them back.
- Outbox, Sagas, and eventual consistency are strong alternatives when resources lack XA support or workflows are long-lived.

## References

- [Oracle Database 19c JDBC Developer's Guide — Distributed Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/distributed-transactions.html)
- [Oracle Database 19c JDBC Developer's Guide — JDBC and XA](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/)
- [Oracle Database 19c Administrator's Guide — Managing Distributed Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-distributed-transactions.html)
- [Oracle Database 19c Reference — DBA_2PC_PENDING](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_2PC_PENDING.html)
- [Oracle Database 19c Reference — DBA_2PC_NEIGHBORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_2PC_NEIGHBORS.html)
- [Jakarta Transactions Specification](https://jakarta.ee/specifications/transactions/)
- [Java SE API — XAResource](https://docs.oracle.com/en/java/javase/21/docs/api/java.transaction.xa/javax/transaction/xa/XAResource.html)
