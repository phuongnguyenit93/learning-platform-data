# Async Reply from Messages Back to gRPC

## 1. Pairing Request/Reply with Message Processing

In **SPRING_GRPC**, clients invoke RPCs according to a Protocol Buffers contract against a Spring service. Some use cases need to run on a worker via a message broker while still returning the business result within the same RPC. The ingress sends a command, holds the RPC open for a bounded duration, receives a reply message from the consumer, and converts the reply into a protobuf response.

This flow is commonly called **asynchronous request/reply**:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as gRPC ingress
    participant B as Message broker
    participant W as Worker / consumer
    C->>G: SubmitOrder(request)
    G->>G: Register pending reply
    G->>B: Publish command + correlation + replyTo
    B->>W: Deliver command
    W->>W: Execute use case
    W->>B: Publish reply(correlationId)
    B->>G: Deliver reply
    G->>G: Complete pending future
    G-->>C: SubmitOrderReply
~~~

RPCs and messages have different lifecycles. gRPC is a call with a deadline and cancellation; messages can be retried, redelivered, or processed after the client has stopped waiting. The ingress must manage the link between these two lifecycles using a correlation ID and a pending-reply registry.

## 2. When Should You Use Asynchronous Reply?

This model fits when a consumer needs to process asynchronously yet completion time remains relatively short and bounded—for example, calling a specialized worker, integrating a legacy service via a broker, or performing a computation step and returning the result immediately in the same request.

Do not hold an RPC open for long workflows, queues that can build deep backlogs, or tasks involving human steps. For those cases, return `ACCEPTED` with an `operationId`, then provide a status-query RPC or a dedicated notification mechanism. Holding an RPC open for a long time consumes connections, pending state, and server resources throughout the wait.

## 3. Correlation ID Matches Replies to the Right RPC

The ingress creates a dedicated correlation ID for the request/reply exchange and includes it in the command message. The worker must copy that ID into the reply:

~~~text
gRPC call A
  correlationId = corr-A
  command       = cmd-100
  replyTo       = orders.reply.instance-2

Worker reply
  correlationId = corr-A
  commandId     = cmd-100
  result        = ACCEPTED_BY_DOMAIN
~~~

The correlation ID identifies the request/reply pair. It is not necessarily the `operationId` or idempotency key:

| ID | Role |
|---|---|
| `correlationId` | Matches the reply to the waiting RPC |
| `operationId` / `commandId` | Identifies a business intent stably across retries |
| `messageId` | Identifies a specific command or reply message |
| `causationId` | Points to the message that caused the reply |
| `traceId` | Connects spans of a distributed trace |

If the client retries the same intent, `operationId` and the idempotency key should stay the same. Each RPC attempt can use a new correlation ID because each attempt has its own pending future. Replies arriving from an earlier attempt must be handled per policy, not mismatched onto the new RPC.

## 4. The Message Contract Needs a Reply Destination

The command must carry enough information for the worker to send back a reply:

~~~json
{
  "messageId": "msg-100",
  "messageType": "orders.submit.v1",
  "schemaVersion": 1,
  "commandId": "cmd-100",
  "correlationId": "corr-A",
  "replyTo": "orders.reply.instance-2",
  "tenantId": "tenant-12",
  "deadlineAt": "2026-11-19T10:15:35Z",
  "payload": {
    "customerId": "customer-9"
  }
}
~~~

The reply message should return the correlation ID and command reference:

~~~json
{
  "messageId": "reply-501",
  "messageType": "orders.submit.reply.v1",
  "correlationId": "corr-A",
  "causationId": "msg-100",
  "commandId": "cmd-100",
  "outcome": "ACCEPTED_BY_DOMAIN",
  "failureCode": ""
}
~~~

`replyTo` must be a destination permitted by the system, not accepted arbitrarily from the caller, to avoid turning the worker into a publisher that can send messages to any topic/queue. `deadlineAt` expresses the contractual processing/waiting deadline; do not confuse it with the broker automatically expiring the message.

## 5. Pending-Reply Registry

The ingress needs a registry mapping correlation IDs to waiting futures. The registry must:

- Register the future **before publishing the command**, because the worker may respond very quickly.
- Reject duplicate correlation IDs that are already pending.
- Enforce timeouts and cap the number of waiting requests.
- Remove the entry on completion, error, timeout, or cancellation.
- Handle late replies or replies with no matching entry.

Simple example using `ConcurrentHashMap` and `CompletableFuture`:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

public final class PendingReplyRegistry {
    private final ConcurrentMap<String, CompletableFuture<OrderReply>> pending =
            new ConcurrentHashMap<>();

    public CompletableFuture<OrderReply> register(
            String correlationId,
            Duration timeout) {

        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        CompletableFuture<OrderReply> future = new CompletableFuture<>();
        if (pending.putIfAbsent(correlationId, future) != null) {
            throw new IllegalStateException("correlation ID is already pending");
        }

        future.orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS);
        future.whenComplete((reply, failure) ->
                pending.remove(correlationId, future));
        return future;
    }

    public void complete(String correlationId, OrderReply reply) {
        CompletableFuture<OrderReply> future = pending.get(correlationId);
        if (future == null || !future.complete(reply)) {
            recordUnmatchedReply(correlationId);
        }
    }

    public void fail(String correlationId, Throwable failure) {
        CompletableFuture<OrderReply> future = pending.get(correlationId);
        if (future != null) {
            future.completeExceptionally(failure);
        }
    }

    private void recordUnmatchedReply(String correlationId) {
        // Bounded metrics/logging; do not use correlationId as a metric label.
    }
}
~~~

`orTimeout` has been available since Java 9. This is a single-instance skeleton; a production registry needs capacity limits, metrics, and shutdown behavior. `CompletableFuture.complete(...)` is thread-safe under contention: only one of reply, timeout, cancellation, or publish failure can complete the future first.

Do not hold pending futures indefinitely. If the ingress restarts, the in-memory map is lost; the client also cannot keep waiting on the old RPC. If results must survive restarts, persist operation status durably and use an operation API rather than treating the pending map as a business state store.

## 6. Register First, Publish Second

The order of these two operations matters:

~~~text
1. Generate correlationId
2. Create pending future in registry
3. Publish command with correlationId and replyTo
4. Worker receives command and publishes reply
5. Reply listener finds future and completes it
6. gRPC adapter maps reply to protobuf response
~~~

If you publish first and register the future afterward, the worker might reply before the registry has an entry. The reply would then be treated as unmatched and the RPC would wait until timeout even though the result already arrived.

When the producer reports an error, complete the future exceptionally so the adapter returns an appropriate status. If the broker received the message but the acknowledgement was lost, the publish outcome is uncertain; client retries must use a stable idempotency key so duplicate side effects are not created.

## 7. Reply Listener Completes the Pending Future

The reply consumer reads the correlation ID from the envelope or broker header, verifies the reply type, and converts the payload into an application reply:

~~~java
@KafkaListener(
        topics = "orders.reply.instance-2",
        groupId = "orders-reply-instance-2")
public void onReply(ConsumerRecord<String, OrderReplyMessage> record) {
    String correlationId = readCorrelationId(record.headers());
    OrderReply reply = replyMapper.toApplicationReply(record.value());
    pendingReplyRegistry.complete(correlationId, reply);
}
~~~

This snippet illustrates a listener for one ingress instance with its own reply topic and consumer group. In deployment, the topic/group must be provisioned per instance identity or mapped through an equivalent partitioning scheme. This is a critical architectural requirement when scaling multiple instances; sharing one topic and one consumer group can deliver replies to the wrong instance.

A reply with no waiting entry may be a late reply, a duplicate, or misrouted to the wrong instance. Record controlled metrics and logs; do not create a new future just because an unexpected reply arrived. If late replies need to update operation status, persist the result by `operationId` in a durable store.

## 8. Routing Replies Across Multiple Ingress Instances

Suppose there are three gRPC instances, each holding an in-memory pending registry:

~~~text
Ingress A: pending {corr-A}
Ingress B: pending {corr-B}
Ingress C: pending {corr-C}
~~~

If the reply topic shares a single consumer group, the broker may deliver the `corr-A` reply to the listener on Ingress B. B has no matching future and cannot complete the RPC waiting on A.

Common routing strategies:

| Approach | How it works | Notes |
|---|---|---|
| Per-instance reply destination | Each ingress instance has its own reply topic/queue; command carries `replyTo` | Easy routing; requires destination lifecycle management |
| Per-instance partitioning | Reply key/partition is pinned to the instance owning the pending request | Must guarantee partition assignment to the right instance |
| Fan-out replies to all instances | Every instance receives a copy and only the instance holding the correlation completes | Higher broker/consumer work; needs separate groups/subscriptions |
| Distributed pending registry | All instances query a shared store and use a notification/stream to wake the owner | More complex; must manage leases, expiry, and races |

With Kafka, do not assume a shared reply topic with a shared consumer group will automatically route replies back to the requesting instance. You can use per-instance reply topics or an explicit partition/consumer assignment design. With RabbitMQ, per-instance reply queues or direct reply-to may fit depending on topology.

`replyTo` must only be generated by the ingress from trusted configuration/instance identity; workers must never publish to arbitrary destinations supplied by clients.

## 9. Completing the gRPC RPC Asynchronously

The service implementation should not block a thread waiting on `future.get()`. When the future completes, a callback converts the result into a protobuf response:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    Context rpcContext = Context.current();
    String correlationId = ids.newCorrelationId();
    String operationId = idempotency.resolveOperationId(
            callerContext.current().tenantId(),
            request.getIdempotencyKey());

    CompletableFuture<OrderReply> replyFuture =
            pendingReplies.register(correlationId, Duration.ofSeconds(2));

    Context.CancellationListener cancellationListener =
            ignored -> replyFuture.cancel(false);
    rpcContext.addListener(cancellationListener, Runnable::run);

    replyFuture.whenComplete((reply, failure) ->
            rpcContext.run(() -> {
                rpcContext.removeListener(cancellationListener);
                if (rpcContext.isCancelled()) {
                    return;
                }
                if (failure != null) {
                    observer.onError(toGrpcStatus(failure));
                    return;
                }
                observer.onNext(toProto(reply));
                observer.onCompleted();
            }));

    if (rpcContext.isCancelled()) {
        return;
    }

    try {
        publisher.publish(
                mapper.toCommand(request, operationId),
                correlationId,
                replyDestinations.currentInstanceDestination())
            .whenComplete((metadata, failure) -> {
                if (failure != null) {
                    pendingReplies.fail(correlationId, failure);
                }
            });
    } catch (RuntimeException ex) {
        pendingReplies.fail(correlationId, ex);
    }
}
~~~

This is an illustrative skeleton; add validation, authorization, in-flight request limits, synchronous exception handling from `publish`, and full status mapping. The key points are registering the pending future before publishing, not blocking the RPC thread, and emitting only one terminal signal.

`Context.CancellationListener` stops waiting when the client cancels or the gRPC deadline expires. It only cancels the future at the ingress; it does not automatically recall a command already accepted by the broker and does not stop the worker. If business rules require cancelling execution, provide a dedicated cancellation command and check state races.

## 10. Timeouts and Late Replies

There are at least two distinct timeouts:

- **gRPC deadline:** how long the client waits for the RPC.
- **Reply timeout:** how long the ingress keeps the pending future waiting for the consumer.

The reply timeout should be less than or equal to the remaining gRPC deadline after subtracting budget for validation, publishing, and returning the response. Do not extend an RPC beyond the caller's deadline.

When a timeout occurs:

1. The future completes with `TimeoutException`.
2. The registry removes the pending entry.
3. The adapter returns `DEADLINE_EXCEEDED` if the RPC is still active.
4. The worker may still continue processing the command.
5. Replies arriving after timeout are recorded as late/unmatched; never send them to an already-terminated observer.

A timeout does not prove the command was not processed. If the client retries, use the same idempotency key/operation ID. If clients need late results, store replies by operation ID and expose `GetOperationStatus`.

## 11. Mapping Replies and Errors to gRPC Status

Reply messages should express typed business outcomes rather than arbitrary Java exceptions:

| Worker outcome | Recommended gRPC status |
|---|---|
| Success with response | `OK` with protobuf reply |
| Business validation failure on input | `INVALID_ARGUMENT` or defined domain status |
| Resource does not exist | `NOT_FOUND` |
| Current state does not allow action | `FAILED_PRECONDITION` |
| Caller lacks permission | `PERMISSION_DENIED` |
| Worker/broker did not respond within deadline | `DEADLINE_EXCEEDED` |
| Broker unavailable before publish confirmed | `UNAVAILABLE` |
| Malformed reply schema or undecodable message | `INTERNAL` at ingress; log and handle bad message |

Do not put stack traces, internal topic names, hostnames, tokens, or sensitive data in status descriptions. Keep `failureCode` stable in the reply contract and map it to a status in the adapter.

## 12. Resource Limits and Backpressure

Each pending RPC consumes a future, map entry, timer, and potentially a gRPC connection. If the broker slows down, the number of pending requests can grow rapidly.

The ingress should:

- Cap pending requests instance-wide and per tenant.
- Reject early with `RESOURCE_EXHAUSTED` when limits are reached.
- Use finite timeouts and clean up entries on every completion path.
- Use a bounded executor for callbacks if mapping/serialization is CPU-intensive.
- Limit request/reply payload sizes and in-flight message counts.
- Monitor broker latency, reply latency, and pending counts.
- Never spawn a separate thread per RPC.

If slow-reply rates increase, increasing the timeout is not the default fix; doing so can make the pending map grow even larger. Inspect consumer lag, downstream latency, partition skew, and capacity.

## 13. When to Use Spring Kafka `ReplyingKafkaTemplate`?

Spring Kafka provides `ReplyingKafkaTemplate` to support request/reply over Kafka. It combines a producer with a reply listener container and manages request-reply correlation via futures. It is a good fit when your Kafka topology satisfies reply-routing requirements.

Conceptual example:

~~~java
ProducerRecord<String, SubmitOrderCommand> record =
        new ProducerRecord<>(
                "orders.commands",
                command.commandId(),
                command);

record.headers().add(new RecordHeader(
        KafkaHeaders.REPLY_TOPIC,
        replyTopic.getBytes(StandardCharsets.UTF_8)));

RequestReplyFuture<String, SubmitOrderCommand, OrderReplyMessage> future =
        replyingKafkaTemplate.sendAndReceive(record);

future.whenComplete((replyRecord, failure) -> {
    if (failure != null) {
        // Map error to the pending gRPC call.
        return;
    }
    // Map replyRecord.value() to the protobuf response.
});
~~~

This is an API-oriented example; real configuration needs a reply listener container, reply topic/partition, serializer/deserializer, timeout, and correlation header matching your Spring Kafka version. When running multiple ingress instances, you must still ensure the reply listener receives only replies belonging to the instance holding the RPC; the template does not automatically solve all routing issues in arbitrary topologies.

If you need tight control over the correlation registry, timeouts, cancellation, or multiple brokers, you can build a custom registry. Whether using the template or a custom implementation, the rules for timeouts, idempotency, late replies, and multi-instance routing still apply.

## 14. Testing Asynchronous Replies

Tests should cover race conditions and failure windows:

| Scenario | What to verify |
|---|---|
| Worker replies very quickly | Pending entry was created before publish; RPC receives the reply |
| Normal reply arrival | Correlation ID matches the right future |
| Two concurrent RPCs | Responses are not cross-matched |
| Duplicate correlation ID | Registry rejects or generates a fresh ID per policy |
| Publish failure | Future fails and RPC receives appropriate status |
| Reply timeout | Entry is cleaned up; RPC ends with `DEADLINE_EXCEEDED` |
| Reply arrives after timeout | Terminated observer is not called; late reply is recorded |
| Client cancels | Pending future is cleaned up; published command is not assumed self-cancelled |
| Duplicate reply | Only one reply completes the future; duplicates are metered/logged |
| Multiple ingress instances | Reply routes to the instance owning the pending request |
| Ingress restarts | Old RPC terminates; durable operation status remains queryable if persisted |
| Worker business error | Reply failure code maps accurately to gRPC status |
| Backpressure | Exceeding pending limit rejects early without unbounded memory growth |

Registry unit tests should verify contention between `complete`, timeout, cancel, and `fail`. Integration tests with a real or containerized broker verify reply topics, headers, consumer groups, routing, and redelivery. Mocking a listener cannot prove replies reach the right instance in a multi-replica setup.

## 15. Metrics and Diagnostics

Monitor:

- Number of RPCs awaiting replies and peak pending count.
- Time from publish to reply by message type.
- Rates of reply timeouts, publish failures, late replies, and unmatched correlations.
- Duplicate replies and correlation collisions.
- Broker lag, consumer processing latency, and reply publish latency.
- Counts of cancelled RPCs and exceeded gRPC deadlines.
- Requests rejected due to pending capacity limits.
- Share of workers completing before the reply deadline.

Use correlation ID/operation ID in logs and traces, not as high-cardinality metric labels. During investigations, link ingress logs, command publish, worker execution, and reply listener via correlation ID; use trace context to inspect technical spans if sampling retained the trace.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Publishing before registering the future | Fast reply arrives first and is dropped | Register pending before publishing |
| Blocking thread with `future.get()` | Reduces throughput, exhausts workers/event loops | Use callbacks and futures |
| Sharing reply topic/consumer group without routing | Reply lands on wrong ingress instance | Per-owner reply destination/partition |
| No timeout on pending entries | Memory leaks and RPCs held indefinitely | Finite timeouts and cleanup |
| Treating timeout as command never ran | Retries may cause duplicate side effects | Use idempotency key and operation status |
| Treating gRPC cancellation as cancelling broker message | Worker still runs while caller thinks it stopped | Separate RPC cancellation from business cancellation |
| Using correlation ID as operation ID | Retries and multiple attempts hard to manage | Separate correlation, operation, and message IDs |
| Not handling late/duplicate replies | Observer errors or hard-to-debug logs | Complete atomically, meter unmatched/late replies |
| Waiting for long workflows in the same RPC | Pending state and connections live too long | Switch to `ACCEPTED` + operation status |

**Key takeaway:** Async replies from messages back to gRPC use a correlation ID to pair reply messages with waiting RPCs. Register the pending future before publishing, complete it in the reply listener, and return the protobuf response via a non-blocking callback. Enforce timeouts, cleanup, cancellation, and pending capacity limits; route replies to the right ingress instance when scaling replicas. Timeouts/cancellations do not automatically cancel already-published commands, so idempotency and operation status remain essential for late results or long workflows.
