# ON, USING, and the Risks of NATURAL JOIN in PostgreSQL

## 1. When Combining Two Tables, the Join Condition Matters More Than Short Syntax

In a relational database, information is typically split across multiple tables to avoid data duplication and preserve integrity. For example, the `teams` table stores team information, while the `members` table stores members and the team ID each person belongs to. To display a member's name alongside their team name, you must **JOIN** the two tables.

PostgreSQL provides multiple ways to specify a JOIN condition:

- **`ON`**: writes the join condition expression explicitly, such as `ON m.team_id = t.team_id`.
- **`USING`**: lists **same-named columns on both sides** to join by equality, such as `USING (team_id)`.
- **`NATURAL JOIN`**: omits the column list; PostgreSQL **automatically picks every column with the same name** on both sides as equality conditions.

At first glance, `NATURAL JOIN` looks short and convenient. Yet that very "auto-match columns" feature makes queries prone to **silently changing meaning without raising an error as the schema evolves**.

Compare three styles:

```sql
-- Style 1: explicit condition.
SELECT m.member_name, t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;

-- Style 2: concise when key names match across both tables.
SELECT m.member_name, t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);

-- Style 3: automatically joins on ALL same-named columns.
SELECT member_name, team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams;
```

The first two queries are equivalent in terms of **joined rows** in this example. The third query can return a different result because both tables also share a column named `status` that carries **different business meanings**.

> **Best practice:** prefer `JOIN ... ON` when you want to express conditions explicitly; use `JOIN ... USING` when you genuinely want to join on matching column names; avoid `NATURAL JOIN` in application SQL that needs long-term stability.

This lesson explains not only which rows are selected, but also **output column counts**, **NULL**, **LEFT/FULL JOIN**, **composite keys**, **schema drift**, and how to spot wrong results.

## 2. Background: What Does a JOIN Do?

Consider two datasets:

```text
teams
+---------+-----------+
| team_id | team_name |
+---------+-----------+
| 10      | Core      |
| 20      | Analytics |
+---------+-----------+

members
+-----------+-------------+---------+
| member_id | member_name | team_id |
+-----------+-------------+---------+
| 101       | An          | 10      |
| 102       | Bình        | 10      |
| 103       | Chi         | 20      |
+-----------+-------------+---------+
```

If you run:

```sql
SELECT m.member_name, t.team_name
FROM members AS m
JOIN teams AS t
    ON m.team_id = t.team_id;
```

you want the result:

```text
An   | Core
Bình | Core
Chi  | Analytics
```

The join condition `m.team_id = t.team_id` determines **which pairs of rows from the two tables relate to each other**.

Not all JOINs behave the same:

| JOIN Type | Which Rows Are Kept? |
| --- | --- |
| `INNER JOIN` or `JOIN` | Only row pairs matching the join condition |
| `LEFT [OUTER] JOIN` | Keeps all left rows; unmatched right side is filled with NULL |
| `RIGHT [OUTER] JOIN` | Keeps all right rows; unmatched left side is filled with NULL |
| `FULL [OUTER] JOIN` | Keeps matched rows as well as unmatched rows from both sides |
| `CROSS JOIN` | Cartesian product: every left–right row pair |
| `NATURAL JOIN` | Not a separate preservation type; a way to **auto-select join columns**, defaulting to `NATURAL INNER JOIN` |

`ON` and `USING` can be combined with `INNER`, `LEFT`, `RIGHT`, or `FULL`. Likewise, `NATURAL` can be paired with those join types, yet PostgreSQL infers the compared columns automatically, introducing risk.

In this lesson, **match** means the join condition expression evaluates to `TRUE`. If the condition evaluates to `FALSE` or `UNKNOWN` due to NULL, the two rows **do not match** in a standard JOIN.

## 3. Creating a PostgreSQL Dataset for Practice

The examples use the `join_lab` schema in an isolated test database. You need privileges to create schemas, tables, and insert data. Do not execute illustrative DDL statements on a production database.

### 3.1. Teams Table: `teams`

```sql
CREATE SCHEMA IF NOT EXISTS join_lab;

CREATE TABLE join_lab.teams (
    team_id bigint PRIMARY KEY,
    team_name text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('ACTIVE', 'INACTIVE')
    ),
    created_at date NOT NULL
);
```

Each team has a unique `team_id`. The `status` column indicates whether the **team** is still active or inactive.

### 3.2. Members Table: `members`

```sql
CREATE TABLE join_lab.members (
    member_id bigint PRIMARY KEY,
    member_name text NOT NULL,
    team_id bigint REFERENCES join_lab.teams(team_id),
    status text NOT NULL CHECK (
        status IN ('ACTIVE', 'INACTIVE')
    ),
    joined_at date NOT NULL
);
```

The `team_id` column in `members` is a foreign key referencing `teams.team_id`. It is nullable to represent a member not yet assigned to a team.

The `members.status` column represents the **member's status**, not the team's status.

This is the key detail: **both tables share the column name `status`, yet there is no requirement that the two values be equal**.

### 3.3. Loading Data

```sql
INSERT INTO join_lab.teams
    (team_id, team_name, status, created_at)
VALUES
    (10, 'Core',      'ACTIVE',   DATE '2026-01-10'),
    (20, 'Analytics', 'ACTIVE',   DATE '2026-02-01'),
    (30, 'Archive',   'INACTIVE', DATE '2025-06-01'),
    (40, 'Support',   'ACTIVE',   DATE '2026-03-15');

INSERT INTO join_lab.members
    (member_id, member_name, team_id, status, joined_at)
VALUES
    (101, 'An',    10,   'ACTIVE',   DATE '2026-01-15'),
    (102, 'Bình',  10,   'INACTIVE', DATE '2026-02-12'),
    (103, 'Chi',   20,   'ACTIVE',   DATE '2026-03-10'),
    (104, 'Dung',  30,   'ACTIVE',   DATE '2026-04-01'),
    (105, 'Em',    30,   'INACTIVE', DATE '2025-07-20'),
    (106, 'Phúc',  NULL, 'ACTIVE',   DATE '2026-05-05'),
    (107, 'Giang', 20,   'ACTIVE',   DATE '2026-06-12');
```

Illustrative data:

**`teams` table**

| team_id | team_name | status |
| ---: | --- | --- |
| 10 | Core | ACTIVE |
| 20 | Analytics | ACTIVE |
| 30 | Archive | INACTIVE |
| 40 | Support | ACTIVE |

**`members` table**

| member_id | member_name | team_id | status |
| ---: | --- | ---: | --- |
| 101 | An | 10 | ACTIVE |
| 102 | Bình | 10 | INACTIVE |
| 103 | Chi | 20 | ACTIVE |
| 104 | Dung | 30 | ACTIVE |
| 105 | Em | 30 | INACTIVE |
| 106 | Phúc | NULL | ACTIVE |
| 107 | Giang | 20 | ACTIVE |

Observations before joining:

- Team 10 has An and Bình, though Bình is `INACTIVE`.
- Team 30 is `INACTIVE`, yet Dung still has member status `ACTIVE`.
- Phúc has no `team_id` yet.
- Team 40 has no members.

These cases highlight the difference between joining properly on **team ID** versus accidentally also joining on `status`.

## 4. `JOIN ... ON`: Expressing Join Conditions Explicitly

### 4.1. Basic Syntax

```sql
SELECT ...
FROM left_table AS l
JOIN right_table AS r
    ON l.join_key = r.join_key;
```

In PostgreSQL, `JOIN` without a type modifier means `INNER JOIN`.

Example:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id,
    t.team_name
FROM join_lab.members AS m
INNER JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Result:

| member_id | member_name | team_id | team_name |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Core |
| 102 | Bình | 10 | Core |
| 103 | Chi | 20 | Analytics |
| 104 | Dung | 30 | Archive |
| 105 | Em | 30 | Archive |
| 107 | Giang | 20 | Analytics |

Phúc (106) does not appear because `m.team_id` is NULL, which does not equal any team ID under `=`.

**Key point:** `ON m.team_id = t.team_id` compares only the team ID. It does **not** require `m.status` to equal `t.status`.

### 4.2. `ON` Does Not Require Same-Named Columns

If a system has `users.department_id` and `departments.id`, you write:

```sql
SELECT ...
FROM users AS u
JOIN departments AS d
    ON u.department_id = d.id;
```

`USING (department_id)` cannot be applied if `departments` does not have a column named `department_id`. In that case, `ON` is the clear way to express it.

### 4.3. `ON` Can Contain Multiple Conditions

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

With INNER JOIN, the result includes `101, 102, 103, 107`. Members Dung and Em belong to the inactive Archive team, so they fail the second condition.

This is an **intentional** condition: joining members only to **active teams**.

Do not confuse it with:

```sql
ON m.team_id = t.team_id
AND m.status = t.status
```

The latter requires two **statuses with different meanings** to be equal, which can discard valid rows.

### 4.4. `ON` Supports Expressions Beyond Equality

In a problem with clear business requirements, `ON` can use:

```sql
ON a.value < b.limit_value
```

or:

```sql
ON a.key IS NOT DISTINCT FROM b.key
```

or combine multiple comparisons. Not all such conditions can be written with `USING`, because `USING` only generates equality checks on **same-named columns**.

For non-equality joins, be mindful of **generated row counts**, NULL behavior, and performance; a range join can produce multiple matches per row.

## 5. `JOIN ... USING`: Concise Syntax When Key Names Match

### 5.1. Syntax

```sql
SELECT ...
FROM left_table
JOIN right_table
    USING (shared_column);
```

This is shorthand when **both sides share the exact column name** and you intend an equality join.

On our example tables:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

The returned members remain `101, 102, 103, 104, 105, 107`, identical to `ON m.team_id = t.team_id`.

### 5.2. Which Condition Does `USING (team_id)` Correspond To?

For the two example tables, you can view:

```sql
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
```

as having row-matching semantics equivalent to:

```sql
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
```

**However, the two forms do not produce the same column set under `SELECT *`.** That important difference is explained in the next section.

### 5.3. `USING` Does Not Automatically Join Other Same-Named Columns

The `members` and `teams` tables have two columns with the same name: `team_id` and `status`.

When writing:

```sql
USING (team_id)
```

PostgreSQL uses only **`team_id`** as the JOIN condition. It **does not automatically add** `status`.

If you intentionally write:

```sql
USING (team_id, status)
```

then both columns are used as conditions. That is equivalent to requiring:

```sql
ON m.team_id = t.team_id
AND m.status = t.status
```

In the sample data, also joining on `status` drops Bình (102) and Dung (104) even though they have valid team IDs.

Hence, `USING` is safer than `NATURAL JOIN` because **the column list is explicitly declared**; still, it can be wrong if the author lists the wrong column.

## 6. Biggest Difference Between `ON` and `USING` Under `SELECT *`

Look at the structure of both tables:

```text
members:
member_id | member_name | team_id | status | joined_at

teams:
team_id | team_name | status | created_at
```

### 6.1. `SELECT *` with `ON` Keeps Both Key Columns

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Conceptual output column list:

```text
member_id
member_name
m.team_id
m.status
joined_at
t.team_id
team_name
t.status
created_at
```

Because `SELECT *` pulls all columns from both sides, `team_id` appears **twice**, as does `status`.

This can inconvenience consumers reading results by **column name**: two columns with the same label are hard to distinguish when mapping to JSON or dictionaries. Never build an API around `SELECT *` on a JOIN with overlapping column names.

### 6.2. `SELECT *` with `USING` Merges the Key Column

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

Conceptual output column list:

```text
team_id           <-- merged output column from USING
member_id
member_name
m.status
joined_at
team_name
t.status
created_at
```

`USING (team_id)` does **not** emit two separate `team_id` columns in `SELECT *`. It creates **a single output column** named `team_id`, placed ahead of the remaining columns.

Meanwhile, `status` is not in the `USING` list, so it still appears from **both sides**.

### 6.3. Column Order of `USING`

With `JOIN ... USING (key_a, key_b)`, `SELECT *` typically orders columns as:

1. The columns in `USING`, in the order listed.
2. Remaining columns from the left side.
3. Remaining columns from the right side.

Therefore, do not view `USING` merely as "shorter `ON`": it also **changes the shape of the result** when selecting all columns.

### 6.4. Use Explicit `SELECT` to Control the Output Contract

A clear style:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id AS assigned_team_id,
    m.status AS member_status,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Or with `USING`:

```sql
SELECT
    team_id,
    m.member_id,
    m.member_name,
    m.status AS member_status,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

The output is self-describing, more stable, and easier for applications to consume. Even as new columns are added to tables, the query will not accidentally expose extra fields in an API due to `SELECT *`.

## 7. Referencing Columns After `USING` and Ambiguous Column Names

### 7.1. Merged Columns Can Be Referenced Unqualified

```sql
SELECT
    team_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY team_id, m.member_name;
```

`team_id` is a shared column in the JOIN result, so you can reference it directly without a table qualifier.

### 7.2. Same-Named Columns Not Listed in `USING` Remain Ambiguous

Wrong:

```sql
-- status exists in both members and teams:
SELECT status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

PostgreSQL does not know whether you want `m.status` or `t.status`; it will fail with **column reference "status" is ambiguous**.

Correct:

```sql
SELECT
    m.status AS member_status,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Rule:** after a JOIN, always qualify with aliases and clear output aliases for columns that might collide. `USING` resolves only the **listed** columns.

### 7.3. You Can Still Reference Individual Sides When Needed

In many contexts, PostgreSQL allows qualified references to the source columns of a `USING` condition, such as `m.team_id` and `t.team_id`, while both table aliases remain in scope. This is particularly useful for distinguishing behavior in `LEFT` or `FULL JOIN`.

However, if you want the merged key in the output, an unqualified `team_id` is usually clearer; if you need the value from **each individual side**, writing `ON` with explicit aliases is cleaner.

## 8. How Does `NATURAL JOIN` Work?

### 8.1. PostgreSQL Automatically Picks All Shared Column Names

The form:

```sql
SELECT ...
FROM left_table
NATURAL JOIN right_table;
```

is equivalent in join-condition selection to a `USING` clause built automatically by PostgreSQL from **all column names appearing on both sides**.

In our `members` and `teams` example, the shared names are:

- `team_id`
- `status`

Therefore:

```sql
SELECT member_id, member_name, team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams
ORDER BY member_id;
```

is nearly equivalent to:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id, status)
ORDER BY m.member_id;
```

**Notice:** `status` was automatically added to the condition even though a member's status is **not** the team's status.

### 8.2. Actual Result Differs from `ON` and `USING (team_id)`

When joining only on `team_id`:

| member_id | member_name | team_name | member_status | team_status |
| ---: | --- | --- | --- | --- |
| 101 | An | Core | ACTIVE | ACTIVE |
| 102 | Bình | Core | INACTIVE | ACTIVE |
| 103 | Chi | Analytics | ACTIVE | ACTIVE |
| 104 | Dung | Archive | ACTIVE | INACTIVE |
| 105 | Em | Archive | INACTIVE | INACTIVE |
| 107 | Giang | Analytics | ACTIVE | ACTIVE |

With `NATURAL JOIN`, PostgreSQL simultaneously requires:

```text
m.team_id = t.team_id
AND
m.status = t.status
```

So the result shrinks to:

| member_id | member_name | team_name |
| ---: | --- | --- |
| 101 | An | Core |
| 103 | Chi | Analytics |
| 105 | Em | Archive |
| 107 | Giang | Analytics |

Bình (102) and Dung (104) are dropped **not because they have no team**, but because their member status does not match their team status.

This is a dangerous bug: the query **is syntactically valid, executes without error, yet silently returns incomplete data**.

### 8.3. `NATURAL JOIN` Does Not Understand Business Semantics

PostgreSQL does not know that `members.status` is a person's status while `teams.status` is a team's status. It only sees **matching column names**.

Column names that frequently cause accidental collisions:

- `status`
- `name`
- `code`
- `created_at`
- `updated_at`
- `id`
- `type`
- `version`

An `updated_at` column across two tables is usually an independent timestamp and should never automatically become an equality join predicate.

**Never infer that "same name" means "relational key."** Join keys must come from the data model, foreign key constraints, and business intent.

## 9. Biggest Risk: `NATURAL JOIN` Changes Results When the Schema Evolves

Suppose two tables initially share only one column name:

```text
employees(employee_id, department_id, employee_name)
departments(department_id, department_name)
```

At that point:

```sql
FROM employees NATURAL JOIN departments
```

might produce the intended result because `department_id` is the sole shared column name.

Later, after a release, the team adds:

```text
employees.status
departments.status
```

The `NATURAL JOIN` SQL query **has not changed by a single character**, yet PostgreSQL silently starts joining on `status` as well.

### 9.1. Demonstrating Schema Drift with a CTE Without Modifying Real Tables

**Before adding a same-named column:**

```sql
WITH
left_data(key_id, left_label) AS (
    VALUES
        (1, 'L1'),
        (2, 'L2')
),
right_data(key_id, right_label) AS (
    VALUES
        (1, 'R1'),
        (2, 'R2')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY key_id;
```

Both sides share only `key_id`, so the result contains both keys `1` and `2`.

**After both sides acquire a `flag` column:**

```sql
WITH
left_data(key_id, flag, left_label) AS (
    VALUES
        (1, 'ENABLED', 'L1'),
        (2, 'ENABLED', 'L2')
),
right_data(key_id, flag, right_label) AS (
    VALUES
        (1, 'DISABLED', 'R1'),
        (2, 'ENABLED',  'R2')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY key_id;
```

Now `NATURAL JOIN` automatically compares **both `key_id` and `flag`**. Row 1 no longer matches; only key 2 remains.

What is alarming is that the query throws no "schema changed" warning; it quietly alters the result set. If that query drives a revenue report or data reconciliation, the bug can go unnoticed for a long time.

### 9.2. Why Are `USING` or `ON` More Stable?

With the same example:

```sql
SELECT *
FROM left_data AS l
JOIN right_data AS r
    USING (key_id);
```

or:

```sql
SELECT *
FROM left_data AS l
JOIN right_data AS r
    ON l.key_id = r.key_id;
```

Both queries keep the join condition strictly on `key_id` even after `flag` is added.

`SELECT *` may change its output column count after a schema change, yet **the row-pairing condition does not change behind your back**.

To keep output schemas stable as well, use an **explicit SELECT column list** instead of `*`.

### 9.3. Adding a Shared Column Can Cause Runtime Errors, Not Just Wrong Filtering

If two newly added columns share a name yet have **incompatible data types for equality**, `NATURAL JOIN` can fail with an operator or type resolution error even on queries that previously ran cleanly.

Thus schema drift carries two layers of risk:

1. **Silent semantic corruption** when the types happen to be comparable.
2. **Runtime errors** when the new implicit condition is invalid.

Both are strong reasons to avoid `NATURAL JOIN` in applications requiring stable SQL contracts.

## 10. When There Are No Shared Columns: NATURAL Becomes CROSS JOIN

Another very dangerous case: the two tables have zero shared column names.

```sql
WITH
left_data(left_id, left_value) AS (
    VALUES
        (1, 'A'),
        (2, 'B')
),
right_data(right_id, right_value) AS (
    VALUES
        (10, 'X'),
        (20, 'Y'),
        (30, 'Z')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY left_id, right_id;
```

With no shared columns to form an equality condition, `NATURAL JOIN` behaves like **`CROSS JOIN`**: every left row pairs with every right row.

With 2 rows on the left and 3 on the right, the result has:

```text
2 x 3 = 6 rows
```

Result:

| left_id | left_value | right_id | right_value |
| ---: | --- | ---: | --- |
| 1 | A | 10 | X |
| 1 | A | 20 | Y |
| 1 | A | 30 | Z |
| 2 | B | 10 | X |
| 2 | B | 20 | Y |
| 2 | B | 30 | Z |

If the left side has 100,000 rows and the right side has 50,000 rows, the Cartesian product can produce up to **5 billion row pairs** before any downstream operations are evaluated. This can make the query extremely slow and exhaust resources.

### 10.1. Distinguish Intentional CROSS JOIN

```sql
SELECT *
FROM left_data
CROSS JOIN right_data;
```

Use `CROSS JOIN` when you **genuinely want every combination**, such as generating every size × color pair from two small tables. Its intent is explicit.

Using `NATURAL JOIN` when no columns happen to match creates an **unintended** Cartesian product.

### 10.2. Why Is This the Opposite Failure Mode of Adding a Column?

When adding a shared column, `NATURAL JOIN` can **over-filter**.

When removing or renaming a shared column, `NATURAL JOIN` can **drop join conditions** and produce **far too many rows**.

The join condition is therefore brittle against both **adding** and **removing/renaming** columns.

## 11. `LEFT JOIN ... ON`: Preserving All Rows on the Left Side

### 11.1. Including Members Without a Team

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Result:

| member_id | member_name | team_id | team_name |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Core |
| 102 | Bình | 10 | Core |
| 103 | Chi | 20 | Analytics |
| 104 | Dung | 30 | Archive |
| 105 | Em | 30 | Archive |
| 106 | Phúc | NULL | NULL |
| 107 | Giang | 20 | Analytics |

`LEFT JOIN` preserves member Phúc even though `team_id` is unassigned. Since no `teams` row matches, `t.team_name` is filled with NULL.

### 11.2. Using `USING` with LEFT JOIN

```sql
SELECT
    m.member_id,
    m.member_name,
    team_id,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

The rows and displayed values match the previous query.

For `LEFT JOIN ... USING (team_id)`, the merged `team_id` output column **prefers the left-side value**. On matched rows, both team IDs are equal; on unmatched rows, the value still comes from the left side.

This distinction matters when extending to `RIGHT` or `FULL JOIN`.

## 12. Condition Placement: `ON` vs. `WHERE` with OUTER JOIN

This is a common pitfall even when `ON` is written properly.

Requirement: "Show **all members**, and attach team info only **if the team is ACTIVE**."

Correct:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

Members in the Archive team (104, 105) and the unassigned member (106) **still appear**, with NULL team columns when there is no matching ACTIVE team.

If you move the condition into `WHERE`:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
WHERE t.status = 'ACTIVE'
ORDER BY m.member_id;
```

the query keeps only `101, 102, 103, 107`. Unmatched rows have `t.status = NULL`, so `WHERE t.status = 'ACTIVE'` evaluates to UNKNOWN and drops them.

**Semantic difference:**

- Conditions in `ON` determine **which rows match**, prior to generating outer-join null-extended rows.
- Conditions in `WHERE` filter the **JOIN result**, which can discard unmatched rows that `LEFT JOIN` was meant to preserve.

With `INNER JOIN`, many conditions can move between `ON` and `WHERE` without changing the result set. **Never generalize that to outer joins.**

## 13. `USING` in `RIGHT JOIN` and `FULL JOIN`

`USING` is not limited to INNER JOIN.

### 13.1. RIGHT JOIN: Preserving the Right Side

To preserve every team, including Support with no members:

```sql
SELECT
    t.team_id,
    t.team_name,
    m.member_id,
    m.member_name
FROM join_lab.members AS m
RIGHT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY t.team_id, m.member_id;
```

Team 40 still appears with `member_id = NULL` and `member_name = NULL`.

You can write the equivalent query by reversing the tables:

```sql
SELECT
    t.team_id,
    t.team_name,
    m.member_id,
    m.member_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    ON m.team_id = t.team_id
ORDER BY t.team_id, m.member_id;
```

Many teams prefer `LEFT JOIN` because reading "keep the main table on the left" is easier to follow; `RIGHT JOIN` remains valid syntax.

### 13.2. FULL JOIN: Preserving Both Sides

Use two simple datasets to observe:

```sql
WITH
left_side(team_id, left_value) AS (
    VALUES
        (1, 'L1'),
        (2, 'L2')
),
right_side(team_id, right_value) AS (
    VALUES
        (2, 'R2'),
        (3, 'R3')
)
SELECT
    team_id,
    left_value,
    right_value
FROM left_side
FULL JOIN right_side
    USING (team_id)
ORDER BY team_id;
```

Result:

| team_id | left_value | right_value |
| ---: | --- | --- |
| 1 | L1 | NULL |
| 2 | L2 | R2 |
| 3 | NULL | R3 |

The single `team_id` column in the `USING` output shows the row's key **from whichever side has data**:

- Key 1: left only, so `team_id = 1`.
- Key 2: matched on both sides, both equal 2.
- Key 3: right only, so `team_id = 3`.

In terms of values, the merged column in `FULL JOIN ... USING` behaves like:

```sql
COALESCE(left_side.team_id, right_side.team_id)
```

For rows matched by `=`, both key values are equal; for one-sided unmatched rows, the other side is NULL.

### 13.3. If Using `FULL JOIN ... ON`

```sql
WITH
left_side(team_id, left_value) AS (
    VALUES (1, 'L1'), (2, 'L2')
),
right_side(team_id, right_value) AS (
    VALUES (2, 'R2'), (3, 'R3')
)
SELECT
    COALESCE(l.team_id, r.team_id) AS team_id,
    l.team_id AS left_team_id,
    r.team_id AS right_team_id,
    l.left_value,
    r.right_value
FROM left_side AS l
FULL JOIN right_side AS r
    ON l.team_id = r.team_id
ORDER BY team_id;
```

Here `ON` keeps **both source key columns** independent in `SELECT`, and the author chooses whether to merge them via `COALESCE`.

This is why `ON` is sometimes clearer than `USING` in **reconciliation** reports, where you need to see whether a key existed only on the left, only on the right, or on both sides.

## 14. `NATURAL LEFT JOIN` Is Also Risky

It is not just `NATURAL INNER JOIN`: PostgreSQL allows variants such as:

```sql
SELECT ...
FROM left_table
NATURAL LEFT JOIN right_table;
```

This means `LEFT JOIN`, yet the join condition is still inferred from **all same-named columns**.

In the sample dataset, writing:

```sql
SELECT
    member_id,
    member_name,
    team_name
FROM join_lab.members
NATURAL LEFT JOIN join_lab.teams
ORDER BY member_id;
```

still keeps all left-side members, **but** Bình (102) and Dung (104) fail to match because their statuses differ. They show `team_name = NULL` even though their `team_id` exists in `teams`.

This bug is easily misdiagnosed as "broken foreign key" or "unsynced team data," when the real culprit is that `NATURAL` injected the wrong predicate.

The difference:

- `NATURAL INNER JOIN` typically **drops rows**.
- `NATURAL LEFT JOIN` preserves rows yet **silently drops right-side information**.

**No outer join variant fixes the risks of `NATURAL`.**

## 15. Comparing Behavior When JOIN Keys Contain NULL

### 15.1. `=` Does Not Treat Two NULLs as Equal

In PostgreSQL:

```sql
SELECT
    NULL::integer = NULL::integer AS normal_equality,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equality;
```

`normal_equality` is NULL (UNKNOWN); `null_safe_equality` is TRUE.

Because `USING (team_id)` and `NATURAL JOIN` rely on standard equality across matching columns, **two rows with NULL keys do not automatically match each other**.

### 15.2. NULL-Safe JOIN When Business Logic Truly Requires It

Suppose raw data tables have two nullable keys and a special rule requires treating "both NULL" as the same group:

```sql
WITH
a(key_value, left_note) AS (
    VALUES
        (1::integer, 'A1'),
        (NULL::integer, 'A_NULL')
),
b(key_value, right_note) AS (
    VALUES
        (1::integer, 'B1'),
        (NULL::integer, 'B_NULL')
)
SELECT
    a.key_value AS left_key,
    b.key_value AS right_key,
    a.left_note,
    b.right_note
FROM a
JOIN b
    ON a.key_value IS NOT DISTINCT FROM b.key_value
ORDER BY a.left_note;
```

The result includes both the `1–1` pair and the `NULL–NULL` pair.

`USING (key_value)` **cannot** express this NULL-safe condition because it always uses standard equality rules.

**Warning:** if both tables have many NULL rows, a null-safe join can produce **huge numbers of NULL–NULL combinations**, inflating row counts sharply. Never use it merely to "fix" INNER JOIN skipping missing values; verify whether NULL genuinely represents a shared key.

### 15.3. Outer Joins Still Preserve Unmatched Rows

With `LEFT JOIN`, a left row with a NULL key is still kept without right-side values. If the requirement is "show unassigned members too," `LEFT JOIN` is far more appropriate than treating NULL as a synthetic team key.

## 16. Multi-Column JOINs: `ON` and `USING` with Composite Keys

In a multi-tenant system, an ID may be unique only **within a tenant**, not globally across the database.

Example:

```text
invoices
tenant_id | invoice_id | issued_date
----------+------------+------------
1         | 500        | ...
2         | 500        | ...
1         | 501        | ...

invoice_lines
tenant_id | invoice_id | line_no | quantity
----------+------------+---------+---------
1         | 500        | 1       | 2
2         | 500        | 1       | 3
1         | 501        | 1       | 1
```

### 16.1. Creating Composite Primary and Foreign Keys

```sql
CREATE TABLE join_lab.invoices (
    tenant_id integer NOT NULL,
    invoice_id bigint NOT NULL,
    issued_date date NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id)
);

CREATE TABLE join_lab.invoice_lines (
    tenant_id integer NOT NULL,
    invoice_id bigint NOT NULL,
    line_no integer NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, invoice_id, line_no),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES join_lab.invoices (tenant_id, invoice_id)
);
```

Load data:

```sql
INSERT INTO join_lab.invoices
    (tenant_id, invoice_id, issued_date)
VALUES
    (1, 500, DATE '2026-10-01'),
    (2, 500, DATE '2026-10-02'),
    (1, 501, DATE '2026-10-03');

INSERT INTO join_lab.invoice_lines
    (tenant_id, invoice_id, line_no, quantity)
VALUES
    (1, 500, 1, 2),
    (2, 500, 1, 3),
    (1, 501, 1, 1);
```

### 16.2. Joining Properly on Both Key Columns

With `ON`:

```sql
SELECT
    l.tenant_id,
    l.invoice_id,
    l.line_no,
    l.quantity,
    i.issued_date
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    ON l.tenant_id = i.tenant_id
   AND l.invoice_id = i.invoice_id
ORDER BY l.tenant_id, l.invoice_id, l.line_no;
```

With `USING`:

```sql
SELECT
    tenant_id,
    invoice_id,
    l.line_no,
    l.quantity,
    i.issued_date
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    USING (tenant_id, invoice_id)
ORDER BY tenant_id, invoice_id, l.line_no;
```

Both return the exact three rows:

| tenant_id | invoice_id | line_no | quantity |
| ---: | ---: | ---: | ---: |
| 1 | 500 | 1 | 2 |
| 1 | 501 | 1 | 1 |
| 2 | 500 | 1 | 3 |

### 16.3. Omitting Part of the Key Can Cross-Join Tenants

Wrong:

```sql
SELECT
    l.tenant_id AS line_tenant,
    i.tenant_id AS invoice_tenant,
    l.invoice_id,
    l.quantity
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    ON l.invoice_id = i.invoice_id
ORDER BY l.invoice_id, line_tenant, invoice_tenant;
```

Because `invoice_id = 500` exists in both tenant 1 and tenant 2, each line item with ID 500 matches **both invoices**, generating **four pairs** instead of two valid pairs. Plus invoice 501, the total becomes five rows.

Partial invalid output:

```text
line_tenant = 1, invoice_tenant = 2, invoice_id = 500
line_tenant = 2, invoice_tenant = 1, invoice_id = 500
```

This is not merely "duplicate data"—it can become a **cross-tenant data leak** or corrupt financial reports if tenant verification/filtering is not thoroughly enforced.

`USING (tenant_id, invoice_id)` provides a concise way to write composite key joins, yet **you must still list every key component**. `USING (invoice_id)` is just as semantically broken as `ON l.invoice_id = i.invoice_id` in this example.

## 17. Multi-Table JOINs and the Scope of `USING`

When joining three or more tables, chaining multiple `JOIN ... USING` clauses can be concise, yet you must stay aware of **intermediate results**.

Suppose we have these relations:

```text
orders(order_id, customer_id, created_at)
customers(customer_id, customer_name)
payments(payment_id, order_id, state)
```

Sample query:

```sql
SELECT
    order_id,
    customer_id,
    c.customer_name,
    p.payment_id
FROM orders AS o
JOIN customers AS c
    USING (customer_id)
LEFT JOIN payments AS p
    USING (order_id);
```

Intent:

1. Join `orders` with `customers` on `customer_id`.
2. Join that result with `payments` on `order_id`.
3. Preserve orders without a payment via `LEFT JOIN`.

The `orders`, `customers`, and `payments` tables here are **illustrative schemas** not created in the lab; to run this, create them or adapt to an existing schema.

### 17.1. Shared Columns in Intermediate Results

When chaining multiple `USING` clauses, a column referenced in a later step can come from the **already-merged result of an earlier JOIN**, not solely from a single base table. Avoid reasoning based on `SELECT *` in long JOIN chains.

### 17.2. Chaining Multiple NATURAL JOINs Is Even Harder to Control

If you replace every step with `NATURAL JOIN`, at each step PostgreSQL automatically matches same-named columns between the **current left-hand intermediate result** and the right-hand relation. Accidental shared names like `status` or `created_at` can appear across multiple levels.

That is why chaining `NATURAL JOIN`s in an evolving system is notoriously hard to maintain: developers must keep track of **every column name** across all tables and intermediate results, even as schemas change later.

## 18. Cardinality: Why Can a JOIN Increase Row Counts?

A JOIN does not automatically guarantee "one row per member" if the right-hand relation has multiple rows for the same key.

In the sample dataset, `teams.team_id` is a PRIMARY KEY, so each `member.team_id` matches at most one team. That keeps an INNER JOIN by `team_id` from duplicating a member.

Now consider the one-to-many direction:

```text
team_id = 10
  -> An
  -> Bình

team_id = 20
  -> Chi
  -> Giang
```

A query starting from `teams` JOIN `members` returns **one row per member**, not one row per team.

### 18.1. Counting Members per Team

```sql
SELECT
    t.team_id,
    t.team_name,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id, t.team_name
ORDER BY t.team_id;
```

Result:

| team_id | team_name | member_count |
| ---: | --- | ---: |
| 10 | Core | 2 |
| 20 | Analytics | 2 |
| 30 | Archive | 2 |
| 40 | Support | 0 |

`COUNT(m.member_id)` is 0 for Support because no member matches; `m.member_id` on the LEFT JOIN null-extended row is NULL.

### 18.2. Why Can `COUNT(*)` Be Wrong in a LEFT JOIN?

```sql
SELECT
    t.team_id,
    COUNT(*) AS row_count,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id
ORDER BY t.team_id;
```

For Support, `COUNT(*) = 1` because LEFT JOIN still emits **one row** for an empty team, whereas `COUNT(m.member_id) = 0`.

When writing summary reports, understand **what each joined row represents** rather than applying `COUNT(*)` mechanically.

### 18.3. `DISTINCT` Does Not Fix a Broken JOIN Condition

If a wrong JOIN produces extra row pairs, adding:

```sql
SELECT DISTINCT ...
```

may reduce row count, yet **it does not guarantee fixing the semantics of the pairings**. Especially when summing money, amounts duplicated prior to an outer `DISTINCT` can still be wrong.

Fix the **key condition** or **relational model** first instead of hiding the root cause with `DISTINCT`.

## 19. `USING`, `ON`, and Anti-Join Queries

A common goal: finding teams **with no members yet**.

### 19.1. LEFT JOIN + IS NULL

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    ON m.team_id = t.team_id
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

Result: team `40 - Support`.

The `m.member_id IS NULL` condition identifies rows without members because `m.member_id` is a PRIMARY KEY and cannot be NULL on a real row.

### 19.2. Using `USING`

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

The result is identical to the previous query.

### 19.3. Using `NOT EXISTS`

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM join_lab.members AS m
    WHERE m.team_id = t.team_id
)
ORDER BY t.team_id;
```

This query also finds team 40. `NOT EXISTS` expresses the intent "no related row exists" very clearly.

When anti-join predicates are complex or the right side has nullable columns, you must pick the right column to test `IS NULL` with LEFT JOIN; `NOT EXISTS` avoids several of those pitfalls. Never assume one form is always faster without checking the actual execution plan.

## 20. `ON` with Expressions and Differently Named Keys: Why Not Force `USING`?

`USING` fits only when both sides share **same-named columns** and the condition is **equality**. Many problems require `ON`.

### 20.1. Different Key Names

```sql
-- Illustrative schema example:
SELECT
    o.order_id,
    c.display_name
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.id;
```

`USING (customer_id)` will fail if `customers` only has `id`.

### 20.2. Joining on Time Ranges

Suppose a table stores effective date ranges of policies:

```sql
-- Illustrative external schema, not part of the lab setup:
SELECT
    e.event_id,
    p.policy_name
FROM events AS e
JOIN policies AS p
    ON e.occurred_at >= p.valid_from
   AND e.occurred_at <  p.valid_to;
```

The join condition is a half-open interval, not equality on a same-named column; `ON` is the proper construct.

If effective periods overlap, one event can match multiple policies, producing multiple rows. Validate data integrity, not just JOIN syntax.

### 20.3. Joining on Expressions

In some legacy systems, key values are stored as text and require casting. You may encounter:

```sql
-- Illustrative idea only: ensure valid data before casting.
ON a.raw_id::bigint = b.id
```

`USING` does not allow arbitrary cast expressions inside the column list. Note that casting raw data can raise errors or impede index usage; standardizing storage types or normalizing ahead of time is better when possible.

### 20.4. Avoid Writing an "Always True" Condition Just to Force a Join

```sql
ON TRUE
```

produces Cartesian-like behavior (depending on the join type) and is appropriate only when specifically required. If you want every combination, `CROSS JOIN` makes the intent clearer.

## 21. JOINs with the Same Intent but Different Column Lists

To summarize, compare:

### 21.1. `ON`

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

- Rows match on `team_id`.
- `SELECT *` emits **two `team_id` columns** and two `status` columns.
- Each side's team ID remains separate in the output.

### 21.2. `USING`

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

- Rows match on `team_id`.
- `SELECT *` emits **one `team_id` column**.
- `status` still appears twice because it is not in `USING`.

### 21.3. `NATURAL JOIN`

```sql
SELECT *
FROM join_lab.members
NATURAL JOIN join_lab.teams;
```

- Rows match on **both `team_id` and `status`**.
- `SELECT *` merges both shared columns into one output column per name.
- Whenever new shared names appear in the schema, the JOIN condition and output shape can change.

### 21.4. Summary Comparison Table

| Criterion | `ON` | `USING` | `NATURAL JOIN` |
| --- | --- | --- | --- |
| Who chooses join columns/expressions? | Developer | Developer picks column names | PostgreSQL auto-discovers shared names |
| Supports differently named keys? | Yes | No | No control list |
| Supports operators other than `=`? | Yes | No | No |
| Automatically adds same-named columns to condition? | No | No | **Yes** |
| `SELECT *` merges key column? | No | Yes, per USING list | Yes, for all shared columns |
| Does JOIN silently change meaning when a shared column is added? | Condition stays unchanged | List stays unchanged | **Possibly** |
| Compatible with all OUTER JOIN types? | Yes | Yes | Yes |
| Suitable for long-lived production code? | **Highly suitable** | Suitable when controlled | **Avoid** |

## 22. Performance: Do `ON` and `USING` Differ in Speed?

When two expressions have the exact same semantics:

```sql
JOIN teams AS t
    ON m.team_id = t.team_id
```

and:

```sql
JOIN teams AS t
    USING (team_id)
```

PostgreSQL typically optimizes them to the **same equijoin condition**. Do not choose `USING` assuming it runs faster than `ON`.

What truly drives performance:

- Do join keys and **data types** match cleanly?
- Are suitable indexes present?
- Are row-count and key-distribution statistics accurate?
- How many rows does the JOIN produce?
- Does PostgreSQL pick `Nested Loop`, `Hash Join`, or `Merge Join`?
- Do filter predicates shrink data before or during the JOIN?
- Are casts or functions applied to keys, blocking index usage?

### 22.1. Indexes on Primary and Foreign Keys

In the example:

```sql
CREATE TABLE join_lab.teams (
    team_id bigint PRIMARY KEY,
    ...
);
```

`PRIMARY KEY` automatically creates an appropriate index on `teams.team_id`.

However, the constraint:

```sql
team_id bigint REFERENCES join_lab.teams(team_id)
```

**does not automatically create an index on `members.team_id`** just because it is a foreign key. For large tables frequently joined or filtered by team ID, consider:

```sql
CREATE INDEX idx_members_team_id
ON join_lab.members (team_id);
```

Indexes add storage and write-maintenance overhead; evaluate based on workload. On tiny sample tables, the query planner will rightly choose a sequential scan.

### 22.2. Inspecting Plans with `EXPLAIN`

```sql
EXPLAIN
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

The plan may show nodes such as:

- `Hash Join`: builds a hash table on one side and probes from the other.
- `Merge Join`: joins two streams sorted by the join key.
- `Nested Loop`: iterates over rows from one side and looks up matching rows on the other, potentially using an index.

The same query written with `USING (team_id)` will likely produce a very similar or identical plan when the conditions are equivalent. There is no guarantee the planner always picks the exact same plan under all circumstances, as statistics, other `SELECT` clauses, and configuration also matter.

### 22.3. Do Not Run `EXPLAIN ANALYZE` Recklessly on Write Queries

`EXPLAIN (ANALYZE, BUFFERS)` **executes the SQL statement** to measure it. When paired with `UPDATE`, `DELETE`, or side-effecting statements, it modifies data. Read-only `SELECT` examples are easy to test here, yet in production you must still consider query load, permissions, and data sensitivity.

### 22.4. A Broken Join Can Look "Faster" Because It Drops Data

`NATURAL JOIN` in our sample returns fewer rows than `JOIN ... ON team_id`. If you time it and see it finish faster, that does not prove the syntax is better: it is **evaluating a different condition** and dropping valid rows.

**Performance comparisons are meaningful only when both queries are semantically equivalent and satisfy the same business requirements.**

## 23. Writing Maintainable SQL and Avoiding Schema Drift Risk

### 23.1. Use Short, Meaningful Aliases

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

Aliases `m` and `t` keep the `ON` expression concise while clearly identifying which table each column belongs to.

### 23.2. Do Not Use `SELECT *` as an API Contract

An API layer reading JOIN output and serializing to JSON can break when a table adds a colliding column or `USING` merges a column. List columns explicitly with clear aliases:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.status AS member_status,
    t.team_id,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

With `LEFT JOIN`, team columns for unassigned members can be NULL; applications must interpret that as "no matching row," not a team with an empty name.

### 23.3. Choose Key Columns from the Relational Model

Never scan for matching column names and join by guesswork. Inspect:

- Primary key of the target table.
- Foreign key from the source table.
- Which columns make up composite keys.
- Whether the relationship is one-to-many, many-to-many, or one-to-one.
- Whether tenant/context keys or effective timestamps must be included.

In the sample tables, `members.team_id` → `teams.team_id` is the real relationship. `members.status` is not a foreign key to `teams.status`, so it does not belong in the default join condition.

### 23.4. Designing Migrations and Reviewing JOINs

During SQL code review, ask for every JOIN:

1. Does the join condition include all key components?
2. Which columns can be NULL?
3. What is the expected row count?
4. Can either table have multiple rows per key?
5. For OUTER JOINs, is condition placement in `ON` or `WHERE` intentional?
6. Is `NATURAL` or `SELECT *` used, risking silent changes on schema updates?
7. Do same-named columns truly share the same meaning?

If you cannot answer these questions, the JOIN is likely underspecified.

## 24. Common JOIN Mistakes

| Scenario | Symptom | Root Cause | Remedy |
| --- | --- | --- | --- |
| `NATURAL JOIN` on tables sharing `status` | Missing rows | Implicitly joins on `status` too | Use `ON`/`USING` listing exact keys |
| Adding a same-named column in migration | Old query returns different results | NATURAL silently changes join condition | Avoid NATURAL in durable code |
| No shared columns in NATURAL | Huge row explosion | Implicit Cartesian product | Specify `ON`/`USING` or explicit CROSS JOIN |
| `SELECT *` with ON | Duplicate ID columns | ON does not merge output | Explicitly SELECT columns with aliases |
| `SELECT *` with USING | One key column instead of two | USING merges keys | Understand output contract |
| `SELECT status` after USING(team_id) | Ambiguous column error | Both tables still have `status` | Select `m.status` and `t.status` |
| `USING (status)` as wrong key | Wrong row pairings | Shared name is not a relation | Use the real foreign key |
| JOIN drops teamless Phúc | Missing row 106 | INNER JOIN drops unmatched rows | Use LEFT JOIN if all members are needed |
| LEFT JOIN with WHERE on right column | Unmatched rows vanish | WHERE filters out NULL | Put filter in `ON` to preserve left side |
| FULL JOIN selecting key from one side only | Key missing on one-sided rows | Two separate key columns | Use `USING` or `COALESCE` across both sides |
| JOIN missing `tenant_id` | Pairs invoices across tenants | Incomplete composite key | Join on both columns in `ON` or `USING` |
| JOIN returns more rows than expected | Counts and sums inflated | One-to-many or non-unique key | Check cardinality, keys, and aggregations |
| `COUNT(*)` in LEFT JOIN on empty team = 1 | Wrong count | Null-extended row is still a row | Use `COUNT(right.pk)` |
| Two NULL keys fail to match | Expected pairs missing | `NULL = NULL` is UNKNOWN | Verify business rules; use null-safe ON only when valid |
| Index created, yet plan still Seq Scan | Index seems ignored | Table too small, cost model | Test on realistic data, check EXPLAIN |
| Joining on display name | Wrong person paired | Names are not unique keys | Join on ID/foreign key |
| Using `DISTINCT` to hide duplication | Sums can still be wrong | Broken join semantics | Fix the JOIN condition first |

## 25. Practice Exercises with Solutions

Use the `join_lab.members` and `join_lab.teams` tables created earlier. Composite-key exercises also use `join_lab.invoices` and `join_lab.invoice_lines`.

### Exercise 1. Join Members with Team Names Using `ON`

Write a query retrieving `member_id`, `member_name`, and `team_name` for members who belong to a team.

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

**Answer:** `101, 102, 103, 104, 105, 107`. Phúc (106) has no team yet and does not match the INNER JOIN.

### Exercise 2. Rewrite Using `USING`

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

**Answer:** the same six members as Exercise 1 because both join on `team_id`.

### Exercise 3. Why Does `NATURAL JOIN` Return Only Four Members?

```sql
SELECT
    member_id,
    member_name,
    team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams
ORDER BY member_id;
```

**Answer:** because both tables share `team_id` and `status`. `NATURAL JOIN` requires both values to match, excluding Bình (102) and Dung (104). Result: `101, 103, 105, 107`.

### Exercise 4. Explicitly Write Both Conditions Using `ON`

Write the join expression equivalent to `NATURAL JOIN` on the current schema.

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND m.status = t.status
ORDER BY m.member_id;
```

**Answer:** also returns `101, 103, 105, 107`. That does not mean this extra condition is business-correct.

### Exercise 5. How Many `team_id` Columns Appear in `SELECT *`?

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Answer:** the first query has **two `team_id` columns** in the output, while the second has **one `team_id` column**. Both tables still emit separate `status` columns; `USING(team_id)` does not merge them.

### Exercise 6. Resolving Ambiguous `status` Column

What is wrong with this query?

```sql
SELECT status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Answer:** `status` exists in both tables and is not in the `USING` list, so an unqualified reference is ambiguous. Fix with `m.status AS member_status` and `t.status AS team_status`.

### Exercise 7. Retrieve All Members Including Unassigned Ones

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

**Answer:** all seven members. Phúc has `team_name = NULL`.

### Exercise 8. Keep All Members, Show Only ACTIVE Teams If Any

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

**Answer:** still seven member rows; Dung and Em's team fails to match because Archive is INACTIVE, leaving `team_name` as NULL; Phúc also has no team.

### Exercise 9. Find Teams Without Members

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

**Answer:** team Support, ID 40.

### Exercise 10. Count Members in Each Team, Including Empty Teams

```sql
SELECT
    t.team_id,
    t.team_name,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id, t.team_name
ORDER BY t.team_id;
```

**Answer:** Core 2, Analytics 2, Archive 2, Support 0. Use `COUNT(m.member_id)` instead of `COUNT(*)` so empty teams yield 0.

### Exercise 11. Multi-Tenant Invoice Join with a Composite Key

```sql
SELECT
    tenant_id,
    invoice_id,
    l.line_no,
    l.quantity
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    USING (tenant_id, invoice_id)
ORDER BY tenant_id, invoice_id, l.line_no;
```

**Answer:** three rows, with no cross-tenant invoice pairings. Joining only on `invoice_id` causes ID 500 in tenants 1 and 2 to multiply erroneously.

### Exercise 12. `NATURAL JOIN` with No Shared Columns

Two tables have 4 and 5 rows and share no column names. How many rows will `NATURAL JOIN` return?

**Answer:** `4 × 5 = 20`, because an empty inferred condition produces a Cartesian product identical to CROSS JOIN.

### Exercise 13. Adding `status` to Two Tables That Previously Shared Only `id`

What happens to an existing `NATURAL JOIN` query?

**Answer:** PostgreSQL starts comparing both `id` and `status`. Pairs with the same ID but different statuses may vanish. The query continues running without error, making the bug hard to notice.

### Exercise 14. Do Two NULL Keys Match Under `USING`?

```sql
WITH
a(k) AS (VALUES (NULL::integer)),
b(k) AS (VALUES (NULL::integer))
SELECT *
FROM a JOIN b USING (k);
```

**Answer:** zero rows. `NULL = NULL` is UNKNOWN, not TRUE.

### Exercise 15. How to Make NULL Match NULL?

```sql
WITH
a(k) AS (VALUES (NULL::integer)),
b(k) AS (VALUES (NULL::integer))
SELECT a.k, b.k
FROM a
JOIN b
    ON a.k IS NOT DISTINCT FROM b.k;
```

**Answer:** the query produces one NULL–NULL pair. Apply this only when the business genuinely treats two NULLs as equivalent keys.

### Exercise 16. Why Can NATURAL LEFT JOIN Return All Members Yet Miss Team Names?

**Answer:** the outer join preserves left-side rows, yet NATURAL silently joins on additional same-named columns like `status`. When statuses differ, the team side fails to match and becomes NULL.

### Exercise 17. How Does `FULL JOIN ... USING` Merge Keys?

```sql
WITH
a(k, v) AS (VALUES (1, 'A1'), (2, 'A2')),
b(k, w) AS (VALUES (2, 'B2'), (3, 'B3'))
SELECT k, v, w
FROM a FULL JOIN b USING (k)
ORDER BY k;
```

**Answer:** the result contains keys 1, 2, and 3; key 1 has only `v`, key 3 has only `w`, and key 2 has both. Column `k` is the merged key, equivalent to `COALESCE(a.k,b.k)` in this case.

### Exercise 18. Put the ACTIVE Team Filter in `WHERE` or `ON` for LEFT JOIN?

Requirement: "all members, but only attach ACTIVE team details."

**Answer:** put `t.status = 'ACTIVE'` **in `ON`**. Putting it in `WHERE` drops unassigned members and members of INACTIVE teams.

### Exercise 19. Is `JOIN ... USING` Faster Than `JOIN ... ON`?

**Answer:** when expressing the same equijoin condition, PostgreSQL optimizes them equivalently. Speed depends on indexes, data, statistics, row counts, and execution plans; shorter syntax is not inherently faster.

### Exercise 20. "column reference is ambiguous" Error After JOIN

```sql
SELECT team_id, status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Answer:** `team_id` is merged by USING, whereas `status` still exists on both sides. Fix:

```sql
SELECT
    team_id,
    m.status AS member_status,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

### Exercise 21. Spotting a Row-Multiplying JOIN Bug

An invoice table has two tenants both using ID 500. A query joins lines with invoices on `invoice_id` alone, causing a line item to appear twice.

**Answer:** the condition is missing `tenant_id`. Write `ON l.tenant_id = i.tenant_id AND l.invoice_id = i.invoice_id` or `USING (tenant_id, invoice_id)`.

### Exercise 22. Should You Use `SELECT DISTINCT` to Fix a NATURAL JOIN Missing Rows?

**Answer:** no. `DISTINCT` removes duplicate rows from a result; it cannot restore rows dropped by `NATURAL JOIN` due to an overly strict implicit condition. You must rewrite the JOIN condition.

## 26. SQL JOIN Review Checklist

Before accepting a JOIN query into an application, verify:

| Question | Why Check? |
| --- | --- |
| Which key links the two tables? | Never infer business relationships from matching column names |
| Is the key single-column or composite? | Avoid JOINs missing tenant/composite key parts |
| Do column names match on both sides? | Decide between `USING` and `ON` |
| Is `NATURAL JOIN` used? | Risk of silently adding/dropping predicates on schema changes |
| Are there non-key columns with the same name? | Especially `status`, `type`, `created_at` |
| Can the key be NULL? | `=` does not match two NULLs |
| Which side's unmatched rows must be kept? | Pick the right INNER/LEFT/RIGHT/FULL JOIN |
| Where is the right-side filter placed in an outer join? | `WHERE` can erase null-extended rows |
| How many rows on the other side match each key? | Predict cardinality, avoid fan-out multiplication |
| Could `SELECT *` duplicate or merge columns? | Keep API/serialization contracts stable |
| Does FULL JOIN require seeing each side's key? | `ON` + aliases can be clearer than USING |
| Are needed foreign key indexes present? | FKs do not auto-index the referencing side |
| Has the query been tested on realistic volume? | Inspect EXPLAIN and actual timings |
| Might migrations add same-named columns? | Prevent schema drift, especially with NATURAL |
| Was output verified against edge cases? | Test unmatched rows, NULLs, duplicate keys, differing statuses |

A solid JOIN query not only returns accurate data on current sample rows, it also maintains **clear semantics and stability as data grows, business rules evolve, and schemas change**.

## 27. Summary

PostgreSQL offers three common ways to express join conditions:

1. **`JOIN ... ON`** is the most complete and explicit approach. It supports differently named keys, multi-column predicates, complex expressions, and non-equality comparisons. Under `SELECT *`, columns from both sides are preserved even when names collide.
2. **`JOIN ... USING (col1, col2)`** is concise when key names match. It joins strictly on the **listed columns** and merges each shared key column into a single output column in `SELECT *`.
3. **`NATURAL JOIN`** automatically uses **all** same-named columns as join conditions, including business-unrelated ones. This can silently alter results whenever tables add, rename, or drop columns.
4. **NATURAL with zero shared columns becomes a Cartesian product**, causing unexpected row explosions.
5. **NATURAL with multiple shared columns can over-filter**: an incidental `status` match is enough to drop valid rows or turn right-side data into NULL in a `NATURAL LEFT JOIN`.
6. **`ON` and `USING` can match the same rows yet produce different output column structures**. Always list `SELECT` columns and aliases explicitly in application code.
7. **With outer joins, `ON` and `WHERE` are not freely interchangeable**: a `WHERE` predicate on the right table can discard rows that `LEFT JOIN` was meant to keep.
8. **Composite keys must be joined on all key components**, especially when `tenant_id` is paired with a tenant-scoped ID. Never patch duplicated results with `DISTINCT` when the join key condition is incomplete.
9. **`NULL = NULL` is not TRUE**, so `USING` and NATURAL never match two NULL keys; use null-safe conditions in `ON` only when explicitly justified by business logic.
10. **Performance comes from proper keys, indexes, and execution plans**, not from picking the shortest syntax.

**Rule of thumb:** if a relationship condition needs to be understood and maintained for years, **write it explicitly with `ON`**; if two tables share exact key names and you want concise output, **use `USING`**; **avoid `NATURAL JOIN`** because matching column names are not a contract for business relationships.
