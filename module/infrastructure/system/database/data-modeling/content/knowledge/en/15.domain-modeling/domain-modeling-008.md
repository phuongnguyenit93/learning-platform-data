# Trade-Offs Between Large Aggregates, Contention, and Transaction Requirements

## Learning Objectives

After this lesson, you will be able to:

- Explain why a **large aggregate** can easily uphold invariants yet struggle to scale, and why splitting aggregates introduces transaction coordination requirements.
- Identify **invariants that must hold immediately upon commit** and distinguish them from consistency achievable through a multi-step workflow.
- Evaluate aggregate boundaries by write contention, number of elements loaded, lock scope, lifecycle, and transaction cost, rather than counting tables in an ERD.
- Design conditional write commands, optimistic or pessimistic locking, constraints, and atomic transactions to prevent lost updates or limit overruns.
- Choose between a centralized aggregate, multiple aggregates in the same database, and independent aggregates connected via contracts, events, or pre-allocated quotas.
- Verify a design using concurrent execution schedules, operational metrics, and mid-flight failure scenarios, while evaluating relational, document, graph, and analytical models.

In **DATABASE_DATA_MODELING**, a good model does more than get entity names and relationships right; it turns business requirements into **enforceable consistency commitments**. An aggregate boundary that is too wide forces every operation to contend on one root; a boundary that is too small splits conditions that must hold together across separate transactions and leaves them unprotected. This topic is a balancing act, not a "smaller is always better" rule.

## 1. Three Forces When Choosing Aggregate Boundaries

An **aggregate** is a consistency unit in the domain model, with an **aggregate root** deciding valid changes to state under its responsibility. Three main forces pull on its boundaries:

1. **Business invariants:** which data must be decided together so illegal states cannot occur?
2. **Cost and contention:** how many commands try to modify the same unit concurrently, how much data must be loaded and locked, and how many retries are needed?
3. **Transaction and deployment boundaries:** does the database provide suitable atomic operations; do the parts needing coordination share the same owner and storage?

A 1-N relationship in an ERD does not prove the N child objects must live in one aggregate. Yet turning every table into its own aggregate does not magically keep a cross-table invariant consistent either.

| Design approach | Potential advantages | Common risks |
| --- | --- | --- |
| One large aggregate covering the whole business group | Centralized internal rules; easy to reason about via one root | Heavy data loading, version conflicts, hot rows, long transactions |
| Multiple small aggregates with separate lifecycles | Less data loaded, independent changes, clearer ownership | Cross-aggregate rules need explicit transactions or protocols |
| Aggregates split across services/databases | Independent deployment and scaling | No cross-system local ACID; timeouts, retries, intermediate states, compensation |

**An aggregate is a logical boundary, not necessarily a table, a document, a process, or a physical lock.** One aggregate can span multiple rows; one SQL transaction can touch multiple rows. Conversely, even within the same table, two rows can be two independent aggregates.

## 2. Running Scenario: Project Expense Budget

An organization allocates **100,000,000 VND** to a project for the quarter. Employees submit expense requests; once a request is reviewed, the system **holds budget** before executing payment. After the expense is formally booked, held funds convert to **committed**. If the request is cancelled or expires, held funds return to the available limit.

Suppose the business requires:

- Total **held + committed never exceeds the limit** on any valid commit.
- An expense request can be retried due to a lost response, but must never hold budget twice for the same intent.
- Employees may edit request details before approval; after approval, the committed amount must be controlled via a different command.
- Project profiles, employees, vendors, and payment details have independent lifecycles.
- Occasionally **500 requests per second** target the same budget fund; this is an illustrative load for evaluating design, not a measured benchmark.

We identify two data groups:

- **`BudgetPool`**: limit, held amount, committed amount, budget period, currency, and fund allocation authority.
- **`ExpenseRequest`**: requester, purpose, approval state, expense line items, receipts/evidence, and request history.

They are related, yet not obviously forced into the same aggregate. Before deciding, write out the exact invariants.

### Invariants and Required Consistency Timing

Notation for a budget pool:

- \(L\): approved budget limit;
- \(H\): currently held funds;
- \(C\): funds committed/booked per policy;
- \(A=L-H-C\): remaining available funds.

Core condition:

\[
L \ge 0,\quad H \ge 0,\quad C \ge 0,\quad H+C \le L.
\]

All values must share **the same currency and budget scope**. This example uses integer **VND** units and avoids floating-point numbers when checking money. If multiple currencies are supported, dedicated conversion policies, exchange rates, and rounding rules are required before enforcing limits.

| Rule | True immediately upon commit? | Authoritative owner |
| --- | --- | --- |
| Never hold/commit more than \(L\) | Yes | `BudgetPool`, the fund allocation authority |
| Same `requestId` never increments \(H\) twice | Yes | Holder of reservations and command results |
| A reservation is committed or released at most once | Yes | `BudgetReservation` lifecycle |
| `APPROVED` `ExpenseRequest` has valid approval details | Yes | `ExpenseRequest` |
| Budget figures on dashboards update instantaneously | Not necessarily; depends on read SLA | Projection/read model |
| Bank transfer succeeds after approval | Multi-step workflow | Authoritative Payment/Accounting |

The designer must distinguish **"the budget must never be over-allocated"** from **"every screen instantly shows the new balance."** Delayed reporting can be acceptable, whereas relying on delayed reports to approve new allocations is not.

## 3. Option A: Large Aggregate Containing All Expense Requests

An intuitive approach treats **`ProjectBudget`** as the root containing all `ExpenseRequest`s and budget holds:

~~~mermaid
flowchart TB
    S["Commands: Submit / Hold / Approve / Cancel"]
    S --> B
    subgraph Big["ProjectBudget Aggregate"]
        B["ProjectBudget root"]
        E1["ExpenseRequest #1"]
        E2["ExpenseRequest #2"]
        E3["... thousands of other requests"]
        B --> E1
        B --> E2
        B --> E3
    end
~~~

**Pros:**

- The root can validate the overall limit and members in one business transaction.
- Commands touching the same budget are expressed in one central place.
- For small funds with few requests, simple rules, and low churn, this model can fit very well.

**Costs:**

- If an ORM loads the root as a full object graph, every 100,000 VND hold command may load thousands of unrelated `ExpenseRequest`s.
- If every write command increments **a single root version**, two people editing unrelated requests still suffer optimistic-lock conflicts.
- A single root row or lock point becomes a **hot spot**; long-held locks increase wait times.
- Long-term history grows without bound, even though deciding a single allocation only requires the limit and active holds.
- Sharing one root across all projects and quarters creates far more contention than the business actually needs.

A large aggregate does **not always** lock an entire table: databases can lock by row and repositories can perform incremental updates without loading everything. The core issue is **whether the model forces independent changes to contend on a single logical unit**, plus how ORMs, repositories, and transactions implement it.

### Signs a Root Is Too Wide

Metrics to measure rather than guess:

- number of elements and bytes loaded to execute a minor command;
- version conflict rate when multiple users edit different parts;
- lock wait times and deadlock counts;
- p95/p99 write latency spiking as traffic or member count grows;
- holding transactions open while calling external APIs;
- multiple teams needing to edit parts of the same root that have independent lifecycles.

If these symptoms appear, do not split blindly right away. First identify **the minimal invariant that genuinely demands a shared decision**.

## 4. Option B: BudgetPool Decides Spending Rights, ExpenseRequest Is Independent

Re-examining the problem: **ensuring spending stays within the limit** does not require the `BudgetPool` root to hold descriptions, receipts, and notes for thousands of `ExpenseRequest`s. It only needs to govern the limit and reconcilable holds/commitments.

~~~mermaid
flowchart LR
    App["Approval use case"]
    App -->|"Reserve(amount, requestId)"| Pool
    App -->|"Approve / Reject"| Expense

    subgraph A["BudgetPool Aggregate"]
        Pool["BudgetPool root<br/>limit, held, committed"]
        R["BudgetReservation<br/>reservationId, amount, status"]
        Pool --> R
    end

    subgraph E["ExpenseRequest Aggregate"]
        Expense["ExpenseRequest root<br/>reason, line items, approval"]
    end

    Expense -.->|"budgetId, reservationId"| Pool
~~~

In this model:

- **`BudgetPool`** is the authority granting holds, converting holds to commitments, and releasing holds.
- **`BudgetReservation`** can be a member of `BudgetPool` stored in a separate table; all operations on it must follow `BudgetPool`'s shared write protocol.
- **`ExpenseRequest`** has an independent state and lifecycle; it only holds `budgetId`/`reservationId` and never adjusts balances via shortcuts.
- **`Project`**, **`Employee`**, and **`Payment`** belong to other sources; keep IDs or needed snapshots instead of pulling them into `BudgetPool`.

An `ExpenseRequest` having its description edited does not contend on `BudgetPool`'s version. Only actions affecting **budget utilization** go through the budget arbitration point.

### Which Questions Guide Merging vs. Splitting?

| Question | If yes | Guidance |
| --- | --- | --- |
| Must two attributes change together for the root to stay valid? | Yes | Candidates for the same aggregate |
| Does an entity have its own lifecycle/approval and edits that do not affect the pool? | Yes | Candidate for an independent root |
| Do two data groups just need to appear side by side on screen? | Yes | Use JOINs/read models; never merge roots for UI |
| Do all users contend on one shared limit? | Yes | Must have a single arbitration point or provably safe quota allocation |
| Are two aggregates in the same DB and required to commit one step together? | Yes | Can use an intentional cross-root transaction; understand coupling cost |
| Are the two sides in independent DBs/services? | Yes | Design intermediate states, idempotency, and compensation workflows |

**Splitting aggregates does not automatically eliminate contention.** If all commands still compete for one shared limit \(L\), the `BudgetPool` row remains a shared arbitration point. However, splitting prevents changes **unrelated to the limit** from contending on it, while reducing loaded data.

## 5. Describing Commands, Lifecycles, and Invariants Before Writing SQL

A budget reservation has its own lifecycle:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: ReserveBudget
    HELD --> COMMITTED: CommitBudget
    HELD --> RELEASED: ReleaseBudget
    HELD --> EXPIRED: ExpireBudgetHold
    COMMITTED --> [*]
    RELEASED --> [*]
    EXPIRED --> [*]
~~~

Sample state transitions:

| Command | Preconditions | Atomic update | Must never happen |
| --- | --- | --- | --- |
| `ReserveBudget` | Pool `OPEN`; positive amount; sufficient \(A\); `requestId` unseen | Insert `HELD` Reservation, increment \(H\) | \(H+C\) exceeds \(L\); two holds from one `requestId` |
| `CommitBudget` | Reservation `HELD`, unexpired; approval proof matches policy | `HELD` -> `COMMITTED`, decrement \(H\) and increment \(C\) by same amount | Increment \(C\) again on retry |
| `ReleaseBudget` | Reservation `HELD` and permitted to cancel | `HELD` -> `RELEASED`, decrement \(H\) | Decrement \(H\) twice |
| `ExpireBudgetHold` | Reservation `HELD` and past expiration | `HELD` -> `EXPIRED`, decrement \(H\) | Release an already `COMMITTED` item |
| `ChangeBudgetLimit` | Authorized approver; new \(L \ge H+C\) | Conditional update of \(L\) | Negative available balance after commit |

If a `COMMITTED` expense needs a refund or adjustment, that is a **new business command** with its own permissions and evidence—never allow arbitrarily reverting `COMMITTED` back to `HELD`.

### Java Example: Root Protecting Invariants in Memory

This example uses integer **VND** amounts to avoid `double` precision errors; it is a simplified domain model, not a complete repository or audit system:

~~~java
import java.util.Objects;
import java.util.UUID;

record BudgetId(UUID value) {
    BudgetId { Objects.requireNonNull(value); }
}

final class BudgetPool {
    private final BudgetId id;
    private long limitVnd;
    private long heldVnd;
    private long committedVnd;

    BudgetPool(BudgetId id, long limitVnd,
               long heldVnd, long committedVnd) {
        this.id = Objects.requireNonNull(id);
        if (limitVnd < 0 || heldVnd < 0 || committedVnd < 0
                || heldVnd > limitVnd
                || committedVnd > limitVnd - heldVnd) {
            throw new IllegalArgumentException("Invalid budget");
        }
        this.limitVnd = limitVnd;
        this.heldVnd = heldVnd;
        this.committedVnd = committedVnd;
    }

    long availableVnd() {
        return limitVnd - heldVnd - committedVnd;
    }

    void reserve(long amountVnd) {
        requirePositive(amountVnd);
        if (availableVnd() < amountVnd) {
            throw new IllegalStateException("Insufficient budget");
        }
        heldVnd = Math.addExact(heldVnd, amountVnd);
    }

    void commit(long amountVnd) {
        requirePositive(amountVnd);
        if (heldVnd < amountVnd) {
            throw new IllegalStateException("Not held");
        }
        heldVnd -= amountVnd;
        committedVnd = Math.addExact(committedVnd, amountVnd);
    }

    void release(long amountVnd) {
        requirePositive(amountVnd);
        if (heldVnd < amountVnd) {
            throw new IllegalStateException("Not held");
        }
        heldVnd -= amountVnd;
    }

    private static void requirePositive(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amount <= 0");
        }
    }
}
~~~

This class illustrates **total-balance invariants**, but does not by itself verify whether a specific `Reservation` is being committed or released for the first time. The domain/repository layer managing `reservationId`, `requestId`, and status must coordinate with the root in the same transaction to prevent duplicate processing. Likewise, in-memory checks alone are insufficient when two JVMs load the budget concurrently; the database must provide synchronization.

## 6. Relational Schema Serving the Chosen Boundaries

In PostgreSQL, `BudgetPool` can live in one table and `BudgetReservation` in another. Together they can still form **one logical aggregate** if `BudgetPool` coordinates every write operation that alters budget reservations.

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE finance.budget_pool (
    tenant_id UUID NOT NULL,
    budget_id UUID NOT NULL,
    period_code VARCHAR(16) NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    state VARCHAR(12) NOT NULL DEFAULT 'OPEN'
        CHECK (state IN ('OPEN', 'FROZEN', 'CLOSED')),
    limit_vnd BIGINT NOT NULL CHECK (limit_vnd >= 0),
    held_vnd BIGINT NOT NULL DEFAULT 0 CHECK (held_vnd >= 0),
    committed_vnd BIGINT NOT NULL DEFAULT 0 CHECK (committed_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, budget_id),
    CONSTRAINT no_budget_overspend
        CHECK (held_vnd <= limit_vnd
           AND committed_vnd <= limit_vnd - held_vnd)
);

CREATE TABLE finance.budget_reservation (
    tenant_id UUID NOT NULL,
    reservation_id UUID NOT NULL,
    budget_id UUID NOT NULL,
    expense_request_id UUID NOT NULL,
    request_id UUID NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    state VARCHAR(12) NOT NULL
        CHECK (state IN ('HELD', 'COMMITTED', 'RELEASED', 'EXPIRED')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, reservation_id),
    UNIQUE (tenant_id, request_id),
    FOREIGN KEY (tenant_id, budget_id)
        REFERENCES finance.budget_pool (tenant_id, budget_id)
);

-- An expense request cannot have two active/committed reservations.
CREATE UNIQUE INDEX one_live_budget_reservation_per_expense
    ON finance.budget_reservation (tenant_id, expense_request_id)
    WHERE state IN ('HELD', 'COMMITTED');

-- Query to sweep expired holds.
CREATE INDEX held_budget_expiry
    ON finance.budget_reservation (expires_at)
    WHERE state = 'HELD';
~~~

**What do these constraints achieve?**

- The `CHECK` on `budget_pool` guards row-local arithmetic: \(H+C \le L\). It does not prove that the sum of reservation rows equals \(H\) or \(C\).
- `UNIQUE(tenant_id, request_id)` enforces uniqueness of a hold request; on retry, compare the payload against the original request rather than relying solely on matching IDs.
- The partial `UNIQUE` index prevents two live or committed holds for the same `ExpenseRequest`. If business rules later allow multiple independent disbursements per `ExpenseRequest`, change the business key rather than keeping an outdated index.
- The composite FK `(tenant_id, budget_id)` protects relationships within the owning source. `expense_request_id` is only a reference ID to the `ExpenseRequest` aggregate and grants no permission to mutate `ExpenseRequest`.
- The index on `expires_at` supports the expiration sweep job; every index still incurs write overhead and must be evaluated against actual workloads.

**Important limitation:** counters \(H\) and \(C\) must match the holds/commitments in the reservation table. PostgreSQL `CHECK` constraints cannot sum across multiple rows in a standard `CHECK`. Every write path changing reservations must update the pool in the same transaction, restricting execution through the proper API/repository; triggers or periodic reconciliation can be added if security policy requires them.

## 7. Atomic Transaction: Reserving Budget Without Overspending

A `ReserveBudget` command can execute the following steps in **one transaction**:

~~~sql
BEGIN;

INSERT INTO finance.budget_reservation
    (tenant_id, reservation_id, budget_id, expense_request_id,
     request_id, amount_vnd, state, expires_at)
VALUES
    (:tenant_id, :reservation_id, :budget_id, :expense_request_id,
     :request_id, :amount_vnd, 'HELD', :expires_at)
ON CONFLICT DO NOTHING
RETURNING reservation_id;

-- If 0 rows: ROLLBACK. Check whether requestId was already processed
-- or the ExpenseRequest already has a hold; do not increment H.

UPDATE finance.budget_pool
SET held_vnd = held_vnd + :amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :budget_id
  AND state = 'OPEN'
  AND :amount_vnd > 0
  AND limit_vnd - held_vnd - committed_vnd >= :amount_vnd
RETURNING version;

-- If UPDATE returns 0 rows: ROLLBACK the INSERT too; report insufficient budget,
-- pool not OPEN, or pool not found per verification results.

COMMIT;
~~~

At the SQL level, the comparison predicate combined with `UPDATE` is decisive. Suppose \(H+C\) = 30 million, \(L\) = 100 million, and **two 70 million requests** arrive nearly simultaneously. Both might earlier read 70 million available, yet two `UPDATE`s on **the same `budget_pool` row** are serialized. Under PostgreSQL row locking at `READ COMMITTED`, the second `UPDATE` waits for the first transaction to finish, then re-evaluates the predicate against the newly committed row version. At most one request can raise \(H\) to 100 million.

If you merely ran:

~~~text
SELECT remainingBudget;
if remainingBudget >= amount:
    INSERT reservation;
    UPDATE budget_pool with the value computed in memory;
~~~

then two requests could both see the stale budget and either over-allocate or overwrite each other's updates. **An unprotected check-then-write is not equivalent to an atomic conditional update.**

### Error Checking, Rollback, and Retries

The application must check each statement's result. If `INSERT` returns 0 rows, **do not run `UPDATE`**. If `UPDATE` returns 0 rows, roll back the `INSERT`. Same `requestId` with a different amount must raise a conflict error rather than silently treating it as a valid retry.

When a client loses the response after `COMMIT`, retrying with the original `requestId` must not allocate extra funds. The system reads the existing reservation, verifies `tenant`/`budget`/`amount`/`expense_request_id` match, and returns the persisted outcome. `requestId` identifies **the command intent**, and does not replace `reservationId` or `ExpenseRequest`'s ID.

If the DB reports a deadlock, serialization failure, or connection drop with an uncertain commit outcome, retries must follow policy and **keep `requestId` stable**; never blindly generate a new ID and duplicate reservations.

## 8. Transitioning HELD to COMMITTED or RELEASED

A specific hold may be **committed at most once**. Never subtract \(H\) by a caller-supplied amount without verifying the reservation's state.

### Committing Held Funds

~~~sql
BEGIN;

UPDATE finance.budget_reservation
SET state = 'COMMITTED'
WHERE tenant_id = :tenant_id
  AND reservation_id = :reservation_id
  AND state = 'HELD'
  AND expires_at > clock_timestamp()
RETURNING budget_id, amount_vnd;

-- If 0 rows: do not touch budget_pool.
-- If 1 row: take actual budget_id and amount_vnd from RETURNING.

UPDATE finance.budget_pool
SET held_vnd = held_vnd - :returned_amount_vnd,
    committed_vnd = committed_vnd + :returned_amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :returned_budget_id
  AND held_vnd >= :returned_amount_vnd
RETURNING version;

-- If 0 rows: ROLLBACK entire transaction, report state mismatch.
COMMIT;
~~~

Verify **exactly one row in both `UPDATE`s** before `COMMIT`; bind `returned_*` parameters from the first query's output, never arbitrarily from the request. Transitioning state does not change \(H+C\), but moves held funds into committed funds. If already `COMMITTED`, a duplicate command must not re-increment \(C\); read the existing state to return the processed result.

In this example, `clock_timestamp()` reflects the time when the statement checks it. If policy strictly requires "never commit past the exact expiration instant," analyze decision timing, transaction duration, and the authoritative clock carefully; checking time at the start of a transaction does not guarantee it still holds at `COMMIT`.

### Releasing Held Funds

~~~sql
BEGIN;

UPDATE finance.budget_reservation
SET state = 'RELEASED'
WHERE tenant_id = :tenant_id
  AND reservation_id = :reservation_id
  AND state = 'HELD'
RETURNING budget_id, amount_vnd;

-- Only if exactly 1 row:
UPDATE finance.budget_pool
SET held_vnd = held_vnd - :returned_amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :returned_budget_id
  AND held_vnd >= :returned_amount_vnd;

-- If pool did not update exactly 1 row: ROLLBACK.
COMMIT;
~~~

If two workers cancel the same reservation concurrently, only one succeeds in moving `HELD` -> `RELEASED`. The other gets no `RETURNING` row and thus never deducts from the budget a second time. Expiration jobs follow **the same conditional transition pattern**, moving to `EXPIRED` while verifying expiration timestamps.

Converting a hold to committed only means **the budget allowance was consumed per policy**; it does not automatically mean the bank wired the money. Payment/Accounting may have their own lifecycles, reconciliation steps, and adjustment entries.

## 9. Contention Analysis: Where Is the Hot Spot?

Large aggregates typically slow down for two distinct reasons that should be separated:

**Logical contention:** every change increments the same version or locks the root's decision boundary. Independent updates collide when placed inside an overly broad root scope.

**Physical contention:** many transactions must update the same row/index/partition or hold locks for too long. Even after separating `ExpenseRequest` from `BudgetPool`, allocation commands still contend on the `BudgetPool` row because limit \(L\) is shared.

For illustration, if each transaction holds the budget row lock for an average of **25 ms**, a single row processed serially has a theoretical ceiling around **1 / 0.025 = 40 lock acquisitions per second** before accounting for queueing, I/O, and variance. This is **not** a PostgreSQL benchmark or throughput guarantee: actual lock hold times must be measured, and other transactions can run in parallel on other rows.

### Common Factors That Lengthen Lock Hold Times

- Loading or saving an entire object graph of thousands of members just to adjust one amount.
- Holding a database transaction open while making HTTP calls to Payment, sending email, or waiting on users.
- Maintaining too many synchronous indexes, triggers, or audit rows on a hot write path.
- Transactions locking multiple pools in inconsistent orders, causing deadlocks.
- A single transaction mutating unrelated aggregates just because a service shares DB credentials.
- Using optimistic locking on a heavily mutated root, causing retry storms.

**Prepare data and invoke external services before or after the transaction** whenever business semantics permit, keeping locked transaction sections as short as possible. Never move steps that genuinely require atomicity outside the transaction just to shorten lock duration.

## 10. Choosing Concurrency Mechanisms by Invariant Characteristics

| Mechanism | Advantages | Limitations / warnings |
| --- | --- | --- |
| **Optimistic locking** with `version` | Simple under low conflict; holds no DB lock during app computation | Hot roots cause heavy retries; must verify exact updated row count |
| **Pessimistic locking** (`SELECT ... FOR UPDATE`) | Serializes before mutating; convenient when checking multiple dependent rows | Adds wait time, deadlock risk; needs consistent lock ordering |
| **Conditional `UPDATE`** on a single row | Keeps check and update atomic for counters/limits | Row can still become a hot spot; all writers must use the same protocol |
| **`UNIQUE` / `CHECK` / `FK`** | Protects DB-expressible constraints across concurrent requests | Does not replace multi-row rules or domain state machines |
| **`SERIALIZABLE`** with retries | Prevents certain anomalies when read/write logic is sound | Can trigger serialization failures; must retry the whole transaction, not just the last SQL statement |
| **Pre-allocated quotas (escrow)** | Reduces reliance on a single central write row per operation | Harder to reclaim unused quota, rebalance shares, and guard total allocation |

**Isolation levels cannot fix a broken model.** `READ COMMITTED` with a conditional `UPDATE` on one row protects local counters very well. However, if the invariant is "no two rental bookings may overlap" across **multiple distinct rows**, running `SELECT` then `INSERT` under `READ COMMITTED` suffers *write skew*. That requires an appropriate constraint (such as a PostgreSQL exclusion constraint for time ranges), locking an authoritative parent resource, or choosing a suitable isolation level with retries.

Nor does a `SERIALIZABLE` transaction guarantee consistency **across two independent services**. It applies only within the database/transaction boundary where that mechanism operates.

### When to Use Optimistic Locking?

For `ExpenseRequest`, which few users edit simultaneously, optimistic locking on request version works well. For `BudgetPool`, where hundreds of allocation commands converge, `version` remains useful for admin edits and reconciliation, while **conditional allocation directly in the DB** avoids unnecessary read-modify-save loops and retries across the entire root.

If using `SELECT ... FOR UPDATE` to read the pool and compute changes, keep the transaction brief, always verify permissions and balances, and acquire locks in a fixed order whenever one command touches multiple pools.

## 11. When Must a Single Transaction Touch Multiple Aggregates?

The usual guideline is **one command modifies one aggregate at a time** to keep consistency boundaries crisp and reduce coupling. However, that is a design guideline, **not an absolute PostgreSQL restriction**.

For example, the requirement "approving `ExpenseRequest` **and** reserving `BudgetPool` must succeed or fail together":

- If both belong to the same application and the same PostgreSQL instance, one **local transaction** can update `ExpenseRequest` and `BudgetPool`/`Reservation` together. This is an intentional coupling between two roots; keep its scope tight and document why.
- If the two roots have separate lifecycles and immediate `APPROVED` display is unnecessary, `ExpenseRequest` can stay in `PENDING_BUDGET` and move to `APPROVED` only after the hold succeeds.
- If the two roots live in independent databases or bounded contexts deployed separately, a local SQL transaction cannot span both. You need a **coordinating workflow** with intermediate states and error handling.

### Why Not Embed Everything in One Aggregate Just to Get a Transaction?

A transaction spanning two roots in the same DB does not force you to merge them into one object graph with a shared lifecycle. Aggregate boundaries still clarify **who owns each invariant**, while a transaction is simply a tool solving a specific atomicity requirement. Conversely, stuffing everything into a huge aggregate still will not produce ACID across separate databases.

Whether a bounded context has multiple aggregates or a database uses multiple schemas does not tell you how far local transactions reach; inspect the actual deployment architecture and DBMS capabilities.

## 12. When Databases Must Be Split: Reservation Tokens and Compensation

Suppose `ExpenseRequest` belongs to Procurement and `BudgetPool` belongs to Finance, each with its own database.

~~~mermaid
sequenceDiagram
    participant U as Employee
    participant E as Procurement / ExpenseRequest
    participant B as Finance / BudgetPool
    participant P as Payment

    U->>E: SubmitExpense(expenseId)
    E->>E: Record PENDING_BUDGET
    E->>B: ReserveBudget(requestId, budgetId, amount)
    B->>B: Check budget limit + commit reservation
    B-->>E: Reserved(reservationId, expiresAt)
    E->>E: Record BUDGET_HELD
    E->>P: Initiate disbursement step per workflow
    P-->>E: Business outcome
    E->>B: CommitBudget or ReleaseBudget
    B-->>E: Hold transition outcome
    E->>E: Transition to appropriate final status
~~~

In this scenario:

- `BudgetPool` **must enforce \(H+C \le L\) directly inside Finance**. Never rely on a replicated budget copy in Procurement.
- `ReservationId`/token is **proof of a hold**, carrying expiration and status. Procurement must never mint a token locally and treat budget as reserved.
- `ReserveBudget`, `CommitBudget`, and `ReleaseBudget` all require **idempotency keys** or explicit duplicate-handling semantics.
- Handle cases where Finance succeeds in reserving budget while Procurement misses the response: query by `requestId` before retrying instead of reserving a second time.
- When a later step fails, run **compensation** such as `ReleaseBudget`; compensation is a controlled business command, not a cross-service ACID `ROLLBACK`.
- When communicating via a broker, use a transactional outbox/inbox or equivalent durable mechanism so post-commit notifications are never lost; consumers must still tolerate duplicate and delayed messages.

**Never use eventual consistency to relax strict invariants.** `ExpenseRequest` status can update asynchronously, yet Finance's budget limit must never be exceeded during synchronization. When a cross-service condition must hold strictly at a decision point, design **an authoritative arbitration point or strong coordination protocol**; never claim certainty merely because an event will arrive eventually.

## 13. When One Allocation Point Remains Too Hot: Conserving Quotas

Even after separating `ExpenseRequest`, a single `BudgetPool` row may still receive too many `UPDATE`s. One way to reduce contention is **pre-allocating spending rights** to independent units (**escrow quota**, **preallocated credits**).

Example: \(L\) = 100 million VND. Finance allocates:

| Processing group | Pre-allocated quota | Maximum local used/held |
| --- | ---: | ---: |
| Group A | 40 million | 40 million |
| Group B | 35 million | 35 million |
| Group C | 25 million | 25 million |
| **Total** | **100 million** | **Cannot exceed 100 million if each group respects its cap** |

Required conditions:

\[
\sum_i Q_i \le L,\qquad 0 \le U_i \le Q_i.
\]

If each group accepts expenses only within its own pre-allocated quota, total spending rights never exceed \(L\) without every request locking the single global budget row. **However, quotas must be granted and transferred between groups via atomically coordinated operations.** If Finance grants 40 million to Group A and grants that same 40 million to Group B before reclaiming it, total allocated rights can exceed the limit.

Important trade-offs:

- Group A may run out of quota while Group B still holds 20 million unused; the system needs quota transfer or reclamation mechanisms.
- Reclaiming allocated rights when a node loses connectivity is harder than incrementing/decrementing one central counter.
- Prevent quota duplication caused by retries, stale replicas, or partition changes.
- Global totals on reports may update with lag, while the global allocation ceiling still holds strictly.

**Sharding data does not automatically shard an invariant.** Simply partitioning a table by hashing `expense_request_id` while letting each shard compare against the full \(L\) allows the sum across shards to exceed \(L\). Pre-allocated quotas stay safe because the sum of granted quotas is capped upfront.

If limits are genuinely independent by **project + quarter + category**, you can model one `BudgetPool` root per combination instead of building complex escrow machinery. Split only when the business truly permits independent limits; a single shared global cap still requires either an allocation policy or centralized control.

## 14. Trade-Offs Across Storage Technologies

| Storage system | Implementation pattern | Points to watch |
| --- | --- | --- |
| **Relational** | `BudgetPool` in one row; `Reservation` in child table; transactional write commands with constraints | Hot rows, lock waits, isolation levels, indexes, root-only write control |
| **Document** | Embed bounded holds inside a `BudgetPool` document or use separate collections | Product's atomic update scope, document size limits, whole-document write conflicts |
| **Graph** | Link `Budget`, `ExpenseRequest`, `Employee`, `Project` via nodes/edges for impact analysis | Edges do not automatically enforce limits or cross-root transactions |
| **Analytical/Columnar** | `FactBudgetTransaction`, `factExpense`, and period/project dimensions | Projections help reporting, may lag, and must not decide fund allocations |

In a document database, embedding all reservations in one document can be convenient when counts are small and updates are atomic. But if reservations grow very large, the document grows unboundedly and updating one field still contends on the hot document. Choose embedding vs. referencing **based on invariants, workload, and product limits**, not just the "NoSQL" label.

In relational systems, multiple tables do not prevent forming one logical aggregate as long as the repository preserves transactions. In analytical warehouses, needing to JOIN `ExpenseRequest` with `BudgetPool` for KPIs does not make them one aggregate. **Read paths** can aggregate freely, while **write paths** must respect the source of truth.

## 15. Measuring and Testing Before Changing Boundaries

A design is sound when invariants hold and operations handle real load. Track these metrics:

| Metric | Meaning | Remedies when degraded |
| --- | --- | --- |
| p50 / p95 / p99 command duration | Latency, especially tail latency under contention | Separate DB time, lock waits, and external service calls |
| Lock wait / deadlocks | Contention and lock acquisition order | Shorter transactions, fixed lock ordering, touch fewer rows |
| Optimistic version conflicts | How many commands retry due to root changes | Narrow unnecessary conflict scope; consider conditional writes |
| Transaction abort/retry rate | Cost of isolation/constraint rejections | Safe retries, optimize locking strategy, revisit invariants |
| Rows/bytes loaded per command | Whether the aggregate loads too broadly | Optimize repositories and data boundaries |
| Throughput by `budgetId` | Which root is the hot spot | Segment by independent invariants or conserving quotas |
| Reservation wait/expiration times | Whether workflows stall or tie up funds too long | Deadlines, expiration sweepers, reconciliation, dashboards |
| Outbox lag / duplicate events | Health of asynchronous integration | Relays, retries, idempotency, monitoring |

### Mandatory Test Scenarios

**Scenario 1 — Two competing requests:** 70 million remains in the pool; two distinct requests each ask to hold 70 million. After all commits/rollbacks, at most one hold succeeds and \(H+C \le L\).

**Scenario 2 — Resending the same `requestId`:** the first request commits and its response is lost. Retrying with the same ID neither creates another reservation nor increments \(H\); if the payload differs, return a consistent error.

**Scenario 3 — Concurrent commit and cancel:** two commands target the same `HELD` reservation. Only one transition succeeds; never both increment \(C\) and release the same hold.

**Scenario 4 — Crash between two SQL steps:** `INSERT` reservation succeeds while `UPDATE` pool fails. The transaction rolls back; no "orphaned" `HELD` reservation remains miscounted.

**Scenario 5 — Concurrent limit reduction:** an admin lowers \(L\) while reservations arrive. Never commit a new \(L\) below \(H+C\).

**Scenario 6 — Two linked budgets:** transferring limit from Budget A to Budget B requires atomicity in the same DB with consistent lock ordering, or a cross-service workflow with compensating states if stored separately.

**Scenario 7 — Connection lost in uncertain state:** the client does not know whether `ReserveBudget` committed. It queries by `requestId` before deciding to retry, avoiding duplicate writes.

**Scenario 8 — Bypassing write path:** attempt to have a secondary service insert directly into reservations without updating the pool. It must be blocked by permissions, API/DB constraints/triggers, or detected and corrected per policy. Never rely on "trusting every team to remember."

Beyond domain unit tests, run **integration tests against a real database**, because locks, isolation, deadlocks, and unique constraints cannot be properly verified by a sequential mock repository.

## 16. Practice Exercise: Campaign Voucher Cap

**Context:** An e-commerce platform runs a campaign giving away 50,000 VND vouchers. In total, only **10,000 vouchers** may be issued; each customer may hold at most one active voucher. Tens of thousands of users click claim within seconds. A campaign has a name, description, eligibility rules, and edit history; each `Voucher` has lifecycle `ISSUED`, `REDEEMED`, `EXPIRED`, `CANCELLED`. Payment and marketing systems have separate databases.

### Tasks

1. If you bundle `Campaign`, all `Voucher`s, and `Customer` profiles into one aggregate, which parts truly belong in the same invariant boundary? What will become the contention hotspot?
2. Propose how to split **`CampaignQuota`** and **`Voucher`**. Which commands must be arbitrated at `CampaignQuota`?
3. Write the constraints "issue at most 10,000 vouchers" and "one customer holds at most one active voucher" as invariants; specify SQL/transaction mechanisms to protect them.
4. How should the system handle two users claiming the final voucher simultaneously, and one customer sending duplicate requests?
5. If `Voucher` and `CampaignQuota` live in two different databases, what intermediate states/grant tokens are needed? When a step fails, how does compensation work?
6. If a single `CampaignQuota` row becomes a hot spot, analyze partitioning quotas by region/group, explaining how to guarantee total grants never exceed 10,000.

### Solution Approach

- `Campaign` describes content, schedule, and eligibility; `Customer` has an independent profile. Voucher issuance authority belongs to **one authoritative quota source**. Never pull full profiles and history into one root just to enforce a cap.
- Use `CampaignQuota` holding `issuedCount` and `quotaLimit`; `Voucher` is an aggregate with its own lifecycle. When issuing, use a transaction with a conditional `UPDATE` checking `issuedCount < quotaLimit`, paired with `INSERT Voucher` and a partial `UNIQUE` on `(campaignId, customerId)` for active statuses. Verify exact row counts and roll back if unmet.
- Transitioning from "issued" to "redeemed" does not refund quota unless policy says so. Distinguish **total vouchers ever issued** from **currently active vouchers**: the two invariants have different formulas.
- Retries must use a stable `requestId` and never increment the count again. If `Voucher` runs in an independent service, `CampaignQuota` issues a single-use grant token and `Voucher` confirms the outcome; retries and compensation must never issue extra rights from the same token.
- If splitting the 10,000 quota into parts, the sum of pre-allocated quotas across parts must **not exceed 10,000**, and quota transfers must prevent concurrent usage on both source and destination.
- Marketing dashboards can use delayed analytical replicas; **never read issuance counts from a dashboard to decide the next voucher grant**.

## 17. Decision Checklist and Conclusion

Before locking down aggregate boundaries, answer:

- Can invariants that must hold **immediately after commit** be stated using concrete data and identifier scopes?
- Which unit has authority to allocate resources or change state? Do commands pass through that root?
- Which members genuinely require a single atomic decision, and which only relate by ID or serve reads?
- Do all write paths enforce constraints, versions/locks, and idempotency; are direct writes that break invariants blocked?
- Does a transaction touch one root or multiple? If multiple, is atomicity guaranteed by a shared DB or an explicitly designed workflow?
- Do the root's member count and contention level fit the workload; are p99 latency, lock waits, and retries measured rather than guessed?
- If partitioning quotas or sharding, can you prove **total allocated rights** still never exceed the limit?
- If an integration step fails or a commit outcome is uncertain, are intermediate states, retries, compensation, and reconciliation defined?
- Do the physical relational/document/graph/analytical structures serve both write invariants and read needs without confusing the source of truth?

**Conclusion:** Aggregate boundaries are a **reasoned trade-off**. Bundling too much data turns transactions and versions into bottlenecks; splitting in the wrong places breaks invariant protection. Sustainable design finds the exact **arbitration point for each rule**, narrows the data that must commit together, enforces conditions with suitable transactions/constraints, and distributes decision authority only when backed by a provably safe protocol. That yields a data model that reflects business logic, withstands real concurrency tests, and evolves cleanly as load grows.
