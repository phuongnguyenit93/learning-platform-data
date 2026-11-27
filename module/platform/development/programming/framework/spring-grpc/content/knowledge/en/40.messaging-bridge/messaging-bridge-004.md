# Returning a Response Before or After Publishing

## 1. Response Timing Determines What the RPC Guarantees

In **SPRING_GRPC**, clients invoke RPCs according to a Protocol Buffers contract against a Spring service. An RPC may execute a use case and then emit an event or command to a message broker for consumers to continue processing. In this case, the moment the server returns its response directly affects what the client is allowed to conclude.

Three milestones must be distinguished:

- **Durably recorded:** the command or outbox record has committed to the database.
- **Published and broker-acknowledged:** the broker has received the message under the configured durability policy.
- **Business-processed:** a consumer has executed the use case and committed the result.

A response before publishing can mean the system has recorded the command for dispatch. A response after publishing can mean the broker has confirmed the message. Neither automatically means the consumer has finished processing.

Design the response around the milestone the API actually guarantees. For example:

| Response state | Meaning |
|---|---|
| `ACCEPTED` | The system has accepted responsibility for processing under the published durability contract |
| `PUBLISHED` | The broker has confirmed receipt of the message per producer/cluster configuration |
| `COMPLETED` | The business use case has finished and the result has committed |
| `REJECTED` | The request was rejected before being accepted for processing |

Do not use a single generic `SUCCESS` status for every milestone. Clients need to know whether they can display "accepted", "sent to broker", or "completed".

## 2. Responding Before Publishing: Safe Only When the Intent Is Durably Saved

If the server returns a response before the broker receives the message, clients can get faster responses and the RPC does not have to wait on the broker. However, distinguish two approaches:

1. **Return immediately and try to publish afterward:** unsafe for important commands. The process can crash after the response and before sending the message; the system promised to handle the work but no longer has the data to do so.
2. **Commit the command receipt and outbox first, return the response, then relay-publish:** much safer. The database has durably stored the dispatch intent in the same transaction; the broker can receive the message afterward.

Outbox flow:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC adapter
    participant U as Use case
    participant DB as Database
    participant R as Outbox relay
    participant B as Broker
    C->>G: SubmitCommand
    G->>U: execute(command)
    U->>DB: Save receipt + outbox
    DB-->>U: Commit
    U-->>G: Operation accepted
    G-->>C: OK / ACCEPTED + operationId
    R->>DB: Read pending outbox
    R->>B: Publish message
    B-->>R: Acknowledgement
    R->>DB: Mark published
~~~

The response is returned after the transaction commits, but before the relay publishes. Therefore, `ACCEPTED` must be defined as "durably recorded for dispatch". It must not be described as "broker received" or "consumer processed".

If the database commit fails, the outbox record does not exist either and the ingress must not return `ACCEPTED`. If the process crashes after commit, the relay can resume from the outbox when the application recovers.

## 3. Responding Before Publishing Without an Outbox Is Fire-and-Forget

A deceptively simple implementation:

~~~java
CompletableFuture<SendResult<String, CreateOrderCommand>> send =
        kafkaTemplate.send("orders.commands", command.commandId(), command);

observer.onNext(SubmitOrderReply.newBuilder()
        .setCommandId(command.commandId())
        .setState("ACCEPTED")
        .build());
observer.onCompleted();
~~~

This snippet returns the response as soon as `send(...)` returns a future, without waiting for broker acknowledgement. The future can fail after the RPC has already ended. Without a durable outbox or another durable queue, the command can be lost while the client already received `ACCEPTED`.

Fire-and-forget is only appropriate when message loss is acceptable under product requirements, or when another durable mechanism has already taken responsibility for persisting and retrying. Do not use "called the send function" as proof that a message was received.

## 4. Responding After Publishing: Waiting for Broker Acknowledgement

If the API needs to guarantee that the broker has received the message, the ingress can wait for the producer future to complete before returning the response:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as gRPC ingress
    participant B as Message broker
    C->>G: SubmitCommand
    G->>B: Publish message
    B-->>G: Broker acknowledgement
    G-->>C: OK / PUBLISHED
~~~

In Spring Kafka 3.x, `KafkaTemplate.send(...)` returns a `CompletableFuture<SendResult<K,V>>`. The adapter can register a callback instead of blocking the RPC thread:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    CreateOrderCommand command = mapper.toCommand(request);
    Context rpcContext = Context.current();

    try {
        kafkaTemplate.send(
                "orders.commands",
                command.commandId(),
                command)
            .whenComplete((result, failure) ->
                rpcContext.run(() -> {
                    if (rpcContext.isCancelled()) {
                        return;
                    }
                    if (failure != null) {
                        observer.onError(Status.UNAVAILABLE
                                .withDescription("Broker publish was not confirmed")
                                .asRuntimeException());
                        return;
                    }

                    observer.onNext(SubmitOrderReply.newBuilder()
                            .setCommandId(command.commandId())
                            .setState("PUBLISHED")
                            .build());
                    observer.onCompleted();
                }));
    } catch (RuntimeException ex) {
        observer.onError(Status.UNAVAILABLE
                .withDescription("Unable to submit message")
                .asRuntimeException());
    }
}
~~~

This is an illustrative skeleton. You need to configure the appropriate serializer, topic, producer timeout, acknowledgement, security, and callback executor. The callback must emit exactly one terminal signal; do not call `onNext` or `onCompleted` after `onError`.

Do not block the Netty/gRPC event loop with `future.get()`. If using a blocking API, offload waiting to a dedicated bounded executor. When callbacks must run under the gRPC context, explicitly manage capturing/restoring the context; do not assume every ThreadLocal propagates automatically across executors.

## 5. Broker Acknowledgement Does Not Mean Consumer Processed

A response after publishing can only guarantee what the producer/broker confirmed:

- The producer sent the message and received acknowledgement per configuration.
- The broker may have written the message per the replication/durability policy.
- Consumers may not have received, processed, or succeeded in processing it yet.

With Kafka, durability depends on settings such as `acks=all`, replication factor, and `min.insync.replicas`, as well as cluster health. With RabbitMQ, consider publisher confirms, durable queues, persistent messages, and the corresponding replication configuration.

The state name `PUBLISHED` should have a clear definition in the API: the broker has confirmed the message, not that consumers have committed side effects. If you need to know when the consumer finishes, provide an operation status, reply channel, or dedicated result event.

## 6. Comparing the Two Response Approaches

| Criterion | Return after durable outbox commit, before broker publish | Return after broker acknowledgement |
|---|---|---|
| Response condition | Database transaction saving receipt + outbox succeeds | Producer receives acknowledgement |
| RPC latency | Typically lower and less dependent on the broker | Depends on broker latency |
| Temporary broker outage | Can still return `ACCEPTED`; outbox pending | May return error/timeout |
| Message loss after response | Outbox preserves dispatch intent durably | Depends on broker/producer durability and retries |
| Response meaning | Recorded for dispatch | Broker confirmed message receipt |
| Consumer processed? | Not guaranteed | Not guaranteed |
| Components to operate | Database, outbox relay, broker | Producer, broker, and often still outbox if DB state exists |

There is no single right choice for every API. Choose based on what the client needs to know and how much dependency the RPC can accept. For important commands that mutate a database, an outbox is usually the reliable foundation; whether the response waits for the broker is an additional contract decision.

## 7. Failure Windows When Waiting for Publish Acknowledgement

Waiting for broker acknowledgement increases confidence in publishing, but creates scenarios that must be handled:

| Scenario | What the ingress knows | How to handle |
|---|---|---|
| Broker ack succeeds | Broker confirmed message receipt | Can return `PUBLISHED` |
| Broker explicitly rejects before accepting | Publish failed | Return appropriate error or retry per policy |
| Timeout before ack | Uncertain whether broker received it | Treat as uncertain outcome; retry with the same idempotency key |
| Broker ack succeeds, response is lost | Message was received, but client does not know | Client retries with same key or queries operation |
| Client cancels while publish is pending | RPC no longer needs a response | Do not assume message was recalled; determine state via idempotency/receipt |

A timeout does not prove the broker did not receive the message. The connection may drop after the broker writes the message but before the acknowledgement reaches the producer. Returning `UNAVAILABLE` or `DEADLINE_EXCEEDED` in this situation must not cause the client to create a new intent.

## 8. Database State and Broker Publish: Avoiding Dual-Write

If a use case commits business data and then publishes directly:

~~~text
Database commit
      |
      +---- process crashes ----> event never sent
      |
      v
Publish to broker
      |
      +---- broker ack lost ----> producer unsure of outcome
~~~

Waiting for publish to finish before returning the gRPC response does not eliminate the dual-write gap. The database can commit successfully while broker publishing fails. If an error is returned, the client may assume the business action did not happen and resend it.

A transactional outbox writes business state and the event record in the same database transaction. The relay publishes after commit and marks the record after acknowledgement. If the relay crashes after broker ack but before marking published, the message may be sent again; consumers must be idempotent.

If the API responds before broker publish, the response rests on the outbox commit. If the API responds after broker publish, it can wait for relay/broker confirmation, but it must still keep an operation receipt and idempotency to resolve uncertain outcomes.

## 9. Idempotency Is Mandatory When Responses Can Be Lost

Clients only observe outcomes over the network. The server may have committed the outbox or the broker may have received the message while the response never reached the client. Retries must therefore express the same intent:

1. The client generates an idempotency key for the business operation.
2. Every retry sends the same key and the same logical payload.
3. The ingress stores a mapping `(tenantId, idempotencyKey)` to `operationId`/`commandId`.
4. If a repeated request has the same payload, return the existing operation and its current status.
5. If the key matches but the payload differs, return a conflict per the API contract.
6. Consumers deduplicate by command/event ID before side effects.

Do not generate a new `operationId` every time the client retries. Nor should you rely solely on Kafka's idempotent producer: that feature does not replace end-to-end idempotency across the client, ingress, database, and consumer.

## 10. Designing a Response Contract with an Operation ID

For asynchronous processing, the response should provide a stable ID for the client to query:

~~~proto
message SubmitOrderReply {
  string operation_id = 1;
  OperationState state = 2;
}

enum OperationState {
  OPERATION_STATE_UNSPECIFIED = 0;
  ACCEPTED = 1;
  PUBLISHED = 2;
  PROCESSING = 3;
  COMPLETED = 4;
  REJECTED = 5;
}

message GetOperationRequest {
  string operation_id = 1;
}

message GetOperationReply {
  OperationState state = 1;
  string result_reference = 2;
  string failure_code = 3;
}
~~~

The enum and state names are API examples. Only expose states the system can determine reliably. `PUBLISHED` should be updated after broker acknowledgement; `COMPLETED` should be based on committed consumer results. Do not transition to `COMPLETED` merely because a consumer began processing.

Operation status can be stored in a database or built from an event/status store. Define retention periods, per-tenant access permissions, and handling for nonexistent operations.

## 11. Deadlines and Client Wait Times

A gRPC deadline bounds the RPC duration, not the duration a command spends in the broker/consumer. For example:

~~~text
RPC deadline: 700 ms
  Authentication + validation: 20 ms
  Persist outbox: 15 ms
  Return ACCEPTED

After response:
  Relay publish: 40-500 ms (may retry)
  Consumer processing: several seconds
  Operation status: COMPLETED or REJECTED
~~~

If the API chooses to return after broker acknowledgement, the producer wait time must fit within the deadline budget. Do not set a producer timeout much longer than the remaining RPC deadline.

When the client deadline expires, the server may receive cancellation, but already-committed transactions or messages received by the broker do not automatically roll back. If work needs to be cancelled, design a dedicated cancellation command and check status/race conditions. RPC cancellation only terminates the current interaction.

## 12. Waiting for Consumer Completion: Request/Reply Is a Different Contract

Some APIs need to return the final business result in the same RPC. In that case, the ingress can:

1. Publish the command with a correlation ID and reply destination.
2. The consumer processes the command.
3. The consumer sends a reply containing the correlation ID and result.
4. The ingress matches the reply with the waiting RPC and returns the response.

This model can fit short, time-bounded processing with moderate throughput. However:

- The RPC connection is held open while the consumer processes.
- The deadline must cover broker, queue wait, consumer, and reply.
- The ingress must manage pending requests, timeouts, cancellations, and late replies.
- If the ingress restarts, pending correlation state can be lost unless durably persisted.
- Consumers still need idempotency when commands are resent.

For long workflows, returning `ACCEPTED` with an operation ID and letting clients query status is usually easier to operate than holding an RPC open for tens of seconds or minutes.

## 13. Mapping Errors by Response Milestone

Status codes must align with what the server knows:

| Scenario | Recommended response |
|---|---|
| Invalid request | `INVALID_ARGUMENT` |
| Caller not authorized to send command | `PERMISSION_DENIED` |
| Insufficient quota/in-flight capacity | `RESOURCE_EXHAUSTED` |
| Outbox transaction rollback | `INTERNAL` or persistence error status per API policy; do not return `ACCEPTED` |
| Outbox commit succeeds | `OK` response with state `ACCEPTED` |
| Broker ack succeeds | `OK` response with state `PUBLISHED` |
| Broker explicitly rejects | `UNAVAILABLE` or defined status |
| Publish timeout, uncertain outcome | `DEADLINE_EXCEEDED`/`UNAVAILABLE` with operation/idempotency lookup |
| Consumer business processing fails after acceptance | Update operation to `REJECTED` or failure state; do not rewrite acceptance history as never received |

Do not use gRPC status codes to represent every state of a long-running workflow. The RPC status describes the outcome of the call; the operation state describes business progress after the request has been accepted.

## 14. Testing Responses Before and After Publishing

Tests must verify the exact milestone the response guarantees:

| Scenario | Pre-publish response with outbox | Post-broker-ack response |
|---|---|---|
| Database commit succeeds | Returns `ACCEPTED` | Does not return until publish is confirmed |
| Database rollback | Does not return `ACCEPTED` | Does not return `PUBLISHED` |
| Broker temporarily down | Can still return `ACCEPTED`; outbox pending | Returns error/timeout per policy |
| Broker ack succeeds | Operation transitions to `PUBLISHED` afterward | Returns `PUBLISHED` |
| Ack lost after broker receipt | Relay retries; consumer idempotent | Client retries with same key; no new operation created |
| Response lost after commit/ack | Retry returns same operation ID | Retry returns same operation ID |
| Client cancels before response | Durable intent still follows policy if committed | Publish may have succeeded; do not assume cancel recalls message |
| Consumer processing fails | Operation transitions to failure/rejected | Operation transitions to failure/rejected |
| Consumer processing finishes | Operation transitions to `COMPLETED` | Operation transitions to `COMPLETED` |

Integration tests should use a real or containerized database and broker to verify commits, acknowledgements, retries, and redelivery. Mocking the producer only verifies that code calls `send`, not durability or broker outcomes.

## 15. Metrics and Diagnostics

Track each milestone separately:

- RPC latency and status codes by method.
- Transaction commit time and pending outbox record count.
- Oldest pending outbox record age and relay retry count.
- Producer acknowledgement latency, timeouts, and send failures.
- Operation counts in `ACCEPTED`, `PUBLISHED`, `PROCESSING`, `COMPLETED`, `REJECTED`.
- Duration from acceptance to publish and from publish to completion.
- Retry/idempotency hits, consumer duplicates, and dead-letters.
- Client cancellations and deadlines exceeded.

If a client receives `ACCEPTED` but does not see the event, inspect pending outbox records, relay, and broker. If a client receives `PUBLISHED` but the operation has not completed, inspect consumer lag, consumer group, retries, and dead-letter queue. These two states point to two different stages.

Do not use operation ID or customer ID as high-cardinality metric labels. Put those IDs in logs/traces; metrics should group by method, event type, topic, status, and consumer.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `ACCEPTED` immediately after calling `send` | Future may fail after response | Wait for durable outbox commit or broker ack |
| Reporting `PUBLISHED` when consumer has not processed | Client misinterprets business state | Separate `PUBLISHED` and `COMPLETED` |
| Waiting for broker without idempotency | Ack can be lost and retry creates duplicates | Use stable operation ID/idempotency key |
| Waiting for publish on event loop | Blocks other RPC processing | Use callbacks or a bounded executor |
| Publishing directly after DB commit | Dual-write can lose events | Use a transactional outbox |
| Treating timeout as proof broker did not receive | Retry can create a new command | Handle uncertain outcome with the same key |
| Treating gRPC cancellation as rollback | Already-committed message still processed by consumer | Separate RPC cancellation from command cancellation |
| Holding RPC open for long workflows | Ties up resources and risks exceeding deadlines | Return operation ID, provide a status API |
| Not persisting operation state | Client cannot learn outcome after lost response | Store receipts and status with retention |

**Key takeaway:** Returning a response before broker publishing is only safe when the command/outbox is durably persisted; in that case `ACCEPTED` means recorded for dispatch. Returning a response after publish acknowledgement lets you guarantee the broker received the message, but it does not prove consumer completion and may increase RPC latency. Use operation IDs and idempotency to handle lost responses or uncertain acknowledgements; use an outbox when database state and messages must stay consistent. Separate `ACCEPTED`, `PUBLISHED`, and `COMPLETED` into distinct milestones in the contract.
