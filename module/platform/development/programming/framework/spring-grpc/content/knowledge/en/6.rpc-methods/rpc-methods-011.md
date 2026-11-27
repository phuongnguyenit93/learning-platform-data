# Distinguishing RPC Commands from Event Notifications

In a gRPC system, a client can either **request the server to perform an action** or **receive notifications about an event that has occurred**. On the surface, both needs can be expressed with RPCs and Protobuf messages, yet they carry distinct semantics:

- **Command** expresses an intent or request to change state. The client asks the server: “Please do this.”
- **Event notification** expresses a fact that has already happened. The server informs the client: “This has happened.”

Making this distinction cleanly helps you design method names, requests/responses, statuses, retryability, and streaming flows appropriately in **Spring gRPC**. A command is commonly invoked directly with a unary RPC; an event stream is commonly delivered via server streaming. However, the RPC type only describes how messages are transported; it does not by itself define command or event semantics.

## 1. A Command Is a Request; an Event Is a Fact

Example in an inventory system:

| Aspect | Command | Event notification |
| --- | --- | --- |
| Meaning | Request to reserve 5 items | Warehouse reserved 5 items |
| Name | **ReserveStock** | **StockReserved** |
| Timing | Before state changes | After the event has occurred |
| Emitter | Client/consumer authorized to make the request | Component recording the change |
| Receiver | An authoritative service handling commands | One or more interested subscribers |
| Outcome | Accepted, rejected, or errored | Information about what happened |

Commands typically use imperative verbs such as **Reserve**, **Cancel**, **Approve**, and **Create**. Events typically use past-tense event names such as **StockReserved**, **OrderCancelled**, and **PaymentApproved**. This naming convention immediately tells readers whether the client is requesting an action or receiving a notification.

A command does not guarantee state has changed simply because the client sent a request. The server must authenticate, check preconditions, and execute business logic. An event should only be emitted after the system has established that the event genuinely occurred according to domain consistency rules.

## 2. Expressing Commands and Events in Protobuf

A single service can expose both command RPCs and event subscription RPCs:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";

service InventoryService {
  // Command: request to change inventory.
  rpc ReserveStock(ReserveStockRequest)
      returns (ReserveStockResponse);

  // Subscription: receive events that have occurred.
  rpc WatchStockEvents(WatchStockEventsRequest)
      returns (stream StockEvent);
}

message ReserveStockRequest {
  string product_id = 1;
  int32 quantity = 2;
  string idempotency_key = 3;
}

message ReserveStockResponse {
  string reservation_id = 1;
  int64 stock_version = 2;
}

message WatchStockEventsRequest {
  string product_id = 1;
  int64 after_sequence = 2;
}

message StockEvent {
  string event_id = 1;
  string product_id = 2;
  int64 sequence = 3;
  google.protobuf.Timestamp occurred_at = 4;

  oneof payload {
    StockReserved stock_reserved = 5;
    StockReleased stock_released = 6;
  }
}

message StockReserved {
  int32 quantity = 1;
  string reservation_id = 2;
}

message StockReleased {
  int32 quantity = 1;
  string reservation_id = 2;
}
~~~

In this contract:

- **ReserveStock** is a **command RPC**: the client sends one request and receives one processing result.
- **WatchStockEvents** is an **event subscription RPC**: the client sends a filter/starting point, and the server emits multiple **StockEvent** messages.
- **StockEvent** is a shared envelope with **event_id** for identification, **sequence** for ordering within a product scope, and **occurred_at** for the timestamp.
- **oneof payload** distinguishes event types and holds event-specific data.
- **idempotency_key** helps the server recognize retries of the same command if the client loses the response.

Do not name an event **ReserveStockRequest** or reuse a command request as an event. A request expresses intent before processing; an event describes an outcome that has already happened and may be consumed by multiple subscribers.

## 3. Command RPC Lifecycle

A command is usually called via a unary RPC because the client needs to send one request and receive the outcome of that exact request:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as InventoryService
    participant D as Domain / database
    C->>S: ReserveStock(command)
    S->>S: Authenticate and check permissions
    S->>D: Check inventory, reserve stock
    alt Accepted
        D-->>S: Reservation recorded
        S-->>C: ReserveStockResponse
        S-->>C: status OK
    else Insufficient inventory
        D-->>S: Business rejection
        S-->>C: status FAILED_PRECONDITION
    end
~~~

The server should distinguish:

- **Protocol/input errors:** e.g., missing **product_id**, use **INVALID_ARGUMENT**.
- **Unmet business preconditions:** e.g., insufficient inventory, use **FAILED_PRECONDITION** or return a structured rejection result if that is a normal domain outcome.
- **Unauthorized:** use **PERMISSION_DENIED**.
- **Transient infrastructure errors:** use **UNAVAILABLE** when appropriate.

Do not return **OK** with a success-looking response when the command was actually rejected. If rejection is a normal business outcome that the client must handle directly, the schema can explicitly represent **accepted**, **rejection_reason**, or a status enum. When using gRPC status, the client must inspect the status to know the command did not succeed.

### Retrying Commands Safely

A client may resend a command after a timeout or connection drop, even though the server may have already performed the operation before the response was lost. An **idempotency_key** helps the server recognize duplicate requests and return the previously recorded outcome instead of reserving inventory a second time.

Idempotency policies must be enforced at the business/storage layer; simply adding a field to Protobuf does not automatically prevent duplicate execution. Define key scope, retention duration, handling of the same key with a different payload, and atomicity between updating state and saving the command result.

## 4. Event Notification Lifecycle

Event notification does not ask the consumer to issue state-changing commands. The consumer subscribes and receives events as they happen:

~~~mermaid
sequenceDiagram
    participant C as Event consumer
    participant S as InventoryService
    participant E as Event source
    C->>S: WatchStockEvents(product_id, after_sequence)
    S->>E: Register subscription
    E-->>S: StockReserved(sequence=41)
    S-->>C: StockEvent 41
    E-->>S: StockReleased(sequence=42)
    S-->>C: StockEvent 42
    Note over C,S: Stream continues until cancelled, errored, or completed
~~~

**WatchStockEvents** uses **server streaming** because the client sends one subscription request while the server sends multiple events. The client can process each event as it arrives rather than waiting for an entire history.

An event notification must carry enough information for the consumer to:

1. Identify the event via **event_id**.
2. Identify the affected entity via **product_id**.
3. Verify ordering or detect gaps via **sequence**.
4. Know the event type and content via **oneof payload**.
5. Know when the event occurred via **occurred_at**.

Never assume events always arrive exactly once or that consumers are always online. If replay, resumption, or guaranteed delivery is required, the server needs a persistent event store and an explicit cursor/sequence protocol. An open gRPC stream by itself is not a durable event queue.

## 5. Commands and Events Can Use Different RPC Types

| Need | Usually Suitable RPC Type | Reason |
| --- | --- | --- |
| Send one command and receive the processing outcome | **Unary** | One request, one result |
| Subscribe to receive continuous events | **Server streaming** | One subscription, multiple notifications |
| Send a batch of commands and receive an aggregated report | **Client streaming** | Many requests, one final result |
| Send control signals and receive events/acks in the same session | **Bidirectional streaming** | Both directions exchange interleaved messages |

Do not equate **event** with **server streaming**. Event refers to data semantics; server streaming is a transport pattern for sending multiple response messages. An event can also be delivered via a message broker, webhook, server streaming, or another mechanism depending on architecture.

Similarly, a command does not always have to be unary. A batch command-upload API can use client streaming, yet each item remains a command if it expresses a request to perform an action. The RPC type should be chosen based on cardinality and exchange timing; command/event describes business semantics.

## 6. Event Notification Is Not a Durable Event Bus

A **WatchStockEvents** method keeps an RPC open and emits events to a connected client. It **does not automatically provide**:

- Durable event storage for replay after a client goes offline.
- Fan-out to multiple consumers with independent offsets.
- Exactly-once delivery or automatic duplicate-processing prevention.
- Consumer processing acknowledgments and event commits.
- Retention, dead-letter queues, or durable retry policies.

If the system requires these capabilities, use an event log or an appropriate message broker as the source of truth; gRPC can serve as the streaming API for clients. If only direct notifications to an online client are needed, server streaming may suffice.

A common deployment pattern:

1. A command is processed and updates domain state.
2. The corresponding event is durably persisted in the same transaction or via a **transactional outbox**.
3. A publisher reads the outbox/event log and emits to subscribers or a broker.
4. gRPC server streaming delivers events to online consumers.
5. Consumers store processed **event_id/sequence** values and use a cursor to resume on reconnect.

The transactional outbox helps avoid updating the database without emitting the event if the process crashes between the two steps. It does not automatically guarantee end-to-end exactly-once processing; consumers still must handle duplicates safely.

## 7. Designing Clear Contracts and Names

Command names typically use imperative verbs:

- **ReserveStock**
- **ReleaseReservation**
- **CancelOrder**
- **ApprovePayment**

Event names typically describe what happened:

- **StockReserved**
- **ReservationReleased**
- **OrderCancelled**
- **PaymentApproved**

Subscription method names can use **Watch...** or **Subscribe...**, such as **WatchStockEvents**. A subscription request contains filter criteria and a cursor, and should not contain state-changing commands.

Key principles:

- Events should be **immutable**: once published, do not alter the meaning of past events.
- Include a stable **event_id** for deduplication.
- Include a per-aggregate sequence/version if detecting missing or out-of-order events is needed.
- Distinguish **occurred_at** (when the domain event occurred) from when the consumer receives the event.
- Do not pack sensitive data or unnecessary fields into event payloads.
- When evolving event schemas, follow Protobuf compatibility rules: never reuse removed field numbers; use **reserved** when needed.

## 8. Security, Deadlines, and Error Handling

Both commands and events require authentication, authorization, and observability:

- **Command:** verify the caller has permission to perform the action on the target resource. Set deadlines based on the operation's budget and use idempotency on retries.
- **Event subscription:** verify which products/tenants the caller is allowed to watch; enforce appropriate concurrent stream limits and lifetimes.
- **Metadata/interceptors:** carry identity, request ID, and trace context at the RPC level; do not use metadata as a substitute for per-message event data.
- **TLS/mTLS:** protect data in transit and authenticate peers according to deployment requirements.

With server streaming, a client may receive some events and then encounter **UNAVAILABLE** or **DEADLINE_EXCEEDED**. On reconnect, the client should use **after_sequence** or a saved cursor to resume; the server must define behavior when the cursor is too old or events are outside retention.

With commands, a timeout does not prove the operation did not occur. The client should query status by idempotency key or resend with the same key per server policy, never generating a new key for the same uncertain action.

## 9. Testing Commands and Events Separately

Command tests must verify **business side effects and outcomes**:

- A valid command creates the expected reservation.
- A command failing preconditions returns the expected rejection status/result.
- Resending the same idempotency key does not create duplicate reservations.
- An unauthorized caller is rejected.

Event tests must verify **content, ordering, and subscription lifecycle**:

- Consumers receive events after domain changes are committed.
- **event_id** and **sequence** are stable and never reordered within the guaranteed scope.
- Cancelling the stream releases the subscription.
- Disconnecting and resuming does not miss events within the retention policy.
- Consumers handle duplicate events without repeating side effects.

You can use gRPC in-process to test stubs and server streaming, but integration tests against a real store or event publisher are needed to verify transactional outbox, replay, and resumption. Unit tests calling command handler functions directly do not prove events are emitted at the right time.

## 10. Summary and Self-Check

A **command** is an intent requesting a state change; an **event notification** is information about a fact that has occurred. A command commonly uses a unary RPC to receive its outcome, while an event subscription commonly uses server streaming to receive multiple notifications. Nevertheless, command/event semantics are independent of RPC cardinality.

Self-check:

1. How do **ReserveStock** and **StockReserved** differ in timing and semantics?
2. Why does **WatchStockEvents** use server streaming while events themselves are not synonymous with streaming?
3. A client hits a timeout calling **ReserveStock**: why can it not conclude the server did not reserve stock?
4. Why can an open gRPC stream not replace an event log or durable message broker?
5. Which fields help consumers deduplicate and resume events after losing a connection?

Designing a clean boundary between **requesting execution** and **notifying what happened** keeps Spring gRPC contracts intuitive, makes retries safer, and supports multiple consumers without mixing command responsibilities with event distribution.
