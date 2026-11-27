# GIN Indexes, Expression Indexes, and Operator Classes for jsonb in PostgreSQL

A `jsonb` column can store highly flexible documents: user attributes, tags, permission sets, product lists, monetary amounts, status flags, and nested objects. That flexibility makes a query such as:

```sql
SELECT event_id
FROM audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

hard to serve efficiently if PostgreSQL must read and parse every JSON document across millions of records. A **GIN index** helps locate rows containing the target keys/values without scanning every document. However, no single JSON index optimizes every query pattern:

```sql
-- Containment: find documents containing a path/value pair
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb

-- Key existence: does the key appear at the top level?
WHERE payload ? 'actor'

-- Array membership: tag "urgent" inside a nested array
WHERE payload -> 'labels' ? 'urgent'

-- Equality on extracted text value
WHERE payload #>> '{actor,id}' = '42'

-- Numeric range
WHERE (payload ->> 'amount')::numeric >= 100
```

These predicates have **different operators, result types, and expression structures**. `GIN (payload)`, `GIN (payload jsonb_path_ops)`, `GIN ((payload->'labels'))`, and `B-tree ((payload#>>'{actor,id}'))` each cover different scopes.

This lesson belongs to the **JSON and Arrays** chapter in the *Database Engine Relational PostgreSQL* module and dives into:

- GIN (*Generalized Inverted Index*) on `jsonb`.
- Two key operator classes: **`jsonb_ops`** (default) and **`jsonb_path_ops`**.
- Operators `@>`, `?`, `?|`, `?&`, `@?`, `@@`, plus limits with `=`, `->`, and `->>`.
- **Expression indexes** for nested attributes/arrays and text/numeric comparisons.
- Combining GIN with B-tree, partial indexes, tenant predicates, sorting, and pagination.
- Reading `EXPLAIN`, evaluating statistics, GIN update costs, pending list behavior, and operating indexes on large tables.
- Designing type-safe JSONB, handling `NULL`, SQL/JDBC parameterization, and practice exercises.

> **Safety scope:** examples use a dedicated schema `jsonb_index_lab` in a practice database and do not touch business tables. `EXPLAIN (ANALYZE)` actually executes statements; examples with `ANALYZE` here use ordinary `SELECT`s only. Never run `EXPLAIN ANALYZE DELETE/UPDATE` on production just to "preview" a plan.

---

## 1. JSON, JSONB, and Why Inverted Indexes Are Needed

### 1.1. JSONB Stores Documents Parsed into Binary Format

PostgreSQL offers two common JSON data types:

| Type | Notable Aspect |
|---|---|
| `json` | Preserves raw input JSON text, including specific formatting details |
| `jsonb` | Stores parsed binary representation, supporting more operators and indexes |

`jsonb` does not retain all original text details such as key ordering or duplicate keys. In applications that query JSON structures regularly, `jsonb` is usually a better fit than `json`.

Even so, simply using `jsonb` **does not automatically index the attributes inside it**.

### 1.2. Example JSON Document

```json
{
  "actor": {
    "id": "42",
    "team": "risk"
  },
  "labels": ["urgent", "review"],
  "severity": "high",
  "amount": 150.50,
  "flags": {
    "approved": false
  }
}
```

A query `WHERE payload @> '{"severity":"high"}'` must find rows matching that structure. Without a matching access path, PostgreSQL may have to read many rows and inspect their documents.

### 1.3. GIN Inverts "Row → Values" into "Value → Rows"

Conceptual view of an inverted index:

```text
Source documents:

  row #11 -> actor.id=42, labels=[urgent, review]
  row #12 -> actor.id=18, labels=[normal]
  row #13 -> actor.id=42, labels=[review]

GIN (conceptual):

  entry for actor/id/42 ----> row #11, row #13
  entry for label urgent ---> row #11
  entry for label review ---> row #11, row #13
```

This is a **mental model**, not an exact byte-level description of how each operator class encodes keys and values. Specifically, `jsonb_ops` and `jsonb_path_ops` emit different index entries.

### 1.4. Do Not Confuse GIN with B-tree

- **B-tree** organizes keys in order for equality, ranges, and `ORDER BY` support.
- **GIN** stores multiple index entries pointing to the same row, ideal for querying **components inside composite values** such as JSONB, SQL arrays, or full-text.
- A `jsonb` GIN index **does not** inherently return rows ordered by `created_at DESC` like a B-tree on `created_at`.

When an API both filters on JSON and sorts by timestamp, you may need to pair GIN with a B-tree, a bitmap/sort plan, or an alternative query design.

---

## 2. Six JSONB Operator Groups to Distinguish

### 2.1. Containment with @>

```sql
SELECT '{"actor":{"id":"42","team":"risk"},"severity":"high"}'::jsonb
       @> '{"actor":{"id":"42"}}'::jsonb
       AS contains_actor_id;
```

The result is `true`. `@>` asks **whether the left-hand document contains the right-hand structure/value under JSONB containment semantics**.

Example:

```sql
SELECT '["urgent","review"]'::jsonb
       @> '["urgent"]'::jsonb AS contains_urgent;
```

The left-hand array contains the required value, so the result is `true`.

### 2.2. Key Existence with ?

```sql
SELECT '{"actor":{"id":"42"}}'::jsonb ? 'actor'
       AS has_actor;

SELECT '{"actor":{"id":"42"}}'::jsonb ? 'id'
       AS has_top_level_id;
```

Results:

```text
has_actor        = true
has_top_level_id = false
```

**`?` inspects only the top level of the JSONB value being tested**, without recursing into nested objects. If the left side is a JSONB array of strings, `?` also checks for string elements at that array level.

### 2.3. Any-Key Existence with ?|

```sql
SELECT '{"severity":"high","labels":[]}'::jsonb
       ?| ARRAY['severity', 'priority']
       AS has_any_key;
```

`?|` returns `true` if **at least one** string in the SQL `text[]` array is found at the JSONB level tested.

### 2.4. All-Keys Existence with ?&

```sql
SELECT '{"severity":"high","labels":[]}'::jsonb
       ?& ARRAY['severity', 'labels']
       AS has_all_keys;
```

`?&` returns `true` when **all** supplied strings exist at the tested level.

### 2.5. JSONPath Existence with @?

```sql
SELECT '{"actor":{"id":"42"}}'::jsonb
       @? '$.actor.id ? (@ == "42")'
       AS path_has_id_42;
```

`@?` checks whether the JSONPath returns at least one matching item. PostgreSQL has supported JSONPath since version 12; path expressions, `strict`/`lax` modes, and optimization rules follow specific semantics.

### 2.6. JSONPath Predicate with @@

```sql
SELECT '{"amount":150.5}'::jsonb
       @@ '$.amount > 100'
       AS amount_above_100;
```

`@@` evaluates a **JSONPath predicate**. Do not treat `@?` and `@@` as interchangeable names for the same syntax: their return types and JSONPath expressions differ.

### 2.7. Summary Table

| Operator | Primary Meaning | Example |
|---|---|---|
| `@>` | Left JSONB contains right JSONB | `payload @> '{"severity":"high"}'::jsonb` |
| `?` | Top-level key/string exists | `payload ? 'actor'` |
| `?|` | At least one key/string in array exists | `payload ?| ARRAY['actor','labels']` |
| `?&` | All keys/strings in array exist | `payload ?& ARRAY['actor','labels']` |
| `@?` | JSONPath yields matching item(s) | `payload @? '$.labels[*] ? (@ == "urgent")'` |
| `@@` | JSONPath predicate check | `payload @@ '$.amount > 100'` |

**Important:** whether an operator can use an index depends on **the operator class, the left-hand expression, and the specific JSONPath form**, not merely on the column being typed as `jsonb`.

---

## 3. Standalone Practice Lab: audit_events

### 3.1. Verify Environment

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

You need privileges to create schemas, tables, and indexes in a test database. If `jsonb_index_lab` already belongs to another lab session, do not drop it; use a separate database.

### 3.2. Create the Table

```sql
CREATE SCHEMA jsonb_index_lab;

CREATE TABLE jsonb_index_lab.audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('security', 'billing', 'activity')),
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

`payload` is constrained to be a JSON **object** so queries have consistent top-level semantics. The `CHECK` only verifies top-level object type; it does **not** guarantee `actor.id`, `labels`, or `amount` exist with the right types.

### 3.3. Insert Easily Observable Sample Events

```sql
INSERT INTO jsonb_index_lab.audit_events
    (tenant_id, event_type, created_at, payload)
VALUES
(
    3,
    'security',
    TIMESTAMPTZ '2026-11-01 08:00:00+00',
    '{
      "actor":{"id":"42","team":"risk"},
      "labels":["urgent","review"],
      "severity":"high",
      "amount":150.50,
      "flags":{"approved":false}
    }'::jsonb
),
(
    3,
    'activity',
    TIMESTAMPTZ '2026-11-01 09:00:00+00',
    '{
      "actor":{"id":"42","team":"support"},
      "labels":["routine"],
      "severity":"normal",
      "amount":20,
      "flags":{"approved":true}
    }'::jsonb
),
(
    9,
    'billing',
    TIMESTAMPTZ '2026-11-01 10:00:00+00',
    '{
      "actor":{"id":"18","team":"billing"},
      "labels":["review"],
      "severity":"normal",
      "amount":250,
      "flags":{"approved":null}
    }'::jsonb
);
```

These small documents illustrate semantics. To give the planner realistic incentive to choose indexes, we load more rows next.

### 3.4. Insert 60,000 Rows with Distributed States

```sql
INSERT INTO jsonb_index_lab.audit_events
    (tenant_id, event_type, created_at, payload)
SELECT
    1 + (g % 12) AS tenant_id,
    CASE
        WHEN g % 10 = 0 THEN 'security'
        WHEN g % 10 < 4 THEN 'billing'
        ELSE 'activity'
    END AS event_type,
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    jsonb_build_object(
        'actor', jsonb_build_object(
            'id', (g % 500)::text,
            'team', CASE
                WHEN g % 5 = 0 THEN 'risk'
                WHEN g % 5 = 1 THEN 'support'
                ELSE 'operations'
            END
        ),
        'labels', CASE
            WHEN g % 20 = 0 THEN
                jsonb_build_array('urgent', 'review')
            WHEN g % 5 = 0 THEN
                jsonb_build_array('review')
            ELSE
                jsonb_build_array('routine')
        END,
        'severity', CASE
            WHEN g % 15 = 0 THEN 'high'
            ELSE 'normal'
        END,
        'amount', (g % 1000)::numeric / 10,
        'flags', jsonb_build_object(
            'approved', (g % 2 = 0)
        )
    ) AS payload
FROM generate_series(1, 60000) AS gs(g);
```

In the seeded rows:

- Roughly 10% have `event_type = 'security'`.
- Roughly 5% have the `urgent` label.
- `actor.id` values span strings `'0'` through `'499'`.
- `amount` is stored as a JSON **number**, not a JSON string.

The three manually inserted rows make simple queries easy to observe; they also shift totals slightly beyond 60,000.

**Run the seed once.** Running it again adds another 60,000 rows, altering counts and plans. Never drop a schema in a shared database just for a "quick reset."

### 3.5. Update Statistics and Verify

```sql
ANALYZE jsonb_index_lab.audit_events;

SELECT COUNT(*) AS total_rows
FROM jsonb_index_lab.audit_events;

SELECT event_type, COUNT(*) AS n
FROM jsonb_index_lab.audit_events
GROUP BY event_type
ORDER BY event_type;
```

If each `INSERT` ran once, the total row count is **60,003**.

---

## 4. Full-Column GIN Index: Default jsonb_ops

### 4.1. Syntax

```sql
CREATE INDEX audit_events_payload_ops_idx
ON jsonb_index_lab.audit_events
USING GIN (payload);
```

For `jsonb`, the default GIN operator class is **`jsonb_ops`**. You can also write it explicitly:

```sql
-- Same opclass intent; do not create a duplicate index in the lab:
-- CREATE INDEX another_ops_idx
-- ON jsonb_index_lab.audit_events
-- USING GIN (payload jsonb_ops);
```

GIN stores index entries for JSONB components according to `jsonb_ops` rules. This lets PostgreSQL narrow down rows that **potentially** satisfy containment or existence operators and recheck as needed.

### 4.2. Containment Query

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"severity":"high"}'::jsonb;
```

PostgreSQL may pick:

```text
Bitmap Heap Scan on audit_events
  Recheck Cond: (payload @> '{"severity":"high"}'::jsonb)
  -> Bitmap Index Scan on audit_events_payload_ops_idx
       Index Cond: (payload @> '{"severity":"high"}'::jsonb)
```

This is an **illustrative plan shape**, not a guaranteed fixed plan. On small tables or unselective predicates, the planner may pick Seq Scan because it is cheaper.

### 4.3. Existence Query

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

`jsonb_ops` supports the `?` operator. In the seeded data nearly every row has `actor`, so **Seq Scan may still be the better choice**. Operator support and selectivity are two separate things.

### 4.4. ?| and ?&

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?| ARRAY['severity', 'priority'];

EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?& ARRAY['actor', 'labels'];
```

Both operators are also supported by `jsonb_ops`. If most documents contain those keys, the planner will still choose a sequential scan.

### 4.5. GIN Does Not "Understand" Every Value Operation

Example:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50;
```

This predicate uses a **scalar `NUMERIC` expression**. A full-column `jsonb_ops` GIN index on `payload` is not a B-tree range index over extracted `amount`. To optimize ranges, look to a **B-tree expression index or a typed column**.

---

## 5. jsonb_path_ops: GIN Specialized for Containment and JSONPath

### 5.1. Creating an Index with an Explicit Operator Class

```sql
CREATE INDEX audit_events_payload_path_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops);
```

Unlike the default index, `jsonb_path_ops` hashes **path-and-value** combinations together. In many containment workloads, the resulting index can be smaller and more selective than `jsonb_ops`.

**Never assume it is always faster or smaller**; results depend on data shape, key/value counts, queries, and write patterns.

### 5.2. The Two Operator Classes Emit Different Index Entries

Conceptual sketch:

```text
Document:
  {"actor":{"id":"42","team":"risk"}}

jsonb_ops:
  indexes keys and values via separate entries;
  containment combines multiple matching entries

jsonb_path_ops:
  indexes information tied to the full path to a value,
  e.g., actor -> id -> "42";
  can be more selective for specific nested paths
```

This is not an exact byte-encoding spec; it illustrates the difference in **index entry granularity**.

### 5.3. Containment Queries Remain Supported

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Both `jsonb_ops` and `jsonb_path_ops` support `@>`. If both indexes exist at once, the planner chooses by cost; **do not credit an operator class with every index scan just because you created it**.

### 5.4. jsonb_path_ops Does NOT Support ?

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

`jsonb_path_ops` **does not support** key-existence operators `?`, `?|`, or `?&`. If you want full-column GIN support for key existence, consider `jsonb_ops`.

With only `jsonb_path_ops`, PostgreSQL cannot use it for `?` the way it uses `jsonb_ops`.

### 5.5. JSONPath: Both Operator Classes Can Support It

On versions supporting JSONPath:

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';

EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @@ '$.actor.id == "42"';
```

Both `jsonb_ops` and `jsonb_path_ops` support `@?` and `@@` when indexable search conditions can be extracted. That **does not mean every JSONPath yields a useful index condition**.

### 5.6. Key Comparison Table

| Operator / Feature | GIN `jsonb_ops` | GIN `jsonb_path_ops` |
|---|---|---|
| `@>` containment | Yes | Yes |
| `?` key existence | Yes | **No** |
| `?|` any-key existence | Yes | **No** |
| `?&` all-key existence | Yes | **No** |
| `@?` JSONPath | Yes | Yes |
| `@@` JSONPath predicate | Yes | Yes |
| Index entries for keys/values | Keys and values via separate entries | Path + value entries |
| Specific containment lookups | Well suited | Often more selective / compact |
| Searching value-less objects like `{"a":{}}` | Can match key entries | Can perform poorly due to missing leaf entries |

### 5.7. Empty Structures Are a Special Case

Example:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"metadata":{}}'::jsonb;
```

For an empty object containing no leaf values, `jsonb_path_ops` may **produce no useful index entry** matching that empty structure. Lookups like this can become very expensive, scanning wide index ranges or many rows.

If your workload frequently checks for empty objects, absent leaf values, or structures without leaf values, **do not choose `jsonb_path_ops` just because it looked smaller on a different benchmark**.

### 5.8. Do Not Maintain Both Indexes in Production Without Need

In the lab, we create both to compare them. On large production tables, keeping two GIN indexes on `payload` costs substantial disk, CPU, WAL, and write maintenance.

Decide from **query operator frequency**:

- Heavy `?` / `?|` / `?&`: prefer `jsonb_ops`.
- Primarily `@>` on specific paths/values: evaluate `jsonb_path_ops`.
- Primarily equality/ranges on a few scalar attributes: B-tree expression indexes often outperform full-column GIN.

---

## 6. JSONPath and Limits on Index Condition Extraction

### 6.1. JSONPath Expresses More Than Indexes Can Optimize

JSONPath supports complex expressions, array/object filters, comparisons, and nested traversals. Yet GIN only exploits **conditions that can be extracted into matching index lookups**.

### 6.2. Equality Patterns in JSONPath

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';
```

In cases like this, PostgreSQL can extract a condition of the form:

```text
accessor_chain == constant
```

where `accessor_chain` follows object keys and array steps so GIN can identify candidate rows.

### 6.3. Wildcards Differ Between Operator Classes

During JSONPath condition extraction:

- `jsonb_ops` supports common accessors such as `.key`, `[*]`, `[index]` and handles certain object/recursive wildcards like `.*` and `.**`.
- `jsonb_path_ops` supports `.key` and common array accessors, but is **not** equivalent to `jsonb_ops` across all wildcard forms.

Do not write a broad wildcard JSONPath and assume both opclasses optimize it identically.

### 6.4. Greater-Than Comparisons Differ from Containment Equality

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @@ '$.amount > 80';
```

This is a **numeric range** JSONPath predicate. Do not assume JSONB GIN turns into a numeric B-tree over `amount`; parts of JSONPath that cannot be extracted as GIN keys still have to be evaluated per candidate/row.

For frequent ranges on `amount`, compare against a B-tree expression index.

### 6.5. Do Not Assume a GIN Plan Evaluates Everything Inside the Index

`EXPLAIN` may show:

```text
Bitmap Index Scan ...
Bitmap Heap Scan ...
Recheck Cond: (...)
Filter: (...)
```

GIN usually **narrows candidate rows**; the executor may still evaluate the full predicate on candidates. Measure total work reduced, not merely the presence of an index node name.

---

## 7. Where the Expression Sits Determines Whether GIN Applies

### 7.1. GIN (payload) Supports Operators Applied Directly to payload

```sql
WHERE payload @> '{"labels":["urgent"]}'::jsonb
```

Here `@>` operates on the **`payload` column itself**, matching `GIN (payload)`.

### 7.2. When ? Operates on payload -> 'labels'

```sql
WHERE payload -> 'labels' ? 'urgent'
```

Here `?` operates not on `payload`, but on the **expression `payload -> 'labels'`**. `GIN (payload)` does not automatically index arbitrary expressions extracted from `payload`.

### 7.3. Rewriting as Containment When Semantics Match

When `labels` is a JSON array of strings:

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"labels":["urgent"]}'::jsonb;
```

keeps the operator on **root `payload`** so full-column GIN applies. Only rewrite like this when you have verified **data semantics** match: array containment and JSONB existence behave differently if the field is a scalar or object.

### 7.4. Creating a GIN Expression Index

If queries primarily use:

```sql
WHERE payload -> 'labels' ? 'urgent'
```

you can create:

```sql
CREATE INDEX audit_events_labels_gin_idx
ON jsonb_index_lab.audit_events
USING GIN ((payload -> 'labels'));
```

The indexed expression is **`payload -> 'labels'`**, and the default operator class for the `jsonb` result is `jsonb_ops`.

### 7.5. Verifying the Expression Index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload -> 'labels') ? 'urgent';
```

PostgreSQL can use `audit_events_labels_gin_idx` because `?` is applied to the exact indexed expression. Selectivity and cost still determine whether the planner picks it.

### 7.6. Why Might a GIN Expression Index Be Smaller?

Given a document:

```json
{
  "actor": {"id": "42", "team": "risk"},
  "labels": ["urgent", "review"],
  "severity": "high",
  "flags": {"approved": false}
}
```

A full-column GIN index tracks entries for every component. A GIN expression index on `payload -> 'labels'` indexes only the `labels` JSONB, so it **has a good chance** of being smaller and better tailored to label queries.

Do not treat "smaller" as an invariant law: payload contents, label counts, structure, pending lists, and write history dictate actual size.

### 7.7. Different Expressions Require Different Indexes

```sql
WHERE payload -> 'labels' ? 'urgent'
```

differs from:

```sql
WHERE payload ->> 'labels' = '["urgent", "review"]'
```

`->` returns `jsonb`; `->>` returns `text`. You cannot apply JSONB `?` directly to the text output of `->>`, and comparing serialized JSON text does not match array membership semantics.

---

## 8. B-tree Expression Indexes for Scalar Values Inside JSONB

### 8.1. Extracting actor.id as TEXT

```sql
SELECT
    event_id,
    payload #>> '{actor,id}' AS actor_id_text
FROM jsonb_index_lab.audit_events
WHERE event_id <= 3;
```

`#>>` extracts a value by **path** and returns `text`. When `actor.id` is a string ID by design, a B-tree on that expression serves equality lookups cleanly.

### 8.2. Creating a B-tree Index for actor.id

```sql
CREATE INDEX audit_events_actor_id_btree_idx
ON jsonb_index_lab.audit_events
    ((payload #>> '{actor,id}'));
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE payload #>> '{actor,id}' = '42';
```

The query matches the indexed expression, allowing PostgreSQL to use the B-tree expression index.

### 8.3. Comparing with GIN Containment

These two queries have similar goals when documents follow a strict schema:

```sql
-- Containment, can use whole-document GIN
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb

-- Equality on scalar text, can use B-tree expression
WHERE payload #>> '{actor,id}' = '42'
```

However, **never assume they are always equivalent for all JSON**. A document with `"id":42` (a JSON number) fails containment against `"42"`, whereas `#>>` extracts both as the text `'42'`.

### 8.4. Ranges on amount Require NUMERIC

```sql
CREATE INDEX audit_events_amount_btree_idx
ON jsonb_index_lab.audit_events
    (((payload ->> 'amount')::numeric));
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50
  AND (payload ->> 'amount')::numeric < 80;
```

A B-tree over `NUMERIC` supports **range predicates** and numeric ordering. Full-column JSONB GIN is not built for this access pattern.

### 8.5. Do Not Compare Numbers as Text When Numeric Order Is Needed

```sql
-- Wrong semantics when numeric range is intended:
-- WHERE payload ->> 'amount' >= '80'
```

Text ordering differs from numeric ordering:

```text
Text:    '100' can sort before '80' lexicographically
Numeric: 100 > 80
```

Never sacrifice business semantics just to make an expression index-friendly.

### 8.6. Watch Out for Missing or Invalid amount Values

In the seed, every row has `amount` as a JSON number. A real system might contain:

```json
{"amount":"unknown"}
```

When evaluating `(payload ->> 'amount')::numeric`, PostgreSQL throws an **invalid input syntax for type numeric** error. Creating an expression index evaluates the expression across existing rows and fails if any row cannot cast.

Never cast unvalidated data blindly. Design options include:

- Validating data on write.
- Enforcing explicit constraints/JSON contracts.
- Storing critical scalars in **dedicated typed columns**, leaving JSONB for extensions.
- Cleaning legacy records before creating the expression index.

### 8.7. Do Not Index Every JSON Attribute

A document with 50 fields does not need 50 expression indexes. Every index incurs:

- Expression evaluation cost on writes.
- Index entry storage and WAL volume.
- Maintenance, vacuum, and reindex overhead.
- Loss of HOT updates.
- More plans for the planner to evaluate.

Start from **measured query workloads**, not from the number of keys that could appear in JSON.

---

## 9. What Is an Operator Class and Why Must You Choose the Right One?

### 9.1. An Operator Class Binds an Index Key to a Set of Operators

An index is defined by more than its column and access method. An **operator class** tells the index how to organize keys and which operators it supports:

```sql
CREATE INDEX ...
ON table_name
USING gin (payload jsonb_path_ops);
```

When omitted, PostgreSQL selects the **default opclass** for that data type and access method if one exists.

### 9.2. jsonb_ops Is the Default for jsonb GIN

```sql
USING gin (payload)
```

is equivalent to specifying `jsonb_ops` for `payload jsonb`.

### 9.3. jsonb_path_ops Deliberately Trades Off Operators

```sql
USING gin (payload jsonb_path_ops)
```

serves eligible containment/JSONPath queries well, while omitting key-existence operators `?`, `?|`, and `?&`.

Never pick `jsonb_path_ops` merely because its name contains "path" and assume every `->` / `->>` path query will use it automatically.

### 9.4. Opclass and Expression Are Independent Choices

You can have:

```sql
USING gin (payload jsonb_ops)
```

and:

```sql
USING gin ((payload -> 'labels') jsonb_ops)
```

Both use the same opclass, yet **the indexed keys differ**. A query applying `?` to `payload -> 'labels'` needs the matching expression index; simply sharing the opclass on `payload` is not enough.

### 9.5. Selection Summary

Before creating a GIN index, ask:

1. Which operators does the query use?
2. Is the operator applied to **`payload`** or a sub-expression?
3. Does the operator class support that operator?
4. Are index entries selective on real data?
5. Would a B-tree better serve scalar ranges or sorting?

---

## 10. JSON null, SQL NULL, and Missing Keys

This is one of the most frequent sources of logic errors when querying JSONB.

### 10.1. Three Distinct States

```json
{}
```

```json
{"note":null}
```

```json
{"note":"null"}
```

These three documents are **not identical**:

- The first **lacks** the `note` key.
- The second has key `note` with **JSON null**.
- The third has key `note` holding the string `"null"`.

### 10.2. The ? Operator Only Checks Key Presence

```sql
SELECT
    '{}'::jsonb ? 'note' AS missing_note,
    '{"note":null}'::jsonb ? 'note' AS json_null_note,
    '{"note":"null"}'::jsonb ? 'note' AS text_null_note;
```

Result:

| Case | `? 'note'` |
|---|---|
| Missing key | `false` |
| JSON null | `true` |
| String `"null"` | `true` |

### 10.3. -> and ->> Behave Differently

```sql
SELECT
    '{"note":null}'::jsonb -> 'note' AS jsonb_value,
    '{"note":null}'::jsonb ->> 'note' AS text_value;
```

`->` returns a JSONB value, here **JSON null**. `->>` returns text, and for JSON null its SQL result is **NULL**. Accessing a missing key with either operator also returns SQL NULL.

Therefore:

```sql
WHERE payload ->> 'note' IS NULL
```

does not distinguish **missing** from **JSON null**.

### 10.4. Containment Distinguishes JSON Values

```sql
WHERE payload @> '{"note":null}'::jsonb
```

finds only documents containing `note` with JSON null per containment, distinct from `payload ? 'note'`.

### 10.5. Do Not Use Casts and COALESCE to Mask Data States

```sql
-- Can conflate missing, JSON null, and empty text:
-- WHERE COALESCE(payload ->> 'note', '') = ''
```

When business logic separates missing, JSON null, and empty text, write explicit predicates and schemas. Indexes optimize an **already-correct predicate**; they cannot fix semantic bugs.

---

## 11. JSONB Arrays and SQL Arrays Are Different Types

The "JSON and Arrays" chapter often leads people to confuse:

```sql
'["urgent","review"]'::jsonb
```

and:

```sql
ARRAY['urgent', 'review']::text[]
```

### 11.1. JSONB ? Operator

```sql
SELECT '["urgent","review"]'::jsonb ? 'urgent'
       AS jsonb_has_urgent;
```

### 11.2. SQL Array @> Operator

```sql
SELECT ARRAY['urgent','review']::text[]
       @> ARRAY['urgent']::text[]
       AS sql_array_contains_urgent;
```

The logical outcomes are similar, but **operand types, operator classes, and index definitions differ**.

### 11.3. GIN for Native text[]

Example dedicated table:

```sql
CREATE TABLE jsonb_index_lab.task_labels (
    task_id BIGINT PRIMARY KEY,
    labels TEXT[] NOT NULL
);

INSERT INTO jsonb_index_lab.task_labels
VALUES
    (1, ARRAY['urgent', 'review']),
    (2, ARRAY['routine']),
    (3, ARRAY['review']);

CREATE INDEX task_labels_gin_idx
ON jsonb_index_lab.task_labels
USING GIN (labels);
```

Query:

```sql
SELECT task_id
FROM jsonb_index_lab.task_labels
WHERE labels @> ARRAY['urgent']::text[];
```

This uses GIN for **native arrays** with the native array operator class, **not** `jsonb_ops` or `jsonb_path_ops`.

### 11.4. Choosing JSONB Arrays vs. Native Arrays

| Requirement | Option to Consider |
|---|---|
| Homogeneous list with no complex metadata | `TEXT[]` or a child relational table |
| Flexible document with nested objects/arrays | `JSONB` |
| Many-to-many relations, FKs, complex queries | Normalized relational tables |
| GIN existence/containment inside a JSON document | `JSONB` with the matching opclass |

Do not push clean relational data into JSONB just because GIN sounds fast. Correctness, constraints, query patterns, and update costs matter more.

---

## 12. Multi-Tenancy: Combining JSONB Filters with tenant_id

### 12.1. Real Queries Often Combine Multiple Predicates

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
  AND payload @> '{"severity":"high"}'::jsonb;
```

GIN on `payload` narrows by JSON; B-tree on `tenant_id` narrows by tenant.

### 12.2. Creating a B-tree for Tenant

```sql
CREATE INDEX audit_events_tenant_time_idx
ON jsonb_index_lab.audit_events
    (tenant_id, created_at DESC, event_id DESC);
```

A query fetching the newest events for a tenant:

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

can exploit the B-tree sort order without involving GIN at all.

### 12.3. BitmapAnd Can Combine Multiple Indexes

Hypothetical plan:

```text
Bitmap Heap Scan on audit_events
  Recheck Cond: (...)
  -> BitmapAnd
       -> Bitmap Index Scan on audit_events_payload_ops_idx
       -> Bitmap Index Scan on audit_events_tenant_time_idx
```

The planner **may** combine bitmaps from multiple indexes, though it is not forced to. It might determine that scanning one index and filtering the remaining condition—or doing a Seq Scan—is cheaper.

### 12.4. GIN Does Not Preserve created_at Order

For:

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE tenant_id = 3
  AND payload @> '{"severity":"high"}'::jsonb
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

there are two primary strategies:

1. Use GIN to find matching JSON rows, filter tenant, and sort/top-N.
2. Walk the tenant/time B-tree in newest-first order, filtering JSON until 20 rows match.

Which is faster depends on **how often the JSON predicate matches within that tenant, the `LIMIT` size, and time distribution**. There is no universal rule that "GIN + ORDER BY is always fast."

### 12.5. Avoid Creating One GIN Index per Tenant

An extreme idea:

```sql
-- Overly specialized example; do not create across every tenant:
-- CREATE INDEX audit_events_tenant3_gin_idx
-- ON jsonb_index_lab.audit_events
-- USING gin (payload)
-- WHERE tenant_id = 3;
```

A partial GIN index can help for a few hot workloads, yet creating thousands of per-tenant indexes explodes DDL, disk, WAL, planning overhead, and write costs.

First profile your workload and test whether **shared indexes plus a tenant filter** already perform well.

### 12.6. Indexes Are Not Authorization

Filtering `tenant_id = 3` in SQL scopes queries and aids performance, but indexes do not prevent a role from reading other tenants. Use roles, RLS, and application-level authorization appropriately.

---

## 13. Partial GIN Indexes for Hot Data Subsets

Suppose only ~10% of events have `event_type = 'security'`, and the system frequently searches JSON inside those security events.

### 13.1. Creating a Partial Index

```sql
CREATE INDEX audit_events_security_gin_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops)
WHERE event_type = 'security';
```

Only rows with `event_type = 'security'` are indexed here.

### 13.2. Queries That Imply the Predicate

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb;
```

Because the query includes `event_type = 'security'`, all matching rows live inside the partial index. The planner can choose it when cost-effective.

### 13.3. Queries That Do Not Imply the Predicate

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"severity":"high"}'::jsonb;
```

This query also wants `billing` and `activity` events, so it cannot rely **solely** on the security partial index for the complete result.

### 13.4. Prepared Statements and Generic Plans

```sql
PREPARE find_by_type(TEXT, JSONB) AS
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = $1
  AND payload @> $2;
```

A **generic plan** must remain valid for both `event_type = 'billing'` and `event_type = 'security'`, so it cannot assume `$1` always implies the security partial predicate. A custom plan that sees `$1`'s actual value can choose differently.

Where supported:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE find_by_type(
    'security',
    '{"severity":"high"}'::jsonb
);

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE find_by_type(
    'security',
    '{"severity":"high"}'::jsonb
);

RESET plan_cache_mode;
DEALLOCATE find_by_type;
```

This is an **experiment**, not a recommendation to force custom plans globally. The planner might still choose another GIN index or a Seq Scan even when a partial index is eligible.

### 13.5. Partial Indexes and Operator Classes Are Separate Choices

In the security index:

```sql
USING GIN (payload jsonb_path_ops)
WHERE event_type='security'
```

we made **two independent choices**:

1. `jsonb_path_ops`: which operators and GIN entries are supported.
2. `WHERE event_type='security'`: which rows are included in the index.

Do not conflate "partial GIN" with "`jsonb_path_ops`"; you can build full-table `jsonb_ops`, full-table `jsonb_path_ops`, or partial versions of either.

---

## 14. JSONB Equality, Key Existence, and Differences from B-tree

### 14.1. The = Operator Compares the Whole JSONB Value

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload = '{"actor":{"id":"42"}}'::jsonb;
```

This requires **the entire document to equal the right-hand JSONB** under JSONB semantics. It differs from containment:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

which matches documents that also contain `labels`, `severity`, or other keys.

### 14.2. GIN jsonb_ops Is Not the Default Index for =

`jsonb_ops` targets `@>` and existence/JSONPath operators. Do not expect GIN on `payload` to optimize **every** `payload = ...` comparison the way a whole-document B-tree does.

If whole-document equality is genuinely needed and documents are reasonably sized, PostgreSQL supports **B-tree comparisons on `jsonb`**, though whole-document B-trees on large payloads are rarely the right first choice. Most applications query **specific fields** rather than exact whole-document equality.

### 14.3. Extracting a Scalar Then Comparing

```sql
WHERE payload ->> 'severity' = 'high'
```

matches:

```sql
CREATE INDEX audit_events_severity_btree_idx
ON jsonb_index_lab.audit_events
    ((payload ->> 'severity'));
```

Yet if `severity = 'high'` makes up a large fraction of the table, Seq Scan can still win. Indexable does not mean always chosen.

### 14.4. Eliminating JSON Number vs. String Ambiguity

```sql
SELECT
    '{"amount":42}'::jsonb
      @> '{"amount":42}'::jsonb AS number_match,
    '{"amount":"42"}'::jsonb
      @> '{"amount":42}'::jsonb AS string_vs_number;
```

`number_match` is true; `string_vs_number` is false. Converting everything to text with `->>` erases JSON type distinctions that business logic may depend on.

---

## 15. EXPLAIN: Verifying Whether an Index Is Actually Chosen

### 15.1. Viewing an Estimated Plan

```sql
EXPLAIN
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

`EXPLAIN` only plans the query without executing it to measure actual rows.

### 15.2. Measuring an Actual Plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Components to inspect:

| Component | Meaning |
|---|---|
| `Bitmap Index Scan` | GIN used to gather candidate tuple locations |
| `Bitmap Heap Scan` | Fetches heap pages via bitmap, handles visibility/recheck |
| `Index Cond` | Operator/predicate pushed into the index scan |
| `Recheck Cond` | Condition re-evaluated on candidates as needed |
| `Filter` | Additional predicate filtering fetched rows |
| `Rows Removed by Filter` | Rows discarded at the filter step, when reported |
| `Heap Blocks: exact/lossy` | Indicates bitmap precision |
| `Buffers: shared hit/read` | Shared buffer hits and reads |
| `actual rows` and `loops` | Actual row counts and node invocations |

### 15.3. Recheck Does Not Mean the Index Is Broken

GIN returns candidate tuple IDs based on indexed entries. Complex JSONB predicates often need re-verification of the full condition for correctness.

When a bitmap heap scan uses lossy blocks due to `work_mem` limits, rechecking becomes even more important. This is **normal access-method behavior**, not an index bug.

### 15.4. Seq Scan Can Be the Right Choice

If:

```sql
WHERE payload ? 'actor'
```

matches 99.99% of rows, probing GIN and reading almost every heap page is slower than Seq Scan. The operator is still supported by `jsonb_ops`, yet the optimizer is right to skip the index.

### 15.5. Comparing Estimated vs. Actual Rows

```text
cost=... rows=100 ...
actual time=... rows=10000 loops=1
```

Large row-estimate errors can lead to poor scan or join choices. Check statistics, common JSON values, per-tenant skew, combined predicates, and generic/custom plans before altering indexes.

### 15.6. Measure Before and After with Identical Queries and Data

- Compare the exact same SQL and literals/parameters.
- Ensure index creation finished and statistics are up to date.
- Run multiple times since warm vs. cold caches differ.
- Compare `BUFFERS` and total work done, not just a single execution time.
- Never create an index merely to see a particular node name appear.

---

## 16. GIN Maintenance: Pending List, fastupdate, and VACUUM

### 16.1. GIN Indexes Have Update Costs

A JSON document with many keys/values generates **many entries** in GIN. On `INSERT`, `UPDATE`, or `DELETE`:

- PostgreSQL must update all affected entries.
- Additional WAL and storage are generated.
- Updating a large `payload` can cost noticeably more CPU than updating a few scalar columns.
- Index size and bloat can grow over time.

### 16.2. fastupdate and the Pending List

GIN provides **`fastupdate`** (enabled by default), buffering newly inserted entries into a **pending list** before merging them into the main index tree.

Conceptual flow:

```text
INSERT/UPDATE JSONB
       |
       v
GIN pending list
       |
       | cleanup / merge
       v
GIN main structure
```

This lowers average write cost, though the pending list must eventually be flushed and can cause latency spikes when cleanup triggers.

### 16.3. Configuring fastupdate

Example storage parameter on index creation:

```sql
-- Illustrative only; DO NOT create a duplicate index in the lab:
-- CREATE INDEX example_payload_gin
-- ON jsonb_index_lab.audit_events
-- USING gin (payload)
-- WITH (fastupdate = on);
```

Changing `fastupdate` does not automatically flush existing pending entries. Tuning must balance write speed, read latency, maintenance, and monitoring.

### 16.4. gin_pending_list_limit

PostgreSQL provides a parameter bounding the pending list size before cleanup triggers. Cleanup runs during `VACUUM` or when an insert hits the threshold.

**Do not** tweak `gin_pending_list_limit` globally to "fix slow queries": it trades off write latency, cleanup bursts, index size, and overall I/O.

### 16.5. VACUUM and AUTOVACUUM

GIN operates inside PostgreSQL's MVCC lifecycle. `DELETE` and `UPDATE` create obsolete tuple versions that must be reclaimed once no active snapshot needs them. Autovacuum/VACUUM cleans dead tuples and maintains index structures.

Long-running transactions holding snapshots open delay dead-tuple cleanup. Avoid long-open transactions on tables with heavy JSONB updates.

### 16.6. Inspecting Index Sizes

```sql
SELECT
    c.relname AS index_name,
    pg_size_pretty(pg_relation_size(c.oid))
        AS index_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_index AS i
    ON i.indexrelid = c.oid
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Size reflects index structure, entry count, value variety, pending list, and maintenance history. Never conclude `jsonb_path_ops` is always smaller than `jsonb_ops` across all tables from one demo measurement.

### 16.7. Index Usage Statistics

```sql
SELECT
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'jsonb_index_lab'
ORDER BY relname, indexrelname;
```

Low `idx_scan` does not automatically prove an index is useless: check the observation window and workload, and remember unique indexes enforce integrity even if few `SELECT`s use them.

---

## 17. Deploying GIN Indexes on Large Tables

### 17.1. Standard CREATE INDEX

```sql
CREATE INDEX new_payload_gin_idx
ON jsonb_index_lab.audit_events
USING GIN (payload jsonb_path_ops);
```

This is illustrative syntax; the lab already has a `path_ops` index. Do not create a duplicate just to waste space. On busy write tables, standard `CREATE INDEX` acquires locks that block writers.

### 17.2. CREATE INDEX CONCURRENTLY

An option for online deployment:

```sql
-- Run only when a new index is genuinely needed
-- and no duplicate name/definition exists:
-- CREATE INDEX CONCURRENTLY audit_events_new_path_idx
-- ON jsonb_index_lab.audit_events
-- USING gin (payload jsonb_path_ops);
```

`CONCURRENTLY` avoids blocking concurrent writes while building the index, but:

- It takes longer and uses more resources.
- It must wait for active transactions/snapshots.
- It **cannot run inside an explicit transaction block**.
- If it fails, it leaves an **invalid** index requiring controlled cleanup.
- Progress and system load still need monitoring.

Never interpret "concurrently" as zero locks, zero I/O, or zero cost.

### 17.3. Checking Index Validity

```sql
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c
    ON c.oid = i.indexrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY c.relname;
```

If `indisvalid = false`, the optimizer will not use the index. Diagnose the failure and drop/rebuild safely, especially after an interrupted concurrent index build.

### 17.4. GIN Indexes and Large Columns

GIN is great for containment, yet indexing JSONB documents with thousands of keys/tags across millions of rows incurs heavy cost. If workloads only touch a few fields:

- Consider targeted expression indexes.
- Consider typed relational columns for critical fields.
- Consider partitioning by time or tenant if data lifecycles align.
- Avoid indexing entire JSON documents "just in case" without measured query needs.

---

## 18. Prepared Statements, Parameter Types, and GIN

### 18.1. Bind JSONB with the Proper Type

```sql
PREPARE find_actor(JSONB) AS
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> $1;

EXPLAIN EXECUTE find_actor(
    '{"actor":{"id":"42"}}'::jsonb
);

DEALLOCATE find_actor;
```

Declaring `$1` as `JSONB` keeps `@>` properly typed. PostgreSQL can use GIN when the operator class supports it and costs favor it.

### 18.2. Do Not Cast the Whole JSONB Column to Text

```sql
-- Avoid for searching JSON elements:
-- WHERE payload::text LIKE '%"id":"42"%'
```

This depends on text serialization, cannot use containment GIN properly, and breaks on whitespace, key ordering, escaping, and nested structures.

Proper containment:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

### 18.3. Typed Values vs. JSON Strings

If `actor.id` is a string:

```sql
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb
```

differs from:

```sql
WHERE payload @> '{"actor":{"id":42}}'::jsonb
```

The second searches for a JSON number. Never switch types just because an API accepts `42`; follow the JSON contract consistently.

### 18.4. Generic Plans Do Not Automatically Disable GIN

`payload @> $1` applies `@>` directly to the column with an explicit `jsonb` parameter. A generic plan **can still consider GIN** even without knowing `$1`'s exact value; index selection depends on estimates and cost.

Do not confuse this with a partial index predicate like `event_type = 'security'`: a generic plan for `event_type = $2` cannot assume `$2` will always equal `'security'`.

### 18.5. JDBC with pgJDBC

In Java applications:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import org.postgresql.util.PGobject;

public final class AuditEventRepository {
    public long countByContainment(
            Connection connection, String jsonFilter
    ) throws SQLException {
        String sql = """
            SELECT COUNT(*)
            FROM jsonb_index_lab.audit_events
            WHERE payload @> ?
            """;

        PGobject parameter = new PGobject();
        parameter.setType("jsonb");
        parameter.setValue(jsonFilter);

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setObject(1, parameter);
            try (ResultSet rs = statement.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    }
}
```

This example uses **pgJDBC** and Java text blocks (Java 15+). The application must still validate the JSON filter structure, tenant authorization, and query bounds; parameter binding prevents SQL injection, not overly broad queries.

### 18.6. JDBC Extracting a Scalar

For `actor.id`:

```java
String sql = """
    SELECT event_id
    FROM jsonb_index_lab.audit_events
    WHERE payload #>> '{actor,id}' = ?
    """;

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setString(1, actorId);
    try (ResultSet rs = ps.executeQuery()) {
        // Process returned rows.
    }
}
```

The matching index is a B-tree expression index on `(payload #>> '{actor,id}')`. There is no need to serialize the document to a string and run `LIKE`.

### 18.7. Never Construct Unchecked Dynamic JSONPath

JSONPath has its own syntax. Concatenating user input directly into a path string can alter query semantics or trigger unexpected errors and resource usage.

Prefer fixed paths when data contracts are clear, bind values safely, or use controlled JSONPath variables (`vars`), validating any dynamically built path parts.

---

## 19. GIN, B-tree, BRIN, and Full-Text: No Single Index Solves Everything

| Requirement | Typical Candidate Index | Notes |
|---|---|---|
| JSONB containment `@>` | GIN `jsonb_ops` or `jsonb_path_ops` | Pick by query operators and data distribution |
| Key existence `?`, `?|`, `?&` | GIN `jsonb_ops` | Not supported by `jsonb_path_ops` |
| JSONPath `@?` / `@@` | Matching GIN | Only certain path forms extract index keys |
| Membership in `payload->'labels'` | Expression GIN or whole-column containment | Expression must match query |
| Equality `payload#>>'{actor,id}' = ...` | B-tree expression | Scalar text |
| Range `(payload->>'amount')::numeric >= ...` | B-tree expression or `numeric` column | Data must cast cleanly |
| `ORDER BY created_at DESC LIMIT 20` | B-tree on time/tenant | GIN does not provide this order |
| Full-text prose search | `tsvector` GIN / full-text | Distinct from JSON key containment |
| Substring `ILIKE '%term%'` | Trigram GIN/GiST if appropriate | Requires `pg_trgm` and selectivity checks |
| Huge time-ordered event table | BRIN or partitioning + targeted indexes | Does not replace JSONB GIN |

### 19.1. A Narrow Scalar B-tree Sometimes Beats Full-Column GIN

If 95% of your workload is:

```sql
WHERE payload #>> '{actor,id}' = $1
```

a narrow B-tree expression index can be smaller and cheaper to maintain on writes than a full-document GIN index. Measure first rather than guessing.

### 19.2. GIN Does Not Replace Relational Normalization

If `actor.id` is actually a foreign key to a `users` table, keeping it solely inside JSONB complicates FK constraints, typed joins, and integrity checks.

A hybrid layout is often ideal:

```sql
event_id      BIGINT PRIMARY KEY
tenant_id     INTEGER NOT NULL
actor_id      BIGINT NOT NULL
created_at    TIMESTAMPTZ NOT NULL
payload       JSONB NOT NULL
```

Important fields participating in constraints and joins live in **typed columns**; JSONB holds flexible extensions.

### 19.3. Do Not Use JSONB to Bypass Schema Governance

JSONB supports flexible shapes, yet business rules must still define:

- Which keys are mandatory?
- What are the scalar types?
- Do missing keys and JSON null differ?
- What is the document schema version?
- What size and array length limits apply?
- Which sensitive keys require read/write access control?

Indexes only accelerate access; they do not enforce schemas or security.

---

## 20. Common Mistakes When Optimizing jsonb

**1. "With `jsonb`, PostgreSQL already indexes the keys."** No. You must create matching indexes or use another access path.

**2. "`GIN (payload)` handles every JSON operator."** No. It depends on the opclass and the left-hand expression.

**3. "`jsonb_path_ops` supports `?`."** False. It does not support key-existence operators `?`, `?|`, or `?&`.

**4. "`jsonb_ops` and `jsonb_path_ops` store identical index entries."** False. Entry structure and selectivity differ.

**5. "`jsonb_path_ops` is always smaller and faster."** No. Data and queries determine that; empty structures are a notable weak spot.

**6. "`@>` is the same as `=`."** False. Containment allows extra keys and elements.

**7. "`?` finds keys nested inside any object."** False. It inspects only the top level of the left-hand JSONB expression.

**8. "`payload ? 'id'` finds `id` inside `payload.actor.id`."** No. Apply `?` to the child object, or use containment/JSONPath.

**9. "`payload -> 'labels' ? 'urgent'` definitely uses `GIN(payload)`."** Not by default; the operator sits on an expression.

**10. "`->` and `->>` return the same type."** False. `->` returns `jsonb`; `->>` returns `text`.

**11. "JSONB GIN handles all `NUMERIC` ranges well."** No. A B-tree on a typed scalar is usually much better.

**12. "Comparing `amount` as text preserves numeric order."** False. Text sorting follows lexicographical rules.

**13. "A numeric expression index always builds even if `'unknown'` exists."** No. Invalid casts fail index creation.

**14. "JSON number `42` equals JSON string `'42'`."** No. JSONB preserves type distinctions.

**15. "A missing key is the same as a key with JSON null."** No. Key existence and containment distinguish them.

**16. "`payload->>'note' IS NULL` separates missing from JSON null."** No; both evaluate to SQL NULL.

**17. "GIN returns rows ordered by `created_at DESC`."** No. You need sorting or an appropriate B-tree.

**18. "With two indexes, PostgreSQL always `BitmapAnd`s them."** No. The planner may pick one index or a Seq Scan based on cost.

**19. "If an index supports the operator, the planner must use it."** No. Unselective queries often prefer Seq Scan.

**20. "`Recheck Cond` proves GIN returned wrong results."** No. Recheck is a normal part of bitmap/GIN execution.

**21. "Complex JSONPath expressions always extract index keys."** No. Extraction has strict limits.

**22. "Generic prepared plans can never use GIN."** No. Typed `payload @> $1` can still use GIN.

**23. "The security partial GIN index serves queries for all `event_type`s."** No. Rows outside the partial predicate are absent from it.

**24. "Partial indexes and `path_ops` are the same thing."** No. One filters which rows enter the index; the other chooses the operator class.

**25. "One whole-column GIN index is always smaller than expression indexes."** Not guaranteed; measure sizes and workloads.

**26. "Adding GIN has no impact on `INSERT`/`UPDATE`."** False. GIN maintains many entries and adds WAL, disk, and CPU cost.

**27. "`fastupdate` means cleanup never happens."** False. The pending list must still be merged and vacuumed.

**28. "Raising the pending list limit infinitely optimizes every workload."** No. It trades write speed against cleanup latency bursts and maintenance.

**29. "`CREATE INDEX CONCURRENTLY` runs inside `BEGIN`."** False.

**30. "`CONCURRENTLY` creates zero load or lock waits."** False. It still consumes resources, waits on transactions, and can fail.

**31. "Low index scans prove an index should be dropped immediately."** No. Check the observation window and full workload first.

**32. "JSONB arrays and `TEXT[]` share the `jsonb_ops` operator class."** False. Native arrays have their own operators and opclasses.

**33. "`payload::text LIKE` uses a JSONB GIN index."** No. That is a text expression with different semantics.

**34. "GIN enforces tenant isolation."** No. RLS and database permissions handle security.

**35. "Seq Scan on a 100-row lab table proves the index is useless."** No. The planner optimizes by cost.

**36. "`EXPLAIN ANALYZE` on DML only measures without writing."** False. It executes the statement.

**37. "Expression indexes do not care about function immutability."** False. PostgreSQL requires index expressions to be immutable.

**38. "Moving every scalar column into JSONB makes the database more flexible with zero downsides."** No. You lose typed/FK constraints and increase query and index costs.

---

## 21. Practice Exercises and Solutions

### Exercise 1 — Choosing an Operator for Containment

**Requirement:** find events where `actor.id` is string `"42"`, allowing extra attributes.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"actor":{"id":"42"}}'::jsonb;
```

Can use whole-column GIN `jsonb_ops` or `jsonb_path_ops` if the planner deems it cost-effective.

### Exercise 2 — Top-Level Key Existence

**Requirement:** find events that have key `actor`, without inspecting `actor` contents.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ? 'actor';
```

GIN `jsonb_ops` supports `?`, whereas `jsonb_path_ops` does not.

### Exercise 3 — Nested Keys

**Question:** why does `payload ? 'id'` fail to find `actor.id`?

**Solution:** `?` checks only the top level of `payload`. Use `(payload -> 'actor') ? 'id'`, containment, or JSONPath as appropriate.

### Exercise 4 — Matching At Least One Key

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload ?| ARRAY['severity', 'priority'];
```

**Solution:** returns rows with at least one matching top-level key. Use `jsonb_ops` if GIN support is needed for this existence check.

### Exercise 5 — Matching All Keys

```sql
WHERE payload ?& ARRAY['actor','labels']
```

**Solution:** requires both `actor` and `labels` at the top level; `jsonb_ops` supports this operator.

### Exercise 6 — Can jsonb_path_ops Serve ? Queries?

**Solution:** No. It supports `@>`, `@?`, and `@@` in eligible cases, not `?`, `?|`, or `?&`.

### Exercise 7 — labels Membership via Containment

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @> '{"labels":["urgent"]}'::jsonb;
```

**Solution:** can use full-document GIN because `@>` is applied directly to `payload`.

### Exercise 8 — Membership via ? on an Expression

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload -> 'labels' ? 'urgent';
```

**Question:** which index directly matches this expression?

**Solution:** `GIN ((payload -> 'labels'))` with `jsonb_ops`, because `?` is applied to the extracted array expression.

### Exercise 9 — Creating an Expression GIN Index

```sql
CREATE INDEX exercise_labels_gin_idx
ON jsonb_index_lab.audit_events
USING GIN ((payload -> 'labels'));
```

**Solution:** valid example syntax. The lab already created `audit_events_labels_gin_idx`; avoid keeping near-duplicate indexes unless serving a distinct purpose.

### Exercise 10 — B-tree on actor.id

**Requirement:** find `actor.id` using text equality.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload #>> '{actor,id}' = '42';
```

A B-tree expression index `((payload #>> '{actor,id}'))` is well suited here.

### Exercise 11 — Range on amount

**Requirement:** find `amount` from 50 up to (excluding) 80 numerically.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE (payload ->> 'amount')::numeric >= 50
  AND (payload ->> 'amount')::numeric < 80;
```

Cast directly only when valid numeric data is guaranteed; a B-tree expression index or real `numeric` column fits best.

### Exercise 12 — Risk of Text Comparison

**Question:** is `payload->>'amount' >= '80'` safe when `amount` is numeric?

**Solution:** No. `->>` produces text; comparison uses lexicographical rather than numeric order.

### Exercise 13 — JSON Number vs. String

```sql
SELECT
  '{"id":"42"}'::jsonb @> '{"id":42}'::jsonb AS matched;
```

**Solution:** `false`, because JSON string and JSON number have different types.

### Exercise 14 — Missing Key vs. JSON null

**Question:** is `payload ? 'note'` true for `{"note":null}`?

**Solution:** Yes, because the key is present. For `{}`, it is false.

### Exercise 15 — Why Does path_ops Struggle with Empty Objects?

**Solution:** `jsonb_path_ops` emits entries from path/value pairs; objects containing no leaf values such as `{"a":{}}` lack useful index entries, making containment lookups for them expensive.

### Exercise 16 — JSONPath Equality

**Requirement:** write a JSONPath query finding `actor.id` equal to `"42"`.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE payload @? '$.actor.id ? (@ == "42")';
```

Not every JSONPath is optimized by GIN; check `EXPLAIN`.

### Exercise 17 — JSONPath Range

```sql
WHERE payload @@ '$.amount > 80'
```

**Question:** does JSONB GIN act as a numeric range B-tree here?

**Solution:** No. JSONPath executes, yet range predicates are not fully resolved by GIN alone. For frequent ranges, evaluate a B-tree on a numeric scalar.

### Exercise 18 — Partial GIN

**Requirement:** find `security` events with `severity` `"high"`.

**Solution:**

```sql
SELECT event_id
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb;
```

This predicate implies `audit_events_security_gin_idx`'s partial condition.

### Exercise 19 — Query Not Implying the Partial Predicate

```sql
WHERE payload @> '{"severity":"high"}'::jsonb
```

**Solution:** cannot rely on the `security` partial index to cover the full query, since other `event_type` values exist.

### Exercise 20 — Generic Plans

**Question:** will `WHERE event_type = $1` in a generic plan always use a partial GIN index `WHERE event_type = 'security'`?

**Solution:** No; `$1` could be `billing` or `activity`. A custom plan seeing `$1 = 'security'` can consider the index, though selection still depends on cost.

### Exercise 21 — GIN and ORDER BY

**Requirement:** fetch the 20 newest `security` events with JSON `severity` `"high"`.

```sql
SELECT event_id, created_at
FROM jsonb_index_lab.audit_events
WHERE event_type = 'security'
  AND payload @> '{"severity":"high"}'::jsonb
ORDER BY created_at DESC, event_id DESC
LIMIT 20;
```

**Solution:** GIN narrows JSON candidates but does not supply `created_at` ordering. PostgreSQL either sorts/top-Ns the GIN matches or walks a time B-tree and filters JSON, depending on cost.

### Exercise 22 — Reading Bitmap Heap Scan

A plan shows `Bitmap Index Scan` and `Recheck Cond`.

**Solution:** the index gathers candidate rows, while the heap scan fetches tuples and rechecks exact predicates as needed. This is normal, not an error.

### Exercise 23 — Seq Scan Despite Having GIN

`payload ? 'actor'` matches nearly the entire table.

**Solution:** Seq Scan can be cheaper than random index/heap I/O. Check selectivity, row counts, and buffers.

### Exercise 24 — GIN Maintenance

**Question:** what does `fastupdate` help with and what does it cost?

**Solution:** GIN buffers new entries in a pending list to lower average write cost; the pending list must be merged/cleaned later, which can cause latency spikes and maintenance overhead.

### Exercise 25 — Comparing Index Sizes

**Suggested solution:**

```sql
SELECT
    c.relname,
    pg_size_pretty(pg_relation_size(c.oid))
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
WHERE n.nspname = 'jsonb_index_lab'
ORDER BY pg_relation_size(c.oid) DESC;
```

Never conclude one index type is universally smaller from lab data alone.

### Exercise 26 — Native Arrays and JSONB

**Question:** does `TEXT[]` use GIN `jsonb_ops`?

**Solution:** No. Native arrays use their own operators and opclasses; `labels @> ARRAY['urgent']::text[]` differs from `jsonb_labels ? 'urgent'`.

### Exercise 27 — SELECT vs. DML in EXPLAIN

**Question:** should you run `EXPLAIN ANALYZE UPDATE` just to "preview index usage"?

**Solution:** It **executes the actual UPDATE**. Use `EXPLAIN UPDATE` without `ANALYZE` for an estimated plan, or test on an isolated copy under controlled procedures.

### Exercise 28 — When to Promote a Field to a Typed Column?

**Solution:** when a field is heavily used in JOINs, FKs, unique/range/sort operations, needs strong constraints, or is queried constantly, a typed column simplifies both schema and indexes while JSONB holds flexible attributes.

---

## 22. JSONB Index Design Checklist

### Identify the Queries

1. **Which operator?** `@>`, `?`, `?|`, `?&`, `@?`, `@@`, or scalar equality/range?
2. **What is it applied to?** `payload` or `payload->'labels'`?
3. **What is the return type?** `jsonb` (`->`) or `text` (`->>` / `#>>`)?
4. **How selective is the match?** Do common queries return 1% or 99% of rows?
5. **Is the JSON shape stable?** Are there missing keys, JSON nulls, or mistyped values?
6. **Is the array JSONB or a native SQL array?** Match operators and opclasses accordingly.

### Choose the Index

7. **Need key existence?** Pick `jsonb_ops`, not `jsonb_path_ops` out of habit.
8. **Mostly path/value containment?** Compare `jsonb_ops` vs. `jsonb_path_ops`.
9. **Frequent empty-object queries?** Evaluate `jsonb_path_ops` limitations.
10. **Queries on sub-expressions?** Use an expression GIN index or rewrite cleanly as containment.
11. **Scalar equality?** B-tree expression index or typed column.
12. **Numeric/date ranges?** Never compare text; use numeric/timestamp indexes.
13. **ORDER BY / LIMIT?** GIN does not replace B-tree ordering.
14. **Tenant/partition keys?** Evaluate composite indexing and partition pruning for the workload.
15. **Partial indexes?** Verify queries imply the predicate and check prepared-statement plan caching.
16. **Redundant indexes?** Avoid maintaining `jsonb_ops`, `jsonb_path_ops`, and overlapping expression indexes without justification.

### Verify and Operate

17. **EXPLAIN:** inspect `Index Cond`, `Recheck Cond`, `Filter`, and scan nodes.
18. **EXPLAIN ANALYZE on safe SELECTs:** check `actual rows`, `loops`, `buffers`, and temp I/O.
19. **Check estimates:** is JSON data skewed across tenants or event types?
20. **Refresh stats:** run `ANALYZE` after bulk loads or major distribution shifts.
21. **Write cost:** frequent JSONB updates make GIN and expression indexes expensive.
22. **Pending list:** understand `fastupdate`, cleanup, and latency effects.
23. **Sizes:** measure `pg_relation_size`; never guess from key counts.
24. **Index usage:** review `pg_stat_user_indexes` across representative workload windows.
25. **Large tables:** deploy with `CREATE INDEX CONCURRENTLY` outside transactions and watch for invalid indexes.
26. **Permissions/RLS:** indexes do not enforce authorization or tenant isolation.
27. **JDBC bind types:** pass typed `jsonb` or matching scalar parameters; never cast whole documents to text.
28. **Preserve semantics:** never conflate JSON numbers, strings, nulls, arrays, and objects.

---

## 23. Summary and Key Takeaways

PostgreSQL offers powerful tools to optimize `jsonb` queries, yet **index selection always starts from the query's operator and left-hand expression**:

- **GIN `jsonb_ops`** is the flexible choice for containment, key existence, and supported JSONPath queries.
- **GIN `jsonb_path_ops`** focuses on path-value containment and JSONPath, often worth evaluating for `@>`-heavy workloads, though it **lacks** `?`/`?|`/`?&` and struggles on empty objects.
- **GIN expression indexes** like `GIN ((payload->'labels'))` serve queries applying JSONB operators to a **sub-expression** rather than the whole document.
- **B-tree expression indexes** like `((payload#>>'{actor,id}'))` or `(((payload->>'amount')::numeric))` serve **scalar** equality, range, and ordering queries.
- JSONB GIN **does not automatically accelerate arbitrary `->>` extractions, numeric/text range comparisons, or `ORDER BY`**. Queries must match compatible operators and index keys.
- **JSONB semantics are part of correctness:** never blur missing keys, JSON null, SQL NULL, JSON numbers, and JSON strings just for speed.
- **An eligible index is not guaranteed to be used:** PostgreSQL weighs cost, selectivity, heap fetches, statistics, prepared plans, and write volume.
- **Every index has a cost:** disk, WAL, pending lists, cleanup, JSONB update overhead, and build time. Never stack multiple overlapping indexes on one document without workload evidence.

**Closing question:** Before writing `CREATE INDEX ... USING GIN`, pick a critical query and highlight the exact **left-hand expression of its operator**. Is it `payload`, `payload -> 'labels'`, `payload #>> '{actor,id}'`, or `(payload->>'amount')::numeric`? Answering that precisely guides you straight to **whole-column GIN, expression GIN, expression B-tree, or a typed column**, rather than guessing indexes by intuition.

### Official PostgreSQL Documentation

- [JSON Types — `json` and `jsonb`](https://www.postgresql.org/docs/current/datatype-json.html).
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html).
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html).
- [GIN Built-in Operator Classes](https://www.postgresql.org/docs/current/gin-builtin-opclasses.html).
- [GIN Implementation and Fast Update](https://www.postgresql.org/docs/current/gin-implementation.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [CREATE INDEX — GIN, operator class, CONCURRENTLY](https://www.postgresql.org/docs/current/sql-createindex.html).
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html).
- [PREPARE and Custom/Generic Plans](https://www.postgresql.org/docs/current/sql-prepare.html).
