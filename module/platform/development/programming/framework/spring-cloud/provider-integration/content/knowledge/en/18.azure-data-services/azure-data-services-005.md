# Transaction Boundaries and Handling Multi-Partition Updates

A business operation such as **placing an order** may need to deduct inventory, create an order, write an audit record, and emit an event. If the items reside in the same logical partition of Azure Cosmos DB for NoSQL, a Java application can use a **Transactional Batch** to commit all or roll back all. However, when items belong to different partition keys, different containers, or other services such as Azure Blob Storage and Service Bus, independent calls cannot be assumed to form a single transaction. That requires designing data boundaries, multi-step workflows, idempotency, and recovery mechanisms.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secrets, integration testing, and evaluating differences between cloud providers. This lesson focuses on Azure Cosmos DB for NoSQL, Spring Data Cosmos, and coordinating updates when a use case spans beyond a single logical partition.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish single-item atomicity, Transactional Batch, stored procedures, multi-partition transactions, and distributed workflows.
- Identify Cosmos DB for NoSQL transaction boundaries in the Java SDK.
- Use `CosmosBatch` to create/update multiple items in the same container and same partition key.
- Understand operation count, payload size, execution time, and contention limits when multiple transactions share a partition.
- Explain why Spring's `@Transactional` does not automatically turn multiple repository/SDK calls into a cross-partition Cosmos DB transaction.
- Design data and aggregates to keep changes requiring atomicity within the same logical partition when appropriate.
- Use sagas, transactional outbox, change feed, compensation, and reconciliation for multi-partition/multi-service workflows.
- Recognize Cosmos DB's new distributed transactions public preview and current SDK support limits.
- Test rollbacks, ambiguous-outcome timeouts, duplicate events, and recovery after restarts.

## 2. Distinguishing Transaction Types

Not every sequence of operations called inside a Java method executes within the same transaction.

| Level | Scope | Typical Mechanism |
| --- | --- | --- |
| Single item | One item create/replace/patch/delete | Cosmos DB atomic item operation |
| Multiple items in one logical partition | Same container and same full partition key value | Transactional Batch or stored procedure |
| Multiple logical partitions/containers | Multiple Cosmos DB resources in the same account | Production Java currently uses multi-step workflows; distributed transactions are in preview without Java SDK support yet |
| Cosmos DB + Blob/Service Bus/SQL/other APIs | Multiple independent services | Outbox, saga, compensation, idempotency, and reconciliation |

**Atomicity** means all operations in a transaction commit or none commit. **Consistency levels** like Session/Strong are read guarantees across replicas; they do not turn multiple writes into a transaction. **ETag** detects item version changes; it likewise does not combine multiple requests into a transaction.

~~~mermaid
flowchart TD
    A[Business use case] --> B{Where do the changes live?}
    B -->|Single item| C[Single item operation]
    B -->|Same container + same partition key| D[Transactional Batch]
    B -->|Multiple partitions/containers| E[Multi-step workflow / saga]
    B -->|Cosmos + broker / blob / database| F[Outbox / saga / compensation]
    D --> G[Commit all or roll back all]
    E --> H[State + retry + reconciliation]
    F --> H
~~~

## 3. Transaction Scope in Azure Cosmos DB for NoSQL

Cosmos DB for NoSQL supports ACID transactions with snapshot isolation within **a single logical partition**. A Transactional Batch groups point operations sharing the same partition key value inside **one container**. Stored procedures and triggers also execute within the transaction scope of a single logical partition key.

Core requirements:

- All items must belong to the same container.
- All operations must use the same partition key value (with hierarchical partition keys, the full partition key path/value must be provided per contract).
- The batch may only include operations supported by the service/SDK.
- Total payload size and operation count must stay within limits.

For example, container `orders` has partition key path `/tenantId`. The following items can participate in the same transactional batch if they share `tenantId = tenant-42`:

~~~json
{
  "id": "order-1001",
  "tenantId": "tenant-42",
  "type": "order",
  "status": "PENDING"
}
~~~

~~~json
{
  "id": "outbox-order-1001",
  "tenantId": "tenant-42",
  "type": "outbox",
  "eventType": "OrderCreated",
  "eventId": "evt-1001"
}
~~~

Both items can be created together in one batch. If one operation fails, the entire batch rolls back. Conversely, an item in container `inventory` with partition key `warehouseId=HCM-01` cannot be added to a batch on container `orders` to form a cross-container transaction in the current Java SDK.

~~~mermaid
flowchart LR
    subgraph C[Container orders]
      subgraph P[Logical partition tenant-42]
        O[Order item]
        E[Outbox event item]
      end
      P2[Logical partition tenant-77]
    end
    O ---|One Transactional Batch| E
    P2 -. Not in same transaction .- P
    I[Container inventory] -. Not in same batch .-> C
~~~

A cross-partition query or two consecutive `save()` calls do not alter this transaction boundary. Sharing the same tenant across two containers likewise does not make them a valid single batch.

## 4. Choosing Aggregates and Partition Keys for Proper Atomicity Boundaries

Before writing code, identify **which invariants must hold immediately after a commit**. For example:

- An order and its `OrderCreated` event must both exist or neither exist.
- An inventory item must not go negative after a reservation.
- A funds transfer must record debit, credit, and ledger entry together.
- An order and its order lines must be consistent on creation.

If items requiring atomicity can be co-located in the same logical partition while still satisfying throughput and storage limits, designing the partition key around the aggregate is an option. However, never cram all data into one partition just to get transactions:

| Choice | Benefit | Risk |
| --- | --- | --- |
| `tenantId` for order and outbox in the same container | Simple atomic order + event creation; convenient tenant queries | A very large tenant can become a hot partition |
| `orderId` as partition key for order + lines | All items of an order can be updated atomically | Querying all orders of a tenant requires cross-partition queries |
| `warehouseId` for inventory | Reserving multiple SKUs in the same warehouse can share a partition | Large/busy warehouses can experience contention |
| One global key for all data | Easy to put every item in one partition | Does not scale; one logical partition becomes a bottleneck |

The partition key does not only dictate query routing; it is also the **transaction boundary**. If a use case requires transactions across two tenants or two warehouses, do not assume a single partition key can satisfy both. Choose invariants handled via multi-step workflows, or intentionally redesign the aggregate/data model.

## 5. Transactional Batch with the Azure Cosmos DB Java SDK

Spring Data Cosmos provides repositories for CRUD and queries. When you need to group multiple atomic point operations in one container, you can use the **Azure Cosmos DB Java SDK** Transactional Batch API inside an adapter/persistence layer. Do not let controllers construct batches or let application services depend directly on SDK classes.

### 5.1. Dependencies and Containers

The application needs an Azure Cosmos DB Java SDK compatible with your Spring Cloud Azure/Spring Data Cosmos line. The example below assumes a synchronous `CosmosClient` is configured and the `orders` container is provisioned with partition key path `/tenantId`. With a starter, check which beans your version exposes; if the starter only configures an async client/builder, intentionally configure a sync client or use the async API. Never create a new client per transaction or accidentally create two clients with different identities/endpoints.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;

CosmosContainer orders = client.getDatabase("orders-db")
    .getContainer("orders");
~~~

In Spring configuration, you can expose the container as a bean from the starter-created client:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CosmosContainerConfiguration {
    @Bean
    CosmosContainer ordersContainer(CosmosClient client) {
        return client.getDatabase("orders-db").getContainer("orders");
    }
}
~~~

Containers are created via IaC/deployment pipelines in production. The application needs appropriate data-plane permissions for every operation in the batch; never grant subscription admin permissions just to write items.

Examples using `CosmosClient` are synchronous APIs that block the calling thread while awaiting the service. WebFlux/reactive applications can use `CosmosAsyncClient` and the asynchronous `executeCosmosBatch` API; never call synchronous APIs on the event loop.

### 5.2. Creating an Order and Outbox Event in the Same Batch

Example using the Java `CosmosBatch` and `CosmosBatchResponse` APIs:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosBatch;
import com.azure.cosmos.models.CosmosBatchResponse;
import com.azure.cosmos.models.PartitionKey;
import org.springframework.stereotype.Component;

@Component
public class OrderCosmosAdapter {
    private final CosmosContainer orders;

    public OrderCosmosAdapter(CosmosContainer orders) {
        this.orders = orders;
    }

    public void createOrderAndOutbox(
            OrderDocument order,
            OutboxEventDocument event) {

        if (!order.getTenantId().equals(event.getTenantId())) {
            throw new IllegalArgumentException(
                "Order and event must use the same tenant partition");
        }

        PartitionKey partitionKey =
            new PartitionKey(order.getTenantId());

        CosmosBatch batch = CosmosBatch.createCosmosBatch(partitionKey);
        batch.createItemOperation(order);
        batch.createItemOperation(event);

        CosmosBatchResponse response =
            orders.executeCosmosBatch(batch);

        if (!response.isSuccessStatusCode()) {
            throw new OrderWriteException(
                response.getStatusCode(),
                response.getResults());
        }
    }
}
~~~

`OrderDocument` and `OutboxEventDocument` must serialize the `tenantId` partition property properly and target the same container. The example assumes models have an appropriate serializer configured. In practice, use the exact constructors/methods from the SDK version pinned in your BOM; the Java code above reflects the Transactional Batch API published in Microsoft Learn.

If the batch succeeds, both the order and the event commit. If order creation succeeds but outbox event creation fails (e.g., duplicate ID), the entire batch rolls back. There is no state where "the order committed but the event was not written" within this transaction.

### 5.3. Inspecting Per-Operation Results

When an operation in a batch fails:

- The failing operation carries its specific status code, such as 409 if the item already exists.
- The remaining operations typically receive **424 Failed Dependency** because the transaction rolled back.
- Checking only the HTTP status of the first operation can miss the root cause; inspect the result list by index.

~~~java
CosmosBatchResponse response = container.executeCosmosBatch(batch);

if (!response.isSuccessStatusCode()) {
    response.getResults().forEach(result -> {
        System.err.printf(
            "operationStatus=%d%n",
            result.getStatusCode());
    });
    throw new OrderWriteException(
        response.getStatusCode(), response.getResults());
}
~~~

Do not expose account endpoints, keys, or sensitive payloads in HTTP error responses. Record operation IDs and safe activity/diagnostics in internal logs for investigation.

### 5.4. Batch Limits

According to current Transactional Batch documentation, common limits are:

| Limit | Value |
| --- | ---: |
| Operations per batch | Up to 100 |
| Payload size | Up to 2 MB |
| Maximum execution time | 5 seconds |

These limits apply to the NoSQL API Transactional Batch and are subject to service updates. Verify documentation before deployment; never split a large logical transaction into multiple batches and claim the whole sequence is atomic.

## 6. Stored Procedures and Triggers

Cosmos DB for NoSQL supports stored procedures and triggers written in JavaScript. They execute server-side within the transaction scope of a single logical partition key:

- Stored procedures can perform multiple reads/writes in the same partition and commit/roll back together.
- Triggers run alongside item operations when clients explicitly specify the trigger; do not assume triggers fire automatically.
- User-defined functions primarily serve query expressions, not transactional write logic.

Transactional Batch is usually preferable for point operations expressible in Java because the code lives in the application and versions with CI/CD. Stored procedures can help when server-side logic needs to execute close to the data, at the cost of managing JavaScript code, deployment/rollback, and runtime limits. Both remain confined to a single logical partition; stored procedures are not a way to span transactions across partitions.

## 7. Spring's `@Transactional` Does Not Extend Cosmos Transactions

In Spring Boot applications, `@Transactional` is typically tied to a relational database's Spring transaction manager or a specific transaction manager. This annotation **does not automatically turn multiple `CosmosRepository.save()` or SDK client calls into a Transactional Batch**.

Example:

~~~java
@Transactional
public void placeOrder(OrderDocument order, OutboxEventDocument event) {
    orderRepository.save(order);
    outboxRepository.save(event);
}
~~~

Never infer that those two calls are atomic simply because the method carries `@Transactional`. If the repository issues two independent requests, the first can commit before the second fails. To achieve atomicity in Cosmos DB Java, use Transactional Batch for the same container/partition key or a specific mechanism verified for your exact library version.

If the same method also writes to PostgreSQL, Blob Storage, or Service Bus, one service's transaction manager cannot automatically roll back side effects in other services. Before using any transaction annotation, verify the active transaction manager, resource enlistment, and actual framework/version scope; never rely on annotation names alone.

## 8. Multi-Partition Updates: Sagas and Multi-Step Workflows

Suppose an order must:

1. Create the order in partition `tenant-42`.
2. Deduct inventory in partition `warehouse-HCM`.
3. Write an audit record in another container.
4. Send a notification to Service Bus.

In the current Java Cosmos SDK, these operations cannot be combined into a single Transactional Batch because they span different partitions/containers and external services. Design a **saga**: each step is a local transaction, the workflow persists state, and compensating actions are defined if a later step fails.

~~~mermaid
flowchart TD
    A[Receive PlaceOrder] --> B[Create order PENDING]
    B --> C[Reserve inventory]
    C --> D{Reservation succeeds?}
    D -->|Yes| E[Mark order CONFIRMED]
    E --> F[Publish OrderConfirmed]
    D -->|No| G[Mark order REJECTED]
    F --> H[Complete]
    G --> H
    C -. timeout / unknown .-> I[Reconcile reservation]
    I --> D
~~~

The diagram above shows a simple saga. In a real system, the `Reserve inventory` step must also carry an idempotency key; if the response times out, the workflow must check whether the reservation already exists before retrying. Never create a second reservation just because the caller missed the first response.

### 8.1. Orchestration vs. Choreography

| Organization | Description | Best Fit |
| --- | --- | --- |
| **Orchestration** | A coordinator persists state and commands the next step | Multi-step workflows with timeouts, retries, and compensation needing centralized observability |
| **Choreography** | Services emit/consume events and react asynchronously | Short flows with clear service boundaries and stable event contracts |

An orchestrator is not a global transaction manager. It persists progress and decides whether to continue, retry, or compensate. Each service must still enforce idempotency on its local operations and persist outcomes durably.

### 8.2. Saga States

A state machine might use:

| State | Meaning | Transitions |
| --- | --- | --- |
| `PENDING` | Command received, no steps completed yet | `INVENTORY_RESERVED` or `REJECTED` |
| `INVENTORY_RESERVED` | Inventory has been reserved | `CONFIRMED` or `COMPENSATING` |
| `CONFIRMED` | Order completed per business rules | `COMPLETED` |
| `COMPENSATING` | Executing compensating actions | `COMPENSATED` or `COMPENSATION_FAILED` |
| `COMPENSATED` | Prior side effects compensated per rules | Finished or pending audit |
| `FAILED_REQUIRES_REVIEW` | Cannot safely self-recover | Handled by operations staff |

Each state transition should record `operationId`, version/ETag, timestamp, attempt count, current step, and a safe error reason. State transitions must be updated using optimistic version conditions or appropriate local transactions so two workers cannot drive the same saga conflictingly.

## 9. Compensation Is Not Rollback

A Transactional Batch rollback occurs inside a transaction before commit: none of the operations take effect. **Compensation** occurs after a local step has already committed and requires another business action to restore a state close to the original intent.

Examples:

| Completed Step | Possible Compensation | Limitations |
| --- | --- | --- |
| Reserve inventory | Release reservation | May fail to release if the reservation was already consumed |
| Create shipment | Cancel shipment | Carrier may have already dispatched the parcel |
| Charge payment | Refund | Refund is a new transaction with its own fees/timing |
| Write file to Blob | Delete object or mark orphaned | Retention/legal hold may block deletion |
| Send email | Cannot unsend email | Can send a follow-up correction notice |

Because compensation does not erase historical side effects, audit logs must preserve both the original action and the compensating action. Never use the term "rollback" for a workflow that has already sent emails, charged payments, or called external APIs.

## 10. Transactional Outbox in Cosmos DB

A common mistake is writing a business item and then publishing an event in two separate steps:

~~~text
1. Save Order succeeds
2. Publish OrderCreated fails due to broker/network/process crash
=> Order exists, but downstream services never learn about it
~~~

**Transactional Outbox** places the business item and event record into the same Transactional Batch:

~~~mermaid
flowchart LR
    A[Order service] --> B[Transactional Batch]
    B --> C[Order item]
    B --> D[Outbox event item]
    C --> DB[(Cosmos container)]
    D --> DB
    DB --> CF[Change Feed]
    CF --> RELAY[Outbox relay]
    RELAY --> Q[Service Bus / broker]
    Q --> CONSUMER[Idempotent consumer]
~~~

The order and outbox event must share the same container and partition key value. When the batch commits, both appear; if the batch rolls back, no event is emitted. The Change Feed Processor reads event documents and relays them to the broker. This is an **at-least-once** model: the relay may replay events after a restart or unpersisted checkpoint, so consumers must deduplicate by event ID.

### 10.1. Outbox Event Model

~~~java
import java.time.Instant;

public class OutboxEventDocument {
    private String id;
    private String tenantId;
    private String type = "outbox";
    private String eventId;
    private String eventType;
    private int schemaVersion;
    private Instant occurredAt;
    private String aggregateId;
    private String payload;

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getType() { return type; }
    public String getEventId() { return eventId; }
    public String getEventType() { return eventType; }
    public int getSchemaVersion() { return schemaVersion; }
    public Instant getOccurredAt() { return occurredAt; }
    public String getAggregateId() { return aggregateId; }
    public String getPayload() { return payload; }
}
~~~

In production, apply `@Container`, `@Id`, `@PartitionKey`, or matching mappings and ensure `tenantId` serializes to the container's partition key path. The event ID must stay stable across relay retries; never use a broker-generated message ID as the business idempotency key.

### 10.2. Relay and Consumer

The relay must:

- Read the change feed using proper checkpoints/leases.
- Only publish events already committed in the container.
- Attach `eventId`, `eventType`, schema version, and safe correlation context to the message.
- Expect duplicate deliveries; log publish outcomes and apply bounded retries.
- Avoid change feed loops if marking items "published" updates the same container the relay watches.

Consumers need an inbox/deduplication record or unique constraint to process each event ID at most once in terms of business effect. If a consumer triggers side effects outside its database, those side effects also require idempotency or compensating workflows.

Outbox solves **atomically writing business state and event records inside Cosmos DB**. It does not create a transaction between Cosmos DB and Service Bus; the relay can send duplicates, and consumers must be idempotent.

## 11. Multi-Service Updates: Blob Storage, Service Bus, and Databases

| Combination | Built-in Atomicity? | Common Design |
| --- | --- | --- |
| Two items in same container + same partition key | Yes, Transactional Batch | Commit all / roll back all |
| Multiple partitions/containers in current Java SDK | No shared Transactional Batch | Saga/orchestration, idempotency, reconciliation |
| Cosmos DB + Azure Blob Storage | No shared distributed transaction | Staging upload, `PENDING`/`READY` state, cleanup/compensation |
| Cosmos DB + Azure Service Bus | No default shared transaction across resources | Transactional Outbox + Change Feed |
| Cosmos DB + Azure SQL/PostgreSQL | Not automatically atomic | Outbox/saga or clear system-of-record ownership |
| Cosmos DB + external payment API | No atomic rollback | Idempotency keys, saga, refund/compensation |

### 11.1. File Upload and Metadata Write

A workflow can:

1. Create a metadata document in `PENDING` state with an operation ID.
2. Upload the file to Blob Storage using a deterministic object key.
3. Verify the upload result (ETag/version/checksum per contract).
4. Update metadata to `READY` using ETag/optimistic concurrency.
5. If upload fails, transition to `FAILED`; if the process crashes after upload but before metadata update, a reconciliation job inspects the object and either finalizes or cleans up.

Never assume deleting a Blob inside a catch block always succeeds. Cleanup itself is a side effect requiring retries and auditing.

### 11.2. Emitting Events After Saving Data

Never write `repository.save(order); serviceBusSender.sendMessage(event);` assuming the two calls are atomic. Write the order + outbox via a batch; let the relay send the message after commit. If the relay crashes after broker acknowledgment but before checkpointing, the event may be resent. Consumers deduplicate by event ID.

## 12. Distributed Transactions Public Preview: What Java Developers Need to Know

**Important update:** Microsoft has announced **distributed transactions for Azure Cosmos DB for NoSQL in public preview**. This preview feature enables read/write transactions across multiple logical partitions, containers, and databases within the same account/region. However, Microsoft Learn documentation currently announces support only through the **Azure Cosmos DB .NET v3 SDK preview**; the "Supported APIs and SDKs" section explicitly notes that support for other SDKs is under development. Therefore, **Spring Boot/Spring Data Cosmos applications using the Java SDK cannot use the distributed transaction preview API under current guidance**.

Published preview limitations:

- NoSQL (Core SQL) API only.
- Provisioned throughput accounts (manual or autoscale), not serverless.
- Single write-region accounts only; multi-region writes are not supported.
- Several features/configurations are not yet supported, such as CMK, continuous backup, long-term retention, partition merge, HPK, and certain sovereign/air-gapped/government environments.
- Preview enrollment required; no SLA and limits are subject to change.
- Current docs specify up to 100 operations and 2 MB payload per transaction.

Do not cite .NET's `CreateDistributedWriteTransaction()` as if it were a Java API. Once Microsoft announces Java SDK and Spring integration support, verify versions, enrollment, semantics, and updated limits before replacing sagas/outbox.

In preview, multi-partition transactions also carry critical nuances: transactions route to the write region; data replicates asynchronously to secondary regions; session tokens are returned per operation/partition and must be propagated properly when read-your-writes is needed in follow-up transactions. `FastResponse` mode can return before final commit/abort, so that response must not be interpreted as final commit outcome. Cancellation does not prove a transaction rolled back; never replay blindly.

For this Spring Data Cosmos Java lesson, **same-partition-key Transactional Batch remains the direct atomicity option**; multi-partition workflows still require sagas/outbox until official Java SDK support arrives and your project confirms preview/GA eligibility.

## 13. Handling Timeouts, Retries, and Ambiguous Outcomes

A request can time out on the client after the server has already committed. This matters especially for transactions: a client missing a response does not guarantee the transaction rolled back.

| Scenario | How to Handle |
| --- | --- |
| Batch returns success | Record commit and return result |
| Batch returns operation-specific error | Inspect failing operation status; others may show 424 from rollback |
| Batch returns 409 create conflict | Check whether item/operation ID already exists and distinguish duplicate vs. real conflict |
| Batch returns 412 ETag/precondition | Re-read items, re-evaluate invariants, and build a new batch if still valid |
| 429/throttling | Honor retry-after/SDK retries; bound concurrency and retry budget |
| Timeout/network reset after send | Reconcile via deterministic IDs/operation records before replaying |
| Saga step fails | Idempotent retry or run compensation per state machine |

### 13.1. Idempotency Keys and Deterministic Item IDs

An order placement command can carry an application-generated `operationId`. Use stable IDs to:

- Create order/outbox items tied to the same command.
- Prevent a retried request from creating multiple orders.
- Look up status when the first response is lost.
- Deduplicate in relays and consumers.

Never generate fresh random IDs on every retry. If a create returns 409, read the item by ID + partition key and compare the `operationId`/state to determine whether the earlier transaction committed or another request claimed the ID.

### 13.2. Contention on the Same Logical Partition

Many concurrent transactions on the same partition key can cause contention. Cosmos DB may return errors related to transactions waiting to complete, such as `TXN_WAIT_FOR_TRANSACTION_END`. Mitigation steps:

- Keep batches short with fewer operations.
- Avoid external network calls while constructing/holding a transaction.
- Retry with exponential backoff and jitter when errors are confirmed transient.
- Bound concurrent workers targeting a hot partition key.
- Revisit the partition key if a single logical partition handles too many concurrent transactions.

Increasing RU/s does not necessarily resolve transaction contention on a single partition key.

## 14. Testing Transaction Boundaries

### 14.1. Testing Transactional Batch

Using the emulator or an Azure test account, verify:

1. Creating two items in the same container and partition key within one batch; both exist after commit.
2. Failing the second operation (e.g., creating an item that already exists); the first item is not persisted.
3. Mixing partition keys in a batch; verify the SDK/service rejects it.
4. Inspecting 409 and 424 statuses by operation index.
5. Testing ETag/`If-Match` inside a batch if the use case requires concurrency control.
6. Testing batches near payload/operation limits without using production data.

### 14.2. Testing Sagas and Compensation

Simulate every failure point:

- After writing `PENDING` order, before reserving inventory.
- Inventory reserved, but response lost.
- Order confirmed, but relay has not yet published the event.
- Broker received the event, but relay crashed before checkpointing.
- Compensating inventory release fails.
- Worker restarts while saga is in `COMPENSATING` state.

After every restart, the workflow must read durable state and resume from a safe step; never rely on in-memory instance variables.

### 14.3. Testing Outbox

| Test Case | Expected Behavior |
| --- | --- |
| Order + event batch succeeds | Both items exist together |
| Event creation fails | Order does not exist due to rollback |
| Relay publishes event then crashes before checkpoint | Event may replay; consumer produces no duplicate business side effects |
| Old event schema version | Consumer handles backward-compatibly or routes to dead-letter |
| Increasing change feed lag | Alert triggers and worker resumes from checkpoint |
| Poison event | Bounded retries, DLQ/quarantine, does not block other events indefinitely |

### 14.4. Emulator vs. Real Azure

The Cosmos DB Emulator is helpful for testing CRUD, Transactional Batch, and basic mapping. Real Azure must be used to verify Managed Identity/native data-plane RBAC, networking, throughput, throttling, diagnostics, failover, and operational behavior. Distributed transactions preview currently has enrollment conditions and a separate SDK; do not simulate it by assuming the emulator supports it.

## 15. Solution Selection Workflow

~~~mermaid
flowchart TD
    A[List business invariants] --> B[Group items that must commit together]
    B --> C{Same container + same full partition key?}
    C -->|Yes| D[Transactional Batch / stored procedure]
    C -->|No| E{Is there suitable Java SDK distributed transaction support?}
    E -->|No| F[Saga / outbox / compensation]
    E -->|Yes| G[Evaluate GA/preview status, limits, SLA, and topology]
    G --> H{Production-eligible?}
    H -->|No| F
    H -->|Yes| I[Dedicated integration and failure tests]
    D --> J[Test atomicity, 409/412/424, and timeouts]
    F --> K[Test idempotency, recovery, and reconciliation]
    I --> L[Deploy with observability]
    J --> L
    K --> L
~~~

Before implementing, answer:

1. Which invariants must hold immediately when the request returns success?
2. Do the items requiring atomicity share the same container and partition key value?
3. Can the aggregate be designed to group them without creating a hot partition?
4. When crossing boundaries, which steps are retryable and which require compensation?
5. How do you determine whether an operation committed if the response is lost?
6. Are relays/consumers idempotent by event ID?
7. If a worker restarts mid-workflow, what durable state lets it resume?
8. Which distributed transaction features/SDKs are actually supported in the target deployment version?

## 16. Common Design Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Assuming `@Transactional` wraps multiple Cosmos repository saves | Partial data can commit independently | Use Transactional Batch within the proper scope |
| Adding items from different partitions to a batch | Invalid batch | Validate full partition keys before constructing the batch |
| Putting an entire tenant in one partition just for atomicity | Hot partitions, contention, and storage limits | Choose appropriate aggregates/invariants; use sagas when needed |
| Writing Cosmos then sending Service Bus in the same method | Lost events or orphaned events | Transactional Outbox + Change Feed |
| Calling two services then catching exceptions to manually roll back | Compensation can fail and cannot erase historical side effects | State-machine saga and reconciliation |
| Retrying after timeout with a new ID | Creates duplicate orders/payments/reservations | Deterministic operation IDs and state reconciliation |
| Treating outbox delivery as exactly-once | Consumers may process duplicate events | At-least-once + idempotent consumers |
| Treating Change Feed as a single transaction with the broker | Publish/checkpoint can drift | Outbox, checkpoints, and deduplication |
| Using .NET distributed transaction preview code from Spring Java | Incompatible SDK/API | Adopt only after official Java support is released |
| Ignoring transaction contention | 429s/transaction waits and high latency | Short batches, backoff, bounded concurrency, partition design |

## 17. Practice Exercises

**Exercise 1 — Ordering within one partition.** Orders and outbox events reside in the same `orders` container with partition key `tenantId`. Write a batch creating both items. Intentionally trigger a duplicate event ID and verify the entire batch rolls back. Inspect the failing operation's status and the 424 statuses.

**Exercise 2 — Cross-partition inventory.** Orders live in a tenant partition while inventory lives in a warehouse partition. Design a saga with `PENDING` order creation, inventory reservation, order confirmation, and reservation release when needed. Specify idempotency keys and state transitions at every step.

**Exercise 3 — Blob + Cosmos.** Upload a file to Azure Blob and record metadata in Cosmos. Design `PENDING`/`READY`/`FAILED` states, deterministic object keys, cleanup, and reconciliation for a crash right after upload.

**Exercise 4 — Transactional Outbox.** Design an order item and outbox event in the same Transactional Batch. Build a Change Feed relay to Service Bus; simulate a crash after publishing but before checkpointing and prove the consumer causes no duplicate business effects.

**Exercise 5 — Batch limits.** A workflow must create 150 items totaling 3 MB and taking over 5 seconds. Explain why splitting into two batches cannot be claimed atomic; propose an aggregate redesign or multi-step workflow.

**Exercise 6 — Contention.** 200 concurrent requests update the same partition key and trigger `TXN_WAIT_FOR_TRANSACTION_END`. Design a load test, shorten transaction duration, bound concurrency, and re-evaluate the partition key.

**Exercise 7 — Ambiguous timeouts.** An order + event batch times out after dispatch. Design a lookup procedure by operation ID before retrying; distinguish safe retries from retries that risk duplicates.

**Exercise 8 — New preview.** Read the Cosmos DB distributed transactions public preview documentation. List account prerequisites, supported SDKs, limits, and why the feature cannot yet be used directly in Spring Data Cosmos Java. State what evidence is required before replacing sagas with distributed transactions.

## 18. Key Takeaways

- Cosmos DB for NoSQL supports ACID transactions within **one logical partition**; Java Transactional Batch requires the same container and same full partition key value.
- **Transactional Batch** fits point operations that must commit/roll back together; a batch failure rolls back all operations, with the failing operation carrying its specific status and others typically showing 424.
- Current docs specify Transactional Batch limits of **100 operations, 2 MB, and 5 seconds**; re-verify before implementation.
- `@Transactional` does not automatically turn multiple repository/SDK calls into a Transactional Batch or a transaction across Cosmos, Blob, and brokers.
- When updates cross partitions/containers/services, use **sagas, outbox, compensation, idempotency, and reconciliation** to handle partial failures.
- Transactional Outbox writes the business item and event within the same partition/batch; Change Feed relays are typically at-least-once, so consumers must deduplicate.
- Multi-partition distributed transactions are in **public preview**, but current docs list support for the .NET v3 SDK only; Spring Data Cosmos Java has no corresponding API in current support lists. Never treat previews as production guarantees.
- Timeouts/cancellations do not prove a transaction rolled back. Use stable operation IDs and reconcile state before replaying.

## 19. References

- [Transactional Batch operations in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch)
- [CosmosBatch Java API](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.models.cosmosbatch?view=azure-java-stable)
- [CosmosContainer.executeCosmosBatch Java API](https://learn.microsoft.com/en-us/java/api/com.azure.cosmos.cosmoscontainer.executecosmosbatch)
- [Database transactions and optimistic concurrency control](https://learn.microsoft.com/en-us/azure/cosmos-db/database-transactions-optimistic-concurrency)
- [Stored procedures, triggers, and UDFs](https://learn.microsoft.com/en-us/azure/cosmos-db/stored-procedures-triggers-udfs)
- [Partitioning and transaction scope](https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning)
- [Implement the Transactional Outbox pattern with Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-out-box-cosmos)
- [Saga distributed transactions pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/saga)
- [Compensating Transaction pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction)
- [Use distributed transactions in Azure Cosmos DB — public preview and SDK support](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-configure-and-use-distributed-transactions)
