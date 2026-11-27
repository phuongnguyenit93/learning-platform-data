# MySQL Server Has Gone Away / Lost Connection and Timeouts / Packet Too Large

Errors like `MySQL server has gone away`, `Lost connection to MySQL server during query`, or JDBC `Communications link failure` indicate the client can no longer communicate with MySQL over the current connection. They do not have a single root cause. The server may have closed an idle connection, the MySQL process may have restarted or crashed, the network/proxy may have dropped the socket, the client may have timed out waiting, or a statement/result packet may have exceeded allowed limits.

`Packet too large` messages usually relate to `max_allowed_packet`. Raising timeouts or packet limits arbitrarily can mask bugs, increase memory consumption, or extend how long connections stay held. Pinpoint the stage where the connection dropped, correlate client/server logs, then tune the exact limit and design safe retries.

## 1. Recognizing the Error Group

Common messages:

| Code / Message | Common Meaning | First Investigation Path |
|---|---|---|
| `ERROR 2006 (HY000): MySQL server has gone away` | Client sent a command to a lost or server-closed connection | Idle timeout, server restart/crash, oversized packet, stale connection |
| `ERROR 2013 (HY000): Lost connection to MySQL server during query` | Connection lost while a statement was executing or returning results | Socket/network timeout, server crash, proxy reset, query/result too slow |
| `ERROR 1153 (08S01): Got a packet bigger than 'max_allowed_packet' bytes` | Packet exceeded server or client transport limit | Statement/row/result size and packet limits on both sides |
| JDBC `CommunicationsException` / `Communications link failure` | Connector/J failed to communicate with the server | Inspect `SQLState`, root exception, packet send/receive timing, and JDBC timeouts |
| `Connection reset`, `Broken pipe`, `EOFException` | Socket closed by peer or network layer | Server log, proxy/load balancer, firewall/NAT, and stale pool connections |
| `Too many connections` (`1040`) | Server out of connection slots | Pool sizing, `max_connections`, connection leaks, and application count |

Codes 2006 and 2013 are client-side symptoms and do not directly identify the root cause. For example, 2006 can appear on the first command after an idle period because the server closed the session; 2013 can appear while the server streams a large result set if a proxy hit its idle timeout.

## 2. Distinguishing Timeouts by Layer

The word "timeout" can refer to many different limits. Before changing anything, identify exactly which timer expired:

| Limit | Configured On | What Duration Does It Measure? |
|---|---|---|
| `connect_timeout` | MySQL server | Server waiting for client to send initial connection handshake packet |
| `connectTimeout` | Connector/J | Client waiting to establish TCP connection/handshake per driver |
| `wait_timeout` | MySQL server | Non-interactive connection idle time before the server closes it |
| `interactive_timeout` | MySQL server | Idle time for clients connected with the interactive flag |
| `net_read_timeout` | MySQL server | Server waiting for more bytes from client while reading a packet |
| `net_write_timeout` | MySQL server | Server waiting to write a block of data to client |
| `socketTimeout` | Connector/J | Client waiting to read data from socket; usually measured in milliseconds |
| `connection-timeout` | HikariCP | Application waiting to borrow a connection from the pool |
| `Statement.setQueryTimeout()` | JDBC | Statement execution time limit per JDBC API, in seconds |
| `max_execution_time` | MySQL | Execution time limit for certain `SELECT` queries, in milliseconds |
| `innodb_lock_wait_timeout` | InnoDB | Wait time for row locks |
| `lock_wait_timeout` | MySQL server | Wait time for metadata locks |

Never raise `wait_timeout` to fix an `innodb_lock_wait_timeout` error, and never raise `socketTimeout` to handle a query blocked on row locks. Each limit governs a distinct phase.

## 3. Collecting Configuration and State Before Making Changes

Run these queries on the failing server:

```sql
SELECT VERSION(), @@version_comment, @@hostname, @@port;

SHOW GLOBAL VARIABLES WHERE Variable_name IN (
  'wait_timeout',
  'interactive_timeout',
  'connect_timeout',
  'net_read_timeout',
  'net_write_timeout',
  'max_allowed_packet',
  'net_buffer_length',
  'max_connections',
  'log_error'
);

SELECT
  @@GLOBAL.max_allowed_packet,
  @@SESSION.max_allowed_packet,
  @@SESSION.wait_timeout,
  @@SESSION.net_read_timeout,
  @@SESSION.net_write_timeout;
```

`GLOBAL` values are defaults or limits for new sessions depending on variable scope; existing sessions may retain previously inherited values. When investigating a specific connection, always inspect `@@SESSION` from that exact connection.

Collect status counters:

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN (
  'Uptime',
  'Connections',
  'Threads_connected',
  'Threads_running',
  'Max_used_connections',
  'Aborted_clients',
  'Aborted_connects',
  'Bytes_received',
  'Bytes_sent'
);
```

Most counters accumulate since server startup. Record before/after snapshots within the same window to compute deltas; never interpret a cumulative number as a current error rate. A sharp drop or reset in `Uptime` signals a recent server restart. `Aborted_clients` can climb when clients close abnormally or disconnect mid-session; `Aborted_connects` relates to failed connection attempts.

## 4. Idle Connections Closed by `wait_timeout`

This is a common culprit when applications use connection pools. MySQL closes non-interactive connections after a period of inactivity. JDBC is typically a non-interactive client, making `wait_timeout` a prime suspect.

Example scenario:

1. Application opens a connection and returns it to HikariCP.
2. The connection sits idle longer than MySQL's `wait_timeout` or a proxy/firewall idle limit.
3. The server or network layer closes the socket.
4. The pool still holds the connection object because it has not noticed the dead socket.
5. The next request borrows that connection and hits 2006/2013 when sending a command.

Check:

```sql
SHOW GLOBAL VARIABLES LIKE 'wait_timeout';
SHOW GLOBAL VARIABLES LIKE 'interactive_timeout';
```

To inspect the current session's value:

```sql
SELECT CONNECTION_ID(), @@SESSION.wait_timeout;
```

`wait_timeout` applies only when a connection is idle between statements. A long-running `SELECT` does not get killed merely for exceeding `wait_timeout`. If an actively running query gets dropped, check `socketTimeout`, `net_read_timeout`, `net_write_timeout`, query limits, proxies, and server logs.

### Aligning Connection Pool Lifetimes

Common HikariCP properties:

- `maxLifetime`: maximum lifetime of a connection in the pool; should be shorter than database/proxy connection lifetime limits with a safety margin.
- `keepaliveTime`: interval to test/keep alive idle connections; must be shorter than `maxLifetime` and below the shortest idle timeout along the path.
- `idleTimeout`: how long surplus idle connections may sit idle before eviction, within pool bounds.
- `connectionTimeout`: how long a request waits to borrow a connection from the pool; not a MySQL query timeout.
- `validationTimeout`: time allowed for connection validation checks.

Illustrative Spring Boot configuration:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1500000
      keepalive-time: 120000
```

Values are in milliseconds and illustrative only. Set `keepalive-time` shorter than the actual idle timeout of MySQL, proxies, NAT, or load balancers; set `max-lifetime` shorter than infrastructure connection lifetime limits. Never assume `wait_timeout` is the only limit: proxies may close sockets sooner.

JDBC 4 drivers typically support `Connection.isValid()` for pool validation. There is no need to configure `connectionTestQuery` if the driver and pool already support standard validation, unless specifically required. Validating before checkout catches some stale sockets, though it cannot completely eliminate race conditions between validation and subsequent execution.

## 5. `ConnectionTimeout`, `SocketTimeout`, and Query Timeouts in Connector/J

Connector/J has its own connection properties. Example URL:

```text
jdbc:mysql://db.example.internal:3306/orders?connectTimeout=10000&socketTimeout=60000&tcpKeepAlive=true
```

- `connectTimeout=10000`: client-side connect/handshake wait limit of roughly 10 seconds.
- `socketTimeout=60000`: socket read wait limit of roughly 60 seconds.
- `tcpKeepAlive=true`: enables TCP keepalive on the socket; actual probe timing still depends on OS settings.

Both timeout properties in Connector/J use milliseconds. A value of `0` typically means unlimited for that property; verify documentation for your exact driver version.

`socketTimeout` is not a server-side SQL execution limit. If a valid query takes 90 seconds while the client sets `socketTimeout=60000`, the client closes its socket at second 60 even though MySQL is still executing. The server may continue working for some time before noticing the client disconnected. Choose timeouts based on SLOs, allowed query durations, and proxy timeouts; do not set them artificially low just to fail faster.

### Hikari `connection-timeout` vs. Connector/J `connectTimeout`

Two frequently confused properties:

- Hikari `connectionTimeout`: time spent waiting to borrow a connection from the pool. Exhausted pools or all connections busy can hit this limit.
- Connector/J `connectTimeout`: time spent establishing a new physical connection to MySQL.

If logs show Hikari timing out waiting for the pool, investigate leaks, transactions holding connections too long, pool size, and DB saturation. Raising `connectTimeout` will not fix having zero free connections in the pool.

### Query Timeouts Are Another Layer

JDBC can set a statement timeout:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.setQueryTimeout(20); // seconds

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read results
        }
    }
}
```

`setQueryTimeout()` asks the driver to bound statement execution time. How cancellation is sent and timeout precision depend on driver implementation. In MySQL, you can use `max_execution_time` or the `MAX_EXECUTION_TIME` optimizer hint for `SELECT` when server-side enforcement is needed:

```sql
SET SESSION max_execution_time = 20000;

SELECT /*+ MAX_EXECUTION_TIME(20000) */ id, status
FROM orders
WHERE customer_id = 501;
```

Values are in milliseconds. `max_execution_time` applies to `SELECT` statements within MySQL's supported scope; it does not replace timeouts for all statement types or pool wait times.

## 6. `net_read_timeout` and `net_write_timeout`

These two variables govern MySQL's data exchange with clients:

- `net_read_timeout`: seconds the server waits to read additional data from a client before dropping the connection. Can involve slow client packet sending, uploads, or flaky networks.
- `net_write_timeout`: seconds the server waits to write a data block to a client before dropping the connection. Can involve clients consuming result sets slowly, network congestion, or proxies stalling forwarding.

Check:

```sql
SHOW VARIABLES LIKE 'net_read_timeout';
SHOW VARIABLES LIKE 'net_write_timeout';
```

If uploading large BLOBs or sending batches over slow networks, check `net_read_timeout` and actual upload speeds. If queries return millions of rows and the application reads row-by-row very slowly, check `net_write_timeout`, fetch strategy, and client result-set consumption time.

Do not raise these two variables if the root cause is a bad query plan or a client failing to close result sets. Longer timeouts can keep server threads/connections occupied longer without improving throughput.

## 7. `max_allowed_packet` and Packet-Too-Large Errors

MySQL transmits data in packets. `max_allowed_packet` caps the packet size accepted by the server or client. Oversized packets can cause MySQL to return `ER_NET_PACKET_TOO_LARGE` (1153) and close the connection. Clients may also enforce their own limits; raising the server limit does not automatically raise every driver/tool limit.

Scenarios prone to oversized packets:

- A multi-row `INSERT` concatenated into an enormous single statement.
- A `BLOB`, `MEDIUMBLOB`, `LONGBLOB`, `JSON`, or `TEXT` column holding a large payload.
- JDBC batch statements rewritten into one massive SQL statement.
- A returned row with huge fields or a huge result set.
- Application sending an excessively long `IN (...)` list instead of chunking or using temporary tables.

Check global and session values:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
SELECT @@GLOBAL.max_allowed_packet, @@SESSION.max_allowed_packet;
```

`max_allowed_packet` can be configured up to 1 GB in current MySQL versions, though that does not mean defaulting to it is wise. High limits raise potential memory allocation per packet and create risk when many clients concurrently send large payloads. Defaults also vary by version and client type; always inspect actual settings.

### Raising Packet Limits Safely

Example raising server global to 64 MiB:

```sql
SET GLOBAL max_allowed_packet = 67108864;
```

`GLOBAL` changes normally affect new sessions. Open a fresh connection and verify `@@SESSION.max_allowed_packet`. If a specific session needs an adjustment and the version supports `SESSION` scope, set it in that session:

```sql
SET SESSION max_allowed_packet = 67108864;
```

To persist changes across restarts, manage the variable in the MySQL configuration file or your organization's config management mechanism after testing. Also verify limits on clients, Connector/J, proxies, and import/export tools. For the MySQL command-line client, configure `--max_allowed_packet` per your exact version's documentation.

Do not raise the server limit higher than necessary if applications still build unbounded statements. Measure real payload sizes and enforce limits at the API/application layer.

## 8. Batch Chunking and Handling Large BLOBs / Result Sets

If a transaction sends tens of thousands of rows in one insert, review batch sizing. Size batches by both row count and estimated total bytes, not fixed row count alone. A 500-row batch is tiny for a few integer columns yet huge if each row carries a several-hundred-KB JSON/BLOB payload.

With JDBC batches:

```java
connection.setAutoCommit(false);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO import_item (external_id, payload) VALUES (?, ?)")) {
    int batchSize = 0;

    for (ImportItem item : items) {
        ps.setString(1, item.externalId());
        ps.setBytes(2, item.payload());
        ps.addBatch();
        batchSize++;

        if (batchSize == 200) {
            ps.executeBatch();
            connection.commit();
            batchSize = 0;
        }
    }

    if (batchSize > 0) {
        ps.executeBatch();
        connection.commit();
    }
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(true);
}
```

This illustrates batch chunking; production code must safely handle rollback/restoring connection state and avoid reusing broken connections. If an earlier batch commits and a later batch fails, earlier data remains committed. Use a batch ID, unique key, or idempotency key so retries do not create duplicates.

With `rewriteBatchedStatements=true` in Connector/J, the driver merges batch statements into larger statements for performance. That can produce larger packets; test with realistic payloads and tune batch sizes accordingly.

For large BLOBs, consider `setBinaryStream()`/`setCharacterStream()` to avoid duplicating huge buffers in the application heap, while verifying whether the driver still buffers data and noting that packet limits still apply. For very large files, storing content in object storage and keeping metadata/URIs in MySQL is often more suitable.

`LOAD DATA LOCAL INFILE` fits bulk file ingestion well and streams data over the protocol. Do not assume the entire file must fit into a single packet; still verify limits, client/server configuration, and actual errors.

### Reading Large Result Sets

If a query returns many rows or large per-row payloads, avoid loading the entire result set into memory unnecessarily. Connector/J supports cursor/fetch strategies depending on version, such as `useCursorFetch=true` with a positive fetch size for server-side cursors. Check your driver version and exact implementation details.

Slow result-set consumption forces the server to hold connections and stream data for a long time. Always close `ResultSet` and `Statement` and return connections to the pool; if streaming results, consume or close the stream before running the next statement on that connection.

## 9. Server Restarts, Crashes, or OS Process Kills

If the MySQL process stops, all open connections drop. Clients typically observe 2006, 2013, `Connection reset`, or JDBC errors around the restart time.

Common causes:

- Planned restarts, deployments, or configuration changes.
- MySQL crash due to software bugs, assertions, or storage faults.
- OS killing the process due to OOM.
- Container restarts, rescheduling, or failed health checks.
- Host reboots or storage/network interruptions.
- Administrators or automation killing connections/processes.

Check:

```sql
SHOW GLOBAL STATUS LIKE 'Uptime';
SHOW VARIABLES LIKE 'log_error';
```

Read the MySQL error log at the configured path, service/container logs, and kernel/host logs. Look for `ready for connections`, shutdown, crash recovery, out-of-memory killer, disk full, I/O errors, or signals. `Uptime` reveals a restart occurred; the error log typically reveals why.

If MySQL runs in a container, inspect restart counts, exit codes, container logs, memory limits, volume health, and orchestration events. Never look only at current container status; the container may have restarted and returned to healthy while the application still holds stale sockets.

If failures coincide with a heavy query, check whether the query spiked memory, temporary tables, sorts, or scans; cross-check OOM/crash logs and host resources. Do not conclude the query caused the crash solely because timestamps overlap.

## 10. Network, Firewalls, NAT, and Proxies

TCP connections can be severed by any layer between the application and MySQL:

- Firewalls/NAT dropping idle connections after a timeout.
- Load balancers or proxies enforcing their own idle timeouts.
- ProxySQL or database proxies closing connections due to pool limits or backend state.
- Packet loss, TCP resets, route changes, or DNS switching to a different address.
- TLS middleboxes or expired certificates breaking handshakes for new connections.

If connections fail after a nearly fixed idle interval while MySQL `wait_timeout` is much higher, inspect proxy/firewall/NAT timeouts. If failures hit only one subnet or availability zone, check routing, security groups, DNS, and network telemetry.

`tcpKeepAlive=true` enables client-socket TCP keepalive, yet probe intervals are controlled by the OS and may exceed infrastructure idle timeouts. It does not replace application/pool-layer keepalives. A query actively transferring data also differs from a completely idle connection.

`mysqladmin ping` confirms the server answers a new connection, but does not prove existing pooled connections remain valid. Test connections borrowed from the pool and inspect proxy/network logs at the exact failure timestamp.

## 11. Connection Pools and Evicting Broken Connections

Once a JDBC connection hits a communication error, do not keep using it for subsequent statements. Close/evict the physical connection and let the pool open a new one. With HikariCP, driver exceptions help the pool detect broken connections; still, the application must close connections properly and never hold onto references for reuse.

Principles:

- Use try-with-resources for `Connection`, `PreparedStatement`, and `ResultSet` with clear ownership.
- Never retain connections in singleton fields or across multiple requests.
- Never hold transactions open across external API calls or user waits.
- Size pools based on MySQL capacity, not just application thread counts.
- Align keepalive and max lifetime with database/proxy timeouts.
- Monitor pool active, idle, pending, and timeout metrics.
- After network errors, discard broken connections rather than running `SELECT 1` on a known-broken socket.

Never rely on `autoReconnect` to recover transactions. Reconnecting creates a brand-new session—losing the transaction, session variables, temporary tables, user variables, and locks of the old connection. Modern Connector/J discourages relying on auto-reconnect for transactional apps; let the pool issue a fresh connection at transaction boundaries.

## 12. Safe Retries After Connection Loss

Losing a connection mid-transaction creates two distinct situations:

- **Not yet committed:** the server may roll back the transaction upon detecting connection closure, yet the client cannot safely assume the outcome if failure struck while transmitting commands.
- **During commit or right after sending COMMIT:** the client may receive no response even though the server committed successfully. From the client's perspective, this outcome is indeterminate.

Therefore, never blindly retry a non-idempotent write. For example, re-sending an order creation request can create two orders if the first commit succeeded and only the response was lost.

### Using Idempotency Keys

Generate a stable request ID on the client or business tier and enforce it with a unique constraint:

```sql
CREATE TABLE payment_requests (
  request_id BINARY(16) NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  status VARCHAR(20) NOT NULL,
  PRIMARY KEY (request_id),
  UNIQUE KEY uq_payment_id (payment_id)
) ENGINE=InnoDB;
```

On retry, reuse the same `request_id`. If the first attempt committed, the application finds the existing record and returns the stored result instead of creating a second payment. If absent, execute the designed transaction. Conflict handling must verify matching request payloads rather than blindly ignoring duplicate errors.

### Handling Indeterminate `COMMIT` Outcomes

1. Mark the operation as indeterminate; do not immediately reissue under a new ID.
2. Acquire a fresh connection from the pool.
3. Look up by idempotency key or unique business key.
4. If the transaction exists in a succeeded state, return that result.
5. If absent, replay the transaction with the same key.
6. If still pending, follow a reconciliation process to determine state before retrying.

Apply retries only to classified transient errors, with bounded attempts, exponential backoff, and jitter. Never retry SQL logic errors such as data duplicates, permission denied, or syntax errors.

## 13. Diagnosing by Failure Timing

When the failure happens narrows the root cause:

| Timing | Priority Checks |
|---|---|
| Immediately on connect | DNS/TCP, `connectTimeout`, `connect_timeout`, TLS, overloaded server, or `max_connections` |
| First command after idle period | `wait_timeout`, proxy/NAT idle timeout, stale pool connection |
| While sending large payload | `max_allowed_packet`, `net_read_timeout`, client packet limit, upload throughput |
| During long-running query | `socketTimeout`, query execution limits, server crash/restart, network or proxy timeout |
| While reading large result set | `net_write_timeout`, socket timeout, slow client reads, fetch/buffering, and large packets |
| Right at commit | Network interruption and indeterminate commit outcome; requires idempotency/reconciliation |
| Only under high concurrency | Connection exhaustion, pool queuing, memory pressure, lock contention, or saturation |
| On a fixed periodic schedule | Infrastructure timeouts, job restarts, rotations/deploys, or connection lifetimes |

Do not look only at the final stack trace. Capture the full exception chain, `SQLState`, vendor error code, request timestamp, connection ID if available, query/digest, pool state, and timestamped server logs.

## 14. Ordered Investigation Runbook

Follow this order during incidents to preserve evidence:

**Step 1 — Define scope.** Is one app, one node, one AZ, or every client failing? Do only existing connections fail or can new connections not open either? Does it occur after idle periods, during uploads, mid-query, or while reading results?

**Step 2 — Collect client-side errors.** Record vendor code, `SQLState`, exception chain, time since last packet, URL/driver version, and pool metrics. Mask passwords, tokens, and sensitive data in logs.

**Step 3 — Check the server.** Confirm MySQL is running; inspect `Uptime`, `max_connections`, error log, crashes/OOMs, and disk space. Check `Aborted_clients` and `Aborted_connects` deltas.

**Step 4 — Check timeouts.** Compare `wait_timeout`, `net_read_timeout`, `net_write_timeout`, Connector/J `connectTimeout`/`socketTimeout`, Hikari timeouts, and proxy idle timeouts.

**Step 5 — Check packets.** Estimate sizes of statements, rows, BLOB/JSON fields, and results; compare with `max_allowed_packet` across server, session, and client. Inspect batch rewriting.

**Step 6 — Check the network.** Correlate TCP resets, firewall/NAT, load balancer, proxy, DNS, and TLS logs at the exact timestamp.

**Step 7 — Controlled recovery.** Evict broken connections, reconnect at transaction boundaries, verify write state via idempotency keys, and retry only safe operations.

**Step 8 — Verify after fixing.** Replay idle, long-query, large-payload, and pool-load scenarios; monitor errors, latency, connection churn, and resource utilization.

## 15. Symptom and Remediation Matrix

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Error right after minutes of idle | MySQL/proxy closed idle connection | Measure shortest idle timeout; tune Hikari keepalive/maxLifetime or evict idle connections |
| `2006` right after server restart | Stale connection pointing to stopped process | Check error log/uptime; evict connection and reconnect |
| `2013` near socket timeout duration | Connector/J closed socket on read timeout | Evaluate query duration and SLO; tune `socketTimeout` sensibly or optimize query |
| Error sending BLOB/JSON | Packet exceeded limit | Measure payload, check both client/server max packet, split payload or stream |
| Error during large JDBC batch | Rewritten statement too large | Shrink batch size by bytes, inspect `rewriteBatchedStatements`, raise packet limit safely |
| Error downloading many rows | Slow server writes or slow client reads | Use pagination/cursor fetch, close result sets, inspect `net_write_timeout` and socket timeout |
| Hikari reports connection timeout | Pool cannot hand out connections in time | Check pending/active, leaks, transaction durations, and MySQL capacity |
| `Too many connections` | Combined pools exceed server capacity | Sum pools across all instances, trim excess connections, and manage concurrency |
| Error behind proxy while MySQL healthy | Proxy/NAT dropped the socket | Inspect proxy timeouts and logs; configure keepalive or connection lifetime accordingly |
| Unclear if prior write committed | Response lost during commit | Query idempotency key / business key before retrying |

## 16. Practice Scenario

A Spring Boot service uses HikariCP to connect to MySQL through a proxy. Requests work fine during the day; after low-traffic periods, the first request on some instances intermittently fails with `Communications link failure`. Another import job fails with `Packet too large` on batches containing large JSON payloads.

**Part A — Idle connections:**

1. Log timestamps of the last query and first failure after idle.
2. Read `@@SESSION.wait_timeout`, `@@GLOBAL.wait_timeout`, and the proxy's idle timeout config.
3. Compare actual idle intervals against Hikari's `keepaliveTime` and `maxLifetime`.
4. Check the pool for stale connections, validation failure counts, and proxy logs.
5. Set keepalive shorter than the lowest idle timeout, set max lifetime below connection lifetime limits, and test across an idle interval longer than before.

**Part B — Oversized packets:**

1. Record the largest JSON size and rewritten batch statement size.
2. Compare `@@SESSION.max_allowed_packet`, `@@GLOBAL.max_allowed_packet`, and client/driver limits.
3. Reduce batch sizes by total bytes instead of row count alone.
4. If valid payloads still exceed the limit, raise packet limits just enough on server and client, then open new connections to verify.
5. Test boundary payloads, concurrency, and memory; ensure the app rejects payloads exceeding business limits.

**Part C — Safe retries:**

1. Attach an `import_batch_id` and unique key to each source row.
2. After a connection error, open a fresh connection and check how far the batch committed.
3. Replay only unfinished items using the same batch ID.
4. Reconcile succeeded, rejected, and pending row counts.

Expected outcome: the connection pool stops reusing closed sockets, batch imports enforce clear byte limits, and retries never duplicate data.

## 17. Prevention Checklist

- [ ] Documented MySQL, Connector/J, pool, proxy, and OS/network timeouts.
- [ ] Distinguished `wait_timeout`, `connect_timeout`, `net_read_timeout`, `net_write_timeout`, and `socketTimeout`.
- [ ] Understood Hikari `connectionTimeout` as pool wait time, not query timeout.
- [ ] Aligned `maxLifetime` and `keepaliveTime` below the lowest DB/proxy/NAT limit.
- [ ] Ensured pools do not hold connections open inside long transactions or external calls.
- [ ] Tracked pool active/idle/pending, validation failures, and connection creation metrics.
- [ ] Measured largest statement, row, BLOB/JSON, and result-set sizes.
- [ ] Synchronized packet limits across server, session, client, and driver.
- [ ] Bounded batches by total bytes and used checkpoints/idempotency keys.
- [ ] Closed result sets, statements, and connections properly.
- [ ] Correlated error logs, uptime, OOMs, restarts, and network resets by timestamp.
- [ ] Avoided relying on auto-reconnect to assume transaction recovery.
- [ ] Implemented bounded retries with backoff and reconciliation for indeterminate commits.
- [ ] Tested idle periods, long queries, large payloads, concurrency, and failover in an isolated environment.

## 18. Documenting Incidents for Faster Future Resolution

After resolving an incident, record:

- Full error message, vendor code, `SQLState`, and driver version.
- Timestamp, connection ID, endpoint, and failing application node.
- Idle duration or query duration preceding the error.
- Timeout and packet limit values across server, client, pool, and proxy.
- MySQL error log, container/service logs, network events, and pool metrics.
- Payload sizes, batch sizes, row counts, and involved query digests.
- Whether transactions could have committed and how reconciliation ran.
- Config/code changes along with post-fix verification results.

Never store passwords, tokens, personal data, or full sensitive payloads in runbooks. Retain only metadata and anonymized samples needed to reproduce the issue.

`MySQL server has gone away` and `Lost connection` signal broken communication channels, while timeouts and packet-too-large errors point to distinct limits along the request path. Determining whether the connection dropped while idle, during upload, during server execution, or while streaming results points directly to the right fix: aligning pool lifetimes, tuning timeouts at the right layer, chunking batches by bytes, raising packet limits safely, or addressing server/network restarts. For writes, always verify commit status before retrying to prevent duplicate data.
