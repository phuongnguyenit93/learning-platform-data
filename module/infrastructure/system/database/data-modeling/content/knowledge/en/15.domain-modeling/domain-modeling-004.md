# Choosing Aggregate Boundaries from Invariants Instead of Copying Table Structures

## Learning Objectives

After this lesson, you will be able to:

- Identify **aggregate** boundaries from **business invariants** and write operations rather than looking at foreign key relationships or ERD diagrams.
- Write command preconditions and postconditions; distinguish constraints that must hold at commit time from goals requiring multi-step coordination.
- Compare aggregate options by invariant protection, lifecycle, data volume, write contention, and cost of change.
- Design aggregate roots that coordinate changes, govern references to other aggregates, and guard against concurrent updates.
- Map the design to relational schemas, constraints, indexes, and transactions; recognize when synchronization or asynchronous workflows are required.
- Validate boundary decisions using concurrency scenarios, change requests, and counterexamples.

In the **DATABASE_DATA_MODELING** module, the goal is to turn a business requirement into a model with clear entities, relationships, and constraints, then choose an appropriate physical structure. A common mistake is using an ERD as the template for the domain model: either every table becomes an aggregate, or all tables connected by foreign keys are lumped into one giant aggregate. Both approaches miss the most important question: **which data must change together so that a rule still holds after every transaction?**

## 1. Starting with a Problem: A Class with Limited Seats

Consider an online course enrollment platform where each class offering has a finite number of seats:

- An advanced Java class has **30 seats**.
- A student may hold at most **one active enrollment** for the same offering.
- Students get a **seat hold** for 10 minutes before paying; expired holds release the seat.
- Confirmations must never exceed 30 seats, even if hundreds of requests arrive simultaneously.
- A student's profile can change name or email without changing the identity of an enrollment record.
- Payment is handled by an external system; responses may be slow, duplicated, or fail.

Obvious nouns include Course, Offering, Student, Enrollment, SeatHold, and Payment. We can draw the relationships:

~~~mermaid
erDiagram
    COURSE ||--o{ OFFERING : opens
    OFFERING ||--o{ ENROLLMENT : has
    STUDENT ||--o{ ENROLLMENT : registers
    ENROLLMENT ||--o{ PAYMENT_ATTEMPT : requests
~~~

**This is a data relationship diagram, not an aggregate diagram.** It shows which records relate to each other; it does not answer who has the authority to confirm a seat, verify remaining capacity, or prevent two concurrent requests from taking the final seat.

If you bundle Course, Offering, Student, Enrollment, and Payment into one root just because links exist between them, you get a bloated model with conflicting lifecycles. Conversely, if each table is an independent aggregate and capacity is checked merely with a `SELECT` followed by an `INSERT`, two concurrent requests can both see "one seat remaining" and both write successfully.

## 2. Invariants Are the Input to Boundary Decisions

An **invariant** is a condition that must never be violated in valid business states that the system promises to uphold. During analysis, write down the exact **scope**, **when it must hold**, and **deciding authority**.

| Rule | Minimum data scope | When must it hold? | Expected owner |
| --- | --- | --- | --- |
| Occupied seats do not exceed capacity | One Offering / corresponding seat pool | Immediately when granting or releasing a seat commits | Seat Capacity / Enrollment |
| One student cannot have two active enrollments in the same Offering | Pair `(offeringId, studentId)` | Immediately after writing enrollment | Enrollment |
| Expired holds lose confirmation rights | One hold and its expiration timestamp | Before allowing confirmation | Seat Hold / Enrollment |
| Confirmed enrollment cannot alter committed price details | One enrollment and price at lock-in | Immediately after any enrollment change | Enrollment |
| System grants course access only after valid payment | Enrollment + Payment info | Upon completing the enrollment workflow | Coordinating workflow |
| Student email matches current profile email | One Student | When the profile is updated | Student |

The "do not exceed capacity" rule is an example of an **immediate invariant**: even if UI screens display stale numbers, the seat pool must never sell beyond 30. The "pay then grant access" rule can be a **multi-step workflow**: the system can stay in `HELD` or `PAYMENT_PENDING` before completion. Do not use eventual consistency in the payment flow as an excuse to allow overbooking capacity.

### Key Question: What Does "Immediately" Mean?

In a DBMS with ACID transactions, an atomic operation can modify multiple rows at once. However, transaction boundaries **do not automatically equal** aggregate boundaries:

- An aggregate is a **domain design decision** about the unit responsible for protecting invariants.
- A transaction is a **storage mechanism** that preserves atomicity on write.
- A single transaction can update multiple tables belonging to the same aggregate.
- In some monolithic systems, a transaction may also update **multiple aggregates** if an invariant genuinely requires it; this is a deliberate decision with coupling costs, not the default rule.
- If data resides in independent services or databases, never assume a local transaction spans all of them.

The goal is to **define the exact business commitment first**, then pick practical enforcement mechanisms that satisfy that commitment.

## 3. Why Table Structure Does Not Determine Aggregate Boundaries

### Mistake A: One Table Equals One Aggregate

Suppose the `Offering` table holds capacity and `Enrollment` holds student registrations. If both are written independently without synchronization, the following can happen:

1. Transaction T1 reads that the class has 1 seat left.
2. Transaction T2 also reads that the class has 1 seat left.
3. T1 inserts an active Enrollment.
4. T2 also inserts an active Enrollment.
5. Total enrollments exceed capacity even though each `INSERT` was individually valid.

A foreign key from `Enrollment` to `Offering` only guarantees that the Offering exists. **A foreign key does not enforce the rule "COUNT(active enrollments) <= capacity."** Therefore, you cannot conclude that two operations can write independently simply because they touch different tables.

### Mistake B: Every FK-Connected Table Belongs to One Aggregate

A Student can join many classes; a Course can open many Offerings; a Payment has its own processing/refund lifecycle. If an Offering root had to load and mutate student profiles, course curricula, and payment transactions, every change would drag in unrelated data and break responsibility boundaries.

An entity does not belong to an aggregate merely because it has an FK pointing to the root. Also ask:

- Does the entity have an **independent lifecycle**, or does it exist solely as part of the root?
- Does the root actually need to coordinate **every mutation** of that entity to protect an invariant?
- Does the entity need to be updated without reading/locking the root?
- If separated, can invariants be protected by constraints or another atomic command?

### Mistake C: Using Read Query Convenience to Define Write Boundaries

A "class details" page may combine course title, instructor, seat counts, and student roster. Needing to display them together does not mean they must commit together. You can use JOINs, read models, projections, or multi-source queries. **Read boundaries and write consistency boundaries serve two different purposes.**

## 4. A Six-Step Process for Designing from Invariants

### Step 1 — Write Commands in Business Language

Instead of "update Enrollment table," list concrete actions:

| Command | Issuer / source | Desired outcome |
| --- | --- | --- |
| `HoldSeat(offeringId, studentId, requestId)` | Student | One active seat hold or an explicit rejection |
| `ConfirmEnrollment(enrollmentId, paymentReference)` | Enrollment workflow | Confirmed enrollment, without allocating an extra seat again |
| `CancelEnrollment(enrollmentId)` | Student/admin per permissions | Cancelled status and seat hold released if applicable |
| `ExpireSeatHold(enrollmentId)` | Expiration processor | Expired hold loses seat reservation |
| `ChangeCapacity(offeringId, newCapacity)` | Admin | Valid new capacity, not lower than currently occupied seats |

Commands describe business intent, preconditions/postconditions, and failure behavior. Distinguishing commands from CRUD clarifies which aggregate owns the responsibility.

### Step 2 — Write Postconditions After a Successful Transaction

For example, for `HoldSeat`:

- If successful, there is exactly one active hold for the student in that Offering.
- Total occupied seats (`HELD` + `CONFIRMED`) do not exceed capacity.
- Retrying the same `requestId` does not increment occupied seat count.
- If sold out, the command fails and creates no half-baked hold record.

If you cannot state these conditions yet, choosing a root or writing new tables is premature.

### Step 3 — Classify Invariants by Ownership Scope

An `Enrollment` itself governs the transition `HELD` -> `CONFIRMED` and its locked-in price. A `Seat Capacity`/`Offering` must decide whether a seat is still available. Membership tiers or Payment status are data from another owner.

Classify each rule:

1. **Internal to one entity/value object:** positive quantity, valid time window.
2. **Across multiple members needing atomic commit:** capacity and seat holds.
3. **Across multiple aggregates in the same store:** can use controlled local transactions while weighing coupling costs.
4. **Across services/databases:** must design intermediate states, contracts, retries, and compensation unless a distributed transaction mechanism is deliberately chosen.

### Step 4 — Choose the Root Coordinating Changes

The root needs a meaningful identity (e.g., `offeringId`) and operations like `holdSeat`, `releaseSeat`, and `changeCapacity`. External callers must not mutate member status directly and bypass capacity checks.

The relationship to `Student` is kept via `studentId`; the relationship to `Payment` via `paymentReference` and verified outcomes. The root does not need to embed the full Student profile or internal payment gateway state.

### Step 5 — Evaluate Scale and Contention

If a class holds at most 30 students, loading active hold records alongside the Offering may be reasonable. If an online event has 100,000 seats and tens of thousands of requests per second, loading the entire list into a single root becomes a bottleneck.

Do not split blindly just to avoid locks: when capacity is **a shared limit**, every seat allocation command must still be arbitrated by a mechanism that preserves the global limit. Sharding by student without per-shard quotas can oversell seats.

### Step 6 — Map to Storage, Verify, and Refine

Only after understanding commands and invariants should you design keys, tables, constraints, versioning, indexes, transactions, and integration contracts. Test two users taking the last seat, one request sent twice, concurrent cancel and confirm, and capacity reduction while holds exist. If testing exposes contention or excessive data loading, refine the boundaries.

## 5. Option A: Offering as Root with Child Enrollments

For small classes with simple enrollment rules, **Offering** can serve as the aggregate root. Holds and enrollments for that Offering are members managed by Offering:

~~~mermaid
flowchart TB
    App["Enrollment use case"]
    App -->|"holdSeat(studentId)"| Root

    subgraph B["Offering Aggregate"]
      Root["Offering (root)"]
      SeatA["Enrollment A (child entity)"]
      SeatB["Enrollment B (child entity)"]
      Root -->|"manages holds"| SeatA
      Root -->|"manages holds"| SeatB
    end

    Student["Student aggregate"]
    Payment["Payment aggregate"]
    Root -.->|"studentId"| Student
    Root -.->|"payment reference"| Payment
~~~

A valid `holdSeat` reads root state, checks remaining seats, prevents duplicate students, adds an Enrollment, and commits everything as one operation. The root enforces:

- capacity and total valid holds/confirmations;
- no duplicate active enrollment per student;
- state transitions and hold expiration;
- never reducing capacity below occupied seats.

**Pros:** closely mirrors business rules; easy to see every change affecting seat limits; can span multiple tables within one transaction. **Cons:** the root can bloat as enrollment count grows or unbounded history accumulates; all requests contend on the same Offering, causing locking/contention.

An `enrollment` table having an `offering_id` foreign key does not automatically make it a child entity. The reason to group them is that **the commands are protecting Offering's own invariants** and the member count is manageable.

### Relational Implementation for Option A

You can use `offering` and `enrollment` tables, provided all enrollment write paths go through Offering operations within the same transaction. One option when row counts are small:

~~~text
BEGIN
  Lock the Offering row with SELECT ... FOR UPDATE
  Read count of Enrollments currently HELD or CONFIRMED
  Verify seats remain and student has no active enrollment
  Insert Enrollment / update status via domain operation
COMMIT
~~~

Locking the Offering row **only protects invariants** if every write path affecting seat counts obeys the same locking protocol. Another application allowed to `INSERT` directly into `enrollment` without locking the root can break the invariant; restrict write privileges and add database-level constraints/controls.

## 6. Option B: SeatPool and Enrollment with Separate Lifecycles

For high traffic, or when Enrollment must live long-term to manage certificates, refunds, and class transfers, you can split them:

- **`SeatPool`** identified by `offeringId`, managing capacity and occupied count. Local invariant: `0 <= seatsTaken <= seatsTotal`.
- **`Enrollment`** having `enrollmentId`, `studentId`, `offeringId`, statuses `HELD`/`CONFIRMED`/`CANCELLED`/`EXPIRED`, price snapshot, and business history.
- **`Student`** and **`Payment`** remain separate aggregates with their own ownership.

~~~mermaid
flowchart LR
    C["HoldSeat command"] --> P["SeatPool root<br/>grants seat occupancy"]
    C --> E["Enrollment root<br/>enrollment lifecycle"]
    E -.->|"offeringId"| P
    E -.->|"studentId"| S["Student"]
    E -.->|"paymentReference"| T["Payment"]
~~~

**Important trade-off:** two separate roots do not automatically uphold the invariant "`seatsTaken` equals the number of active enrollments." If `SeatPool` and `Enrollment` reside in the same PostgreSQL database, the application can update both roots in **one local transaction** to protect that relationship. This is a conscious choice, even though aggregate guidelines typically advise minimizing cross-root transactions.

If the two roots reside in two independent databases, the protocol must change: `SeatPool` can issue a unique **reservationId/token** and enforce the capacity invariant at the source; `Enrollment` persists the outcome using a stateful workflow, retries/idempotency, and compensation on failure. Never downgrade "do not exceed capacity" to eventual consistency merely because services were split.

| Criterion | Offering contains Enrollment (A) | SeatPool + Enrollment (B) |
| --- | --- | --- |
| Capacity owner | Offering root | SeatPool root |
| Enrollment lifecycle | Coupled to Offering | Enrollment is more independent |
| Load/mutation cost | Grows with member count | Updates a small counter; Enrollment handled separately |
| Write contention | Concentrated on Offering | Seat allocation still has a shared arbitration point at SeatPool |
| Cross-record rules | Consistent inside the aggregate | Requires a transaction or explicit allocation protocol |
| When appropriate | Bounded groups, stable rules | High load, long history, separated responsibilities |

Neither option fits every system. Choosing B must be driven by **analyzed** lifecycle independence, scale, or throughput needs—not simply because two tables exist.

## 7. Implementing Option B in PostgreSQL

The following example scopes down to a single database to illustrate **a seat-hold transaction that never exceeds capacity**. Course, Student, and Payment data are owned by other models and have no DDL in this example.

~~~sql
CREATE SCHEMA IF NOT EXISTS academy;

CREATE TABLE academy.offering_capacity (
    offering_id UUID PRIMARY KEY,
    seats_total INTEGER NOT NULL CHECK (seats_total > 0),
    seats_taken INTEGER NOT NULL DEFAULT 0 CHECK (seats_taken >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    CONSTRAINT capacity_not_exceeded CHECK (seats_taken <= seats_total)
);

CREATE TABLE academy.enrollment (
    enrollment_id UUID PRIMARY KEY,
    offering_id UUID NOT NULL
        REFERENCES academy.offering_capacity(offering_id),
    student_id UUID NOT NULL,
    request_id UUID NOT NULL UNIQUE,
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'EXPIRED')),
    hold_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- No two active Enrollments for the same student and Offering.
CREATE UNIQUE INDEX one_active_enrollment_per_student
    ON academy.enrollment (offering_id, student_id)
    WHERE status IN ('HELD', 'CONFIRMED');

-- Helps locate and process holds that need to expire.
CREATE INDEX enrollment_held_expiry
    ON academy.enrollment (hold_expires_at)
    WHERE status = 'HELD';
~~~

**Constraint rationale:**

- The `CHECK` on `offering_capacity` protects the source row's bound: occupied seats never exceed published seats.
- The partial `UNIQUE` index prevents two **active** enrollments for the same student in the same Offering while still retaining `CANCELLED`/`EXPIRED` history. If business rules forbid re-enrolling after cancellation, adjust the uniqueness rule accordingly.
- `request_id` distinguishes a new hold command from a retry of the same operation. A brand-new command after cancellation must use a new `request_id`.
- `hold_expires_at` must be checked during confirmation and by the expiration sweep job. Storing a timestamp does not make the DB transition status automatically as the clock advances.
- The expiration index helps periodic jobs find `HELD` rows; indexes should be evaluated against actual row counts and workload.

### Transaction to Acquire a Seat

The flow below runs in **one transaction**. The application must inspect the outcome of each statement before proceeding:

~~~sql
BEGIN;

-- 1. Register an active hold request.
INSERT INTO academy.enrollment
    (enrollment_id, offering_id, student_id, request_id,
     status, hold_expires_at)
VALUES
    (:enrollment_id, :offering_id, :student_id, :request_id,
     'HELD', :hold_expires_at)
ON CONFLICT DO NOTHING
RETURNING enrollment_id;

-- If 0 rows returned: ROLLBACK immediately; do not run step 2.
-- Distinguish a request_id retry from a duplicate-student conflict,
-- then return the existing result or appropriate business error.

-- 2. Allocate seat only if capacity remains; UPDATE is atomic.
UPDATE academy.offering_capacity
SET seats_taken = seats_taken + 1,
    version = version + 1
WHERE offering_id = :offering_id
  AND seats_taken < seats_total
RETURNING offering_id, seats_taken;

-- If 0 rows returned: ROLLBACK both INSERT and UPDATE; report sold out
-- or non-existent Offering.

COMMIT;
~~~

When two students race for the 30th seat, PostgreSQL serializes the two conditional `UPDATE`s on **the same row**. After the first transaction updates it, the second evaluates the predicate against the new state and cannot increment past `seats_total`. This holds as long as all related operations follow the corresponding workflow/constraints with no bypassing write paths.

When the same `request_id` is retried after commit because the client lost the response, `INSERT` returns 0 rows due to the `UNIQUE` conflict. The application **does not increment `seats_taken` again**; instead, it looks up the enrollment for that `request_id` and returns the corresponding result. Two different `request_id`s for the same student are caught by the partial unique index.

**Scope limitation of the example:** the `CHECK` only verifies `seats_taken` is within bounds; it **does not** compare `seats_taken` against the count of `HELD`/`CONFIRMED` rows. Equality between the counter and the records must be protected by transactions across every state-changing command, restricted write permissions, and verification/reconciliation checks. If the system must even guard against arbitrary ad-hoc SQL writes, additional database-level mechanisms and access controls are required.

### Releasing a Seat Without Double-Decrementing

When cancelling or expiring a hold, update `Enrollment` status and decrement the counter in **the same transaction**, only if the hold was still occupying a seat:

~~~sql
BEGIN;

UPDATE academy.enrollment
SET status = 'EXPIRED'
WHERE enrollment_id = :enrollment_id
  AND status = 'HELD'
  AND hold_expires_at <= CURRENT_TIMESTAMP
RETURNING offering_id;

-- If 0 rows returned: do not decrement seats_taken; ROLLBACK/finish appropriately.
-- If 1 row returned: use the returned offering_id for the next step.

UPDATE academy.offering_capacity
SET seats_taken = seats_taken - 1,
    version = version + 1
WHERE offering_id = :returned_offering_id
  AND seats_taken > 0;

-- Verify exactly 1 row; otherwise ROLLBACK to avoid data drift.
COMMIT;
~~~

Two workers simultaneously trying to expire an Enrollment contend for the lock on that Enrollment row; only the one that successfully transitions `HELD` to `EXPIRED` decrements the counter. On `CONFIRMED`, transitioning `HELD` to `CONFIRMED` **does not increment occupied seats again**, because the seat was already counted when held.

If a confirm command and an expire command arrive concurrently, the outcome must be decided based on the status and **expiration timestamp at processing time**. Confirmation is only valid if still `HELD`, not expired, and payment evidence satisfies policy. Never accept an old Payment event to revive an already expired hold.

### Changing Capacity Is Also an Invariant-Guarded Command

An administrator cannot arbitrarily set `seats_total = 20` when 25 seats are already occupied. Conditional operation:

~~~sql
UPDATE academy.offering_capacity
SET seats_total = :new_total,
    version = version + 1
WHERE offering_id = :offering_id
  AND :new_total > 0
  AND :new_total >= seats_taken
  AND version = :expected_version;
~~~

The application must check updated row counts, handle conflicts, and clearly report why the reduction failed. If reducing capacity affects already-sold contracts, approval/refund workflows may be needed beyond arithmetic checks.

## 8. When Invariants Cross Database or Service Boundaries

Suppose Payment is an independent service. `HoldSeat` only grants a **hold** in `SeatPool`; it does not directly write bank status. The flow can look like this:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Enrollment
    participant S as SeatPool
    participant P as Payment

    U->>A: Request enrollment (requestId)
    A->>S: HoldSeat (offeringId, studentId)
    S-->>A: Reserved (reservationId, expiresAt)
    A-->>U: HELD, awaiting payment
    A->>P: AuthorizePayment (paymentRequestId)
    P-->>A: PaymentAuthorized (paymentId)
    A->>S: ConfirmHold (reservationId)
    S-->>A: Confirmed or Expired
    A-->>U: Confirmed or handle failure
~~~

In this scenario, `SeatPool` must protect **allocated seat count** right at the `HoldSeat` step. `Enrollment` may temporarily stay in `HELD`/`PAYMENT_PENDING`. When Payment succeeds after the hold has already expired, the workflow must handle the failure as a business case (e.g., void authorization or refund) rather than granting access without a seat.

Mandatory design elements:

- **Idempotency:** `requestId` and `reservationId` ensure retries do not allocate two seats; `paymentRequestId` ensures payment commands do not charge multiple times.
- **Intermediate states:** `HELD`, `CONFIRMED`, `EXPIRED`, `CANCELLED`, and Payment statuses per the payment provider's contract.
- **Deadlines:** expiration timestamps are checked by the hold-owning authority, never trusting the browser's clock alone.
- **Messaging:** use `eventId`, versions, or sequence numbers as needed to detect duplicates and out-of-order delivery.
- **Reliable event publishing:** when using a broker, transactional outbox/inbox patterns help write data and record messages in a local transaction while handling retries.
- **Compensation and reconciliation:** release holds, void authorizations, or issue refunds depending on what actually occurred; compensation is not a cross-system rollback.

A workflow that accepts eventual consistency for `Enrollment` status can still maintain strict invariants inside `SeatPool`. These two consistency levels do not conflict when ownership boundaries are clearly defined.

## 9. Testing Boundary Decisions with Counterexamples

| Scenario | Analysis required | Impact on design |
| --- | --- | --- |
| Two students take the last seat | Check the same capacity source, atomic operation, do not trust stale SELECT | Root/locking mechanism at the seat-granting source |
| One student sends two different `requestId`s | `UNIQUE` on `(offeringId, studentId)` filtered by status | Protects per-student rule alongside capacity |
| Client retries the same `requestId` | Command must return the same outcome without incrementing counter again | Store idempotency record and reconcile results |
| Payment succeeds after hold expires | Must verify active hold when confirming | Compensation/refund flow; do not conjure seats arbitrarily |
| Admin lowers capacity during active holds | Same write source with `seats_taken <= seats_total` | Use lock/version and conditional UPDATE |
| Class has 100,000 students | Root holding all Enrollments is expensive to load/save | Consider a compact SeatPool and separate Enrollment root |
| Accounting needs per-course reports | Multiple tables/aggregates must be JOINed on read | Dedicated read model; do not bloat the write aggregate |
| Transfer student from Offering A to B | If granting B and releasing A must happen together, constraint spans two pools | Multi-row transaction in same DB or compensation workflow |

Two decisive questions:

1. If a transaction **succeeds locally** but the next step has not completed, which data must still strictly hold true?
2. If two requests arrive **at the same time**, what arbitration point prevents the system from accepting two conflicting outcomes?

If you cannot point to concrete answers, the aggregate boundaries lack verification.

## 10. How Choices Affect the Physical Model

Aggregate boundaries are a domain decision; storage choices should serve them rather than dictate them:

| Storage approach | Example model | Risks to evaluate |
| --- | --- | --- |
| **Relational** | Offering/SeatPool and Enrollment in one or more tables; transactions, UNIQUE, CHECK, FK | Write paths bypassing root, lost updates, long locks, contention |
| **Document** | One Offering document holding holds if small; or separate SeatPool and Enrollment documents | Document size, update atomicity scope, write conflicts on the same document |
| **Graph** | Student, Offering, Enrollment as multi-dimensional relationships for learning network queries | Edge traversal does not solve capacity invariants or transactions |
| **Analytical/Columnar** | `FactEnrollment`, Course/Student dimensions, historical data | Projections may lag and should not arbitrate seat allocation |

When designing physical tables, check:

- **Primary key:** What is the root's ID, and what is a child entity's identity within the root's scope?
- **Foreign keys:** Which relationships are DB-enforced inside the same ownership boundary, and which are references to external sources?
- **Constraints:** Which invariants are protected by `UNIQUE`, `CHECK`, `FK`, and partial indexes, and which require transactions?
- **Indexes:** Do queries by `offeringId`/`studentId`, `requestId` lookups, hold expiration sweeps, and reports genuinely require index support?
- **Historical data:** Do committed prices, policy versions, and registration timestamps require snapshots?
- **Write cost:** Does a root create a **hot row**, deadlocks, long-running transactions, or excessive version conflicts?

**Do not infer that every aggregate requires its own microservice.** A monolithic system with clearly owned modules and local transactions can be a great design. Split deployments only when operational independence benefits outweigh integration overhead.

## 11. Exercise: Choosing Boundaries for Equipment Rental

**Context:** A camera rental company operates multiple warehouses. A single contract can rent multiple devices; each device has its own serial number, rental start/end dates, and maintenance status. A single device cannot be allocated to two contracts with **overlapping rental periods**. Customers can pay a deposit via an external payment gateway. Management reports need revenue, device status, and contracts grouped by warehouse.

**Tasks:**

1. List at least four business commands and write their corresponding invariants.
2. Choose aggregate roots for the rental contract and for allocating one device over a time period. Should contracts, customers, devices, and payments all be merged into one aggregate?
3. Propose a way to prevent two contracts from renting the same device for overlapping times under concurrent write requests.
4. When a contract rents three devices and the customer requires **confirming only if all three are available**, how do you protect this condition?
5. If the system uses PostgreSQL and separates device allocation from the contract, what constraints/transactions and compensation steps are needed? How should management reports read data?

**Guided solution approach:**

- Commands could include `CreateRental`, `ReserveDevice`, `ConfirmRental`, `CancelRental`, and `ReturnDevice`. Invariants: rental start is before end; one serial cannot have two active allocations with overlapping periods; a confirmed contract cannot arbitrarily change locked-in prices/configuration; a device under maintenance cannot be allocated if policy forbids it.
- `RentalContract` is the root for rental lines and locked-in prices. Device reservation/allocation rights should be managed by the authoritative source for device schedules, such as a `DeviceSchedule` or `DeviceAllocation` aggregate depending on scale and concurrency strategy. `Customer` and `Payment` have independent lifecycles.
- With PostgreSQL, consider an **exclusion constraint** on `serialId` and the time range for records actively occupying a device; or consistent transactions and locking at the allocation source. Simply checking "no overlap" with `SELECT` followed by an unprotected `INSERT` is insufficient under concurrency.
- Requiring all three devices is a **cross-allocation** condition. If in the same database and updated in a single transaction with consistent lock ordering, they can commit atomically. If spread across services, you need a partial-reservation workflow, timeouts, compensation, and contract confirmation only after all allocations succeed.
- Payment needs idempotency and deposit refund/void handling when device allocation fails. Reports can use JOINs or projections by warehouse and time; reporting needs do not dictate write aggregate boundaries.

**Self-check:** if a proposed solution creates a "Warehouse" aggregate containing every device, contract, and customer history, identify which invariant truly requires all that data in one transaction. If none exists, that is a sign the aggregate was inflated by table relationships or reporting needs.

## 12. Boundary Decision Checklist

- Are business commands written in terms of **intent**, preconditions/postconditions, and failure outcomes?
- Does every invariant have an explicit data scope, enforcement timing, and owner?
- Which root is authorized to receive commands and protect invariants? Can child entities be mutated directly via other write paths?
- Is consistency maintained via **one aggregate**, an intentional multi-root transaction, DB constraints, or a cross-service protocol? Why?
- Are FK relationships, JOIN needs, or UI screens being confused with aggregate membership?
- Do member count, mutation frequency, and contention hotspots fit the chosen root?
- Have duplicate commands, mid-flight failures, expirations, write conflicts, and capacity changes been tested?
- Are historical data and external ownership handled via IDs, snapshots, and proper contracts?
- Do the physical relational/document/graph/analytical structures serve real invariants and query workloads?

**Conclusion:** Aggregates are chosen from **the invariants that must be protected during business operations**, not mechanically derived from table counts, foreign key lines, or JOIN needs. When boundaries are sound, the aggregate root controls change tightly, transactions/constraints enforce commitments, and external relationships are integrated intentionally. This approach yields data models that are clear, verifiable, and able to evolve as scale or deployment changes.
