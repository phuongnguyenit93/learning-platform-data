# Testing LWT Contention and `[applied]` Outcomes

> **Chapter:** Integration Testing  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Java integration testing must account for partition keys, query-driven table design, replication, consistency levels, CQL, compaction, repair, and how applications receive and interpret errors.  
> **Focus:** Lightweight Transactions (LWT), conditional operations, contending clients, and the **`[applied]`** result column.

## 1. Opening Scenario: Two Requests Trying to Claim the Same Key

Suppose an order service creates an **order reservation** record keyed by business ID. Two requests arrive simultaneously with the same **order_id** from two different workers, and both want to return “created successfully”.

A bug-prone implementation:

~~~text
Worker A: SELECT sees no order
Worker B: SELECT sees no order
Worker A: INSERT order
Worker B: INSERT order
Worker A: reports CREATED
Worker B: reports CREATED
~~~

Even when both SELECTs and both INSERTs use **`LOCAL_QUORUM`**, a *read-then-write* sequence does not become an **atomic compare-and-set**. In Cassandra, when business rules require “create only if not already present”, you can use CQL:

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Cassandra executes an **LWT**, backed by Paxos consensus within the relevant data scope. Clients contending for the same key observe distinct conditional outcomes:

- **`[applied] = true`:** the conditional operation succeeded per the server's response.
- **`[applied] = false`:** the condition was not satisfied at evaluation time; this is neither an exception nor a sign Cassandra “failed”.
- **Exception/timeout:** the client **lacks a reliable conclusion** on whether the operation applied. Never silently coerce this into `false`.

This lesson builds a Java test where **multiple workers start together at a barrier**, verifies the winner count and final row state, and models unknown outcomes.

### Learning Outcomes

After this lesson, you will be able to:

1. Describe **`IF NOT EXISTS`**, **`IF column = value`**, regular CL, and serial CL.
2. Design a **unique-key-per-run** fixture to prevent interference from other tests.
3. Write **JUnit 5 + Java Driver 4.x** integration tests launching concurrent contending clients.
4. Assert within exact bounds: when all outcomes are deterministic, **exactly one `applied=true`** occurs for a new key, and all others return `false`.
5. Test **conditional UPDATEs** using a **revision** column and verify the final state.
6. Distinguish `false`, post-timeout retries, idempotency, and data reconciliation.
7. Scale testing from single-node labs to multi-replica, multi-DC, fault-injection, and load environments.
8. Capture enough evidence to diagnose regressions, flakiness, and business bugs in CI/CD.

> **Scope:** Examples use **Apache Cassandra Java Driver 4.x** (`com.datastax.oss.driver.api` namespace) and JUnit 5. Exact Cassandra/driver/JDK versions, exceptions, and LWT limits must be verified against your target system. Run contention tests on **isolated lab/staging clusters**, never on production data.

## 2. Why Does LWT Need Contention Testing?

A sequential test:

~~~text
INSERT IF NOT EXISTS → [applied]=true
INSERT IF NOT EXISTS → [applied]=false
~~~

proves the conditional statement works **without contention**. It does not prove the application behaves properly when multiple requests launch concurrently. Real-world bugs hide in:

- Java APIs generating a **fresh `order_id` on every retry**, creating multiple logical records.
- Spring Boot instances executing **SELECT → INSERT** instead of LWT.
- One client setting **`LOCAL_SERIAL`** while another uses a different serial policy, despite the domain assuming global invariants.
- Code treating **WriteTimeout/CAS timeout** as failure and retrying without reconciling.
- Repositories/services **sending emails, charging payments, or publishing events** as soon as a future completes without checking **`[applied]`**.
- Tests counting only true/false results while ignoring exceptions or skipping final row checks.
- Submitting 100 tasks to a 4-thread pool so tasks never genuinely contend at the same time.
- Re-running tests with the same static key so every client gets `false`, producing hard-to-diagnose false negatives.

**Integration tests must verify all three layers:** the CQL response, the final persisted state in Cassandra, and the business semantics for winning vs losing clients.

## 3. `[applied]` Semantics: `true`, `false`, and `UNKNOWN`

### 3.1. Decision Table

| Observed Java Outcome | Valid Conclusion | Invalid Conclusion |
|---|---|---|
| Conditional CQL returns **`[applied] = true`** | Condition held and this operation is confirmed applied | Other tables/partitions also updated atomically |
| Conditional CQL returns **`[applied] = false`** | Condition did not hold; **this** conditional operation did not apply | An earlier request from the same client definitely failed to create data |
| **Read/WriteTimeout**, CAS timeout, or network error | Client lacks a final outcome for that attempt | **`[applied] = false`**, or “no replica wrote” |
| **Overloaded/Unavailable** | Capacity or replica availability issue per CL | Safe to retry indefinitely |
| **Driver request timeout/cancel** | Client-side deadline expired or thread was cancelled | Coordinator definitely aborted or rolled back the write |

In `INSERT IF NOT EXISTS`, a `false` response may also include existing row values depending on CQL/driver/server version. Avoid writing tests tightly coupled to **exact returned-column formatting on `false`** without verifying your version. The most reliable indicator of **whether this operation applied** is the **`[applied]`** column.

### 3.2. False After Retry Scenario

~~~mermaid
sequenceDiagram
    participant J as Java client A
    participant C as Cassandra
    J->>C: INSERT IF NOT EXISTS (claim=K, owner=A)
    C-->>C: Condition true, data applied
    C--xJ: Response lost / client timeout
    J->>C: Retry same claim=K
    C-->>J: [applied] = false (K already exists)
    J->>C: SELECT K to reconcile
    C-->>J: K has owner=A
~~~

If client A gets `false` on a subsequent attempt, **it cannot conclude someone else won**. A's own first attempt may have succeeded. The business layer needs an **idempotency key**, owner/request fingerprint, and reconciliation rules to return “already completed by this request” when appropriate.

Conversely, if the row holds **owner=B** with a different fingerprint, that is a genuine contention/conflict. Distinguish the two using business metadata, not just the boolean.

### 3.3. LWT Is Partition-Scoped, Not a Global Multi-Table Transaction

LWT coordinates **conditional mutations within partition bounds** supported by Cassandra. It **does not** create an ACID transaction with rollback across multiple partitions, tables, and external services.

For example:

1. `INSERT IF NOT EXISTS` on **`claim_by_key`** returns `true`.
2. App writes a row to **`events_by_tenant_day`**.
3. App publishes a notification to a message broker.

If step 2 or 3 fails, step 1 is not automatically rolled back. Contention tests must separate **single-key invariants** from **end-to-end contracts**, using outbox patterns, idempotent projections, or reconciliation where needed.

## 4. Regular Consistency vs Serial Consistency in LWT

LWT involves two consistency settings to distinguish:

| Attribute | Purpose | Illustrative Value |
|---|---|---|
| **Regular consistency level** | Commit/acknowledgment level of the operation per request rules | **`LOCAL_QUORUM`** |
| **Serial consistency level** | Scope of Paxos/conditional coordination for statements with **`IF`** | **`LOCAL_SERIAL`** or **`SERIAL`** |

In Java Driver 4.x:

~~~java
BoundStatement statement = prepared.bind(
        tenantId, claimId, "client-A", "CLAIMED", 0)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL);
~~~

**Never confuse** `LOCAL_QUORUM` with serial consistency. A high regular CL **does not turn a SELECT followed by an INSERT into CAS**.

### 4.1. RF = 3 in One Datacenter

With a keyspace at **RF = 3** in **`dc1`**, `LOCAL_QUORUM` typically requires responses from **two of three local replicas**. `LOCAL_SERIAL` coordinates the serial phase within the local DC per Cassandra's LWT rules.

Test preconditions must explicitly record **RF, live node count, snitch/topology/DC, and each statement's CL**. A single-node RF = 1 test verifies APIs/basic conditions, yet **cannot prove behavior under replica failures, quorum, or multi-DC**.

### 4.2. `SERIAL` vs `LOCAL_SERIAL` Across Multiple DCs

- **`SERIAL`** coordinates serial consensus across a wider multi-DC scope.
- **`LOCAL_SERIAL`** restricts the serial phase to the local DC, reducing cross-DC dependency while narrowing coordination scope.
- If **invariants require uniqueness across all datacenters**, never assume `LOCAL_SERIAL` from two different DCs guarantees a single global ordering.
- Never mix `SERIAL` and `LOCAL_SERIAL` across writers maintaining the same invariant without version-specific analysis and testing.
- In single-DC tests, document `LOCAL_SERIAL` usage explicitly; multi-DC tests must drive contention from **both DCs**, not just a single Java client in `dc1`.

**LWT is not free:** Paxos requires multiple round-trips, and contention on the same partition increases latency, CAS contention, timeouts, and resource usage. Never apply LWT to every independent event just “to be safe”.

## 5. Designing the CQL Fixture: One Key, One Contention Point

### 5.1. Keyspace and Replication

On a **three-node lab cluster in `dc1`**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

This is a **hypothetical test configuration**. On single-node Cassandra tests, use lab-appropriate RF and CL and record verification limits. Never alter production replication just to run tests.

### 5.2. Claim Table with Single-Row Partitions

~~~sql
CREATE TABLE IF NOT EXISTS lwt_lab.claim_by_key (
    tenant_id uuid,
    claim_id uuid,
    owner_token text,
    state text,
    revision int,
    PRIMARY KEY ((tenant_id, claim_id))
);
~~~

**Explanation:**

- **`(tenant_id, claim_id)`** is a **composite partition key**. Each logical claim sits in its own partition under the combined key.
- **`owner_token`** identifies the client/request holding the claim; **`state`** holds status; **`revision`** enables CAS updates.
- Each partition contains one row. This keeps each claim's LWT scope crisp and prevents all orders for a tenant from contending on one tenant-wide partition.
- Two INSERTs with the same partition key and different **`owner_token`** contend on the same **`IF NOT EXISTS`** condition.
- Distinct claims map to distinct partitions, enabling tests at varying contention levels and token distributions; never lump all claims into a single LWT batch.

**Cassandra does not alter `PRIMARY KEY` via `ALTER TABLE` like relational databases.** Changing a key from `(tenant_id, claim_id)` to `(tenant_id)` requires a new table, backfilling, and updated queries—not just changing Java annotations over existing data.

### 5.3. Conditional INSERT

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'client-A',
    'CLAIMED',
    0
) IF NOT EXISTS;
~~~

Repeat with the **same key** (or try **`owner_token = 'client-B'`**):

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'client-B',
    'CLAIMED',
    0
) IF NOT EXISTS;
~~~

If the first succeeded with no intervening delete/mutation, the next receives `false` because the claim already exists. **Contention tests** drive multiple clients concurrently, not sequentially like `cqlsh`.

### 5.4. Conditional UPDATE by Revision

Suppose the claim currently has **`revision = 0`**:

~~~sql
UPDATE lwt_lab.claim_by_key
SET state = 'COMMITTED',
    revision = 1,
    owner_token = 'worker-A'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND claim_id = 22222222-2222-4222-8222-222222222222
IF revision = 0;
~~~

When multiple clients concurrently send **`IF revision = 0`** with different `owner_token`s, only one transition from revision 0 to 1 returns **`applied=true`** provided all attempts complete cleanly and no other writer resets revision. The rest return `false`.

**Do not confuse revision with full MVCC:** it is an application-maintained column. Any writer bypassing the condition or updating via different timestamp/config policies breaks the invariant. Every writer touching `revision` must obey the same contract.

## 6. Matrix of Invariants to Verify

| Test | Precondition | Actions | What Must Hold When All Outcomes Are Deterministic |
|---|---|---|---|
| **T1 — create race** | Key absent | N clients concurrently **`INSERT IF NOT EXISTS`** | **Exactly 1 `true`**, N − 1 `false`; final row belongs to winner |
| **T2 — duplicate request** | Key absent | Send once, then resend same owner/fingerprint | First `true`; retry `false` with matching business metadata |
| **T3 — update race** | `revision = 0` | N clients concurrently **`UPDATE ... IF revision = 0`** | **Exactly 1 `true`**, final `revision = 1` and winner's owner |
| **T4 — sequential CAS** | `revision = 0` | CAS 0→1 then CAS 1→2 | Both `true` when ordered; final `revision = 2` |
| **T5 — stale expected revision** | `revision = 2` | `UPDATE IF revision = 1` | `false`; row unchanged by that operation |
| **T6 — different keys** | N fresh keys | Each client claims a distinct key | Each independent key can return `true`; do not count one winner across all keys |
| **T7 — timeout/unknown** | State unknown post-attempt | Timeout mid-flight | Test reports **`UNKNOWN/ERROR`**, never counts as `false` |
| **T8 — multi-DC** | ≥2 DCs, matching RF/serial policy | Writers from both DCs contend on same key | Invariant tested under supported policy, not inferred from single-DC lab |

**The “exactly one true” invariant assumes**: the row initially did not exist, no external client mutated/deleted it, every attempt returned a clean final response, all clients used the same LWT and serial CL scope, and the test did not inject uncounted silent retries.

If any **timeout** or exception occurs, tests must not ambiguously report “0 winners”. Mark the run **`inconclusive`** and reconcile the row alongside logs/metrics.

## 7. JUnit 5 Test: N Clients Concurrently Running `INSERT IF NOT EXISTS`

### 7.1. Prerequisites

Before running:

1. Create the **keyspace and table** from Section 5 on the test cluster.
2. Ensure the driver's **local datacenter** matches the cluster, e.g. **`dc1`**.
3. If using RF = 3 and `LOCAL_QUORUM`, ensure enough healthy replicas exist in `dc1`.
4. Configure **TLS/auth** if required by the environment; omitted in the snippet to focus on LWT.
5. Run with **JUnit Jupiter (JUnit 5)** and **Java Driver 4.x**; Spring Boot is not required to test the core mechanics.
6. Generate **fresh UUIDs** for tenant/claim per test so prior runs never leak state.

Crucially: spawn **N worker threads** and synchronize on a **`CountDownLatch`** barrier so tasks start together. Calling `INSERT` inside a sequential `for` loop is not a real contention test.

### 7.2. Complete Integration Test Code

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.Test;

public class ClaimContentionIT {
    private static final int CONTENDERS = 8;

    private static final class Attempt {
        final String actor;
        final boolean applied;

        Attempt(String actor, boolean applied) {
            this.actor = actor;
            this.applied = applied;
        }
    }

    @Test
    void exactlyOneAppliedWhenClaimingNewKey()
            throws Exception {

        UUID tenantId = UUID.randomUUID();
        UUID claimId = UUID.randomUUID();

        // Test lab: swap contact point/DC and security if needed.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement claim = session.prepare(
                "INSERT INTO lwt_lab.claim_by_key " +
                "(tenant_id, claim_id, owner_token, " +
                "state, revision) VALUES (?, ?, ?, ?, ?) " +
                "IF NOT EXISTS");

            PreparedStatement verify = session.prepare(
                "SELECT owner_token, state, revision " +
                "FROM lwt_lab.claim_by_key " +
                "WHERE tenant_id = ? AND claim_id = ?");

            ExecutorService workers =
                Executors.newFixedThreadPool(CONTENDERS);
            CountDownLatch ready =
                new CountDownLatch(CONTENDERS);
            CountDownLatch start =
                new CountDownLatch(1);
            List<Future<Attempt>> futures =
                new ArrayList<>();

            try {
                for (int i = 0; i < CONTENDERS; i++) {
                    final String actor = "client-" + i;

                    futures.add(workers.submit(() -> {
                        ready.countDown();

                        // Wait together on a single signal to start.
                        if (!start.await(
                                10, TimeUnit.SECONDS)) {
                            throw new TimeoutException(
                                "start barrier timed out");
                        }

                        BoundStatement statement = claim.bind(
                                tenantId, claimId,
                                actor, "CLAIMED", 0)
                            .setConsistencyLevel(
                                DefaultConsistencyLevel
                                    .LOCAL_QUORUM)
                            .setSerialConsistencyLevel(
                                DefaultConsistencyLevel
                                    .LOCAL_SERIAL);

                        Row outcome =
                            session.execute(statement).one();

                        if (outcome == null) {
                            throw new IllegalStateException(
                                "LWT did not return a row");
                        }

                        return new Attempt(
                            actor,
                            outcome.getBoolean("[applied]"));
                    }));
                }

                assertTrue(
                    ready.await(10, TimeUnit.SECONDS),
                    "Not all contenders reached barrier");

                start.countDown();

                int winners = 0;
                String winningActor = null;

                for (Future<Attempt> future : futures) {
                    // Timeout/exception => test FAIL,
                    // never convert into applied=false.
                    Attempt attempt =
                        future.get(30, TimeUnit.SECONDS);
                    if (attempt.applied) {
                        winners++;
                        winningActor = attempt.actor;
                    }
                }

                assertEquals(
                    1, winners,
                    "Exactly one conditional insert should win");

                Row stored = session.execute(
                    verify.bind(tenantId, claimId)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel
                                .LOCAL_QUORUM))
                    .one();

                assertNotNull(stored);
                assertEquals(
                    winningActor,
                    stored.getString("owner_token"));
                assertEquals(
                    "CLAIMED",
                    stored.getString("state"));
                assertEquals(
                    0,
                    stored.getInt("revision"));
            } finally {
                // Release workers even if assertions/attempts fail.
                start.countDown();
                workers.shutdownNow();
            }
        }
    }
}
~~~

### 7.3. Why This Harness Is Valuable

- **N = 8** workers all wait on the **`start`** latch; tasks are released at the same logical moment, creating genuine contention.
- **`CqlSession`** is thread-safe and shared across requests from multiple threads; do not open a new session per contender.
- **`PreparedStatement`** is shared while each worker creates its own **`BoundStatement`** with its `owner_token`. Never share a mutable statement across threads.
- Every request targets **the same `tenantId + claimId`** with **distinct `owner_token`s** to identify the winner. Generating a unique `claimId` per worker would not race on the same key.
- **`getBoolean("[applied]")`** is read only on successful responses. If the server/driver throws, the `Future` fails exceptionally and **`future.get`** fails the test rather than turning it into `false`.
- Counts **exactly one** winner across deterministic results, then reads back at **`LOCAL_QUORUM`** and asserts **`owner_token`, `state`, `revision`**.
- **`shutdownNow()`** in `finally` halts remaining Java tasks, though it cannot cancel mutations already dispatched to Cassandra. Because the test uses an isolated ID, late outcomes never overwrite production data.
- **10/30-second** timeouts are illustrative CI bounds; tune them to your environment, but never use huge timeouts to mask CAS contention or an overloaded cluster.

### 7.4. Why We Do Not Claim “Started at the Exact Same Nanosecond”

**`CountDownLatch`** delivers the start signal to N tasks simultaneously, yet OS thread schedulers, drivers, networks, and coordinators still introduce jitter. What we verify is that **overlapping operations satisfy the LWT invariant**, not that all packets hit the server in the exact same nanosecond.

To verify real contention occurred, record **start timestamps**, **end timestamps**, per-attempt durations, and cluster CAS contention metrics. If attempts end up serialized sequentially, raise contender count or concurrency—**never add arbitrary sleeps to force a particular winner order**.

## 8. Second Test: Multiple Clients Racing on CAS Revision 0 → 1

This test seeds a claim at **`revision = 0`**, then has N workers concurrently attempt to transition it to `revision = 1` with distinct **`owner_token`s**.

### 8.1. Explicit State Setup

Use conditional CQL to seed the initial row:

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (?, ?, 'seed', 'CLAIMED', 0)
IF NOT EXISTS;
~~~

When seeding via the driver, **assert `applied=true`**. If `false`, the key already existed and the precondition is invalid. Always use a fresh UUID per test.

### 8.2. Conditional UPDATE

~~~sql
UPDATE lwt_lab.claim_by_key
SET state = ?,
    revision = ?,
    owner_token = ?
WHERE tenant_id = ?
  AND claim_id = ?
IF revision = ?;
~~~

Each contender binds **`state = COMMITTED`**, **new `revision = 1`**, its own **`owner_token`**, the shared key, and **`expected revision = 0`**.

**Expected invariant:** when all attempts return cleanly, exactly one returns `true` and the rest `false`; the final row has **`revision = 1`** and the winner's **`owner_token`**.

### 8.3. Extended Test Method

This is a JUnit method placed inside a test class with the same imports and lifecycle as Section 7:

~~~java
@Test
void exactlyOneCasUpdateWins() throws Exception {
    UUID tenantId = UUID.randomUUID();
    UUID claimId = UUID.randomUUID();
    int contenders = 8;

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement seed = session.prepare(
            "INSERT INTO lwt_lab.claim_by_key " +
            "(tenant_id, claim_id, owner_token, state, revision) " +
            "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");

        Row seeded = session.execute(seed
            .bind(tenantId, claimId, "seed", "CLAIMED", 0)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL))
            .one();

        assertNotNull(seeded);
        assertTrue(seeded.getBoolean("[applied]"));

        PreparedStatement cas = session.prepare(
            "UPDATE lwt_lab.claim_by_key " +
            "SET state = ?, revision = ?, owner_token = ? " +
            "WHERE tenant_id = ? AND claim_id = ? " +
            "IF revision = ?");

        PreparedStatement verify = session.prepare(
            "SELECT owner_token, state, revision " +
            "FROM lwt_lab.claim_by_key " +
            "WHERE tenant_id = ? AND claim_id = ?");

        ExecutorService pool =
            Executors.newFixedThreadPool(contenders);
        CountDownLatch ready =
            new CountDownLatch(contenders);
        CountDownLatch start =
            new CountDownLatch(1);
        List<Future<Attempt>> results =
            new ArrayList<>();

        try {
            for (int i = 0; i < contenders; i++) {
                final String owner = "updater-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("barrier timeout");
                    }

                    BoundStatement update = cas.bind(
                            "COMMITTED", 1, owner,
                            tenantId, claimId, 0)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_QUORUM)
                        .setSerialConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_SERIAL);

                    Row result = session.execute(update).one();
                    if (result == null) {
                        throw new IllegalStateException(
                            "Missing CAS outcome");
                    }
                    return new Attempt(
                        owner, result.getBoolean("[applied]"));
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int winnerCount = 0;
            String winner = null;
            for (Future<Attempt> future : results) {
                Attempt outcome =
                    future.get(30, TimeUnit.SECONDS);
                if (outcome.applied) {
                    winnerCount++;
                    winner = outcome.actor;
                }
            }
            assertEquals(1, winnerCount);

            Row stored = session.execute(
                verify.bind(tenantId, claimId)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            assertNotNull(stored);
            assertEquals(1, stored.getInt("revision"));
            assertEquals("COMMITTED", stored.getString("state"));
            assertEquals(winner, stored.getString("owner_token"));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

**Note on assembling the code:** the class must include **`Attempt`** from Section 7 along with the corresponding **JUnit, `java.util.concurrent`, and `CqlSession`** imports. Sections 7 and 8 are **two independent test methods**. In real codebases, extract the barrier/race runner into a shared helper to avoid duplication and keep tests readable.

### 8.4. When Can “Two Trues” Still Be Legitimate?

If a test **does not target the same key**, if another operation **resets `revision` back to 0** between attempts, or if conditional statements target **different partitions**, multiple `true` results can occur without violating single-partition LWT semantics. Tests must enforce:

- Identical partition key and clustering key (if any).
- No external writer resetting or deleting the row.
- Verified seed state read at an appropriate CL.
- All actors using equivalent conditional/serial policies.
- Explicit logging of timestamps and outcomes for every attempt.

Never assert only the count of `true`s without verifying **preconditions + final data**.

## 9. Async Java Pattern: Handling `[applied]` via `CompletionStage`

Spring WebFlux or reactive Java services avoid blocking worker threads on Cassandra I/O. You can execute LWT via **`executeAsync`** and map each response to an outcome carrying the boolean.

~~~java
import java.util.Iterator;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AsyncClaimClient {
    private final CqlSession session;
    private final PreparedStatement insert;

    public AsyncClaimClient(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO lwt_lab.claim_by_key " +
            "(tenant_id, claim_id, owner_token, state, revision) " +
            "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");
    }

    public CompletionStage<Boolean> claim(
            UUID tenantId, UUID claimId, String owner) {
        BoundStatement statement = insert
            .bind(tenantId, claimId, owner, "CLAIMED", 0)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL);

        return session.executeAsync(statement).thenApply(page -> {
            Iterator<Row> iterator =
                page.currentPage().iterator();
            if (!iterator.hasNext()) {
                throw new IllegalStateException(
                    "LWT result is missing [applied]");
            }
            return iterator.next().getBoolean("[applied]");
        });
    }
}
~~~

**Explanation:**

- A completed stage yields **`true` or `false`** only when driver/server returned a normal LWT result.
- On timeout/error, the stage completes **exceptionally** rather than silently becoming `false`.
- Never call **`join`/`get`** inside a driver callback or reactive event loop.
- **`AsyncResultSet.currentPage`** suffices because conditional DML results return only the row carrying **`[applied]`**; do not treat this like multi-thousand-row paging.
- Reuse shared session/prepared statements; never create a session per HTTP request.

### 9.1. Multiple Async Calls Do Not Equal a Barrier

A loop like:

~~~java
for (int i = 0; i < 8; i++) {
    stages.add(client.claim(
        tenantId, claimId, "client-" + i));
}
~~~

dispatches requests quickly, yet does not ensure all calls are ready simultaneously. The **`CountDownLatch`** pattern in Section 7 controls logical release timing. In reactive code, use a shared **completion gate** or worker barrier before dispatching async calls, while still accounting for scheduler/network jitter.

### 9.2. Never Mask Errors with `exceptionally(false)`

Anti-pattern:

~~~java
return client.claim(tenantId, claimId, owner)
    .exceptionally(error -> false);  // SEMANTICALLY WRONG!
~~~

That turns **timeouts, `Overloaded`, and network failures** into **`[applied]=false`**, causing the API to report “lost the race” or “already exists” even when the mutation may have applied.

A cleaner approach is a **three-state** outcome model in the service:

~~~text
APPLIED_TRUE  : server returned [applied] = true
APPLIED_FALSE : server returned [applied] = false
UNKNOWN       : timeout/transport/error; state check required
~~~

This is an **application model**, not a Cassandra enum. `UNKNOWN` should preserve the cause, attempt count, business key, and reconciliation policy without logging raw payloads or secrets.

## 10. Idempotency Flags and Retries: Tests Must Observe Attempts

A common mistake is assuming “because of `IF NOT EXISTS`, infinite retries are safe”. There are two idempotency layers:

1. **Data state:** same primary key and values generally yield one logical row across retries.
2. **Business outcome/side effects:** the first attempt may return `true` and a retry `false`; if the app emits a message only in the `true` branch, a lost response leaves the workflow incomplete. Emitting before checking risks duplicates.

**`setIdempotent(true)`** only hints to the driver's retry/speculative execution policies; it does not make the whole workflow exactly-once. In contention tests, explicitly **control driver/app retries** so physical attempt counts stay visible and unknown outcomes are not hidden.

### 10.1. Retry Decision Matrix

| Operation | Timeout Before Client Learns Outcome | Safe to Auto-Retry? |
|---|---|---|
| SELECT by partition key | Normally no mutation | Bounded retry if deadline and load allow |
| INSERT same key and fixed values | Row may already have applied | Retry only per idempotency contract, then reconcile |
| INSERT IF NOT EXISTS | May have applied `true` with lost response | Never treat post-retry `false` as initial failure; compare owner/request fingerprint |
| UPDATE IF revision = 0 | May already have bumped revision to 1 | Read revision/owner before deciding next step |
| Counter increment | May already have incremented | **Never retry blindly** |
| Write Cassandra then send email | Side effects may partially occur | Requires outbox/deduplication/saga |

When simulating timeouts in tests, capture:

- Request identity and idempotency key.
- Dispatch time, deadline, and attempt counts across driver/app/gateway.
- True/false outcome or exception per attempt.
- Final row by key at proper CL.
- Downstream sink side effects (if integrated).
- Explicit **`UNKNOWN`** status when evidence is lacking.

### 10.2. Retries Must Never Silently Downgrade Serial CL

If a writer uses **`SERIAL`** to protect a multi-DC invariant, falling back to **`LOCAL_SERIAL`** or a lower regular CL on timeout violates the design. Assign LWT a dedicated **execution profile**, verify effective settings, and only alter CL intentionally.

### 10.3. Never Classify `applied=false` as an Exception

**`[applied]=false`** is a **valid conditional result**. In metrics, separate:

- **`applied_true`**: conditional operation succeeded.
- **`applied_false`**: contention/conflict or duplicate business request.
- **`request_error`**: timeout, unavailable, overloaded, network, protocol.
- **`unknown_outcome`**: unable to confirm whether data changed.

A rising `false` rate signals **contention**, duplicate business keys, or client retries—never lump it into “database error rate”.

## 11. Single-Node Runs vs Multi-Replica Clusters

**One Cassandra container** verifies CQL APIs, schemas, mappings, and app logic, yet does not simulate full distributed behavior.

| Environment | What It Verifies | What Cannot Be Inferred |
|---|---|---|
| **Single node, RF = 1** | `INSERT IF NOT EXISTS`, `[applied]`, basic serial syntax, Java mapping | RF3 quorum, network partitions, CAS with dead replicas, multi-DC |
| **Three nodes in one DC, RF = 3** | `LOCAL_QUORUM`, `LOCAL_SERIAL`, lagging replicas, intra-DC contention | Cross-DC invariants, cross-region latency |
| **Representative multi-DC** | Writers per DC, `SERIAL`/`LOCAL_SERIAL` policies, controlled network partitions | Full production behavior if hardware/load differ |
| **Production** | Real SLOs/errors under live traffic | Not an environment to deliberately inject faults or touch user data |

In fast CI, use **Testcontainers** to spin up a short-lived single Cassandra node (with approved pinned module and image versions). Use an **`RF = 1`** schema and document that the test verifies **baseline semantics** only. To validate quorum or replica loss, run a **multi-node environment** in a dedicated pipeline.

**Never hardcode Testcontainers imports/APIs** without checking your version. Testcontainers Cassandra modules and APIs differ across releases; align dependencies with your Java BOM, verify docs for the locked version, and confirm in CI. Never fake multi-DC production with one container and claim global consistency.

## 12. Test Independence and Repeatability

Contention integration tests become flaky if the environment is not controlled:

1. **Generate fresh `tenantId`/`claimId` per test.** Never reuse fixed UUIDs across CI runs.
2. **Never run two suites sharing a keyspace/fixture** if tests truncate or wipe tables.
3. Create schemas via **dedicated test setup/migrations**, rather than having every JUnit method or Spring context send DDL.
4. Wait for schema agreement before preparing statements.
5. Verify cluster health and sufficient replicas before starting contention.
6. Never assume winner order: **`client-0` need not win**. Assert only one winner and that the final row matches the winner.
7. Never use **`Thread.sleep`** to infer race ordering; use barriers and invariant-based assertions.
8. Set CI timeouts and contention levels appropriate to test cluster capacity.
9. Record errors/timeouts/metrics separately; never turn exceptions into `applied=false`.
10. Clean up data **strictly within the lab keyspace** per ownership, avoiding concurrent tombstones/truncates that disturb other tests.

For large-data tests, use short-lived clusters with clear lifecycles. **`DELETE`/`TRUNCATE`** carry distributed costs—cleanup is not free.

## 13. Spring Boot / Spring Data: Dedicated Test Profiles and Managed Schemas

In Spring Boot and Spring Data Cassandra apps, tests often exercise the **real service/repository** instead of building `CqlSession` per method. Separate three layers:

1. **`CqlSession`/Java driver:** sends conditional CQL, receives **`[applied]`** and server errors.
2. **Spring service:** selects serial/regular CL, preserves idempotency keys, maps `false`/`unknown` to business outcomes.
3. **HTTP/controller:** returns 201/200/409/503 or contract responses without leaking sensitive data.

### 13.1. Test Contexts Should Not Auto-Create Schemas

Integration test skeleton:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cassandra.schema-action=none"
})
public class LwtSpringIntegrationIT {
    @Autowired
    private CqlSession session;

    @Test
    void serviceUsesRealCassandraSession() {
        // Prepare test fixture with a fresh key.
        // Call the real service to execute IF NOT EXISTS.
        // Assert applied true/false + final persisted state.
        // Do not run CREATE/DROP on every context startup.
    }
}
~~~

**Snippet limitation:** this is a skeleton, not a complete runnable test; the method marks where to invoke the service and assert. Property **`spring.cassandra.schema-action`** targets Spring Boot 3.x conventions; Boot 2.x and other Spring Data versions may use different namespaces. Verify your version instead of assuming an unrecognized property disabled DDL.

Provision lab schemas via migrations/test bootstrap before starting the context or suite. Never let `ApplicationRunner`/`@PostConstruct` create and drop tables on every Spring Boot instance.

### 13.2. Why Test Through the Service in Addition to Direct CQL?

Pure CQL tests verify the cluster's LWT semantics, yet a service can still fail even when Cassandra behaves properly:

- Catching exceptions and returning **boolean `false`**, erasing `UNKNOWN` status.
- Emitting a **“created” event** before checking `[applied]`.
- Generating a **new `order_id`** on timeout retries, creating two rows in different partitions for one request.
- Using one execution profile for SELECT and another for `IF NOT EXISTS`, misaligning serial CL.
- Running service instances with **different local DCs** while business logic assumes global uniqueness.
- Mixing relational **`@Transactional`** or repository patterns assuming Cassandra supports multi-row/multi-table transactions.

Maintain **two integration layers**: direct LWT CQL tests for database behavior and endpoint/service tests for **outcome mapping + idempotency + side effects**.

### 13.3. Clear Business Response States

Suppose claiming a key for a request ID:

| Service State | Meaning | API-Layer Action |
|---|---|---|
| **`CREATED`** | LWT `true` and row has matching fingerprint | Return created status |
| **`ALREADY_OWNED_BY_SAME_REQUEST`** | LWT `false`, read/reconcile row matches idempotency key | Return idempotent success per contract |
| **`CONFLICT`** | LWT `false`, row belongs to a different request | Return business conflict |
| **`UNKNOWN_RECONCILIATION_REQUIRED`** | Timeout/transport error or state unverifiable | Return trackable error; never report `false` or `created` |
| **`UNAVAILABLE/OVERLOADED`** | Cluster lacks capacity | Bounded retry/backoff/load-shedding; never retry forever |

Exact HTTP codes (201, 200, 409, 503...) depend on API design, but **never return the exact same “failed” response** for a failed condition vs an unknown outcome.

## 14. Concurrency Testing at Varying Load Levels

An 8-contender test is helpful, yet insufficient to evaluate contention under high load.

### 14.1. Contention Matrix

| Scenario | Key Count | Concurrent Clients | What to Observe |
|---|---:|---:|---|
| **Hot key** | 1 | 2 / 8 / 32 | Exactly one winner when deterministic; CAS latency/`false` count |
| **Independent keys** | 100 | 100 | Independent keys can all return `true`; measure throughput |
| **Same tenant, multiple claims** | 100 | 100 | Partition key includes `claim_id`, so requests spread across partitions |
| **Mixed reads and CAS** | 1 | N readers + N writers | Observe data/CL and conditional updates |
| **Mixed-DC writers** | 1 | Writers from `dc1` and `dc2` | Verify `SERIAL`/`LOCAL_SERIAL` in exact scope |
| **Injected failure** | 1 | N | Classify `true`/`false`/error/unknown and reconcile |
| **Backfill/compaction load** | many | N | CAS latency, timeouts, and API impact |

Counts like **32/100** are illustrative. Larger tests must **bound concurrency, rate, and total duration** to avoid unintentionally saturating the test cluster.

### 14.2. Single-Key Races vs Distributed Throughput Are Different Measurements

If 1,000 clients race on one key, serialization and Paxos contention drive latency way up. That does not represent throughput for 1,000 independent claims spread across token ranges. Separate:

- **Safety/correctness tests:** single-winner invariant per partition.
- **Performance under contention:** latency/p99, failure rates, and CAS contention.
- **Distributed throughput tests:** many partition keys, realistic tenant/order ID distributions.
- **Availability tests:** replica/DC loss or network partitions.

Never treat hot-key latency as representative of all queries, nor judge correctness solely by throughput.

## 15. Testing Under Timeouts, Replica Failures, and Network Disruptions

The single most important rule in distributed integration testing is: **never force every outcome into a boolean**.

### 15.1. Keep Three Distinct States

~~~mermaid
flowchart TD
    A["Execute LWT"] --> B{"Received complete response?"}
    B -->|Yes| C{"[applied]?"}
    C -->|true| T["APPLIED_TRUE"]
    C -->|false| F["APPLIED_FALSE"]
    B -->|No/exception| U["UNKNOWN or classified ERROR"]
    U --> R["Reconcile row by key + request fingerprint"]
    R --> D{"Enough evidence to conclude?"}
    D -->|Yes| E["Report outcome per business contract"]
    D -->|No| I["INCONCLUSIVE; investigate / controlled retry"]
~~~

On a timed-out request:

1. Preserve the sent **`tenant_id + claim_id + owner/request fingerprint`**.
2. Never change `claim_id` on retry.
3. Classify **server timeout**, **driver-side deadline**, **`Overloaded`**, **`Unavailable`**, and **connection errors**.
4. Re-read the row by partition key at the designed CL.
5. Compare owner/fingerprint/version against the original request.
6. If the read is unreliable or replicas are missing, keep **`UNKNOWN`** status rather than guessing success/failure.
7. If business rules permit retrying, enforce a **retry budget** without silently downgrading serial/regular CL.

**No simple timeout simulation proves all timeouts happen post-commit.** Inspect actual timelines and persisted data per occurrence.

### 15.2. Controlled Fault Scenarios

| Lab Fault | What to Check | Assumptions to Avoid |
|---|---|---|
| Increased network latency to one replica | Do CL/serial consensus and deadlines still hold? | An UP replica is always fast/healthy |
| Stopping one replica of RF3 | Do quorum/serial phases stay available per policy? | Every request must succeed |
| Dropping client responses | Reconcile when server may have applied | Timeout = `false` |
| Temporary cross-DC partition | `SERIAL`/`LOCAL_SERIAL` invariants in multi-DC | Single-local test proves global uniqueness |
| Bounded disk/GC stress | CAS latency, timeouts, `Overloaded` | Infinite retries improve reliability |
| Retry with identical request ID | Is post-retry `false` recognized as same-request success? | `false` = another client won |
| Client crash before recording outcome | Does the job have checkpoints/reconciliation? | No log = no mutation |

Use **fault injection/network shaping** strictly on approved test clusters. Never stop replicas, break disks, or cut production networks to study LWT.

### 15.3. Reasonable Pass/Fail Criteria Under Faults

For **fault-free contention**, assert **exactly one `applied=true`** and the final row matching the winner.

For **fault-injection** runs, split criteria into two buckets:

- **Safety:** never observe two **invalid** `applied=true` results for the same state version within the same LWT scope, and no data violating invariants.
- **Liveness/availability:** track completed requests, timeouts/unavailables, latency, and recovery once the fault clears.

When attempts time out, the **observed `applied=true` count** can be **0** even though the row was created. Tests must report **`inconclusive/unknown outcome`** and inspect evidence rather than falsely claiming Cassandra “did not write”.

## 16. Observability in Java, Cassandra, and CI

### 16.1. Structured Test Reports

Example execution report:

~~~yaml
suite: "lwt_contention_integration"
run_id: "ci-example-2026-11-21-01"
environment: "staging-lab"
cassandra_version: "<exact-version>"
java_driver_version: "<exact-version>"
jdk_version: "<exact-version>"
topology:
  datacenter: "dc1"
  nodes: 3
  replication_factor: 3
cql:
  table: "lwt_lab.claim_by_key"
  statement_shape: "INSERT ... IF NOT EXISTS"
  regular_consistency: "LOCAL_QUORUM"
  serial_consistency: "LOCAL_SERIAL"
test:
  contenders: 8
  partition_keys: 1
  fresh_fixture: true
outcomes:
  applied_true: 1
  applied_false: 7
  exceptions: 0
  unknown_outcomes: 0
verification:
  expected_winners: 1
  final_row_matches_winner: true
  status: "PASS"
evidence:
  ci_job: "<run-link>"
  test_logs: "<trace-id-location>"
  server_metrics: "<dashboard-or-snapshot>"
~~~

This is an **illustrative report format**, not Cassandra config or default driver output. In real CI, also capture **start/end timestamps, query shapes, bytes/latencies, errors by class**, and **tested scope**. Never log raw tenant IDs, session tokens, payloads, or PII.

### 16.2. Key Metrics

| Layer | Metrics / Signals | Why Needed |
|---|---|---|
| **Java test harness** | N contenders, barrier readiness, `true`/`false`/error counts, duration | Confirms real contention and no swallowed errors |
| **Driver** | Retry counts, coordinator, request timeouts, local DC, CL/profile | Reveals client's effective execution policy |
| **Cassandra LWT** | CAS latency, contention, version-specific timeouts/failures | Observes Paxos cost and hot-key pressure |
| **Cassandra cluster** | Replicas UP/DOWN, RF/DC, read/write latencies, unavailables | Confirms CL conditions were met |
| **JVM/Storage** | GC pauses, heap/native RSS, disk I/O/free, compaction backlog | Separates infra/background load from logic |
| **Business service** | `CREATED`/`CONFLICT`/`SAME_REQUEST`/`UNKNOWN`, duplicate side effects | Verifies end-to-end invariant protection |

Exact LWT metric names (CAS contention, read/write latency...) depend on Cassandra version and exporter/JMX mappings. Never assume a specific Prometheus metric name always exists.

### 16.3. Read-Only Cluster Inspection Commands

~~~bash
# Health and DC/rack/tokens.
nodetool status

# Node info and operational status.
nodetool info

# Pending/dropped messages and thread pools.
nodetool tpstats

# I/O-intensive background work.
nodetool compactionstats

# Table/partition statistics.
nodetool tablestats lwt_lab.claim_by_key
~~~

Also inspect coordinator and replica server logs, disk latency, GC, and network metrics. An **`UP/NORMAL`** node can still be overloaded; compaction or repair can spike LWT tail latency.

**Never reflexively run `repair` when seeing `applied=false`.** `false` is a conditional outcome; repair reconciles replicas at the storage level—it does not make conditions turn `true` and knows nothing of application invariants.

## 17. Safety Tests vs End-to-End Business Flow Tests

An “only one winner” test is necessary yet often insufficient.

Consider an order-creation API:

~~~text
1. Claim orderId via LWT IF NOT EXISTS.
2. Write order details into query-driven table.
3. Publish OrderCreated event.
4. Return HTTP 201.
~~~

Suppose step 1 returns `true`, step 2 succeeds, and step 3 fails. LWT protected **claim uniqueness**, yet the event is missing. If the client retries, step 1 returns `false`. If the code treats `false` as a conflict and aborts, the event may never be published.

Testing and design must account for:

- **Idempotency keys** and request fingerprints per business request.
- Workflow progress states, e.g. `CLAIMED → STORED → PUBLISHED`.
- Outbox/CDC or durable event logs when reliable messaging is required.
- Reconciliation/recovery jobs resuming from intermediate states.
- Explicit response contracts for duplicate requests from **the same client**.
- Never treating timeouts as rolling back step 1.

**Never treat LWT as a cross-system transaction.** Supplement Cassandra-level concurrency tests with service/endpoint integration tests whenever external side effects exist.

## 18. Detecting and Fixing Flaky Tests

A CAS test that occasionally fails due to overloaded runners or barrier timing should never be “fixed” by **adding unbounded `Thread.sleep` calls** or deleting assertions.

### 18.1. Sources of Flakiness

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| `0 true, N false` on first run | Stale fixture or collision with another test | Log run ID, hashed fixture key; generate fresh keys |
| `Future` timeout | Slow cluster, high contention, tight CI timeout | Inspect CAS latency, disk/GC, retries/CL |
| Some workers miss barrier | Thread pool smaller than contender count, overloaded CI | Set pool size = N; explicit timeout on ready latch |
| Two `true`s across tests | Tests used **different keys** or reset revision | Check partition keys, seeds, and concurrent writers |
| Unknown table/schema | Migration/setup unfinished, schema not agreed | Separate schema lifecycle from test execution |
| `applied=true`, verify read wrong | External concurrent writer or wrong read CL/fixture | Isolate test; check CL, timestamps, data model |
| `applied=false` after retry | Prior attempt may have applied | Reconcile owner/fingerprint; classify duplicate |
| Passes single-node, fails multi-DC | Different RF/serial policy, network latency | Test topology matrix; verify `SERIAL`/`LOCAL_SERIAL` |

### 18.2. Safe Remediation Practices

1. Preserve **test inputs and run IDs** for controlled reproduction without logging sensitive data.
2. Classify **assertion failures, infrastructure failures, and unknown outcomes** separately.
3. Capture **root-cause stack traces**; never swallow exceptions in `CompletableFuture`/`Future`.
4. Inspect driver/server versions and effective retry policies.
5. Verify schema agreement, cluster health, and resource baselines.
6. Re-run on an isolated test cluster after fixing root causes rather than just bumping timeouts.
7. When a fault test is inherently non-deterministic, define clear **safety invariants** and inconclusive criteria instead of unrealistic liveness expectations.
8. Never mark a failing critical test `@Disabled`/`ignored` just to turn CI green without an owner, ticket, and fix plan.

## 19. Scenario Exercises and Suggested Answers

### Exercise 1 — Is SELECT Then INSERT Strong Enough?

Two clients read the same claim at `LOCAL_QUORUM`, both see no row, and both run a regular `INSERT`.

**Question:** Is it guaranteed only one client reports created?

**Answer:** No. Two separate `LOCAL_QUORUM` requests do not form an atomic compare-and-set. You need `IF NOT EXISTS` or proper uniqueness/idempotency mechanisms, verified under contention.

### Exercise 2 — Counting `applied` When N = 10

On a brand-new key, 10 clients concurrently run `INSERT IF NOT EXISTS` with no timeouts or external writers. Outcomes: 1 `true`, 9 `false`.

**Question:** Is the test complete?

**Answer:** Not quite. Verify **the final row holds the winner's owner**, expected `state`/`revision`, partition key, and serial CL policy. Also record CL, RF/DC, and timings.

### Exercise 3 — Test Gets 0 `true` and One Timeout

With 8 workers, 7 return `false` and 1 times out; a final `SELECT` finds the claim exists.

**Question:** Can we report Cassandra violated LWT because there was no winner?

**Answer:** No. The timed-out worker may have applied the claim. The test must report **`UNKNOWN/INCONCLUSIVE`** and reconcile the owner/fingerprint—never count timeouts as `false`.

### Exercise 4 — Retry Changes `orderId`

A client tries creating an order with `orderId` A, times out, and generates `orderId` B to retry.

**Question:** Does LWT prevent two logical orders?

**Answer:** No. A and B map to different partition keys; both can apply. Keep `orderId`/idempotency keys stable per business request.

### Exercise 5 — CAS Revision

A row is at `revision = 3`. Two workers concurrently run `UPDATE SET revision=4 IF revision=3` on the same partition.

**Question:** If both return cleanly, how many `true`s are expected and what must be verified?

**Answer:** One `true` and one `false` assuming no other writer resets revision within the same LWT scope. Verify final `revision = 4` and the winner's owner/state.

### Exercise 6 — Test That Doesn't Actually Contend

A test submits N = 20 tasks to a 2-thread executor, with each task waiting at a latch until all 20 report ready.

**Question:** What happens?

**Answer:** The remaining 18 tasks never start to count down the latch; the test deadlocks/times out. Size the pool to match the barrier or avoid blocking unscheduled workers.

### Exercise 7 — Single-Node Testcontainers

A team runs LWT on a single RF = 1 Cassandra container; all `true`/`false` tests pass. They conclude the system guarantees RF = 3 quorum and multi-DC correctness.

**Question:** Is this conclusion valid?

**Answer:** No. Single-node tests check basic syntax/logic; you need multi-node RF3 and multi-DC writer tests to verify topology-specific consistency/availability.

### Exercise 8 — `LOCAL_SERIAL` Across Two DCs

Services in `dc1` and `dc2` concurrently claim the same key, both using `LOCAL_SERIAL` for low latency; business rules require system-wide uniqueness.

**Question:** Is testing only in `dc1` sufficient proof?

**Answer:** No. Evaluate consensus scope, Cassandra version, per-DC RF, and every writer's serial policy, and run cross-DC tests; consider `SERIAL` for global invariants per official docs.

### Exercise 9 — Is `applied=false` an Error to Retry?

A new request gets `[applied]=false` because another worker already created the row.

**Question:** Should it retry in a loop until `true`?

**Answer:** No. `false` is a valid conditional result. The service should return conflict or handle idempotent duplicates by owner/fingerprint rather than adding CAS contention.

### Exercise 10 — LWT Succeeds, Email Fails

A client claims an order successfully, then fails sending the email. Retrying the whole endpoint returns LWT `false`.

**Question:** How do you avoid dropping the email or sending duplicates?

**Answer:** Track workflow state, use an outbox/stable event ID, idempotent sinks, and reconciliation. LWT protects the claim only; it does not transactionally commit email delivery.

### Exercise 11 — Under Test Overload

A test scales up to 5,000 contenders on a single partition; `Overloaded`, `WriteTimeout`, and huge p99 appear.

**Question:** Should you downgrade `LOCAL_QUORUM` to `ONE` and crank up retries to “turn the test green”?

**Answer:** No. That breaks the consistency contract and amplifies load. Lower concurrency, separate correctness tests from load tests, and inspect CAS contention, disk/GC, and test cluster limits.

### Exercise 12 — New Table for Another Access Pattern

The app needs to query claims by **`owner_token`**, while the table has partition key **`(tenant_id, claim_id)`**.

**Question:** Can you filter by `owner_token` and require `LOCAL_QUORUM` to make it fast?

**Answer:** CL does not change access patterns. Design a query-driven table keyed by owner or evaluate a version-appropriate index. If maintaining two tables, use idempotent projections and reconciliation; LWT on the claim table is not a cross-table transaction.

## 20. CI/CD Checklist for LWT Contention Testing

- [ ] CQL schemas/replication created via isolated setup/migrations, awaiting schema agreement before tests.
- [ ] Each test uses **fresh `tenantId + claimId`**, avoiding collisions with other suites.
- [ ] All contenders target the **same partition key** and condition to create a real race.
- [ ] Uses **`CountDownLatch`/barriers** or explicit concurrency primitives, never sequential loops.
- [ ] Tracks **`applied_true`**, **`applied_false`**, **`errors`**, and **`unknown`** separately.
- [ ] Never coerces timeouts/exceptions into `applied=false`.
- [ ] Asserts `exactly-one true` only when **all outcomes are deterministic**, the key is fresh, and no external writers interfere.
- [ ] Verifies **final row** owner/state/revision at proper CL.
- [ ] Also tests **`UPDATE IF revision = ...`** and stale expected revisions.
- [ ] Tests same-client post-timeout retries and idempotency keys/fingerprints.
- [ ] Java service never emits side effects before checking `[applied]` and never conflates `false` with `unknown`.
- [ ] Regular CL and serial CL are set explicitly and match RF/DC.
- [ ] Never mixes `SERIAL`/`LOCAL_SERIAL` across writers without a verified consensus strategy.
- [ ] Single-node Testcontainers reserved for baseline checks; multi-node/multi-DC have dedicated suites.
- [ ] Never opens/closes `CqlSession` per worker; uses a thread-safe session and prepared statements.
- [ ] Executors/futures enforce timeouts and clean up in `finally` so tests never hang.
- [ ] Fault-injection tests enforce retry budgets with backoff/jitter, avoiding retry storms.
- [ ] Replica/network fault tests run on staging, never harming production.
- [ ] Monitors CAS contention, p95/p99, errors, RF/DC, disk/GC, and compaction/repair under load.
- [ ] Never uses `repair` to “fix” `applied=false` or undo bad writes.
- [ ] Never logs raw payloads, credentials, idempotency secrets, or user PII.
- [ ] CI reports record Cassandra/driver/JDK versions, topology, CL, contender count, durations, and evidence.
- [ ] Distinguishes **correctness PASS**, **infrastructure error**, and **INCONCLUSIVE** when outcomes are missing.

## 21. Summary

**Lightweight Transactions** enforce **`IF NOT EXISTS`** or **`IF column = value`** within Cassandra's supported bounds, and the **`[applied]`** column reports whether **that specific conditional operation** applied. When multiple clients race for the same new key and all responses are deterministic, tests should observe **exactly one `true`** and **final state matching the winner**. For CAS revisions, only one request advances a given state version per partition under controlled conditions.

**Timeouts/exceptions are not `applied=false`.** The first attempt may have succeeded with a lost response, causing a retry to return `false` because the same request already created the row. Therefore, tests must preserve **idempotency keys**, reconcile rows, and separate **`APPLIED_TRUE` / `APPLIED_FALSE` / `UNKNOWN`**.

A trustworthy LWT test combines **contention barriers, isolated fixtures, CQL/Java Driver integration, RF/DC-appropriate regular/serial consistency, final data verification, distributed fault tests, and observability**. In Apache Cassandra, you must still respect partition keys, query-driven table design, compaction/repair, and replica availability; correctness of a single LWT **does not automatically provide multi-table transactions, exactly-once email/broker delivery, or availability across every failure**.
