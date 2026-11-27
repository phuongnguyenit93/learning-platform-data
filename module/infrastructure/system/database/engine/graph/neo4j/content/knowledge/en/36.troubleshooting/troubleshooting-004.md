# Duplicate Data, Constraint Violations, and Unexpected MERGE Behavior

## 1. Why Is MERGE Not a “Silver-Bullet Deduplication Command”?

In Neo4j, data is organized as a **property graph**: nodes have labels and properties, and relationships have types, directions, and properties. Applications use Cypher to match, create, and update the graph; the Java Driver or Spring Data Neo4j sends those queries inside transactions.

When integrating data, many teams pick `MERGE` expecting:

- If the node/relationship already exists, reuse it.
- If it does not exist, create it.
- No matter how many times it is re-run, the graph will never have duplicates.
- If constraints exist, Neo4j will automatically merge all identical entities.
- If two workers write concurrently, both will succeed automatically without error handling.

**Only the first two points hold within the scope of the pattern matched by MERGE; the remaining expectations are not guaranteed automatically.**

Example:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
RETURN c;
~~~

Cypher searches for a `Customer` node matching **the entire specified pattern and properties**; if none is found, it attempts to create a new node. However, if the data already contains **two nodes with the same `customerId`**, the query can match multiple nodes and will **not merge** them into one.

If two concurrent transactions execute `MERGE` **without a matching uniqueness constraint**, both may fail to see the node and create two records sharing the same business key.

This lesson focuses on troubleshooting: **identifying where duplicates exist, distinguishing root causes, inspecting constraints/indexes, fixing Cypher, protecting concurrent writes, and safely cleaning up data**. The examples use a Customer, Order, User, and FOLLOWS relationship model; swap in labels/types suited to your real application.

## 2. Symptom Map and Common Root Causes

| Symptom | Likely causes to check first | Remediation direction |
|---|---|---|
| Two `Customer` nodes share the same email | No unique key; inconsistent normalization; parallel imports | Define business key, locate duplicates, add constraint |
| `MERGE` reports constraint validation error | MERGE pattern missed existing node, then CREATE violated unique key | Narrow the MERGE key, inspect extra properties |
| `MERGE` returns multiple rows | Multiple nodes/relationships share the pattern, or multi-row input | Count actual nodes/relationships; inspect `UNWIND`/`MATCH` |
| Same User pair has two FOLLOWS edges | MERGE includes changing property; concurrent writers; legacy duplicates | Stabilize edge identity key, control concurrency |
| Re-running MERGE creates a new record | Changing key, different null/format, different label/type | Normalize input, use an immutable business key |
| `MERGE` creates nothing | `MATCH` or `WHERE` before MERGE produced 0 rows | Check input cardinality |
| `MERGE` tries to recreate an existing node | MERGEing a path pattern that did not fully match | Bind nodes first, MERGE relationship afterward |
| Constraint creation rejected | Duplicate data already exists on the constrained property | Find and resolve duplicates before migration |
| MERGE runs slowly | Missing index/constraint or low-selectivity key | Check `EXPLAIN` and appropriate indexes |
| Updates repeat even with a single node | `SET counter = counter + 1` lacks idempotency protection | Use command receipts and stable command keys |
| Driver retries yet requests keep failing | Permanent data error, constraint violation, or conflict | Classify errors; avoid infinite retries |

**Triage order:** first verify **whether graph entities are actually duplicated**, then check **which pattern MERGE uses**, **which constraints are active**, **how many rows enter the clause**, and finally analyze write contention.

## 3. Understand the Exact Matching Unit of MERGE

`MERGE` means: try to **match the entire specified pattern**; if no matching pattern exists, try to **create that pattern**.

### 3.1. MERGEing a Node by a Single Property

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u.userId AS userId;
~~~

With a uniqueness constraint on `User.userId` and a valid, stable `$userId`, this is a solid starting point to find or create a User by business ID.

However:

- Without a constraint, concurrent transactions can still create duplicates.
- If two Users already share the same key beforehand, MERGE will not clean them up.
- If `$userId` changes across retries, each value represents a different key.
- If `userId` appears across different labels, a constraint on `:User` does not automatically apply to another label.

### 3.2. MERGEing by Multiple Properties: Every Property Participates in Identity

~~~cypher
MERGE (u:User {
    userId: $userId,
    status: $status
})
RETURN u;
~~~

Suppose a node already has `userId = 'U-100'` and `status = 'ACTIVE'`. Next time, a client sends `status = 'BLOCKED'`; the full pattern fails to match because `status` differs.

Without a constraint, MERGE can create a **second User with the same `userId`**. With a uniqueness constraint on `User.userId`, creation is rejected with a constraint violation. **Neither outcome accomplishes “update the existing User's status”.**

Better design:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.status = $status
RETURN u.userId AS userId, u.status AS status;
~~~

Here, `userId` is the identity key, while `status` is a **mutable** attribute. `SET` updates status as requested; that works for a “set status” operation, though out-of-order events still require ordering/versioning rules.

### 3.3. ON CREATE SET vs. ON MATCH SET

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET
    p.createdAt = datetime(),
    p.priceInCents = $price
ON MATCH SET
    p.lastSeenAt = datetime()
RETURN p.sku AS sku;
~~~

- `ON CREATE SET` runs on the creation branch.
- `ON MATCH SET` runs on the existing-match branch.
- Unconditional `SET` runs in both cases when the row is processed.

`ON CREATE SET` does **not** mean “runs strictly once in the entire lifetime of the system” if data is deleted and re-imported with the same key or if nodes with equivalent keys were created outside policy. Understand key lifecycles and constraints.

### 3.4. MERGE Does Not Merge Existing Duplicate Nodes

Suppose two nodes exist:

~~~text
(:User {userId: "U-7", name: "Lan"})  # node A
(:User {userId: "U-7", name: "Lan"})  # node B
~~~

When running:

~~~cypher
MERGE (u:User {userId: 'U-7'})
RETURN u.name AS name;
~~~

the query can return two rows for the two matching nodes. Neo4j **does not delete extra nodes, move relationships, or coalesce properties**. Data cleanup is a separate procedure that can affect paths pointing to duplicate nodes.

## 4. Do Not Confuse Duplicate Result Rows with Duplicate Nodes

A query can return an Order multiple times because the Order has multiple OrderLines:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_LINE]->(l:OrderLine)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       l.lineId AS lineId;
~~~

If Order O1 has three line items, O1 appearing in **three result rows** is completely accurate for the pattern. This **does not prove** the database contains three O1 Order nodes.

### 4.1. Counting Distinct Entities

~~~cypher
MATCH (o:Order)
RETURN count(o) AS rawMatches,
       count(DISTINCT o) AS distinctNodes;
~~~

With a simple `MATCH (o:Order)`, the two numbers match. Use this counting check in queries that **expand multiple relationships** to detect row multiplication:

~~~cypher
MATCH (o:Order)-[:HAS_LINE]->(l:OrderLine)
RETURN count(*) AS matchedRows,
       count(DISTINCT o) AS distinctOrders,
       count(DISTINCT l) AS distinctLines;
~~~

If `matchedRows` exceeds the Order count, that may be legitimate relationship multiplicity.

### 4.2. DISTINCT Changes Results, Not Stored Data

~~~cypher
MATCH (o:Order)-[:HAS_LINE]->(:OrderLine)
RETURN DISTINCT o.orderId AS orderId;
~~~

`DISTINCT` only removes duplicate result rows across the returned expressions; it **does not merge actual nodes**. If two distinct Order nodes share the same `orderId`, the query above can still return **a single ID**, causing an observer to miss real duplicates.

When debugging, count **distinct nodes** and **duplicate business keys** separately.

### 4.3. OPTIONAL MATCH Also Multiplies Rows

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[:LIKED]->(p:Post)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:User)
RETURN u.userId, p.postId, v.userId;
~~~

If the User liked 10 Posts and follows 20 Users, chaining the matches can generate up to **200 row combinations**. Those are not 200 new relationships, but the Cartesian product of the patterns.

Reduce row multiplication by computing or aggregating each set in appropriate stages; check with `count(DISTINCT ...)` when asking for distinct entity counts. Never use `DISTINCT` to hide modeling bugs because it masks real duplicates.

## 5. Find Duplicate Nodes with Cypher Before Fixing

Run **read-only** queries in authorized environments. On large graphs, full scans can consume significant resources; run on a replica/staging environment or an appropriate maintenance window.

### 5.1. Find Duplicate Customers by `customerId`

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS customerId, count(c) AS nodeCount
WHERE nodeCount > 1
RETURN customerId, nodeCount
ORDER BY nodeCount DESC, customerId
LIMIT 50;
~~~

Meaning:

- Groups by `customerId` value.
- Reports only groups with **multiple nodes sharing the key**.
- Excludes nulls so missing keys are not treated as a real business key.
- Limits output; this **does not limit the scan work** if the engine must inspect many nodes.

If `:Customer` already has an active uniqueness constraint on `customerId`, two committed nodes with this label cannot share the same non-null `customerId`. If the query still reports duplicates, verify which database, label, and constraints are actually active.

### 5.2. Find Null and Invalid Keys

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS customersWithoutId;
~~~

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
  AND trim(c.customerId) = ''
RETURN count(c) AS customersWithBlankId;
~~~

Both examples assume `customerId` is a string on non-null nodes. If data contains mixed types, calling `trim` on a non-string value can throw an error; inspect data types and classify before applying string functions.

A standard **uniqueness constraint** prevents duplicate values, yet **does not automatically require every node to have the property**. When an ID is mandatory, enforce input validation and, where supported by version/edition, consider existence or key constraints.

### 5.3. Find Keys Differing Only by Case or Whitespace

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     collect(c) AS matches
WHERE size(matches) > 1
RETURN normalizedEmail,
       size(matches) AS nodeCount,
       [c IN matches | c.customerId] AS customerIds
ORDER BY nodeCount DESC
LIMIT 50;
~~~

This is a **diagnostic query**, not a universal email normalization rule. In real business domains, review casing conventions, Unicode, whitespace, email providers, tenants, and data policies; never merge two addresses merely because they look similar.

Queries using `collect(c)` can consume considerable memory if one email group is huge. When only counts are needed, prefer `count(*)` by normalized key:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS nodeCount
WHERE nodeCount > 1
RETURN normalizedEmail, nodeCount
ORDER BY nodeCount DESC
LIMIT 50;
~~~

### 5.4. Find Duplicate Nodes Within Multi-Tenant Scope

If `customerId` is unique only **per tenant**, two Customers in different tenants must not be treated as duplicates.

~~~cypher
MATCH (c:Customer)
WHERE c.tenantId IS NOT NULL
  AND c.customerId IS NOT NULL
WITH c.tenantId AS tenantId,
     c.customerId AS customerId,
     count(*) AS nodeCount
WHERE nodeCount > 1
RETURN tenantId, customerId, nodeCount
ORDER BY nodeCount DESC
LIMIT 50;
~~~

When defining uniqueness constraints, select the exact **business identity scope**: system-wide, per tenant, per source system, or per version.

## 6. Inspect Schema: Constraints and Indexes

For Neo4j 5.x and versions supporting these commands:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

**Version note:** displayed columns, constraint types, support for existence/property-type constraints, node/relationship keys, and required privileges may vary by version or edition.

### 6.1. Uniqueness Constraint for a Single Node Key

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

This constraint prevents `:Customer` nodes from holding **two identical non-null `customerId` values**. It also supports key-based lookups in many scenarios.

**Before creating:** search for duplicate groups. If two Customers already share `customerId`, constraint creation will fail. Neo4j will not automatically pick a canonical Customer and delete extras.

### 6.2. Composite Uniqueness by Tenant

~~~cypher
CREATE CONSTRAINT customer_tenant_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

The pair `(tenantId, customerId)` is the key in this example. Different tenants may use the same `customerId` if the domain allows it.

**Do not confuse composite uniqueness with two single-property constraints.** Two separate constraints:

~~~cypher
CREATE CONSTRAINT customer_tenant_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.tenantId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT customer_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

enforce **one Customer per tenant** and **globally unique `customerId`**, which is usually wrong for multi-tenant systems. These two constraints are examples **not to apply** to that model; do not run them on a business database.

### 6.3. Regular Indexes Are Not Uniqueness Constraints

A range index on `Customer.email` speeds up filter queries, yet **does not prevent** two Customers from sharing an email.

To guarantee database-level uniqueness, you need an appropriate constraint. Relying solely on a Java “check first, then create” pattern is also unsafe when two workers write concurrently.

### 6.4. Even With Constraints, Input Validation Is Still Required

Constraints do not replace:

- Rejecting null/blank IDs.
- Normalizing strings per business contract.
- Enforcing tenant/source boundaries.
- Identifying which record to update when multiple properties change.
- Handling uniqueness errors and retries at the application layer.

If a business key is **mandatory**, evaluate node key / property existence constraints for your version/edition, and still validate inputs at the system boundary.

## 7. MERGE and Multiple Constraints: Conflicts from Non-Matching Patterns

Suppose `:User` has uniqueness constraints on both `email` and `username`:

~~~cypher
CREATE CONSTRAINT user_email_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.email IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT user_username_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.username IS UNIQUE;
~~~

The database already contains:

~~~text
User A: email = "a@example.invalid", username = "alice"
User B: email = "b@example.invalid", username = "bob"
~~~

A new request sends A's email and B's username:

~~~cypher
MERGE (u:User {
    email: 'a@example.invalid',
    username: 'bob'
})
RETURN u;
~~~

**No node matches both properties simultaneously.** MERGE cannot take email from A and username from B and fuse two Users. It attempts to create a new node, violates one or both uniqueness constraints, and fails.

Even when both values belong to the same node yet one field changed, a MERGE pattern containing both fields will fail to match and trigger a constraint conflict.

### 7.1. Choose One Primary Business Key, Then Validate Other Fields

If `userId` is the stable identifier:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

Email/username have their own constraints, so keep them out of the **MERGE key** if the domain allows them to change. When updating email, verify permissions, check uniqueness, and handle conflicts with other Users explicitly.

If there is no `userId` and email is the lookup key, define clear rules for email changes and username collisions. A single “all-properties” MERGE cannot substitute for identity resolution.

### 7.2. Never Swallow Constraint Errors and Pretend Everything Succeeded

On a constraint violation:

1. Inspect **which constraint** was violated.
2. Determine whether it is a duplicate of **the same business entity** or a conflict with a different entity.
3. Re-read by the stable primary key if needed.
4. Compare payload and owner/tenant.
5. Treat it as an idempotent duplicate only when the contract allows it.
6. If data or ownership differs, raise a conflict and investigate.

**Never** catch all uniqueness errors and return HTTP 200; doing so can mask reassigning another customer's email or violating tenant isolation.

## 8. Nulls, Empty Strings, Data Types, and Normalization

Cypher distinguishes `null` from empty strings and from values of other types. A common mistake is treating them as equivalent.

### 8.1. MERGE Rejects Null Properties in Key Maps

Example with a missing `userId`:

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u;
~~~

If `$userId = null`, MERGE throws an error because it cannot match or create a node with a null property in the MERGE pattern. Never work around this by silently converting null into the string `'null'`, which creates a **fake business key**.

Before writing:

- Validate required properties.
- Reject null/blank/wrong types with an explicit input error.
- Distinguish “missing property” from “property with a different value”.
- Ensure IDs are generated before a transaction callback that might retry.

### 8.2. Representations That Look Similar Can Be Different Keys

~~~text
"C-100"
"c-100"
"C-100 "
100
"100"
~~~

These representations do not necessarily match the same key under Neo4j value comparison. Depending on types and domain contracts, they can create multiple nodes.

If a business key is a string, normalize it **before calling MERGE**—for example, trimming, Unicode normalization, or case-folding per domain rules. Normalization must be consistent across the Java API, batch imports, CDC, and every other write path.

### 8.3. Avoid Inconsistent Inline Normalization Across Queries

Example:

~~~cypher
MERGE (c:Customer {email: toLower(trim($email))})
RETURN c;
~~~

This pattern can work if normalized email is the application's official key, but consider existing data and normalization rules carefully.

A cleaner approach is two explicit fields:

~~~text
emailOriginal    = validated input preserved for display
emailLookupKey   = normalized lookup key per policy
~~~

Then place the uniqueness constraint on the lookup key if the domain requires one account per normalized key. Avoid changing normalization rules abruptly without migrating existing data.

## 9. MERGEing an Entire Path Pattern: Easy to Create Extra Nodes

This is one of the subtlest bugs when using `MERGE` across multiple nodes and a relationship at once.

Suppose Users A and B already exist without a `FOLLOWS` edge.

### 9.1. Anti-Pattern

~~~cypher
MERGE (a:User {userId: $fromId})
      -[:FOLLOWS]->
      (b:User {userId: $toId})
RETURN a, b;
~~~

Cypher looks for the **entire pattern containing both nodes and the edge**. Because the relationship does not exist yet, the whole pattern fails to match. Without appropriate uniqueness constraints, MERGE can create **unbound parts of the pattern**, yielding duplicate Users; with constraints, it fails when trying to create nodes with already existing `userId`s.

### 9.2. Right Pattern for “If Both Users Exist, Create the Edge”

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
RETURN a.userId AS sourceId,
       b.userId AS targetId;
~~~

Here:

1. `MATCH` binds `a` and `b` to existing nodes.
2. `WHERE a <> b` prevents self-follows if required by domain rules.
3. `MERGE` only matches or creates the relationship between the already-bound nodes.

If either `a` or `b` does not exist, the query returns **0 rows** and creates no Users. The application service must check this and handle not-found errors; do not treat “no exception” as “edge created”.

### 9.3. When Both Users Should Be Created If Missing

~~~cypher
MERGE (a:User {userId: $fromId})
WITH a
MERGE (b:User {userId: $toId})
WITH a, b
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
RETURN a.userId AS sourceId,
       b.userId AS targetId;
~~~

These are **three separate MERGEs**, so the nodes are bound before the relationship is merged. For safety under concurrent writes, a uniqueness constraint on `User.userId` is required. If `fromId = toId`, the node MERGEs can still create a User before `WHERE` suppresses the edge; validate at input if self-follow requests must be rejected outright.

**Important:** even with unique nodes, duplicate relationships under concurrency must be evaluated separately per your Neo4j version and locking/idempotency strategy.

## 10. MERGEing Relationships: Keep Mutable Properties Out of the Match Key

Suppose one User follows another and the relationship status can transition from `PENDING` to `ACTIVE`.

### 10.1. Anti-Pattern: Status Property Inside the Pattern

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
MERGE (a)-[r:FOLLOWS {status: $status}]->(b)
RETURN r;
~~~

If `FOLLOWS {status: 'PENDING'}` already exists and a new request passes `status: 'ACTIVE'`, the new pattern **does not match the existing relationship**. MERGE creates a **second relationship** between the same two Users instead of updating the existing edge's status.

### 10.2. Better Pattern When Each Pair Has At Most One FOLLOWS

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
SET r.status = $status
RETURN r.status AS status;
~~~

When the domain treats **(source User, relationship type, target User)** as a single relationship, only the endpoints, direction, and type belong in MERGE; `status` is a mutable property.

**Do not treat this statement as an absolute guarantee under concurrent writers.** Neo4j does not automatically enforce “at most one FOLLOWS per pair” just because Users have unique keys. When strict invariants are needed under concurrency, design endpoint locking/relationship keys/edge identity mechanisms and test them on your target version.

### 10.3. MERGE Does Not Clean Up Existing Duplicate Relationships

If two `FOLLOWS` edges with the same pair, direction, and type already exist, MERGE can match both. `ON MATCH SET` will run on multiple matched rows, and downstream query parts can produce multiplied results.

Before claiming MERGE “fixed duplicates”, count actual relationships by source/target/type and verify consistency.

### 10.4. Relationships with Their Own Business Key

Some relationships represent **events with distinct IDs**, such as `TRANSFERRED` or `IMPORTED_AS`, allowing multiple edges between two nodes distinguished by `eventId`. In that model, “one edge per User pair” is **not** the right invariant.

Use a different pattern:

~~~text
(source)-[:TRANSFERRED {eventId: E1, amount: 10}]->(target)
(source)-[:TRANSFERRED {eventId: E2, amount: 20}]->(target)
~~~

When identity is event-based, consider a uniqueness constraint on the relationship property or a dedicated event node depending on version/edition capabilities. Do not force every relationship to be unique per endpoint pair.

## 11. Diagnosing Duplicate Relationships by Endpoints and Direction

Assume `User.userId` is already a unique key. Find pairs with multiple `FOLLOWS` edges:

~~~cypher
MATCH (a:User)-[r:FOLLOWS]->(b:User)
WHERE a.userId IS NOT NULL
  AND b.userId IS NOT NULL
WITH a.userId AS fromId,
     b.userId AS toId,
     count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN fromId, toId, relationshipCount
ORDER BY relationshipCount DESC
LIMIT 50;
~~~

Notes:

- If Users themselves have duplicate IDs, grouping by ID can merge **different physical node pairs**. Identify the real endpoint nodes before deleting extra relationships.
- Relationship direction matters: `(a)-[:FOLLOWS]->(b)` and `(b)-[:FOLLOWS]->(a)` carry distinct meanings and are not duplicates by default.
- Two relationships sharing pair and type may be valid if the domain permits multi-edges; never delete based solely on a count.

### 11.1. Inspecting Individual Relationships Between a Pair

~~~cypher
MATCH (a:User {userId: $fromId})
      -[r:FOLLOWS]->
      (b:User {userId: $toId})
RETURN elementId(r) AS diagnosticElementId,
       properties(r) AS relationshipProperties
ORDER BY diagnosticElementId;
~~~

`elementId(r)` is useful during a single diagnostic session to tell relationships apart. **Never use `elementId` as a long-term stable business key** or assume IDs survive exports, imports, or restores.

### 11.2. Using `count(*)` vs. `count(DISTINCT r)` for the Right Question

When relationship `r` is multiplied by another `MATCH`, `count(r)` counts the same relationship repeatedly. To count distinct relationship entities:

~~~cypher
MATCH (a:User)-[r:FOLLOWS]->(b:User)
OPTIONAL MATCH (a)-[:AUTHORED]->(p:Post)
WITH a, b,
     count(DISTINCT r) AS distinctFollowEdges,
     count(DISTINCT p) AS distinctPosts
RETURN a.userId AS fromId,
       b.userId AS toId,
       distinctFollowEdges,
       distinctPosts
ORDER BY distinctFollowEdges DESC
LIMIT 50;
~~~

When checking fan-out, remember `OPTIONAL MATCH` also multiplies rows; apply `DISTINCT` to the **relationship variable**, not just its `status` property.

## 12. Concurrent Writes: MERGE Does Not Replace Data Constraints

Consider two nearly simultaneous workers:

~~~text
Worker A                    Database                    Worker B
    |                           |                            |
    | -- lookup Customer K ----->|<----- lookup Customer K --|
    |         not found          |         not found         |
    | -- attempt create K ------>|<----- attempt create K ---|
    |                           |                            |
    +---------------------------+----------------------------+
~~~

**Without a constraint**, both can create nodes with the same key. **With an appropriate uniqueness constraint**, the database enforces the invariant that two nodes with the same key cannot commit; one transaction may succeed while the other waits, matches existing data, or fails depending on execution timing and version.

### 12.1. Safer Node Pattern

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

Here the business key is **immutable** and backed by a constraint. If transient contention or request-level duplicates occur, the application classifies and handles them per policy; **never** assume every worker succeeds on the first attempt.

### 12.2. “Check Then CREATE” Across Two Transactions Is a Race Condition

Anti-pattern:

~~~text
Transaction 1: MATCH User K -> 0 rows
Application:   decides creation is needed
Transaction 2: CREATE User K
~~~

Another worker can create `K` between the two steps. For atomic “find or create”, place the operation inside a transaction with `MERGE` and a matching constraint. If an invariant spans multiple steps, align the transaction boundary to the business unit of work.

### 12.3. Transaction Boundaries and Locking When Updating Relationships

Creating relationships between two nodes can contend on the endpoints or related structures. To enforce a no-duplicate-edge rule, you may need:

- A stable relationship identifier with a constraint if supported by model/version.
- An intermediate node representing the event/relationship with a unique business key.
- Write serialization by business key in the application or verified locking mechanisms.
- Testing with two or more concurrent transactions.
- Handling deadlocks and transient errors with bounded retries.

Never use two sequential `MERGE` runs as proof of race-free behavior when production runs multiple concurrent workers.

## 13. UNWIND, LOAD CSV, and Batch Imports: Duplicates from the Source

In import pipelines, duplicates can appear **within the same batch** or across batches, not only from concurrency.

Example input:

~~~json
[
  {"customerId": "C-1", "name": "An"},
  {"customerId": "C-1", "name": "An"},
  {"customerId": "C-2", "name": "Binh"}
]
~~~

When running:

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {customerId: row.customerId})
SET c.name = row.name
RETURN count(c) AS processedRows;
~~~

`processedRows` can be 3 because **three input rows were processed**, not because three nodes were created. With a uniqueness constraint and proper MERGE key, only two distinct Customers exist.

### 13.1. Deduplicate by Key Before MERGE

~~~cypher
UNWIND $rows AS row
WITH row.customerId AS customerId
WHERE customerId IS NOT NULL AND trim(customerId) <> ''
WITH DISTINCT customerId
MERGE (c:Customer {customerId: customerId})
ON CREATE SET c.createdAt = datetime()
RETURN count(c) AS distinctKeysProcessed;
~~~

The predicate assumes `row.customerId` is a string. Validate/normalize bad input types before sending them to Neo4j.

Important:

- `WITH DISTINCT` removes **rows with the same key** within the current batch; it does not replace a uniqueness constraint across multiple workers.
- If the same `customerId` appears with two different names, deduplicating by ID **does not decide which name wins**. Define a winner/merge rule upstream first.
- `count(c)` after MERGE still counts processed keys, not newly created nodes.

### 13.2. Do Not Let Input Order Silently Dictate State

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {customerId: row.customerId})
SET c.status = row.status;
~~~

If the same key appears with two different statuses, the final value depends on write/execution order. Never rely on JSON array ordering as a guaranteed business versioning mechanism.

Choose a verifiable policy: source timestamps/versions, allowed state transitions, or rejecting batches with conflicting payloads for the same key.

### 13.3. LOAD CSV Does Not Automatically Deduplicate

`LOAD CSV` reads rows from a source; it does not imply deduplication. A file containing multiple rows with the same ID requires the same MERGE rules, constraints, normalized keys, and error handling as `UNWIND`.

In imports using parallelism or transaction batching, check:

- Can the same key appear across multiple batches?
- Were constraints created before importing?
- How many rows are processed per transaction?
- If a batch fails, do replays preserve business keys and idempotency?
- Are rows silently dropped because a `MATCH` could not find an endpoint?
- Are created/matched/failed/ignored counts tracked separately?

## 14. MERGE Fails Silently Because Preceding MATCH/WHERE Left Zero Rows

The opposite of duplicates is **MERGE not running at all**:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {sku: $sku})
MERGE (c)-[:BOUGHT]->(p)
RETURN c, p;
~~~

If either Customer or Product does not exist, `MATCH` yields 0 rows, so MERGE **never executes**. The query throws no exception yet creates no relationship.

### 14.1. Distinguish “Must Already Exist” from “Create If Missing”

If both nodes **must already exist**, use `MATCH` and check the returned row count. If policy allows creating missing nodes, `MERGE` each node individually on a constrained stable key first, then `MERGE` the edge.

Never replace every `MATCH` with `MERGE` when seeing 0 rows: doing so can fabricate invalid data, such as spawning a catalog Product that does not actually exist merely because an order referenced it.

### 14.2. OPTIONAL MATCH and Misplaced WHERE

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[r:HAS_PHONE]->(p:Phone)
WHERE p.verified = true
RETURN u.userId, p.number;
~~~

Here `WHERE` attaches to `OPTIONAL MATCH` to filter the optional pattern. If rewritten as:

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[r:HAS_PHONE]->(p:Phone)
WITH u, p
WHERE p.verified = true
RETURN u.userId, p.number;
~~~

then rows with `p = null` are filtered out at `WITH/WHERE`, causing the query to return no User even though the initial `MATCH` succeeded. Any subsequent MERGE will not run either.

**Lesson:** before blaming MERGE, measure cardinality at every `MATCH`, `OPTIONAL MATCH`, `WITH`, and `WHERE` step.

## 15. Reading and Classifying Constraint Errors Properly

When the database throws an error, the application should log **allowed error categories and the operation name**, avoiding logging parameters containing emails or tokens. Exact code/message strings can vary by Neo4j/Java Driver version and constraint type.

Categories to distinguish:

| Category | Example | Action |
|---|---|---|
| **Constraint violation** | Attempting to create a User with an email held by another node | Check identity/payload, return conflict or handle duplicate properly |
| **MERGE null property** | Missing User ID | Return input error; do not retry |
| **Syntax/type error** | Wrong parameter type, invalid Cypher | Fix request/query; do not retry endlessly |
| **Transient transaction failure** | Deadlock, lock conflict recognized by driver | Retry transaction with bounded limit |
| **No matching row** | `MATCH` finds no Customer | Handle not-found; do not assume success |
| **Ambiguous commit** | Client lost response while commit may have succeeded | Re-read by stable key before replaying |
| **Permission/schema change** | Unauthorized to create constraint or label | Check privileges/migrations; do not mutate data ad hoc |

### 15.1. Do Not Retry Permanent Errors

If the uniqueness constraint on `User.email` is violated because that email belongs to another User, sending **the same request ten times** will not make the conflict vanish. Retries belong only to confirmed transient failures or explicit contention/idempotency designs.

### 15.2. Constraint Exceptions May Prove Data Protection Is Working

Sometimes an error is **proof that the constraint is doing its job**: the database rejected a transaction that would have created a duplicate key. Never “fix” it by dropping the constraint just to let an import finish if that constraint enforces a real business invariant.

The right fix is usually investigating the source data, MERGE key, or pre-existing duplicates prior to migration.

## 16. Java Driver: Stable MERGE and Proper Result Handling

Java applications should use **parameters** instead of concatenating strings into Cypher, and stabilize business keys before invoking managed transactions.

Example Customer upsert service using a composite key:

~~~java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerUpsertService {
    public record CustomerKey(
        String tenantId,
        String customerId
    ) {}

    private final Driver driver;

    public CustomerUpsertService(Driver driver) {
        this.driver = driver;
    }

    public CustomerKey upsert(
            String tenantId,
            String customerId,
            String displayName) {

        if (tenantId == null || tenantId.isBlank()
                || customerId == null || customerId.isBlank()
                || displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Invalid customer input");
        }

        String cypher = """
            MERGE (c:Customer {
                tenantId: $tenantId,
                customerId: $customerId
            })
            ON CREATE SET c.createdAt = datetime()
            SET c.displayName = $displayName
            RETURN c.tenantId AS tenantId,
                   c.customerId AS customerId
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Map.of(
                    "tenantId", tenantId,
                    "customerId", customerId,
                    "displayName", displayName
                ));
                var row = result.single();

                return new CustomerKey(
                    row.get("tenantId").asString(),
                    row.get("customerId").asString()
                );
            });
        }
    }
}
~~~

This example assumes the `(tenantId, customerId)` constraint is already deployed, all write paths share the same policy, and both input IDs are normalized per contract.

### 16.1. What This Example Protects Against—and What It Does Not

**Protected:**

- No string concatenation of inputs into query text.
- Uses a stable key inside MERGE.
- Upserts the node and sets properties in a single managed transaction.
- Maps results into a DTO inside the transaction callback.
- Driver automatically retries eligible transient errors.

**Not solved automatically:**

- Name update ordering when two events arrive out of order.
- Conflicts when another constraint (such as email/username) is violated.
- Duplicates that existed before the constraint was created.
- Side effects on external systems like email/message brokers.
- Consistent input normalization across multiple services.

### 16.2. Managed Transaction Callbacks Can Re-Execute

In the Java Driver, `session.executeWrite(...)` may re-run the callback on eligible transient failures. Therefore **never** generate a fresh UUID for a business key inside the callback, send emails, or call payment APIs inside the callback.

When using explicit transactions via `session.beginTransaction()`, transaction-level retry policies differ from managed transactions; the application must handle errors and idempotency explicitly.

### 16.3. Do Not Dump Full Exceptions or Parameters into Logs

When debugging constraint failures in production, parameter maps may contain emails or sensitive data. Prefer logging:

~~~text
operation=customer.upsert
errorCategory=CONSTRAINT_CONFLICT
tenantAlias=approved-safe-code
durationMs=18
~~~

Never log raw Cypher parameter maps, tokens, or full `Node`/`Record` objects. For sensitive data, rely on correlation IDs and access-controlled tracing rather than printing business keys onto shared dashboards.

## 17. Spring Data Neo4j: Repository `save` Does Not Replace Uniqueness

In Spring Data Neo4j, entities commonly use `@Node`, `@Id`, `@GeneratedValue`, `@Relationship`, and repositories. Yet `save(...)` working does not mean the database automatically knows which business key is unique.

An entity receiving a newly generated technical ID on each import can create two nodes for the same `externalCustomerId` if the application lacks a database constraint or stable lookup/upsert strategy.

### 17.1. Choose IDs and Business Keys Deliberately

- A **technical ID** can suit internal entity lifecycle management within one service.
- A **business key** identifies the same entity across imports, CDC, API retries, and integrations.
- If a business key must be unique, enforce a constraint in Neo4j.
- If an entity spans multiple labels or tenants, define the exact constraint scope.
- When using DTOs/repositories with nested relationships, verify mapping behavior so unintended new related nodes are not created.

Never treat a Java entity `@Id` annotation as proof that a `CREATE CONSTRAINT` DDL statement was executed in the database. Separate schema migration and verification are required.

### 17.2. Transaction Boundaries in Application Services

A use case creating an Order, OrderLines, and relationships atomically should wrap the steps in a properly configured Spring-managed transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerImportWorkflow {
    private final CustomerRepository repository;

    public CustomerImportWorkflow(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void handle(CustomerImportCommand command) {
        repository.upsertByBusinessKey(command);
        repository.attachRelationships(command);
    }
}
~~~

This is an **architectural example**, assuming `CustomerRepository` and `CustomerImportCommand` are defined. It will not run without wiring repositories, transaction manager, and schema.

If a repository query embeds `status` in its MERGE key, `@Transactional` cannot turn the broken pattern into a valid one. On constraint violations, classify errors at the service layer rather than swallowing exceptions and letting transactions partially commit unexpectedly.

### 17.3. Repositories Creating Duplicate Relationships

If each `save` builds fresh relationship wrapper objects without matching existing relationship identities, the application may create or map data unexpectedly. Inspect the generated queries, Spring Data Neo4j version, and relationship entity identity when modeling relationships with properties/IDs.

**Never assume** every repository write behaves identically to a hand-written `MERGE (a)-[:REL]->(b)`. Behavior depends on mapping and graph persistence rules.

## 18. MERGE and Additive Commands: Dedicated Idempotency Is Required

Duplicate **business side effects** can still occur even with zero duplicate nodes:

~~~cypher
MERGE (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + 100;
~~~

If the same command commits twice, points increase by **200**, even though there is still only one Account. MERGE identifies the **node**, not the **points-addition command**.

### 18.1. Using a Receipt/Ledger Keyed by `commandId`

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

Pattern for recording a new command:

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.points = coalesce(a.points, 0) + $delta
SET cmd.resultPoints = a.points
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.commandId AS commandId,
       cmd.resultPoints AS resultPoints;
~~~

The receipt and Account update occur in **the same transaction**. If `commandId` already exists and the uniqueness constraint rejects `CREATE`, that transaction cannot commit the addition.

After an ambiguous error/timeout, the application looks up the receipt by `commandId`, verifies `accountId`/delta/payload, and decides whether to return the prior result or retry. Never generate a new `commandId` for the same logical operation.

### 18.2. Do Not MERGE a Receipt and Unconditionally SET the Delta

Anti-pattern:

~~~cypher
MERGE (cmd:AppliedCommand {commandId: $commandId})
WITH cmd
MATCH (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + $delta;
~~~

Even if the receipt already exists, `SET` still adds the points again. You need a transaction boundary that applies the business effect **only for a new command**, rather than assuming “using MERGE makes the whole query idempotent”.

## 19. Checking EXPLAIN/PROFILE When MERGE Is Slow

A semantically valid MERGE can still be slow if indexes are missing, many nodes are scanned, or the input generates many rows.

### 19.1. EXPLAIN to Inspect the Plan Without Executing Writes

~~~cypher
EXPLAIN
MERGE (c:Customer {customerId: $customerId})
RETURN c.customerId;
~~~

Check whether the planner uses an index/constraint for the key lookup; inspect estimated cardinality and input rows. With proper constraints and indexes, Neo4j can typically locate keys much faster than scanning the entire label.

### 19.2. PROFILE Executes the Real Statement

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})
RETURN c.customerId;
~~~

Here `PROFILE` is read-only. However, if `PROFILE` is prepended to `MERGE`, `CREATE`, `SET`, or `DELETE`, **it executes the write side effects**. Never run `PROFILE` on a write query in production just to inspect the query plan.

### 19.3. Investigate Cardinality Instead of Blindly Adding Indexes

If an `UNWIND` query receives 50,000 rows, MERGE still runs per row. If a preceding `MATCH` multiplies rows, far more write attempts may execute than expected.

Measure each stage with a safe read query on test inputs:

~~~cypher
UNWIND $rows AS row
RETURN count(*) AS inputRows,
       count(DISTINCT row.customerId) AS distinctCustomerIds;
~~~

Distinct counts are diagnostic only; if multiple rows share an ID with conflicting payloads, classify the source conflict rather than silently discarding rows.

## 20. Safe Duplicate Cleanup Workflow

When duplicate data is discovered, **do not immediately run DETACH DELETE**. An extra node may carry important relationships or properties that the canonical node lacks.

### 20.1. Step 1 — Isolate and Stop the Source of Duplicates

- Identify the label, key, tenant/source, and time window of occurrence.
- Find which API, batch job, or CDC pipeline writes MERGE without constraints or with the wrong key.
- Pause or restrict the duplicate-producing write path per operational procedures.
- Take an appropriate backup/restore point; consider testing on a staging clone first.
- Restrict access to sensitive data in investigation logs.

Never clean up duplicates while an unfixed writer continues creating new ones.

### 20.2. Step 2 — Choose the Canonical Node by Business Rules

For a duplicate Customer group, choose the canonical node based on:

- Trusted source ID and creation timestamp.
- Traceability to orders/transactions.
- Completeness of properties and relationships.
- Records already referenced by external systems.
- Audit and history retention rules.

Never pick “the first node” arbitrarily and delete the rest. One node may hold unique orders or relationships treated as business evidence.

### 20.3. Step 3 — Inventory Relationships and Properties Before Merging

Illustrative query for a single key:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[r]-()
RETURN elementId(c) AS diagnosticNodeId,
       labels(c) AS labels,
       properties(c) AS nodeProperties,
       count(r) AS attachedRelationships;
~~~

**Run only in authorized environments/scopes** because `properties(c)` may contain PII and all node properties. Handle output over secure channels; when sharing reports, expose only approved fields.

If source/target/relationship type details are needed, continue inventorying with read-only queries; never delete before knowing where every edge must move.

### 20.4. Step 4 — Design Semantic-Preserving Relationship Transfers

“Merging two nodes” in a property graph typically involves:

1. Selecting the canonical node.
2. Resolving property conflicts.
3. Identifying which relationships must be transferred to the canonical node.
4. For each relationship, checking type, direction, properties, and allowed multiplicity.
5. Ensuring no unintended self-loops or domain-invalid duplicates are created during transfer.
6. Preserving history if required for auditing.
7. Deleting the redundant node only after verifying data preservation.

If using utility procedures (such as graph utility libraries), verify **version, behavior, merge policies, and privileges** in a test environment. Never assume a generic “merge nodes” procedure resolves every domain conflict properly.

### 20.5. Step 5 — Test on a Clone and Verify Invariants

For complex relationship graphs, build a test simulation:

~~~text
Customer C1 (canonical) --[:PLACED]--> Order O1
Customer C1 (duplicate) --[:PLACED]--> Order O2
Customer C1 (duplicate) --[:HAS_CASE]-> Case K
~~~

After merging, verify that canonical C1 retains all required business links to O1/O2/K, with no inverted directions or lost historical attributes.

Verify:

- Entity counts per business key.
- Relationship counts per type/direction.
- Invariants such as every Order belonging to a valid Customer.
- Reconciliation counts against source tables/systems.
- Critical application read queries.
- Impact of constraints created after cleanup.

### 20.6. Step 6 — Create Constraints and Deploy Fixed Writes

Once data is cleaned and free of conflicts:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Apply the constraint at the exact right scope; if the key is `(tenantId, customerId)`, create the composite constraint instead of constraining `customerId` alone.

**`IF NOT EXISTS` does not guarantee that an existing schema matches your intent.** Run `SHOW CONSTRAINTS` after migration to verify names, labels, properties, and types; “no error thrown” is insufficient if the existing schema differs from expectations.

## 21. Production Runbook for MERGE and Constraint Incidents

Follow this sequence:

### 21.1. Identification

1. Capture the operation name and safe error category (never log PII).
2. Identify the database, version, timestamp, and affected endpoints.
3. Distinguish a single bad request from widespread import/API failures.
4. Verify whether real duplicate writes occurred or query results were merely multiplied.
5. Inspect active constraints/indexes in the database rather than inferring from migration source files.

### 21.2. Isolation

1. Reproduce with synthetic input matching the real payload shape.
2. Run read queries counting duplicates by business key.
3. Check key normalization and nulls.
4. Run `EXPLAIN` to inspect the plan and cardinality.
5. Check whether multiple workers, batches, or CDC streams are writing concurrently.
6. For relationships, identify which direction, type, and properties appear in MERGE.
7. For multi-`MATCH` queries, measure row counts after every step.

### 21.3. Remediation

1. Fix the MERGE key to match the domain identity.
2. Add the proper constraint after resolving existing duplicates.
3. Fix concurrency, retries, and idempotency.
4. Clean up legacy data via a change plan, backups, and testing.
5. Test request replays, two concurrent workers, and same-key conflicting payloads.
6. Monitor constraint errors, duplicate counts, and invariants post-deploy.

### 21.4. Do Not Do Without a Plan

- Dropping constraints just to “make errors stop”.
- Running `DETACH DELETE` on supposedly extra nodes without inventorying relationships.
- Re-importing with newly generated business IDs to avoid collisions.
- Catching all exceptions and returning success.
- Turning on unbounded retries for schema or validation errors.
- Pointing the app to a different database and ignoring mismatched records.
- Running `PROFILE` on write statements against live data just to debug.

## 22. Regression and Concurrency Testing

An effective test suite verifies **final database state**, not just HTTP 200 responses.

| Scenario | Expected outcome |
|---|---|
| MERGE new node with valid ID | Exactly one node for that business key |
| MERGE same ID a second time | No second node created |
| Two threads MERGE the same ID concurrently | Constraint prevents two nodes with the same key from committing |
| Null/blank key | Input rejected or handled per policy; no fake key created |
| Same ID, changed status | Existing node updated; no new node created |
| Same ID across two tenants | Follows composite key rules (allowed or rejected by design) |
| MERGE User–FOLLOWS–User when both Users exist | No extra Users created |
| MERGE relationship with changed status | No duplicate edge created just because status changed when domain allows one edge |
| `UNWIND` input with 10 rows sharing one key | Dedupe/match counts accurate; 10 nodes not created |
| Retried points-addition command | Business effect applied once per `commandId` |
| Query spanning multiple OrderLines | Do not report duplicate Orders just because multiple rows return |
| Creating constraint on existing duplicates | Migration fails cleanly without auto-deleting data |
| Duplicate cleanup with relationships | All links and invariants preserved after transfer |
| Two workers update the same entity | Verify contention, lost updates, and versioning if required |

### 22.1. Two-Thread Test Without Improper Session Sharing

In the Java Driver, `Driver` is meant to be reused, whereas `Session` is short-lived and must not be shared across threads. Give each test worker its own `Session`/transaction.

Run concurrent writes with the same `customerId` repeatedly, then verify:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN count(c) AS nodeCount;
~~~

Expect `nodeCount = 1` when identity contracts and constraints are properly configured. Also verify all properties and relationships; `nodeCount = 1` alone does not prove other properties were not overwritten incorrectly.

### 22.2. Testing Multi-Relationship Paths

With User A following User B, execute the `FOLLOWS` creation operation repeatedly, both sequentially and concurrently. Afterward:

~~~cypher
MATCH (a:User {userId: $fromId})
      -[r:FOLLOWS]->
      (b:User {userId: $toId})
RETURN count(r) AS relationshipCount;
~~~

Expect `count = 1` **if** the domain mandates one `FOLLOWS` edge per pair and concurrency protection has been designed accordingly.

### 22.3. Prevent Accidental Deletion in Cleanup Tests

All tests using `DETACH DELETE`, relationship rewrites, or node merges must run in an isolated test database with synthetic IDs and data. Never use production customer data when testing duplicate cleanup.

## 23. Misconceptions to Avoid

**“MERGE is equivalent to a uniqueness constraint.”** False. MERGE is a pattern match-or-create operation; a constraint is an invariant enforced at write time.

**“Two nodes with identical properties automatically merge during MERGE.”** False. MERGE does not move relationships or delete extra nodes.

**“Put every property in MERGE to ensure an exact match.”** Wrong for mutable properties such as `status`, `name`, `price`, or `lastSeenAt`.

**“MERGEing a path only creates the missing relationship.”** Unreliable when nodes are not already bound outside the full path pattern.

**“Two rows with the same `customerId` mean two nodes exist.”** May simply be graph join expansion across multiple relationships.

**“DISTINCT fixed the duplicate data.”** False. It only affects the returned result set.

**“Having an index prevents duplicates.”** False; regular indexes do not enforce uniqueness.

**“A constraint threw an error, so drop the constraint.”** False; the error usually signals either a protected invariant or bad input.

**“MERGEing a relationship with `status` in the map updates the old status.”** False; a changed status alters the pattern and can create a new edge.

**“MERGE Account and increment counter is idempotent.”** False; each commit increments the counter again.

**“`@Transactional` or `executeWrite` always prevents duplicates.”** False; transaction atomicity/retries do not replace business keys and constraints.

**“Deleting an extra node is safe if the email matches.”** False; you can lose relationships, audit trails, and valid data.

## 24. Applied Exercises

### Exercise 1 — Duplicate Caused by Status

Database contains:

~~~text
(:User {userId: "U1", status: "ACTIVE"})
~~~

Application runs:

~~~cypher
MERGE (:User {userId: 'U1', status: 'BLOCKED'});
~~~

**Question:** Without a uniqueness constraint, what can happen?

**Answer:** A second User with the same `userId` and status `BLOCKED` can be created because the full pattern does not match the `ACTIVE` User. You should MERGE by `userId` and then `SET` `status`, backed by a uniqueness constraint on the key.

### Exercise 2 — Constraint Exists, Yet MERGE Still Fails

`User.userId` has a uniqueness constraint. User U1 exists with status `ACTIVE`; MERGE with U1 and status `BLOCKED` throws an error.

**Question:** Is the constraint malfunctioning?

**Answer:** No. The constraint correctly blocks creating a second User with the same `userId`. The MERGE pattern is misusing a mutable property as part of the match key.

### Exercise 3 — Same Order Returned Twice in a Query

An Order has two OrderLines, and a query returning Order after matching `HAS_LINE` returns two rows.

**Question:** How do you tell duplicate nodes apart from cardinality?

**Answer:** Compare `count(DISTINCT o)` against `count(o)`/row count; check for duplicate business keys in a standalone `MATCH (o:Order)` query.

### Exercise 4 — MERGEing the Whole Pattern

Users A and B already exist without `FOLLOWS`. A single MERGE over the full pattern of both nodes and the relationship triggers a uniqueness error.

**Question:** How do you fix the query?

**Answer:** `MATCH` or `MERGE` each User individually by its constrained key first, then `MERGE` the relationship between the two bound variables.

### Exercise 5 — Relationship Changing Status

A `FOLLOWS` edge with status `PENDING` exists, and later a MERGE runs with status `ACTIVE`.

**Question:** Why can two relationships appear?

**Answer:** `status` is part of the MERGE pattern, so the existing edge does not match. MERGE by endpoints and type, then `SET status`, plus concurrency protection if only one edge is allowed.

### Exercise 6 — Multi-Tenant

Customer ID `C1` appears in both tenant `T1` and tenant `T2`.

**Question:** Should the uniqueness constraint cover one field or two?

**Answer:** If business keys are unique only per tenant, use composite uniqueness `(tenantId, customerId)`. A globally unique constraint on `customerId` alone would reject valid cases.

### Exercise 7 — Null in MERGE

A batch import contains a row missing `externalId`.

**Question:** Should you use `coalesce(row.externalId, 'unknown')` to avoid errors?

**Answer:** Usually no. That collapses multiple rows missing IDs onto the same fake key and corrupts data by merging unrelated records. Validate, classify, quarantine invalid rows, or assign IDs per source contract before MERGE.

### Exercise 8 — Retrying a Points Addition

An API MERGEs Account and runs `SET points = points + 50`. The client times out and retries.

**Question:** Can 100 points be added even with only one Account node?

**Answer:** Yes. You need a stable `commandId`, a receipt with a uniqueness constraint, and the Account update in the same transaction.

### Exercise 9 — Importing 1,000 Rows

A batch has 1,000 rows containing only 800 distinct `customerId`s; `RETURN count(c)` after MERGE reports 1,000.

**Question:** Were 1,000 new Customers created?

**Answer:** You cannot conclude that. The count reflects processed output rows; count distinct nodes by business key, inspect duplicate keys, and track created vs. matched counts separately.

### Exercise 10 — Quick Cleanup with DETACH DELETE

Two Customers share the same email, yet one node holds indirect `OrderLine` links through `Order`.

**Question:** Is it safe to delete the newer node?

**Answer:** Not until you determine the canonical node, properties, and every relationship that must be preserved. Back up, test edge migration, verify invariants, and delete only under an approved change plan.

## 25. Pre-Closure Incident Checklist

- [ ] Confirm whether duplicates are **nodes**, **relationships**, or only **multiplied result rows**.
- [ ] Document the business key, tenant/source scope, and normalization rules.
- [ ] Check nulls, blanks, types, and casing/whitespace.
- [ ] Inspect `SHOW CONSTRAINTS` and `SHOW INDEXES` in the running database.
- [ ] MERGE uses only stable identity properties—never mutable `status`/`name`/`lastSeenAt` keys.
- [ ] For paths, bind nodes first, then MERGE the relationship.
- [ ] For relationships, verify how many edges the domain permits per pair/direction/type.
- [ ] Check cardinality across `MATCH`, `OPTIONAL MATCH`, `WITH`, and `UNWIND`.
- [ ] Confirm appropriate uniqueness constraints exist before allowing concurrent writers.
- [ ] Java Driver / Spring Data Neo4j properly handle transient failures, constraint conflicts, and ambiguous commits.
- [ ] Use command receipts if additive/event writes must apply at most once.
- [ ] For cleanup, ensure backups, canonical rules, and relationship/property inventories exist.
- [ ] Run both sequential and concurrency tests, including conflicting payloads and retries.
- [ ] Confirm no sensitive data is logged in parameters, exceptions, or diagnostic queries.
- [ ] Reconcile post-fix data and document the root cause that introduced duplicates.

## 26. Key Takeaways

**MERGE in Neo4j matches or creates a specified pattern**; it is neither a duplicate-merging tool nor a replacement for **uniqueness constraints**. Use **stable business keys**, keep mutable properties out of MERGE keys, and when working with paths, **bind nodes first before MERGEing relationships**. Duplicate nodes, duplicate relationships, and multiplied result rows each require distinct diagnostic techniques.

When constraint errors happen, never drop constraints or retry blindly: inspect the key, scope, payload, and concurrent write timing. For batch imports, normalize and deduplicate from the source; with the Java Driver or Spring Data Neo4j, keep transaction boundaries and error handling explicit; for additive operations, use **`commandId`/receipts to prevent double-application**. For existing duplicates, **inventory and preserve relationships before deleting nodes**, validate the graph in a test environment, and add long-term protective constraints.
