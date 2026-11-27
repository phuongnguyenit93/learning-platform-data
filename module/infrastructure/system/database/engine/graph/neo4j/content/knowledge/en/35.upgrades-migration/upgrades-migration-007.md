# Migrating Labels, Properties, and Relationships While Preserving Business Identity

## 1. Problem: Changing the Graph Model Without Changing Entity Identity

In the **DATABASE_ENGINE_GRAPH_NEO4J** module, Neo4j represents data using **nodes**, **relationships**, and **properties**, queried via Cypher and typically accessed through the Java Driver or Spring Data Neo4j. As an application evolves, the graph model may need to change:

- Node label **LegacyCustomer** is replaced by **Customer**.
- Property **accountNo** is renamed to **customerId**.
- Property **totalCents** moves to **amountMinor**, still storing an integer in the currency's minor unit.
- Relationship type **PURCHASED** changes to **PLACED**, preserving direction from Customer to Order.
- Queries and repositories are updated to use the new labels, property names, and relationships.

The hard part is not renaming tokens in a Cypher query. **The same customer must remain the exact same customer**, even after changing the model, deploying multiple services, or re-running a migration following a failure.

A migration bug can cause the application to create **two Customer nodes** for the same code, lose Customer–Order links, attach orders to the wrong tenant, or overwrite a paid Order's status. Worse, many such bugs raise no exceptions: Cypher runs cleanly yet returns the wrong graph.

**Lesson goal:** design and test migrations of **labels, properties, and relationships** in a way that preserves **business keys**, is safe to re-run, supports running multiple application versions concurrently, and deletes legacy structures only after verified evidence.

> **Scope:** all create, update, and delete statements in this lesson target **an isolated test database**. For production, you must have backups, a multi-step rollout plan, least-privilege permissions, and source data validation before changing anything.

## 2. Business Identity Differs from Neo4j Internal IDs

### 2.1. Three Common Types of Identifiers

| Concept | Example | Purpose | Should it serve as a long-term API contract? |
|---|---|---|---|
| **Business key** | **(tenantId, customerId)** | Identifies the same customer across models and systems | **Yes**, when stably governed |
| **Graph internal ID** | **elementId(n)** or legacy internal IDs | References a Neo4j element per API rules | **No**, never treat as a durable business key |
| **Request/event ID** | **eventId = ev-a-101** | Prevents reprocessing an event or request submission | Yes, within **event scope**, never substituting for customerId |

In this lesson, customer identity is the pair **(tenantId, customerId)**; order identity is **(tenantId, orderId)**. Two tenants may share the same code **C-1** or **P-101** without colliding.

Adding a label via **SET n:Customer** on an existing node does not create a new node; the node remains the same graph entity. Yet **never rely on that to expose elementId to external systems**. Across dumps/restores, data rebuilds, or graph merges, primary verification must always rely on **business keys**.

### 2.2. Business Invariants Before and After Migration

Let \(K_C=(tenantId,customerId)\) and \(K_O=(tenantId,orderId)\).

A migration meets requirements when:

1. **Key preservation:** every old Customer node corresponds to **exactly one** new Customer with the same \(K_C\); every old Order corresponds to exactly one new Order with the same \(K_O\).
2. **Zero duplicates:** no two nodes sharing a target label hold the same valid key.
3. **Zero lost links:** if Customer A placed Order B in the old model, the new model retains a corresponding relationship with exact direction and tenant.
4. **No uncontracted data mutation:** amounts, statuses, timestamps, and retained properties are neither dropped nor mis-cast.
5. **Safe re-runs:** running the migration a second time neither inflates entity/relationship counts nor overwrites valid new updates.
6. **Forward compatibility:** while two application versions run side by side, neither side writes into a blind spot unreadable by the other.

**Note:** uniqueness constraints protect **uniqueness**, yet do not automatically require every node to possess all key properties. Check **missing/null keys** separately or evaluate **node key constraints** if your edition supports them.

## 3. Design the Old → New Mapping Before Writing Cypher

Suppose starting data looks like:

~~~text
(:DemoMigLegacyCustomer {
    orgId: "shop-a",
    accountNo: "C-1",
    fullName: "An"
})-[:DEMO_MIG_PURCHASED {
    sourceEventId: "ev-a-101",
    createdAt: datetime(...)
}]->(:DemoMigLegacyPurchase {
    orgId: "shop-a",
    purchaseNo: "P-101",
    totalCents: 120000,
    orderState: "PAID"
})
~~~

Target model:

~~~text
(:DemoMigCustomer {
    tenantId: "shop-a",
    customerId: "C-1",
    displayName: "An"
})-[:DEMO_MIG_PLACED {
    eventId: "ev-a-101",
    occurredAt: datetime(...)
}]->(:DemoMigOrder {
    tenantId: "shop-a",
    orderId: "P-101",
    amountMinor: 120000,
    status: "PAID"
})
~~~

These label and relationship names are **dedicated to practice**, kept separate from real application data.

### 3.1. Mandatory Mapping Table

| Old component | Target component | Transformation | Invariant to verify |
|---|---|---|---|
| **DemoMigLegacyCustomer** | **DemoMigCustomer** | Add new label on the same node | No increase in logical Customer count |
| **orgId** (Customer) | **tenantId** | Copy value, never assign silent defaults | Equal after mapping |
| **accountNo** | **customerId** | Copy **STRING** | Preserves letters, leading zeros, and tenant |
| **fullName** | **displayName** | Copy when target is missing | Never overwrite newly updated names |
| **DemoMigLegacyPurchase** | **DemoMigOrder** | Add new label on the same node | No increase in logical Order count |
| **purchaseNo** | **orderId** | Copy STRING | Never generate new random IDs |
| **totalCents** | **amountMinor** | Copy INTEGER in minor units | Zero monetary precision loss |
| **orderState** | **status** | Explicit status mapping | PAID → PAID; CREATED → NEW per example |
| **DEMO_MIG_PURCHASED** | **DEMO_MIG_PLACED** | Create new directed relationship | Zero mismatched endpoints |
| **sourceEventId** | **eventId** | Copy event identifier | Preserves event identity |
| **createdAt** (relationship) | **occurredAt** | Copy temporal type | Never shift UTC to wrong local dates |

**Never use** mutable property values such as **status**, **displayName**, or **lastUpdatedAt** as part of a **MERGE key**. Those are entity attributes, not identity.

### 3.2. Relationship Direction Diagram

~~~mermaid
flowchart LR
  subgraph OLD["Old Model"]
    LC["LegacyCustomer<br/>orgId + accountNo"] -->|"DEMO_MIG_PURCHASED"| LP["LegacyPurchase<br/>orgId + purchaseNo"]
  end
  subgraph NEW["New Model"]
    C["Customer<br/>tenantId + customerId"] -->|"DEMO_MIG_PLACED"| O["Order<br/>tenantId + orderId"]
  end
  LC -.->|"Preserves same business key"| C
  LP -.->|"Preserves same business key"| O
~~~

In this lesson's **in-place migration** strategy, LC and C are **the same node carrying two labels during transition**; likewise for LegacyPurchase and Order. Dashed arrows denote **logical mapping**, not extra Neo4j relationships to create.

## 4. Create a Fixture Capable of Catching Tenant Mix-Ups

### 4.1. Prepare Source and Target Schemas

Run the following constraints on a **clean test database**:

~~~cypher
CREATE CONSTRAINT demo_mig_old_customer_key IF NOT EXISTS
FOR (c:DemoMigLegacyCustomer)
REQUIRE (c.orgId, c.accountNo) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_old_purchase_key IF NOT EXISTS
FOR (o:DemoMigLegacyPurchase)
REQUIRE (o.orgId, o.purchaseNo) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_customer_key IF NOT EXISTS
FOR (c:DemoMigCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_order_key IF NOT EXISTS
FOR (o:DemoMigOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

Creating target constraints **before adding new labels** helps catch collisions during migration. If the graph already holds a **DemoMigCustomer** node from another ingestion path sharing the same business key, attaching the new label is rejected instead of silently creating two logical entities. Classify and resolve such conflicts before proceeding.

**CREATE CONSTRAINT** commands require schema admin privileges. On **Enterprise Edition**, consider **node key constraints** to enforce both **existence and uniqueness**; basic uniqueness constraints here do not automatically block empty/null properties.

### 4.2. Seed Sample Source Data

~~~cypher
CREATE
  (c1:DemoMigLegacyCustomer {
    orgId: 'shop-a', accountNo: 'C-1', fullName: 'An'
  }),
  (c2:DemoMigLegacyCustomer {
    orgId: 'shop-b', accountNo: 'C-1', fullName: 'Binh'
  }),
  (p1:DemoMigLegacyPurchase {
    orgId: 'shop-a', purchaseNo: 'P-101',
    totalCents: 120000, orderState: 'PAID'
  }),
  (p2:DemoMigLegacyPurchase {
    orgId: 'shop-a', purchaseNo: 'P-102',
    totalCents: 69000, orderState: 'CREATED'
  }),
  (p3:DemoMigLegacyPurchase {
    orgId: 'shop-b', purchaseNo: 'P-101',
    totalCents: 27000, orderState: 'CREATED'
  }),
  (c1)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-a-101',
    createdAt: datetime('2026-10-01T08:00:00Z')
  }]->(p1),
  (c1)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-a-102',
    createdAt: datetime('2026-10-01T09:00:00Z')
  }]->(p2),
  (c2)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-b-101',
    createdAt: datetime('2026-10-01T10:00:00Z')
  }]->(p3);
~~~

Expected data:

| Tenant | Customer | Order | totalCents | orderState | Event |
|---|---|---|---:|---|---|
| shop-a | C-1 | P-101 | 120000 | PAID | ev-a-101 |
| shop-a | C-1 | P-102 | 69000 | CREATED | ev-a-102 |
| shop-b | C-1 | P-101 | 27000 | CREATED | ev-b-101 |

Both tenants share **Customer C-1** and **Order P-101**. This exact overlap exposes queries or migrations that omit **tenantId/orgId**.

**Do not re-run the CREATE fixture** once data exists; uniqueness constraints will reject it. To reset the exercise, use a fresh test database or an isolated fixture reset procedure. Never run **MATCH (n) DETACH DELETE n** on a shared database.

## 5. Preflight: Validate Source Data Before Modifying the Graph

A solid migration **halts before writing** if source data violates invariants. Never turn bad records into seemingly valid output by silently skipping non-matching rows.

### 5.1. Check for Missing Business Keys

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE trim(coalesce(c.orgId, '')) = ''
   OR trim(coalesce(c.accountNo, '')) = ''
RETURN c.orgId AS orgId, c.accountNo AS accountNo
LIMIT 50;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE trim(coalesce(o.orgId, '')) = ''
   OR trim(coalesce(o.purchaseNo, '')) = ''
RETURN o.orgId AS orgId, o.purchaseNo AS purchaseNo
LIMIT 50;
~~~

With a valid fixture, both queries return **zero rows**. If violations appear, fix, remove, or quarantine them per business policy before attaching target labels.

**Note:** business IDs are STRINGS. Never run **toInteger('00042')** if leading zeros matter; never strip spaces or fold case unless the entire system agrees on canonical identifier normalization.

### 5.2. Check for Duplicate Keys in Existing Data

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WITH c.orgId AS orgId, c.accountNo AS accountNo, count(*) AS copies
WHERE copies > 1
RETURN orgId, accountNo, copies;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WITH o.orgId AS orgId, o.purchaseNo AS purchaseNo, count(*) AS copies
WHERE copies > 1
RETURN orgId, purchaseNo, copies;
~~~

When source constraints are active, complete key duplicates are normally prevented. However, on legacy data lacking constraints, run these queries **before creating new constraints**. Adding **IF NOT EXISTS** does not merge duplicate records.

### 5.3. Check Cross-Tenant Edges or Missing Endpoints

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[r:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WHERE c.orgId IS NULL OR o.orgId IS NULL
   OR c.orgId <> o.orgId
RETURN c.orgId AS customerTenant, c.accountNo AS customerId,
       o.orgId AS orderTenant, o.purchaseNo AS orderId,
       r.sourceEventId AS eventId;
~~~

Expected output: **0 rows**. Matching nodes by **accountNo** without **orgId** could link a shop-a order to a shop-b customer.

For every Order, verify the expected incoming purchase edge count:

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
OPTIONAL MATCH (c:DemoMigLegacyCustomer)
  -[r:DEMO_MIG_PURCHASED]->(o)
WITH o, count(r) AS incoming
WHERE incoming <> 1
RETURN o.orgId AS tenantId, o.purchaseNo AS orderId, incoming;
~~~

In this example, each Order has **exactly one** placing Customer. If your domain allows multiple placing actors or multiple events per Order, **do not enforce** this example's "one edge per pair" rule; design an event model with a dedicated **eventId**.

### 5.4. Check Properties, Types, and Statuses Before Mapping

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE o.totalCents IS NULL
   OR o.totalCents < 0
   OR o.orderState IS NULL
   OR NOT o.orderState IN ['PAID', 'CREATED']
RETURN o.orgId AS tenantId, o.purchaseNo AS orderId,
       o.totalCents AS amount, o.orderState AS state;
~~~

This checks missing amounts, negative values, and unmapped statuses. In real datasets, also verify **INTEGER type**, currency units, domain rules for refunds/negative amounts, and valid timestamps.

**Never map unrecognized statuses arbitrarily to PAID or NEW.** If **REFUNDED**, **CANCELLED**, or **PENDING** appear, add business-approved mappings before running the migration.

### 5.5. Check Collisions with Existing Target Model Nodes

If the database already contains target nodes created by an earlier partial rollout:

~~~cypher
MATCH (old:DemoMigLegacyCustomer)
MATCH (other:DemoMigCustomer {
  tenantId: old.orgId,
  customerId: old.accountNo
})
WHERE old <> other
RETURN old.orgId AS tenantId, old.accountNo AS customerId,
       count(other) AS conflictingNodes;
~~~

Returned rows indicate **identity conflicts**: two distinct physical nodes representing the same business key. Never blindly run **MERGE** to create a third node, and never delete either node without auditing every property and relationship referencing it. Decide which node survives and transfer all links via a verified merge procedure.

## 6. Choosing a Strategy: In-Place Migration or Creating New Nodes?

### 6.1. In-Place Migration — Ideal When Only Representation Changes

When a **Customer remains the exact same Customer** and only labels and property names change, the simplest and lowest-risk method is usually:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL AND c.accountNo IS NOT NULL
SET c.tenantId = coalesce(c.tenantId, c.orgId),
    c.customerId = coalesce(c.customerId, c.accountNo),
    c.displayName = coalesce(c.displayName, c.fullName)
SET c:DemoMigCustomer;
~~~

Here:

- **SET c:DemoMigCustomer** attaches the new label without creating a node.
- New properties are backfilled from old properties **when the target property is null**.
- Legacy labels/properties stay intact so old app instances keep reading during rollout.
- The pair **(tenantId, customerId)** preserves business identity from **(orgId, accountNo)** rather than inventing random IDs.

**Preconditions before running:** all preflight queries PASS, zero target identity conflicts exist, and no target properties already hold mismatched values from a failed prior run. If a node already has **c.customerId** set to a wrong code, **coalesce** preserves the wrong code; post-migration drift checks must catch this instead of equating query execution with PASS.

### 6.2. When Must You Create New Nodes?

Consider creating new nodes when **the domain entity itself changes**, for example:

- A **LegacyAccount** splits into **Person** and **Organization**.
- Two source nodes merge into a single canonical Customer.
- A many-to-many relationship is promoted into a **PurchaseEvent** node with its own lifecycle/state.
- Data moves into a separate database or cluster where physical node identity cannot be preserved.

Only then should you use **MERGE (target:NewLabel {businessKey: ...})** backed by uniqueness constraints, copy data, reattach relationships, and reconcile one-to-one or many-to-one mappings. Never assume the new node's **elementId** matches the old node's.

**Rule of thumb:** representation/schema changes do not automatically require creating new entities. Creating new nodes without a relationship-reattachment strategy easily introduces "split sources of truth" in the graph.

## 7. Migrating Customer and Order Properties with Proper Types

### 7.1. Customer Backfill Without Overwriting Newer Updates

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL AND c.accountNo IS NOT NULL
SET c.tenantId = coalesce(c.tenantId, c.orgId),
    c.customerId = coalesce(c.customerId, c.accountNo),
    c.displayName = coalesce(c.displayName, c.fullName)
SET c:DemoMigCustomer
RETURN count(c) AS migratedCustomers;
~~~

On the fixture, result is **2**. Re-running creates no extra Customers. If the new app release already updated **displayName**, re-running will not revert it to **fullName**.

This illustrates **null backfill** only. If real requirements distinguish **empty strings** from **NULL**, normalize explicitly and decide whether empty strings represent missing data or valid values to preserve. Never treat **coalesce** as a cure-all for dirty data.

### 7.2. Order Backfill with Explicit Status Mapping

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE o.orgId IS NOT NULL
  AND o.purchaseNo IS NOT NULL
  AND o.totalCents IS NOT NULL
  AND o.orderState IN ['PAID', 'CREATED']
SET o.tenantId = coalesce(o.tenantId, o.orgId),
    o.orderId = coalesce(o.orderId, o.purchaseNo),
    o.amountMinor = coalesce(o.amountMinor, o.totalCents),
    o.status = coalesce(
      o.status,
      CASE o.orderState
        WHEN 'PAID' THEN 'PAID'
        WHEN 'CREATED' THEN 'NEW'
      END
    )
SET o:DemoMigOrder
RETURN count(o) AS migratedOrders;
~~~

On the fixture, **migratedOrders = 3**:

| tenantId | orderId | amountMinor | status |
|---|---|---:|---|
| shop-a | P-101 | 120000 | PAID |
| shop-a | P-102 | 69000 | NEW |
| shop-b | P-101 | 27000 | NEW |

**Preserve units:** **totalCents → amountMinor** here is **INTEGER → INTEGER** in identical minor units, avoiding any FLOAT conversion. If the new model stores a different unit (such as major currency units instead of cents), define exact formulas, rounding, currencies, bounds, and accuracy tests. Never guess units from property names alone.

**Safe re-runs:** an Order whose **status** progressed after migration will not revert to NEW if backfill re-runs. If domain rules require bidirectional status sync during dual-write, implement an explicit source-of-truth rule rather than relying on a single **coalesce**.

### 7.3. Never Replace the Whole Map When Changing Only Selected Properties

Cypher allows:

~~~cypher
// DO NOT use for this migration unless mapping every property intentionally.
MATCH (o:DemoMigOrder {tenantId: 'shop-a', orderId: 'P-101'})
SET o = {tenantId: 'shop-a', orderId: 'P-101'};
~~~

**SET o = {...}** replaces the node's **entire** property map, deleting any unlisted properties. That snippet would wipe **amountMinor** and **status** and corrupt data. It is shown **solely as a warning—do not run it**.

When backfilling specific fields, use **SET o.property = ...**. If merging a map is truly required, **SET o += {...}** preserves unmentioned properties, while still needing explicit null/overwrite checks per contract.

### 7.4. Check Drift Between Old and New Properties

After backfill, detect identity mismatches:

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
WHERE c.tenantId IS NULL
   OR c.customerId IS NULL
   OR c.tenantId <> c.orgId
   OR c.customerId <> c.accountNo
RETURN c.orgId AS orgId, c.accountNo AS accountNo,
       c.tenantId AS tenantId, c.customerId AS customerId;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase:DemoMigOrder)
WHERE o.tenantId IS NULL
   OR o.orderId IS NULL
   OR o.tenantId <> o.orgId
   OR o.orderId <> o.purchaseNo
RETURN o.orgId AS oldTenant, o.purchaseNo AS oldOrderId,
       o.tenantId AS newTenant, o.orderId AS newOrderId;
~~~

Both must return **0 rows**. Differences in display names or statuses can be legitimate once dual-write applications allow updates on the new model; verify those via **data version/timestamp and source-of-truth rules** rather than blindly asserting equality across every property.

## 8. Migrating Relationship Types, Directions, and Properties

### 8.1. There Is No `SET` Statement to Directly Rename a Relationship Type

In Cypher, every relationship has **a single type**. **SET r:NEW_TYPE** does not exist as an equivalent to adding node labels. To transition **DEMO_MIG_PURCHASED → DEMO_MIG_PLACED**, create the new relationship between bound endpoints, verify data, and only then delete the old relationship.

**Domain assumption in this example:** each Order has exactly **one** placing event linking it to **one** Customer. If multiple distinct events connect the same pair of nodes, model **event nodes/relationships keyed by eventId** with matching schemas instead of collapsing them onto a single edge just because endpoints match.

### 8.2. Dedicated Preflight for Source Relationships

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WITH c, o, count(old) AS copies
WHERE copies <> 1
RETURN c.orgId AS tenantId,
       c.accountNo AS customerId,
       o.purchaseNo AS orderId, copies;
~~~

Expected output: **0 rows**—no duplicate old edges between the same node pair. Check missing event IDs:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WHERE trim(coalesce(old.sourceEventId, '')) = ''
   OR old.createdAt IS NULL
RETURN c.accountNo AS customerId,
       o.purchaseNo AS orderId,
       old.sourceEventId AS eventId;
~~~

If event IDs are non-unique or multiple events traverse the same node pair, follow the proper domain model. Never use **MERGE (c)-[:PLACED]->(o)** if doing so silently collapses distinct events.

### 8.3. Create New Relationships Between Already-Bound Endpoints

Once both Customer and Order nodes carry target labels:

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
WHERE c.orgId = o.orgId
  AND old.sourceEventId IS NOT NULL
MERGE (c)-[fresh:DEMO_MIG_PLACED]->(o)
ON CREATE SET
  fresh.eventId = old.sourceEventId,
  fresh.occurredAt = old.createdAt
RETURN count(fresh) AS processedRelationships;
~~~

On the fixture, result is **3**. At this stage, **both relationship types** coexist in the graph, connecting the same source/target nodes.

**Why bind endpoints before MERGE?** Nodes c and o are already matched. MERGE only checks/creates **the relationship** between those exact two nodes, preventing accidental creation of orphan Customer/Order nodes if part of a longer pattern misses.

**Why ON CREATE SET?** Metadata is copied only when creating the edge; re-runs never overwrite **occurredAt** on an existing new edge. If a target edge already exists with mismatched metadata, the migration **does not silently overwrite it**, allowing the validation query below to surface the discrepancy.

### 8.4. Verify Relationship Metadata

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
OPTIONAL MATCH (c)-[fresh:DEMO_MIG_PLACED]->(o)
WITH c, o, old,
     count(fresh) AS freshCount,
     collect(fresh.eventId) AS eventIds,
     collect(fresh.occurredAt) AS eventTimes
WHERE freshCount <> 1
   OR NOT old.sourceEventId IN eventIds
   OR NOT old.createdAt IN eventTimes
RETURN c.tenantId AS tenantId,
       c.customerId AS customerId,
       o.orderId AS orderId,
       old.sourceEventId AS oldEvent,
       freshCount, eventIds, eventTimes;
~~~

Expected output: **0 rows**. Because **collect** aggregates per endpoint pair, **freshCount <> 1** catches both missing and extra edges. In production, also reconcile **eventId** per tenant, enforce event uniqueness schemas where supported, and check relationship counts by type.

**Never delete old edges immediately after MERGE**. Validate the new model first and ensure every consumer reading **DEMO_MIG_PURCHASED** has followed an agreed transition plan.

### 8.5. If You Must Reverse Relationship Direction

A model redesign might prefer **(Order)-[:PLACED_BY]->(Customer)** instead of **(Customer)-[:PLACED]->(Order)**. Write that explicitly:

~~~cypher
MATCH (c:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigOrder)
MERGE (o)-[r:DEMO_MIG_PLACED_BY]->(c)
ON CREATE SET r.eventId = old.sourceEventId;
~~~

This is an **alternative design**—never run it alongside section 8.3 and treat all three edge types as one schema. Pick **one target direction** and update every **-> / <-** pattern in Java Driver/SDN queries.

## 9. Large-Scale Migration: Batching, Checkpoints, and Idempotency

### 9.1. Why Not Update Millions of Nodes in One Transaction?

Oversized transactions spike memory pressure, lock contention, transaction logs, commit latency, and total rollback risk on a single bad record. Neo4j provides **CALL { ... } IN TRANSACTIONS** to split input into smaller transaction batches.

For Neo4j versions supporting **variable scope clauses** (Neo4j 5.23+), Customer batching example:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL
  AND c.accountNo IS NOT NULL
CALL (c) {
  SET c.tenantId = coalesce(c.tenantId, c.orgId),
      c.customerId = coalesce(c.customerId, c.accountNo),
      c.displayName = coalesce(c.displayName, c.fullName)
  SET c:DemoMigCustomer
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Critical condition:** statements using **IN TRANSACTIONS** must execute in an **implicit transaction**. In Neo4j Browser, prefix with **:auto**; in Java Driver, call **session.run(...)** and consume the result. Never wrap it inside **executeWrite(...)**, explicit transactions, or Spring **@Transactional**, as those contexts forbid nested inner transactions.

On older Cypher releases lacking variable scope clauses, use importing **WITH** per your version's docs; verify server support before modifying syntax.

### 9.2. Transactions Committed Before a Failure Remain Persisted

If batch 1 commits 1,000 Customers and batch 2 hits a constraint violation, Neo4j **does not roll back batch 1**. Therefore:

1. Preflight must catch bad records before writing.
2. Every backfill step must be safely **re-runnable** without creating duplicates.
3. Track read counts, updated counts, errors, skips, and job checkpoints/manifests.
4. Record completed batches to resume cleanly, rather than relying on unstable **SKIP/LIMIT** offsets while source data changes.
5. After resuming, **reconcile the full source–target set**, not just the final batch's logs.

Never assume **IN CONCURRENT TRANSACTIONS** is always faster. Concurrent batches touching nodes/relationships with shared endpoints can trigger **lock contention or deadlocks**; benchmark on real workloads, especially when creating relationships.

### 9.3. Only Use LIMIT with a Proper Pagination Strategy

A query like:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WITH c LIMIT 1000
SET c:DemoMigCustomer;
~~~

is **not** a safe pagination strategy if re-run without filtering out processed nodes: it can repeatedly pick the first nodes and miss the rest. For batch processing, use **CALL ... IN TRANSACTIONS** or an explicit state-filtering and stable-key strategy.

## 10. Zero-Write-Freeze Deployment: Expand → Migrate → Verify → Switch → Contract

Model migrations often occur while multiple application versions serve live traffic. Running one script and immediately dropping old labels will break un-upgraded Java/SDN instances.

~~~mermaid
flowchart LR
  A["1. Expand schema & compatibility"] --> B["2. Dual-write / capture new writes"]
  B --> C["3. Backfill nodes & relationships"]
  C --> D["4. Verify & reconcile"]
  D --> E["5. Switch readers & APIs"]
  E --> F["6. Contract: controlled legacy cleanup"]
~~~

### 10.1. Expand — Allow Both Models to Coexist

- Create target constraints/indexes first.
- Deploy app code capable of reading **both legacy and new models** where needed.
- Never drop old properties/labels while readers still query them.
- Pin immutable business keys shared by **both versions**.
- Lock compatible versions of Neo4j/Java Driver/SDN/APOC/GDS wherever migration depends on them.

**Never switch all queries to the new label** while target data exists for only a subset of nodes.

### 10.2. Ensure New Writes Are Not Lost During Backfill

If the app keeps accepting orders while scripts run, this race can happen:

~~~text
T1: Migration backfills Order P-101
T2: Legacy app creates Order P-103 with only LegacyPurchase label
T3: Migration reports done because it scanned rows prior to T2
T4: New app queries only :DemoMigOrder -> misses P-103
~~~

Two common options:

1. **Planned write freeze** during a maintenance window if downtime is permitted.
2. **Transactional dual-write** or a **checkpointed CDC/queue stream** ensuring writes occurring after backfill starts also populate the target model.

With dual-write inside **the same database**, a single Neo4j transaction can update **both old and new labels/properties** atomically; new apps see both representations immediately. If both models span separate services or databases, use event IDs, idempotent retries, and progress tracking—never assume Neo4j transactions span external systems.

**Critical trap:** backfill scripts using **coalesce** will not update a target property if the old property changed *after* the target property was already populated. During dual-write, define a clear source of truth and update rules, or replay new deltas reliably before cutover.

### 10.3. Verify — Prove Both Models Express the Same Meaning

A migration does not PASS merely because updated node counts match source counts. Verify:

- Source–target **business key sets**, including tenants.
- Orders per Customer and vice versa.
- Relationship directions, types, and metadata.
- Monetary properties/types, statuses, and timestamps.
- Zero missing keys, zero duplicates, and **zero** cross-tenant relationships.
- Every write committed **after backfill started** appears in the new model.
- Second dry run on staging to verify idempotency.

### 10.4. Switch — Shift Traffic in Stages

The new application can:

1. Read select requests from the new schema and shadow-compare against the old schema on staging/canary.
2. Shift **5% → 25% → 100%** of traffic if supported by infrastructure.
3. Monitor query p95, DB Hits, invariants, and SDN mapping errors.
4. Stop querying legacy labels/properties once every instance is upgraded.

**Never rely on API traffic percentages alone**: a nightly batch worker or un-upgraded connector might still read the old schema outside main API routes.

### 10.5. Contract — Clean Up Legacy Structures Only After Evidence

Begin removing legacy relationship types, properties, or labels only when:

- Every writer has stopped writing legacy schemas.
- Every reader, consumer, report, and ETL job has switched to the new model.
- Data reconciliation PASSES and monitoring holds steady over an adequate window.
- Backups and restore/compensation runbooks have been rehearsed.
- Data owners approve deletion, especially when historical fields carry audit obligations.

Contract is typically the **hardest step to roll back**, as it removes old query paths and may delete data absent from the new schema.

## 11. Cypher Verification Before Removing Legacy Schema

### 11.1. Compare Business Outputs of Old and New Queries

Old query:

~~~cypher
MATCH (c:DemoMigLegacyCustomer {
  orgId: $tenantId,
  accountNo: $customerId
})-[:DEMO_MIG_PURCHASED]->(o:DemoMigLegacyPurchase)
RETURN o.purchaseNo AS orderId
ORDER BY orderId;
~~~

New query:

~~~cypher
MATCH (c:DemoMigCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_MIG_PLACED]->(o:DemoMigOrder)
WHERE o.tenantId = $tenantId
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

For **shop-a/C-1**, both must return **[P-101, P-102]**. For **shop-b/C-1**, both must return shop-b's **[P-101]**. Checking only Order code **P-101** without tenant would let cross-tenant bugs slip through.

**Cypher does not guarantee row order without ORDER BY.** When comparing lists in tests, always include ORDER BY or perform order-independent set comparisons.

### 11.2. Verify New Label Coverage

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE NOT c:DemoMigCustomer
   OR c.tenantId IS NULL
   OR c.customerId IS NULL
RETURN count(c) AS unmigratedCustomers;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE NOT o:DemoMigOrder
   OR o.tenantId IS NULL
   OR o.orderId IS NULL
RETURN count(o) AS unmigratedOrders;
~~~

Expect **0**, while still verifying values are **accurate**, not merely non-null.

### 11.3. Verify Counts and Uniqueness

~~~cypher
MATCH (c:DemoMigCustomer)
WITH c.tenantId AS tenantId, c.customerId AS customerId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, customerId, copies;
~~~

~~~cypher
MATCH (o:DemoMigOrder)
WITH o.tenantId AS tenantId, o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, orderId, copies;
~~~

Both must return **zero rows**. On the static fixture, post-migration counts are **2** Customers, **3** Orders, **3** old edges, and **3** new edges. In live production accepting writes, counts change mid-query; compare at the same **checkpoint or watermark** rather than across skewed snapshots.

### 11.4. Check Missing, Extra, or Cross-Tenant Relationships

~~~cypher
MATCH (o:DemoMigOrder)
OPTIONAL MATCH (c:DemoMigCustomer)-[r:DEMO_MIG_PLACED]->(o)
WITH o, count(r) AS incoming
WHERE incoming <> 1
RETURN o.tenantId AS tenantId,
       o.orderId AS orderId, incoming;
~~~

~~~cypher
MATCH (c:DemoMigCustomer)-[r:DEMO_MIG_PLACED]->
      (o:DemoMigOrder)
WHERE c.tenantId IS NULL
   OR o.tenantId IS NULL
   OR c.tenantId <> o.tenantId
RETURN c.customerId AS customerId,
       o.orderId AS orderId, type(r) AS relationshipType;
~~~

Expect **0 rows** for both. These express the sample domain's invariants; if one Order legitimately maps to multiple Customers, adjust the check rather than forcing real data into an exercise constraint.

### 11.5. Verify Schema and Query Plans

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_mig_'
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, state, type, labelsOrTypes, properties
RETURN name, state, type, labelsOrTypes, properties
ORDER BY name;
~~~

When adding uniqueness constraints, Neo4j creates backing indexes. For critical newly created indexes, wait for **ONLINE** status before declaring new queries ready for load. **POPULATING** or **FAILED** indexes fail the release gate.

~~~cypher
EXPLAIN
MATCH (o:DemoMigOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status;
~~~

**EXPLAIN** only plans without running the query. **PROFILE** executes the query, so run it only on safe read queries in production and compare **Rows, DB Hits, index seeks, and latency** against baseline without requiring identical operator names across Neo4j versions.

## 12. Java Driver and Spring Data Neo4j During Transition

### 12.1. APIs Must Preserve Business Keys

If the API prior to migration returned:

~~~json
{
  "tenantId": "shop-a",
  "customerId": "C-1",
  "orders": ["P-101", "P-102"]
}
~~~

then post-migration it must return the exact same customer and order keys per contract, even though internal Cypher switched labels and relationship types. **Never switch the API contract to Neo4j internal IDs** merely because they are convenient to read via Java Driver.

### 12.2. Java Driver Queries Parameterized by Business Key

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class DemoMigratedQuery {

    public static List<String> findOrders(
            Driver driver,
            String database,
            String tenantId,
            String customerId) {

        try (var session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (c:DemoMigCustomer {
                      tenantId: $tenantId,
                      customerId: $customerId
                    })-[:DEMO_MIG_PLACED]->(o:DemoMigOrder)
                    WHERE o.tenantId = $tenantId
                    RETURN o.orderId AS orderId
                    ORDER BY orderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "customerId", customerId
                    ))
                  .list(record -> record.get("orderId").asString())
            );
        }
    }
}
~~~

Expect **findOrders(driver, dbName, "shop-a", "C-1")** to return **["P-101", "P-102"]** on the fixture. Read queries run via **executeRead**; the Driver lives at application scope while Sessions close after each unit of work.

If the app must immediately read newly written data on a **cluster reader** after a write transaction, use **bookmarks** to preserve **read-your-writes**. Causal chaining does not replace migration validation, yet avoids misdiagnosing replica lag as lost data.

### 12.3. Spring Data Neo4j: Label and Type Changes Require Mapping Updates

When altering the model, verify simultaneously:

- **@Node** target node labels being mapped.
- **@Relationship(type = ..., direction = ...)** matching the new type and direction.
- **@Id** and identity mapping. If the business key combines **tenantId + customerId**, design appropriate composite mapping or custom repository queries; never assume every SDN version automatically composes a key from two fields.
- Custom **@Query** methods—whether they still reference old labels/properties or have been updated.
- Transaction boundaries: dual-write steps must execute atomically within **one database transaction** when both representations live in the same Neo4j database.
- Repository `save` calls can update or delete relationships when mappings diverge; test on fixtures and consider **Neo4jClient/custom Cypher** for complex migrations.

Never place an entire **CALL ... IN TRANSACTIONS** script under **@Transactional** expecting inner batches to commit independently; those are incompatible transaction models. Standard Spring services handling single business operations use **@Transactional**, while batch migrations belong in dedicated jobs/tools.

## 13. Contract Step: Clean Up Legacy Structures Only After Acceptance

**Statements in this section are destructive** to the legacy schema. Run them on test/target databases only after confirming:

1. All new queries and invariants PASS.
2. Zero writers or readers still depend on old labels, properties, or relationships.
3. Restore-tested backups exist and a go/no-go owner signs off.
4. New writes produced during the transition window have been reconciled.

### 13.1. Delete Old Relationships Only Where Replaced

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
MATCH (c)-[fresh:DEMO_MIG_PLACED]->(o)
WHERE old.sourceEventId = fresh.eventId
DELETE old;
~~~

This deletes old edges **only when a matching target edge with the same eventId exists**, avoiding blind deletion. Still, **reconcile completely beforehand**: if any old edge lacks a matching new edge, this query leaves it behind, meaning cleanup gates have not been met.

**Never re-run relationship backfill after deleting all old edges** if provenance matters; preserve audit logs/checkpoints and versioned migrations.

### 13.2. Remove Source Labels and Properties Last

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
REMOVE c:DemoMigLegacyCustomer
REMOVE c.orgId, c.accountNo, c.fullName;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase:DemoMigOrder)
REMOVE o:DemoMigLegacyPurchase
REMOVE o.orgId, o.purchaseNo, o.totalCents, o.orderState;
~~~

**REMOVE label** does not delete the node; **REMOVE property** deletes those properties. This is not an automatic "property rename": new properties must already be **copied and verified** beforehand.

For example, if a consumer still queries `MATCH (:DemoMigLegacyPurchase)`, after this statement it finds nothing even though nodes still exist under **DemoMigOrder**. Hence contract must wait **until after** code changes and a monitoring window.

### 13.3. Drop Legacy Constraints/Indexes After Verifying Dependencies

~~~cypher
DROP CONSTRAINT demo_mig_old_customer_key IF EXISTS;
DROP CONSTRAINT demo_mig_old_purchase_key IF EXISTS;
~~~

This is the **final** step once old schemas are confirmed unused. Never DROP legacy constraints while older writers remain active, or duplicate source records may slip through.

**Never** use **DETACH DELETE** to "change labels" or "refactor models"; it deletes the node along with all its relationships. For in-place migration, the proper sequence is **SET new label, backfill properties, create new relationships, verify, then REMOVE/DELETE exact legacy components**.

## 14. Rollback and Recovery If Migration Fails

| Failure timing | Scenario | Typical response |
|---|---|---|
| **Before writing** | Preflight spots missing/duplicate IDs | Halt, clean source data, do not deploy |
| **After expand** | Only target constraints/indexes added | Leave harmless schema or drop per plan; old app keeps using old schema |
| **Mid-backfill batch** | Some batches committed, others failed | Fix root cause, safely re-run, reconcile full dataset |
| **Post-backfill, pre-switch** | New queries return wrong results; old schema intact | Keep old readers, fix scripts/mappings, re-verify |
| **Post-switch, pre-contract** | New API errors; legacy schema still present | Roll back code when writers/dual-write stay compatible; reconcile new writes |
| **Post-contract** | Legacy labels/properties/edges already deleted | May require compensating migration or **rehearsed backup restore**; code rollback alone fails |

In production with multi-batch commits, **no single transaction exists** to roll back an entire migration once batches commit. Reversibility must be **engineered**, not left to luck.

### 14.1. Do Not Blindly Overwrite New Data by Copying Old Properties Back

For instance, after switch, an Order transitions from **NEW → PAID** in the new model. If a rollback script blindly runs **SET o.status = o.orderState** while legacy `orderState` still says CREATED, you erase the payment event. Therefore:

- Record the exact **source-of-truth cutover timestamp**.
- Track versions or timestamps on new data if reconciliation must determine "which update is newer".
- Avoid unconditional **SET ... = legacyProperty** during rollback.
- Across services, use outbox/event IDs, checkpoints, and controlled replay.

### 14.2. Backups Must Align with Recovery Points

A pre-migration backup helps only if it restores cleanly and you can tolerate or recover writes occurring between backup time and failure detection. If **near-zero RPO** is required, design write continuity, log/backup chains, and reconciliation explicitly. Never assume merely having a backup yields a two-second rollback.

## 15. Typical Mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Creating new Customer nodes when only changing labels | Two nodes for the same customer | **SET label** on existing node when domain entity is unchanged |
| Using **elementId** as a cross-system integration key | Unstable across business contracts | Use business keys with composite tenant scope |
| Querying **accountNo** without **orgId** | Cross-tenant data corruption | Key by **(tenantId, customerId)** |
| Including status/name in MERGE keys | When status changes, MERGE fails to match old node | MERGE strictly on immutable keys |
| Adding new label without backfilling identity properties | New queries fail to find target nodes | Backfill properties in the same phase and verify |
| Using `SET n = {...}` with partial properties | Wipes unlisted properties | Use per-field `SET` or controlled `+=` |
| Using `coalesce` assuming dirty data fixed itself | Stale/wrong values silently persist | Run reconciliation queries and enforce source of truth |
| Changing relationship types by deleting old edges first | Loses direction, metadata, and events | Create new edges, verify, then DELETE old edges |
| Merging multiple events with endpoint-only MERGE | Collapses historical interactions | Model Event nodes/edges keyed by **eventId** |
| Running batches expecting trailing failures to roll back everything | Half-migrated graph | Idempotent batches + checkpoints + full reconciliation |
| Running one-off backfill while old writers keep inserting | Newly created records go missing | Dual-write/CDC or controlled write-freeze window |
| Switching all queries before migration completes | Queries miss unmigrated nodes/edges | Gated cutover and canary checks |
| Dropping legacy constraints while old services still write | Source duplicates enter | Clean up only after contract and consumer checks |
| Comparing only pre/post node counts | Matching totals hide wrong keys or tenant leaks | Reconcile business key sets and relationships |
| Rolling back code after legacy `REMOVE` ran | Old code finds no legacy fields to read | Plan rollback/restore before running contract |

## 16. Practice Exercises

### Exercise 1 — Preserving Identity Across Label Changes

Run the fixture in section 4. Write Cypher to backfill **DemoMigLegacyCustomer → DemoMigCustomer** without creating new nodes. Prove that after running twice, only **2** logical Customers exist and keys **shop-a/C-1**, **shop-b/C-1** remain unchanged.

### Exercise 2 — Analyzing Tenant-Omission Bugs

A migration query looks up Customers by **accountNo = 'C-1'** without **orgId**. Explain how it can attach a shop-a Order to a shop-b Customer. Rewrite the MATCH using **(orgId, accountNo)** and write a query counting cross-tenant edges.

### Exercise 3 — Verifying Status Mapping

Insert an Order with **orderState = 'REFUNDED'** into source data. Run preflight and explain why it must not default to NEW. Add a domain-approved mapping rule, update the backfill query, and write assertions verifying each status.

### Exercise 4 — Replacing Relationships Without Losing Events

Convert all three **DEMO_MIG_PURCHASED** edges to **DEMO_MIG_PLACED**, preserving **sourceEventId → eventId** and **createdAt → occurredAt**. Run the migration a second time. Query to verify target edge count, event IDs, and directions.

### Exercise 5 — Two Events Between the Same Node Pair

Suppose a Customer purchases the same Product twice and the system must retain both events separately. Why does **MERGE (c)-[:BOUGHT]->(p)** lose history? Design a **PurchaseEvent** node with a unique `eventId`, linked to Customer and Product, ensuring event retries create zero duplicates.

### Exercise 6 — Backfill While Writes Continue

Migration starts at 10:00, an old worker creates a new Order at 10:01, and the scan finishes at 10:02. Propose a dual-write, CDC/watermark, or write-freeze mechanism proving the new Order is not missed when switching queries to the new model.

### Exercise 7 — Rollback After Contract

The application switched to the new model, and **orgId/accountNo/purchaseNo** properties plus old edges were deleted. An un-updated service starts failing. Explain why rolling back container images alone is insufficient; propose data rollback, compensating migration, or RPO/RTO-bounded restore.

### Exercise 8 — Java Driver and SDN

Write a Java Driver function querying orders by **tenantId + customerId**, then design a Spring Data Neo4j repository/integration test verifying that **labels**, **relationship types**, **directions**, and business IDs remain intact across the migration.

## 17. Summary

**Safe label, property, and relationship migrations must preserve business identity, not merely node counts.**

For the same entity, prefer **adding the new label on the existing node**, backfilling properties with explicit rules, and preserving **business keys**. When changing relationship types, **create new edges with exact direction and metadata**, verify thoroughly, and only then delete old edges. When multiple events connect the same pair of nodes, never collapse them with a keyless MERGE.

Recommended production workflow:

**Preflight & align mappings → Backup → Create target constraints/indexes → Expand/dual-write → Batch backfill → Reconcile business keys & relationships → Switch Java Driver/SDN queries → Canary/monitor → Contract & clean up legacy.**

Halt rollout immediately upon missing keys, identity conflicts, tenant mismatches, missed writes, or unready indexes. Delete legacy structures only with verified proof, remembering that **rolling back application code does not undo committed migration transactions**.

### Official Neo4j Documentation

- [Neo4j Cypher Manual – SET node labels and properties](https://neo4j.com/docs/cypher-manual/current/clauses/set/)
- [Neo4j Cypher Manual – REMOVE properties and labels](https://neo4j.com/docs/cypher-manual/current/clauses/remove/)
- [Neo4j Cypher Manual – MERGE and concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – CREATE CONSTRAINT and composite uniqueness](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual – Constraints and key constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual – SHOW CONSTRAINTS](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher Manual – SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Java Driver Manual – Run transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
