# Pattern for Creating Unique Identifiers Within a Guaranteed Scope

In Apache Cassandra, a **unique** value can mean two very different things: either the application *generates values with an extremely low collision probability* or the system *actually rejects the second requester trying to claim the same value*. This lesson belongs to the **LWT and Concurrency** chapter, explaining how to use **Lightweight Transactions (LWT)** with **IF NOT EXISTS** to guarantee an identifier cannot be claimed by two concurrent requests, while precisely defining the **scope** in which that guarantee holds.

This is a concrete design pattern in the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module: learners apply partition keys and query-driven wide-column modeling, practice CQL/Java Driver usage, weigh replication and consistency levels, and handle retries, timeouts, and failures step by step. LWT provides **compare-and-set (CAS)** on a partition; it does not automatically create a UNIQUE constraint on an arbitrary column or a general transaction across multiple partitions.

## 1. Expected Outcomes

After this lesson, you will be able to:

1. Define the exact uniqueness scope: system-wide, per-tenant, per-day, per-namespace, or solely per primary key.
2. Distinguish **low-collision-probability UUID/timeuuid** from **LWT-enforced uniqueness**.
3. Design the partition key so all requests contending for the same identifier hit **the same conditional row/partition**.
4. Use **INSERT ... IF NOT EXISTS** and read **`[applied]`** to arbitrate contention.
5. Understand the boundary between **claiming an identifier** and **writing the business profile** in a different partition.
6. Implement safe retries in Java, even when an LWT request times out and the write outcome is uncertain.
7. Choose consistency levels, write concurrency test scenarios, and monitor operational cost.

## 2. "Unique" Must Have an Explicit Scope

Imagine a registration service with tenant A and tenant B. Two users both want the username **an**.

| Business Rule | Example Key to Protect | Can Two Tenants Both Use "an"? |
| --- | --- | --- |
| Username unique **system-wide** | handle = an | No |
| Username unique **within each tenant** | (tenant A, an), (tenant B, an) | Yes |
| Ticket code unique **within each event** | (event ID, ticket code) | May repeat in a different event |
| Order code unique **per day** | (UTC date, order code) | May be reused on another day if rules allow |
| Unique record key | record_id | Guarantees only no two rows share that primary key; does not make other columns unique |

The verbal rule must map to **one deterministic control key**. If the policy is "unique within a tenant," the key should contain **`tenant_id` and the normalized name**. When two clients register the same name in tenant A, they must collide on **one partition key**; if each client generates a UUID and writes to two different partitions, Cassandra has nothing to stop both.

### Two Common Kinds of Identifiers

**Machine-generated identifiers**: random UUIDs (e.g., UUID v4) work well for distributed record IDs when negligible collision probability is acceptable. TimeUUID adds a time component for ordering and time-range queries, but it is not a DB-enforced uniqueness lock. If the requirement is "never accept an already-used key," use a conditional insert on **that ID key itself**.

**Business identifiers**: email, username, contract number, voucher code, etc., can collide intentionally when users pick the same value. Here, merely generating a UUID for `account_id` is **not enough**. You must guard the business value using a **claim (reservation) row** whose primary key is the protected identifier.

## 3. How Does LWT Protect Against Contention?

A regular CQL `INSERT` is an *upsert*: if the row already exists, the write can update/overwrite columns under timestamp rules; it does not throw a duplicate-key error like many RDBMSs.

~~~sql
-- If record_id already exists, this performs no duplicate check.
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'new value');
~~~

Adding **IF NOT EXISTS** makes Cassandra run a **Paxos**-based LWT so competing proposals against **the same partition** are resolved in an order observable as a CAS operation:

~~~sql
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'new value')
IF NOT EXISTS;
~~~

If it succeeds, the CQL result contains **`[applied] = true`**. If the key was already written, **`[applied] = false`**, and the result may include the existing row's data so the application can decide whether it is a conflict or a retry of the same request.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant C as Cassandra / Paxos
    participant B as Client B
    A->>C: INSERT key=an IF NOT EXISTS
    B->>C: INSERT key=an IF NOT EXISTS
    C-->>A: applied=true (one winner)
    C-->>B: applied=false (already owned)
    Note over A,B: A/B order is illustrative; winner depends on execution
~~~

The **guarantee scope** is the condition on the shared key/partition used by all participants. It does not mean "unique across all values of a column in every table"; Cassandra does not support an arbitrary global UNIQUE constraint on a non-key column merely by adding `IF` to a table with a different partition key.

### Two Consistency Levels When Writing LWT

A conditional statement has two separate properties:

- **Serial consistency** (**SERIAL** or **LOCAL_SERIAL**): governs the Paxos phase that evaluates the condition and orders CAS operations.
- **Regular consistency** (e.g., **LOCAL_QUORUM**): applies to the write/commit phase and affects how regular reads observe the newly committed write.

~~~sql
-- Commands for cqlsh; not CQL syntax sent from the Java driver.
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;
~~~

In multi-DC systems requiring **cluster-wide uniqueness**, design a consistent coordination domain: use `SERIAL` to coordinate across the required scope and verify behavior in a multi-DC setup. `LOCAL_SERIAL` runs the serial phase only in the local DC, so never assume by default that two regions can accept claims concurrently while preserving **cluster-wide** uniqueness. Another simpler approach is routing all claim operations for a namespace to one home DC with explicit failover rules. LWT availability drops when replicas are insufficient for consensus or commit: getting a timeout **does not mean** the condition failed.

## 4. Pattern 1 — ID Is Also the Primary Key: Blocking ID Overwrites

When an ID only needs to be unique within one table, put the ID (and namespace if needed) in the partition key:

~~~sql
-- Example requires DC dc1 to exist with enough replicas; adjust RF for your lab cluster.
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 3}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS app.records_by_id (
  record_id uuid PRIMARY KEY,
  description text
);

CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;

INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'created by request A')
IF NOT EXISTS;

-- Retry same ID with a different payload: expect [applied] = false.
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'created by request B')
IF NOT EXISTS;
~~~

Rule achieved: **no `INSERT` with `IF NOT EXISTS` is allowed to create the same `record_id` a second time while the row exists**. However:

1. It does not stop another client using a **regular `UPDATE`/`INSERT`** from modifying or overwriting the same row. Every writer must follow the protection protocol.
2. If you delete the record, you may allow **ID reuse**; this differs from "the ID has never been used in history."
3. It does not guarantee `description` (or an email in another table) is unique.

For "an ID may never be reused forever," keep an unexpiring, undeleted "issued ledger," or use an ID-issuing service with an appropriate history-retention policy. Putting a TTL on the issued ledger breaks the "forever" guarantee.

## 5. Pattern 2 — Claiming a Business Identifier per Tenant

**Problem:** each tenant has many accounts; **handle** (login display name) must be unique **within the tenant**, while `account_id` is an application-generated UUID and profiles are queried by `account_id`.

Design two tables for the two query paths:

~~~sql
-- One partition per (tenant_id, handle_key) pair.
CREATE TABLE IF NOT EXISTS app.handle_claims (
  tenant_id text,
  handle_key text,
  account_id uuid,
  request_id uuid,
  PRIMARY KEY ((tenant_id, handle_key))
);

-- One partition per account, serving lookups by account_id.
CREATE TABLE IF NOT EXISTS app.accounts_by_id (
  tenant_id text,
  account_id uuid,
  handle_key text,
  display_name text,
  request_id uuid,
  PRIMARY KEY ((tenant_id, account_id))
);
~~~

Here **`tenant_id` and `handle_key` together form the claim's partition key**. The goal is to spread handles across the token ring instead of putting every handle of a tenant into **one giant partition**. Do not use `PRIMARY KEY ((tenant_id), handle_key)` just for convenience if a tenant can have many registrations: that design packs all handles of a tenant into a single partition and leads to partition-size limits and hot partitions.

### Step 1 — Normalize and Lock Down the Key to Claim

Before any query, the application must define one shared **canonicalize function** for all callers: trimming, case folding, Unicode normalization, accents, whitespace, allowed characters, and rename behavior. For example, restrict handles to ASCII `a-z`, `0-9`, and underscore, lowercased with `Locale.ROOT`:

~~~text
Input "  Alice_01  " -> handle_key = "alice_01"
Input "ALICE_01"     -> handle_key = "alice_01"
Scope: tenant_id = "shop-7"
Claim key: ("shop-7", "alice_01")
~~~

This is an **application-defined business rule**; never silently change it once data exists. If different services normalize differently, they can create two distinct keys for names humans consider identical.

### Step 2 — Generate Stable Request IDs

The application generates **`account_id`** once for the account to be created and **`request_id`** (idempotency key) once for the registration operation. When a client times out or retries, **reuse both exact IDs**—never regenerate them on each attempt. Persist `request_id` durably in the orchestrator/request input; an idempotency header may be supplied by the client and validated by the server per tenant.

### Step 3 — Claim with One LWT

~~~sql
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;

INSERT INTO app.handle_claims
  (tenant_id, handle_key, account_id, request_id)
VALUES
  ('shop-7', 'alice_01',
   22222222-2222-4222-8222-222222222222,
   aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Expected outcomes when two requests target `(shop-7, alice_01)`:

| Result | Meaning | Handling |
| --- | --- | --- |
| **`[applied] = true`** | Request acquired ownership of the claim. | Proceed to create the `accounts_by_id` profile; log for recovery. |
| **`[applied] = false`**, stored `account_id` + `request_id` **match this request** | An earlier attempt likely claimed it; this is a retry of the same operation. | Continue/verify the profile-creation step. |
| **`[applied] = false`**, owner or `request_id` **differs** | Handle is currently held by someone else. | Return conflict (e.g., HTTP 409); do not create a profile using this handle. |
| **Timeout/Unavailable or indeterminate error** | Unknown whether the claim was written or not. | Record **UNKNOWN**, retry/reconcile with the same IDs; do not immediately grant the handle to someone else. |

An LWT failing due to its condition (`[applied] = false`) is **different** from an LWT timing out. Never collapse these two cases into the same "handle already exists" error.

### Step 4 — Write the Profile by ID

Only after the claim is confirmed for this exact request, create the profile:

~~~sql
INSERT INTO app.accounts_by_id
  (tenant_id, account_id, handle_key, display_name, request_id)
VALUES
  ('shop-7',
   22222222-2222-4222-8222-222222222222,
   'alice_01', 'Alice', aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Intentionally use **`IF NOT EXISTS`** on the `account_id` partition too, preventing a retry with a mismatched payload from overwriting an existing account. If `[applied] = false`, read the existing state to verify **`account_id`/`handle_key`/`request_id`** match the request; do not blindly treat every rejection as success.

**Critical boundary:** `handle_claims` and `accounts_by_id` live in **two different partitions**. Two separate LWTs **do not form an atomic/isolated cross-partition transaction**. If the app crashes after claiming but before writing the profile, the handle remains reserved while the account does not yet appear. A **`LOGGED BATCH`** also does not turn this pair into a conditional UNIQUE constraint with full multi-row SQL isolation. Therefore, **recovery** is mandatory in this pattern.

~~~mermaid
flowchart TD
    req["Register tenant + handle"] --> canon["Normalize handle and fix request_id"]
    canon --> cas["INSERT claim IF NOT EXISTS"]
    cas -->|applied=true| profile["INSERT account IF NOT EXISTS"]
    cas -->|applied=false| check{"Owner and request_id match?"}
    check -->|Yes| profile
    check -->|No| conflict["409: handle already taken"]
    cas -->|Outcome unknown| unknown["Retry with same ID or investigate"]
    profile --> done["Verify profile then publish success"]
    profile -->|Outcome unknown| retry["Retry/reconcile profile with same ID"]
~~~

### Conditions for the "Unique" Claim to Hold

With this pattern, the guarantee is: **at any point in time, for each `(tenant_id, canonical_handle)` currently holding a valid claim, at most one `account_id` owns the claim via the LWT protocol**. It simultaneously requires:

1. All account creation/rename write paths claim the same canonical key before publishing the handle.
2. Only controlled administrative workflows may edit/delete claims; no regular writer overwrites `account_id` on a claim.
3. No TTL expires claims outside an explicitly designed reuse policy.
4. Replication, serial consistency, multi-DC routing, and data permissions satisfy the required guarantee scope.
5. An account is never published with that handle before the claim workflow confirms ownership.

This is **uniqueness within the active namespace of the claim table**; it does not automatically imply historical uniqueness across all past allocations, absence of transiently missing profile rows, or validation across external systems.

## 6. Java Code: Checking `[applied]` Without Turning Timeouts into Conflicts

The example uses **Java Driver 4.x** (package `com.datastax.oss.driver.api`). `CqlSession` is already built with appropriate contact points, local datacenter, credentials, and connection policy. The snippet below illustrates only **acquiring the claim**:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

enum ClaimResult { ACQUIRED, OWNED_BY_SAME_REQUEST, CONFLICT }

static ClaimResult claimHandle(
    CqlSession session,
    PreparedStatement stmt,
    String tenantId,
    String canonicalHandle,
    UUID accountId,
    UUID requestId
) {
    BoundStatement bound = stmt
        .bind(tenantId, canonicalHandle, accountId, requestId)
        .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(ConsistencyLevel.SERIAL);

    ResultSet result = session.execute(bound);
    if (result.wasApplied()) {
        return ClaimResult.ACQUIRED;
    }

    Row existing = result.one();
    if (existing != null
        && accountId.equals(existing.getUuid("account_id"))
        && requestId.equals(existing.getUuid("request_id"))) {
        return ClaimResult.OWNED_BY_SAME_REQUEST;
    }
    return ClaimResult.CONFLICT;
}

// Prepare once at service startup:
PreparedStatement claimStmt = session.prepare(
    "INSERT INTO app.handle_claims " +
    "(tenant_id, handle_key, account_id, request_id) " +
    "VALUES (?, ?, ?, ?) IF NOT EXISTS");
~~~

In the code above:

- **ACQUIRED**: claim succeeded; the next step is creating the profile, not treating the two-table workflow as done.
- **OWNED_BY_SAME_REQUEST**: confirms only that the claim belongs to the same account/request; you must still **verify or complete** the profile write.
- **CONFLICT**: the claim is owned by another request; return the appropriate business status.
- **Exception/timeout during `execute`**: the function does not return `CONFLICT`, because the LWT may have committed before the client lost the response. The orchestration layer must preserve the same `request_id`/`account_id` and run controlled retries or reconciliation. Never do blind infinite retries or generate a new `request_id`.

Exact driver versions, execution profiles, timeouts, and exceptions vary; this code illustrates one operation, not a standalone application. All input variables are bound into a prepared statement to preserve types and avoid concatenating CQL strings from user input.

## 7. Retries, Orphan Claims, and Identifier Reclamation

### Two "Halves" of a Multi-Partition Workflow

| Failure Point | Possible Remaining State | Resolution |
| --- | --- | --- |
| Before claim succeeds | No claim, or indeterminate state due to timeout | Retry with same IDs; use CAS result/read check to distinguish |
| Claim succeeds, profile not written | **Orphan claim**: name is reserved with no profile | Recovery worker completes the profile or triggers controlled release |
| Profile written, response lost | Both tables may be valid while client doesn't know | Retry with same IDs; verify claim and profile match `request_id` before reporting success |
| Profile exists but claim belongs to wrong owner | Business invariant violated by out-of-protocol operation | Isolate, alert, investigate; never silently return success |
| User wants to change handle | Must claim new name and release old name | Use a multi-step rename workflow with a clear publication point and recovery |

A practical recovery strategy:

1. Persist **`request_id`, `account_id`, `tenant_id`, `handle_key`** in a durable request-processing store (e.g., a status table keyed by request ID and/or a replayable queue). Writing state across multiple partitions still has failure windows, so the workflow must be idempotent.
2. On timeout, **never** assume the write did not happen. Retry the claim with the exact same data; if the claim belongs to the same IDs, continue checking `accounts_by_id`.
3. If the profile is missing, create it with `IF NOT EXISTS`; if the profile already exists and matches the request, treat profile creation as complete.
4. Return "registration succeeded" only after verifying the required business state.
5. Run a reconciliation job for stuck requests using a **key-lookup journal/queue**, rather than scanning the entire claim table with `ALLOW FILTERING`.

**Never delete the claim immediately when writing the profile times out.** Writing the profile may have succeeded; deleting the claim at that moment could allow someone else to take the same name while the existing account still uses it.

### If Business Rules Allow Releasing Handles

To ensure only the expected owner can delete, use a **conditional delete** matching `account_id` and `request_id`:

~~~sql
DELETE FROM app.handle_claims
WHERE tenant_id = 'shop-7' AND handle_key = 'alice_01'
IF account_id = 22222222-2222-4222-8222-222222222222
   AND request_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
~~~

However, this condition **only guards deleting the claim**. It does not simultaneously invalidate login sessions or delete/update the profile in another partition. Rename/account-cancellation workflows must ensure a clear publication boundary and recoverability. If an old client might retry after a name is released and someone else claims it, use a **generation/fencing token** model or record completed request history to prevent stale operations from taking effect again. If names are **never reused**, it is simpler to **never delete claims** and retain the allocation ledger.

TTL is suitable only for **leases with an explicit expiration policy**. When a claim row expires automatically, ownership becomes available again while another system may still believe the old account is active. Never attach arbitrary TTLs to claims meant to enforce long-term uniqueness.

## 8. Designs That Fail to Deliver the Desired Guarantee

| Approach | Why It Is Insufficient | Replace With |
| --- | --- | --- |
| `SELECT` to check if name exists, then regular `INSERT` | Two clients both read "absent" and both create accounts | Claim with `INSERT ... IF NOT EXISTS` |
| Only assigning a UUID for `account_id` | Avoids ID collision probabilistically but does not prevent two accounts sharing one username | Claim table keyed by `(scope, canonical username)` |
| Creating a secondary index on username | Indexes aid lookups; they do not enforce a `UNIQUE` constraint | Guard the business key with LWT |
| `IF NOT EXISTS` on an account table partitioned by `account_id` | Condition only guards the account's ID; each request has a different ID | Claim on the contested username key |
| Packing all tenant handles into one partition | Risks exceeding partition size limits and creating hotspots on large tenants | Composite partition key `(tenant_id, handle_key)` |
| Using counters to issue gapless global IDs | Counters do not provide CAS-ordered, gapless sequencing across concurrent writers | Dedicated sequence service if strict/gapless is needed |
| Using `LOGGED BATCH` as a "transaction" across claim and profile | `BATCH` provides no general cross-partition isolation or conditional transaction | Idempotent workflow and reconciliation |
| Returning "name already taken" on LWT timeout | Timeouts do not tell whether the statement was applied | Retry/reconcile with the same `request_id` |
| Writing claims via LWT while another job uses regular upserts | The job can overwrite claim ownership without obeying CAS | Lock down write permissions and require all writers to use the same protocol |
| Using `LOCAL_SERIAL` from two DCs while claiming global uniqueness | Local Paxos scope does not prove cluster-wide uniqueness | Use `SERIAL` or a single coordinating region and test multi-DC |

## 9. Cost, Replication, and Availability

LWT requires more replica round trips than regular writes; latency and fault tolerance depend on Cassandra version, Paxos implementation, topology, and consistency levels. Therefore, do not put `IF NOT EXISTS` on every `INSERT` when you only need a low-collision UUID.

Operational guidelines:

1. **Replication**: use `NetworkTopologyStrategy` to place replicas across DCs/racks; a namespace with global uniqueness needs a topology capable of coordinating LWTs.
2. **Serial and regular consistency**: configure them separately and log/trace them. When replicas are insufficient for consensus, **never silently downgrade consistency** to bypass your committed guarantee.
3. **Contention**: a claim row for a popular name can receive many competing requests; monitor LWT latency, timeouts, retries, and `[applied] = false` rates.
4. **Secondary reads/writes**: profiles by `account_id` follow query-driven modeling. Eventual consistency, compaction, and repair still apply to replicated data; LWT does not exempt you from repair/maintenance or incident handling.
5. **Recovery**: a conditional request may reject or time out when replicas fail; this is the deliberate trade-off to avoid granting two owners the same name when state cannot be verified.

### Do Not Turn IDs into a Global Counter

For example, "every order system-wide must receive a contiguous integer incrementing by 1 with no gaps" is **fundamentally different** from "each ID is unique." Using a single partition to increment numbers via LWT creates a severe contention bottleneck, and lost client responses make gapless guarantees hard. For global/gapless ordering, choose a dedicated sequence architecture, renegotiate the gapless requirement, or allocate regional ranges if the domain permits; **never** promise that UUID/timeuuid, Cassandra counters, or standalone LWT solve it all.

## 10. Practical Testing: Two Clients Competing for One Handle

Test in a **lab** with enough nodes to satisfy your configured RF/consistency. Never test by mutating live production data. All requests must use **the same normalization**, namespace, and serial consistency configuration.

### Test Matrix

| Case | Concurrent Requests | Verifiable Expectation |
| --- | --- | --- |
| T1 — Same handle, same tenant | Clients A and B use **different** `account_id`/`request_id` for `(shop-7, alice_01)` | Only **one claim** gets `[applied] = true`; the other gets `false` or must retry after an indeterminate error; ultimately only one valid owner |
| T2 — Same handle, different tenants | A registers `(shop-7, alice_01)`, B registers `(shop-8, alice_01)` | Both can succeed, because scope is per-tenant |
| T3 — Different casing | A sends `"Alice_01"`, B sends `"ALICE_01"` | After normalization they contend on **the same key**; never two valid owners |
| T4 — Retry after timeout | Request A times out, then resends exact same `account_id`/`request_id` | Does not create a second owner; verifies A owns the claim and completes the profile |
| T5 — Crash after claim | A claims successfully, process crashes before writing `accounts_by_id` | Claim holds the name; reconciliation worker creates the profile or performs conditional cancellation |
| T6 — Two DCs | Two competing requests from different DCs | Never two winners if global guarantee model is configured properly; observe timeouts and failover behavior |
| T7 — Out-of-protocol write | A job runs regular upsert on the same claim | Flag this as a **process violation**, not an LWT guarantee failure |

### Execution Guide

1. Create the schema with CQL; verify RF, DC, node readiness, and `cqlsh` `CONSISTENCY`/`SERIAL CONSISTENCY` settings.
2. Synchronize the start time of two clients (e.g., a barrier in a Java program) to increase collision likelihood; millisecond clock perfection is unnecessary.
3. Each client sends **one** conditional insert with the same tenant/handle but different `request_id`/`account_id`. Record `[applied]`, timestamp, latency, exceptions, and `request_id`.
4. Query the claim at `(shop-7, alice_01)` at an appropriate consistency level and check the owner ID. If one client times out, retry/reconcile before counting owners.
5. Repeat enough times to observe contention; run T2–T5 as well. For T6, use a multi-DC lab with an explicit routing/serial-consistency design.
6. Reset test data cleanly; use distinct names for subsequent rounds or delete test data via conditional delete **in the lab only**.

**Pass criterion:** for each **`(scope, canonical ID)`** pair, every successful outcome after reconciliation converges to **at most one owner at a time**; `UNKNOWN` outcomes resolve to a known state without misallocating the handle; no profile is published contrary to the claim.

## 11. Self-Check Questions

1. Can two different `account_id` UUIDs both register the username `"alice"` if the accounts table uses `IF NOT EXISTS` only on `account_id`? Why?
2. Why does `PRIMARY KEY ((tenant_id, handle_key))` express **per-tenant** uniqueness, whereas `PRIMARY KEY (handle_key)` expresses a broader scope?
3. If `[applied] = false` yet `request_id` matches the previous attempt, what must the workflow do before returning success?
4. Why is losing an LWT response not enough to conclude the claim was not written?
5. Why must you not release the claim immediately when writing `accounts_by_id` times out?
6. When is a regular UUID v4 sufficient, and when do you need LWT to guard an ID?
7. Why don't a `LOGGED BATCH` or secondary index automatically enforce uniqueness across two independent partitions?

## 12. References

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): conditional `INSERT`/`UPDATE`/`DELETE`, `IF NOT EXISTS`, and `BATCH` semantics.
- [Apache Cassandra — Architecture Overview](https://cassandra.apache.org/doc/latest/cassandra/architecture/overview.html): partition-scoped compare-and-set and multi-partition transaction limits.
- [Apache Cassandra — Guarantees](https://cassandra.apache.org/doc/latest/cassandra/architecture/guarantees.html): Paxos-backed LWT model and linearizable consistency.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY` and `SERIAL CONSISTENCY`.
- [Java Driver 4.x — Statement API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html): `setConsistencyLevel` and `setSerialConsistencyLevel`.
- [Java Driver 4.x — ResultSet API](https://apache.github.io/cassandra-java-driver/4.10/api/com/datastax/oss/driver/api/core/cql/ResultSet.html): `wasApplied` when handling conditional statements.

**Key takeaway:** to guarantee unique identifiers in Cassandra, decide the **uniqueness scope first**, encode that scope into **a claim key that all writers contend on**, apply **LWT `IF NOT EXISTS`**, inspect **`[applied]`** accurately, and keep `request_id` identical across retries. Across multiple partitions and Java applications, add an explicit recovery workflow: LWT settles **who owns the name**, while the application is responsible for completing and reconciling the records derived from that ownership.
