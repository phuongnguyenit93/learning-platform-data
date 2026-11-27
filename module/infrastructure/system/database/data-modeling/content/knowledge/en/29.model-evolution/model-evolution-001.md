# Distinguishing Rename, Structural Change, and Semantic Change

## 1. Why Do Three Similar-Looking Changes Carry Very Different Risks?

A request to "rename column `customer_name` to `display_name`" may be a pure rename. A request to "extract the `phone` column into a contact table" is a structural change and may change the relationship from one-to-one to one-to-many. A request that "`PAID` from now on only means funds have been confirmed by the payment provider" is a **business semantic change**, even though the column name and data type do not change.

In data modeling, **you cannot judge migration safety just by looking at DDL**. Two identical `ALTER TABLE` statements can have completely different impacts if constraints and data contracts differ; conversely, a semantic change may not touch the physical schema at all yet corrupt financial reports.

For example, a sales platform has:

- `Customer`: `customer_id`, `customer_name`, `phone_e164`, `segment`.
- `Order`: `order_id`, `customer_id`, `amount_minor`, `status`.
- `Payment`: `payment_attempt_id`, confirmation result from the provider.

The engineering team receives three requests:

1. "Rename `customer_name` to `display_name`; it is still the name used for display."
2. "A customer can have multiple phone numbers; move phone numbers to a contact table."
3. "From now on `status = PAID` is only recorded when the payment provider confirms capture, rather than when the collection request is sent."

The three requests require three different strategies:

| Primary Classification | What Changes | Does Physical Schema Necessarily Change? | Main Risk |
| --- | --- | --- | --- |
| **Rename** | How a concept is named while keeping the same meaning. | Not necessarily: may only change API/semantic layer labels. | Breaking consumers, views, queries, mappings, serialization. |
| **Structural change** | How tables/documents are split, relationships, cardinality, keys, types, and data placement. | Usually yes. | Losing or multiplying rows, breaking FK/unique constraints, incomplete backfill, changing grain. |
| **Semantic change** | What a value/event/status asserts about the business. | Not necessarily. | Old and new data interpreted as having the same meaning, leading to wrong decisions/KPIs. |

**A single change can belong to multiple categories.** Changing `amount_minor` to `net_amount_minor` looks like a rename on the surface, but if `amount_minor` previously meant the amount *before* refunds while `net_amount_minor` means the amount *after* refunds, that is a **semantic change** and may require a **structural change** to record individual refund transactions.

This lesson focuses on how to classify, design schemas, and roll out verifiable model evolution in relational databases, while comparing with document, graph, and analytical models.

## 2. Three Layers to Distinguish: Name, Representation, and Semantic Contract

Every data field should be examined across at least three layers:

1. **Name and language:** `display_name`, `customer_name`, "Display Name" in the UI; including logical name, physical name, and name in API/event contracts.
2. **Representation:** `TEXT` column or JSON property, separate table or embedded document, single row or multiple rows, keys/FKs, storage unit.
3. **Semantics:** which entity this name belongs to, at what point in time it remains valid, who has authority to confirm it, what a missing value means, and which constraints must hold.

For example, pricing has fields that look deceptively similar:

| Name | Possible Definition | Owner |
| --- | --- | --- |
| `current_list_price_minor` | Current list price in the Catalog. | Catalog. |
| `agreed_unit_price_minor` | Unit price locked at order placement time. | Ordering. |
| `captured_amount_minor` | Amount confirmed as captured by the provider. | Payment. |
| `refunded_amount_minor` | Amount confirmed as refunded. | Payment. |
| `net_cash_minor` | Total captured minus total refunded within the defined scope/time. | Finance/Analytics based on Payment. |

All five may use `BIGINT` and the smallest currency unit, yet **they are not five names for one field**. Renaming a field when doing so changes its owner, source of truth, or calculation formula is no longer a pure rename.

A good **data contract** must include: identifier, grain, type and unit, key scope, nullability, enum, effective time, default value, owner, update rules, security/retention, and meaning for consumers.

## 3. Pure Rename: Conditions to Assert "No Change in Meaning"

A pure rename is valid only when **all invariants and meanings of the data remain unchanged**:

- Same entity, same business key and tenant scope.
- Same grain: one row still represents the same event/object.
- Same value type and unit, without changing normalization or rounding rules.
- Same interpretation of `NULL`, empty values, enums, and defaults.
- Same authoritative source and confirmation timing.
- Same lifecycle and historical meaning.

For example, changing `customer_name` to `display_name` can be a rename if both refer to *the display name owned by Customer Identity*. However, if `customer_name` was previously the **legal name on invoices**, while `display_name` is a **user-editable nickname**, this change is **not pure**: you must separate the two concepts, edit permissions, and usage contracts.

### Display Name, API Name, and Column Name Can Differ

You do not have to rename every layer at once. A model can use:

~~~text
Database column: customer_name
Domain property: displayName
REST API field: display_name
UI label: Display Name
~~~

If the meaning is the same and the mapping is documented, differing names are not a bug. Renaming **in code or UI** may not require DDL. Renaming a physical column can reduce technical debt, but creates risks for SQL consumers, stored procedures, exports, materialized views, CDC, and ORM mappings.

### Dangerous Renames Even When Data Is Unchanged

~~~sql
ALTER TABLE customer_account
RENAME COLUMN customer_name TO display_name;
~~~

PostgreSQL performs the column metadata change without copying all values into a new column, **but that does not make it non-disruptive**. The DDL requires the appropriate lock and can wait on or block other queries; applications, raw SQL, and consumers depending on the old column name can break on deployment.

Some database-managed dependencies may update via the catalog, but **SQL text in applications, queries stored elsewhere, and message contracts do not change automatically**. Therefore, in systems with multiple application versions running concurrently, a direct `RENAME COLUMN` is usually not the safest compatibility strategy.

## 4. Structural Change: Changing How Data Is Represented and Linked

A structural change is not merely changing a data type; it can alter **row counts, table boundaries, relationships, and constraints**.

| Structural Change | Example | Question That Must Be Answered |
| --- | --- | --- |
| **Split a column into multiple columns** | `full_address` → `street`, `ward`, `city`. | Can all legacy data be split accurately? |
| **Merge columns** | `first_name` + `last_name` → `display_name`. | How are name order, culture, missing values, and whitespace handled? |
| **Split a table** | `customer.phone` → `customer_contact_method`. | Cardinality changes from one number to many; what are the new keys/unique constraints? |
| **Merge tables** | `order_header` + `order_detail` → document. | What is the row/document grain, and is detail querying lost? |
| **Change type** | `VARCHAR` → enum/UUID, `INT` → `BIGINT`. | Can existing data convert safely within range? |
| **Change key** | `customer_email` as PK → surrogate `customer_id`. | How are FKs, external references, duplicates, and email lifecycle handled? |
| **Change cardinality** | One order has one coupon → multiple coupons. | Does the old unique constraint still hold? Is a many-to-many join table needed? |
| **Normalize/denormalize** | `order.customer_name` extracted to a dimension. | Does the snapshotted name on the order still need to be kept? |
| **Change partitioning/indexing** | Partition `orders` by month. | How do cross-partition uniqueness, routing keys, and query pruning behave? |
| **Change ownership location** | `payment_status` moved from Ordering to Payment. | Is this still a structural change, or also a change in source and meaning? |

A structural change **does not necessarily change meaning** if the new data is simply an equivalent representation and the mapping is lossless per requirements. In practice, however, many migrations encounter missing data, unstable keys, ambiguous legacy rules, or cardinality changes that make automated mapping **impossible**.

### Lossless vs. Lossy Mapping

Suppose `full_name = "Nguyễn Văn An"`. You cannot reliably split it into `first_name = An` and `last_name = Nguyễn Văn` across all cultures and all data. If the original name must be preserved, keep `full_name` intact or store components only when confirmed by an authoritative source.

Similarly, from a single `phone` column you cannot infer how many other phone numbers a customer had in history. Migrating to a multi-contact table can create **at most one known contact from the old source**, not reconstruct contacts that were never stored.

**Rule:** for a structural migration, you must define the old → new data mapping, the boundary of recoverable information, and preservation checks before dropping the old structure.

## 5. Semantic Change: Dangerous Because the Schema May Still Be Completely Valid

A semantic change occurs when the interpretation of a value **before and after the change is no longer equivalent**.

Example `order_status = 'PAID'`:

- **Old rule:** assign `PAID` when the application sends a collection command and receives an "accepted" response.
- **New rule:** assign `PAID` only after the provider confirms a successful capture.

Both values have the **same string**, yet one describes *a request accepted* and the other describes *funds captured*. If a dashboard computes revenue using `COUNT(status = 'PAID')` across multiple periods, the results can be wrong even though the query runs cleanly.

Other semantic changes:

| Value/Field | Old Interpretation | New Interpretation | Why It Is Not Just a Rename |
| --- | --- | --- | --- |
| `amount` | Amount before discount. | Amount after discount. | Different formula and evidence source. |
| `amount_minor` | Minor unit of VND. | Major unit of VND. | Changing the unit breaks calculations even though numeric types remain valid. |
| `active` | Entity is not soft-deleted. | Entity is currently allowed to transact. | Display state differs from business eligibility. |
| `order_date` | When the system created the order. | When the customer confirmed the purchase. | Daily reporting groupings will change. |
| `customer_id` | Login account. | Legal buyer / merged identity. | Different entity and reference key. |
| `gross_revenue` | Value of placed orders. | Value of recognized invoices. | Different accounting cutoff and cancellation/refund handling. |
| `delivery_done` | Driver tapped "delivered". | Recipient confirmed successful delivery. | Requires different evidence. |
| `quantity` | Number of units ordered. | Number of units delivered. | Does not reflect the same business state. |

**Semantic compatibility** is a separate problem from **schema compatibility**. Two JSON versions with identical field names and types can *still be incompatible* in meaning.

### Do Not Change Historical Meaning via Default Assignment

If legacy records lack provider capture evidence, do not turn old `PAID` rows into the new `PaymentCaptured` state simply via:

~~~sql
-- DO NOT do this if historical PAID only meant collection was requested.
UPDATE orders
SET payment_state = 'CAPTURED'
WHERE status = 'PAID';
~~~

A proper plan must determine whether **provider confirmation IDs** can be traced back, which transactions are reconciled, which are unknown, and how data limitations are disclosed. Without sufficient evidence, preserve **LEGACY_REQUEST_ACCEPTED** or **UNKNOWN_CAPTURE_RESULT** per the agreed contract rather than fabricating financial outcomes.

## 6. One Change Can Belong to All Three Categories

Change categories are not mutually exclusive. Separate each layer so no risk is missed.

For example, a request to "replace `order.total` with `payment_summary.net_cash_minor`":

1. **Rename:** `total` → `net_cash_minor`.
2. **Structural change:** a single column on `orders` becomes a summary derived from multiple `payment_movement` rows for `CAPTURE`/`REFUND`.
3. **Semantic change:** "order value" becomes "net cash collected" as of a reconciliation point.

These three transformations cannot be safely deployed with a single `RENAME COLUMN`, because there is no one-to-one relationship between order total and cashflow: an order can be canceled, captured in multiple installments, partially refunded, or have transactions not yet confirmed by the provider.

### Quick Classification Table

| Diagnostic Question | If Answer Is Yes | Classification to Examine |
| --- | --- | --- |
| Does only the label change, with the same definition and grain? | Yes. | Rename. |
| Is data moved between tables/documents or are relationships added? | Yes. | Structural. |
| Do keys, cardinality, units, or types change? | Yes. | Structural; **possibly also semantic**. |
| Same old value, but now asserting something different? | Yes. | Semantic. |
| Does "who is authorized to decide/write the value" change? | Yes. | Semantic/ownership boundary. |
| Does the point in time when an event is considered to have occurred change? | Yes. | Semantic/temporal. |
| Can historical reports change even when underlying facts did not? | Yes. | Possibly semantic restatement or SCD policy. |
| Is there legacy data that cannot map accurately to the target? | Yes. | Lossy structural migration / semantic ambiguity. |

When concluding "pure rename," write down the **proof of unchanged meaning**, not just "the team said they are the same."

## 7. Grain, Business Keys, and Invariants Govern Evolvability

**Grain** answers what one row represents. **Business key** answers how that entity/event is identified within the business scope. **Invariant** answers what must always remain true.

These three matter more than table names.

### Key Rename or Identity Change?

Suppose `user_id` was previously the account ID, while the new requirement uses `customer_id`. If one customer can have multiple accounts, then `user_id` and `customer_id` are not equivalent. Renaming the key will merge entities incorrectly or corrupt relationships:

~~~text
UserAccount U-101 ----+
                      +---- Customer C-42
UserAccount U-202 ----+
~~~

You may need a `customer_account_membership` mapping table with effective time, verification source, and unique constraints. You cannot simply rename column `user_id` to `customer_id` and keep all values as if every account were a customer.

### Changing Cardinality Is a Structural Change and May Change Rules

A customer can have multiple phone numbers. Before:

~~~text
customer_account(customer_id, phone_e164)
~~~

After:

~~~text
customer_account(customer_id)
customer_contact_method(contact_id, customer_id, contact_type, value, ...)
~~~

Questions to clarify: what is the maximum number of numbers? Is there one **primary** number or multiple primaries by purpose? Can one number belong to two customers? Is a verified number distinct from a customer-entered number? Under what policy can numbers be deleted/restored?

Without defining invariants, the new data may satisfy FKs while breaking verification-code flows or leaking contact information.

### Do Not Break Fact Grain

Table `fact_order_line` has grain "one line item of an order"; table `fact_payment_movement` has grain "one confirmed capture/refund transaction". Joining the two tables directly on `order_id` can multiply rows when an order has three line items and two payments. A structural migration to an "aggregated orders" table must define the new grain and aggregation rules rather than blindly doing JOIN then SUM.

## 8. End-to-End Example: Same Customer, Three Types of Changes

Suppose a simplified v1 schema of a Customer Identity module:

~~~sql
CREATE TABLE customer_account (
    tenant_id       UUID NOT NULL,
    customer_id     UUID NOT NULL,
    customer_name   TEXT NOT NULL,
    phone_e164      TEXT,
    account_status  VARCHAR(20) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, customer_id)
);
~~~

Three requests:

**R1 — Rename:** `customer_name` → `display_name`, keeping the meaning "account display name", not legal name on official documents. Can use the expand–contract compatibility technique.

**R2 — Structural change:** `phone_e164` → `customer_contact_method` table to support multiple numbers. The legacy number produces at most one known contact. Do not mark it verified by default.

**R3 — Semantic change:** the business wants `account_status = 'ACTIVE'` only when **identity is verified and transactions are permitted**, whereas legacy data used `ACTIVE` to mean "account not closed". The new status must rely on verification evidence, not merely renaming enum values.

The three requests may ship in the same product-level release, but **they should have separate migration and verification plans**. Combining everything into one script risks having phone-backfill errors mask status-semantic bugs.

## 9. Expand–Migrate–Contract Process for Compatible Renames

**Expand–Migrate–Contract** (also known as expand/contract) is a rollout path that allows two application versions to operate side by side during the transition window.

~~~mermaid
flowchart LR
    A["v1: customer_name"] --> B["EXPAND: add display_name, readers support both names"]
    B --> C["MIGRATE: backfill, one authoritative write path updates both"]
    C --> D["CUTOVER: readers use display_name, verify"]
    D --> E["CONTRACT: remove old code, drop customer_name once no dependencies remain"]
~~~

### Phase A — Expand: Add the New Field Without Removing the Old One

~~~sql
ALTER TABLE customer_account
ADD COLUMN display_name TEXT;
~~~

In the initial phase, `display_name` is **nullable** so existing rows are not assumed to already contain the new data. Simply creating the column does not prove the application has migrated; code/mappers, APIs, and compatibility tests must also be updated.

### Phase B — Migrating Reads/Writes

While both columns exist, the new application can read:

~~~sql
SELECT tenant_id, customer_id,
       COALESCE(display_name, customer_name) AS display_name
FROM customer_account
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

`COALESCE` is valid here only because **both fields have been confirmed to share the same meaning** and `NULL` represents "not yet migrated". If an empty string carries a distinct business meaning, you must define a handling policy instead of treating empty string as `NULL`.

An **authoritative write path** temporarily updates both columns within the **same transaction/row**:

~~~sql
UPDATE customer_account
SET customer_name = :new_display_name,
    display_name  = :new_display_name,
    updated_at    = now()
WHERE tenant_id   = :tenant_id
  AND customer_id = :customer_id;
~~~

This is a **dual-column write in the same transaction**, distinct from **dual-write across two independent databases**. You must audit all legacy write paths: if service v1 keeps writing only `customer_name` while v2 writes only `display_name`, the two columns can diverge. Options include keeping a single writer/migration facade, backward compatibility in both versions, or tested forward synchronization.

### Phase C — Backfill Existing Data

~~~sql
-- Illustrative update logic; for large tables, batch and bound locks.
UPDATE customer_account
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

Under concurrent writes, you must define deployment ordering and guard against a job using a stale snapshot and overwriting newer updates. Enable dual-column writes **before** backfill or use change capture / guarded cutover. With millions of rows, running a single `UPDATE` can cause heavy WAL, bloat, lock waits, and replica lag; batch with checkpoints and rate/load limits.

### Phase D — Verify and Tighten Constraints

Check remaining missing/mismatched rows:

~~~sql
SELECT COUNT(*) AS mismatched_rows
FROM customer_account
WHERE display_name IS DISTINCT FROM customer_name;
~~~

During the phase where both must match, the expected result is 0 at a **consistent snapshot**. If discrepancies appear, triage faulty write paths, contract-violating data, or incomplete backfill.

Once data is complete and all writers guarantee the new column is non-null, you can tighten constraints:

~~~sql
ALTER TABLE customer_account
ADD CONSTRAINT customer_display_name_present
CHECK (display_name IS NOT NULL) NOT VALID;

ALTER TABLE customer_account
VALIDATE CONSTRAINT customer_display_name_present;
~~~

`NOT VALID` on a `CHECK` constraint lets you add the constraint without immediately scanning all existing rows, while **new/updated writes must still satisfy it**. Deploy compatible writers first, then validate the constraint, and consider `SET NOT NULL` based on PostgreSQL version capabilities, locking, and migration plan.

### Phase E — Contract: Drop the Old Field Once No Consumers Remain

Only after all readers/writers, jobs, queries, exports, APIs, and CDC consumers have no remaining dependency should you consider:

~~~sql
ALTER TABLE customer_account
DROP COLUMN customer_name;
~~~

Dropping a column is **hard to reverse** without backups or source data to restore from, even if the data once lived in both columns. Define a cutover point, verification, rollback plan, and observation window before cleanup.

**Do not keep both columns forever:** the compatibility phase is a bounded transition step. Leaving both in place long-term without a canonical column creates two data sources that can drift apart.

## 10. Structural Change Example: From Phone on Customer to Contact Table

The new requirement is that each customer can use **multiple contact methods**. This is a change in cardinality and constraints; it cannot be solved by renaming `phone_e164` → `contact_value`.

### Target Schema

~~~sql
CREATE TABLE customer_contact_method (
    contact_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    customer_id      UUID NOT NULL,
    contact_type     VARCHAR(20) NOT NULL,
    contact_value    TEXT NOT NULL,
    is_primary       BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at      TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    origin           VARCHAR(30) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer_account (tenant_id, customer_id),
    CHECK (contact_type IN ('PHONE', 'EMAIL')),
    CHECK (btrim(contact_value) <> ''),
    UNIQUE (tenant_id, customer_id, contact_type, contact_value)
);

-- At most one active primary phone number per customer.
CREATE UNIQUE INDEX ux_one_live_primary_phone
ON customer_contact_method (tenant_id, customer_id)
WHERE contact_type = 'PHONE'
  AND is_primary = TRUE
  AND revoked_at IS NULL;
~~~

**Limitations of the illustrative schema:**

- `contact_value` in a multi-type table needs separate validators/normalization for `PHONE` and `EMAIL`. `CHECK (btrim(...) <> '')` alone does not prove a phone number is well-formed or an email is deliverable.
- `verified_at` is populated only when verification evidence exists. Data imported from the legacy column must never be marked verified automatically.
- `is_primary` and `revoked_at` enforce **at most one** active primary phone. Nothing in this example enforces **at least one** primary phone; if the business requires it, appropriate transaction/constraint logic is needed.
- The unique constraint on `(tenant_id, customer_id, contact_type, contact_value)` disallows two records with the same value for a customer even if one is revoked; that is a **lifecycle choice**. To allow re-registering the same number and keeping multiple verification cycles, a different history/grain design is needed.
- Whether one phone number can belong to multiple customers is a business decision; this schema does not enforce global uniqueness.

### Backfill from Legacy Data

Assume `phone_e164` in the source has been format-verified or cleaned. There is no proof of phone ownership verification, so `verified_at` must be `NULL`.

~~~sql
INSERT INTO customer_contact_method (
    tenant_id, customer_id, contact_type, contact_value,
    is_primary, verified_at, origin
)
SELECT tenant_id, customer_id, 'PHONE', phone_e164,
       TRUE, NULL, 'LEGACY_IMPORT'
FROM customer_account
WHERE phone_e164 IS NOT NULL
  AND btrim(phone_e164) <> ''
ON CONFLICT (tenant_id, customer_id, contact_type, contact_value)
DO NOTHING;
~~~

This backfill **assumes** source data can serve as a provisional contact number and only one migration writer is active. If another primary `PHONE` has already been created beforehand, the partial unique index can fail the transaction; you should **not** blindly drop the constraint. Coordinate ordering, lock per Customer, or route conflicts into a reconciliation workflow.

If a source number fails E.164 validation, **quarantine/retain the raw value with restricted permissions** and normalize only from trusted evidence—do not fabricate valid numbers. If the source stored only one number, you cannot reconstruct a customer's history of multiple numbers.

### Cardinality Comparison and Verification

- Before migration: `customer_account` has 0 or 1 `phone_e164` per customer.
- After migration: `customer_contact_method` has 0..N contact methods per customer.
- During transition: a legacy phone record can produce **at most one** `LEGACY_IMPORT` PHONE contact per business key.
- A query joining Customer → Contacts can now return multiple rows per Customer; reports doing `COUNT(customers)` or joining Order can suffer row multiplication.

~~~sql
-- Count customers with a legacy phone that has no corresponding contact yet.
SELECT COUNT(*) AS missing_legacy_contacts
FROM customer_account c
WHERE c.phone_e164 IS NOT NULL
  AND btrim(c.phone_e164) <> ''
  AND NOT EXISTS (
      SELECT 1
      FROM customer_contact_method m
      WHERE m.tenant_id = c.tenant_id
        AND m.customer_id = c.customer_id
        AND m.contact_type = 'PHONE'
        AND m.contact_value = c.phone_e164
  );
~~~

The count should reach 0 **after backfill completes and at a consistent snapshot**. That does not prove the numbers are verified or that every active contact can be synced back into a single column; that is the new boundary of a 1:N relationship.

### Write-Path Transition Strategy

Once the Contact table becomes the source of truth for multiple numbers, applications should no longer arbitrarily mutate `customer_account.phone_e164`. During the compatibility window, if a "primary number" must still be exposed to legacy consumers, treat it as a **projection** computed from Contact under a single policy; do not treat both tables as independent masters.

In the new contact model, soft-deleting or revoking a number must carry business meaning, authorization, timestamps, and downstream notifications. Simply overwriting the old table with the most recently received number is insufficient for managing multiple numbers and verification states.

## 11. Changing Status Semantics: Rewrite the Domain Model Before Editing Columns

Returning to `account_status = ACTIVE`: the old rule "not closed" is not synonymous with the new rule "verified and permitted to transact".

A clearer design separates orthogonal dimensions:

| Field | Illustrative Values | Meaning |
| --- | --- | --- |
| `lifecycle_status` | `OPEN`, `CLOSED` | Whether the account is active in its lifecycle or closed. |
| `verification_status` | `UNVERIFIED`, `VERIFIED`, `REJECTED` | Verification evidence under an approved process. |
| `access_status` | `ENABLED`, `SUSPENDED` | Whether feature access is currently allowed by policy or suspended. |
| `eligible_for_purchase` (derived) | true/false | Composite rule combining lifecycle, verification, access, and other conditions. |

The new model may require multiple columns/tables (structural) because **a single legacy enum collapsed multiple semantic dimensions**. Most importantly, however, are **the semantics of each value and decision point**.

### Do Not Fabricate Historical Verification Status

If legacy customers only have `account_status = 'ACTIVE'`, you cannot migrate all of them to `verification_status = 'VERIFIED'`. You must:

1. Inventory prior verification sources (records, providers, authoritative audits), if any exist.
2. Classify customers with provable `VERIFIED`, `UNVERIFIED`, or `REJECTED` status.
3. Where evidence is missing, use `UNKNOWN_LEGACY` or an undetermined status per policy—never auto-fill "verified".
4. Explicitly define behavior for unknown accounts: allow read access? require re-verification before purchase? block sensitive operations?
5. Record the migration rule version and effective timestamp; users must understand the difference between **verified** and **grandfathered from the legacy era**.

### New State Transitions Must Not Rewrite History

For orders, `PAID` only upon provider capture confirmation is a new state transition rule. Historical records from the legacy system must be reconciled or retain their legacy classification. If capture confirmation arrives late, handle timestamps and status history appropriately; do not overwrite the order's `created_at` with the callback timestamp.

Changing a field's meaning may require **new domain events**, data migration, and versioned read models, not just editing an enum validation list.

## 12. Historical Data: "Known at the Time" Differs from "Currently Recognized Since Then"

Model evolution becomes especially complex when data involves both **valid time** and **recorded time**.

Example shipping-fee policy:

- March 01: the system knows the applicable fee is 20,000 VND.
- March 10: the business discovers the fee should have been 18,000 VND effective from March 01.
- March 10: a retroactive correction decision is recorded.

A report needs to answer two questions:

1. **On March 05, what fee did the system know?** 20,000 VND.
2. **Under the new decision, what fee applies to March 05?** 18,000 VND.

If you simply overwrite a Type 1 column, you lose the first answer. If you only store `valid_from/to` without recording when the system logged the correction, it is also hard to answer "what was known at that time".

| Mechanism | When Appropriate | Limitation |
| --- | --- | --- |
| **SCD Type 1** | Updating display values and intentionally re-bucketing all history. | Does not retain old values directly in the dimension. |
| **SCD Type 2 / valid-time** | Need to know which attributes were effective across time intervals. | A single time axis does not automatically capture full knowledge history. |
| **Bitemporal** | Need both business effective time and system recording time. | Higher schema, update, query, and constraint costs. |
| **Event/correction history** | Need to know events and evidenced correction decisions. | Readers must understand versions/events; replay alone does not guarantee complete context. |
| **Audit/CDC** | Need to trace storage operations and before/after changes. | Does not capture business semantics of events by default. |

**Do not treat `updated_at` as "having history".** Without other versioning info, it only indicates the most recent modification.

### Historical Facts Must Preserve Snapshotted Values

Catalog may update the current `list_price`, but `order_line.agreed_unit_price` on a finalized order must reflect the transaction document. If a migration renames a price column to a generic `price` and joins back to Catalog to compute past orders, the data loses its true historical meaning even though the schema stays valid.

## 13. Compatibility Is a Matrix Between Writers, Readers, and Legacy Data

When deploying a model change, there is always a window where writers and readers **run different versions**.

| Writer / Reader | Old Reader | New Reader |
| --- | --- | --- |
| **Old Writer** | Typically runs on the v1 contract. | New reader must read v1 or use an adapter. |
| **New Writer** | Needs writer backward compatibility with old readers, or parallel v1 support. | Must read v2 and apply new validation. |

To avoid terminology ambiguity:

- **New reader reading old writer's data:** commonly called **backward compatibility** in reader/writer terms.
- **Old reader reading new writer's data:** commonly called **forward compatibility**.
- **Full compatibility:** bidirectional under the specified constraints.

Different schema registries/frameworks have their own definitions and rules; check the specific tool in use rather than assuming every field addition is safe.

### Renaming in REST/GraphQL/JSON

JSON v1 example:

~~~json
{
  "customer_id": "CUS-42",
  "customer_name": "Nguyễn Vân"
}
~~~

JSON v2:

~~~json
{
  "customer_id": "CUS-42",
  "display_name": "Nguyễn Vân"
}
~~~

If old consumers **require** `customer_name`, removing it is a breaking change. A controlled transition emits both fields with the same meaning for a window, documents deprecation, and forbids new consumers from adopting the old field. However, you must ensure **both fields stay identical**, never drifting into two different values.

### Renaming or Changing Event Schemas

Immutable events written with `event_type + schema_version` must remain readable years later. An upcaster can transform the v1 `customer_name` representation into canonical `display_name` if the meaning has not changed.

~~~text
decode_v1(event):
  return CanonicalCustomerRenamed(
    display_name = event.payload.customer_name,
    original_event_id = event.event_id
  )
~~~

This is **pseudocode**, and it is valid only when the v1 event genuinely describes the same fact. An upcaster cannot turn `PaymentRequested` into `PaymentCaptured` by renaming alone without transaction confirmation.

### CDC Is a Contract Prone to Implicit Coupling

A consumer reading table CDC directly will see column names and types change even when business APIs do not. If CDC is used long-term for integration, manage schema contracts, cursors/checkpoints, permissions, and deprecation as a formal interface; in many cases, a **transactional outbox** publishing semantically stable integration events is preferable.

## 14. Table and Contract Changes: Never "Just One SQL Script"

A change spans multiple layers:

~~~mermaid
flowchart TD
    REQ["Business requirement & data definition"] --> MODEL["Logical model: entities, grain, keys, invariants"]
    MODEL --> DB["Physical schema: tables, columns, indexes, FKs"]
    DB --> WRITE["Writer / validation / transaction"]
    WRITE --> API["API, event, CDC contracts"]
    API --> CONS["Consumers, caches, read models, reports"]
    CONS --> QA["Reconciliation & monitoring"]
    QA -. "Detect drift / adjust" .-> MODEL
~~~

A complete migration plan must identify **every dependent**:

- ORM mappings, raw SQL, stored procedures/triggers, views/materialized views.
- In-flight migration scripts, data imports, and batch jobs.
- REST/GraphQL/gRPC, JSON/Avro/Protobuf events, Kafka topics, CDC.
- Caches, search indexes, analytical facts/dimensions, exports.
- Un-upgraded mobile/offline clients, partner integrations.
- Audits, backups, retention, and operational/debugging tools.

Even if a change is only a database rename, if a partner consumes a CSV export with header `customer_name`, it is still a contract change requiring governance. A column rename may leave values unchanged while requiring extensive reader updates.

### Establish a Single Source of Truth During Transition

While two representations coexist, specify:

- Which field/table is **authoritative** in the current phase?
- Which writers may mutate it, and is there a single write path or multiple?
- What mechanism synchronizes the derived representation?
- What criteria prove reads can safely switch over?
- How far back can we roll back once new data exists that the old model cannot represent?

Especially for a 1:1 → 1:N change, the legacy system cannot represent multiple phone numbers. Once consumers start writing **two contacts of the same type**, rolling back to a single `phone_e164` column is **no longer lossless**. Define the **rollback boundary** before enabling the new feature.

## 15. Online Migration: Large Data, Concurrent Writes, and Constraints

For large databases, a backfill is not merely a logical transformation—it is a **physical operation** affecting WAL, CPU, indexes, replication, and locks.

### Compatible Rollout Sequence

1. Audit data and invalid records: `NULL`s, unexpected characters, duplicate keys, orphan references.
2. **Expand**: add new structures without breaking legacy writers.
3. Upgrade readers and writers per the compatibility matrix; if needed, deploy a single write path updating both old and new representations atomically.
4. **Batched backfill** with checkpoints, retries, load limits, and idempotency criteria.
5. Reconcile grain, row counts, currencies, mismatches, and reporting impact.
6. Create/validate appropriate constraints and indexes. Some engines support separate validation or online DDL, but exact capabilities must be verified for your DB version.
7. Shift read traffic (canary → full rollout), monitoring lag/drift and contract errors.
8. After the compatibility window, **contract**: remove legacy columns/tables, old code, and unnecessary permissions.

### Index and Constraint Pitfalls in PostgreSQL

In PostgreSQL, `CREATE INDEX CONCURRENTLY` reduces write blocking while building an index, but **cannot run inside a regular transaction block**; it also carries overhead, can fail, and can leave behind an invalid index that must be handled per version documentation. Do not bundle it into the same `BEGIN ... COMMIT` block as a backfill just to make "everything atomic".

`ALTER TABLE ... ADD CONSTRAINT ... NOT VALID` followed by `VALIDATE CONSTRAINT` is useful for supported constraints such as `CHECK` or `FK`; **not every constraint type shares the same mechanism**. Adding `UNIQUE` or `PK` on a large table requires an appropriate index and lock plan. While a constraint remains unvalidated, do not declare historical data compliant.

### Foreign Keys and Key Changes

When migrating the primary key from `email` to `customer_id`:

- Generate durable, unique IDs; check duplicate emails, case-sensitivity, and tenant scope.
- Add the new reference column on child tables and backfill using verified mappings.
- Check for missing parents, reused IDs, and customer merge cases.
- Create FKs and validate at a consistent data point.
- Switch writers/readers before dropping the legacy key dependency.

Do not drop FKs first and assume data will stay consistent on its own; nor should you upgrade keys by sacrificing constraints without an alternative safeguard.

## 16. Verification SQL: Proving Data and Semantics Remain Intact

A migration must have **concrete proofs**, not just "the script ran without errors".

### Name Check in Dual-Column Phase

~~~sql
SELECT COUNT(*) AS rows_with_mismatched_name
FROM customer_account
WHERE display_name IS DISTINCT FROM customer_name;
~~~

Expect 0 **while both columns are defined to mean the same thing and must stay in sync**. After contraction, stop comparing against the dropped column.

### Key and Grain Check

~~~sql
SELECT tenant_id, customer_id, COUNT(*) AS n
FROM customer_account
GROUP BY tenant_id, customer_id
HAVING COUNT(*) > 1;
~~~

An enforced PK prevents duplicates, yet this query is valuable when checking staging or un-constrained copies.

### Relationship Check After Table Split

~~~sql
SELECT m.tenant_id, m.customer_id
FROM customer_contact_method m
LEFT JOIN customer_account c
  ON c.tenant_id = m.tenant_id
 AND c.customer_id = m.customer_id
WHERE c.customer_id IS NULL;
~~~

Expect 0 when tables live in the same DB with enforced constraints. If data flows through pipelines or across databases, orphan checks are even more critical.

### Checking Historical Values on Semantic Change

No simple SQL query can prove "all historical `PAID` orders were captured" when the legacy source never stored provider confirmations. You need a reconciliation table against the authoritative transaction source:

~~~text
order_id | legacy_status | provider_capture_ref | evidence_status
ORD-1    | PAID          | CAP-101              | VERIFIED
ORD-2    | PAID          | NULL                 | UNKNOWN
ORD-3    | PENDING       | CAP-105              | REQUIRES_REVIEW
~~~

In row `ORD-2`, `UNKNOWN` is truthful information about the limit of evidence. In row `ORD-3`, do not blindly flip `PENDING` to `CAPTURED` without explaining the business cutoff and reconciliation rule.

### Reconciling by Grain and Unit

If a migration turns an order amount into multiple payment movements, compare:

- Order counts by tenant and period.
- Unique transaction counts by provider reference / idempotency key.
- Total `CAPTURE` and `REFUND` **separately by currency**.
- Counts of unreconciled, sourceless, or conflicting records.
- Before/after KPI formula versions and restatement scope.

**Never sum amounts across different currencies.** Never compare total order value against total captured and assume they must match if the business allows uncollected deliveries, split payments, or partial refunds.

## 17. Model Evolution in Document, Graph, and Analytical Systems

Rename/structural/semantic principles apply across storage models, though physical mechanics differ.

| Storage Model | Rename | Structural Change | Semantic Change |
| --- | --- | --- | --- |
| **Relational** | Rename columns/views/mappers; review SQL/ORM/CDC. | Split/merge tables, PK/FK, unique, indexes, partitions. | Often needs new rules/constraints/sources and historical reconciliation. |
| **Document** | Rename JSON keys; readers support old and new schemas. | Switch embedded objects ↔ references/collections; change aggregate boundaries. | Needs document versioning and legacy read rules; JSON parsing is not enough. |
| **Graph** | Rename labels/properties/relation names with equivalent mapping. | Split nodes, add edges and cardinality; reverse relation/traversal direction. | Changing `FRIEND` from "follow" to "mutual acceptance" requires events/evidence. |
| **Analytics** | Rename fact/dimension/metric labels in the semantic layer. | Change grain, SCD, star schema/data mart, backfill. | Changing revenue formulas and release cadence requires versioning/restatement. |
| **Event store** | Upcast legacy event representations when meaning is unchanged. | Change envelope/payload, split event types, store versions. | Do not alter past events to fabricate new facts; emit corrections/confirmations. |

### Document: Schema-on-Read Does Not Eliminate Schema

A v1 document has `"phone": "..."`; a v2 document has `"contacts": [...]`. If the new reader only understands `contacts`, legacy documents must still be backfilled or read through an adapter. Some systems only rewrite documents when updated, leaving multiple shapes coexisting in the same collection for a long time. Version documents explicitly and specify which shapes decoders support.

### Graph: Modifying Relationships Often Changes Meaning

Renaming edge `WORKS_AT` to `EMPLOYED_BY` can be a pure rename if conditions and effective periods match. But if `WORKS_AT` previously included contractors while `EMPLOYED_BY` covers only contracted employees, that is a semantic change requiring verified source data. Changing the label alone creates false edges.

### Analytics: Metric Changes Require Versioning

The name `net_revenue` sounds unambiguous, yet it may currently be calculated from discounted order totals while the new definition requires invoice-recognized revenue after adjustments. Create an explicit metric/version (or publish a restatement) documenting the source and applicable timeframe. Never change a formula silently and let viewers believe figures from two periods mean the same thing.

## 18. Schema Governance, Contracts, and Data Permissions

A technical change can become a security violation if it leaks data or alters ownership.

### Ownership and Write Permissions

- Who owns the fact and holds authority to modify it?
- Which service/schema owns the data; are other services running direct `UPDATE` statements on the table?
- Does the structural change create a new copy; does it carry the same access controls as the source?
- Do new APIs/events inadvertently expose emails, addresses, or more sensitive attributes than before?
- Is the data warehouse treating a derived fact/dimension as an authoritative source and writing back to OLTP?

Clear boundaries allow an owner to refactor internal tables without forcing every consumer to change. Consumers rely on **published contracts**, not physical column names as stable APIs.

### Retention, Erasure, and History

When splitting `customer.phone` into `customer_contact_method`, legacy information still lingers in backfill logs, audits, CDC streams, read models, backups, and exports. Dropping the old column **does not automatically erase every copy of personal data**.

When a valid erasure/anonymization request arrives, evaluate sources, derived copies, retention rules, and legal holds under actual policy. Do not treat hashing an ID or dropping a display name as absolute anonymization if records can still be linked back to an individual.

### What Should a Migration Contract Capture?

| Attribute | Example |
| --- | --- |
| `change_id` and owner | `CUST-MODEL-2026-01`, Customer Identity team. |
| Change type | Rename + structural split + separate semantic change. |
| Source → target | `customer_name → display_name`. |
| Grain and keys | `(tenant_id, customer_id)` unchanged; contacts 0..N. |
| Mapping rules | Create contact only from valid `phone_e164` data. |
| Semantic rules | New `ACTIVE` requires verification evidence. |
| Backward/forward policy | Support window for v1/v2 readers. |
| Data quality and exceptions | Missing, duplicate, ambiguous, conflict. |
| Security/retention | Paths holding PII and handling policies. |
| Cutover/rollback | When ownership transfers and conditions allowing recovery. |
| Success criteria | Row counts, FKs, KPIs, consumer contracts, and SLOs. |

## 19. Failure Modes and Rollbacks to Rehearse Before Dropping Columns

| Incident | Consequence | Prevention / Recovery |
| --- | --- | --- |
| App v1 still writes `customer_name` after cutover | `display_name` becomes stale or diverges. | Inventory writers, transitional compatibility, block old writers after cutoff. |
| Batch backfill re-runs | Creates duplicate contacts or overwrites newer data. | Business keys/unique constraints, idempotent backfill, version checks. |
| Two writers create a primary phone concurrently | Unique violation or race on primary selection. | Customer-scoped transaction/locking and conflict policy. |
| Column renamed while old SQL queries still run | APIs/reports fail immediately on deploy. | Expand–contract, dependency inventory, canary. |
| v1 data fails to parse into v2 schema | New reader crashes or "fixes" with guessed values. | Versioned adapters, quarantine, golden fixtures. |
| Legacy `PAID` read as provider-confirmed | Revenue and refund workflows break. | Legacy semantic version, reconciliation, unknown classification. |
| Old table dropped then rollback needed | Data absent from target is lost. | Backup/rollback window, retain old data long enough; define point of no return. |
| Both 1:N and 1:1 models accept writes | No lossless reverse mapping. | Designate one write owner; gate new features until after cutover. |
| Old aggregates not rebuilt | Reports still reflect old grouping/meaning. | Shadow mart, grain reconciliation, metric versioning. |
| Large DDL causes long locks or replica lag | Production SLO degradation. | Appropriate batched/online DDL, testing, resource throttling. |
| Backup restored from before migration | Recovery system does not match current contract/schema. | Restore runbook + replay migrations + compatibility checks. |
| Key changed while omitting tenant scope | FKs point to wrong customer/order of another tenant. | Composite keys, tenant isolation tests, permissions, mapping validation. |

### Distinguishing Code Rollback, Schema Rollback, and Data Rollback

These three are **different**:

- **Code rollback:** re-running the previous app version; safe only if it understands the existing data and contract.
- **Schema rollback:** restoring old columns/tables; may not recover data already discarded or split.
- **Data rollback:** restoring state to a point in time via backups, logs, or verified reverse migrations; must avoid losing valid newly committed data.

A semantic change cannot be rolled back simply by renaming a column. Once transaction eligibility has been granted under new rules or a provider has captured funds, reverting code does not undo business effects; explicit workflows and corrections are required.

## 20. Decision Process: Classify First, Execute Second

Follow this ordered checklist:

**Step 1 — Write source and target contracts.** For each field/entity, define grain, ID, type, unit, nullability, time semantics, owner, finalization condition, constraints, and data consumers.

**Step 2 — Prove the level of change.**

- Same meaning, same grain, only label differs? Rename.
- Representation/cardinality/keys change? Structural.
- Authoritative source, confirmation condition, formula, validity, or KPI definition changes? Semantic.
- Multiple Yes answers? Record it as a **multi-risk migration**, rather than assigning a single label to downplay complexity.

**Step 3 — Classify legacy data.** Which records map cleanly, which lack information, and which must go to review/unknown?

**Step 4 — Choose a compatibility strategy.** Direct rename only in closed systems with coordinated downtime; expand–contract for rolling deployments; versioned adapters/upcasters for historical events; shadow projections when KPI meanings change.

**Step 5 — Design and verify invariants.** PK/FK/unique/check, unchanged unexpected grain, accurate currency/units, no orphan references, no overwriting sources of truth.

**Step 6 — Plan rollout/cutover/rollback.** Who writes, who reads, when the new field takes over, when old structures drop, and when lossless rollback ceases to be possible?

**Step 7 — Measure and reconcile.** Row counts, duplicates/orphans, mismatches, exception counts, version/schema errors, query P95/P99, outbox/projection lag, before/after metrics.

### Short Decision Tree

~~~mermaid
flowchart TD
    A["Proposed data change"] --> B{"Does meaning, timing, or owner change?"}
    B -->|"Yes"| S["Semantic change: new definition + historical evidence"]
    B -->|"No"| C{"Do grain, keys, relationships, or type/unit change?"}
    C -->|"Yes"| T["Structural change: mapping + constraints + backfill"]
    C -->|"No"| D{"Only renaming or changing label?"}
    D -->|"Yes"| N["Rename: contract compatibility + rollout"]
    D -->|"No"| R["Clarify requirements and ownership"]
    S --> M["Evaluate accompanying structural changes/renames"]
    T --> M
    N --> M
    M --> V["Verify, cut over, observe, and clean up dependencies"]
~~~

The tree is meant to **surface the primary risk category first**, not to imply the branches are mutually exclusive. A project with a semantic change may still require structural migrations and renames.

## 21. Practical Exercise: Evolving an Order Model Without Corrupting History

**Context:** a service-booking platform uses PostgreSQL and publishes events to Finance/CRM. Legacy schema:

~~~text
customer(
  tenant_id, customer_id, customer_name, phone, active
)

booking(
  tenant_id, booking_id, customer_id, total_amount, status, created_at
)

status = NEW | PAID | CANCELLED
~~~

Verified context from teams:

- `customer_name` is a display name, not a legal name.
- `phone` currently stores one number; customers may want multiple numbers and verification status.
- Legacy `active` meant "account not closed", not "verified".
- Legacy `total_amount` was the quoted amount to the customer **before refunds**, though history did not always clearly record discounts and currency.
- Legacy `PAID` was recorded when the system sent a payment request; successful provider callbacks were not always stored.
- Historical bookings must be kept for dispute handling; some customers request contact-info deletion under policy.
- CRM reads JSON `customer_name`; Finance consumes CDC from the `booking` table; an older mobile app version is still active.

### Tasks

1. **Classify six requests:** rename `customer_name` to `display_name`, extract `phone`, change `active`, replace `total_amount` with `net_cash`, revise `PAID`, and add multi-version booking history. State whether each is rename, structural, semantic, or combined.
2. **Define contracts:** for `customer_id`, `phone`, `booking.total_amount`, and `PAID`, specify grain, unit, timing, owner, nullability, and evidence.
3. **Design keys:** 0..N Contact table, primary phone, verification, tenant isolation; explain why email/phone should not be the Customer PK.
4. **Plan the rename migration:** write `ADD COLUMN display_name`, compatibility queries, backfill, mismatch checks, and a drop plan after CRM/mobile upgrades.
5. **Migrate phone:** create the Contact table with FKs; describe duplicate prevention, invalid-number handling, and why legacy phones must not be marked verified.
6. **Handle status semantics:** separate account lifecycle, verification, and transaction eligibility; propose an `UNKNOWN` value for history lacking evidence.
7. **Separate amounts:** distinguish booked amount from captured/refunded cash; design `payment_movement` with grain of one provider-confirmed transaction, `currency`, and idempotency.
8. **Reconcile `PAID`:** define categories `VERIFIED_CAPTURE`, `PENDING_RECONCILIATION`, `UNKNOWN_LEGACY`; explain why all legacy rows cannot be backfilled as `CAPTURED`.
9. **Timing:** distinguish booking `created_at`, provider `captured_at`, and callback `recorded_at`; handle late-arriving callbacks.
10. **Consumers:** define v2 API/events, compatibility matrix, and historical readers; contrast CDC with semantically meaningful integration events.
11. **Production rollout:** sequence of expand, dual-column write, backfill, validate, cutover, contract; which steps require a single writer and which are irreversible?
12. **Security:** list paths where personal data persists across staging, events, read models, and backups, and how retention/erasure applies per policy.
13. **Testing:** write queries/tests for mismatches, duplicate BKs, orphan FKs, fact grain, net cash by currency, unknown provider outcomes, and v1/v2 API readers.
14. **ADR:** document two rejected alternatives, rationale, SLOs, owner, rollback scenarios, and completion criteria.

### Self-Assessment Checklist

| Criterion | Indicator of Success |
| --- | --- |
| **Accurate classification** | Rename only when meaning is identical; structural and semantic aspects identified independently. |
| **No fabricated facts** | Verification, refunds, or captures are never synthesized from statuses lacking evidence. |
| **Correct keys/grain** | 0..N Contact extracted, business IDs preserved, tenant-scoped FK/unique constraints. |
| **Compatibility** | Clear transition paths for old/new readers and historical data. |
| **Safe rollout** | Expand–migrate–contract with single write source, batched/checkpointed backfill, cutover, and verification. |
| **KPI accuracy** | Booked amount separated from net cash; no invalid cross-currency sums or double-counted movements. |
| **History** | Documents and timestamps preserved per business meaning and retention rules. |
| **Operations** | Monitoring for mismatches, unknowns, lag, load, errors, and realistic rollback plans. |

**Conclusion:** renaming only changes **how a fact is named**, structural change alters **representation and relationships**, and semantic change alters **what a value asserts about the business**. A single migration can involve all three. To keep systems evolvable yet verifiable, define grain, business keys, constraints, owners, time semantics, and contracts for source and target data; migrate only known facts with evidence, isolate ambiguous legacy data, roll out compatibly in phases, and reconcile before dropping old structures.
