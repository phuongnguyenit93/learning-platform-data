# Cascading Deletes Destroying History That Must Be Retained

## 1. One Customer Delete Command Can Wipe Out Contracts and Records

Suppose an equipment rental system has `Customer`, `RentalContract`, `RentalItem`, and `PaymentMovement`. A customer requests account closure, and the application runs:

~~~sql
DELETE FROM customer
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

If the foreign keys from contract to customer, rental item to contract, and payment to contract are all configured with `ON DELETE CASCADE`, a single statement meant to affect only the customer profile can **wipe out all rental history, equipment lines, and confirmed transactions**.

Consequences:

- Nobody knows who rented which equipment, under what terms, or the pickup/return timestamps.
- Collections and refunds can no longer be reconciled against payment sources.
- Historical reports shift after the account is closed; revenue totals can drop artificially.
- Evidence needed to explain contract cancellations, disputes, or lost equipment vanishes.
- Copies in warehouses, caches, and backups may still hold the data, leaving source and derived stores inconsistent.
- Restoring backups can lose newer transactions committed after the backup point or resurrect personal data that had already been erased.

**Root cause:** confusing a **referential relationship** ("a contract has a customer") with a **lifecycle dependency** ("a contract cannot exist once the customer no longer has an account").

A foreign key constraint can be technically valid yet semantically wrong. Data deletion must be governed by **grain, event finalization points, data ownership, retention, and processing purpose**, not by the fact that two tables share a 1:N relationship.

### Running Scenario

Customer `CUS-42` has 3 finalized rental contracts, 7 rental lines, 5 confirmed collection/refund transactions, 1 expired draft cart with 2 lines, and 1 profile containing email/phone number. The goal is to **close the account and handle contact details per policy**, not automatically delete 3 contracts and 5 transactions.

## 2. Precisely Defining Three Operations: Closing, Canceling, and Deleting

| Operation | Business meaning | Must NOT be inferred |
| --- | --- | --- |
| `CloseCustomerAccount` | Revokes login access or account activity. | All past contracts and payments must disappear. |
| `CancelRentalContract` | Transitions a contract to canceled state, with terms and evidence. | Confirmed transactions may be deleted from history. |
| `EraseCustomerPrivateProfile` | Processes personal data within a **verified request scope**. | One SQL DELETE on the profile means every copy is gone. |
| `PurgeExpiredDraftCart` | Deletes expired draft data per policy. | The same rule applies to signed contracts. |
| `PurgeRetainedHistory` | Deletes history after retention obligations are met and no exceptions remain. | All data created at the same timestamp shares the same retention period. |

**Canceling an event is not equivalent to erasing the fact that it happened.** A canceled contract may still need to show the locked-in price, cancellation reason, and refund details. A `RefundRequested` transaction cannot stand in for `RefundConfirmed` if the provider has not confirmed the refund.

There is no universal retention period applicable to every contract or every jurisdiction. Retention durations, retention bases, legal holds, and exceptions must be determined by authorized stakeholders for each data category.

## 3. Every Relationship Needs an Independent Lifecycle Policy

| Relationship | Referential meaning | Deletion policy to consider |
| --- | --- | --- |
| Customer → RentalContract | Contract is linked to customer. | Contract may need to survive account closure. |
| RentalContract → RentalItem | Line item describes agreed equipment. | Finalized lines usually must stay with the contract. |
| RentalContract → PaymentMovement | Financial movement tied to contract. | Never delete confirmed transactions just because a UI cancels a contract. |
| DraftCart → DraftCartLine | Line is strictly part of a draft cart. | Can cascade when deleting an expired cart, if policy allows. |
| Session → SessionToken | Token used for an access session. | Can be revoked/deleted, separate from retained security audits. |
| Customer → SearchProjection | Derived copy for reading/searching. | Can be purged/rebuilt; not a source of truth. |
| Transaction → AuditRecord | Records finalized actions and sources. | Has its own retention/permissions; does not delete with parent by default. |

A signed `OrderLine` may be a dependent component in business terms yet still require **retaining history alongside its Order**, rather than cascading simply because an Order is hidden from the UI. A prerequisite for using cascade is that the parent **is allowed to be physically deleted** and every child deleted shares the exact same true lifecycle.

## 4. How `ON DELETE` Works in PostgreSQL

| FK option | Effect on parent delete | Appropriate condition |
| --- | --- | --- |
| `ON DELETE CASCADE` | Automatically deletes referencing child rows. | Child data has no remaining meaning or reason to retain once parent is deleted. |
| `ON DELETE RESTRICT` | Blocks parent deletion if child rows exist. | Need to protect referenced documents/historical records. |
| `ON DELETE NO ACTION` | Requires valid FK at check time; checked at statement end by default. | Can use a `DEFERRABLE` constraint when deferred checking is needed; logic must be verified. |
| `ON DELETE SET NULL` | Sets the child referencing column to NULL. | Child can exist without parent and loses no required evidence. |
| `ON DELETE SET DEFAULT` | Sets a default reference value. | Default is a valid reference with real business meaning. |

**`RESTRICT` and `NO ACTION` are not completely identical:** in PostgreSQL, `NO ACTION` checks can be deferred when the constraint is declared `DEFERRABLE`; `RESTRICT` cannot be deferred that way. Regardless of mechanism, a foreign key only protects referential integrity—it does not replace privacy or retention policies.

With composite foreign keys containing `tenant_id` and `customer_id`, `SET NULL` can conflict with `NOT NULL` or break tenant scoping if applied to the wrong column. Carefully design nullable fields and identity scope; do not mechanically copy a single-column FK example into a multi-tenant system.

## 5. Anti-Pattern: A Cascade Chain Valid in SQL, Broken for Data

This DDL is intentionally flawed for records that must be retained; **inspect or run only in an isolated database**, never use as-is in production:

~~~sql
CREATE SCHEMA IF NOT EXISTS demo_bad;

CREATE TABLE demo_bad.customer (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    full_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE demo_bad.rental_contract (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, rental_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_bad.customer (tenant_id, customer_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_bad.rental_item (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, rental_id, line_no),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_bad.rental_contract (tenant_id, rental_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_bad.payment_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_bad.rental_contract (tenant_id, rental_id)
        ON DELETE CASCADE
);
~~~

~~~mermaid
flowchart TD
    C["DELETE customer"] --> R["CASCADE rental_contract"]
    R --> L["CASCADE rental_item"]
    R --> P["CASCADE payment_movement"]
    L --> HIST["Lose finalized contract contents"]
    P --> CASH["Lose collection/refund evidence for reconciliation"]
~~~

The database is simply enforcing the declared constraints. **This is a lifecycle design error, not a PostgreSQL bug.**

Deleting one `customer` with 3 contracts, 7 lines, and 5 movements can erase all four data tiers simultaneously. Never assume an operation is safe just because the application issues one DELETE and sees "1 row affected" on the entry table.

## 6. Trace the Entire Cascade Chain Instead of Checking Only One FK

When auditing a delete operation, locate all FKs pointing to the parent table and keep traversing through each child table that would be deleted.

PostgreSQL stores foreign key metadata in `pg_constraint`:

~~~sql
SELECT con.conrelid::regclass AS child_table,
       con.confrelid::regclass AS parent_table,
       con.conname AS fk_name,
       CASE con.confdeltype
          WHEN 'a' THEN 'NO ACTION'
          WHEN 'r' THEN 'RESTRICT'
          WHEN 'c' THEN 'CASCADE'
          WHEN 'n' THEN 'SET NULL'
          WHEN 'd' THEN 'SET DEFAULT'
       END AS on_delete_action,
       pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.contype = 'f'
  AND con.connamespace = 'demo_bad'::regnamespace
ORDER BY parent_table, child_table, fk_name;
~~~

Check:

1. Target table → all FKs referencing that table.
2. For every `CASCADE` FK, continue finding FKs referencing that child table.
3. Identify multiple cascade paths leading to the same table, lock cycles, row volumes, and transaction consistency.
4. Search for triggers, stored procedures, cleanup jobs, ORM/JPA cascades, and outbox/event handlers.
5. Verify execution privileges, queries missing `tenant_id`, automated purge schedules, and partition maintenance.
6. Expand the audit to search, cache, warehouse, event store, backups/replicas, and related services.

Querying `pg_constraint` **only reveals FKs inside the database being inspected**. It does not reveal deletions across external service APIs or application side effects.

### Three Mechanisms with Similar Names but Different Effects

| Mechanism | Effect |
| --- | --- |
| `DELETE FROM parent ...` with `ON DELETE CASCADE` FK | Deletes **child rows with FK references** to the deleted parent rows, and may cascade further. |
| `TRUNCATE parent CASCADE` | Can truncate **all referencing tables in full** per TRUNCATE semantics, not just rows for one customer. |
| `DROP TABLE parent CASCADE` | Drops the schema object and dependent objects; not a conditional row-level DELETE. |

`TRUNCATE ... CASCADE` is extremely dangerous when mistaken for a "faster" way to delete a few customer rows. Always review table-wide impact independently.

## 7. Classifying Data: Records, Ephemeral Data, PII, and Derived Copies

One table may hold several categories of facts with different lifecycle requirements. Analyze by **semantics** rather than table names alone.

| Category | Example | Evaluation principle |
| --- | --- | --- |
| **Finalized business record** | Contract, invoice, issued ticket. | Retain where justified; fix errors via proper corrections/adjustments. |
| **Confirmed financial movement** | Provider-confirmed capture/refund. | Never delete alongside account; must reconcile via reference/ID. |
| **In-progress** | Pending payment, unknown-outcome refund. | Do not assume timeout equals failure; retain enough state for recovery. |
| **Draft/ephemeral** | Cart, draft line, temporary search. | May cascade on expiration when no retention obligation remains. |
| **Current personal data** | Email, phone, display name. | Dedicated processing purpose, retention/erasure, and access control. |
| **Derived copy** | Cache, search projection, dashboard mart. | Sync lifecycle and reconcile with authoritative source. |
| **Audit/event history** | Contract cancellation event, permission changes. | May require independent history, while minimizing PII and setting separate retention. |

**Do not treat account retention as the retention period for every fact carrying `customer_id`.** Contract retention may start from contract completion, dispute closure, or an approved business milestone; draft lines may follow a shorter schedule.

Document precisely **who has authority to decide** whether a fact is accepted and how long it survives: Customer Identity owns profiles, Rental owns contracts, Payment owns confirmed movements, and Analytics owns derived calculations.

## 8. Separating PII from Transaction History to Reduce Lifecycle Coupling

One modeling option separates:

- `CustomerSubject`: minimal identity reference and account state, with an appropriate retention basis.
- `CustomerPrivateProfile`: currently permitted contact information, governed by separate privacy workflows.
- `RentalContract`: signed document and locked-in values.
- `RentalItem`: contract line contents, independent of current catalog list prices.
- `PaymentMovement`: collection/refund facts confirmed with the provider.
- `Projection`: read-serving copy, deleted/rebuilt per owner rules.

~~~mermaid
flowchart LR
    S[("CustomerSubject")] --> C[("RentalContract")]
    C --> I[("RentalItem")]
    C --> M[("PaymentMovement")]
    S --> P[("CustomerPrivateProfile: PII")]
    C -. "Authoritative facts" .-> H[("History / Audit")]
    P -. "Policy-driven lifecycle" .-> E["Erasure workflow"]
~~~

Keeping `customer_id` or a surrogate ID does not automatically make data anonymous. An ID can still link back to an individual through another system. **Pseudonymization is not anonymization**; retention, access rights, and maps of linked sources still require governance.

### When a Contract Requires Signed Name/Address

If a document legally requires recording a name/address at signing time, define a **document snapshot** and retention policy for that specific field instead of simply JOINing the current Profile. At the same time, do not copy the entire personal profile into every row or event merely for query convenience.

## 9. Safer PostgreSQL Example: Protecting Records with `RESTRICT`

The model below separates the private profile from transaction rows; this is **one option when there is a valid basis to retain history**. It does not automatically satisfy every scenario requiring complete removal of identifiers.

~~~sql
CREATE SCHEMA IF NOT EXISTS demo_safe;

CREATE TABLE demo_safe.customer_subject (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    state_code VARCHAR(20) NOT NULL
        CHECK (state_code IN ('ACTIVE', 'CLOSED', 'ERASED_PROFILE')),
    closed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE demo_safe.customer_private_profile (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    email TEXT,
    phone_e164 TEXT,
    display_name TEXT,
    PRIMARY KEY (tenant_id, customer_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_safe.customer_subject (tenant_id, customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.rental_contract (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    agreed_total_minor BIGINT NOT NULL CHECK (agreed_total_minor >= 0),
    currency_code CHAR(3) NOT NULL,
    signed_at TIMESTAMPTZ NOT NULL,
    status_code VARCHAR(20) NOT NULL
       CHECK (status_code IN
         ('SIGNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    PRIMARY KEY (tenant_id, rental_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_safe.customer_subject (tenant_id, customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.rental_item (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    item_code TEXT NOT NULL,
    qty NUMERIC(18,3) NOT NULL CHECK (qty > 0),
    PRIMARY KEY (tenant_id, rental_id, line_no),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_safe.rental_contract (tenant_id, rental_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.payment_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    provider_name VARCHAR(60) NOT NULL,
    provider_reference VARCHAR(120) NOT NULL,
    movement_type VARCHAR(12) NOT NULL
       CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code CHAR(3) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    UNIQUE (tenant_id, provider_name, provider_reference),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_safe.rental_contract (tenant_id, rental_id)
        ON DELETE RESTRICT
);
~~~

Benefits and limitations:

1. `CustomerPrivateProfile` can be processed within PII scope **without deleting `RentalContract` and `PaymentMovement`**.
2. `customer_subject` holds a minimal ID for relationships; it **can still constitute personal data** and requires a retention basis, access controls, and end-of-retention handling.
3. `ON DELETE RESTRICT` prevents deleting the parent while finalized child rows reference it. By itself, it does not define who may purge once retention obligations expire.
4. Composite FKs including `tenant_id` enforce same-tenant linkage inside the DB.
5. `provider_reference` must truly be unique within the source scope; if a provider guarantees uniqueness only per merchant account or operation type, adjust the key accordingly.
6. `currency_code` and `amount_minor` only represent monetary figures and do not prove revenue; confirmed movements must originate from an approved Payment source.
7. If **`customer_subject` must be completely deleted** while contracts remain retained, this model must be redesigned around linkage (such as appropriate nullable references separating identity and documents) per policy. **Do not** drop FKs carelessly to create orphans or conceal residual linkability.

## 10. Setting Proper Policies for `SET NULL` and Referencing Records

`SET NULL` fits when a relationship is **genuinely optional** after parent deletion.

For example, a support ticket remains valid even if the assigned operator leaves:

~~~sql
CREATE TABLE demo_safe.support_operator (
    operator_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE demo_safe.support_ticket (
    ticket_id UUID PRIMARY KEY,
    assigned_operator_id UUID
        REFERENCES demo_safe.support_operator (operator_id)
        ON DELETE SET NULL,
    subject_text TEXT NOT NULL
);
~~~

This field means only "currently assigned operator"; if you need to know **who ever handled it**, store an assignment history separately. If applying `SET NULL` to `rental_contract.customer_id`, establish clear policies on how documents are reconciled with customers/sources and retained, rather than turning all history into "unknown."

`SET DEFAULT` is even riskier: substituting a dummy default customer ID to satisfy an FK can attribute many different people's documents to a single "UNKNOWN" customer. It is only valid if the default carries genuine business meaning, the target exists, tenant scoping holds, and explanatory provenance remains intact.

## 11. Soft Delete Is Not Equivalent to Erasing Personal Data

**Soft delete** marks a row instead of running a physical DELETE:

~~~sql
ALTER TABLE demo_safe.customer_subject
ADD COLUMN deleted_at TIMESTAMPTZ;

UPDATE demo_safe.customer_subject
SET state_code = 'CLOSED',
    closed_at = COALESCE(closed_at, now()),
    deleted_at = now()
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND state_code = 'ACTIVE';
~~~

It helps preserve references and prevent cascades, yet it does not prove erasure is complete:

- PII may remain in the profile, soft-deleted rows, indexes, WAL, backups, caches, and exports.
- Queries missing `deleted_at IS NULL` still return the row; historical queries mistakenly JOINing current state may drop facts.
- Unique constraints on email/phone can block new sign-ups or risk ID reuse if constraints are dropped carelessly.
- ORM delete/`orphanRemoval` can still physically delete children even if the parent changes state.
- `deleted_at` says nothing about processing status across all downstream systems.

If the goal is **closing an account**, call and name that command explicitly. If it is **erasing PII**, you need a dedicated verifiable workflow. If it is **canceling a contract**, use states/events instead of deleting records.

## 12. Business Cancellations and Refunds Are New Facts, Not Erasing the Past

A `RentalContract` that was `SIGNED` can become `CANCELLED`. That neither erases `RentalContractSigned` nor alters the original agreement contents.

Minimal state update example:

~~~sql
UPDATE demo_safe.rental_contract
SET status_code = 'CANCELLED'
WHERE tenant_id = :tenant_id
  AND rental_id = :rental_id
  AND status_code IN ('SIGNED', 'ACTIVE')
RETURNING tenant_id, rental_id, status_code;
~~~

This snippet illustrates only the update; production requires authorization, reason, actor, version/concurrency control, timestamp, business invariants, and appropriate outbox/audit logging.

Similarly, given confirmed `CAPTURE 500,000 VND` and `REFUND 100,000 VND`:

- Retain the `CAPTURE 500,000 VND` movement.
- Retain the `REFUND 100,000 VND` movement.
- Approved net cash calculation yields 400,000 VND; **do not** mutate the original CAPTURE into 400,000 or delete the REFUND.
- If a refund is still `REQUESTED`, do not count it as already refunded.

That is why payment history normally needs a **grain of one confirmed movement**, independent of account lifecycle.

## 13. ORM-Level CASCADE Can Also Destroy Records

In JPA/Hibernate:

~~~java
@Entity
class RentalContract {
    @OneToMany(
        mappedBy = "rentalContract",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<RentalItem> items;
}
~~~

Here `CascadeType.ALL` includes `REMOVE`; deleting the parent entity lets the ORM delete items. `orphanRemoval = true` can delete an item when it is removed from the collection at flush time, even if the developer thought they were only editing a list.

**Do not confuse:**

- `ON DELETE CASCADE` is enforced by the **DB foreign key** on DELETE regardless of client.
- `CascadeType.REMOVE` and `orphanRemoval` are ORM policies.
- Triggers, cleanup jobs, stored procedures, and event handlers may execute additional deletions.
- A system can have both DB cascades and ORM cascades; audit both.

For a draft cart whose items live strictly inside the cart, cascade can be right. For finalized contract lines, a `removeItem` method may need to record a **correction/version** rather than wiping traces.

## 14. CASCADE Remains Useful When Children Truly Have No Separate Lifecycle

The goal is not an absolute ban on cascade, but using it only when **every child is allowed to perish with its parent**.

~~~sql
CREATE TABLE demo_safe.draft_cart (
    tenant_id UUID NOT NULL,
    cart_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, cart_id)
);

CREATE TABLE demo_safe.draft_cart_line (
    tenant_id UUID NOT NULL,
    cart_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, cart_id, line_no),
    FOREIGN KEY (tenant_id, cart_id)
        REFERENCES demo_safe.draft_cart (tenant_id, cart_id)
        ON DELETE CASCADE
);
~~~

Conditions:

1. The cart is strictly a **draft**, not a finalized order document.
2. Cart lines have no independent retention or audit obligations.
3. Deleting expired carts past expiration is permitted by policy.
4. Once converted to an order, data must be persisted as `Order/OrderLine` in the authoritative source **before** deleting the cart.
5. Cleanup jobs are tenant-scoped, batched, observable, and retry-safe.

Two relationships with identical cardinality (1:N) can have **opposite deletion policies**, because their lifecycles and business evidence differ.

## 15. Erasing the Private Profile While Retaining Justified History

A local transaction illustrating **Customer Profile scope**:

~~~sql
BEGIN;

DELETE FROM demo_safe.customer_private_profile
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

UPDATE demo_safe.customer_subject
SET state_code = 'ERASED_PROFILE',
    closed_at = COALESCE(closed_at, now())
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

COMMIT;
~~~

This is **not** an end-to-end personal data erasure workflow. It handles only the `customer_private_profile` table in one database. You must also account for:

- Search, cache, analytics, exports, audits, logs, and message brokers.
- Backups/restores, replicas, retention, and limits on immediate deletion.
- Whether IDs or document facts still link back to the individual.
- Valid retention exceptions, reconciliation duties, or active disputes.
- Whether late-arriving old events/snapshots could re-write erased fields into projections.

State `ERASED_PROFILE` should be interpreted as **the profile in this source has been processed within the defined scope**, not "the entire organization has deleted every trace."

## 16. Impact Analysis Before Executing a DELETE

Never treat an API receiving a `customer_id` as sufficient authorization to delete. Count the records at risk first.

~~~sql
SELECT
    (SELECT COUNT(*)
     FROM demo_safe.rental_contract c
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS contracts_count,
    (SELECT COUNT(*)
     FROM demo_safe.rental_item i
     JOIN demo_safe.rental_contract c
       ON c.tenant_id = i.tenant_id
      AND c.rental_id = i.rental_id
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS items_count,
    (SELECT COUNT(*)
     FROM demo_safe.payment_movement p
     JOIN demo_safe.rental_contract c
       ON c.tenant_id = p.tenant_id
      AND c.rental_id = p.rental_id
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS movements_count;
~~~

**Counting at time T does not guarantee the row count deleted at T+1** if concurrent writes are occurring. When strong preconditions are needed, use proper isolation/locking or owner workflows. For operations capable of deleting large row counts, enforce limits, approvals, and checks across all in-scope sources.

Pre-deletion checklist:

- Which FKs, ORMs, triggers, or jobs could cascade deletes?
- Are there active contracts, disputes, legal holds, or pending refunds?
- Does the source allow deletion or only close/disable?
- Can necessary history be kept while minimizing identifying data?
- Does the purge path enforce tenant scope and retention dates?
- Are snapshots/backups and tested recovery runbooks in place?

Never run a risky DELETE in production just to "test a rollback." A database transaction can roll back row changes, yet external side effects and concurrent behaviors do not necessarily revert as expected.

## 17. Replacing CASCADE with RESTRICT Requires Both Migrations and App Changes

Once a flawed FK is found, changing only ORM annotations is insufficient; you must replace the database constraint and every parent-deletion path.

For example, on the test schema, **the actual FK name must be verified** via `pg_constraint` before use:

~~~sql
BEGIN;

ALTER TABLE demo_bad.rental_contract
DROP CONSTRAINT rental_contract_tenant_id_customer_id_fkey;

ALTER TABLE demo_bad.rental_contract
ADD CONSTRAINT rental_contract_customer_fk
FOREIGN KEY (tenant_id, customer_id)
REFERENCES demo_bad.customer (tenant_id, customer_id)
ON DELETE RESTRICT;

COMMIT;
~~~

Notes:

- Auto-generated constraint names may differ; this snippet is illustrative.
- DDL acquires locks and carries overhead; benchmark in a production-like environment and prepare rollback/timeouts.
- If using `NOT VALID` + `VALIDATE CONSTRAINT` on large tables, understand which constraints support it, enforcement for new rows, and cutover order.
- **Do not add a new RESTRICT and assume the old CASCADE is neutralized.** As long as the old CASCADE constraint exists, a deletion path remains; coordinate migrations/write paths to avoid a dangerous window.
- Before switching the FK, audit application code still calling `DELETE customer` and migrate it to proper account-closure/PII commands.
- If data was already mistakenly deleted, changing the FK **does not restore** lost rows; you need a recovery workflow from appropriate sources plus reconciliation with newly created data.

## 18. Cross-Service Deletion: Requires Workflows, Idempotency, and Reconciliation

Processing customer profiles typically involves multiple owners: Customer Identity, Rental, Payment, Search, Analytics, and Backup.

A workflow may track states such as:

| State | Meaning |
| --- | --- |
| `REQUESTED` | Request received from actor; scope not yet finalized. |
| `VERIFIED` | Requester authority has been verified. |
| `SCOPED` | Data to delete/minimize and justified retained portions are classified. |
| `IN_PROGRESS` | Owners are executing their respective steps. |
| `WAITING_DEPENDENCY` | A source or copy has not confirmed, or awaiting a retention condition. |
| `NEEDS_REVIEW` | Conflict between data rights and retention obligations, or insufficient evidence. |
| `COMPLETED` | Every step **within the confirmed scope** is verified or covered by a valid exception. |

~~~mermaid
flowchart TD
    A["Close / Erasure request"] --> B["Verify authority, policy, and scope"]
    B --> C{"Valid records require retention?"}
    C -->|Yes| D["Keep minimal history, minimize PII"]
    C -->|No| E["Purge per policy"]
    D --> F["Dispatch commands to each data owner"]
    E --> F
    F --> G["Customer Identity"]
    F --> H["Search / Analytics / Cache"]
    F --> I["Backup / Archive policy"]
    G --> J["Reconcile, record outcome"]
    H --> J
    I --> J
    J --> K{"Full scope verified?"}
    K -->|Not yet| L["Retry / Needs review"]
    K -->|Yes| M["Complete with explicit scope"]
~~~

Do not mark `COMPLETED` merely because the primary DELETE returned 1 row. Know which copies hold data needing action, backup retention rules, and how to prevent erased data from being restored.

### Outbox/Inbox and Tombstones

The owner can persist the profile change alongside an `outbox` record in one local transaction, then emit an event carrying ID, aggregate version, and scope while keeping raw PII out of the payload:

~~~json
{
  "event_id": "2d918b53-930b-49fa-b5e5-8f37db2f9261",
  "event_type": "CustomerPrivateProfileErased",
  "schema_version": 1,
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "customer_id": "11111111-1111-4111-8111-111111111111",
  "aggregate_version": 24,
  "payload": {
    "scope": "PRIVATE_PROFILE",
    "contact_fields_erased": true
  }
}
~~~

Consumers should deduplicate by `event_id`, compare versions so a late v23 event **cannot resurrect an email** erased at v24, and record verifiable outcomes. When rebuilding projections or replaying, enforce tombstone/erasure policies. An outbox does not guarantee end-to-end exactly-once delivery; consumers still require idempotency.

## 19. Warehouses, SCD2, and Reports Can "Lose History" Even Without Deleting Facts

In analytics, `fact_order` may still exist yet a flawed query filters it out:

~~~sql
-- Anti-pattern: historical stats counting only currently active customers.
SELECT f.month_key, SUM(f.booked_minor)
FROM analytics_fact_order f
JOIN analytics_dim_customer d
  ON d.customer_sk = f.customer_sk
WHERE d.is_active = TRUE
GROUP BY f.month_key;
~~~

When a customer closes their account, their facts **disappear from results** even though they remain in the warehouse. This query is valid only when the real question is "historical sales of currently active customers," never for "total booked sales in the period."

With SCD Type 2, multiple historical Customer dimension rows can contain PII. Processing PII on the current row **does not mean** historical versions are handled. Protections include:

- Keeping facts at transaction grain within permitted retention.
- Defining an `ERASED/UNKNOWN` dimension or nullable reference with a clear semantic contract; never merge distinct individuals into one real customer.
- Minimizing/removing PII fields from historical versions and read models per policy.
- Avoiding `ON DELETE CASCADE` from dimensions to facts holding valid records.
- Reconciling pre/post aggregates by currency, tenant, business time, and identical KPI definitions.

A surrogate key or hashed identifier can still link back to an individual; govern it appropriately.

## 20. Document, Graph, Event, and Time-Series Models Also Suffer Cascading Deletes

| Model | Typical pitfall | Design adjustment |
| --- | --- | --- |
| **Relational** | FK `CASCADE` deletes Order/Payment on Customer delete. | Separate ownership/lifecycle; RESTRICT / isolate PII. |
| **Document** | Embedding finalized invoices inside Customer document, then deleting whole doc. | Separate aggregates and evidence with distinct retention. |
| **Graph** | Deleting Customer node removes edges proving transactions/relationships. | Assign owners to nodes/edges; retain time-bounded history. |
| **Event store** | Deleting entire event stream to "close account," breaking replay. | Separate PII, set event retention, apply policy-based redaction/correction. |
| **Time-series** | Deleting Sensor metadata cascades measurements needed for incident investigation. | Separate current metadata from historical measurements. |
| **Warehouse** | Deleting dimension or INNER JOINing active rows hides past facts. | Retain valid historical facts; handle keys/PII separately. |
| **Cache/search** | Failing to apply delete events leaves PII visible. | Tombstones/versions, idempotency, reconciliation. |

In graphs, operations like `DETACH DELETE` remove all edges attached to a node, yet many edges represent **historically significant facts**. In documents, embedding `cart_items` inside `draft_cart` can fit because they share a lifecycle; embedding all paid invoices under `customer_profile` usually creates unwanted deletion coupling.

## 21. Partition Purging, Retention, and Backups Must Not Be Applied Mechanically

Time-based purging can use batches or partition drops, yet you cannot assume all data created on the same day shares the same deletion eligibility.

| Tool | Benefit | Risk |
| --- | --- | --- |
| DELETE by tenant/ID | Clear scope when filtered properly. | Cascades, locks, WAL bloat, write contention. |
| Retention-milestone purge | Automates lifecycle enforcement. | Wrong retention start date, unhandled legal holds. |
| Drop old partition | Efficient when all data shares one policy. | Accidentally drops disputed, late-arriving, or adjustable records. |
| Delete archive/backup | Reduces retained footprint. | Loses recovery capability or violates backup policy. |
| Delete projection | Shrinks derived storage. | Replaying old sources can regenerate erased fields. |

Measure row counts, storage size, locks, WAL, replica lag, and recovery time. A purge job lacking tenant scoping or checkpoints can cause widespread outages.

**Immutable backups:** may not support deleting a single row immediately; establish retention limits, access restrictions, restore runbooks, and mechanisms **preventing erased data from re-entering live systems**. Never claim "all copies have been deleted" without the ability to verify it.

## 22. Before/After Testing: Retained Records Must Not Disappear

Build a golden fixture for `CUS-42`: 3 signed contracts, 7 rental lines, 5 provider-confirmed payment movements, and 1 draft cart with 2 lines.

| Stage | Check | Expected outcome |
| --- | --- | --- |
| Before | Inventory FK cascades, ORM removals, triggers, and cleanup jobs. | No out-of-policy record deletion paths exist. |
| Before | Snapshot rental IDs, movement IDs, and totals by currency. | Baseline available for comparison. |
| During | Execute close/profile erasure under verified permissions. | No DELETE issued against RentalContract/PaymentMovement. |
| During | Retry same request and deliver old events. | No extra deletions / no PII resurrection. |
| After | Count retained contracts, rental lines, and movements. | Exact same counts and business keys. |
| After | Inspect profile source and downstreams. | PII handled per scope; clear status if pending elsewhere. |
| After | Compare CAPTURE/REFUND totals by currency/provider reference. | Unchanged by account closure. |
| After | Compare historical dashboards at the same grain. | No drop in figures from flawed active JOIN/filters. |
| After | Verify restore/replay policy. | No unauthorized restoration of erased data. |

Reconciliation example:

~~~sql
-- Count of contracts permitted to remain after profile handling.
SELECT COUNT(*) AS contracts_count
FROM demo_safe.rental_contract
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

-- Totals of confirmed movements by currency and type.
SELECT p.currency_code, p.movement_type,
       COUNT(*) AS movements_count,
       SUM(p.amount_minor) AS amount_minor
FROM demo_safe.payment_movement p
JOIN demo_safe.rental_contract c
  ON c.tenant_id = p.tenant_id
 AND c.rental_id = p.rental_id
WHERE c.tenant_id = :tenant_id
  AND c.customer_id = :customer_id
GROUP BY p.currency_code, p.movement_type;

-- Verifies only the private profile table in this database.
SELECT COUNT(*) AS private_profiles_remaining
FROM demo_safe.customer_private_profile
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

`private_profiles_remaining = 0` **does not** prove all copies were handled. Deletion results must be reconciled against the approved scope and relevant owners.

### An FK Error Can Be the Right Result

In a test environment where `RentalContract` still references the subject, running:

~~~sql
DELETE FROM demo_safe.customer_subject
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

**must be rejected** by `RESTRICT` under the assumed data scope. That is a **guardrail success**: the API must guide operators toward policy-compliant account closure/profile erasure rather than "fixing the error" by switching the FK back to CASCADE.

## 23. When Physical Deletion Is Genuinely Required: Do Not Turn History Retention into Infinite Retention

Cases that may require physical deletion:

1. Expired draft data with no independent obligations.
2. Personal data with no remaining processing purpose or mandated for deletion under approved policy.
3. Derived data that is no longer needed.
4. Transaction/record data past retention with no legal hold.
5. Erroneous records verified not to represent real business events, via proper workflow and audit.

Still distinguish:

- **Correction** of an occurred fact vs. deleting a record that was never real.
- **Transaction cancellation** vs. deleting a contract/receipt from history.
- Deleting the source profile vs. **deleting copies** or ending re-identifiability.
- Restoring accidentally deleted data vs. **resurrecting legitimately erased data**.

Never use `RESTRICT` as an excuse to reject every personal-data deletion request. When retention forbids keeping data, the model must support appropriate handling—including unlinking/data minimization or purging once eligible.

## 24. Practice Exercise: Closing a Ticket-Buyer Account While Retaining Records

**Scenario:** A ticketing platform has `Customer`, `Booking`, `BookingLine`, `PaymentMovement`, and `DraftCart`. One customer has 2 confirmed bookings, 4 ticket lines, 3 provider-confirmed movements, and 1 expired draft cart. FKs from Customer → Booking → BookingLine/PaymentMovement currently use `ON DELETE CASCADE`. Customer Identity receives a request to erase email/phone and close the account. Finance must continue reconciling movements within the approved retention window.

### Tasks

1. Draw the full FK graph, marking every cascade edge that risks record loss and counting at-risk records.
2. Define grain, business key, owner, and lifecycle for `Booking`, `BookingLine`, `PaymentMovement`, and `DraftCart`.
3. Distinguish `CloseCustomerAccount`, `CancelBooking`, `EraseCustomerPrivateProfile`, and `PurgeExpiredCart`.
4. Write the counter-example DDL with bad `CASCADE`; write the target DDL protecting records with `RESTRICT` or an appropriate design.
5. Explain when `SET NULL` can work, when a minimal subject/identifier must remain, and why PII risks still persist.
6. Identify all deletion paths across DB FKs, Hibernate `CascadeType.ALL`/`orphanRemoval`, triggers, and cleanup jobs.
7. Draft a migration plan updating FKs and APIs within a controlled window, avoiding any period where the old CASCADE still fires.
8. Write SQL counting `Booking`, `BookingLine`, and `PaymentMovement` before/after; confirm valid history does not shrink.
9. Given a 500,000 VND capture and 100,000 VND refund, explain why both movements stay and state the net cash formula.
10. Design a multi-service PII erasure workflow with outbox, tombstones, idempotency, waiting states, and reconciliation.
11. Explain why a warehouse `INNER JOIN` from `Booking` → active `Customer` can make historical revenue vanish.
12. Create a retention matrix covering disputed bookings, retention-expired bookings, draft carts, and immutable backups.
13. Simulate a failure: Customer service deletes the profile successfully, but Search misses the event; how should retries work?
14. Write an ADR stating the decision, rejected alternatives, invariants, data-access limits, tests, and re-evaluation criteria.

### Self-Check

| Criterion | Achieved outcome |
| --- | --- |
| **Lifecycle classification** | Referential FKs are not mistaken for cascading deletion rights. |
| **History protection** | Bookings/Movements stay while justified; not deleted on account closure. |
| **Accurate payments** | Captures/refunds are never deleted, and requests are never treated as confirmed. |
| **Scoped PII** | Clearly states which personal data is processed, where, and under what policy. |
| **Constraints** | PK/FK enforce tenant scope and block improper deletions. |
| **Operations** | Audits ORM, triggers, jobs, replication, backups, and outbox/replay. |
| **Reconciliation** | Business keys, counts, currency totals, and dashboard metrics are neither multiplied nor dropped. |
| **Recovery** | Runbook covers accidental deletion recovery and prevents resurrecting validly erased data. |

**Conclusion:** `ON DELETE CASCADE` is not inherently wrong; it is wrong when applied to **records or events whose lifecycle is independent of the parent account**. Sound design starts from grain, authoritative sources, business semantics, required history, and personal-data policies. Cascade true same-lifecycle drafts; protect confirmed contracts/movements with proper constraints and semantically accurate commands; process PII separately within a verifiable scope. Only with a full deletion graph, golden fixtures, and multi-source reconciliation can a system avoid "deleting one customer" while accidentally erasing facts that actually happened.
