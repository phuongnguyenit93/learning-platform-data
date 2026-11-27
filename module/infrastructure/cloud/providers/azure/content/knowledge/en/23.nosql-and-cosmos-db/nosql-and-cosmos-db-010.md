# TTL, Unique Keys, and Document Lifecycle Management

An e-commerce application stores temporary shopping carts, session records, notifications, orders, and audit records in Azure Cosmos DB. Not every document should live forever: shopping carts can expire and session tokens must vanish after a window, whereas invoices and audit evidence must be retained per policy. At the same time, two users in the **same tenant** must not create profiles with the same email address, nor should a retried request accidentally insert duplicate documents.

**Azure Cosmos DB for NoSQL** provides core mechanisms for these requirements:

- **Time to Live (TTL):** Automatically expires documents after a specified number of seconds from their last modification.
- **Unique key policy:** Prevents duplicate property combinations **within the same logical partition**.
- **Document lifecycle management:** Designing state machines, retention, soft deletes, change feed processing, archival, purging, and observability so data is neither kept too long nor deleted prematurely.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects to Azure subscriptions, resource groups, Microsoft Entra ID, App Service / Azure Functions / AKS apps, private networking, Storage, monitoring, security, and cost control. Content focuses on **API for NoSQL**; APIs such as MongoDB, Cassandra, and Table have their own feature rules, so never copy these examples verbatim to those APIs.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain containers, items/documents, JSON, partition keys, logical partitions, `id`, and Request Units (RUs).
2. Distinguish TTL disabled, TTL enabled with no default, container default TTL, and item-level TTL overrides.
3. Calculate expiration timestamps from the system **`_ts`** property and explain why item updates reset the timer.
4. Design time-bounded data: sessions, carts, notifications, logs, and intermediate markers.
5. Create containers with TTL and unique key policies via Azure CLI and inspect configurations via Data Explorer / management APIs.
6. Distinguish **`(partition key, id)`** uniqueness from unique keys on a property or tuple of properties.
7. Recognize unique key limits: logical-partition scope, case sensitivity, missing paths treated as `null`, and policy immutability after container creation.
8. Handle HTTP 409 conflicts, retry bugs, race conditions, and system-wide uniqueness requirements.
9. Contrast TTL hard deletion against soft deletes, tombstones, the change feed, and pre-deletion archival.
10. Build controlled lifecycles covering legal holds, retention, backups, auditing, and data erasure requests.
11. Account for the impact of TTL and unique keys on RUs, storage, throughput, and cost.
12. Create a production checklist, migration plan, test scenarios, and troubleshooting runbooks.

Configurations and code below are learning examples only; resource names and data are synthetic. Never execute commands or provision billable resources outside an authorized lab environment.

## 2. Background: Items, Containers, and Partitions

### 2.1. Cosmos DB for NoSQL Data Structure

~~~mermaid
flowchart TD
    A["Azure Cosmos DB account"] --> D["Database: commerce"]
    D --> C["Container: profiles"]
    C --> P1["Logical partition: tenant-a"]
    C --> P2["Logical partition: tenant-b"]
    P1 --> I1["Item: user-001"]
    P1 --> I2["Item: user-002"]
    P2 --> I3["Item: user-001"]
~~~

In this model:

- **Account** is the Azure Cosmos DB resource.
- **Database** holds containers.
- **Container** defines the partition key, indexing policy, unique key policy, and default TTL.
- **Item / document** is a JSON object containing **`id`** and the partitioning property.
- **Partition key** is chosen at container creation to distribute data and load.
- **Logical partition** contains all items sharing a partition key value.
- **Physical partition** is an internal distribution/scaling unit; one logical partition does not map to a fixed physical machine.

Sample item:

~~~json
{
  "id": "user-001",
  "tenantId": "tenant-a",
  "email": "Minh@example.com",
  "emailNormalized": "minh@example.com",
  "displayName": "Minh",
  "state": "active"
}
~~~

For point reads, clients must supply both **`id` and the partition key value**. Cosmos DB maintains system metadata like **`_etag`**, **`_ts`**, and **`_rid`**, visible in responses but never mutated directly by business code.

### 2.2. Distinguishing `id` and Unique Keys

In Cosmos DB for NoSQL, **`id` must be unique within one logical partition**. Two different logical partitions can hold items with the exact same `id`.

Example:

| Partition Key Value | `id` | Valid? | Reason |
|---|---|---|---|
| `tenant-a` | `user-001` | Yes | First item |
| `tenant-a` | `user-001` | No (on second create) | Duplicate `(partition key, id)` |
| `tenant-b` | `user-001` | Yes | Different logical partition |

If **`emailNormalized`** must be unique per tenant when `id` is a separate UUID, `id` uniqueness alone is insufficient. You need a unique key policy or an alternative data model to enforce uniqueness.

### 2.3. What Is an RU?

Cosmos DB measures resource consumption for reads, writes, queries, updates, and deletes in **Request Units (RUs)**. Cost depends on:

- Item size.
- Property count, indexing policy, and unique key policy.
- Read/write rates and query complexity.
- Partition counts and whether queries supply a partition key.
- Provisioned/autoscale throughput or serverless billing model.
- Stored data volume and replication footprint.
- Background work and change feed processing.

**Unique keys and TTL are not infinitely free features.** Benchmark RUs when designing schemas and retention policies.

## 3. What Is TTL?

### 3.1. Definition

**Time to Live (TTL)** specifies how many **seconds** an item may exist starting from its **last modification time**. Once an item exceeds its TTL, Cosmos DB marks it expired and removes it via a background purge as system resources permit.

~~~mermaid
flowchart LR
    W["Create / Update item"] --> TS["Service updates _ts"]
    TS --> E["Calculates expiration = _ts + ttl"]
    E --> V["Item active"]
    V --> X["TTL exceeded"]
    X --> Q["Omitted from queries"]
    Q --> P["Background purge"]
    P --> D["Physically deleted from container"]
~~~

**TTL is not a millisecond-accurate deletion scheduler.** Once expired, an item ceases to appear in query results per Cosmos DB semantics, yet **physical deletion** runs asynchronously and can lag when spare RUs are scarce.

### 3.2. What Is `_ts`?

The system property **`_ts`** is a Unix timestamp in **seconds**, managed by Cosmos DB, representing when the item was last modified.

Illustrative example:

~~~json
{
  "id": "session-101",
  "tenantId": "tenant-a",
  "userId": "user-001",
  "ttl": 1800,
  "_ts": 1795000000
}
~~~

Assuming TTL is enabled on the container, expiration occurs at:

~~~text
expirationEpochSeconds = _ts + ttl
                       = 1,795,000,000 + 1,800
                       = 1,795,001,800
~~~

If the item is updated before expiring, Cosmos DB refreshes **`_ts`** and restarts the TTL clock from the new timestamp. Any valid **replace, upsert, or patch** extends the item's lifetime—even if business logic only intended to update an unrelated field.

**Never try to edit `_ts` manually** to extend a session. If an application requires a fixed legal expiration deadline, see Section 8 on **`expiresAt`** and strategies independent of last-modified TTL.

### 3.3. Container-Level vs. Item-Level TTL

Cosmos DB supports:

- **Container-level default TTL:** Default rule for items without their own `ttl` property.
- **Item-level TTL:** A JSON **`ttl`** property overriding the container default when container TTL is enabled.

Remember that **item-level `ttl` only takes effect when container-level TTL is enabled** (i.e., the container setting is not `null`/omitted).

## 4. Three Container TTL States

### 4.1. `defaultTtl` Values

Across APIs, SDKs, and ARM templates, the property is typically named **`defaultTtl`** or **`DefaultTimeToLive`**. Three states to know:

| Container Default TTL | Meaning | Items Without `ttl` |
|---|---|---|
| **`null` / absent** | TTL **disabled** | Never auto-expire |
| **`-1`** | TTL **enabled**, **no default expiration** | Never auto-expire |
| **`n > 0`** | TTL **enabled** with `n`-second default | Expire `n` seconds after `_ts` |

**`0` is not a valid TTL.** At the item level, `ttl` must likewise be a supported positive non-zero integer or `-1`.

### 4.2. Container and Item Interaction Matrix

| Container `defaultTtl` | Item `ttl` | Outcome |
|---|---|---|
| `null` / absent | Absent | Never expires |
| `null` / absent | `3600` | **Ignored**; never expires |
| `-1` | Absent | Never expires |
| `-1` | `3600` | Expires after 3,600 seconds |
| `-1` | `-1` | Never expires |
| `86400` | Absent | Expires after 24 hours |
| `86400` | `3600` | Expires after 1 hour |
| `86400` | `-1` | Never expires |
| `86400` | `172800` | Expires after 48 hours |

**Trap:** Setting item **`ttl: 600`** while container **`defaultTtl = null`** will not delete the item after 10 minutes.

### 4.3. Container TTL `-1` Does Not Mean “TTL Off”

When container **`defaultTtl = -1`**, TTL is enabled, yet items lacking `ttl` stay forever. You can assign per-item TTLs selectively:

~~~json
{
  "id": "notification-short",
  "tenantId": "tenant-a",
  "ttl": 1800,
  "type": "notification"
}
~~~

Another item with no `ttl`:

~~~json
{
  "id": "notification-archived",
  "tenantId": "tenant-a",
  "type": "notification",
  "archiveStatus": "retained"
}
~~~

In the same container, the first expires 30 minutes after `_ts`, while the second stays indefinitely **under TTL rules**, unless deleted explicitly by a business process.

### 4.4. Item TTL `-1` When Container Has a Positive Default

If `defaultTtl = 604800` (7 days), this item overrides to stay permanently:

~~~json
{
  "id": "audit-legal-hold-001",
  "tenantId": "tenant-a",
  "type": "audit",
  "ttl": -1,
  "retentionReason": "legal-hold"
}
~~~

That item will not auto-expire via TTL. However, **`ttl: -1` alone does not satisfy legal hold or immutable retention**: identities with write permissions can still edit or delete it, so you still need RBAC, locks/backups, auditing, and approval workflows.

### 4.5. Item `ttl: null` Is Invalid

Never write:

~~~json
{
  "id": "bad-item",
  "tenantId": "tenant-a",
  "ttl": null
}
~~~

To inherit the container's default TTL, **omit the `ttl` property entirely**. To exempt an item from auto-expiration in a container with a positive default, set **`ttl: -1`** where supported.

## 5. Practical TTL Patterns

### 5.1. Session Expiring 30 Minutes After Last Activity

~~~json
{
  "id": "session-1",
  "tenantId": "tenant-a",
  "userId": "user-42",
  "sessionState": "active",
  "ttl": 1800
}
~~~

If the app writes a heartbeat onto the item on every request, **`_ts`** advances and TTL slides forward—giving **sliding expiration** if desired. If business rules demand a hard 2-hour cap since login, validate **`absoluteExpiresAt`** in application logic rather than relying solely on item `ttl`.

### 5.2. Temporary Shopping Cart Kept for 14 Days

~~~json
{
  "id": "cart-100",
  "tenantId": "tenant-a",
  "userId": "user-42",
  "items": [
    {"sku": "P-10", "qty": 2}
  ],
  "ttl": 1209600
}
~~~

14 × 24 × 60 × 60 = 1,209,600 seconds. Updating the cart on day 10 resets TTL from that edit—ideal for “delete after 14 days of inactivity.”

### 5.3. API Cache Document Held for 10 Minutes

~~~json
{
  "id": "cache-product-10",
  "tenantId": "tenant-a",
  "cacheKey": "product:P-10",
  "payloadRef": "blob-path-or-small-payload",
  "ttl": 600
}
~~~

TTL cleans stale cache items nicely, yet **does not replace freshness checks** when immediate invalidation is required. When source data changes, cached items remain visible until updated or deleted by the application.

### 5.4. Multi-Year Audit Retention

Audit records follow strict governance policies. When retention or legal holds apply, **never set a short container default TTL hoping to manually stamp `ttl: -1` on important records**. Separate containers or storage tiers with governed retention, encryption, and audit controls.

### 5.5. Common Lifecycle Matrix

| Document Type | Discussion TTL | Key Caveats |
|---|---|---|
| Session token state | Minutes / hours | Absolute expiry and revocation |
| Inactive shopping cart | Days / weeks | Sliding expiration from `_ts` |
| Transient notification | Hours / days | Read vs. unread distinction |
| ETL processing marker | Hours / days | Must outlast retries and reconciliation |
| API cache item | Minutes | Freshness and invalidation |
| Business order | Usually no short TTL | Reconciliation, archiving, compliance |
| Security audit event | Per approved retention policy | Immutability, audit, legal hold |
| GDPR / deletion queue | Never rely on TTL as sole erasure SLA | Verify deletion across copies and backups |

Durations above are design examples—**not legal retention mandates**.

## 6. Configuring TTL via Azure Portal and Azure CLI

### 6.1. Lab Environment Preparation

Assume existing resources:

~~~text
Subscription: <SUBSCRIPTION_ID>
Resource group: rg-cosmos-lab
Cosmos DB account (API for NoSQL): cosmos-commerce-lab
Database: commerce
Container to create: sessions
Partition key path: /tenantId
Default TTL: 1800 seconds
~~~

You need Azure management-plane permissions. Provisioned resources and throughput can incur charges. No live Azure CLI commands are executed in authoring this lesson.

Verify context:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az cosmosdb show \
  --resource-group rg-cosmos-lab \
  --name cosmos-commerce-lab \
  --query "{name:name,kind:kind,locations:locations}" \
  --output json
~~~

Confirm the **API for NoSQL account** and database exist in the intended subscription and region.

### 6.2. Creating a Container with Default TTL

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --partition-key-path "/tenantId" \
  --ttl 1800 \
  --throughput 400
~~~

In a lab, **`--throughput 400`** illustrates dedicated provisioned throughput; use it only when compatible with your account/throughput model. If the database uses shared throughput, omit container-level throughput as appropriate.

`--ttl` sets the **container** TTL, not per-item TTL. CLI options vary across Azure CLI releases; verify with **`az cosmosdb sql container create --help`** first.

### 6.3. Inspecting Container Configuration

~~~bash
az cosmosdb sql container show \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --query "{id:resource.id,partitionKey:resource.partitionKey,defaultTtl:resource.defaultTtl}" \
  --output json
~~~

If your CLI/API version outputs a different JSON structure, inspect the full JSON response for `defaultTtl`, partition key, and `uniqueKeyPolicy`. Reading management configuration does not prove TTL purging has run.

### 6.4. Enabling TTL in the Azure Portal

In the Azure Portal:

1. Open the Cosmos DB account → **Data Explorer**.
2. Expand the database and container.
3. Open **Settings** or **Scale & Settings** per UI.
4. Locate **Time to Live**.
5. Select **Off**, **On (no default)**, or **On** with seconds.
6. Save and verify the setting.

Exercise extreme caution when switching from TTL disabled to a positive default on a container holding legacy data: items with **old `_ts` values** immediately qualify for expiration and deletion. Review retention, backups, and rollback plans **before** applying to production.

### 6.5. Enabling TTL with No Default Expiration

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name mixed-lifecycle \
  --partition-key-path "/tenantId" \
  --ttl -1 \
  --throughput 400
~~~

Items without `ttl` will not expire automatically; only items with a positive `ttl` expire. **`-1` does not delete everything immediately, nor does it disable TTL.**

### 6.6. Updating TTL on an Existing Container

Unlike **unique key policies—which are immutable after container creation**—TTL can be updated via management SDKs or CLI. Example syntax:

~~~bash
az cosmosdb sql container update \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name sessions \
  --ttl 3600
~~~

Before altering TTL:

- Identify which existing items will expire sooner or later.
- Evaluate compliance and business retention impacts.
- Check indexing and throughput configurations.
- Confirm backup/restore coverage for critical data.
- Test in staging with synthetic historical items.
- Record approval and monitor purge volume.

Never pass `--ttl 0` to “turn off TTL”; use the API/SDK mechanism to clear/set `defaultTtl` to `null`. Switching to `-1` leaves TTL enabled with no default—**not the same as `null`**.

## 7. Setting Per-Item TTL with the Python SDK

### 7.1. Authentication Recommendation

Azure-hosted apps should prefer **Microsoft Entra workload identity / managed identity** wherever supported by the SDK and API for NoSQL, paired with Cosmos DB **data-plane RBAC**. Never embed account keys in source code.

Python 3.x example using compatible **`azure-cosmos`** and **`azure-identity`** packages:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]
credential = DefaultAzureCredential()

client = CosmosClient(endpoint, credential=credential)
database = client.get_database_client("commerce")
container = database.get_container_client("sessions")
~~~

Locally, `DefaultAzureCredential` picks up developer tooling credentials; in Azure, it uses managed identity. Those **can be two completely different principals**, so assign dev and prod permissions separately and test credentials. Azure management role `Contributor` does not grant item read/write permissions without proper Cosmos data-plane RBAC.

### 7.2. Creating a Session Item with `ttl`

~~~python
from uuid import uuid4

session = {
    "id": f"session-{uuid4()}",
    "tenantId": "tenant-a",
    "userId": "user-42",
    "status": "active",
    "ttl": 1800
}

created = container.create_item(body=session)
print("Session created:", created["id"])
~~~

Never print tokens or PII payloads. For sensitive workflows, use deterministic business/idempotency IDs on creation rather than minting a fresh random UUID on every retry.

### 7.3. Reading via Point Read

~~~python
session_id = created["id"]

current = container.read_item(
    item=session_id,
    partition_key="tenant-a"
)

print(current["id"], current.get("status"))
~~~

Supplying the partition key makes a point read far cheaper than cross-partition queries when `id` and tenant are known. Once expired, handle `NotFound` cleanly—**without assuming physical deletion finished at the exact expiration second**.

### 7.4. Overriding TTL on an Individual Item

If the container defaults to 1,800 seconds while a test session needs 300 seconds:

~~~python
session["ttl"] = 300
container.upsert_item(body=session)
~~~

**`upsert` is not safe for every workflow**: if an item with that `id` and partition key already exists, it overwrites per API semantics and resets `_ts`. For contended data, use optimistic concurrency via `_etag`/`If-Match` and conditional operations.

### 7.5. Item Modifications Reset `_ts`

Suppose a notification must expire exactly 1 hour after creation, yet the app updates **`read: true`** at minute 59. With only `ttl: 3600`, `_ts` resets and expiration shifts another hour out—creating a retention bug.

Mitigations:
- Separate **frequently mutated state** from **objects with strict deadlines** into distinct items or containers.
- Store **`expiresAtUtc`** and enforce it in application logic and queries.
- Recompute remaining `ttl` on updates while guarding against races and clock skew.
- Use timers/workers for hard deadlines and post-delete verification.
- Avoid writing unnecessary metadata updates onto TTL-sliding items.

## 8. Sliding Expiration vs. Absolute Expiration

### 8.1. Sliding Expiration

If policy states “expire cart after 14 days **of inactivity**,” `_ts`-based TTL fits naturally:

~~~text
Create cart: Day 0      → expected expiration Day 14
Update cart: Day 10     → _ts advances
New expected expiration → Day 24
~~~

Update only on **genuine user activity** that should extend lifetime; avoid blind heartbeats that keep resetting `_ts` endlessly unless intended.

### 8.2. Absolute Expiration

If policy states “token expires strictly 60 minutes after login,” updates must never extend the deadline:

~~~json
{
  "id": "session-absolute-1",
  "tenantId": "tenant-a",
  "createdAtUtc": "2026-11-20T08:00:00Z",
  "expiresAtUtc": "2026-11-20T09:00:00Z",
  "ttl": 3600
}
~~~

**`expiresAtUtc` is an application-managed business field**, whereas Cosmos DB computes TTL strictly from `_ts + ttl`. The application must **check `expiresAtUtc` on every authorization**, even if the item has not yet been purged. When updating near expiration, recompute remaining `ttl` without extending past policy.

### 8.3. Formula to Recompute Remaining `ttl`

~~~text
remainingSeconds = floor(expiresAtEpochSeconds - currentEpochSeconds)
~~~

If `remainingSeconds <= 0`, never write `ttl = 0` hoping Cosmos DB deletes it instantly. Execute the expired/rejected branch, then delete or handle per policy with concurrency checks. If `remainingSeconds > 0`, set `ttl` to the remaining seconds while accounting for network latency, retries, and clock skew.

### 8.4. TTL Does Not Replace Token Revocation

A revoked session must be rejected immediately by authentication logic without waiting for background purging. Auth flows must check revocation/expiry state or use dedicated revocation mechanisms. TTL is **data cleanup**, never your sole authorization control.

## 9. Unique Keys in Cosmos DB for NoSQL

### 9.1. What Do Unique Keys Prevent?

Suppose a multi-tenant SaaS manages user profiles. Within **`tenant-a`**, two accounts cannot share the same normalized email, whereas **`tenant-b`** may still use that email independently.

~~~json
{
  "id": "profile-001",
  "tenantId": "tenant-a",
  "email": "Minh@Example.com",
  "emailNormalized": "minh@example.com"
}
~~~

When the container has partition key path **`/tenantId`** and unique key path **`/emailNormalized`**, Cosmos DB blocks creating another item with the same **`tenantId` and `emailNormalized`**, regardless of its `id`.

~~~mermaid
flowchart TD
    W["Create profile"] --> P["Resolve logical partition /tenantId"]
    P --> U["Check unique key /emailNormalized"]
    U --> C{"Email already exists in tenant?"}
    C -->|No| OK["Create item succeeds"]
    C -->|Yes| X["HTTP 409 Conflict"]
~~~

**Unique key policies are server-side constraints**, not just client checks. Two concurrent requests attempting to insert the same value in one logical partition cannot both succeed when the constraint is configured properly.

### 9.2. Uniqueness Scope Is the Logical Partition

Example with unique key **`/emailNormalized`** and partition key **`/tenantId`**:

| `tenantId` | `id` | `emailNormalized` | Valid? |
|---|---|---|---|
| `tenant-a` | `p1` | `minh@example.com` | Yes |
| `tenant-a` | `p2` | `minh@example.com` | No — unique key conflict |
| `tenant-b` | `p3` | `minh@example.com` | Yes — different logical partition |
| `tenant-a` | `p4` | `lan@example.com` | Yes |

**Uniqueness is NOT enforced across the entire container when items live in different logical partitions.** If emails must be globally unique across all tenants, a unique key on a `/tenantId`-partitioned container **cannot enforce it**.

### 9.3. `id` and Unique Keys Complement Each Other

- **`id`:** Identifies the item; `(partition key value, id)` must be unique.
- **Unique key:** Enforces uniqueness on non-`id` properties such as `emailNormalized`, `externalRef`, or multi-field combinations.
- **Partition key:** Sets the scope within which the constraint applies and governs scale/distribution.

If a stable business ID already uniquely identifies items within a tenant, making **`id`** that deterministic value may avoid redundant unique keys—balancing against public ID exposure, PII, mutability, access patterns, and partitioning.

## 10. Unique Key Policy Is Set at Container Creation

### 10.1. Cannot Be Added or Edited After Creation

This is one of the sharpest differences from TTL:

- **Container TTL can be updated** via supported APIs/SDKs.
- **Unique key policies must be defined when creating the container**, and cannot be modified on that container afterward.

If a production container already exists without a required unique key, you cannot run an `UPDATE` to add one. You must:

1. Design a new container with the proper partition key and unique key policy.
2. Audit source data for existing duplicates and missing paths.
3. Migrate items while resolving conflicts cleanly.
4. Sync mutations arriving during migration as needed.
5. Cut over application reads and writes in a controlled rollout.
6. Verify counts, business invariants, and routing.
7. Retire the old container only after retention/rollback windows and approval.

### 10.2. Unique Key Policy JSON Schema

A policy with **one** unique constraint on email:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    }
  ]
}
~~~

A policy with **two** independent constraints:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    },
    {
      "paths": ["/externalAccountId"]
    }
  ]
}
~~~

Above, each constraint is enforced independently: two items in the same tenant sharing either `emailNormalized` or `externalAccountId` are rejected.

### 10.3. Composite Unique Keys

To make the combination **`countryCode + taxNumber`** unique:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/countryCode", "/taxNumber"]
    }
  ]
}
~~~

Meaning: the tuple must be unique **within one logical partition**. Two items with the same `taxNumber` in different `countryCode`s are allowed; two items matching on both fail.

**A composite constraint does not make each individual field unique on its own.** To enforce `email` alone AND `(countryCode, taxNumber)` together, declare **two separate entries** in `uniqueKeys`.

### 10.4. Policy Limits

Per Azure Cosmos DB for NoSQL documentation, unique key policies enforce limits:

- Up to **10 unique key constraints/combinations** per container.
- Up to **16 unique key paths total** across the policy.
- Slightly higher RU charges on creates, updates, and deletes compared to containers without unique keys.

Product limits can evolve; verify current docs at container creation time. Avoid using unique keys as a catch-all substitute for business validation or full-text uniqueness.

## 11. Unique Key Traps: `null`, Optional Fields, and Case Sensitivity

### 11.1. Missing Paths Are Treated as `null`

Cosmos DB for NoSQL **does not support sparse unique keys** in the sense of SQL filtered unique indexes. If a unique key property is **absent** from an item, it participates in uniqueness checks as **`null`**.

Example with unique key **`/emailNormalized`**, `tenantId = tenant-a`:

~~~json
{
  "id": "profile-100",
  "tenantId": "tenant-a",
  "displayName": "User without email"
}
~~~

This item occupies the `null` slot for `/emailNormalized`. A second item in `tenant-a` that also omits `emailNormalized` triggers a **unique constraint conflict** because both evaluate to `null`.

Never assume “missing path = unindexed = skipped by unique constraint” as in sparse SQL indexes.

### 11.2. Designing Around Optional Fields

If email is optional for many items, consider:

- **Separate containers:** Records with emails live in a container with the unique policy; email-less records live elsewhere.
- **Intentional unique placeholders** per item when email is absent, ensuring placeholders never collide with real values or leak into business logic.
- **Business reservation container:** Insert an email claim only when an email exists, instead of enforcing unique keys on optional fields in the main container.
- **Adjust partition/item model** if uniqueness applies only to one sub-type.
- **App checks + transactional coordination** when schemas cannot change yet race protection is mandatory.

Never use arbitrary placeholders that cause downstream code to mistake them for valid email addresses or break privacy/search logic.

### 11.3. Unique Key Paths Are Case-Sensitive

JSON property names are case-sensitive. **`/emailNormalized`** differs from **`/EmailNormalized`** and **`/emailnormalized`**.

If the policy declares:

~~~json
{
  "uniqueKeys": [
    {
      "paths": ["/emailNormalized"]
    }
  ]
}
~~~

Yet an item writes:

~~~json
{
  "id": "profile-200",
  "tenantId": "tenant-a",
  "EmailNormalized": "minh@example.com"
}
~~~

Cosmos DB sees **`/emailNormalized`** as missing/`null`—causing future missing-key writes to fail with 409 on `null`. Prevent this via:

- Canonical property names enforced by JSON contracts.
- Schema validation in the app or ingestion pipeline.
- Automated tests covering field-name variations.
- Avoiding silent field renames across deployments.
- Double-checking policy paths before container creation since they are immutable.

### 11.4. Unique Key Values Are Also Case-Sensitive

With unique key **`/email`**, these two strings:

~~~text
Minh@Example.com
minh@example.com
~~~

Are treated as **distinct values** under Cosmos DB's case-sensitive comparison. If business logic requires case-insensitive uniqueness, store a canonicalized **`emailNormalized`** property and enforce the unique key on it.

Production email normalization must account for IDN/Unicode domains, whitespace, case folding, and provider semantics. Simple lab helper:

~~~python
def normalize_email(raw: str) -> str:
    return raw.strip().casefold()
~~~

This is an illustrative helper—**not a complete international email normalization standard**. Verify compatibility rules before applying uniform case folding in production.

### 11.5. Multiple Unique Keys and Composite `null`s

For a composite constraint on **`/countryCode`** and **`/taxNumber`**, an item missing `taxNumber` still registers as `(countryCode, null)`. Two items sharing `countryCode` with missing `taxNumber` collide inside the same partition.

Safe rule: every property referenced in a unique key should be **required, consistently typed, and canonicalized** across items in that container.

### 11.6. Unique Keys Do Not Replace Referential Integrity

Unique keys only block duplicate declared paths within a logical partition. They do not enforce:

- Foreign keys to other items or containers.
- Valid business state transitions (`active → suspended → deleted`).
- Non-negative balances across complex workflows.
- Per-tenant query authorization.
- Cross-partition uniqueness.
- Audit retention prior to TTL expiration.

Those require explicit data models, transactions, and application rules.

## 12. Creating a Container with Unique Keys and TTL via Azure CLI

### 12.1. `profiles` Container for a Multi-Tenant SaaS

Setup:

~~~text
Account: cosmos-commerce-lab
Database: commerce
New container: profiles
Partition key path: /tenantId
Unique key path: /emailNormalized
Container TTL: -1 (enabled with no default expiration)
Throughput: 400 RU/s in lab where applicable
~~~

Illustrative Bash / Azure Cloud Shell command:

~~~bash
az cosmosdb sql container create \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name profiles \
  --partition-key-path "/tenantId" \
  --unique-key-policy '{"uniqueKeys":[{"paths":["/emailNormalized"]}]}' \
  --ttl -1 \
  --throughput 400
~~~

In Windows PowerShell, quoting rules differ from Bash, so adjust **`--unique-key-policy`** quoting accordingly. In CI/CD pipelines, store the policy JSON in a **reviewed IaC artifact** or file parameter where supported. This lesson creates no auxiliary JSON files.

**Never re-run `create` expecting to “update unique keys”** on an existing container. Verify resource names, throughput mode, and partition key upfront, and check `az cosmosdb sql container create --help` for your CLI version.

### 12.2. Inspecting the Policy After Creation

~~~bash
az cosmosdb sql container show \
  --resource-group rg-cosmos-lab \
  --account-name cosmos-commerce-lab \
  --database-name commerce \
  --name profiles \
  --output json
~~~

Inspect the relevant properties in the response:

~~~json
{
  "resource": {
    "id": "profiles",
    "partitionKey": {
      "paths": ["/tenantId"]
    },
    "defaultTtl": -1,
    "uniqueKeyPolicy": {
      "uniqueKeys": [
        {
          "paths": ["/emailNormalized"]
        }
      ]
    }
  }
}
~~~

The JSON above is a **structural excerpt for illustration**, not the complete ARM response or live Azure output. Inspect your actual API response if CLI versions differ.

### 12.3. Practicing via Data Explorer

1. Open Cosmos DB account → **Data Explorer**.
2. Inspect database `commerce` and create container `profiles`.
3. Set the partition key path.
4. Define the unique key policy upfront in the UI.
5. Configure TTL as needed.
6. Review throughput, indexing, and container name.
7. Create the container and verify the saved policy.
8. Attempt to insert two documents with the same `emailNormalized` in the same tenant.
9. Test the same email in a different tenant.
10. Log response statuses and RU charges in the lab without real PII.

**Unique key policies cannot be edited on the container after creation**, even though the UI displays them.

## 13. Hands-On: Testing Unique Keys with the Python SDK

### 13.1. Connecting to the `profiles` Container

Use the Cosmos DB SDK with managed identity and data-plane permissions:

~~~python
import os

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.identity import DefaultAzureCredential

client = CosmosClient(
    os.environ["COSMOS_ENDPOINT"],
    credential=DefaultAzureCredential()
)
container = (
    client.get_database_client("commerce")
    .get_container_client("profiles")
)
~~~

This assumes Entra data-plane RBAC is active and your identity holds item creation permissions. On 403, verify the **Cosmos DB data-plane role assignment** and networking rather than escalating Azure management RBAC blindly.

### 13.2. Creating the First Profile

~~~python
first = {
    "id": "profile-001",
    "tenantId": "tenant-a",
    "email": "Minh@Example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Minh",
    "state": "active"
}

result = container.create_item(body=first)
print(result["id"])
~~~

The **`/emailNormalized`** unique key policy is enforced server-side within logical partition `tenant-a`.

### 13.3. Attempting to Insert a Duplicate Value

~~~python
duplicate = {
    "id": "profile-002",
    "tenantId": "tenant-a",
    "email": "MINH@example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Duplicate profile",
    "state": "active"
}

try:
    container.create_item(body=duplicate)
except CosmosResourceExistsError as exc:
    if exc.status_code == 409:
        print("Conflict: email already in use in this tenant")
    else:
        raise
~~~

Expect **HTTP 409 Conflict**. Exact error text may mention ID or unique index and varies by SDK/server; never parse prose strings to classify business error codes.

**Never fall back to blind `upsert` on a 409**: upserting with a different `id` still hits the unique constraint, while upserting with the existing `id` could silently overwrite a real user's profile.

### 13.4. Different Tenants May Share the Same Email

~~~python
other_tenant = {
    "id": "profile-003",
    "tenantId": "tenant-b",
    "email": "Minh@Example.com",
    "emailNormalized": "minh@example.com",
    "displayName": "Minh in tenant-b",
    "state": "active"
}

container.create_item(body=other_tenant)
~~~

With no external constraints, this succeeds because `tenant-b` is a separate logical partition.

### 13.5. Testing Missing Keys and Case Mismatches

~~~python
missing_email = {
    "id": "profile-010",
    "tenantId": "tenant-a",
    "displayName": "No email provided"
}

wrong_case = {
    "id": "profile-011",
    "tenantId": "tenant-a",
    "EmailNormalized": "abc@example.com"
}
~~~

Both omit the exact **`emailNormalized`** property. In a container with unique key `/emailNormalized`, one missing-key item succeeds, while the second missing-key item in `tenant-a` collides on `null`. Run this test in a clean tenant/partition to avoid noise from old lab items.

### 13.6. Case-Sensitive Value Test

~~~python
case_1 = {
    "id": "case-1",
    "tenantId": "tenant-c",
    "emailNormalized": "A@example.com"
}

case_2 = {
    "id": "case-2",
    "tenantId": "tenant-c",
    "emailNormalized": "a@example.com"
}
~~~

Under case-sensitive value semantics, both coexist. That is why values must be canonicalized before writing whenever case-insensitive uniqueness is required.

### 13.7. Concurrency Test to Prove Uniqueness

A proper concurrency test fires multiple parallel requests with:

~~~text
tenantId = tenant-race
emailNormalized = race@example.com
distinct id per request
~~~

Only **one** request may succeed under the constraint; all others receive 409 (ignoring unrelated network/test errors). If an app simply runs a query “does this email exist?” followed by `create` **without a server-side constraint**, concurrent requests both see “not found” and both insert duplicates.

## 14. When System-Wide Uniqueness Is Required

### 14.1. The Partition-Scoped Uniqueness Gap

Suppose business rules require emails to be unique **across the entire platform**, regardless of tenant. Yet `profiles` is partitioned by `tenantId`, so `/emailNormalized` only enforces uniqueness **per tenant**.

Options to evaluate:

1. **Adjust partition key / data model** so all items needing uniqueness share one logical partition—if scale/size fits; never cram massive global user bases into one partition just for global uniqueness.
2. **Identity claim / reservation container:** Store a document keyed deterministically by `emailNormalized` in a partition designed for email claims, using create-only writes to catch conflicts.
3. **Dedicated identity provider:** Use Microsoft Entra ID or an identity service enforcing global business uniqueness.
4. **External transactional store:** Use a database supporting global uniqueness if cross-entity transactions are required.

### 14.2. Reservation Container Pattern

A dedicated container holding email claims:

~~~json
{
  "id": "email:sha256-of-normalized-email",
  "claimBucket": "by-email",
  "ownerTenantId": "tenant-a",
  "profileId": "profile-001",
  "status": "reserved"
}
~~~

The **`id`** is derived deterministically from the canonicalized email—for example, via a hash to avoid exposing raw PII in IDs. Pair a create-only operation with a deterministic `(id, partition key)` routing all claims for the same email to the exact same logical partition.

However, creating a claim in Container A and a profile in Container B **has no automatic cross-container ACID transaction**:

~~~text
Claim created successfully
        |
        v
Profile creation fails due to network / validation
        |
        v
Claim stays reserved with no profile
~~~

You need sagas/compensation, `pending` states, timeouts, reconciliation workers, and idempotency. **Never put a short TTL on active claims** that might expire and let someone else hijack the email before recovery finishes.

### 14.3. Transactional Batch Only Within One Logical Partition

Cosmos DB for NoSQL supports transactional batches for items sharing the **same logical partition key value** in one container per SDK/API support. Never treat transactional batch as an atomic commit across containers or partitions.

When an invariant spans partitions, design around idempotency, sagas, or an authoritative store.

## 15. How Do TTL and Unique Keys Interact?

### 15.1. When Is a Unique Value Freed After Expiration?

Suppose in `tenant-a`, an item has `emailNormalized = minh@example.com` and `ttl = 600`. Once TTL expires, Cosmos DB queues background deletion. Never build logic assuming **the unique value becomes reusable at exact second 600**:

- The item may already be hidden from queries.
- Physical purging may not have finished yet.
- Constraint release timing depends on runtime/SDK and load.
- Recreating the same unique value during the transition window can hit race conflicts.
- Clients should handle 409 cleanly and retry within bounds if appropriate.

If business logic needs **immediate, deterministic release** of an email or username, use an explicit state transition or conditional delete; treat TTL strictly as background cleanup.

### 15.2. Do Not Expire Profiles Just to Free an Email

A closed profile may need long-term retention for auditing even though the email can be re-registered. Placing `/emailNormalized` as a unique key directly on the main profile container creates conflict between:

- Retaining the old profile as evidence.
- Allowing a new account to claim that email.

Solutions:

- Separate **active identity claims** from **historical profiles**.
- On account closure, release/update the claim via workflow while preserving an immutable audit record.
- Move closed profiles to an archive container under proper retention policies where permitted.
- Never put TTL on audit records just to “free” a unique key.
- Log reason, approver, and timestamp if email reassignment is governed by compliance.

### 15.3. Never Protect Uniqueness with Uncontrolled TTLs

If an email reservation record carries a positive TTL and a downstream service stalls, TTL could delete the claim before profile creation finishes—allowing a second request to claim the email and cause duplicate ownership. Claims need explicit lifecycles (`pending`, `committed`, `released`, `expired`) driven by deadlines and reconciliation.

## 16. Document Lifecycle Management: Create, Update, Archive, Delete

### 16.1. Model the Lifecycle as a State Machine

A document passes through richer states than just “exists or deleted”:

~~~mermaid
flowchart TD
    C["Created"] --> A["Active"]
    A --> U["Updated"]
    U --> A
    A --> S["Soft Deleted / Archived"]
    S --> R["Restored per policy"]
    R --> A
    S --> H{"Legal hold?"}
    H -->|Yes| L["Retained / Hold"]
    H -->|No| E["Eligible for TTL / purge"]
    L --> P["Release hold with approval"]
    P --> E
    E --> D["Physically Deleted"]
    D --> V["Verify deletion + reconcile copies"]
~~~

This state machine is **application-enforced**, not built into Cosmos DB. TTL handles automatic expiration and purging—it never checks legal holds or archives data to Blob Storage automatically.

### 16.2. Classify Data Before Choosing TTL

Sample inventory:

| Document Type | Data Owner | Last Activity | Retention | Deletion / Archive |
|---|---|---|---|---|
| Session | Authentication service | Login / refresh | Short | TTL + auth expiry |
| Cart | Shopping service | User activity | Inactivity policy | TTL or selective archive |
| Notification | Notification service | Delivered / read | UX-driven | TTL after sufficient window |
| Process marker | Data pipeline | Completed | Must outlast retries | TTL after reconciliation |
| Order | Commerce service | Fulfilled / refunded | Business/legal policy | Archive before delete if allowed |
| Payment record | Payments service | Settled / disputed | Contractual / statutory | Separate retention and audit |
| Security event | Security team | Recorded | Security/compliance policy | Evaluate immutability/audit |
| Profile | Identity service | Deactivated | Privacy / retention | Soft delete / claim release / reconciliation |

Never slap `defaultTtl = 86400` onto a container holding sessions, invoices, and audit evidence together when retention rules diverge. Separate containers by access patterns, partition keys, lifecycles, and security.

### 16.3. Hard Delete

**Hard delete** removes an item from the container via SDK/API calls or TTL purge. Afterward, point reads and queries no longer return it—though erasure across backups, replicas, exports, logs, and analytical copies must be handled independently.

Use hard delete when:

- Cached/temporary items need no recovery.
- Retention policies permit deletion.
- Consumers do not rely on latest-version change feed delete events.
- No legal holds or active references remain.

### 16.4. Soft Delete

**Soft delete** stamps a flag/state instead of deleting immediately:

~~~json
{
  "id": "profile-001",
  "tenantId": "tenant-a",
  "emailNormalized": "minh@example.com",
  "state": "deleted",
  "deletedAtUtc": "2026-11-20T10:30:00Z",
  "ttl": 86400
}
~~~

Workflow:

1. API verifies caller authorization to request deletion.
2. Check business holds and retention rules.
3. Transition **`state = deleted`** via a conditional write.
4. Record `deletedAtUtc`, correlation ID, and an audit entry.
5. Consumers update search indexes, caches, and replicas from the soft-delete event.
6. Once downstream processing is confirmed, let TTL purge or run an explicit delete.
7. Track copies and backups per independent retention policies.

**TTL still counts from `_ts` after the soft-delete write.** `ttl: 86400` means roughly one day after the last mutation to `_ts`—not necessarily one day after `deletedAtUtc` if anything modifies the item later.

### 16.5. Soft Delete Does Not Hide Data from Unauthorized Callers

An item with **`state=deleted`** still exists and remains readable to any caller with data-plane permissions. Every query, API read, and background consumer must filter by state:

~~~sql
SELECT c.id, c.displayName
FROM c
WHERE c.tenantId = @tenantId
  AND c.state = "active"
~~~

This Cosmos DB for NoSQL query illustrates the filter; if another query forgets the state predicate, soft-deleted records leak back out. Scrub/anonymize sensitive fields or restrict permissions per policy rather than trusting application filters alone.

### 16.6. Archive Before Deletion

A sample archival pipeline:

~~~mermaid
flowchart LR
    C["Cosmos DB active container"] --> F["Change feed / export workflow"]
    F --> B["Azure Blob Storage archive"]
    B --> V["Verify checksum, schema, access, retention"]
    V --> M["Mark archived / soft deleted"]
    M --> T["TTL / approved hard deletion"]
    T --> A["Audit + reconciliation"]
~~~

Never assume TTL **automatically archives items to Blob Storage**. TTL only expires and deletes; archival is application/pipeline work. Set states and verify archive checksums before assigning short TTLs.

## 17. Change Feed and Deletion Handling Limitations

### 17.1. Latest-Version Change Feed

In **latest-version mode**, Cosmos DB for NoSQL surfaces latest versions from creates and updates. It **does not emit delete operations** as events alongside inserts and updates.

Consequences:

- TTL hard deletions generate no delete event in the latest-version feed.
- If soft delete is an **update**, consumers see the `deleted` state provided they read in time.
- Intermediate updates may coalesce if an item mutates rapidly before the consumer reads.
- If an item is purged by TTL before the consumer reads it, the soft-delete marker disappears from the feed.
- Never use the latest-version change feed as complete proof of every deletion.

### 17.2. Soft-Delete Marker Pattern

Example timeline:

~~~text
10:00 Item is active
10:05 Update state=deleted, ttl=86400
10:06 Change feed consumer reads soft-deleted item
10:07 Consumer removes entry from search index and emits audit
Next day Cosmos DB purges the item via TTL
~~~

If the consumer is down longer than `ttl`, it may miss the marker completely in latest-version mode. Set soft-delete marker retention **longer than worst-case consumer lag + recovery window**, paired with reconciliation.

### 17.3. All Versions and Deletes Change Feed

On supported accounts/configurations, **all versions and deletes mode** provides:

- Intermediate update versions.
- Create, update, and delete events.
- Metadata distinguishing TTL-driven deletions.
- Access to changes within the **continuous backup retention window**.

Verify current prerequisites and capabilities: this mode ties to **continuous backup**, API for NoSQL, feature availability/enrollment, and account limits. Never assume every account has it enabled or retains history indefinitely.

Specifically, **TTL delete events appear when the item is actually purged**, not necessarily at the exact second TTL expires.

### 17.4. Comparing the Two Modes

| Criterion | Latest-Version Mode | All Versions and Deletes Mode |
|---|---|---|
| Creates / updates | Yes, per latest-version semantics | Yes, including intermediate versions |
| Explicit deletes | Not emitted as delete events | Yes, where mode is supported |
| TTL deletes | Not emitted as delete events | Yes, with TTL metadata on purge |
| History completeness | Intermediate edits not guaranteed | Complete within retention window per semantics |
| Retention | Per latest-version feed behavior | Bounded by continuous backup retention |
| Account prerequisites | Standard default per supported API | Continuous backup and feature prerequisites |
| Primary goal | Latest-state sync, basic ETL | CDC/auditing/replication needing delete awareness |

Never replace an immutable compliance audit log with the change feed if compliance forbids losing events during outages or beyond retention windows.

### 17.5. Idempotency for Change Feed Consumers

Consumers can redeliver items/events across checkpoints and retries. Therefore:

- Deduplicate using operation IDs, versions/ETags, or business sequences.
- Persist processed state in a constrained store.
- Never resend emails or payments on replay.
- Remember ordering is scoped to partition keys, not global total order.
- Monitor consumer lag, lease health, RUs, and retries.

If a delete event arrives after a newer create for the same business key, compare versions, operation timestamps, and business state before deleting newer data.

## 18. Transactional TTL vs. Analytical Store TTL and Backup Retention

### 18.1. Transactional TTL

Container/item TTL covered so far governs documents in the **transactional store** of Azure Cosmos DB for NoSQL, driven by **`_ts`** and background purging.

### 18.2. Analytical TTL Is a Separate Setting

When an account/container enables an analytical store where supported, **`analytical storage TTL`** is configured separately from transactional TTL.

For example, CLI flags may appear as:

~~~text
--ttl
--analytical-storage-ttl
~~~

Never conflate the two:

- Transactional TTL governs how long items remain in the transactional container.
- Analytical TTL governs retention in the analytical store where enabled/supported.
- Analytical store billing, sync, and retention follow separate semantics.
- Deleting from the transactional store does not instantly wipe analytical copies, exports, or backups.

If using external analytical links or mirroring outside Cosmos DB, inspect replication and deletion rules per target service rather than extrapolating from one TTL.

### 18.3. Backups Are Not TTL

Cosmos DB offers periodic or continuous backups per account configuration to support recovery within retention bounds. Even after TTL purges an item from the transactional store, **copies in backup restore points persist for the backup retention window**.

Therefore:
- TTL is not an instant purge across all backups.
- Backup retention does not replace operational legal retention.
- Restoring to a point before deletion can reintroduce deleted records into the restored account.
- Restore runbooks must reconcile against deletion/consent/legal-hold ledgers per compliance.
- Backup durations and geography must respect data residency and privacy policies.

### 18.4. TTL Alone Cannot Satisfy Statutory / Contractual Erasure SLAs

When a customer requests personal data erasure under a strict SLA, merely setting `ttl` to remaining seconds is insufficient:

1. TTL purging runs asynchronously with no exact deletion-second SLA.
2. Data may remain in backups, logs, exports, replicas, and analytical stores.
3. Search indexes, caches, and downstream copies need verified deletion.
4. Legal holds may temporarily block erasure.
5. Compliance requires auditable proof of action and verification.

Use an explicit **deletion workflow** with owners, queues, deadlines, explicit deletes/verification, replica tracking, and retention governance—using TTL only as supporting cleanup.

## 19. Indexing Policies, RUs, and TTL Purge Costs

### 19.1. TTL and Indexing

Cosmos DB TTL carries compatibility requirements with indexing policies. **`indexingMode = none` cannot be used with TTL enabled** per current indexing documentation.

To use Cosmos DB like a key-value store with TTL without indexing business fields, use **`consistent`** indexing with selective `includedPaths`/`excludedPaths` to trim overhead rather than turning indexing completely off.

If queries later filter or sort on excluded paths, performance and RUs shift—always test before optimizing.

### 19.2. TTL Background Purges Consume RUs

Under **provisioned throughput**, background TTL deletions consume spare unused RUs. When active workloads saturate throughput, background purging slows down.

Under **serverless**, TTL deletions can **incur RU charges similar to delete item operations**. Storage, networking/replication, and account limits still apply.

Never model costs assuming TTL deletions always cost zero RUs across every pricing tier.

### 19.3. Unique Keys Increase Write RUs

Containers with unique key policies validate uniqueness on creates, updates, and deletes; Microsoft Learn notes slightly higher RU charges on those writes compared to containers without unique keys.

Cost drivers:

- Item size.
- Number and length of unique key paths.
- Indexing policy.
- Logical partition hotspots.
- Throughput mode.
- Ratio of creates/updates/deletes.
- Contention and 409 conflict rates.

Never declare 10 unique constraints just because you can; justify every constraint against clear business needs.

### 19.4. Benchmarking RUs

A lab benchmark:

1. Create Container A without unique keys and Container B with unique keys.
2. Keep the **exact same partition strategy**, indexing policy, and item sizes.
3. Insert 1,000 non-duplicate records.
4. Measure average and p95 request charges and latency on both A and B.
5. Update the same records and re-measure.
6. Test controlled 409 conflicts.
7. Enable TTL and observe active item counts and storage after expiration/purge.
8. Compare RUs across throughput/pricing models.
9. Test across multiple partition keys to detect skew.
10. Record region, SDK version, consistency level, and settings.

There is no fixed constant RU overhead across workloads; measure against your real data model.

### 19.5. Total Lifecycle Cost

~~~text
Total lifecycle cost =
    Read / write / query / patch / delete RUs
  + Provisioned/autoscale capacity or serverless request charges
  + Transactional storage across volume and replicas
  + Indexing / uniqueness overhead
  + Change feed processor RUs and lease container
  + Backup / continuous backup / analytical store (if enabled)
  + Archive Blob Storage and network transfer
  + Application telemetry / log retention
  + Operational reconciliation, security, and compliance effort
~~~

TTL does not always cut costs immediately. Enabling TTL across millions of stale items can trigger a large purge backlog—budget RUs, capacity, and rollout timing accordingly.

## 20. Changing Unique Key Policies: Migrating Properly

### 20.1. Scenario

Container **`profiles-v1`** holds one million profiles partitioned by `/tenantId`, with no unique key. Business now requires `emailNormalized` to be unique per tenant.

**You cannot edit the unique key policy in place.** You must create **`profiles-v2`** with the new policy and migrate.

### 20.2. Migration Flow

~~~mermaid
flowchart TD
    V1["profiles-v1 serving live traffic"] --> A["Inventory + duplicate scan"]
    A --> B["Normalize emails + resolve nulls/duplicates"]
    B --> C["Create profiles-v2 with uniqueKeyPolicy"]
    C --> D["Backfill clean data"]
    V1 --> CF["Change feed / dual-write strategy"]
    CF --> D
    D --> E["Validate counts, conflicts, partition routing"]
    E --> G{"Cutover gate passed?"}
    G -->|No| H["Stay on v1, fix, and retry"]
    G -->|Yes| I["Switch app reads/writes to v2"]
    I --> J["Monitor + reconcile + rollback window"]
~~~

### 20.3. Pre-Migration Inventory

Audit:

- How many items lack `emailNormalized`?
- How many emails differ only by letter case?
- Are there duplicate emails within any tenant?
- Do values have unexpected whitespace, Unicode, or formatting quirks?
- Do any items use **`EmailNormalized`** instead of **`emailNormalized`**?
- Do unrelated doc types lacking emails share the same container?
- Are any items nearing TTL expiration during the move?
- Does the partition key also need to change?
- Are continuous writes, change feed jobs, or batches modifying v1?
- How many RUs and hours will backfill require?

### 20.4. Resolving Duplicates Before Copying

Example:

~~~text
tenant-a:
  profile-001 → minh@example.com
  profile-002 → MINH@example.com

Normalized:
  both become minh@example.com
~~~

Only one profile can hold that value once the per-tenant unique key is active. Apply business rules: merge profiles, pick a canonical owner, relink orders/transactions, route to manual review, or update one record's email with user consent.

Never delete a profile just to make a backfill script “pass” when financial or privacy records depend on it.

### 20.5. Backfill Alongside Live Writes

If the app keeps writing to v1 during copying, a plain snapshot copy followed by cutover drops recent writes.

Strategies include:

- **Controlled dual-write** with idempotency and per-target error reconciliation.
- **Change feed** syncing creates and updates (factoring in delete semantics from Section 17).
- **Maintenance / read-only window** right before cutover if SLAs permit.
- **Container copy jobs/tools** where supported by the platform and configuration.

Choose based on data volume, downtime SLAs, and consistency needs. Never assume latest-version change feed automatically propagates v1 deletes.

### 20.6. Pre-Cutover Verification

- Item totals match per tenant and doc type.
- Failure rates and unique conflicts resolved cleanly.
- Core index and partition-key queries pass.
- New TTL settings do not prematurely expire retained records.
- NoSQL SDK point reads return expected documents.
- Application contract tests pass for creates, updates, and deletes.
- Change feed lag is near zero or within cutover tolerances.
- RUs and 429s stay within limits.
- Rollback plan and old-container retirement date documented.

### 20.7. Rollback Constraints

Once traffic moves to v2 and accepts new writes, rolling back to v1 **does not automatically sync those new v2 writes backward**. You need reverse sync/reconciliation, write freezes, or explicit data rollback steps. Deleting v1 immediately destroys your fallback, while keeping v1 indefinitely raises storage cost and personal-data exposure—balance the rollback window per policy.

## 21. Real-World Scenario: Multi-Tenant SaaS Profiles and Notifications

### 21.1. Requirements

A multi-tenant SaaS has the following needs:

- Each tenant maintains user profiles; `emailNormalized` must be unique per tenant.
- Sessions auto-expire after 30 minutes of inactivity.
- Notifications live at most 7 days from last edit unless exempted.
- Payment evidence and audit logs follow independent retention rules.
- When a user requests account deletion, remove from search indexes, block login, and clean downstream copies.
- Services run on Azure Functions and App Service using managed identity and VNet/Private Endpoints where security mandates.

### 21.2. Container Design

| Container | Partition Key | Unique Keys | TTL | Rationale |
|---|---|---|---|---|
| `profiles` | `/tenantId` | `/emailNormalized` | `-1` | Profiles do not auto-expire; unique per tenant |
| `sessions` | `/tenantId` or load-balanced PK | Unnecessary if `id` suffices | `1800` | Session inactivity |
| `notifications` | `/tenantId` | Optional per business ID | `604800` | Clean up notifications 7 days after `_ts` |
| `identity-claims` | Per global email claim strategy | `id`/unique constraint per model | State-driven | Global email reservations if needed |
| `payment-audit` | Per access/retention pattern | Per business rules | Dedicated policy | No short TTL expiration |
| `deletion-jobs` | By tenant / job ID | Idempotency ID | Post-reconciliation | Track erasure state and audit |

**Not every container needs a unique key policy.** Deterministic IDs often suffice for notifications; unnecessary constraints add RUs and operational rigidity.

### 21.3. Profile Creation Flow

~~~mermaid
sequenceDiagram
    participant U as App Client
    participant A as Profile API
    participant C as Cosmos DB Profiles
    participant M as Monitor
    U->>A: POST profile + email
    A->>A: Authenticate tenant + normalize email
    A->>C: create_item (tenantId, id, emailNormalized)
    alt Unique constraint satisfied
        C-->>A: Created
        A-->>U: 201
    else Duplicate
        C-->>A: 409 conflict
        A-->>U: 409 business error
    end
    A->>M: Log correlation, status, RUs (omit raw email)
~~~

Never let callers pass an arbitrary `tenantId` without verifying access tokens and tenant ownership; unique keys do not enforce authorization.

### 21.4. Account Deletion Flow

~~~mermaid
flowchart TD
    R["Authenticated delete request"] --> A["Check tenant ownership + legal hold"]
    A --> B{"Legal hold active?"}
    B -->|Yes| H["Mark restricted / human review"]
    B -->|No| S["Disable login + soft delete profile"]
    S --> C["Publish deletion job / event"]
    C --> D["Remove cache/search/index copies"]
    D --> E["Archive or delete data per policy"]
    E --> F["Verify Cosmos + downstream"]
    F --> G["Audit completion; retain deletion job"]
~~~

Never set a short TTL on a profile and declare the entire deletion workflow done. If the record expires before search indexes or Blob archives are updated, reconciliation breaks.

### 21.5. Acceptance Criteria

1. Two concurrent creates with the same email in one tenant: only one succeeds.
2. Two different tenants can register the same email per policy.
3. Missing unique paths or case mismatches are blocked before production via schema validation.
4. Sessions expire within policy; apps deny access once absolute expiry passes.
5. Soft-deleted profiles never appear in normal API responses.
6. Change feed consumers process markers before TTL purge, or use a supported AVD strategy.
7. Backup, analytical, and export retention are governed independently.
8. Cosmos DB RUs/429s, consumer lag, and deletion SLAs are actively monitored.
9. Migration and rollback drills are tested for unique key policy changes.
10. All administrative actions carry audit logs, RBAC, and approvals.

## 22. Monitoring, Operations, and Security

### 22.1. Signals to Track

| Signal | Why It Matters |
|---|---|
| RU consumption / normalized RUs | Tracks whether reads, writes, or unique keys are climbing |
| HTTP 429s | Capacity throttling or aggressive retries |
| HTTP 409s | Duplicates, ID collisions, or schema bugs |
| P95 read/write latency | Business SLAs and noisy partitions |
| Storage usage | Confirms whether TTL trims storage as expected |
| Logical partition skew | Hot partitions or oversized tenants |
| Change feed lag | Checks if soft-delete markers are falling behind |
| Lease / processor failures | Detects stalled archive/search sync |
| TTL volume / workflow deletion backlog | Never promise exact-second purges |
| Legal-hold exceptions | Tracks items exempted from default TTL |
| Backup / retention changes | Compliance and recovery risk |
| Privileged data-plane role changes | Guards against mass reads or deletions |
| App delete-job failures | Incomplete downstream erasure |
| Cost by account / container / env | Controls RUs, storage, and replication spend |

Cosmos DB metrics do not necessarily expose a built-in metric named **`TTL Backlog`** on every account; track hard deadlines and purges with business metrics, sampling, and verification jobs.

### 22.2. Safe Logging

Do log:

- Correlation IDs.
- Account, database, and container names.
- Tenant ID formatted per privacy policy.
- Operation type, status code, and substatus where exposed by the SDK.
- RU charges, latency, and retry counts.
- Classified business document IDs.
- Policy versions, TTL settings, and release commits.
- Deletion job state, UTC timestamp, and audit actor.

Never log:

- Account keys or authorization headers.
- Connection strings containing credentials.
- Raw emails or PII unless strictly required and governed.
- Full user document payloads.
- Secrets or SAS tokens inside Blob URLs.

### 22.3. Azure RBAC vs. Cosmos DB Data-Plane Roles

Distinguish:

- **Azure management-plane RBAC:** Who can modify Cosmos DB accounts, databases, containers, TTL, and throughput.
- **Cosmos DB for NoSQL data-plane RBAC:** Who can read, create, update, and delete items via Microsoft Entra identities.
- **Networking:** Firewalls, Private Endpoints, VNets, and DNS.
- **Application authorization:** Which user may access which tenant.
- **Key Vault:** External secret governance per policy.

Enabling a managed identity does not grant item write permissions automatically, nor does an Azure resource manager role grant Cosmos data-plane access—assign explicit roles and scopes.

### 22.4. Private Networking

In a private-only environment:

~~~text
App Service / Azure Functions / AKS
    ↓ VNet integration / VNet networking
Private DNS resolver / zone
    ↓
Cosmos DB Private Endpoint
    ↓
Cosmos DB for NoSQL data plane
~~~

Test DNS resolution from the live runtime, TLS hostnames, routes/NSGs/firewalls, and reachability to Entra token endpoints. Never open global public access to fix timeouts, and never grant broad data-plane roles to fix DNS bugs.

### 22.5. Runbook: Handling 409 Conflicts

1. Identify whether the conflict occurred on a create or an update.
2. Check `id` and partition key value.
3. Inspect the container's unique key policy.
4. Check JSON property casing and normalized fields.
5. Check for existing duplicates in the **corresponding logical partition**.
6. Check for missing/`null` keys and composite key collisions.
7. If an item is near TTL expiration, avoid infinite blind retries assuming exact-second deletion.
8. Separate genuine business conflicts from idempotent retries.
9. Return HTTP 409 with a clear business error code—never leak secrets or raw payloads.
10. Open an incident if schema, normalization, or migration bugs trigger widespread conflicts.

### 22.6. Runbook: Item Not Expiring Under TTL

1. **Is container `defaultTtl` `null`/absent?** If so, item `ttl` is ignored.
2. **Is container `defaultTtl = -1`?** Items must carry a positive `ttl` to expire.
3. **Is item `ttl = -1`?** The item is exempted from auto-expiry.
4. **Was `_ts` recently updated?** Expiration slides from the latest modification.
5. **Is TTL in seconds or milliseconds?** Never pass milliseconds as seconds.
6. **Has the item actually expired yet?** Calculate `_ts + ttl`.
7. **Queries hide the item, yet storage stays high?** Background purging may lag.
8. **Are provisioned RUs saturated?** Lack of spare RUs delays physical deletion.
9. **Are you inspecting analytical store, backups, or exports?** Those follow separate retention rules.
10. **Is a legal hold or archive workflow keeping it alive?** Audit overrides.

### 22.7. Runbook: Accidental Deletions from a TTL Policy Change

1. Halt the rollout and pause app jobs triggering unintended updates/cleanups.
2. Record the container, prior/new policies, and exact UTC change timestamp.
3. Run bounded queries to inventory expired vs. surviving items.
4. Check available backup modes and restore points within retention.
5. Never blindly overwrite production—restore and verify in an isolated environment first.
6. Reconcile fresh writes committed since the incident began.
7. Cross-check archive, search, and downstream copies to avoid “resurrecting” legitimately erased user data.
8. Cut over or merge with approvals and business reconciliation.
9. Write a postmortem and add guardrails around `defaultTtl` edits.
10. Require canary validation on representative legacy items before future production changes.

## 23. Common Mistakes and Misconceptions

| Symptom or Misconception | Root Cause | Remediation |
|---|---|---|
| Item `ttl=600` never expires | Container TTL disabled | Set `defaultTtl` non-null |
| `defaultTtl=-1` deletes nothing | `-1` enables TTL with no default | Set positive `ttl` on expiring items |
| Trying to disable TTL with `0` | `0` is invalid | Clear / set `defaultTtl` to `null` per API |
| Item expires later than expected | `_ts` updated by edits | Enforce `absoluteExpiresAt` in app logic |
| Hidden from queries, storage still high | Background purge runs asynchronously | Monitor RUs/retention and recheck |
| TTL hides who deleted an item | Latest-version feed emits no deletes | Use soft-delete events or AVD if supported |
| Enabling TTL deletes legacy items | Default TTL counts from old `_ts` | Audit data age, canary, and back up first |
| Updating unique key on container fails | Policy is immutable | Create new container and migrate |
| Duplicate emails slip into one tenant | Wrong path/casing or missing policy | Canonicalize and verify policy |
| Same email across two tenants seen as bug | Uniqueness is per logical partition | Clarify business scope |
| Multiple email-less items hit 409 | Missing unique path treated as `null` | Schema validation or separate model |
| `A@domain` and `a@domain` both exist | Values are case-sensitive | Enforce normalized keys |
| Composite key doesn't make parts unique | Only the full tuple is constrained | Declare separate constraints if needed |
| 409 on retry creating new IDs | Unstable idempotency | Use deterministic business request IDs |
| 409 due to duplicate `id` | `(pk, id)` must be unique | Distinguish `id` collision from unique field |
| Want global uniqueness with `pk=/tenantId` | Constraint stays inside each tenant | Use reservation / authority store |
| Archiver misses TTL deletes | Latest feed omits delete events | Use soft delete + timely reads or AVD |
| TTL purges before audit finishes | Retention too short | Verify archival before short TTL |
| Legal-hold record deleted | App logic skips hold checks | Separate retention and enforce RBAC |
| Costs do not drop right away | Purge lag, backups, indexes, other storage | Break down each billing component |
| Write RUs rise after adding unique keys | Index and constraint overhead | Benchmark and remove unneeded constraints |
| TTL fails with `indexingMode: none` | TTL requires compatible indexing | Use `consistent` indexing with exclusions |
| Restore brings back deleted data | Restore point predates deletion | Reconcile against deletion ledger and policy |

## 24. Production Checklist

### Data Model

- [ ] Partition key chosen from access patterns, scale, and tenant isolation.
- [ ] Distinguished `id` uniqueness from property unique keys.
- [ ] Unique keys placed strictly on fields with clear business semantics.
- [ ] Unique paths guaranteed present, consistently cased, and consistently typed.
- [ ] Optional fields and `null` behavior tested.
- [ ] Email/identifier canonicalization strategy defined.
- [ ] Explicitly decided between per-tenant and global uniqueness.
- [ ] Migration plan prepared if unique key policies ever change.

### TTL and Lifecycle

- [ ] `defaultTtl` (`null` / `-1` / `n`) chosen deliberately.
- [ ] Item `ttl` measured in **seconds**, strictly `-1` or valid positive integers.
- [ ] Accounted for `_ts` resets on updates and patches.
- [ ] Distinguished sliding expiration from absolute expiration.
- [ ] Authorization checks do not rely solely on whether an item still exists.
- [ ] Sequenced archival → soft delete → physical delete cleanly.
- [ ] Legal holds and retention exceptions governed separately.
- [ ] Never treated TTL as an instant deletion SLA.
- [ ] Backup/restore reconciliation handles previously deleted items.
- [ ] Analytical TTL and exports governed independently when enabled.

### Change Feed, Reliability, and Security

- [ ] Latest-version feed is not treated as a complete deletion log.
- [ ] Soft-delete marker TTL exceeds worst-case consumer lag and recovery time.
- [ ] All-versions-and-deletes mode used only after verifying prerequisites.
- [ ] Change feed consumers implement idempotency and deduplication.
- [ ] Data-plane RBAC separated from management-plane RBAC.
- [ ] Managed identities scoped to least privilege.
- [ ] Private networking, DNS, and TLS verified end-to-end.
- [ ] Logs exclude account keys and unnecessary PII.
- [ ] Business deletions emit audit trails, correlation IDs, and ownership records.

### RUs, Monitoring, and Release

- [ ] Benchmarked create/update/delete RUs with unique keys enabled.
- [ ] Budgeted purge/TTL volume against throughput mode.
- [ ] Monitored RUs, 429s, 409s, latency, storage, and consumer lag.
- [ ] Configured Azure Cost Management budgets and tags.
- [ ] Tested `defaultTtl` edits against legacy timestamps before rollout.
- [ ] Prepared rollback, restore, and reconciliation runbooks.
- [ ] Tested concurrent writes against unique keys.
- [ ] Tested `null` handling, case sensitivity, and composite constraints.
- [ ] Tested consumer outages outlasting soft-delete marker TTLs.
- [ ] Configured alerts when deletion workflows breach deadlines.

## 25. Self-Check Questions

1. **What unit does TTL use in Cosmos DB for NoSQL?** Seconds.
2. **Is TTL measured from creation time or last modification?** From `_ts` of the last modification (or creation time if unmodified).
3. **What does `defaultTtl = null` mean?** TTL is disabled; item-level `ttl` is ignored.
4. **What does `defaultTtl = -1` mean?** TTL is enabled, yet items without `ttl` never expire automatically.
5. **What does `defaultTtl = 604800` mean?** Items without an override expire 7 days after `_ts`.
6. **What does item `ttl = -1` do?** Exempts that item from auto-expiry even if the container has a positive default TTL.
7. **Is `ttl = null` valid on an item?** No; omit the property to inherit the container default.
8. **Should `ttl = 0` be used for immediate deletion?** No; `0` is not a valid TTL value.
9. **Does a positive item `ttl` work when container TTL is off?** No.
10. **If queries stop returning an expired item, has physical purging finished?** Not necessarily.
11. **Does updating an item reset its TTL countdown?** Yes, because `_ts` updates.
12. **How does sliding expiration differ from absolute expiration?** Sliding extends from last activity; absolute enforces a fixed timestamp.
13. **Does TTL replace token revocation?** No.
14. **At what scope are unique keys enforced?** Within a logical partition.
15. **Is `(pk, id)` unique?** Yes, within a container.
16. **Does unique key `/emailNormalized` prevent duplicate emails across two tenants?** No, if `tenantId` is the partition key and differs.
17. **Can a unique key policy be added to an existing container?** No; create a new container and migrate.
18. **What are the maximum unique constraints and total paths?** Per current docs, 10 constraints and 16 paths total.
19. **Are unique key paths case-sensitive?** Yes.
20. **Are `A@example.com` and `a@example.com` considered duplicates by default?** No; normalize first.
21. **How is an item missing a unique property treated?** As `null` in the uniqueness constraint.
22. **Does a composite unique key make each individual component unique?** No.
23. **Why must 409 conflicts be handled explicitly?** Could stem from duplicate `id`, unique constraint violation, or other conflicts needing classification.
24. **Is querying “does email exist?” then calling `create` safe under concurrency?** No; it races without an atomic server-side constraint or reservation.
25. **How do you enforce global uniqueness?** Use a dedicated partition/reservation authority with concurrency and reconciliation—not per-tenant unique keys.
26. **How does soft delete differ from TTL hard delete?** Soft delete retains the item with a marker; TTL hard delete purges it after expiration.
27. **Does the latest-version change feed include TTL delete events?** No.
28. **What prerequisites apply to all-versions-and-deletes mode?** Continuous backup and compatible feature availability/prerequisites.
29. **When does a TTL delete event appear in all-versions-and-deletes?** When the item is physically purged, not necessarily the instant TTL expires.
30. **Should soft-delete marker TTL be shorter than max consumer outage time?** No, not if you rely on reading the marker.
31. **Does TTL automatically archive items to Blob Storage?** No.
32. **Does TTL immediately erase items from all backups and exports?** No.
33. **Is `indexingMode: none` compatible with TTL-enabled containers?** No, per current support rules.
34. **Do unique keys affect RUs?** Yes, they can increase RUs for creates, updates, and deletes.
35. **When can provisioned throughput slow down TTL purging?** When active workloads consume all spare RUs.
36. **Can serverless TTL deletions incur RU charges?** Yes.
37. **Can legal-hold retention be solved solely with `ttl=-1`?** No; it requires security, audit, and retention controls.
38. **What is required to change a unique key policy in production?** New container, normalization/conflict cleanup, migration, testing, cutover, and reconciliation.
39. **What happens if you restore a snapshot from before an item was deleted?** Deleted data can reappear in the restored database.
40. **What defines a sound document lifecycle?** Clear state machine, fitting TTL/unique policies, security, archival, deletion verification, cost control, and monitoring.

## 26. References

- [Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/) — NoSQL service docs, JSON documents, and SDKs.
- [Time to live (TTL)](https://learn.microsoft.com/azure/cosmos-db/time-to-live) — container/item TTL, `_ts`, RUs, and expiration semantics.
- [Configure time to live](https://learn.microsoft.com/azure/cosmos-db/how-to-time-to-live) — Portal, CLI, SDK, and TTL updates.
- [Unique key constraints](https://learn.microsoft.com/azure/cosmos-db/unique-keys) — partition scope, policy immutability, casing/`null`, and limits.
- [Define unique keys for a container](https://learn.microsoft.com/azure/cosmos-db/how-to-define-unique-keys) — creating containers with unique keys.
- [Azure CLI cosmosdb sql container](https://learn.microsoft.com/cli/azure/cosmosdb/sql/container) — `create`/`show`/`update`, `ttl`, and `unique-key-policy` options.
- [Change feed in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/change-feed) — consumer patterns and change feed overview.
- [Change feed modes](https://learn.microsoft.com/azure/cosmos-db/change-feed-modes) — latest version vs. all versions and deletes.
- [Transactional batch operations](https://learn.microsoft.com/azure/cosmos-db/transactional-batch) — intra-logical-partition transactions.
- [Indexing policy management](https://learn.microsoft.com/azure/cosmos-db/nosql/how-to-manage-indexing-policy) — indexing and TTL compatibility.
- [Partitioning in Azure Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview) — logical/physical partitions and scale.
- [Azure Cosmos DB request units](https://learn.microsoft.com/azure/cosmos-db/request-units) — RUs and performance.
- [Azure Cosmos DB security](https://learn.microsoft.com/azure/cosmos-db/security) — identity, networking, and encryption.
- [Azure Cosmos DB backup and restore](https://learn.microsoft.com/azure/cosmos-db/online-backup-and-restore) — backup modes and recovery constraints.
- [Azure Cosmos DB monitoring](https://learn.microsoft.com/azure/cosmos-db/monitor) — metrics, diagnostic logs, and alerts.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags, and cost analysis.

**Conclusion:** TTL governs document lifetimes from `_ts` with asynchronous background purging; unique keys enforce uniqueness **within a logical partition** and must be set at container creation; and document lifecycle management spans state machines, soft deletes, archival, the change feed, backups, security, legal holds, and deletion verification. A solid implementation does more than make items “vanish after *n* seconds” or “block duplicate emails”—it prevents race conditions, handles 409s cleanly, protects retained data, preserves deletion signals across pipelines, and stays auditable and cost-effective.
