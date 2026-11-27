# Lifecycle, Ownership, and State-Changing Operations

## Learning Objectives

After this lesson, you will be able to:

- Describe an entity's **lifecycle** using states, events, and permitted transitions rather than merely listing a `status` column.
- Identify the **data owner**, aggregate root, authorized command issuers, and authoritative system for each rule.
- Design **business commands** with explicit preconditions, postconditions, and error cases; protect invariants under concurrent actors.
- Distinguish **stored state**, **time-derived state**, **transition history**, and **snapshot data**.
- Map a lifecycle model to keys, constraints, indexes, transactions, and concurrency control mechanisms.
- Handle cross-aggregate changes using integration contracts, idempotency, events, and appropriate intermediate states.

In the **DATABASE_DATA_MODELING** module, the goal is not to create as many tables as possible, but to turn business requirements into a clear, evolvable, and verifiable data model. An entity with an ID, relationships, and columns is still incomplete if you do not know **who is allowed to change its state**, **which operations perform the change**, **what conditions must hold**, and **whether historical data is retained**. That is the focus of this lesson in the **Domain Modeling** chapter.

## 1. What Is a Lifecycle in a Domain Model?

An entity's **lifecycle** describes its progression from creation, through valid states and behaviors, until termination or archival per policy. A lifecycle answers questions that foreign key relationships alone cannot resolve:

- Can a closed ticket have its contents edited?
- Does a retried command advance the state a second time?
- Who is allowed to cancel, who is allowed to approve, and is cancellation permitted once work begins?
- Should the system delete records upon completion or retain history?
- When two requests arrive simultaneously, which one is allowed to win?

Our running example is **`MaintenanceTicket`**, a maintenance request for an enterprise asset. A user reports a fault, support triages it, a technician resolves it, and an authorized person closes the ticket. The asset and technician profiles have their own separate lifecycles.

A ticket can move through these states:

~~~mermaid
stateDiagram-v2
    [*] --> NEW: CreateTicket
    NEW --> TRIAGED: TriageTicket
    TRIAGED --> IN_PROGRESS: StartWork
    IN_PROGRESS --> RESOLVED: ResolveTicket
    RESOLVED --> CLOSED: CloseTicket
    RESOLVED --> IN_PROGRESS: ReopenTicket
    NEW --> CANCELLED: CancelTicket
    TRIAGED --> CANCELLED: CancelTicket
    CLOSED --> [*]
    CANCELLED --> [*]
~~~

This is an **illustrative policy**, not a universal law for every company. In another workflow, an administrator might be able to cancel work in progress, or a `CLOSED` ticket might be reopened under a warranty policy. If the business allows it, add the corresponding command, conditions, and history instead of mutating `status` directly.

### Status Does Not Replace Full Business Semantics

| Concept | Example | Role |
| --- | --- | --- |
| **Identity** | `ticketId` | Identifies the same Ticket even as status changes |
| **State** | `IN_PROGRESS` | Expresses the Ticket's current stage |
| **Behavior/command** | `ResolveTicket` | Requests an intentional state change |
| **Invariant** | Only `IN_PROGRESS` may become `RESOLVED` | Condition that must remain true after the operation |
| **Domain event** | `TicketResolved` | Fact about a change that already occurred |
| **Timestamp** | `resolvedAt`, `dueAt` | Basis for deadlines, preconditions, and history |
| **Owner** | `MaintenanceTicket` aggregate in Service Desk | Holds authority over Ticket status |

An entity can have many attributes change within the same state. For example, `AssignTechnician` changes the assigned technician while the Ticket stays `TRIAGED`; there is no need to invent a new status for every data mutation.

## 2. Separating Business State, Derived State, and Technical State

### 2.1. Persisted Business State

`NEW`, `TRIAGED`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`, and `CANCELLED` are meaningful states in a maintenance workflow. They must be named in **business language**, with clear rules on who can move an object into each state and which fields are mandatory upon transition.

For example: if a Ticket is `RESOLVED`, it must have a valid `resolutionCode`. If a Ticket is `IN_PROGRESS`, it must have an assigned technician. These constraints can be checked in the aggregate and reinforced by data constraints.

### 2.2. Time-Derived State

Suppose a Ticket has a `dueAt` timestamp and is currently `IN_PROGRESS`. Once the clock passes `dueAt`, the ticket is **SLA-overdue** without any user issuing a transition command. This can be expressed as:

~~~text
overdue = now > dueAt AND status NOT IN (RESOLVED, CLOSED, CANCELLED)
~~~

`OVERDUE` in this case is a **derived state** for alerting or reporting, not necessarily a value in the same `status` enum. If you store a physical `overdue` column, you must maintain a time-driven updater or tolerate staleness. Avoid mixing time-based indicators into lifecycle status when the two mechanisms carry different semantics.

Similarly, a Ticket can simultaneously be `IN_PROGRESS` and have **priority `HIGH`**. Priority is a classification attribute, not a lifecycle state.

### 2.3. Technical State Differs from Business State

A failed message might be in `RETRYING` or `DEAD_LETTER`; an outbox event might be `PENDING`/`SENT`. Those are **messaging infrastructure** states, not whether a Ticket is finished. Avoid folding them into Ticket's `status`, as doing so couples the domain model to broker details and causes state explosion.

A practical rule: add a state only if domain experts can explain **what changed in rights, obligations, or permitted operations on the entity**.

## 3. Data Ownership Differs from Permission to Act

In a system, at least three questions must be kept distinct:

1. **Who owns the business truth?** Which aggregate/bounded context has authority to create and modify the data?
2. **Who is allowed to request a change?** Which user or system is authorized to invoke a command?
3. **Who is responsible for storage and access control?** Which database, service, operations team, and authorization policies enforce it?

Examples:

| Data | Domain owner | Who may request changes | Control point |
| --- | --- | --- | --- |
| `MaintenanceTicket` status | Service Desk / Ticket aggregate | Triagers, technicians, authorized closers per policy | Application authorization + Ticket behavior |
| `Asset` condition/status | Asset Management / Asset aggregate | Asset managers, inventory/maintenance workflows | Asset Management commands |
| `Technician` profile | Workforce Management | HR admins, the technician per permissions | Workforce APIs and ownership |
| Maintenance invoice result | Billing / Invoice aggregate | Billing or valid financial workflows | Billing commands and transactions |
| Maintenance reporting data | Read model/analytics | Authorized readers | Projections and query permissions |

Service Desk can store `assetId` and `technicianId`, but it must never directly modify asset status or employment contracts through Ticket. If completing a ticket must mark an Asset as inspected, Ticket can publish an event or send a request via Asset Management's API.

**Ownership is not merely a database connection account.** The fact that a service can run an `UPDATE` on another table because they share a database does not mean it is authorized to mutate that aggregate's business state. Conversely, merely knowing a Ticket's ID does not grant permission to view or edit it; authorization and tenant scope must be checked separately.

### Aggregate Boundaries and Write Authority

`Ticket` can be the aggregate root coordinating status changes, assignments, and resolution recording. Data that exists solely to serve Ticket and must change consistently with Ticket can be internal members. `Asset` and `Technician` are usually separate aggregates with independent lifecycles, so Ticket references them by ID and stores snapshots when history must be preserved.

Do not define an aggregate solely from a one-to-many relationship on an ERD. Boundaries must be justified by **which invariants must be checked and committed together**.

## 4. Designing Commands and Transition Preconditions

Command names should describe **business intent**, not column updates:

- `CreateTicket` — create a ticket with `assetId`, `requesterId`, and fault description.
- `TriageTicket` — classify, set priority, and determine handling conditions.
- `AssignTechnician` — assign a technician when status permits.
- `StartWork` — begin work once assigned.
- `ResolveTicket` — record resolution code/actions, move to `RESOLVED`.
- `ReopenTicket` — record reason for unsatisfactory fix, move `RESOLVED` back to `IN_PROGRESS`.
- `CloseTicket` — confirm completion from `RESOLVED`.
- `CancelTicket` — cancel a `NEW`/`TRIAGED` ticket per policy.

Write a transition table instead of letting clients send arbitrary `status` values:

| Command | Allowed prior states | Other preconditions | Resulting state |
| --- | --- | --- | --- |
| `TriageTicket` | `NEW` | Valid priority; actor has triage permission | `TRIAGED` |
| `AssignTechnician` | `TRIAGED`, `IN_PROGRESS` | Valid `technicianId`; actor has assignment permission | Unchanged |
| `StartWork` | `TRIAGED` | `technicianId` is already assigned | `IN_PROGRESS` |
| `ResolveTicket` | `IN_PROGRESS` | Non-empty `resolutionCode`; actor authorized | `RESOLVED` |
| `ReopenTicket` | `RESOLVED` | Reason provided; suitable technician remains available | `IN_PROGRESS` |
| `CloseTicket` | `RESOLVED` | Confirmation/verification meets policy | `CLOSED` |
| `CancelTicket` | `NEW`, `TRIAGED` | Reason provided; actor permitted to cancel | `CANCELLED` |

**Preconditions** are conditions required for a command to be accepted. **Postconditions** describe the valid outcome when the command succeeds. Failure modes must also be defined: not found, unauthorized, invalid state, version conflict, invalid reference, or external dependency unavailable.

Example for `ResolveTicket`:

~~~text
Command: ResolveTicket(ticketId, resolutionCode, expectedVersion, requestId)

Precondition:
  - Ticket exists in the current tenant
  - Actor is authorized to resolve this Ticket
  - Ticket is currently IN_PROGRESS
  - resolutionCode is non-empty
  - expectedVersion matches current version

Success:
  - Ticket.status = RESOLVED
  - Ticket.resolutionCode is persisted
  - version increments exactly once
  - A TicketResolved history record is created
  - Outbound event is recorded in the same transaction

Failure:
  - Ticket is not partially modified
  - Return a clear business or conflict error code
~~~

A successful command can update several fields simultaneously. Thus **the business operation is the unit of consistency**, not individual `UPDATE` statements in a controller.

## 5. Java Example: Root Protecting Its Own Lifecycle

The following example models core transitions with no I/O. In a real application, actor authorization, Asset/Technician lookups, and transactions sit outside this domain snippet.

~~~java
import java.util.Objects;
import java.util.UUID;

enum TicketStatus {
    NEW, TRIAGED, IN_PROGRESS, RESOLVED, CLOSED, CANCELLED
}

record TicketId(UUID value) {
    TicketId {
        Objects.requireNonNull(value);
    }
}

record TechnicianId(UUID value) {
    TechnicianId {
        Objects.requireNonNull(value);
    }
}

// Aggregate root: interact only through domain-meaningful methods.
final class MaintenanceTicket {
    private final TicketId id;
    private TicketStatus status = TicketStatus.NEW;
    private TechnicianId assignedTechnician;
    private String resolutionCode;
    private long version;

    MaintenanceTicket(TicketId id) {
        this.id = Objects.requireNonNull(id);
    }

    void triage() {
        require(TicketStatus.NEW);
        status = TicketStatus.TRIAGED;
    }

    void assign(TechnicianId technicianId) {
        if (status != TicketStatus.TRIAGED
                && status != TicketStatus.IN_PROGRESS) {
            throw new IllegalStateException("Assignment not allowed");
        }
        assignedTechnician = Objects.requireNonNull(technicianId);
    }

    void startWork() {
        require(TicketStatus.TRIAGED);
        if (assignedTechnician == null) {
            throw new IllegalStateException("Technician required");
        }
        status = TicketStatus.IN_PROGRESS;
    }

    void resolve(String code) {
        require(TicketStatus.IN_PROGRESS);
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Resolution required");
        }
        resolutionCode = code.strip();
        status = TicketStatus.RESOLVED;
    }

    void reopen(String reason) {
        require(TicketStatus.RESOLVED);
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Reason required");
        }
        // The reopen reason will be persisted in command/event history.
        resolutionCode = null;
        status = TicketStatus.IN_PROGRESS;
    }

    void close() {
        require(TicketStatus.RESOLVED);
        status = TicketStatus.CLOSED;
    }

    void cancel(String reason) {
        if (status != TicketStatus.NEW
                && status != TicketStatus.TRIAGED) {
            throw new IllegalStateException("Cancellation not allowed");
        }
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Reason required");
        }
        status = TicketStatus.CANCELLED;
    }

    TicketStatus status() { return status; }
    TicketId id() { return id; }
    long version() { return version; }

    private void require(TicketStatus expected) {
        if (status != expected) {
            throw new IllegalStateException(
                "Expected " + expected + ", actual " + status);
        }
    }
}
~~~

Here `version` is the **persistence version**. Because this example omits a repository, individual methods do not increment `version`; when persistence saves successfully under optimistic locking, the repository must keep the object's version aligned with the stored version. Never assume that reading `version` from an in-memory object automatically resolves two competing transactions.

Design notes:

- Do not expose `setStatus`, `setResolutionCode`, or let application code mutate internal fields directly.
- `TicketId` and `TechnicianId` are **identifying value objects**, avoiding pulling the entire Technician into Ticket.
- `CLOSED` and `CANCELLED` are **terminal states in this sample policy**; no command allows arbitrary edits afterward.
- Cancellation/reopen reasons can be recorded in domain event history or audit logs; the example shows only input validation.
- Distinguish a **domain event** describing what happened from a **command** requesting an action: `TicketResolved` is only emitted once `ResolveTicket` succeeds.

If a rule spans multiple aggregates—such as a technician not exceeding a maximum active workload—Ticket should not directly mutate Technician's schedule. The owner of schedules/availability must reserve capacity or confirm assignment through its own protocol.

## 6. Mapping Lifecycles to PostgreSQL

In the sample schema, Service Desk owns Tickets, transition history, and outbox events. Asset and Technician may belong to other systems, so Ticket only stores reference IDs.

~~~sql
CREATE SCHEMA IF NOT EXISTS service_desk;

CREATE TABLE service_desk.maintenance_ticket (
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    asset_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    assigned_technician_id UUID,
    status VARCHAR(16) NOT NULL DEFAULT 'NEW'
        CHECK (status IN (
            'NEW', 'TRIAGED', 'IN_PROGRESS',
            'RESOLVED', 'CLOSED', 'CANCELLED'
        )),
    priority VARCHAR(8) NOT NULL DEFAULT 'NORMAL'
        CHECK (priority IN ('LOW', 'NORMAL', 'HIGH')),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    resolution_code TEXT,
    due_at TIMESTAMPTZ,
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, ticket_id),
    CONSTRAINT resolution_required_after_work
        CHECK (
            status NOT IN ('RESOLVED', 'CLOSED')
            OR (resolution_code IS NOT NULL AND length(trim(resolution_code)) > 0)
        ),
    CONSTRAINT technician_required_when_work_started
        CHECK (
            status NOT IN ('IN_PROGRESS', 'RESOLVED', 'CLOSED')
            OR assigned_technician_id IS NOT NULL
        )
);

CREATE TABLE service_desk.ticket_transition_history (
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    version BIGINT NOT NULL,
    command_id UUID NOT NULL,
    from_status VARCHAR(16) NOT NULL,
    to_status VARCHAR(16) NOT NULL,
    actor_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    PRIMARY KEY (tenant_id, ticket_id, version),
    UNIQUE (tenant_id, command_id),
    FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES service_desk.maintenance_ticket (tenant_id, ticket_id)
);

CREATE TABLE service_desk.outbox_event (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

-- Look up unfinished tickets by due time within a tenant.
CREATE INDEX ticket_open_by_due
    ON service_desk.maintenance_ticket (tenant_id, due_at)
    WHERE status IN ('NEW', 'TRIAGED', 'IN_PROGRESS');

-- Worklist queue by assigned technician and status.
CREATE INDEX ticket_assignee_worklist
    ON service_desk.maintenance_ticket
        (tenant_id, assigned_technician_id, status)
    WHERE assigned_technician_id IS NOT NULL;
~~~

A few observations:

- **Key `(tenant_id, ticket_id)`** enforces tenant scope. Queries and commands must also check `tenant_id` alongside authorization; an ID is not an access pass.
- **`CHECK`** protects the set of valid statuses and two row-level invariants: `RESOLVED`/`CLOSED` tickets must have a resolution code; tickets from `IN_PROGRESS` onward must have an assigned technician. `CHECK` **does not** automatically enforce transition order or who is authorized to act.
- **Internal foreign key** links history to Ticket; omitting FKs to Asset/Technician is an intentional choice when they have independent owners, not an excuse to skip existence/validity checks.
- **History** includes `version` and `command_id` to trace changes; in production, define what audit data is sufficient—whether event codes, before/after snapshots, or separate command receipt timestamps are needed.
- **Outbox** supports publishing integration events after commit; it is distinct from the business history table. Some events need not be published externally, and a single change may emit multiple messages.
- **Indexes** serve two specific query patterns; create indexes from real demand and verify query plans instead of indexing every column.

If you need to report overdue Tickets relative to current time, query open statuses alongside `due_at` rather than relying on an `overdue` column that easily becomes stale.

### Terminal State Differs from Deleting a Record

`CLOSED` and `CANCELLED` are **business lifecycle** states, not physical deletion. A Ticket may have been `CLOSED` long ago yet still be needed for reconciliation, turnaround metrics, or regulatory retention. If storage tiering is needed, use a dedicated retention/archive policy. Never turn `deleted_at` into a business status or auto-delete rows whenever a ticket closes.

## 7. A Command Must Commit Atomically

Suppose a technician submits `ResolveTicket` while a manager might be reassigning the ticket. Both status and version must be guarded:

~~~sql
BEGIN;

-- Repository has already verified actor permissions for ticket/tenant.
UPDATE service_desk.maintenance_ticket
SET status = 'RESOLVED',
    resolution_code = :resolution_code,
    status_changed_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND ticket_id = :ticket_id
  AND status = 'IN_PROGRESS'
  AND assigned_technician_id IS NOT NULL
  AND version = :expected_version
RETURNING version;

-- Application must verify exactly one row was updated.
-- If 0 rows: ROLLBACK and handle NOT_FOUND / INVALID_STATE /
-- VERSION_CONFLICT using appropriate safe checks.
-- :new_version below is the version returned by RETURNING.

INSERT INTO service_desk.ticket_transition_history
    (tenant_id, ticket_id, version, command_id,
     from_status, to_status, actor_id, reason)
VALUES
    (:tenant_id, :ticket_id, :new_version, :command_id,
     'IN_PROGRESS', 'RESOLVED', :actor_id, :resolution_code);

INSERT INTO service_desk.outbox_event
    (event_id, tenant_id, aggregate_id, aggregate_version,
     event_type, payload)
VALUES
    (:event_id, :tenant_id, :ticket_id, :new_version,
     'TicketResolved', :payload);

COMMIT;
~~~

The SQL illustrates **the happy path**. The application must never execute the two `INSERT`s if the `UPDATE` returned 0 rows. If writing history or outbox fails, the entire transaction must roll back, including the `UPDATE`. Outbox payloads and `command_id` must be generated, validated, and passed from the appropriate orchestration layer, never accepted blindly from an unverified client.

### Optimistic Locking and Unchanged Status

Suppose T1 and T2 both read Ticket version 5:

1. T1 executes `ResolveTicket` with `expectedVersion = 5` and commits successfully, reaching `version = 6`.
2. T2 executes `AssignTechnician` with `expectedVersion = 5`; even though assignment was allowed in `IN_PROGRESS` in the copy T2 read, the conditional `UPDATE` checking `version = 5` fails.
3. T2 must reload the Ticket, re-evaluate current business conditions, and decide whether to retry with a new command or return a conflict.

This is **optimistic locking**. If concurrency on a single Ticket is very high, pessimistic locking can be considered, but wait times, deadlocks, and lock ordering must be analyzed.

Every write operation that can affect invariants—including **`AssignTechnician` which does not change status**—must participate in the Ticket's shared version or lock protocol. If a direct `UPDATE` bypasses the root, versioning on standard commands alone is not enough to preserve consistency.

### Idempotency Is Not the Same as Version Checking

If a technician sends `ResolveTicket`, the server commits successfully, and the response is lost on the network, the client retries the same command. The retry may see the Ticket is already `RESOLVED` and think "invalid state." That does not mean the first attempt failed.

To distinguish a retry from **a new intent**, use a durable `commandId`/`requestId`:

- For the same `commandId`, return the previously processed outcome without re-applying business side effects.
- For a different `commandId`, validate status and version normally.
- Persist command tracking and outcomes within the relevant transaction scope, or provide a recovery protocol for mid-flight crashes.

`UNIQUE(tenant_id, command_id)` on transition history prevents duplicate transition rows, yet **is not sufficient to guarantee returning the right response for a repeated command** in every case (for example, an assignment command that does not change status, a rejected command, or responses carrying extra data). The system may need a dedicated idempotency table storing processing status/result and request-key retention rules.

## 8. Cross-Aggregate Operations: Contracts and Events

When a Ticket becomes `RESOLVED`, the business may want to update the Asset's maintenance history and notify the requester. These are two obligations **outside Ticket**:

~~~mermaid
sequenceDiagram
    participant U as Technician
    participant T as Service Desk / Ticket
    participant B as Event Bus
    participant A as Asset Management
    participant N as Notification

    U->>T: ResolveTicket(ticketId, commandId)
    T->>T: Validate + commit Ticket & outbox
    T-->>U: Ticket RESOLVED
    T->>B: TicketResolved(eventId, ticketId, assetId)
    B-->>A: TicketResolved
    A->>A: Check policy, update Asset via root
    B-->>N: TicketResolved
    N->>N: Send idempotent notification
~~~

Ticket does not directly mutate Asset state. Asset Management decides how to interpret `TicketResolved`, the conditions for marking an Asset serviced, and whether to reject if the Asset changed owner or entered another workflow.

**Eventual consistency** fits reporting updates or notifications well. However, if business policy says **you cannot `ResolveTicket` until the equipment passes a mandatory inspection**, you must place the verification step with Asset Management **before completion** or introduce an intermediate state like `RESOLUTION_PENDING`. Never rely on a downstream event arriving later as a way to "hope" a strict invariant holds.

Integration rules to specify explicitly:

| Issue | Decision required |
| --- | --- |
| Message delivered twice | Consumer deduplicates by `eventId` or idempotency key |
| Messages arrive out of order | Use source aggregate `version`/sequence and handle stale events |
| Publisher crashes after commit | Outbox is relayed and retried, avoiding lost events from separate DB write + publish |
| Consumer fails mid-processing | Safe retries, inbox/dedup, and dead-letter/reconciliation |
| Receiver rejects the change | Record error handling state, compensate, or invoke remediation workflow per policy |
| Waiting on external party too long | Timeouts, deadlines, intermediate states, and progress lookup capability |

Do not confuse **Ticket state** with **message delivery state**. These are two separate lifecycles owned by two different components.

## 9. History, Time, and Auditability

A lifecycle is more than the current `status` value. For maintenance, you need to know which stages a Ticket passed through, who acted, when, and for what reason.

| Data | Meaning | Common storage |
| --- | --- | --- |
| `status` | Latest state | Column on aggregate root |
| `status_changed_at` | Most recent state change | Column on root, updated only when `status` changes |
| `created_at` | Record creation time | System column, authoritative clock |
| `occurred_at` | When the business event happened | Business history, requires defining time source |
| `recorded_at` | When the system received/persisted the event | History for measuring ingestion lag |
| `version` | Root version | Guards concurrent writes and change ordering |
| `actorId` / `commandId` | Who requested and which request | Audit/idempotency; must enforce authorization |
| `reason` / `resolutionCode` | Context for decision | Business data; requires protection/retention policy |

**Valid time** and **transaction/recorded time** are not necessarily identical. For instance, a technician finishes work at 14:00, but an offline mobile app syncs at 15:30. If SLA reporting needs actual completion time, define validation rules for completion timestamps and store both timestamps; never blindly substitute a message's `created_at` for business event time.

A transition history table **does not automatically constitute event sourcing**. In event sourcing, events are the source of truth used to reconstruct state via versioning and replay rules; the model here uses the current Ticket row as the primary write source and history for auditability. Outbox, in turn, serves integration message transport. Choose architecture based on real needs, not because a table has "event" in its name.

### Correcting History Does Not Mean Erasing Traces

Suppose `ResolveTicket` recorded the wrong `resolutionCode`. You may need a `CorrectResolution` command or an adjustment event with reason and approver, rather than silent overwrites or deletions. If records contain personal data, erasure/anonymization requests must balance against statutory retention obligations; do not retain all payloads indefinitely solely "for audit."

### Closing, Archiving, and Deleting Are Three Distinct Actions

- **`CloseTicket`:** transitions the business lifecycle to `CLOSED`.
- **`ArchiveTicket`:** moves older data to colder storage, potentially preserving lookup access.
- **`Delete/Anonymize`:** removes or de-identifies data per authorization and retention policy; does not happen by default upon `CLOSED`.

If adding `deleted_at`, document clearly that it is **a soft-delete marker for data**, not a new workflow status. Also check whether uniqueness constraints and queries properly exclude soft-deleted rows.

## 10. Choosing Data Structures Based on Lifecycle and Ownership

| Storage type | Modeling approach | Considerations |
| --- | --- | --- |
| **Relational** | Ticket root, history table, and outbox; FKs for internal members | Transactions, `CHECK`, `UNIQUE`, indexes by status/due date; root must govern writes |
| **Document** | A Ticket document holding state and local business data; history can be separate | Know the atomic update scope; documents bloat if unbounded history is embedded |
| **Graph** | Ticket linked to Asset, Technician, Incident/RootCause via edges | Relationships do not determine ownership or atomicity; never mutate another source's lifecycle across an edge |
| **Analytical/Columnar** | `FactTicketTransition`, Technician/Asset dimensions, processing time snapshots | Used for SLA metrics and trends; not a command decision source when data lags |

**Lifecycle matters more than physical layout.** You can put Ticket and history in two tables or one document, provided you preserve the requirement that every command validates state, checks versions, records events, and respects the authoritative owner.

In analytics, time spent in each status can be derived from the transition sequence. Account for open states (no end timestamp yet), reopens, and valid time differing from recorded time. Never compute SLA simply as `CLOSED - CREATED` across all workflows, since time waiting on customers or paused time may be excluded by policy.

## 11. Practical Process for Turning Requirements into a Lifecycle

When given a requirement like "do not allow closing a ticket without a resolution outcome," walk through these steps:

1. **List entities with identity and lifecycle:** Ticket, Asset, Technician, Invoice... Do not infer solely from table names.
2. **Identify the system owning each truth:** Service Desk owns Ticket status, Asset Management owns equipment condition, Billing owns payment outcomes.
3. **List minimal states:** add a state only when permissions/behaviors differ meaningfully in business terms.
4. **List commands and actors:** who may request it, is approval needed, is the command idempotent?
5. **Build a transition table:** prior state, preconditions, next state, required data, and post-commit events.
6. **Classify invariants:** internal to root, multi-row in same DB, or cross-aggregate/service.
7. **Design storage:** IDs, intentional FKs, `CHECK`, `version`, history, indexes, and transactions. Identify fields requiring snapshots.
8. **Test concurrency and failures:** two actors editing simultaneously, retries with same `commandId`, delayed messages, revoked permissions, unresponsive source systems.
9. **Define end-of-lifecycle:** closing, archiving, soft delete, hard delete, retention/anonymization.

The starting point of design is **business rules**, not SQL statements. SQL enforces rules that have already been understood properly; it cannot discover them from column names alone.

## 12. Exercise: Refund Request Lifecycle

**Scenario:** An e-commerce marketplace has `RefundRequest` linked to `Order` and `Payment`. A buyer submits a refund request for part of a paid order. Staff approves it, the system sends a refund command to the payment gateway, and responses may arrive late or duplicated. When refund succeeds, the request ends; when it fails, it can be retried per policy.

### Questions

1. Propose minimal states for `RefundRequest` and a transition table. Distinguish `PROCESSING` (refund command sent, awaiting result) from `REFUNDED` and `FAILED`; identify which states allow retries.
2. Who owns `RefundRequest`, `Order`, and `Payment`? Which actions can buyers or staff **request**, and who records the authoritative refund outcome?
3. Write three internal invariants of `RefundRequest` and at least one condition requiring coordination with `Payment` or `Order`.
4. Choose which data must be snapshotted (amount, currency, reason, purchased line/unit price) and which IDs must be retained for reconciliation.
5. What can go wrong if two processes approve the same `RefundRequest` concurrently, or if the gateway delivers `RefundSucceeded` twice? Propose `version`, `commandId`, and `paymentRefundId` to prevent duplicate refunds.
6. Sketch `RefundRequest` and `RefundTransitionHistory` tables, including constraints enforceable via SQL `CHECK`/`UNIQUE` and conditions requiring transactions or cross-system integration.

### Guided Solution Approach

One possible state machine is:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: ApproveRefund
    REQUESTED --> REJECTED: RejectRefund
    REQUESTED --> CANCELLED: CancelRefund
    APPROVED --> PROCESSING: SubmitRefund
    PROCESSING --> REFUNDED: RefundSucceeded
    PROCESSING --> FAILED: RefundFailed
    FAILED --> PROCESSING: RetryRefund (per policy)
    REFUNDED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
~~~

- `RefundRequest` is an aggregate with `refundRequestId`, `orderId`, `paymentId`, and `amount`/`currency` snapshots. `Order` and `Payment` still have their own owners.
- A `RefundRequest` cannot be approved if cancelled/rejected; `amount` must be positive and within the refundable limit. The rule **total amount across multiple refund requests cannot exceed the payment amount** needs an arbitration point at the authoritative Payment/Refund ledger—it cannot be protected solely by a `CHECK` constraint on an individual `RefundRequest`.
- Only `APPROVED` may run `SubmitRefund`; `RefundSucceeded` must include `paymentRefundId` and a verified outcome from the processor. Retries must use an idempotency key tied to the same refund intent so duplicate gateway transactions are not created.
- Store history of who approved, when, amount, calculation basis, and integration outcomes. Never alter historical unit prices when Catalog updates prices.
- Optimistic locking protects against two staff members approving concurrently; outbox/inbox and idempotency protect against communication failures. Reconciling with Payment handles cases where a delayed success response arrives after a timeout.

Specifically, if Payment reports success while `RefundRequest` is still `PROCESSING` due to a transient consumer crash, you need a recovery workflow rather than initiating a **new** refund transaction. The difference between "result not yet received" and "definitely not executed" carries major financial impact.

## 13. Common Mistakes and Checklist

| Design mistake | Consequence | Fix |
| --- | --- | --- |
| Controller allows arbitrary status updates | Bypasses preconditions and forbidden states | Domain commands with an explicit transition table |
| Mixing `OVERDUE` into workflow states | Clock-dependent status becomes stale | Compute derived state or manage time-driven updates separately |
| One service directly updates another bounded context's table | No single data owner; hard to evolve | Invoke commands/contracts through the authoritative owner |
| Validating status only in the UI | Workers/batches/other APIs write invalid states | Enforce invariants in the domain and guarded DB write paths |
| Saving Ticket then publishing event in a separate transaction without recovery | Lost events on crash between steps | Outbox in the same commit plus relay/retry |
| Retrying without a `commandId` | Duplicates side effects or emits false events | Idempotency and durable command results |
| Saving current status without transition history | Cannot tell who changed it, why, or when | Policy-driven transition history/audit |
| Deleting records immediately on `CLOSED` | Loses auditability and analytics | Separate closing, archiving, and delete/anonymize |
| Allowing commands to bypass tenant or authorization checks | Cross-tenant data leaks and unauthorized edits | Check authorization with tenant and specific resource |
| Sharing one status across workflow and message relay | Complexity and mixed responsibilities | Separate domain status from infrastructure status |

**Checklist before finalizing the data model:**

- Do states accurately express business semantics without mixing in priority, deadlines, or broker states?
- Is there a command/transition table specifying preconditions, postconditions, actors, and error cases?
- Does every field and invariant have a clear owner rather than being mutated ad hoc by multiple services?
- Are changes within an aggregate committed atomically with necessary versions/locks and constraints?
- Are retries, timeouts, concurrent edits, and duplicate/late messages covered by tests?
- Are snapshots, history, actors, timestamps, and request identifiers sufficient for traceability?
- Are business termination, long-term archival, and policy-based deletion/anonymization clearly separated?
- Do the chosen storage engine and indexes properly serve commands, queries, consistency, and evolvability?

**Conclusion:** A domain data model is more than entities with keys and relationships. **Lifecycle** explains valid states; **ownership** defines who holds authority over data; **commands** define how state changes while preserving invariants. Combined with transactions, concurrency control, history, events, and retention policies, you get a design that is clear, verifiable, and flexible enough to grow alongside business requirements.
