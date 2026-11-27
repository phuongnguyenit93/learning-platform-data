# ETag, Optimistic Locking, and Choosing Consistency Levels

An inventory management application using Azure Cosmos DB might have two requests concurrently read a quantity of 10 and each subtract 3. If both write back 7 without checking versions, one update can overwrite the other: the system still shows 7 instead of 4. This is a **lost update**. Cosmos DB provides **ETag** and the HTTP `If-Match` condition to detect operations based on stale versions. At the same time, the service lets you choose a **consistency level** to govern how fresh a read is guaranteed to be across distributed replicas and multiple regions.

These two mechanisms answer two separate questions: **ETag protects a write from overwriting a version that has already changed**; **consistency level governs what data a read operation is allowed to observe**. Using ETags does not turn every read into strong consistency, and choosing strong consistency does not replace rules for handling two actors updating the same item concurrently.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secrets, integration testing, and evaluating differences between cloud providers. This lesson focuses on Azure Cosmos DB for NoSQL, Spring Data Cosmos, and selecting consistency levels according to business requirements.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Explain ETag, `If-Match`, `If-None-Match`, and HTTP 412 errors.
- Identify lost updates/lost deletes and implement optimistic concurrency control (OCC).
- Map `_etag` onto a Spring Data Cosmos entity using `@Version`.
- Handle conflicts by re-reading and re-evaluating business rules instead of retrying stale payloads.
- Distinguish ETags from session tokens, item IDs, partition keys, and application versions.
- Describe the five consistency levels: Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual.
- Configure default consistency for Spring Cloud Azure and understand session tokens in multi-instance applications.
- Evaluate the impact of multi-region writes, conflict resolution, and ETag limitations.
- Design tests for concurrency, read-after-write, failover, and stale-read scenarios.

## 2. Two Problems That Must Be Solved Separately

### 2.1. Concurrent Updates: Who Is Allowed to Write Which Version?

Suppose an inventory item has `availableQuantity = 10`. Two workers read the item at ETag version `E1`:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as Cosmos DB
    A->>DB: Read item (quantity=10, ETag=E1)
    B->>DB: Read item (quantity=10, ETag=E1)
    A->>DB: Replace quantity=7, If-Match E1
    DB-->>A: Success, ETag=E2
    B->>DB: Replace quantity=7, If-Match E1
    DB-->>B: 412 Precondition Failed
    B->>DB: Read latest item (quantity=7, ETag=E2)
    B->>B: Re-evaluate business rule
    B->>DB: Replace quantity=4, If-Match E2
    DB-->>B: Success, ETag=E3
~~~

ETag lets the server reject the second write because worker B is operating on a stale version. The application re-reads the latest value, recalculates the quantity, and attempts the write with the new ETag. If inventory is insufficient after re-reading, business logic must reject the transaction rather than forcing a write.

### 2.2. Distributed Reads: Which Replicas Are Allowed to Answer?

In a Cosmos DB account spanning multiple replicas/regions, a read may need stronger or weaker guarantees on data freshness and ordering. The consistency level defines these guarantees:

~~~mermaid
flowchart TD
    A[Application read] --> B{Consistency policy}
    B --> C[Strong: latest committed value]
    B --> D[Bounded staleness: lag <= K or T]
    B --> E[Session: read-your-writes in session]
    B --> F[Consistent prefix: ordered prefix]
    B --> G[Eventual: convergence over time]
    C --> H[Read result]
    D --> H
    E --> H
    F --> H
    G --> H
~~~

An item having a new ETag does not mean every region immediately observes that version under all consistency levels. Conversely, a strong read returning the latest version still does not prevent two requests from attempting concurrent writes; protecting updates requires a version condition such as an ETag.

## 3. What Is an ETag?

Each item in Azure Cosmos DB for NoSQL has a server-generated system property **`_etag`**. Whenever an item is updated, its ETag changes. This value is an **opaque token**: the application stores and sends it back intact, without parsing it as a timestamp, sequence number, or version ordering comparison.

When reading an item, the response includes the current ETag. When replacing or deleting an item only if it has not been modified, the client sends that value via the **`If-Match`** condition:

- If the submitted ETag matches the current ETag on the server, the operation can proceed.
- If the item has changed and the ETag no longer matches, the server rejects with **HTTP 412 Precondition Failed**.
- The application re-reads the item, inspects the new state, and decides whether the business rule can be re-applied or must report a conflict.

~~~text
GET item
  <- item + ETag: E1

PUT/REPLACE item
  If-Match: E1
  -> Server ETag is still E1: update succeeds, server issues E2
  -> Server ETag is already E2: returns 412, newer version not overwritten
~~~

ETag helps detect **lost updates** and **lost deletes**. It does not lock the item, does not hold a transaction open between read and write, and does not guarantee a read always returns the newest state. This is **optimistic locking**: multiple processes can read concurrently; only at write time is version validity checked.

## 4. `If-Match` and `If-None-Match`

| Header | Purpose | Typical Outcome |
| --- | --- | --- |
| `If-Match: <etag>` | Update/delete only if the resource is still at the read version | Match: operation proceeds; mismatch: 412 |
| `If-None-Match: <etag>` | Check whether the resource changed relative to the client's cached copy | ETag still matches: may return 304; differs: returns new representation |

`If-Match` is typically used for **replace**, **upsert** (when the operation resolves to a replace), and **delete**. For creates, there is no existing version to match, so this condition may be ignored depending on the API. For upserts, understand both the create and replace branches; do not assume an ETag condition carries identical semantics across both branches.

`If-None-Match` is typically used for cache validation or checking whether an item has changed. It is not an overwrite-protection mechanism. In web applications, HTTP ETags on your API can act as response validators, but map them cleanly to item versions and prevent callers from supplying ETags from other resources.

**Do not confuse 409 and 412:** 409 is typically a conflict such as a duplicate ID/unique key; 412 means a precondition is no longer true, such as a stale ETag. Applications may map these two errors to distinct responses per their public API contract.

## 5. Optimistic Locking in Spring Data Cosmos with `@Version`

Spring Data Cosmos supports optimistic locking for supported containers/operations. The common pattern is adding a `String` field named `_etag` annotated with `@Version`.

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(
    containerName = "inventory",
    autoCreateContainer = false
)
public class InventoryDocument {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryDocument() {
    }

    public String getId() { return id; }
    public String getWarehouseId() { return warehouseId; }
    public int getAvailableQuantity() { return availableQuantity; }
    public String getEtag() { return _etag; }

    public void setId(String id) { this.id = id; }
    public void setWarehouseId(String warehouseId) {
        this.warehouseId = warehouseId;
    }
    public void setAvailableQuantity(int quantity) {
        this.availableQuantity = quantity;
    }
}
~~~

Repository:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;

public interface InventoryRepository
        extends CosmosRepository<InventoryDocument, String> {
}
~~~

Application service:

~~~java
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    public InventoryDocument reserve(
            String warehouseId, String itemId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        InventoryDocument item = inventory.findById(
            itemId, new PartitionKey(warehouseId))
            .orElseThrow(() -> new IllegalArgumentException("Item not found"));

        if (item.getAvailableQuantity() < quantity) {
            throw new InsufficientInventoryException();
        }

        item.setAvailableQuantity(item.getAvailableQuantity() - quantity);
        return inventory.save(item);
    }
}
~~~

This illustrates the application flow; constructors, exceptions, and packages should follow your project structure. `@Version` enables Spring Data Cosmos to attach the current ETag to write conditions on supported operations. When another process has updated the item, an upsert/delete carrying a stale ETag will fail instead of silently overwriting.

**Never assign or compute `_etag` yourself.** This value is managed by Cosmos DB and updated by the framework after a successful write. Do not expose `_etag` as a user-editable DTO field, set it to a timestamp, or manually increment it as a number.

### 5.1. What Does `@Version` Protect?

- Protects item-level updates/upserts/deletes across supported Spring Data Cosmos operations.
- Detects when another process modified the item since it was read.
- Reduces lost updates/lost deletes in multi-request/multi-worker environments.
- Gives the application service a hook to resolve conflicts according to business rules.

It does **not** automatically protect arbitrary bulk queries or SDK calls executed outside the repository; nor does it create transactions across multiple items, containers, or external services. If a code path uses the SDK directly, it must pass ETag/`If-Match` for those operations itself.

### 5.2. Handling Conflicts Properly

When Spring Data detects a version mismatch, the framework may throw an optimistic locking/data access exception. The application layer should catch it at the appropriate boundary and classify it as a business conflict. Do not depend on specific exception message text; inspect the exception type and cause according to your Spring Data Cosmos version.

Safe handling flow:

1. Read the item and its current ETag.
2. Compute the change from the read state.
3. Submit the update with the ETag.
4. If successful, return the result.
5. On conflict, re-read the new state and **re-evaluate business preconditions**.
6. Retry only a bounded number of times if the operation remains valid; otherwise, return a conflict to the caller.

Inventory reservation example: if two users order concurrently, the second request must re-read remaining inventory. If remaining quantity is insufficient, return an "insufficient inventory" error; never simply copy the stale payload and rewrite it with the new ETag.

## 6. Using ETag Directly with the Azure Cosmos DB Java SDK

When low-level SDK operations outside a repository are needed, you can set the ETag in `CosmosItemRequestOptions`:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public InventoryDocument updateWithEtag(
        CosmosContainer container,
        String itemId,
        String warehouseId,
        InventoryDocument itemReadEarlier,
        String etagReadEarlier) {

    itemReadEarlier.setAvailableQuantity(
        itemReadEarlier.getAvailableQuantity() - 1);

    CosmosItemRequestOptions options = new CosmosItemRequestOptions()
        .setIfMatchETag(etagReadEarlier);

    CosmosItemResponse<InventoryDocument> response =
        container.replaceItem(
            itemReadEarlier,
            itemId,
            new PartitionKey(warehouseId),
            options);

    return response.getItem();
}
~~~

In this example, `etagReadEarlier` must come from the read response of that exact item—never from another item or a separate unrelated request. `replaceItem` requires the exact item ID and partition key; if the ETag is stale, the SDK receives a precondition error (412). This example illustrates conditional replace only; production code must handle exceptions, validate quantities, and avoid reusing stale objects after a conflict.

When using Spring Data repositories, prefer `@Version` so the framework manages ETags. Only use `CosmosItemRequestOptions.setIfMatchETag` when direct SDK control is needed for a clear reason.

## 7. ETag Is Not a Session Token or Application Version

| Value | Origin | Purpose | Can Substitute for ETag? |
| --- | --- | --- | --- |
| **ETag / `_etag`** | Cosmos DB server | Conditional write/delete by item version | This is the token used for `If-Match` |
| **Session token** | Cosmos DB response, stored and sent back by SDK | Ensures session consistency across read/write flows | No; it is not an item version for conditional updates |
| **Item ID** | Application | Identifies an item within a container | No; ID does not show whether an item changed |
| **Partition key value** | Application/container model | Routes to a logical partition | No; it is not a version |
| **Application revision** | Application | Business version that may be displayed or synced | Only with a separate contract; does not replace ETag automatically |
| **Timestamp `_ts`** | Cosmos DB server | Update time in epoch seconds | No; two updates may not be distinguished granularly enough for OCC |

ETag is an opaque value meant strictly for server-side equality matching. Never compare ETag strings to determine "which copy is newer," parse their contents, or share ETags across items. If an application needs a monotonically increasing revision for cache/event synchronization, maintain an explicit **application version** and update it under OCC.

## 8. The Five Consistency Levels of Azure Cosmos DB for NoSQL

Cosmos DB offers five consistency levels, from strongest to weakest:

| Level | Primary Guarantee | When to Consider |
| --- | --- | --- |
| **Strong** | Linearizability: reads return the latest committed version | Business requires every read to see the latest write and accepts latency/availability trade-offs |
| **Bounded Staleness** | Data lag across regions is bounded by K versions or T time | Need explicit stale-read bounds without requiring Strong |
| **Session** | Read-your-writes, monotonic reads, and write-follows-reads within a matching session | Interactive applications scoped to a user or workflow |
| **Consistent Prefix** | Reads see an ordered prefix of writes, never out-of-order writes | Tolerates stale reads while requiring write order preservation |
| **Eventual** | Replicas converge eventually; no guarantee on freshness or ordering | Data can be temporarily stale and availability/latency are prioritized |

Consistency guarantees apply to single read operations within a logical partition. They do not create multi-partition or multi-container snapshot transactions. If a use case needs multiple reads/writes to be mutually consistent, evaluate transactions/batches within a single logical partition and their limits.

### 8.1. Strong

Strong consistency provides **linearizability**: a read always observes the latest committed version, even under concurrent operations. For multi-region accounts, writes must wait for strong replication across regions, so latency can rise substantially with geographic distance. Strong can also reduce availability when required quorums cannot be reached.

Strong is not the default choice for every application. Use it only when business requirements genuinely demand globally reading the latest value and latency/cost trade-offs have been evaluated. **Accounts configured for multi-region writes do not support Strong consistency.**

Strong and Bounded Staleness use quorum reads across multiple replicas; for the same RU budget, read throughput may be lower than Session, Consistent Prefix, or Eventual. Strong can also increase write latency when an account spans distant regions. Evaluate with realistic workloads rather than comparing consistency names alone.

### 8.2. Bounded Staleness

Bounded staleness caps the maximum lag across regions using:

- **K:** maximum number of versions/updates a read can lag behind.
- **T:** maximum time interval a read can lag behind.

Reads in a secondary region may not see the latest write instantaneously, but staleness is bounded by K/T. If replication lag exceeds the bound, writes on the affected partition may be throttled until lag returns within limits. This level fits business cases that tolerate a defined lag window without requiring Strong.

### 8.3. Session

Session consistency is commonly the right default for interactive applications. Within a client session, Cosmos DB guarantees:

- **Read-your-writes:** after writing, subsequent reads in the same session see that session's writes.
- **Monotonic reads:** reads never move backward to an older version after observing a newer one in the same session.
- **Write-follows-reads:** subsequent writes follow the session's read/write ordering.

Read-your-writes requires a single writer session or writers sharing the session token. Session tokens are bound to partitions; the SDK stores tokens from responses and attaches them automatically on subsequent reads. A token is not a historical snapshot pointer for reading past data; it is a minimum-version barrier.

If an application runs multiple instances with separate `CosmosClient`s, each client's in-memory session token cache is not shared automatically. A write request might hit instance A while the next read request is load-balanced to instance B; if B lacks the token for that partition, it may temporarily miss the recent write. When cross-instance read-your-writes is required, use session affinity or pass the session token securely across layers and attach it to the subsequent read. Never modify token contents.

### 8.4. Consistent Prefix

Consistent Prefix guarantees writes are observed as an ordered prefix—never seeing a later write while missing an earlier write in that order. However, reads can still be stale and do not necessarily reflect the latest write. This fits scenarios where event order matters more than immediate freshness, without needing per-session read-your-writes.

### 8.5. Eventual

Eventual consistency allows reads from replicas that may not yet have received the latest writes. Once new writes stop, replicas converge to the same state over time. This can lower read latency and suits secondary display data, dashboards, or workloads tolerant of stale data. Never use it for decisions like inventory deduction or payment approval if stale reads could cause incorrect business outcomes.

## 9. Configuring Consistency in Spring Cloud Azure

Spring Cloud Azure provides the property `spring.cloud.azure.cosmos.consistency-level`. Example selecting Session:

~~~yaml
spring:
  cloud:
    azure:
      cosmos:
        endpoint: ${AZURE_COSMOS_ENDPOINT}
        database: orders-db
        consistency-level: SESSION
~~~

Exact property names and supported values must be verified against your Spring Cloud Azure/Azure Spring Data Cosmos version. The Java SDK also defaults to **Session** if no other level is configured on the client.

If building a `CosmosClient` directly with the Java SDK:

~~~java
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;

CosmosClient client = new CosmosClientBuilder()
    .endpoint(endpoint)
    .key(accountKey)
    .consistencyLevel(ConsistencyLevel.SESSION)
    .buildClient();
~~~

This illustrates client configuration; in production, prefer secure credentials such as Managed Identity rather than placing account keys in source code. If the starter already creates the client, do not create an extra client just to change consistency; use properties or proper custom configuration to avoid two clients running with conflicting settings in the same application.

### 9.1. Account Default and Client Overrides

Default consistency is configured at the account level and applies to databases/containers underneath. Clients/requests can override it within API constraints: under the traditional `ConsistencyLevel` model, an application can only **relax** to a weaker level than or equal to the account default; strengthening requires configuring the account itself. Newer Java SDK releases offer read consistency strategy APIs, though availability depends on version/feature support; do not assume every Spring Data Cosmos starter exposes them.

When changing account consistency, redeploy/restart applications/clients if clients were initialized under the old setting. Verify account configuration, client beans, preferred regions, and request options; a YAML property alone does not prove all instances are running the same configuration.

## 10. Session Tokens in Multi-Instance Applications

With Session consistency, the SDK usually manages session tokens automatically within a single client instance. Manual handling is only needed when bridging a session across multiple clients/processes, for example:

~~~mermaid
sequenceDiagram
    participant U as Browser / caller
    participant A as App instance A
    participant B as App instance B
    participant DB as Cosmos DB
    U->>A: POST update item
    A->>DB: Write
    DB-->>A: Success + session token T1
    A-->>U: Success + opaque session context (if needed)
    U->>B: GET item, with session context
    B->>DB: Read with token T1
    DB-->>B: Read at minimum session version
    B-->>U: Latest value in session
~~~

You do not necessarily have to send the raw session token to the browser. You can keep the token in server-side session/cache or wrap it inside a protected opaque context. If passing via a client, bound its size, validate scope/partition, and avoid logging it. A session token is not a credential and grants no read authorization; identity/RBAC is still enforced independently.

Session tokens are **partition-bound**. Never reuse a token obtained from partition A for partition B. If a client instance restarts, its in-memory token cache resets; until new writes/tokens arrive, reads on partitions without a cached token may behave closer to Eventual.

## 11. Multi-Region Writes and Conflict Resolution

A Cosmos DB account can be configured with multiple write regions to lower write latency across geographic regions and boost resilience. However, multiple write regions introduce the possibility that two regions update the same item nearly simultaneously.

Key points to remember:

- **Strong consistency is unsupported** on multi-region write accounts.
- Local ETag/OCC in each region does not replace cross-region conflict resolution.
- Conflicts can occur on duplicate ID inserts, concurrent replaces on the same item, or a delete in one region racing an update in another.
- Cosmos DB provides conflict resolution policies; the default is typically **Last Write Wins (LWW)** based on the `_ts` timestamp, or a custom numeric property can serve as the conflict resolution path.
- The API for NoSQL also supports custom conflict resolution via merge stored procedures configured on the container.

For example, two regions might read an item with their respective local ETags and both write. Each operation can succeed in its local region, and the conflict is resolved later as changes converge. Therefore, do not treat ETag as a global distributed lock preventing all concurrent writes across regions.

If business logic demands merge invariants like "balance must never go negative" or "only one reservation can win," timestamp-based LWW may be insufficient. You may need to:

- Route critical write operations to a single write region/coordinator.
- Design operation IDs and idempotency to prevent duplicate side effects.
- Use appropriate custom conflict resolution or a business-level conflict-resolution workflow.
- Store immutable commands/events and derive state rather than overwriting a shared aggregate in multiple regions.

Do not enable multi-region writes just to cut latency without defining conflict semantics. Test failover and concurrent cross-region writes in a real Azure environment before production rollout.

## 12. Choosing a Consistency Level by Use Case

| Use Case | Starting Level to Evaluate | Rationale and Conditions |
| --- | --- | --- |
| User-session shopping cart or profile | **Session** | Typically needs to read back changes just written within the same user session |
| Single-write-region inventory | **Session + ETag OCC** or Strong if globally required | ETag prevents lost updates; consistency governs read freshness |
| Reporting dashboard tolerating delayed data | **Eventual** or Session depending on UX | Optimizes latency/throughput when stale data is acceptable |
| System needing bounded cross-region lag | **Bounded Staleness** | Allows defining K/T acceptable to the business |
| Log/event data needing prefix order | **Consistent Prefix** | Does not require reading the latest version immediately |
| Business requiring all regions to read latest commit | **Strong** if account topology supports it | Evaluate latency/availability; unavailable with multi-region writes |

These are starting points, not universal defaults. Frame requirements with concrete questions:

1. Immediately after a write, must the caller itself see the result?
2. Must a request in another region see the write immediately?
3. What maximum staleness in time or update count is acceptable?
4. If two actors update the same item, who wins and what does the application do?
5. Are multiple regions allowed to write concurrently?
6. Which matters more during a region outage: latency or availability?

**Consistency levels do not replace transaction design.** If an operation must modify multiple items in the same logical partition, use transactional batches or stored procedures within Cosmos DB limits. If you need to update Cosmos DB and publish a message/write a Blob, use outbox/saga; Cosmos DB Strong consistency does not create distributed transactions across separate services.

## 13. How ETag and Consistency Work Together

A safe item-update flow can combine both:

1. The SDK reads the item under Session consistency and receives ETag `E1`.
2. The application validates business rules and prepares the change.
3. Spring Data Cosmos `save`s the item carrying `@Version`; the server checks the ETag.
4. If unchanged, the write succeeds and the server issues a new ETag `E2`.
5. If updated concurrently, the server returns 412; the application re-reads and re-evaluates business rules.
6. Subsequent reads in the same session use the SDK-managed session token to observe the new version per Session guarantees.

Here:

- **ETag** prevents a write based on a stale version from overwriting a newer version.
- **Session token** ensures subsequent reads in the same session do not regress to an older version.
- **Consistency level** defines read guarantees across replicas/regions.
- **Business rules** determine whether a command can be re-applied after conflict or must be rejected.

If two instances run separate clients, session token caches are not shared automatically; if reading across regions or using multi-region writes, account for topology, conflict resolution, and session-token propagation.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Omitting `@Version` while assuming repositories prevent lost updates | Stale updates can overwrite newer updates | Map `_etag` with `@Version` or pass `If-Match` in SDK |
| Manually setting/mutating `_etag` | Conditional writes stop working properly | Let Cosmos DB manage it; preserve response tokens verbatim |
| Immediately retrying 412 with the same payload | Repeated conflicts or overwriting newer business decisions | Re-read, re-check business invariants, and recompute |
| Treating ETag as a timestamp or version number | Wrong ordering comparisons | Treat as an opaque token for equality matching only |
| Assuming Strong consistency replaces ETag | Concurrent writes can still race | Use OCC on update operations |
| Assuming ETag protects globally under multi-region writes | Cross-region conflicts can still occur | Design conflict resolution and write topology |
| Using Eventual for UI read-after-write | Callers can see stale data | Use Session or propagate session tokens across clients |
| Creating separate `CosmosClient`s per instance expecting shared sessions | Token caches are isolated | Use proper client lifecycle or pass tokens securely |
| Selecting Strong with multi-region writes | Unsupported configuration | Pick compatible topology/consistency |
| Treating 412 as a transient error with infinite auto-retry | Adds load without resolving conflicts | Handle conflicts at the application layer |
| Using `@Version` while bypassing OCC in bulk/SDK paths | Alternative write paths lack OCC | Audit all write paths and attach `If-Match` in SDK calls |

## 15. Testing Optimistic Locking and Consistency

### 15.1. Testing Two Writers with the Same ETag

Required scenario:

1. Create an initial item.
2. Read the item twice, holding two copies with the same ETag.
3. Writer A updates and writes successfully.
4. Writer B writes its stale copy.
5. Verify Writer B receives a conflict/412 instead of overwriting.
6. Re-read the item, re-apply business rules, and verify the final result.

With Spring Data Cosmos, test the real repository with an entity carrying `@Version`. Mocking the repository only proves the application service handles exceptions; it does not prove the framework sends the right ETag.

### 15.2. Testing Consistency

| Test Case | What to Verify |
| --- | --- |
| Write then read with the same client/session | Session read-your-writes |
| Write on instance A, read on instance B | Behavior when session tokens are not shared |
| Read from a different preferred region | Replication lag and selected consistency |
| Strong account across multiple regions | Reads see latest committed per guarantee; measure write latency |
| Bounded staleness | Staleness stays within configured K/T bounds |
| Multi-region writes | Conflict policy, hub resolution, and post-failover recovery |
| ETag conflict | 412 is not mistaken for 429/5xx or permission errors |

The Cosmos DB Emulator is useful for CRUD and some basic concurrency tests, but does not fully simulate cross-region latency, replication, global Strong consistency, multi-region writes, and failover. These guarantees must be tested against an Azure test account with the proper topology.

### 15.3. Metrics and Diagnostics

Monitor:

- Count and rate of **412 Precondition Failed** by container/operation.
- Application re-read/retry counts after conflicts and final conflict rate returned to callers.
- p50/p95/p99 read/write latency by region.
- RU charges, 429/throttling, and retry-after.
- Replication latency, consistency/PBS metrics, and region health.
- Conflicts raised/resolved under multi-region writes.

Never log full items or session tokens. Use activity IDs, request diagnostics, and operation IDs for correlation; protect tenant info and sensitive data.

## 16. Practice Exercises

**Exercise 1 — Lost update.** Two requests read an account balance of 100. Request A subtracts 30; Request B subtracts 20. Trace two writes without ETag vs. with ETag. Determine whether the correct final balance is 50 or 70 in each scenario and explain why.

**Exercise 2 — Spring Data `@Version`.** Create `InventoryDocument` with `_etag` and `@Version`. Write a repository/service to reserve stock; run two concurrent tests reading the same item and verify one request must re-read and recalculate.

**Exercise 3 — Handling 412.** Write an application flow catching optimistic locking errors, reading the updated item, and re-applying the rule "never allow negative stock." Specify when retries are allowed and when to return a conflict/insufficient-inventory error.

**Exercise 4 — Choosing consistency.** An application serves users across three regions. After a user updates their address, the next GET must show the new address; a global dashboard may lag by 30 seconds. Propose consistency levels and a session-token strategy for both use cases.

**Exercise 5 — Multi-region writes.** Two regions concurrently update an inventory item. Explain why Strong is unavailable, why local ETags do not resolve global conflicts, and why LWW can violate business invariants. Propose a write/merge strategy.

**Exercise 6 — Sessions across multiple instances.** A POST hits instance A and the follow-up GET hits instance B. Describe where the SDK caches session tokens, why B might lack the token, and how to pass tokens safely when cross-instance read-your-writes is required.

**Exercise 7 — `If-None-Match`.** Design an item-read endpoint supporting ETag cache validation. Distinguish `304 Not Modified` from `412 Precondition Failed` and specify which header applies to GET vs. updates.

**Exercise 8 — Realistic testing.** Build a test matrix covering ETag, Session, Strong, Bounded Staleness, and multi-region writes. Indicate which tests can run as unit/emulator tests and which require an Azure test account.

## 17. Key Takeaways

- **ETag/`_etag` is an opaque version token generated by Cosmos DB.** Use `If-Match` to protect replace/upsert/delete from lost updates; never parse or mutate ETags.
- **HTTP 412** indicates a precondition is no longer valid. Re-read the item and re-evaluate business rules before retrying; never blindly resend stale payloads.
- Spring Data Cosmos supports optimistic locking via a String `_etag` field annotated with `@Version` for supported containers/operations.
- **Consistency level is a read guarantee**, not a write lock. ETags and consistency solve different problems and are commonly used together.
- The five levels are **Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual**. Choose based on read-your-writes, acceptable staleness, ordering, latency, and region topology.
- Session tokens are managed by the SDK per client and are **partition-bound**. Multi-instance/multi-client deployments need a token propagation strategy if sharing a session.
- **Multi-region writes do not support Strong** and can generate cross-region conflicts. ETags do not replace conflict resolution policies or business rules.
- Test concurrent writers, cross-instance sessions, stale reads, failover, and diagnostics on an appropriate Azure environment; the Emulator cannot prove multi-region guarantees.

## 18. References

- [Optimistic concurrency control and ETags in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/database-transactions-optimistic-concurrency)
- [Azure Spring Data Cosmos — Optimistic Locking with @Version](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Five consistency levels of Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels)
- [Managing consistency and session tokens](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-manage-consistency)
- [CosmosClientBuilder and consistencyLevel in the Java SDK](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.cosmosclientbuilder?view=azure-java-stable)
- [HTTP status codes: 412 Precondition Failed](https://learn.microsoft.com/en-us/rest/api/cosmos-db/http-status-codes-for-cosmosdb)
- [Conflict resolution policies for multi-region writes](https://learn.microsoft.com/en-us/azure/cosmos-db/conflict-resolution-policies)
- [Reliability and multi-region writes in Cosmos DB for NoSQL](https://learn.microsoft.com/en-us/azure/reliability/reliability-cosmos-db-nosql)
