# Representing Effective Time, History, and Entity Versions in Neo4j

An entity in a graph can keep the same identity while changing properties or relationships over time. For example, customer `C001` is ranked `BRONZE` from 2024-01-01 and transitions to `GOLD` starting 2024-04-01; employee `E01` transfers from department `D01` to `D02` starting 2024-07-01. If you only overwrite the node's current property or delete the old relationship, you cannot answer: **“What state did the graph hold at a given point in the past?”**

In Neo4j, you can model effective time using temporal properties on nodes/relationships, store entity versions as separate nodes, or combine recorded time so you know **what the system believed at an earlier point in time**. This lesson focuses on property graph design and Cypher queries for history, auditing, and state reconstruction.

## 1. Distinguishing Temporal Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| **Valid time** | Time interval during which a fact is true in the business domain | `GOLD` tier is effective from 2024-04-01 |
| **Recorded/system time** | Time interval during which the system stored and treated a fact as current truth | On 2024-04-10, the system received a change effective 2024-04-01 |
| **Version** | A specific state of an entity, typically with a version number and effective interval | `CustomerVersion` #2 stores tier `GOLD` |
| **Event** | Something that happened, with a timestamp and business semantics | `CustomerPromoted` occurred on 2024-04-01 |
| **Point-in-time snapshot** | State reconstructed as of a query timestamp | `C001`'s tier on 2024-03-15 |

**Valid time** answers “What was true in the business on date X?”. **Recorded time** answers “On date Y, what did the system know/record?”. These two questions diverge whenever data arrives late or gets corrected retroactively.

The recommended interval convention is **closed at the start, open at the end**:

\[
[\text{validFrom},\ \text{validTo})
\]

At time `t`, a record is effective if:

~~~text
validFrom <= t AND (validTo IS NULL OR t < validTo)
~~~

Accordingly, an old version ending on `2024-04-01` and a new version starting on `2024-04-01` do not overlap. In Neo4j, missing properties read as `null`; assigning `null` to a property also removes it. Therefore, you can **omit `validTo` altogether** to represent an open-ended interval.

Choose the right precision from the start:

- `date` for business-day changes, such as a loyalty tier taking effect at the start of a day.
- `datetime` for instant-level changes, such as access permissions effective from `2024-04-01T09:30:00Z`. Standardize timezones and conversion rules across systems.
- Never use arbitrary strings like `"01/04/24"` for interval comparisons; store native Neo4j temporal types.

## 2. Three Ways to Represent History in a Property Graph

| Model | Structure | Appropriate When | Things to Watch |
| --- | --- | --- | --- |
| **Temporal properties on node/relationship** | Add `validFrom`, `validTo` to a record or edge | Simple relationship history, such as which department an employee belonged to | Never delete historical records when their validity ends |
| **Version nodes** | `(:Customer)-[:HAS_VERSION]->(:CustomerVersion)` | Need to query past states of an entity while preserving a stable business ID | Increases node/edge count; requires interval management |
| **Event nodes** | `(:Customer)-[:HAS_EVENT]->(:CustomerEvent)` | Need to explain why state changed or replay from an event stream | Rebuilding snapshots can be expensive; often paired with versions/snapshots |

These patterns can be combined. A system commonly uses version nodes for entity state history, effective-dated relationships for simple links, and events for business audit trails.

**Do not confuse “version 3” with “state on day 3”.** Version numbers reflect creation/edit order; backdated versions added retroactively can have an earlier `validFrom` than a previously recorded version.

## 3. Root Entity and Version Node Model

Keep one root node as the entity's **stable identity**, then link it to nodes holding time-varying state:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId: C001"]
    V1["CustomerVersion v1<br/>BRONZE<br/>[2024-01-01, 2024-04-01)"]
    V2["CustomerVersion v2<br/>GOLD<br/>[2024-04-01, ∞)"]
    C -->|HAS_VERSION| V1
    C -->|HAS_VERSION| V2
~~~

Here:

- `Customer.customerId` is the stable business key used as the query anchor.
- `CustomerVersion` stores mutable attributes: `loyaltyTier`, `fullName`, `validFrom`, `validTo`, and `versionNo`.
- Relationship `HAS_VERSION` indicates the states belong to the same customer.
- Immutable or identity-defining attributes can sit on the root node; attributes needing historical queries must live on the corresponding version.

### 3.1. Constraints and Indexes

The following Cypher statements use Neo4j 5.x+ syntax:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT customer_version_unique IF NOT EXISTS
FOR (v:CustomerVersion)
REQUIRE (v.customerId, v.versionNo) IS UNIQUE;

CREATE RANGE INDEX customer_version_time IF NOT EXISTS
FOR (v:CustomerVersion)
ON (v.customerId, v.validFrom);
~~~

The first constraint prevents duplicate root identities; the second prevents duplicate `(customerId, versionNo)` **pairs**. Repeating `customerId` on version nodes supports identification and indexing, though the application must still ensure `CustomerVersion.customerId` matches the `Customer` node it connects to.

An index on `(customerId, validFrom)` helps queries starting directly at version nodes by ID and date. If queries always locate `Customer` via its unique constraint and traverse `HAS_VERSION`, Neo4j may prefer relationship traversal; inspect the actual plan with `EXPLAIN` or `PROFILE`.

### 3.2. Creating a Two-Version Example

~~~cypher
CREATE (c:Customer {customerId: 'C001'})
CREATE (v1:CustomerVersion {
    customerId: 'C001',
    versionNo: 1,
    validFrom: date('2024-01-01'),
    validTo: date('2024-04-01'),
    fullName: 'Nguyen An',
    loyaltyTier: 'BRONZE'
})
CREATE (v2:CustomerVersion {
    customerId: 'C001',
    versionNo: 2,
    validFrom: date('2024-04-01'),
    fullName: 'Nguyen An',
    loyaltyTier: 'GOLD'
})
CREATE (c)-[:HAS_VERSION]->(v1)
CREATE (c)-[:HAS_VERSION]->(v2);
~~~

Run the setup snippet on an empty test database or change the ID if `C001` already exists. Version `v2` has no `validTo` property, indicating no expiration date is currently known. The data illustrates business state and does not imply the two versions were recorded by the system on their exact effective dates.

### 3.3. Querying “As Of” State

Suppose the application passes `$customerId = 'C001'` and `$asOf = '2024-03-15'` (ISO 8601 date string):

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
WITH v, date($asOf) AS asOf
WHERE v.validFrom <= asOf
  AND (v.validTo IS NULL OR asOf < v.validTo)
RETURN v.versionNo AS version,
       v.fullName AS fullName,
       v.loyaltyTier AS loyaltyTier,
       v.validFrom AS validFrom,
       v.validTo AS validTo;
~~~

The result for `2024-03-15` is version **1 / BRONZE**; for `2024-04-01`, version **2 / GOLD**. Under the non-overlapping rule, an as-of query returns at most one state per entity. Returning multiple rows indicates a data-integrity issue to investigate.

To view the full history instead of a single snapshot:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
RETURN v.versionNo AS version,
       v.loyaltyTier AS tier,
       v.validFrom AS fromDate,
       v.validTo AS toDate
ORDER BY v.validFrom, v.versionNo;
~~~

To fetch the state effective **today**, use `date()` instead of `date($asOf)`, keeping in mind that “today” is evaluated using Neo4j's query session clock and timezone. For timezone-specific business logic, have the application compute the business date and pass it as a parameter.

### 3.4. Writing a New Version Inside a Transaction

When changes only occur **after existing effective intervals**, you can close the old interval and open a new version:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(old:CustomerVersion)
WHERE old.validTo IS NULL
  AND old.validFrom < date($effectiveFrom)
SET old.validTo = date($effectiveFrom)
CREATE (c)-[:HAS_VERSION]->(next:CustomerVersion {
    customerId: $customerId,
    versionNo: old.versionNo + 1,
    validFrom: date($effectiveFrom),
    fullName: $fullName,
    loyaltyTier: $loyaltyTier
})
RETURN next.versionNo AS version, next.validFrom AS validFrom;
~~~

This example targets sequential update flows where each entity has **one open latest version**. Run the entire statement inside a write transaction; closing the old interval and creating the new node must succeed or roll back atomically. Under concurrent updates, apply write-layer locking/conflict control, use unique constraints to catch duplicate version numbers, and handle retries per business rules. Never assume `versionNo + 1` alone is concurrency-safe.

If a change must take effect **retroactively** (for instance, on 2024-03-15 when a version starting 2024-04-01 already exists), do not use the statement above as-is. You must locate affected intervals, split or adjust impacted ranges, and verify history afterward. Retroactive updates also differ from correcting data that was previously recorded erroneously, as covered in the bitemporal section below.

An auxiliary `CURRENT_VERSION` relationship can optimize current-state reads, yet it is derived data. If future-dated versions or retroactive edits are permitted, clearly define “current” and update the pointer timely; `validFrom/validTo` queries remain the authoritative basis for point-in-time lookups.

## 4. Relationship History: Who Was Linked to Whom and When?

Not every change needs version nodes. A relationship can directly carry effective intervals. For example, employee `E01` belonged to department `D01` until before 2024-07-01, then transferred to `D02`:

~~~cypher
CREATE (e:Employee {employeeId: 'E01'})
CREATE (d1:Department {deptId: 'D01', name: 'Sales'})
CREATE (d2:Department {deptId: 'D02', name: 'Operations'})
CREATE (e)-[:WORKS_IN {
    validFrom: date('2024-01-01'),
    validTo: date('2024-07-01')
}]->(d1)
CREATE (e)-[:WORKS_IN {
    validFrom: date('2024-07-01')
}]->(d2);
~~~

Querying the department on any given date:

~~~cypher
MATCH (:Employee {employeeId: $employeeId})
      -[r:WORKS_IN]->(d:Department)
WITH r, d, date($asOf) AS asOf
WHERE r.validFrom <= asOf
  AND (r.validTo IS NULL OR asOf < r.validTo)
RETURN d.deptId AS departmentId, d.name AS departmentName;
~~~

`2024-06-30` returns `D01`; `2024-07-01` returns `D02`. **Do not delete the old `WORKS_IN` edge** when an employee transfers departments, as doing so erases relationship history.

There is an important caveat: if `Department.name` is edited directly from `Sales` to a new name, the historical query still returns the department's **current name**. If you need an exact snapshot of the department's historical name as well, version the `Department` entity too or link to an immutable version node.

When the relationship itself has multiple properties, a lifecycle, or amendments (such as appointment contracts, roles, allocation percentages), you can **promote the relationship to a business node**:

~~~text
(:Employee)-[:HAS_ASSIGNMENT]->(:Assignment {
    assignmentId, validFrom, validTo, role
})-[:TO_DEPARTMENT]->(:Department)
~~~

An `Assignment` node easily supports its own ID, version history, attached documents, and extra relationships. It is the right choice when a simple edge cannot express the full semantics.

## 5. Bitemporal Models

A version with only `validFrom/validTo` tells you **what is considered true in the business today**. It cannot answer: **“On 2024-04-10, what tier did the system believe the customer held on 2024-03-15?”**

To answer that, each fact/version needs two independent intervals:

- `validFrom` / `validTo`: when the fact is true in the business domain.
- `recordedFrom` / `recordedTo`: when the system considered that fact an accepted record.

Example: the system initially recorded tier `GOLD` effective 2024-03-01, then on 2024-05-01 received a correction stating it should have taken effect on 2024-02-01.

| Record | Tier | Valid Interval | Recorded Interval |
| --- | --- | --- | --- |
| A | `BRONZE` | [Jan 1, Mar 1) | [Jan 5, May 1) |
| B | `GOLD` | [Mar 1, ∞) | [Mar 2, May 1) |
| C | `BRONZE` | [Jan 1, Feb 1) | [May 1, ∞) |
| D | `GOLD` | [Feb 1, ∞) | [May 1, ∞) |

*All dates in the table are in 2024; “∞” indicates an unclosed interval.* Records A/B represent the view before correction; C/D represent the view after correction. At a given `recordedAt` timestamp, only records whose recorded interval covers that timestamp are evaluated; thus A/B's valid intervals never conflict with C/D's.

You can store these records under label `CustomerAssertion`, linked from `Customer` via `HAS_ASSERTION`. Sample node properties:

~~~cypher
CREATE (:CustomerAssertion {
    customerId: 'C001',
    loyaltyTier: 'GOLD',
    validFrom: date('2024-02-01'),
    recordedFrom: datetime('2024-05-01T00:00:00Z')
});
~~~

The snippet above only illustrates properties of assertion D. In a full model, link it to the `Customer` node and persist the remaining assertions as well.

Bitemporal query, where `$validAt` is an ISO date string and `$knownAt` is a timezone-aware ISO datetime string:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_ASSERTION]->(a:CustomerAssertion)
WITH a, date($validAt) AS validAt,
        datetime($knownAt) AS knownAt
WHERE a.validFrom <= validAt
  AND (a.validTo IS NULL OR validAt < a.validTo)
  AND a.recordedFrom <= knownAt
  AND (a.recordedTo IS NULL OR knownAt < a.recordedTo)
RETURN a.loyaltyTier AS tier,
       a.validFrom AS effectiveFrom,
       a.recordedFrom AS knownFrom;
~~~

Using the table example:

- `validAt = 2024-02-15`, `knownAt = 2024-04-10T12:00:00Z`: returns `BRONZE` from record A.
- `validAt = 2024-02-15`, `knownAt = 2024-05-10T12:00:00Z`: returns `GOLD` from record D.

When issuing a correction, run one transaction to **close `recordedTo` on superseded assertions and create new assertions** with corrected valid intervals. Never overwrite tier or valid time on old assertions if you must preserve answers to “what did the system know at an earlier time”. Updating `recordedTo` closes the metadata window of when the assertion was active knowledge; the historical claim itself stays intact.

**Note:** Neo4j supports temporal data types and transactions, but does not provide automatic system-versioned/bitemporal management for this pattern. `recordedFrom/recordedTo` must be maintained consistently by the application or ingestion pipeline. If strict commit-order accuracy is required, design transaction identifiers and concurrency handling accordingly; application-generated timestamps do not automatically equal actual commit timestamps.

## 6. Detecting Overlapping Intervals and Invalid Data

Define business invariants upfront. For instance, “each customer has **at most one** valid tier at any point in time”. Cypher does not automatically forbid two overlapping versions solely via a unique constraint on `(customerId, versionNo)`.

### 6.1. Checking Invalid Intervals

~~~cypher
MATCH (v:CustomerVersion)
WHERE v.validFrom IS NULL
   OR (v.validTo IS NOT NULL AND v.validTo <= v.validFrom)
RETURN v.customerId, v.versionNo, v.validFrom, v.validTo;
~~~

The ideal result is **0 rows**: every interval must have a start and, if bounded, an end strictly greater than its start.

### 6.2. Detecting Two Overlapping Versions

Two half-open intervals `[aFrom, aTo)` and `[bFrom, bTo)` overlap when `aFrom < bTo` and `bFrom < aTo`:

~~~cypher
MATCH (c:Customer)-[:HAS_VERSION]->(a:CustomerVersion),
      (c)-[:HAS_VERSION]->(b:CustomerVersion)
WHERE a.versionNo < b.versionNo
  AND a.validFrom < coalesce(b.validTo, date('9999-12-31'))
  AND b.validFrom < coalesce(a.validTo, date('9999-12-31'))
RETURN c.customerId AS customerId,
       a.versionNo AS versionA,
       b.versionNo AS versionB,
       a.validFrom AS fromA, a.validTo AS toA,
       b.validFrom AS fromB, b.validTo AS toB;
~~~

This query uses `9999-12-31` as a sentinel for an open end; use it only if business dates never exceed that bound. It is a data-validation query and can be expensive when entities accumulate many versions.

### 6.3. Counting Unclosed Intervals

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:HAS_VERSION]->(v:CustomerVersion)
WHERE v.validTo IS NULL
WITH c, count(v) AS openVersions
WHERE openVersions <> 1
RETURN c.customerId AS customerId, openVersions;
~~~

If the rule states each customer has exactly one open latest version, this should also return **0 rows**. If business logic allows entities with no versions yet or fixed-term closed intervals, adjust the invariant check accordingly.

Besides overlaps, check for **gaps** if business rules demand continuous history: sort by `validFrom` and compare the previous version's `validTo` against the next version's `validFrom`. A gap is not always a bug—for example, an employee leaving and later returning; rules must reflect real business semantics.

## 7. Interval Range Queries and Performance Tuning

Beyond “as of date X”, systems often ask **which versions intersect a range `[start, end)`**. The intersection condition is:

~~~cypher
MATCH (:Customer {customerId: $customerId})
      -[:HAS_VERSION]->(v:CustomerVersion)
WITH v, date($rangeStart) AS rangeStart,
        date($rangeEnd) AS rangeEnd
WHERE rangeStart < rangeEnd
  AND v.validFrom < rangeEnd
  AND (v.validTo IS NULL OR rangeStart < v.validTo)
RETURN v.versionNo, v.loyaltyTier, v.validFrom, v.validTo
ORDER BY v.validFrom;
~~~

Using `<` instead of `<=` ensures intervals that merely **touch at a boundary** are not treated as intersecting.

Key considerations for large-scale deployments:

1. **Start from an indexed key** (such as `Customer.customerId`) before traversing `HAS_VERSION`; avoid scanning the entire graph per request.
2. For very long histories, consider querying `CustomerVersion` directly by `customerId` and `validFrom` to leverage a composite index; verify with `PROFILE` rather than guessing.
3. Return only required fields; paginate long histories with deterministic `ORDER BY`.
4. Separate **current-state queries** from **audit history**. You can maintain a current snapshot for fast reads, provided it stays synchronized and remains recoverable from history.
5. In bitemporal datasets, size grows quickly as corrections split intervals. Establish retention policies, load-test queries, and enforce reasonable query bounds.

## 8. Decisions to Finalize Before Implementation

| Design Question | Recommendation |
| --- | --- |
| Does the entity need a stable ID across versions? | Keep a root node with the business key; store states on version nodes. |
| Does the relationship change while endpoints need no versioning? | Place `validFrom/validTo` on the relationship and preserve historical edges. |
| Need to reconstruct endpoint properties as they were in the past? | Version the endpoint nodes too, or link to their corresponding version nodes. |
| Is there late-arriving data or retroactive corrections? | Separate valid time and recorded time; never overwrite old assertions. |
| Need to know “why” a change occurred? | Store business events or metadata: source, actor, reason, transaction ID. |
| Can multiple states be valid simultaneously? | Redefine keys and invariants; e.g., tiers per loyalty program. |
| Are writes concurrent? | Use write transactions, unique constraints, conflict control, and application-level overlap checks. |

When using the **Java Driver** or **Spring Data Neo4j**, pass structured temporal types (e.g., `LocalDate` for `date`, offset/zoned temporal types for `datetime`), keep creating the new version and closing the old version inside **one transaction**, and centralize invariant checks in one clear component. Never let separate service branches update effective intervals with conflicting rules.

## 9. Self-Check Exercises

**Scenario 1.** Customer `C001` has the two versions from Section 3. Predict the `asOf` query result at `2024-03-31`, `2024-04-01`, and `2024-06-01`.

**Answer:** `BRONZE`, `GOLD`, and `GOLD`, respectively. `2024-04-01` belongs to the new version because of the `[from, to)` convention.

**Scenario 2.** Employee `E01` transfers from `D01` to `D02` on 2024-07-01. Should the `WORKS_IN` edge to `D01` be deleted?

**Answer:** No. Close the old edge's validity at `2024-07-01` and create a new edge starting on that date. Deleting the old edge would cause historical queries before July to return incomplete data.

**Scenario 3.** On 2024-05-01, the system discovers that data recorded in March had the wrong effective date. Does editing `validFrom` directly on the old node preserve the audit trail?

**Answer:** No, if you need to know what date the system had recorded prior to 2024-05-01. In that case, use a bitemporal model or store traceable correction events. Bitemporal modeling preserves both business state by valid date and system knowledge state by recorded date.

**Remember:** A sound temporal model explicitly defines **what is effective**, **when it is effective**, **when the system recorded it**, and **which historical states must be preserved**. Interval conventions, versioning, and transactions determine how trustworthy historical queries are in Neo4j.
