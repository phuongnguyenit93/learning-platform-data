# Correlation ID, business keys, and routing data

## 1. Why are these three identifiers important in message contracts?

In asynchronous communication systems, a producer emits a message and continues working without necessarily waiting for the consumer to finish processing it. Spring Cloud Contract (**SCC**) lets you describe HTTP or messaging behavior using **Groovy/YAML DSL**, generate producer-side tests, create stubs so consumers can test via **Stub Runner**, and integrate with CI to catch incompatible changes.

When a message has a valid JSON payload yet lacks metadata or goes to the wrong destination, the system can still fail:

- The consumer cannot correlate outcomes back to the original request due to a missing **correlation ID**.
- Two events for the same product land in different partitions due to inconsistent **business keys**, making ordering unpredictable.
- An event is emitted with the right body but to a **topic, exchange, or routing key** the consumer never subscribed to.
- The consumer fails to deduplicate messages because **event ID** was confused with correlation ID.
- Contract tests assert only the payload, ignoring headers and destinations, so the pipeline stays green even though real communication is broken.

This lesson focuses on **correlation IDs, business keys, and routing data** in the *Message contracts* chapter of the `SPRING_CLOUD_CONTRACT` module. The goal is not merely naming fields, but determining semantics, placement, verification methods, and Spring Cloud Contract limits when paired with Kafka, RabbitMQ, or Spring Cloud Stream.

### After this lesson, you will be able to

1. Distinguish `correlationId`, `eventId`, `businessKey`, message keys, partition keys, topics, and routing keys.
2. Decide which metadata belongs in the payload, headers, or transport configuration.
3. Write Groovy/YAML message contracts with destination, headers, and body.
4. Wire generated producer tests to **real message-emitting flows** instead of fabricating fake events inside the test base.
5. Test consumers with Stub Runner and know which tests require a real/test broker.
6. Design event correlation, idempotency, partitioning, ordering, retries, and schema evolution.
7. Build a CI checklist that catches incompatible message changes.

## 2. Scenario: an inventory update request

Suppose **Inventory Service** is the producer, emitting `InventoryChanged` events. **Checkout Service** and **Fulfillment Service** are two consumers:

~~~mermaid
flowchart LR
    A["Inventory update API"] --> B["Inventory Service"]
    B --> C["inventory.events"]
    C --> D["Checkout Service"]
    C --> E["Fulfillment Service"]
    B --> F["Contract Verifier"]
    F --> G["Generated producer tests"]
    C --> H["Broker or test binder"]
~~~

An inventory update request carries this context:

~~~text
tenantId:       tenant-a
sku:            SKU-123
newQuantity:    12
correlationId:  corr-1001
~~~

Producer emits a sample message:

~~~json
{
  "eventId": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "InventoryChanged",
  "tenantId": "tenant-a",
  "sku": "SKU-123",
  "available": true,
  "quantity": 12,
  "aggregateVersion": 7
}
~~~

Illustrative **application message headers**:

~~~text
correlationId: corr-1001
businessKey: tenant-a|SKU-123
eventType: InventoryChanged
schemaVersion: 1
~~~

And routing information:

~~~text
Logical destination: inventory.events
Kafka message key (when using Kafka): tenant-a|SKU-123
~~~

These are **conventions of the example application**, not defaults assigned automatically by SCC or the broker. Specifically, merely adding a `businessKey` header **does not make Kafka use it as the record key**; the adapter/binder must explicitly map it.

## 3. Table distinguishing identifier types

| Value | Question it answers | Scope and stability |
|---|---|---|
| **Correlation ID** | “Which messages belong to the same request/workflow?” | Can be reused across **multiple distinct events** in the same workflow |
| **Event ID / Message ID** | “Which logical event is this?” | Distinguishes one event from another; typically **unchanged when redelivering the same event** |
| **Business key / Aggregate key** | “Which business entity is this event about?” | Stable for the same aggregate, e.g., tenant + SKU |
| **Kafka record key / Partition key** | “Which value does the broker use to choose a partition?” | Depends on transport/partitioner; may use the business key |
| **Destination / Topic / Queue / Exchange** | “Where is the message sent?” | Typically part of transport config or contract |
| **RabbitMQ routing key** | “Which routing rule does the exchange apply?” | Depends on exchange type and bindings; **different from Kafka key** |
| **Trace ID / Span ID** | “Which distributed execution trace is being observed?” | Managed by tracing systems; not inherently equal to correlation ID |
| **Causation ID** | “Which event directly caused this event?” | Usually the ID of the parent event/command, aiding causal tracing |

The three IDs relate in a scenario as follows:

~~~text
Correlation ID: corr-1001
  ├── Event ID: evt-a1   businessKey: tenant-a|SKU-123
  │      InventoryChanged(quantity=12)
  ├── Event ID: evt-a2   businessKey: tenant-a|SKU-123
  │      InventoryReserved(quantity=2)
  └── Event ID: evt-b1   businessKey: tenant-a|ORDER-789
         CheckoutConfirmed
~~~

All three events share the **same correlation ID**, yet have **different event IDs** and may carry **different business keys**. Always using correlation ID as the partition key can scatter events for the same product across workflows; using business key as event ID prevents consumers from distinguishing two separate updates to the same product.

## 4. Correlation ID: linking a processing chain

A correlation ID links communication steps to a single request or cross-service workflow. For example, Checkout's HTTP request:

~~~http
POST /api/inventory/adjust HTTP/1.1
Content-Type: application/json
X-Correlation-Id: corr-1001

{"tenantId":"tenant-a","sku":"SKU-123","quantity":12}
~~~

Inventory Service receives the request, processes it, and emits `InventoryChanged` with the application header:

~~~text
correlationId: corr-1001
~~~

Consumers can include that correlation ID in logs, controlled metrics, or downstream events to investigate the end-to-end flow.

### Implementation rules to lock down

- **ID source:** accept from a trusted ingress or generate a new one if missing. External values must be **validated** and length-bounded, never trusted unconditionally.
- **Propagation boundary:** an HTTP header named `X-Correlation-Id` may map to application message header `correlationId`; code must perform that mapping explicitly.
- **Never use as an event identifier:** distinct events within one request can share a correlation ID.
- **Do not assume it equals a tracing ID:** `traceparent` in W3C Trace Context has its own structure and semantics. They can be linked, not arbitrarily renamed to each other.
- **No sensitive data:** avoid embedding emails, phone numbers, tokens, session IDs, or personal data in correlation values.
- **Missing-ID policy:** keep processing, reject, dead-letter, or generate a new ID? Producer and consumer must agree on the policy.

For a long-running asynchronous workflow, a correlation ID may outlive a single HTTP request. Test its propagation across multiple steps, not only at the initial endpoint.

## 5. Event ID: identifying events to prevent duplicate processing

Brokers commonly provide **at-least-once delivery** in standard configurations: the same logical event may be redelivered on retries, rebalances, or when a consumer finishes processing before recording an acknowledgement.

Example of two deliveries:

~~~text
delivery #1: eventId=550e8400-e29b-41d4-a716-446655440000
delivery #2: eventId=550e8400-e29b-41d4-a716-446655440000
~~~

Consumers must recognize both deliveries as **the same event** when business rules require idempotent processing. If a producer generates a brand-new event ID on every retry of **the same event**, event-ID-based deduplication breaks down.

Compare:

| Case | Event ID | Correlation ID | Business key |
|---|---|---|---|
| Redelivery of same event | **Unchanged** | Unchanged | Unchanged |
| Two events updating the same SKU | **Different** | May be same or different | May be same |
| Event updating another SKU in same workflow | **Different** | May be same | **Different** |

Consumers often record processed IDs using `eventId` or `source + eventId` per system convention. That is part of **idempotency** design, not something SCC implements automatically.

Never substitute a Kafka offset for an event ID: offsets only have meaning within one specific partition and are not durable business identifiers if re-published across brokers or topics.

## 6. Business key: which entity is changing?

In the inventory example, the aggregate is identified by:

~~~text
tenantId = tenant-a
sku      = SKU-123

businessKey = tenant-a|SKU-123
~~~

In multi-tenant applications, using only `SKU-123` risks **collisions** across tenants. When joining keys with `|`, define escaping/normalization rules or use a structured key representation so raw data containing the delimiter cannot collide.

A business key should be:

- **Stable** across events for the same aggregate.
- **Free of secrets**; since keys often appear in logs/headers/broker metadata, consider PII and access control.
- **Normalized consistently**: casing, Unicode, leading/trailing whitespace, ID format.
- **Aligned with grouping/ordering needs**: tenant + SKU for inventory aggregates; tenant + order ID for orders.
- **Not silently altered** during schema upgrades or data refactors.

When consumers need per-SKU change ordering, the business key is a natural candidate for the **Kafka record key**. Whether it actually determines partitioning depends on the adapter/binder implementation and broker configuration.

## 7. Routing data: distinguishing destination from key

In Spring Cloud Contract message DSL, `sentTo(...)` usually specifies the output **destination** observed by messaging tests/verifier:

~~~groovy
outputMessage {
    sentTo('inventory.events')
}
~~~

Yet a real system can involve multiple routing layers:

| Layer | Example | Responsibility |
|---|---|---|
| Application intent | `InventoryChanged` | Identifies the event type |
| Logical destination | `inventory.events` | Where the producer publishes events per contract |
| Spring Cloud Stream binding | `inventoryChanged-out-0` | Binding name between application and binder |
| Kafka topic | `inventory.events` | Real broker topic |
| Kafka record key | `tenant-a|SKU-123` | Input to partitioning logic |
| RabbitMQ exchange | `inventory.exchange` | Broker message intake point |
| RabbitMQ routing key | `inventory.changed.tenant-a` | Used for exchange routing/bindings |
| Consumer group/queue | `checkout-consumer` | Consumer group receiving messages per topology |

Not every system uses all of these layers. They are **not synonymous**; changing a topic name or routing key can prevent consumers from receiving events even if the JSON payload is unchanged.

**Important:** a contract checking `sentTo('inventory.events')` may observe destinations **at the test binder's abstraction level**, without necessarily verifying real Kafka topics, Rabbit exchange bindings, or Kafka partition keys. If those details are operational commitments, add adapter/broker tests.

## 8. Kafka key vs. RabbitMQ routing key

### 8.1. With Kafka

In Kafka, every record is sent to a **topic**. The record key is typically used by the partitioner to pick a **partition**. On a multi-partition topic, messages sharing a key generally land in the same partition under a stable partitioner/configuration.

This helps consumers process changes to the **same aggregate** in partition log order, subject to known limits:

- Kafka **does not guarantee global ordering** across partitions.
- Ordering within a partition still depends on publish/retry policies and parallel consumer handling.
- Changing the **partition count**, partitioner, or key serialization alters key→partition mapping.
- A `businessKey` field in JSON or a custom header **does not automatically** become the Kafka record key.
- Consumers must inspect **key bytes/format** if grouping or routing by key, not only the payload.

### 8.2. With RabbitMQ

Messages are usually published to an **exchange** with a **routing key**; the exchange uses its type and bindings to route to queues. For example, a topic exchange might use a key like:

~~~text
inventory.changed.tenant-a
~~~

That is a **routing pattern**, not a Kafka partition key. Never transfer Kafka partition-ordering assumptions onto RabbitMQ routing keys. RabbitMQ also has its own queue, consumer acknowledgement, and retry/dead-letter semantics.

### 8.3. Practical takeaway

If the goal is **keeping the same aggregate on the same partition**, specify the business key, Kafka key mapping, and test against a real broker/adapter. If the goal is **selecting a queue by event type or tenant**, test actual exchanges, routing keys, and queue bindings. Spring Cloud Contract protects only what the contract and test environment genuinely observe.

## 9. Groovy DSL contract for a message with metadata

Suppose the producer emits a message after the application service updates inventory. Place the contract in the configured producer path, e.g.:

~~~text
src/test/resources/contracts/inventory/inventory-changed.groovy
~~~

Contents:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Emit InventoryChanged with correlation and business key'
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')

        headers {
            header('contentType', 'application/json')
            header('correlationId', 'corr-1001')
            header('businessKey', 'tenant-a|SKU-123')
            header('eventType', 'InventoryChanged')
            header('schemaVersion', '1')
        }

        body(
            eventId: '550e8400-e29b-41d4-a716-446655440000',
            eventType: 'InventoryChanged',
            tenantId: 'tenant-a',
            sku: 'SKU-123',
            available: true,
            quantity: 12,
            aggregateVersion: 7
        )

        bodyMatchers {
            jsonPath('$.eventId', byRegex(uuid()))
        }
    }
}
~~~

Key components:

1. `label` identifies the contract; in certain Stub Runner messaging flows, consumers can trigger stubs by label.
2. `input.triggeredBy` names the **method in the producer test base** that triggers message emission. This is not a consumer method.
3. `outputMessage.sentTo` describes the expected logical destination.
4. `outputMessage.headers` describes metadata the producer must place on the message at the layer observed by the test verifier.
5. `outputMessage.body` describes the sample JSON payload consumers must understand.
6. `bodyMatchers` allows `eventId` to vary while enforcing UUID format instead of forcing the producer to emit the exact sample literal every time.

**Warning:** never turn `triggerInventoryChanged()` into a method that manually emits a sample message. The trigger method must invoke the **production business flow** that generates the real message. Other dynamic fields such as timestamps or IDs may need matchers compatible with your SCC version.

Verify `uuid()` syntax, `bodyMatchers` usage for messages, and header/transport observability against your chosen Spring Cloud Contract version and confirm via **real generated tests**.

## 10. The same idea in YAML DSL

A conceptually equivalent `inventory-changed.yml`:

~~~yaml
description: Emit InventoryChanged with correlation and business key
label: inventoryChanged

input:
  triggeredBy: triggerInventoryChanged()

outputMessage:
  sentTo: inventory.events
  headers:
    contentType: application/json
    correlationId: corr-1001
    businessKey: 'tenant-a|SKU-123'
    eventType: InventoryChanged
    schemaVersion: '1'
  body:
    eventId: 550e8400-e29b-41d4-a716-446655440000
    eventType: InventoryChanged
    tenantId: tenant-a
    sku: SKU-123
    available: true
    quantity: 12
    aggregateVersion: 7
  matchers:
    body:
      - path: $.eventId
        type: by_regex
        predefined: uuid
~~~

Notes on YAML:

- `input.triggeredBy` and `outputMessage` belong to **SCC's schema**, not standard YAML parser features.
- `businessKey` is quoted because of the application-chosen delimiter; if keys contain `:` or text YAML might misread, quoting is essential.
- `schemaVersion: '1'` is a **string** in this example; changing it to number `1` changes metadata typing and may affect consumers.
- `aggregateVersion: 7` is a **JSON number**, distinguishing aggregate versions in the payload.
- The body matcher targets the dynamic event ID; fields like `sku`, `quantity`, and headers have fixed expectations in this sample scenario.

The Groovy and YAML contracts above are **two alternatives**—do not keep both in the same project if they describe the same scenario. Test base, messaging adapter, and plugin must be configured appropriately so contracts compile into real tests.

## 11. Distinguishing fields across payload, headers, and transport envelope

An event can be divided into three layers:

~~~text
TRANSPORT ENVELOPE
  destination/topic: inventory.events
  record key:       tenant-a|SKU-123
  partition:        determined by broker/partitioner

APPLICATION HEADERS
  correlationId:    corr-1001
  businessKey:      tenant-a|SKU-123
  schemaVersion:    1
  eventType:        InventoryChanged

BODY (JSON)
  eventId:          550e8400-e29b-41d4-a716-446655440000
  tenantId:         tenant-a
  sku:              SKU-123
  available:        true
  quantity:         12
  aggregateVersion: 7
~~~

| Placement | Pros | Considerations |
|---|---|---|
| **Payload** | Easy to serialize, store, replay, and apply JSON Schema | Consumers must parse body to inspect metadata |
| **Application headers** | Fast to read before parsing body; useful for tracing/routing | Header propagation and converters/binders can vary |
| **Transport key/envelope** | Used directly by the broker for partitioning/routing | Must test adapter, wire format, and transport config |
| **Both headers and payload** | Helpful when diverse consumers/tools inspect different layers | Requires **consistency** rules and tests preventing conflicting values |

Avoid duplicating data unnecessarily. If `tenantId` or `businessKey` appears in both headers and body, the contract must specify how consumers behave if they conflict: reject, pick one source, or fail safely. Security/authorization checks **must never** trust self-asserted headers from untrusted sources alone.

## 12. Producer code: creating metadata from business context

For meaningful verification, messages must originate from the **production application service**. Example event model:

~~~java
package com.example.inventory;

public record InventoryChangedEvent(
        String eventId,
        String eventType,
        String tenantId,
        String sku,
        boolean available,
        int quantity,
        long aggregateVersion) {
}
~~~

An event-publishing port:

~~~java
package com.example.inventory;

public interface InventoryEventPublisher {
    void publish(
            InventoryChangedEvent event,
            String correlationId,
            String businessKey);
}
~~~

Application service handling updates and calling the port:

~~~java
package com.example.inventory;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InventoryApplicationService {

    private final InventoryEventPublisher eventPublisher;

    public InventoryApplicationService(
            InventoryEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void changeStock(
            String tenantId,
            String sku,
            int quantity,
            long aggregateVersion,
            String correlationId) {

        // Demo only illustrates building the event. A real application still
        // needs permission checks, transactions, state/outbox persistence, etc.
        String businessKey = tenantId + "|" + sku;

        InventoryChangedEvent event = new InventoryChangedEvent(
            UUID.randomUUID().toString(),
            "InventoryChanged",
            tenantId,
            sku,
            quantity > 0,
            quantity,
            aggregateVersion
        );

        eventPublisher.publish(event, correlationId, businessKey);
    }
}
~~~

**Key rules:**

- `eventId` is generated **once per logical event**; when retrying delivery for that same event, preserve the stored ID (e.g., from an outbox) rather than calling `UUID.randomUUID()` again on each retry.
- `correlationId` comes from the request/workflow context; **never replace it with `eventId`**.
- `businessKey` is built from tenant + SKU to group by aggregate.
- `aggregateVersion` should come from real state versioning if used for ordering; passing it directly into `changeStock` is only illustrative and does not guarantee sequential ordering automatically.
- To prevent lost events between DB updates and publishing, production apps often need a **transactional outbox** or equivalent guarantee. Contract tests do not replace transactional consistency verification.

## 13. Adapter: a custom `businessKey` is not yet a broker key

An adapter can attach application headers when sending via Spring Cloud Stream:

~~~java
package com.example.inventory;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Component;

@Component
public class StreamInventoryEventPublisher
        implements InventoryEventPublisher {

    private final StreamBridge bridge;

    public StreamInventoryEventPublisher(StreamBridge bridge) {
        this.bridge = bridge;
    }

    @Override
    public void publish(
            InventoryChangedEvent event,
            String correlationId,
            String businessKey) {

        Message<InventoryChangedEvent> message =
                MessageBuilder.withPayload(event)
                    .setHeader("correlationId", correlationId)
                    .setHeader("businessKey", businessKey)
                    .setHeader("eventType", "InventoryChanged")
                    .setHeader("schemaVersion", "1")
                    .build();

        boolean accepted = bridge.send(
            "inventoryChanged-out-0", message
        );

        if (!accepted) {
            throw new IllegalStateException("Failed to send event");
        }
    }
}
~~~

The example intentionally separates the **logical binding name** `inventoryChanged-out-0` from the **broker destination** `inventory.events`. In Spring Cloud Stream, binding configuration maps the binding name to the destination:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventoryChanged-out-0:
          destination: inventory.events
~~~

This configuration is illustrative only; it is not written to an actual project file during this lesson.

**This is not yet proof of a Kafka record key.** `setHeader("businessKey", ...)` only sets an **application header**. With the Kafka binder, map it to the **Kafka key** using the API/header/binder config supported by your version (such as `KafkaHeaders.KEY` if supported by your adapter). With RabbitMQ, configure the exchange/routing key separately.

Never assume Kafka header names are identical across every Spring Kafka/Spring Cloud Stream version. Verify the **actual record key on the broker or in a producer adapter integration test**, not merely `businessKey` in JSON.

### Why not check only the boolean from `send`?

`StreamBridge.send(...)` reports acceptance by its abstraction; returning `true` **does not prove** the broker durably persisted the message or consumers processed it. Delivery, retries, outbox, DLQs, and acknowledgements require dedicated tests and guarantees.

## 14. Base test: trigger the production use case, don't emit fake messages

Generated message contract tests need a way to trigger the event. Example in a producer test base:

~~~java
package com.example.inventory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public abstract class ContractTestBase {

    @Autowired
    InventoryApplicationService inventoryService;

    public void triggerInventoryChanged() {
        inventoryService.changeStock(
            "tenant-a",
            "SKU-123",
            12,
            7L,
            "corr-1001"
        );
    }
}
~~~

In a real project, the base test must also configure an appropriate **message verifier/test binder** so SCC can observe outputs. If a database is used, manage fixtures/transactions so initial state is deterministic. Generated tests must connect to the producer's Spring context and messaging infrastructure.

**Off-target anti-pattern:**

~~~java
// Anti-pattern: base test constructs a message matching the contract itself.
public void triggerInventoryChanged() {
    testSink.send(
        "inventory.events",
        "{\"eventType\":\"InventoryChanged\","
        + "\"sku\":\"SKU-123\",\"quantity\":12}"
    );
}
~~~

This bad pattern fabricates a compliant event in a **test helper**, bypassing `InventoryApplicationService` and the production adapter. The producer could drop `correlationId`, send to the wrong destination, or compute `available` wrong while generated tests still stay green.

**Confirmation test:** temporarily break one production step—such as omitting the `correlationId` header in the adapter or changing `quantity` to 11. A properly scoped generated producer test must **fail** on the corresponding assertion. Then revert the change.

## 15. What does Contract Verifier observe?

Message contracts can verify described conditions:

- The event is **emitted after the appropriate trigger**.
- `sentTo('inventory.events')` matches the destination observed by the message verifier.
- The JSON body has the required fields and matching types/values.
- Headers such as `correlationId`, `businessKey`, `eventType`, and `schemaVersion` appear and match expectations.
- Dynamic values like `eventId` satisfy appropriate matchers.
- Generated tests are **generated and executed**, not merely sitting as a contract file.

However, never infer that a single generated message test automatically verifies:

- Actual Kafka record keys and broker-chosen partitions.
- RabbitMQ exchange types, queue bindings, or routing keys.
- Consumer groups, offset commits, broker ACLs/TLS.
- Duplicate delivery, idempotency, exactly-once, DLQs, retry/backoff.
- System-wide ordering or DB–message transactional consistency.
- Real network/broker latency in production.

Those require **adapter/broker integration tests** or dedicated operational verification. SCC is an essential communication contract layer, not a replacement for all event-driven testing.

## 16. Header matchers: static, dynamic, and propagation

The example contract uses `correlationId: corr-1001` so generated producer tests can verify **the value propagated from the trigger**. In real systems, correlation IDs vary per workflow.

Three testing strategies:

1. **Deterministic sample:** the base test invokes the use case with `corr-1001`, and the contract requires exact `corr-1001`. This proves propagation for one known input.
2. **Format matcher:** checks that correlation ID matches an allowed regex/format when generated dynamically. Use your DSL/version's header-matcher syntax and inspect the generated assertion.
3. **Supplementary integration test:** invoke the producer with **two different correlation IDs**, observe the corresponding events, and prove the incoming ID is reflected rather than hardcoded.

A producer that always emits `corr-1001` would pass a fixed-sample contract yet **fail** an integration test with `corr-2002`. Therefore, a regex matcher checking only syntax does not prove **correlation with the input context**.

### Missing, blank, and malformed headers

| Input or output header | Rule to define |
|---|---|
| Missing correlation ID | Generate a new one, reject, or apply another policy? |
| `correlationId: ""` | Is empty string accepted? |
| Very long value | Length cap to prevent log/trace abuse |
| Value containing newlines | Must be rejected or safely normalized |
| Same ID in header and body | Must both values match? |
| Trace ID present but no correlation ID | One-way mapping or kept independent? |

Never let tests check only that a header **exists** when the real consumer requires the **exact ID of a specific request**.

## 17. Business keys and per-aggregate event ordering

For inventory, two events can happen back to back:

~~~text
eventId=evt-101   businessKey=tenant-a|SKU-123   aggregateVersion=7
eventId=evt-102   businessKey=tenant-a|SKU-123   aggregateVersion=8
~~~

If the same business key is properly mapped to the Kafka record key, both events typically land in the same partition under a stable configuration. Consumers can use `aggregateVersion` to detect **stale/late events** or out-of-order arrivals.

Do not rely solely on broker ordering:

- A consumer may process asynchronously and complete handlers out of order.
- Retries or dead-letter/re-publish flows can disrupt processing order.
- Changing partition counts or partitioning algorithms changes where new records land.
- Multiple concurrent producers for the same aggregate need version/state control to preserve meaningful order.
- Inconsistent casing or missing/present `tenantId` in the business key splits one aggregate across multiple keys.

A useful test emits two events with the same key at versions 7 and 8, verifies the adapter sends the right key, checks that the consumer updates state per version policy, and tests an older event arriving late. A single-event contract test does not prove any of these ordering conditions on its own.

## 18. Correlation and idempotency across a chain of events

Suppose Inventory Service emits `InventoryChanged`, and Checkout Service processes it and emits `CheckoutUpdated`:

~~~mermaid
sequenceDiagram
    participant HTTP as API Request
    participant Inventory as Inventory Service
    participant Broker as Message Broker
    participant Checkout as Checkout Service
    HTTP->>Inventory: changeStock(correlationId=corr-1001)
    Inventory->>Broker: InventoryChanged(eventId=evt-101, key=tenant-a|SKU-123)
    Broker-->>Checkout: deliver evt-101, corr-1001
    Checkout->>Checkout: dedup by eventId; execute business logic
    Checkout->>Broker: CheckoutUpdated(eventId=evt-202, correlationId=corr-1001)
    Broker-->>Checkout: redeliver evt-101
    Checkout->>Checkout: recognize evt-101 was already processed
~~~

Rules:

- **Correlation ID** stays the same throughout the workflow when steps belong to the same request.
- **Event ID** of `CheckoutUpdated` differs from `InventoryChanged` because it is a distinct logical event.
- **Business key** may switch from SKU to order ID when the next step concerns a different aggregate.
- **Causation ID** (if used) on `CheckoutUpdated` can point to `evt-101`.
- Redelivery of `evt-101` should preserve its event ID so consumers can skip duplicate processing.

A single-output messaging contract protects headers and payload; verifying idempotency and multi-event chains requires corresponding **consumer handler tests, integration tests, and state assertions**.

## 19. Stub Runner and consumer-side verification

Once the producer generates stubs from contracts, consumers can use **Stub Runner** to emit a simulated message by contract label. Example test configuration:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-service:1.3.0-rc1:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class InventoryEventConsumerContractTest {
    // Consumer test requires appropriate messaging test infrastructure.
}
~~~

In a `LOCAL` setup, the stubs JAR must already exist in the local Maven repository. In multi-job CI environments, configure a remote repository and the matching mode.

In supported Stub Runner messaging APIs, tests can use `StubTrigger` to fire a message by label:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.contract.stubrunner.StubTrigger;

@Autowired
StubTrigger stubTrigger;

void triggerStubMessage() {
    stubTrigger.trigger("inventoryChanged");
}
~~~

This is an **illustrative snippet** to place inside a test class, while messaging adapters/test binders and consumer listeners must be configured. Package names, trigger APIs, and supported modes depend on SCC version. Tests must verify that the consumer **actually receives** the message and processes its fields/headers.

A consumer test should verify:

1. The listener receives the message from the destination/subscription supported by the test environment.
2. `correlationId` is extracted and propagated into downstream processing or logging.
3. `businessKey` or aggregate fields map to the right domain entity.
4. `eventId` enables deduplication when the same event is delivered twice.
5. `schemaVersion` is read accurately and the body maps to a valid DTO.
6. Consumer processing behavior is correct, not merely that “the message was triggered”.

**Limitation:** Stub Runner messaging simulates messages at the contract/test-binder layer. It does not necessarily reproduce exact Kafka partition keys, Rabbit exchange bindings, or broker acknowledgements. Those constraints require adapter/broker integration tests.

## 20. Broker/adapter tests for partition keys and routing

If the business key must become the Kafka record key, tests should inspect the **actual record**, not just an application-created header. For Kafka, a test using Embedded Kafka or Testcontainers Kafka can:

1. Start a test broker with a deterministically configured topic.
2. Run the production producer adapter with the message business key.
3. Read the record with a Kafka test consumer.
4. Assert **topic**, **`record.key()`**, headers, and payload.
5. Emit two events with the same business key and verify partition consistency under a stable test config.
6. Test different tenant/SKU keys and verify canonicalization rules.

Conceptual assertion sample:

~~~java
// Illustrative code inside a configured broker integration test.
// record is a ConsumerRecord<String, byte[]> read from the test broker.
assertThat(record.topic()).isEqualTo("inventory.events");
assertThat(record.key()).isEqualTo("tenant-a|SKU-123");
assertThat(record.value()).isNotEmpty();
~~~

Never conclude that two different keys **must** land in different partitions: a partitioner can hash them into the same partition. What you protect is the **exact key**, and—when per-aggregate ordering matters—partition consistency under the active configuration.

For RabbitMQ, the corresponding test must verify exchanges, routing keys, queue bindings, and where the consumer actually receives messages. Kafka record keys and Rabbit routing keys serve different purposes; never apply one shared assertion to both.

## 21. How bad routing data causes failures

| Change | Possible outcome | Test needed |
|---|---|---|
| Rename `inventory.events` to `inventory.v2.events` | Consumers subscribed to old topic miss events | Contract `sentTo` and adapter/broker integration |
| Drop `correlationId` header | Lost workflow/trace correlation | Generated producer test + consumer handler test |
| Use `eventId` as Kafka key instead of business key | Events for same SKU scatter across partitions | Broker adapter test asserting `record.key()` |
| Change key from `tenant-a|SKU-123` to `SKU-123` | Tenants may collide in grouping | Key-builder unit test + broker test |
| Change `schemaVersion` from string `"1"` to number `1` | Consumer parsing/header handling may break | Contract header + consumer compatibility test |
| Change Rabbit routing key | Message goes to wrong queue or has no matching binding | Rabbit integration test |
| Rename field `sku` to `productId` | Consumer fails to deserialize/read properly | Producer contract + new consumer stub |
| Generate new `eventId` on each retry of same event | Consumer deduplication stops working | Outbox/retry/idempotency integration test |
| Emit events for same aggregate out of order | Consumer ends up with stale state or logic bugs | Version/ordering handling test |

**Diagnosis:** if a consumer never sees an event, do not inspect only the JSON body. Trace destination → binding → broker route/key → consumer group/queue → serialization → listener.

## 22. Untrusted headers and security risks

Correlation IDs and business keys frequently appear in logs and metrics, sometimes crossing organizations or tenants. Treat them as untrusted input:

- **Validate format, length, and character set**; never let oversized strings or control characters reach logs unescaped.
- **Never treat a self-declared `tenantId` header as authorization evidence.** Cross-check against a trusted authentication/authorization context.
- **Never embed personal data** into correlation IDs or broker keys unnecessarily; use opaque/random IDs or hashed/encrypted keys per policy.
- **Prevent unbounded metric cardinality**: per-request correlation IDs do not belong as labels on bounded time-series metrics.
- **Prevent cross-tenant leakage**: routing an event to the wrong tenant can be far worse than a typical functional bug.
- **Keep metadata schemas stable** and define rules for handling invalid headers.
- When using tracing headers (such as `traceparent`), use standard propagation libraries instead of inventing ad-hoc string IDs.

Contract tests can check fields and formats, yet ACLs, authorization, tenant isolation, and broker security still require dedicated security and integration tests.

## 23. Schema evolution: changing headers can break consumers too

Changing the body is not the only way to break consumers. Headers and routing metadata can also be part of the API/message contract.

Suppose version 1 uses:

~~~text
correlationId: corr-1001
businessKey: tenant-a|SKU-123
schemaVersion: "1"
destination: inventory.events
~~~

Version 2 wants to switch to:

~~~text
traceId: corr-1001
partitionKey: tenant-a:SKU-123
schemaVersion: "2"
destination: inventory.v2.events
~~~

If consumers read `correlationId` or subscribe to `inventory.events`, changing names or encoding **breaks compatibility** even when the body stays identical.

An evolution plan typically follows phases:

1. **Expand:** producer continues supplying old headers/destinations while adding new metadata/routes if required.
2. **Migrate:** new consumers read/subscribe using the new conventions; run tests against both old and candidate stubs.
3. **Contract:** remove old forms only after all supported consumers have migrated.
4. **Release gate:** never ship a new version until compatibility is verified or a versioning plan is in place.

When using **dual-publish** to two topics during migration, design idempotency and event identity carefully: the same logical event sent over two channels could be processed twice by a single consumer.

## 24. CloudEvents and tracing: useful standards, never mix IDs

Some systems adopt **CloudEvents** to standardize event envelopes. Attributes like `id`, `source`, `type`, `subject`, and `time` carry standard meanings. Example:

~~~json
{
  "specversion": "1.0",
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "/inventory-service",
  "type": "com.example.inventory.changed.v1",
  "subject": "tenant-a/SKU-123",
  "time": "2026-11-24T04:00:00Z",
  "data": {
    "tenantId": "tenant-a",
    "sku": "SKU-123",
    "quantity": 12
  }
}
~~~

CloudEvents `id` paired with `source` identifies an event per standard semantics. `subject` can describe the subject entity, yet is not automatically a Kafka record key. **Correlation ID** remains a separate concept, carried via an extension attribute or header by convention.

When using W3C Trace Context, `traceparent` and tracing baggage/headers must be propagated by a compliant library; never equate `traceId` with `eventId` or `businessKey`.

This lesson does not require switching to CloudEvents. The main takeaway is **never pick one random ID and overload it for every role**; when adopting an envelope standard, honor its semantics and test conversions.

## 25. Integrating message contracts into CI/CD

A compatibility-protecting pipeline can be divided into gates:

~~~mermaid
flowchart TD
    A["PR modifies producer, contract, or adapter"] --> B["Parse/generate message contract tests"]
    B --> C["Run generated producer tests with real app flow"]
    C --> D{"Headers/body/destination pass?"}
    D -- "No" --> X["BLOCK"]
    D -- "Yes" --> E["Broker/adapter tests for key/routing"]
    E --> F{"Key/topic/binding right?"}
    F -- "No" --> X
    F -- "Yes" --> G["Package candidate stubs"]
    G --> H["Consumer tests using Stub Runner"]
    H --> I{"Consumer processes event right?"}
    I -- "No" --> X
    I -- "Yes" --> J["Proceed to release gates"]
~~~

In a Maven producer with the plugin configured:

~~~bash
./mvnw clean verify
~~~

In Gradle with the matching Spring Cloud Contract plugin:

~~~bash
./gradlew clean test
~~~

These commands **only illustrate the build cycle**: exact task names, test bases, message verifiers, and stub packaging vary by plugin/version. Never infer messaging contracts ran just because the build exited 0.

CI must archive evidence:

- Contracts were discovered, generated tests **actually ran**, and they observed messages from production triggers.
- Headers, payload, and destination were verified without overly loose matchers.
- Adapter/broker integration results for Kafka keys or Rabbit routing when applicable.
- Stubs artifact matches exact **group, artifact, version, classifier, commit**; no stale cache mistakes.
- Consumers triggered stubs/messages, real listeners processed them, and assertions passed.
- Retry/dedup/ordering tests when required by business rules.

**Never let CI go green merely because a JSON fixture file parses.** In message-driven systems, wrong metadata or routing can prevent consumers from ever seeing events.

## 26. Four-round practice exercise

### Round A — Metadata analysis

For the `InventoryChanged` event, build a table explaining:

1. `correlationId = corr-1001`: which events in the workflow share it?
2. `eventId = 550e8400-e29b-41d4-a716-446655440000`: what happens upon redelivery?
3. `businessKey = tenant-a|SKU-123`: why is `tenantId` needed?
4. Is destination `inventory.events` an application logical address or a broker topic?
5. With Kafka, which field must become the **record key** to group by SKU?

**Output:** propagation diagram and ownership table for every field/header/transport attribute.

### Round B — Writing the message contract and producer test

1. Write the Groovy or YAML message contract from Section 9/10.
2. Specify `label`, `triggeredBy`, `sentTo`, headers, body, and a UUID matcher for event ID.
3. Create a test base calling real `InventoryApplicationService.changeStock(...)`.
4. Configure the message verifier/test binder and run generated producer tests.
5. Intentionally drop `correlationId` or change the destination in the adapter; verify the right test catches it.

**Output:** contract, base test, generated source/test report, and intentional failure evidence.

### Round C — Testing broker routing and idempotency

1. Using a test broker or test adapter, publish the event with `businessKey`.
2. Read the Kafka record (if using Kafka) and verify `record.key()` and topic.
3. Emit two events for the same SKU with increasing `aggregateVersion`, checking partition/order under a stable configuration.
4. Redeliver **the same `eventId`**; the consumer must not apply business changes twice if idempotency is required.
5. Change tenant while keeping SKU; verify keys do not collide.

**Output:** record-key logs, deduplication test results, and ordering-limit analysis.

### Round D — Consumer contracts and breaking changes

1. Package candidate stubs from the exact verified commit.
2. Have Checkout use Stub Runner to trigger label `inventoryChanged`; verify the listener handles metadata.
3. Rename `correlationId` to `traceId` or change destination on a scratch branch.
4. Observe which producer/consumer tests fail.
5. Design a migration plan so older consumers do not miss events.

**Output:** stub coordinates, consumer test report, breaking-change inventory, and migration plan.

## 27. Checklist before merging a message contract

- [ ] Each field (`correlationId`, `eventId`, `businessKey`) has a clearly documented role and owner.
- [ ] Correlation ID is not used as event ID or Kafka partition key when semantics conflict.
- [ ] Event ID stays stable across redeliveries of the **same logical event**.
- [ ] Business key includes all aggregate-identifying parts, especially tenant.
- [ ] Header/payload/transport keys are mapped clearly without contradictions.
- [ ] Contract accurately specifies `label`, `triggeredBy`, `sentTo`, headers, and body.
- [ ] Generated producer tests invoke **production use cases**, never emitting hardcoded JSON from the base test.
- [ ] Message verifier/test binder observes the right destination and headers.
- [ ] If using Kafka partition keys, an adapter/broker test verifies the **actual `record.key()`**.
- [ ] If using RabbitMQ routing, exchange/routing key/queue bindings are tested.
- [ ] Missing, blank, malformed headers and untrusted inputs are checked where needed.
- [ ] Consumers use event ID for deduplication per policy, never confusing it with correlation ID.
- [ ] Header, schema version, or destination changes are evaluated as potentially breaking.
- [ ] Consumer tests use Stub Runner with candidate stubs matching exact version/commit.
- [ ] CI confirms generated test count > 0 and archives test reports, artifacts, and broker test results.
- [ ] Retry, DLQ, ordering, and deduplication plans exist where business rules demand them, rather than being inferred from a single contract.

## 28. Self-check questions

**1. How do correlation ID and event ID differ?**

Correlation ID groups **multiple steps within one workflow**. Event ID identifies **one logical event**; redeliveries of that event should keep the same event ID so consumers can prevent duplicate processing.

**2. Does placing `businessKey` in a header automatically make it the Kafka record key?**

No. `businessKey` is application metadata. The producer adapter or binder must map it to the Kafka key using the mechanism supported by your project's version, and you must verify the real record.

**3. Does `sentTo('inventory.events')` prove Kafka partition keys and RabbitMQ routing keys are right?**

No. It specifies the destination observed by the message contract verifier. Kafka keys/partitions and Rabbit routing require adapter/broker integration tests when they are key commitments.

**4. If two distinct events share the same correlation ID, should consumers deduplicate by correlation ID?**

Usually no. Both events may belong to the same workflow and both need processing; deduplicating by correlation ID would drop valid events.

**5. Why shouldn't a base test emit sample messages directly?**

Because tests could pass even if production code emits no events, drops headers, or routes incorrectly. Base tests must trigger production use cases so generated tests observe real outputs.

**6. Why can changing a destination or topic also be a breaking change?**

Because consumers subscribed to the old address may **stop receiving messages** even though the JSON body did not change. Coordinate rollouts, test routing, and plan migrations.

**7. Why does sharing a business key help Kafka ordering without guaranteeing system-wide order?**

Because a partitioner can route records with the same key to one partition, where Kafka preserves log order. However, there is no global order across partitions, and retries, concurrent processing, partition-count changes, and multiple producers still affect ordering.

## 29. References

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): message contracts, generated producer tests, and Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, message input/output, and matchers.
- [Spring Cloud Contract – Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): message contract testing and messaging infrastructure (verify URL/version against your docs when applying).
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): bindings, destinations, and binder-specific message metadata.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): Kafka record keys, headers, producers/consumers.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): topics, partitions, and delivery semantics.
- [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials): exchanges, routing keys, queues, and bindings.
- [CloudEvents Specification](https://github.com/cloudevents/spec): envelope standard and `id`, `source`, `type`, `subject` attributes.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent` structure and propagation.

**Version note:** Message DSL syntax, header/body matcher capabilities, `StubTrigger`, message verifiers, and how binders map Kafka/Rabbit metadata depend on SCC/Spring Cloud Stream/broker adapter versions. Always verify **generated tests, stub mappings, and actual broker records** against your project's dependency versions. Examples are learning material, not outputs from an executed build.

---

**Key takeaway:** `correlationId` links steps across a workflow; `eventId` identifies a logical event and prevents redelivery duplicates; `businessKey` identifies an aggregate for grouping and can become a partition key **if the adapter maps it properly**. `sentTo` defines the message target at the contract level, while Kafka keys, partitions, and Rabbit routing require transport-level verification. A trustworthy message contract protects **body + headers + destination**, runs through **real producer code**, and tests consumers via **candidate stubs** alongside necessary broker/adapter tests in CI.
