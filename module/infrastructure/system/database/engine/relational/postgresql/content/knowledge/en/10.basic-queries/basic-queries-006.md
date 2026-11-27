# ORDER BY, Multiple Sort Keys, and NULLS FIRST / LAST in PostgreSQL

## 1. Why Understand ORDER BY Instead of Just Adding a Line of SQL?

In applications, users routinely expect data to appear in a clear, predictable order:

- Support ticket lists: **highest priority first**, older or newer tickets first per business rules.
- Invoice lists: **most recent issue date first**, breaking same-day ties by invoice ID.
- Leaderboards: **highest score first**, breaking ties with timestamp and ID.
- Task lists: **earliest due date first**, pushing tasks without a due date to the end.
- Search pages: stable ordering when a user moves from page 1 to page 2.

PostgreSQL uses the **`ORDER BY`** clause to specify the row order of a **query result**. When sorting by multiple criteria, you declare **multiple sort keys**, each with its own `ASC` or `DESC` direction and `NULL` placement.

Example:

```sql
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC;
```

This SQL statement expresses four layers of rules. Within each `team`:

1. Priority `1` comes before `2`, `3`; tickets without a `priority` appear last.
2. Within the same priority, newer tickets appear first.
3. If timestamps also match, smaller IDs appear first.

Crucial point: **Without `ORDER BY` on the outer query, PostgreSQL makes no guarantee about return order**. Seeing rows happen to arrive by ID or insertion order on sample data is not a SQL guarantee.

After this lesson, you will know how to:

1. Use `ORDER BY` with `ASC`, `DESC`, expressions, aliases, and multiple keys.
2. Explain PostgreSQL's exact defaults for `NULLS FIRST`/`NULLS LAST`.
3. Create **fully deterministic** ordering with tie-breakers, especially before `LIMIT` and `OFFSET`.
4. Sort by custom business orders, handle strings, letter case, and collations.
5. Distinguish outer result ordering from ordering inside `DISTINCT ON`, window functions, and aggregates.
6. Read `EXPLAIN` and understand when a B-tree index helps avoid a separate sort step.
7. Design keyset pagination and recognize issues with nullable keys.
8. Avoid common SQL mistakes when sorting and paginating.

> The table-creation and data-insertion commands in this lesson are strictly for a **practice database**. On live systems, run read queries with appropriate scope and privileges, and never add indexes casually.

---

## 2. Preparing Sample Data for Practice

Use an isolated schema to avoid colliding with existing business tables:

```sql
CREATE SCHEMA IF NOT EXISTS sort_lab;

CREATE TABLE sort_lab.tickets (
    ticket_id INTEGER PRIMARY KEY,
    team TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'OPEN', 'RESOLVED')),
    priority SMALLINT CHECK (priority BETWEEN 1 AND 3),
    score NUMERIC(5,2),
    assigned_to TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ
);
```

Dataset conventions:

- `priority = 1`: highest priority; `2`: medium; `3`: low.
- `priority IS NULL`: not yet triaged.
- `score` may not be graded yet.
- `assigned_to` may be unassigned yet.
- `due_at` may not have a due date yet.
- `created_at` is an instant in time, stored as `TIMESTAMPTZ`.

Note: `CHECK (priority BETWEEN 1 AND 3)` **does not forbid NULL**. In PostgreSQL, a `CHECK` constraint passes whenever the result is `TRUE` or `UNKNOWN`; thus nullable columns must be handled explicitly in queries.

Load 12 tickets:

```sql
INSERT INTO sort_lab.tickets
    (ticket_id, team, status, priority, score,
     assigned_to, created_at, due_at)
VALUES
    (101, 'Support', 'OPEN', 1, 90, 'An',
     TIMESTAMPTZ '2026-02-01 09:00:00+07',
     TIMESTAMPTZ '2026-02-03 09:00:00+07'),

    (102, 'Support', 'OPEN', 1, 90, 'Bình',
     TIMESTAMPTZ '2026-02-01 09:00:00+07', NULL),

    (103, 'Support', 'NEW', 2, 80, NULL,
     TIMESTAMPTZ '2026-02-01 10:00:00+07',
     TIMESTAMPTZ '2026-02-03 17:00:00+07'),

    (104, 'Billing', 'OPEN', 1, 95, 'Chi',
     TIMESTAMPTZ '2026-02-02 08:00:00+07',
     TIMESTAMPTZ '2026-02-04 12:00:00+07'),

    (105, 'Billing', 'RESOLVED', 3, 70, 'An',
     TIMESTAMPTZ '2026-02-02 09:00:00+07', NULL),

    (106, 'Support', 'OPEN', 2, 80, 'Bình',
     TIMESTAMPTZ '2026-02-01 10:00:00+07',
     TIMESTAMPTZ '2026-02-05 10:00:00+07'),

    (107, 'Sales', 'NEW', NULL, NULL, NULL,
     TIMESTAMPTZ '2026-02-03 09:00:00+07', NULL),

    (108, 'Sales', 'OPEN', 3, 70, 'Chi',
     TIMESTAMPTZ '2026-02-03 11:00:00+07',
     TIMESTAMPTZ '2026-02-06 14:00:00+07'),

    (109, 'Billing', 'NEW', NULL, 80, 'An',
     TIMESTAMPTZ '2026-02-04 10:00:00+07',
     TIMESTAMPTZ '2026-02-04 18:00:00+07'),

    (110, 'Support', 'RESOLVED', 3, NULL, 'An',
     TIMESTAMPTZ '2026-02-04 10:00:00+07',
     TIMESTAMPTZ '2026-02-07 12:00:00+07'),

    (111, 'Sales', 'OPEN', 1, 95, 'Bình',
     TIMESTAMPTZ '2026-02-05 08:00:00+07', NULL),

    (112, 'Support', 'NEW', 2, 80, 'Chi',
     TIMESTAMPTZ '2026-02-05 09:00:00+07',
     TIMESTAMPTZ '2026-02-06 16:00:00+07');
```

Verify:

```sql
SELECT COUNT(*) AS number_of_tickets
FROM sort_lab.tickets;
```

Expected: `12` if loaded once.

**Environment note:** `CREATE TABLE` omits `IF NOT EXISTS`. If the table was created in an earlier run, use a clean lab database/schema or manage test data through an approved workflow; never drop unfamiliar tables just to re-run an example.

### 2.1. Viewing Data in a Clear Order

```sql
SELECT
    ticket_id,
    team,
    status,
    priority,
    created_at
FROM sort_lab.tickets
ORDER BY ticket_id;
```

With `ORDER BY ticket_id`, results are requested in ascending ID order. This makes sample data easy to inspect, **not proof that PostgreSQL tables permanently store rows sorted by ID**.

## 3. General ORDER BY Syntax

Compact syntax:

```sql
SELECT expression_or_columns
FROM relation
WHERE condition
ORDER BY
    sort_expression_1 [ASC | DESC] [NULLS FIRST | NULLS LAST],
    sort_expression_2 [ASC | DESC] [NULLS FIRST | NULLS LAST],
    ...
LIMIT number;
```

Example:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id ASC
LIMIT 10;
```

Characteristics:

- `ORDER BY` can contain **one or more** expressions.
- Keys are evaluated **from left to right**.
- `ASC` means ascending; `DESC` means descending.
- If direction is omitted, PostgreSQL defaults to `ASC`.
- `NULLS FIRST` and `NULLS LAST` control `NULL` placement **per individual key**.
- A **tie-breaker** key can be added to resolve rows sharing identical leading keys.
- `ORDER BY` guarantees only the **output order** of that query. It imposes no permanent physical order on the table.

### 3.1. Simplest Case: Ascending

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority;
```

Equivalent to:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority ASC;
```

Because multiple tickets share the same priority, the order **among tickets with identical priority is not yet guaranteed**.

To make it explicit:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority ASC, ticket_id ASC;
```

### 3.2. Descending

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
WHERE score IS NOT NULL
ORDER BY score DESC, ticket_id ASC;
```

Scores of 95 appear before 90, 80, and 70. When two rows tie on score, the smaller ID comes first.

`DESC` only reverses the direction of the key **immediately preceding it**, not any remaining keys.

### 3.3. ORDER BY Does Not Modify Table Data

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC;
```

This does not write data, trigger an `UPDATE`, or reorder rows on disk. PostgreSQL chooses a query plan to emit rows in the requested order, using either an index or a sort operator.

Never treat `ORDER BY` as a way to "permanently store data in order."

## 4. ORDER BY with Multiple Keys: Left-to-Right Rule

Suppose a list needs:

1. Team ascending by string/collation rules.
2. Within each team, high priority (`1`) first.
3. Within the same priority, newer tickets first.
4. If all three tie, smaller ID first.

```sql
SELECT
    ticket_id,
    team,
    priority,
    created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC;
```

Interpretation:

```text
team
  ├── Billing
  │     ├── priority 1
  │     ├── priority 3
  │     └── priority NULL
  ├── Sales
  │     ├── priority 1
  │     ├── priority 3
  │     └── priority NULL
  └── Support
        ├── priority 1
        ├── priority 2
        └── priority 3
```

This diagram illustrates grouping order under typical collations for the sample data; comparing other strings can depend on collation.

### 4.1. Subsequent Keys Apply Only When Earlier Keys Tie

In:

```sql
ORDER BY team ASC, priority ASC
```

PostgreSQL does **not** sort by `priority` across the whole table first and then sort by team. It sorts by `team` first; **only rows sharing the same team** are ordered by priority.

Similarly:

```sql
ORDER BY priority ASC, created_at DESC
```

differs completely from:

```sql
ORDER BY created_at DESC, priority ASC
```

Left-to-right order expresses **rule precedence**.

### 4.2. Sort Direction Is Declared Per Key

```sql
ORDER BY team ASC, priority DESC, ticket_id ASC
```

means:

- Team ascending.
- Within a team, **larger** priority numbers first.
- On tied team and priority, smaller ID first.

Notice our sample system defines priority **1 as highest**, so `DESC` puts low priority (`3`) first. Valid syntax does not guarantee right business logic—always check the **column's values and domain meaning**.

### 4.3. Thinking in Terms of Lexicographical Tuple Comparison

Multi-column `ORDER BY` works like lexicographically comparing tuples:

```text
(team, priority, created_at, ticket_id)
```

When comparing two rows:

1. If teams differ, team alone decides.
2. If teams match, compare priority.
3. If priorities match, compare `created_at` in its specified direction.
4. If still equal, compare `ticket_id`.

Having a unique ID as the final key yields a completely deterministic total order.

### 4.4. A Verifiable Practice Subset

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
  AND priority IS NOT NULL
ORDER BY priority ASC, created_at DESC, ticket_id ASC;
```

On the sample data, the ID order is:

```text
101, 102, 112, 103, 106, 110
```

Explanation:

- Priority 1: `101`, `102` share the same timestamp, so smaller ID goes first.
- Priority 2: `112` is newest, followed by `103` and `106` sharing a timestamp (ID 103 first).
- Priority 3: `110`.

This clearly illustrates the **tie-breaking** role of the third and fourth keys.

## 5. What Is NULL in PostgreSQL Sorting?

### 5.1. SQL NULL Is Not Zero or an Empty String

A ticket with:

```text
priority = NULL
```

means priority is unknown or unassigned, not `priority = 0`, `priority = 3`, or `priority = ''`.

When sorting, PostgreSQL must decide where NULLs go. That is controlled by:

```sql
NULLS FIRST
NULLS LAST
```

### 5.2. PostgreSQL Defaults

In PostgreSQL, the default placement is:

| Syntax | Default NULL Placement |
|---|---|
| `ORDER BY x` | `ASC NULLS LAST` |
| `ORDER BY x ASC` | `NULLS LAST` |
| `ORDER BY x DESC` | `NULLS FIRST` |
| `ORDER BY x ASC NULLS FIRST` | NULLs first |
| `ORDER BY x ASC NULLS LAST` | NULLs last |
| `ORDER BY x DESC NULLS FIRST` | NULLs first |
| `ORDER BY x DESC NULLS LAST` | NULLs last |

**Easy rule for PostgreSQL:** in default `ORDER BY` comparisons, NULL is treated as **larger than all non-NULL values**. Hence ascending puts NULLs last, and descending puts NULLs first.

This is **PostgreSQL behavior**; do not assume every DBMS shares the same defaults. When cross-database consistency or reader clarity matters, **write it explicitly**.

### 5.3. Observing All Four Ordering Modes

Pick four tickets with priorities 1, 2, 3, and NULL:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority ASC NULLS LAST, ticket_id;
```

Priority output:

```text
ticket_id | priority
----------+---------
101       | 1
103       | 2
105       | 3
107       | NULL
```

Ascending, NULLs first:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority ASC NULLS FIRST, ticket_id;
```

ID order:

```text
107, 101, 103, 105
```

Descending, NULLs first:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority DESC NULLS FIRST, ticket_id;
```

ID order:

```text
107, 105, 103, 101
```

Descending, NULLs last:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority DESC NULLS LAST, ticket_id;
```

ID order:

```text
105, 103, 101, 107
```

### 5.4. Common Business Scenarios

Earliest due date first, tickets without due dates at the end:

```sql
SELECT ticket_id, due_at
FROM sort_lab.tickets
ORDER BY due_at ASC NULLS LAST, ticket_id ASC;
```

Leaderboard from highest to lowest score, ungraded entries at the end:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

Triage queue putting untriaged tickets first for staff review:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
ORDER BY priority ASC NULLS FIRST, ticket_id ASC;
```

`NULLS FIRST/LAST` **neither alters** NULL values in the table **nor removes** NULL rows from results; it solely controls their relative position.

## 6. NULLS FIRST/LAST Applies Per Individual Key

Consider:

```sql
SELECT
    ticket_id,
    team,
    priority,
    due_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    ticket_id ASC;
```

There are two nullable columns: `priority` and `due_at`.

Sorting sequence:

1. Group/order by team.
2. Within each team, priorities 1, 2, 3 first, then NULL.
3. Within the same priority, earliest due dates first, no due date last.
4. Among remaining ties, sort by ID.

**A trailing `NULLS LAST` only affects the single key immediately before it.**

For example:

```sql
ORDER BY priority DESC NULLS LAST, due_at ASC NULLS FIRST
```

means **NULL priorities go last within any preceding group**, whereas among rows sharing the same priority, NULL `due_at` values go **first within that subgroup**. There is no global "NULLs always go at the bottom of the whole list" flag spanning every key.

### 6.1. NULLs and Tie-Breakers

Multiple rows have `priority NULL`. Because they tie on that key, subsequent keys determine their relative order.

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Inside the NULL-priority group, tickets `109` and `107` are ordered by descending `created_at`. If two tickets tied on timestamp as well, ID would be the final tie-breaker.

### 6.2. Using Expressions vs. COALESCE to Place NULLs

An alternative trick is:

```sql
ORDER BY priority IS NULL ASC, priority ASC, ticket_id ASC
```

In PostgreSQL, sorting booleans ascending places `FALSE` before `TRUE`, so `priority IS NULL` puts **non-NULL** rows before NULL rows, then compares priority.

By contrast:

```sql
ORDER BY COALESCE(priority, 999)
```

substitutes a sentinel value **inside the sort expression**. That has side effects:

- If a valid priority ever equals 999, NULL and 999 become **tied** in the sort expression.
- The expression's data type and comparison rules may differ from the base column.
- An index on `priority` will not generally serve `ORDER BY COALESCE(priority,999)` the way it serves `ORDER BY priority`.
- Readers might mistakenly think priorities were actually rewritten in the table.

When you only need NULL placement, **`NULLS FIRST/LAST` is much clearer**. Use `COALESCE` only when substituting a concrete value for NULL is an explicit business rule—such as "ungraded scores count as 0 on the leaderboard"—and document it clearly.

## 7. ORDER BY with Computed Expressions

PostgreSQL allows sorting by expressions, not only column names.

### 7.1. By String Length

```sql
SELECT ticket_id, team, length(team) AS team_name_length
FROM sort_lab.tickets
ORDER BY length(team) DESC, team ASC, ticket_id ASC;
```

Places longer team names first; ties are broken alphabetically by name, then ID.

### 7.2. By CASE Result

Suppose business status order is:

1. `OPEN` — needs action.
2. `NEW` — newly created.
3. `RESOLVED` — completed.

Alphabetical order does **not** capture this policy. Use:

```sql
SELECT ticket_id, status, priority
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END ASC,
    priority ASC NULLS LAST,
    ticket_id ASC;
```

`ELSE 4` gives the expression a safe fallback if the status list evolves. While the lab schema has a `CHECK` constraint limiting three statuses, application SQL should handle unexpected values gracefully.

### 7.3. By Arithmetic Calculation

```sql
SELECT
    ticket_id,
    score,
    COALESCE(score, 0) * 1.2 AS weighted_score
FROM sort_lab.tickets
ORDER BY weighted_score DESC, ticket_id ASC;
```

This uses a hypothetical formula. `weighted_score` is an alias for the computed output; it is **not a physical column**, unless the schema defines one separately.

If NULL scores should not count as 0, sort directly instead of using `COALESCE`:

```sql
ORDER BY score DESC NULLS LAST, ticket_id ASC
```

### 7.4. By Date Extracted from TIMESTAMPTZ

To group/sort by **calendar date in Vietnam**:

```sql
SELECT
    ticket_id,
    created_at,
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS created_day_vn
FROM sort_lab.tickets
ORDER BY created_day_vn DESC, created_at DESC, ticket_id DESC;
```

`TIMESTAMPTZ` is an instant in time; formatting and casting to a calendar date depend on time zone. Use `AT TIME ZONE` explicitly whenever "day" refers to a specific geographical region.

Note: sorting solely by `ORDER BY created_day_vn DESC` leaves tickets on the **same day** in nondeterministic order; add `created_at` and `ticket_id` as tie-breakers.

## 8. SELECT Aliases, Column Positions, and Column Names in ORDER BY

### 8.1. Using Aliases

```sql
SELECT
    ticket_id,
    COALESCE(score, 0) AS effective_score
FROM sort_lab.tickets
ORDER BY effective_score DESC, ticket_id ASC;
```

In `ORDER BY`, PostgreSQL permits referencing an output column name like `effective_score`.

This avoids repeating long expressions. Keep the semantics in mind, though: **a standalone output alias** resolves to the output column; if you need a complex expression built on top of an alias, repeat the expression or wrap the query in a subquery.

Clear example with a subquery:

```sql
SELECT ticket_id, effective_score
FROM (
    SELECT
        ticket_id,
        COALESCE(score, 0) AS effective_score
    FROM sort_lab.tickets
) AS t
ORDER BY effective_score * 2 DESC, ticket_id ASC;
```

### 8.2. Using Output Column Positions

PostgreSQL allows:

```sql
SELECT
    team,
    priority,
    ticket_id
FROM sort_lab.tickets
ORDER BY 1 ASC, 2 ASC NULLS LAST, 3 ASC;
```

Here:

- `1` is the first output column (`team`).
- `2` is the second (`priority`).
- `3` is the third (`ticket_id`).

However, if someone reorders columns in `SELECT`, the sort logic silently changes without raising an error. Therefore, in application code and documentation, **prefer explicit column names or expressions**.

### 8.3. Beware of Alias Name Collisions

```sql
SELECT score AS priority
FROM sort_lab.tickets
ORDER BY priority DESC;
```

When a **bare output column name** `priority` appears in `ORDER BY`, PostgreSQL's name-resolution rules prefer the output column on conflict. It will sort by the aliased `score`, not the input column `priority` as a reader might expect.

To eliminate ambiguity, use a table qualifier or a distinct alias:

```sql
SELECT t.score AS reported_score, t.priority
FROM sort_lab.tickets AS t
ORDER BY t.priority ASC NULLS LAST, t.ticket_id;
```

Even if `ticket_id` is not selected, PostgreSQL can still reference source columns in `ORDER BY` for ordinary `SELECT`s; `SELECT DISTINCT` has stricter rules covered later.

## 9. Sorting Strings: Collations, Case, and Vietnamese Diacritics

### 9.1. String Order Depends on Comparison Rules

Values:

```text
An
Bình
Chi
Ánh
anh
```

do not always sort identically across databases. PostgreSQL relies on the expression's **collation** and the active locale/ICU/libc configuration.

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY assigned_to ASC NULLS LAST, ticket_id ASC;
```

This query has a deterministic order under the column's collation, yet **relative order of different strings can change under a different collation**.

### 9.2. Specifying a Collation Explicitly

The `"C"` collation is widely available:

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY assigned_to COLLATE "C" ASC NULLS LAST, ticket_id ASC;
```

`"C"` uses simple byte-wise comparison rules, useful for certain technical checks, **not natural alphabetical sorting for Vietnamese**.

For user-facing products, choose a collation matching the language, locale, and PostgreSQL version. Custom ICU collations can be created if infrastructure supports them; never assume a Vietnamese collation exists in the database without checking.

### 9.3. Case-Insensitive Sorting

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC;
```

Here `lower(assigned_to)` lowercases names before comparing under the active collation. This smooths out some case differences, though it does not solve **every** Vietnamese rule, Unicode normalization, or accent equivalence.

Include `ticket_id` because different names can lowercase to the same sort key.

### 9.4. Sorting Numbers Stored as TEXT

If a column stores strings:

```text
'2', '10', '100'
```

sorting as text/collation gives a different order from **numeric sorting**. You cannot run `ORDER BY text_col` and expect 2, 10, 100 in numerical order.

If values are genuinely numbers, **store them in a numeric type** such as `INTEGER` or `NUMERIC`. If you must cast at read time, ensure all strings are valid:

```sql
-- Use only if every code_text value can be cast to integer.
SELECT code_text
FROM some_table
ORDER BY code_text::integer ASC;
```

On dirty data, an invalid cast fails the query. That is a data-modeling issue, not something `NULLS LAST` can fix.

### 9.5. Collations Can Produce Equal Sort Keys

Some collations treat distinct strings as equal at the sort-comparison level. When deterministic output is needed, add a unique ID:

```sql
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC
```

The uniqueness of `ticket_id` breaks ties even when collation or normalization folds distinct strings to equal keys.

## 10. Tie-Breakers: Achieving Fully Deterministic Ordering

### 10.1. The Problem When Multiple Rows Share Keys

This query:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST;
```

ensures high scores come first and NULLs last. However, both `104` and `111` have `score = 95`, and several tickets have `score = 80`. **The relative order of tied rows is not guaranteed by SQL.**

Two runs might return the same order by coincidence, yet index changes, PostgreSQL upgrades, plan shifts, parallel workers, or data edits can reorder tied rows.

### 10.2. Adding a Unique Key

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

Since `ticket_id` is the `PRIMARY KEY`, no two rows share an ID. Combining both keys produces a completely deterministic total order.

To put "newer tickets first" on score ties:

```sql
ORDER BY
    score DESC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Here `created_at` can tie, and `ticket_id` resolves any remaining tie.

### 10.3. Tie-Breakers Do Not Have to Be Single-Column PKs

A table with composite PK `(tenant_id, sku)` can use:

```sql
ORDER BY
    price DESC,
    tenant_id ASC,
    sku ASC;
```

as long as the final combination of keys uniquely identifies every row in the relevant result set.

A **timestamp** or `status` column is not unique by default. If a system allows two events within the same millisecond, `ORDER BY created_at DESC` still has ties.

### 10.4. When Are Tie-Breakers Especially Critical?

- `LIMIT`/`OFFSET` pagination.
- Keyset/cursor pagination.
- Reproducible report exports.
- Selecting the "latest row per group" with `DISTINCT ON`.
- Rankings requiring specific row placement.
- Automated tests comparing ordered lists repeatedly.
- APIs allowing multi-column sorting.

## 11. ORDER BY with LIMIT and OFFSET

### 11.1. Basic Pagination

```sql
SELECT
    ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 0;
```

Page 1 fetches up to five newest tickets.

```sql
SELECT
    ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 5;
```

Page 2 skips the first five tickets in the **exact same order**.

Standard formula:

```text
OFFSET = (page_number - 1) × page_size
```

where `page_number` starts at 1.

### 11.2. What Happens If You Omit ORDER BY?

```sql
SELECT *
FROM sort_lab.tickets
LIMIT 5 OFFSET 5;
```

This does not mean "rows 6 to 10 by insertion order." PostgreSQL is free to return any subset per its current plan and change it on the next run. **Every meaningful paginated query must specify `ORDER BY`.**

### 11.3. What If ORDER BY Still Has Ties?

```sql
ORDER BY created_at DESC
LIMIT 5 OFFSET 5
```

Two rows sharing the same `created_at` across a page boundary can swap places. Page 1 and Page 2 can become inconsistent even when underlying data hasn't changed, because tie order is nondeterministic.

Always add:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

### 11.4. Tie-Breakers Do Not Solve Concurrent Updates

Suppose a user views page 1 at `t1`, and a new ticket is inserted before they request page 2 at `t2`. With `OFFSET`, row positions shift downward; rows can be **duplicated or skipped** between requests.

Tie-breakers make ordering deterministic **at a single snapshot**, but do not preserve a snapshot across separate HTTP requests. If consistent pagination under concurrent writes is required, evaluate keyset pagination, snapshot/transaction semantics, and product requirements.

### 11.5. Large OFFSET Can Be Expensive

```sql
LIMIT 50 OFFSET 500000
```

can force PostgreSQL to scan and discard huge numbers of rows before returning 50 rows, even with an index. For deep lists, **keyset/cursor pagination** is usually worth considering.

## 12. Keyset Pagination: Resuming After the Last Row's Key

### 12.1. Favorable Case: Two DESC Keys, Both Non-NULL

Suppose an API sorts by:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

and returns 5 rows per page.

First page:

```sql
SELECT
    ticket_id, created_at, status
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

The client records `(created_at, ticket_id)` from the **last row** received.

The next page asks for rows whose key tuple is **smaller** in the same lexicographical order:

```sql
SELECT
    ticket_id, created_at, status
FROM sort_lab.tickets
WHERE (created_at, ticket_id)
    < (TIMESTAMPTZ '2026-02-03 11:00:00+07', 108)
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

The cursor pair in this example is an **illustrative value**. In real applications, bind the **actual last row values** rather than hard-coding.

Because both columns are non-NULL and both `DESC`, tuple comparison `<` directly matches "move forward to older/smaller values." Including the unique ID resolves ties at identical timestamps.

### 12.2. SQL Row Comparisons Have Their Own NULL Rules

```sql
(created_at, ticket_id) < (:cursor_created_at, :cursor_id)
```

works cleanly when both fields are non-NULL and share the same direction. If a key contains `NULL`, SQL row comparison can return **UNKNOWN**, which does not automatically match `ORDER BY ... NULLS LAST`.

When sorting with mixed directions or `NULLS FIRST/LAST`, you cannot simply convert everything into a single tuple `<`/`>` comparison and expect correct results.

### 12.3. Keyset with priority ASC NULLS LAST

Suppose the sort order is:

```sql
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
```

We need two cases.

**Case A — last cursor has non-NULL `priority`**, with parameters `:last_priority`, `:last_created_at`, `:last_id`:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE
    priority > :last_priority
    OR (
        priority = :last_priority
        AND (created_at, ticket_id)
            < (:last_created_at, :last_id)
    )
    OR priority IS NULL
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
LIMIT 5;
```

Explanation:

- Include higher priority numbers (since priority is `ASC`).
- For equal priority, take rows with older timestamp/ID under the two `DESC` keys.
- Rows with NULL priority always **come after** all non-NULL priorities, so include them too.

**Case B — last cursor has `priority IS NULL`:**

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE priority IS NULL
  AND (created_at, ticket_id)
      < (:last_created_at, :last_id)
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
LIMIT 5;
```

Once inside the trailing NULL group, continue solely within the NULL group.

These examples assume `created_at` and `ticket_id` are **non-NULL**, matching the lab schema; if tie-breaker keys themselves are nullable, extend the logic accordingly.

In real applications, use parameter binding through your driver/API—never build SQL strings from user input.

### 12.4. Keyset Is Not an Absolute Historical Snapshot

If a row's `priority` or `created_at` changes after the previous page was read, it can shift across the cursor boundary. Keyset avoids OFFSET's scanning cost and drift in many scenarios, yet **does not create an immutable snapshot across requests**. Account for mutable data policies and API consistency requirements.

## 13. Sorting When Using DISTINCT

### 13.1. SELECT DISTINCT and ORDER BY

Query:

```sql
SELECT DISTINCT status
FROM sort_lab.tickets
ORDER BY status ASC;
```

is valid: `status` is selected and used as the sort key.

In PostgreSQL, with `SELECT DISTINCT`, `ORDER BY` expressions must obey restrictions tied to the **selected output list**; you cannot arbitrarily sort distinct statuses by a column not in the output when each status has multiple distinct values.

Problematic intent:

```sql
-- Invalid way to select distinct statuses
-- and arbitrarily sort by individual rows' created_at:
SELECT DISTINCT status
FROM sort_lab.tickets
ORDER BY created_at DESC;
```

Since one status has multiple `created_at` timestamps, define an **aggregation rule**: latest date, earliest date, or business order?

Clear approach:

```sql
SELECT
    status,
    MAX(created_at) AS last_created_at
FROM sort_lab.tickets
GROUP BY status
ORDER BY last_created_at DESC, status ASC;
```

### 13.2. DISTINCT ON Is a PostgreSQL Feature

To pick the **single newest ticket per team**, use `DISTINCT ON`:

```sql
SELECT DISTINCT ON (team)
    team,
    ticket_id,
    created_at,
    status
FROM sort_lab.tickets
ORDER BY
    team ASC,
    created_at DESC,
    ticket_id DESC;
```

`DISTINCT ON (team)` keeps the **first row** of each team group according to `ORDER BY`.

PostgreSQL rule: the `DISTINCT ON` expressions must **match the leftmost `ORDER BY` expressions** as required by syntax; subsequent keys then pick which row within the group to keep.

Writing only:

```sql
SELECT DISTINCT ON (team) ...
FROM sort_lab.tickets;
```

without defining the intra-group sort makes "the first row" nondeterministic.

### 13.3. Pick Newest Per Group, Then Sort Overall Result by Time

A subtle issue: the `DISTINCT ON (team)` query above has `ORDER BY team` to drive per-group selection, so the **entire result** ends up sorted by team rather than globally by latest date.

To pick first, then re-sort outside:

```sql
SELECT
    team, ticket_id, created_at, status
FROM (
    SELECT DISTINCT ON (team)
        team, ticket_id, created_at, status
    FROM sort_lab.tickets
    ORDER BY team, created_at DESC, ticket_id DESC
) AS latest_per_team
ORDER BY created_at DESC, ticket_id DESC;
```

**The two `ORDER BY` clauses serve two different roles**:

- The inner `ORDER BY` decides **which row is kept for each team**.
- The outer `ORDER BY` decides **the final display order of the list**.

This clearly illustrates the difference between **ordering for an intermediate operation** and **final presentation order**.

## 14. ORDER BY Inside Window Functions Differs from Outer Result ORDER BY

### 14.1. ROW_NUMBER per Team

```sql
SELECT
    ticket_id,
    team,
    priority,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY
            priority ASC NULLS LAST,
            created_at DESC,
            ticket_id ASC
    ) AS row_in_team
FROM sort_lab.tickets
ORDER BY team ASC, row_in_team ASC;
```

Inside `OVER (...)`:

- `PARTITION BY team` divides rows into team partitions for the window calculation.
- `ORDER BY priority, created_at, ticket_id` determines **numbering order within each partition**.
- `ROW_NUMBER()` assigns 1, 2, 3... following those window keys.

Meanwhile, the trailing `ORDER BY team, row_in_team` determines **how rows are returned to the client**.

### 14.2. Missing Outer ORDER BY

```sql
SELECT
    ticket_id,
    ROW_NUMBER() OVER (ORDER BY created_at DESC, ticket_id DESC) AS rn
FROM sort_lab.tickets;
```

The window `ORDER BY` defines how `rn` is computed, but should not be relied on as a **guarantee of final output row order** without an outer `ORDER BY`.

To be certain:

```sql
SELECT
    ticket_id,
    ROW_NUMBER() OVER (ORDER BY created_at DESC, ticket_id DESC) AS rn
FROM sort_lab.tickets
ORDER BY rn;
```

### 14.3. RANK, DENSE_RANK, and Ties

If you write:

```sql
RANK() OVER (ORDER BY score DESC NULLS LAST)
```

tickets sharing the same `score` belong to the same **peer group** and receive the same rank. Adding `ticket_id` inside the rank window's `ORDER BY` splits peers apart, producing different ranks.

Distinguish the two goals:

- **Score ranking:** keep ties on `score` inside the window.
- **Stable display order:** add `ticket_id` to the **outer** `ORDER BY`.

Example:

```sql
SELECT
    ticket_id,
    score,
    RANK() OVER (
        ORDER BY score DESC NULLS LAST
    ) AS score_rank
FROM sort_lab.tickets
ORDER BY
    score DESC NULLS LAST,
    ticket_id ASC;
```

Tied scores still receive identical ranks, while their display order in the output is completely deterministic.

## 15. ORDER BY Inside Aggregates

### 15.1. array_agg in a Desired Order

PostgreSQL supports:

```sql
SELECT
    team,
    array_agg(
        ticket_id
        ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_ids_newest_first
FROM sort_lab.tickets
GROUP BY team
ORDER BY team ASC;
```

The `ORDER BY` **inside `array_agg`** dictates element ordering within each team's array.

The **outer** `ORDER BY team` dictates the ordering of team rows.

These two orderings are independent. If you omit `ORDER BY` inside the aggregate, never expect `array_agg` elements to reflect insertion or index order.

### 15.2. json_agg or string_agg

Example:

```sql
SELECT
    team,
    string_agg(
        ticket_id::text,
        ', ' ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_id_list
FROM sort_lab.tickets
GROUP BY team
ORDER BY team;
```

With `string_agg`, element ordering **is semantically significant**: the concatenated string changes if inputs arrive in a different order.

### 15.3. Do Not Confuse with GROUP BY

```sql
GROUP BY team
```

groups rows by team for aggregation; by itself it **does not guarantee the output order of the groups**.

To sort groups alphabetically:

```sql
GROUP BY team
ORDER BY team ASC
```

To put the team with the most tickets first:

```sql
SELECT team, COUNT(*) AS ticket_count
FROM sort_lab.tickets
GROUP BY team
ORDER BY ticket_count DESC, team ASC;
```

`team ASC` breaks ties when two teams have the same `ticket_count`.

## 16. ORDER BY in Subqueries, CTEs, and Views

### 16.1. ORDER BY Inside a Subquery Does Not Replace an Outer ORDER BY

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM sort_lab.tickets
    ORDER BY created_at DESC
) AS ordered_input;
```

Never rely on a subquery's ordering to guarantee outer output order in all cases. Outer operations like JOINs, aggregations, or parallel execution can alter final row order.

When the client needs sorted output:

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM sort_lab.tickets
) AS t
ORDER BY created_at DESC, ticket_id DESC;
```

### 16.2. Subquery ORDER BY + LIMIT Selects a Subset

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at, team
    FROM sort_lab.tickets
    ORDER BY created_at DESC, ticket_id DESC
    LIMIT 5
) AS latest_five
ORDER BY team ASC, ticket_id ASC;
```

Here:

- The **inner `ORDER BY`** paired with `LIMIT 5` identifies the **five newest tickets**.
- The **outer `ORDER BY`** sorts those **five tickets by team** for display.

Each serves a different purpose. You cannot remove the inner `ORDER BY` and still pick the five newest tickets.

### 16.3. Views Do Not Turn Ordering into a Contract

Even if a view is defined over a sorted query, applications should still declare `ORDER BY` in the **query reading the view** whenever output order is part of the API.

Example:

```sql
SELECT ticket_id, created_at
FROM some_view
ORDER BY created_at DESC, ticket_id DESC;
```

Never rely on incidental view order in UI tests.

### 16.4. UNION and ORDER BY

After `UNION`, `INTERSECT`, or `EXCEPT`, PostgreSQL restricts what expressions can appear in `ORDER BY` for the combined result. Normally use **output column names or positions**:

```sql
SELECT ticket_id, team
FROM sort_lab.tickets
WHERE team = 'Support'

UNION ALL

SELECT ticket_id, team
FROM sort_lab.tickets
WHERE team = 'Billing'

ORDER BY team, ticket_id;
```

To sort the combined result by a complex expression, wrap it in a subquery:

```sql
SELECT *
FROM (
    SELECT ticket_id, team
    FROM sort_lab.tickets
    WHERE team = 'Support'

    UNION ALL

    SELECT ticket_id, team
    FROM sort_lab.tickets
    WHERE team = 'Billing'
) AS combined
ORDER BY lower(team), ticket_id;
```

This keeps processing layers clear and avoids assuming arbitrary sort expressions work directly after set operations.

## 17. How Does ORDER BY Relate to B-Tree Indexes?

### 17.1. Two Common Ways PostgreSQL Returns Sorted Data

Given:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id ASC
LIMIT 10;
```

PostgreSQL can:

1. Read matching rows and execute a **Sort** (possibly using a top-N optimization for `LIMIT`).
2. Scan in **matching B-tree index order**, potentially avoiding a separate Sort node.

The planner's choice depends on indexes, filters, data distribution, statistics, heap-access cost, `LIMIT`, and available resources. **Having an index does not force PostgreSQL to use it.**

### 17.2. Creating a Composite Index Matching the Query

In the **lab**, you can test:

```sql
CREATE INDEX ix_tickets_team_priority_created_id
ON sort_lab.tickets (
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC
);
```

With the equality filter `team = 'Support'`, the remaining index order matches:

```text
priority ASC NULLS LAST
created_at DESC
ticket_id ASC
```

So the query above has the opportunity to read rows in the desired order directly.

Why does the index start with `team`? Because the query filters `WHERE team = ...` and then sorts by the remaining keys. If the workload mostly sorts the **whole table without filtering by team**, this index would not be ideal.

### 17.3. B-Tree Forward and Backward Scans

A B-tree index can be scanned forward or backward. For instance, an index:

```sql
CREATE INDEX ix_tickets_created_id
ON sort_lab.tickets (created_at ASC, ticket_id ASC);
```

can support:

```sql
ORDER BY created_at ASC, ticket_id ASC
```

and, via backward scan, support:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

However, for **mixed directions**:

```sql
ORDER BY created_at DESC, ticket_id ASC
```

an index with both columns in the same direction cannot match purely via a backward scan. When warranted after measuring load, create an index with matching mixed sort directions.

With `NULLS FIRST/LAST`, a backward scan also reverses NULL placement relative to the index definition. Direction and NULL placement in `CREATE INDEX` therefore carry physical significance.

### 17.4. An Index Helps Sort Order, Yet May Still Need Heap Fetches

An index on the sort keys can eliminate sorting work, yet the query also selects `status`, `score`, and `assigned_to`. If those columns are not available in the index in a usable way, PostgreSQL still fetches heap pages to read them.

Even `Index Only Scan` checks the Visibility Map for MVCC correctness, so the name `Index Only Scan` does not promise zero heap reads on every query.

### 17.5. Sorting by Expressions and Expression Indexes

If a workload frequently runs:

```sql
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id
```

a plain B-tree index on `assigned_to` will not match the order of the **`lower(assigned_to)` expression**. Consider an expression index:

```sql
CREATE INDEX ix_tickets_assignee_normalized
ON sort_lab.tickets (
    lower(assigned_to) ASC NULLS LAST,
    ticket_id ASC
);
```

Add this only when justified by workload demand. Expression indexes add `INSERT`/`UPDATE` overhead and must match the query's collation and comparison rules.

### 17.6. Indexes Do Not Replace ORDER BY in Application Code

Even when the planner consistently picks an index and results **appear** stable, SQL without `ORDER BY` never guarantees output order.

Write the ordering requirement in SQL:

```sql
SELECT ...
FROM ...
ORDER BY ...
```

and use indexes to **optimize satisfying that requirement**, not the other way around.

## 18. EXPLAIN: Reading Sort Plans

### 18.1. EXPLAIN Shows the Estimated Plan

```sql
EXPLAIN
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id
LIMIT 5;
```

Common plan nodes:

| Node | Role |
|---|---|
| `Seq Scan` | Sequential table scan |
| `Index Scan` | Uses index to locate/read rows |
| `Index Only Scan` | Reads directly from index when visibility permits |
| `Sort` | Sorts row set by requested keys |
| `Incremental Sort` | Exploits input already sorted on a leading prefix of keys |
| `Limit` | Stops after returning at most `LIMIT` rows |
| `Gather Merge` | Merges sorted streams from parallel workers while preserving order |

Inside a `Sort` node, you will often see `Sort Key`:

```text
Sort Key: priority, created_at DESC, ticket_id
```

Verify that the sort keys match your intended **direction, NULL placement, and tie-breaker**.

### 18.2. EXPLAIN ANALYZE Executes the SQL

In a lab database:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id
LIMIT 5;
```

`ANALYZE` **actually runs the query** to collect real timings and row counts, unlike plain `EXPLAIN`.

For a `SELECT` on 12 rows this is negligible. In production, a `SELECT` sorting millions of rows still consumes significant CPU and I/O—never run it carelessly just because it is read-only.

### 18.3. Sort Strategies

In actual execution plans, you may see:

- `Sort Method: quicksort`: in-memory sort using a common algorithm.
- `Sort Method: top-N heapsort`: optimized when only the top few rows are needed under `LIMIT`.
- `Sort Method: external merge`, with disk usage: large sort spilling to temporary files.
- `Incremental Sort`: exploits input already ordered by a **key prefix** and sorts only within tied groups.

Method names and appearances in plans are not guaranteed contracts; planner and executor choices vary with version, statistics, and query shape.

### 18.4. LIMIT Does Not Guarantee Reading Little Data

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id
LIMIT 10;
```

Only 10 rows are returned at most, yet PostgreSQL may have to inspect many rows to find **which 10 have the highest score** if no supporting access path exists.

`LIMIT 10` by itself does **not** mean "read only 10 rows."

### 18.5. work_mem and Large Sorts

PostgreSQL treats `work_mem` as a budget for executor operations such as sort and hash nodes per its own rules; do not think of it as "total RAM for all of PostgreSQL."

If a sort exceeds its budget or requires temporary files, PostgreSQL spills to disk. However, raising `work_mem` server-wide is not automatically safe, because **a single query can contain multiple nodes** and many queries can run concurrently.

To investigate:

1. Inspect `EXPLAIN (ANALYZE, BUFFERS)` in an appropriate environment.
2. Check sort method, memory, and temp data usage.
3. See whether an index or tighter filter can avoid the sort.
4. If testing `work_mem`, scope it narrowly to a lab/session rather than server-wide.
5. Measure concurrency, CPU, memory, and I/O before rolling out changes.

Lab-only example:

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC;

ROLLBACK;
```

This demonstrates `SET LOCAL` inside a transaction. It does not prove `16MB` is the right production setting.

## 19. ORDER BY and NULL Data in B-Tree Indexes

### 19.1. NULL Placement Is Stored in the Index Definition

Example:

```sql
CREATE INDEX ix_tickets_due_nulls_last
ON sort_lab.tickets (
    due_at ASC NULLS LAST,
    ticket_id ASC
);
```

This index can support:

```sql
SELECT ticket_id, due_at
FROM sort_lab.tickets
ORDER BY due_at ASC NULLS LAST, ticket_id ASC;
```

because the index ordering definition matches the query's sort keys.

### 19.2. Reversing Scan Direction Does Not Always Match Intent

Scanning an index defined as:

```text
due_at ASC NULLS LAST
```

in reverse produces:

```text
due_at DESC NULLS FIRST
```

Yet an application might want:

```sql
ORDER BY due_at DESC NULLS LAST
```

That is a **different ordering rule**. Check whether the planner finds another access path, adds a Sort step, or warrants a matching index if the workload justifies it.

### 19.3. NULLS FIRST/LAST on a Secondary Column

Index:

```sql
CREATE INDEX ix_tickets_team_due
ON sort_lab.tickets (
    team ASC,
    due_at ASC NULLS LAST,
    ticket_id ASC
);
```

can match:

```sql
WHERE team = 'Support'
ORDER BY due_at ASC NULLS LAST, ticket_id ASC
```

but does not automatically match:

```sql
ORDER BY team ASC, due_at DESC NULLS LAST, ticket_id ASC
```

because the second key's direction flipped. Always check ordering **per column**, not just whether `DESC` appears somewhere in the SQL.

## 20. When Can ORDER BY Cause Errors or Unexpected Results?

### 20.1. Sorting by a Nonexistent Column Name

```sql
SELECT ticket_id
FROM sort_lab.tickets
ORDER BY no_such_column;
```

PostgreSQL raises an error because that column name does not exist in the query scope.

### 20.2. Sorting by a Type Without a Compatible Comparison Operator

Different PostgreSQL types have different operators and operator classes. Not every complex value sorts directly like `INTEGER` or `TEXT`.

For `JSONB`, if you want to sort by a specific JSON field, extract the value, cast it to the proper type, and handle missing/NULL cases.

Schematic example given a JSONB table `events(payload)`:

```sql
SELECT payload
FROM events
ORDER BY (payload ->> 'amount')::numeric DESC NULLS LAST;
```

Use this only if all non-NULL `amount` values can cast cleanly to `numeric`. Non-numeric strings will cause the cast to fail. This SQL snippet is an illustrative example and **does not require an `events` table in the lab**.

### 20.3. Sorting by an Expression While Forgetting a Type Cast

```sql
ORDER BY text_number
```

sorts as **text**, not numerically. Store numeric data in a numeric type or apply a controlled cast.

### 20.4. Failing to Stabilize Order on Key Ties

```sql
ORDER BY status ASC
```

merely groups/orders by status; rows sharing a status have nondeterministic order. Add timestamp and ID if the business needs stability.

### 20.5. Treating NULLS LAST as WHERE IS NOT NULL

```sql
ORDER BY due_at NULLS LAST
```

does not exclude tickets without a due date. To exclude them:

```sql
WHERE due_at IS NOT NULL
ORDER BY due_at ASC;
```

To **keep all tickets while pushing NULLs to the end**, use `NULLS LAST`.

### 20.6. Using ORDER BY random() on Large APIs

```sql
SELECT ticket_id
FROM sort_lab.tickets
ORDER BY random()
LIMIT 3;
```

This works for grabbing a **small, non-reproducible** random sample. On large tables, however, it computes `random()` and sorts many rows, consuming heavy resources. It also **produces no stable order for pagination**.

If you need reproducible samples or large-scale sampling, design a dedicated strategy (such as key/hash-based sampling) rather than running `ORDER BY random()` over millions of rows.

### 20.7. Confusing Ordering Across Concurrent Transactions

An `ORDER BY` result is deterministically ordered over **the rows visible to that snapshot/query**. When another transaction inserts, updates, or deletes rows, subsequent reads may observe a different dataset.

Tie-breakers eliminate ambiguity for a given set of rows; they do not lock the table or freeze data across transactions.

## 21. Practical Scenarios: Writing Business-Accurate ORDER BY

### 21.1. High-Priority Task List, Earliest Due Date First

Requirements:

- Priority `1` before `2` before `3`.
- Unclassified tickets at the **end**.
- Within the same priority, earliest due date first; no due date at the end of the group.
- On tied due date, newest created ticket first.
- Finally descending ID.

```sql
SELECT
    ticket_id, priority, due_at, created_at
FROM sort_lab.tickets
WHERE status <> 'RESOLVED'
ORDER BY
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

`WHERE` removes resolved tickets **before sorting the result**; it does not alter NULL-placement semantics.

### 21.2. Queue Putting Unassigned Tickets First

Requirements:

- Tickets with no `assigned_to` at the top.
- Assigned tickets sorted by assignee name.
- Within each assignee, newest tickets first.

```sql
SELECT ticket_id, assigned_to, created_at
FROM sort_lab.tickets
ORDER BY
    assigned_to ASC NULLS FIRST,
    created_at DESC,
    ticket_id DESC;
```

When `assigned_to` is NULL, those rows form the leading group, ordered internally by `created_at` and `ticket_id`.

### 21.3. Score Dashboard: Highest Score First, Ungraded Last

```sql
SELECT ticket_id, score, created_at
FROM sort_lab.tickets
ORDER BY
    score DESC NULLS LAST,
    created_at ASC,
    ticket_id ASC;
```

`created_at ASC` favors older tickets when scores tie. If the product requires newer tickets first on ties, switch it to `DESC`.

### 21.4. Multi-Tenant Admin View by Invoice Number

Suppose you have a table:

```text
invoices(tenant_id, issued_at, invoice_no, invoice_id)
```

Each tenant views newest invoices first, and ascending invoice number within the same date:

```sql
SELECT tenant_id, issued_at, invoice_no, invoice_id
FROM invoices
WHERE tenant_id = :tenant_id
ORDER BY issued_at DESC, invoice_no ASC, invoice_id ASC;
```

This is an API syntax example, not a table created in the lab. `invoice_id` serves as a tie-breaker in case invoice numbers can collide across a date range or dataset.

### 21.5. Custom Status Order and History

```sql
SELECT ticket_id, status, priority, created_at
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

If an API relies heavily on this sort on large tables, measure the cost of the expression sort and evaluate expression indexes or schema design changes. Never add indexes before gathering workload evidence.

## 22. Quick Reference Table

| Goal | Suggested ORDER BY | Notes |
|---|---|---|
| Ascending ID | `ORDER BY id ASC` | No NULLs if `id` is a PK |
| Newest first | `ORDER BY created_at DESC, id DESC` | `id` breaks same-timestamp ties |
| Highest score first, ungraded last | `ORDER BY score DESC NULLS LAST, id` | Plain `DESC` puts NULLs first by default |
| Earliest due first, no due date last | `ORDER BY due_at ASC NULLS LAST, id` | Explicit `NULLS LAST` |
| Untriaged first | `ORDER BY priority ASC NULLS FIRST, id` | NULL is not priority 0 |
| Multiple keys left-to-right | `ORDER BY team, priority, id` | Later keys apply only on ties |
| Custom business status order | `ORDER BY CASE ... END, id` | Do not rely on alphabetical order |
| Case-insensitive | `ORDER BY lower(name), id` | Still depends on collation/Unicode |
| Paginated slice | `ORDER BY created_at DESC, id DESC LIMIT 20` | Order must be deterministic |
| Latest per group | `DISTINCT ON (team) ... ORDER BY team, created_at DESC, id DESC` | Leading `ORDER BY` must match `DISTINCT ON` |
| Tied ranking | `RANK() OVER (ORDER BY score DESC NULLS LAST)` | Add `id` to outer `ORDER BY` for stability |
| Ordered array | `array_agg(id ORDER BY created_at DESC, id DESC)` | Sort inside the aggregate |
| By tenant and SKU | `ORDER BY tenant_id ASC, sku ASC` | Can leverage a matching B-tree index |

## 23. Checklist for Verifying ORDER BY on Real Data

A simple workflow:

~~~mermaid
flowchart TD
    A["Define business ordering"] --> B["List keys in priority order"]
    B --> C["Choose ASC/DESC for each key"]
    C --> D["Define NULL placement per key"]
    D --> E["Add a unique tie-breaker"]
    E --> F["Test tied and NULL rows"]
    F --> G{"Using LIMIT/OFFSET or cursor?"}
    G -- "Yes" --> H["Verify pagination and concurrent writes"]
    G -- "No" --> I["Verify output ordering"]
    H --> I
    I --> J["Run EXPLAIN and check indexes on large tables"]
~~~

Questions to answer before shipping:

1. **Is the first column the most important criterion?**
2. Does `ASC` or `DESC` match the column's business meaning (is priority 1 high or low)?
3. If the column is nullable, should it use `NULLS FIRST` or `NULLS LAST`?
4. When two rows match on all keys, does the final tie-breaker uniquely distinguish them?
5. Are there requirements around letter case, Vietnamese accents, or collation?
6. Are you using `LIMIT/OFFSET` and expecting stable results?
7. If using cursor pagination, are nullable keys and mixed directions handled properly?
8. If sorting appears inside a window/aggregate/subquery, does the outer query have its own `ORDER BY`?
9. On large tables, is a supporting index needed? What indexes already exist?
10. Does the sort consume excessive CPU, RAM, I/O, or temp disk space?

## 24. Practice Exercises

The following exercises use `sort_lab.tickets`. No additional write statements are needed.

### Exercise 1 — Basic Ascending

Write a query returning `ticket_id` and `priority`, sorted by ascending priority. Tickets with NULL priority must appear last; ascending ID breaks priority ties.

### Exercise 2 — DESC and NULL

Explain why:

```sql
ORDER BY score DESC
```

in PostgreSQL does **not** put all ungraded scores at the end. Fix it so highest scores come first, NULLs go last, and smaller IDs break ties.

### Exercise 3 — Multiple Sort Keys

Sort tickets by ascending team, ascending status, and newest first within each team/status. Add a final key so the result is completely deterministic.

### Exercise 4 — Business Priority and NULL

Using `priority` where 1 is highest, 3 is lowest, and NULL is untriaged: write a query putting highest priority first, NULLs last, then earliest due date first, NULLs last, and finally ascending ID.

### Exercise 5 — Verifiable Subset

Consider only ticket IDs 101, 103, 105, and 107. With:

```sql
ORDER BY priority DESC NULLS LAST, ticket_id
```

what is the resulting ticket ID order?

### Exercise 6 — Custom Status Order

Order `OPEN` before `NEW`, and `RESOLVED` last; within each status, highest score first, NULLs last; on tied scores, ascending ID. Use `CASE`.

### Exercise 7 — Letter Case

Sort tickets by assignee name case-insensitively, putting unassigned tickets last, with ascending ID on tied names.

### Exercise 8 — LIMIT/OFFSET

Fetch the five newest tickets (page 1), then the next five (page 2), with deterministic order even when multiple tickets share identical timestamps.

### Exercise 9 — Keyset DESC

A query uses `ORDER BY created_at DESC, ticket_id DESC` to return the first page. Write the cursor predicate to fetch the next page after the last row's `(created_at, ticket_id)`.

### Exercise 10 — Keyset with NULL

Given:

```sql
ORDER BY priority ASC NULLS LAST,
         created_at DESC,
         ticket_id DESC
```

why can't a single tuple `<` comparison handle every cursor if `priority` is nullable? Outline the solution for both non-NULL and NULL cursors.

### Exercise 11 — DISTINCT ON

Select the newest ticket per team, breaking timestamp ties by descending ID. Then display **those selected tickets** ordered globally by newest `created_at` first.

### Exercise 12 — Window Functions

Compute `ROW_NUMBER()` per team, prioritizing 1 first, NULLs last, newest first, descending ID. Sort the final output by team and the computed row number.

### Exercise 13 — Ordered Aggregate

Write a query returning each team along with an array of its ticket IDs ordered by `created_at DESC, ticket_id DESC`; sort teams alphabetically.

### Exercise 14 — Supporting Index

Write a B-tree index definition that can support:

```sql
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST,
         created_at DESC,
         ticket_id ASC
LIMIT 20;
```

Explain why the planner might still choose a Seq Scan on the 12-row dataset.

### Exercise 15 — Interpreting EXPLAIN

An `EXPLAIN ANALYZE` shows `Sort Method: external merge`. What does this indicate? Name three things to investigate before raising `work_mem` server-wide.

### Exercise 16 — Multi-Level ORDER BY

A query uses `DISTINCT ON(team)` to pick the latest row per team, then wants the overall result sorted by descending score with NULLs last. How many `ORDER BY` levels are needed and why?

### Exercise 17 — ORDER BY Is Not Data Filtering

A user asks to "push tickets without a due date to the end." When should you use only `NULLS LAST`, and when should you add `WHERE due_at IS NOT NULL`?

### Exercise 18 — Display Order and Indexes

An index on `created_at DESC` exists, and `SELECT * FROM tickets` seems to always return newest rows first. Can the API safely omit `ORDER BY created_at DESC`? Why or why not?

## 25. Suggested Solutions

### Exercise 1

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

### Exercise 2

PostgreSQL defaults to `DESC NULLS FIRST`, placing NULLs at the top. Fix:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

### Exercise 3

```sql
SELECT ticket_id, team, status, created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    status ASC,
    created_at DESC,
    ticket_id ASC;
```

Here `status` is text, so status order follows collation order rather than a custom business priority order.

### Exercise 4

```sql
SELECT ticket_id, priority, due_at
FROM sort_lab.tickets
ORDER BY
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    ticket_id ASC;
```

The two `NULLS LAST` clauses apply independently: one to `priority`, and one to `due_at` within the same priority group.

### Exercise 5

Order:

```text
105, 103, 101, 107
```

Because priorities are 3, 2, 1, NULL; `NULLS LAST` overrides `DESC`'s default `NULLS FIRST`.

### Exercise 6

```sql
SELECT ticket_id, status, score
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END ASC,
    score DESC NULLS LAST,
    ticket_id ASC;
```

### Exercise 7

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC;
```

`lower()` handles basic case folding; collation still governs string comparison rules.

### Exercise 8

Page 1:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 0;
```

Page 2:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 5;
```

Adding ID breaks timestamp ties. If data changes between requests, `OFFSET` can still cause duplicates or skipped rows.

### Exercise 9

Using two `DESC` keys, both non-NULL:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
WHERE (created_at, ticket_id)
    < (:last_created_at, :last_id)
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

Placeholders must be bound via the driver, never concatenated into SQL strings.

### Exercise 10

SQL tuple comparisons with NULL can evaluate to `UNKNOWN` and do not automatically replicate `NULLS LAST` logic. When the cursor priority is non-NULL, select higher priorities, equal priority with older timestamp/ID, and all NULL priorities. When the cursor priority is NULL, select only NULL-priority rows coming after the cursor under the remaining two keys. Implement two branches as shown in section 12.3.

### Exercise 11

```sql
SELECT team, ticket_id, created_at, status
FROM (
    SELECT DISTINCT ON (team)
        team, ticket_id, created_at, status
    FROM sort_lab.tickets
    ORDER BY team, created_at DESC, ticket_id DESC
) AS latest
ORDER BY created_at DESC, ticket_id DESC;
```

The inner `ORDER BY` picks the newest row per group; the outer `ORDER BY` controls overall result ordering.

### Exercise 12

```sql
SELECT
    ticket_id,
    team,
    priority,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY
            priority ASC NULLS LAST,
            created_at DESC,
            ticket_id DESC
    ) AS rn
FROM sort_lab.tickets
ORDER BY team ASC, rn ASC;
```

### Exercise 13

```sql
SELECT
    team,
    array_agg(
        ticket_id
        ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_ids
FROM sort_lab.tickets
GROUP BY team
ORDER BY team ASC;
```

### Exercise 14

```sql
CREATE INDEX ix_tickets_support_sort
ON sort_lab.tickets (
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC
);
```

The planner may still choose Seq Scan because the table is tiny, so scanning a few rows is cheaper than traversing an index. An index is never guaranteed to be used.

### Exercise 15

`external merge` indicates the sort spilled to temporary disk files instead of completing entirely in memory. Investigate: how many rows/columns enter the sort, whether filters and `LIMIT` can be pushed down earlier, whether an index can supply the sort order, row width, and concurrency. Only consider increasing `work_mem` after measuring memory and temp I/O.

### Exercise 16

Two levels are required:

1. `DISTINCT ON(team)` with `ORDER BY team, created_at DESC, ticket_id DESC` to select the newest ticket per team.
2. An outer query with `ORDER BY score DESC NULLS LAST, ticket_id ASC` to sort those selected tickets for display.

### Exercise 17

Use `ORDER BY due_at ASC NULLS LAST` when you still want to **keep tickets without a due date** at the bottom. Use `WHERE due_at IS NOT NULL` when the requirement is actually to **show only tickets that have a due date**.

### Exercise 18

No. An index can influence the scan plan, but SQL makes no guarantee about result order without `ORDER BY`. The planner can choose a different scan, use parallelism, or switch plans as data grows. The API must declare ordering explicitly.

## 26. Conclusion

`ORDER BY` is the **ordering contract for a query's output**, not a permanent physical order for a table. With multiple keys, PostgreSQL compares **from left to right**; each key has its own `ASC`/`DESC` direction and NULL placement.

Key takeaways:

- **Without `ORDER BY`, there is no guarantee of row order.**
- PostgreSQL defaults to **`ASC NULLS LAST`** and **`DESC NULLS FIRST`**.
- Write `NULLS FIRST/LAST` explicitly whenever business logic requires it, especially with `DESC`.
- Add a **unique tie-breaker** for deterministic order, particularly before `LIMIT`, `OFFSET`, or cursor pagination.
- `DISTINCT ON`, window functions, and aggregates can have internal `ORDER BY` clauses **for their own calculations**; final output order still requires an outer `ORDER BY`.
- B-tree indexes can let PostgreSQL return sorted rows without a separate sort, yet **column order, direction, NULL placement, filters, and statistics** govern index usability.
- `EXPLAIN` inspects the estimated plan; `EXPLAIN ANALYZE` executes the query to measure runtime, so run it in an appropriate environment.
- Across paginated requests, tie-breakers ensure deterministic ordering over a snapshot, **not snapshot isolation or concurrency control**.

A reliable way to construct any sorting query is: **put the most important key first → choose each key's direction → specify NULL behavior → add a unique tie-breaker → verify pagination → measure the plan on representative data**.
