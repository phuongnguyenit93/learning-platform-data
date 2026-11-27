# Transition Tables and Set-Based Change Processing in PostgreSQL

When a SQL statement modifies **many rows**, a PostgreSQL trigger may need to process the **entire set of affected rows** rather than firing once per row. For instance, a statement:

~~~sql
UPDATE sales
SET status = 'paid'
WHERE status = 'draft';
~~~

can update hundreds of sales orders. A `FOR EACH ROW` trigger executes many times and inspects each `OLD`/`NEW` pair individually. However, if the task is computing **total revenue delta per customer**, per-row processing easily produces many redundant writes and raises overhead.

PostgreSQL provides **transition relations**, commonly called **transition tables**, giving triggers access to a set of rows:

- `OLD TABLE`: the **before-update or before-delete** image of the affected rows.
- `NEW TABLE`: the **after-insert or after-update** image of the affected rows.

Example:

~~~sql
CREATE TRIGGER sales_after_update
AFTER UPDATE ON sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION update_sales_summary();
~~~

Inside the trigger function, `old_rows` and `new_rows` can be queried with SQL like relations:

~~~sql
SELECT customer_id, SUM(amount)
FROM new_rows
WHERE status = 'paid'
GROUP BY customer_id;
~~~

This lesson, **"Transition Tables and Set-Based Change Processing,"** belongs to the **Triggers and Rules** chapter in the **Database Engine Relational PostgreSQL** module. It focuses on the nature of transition tables, trigger creation syntax, set-based INSERT/UPDATE/DELETE handling, a hands-on audit and summary-table lab, performance, transactions, concurrency, limitations, and safe operational practices.

> **Note:** DDL/DML examples in this lesson are intended for a practice database. Triggers execute automatically when data changes and can increase per-statement work; do not enable them on production tables without evaluating dependencies, change volume, locks, and rollback behavior.

---

## 1. Why Are Row-Level Triggers Not Enough for Every Problem?

A row-level trigger reads:

~~~text
Call 1: OLD of sale 1, NEW of sale 1
Call 2: OLD of sale 2, NEW of sale 2
Call 3: OLD of sale 3, NEW of sale 3
...
~~~

If each invocation updates a summary table:

~~~sql
UPDATE customer_summary
SET paid_total = paid_total + change_for_one_row
WHERE customer_id = ...;
~~~

then a statement updating 10,000 rows can perform vast numbers of summary-table updates, contend on locks for the same customer, and generate unnecessary WAL.

Transition tables let a statement-level trigger process:

~~~text
UPDATE affects 10,000 rows
             |
             v
OLD TABLE: 10,000 before images
NEW TABLE: 10,000 after images
             |
             v
GROUP BY customer_id
             |
             v
One UPSERT per customer with a changed delta
~~~

For many **aggregation, reconciliation, batch auditing, and group-level checking** tasks, set-based processing is clearer and potentially far more efficient.

That does not mean every row-level piece of logic should move to transition tables. Single-row constraints, pre-INSERT value normalization, or simple validations are often a better fit for row-level triggers or table constraints.

## 2. Core Concepts

| Concept | Meaning |
|---|---|
| Trigger | Logic automatically fired by an event on a table or view |
| Trigger function | Function, usually `RETURNS trigger`, containing logic executed when the trigger fires |
| `FOR EACH ROW` | Trigger invoked once per matching row |
| `FOR EACH STATEMENT` | Trigger invoked once per statement |
| Transition table | Set of before/after rows associated with a change event |
| `OLD TABLE` | Old rows from UPDATE/DELETE |
| `NEW TABLE` | New rows from INSERT/UPDATE |
| `REFERENCING` | Declares transition relation names in `CREATE TRIGGER` |
| Set-based SQL | A single SQL operation over an entire set, e.g., `GROUP BY`, `JOIN`, `INSERT ... SELECT` |

Transition tables are not persistent business tables created with `CREATE TABLE`. They are **temporary relations scoped to a trigger invocation** provided by PostgreSQL for the trigger.

## 3. Before and After in an UPDATE Statement

Suppose the table holds:

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | draft | 100.00 |
| 11 | 101 | paid | 200.00 |
| 12 | 102 | paid | 50.00 |

Statement:

~~~sql
UPDATE sales
SET status = 'paid', amount = amount + 20
WHERE sale_id IN (10, 12);
~~~

For the **two rows actually updated**, the logical transition tables are:

**OLD TABLE**

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | draft | 100.00 |
| 12 | 102 | paid | 50.00 |

**NEW TABLE**

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | paid | 120.00 |
| 12 | 102 | paid | 70.00 |

Row `sale_id=11` does not appear in either transition table because the UPDATE did not touch it.

**Important:** transition tables represent the rows affected by the **triggering statement**, not a full snapshot of the entire table.

## 4. Transition Tables Differ From OLD and NEW Variables

In a `FOR EACH ROW` trigger:

~~~sql
OLD.amount
NEW.amount
~~~

are **single records** for the current row.

In a statement-level trigger using:

~~~sql
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
~~~

then:

~~~sql
SELECT SUM(amount) FROM old_rows;
SELECT SUM(amount) FROM new_rows;
~~~

are **queries over sets of rows**.

Do not write:

~~~sql
-- Wrong if expecting OLD to be a table:
SELECT * FROM OLD;
~~~

or:

~~~sql
-- Inside a statement-level trigger there is no OLD.amount
-- for a single row:
v_old_amount := OLD.amount;
~~~

In statement-level triggers, record variables `OLD`/`NEW` do not represent individual rows like in row-level triggers. Use the named transition relations.

## 5. Key Limitations to Remember

Transition relations are designed for eligible **AFTER triggers** on PostgreSQL tables, not every trigger kind.

Rules to remember:

1. The primary event must be `INSERT`, `UPDATE`, or `DELETE`.
2. Transition tables cannot be used in `BEFORE` triggers.
3. Transition tables cannot be used in `INSTEAD OF` triggers on views.
4. They cannot be used with `TRUNCATE` triggers.
5. A trigger declaring transition relations **cannot be a constraint trigger**.
6. For `UPDATE` with transition relations, you cannot specify a column list like `UPDATE OF column_name`.
7. Transition relations can be used in eligible **AFTER ROW** and **AFTER STATEMENT** triggers; set-wide processing normally uses `FOR EACH STATEMENT`.
8. For foreign tables, trigger support differs from regular local tables; never assume transition tables work identically to local tables.
9. Behavior with partitioning, inheritance, UPSERT, and MERGE depends on how the command executes and the PostgreSQL version.

Do not assume that because `REFERENCING` exists, every `CREATE TRIGGER` combination is valid. Choose the right event, timing, level, and table type.

## 6. CREATE TRIGGER Syntax With REFERENCING

**INSERT:**

~~~sql
CREATE TRIGGER name_after_insert
AFTER INSERT ON schema_name.table_name
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

**DELETE:**

~~~sql
CREATE TRIGGER name_after_delete
AFTER DELETE ON schema_name.table_name
REFERENCING OLD TABLE AS deleted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

**UPDATE:**

~~~sql
CREATE TRIGGER name_after_update
AFTER UPDATE ON schema_name.table_name
REFERENCING OLD TABLE AS deleted_rows
            NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

The names `inserted_rows` and `deleted_rows` are simply **aliases**. They are not fixed table names or special keywords. You can use `old_rows` and `new_rows` for clarity.

### 6.1. Do not use UPDATE OF with transition relations

**Invalid** example:

~~~sql
-- Do not run; illustrates forbidden combination:
CREATE TRIGGER bad_trigger
AFTER UPDATE OF amount ON some_table
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION some_trigger_function();
~~~

If you need to react only when `amount` actually changes, use `AFTER UPDATE` without a column list and filter changes inside the trigger function using `IS DISTINCT FROM`.

### 6.2. Transition relation names are not schema tables

`old_rows`/`new_rows` are local relation names within the trigger context, not `public.old_rows`. Never create a real table with that name trying to "access the transition table."

## 7. What Does AFTER Timing Mean?

An `AFTER` trigger runs after the corresponding data-modification event has occurred under PostgreSQL rules. Consequently, the `NEW TABLE` transition table reflects the image **after** the statement's transformations, including values accepted during execution.

However, **AFTER does not mean COMMITted**:

- The trigger still runs inside the statement/caller's transaction.
- The trigger sees changes under appropriate visibility rules.
- If the trigger raises an error, the statement/transaction can roll back.
- If the caller ultimately runs `ROLLBACK`, data written by the trigger also rolls back.

Writing to an audit table using transition tables is **not** sending data outside the transaction. It is part of PostgreSQL's transactional work.

## 8. Creating the Lab Schema

In a clean practice database:

~~~sql
CREATE SCHEMA tt_lab;

CREATE TABLE tt_lab.sales (
    sale_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'paid', 'cancelled')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE tt_lab.statement_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation TEXT NOT NULL
        CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    affected_rows BIGINT NOT NULL CHECK (affected_rows > 0),
    paid_amount_delta NUMERIC(18, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE tt_lab.customer_summary (
    customer_id BIGINT PRIMARY KEY,
    sale_count BIGINT NOT NULL CHECK (sale_count >= 0),
    paid_total NUMERIC(18, 2) NOT NULL
        CHECK (paid_total >= 0)
);
~~~

Purpose:

- `sales` stores business data.
- `statement_audit` stores statistics for each **statement affecting at least one row**.
- `customer_summary` stores the count of sale rows and total amount of `paid` sales per customer.

**Do not INSERT into `sales` yet**: we will create the triggers first so all changes in this lesson are tracked consistently.

### 8.1. Why does summary store both sale_count and paid_total?

An UPDATE statement can:

- Change `amount` without changing customer.
- Change `status` from draft to paid.
- Change `customer_id`, decreasing the count on the old customer and increasing it on the new customer.
- Change both customer and amount simultaneously.

Simply adding or subtracting one row's amount misses cases like group reassignment. We need **set-wide deltas** derived from old and new images.

## 9. Trigger Functions Return RETURNS trigger

A trigger function is typically declared as:

~~~sql
CREATE FUNCTION tt_lab.example_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Trigger logic.
    RETURN NULL;
END;
$$;
~~~

For an `AFTER STATEMENT` trigger, the return value is ignored by PostgreSQL in that trigger context; `RETURN NULL` is clear and idiomatic.

Do not declare a regular function returning `INTEGER` expecting `EXECUTE FUNCTION` in `CREATE TRIGGER` to accept it.

### 9.1. Metadata inside triggers

A PL/pgSQL trigger function can access:

- `TG_OP`: operation name, e.g., `INSERT`/`UPDATE`/`DELETE`.
- `TG_LEVEL`: `ROW` or `STATEMENT`.
- `TG_TABLE_NAME`: name of the triggering table.
- `TG_TABLE_SCHEMA`: schema.
- `TG_NAME`: trigger name.
- `TG_ARGV`/`TG_NARGS`: arguments specified when creating the trigger.

These metadata variables let one function serve multiple triggers with clear conditional branching.

## 10. Statement-Level Logging: The Idea

We want to write **one audit row per data-modifying SQL statement**, recording:

- Statement type: `INSERT`, `UPDATE`, or `DELETE`.
- Number of affected sale rows.
- Net change in total paid amount produced by the statement.

Examples:

~~~text
UPDATE:
  old paid_total = 250
  new paid_total = 390
  delta = +140

INSERT:
  old = 0
  new paid_total = 75
  delta = +75

DELETE:
  old paid_total = 120
  new = 0
  delta = -120
~~~

For a statement affecting 1,000 rows, we only compute **one aggregate over the transition sets** rather than inserting 1,000 audit rows when summary auditing is all that is required.

## 11. Creating the Set-Based Audit Function

~~~sql
CREATE FUNCTION tt_lab.audit_sales_statement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows BIGINT := 0;
    v_paid_delta NUMERIC(18, 2) := 0;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT
            COUNT(*),
            COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM new_rows;

    ELSIF TG_OP = 'DELETE' THEN
        SELECT
            COUNT(*),
            -COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM old_rows;

    ELSIF TG_OP = 'UPDATE' THEN
        SELECT
            COUNT(*),
            COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM new_rows;

        SELECT
            v_paid_delta - COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_paid_delta
        FROM old_rows;
    END IF;

    IF v_rows > 0 THEN
        INSERT INTO tt_lab.statement_audit (
            operation,
            affected_rows,
            paid_amount_delta
        )
        VALUES (TG_OP, v_rows, v_paid_delta);
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 11.1. Why use FILTER?

`SUM(amount) FILTER (WHERE status='paid')` sums only paid sale rows. `COUNT(*)` counts **all** affected sale rows, including draft and cancelled.

### 11.2. Why COALESCE?

`SUM` over an empty set or zero matching rows returns SQL NULL. `COALESCE(..., 0::NUMERIC)` converts it to 0 so delta arithmetic works cleanly.

### 11.3. What is IF v_rows > 0 for?

PostgreSQL can invoke `FOR EACH STATEMENT` triggers even when a DML statement affects zero rows. Our lab rule is **write audit rows only when at least one row was affected**, so the function skips empty sets.

### 11.4. Can one function serve all three events?

Yes, using three separate triggers with consistent transition relation aliases. PL/pgSQL executes only the branch matching `TG_OP`, so it only queries the transition relations that exist for that event.

## 12. Attaching the Three AFTER STATEMENT Triggers

~~~sql
CREATE TRIGGER sales_stmt_audit_insert
AFTER INSERT ON tt_lab.sales
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();

CREATE TRIGGER sales_stmt_audit_delete
AFTER DELETE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();

CREATE TRIGGER sales_stmt_audit_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();
~~~

All three triggers call the same function, while each event supplies the **transition relations valid for that change type**.

### 12.1. An AFTER UPDATE trigger with both OLD TABLE and NEW TABLE

This is the key structure whenever you need a **net delta**:

~~~text
UPDATE statement
       |
       +--> old_rows: before images
       |
       +--> new_rows: after images
       |
       +--> SUM(new paid) - SUM(old paid)
~~~

You do not always need to JOIN individual old/new rows to compute a total difference. When you only need group totals, aggregating old and new independently is clearer and automatically handles changing group keys.

## 13. Why Maintain a Summary Table?

Suppose an API frequently asks:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS sale_count,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0
    ) AS paid_total
FROM tt_lab.sales
GROUP BY customer_id;
~~~

This direct query is the **source of truth**, easy to verify, and usually the best default when data size and query volume are modest.

However, if the table grows very large and the system constantly looks up customer totals, you can store an **incrementally maintained summary table**:

~~~text
sales (source of truth)
     |
     v
Transition tables
     |
     v
GROUP BY customer_id over changed subset
     |
     v
customer_summary
~~~

This is **incremental maintenance** implemented with triggers, not an auto-refreshing materialized view.

### 13.1. Do not add summary triggers before understanding the cost

Summary tables add write overhead, lock contention, and bug risk. If a direct `GROUP BY` query is fast enough, avoid building complex trigger infrastructure just because you can.

## 14. Computing Deltas for INSERT

For INSERT, each new row causes:

- Customer's `sale_count` to increase by 1.
- `paid_total` to increase by `amount` if `status='paid'`, otherwise 0.

Set-based:

~~~sql
SELECT
    customer_id,
    COUNT(*)::BIGINT AS sale_delta,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0::NUMERIC
    ) AS paid_delta
FROM new_rows
GROUP BY customer_id;
~~~

Then UPSERT the deltas by `customer_id`.

Crucial: **GROUP BY before ON CONFLICT**. If an INSERT statement contains multiple rows for the same `customer_id` and you feed each row straight into UPSERT, a single target row would be updated multiple times in one command, causing errors or undefined behavior. Aggregating first guarantees each customer appears at most once.

## 15. Computing Deltas for DELETE

For DELETE, old rows are removed:

~~~sql
SELECT
    customer_id,
    -COUNT(*)::BIGINT AS sale_delta,
    -COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0::NUMERIC
    ) AS paid_delta
FROM old_rows
GROUP BY customer_id;
~~~

When applied to the summary table, the negative deltas subtract from the stored totals.

If a DELETE tries to push the summary negative due to drifted data, the `CHECK` constraints on `customer_summary` block the transaction. That is a signal to reconcile source vs. summary consistency—never silently drop the constraint just to "let the DELETE succeed."

## 16. Computing Deltas for UPDATE

UPDATE has both before and after images:

~~~text
delta(customer)
  = contribution(NEW rows by customer)
  - contribution(OLD rows by customer)
~~~

Example of a single sale:

~~~text
OLD: customer 101, paid, amount=100
NEW: customer 102, paid, amount=150
~~~

Result:

| customer_id | sale_count_delta | paid_total_delta |
|---:|---:|---:|
| 101 | -1 | -100 |
| 102 | +1 | +150 |

Computing only `NEW.amount - OLD.amount = 50` for one customer would **miss moving the sale between two customers**.

Safe pattern: aggregate both sets separately, combine with `UNION ALL`, then `GROUP BY customer_id` once more to compute the net delta.

## 17. Creating the Trigger Function to Maintain customer_summary

~~~sql
CREATE FUNCTION tt_lab.maintain_customer_summary()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN

        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            COUNT(*)::BIGINT,
            COALESCE(
                SUM(amount) FILTER (WHERE status='paid'),
                0::NUMERIC
            )
        FROM new_rows
        GROUP BY customer_id
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    ELSIF TG_OP = 'DELETE' THEN

        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            -COUNT(*)::BIGINT,
            -COALESCE(
                SUM(amount) FILTER (WHERE status='paid'),
                0::NUMERIC
            )
        FROM old_rows
        GROUP BY customer_id
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    ELSIF TG_OP = 'UPDATE' THEN

        WITH contributions AS (
            SELECT
                customer_id,
                COUNT(*)::BIGINT AS sale_delta,
                COALESCE(
                    SUM(amount) FILTER (WHERE status='paid'),
                    0::NUMERIC
                ) AS paid_delta
            FROM new_rows
            GROUP BY customer_id

            UNION ALL

            SELECT
                customer_id,
                -COUNT(*)::BIGINT AS sale_delta,
                -COALESCE(
                    SUM(amount) FILTER (WHERE status='paid'),
                    0::NUMERIC
                ) AS paid_delta
            FROM old_rows
            GROUP BY customer_id
        ),
        net AS (
            SELECT
                customer_id,
                SUM(sale_delta)::BIGINT AS sale_delta,
                SUM(paid_delta) AS paid_delta
            FROM contributions
            GROUP BY customer_id
        )
        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            sale_delta,
            paid_delta
        FROM net
        WHERE sale_delta <> 0
           OR paid_delta <> 0
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    END IF;

    RETURN NULL;
END;
$$;
~~~

**This function illustrates all three events completely.** It intentionally uses consistent `old_rows` and `new_rows` names; for each trigger event, PostgreSQL provides the matching relation within the function scope.

### 17.1. Why does UPDATE aggregate twice?

`contributions` holds positive deltas from NEW and negative deltas from OLD. `net` combines contributions sharing the same `customer_id` so the target row is never upserted twice.

### 17.2. Why filter out net = 0?

An UPDATE might modify only `updated_at` without changing `customer_id`, `status`, or `amount`. There is no reason to touch the summary table when both metric deltas are 0. Filtering avoids wasted UPDATEs on such events.

### 17.3. The summary table may retain zero rows

When a customer's last sale is deleted, `sale_count=0` and `paid_total=0` may remain. This is an intentional data-modeling choice; if zero rows must be pruned, design a policy accounting for concurrency and historical reporting.

### 17.4. Prerequisite: the summary must already be in sync

Delta maintenance assumes `customer_summary` already matches `sales` before incremental updates begin. If source rows exist while the summary is empty, DELETE/UPDATE can produce negative deltas rejected by CHECK. Build a consistent baseline before enabling incremental maintenance.

## 18. Attaching the Summary Triggers

~~~sql
CREATE TRIGGER sales_summary_insert
AFTER INSERT ON tt_lab.sales
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();

CREATE TRIGGER sales_summary_delete
AFTER DELETE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();

CREATE TRIGGER sales_summary_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();
~~~

Each source-table event now has two AFTER STATEMENT triggers:

1. Write `statement_audit`.
2. Maintain `customer_summary`.

Triggers of the same event type fire in alphabetical order by trigger name per PostgreSQL rules. **Do not rely on that ordering to hide functional dependencies**; design audit and summary logic to operate independently whenever possible.

## 19. Multi-Row INSERT and Observing Both Target Tables

Only **after creating the triggers**, insert sample data:

~~~sql
INSERT INTO tt_lab.sales (
    sale_id, customer_id, status, amount
)
VALUES
    (10, 101, 'draft', 100.00),
    (11, 101, 'paid', 200.00),
    (12, 102, 'paid', 50.00),
    (13, 102, 'cancelled', 60.00),
    (14, 103, 'paid', 75.00);
~~~

This is **one INSERT statement with 5 rows**, not 5 separate statements.

Inspect summary:

~~~sql
SELECT *
FROM tt_lab.customer_summary
ORDER BY customer_id;
~~~

Expected:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 2 | 200.00 |
| 102 | 2 | 50.00 |
| 103 | 1 | 75.00 |

And audit:

~~~sql
SELECT operation, affected_rows, paid_amount_delta
FROM tt_lab.statement_audit
ORDER BY audit_id;
~~~

Expect **one audit row** for inserting 5 sale rows, with paid delta:

\[
200 + 50 + 75 = 325
\]

### 19.1. Why is there only one audit row?

Because the trigger is `FOR EACH STATEMENT` and the function inserts one audit row after aggregating the entire transition relation.

### 19.2. What if FOR EACH ROW were used?

A separate row-level trigger would write 5 audit rows. That is not inherently wrong; it serves a **per-row detail** goal different from statement-level summary auditing.

## 20. Multi-Row UPDATE: Observing OLD/NEW Deltas

~~~sql
UPDATE tt_lab.sales
SET
    amount = amount + 20,
    status = 'paid',
    updated_at = statement_timestamp()
WHERE sale_id IN (10, 12);
~~~

Effects:

- Sale 10: draft 100 -> paid 120, paid contribution increases by 120.
- Sale 12: paid 50 -> paid 70, paid contribution increases by 20.
- Total paid delta: +140.
- Sale row counts per customer stay unchanged.

Check:

~~~sql
SELECT *
FROM tt_lab.customer_summary
ORDER BY customer_id;
~~~

Expected:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 2 | 320.00 |
| 102 | 2 | 70.00 |
| 103 | 1 | 75.00 |

Audit records one UPDATE event with `affected_rows=2` and `paid_amount_delta=140.00`.

## 21. UPDATE Reassigning a Sale to Another Customer

~~~sql
UPDATE tt_lab.sales
SET customer_id = 103,
    updated_at = statement_timestamp()
WHERE sale_id = 11;
~~~

Sale 11 currently has `status='paid'` and `amount=200`.

Net result:

| customer_id | sale_count_delta | paid_total_delta |
|---:|---:|---:|
| 101 | -1 | -200 |
| 103 | +1 | +200 |

The summary table becomes:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 1 | 120.00 |
| 102 | 2 | 70.00 |
| 103 | 2 | 275.00 |

A trigger that used `NEW.customer_id` and added a zero amount difference would be **wrong** when group keys change. That is why separating OLD and NEW contributions is essential.

### 21.1. Statement audit shows total delta = 0

In this event, **total paid amount across the whole table did not change**, so `paid_amount_delta=0` in the statement-level audit. Meanwhile, two customer summaries did change.

A single global audit figure cannot replace detailed reporting on shifts across groups.

## 22. Multi-Row DELETE

~~~sql
DELETE FROM tt_lab.sales
WHERE sale_id IN (12, 13);
~~~

- Sale 12: customer 102, paid 70 -> subtract 70 paid.
- Sale 13: customer 102, cancelled 60 -> no paid contribution.
- Customer 102's sale count decreases by 2.

Customer 102's summary becomes `sale_count=0`, `paid_total=0`.

Statement-level audit records:

- `operation='DELETE'`.
- `affected_rows=2`.
- `paid_amount_delta=-70.00`.

### 22.1. DELETE does not need NEW TABLE

DELETE creates no new row images in the source table. Use `OLD TABLE` only.

### 22.2. INSERT does not need OLD TABLE

INSERT has no old row images for newly created rows. Use `NEW TABLE` only.

### 22.3. UPDATE has both

UPDATE needs both OLD and NEW whenever comparing states or computing deltas.

## 23. A Statement Affecting Zero Rows

~~~sql
UPDATE tt_lab.sales
SET amount = amount + 1
WHERE sale_id = -999;
~~~

An `AFTER STATEMENT` trigger can still fire for the event even when **0 rows** match the condition. In that case, the transition tables are empty.

In our lab:

- `audit_sales_statement` only inserts an audit row if `v_rows > 0`.
- `maintain_customer_summary` finds no grouped deltas to UPSERT.
- Nothing changes in the summary table.

Thus a statement-level trigger firing **does not guarantee** an audit row is written. Whether it writes depends on the trigger's logic.

### 23.1. COUNT(*) vs. SUM on empty sets

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total
FROM new_rows;
~~~

On an empty transition relation, `COUNT(*)=0`, while `SUM(amount)` is SQL NULL. Use `COALESCE` if zero is required.

## 24. An UPDATE Touching a Row With Unchanged Values

~~~sql
UPDATE tt_lab.sales
SET amount = amount
WHERE sale_id = 10;
~~~

This is still an UPDATE touching one matching row.

- Transition relations contain the corresponding before/after row images.
- `affected_rows` is 1, not automatically 0 just because amount did not change.
- Net deltas for `paid_total` and `sale_count` are 0.
- The lab's statement audit records an UPDATE with delta 0.
- The summary function filters out zero net deltas, avoiding a pointless summary UPDATE.

**"Row was updated"** and **"business values actually differed"** are two distinct concepts.

## 25. Comparing Old/New With IS DISTINCT FROM

When you need to know whether a field actually changed:

~~~sql
SELECT
    o.sale_id,
    o.status AS old_status,
    n.status AS new_status
FROM old_rows AS o
JOIN new_rows AS n
    ON n.sale_id = o.sale_id
WHERE o.status IS DISTINCT FROM n.status;
~~~

`IS DISTINCT FROM` has unambiguous semantics with SQL NULL, unlike `<>` which yields NULL when either side is NULL.

### 25.1. Combining multiple fields

~~~sql
WHERE ROW(
    o.customer_id,
    o.status,
    o.amount
) IS DISTINCT FROM ROW(
    n.customer_id,
    n.status,
    n.amount
)
~~~

Use this when auditing only meaningful business changes while ignoring `updated_at`.

### 25.2. Condition for accurate per-row OLD/NEW JOINs

Joining on `sale_id` assumes **that key does not change during the UPDATE**. If an UPDATE alters the join key itself, old and new rows will fail to pair up.

When you need per-row auditing and allow primary-key updates, use an **immutable identity** or another mechanism such as a row-level trigger; never assume transition tables secretly carry a hidden pairing ID linking old and new rows.

## 26. Per-Row Auditing Using Transition Tables

Transition tables are not limited to aggregates. You can use a set-based `INSERT ... SELECT` to write many detail records in **one statement**.

Create a JSONB audit table:

~~~sql
CREATE TABLE tt_lab.sale_change_audit (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id BIGINT NOT NULL,
    before_row JSONB,
    after_row JSONB,
    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

Create an UPDATE-specific function assuming `sale_id` never changes:

~~~sql
CREATE FUNCTION tt_lab.audit_sale_row_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO tt_lab.sale_change_audit (
        sale_id, before_row, after_row
    )
    SELECT
        n.sale_id,
        to_jsonb(o),
        to_jsonb(n)
    FROM old_rows AS o
    JOIN new_rows AS n
        ON n.sale_id = o.sale_id
    WHERE ROW(o.customer_id, o.status, o.amount)
          IS DISTINCT FROM
          ROW(n.customer_id, n.status, n.amount);

    RETURN NULL;
END;
$$;

CREATE TRIGGER sales_row_audit_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sale_row_changes();
~~~

Even though the audit table receives **one row per sale that actually changed**, the trigger function is invoked **only once per statement**.

### 26.1. Do not blindly put sensitive data into JSONB audits

`to_jsonb(o)`/`to_jsonb(n)` capture all columns from the row. In production, avoid dumping PII, tokens, secrets, or huge payloads into audits. Use `jsonb_build_object` to whitelist fields and enforce retention/access policies.

## 27. Do Not JOIN OLD/NEW If You Only Need Group Deltas

To update customer summaries, we do not need to pair every old/new sale row.

Compute:

~~~sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM new_rows
GROUP BY customer_id;
~~~

and:

~~~sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM old_rows
GROUP BY customer_id;
~~~

then combine contributions via `UNION ALL`. This remains exact even when `customer_id` changes, as long as each before/after contribution is computed accurately.

**Principle:** when the problem is a **set-wide net delta**, work on old-set and new-set as two independent relations; only JOIN row-by-row when business logic requires pairing old and new rows by identity.

## 28. Transition Tables and AFTER ROW Triggers

An eligible `AFTER ROW` trigger can also declare transition relations alongside its own `OLD`/`NEW` row records.

However, if it is called N times for N rows and scans the entire transition table each time, total work degrades to roughly N scans of N rows—extremely expensive.

When the goal is aggregating across the statement:

~~~sql
FOR EACH STATEMENT
~~~

is normally the right choice.

### 28.1. When AFTER ROW fits

- Action depends on a single row's identity.
- Needs per-row `OLD`/`NEW` for conditions or payload.
- Does not need to aggregate the entire set.
- Purpose-built row-level constraint or audit.

Do not convert every trigger to statement-level merely because you heard "set-based is always faster."

## 29. BEFORE ROW Triggers and NEW TABLE Data

A `BEFORE ROW` trigger can:

- Modify values in `NEW`.
- Reject or skip a row per trigger semantics.
- Apply normalization before INSERT/UPDATE.

An AFTER trigger's `NEW TABLE` reflects **the rows after statement processing**, not merely the raw client-supplied values.

For example, if a BEFORE INSERT trigger turns `'PAID'` into valid `'paid'`, the AFTER INSERT transition table contains the accepted normalized value.

### 29.1. Do not use transition tables to replace BEFORE validation

Transition tables exist only in eligible AFTER triggers. If a value must be normalized or rejected before storage, table constraints or BEFORE ROW triggers are the right place.

## 30. Constraint Triggers Differ From Transition-Table Triggers

**Constraint triggers** have distinct semantics for check timing and deferrability in supported PostgreSQL contexts.

Transition relations **cannot be used in constraint triggers**. Therefore, if a rule must be deferred until transaction end via a constraint trigger, you cannot simply add `REFERENCING OLD TABLE/NEW TABLE` to it.

To enforce cross-row invariants:

- Prefer declarative constraints (`UNIQUE`/`EXCLUDE`/`FK`) whenever possible.
- Consider statement-level AFTER triggers with transition tables when immediate post-statement checking is suitable.
- Design explicit transaction isolation or locking to prevent race conditions.
- Never assume an aggregate check under `READ COMMITTED` automatically acts as a concurrency-safe global constraint.

## 31. Transition Tables Cannot Be Used With TRUNCATE

`TRUNCATE` is a different event from `DELETE`:

~~~sql
TRUNCATE TABLE tt_lab.sales;
~~~

It is not handled by `AFTER DELETE ... REFERENCING OLD TABLE` as a row-by-row DELETE, and transition tables are not supported for TRUNCATE.

**Do not run TRUNCATE on the lab** if you want to preserve data and trigger state for later steps.

### 31.1. When summaries depend on source tables, TRUNCATE is a hazard

If an application holds `TRUNCATE` permission on the source table while summaries are maintained solely via INSERT/UPDATE/DELETE transition triggers, the summary table will drift out of sync.

System-appropriate safeguards:

- Restrict `TRUNCATE` privileges.
- Use a safe transactional reset procedure for both source and summary.
- Add a dedicated statement-level TRUNCATE trigger aligned with policy.
- Schedule summary rebuilds from source after planned bulk operations.

Never assume "every way of clearing a table goes through DELETE triggers."

## 32. Be Careful With INSERT ... ON CONFLICT DO UPDATE

An UPSERT statement:

~~~sql
INSERT INTO tt_lab.sales (
    sale_id, customer_id, status, amount
)
VALUES
    (10, 101, 'paid', 130.00),
    (20, 104, 'paid', 45.00)
ON CONFLICT (sale_id) DO UPDATE
SET
    customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    amount = EXCLUDED.amount,
    updated_at = statement_timestamp();
~~~

Within one statement:

- Row `sale_id=20` can be inserted.
- Row `sale_id=10` can take the UPDATE branch if it already exists.

PostgreSQL has specific rules firing statement-level INSERT and UPDATE triggers for `INSERT ... ON CONFLICT DO UPDATE`. Never assume only a single event type runs in audit/summary logic for the entire statement.

**Each event's transition tables hold only the rows belonging to that event**; summaries must process both inserts and updates when both occur.

### 32.1. Writing a single audit row for the entire SQL text?

The three lab triggers log per **event**, not necessarily one row for the whole UPSERT command when multiple event branches execute. If your audit contract demands one correlation ID and one row per request, aggregate/correlate at the proper layer; separate per-event transition tables do not automatically merge into one object.

### 32.2. Zero-row UPDATE event

An event-level statement trigger can run with an empty transition relation. In the lab, `v_rows > 0` prevents logging 0-row audits.

## 33. MERGE and Transition Relations

Modern PostgreSQL supports `MERGE` with conditional INSERT/UPDATE/DELETE branches.

When using triggers:

- Check your exact PostgreSQL version.
- Distinguish which rows were actually inserted, updated, or deleted.
- Understand that statement-level triggers for the specified events follow their own firing rules.
- Never assume one MERGE yields a single combined transition table across all actions.

For summaries, a **per-event** delta architecture works when each trigger event is validly fired by PostgreSQL. Always test against your exact server version and representative MERGE branches before production rollout.

### 33.1. Do not rely on MERGE syntax from other databases

SQL Server, Oracle, and PostgreSQL differ in trigger/MERGE details. Never infer PostgreSQL transition-table trigger behavior from other engines.

## 34. Partitioned Tables and Transition Relations

Partitioned tables introduce extra considerations:

- Does the statement target the parent table or a specific partition?
- Row-level triggers propagate to partitions under PostgreSQL rules.
- Statement-level triggers generally bind to the relation named in the statement.
- Transition relations can collect rows across affected partitions in supported PostgreSQL cases.
- Moving rows across partitions during UPDATE can have row-level trigger subtleties beyond intuitive "UPDATE only."

Never write business logic assuming "every partition shares one identical statement trigger." For partitioned tables, verify on your target PostgreSQL version and test INSERT/UPDATE/DELETE both through the parent and directly on partitions if permitted.

### 34.1. Be careful with partition-moving UPDATEs

When changing a partition key moves a row between partitions, PostgreSQL may execute DELETE/INSERT semantics at the row-trigger level while remaining an UPDATE at statement level. Verify transition relations and trigger placement across parent/partitions to avoid **double-counting deltas**.

## 35. Inheritance and Child Tables

PostgreSQL supports both table inheritance and declarative partitioning, and they do not share identical trigger and schema rules.

When updating a parent table that includes child-table rows, statement-trigger scope and transition relations depend on the target relation and execution path. Never assume a trigger on the parent is equivalent to triggers created separately on each child table.

A multi-table summary design must clarify:

- Which tables make up the source of truth?
- Can statements hit child tables directly?
- Where should triggers live?
- Is there any risk of missing or double-counting events?

## 36. Foreign Tables and Remote Changes

Foreign tables use FDWs to represent external data. Trigger and transition-table support differs from regular local tables.

Never treat `REFERENCING OLD TABLE/NEW TABLE` as a universal CDC mechanism for remote sources. To synchronize remote changes, evaluate:

- FDW capabilities specific to your adapter/version.
- Logical decoding/CDC at the source.
- Ingestion pipelines with event identifiers.
- Transactional/outbox patterns.

Transition tables on regular tables serve a single PostgreSQL statement; they **do not monitor external changes automatically**.

## 37. Transition Tables Are Not a Logical Replication Stream

A transition table:

- Exists only for the active trigger context.
- Represents only the rows touched by that statement/event.
- Is not a persistent table across sessions.
- Does not replace WAL-based logical decoding.
- Does not automatically retain durable history after the statement.

For long-term traceability, the trigger must **persist selected data** into an audit table or outbox within the transaction.

For cross-database or cross-service CDC, logical replication/CDC and application idempotency are usually better suited.

## 38. Migrating From Row-by-Row Triggers to Statement-Level

Suppose an old row-level trigger performed:

~~~text
Each sale UPDATE:
    read OLD/NEW
    compute delta
    UPDATE customer_summary
~~~

Migrating to transition tables:

~~~text
One multi-sale UPDATE:
    old_rows/new_rows
    GROUP BY customer_id
    compute net delta
    set-based UPSERT customer_summary
~~~

Migration steps:

1. Document exact semantics of the legacy trigger.
2. Inventory all statement types that can modify the source.
3. Build the new function and test in an isolated database.
4. Reconcile summary against direct `GROUP BY`.
5. Ensure both trigger systems never run simultaneously adding deltas.
6. Deploy inside an appropriate transactional DDL migration.
7. Monitor drift, contention, and regressions.

### 38.1. Double-counting risk during migration

If the legacy row-level trigger and the new statement-level transition trigger are active at the same time, an INSERT adds to the summary **twice**.

Perform a clean cutover—never just add the new trigger "to observe alongside" on the same live production summary.

## 39. Reconciling Summary With the Source of Truth

After running INSERT/UPDATE/DELETE operations in the lab:

~~~sql
WITH expected AS (
    SELECT
        customer_id,
        COUNT(*)::BIGINT AS sale_count,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'paid'),
            0::NUMERIC
        ) AS paid_total
    FROM tt_lab.sales
    GROUP BY customer_id
)
SELECT
    COALESCE(e.customer_id, s.customer_id)
        AS customer_id,
    e.sale_count AS expected_count,
    s.sale_count AS stored_count,
    e.paid_total AS expected_paid_total,
    s.paid_total AS stored_paid_total
FROM expected AS e
FULL JOIN tt_lab.customer_summary AS s
    USING (customer_id)
WHERE e.sale_count IS DISTINCT FROM s.sale_count
   OR e.paid_total IS DISTINCT FROM s.paid_total
ORDER BY customer_id;
~~~

**Note:** a customer with a 0/0 summary after their last sale is deleted will appear as a "difference" because `expected` has no row for that customer. That can be an **intentional representation difference permitted by policy**, not necessarily an arithmetic bug.

### 39.1. Reconciliation handling zero-summary rows

If the design permits 0/0 summary rows, compare using `COALESCE`:

~~~sql
WITH expected AS (
    SELECT customer_id,
           COUNT(*)::BIGINT AS sale_count,
           COALESCE(
               SUM(amount) FILTER (WHERE status='paid'),
               0::NUMERIC
           ) AS paid_total
    FROM tt_lab.sales
    GROUP BY customer_id
),
actual AS (
    SELECT customer_id, sale_count, paid_total
    FROM tt_lab.customer_summary
)
SELECT
    COALESCE(e.customer_id, a.customer_id) AS customer_id,
    COALESCE(e.sale_count, 0) AS expected_count,
    COALESCE(a.sale_count, 0) AS actual_count,
    COALESCE(e.paid_total, 0) AS expected_paid,
    COALESCE(a.paid_total, 0) AS actual_paid
FROM expected e
FULL JOIN actual a USING (customer_id)
WHERE COALESCE(e.sale_count, 0)
      IS DISTINCT FROM COALESCE(a.sale_count, 0)
   OR COALESCE(e.paid_total, 0)
      IS DISTINCT FROM COALESCE(a.paid_total, 0)
ORDER BY customer_id;
~~~

An empty result means **no discrepancy on either metric** at that query snapshot. It does not prove every other column or historical audit entry is error-free.

## 40. Ordering Inside Transition Relations Is Not Guaranteed

Transition tables are **relations**. Querying:

~~~sql
SELECT * FROM new_rows;
~~~

does not guarantee row order matching `VALUES` or client submission order.

If you need ID ordering:

~~~sql
SELECT *
FROM new_rows
ORDER BY sale_id;
~~~

Similarly, `jsonb_agg` or `array_agg` inside a trigger must include `ORDER BY` inside the aggregate if array order is a business requirement.

### 40.1. Do not confuse with event ordering

In a multi-row statement, "which row was processed first" should not become a business contract unless SQL defines it. For durable operation ordering, generate an explicit sequence or logical key under a controlled design.

## 41. Transition Tables Can Be Joined With Other Tables

Transition relations behave like normal relations inside queries:

~~~sql
SELECT
    n.customer_id,
    COUNT(*) AS updated_rows
FROM new_rows AS n
JOIN (
    SELECT DISTINCT customer_id
    FROM tt_lab.sales
) AS c
    ON c.customer_id = n.customer_id
GROUP BY n.customer_id;
~~~

This illustrates general query shape inside a compatible trigger—not a standalone SQL query outside a trigger (since `new_rows` does not exist outside that context).

### 41.1. Watch out for fan-out JOINs

Joining against a one-to-many table multiplies rows. To compute `COUNT(*)` or `SUM(amount)` over a transition table accurately, ensure joins do not duplicate contributions, or aggregate the source first.

### 41.2. When you only need columns already in the transition relation

Do not re-join the source table to fetch columns already present in `new_rows`. That adds I/O and risks unnecessary visibility or locking issues.

## 42. Updating Summary Tables With UPSERT

In the lab:

~~~sql
INSERT INTO tt_lab.customer_summary AS s (
    customer_id, sale_count, paid_total
)
SELECT
    customer_id,
    COUNT(*)::BIGINT,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0::NUMERIC
    )
FROM new_rows
GROUP BY customer_id
ON CONFLICT (customer_id) DO UPDATE
SET sale_count = s.sale_count + EXCLUDED.sale_count,
    paid_total = s.paid_total + EXCLUDED.paid_total;
~~~

Mechanics:

1. Aggregate transition rows by customer.
2. If the customer has no summary row yet, insert one.
3. If one exists, add the delta to current values.
4. PostgreSQL enforces appropriate locking and constraints.

**Do not do this:**

~~~sql
-- Buggy pattern if multiple NEW rows share customer_id:
INSERT INTO summary
SELECT customer_id, 1, amount
FROM new_rows
ON CONFLICT (customer_id) DO UPDATE ...;
~~~

A single `INSERT ... ON CONFLICT DO UPDATE` command cannot arbitrarily update the same target row multiple times; duplicate keys in the input must be grouped first.

## 43. Concurrency and Transactional Consistency

Suppose two transactions concurrently insert different sale rows for customer 101. If each transaction computes its delta from its own transition rows and runs UPSERT:

~~~sql
paid_total = paid_total + EXCLUDED.paid_total
~~~

PostgreSQL leverages UPSERT's locking/concurrency mechanics to update against the latest row state, avoiding classic **lost updates** caused by two uncoordinated read-then-write statements.

Still, do not conclude every concurrency invariant is automatically guaranteed.

### 43.1. Avoid read-summary-then-overwrite patterns

An unsafe pattern:

~~~text
SELECT paid_total FROM customer_summary
Compute v_new_total in application
UPDATE customer_summary SET paid_total = v_new_total
~~~

If two transactions read the same old value, one update overwrites the other without locking or version checks.

Adding deltas directly inside `ON CONFLICT DO UPDATE` is generally far safer for accumulators.

### 43.2. Deadlocks can still happen

If one statement touches multiple customer summaries, two concurrent transactions can lock customer rows in opposite orders and deadlock. Therefore:

- Consider ordering inputs by `customer_id` when building UPSERTs.
- Keep transactions short.
- Avoid multiple triggers updating the same tables in inconsistent orders.
- Implement transaction retries for deadlocks and serialization failures per policy.
- Benchmark under concurrency.

## 44. CHECK Constraints on Summary Tables Do Not Replace Reconciliation

In the lab:

~~~sql
sale_count BIGINT CHECK (sale_count >= 0)
paid_total NUMERIC CHECK (paid_total >= 0)
~~~

prevent negative values. Yet a summary inflated by +100 is still non-negative, so CHECK cannot catch the drift.

Therefore you need:

- Constraints guarding valid value ranges.
- Accurate delta triggers.
- An accurate baseline.
- Periodic or batch reconciliation queries.
- A documented rebuild procedure from the source table if drift occurs.

**Constraints and audits are complementary defenses, not substitutes for reconciling against the source of truth.**

## 45. Statement-Level Triggers Can Process Zero Rows

An easily overlooked point: statement-level triggers fire per **statement**, without requiring at least one row to have changed.

Example:

~~~sql
DELETE FROM tt_lab.sales
WHERE sale_id = -100;
~~~

The `AFTER DELETE` trigger still runs with an empty `old_rows`.

Consequences if unhandled:

- `SUM` returns NULL.
- `INSERT ... SELECT GROUP BY` returns zero rows.
- An unguarded `INSERT audit VALUES (...)` writes a spurious zero-row audit entry.
- Code assuming a row exists and using `SELECT INTO STRICT` throws an exception.

Decide on your policy for no-op statements and write explicit `COUNT(*)` / `IF v_rows > 0` checks as shown in the lab.

## 46. Statement Triggers Do Not Prove External Request Success

A trigger can insert an audit record inside the transaction. If the caller subsequently runs `ROLLBACK`:

- Changes to `sales` roll back.
- Summary-table changes roll back.
- Audit rows roll back.
- Identity sequence counters may not rewind.

Thus a surviving audit row reflects a committed transaction under transactional rules, though `audit_id` is not proof of global commit order.

To emit messages externally after commit, use a **transactional outbox** with a background publisher rather than calling external services inside triggers.

## 47. A Statement-Level Outbox

Conceptual example:

~~~sql
CREATE TABLE tt_lab.outbox_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    published_at TIMESTAMPTZ
);
~~~

Inside the trigger function you can write:

~~~sql
INSERT INTO tt_lab.outbox_events (
    event_type, payload
)
SELECT
    'sales_batch_inserted',
    jsonb_build_object(
        'sale_ids',
        COALESCE(
            jsonb_agg(sale_id ORDER BY sale_id),
            '[]'::jsonb
        )
    )
FROM new_rows
HAVING COUNT(*) > 0;
~~~

This `INSERT ... SELECT` is a **pattern meant to run inside an AFTER INSERT trigger function declaring `NEW TABLE AS new_rows`**, not standalone in a SQL client.

### 47.1. An outbox does not publish messages by itself

A separate publisher reads, dispatches, and marks events; it must handle retries, idempotency, and partial publish/ack failures. Transition tables simply collect the event payload set-wise within the same transaction.

### 47.2. Do not build oversized arrays

A statement inserting millions of rows could build a massive JSONB payload, straining memory and object-size limits. For large bulk changes, outbox records should carry batch IDs, key ranges, or chunked messages.

## 48. Transition Tables vs. Materialized Views

Transition tables:

- Exist temporarily inside triggers.
- Hold rows affected by a single statement/event.
- Useful for computing deltas.

Materialized views:

- Persistent objects storing query results.
- Refreshed via `REFRESH MATERIALIZED VIEW`.
- Do not incrementally self-update merely because transition tables exist on the source table.

The lab's `customer_summary` is a **regular table maintained by triggers**. It is not a PostgreSQL materialized view and has no `REFRESH MATERIALIZED VIEW` command.

### 48.1. When to use direct queries vs. materialized views?

- Direct query: simple logic, results must reflect current data, cost is acceptable.
- Materialized view: reports where periodic staleness between refreshes is acceptable.
- Summary table + transition triggers: near-real-time transactional totals, at the expense of write overhead and trigger maintenance.

## 49. Caution When Changing Source Table Schemas

If `tt_lab.sales` gains a new column:

~~~sql
ALTER TABLE tt_lab.sales
ADD COLUMN channel TEXT;
~~~

transition relations automatically reflect the updated table shape. Queries selecting only `customer_id`, `status`, and `amount` keep working if the new column does not alter business rules.

However, renaming or changing the data type of a column referenced by the trigger function can break SQL inside the routine or change semantics.

### 49.1. Prefer explicit column selection

For auditing:

~~~sql
SELECT to_jsonb(n)
FROM new_rows AS n;
~~~

automatically exposes newly added table columns, which is not always desirable.

To keep event contracts stable:

~~~sql
SELECT jsonb_build_object(
    'sale_id', n.sale_id,
    'customer_id', n.customer_id,
    'status', n.status,
    'amount', n.amount
)
FROM new_rows AS n;
~~~

Whitelisting fields prevents accidentally leaking newly added sensitive columns after schema migrations.

## 50. Inspecting Triggers in System Catalogs

PostgreSQL exposes `pg_trigger` alongside `pg_class` and `pg_namespace`.

Example:

~~~sql
SELECT
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_state,
    pg_get_triggerdef(t.oid, TRUE) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'tt_lab'
  AND c.relname = 'sales'
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

`pg_get_triggerdef` reconstructs the SQL definition stored by PostgreSQL, including `REFERENCING` clauses where present.

### 50.1. psql meta-command

~~~text
\d+ tt_lab.sales
~~~

inspects the table and triggers inside psql. This is not SQL to send over JDBC.

### 50.2. Inspecting trigger functions

~~~sql
SELECT pg_get_functiondef(
    'tt_lab.maintain_customer_summary()'::regprocedure
);
~~~

Verifies the live function body on the server. Note that output is reconstructed from catalog data and need not preserve original migration-file formatting.

## 51. Enabling/Disabling Triggers: Summary Drift Risk

You can run:

~~~sql
ALTER TABLE tt_lab.sales
DISABLE TRIGGER sales_summary_insert;
~~~

or:

~~~sql
ALTER TABLE tt_lab.sales
ENABLE TRIGGER sales_summary_insert;
~~~

**Never run these commands in production without a plan.** If INSERTs happen while the summary trigger is disabled, the source table changes while the summary falls behind.

### 51.1. When is a rebuild needed?

If you must import massive data and intentionally disable maintenance triggers, follow a strict procedure:

1. Lock or control writes / establish a consistent snapshot.
2. Import the data.
3. Rebuild the summary from the source of truth.
4. Reconcile metrics.
5. Re-enable triggers.
6. Reopen normal writes per plan.

**Never just re-enable the trigger assuming skipped changes will replay automatically.**

## 52. Rebuilding the Summary From Source

In an isolated lab scenario, after confirming privileges and blocking writers appropriately, one rebuild pattern is:

~~~sql
BEGIN;

LOCK TABLE tt_lab.sales IN SHARE MODE;

DELETE FROM tt_lab.customer_summary;

INSERT INTO tt_lab.customer_summary (
    customer_id, sale_count, paid_total
)
SELECT
    customer_id,
    COUNT(*)::BIGINT,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0::NUMERIC
    )
FROM tt_lab.sales
GROUP BY customer_id;

COMMIT;
~~~

This is an **operational pattern requiring careful review**, not a turnkey production runbook. Lock modes, isolation, concurrent writers, partitions, timeouts, and data size must be evaluated realistically.

### 52.1. Why synchronize snapshots and writers?

If writers modify `sales` while the summary is being wiped/rebuilt and triggers are concurrently adding deltas, totals will be under- or double-counted.

Production rebuilds must define who may write during the window and how catch-up is synchronized.

### 52.2. Zero-summary rows after rebuild

The rebuild above creates summary rows only for customers currently having sales rows. Customers whose sales were all deleted earlier will no longer have 0/0 summary rows. That does not affect totals if the API treats missing rows as 0, yet it breaks contracts requiring every customer key to remain present.

## 53. Performance of Transition Tables

Costs to weigh:

- PostgreSQL must collect and buffer the affected before/after rows.
- Scanning transition rows for grouping and aggregation.
- Memory or temporary-file I/O if the modified set is huge.
- Indexes, constraints, and WAL for audit and summary tables.
- Locks and contention on hot summary keys.
- Number of triggers and inner SQL statements.
- PL/pgSQL planning and execution overhead.
- Volume of rows actually touched in one statement.

For a 5-row UPDATE, a simple row-level trigger may already be plenty fast. For a 100,000-row UPDATE on the same customer, aggregating once per customer slashes summary writes, despite the cost of materializing transition relations.

**Never claim transition tables are faster in every case**; benchmark on your actual workload.

## 54. EXPLAIN and Measuring Trigger Internals

You can inspect DML with:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE tt_lab.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 14;

ROLLBACK;
~~~

`EXPLAIN ANALYZE` **executes the UPDATE**, so the example wraps it in a lab transaction to roll back transactional writes.

Depending on plan type and PostgreSQL version, output can show execution timing for triggers and constraint triggers, though it does not automatically break out every inner SQL statement inside PL/pgSQL trigger functions as a nested query plan.

### 54.1. Metrics to measure

- Total statement duration with and without triggers.
- Number of rows modified.
- Number of distinct `customer_id`s in transition relations.
- Number of summary rows upserted.
- WAL volume.
- Buffer hits/reads/writes.
- Temporary files and memory usage.
- Lock waits and deadlocks.
- p95/p99 latency under concurrency.
- Summary accuracy after each event type.

### 54.2. Measure baseline before optimizing

A trigger collapsing 10,000 updates into 20 group updates can greatly help typical workloads, yet raise memory usage during giant batches. Measure before and after with realistic data volumes and `customer_id` distributions.

## 55. Complex Business Conditions and Grouping Expressions

Trigger aggregations are not restricted to `customer_id`. You can group by:

- Customer.
- Product.
- Day/month.
- Region.
- Currency.
- Multi-dimensional combinations.

Conceptual example:

~~~sql
SELECT
    customer_id,
    DATE(updated_at) AS change_date,
    COUNT(*) AS changed_rows
FROM new_rows
GROUP BY customer_id, DATE(updated_at);
~~~

**Timestamp caveat:** a row's `updated_at` is not necessarily the business event time or commit time. For accounting-day aggregations, define timezone, business timestamp, and rules unambiguously.

### 55.1. Watch out for changing group keys

If an UPDATE can change `region` or `customer_id`, subtract contributions from the **old group key** and add to the **new group key**—never update only the new group.

### 55.2. Multi-dimensional aggregates can increase contention

If a hot key is updated constantly across concurrent transactions, the summary table becomes a lock bottleneck. Consider sharding, batching, asynchronous aggregation, or a different data model for high throughput.

## 56. Avoid Rounding Drift When Computing Deltas

In this lesson, `amount NUMERIC(12,2)` and `paid_total NUMERIC(18,2)` model currency requiring exact decimal precision.

Using `DOUBLE PRECISION` for money introduces floating-point inaccuracies that cause summaries to fail exact-equality reconciliation.

Rules:

- Use `NUMERIC` or smallest integer currency units per business contract.
- Enforce consistent scale and rounding where amounts originate.
- For multiple currencies, **group by currency** rather than adding different currencies together.
- Watch out for numeric overflow and precision limits.

## 57. Triggers Issuing DML Can Cause Recursion

A trigger on `sales` inserts into `statement_audit` and upserts `customer_summary`. In our lab, those two target tables **have no triggers updating `sales`**, so no recursive cycle forms.

In real systems:

~~~text
sales trigger
   |
   v
UPDATE summary
   |
   v
summary trigger
   |
   v
UPDATE sales
   |
   v
sales trigger ...
~~~

risks unintended recursion.

### 57.1. pg_trigger_depth does not replace good design

PostgreSQL provides `pg_trigger_depth()` to inspect current trigger depth, yet disabling logic solely on depth conditions can mask real business bugs.

Design unidirectional write flows, keep responsibilities clearly separated, and test changes that can chain across triggers.

## 58. Why Not Use a Statement Trigger to "Block" All Invalid Data?

Transition tables are available in AFTER triggers. If an AFTER trigger detects an invalid invariant, it can `RAISE EXCEPTION` to fail the statement and roll back transactional changes.

However, doing so wastes work before detecting the error, and under concurrent transactions an unguarded aggregate query is not a globally safe constraint.

Prefer whenever possible:

- `NOT NULL`, `CHECK`.
- `UNIQUE`, `EXCLUDE`.
- `FOREIGN KEY`.
- Proper schema constraints.
- Row-Level Security / authorization.
- Serializable transactions or explicit locking for complex cross-row invariants.

Transition tables excel at **processing or reconciling changed row sets**, not replacing every database integrity mechanism.

## 59. Securing Trigger Functions

Trigger functions execute with role privileges determined by `SECURITY INVOKER`/`SECURITY DEFINER` and ownership rules.

Never grant overly broad privileges just so a trigger can write to an audit table.

If using `SECURITY DEFINER`:

~~~sql
CREATE FUNCTION tt_lab.some_privileged_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tt_lab, pg_temp
AS $$
BEGIN
    -- Reference objects with full schema qualification.
    RETURN NULL;
END;
$$;
~~~

ensure:

- A trusted owner with least privilege.
- A safe `search_path` excluding schemas where untrusted users can create objects.
- Schema-qualified table and function names in the body.
- Strict control over who can alter the function or schema.
- No raw dynamic identifiers from user input.
- No secrets or sensitive data leaked in exceptions or audits.

### 59.1. Triggers do not replace RLS policies

When tenant isolation is required, verify RLS, read/write grants, and access paths for both source and summary tables. Never assume that because a summary table is populated by triggers, queries reading the summary are automatically tenant-filtered.

## 60. Privileges to Create Triggers and Access Target Tables

Creating/attaching triggers requires appropriate privileges on the source table and trigger function per PostgreSQL rules. Privileges on tables queried or modified inside the trigger function depend on the execution security context.

In multi-role systems:

- Migration role creates tables, triggers, and functions.
- Application role executes DML within granted limits.
- Audit/reporting roles receive appropriate read access.
- `SECURITY DEFINER` owner (if needed) holds strictly scoped privileges.

Never fix a permission error by granting superuser to the application.

## 61. Triggers and Row-Level Security

RLS can govern which rows the caller may modify and which rows the trigger function can read under its security context, depending on ownership, policies, and operations.

When a transaction updates 10 rows, transition tables contain only the rows touched within that event—they do not expose every tenant's data.

Summary tables can leak metrics if shared across tenants. A summary keyed solely by `customer_id` when `customer_id` is not globally unique mixes tenant data; in multi-tenant designs, include `tenant_id` in the grouping key or guarantee global key uniqueness by contract.

## 62. Transition Tables and Exact Per-Change Auditing

When audit requirements demand:

- Who made the edit?
- Exact before/after values per row?
- Correlation/request ID?
- Business reason?
- Commit timestamp?
- Cross-table impact?

transition tables provide **old/new row values** within the event scope, yet cannot safely and durably supply all of that context on their own.

Design for:

- Application-supplied context (trusted role/request ID propagation).
- Stable audit table schemas.
- Permissions and retention.
- Idempotency.
- Correlation across multiple statements within one transaction.
- Accurate distinction between statement, transaction, and commit timestamps.

Never call `statement_timestamp()` a "commit timestamp"; they are different points in time.

## 63. One Row May Be Modified by Multiple Statements in a Transaction

Example:

~~~sql
BEGIN;

UPDATE tt_lab.sales
SET amount = amount + 10
WHERE sale_id = 10;

UPDATE tt_lab.sales
SET status = 'paid'
WHERE sale_id = 10;

COMMIT;
~~~

Two UPDATE statements trigger **two separate `AFTER UPDATE` statement triggers**, each with its own transition relations, even for the same `sale_id` in the same transaction.

Consequently:

- Transition tables do **not** aggregate across an entire transaction.
- Statement-level auditing differs from transaction-level or request-level auditing.
- If you need to reconcile a "per-transaction net delta," build a separate aggregation/correlation layer.

## 64. Triggers Can Fire Triggers via Inner SQL

A trigger function performing DML on another table can fire triggers on that target table. All effects remain within the enclosing transaction.

When drawing dependency graphs, map:

~~~text
source DML
   |
   +--> trigger A -> audit table INSERT
   |
   +--> trigger B -> summary UPSERT
                          |
                          +--> summary triggers (if any)
~~~

Never analyze triggers in isolation when deep chains exist; evaluate lock/deadlock ordering, recursion, error propagation, and total cost.

## 65. DML With RETURNING: When Are Triggers Unnecessary?

If the application simply needs to see the newly modified rows, PostgreSQL supports `RETURNING`:

~~~sql
UPDATE tt_lab.sales
SET status = 'paid'
WHERE sale_id = 10
RETURNING sale_id, customer_id, status, amount;
~~~

The application receives those rows directly in the statement response without needing a trigger to read new values.

However, `RETURNING`:

- Applies only to the caller's specific DML statement.
- Does not ensure every code path maintains audits or summaries.
- Does not replace full old/new transition tables across all syntaxes/versions.
- Does not coordinate dependencies when multiple writers use different APIs.

### 65.1. When to choose triggers?

When an invariant, audit, or summary must apply **centrally** across multiple writer paths without relying on every application to remember updating auxiliary tables.

### 65.2. When to choose application logic?

When business workflows coordinate multiple services or rely on context unavailable in the DB, with transactions and outboxes controlled by the application. Never update the same summary in both triggers and application code or you will double-count.

## 66. MERGE, UPSERT, and COPY With Large Datasets

For bulk ingestion:

- `INSERT ... VALUES (...), (...)` supplies many rows in one statement.
- `INSERT ... SELECT` can affect huge sets.
- `COPY FROM` follows PostgreSQL INSERT trigger semantics, requiring care on large datasets.
- `INSERT ... ON CONFLICT DO UPDATE` can exercise multiple event branches.
- `MERGE` has version- and branch-dependent event/trigger semantics.

Transition tables process **the event's rows cleanly**, yet huge transition sets consume memory and temp I/O. For multi-million-row bulk loads, evaluate chunked imports, batch summary rebuilds, and monitoring rather than assuming incremental triggers are always fastest.

## 67. Testing Across Diverse Modification Patterns

A thorough lab test suite should cover:

1. INSERT a single draft row.
2. INSERT multiple paid/draft rows for the same customer.
3. UPDATE amount on a paid sale.
4. UPDATE draft -> paid.
5. UPDATE paid -> cancelled.
6. UPDATE `customer_id`.
7. UPDATE status and amount simultaneously.
8. UPDATE a non-metric field.
9. UPDATE 0 rows.
10. DELETE a paid row.
11. DELETE a cancelled row.
12. DELETE 0 rows.
13. `INSERT ON CONFLICT DO UPDATE` hitting both insert and update paths.
14. Two concurrent transactions updating the same summary key.
15. `ROLLBACK` after DML.
16. Oversized batch or lock contention.
17. `TRUNCATE` according to defined policy.
18. Source schema changes and audit output contracts.

Reconcile against source aggregations after each test group—never assume correctness just because no trigger threw an error.

## 68. Transition-Table Trigger Design Checklist

**Semantics:**

- Is the event INSERT, UPDATE, or DELETE?
- Do you need OLD, NEW, or both?
- Do you need per-statement totals or per-row auditing?
- Do you need to pair individual OLD–NEW rows?
- Is the pairing key immutable during UPDATE?
- Can the grouping key change?
- Can zero rows be affected?
- Are NULLs and status values handled properly?
- Is ordering required? If so, did you add `ORDER BY`?

**Schema and DDL:**

- Is the trigger AFTER on an eligible table type?
- Is it not a constraint trigger?
- Did you avoid `UPDATE OF` with transition relations?
- Do aliases in `REFERENCING` match the function body?
- Are UPSERT, MERGE, and partition paths accounted for?
- Is TRUNCATE handled or restricted?
- Are source and summary baselines consistent?

**Operations:**

- Are privileges and security contexts properly configured?
- Are double-counting risks prevented?
- Does UPSERT aggregate inputs before `ON CONFLICT`?
- Are concurrency and deadlock retry policies in place?
- Is periodic metric reconciliation scheduled?
- Have latency, WAL, and locks been measured?
- Are rebuild and rollback plans documented?
- Are batch sizes and audit retention controlled?

## 69. Common Mistakes

### Mistake 1 — Using OLD TABLE in a BEFORE trigger

Transition relations are only for eligible AFTER triggers.

### Mistake 2 — Using UPDATE OF amount with REFERENCING

Column-specific UPDATE triggers cannot be combined with transition relations.

### Mistake 3 — Confusing OLD/NEW records with old_rows/new_rows

`OLD.amount` is for row-level triggers; `SELECT ... FROM old_rows` queries a transition relation.

### Mistake 4 — Treating transition tables as permanent tables

They exist only during trigger execution, not as persistent tables after the statement.

### Mistake 5 — Assuming they contain the entire source table

They contain only the rows touched by the statement's event, not all existing rows.

### Mistake 6 — Looking only at NEW on UPDATE

Misses old contributions, especially when status or `customer_id` changes.

### Mistake 7 — Joining OLD/NEW on a mutable key

Pairing breaks or drops rows. Use a stable identity or aggregate both sets independently.

### Mistake 8 — Using SUM without COALESCE

`SUM` over an empty set returns NULL.

### Mistake 9 — Inserting empty audit rows on 0-row statements

Define policy clearly and check `COUNT(*)`.

### Mistake 10 — ON CONFLICT with duplicate group keys in input

Aggregate/deduplicate before upserting into the same target key.

### Mistake 11 — Leaving both legacy row triggers and new statement triggers enabled

Causes summary double-counting.

### Mistake 12 — Overlooking TRUNCATE

TRUNCATE does not fire DELETE transition-table triggers.

### Mistake 13 — Assuming UPSERT emits INSERT events only

`ON CONFLICT DO UPDATE` also exercises UPDATE event logic per rules.

### Mistake 14 — Assuming partition triggers behave identically to plain tables

Verify parent, partition, and row-movement behavior on your version.

### Mistake 15 — Assuming AFTER means already committed

Triggers remain inside the transaction and can roll back.

### Mistake 16 — Performing external side effects in triggers expecting rollback

External services do not roll back with PostgreSQL; use an outbox and idempotency.

### Mistake 17 — Auditing all columns with to_jsonb without PII review

Can leak sensitive data and bloat storage.

### Mistake 18 — Ignoring contention on hot summary keys

Concurrent writers can suffer lock waits and deadlocks.

### Mistake 19 — Comparing FLOAT money totals for exact equality

Introduces rounding drift; use exact decimal types like `NUMERIC`.

### Mistake 20 — Treating the summary table as the sole source of truth

Reconcile against `sales` and rebuild when discrepancies occur.

### Mistake 21 — Disabling triggers and forgetting to rebuild

Skipped changes do not replay automatically after `ENABLE`.

### Mistake 22 — Assuming transition relations have deterministic order

Relations have no guaranteed order; add `ORDER BY` when order matters.

### Mistake 23 — Building giant JSONB arrays

Causes memory/network spikes and hits size limits.

### Mistake 24 — Leaving EXECUTE unrestricted on trigger functions

Enforce safe security context and least privilege.

### Mistake 25 — Using unlocked transition triggers as cross-row constraints

An aggregate query inside an AFTER trigger is not automatically safe under all concurrency levels.

### Mistake 26 — Benchmarking only 1-row UPDATEs

Test workloads reflecting realistic batch sizes, distinct grouping keys, and concurrency.

## 70. Practice Exercises

### Exercise 1 — Concept

Is a transition table a persistent table containing the entire source table?

**Hint:** No; it holds only rows affected by the statement/event inside the trigger.

### Exercise 2 — INSERT

Write an AFTER INSERT trigger with `REFERENCING NEW TABLE AS new_rows`.

**Hint:** `FOR EACH STATEMENT EXECUTE FUNCTION ...`.

### Exercise 3 — DELETE

Write an AFTER DELETE trigger referencing `OLD TABLE`.

**Hint:** `REFERENCING OLD TABLE AS old_rows`.

### Exercise 4 — UPDATE

How many transition relations does an AFTER UPDATE trigger need to compute per-customer deltas?

**Hint:** Both OLD and NEW.

### Exercise 5 — OLD vs. old_rows

What is the difference between `OLD.amount` and `SELECT SUM(amount) FROM old_rows`?

**Hint:** A single row record vs. a set relation.

### Exercise 6 — AFTER

Why can't BEFORE triggers use transition tables?

**Hint:** Syntax and execution-timing restrictions.

### Exercise 7 — Constraint trigger

Can you add `REFERENCING` transition tables to a constraint trigger?

**Hint:** No.

### Exercise 8 — UPDATE OF

Is `AFTER UPDATE OF status ... REFERENCING OLD TABLE ...` valid?

**Hint:** No; use `AFTER UPDATE` and filter changes inside the function.

### Exercise 9 — INSERT 100 rows

How many times does a `FOR EACH STATEMENT` trigger run for a single `INSERT VALUES` with 100 rows?

**Hint:** Once for that statement event, not 100 times.

### Exercise 10 — UPDATE 0 rows

Can an `AFTER STATEMENT` trigger still run?

**Hint:** Yes, with an empty transition relation.

### Exercise 11 — COUNT and SUM

What do `COUNT(*)` and `SUM(amount)` return on an empty transition table?

**Hint:** 0 and NULL.

### Exercise 12 — Paid delta for INSERT

Write `GROUP BY customer_id` on `new_rows` using `SUM(amount) FILTER (WHERE status='paid')`.

**Hint:** Use `COALESCE` to get 0.

### Exercise 13 — Paid delta for DELETE

What sign must old contributions carry?

**Hint:** Negative.

### Exercise 14 — Reassigning customer

OLD customer 101 paid 100, NEW customer 102 paid 150. Compute deltas for both groups.

**Hint:** 101: -1 / -100; 102: +1 / +150.

### Exercise 15 — UNION ALL

Why combine old/new contributions with `UNION ALL` and `GROUP BY` a second time?

**Hint:** Produces a single net delta per group key, even when keys change.

### Exercise 16 — Duplicate UPSERT sources

Why must you `GROUP BY` before `ON CONFLICT DO UPDATE`?

**Hint:** Avoids touching the same target row multiple times in a single command.

### Exercise 17 — Unchanged business fields

Does an UPDATE touching only `updated_at` produce a non-zero paid delta?

**Hint:** No.

### Exercise 18 — IS DISTINCT FROM

Why is this operator suitable when fields are nullable?

**Hint:** Handles NULL deterministically.

### Exercise 19 — Pairing old and new

When is joining `old_rows` and `new_rows` on `sale_id` unsafe?

**Hint:** When `sale_id` itself can be updated.

### Exercise 20 — Per-row auditing

Use `INSERT INTO audit SELECT ... FROM old_rows JOIN new_rows ...` to write multiple audit records in a single trigger call.

**Hint:** Whitelist fields and require a stable key.

### Exercise 21 — Transactions

If the caller runs `ROLLBACK`, does the summary table updated by the trigger also roll back?

**Hint:** Yes, since it is transactional DML in the same transaction.

### Exercise 22 — Commit timestamp

Is `statement_timestamp()` the commit timestamp?

**Hint:** No.

### Exercise 23 — TRUNCATE

Does TRUNCATE fire AFTER DELETE transition triggers like DELETE?

**Hint:** No.

### Exercise 24 — UPSERT

Which events can an `INSERT ON CONFLICT DO UPDATE` pass through?

**Hint:** Both INSERT and UPDATE according to the relevant branches and trigger rules.

### Exercise 25 — MERGE

Why must semantics be verified on your target PostgreSQL version?

**Hint:** Multiple action branches, event triggers, and transition sets.

### Exercise 26 — Partitioned tables

Why shouldn't you blindly attach triggers to both parent and partitions on simple assumptions?

**Hint:** Risk of double-counting or missing events due to event semantics.

### Exercise 27 — Foreign tables

Can transition tables serve as a mechanism to capture all changes in a remote DB?

**Hint:** No.

### Exercise 28 — CDC

Do transition tables replace logical replication / WAL decoding?

**Hint:** No, they are scoped to a single statement/event.

### Exercise 29 — Materialized views

Is a trigger-maintained summary table a materialized view?

**Hint:** No.

### Exercise 30 — Baseline

If `sales` already has data while `customer_summary` is empty, how do you start incremental maintenance?

**Hint:** Rebuild a consistent baseline first.

### Exercise 31 — Reconciliation

Write a `SELECT ... GROUP BY customer_id` query to compare against `customer_summary`.

**Hint:** `COUNT` and `SUM ... FILTER` for paid rows.

### Exercise 32 — Zero-summary rows

If a customer has a 0/0 summary row and no remaining sales, is that necessarily an error?

**Hint:** Depends on contract; compare with `COALESCE` if permitted.

### Exercise 33 — Lock contention

What is the risk when many transactions concurrently UPSERT customer 101?

**Hint:** Lock waits, deadlocks, and reduced throughput.

### Exercise 34 — Lost update

Why is `SET paid_total=s.paid_total+EXCLUDED.paid_total` better than reading the total externally and overwriting it?

**Hint:** Applies an atomic delta against the current row state under UPSERT locking.

### Exercise 35 — Outbox

Why shouldn't triggers call external APIs directly to publish events?

**Hint:** External actions do not roll back with the DB.

### Exercise 36 — Large JSONB payloads

If a statement affects 2 million sale rows, should you `jsonb_agg` every row into a single outbox event?

**Hint:** Usually no; use batches or batch IDs.

### Exercise 37 — Security

What must a `SECURITY DEFINER` trigger function protect?

**Hint:** Owner, `search_path`, grants, schema qualification, and authorization.

### Exercise 38 — RLS

What can a summary table lacking `tenant_id` cause when IDs are not globally unique?

**Hint:** Cross-tenant mixing and data leakage.

### Exercise 39 — Disabling triggers

If you disable a summary trigger for a bulk load and re-enable it afterwards, does it automatically replay skipped changes?

**Hint:** No; you must rebuild or catch up.

### Exercise 40 — pg_get_triggerdef

Write a query to inspect trigger definitions on `tt_lab.sales`.

**Hint:** `pg_trigger` combined with `pg_get_triggerdef`.

### Exercise 41 — DML EXPLAIN

Why should `EXPLAIN ANALYZE UPDATE` run inside a lab transaction?

**Hint:** Because it executes the real DML.

### Exercise 42 — Row triggers vs. statement triggers

When is a row-level trigger better than transition tables?

**Hint:** Per-row validation or transformations tied to individual `OLD`/`NEW` rows.

### Exercise 43 — GROUP BY dimensions

When a grouping key like region or currency changes, how must old/new be handled?

**Hint:** Subtract from old group, add to new group.

### Exercise 44 — Race conditions

Does an unlocked trigger checking totals across rows guarantee invariants under all concurrent transactions?

**Hint:** No; proper constraints, locking, or isolation are needed.

### Exercise 45 — Double counting

If both an old row trigger and a new transition trigger update the same summary, what bug occurs?

**Hint:** Deltas are applied twice.

## 71. Frequently Asked Questions

### Is a transition table a temporary table I create with CREATE?

No. PostgreSQL provides transition relations automatically for eligible triggers; you assign aliases via `REFERENCING`. They are not persistent tables queryable outside the trigger.

### Does OLD TABLE contain every old row in the entire table?

No. It contains only the rows affected by the event of the DML statement that fired the trigger, not a full-table snapshot.

### Can I use transition tables in a BEFORE trigger?

No, transition relations are restricted to eligible AFTER triggers.

### Do I have to use FOR EACH STATEMENT to use transition tables?

That is the standard approach when aggregating the whole set. Eligible `AFTER ROW` triggers can also reference transition relations, though scanning the entire set inside every row trigger is usually expensive.

### Can an UPDATE trigger use both OLD TABLE and NEW TABLE?

Yes, on an eligible `AFTER UPDATE` trigger without an `UPDATE OF column_list` clause.

### Does a 0-row UPDATE fire statement triggers?

Yes; statement-level triggers fire per statement event. The transition relation is empty, so handle `COUNT`/`SUM` carefully.

### Why does updating customer_id require aggregating both sets?

Because a row can leave an old group and enter a new group. Computing only the amount difference on the new group would be wrong.

### Why shouldn't I JOIN old_rows/new_rows on a mutable key?

If the key changes, old and new rows fail to match. For summaries, aggregate each set independently; for per-row auditing, use an immutable identity or another mechanism.

### Do transition triggers replace constraints?

No. They excel at set-based processing, while integrity invariants should use declarative database constraints or proper concurrency control whenever possible.

### Can transition tables be used with TRUNCATE?

No. TRUNCATE has its own trigger behavior and has no equivalent to DELETE old transition rows.

### Does UPSERT fire INSERT triggers only?

Not by default. With `ON CONFLICT DO UPDATE`, trigger semantics involve both INSERT and UPDATE paths. Design for each event properly.

### Do transition tables preserve row modification order?

No SQL query order is guaranteed without `ORDER BY`.

### Does a trigger running after UPDATE mean the change is COMMITted?

No. AFTER triggers run inside the transaction; data, audit, and summary changes can still roll back.

### Should I create transition-trigger summaries for every report?

No. Try direct queries or materialized views first depending on freshness requirements. Trigger-maintained summaries add write/lock overhead and logic maintenance.

### Can transition tables serve as complete event sourcing or CDC?

No. They only expose affected rows within trigger scope. Durable history requires writing audits/outboxes; system-wide CDC requires an appropriate pipeline.

## 72. Summary

Core syntax:

~~~sql
-- Insert: provides NEW image.
CREATE TRIGGER trg_insert
AFTER INSERT ON schema_name.table_name
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();

-- Delete: provides OLD image.
CREATE TRIGGER trg_delete
AFTER DELETE ON schema_name.table_name
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();

-- Update: provides both OLD and NEW.
CREATE TRIGGER trg_update
AFTER UPDATE ON schema_name.table_name
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();
~~~

Key principles:

1. **Transition tables expose the before/after row sets of a DML event**, not a full-table snapshot.
2. `REFERENCING NEW TABLE` is used for INSERT/UPDATE; `REFERENCING OLD TABLE` is used for DELETE/UPDATE.
3. They belong to **eligible AFTER triggers** and have restrictions: not allowed with BEFORE/INSTEAD OF/TRUNCATE, constraint triggers, or `UPDATE OF`.
4. **Statement-level triggers can run even when 0 rows are affected**; handle empty sets explicitly.
5. A transition-table trigger can use `SELECT ... GROUP BY`, `INSERT ... SELECT`, and `ON CONFLICT` for batch processing, cutting down per-row work.
6. On UPDATE, compute **new contributions minus old contributions**; grouping keys themselves can change.
7. **Aggregate sources by key before UPSERT** so multiple source rows never target the same key in one command.
8. If per-row old/new pairing is needed, use a **stable identity key**; transition tables do not auto-generate row-pairing IDs.
9. `AFTER` **does not mean COMMITted**; trigger writes stay inside the caller's transaction.
10. UPSERT/MERGE, partitions, cascading actions, and trigger chains have semantics that must be tested on your actual PostgreSQL version and schema.
11. TRUNCATE or disabling triggers can cause summary drift without a rebuild procedure.
12. **Trigger-based summaries do not replace constraints**; verify concurrency, locking, idempotency, and RLS.
13. Use `NUMERIC` and proper business dimension keys when aggregating money.
14. Audit/outbox tables need proper schemas and retention—avoid building giant JSONB payloads or leaking sensitive fields.
15. **Reconciling against the source table and benchmarking** are mandatory for incrementally maintained summary tables.

Mental model:

~~~text
INSERT / UPDATE / DELETE statement
                  |
                  v
        Eligible AFTER trigger
                  |
                  v
       REFERENCING transition relations
              /              \
             /                \
        OLD TABLE           NEW TABLE
             \                /
              \              /
               v            v
        Compute set contributions
                       |
                       v
          GROUP BY business key
                       |
                       v
               Net delta
                       |
              +--------+--------+
              |                 |
              v                 v
       Statement audit   Summary UPSERT
              |                 |
              +--------+--------+
                       |
                       v
           Same source transaction
                       |
             COMMIT or ROLLBACK
~~~

Core takeaway: **whenever business logic must inspect and process an entire set of modified rows together, reach for transition tables with set-based SQL.** They centralize statement logic and eliminate per-row overhead, provided you accurately account for events, transactions, group deltas, concurrency, and what the trigger actually sees.
