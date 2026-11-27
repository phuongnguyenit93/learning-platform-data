# Avoiding Event and Message Loops

In `SPRING_INTEGRATION_ADAPTERS`, an integration flow typically receives data through an inbound adapter, transforms or routes messages using `MessageChannel`s, and sends data out via an outbound adapter. Gateways can combine sending and receiving replies; pollers can read sources on a schedule. When an output becomes an input to the same flow again, the same event can circulate through the system repeatedly, creating duplicate records, sending repeated notifications, or driving continuous load.

This lesson focuses on identifying and stopping loops in file, SFTP, HTTP, JMS, AMQP, Kafka, and database flows. Two distinct issues must be separated: a **loop** is a path causing a message to return to a step that already processed it; a **duplicate message** is the same event delivered multiple times, possibly due to retries, redelivery, or delivery-guarantee mechanics. Both issues often appear together, yet require complementary safeguards.

## 1. How Do Loops Form?

An event describes something that happened in the domain, such as `OrderCreated`. A message is the Spring Integration unit passed between endpoints; it carries a payload plus headers such as ID, correlation, source, or routing info. One event can be packaged inside multiple different messages as it traverses adapters. Therefore, looking only at channel names or adapter types is not enough to tell whether a message is coming back; you must understand both the internal topology and paths through external systems.

Common forms of loops:

- **In-app circular wiring:** channel A routes to handler B, and handler B sends back to channel A. A misconfigured bridge or router can also create a backward edge.
- **Echo through an external system:** the application consumes an event from Kafka, publishes that event to a topic consumed by the same inbound adapter, and re-consumes the message it just emitted.
- **Re-reading output data:** file outbound writes to the directory watched by file inbound; or SFTP outbound uploads files to the exact remote directory scanned by the inbound poller.
- **Self-triggering CDC:** a flow receives changes from a database table and updates the same tracked table, causing the change-data-capture reader to emit a new event.
- **Reply turned back into request:** an HTTP or messaging gateway sends a request, receives a reply, and another route feeds that reply back into the request channel.
- **Fan-out mistaken for duplicates:** `PublishSubscribeChannel` delivers a message to multiple subscribers. If one subscriber sends the message back to an entry branch, the system both fans out and loops.

Example of a risky topology:

```text
Kafka inbound adapter
        |
        v
  eventChannel ---> business processing ---> Kafka outbound adapter
        ^                                      |
        +------------- same topic --------------+
```

If outbound publishes to the exact topic inbound consumes, events can come back. Consumer groups, offsets, or pollers only govern how messages are read; they do not by themselves prove an event was processed once.

## 2. Designing a Clear Directional Topology

Define entry, processing, and exit boundaries before configuring adapters. A typical flow looks like:

```text
External source
    |
    v
Inbound adapter
    |
    v
partnerInboundChannel
    |
    v
Contract validation + loop guard
    |
    v
domainEventChannel
    |
    v
Business handler
    |
    v
partnerOutboundChannel
    |
    v
Outbound adapter
    |
    v
External target
```

Any return path, if present, should be a separate flow with a clear contract and correlation ID. Do not wire output back to the input channel just to "wait" for a reply. For request-reply, the gateway correlates replies with requests; the responding handler must return to the reply channel or equivalent mechanism rather than emitting the reply as a new request.

Channel design guidelines:

- Name channels by role and direction, e.g., `partnerInboundChannel`, `validatedOrderChannel`, `partnerOutboundChannel`. Clear names make reverse links obvious when reading configuration.
- Pick channels by semantics. `DirectChannel` delivers to one subscriber; `PublishSubscribeChannel` broadcasts to multiple subscribers; `QueueChannel` buffers messages for consumers to poll later. Fan-out is intentional behavior, not a loop-prevention mechanism.
- Use bridges only when forwarding between two channels is needed. Trace the full graph to prevent bridging A to B while also bridging B back to A.
- Routers must define a default route or an explicit discard branch. Do not route invalid messages back to the source channel for unbounded retries.
- Logging or metrics-only branches should have no business side effects. If a monitoring branch must forward messages elsewhere, use a dedicated channel and ensure it never merges back into the processing flow.

## 3. Placing a Loop Guard at the Inbound Boundary

A loop guard inspects messages right after the inbound adapter, before a message can trigger side effects. For the guard to work across multiple systems, standardize an event envelope. Example:

```json
{
  "eventId": "evt-8f12",
  "eventType": "InventoryAdjusted",
  "originSystem": "warehouse-erp",
  "lastEmitter": "inventory-service",
  "visitedSystems": ["warehouse-erp", "inventory-service"],
  "hopCount": 2,
  "correlationId": "order-391",
  "causationId": "evt-7a21",
  "schemaVersion": 1,
  "payload": {
    "sku": "SKU-42",
    "quantity": 18
  }
}
```

Field meanings:

| Field | Role |
|---|---|
| `eventId` | Stable event identifier; preserved across retries and redeliveries |
| `originSystem` | System that originally produced the event; unchanged when forwarded |
| `lastEmitter` | System that most recently emitted the message |
| `visitedSystems` | Systems that have processed or forwarded the event; used to detect re-entry |
| `hopCount` | Number of hops traversed; bounds path length |
| `correlationId` | Links messages belonging to the same business workflow or request |
| `causationId` | Event or message that directly caused the current event |
| `schemaVersion` | Payload contract version |

When the outbound adapter emits an event to the next system, the handler builds the outgoing envelope keeping `eventId` and `originSystem`, updating `lastEmitter`, appending the current system ID to `visitedSystems`, and incrementing `hopCount`. When the inbound adapter receives an event again, the guard drops events already containing the current system ID in `visitedSystems` or exceeding the hop limit.

The Java DSL example below assumes the adapter already parsed JSON into a `Map`. In a real application, replace `Map` with a validated DTO. `SERVICE_ID` and `MAX_HOPS` are application configuration values.

```java
import java.util.Collection;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.core.MessageSelector;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
MessageSelector loopGuard() {
    return message -> {
        Object payload = message.getPayload();
        if (!(payload instanceof Map)) {
            return false; // Malformed envelope: route to discard branch.
        }

        Map<?, ?> event = (Map<?, ?>) payload;
        Object eventId = event.get("eventId");
        Object visited = event.get("visitedSystems");
        Object hops = event.get("hopCount");

        boolean visitedHere = visited instanceof Collection
                && ((Collection<?>) visited).contains(SERVICE_ID);
        int hopCount = hops instanceof Number
                ? ((Number) hops).intValue() : 0;

        return eventId != null && !visitedHere && hopCount < MAX_HOPS;
    };
}

@Bean
IntegrationFlow partnerInboundFlow(MessageSelector loopGuard) {
    return IntegrationFlow.from("partnerInboundChannel")
            .filter(loopGuard,
                    endpoint -> endpoint.discardChannel("loopDiscardChannel"))
            .channel("domainEventChannel")
            .get();
}
```

In this example, the selector returns `false` for malformed envelopes, events that already visited the current service, or events exceeding the hop limit. `discardChannel` routes dropped messages to a separate branch for recording and investigation. Never send them back to the inbound channel. If the system needs to separate contract-violation messages from echoed messages, use distinct selectors or discard branches for accurate metrics.

**Note on headers:** Spring message headers are useful for routing inside the application, yet not every adapter or external system transmits all headers. When metadata must traverse HTTP, JMS, AMQP, Kafka, files, or SFTP, map it to supported transport headers or include it in the envelope payload. Verify header mapper settings and actual contents after passing through adapters. Never rely on an internal header that may be stripped at the transport boundary.

## 4. Combining Loop Guards with Idempotency

A loop guard prevents an event from returning along known paths. Idempotency prevents the same event from producing repeated side effects when a broker redelivers, a poller re-reads, or a client retries. A consumer should use a stable idempotency key, typically `(originSystem, eventId)` or a globally unique ID.

A processing workflow can be structured as follows:

1. Validate the envelope and verify `eventId`.
2. Use a durable state store to claim the idempotency key. If the key is already completed, record a duplicate and finish the message.
3. Perform the business update.
4. Mark processing complete in the same transaction as the business change when both reside in the same database.
5. If follow-up events must be emitted, write them to a transactional outbox in the same transaction; a publisher process dispatches the outbox afterward.

Spring Integration provides `IdempotentReceiverInterceptor`, `MetadataStore`, and `MetadataStoreSelector` to implement duplicate message control. Choose a `MetadataStore` implementation backed by durable, shared storage when running multiple instances. In-memory stores do not protect across restarts or when two instances receive the same event concurrently. For critical workflows, a database unique constraint or atomic claim prevents race conditions.

Example SQL in PostgreSQL syntax for a table tracking consumed events:

```sql
INSERT INTO consumed_event (origin_system, event_id, processed_at)
VALUES (:originSystem, :eventId, CURRENT_TIMESTAMP)
ON CONFLICT (origin_system, event_id) DO NOTHING;
```

The application proceeds only when the insert actually creates a new row. Execute the claim and business change in an appropriate transaction; marking as processed first and executing the side effect in a separate transaction risks losing the event if a failure occurs between steps. For side effects outside the database, attach an idempotency key if the target API supports it, or use an outbox and delivery state for safe retries.

Do not promise "exactly once" merely because a broker or adapter offers special delivery modes. Across a multi-system flow, retries and network failures can still cause repeated deliveries. Designing idempotent consumers and side effects with stable keys is usually the more practical control.

## 5. Applying This by Adapter Type

| Connection type | Common cause of loops | How to prevent |
|---|---|---|
| File | Inbound poller watches the same directory where outbound writes files | Separate `inbox`, `outbox`, and `archive` directories; scan only inbound filename patterns; move processed files to archive; write outbound files using a temporary name then rename in `outbox` |
| SFTP | Inbound poller downloads files that outbound just uploaded | Separate remote paths by direction; filter filenames and completion markers; persist received file markers durably; archive or delete source files per partner agreement |
| HTTP | Webhook receives callbacks from the endpoint outbound client just called | Use distinct URLs and routes for webhooks and outbound APIs; verify signatures and event IDs; use idempotency keys; do not call back to your own webhook unless required by contract |
| JMS | Consumer re-receives messages just sent by the same flow's producer | Use dedicated queues/topics by direction or event type; configure clear selectors and routing; control redelivery and dead-letter queues; keep event IDs stable |
| AMQP | Exchange bindings route messages back to the source queue | Audit exchanges, routing keys, and queue bindings; separate routing keys for inbound/outbound events; never bind the source queue to routes re-emitting the same event |
| Kafka | Consumer reads a topic the service itself publishes to | Separate input and output topics; share a topic only when event contracts and subscriptions are explicitly designed; filter self-emitted events and use event IDs for deduplication |
| Database / CDC | Consumer updates a table watched by CDC | Separate source, target, and outbox tables; filter self-generated changes where appropriate; avoid writing identical data back to the source table; define transaction and event-emission order |

Items to check more closely:

- **File and SFTP:** a poller only decides when to read. It does not guarantee each file is processed once. An in-memory accept-once filter loses state after restarts; consider a durable metadata store, unique filenames, checksums, or archiving. Never read files still being written by an outbound adapter.
- **HTTP:** inbound endpoints typically receive webhooks while outbound gateways call partner APIs. Separate the two URLs by role and validate `eventId`, signatures, timestamps, and idempotency keys. If a partner sends a callback, it must carry a correlation ID linking back to the original request.
- **JMS and AMQP:** redelivery after rollback is normal delivery behavior, not necessarily a topology loop. Configure bounded retries, backoff, and dead-letter routes; ensure dead-letter queues are never routed back to source queues endlessly.
- **Kafka:** consumer groups balance load across consumers in the same group; they do not stop a service from reading events it just published. Govern topics, keys, event types, and subscriptions by contract. When filtering out self-published events, inspect source metadata in the consumer.
- **Database:** a transactional outbox updates business data and records events to emit in the same transaction. A CDC publisher reads the outbox and publishes to the broker; consumers should not write echoed results back into the outbox table or a table generating the same change event.

## 6. Controlling Pollers, Gateways, and Error Flows

**Pollers** control the cadence of reading sources like directories, SFTP, or database tables. Configure fixed delay, cron, transactions, and max messages per poll to manage load. These settings do not replace loop guards or idempotency. If a poller reads a source that an outbound adapter might write back to, fix the source/target boundary before tuning schedules.

**Gateways** typically implement request-reply. Preserve the correlation ID from request to reply, set timeouts, and define explicit reply channels. If a reply represents a new business event, generate a new event ID and set causation ID pointing to the original request or event. Never reuse the exact same event ID for a new event solely because they are related.

**Error flows** must have a termination point. Retries should be bounded, use backoff, and separate transient errors from data errors. Once retries are exhausted, move messages to a dead-letter or quarantine channel for investigation. Avoid configuring an error handler that sends failed messages unboundedly back into the channel that failed. When replaying from dead-letter, keep the original event ID so idempotency continues protecting side effects.

## 7. Testing and Observability

An integration test suite should cover both normal paths and re-entry scenarios:

1. Send a fresh event through a simulated inbound adapter; confirm the business handler runs once and the outbound adapter emits one event.
2. Re-send the same `eventId`; confirm the consumer detects the duplicate and does not repeat side effects.
3. Send an event whose `visitedSystems` contains `SERVICE_ID`; confirm the loop guard routes it to the discard channel.
4. Send an event whose `hopCount` has reached the limit; confirm it is blocked before the business handler.
5. Simulate broker redelivery or poller re-reading after restart; confirm idempotency metadata persists.
6. Trigger failures in outbound or handler steps; confirm bounded retries and that dead-letter routing does not loop back to the source flow.
7. Verify header mapping or envelopes across each transport boundary to ensure event IDs and required metadata are preserved.

In logs and metrics, track `eventId`, `originSystem`, `lastEmitter`, `correlationId`, channel, adapter, hop count, and guard outcome. Maintain separate metrics for valid messages, duplicates, blocked loops, malformed envelopes, retries, and dead-lettered messages. Alert on unusual spikes in blocked messages or hop counts. Avoid logging full payloads containing sensitive data; identifying metadata and status are usually enough for tracing.

### Practical Exercise

A Spring Integration service reads `OrderUpdated` events from Kafka topic `orders`, updates the database, and then publishes the normalized event to topic `orders`. The inbound adapter also consumes topic `orders`. After each processing run, the event reappears at the input and keeps updating the database.

Propose fixes in priority order:

1. Redraw inbound and outbound directions; choose separate topics or a distinct routing contract so the consumer does not re-read events emitted by the same flow.
2. Add an envelope with `eventId`, `originSystem`, `visitedSystems`, `hopCount`, and `causationId`; preserve the event ID across retries.
3. Place a filter immediately after the inbound adapter and route dropped events to a monitoring channel.
4. Add a durable idempotency store keyed by `(originSystem, eventId)` to protect against broker redelivery.
5. If database updates and event publication must stay consistent, write the event to a transactional outbox in the same transaction and publish from the outbox.
6. Test fresh events, echoed events, duplicate deliveries, consumer restarts, and publish failures.

**Completion criteria:** the topology has no unintended edge returning to the source; echoed events are blocked before side effects; duplicate deliveries produce no repeated business updates; retries and error flows are bounded; events remain traceable across adapters.
