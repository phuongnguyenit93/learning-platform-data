# Compensating Actions, Update Conflicts, and Optimistic Locking

## 1. The problem: two requests modifying the same state

Cloud applications frequently receive concurrent requests from web clients, mobile apps, workers, and integrated services. Two users may edit the same reservation; two workers may process the same message; a payment flow may complete at the provider while the response times out. If a system simply reads data, computes, and writes back without checking whether state changed in between, one update can silently overwrite another.

Two groups of techniques typically work together:

- **Optimistic concurrency control:** allows multiple parties to read the same state, but on write requires confirming that the data is still at the version the operation read. If an intervening change occurred, the operation is rejected so the caller re-reads and resolves the conflict.
- **Compensation:** when a multi-step process has already produced certain effects but cannot complete, the system performs reverse or corrective business actions to bring state to an acceptable outcome. This is not always an exact rollback like a database transaction.

For example, a customer books an apartment. Booking service holds the slot, Payment service requests funds, and then the system confirms the reservation and sends a notification. If payment fails, the system can release the hold. If payment succeeds but the booking confirmation step fails, a refund or reconciliation may be required. Meanwhile, if two customers book the same schedule simultaneously, the system must prevent overwriting updates that would let both believe they secured the slot.

In the **CLOUD_ARCHITECTURE** module, these decisions connect directly to reliability, data consistency, scalability, cost, and operations. Especially in distributed architectures, you cannot assume a single ACID transaction spans multiple databases, queues, and external providers.

### Learning objectives

After this lesson, you will be able to:

1. Explain lost updates, stale writes, and common update conflicts.
2. Design optimistic locking using version numbers, appropriate timestamps, or HTTP `ETag`/`If-Match`.
3. Handle conflicts safely by re-reading, merging changes, or asking the user to decide.
4. Distinguish database rollback, retries, and business compensation.
5. Model multi-step processes with Sagas, state machines, and compensating actions.
6. Design idempotency, timeouts, retries, reconciliation, and compensation state observability.
7. Test update contention and partial-failure scenarios in cloud architectures.

## 2. Identifying update conflicts

### 2.1. Lost update

Suppose a reservation has 2 guests and two users open the screen at time T0:

1. User A reads `guestCount = 2`.
2. User B also reads `guestCount = 2`.
3. A edits it to 3 and writes to the database.
4. B edits it to 4 based on the stale copy and overwrites.
5. The final result is 4; A's change vanished without anyone being notified.

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant DB as Database
    A->>DB: Read guestCount = 2
    B->>DB: Read guestCount = 2
    A->>DB: Write guestCount = 3
    DB-->>A: Success
    B->>DB: Write guestCount = 4 (based on stale value)
    DB-->>B: Success, overwrites A
~~~

This is a **lost update**: a later write overwrites an earlier change because there is no version check or appropriate synchronization mechanism.

### 2.2. Other forms of conflict

| Type | Description | Example |
|---|---|---|
| **Lost update** | An update is overwritten by another update based on stale data | Two staff members edit the same customer address |
| **Stale write** | Client writes based on an outdated version | Offline app submits an old profile snapshot |
| **Write-write conflict** | Multiple transactions modify the same record or data region concurrently | Two requests change booking status simultaneously |
| **Check-then-act race** | Check a condition then act, but the condition changes in between | Two requests both see one room left and both book |
| **Duplicate command** | A command executes multiple times due to retries/redelivery | Worker receives a payment collection message again |
| **Non-repeatable read** | A transaction reads the same data twice and sees different values due to another committed transaction | A business flow reads balance before and after another transaction |
| **Phantom / read skew** | Reading a dataset or multiple records no longer reflects one consistent snapshot | Checking total quota and active bookings in two queries at different times |

Not every system needs to solve every anomaly with the same mechanism. Identify **business invariants** (conditions that must always hold), transaction boundaries, and required consistency levels.

## 3. Pessimistic locking and optimistic locking

Two common approaches to protecting concurrent updates:

| Criterion | Pessimistic locking | Optimistic concurrency |
|---|---|---|
| Assumption | Conflicts occur frequently enough to require locking upfront | Conflicts are relatively rare; verify on write |
| How it works | Holds locks for the duration of the operation/transaction | Reads version, writes conditionally against expected version |
| On conflict | Other requests wait, time out, or fail due to locks | One request succeeds; requests using stale versions receive conflict |
| Advantages | Can simplify certain operations needing serialization | Avoids long-held locks; fits read-heavy, low-contention workloads |
| Risks | Deadlocks, lock contention, timeouts, reduced throughput | Callers must handle conflicts and retry/merge |
| Suitable for | Short critical sections, hot data, invariants requiring serialization | Profile-editing APIs, resources with many reads and low/moderate contention |

**Optimistic locking does not mean zero concurrency control.** It still uses an atomic conditional write at the database or storage service. The difference is that it does not hold an exclusive lock for the entire time the client is reading and editing.

Do not choose solely on the slogan "lock-free is faster." On a very hot resource updated continuously by many clients, optimistic retries can cause frequent failures and higher load. Pessimistic locking or partitioning/serialized commands may be a better fit.

## 4. Optimistic locking with version numbers

### 4.1. Principle

Each record has a version field that increments on every successful update. Clients read data along with its version; on write, the statement succeeds only if the current version still equals the version the client read.

Suppose a reservation initially has `version = 7`:

1. A and B both read version 7.
2. A writes changes conditioned on `version = 7`; the database updates and increments version to 8.
3. B writes conditioned on `version = 7`; no record matches the condition.
4. B receives a conflict, re-reads version 8, and decides to merge, retry, or prompt the user to review the newer changes.

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant DB as Database
    A->>DB: Read value, version=7
    B->>DB: Read value, version=7
    A->>DB: UPDATE ... WHERE version=7
    DB-->>A: 1 row updated, version=8
    B->>DB: UPDATE ... WHERE version=7
    DB-->>B: 0 rows updated (conflict)
    B->>DB: Read latest value, version=8
    DB-->>B: Latest state
    B->>B: Merge, retry, or ask user
~~~

### 4.2. SQL example

~~~sql
CREATE TABLE reservations (
    reservation_id VARCHAR(40) PRIMARY KEY,
    guest_count INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1
);
~~~

A client read version 7 and wants to change `guest_count`:

~~~sql
UPDATE reservations
SET guest_count = 3,
    version = version + 1
WHERE reservation_id = 'rs-1732'
  AND version = 7;
~~~

The application checks the affected row count:

- **1 row:** update succeeded, version incremented.
- **0 rows:** the record may not exist or the version changed; distinguish these using appropriate lookup/authorization rules.

Execute the update in a single atomic database operation. Reading the version first and then issuing an unconditional write still suffers from races. The version must increment on **every write path**: APIs, workers, batch jobs, admin tools, and migrations modifying business data. If any path bypasses the version, lost-update protection becomes unreliable.

### 4.3. Version numbers differ from timestamps

Timestamps can serve as version tokens in some systems, but you must evaluate precision, clock sync, two updates within the same clock resolution, timezones, and how the provider generates values. A monotonically increasing counter or database-issued concurrency token is usually clearer for concurrency checks.

Never use a client-supplied timestamp as sole proof of the latest version. Client clocks can drift, and requests can arrive at servers out of order.

## 5. Optimistic locking at the HTTP layer: ETag and If-Match

HTTP provides validators so clients update a representation only when the resource still matches the version the client read.

### 5.1. Reading a resource and receiving an ETag

~~~http
GET /v1/reservations/rs-1732
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
ETag: "reservation-v7"
Content-Type: application/json

{
  "id": "rs-1732",
  "guestCount": 2,
  "status": "PENDING"
}
~~~

Client updates with the validator:

~~~http
PATCH /v1/reservations/rs-1732
If-Match: "reservation-v7"
Content-Type: application/merge-patch+json

{
  "guestCount": 3
}
~~~

If the representation still matches the validator, the API performs the update and returns a new validator. If it changed, the server returns **412 Precondition Failed** because the `If-Match` condition no longer holds.

### 5.2. Related status codes

| Status | Typical meaning | How the client reacts |
|---|---|---|
| **200 OK** | Update succeeded and returns representation | Use new body/ETag |
| **204 No Content** | Update succeeded, no body | Store new ETag if present |
| **409 Conflict** | Conflict with business semantics or current state | Display/handle conflict per API contract |
| **412 Precondition Failed** | HTTP precondition such as `If-Match` not met | Re-read resource and merge or ask user |
| **428 Precondition Required** | Server requires client to send a precondition per policy | Re-read and send `If-Match` |

Distinguish 409 from 412 in your contract. When an API uses `If-Match` for concurrency control, 412 clearly expresses that the precondition no longer holds. 409 can express other business conflicts, such as inability to cancel a completed booking.

### 5.3. ETag is not always a database version

An ETag is a validator for a representation; it can be a hash or an opaque token. The API must ensure validator generation and comparison detect changes relevant to the representation and update operation. Do not leak sensitive internal information in ETags.

Weak ETags prefixed with `W/` cannot be used for strong matching with `If-Match`. If an API requires exact update preconditions, use strong ETags or an explicitly designed concurrency token.

## 6. Conflict handling: do not always retry blindly

When receiving an optimistic conflict, the client or service must know **which changes can be merged safely**.

### 6.1. Strategies

| Strategy | Use when | Example |
|---|---|---|
| **Read–merge–write** | Changes are independent and have merge rules | A changes phone number, B edits address |
| **Retry after re-read** | Operation can be recomputed on the new state | Conditional counter increment |
| **Reject and prompt user** | Changes involve choices that cannot be auto-merged | Two users pick different times for one schedule |
| **Field-level update** | Fields are independent, still respecting permissions and invariants | `PATCH` one property instead of `PUT`ting the whole object |
| **Serialize commands** | Hot data requiring ordered processing | One queue/partition per resource ID |
| **Domain-specific merge** | Deterministic business rule exists | Add quantity deltas rather than writing absolute values |

### 6.2. Merge example

Suppose A changes the phone number and B changes the address. If the two changes are independent and both valid against the latest state, the system can fetch the latest copy and reapply the caller's field. However, if both change the check-in date and that affects availability/pricing, you cannot pick one value automatically without a business rule.

Do not automatically merge arrays, payment states, access permissions, or invariant-coupled fields merely because they sit in different columns.

### 6.3. Retries must be bounded

A sensible retry loop:

1. Read current state and version.
2. Recompute the change from the original command against the new state.
3. Attempt a version-conditioned write.
4. If it still conflicts, enforce limits on attempts/total duration.
5. If limits are exceeded, return a comprehensible conflict or route to serialized processing.

Unbounded retries worsen hot-resource contention and increase database load. For client requests, it is usually better to return a conflict so the client reloads rather than having the server silently retry many times without user awareness.

## 7. Protecting invariants: check-then-act must be atomic

A serious bug occurs when an application splits checking and writing into two unprotected operations.

Example: an apartment has one remaining spot. Two requests run concurrently:

~~~text
Request A: SELECT available_count -> 1
Request B: SELECT available_count -> 1
Request A: INSERT reservation
Request B: INSERT reservation
~~~

Without database constraints, transaction isolation, or an appropriate atomic update mechanism, both can succeed.

One option is a conditional update:

~~~sql
UPDATE inventory
SET available_count = available_count - 1,
    version = version + 1
WHERE property_id = 'home-25'
  AND available_count > 0
  AND version = 12;
~~~

The application treats the spot as held only when one row was updated. Otherwise, re-read state and handle per business rules. Depending on the problem, you may need unique/exclusion constraints for non-overlapping date ranges, appropriate transactions, or a dedicated reservation/hold model.

**An optimistic version alone does not guarantee every complex invariant.** If an invariant spans multiple records or tables, checking one row's version may be insufficient. Place transaction boundaries and constraints at the authoritative decision owner.

## 8. How do transactions, rollbacks, and compensation differ?

Three concepts are frequently conflated:

- **Database transaction rollback:** cancels uncommitted changes inside an ACID transaction within the scope controlled by the database.
- **Retry:** re-attempts an operation after an error considered transient or after reading fresh state.
- **Compensation:** creates a new business operation to offset committed effects from an earlier step in a distributed workflow.

For example, the DB committed booking state, the payment provider charged funds, and an email was sent. No single rollback button can atomically rewind all three systems. The system needs **compensating actions**: cancelling/adjusting the booking, refunding via the provider, and possibly sending an update notice.

| Aspect | Transaction rollback | Compensation |
|---|---|---|
| Scope | One transaction controlled by a transaction manager/database | Multiple operations/services completed at different times |
| Atomicity | Uncommitted changes roll back per DB semantics | Not atomic across all systems |
| Timing | Before or upon commit failure | After one or more steps have produced effects |
| Outcome | State as before the transaction | New business state offsetting/adjusting prior effects |
| Failure modes | Transaction rollback has specific DB mechanics | Compensation can also fail, retry, need reconciliation, or manual intervention |
| Example | Updating booking and outbox in the same transaction errors out | Charged payment but booking cannot confirm, requiring a refund |

**Compensation does not erase history.** A refund does not make the charge as if it never happened; it creates a new transaction referencing the prior one. Preserving history is essential for audits, reconciliation, and disputes.

## 9. Saga: coordinating steps and compensating actions

A Saga is a pattern for managing distributed processes composed of multiple local transactions. Each step commits in a separate service/database; if the process cannot continue, compensating steps execute according to designed rules.

### 9.1. Booking and payment example

~~~mermaid
flowchart TD
    Start["Create reservation"] --> Hold["T1: Hold inventory"]
    Hold --> Charge["T2: Request payment"]
    Charge --> Paid{"Payment result"}
    Paid -->|Success| Confirm["T3: Confirm booking"]
    Confirm --> Notify["Publish confirmation"]
    Notify --> Done["Completed"]
    Paid -->|Declined| Release["C2: Release hold"]
    Release --> Fail["Booking failed"]
    Confirm -->|Permanent failure| Refund["C3: Refund payment"]
    Refund --> Release2["C2: Release hold"]
    Release2 --> Compensated["Compensated / reconcile"]
~~~

In the example:

- **T1** holds the slot with an expiry/lease to avoid holding resources indefinitely.
- **T2** requests payment using an idempotency key.
- **T3** confirms the booking after verifying the payment outcome.
- **C2** releases the held slot.
- **C3** requests a refund if payment succeeded but the booking cannot be confirmed.

The Saga must also handle a payment timeout where the provider actually collected funds. Never infer that timeout equals payment failure; query by idempotency/reference or reconcile before issuing a new charge.

### 9.2. Orchestration and choreography

| Coordination style | How it works | Advantages | Trade-offs |
|---|---|---|---|
| **Orchestration** | A workflow/state machine decides next steps, retries, and compensation | Clear overall state and execution flow | Workflow engine and state machine become critical components to operate |
| **Choreography** | Services react to events from other services | Less central coordination, more autonomous services | Harder to see the full process, easy to form event cycles, harder ordering control |

For workflows with many branches, long durations, human approvals, or audit needs, orchestration is usually easier to reason about. For simple event chains with few steps, choreography can suffice. Do not introduce a Saga just because two services communicate; use a local transaction if invariants fit inside one boundary.

### 9.3. State machines and intermediate states

A long-running process should have explicit states, for example:

~~~text
REQUESTED
  -> INVENTORY_HELD
  -> PAYMENT_PENDING
  -> PAYMENT_CONFIRMED
  -> BOOKING_CONFIRMED

Branches:
PAYMENT_DECLINED -> COMPENSATING -> FAILED
PAYMENT_UNKNOWN  -> RECONCILING
CONFIRM_FAILED   -> REFUND_PENDING -> COMPENSATING
COMPENSATION_FAILED -> MANUAL_REVIEW
~~~

Do not lump every error into `FAILED`. Keep `PAYMENT_UNKNOWN` separate because the provider may have succeeded while the system has not yet received the outcome. Reconciliation verifies state before deciding the next step.

## 10. Designing business-meaningful compensation

Compensation does not necessarily mean performing the exact inverse database mutation. It must reflect what both the system and the user experienced.

| Completed action | Possible compensating action | What to verify |
|---|---|---|
| Hold slot | Release hold | Does the hold still belong to this Saga? Did it expire or get reassigned? |
| Collect funds | Refund or void/authorization reversal depending on transaction state | Did the provider capture or only authorize? Can refunds be partial? |
| Issue voucher | Revoke voucher or issue adjusting entry | Was the voucher already redeemed? Does revoking break a displayed commitment? |
| Send email | Send correction email or cancellation notice | Cannot recall sent email; handle transparently |
| Update search index | Emit index fix/delete event | Does the index handle eventual consistency and replay? |
| Generate invoice | Issue credit note / adjustment per accounting rules | Never delete issued invoice history |

Some actions cannot be completely undone. Sent emails, SMS messages, or partner notifications do not disappear simply by updating a database. Compensation can be a **new corrective action**, not erasing traces.

### 10.1. Compensation must also be idempotent

If a Saga retries a refund step, there is a risk of refunding twice. Use a deterministic compensation ID or idempotency key per Saga step:

~~~text
Saga ID: saga-rs-1732
Step: refund-payment
Compensation key: saga-rs-1732:refund:v1
~~~

A service receiving the same key must return the already-processed result or resume the existing operation state without creating an extra refund. Store provider responses/references for reconciliation.

### 10.2. Compensation order

Compensation is usually designed in reverse order of completed steps, though this is not an absolute rule. Depending on the business, some actions must run first to stop further effects:

- Stop accepting further commands or move the workflow to a cancelling state.
- Block new resource confirmations/consumptions.
- Refund funds or release holds per requirements and dependencies.
- Update read models, send notifications, and record audits.

What matters is defining **preconditions, owner, retries, timeouts, and failure consequences** for every action.

## 11. Timeouts and ambiguous outcomes

A timeout does not tell the caller whether the server-side operation succeeded. Especially when calling payment, inventory, or third-party services:

1. Caller sends request.
2. Provider processes and commits transaction.
3. Response is lost on the network.
4. Caller times out and does not know the outcome.

If the caller sends a new request with a different idempotency key, it may charge twice. If the caller marks it failed immediately, internal state diverges from the provider.

### How to handle

- Generate an operation ID / idempotency key before calling the provider and persist state.
- On timeout, set state to `UNKNOWN`/`PENDING_RECONCILIATION`; do not mark definitely failed.
- Query the provider by reference/idempotency key or wait for a signed webhook.
- Verify webhooks, prevent replay, and protect callback endpoints.
- Execute compensation or retry commands only after learning the outcome or per defined unknown-handling policy.
- Run periodic reconciliation for operations stuck in intermediate states too long.

## 12. Idempotency in updates and compensation

Optimistic concurrency protects against version conflicts; idempotency protects against repeating the same intent. They solve different problems and often work together.

| Problem | Primary mechanism |
|---|---|
| Two callers read the same version and then write | Optimistic concurrency / conditional update |
| One client retries the same create-booking request | API command idempotency key |
| Queue delivers a message multiple times | Idempotent consumer / deduplication |
| Saga re-executes refund due to timeout | Compensation idempotency key |
| Provider redelivers webhook | Store processed event ID / provider transaction ID |
| Operation succeeded but response was lost | Look up existing operation and return stored outcome |

A write API should bind the idempotency key to caller/tenant, operation type, and an appropriate request hash. If the same key arrives with a different payload, return a conflict per contract instead of mistakenly returning the old result.

Example state table:

~~~sql
CREATE TABLE idempotency_records (
    tenant_id VARCHAR(80) NOT NULL,
    operation_key VARCHAR(120) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    operation_id VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    response_reference VARCHAR(200),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_key)
);
~~~

The table needs a unique constraint for the key scope; retention must exceed the retry/reconciliation window. Do not store sensitive payment details if only a provider reference is needed.

## 13. Choosing consistency boundaries and data models

Conflicts are harder to resolve when invariants span multiple owners. Before splitting services/databases, determine:

- Which record or aggregate is the source of truth for the invariant?
- Who holds write authority and where can commands be serialized?
- Which data needs atomic transactions?
- Which data can update later via events?
- How much lag and stale reading can consumers tolerate?
- Can read models be rebuilt from events or the source of truth?

For example, the decision of "whether a slot is still available to confirm" belongs in a boundary capable of enforcing atomic constraints/conditional updates. The search index can be an eventually consistent read model; never use stale search results as final proof that capacity remains.

A useful pattern is a **write model** owning rules and primary data, and a **read model** updated from events for queries. When the read model lags, the API can show a syncing indicator or read the authoritative store for critical actions.

## 14. Testing conflicts and Sagas

Sequential happy-path tests do not adequately catch lost updates or race conditions. Test with concurrency and faults injected at every boundary.

### 14.1. Testing optimistic concurrency

Scenario:

1. Create resource version 1.
2. Two clients both read version 1.
3. Client A writes successfully with version 1.
4. Client B writes with version 1 and must receive a conflict.
5. Verify final data reflects A's change and version incremented only by the number of successful updates.
6. Test B re-reading and merging/retrying per policy.

~~~text
Given reservation version = 1
When client A and B read version = 1
And A updates with expected version = 1
Then A succeeds and version becomes 2
When B updates with expected version = 1
Then B receives conflict
And no stale value overwrites A
~~~

### 14.2. Testing Saga anomalies

| Fault injection | Expected result |
|---|---|
| Inventory hold succeeds, payment declined | Hold released exactly once from a business standpoint |
| Payment provider captures, response times out | Transitions to `UNKNOWN` and reconciles; never charges blindly again |
| Booking confirmation fails after payment capture | Refund/compensation per policy with audit |
| Refund times out after provider executes it | Query using same idempotency key before retrying |
| Consumer receives event twice | No unintended duplicate side effects |
| Compensation service is down | Saga stays `COMPENSATING`, retries, and alerts |
| Workflow engine restarts | Recovers state without re-running steps that duplicate effects |
| Hold expires while payment is pending | Handles race among expiry, payment callback, and confirmation |

### 14.3. Measurement

- Optimistic conflict rate per resource/endpoint.
- Average and p95 retry counts.
- Saga success, failure, and compensating rates.
- Age of operations in `pending`/`unknown`/`compensating` states.
- Compensation success, failure, and manual-review rates.
- Count of operations needing reconciliation and resolution time.
- Duplicate/idempotency hit rate and prevented side effects.

A rising conflict rate can indicate an overly hot resource, a UI holding data too long, or an endpoint updating too many fields at once. Do not treat every conflict as a bug; monitor user-tolerable conflict rates and latency impact.

## 15. Case study: concurrent reservation edits and payment failure

**Context:** a booking platform lets guests change guest count and stay dates. The system comprises a Reservation API, Inventory service, Payment provider, and Notification worker.

### 15.1. Stay-date edit conflict

A and B both read reservation version 10. A changes the check-out date; B changes guest count. If the API uses whole-document `PUT`, B can write back the old date and wipe out A's change. Two options:

- Use `PATCH` only for fields the caller is permitted to change, paired with `If-Match` version 10. After A succeeds to version 11, B receives 412.
- The service re-reads version 11 and merges guest count if availability/pricing rules still allow it; if date changes affect pricing and availability, ask the user to review the updated data.

Never auto-merge every field. Changing guest count can affect capacity, pricing, and booking eligibility; business validation must re-run against the new state.

### 15.2. Payment failure

1. Reservation service creates an operation and holds inventory with an expiry.
2. Payment service calls the provider using an idempotency key tied to the operation.
3. The provider collects funds, but the response times out.
4. The operation enters `PAYMENT_UNKNOWN`; the reconciliation worker queries the provider.
5. If captured, the workflow proceeds to confirm the booking.
6. If the provider confirms funds were not collected and the retry window remains valid, the workflow can retry with the same key per the provider contract.
7. If the booking cannot be confirmed after funds were collected, the workflow requests a refund and releases the hold per policy.
8. If the refund outcome is unclear, keep `REFUND_PENDING`/`RECONCILING` and alert; never assume the refund succeeded.

### 15.3. States and ownership

| Component | Owned states | Responsibilities |
|---|---|---|
| Reservation service | `REQUESTED`, `CONFIRMED`, `CANCELLED`, `COMPENSATING` | Decides booking status and issues operations |
| Inventory service | `HELD`, `COMMITTED`, `RELEASED`, `EXPIRED` | Prevents double-booking and manages hold lifecycle |
| Payment service/provider | `PENDING`, `CAPTURED`, `DECLINED`, `REFUND_PENDING`, `REFUNDED`, `UNKNOWN` | Tracks transactions and reconciliation |
| Notification worker | `QUEUED`, `SENT`, `FAILED` | Sends notifications after appropriate business states |

Each service owns its own states; the overall workflow coordinates progress without assuming direct write access to another service's database.

## 16. Well-Architected trade-offs

| Perspective | Decision | Benefits and trade-offs |
|---|---|---|
| **Reliability** | Version checks, idempotency, Sagas, and reconciliation | Prevents overwrites/duplicate effects and handles partial failures; increases state count to manage |
| **Security** | Authorization before updates/compensation, protecting webhooks and secrets | Prevents unauthorized actions; requires auditing and rotation |
| **Performance efficiency** | Optimistic locking for low contention, serialize hot resources | Avoids long locks; conflicts/retries can increase load under high contention |
| **Cost optimization** | Choose consistency boundaries and bounded retries | Reduces lock waits/long transactions; workflows, events, and reconciliation add cost |
| **Operational excellence** | State machines, dashboards, runbooks, and operation history | Easier incident explanation; requires owners for pending/manual-review states |
| **Sustainability** | Avoid retry storms and redundant work | Reduces compute/data transfer and waste from duplicate processing |

Optimistic locking reduces lock hold times, but it is not free: frequent conflicts cost extra reads/writes and force users to retry. Sagas improve partial-failure handling, but require designing compensation, idempotency, timeouts, and reconciliation. Choices must align with invariants, contention levels, SLOs, and operational capability.

## 17. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Read then write without version/constraints | Lost updates | Conditional write or appropriate transaction |
| Checking version only in the API, not in the database | Races still occur between check and write | Put the version condition into the atomic write |
| Using client timestamps as versions | Clock skew or same-resolution collisions | Use reliable versions / concurrency tokens |
| Retrying conflicts infinitely | Higher load and starvation | Cap retries, merge, or serialize processing |
| Auto-merging every field | Violates invariants and business rules | Merge only fields with safe rules |
| Treating compensation as rollback | History and external side effects do not vanish | Create audited compensating business actions |
| Treating timeouts as definite failures | Duplicate charges/bookings | `UNKNOWN` state and reconciliation |
| Non-idempotent compensation | Multiple refunds or resource releases | Compensation keys and operation state |
| Not monitoring compensating Sagas | Processes hang unnoticed | Alert by age/status and manual review |
| Splitting invariants across DBs prematurely | Complex Saga for an operation that should be atomic | Revisit consistency boundaries and domain ownership |
| Using stale read models for write decisions | Accepts invalid transactions | Check the source of truth on critical commands |

## 18. Design review checklist

### Update conflicts and optimistic concurrency

- [ ] Business invariants and owned data are identified.
- [ ] Every write path uses versions/concurrency tokens or an equivalent atomic mechanism.
- [ ] Conditional updates execute inside atomic database/storage operations.
- [ ] APIs have clear semantics for 409, 412, or 428 by conflict type.
- [ ] Clients re-read, merge, or prompt users rather than retrying blindly.
- [ ] Versions increment across APIs, workers, batch jobs, and all other write tools.
- [ ] Concurrency tests and conflict/retry metrics are in place.

### Compensation and Sagas

- [ ] Local transactions and workflow ordering are documented.
- [ ] Each step has clear timeouts, retry policies, and states.
- [ ] Each compensable action defines compensation, preconditions, and owner.
- [ ] Compensation carries idempotency keys and stores provider references.
- [ ] Timeouts/unknown outcomes reconcile before repeating side effects.
- [ ] `COMPENSATING`, `UNKNOWN`, and `MANUAL_REVIEW` states exist where needed.
- [ ] DLQs / failed workflows have alerts, runbooks, and assigned owners.
- [ ] Audits preserve both original and compensating transaction history.

### Operations

- [ ] Dashboards track conflicts, retries, Saga age, compensation success, and pending operations.
- [ ] SLOs reflect end-to-end business outcomes.
- [ ] Fault-injection tests cover every critical failure window.
- [ ] Manual-handling and reconciliation guides exist when providers return ambiguous results.
- [ ] Retry, event, workflow, and operational costs are included in cost per business operation.

## 19. Practice exercise

**Context:** a car-rental booking system has one vehicle available during time window T. Two customers concurrently submit booking requests. One request holds the vehicle and starts payment; the provider collects funds, but the response times out. Meanwhile, a support agent updates the reservation, and a confirmation email may already have been sent.

Design consistency protection:

1. Identify invariants required so two reservations cannot be confirmed for the same vehicle and time window.
2. Choose protection mechanisms: transactions/constraints, conditional updates, optimistic versions, or serialized commands. Explain the data boundaries.
3. Define read/update APIs with versions or `ETag`/`If-Match` and behavior when receiving 412.
4. Specify how to handle conflicting edits between support staff and the customer; which fields can merge and which require review?
5. Model the book–pay–confirm Saga, including `UNKNOWN`, compensation, and manual review states.
6. Design idempotency for client retries, payment requests, webhooks, hold releases, and refunds.
7. Define reconciliation when the provider collected funds but the response was lost.
8. Specify behavior if the email was already sent before the booking was cancelled or compensated.
9. Build concurrency tests and fault-injection scenarios.
10. Define dashboards/SLOs for conflict rate, pending age, refund completion, and booking success rate.

**Self-check hints:** Never use search/read availability results as final proof when writing a booking; holding slots must be atomic or serialized. Never treat a payment timeout as a payment decline. Sent emails cannot be recalled via database rollback. Every compensating step must be a business operation with an owner, idempotency, and audit trail.

## 20. Takeaway

**Optimistic concurrency** protects updates against the latest version using conditional writes; when conflicts occur, callers must re-read, merge by rule, or request a fresh decision. This works well when contention is low enough and locks need not be held while users edit.

**Compensation** addresses committed effects in distributed workflows without a global transaction. It creates new business actions that can fail or need reconciliation, requiring state machines/Sagas, idempotency, timeouts, bounded retries, and manual recovery. Good design starts from invariants and consistency boundaries, then verifies race conditions and partial failures through tests and operational metrics.
