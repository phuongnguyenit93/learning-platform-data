# Reading Syntax Errors, Authentication Errors, Unavailable, and Timeouts

## 1. Reading Error Messages to Pinpoint the Exact Failure Layer

In Apache Cassandra, Java applications or `cqlsh` connect to a node via the **native CQL protocol** (typically over TCP 9042). The node receiving the query acts as the **coordinator**, locates replicas from the partition key, replication strategy, and topology, and collects responses according to the **consistency level** (CL). A statement can fail due to the CQL itself, user identity, table permissions, replica state, or the network.

For the **Tools and Connections** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, reading errors is not just looking for a line containing "Exception." We must determine **whether the error occurred before or after the request reached Cassandra**, and whether it resulted from invalid CQL or a distributed system failing to satisfy read/write conditions. This skill is essential when practicing partition keys, query-driven table design, replication, consistency, repair/compaction, and Java Driver connectivity.

**Learning objectives:**

1. Distinguish **syntax errors** from **syntactically valid CQL that violates schema or query rules**.
2. Distinguish **authentication** (login failure) from **authorization** (login succeeded, insufficient permissions).
3. Interpret **Unavailable** messages in terms of required versus alive replicas.
4. Distinguish **ReadTimeout**, **WriteTimeout**, **driver/request timeout**, and **TCP connection loss**, without drawing false conclusions about write outcomes.
5. Use `SHOW HOST`, `DESCRIBE`, `CONSISTENCY`, `TRACING`, `nodetool`, and logs to narrow down root causes.
6. Write Java Driver code that logs contextual errors without leaking passwords, and avoid dangerous retries.

## 2. Stage-by-Stage Error Map

~~~mermaid
flowchart TD
    A["Java app or cqlsh sends request"] --> B{"Do DNS/TCP reach the native port?"}
    B -->|"No"| C["Connection refused, connect timeout, unknown host"]
    B -->|"Yes"| D{"Do TLS/native handshake and login succeed?"}
    D -->|"No"| E["TLS handshake, AuthenticationException, protocol error"]
    D -->|"Yes"| F{"Are CQL syntax and schema valid?"}
    F -->|"No"| G["SyntaxException or InvalidRequest"]
    F -->|"Yes"| H{"Is the role permitted to run the operation?"}
    H -->|"No"| I["Unauthorized"]
    H -->|"Yes"| J{"Are enough replicas alive for chosen CL?"}
    J -->|"No"| K["Unavailable"]
    J -->|"Yes"| L{"Did enough responses arrive before deadline?"}
    L -->|"No"| M["ReadTimeout / WriteTimeout / driver timeout"]
    L -->|"Yes"| N["Successful RESULT"]
~~~

This diagram shows a **practical triage flow**, not an immutable internal check order across all versions. For example, certain schema/permission errors may be detected at different points during request processing. What matters is **separating the connection layer, request validation layer, and distributed execution layer**.

| Error Group | Typical Symptoms | What to Check First |
| --- | --- | --- |
| CQL syntax | `SyntaxException`, points to `line/column` | Statement structure, commas/semicolons, keywords, quotes. |
| Invalid request/schema | `InvalidRequest`, `InvalidQuery`, or equivalent message | `DESCRIBE TABLE`, partition key, data types, table/column names. |
| Authentication | `AuthenticationException`, `AuthenticationFailed` | Username/password, auth provider, TLS, role login permission. |
| Authorization | `Unauthorized` or `UnauthorizedException` | Actual role, `GRANT`, permissions on keyspace/table. |
| Insufficient replicas | `Unavailable` or `UnavailableException` | Requested CL, replication factor, datacenter, Up/Down node status. |
| Slow/unresponsive replicas | `ReadTimeout`, `WriteTimeout` | Response count, deadlines, load, and internode networking. |
| Client deadline exceeded | `DriverTimeoutException`, driver request timeout (exact name varies by version) | Application deadline, connectivity, server latency, paging/queues. |
| Client cannot reach nodes | `AllNodesFailedException` (Java Driver 4.x), connect timeout | Contact points, native port, TLS, advertised peer addresses. |

Exception class names and cqlsh formatting vary across Cassandra, cqlsh, and Java Driver versions. **Do not rely solely on the exception name**: read the message, CQL statement, host/coordinator, CL, and timestamp.

## 3. Setting Up a Safe Lab for Reading Errors

The examples below use a **single-node Cassandra instance, RF = 1**, so you do not need to stop nodes or touch production cluster data. To observe multi-replica failures and quorum differences, use a dedicated lab cluster with an appropriate topology.

Connect from a terminal where `cqlsh` is installed:

~~~bash
cqlsh 127.0.0.1 9042
~~~

In cqlsh, verify the endpoint and create the table:

~~~sql
SHOW HOST;
SHOW VERSION;

CREATE KEYSPACE IF NOT EXISTS error_diagnostics_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS error_diagnostics_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO error_diagnostics_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 'temperature', 25.1);

INSERT INTO error_diagnostics_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:05:00Z',
        22222222-2222-4222-8222-222222222222, 'temperature', 25.3);
~~~

`(device_id, event_day)` is the **composite partition key**. Within a partition, Cassandra sorts rows by `event_time` descending and then `event_id` ascending. The two `INSERT` statements use fixed primary keys: re-running the lab **upserts** the same rows without creating duplicate primary keys.

A valid baseline query for comparison:

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_type, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Expected result: **two rows**, with timestamp 01:05 before 01:00. `SimpleStrategy`/RF = 1 is strictly for lab use. Multi-datacenter systems typically use `NetworkTopologyStrategy` with per-datacenter RF; do not copy this setup as a production standard.

## 4. Syntax Errors: Reading Messages and Fixing the Right Spot

### 4.1. What Is `SyntaxException`?

CQL has its own grammar. When a token appears in an unexpected position or a required element is missing, the parser may return **`SyntaxException`**. Intentionally invalid example:

~~~sql
-- Wrong: trailing comma right before FROM.
SELECT event_time, FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

A message may look **similar to**:

~~~text
SyntaxException: line 1:... mismatched input 'FROM' ...
~~~

This is only an **illustrative message pattern**, not fixed output. Exact phrasing and column numbers depend on the version and where cqlsh breaks lines. How to read it:

1. Locate the failing statement in your cqlsh history or script.
2. Read `line` and `column` if provided; that is where the parser detected an anomaly, **not always the original offending character**.
3. Inspect tokens both before and after the reported location, especially commas, parentheses, quotes, and `;`.
4. Fix small statements individually and test them in the lab before editing large scripts.

Corrected version:

~~~sql
SELECT event_time
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

### 4.2. `SyntaxException` vs. `InvalidRequest`

A statement can be **grammatically valid yet violate the query model**. Example:

~~~sql
-- Valid SELECT syntax, but WHERE omits the partition key.
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE event_time > '2026-11-21T01:00:00Z';
~~~

On this lab table without an appropriate index, Cassandra typically rejects it because it cannot route/read efficiently with that condition or because it requires disallowed data filtering. The error falls under **InvalidRequest/InvalidQuery**, **not** a password error and not simply a lost connection.

To fix it properly, return to **query-driven table design**. The lab query must filter on both `device_id` and `event_day`:

~~~sql
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
  AND event_time > '2026-11-21T01:00:00Z';
~~~

With clustering column `event_time timestamp`, a range condition on `event_time` after specifying the partition is valid. Do not blindly add `ALLOW FILTERING` to every query just to "silence the error" without evaluating partition scan cost, schema, and real query patterns.

### 4.3. Common Syntax and Data Errors

| Symptom | Interpretation | Fix |
| --- | --- | --- |
| `SyntaxException` near `FROM` or `WHERE` | Bad column list, missing punctuation, misplaced keyword. | Inspect tokens around the reported position and verify `SELECT` syntax. |
| `unconfigured table` / table does not exist | Wrong table/keyspace name or not created yet. | Run `DESCRIBE KEYSPACES;`, `DESCRIBE TABLE keyspace.table;`. |
| `Unknown identifier` / column does not exist | Column name mismatches schema, possibly due to case/quoted identifiers. | Read the table definition and exact column names. |
| Data type mismatch | Passing a string for UUID/int or an invalid timestamp format. | Check CQL types; in Java, pass correctly typed bind values. |
| Missing partition key error | Query pattern does not match the primary key. | Identify the partition key from `DESCRIBE TABLE`; design tables per query. |
| Query valid only in another keyspace | Session `USE` points to the wrong keyspace with an identically named table. | Use `keyspace.table` or re-verify `USE`. |

**In scripts:** `cqlsh -f script.cql` and `SOURCE 'script.cql';` run multiple statements sequentially, but do not turn the script into a transaction. One failing statement does not roll back earlier statements that already succeeded. Verify schema creation order, written data, and script re-run safety.

## 5. Authentication vs. Authorization Errors: Do Not Conflate Them

### 5.1. Where Does Authentication Occur?

If the server enables `PasswordAuthenticator`, the client must supply a valid login identity during native session setup. Example:

~~~bash
# Sample connection when the account is provisioned.
cqlsh db.example.internal 9042 --ssl -u report_reader
~~~

`db.example.internal` is an example; a real server must have a reachable native endpoint. `--ssl` is used when the server configures TLS; accounts and CA certificates must match the environment. Avoid passing passwords via `-p` so they are not exposed in shell history, process lists, or logs.

If the password is wrong, the role cannot log in, or the auth backend is unavailable, the result may be `AuthenticationFailed` or `AuthenticationException`. Key indicator: **no valid CQL session exists yet** to execute `SELECT`.

Safe verification steps:

1. Confirm the client is connecting to the right cluster/node/port, not mixing up production and staging.
2. Confirm whether the server requires TLS, and whether the CA/server certificate and hostname are valid.
3. Check the identity **actually used by the application** (not just the username written in docs), ensure the password was updated via your secret manager, and confirm the role has `LOGIN = true`.
4. With multiple nodes where the issue hits only certain nodes, inspect the status and replication of **`system_auth`**, auth caches, clock/config, and server logs.
5. Never brute-force passwords repeatedly, and never disable `PasswordAuthenticator` or TLS as a temporary workaround.

### 5.2. Authorization Occurs After Authentication

Suppose the user logged in successfully, yet the query:

~~~sql
SELECT *
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

returns **`Unauthorized`**. This indicates the role has not been granted the right `SELECT` permission on the table/keyspace, or there is a discrepancy in identity, role inheritance, or caching. Changing syntax or raising consistency will not fix a permission error.

In a lab with `CassandraAuthorizer` enabled, an admin account can grant least-privilege access:

~~~sql
-- Run as an authorized admin role.
GRANT SELECT ON TABLE error_diagnostics_lab.events_by_device_day
TO report_reader;

-- Inspect permissions depending on privileges and Cassandra version.
LIST ALL PERMISSIONS OF report_reader;
~~~

This assumes `report_reader` already exists with login enabled. In real systems, inspect existing grants, inherited roles, and authorization policies before making changes. `GRANT` may take time to propagate through authorization caches across nodes; do not assume every active connection sees it immediately.

If the role only has `SELECT`, an `INSERT` on the same table **must be rejected**, even though `SELECT` succeeds. That is expected **least-privilege** behavior, not a Cassandra bug.

| Error Type | Example Response | Resolution |
| --- | --- | --- |
| **Authentication** | "Bad credentials" or `AuthenticationException` during session creation. | Check role, login flag, password, auth backend, and TLS. |
| **Authorization** | `Unauthorized` when running `SELECT`, `INSERT`, or DDL. | Check resource grants, role inheritance, and `CassandraAuthorizer`. |
| **TLS certificate error** | `SSLHandshakeException`, hostname/CA verification failed. | Fix truststore, hostname/SAN, cert chain, and mTLS if used; do not randomly change passwords. |

**Note:** TLS/mTLS verifies identity at the transport layer; under `PasswordAuthenticator`, clients may still need a username/password even after TLS succeeds. Client ↔ server encryption (`client_encryption_options`) and internode encryption (`server_encryption_options`) are separate configurations.

## 6. Unavailable: Not Enough Live Replicas for Consistency

### 6.1. How Cassandra Evaluates Availability Before Waiting

**Replication factor (RF)** determines how many replicas a partition has per keyspace/datacenter; **consistency level (CL)** determines how many responses an operation requires. When the coordinator sees that the number of **currently alive** replicas cannot satisfy the CL, it may fail fast with **`Unavailable`** instead of waiting until timeout.

Illustrative message:

~~~text
Unavailable: Cannot achieve consistency level QUORUM
Required replicas: 2; alive replicas: 1
~~~

Exact wording depends on the version. Do not copy the "required/alive" counts from an example to explain a real cluster; read the **required and actual replica counts** from the request's own error message.

### 6.2. Replica Counts for a Single Datacenter with RF = 3

| Consistency Level | Replicas Needed for RF = 3 (One DC) | If Only 1 Replica Is Up |
| --- | ---: | --- |
| `ONE` | 1 | Can succeed if that node responds. |
| `TWO` | 2 | Insufficient; may return `Unavailable`. |
| `QUORUM` | 2 | Insufficient; may return `Unavailable`. |
| `LOCAL_QUORUM` | 2 in the target DC | Insufficient in a single-DC RF = 3 case. |
| `ALL` | 3 | Insufficient. |

With multiple datacenters, `LOCAL_QUORUM` computes quorum **within the local DC**, whereas `QUORUM` computes it across the system's replica set per the corresponding consistency semantics. Read the actual replication definition rather than applying the RF = 3 table above to every DC. With RF = 1 in the lab, **`LOCAL_QUORUM` requires only 1 replica** in that RF = 1 DC, not 2.

Quorum balances consistency and availability, but does not create multi-row transactions, fix partition key design, or replace LWT (`IF`) when conditional updates are required.

### 6.3. Practicing Insufficient Replicas in the RF = 1 Lab

On the single-node lab created in Section 3:

~~~sql
-- Valid query with RF=1.
CONSISTENCY ONE;
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Intentionally choose a CL requiring 2 replicas to demonstrate the error.
-- Do this only in an RF=1 lab; never arbitrarily change CL in production.
CONSISTENCY TWO;
SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';

-- Reset CL after observing.
CONSISTENCY ONE;
~~~

The second query typically returns `Unavailable` or a message stating **the requested consistency cannot be achieved**, because RF = 1 has only one logical replica. It does not prove a node is down; **the CL requirement itself exceeds the configured replication factor**.

To evaluate real node-loss scenarios, use a multi-node lab cluster with non-critical data and a recovery plan. Never stop a production node to "test Unavailable."

### 6.4. Addressing `Unavailable` Properly

1. Confirm the **keyspace** the query accesses and its replication strategy:

   ~~~sql
   DESCRIBE KEYSPACE error_diagnostics_lab;
   CONSISTENCY;
   ~~~

2. Check cluster status from an authorized node:

   ~~~bash
   nodetool status
   nodetool gossipinfo
   ~~~

3. Verify whether the relevant nodes are running and **internode networking** (typically 7000) is open; check rack/datacenter placement and gossip info.
4. In production, evaluate the node incident, recovery plan, and business requirements before altering CL. **Lowering CL can weaken the consistency guarantees the application relies on.**
5. If changing the replication factor, follow an operational plan so data and actual replicas synchronize; editing the keyspace schema alone does not guarantee data already has enough copies.

## 7. Timeouts: Waited Without Receiving Enough Qualifying Answers

`Unavailable` means the coordinator already knows not enough replicas are *alive* to meet CL. A **timeout** usually means the request or one of its stages **did not finish within its deadline**. Distinguish server/coordinator timeouts from client/driver timeouts.

### 7.1. Comparing Timeout Types

| Type | Where Observed? | Key Meaning to Remember |
| --- | --- | --- |
| **ReadTimeout** | Cassandra coordinator returns a read error over native protocol. | Did not receive enough read responses/data within deadline; may involve slow replicas, disk/compaction/tombstones/network. |
| **WriteTimeout** | Coordinator returns a write error before deadline. | Not enough write acknowledgments arrived in time; **some or all replicas may still have applied the write**. |
| **Driver/request timeout** | Java Driver or client wait deadline expires. | Client received no result within its deadline; the server request may still be running or already completed. |
| **Connect timeout** | TCP connection setup timed out. | No stable native session yet; inspect routing, listener, firewall, DNS. |
| **ReadFailure / WriteFailure** | Server reports processing error at a replica. | Explicit error response from replicas, distinct from simply timing out. |

Illustrative messages:

~~~text
ReadTimeout: received 1 responses, required 2
WriteTimeout: received 1 acknowledgements, required 2
DriverTimeoutException: query timed out after a client deadline
~~~

Exact names and extra fields (write type, data present, coordinator, request/trace ID) vary. When `received`/`required` appears, interpret those counts alongside **CL, RF, and DC**.

### 7.2. `ReadTimeout` Does Not Mean Data Does Not Exist

In Cassandra, reads may require multiple replicas coordinating, digest/reconciliation steps, and fetching data to satisfy CL semantics. A slow node due to GC, compaction, SSTable reads, heavy tombstones, or flaky networking can prevent the coordinator from collecting enough results on time.

When encountering `ReadTimeout`:

- Check whether `WHERE` includes the right **partition key**; wide scans, oversized partitions, or large multi-page reads raise cost.
- Inspect `nodetool status`, node resources, latency, compaction, and server logs; optionally enable `TRACING ON` for **one controlled representative query**.
- Verify active consistency, RF, datacenter, and timeout settings.
- Do not conclude "the row does not exist": this is a **failed/incomplete read**, not a `SELECT` returning zero rows.

### 7.3. `WriteTimeout` and Indeterminate Write Outcomes

A coordinator may have dispatched a write to multiple replicas, and one or more replicas may have persisted the data before the client receives `WriteTimeout`. If the application **retries blindly**, it risks logical duplicates or repeated side effects.

Consider two scenarios:

1. **Idempotent upsert with same primary key and same values:** re-running may be safe in some situations, though cell timestamps, concurrent writes, TTLs, and business rules must still be considered.
2. **Counter increments, sequence allocation, "debit balance" logic, event-emitting workflows:** blind retries when the write outcome is unknown can cause the business effect to happen **more than once**. Use idempotency keys, conditional guards, or reconciliation workflows depending on business needs.

With **LWT** (`INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...`), timeouts can occur during the Paxos/commit phase. **Do not assume the condition was never applied**; read/reconcile state and retry according to application semantics and supported driver policies.

**Safety rule:** for writes with unknown outcomes, verify the **primary key and business state**, design for idempotency, and inspect metrics/logs before deciding to retry. Do not raise retry counts indefinitely or arbitrarily change consistency.

### 7.4. Client Timeout vs. Server Timeout

Visualize the timeline:

~~~mermaid
sequenceDiagram
    participant App as Java Driver (2s deadline, example)
    participant Coord as Coordinator
    participant Rep as Replica
    App->>Coord: INSERT / SELECT with CL
    Coord->>Rep: Read/write partition
    Note over App: Client deadline expires
    App--xApp: Client reports timeout
    Rep-->>Coord: Replica responds late
    Coord-->>App: Response may arrive later or be ignored
~~~

The **2-second** deadline is illustrative only, not a universal Cassandra/Java Driver default. Client expiration does not mean the server stopped processing or that data was not written. Conversely, when the coordinator returns `ReadTimeout`/`WriteTimeout`, that is a native/server signal containing details about the operation type and replica responses. Inspect the **stack trace, exception class, and message** to tell them apart.

**Beware of retry storms:** when many clients time out simultaneously, immediate continuous retries can push an overloaded cluster further behind. Use timeouts, retry policies, backoff/jitter, and circuit breakers aligned with SLAs alongside concurrency limits; only auto-retry operations confirmed safe.

## 8. Using `cqlsh` and `nodetool` to Gather Evidence

### 8.1. Verify the Right Cluster and Schema First

~~~sql
SHOW HOST;
SHOW VERSION;
DESCRIBE KEYSPACES;
DESCRIBE KEYSPACE error_diagnostics_lab;
DESCRIBE TABLE error_diagnostics_lab.events_by_device_day;

-- View or change CL in cqlsh for the current session.
CONSISTENCY;
CONSISTENCY ONE;
~~~

`SHOW HOST` verifies cqlsh's connection target. `DESCRIBE` confirms schema, keyspace replication, and primary keys. `CONSISTENCY` **only alters the current cqlsh session's consistency**, not a running Java application's configuration.

### 8.2. What `TRACING` Helps With and What It Does Not

~~~sql
-- Enable only briefly to investigate a small query.
TRACING ON;

SELECT event_time, value
FROM error_diagnostics_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21'
LIMIT 2;

TRACING OFF;
~~~

Tracing can show the coordinator, replica activities, step timings, and trace session ID. However, tracing adds overhead and requires permissions/ability to read trace data. For **pre-session authentication errors**, CQL tracing cannot run yet; for **immediate `Unavailable`**, trace output may be minimal or absent. Never enable tracing across all production traffic just to hunt down one slow request.

### 8.3. Checking Cluster Health from an Admin Node

~~~bash
# Status of nodes in the ring from the queried node's perspective.
nodetool status

# Gossip/endpoint info; useful when suspecting internode networking.
nodetool gossipinfo

# Streaming progress, e.g., during bootstrap/repair.
nodetool netstats

# Observe active compactions when seeing slow-read symptoms.
nodetool compactionstats
~~~

Combine these with **server logs, CPU/GC, disk I/O, latency percentiles, dropped messages, tombstones, and queue/concurrency metrics**. A node showing `UN` does not guarantee all of its queries are fast. Do not trigger `repair` or `compact` simply because you see timeouts: those are operational commands with real resource costs and specific purposes—diagnose the root cause first.

### 8.4. If the Failure Occurs During Connection

From the **client host**, test:

~~~bash
# TCP: confirms socket reachability only; does not test CQL/auth.
nc -vz db.example.internal 9042

# If the endpoint requires TLS:
openssl s_client -connect db.example.internal:9042 \
  -servername db.example.internal
~~~

On Windows:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 9042
~~~

If cqlsh works on the node itself while an app in an external container/VM fails, check bind address `rpc_address`, advertised endpoint `broadcast_rpc_address`, DNS, container networking, firewalls, and TLS on **each native peer**. The Java Driver may connect to the contact point yet fail on discovered nodes. That is not a CL-related `Unavailable` if the native handshake with the peer never completed.

## 9. Java Driver 4.x: Logging Proper Error Context Without Leaking Secrets

The snippet below uses the Java Driver 4.x API. Connection values must come from real configuration; for clusters with auth enabled, configure credentials via a secret manager or controlled environment variables. The example below **assumes a lab without auth/TLS** to focus on request error handling.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Duration;
import java.time.LocalDate;

public final class CassandraErrorDiagnostics {
    public static void main(String[] args) {
        String host = System.getenv().getOrDefault("CASSANDRA_HOST", "127.0.0.1");
        String dc = System.getenv().getOrDefault("CASSANDRA_DC", "datacenter1");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(host, 9042))
                .withLocalDatacenter(dc)
                .build()) {

            PreparedStatement ps = session.prepare(
                "SELECT event_time, value " +
                "FROM error_diagnostics_lab.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement statement = ps.bind(
                    "sensor-01", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setTimeout(Duration.ofSeconds(5));

            for (Row row : session.execute(statement)) {
                System.out.println(
                    row.getInstant("event_time") + " : " +
                    row.getDouble("value"));
            }
        } catch (RuntimeException error) {
            // Controlled logging: do not print passwords, tokens, or sensitive bind values.
            System.err.println("Cassandra error type: " +
                error.getClass().getName());
            System.err.println("Message: " + error.getMessage());
            if (error.getCause() != null) {
                System.err.println("Cause type: " +
                    error.getCause().getClass().getName());
            }
            throw error; // Let upper layers decide appropriate response/retry handling.
        }
    }
}
~~~

**Notes on the example:**

- `datacenter1` is an **assumed** lab name; check `SELECT data_center FROM system.local;` and use the real name in `withLocalDatacenter`.
- `setConsistencyLevel(ONE)` applies **to the statement**, separate from `CONSISTENCY ONE;` in an external cqlsh session.
- `setTimeout(Duration.ofSeconds(5))` is an **example deadline**, not an immutable driver default. Real deadlines should reflect SLAs and cluster capacity.
- If the environment requires TLS/passwords, the session must configure a **CA-trusting SSL context and auth credentials**; never disable security to "make errors go away."
- `getClass().getName()` and cause help distinguish **server-side errors** from **client-side errors**. In production, configure loggers safely: error messages can include table names, CQL text, hostnames, or sensitive values.
- In real systems, also capture **request correlation ID, coordinator/endpoint, query name, CL, elapsed time, and retry count** via approved observability; avoid logging full sensitive payloads.

### 9.1. Interpreting Common Exceptions in Java

| Group | Meaning in Java Driver 4.x | Appropriate Action |
| --- | --- | --- |
| `SyntaxError` / invalid query error (exact class name varies by driver version) | Server rejected the CQL. | Fix query/schema/bind values; do not retry verbatim. |
| `AuthenticationException` | Failed to authenticate while establishing connection. | Check auth and secrets; do not retry bad passwords indefinitely. |
| `UnauthorizedException` | Statement denied due to missing permissions. | Grant proper permissions or adjust role per policy; do not weaken security. |
| `UnavailableException` | Not enough replicas for the requested CL. | Check RF/topology, node health, and CL. |
| `ReadTimeoutException` / `WriteTimeoutException` | Server/coordinator returned an operation timeout. | Inspect response counts, why replicas were slow, and idempotency. |
| `DriverTimeoutException` | Client deadline elapsed before receiving a qualifying response. | Check client timeout, backlog, connectivity/latency; write outcome may be unknown. |
| `AllNodesFailedException` | Driver could not establish/maintain valid connections to nodes. | Inspect the per-node error map and root cause: DNS/TCP/TLS/auth/protocol. |

**There is no "catch every exception and retry" formula.** Syntax or permission errors cannot be fixed by retrying. Read timeouts can be retried under certain conditions; write timeouts require understanding idempotency and data semantics. LWTs, counters, and side-effecting workflows require dedicated policies.

## 10. Incident Triage Workflow in Production

When alerted "Cassandra query failed," gather full context before changing configuration:

1. **Identify the request:** timestamp, service/endpoint, cluster/datacenter, host/coordinator, keyspace/table, operation type (read/write/LWT), query pattern, and whether the partition key aligns.
2. **Classify the error:** parse/schema, authentication, authorization, unavailable, server timeout, driver timeout, or connect/TLS.
3. **Verify replica reality:** inspect RF, CL, datacenter, required/alive/responding node counts, and ring state via `nodetool`.
4. **Correlate timelines:** compare client/server timestamps, latencies, GC, disk, network, compaction, streaming, and relevant logs; distinguish one slow node from a cluster-wide outage.
5. **Assess business impact:** did the request partially write or succeed before timing out? Is retrying permitted? Are idempotency/reconciliation mechanisms in place?
6. **Remediate under control:** fix CQL, permissions, credentials, networking, replicas, or tune timeouts/CL per policy. Monitor after the change.
7. **Record root cause and prevention:** add metrics, alerts, proper partitioning, load limits, repair/compaction schedules, and Java Driver compatibility tests as needed.

### 10.1. Actions to Avoid

- **Do not** lower production CL from `LOCAL_QUORUM` to `ONE` just to silence `Unavailable` without agreeing on the required consistency guarantees.
- **Do not** disable TLS, authentication, or authorization when seeing login/`Unauthorized` errors.
- **Do not** leave `TRACING ON` for extended periods under heavy traffic or expand logs to capture passwords/bind values.
- **Do not** blindly retry non-idempotent writes after `WriteTimeout`, client timeouts, or LWT errors.
- **Do not** use `ALLOW FILTERING` as a blanket fix for queries missing a partition key.
- **Do not** run `nodetool repair` or `nodetool compact` to "cure all timeouts" without knowing the root cause and operational cost.

## 11. Quick Reference: Error, First Question, and Next Step

| Error Observed | First Diagnostic Question | Next Step |
| --- | --- | --- |
| `SyntaxException` | Which token did the parser report? | Fix syntax, check terminating `;`, quotes, and keywords. |
| `InvalidRequest` | Do columns, types, primary key, and filters match the schema? | Run `DESCRIBE TABLE` and fix the query or table model. |
| `AuthenticationFailed` | Did the server receive valid credentials and TLS? | Check role login, secret rotation, auth backend, CA/SAN. |
| `Unauthorized` | Does the user actually hold permission on the resource? | Check `GRANT`, role inheritance, authorizer/cache. |
| `Unavailable` | What are required vs. alive replicas, CL, and RF? | Check `DESCRIBE KEYSPACE`, `nodetool status`, internode/topology. |
| `ReadTimeout` | How many responses arrived, which node is slow, is there a hot/large partition? | Metrics, logs, selective tracing, GC/compaction/tombstones. |
| `WriteTimeout` | Did any replica already write? Is the request idempotent? | Reconcile state and retry only under safe policies. |
| `DriverTimeoutException` | What is the client deadline and how far did the server get? | Inspect network/queues/latency, client config, and server logs. |
| `AllNodesFailedException` | Which native endpoints failed and at what stage? | Check DNS, 9042, TLS/auth, discovery, local datacenter. |

## 12. Practice Exercises and Self-Evaluation

1. Set up `error_diagnostics_lab` and run a valid `SELECT` as a **baseline**; record the keyspace, partition key, and active CL.
2. Intentionally place an extra comma before `FROM`. Locate the token reported in `SyntaxException` and fix the query.
3. Test a query with only `event_time` in `WHERE`. Explain why this is a **query-model/`InvalidRequest`** error rather than merely a missing comma.
4. In an auth-enabled lab cluster, distinguish entering a wrong password from logging in successfully when the role lacks `SELECT`. Name the tools and authorized people needed to resolve it.
5. On the RF = 1 lab, set `CONSISTENCY TWO` and read a partition. Predict the error, compare against RF, and then **reset `CONSISTENCY ONE`**.
6. In a theoretical **single-DC RF = 3** cluster, compute the replicas required for `ONE`, `QUORUM`, and `ALL`; explain how `Unavailable` and `ReadTimeout` differ when only one or two replicas respond.
7. Suppose an `INSERT` returns `WriteTimeout` yet one replica already persisted the data. Why would automatically retrying a counter increment be wrong? Propose a reconciliation method.
8. Suppose Java reports `DriverTimeoutException` after 5 seconds while CQL may still be executing. Why must you not conclude the server canceled the statement?
9. Enable `TRACING ON` for a small `SELECT`, inspect the trace, then run `TRACING OFF`. List additional metrics/logs to examine if the trace is inconclusive.
10. The Java Driver connects to the contact point yet reports `AllNodesFailedException` for a peer advertised with a container IP. Explain how to distinguish this native networking/driver discovery error from CL-based `Unavailable`.

**Completion criteria:** you can explain with concrete context why an error occurred, distinguish parse/auth/permission/replica/deadline failures, choose the right diagnostic command, and state **one safe remediation step** for each category.

## References

- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY`, `TRACING`, `DESCRIBE`, and connection options.
- [Apache Cassandra — CQL documentation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/index.html): CQL syntax, primary keys, tables, `INSERT`, `SELECT`, and query conditions.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): coordinator/replicas, replication, and consistency levels.
- [Apache Cassandra — Security](https://cassandra.apache.org/doc/stable/cassandra/operating/security.html): authentication, authorization, and security configuration.
- [Apache Cassandra — nodetool](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): inspecting node status, gossip, streaming, and compaction.
- [Apache Cassandra Java Driver 4.x — Core](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/index.html): sessions, statements, timeouts, consistency, execution, and exceptions.
- [Apache Cassandra Java Driver 4.x — Retry policy](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/index.html): idempotence and choosing retries by error type.
