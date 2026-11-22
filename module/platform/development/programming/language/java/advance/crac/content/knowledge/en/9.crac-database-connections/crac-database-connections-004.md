# Unfinished Transactions and Safe Checkpoint Boundaries

When a Java application uses CRaC, a checkpoint records the state of the process at a point in time. The database remains an independent system and continues to manage sessions, transactions, locks, logs, and data according to its own lifecycle. Therefore, an open transaction cannot be treated as a part of heap state that can be brought back to the exact previous point in time simply by restoring the JVM.

A safe checkpoint boundary for an application with a database is usually a point where all in-flight work has ended its transactions according to business rules. The application needs to stop accepting new work, wait for running requests and tasks to finish, confirm that no unfinished transactions remain, and only then allow the checkpoint. After restore, the application creates or re-verifies connections and continues from the actual data state of the database.

## 1. Transactions and Checkpoints Belong to Two Different Lifecycles

A database transaction has state managed by the database and the transaction manager. With JDBC, an application typically starts a transaction by disabling auto-commit, executing SQL statements, and then calling commit or rollback.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Execute the SQL statements belonging to the same transaction.
        updateInventory(connection);
        insertOrder(connection);
    } catch (Exception error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }

    // Commit is performed after the SQL work has completed.
    // If commit throws an error due to a lost connection, the outcome may be undetermined.
    connection.commit();
}
~~~

Meanwhile, a CRaC checkpoint records the state of the Java process. It does not create a synchronized snapshot for the database and does not revert the database to its state at checkpoint time.

We can distinguish:

- **State in the JVM:** Connection objects, repositories, services, local variables, coordination state, and Java references.
- **State in the database:** sessions, transactions, locks, cursors, committed data, and transaction logs.
- **State between the two systems:** a commit command sent whose response has not returned, a message published but not yet acknowledged, or a request processed whose response has not reached the client.

These states are not automatically checkpointed as an atomic unit. A Connection object still in the heap does not prove that the database-side session is still active. Similarly, restoring a Java variable to its pre-checkpoint value does not undo a transaction committed in the database after that point.

## 2. Why Are Unfinished Transactions an Unsafe State?

Suppose an order placement request performs three steps:

1. Read inventory.
2. Decrement inventory quantity.
3. Create an order record.

If a checkpoint occurs while the transaction is still open, the process may be restored with objects and threads in their old state, while the database has already handled the session according to its own lifecycle. An uncommitted transaction may be rolled back when the session is closed or lost; when and how resources are released depends on the database and driver. If the commit command reached the database but the response was lost, the application may not know whether the transaction committed or not.

This creates awkward situations:

- The application thinks the order was not created, but the database has already committed the order.
- The application restores a pre-commit state variable and resends the same operation, creating duplicate data.
- The database is still holding locks while the JVM is no longer handling the corresponding request.
- An old cursor or result set is referenced in the heap while the session is no longer valid.
- An in-progress request is reprocessed after restore while the previous operation already completed on an external system.

Therefore, open transactions should not be held across a checkpoint. Complete or roll back the transaction before allowing a checkpoint, and handle the case of an undetermined commit outcome separately.

## 3. Transaction States and Checkpoint Positions

A typical transaction can be viewed in stages:

~~~text
Not started
    |
    v
Executing SQL
    |
    +------> Rollback completed
    |
    v
Commit requested
    |
    +------> Commit confirmed
    |
    +------> Unknown response / lost connection
~~~

Points to distinguish:

| State | Meaning | Handling before checkpoint |
|---|---|---|
| Not started | No database transaction yet | Can checkpoint if no other work is using the dependency |
| Executing SQL | Transaction is open, may be holding locks and uncommitted changes | Wait for completion or roll back according to business rules |
| Rolling back | Application or transaction manager is canceling changes | Wait for rollback to complete and confirm state |
| Commit confirmed | Database confirmed the transaction committed successfully | Can proceed after completing related work |
| Commit outcome unknown | The commit command may have been processed by the database, but the response did not reach the application | Do not blindly retry; reconcile using a business identifier/idempotency key |
| XA/in-doubt | Distributed transaction may be in prepared state or waiting for coordinator decision | Let the transaction manager perform recovery according to logs and XA configuration |

A safe checkpoint usually lies between completed units of work, when there are no active transactions and no unresolved commit outcomes at the business layer.

A request may contain multiple separate transactions. Just because the current transaction has completed does not mean the entire request is safe: the request may still have steps to call external services, publish messages, or update other state. The checkpoint boundary needs to consider the entire unit of work, not just the JDBC transaction flag.

## 4. How Is a Safe Checkpoint Boundary Formed?

A safe boundary is a point proactively created by the application through a work coordination mechanism. It does not appear automatically just because CRaC starts invoking callbacks.

A typical process:

1. **Stop accepting new work.** Mark the instance as no longer receiving new traffic, pause schedules, and stop receiving new messages.
2. **Drain in-flight work.** Wait for current requests, jobs, and consumer handlers to finish or cancel according to a defined policy.
3. **Complete transactions.** Every transaction must commit or roll back; do not leave connections in an open transaction state.
4. **Handle unknown outcomes.** If commit encounters a connection error and the outcome cannot be determined, mark the unit of work for reconciliation; do not blindly resend.
5. **Release transaction-dependent resources.** Close cursors, result sets, and connections according to the JDBC driver/connection pool guidelines; release locks or leases if policy requires.
6. **Check checkpoint conditions.** Confirm there are no remaining transactions or work that need continuity within the process.
7. **Perform the checkpoint.** Only when the application has reached a quiescent state should the runtime be allowed to create a checkpoint.

After restore, the application verifies dependencies, restarts consumers and schedulers, and only then opens traffic. This must be done in order so that no new requests enter while the pool or transaction manager is not yet ready.

## 5. Managing Transactions at the Service Boundary

A transaction should have a clear scope, usually wrapped around a short unit of work. With plain JDBC, try-with-resources ensures the connection is closed or returned to the pool when the block of work finishes.

~~~java
public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createOrder(OrderCommand command) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            boolean commitAttempted = false;

            try {
                insertOrder(connection, command);
                updateInventory(connection, command);
                commitAttempted = true;
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                if (commitAttempted) {
                    throw new CommitOutcomeUnknownException(
                            command.requestId(), error);
                } else {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                }
                throw error;
            }
        }
    }

    private static final class CommitOutcomeUnknownException
            extends SQLException {
        CommitOutcomeUnknownException(String requestId, Throwable cause) {
            super("Commit outcome must be reconciled for request "
                    + requestId, cause);
        }
    }

    private void insertOrder(Connection connection, OrderCommand command)
            throws SQLException {
        // INSERT order using PreparedStatement.
    }

    private void updateInventory(Connection connection, OrderCommand command)
            throws SQLException {
        // UPDATE inventory in the same transaction.
    }
}
~~~

The code snippet illustrates transaction scope contained within a single service call. The application needs to ensure that the SQL operation methods actually use the same connection and do not keep the transaction after the method finishes.

With Spring, a method managed by @Transactional usually has its transaction opened before the method body runs and committed/rolled back when the interceptor finishes the call. Therefore, the checkpoint coordination layer needs to wait for running transactional calls to finish completely. Waiting only for the method body to return at another layer, while the interceptor has not finished committing, is not enough.

Do not store a Connection, Statement, ResultSet, or transaction-scoped EntityManager in a long-lived object to continue using after restore. These objects belong to a specific operation scope and depend on the session/database transaction. Acquire resources from the pool within each unit of work and return them when the transaction completes.

## 6. A Failed Commit Does Not Mean the Transaction Definitely Did Not Commit

One of the most important scenarios is an error occurring right when calling commit:

~~~java
connection.commit();
~~~

For example, the application sends a commit command to the database. The database processes and commits successfully, but the connection drops before the response reaches the JVM. The application receives a SQLException, but it cannot deduce from the exception alone that the database rolled back.

Calling rollback afterward also does not resolve the uncertainty: the transaction may have already committed. Resending the entire business operation can create duplicate records or side effects.

### Using an idempotency key

Each business request can have a stable identifier, such as requestId or orderRequestId. The database stores this identifier along with the business outcome in the same transaction and places a unique constraint so the same request is not applied twice.

~~~sql
CREATE TABLE processed_request (
    request_id VARCHAR(100) PRIMARY KEY,
    result_code VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Within the transaction:

1. Check or record the requestId using a mechanism that guarantees uniqueness.
2. If the request has already been processed, return the stored outcome.
3. If not, perform the business changes.
4. Store the processing outcome and commit in the same transaction.

After restore, if a pre-checkpoint commit outcome is unknown, the application opens a new connection and looks up the requestId in the database. If an outcome already exists, reuse that outcome; if not, re-execute according to business policy. Checking and writing the requestId must be designed against race conditions, usually via a unique constraint and duplicate key handling within the transaction.

An idempotency key is only effective when used across retries and persisted alongside business changes. A boolean variable in the heap cannot replace this mechanism.

## 7. Coordinating Database Transactions with a Message Broker

A request may both update the database and publish a message. If the database commits successfully but the message has not been sent, the system may miss an event. If the message was sent but the publish status was not recorded, after restore the application may publish the message again.

Transactional outbox is a common pattern:

1. Within the same database transaction, update the business data and write a record to the outbox table.
2. Commit the transaction.
3. A separate publisher reads outbox records and sends messages.
4. The publisher marks records as sent using a retryable mechanism.
5. The consumer processes idempotently or uses an inbox/deduplication to detect duplicate messages.

~~~text
Request
  |
  v
Database transaction
  |-- update business data
  |-- write event to Outbox
  |
  v
Commit
  |
  v
Outbox publisher
  |
  v
Message broker
  |
  v
Consumer (idempotent / deduplication)
~~~

With this pattern, a checkpoint can take place after the outbox-writing transaction has committed. The publisher can resume after restore from pending outbox records. Message sending may be duplicated if the publisher fails at the boundary between sending and marking as sent; the consumer still needs to handle duplicates safely.

Do not assume a normal JDBC transaction automatically covers both the database and the broker atomically. If distributed transactions/XA are needed, the corresponding transaction manager must be configured and used.

## 8. XA and Distributed Transactions

In XA, a transaction can span multiple resource managers. The transaction manager coordinates prepare and commit/rollback. An in-doubt state can exist when a participant has prepared but has not received the final decision.

A JVM checkpoint does not replace the transaction manager's durable log and does not synchronously snapshot the state of every resource manager. With XA:

- Do not arbitrarily close or roll back an XAResource currently managed by the transaction manager.
- Wait for the transaction manager to bring active transactions to an appropriate boundary before checkpointing.
- Ensure the transaction recovery log is stored in a durable location and is accessible after restore.
- Let the transaction manager perform recovery according to the XA protocol after reconnecting to the resource managers.
- Verify recovery identity, credentials, and required access permissions.

If the system still has prepared/in-doubt transactions, follow the operational guidance of the transaction manager and database. Do not assume that restoring the heap will decide commit or rollback on behalf of the coordinator.

## 9. Integrating Transaction Boundaries into a CRaC Resource

A Resource can connect the checkpoint lifecycle with the application's work coordinator. The interfaces in the example below are application-defined interfaces; they represent the ability to stop admission, drain work, and check transactions.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabaseCheckpointBoundary implements Resource {
    public interface WorkCoordinator {
        void stopAdmission() throws Exception;
        void drainInFlightWork() throws Exception;
        void assertNoActiveTransactions() throws Exception;
        void verifyDatabaseReady() throws Exception;
        void resumeAdmission() throws Exception;
    }

    private final WorkCoordinator coordinator;

    public DatabaseCheckpointBoundary(WorkCoordinator coordinator) {
        this.coordinator = coordinator;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        coordinator.stopAdmission();
        coordinator.drainInFlightWork();
        coordinator.assertNoActiveTransactions();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        coordinator.verifyDatabaseReady();
        coordinator.resumeAdmission();
    }
}
~~~

In the example:

- stopAdmission blocks new requests, jobs, or messages from entering the work area that needs to be drained.
- drainInFlightWork waits for running units of work to finish.
- assertNoActiveTransactions confirms there are no open transactions within the application-managed scope.
- verifyDatabaseReady checks that the database and connection pool are ready after restore.
- resumeAdmission only reopens work when the necessary dependencies are functioning.

This is an integration skeleton, not a built-in transaction tracker of CRaC. The application needs to implement the methods according to its actual architecture, including all paths that create transactions such as HTTP requests, schedulers, consumers, async tasks, and internal callbacks.

In particular, a Resource does not automatically detect transactions created by unmanaged libraries or unregistered threads. If the connection pool, JDBC driver, or framework already has CRaC integration, follow that version's instructions for managing connections. Do not manually close the pool or XA resources in an application callback if doing so conflicts with the integration.

Stopping admission needs to be coordinated with the deployment system. For example, readiness can transition to not accepting traffic and the load balancer stops sending new requests. However, a readiness change does not mean running requests have finished; draining and transaction checks are still required.

afterRestore only serves the restored process. If checkpoint preparation fails or the checkpoint request is canceled and the original process continues running, you cannot rely on afterRestore to reopen admission. The coordinator that issues the checkpoint command needs its own failure-handling path: restore resources that were closed, verify transaction state, and only reopen traffic when the system returns to a safe state. If recovery is not possible, keep the instance in an unready state to be handled according to operational procedures.

## 10. Common Misconceptions

**“If the Connection is still in the heap, the transaction is still alive.”**

False. A Connection object is a Java representation; sessions and transactions are managed by the database. After restore, the handle may no longer be valid and an uncommitted transaction may have already been handled by the database according to the session lifecycle.

**“Restore will roll back open transactions to the exact checkpoint time.”**

False. CRaC does not snapshot the database. The database handles sessions/transactions according to its own rules; the JVM cannot turn external data back to the past.

**“A SQLException from commit means the database has not written the data.”**

Not certain. The commit command may have been processed while the response was lost. Reconciliation using an idempotency identifier or appropriate transaction recovery is required.

**“Just close the connection pool in beforeCheckpoint.”**

Closing the pool while requests are still using connections can corrupt transactions. First stop new work and drain current operations; then follow the CRaC guidance for the pool/driver.

**“Once a @Transactional method has returned, the entire request is definitely safe.”**

The transaction may have completed, but the request can still call other services, publish messages, or update other state. A safe boundary must consider the entire unit of work and its side effects.

**“The database and message broker will roll back together when the JVM restores.”**

False unless a distributed transaction mechanism is properly configured and managed. A normal JDBC transaction only guarantees the corresponding database scope.

## 11. Testing Checkpoint Boundaries

Testing should be done on the exact JDK/CRaC runtime, JDBC driver, connection pool, database, and transaction manager intended for deployment.

Scenarios to test:

- Request a checkpoint when no requests or transactions are running.
- Request a checkpoint while a transaction is executing multiple SQL statements.
- Request a checkpoint while a transaction is committing or rolling back.
- Restart the database or close sessions while the application is paused.
- Lose connection right at commit time and verify the idempotency reconciliation mechanism.
- Transaction rollback fails or a connection cannot be returned to the pool.
- Consumer receives a message but has not acknowledged it at the time of stopping.
- Publisher sends a message successfully but has not marked the outbox record as sent.
- Restore when the database is not yet ready and verify the application has not opened traffic.
- Multiple checkpoint/restore cycles to detect stale connections, leaked transactions, or duplicate-started consumers.

Logs and metrics should show the number of running requests, active transactions, transactions needing reconciliation, connection pool status, and drain duration. Do not log passwords, access tokens, or sensitive data.

A checkpoint should only be considered safe when the quiescence condition is confirmed. If transactions or unknown commit outcomes remain, the application needs to continue processing or hand that unit of work over to a recovery mechanism before checkpointing.

## 12. Conclusion

Database transactions and JVM checkpoints belong to two different lifecycles. CRaC saves process state; the database continues managing its transactions and data. Therefore, unfinished transactions should not be held across a checkpoint.

Applications need to create a safe boundary by stopping new work, draining requests and consumers, completing commits/rollbacks, reconciling unknown commit outcomes, and confirming no active transactions remain. After restore, connections and pools must be verified, the transaction manager must recover via its own mechanism, and operations that may be resent need idempotency or deduplication to avoid duplicate side effects.
