# Soft Delete, Expiration Status, and History Retention Policies

## 1. The Problem: “No Longer Used” Does Not Mean “No Longer Exists”

In an equipment rental system, operators might say “delete old customer,” “close contract,” “expire price rate,” or “purge data after retention ends.” All four statements involve the data lifecycle, yet **cannot be collapsed into a single `DELETE` statement or an `is_deleted` flag**.

For example, a customer has account `CUS-108`, signed contract `RENT-204`, paid a deposit, and completed returning the equipment. Later, the customer requests closing their account:

- **The account can be deactivated** and blocked from logging in.
- **The contract has expired**, yet remains evidence of obligations that once existed.
- **The account profile can be soft-deleted** so it disappears from everyday operational screens.
- **Related data has different retention periods and legal bases**, so you cannot blindly delete every record immediately.
- **Once eligible**, certain data must be physically erased, anonymized, or archived per approved policy; soft delete does not accomplish those tasks.

In database design, separate **business status**, **effective time**, **visibility**, **change history**, and **retention lifecycle**. Separating them cleanly preserves key and constraint integrity, keeps temporal queries accurate, prevents hidden records from leaking, and ensures audits and personal-data handling rest on clear rules.

## 2. Concept Map: Six Distinct Operations

| Concept | Question Answered | Typical Data Action | Physical Record Deleted Immediately? |
| --- | --- | --- | --- |
| **Disable / suspend** | Is the entity allowed to perform actions anymore? | Set `account_status` to `DISABLED`, record reason. | No. |
| **Business expiration (expire/end)** | Does the entitlement/contract/rate still apply at time T? | Set `valid_to` or `effective_to`, transition status to `ENDED`. | No. |
| **Soft delete** | Should the record appear in normal operational views? | Populate `deleted_at` and deletion metadata. | No. |
| **Cold archive** | Can the record move off hot read paths while remaining retained per policy? | Move data to archive storage with metadata and access controls. | Hot copy may be removed after verification, yet data remains in archive. |
| **Physical purge / erasure / anonymization** | When and how do we end retention of identifying data? | Delete records, files, derived copies, or apply controlled irreversible transformation. | Depends on mechanism; distinguish erasure from true anonymization. |
| **History / temporal record** | What value did the entity hold previously, when, and since when did the system know? | Temporal version table, audit trail, event log, or bitemporal model. | Not by default; history is also subject to retention. |

`is_deleted = true` does not tell when the record was hidden, why, or when it must be purged. A column `status = INACTIVE` does not reveal the actual effective period of a contract. Conversely, `valid_to < now()` does not prove a user requested erasing their profile from the system.

**Ask these design questions separately:**

1. **Expiration:** after date X, can the entity still create new obligations?
2. **Hiding from everyday operations:** who may read, edit, or restore the entity?
3. **Retaining history:** which data must be kept to prove which decisions?
4. **Ending retention:** when and under what conditions is data erased or anonymized?
5. **Recovery from error or undo requests:** what content may be restored and within what window?

## 3. Modeling State Across Independent Dimensions

Designs are far easier to reason about when you do not cram every state into one enum.

For example, a customer account can carry:

- `account_status`: `ACTIVE`, `SUSPENDED`, or `CLOSED` — business usability of the account.
- `deleted_at`: timestamp when the account was soft-deleted to hide it from normal flows.
- `retention_review_at` or linked retention policy: milestone to evaluate purge vs. retention.
- `legal_hold` or a separate hold record: whether purging is suspended under authorized process.

A rental contract has different dimensions:

- `rental_status`: `DRAFT`, `ACTIVE`, `RETURNED`, `ENDED`, `CANCELLED`.
- `effective_from` and `effective_to`: period during which the contract is effective.
- `archived_at`: when moved off hot processing paths if archived.
- Term adjustment history: multiple versions of pricing/return deadlines with separate effective intervals.

A completely valid state is **contract `ENDED`, customer `ACTIVE`, contract `archived_at` set, yet purge forbidden because it remains within document retention**. Forcing all of that into a single `status` column makes many states awkward or impossible to represent.

### State Transitions Require Policy

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Suspended: Temporarily lock
    Suspended --> Active: Restore access
    Active --> Closed: Close account
    Suspended --> Closed: Close account
    Closed --> SoftDeleted: Valid soft delete
    SoftDeleted --> Closed: Restore if allowed
    SoftDeleted --> Purged: Eligible for purge
    Purged --> [*]
~~~

This diagram is **one example**, not a mandatory workflow for every system. Never allow `Purged -> Active` as a routine transition: physically erased data cannot simply be “re-enabled” from the same deleted row. If a valid backup recovery or re-registration occurs, it is a controlled workflow with its own identity and obligations.

### Invariants to State Explicitly

- Accounts with `deleted_at IS NOT NULL` cannot be used for standard login.
- `ENDED` contracts stop accruing new rental charges unless explicitly defined post-term rules apply.
- An effective price at time T must resolve to **one** valid term version within constraint scope.
- While retention has not expired or an active hold exists, purging must be blocked.
- Soft-deleting an account **must not drop** required financial records or break referential integrity.

## 4. Designing Soft Delete: Timestamps, Keys, and Query Behavior

The simplest pattern adds `deleted_at TIMESTAMPTZ NULL`. `NULL` means not soft-deleted; a timestamp records when it was hidden.

An illustrative PostgreSQL schema:

~~~sql
CREATE TABLE customer_account (
    tenant_id       UUID NOT NULL,
    account_id      UUID NOT NULL,
    login_email     TEXT NOT NULL,
    account_status  VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    deleted_at      TIMESTAMPTZ,
    deletion_reason VARCHAR(80),
    deleted_by      UUID,
    version         BIGINT NOT NULL DEFAULT 0
                    CHECK (version >= 0),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, account_id),
    CHECK (
        account_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')
    ),
    CHECK (
        deleted_at IS NOT NULL OR
        (deletion_reason IS NULL AND deleted_by IS NULL)
    )
);
~~~

This is a teaching schema: production systems must handle email normalization, actor authorization, tenant isolation, personal-data categories, and account verification rules. Never assume `deleted_by` is always a human user: the actor may be an automated job or admin workflow, requiring an appropriate actor identifier and actor type.

### Identifiers Must Never Be Reused

`account_id` is a durable identifier. When an account is soft-deleted, never reuse that ID for someone else: old contracts, transactions, and audits may still reference that ID. In multi-tenant systems, `(tenant_id, account_id)` preserves strict isolation.

### Unique Keys for “Live” Records

Suppose each tenant allows at most **one non-soft-deleted account** per normalized email:

~~~sql
CREATE UNIQUE INDEX ux_customer_live_email
    ON customer_account (tenant_id, lower(login_email))
    WHERE deleted_at IS NULL;
~~~

This partial index lets an email appear on a soft-deleted record and another active record. That is just **one product policy choice**:

- If the email must stay reserved during a recovery window, uniqueness rules may need to be stricter or backed by a username/email reservation table.
- If an old account is restored after someone else registered that email, restoration must **be blocked or go through conflict resolution**—never hijack the new account's email.
- If normalized emails must be unique globally rather than per tenant, adjust the key accordingly and standardize Unicode/email canonicalization rules.
- A unique index on `lower(login_email)` does not automatically cover every email canonicalization rule. Use a consistent normalization function/strategy on both writes and lookups.

### Default Queries Must Filter Consistently

~~~sql
SELECT account_id, login_email, account_status
FROM customer_account
WHERE tenant_id = :tenant_id
  AND deleted_at IS NULL
  AND account_status = 'ACTIVE';
~~~

Ensure every code path—list APIs, search, autocomplete, exports, reports, background jobs, and joins—applies visibility policies. **A soft-deleted row still lives in the database and can leak** through any query that forgets the predicate.

You can define a business view:

~~~sql
CREATE VIEW customer_account_live AS
SELECT tenant_id, account_id, login_email, account_status,
       version, created_at, updated_at
FROM customer_account
WHERE deleted_at IS NULL;
~~~

A view standardizes read paths, yet **is not a security boundary** if the application role still has direct `SELECT` access to the underlying table. For real isolation, combine database privileges, API guards, row-level security where appropriate, and tenant access tests.

## 5. Soft Delete in Transactions, Deduplication, and Restoration

Soft delete is more than `UPDATE deleted_at = now()`. Before hiding data, validate permissions, state, open obligations, and downstream notifications.

Example optimistic-versioned update:

~~~sql
UPDATE customer_account
SET account_status = 'CLOSED',
    deleted_at = now(),
    deletion_reason = :reason_code,
    deleted_by = :actor_id,
    version = version + 1,
    updated_at = now()
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND deleted_at IS NULL
  AND version = :expected_version
RETURNING account_id, version, deleted_at;
~~~

If zero rows return, the account may already be soft-deleted, the version may have changed, or the account does not exist in that tenant. **Never blindly treat zero rows as success**: use a command ID or `idempotency_key` to distinguish a retry of an already-completed request from a competing request.

A complete workflow should:

1. Verify actor and authorization; if financial/contractual data exists, decide which fields are merely **hidden** vs. which must be **retained**.
2. Lock/update conditionally on version; write audit/correction records if required.
3. In the same transaction, write an **outbox** record if downstream systems must be notified of visibility or account status changes.
4. Commit; only afterward does the relay publish the message. Consumers must handle retries idempotently.
5. Schedule retention/purge evaluation separately—never confuse soft delete with completed erasure.

**Restoration** must verify: is it still inside the allowed restore window, which business status should be restored, do unique keys collide, must the account re-verify contact info, and was any dependent data already physically purged and unrecoverable?

~~~sql
UPDATE customer_account
SET deleted_at = NULL,
    deletion_reason = NULL,
    deleted_by = NULL,
    account_status = 'SUSPENDED',
    version = version + 1,
    updated_at = now()
WHERE tenant_id = :tenant_id
  AND account_id = :account_id
  AND deleted_at IS NOT NULL
  AND version = :expected_version
RETURNING account_id, version;
~~~

This restore example sets `SUSPENDED` to require re-verification before restoring full access. If the email unique index collides, the transaction fails; the application must resolve duplicate-account policy rather than dropping the constraint.

## 6. Interval-Based Expiration: Distinct from Soft Delete

For pricing, contracts, entitlements, or terms, the usual question is:

> Which record **was effective at time T**?

This is **valid time** (business effective time), distinct from whether a record is visible in the UI. Represent effective intervals as **half-open** `[valid_from, valid_to)`: inclusive start, exclusive end.

Example rental rate history for the same equipment:

| Version | valid_from | valid_to | Daily Rate |
| --- | --- | --- | ---: |
| P1 | 2026-01-01 00:00 UTC | 2026-04-01 00:00 UTC | 70,000 VND |
| P2 | 2026-04-01 00:00 UTC | 2026-09-01 00:00 UTC | 80,000 VND |
| P3 | 2026-09-01 00:00 UTC | Unbounded | 85,000 VND |

At exact instant `2026-04-01 00:00 UTC`, P2 is effective and P1 is no longer active. Using `[)` prevents two versions from both matching at the boundary.

### Versioned Table Model

~~~sql
CREATE TABLE rental_agreement (
    tenant_id       UUID NOT NULL,
    agreement_id    UUID NOT NULL,
    account_id      UUID NOT NULL,
    agreement_status VARCHAR(20) NOT NULL,
    effective_from  TIMESTAMPTZ NOT NULL,
    effective_to    TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    version         BIGINT NOT NULL DEFAULT 0
                    CHECK (version >= 0),
    PRIMARY KEY (tenant_id, agreement_id),
    FOREIGN KEY (tenant_id, account_id)
        REFERENCES customer_account (tenant_id, account_id),
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    CHECK (agreement_status IN
           ('DRAFT', 'ACTIVE', 'RETURNED', 'ENDED', 'CANCELLED'))
);

CREATE INDEX ix_rental_active_by_tenant
    ON rental_agreement
       (tenant_id, agreement_status, effective_from)
    WHERE deleted_at IS NULL;
~~~

Here `effective_to` marks when the **contract** expires; it does not mean the contract may be purged. Likewise, `archived_at` does not mean data was deleted. Depending on domain rules, a contract may expire by clock time even before a job flips `agreement_status` to `ENDED`; explicitly define whether **validity authority** is the time interval, computed status, or both under specific rules.

Querying agreements effective at `:as_of`:

~~~sql
SELECT tenant_id, agreement_id, account_id, agreement_status
FROM rental_agreement
WHERE tenant_id = :tenant_id
  AND effective_from <= :as_of
  AND (effective_to IS NULL OR :as_of < effective_to)
  AND deleted_at IS NULL;
~~~

This queries **the current operational view of visible data** and effective intervals. If an authorized investigation needs soft-deleted agreements, replace `deleted_at IS NULL` under a separate historical-access policy. Never claim omitting the soft-delete filter in every “as-of” query is always right or always wrong: define the read purpose explicitly.

### Keeping Multiple Term Versions Without Overwriting History

When prices change, running `UPDATE current_price` erases which price applied on past signing dates. A term version table preserves effective intervals:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE rental_term_version (
    tenant_id        UUID NOT NULL,
    agreement_id     UUID NOT NULL,
    term_version_id  UUID NOT NULL,
    valid_from       TIMESTAMPTZ NOT NULL,
    valid_to         TIMESTAMPTZ,
    daily_fee_minor  BIGINT NOT NULL CHECK (daily_fee_minor >= 0),
    currency         CHAR(3) NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    voided_at        TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, term_version_id),
    FOREIGN KEY (tenant_id, agreement_id)
        REFERENCES rental_agreement (tenant_id, agreement_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    EXCLUDE USING gist (
        tenant_id WITH =,
        agreement_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    ) WHERE (voided_at IS NULL)
);
~~~

The `EXCLUDE ... WITH &&` constraint prevents two **non-voided** versions of the same contract from having overlapping effective intervals. `btree_gist` enables equality checks on scalar keys inside the GiST index; enabling extensions requires appropriate DB privileges and setup.

**Important limitation:** `voided_at` is a technique to exclude a version from the authoritative set; updating it mutates current knowledge. If you must prove exactly “which version did the system know on date X?”, use **recorded-time history** or controlled bitemporal modeling rather than relying on this table alone and assuming all changes are immutable.

## 7. Valid Time, Recording Time, and History Queries

Two time axes are commonly involved:

- **Valid time:** during which interval is the data considered effective in the business domain?
- **Transaction/system time:** during which interval did the system store/know that version?

Suppose a contract term originally recorded return deadline 10:00. At 12:00, staff submits documentation that an extension to 11:00 had been approved the day before. The system may need to answer:

1. **At 11:30, what did the system believe?** The recorded deadline then was 10:00.
2. **Per new evidence, what was the valid deadline at 11:30?** The recognized deadline is 11:00.

The two questions do not conflict; they ask about two different time dimensions.

A bitemporal model retains `valid_from/valid_to` and `recorded_from/recorded_to` (or equivalent metadata). On a correction, it **closes the old recording interval and inserts a new version**, never pretending the system always knew the new value. Temporal queries must filter both axes using half-open bounds:

~~~sql
-- SQL pseudocode for a temporal_version table with four timestamps.
SELECT *
FROM temporal_version
WHERE entity_id = :entity_id
  AND valid_from <= :business_at
  AND (valid_to IS NULL OR :business_at < valid_to)
  AND recorded_from <= :known_at
  AND (recorded_to IS NULL OR :known_at < recorded_to);
~~~

This illustrates a model **assuming a dedicated `temporal_version` table**, not a query against the earlier tables in section 6. For bitemporal data to remain accurate, enforce version boundaries, write transactions, and non-overlap constraints across both valid-time and recorded-time semantics.

**Never use `updated_at` alone to simulate history.** The latest update timestamp cannot tell what prior states were; likewise, `deleted_at` never proves when a business fact took effect or expired.

### Time Zones and Time Boundaries

Store event instants as `TIMESTAMPTZ` (absolute instants) when needed; apply business time zones when displaying or mapping to calendar dates. Never assume “April 1” maps to the same UTC hour across all tenants. For deadlines expressed in local calendar days, store the time zone/calendar policy explicitly and define how DST transitions are resolved.

A record expires when `valid_to <= :as_of` under `[)`. This differs from a scheduled job updating `status = 'EXPIRED'`: jobs can lag, so time-rule queries must not depend solely on when a batch job ran when exact hourly/minute accuracy is required.

## 8. History Retention Policies: Each Data Category Has Its Own Basis and Clock

A **retention policy** specifies **which data must/may be kept, for how long, starting from which trigger, who approved it, and what happens upon expiry**. Never apply one blanket number across every table just because they relate to the same customer.

A policy specification should capture at least:

| Attribute | Question |
| --- | --- |
| **Data category** | Which group: account profile, contracts, transactions, audits, access logs, attachments? |
| **Purpose/legal basis** | Why keep it, and what justifies that duration? |
| **Trigger** | Does the clock start at record creation, contract close, settlement, service termination, or another event? |
| **Retention rule** | Mandatory/maximum duration, exceptions, and applicable date/time calculation rules. |
| **Action at expiry** | Purge, anonymize, aggregate, archive, or manual review? |
| **Hold/exception** | When is purging paused, and who owns periodic review? |
| **Coverage** | Primary DB, derived tables, attachments, search indexes, caches, audits, backups, partners? |
| **Evidence** | What minimal evidence proves the policy was executed? |
| **Policy version** | Which approved policy version applied when computing expiry, and why it changed. |

Example classification (durations are **parameters taken from actual policy**, not hardcoded legal defaults):

| Data Category | Possible Clock Trigger | Action When Eligible |
| --- | --- | --- |
| Account profile no longer needed | Close/delete request verified and linked obligations classified. | Erase/anonymize permitted personal attributes. |
| Rental contracts and documents | Contract end date or dispute resolution per applicable rules. | Archive/purge under approved document policy. |
| Payment transactions / ledger | Settlement date or retention milestone for accounting obligations. | Retain or process on its own clock; never delete blindly with account. |
| Technical access logs | Log creation time. | Rolling purge after considering security/investigation needs. |
| Read models and search indexes | Depends on purpose and source data. | Sync hide/delete and rebuild cleanly. |
| System backups / snapshots | Backup time and backup rotation policy. | Rotate out per schedule; handle restores from older backups to prevent re-exposing erased data. |

**Never invent “7 years,” “90 days,” or similar cutoffs and treat them as universal legal mandates.** Exact durations depend on data category, jurisdiction, contracts, user rights, and organizational policy. Obtain confirmation from legal/compliance owners before implementing in production.

### Expiry Milestone vs. Execution Time Are Distinct

- `retention_until`: **earliest eligible or mandatory review instant** for end-of-lifecycle action per policy; document exact meaning.
- `purge_scheduled_at`: when the job is scheduled to run.
- `purged_at`: when a task confirmed completion across the defined data scope.
- `hold_until` or hold status: authorized exception; may lack a predetermined end date and require periodic review.

Never overload one `deleted_at` column for all four meanings. Once data is physically erased, you cannot update `purged_at` **on the deleted row itself**; store minimal execution records or tombstones separately per policy.

## 9. Designing Purge Jobs: Decision, Execution, and Evidence

A responsible purge workflow does not simply execute:

~~~sql
DELETE FROM customer_account
WHERE deleted_at IS NOT NULL;
~~~

That statement ignores retention windows, open contracts, downstream stores, legal holds, and authorization. Instead, coordinate erase/anonymize tasks with a dedicated tracking table:

~~~sql
CREATE TABLE data_retention_action (
    action_id          UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    subject_ref        VARCHAR(120) NOT NULL,
    data_category      VARCHAR(80) NOT NULL,
    policy_version     VARCHAR(60) NOT NULL,
    eligible_at        TIMESTAMPTZ NOT NULL,
    action_type        VARCHAR(24) NOT NULL
                       CHECK (action_type IN ('ERASE', 'ANONYMIZE', 'ARCHIVE')),
    action_status      VARCHAR(24) NOT NULL
                       CHECK (action_status IN
                          ('PENDING', 'BLOCKED', 'RUNNING',
                           'COMPLETED', 'FAILED')),
    completed_at       TIMESTAMPTZ,
    last_error_code    VARCHAR(80),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_retention_due
    ON data_retention_action (eligible_at, action_id)
    WHERE action_status IN ('PENDING', 'FAILED');
~~~

This is **coordination metadata**; `subject_ref` should be a minimal reference compliant with access and evidence policies—not a place copying personal data. `COMPLETED` must have a defined scope: source DB only, derived projections too, or partner confirmations as well? Never mark deletion complete while downstream stores remain pending.

### A Safe Purge Workflow

~~~mermaid
flowchart TD
    A["Record soft-deleted/closed"] --> B["Evaluate eligibility per policy version"]
    B --> C{"Retention expired and no hold?"}
    C -->|"No"| D["Retain, re-evaluate at next milestone"]
    C -->|"Yes"| E["Lock/reconcile data and obligations"]
    E --> F["Erase/anonymize at source per scope"]
    F --> G["Notify read models, search, files, cache"]
    G --> H{"All steps confirmed?"}
    H -->|"No"| I["Retry/reconcile, keep incomplete status"]
    H -->|"Yes"| J["Record minimal evidence and close action"]
~~~

Steps must be **idempotent**, because jobs may retry after timeouts. Physical erasure rarely fits inside one atomic transaction across databases, object storage, search indexes, and third parties. Track per-step status, re-verification, strict privileges, and reconciliation rather than assuming one successful SQL `DELETE` cleaned everything.

**Holds must be re-checked right before irreversible execution**, not merely when the job was first queued. If a hold is placed after queuing, the worker must honor it. Locking or policy-version checks prevent races between “place hold” and “purge.”

### Evidence Must Not Become a Copy of Deleted Data

Completion logs can record action ID, timestamp, policy version, system scope, outcome, and error code. Never copy emails, government IDs, or deleted payloads into deletion-proof logs. Even hashes or identifiers can re-identify subjects when combined with other datasets; evaluate necessity and retention for the proof log itself.

## 10. Foreign Keys, Dependent Relationships, and “Cascading Deletes”

A common mistake is enabling `ON DELETE CASCADE` and physically deleting an account—wiping out contracts, invoices, and payment history. That destroys financial documents, accounting links, and reconciliation capability.

### Soft Delete Does Not Trigger FK Cascades

Updating `deleted_at` leaves the row intact, so foreign keys do nothing. Consequently:

- Contract rows still reference a valid customer key.
- Never assume contracts automatically become hidden in UIs; apply visibility policies consistently across queries and domain logic.
- Keeping contracts does not justify keeping all personal profile attributes forever.
- When the account row is eventually purged, foreign keys from contracts will **block DELETE** unless the schema handles preserved references or policy-compliant relationship cleanup.

### Three Strategies for Dependent Data

| Strategy | When Appropriate | Notes |
| --- | --- | --- |
| **Keep surrogate ID, anonymize attributes** | Transactions/contracts must stay while full identity is no longer needed. | Assess re-identification risk across tables and policy permissibility. |
| **Separate identity vault and business records** | Identity lifecycle differs from obligation lifecycle. | Decouple reference keys and access controls; maintain dedicated identity erasure workflow. |
| **Controlled deletion of entire dependent graph** | All records in the group are permitted and required to be deleted. | Define order, local transactions, file/search/backup handling, and audit proof. |

`SET NULL` on a foreign key fits only when the link can genuinely be absent without breaking business meaning. Never null out `account_id` on transactions just to make `DELETE` succeed when reconciliation requires stable customer grouping.

### Why Keys Must Never Be Reused

If an account was purged while historical transactions still hold its surrogate ID for reconciliation, **never reassign that ID to a new user**. Reusing IDs makes old contracts appear to belong to someone else. Even after PII erasure, minimal identity/tombstone tracking may be needed to guarantee non-reuse per policy.

## 11. Queries, Indexes, and Performance as Old Data Accumulates

Soft delete puts both active and hidden rows in the same table. As hidden rows grow, queries and indexes must match real workloads.

### Indexes for Hot Read Paths

~~~sql
CREATE INDEX ix_customer_active
    ON customer_account (tenant_id, account_status, account_id)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_customer_deleted
    ON customer_account (tenant_id, deleted_at)
    WHERE deleted_at IS NOT NULL;
~~~

The first index optimizes queries for live customers; the second helps retention jobs scan soft-deleted rows. Still, **never add indexes blindly** to production: measure data skew, selectivity, query predicates, execution plans, and write overhead. A partial index is only chosen by the planner when query predicates prove implication of the index predicate; verify parameterized queries with `EXPLAIN (ANALYZE, BUFFERS)` in a realistic environment.

### How Should Historical Data Be Separated?

Several options exist:

- **Same table + `deleted_at`:** simple and supports restoration; works well while volume and access controls stay manageable.
- **Dedicated history/archive table:** shrinks hot read paths, at the cost of data movement, key management, schema sync, and cross-table lookups.
- **Time-based partitioning:** fits large datasets with time-scoped queries and retention drops; verify unique/FK constraints and actual partition pruning.
- **Cold archive / object storage:** fits infrequently queried, high-retention records; verify integrity, access control, lookup ability, and expiry erasure.

Moving data to an archive **does not eliminate obligations** for retention management, access control, or valid erasure requests. Copies in search indexes, caches, or exports can continue exposing data even after the primary row is hidden.

### Document, Graph, and Analytical Models

In document stores, include `deleted_at` or `lifecycle_status` in all relevant queries and indexes; TTL mechanisms physically expire documents, yet **do not replace policy evaluation and downstream cleanup**. In graphs, deactivating a node must account for connected edges: hiding a node while leaving edges readable can still leak identities. In analytical warehouses, define clear policies for facts, dimensions, snapshots, and aggregates once source data is erased or anonymized.

## 12. Synchronizing Soft Delete and Expiration to Other Systems

Running `UPDATE customer_account SET deleted_at = now()` mutates only the local source. Downstream search, CRM, or caches will keep surfacing the account unless they receive and apply the change accurately.

Distinguish message semantics:

- **AccountDisabled:** account may no longer act; data may remain visible to authorized staff.
- **AccountSoftDeleted:** entity hidden from routine business views, not necessarily physically erased.
- **AgreementExpired / AgreementEnded:** contract validity ended under business rules.
- **AccountErasureCompleted:** publish only once defined erasure scope is confirmed; never emit success while downstream stores remain uncleaned.
- **CDC UPDATE:** database log recorded a change to `deleted_at`; that is a storage event, not full privacy/retention semantics on its own.

A transactional outbox writes inside the same transaction as the source state update:

~~~sql
CREATE TABLE lifecycle_outbox (
    message_id       UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_id     UUID NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at     TIMESTAMPTZ
);
~~~

Relays can redeliver messages on retry. Consumers need deduplication keys (such as `message_id` + source) and version/ordering rules so a late-arriving stale status message never **resurrects a soft-deleted record**. For cross-system erasure, also require per-scope execution confirmation or reconciliation rather than trusting “message published.”

**Avoid stuffing raw emails or phone numbers into “delete this user” messages** when agreed opaque IDs and trusted channels work. A deletion message carrying full PII becomes yet another hard-to-control PII copy.

## 13. Privacy, Security, Compliance, and Backups

Soft delete **is not personal-data erasure**. Data persists in source rows, backups, logs, projections, search indexes, and potentially third-party systems. Review deletion and retention scope with legal and privacy stakeholders.

### Key Points to Confirm

1. **Purpose and retention basis:** which data is no longer needed, and which carries independent retention obligations?
2. **Minimization:** retain only necessary attributes; contracts/transactions can hold surrogate IDs without duplicating emails everywhere.
3. **Authorization:** restrict soft-deleted record access strictly to authorized roles; audit access to those records separately.
4. **Retention:** when is data archived, anonymized, or purged? Re-evaluate when policies change.
5. **Backups:** erased data can linger inside unexpired backups. Maintain backup security policies and workflows ensuring restores **never reactivate erased data**.
6. **Immutable stores:** append-only events, audits, and WORM storage can conflict with erasure mandates; design PII decoupling, access control, retention, and approved exception handling.
7. **Execution proof:** maintain deletion logs without turning them into a new PII store.

**Anonymization and pseudonymization differ:** replacing a name with `account_id` is usually only **pseudonymization**, since records can still be linked and re-identified via auxiliary data. Never label data “anonymous” just because an email column was cleared. Cryptographic shredding (destroying encryption keys) is sometimes proposed to block access, yet requires evaluating key backups, shared keys, irreversibility, and legal compliance—never assume key destruction automatically satisfies every erasure mandate.

### Restoring from Backup

Suppose an account is erased on Monday following approved workflows. On Wednesday, operations restores Sunday's backup. The backup still contains the erased account. Maintain an **erasure replay list/process** applied safely to restored environments within policy scope and retention rules. Test restores periodically to verify erased data neither reappears in UIs nor leaks to downstream consumers.

## 14. Choosing Complexity Based on Real Needs

Not every entity needs soft delete, valid-time versioning, and bitemporal history all at once. Pick the minimal complexity that satisfies requirements:

| Problem | Starting Approach | When to Expand |
| --- | --- | --- |
| Discontinued equipment catalog items | `status = INACTIVE`, store timestamp and reason. | Add version/valid-time if past catalog states must be queried. |
| Customer requests hiding/deleting account | Soft delete with retention/erasure workflow. | Decouple identity from business records and add audit/holds when document retention applies. |
| Contract with start/end dates | `effective_from/to`, contract status. | Add effective-interval history table when terms have multiple versions. |
| Quoted rates amended retroactively | Valid-time + recorded-time (bitemporal or equivalent history). | Whenever querying both “what did system know?” and “what applied when?” is required. |
| High-volume technical logs | Partition/TTL per approved policy. | Add holds, deletion tracing, archive, or multi-store workflows when mandated. |
| Reconcilable financial transactions | Ledger/history with clear source and dedicated retention. | Add historical projections, corrections, and cross-service reconciliation as needed. |

**Choose per bounded context** rather than slapping `is_deleted` onto every table because an ORM offers it. For example, `OrderCancelled` is a business event, not necessarily a “soft delete” of the order. Likewise, “expiring a price list” does not mean “deleting invoices that used that price list.”

### Design Decision Matrix

Before implementation, answer clearly:

- Can the entity *pause* and resume, or is the terminal state permanent?
- Does “delete” mean UI hiding, blocking processing, physical purge, or formal erasure?
- Which histories are needed: before/after edits, business milestones, effective intervals, or full bitemporal?
- Under which time zones and definitions must as-of queries operate?
- Can unique keys be reused after soft delete, and how do restores resolve collisions?
- Which dependent records must survive, and how should foreign keys be structured?
- Who can place legal holds, and how are holds verified right before purging?
- Which downstream replicas must hide or erase alongside source records?
- Which policy governs retention, what triggers the clock, and how do policy updates affect existing rows?
- What is the plan for testing, monitoring, backup/restore, and partial mid-workflow failures?

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `is_deleted` for expiration, hiding, and erasure | Cannot distinguish obligations or actual actions. | Separate business status, effective bounds, soft delete, and retention actions. |
| Treating soft delete as sufficient for data erasure | PII remains across multiple stores. | Full erasure pipeline covering downstream stores and backups. |
| Treating `updated_at` as history | Loses prior values and change reasons. | Use audits, version tables, events, or bitemporal per need. |
| Purging immediately when `valid_to <= now()` | Destroys documents still under retention obligations. | Separate business validity from retention policies and holds. |
| Filtering `deleted_at` in only one API | Other read paths leak hidden records. | Centralize read policies, access control, and full test coverage. |
| Restoring without checking unique keys | Email/identifier collides with newer users. | Conditional transactional restore with explicit conflict handling. |
| Applying `ON DELETE CASCADE` everywhere | Accidentally wipes out invoices, audits, or evidence. | Classify dependencies; keep surrogate IDs or decouple identity per policy. |
| Ignoring race conditions between legal holds and purges | Erases data just placed on hold. | Re-check holds right before commit using locks or policy versioning. |
| Expiring via `status` alone without timestamps | Cannot query which version applied at T. | Store valid-time bounds and interval constraints. |
| Allowing overlapping effective price intervals | As-of queries return multiple prices. | Enforce exclusion constraints or equivalent transactional rules. |
| Using `recorded_at` instead of `effective_at` | Wrong effective dates under retroactive edits. | Model both time axes when required. |
| Deleting source rows while skipping search/cache | Hidden data remains searchable. | Lifecycle events, idempotent consumers, completion reconciliation. |
| Restoring backups without reapplying erasures | Violates erasure intent and leaks data. | Reapply recorded erasure decisions during restore workflows. |
| Hardcoding arbitrary retention periods without basis | Deletes too early or retains too long. | Policy-driven rules per category, trigger, approver, and version. |
| Proving deletion by copying full PII into logs | Creates a new sensitive data store. | Minimal confirmation records with clear retention and access control. |

## 16. Practice Exercise: One System with Three Data Lifecycles

**Context:** an equipment rental platform has three data groups:

1. **Accounts:** customers register by email; accounts can be suspended, closed, and requested for personal-data erasure.
2. **Contracts:** effective over an interval, renewable or terminable; payment documents must be retained under a separate policy.
3. **Price schedules:** rates change by date, occasionally with retroactive corrections after data-entry errors.

The platform runs PostgreSQL, a search engine, a cache, object storage for signed forms, and a reporting warehouse. Select staff need historical access to resolve disputes.

### Design Tasks

1. **Separate semantics:** for each group, state when to use `status`, `deleted_at`, `valid_from/to`, `recorded_from/to`, and purge policies. Explain why one shared flag fails.
2. **Design keys:** specify primary keys for accounts, contracts, and price versions plus foreign keys; explain why account IDs must never be reused.
3. **Uniqueness and restore:** a soft-deleted email is re-registered by someone else; later, the original owner requests restoration. Define constraints and conflict handling.
4. **As-of:** price P1 applies until 00:00 on Apr 1, and P2 starts at that exact instant. Write the SQL predicate so 00:00 selects only P2.
5. **Bitemporal:** on Apr 10, staff retroactively amends a price effective Apr 1. Answer separately: “on Apr 5, which price did the system know?” and “currently, which price is recognized as effective on Apr 5?”
6. **Retention:** draft policy specs for account profiles, contracts, transactions, and access logs, naming triggers and expiry actions—without inventing statutory durations.
7. **Holds:** a purge action is queued, but before execution a dispute hold arrives. Describe how the worker avoids accidental erasure.
8. **Cross-system erasure:** list steps across DB, search, cache, files, reports, and backups; distinguish `PENDING`, `BLOCKED`, and `COMPLETED`.
9. **Concurrency tests:** two delete/restore or email-change requests arrive simultaneously. Detail versioning, transactions, and idempotency.
10. **Security tests:** prove regular APIs hide soft-deleted accounts; investigation APIs restrict access to authorized roles; tenant A cannot read tenant B's accounts.
11. **Backup restore:** simulate restoring a backup containing an erased account; describe how to prevent re-exposure.
12. **ADR:** choose the minimal implementation for each group and state what triggers expanding to bitemporal or cold archives.

### Self-Assessment Checklist

| Check | Passing Indicator |
| --- | --- |
| **Lifecycle semantics** | Never confuses expiration with soft delete, archiving, or erasure. |
| **Historical queries** | As-of uses half-open intervals accurately; bitemporal separates valid-time and recorded-time when needed. |
| **Constraints** | PK/FK/unique/exclusion align with business boundaries, including restore collisions. |
| **Consistency** | State transitions use proper transactions, optimistic locking, and idempotency. |
| **Retention** | Triggers, policy versions, exceptions, and holds are explicit; never purges solely because status expired. |
| **Dependent data** | Never wipes out transactions/documents via careless cascades. |
| **PII protection** | Soft delete is never treated as erasure; downstream stores, backups, and proof logs are controlled. |
| **Recovery and verification** | Processing decisions are auditable, retries stay drift-free, and cross-system outcomes reconcile cleanly. |

**Conclusion:** soft delete is merely a mechanism for **hiding records and managing recoverability**; expiration is a rule defining **when business values apply**; retention policies govern **what must be kept, on what basis, and how data ends its lifecycle**. Sound design separates these dimensions from the requirements stage, applies proper keys, constraints, and temporal tables, and controls cross-system access and erasure—both answering historical questions accurately and protecting data under real obligations.
