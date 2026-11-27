# Aligning CQL Features with Server, Native Protocol, and Driver in Apache Cassandra

## 1. The Problem: Why Does the Same CQL Statement Work in One Environment and Fail in Another?

Apache Cassandra is a distributed **wide-column** database organizing data by **partition key**, replicating across multiple nodes, and modeling tables around queries. In **Advanced CQL**, before adopting a feature in a Java application, asking "Does CQL have this syntax?" is not enough. You must answer three distinct questions:

1. Does the running **Cassandra server** recognize the syntax, data types, and semantics of that feature?
2. Can the **native protocol** negotiated between client and server carry the request types, metadata, parameter values, and results required by the feature?
3. Is the **Java driver** compatible with that server/protocol version, capable of encoding and decoding the data types, and exposing the right API?

For instance, an application's standard `SELECT` queries may run smoothly, yet adding a new data type or trying vector search triggers errors. The root cause might be **the server not supporting the feature yet**, **a mid-upgrade heterogeneous cluster**, **a negotiated protocol unable to express the new type**, or **a driver/codec that does not understand the type**. Each case requires a different fix.

**Principle:** usability of any feature is **the intersection of server, protocol, driver, and deployment configuration**; upgrading a single layer alone does not guarantee the entire feature works end-to-end.

## 2. Four Concepts Commonly Conflated

| Component | What It Does | What It Does Not Do |
|---|---|---|
| **CQL (Cassandra Query Language)** | Language describing schemas and queries: `CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE ... IF`, `USING TTL`, etc. | Does not define how TCP frames are wire-encoded |
| **Cassandra server** | Parses and validates CQL, executes queries, routes reads/writes to replicas, enforces server version and config features | Does not automatically upgrade deployed client libraries |
| **Native protocol** | Client–server wire protocol for handshake, `QUERY`, `PREPARE`, `EXECUTE`, typed values, metadata, paging, and errors | Does not make an older server understand new CQL syntax |
| **Java driver** | Manages connections, discovery, prepared statements, binding, codecs, retries, paging, consistency, and Java type mapping | Cannot provide features the server does not implement |

**Crucial distinction:** **"CQL 3.x" and "native protocol v3/v4/v5" are two completely separate versioning schemes**. Native protocol v4 does not mean "CQL version 4"; forcing a higher protocol version does not make an older server understand newer CQL syntax.

A typical execution flow:

~~~mermaid
flowchart LR
    A["Java application"] --> B["Java driver\nAPI + codecs"]
    B --> C["Native protocol\nQUERY / EXECUTE"]
    C --> D["Cassandra coordinator\nparse + validate CQL"]
    D --> E["Replicas\nread / write"]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Applications may connect via the Java driver, `cqlsh`, or another client. Even over the same native protocol, **type-rendering capabilities and APIs vary across clients**.

## 3. How to Check Versions from the Right Perspectives

### 3.1. Check the Responding Server Node

In `cqlsh`, you can query the connected local node's metadata:

~~~cql
SELECT release_version, cql_version, native_protocol_version
FROM system.local;
~~~

Interpretation:

- `release_version`: Cassandra release version of **the queried node**.
- `cql_version`: CQL specification version advertised by that node.
- `native_protocol_version`: native protocol version advertised by that node, **not necessarily the exact protocol used by every driver**.

Distinguish **single-node info** from **cluster-wide state**. During a rolling upgrade, nodes can run mixed versions. Inspect node metadata/health across the cluster with operational tools and test against the coordinators your application actually connects to.

**Never conclude** that because one node reports a newer version, the whole cluster is ready for a new feature. A feature may require compatible schemas, fully built indexes, enabled config flags, and every participating node supporting it.

### 3.2. Check the Actually Negotiated Native Protocol Version

At connection setup, client and server exchange protocol capabilities. Depending on the client, this involves `OPTIONS / SUPPORTED`, `STARTUP`, `READY`, and authentication steps. The driver picks a version **both sides support** and manages host connections.

Inspect driver startup/config logs and the negotiated protocol reported at runtime. Do not just read the library's documentation: the driver's **maximum supported** protocol can differ from the **actual negotiated** protocol when talking to an older server.

### 3.3. Check the Driver Version and Codec Dependencies

In a Java application, explicitly verify:

- The actual Cassandra Java driver JAR version packaged in the runtime artifact.
- Which major API is used: e.g., driver 4.x's `com.datastax.oss.driver.api` namespace, distinct from driver 3.x.
- Codecs matching every CQL type read/written: `uuid`, `timestamp`, collections, UDTs, tuples, or newer types.
- Whether the library supports the target native protocol and deployed Cassandra topology.

A project can compile against a newer driver while deployment bundles an older dependency; always verify **effective runtime dependencies**, not just intended versions in build files.

## 4. Feature Matrix: What Must Each Layer Satisfy?

The table below is a **verification framework**, not a promise that all Cassandra versions share identical features. Always cross-check documentation for your exact **server release, distribution, and driver**.

| Feature Group | Server Requirement | Native Protocol Requirement | Driver Requirement |
|---|---|---|---|
| `SELECT` by partition key, `INSERT`, `UPDATE` | Grammar, schema, partition routing, and query rules | Transports CQL text, parameters, and results | Sends statements, binds typed keys, reads rows |
| `USING TTL`, `USING TIMESTAMP` | Server parser and TTL/timestamp semantics | Transports CQL and bound values | Binds numeric parameters and respects write semantics |
| `IF NOT EXISTS`, `UPDATE ... IF` (LWT) | Server conditional updates and Paxos support | Transports request/result, returns `[applied]` row | Reads `[applied]` and sets regular/serial consistency |
| Collections/UDTs/tuples | Server support for corresponding types and schemas | Represents type metadata and encoded values | Codecs mapping CQL <-> Java |
| `SELECT JSON` / `INSERT ... JSON` | Server CQL JSON parsing/serialization support | Transports query/results as data | Can execute raw CQL and read JSON strings/results |
| Prepared statements | Server `PREPARE`, metadata caching, `EXECUTE` | Prepare/execute frames, IDs, bound values, `UNPREPARED` errors | Prepares/caches/reprepares and binds matching types |
| Paging | Server page generation and paging state | Carries flags and paging state across requests/responses | Paging API and next-page fetching |
| **UNSET** value in bindings | Server semantics for "skip updating this parameter" | Requires UNSET encoding supported by protocol (v4+) | Bind/unset API properly distinguishing NULL from UNSET |
| Advanced indexes/SAI, vector/ANN | Depends on version/distribution, index config, and supported query types | Must express protocol-supported types and metadata | Query API, new type codecs, and decoding strategies |

**Note:** some features depend mainly on **server-side CQL** (e.g., `USING TTL`); others clearly involve **wire format and codecs** (e.g., new typed values); still others require **both server version and index/config state** (e.g., vector search). Never build a blanket rule like "this statement needs protocol vN" without checking version-specific docs.

## 5. Practical Tests Across Each Layer

### 5.1. Features Driven by Server Syntax: TTL and Conditional Writes

Create an illustrative table routed properly by partition key:

~~~cql
CREATE TABLE event_by_account (
    account_id uuid,
    event_id uuid,
    state text,
    tags set<text>,
    PRIMARY KEY ((account_id), event_id)
);
~~~

Write an event with a 10-minute lifetime:

~~~cql
INSERT INTO event_by_account
    (account_id, event_id, state, tags)
VALUES
    (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
     11111111-1111-1111-1111-111111111111,
     'NEW',
     {'mobile', 'created'})
USING TTL 600;
~~~

TTL is **enforced and stored server-side with the mutation**; the native protocol carries the query and values. Even if a driver lacked a dedicated builder method for TTL, the application could still send **raw CQL** through the driver as long as the server understands the syntax.

Test LWT on the exact primary key:

~~~cql
UPDATE event_by_account
SET state = 'PROCESSING'
WHERE account_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND event_id = 11111111-1111-1111-1111-111111111111
IF state = 'NEW';
~~~

The result contains an `[applied]` column. The driver must **read that column** and distinguish `true` from `false`; executing without an exception **does not mean** the condition succeeded.

Both examples show that **syntax and semantics live on the server**. The protocol/driver must transmit requests and responses faithfully, yet they do not evaluate CQL predicates.

### 5.2. Features Tied to Encoding: NULL and UNSET

With prepared statements, distinguish:

- **Bind a value**: updates or supplies that value.
- **Bind NULL**: normally represents null in a CQL mutation; for regular columns, writing null creates deletion/tombstone semantics.
- **Bind UNSET**: instructs the server to **skip updating that parameter**, rather than treating it as writing NULL.

Native protocol **v4 and above** defines wire encoding for UNSET in bound values; the driver must expose an API to leave parameters unset without coercing UNSET to NULL. This clearly illustrates a feature spanning **both server behavior and the wire protocol**.

Scenario: an application handles a PATCH request where `display_name` is absent from the JSON, meaning **keep the existing column intact**, whereas explicitly clearing the name requires an intentional mutation. If the driver mistakes "not provided" for "bind null," existing data gets deleted unintentionally.

**Do not use UNSET to bypass query design:** Cassandra still requires all primary key components where mandatory; UNSET does not turn a prepared statement into an arbitrary multi-key update mechanism.

### 5.3. Features Tied to Data Types: Collections, UDTs, and Vectors

A `set<text>` column in `event_by_account` requires the driver to provide a codec converting between a Java `Set` and CQL wire encoding. `map`, `list`, `tuple`, and **user-defined types (UDTs)** carry corresponding codec/metadata requirements.

Newer Cassandra releases, such as the **5.x** line, introduce features like **the `vector` type and approximate nearest neighbor (ANN) search**. Before adopting them, check:

1. Do **all involved server nodes** support the intended CQL type and query?
2. Are index creation syntax, index types, and index build status satisfied?
3. Can the negotiated protocol carry the corresponding **metadata and values**?
4. Does the current driver bundle read/write codecs for the new type, or is a driver upgrade or custom codec needed?

A driver can **send DDL as raw CQL** even without a dedicated Java API for a feature. Yet if it subsequently cannot **decode returned values**, the application does not truly support the feature end-to-end.

### 5.4. Protocol-Supported Features: Prepared Statements and Paging

High-level prepared statement flow:

~~~mermaid
sequenceDiagram
    participant J as Java application
    participant D as Java driver
    participant S as Cassandra coordinator
    J->>D: prepare(CQL with ?)
    D->>S: PREPARE
    S-->>D: Prepared ID + parameter metadata
    J->>D: bind(values)
    D->>S: EXECUTE + ID + encoded values
    S-->>D: RESULT or ERROR
    D-->>J: Row / exception
~~~

The driver normally manages preparation caching across nodes. If a server forgets a prepared ID, it returns an `UNPREPARED` error; compliant drivers can transparently re-prepare depending on execution flow. **Never treat a prepare error alone as proof that a CQL feature is unsupported by the server.**

With paging, the server returns a **paging state** to resume the query. The driver can automatically fetch subsequent pages as the app iterates results, yet **page size does not cap total rows returned**. Paging state must be reused strictly within the matching query, bound values, settings, and protocol version; never edit it manually or share tokens across different queries.

## 6. Error Analysis to Pinpoint the Failing Layer

Do not respond to every "unsupported" error by bumping the protocol version. Trace **which layer the command reached**.

| Symptom | First Layer to Inspect | How to Verify |
|---|---|---|
| CQL throws syntax errors even in `cqlsh` | Server / CQL grammar | Check `release_version`, server-specific syntax, minimal CQL reproducer |
| DDL fails only on certain nodes | Heterogeneous cluster, feature gates, coordinators | Per-node version/status, rolling upgrade state, schema agreement |
| Cannot connect; protocol version/handshake error | Native protocol, TLS/auth, driver compatibility | Negotiated version, endpoint config, connection logs |
| CQL runs in `cqlsh`, yet Java fails to bind/read new column | Driver codec/metadata or protocol capability | Actual CQL type, codec/type mapping, runtime driver JARs |
| Prepared statement reports `UNPREPARED` | Prepare/cache/host/schema lifecycle | Reprepare behavior, schema changes, target pool/host |
| Using LWT, yet Java treats conflicts as success | Application result handling | Inspect `[applied]` column and handle `false` |
| Paging repeats/skips rows when passing state manually | Paging/query API and mutating data | Keep query/bound values identical; check paging state handling |
| Query runs very slowly or demands `ALLOW FILTERING` | Table/index design and CQL constraints | Check partition key, clustering order, indexes, predicates |

An exception surfaced by the driver **does not necessarily originate in the driver**. The driver often forwards an `ERROR` frame returned by the server—for example, syntax errors, invalid schema, insufficient replicas for consistency, or timeouts. Record **error type, message, statement, host, and involved versions** before concluding.

### Three Scenarios to Distinguish

**Scenario A — Server lacks the feature:** the Java driver sends a new CQL statement; the coordinator parses it and returns a syntax/invalid error. Changing the driver without upgrading servers/config will not fix it.

**Scenario B — Driver lacks the codec:** the server accepts the schema and another client can even read the data, yet the Java driver fails to decode the new column type. You need a compatible codec/driver; rewriting CQL may not be enough.

**Scenario C — Protocol incompatibility:** the client fails handshake or the active protocol version cannot encode required values/metadata. Identify a protocol version **supported by both ends**, then align driver/server versions; forcing a newer protocol against an older server breaks connectivity.

## 7. Java Driver 4.x Example: Tracing from Connection to Result

The example below uses **DataStax Java Driver 4.x** (`com.datastax.oss.driver.api` namespace). Assume `CqlSession session` is initialized with appropriate contact points, local datacenter, authentication, and keyspace, and `event_by_account` already exists.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Set;
import java.util.UUID;

// Example inside a method receiving CqlSession session.
// Prepare once and reuse across service calls.
PreparedStatement insert = session.prepare(
    "INSERT INTO event_by_account " +
    "(account_id, event_id, state, tags) " +
    "VALUES (?, ?, ?, ?) USING TTL ?"
);

UUID accountId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
);
UUID eventId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111"
);

BoundStatement mutation = insert.bind(
        accountId, eventId, "NEW", Set.of("mobile", "created"), 600)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(mutation);

// Verify typed result; driver must decode uuid, text, and set<text>.
PreparedStatement select = session.prepare(
    "SELECT event_id, state, tags FROM event_by_account " +
    "WHERE account_id = ?"
);

BoundStatement query = select.bind(accountId)
    .setPageSize(100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

ResultSet rows = session.execute(query);
for (Row row : rows) {
    UUID returnedId = row.getUuid("event_id");
    String state = row.getString("state");
    Set<String> tags = row.getSet("tags", String.class);
    // Use values in business logic; avoid logging sensitive data.
}
~~~

This example illustrates **layer alignment**, not a universal compatibility matrix for every Cassandra cluster:

- **Server:** supports the table, TTL, `set<text>`, prepared queries, partitioning, and requested consistency level.
- **Protocol:** carries `PREPARE`, `EXECUTE`, bound values, result metadata, and paging.
- **Driver:** binds `UUID`, `String`, `Set<String>`, and `int`; decodes returned types; applies consistency/paging; and manages connections.

`LOCAL_QUORUM` only succeeds if replication and topology satisfy the required local replica ACKs. Otherwise, availability/consistency errors occur even when **CQL features, protocol, and codecs are all supported**.

### LWT and Two Consistency Levels in Java

When testing LWT features, executing the CQL without checking the outcome is not enough:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement cas = SimpleStatement.builder(
        "UPDATE event_by_account SET state = ? " +
        "WHERE account_id = ? AND event_id = ? IF state = ?")
    .addPositionalValues("PROCESSING", accountId, eventId, "NEW")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

Row outcome = session.execute(cas).one();
if (outcome == null) {
    throw new IllegalStateException("No LWT result returned");
}
boolean applied = outcome.getBoolean("[applied]");
if (!applied) {
    // Conflict: condition did not match; re-read state if needed.
}
~~~

- `LOCAL_QUORUM` is the **regular/write consistency level**.
- `LOCAL_SERIAL` is the **serial consistency level** used by Paxos for LWT.
- With multi-datacenter contention on the same key, choose serial consistency per consensus requirements rather than assuming `LOCAL_SERIAL` guards the entire cluster.
- `[applied] = false` means the condition failed; a **timeout**, by contrast, leaves the outcome uncertain and must be handled separately.

A driver exposing `setSerialConsistencyLevel` does not guarantee every server version supports every `IF` clause or new data type.

## 8. Why Does `cqlsh` Succeed While the Java Application Fails?

This is a useful comparison, provided it is done under **identical conditions**.

Check in order:

1. **Same cluster and matching coordinator?** `cqlsh` may connect directly to an upgraded node, while the driver's load balancing routes queries to an older node.
2. **Same keyspace, schema, and role?** Different roles, keyspace contexts, permissions, or schema propagation states yield different behavior.
3. **Same query text and bound values?** `cqlsh` uses inline literals; Java prepared statements use encoded bindings, which can mismatch types or lack codecs.
4. **Same protocol capabilities?** Two clients can negotiate different protocol versions, affecting UNSET or newer types.
5. **Same consistency, retry policy, and paging?** Timeout behavior, replica counts, page sizes, and latencies can differ.
6. **Are schemas/indexes genuinely ready?** A `CREATE INDEX` returning success does not prove every node finished building the index or that queries are fast yet.

### Minimal Controlled Experiment

To isolate server syntax errors from driver issues:

1. Craft the **smallest CQL statement** reproducing the issue, minimizing new writes.
2. Run it in `cqlsh` against the exact target host/cluster.
3. Send the **exact same CQL as a raw `SimpleStatement`** from Java, if safe and appropriate.
4. If raw CQL succeeds while prepared/bound fails, inspect type metadata, codecs, and bound values.
5. If both are rejected by the server, verify server version, configuration, and syntax before upgrading the driver.
6. Repeat against coordinators running different versions during rolling upgrades.

Never extrapolate results from **one test on a single node** into a cluster-wide guarantee.

## 9. Rolling Out a New CQL Feature Safely

Suppose the engineering team wants to adopt a data type or query feature from a newer Cassandra release and call it from Java.

~~~mermaid
flowchart TD
    A["Identify exact feature / data type"] --> B{"Do all required server nodes support it?"}
    B -->|No| C["Upgrade/standardize servers and finish rolling upgrade"]
    B -->|Yes| D{"Schema, indexes, and config ready?"}
    C --> D
    D -->|No| E["Deploy schema, build indexes, verify"]
    D -->|Yes| F{"Protocol compatible?"}
    E --> F
    F -->|No| G["Select supported protocol/driver version"]
    F -->|Yes| H{"Driver codecs/APIs and integration tests pass?"}
    G --> H
    H -->|No| I["Upgrade driver/codecs or adjust bindings"]
    H -->|Yes| J["Enable feature gradually + monitor"]
    I --> H
~~~

**Recommended steps:**

1. **Compile an exact version inventory:** Cassandra per datacenter/node, distribution type (Apache Cassandra vs. vendor), negotiated native protocol, Java driver, and codecs.
2. **Read the specific feature's requirements:** minimum server version, syntax, types, indexes, and config flags. Never guess from the label "Advanced CQL."
3. **Maintain compatibility during rolling upgrades:** while the cluster is mixed, avoid statements or types understood only by newer nodes until all required nodes are ready.
4. **Test on a representative cluster:** realistic data, partition keys, replication, consistency, and read/write patterns; test both success and failure paths.
5. **Deploy matching driver/codecs:** validate negotiated protocol, prepared statements, decoding, paging, and retries in the real application.
6. **Roll out traffic incrementally:** watch for syntax/invalid errors, codec/protocol errors, timeouts, p95/p99 latency, coordinator/replica load, and index impact.
7. **Plan rollback:** CQL/schema/index changes are harder to roll back than app code; verify whether older drivers/servers can still read new data before enabling broad writes.

**Do not treat `ALLOW FILTERING` or adding an index as a "compatibility fix."** Those govern query design and execution; a syntactically supported feature can still fail load requirements. Cassandra performs best with query-driven tables and reads aligned to partition, clustering, and justified indexes.

## 10. Diagnostic Exercises

### Exercise 1 — Do CQL and Protocol Share Version Numbers?

A node advertises `cql_version = 3.x`, while the driver connects over native protocol v4. Is this a version mismatch?

**Answer hint:** No. CQL version and native protocol version are independent axes. Verify actual compatibility between server and driver rather than expecting matching version numbers.

### Exercise 2 — Server Supports It, Older Driver Fails Reading the New Type

`cqlsh` creates the table and queries the new type fine, yet the Java client fails to decode the column.

**Answer hint:** Inspect **codecs/type metadata**, the actual runtime driver JAR, and the negotiated native protocol. The server accepting CQL only proves server-side support, not that every client can decode the output.

### Exercise 3 — LWT Throws No Exception, Yet Users Never See Updates Applied

The application runs `UPDATE ... IF state = 'NEW'` and reports success because `execute()` threw no exception.

**Answer hint:** You must read `[applied]` from the returned row. `false` is a valid CAS conflict outcome, not a protocol exception.

### Exercise 4 — Enabling a Feature Mid-Rolling Upgrade

One upgraded node handles the new CQL cleanly; an un-upgraded node returns a syntax error.

**Answer hint:** Rollout is premature. Complete server upgrades across all required nodes and verify schema/index/driver readiness before enabling the new syntax widely in applications.

### Exercise 5 — A PATCH Request Erases Data

The Java client omits `display_name` from a request and binds `null` in a prepared `UPDATE`. The value in Cassandra disappears.

**Answer hint:** Distinguish **an omitted field** from **a field explicitly requested to be cleared**. With prepared statements and supported protocol versions, UNSET preserves the column; NULL carries deletion semantics. Inspect driver binding logic to avoid accidental deletes.

## 11. Pre-Production Checklist for CQL Features

- [ ] Know the exact **feature/CQL syntax/type** being adopted and its server version prerequisites.
- [ ] Verified version, distribution, and upgrade state across **all required nodes**.
- [ ] Verified the **actually negotiated** native protocol, not merely the library name.
- [ ] Java driver supports the protocol, bundles **codecs** for all types, and provides the needed binding APIs.
- [ ] Tested CQL with both literals and prepared/bound values under the target keyspace, role, and hosts.
- [ ] If using LWT, code checks `[applied]` and distinguishes CAS conflicts from timeouts.
- [ ] If using paging, tested multi-page reads without mistaking page size for a total row cap.
- [ ] If using indexes/advanced search, verified schema, index builds, and load plans.
- [ ] Monitoring tracks errors across **server, protocol, driver, and query** layers, with a tested rollback plan.

**Conclusion:** **The server determines whether a CQL feature exists and executes; the native protocol determines what requests and results can cross the wire; the driver determines whether the Java application can bind, decode, connect, and use that feature properly.** Only when all three layers align with **topology, replication, configuration, and real query design** is a new CQL feature ready for production.
