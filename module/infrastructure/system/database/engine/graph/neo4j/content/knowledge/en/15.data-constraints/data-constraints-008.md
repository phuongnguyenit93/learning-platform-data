# Detecting Violating Data Before Applying Constraints in Neo4j

In Neo4j, **constraints** protect the consistency of a property graph: customer codes cannot collide, mandatory properties are always present, business key pairs uniquely identify a node, or properties must hold the right data type. However, when adding a constraint to a database **that already contains data**, Neo4j must check all nodes/relationships within scope. If any violating record is found, constraint creation fails; Neo4j does not automatically fix or ignore invalid data.

This lesson in the **Data Constraints** chapter focuses on how to **inventory, detect, interpret, and remediate violations before running `CREATE CONSTRAINT`** with Cypher. This is an essential step during data ingestion, schema migrations, using the Neo4j Java Driver or Spring Data Neo4j, and before promoting a graph system to production.

> **Principle:** define the exact rule to enforce -> query to find violating data -> decide how to fix according to business rules -> re-verify -> create the constraint -> verify and monitor subsequent writes. Avoid creating the constraint first and figuring out fixes from the first error message.

## 1. Know What Each Constraint Checks

Each constraint type catches a different class of bad data. Before auditing, lock down **label/relationship type**, **properties**, **the unit of uniqueness**, and **rules for missing values**.

| Constraint Type | Data Condition Required | Violation Pattern to Search First |
| --- | --- | --- |
| Node property uniqueness | Nodes with the same label cannot have **duplicate property values** when present | Multiple nodes sharing the same key value |
| Node composite uniqueness | No two nodes with the same label share **the same tuple of values** across participating properties when all are present | Duplicate key pairs/tuples, e.g., `(tenantId, orderCode)` |
| Node property existence | Every node with the label must carry the mandatory property | Missing property or `null` |
| Node key | Combines **full existence** and **uniqueness** for a single or composite key | Need to find both records missing keys and duplicate key groups |
| Relationship property uniqueness/existence/key | Checks property values across all relationships of the same type (subject to constraint type and version support) | Relationships missing codes or duplicating codes |
| Property type constraint | Present values must match the declared type, e.g., `INTEGER` | Values stored with the wrong type, such as age stored as a string |

**Common pitfall:** property uniqueness **does not** mean property existence. Multiple nodes missing `email` still do not violate uniqueness. Likewise, composite uniqueness does not automatically require every key component to exist. If both conditions are needed, use a node key when supported by your version/edition, or combine the corresponding constraints.

The DDL examples below use Neo4j 5.x syntax. Some constraint types—especially **existence**, **keys**, and **property types**—depend on version and edition (typically Enterprise). Verify support in your target environment before deploying; `property type constraints` are a Neo4j 5 feature starting in 5.9.

## 2. Preparing an Audit Dataset with Intentional Errors

Run the following data creation snippet **once only on a test database**. Labels `AuditCustomer`, `AuditOrder` and type `AUDIT_PLACED` isolate the example from application data. Running `CREATE` multiple times will change expected row and error counts.

```cypher
CREATE
  (c1:AuditCustomer {sourceId: 'C1', email: 'an@example.com', age: 29}),
  (c2:AuditCustomer {sourceId: 'C2', email: 'an@example.com', age: 31}),
  (c3:AuditCustomer {sourceId: 'C3', age: 22}),
  (c4:AuditCustomer {sourceId: 'C4', email: ' AN@Example.com ', age: '25'}),
  (c5:AuditCustomer {sourceId: 'C5', email: 'binh@example.com', age: 40}),
  (o1:AuditOrder {sourceId: 'O1', tenantId: 'T1', orderCode: '001'}),
  (o2:AuditOrder {sourceId: 'O2', tenantId: 'T1', orderCode: '001'}),
  (o3:AuditOrder {sourceId: 'O3', tenantId: 'T2', orderCode: '001'}),
  (o4:AuditOrder {sourceId: 'O4', tenantId: 'T1'}),
  (c1)-[:AUDIT_PLACED {sourceId: 'R1', eventId: 'E1'}]->(o1),
  (c2)-[:AUDIT_PLACED {sourceId: 'R2', eventId: 'E1'}]->(o2),
  (c3)-[:AUDIT_PLACED {sourceId: 'R3'}]->(o3);
```

The dataset intentionally contains these cases:

- **C1/C2** have an exact duplicate `email`; **C4** has an email with the same business meaning if case and whitespace are ignored; **C3** is missing `email`.
- **C4** has `age` stored as string `'25'`, whereas the expected rule requires an integer.
- **O1/O2** duplicate key `(T1, 001)`; **O3** has the same `orderCode` in a different tenant, so it does **not** duplicate the composite key; **O4** is missing `orderCode`.
- **R1/R2** share `eventId = 'E1'`; **R3** is missing `eventId`.

Each record includes `sourceId` to trace back to source ingestion data. In real applications, rely on **stable business IDs** like this when planning remediation. `elementId()` is helpful for finding nodes/relationships within a session, but should not be persisted long-term as a business identifier, especially across re-imports, deletions, or data rebuilds.

## 3. Detecting Duplicate Values Before a Uniqueness Constraint

### 3.1. Checking Exact Duplicates

Suppose you want uniqueness on `AuditCustomer.email`. Group in Cypher style by placing the key expression and aggregate functions in `WITH`, then filtering groups with more than one row:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH c.email AS email,
     count(*) AS occurrences,
     collect(c.sourceId) AS records
WHERE occurrences > 1
RETURN email, occurrences, records
ORDER BY occurrences DESC, email;
```

Expected output:

| email | occurrences | records |
| --- | ---: | --- |
| `an@example.com` | 2 | `['C1', 'C2']` |

The filter `WHERE c.email IS NOT NULL` matches uniqueness behavior: missing properties do not produce a key value for duplicate checks. If you only want to know **whether violations exist** on a large dataset, skip `collect()` over all record IDs:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH c.email AS email, count(*) AS occurrences
WHERE occurrences > 1
RETURN count(*) AS duplicateGroups,
       coalesce(sum(occurrences - 1), 0) AS excessRecords;
```

On the sample data, `duplicateGroups = 1` and `excessRecords = 1`. `excessRecords` is the count of records beyond one kept per group; it does **not** automatically decide which record should be deleted.

### 3.2. Distinguishing Technical Duplicates from Business Duplicates

Neo4j compares property values by the exact type and value stored in the database. Thus `'an@example.com'` and `' AN@Example.com '` are two different strings; uniqueness on `email` does **not** treat them as duplicates.

If product rules specify comparing emails after trimming outer whitespace and ignoring case, audit using the normalized key:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS occurrences,
     collect(c.sourceId) AS records
WHERE occurrences > 1
RETURN normalizedEmail, occurrences, records;
```

The result shows one group `an@example.com` containing **3 records: C1, C2, C4**. This is a **business-rule check**, not the exact violation set of a uniqueness constraint on the raw property. If the database must enforce normalized uniqueness, design a normalized key property (such as `emailKey`), clean source data, and create uniqueness on `emailKey`.

Functions like `trim()` and `toLower()` expect string inputs. If ingested data can hold wrong types, detect wrong-type values before running bulk normalization expressions.

## 4. Detecting Missing Properties Before Existence or Node Keys

For each mandatory property, use `IS NULL`:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NULL
RETURN c.sourceId AS sourceId, properties(c) AS currentProperties
ORDER BY sourceId;
```

The result returns **C3**. In Neo4j, you cannot store a property with value `null` as a normal value: setting a property to `null` removes that property. Hence `c.email IS NULL` covers absent properties.

For composite keys, find **all rows missing at least one component**, not only rows missing all components:

```cypher
MATCH (o:AuditOrder)
WHERE o.tenantId IS NULL OR o.orderCode IS NULL
RETURN o.sourceId AS sourceId,
       o.tenantId AS tenantId,
       o.orderCode AS orderCode
ORDER BY sourceId;
```

The result returns **O4**, missing `orderCode`. This row **does not fail composite uniqueness** on `(tenantId, orderCode)`, but it **fails the corresponding node key**.

To audit counts before inspecting individual records:

```cypher
MATCH (c:AuditCustomer)
RETURN count(*) AS totalCustomers,
       count(c.email) AS customersWithEmail,
       count(*) - count(c.email) AS missingEmail;
```

For example, this produces `totalCustomers = 5`, `customersWithEmail = 4`, and `missingEmail = 1`. `count(property)` counts only non-`null` values; `count(*)` counts every row.

## 5. Detecting Duplicate Composite Keys

Suppose `orderCode` only needs to be unique **within each tenant**. The unit of uniqueness is the `(tenantId, orderCode)` pair, not `orderCode` alone.

```cypher
MATCH (o:AuditOrder)
WHERE o.tenantId IS NOT NULL AND o.orderCode IS NOT NULL
WITH o.tenantId AS tenantId,
     o.orderCode AS orderCode,
     count(*) AS occurrences,
     collect(o.sourceId) AS records
WHERE occurrences > 1
RETURN tenantId, orderCode, occurrences, records
ORDER BY occurrences DESC, tenantId, orderCode;
```

Output:

| tenantId | orderCode | occurrences | records |
| --- | --- | ---: | --- |
| `T1` | `001` | 2 | `['O1', 'O2']` |

**O3** is not treated as a duplicate of O1/O2 because it belongs to tenant `T2`. When designing constraints, picking the wrong scope (such as uniqueness on `orderCode` alone) will flag valid data as violating.

For **composite uniqueness**, run the duplicate check on tuples where all properties are present. For a **composite node key**, run **both** the duplicate check in this section **and** the missing-key check in Section 4.

## 6. Auditing Properties on Relationships

Constraints on relationships are evaluated across **all relationships of the same type**, regardless of which nodes they connect. For instance, requiring every `AUDIT_PLACED` to have `eventId` and each `eventId` to be used at most once.

Check duplicates:

```cypher
MATCH ()-[r:AUDIT_PLACED]->()
WHERE r.eventId IS NOT NULL
WITH r.eventId AS eventId,
     count(*) AS occurrences,
     collect(r.sourceId) AS records
WHERE occurrences > 1
RETURN eventId, occurrences, records;
```

Output: `eventId = 'E1'` appears **2 times**, on R1/R2.

Check missing values:

```cypher
MATCH ()-[r:AUDIT_PLACED]->()
WHERE r.eventId IS NULL
RETURN r.sourceId AS sourceId,
       properties(r) AS currentProperties;
```

Output returns **R3**. The pattern `MATCH ()-[r:AUDIT_PLACED]->()` does not constrain endpoint node labels, avoiding accidentally skipping relationships of the same type attached to other node types.

One distinction to keep in mind: a unique constraint on `r.eventId` checks **`eventId` globally across that relationship type**. If the requirement is "`eventId` is unique per tenant", include tenant scope in the key model and select the matching constraint; scope cannot be inferred automatically from endpoint nodes.

## 7. Detecting Wrong Types Before Property Type Constraints

Data can be **present and non-duplicate** yet still have the wrong type. In the sample dataset, `C4.age` is string `'25'` whereas the intended rule requires an integer.

With Cypher supporting **type predicates** (Neo4j 5.9 and later), check:

```cypher
MATCH (c:AuditCustomer)
WHERE c.age IS NOT NULL
  AND NOT (c.age IS :: INTEGER)
RETURN c.sourceId AS sourceId,
       c.age AS actualValue,
       valueType(c.age) AS actualType;
```

The query finds **C4**. If `age` might be missing and business rules require it, also check `WHERE c.age IS NULL`: **type constraints do not replace existence constraints**.

Do not "fix" all strings into numbers by blindly casting before inspecting the data. With values like `'25'`, `'25 years'`, or `'unknown'`, indiscriminate conversion can lose information or corrupt data. Define conversion rules, preserve originals if needed, and inspect unconvertible cases.

**Business validity differs from schema validity:** `STRING` does not guarantee an email is well-formed; `INTEGER` does not guarantee age falls within an allowed range. Those rules need additional validation in ingestion workflows or the application layer.

## 8. Pre-Migration Audit and Remediation Workflow

### Step 1 — Document the Target Constraint Set

Example:

| Target | Planned Rule | Checks That Must Pass |
| --- | --- | --- |
| `AuditCustomer.email` | Unique and mandatory | No duplicate actual values; none missing |
| `AuditCustomer.age` | `INTEGER` | No present values with wrong type |
| `AuditOrder(tenantId, orderCode)` | Node key | No missing components; no duplicate pairs |
| `AUDIT_PLACED.eventId` | Unique and mandatory | No duplicates; none missing |

To inspect **existing** constraints and avoid duplicate or conflicting definitions, check:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

### Step 2 — Run **Read-Only** Audits and Save Violation Lists

The `MATCH`/`RETURN` queries in Sections 3–7 do not modify data. Save the **violation type, duplicate/missing keys, counts, and business IDs** to review with data owners. On large record sets, count groups first, then query details for the groups requiring remediation; `collect()` across all nodes/IDs can exhaust memory.

Do not read `LIMIT 10` in an error-listing query as "the whole dataset only has 10 errors." `LIMIT` caps only **the displayed sample**; to verify the data is clean, aggregate across **the entire target scope**.

### Step 3 — Choose Remediation Based on Business Rules

Depending on the violation type, remediation differs:

1. **Duplicate keys:** determine which node/relationship is authoritative, whether attributes and relationships must be merged, or whether the chosen business key is actually too narrow. Never run `DETACH DELETE` on a copy without checking connected relationships.
2. **Missing properties:** backfill from a trusted source, or agree on whether incomplete records need a status/label change before applying constraints.
3. **Wrong types:** verify source formats and conversion rules; re-audit after conversion.
4. **Duplicates under normalization:** standardize whitespace trimming and case rules consistently across APIs, imports, and existing records.

Cypher's `MERGE` is useful for creating or matching data by key, but **does not automatically merge already-existing duplicate nodes**. Choosing the surviving record, migrating relationships, and resolving conflicting attributes must be an intentional data-repair plan.

You can preview normalized keys **without writing**:

```cypher
MATCH (c:AuditCustomer)
WHERE c.email IS NOT NULL
RETURN c.sourceId AS sourceId,
       c.email AS originalEmail,
       toLower(trim(c.email)) AS proposedEmailKey
ORDER BY sourceId;
```

### Step 4 — Re-Check Immediately Before Creating Constraints

After fixing data, re-run all audit queries. You should see **0 duplicate groups**, **0 missing records**, and **0 wrong-type records** matching each constraint. If applications are still writing data, new violations can appear between the audit and constraint creation. Plan the migration window, control write paths during transition, and let the constraint serve as the guard once created.

### Step 5 — Create Constraints and Verify

The commands below **illustrate the target configuration**. **Do not run them on the dirty dataset from Section 2** before cleaning; the affected constraints will fail. Use the real names and labels/types of your environment, and verify edition/version for constraints beyond basic uniqueness.

```cypher
// Unique on node email
CREATE CONSTRAINT audit_customer_email_unique IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.email IS UNIQUE;
```

```cypher
// Existence: requires supporting edition
CREATE CONSTRAINT audit_customer_email_required IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.email IS NOT NULL;
```

```cypher
// Composite node key: both unique and requires all properties
CREATE CONSTRAINT audit_order_key IF NOT EXISTS
FOR (o:AuditOrder)
REQUIRE (o.tenantId, o.orderCode) IS NODE KEY;
```

```cypher
// Unique on relationship property: requires supporting version
CREATE CONSTRAINT audit_event_unique IF NOT EXISTS
FOR ()-[r:AUDIT_PLACED]-()
REQUIRE r.eventId IS UNIQUE;
```

```cypher
// Property type constraint: Neo4j 5.9+ feature on supporting editions
CREATE CONSTRAINT audit_customer_age_integer IF NOT EXISTS
FOR (c:AuditCustomer)
REQUIRE c.age IS :: INTEGER;
```

`IF NOT EXISTS` only avoids errors when a matching constraint already exists; **it does not allow bypassing violating data**. After deployment, re-run `SHOW CONSTRAINTS` and confirm the intended constraints are present.

## 9. Operating Safely on Large Graphs

Auditing an entire large label can read many nodes/relationships and group many values. Best practices:

- **Prefer lightweight summary queries:** count violating groups first, then inspect `sourceId` lists for individual groups needing fixes; limit `collect()` when duplicate groups are huge.
- **Inspect execution plans:** use `EXPLAIN` or `PROFILE` on read-only queries when needed to check scan size, index access, and aggregation memory. Note that `PROFILE` actually runs the query.
- **Run in an appropriate load window:** execute heavy audits when resources are provisioned; explicitly confirm the target database, label, and relationship type.
- **Keep verifiable evidence:** before/after violation counts, modified fields, review outcomes, deployment timestamps, and created constraints.
- **Protect new writes:** normalize and validate inputs in ingestion jobs, the Neo4j Java Driver, or Spring Data Neo4j; handle database constraint errors in business terms. Application checks do not replace the concurrency guarantees of database constraints.

In multi-tenant systems or multi-source integrations, the most critical step is defining the exact **uniqueness boundary**: global, per-tenant, or per-source. A constraint schema with the wrong scope can be technically consistent yet wrong for the business.

## 10. Pre-Constraint Readiness Checklist

| Checklist Question | Completion Signal |
| --- | --- |
| Have label/type, properties, and uniqueness scope been defined? | Explicit business key specification and constraint types |
| Have exact duplicates been checked on the keys to be stored? | 0 groups with `count(*) > 1` |
| Are there string/value normalization rules? | Audited using the normalized key and storage convention aligned |
| Have all mandatory properties been checked? | 0 rows with property `IS NULL` |
| Do composite keys have any missing components? | 0 rows missing any component when using a node key |
| Have relationships and data types been checked if applicable? | 0 duplicate relationship groups, 0 missing relationship properties, 0 wrong-type values |
| Was the audit re-run after cleanup and right before deployment? | Latest audit report is clean and write flows are controlled |
| Were constraints verified after creation? | `SHOW CONSTRAINTS` lists every intended constraint |

**Takeaway:** creating a constraint is **the final step of cleaning and verifying data**, not a data-repair tool. An audit report clearly tells you "who is violating what"; deciding "how to fix it" still requires understanding the property graph model, inter-node relationships, and the system's business keys.
