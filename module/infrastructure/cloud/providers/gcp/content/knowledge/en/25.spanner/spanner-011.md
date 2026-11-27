# Hands-On Transaction Ledger Design on Spanner

A Java e-wallet needs to transfer $25.00 from account A to B. If the application deducts from A successfully but fails to credit B, the data becomes corrupt. If the client resends the same request after a timeout, the system could transfer the money **twice**. This hands-on lab uses **Google Cloud Spanner** to build a *simple double-entry ledger*: every transfer creates two equal-and-opposite entry rows while updating both balances inside **one read-write transaction**.

This lesson belongs to the **Spanner** chapter of the **CLOUD_PROVIDERS_GCP** module: learning how to choose databases, secure resources with IAM, deploy Java services on Cloud Run/GKE, automate releases, and monitor reliability alongside cost. The focus is on **data design and safe transaction execution**, not a full financial accounting manual.

After this lesson, you will be able to:

- Define double-entry invariants, idempotency, atomicity, and non-negative balance rules.
- Design a GoogleSQL schema containing `Accounts`, `Transfers`, and `LedgerEntries`, avoiding sequential keys.
- Use Spanner read-write transactions to write two ledger entries and update two balances together.
- Write a Java client using **ADC**, `TransactionRunner`, parameterized DML, and retry/commit-timestamp handling.
- Verify with SQL: net-zero entry sums, balance reconciliation, duplicate detection, and history queries.
- Identify limitations of monetary ledgers, hot-account contention, index hotspots, IAM, and cost.
- Test concurrent transactions, request timeouts, cross-tenant misuse, and remediation/rollback plans.

> **Safety:** This is a training model, **not an audited or compliance-certified payment system**. Never use real monetary data. Every command creating a Spanner instance can incur charges; run only in an authorized lab project.

## 1. Double-Entry Invariants and Lab Scope

For an internal transfer in the same currency:

~~~text
Before transaction:
  A = 100.00 USD = 10,000 cents
  B =   5.00 USD =    500 cents

Transfer 25.00 USD (2,500 cents):
  LedgerEntries:
    A: -2500
    B: +2500

After commit:
  A =  7,500 cents =  75.00 USD
  B =  3,000 cents =  30.00 USD

Sum of deltas: (-2500) + (+2500) = 0
~~~

Four core invariants:

1. **Balanced:** every transfer has **exactly two** entries, in the same currency, one negative and one positive, summing to `DeltaMinor = 0`.
2. **Atomic:** updating `BalanceMinor` for A/B and inserting both ledger entries **commit together or roll back together**.
3. **No overdrafts:** the source account transfers only when its status is valid and balance is sufficient. For businesses allowing overdrafts, model that as an explicit rule rather than blindly disabling negative checks.
4. **Idempotency:** resending the same `RequestId` with the **same payload** never transfers again; reusing `RequestId` with a different payload must be rejected.

**Terminology convention:** `DeltaMinor < 0` means decreasing the source balance, while `DeltaMinor > 0` means increasing the destination balance. This models **transfers between two accounts of the same type**; in general accounting, "debit"/"credit" depend on account classification and signs should not be mechanically equated to Debit/Credit. **Cross-currency** transfers require exchange rates, clearing accounts, and FX workflows—you cannot simply record `-100 USD` and `+100 EUR` and treat them as balanced.

### Why Use Minor Currency Units?

`AmountMinor INT64` stores integers in the currency's *minor unit*: USD uses cents (2 decimal places), while VND typically uses dong (0 decimal places). This avoids `FLOAT64` rounding errors and enables exact balance comparisons. For invoices/interest needing different precision or scale, consider `NUMERIC` (exact decimal within Spanner's limits), rounding rules, and overflow checks; **never use floating point** for money.

## 2. Data Design: Three Tables and One Index

~~~mermaid
flowchart LR
  A["Accounts<br/>AccountId PK<br/>OpeningBalanceMinor<br/>BalanceMinor"] 
  T["Transfers<br/>RequestId PK<br/>AmountMinor<br/>PostedAt"]
  L["LedgerEntries<br/>RequestId + LineNo PK<br/>AccountId, DeltaMinor"]
  T -->|"each transfer has 2 entries"| L
  L -->|"entries for"| A
~~~

| Table | Purpose | Design Notes |
|---|---|---|
| `Accounts` | Current balance and audited opening balance | Never rely on cached balances as the sole source of truth |
| `Transfers` | One unique transfer document per `RequestId` | PK prevents duplicate documents; stores payload to catch mismatched key reuse |
| `LedgerEntries` | Two immutable entries per transfer | Key `(RequestId, LineNo)` and signed `DeltaMinor` |
| `LedgerEntriesByAccount` | Look up entries by account | Add indexes when read patterns require them; monitor write amplification |

`RequestId` must be a UUID v4 or **randomly distributed, globally unique** identifier generated **before** invoking the transaction and reused on retries. Never use commit timestamps or ascending sequences as the leading primary key prefix in high-write tables, as that creates **hotspots** on one key range.

To ease reconciliation of data migrated from legacy systems, `Accounts` includes `OpeningBalanceMinor`. In the lab, two accounts are **seeded** with approved opening balances. In new products, designing **audited opening journal entries** is preferable; never let users edit opening balances freely. Reconciliation must sum the opening balance plus every movement since opening.

### GoogleSQL DDL

Save as `schema.sql` inside your **dedicated lab directory**. This is the **Spanner GoogleSQL dialect**, not the PostgreSQL dialect.

~~~sql
CREATE TABLE Accounts (
  AccountId STRING(36) NOT NULL,
  TenantId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  OpeningBalanceMinor INT64 NOT NULL,
  BalanceMinor INT64 NOT NULL,
  Status STRING(16) NOT NULL,
  CONSTRAINT balance_not_negative CHECK (BalanceMinor >= 0)
) PRIMARY KEY (AccountId);

CREATE TABLE Transfers (
  RequestId STRING(36) NOT NULL,
  TenantId STRING(36) NOT NULL,
  SourceAccountId STRING(36) NOT NULL,
  DestinationAccountId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  AmountMinor INT64 NOT NULL,
  PostedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT positive_transfer CHECK (AmountMinor > 0),
  CONSTRAINT distinct_accounts CHECK (SourceAccountId != DestinationAccountId)
) PRIMARY KEY (RequestId);

CREATE TABLE LedgerEntries (
  RequestId STRING(36) NOT NULL,
  LineNo INT64 NOT NULL,
  TenantId STRING(36) NOT NULL,
  AccountId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  DeltaMinor INT64 NOT NULL,
  CONSTRAINT nonzero_entry CHECK (DeltaMinor != 0)
) PRIMARY KEY (RequestId, LineNo);

CREATE INDEX LedgerEntriesByAccount
ON LedgerEntries (AccountId, RequestId)
STORING (DeltaMinor, TenantId, Currency);
~~~

**Data-protection limits in this schema:** `CHECK` constraints validate values **within a single row**, not "two entries sharing a `RequestId` must sum to 0." Cross-row invariants must be enforced in the **transaction write path** and verified via **reconciliation**. Production should add write-path isolation (never grant direct DML to multiple arbitrary apps), tenant-scoped read authorization, auditing, and *compensating entry* correction workflows.

**Why not put `PostedAt` first in the primary key?** Monotonically increasing timestamps funnel inserts to the tail of the key range and cause hotspots. Random `RequestId` spreads writes; `PostedAt` stores the **commit timestamp** for auditing/ordering. A global timestamp secondary index can also become a hotspot; add one only when truly needed with a partitioning strategy.

## 3. Provisioning the Spanner Instance/Database and Test Data

The lab uses the Singapore regional configuration; pick an instance configuration **actually supported** in your project/edition and consider data residency. Requires billing, appropriate Spanner Instance Admin/Database Admin permissions, `gcloud`, and Java 17+.

~~~bash
PROJECT_ID="my-spanner-ledger-lab"
INSTANCE="ledger-lab"
DATABASE="ledger"

gcloud config set project "$PROJECT_ID"
gcloud services enable spanner.googleapis.com

# Testing: create a new instance only in a lab project.
gcloud spanner instances create "$INSTANCE" \
  --config="regional-asia-southeast1" \
  --description="Double-entry ledger lab" \
  --processing-units=100

gcloud spanner databases create "$DATABASE" \
  --instance="$INSTANCE" \
  --database-dialect=GOOGLE_STANDARD_SQL

gcloud spanner databases ddl update "$DATABASE" \
  --instance="$INSTANCE" \
  --ddl-file="schema.sql"

# Read-only schema check; wait for DDL operation to finish before writing.
gcloud spanner databases ddl describe "$DATABASE" \
  --instance="$INSTANCE"
~~~

**Note:** processing units and edition determine minimum capacity and feature support; if `100 PU` is unavailable in your project/edition, select a permitted size per current docs/quotas. Never switch to a production instance just "for a quick test."

### Seeding Opening Data

Use **two fixed UUID v4s for the lab** (never use the IDs below in production). Assume opening balances come from an audited legacy system snapshot:

~~~text
Tenant: tenant-demo
A: 782e6ff2-965e-4668-960a-10493863f5c2
B: 3f4cbb77-3a16-467f-b357-0c5573a047ed
Currency: USD
Opening balances: 10000 cents and 500 cents
~~~

~~~sql
INSERT INTO Accounts (
  AccountId, TenantId, Currency,
  OpeningBalanceMinor, BalanceMinor, Status
)
VALUES
  ("782e6ff2-965e-4668-960a-10493863f5c2",
   "tenant-demo", "USD", 10000, 10000, "ACTIVE"),
  ("3f4cbb77-3a16-467f-b357-0c5573a047ed",
   "tenant-demo", "USD", 500, 500, "ACTIVE");
~~~

In Spanner Studio, execute the seed SQL **once** in the lab database. You can also run DML via `gcloud spanner databases execute-sql` with `--sql` if supported by your CLI version. Never use `INSERT OR UPDATE` or `INSERT OR IGNORE` to overwrite seeds accidentally; DML `INSERT` should fail if the data already exists.

**Opening balances are not money created out of thin air:** in a full accounting system, opening balances must reconcile against equity, liabilities, and migration records. This lesson only tracks **movements after the snapshot**, which is why the reconciliation formula includes `OpeningBalanceMinor`.

## 4. Java: Posting Entries Inside One Read-Write Transaction

The single authoritative write path: **authenticate tenant at HTTP/API layer → validate inputs → check idempotency → read both Accounts → compute new balances → update two Accounts, insert two LedgerEntries, insert one Transfer → commit**. Never place Pub/Sub publishes or payment HTTP calls **inside the transaction callback**, as Spanner can re-execute the callback on `ABORTED`.

### Dependency and Application Default Credentials

Examples use Java 17+ and `com.google.cloud:google-cloud-spanner`. With Maven, declare the dependency below in a Java project configured with an appropriate build plugin:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-spanner</artifactId>
    <version>6.124.0</version>
  </dependency>
</dependencies>
~~~

The version above illustrates a 6.x API release, not a permanent pin; real projects should select a supported version via the Google Cloud Libraries BOM and test it. When running on Cloud Run/GKE, the client uses the runtime service account's **ADC**; locally, run `gcloud auth application-default login` in the lab project.

### `LedgerDemo` Class: Reading, Updating, and Preventing Duplicate Transfers

Place the file at `src/main/java/example/LedgerDemo.java`. Imports, types, and the write path are complete enough to drop into a Maven project:

~~~java
package example;

import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.TransactionContext;
import java.util.UUID;

public final class LedgerDemo {
    private final DatabaseClient db;

    public LedgerDemo(DatabaseClient db) {
        this.db = db;
    }

    public record Request(
        String requestId, String tenantId, String from, String to,
        String currency, long amountMinor) {}

    public record Receipt(String requestId, String status) {}

    private record Account(
        String tenantId, String currency, String status, long balanceMinor) {}

    public Receipt transfer(Request r) {
        // Validate input data and tenant permissions at the API boundary.
        if (r.amountMinor() <= 0 || r.from().equals(r.to())
                || UUID.fromString(r.requestId()).version() != 4) {
            throw new IllegalArgumentException("Invalid transfer request");
        }

        // TransactionRunner may re-invoke the callback after ABORTED.
        return db.readWriteTransaction().run(tx -> {
            // 1. RequestId is the idempotency key; if already recorded, compare payload.
            Statement existingQuery = Statement.newBuilder(
                "SELECT TenantId, SourceAccountId, DestinationAccountId, "
                + "Currency, AmountMinor FROM Transfers "
                + "WHERE RequestId = @requestId")
                .bind("requestId").to(r.requestId())
                .build();
            try (ResultSet existing = tx.executeQuery(existingQuery)) {
                if (existing.next()) {
                    boolean samePayload =
                        existing.getString("TenantId").equals(r.tenantId())
                        && existing.getString("SourceAccountId").equals(r.from())
                        && existing.getString("DestinationAccountId").equals(r.to())
                        && existing.getString("Currency").equals(r.currency())
                        && existing.getLong("AmountMinor") == r.amountMinor();
                    if (!samePayload) {
                        throw new IllegalArgumentException(
                            "Idempotency key reused with different payload");
                    }
                    return new Receipt(r.requestId(), "ALREADY_POSTED");
                }
            }

            // 2. Read both accounts in the same transaction.
            Account source = getAccount(tx, r.from());
            Account destination = getAccount(tx, r.to());
            requireActive(source, r);
            requireActive(destination, r);

            long newSource = Math.subtractExact(
                source.balanceMinor(), r.amountMinor());
            long newDestination = Math.addExact(
                destination.balanceMinor(), r.amountMinor());
            if (newSource < 0) {
                throw new IllegalArgumentException("Insufficient funds");
            }

            // 3. Both balance updates run inside the SAME transaction.
            updateBalance(tx, r.from(), newSource);
            updateBalance(tx, r.to(), newDestination);

            // 4. Two opposite-signed entries sharing RequestId/Currency.
            insertEntry(tx, r, 1L, r.from(), -r.amountMinor());
            insertEntry(tx, r, 2L, r.to(), r.amountMinor());

            // 5. Write transfer record with commit timestamp in the FINAL DML STATEMENT.
            // Do not re-read Transfers after PENDING_COMMIT_TIMESTAMP().
            mustWriteOne(tx, Statement.newBuilder("""
                INSERT INTO Transfers (
                    RequestId, TenantId, SourceAccountId,
                    DestinationAccountId, Currency, AmountMinor, PostedAt
                ) VALUES (
                    @requestId, @tenantId, @sourceId,
                    @targetId, @currency, @amount, PENDING_COMMIT_TIMESTAMP()
                )
                """)
                .bind("requestId").to(r.requestId())
                .bind("tenantId").to(r.tenantId())
                .bind("sourceId").to(r.from())
                .bind("targetId").to(r.to())
                .bind("currency").to(r.currency())
                .bind("amount").to(r.amountMinor())
                .build());

            // Result is only returned to the caller after commit succeeds.
            return new Receipt(r.requestId(), "POSTED");
        });
    }

    private static Account getAccount(TransactionContext tx, String id) {
        Statement q = Statement.newBuilder("""
            SELECT TenantId, Currency, Status, BalanceMinor
            FROM Accounts WHERE AccountId = @accountId
            """)
            .bind("accountId").to(id)
            .build();
        try (ResultSet rows = tx.executeQuery(q)) {
            if (!rows.next()) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                rows.getString("TenantId"),
                rows.getString("Currency"),
                rows.getString("Status"),
                rows.getLong("BalanceMinor"));
        }
    }

    private static void requireActive(Account a, Request r) {
        if (!a.tenantId().equals(r.tenantId())
                || !a.currency().equals(r.currency())
                || !a.status().equals("ACTIVE")) {
            throw new IllegalArgumentException(
                "Account not permitted or wrong currency");
        }
    }

    private static void updateBalance(
            TransactionContext tx, String accountId, long newBalance) {
        mustWriteOne(tx, Statement.newBuilder("""
            UPDATE Accounts SET BalanceMinor = @balance
            WHERE AccountId = @accountId
            """)
            .bind("balance").to(newBalance)
            .bind("accountId").to(accountId)
            .build());
    }

    private static void insertEntry(
            TransactionContext tx, Request r, long lineNo,
            String accountId, long signedDelta) {
        mustWriteOne(tx, Statement.newBuilder("""
            INSERT INTO LedgerEntries (
                RequestId, LineNo, TenantId, AccountId,
                Currency, DeltaMinor
            ) VALUES (
                @requestId, @lineNo, @tenantId, @accountId,
                @currency, @delta
            )
            """)
            .bind("requestId").to(r.requestId())
            .bind("lineNo").to(lineNo)
            .bind("tenantId").to(r.tenantId())
            .bind("accountId").to(accountId)
            .bind("currency").to(r.currency())
            .bind("delta").to(signedDelta)
            .build());
    }

    private static void mustWriteOne(
            TransactionContext tx, Statement statement) {
        if (tx.executeUpdate(statement) != 1L) {
            throw new IllegalStateException("Expected exactly one row");
        }
    }

    public static void main(String[] args) {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID INSTANCE_ID DATABASE_ID REQUEST_UUID_V4");
        }
        String project = args[0];
        String instance = args[1];
        String database = args[2];
        String requestId = args[3];
        Spanner spanner = SpannerOptions.newBuilder()
            .setProjectId(project).build().getService();
        try {
            DatabaseClient client = spanner.getDatabaseClient(
                DatabaseId.of(project, instance, database));
            Request req = new Request(
                requestId, "tenant-demo",
                "782e6ff2-965e-4668-960a-10493863f5c2",
                "3f4cbb77-3a16-467f-b357-0c5573a047ed",
                "USD", 2500L);
            Receipt receipt = new LedgerDemo(client).transfer(req);
            System.out.println(receipt);
        } finally {
            spanner.close();
        }
    }
}
~~~

Key points:

- Spanner's `TransactionRunner` **automatically retries transactions on `ABORTED`**, so the callback must have **no external side effects outside Spanner**, such as sending emails or calling payment APIs inside it.
- `SELECT Transfers WHERE RequestId = ...` and `INSERT Transfers` live in the same transaction, letting serializable isolation resolve racing requests; the primary key ensures no two documents share an ID. On timeout/race errors, the caller can **query `Transfers` by `RequestId`** before deciding to resend.
- `PENDING_COMMIT_TIMESTAMP()` is a DML expression replaced by Spanner with the commit timestamp; it cannot be used like a normal `CURRENT_TIMESTAMP()`. Once called, do not re-read the affected table in the same transaction—which is why **the `Transfers` write is placed last**.
- `Math.subtractExact` and `Math.addExact` catch `INT64` overflow in Java instead of silently corrupting amounts; input validation must also check ID lengths, currency codes, and caller authentication before calling `transfer`.
- In this pattern, `Accounts` is updated with DML; never mix DML and mutations without understanding ordering and visibility rules.

### Running Java in the Lab Project

Learners need the Java source file, a `pom.xml` with the dependency, and an execution plugin configured. You can use the Maven Exec Plugin configured in the project:

~~~bash
# Requires application ADC when running LOCALLY (do not run on Cloud Run):
gcloud auth application-default login

# Keep the exact same UUID when retrying; DO NOT generate a new UUID for retries.
REQUEST_ID="5fe632ac-e86b-49f5-8f83-ac429bb278df"

mvn -q compile exec:java \
  -Dexec.mainClass=example.LedgerDemo \
  -Dexec.args="my-spanner-ledger-lab ledger-lab ledger $REQUEST_ID"
~~~

The first run expects `Receipt[..., status=POSTED]`; running **the exact same command** again expects `ALREADY_POSTED`, with no extra deduction. If running on an environment already seeded or holding prior transactions, query balances and the journal beforehand to avoid misinterpreting results.

## 5. Reading the Ledger and Reconciling Data with SQL

Spanner supports **strongly consistent reads**; a read-only transaction can read a consistent snapshot across multiple tables, whereas read-write transactions default to **serializable/external consistency**. Reading two balances via two separate requests without a shared snapshot can observe two different instants, so **ledger reporting requires consistent snapshots** for audit reports.

### Verifying Balances, Transfer, and Entries

After a 2,500-cent transfer from A to B:

~~~sql
-- Expected: A = 7500, B = 3000.
SELECT AccountId, Currency, OpeningBalanceMinor, BalanceMinor
FROM Accounts
WHERE TenantId = "tenant-demo"
ORDER BY AccountId;

-- Transfer record, commit timestamp, and payload for deduplication.
SELECT RequestId, SourceAccountId, DestinationAccountId,
       Currency, AmountMinor, PostedAt
FROM Transfers
WHERE RequestId = "5fe632ac-e86b-49f5-8f83-ac429bb278df";

-- Two entries sharing RequestId.
SELECT RequestId, LineNo, AccountId, DeltaMinor, Currency
FROM LedgerEntries
WHERE RequestId = "5fe632ac-e86b-49f5-8f83-ac429bb278df"
ORDER BY LineNo;
~~~

| Check | Value After First Send | After Resending Same ID |
|---|---:|---:|
| Balance A | 7,500 cents | 7,500 cents |
| Balance B | 3,000 cents | 3,000 cents |
| Transfer documents with that RequestId | 1 | 1 |
| `LedgerEntries` rows for RequestId | 2 | 2 |
| Sum of `DeltaMinor` across both entries | 0 | 0 |

### Reconciling Net Movement per Transfer

~~~sql
-- Returns transfer records with missing lines, extra lines, or imbalance.
-- Expected result: 0 rows for valid data.
SELECT
  t.RequestId,
  COUNT(e.LineNo) AS EntryCount,
  IFNULL(SUM(e.DeltaMinor), 0) AS NetMinor
FROM Transfers AS t
LEFT JOIN LedgerEntries AS e ON t.RequestId = e.RequestId
GROUP BY t.RequestId
HAVING COUNT(e.LineNo) != 2
   OR IFNULL(SUM(e.DeltaMinor), 0) != 0;
~~~

This query also needs extending to verify **exact source/destination accounts, tenant, currency, and signs** for each entry. Having two lines summing to 0 **does not by itself prove** they are two valid entries for the same transaction.

### Reconciling Opening Balance Plus Movements

~~~sql
-- Find accounts whose balance differs from opening balance + entries.
-- Expected result: 0 rows.
SELECT
  a.AccountId,
  a.BalanceMinor,
  a.OpeningBalanceMinor + IFNULL(SUM(e.DeltaMinor), 0) AS ExpectedMinor
FROM Accounts AS a
LEFT JOIN LedgerEntries AS e ON a.AccountId = e.AccountId
GROUP BY a.AccountId, a.BalanceMinor, a.OpeningBalanceMinor
HAVING a.BalanceMinor
    != a.OpeningBalanceMinor + IFNULL(SUM(e.DeltaMinor), 0);
~~~

With massive history, never run full-table scans across `LedgerEntries` continuously in production. Use **daily/partitioned reconciliation**, audited snapshots, or rate-limited batch reads instead. To display balances to users, read `Accounts.BalanceMinor` via a strong read; for periodic reconciliation, rely on entry history and opening snapshots.

### Querying One Account's History

~~~sql
SELECT e.RequestId, t.PostedAt, e.DeltaMinor, e.Currency
FROM LedgerEntries AS e
JOIN Transfers AS t ON t.RequestId = e.RequestId
WHERE e.AccountId = "782e6ff2-965e-4668-960a-10493863f5c2"
ORDER BY t.PostedAt DESC, e.RequestId DESC
LIMIT 20;
~~~

The `LedgerEntriesByAccount` index narrows the scan by `AccountId`. However, it **does not automatically sort by `PostedAt`**, because the timestamp resides in `Transfers`; the query may still join and sort many entries. When building transaction history at scale, design a **dedicated read model/index by `AccountId` + time** and evaluate write amplification/hotspots rather than blindly adding a global ascending timestamp index.

## 6. Mandatory Testing: Errors, Retries, and Concurrency Races

| Test Case | How to Execute | Expected Result |
|---|---|---|
| **T1 — Valid transfer** | Generate UUID v4 `RequestId`, transfer 2500 cents | Balances shift -2500/+2500, 1 transfer, 2 entries |
| **T2 — Resend same request** | Keep identical `RequestId` and full payload | `ALREADY_POSTED`; no extra entries |
| **T3 — Reuse key with different payload** | Same `RequestId` but different amount/account | Rejected; balances unchanged |
| **T4 — Insufficient funds** | New `RequestId`, transfer exceeding source `BalanceMinor` | Fails; no partial transfer/entries |
| **T5 — Wrong tenant/currency** | Pick account from another tenant or USD → EUR | Rejected before commit |
| **T6 — Negative input or source = target** | `AmountMinor` <= 0, or identical account | Rejected by validation |
| **T7 — Race on one balance** | Two concurrent requests, each individually affordable yet exceeding balance together | Never let both commit into negative balance; one transaction may `ABORTED`/retry then fail for insufficient funds |
| **T8 — Timeout after commit** | Client misses response after server commits; resend same ID | Querying `Transfers` finds existing record; no double debit |
| **T9 — Overflow** | Values near `Long.MAX_VALUE` | Blocked by Java `Math.addExact/subtractExact` or constraints |
| **T10 — Recovery/reports** | Run both reconciliation queries | Zero violating rows |

### Why Does Spanner Survive Balance Races?

~~~mermaid
sequenceDiagram
  participant R1 as Request 1
  participant SP as Spanner
  participant R2 as Request 2
  R1->>SP: Read A=5000; plan to deduct 4000
  R2->>SP: Read A=5000; plan to deduct 4000
  R1->>SP: Write balances + entries + commit
  SP-->>R1: COMMITTED
  R2->>SP: Attempt commit with stale read
  SP-->>R2: ABORTED / retry requested
  R2->>SP: Re-read A=1000
  SP-->>R2: Insufficient for 4000 → reject
~~~

This sequence is illustrative and does not assert which transaction always wins. **Read-write transactions are serializable by default** and the Java client automatically retries on `ABORTED`, so the retry observes the updated balance. If using a different isolation level or write path, re-verify the corresponding invariants.

**Never** use `Partitioned DML` for partial balance/entry updates: Partitioned DML is not atomic across a single transfer and applies per-partition; it fits idempotent bulk updates, not multi-row ledger postings. Never put Pub/Sub publishes, payment gateway charges, or side-effecting logs inside an auto-retried callback.

## 7. Immutable Auditing, Corrections, and Event Publishing

### Never Fix History by Overwriting

In this lab, only **insert** `Transfers` and `LedgerEntries` during transfers; if business logic requires refunding $25.00, create a **new compensating transfer** with its own `RequestId`, moving funds from B back to A. Include an `OriginalRequestId` reference column in an extended schema and record the reversal reason, approver, and timestamp.

**Never** run `UPDATE LedgerEntries SET DeltaMinor=...` or `DELETE FROM Transfers ...` to "patch the ledger"; that destroys the audit trail. Spanner has strong transactional consistency, yet **does not automatically create a legally immutable audit ledger**: IAM permissions, change tracking, hashes/audit trails, and retention policies must be designed into the system.

### Outbox and Change Streams

After commit, a `transfer-posted` event must go to Pub/Sub for the notification service. Publishing to Pub/Sub **after commit** risks DB success followed by publish failure; publishing **before commit** risks emitting events for rolled-back transfers.

Remedies:

- Write an **`OutboxEvents`** record in the **same Spanner transaction**, then have a worker read/publish and mark status (with consumer retries/idempotency).
- Or use **Spanner change streams** where supported to capture committed changes and forward them to Dataflow/Pub/Sub downstream; design for at-least-once delivery and business-key ordering.

Never claim **end-to-end exactly-once** solely because Spanner transactions are atomic. In distributed systems, consumers still must deduplicate using event IDs or business keys.

### Commit Timestamps and History Retrieval

`PostedAt TIMESTAMP OPTIONS (allow_commit_timestamp=true)` records when Spanner commits. **Commit timestamps are not unique IDs**; independent transactions can share identical timestamps, so use `RequestId` for uniqueness and tie-breaking. For multi-query reports, use an appropriate snapshot/read-only transaction to avoid combining data from different instants.

## 8. Scale: Primary Keys, Hot Accounts, and Queries

Spanner partitions data by key ranges. Even with strong horizontal scalability, a schema can still heat up one range or one row:

| Mistake | Consequence | Fix |
|---|---|---|
| PK `(PostedAt, RequestId)` | Ascending timestamps pile inserts at the tail of the keyspace | UUID v4 `RequestId`; keep timestamp as a non-leading column |
| Sequential `RequestId` or UUID v1 | Writes cluster closely in key order | UUID v4 / random distribution; or properly configured bit-reversed sequence |
| Every transfer touches **one central account** | The same balance row faces heavy contention, aborts, and latency | Design business subledgers/shards, reconcile totals, and weigh consistency trade-offs |
| Global index starting with ascending timestamp | Hotspot on the secondary index | Reorder index, using account/shard prefixes aligned with queries |
| Scanning billions of entries per request | Very high cost and latency | Materialized balances, read models, partitioned/batched reconciliation |
| Transaction performs HTTP calls or heavy processing | Holds locks, increases aborts and commit time | Keep only DB reads/writes inside callback; orchestrate externally |

**Never shard a single balance by arbitrarily summing shard balances** if real-time overdraft prevention is required: operations must uphold sufficient-funds invariants under contention, and summing shards without coordination cannot prevent overdrafts. For e-wallets with a single account receiving tens of thousands of transfers/second, benchmark and design specifically rather than assuming one Spanner row scales infinitely.

As data grows, inspect **Key Visualizer**, transaction statistics, lock/abort metrics, CPU utilization, Query Insights, and query plans to hunt hotspots. Before adding an index, weigh read gains against the extra mutations/index entries written per transfer.

## 9. IAM, Networking, and Deploying Java Apps on GCP

| Identity | Role | Reference Permissions |
|---|---|---|
| Platform/DB administrator | Create instances/databases, DDL, backup/restore | Spanner Instance Admin / Database Admin per scope and approval |
| Java Cloud Run/GKE runtime service account | Read/write ledger per workload | `roles/spanner.databaseUser` on the **specific database** if that scope is acceptable |
| Reconciliation worker | Read snapshots/reports | Read-only role or **Spanner fine-grained access control** via database role |
| CI/CD deployer | Build/deploy Java runtime | Cloud Run deploy and `iam.serviceAccounts.actAs` on the runtime SA |
| Auditor | View reports and audit logs | Approved read-only / log reader roles |

**Beware broad permissions:** `roles/spanner.databaseUser` grants broad SQL operations, **including schema modifications** under current role definitions; for real monetary ledgers, evaluate **custom IAM roles** or **Spanner fine-grained access control**, separating schema migrations from account posting. Never grant `roles/spanner.databaseAdmin` or Owner to an app just to write two ledger entries.

Example assigning IAM at the **database** rather than project level:

~~~bash
PROJECT_ID="my-spanner-ledger-lab"
INSTANCE="ledger-lab"
DATABASE="ledger"
RUNTIME_SA="orders-ledger@$PROJECT_ID.iam.gserviceaccount.com"

# Create runtime SA and inspect IAM policy first; avoid duplicate bindings.
gcloud spanner databases add-iam-policy-binding "$DATABASE" \
  --instance="$INSTANCE" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/spanner.databaseUser" \
  --project="$PROJECT_ID"

gcloud spanner databases get-iam-policy "$DATABASE" \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

This illustrates lab IAM commands. For production, review overly broad roles and enforce change approvals. Java uses the runtime SA's **Application Default Credentials (ADC)** without downloading JSON keys. On GKE, use **Workload Identity Federation for GKE**; on Cloud Run, configure `--service-account` on the revision.

**Networking:** Spanner client libraries call the Spanner API over gRPC/TLS. Workloads need egress to Google Cloud APIs per network policy. Private Google Access, PSC for Google APIs, or VPC Service Controls can be used per org architecture; **Spanner does not require Cloud SQL Private Services Access** and does not use Cloud SQL Auth Proxy or Cloud SQL JDBC SocketFactory. IAM auth and network paths are two separate requirements.

**Per-tenant authorization:** database-level IAM does not check `tenant-demo` inside individual Java requests. Before calling `transfer`, authenticate the caller and derive `tenantId` from the verified identity; never trust an unverified client-supplied tenant string. Account-read queries must also filter/authorize by owner/tenant rather than relying solely on knowing an `AccountId`.

## 10. Emulator, CI/CD, Backups, and Auditing

### Using the Spanner Emulator for Logic Testing

The emulator runs locally, stores data in **RAM**, and loses data on restart; it supports GoogleSQL/PostgreSQL APIs but **does not fully simulate IAM, TLS, performance, production schema/transaction locking, or all production limits**.

~~~bash
# Terminal 1:
gcloud components install cloud-spanner-emulator
gcloud emulators spanner start

# Terminal 2: separate gcloud config to avoid overwriting production config.
gcloud config configurations create spanner-emulator-lab
gcloud config configurations activate spanner-emulator-lab
gcloud config set auth/disable_credentials true
gcloud config set project emulator-project
gcloud config set api_endpoint_overrides/spanner http://localhost:9020/

gcloud spanner instances create ledger-emulator \
  --config=emulator-config \
  --description="Local ledger emulator" \
  --nodes=1
gcloud spanner databases create ledger \
  --instance=ledger-emulator
gcloud spanner databases ddl update ledger \
  --instance=ledger-emulator \
  --ddl-file=schema.sql

# Java client targets the gRPC emulator endpoint.
export SPANNER_EMULATOR_HOST="localhost:9010"
~~~

After testing, switch back to your normal gcloud configuration:

~~~bash
gcloud config configurations activate default
unset SPANNER_EMULATOR_HOST
~~~

**Never run delete commands in an unverified CLI configuration.** In Windows PowerShell, environment variable syntax differs from Bash (`$env:SPANNER_EMULATOR_HOST = "localhost:9010"`). The emulator does not replace integration tests against real Spanner databases for concurrency/aborts, IAM, throughput, latency, and cost.

### CI/CD and Data Operations

1. Review SQL DDL/migrations in Git, checking large-table schema changes, rollback plans, and isolated deploy permissions.
2. Run **unit tests** for validation, idempotency, and arithmetic; run integration tests against the emulator with synthetic data.
3. Run against **real staging Spanner** to test read-write retries, IAM, performance, and races under load.
4. Deploy the Java service as a canary; monitor 5xx/`ABORTED` errors, latency, and reconciliation. Never change ledger schemas across multiple components simultaneously without a migration plan.
5. Configure **backups/PITR**, compliance retention/auditing, encryption, strict restore permissions, and recovery drills.
6. For large-scale analytics/reconciliation, use controlled export/ETL to an analytical system; do not subject production OLTP to continuous full-table scans.

**Restoring from backup does not answer "which transactions were already sent to partners."** You still need journals/outboxes/reconciliation against upstream and downstream systems. Never overwrite a production database from an old snapshot just because one report has a bug.

## 11. Monitoring, Reliability, and Cost

| Signal | Why Monitor |
|---|---|
| Commit latency P50/P95/P99, transaction abort rate | Lock contention or database/network latency |
| Read/write CPU utilization, processing units/nodes | Compute capacity and performance headroom |
| Hot splits / Key Visualizer | Monotonic keys, central hot accounts, index hotspots |
| Query/transaction statistics | Slow DML, large scans, suboptimal indexes |
| Sessions and client retry latency | Per-request client creation, session exhaustion, retry storms |
| Reconciliation mismatches | Broken invariants or unauthorized direct mutations |
| IAM/DDL/audit log events | Risky role, schema, or configuration changes |
| Storage size, backup/PITR retention, network egress | Cost and recoverability |

**Detecting faults:** occasional `ABORTED` responses are normal under contention; a high abort rate paired with rising P99 or workflow timeouts warrants investigation. Never set unlimited retries on every error; configure **deadlines and backoff** aligned with API/SLOs, especially under Cloud Run request timeouts.

**Spanner costs** typically tie to compute capacity by config/edition, storage, backups, replication, network, and add-on features. A figure like "1 million transfers/day" cannot predict a bill without knowing processing units, instance configuration, storage footprint, index write amplification, query scans, and retention. In a lab, delete the instance **after verifying no data is needed** to stop ongoing charges; in production, verify deletion protection, backups, and owners before deleting anything.

## 12. Common Error Runbook

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `PERMISSION_DENIED` on Java connect | ADC using wrong SA, missing Spanner IAM/DB role | Verify runtime principal and database IAM/FGAC |
| `NOT_FOUND` instance/database | Wrong project/instance/database/dialect or resource missing | `gcloud spanner instances/databases describe` |
| `ABORTED` during transfer | Two transactions touched the same `Accounts` row | Let `TransactionRunner` retry; measure contention/latency |
| Two transfers share `RequestId` with different payload | Client misused idempotency key | Reject with business HTTP 409; never alter posted records |
| Negative balance or `CHECK constraint failed` | Business rule bypassed by another write path | Block rogue write path, audit ledger, post compensating entry |
| `ALREADY_EXISTS` writing transfer record | Two racing requests or key reuse | Read `Transfers` by `RequestId`, compare payload before returning status |
| `RESOURCE_EXHAUSTED` / quota | Session/CPU/quota shortage, client explosion | Reuse `Spanner` client; inspect quotas and Key Visualizer |
| `DEADLINE_EXCEEDED` | Slow backend, hotspot, or tight client timeout | Check actual commit via `RequestId`; retry with same ID |
| Reconciliation returns violating rows | Direct mutation, schema bug, bad migration/opening snapshot | Isolate write path, audit, never `UPDATE` ledger history |
| History query slow | Missing index, large scan/sort | Inspect query plan, read model, and workload-aligned index |
| Emulator passes, production fails | Emulator does not fully simulate IAM/performance | Run integration tests in real staging |
| Missing table/column after deploy | DDL still running or runtime/schema version mismatch | Check migration operation and backward compatibility |

When unsure whether a request committed, **never generate a new `RequestId`** just to "resend to be safe": query `Transfers` by the original ID and reuse that exact ID on retry. HTTP status mapping at the API boundary: invalid input `400`, unauthorized `403`, conflict / mismatched idempotency payload `409`, transient backend error `503` with sensible `Retry-After`/backoff; HTTP codes are an application design decision, not provided wholesale by Spanner.

## 13. Pre-Production Checklist

- [ ] Clearly distinguished the simplified lab ledger from full legal/accounting ledgers and formal Debit/Credit rules.
- [ ] Transfers restricted to same tenant/currency in the lab; no mixed FX.
- [ ] Monetary values use `INT64 minor units` or exact decimals; overflow and inconsistent rounding blocked.
- [ ] Each v4 `RequestId` generated before the transaction, preserved on retries, and payload-checked on duplicates.
- [ ] Both balances, both entries, and the transfer record written in **one read-write transaction**.
- [ ] Constraints enforce positive amounts, distinct accounts, and non-negative balances.
- [ ] Commit timestamp placed at the end of the DML transaction; timestamps never used as unique IDs.
- [ ] Zero Pub/Sub/HTTP/payment calls inside auto-retried callbacks.
- [ ] History never edited or deleted; use compensating transfers plus outbox/change streams for events.
- [ ] SQL reconciliation, concurrency, timeout-after-commit, and duplicate-request tests in place.
- [ ] Least-privilege runtime IAM, FGAC where needed, and tenant-scoped read authorization enforced in the app.
- [ ] Tested on emulator + real Spanner staging; measured P95 latency, aborts/hot rows, and cost.
- [ ] Backups/PITR, logging/auditing, runbooks, and canary/rollback plans ready.

## 14. Applied Exercises

**Exercise 1 — Invariants.** A holds $150.00 and B holds $20.00. Transfer $45.75. Write both `DeltaMinor` values in cents, the new balances, and the SQL checking net-zero deltas. Why is updating A and B in two separate transactions wrong?

**Exercise 2 — Idempotency.** A client sends `RequestId` `R` to transfer 2500 cents, hits a timeout, and resends the same ID. Describe the response when (a) the transaction already committed; (b) it did not commit; (c) the retry payload changed to 3500 cents.

**Exercise 3 — Concurrency.** A has 6,000 cents. Two requests with different IDs concurrently try to transfer 4,000 cents to two recipients. Under serializable transactions, describe at most how many requests can succeed and the role of `ABORTED`/retries.

**Exercise 4 — Schema Design.** Why is `PRIMARY KEY (PostedAt, RequestId)` a poor choice under high write load? Replace it with UUID v4, and explain secondary index cost and querying history by `AccountId`.

**Exercise 5 — SQL Verification.** Create a test dataset with a `Transfers` row and only one `LedgerEntries` row; predict the reconciliation query output. Extend the query to catch tenant/currency mismatches between entries and transfers.

**Exercise 6 — Corrections.** A 500-cent transaction was already posted, yet business rules require a refund. Why must you not `UPDATE LedgerEntries`? Design a reversing transfer referencing the original `RequestId` and rules to prevent refunding twice.

**Exercise 7 — Java.** Identify where overflow, insufficient funds, or idempotency-key conflicts can occur in `LedgerDemo`. Write unit/integration tests for each case and verify no partial writes occur.

**Exercise 8 — Events Outside Spanner.** After posting a transfer, the app must publish to Pub/Sub. Diagram the two failures "DB commits then publish fails" and "publish succeeds then DB rolls back"; propose transactional outbox/change streams and consumer idempotency.

**Exercise 9 — Permissions and Reliability.** A Java service runs on Cloud Run, a reconciliation job runs on GKE, and the DB sits in a data project. Specify separate runtime identities and IAM roles, how to block cross-tenant reads, two metrics to alert on, and the impact of creating a new `Spanner` client per request.

**Exercise 10 — Migration.** A legacy system has account balances without full historical ledger entries. Design an audited opening-balance snapshot, reconciliation baseline, sum-verified import, rollback capability, and readiness gates before shifting live traffic to Spanner.

## Official References

- [Spanner overview](https://cloud.google.com/spanner/docs/overview) — distributed database architecture and consistency.
- [Transactions overview](https://cloud.google.com/spanner/docs/transactions) — read-write, serializability, and commits.
- [Get started with Spanner in Java](https://cloud.google.com/spanner/docs/getting-started/java) — `DatabaseClient`, DML, transactions, and queries.
- [Spanner Java TransactionRunner](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.TransactionRunner) — automatic retries and commit timestamps.
- [DML best practices](https://cloud.google.com/spanner/docs/dml-best-practices) — DML vs. mutations and commit timestamps.
- [Commit timestamps](https://cloud.google.com/spanner/docs/commit-timestamp) — `PENDING_COMMIT_TIMESTAMP()`.
- [Schema design best practices](https://cloud.google.com/spanner/docs/schema-design) — UUID v4, key-range hotspots, and secondary indexes.
- [Create/check constraints](https://cloud.google.com/spanner/docs/check-constraint/how-to) — `CHECK` constraints on same-table data.
- [Create database with Google Cloud CLI](https://cloud.google.com/spanner/docs/getting-started/gcloud) — instances, databases, and schemas.
- [Spanner emulator](https://cloud.google.com/spanner/docs/emulator) — local tests and production differences.
- [Spanner IAM roles](https://cloud.google.com/spanner/docs/iam) — database-level permissions and fine-grained access.
- [Spanner change streams](https://cloud.google.com/spanner/docs/change-streams) — capturing committed changes.
- [Spanner Query insights](https://cloud.google.com/spanner/docs/query-insights) and [Key Visualizer](https://cloud.google.com/spanner/docs/key-visualizer) — observing slow queries/hotspots.
- [Backup and recovery](https://cloud.google.com/spanner/docs/backup) — backups/restores.
- [Spanner pricing](https://cloud.google.com/spanner/pricing) — compute, storage, and regional/edition configurations.
