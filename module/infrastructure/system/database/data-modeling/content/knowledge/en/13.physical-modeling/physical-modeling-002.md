# Designing Required Columns, Default Values, and Check Constraints

## 1. Why Are These Three Decisions Crucial in Physical Modeling?

In the `DATABASE_DATA_MODELING` module, the goal is to turn business requirements into a clear, verifiable data model: from entities, relationships, constraints, normalization, keys, and indexes to the physical schema. When deploying on a database management system (DBMS), three fundamental mechanisms protect the meaning of **each column and each row**:

- **`NOT NULL`**: whether a column is required to have a value.
- **`DEFAULT`**: what value the DBMS uses when a write statement **omits** a value for the column.
- **`CHECK`**: whether a value or combination of values within a row satisfies an allowed condition.

These three mechanisms answer **three different questions**. A column with `DEFAULT` is not necessarily required; a column with `CHECK` does not automatically forbid `NULL`. Sound design must start with business semantics, then choose data types and constraints that the DBMS genuinely enforces.

**Target outcome:** from a requirement such as "each booking has at least one attendee, starts in draft status, and ends after it starts", learners can decide which columns are `NOT NULL`, which have `DEFAULT`, how to write `CHECK` constraints, and how to test invalid boundary data.

## 2. First Step: Define the Meaning of "Missing Value"

Consider a consultation booking system. A booking has a customer, start/end timestamps, attendee count, status, agreed fee, and cancellation reason (if any). Before writing SQL, determine:

| Logical Attribute | Can It Be Missing? | Reasonable Default? | Validity Rule |
|---|---|---|---|
| Booking ID | No | Can be DBMS-generated | Unique identifier |
| Customer | No | No | Must reference an existing customer |
| Start and end | No | No | End must be after start |
| Attendee count | No | `1` if the business explicitly defines "omitted means one person" | Between 1 and 12 |
| Status | No | `DRAFT` | Only `DRAFT`, `CONFIRMED`, `CANCELLED` |
| Agreed fee | No | **Do not assume 0** | Non-negative; appropriate currency precision |
| Cancellation reason | Conditionally | No | Required with content when cancelled, must be empty when not cancelled |
| Creation timestamp | No | System-recorded timestamp | Represents a real point in time, with timezone convention |

Distinguish between these cases:

1. **Unknown:** expected delivery date is not yet known; `NULL` can carry a valid meaning.
2. **Not applicable:** cancellation reason does not exist yet because the booking is not cancelled; `NULL` can be valid conditionally based on status.
3. **User did not enter, but a derivable rule applies:** attendee count defaults to one; `DEFAULT 1` can be used.
4. **Required data not yet provided:** customer or agreed fee is missing; the operation must be rejected or a complete record must not yet be created.

Do not use dummy sentinel values like `1970-01-01`, `'UNKNOWN'`, `-1`, or `0` to stand in for "unknown" just to avoid `NULL`. Sentinel values participate in filters, aggregations, and comparisons like real data, causing hard-to-detect distortions.

## 3. `NOT NULL`: Columns Required to Have a Value

### 3.1. Semantics of `NULL`

In SQL, `NULL` represents a missing or unknown value; it is not equal to `0`, empty string `''`, whitespace, `FALSE`, or a default date. Standard comparisons with `NULL` can evaluate to **UNKNOWN**.

```sql
-- PostgreSQL: neither expression returns a normal TRUE/FALSE.
SELECT NULL = NULL;  -- NULL (UNKNOWN)
SELECT 5 > NULL;     -- NULL (UNKNOWN)

-- To check for the presence of data:
SELECT NULL IS NULL;     -- TRUE
SELECT 5 IS NOT NULL;    -- TRUE
```

For a column declared `NOT NULL`, the DBMS blocks inserts or updates if the resulting column value is `NULL`. It protects the data whether writes come from the application, SQL scripts, ingestion jobs, or another integrated system.

```sql
CREATE TABLE consultation_customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(254) NOT NULL,
    CONSTRAINT uq_consultation_customer_email UNIQUE (email),
    CONSTRAINT ck_consultation_customer_name
        CHECK (char_length(btrim(full_name)) > 0)
);
```

Here, `full_name NOT NULL` only forbids `NULL`. It still permits `''` or `'   '` unless an extra `CHECK` exists. The constraint `char_length(btrim(full_name)) > 0` catches empty strings and strings of ordinary spaces; PostgreSQL's default `btrim` does not replace full Unicode normalization rules or every kind of whitespace character. Valid name policies must be explicitly specified when stricter validation is needed.

### 3.2. Choosing Required Columns by Business State

Do not attach `NOT NULL` just because the current UI shows an asterisk. Ask: can a record ever be saved before all information is complete? A `DRAFT` order might not yet have a shipping address; a `CONFIRMED` order might require one. In that case, the address is not "required for every row", but **conditionally required by status**; you can combine a nullable column with a cross-column `CHECK` or design a split-table lifecycle.

Conversely, if a column is a required foreign key, you need both `NOT NULL` **and** `FOREIGN KEY`: a foreign key alone allows `NULL` when the referencing column is optional.

### 3.3. Consequences of Adding `NOT NULL` to an Existing Table

If a table already contains `NULL` data, a statement adding `NOT NULL` will fail; you must inspect existing data groups, handle them, and determine who has authority to supply missing values. Turning every `NULL` into `0` or `'N/A'` is rarely business-accurate. On large tables, validation scans and locks during schema alterations also affect response times, so migrations must be planned.

## 4. `DEFAULT`: Behavior When a Value Is Omitted

`DEFAULT` defines the value the DBMS uses for a column if an `INSERT` omits that column or explicitly specifies the `DEFAULT` keyword. It is a business-semantic convenience, **not** a substitute for `NOT NULL` or a fix for all missing data.

```sql
CREATE TABLE default_demo (
    demo_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label   TEXT NOT NULL,
    active  BOOLEAN NOT NULL DEFAULT TRUE
);

-- Omit active: DBMS uses TRUE.
INSERT INTO default_demo (label) VALUES ('A');

-- Explicitly specify DEFAULT: DBMS also uses TRUE.
INSERT INTO default_demo (label, active)
VALUES ('B', DEFAULT);

-- Explicitly specify NULL: DEFAULT is not used; rejected by NOT NULL.
INSERT INTO default_demo (label, active)
VALUES ('C', NULL);
```

The example above uses PostgreSQL. The final `INSERT` **intentionally fails** and should be run separately when practicing on a test database.

### 4.1. Common Types of Defaults

| Default Type | PostgreSQL Example | When to Use |
|---|---|---|
| Constant | `DEFAULT 1`, `DEFAULT 'DRAFT'`, `DEFAULT FALSE` | Business confirms the value applies to every write omitting the column |
| Write timestamp | `DEFAULT CURRENT_TIMESTAMP` | Record creation time when the database is the source of truth |
| DBMS-generated ID | `GENERATED ALWAYS AS IDENTITY` | Technical identifier that callers do not provide |
| System expression/function | A UUID generator function supported by the DBMS/extension | Requires alignment on compatibility, generation method, uniqueness, and version |

Choices to weigh carefully:

- **Default values must have the right meaning.** `status DEFAULT 'CONFIRMED'` is dangerous if "status not specified" actually means unapproved. `DRAFT` is usually safer when an approval step exists.
- **Never default a fee to 0** if the fee has not been finalized; free-of-charge is real information, distinct from fee-not-yet-known. To allow drafts without finalized fees, allow `NULL` in draft state and enforce conditionally upon confirmation.
- **Defaults do not auto-update on every `UPDATE`.** `DEFAULT CURRENT_TIMESTAMP` on `created_at` only helps at row creation. To maintain an `updated_at` reflecting updates, design and test an appropriate application, trigger, or system mechanism.
- **Timestamp functions depend on the DBMS.** In PostgreSQL, `CURRENT_TIMESTAMP` reflects transaction start time, so multiple rows in the same transaction receive the same timestamp. If true wall-clock time at call time is needed, evaluate alternative functions and operational requirements.
- **Defaults can mask integration bugs.** If every event must distinguish sales channels, setting `channel DEFAULT 'WEB'` silently turns events from other channels into web traffic whenever a sender omits the field.

### 4.2. `DEFAULT` in the Database or the Application?

The application can suggest values and render them on forms; the DBMS should still define defaults if **all writers** share the same policy. Both layers must stay aligned to avoid an API creating `DRAFT` while a batch import job creates `CONFIRMED`. When you need to know whether a user actively chose a value or merely accepted the default, consider recording the decision source; `DEFAULT` alone does not track "who chose it".

## 5. `CHECK`: Forbidding Invalid Values or Combinations

`CHECK` places a boolean condition expression on a table row. For example:

```sql
-- Only accept 1 to 12 attendees.
CHECK (attendee_count BETWEEN 1 AND 12)

-- Non-negative fee.
CHECK (agreed_fee >= 0)

-- End after start.
CHECK (ends_at > starts_at)

-- Status belongs to allowed set.
CHECK (booking_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
```

The proper scope for `CHECK` is **single-row invariants**: numeric ranges, status sets, string limits, ordering between two timestamps, and conditional relationships between status and cancellation reason. Naming constraints like `ck_booking_time_order` makes error messages and migrations easier to trace.

### 5.1. Biggest Trap: SQL Three-Valued Logic

`CHECK` in PostgreSQL and many other DBMSs is satisfied when the expression evaluates to **TRUE** or **UNKNOWN**; it rejects only when the result is **FALSE**. Therefore:

| Value of `quantity` | `CHECK (quantity > 0)` | Outcome |
|---|---|---|
| `5` | `TRUE` | Accepted |
| `0` | `FALSE` | Rejected |
| `-3` | `FALSE` | Rejected |
| `NULL` | `UNKNOWN` | **Still accepted** without `NOT NULL` |

To make `quantity` both required and positive, declare **both**:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_quantity_positive CHECK (quantity > 0)
```

Similarly, `CHECK (status IN (...))` does not forbid `NULL`. The rule "cannot be empty" is `NOT NULL`'s job, while `CHECK` guards the value domain.

A cross-column expression must also account for `NULL` explicitly. For example, `CHECK (cancelled_at > created_at)` does not forbid missing `cancelled_at`, because comparing against `NULL` yields `UNKNOWN`. If the rule is "when cancelled, a cancellation timestamp must exist", add the corresponding `IS NOT NULL` condition.

### 5.2. Cross-Column Invariants Within the Same Row

A rule like "when `booking_status = 'CANCELLED'`, a reason must be recorded; when not cancelled, there must be no reason" can be verified with a single `CHECK`:

```sql
CHECK (
    (
        booking_status = 'CANCELLED'
        AND cancellation_reason IS NOT NULL
        AND char_length(btrim(cancellation_reason)) > 0
    )
    OR
    (
        booking_status <> 'CANCELLED'
        AND cancellation_reason IS NULL
    )
)
```

This is a **bidirectional** constraint: cancelled requires a reason; non-cancelled forbids attaching a reason. It assumes `booking_status NOT NULL`. If you do not want to force deleting the reason when restoring a booking, adjust the business requirement or design a cancellation history table instead of quietly dropping the constraint.

### 5.3. What `CHECK` Cannot Do

- **Does not replace a unique key.** "No two customers share an email" requires `UNIQUE` or an equivalent uniqueness mechanism, plus a case-sensitivity comparison policy.
- **Does not replace a foreign key.** "The customer must exist" requires `FOREIGN KEY` or appropriate referential enforcement.
- **Cannot enforce multi-row relationships with a standard `CHECK`.** "A room cannot have two overlapping bookings" requires dedicated design: exclusion constraints where the DBMS supports them, transactions/locking at an appropriate isolation level, or another synchronization mechanism.
- **Does not enforce state transition history on its own.** `CHECK (status IN (...))` cannot verify whether `DRAFT → CONFIRMED → CANCELLED` was a valid transition because each row only reflects the current state. State transition rules require transactional logic or an event history model.
- **Should not depend on time-varying conditions.** A `CHECK` such as `starts_at > CURRENT_TIMESTAMP` may hold at insert time yet become false an hour later without the DBMS re-checking existing rows. PostgreSQL also expects `CHECK` expressions to be immutable/stable relative to row data. For "bookings may only be created in the future", validate at the time the business operation executes.

## 6. Complete Example: PostgreSQL 16 Schema Design

The following schema assumes a consultation service limited to **1–12 people** per booking, one customer per booking, fee finalized before saving the booking, and initial status `DRAFT`. This DDL uses several PostgreSQL-specific features, notably `IDENTITY`, `TIMESTAMPTZ`, and `btrim`; other DBMSs require remapping.

```sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(254) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_full_name_nonblank
        CHECK (char_length(btrim(full_name)) > 0)
);

CREATE TABLE booking (
    booking_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id         BIGINT NOT NULL,
    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ NOT NULL,
    attendee_count      INTEGER NOT NULL DEFAULT 1,
    booking_status      VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    agreed_fee          NUMERIC(12, 2) NOT NULL,
    cancellation_reason TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_booking_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    CONSTRAINT ck_booking_attendee_count
        CHECK (attendee_count BETWEEN 1 AND 12),
    CONSTRAINT ck_booking_time_order
        CHECK (starts_at < ends_at),
    CONSTRAINT ck_booking_status
        CHECK (booking_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_booking_agreed_fee
        CHECK (agreed_fee >= 0 AND agreed_fee <> 'NaN'::NUMERIC),
    CONSTRAINT ck_booking_cancellation_reason
        CHECK (
            (
                booking_status = 'CANCELLED'
                AND cancellation_reason IS NOT NULL
                AND char_length(btrim(cancellation_reason)) > 0
            )
            OR
            (
                booking_status <> 'CANCELLED'
                AND cancellation_reason IS NULL
            )
        )
);
```

Here, `agreed_fee <> 'NaN'::NUMERIC` blocks the special `NaN` value that PostgreSQL permits in `NUMERIC`; it is a physical DBMS detail, not standard SQL syntax. `NUMERIC(12,2)` is chosen for illustration and does **not** guarantee suitability for every currency or rounding policy. For multi-currency billing, store currency codes, decimal-place rules, and conversion policies; the model above assumes a single pre-agreed currency outside the table.

**Interpreting against the data contract:**

| Column / Column Group | `NOT NULL` | `DEFAULT` | `CHECK` and Meaning |
|---|---|---|---|
| `customer_id` | Yes | No | `FOREIGN KEY` verifies the customer exists |
| `starts_at`, `ends_at` | Yes | No | `starts_at < ends_at` protects chronological order |
| `attendee_count` | Yes | `1` | Bounded from 1 to 12 |
| `booking_status` | Yes | `'DRAFT'` | Only three valid values |
| `agreed_fee` | Yes | No | Non-negative and excludes `NaN` on PostgreSQL |
| `cancellation_reason` | No | No | Conditionally dependent on status |
| `created_at` | Yes | `CURRENT_TIMESTAMP` | Preserved as the creation timestamp |

Example inserting a customer and a booking in the **same statement**; `attendee_count`, `booking_status`, and `created_at` are omitted so the DBMS applies their defaults:

```sql
WITH new_customer AS (
    INSERT INTO customer (full_name, email)
    VALUES ('Minh An', 'minh-an@example.test')
    RETURNING customer_id
)
INSERT INTO booking (customer_id, starts_at, ends_at, agreed_fee)
SELECT
    customer_id,
    '2027-03-05 09:00:00+07'::TIMESTAMPTZ,
    '2027-03-05 10:00:00+07'::TIMESTAMPTZ,
    250000.00
FROM new_customer
RETURNING booking_id, attendee_count, booking_status, created_at;
```

The expected values for the three defaulted columns are `attendee_count = 1`, `booking_status = 'DRAFT'`, and `created_at` recorded by the DBMS. `booking_id` is generated by `IDENTITY`.

If you subsequently run `UPDATE booking SET attendee_count = NULL WHERE ...`, the operation is rejected by `NOT NULL`; the DBMS does not substitute `DEFAULT 1` for `NULL`. When you intentionally want to reapply the default, PostgreSQL supports `UPDATE booking SET attendee_count = DEFAULT WHERE ...`.

### What Is Not Yet Protected in This Schema?

The schema does not validate emails according to mail delivery specs; `UNIQUE(email)` also does not automatically treat `A@example.test` and `a@example.test` as duplicates. There are no rules yet against double-booking rooms, enforcing valid state transitions, cancellation authorization, or change history. Those rules must be modeled separately according to business requirements; never claim a schema enforces them merely because it has `CHECK` constraints.

## 7. Boundary Test Suite to Run on a Real DBMS

Do not test only successful `INSERT`s. Create a test database, run independent test cases, and verify that the DBMS actually rejects or accepts each case as required. After any statement expected to fail, end or roll back the failed transaction before continuing on PostgreSQL.

| Scenario | Expected Outcome and Responsible Constraint |
|---|---|
| Omit `booking_status`, `attendee_count`, `created_at` in `INSERT` | Receives defaults `DRAFT`, `1`, creation timestamp |
| Send `attendee_count = NULL` | Rejected by `NOT NULL` despite `DEFAULT 1` |
| Send `attendee_count = 0` or `13` | Rejected by `ck_booking_attendee_count` |
| Send `booking_status = 'DONE'` | Rejected by `ck_booking_status` |
| Send `agreed_fee = -0.01` or `'NaN'` | Rejected by `ck_booking_agreed_fee` |
| Send `ends_at = starts_at` or earlier | Rejected by `ck_booking_time_order` |
| `CANCELLED` with `cancellation_reason = NULL` or `'   '` | Rejected by `ck_booking_cancellation_reason` |
| `DRAFT` with `cancellation_reason = 'Customer requested cancellation'` | Rejected due to conflicting status and reason |
| `CONFIRMED` with `NULL` cancellation reason | Accepted |
| `customer_id = NULL` | Rejected by `NOT NULL` |
| Nonexistent `customer_id` | Rejected by `FOREIGN KEY` |
| `full_name = ''` or ordinary-spaces-only string | Rejected by `ck_customer_full_name_nonblank` |

Example metadata verification queries on PostgreSQL:

```sql
-- Data types, nullability, and defaults after table creation.
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'booking'
ORDER BY ordinal_position;

-- Constraint definitions stored by the DBMS.
SELECT
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.booking'::regclass
ORDER BY conname;
```

Beyond negative/zero/out-of-range values, test Unicode, empty strings, special whitespace characters, numbers near `NUMERIC` limits, timezone conversions, and write paths bypassing the UI form. These cases help distinguish UI bugs, application bugs, and database constraints.

## 8. Decisions That Change When Switching DBMSs

`NOT NULL`, `DEFAULT`, and `CHECK` are widespread relational concepts, but support and syntax vary by **product, version, SQL mode, and engine**.

| Question | PostgreSQL 16 | MySQL 8.0 / InnoDB | SQL Server 2022 |
|---|---|---|---|
| Enforces `CHECK`? | Yes; supports row constraints | Versions **8.0.16 and later** enforce `CHECK`; check actual version | Yes |
| Auto-generated ID column? | `GENERATED ... AS IDENTITY` | `AUTO_INCREMENT` | `IDENTITY(1,1)` |
| Current timestamp value? | `CURRENT_TIMESTAMP` has transaction-start semantics | `CURRENT_TIMESTAMP`/`NOW()` and timezone rules depend on type | `SYSDATETIMEOFFSET()`/`SYSUTCDATETIME()` as needed |
| Dedicated boolean type? | `BOOLEAN` | `BOOLEAN` is an alias for `TINYINT(1)` | `BIT` |
| Timestamp type used in example | `TIMESTAMPTZ` | Choose `TIMESTAMP` or `DATETIME` based on semantics | Typically consider `DATETIMEOFFSET` |
| Cross-row validation? | `CHECK` is not for cross-table references | Needs `FOREIGN KEY`/`UNIQUE` or specialized mechanisms | Needs `FOREIGN KEY`/`UNIQUE` or specialized mechanisms |

Because of these differences, do not copy `'NaN'::NUMERIC`, `btrim(...)`, or `IDENTITY` syntax straight to another DBMS. In MySQL, also check SQL mode, charset/collation, and handling of invalid-type values. In SQL Server, `TIMESTAMP` is not a date-time type; it is a legacy synonym for `ROWVERSION`.

To evaluate DBMS support, check at least: exact version, `CHECK` enforcement, `NULL` behavior in `CHECK`, default syntax, temporal types, numeric precision, type casting, and error handling. Writing **intentional failure tests** is more reliable than assuming DDL execution proves a constraint is enforced.

## 9. Safely Adding Constraints to Tables with Existing Data

Converting a nullable column to `NOT NULL` or adding a `CHECK` can fail due to legacy rows and increase table lock duration. The migration workflow should move from inspection to remediation before tightening constraints:

1. **Understand current semantics:** what do missing records mean? Can they be accurately derived from another source, do they need manual remediation, or must draft status be accepted?
2. **Measure violating rows:** count `NULL`s, out-of-range values, whitespace-only strings, and cross-column contradictions; assess data volume and peak traffic.
3. **Finalize the new policy:** align on `DEFAULT`, audit all UI/API/job writers, and establish an auditable legacy data backfill plan.
4. **Update writers and backfill:** ensure new records follow the new rules and remediate legacy rows in batches if necessary.
5. **Apply constraints and verify:** test DBMS behavior, lock/duration impact; run negative tests and monitor write errors post-deployment.

The example steps below are **independent of the `CREATE TABLE` in Section 6**: assume an existing legacy table named `legacy_booking` where `attendee_count` currently allows `NULL` and lacks the 1–12 range check. This is an illustrative PostgreSQL sequence to adapt to real data:

```sql
-- 1. Inspect before making changes.
SELECT
    COUNT(*) FILTER (WHERE attendee_count IS NULL) AS missing_count,
    COUNT(*) FILTER (
        WHERE attendee_count IS NOT NULL
          AND attendee_count NOT BETWEEN 1 AND 12
    ) AS out_of_range_count
FROM legacy_booking;

-- 2. Only run if business confirms legacy NULLs genuinely mean 1.
UPDATE legacy_booking
SET attendee_count = 1
WHERE attendee_count IS NULL;

-- 3. Default value for new records omitting the column.
ALTER TABLE legacy_booking
    ALTER COLUMN attendee_count SET DEFAULT 1;

-- 4. Block new invalid values; existing rows will be validated later.
ALTER TABLE legacy_booking
    ADD CONSTRAINT ck_legacy_booking_attendees
    CHECK (attendee_count BETWEEN 1 AND 12) NOT VALID;

-- 5. Once all out-of-range values are fixed, validate existing data.
ALTER TABLE legacy_booking
    VALIDATE CONSTRAINT ck_legacy_booking_attendees;

-- 6. Once no NULLs remain and operational impact is verified:
ALTER TABLE legacy_booking
    ALTER COLUMN attendee_count SET NOT NULL;
```

In PostgreSQL, `CHECK ... NOT VALID` is still enforced for newly inserted or updated rows while deferring the scan of all existing rows; `VALIDATE CONSTRAINT` performs the validation pass over existing rows. Depending on version and scale, `ALTER TABLE` operations can hold locks and scan data; test on a replica with realistic data distribution and load. If legacy rows have `attendee_count = 0` or `13`, fix them on solid grounds **before** `VALIDATE` can succeed.

Do not blindly convert every legacy `NULL` to `1`. If you cannot prove what it meant, you may need to keep `NULL`, separate incomplete-data states, or build a reconciliation and cleanup tool. A migration that succeeds syntactically by fabricating historical values is still a broken migration.

## 10. Common Pitfalls

| Flawed Design | Why It Is Wrong | How to Fix |
|---|---|---|
| `quantity INTEGER CHECK (quantity > 0)` treated as "required" | `NULL` evaluates to `UNKNOWN`, so it slips through | Add `NOT NULL` |
| `status NOT NULL DEFAULT 'CONFIRMED'` without an approval step | Missing input silently becomes approved | Use a lifecycle-appropriate default, usually `DRAFT` |
| `fee NOT NULL DEFAULT 0` before fee calculation | Confuses free-of-charge with undetermined | Require fee input or model an unfinalized state |
| `email NOT NULL` assumed sufficient for validity | Still allows empty strings and malformed inputs | Add appropriate validation, normalization, and business-level email verification |
| `CHECK (a < b)` on two optional columns | One `NULL` turns the condition into `UNKNOWN` | Specify optionality clearly; add `NOT NULL` or explicit `IS NULL`/`IS NOT NULL` clauses |
| Using `CHECK` to prevent overlapping room bookings | Single-row checks cannot reliably see other rows | Design multi-row constraints and an appropriate transaction strategy |
| Using `created_at <= CURRENT_TIMESTAMP` as a permanent invariant | Time advances without the DBMS re-validating rows | Validate when the operation executes and store decision evidence |
| Adding `NOT NULL` directly onto a legacy table | May hit `NULL`s, write errors, or long locks | Inspect, remediate data, test migration, then tighten constraints |

## 11. Design Checklist and Practice Exercise

Before handing off a physical schema, answer for **each column**:

- Can this value be absent? Does `NULL` represent "unknown", "not applicable", or an error?
- If a writer omits the column, does **one value derivable in all cases** exist for `DEFAULT`?
- Which value domains and cross-column conditions must always hold? Have `NULL`s been accounted for inside `CHECK` expressions?
- Does the constraint check one row, multiple rows, or data in another table? Are `UNIQUE`, `FOREIGN KEY`, or transactions needed instead of `CHECK`?
- Does the target DBMS version enforce this mechanism accurately? Are there differences in numeric types, timezones, string expressions, casting, or compatibility?
- Can legacy data and non-UI write paths comply with the new rules? Are there intentional failure tests and a migration plan?

**Practice exercise:** a room-booking application has `room_id`, `start_at`, `end_at`, `seat_count`, `status`, and `cancelled_at`. Requirements: room and timestamps are required; `seat_count` is from 1 up to the room's capacity; default status is `PENDING`; when cancelled, `cancelled_at` must be present; a room cannot have two confirmed bookings with overlapping times.

1. Categorize which rules can be handled with single-row `NOT NULL`, `DEFAULT`, and `CHECK`, and which require `FOREIGN KEY` or multi-row mechanisms.
2. Write the `CHECK` for `start_at < end_at` and the status/cancellation condition, stating clearly which columns must be `NOT NULL` to avoid `UNKNOWN`.
3. Explain why "`seat_count` does not exceed room capacity" cannot be written as a simple single-row `CHECK` if capacity lives in the `room` table; propose an appropriate way to preserve integrity.
4. List at least six test cases including an explicitly sent `NULL`, a defaulted value, an out-of-range value, misordered timestamps, and two overlapping room bookings.

A solid physical model does not merely define what data type a column holds; it expresses **when a value is required, when it is derived, and which combinations are forbidden**. Using `NOT NULL`, `DEFAULT`, and `CHECK` with accurate semantics helps data preserve critical invariants even as applications and integration pipelines evolve.
