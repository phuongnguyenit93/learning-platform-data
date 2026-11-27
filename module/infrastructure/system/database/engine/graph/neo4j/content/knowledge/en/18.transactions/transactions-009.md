# Testing Rollbacks and Preserving Business Invariants

In a Neo4j system, a transaction is more than a way to group multiple Cypher statements. It is also the boundary ensuring related changes are **committed together** or **rolled back together** on failure. If a transfer operation debits a source wallet, credits a destination wallet, and creates a transfer history record, completing only two of the three steps leaves the graph business-inconsistent.

This lesson belongs to the **Transactions** chapter of module `DATABASE_ENGINE_GRAPH_NEO4J`, where Neo4j is used to model a **property graph**, query nodes/relationships with Cypher, and build applications via the Java Driver or Spring Data Neo4j. The focus here is **testing rollbacks and proving that business invariants remain true after errors**, even when one transaction executes multiple writes.

After this lesson, you will be able to:

- State the **invariants**, preconditions, and postconditions of a transaction.
- Set up test data and distinguish **in-transaction** state from **committed** data.
- Test explicit `rollback()`, exception-triggered rollbacks, and constraint-violation rollbacks.
- Verify nodes, relationships, and aggregate totals after both success and failure.
- Recognize the limitations of single-threaded tests against concurrency bugs, retries, and commit-time connection drops.

## 1. What Must a Rollback Protect?

Consider a simple graph model:

~~~text
(:TxDemoWallet {walletId, balance})
       |                            ^
       | [:SENT]                    | [:RECEIVED_BY]
       v                            |
(:TxDemoTransfer {transferId, amount, status})
~~~

Each successful transfer creates a `TxDemoTransfer` node with a `SENT` relationship from the sender wallet and a `RECEIVED_BY` relationship to the recipient wallet. Examples use **integers** representing the smallest currency unit in the test system to avoid floating-point rounding errors.

Suppose two wallets initially hold:

| Wallet | `walletId` | `balance` before transaction |
| --- | --- | ---: |
| Sender wallet | `TX-A` | 1,000 |
| Recipient wallet | `TX-B` | 500 |
| **Total** | | **1,500** |

The transaction aims to transfer 200 units from TX-A to TX-B while recording a history node with ID `TX-TRANSFER-001`. **Invariants** are conditions that must always hold in committed data state.

| Code | Invariant / business rule | How to detect a violation |
| --- | --- | --- |
| I1 | Every wallet balance is non-negative. | Any `balance < 0` after commit. |
| I2 | Internal transfers neither create nor destroy money. | Total balance of **the two wallets in an isolated scenario** differs from 1,500. |
| I3 | Each `transferId` represents at most one persisted transfer record. | Two history nodes share the same ID. |
| I4 | A successful transfer record links to exactly one sender wallet and one recipient wallet. | Missing or extra `SENT` / `RECEIVED_BY` relationships. |
| I5 | When the operation fails, all related balances and graph structures remain in their pre-run state. | Any balance changed or new history node/relationship appeared. |

I2 applies only to **the isolated test wallets**, with no deposits, withdrawals, fees, or external modifications. If the system allows deposits, withdrawals, fees, exchange rates, or multi-wallet flows, expand the conservation equation to match those exact money flows. Never use total balance across the entire database as proof for one transaction when other valid concurrent writes are running.

**Preconditions** for a transfer also include: positive amount, both source and destination wallets exist, they are distinct, sufficient balance exists, and the transfer ID is valid and unused. Not every precondition can be expressed as a Neo4j constraint; some must be enforced in application flow with proper concurrency control.

## 2. ACID from a Testing Perspective

Neo4j supports ACID transactions. When writing tests, translate general properties into observable assertions:

| Property | What to observe | What a single test does not yet prove |
| --- | --- | --- |
| **Atomicity** | After rollback, none of the transaction's writes remain: balances, history nodes, relationships. | Concurrency safety across multiple transactions. |
| **Consistency** | Checked rules and constraints hold after commit; rule-violating transactions are rejected. | Business invariants that the application has neither defined nor verified. |
| **Isolation** | Other transactions cannot see uncommitted writes; concurrency tests produce valid outcomes. | That all concurrent schedules are serializable by default. |
| **Durability** | After a successful commit, data persists when read back from the appropriate database. | Recoverability across specific infrastructure failures if recovery procedures haven't been tested. |

Two cases to distinguish:

~~~text
SUCCESS                              FAILURE
BEGIN                                BEGIN
  Debit wallet TX-A                    Debit wallet TX-A
  Credit wallet TX-B                   Error before crediting TX-B
  Create TxDemoTransfer                ROLLBACK
  Create 2 relationships               |
COMMIT                                 v
  |                               Committed data:
  v                               A=1000, B=500,
A=800, B=700,                    no new transfer
transfer and 2 relationships exist
~~~

The key point is that **balances modified temporarily inside a transaction are not committed state**. Tests must finish the transaction and then read back from an independent read transaction to verify rollback behavior.

## 3. Setting Up Test Data on an Isolated Database

The commands below create and modify data. Run them on a **resettable test database**, never on production or a shared database. Each `CREATE CONSTRAINT` block is a separate Cypher statement.

### 3.1. Identity Constraints

~~~cypher
CREATE CONSTRAINT tx_demo_wallet_id_unique IF NOT EXISTS
FOR (w:TxDemoWallet)
REQUIRE w.walletId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT tx_demo_transfer_id_unique IF NOT EXISTS
FOR (t:TxDemoTransfer)
REQUIRE t.transferId IS UNIQUE;
~~~

These two uniqueness constraints prevent nodes with the same label from duplicating key values **when the key property is present**. They do not enforce that `walletId` or `transferId` must exist; if you need both mandatory and unique keys, add constraints appropriate for your Neo4j edition and version. Nor does Neo4j have a general check constraint in this example to enforce `balance >= 0` automatically.

### 3.2. Create Two Wallets in Initial State

~~~cypher
MERGE (a:TxDemoWallet {walletId: 'TX-A'})
MERGE (b:TxDemoWallet {walletId: 'TX-B'})
SET a.balance = 1000,
    b.balance = 500
RETURN a.walletId AS viGui, a.balance AS soDuGui,
       b.walletId AS viNhan, b.balance AS soDuNhan;
~~~

This example assumes the two test wallets have no existing history relationships to preserve. When rerunning the lab, manage any `TxDemoTransfer` nodes created in earlier runs; resetting balances **does not automatically delete history**. Clean up only the test data you own on the selected database.

### 3.3. Capture Initial State

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
OPTIONAL MATCH (t:TxDemoTransfer {transferId: 'TX-ROLLBACK-001'})
RETURN a.balance AS soDuA,
       b.balance AS soDuB,
       a.balance + b.balance AS tongHaiVi,
       count(t) AS soBanGhiThu;
~~~

Expected result before a clean rollback test: `soDuA = 1000`, `soDuB = 500`, total 1,500, and `soBanGhiThu = 0`. If `TX-ROLLBACK-001` already exists, use another fixture/ID or properly clean up test data; never accept an ambiguous initial state.

## 4. Defining a Graph Transfer Transaction

This Cypher statement expresses all three parts: updating both wallets, creating the history node, and creating two relationships:

~~~cypher
MATCH (sender:TxDemoWallet {walletId: $fromId})
MATCH (recipient:TxDemoWallet {walletId: $toId})
WHERE sender <> recipient
  AND $amount > 0
  AND sender.balance >= $amount
SET sender.balance = sender.balance - $amount,
    recipient.balance = recipient.balance + $amount
CREATE (transfer:TxDemoTransfer {
  transferId: $transferId,
  amount: $amount,
  status: 'COMPLETED'
})
CREATE (sender)-[:SENT]->(transfer)
CREATE (transfer)-[:RECEIVED_BY]->(recipient)
RETURN transfer.transferId AS transferId,
       sender.balance AS soDuGui,
       recipient.balance AS soDuNhan;
~~~

Example parameters:

| Parameter | Value |
| --- | --- |
| `$fromId` | `'TX-A'` |
| `$toId` | `'TX-B'` |
| `$amount` | `200` |
| `$transferId` | `'TX-ROLLBACK-001'` |

When executed successfully and **committed**, valid state is TX-A = 800, TX-B = 700, one `TxDemoTransfer` node, and exactly two relationships connecting the right wallets. If the amount is invalid, a wallet does not exist, or balance is insufficient, the `MATCH ... WHERE` pattern returns **0 rows**: the application must treat this as a **failed** transfer request rather than assuming an empty result means processed.

**Guarantee scope of the example:** a single write statement inside one transaction demonstrates atomicity, but does not prove the transfer flow is safe against all concurrent schedules. Evaluating `sender.balance >= $amount` can be affected by read timing and transaction contention; the concurrency testing section (Section 10) explains how to catch bugs. Real financial systems must have independently evaluated locking/serialization strategies, validation, idempotency, and ledgering.

## 5. Testing Explicit Rollback with the Neo4j Java Driver

The Java Driver supports **explicit transactions**: start with `beginTransaction()`, call `tx.run()`, then choose `commit()` or `rollback()`. This is ideal for testing a write that ran yet is **deliberately not committed**.

The example below uses `org.neo4j.driver.Driver` (Neo4j Java Driver 5.x API). It assumes the fixture from Section 3 is initialized and no transfer `TX-ROLLBACK-001` exists yet.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Transaction;

public final class ExplicitRollbackExample {
    private static final String TRANSFER = """
        MATCH (sender:TxDemoWallet {walletId: $fromId})
        MATCH (recipient:TxDemoWallet {walletId: $toId})
        WHERE sender <> recipient
          AND $amount > 0
          AND sender.balance >= $amount
        SET sender.balance = sender.balance - $amount,
            recipient.balance = recipient.balance + $amount
        CREATE (transfer:TxDemoTransfer {
          transferId: $transferId,
          amount: $amount,
          status: 'COMPLETED'
        })
        CREATE (sender)-[:SENT]->(transfer)
        CREATE (transfer)-[:RECEIVED_BY]->(recipient)
        RETURN transfer.transferId AS transferId
        """;

    public static void verifyExplicitRollback(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            try (Transaction tx = session.beginTransaction()) {
                Record result = tx.run(TRANSFER, Map.of(
                    "fromId", "TX-A",
                    "toId", "TX-B",
                    "amount", 200L,
                    "transferId", "TX-ROLLBACK-001"
                )).single();

                if (!"TX-ROLLBACK-001"
                        .equals(result.get("transferId").asString())) {
                    throw new AssertionError("Unexpected transaction result");
                }

                // Intentionally abort even after the Cypher statement has executed.
                tx.rollback();
            }

            Record balances = session.run("""
                MATCH (a:TxDemoWallet {walletId: 'TX-A'})
                MATCH (b:TxDemoWallet {walletId: 'TX-B'})
                RETURN a.balance AS a, b.balance AS b
                """).single();
            long a = balances.get("a").asLong();
            long b = balances.get("b").asLong();

            long events = session.run("""
                MATCH (t:TxDemoTransfer {
                  transferId: 'TX-ROLLBACK-001'
                })
                RETURN count(t) AS n
                """).single().get("n").asLong();

            if (a != 1000L || b != 500L || events != 0L) {
                throw new AssertionError(
                    "Incorrect rollback: A=" + a + ", B=" + b
                        + ", events=" + events
                );
            }
        }
    }
}
~~~

Points to note:

- Both balance updates and history creation run inside **the same `Transaction`**.
- `tx.rollback()` ends the transaction without publishing temporary writes.
- Verification happens **after rollback**; `session.run()` here executes a new read transaction on the same session.
- Do not assert only balances: assert history as well. Leftover relationship data is also an atomicity bug.
- The example assumes the database is named `neo4j` and no concurrent operations interfere with initial state. In a real test suite, use an isolated fixture and matching database name.

**Common mistake:** checking balances via `tx.run()` before `rollback()` and concluding data was persisted. A transaction is allowed to see its own uncommitted writes, so that check **does not prove data will survive after commit or disappear after rollback**.

## 6. Injecting Errors Between Steps to Test Exception Rollback

In practice, an exception can arise **after debiting funds yet before crediting**, or after creating history yet before committing. A worthwhile test must actively reproduce those situations.

### 6.1. Managed Transactions Automatically Roll Back When the Callback Fails

The Java Driver provides `session.executeWrite(...)` to manage write transactions and may retry **certain transient errors**. If the callback throws a non-retryable application exception, the transaction does not commit.

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class FaultInjectionExample {
    public static void rollbackAfterDebit(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            try {
                session.executeWrite(tx -> {
                    tx.run("""
                        MATCH (w:TxDemoWallet {walletId: 'TX-A'})
                        SET w.balance = w.balance - 200
                        """).consume();

                    // Simulate failure after the debit step.
                    throw new IllegalStateException("INJECTED_AFTER_DEBIT");
                });
                throw new AssertionError("Expected test exception");
            } catch (IllegalStateException ex) {
                if (!"INJECTED_AFTER_DEBIT".equals(ex.getMessage())) {
                    throw ex;
                }
            }

            long actual = session.run("""
                MATCH (w:TxDemoWallet {walletId: 'TX-A'})
                RETURN w.balance AS balance
                """).single().get("balance").asLong();

            if (actual != 1000L) {
                throw new AssertionError(
                    "TX-A balance changed after rollback: " + actual
                );
            }
        }
    }
}
~~~

This snippet illustrates only **a failure point right after a partial write**. It is not a complete transfer service. When run against a clean fixture, TX-A's balance remains 1,000 after the exception. In practice, snapshot pre-run state rather than hardcoding constants if tests may run with varying fixtures.

Never put **non-Neo4j** side effects such as sending emails, calling payment gateways, or publishing irreversible messages directly inside a managed callback without accounting for retries. The driver may re-invoke the callback on certain transient errors. Rolling back the graph does not recall sent emails or HTTP requests. When consistency between the DB and a message broker is required, consider the **transactional outbox** pattern, idempotency, and appropriate integration protocols.

### 6.2. Fault-Injection Points (*Failpoints*)

| Simulated failpoint | What executed before the error | Mandatory checks after rollback |
| --- | --- | --- |
| F0 — before writes | Input validation only. | Both wallets unchanged, no new transfer. |
| F1 — after debiting source | `SET sender.balance = ...` | TX-A back to initial value; TX-B and history unchanged. |
| F2 — after crediting target | Both balance updates. | Both wallets back to initial state; total preserved. |
| F3 — after creating history node | Balances updated and `TxDemoTransfer` created. | No new history node remains and no money lost. |
| F4 — after creating relationships | All changes created yet uncommitted. | No new nodes/relationships or balance updates remain. |
| F5 — constraint error | A write in the same transaction violates uniqueness. | All writes prior to the error are rolled back. |

You can implement failpoints F1–F4 by splitting operations into multiple `tx.run()` calls inside **one explicit transaction**, then intentionally throwing an exception or calling `rollback()` at the test point. Never run steps across separate auto-commit sessions/transactions: each step could commit individually, no longer testing single-transaction atomicity.

## 7. Testing Constraint Errors and Graph Integrity

The uniqueness constraint on `TxDemoTransfer.transferId` was created in Section 3. You can use it to test a database-level error causing the transaction to fail.

Prepare a fixed history node in the **test fixture** with a dedicated ID:

~~~cypher
MERGE (t:TxDemoTransfer {transferId: 'TX-DUPLICATE-001'})
ON CREATE SET t.amount = 1, t.status = 'TEST_SEED';
~~~

In the test, execute these steps inside **one transaction**:

1. Debit TX-A's balance as the first step of a transfer transaction.
2. Execute `CREATE (:TxDemoTransfer {transferId: 'TX-DUPLICATE-001'})`.
3. Verify step 2 is rejected by Neo4j because the ID already exists and the uniqueness constraint is active.
4. Roll back/close the transaction and read TX-A's balance in a new transaction: it must return to 1,000.

Cypher intentionally triggering the violation:

~~~cypher
CREATE (:TxDemoTransfer {
  transferId: 'TX-DUPLICATE-001',
  amount: 200,
  status: 'COMPLETED'
});
~~~

After a database exception, **do not keep writing inside the failed transaction hoping later operations will commit**. Handle errors at the transaction boundary; ensure the transaction is rolled back and released before re-checking.

Beyond uniqueness, you can verify relationship integrity on committed history:

~~~cypher
MATCH (t:TxDemoTransfer)
WHERE t.status = 'COMPLETED'
OPTIONAL MATCH (:TxDemoWallet)-[sent:SENT]->(t)
WITH t, count(sent) AS soQuanHeGui
OPTIONAL MATCH (t)-[received:RECEIVED_BY]->(:TxDemoWallet)
WITH t, soQuanHeGui, count(received) AS soQuanHeNhan
WHERE soQuanHeGui <> 1 OR soQuanHeNhan <> 1
RETURN t.transferId AS maChuyenTien,
       soQuanHeGui, soQuanHeNhan;
~~~

On the **test dataset created by this lesson**, the query should return 0 rows after valid commits. This is an application rule verified by query, not automatically a Neo4j constraint enforcing exact relationship cardinality. When both sides can hold multiple parallel relationships or the model does not bound edge multiplicity, design write operations and tests accordingly.

Check specifically for unwanted records after rollback:

~~~cypher
MATCH (t:TxDemoTransfer {transferId: 'TX-ROLLBACK-001'})
OPTIONAL MATCH ()-[s:SENT]->(t)
OPTIONAL MATCH (t)-[r:RECEIVED_BY]->()
RETURN count(DISTINCT t) AS soTransfer,
       count(DISTINCT s) AS soSent,
       count(DISTINCT r) AS soReceivedBy;
~~~

After rollback, all three counts must equal 0. Without node `t`, the two relationships incident to `t` cannot survive as dangling edges either: Neo4j never stores relationships without endpoints. Still, asserting all three counts makes test state crystal clear.

## 8. Testing a Successfully Committed Transaction

Rollback tests always need a **positive control**. A test that only proves "an error caused nothing to be written" can accidentally pass because the code never wrote anything in the first place.

Starting from TX-A=1000, TX-B=500, run the `TRANSFER` statement from Section 4 inside a transaction and **commit** with a dedicated ID `TX-COMMIT-001`. Then read from a new transaction:

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
MATCH (t:TxDemoTransfer {transferId: 'TX-COMMIT-001'})
MATCH (a)-[:SENT]->(t)-[:RECEIVED_BY]->(b)
RETURN a.balance AS soDuA,
       b.balance AS soDuB,
       a.balance + b.balance AS tongHaiVi,
       t.amount AS soTien,
       t.status AS trangThai;
~~~

The valid result is `soDuA=800`, `soDuB=700`, `tongHaiVi=1500`, `soTien=200`, and `trangThai='COMPLETED'`. Also verify the **count** of transfers with that ID is 1 and there is exactly one relationship of each type; a `MATCH` returning one row only shows a path exists and does not prove edge uniqueness if the model permits duplicate edges.

For rollback tests, create a **fresh fixture** or properly reset test wallets before each scenario. If you run a successful commit and then reuse that state for a rollback test expecting TX-A=1000, the test fails due to changed starting state, not because Neo4j rolled back improperly.

## 9. Spring Data Neo4j: Testing the Right Transaction Boundary

In Spring Data Neo4j applications, transactions are typically managed at the **service layer** via `@Transactional` paired with the Neo4j transaction manager. One service call can write multiple nodes and relationships; if any step throws a rollback-triggering exception, all changes in that transaction must be canceled.

Illustrative example:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TxDemoService {
    private final Neo4jClient client;

    public TxDemoService(Neo4jClient client) {
        this.client = client;
    }

    @Transactional
    public void debitThenFail() {
        client.query("""
            MATCH (w:TxDemoWallet {walletId: 'TX-A'})
            SET w.balance = w.balance - 200
            """).run();

        // Runtime exception triggers rollback under Spring's default rules.
        throw new IllegalStateException("INJECTED_AFTER_DEBIT");
    }
}
~~~

An integration test can invoke the **service bean through the Spring context**, catch the expected exception, and read data back in an independent transaction. Crucially, configure `Neo4jTransactionManager`/the transaction manager for the right database and ensure calls go through Spring's proxy/interceptor. Calling a `@Transactional` method from another method on **the same bean** (*self-invocation*) may bypass transaction proxying.

Distinguish two Spring rollback rules:

- By default, `@Transactional` marks rollback when a method throws a `RuntimeException` or `Error`.
- Checked exceptions like `IOException` may not trigger rollback by default; if business rules require it, configure `@Transactional(rollbackFor = IOException.class)` or use an appropriate exception model.

Also note: a test annotated with `@Transactional` at the **test-method level** in Spring Test is typically rolled back by the framework after the test finishes. That helps isolate fixtures, yet can mask whether application code actually commits when run outside tests. Write separate tests confirming **successful commit** and failure tests reading state in an independent transaction, avoiding reading uncommitted data inside the same context.

If a business operation also writes to another system (RDBMS, Kafka, HTTP), Neo4j transaction annotations **do not automatically provide distributed ACID** across those systems. Design compensation, outbox, or saga patterns per consistency requirements.

## 10. Concurrency Testing, Retries, and Uncertain Commit Outcomes

Single-threaded F0–F5 tests are essential yet **do not prove** transfers remain correct when multiple transactions execute concurrently.

### 10.1. Two Transactions Concurrently Debiting One Wallet

Suppose TX-A holds 1,000, and two concurrent requests each try to transfer **700** from TX-A to different wallets. If both read balance 1,000 before proper write synchronization takes effect, the system risks accepting both or updating from stale data.

Tests should use a barrier so two workers start nearly simultaneously, run multiple rounds, and then verify:

1. No wallet holds a negative balance.
2. Total balance across participating wallets remains accurate (when no external flows occur).
3. No `COMPLETED` history exists for a transfer whose balance entries were not committed.
4. Count of successful transactions matches actual balances, rather than trusting an API success message if the DB rolled back.

To enforce "sufficient balance," define and implement an **appropriate locking/serialization strategy**, re-read values after winning write access if the workflow demands, and test under load. **Do not assume `WHERE sender.balance >= $amount` from the single-threaded example prevents all race conditions.** Neo4j locks on writes, yet condition evaluation timing, query plans, and transaction contention must still be analyzed on real queries.

When multiple nodes are updated, standardize lock acquisition order or use an equivalent strategy to reduce deadlock risk. When the driver reports a retryable transient error, distinguish retrying **the whole transaction** from retrying a loose statement that already triggered external side effects.

### 10.2. Retries and Idempotency

A transfer request may be resent due to client timeouts or network errors. If the client **never receives the commit response**, it cannot automatically conclude the transaction rolled back; the commit may have succeeded while the response was lost.

Therefore, attach a stable `transferId` to each request and check persisted state to reconcile outcomes after uncertain failures. A uniqueness constraint prevents two history nodes with the same ID, yet by itself is not enough for an idempotent transfer API: the system must also return the prior outcome cleanly without repeating ledger entries, handle parameter mismatches for the same request ID, and handle in-flight states.

Important test scenarios:

| Scenario | Expectation |
| --- | --- |
| Calling the same `transferId` twice with identical parameters | Does not transfer twice; recognizes and returns already-processed result. |
| Calling the same ID with a different amount | Detects idempotency conflict; refuses to record mismatched writes. |
| Pre-commit error confirmed rolled back | Zero committed changes; eligible to retry per policy. |
| Connection drop right at commit time | Initial status is **unknown** to the client; look up by request ID before replaying. |
| Managed callback retried on transient error | Neo4j writes in the rolled-back attempt leave no trace; external DB side effects remain controlled. |

In a Neo4j cluster, when verifying read-after-write across a different session, configure causal consistency via appropriate Driver/bookmark settings to avoid confusion from reading across cluster members. Never cite a read that missed data as proof of rollback unless causal visibility guarantees were met.

### 10.3. Batch Transactions Are Not One Large Transaction

Some ingestion jobs use `CALL { ... } IN TRANSACTIONS` to split processing into batch transactions. When a later batch fails, **earlier batches may already have committed**. Never use batching for business operations requiring "all-or-nothing" across every element without dedicated recovery design.

## 11. Test Matrix and Fixture Organization

Maintain an automated test suite running against an **isolated database**, resetting data to a known state before each scenario. Minimum matrix:

| ID | Case | Assertions required |
| --- | --- | --- |
| T01 | Transfer 200 succeeds and commits | A=800, B=700, total=1500, one transfer, valid relationships. |
| T02 | Call `rollback()` after all Cypher executes | A=1000, B=500, no test transfer record. |
| T03 | Exception after debiting | Both balances and all history unchanged. |
| T04 | Exception after creating history node | New node and relationships do not exist after rollback. |
| T05 | Uniqueness violation mid-transaction | All writes before error discarded; expected exception type observed. |
| T06 | Zero or negative amount | Service rejects; zero changes committed. |
| T07 | Insufficient balance | No transfer/completed history; balances unchanged. |
| T08 | Sender equals recipient, or missing endpoint | Transaction fails; no partial writes. |
| T09 | Two concurrent requests on the same balance | Invariants and concurrency outcomes remain valid. |
| T10 | Retry with the same transaction ID | Does not transfer twice. |
| T11 | Commit timeout / lost response | State reconcilable by `transferId`; never assume rollback. |
| T12 | Spring app throws checked/runtime exception | Rollback matches `@Transactional` configuration. |

A test organization template:

~~~text
beforeEach:
  - prepare isolated database/fixture
  - create 2 wallets A=1000, B=500 and identifier constraints
  - verify no transfer belonging to current test exists

test:
  - capture snapshot of balances, node counts, and relevant relationship counts
  - call the right transaction API (explicit tx or service)
  - trigger error at failpoint or commit successfully
  - wait for transaction completion and read via an independent transaction
  - assert balances, total, transfer, relationships, and expected error

afterEach:
  - clean up only this test's fixture
  - do not delete nodes/relationships outside owned scope
~~~

**Value of testing:** comparing **before/after** snapshots catches "no exception thrown yet balance changed wrongly." Never use global database node counts as an oracle when concurrent writes exist; key isolated fixtures uniquely and query only the target group.

### 11.1. Query to Audit Balance Invariants

~~~cypher
MATCH (w:TxDemoWallet)
WHERE w.walletId IN ['TX-A', 'TX-B']
RETURN count(w) AS soVi,
       sum(w.balance) AS tongSoDu,
       min(w.balance) AS soDuThapNhat;
~~~

On the two-wallet fixture: `soVi = 2`, `tongSoDu = 1500`, `soDuThapNhat >= 0`. **Check the wallet count** before accepting the sum: if one node was deleted, `sum()` could still return a number plausible for a different set. If `balance` is missing/`null`, `sum` and `min` may skip values; assert every wallet has valid non-null properties of the expected integer type.

### 11.2. Query to Audit Complete Transfer Endpoints

~~~cypher
MATCH (t:TxDemoTransfer {transferId: $transferId})
OPTIONAL MATCH (source:TxDemoWallet)-[:SENT]->(t)
WITH t, count(source) AS senderCount
OPTIONAL MATCH (t)-[:RECEIVED_BY]->(target:TxDemoWallet)
RETURN t.transferId AS transferId,
       senderCount,
       count(target) AS recipientCount;
~~~

On a **successful commit**, expect one row with `senderCount = 1` and `recipientCount = 1`. On **rollback**, `MATCH (t ... )` returns 0 rows; that is a different expectation and must be asserted properly. For models permitting multiple parallel relationships to the same wallet, count relationships instead of only nodes and verify endpoints match the transfer request.

## 12. Common Pitfalls in Interpreting Test Results

| Observation | Hasty conclusion to avoid | Accurate verification |
| --- | --- | --- |
| `tx.run()` returns updated balances | "Committed successfully." | Conclude only after `commit()` and re-reading in a consistent context. |
| Callback throws an exception | "Guaranteed rollback and zero side effects." | Re-read nodes/relationships; verify external DB side effects separately. |
| Test finishes with a clean DB | "Service rolled back properly." | Check whether the test framework auto-rolled back an outer test transaction. |
| No new history node found | "The entire transaction rolled back." | Check balances and related relationships too. |
| `sum(balance)` matches old value | "No data corruption." | Check each wallet, wallet count, property validity, history, and edges. |
| Client lost connection at commit | "Transaction failed." | Reconcile by request ID on the database with proper read consistency. |
| One run of two concurrent requests succeeded | "System has no race conditions." | Run barrier-synchronized concurrency tests across interleavings and check invariants. |
| Constraint violation threw an error | "All business rules are protected." | Distinguish Neo4j constraints from service-level business preconditions. |

## 13. Hands-On Exercises

**Exercise 1 — Proving rollback:** Create the TX-A/TX-B fixture from Section 3. Inside an explicit transaction, debit 200, credit 200, create transfer `TX-EXERCISE-01`, and call `rollback()`. Capture before/after snapshots using Cypher queries and explain why a read *inside* the transaction is insufficient to prove rollback.

**Exercise 2 — Three failpoints:** Write a test method accepting a `failpoint` parameter. Use `AFTER_DEBIT`, `AFTER_CREDIT`, and `AFTER_TRANSFER_CREATE` to throw exceptions at three different points in the same transaction. Initialize an independent fixture per run and re-verify at least I1, I2, I4, and I5.

**Exercise 3 — Uniqueness error:** Pre-create `TxDemoTransfer {transferId:'TX-DUPLICATE-001'}` on the test database; open a new transaction, debit a balance, and attempt to create a transfer with the same ID. Verify the constraint error and prove the balance debit was not committed.

**Exercise 4 — Concurrency:** Two requests simultaneously transfer 700 from a wallet holding 1,000. List all allowed outcomes under the rule "non-negative, total conserved, log recorded for every committed transfer," then design a barrier-based test to catch invalid updates. Describe the locking/serialization mechanism you would use in production and why sequential tests alone are insufficient.

**Exercise 5 — Lost commit response:** A client sends request `TX-RETRY-09`, but loses connection right at commit time. Design the reconciliation step and idempotency rules so funds are never transferred twice, even if the same ID is resent with a different amount.

Minimal post-rollback verification query:

~~~cypher
MATCH (a:TxDemoWallet {walletId: 'TX-A'})
MATCH (b:TxDemoWallet {walletId: 'TX-B'})
OPTIONAL MATCH (t:TxDemoTransfer {transferId: $transferId})
RETURN a.balance AS aBalance,
       b.balance AS bBalance,
       a.balance + b.balance AS total,
       count(t) AS transferCount;
~~~

Expected values on the initial fixture are `aBalance=1000`, `bBalance=500`, `total=1500`, and `transferCount=0`. From there, check the remaining relationships and specific conditions of each exercise.

**Core principle:** rollback testing only has real meaning once you have defined **which invariants must hold** and **which writes must share a single transaction**. Test successful commits, pre-commit failpoints, database exceptions, retries, and concurrent contention; always read committed data back in an independent context for clear proof that the property graph remains valid.
