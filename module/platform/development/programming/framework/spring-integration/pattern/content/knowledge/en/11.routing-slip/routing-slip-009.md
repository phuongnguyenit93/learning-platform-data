# Idempotency when a message re-runs a routing slip

## 1. Context: a dynamic path can run multiple times

In the **Routing slip** chapter of the **SPRING_INTEGRATION_PATTERN** module, we practice Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Router, Filter, Transformer, Splitter, Aggregator, and Gateway organize business steps; retry, error channels, correlation, and per-branch observability help flows keep operating during failures.

A routing slip describes **a message's path through subsequent endpoints**. Instead of hardcoding multiple routers for every branch, the message carries information so an endpoint knows which channel to send its reply to after finishing processing. This pattern is convenient for flexible processes, yet when **a message is re-run**, already executed steps may be invoked again.

For example, the system receives a **shipment.requested** event and executes:

1. **validateShipment**: validates data (no side effects).
2. **reserveInventory**: records inventory reservation (has side effects).
3. **chargePayment**: requests payment collection (has external side effects).
4. **notifyCustomer**: sends confirmation notification (has external side effects).

If a network error occurs after `chargePayment` collects payment but before the result is confirmed, re-sending the same event from the start can **reserve stock twice, charge twice, or send duplicate emails**. A routing slip does not automatically track which business side effects already occurred.

~~~mermaid
flowchart LR
    I["ShipmentRequested evt-301"] --> S["Routing slip"]
    S --> V["validateShipment"]
    V --> R["reserveInventory"]
    R --> C["chargePayment"]
    C --> N["notifyCustomer"]
    C -->|"Lost response / error"| X["Retry same event"]
    X -.-> S
~~~

**Lesson objectives**

- Explain accurately how routing slip, path, and current position work in Spring Integration.
- Distinguish **single-handler retry**, **replay from ingress**, **resume from checkpoint**, and **broker redelivery**.
- Construct idempotency keys by **business event + side-effecting step**.
- Design transactions, checkpoints, outbox, and external idempotency for each leg.
- Understand the role and limits of Idempotent Receiver and MetadataStore.
- Write tests for re-execution, failures after side effects, concurrent runs, restarts, and flow versioning.

## 2. What does Routing slip in Spring Integration actually do?

Spring Integration has supported the Routing Slip pattern since version 4.1. The framework uses the **routingSlip** metadata on a message to find the **next channel** on **AbstractMessageProducingHandler** endpoints when the endpoint produces a reply and does **not** set an explicit `outputChannel`.

Once the routing slip is exhausted, the framework falls back to normal **replyChannel** resolution. Routing slip **does not create a durable workflow engine by itself** and does not guarantee each step executes only once.

### 2.1. Path and routingSlipIndex

A routing slip describes a **path** of entries (typically channel names). The framework manages **routingSlipIndex** to know the current entry. In Spring Integration, path and index belong to **the framework-managed `routingSlip` header structure**; do not treat the index as an independent arbitrary header and increment it manually.

Suppose the path is:

~~~text
validateChannel -> reserveChannel -> chargeChannel -> notifyChannel
~~~

A conceptual model:

| Stage | Next entry | Meaning |
| --- | --- | --- |
| Start | validateChannel | Sends reply from slip-attaching endpoint to validate |
| After validate | reserveChannel | Validate succeeded and produced a reply |
| After reserve | chargeChannel | Reserve produced a reply to forward |
| After charge | notifyChannel | Charge produced a reply to forward |
| After notify | End of path | Normal `replyChannel` handling if a reply exists |

**The index is a routing position, not proof of commit.** A leg may have written to a database or succeeded on an HTTP call and then crashed before progress updates persisted. Conversely, a message with a later slip position does not prove all preceding side effects succeeded.

### 2.2. Conditions for the routing slip to be consulted

The routing algorithm runs when **the handler produces a reply** and **no explicit `outputChannel` is configured** for that endpoint. If the handler returns null, the flow may stop there; never assume the message automatically moves to the next step.

~~~mermaid
flowchart TD
    H["Handler receives message"] --> R{"Produces reply?"}
    R -->|"No"| STOP["No next message created"]
    R -->|"Yes"| E{"Explicit outputChannel on endpoint?"}
    E -->|"Yes"| OUT["Forward to outputChannel"]
    E -->|"No"| SL{"Remaining path in routing slip?"}
    SL -->|"Yes"| NEXT["Select next channel"]
    SL -->|"Exhausted"| REPLY["Evaluate normal replyChannel"]
~~~

If an `outputChannel` is explicitly specified, do not expect the routing slip to override that destination. Similarly, if a step returns null before the final leg, later steps do not run automatically.

### 2.3. Static entries and RoutingSlipRouteStrategy

A path can contain:

- Fixed `MessageChannel` bean names.
- **`RoutingSlipRouteStrategy`** bean names that decide channels dynamically.
- SpEL expressions, depending on `RoutingSlipHeaderValueMessageProcessor` handling.

A **`RoutingSlipRouteStrategy`** can be queried multiple times at **the same path position**, until it returns null or an empty string so the framework advances to the next entry. When the strategy returns a channel name, the index can **remain unchanged** so the strategy decides next time whether to continue.

This matters for idempotency: a channel chosen **multiple times intentionally** by a strategy is not necessarily a duplicate. For example, a step processing multiple items sequentially needs keying by **itemId or logical iteration**; using only `eventId + stepId` could mistakenly skip legitimate iterations.

### 2.4. The routingSlip header is not business completion state

| Component | Responsibility |
| --- | --- |
| routingSlip path | Knows which channels or strategies to visit |
| routingSlipIndex | Routing state inside the current message |
| eventId | Identifies a logical business event across redeliveries |
| stepId | Identifies a specific business task |
| step status | PENDING, PROCESSING, COMPLETED, FAILED, UNKNOWN |
| idempotency record | Prevents repeating an already completed effect by business key |
| outbox/inbox or broker | Supports durable delivery and redelivery if configured |

Routing slip helps **pick the path**, while completion state and side-effect commitments must be managed by **appropriate application and infrastructure mechanisms**.

## 3. When does the same routing slip run again?

There are several types of re-execution, and each needs a different recovery mechanism.

### 3.1. Replay from the ingress point

A producer, scheduler, or operator submits the **same eventId** into ingress a second time. If at ingress the application rebuilds the `routingSlip` path from scratch, the chain can run again starting from validate. The path is valid, yet every side-effecting step must tolerate repeated calls.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Slip ingress
    participant V as Validate
    participant R as Reserve
    participant C as Charge
    P->>S: evt-301 attempt 1
    S->>V: validate
    V->>R: reserve
    R->>C: charge
    C--xP: Lost response
    P->>S: evt-301 attempt 2
    S->>V: validate again
    V->>R: reserve again
    Note over R: Must recognize already completed effect
~~~

### 3.2. Retry directly at a handler

When a Retry Advice wraps **around the `chargePayment` handler**, the same message may be processed multiple times at **one step** without returning to ingress. When a transient error occurs **before** the side effect, retry can succeed. If the error occurs **after** the side effect but **before** the response, retry can create a duplicate.

Do not conclude that local retry is always safer than full-flow retry: it only **narrows the scope of re-executed work**. At HTTP, database, or email boundaries, idempotency and explicit error policies are still required.

### 3.3. Redelivery from a broker or queue

If a leg forwards messages to a broker, a consumer can crash after updating the target system but before acknowledging. The broker redelivers the message to a consumer. How much of the `routingSlip` header survives depends on the adapter, serialization, header persistence/publishing, and where the message is re-fetched.

**Never assume a broker always preserves `routingSlip` or `routingSlipIndex` intact.** Some distributed environments cannot serialize slip contents if the path contains inline expression strategies. Test how your adapter transfers headers and rely on a **durable business checkpoint** whenever exact resumption is needed.

### 3.4. Resume from snapshot/checkpoint

A system may persist completed step state and **decide to continue from the unfinished step**. If a snapshot stores only `routingSlipIndex` without storing side-effect state, two discrepancies remain:

- **Stale index behind reality:** side effect succeeded, yet index was not saved → risk of duplicate effect.
- **Index ahead of reality:** progress was saved before effect committed → risk of skipping an unfinished effect.

When safe resumption is required, checkpoints, effects, and idempotency records must share consistent commit semantics or have reconciliation when spanning different systems.

## 4. Defining idempotency at the per-step level

Suppose `evt-301` must execute three effects:

| Step ID | Effect | How can it be safely repeated? |
| --- | --- | --- |
| validate | Pure data validation | Safe to re-run; creates no side effects |
| reserve-inventory | Records reserved quantity | Unique business operation or DB transaction |
| charge-payment | External payment request | Stable idempotency key sent to payment API |
| notify-customer | Sends email/SMS | Provider key, outbox, delivery state, and reconciliation |

A key typically takes the form:

~~~text
idempotencyKey = trustedTenantId + ":" + eventId + ":" + logicalStepId
~~~

Examples:

| Tenant | Event | Step | Key |
| --- | --- | --- | --- |
| tenant-A | evt-301 | reserve-inventory | tenant-A:evt-301:reserve-inventory |
| tenant-A | evt-301 | charge-payment | tenant-A:evt-301:charge-payment |
| tenant-A | evt-301 | notify-customer | tenant-A:evt-301:notify-customer |
| tenant-A | evt-302 | charge-payment | tenant-A:evt-302:charge-payment |

**Do not use a single key for the entire routing slip** and mark the whole flow done once the first step succeeds. Each step has its own state and risk; an already finished step must not cause later steps to be dropped on retry.

### 4.1. Never use MessageHeaders.ID as a business key

Spring Message's ID serves messaging transport; when a message is rebuilt across a Transformer, Gateway, or adapter, the technical ID can change. `eventId` must identify **one logical event** across deliveries and retries.

Fields serve distinct purposes:

- **eventId**: one logical event, stable across retries/redeliveries.
- **orderId/shipmentId**: a business entity that may have many events.
- **logicalStepId**: an effect such as `reserve-inventory` or `charge-payment`.
- **routingSlipIndex**: routing position, not a business key.
- **attemptId**: a single attempt; changes across retries, unsuitable for preventing duplicate effects.
- **correlationId**: links a group of messages (Splitter/Aggregator); does not prove processing happened.

### 4.2. When the same step is legitimately called multiple times

A strategy may repeat a processing step for multiple line items, such as calculating fees for three parcels. Then the key may need:

~~~text
tenantId : eventId : logicalStepId : packageId
~~~

Never include **attemptId** in the key: doing so gives each retry a fresh key and defeats deduplication. Nor should you use **routingSlipIndex** in place of `packageId` when a strategy repeats at the same index.

### 4.3. Flow versions and path changes

When upgrading a flow from:

~~~text
validate -> reserve -> charge -> notify
~~~

to:

~~~text
validate -> reserve -> fraudCheck -> charge -> notify
~~~

decide whether older events use the **old path** or **migrate to the new path**. Resuming under the new version may introduce a step that never ran. If you mechanically embed `flowVersion` into every idempotency key, reserve/charge steps already completed under the old version could re-execute.

**Rule:** keep **`logicalStepId` stable per business effect**. Only mint a new effect identity when you genuinely intend the business to run a new operation. Store `flowVersion` separately for migration and audit rather than letting version bumps duplicate all side effects.

## 5. Java DSL: building a routing slip with clear steps

Spring Integration Java DSL supports adding routing slips via **`HeaderEnricherSpec.routingSlip`**. The example below creates a fixed routing slip for a shipment type. We use **`DirectChannel`** for easy observation, while step idempotency services are covered in the next section.

### 5.1. Data contract and services

~~~java
import java.math.BigDecimal;

record ShipmentRequested(
        String eventId,
        String tenantId,
        String orderId,
        String sku,
        int quantity,
        BigDecimal totalVnd) {}

interface ShipmentValidation {
    void validate(ShipmentRequested event);
}

interface InventoryReservation {
    void reserveOnce(ShipmentRequested event);
}

interface PaymentCharging {
    void chargeOnce(ShipmentRequested event);
}

interface CustomerNotification {
    void notifyOnce(ShipmentRequested event);
}
~~~

The **Once** suffix in method names expresses the **required contract**, not proof that an implementation is already idempotent. Service implementations must be built and tested around valid keys, especially for side effects in databases or external systems.

### 5.2. Declaring the routing slip and channels

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ShipmentRoutingSlipConfig {

    @Bean
    MessageChannel shipmentInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validateChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel reserveChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel chargeChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel notifyChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow startShipmentSlip() {
        return IntegrationFlow.from("shipmentInput")
                .enrichHeaders(headers -> headers.routingSlip(
                        true,  // Overwrite any prior slip at trusted ingress.
                        "validateChannel",
                        "reserveChannel",
                        "chargeChannel",
                        "notifyChannel"))
                .get();
    }

    @Bean
    IntegrationFlow validateShipment(ShipmentValidation validation) {
        return IntegrationFlow.from("validateChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    validation.validate(event);
                    return event;  // Produce reply to advance routing slip.
                })
                .get();
    }

    @Bean
    IntegrationFlow reserveInventory(InventoryReservation inventory) {
        return IntegrationFlow.from("reserveChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    inventory.reserveOnce(event);
                    return event;
                })
                .get();
    }

    @Bean
    IntegrationFlow chargePayment(PaymentCharging payments) {
        return IntegrationFlow.from("chargeChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    payments.chargeOnce(event);
                    return event;
                })
                .get();
    }

    @Bean
    IntegrationFlow notifyCustomer(CustomerNotification notifications) {
        return IntegrationFlow.from("notifyChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    notifications.notifyOnce(event);
                    return null; // Final step: emit no new reply.
                })
                .get();
    }
}
~~~

**Technical notes:**

1. Header Enricher creates a routing slip containing the channel names. In supporting Java DSL versions, the **`true`** parameter of `routingSlip(true, ...)` instructs it to overwrite an existing routing-slip header.
2. Service Activators at validate/reserve/charge return the payload to produce a reply; they **do not configure an explicit `outputChannel`**, allowing the routing slip to be consulted.
3. Notify is the final step needing no reply in this one-way example; if a Gateway must return a result, design request/reply and handle `replyChannel` once the slip is exhausted. Never let an intermediate step return null when mandatory steps remain.
4. This is an **illustrative flow**: the application still needs beans implementing the four interfaces, input validation, transaction configuration, and recovery strategy.
5. If an explicit channel is wired immediately after a handler, the flow may follow that `outputChannel` instead of the routing slip path. Test the real topology rather than merely inspecting channel names in the header.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant I as Header Enricher
    participant V as Validate
    participant R as Reserve
    participant C as Charge
    participant N as Notify
    P->>I: ShipmentRequested
    I->>V: Slip entry 0
    V-->>R: Reply, entry 1
    R-->>C: Reply, entry 2
    C-->>N: Reply, entry 3
    N-->>P: No reply, one-way complete
~~~

### 5.3. Why must the path be attached at trusted ingress?

Because a routing slip holds channel or strategy names, it can influence **processing topology**. Never accept unverified paths supplied by untrusted HTTP/broker clients. A sender could inject sensitive channels, loops, or unintended expressions into the path if the system copies raw external headers.

At the trust boundary:

- Authenticate the producer, tenant, and event-submission permissions.
- Normalize/validate payload and attach a system-managed, stable `eventId`.
- Build the routing slip from an **internal allowlist of channels/strategies**.
- Bound path length, leg count, and dynamic choices.
- Manage `replyChannel`, `errorChannel`, and message correlation according to real needs.

**Overwriting `routingSlip`** handles only one header; it does not automatically strip other malicious headers. When reconstructing messages at ingress, consider allowlisting which headers are kept.

## 6. Placing deduplication at the right boundary

In a multi-step routing slip, deduplicating at ingress by `eventId` can lose unfinished work. For instance, the first run reserved inventory, then `charge` failed to complete; if ingress sees `eventId` was already received and **drops the entire retry**, `charge` and `notify` never get a chance to run.

~~~mermaid
flowchart TD
    E["Replay evt-301"] --> D{"Global flow dedup?"}
    D -->|"Already saw evt-301"| LOST["Dropped: charge never finished"]
    E --> STEP{"Dedup per logical step"}
    STEP --> V["Validate re-runs safely"]
    STEP --> R["Reserve already completed: skip effect"]
    STEP --> C["Charge not completed: execute"]
    STEP --> N["Notify once charge succeeds"]
~~~

A practical design separates two layers:

1. **Transport and coordination layer**: knows which step the message is at and which legs remain unfinished; places retry/replay mechanisms appropriately.
2. **Business effect layer**: services at each leg execute under idempotent contracts, recognizing already completed or ambiguous outcomes.

Never equate "a message passed through a step" with "its side effect committed". A log entry saying "called charge" only proves an attempt occurred—not that payment succeeded.

### 6.1. Per-step processing state table

A minimal model:

| Status | Meaning | Action on retry |
| --- | --- | --- |
| **PENDING** | No attempt yet, or work prepared | Can begin processing |
| **PROCESSING** | An attempt is currently claimed | Check lease/lock; avoid unbounded parallel runs |
| **COMPLETED** | Effect committed or validly confirmed | Skip effect, emit reply so slip continues |
| **FAILED_RETRYABLE** | Transient error, not yet completed | Bounded retry with backoff |
| **FAILED_FINAL** | Cannot recover automatically | Quarantine/DLQ and manual intervention |
| **UNKNOWN** | Unclear whether external effect occurred | Reconcile or retry with idempotency key |

**COMPLETED** must have a clearly defined business meaning. An HTTP 202 Accepted may only mean downstream queued the request, not that payment was collected; step status must accurately reflect the external API contract.

## 7. SQL example: effects within the same database

For a `reserveInventory` step where both the deduplication record and inventory deduction share **one database and transaction manager**, you can commit atomically using a unique constraint and transaction.

~~~sql
CREATE TABLE routing_step_execution (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    logical_step_id VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, event_id, logical_step_id)
);

CREATE TABLE stock_balance (
    tenant_id VARCHAR(80) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
    PRIMARY KEY (tenant_id, sku)
);
~~~

Implementation example using Spring JDBC and PostgreSQL:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class JdbcInventoryReservation implements InventoryReservation {
    private final JdbcTemplate jdbc;

    JdbcInventoryReservation(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public void reserveOnce(ShipmentRequested event) {
        String step = "reserve-inventory";

        // PostgreSQL: only one attempt can insert the new key.
        int claimed = jdbc.update("""
                INSERT INTO routing_step_execution
                    (tenant_id, event_id, logical_step_id, status)
                VALUES (?, ?, ?, 'PROCESSING')
                ON CONFLICT DO NOTHING
                """,
                event.tenantId(), event.eventId(), step);

        if (claimed == 0) {
            // Safe to skip only if the existing entry is already COMPLETED.
            String status = jdbc.queryForObject("""
                    SELECT status FROM routing_step_execution
                    WHERE tenant_id = ? AND event_id = ?
                      AND logical_step_id = ?
                    """,
                    String.class,
                    event.tenantId(), event.eventId(), step);
            if ("COMPLETED".equals(status)) {
                return;
            }
            throw new IllegalStateException(
                    "Step not yet completed; must retry in a controlled manner");
        }

        int updated = jdbc.update("""
                UPDATE stock_balance
                   SET available_quantity = available_quantity - ?
                 WHERE tenant_id = ? AND sku = ?
                   AND available_quantity >= ?
                """,
                event.quantity(), event.tenantId(),
                event.sku(), event.quantity());

        if (updated != 1) {
            throw new IllegalStateException("Insufficient stock or invalid SKU");
        }

        jdbc.update("""
                UPDATE routing_step_execution
                   SET status = 'COMPLETED',
                       completed_at = CURRENT_TIMESTAMP
                 WHERE tenant_id = ? AND event_id = ?
                   AND logical_step_id = ?
                """,
                event.tenantId(), event.eventId(), step);
    }
}
~~~

**Preconditions:** the event has been validated (non-empty `eventId`/`tenantId`/`sku`, positive `quantity`, `tenantId` from an authenticated source). Both tables and `JdbcTemplate` must share the same database and transaction manager; the method must be invoked through a Spring proxy so **`@Transactional`** actually takes effect.

### Why is this pattern useful?

When the operations above share one transaction:

1. The first attempt **inserts the key** and updates inventory.
2. If a failure occurs before commit, **both the key insert and the stock change roll back**.
3. Once committed, a retry sees the existing key, reads **COMPLETED**, and **does not deduct inventory a second time**.
4. Two concurrent attempts racing for the same key are serialized by **the primary key and transaction locking**, instead of relying on non-atomic check-then-insert logic.

While a transaction is still in flight, waiting or blocking behavior of a second transaction depends on isolation and locking. An existing entry that is not yet COMPLETED must be treated as needing investigation/retry, never assumed succeeded.

**Guarantee boundary:** this pattern prevents duplicate stock deductions **within one database** when the same `eventId`/`stepId` is used properly. It does not guarantee `chargePayment` or email notifications ran only once. External APIs require separate strategies.

### 7.1. Why not just use an in-memory Set or MetadataStore?

~~~java
// Counterexample: claiming before the side effect finishes.
if (seen.add(event.eventId() + ":charge-payment")) {
    paymentClient.charge(event);
}
~~~

If `seen.add` succeeds and then `paymentClient.charge` fails, retries can be skipped permanently. If the app restarts, the `Set` loses all data and charging can repeat. With multiple instances, each JVM has its own separate `Set`.

A **`ConcurrentMetadataStore`** supports atomic operations like `putIfAbsent`, yet if recording the claim and executing the effect are not in the same transaction, an atomic claim alone is insufficient for an exactly-once effect. The same applies to Redis/DB caches if completion state is modeled poorly.

## 8. HTTP-calling leg: charged payment, lost response

Suppose `chargePayment` sends a request to a payment provider. The provider **already collected payment**, yet the connection drops before the application receives the HTTP response. From the client's perspective, the leg's outcome is **UNKNOWN**.

~~~mermaid
sequenceDiagram
    participant W as Workflow worker
    participant P as Payment provider
    participant S as Step store
    W->>P: POST charge, key=tenant-A:evt-301:charge-payment
    P->>P: Payment collected
    P--xW: Lost response
    W->>S: Save UNKNOWN / retryable status
    W->>P: Query by same key or idempotent retry
    P-->>W: Existing charge result
    W->>S: Mark COMPLETED
~~~

**You cannot decide a request failed merely from a timeout.** Resending the request with a **different idempotency key** may cause the provider to treat it as a brand-new payment.

### 8.1. Sending the same key for the same effect

~~~java
final class ExternalChargeKey {
    static String forEvent(ShipmentRequested event) {
        return event.tenantId()
                + ":" + event.eventId()
                + ":charge-payment";
    }
}

interface PaymentProviderPort {
    // Example adapter contract: provider accepts an idempotency key.
    ChargeResult charge(ShipmentRequested event, String key);

    // If provider supports lookup by the same key.
    ChargeResult findByIdempotencyKey(String key);
}

record ChargeResult(boolean succeeded, boolean unknown) {}
~~~

This is an **illustrative contract interface**, not a built-in Spring Integration API. Each provider has its own key retention, TTL, scope, response caching, and retry rules; read your provider's documentation and test timeout behavior.

A coordination strategy:

1. For keys already **COMPLETED**, skip charging and continue the slip.
2. For **PENDING/FAILED_RETRYABLE** keys, call charge using the **same key**.
3. For **UNKNOWN** state, query the outcome by key or reconcile; retry only when the provider guarantees appropriate idempotent semantics.
4. Once the provider confirms success, persist COMPLETED before marking the business leg ready to advance.
5. For unrecoverable errors, transition the workflow to a manual-intervention state instead of spawning infinite new requests.

**Irreducible edge case:** if a provider supports neither idempotency keys nor status lookups, the application cannot distinguish "not charged" from "charged but response lost". In that case, you need reconciliation, compensating actions where appropriate, or an explicit risk-acceptance policy.

## 9. Outbox and reliable checkpoints when flows must survive restarts

Routing slip carries path/index inside the **current message**; it does not durably persist the entire step history to a database. If progress must survive application restarts, you can build **`workflow_instance`**, **`routing_step_execution`**, and **`outbox`** tables.

Example schema:

~~~sql
CREATE TABLE workflow_instance (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    flow_version VARCHAR(32) NOT NULL,
    state VARCHAR(24) NOT NULL,
    next_logical_step VARCHAR(80),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE workflow_outbox (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    target_step VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivered_at TIMESTAMPTZ,
    UNIQUE (tenant_id, event_id, target_step)
);
~~~

Suppose `reserveInventory` runs in the same database:

~~~mermaid
flowchart LR
    A["Reserve inventory"] --> TX["DB transaction"]
    TX --> E["Deduct stock"]
    TX --> ST["Step COMPLETED"]
    TX --> OB["Outbox: charge-payment"]
    OB --> D["Dispatcher"]
    D --> C["Charge consumer<br/>same idempotency key"]
~~~

When reserve completes:

- Deduct inventory, mark reserve completed, and write **the outbox entry for the charge step** inside the **same transaction**.
- The dispatcher reads the outbox and sends a message to the charge leg; if dispatched repeatedly, the charge consumer uses the **same idempotency key**.
- A durable broker/queue can support redelivery if a consumer dies; acks must align with the commit boundary.
- The workflow can **rebuild the routing slip or resume from `next_logical_step`** using persisted state rather than relying solely on the received header/index.

**This example is just one option:** Spring Integration does not automatically provide a transactional outbox/checkpoint for every routing slip. You must implement/configure the corresponding services, stores, adapters, retries, and monitoring.

### 9.1. Writing next step too early skips side effects

Wrong:

~~~text
UPDATE workflow_instance SET next_logical_step='notify-customer'
CALL paymentProvider.charge(...)
~~~

If a crash happens before charge, resuming at notify will **skip collecting payment**. Instead, progress state must reflect whether **charge was confirmed**. For external APIs, an UNKNOWN state and a reconciliation step may be needed before advancing to notify.

### 9.2. Writing next step too late can repeat effects

Wrong in the opposite direction:

~~~text
CALL paymentProvider.charge(...)  // succeeded
PROCESS CRASH
UPDATE workflow_instance SET next_logical_step='notify-customer'
~~~

After restart, state still points at charge, so the worker calls it again. **An idempotency key at the payment provider** or reconciliation keeps the effect once-only despite repeated attempts.

### 9.3. Durability of the routingSlip header

Spring Integration documentation warns that when a routing slip crosses **JMS/AMQP, a persistent `MessageStore`, or JVM boundaries**, you should avoid using **inline SpEL expressions** as path entries in a way that causes the framework to store a **non-Serializable `ExpressionEvaluatingRoutingSlipRouteStrategy`** in the header.

Measures:

- Use **registered `RoutingSlipRouteStrategy` bean names** instead of inline expressions embedded in distributed messages.
- Use stable channel names with controlled mappings/strategies inside each application.
- Test serialization, header mappers, and version compatibility across real adapters/brokers.
- When multiple services do not share the same topology or channel names, pass **portable workflow state/payloads** rather than sending internal routing-slip structures across services.

Even if a header is serializable, that **does not** guarantee all steps finished, nor does it replace idempotency.

## 10. Spring Integration Idempotent Receiver at each leg

Spring Integration provides **`IdempotentReceiverInterceptor`** and **`MetadataStoreSelector`** to support the Idempotent Receiver pattern. This is an **endpoint-level** mechanism, not a default option of routing slip.

`MetadataStoreSelector` can use a **`ConcurrentMetadataStore`** to claim keys, for example:

~~~java
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;

// store must be provided by the application with appropriate durability.
MetadataStoreSelector selector = new MetadataStoreSelector(
        (Message<?> message) -> {
            ShipmentRequested event =
                    (ShipmentRequested) message.getPayload();
            return event.tenantId()
                    + ":" + event.eventId()
                    + ":reserve-inventory";
        },
        store);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);

// Attach advice to the reserveInventory endpoint per project configuration.
// When duplicates must be dropped, configure discardChannel
// or an explicit rejection policy rather than merely creating the advice.
~~~

This snippet illustrates the mechanism; the store and advice must be declared and attached to the endpoint using the API matching your Spring Integration version.

### 10.1. Default behavior does not necessarily block duplicates

According to the documentation, if the selector rejects a message, **`IdempotentReceiverInterceptor`** may attach a **`duplicateMessage=true`** header and still pass the message to the handler, unless **`discardChannel`** or **`throwExceptionOnRejection`** is configured.

Therefore, merely creating the interceptor does not mean side effects will be skipped automatically. If the leg produces a reply so the routing slip continues, **completely discarding duplicates before the handler** also needs careful thought: it could cause the flow to **halt at the already processed leg**, rather than skipping the side effect and **continuing to unfinished legs**.

For a routing slip that may replay from ingress, a sensible design for a COMPLETED step is usually:

~~~java
ShipmentRequested processReserve(ShipmentRequested event) {
    // reserveOnce recognizes completed state and skips duplicate effect.
    inventoryReservation.reserveOnce(event);

    // Even if completed previously, still return the message
    // so the routing slip proceeds to the next leg.
    return event;
}
~~~

**Key point:** avoid deducting stock twice **while still emitting a reply** so missing `charge` or `notify` legs can proceed. Setting `discardChannel=nullChannel` on `reserve` could cause a replay from the start to stop before `charge`.

### 10.2. Claiming keys before effects and failing after claim

If `MetadataStoreSelector` claims a key before the handler calls an external service, an exception after the claim can cause retries to be flagged as duplicates. That creates a risk of **losing the task**, not just duplicating it.

Solutions depend on the side-effect source:

- **DB in the same transaction:** persist idempotency record and effect atomically.
- **External API supporting keys:** reuse the same key on every attempt; query when outcome is unknown.
- **Multi-step workflow:** persist step status and skip effects only when status confirms COMPLETED.
- **Distributed store:** verify atomicity, TTL, concurrency, and lock/claim recovery.

### 10.3. Avoid global deduplication without per-step state

A gate right before the header enricher that says "if `eventId` was seen, drop it" can block replays completely even when `reserve` succeeded and `charge` never ran. Unless every sub-task has already been **durably handed off** to each recipient/step or an independent resume mechanism exists, never treat global dedup as a complete solution.

## 11. Retry, error channel, and ordering control

### 11.1. Synchronous vs. asynchronous errors

| Context | Typical error behavior | What to do |
| --- | --- | --- |
| DirectChannel, sync handler | Exception may propagate back to caller | Define transaction rollback and retry placement |
| ExecutorChannel | Handler runs after executor accepts task | Dedicated error handler/flow and bounded executor |
| QueueChannel + poller | Error arises when consumer polls/handles | Retry/backoff, step status, DLQ |
| Broker/JMS/AMQP | Ack/redelivery per adapter and broker | Commit message only when effect is persisted |
| Request/reply Gateway | `replyChannel` routes response when slip finishes | Timeout/error replies need explicit contracts |

If a routing slip has **reserve** and **charge** on synchronous `DirectChannel`s, an exception in `charge` can make the caller think the entire process failed. That **does not prove** `reserve` rolled back, especially if `reserve` committed its own DB transaction or triggered an external effect.

### 11.2. Retries must be bounded and error-aware

| Error type | Safe to retry immediately? | Priority action |
| --- | --- | --- |
| Invalid input | Usually no | Reject before any side effect |
| Missing channel/bean in slip | No, until topology is fixed | Fail fast, fix configuration |
| Out of stock | Business-dependent | Business rejection or separate restock workflow |
| DB deadlock/timeout | Possible | Retry with backoff using unique key |
| Payment provider timeout | Only safe with idempotency/reconciliation | Keep UNKNOWN status, use same key |
| Email provider 429 | Possible | Backoff, rate limit, same idempotency key if supported |
| Strategy looping infinitely | Never retry blindly | Cap hops/iterations, alert |

Never allow unconstrained retries to form an unbounded **`RoutingSlipRouteStrategy` → same channel** loop. If a workflow intentionally iterates per item, define termination conditions and maximum counts.

### 11.3. Correlation is not idempotency

When a routing slip is combined with **Splitter/Aggregator**, `correlationId`/`sequenceSize` help manage child message groups. They do not automatically prevent a side effect from re-executing.

For example:

~~~text
eventId = evt-301
correlationId = shipment-301
stepId = reserve-inventory
itemId = SKU-9
~~~

The idempotency key can be `tenantId + eventId + stepId + itemId`. `correlationId` **links parts of the same shipment** and should not replace `eventId` when a shipment emits multiple distinct valid events and tasks.

If a strategy inspects the reply to choose the next leg, guard the reply type. Spring Integration documentation notes `reply` may be a `Message`, builder, or domain object depending on the handler; never assume the strategy can always read `reply.payload` and `reply.headers` in every case.

## 12. Integration test: replay re-runs the path without automatic idempotency

To understand the real mechanics, a test should verify:

1. Routing slip routes messages to the right channels in order during a single synchronous send.
2. Sending the **same event** into ingress a second time causes handlers to execute again.
3. A failure at the `charge` leg stops the run before reaching `notify`.
4. Resending from ingress invokes earlier legs again unless they enforce their own idempotency.

The following example runs with **JUnit 5, spring-test, and Spring Integration Java DSL**. Handlers only record step names, with no real side effects.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RoutingSlipReplayTest.Config.class)
class RoutingSlipReplayTest {

    static final class Probe {
        final List<String> visits = new CopyOnWriteArrayList<>();
        volatile boolean failCharge;
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        MessageChannel ingress() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel verifyStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel inventoryStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel paymentStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel notificationStep() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow slipIngress() {
            return IntegrationFlow.from("ingress")
                    .enrichHeaders(h -> h.routingSlip(true,
                            "verifyStep",
                            "inventoryStep",
                            "paymentStep",
                            "notificationStep"))
                    .get();
        }

        @Bean
        IntegrationFlow verifyFlow(Probe probe) {
            return IntegrationFlow.from("verifyStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("verify");
                        return event; // Produce reply to fetch next entry.
                    })
                    .get();
        }

        @Bean
        IntegrationFlow inventoryFlow(Probe probe) {
            return IntegrationFlow.from("inventoryStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("inventory");
                        return event;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow paymentFlow(Probe probe) {
            return IntegrationFlow.from("paymentStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("payment");
                        if (probe.failCharge) {
                            throw new IllegalStateException("Payment timeout");
                        }
                        return event;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow notificationFlow(Probe probe) {
            return IntegrationFlow.from("notificationStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("notification");
                        return null; // End one-way flow.
                    })
                    .get();
        }
    }

    @Autowired
    @Qualifier("ingress")
    MessageChannel input;

    @Autowired
    Probe probe;

    @BeforeEach
    void clear() {
        probe.visits.clear();
        probe.failCharge = false;
    }

    private ShipmentRequested event() {
        return new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));
    }

    @Test
    void aSingleSendVisitsEachStepInOrder() {
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(
                List.of("verify", "inventory", "payment", "notification"),
                probe.visits);
    }

    @Test
    void replayingAtIngressRepeatsHandlersWithoutDedup() {
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(List.of(
                "verify", "inventory", "payment", "notification",
                "verify", "inventory", "payment", "notification"),
                probe.visits);
    }

    @Test
    void aFailedStepStopsThisAttemptButReplayStartsAgain() {
        probe.failCharge = true;

        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload(event()).build()));
        assertEquals(
                List.of("verify", "inventory", "payment"),
                probe.visits);

        probe.failCharge = false;
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(List.of(
                "verify", "inventory", "payment",
                "verify", "inventory", "payment", "notification"),
                probe.visits);
    }
}
~~~

The tests use synchronous `DirectChannel`s, so order can be observed immediately after `send()`. If switching to `ExecutorChannel`, `QueueChannel`, or a broker adapter, do not rely on synchronous test assumptions to infer completion order; use `CountDownLatch`, timeouts, or appropriate integration test tools.

**Attention:** the last test demonstrates that earlier legs get invoked again; it intentionally **does not** attach idempotency to the handlers. In a real system, `inventory.reserveOnce` skips an already COMPLETED side effect yet still **returns a reply** so the slip proceeds to `charge` and `notify`.

## 13. Testing idempotency under crashes

An independent test layer must protect effects. Never assert only that a service was invoked once on the happy path.

### 13.1. Required failure matrix

| Failure timing | Observable state | Desired retry outcome |
| --- | --- | --- |
| Before validate | No effect yet | Re-runs normally |
| After validate, before reserve | No effect yet | Re-validates, reserves once |
| Reserve DB fails before commit | Transaction rolls back | Subsequent reserve succeeds |
| Reserve DB commits, before moving to charge | Reserve COMPLETED | Skips reserve effect, continues to charge |
| Payment has not received request | Not charged | Retries with same idempotency key |
| Payment collected, response lost | UNKNOWN | Queries or idempotently retries; no double charge |
| Notified, before ack | Email may have been sent | Provider idempotency/reconciliation |
| Retry from snapshot with old index | Earlier legs may be invoked | Completed effects do not repeat |
| Retry from snapshot with premature new index | Effects may be skipped | Verify step state; never trust index alone |
| Two workers claim same step concurrently | Race condition | One commits effect; other does not duplicate |
| Application restart | In-memory metadata lost | Durable store restores accurate state |
| Flow version changes | Different path and step mapping | Clear migration/replay policy; no unintended effect repeats |

### 13.2. Unit test for per-step keys

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class StepKeyTest {
    static String key(ShipmentRequested e, String step) {
        return e.tenantId() + ":" + e.eventId() + ":" + step;
    }

    @Test
    void aRetryKeepsTheSameKeyButStepsHaveDifferentKeys() {
        ShipmentRequested original = new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));
        ShipmentRequested replayed = new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));

        assertEquals(
                key(original, "charge-payment"),
                key(replayed, "charge-payment"));
        assertNotEquals(
                key(original, "reserve-inventory"),
                key(replayed, "charge-payment"));
    }
}
~~~

This test checks **only the identity contract**. To test real deduplication, use a database with unique constraints or a real `MetadataStore` and exercise concurrent + rollback cases.

### 13.3. Testing DB transactions

An integration test with PostgreSQL/Testcontainers or an appropriate test DB should verify:

1. Initialize stock for `tenant-A`, `SKU-9` to 10.
2. Send `evt-301` to `reserveInventory`; wait for commit.
3. Resend `evt-301` with the same tenant/event/step; stock must remain 8, not drop to 6.
4. Throw an exception **after inserting the step claim but before deducting stock**; verify the transaction rolls back.
5. Retrying after rollback must still be able to reserve successfully.
6. Have two workers process the same key concurrently; verify only one transaction commits the effect.

Also verify invalid-data policies: zero or negative quantity must be rejected **before** inserting a claim; never let a client select a different `tenantId` by tampering with headers/payload.

### 13.4. Testing payment with lost response

A fake `PaymentProviderPort` should simulate: **record the charge successfully, then throw a network error to the caller**. Retrying with the same idempotency key must return the original charge result without creating a second charge. If the provider does not support keys, the test must represent the UNKNOWN state and reconciliation path rather than falsely declaring the charge failed.

### 13.5. Testing replay from checkpoint

Set up a workflow with state:

~~~text
evt-301:
  validate = COMPLETED
  reserve-inventory = COMPLETED
  charge-payment = UNKNOWN
  notify-customer = PENDING
~~~

During recovery:

- Do not deduct inventory again.
- Do not let `notify` run before `charge` is confirmed succeeded.
- Reconcile `charge` using the same idempotency key.
- Only after `charge` succeeds, mark `charge` COMPLETED and proceed to `notify`.

If a message is rebuilt with a routing slip path from the start, `validate`/`reserve` services must be **safe to re-run**. If the system resumes directly at `charge`, orchestration must verify prerequisites from durable state.

## 14. Per-leg observability and detecting duplicates

In a multi-step system, logging a successful message send is not enough. Observe both **routing** and **effect status**:

| Metric/log | Meaning |
| --- | --- |
| `workflow_started_total` | Count of logical workflows started |
| `workflow_replay_attempts_total` | Count of event replays |
| `step_attempts_total{step}` | Invocations per leg |
| `step_completed_total{step}` | Effects confirmed completed |
| `step_idempotent_skips_total{step}` | Attempts that skipped already completed effects |
| `step_unknown_total{step}` | Effects with unknown outcome |
| `step_retry_total{step}` | Retry counts |
| `workflow_outbox_pending_total` | Tasks awaiting dispatch |
| `workflow_dead_letter_total` | Tasks requiring manual intervention |
| `workflow_replay_age_seconds` | Time an event waits for recovery |

Never use high-cardinality `eventId`, `orderId`, or `tenantId` as **metric labels**, as cardinality grows without bound. Use access-controlled logs/tracing with sensitive fields masked to look up by `eventId`. Headers such as `traceId`, `businessCorrelationId`, and `routingSlip` help follow paths, but do not by themselves guarantee once-only execution.

### Three questions to answer during investigations

1. **Where did an event go?** Determine `flowVersion`, path, and current leg from telemetry—do not rely only on a stale header.
2. **Which legs truly completed?** Cross-check step status, transaction commits, and provider idempotency responses.
3. **Where can retry safely resume?** Pick checkpoint resume or ingress replay based on step idempotency.

## 15. Common mistakes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Treating `routingSlipIndex` as proof a step committed | Skipped or duplicated effects on crash | Persist step status durably; confirm effects |
| Using `MessageHeaders.ID` as a dedup key | Retries across adapters receive new IDs | Use a stable logical `eventId` |
| Global flow dedup at ingress dropping replays | Cannot recover unfinished downstream branches | Dedup per step; resume with state |
| Using `eventId + stepId` for strategies intentionally iterating items | Mistakenly drops legitimate item runs | Include true itemId/iteration identity |
| Writing claim before effect without rollback on failure | Retries get blocked even though effect failed | Transaction or status/lease/recovery |
| Assuming routing slip creates durable checkpoints | Crashes lose in-memory progress | DB state, outbox/broker, and replay policy |
| Returning `null` from an intermediate handler | Routing slip stops before subsequent legs | Return a reply whenever continuation is needed |
| Configuring explicit `outputChannel` while expecting slip to decide | Message ignores desired slip path | Design endpoints and test wiring |
| Retrying charge with a new idempotency key | Risks double charging | Reuse key for the same logical effect |
| Retrying whole slip when notification fails | Reserve/charge get called again | Retry failing branch; idempotent services |
| Using inline SpEL slips across distributed brokers | Risk of serialization errors | Strategy bean names, portable state |
| Letting clients supply `routingSlip` header directly | Can route to unauthorized channels | Build path at trust boundary with allowlists |
| Blindly putting `flowVersion` into every effect key | Deploying new version repeats old effects | Keep `logicalStepId` stable; explicit migration |
| Testing only single-run happy path | Misses duplicates and crash windows | Test replays, concurrency, restarts, unknown state |

## 16. Practice exercise: building a replayable routing slip

A sales system processes **`OrderAccepted(eventId, tenantId, orderId, totalVnd)`** along the path:

~~~mermaid
flowchart LR
    I["Ingress"] --> V["Validate"]
    V --> S["Reserve stock"]
    S --> P["Capture payment"]
    P --> A["Create shipment"]
    A --> N["Notify customer"]
~~~

**Requirements**

1. Events carry a stable `eventId` across redeliveries and a `tenantId` from an authenticated source.
2. Validate can re-run without creating side effects.
3. Reserve stock never deducts inventory a second time when the same event replays.
4. Payment provider receives a stable idempotency key; timeouts may yield UNKNOWN status requiring reconciliation.
5. Create shipment has a unique business operation or target-service idempotency.
6. Notify runs only after mandatory legs succeed; replays never send duplicate notifications.
7. Workflow can restart and resume from durable state.

**Implementation steps**

1. Define the `OrderAccepted` record and business ports; validate mandatory fields.
2. Build the routing slip via `HeaderEnricherSpec.routingSlip` with allowlisted channel names.
3. Ensure intermediate handlers **return a reply** and omit `outputChannel` settings that bypass the slip.
4. Create a `step_execution` table with unique key `tenantId + eventId + logicalStepId`.
5. For reserve stock, use a transaction coupling status persistence with inventory updates.
6. For capture payment, simulate a lost response after the provider processes it; retry with the same key.
7. Persist leg states and decide between ingress replay and checkpoint resumption.
8. Write tests for single send, repeated send, mid-flow exceptions, restarts, and two concurrent workers.
9. Add `step_attempts`, `step_idempotent_skips`, `step_unknown`, and `workflow_replay_attempts` metrics.
10. Propose how to ship the flow across a broker without serializing inline `BeanFactory`-bound `RoutingSlipRouteStrategy` objects.

### Self-check questions

1. Under what conditions on replies and `outputChannel` is the routing slip consulted?
2. Does `routingSlipIndex` prove `charge-payment` succeeded?
3. Why can a failure after `reserve` cause an ingress replay to deduct stock twice?
4. Why can filtering solely by `eventId` across the whole flow drop an unfinished `charge` leg?
5. Is a strategy returning the same channel multiple times always a duplicate?
6. Should an idempotency key change or stay the same across retries?
7. Does a payment timeout mean the provider did not collect payment?
8. When can an idempotency record and effect be written in the same transaction?
9. Why can a bare `MetadataStoreSelector` lose retry opportunities after errors?
10. What must be done if an event needs replaying after upgrading the routing slip version?
11. Why are inline SpEL strategies risky when messages cross a broker?
12. If a duplicate is discarded before `reserve`, how will the `charge` leg execute?

## 17. Pre-operation checklist

- Routing slip paths are defined using **allowlisted channels/strategies**, never taken directly from untrusted data.
- Intermediate endpoints produce replies, and explicit `outputChannel` is used only when intentionally bypassing the slip.
- `eventId` and `tenantId` come from authenticated origins and stay stable across retries/redeliveries.
- Every leg has a `logicalStepId` and an idempotency key scoped to its effect.
- Legs legitimately repeated per item/iteration have distinct keys so they are not wrongly deduplicated.
- Never use slip index or `MessageHeaders.ID` as a business commit marker.
- For DB effects, unique constraints and transactions ensure claim and effect commit/roll back atomically.
- For external effects, idempotency keys, reconciliation, or valid UNKNOWN states exist.
- Already completed services still **emit replies** when replays need subsequent legs to proceed.
- Checkpoints/outbox/inbox or durable handoff exist if workflows must survive restarts.
- Retries are bounded with backoff, error channels/DLQs, and unrecoverable-error policies.
- Flow versions are managed without changing effect identities when upgrading paths.
- `routingSlip` headers crossing brokers have been tested for serialization and environment compatibility.
- Tests cover ingress replay, resume, partial failure, concurrency, post-effect timeouts, and restarts.

**Conclusion:** Routing slip tells you **the next path**, whereas idempotency tells you **whether a business effect already ran and whether repeating it is allowed**. When a message re-runs a routing slip, each leg must have its own identity, completion status, and recovery policy. Only by combining routing slips with transactions, idempotent consumers, outboxes, or reconciliation at the right system boundaries can you avoid duplicate side effects without dropping unfinished steps.

## References

- [Spring Integration Reference — Routing Slip](https://docs.spring.io/spring-integration/reference/router/routing-slip.html): path/index mechanics, `AbstractMessageProducingHandler`, strategies, and `replyChannel`.
- [Spring Integration API — HeaderEnricherSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/HeaderEnricherSpec.html): `routingSlip` path and header overwrite option.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): `IdempotentReceiverInterceptor` and duplicate handling.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): `ConcurrentMetadataStore`, in-memory and persistent stores.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `IntegrationFlow`, Header Enricher, Service Activator.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): sync/async channels, `QueueChannel`, and error handling.
