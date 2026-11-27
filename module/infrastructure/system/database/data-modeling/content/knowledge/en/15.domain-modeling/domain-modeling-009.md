# Avoiding Getter/Setter-Only Models When Business Rules Must Be Protected

## Learning Objectives

After this lesson, you will be able to:

- Recognize an **anemic domain model** and distinguish it from DTOs, read records, persistence entities, or genuinely simple CRUD.
- Replace arbitrary setters with **domain-meaningful operations** complete with preconditions, postconditions, and explicit error cases.
- Place **invariants** on aggregate roots, value objects, domain services, or database constraints according to their proper scope of responsibility.
- Close direct write paths to child entities and internal state while still supporting queries, persistence mapping, and testing.
- Combine domain behavior with transactions, version checks, constraints, and authorization to protect state under concurrent requests.
- Evaluate when a behavior-rich model pays off and when a transaction script or simple data model is the right choice.

In **DATABASE_DATA_MODELING**, business requirements must be translated into verifiable entities, relationships, constraints, keys, and schemas. If you only create classes with fields and getters/setters, a system can **persist data** without protecting what that data means. The issue is not getter/setter syntax; the issue is **who can put an object into an invalid state, and whether anything stops that before commit**.

## 1. How Can a Getter/Setter-Only Model Break?

Suppose a system manages **internal purchase requests**. An employee creates a `PurchaseRequest` with product lines, submits it for approval, and an authorized person approves or rejects it.

Confirmed business rules:

- Only a request in **`DRAFT`** status may add, remove, or edit line items.
- Line items must have a positive quantity and a positive VND unit price.
- An empty request with no lines cannot be **`SUBMIT`**ted.
- Only a **`SUBMITTED`** request may be **`APPROVE`**d.
- A requester cannot approve their own request.
- Once approved, expense contents must remain unchanged; any adjustments require a separate workflow.
- Total cost equals the sum of line totals; users must never write a mismatched number directly.

A data-only style class:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Counterexample: class does not protect invariants.
class PurchaseRequestData {
    private UUID id;
    private String status;
    private long totalVnd;
    private List<PurchaseLineData> lines = new ArrayList<>();

    public void setStatus(String status) { this.status = status; }
    public void setTotalVnd(long totalVnd) { this.totalVnd = totalVnd; }
    public List<PurchaseLineData> getLines() { return lines; }

    // Other getters/setters...
}

class PurchaseLineData {
    public UUID productId;
    public int quantity;
    public long unitPriceVnd;
}
~~~

Code anywhere in the codebase can call `setStatus("APPROVED")` on an unsubmitted request, call `setTotalVnd(1)` even though the lines total millions, or call `getLines().clear()` to wipe all lines after approval. Even if a controller checks before calling setters, a batch job, new API endpoint, or data import pipeline can bypass those checks.

**The flaw is not having getters.** A read-only getter can be safe; a scoped, validated setter is not automatically wrong. The design flaw here is **overly broad mutation access with no single authority responsible for enforcing rules**.

### Signs of an Anemic Domain Model

| Symptom | Risk | Question to ask |
| --- | --- | --- |
| Entities only have fields and public setters | Any caller can create invalid states | Which business operations are actually allowed? |
| Services just chain multiple setters in sequence | Rules are scattered, easily forgotten, or partially executed | Which changes must happen as a single unit? |
| Totals, balances, or derived states set arbitrarily | Conflicting data | Should they be computed rather than set directly? |
| Returning mutable internal `List`/`Map` references | Callers mutate child entities behind the root's back | Can you return an immutable view/snapshot? |
| Controllers decide every state transition | Batch jobs, listeners, or imports bypass rules | Which component owns the invariants? |
| Validation exists only in the UI | Direct or concurrent requests violate rules | What safeguards exist in the domain and database? |

## 2. Distinguishing Data Structures from Domain Models

Do not conclude that every data-holding class must become a behavior-heavy object. The same system can have models with distinct responsibilities:

| Object type | Role | Are getters/setters appropriate? |
| --- | --- | --- |
| **Request DTO** | Receives data from HTTP/APIs | Yes, though data is untrusted; must validate and convert to commands |
| **Response DTO** | Outputs data to clients | Getters or immutable records are completely normal |
| **Read model / projection** | Powers screens, analytics, search | Usually data-focused; does not own write rules |
| **Persistence row / ORM mapping** | Maps storage columns and relationships | May have framework-required accessors; write paths must be restricted |
| **Value object** | Expresses a constrained value | Typically immutable; validates upon construction |
| **Entity / aggregate root** | Owns identity, lifecycle, and invariants | Should expose business operations whenever rules need protection |
| **Domain service** | Expresses domain rules that do not naturally fit one entity | Holds business behavior, not just CRUD |

For example, a response DTO containing `{requestId, status, totalVnd, lines}` with getters causes no harm because a DTO **is not the authoritative source for transitioning request status**.

By contrast, if `PurchaseRequest` is the aggregate root responsible for submission/approval rules, letting callers change status through a public setter grants a backdoor past the business boundary.

## 3. Identify Invariants Before Choosing Methods

An **invariant** is a condition that must hold across all valid states the model commits to preserve. Write invariants in testable form, then assign **ownership**.

| Invariant | Verification scope | Responsible owner |
| --- | --- | --- |
| `quantity > 0` and `unitPriceVnd > 0` | One line item | `PurchaseLine` value object/entity |
| `lineId` is unique within the request | One `PurchaseRequest` | Aggregate root |
| Only `DRAFT` allows line edits | Status and line items | Aggregate root |
| `SUBMITTED` must have at least one line | Line collection and status | Aggregate root, DB write protocol |
| `APPROVED` has an approver distinct from requester | Status and two identities | Aggregate root, plus application authorization |
| Total equals sum of `quantity * unitPrice` | All lines | Computed from lines inside root; if cached, updated atomically |
| Total budget across requests stays within limit | Multiple `PurchaseRequest`s and budget pool | Budget aggregate / authoritative allocation mechanism |

Do not pull **the entire budget, employee profiles, and vendor records** into `PurchaseRequest` just to call their getters. Those objects can be separate aggregates. `PurchaseRequest` holds identifiers and required evidence/versions; approval permissions and budget checks coordinate with their authoritative owners.

### Business Commands Instead of Arbitrary Column Edits

| Business command | Preconditions | Postconditions on success |
| --- | --- | --- |
| `AddLine` | `DRAFT`; fresh `lineId`; valid `productId`; positive quantity/unit price | Line added; line-derived total updates |
| `ChangeQuantity` | `DRAFT`; line exists; new quantity positive | Line replaced with valid value |
| `RemoveLine` | `DRAFT`; line exists | Line removed; `DRAFT` may temporarily be empty |
| `SubmitRequest` | `DRAFT`; has lines; valid total calculation | Status transitions to `SUBMITTED` |
| `ApproveRequest` | `SUBMITTED`; actor != requester; actor authorized | Status becomes `APPROVED`, `approverId` stored |
| `RejectRequest` | `SUBMITTED`; actor authorized; reason provided | Status becomes `REJECTED` |
| `CancelRequest` | `DRAFT` or `SUBMITTED`; actor authorized | Status becomes `CANCELLED` |

Here, one `AddLine` operation can change multiple fields; one `ApproveRequest` records status, approver, timestamp, and approval history. These updates must be treated as **one business decision**, not independent setters.

## 4. Designing an Aggregate Root with a Domain-Meaningful API

A responsibility diagram:

~~~mermaid
flowchart LR
    HTTP["HTTP request / UI"] --> DTO["Request DTO"]
    DTO --> APP["Application service"]
    APP --> AUTH["Authorization and scope check"]
    APP --> ROOT["PurchaseRequest aggregate root"]
    ROOT -->|"coordinates changes"| LINE["PurchaseLine"]
    ROOT --> REPO["PurchaseRequestRepository"]
    REPO --> DB[("DB transaction")]
    APP -.->|"budgetId / approval evidence"| EXT["Other aggregate or service"]
~~~

The application service orchestrates use cases, verifies permissions, loads/saves aggregates, manages transactions, and talks to external systems. The aggregate root **decides whether internal state after a command is valid**. Value objects validate the integrity of their own values.

This design does not mean the application service has zero logic: it still enforces authorization, coordinates transactions, and drives cross-aggregate workflow rules. However, it should not duplicate "only `DRAFT` can edit lines" across five different controllers.

### Read Paths and Write Paths Differ

Allowing reads of status, ID, total, or an unmodifiable line list is usually helpful. What must be avoided is letting callers mutate **internal memory directly** and break invariants behind the root's back.

In Java, you can use:

- private fields and domain-named methods;
- immutable records/value objects for members where appropriate;
- `List.copyOf` or `Map.copyOf` to return unmodifiable collections;
- constructors/factories validating inputs;
- strongly typed IDs to prevent mix-ups;
- controlled state reconstitution paths for repositories rather than wide-open public setters.

**Encapsulation does not replace authorization.** Knowing `requestId` does not authorize a user to approve it; the application service must obtain the actor from the authenticated security context rather than trusting a client-supplied `approverId`.

## 5. Java 17 Example: Behavior Instead of Getters/Setters

The example below uses integer **VND** units with `long`; multi-currency systems need a `Money` value object with currency, scale, and proper rounding rules. It models only internal purchase request invariants, not shared budget caps.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

enum PurchaseStatus {
    DRAFT, SUBMITTED, APPROVED, REJECTED, CANCELLED
}

record PurchaseLine(
        UUID lineId, UUID productId, int quantity, long unitPriceVnd) {
    PurchaseLine {
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(productId);
        if (quantity <= 0) throw new IllegalArgumentException("quantity");
        if (unitPriceVnd <= 0) throw new IllegalArgumentException("unit price");
    }

    long lineTotalVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    PurchaseLine withQuantity(int newQuantity) {
        return new PurchaseLine(lineId, productId, newQuantity, unitPriceVnd);
    }
}

final class PurchaseRequest {
    private final UUID requestId;
    private final UUID requesterId;
    private final Map<UUID, PurchaseLine> lines = new LinkedHashMap<>();
    private PurchaseStatus status = PurchaseStatus.DRAFT;
    private UUID approvedBy;
    private String rejectionReason;
    private long version;

    PurchaseRequest(UUID requestId, UUID requesterId) {
        this.requestId = Objects.requireNonNull(requestId);
        this.requesterId = Objects.requireNonNull(requesterId);
    }

    void addLine(UUID lineId, UUID productId, int qty, long priceVnd) {
        requireDraft();
        PurchaseLine line = new PurchaseLine(lineId, productId, qty, priceVnd);
        if (lines.containsKey(lineId)) {
            throw new IllegalArgumentException("Duplicate line ID");
        }
        // Ensure the new total does not overflow long before writing.
        Math.addExact(totalVnd(), line.lineTotalVnd());
        lines.put(lineId, line);
        version++;
    }

    void changeQuantity(UUID lineId, int newQuantity) {
        requireDraft();
        PurchaseLine current = lines.get(lineId);
        if (current == null) throw new IllegalArgumentException("Unknown line");
        PurchaseLine updated = current.withQuantity(newQuantity);
        // Check total before updating state.
        long nextTotal = 0;
        for (PurchaseLine line : lines.values()) {
            nextTotal = Math.addExact(nextTotal,
                line.lineId().equals(lineId)
                    ? updated.lineTotalVnd() : line.lineTotalVnd());
        }
        lines.put(lineId, updated);
        version++;
    }

    void removeLine(UUID lineId) {
        requireDraft();
        if (lines.remove(lineId) == null) {
            throw new IllegalArgumentException("Unknown line");
        }
        version++;
    }

    void submit() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Empty request");
        totalVnd(); // validates total, including overflow if any
        status = PurchaseStatus.SUBMITTED;
        version++;
    }

    void approve(UUID authenticatedApproverId) {
        requireSubmitted();
        Objects.requireNonNull(authenticatedApproverId);
        if (requesterId.equals(authenticatedApproverId)) {
            throw new IllegalStateException("Self approval forbidden");
        }
        approvedBy = authenticatedApproverId;
        status = PurchaseStatus.APPROVED;
        version++;
    }

    void reject(String reason) {
        requireSubmitted();
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Rejection reason required");
        }
        rejectionReason = reason.strip();
        status = PurchaseStatus.REJECTED;
        version++;
    }

    void cancel() {
        if (status != PurchaseStatus.DRAFT
                && status != PurchaseStatus.SUBMITTED) {
            throw new IllegalStateException("Cannot cancel in " + status);
        }
        status = PurchaseStatus.CANCELLED;
        version++;
    }

    long totalVnd() {
        long total = 0;
        for (PurchaseLine line : lines.values()) {
            total = Math.addExact(total, line.lineTotalVnd());
        }
        return total;
    }

    List<PurchaseLine> linesView() {
        return List.copyOf(lines.values()); // records are immutable
    }
    UUID id() { return requestId; }
    UUID requesterId() { return requesterId; }
    PurchaseStatus status() { return status; }
    UUID approvedBy() { return approvedBy; }
    long version() { return version; }

    private void requireDraft() {
        if (status != PurchaseStatus.DRAFT) {
            throw new IllegalStateException("Request is not editable");
        }
    }
    private void requireSubmitted() {
        if (status != PurchaseStatus.SUBMITTED) {
            throw new IllegalStateException("Request is not submitted");
        }
    }
}
~~~

Here **`PurchaseLine`** is an immutable record with `lineId`; the root swaps in a new record when quantity changes. The line still retains **business identity** even though the Java object instance is replaced. Record immutability and `List.copyOf` stop callers from mutating line state through the returned collection.

**`totalVnd()` is derived from the lines**, not set via a setter on a `total` field for clients to supply. `Math.multiplyExact`/`Math.addExact` catch arithmetic overflow on `long`; for larger magnitudes, pick a suitable numeric type rather than dropping checks. Incrementing `version` in memory only tracks the domain version; **the repository must still check the original version on write**.

This snippet omits database reconstitution, domain events, approval timestamps, and budget limits. The repository must provide a way to **rehydrate** the object from persisted data without invoking commands like `addLine`/`approve` that replay business logic and trigger side effects. Once loaded, the root must reflect exact status, lines, and version; implementation depends on the framework, yet should never expose public setters to arbitrary callers.

If the system needs taxes, multiple currencies, discounts, or purchasing limits, model them as explicit value objects/rules and assign proper owners; never cram every cross-system policy into an oversized `PurchaseRequest` class.

## 6. Do Not Confuse Input Validation with Business Invariants

Three complementary layers of control exist:

| Layer | Appropriate checks | Example |
| --- | --- | --- |
| **API / input validation** | Data types, format, required fields, request size limits | `quantity` is an integer, `lineId` has UUID syntax |
| **Domain model** | State-dependent business rules, cross-field relationships, legal transitions | Only `DRAFT` is editable; no self-approval; `SUBMITTED` has lines |
| **Database** | Keys, `UNIQUE`, `CHECK`, `FK`, transactions, and concurrency checks | `quantity > 0`, unique `lineId`, optimistic `version` |

None of the three layers fully replaces the other two:

- API validation does not protect batch jobs or internal commands that bypass HTTP.
- An in-memory domain model does not automatically protect two processes writing to the same row simultaneously.
- SQL `CHECK` constraints cannot conveniently express every policy, such as role-based approval hierarchy or budget status in another system.

A rule can appear across multiple layers for **different protective purposes**. For instance, `quantity > 0` is checked in the constructor to fail fast and in a database `CHECK` constraint to block invalid data from any write path. That is not wasteful duplication when each layer's role is clear.

## 7. Put Behavior on Entity, Value Object, or Domain Service?

Not every rule belongs on the aggregate root:

**Value object:** `Money`, `DateRange`, `Quantity`. They protect the validity of the value itself. For example, `DateRange` forbids `end` before `start`; `Money` forbids directly adding incompatible currencies.

**Child entity:** `PurchaseLine` can encapsulate validated quantity changes, while the root `PurchaseRequest` decides **when** it may change because that depends on `DRAFT` status. External code must not grab a child entity and mutate it directly around the root.

**Aggregate root:** Cross-line or status-dependent conditions on the request, such as "only `DRAFT` edits lines" or "no self-approval." The root is also the gateway for the repository to persist a consistent unit.

**Domain service:** Used when a pure business rule does not naturally belong to a single entity or value object. For example, evaluating purchasing authority by grade, threshold, and item category can be a policy/domain service accepting inputs and returning a decision; the root accepts valid proof/decision if the workflow requires it.

**Application service:** Loads `PurchaseRequest`, authenticates the actor, queries external policies/services, invokes domain behavior, coordinates transactions, and saves via the repository. It should not become a "god service" packed with `if` statements inspecting internal state.

A division of responsibilities:

~~~mermaid
sequenceDiagram
    participant U as User/API
    participant A as Application Service
    participant P as Approval Policy
    participant R as PurchaseRequest root
    participant D as Repository/DB

    U->>A: ApproveRequest(requestId)
    A->>A: Authenticate actor, tenant, access rights
    A->>D: Load request + version
    D-->>A: Aggregate in SUBMITTED
    A->>P: Check approval scope, threshold, budget policy
    P-->>A: Approved for attempt / rejected
    A->>R: approve(authenticatedApproverId)
    R->>R: Block self-approval, check status
    A->>D: Save with expectedVersion + transaction
    D-->>A: Commit or version conflict
    A-->>U: Command result
~~~

If a policy must hold **at the exact instant of commit**, an earlier answer from a policy service may already be stale. Design valid approval tokens, locks/versions at the authoritative source, or an explicit confirmation protocol. Never assume calling a behavior-rich method automatically solves concurrent changes in external data.

## 8. Mapping a Behavior-Rich Model to PostgreSQL

One aggregate can span **multiple tables**. The example below has a request table and a line table; they still form one consistency unit when write paths are designed properly.

~~~sql
CREATE SCHEMA IF NOT EXISTS procurement;

CREATE TABLE procurement.purchase_request (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN (
            'DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED'
        )),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    approved_by UUID,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, request_id),
    CONSTRAINT approval_fields_match_status
        CHECK (
            (status = 'APPROVED') =
            (approved_by IS NOT NULL AND approved_at IS NOT NULL)
        ),
    CONSTRAINT cannot_self_approve
        CHECK (approved_by IS NULL OR approved_by <> requester_id),
    CONSTRAINT rejection_reason_required
        CHECK (
            status <> 'REJECTED' OR
            (rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)
        )
);

CREATE TABLE procurement.purchase_line (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    line_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd > 0),
    PRIMARY KEY (tenant_id, request_id, line_id),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES procurement.purchase_request(tenant_id, request_id)
);

CREATE INDEX purchase_request_pending_approval
    ON procurement.purchase_request(tenant_id, created_at)
    WHERE status = 'SUBMITTED';
~~~

**This is an illustrative schema.** Production systems may need price/currency snapshots, tax rules, and multi-level approval states; model those explicitly rather than stretching the schema with uncontrolled setters.

### What Do the Constraints Protect?

- **`PRIMARY KEY`** and **`FOREIGN KEY`** protect identity and ensure lines belong to a request in the same tenant.
- **`CHECK`** protects positive quantities, positive unit prices, and certain invariants linking `status` with `approvedBy`/`approvedAt`.
- **`UNIQUE`/`PK`** prevents duplicate `lineId`s within the same request.
- **Partial index** supports querying the pending-approval queue; it is not a state transition constraint.

They **do not yet** enforce "SUBMITTED must have at least one line", "only DRAFT allows line edits", or "user has hierarchical approval authority." Those rules need domain behavior paired with write protocols and authorization; when guarding against direct out-of-band SQL writes as well, consider triggers/procedures, DB privileges, and auditing.

In this example, `totalVnd` is not stored on the request to avoid a duplicated source that could drift. When line counts are bounded, totals can be summed from `purchase_line` or read projections. If a materialized total is needed for performance, treat it as data updated **atomically** alongside lines whenever lines change.

## 9. In-Memory Behavior Needs Transactions and Concurrency Control

Suppose T1 and T2 both read `PurchaseRequest` in `DRAFT` at version 6:

1. T1 adds a line and saves the request as version 7.
2. T2 also adds a different line based on version 6.
3. If the repository blindly writes back the entire list without checking version, T2 can overwrite T1's line (**lost update**) or both can produce an unexpected state.

An **optimistic locking protocol** on the root:

~~~sql
BEGIN;

-- Every command editing lines must lock/bump the root version before modifying child tables.
UPDATE procurement.purchase_request
SET version = version + 1
WHERE tenant_id = :tenant_id
  AND request_id = :request_id
  AND status = 'DRAFT'
  AND version = :expected_version
RETURNING version;

-- If 0 rows: ROLLBACK and report VERSION_CONFLICT or INVALID_STATE.
-- If 1 row: INSERT/UPDATE/DELETE purchase_line per domain result.

UPDATE procurement.purchase_line
SET quantity = :new_quantity
WHERE tenant_id = :tenant_id
  AND request_id = :request_id
  AND line_id = :line_id
  AND :new_quantity > 0;

-- Must verify exactly 1 row updated; otherwise ROLLBACK.
COMMIT;
~~~

This is an **example of updating quantity** after the domain has called `changeQuantity`, not a raw command allowed straight from HTTP. Every write path adding, deleting, or editing lines must follow the same root-first locking protocol. If another worker updates `purchase_line` without checking the root's status/version, the rule "SUBMITTED cannot edit lines" can be broken.

### Approval Transaction

Upon approval, status and approver are recorded atomically:

~~~sql
BEGIN;

UPDATE procurement.purchase_request AS p
SET status = 'APPROVED',
    approved_by = :authenticated_approver_id,
    approved_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE p.tenant_id = :tenant_id
  AND p.request_id = :request_id
  AND p.status = 'SUBMITTED'
  AND p.requester_id <> :authenticated_approver_id
  AND p.version = :expected_version
  AND EXISTS (
      SELECT 1 FROM procurement.purchase_line AS l
      WHERE l.tenant_id = p.tenant_id
        AND l.request_id = p.request_id
  )
RETURNING version;

-- If 0 rows: do not treat approval as successful; ROLLBACK.
-- If audit/outbox is used, write in the same transaction before COMMIT.
COMMIT;
~~~

SQL checks status and line existence, yet **`EXISTS` alone is not enough** if any delete path ignores the root locking protocol. When every line-modifying command locks the root first, the last line cannot be legally deleted during approval. If you need protection even against direct SQL paths, add DB privileges and database-level mechanisms.

**Version note:** the Java example increments `version` in memory on each change. The repository must retain `originalVersion` on load to pass as `:expected_version`, then persist the final version produced by the domain; in the SQL above, one command makes one step so `version` increments by 1. If a use case invokes multiple behaviors before commit, never silently ignore version deltas; design a unified protocol for final version values and related events/audits.

### DB and Application Layers Should Not Have Competing Write Paths

An organization may allow services to write only through authorized repositories while granting dashboard DB roles `SELECT` only. If multiple services update the same table directly simply because they share a database, no single component remains responsible for invariants.

Encapsulation in Java is valuable, yet insufficient if scripts/batches mutate tables directly. Write paths and DB access privileges are part of **physical data model design**.

## 10. Testing Behavior Instead of Testing Setters

Unit tests should specify **rules**, not just verify that `set` followed by `get` returns the value. JUnit 5 example for the class above:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.UUID;

class PurchaseRequestTest {
    @Test
    void cannotSubmitEmptyRequest() {
        var request = new PurchaseRequest(UUID.randomUUID(), UUID.randomUUID());
        assertThrows(IllegalStateException.class, request::submit);
        assertEquals(PurchaseStatus.DRAFT, request.status());
    }

    @Test
    void cannotEditAfterSubmitting() {
        var request = new PurchaseRequest(UUID.randomUUID(), UUID.randomUUID());
        var lineId = UUID.randomUUID();
        request.addLine(lineId, UUID.randomUUID(), 2, 100_000);
        request.submit();
        assertThrows(IllegalStateException.class,
            () -> request.changeQuantity(lineId, 3));
        assertEquals(200_000, request.totalVnd());
    }

    @Test
    void requesterCannotApproveOwnPurchase() {
        var requester = UUID.randomUUID();
        var request = new PurchaseRequest(UUID.randomUUID(), requester);
        request.addLine(UUID.randomUUID(), UUID.randomUUID(), 1, 250_000);
        request.submit();
        assertThrows(IllegalStateException.class,
            () -> request.approve(requester));
        assertEquals(PurchaseStatus.SUBMITTED, request.status());
    }

    @Test
    void authorizedApproverCanApproveSubmittedRequest() {
        var requester = UUID.randomUUID();
        var approver = UUID.randomUUID();
        var request = new PurchaseRequest(UUID.randomUUID(), requester);
        request.addLine(UUID.randomUUID(), UUID.randomUUID(), 1, 250_000);
        request.submit();
        request.approve(approver); // Assumes service already verified actor permissions.
        assertEquals(PurchaseStatus.APPROVED, request.status());
        assertEquals(approver, request.approvedBy());
    }
}
~~~

These tests guard behavior **within a single process**. Add integration tests against a real PostgreSQL instance for behaviors that mocks cannot faithfully simulate:

| Scenario | What to verify |
| --- | --- |
| Two commands editing the same version | At most one write against the stale version succeeds; the other reports a conflict |
| Submitting concurrently with deleting the last line | No `SUBMITTED` request with an empty line list exists after commit |
| Approving concurrently with editing a line | No `APPROVED` request ends up with edited lines afterward |
| Root write succeeds but audit/outbox write fails | Entire transaction rolls back |
| Retrying command after client loses response | No duplicate business side effects; returns outcome per `requestId`/idempotency |
| User tries to approve another tenant's request | Authorization and tenant scope block it |
| Script tries to edit lines bypassing the root | Blocked or detected per data defense policy |

**Never run tests solely against in-memory mocks and conclude multi-process consistency holds.** Locking, isolation, and conflict behavior must be verified against the actual storage engine.

## 11. When Is a Behavior-Rich Model Not the Best Choice?

Avoid the opposite extreme: forcing every table into a rich DDD entity when no significant business rules exist.

A rarely changing `CountryCode` or `LanguageCode` reference table, a display DTO, and an analytical read model usually do not need dozens of domain methods. A simple admin CRUD screen with no cross-field/scoped invariants and full protection from SQL constraints can use a **transaction script** or thin application service cleanly.

| Situation | Usually appropriate design |
| --- | --- |
| Multiple state transitions, invariants, and members needing consistency | Behavior-rich aggregate root |
| Small, immutable, reusable value calculations | Value object with suitable constructors/methods |
| Rules spanning multiple independent sources | Domain/application service + contracts, without stuffing all into one root |
| Simple CRUD adequately guarded by `CHECK`/`FK`/`UNIQUE` | Transaction script or simple data model |
| Search results and reports | Data-oriented DTO/read model |
| ORM requiring setters or no-arg constructors | Restrict framework access rather than exposing public business APIs |

Evaluation rule: **where does the cost of not violating rules sit?** If complex rules are being duplicated across controllers, batch jobs, and listeners, moving them into a behavior-rich domain model yields clear benefits. If a task merely saves a record with simple row-level constraints, an artificially behavior-heavy class adds overhead without reducing risk.

**Avoid both extremes:** an anemic setter-only model and an overstuffed model that directly performs DB I/O, sends emails, calls payment gateways, runs reporting logic, and absorbs unrelated workflows.

## 12. Compatibility Across Different Storage Models

An aggregate's goal stays the same across databases, while **enforcement mechanisms** vary:

| Storage model | How invariants are protected | Common pitfalls |
| --- | --- | --- |
| **Relational** | Root writes multiple tables in a transaction; `CHECK`, `FK`, `UNIQUE`, version/lock | ORM allowing direct child edits bypassing root; missing transactions |
| **Document** | Root and embedded members within atomic write scope; conditional updates/version | Assuming all documents/collections update atomically together |
| **Graph** | Commands through owner; engine-specific transactions and constraints | Traversing an edge and mutating any linked node just because a link exists |
| **Analytical/Columnar** | Event/projection data for aggregation and trend checks | Using delayed reports as the authority for grants or approvals |

For example, `PurchaseRequest` can store `lines` inside one document if sizes stay moderate and the DBMS supports the required atomic updates. Still, that never removes the need to check `DRAFT`, `version`, or self-approval. With relational tables, a 1-N relationship can still form **one logical aggregate** protected by transactions.

**Read models need not mirror write models.** Expense reports can JOIN `PurchaseRequest` with product catalogs and approvers, or build projections; needing joined reads is never a reason to let `PurchaseRequest` mutate employee or product records.

## 13. Practice Exercise: Product Return Request

**Context:** A store allows customers to request returns within 30 days of delivery. Each `ReturnRequest` contains one or more `ReturnLine`s. Accepted return quantities must not exceed the purchased quantity **minus quantities already returned in other requests**. Once inspection passes, the store confirms the refund; payment execution is handled in a separate Payment system. Users cannot edit return lines after a request is submitted.

### Questions

1. Write a `ReturnRequest` counterexample with `setStatus`, `setLines`, and `setRefundAmount`. List at least three invalid states a caller could produce.
2. Propose a domain API such as `addReturnLine`, `submit`, `acceptInspection`, `rejectInspection`, and `authorizeRefund`. What are the preconditions/postconditions for each command?
3. Does the rule "do not return more than purchased quantity minus prior returns" belong to a single `ReturnRequest`, or does it require an **authoritative return allowance source** across requests? Why?
4. Which data should be snapshotted (purchase price, currency, SKU), and which IDs reference `Order` or `Payment`?
5. If two different `ReturnRequest`s concurrently try to return the last remaining unit of an item, what database/transaction mechanism prevents over-returning?
6. Write a unit test showing a `SUBMITTED` request cannot call `addReturnLine`, plus an integration test illustrating two competing requests.
7. When Payment returns outcomes late or duplicated, how do `ReturnRequest` and `Payment` coordinate without assuming both share one transaction?

### Guided Solution Approach

- `ReturnRequest` is the root for a single request's lifecycle and its lines; never expose public setters to alter status or refund total. `ReturnLine` can be a value object/child entity with positive quantities and price snapshots.
- Refund totals must be calculated from quantities and committed prices per policy. Never use current Catalog prices to replace historical transaction prices.
- The rule capping **total returned quantity across multiple `ReturnRequest`s** must be enforced at an authoritative source—such as `ReturnAllowance`/`OrderReturnBalance` keyed by `(orderId, lineId)`. If each `ReturnRequest` merely checks stale copies it read, two concurrent requests could both approve the final unit.
- A relational approach uses a conditional `UPDATE` on the allowance row (`remainingQuantity >= requestedQuantity`) while recording the return grant in **the same transaction**. Across separate databases, you need return-grant tokens, idempotency, intermediate states, and explicit compensation.
- `Payment` is a separate aggregate/context returning outcomes via contracts with IDs, versions/idempotency. A `RefundSucceeded` delivered twice must never grant two refunds; timeouts require reconciliation instead of blindly issuing a brand-new refund command.
- You can use JOINs/read models to view `ReturnRequest`, `Order`, and `Payment` together without granting write authority over all three to one aggregate.

## 14. Checklist and Conclusion

- Are business rules scattered across controllers, batch jobs, listeners, or setters?
- Which invariants belong to value objects, child entities, aggregate roots, or external sources?
- Do method names express **business intent** (`submit`, `approve`, `cancel`) instead of arbitrary field mutations?
- Do getters expose mutable internal collections or objects that callers could change behind the root's back?
- Are status, totals, and derived data updated or computed from the authoritative source?
- Do input validation, domain validation, and DB constraints have clear, complementary roles?
- Does the application service check authorization from authenticated context rather than trusting client-passed actor IDs?
- Do all write commands use transactions, versions/locks, and proper rollbacks across multi-row/multi-step changes?
- Are concurrency conflicts, retries, invalid states, and root-bypassing write paths tested?
- Have you avoided cramming I/O, reporting, and independent aggregates into an overgrown entity?
- Do the chosen read paths and physical models fit workloads, invariants, and evolution costs?

**Conclusion:** A domain model is not judged by the count of getters/setters or classes. When business constraints exist, **behavior must live at the authority protecting those constraints**: value objects, aggregate roots, policies, and appropriate transactions/constraints. Getters can serve reads; setters can serve controlled persistence mapping; neither should become a shortcut that breaks invariants. By designing intent-revealing commands paired with storage-level concurrency control, you turn business requirements into data models that are safe, easy to verify, and built to evolve long-term.
