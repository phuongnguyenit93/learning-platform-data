# gRPC as Ingress into a Message Flow

## 1. gRPC Receives Commands, Message Broker Continues Processing

In **SPRING_GRPC**, clients send RPCs according to a Protocol Buffers contract to a service running in a Spring application. A common way to organize this is to use gRPC as an **ingress**: authenticate the caller, validate the request, convert the request into a command, and send the command to a message broker for consumers to process asynchronously.

General flow:

~~~mermaid
flowchart LR
    C["gRPC client"] --> G["Spring gRPC ingress"]
    G --> V["Authenticate / validate"]
    V --> M["Map request to command"]
    M --> B["Message broker"]
    B --> W["Consumer / worker"]
    W --> D["Domain use case"]
    D --> E["Event / result store"]
    E --> Q["Query status / notification"]
    Q --> C
~~~

gRPC handles request/response communication at the system boundary. The broker decouples the time a command is accepted from the time business logic executes. As a result, the ingress can respond quickly once the command is durably accepted, while workers handle long-running tasks or independent retries.

This model fits tasks such as creating orders, processing payments, generating reports, sending notifications, or running multi-step workflows. It does not mean every RPC must go through a broker: queries that need immediate results and have short processing times can still call a use case synchronously.

## 2. Distinguishing Command Ingress from Event Publishing

A request from a client usually expresses a **command**: asking the system to perform an action. An **event** expresses something that has happened after the action was processed.

| Message | Meaning | When emitted |
|---|---|---|
| `CreateOrderCommand` | Request to create an order | When the ingress accepts the request |
| `OrderCreated` | The order was successfully created | After the create-order use case completes |
| `PaymentRequested` | Request to initiate payment processing | When the workflow decides payment is needed |
| `PaymentCaptured` | Payment was recorded | After the payment system confirms |

Do not emit `OrderCreated` immediately upon receiving `CreateOrderRequest`. At that moment, the order may not be created yet, inventory may not be reserved, and business checks may not be complete. The ingress should publish a command such as `CreateOrderCommand`; the worker only emits `OrderCreated` after the business transaction succeeds.

This distinction helps consumers understand their responsibilities properly and avoids signaling a success state too early to other systems.

## 3. Choosing the Response Type for gRPC Ingress

An ingress typically has three response types:

| Type | What does the gRPC response mean? | When appropriate |
|---|---|---|
| Accepted | The broker confirmed receipt of the command under the durability policy | Asynchronous work |
| Completed | The use case completed with a business result | Short, bounded work needing immediate results |
| Request/reply | The ingress sends a command and waits for a corresponding reply message | Consumer responds quickly, with a clear timeout |

For asynchronous processing, the response should return `command_id` or `operation_id`, state `ACCEPTED`, and information for querying progress. The client can call `GetCommandStatus` or subscribe to a separate RPC/notification to receive the result.

Do not return `SUCCESS` if the command was only sent to the broker. `ACCEPTED` means the system has taken responsibility for processing it; it does not assert that the command will succeed from a business perspective.

If using request/reply over a broker, you need a correlation ID, reply destination, deadline, and rules for handling late responses. Do not hold an RPC open indefinitely just to wait for a worker.

## 4. Acknowledgement Boundary: Broker Received vs. Consumer Processed

There are several different acknowledgement milestones:

1. The ingress received the request from the client.
2. The request passed authentication and validation.
3. The producer sent the message.
4. The broker confirmed the message according to the durability configuration.
5. The consumer received the message.
6. The use case committed the business result.
7. The result event was published.

An `ACCEPTED` response should correspond to milestone 4 if the contract guarantees that the command was durably accepted by the broker. It does not mean milestone 6 or 7 has occurred.

With Kafka, acknowledgement durability depends on producer and cluster configuration, such as `acks=all`, replication factor, and `min.insync.replicas`. Simply waiting on the future returned by `KafkaTemplate.send(...)` is not enough if the producer uses a weaker acknowledgement setting than the system guarantees. With RabbitMQ or other brokers, use publisher confirms and the corresponding durable queue/message settings.

If the broker does not confirm before the deadline, the ingress should not return `ACCEPTED`. It can return `UNAVAILABLE` or an appropriate status per the API policy. However, if the connection drops right when the broker has already received the message but the acknowledgement is lost, the ingress may not know for sure whether the message was stored. This is why idempotency is necessary.

## 5. Keeping Message Contracts Independent of Protobuf Requests

You should not default to serializing the raw protobuf request and publishing it directly to an internal topic. A gRPC request and a broker message can have different lifecycles, consumers, and compatibility requirements:

- A Protobuf RPC contract is designed for client-server communication.
- A command message is designed for consumers and workflows.
- The message may need a command ID, tenant, correlation ID, causation ID, schema version, and timestamp.
- Consumers may be implemented in different languages or with different schemas.

The ingress should map the request into a command envelope with a managed schema:

~~~json
{
  "messageId": "cmd-8f31",
  "messageType": "orders.create.v1",
  "schemaVersion": 1,
  "aggregateKey": "order-42",
  "correlationId": "req-7c20",
  "causationId": "api-call-91",
  "tenantId": "tenant-12",
  "occurredAt": "2026-11-19T10:15:30Z",
  "payload": {
    "customerId": "customer-9",
    "lines": [
      { "sku": "SKU-100", "quantity": 2 }
    ]
  }
}
~~~

This is an illustrative structure example; the actual payload can use Protobuf, Avro, JSON Schema, or a format standardized by your organization. `messageId` identifies the message, `correlationId` links steps of the same request/workflow, and `causationId` indicates which message caused the current message.

Establish clear schema versions and compatibility rules. Do not reuse deleted protobuf field numbers or change the meaning of existing fields. Consumers must handle new fields in a way that remains compatible with older messages.

## 6. Mapping a gRPC Request to a Command

Example ingress protobuf:

~~~proto
syntax = "proto3";

package orders.v1;

service OrdersIngress {
  rpc SubmitOrder(SubmitOrderRequest) returns (SubmitOrderReply);
  rpc GetCommandStatus(GetCommandStatusRequest)
      returns (GetCommandStatusReply);
}

message SubmitOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

message SubmitOrderReply {
  string command_id = 1;
  string state = 2;
}
~~~

The application command can be independent of generated classes:

~~~java
public record CreateOrderCommand(
        String commandId,
        String tenantId,
        String customerId,
        java.util.List<Line> lines,
        String idempotencyKey,
        String correlationId) {

    public record Line(String sku, int quantity) {}
}
~~~

The ingress mapper should validate required structure such as a non-empty customer ID, a bounded list of lines, and a valid idempotency key. Business rules such as whether the customer is allowed to place orders, whether a SKU is for sale, or whether the quantity is within limits must be re-verified by the consumer/use case at execution time.

Do not pass `StreamObserver`, `Metadata`, `ServerCall`, or generated protobuf requests into the consumer/domain layer. Those types belong to the transport boundary.

## 7. Example: Publishing a Command with Spring Kafka

The following example uses Spring Kafka 3.x, where `KafkaTemplate.send(...)` returns a `CompletableFuture`. The serializer for `CreateOrderCommand` needs to be configured appropriately for the system's message schema:

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.grpc.server.service.GrpcService;

import java.util.concurrent.CompletableFuture;

@GrpcService
public class OrdersIngressGrpcService
        extends OrdersIngressGrpc.OrdersIngressImplBase {

    private final KafkaTemplate<String, CreateOrderCommand> kafka;
    private final CommandMapper mapper;
    private final CommandIdentity identity;

    public OrdersIngressGrpcService(
            KafkaTemplate<String, CreateOrderCommand> kafka,
            CommandMapper mapper,
            CommandIdentity identity) {
        this.kafka = kafka;
        this.mapper = mapper;
        this.identity = identity;
    }

    @Override
    public void submitOrder(
            SubmitOrderRequest request,
            StreamObserver<SubmitOrderReply> observer) {

        final CreateOrderCommand command;
        try {
            command = mapper.toCommand(
                    request,
                    identity.commandIdFor(request.getIdempotencyKey()),
                    identity.tenantId(),
                    identity.correlationId());
        } catch (IllegalArgumentException ex) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid order request")
                    .asRuntimeException());
            return;
        }

        Context rpcContext = Context.current();
        try {
            CompletableFuture<?> publish =
                    kafka.send("orders.commands",
                            command.commandId(),
                            command);

            publish.whenComplete((result, failure) ->
                    rpcContext.run(() -> {
                        if (rpcContext.isCancelled()) {
                            return;
                        }
                        if (failure != null) {
                            observer.onError(Status.UNAVAILABLE
                                    .withDescription(
                                            "Command was not confirmed by the message broker")
                                    .asRuntimeException());
                            return;
                        }

                        observer.onNext(SubmitOrderReply.newBuilder()
                                .setCommandId(command.commandId())
                                .setState("ACCEPTED")
                                .build());
                        observer.onCompleted();
                    }));
        } catch (RuntimeException ex) {
            observer.onError(Status.UNAVAILABLE
                    .withDescription("Message broker is unavailable")
                    .asRuntimeException());
        }
    }
}
~~~

This is an illustrative skeleton for a unary ingress. You need to configure `KafkaTemplate` with the appropriate serializer, topic, producer acknowledgement, timeout, and security. `identity` must obtain the tenant/principal from the authenticated context; do not trust a self-declared `tenantId` from the caller.

The callback emits at most one response or one error for a unary RPC. If the client cancels the RPC before the callback runs, check for cancellation so you do not send a late response. Client cancellation does not guarantee that a message already sent to the broker will be recalled; once the broker has accepted the command, the workflow must proceed according to system policy.

## 8. Idempotency for Handling Retries at the Ingress

A client may retry when the response is lost or it receives `UNAVAILABLE`. However, the first send might have already been confirmed by the broker while the acknowledgement failed to reach the ingress. If the retry generates a new command ID, the same business request could be processed twice.

Idempotency design:

1. The client generates a stable idempotency key for a business intent.
2. Every retry of the same intent resends that exact key.
3. The ingress determines the tenant/principal and the scope of the key.
4. The system maps the pair `(tenant, idempotencyKey)` to a stable `commandId`.
5. The message consumer also deduplicates by `commandId` or business key before side effects.

The idempotency store must handle contention when two requests with the same key arrive concurrently. If the key matches but the payload differs, return a conflict or clear business error; do not silently treat two different payloads as the same command.

Kafka's idempotent producer handles duplicates at the producer/broker layer within the scope of the producer's configuration and session. It does not replace end-to-end idempotency across the client, ingress, consumer, and database.

## 9. Dual-Write and the Transactional Outbox

If the ingress both writes a command/receipt to the database and publishes a message, there is a dual-write risk:

~~~text
Database commit succeeds
        |
        v
Process crashes before publish
        |
        v
Receipt exists, but worker never receives the command
~~~

The reverse can also happen: the broker receives the message, but the database rolls back, causing the worker to process a command for which the ingress has no corresponding receipt.

**Transactional outbox** solves this problem by writing the command state and outbox record within the same database transaction:

~~~mermaid
flowchart TD
    A["gRPC ingress"] --> B["Database transaction"]
    B --> C["Command receipt"]
    B --> D["Outbox record"]
    D --> E["Outbox relay"]
    E --> F["Message broker"]
    F --> G["Consumer"]
    G --> H["Use case + idempotency"]
~~~

The relay reads the outbox and publishes the message; after the broker confirms, the record is marked sent or transitioned in state. The relay may re-publish after a crash, so the consumer must still be idempotent.

If the ingress only publishes a message and does not write business state/receipts to a database, an outbox may not be needed. However, when you need to store operation state, deduplication, or audit records in the database alongside emitting a message, design a clear transaction boundary.

With an outbox architecture, the API can define `ACCEPTED` at the point the database transaction commits successfully because the command and outbox record are durably stored for the relay to dispatch. In that case, `ACCEPTED` means **recorded for dispatch**, not necessarily that the broker has confirmed it yet. If the API must guarantee broker receipt, it must track relay status and only return the response after the corresponding acknowledgement. Document this milestone clearly in the contract and provide consistent operation status.

## 10. Delivery Semantics, Ordering, and Retries at the Consumer

In common messaging systems, a consumer may receive a message again if processing succeeds but the acknowledgement/offset commit is lost. Therefore, the default design should tolerate **at-least-once delivery**:

- The consumer checks whether `commandId` has already been processed.
- Writes the result and deduplication marker within an appropriate transaction.
- Commits the offset/ack only after processing reaches a safe milestone.
- Retries transient errors with backoff and a maximum retry limit.
- Routes unrecoverable failed messages to a dead-letter flow for investigation.

With Kafka, ordering is guaranteed within a single partition, not across the entire topic. Choose a message key based on the aggregate whose order must be preserved, such as `orderId`; commands for the same order will be routed to the same partition by the corresponding partitioner.

Ordering in a partition log does not automatically ensure side effects complete in order if the consumer processes records from the same partition concurrently. Configure the consumer to preserve processing order for that aggregate, or use version/sequence numbers and optimistic concurrency in the use case.

Do not assume commands for the same tenant are always processed sequentially if they land in different partitions. If business ordering is required, define the aggregate key, partitioning, and concurrency handling at the consumer.

Exactly-once at a single broker layer does not automatically create end-to-end exactly-once semantics. Side effects in databases or external systems still require transactions, idempotency, or appropriate coordination mechanisms.

## 11. Deadlines, Cancellation, and gRPC Responses

A gRPC deadline bounds how long the client waits on the ingress. It does not automatically bound the total time a command sits in the broker or is processed by a consumer:

~~~text
Client deadline: 800 ms
  Authentication + validation: 20 ms
  Publish + broker confirmation: 100 ms
  gRPC response: ACCEPTED

Consumer processing:
  may take several seconds or minutes
  -> updates command status
  -> emits OrderCreated or OrderRejected
~~~

If the broker does not confirm within the deadline, the ingress may time out even though the message was actually stored. Client retries must use the same idempotency key to avoid creating duplicate commands.

If the client cancels the RPC after the broker has received the message, cancellation only ends the gRPC interaction; it does not mean the command is cancelled. If business requirements allow cancelling a command, design a dedicated command such as `CancelOrderProcessing` or a stateful cancellation operation with race condition checks.

For request/reply, the deadline must cover publishing, waiting for the consumer, reply routing, and returning the response. Only use this model when processing time is bounded and keeping the RPC open is reasonable.

## 12. Status Codes at the Ingress

The ingress should map errors according to the failure milestone:

| Scenario | Recommended gRPC status |
|---|---|
| Malformed request or missing required fields | `INVALID_ARGUMENT` |
| Caller is unauthenticated | `UNAUTHENTICATED` |
| Caller is not authorized to send the command | `PERMISSION_DENIED` |
| Duplicate idempotency key with different payload | `ALREADY_EXISTS` or conflict status per API contract |
| Broker is unavailable or fails to confirm | `UNAVAILABLE` |
| Command intake quota exceeded | `RESOURCE_EXHAUSTED` |
| Ingress deadline expires before confirmation | `DEADLINE_EXCEEDED` |
| Command has been accepted | Successful response with state `ACCEPTED` |

Do not return `OK/ACCEPTED` before reaching the confirmation milestone promised by the API. Also, do not return `INTERNAL` for transient broker errors if the client can safely retry.

## 13. Security and Context Propagation

The ingress is a trust boundary. Before publishing a command:

- Authenticate credentials via an interceptor or security integration.
- Extract the principal and tenant from the verified identity.
- Check authorization to submit the command type and act on the resource.
- Limit payload size, number of lines, request rate, and tenant quotas.
- Do not publish access tokens, refresh tokens, or sensitive metadata to the broker.
- Include only the minimal claims needed by the consumer in the message; protect topic integrity and access permissions.

Correlation ID, trace context, tenant ID, and actor ID should be propagated via message headers/envelope by convention. If using W3C Trace Context, propagate `traceparent`/`tracestate` appropriately; do not rely solely on ThreadLocal since consumers run on different threads/processes.

Consumers should not trust an arbitrary `tenantId` in the payload if messages could be sent by other producers. Use broker ACLs, signatures, or trusted sources, and enforce data access checks at the consumer layer.

## 14. Backpressure and Ingress Protection

A broker can absorb bursts for a period, but that does not mean the system has infinite processing capacity. If the ingress accepts requests faster than consumers can process them, the backlog will grow, command completion times will lengthen, and data may exhaust storage.

Countermeasures:

- Limit concurrent RPCs and in-flight publishes awaiting acknowledgement.
- Set publish deadlines and producer timeouts.
- Limit message sizes and per-tenant request rates.
- Use quotas/admission control when backlog or broker latency exceeds thresholds.
- Return `RESOURCE_EXHAUSTED` when the ingress actively rejects requests due to overload.
- Monitor consumer lag and processing time to tune throughput.
- Do not hold an RPC open waiting for the backlog to drain.

If publish callbacks are slow, do not spawn unbounded threads. Use a bounded producer client and executor; avoid blocking the server event loop.

## 15. Testing gRPC Ingress and Message Flows

Tests must verify both the gRPC response and that the message was actually placed into the flow:

| Scenario | What to verify |
|---|---|
| Valid request | Command with the right schema, key, and correlation ID is published |
| Invalid request | Returns `INVALID_ARGUMENT`, nothing published |
| Unauthorized caller | Returns `PERMISSION_DENIED`, no command created |
| Broker confirms | Returns `ACCEPTED` with command ID |
| Broker rejects or times out | Does not return `ACCEPTED`; appropriate status |
| Broker received but ack lost | Retry with same idempotency key creates no duplicate operation |
| Two requests with same idempotency key | Same command ID, or conflict if payloads differ |
| Consumer receives duplicate message | Side effects do not repeat |
| Consumer succeeds | Status transitions to completed and result event is emitted properly |
| Consumer transient failure | Retry/backoff without losing the message |
| Consumer permanent failure | Dead-letter flow allows investigation |
| Client cancels after broker ack | Command still follows accepted policy; no late response sent |
| Different tenants | No data leakage and partitioning/key policy is correct |

Use a test broker or containerized broker for integration tests. Mocking `KafkaTemplate` only verifies that the adapter calls the producer; it does not prove durability, publisher acknowledgement, partition ordering, or redelivery.

## 16. Metrics and Diagnostics

Monitor the ingress and consumer separately:

- RPC request rate, status codes, and latency at the ingress.
- Time from receiving a request to broker acknowledgement.
- Number of pending publishes, timeouts, and send failures.
- Message rate, broker errors, and producer retries.
- Consumer lag, backlog age, and processing latency.
- Counts of accepted, completed, rejected, and dead-lettered commands.
- Duplicate/idempotency hit rate.
- Time from `ACCEPTED` to final outcome.
- Trace/correlation ID end-to-end across gRPC → broker → consumer.

If a client receives `ACCEPTED` but sees no outcome, check broker acknowledgement, topic/partition, consumer group, lag, dead-letter queue, and command status. Do not infer that the consumer has processed the command merely from the ingress returning success.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `ACCEPTED` immediately on calling producer | Message may not yet be confirmed by broker | Wait for publisher acknowledgement per durability policy |
| Emitting completion event before use case runs | Other systems believe business work succeeded prematurely | Publish command at ingress; event after commit |
| Serializing raw gRPC request into topic | Consumer couples to transport contract | Map to a dedicated message schema |
| Generating a new command ID on every retry | One intent may execute multiple times | Stable idempotency key |
| Assuming broker exactly-once protects database side effects | Consumer can still perform duplicate work | Deduplicate and use transactions at the consumer |
| Writing database and publishing separately | Dual-write loses or emits orphaned messages | Transactional outbox |
| Waiting indefinitely on consumer in RPC | Holds connections/threads and exceeds deadlines | Return receipt and provide a status API |
| Trusting client-supplied tenant ID | Possible cross-tenant access | Derive tenant from authenticated principal |
| No limits on backlog or in-flight publishes | Memory and broker become overloaded | Admission control, quotas, and backpressure |

**Key takeaway:** Use gRPC as an ingress to authenticate, validate, and convert requests into commands; only return `ACCEPTED` after the published durability milestone: broker acknowledgement or transactional outbox commit. Consumers execute the use case and emit result events after business logic completes. Keep message contracts independent of protobuf requests, use end-to-end idempotency, use a transactional outbox when dual-writing, propagate correlation/trace context, and bound the backlog. RPC deadlines/cancellations do not automatically cancel commands already accepted by the broker or recorded in the outbox.
