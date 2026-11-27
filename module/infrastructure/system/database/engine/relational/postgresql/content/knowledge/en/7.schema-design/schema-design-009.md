# Soft Delete, Data Lifecycle, and Retention Policies in PostgreSQL

In real-world applications, "deleting" does not always mean immediately removing a row from the database. A customer may close an account while past orders must still be reconciled. A post may sit in a trash bin for 30 days before permanent removal. An employee record may be retained under internal policy while remaining hidden from active staff lists.

Therefore, when designing a PostgreSQL schema, distinguish **soft delete**, **hard delete**, **data lifecycle states**, and **retention policies**:

- **Soft delete:** marks a record as no longer active or visible while the row remains in PostgreSQL.
- **Hard delete:** runs `DELETE` to remove rows under PostgreSQL's transaction and constraint semantics; storage space is not necessarily reclaimed immediately.
- **Long-term or cold archiving:** moves or classifies infrequently used data; not equivalent to erasing data.
- **Retention policy:** defines which data must be kept, from what anchor event, for how long, when deletion is permitted, who approves it, and how execution is verified.
- **Legal hold / preservation hold:** mandates retaining data within a defined scope despite normal purge schedules when a valid legal or policy directive applies.

PostgreSQL provides SQL, transactions, constraints, indexes, partitioning, roles, and operational tools to implement these rules. However, **PostgreSQL does not decide which business data must be kept or for how long**. Policies must come from the organization's application, legal, and operational requirements.

This lesson builds a practical design: customer and order tables, a `deleted_at` column, partial unique indexes, safe delete/restore operations, foreign-key checks, purge eligibility rules, and batched purge jobs. Durations such as 30 or 90 days are **technical examples**, not mandatory deadlines for any specific industry or jurisdiction.

## 1. Why Not Always Run DELETE Immediately?

Suppose an application has a customer table:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL
);
~~~

A physical deletion:

~~~sql
DELETE FROM customer
WHERE customer_id = 101;
~~~

Once committed, the row disappears from ordinary `SELECT` results. This works well when data does not need retention and dependent relationships have been handled.

Yet several situations call for caution:

1. A user accidentally clicks "Delete" and needs recovery within a grace period.
2. An account closes while order history must remain under a separate policy.
3. Support teams need to tell "never existed" apart from "was deleted".
4. Background jobs, caches, or search engines have not yet processed the deletion event.
5. Foreign keys forbid deleting a parent row while child rows still reference it.
6. Deleting millions of rows at once creates heavy load, WAL spikes, and dead tuples.
7. Data must be hidden from normal features right away, yet cannot be purged yet.

**Soft delete solves certain recovery and lifecycle needs**, yet does not remove data from storage, backups, or downstream systems. When data truly must be erased under a compliance mandate, corresponding purge, anonymization, or erasure pipelines are required.

## 2. Comparing Soft Delete, Hard Delete, Archiving, and Anonymization

| Strategy | Operation | Row Still in Main Table? | Recoverability | Key Considerations |
|---|---|---|---|---|
| Soft delete | `UPDATE ... SET deleted_at` | Yes | Usually easy before purge | Queries must filter; data still exists |
| Hard delete | `DELETE FROM ...` | Gone after commit | Usually needs backup/PITR to recover | FKs, WAL, MVCC, vacuum |
| Archive | Move/classify data to secondary storage | Depends on design | Readable via archive process | Not deletion; still requires access controls |
| Anonymization | Strip or transform identifying fields | De-identified row may remain | Depends on method | Must evaluate re-identification risk |
| Logical deactivation | `status = 'inactive'` | Yes | Status can be toggled back | Not automatically equivalent to soft delete |

A row with `status = 'cancelled'` should not necessarily be soft-deleted. For example, a cancelled order remains an important business event for cancellation-rate reporting.

Conversely, an account with `deleted_at IS NOT NULL` normally disappears from active account lists regardless of its status prior to deletion.

## 3. Distinguishing Business Status from Existence Status

A common design mistake is cramming every meaning into one `status` column:

~~~text
active
inactive
deleted
archived
blocked
pending
~~~

That list mixes unrelated dimensions:

- `active` / `blocked`: account usage status.
- `deleted`: record excluded from normal active visibility.
- `archived`: data moved to a different storage tier.
- `pending`: likely a business workflow state.

It is usually cleaner to separate at least two dimensions:

~~~text
account_status : active | suspended
deleted_at     : NULL or soft-delete timestamp
~~~

Complex systems may model a full lifecycle state machine, ensuring states never contradict one another.

Example:

~~~text
Registration
   |
   v
ACTIVE -------> SUSPENDED
   |                 |
   |                 +-------> ACTIVE
   |
   +-------> SOFT_DELETED
                     |
                     +-------> RESTORED (per policy)
                     |
                     +-------> PURGE_ELIGIBLE
                                  |
                                  v
                             HARD_DELETED
~~~

Here `SOFT_DELETED` can be represented by `deleted_at IS NOT NULL` without polluting the `account_status` enum. `PURGE_ELIGIBLE` is a **point-in-time evaluation**, not necessarily a permanently stored column value.

## 4. Common Fields for Soft Delete

Minimalist design:

~~~sql
CREATE TABLE demo_document (
    document_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
~~~

Interpretation:

- `deleted_at IS NULL`: document is not soft-deleted.
- `deleted_at IS NOT NULL`: document is marked soft-deleted.
- `deleted_at` records **when** the event happened, supporting retention and audit queries.

Useful extended columns:

| Field | Purpose | Notes |
|---|---|---|
| `deleted_at TIMESTAMPTZ` | Soft-delete timestamp | Use clear timezone-aware instant semantics |
| `deleted_by` | User/system requesting deletion | Can be an ID or trusted actor identifier |
| `deletion_reason` | Reason code/description | Avoid storing unnecessary sensitive info |
| `retention_until TIMESTAMPTZ` | Earliest date purge is allowed | Does not express the full policy alone |
| `legal_hold BOOLEAN` | Blocks purge under preservation hold | Real systems may need a separate holds table |
| `created_at` | Creation timestamp | Distinct from retention start anchors for each data type |
| `updated_at` | Last update timestamp | PostgreSQL does not auto-update without explicit logic/triggers |
| `account_status` | Business status | Should not replace `deleted_at` alone |

**No single column set is mandatory for every app.** Small tables may need only `deleted_at`; policy-heavy systems need rich metadata and decision histories.

## 5. Self-Contained PostgreSQL Schema Example

We create a learning schema with two tables: customers and orders. Synthetic data avoids real personal details.

**Run only in a dedicated practice database.** The script creates a new schema and tables; if objects with these names exist, use a fresh test database or migration workflow rather than deleting live data.

~~~sql
CREATE SCHEMA lifecycle_lab;

CREATE TABLE lifecycle_lab.customer (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    account_status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    deleted_at TIMESTAMPTZ,
    deleted_by TEXT,
    deletion_reason TEXT,
    retention_until TIMESTAMPTZ,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_customer_status
        CHECK (account_status IN ('active', 'suspended')),

    CONSTRAINT chk_customer_delete_metadata
        CHECK (
            (
                deleted_at IS NULL
                AND deleted_by IS NULL
                AND deletion_reason IS NULL
                AND retention_until IS NULL
            )
            OR (
                deleted_at IS NOT NULL
                AND retention_until IS NOT NULL
                AND retention_until >= deleted_at
            )
        )
);

CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;

CREATE INDEX ix_customer_purge_candidate
ON lifecycle_lab.customer (retention_until, customer_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;

CREATE TABLE lifecycle_lab.customer_order (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lifecycle_lab.customer(customer_id),
    order_status TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    deleted_at TIMESTAMPTZ,
    retention_until TIMESTAMPTZ,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT chk_order_status
        CHECK (
            order_status IN (
                'draft', 'confirmed', 'fulfilled', 'cancelled'
            )
        ),

    CONSTRAINT chk_order_amount
        CHECK (total_amount >= 0),

    CONSTRAINT chk_order_delete_metadata
        CHECK (
            (deleted_at IS NULL AND retention_until IS NULL)
            OR (
                deleted_at IS NOT NULL
                AND retention_until IS NOT NULL
                AND retention_until >= deleted_at
            )
        )
);

CREATE INDEX ix_order_live_by_customer
ON lifecycle_lab.customer_order (customer_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX ix_order_purge_candidate
ON lifecycle_lab.customer_order (retention_until, order_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;
~~~

This design illustrates several deliberate choices:

- Customers and orders have **stable primary keys**; soft delete never changes IDs.
- Only non-deleted customers participate in the **case-insensitive unique index via `lower(email)`**.
- Orders reference customers via a foreign key; soft-deleting a customer **does not break the foreign key**.
- `retention_until` appears on both tables to represent separate retention timestamps; real systems may apply completely different policies to each.
- `legal_hold` demonstrates blocking physical deletion temporarily.
- Partial indexes target frequent active-row queries.
- `updated_at` is maintained by application/SQL updates; this DDL **has no auto-updating trigger** on edits.

### 5.1. Why Not Use a Table-Wide `UNIQUE(email)`?

If you declare:

~~~sql
-- Keeps email unique across the entire history of records:
-- UNIQUE (email)
~~~

then after soft-deleting a customer, a new customer still cannot register with that email, even if product policy allows reuse.

The partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;
~~~

only enforces that **no two non-deleted rows** share the same `lower(email)` value under active comparison rules. Soft-deleted rows stay outside this index.

Whether to allow email reuse is a **business rule**, not an automatic property of soft delete. If emails must remain globally unique forever, use a full unique constraint or a dedicated identity registry.

### 5.2. Why Use TIMESTAMPTZ?

`TIMESTAMPTZ` represents points in time under PostgreSQL's timezone-aware instant semantics, ideal for computing retention deadlines, comparing logs, and working across time zones.

Example:

~~~sql
SELECT
    now() AS current_transaction_time,
    statement_timestamp() AS current_statement_time,
    clock_timestamp() AS current_wall_clock_time;
~~~

How they differ:

- `now()` returns the start time of the current transaction.
- `statement_timestamp()` returns the start time of the current statement.
- `clock_timestamp()` returns the current wall-clock time when called, advancing even mid-statement.

When recording one delete event, choose and reuse **one consistent timestamp** rather than populating multiple fields with slightly different clock calls.

## 6. Loading Fixed Practice Data

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status, created_at)
VALUES
    (
        101, 'an@example.test', 'An Nguyen', 'active',
        TIMESTAMPTZ '2026-01-05 08:00:00+00'
    ),
    (
        102, 'binh@example.test', 'Binh Tran', 'active',
        TIMESTAMPTZ '2026-01-06 08:00:00+00'
    ),
    (
        103, 'chi@example.test', 'Chi Le', 'suspended',
        TIMESTAMPTZ '2026-01-07 08:00:00+00'
    );

INSERT INTO lifecycle_lab.customer_order
    (order_id, customer_id, order_status, total_amount, created_at)
VALUES
    (
        1001, 101, 'confirmed', 250000.00,
        TIMESTAMPTZ '2026-01-10 10:00:00+00'
    ),
    (
        1002, 101, 'draft', 150000.00,
        TIMESTAMPTZ '2026-01-11 11:00:00+00'
    ),
    (
        1003, 102, 'fulfilled', 600000.00,
        TIMESTAMPTZ '2026-01-12 12:00:00+00'
    ),
    (
        1004, 103, 'cancelled', 90000.00,
        TIMESTAMPTZ '2026-01-13 13:00:00+00'
    );
~~~

Right after loading:

- There are 3 customers.
- There are 4 orders.
- No rows are soft-deleted yet.
- Emails are unique among active customers.
- A customer can have multiple orders.

The data uses `example.test` addresses to avoid colliding with real accounts. Never put real personal data or production tokens into practice labs.

## 7. Soft-Deleting a Customer with UPDATE

To soft-delete customer 102:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    deleted_by = 'operator:training',
    deletion_reason = 'user_requested',
    retention_until = statement_timestamp() + INTERVAL '90 days',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NULL
RETURNING
    customer_id,
    email,
    deleted_at,
    retention_until;
~~~

Explanation:

- No `DELETE` is run; the row stays in the table.
- `deleted_at` records the soft-delete instant.
- `deleted_by` and `deletion_reason` provide basic traceability.
- `retention_until` marks the earliest time **purge eligibility may be evaluated**, without automatically triggering deletion.
- `AND deleted_at IS NULL` ensures repeated calls do not overwrite the original soft-delete timestamp.
- `RETURNING` reports which row was actually modified.

Calling the exact same statement a second time no longer matches `deleted_at IS NULL` and `RETURNING` returns **0 rows**—clearly distinguishing a repeat from the initial soft delete.

### 7.1. Why Be Careful with Repeated Calls?

If you write:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = now(),
    retention_until = now() + INTERVAL '90 days'
WHERE customer_id = 102;
~~~

every retried request **pushes the purge deadline further into the future**. Under multiple retries, data stays retained longer than policy allows.

Therefore, make soft-delete operations **idempotent**: retrying the request must not alter the established timestamp unless the business intentionally extends retention.

### 7.2. Avoid a Lone Boolean When Auditing Is Needed

An `is_deleted BOOLEAN` column supports basic filtering:

~~~sql
-- Minimalist design lacking timestamps:
-- is_deleted BOOLEAN NOT NULL DEFAULT FALSE
~~~

Yet when you need to answer "when was it deleted?", "when can it be purged?", or "is it overdue?", a boolean lacks the necessary information.

If only UI visibility matters with zero temporal rules, a boolean can suffice. If storing both `is_deleted` and `deleted_at`, enforce a constraint or single source of truth so they never contradict each other.

## 8. Default Queries Must Exclude Soft-Deleted Rows

An unfiltered query:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
ORDER BY customer_id;
~~~

still returns customer 102. That is standard SQL behavior: soft delete is just a column value, and PostgreSQL does not hide rows automatically.

Querying only active (non-deleted) customers:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
ORDER BY customer_id;
~~~

Expected result after deleting customer 102:

| customer_id | email | full_name |
|---:|---|---|
| 101 | an@example.test | An Nguyen |
| 103 | chi@example.test | Chi Le |

If business rules also exclude suspended accounts:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND account_status = 'active'
ORDER BY customer_id;
~~~

Only customer 101 satisfies both predicates.

**Key rule:** "Not soft-deleted" and "permitted to use the account" are two separate checks. A record with `deleted_at IS NULL` and `account_status = 'suspended'` still should not be treated as fully active.

## 9. Designing a VIEW for Live Records

To centralize the active-row filter, you can define a view:

~~~sql
CREATE VIEW lifecycle_lab.active_customer AS
SELECT
    customer_id,
    email,
    full_name,
    account_status,
    created_at,
    updated_at
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL;
~~~

Usage:

~~~sql
SELECT customer_id, email, full_name
FROM lifecycle_lab.active_customer
ORDER BY customer_id;
~~~

Views centralize the **definition of live records** in one place. However:

- Standard views **do not store a separate copy** of the data.
- Views do not prevent roles with privileges on the base table from reading deleted rows directly.
- Views do not turn soft delete into an automatic filter across all SQL queries.
- DML through views carries specific conditions, limits, and semantics.

To restrict an application to reading only via views, configure **GRANT/REVOKE and roles** explicitly. UI/view filters alone are not security boundaries.

### 9.1. JOIN Queries Must Clarify Status on Both Tables

Example showing live orders belonging to non-deleted customers:

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.order_status,
    o.total_amount
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.deleted_at IS NULL
  AND c.deleted_at IS NULL
ORDER BY o.order_id;
~~~

If you forget `c.deleted_at IS NULL`, orders of soft-deleted customers appear. If you filter customers while forgetting orders, soft-deleted orders appear.

Conversely, workflows such as reconciliation, customer support, or compliance reporting may **need** to see orders of soft-deleted customers. Always match filters to the **query's purpose** rather than adding them blindly everywhere.

## 10. Partial Indexes: Optimizing Queries on Live Data

PostgreSQL supports **partial indexes**—indexing only rows matching a `WHERE` predicate.

Already created in our schema:

~~~sql
CREATE INDEX ix_order_live_by_customer
ON lifecycle_lab.customer_order (customer_id, created_at DESC)
WHERE deleted_at IS NULL;
~~~

Matching query:

~~~sql
SELECT order_id, created_at, total_amount
FROM lifecycle_lab.customer_order
WHERE customer_id = 101
  AND deleted_at IS NULL
ORDER BY created_at DESC;
~~~

This index helps queries touch only live orders, especially when soft-deleted rows make up a large share of the table.

Keep in mind:

- The planner uses an index only when it estimates lower cost.
- Small sample tables often trigger sequential scans instead of index scans; that is normal, not an error.
- Query predicates must allow the planner to prove the queried rows are a subset of the partial index predicate.
- Parameterized queries with overly generic predicates can sometimes prevent generic plans from matching partial indexes.
- Partial indexes do not remove soft-deleted rows from the heap table; they only exclude them from the index.

Inspect the plan:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM lifecycle_lab.customer_order
WHERE customer_id = 101
  AND deleted_at IS NULL
ORDER BY created_at DESC;
~~~

Never judge index usefulness from a four-row table. In production, evaluate realistic workloads, data skew, and index write overhead.

## 11. Partial UNIQUE Indexes: Allowing Email Reuse After Soft Delete

Problem: email must be unique only among **currently active (non-deleted) customers**.

Index already defined:

~~~sql
CREATE UNIQUE INDEX uq_customer_live_email
ON lifecycle_lab.customer (lower(email))
WHERE deleted_at IS NULL;
~~~

Once customer 102 is soft-deleted, try adding a new customer with the same email:

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (104, 'BINH@example.test', 'New Customer', 'active');
~~~

In our demo, this succeeds because soft-deleted row 102 is excluded from the partial unique index and `lower('BINH@example.test')` matches the reused address.

If you then try inserting **another non-deleted customer** with the equivalent email:

~~~sql
-- Expected unique violation when the index is active:
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (105, 'binh@example.test', 'Duplicate Email Customer', 'active');
~~~

PostgreSQL rejects it because two live customers cannot share the same `lower(email)` in the index.

### 11.1. Consequence When Restoring an Old Row

If customer 104 now holds `binh@example.test`, restoring customer 102 back to `deleted_at IS NULL` places both rows into the unique index—so the restore **fails with a unique violation**.

This is not a PostgreSQL flaw; it is an **identifier-reuse policy conflict**. Choose one clear business rule:

- Forbid reusing an email during the restore grace window.
- Allow reuse, but require a new email when restoring.
- Separate login identity from contact email.
- Check and resolve conflicts explicitly before restoring.
- Permit restores only within a clearly defined time window.

Never silently overwrite or rename the newer account's email just to force a restore through.

### 11.2. Collations and Case-Insensitivity Are Not Trivial

`lower(email)` depends on PostgreSQL character semantics and collations. Define email equivalence rules according to application policy, especially for Unicode, internationalized addresses, and string normalization.

If using `citext` or nondeterministic collations, understand their behavior, extension permissions, compatibility, and index impacts. Never assume plain `lower()` handles all global email conventions.

## 12. ON CONFLICT with Partial Unique Indexes

When live rows are constrained via a **partial unique index**, `INSERT ... ON CONFLICT` must specify the matching conflict target and predicate so PostgreSQL can infer the right index.

Example:

~~~sql
INSERT INTO lifecycle_lab.customer
    (customer_id, email, full_name, account_status)
VALUES
    (106, 'an@example.test', 'Test Name', 'active')
ON CONFLICT (lower(email)) WHERE deleted_at IS NULL
DO NOTHING;
~~~

With our loaded data, `an@example.test` belongs to live customer 101, so the statement inserts nothing for 106.

**Note:** a partial unique index is an index, not a table-wide `UNIQUE CONSTRAINT`. You cannot write `ON CONFLICT ON CONSTRAINT uq_customer_live_email` because `uq_customer_live_email` was created via `CREATE UNIQUE INDEX`, not as a named constraint.

If using `DO UPDATE`, carefully verify whether overwriting existing customer fields is permitted by business rules—never treat upserts as harmless by default.

## 13. Soft Delete Does Not Automatically Handle Foreign Keys

Suppose order 1003 belongs to customer 102. After customer 102 is soft-deleted:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.deleted_at AS customer_deleted_at
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 1003;
~~~

The order still references a valid customer foreign key because the customer row **still exists**. PostgreSQL does not treat `deleted_at IS NOT NULL` as breaking links.

Compare:

- **Soft delete:** `UPDATE customer SET deleted_at = ...` does not trigger foreign-key `ON DELETE` actions.
- **Hard delete:** `DELETE FROM customer ...` triggers PostgreSQL's declared foreign-key actions.

If multiple related objects must be soft-deleted together, implement explicit **business logic** (in application code, transactions, or well-designed triggers) rather than expecting `ON DELETE CASCADE` to fire on timestamp updates.

### 13.1. Should All Orders Be Soft-Deleted When a Customer Closes Their Account?

There is no universal answer.

For example:

- Draft orders may be soft-deleted alongside the account.
- Paid orders may need to stay visible for reconciliation.
- Fulfilled orders may require stripping personal identifiers while retaining transaction totals.
- Orders under legal hold must not be purged on normal schedules.

Blindly applying physical `ON DELETE CASCADE` or cascading soft deletes everywhere can violate differing retention policies.

**Principle:** define the lifecycle of each entity type independently, then specify how those lifecycles interact.

## 14. Designing Different Retention Policies for Customers and Orders

Sample policy matrix:

| Data Category | Retention Anchor | Illustrative Duration | Action at Expiration |
|---|---|---|---|
| Soft-deleted accounts | `deleted_at` | 90 days | Evaluate purge or anonymization |
| Cancelled draft orders | Cancellation timestamp | 30 days | Evaluate deletion if no dependencies exist |
| Fulfilled orders | Defined business milestone | Per financial/transaction policy | Archive / anonymize / purge per regulation |
| Operational audit logs | Log timestamp | 30 days | Delete / rotate by classification |
| Data under legal hold | Hold anchor and scope | Until hold is formally released | Never purge within hold scope |

These numbers are purely illustrative. Never assume all orders, financial records, or personal data may be or must be kept for these exact durations. **Real retention periods must be approved by your organization for specific compliance needs.**

### 14.1. Why One `retention_until` Column Isn't Enough for Every Policy

A single timestamp cannot answer:

- Why is the record retained until that date?
- Which policy version governs it?
- Who approved or extended the deadline?
- Is there an active preservation hold?
- Upon expiration, should we hard-delete, archive, or anonymize?
- Do replicas, backups, attachments, and analytics warehouses share the same deadline?

Large systems often need dedicated `retention_policy` and `retention_hold` tables alongside a decision audit log.

## 15. Versioned Retention Policy Model

One design for multi-category systems:

~~~sql
CREATE TABLE lifecycle_lab.retention_policy (
    policy_id BIGINT PRIMARY KEY,
    policy_code TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    data_category TEXT NOT NULL,
    duration_days INTEGER NOT NULL,
    retention_event TEXT NOT NULL,
    purge_action TEXT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_policy_version
        UNIQUE (policy_code, policy_version),
    CONSTRAINT chk_duration
        CHECK (duration_days >= 0),
    CONSTRAINT chk_purge_action
        CHECK (purge_action IN ('delete', 'anonymize', 'archive_review'))
);
~~~

This table holds **policy metadata** only. It does not execute deletions or enforce legal compliance automatically; application jobs must apply the rules and verify conditions.

Real systems often add:

- Policy effective start/end dates.
- Tenant, jurisdiction, or contract scope.
- External storage targets outside PostgreSQL.
- Legal basis and approver metadata.
- Exact calendar definitions for "days" or "months".
- Rules for applying newly approved policy versions.
- Hold precedence and pause rules.

### 15.1. Why Track Policy Versions?

Suppose last month customers fell under a 90-day policy, and today the organization changes it to 30 days. Storing only `retention_until` without metadata makes it hard to explain why one record was retained until a particular date.

You can store `retention_policy_id` or `policy_version` on records or purge logs for traceability. Also decide explicitly whether policy changes apply retroactively—that is a business governance decision, not something PostgreSQL resolves automatically.

## 16. Legal Holds: Blocking Purges Within an Approved Scope

Our sample table has:

~~~sql
legal_hold BOOLEAN NOT NULL DEFAULT FALSE
~~~

A purge worker must check `legal_hold = FALSE` before deleting. Yet a lone boolean has limits:

- Records neither the reason nor who placed the hold.
- Records no start or release timestamps.
- Cannot represent multiple overlapping holds independently.
- Leaves no history of who toggled it on or off.
- Cannot express holds spanning related records across other tables.

A richer model might look like:

~~~sql
CREATE TABLE lifecycle_lab.retention_hold (
    hold_id BIGINT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    hold_reason TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    released_at TIMESTAMPTZ,
    CONSTRAINT chk_hold_times
        CHECK (
            released_at IS NULL
            OR released_at >= applied_at
        )
);
~~~

This example is a **generic descriptive model**—it does not enforce polymorphic foreign keys on `entity_type + entity_id`. When strict referential integrity is needed, build per-entity hold tables or an explicit entity registry with proper foreign keys.

**Design warning:** when multiple holds exist, purge only when **zero active holds remain** under governing policy. Never let a job flip a single boolean flag to false while ignoring another hold table.

### 16.1. Solving Race Conditions with Holds

Suppose a purge worker checks "no hold exists" at the exact moment legal counsel inserts a new hold. Without coordination, the record could be purged right as the preservation hold is recorded.

Critical systems require consistent coordination:

- Lock the coordinating entity row when deciding hold vs. purge.
- Perform hold placement and purge eligibility checks inside transactions sharing the same locking protocol.
- Define business precedence when a hold and purge collide.
- Audit all hold/purge decisions and restrict privileges.

Never write `NOT EXISTS (hold)` in a standalone SQL query and assume concurrency races are solved.

## 17. Soft Delete and Restore States

Restoration can be modeled as:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
RETURNING customer_id, email, account_status;
~~~

Here `account_status` is set to `'suspended'` to require a review step before full reactivation. Other apps restore the prior pre-deletion status by saving it in a controlled column beforehand.

**If customer 104 was already inserted using customer 102's email earlier, this restore fails with a unique violation.** That demonstrates why restore workflows must explicitly handle identifier collisions.

### 17.1. Never Allow Indefinite Restores Just Because the Row Still Exists

A row past `retention_until` waiting for a nightly purge job may still sit in the database. That **does not automatically mean business rules permit restoring it**.

Restore eligibility should check:

- Active policy rules.
- Requester's role and authority.
- Allowed restore window.
- Key collisions and dependent records.
- Whether related records have already been anonymized or purged.

Illustrative guard:

~~~sql
-- Illustrative only when policy permits restoring
-- prior to retention_until.
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
  AND retention_until > statement_timestamp()
RETURNING customer_id;
~~~

Never invent restore time bounds by guesswork; business policy must specify them.

## 18. Transactions and Consistency When Deleting a Group of Records

An "account closure" request may affect:

- Primary customer record.
- Active login sessions.
- API tokens.
- Public profile visibility.
- Draft orders.
- Notification preferences.
- Search indexes or caches.
- External email services.

If all affected tables reside inside **the same PostgreSQL database**, coordinate those updates in one transaction:

~~~sql
BEGIN;

-- Illustrative example: mark draft orders of customer 101 soft-deleted.
UPDATE lifecycle_lab.customer_order
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '30 days'
WHERE customer_id = 101
  AND order_status = 'draft'
  AND deleted_at IS NULL;

-- Soft-delete customer profile, recording timestamp and reason.
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    deleted_by = 'operator:training',
    deletion_reason = 'account_closed',
    retention_until = statement_timestamp() + INTERVAL '90 days',
    updated_at = statement_timestamp()
WHERE customer_id = 101
  AND deleted_at IS NULL;

COMMIT;
~~~

If anything fails before commit, rollback prevents half-deleted inconsistent state.

**This is a simplified lab model.** Do not assume all real draft orders expire after 30 days or all orders vanish when a customer closes their account.

### 18.1. External Side Effects Do Not Roll Back with PostgreSQL Transactions

Suppose during account closure the service calls a search API to delete a document or sends an email. If the PostgreSQL transaction rolls back afterward, those external side effects will not roll back.

Consider the **transactional outbox** pattern:

1. Update soft-delete state in PostgreSQL.
2. Insert an outbox event row in the same transaction.
3. Commit.
4. A worker reads the outbox and updates search indexes, caches, and notifications.
5. The worker handles retries and idempotency using event IDs.

This prevents "database rolled back while external systems processed the delete" and "database committed while the event was lost mid-flight".

## 19. Soft Delete, Concurrency, and Idempotency

Suppose two requests concurrently attempt to delete the same customer:

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '90 days'
WHERE customer_id = 103
  AND deleted_at IS NULL
RETURNING customer_id, deleted_at;
~~~

PostgreSQL uses MVCC and row locks for `UPDATE`. One request acquires the row lock and updates first; the second re-evaluates the predicate once unblocked, sees `deleted_at` is no longer `NULL`, and updates 0 rows.

This avoids overwriting the timestamp, yet **does not eliminate all concurrency issues**:

- Restore and purge competing simultaneously.
- Email update racing with soft delete.
- New order creation racing with account closure.
- Legal hold added while a purge check is running.
- Two restores colliding on a partial unique index.

Combine transactions, locks, constraints, and clear business rules. For critical lifecycle actions, **never assume clients send a request only once**; retries are normal.

## 20. Hard Delete: What Happens Inside PostgreSQL?

Running:

~~~sql
DELETE FROM lifecycle_lab.customer_order
WHERE order_id = 1002;
~~~

differs from `UPDATE deleted_at` in that the row is logically removed upon SQL transaction commit.

However, under PostgreSQL **MVCC**:

- Old tuple versions physically remain until no active transaction can see them.
- `VACUUM` reclaims dead tuples for space reuse according to storage rules.
- Heap/index files do not automatically shrink on disk right after `DELETE`.
- WAL retains mutation records for recovery and replication.
- Replicas, backups, and WAL archives follow their own retention schedules.

Therefore, never claim "once `DELETE` finishes, every byte vanishes instantly from every copy".

**Hard-deleting from the live table** and **erasing data from backups, logs, caches, and object storage** are separate concerns. System-wide erasure policies must address all layers.

### 20.1. VACUUM Is Not a Soft-Delete Purge Tool

`VACUUM` reclaims tuples no longer visible under MVCC for database maintenance. It **does not inspect `deleted_at`** or treat soft-deleted rows as garbage.

~~~sql
-- Does NOT remove rows merely marked with deleted_at.
VACUUM lifecycle_lab.customer;
~~~

Soft-deleted rows are still live tuples in the table, so `VACUUM` never purges them based on a timestamp column.

## 21. When Is a Row Eligible for Purge?

A baseline decision flow:

~~~text
Soft-deleted?
      |
      +-- No ---> Do not purge via this pipeline
      |
      v
Reached retention_until?
      |
      +-- No ---> Keep retaining
      |
      v
Legal hold or blocking dependency?
      |
      +-- Yes --> Defer, log reason
      |
      v
Passed business & dependency checks?
      |
      +-- No ---> Defer, handle exception
      |
      v
Eligible for controlled hard delete
~~~

Minimalist SQL query:

~~~sql
SELECT
    customer_id,
    email,
    retention_until
FROM lifecycle_lab.customer
WHERE deleted_at IS NOT NULL
  AND retention_until <= statement_timestamp()
  AND legal_hold = FALSE
ORDER BY retention_until, customer_id;
~~~

**This is only a candidate list.** It does not yet verify child orders needing retention, holds in separate tables, or concurrent policy updates.

Never compress all legal and domain rules into one short `WHERE` clause and assume every returned row is safe to delete.

## 22. Batched Purges to Control Load

A single `DELETE` removing millions of rows in one transaction can:

- Generate massive WAL spikes.
- Hold row locks for a long time.
- Create huge dead-tuple surges.
- Overload autovacuum.
- Cause replication lag.
- Prolong transactions and disrupt live traffic.

Purge in **small controlled batches** with progress tracking and throttling.

Example batch of up to 100 soft-deleted orders meeting simple eligibility:

~~~sql
WITH candidates AS (
    SELECT order_id
    FROM lifecycle_lab.customer_order
    WHERE deleted_at IS NOT NULL
      AND retention_until <= statement_timestamp()
      AND legal_hold = FALSE
    ORDER BY retention_until, order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
DELETE FROM lifecycle_lab.customer_order AS o
USING candidates AS c
WHERE o.order_id = c.order_id
RETURNING
    o.order_id,
    o.customer_id,
    o.retention_until;
~~~

How it works:

1. CTE `candidates` picks a bounded batch of eligible rows.
2. `FOR UPDATE` locks those candidate rows for the statement's transaction.
3. `SKIP LOCKED` lets concurrent workers skip rows locked by other workers instead of blocking.
4. `DELETE ... USING` deletes the exact locked candidates.
5. `RETURNING` outputs which rows were removed.

**`SKIP LOCKED` provides an intentionally incomplete point-in-time view**: locked rows are skipped and retried on subsequent passes. Great for queues/batch workers, never for exact reporting reads.

### 22.1. Why Limit Batch Size?

With batches of 100 or 1,000 rows, workers can:

- Commit frequently.
- Avoid long-running transactions.
- Track deleted counts and batch duration.
- Pause automatically under high database load.
- Tune batch size empirically.

No single batch size fits every table. Rows with large JSON/BLOB payloads or many referencing tables cost far more per row than tiny rows.

### 22.2. The Sample Query Alone Is Not Production-Ready

Before running real purges, check:

- Foreign keys and child tables.
- External holds and policy versions.
- Archiving or anonymization requirements.
- Worker role privileges and throttling limits.
- Auditing without leaking sensitive payloads.
- Copies across replicas, CDC streams, backups, and external stores.
- Recovery procedures for accidental deletions.

**Never paste this sample hard-delete query straight into a production cron job.**

## 23. Purging Parent Rows Requires Checking Child Data

`customer_order` has a foreign key pointing to `customer`. In our sample schema, the FK does not specify `ON DELETE CASCADE`.

Attempting to hard-delete a customer who still has orders:

~~~sql
-- Expected to fail while referencing orders still exist.
DELETE FROM lifecycle_lab.customer
WHERE customer_id = 101;
~~~

PostgreSQL checks the foreign key and rejects the deletion, preserving referential integrity.

Querying **customer purge candidates with zero remaining orders**:

~~~sql
SELECT
    c.customer_id,
    c.retention_until
FROM lifecycle_lab.customer AS c
WHERE c.deleted_at IS NOT NULL
  AND c.retention_until <= statement_timestamp()
  AND c.legal_hold = FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM lifecycle_lab.customer_order AS o
      WHERE o.customer_id = c.customer_id
  )
ORDER BY c.retention_until, c.customer_id;
~~~

Notice `NOT EXISTS` checks **all orders**, not just non-deleted ones. A soft-deleted order that has not yet been hard-deleted still references the customer.

### 23.1. When Should `ON DELETE CASCADE` Be Used?

A foreign key with `ON DELETE CASCADE` physically deletes child rows whenever the parent is hard-deleted:

~~~sql
-- Conceptual example; do not alter the demo schema:
-- FOREIGN KEY (customer_id)
-- REFERENCES customer(customer_id)
-- ON DELETE CASCADE
~~~

However, cascade ignores whether child rows have `legal_hold`, longer retention periods, or separate archiving rules. Cascading deletes are dangerous when parent and child entities have independent lifecycles.

Use cascade only when ownership and lifecycle rules of the child data genuinely match the parent's—never to "work around" foreign-key errors in a purge job.

### 23.2. Keeping Orders While Removing Customer Identifying Info

You may need to separate:

- Customer personally identifiable information (PII).
- Financial transaction records that must be retained.
- A non-identifying surrogate reference for reconciliation.

Solutions include anonymizing customer fields when permitted, isolating PII in a separate identity table, or designing decoupled relationships upfront. **Never assume overwriting email with a dummy string alone makes the whole record non-identifiable.**

## 24. Audit Logs: Who Deleted, Restored, Held, or Purged?

A single `deleted_by` field helps, yet misses multi-step histories:

- Person A soft-deletes.
- Person B restores.
- Person C soft-deletes again.
- A job updates retention.
- Legal counsel applies a hold.
- A worker runs hard delete.

When full lifecycle auditing is required, add an event table:

~~~sql
CREATE TABLE lifecycle_lab.data_lifecycle_event (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    actor_id TEXT NOT NULL,
    policy_code TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_lifecycle_event_type
        CHECK (
            event_type IN (
                'soft_deleted',
                'restored',
                'retention_changed',
                'hold_applied',
                'hold_released',
                'purged'
            )
        )
);
~~~

This is a minimal template. Production systems must also design:

- Append-only and read permissions on the audit table.
- Tamper protection against unauthorized edits/deletes.
- Allowed fields inside `details`.
- Linking events to idempotency keys / request IDs.
- Event ordering accuracy and transaction alignment.
- Retention policy **for the audit log itself**.
- Recording purge events after the primary row is gone.

**Never dump emails, tokens, or sensitive PII indiscriminately into audit logs**; doing so retains sensitive data past intended erasure deadlines.

## 25. Writing Lifecycle Events in the Soft-Delete Transaction

Example soft delete + audit event in one transaction:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE lifecycle_lab.customer
    SET
        deleted_at = statement_timestamp(),
        deleted_by = 'operator:training',
        deletion_reason = 'user_requested',
        retention_until = statement_timestamp() + INTERVAL '90 days',
        updated_at = statement_timestamp()
    WHERE customer_id = 103
      AND deleted_at IS NULL
    RETURNING customer_id
)
INSERT INTO lifecycle_lab.data_lifecycle_event
    (entity_type, entity_id, event_type, actor_id, policy_code)
SELECT
    'customer',
    customer_id,
    'soft_deleted',
    'operator:training',
    'customer-retention-example'
FROM changed;

COMMIT;
~~~

If zero customer rows matched, the `changed` CTE returns 0 rows and no spurious `soft_deleted` event is inserted.

Transactions guarantee that state updates and in-database audit rows commit or roll back together. Note that if security requires logging **failed or rejected attempts**, that needs an external or out-of-transaction logging mechanism.

## 26. Event Sourcing vs. Soft Delete

Soft delete keeps the current row alongside a flag/timestamp. **Event sourcing** stores an immutable sequence of domain events and derives state by replaying them. The two models are distinct:

~~~text
Soft delete:
  customer(id=101, deleted_at=...)

Event sourcing:
  CustomerCreated
  CustomerEmailChanged
  CustomerDeleted
~~~

An event-sourced system still needs retention and access controls for its event store; personal data can persist inside historical events. Appending a `CustomerDeleted` event does not automatically erase bytes from older events.

Soft delete, outboxes, and event logs can coexist—just define clearly where the source of truth lives and how data erasure works in each store.

## 27. Soft Delete in ORMs and Repository Layers

ORMs often offer annotations or global filters to hide soft-deleted rows. Whether using Hibernate, Spring Data, or another library, verify carefully:

1. Does `findById` exclude soft-deleted rows?
2. Do native SQL queries automatically apply the filter?
3. Do aggregate queries and JOINs apply consistent semantics?
4. Can batch jobs and admin queries bypass the filter when needed?
5. Do partial unique indexes align with ORM filters?
6. Can restores trigger unique conflicts?
7. Does the ORM ever emit real SQL `DELETE` when soft delete was intended?
8. Are second-level or application caches invalidated properly on state changes?

Never trust an ORM soft-delete annotation alone to enforce uniform filtering across every native query, trigger, stored function, and background job.

### 27.1. Repository APIs Should Express Intent Clearly

Conceptual application-layer methods:

~~~text
findActiveCustomer(id)
findCustomerIncludingDeleted(id)
softDeleteCustomer(id, actor, reason)
restoreCustomer(id, actor)
findPurgeCandidates(cutoff, batchSize)
~~~

Explicit method names are far clearer than a generic `delete()` method mixing soft and hard deletes.

For SQL statements, always use prepared statements and bound parameters for IDs, actors, and reasons—never concatenate user input into SQL strings.

## 28. Can Row-Level Security Replace Soft-Delete Filters?

PostgreSQL **Row-Level Security (RLS)** controls which rows a role may read or modify under defined policies.

In principle, you could write an RLS policy restricting the app role to `deleted_at IS NULL`. However:

- RLS is a **row-level authorization mechanism**, not a retention tool.
- `USING` and `WITH CHECK` policies behave differently across `SELECT`, `UPDATE`, and `INSERT`.
- Table owners, `BYPASSRLS` roles, and superusers bypass RLS by default.
- Soft-delete `UPDATE`s must be permitted to transition a row from "visible" to "not visible" without `WITH CHECK` unexpectedly blocking the update.
- Audit readers may need to see tombstones while runtime roles must not.
- RLS on one table never deletes data in related tables or backups.

Therefore, **never turn on a sample RLS policy in production simply to replace `WHERE` clauses** without testing all read, write, soft-delete, restore, and admin paths end to end.

You can combine approaches—having runtime roles read via controlled views/RLS while operations roles inspect deleted rows through audited workflows—but design, test, and monitor security and lifecycle goals separately.

## 29. Multi-Tenancy: Uniqueness and Retention per Tenant

Suppose a system serves multiple organizations (tenants). An email may exist across multiple tenants, yet must remain unique among non-deleted customers **within the same tenant**.

Example partial unique index:

~~~sql
-- Assumes table has tenant_id and email:
CREATE UNIQUE INDEX uq_customer_live_email_per_tenant
ON tenant_customer (tenant_id, lower(email))
WHERE deleted_at IS NULL;
~~~

This is a syntax illustration—do not run it on `lifecycle_lab.customer` since that demo table lacks `tenant_id`.

In multi-tenant systems, keep in mind:

- Every query must enforce `tenant_id` boundaries per the security model.
- Retention periods may vary by contract or data category, always following approved policies.
- Purging one tenant must never affect any other tenant's rows.
- Indexes and foreign keys must preserve same-tenant integrity where required.
- Audit logs and outboxes may need `tenant_id` while preventing cross-tenant leakage.
- Shared system-wide data may follow a different lifecycle than tenant-owned data.

**Partial indexes do not enforce tenant isolation.** They only enforce the declared uniqueness rule.

## 30. Partitioning and Retention for Huge Datasets

On massive log, event, or time-series tables, row-by-row deletes are expensive. PostgreSQL supports **declarative partitioning** by a partition key.

Example:

~~~sql
CREATE TABLE lifecycle_lab.event_log (
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL
)
PARTITION BY RANGE (occurred_at);

CREATE TABLE lifecycle_lab.event_log_2026_01
PARTITION OF lifecycle_lab.event_log
FOR VALUES FROM ('2026-01-01 00:00:00+00')
             TO ('2026-02-01 00:00:00+00');

CREATE TABLE lifecycle_lab.event_log_2026_02
PARTITION OF lifecycle_lab.event_log
FOR VALUES FROM ('2026-02-01 00:00:00+00')
             TO ('2026-03-01 00:00:00+00');
~~~

When an entire partition holds **expired data with no remaining holds**, you can detach, archive, or drop the partition per PostgreSQL docs instead of running row-by-row `DELETE`.

### 30.1. Never Drop a Partition Just Because It's "Old"

Before dropping a partition, confirm:

- All rows inside the partition are expired under policy.
- Zero legal holds or exception records reside in that partition.
- Backups, archives, and audits are complete.
- No active query or report needs recovery from that partition.
- Foreign keys and dependencies permit dropping it.
- The operation is approved and rehearsed.

If January's partition contains even one record that must be retained until next year, **dropping the entire January partition is wrong**. Extract exception records, partition by policy expiration, or purge row-by-row.

### 30.2. Partition Keys Dictate Purge Strategy

If retention keys off `occurred_at`, time partitioning fits immutable data like event logs cleanly.

If retention keys off `deleted_at` while most rows remain undeleted, partitioning by `created_at` does not guarantee every row in an old partition is purge-eligible.

Architectural options include:

- Keeping live data in an active table.
- Moving deleted rows to a separate tombstone/archive table.
- Partitioning the archive table by expiration date.
- Maintaining clean data-movement and referential-integrity pipelines.

This is a major architectural choice; weigh query patterns, uniqueness, foreign keys, and operational complexity carefully.

### 30.3. Unique Constraints on Partitioned Tables Have Limitations

In PostgreSQL, `UNIQUE` and `PRIMARY KEY` constraints on partitioned tables must include all partition key columns; there is no built-in **global unique index** solely on a non-partition-key column.

Thus, partitioning `customer` by `deleted_at` or `created_at` may require redesigning the "live email unique across the entire table" rule. Never copy a non-partitioned table's partial unique index onto a partitioned table without verifying PostgreSQL version constraints and partitioning semantics.

## 31. Archiving and Tiered Storage

Soft delete does not save storage space. Leaving huge volumes of deleted rows in main tables gradually degrades:

- Table and index scans.
- `VACUUM`/`ANALYZE` runs.
- Backup and restore times.
- Replication and WAL volume.
- Storage provisioning costs.
- Rows scanned and discarded in analytics.

A tiered lifecycle flow might look like:

~~~text
Active operational data
      |
      | Reaches low-activity / closed milestone
      v
Controlled archive storage
      |
      | Retention expired + zero holds
      v
Purge / anonymize per policy
~~~

Archives can live in a separate schema/table, separate database, or object storage in an appropriate format. Moving rows out of the live table **does not automatically reduce security or retention obligations**.

Plan explicitly for:

- How archived records are queried when needed.
- Integrity verification and checksums.
- Access controls and encryption.
- Retention schedules on the archive tier.
- Partial restoration when required.
- Deleting archived copies upon expiration.

If tables carry foreign keys spanning live and archived rows, design the architecture upfront; moving parent rows out alone either breaks links or gets blocked by FKs.

## 32. Indexing for Soft Delete and Purge

At least two distinct query workloads exist.

### 32.1. Live Queries

Example:

~~~sql
SELECT *
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND lower(email) = lower('an@example.test');
~~~

The partial unique index `uq_customer_live_email` can serve `lower(email)` lookups when predicates match.

### 32.2. Purge Queries

~~~sql
SELECT customer_id, retention_until
FROM lifecycle_lab.customer
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE
  AND retention_until <= statement_timestamp()
ORDER BY retention_until, customer_id
LIMIT 100;
~~~

Partial index for purge candidates:

~~~sql
CREATE INDEX ix_customer_purge_candidate
ON lifecycle_lab.customer (retention_until, customer_id)
WHERE deleted_at IS NOT NULL
  AND legal_hold = FALSE;
~~~

Already defined in our demo schema, separate from live query indexes.

**Never index every column combination just because a query exists.** Every index adds write, storage, and vacuum overhead. Use statistics and `EXPLAIN (ANALYZE, BUFFERS)` in a realistic test environment to evaluate.

### 32.3. Why Can `UPDATE deleted_at` Be Expensive?

When `deleted_at` changes from `NULL` to a timestamp, the row leaves the "live" partial indexes and enters the "purge" partial indexes. PostgreSQL must update indexes and write a new MVCC tuple version. At high scale, bulk soft deletes generate significant WAL and dead tuples requiring vacuuming.

Choosing soft delete over hard delete **is not free**; it changes semantics and shifts when storage cleanup work happens.

## 33. VACUUM, Autovacuum, and Bloat

PostgreSQL uses MVCC: `UPDATE` creates new tuple versions, and `DELETE` marks old versions obsolete once transactions complete. `VACUUM` reclaims dead tuples so space can be reused.

Implications:

- Soft deletes via `UPDATE` still incur write and vacuum overhead.
- Hard-deleting millions of rows generates massive dead tuples.
- Long-running transactions delay cleanup of obsolete tuple versions.
- Indexes covering columns modified by soft delete still need maintenance.
- Table bloat grows if write/delete volume outpaces autovacuum.

Inspect table vacuum statistics:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lifecycle_lab'
ORDER BY n_dead_tup DESC;
~~~

`n_live_tup` and `n_dead_tup` are statistical estimates, not exact real-time counts.

Never disable autovacuum just to speed up a purge job without understanding the fallout. At scale, monitor bloat, WAL, replication lag, and checkpoints together.

## 34. Backups, WAL, CDC, and Downstream Copies

A soft-deleted record still exists in:

- The live PostgreSQL table.
- Subsequent backups containing that table.
- Earlier backups in its pre-deleted state.
- WAL archives retained for backup/replication.
- Read replicas and CDC pipelines.
- Search indexes, caches, and data warehouses until synced.
- Previously generated file exports and reports.

Even after hard delete, backups and downstream stores follow **independent retention lifecycles**. You cannot claim "erased everywhere" solely from running `DELETE` on the primary database.

### 34.1. Backup Retention Differs from Row Retention

For example:

- A customer row is purged from primary at 10:00.
- Backups taken before 10:00 still contain that row.
- WAL/backup archives persist until DR retention expiration.

Clarify boundaries across:

1. Row retention in the live database.
2. Snapshot and backup retention.
3. Replica, CDC, and analytics retention.
4. Restoring backups without accidentally resurrecting purged data.

In strict data-erasure environments, align data protection, backup, and recovery policies end to end—never claim one SQL script satisfies all legal obligations alone.

### 34.2. What Happens When Restoring an Old Backup?

A backup taken before deletion restores the row in its undeleted state. Disaster recovery plans should account for:

- Recovery point and obligations to replay deletions issued after that point.
- Event logs or deletion manifests to re-apply in recovery environments.
- Access restrictions on temporary restore instances used for verification.
- Pre-cutover validation before serving restored data back to users.

That is why retention is much more than a nightly `DELETE` cron job.

## 35. Designing a Controlled Purge Job

A production purge job should include at least:

**Inputs:** data category, policy/version, evaluation timestamp, batch size, execution role.

**Eligibility checks:** soft-deleted, past retention deadline, zero legal holds, FKs and dependencies cleared, no conflicting workflows.

**Execution:** hard delete, anonymize, or archive per policy, inside bounded transactions.

**Observability:** eligible count, processed count, error count, batch duration, WAL/replication lag, held count, last run status.

**Safety stops:** dry-run reporting before deletion, maximum row caps per run, circuit breakers pausing under high load or unexpected anomalies.

**Audit:** record policy and outcome metadata without retaining sensitive deleted content unnecessarily.

### 35.1. Dry-Run to Inspect Candidates

~~~sql
SELECT
    COUNT(*) AS eligible_count,
    MIN(retention_until) AS oldest_eligible
FROM lifecycle_lab.customer_order
WHERE deleted_at IS NOT NULL
  AND retention_until <= statement_timestamp()
  AND legal_hold = FALSE;
~~~

This gives a simple baseline count, **not a guarantee every row will be purged**. Additional business and dependency checks still apply when required by policy.

### 35.2. Counting Actual Deletions per Batch

Example:

~~~sql
WITH candidates AS (
    SELECT order_id
    FROM lifecycle_lab.customer_order
    WHERE deleted_at IS NOT NULL
      AND retention_until <= statement_timestamp()
      AND legal_hold = FALSE
    ORDER BY retention_until, order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
),
deleted AS (
    DELETE FROM lifecycle_lab.customer_order AS o
    USING candidates AS c
    WHERE o.order_id = c.order_id
    RETURNING o.order_id
)
SELECT COUNT(*) AS removed_in_this_batch
FROM deleted;
~~~

The job loops over small committed batches under application control—never running unbounded tight loops when the database is under heavy load.

### 35.3. Why Separate Selection Logic from Execution Logic?

If an operator sees 100,000 eligible rows in a report yet the job deletes 99,990, they must be able to explain the remaining 10 rows:

- A legal hold was just applied.
- Another operation held a row lock.
- A foreign-key/constraint blocked deletion.
- Policy changed mid-run.
- A worker encountered an error.
- A concurrent transaction updated the row's state.

You need diagnostics to explain discrepancies rather than tweaking SQL blindly until every row disappears.

## 36. Hands-On Lab: Testing Soft Delete and Restore

You can step through these queries on the demo data. **These steps show independent branches**—not every step will succeed if earlier tests already added duplicate emails or deleted rows.

### Step 1 — Inspect Initial State

~~~sql
SELECT customer_id, email, deleted_at
FROM lifecycle_lab.customer
ORDER BY customer_id;
~~~

### Step 2 — Soft-Delete Customer 102

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = statement_timestamp(),
    retention_until = statement_timestamp() + INTERVAL '90 days',
    deleted_by = 'operator:training',
    deletion_reason = 'user_requested',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NULL
RETURNING customer_id, deleted_at;
~~~

### Step 3 — Compare Unfiltered vs. Filtered Queries

~~~sql
SELECT COUNT(*) AS all_customers
FROM lifecycle_lab.customer;

SELECT COUNT(*) AS live_customers
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL;
~~~

Assuming no other inserts or deletes occurred, the counts are **3** and **2** respectively.

### Step 4 — Verify Order Foreign Key Remains Intact

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    c.deleted_at
FROM lifecycle_lab.customer_order AS o
JOIN lifecycle_lab.customer AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 102;
~~~

Order 1003 still references customer 102.

### Step 5 — Restore When No Duplicate Email Exists

~~~sql
UPDATE lifecycle_lab.customer
SET
    deleted_at = NULL,
    deleted_by = NULL,
    deletion_reason = NULL,
    retention_until = NULL,
    account_status = 'suspended',
    updated_at = statement_timestamp()
WHERE customer_id = 102
  AND deleted_at IS NOT NULL
RETURNING customer_id, email, account_status;
~~~

This restores database columns; downstream caches or search indexes must be resynchronized via their own workflows if they already processed the deletion.

### Step 6 — Test Idempotency

Run the conditional restore `UPDATE` again. It returns 0 rows because `deleted_at` is already `NULL`.

### Step 7 — Inspect EXPLAIN

~~~sql
EXPLAIN
SELECT customer_id, email
FROM lifecycle_lab.customer
WHERE deleted_at IS NULL
  AND lower(email) = lower('an@example.test');
~~~

On tiny tables, PostgreSQL often chooses a sequential scan. The key lesson is that partial indexes are eligible when query predicates match, not forced unconditionally.

### Step 8 — Test Restore Conflict in a Separate Transaction

In the demo environment, soft-delete 102, insert 104 with the equivalent email, and then attempt to restore 102. Expect a unique violation. If testing inside a transaction, run `ROLLBACK` before issuing further queries. **Never run these tests on real data.**

## 37. Validating State with Constraints and CHECK

In the sample DDL we defined:

~~~sql
CONSTRAINT chk_customer_delete_metadata
CHECK (
    (
        deleted_at IS NULL
        AND deleted_by IS NULL
        AND deletion_reason IS NULL
        AND retention_until IS NULL
    )
    OR (
        deleted_at IS NOT NULL
        AND retention_until IS NOT NULL
        AND retention_until >= deleted_at
    )
)
~~~

This prevents invalid combinations such as:

- Not soft-deleted yet carrying purge retention metadata.
- Having `deleted_at` while missing `retention_until`.
- Having `retention_until` earlier than `deleted_at`.

However, it **does not guarantee full business correctness**:

- Does not prove the 90-day policy was computed properly.
- Does not prove the actor was authorized to delete.
- Does not check related tables sharing the lifecycle.
- Does not enforce preservation holds.
- Does not track historical restore counts.

Constraints guard **SQL-expressible data invariants**. Workflow logic and external decisions need complementary mechanisms.

### 37.1. PostgreSQL CHECK and NULL Values

In PostgreSQL, a `CHECK` constraint passes when the expression evaluates to `TRUE` or `UNKNOWN`/`NULL`; only `FALSE` fails. When constraining nullable columns, account for SQL's three-valued logic using `IS NULL`, `IS NOT NULL`, or `NOT NULL` explicitly.

Never assume:

~~~sql
CHECK (deleted_at <= retention_until)
~~~

automatically requires `retention_until` to be populated when `deleted_at` is non-null. If `retention_until` is `NULL`, the comparison yields `UNKNOWN` and passes `CHECK`.

## 38. Policy Consistency Across Multiple Systems

A deletion workflow often spans many systems:

~~~text
User requests deletion
       |
       v
PostgreSQL customer.deleted_at
       |
       +--> Cache invalidation
       +--> Search index delete/update
       +--> Analytics suppression
       +--> Object storage / file attachments
       +--> Notification service
       +--> Audit + retention decision
       |
       v
Retention deadline reached
       |
       +--> PostgreSQL hard delete / anonymize
       +--> Archive and downstream systems
       +--> Backup retention and DR handling
~~~

These updates rarely sit inside **one single transaction**. Use event IDs, idempotent consumers, outboxes, retries, dead-letter queues, and reconciliation where needed.

### 38.1. Distinguishing "Deleted in UI" from "Deleted Everywhere"

Define distinct reporting states:

- **Hidden from normal UI:** excluded from standard queries.
- **Soft deleted:** still present in the database with a tombstone.
- **Purge pending:** eligible or queued for deletion.
- **Purged from live system:** hard-deleted or anonymized in the primary database.
- **Propagation pending/completed:** sync status across external systems.
- **Backup expiry pending:** pre-deletion backups following their own retention window.

Never report "data has been erased from all copies" right after running `UPDATE deleted_at`.

## 39. Designing Retention Monitoring Metrics

Track operational metrics:

| Metric | Meaning |
|---|---|
| `live_rows` | Rows not soft-deleted |
| `soft_deleted_rows` | Rows with `deleted_at` set |
| `eligible_purge_rows` | Rows past minimum policy deadline |
| `held_rows` | Rows currently under hold |
| `purge_batch_count` | Rows actually removed per batch |
| `purge_failure_count` | Failed purge job runs |
| `oldest_overdue_age` | Longest delay past purge eligibility |
| `WAL_generated` | WAL write pressure from purges |
| `replication_lag` | Replica delay during purge runs |
| `vacuum_progress` | Dead tuple cleanup progress |

Example SQL:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE deleted_at IS NULL
    ) AS live_rows,

    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
    ) AS soft_deleted_rows,

    COUNT(*) FILTER (
        WHERE deleted_at IS NOT NULL
          AND retention_until <= statement_timestamp()
          AND legal_hold = FALSE
    ) AS eligible_purge_rows,

    COUNT(*) FILTER (
        WHERE legal_hold = TRUE
    ) AS held_rows
FROM lifecycle_lab.customer;
~~~

On massive tables, full-table `COUNT(*)` queries are expensive; avoid polling them too frequently just for dashboards. Use summary counters, sampling, or worker metrics depending on precision needs.

### 39.1. Tie Alerts to Actionable Decisions

Examples:

- Purge job has not succeeded for several days.
- Overdue purge backlog keeps growing.
- Replication lag spikes after purge batches.
- High FK failure rate during purge.
- A policy update suddenly spikes candidate counts abnormally.
- Backup/restore drills fail data-protection checks.

Do not measure deleted row counts alone. **A job deleting 0 rows can be healthy** when zero candidates exist, or broken if thousands of rows are overdue. Always compare against data state and policy.

## 40. Common Mistakes

### Mistake 1 — Treating Soft Delete as Hard Delete

Data remains in tables, backups, and downstream systems.

**Fix:** use accurate terminology and build purge/anonymization pipelines when required.

### Mistake 2 — Forgetting `WHERE deleted_at IS NULL`

Queries accidentally expose hidden records.

**Fix:** enforce repository/view/query conventions, test deleted-row exclusion, and lock down permissions.

### Mistake 3 — Using Table-Wide `UNIQUE(email)` While Allowing Reuse

Soft-deleted rows still block the old email.

**Fix:** use a partial unique index aligned with policy and handle restore conflicts.

### Mistake 4 — Using a Partial Unique Index Without Planning Restores

Restores fail once an identifier has been reused.

**Fix:** define identifier reuse windows and conflict resolution workflows.

### Mistake 5 — Believing `ON DELETE CASCADE` Handles Soft Delete

`ON DELETE CASCADE` applies to hard `DELETE`, never to updating `deleted_at`.

**Fix:** implement explicit lifecycle rules across related tables.

### Mistake 6 — Mechanically Soft-Deleting Every Child Record

Orders often have different retention requirements than user accounts.

**Fix:** model lifecycles per entity type, especially financial/transactional records.

### Mistake 7 — Resetting `deleted_at` on Retried Requests

Retries keep pushing out retention deadlines.

**Fix:** make updates conditional on `deleted_at IS NULL` and use idempotency.

### Mistake 8 — Using `is_deleted` Without Any Timestamp

Impossible to tell when a record became eligible for purge.

**Fix:** store `deleted_at` and supporting metadata whenever timing/auditing matters.

### Mistake 9 — Purging by Expiration While Ignoring Holds

Protected records get deleted improperly.

**Fix:** track policy versions, hold workflows, locking coordination, and pre-purge checks.

### Mistake 10 — Deleting Millions of Rows in One Transaction

Spikes WAL, bloat, locks, autovacuum load, and replication lag.

**Fix:** use small batches, load monitoring, circuit breakers, and rehearsals.

### Mistake 11 — Assuming `VACUUM` Purges Rows with `deleted_at`

`VACUUM` knows nothing about application soft-delete semantics.

**Fix:** run explicit SQL hard-delete jobs; `VACUUM` cleans dead MVCC tuple versions.

### Mistake 12 — Dropping Partitions Purely by Calendar Month

A partition may still hold records under legal hold or longer retention.

**Fix:** verify every row in the partition is eligible before detaching/dropping.

### Mistake 13 — Storing Full Copies of Sensitive PII in Audit Tables

Defeats data erasure goals because audit logs retain copies.

**Fix:** minimize audit payloads, define separate audit retention, and restrict access.

### Mistake 14 — Forgetting Caches, Search Indexes, and Analytics

Database shows soft-deleted while search still returns the profile.

**Fix:** use outbox/events, retries, reconciliation, and propagation lag monitoring.

### Mistake 15 — Purging Live Tables While Ignoring Backups

Data survives in snapshots, WAL archives, or older restores.

**Fix:** align backup retention and DR policies with data erasure requirements.

### Mistake 16 — Using Soft Delete as a Substitute for SQL Permissions

Users with `SELECT` on base tables can still read tombstones.

**Fix:** configure roles, `GRANT`s, views, or RLS as appropriate—never rely solely on UI filters.

### Mistake 17 — Not Synchronizing Legal Holds Against Concurrent Purges

A purge worker reads stale state right as a hold is added.

**Fix:** coordinate holds and purges via transactions and consistent locking, not a lone flag read.

### Mistake 18 — Running Purge Jobs with Over-Privileged Accounts

A bug could delete the wrong table or cross tenant boundaries.

**Fix:** use dedicated least-privilege roles, conditional statements, audit logging, and strict scope limits.

## 41. Integrated Design Scenario

Suppose an e-commerce platform requires:

- Customers can close their own accounts.
- Account restoration is allowed within a defined grace period.
- Fulfilled orders must be retained under transaction policy.
- Emails may be reused after an old account is soft-deleted.
- Search must immediately stop showing closed profiles.
- Certain accounts may be placed under legal hold.
- Nightly purges must not degrade latency for live transactions.

### 41.1. Unsafe Design

~~~text
User clicks Delete
    -> UPDATE customer SET is_deleted = true
    -> Filter missing on some queries
    -> No retention deadline
    -> Job DELETEs everything with is_deleted = true
~~~

Risks:

- UI or native queries leak deleted rows.
- No way to tell when rows become purge-eligible.
- Holds are ignored.
- Child orders cause FK errors or get wiped by reckless cascades.
- No audit trail or controlled restoration.
- Stale caches and search indexes remain.
- Backup retention is unaccounted for.

### 41.2. Controlled Design

~~~text
[Account closure request]
          |
          v
[Authorize / check state]
          |
          v
[PostgreSQL transaction]
  - set deleted_at, actor, reason
  - compute retention_until
  - update same-lifecycle objects
  - write outbox and audit metadata
          |
          v
[Commit]
          |
          +----> Update search/cache via worker
          |
          +----> Allow restore per policy
          |
          v
[Retention deadline reached]
          |
          +----> Check holds
          +----> Check child data and policy
          +----> Archive / anonymize if required
          |
          v
[Batched purge + audit]
          |
          v
[Reconcile database and downstream systems]
~~~

To resolve email collisions on restore, decide whether emails are locked during the grace period after soft delete. If immediate reuse is allowed, returning users may have to provide a new email upon restoration.

For fulfilled orders, policy may retain transaction summaries while stripping PII. Clarifying this model **before deleting data** is far easier than retrofitting a database after years in production.

## 42. Practice Exercises

### Exercise 1 — Choosing Deletion Type

A post moves to Trash for 14 days so authors can restore it. Should you soft-delete or hard-delete immediately?

**Hint:** soft-delete with a timestamp and purge anchor, then hard-delete afterward if policy allows.

### Exercise 2 — Querying Only Live Records

Write SQL returning customers who are neither soft-deleted nor suspended.

**Hint:** `WHERE deleted_at IS NULL AND account_status = 'active'`.

### Exercise 3 — Idempotency

Why can `UPDATE ... SET deleted_at = now() WHERE customer_id = 101` cause bugs when retried?

**Hint:** it overwrites `deleted_at` and extends retention deadlines. Add `AND deleted_at IS NULL`.

### Exercise 4 — Partial Unique Index

Create a unique index on `lower(email)` covering only non-deleted customers.

**Hint:** `CREATE UNIQUE INDEX ... ON ... (lower(email)) WHERE deleted_at IS NULL`.

### Exercise 5 — Restore Conflict

Customer 102 was soft-deleted, and customer 104 reused that email. Why can restoring 102 fail?

**Hint:** both rows would become live rows with identical `lower(email)` in the partial unique index.

### Exercise 6 — Foreign Keys

When soft-deleting a customer, why do their orders still satisfy the foreign key?

**Hint:** the customer row still exists; only a timestamp column changed.

### Exercise 7 — Retention Across Two Data Categories

Accounts expire after 90 days, while fulfilled orders must stay longer per policy. Should you hard-delete the customer and all their orders right at 90 days?

**Hint:** not by default. Respect order retention, references, and anonymization/PII-separation options.

### Exercise 8 — Legal Hold

Write the minimal SQL condition selecting customers who are soft-deleted, past retention, and not under `legal_hold`.

**Hint:** `deleted_at IS NOT NULL AND retention_until <= now() AND legal_hold = FALSE`.

### Exercise 9 — Auditing

Why is a `deleted_by` column on `customer` insufficient once a record is deleted, restored, and deleted again?

**Hint:** a single column cannot store multi-step transition history; use an event/audit table with its own policy.

### Exercise 10 — Batched Purge

Explain the purpose of `LIMIT 100 FOR UPDATE SKIP LOCKED` in the candidate-selection CTE.

**Hint:** bounds transaction size and avoids worker lock contention; locked rows are skipped and retried later.

### Exercise 11 — VACUUM

If a row has `deleted_at IS NOT NULL` without having run `DELETE`, does `VACUUM` remove it from business data?

**Hint:** no; under MVCC it is still a current live tuple.

### Exercise 12 — Backups

Does hard-deleting a row from the primary database guarantee yesterday's backup no longer holds that row?

**Hint:** no. Backups reflect earlier points in time and follow separate retention lifecycles.

### Exercise 13 — RLS

If the application filters `deleted_at IS NULL` in UI queries, can an account with `SELECT` on the base table still read soft-deleted rows?

**Hint:** yes. Application/UI filters are not database security policies.

### Exercise 14 — Partition Retention

January's partition has 99,999 expired rows and 1 row under legal hold. Can you drop the entire partition?

**Hint:** no, unless the exception row is handled via an approved process that preserves the hold.

### Exercise 15 — CHECK and NULL Trap

Why doesn't `CHECK (retention_until >= deleted_at)` guarantee `retention_until` is always populated when `deleted_at` is set?

**Hint:** comparing against `NULL` yields `UNKNOWN`, which passes `CHECK`.

### Exercise 16 — Multi-Tenancy

An email may exist in both tenant A and tenant B, yet each tenant allows only one live account per email. Describe the right partial unique index.

**Hint:** key on `(tenant_id, lower(email))` with predicate `WHERE deleted_at IS NULL`.

### Exercise 17 — Failing Purge Job

A purge worker hits repeated FK errors. Should you change the table to `ON DELETE CASCADE` and rerun it?

**Hint:** do not rush to do that. Inspect child lifecycles, retention rules, holds, and data that must remain intact.

### Exercise 18 — External System Sync

PostgreSQL committed a soft delete, yet the search index still returns the profile. How do you make synchronization reliable?

**Hint:** use an outbox/events with IDs, idempotent consumers, retries, and reconciliation.

### Exercise 19 — Restore Eligibility

A profile is past its restore deadline yet hasn't been purged yet. Should restore be allowed simply because the row still exists?

**Hint:** not by default; restore eligibility follows business policy, not mere physical row survival.

### Exercise 20 — Runbook Design

List the steps to safely operate nightly production purges without accidental data loss.

**Hint:** dry-runs, policy/hold/dependency checks, small batches, least-privilege role, auditing, WAL/replica monitoring, circuit breakers, and drills.

## 43. Key Takeaways

- **Soft delete = status update**, not physical removal; `deleted_at IS NULL` commonly marks live records.
- **Hard delete = `DELETE`**, yet MVCC, WAL, `VACUUM`, and backups follow independent retention lifecycles.
- **Business status differs from deletion status:** `cancelled` orders or `suspended` accounts are not automatically soft-deleted.
- **Partial unique indexes** enforce uniqueness only across live rows; plan for restore collisions and identifier reuse rules.
- **Soft delete never fires `ON DELETE CASCADE`**; design cross-table lifecycles deliberately.
- **Retention policies** define what to keep, for how long, and what action follows expiration; `retention_until` is only one piece of the model.
- **Legal holds and dependencies** can block purges even past normal expiration dates.
- **Batched purges** control transaction duration, WAL, locks, and vacuum/replication impact, requiring strict guards and monitoring.
- **RLS, views, and ORM filters** help hide rows yet never replace retention, security, or recovery policies.
- **Archiving is not erasure**; backups, replicas, CDC streams, search indexes, and exports have their own lifecycles.
- **Audits and outboxes** ensure traceability and reliable event delivery, yet require their own retention and security controls.
- **Rehearsals and reconciliation** matter far more than a cron job reporting "succeeded".

Good soft-delete design goes far beyond adding a `deleted_at` column. It explicitly defines **when a record disappears from view, who may restore it, which dependent records must remain, what blocks hard deletion, when purging is permitted, and how compliance is verified across PostgreSQL and connected systems**. Designing those boundaries right into the schema keeps data lifecycles controllable and prevents hard-to-recover incidents down the road.
