# Testing Pagination When Underlying Data Changes

## 1. Scenario: Page One Is Correct, Yet the Traversal May No Longer Reflect One Old Dataset

A Java API reads device event history from **Apache Cassandra**. The table stores events by `device_id` and daily bucket; the UI displays 20 rows per page. A user fetches page 1 at 09:00; meanwhile, an ingestion stream inserts late events, a TTL job expires older records, and an admin updates an event's status. The user clicks **Next** at 09:01.

In a test with 100 immutable rows, pagination works cleanly. Once mutations happen between page fetches, tough questions emerge:

- Does an event inserted **before the position already scanned** show up on later pages?
- Does an event inserted **after that position** change the row count or ordering of the next page?
- Will an event that was just `DELETE`d or TTL-expired still be returned?
- Will a row value shown on page 1 match if re-read later?
- If the network drops before saving the cursor, does retrying the old page duplicate rows?
- If a web client modifies filters/page size while keeping the same paging token, is that still valid?

**Lesson focus:** a `paging state` lets Cassandra and the Java Driver **resume from a query position**—it **does not** turn a sequence of requests into a transactionally isolated snapshot. You must test **API contract correctness**, **the actual guarantees Cassandra provides**, and **visibility of new mutations** under controlled ordering.

This lesson belongs to the **Integration Testing** chapter of module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, supporting mastery of the wide-column model, partition keys, query-driven table design, replicas/coordinators, read/write consistency levels, and Java/CQL connectivity.

**After this lesson, learners will be able to:**

1. Distinguish `LIMIT`, **page size**, **paging state**, API cursors, and keyset/seek pagination.
2. Build fixtures with immutable clustering keys and test full pagination over **static data** first.
3. Deliberately insert/update/delete/TTL-expire rows **between page 1 and page 2** using barriers or deterministic pause points rather than guessing with `Thread.sleep`.
4. Write Java Driver 4.x integration tests using `ResultSet`, `AsyncResultSet`, `PagingState`, and Testcontainers.
5. Design **keyset pagination** on clustering keys with a high-water bound, understanding what the bound does and **does not** guarantee.
6. Separate **required correctness** from **behaviors Cassandra does not promise** under concurrent mutations.
7. Test TTL/tombstones, consistency levels, retries/restarts/cursor security, and multi-bucket queries.
8. Structure single-node and multi-node test matrices, metrics, property-based/concurrency tests, runbooks, and a production checklist.

**Scope:** Examples use Cassandra CQL 4.x, Java Driver 4.x, JUnit 5, and Testcontainers Java. Specific APIs, Testcontainers 1.x/2.x packages, driver settings, and version-specific behavior must be verified via **resolved dependency graph + cluster integration tests**. Never interpret illustrative measurements as production benchmark figures.

## 2. Three Mechanisms Often Conflated as “Pagination”

| Mechanism | Meaning | What It Does **Not** Guarantee |
| --- | --- | --- |
| **CQL `LIMIT 100`** | Caps the logical row count of one statement. | Does not split into 5 pages of 20 rows; does not cap physical cells scanned due to tombstones/SSTable versions. |
| **Driver page size = 20** | Target rows per network page; driver/server may return fewer or more. | Not a hard byte limit and **not the query's total row count**. |
| **Driver paging state** | Opaque token marking the next position for **the exact same statement and bound values**. | Does not provide a database snapshot, backward paging, or O(1) random jump to page 57. |
| **API cursor (app-issued)** | HTTP contract carrying scope, query, expiry, and continuation. | Does not add snapshot consistency by merely wrapping raw paging state. |
| **Keyset/seek cursor** | Stores last clustering key, e.g., `seq > lastSeen`. | Does not freeze live row values or automatically surface late inserts before `lastSeen`. |
| **High-water bound** | Caps upper key, e.g., `seq <= H`. | Not a snapshot: older rows can still be deleted/updated, and late inserts below `H` can still appear. |

### 2.1. `LIMIT` Is Not `OFFSET`

In Cassandra, **`OFFSET 10000` is not a natural CQL pagination mechanism like in relational SQL**. Paging state only moves **forward**; reaching page 10 normally requires the page-9 cursor or linearly scanning/skipping preceding rows.

~~~text
SQL OFFSET mental model (DO NOT apply verbatim to Cassandra):
  page 1: OFFSET 0 LIMIT 20
  page 2: OFFSET 20 LIMIT 20
  ...

Cassandra native paging:
  fixed statement -> page 1 + paging state S1
  same statement + S1 -> page 2 + paging state S2

Keyset:
  WHERE seq > lastSeq AND seq <= highWater LIMIT 20
  => every query seeks by clustering key, no OFFSET needed.
~~~

**Note:** `LIMIT` belongs to one query's statement, whereas `page size` controls how the response streams across network round-trips. Do not arbitrarily alter `LIMIT` while reusing an old paging state.

### 2.2. Java Driver 4.x Sync and Async APIs

~~~mermaid
flowchart TD
    A["CqlSession + BoundStatement"] --> B{"Execution mode"}
    B -->|execute| C["ResultSet"]
    C --> D["Iterate rows; driver auto-fetches next pages as needed"]
    B -->|executeAsync| E["CompletionStage<AsyncResultSet>"]
    E --> F["Iterate currentPage"]
    F --> G{"hasMorePages?"}
    G -->|Yes| H["fetchNextPage + thenCompose"]
    H --> F
    G -->|No| I["End workflow"]
    D --> I
~~~

With the sync API, `ResultSet` fetches subsequent pages automatically as the iterator crosses buffered rows; with the async API, `AsyncResultSet.currentPage()` **holds only the current page**, requiring explicit `fetchNextPage()` calls. The initial `CompletionStage` completing for page 1 **does not mean** the full query has been read.

## 3. Define the Test Contract Before Writing Assertions

If the product leaves “what does next page mean when data changes?” undefined, tests can either **flag non-existent bugs** or **bless real data loss**.

### 3.1. Four Common Contracts

| Contract | Description | Appropriate Testing Approach |
| --- | --- | --- |
| **A. Static traversal** | Nobody modifies the table during the entire scan. | Exact ordered IDs, row count, zero duplicates/omissions, all pages read. |
| **B. Live feed** | Later pages may reflect mutations occurring prior to their fetch. | Never promise an immutable old set; check scope, order, cursors, tenant isolation, and bounded resources. |
| **C. Fixed-range traversal** | Pick `highWater=H`; accept only keys `<=H` and `>last`. | Never exceed `H`, keys strictly advance, no revisiting prior keys; **never** assume every row at t0 still exists. |
| **D. Exact t0 snapshot** | Every page returns the exact dataset as of one timestamp. | Requires a **snapshot/versioned materialized view** or historical architecture. Paging state + `QUORUM` is **insufficient**. |

An admin UI might accept B; a daily export job might require C; legal/reconciliation workflows might require D. **Never write “snapshot-consistent” in API docs merely because page size or CL was pinned.**

### 3.2. Invariants to Verify

Suppose a query reads **one daily partition** with ascending clustering key `seq`:

1. Every returned row belongs to the authorized `device_id`, `event_day`, and `seq` range.
2. Within **one response**, keys follow CQL order; with keyset `seq > last`, consecutive pages advance monotonically.
3. Never expose `payload`/sensitive columns outside authorization scope, even if cursors are tampered with.
4. Never return 200 “finished” while pages remain if the caller requested full traversal.
5. Never fetch beyond contracted page, byte, deadline, or partition budgets.
6. **Exact equality with a t0 baseline** is valid only when data is static or backed by a true snapshot.

### 3.3. “No Snapshot Guarantee” Does Not Mean Every Run Fails

In one run, page 2 **might** happen to match t0; in another, intervening inserts/deletes alter row counts or values. Good tests **do not rely on lucky timing across runs**; they prove which contract the API actually enforces and analyze conditional changes explicitly.

## 4. CQL Fixture: Table by Device and Daily Bucket

For clarity, examples use clustering key **`seq bigint`**, assumed to be **uniquely, stably, and immutably** assigned upstream per `(device_id, event_day)`. Cassandra **does not auto-generate sequential IDs**; this is a fixture/app model assumption—never use Cassandra counters for global transactional sequencing without proper design.

### 4.1. Single-Node DDL for Testcontainers

~~~sql
CREATE KEYSPACE IF NOT EXISTS paging_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
};

CREATE TABLE IF NOT EXISTS paging_lab.events_by_device_day (
  device_id text,
  event_day date,
  seq bigint,
  event_id uuid,
  event_time timestamp,
  status text,
  payload text,
  updated_at timestamp,
  PRIMARY KEY ((device_id, event_day), seq)
) WITH CLUSTERING ORDER BY (seq ASC);
~~~

**Key distinctions:**

- `(device_id, event_day)` is the **partition key**. Cassandra hashes it to pick tokens and natural replicas; querying one day of one device is a cleanly scoped read path.
- `seq` is the sole **clustering key**, ordered **`ASC`** inside the partition. Thus `seq > last` and `seq <= highWater` are natural CQL predicates on this fixture.
- `event_time` is a regular column here. If a real API needs time-range queries, make `event_time`/tie-breaker the clustering key and build the corresponding tuple keyset—**never assume time-range queries are optimal when time is a regular column**.
- `status`/`payload` can be `UPDATE`d without changing the primary key; `DELETE` and TTL create tombstones.
- **Single-node** Testcontainers uses RF 1/`LOCAL_ONE` to test client/paging behavior—it **does not** prove quorum, read repair, replica failures, or multi-DC.

### 4.2. DDL for a Three-Replica Test Cluster

~~~sql
-- Only for a test cluster with three full replicas in dc1.
CREATE KEYSPACE IF NOT EXISTS paging_lab_ha
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Create the same table above under keyspace paging_lab_ha
-- via a versioned DDL test pipeline; never auto-copy into prod.
~~~

With RF = 3, `LOCAL_QUORUM` requires two replicas in local DC `dc1`. `LOCAL_QUORUM` governs consistency per individual read/write, **without creating a multi-page snapshot**. A passing RF = 1 test never proves node-failure tolerance.

### 4.3. Seeding Keys with Intentional Gaps

~~~sql
-- Example records; the Java test will insert all 12 rows.
INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',10,
  123e4567-e89b-42d3-a456-426614174010,
  '2026-11-21T09:00:10Z','NEW','p10','2026-11-21T09:00:10Z');

INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',20,
  123e4567-e89b-42d3-a456-426614174020,
  '2026-11-21T09:00:20Z','NEW','p20','2026-11-21T09:00:20Z');

INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-7','2026-11-21',30,
  123e4567-e89b-42d3-a456-426614174030,
  '2026-11-21T09:00:30Z','NEW','p30','2026-11-21T09:00:30Z');
~~~

Before testing mutations, seed **12 keys**: `10,20,30,...,120`. Gaps between keys allow inserting `35` or `lastSeq+5` between pages without mutating existing clustering keys. Each test must use a **unique partition ID** or isolated cluster reset so tests never share state.

## 5. Mutation Map Between Two Page Fetches

~~~mermaid
sequenceDiagram
    participant Reader as Java Reader
    participant Coordinator as Cassandra coordinator
    participant Writer as Ingestion / admin
    Reader->>Coordinator: SELECT partition seq 10..120, page-size=3
    Coordinator-->>Reader: Page 1: 10,20,30 + S1
    Note over Reader: Paused at test barrier after page 1
    Writer->>Coordinator: INSERT seq=35 and seq=130
    Writer->>Coordinator: UPDATE status seq=80
    Writer->>Coordinator: DELETE seq=60
    Coordinator-->>Writer: Mutation ACKs at CL
    Reader->>Coordinator: Fetch page 2 from S1
    Coordinator-->>Reader: Next page per current CQL/replica state
    Note over Reader,Coordinator: Not an immutable snapshot of t0
~~~

### 5.1. Calibrated Expectations Table

| Mutation After Page 1 | With Native Paging State | With Keyset `seq > last` + `seq <= H` |
| --- | --- | --- |
| `INSERT seq=35` (past cursor 30, ≤ H=120) | Can affect the next page set; **do not claim one deterministic result across all versions/clusters**. | If visible per CL before the new query, **can/is expected to** appear since `35>30` and `35<=120`. |
| `INSERT seq=5` (before cursor 30) | No snapshot guarantee; never rely on tokens to “go back” before the cursor. | **Will not appear** in subsequent `seq>30` queries; this is by design. |
| `INSERT seq=130` (above H) | May appear in queries lacking an upper bound. | **Excluded** when every page enforces `seq<=120`. |
| `UPDATE status seq=80` | If read post-update, value may reflect new state per CL. | Returns new state in subsequent SELECTs; high-water **does not freeze values**. |
| `DELETE seq=60` | Row may vanish from later pages; never expect exact t0 baseline. | Later queries omit deleted rows once deletion is visible per CL. |
| TTL of `seq=100` expires | Clustering order stays intact, while live row vanishes. | Same; `H` bounds keys, not cell lifetimes. |

**Saying “may” is not dodging assertions:** Cassandra provides no cross-page snapshot. Tests must prove **mutations ran at the exact orchestrated moment, targeted the right partition, and received ACKs**, then assert the invariants of **the chosen contract** rather than inventing a non-existent t0 snapshot.

## 6. Keyset Pagination: Explicit Clustering-Key Cursors

On a table with immutable `seq`, the endpoint can query:

~~~sql
-- First keyset page: lastSeq = 0, H = 120.
SELECT seq, event_id, event_time, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 0
  AND seq <= 120
LIMIT 3;

-- When page 1 returns 10,20,30, next page:
SELECT seq, event_id, event_time, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 30
  AND seq <= 120
LIMIT 3;
~~~

Since CQL partition ordering is `ASC`, the previous page's `lastSeq` bounds the next page. No `OFFSET` is used; every query supplies **the full partition key + bounded clustering range** with a business-sized CQL `LIMIT`.

### 6.1. Reading the High-Water Bound at Traversal Start

~~~sql
SELECT seq
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
ORDER BY seq DESC
LIMIT 1;
~~~

If the highest key is `120`, issue the cursor with `H=120` and hold it constant across all pages. **Never recompute `H` on each page** if the goal is excluding newly arrived sequences above `H`. Still, writes with `seq<=H` that were in-flight when `H` was read can still appear later, and deleted/TTL-expired rows can vanish.

### 6.2. High-Water Is Not a “Snapshot at t0”

~~~text
At t0:
  Existing seqs: [10,20,30,40,50,60,70,80,90,100,110,120]
  H = 120
  Page 1: [10,20,30]

At t1:
  INSERT seq=35, DELETE seq=60, UPDATE seq=80 status=PROCESSED
  INSERT seq=130

Page 2 with WHERE 30<seq<=120:
  seq=35 matches
  seq=60 deleted, no live row
  seq=80 may carry updated status
  seq=130 excluded by H
~~~

Useful for **bounded scrolling**, not immutable audit reports. To export **exact t0 data**, consider **materialized snapshots**, versioned immutable projections, or CDC/event-log pipelines with explicit commit offsets rather than mislabeling cursors as snapshots.

### 6.3. When Timestamps Are the Clustering Key

If a real table is `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, a cursor storing only `event_time` can **drop rows sharing a timestamp**. Store **the full clustering tuple `(event_time, event_id)`** and use CQL tuple comparison matching the table's `ASC`/`DESC` order:

~~~sql
-- Illustrative only for a table with ASC clustering order on both columns:
SELECT event_time, event_id, status
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND (event_time, event_id) > (?, ?)
LIMIT 20;
~~~

In tables with `CLUSTERING ORDER BY event_time DESC` or mixed orderings, adjust the cursor operator and merge logic accordingly. Never use Java `UUID.compareTo` to guess CQL's byte ordering without verification; test **multiple events sharing the same timestamp** and bucket boundaries.

## 7. A Good Test Distinguishes Three Value Sets

~~~text
baseline_at_t0:
  Set of seeded and verified seqs before fetching page 1.

observed_pages:
  Seqs/values the reader actually observed across pages.

final_state_at_t2:
  Independent SELECT after mutations have ACKed.
~~~

- **Static** tests: assert `observed_pages == baseline_at_t0` and exact order.
- **Live native paging** tests: assert scope/query identity, bounds, and proper error classes; log diffs `observed - baseline` and `baseline - observed` for analysis without blindly calling them bugs.
- **Keyset with `H`** tests: assert no `seq>H`, strictly increasing `seq>last`, and zero duplicates across successful pages when clustering keys are immutable; assert `seq=130` was excluded.
- **Never infer from `observed == final_state`** that mutations happened before page 1; `final_state` simply reflects state at test end.

### 7.1. When Can You Assert Exact New Data?

If a test explicitly does:

1. Fetch page 1 and capture `lastSeq`.
2. Execute `INSERT seq=lastSeq+5` and await **ACK**.
3. Run keyset `seq > lastSeq AND seq <= H` on **the same partition** post-ACK.
4. No other writers/TTLs/deletes interfere, with topology-appropriate CL,

then expecting `lastSeq+5` in the result **matches the contract** (provided it fits within bounds). For native paging state, avoid hardcoding identical assertions across all versions without an explicit cross-page snapshot guarantee.

## 8. Setting Up Testcontainers, JUnit 5, and Java Driver 4.x

### 8.1. Pick a Consistent Library Stack

Examples below use **Testcontainers Java 2.0.x** importing `org.testcontainers.cassandra.CassandraContainer`. Testcontainers 1.x uses **different artifacts/packages** (e.g., `org.testcontainers:cassandra` and `org.testcontainers.containers.CassandraContainer`). Never mix 2.x POM coordinates with 1.x imports.

~~~xml
<!-- Maven dependency snippets for Java 17 tests.
     Versions are illustrative lab markers; real projects use BOMs,
     approved patches, and verified dependency graphs. -->
<dependencies>
  <dependency>
    <groupId>com.datastax.oss</groupId>
    <artifactId>java-driver-core</artifactId>
    <version>4.18.1</version>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-cassandra</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Do not treat these exact patches as recommended for every 2026 environment.** Check your repository's dependencies, JDK/Spring Boot BOM compatibility, and security policies. If using Testcontainers 1.x, change both **artifacts and packages** per release line, not just version numbers.

### 8.2. What Single-Node Testcontainers Proves

**Proven:** Java Driver native-protocol connectivity, CQL schemas/mappings, reads/writes/deletes, per-page APIs, cursor reuse, controlled keyset behavior, and error-handling code.

**Unproven:** replica consistency during node outages, RF=3 quorum, topology changes, repair/streaming, multi-DC failover, or behavior while replicas are out of sync. Those require a **multi-node test cluster** or isolated staging environment.

> **Tooling note:** Testcontainers requires a Docker/container runtime in CI. This lesson provides examples only and **does not run Docker/Maven inside the Worker workspace**, as this step authors knowledge content only.

## 9. Java Fixture: Isolated Schema and Data Seeding per Test

Below is a **self-contained JUnit 5 class** for Testcontainers Java 2.0.x matching project docs. Each test uses a unique partition key so tests never contend over shared rows. In practice, place in appropriate packages/imports.

~~~java
// CassandraPagingIT.java — fixture & baseline test section
package example.paging;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.LongStream;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
public class CassandraPagingIT {
    private static final LocalDate DAY = LocalDate.of(2026, 11, 21);
    private static CqlSession session;
    private static PreparedStatement bounded;

    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(DockerImageName.parse("cassandra:4.1.4"));

    @BeforeAll
    static void setup() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();

        // 'datacenter1' is the local DC of this fixture container;
        // if overriding CASSANDRA_DC, update the DDL to match.
        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS paging_lab " +
            "WITH replication = {'class':'NetworkTopologyStrategy'," +
            "'datacenter1':1}");
        session.execute(
            "CREATE TABLE IF NOT EXISTS paging_lab.events_by_device_day (" +
            "device_id text, event_day date, seq bigint, " +
            "event_id uuid, event_time timestamp, status text, " +
            "payload text, updated_at timestamp, " +
            "PRIMARY KEY ((device_id,event_day),seq)) " +
            "WITH CLUSTERING ORDER BY (seq ASC)");

        bounded = session.prepare(
            "SELECT seq,event_id,event_time,status " +
            "FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? " +
            "AND seq>? AND seq<=?");
    }

    @AfterAll
    static void close() {
        if (session != null) session.close();
    }

    static String newDevice() {
        return "test-" + UUID.randomUUID();
    }

    static void seed(String deviceId, int count) {
        PreparedStatement insert = session.prepare(
            "INSERT INTO paging_lab.events_by_device_day " +
            "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
            "VALUES (?,?,?,?,?,?,?,?)");
        for (int i = 1; i <= count; i++) {
            long seq = i * 10L;
            Instant time = Instant.parse("2026-11-21T09:00:00Z")
                .plusSeconds(i);
            session.execute(insert.bind(
                deviceId, DAY, seq, UUID.randomUUID(),
                time, "NEW", "p" + seq, time));
        }
    }

    static BoundStatement query(String device, long after, long highWater) {
        return bounded.bind(device, DAY, after, highWater)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
            .setPageSize(3);
    }

    @Test
    void staticDataMustReadAllRowsExactlyOnce() {
        String device = newDevice();
        seed(device, 12);

        List<Long> actual = new ArrayList<>();
        ResultSet result = session.execute(query(device, 0, 120));
        for (Row row : result) {
            actual.add(row.getLong("seq")); // Sync iterator auto-fetches next pages.
        }

        List<Long> expected = LongStream.rangeClosed(1, 12)
            .map(i -> i * 10L).boxed().toList();
        assertEquals(expected, actual);
        assertEquals(actual.size(), actual.stream().distinct().count());
    }
}
~~~

**To use the snippets in later sections:** add the methods to `CassandraPagingIT` or extract a helper class injecting `CqlSession`. Do not paste multiple `package`/`class` declarations into one Java file. Seeding here uses random row UUIDs with **deterministic clustering keys (`seq`)**, since the tests verify ordering by `seq`, not UUID.

### 9.1. Why Not Share One Partition Across All Tests?

If two tests share `device-7` and `event_day=2026-11-21`, a test inserting `seq=35` can break the baseline test depending on execution order. A fresh Testcontainers startup **does not stop tests within the same class or parallel runs from corrupting each other's fixtures**. Use per-test UUID partition keys, separate keyspaces/schema versions when needed, and avoid full-table `TRUNCATE` in parallel suites.

### 9.2. Consistency Conditions on a Single Node

RF=1 and `LOCAL_ONE` fit client-behavior tests. Once `session.execute(insert)` ACKs, a subsequent read on a single-node test cluster observes the completed mutation assuming no concurrent writes or custom timestamps. Still, **this is not proof of RF=3/`LOCAL_QUORUM` or cluster-wide consistency**.

## 10. Sync Java Driver: Grabbing Paging State and Stopping Cleanly at Page End

Driver 4.x documentation warns that you must **consume the entire current page** before resuming with paging state. If you grab the state after page 1 and read only **half of page 1's rows**, resuming starts at **the beginning of page 2**, silently dropping the unread tail of page 1.

~~~java
// Add method to CassandraPagingIT from Section 9.
import com.datastax.oss.driver.api.core.cql.PagingState;

@Test
void rawPagingStateResumesOnlyAfterFullyConsumedFirstPage() {
    String device = newDevice();
    seed(device, 12);

    BoundStatement statement = query(device, 0, 120);
    ResultSet first = session.execute(statement);
    PagingState next = first.getExecutionInfo().getSafePagingState();

    List<Long> received = new ArrayList<>();
    // Read ONLY ALREADY-LOADED rows of current page; do not trigger next fetch.
    while (first.getAvailableWithoutFetching() > 0) {
        Row row = first.one();
        if (row != null) received.add(row.getLong("seq"));
    }

    assertNotNull(next); // Fixture has more rows than page-size=3.

    BoundStatement resumed = statement.setPagingState(next);
    for (Row row : session.execute(resumed)) {
        received.add(row.getLong("seq"));
    }

    List<Long> expected = LongStream.rangeClosed(1, 12)
        .map(i -> i * 10L).boxed().toList();
    assertEquals(expected, received);
}
~~~

**Explanation:**

- `getExecutionInfo().getSafePagingState()` returns a **safe wrapper** checking compatibility with the query/bound values—not a snapshot guarantee or security signature.
- `getAvailableWithoutFetching()` and `one()` ensure **all buffered rows of the current page are drained** before resuming.
- `statement.setPagingState(next)` reuses **the exact same CQL and bound values**. Changing `device_id`, `event_day`, or range invalidates the old state.
- With **static** data, asserting all 12 exact `seq`s is valid.
- In HTTP APIs, generate the next cursor **only after deciding which rows belong to the current HTTP response**, avoiding gaps between returned rows and the next page.

### 10.1. Never Send Raw Paging State to Browsers as a Trusted ID

The driver's safe wrapper checks statement compatibility, **not a cryptographic MAC**. A raw paging token is not proof the user is authorized to read a partition. Per Driver docs, raw tokens can be manipulated to target other ranges if unvalidated. **Sign/seal cursors at the API layer** and authorize tenant/device access on every request.

## 11. Async Java Driver: Process Each Page Exactly Once

This example demonstrates `AsyncResultSet` and `thenCompose` chaining. It avoids blocking inside callbacks and traverses all fetched pages; blocking on `get()` happens strictly **at the JUnit test boundary**.

~~~java
// Additional helper for CassandraPagingIT.
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

private static CompletionStage<List<Long>> consumePages(
        AsyncResultSet page, List<Long> seen) {
    for (Row row : page.currentPage()) {
        seen.add(row.getLong("seq"));
    }
    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(seen);
    }
    return page.fetchNextPage().thenCompose(
        next -> consumePages(next, seen));
}

@Test
void asyncMustFetchAllPagesForStaticData() throws Exception {
    String device = newDevice();
    seed(device, 12);

    CompletionStage<List<Long>> workflow =
        session.executeAsync(query(device, 0, 120))
            .thenCompose(first -> consumePages(first, new ArrayList<>()));

    // Blocking allowed at JUnit/CLI boundary; never inside callbacks.
    List<Long> actual = workflow.toCompletableFuture()
        .get(10, TimeUnit.SECONDS);

    List<Long> expected = LongStream.rangeClosed(1, 12)
        .map(i -> i * 10L).boxed().toList();
    assertEquals(expected, actual);
}
~~~

**Takeaway:** `executeAsync` completes with **page 1 only**; if `hasMorePages()` is true and `fetchNextPage()` is never called, the code drops data even when Cassandra is completely healthy. Verify this on static data **before** introducing concurrent writers, or a Java pagination bug will be misattributed to concurrent mutations.

### 11.1. Dangerous Bounds of This Helper

`consumePages` accumulates every `seq` into a `List`. Fine for a **12-row** fixture, whereas production needs caps on **rows, bytes, pages, deadlines**, and bounded downstream consumers. Never use this pattern to `SELECT` an entire keyspace or multi-million-row partition, and never spawn unbounded `CompletableFuture`s fetching all pages at once.

### 11.2. Never Call `join()` Inside Completion Callbacks

~~~java
// ANTI-PATTERN: can block driver completion/event-loop threads.
return session.executeAsync(statement).thenApply(page ->
    page.fetchNextPage().toCompletableFuture().join());

// Right approach: compose stages asynchronously.
return session.executeAsync(statement).thenCompose(page ->
    page.hasMorePages()
        ? page.fetchNextPage()
        : CompletableFuture.completedFuture(page));
~~~

These are **two illustrative snippets inside a method**, not standalone files with imports/classes; note the second snippet returns page 2 if present **without keeping page 1**. Process page 1 before chaining to `fetchNextPage()`.

## 12. Injecting Mutations After Page 1: Avoiding Snapshot Assumptions

### 12.1. Pause Strictly Between Two Fetches

In a clean test, you don't need hundreds of threads hoping for a race. Deliberately sequence:

~~~text
T0: Seed keys 10,20,...120
T1: Reader executes SELECT, gets first page, saves safe paging state
T2: Drain exact rows of first page
T3: Writer INSERTs seq=(lastSeen+5), INSERTs seq=130,
    UPDATEs status seq=80, DELETEs seq=60; awaits ACKs
T4: Reader resumes using same statement + paging state
T5: Log observed keys/values, validate live-paging contract
~~~

This provides **deterministic orchestration**, not **deterministic visibility semantics** of paging state across every Cassandra release. Mutation boundaries are controlled; exact visibility can vary with server paging internals and consistency.

### 12.2. Java Test: Mutations ACKed Before Resuming

~~~java
// Add to CassandraPagingIT:
@Test
void pagingStateIsNotAnImmutableSnapshotUnderMutations() {
    String device = newDevice();
    seed(device, 12);
    BoundStatement original = query(device, 0, 120);
    ResultSet first = session.execute(original);
    PagingState state = first.getExecutionInfo().getSafePagingState();
    assertNotNull(state);

    List<Long> observed = new ArrayList<>();
    while (first.getAvailableWithoutFetching() > 0) {
        Row row = first.one();
        if (row != null) observed.add(row.getLong("seq"));
    }
    long last = observed.get(observed.size() - 1);
    // Fixture spaces seqs by 10; page 1 expects fewer than 12 rows.
    assertTrue(last + 5 < 120);

    Instant now = Instant.parse("2026-11-21T10:00:00Z");
    PreparedStatement insert = session.prepare(
        "INSERT INTO paging_lab.events_by_device_day " +
        "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
        "VALUES (?,?,?,?,?,?,?,?)");

    // Mutate after page 1 but before fetching next page.
    session.execute(insert.bind(
        device, DAY, last + 5, UUID.randomUUID(),
        now, "LATE", "late-in-window", now));
    session.execute(insert.bind(
        device, DAY, 130L, UUID.randomUUID(),
        now, "LATE", "beyond-watermark", now));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "UPDATE paging_lab.events_by_device_day " +
            "SET status=? WHERE device_id=? AND event_day=? AND seq=?",
            "PROCESSED", device, DAY, 80L));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "DELETE FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? AND seq=?",
            device, DAY, 60L));

    // Keep exact query/params; state resumes from old position, not a t0 snapshot.
    ResultSet resumed = session.execute(original.setPagingState(state));
    for (Row row : resumed) observed.add(row.getLong("seq"));

    assertFalse(observed.isEmpty());
    assertTrue(observed.stream().allMatch(s -> s > 0 && s <= 120));

    // DO NOT assert exact == [10..120] or require presence/absence of 35/60.
    // Instead log observed results against the app's live-paging contract.
    System.out.println("observed=" + observed);
}
~~~

**Why not `assertEquals(baseline, observed)`?** The test itself mutated data between requests. Paging state **promises no snapshot**, so matching a static baseline tests the wrong contract. This test still proves critical guarantees: the code binds paging state to the matching statement, mutations ACKed on time, and no rows outside `seq<=120` leak through. Native queries without an upper bound need different assertions.

### 12.3. Updating a Regular Column Does Not Change Sort Key

`UPDATE status` on `seq=80` leaves `seq` unchanged; if read **after** the UPDATE, the new payload appears per CL. A UI that saw `status=NEW` on page 1 may observe `status=PROCESSED` on refresh. **Without row versions/snapshots**, tests must never promise immutable field values across pages.

### 12.4. Never “Move” a Clustering Key via UPDATE

In Cassandra, primary keys cannot update in place. “Moving” an event from `seq=40` to `seq=45` requires **`INSERT` new key + `DELETE` old key**—**two separate identities/operations** that can cause gaps or duplicates during pagination, especially without transactional workflows. Write dedicated rekey/late-correction tests with explicit idempotency contracts.

## 13. Keyset Tests Can Assert Exact Outcomes Under Controlled Conditions

Unlike native paging state across pages of one statement, **each keyset page is a fresh CQL query** with `WHERE seq > last`. This supports **crisp contracts**: rows inserted after the cursor within the upper bound appear on subsequent pages; rows inserted before the cursor **intentionally do not reappear**.

### 13.1. Helper Returning One Bounded CQL `LIMIT` Page

~~~java
// Add to CassandraPagingIT from Section 9.
record EventView(long seq, String status) {}

private static List<EventView> seekPage(
        String device, long after, long highWater, int limit) {
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid page limit");
    }

    PreparedStatement seek = session.prepare(
        "SELECT seq,status FROM paging_lab.events_by_device_day " +
        "WHERE device_id=? AND event_day=? " +
        "AND seq>? AND seq<=? LIMIT ?");

    BoundStatement statement = seek.bind(
            device, DAY, after, highWater, limit)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
        .setPageSize(3);

    // LIMIT=limit does not guarantee a single network page.
    List<EventView> output = new ArrayList<>();
    for (Row row : session.execute(statement)) {
        output.add(new EventView(
            row.getLong("seq"), row.getString("status")));
    }
    return output;
}
~~~

**In production**, keep `PreparedStatement` long-lived instead of calling `prepare` per page as in this helper. Even with CQL `LIMIT 3`, `page-size` remains a network paging hint; this helper drains the **bounded** result to collect the exact logical rows per CQL.

### 13.2. Testing Inserts, Deletes, Updates, and Upper-Bound Pinning

~~~java
// Add to CassandraPagingIT.
@Test
void keysetHasDefinedLiveWindowSemantics() {
    String device = newDevice();
    seed(device, 12);
    long highWater = 120L; // Fixed before any mutations.

    List<EventView> first = seekPage(device, 0, highWater, 3);
    assertEquals(List.of(10L, 20L, 30L),
        first.stream().map(EventView::seq).toList());
    long last = first.get(first.size() - 1).seq();

    Instant when = Instant.parse("2026-11-21T10:00:00Z");
    PreparedStatement insert = session.prepare(
        "INSERT INTO paging_lab.events_by_device_day " +
        "(device_id,event_day,seq,event_id,event_time,status,payload,updated_at) " +
        "VALUES (?,?,?,?,?,?,?,?)");

    // One key between old rows and one key beyond the upper bound.
    session.execute(insert.bind(
        device, DAY, 35L, UUID.randomUUID(), when,
        "LATE", "mid-range", when));
    session.execute(insert.bind(
        device, DAY, 130L, UUID.randomUUID(), when,
        "LATE", "outside-upper", when));

    // One key below cursor: intentionally excluded from later pages.
    session.execute(insert.bind(
        device, DAY, 5L, UUID.randomUUID(), when,
        "LATE", "before-cursor", when));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "DELETE FROM paging_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? AND seq=?",
            device, DAY, 60L));
    session.execute(
        com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
            "UPDATE paging_lab.events_by_device_day " +
            "SET status=? WHERE device_id=? AND event_day=? AND seq=?",
            "PROCESSED", device, DAY, 80L));

    List<EventView> all = new ArrayList<>(first);
    while (true) {
        List<EventView> page = seekPage(device, last, highWater, 3);
        if (page.isEmpty()) break;
        assertTrue(page.get(0).seq() > last);
        all.addAll(page);
        last = page.get(page.size() - 1).seq();
    }

    List<Long> actual = all.stream().map(EventView::seq).toList();
    assertEquals(
        List.of(10L,20L,30L,35L,40L,50L,70L,80L,90L,100L,110L,120L),
        actual);
    assertFalse(actual.contains(5L));   // Inserted before cursor.
    assertFalse(actual.contains(60L));  // Deleted after page 1.
    assertFalse(actual.contains(130L)); // Exceeds highWater.
    assertTrue(all.stream().anyMatch(
        e -> e.seq() == 80L && "PROCESSED".equals(e.status())));
}
~~~

**Why can this test assert exact results?** Every mutation **ACKed before the next keyset page**, using a single lab replica, no competing writers/TTLs, immutable `seq`, and `WHERE seq>last AND seq<=120` on every page. It verifies the **app-defined live-keyset contract**, without claiming native paging state produces a snapshot.

### 13.3. A Helpful Caveat on This Test

If `seq` is replaced by millisecond-precision `event_time` and two rows share a timestamp, a timestamp-only cursor drops rows. Include secondary key `event_id` in the **full clustering tuple**. If sort keys are mutable or late arrivals land with `seq<=last`, forward-only seeking **cannot guarantee** seeing every new row. Tests must mirror your late-arrival policy.

### 13.4. Don't Generalize “Zero Duplicates” to Every Situation

Simple keysets with **immutable clustering keys, one partition, forward traversal, no rekeying, and unchanged queries** avoid revisiting prior keys. Still, if an app **replays the same cursor after an HTTP retry and appends both responses**, duplicates happen at the **consumer layer**. True deduplication requires business/idempotency keys, especially if producers can emit one logical event under **two different primary keys**.

## 14. Testing TTL: Disappearing Between Pages Does Not Mean Missing ACKs

TTLs expire cells/rows **by write time and Cassandra rules**, regardless of whether a client already fetched page 1. If `seq=80` expires before its page is read, a non-snapshot scan omits it.

### 14.1. TTL Lab Data

~~~sql
-- New row with 3-second TTL applied to written columns.
INSERT INTO paging_lab.events_by_device_day
 (device_id,event_day,seq,event_id,event_time,status,payload,updated_at)
VALUES
 ('device-ttl','2026-11-21',80,
  123e4567-e89b-42d3-a456-426614174080,
  '2026-11-21T09:01:20Z','EPHEMERAL','short-lived',
  '2026-11-21T09:01:20Z')
USING TTL 3;
~~~

### 14.2. Structuring the Test Without Blind Sleeps

~~~text
1. Seed multiple stable rows besides seq=80.
2. Insert seq=80 with TTL=3 and await ACK.
3. Read page 1 containing seqs < 80.
4. Bounded-poll exact key seq=80 until SELECT returns no live row.
   Abort if past deadline (e.g., 10s); never wait forever.
5. Fetch the page covering the seq=80 range.
6. Under a live contract, never assert seq=80 must still appear as at t0.
7. Observe server tombstones/latency if needed; never confuse TTL with file DROP.
~~~

Here, **waiting until `SELECT` confirms the row expired** synchronizes on real state—far superior to `Thread.sleep(3000)` assuming exact millisecond alignment between TTL and server clocks. Use **Awaitility or bounded polling** on the JUnit thread; never block driver I/O callbacks.

### 14.3. Tombstones and `gc_grace_seconds`

`DELETE`d or TTL-expired rows leave tombstones in SSTables. A `LIMIT 20` query may scan many cell versions and tombstones before gathering 20 live rows. Tests should check **latency, tombstones scanned, SSTable count, and compaction**, rather than assuming small pages always mean low storage cost.

Never lower `gc_grace_seconds` just to make tombstones vanish faster in tests. In multi-replica clusters, purging tombstones before an absent replica is repaired causes **zombie data**.

## 15. Updates and Sort Keys: Assert Values, Not Just Row Counts

Tests checking only `rowCount` per page miss **`status`** changing from `NEW` to `PROCESSED` between fetches.

| Mutation | Identity/Clustering Key | Row Content | What to Assert |
| --- | --- | --- | --- |
| `UPDATE status` | Unchanged | Changed | Verify version/contract allows live updates. |
| `UPDATE payload` | Unchanged | Changed | Verify column projection; never log sensitive payloads. |
| `DELETE` | Row becomes non-live | Absent from reads once deletion is visible | Never require exact t0 baseline unless snapshot. |
| `INSERT` new `seq` | New key | New row | Check position relative to last cursor and `H`. |
| “Change `seq`” via INSERT+DELETE | Identity changes | One logical event may appear under two keys mid-transition | Test dedup, ordering, and reconciliation. |

### 15.1. When an API Requires Immutable Values Across Traversal

Design **immutable event versions** or snapshot materialization:

~~~text
Event v1 status change -> write event v2 / new version

Snapshot manifest at t0:
  snapshot_id = S
  list of row identities + versions, or an immutable projection

Pagination:
  WHERE snapshot_id = S AND seq > lastSeq LIMIT K
~~~

This is **additional architecture**, not an automatic feature of paging state. Manifests/versioned projections require storage policies, TTLs that outlive active cursors, access control, and cost sizing—especially at multi-TB scale.

## 16. HTTP Cursors: Secure, Expiring, and Authorization-Bound

### 16.1. Business-Level Cursor Contents

~~~json
{
  "cursorVersion": 2,
  "queryName": "events_by_device_day_v2",
  "tenantScope": "tenant-a",
  "deviceId": "device-7",
  "eventDay": "2026-11-21",
  "sort": "seq-asc",
  "lastSeq": 30,
  "highWater": 120,
  "pageLimit": 20,
  "expiresAtUtc": "2026-11-21T09:15:00Z"
}
~~~

This illustrates a **JSON keyset cursor before sealing**—**never** return this raw payload to browsers as a trusted token. For native state, cursors also need **opaque paging state, query/parameter digest, driver/schema/cursor version, and page contract**; never use paging state as proof of authorization.

### 16.2. Sealing the Cursor

~~~mermaid
flowchart TD
    A["Server builds cursor payload"] --> B["Canonicalize + encode"]
    B --> C["Sign HMAC with server-held secret/kid"]
    C --> D["Return token + expiry to client"]
    D --> E["Client requests Next"]
    E --> F["Server verifies signature, expiry, version"]
    F --> G["Authorize user/tenant/device and filters"]
    G --> H["Resume via keyset or valid paging state"]
~~~

**Mandatory security rules:**

1. `Base64url` **is not encryption**. If cursors carry sensitive data, use authenticated encryption or return only a **server-side cursor ID** pointing to protected state.
2. `PagingState`'s safe wrapper checks query compatibility, **not tamper-proof MACs**. Sign envelopes with HMAC-SHA256 (or an approved equivalent); store keys in a secret manager with `kid`, rotation, and expiry.
3. Bind tokens to **tenant, user/scope, query name, filters, sort, page size, and keyspace/table version** per contract. Always **re-authorize on every `Next` call**, never trusting page 1's authorization.
4. Reject oversized/tampered/expired tokens with `400` or `410` per contract; never degrade errors into unfiltered `SELECT`s.
5. Never log raw tokens in public logs/traces: they can leak positioning metadata, act as bearer capabilities, or widen scope risks.
6. Cluster/schema/protocol changes can invalidate older cursors. APIs need **cursor versioning**, reasonable lifetimes, and clean restart paths.
7. Replaying the same cursor **creates no snapshot** and can return different data after mutations; idempotent page payloads require server-side version caching or materialized snapshots.

### 16.3. Cursor-Tampering Tests

| Test | Action | Expectation |
| --- | --- | --- |
| Alter `deviceId` in payload | Modify token without signing key. | Signature fails; never touches Cassandra with new scope. |
| Tenant B uses Tenant A's token | Valid signature, wrong caller. | Authorization fails; leaks zero Tenant A rows. |
| Change filter/page size | Reuse old paging state. | Reject or force fresh page 1; never reuse state across statements. |
| Expired token | Request past expiry. | `400`/`410` per contract; never resume blindly. |
| Key `kid` rotated | Old cursor inside grace vs revoked. | Intentional policy; reject invalid signatures. |
| Paste state into another CQL query | Use safe wrapper. | Fail fast / query error; never fall back to unchecked raw tokens. |
| Replay after DB mutation | Resend valid token. | May return updated live state; no idempotent snapshot promised. |

## 17. Paging State Guarantees and Often-Overlooked Limits

### 17.1. Same Query, Same Bound Values

Java Driver 4.x docs confirm paging state must be paired with **the exact same statement (CQL string + bound parameters)**. `getExecutionInfo().getSafePagingState()` adds compatibility checks and `PagingState.fromString(...)` supports serialization, yet **changing one parameter or CQL clause** invalidates the state.

~~~java
// Conceptual snippet after draining the current page:
PagingState saved = result.getExecutionInfo().getSafePagingState();
String encoded = saved.toString(); // Not safe to expose publicly as-is!

PagingState decoded = PagingState.fromString(encoded);
BoundStatement sameQuery = prepared.bind(
    originalDevice, originalDay, originalAfter, originalHighWater);

BoundStatement continued = sameQuery.setPagingState(decoded);
// Server/app must still verify cursor HMAC, tenant scope, expiry, and schema.
~~~

This is an **in-method snippet** assuming `prepared` and parameters are already defined. With custom codecs or simple statements, some APIs require `Session` to validate state; follow your driver version's API.

### 17.2. Never Extract Paging State Before Slicing an HTTP Response Mid-Page

If a network page holds 20 rows and the API returns only 10 while saving paging state for **the next page**, the remaining 10 rows of the first network page **are skipped**. Two fixes:

- Align CQL/paging so **every HTTP response drains the full network page** (without assuming exact page size), or
- Buffer **leftover rows/internal cursor** in bounded-TTL storage, or switch to **keyset cursors using the actual last row returned** instead of raw paging state.

**Rule:** the cursor must point **immediately after the last row actually delivered and acknowledged to the caller**, never past buffered rows the app never returned.

### 17.3. Never Share Paging State Across Different Partitions

When switching from `device-7, 2026-11-21` to `device-8, 2026-11-21`, issue a **new query and new cursor**. Reusing raw state while swapping the bound `device_id` is both **semantically broken** and a security vulnerability.

## 18. Testing Concurrency with Latches/Barriers Instead of Guessing Timings

A test claiming “writer runs concurrently with reader” flakes whenever the writer finishes **before page 1**, **between pages**, or **after the full scan**. To guarantee mutations land **after page 1 and before page 2**, orchestrate them explicitly.

### 18.1. Observable Milestones

~~~text
reader-thread:
  execute SELECT -> receive page 1 -> drain page 1
  firstPageReady.countDown()
  writerFinished.await()
  fetch page 2 -> finish

writer-thread:
  firstPageReady.await()
  execute mutations, await write ACKs
  writerFinished.countDown()

test-thread:
  await both, assert test contract, save trace on failure
~~~

Here, **`CountDownLatch` proves execution ordering inside the test process**, while Cassandra write ACKs/CL confirm mutation state. Neither creates a server-side snapshot.

### 18.2. JUnit Java Sample with Explicit Pause Points

~~~java
// Add to CassandraPagingIT (extra imports shown below).
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void mutationHappensStrictlyBetweenPageOneAndTwo() throws Exception {
    String device = newDevice();
    seed(device, 12);
    CountDownLatch firstPageReady = new CountDownLatch(1);
    CountDownLatch writerFinished = new CountDownLatch(1);
    ExecutorService executor = Executors.newSingleThreadExecutor();

    try {
        Future<List<Long>> scan = executor.submit(() -> {
            BoundStatement stmt = query(device, 0, 120);
            ResultSet first = session.execute(stmt);
            PagingState state = first.getExecutionInfo().getSafePagingState();
            if (state == null) {
                throw new IllegalStateException(
                    "Test expected multiple server pages");
            }

            List<Long> rows = new ArrayList<>();
            while (first.getAvailableWithoutFetching() > 0) {
                Row r = first.one();
                if (r != null) rows.add(r.getLong("seq"));
            }

            firstPageReady.countDown();
            if (!writerFinished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Writer did not finish");
            }
            for (Row r : session.execute(stmt.setPagingState(state))) {
                rows.add(r.getLong("seq"));
            }
            return rows;
        });

        assertTrue(firstPageReady.await(10, TimeUnit.SECONDS));
        try {
            session.execute(
                com.datastax.oss.driver.api.core.cql.SimpleStatement.newInstance(
                    "DELETE FROM paging_lab.events_by_device_day " +
                    "WHERE device_id=? AND event_day=? AND seq=?",
                    device, DAY, 80L));
        } finally {
            // Even if mutation fails, do not block reader forever.
            writerFinished.countDown();
        }

        List<Long> observed = scan.get(10, TimeUnit.SECONDS);
        assertTrue(observed.stream().allMatch(s -> s > 0 && s <= 120));
        // Do not assert an exact static baseline under mutations.
    } finally {
        writerFinished.countDown();
        executor.shutdownNow();
    }
}
~~~

**Notes on this test:**

- The reader thread blocks on the latch inside a JUnit worker thread; never use this blocking pattern inside **driver I/O callbacks** in production.
- If an error occurs before `firstPageReady.countDown()`, the test fails within the bounded timeout logging the cause; you can refine it with `CompletableFuture` error propagation to fail faster in CI.
- `shutdownNow()` only stops the test executor; it **cannot cancel queries already sent to Cassandra**.
- Uses an **isolated key/partition**; the same `CqlSession` safely handles concurrent reads and writes.
- Use this test to verify **orchestration and absence of deadlocks**, without assuming deletes retroactively erase rows already returned on page 1.

### 18.3. Barriers for Two Writers and One Reader

A more realistic workload:

~~~text
writerA: INSERT new key past cursor
writerB: DELETE or UPDATE key about to be read
reader : fetch page after both writers ACK
~~~

To force a specific order, use **separate latches for `writerA` and `writerB`** rather than assuming the JVM schedules two futures in submission order. When **deliberately** letting writers race, assert only valid outcomes (LWT vs unconditional timestamp conflicts)—**never assert one fixed writer always wins**.

## 19. Multiple Partitions/Buckets: One Cassandra Cursor Cannot Drive a Global Feed

In real time-series tables, each day forms a partition `(device_id, event_day)`. An API querying 23:45 on Nov 20 to 00:15 on Nov 21 UTC must read **two partitions**. Cassandra guarantees clustering order **inside each partition**, not a total order across days.

~~~mermaid
flowchart TD
    A["HTTP GET timeline spanning 2 days"] --> B["Nov 20 Partition"]
    A --> C["Nov 21 Partition"]
    B --> D["Rows in per-day clustering order"]
    C --> E["Rows in per-day clustering order"]
    D --> F["Merge in Java by event_time + tie-breaker"]
    E --> F
    F --> G["Top K + cursor storing per-bucket state"]
~~~

### 19.1. What the Cursor Contract Must Include

- **Half-open time interval** `[startInclusive, endExclusive)` in UTC; never substitute server `LocalDate.now()` for UTC event dates.
- List of **buckets to scan**, capping max days/partitions.
- Per bucket: **last clustering tuple** or **dedicated paging state** plus unconsumed buffer state.
- **Global ordering** by event time plus a unique, deterministic tie-breaker to avoid dropping equal-timestamp events.
- High-water, cursor version, deadlines, and retry/fan-out budgets.

### 19.2. Mutations Affecting Merged Results

A **late-arrival** event has yesterday's `event_time` yet arrives today. It may:

- Land in a partition the API already passed → omitted from later pages if the cursor moves forward-only.
- Land in a partition about to be fetched → appear in the live feed.
- Shift the merged global order → require replay/reconciliation if the product guarantees zero missed events.

**Never claim `thenCombine` over two queries produces a shared snapshot.** The two statements can hit different coordinators at different instants, even when both use `LOCAL_QUORUM`.

### 19.3. Dedicated Day-Boundary Tests

| Data | Key/Bucket | Expectation |
| --- | --- | --- |
| `2026-11-20 23:59:59.999Z` | Nov 20 UTC. | Belongs to old bucket when range reaches this boundary. |
| `2026-11-21 00:00:00.000Z` | Nov 21 UTC. | Belongs to new bucket; never double-counted via dual-inclusive endpoints. |
| Two events with identical timestamp | Two distinct IDs. | Cursor/merge must apply a stable tie-breaker. |
| Late insert into an already-scanned day | Old bucket. | Not promised to appear under a forward-only contract. |
| Delete in second bucket after first fetched | New bucket. | Never assume a global snapshot. |

**CQL does not support** scanning two arbitrary daily partitions and applying a global `ORDER BY event_time` like an SQL table scan with a global index. That belongs in data modeling/projections and the service layer.

## 20. Consistency Level: Changing RF/CL Does Not Turn Paging into a Snapshot

### 20.1. Environment Matrix

| Environment | RF / Topology | Reference Read/Write CL | What the Test Proves |
| --- | --- | --- | --- |
| **Single-node Testcontainers** | RF=1 in `datacenter1`. | `LOCAL_ONE`. | CQL/Java Driver/paging, ACKed mutations, cursor API. |
| **Three-full-replica staging** | RF=3 in `dc1`. | `LOCAL_QUORUM`. | Quorum replica counts, reads/writes during slow/down node, timeouts, visibility. |
| **Two-DC staging** | E.g. `dc1:3, dc2:3`. | Per-DC local CL per policy. | Local vs cross-DC routing, replication lag/failover behavior. |
| **Production-like chaos** | Multiple nodes, repair/compaction/network faults. | Per SLO & consistency contract. | Resource/recovery limits; never implies “all pages share one snapshot”. |

### 20.2. What RF=3 with `LOCAL_QUORUM` Requires

In a DC with three full replicas, `LOCAL_QUORUM` awaits two responding replicas per operation. Matching quorum reads/writes on the same partition intersect per quorum theory, yet:

- Two pages are **two requests at different points in time**.
- Replicas can receive new mutations between pages.
- TTLs can expire mid-scan.
- Multi-partition batches/workflows **do not** automatically form a snapshot.
- Tombstones, repair, GC, and system load vary latency.

**Never** downgrade `LOCAL_QUORUM` to `LOCAL_ONE` in tests and cite the pass as production-equivalent proof. Nor should you raise timeouts to “fix” `Unavailable` when replicas are missing.

### 20.3. Testing Replication Lag and Repair

In a multi-node test cluster, run:

1. Baseline partition read recording coordinator, replicas, and CL.
2. Stop one full replica using authorized fault injection.
3. Write/delete/TTL at an achievable CL and track mutation ACKs.
4. Restore the replica and verify reads after convergence/repair per runbook.
5. Measure p99, page counts, tombstones, hints/repair, and server warnings.

Never use a **single RF=1 Testcontainers session** to simulate this by simply calling `setConsistencyLevel(LOCAL_QUORUM)`; real multi-node topology must exist.

## 21. Handling Retries, Timeouts, and “Unknown Page” Errors

### 21.1. Two Opposite Risks

~~~text
Client receives page N, but HTTP response is lost.
  -> Client retries same cursor:
     may re-receive page N -> downstream duplicates.

Server advances paging state before client receives all rows.
  -> Client saves cursor past page N without receiving page N:
     loses entire page N from user's results.
~~~

Both issues arise in the **API delivery/cursor layer**, with zero Cassandra bugs involved. A cursor is a query position, **not an end-to-end consumer ACK**.

### 21.2. Purpose-Fit Retry Policy

| Situation | Handling |
| --- | --- |
| Read timeout on a page | Bounded retry within deadline/budget; if reusing the same cursor, accept that live mutations may alter the page. |
| Connection dropped after server built response | Never assume the page wasn't sent or received; enforce downstream idempotency/dedup. |
| Cursor format changed post-deploy | Check version/expiry; return restart error or run approved cursor migration. |
| `Unauthorized` / scope mismatch | Reject immediately; never retry with higher-privileged credentials. |
| Page size changed from 20 to 200 | Define cursor contract; never tweak options while keeping old state. |
| `Unavailable` for RF/CL | Investigate topology/availability; never silently downgrade CL. |
| TTL just expired | Never retry forever to “recover old rows”; follow live/snapshot contract. |

**Retrying a SELECT** has no write side effects, yet consumes CPU, network, and replica capacity; retry storms worsen degraded clusters. Avoid `while(true)` on driver timeouts—enforce **bounded attempts, exponential backoff + jitter, and a total deadline**.

### 21.3. Cancellation Does Not Roll Back Reads

If a user closes their browser tab after page 1, the service should **avoid fetching page 2**. Still, cancelling a Java `CompletableFuture` or closing HTTP **does not guarantee** the Cassandra coordinator stops an in-flight request. Tests should verify actual fetch counts, release semaphores/connections, and prevent runaway background page fetching.

## 22. Spring Data Cassandra: `Slice` Is Forward Paging, Not a Snapshot

Spring Data Cassandra provides `CassandraPageRequest` and `Slice<T>` for forward navigation matching Cassandra's paging model. Spring Data docs explicitly warn that repositories cannot use traditional SQL offset paging for cheap random jumps.

~~~java
// Snippet inside a Spring Data Repository integration test:
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<EventEntity> first =
    repository.findAll(CassandraPageRequest.first(10));

if (first.hasNext()) {
    Slice<EventEntity> second =
        repository.findAll(first.nextPageable());
    // Validate scope and mutations according to your API contract.
}
~~~

**This illustrates Spring Data paging mechanics**, not a recommendation to call `repository.findAll()` on huge production keyspaces. Use **queries supplying full partition keys and limits**, or `CassandraTemplate.slice(Query, Class)` with proper filters, verifying method signatures against your BOM-pinned Spring Data version.

### 22.1. What to Test When Replacing Driver Core with Spring Data

1. Generated queries bind the **exact full partition key and sort order**.
2. `nextPageable()` preserves **filters, sort, page size, and bound values**.
3. `Slice.hasNext()` and full slice iteration behave cleanly when rows per page vary.
4. Entity mapping does not eagerly load huge unused `payload` columns, spiking GC/p99.
5. Mutations between slices follow **live-view** semantics without promising snapshots.
6. Spring Data and Java Driver versions align via the BOM, and schema drift is checked.

**A `Page<T>` carrying total counts does not fit every Cassandra query**: total counts shift under live mutations, and `COUNT` over wide partitions is expensive. Prefer `Slice`/continuation tokens when the API only needs “is there a next page?”.

## 23. Pre-Release Integration Test Matrix

### 23.1. Static-Data Tests (No Mutations)

| ID | Fixture | Operation | Strong Assertion |
| --- | --- | --- | --- |
| P01 | 0 rows. | Query one partition, page size 3. | Empty result, workflow terminates, no infinite fetch. |
| P02 | 1 row. | Page size 1 or 20. | Returns exact key/value; no spurious next page. |
| P03 | 12 rows, keys 10..120. | Page sizes 1/2/3/5/20. | Identical exact ordered set; zero duplicates/gaps on static data. |
| P04 | 12 rows, `LIMIT 5`. | Page size 2. | At most 5 logical rows total; never confuse `LIMIT` with page size. |
| P05 | Two partitions with distinct `device_id`. | Query one device only. | Zero cross-tenant/device/partition leakage. |
| P06 | Equal timestamps, distinct event IDs. | Keyset on full clustering tuple. | No rows dropped on timestamp ties. |
| P07 | Large row payloads. | Page size 3. | Track bytes/heap/timeouts; never assume 3 rows means tiny payloads. |
| P08 | Partition with many tombstones. | `LIMIT 20`. | Results and p99 bounded per policy; scan warning if threshold breached. |
| P09 | Same statement, safe paging state. | Fetch page 1 then resume. | Full row set returned once page 1 is fully drained. |
| P10 | Swap bound `device_id` with old state. | Resume mismatched statement. | Fail/reject; never read another partition. |

### 23.2. Mutation Tests Between Page 1 and Page 2

| ID | ACKed Mutation Between Pages | Contract / Claim to Prove |
| --- | --- | --- |
| M01 | Insert key **after** last cursor, `<=H`. | New keyset query sees the key once visible; native paging requires no t0 snapshot. |
| M02 | Insert key **before** last cursor. | Forward keyset does not revisit; product handles late arrivals via separate policy. |
| M03 | Insert key **above `H`**. | Keyset blocks via upper bound; unbounded native queries make no such promise. |
| M04 | Update `status` of upcoming row. | New value may appear; immutable views require versioning/snapshots. |
| M05 | Delete upcoming row. | Live paths must not force deleted rows to remain visible. |
| M06 | TTL expires after page 1. | Do not mistake expired row for “driver skipped a page”. |
| M07 | Insert+delete to “rekey”. | Dual identities/gaps possible; requires event dedup/reconciliation. |
| M08 | Retry same cursor after lost HTTP response. | Client/API idempotency/dedup; never treat token as ACK. |
| M09 | Schema/query filter changes mid-pagination. | Cursor invalidated; clear versioning and error contract. |
| M10 | One replica drops before page 2. | Read CL/error/timeout per real topology; never assert static snapshot baseline. |
| M11 | Multi-DC writer in remote DC. | Test replication visibility at local CL without assuming instant sync. |
| M12 | Hot partition. | Bounded in-flight, timeout/backpressure, zero retry storms. |

### 23.3. What Outcomes Count as Definite Bugs?

**Definite API bugs** if:

- Returns rows belonging to a **tenant/partition outside the filter**.
- Drops rows already present in a **received network page** when the response claimed to return that full page.
- Reuses state across a different query bypassing validation/authorization, leaking data.
- Issues thousands of unbounded fetches/requests, violating byte/deadline budgets.
- Treats `hasMorePages()=true` as query completion when the API promised all rows.
- Keyset over immutable clustering keys returns `seq<=last` due to broken query construction.
- On an **immutable dataset**, drops/duplicates keys or diverges from raw CQL output.

**Do not automatically call it a bug** when a later live page **omits a deleted row**, **includes a newly inserted row past the cursor**, or **shows an updated value**. Judge these against **the documented contract**, not an implicit snapshot assumption.

## 24. Property-Based, Fault-Injection, and Stress Tests

### 24.1. Varying Page Sizes on the Same Static Dataset

A solid property test:

~~~text
Given:
  static partition with ordered unique seq [10,20,...,120]

For each pageSize in [1,2,3,5,7,20]:
  read full native-paging query
  assert seenSeq == baseline
  assert duplicate key count == 0
  assert out-of-partition/out-of-range key count == 0

Then:
  ignore exact number of network pages created by driver;
  goal is completeness, ordering, and bounds.
~~~

### 24.2. Reproducible Seeded Random Mutation Schedules

For live-keyset contracts, build an in-memory **reference model** when all ACKs are orchestrated:

~~~text
randomSeed = 20261121
initialKeys = [10,20,...,120]
pageLimit in [1..10]
mutationOperations = [
  insert(seq=35), update(seq=80), delete(seq=60),
  insert(seq=130), insert(seq=5)
]

For every page boundary:
  apply a subset of mutations and await ACKs before next query
  update reference live state
  compute expected keys in (lastSeq, H] with LIMIT K
  compare CQL result against reference (under single-node conditions,
      no unrelated TTLs or replication lag)
~~~

**Always log `randomSeed`, Cassandra/Driver versions, query name, mutation order, page size, `lastSeq`, and `H`** on failure for reproduction. Separate **guaranteed contract tests** from “native paging fuzzing” used solely to hunt anomalies, so CI doesn't turn red over unpromised snapshot behavior.

### 24.3. Fault Injection by Layer

- **Client:** network drop before/after page receipt, `CompletionStage` cancellation, cursor tampering, post-expiry retries, mapping/codec failures.
- **Coordinator:** node restarts, timeouts, dropped messages, driver failover, connection pool saturation.
- **Replica:** slow GC/disk, replica down, read repair/anti-entropy repair handling out-of-sync data.
- **Storage:** heavy tombstones, compaction backlogs, TTL expirations, SSTable growth, disk-full alerts.
- **Schema/deployment:** table/column changes, driver/cluster upgrades, query version and legacy cursor formats.
- **Traffic:** hot partitions, next-page thundering herds, thousands of clients holding long-lived cursors.

Tests stopping nodes or shaping networks must run in **dedicated authorized test clusters** with cleanup, never touching production. Tests verifying post-repair reads must await **repair/convergence post-conditions** rather than guessing with `sleep`.

## 25. Observability: Measuring Both Paging and Storage Paths

### 25.1. From HTTP to SSTables

~~~mermaid
flowchart TD
    A["HTTP NextPage latency, cursor validation"] --> B["Java app in-flight, queue, heap/GC"]
    B --> C["Driver statement/page latency, retries"]
    C --> D["Coordinator pending work, CL/timeouts"]
    D --> E["Replica read path, SSTables/tombstones"]
    E --> F["Compaction, repair, disk IO, network"]
~~~

| Layer | Metrics to Collect | Question Answered |
| --- | --- | --- |
| **API** | Per-page p50/p95/p99, full traversal time, `next_cursor` errors, invalid/expired cursors. | How are users affected? |
| **Pager** | Pages fetched, logical rows returned, bytes decoded, `hasMorePages`, stop reasons. | Are pages under/over-fetched or skipped? |
| **Java** | In-flight futures, queues, heap/direct memory, allocations, GC, threads. | Are callbacks/`collectList` causing memory pressure? |
| **Driver** | Request latency, retries, coordinators, connection pools, throttler rejects/delays, response size if supported. | Is routing, queuing, or networking slow? |
| **Cassandra** | Read latency, tombstones scanned, SSTable counts, `tpstats`, dropped messages, compaction backlog. | Are replicas scanning too many tombstones or disk-bound? |
| **Topology** | RF/CL, DC, node availability, streaming/repair, network RTT. | Is topology causing slow/inconsistent reads? |

**Never average per-node p99s to estimate cluster-wide p99.** Use properly scoped histograms over matching UTC windows; plot client p99 alongside coordinator/replica metrics, traffic rates, and deployment markers on one timeline.

### 25.2. Useful Investigation Commands

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats paging_lab.events_by_device_day
nodetool tablehistograms paging_lab events_by_device_day
~~~

Commands, counters, and histograms vary across Cassandra versions. `nodetool status` showing `UN` reflects node state only—it neither proves cross-page snapshots nor un-hot partitions. Never enable tracing for all queries on an already overloaded cluster; tracing adds overhead and captures potentially sensitive metadata.

### 25.3. Selectively Tracing One `SELECT`

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;
SELECT seq, event_id, status
FROM paging_lab.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND seq > 0 AND seq <= 120
LIMIT 20;
TRACING OFF;
~~~

`CONSISTENCY` and `TRACING` are **`cqlsh`** commands, not CQL sent verbatim by the Java Driver. CQL traces reveal coordinators, replicas, and SSTable scans, yet **do not measure HTTP cursor validation, Java mapping, GC, or consumer ACK waits**. Pair them with Java metrics/tracing.

### 25.4. Keep Partition Keys Out of Metric Labels

Safe bounded labels include `query_name`, `environment`, `local_dc`, `page_path` (native/keyset), `status`, `cursor_version`, and `stop_reason`. **Never attach `device_id`, `tenant_id`, event UUIDs, raw cursors, or payloads** to histogram samples; both cardinality and data-leak risk skyrocket.

## 26. Case Study: “Cassandra Lost 200 Records” — When the Bug Was the HTTP Cursor

**Hypothetical scenario:** an API returns 50 events per page. Driver page size is set to 200 to cut round-trips. The service receives page 1 from `ResultSet` with 200 rows, serializes only **50 rows**, extracts page 1's raw paging state, and returns it as `next` to the browser.

### 26.1. Timeline

~~~text
T0: Cassandra returns network page: rows 1..200, state points to row 201.
T1: Service returns HTTP page 1: rows 1..50 + state pointing to row 201.
T2: Browser clicks Next; server passes that state.
T3: Cassandra resumes from row 201.

Rows 51..200 were never sent to the browser.
Zero DELETEs occurred in this scenario.
~~~

| Observation | Hasty Conclusion | True Root Cause |
| --- | --- | --- |
| 150 rows vanished between two HTTP pages. | “Replicas are out of sync.” | API cursor **skipped the unused tail of the network page**. |
| `nodetool status` shows all `UN`. | “No bug here.” | Cluster membership does not fix Java slicing bugs. |
| Switching `LOCAL_ONE` to `LOCAL_QUORUM` still drops rows. | “Quorum isn't enough.” | Bug stems from HTTP page size ≠ network page size. |
| Raising page size to 1000 drops even more rows. | “Cassandra pagination breaks on large pages.” | Service discards even more unread rows. |

### 26.2. Remediation

1. Reproduce with a **static dataset** larger than driver page size using a full-traversal integration test.
2. Separate HTTP page size from driver network page size; ensure zero buffered rows are discarded.
3. Switch to **keyset cursors anchored on the last actually delivered row**, or buffer leftovers server-side with bounded TTL/limits.
4. Add a **cursor contract test** to CI (50 HTTP rows, 200 driver rows; assert exact ordered IDs).
5. Only after fixing the static bug, layer on live-feed/TTL/late-arrival mutation tests.
6. Handle retry/duplicate semantics on browser network drops; deduplicate by logical event ID.

**Takeaway:** before blaming concurrent mutations, prove pagination works over **immutable** data. Many “missing data” bugs are simply **boundary bugs between network pages and HTTP pages**.

## 27. Common Misconceptions

| Claim | Verdict | Explanation |
| --- | --- | --- |
| “`getSafePagingState()` creates a snapshot.” | **False** | The wrapper validates statement compatibility; it does not freeze data. |
| “`LOCAL_QUORUM` on every page makes the whole scan one transaction.” | **False** | Each page is a separate request at a different instant. |
| “If page 1 has 20 rows, page size always returns exactly 20.” | **False** | Page size is a hint; the server may return fewer or more. |
| “CQL `LIMIT 100` and driver page size 100 are the same setting.” | **False** | `LIMIT` caps total logical rows; page size chunks network responses. |
| “Checking `hasMorePages()` is enough; no need to call `fetchNextPage()`.” | **False** | Async APIs must explicitly fetch subsequent pages. |
| “Iterating sync `ResultSet` auto-fetches next pages.” | **True** | Yet iteration can block, so measure full-traversal duration. |
| “`OFFSET 100000` is Cassandra's optimal way to jump pages.” | **False** | Native CQL paging is forward-only; offsets are not cheap access paths. |
| “Storing only `event_time` in a cursor is always safe on equal timestamps.” | **False** | Requires the full clustering tuple / tie-breaker. |
| “High-water `seq<=H` freezes all row values.” | **False** | Updates, deletes, TTLs, and late inserts below `H` still apply. |
| “An insert with `seq` below the last cursor must appear on later pages.” | **False under forward seek** | `WHERE seq>last` intentionally never goes backward; late arrivals need a separate policy. |
| “Cassandra clustering keys can be `UPDATE`d like regular columns.” | **False** | Changing a key requires writing a new identity and deleting the old one. |
| “Raw paging tokens prove authorization to access another tenant.” | **False** | Tokens do not replace authorization and must be signed/sealed. |
| “Base64 encrypts and hides cursor contents.” | **False** | Base64 is encoding only; use encryption for sensitive fields. |
| “Signing a cursor with HMAC creates a consistent snapshot.” | **False** | HMAC protects authenticity/integrity, never freezing CQL rows. |
| “Replaying the same cursor always returns the exact same page.” | **False** | Live data and TTLs change; idempotent responses require extra caching/snapshots. |
| “`COUNT(*)` gives a scan an immutable total.” | **False** | A point-in-time count does not lock subsequent mutations. |
| “Single-node Testcontainers proves RF=3 failover.” | **False** | Requires a real multi-replica cluster. |
| “Spring Data Cassandra `Slice` always makes jumping to page 1000 cheap.” | **False** | Uses forward paging state, not cheap random offset access. |
| “A static-dataset test dropping rows is a code/driver bug to investigate.” | **True** | When query and data are unchanging, full traversal must be complete per contract. |
| “Not asserting an exact baseline under live mutations means zero testing.” | **False** | Testing invariants, scope, cursors/ACLs, budgets, and mutation ACKs is rigorous. |
| “Enabling TTL and calling `sleep(3000)` is a reliable sync point.” | **False** | Use bounded polling until the row genuinely expires/disappears. |
| “Small pages guarantee replicas scan very few tombstones.” | **False** | `LIMIT`/page size does not eliminate SSTable/tombstone scanning costs. |
| “Retry/timeout failures can duplicate pages at the consumer.” | **True** | Without end-to-end delivery ACKs, deduplication or explicit cursor protocols are required. |
| “Changing query/filters while keeping old raw paging state is harmless.” | **False** | State is tied to statement/values; validate versions and reject mismatched cursors. |

## 28. Practice Exercises with Answers

**Exercise 1.** A partition has 12 rows, `seq` `10..120` in steps of 10, with no writers. Driver page size is 3, and code iterates the entire `ResultSet`. What is the right outcome?

**Answer:** Returns the full ordered sequence `[10,20,30,40,50,60,70,80,90,100,110,120]` with no duplicates or gaps. Do not hard-assert exactly four network pages since page size is a hint.

**Exercise 2.** `executeAsync()` returns an `AsyncResultSet`; `currentPage()` has 3 rows and `hasMorePages()=true`. If the API returns those 3 rows claiming “all data returned”, where is the bug?

**Answer:** A **Java async pagination** bug—missing `fetchNextPage()` and page aggregation. Cassandra never promises page 1 contains the entire query.

**Exercise 3.** An app grabs paging state from a 200-row network page, sends only the first 50 rows to the browser, and uses that state for the next request. Which rows are lost?

**Answer:** The remaining 150 rows (rows 51–200) of that network page; the state already points to **the next network page**, not row 51. Drain/buffer leftovers or use a keyset cursor on the actual last row delivered.

**Exercise 4.** Even with `LOCAL_QUORUM`, why don't two pages form a snapshot?

**Answer:** CL governs replica responses **per individual statement**. Mutations occurring between two statements are visible to the later page; there is no cross-page transaction or snapshot.

**Exercise 5.** Keyset page 1 returns `seq` `10,20,30`, `H=120`. Then `seq=35` is inserted and ACKed; page 2 queries `seq>30 AND seq<=120 LIMIT 3`. Which keys are expected on a single-node fixture with no other writers?

**Answer:** `[35,40,50]`, since 35 falls past the cursor and 40/50 follow. This tests the **live keyset contract**, not native paging snapshots.

**Exercise 6.** Same setup, plus `seq=5` is inserted. Why does the next page exclude 5?

**Answer:** The query filters `seq>30`; skipping late inserts **before the cursor** is the intended forward-only behavior. If business rules cannot drop late data, use another mechanism (CDC, overlap + dedup, or versioned feeds).

**Exercise 7.** If `seq=130` is inserted after locking `H=120`, what must the test assert?

**Answer:** No keyset page ever returns `seq=130`, because every query enforces `seq<=120`. Note this still does not freeze statuses of keys `<=120`.

**Exercise 8.** `seq=60` is `DELETE`d and ACKed between page 1 and page 2. Should a live-paging test require 60 to appear in the results?

**Answer:** **No.** Once the delete is visible per CL before the read, no live row exists. Only snapshots/materialized views promise old state.

**Exercise 9.** Row `seq=80` gets `UPDATE status='PROCESSED'` after page 1. Why is comparing row count alone insufficient?

**Answer:** Identity and count stay identical while column values change. Test **column values**, version/as-of semantics if immutability is required, and mapping/caching.

**Exercise 10.** Does CQL `LIMIT 20` guarantee Cassandra reads only 20 physical cells when the table holds tombstones?

**Answer:** **No.** Cassandra may scan additional SSTables, cell versions, and tombstones before finding 20 live rows. Monitor p99, tombstones, and compaction—not just result sets.

**Exercise 11.** Why is using `Thread.sleep(100)` to land a writer between two pages a poor test?

**Answer:** Scheduling, networking, and GC jitter can push the writer before, during, or after the pages unpredictably. Use **latches/barriers** and wait for mutation ACKs to control test ordering.

**Exercise 12.** Does `PagingState`'s safe wrapper prove User A is authorized to read User B's partition?

**Answer:** **No.** It only checks query/bind compatibility (without a cryptographic MAC). The API must validate signatures, expiry, and tenant authorization on every request.

**Exercise 13.** Why is `Base64url(JSON cursor)` not enough to stop clients from tampering with `deviceId`?

**Answer:** Base64 can be decoded, edited, and re-encoded trivially. Use **HMAC or authenticated encryption** with server-held keys, plus scope and permission checks on every request.

**Exercise 14.** If an HTTP client replays the same cursor after a `DELETE`, must the server return the exact same old page?

**Answer:** **No** under a live-feed contract. A cursor is not a snapshot or response cache. Idempotent responses require snapshots, versioned page caches, or equivalent mechanisms.

**Exercise 15.** An API spans two days while holding only one paging state. Why is that insufficient?

**Answer:** Two days are **two partitions**, each with its own query continuation; global ordering requires merging by `event_time` + tie-breaker while tracking per-bucket state and bounding fan-out.

**Exercise 16.** Is Spring Data `Slice<T>` a cheap `OFFSET`/`COUNT` model for every Cassandra table?

**Answer:** **No.** Spring Data Cassandra uses forward paging state; avoid full-table `findAll()` on large datasets and never assume jumping to arbitrary pages is cheap.

**Exercise 17.** Single-node Testcontainers with RF=1/`LOCAL_ONE` passes. Has it proven RF=3 `LOCAL_QUORUM` survives a node outage with an identical view across pages?

**Answer:** **No.** You need a three-full-replica cluster with dedicated fault injection; even `LOCAL_QUORUM` does not provide a traversal-wide snapshot.

**Exercise 18.** A row has a 3-second TTL; a test runs `sleep(3000)` then asserts the row is gone. How do you improve it?

**Answer:** Use **bounded polling** on the exact key until `SELECT` shows no live row, with clear deadline/interval. Only then fetch the next page, avoiding millisecond reliance on sleeps matching TTL.

**Exercise 19.** A client times out fetching a page and retries, increasing load on Cassandra. Is a retry budget needed?

**Answer:** **Yes.** Retries add load and can observe a changed live view; enforce bounded retries, backoff + jitter, API deadlines, and downstream idempotency/dedup.

**Exercise 20.** A service changes clustering key `seq=40` to `seq=45` via `INSERT`+`DELETE` mid-scan. Why can duplicates/gaps still appear despite a `seq` cursor?

**Answer:** The logical event existed under **two primary keys** during transition. The cursor cannot know they represent the same event; you need immutable logical IDs and dedup/reconciliation, or versioned snapshots.

**Exercise 21.** Native paging state is reused with identical CQL text but a different `device_id`. Valid?

**Answer:** **No.** State is bound to **parameter values** too. Use the safe wrapper to fail fast and validate cursor envelopes/authorization—never bypass checks with blind raw states.

**Exercise 22.** If a live native-paging test cannot assert an exact t0 baseline under mutations, what should it assert to remain valuable?

**Answer:** Assert `filter/partition` scope, upper bounds, resource limits, zero skipped network-page leftovers, cursor identity/security, error contracts, timely writer ACKs, and log observed sets to detect version regressions.

**Exercise 23.** Why save the random seed when fuzzing concurrent mutations?

**Answer:** To reproduce the exact writer/page schedule on failure; without seeds and mutation timelines, flaky runs are nearly impossible to debug. Still separate guaranteed invariants from non-snapshot behavior.

**Exercise 24.** When an API reports missing rows after switching to async, what is the right investigation order?

**Answer:** First test **static data** and `currentPage/hasMorePages/fetchNextPage` handling, plus HTTP cursor/leftovers; only then investigate concurrent mutations, TTL, RF/CL, tombstones, and networking.

## 29. Implementation Checklist and Decision Flowchart

~~~text
QUERY / SCHEMA
[ ] Partition key and clustering range are bounded; no blind ALLOW FILTERING.
[ ] Clustering key/tie-breaker deterministically orders rows and cursors.
[ ] LIMIT, driver page size, byte/page caps, and HTTP page size are distinct.
[ ] Multi-bucket requests cap partitions, fan-out, and enforce global ordering.
[ ] Late inserts, rekeys, TTL, and deletes have explicit contracts—never assumed snapshots.

TEST FIXTURE / ORCHESTRATION
[ ] Tests isolate partitions/keys with reproducible seeds and IDs.
[ ] Static datasets tested first: 0/1/N rows, page sizes 1..N.
[ ] Both sync and async tests drain all pages without blocking callbacks.
[ ] Network page fully consumed before resuming via paging state.
[ ] Writers await ACKs and synchronize via latch/barrier between page 1 and 2.
[ ] Live native tests never assert unpromised snapshots.
[ ] Keyset tests with H explicitly assert inserts before/after the cursor.
[ ] TTL tests use bounded polling instead of blind sleeps and track tombstones/compaction.

CURSOR / API / SECURITY
[ ] Cursors bind query/filter/sort/tenant/page size/version and expiry.
[ ] Safe PagingState is never treated as a cryptographic signature.
[ ] Cursors signed/sealed; token validation and tenant auth run on every request.
[ ] Zero raw tokens, passwords, payloads, or partition IDs leaked in logs/metrics.
[ ] API defines replay/timeout/duplicate handling, HTTP errors, and expiry.
[ ] Never skip leftovers when HTTP page < driver network page.
[ ] Replays are never claimed to be idempotent snapshots on live queries.

TOPOLOGY / RESOURCES
[ ] Single-node Testcontainers used strictly to prove client behavior.
[ ] RF3/LOCAL_QUORUM, node down, repair, and multi-DC tested on dedicated clusters.
[ ] Bounded in-flight, queues, retries, and total API deadlines enforced.
[ ] Client p99/pages/bytes analyzed alongside Cassandra tombstones/disk/GC.
[ ] Never inflate page size/pools/timeouts to mask broken queries/models.

CI / ROLLOUT
[ ] Pin Cassandra, Java Driver, and Testcontainers versions and dependency graphs.
[ ] Schema/driver cursor migration tested across deployments.
[ ] Mutation fuzz seeds archived; flakes classified strictly against contracts.
[ ] Staging load/chaos tests, canary, stop criteria, and rollback defined.
~~~

~~~mermaid
flowchart TD
    A["Need to test Cassandra pagination"] --> B["Choose contract: static/live/high-water/snapshot"]
    B --> C["Design partition key, clustering key, LIMIT, and page size"]
    C --> D["Static fixture test: read every page cleanly"]
    D --> E{"Exact baseline passes?"}
    E -->|No| F["Fix client paging / HTTP cursor / CQL"]
    F --> D
    E -->|Yes| G["Pause after page 1, execute ACKed mutations"]
    G --> H{"Which contract?"}
    H -->|Live native| I["Assert scope, bounds, cursor/ACL; no snapshot claim"]
    H -->|Keyset + H| J["Assert ordering, upper bound, and continuation"]
    H -->|Snapshot| K["Build versioned materialization/CDC snapshot"]
    I --> L["RF/CL, TTL/tombstone, retry/fault tests"]
    J --> L
    K --> L
    L --> M["Load tests, p99/GC/replica health, canary, and rollback"]
~~~

## 30. Official References and Summary

Always cross-check exact APIs and behaviors against your project's versions:

1. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): sync/async paging, page size, paging state, and offset limitations.
2. [Apache Cassandra Java Driver 4.18 — Async programming](https://apache.github.io/cassandra-java-driver/4.18.0/core/async/): `CompletionStage`, `AsyncResultSet`, `fetchNextPage`, and callbacks.
3. [Apache Cassandra Java Driver 4.18.1 — PagingState Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/PagingState.html): safe state, serialization, query/bind matching, and security notes.
4. [Apache Cassandra Java Driver 4.18.1 — ExecutionInfo Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html): raw/safe paging state, trace IDs, warnings, and coordinators.
5. [Spring Data Cassandra — Repositories and paging](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/repositories.html): `CassandraPageRequest`, `Slice`, and forward-only continuation.
6. [Spring Data Cassandra — Template querying](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraTemplate.slice`, CQL, and entity mapping.
7. [Testcontainers Java — Cassandra module](https://java.testcontainers.org/modules/databases/cassandra/): container, contact point, local DC, TLS/auth labs, and 2.x Maven dependencies.
8. [Apache Cassandra — CQL reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `WHERE` clauses, `LIMIT`, TTL, mutation semantics, and key-based access.

**Summary:** testing pagination while Cassandra mutates requires separating **“reached the next page”** from **“reading an immutable data snapshot”**. Java Driver's `PagingState` marks the next position within **the same statement**, `AsyncResultSet` must explicitly fetch each page, and `LOCAL_QUORUM` governs each individual request across replicas—none creates a cross-time snapshot. **Prove your static baseline has zero drops/duplicates first**, inject mutations **between page 1 and page 2 using latches + ACKs**, choose an explicit **live** or **high-water keyset** contract, test TTL/tombstones, late arrivals, and retries, seal/authorize cursors on every request, and run multi-node RF/CL tests in an appropriate environment. **If the business needs an exact dataset as of t0**, build dedicated snapshots or versioned projections—never inflate page size or mislabel paging tokens as “snapshots” to hide that gap.
