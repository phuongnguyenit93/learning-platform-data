# Business Keys, External Identifiers, and Limits of Internal Identifiers

## 1. Objectives and Context

In Neo4j's **property graph**, a **node** has its own identity, can carry multiple labels and multiple properties, and connects to other nodes via **relationships**. When an application reads, ingests, updates, or synchronizes a graph, the critical question is: **How do we know two records refer to the same entity?**

This lesson belongs to the **Graph Elements** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module covers modeling connected data, querying relationships and paths with **Cypher**, designing **indexes and constraints**, tuning queries, ingesting data, and integrating with **Neo4j Java Driver** or **Spring Data Neo4j**. Choosing the right identifiers is the foundation for all of those tasks.

After this lesson, you will be able to:

1. Distinguish **business keys**, **external identifiers**, and **internal identifiers** managed by Neo4j.
2. Explain why two nodes with identical properties can still be **two distinct nodes**, and why `elementId()` should not become a long-term API key.
3. Choose durable keys for entities such as `Person`, `Customer`, `Order`, `Product`, or events with their own identities.
4. Create **uniqueness constraints** on single or composite keys and use `MERGE` more safely during data ingestion.
5. Design mappings from multiple source-system IDs to **one canonical entity** in the graph.
6. Handle missing, duplicate, mutable, or tenant/source-scoped identifiers.
7. Incorporate business identifiers into Cypher queries, Java Driver code, and Spring Data Neo4j models.

## 2. Three Types of Identifiers to Distinguish

Suppose the system stores a customer named **An**:

```text
(:Customer {
  customerId: 'CUST-00042',
  crmId: 'CRM-872',
  fullName: 'Nguyễn An'
})
```

At any given time, Neo4j also has a technical identifier for that node, readable via `elementId(n)`. These three values serve three different purposes:

| Concept | Who Issues/Manages It? | Example | What Is It Used For? |
| --- | --- | --- | --- |
| **Business key** | Application system or business domain | `customerId = 'CUST-00042'` | Identifying the customer across the data lifecycle, APIs, and data exchange |
| **External identifier** | Source/partner system | `crmId = 'CRM-872'` | Linking the Neo4j record to a record in CRM |
| **Neo4j internal identifier** | Neo4j database | Value returned by `elementId(n)` | Referencing an element in suitable technical contexts, short-lived inspection/queries |

**A single value can play multiple roles**, depending on the data contract: if CRM is the primary system of record for identity and CRM IDs are guaranteed stable, that ID can serve as an application's business key. However, when multiple systems participate, proactively separate the **canonical application ID** from **per-source IDs**.

Do not assume "two records with the same name Nguyễn An" are the same person, or "two records with different emails" are two different people. **Name/email are descriptive properties**, whereas entity resolution must rely on trustworthy keys and business rules.

## 3. Node Identity Differs from Property Values

The following two node-creation commands create **two separate graph elements**:

```cypher
CREATE (:Person {fullName: 'Nguyễn An'});
CREATE (:Person {fullName: 'Nguyễn An'});
```

Even though both nodes share the same label and property, they do not merge automatically. Conversely, updating a node's `fullName` from `'Nguyễn An'` to `'Nguyễn Văn An'` keeps it **the exact same node**.

### 3.1. What Constitutes Entity Identity?

In a business domain, identity should answer:

- Is this **the same person** after changing their name, email, or phone number?
- Is this **the same order** after its status transitions from `PENDING` to `SHIPPED`?
- Is this **the same product** after its display name or selling price changes?
- Is this **the same transaction** when an ingestion job is rerun?
- Could an ID appear across **two different tenants** or **two different source systems**?

A suitable key property generally needs a **clearly defined uniqueness scope**, sufficient **stability**, **lookup capability**, and **enforcement via data rules**.

### 3.2. Natural Keys vs. Application-Assigned Keys

Two common categories:

| Key Type | Example | Advantages | Limitations |
| --- | --- | --- | --- |
| **Natural key** | Corporate tax ID within a specific regulatory jurisdiction; ISBN of a book edition | Meaningful outside the system | Can change, be reissued, have exceptions, or be unique only within a narrow scope |
| **Application-assigned / surrogate key** | `customerId` as a UUID or service-generated code | Less coupled to changes in descriptive attributes | Requires an issuance mechanism, deduplication, and mapping maintenance |

In this lesson, "business key" refers to the **long-lived identifier used by the application to identify an entity**, and it does not have to be a human-readable string. A UUID issued by the application and stored as `customerId` can still be a durable identifier for APIs and integrations.

**Avoid using as default keys:** person names, product names, mutable emails, phone numbers, addresses, or values shareable across multiple entities. These fields can be indexed for searching, but convenient lookup is **not** identity guarantee.

## 4. Limits of Neo4j Internal Identifiers

Neo4j provides functions related to graph element identity:

```cypher
MATCH (p:Person {personId: 'P001'})
RETURN
  p.personId AS businessId,
  elementId(p) AS technicalElementId;
```

`elementId(p)` returns **an element identifier string provided by Neo4j**. That value is useful for short-lived technical operations, but **does not carry a stability contract like a business ID** when data changes, is exported/imported, or is accessed across different times/transactions.

### 4.1. `elementId()` Is Not a Durable Business Key

By Neo4j's contract, `elementId()` guarantees uniqueness of an element **within the scope of a transaction**; do not infer from it a permanent immutability guarantee across transactions. Specifically:

- When **deleting and recreating** a node/relationship, the new element is a different technical entity even if it carries identical business data.
- When **copying, recreating, exporting/importing, or migrating** a graph, do not assume `elementId()` values remain identical.
- Applications **must not parse internal structure** inside the `elementId()` string to extract numeric IDs, storage slots, database names, or creation order.
- Using `elementId()` in URLs/APIs such as `/customers/{elementId}` risks breaking old links after a data migration.

Therefore, APIs should accept an application-managed key:

```text
GET /customers/CUST-00042       ← Business ID
GET /orders/ORDER-2026-00017    ← Business ID
```

Displaying `elementId()` in Neo4j Browser or diagnostic tools is fine; the problem is **treating it as a long-term identity contract** for external systems.

### 4.2. `id()` and Version Compatibility

In many Neo4j versions, the legacy `id(n)` function returns an **internal numeric identifier**. In modern Cypher versions, `id()` is considered **legacy/deprecated**; do not design new applications around it. Numeric IDs can be **reused** after an element is deleted, making them especially dangerous if stored in external systems as permanent keys.

Example solely for recognizing old code in legacy queries:

```cypher
// Only use if the running Neo4j version still supports id()
MATCH (p:Person)
RETURN id(p) AS legacyInternalId
LIMIT 5;
```

When working with newer versions, check the documentation for supported functions; whether using `id()` or `elementId()`, **internal identifiers never replace business keys**.

### 4.3. Why Not Transform `elementId()` Yourself?

Do not do this:

```text
elementId = "..." 
→ split string, extract numeric part
→ store as customerId
→ send to another system
```

Internal formatting is not a public business-ID protocol. Treat `elementId()` as an **opaque string**: read or compare it when needed in supported contexts, without parsing or redefining it.

## 5. External Identifiers: Always Specify Source and Scope

A customer can appear simultaneously in a CRM, a customer support system, and an e-commerce platform:

```text
CRM:         customerId = "42"
Support:     contactId  = "42"
Commerce:    buyerId    = "C-4200"
```

The two `'42'` values across two systems **do not necessarily** represent the same person. The ID string alone is not enough: you must know **which system issued it**.

### 5.1. Namespaced External Keys

Instead of storing only `externalId`, use a composite key:

```text
(sourceSystem, externalId)
('crm',     '42')
('support', '42')
('shop',    'C-4200')
```

Each pair can be unique within its source system's scope. If data is also partitioned by enterprise customer (*tenant*), you may need:

```text
(tenantId, sourceSystem, externalId)
('TENANT-A', 'crm', '42')
('TENANT-B', 'crm', '42')
```

That is a **composite key**: uniqueness is determined by the **combination of values**, not each value in isolation.

### 5.2. Two Ways to Represent External IDs in a Graph

**Approach A – Properties on the main node** when there are few sources and contracts are fairly stable:

```cypher
(:Customer {
  customerId: 'CUST-00042',
  crmId: 'CRM-872',
  commerceId: 'BUY-390'
})
```

Advantage: easy to look up in small applications. Drawback: as you add more providers, multiple accounts per source, or ID change history, the node accumulates source-specific properties.

**Approach B – Identity mapping nodes** when one entity has many external IDs:

```text
(:ExternalIdentity {source: 'crm', externalId: 'CRM-872'})
                     |
                     | [:IDENTIFIES]
                     v
          (:Customer {customerId: 'CUST-00042'})
                     ^
                     | [:IDENTIFIES]
                     |
(:ExternalIdentity {source: 'shop', externalId: 'BUY-390'})
```

In Approach B, each `ExternalIdentity` is a mapping that can also store `firstSeenAt`, `verifiedAt`, or source status. The business key `Customer.customerId` remains the canonical identifier used by the application in relational queries.

**Never automatically merge** two customers solely because of matching name/email. Concluding that two external IDs point to the same customer requires sufficiently reliable reconciliation rules, because a mistaken mapping merges data belonging to two different people.

## 6. Constraints: Identifiers Protected by Data Rules

Merely writing `personId` in a property **does not make Neo4j automatically enforce uniqueness**. Repeated `CREATE` statements can create two nodes with the same `personId`. To let the database protect the key, apply an appropriate **uniqueness constraint**.

### 6.1. Unique Key on a Single Property

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Meaning: there cannot be **two nodes carrying the `Person` label** with the same `personId` value while the constraint is active.

Example:

```cypher
CREATE (:Person {personId: 'P001', fullName: 'An'});
```

If `:Person {personId: 'P001'}` already exists and the constraint above is active, attempting to create another `Person` node with the same `personId` will be rejected.

**Scope limit:** The `Person.personId` constraint applies to nodes **carrying the `Person` label**. A node carrying only `:Customer` without `:Person` is outside this scope. Neo4j does not treat `Customer` as a "sub-label" of `Person`.

### 6.2. Uniqueness Does Not Yet Require Property Existence

A uniqueness constraint means **"existing key values cannot collide"**, not necessarily that **every node has the key property**.

For example, with only a uniqueness constraint on `Person.personId`, the following node can exist **without `personId`**:

```cypher
CREATE (:Person {fullName: 'Unidentified Person'});
```

To require both **existence** and **uniqueness**, evaluate property existence constraints or node key constraints and the support conditions of your Neo4j version and edition.

Application options:

- Validate required IDs **before issuing Cypher**.
- Use appropriate database constraints to safeguard data integrity.
- Define explicit rules for unverified records instead of assigning colliding dummy IDs.

### 6.3. Composite Keys for Multi-Tenant Data

When `customerId` is unique only **within a single tenant**, use:

```cypher
CREATE CONSTRAINT customer_tenant_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

Now:

```text
(:Customer {tenantId: 'TENANT-A', customerId: '42'})
(:Customer {tenantId: 'TENANT-B', customerId: '42'})
```

can coexist because the two **combinations** differ.

When operating on a customer, you must use the **full composite key**:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c;
```

Using only `customerId = '42'` could match customers from **multiple tenants**, causing unauthorized access or updates to the wrong entity.

**Note:** A composite uniqueness constraint does not by itself resolve records **missing one of the key components**. The application must validate all key components; consider node key/existence constraints where supported.

### 6.4. Composite Keys for External Data Sources

With `ExternalIdentity` nodes:

```cypher
CREATE CONSTRAINT external_identity_unique IF NOT EXISTS
FOR (x:ExternalIdentity)
REQUIRE (x.source, x.externalId) IS UNIQUE;
```

This constraint protects an ID within **a specific source**; it does not assert that the same ID string in another source is the same entity.

For multi-tenant systems, you can extend it to `(x.tenantId, x.source, x.externalId)`; choose the scope matching your data contract.

### 6.5. Inspecting Current Constraints and Indexes

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

A uniqueness constraint is typically backed by an index mechanism to enforce/look up keys. Do not add redundant indexes without checking existing ones. On large datasets, distinguish **keys used to identify entities** from **columns used for report filtering**; not every filterable field needs uniqueness.

## 7. Using MERGE to Ingest Data by Accurate Identity

### 7.1. `CREATE` and `MERGE` Do Not Mean the Same Thing

`CREATE` always creates a new element:

```cypher
CREATE (p:Person {
  personId: 'P001',
  fullName: 'An'
})
RETURN p;
```

`MERGE` searches for a matching pattern; if none is found, it creates one:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName,
              p.createdAt = datetime()
RETURN p;
```

When re-ingesting `personId = 'P001'`, `MERGE` finds the existing node **instead of creating another**, provided the pattern matches. To guarantee uniqueness under concurrent writes, a uniqueness constraint on `Person.personId` is required.

### 7.2. Put Only Stable Keys in the MERGE Pattern

Avoid putting mutable fields like name/email into the identity pattern:

```cypher
// Prone to attempting to create another node when the name changes
MERGE (p:Person {
  personId: $personId,
  fullName: $fullName
})
RETURN p;
```

For instance, the existing node has `personId = 'P001'` and `fullName = 'An'`; the source updates it to `fullName = 'Nguyễn An'`. The pattern above **does not match** the existing node because it requires both ID and name. Consequence:

- Without a constraint: may create **a duplicate node for the same business entity**.
- With a uniqueness constraint: may fail with a constraint conflict instead of updating the right node.

Solution:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
SET p.fullName = $fullName,
    p.updatedAt = datetime()
RETURN p.personId AS personId, p.fullName AS fullName;
```

`MERGE` identifies **which person**; `SET` specifies **current properties to update**.

### 7.3. For Composite Keys, Include All Key Components in MERGE

```cypher
MERGE (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = $fullName
RETURN c;
```

This lets a sync job distinguish customer `'42'` of `TENANT-A` from customer `'42'` of `TENANT-B`.

**Important:** Before running, ensure `$tenantId` and `$customerId` are not `null`. `MERGE` with a `null` key property can raise errors; normalize/filter out records missing keys before writing.

### 7.4. MERGE Does Not Clean Up Pre-Existing Duplicate Data

If the graph already contains **two `Person` nodes with the same `personId`**, switching to `MERGE` will neither merge those two nodes nor migrate their relationships. You need a reconciliation process:

1. Verify that the duplicate records genuinely represent **the same entity**.
2. Select the canonical node and decide how to preserve properties/history.
3. Migrate or recreate required relationships per business rules.
4. Remove redundant records after verifying impact.
5. Add constraints to prevent recurrence.

Merging should never be done solely because two names, emails, or search fields look similar; a single mistake can blend data from **two different people**.

## 8. Integration Problem: One Customer, Multiple Source IDs

Suppose an application has canonical customer `'CUST-00042'` and a CRM source record `'CRM-872'`.

### 8.1. Creating Canonical Keys and External Keys

```cypher
CREATE CONSTRAINT customer_canonical_id_unique IF NOT EXISTS
FOR (c:CanonicalCustomer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT identity_source_id_unique IF NOT EXISTS
FOR (x:ExternalIdentity)
REQUIRE (x.source, x.externalId) IS UNIQUE;
```

Then write the mapping link:

```cypher
MERGE (c:CanonicalCustomer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = $fullName
MERGE (x:ExternalIdentity {
  source: $source,
  externalId: $externalId
})
ON CREATE SET x.firstSeenAt = datetime()
MERGE (x)-[:IDENTIFIES]->(c)
RETURN c.customerId AS customerId,
       x.source AS source,
       x.externalId AS externalId;
```

Example parameters:

```json
{
  "customerId": "CUST-00042",
  "fullName": "Nguyễn An",
  "source": "crm",
  "externalId": "CRM-872"
}
```

This is an **illustrative model**. In production, before creating `IDENTIFIES`, verify that the external ID truly belongs to that `customerId`.

### 8.2. Resolving from a Source ID to the Canonical ID

```cypher
MATCH (x:ExternalIdentity {
  source: $source,
  externalId: $externalId
})-[:IDENTIFIES]->(c:CanonicalCustomer)
RETURN c.customerId AS customerId,
       c.fullName AS fullName;
```

This query answers: **which canonical customer corresponds to CRM record `CRM-872`?**

### 8.3. Notes on One-to-One Mappings

`MERGE (x)-[:IDENTIFIES]->(c)` finds or creates **a link to node `c`**, but by itself does not guarantee `x` does not simultaneously have another `IDENTIFIES` link to a **different** canonical customer.

If business rules require each external ID to map to **at most one** canonical customer at a time, enforce the rule in the write workflow and audit with:

```cypher
MATCH (x:ExternalIdentity)-[:IDENTIFIES]->(c:CanonicalCustomer)
WITH x, count(DISTINCT c) AS canonicalCount
WHERE canonicalCount > 1
RETURN x.source AS source,
       x.externalId AS externalId,
       canonicalCount;
```

This query **detects** anomalous mappings without fixing them. Put validation and conflict-handling logic into the write transaction; if needed, design mapping change history separately from the currently active relationship.

## 9. Identifiers for Relationships and Events

Nodes are not the only elements needing business identifiers. If a relationship represents an **independent event**, such as `TRANSFERRED`, `PURCHASED`, or `BOOKED`, each event may need its own ID.

```text
(:Account {accountId: 'A'})
   ├──[:TRANSFERRED {transferId: 'T001', amount: 100000}]──→ (:Account {accountId: 'B'})
   └──[:TRANSFERRED {transferId: 'T002', amount: 250000}]──→ (:Account {accountId: 'B'})
```

Two relationships with the same type, direction, and endpoints are **two valid transactions** because they have different `transferId` values.

### 9.1. Constraints on Relationship Identifiers

In Neo4j versions supporting uniqueness constraints on relationships:

```cypher
CREATE CONSTRAINT transfer_id_unique IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
REQUIRE r.transferId IS UNIQUE;
```

The constraint prevents two `TRANSFERRED` relationships from carrying the same `transferId`. It **does not forbid** two differently identified transactions between the same two accounts.

For events unique only within a single source, consider a composite key `(r.source, r.transferId)` if supported by your Neo4j version and required by the data contract.

### 9.2. MERGE Must Reflect Event Identity

```cypher
MATCH (from:Account {accountId: $fromAccountId})
MATCH (to:Account {accountId: $toAccountId})
MERGE (from)-[r:TRANSFERRED {transferId: $transferId}]->(to)
ON CREATE SET
  r.amount = $amount,
  r.occurredAt = datetime($occurredAt)
RETURN r.transferId AS transferId;
```

If you only use `MERGE (from)-[:TRANSFERRED]->(to)`, distinct transactions between the same two accounts would be collapsed into **a single relationship**, losing information about subsequent transactions.

If `transferId` already exists but connects two accounts **different** from the incoming data, treat it as a **conflict requiring reconciliation**; a uniqueness constraint will cause the new write to fail. Never silently rewire endpoints just to make the operation succeed.

### 9.3. When Should You Use a Dedicated Event Node?

If an event has its own lifecycle, multiple states, or needs links to invoices, payments, or reconciliation records, consider:

```text
(:Account A)-[:SENT]->(:Transfer {transferId: 'T001'})-[:RECEIVED_BY]->(:Account B)
```

The `Transfer` node can be identified by `transferId` and have additional relationships to `PaymentMethod`, `Invoice`, or `AuditRecord`. Choose node vs. relationship based on model requirements; both can store business-key properties.

## 10. Data Ingestion: Preventing Duplicates and Broken Links

Stable identifiers are especially important when ingesting CSV files, calling APIs, or running scheduled jobs.

### 10.1. Idempotent Rerun Principle

A job loading the same customer record **twice** should not create two customers; a payment event with the same ID should not be recorded as two transactions.

For nodes:

```cypher
UNWIND $customers AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: row.customerId})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = row.fullName,
    c.updatedAt = datetime();
```

This is a simple ingestion pattern assuming `$customers` is a type-checked list of maps. In production systems, you must also **log/quarantine** missing or invalid rows so data is not silently dropped. A uniqueness constraint on `Customer.customerId` and error handling for concurrent write jobs are also required.

### 10.2. Avoid Linking by Display Name

Never link orders to customers by searching on names:

```cypher
// Risky pattern: fullName can collide or change
MATCH (c:Customer {fullName: $customerName})
MATCH (o:Order {orderId: $orderId})
CREATE (c)-[:PLACED]->(o);
```

If two people share the same name, the query may link the order to **multiple customer nodes**. Instead:

```cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MERGE (c)-[:PLACED]->(o);
```

Assuming business rules dictate each order has **exactly one `PLACED` relationship from its owning customer** and this rule is enforced at the write layer. `MERGE` by itself does not guarantee an order will not be linked from **two different customers**; enforce order-ownership checks in your write workflow.

### 10.3. Exports/Imports Must Preserve Business Keys

Example exported data:

```csv
customerId,fullName
CUST-00042,Nguyễn An
CUST-00043,Trần Bình
```

Order relationships should reference business keys:

```csv
orderId,customerId
ORDER-00017,CUST-00042
ORDER-00018,CUST-00043
```

Do not rely on `elementId()`/`id()` from the source database to recreate links in the target database. When importing into a new environment, match or create nodes by **`customerId`/`orderId`**, then create relationships using those keys.

### 10.4. Rule-Based Key Normalization

Define upfront:

- Are `'ABC'` and `'abc'` distinct?
- Is leading/trailing whitespace allowed?
- Can IDs contain leading zeros, like `'00042'`?
- Are IDs stored as **strings** or **numbers**?
- Is namespacing by tenant, source, country, or system version required?

Never arbitrarily cast `'00042'` to the integer `42` if the source format requires preserving leading zeros. Likewise, do not blindly apply `toLower()` to every ID because some systems treat uppercase and lowercase as **two different codes**.

Normalization must follow the **issuing authority's contract** and be applied consistently across ingestion, queries, APIs, and constraints.

## 11. Neo4j Java Driver and Spring Data Neo4j Integration

### 11.1. Java Driver: Parameters as Business Keys

Java applications should pass IDs via **parameters**, never concatenating user values into Cypher strings:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.fullName AS fullName;
```

Corresponding parameter map:

```json
{
  "tenantId": "TENANT-A",
  "customerId": "CUST-00042"
}
```

The key here consists of **two node properties**, so when an API looks up a customer by tenant, both values must be provided. Using parameters separates query structure from input data and enables query plan reuse.

### 11.2. Spring Data Neo4j: Identifying Entities by Application ID

With Spring Data Neo4j, you can map an application-assigned ID key to a node property:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;

    private String fullName;

    protected Customer() {
    }

    public Customer(String customerId, String fullName) {
        this.customerId = customerId;
        this.fullName = fullName;
    }
}
```

In this example, `customerId` is **supplied by the application** and stored as a property on `:Customer`. `@Id` tells Spring Data Neo4j how to identify the entity during mapping, but **does not automatically create a uniqueness constraint in the database**; you must declare the corresponding constraint separately.

Spring Data Neo4j also supports framework/database-generated IDs depending on version. If you use an internal technical identifier for mapping, still keep a **durable application key** whenever data must be exported/imported or referenced via APIs. For composite keys, design mapping and repository lookups according to your library version's capabilities; do not assume a single `@Id` annotation natively handles all composite key forms.

### 11.3. What If an ID Changes?

In APIs, treat canonical keys as **immutable** whenever possible. If a source system requires changing an ID, do not arbitrarily overwrite IDs across all nodes. Instead:

1. Verify whether it is an **ID change for the same entity** or a **new entity**.
2. Maintain a mapping from the old ID to the new ID during a transition window if needed.
3. Update references across integrated systems in a planned rollout.
4. Audit constraints, caches, APIs, and sync jobs.

If external IDs change frequently, that is all the more reason to maintain a **stable canonical ID** and a history-aware `ExternalIdentity` model.

## 12. Identifiers and Query Tuning

Querying by an explicit key is usually the best starting point in a large graph:

```cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (c)-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY orderId;
```

When an appropriate constraint/index exists on `Customer.customerId`, the optimizer **can** start with a keyed node lookup before traversing `PLACED` relationships.

Compare with a keyless query:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.fullName CONTAINS $nameFragment
RETURN o.orderId;
```

A fuzzy name query can match **many customers** and traverse many relationships; it serves a search use case rather than a keyed lookup.

To inspect the plan:

```cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
```

`EXPLAIN` only builds the plan; `PROFILE` executes the query to collect metrics. Creating an index does not guarantee every query will use it; the choice depends on the optimizer, statistics, and filter predicates.

**Design takeaway:** Stable identifiers pinpoint the exact **starting node** for relationship/path queries while also aiding tracing and incident investigation in production.

## 13. Common Mistakes and How to Prevent Them

| Mistake | Consequence | Prevention / Fix |
| --- | --- | --- |
| Using `elementId(n)` as an API key, CSV key, or long-term contact ID | Links can break when data is recreated or migrated | Use a durable application-managed key |
| Using `id(n)` as a customer ID | Internal numeric IDs can be reused; API couples to storage internals | Use a dedicated `customerId` |
| Assuming two nodes with the same `fullName` are the same person | Wrongly merges people who share a name | Reconcile using trustworthy keys |
| Using `MERGE` on both ID and name/email | Changing descriptive values causes the pattern to stop matching | `MERGE` on the key, `SET` mutable properties |
| Omitting uniqueness constraints on keys | Re-ingestion or concurrent writes can create duplicate nodes | Add constraints matching label and scope |
| Assuming uniqueness always requires the property to exist | Nodes lacking the ID remain valid under a plain uniqueness constraint | Validate input data; consider existence/node key constraints |
| Using `externalId = '42'` without recording the source | Confuses CRM ID with support ID | Use composite key `(source, externalId)` |
| Forgetting tenant in `MATCH` or `MERGE` | Reads/updates the wrong tenant's entity | Always include the full composite key |
| Stripping leading zeros or altering ID casing arbitrarily | Causes collisions or misses matching records | Normalize strictly per source contract |
| Using a single relationship for multiple distinct transactions | Loses event history | Attach a transaction ID or use an event node |
| Assuming `MERGE` deletes pre-existing duplicate data | Duplicate nodes/edges remain in the graph | Reconcile, clean up under control, then add constraints |
| Blindly creating `IDENTIFIES` links to multiple customers for one source ID | One external ID resolves to multiple canonical entities | Guard the write workflow, audit mappings, handle conflicts |

## 14. Practice Exercises with Answers

Practice in a **test database**. Examples use dedicated labels or codes prefixed with `GE006-` to avoid colliding with other domain data.

### Exercise 1. Choosing a Key for Products

A product has `name`, `price`, `sku`, and `supplierId`. Name and price can change, and `sku` is unique **only within a single supplier**. Which key is appropriate?

**Suggested Answer:** You can use the composite key `(supplierId, sku)` if the contract with the source guarantees uniqueness and stability. If products have an application-issued canonical ID, use `productId` as the durable key and store `supplierId`/`sku` as source references. Do not choose `name` or `price` as the key.

### Exercise 2. Writing a Tenant-Scoped Constraint

Given `Customer` with `tenantId` and `customerId`; a `customerId` may repeat across two tenants but must not repeat within the same tenant.

**Answer:**

```cypher
CREATE CONSTRAINT ge006_customer_tenant_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

When querying:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c;
```

### Exercise 3. Identifying a MERGE Mistake

`(:Person {personId: 'GE006-P001', fullName: 'An'})` already exists. The next ingestion run executes:

```cypher
MERGE (:Person {personId: 'GE006-P001', fullName: 'Nguyễn An'});
```

Why is this inappropriate?

**Answer:** `MERGE` must match the **entire map**, but the name has changed. It may try to create a new node or fail with a constraint error. `MERGE` on `personId`, then `SET p.fullName = ...`.

### Exercise 4. Choosing Between Internal ID and Application ID

An application needs to build customer-view URLs, sync with a third-party system, and re-import data into a staging environment. Should it pass `elementId(c)` or `c.customerId`?

**Answer:** Choose `c.customerId`, stably managed at the application layer. `elementId()` is only appropriate in technical contexts and has no persistence guarantee as a business key across transactions or environments.

### Exercise 5. IDs from Multiple Systems

CRM has `customerId = '42'` and the support system has `contactId = '42'`. Can you automatically conclude these are the same person?

**Answer:** No. Treat the two codes as belonging to **two different namespaces**. Use the `(source, externalId)` combination to identify source records and only link them to the same canonical node once reconciliation evidence exists.

### Exercise 6. Same Two Accounts, Two Transactions

A transfers to B the first time with `transferId = 'T001'` and the second time with `transferId = 'T002'`. Should you use `MERGE (a)-[:TRANSFERRED]->(b)` for both transfers?

**Answer:** No, if you want to preserve two distinct events. Use a `transferId` identifier on each relationship or create a `Transfer` node per transaction. You can also place a uniqueness constraint on the transaction ID so job reruns never duplicate the same event.

### Exercise 7. Writing a Query to Detect Existing Duplicate Keys

In a test database **without a uniqueness constraint yet**, write a query to find `Person.personId` values appearing on more than one node.

**Answer:**

```cypher
MATCH (p:Person)
WHERE p.personId IS NOT NULL
WITH p.personId AS personId, count(p) AS occurrences
WHERE occurrences > 1
RETURN personId, occurrences
ORDER BY occurrences DESC;
```

This is a **detection** query; it does not merge nodes or fix relationships automatically.

## 15. Summary

- A **business key** is a durable identifier used by an application to recognize an entity, an **external identifier** belongs to a source system's scope, and an **internal identifier** is managed by Neo4j for technical purposes.
- `elementId()` (and `id()` where still supported) is **not a long-term stable business key**; avoid using it for URLs, API keys, or cross-environment data exchange.
- Two nodes with identical properties are still **two separate elements** if created separately. Use reliable keys and appropriate uniqueness constraints to protect identity.
- Use `MERGE` on **stable keys** and `SET` for mutable properties; include **tenant** or **source** in composite keys when required by the uniqueness scope.
- With multiple data sources, you can store external IDs as properties or `ExternalIdentity` nodes, but only link them to the **same canonical node** after verifying entity identity.
- Both nodes and event-representing relationships may require dedicated business IDs to support idempotent ingestion and accurate queries.
- Sound identifier design makes **creating links**, **querying paths**, **index tuning**, **data ingestion**, and **Java Driver/Spring Data Neo4j integration** far more reliable.

When identifiers are placed at the right level and enforced through constraints and write workflows, a property graph can scale across many applications and source systems while preserving the meaning of **"this is the same entity"** over time.
