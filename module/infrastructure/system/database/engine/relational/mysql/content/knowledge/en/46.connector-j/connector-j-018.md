# Limits of autoReconnect, Failover URLs, and Transaction Integrity

MySQL Connector/J can try connecting to another host when the current connection fails, but picking a new host does not mean an active transaction continues seamlessly. A JDBC connection is tied to a MySQL session; when the session drops, any uncommitted transaction, temporary table, session variable, lock, and session settings may be gone. In particular, if the network drops right while sending COMMIT, the application may not know whether the server committed or not.

Therefore, distinguish three layers: **detecting failed connections**, **selecting a replacement endpoint**, and **safe business recovery**. The autoReconnect property and multi-host failover URLs help partially in the first two layers. Transaction integrity must still be designed into the application, database topology, and retry workflow.

This lesson belongs to the **Connector/J** chapter of the DATABASE_MYSQL module. The module covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query tuning, authorization, backups, and relational database operations. Examples use JDBC and MySQL Connector/J; verify documentation for your deployed driver version because certain failover properties and connection behaviors have changed across releases.

After this lesson, you will be able to:

- Explain what autoReconnect can do and what it cannot guarantee.
- Distinguish connection failures from SQL errors and ambiguous commit outcomes.
- Configure multi-host failover URLs for their intended purpose.
- Distinguish failover, load balancing, and replication connections.
- Understand MySQL Router's role in InnoDB Cluster.
- Design timeouts, connection pools, and validation.
- Safely retry transactions using idempotency keys and reconciliation.
- Test failover without creating duplicate writes or data loss.

## 1. Three Layers to Distinguish

A Java system connecting to MySQL involves at least three behavioral layers during an outage:

| Layer | Question to answer | Relevant components |
|---|---|---|
| Failure detection | Is the socket or session still alive? | TCP, timeouts, Connector/J, connection pool |
| Endpoint switching | Is another host available to accept connections? | Multi-host JDBC URL, MySQL Router, topology/cluster |
| Business recovery | Did the transaction commit and can it be re-executed? | Application, transaction boundaries, idempotency, unique constraints |

For example: the application sends a payment command, MySQL commits the transaction, yet the COMMIT response is lost due to a network partition. The driver sees a broken connection. Another host may accept a new connection, but the driver cannot infer from a socket error alone whether the previous transaction committed or rolled back.

A safe design must address all three layers. Simply adding hosts to a URL or enabling autoReconnect is not enough to protect business data.

## 2. What Is autoReconnect?

Connector/J has the §autoReconnect§ connection property. This property allows the driver to attempt re-establishing a connection when it detects the old connection is stale or dead. By default, autoReconnect is off.

Configuration example:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?autoReconnect=true
~~~

Never treat this as a transaction recovery mechanism. A new connection is a brand-new MySQL session. The driver cannot restore open transaction state from the old session, nor can it recreate every session setting established by the application.

State that can be lost when a connection is recreated:

- Open transactions and uncommitted changes.
- Session-created temporary tables.
- User variables and session variables.
- Session-held locks, including named locks.
- Isolation level, autocommit, and read-only state if modified on the session.
- Current schema/database if changed via a session statement.
- Server-side prepared statements and open cursors.
- ResultSet reading state or cursor position.
- Session context such as SQL mode or timezone if customized by the application.

Some state may be reapplied by the driver or pool per configuration, but the application must never assume a new session is fully equivalent to the previous one.

**Principle:** autoReconnect may help re-establish a connection for a subsequent operation in certain scenarios, but it does not prove the previous statement completed and does not recover an active transaction.

## 3. Why You Should Not Rely on autoReconnect for Transactions

Suppose the application runs:

~~~sql
START TRANSACTION;
UPDATE sales.accounts
SET balance = balance - 100
WHERE account_id = 10;
UPDATE sales.accounts
SET balance = balance + 100
WHERE account_id = 20;
COMMIT;
~~~

If the connection drops after the first UPDATE, the transaction on the old session has not committed. Once the server detects the lost session, the uncommitted transaction rolls back via InnoDB's mechanism. However, when the server detects the disconnect may differ from when the application receives an exception.

If the connection drops right during COMMIT, there are two possibilities:

1. The server had not committed the transaction yet. When the session ends, changes roll back.
2. The server committed, yet the acknowledgment response failed to reach the client.

From the application's perspective, both cases can surface as a timeout or communication exception. If the application reconnects and blindly reruns the entire transaction, the second case creates a duplicate business transaction.

autoReconnect cannot resolve this ambiguity. The driver lacks enough context to decide autonomously whether a business transaction should rerun.

### 3.1. Ambiguous COMMIT Outcomes

An error before sending COMMIT can usually be handled by rolling back and retrying the entire transaction if the error is transient and business rules allow. However, an error during or after sending COMMIT must be treated as **outcome unknown** until the application reconciles state.

Never assume that:

- Because the client caught an exception, the transaction definitely rolled back.
- Because the client saw no exception, every replica already applied the write.
- Because the driver reconnected successfully, the previous transaction recovered.
- Because an UPDATE returned no result, the database stayed unchanged.

Use a unique request ID and persist the business outcome in the same transaction so you can query it after reconnecting.

## 4. Multi-Host Failover URLs

Connector/J supports URLs with multiple hosts so the driver can try another endpoint when a host is unreachable or the active connection encounters a failover-eligible error.

Example:

~~~text
jdbc:mysql://db-a.example.internal:3306,db-b.example.internal:3306/sales?connectTimeout=5000&socketTimeout=30000&sslMode=VERIFY_IDENTITY
~~~

In this example:

- db-a and db-b are endpoints in a topology designed for failover.
- sales is the default database.
- connectTimeout limits connection establishment time.
- socketTimeout limits socket read wait time.
- sslMode=VERIFY_IDENTITY enforces server identity verification via TLS.

A host list merely describes addresses the driver can attempt. It does not elect a primary, check quorum, synchronize data, or guarantee the next host permits writes.

### 4.1. Requirements for Hosts in the List

Before listing multiple hosts in a URL, answer:

- Do the hosts belong to the same logical database or replication topology?
- Does data across hosts share the same origin and an acceptable consistency level?
- Which host is currently permitted to accept writes?
- What mechanism promotes a replica or elects a primary when a node fails?
- How do you prevent two hosts from independently accepting writes after a network partition?
- Does the client detect read-only state and retry appropriately?
- Do all hosts share identical TLS policies, accounts, grants, schemas, and session configs?

Never place an arbitrary replica into a write-failover list simply because its TCP port is open. The replica may be lagging, read-only, or unpromoted. Being able to open a socket to a replica does not mean it is ready to accept write transactions.

### 4.2. Host Ordering and Retry Behavior

Host ordering in the URL can affect connection/attempt ordering depending on driver mode and version. Never rely on list order as a primary-election mechanism or a guarantee that the first host is always the writer.

Certain failover-related properties, such as §failOverReadOnly§ or §retriesAllDown§, have version- and mode-dependent behavior. Read Connector/J documentation for your exact version before using them. In particular, understand how the driver sets connections to read-only upon switching hosts and how many attempts occur when all hosts are down.

Never stack unbounded retries across the driver, connection pool, HTTP framework, and business layer simultaneously. Multi-layer retries multiply call counts, spike load during recovery, and blow through request deadlines.

## 5. A Failover URL Is Not an HA System

A failover URL only helps the client try another endpoint within driver capabilities. It does not provide full high-availability system functionality.

| Capability | Provided automatically by multi-host URL? |
|---|---|
| Attempt connecting to another host | Yes, within driver-supported failover scenarios |
| Elect a new primary | No |
| Promote a replica | No |
| Verify quorum | No |
| Synchronize transactions across hosts | No |
| Pick the node with freshest data | Not guaranteed automatically |
| Prevent split-brain | No |
| Recover a transaction whose session dropped | No |
| Know for sure whether COMMIT succeeded after lost response | No |

Database topologies require dedicated HA mechanisms such as Group Replication/InnoDB Cluster, replication with an orchestrator, or a managed database platform. The driver is only one link on the path from the application to that topology.

With MySQL asynchronous replication, a replica may not yet have received the latest transaction. If an application fails over writes to a lagging replica without proper promotion and data verification, acknowledged writes on the old primary can be lost or split-brain dual writers can occur.

## 6. Distinguishing Failover, Load Balancing, and Replication URLs

Connector/J provides distinct multi-host URL schemes. Do not use them interchangeably.

| URL scheme | Purpose | Operational meaning |
|---|---|---|
| jdbc:mysql://host1,host2/db | MySQL connection with failover capability | Driver tries another host when the current connection becomes unusable per failover policy. |
| jdbc:mysql:loadbalance://host1,host2/db | Load balancing | Distributes connections/work using the driver's load balancing mechanism and configuration. |
| jdbc:mysql:replication://source,replica/db | Replication connection | Supports read/write splitting between source and replica via the connection's read-only state. |

### 6.1. Load Balancing

Example:

~~~text
jdbc:mysql:loadbalance://db-a.example.internal:3306,db-b.example.internal:3306/sales
~~~

Load balancing is not synonymous with failover. The driver can distribute connections or switch hosts per load balancing policy. Use it only when hosts are designed to serve identical workloads with compatible consistency and write privileges.

Never place nodes with divergent data or asymmetric writer/reader roles into a load balancing URL as if they were interchangeable machines.

### 6.2. Replication Connections

Example:

~~~text
jdbc:mysql:replication://mysql-source.example.internal:3306,mysql-replica.example.internal:3306/sales
~~~

Replication connections manage routing to source and replica hosts. Applications can mark a connection read-only so the driver routes read queries per supported modes; when read-only is off, write queries go to the source.

Conceptual example:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setReadOnly(true);
    // Execute read queries per replication connection policy.
}
~~~

Never mark a connection read-only just to "speed things up" if the transaction might write. Nor should you assume every SELECT can go to a replica: queries needing read-after-write freshness, temporary tables, or session-bound state must stay on the same node.

Check Connector/J documentation for how to configure replication connections, toggle read-only state, detect hosts, and handle failover in your version.

## 7. failOverReadOnly and the Risk of Writing to a Replica

In multi-host failover mode, the §failOverReadOnly§ property controls whether a connection is set to read-only when the driver falls back to an alternate host. Verify default values and exact semantics for your Connector/J version.

Setting a failed-over connection to read-only helps prevent accidentally writing to an unpromoted replica. However, this is not server-side authorization and does not replace verifying node roles.

Defense-in-depth layers should include:

- Replicas configured with read-only/super-read-only on the server where appropriate.
- Driver or Router routing to endpoints strictly by role.
- Application status checks and proper handling of read-only errors.
- HA orchestration confirming promotion completes before opening writes.
- Runbooks preventing an old primary from returning and accepting writes alongside a new primary.

Do not disable failover read-only just to bypass write errors on host switch unless the topology guarantees every host is a valid writer with matching consistency semantics.

## 8. MySQL Router and InnoDB Cluster

For InnoDB Cluster, MySQL Router is the routing layer designed to track cluster metadata and direct connections to endpoints matching current node roles. Applications typically connect to Router rather than maintaining individual member lists themselves.

Example URL targeting a Router endpoint:

~~~text
jdbc:mysql://mysql-router.example.internal:6446/sales?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000
~~~

The port in this example is illustrative; use the actual read/write or read-only endpoint configured on your environment's Router.

Router does not keep JDBC transactions alive across a lost connection. If a connection through Router drops mid-transaction, the application still must handle rollback/outcome-unknown as usual. Router routes new connections using cluster metadata; it cannot resurrect an old session on a fresh socket.

When using Router:

- Configure Router and metadata per InnoDB Cluster guidelines.
- Use the read/write endpoint for transactions requiring writes.
- Use the read-only endpoint only when the application tolerates consistency/replication lag.
- Ensure redundant Router instances so Router itself is not a single point of failure.
- Monitor Router health, cluster members, and quorum separately.
- Test applications across primary role switches and Router restarts.

## 9. Detecting Broken Connections and Timeouts

Connection failures can be detected by TCP, Connector/J, the pool, or the server. No single timeout covers every stage.

| Mechanism | Scope | What to watch out for |
|---|---|---|
| connectTimeout | Socket/connection establishment | Does not limit query execution time after connecting. |
| socketTimeout | Waiting for socket data | Too short may abort valid slow queries as timeouts. |
| Statement.setQueryTimeout | JDBC execution duration | Cancellation behavior depends on driver/server. |
| Connection.isValid(timeout) | Connection health check | Used by apps/pools; does not guarantee prior transaction had no errors. |
| TCP keepalive | Detects certain dead network connections | Detection speed depends on OS and network settings. |
| Pool validation/keepalive | Checks connections on borrow or while idle | Tune against database/proxy idle timeouts. |

Example URL with timeouts:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?connectTimeout=5000&socketTimeout=30000&sslMode=VERIFY_IDENTITY
~~~

Connector/J timeouts are typically measured in milliseconds. Choose values based on SLAs, network latency, result sizes, and legitimate query durations. socketTimeout should not be lower than the p99 of slow queries if the application expects those queries to complete.

### 9.1. Connection.isClosed and Connection.isValid

§Connection.isClosed()§ primarily reports whether the connection has been closed on the JDBC side. It is not a reliable test of whether the socket and server can still exchange data.

§Connection.isValid(timeoutSeconds)§ asks the driver to validate connection liveness per the JDBC API. Pools can use this method or a validation query to evict stale connections before handing them to requests.

Even immediately after isValid returns true, the network can drop on the very next packet. Validation lowers the odds of borrowing a dead connection, but never eliminates race conditions.

## 10. Connection Pools and Stale Connections

In server applications, connection pools manage physical connection lifecycles. A pool can validate connections on borrow, send keepalives, retire aged connections, and open new ones on demand.

Pool settings to review:

- Maximum pool size aligned with MySQL capacity.
- Connection acquisition timeout.
- Validation timeout.
- Idle timeout.
- Max lifetime shorter than proxy/firewall connection close timeouts when needed.
- Appropriate keepalive for idle connections.
- Leak detection to spot connections never returned.
- How the pool evicts connections after connection-failure SQLExceptions.

Conceptual configuration example with HikariCP:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(
    "jdbc:mysql://mysql-router.example.internal:6446/sales" +
    "?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000"
);
config.setUsername(dbUser);
config.setPassword(dbPassword);
config.setMaximumPoolSize(20);
config.setConnectionTimeout(5000);
config.setValidationTimeout(3000);
config.setMaxLifetime(1500000);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

These numbers are examples only. Tune maxLifetime to actual limits of MySQL, Router, proxies, or firewalls. Never copy this snippet verbatim to production without load testing and verifying infrastructure timeouts.

Never use autoReconnect as a substitute for pooling. The pool must know which physical connection failed so it can evict it and open a clean replacement. Transparent driver-level reconnecting inside a pooled connection hides physical lifecycle events and makes session state hard to reason about.

### 10.1. Validation Queries

Some pools allow specifying a validation query such as §SELECT 1§. When the pool and driver support JDBC isValid well, running a validation query on every borrow is usually unnecessary. Overly frequent validation adds round trips and database load.

Configure validation according to pool capabilities, driver version, and infrastructure. Never run a validation query on a connection currently holding a business transaction to infer the transaction is still intact.

## 11. Identifying Connection Errors

JDBC exposes SQLState, vendor error codes, and SQLException subclasses to classify failures.

Common indicators:

| Indicator | Possible meaning | Action |
|---|---|---|
| SQLState class 08 | Connection exception | Check socket, server, Router, and host failover eligibility. |
| MySQL error 2006 | Server has gone away | Check server restarts, idle timeouts, packets, or stale connections. |
| MySQL error 2013 | Lost connection during query | Check network, query duration, socket timeout, and server logs. |
| SQLTransientConnectionException | Potentially transient connection failure per JDBC classification | Retry only when transactions/outcomes are handled safely. |
| SQLNonTransientConnectionException | Non-transient connection failure per driver classification | Check config, topology, and endpoint health. |

Never classify solely by message text. Log SQLState, vendor code, exception class, timestamp, connected host, query duration, and transaction stage. Avoid logging passwords, access tokens, or sensitive data.

SQL errors such as duplicate key, deadlock, or missing privileges are not connection errors. Handle them by specific root cause instead of pushing every SQLException through the same retry loop.

## 12. What Happens to a Transaction During Failover?

Distinguish disconnection timing:

| Time of disconnection | What the application knows | Handling |
|---|---|---|
| Before sending statement | Statement was not sent per application flow | Safe to open a new connection and retry if request has no side effects. |
| While statement is running | Server may have received part of or completed work, but response was lost | Inspect transaction state; for writes, never guess outcome from timeout alone. |
| After statement, before COMMIT | Transaction has not been confirmed committed | Once session ends, uncommitted InnoDB transactions roll back; clean up connection/session and retry whole transaction when safe. |
| While sending COMMIT | Outcome is unknown on the client | Look up idempotency key or business state before rerunning. |
| After receiving COMMIT acknowledgment | Server confirmed commit to the client | Transaction committed on server; durability and replica visibility depend on MySQL/topology settings. |

If the session dies, the server handles uncommitted transactions per storage engine rules upon detecting session termination. However, the application cannot know the exact moment that happens. Never open a new connection and call rollback thinking it rolls back the old transaction; rolling back on a new session does not touch the old session's transaction.

Nor does failover guarantee a replica already received the old primary's final transaction. Potential data loss depends on replication mode, durability settings, quorum, and promotion procedures.

## 13. Idempotency Keys for Safe Retries

A write request may be resent due to client timeouts, gateway retries, or user double-clicks. Use a unique idempotency key per business operation so the server recognizes already-processed requests.

Example table storing request results:

~~~sql
CREATE TABLE sales.processed_requests (
  request_id VARCHAR(64) NOT NULL,
  operation_type VARCHAR(40) NOT NULL,
  result_order_id BIGINT NULL,
  result_status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (request_id)
) ENGINE=InnoDB;
~~~

When handling a request, generate request_id at the application layer and reuse the exact same key across all retries of that single business operation.

Transaction flow:

1. Start transaction.
2. Insert request_id into processed_requests.
3. Perform business mutations.
4. Store outcome or created entity ID in processed_requests.
5. Commit transaction.
6. Return result to client.

If request_id already exists, the application reads the stored outcome and returns it without re-applying business mutations.

Illustrative SQL example:

~~~sql
START TRANSACTION;

INSERT INTO sales.processed_requests (
  request_id, operation_type, result_status
)
VALUES (
  'req-2026-000001', 'CREATE_ORDER', 'PROCESSING'
);

INSERT INTO sales.orders (
  customer_id, status, total_amount
)
VALUES (
  42, 'NEW', 125.00
);

SET @new_order_id = LAST_INSERT_ID();

UPDATE sales.processed_requests
SET result_order_id = @new_order_id,
    result_status = 'COMPLETED'
WHERE request_id = 'req-2026-000001';

COMMIT;
~~~

If the transaction rolls back, both the request record and the order roll back. If commit succeeds yet the response is lost, the retry inserting the same request_id hits a duplicate key; the application catches the duplicate error, reads the existing record, and returns the previous result.

In real code, use PreparedStatement for request_id and input parameters. Handle duplicate key errors specifically; never swallow all SQL errors. Retain idempotency records long enough per retry and reconciliation policies.

### 13.1. Avoiding Stuck PROCESSING States

If a PROCESSING record is committed separately before business logic runs, a process crash can leave an orphaned in-progress state. A simpler design creates the record, applies business changes, and marks COMPLETED within the same InnoDB transaction.

If asynchronous processing is required, use a state machine with leases/owners, timeouts, and explicit recovery. Never assume an old PROCESSING record proves no side effects occurred.

## 14. External Side Effects and the Transactional Outbox

If a transaction writes to MySQL and directly calls a payment gateway, sends email, or publishes messages, both systems do not share one local transaction. A lost MySQL connection cannot roll back side effects in external systems.

Transactional outbox pattern:

1. Inside one MySQL transaction, update business tables and insert an event into an outbox table.
2. Commit both together.
3. A worker reads unpublished events and delivers them to external systems.
4. The worker marks events published or uses status/leases for retries.
5. Consumers use event IDs for idempotent processing.

Example:

~~~sql
CREATE TABLE sales.outbox_events (
  event_id CHAR(36) NOT NULL,
  aggregate_id BIGINT NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSON NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at TIMESTAMP NULL,
  PRIMARY KEY (event_id),
  KEY idx_outbox_pending (status, created_at)
) ENGINE=InnoDB;
~~~

An outbox does not automatically guarantee exactly-once delivery. A worker may publish successfully and crash before marking the event published; on restart, the event may publish again. Consumers must deduplicate by event_id or apply idempotent business logic.

## 15. Application-Layer Retry Policy

A retry policy must define:

- Which exceptions count as transient.
- Which requests can safely be retried.
- Where transaction boundaries sit.
- Whether a fresh connection is required.
- Maximum retry attempts.
- Backoff and jitter.
- Overall request deadline.
- How to handle unknown commit outcomes.
- How metrics and alerts are recorded.

Pseudocode pattern:

~~~text
request_id = generate or receive idempotency key

for attempt from 1 to limit:
    borrow a fresh connection from pool
    begin transaction
    try processing request with request_id
    if succeeded:
        commit
        return result
    if failed before commit and retryable:
        roll back if connection is still usable
        close connection
        wait exponential backoff + jitter
        continue
    if failed during commit:
        close connection
        look up request_id via a new connection
        if already COMPLETED:
            return stored result
        if not found:
            re-execute per idempotency policy
        if still indeterminable:
            route to reconciliation, never write blindly
~~~

Never retry infinitely. Total retry duration must fit inside the request deadline and avoid creating a retry storm while MySQL or the network is recovering.

### 15.1. Exponential Backoff and Jitter

If many clients retry immediately after failover, they can generate a traffic spike right as the database recovers. Backoff spaces out attempts; jitter adds randomness so clients do not synchronize retry bursts.

Illustrative growing wait intervals:

| Attempt | Illustrative wait range |
|---|---:|
| 1 | 100–200 ms |
| 2 | 200–400 ms |
| 3 | 400–800 ms |
| 4 | 800–1600 ms |

These are illustrative values only; apply real caps and deadlines. Never let the driver, pool, and business service each retry independently without a unified retry budget.

## 16. Checking Host Roles and Read-After-Write

After failover, the application must verify the new endpoint's role. A successful TCP connection does not prove the host is primary.

You can inspect server state with an appropriate query:

~~~sql
SELECT
  @@hostname,
  @@server_uuid,
  @@read_only,
  @@super_read_only,
  @@global.gtid_executed;
~~~

These values help inspect host identity and read-only status, but do not replace cluster metadata or promotion workflows. A read-write node is not automatically a valid primary in the topology; a read-only node might still be applying replication.

Read-after-write consistency also matters. If an application writes to the primary and immediately reads from a replica, the replica may not have applied that transaction yet. Mitigations include:

- Keeping read-after-write queries on the writer.
- Using the topology's consistency policies.
- Waiting for the replica to reach the required GTID if your architecture supports it.
- Pinning requests requiring fresh reads to an endpoint with matching consistency guarantees.

Never assume every replica is caught up to the latest transaction immediately after failover.

## 17. Scenarios to Test

Failover must be tested in staging or a game-day environment mirroring production topology. Minimum test scenarios:

| Scenario | What to observe |
|---|---|
| First host port closed | Driver tries another host per config; connect time stays within deadline. |
| Idle connection closed by firewall | Pool detects and evicts stale connection before or during next borrow. |
| MySQL restarts mid-SELECT | Application classifies connection exception and handles retryable reads. |
| Connection drops between UPDATE and COMMIT | Uncommitted transaction does not resume on the new session. |
| Response lost right after COMMIT | Application queries idempotency key and resolves outcome. |
| Primary failover in InnoDB Cluster | Router updates routing; in-flight requests handle exceptions cleanly. |
| Lagging or unpromoted replica | No writes sent to replica merely because host accepts TCP connections. |
| All hosts unavailable | Bounded retries, circuit breaker, and clear error reporting. |
| Old host returns after partition | Two writers never serve the same workload outside controlled topology. |

During tests, record timestamps, hosts, SQLState, vendor codes, reconnect durations, transaction outcomes, request IDs, and retry counts. Never use real production data without proper safeguards.

## 18. Java Example Handling Unknown Outcomes

The code below illustrates the concept, not a complete retry framework. The key idea is reusing the same request ID and querying outcome after a commit failure.

~~~java
public OrderResult createOrder(
        DataSource dataSource,
        String requestId,
        long customerId,
        BigDecimal total) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            // Try recording the request key in the same business transaction.
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO sales.processed_requests " +
                    "(request_id, operation_type, result_status) " +
                    "VALUES (?, 'CREATE_ORDER', 'PROCESSING')")) {
                ps.setString(1, requestId);
                ps.executeUpdate();
            }

            long orderId;
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO sales.orders " +
                    "(customer_id, status, total_amount) " +
                    "VALUES (?, 'NEW', ?)",
                    Statement.RETURN_GENERATED_KEYS)) {
                ps.setLong(1, customerId);
                ps.setBigDecimal(2, total);
                ps.executeUpdate();

                try (ResultSet keys = ps.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Missing generated order id");
                    }
                    orderId = keys.getLong(1);
                }
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    "UPDATE sales.processed_requests " +
                    "SET result_order_id = ?, result_status = 'COMPLETED' " +
                    "WHERE request_id = ?")) {
                ps.setLong(1, orderId);
                ps.setString(2, requestId);
                ps.executeUpdate();
            }

            connection.commit();
            return new OrderResult(orderId, "COMPLETED");

        } catch (SQLException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
~~~

If commit throws due to connection loss, this method simply propagates the error; the caller must open a new connection and look up request_id. If a COMPLETED record exists, return the stored order ID. If no record exists, the prior transaction likely rolled back; rerun with the exact same request ID under idempotency rules. If status cannot be determined, route the request to reconciliation.

In real deployments, also handle duplicate key exceptions on the request insert step, check operation_type, verify request_id matches the same payload/customer, and never reuse one request_id across different business operations.

## 19. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Enabling autoReconnect and assuming transactions stay alive | Application continues on a fresh session after losing prior transaction/session state | Handle connection failures explicitly and start a new transaction safely. |
| Retrying immediately when COMMIT throws | An already-committed transaction can execute twice | Use idempotency keys and verify outcomes. |
| Adding replicas to a writer failover list | Accidental writes to read-only or lagging nodes | Use topology/Router with proper promotion and role-based routing. |
| Assuming multi-host URL auto-promotes primaries | Driver connects to a node lacking writer role | Use Group Replication/Orchestrator or dedicated HA tooling. |
| Disabling failOverReadOnly without role controls | Risk of writing to an unpromoted replica | Enforce protections at server, Router, and app layers; test promotion. |
| Setting overly short timeouts | Valid queries get aborted, causing errors and wasteful retries | Base timeouts on SLAs and real p99 metrics. |
| Pool holds connections longer than network idle timeout | Requests borrow closed stale connections | Align validation, keepalive, and maxLifetime with infrastructure limits. |
| Multiple retry layers without a shared budget | Retry storms and recovery overload | Designate one retry owner, cap attempts, and enforce deadlines. |
| Calling external APIs inside DB transactions | Side effects do not roll back with MySQL | Use transactional outbox and idempotent consumers. |
| Checking only connection success | Blind to stale data or invalid write privileges | Check node role, GTID, quorum, and replication state. |

## 20. Configuration and Operations Checklist

- [ ] Documented MySQL topology and each host's role.
- [ ] Never relied on autoReconnect as a transaction recovery guarantee.
- [ ] Multi-host URL contains only endpoints valid for the intended failover mode.
- [ ] Distinguished failover URLs, loadbalance URLs, and replication URLs.
- [ ] Defined primary promotion and split-brain prevention mechanisms.
- [ ] Checked failOverReadOnly and related properties for your driver version.
- [ ] Configured TLS server identity verification for every endpoint.
- [ ] Aligned connectTimeout, socketTimeout, and query timeouts with SLAs.
- [ ] Configured connection pool validation, maxLifetime, and sizing limits.
- [ ] Properly closed Connection/Statement/ResultSet resources.
- [ ] Application classifies SQLState and vendor error codes.
- [ ] Transactions have clear boundaries.
- [ ] Idempotency keys exist for retryable write requests.
- [ ] Ambiguous COMMIT outcomes are reconciled before retrying.
- [ ] External side effects use outbox or equivalent mechanisms.
- [ ] Tested connection drops before, during, and after COMMIT.
- [ ] Tested primary failover, replica lag, and all-hosts-down scenarios.
- [ ] Metrics exist for connection failures, reconnects, retries, transaction outcomes, and pool exhaustion.

## 21. Hands-On Exercises

### Exercise 1: Observing autoReconnect

In a test environment, open a Connection and run a query. Stop MySQL or sever the network, then run the next query with autoReconnect off and on. Record the exceptions, Connection state, transaction state, and session variables. Explain why reconnecting does not recover the previous transaction.

### Exercise 2: Multi-Host URL

Set up two MySQL endpoints in a test topology. Configure a multi-host URL, take the first host down, and observe the driver trying the remaining endpoint. Confirm the alternate endpoint has the right data, role, and write permissions per design.

### Exercise 3: Lost COMMIT Response

Execute a transaction with a unique request ID. Use a proxy or test harness to drop the connection right after the server receives COMMIT but before the client receives the response. Reconnect, query the request ID, and determine whether the transaction completed.

### Exercise 4: Pools and Stale Connections

Configure a pool with validation and maxLifetime. Set a test proxy/firewall idle timeout shorter than connection lifetime, then observe how the pool evicts stale connections and creates fresh ones. Verify requests never reuse dead sessions.

### Exercise 5: Failover on InnoDB Cluster

Using a Router endpoint, run read/write transactions and rehearse a primary switchover. Record interruption duration, JDBC errors, retry counts, and how the application handled in-flight transactions. Confirm request IDs prevent duplicate orders.

### Exercise 6: Retry Storms

Run multiple clients and make the endpoint temporarily unavailable. Compare unbounded retries against exponential backoff with jitter, deadlines, and a circuit breaker. Measure connection attempts, recovery time, and MySQL/Router load.

Failover gives applications a chance to connect to a healthy endpoint; autoReconnect may attempt to re-establish a connection in some scenarios. Neither recovers an old session's transaction, and neither resolves COMMIT outcomes when responses are lost. Let topology manage node roles, let the pool manage connection lifecycles, and let the application manage idempotency and business outcomes; test disconnections around COMMIT before deploying to production.
