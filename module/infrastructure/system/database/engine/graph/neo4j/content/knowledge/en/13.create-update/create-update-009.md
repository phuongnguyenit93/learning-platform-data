# Designing Idempotent Updates and Preventing Duplicate Data in Neo4j

## Learning Objectives

After this lesson, you can:

- Explain why a write statement may execute multiple times when applications retry, re-import data, or receive duplicate messages.
- Choose **stable identifying keys**, create **uniqueness constraints**, and use `MERGE` properly to update nodes and relationships.
- Distinguish idempotent operations from operations that increment counters, append to lists, or write the current timestamp.
- Design handling for duplicate events, out-of-order updates, and concurrent writes; verify that the graph does not accumulate duplicate records.

In Neo4j's **property graph** model, an entity is typically a node, a link between entities is a relationship, and both can carry properties. The **Create and Update** chapter focuses on writing data with Cypher so that re-runs do not corrupt the graph structure.

## 1. What Does Idempotent Mean?

A write operation is **idempotent** if executing it again with the **same input** yields the same logical state as executing it once. Denoting `G` as the graph state and `m` as the input message:

\[
f(f(G,m),m)=f(G,m)
\]

For example, a service receives the same customer sync request again due to a timeout, a worker reprocesses a message from a queue, or an import job restarts after an interruption. If the first run created customer `C-101`, subsequent runs must locate that exact node and update it instead of creating another node with the same identifier.

| Write Pattern | Re-running with Same Input | Idempotent? |
| --- | --- | --- |
| `CREATE (c:Customer {customerId: $id})` | Creates an additional node | No |
| `MERGE (c:Customer {customerId: $id})` | Matches the existing node, if found | Yes under suitable conditions; requires constraints for safety under concurrent writes |
| `SET c.name = $name` | Re-assigns the same value | Yes |
| `SET c.points = c.points + 10` | Adds 10 on every run | No |
| `SET c.tags = c.tags + $tag` | Appends duplicate element to the list | No |
| `SET c.updatedAt = datetime()` | Changes the timestamp on every retry | No when considering all properties |

**Scope note:** `MERGE` does not automatically make every query idempotent. The identifying key must be stable, `SET` operations must be appropriate, and multiple concurrent write transactions must be accounted for.

## 2. Define Identity Before Writing Queries

A node must have a **business key** — an identifying key that does not change when other attributes are edited. For example:

- `Customer.customerId` is the customer ID from the source system; name and email are merely updatable data.
- `Order.orderId` is the order ID; order status changes, but identity stays the same.
- In a multi-tenant system, the pair `(tenantId, customerId)` forms the unique identity; two tenants may use the same customer code.
- An event ingested from an external system has a fixed `eventId`, resent intact on retries; never generate a new UUID on each retry.

### Using Uniqueness Constraints to Protect Data

Create constraints **before** running heavy write jobs. The following syntax fits Cypher on modern Neo4j versions supporting uniqueness constraints:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:OrderEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

If `customerId` is unique only **within each tenant**, choose a composite constraint and use **both** fields in every lookup:

~~~cypher
CREATE CONSTRAINT tenant_customer_unique IF NOT EXISTS
FOR (c:TenantCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

A uniqueness constraint prevents two nodes **with the same label** from sharing the same key value when that key is present; it also provides the backing index for efficient lookups. It **does not by default require the property to exist**. Validate or reject inputs missing keys. If the graph already contains duplicate records, resolve the existing duplicates before creating the constraint, or constraint creation will fail.

Avoid choosing mutable names or emails, timestamps, or randomly generated IDs per retry as keys for `MERGE`.

## 3. Upserting Nodes with MERGE and SET

**Upsert** means looking up a record by key: if absent, create it; if present, update its information.

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET
    c.createdAt = datetime($createdAt),
    c.createdBy = $source
SET
    c.displayName = $displayName,
    c.email = $email
RETURN c.customerId AS customerId;
~~~

Example parameters:

~~~json
{
  "customerId": "C-101",
  "createdAt": "2026-11-25T08:00:00Z",
  "source": "crm",
  "displayName": "Nguyễn Lan",
  "email": "lan@example.org"
}
~~~

When re-run with the same parameters:

1. `MERGE` looks up by `Customer.customerId`, creating the node only if not found.
2. `ON CREATE SET` executes only when the node is created; the original creation timestamp is preserved across retries.
3. `SET` assigns the same values, without accumulating or creating another record.

A common mistake is putting a **mutable** property into the identifying pattern:

~~~cypher
// Wrong: displayName is not a key.
MERGE (c:Customer {
  customerId: $customerId,
  displayName: $displayName
});
~~~

When the name changes, Neo4j no longer matches the full pattern. Without a constraint, another node may be created; with a uniqueness constraint on `customerId`, the write statement can report a conflict. The right way is to `MERGE` **only on the key**, then `SET` updatable fields.

**Handling null:** `MERGE` does not accept a key with value `null`; validate `customerId` before invoking the query. In Neo4j, `SET c.email = null` deletes the `email` property: if `null` means "no new data," the application must adopt a policy to skip that field rather than blindly writing `null`. Likewise, normalize casing, whitespace, and tenant codes per business rules **before identification**; `C-101` and `c-101` are distinct values unless normalized.

### Avoid Side Effects That Break Idempotency

Although the following uses `MERGE`, it is **not** idempotent because every call adds points:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
SET c.points = coalesce(c.points, 0) + $earnedPoints;
~~~

If points originate from a transaction with its own `transactionId`, store the event/transaction by its unique ID and compute points from those records. For a "last request received" timestamp property, be explicit that it tracks operational activity (which may change on retries), rather than treating the entire node as invariant after the first run.

## 4. Upserting Relationships Without Creating Duplicate Edges

For a `FOLLOWS` edge, identify both endpoint nodes first, then `MERGE` the relationship:

~~~cypher
MATCH (a:User {userId: $followerId})
MATCH (b:User {userId: $followeeId})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime($followedAt)
RETURN r;
~~~

Create a dedicated constraint on `User.userId`. The query above works when both users already exist and operations run sequentially. If you need to create both users as well, use **two separate node `MERGE` clauses** before `MERGE`ing the edge. Avoid collapsing everything into one pattern:

~~~cypher
// Hard to control: full-pattern MERGE may try to recreate existing nodes.
MERGE (a:User {userId: $followerId})
      -[:FOLLOWS]->
      (b:User {userId: $followeeId});
~~~

**Concurrent writes are a special case:** `MERGE` on an edge, relying solely on the two endpoints, is not a database-level uniqueness constraint for the node pair. If multiple transactions create the same edge simultaneously, add protective mechanisms when duplicate edges must be prevented in every scenario.

One option on Neo4j versions supporting **relationship property uniqueness constraints** is assigning a deterministic `edgeId` and enforcing uniqueness:

~~~cypher
CREATE CONSTRAINT follows_edge_unique IF NOT EXISTS
FOR ()-[r:FOLLOWS]-()
REQUIRE r.edgeId IS UNIQUE;

MATCH (a:User {userId: $followerId})
MATCH (b:User {userId: $followeeId})
MERGE (a)-[r:FOLLOWS {edgeId: $edgeId}]->(b)
ON CREATE SET r.followedAt = datetime($followedAt);
~~~

The application must derive `edgeId` deterministically from **relationship type + source ID + target ID** (or use a fixed link ID from the source), never randomly per retry. For directed relationships, endpoint order is part of the identity; for undirected relationships, canonicalize the order of the two IDs. A unique constraint prevents committing duplicate edges with the same `edgeId`, though the losing transaction may receive a conflict error and must be handled/retried appropriately. If the same `edgeId` points to two different endpoint pairs, that is a source data error that must be detected.

## 5. Receiving Messages Multiple Times: Storing Events by eventId

In synchronized systems, consumers typically must tolerate *at-least-once* message delivery: a message can be redelivered. For example, the message "order `O-42` delivered" has `eventId = EVT-9001`. If every redelivery creates a new event or increments total delivery counts, data becomes corrupted.

The model should use an **event node with a unique identifier** linked to the order:

~~~mermaid
flowchart LR
    M["Receive eventId + payloadHash"] --> U["MERGE OrderEvent by eventId"]
    U --> C{"Do ID and payload match?"}
    C -->|Yes| R["MERGE HAS_EVENT link"]
    C -->|No| X["Report data conflict"]
    R --> OK["Done; retries yield same state"]
~~~

~~~cypher
// Unique constraint already created for OrderEvent.eventId.
MERGE (e:OrderEvent {eventId: $eventId})
ON CREATE SET
    e.orderId = $orderId,
    e.kind = $kind,
    e.payloadHash = $payloadHash,
    e.occurredAt = datetime($occurredAt)
WITH e
WHERE e.orderId = $orderId
  AND e.payloadHash = $payloadHash
MERGE (o:Order {orderId: $orderId})
MERGE (o)-[r:HAS_EVENT]->(e)
RETURN e.eventId AS acceptedEventId;
~~~

`payloadHash` is a stable hash computed over normalized business content, **excluding** fields such as when the consumer received the message. If the query returns no rows because the same `eventId` arrived with a different order or payload, the application must treat that as a **conflict**, not silently report success. When concurrent writes may create the `HAS_EVENT` link, you can also apply a unique key on the relationship as in Section 4 (such as `r.eventId`); configure the constraint and set that key consistently in `MERGE`.

Instead of running `SET o.deliveredCount = o.deliveredCount + 1` on every message receipt, compute it from the unique events:

~~~cypher
MATCH (o:Order {orderId: $orderId})-[:HAS_EVENT]->(e:OrderEvent)
WHERE e.kind = 'DELIVERED'
RETURN count(DISTINCT e) AS deliveredEvents;
~~~

If maintaining a physical counter is strictly required for fast reads, use a workflow that **marks the event as applied and updates the counter in the same transaction**, incrementing only when genuinely processing a new event. Counting directly from the event set is usually easier to verify and debug.

## 6. Preventing Older Updates from Overwriting Newer Ones

Idempotency for the **same message** is not enough if two different messages arrive out of order. For example, `version=7` arrives before `version=6`; if the application blindly applies "last write wins," data can regress to version 6.

If the source system provides a monotonically increasing `sourceVersion` per customer, apply only newer messages:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.sourceVersion = -1
WITH c
WHERE coalesce(c.sourceVersion, -1) < $sourceVersion
SET
    c.displayName = $displayName,
    c.sourceVersion = $sourceVersion
RETURN c.customerId AS appliedCustomerId;
~~~

- First arrival with version 7: data is applied.
- Redelivery of version 7: no further update and no row returned.
- Stale message version 6: does not overwrite.
- Newer message version 8: updates state properly.

The convention here is that `sourceVersion` is a non-negative integer. When the query returns no rows, the application can read back the current version to distinguish "stale/duplicate message" from "invalid data." Two messages with the same version but different payloads must be flagged as a conflict per the data contract.

**Concurrency limitation:** version checking and data writing must execute inside a transaction with a concurrency control policy. For very strict ordering requirements, serialize updates by business key, use optimistic locking or an appropriate locking strategy, and retry the whole transaction on conflict. Do not assume a bare `WHERE` condition resolves every race between concurrent transactions.

## 7. Batch Import and Calling from Java

When syncing many IDs, `UNWIND` combined with `DISTINCT` deduplicates inputs **before** operating on each node:

~~~cypher
UNWIND $customerIds AS customerId
WITH DISTINCT customerId
WHERE customerId IS NOT NULL
  AND trim(customerId) <> ''
MERGE (c:Customer {customerId: customerId})
RETURN count(c) AS processedCustomers;
~~~

Here the list contains only IDs. When importing records with the same ID but **different data**, `DISTINCT` across entire rows does not resolve conflicts: you must decide a record-selection rule based on reliable version/timestamp at the ingestion layer. For large datasets, batch to fit memory and transaction limits; ensure each batch can be safely re-run.

Example Java application using the **Neo4j Java Driver** and parameterized queries:

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

class CustomerSync {
    static String upsert(
            Driver driver, String customerId, String displayName) {
        var params = Map.of(
                "customerId", customerId,
                "displayName", displayName);

        try (Session session =
                     driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> tx.run(
                    """
                    MERGE (c:Customer {customerId: $customerId})
                    SET c.displayName = $displayName
                    RETURN c.customerId AS id
                    """,
                    params).single().get("id").asString());
        }
    }

    public static void main(String[] args) {
        try (Driver driver = GraphDatabase.driver(
                "bolt://localhost:7687",
                AuthTokens.basic("neo4j", "password-from-config"))) {
            upsert(driver, "C-101", "Nguyễn Lan");
            upsert(driver, "C-101", "Nguyễn Lan"); // Same node.
        }
    }
}
~~~

In production systems, load the URI and credentials from secure configuration; the example above only illustrates the call flow. `executeWrite` runs a managed write transaction and may retry on **retryable** errors. Therefore, the callback should perform only graph transaction work: do not send emails, debit accounts, generate new random IDs, or trigger external side effects inside the callback. Not all errors (especially unique constraint conflicts) are automatically retried by the driver; the application must classify errors and design controlled re-read/deduplication handling.

With **Spring Data Neo4j**, declare a stable entity identifier (for example, an `@Id` field mapped to `customerId`), consider `@Version` to detect concurrent updates, and still enforce constraints in the database. Repository configuration or standalone `save` calls do not replace event deduplication rules or identity constraints.

## 8. How to Verify the Solution

After creating constraints and running the upsert query multiple times, check the node count for the same ID:

~~~cypher
MATCH (c:Customer {customerId: 'C-101'})
RETURN count(c) AS customerCount;
// Expected: 1
~~~

Check legacy data for duplicate IDs (before creating constraints) and duplicate links:

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS id, count(*) AS copies
WHERE copies > 1
RETURN id, copies;

MATCH (a:User)-[r:FOLLOWS]->(b:User)
WITH a.userId AS fromId, b.userId AS toId, count(r) AS copies
WHERE copies > 1
RETURN fromId, toId, copies;
~~~

A meaningful test suite should cover the following cases:

| Scenario | Expected Outcome |
| --- | --- |
| Send the same node create/update command 2–10 times | Still only one node per business key with the right properties |
| Replay the same `eventId` and payload | Only one logical event, no unintended accumulation |
| Same `eventId` but different payload | Detected and flagged as a conflict |
| Deliver version 8 then version 7 | Final state retains version 8 |
| Send two concurrent requests creating the same ID | Never commits two duplicate nodes; concurrency error handled properly |
| Missing ID or `null` key | Input rejected cleanly, no malformed node written |
| Retry after timeout mid-import job | Re-running the batch still yields the right logical graph |

## 9. Project Application Checklist

1. Choose an immutable business key; normalize keys and ensure no identifying component is missing.
2. Define uniqueness constraints for nodes or relationships that need protection before running concurrent writes.
3. `MERGE` by **key**, `SET` mutable properties; avoid unconditional `CREATE` in retryable flows.
4. For counters, lists, or events, use stable operation/event IDs; do not accumulate on replay.
5. For multiple distinct updates, use versioning or ordering rules and detect conflicting payloads.
6. Group related writes inside the same transaction; test retries, concurrency, and real duplicate-data scenarios.

**Conclusion:** A safe Neo4j update pipeline requires combining **stable identity + database constraints + semantically sound Cypher queries + retry/transaction handling**. `MERGE` is the core tool for upserts, but end-to-end idempotency also depends on event design, update ordering, and concurrent write policies.
