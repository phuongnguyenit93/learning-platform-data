# Handling RESOURCE_EXHAUSTED

## Lesson Objectives

In **SPRING_GRPC**, the server must limit concurrency, queues, message sizes, connections, and quotas to protect both the process and downstream dependencies. When a limit is hit, gRPC provides the RESOURCE_EXHAUSTED status. Clients must understand the cause to decide whether to wait, shed load, shrink the request, or stop retrying.

This lesson focuses on **handling RESOURCE_EXHAUSTED**: distinguishing temporary overload from quotas and oversized payloads, emitting semantically accurate statuses, applying admission control and bounded queues, passing retry guidance, designing budgeted retries, handling streaming/backpressure, observing rejection rates, and testing saturation/recovery.

After this lesson, you can:

1. Explain the meaning of the gRPC status RESOURCE_EXHAUSTED.
2. Classify capacity exhaustion, quota exhaustion, and message/resource limits.
3. Return RESOURCE_EXHAUSTED at the service boundary when no more work can be accepted.
4. Bound concurrency, queues, and payload sizes.
5. Safely convey retry guidance using status details when appropriate.
6. Design client retries with backoff, jitter, deadlines, and idempotency.
7. Combine streaming flow control with resource limits.
8. Monitor overload and test the system when hitting limits.

> **Scope:** Examples use gRPC Java, Spring, and protobuf. Some examples use google.rpc.Status/RetryInfo from googleapis common protos. Spring gRPC starter property names depend on the version; app.grpc.* settings in this lesson are an application-defined namespace.

## 1. What does RESOURCE_EXHAUSTED mean?

RESOURCE_EXHAUSTED is gRPC status code 8. It indicates an operation could not complete because a resource or quota has been exhausted/exceeded. This status alone does not state whether the error will self-recover or whether the client should retry immediately.

Common causes:

| Cause | Example | Typical appropriate handling |
| --- | --- | --- |
| Temporary capacity | Worker pool full, semaphore out of permits, server overloaded | Reject early; may retry after waiting if the operation is safe |
| Quota | Tenant exceeds requests/minute or usage limit | Wait for quota window/reset or request quota increase; aggressive retries do not help |
| Oversized payload | Message larger than inbound message size limit | Shrink/split payload; resending the exact same request usually still fails |
| Downstream resource | Connection pool or downstream capacity exhausted | Shed load, timeouts, circuit breakers, and controlled retries |
| System resource | Memory, file descriptors, or operational limits | Protect the process, investigate root cause, and restore capacity |

Do not use RESOURCE_EXHAUSTED for every server error. For instance, malformed requests should be INVALID_ARGUMENT; unauthorized callers are PERMISSION_DENIED; expired deadlines are DEADLINE_EXCEEDED. Accurate statuses help clients and dashboards choose the right behavior.

### 1.1. Distinguishing capacity, quota, and payload

These three groups typically require different handling:

- **Capacity exhaustion:** concurrency limits or queues are full. May be transient if load drops.
- **Quota exhaustion:** caller/tenant has used up its granted budget. Retry only after reset or once additional quota is granted.
- **Payload/resource limit:** request exceeds a fixed limit such as message size. Requires changing the request or an approved configuration change.

You can keep the same gRPC code RESOURCE_EXHAUSTED while classifying internal reasons into a finite set of values like capacity, quota, and message_size. Never embed tenant IDs or request IDs in metric labels to describe the cause.

## 2. Identifying limits to protect

Before returning a status, identify which resources need limits and at which layer:

| Resource | Limiting mechanism |
| --- | --- |
| Concurrent in-flight RPCs | Semaphore/admission control or server concurrency policy |
| Worker threads | Bounded executor with max threads |
| Waiting tasks | Finite queue capacity |
| Inbound messages | max inbound message size |
| Request rate | Rate limiter/token bucket |
| Tenant/API key quota | Quota store or policy service |
| Downstream connections | Connection pools and concurrency limits |
| Streaming messages | Flow control, bounded buffers, and in-flight limits |
| Processing duration | Deadlines, timeouts, and cancellation |

Limits must be chosen according to downstream capacity and latency budgets, not just the service's CPU count. If the gRPC server accepts 500 concurrent RPCs while the database can only sustain 50 concurrent queries, admission or pools must be capped appropriately before the database overloads.

Never use unbounded queues to absorb traffic bursts. Unbounded queues only delay failure, increase memory pressure, and cause requests to wait until deadlines expire.

## 3. Emitting RESOURCE_EXHAUSTED when admission control rejects

Admission control decides whether to accept another operation before starting resource-intensive work. A semaphore bounds running operations:

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryGrpc.InventoryImplBase {

    private final Semaphore permits = new Semaphore(64);
    private final InventoryRepository repository;

    public InventoryGrpcService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockResponse> observer) {

        if (!permits.tryAcquire()) {
            observer.onError(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Server is overloaded")
                            .asRuntimeException());
            return;
        }

        try {
            Stock stock = repository.load(request.getSku());

            observer.onNext(
                    GetStockResponse.newBuilder()
                            .setAvailable(stock.available())
                            .build());
            observer.onCompleted();
        } catch (Exception ex) {
            observer.onError(
                    Status.INTERNAL
                            .withDescription("Unable to read stock")
                            .asRuntimeException());
        } finally {
            permits.release();
        }
    }
}
```

This example uses synchronous processing to illustrate admission control; in real blocking services, do not hold gRPC callback threads for long. When offloading to a worker pool, release the permit only when the operation actually completes/cancels, not immediately after submitting the task. With async callbacks, ensure exactly-once release using operation lifecycle/atomic guards.

Permits must be released on all success, exception, and cancellation paths. If permits leak, the service will keep returning RESOURCE_EXHAUSTED even after load subsides.

### 3.1. Admission control before submitting to workers

When a service uses a bounded worker executor:

1. Check deadline/cancellation.
2. Try acquiring a permit or checking capacity.
3. Submit the task to the bounded executor.
4. If the executor rejects, return RESOURCE_EXHAUSTED.
5. When the task finishes or is canceled, release the permit.
6. Ensure terminal callbacks are sent only once.

Do not catch every RuntimeException and turn it into RESOURCE_EXHAUSTED. Map only explicit admission/rejection errors; business errors and programming bugs need their own appropriate statuses.

## 4. Bounded executors and queues

Spring ThreadPoolTaskExecutor can configure finite workers and queues:

```java
@Bean
ThreadPoolTaskExecutor grpcBusinessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(16);
    executor.setMaxPoolSize(48);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("grpc-business-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(20);
    return executor;
}
```

The values above are examples only. Choose them based on throughput, blocking duration, database connection pools, downstream limits, and latency budgets. A queue of 100 does not mean the system can always process 100 additional requests; it means 100 waiting tasks, and queue wait time may cause deadlines to expire before tasks begin.

Catch rejections right at the submission boundary:

```java
try {
    grpcBusinessExecutor.execute(task);
} catch (RejectedExecutionException ex) {
    observer.onError(
            Status.RESOURCE_EXHAUSTED
                    .withDescription("Temporary capacity limit reached")
                    .asRuntimeException());
}
```

In practice, Spring's ThreadPoolTaskExecutor can wrap rejections as TaskRejectedException, a subclass of RejectedExecutionException. Catching RejectedExecutionException covers both; if using another abstraction, check the exception hierarchy before picking the catch type. A handler can translate rejections into a domain exception and map centrally at the service boundary.

Do not use CallerRunsPolicy carelessly. If the caller is a gRPC transport/callback thread, a blocking task can tie up the thread handling other RPCs and stall the server. Do not use DiscardPolicy because it can silently drop tasks without notifying the client.

## 5. Message size and payload limits

gRPC Java lets you configure inbound message size on server/channel builders. Example:

```java
ServerBuilder<?> serverBuilder = obtainServerBuilder();
serverBuilder.maxInboundMessageSize(4 * 1024 * 1024);
```

This is an illustrative 4 MiB limit. Align it with clients, proxies, gateways, and downstream services. Do not raise the limit just to make one huge request work if the payload can be paginated, batched, or moved to object storage.

When a request exceeds the transport limit, gRPC may reject it before the service method is invoked. Therefore, not every message-size error can be mapped via try/catch inside the service. Test behavior on the exact transport/version and observe the client-side status.

For large payloads:

- Prefer pagination or bounded batching.
- Set maximum item count and total byte size.
- Use streaming when semantics fit, paired with flow control.
- Consider uploading directly to object storage instead of passing large blobs over RPC.
- Validate size at the gateway/client if possible, while still enforcing limits on the server.

## 6. Conveying retry guidance with google.rpc.RetryInfo

For recoverable capacity exhaustion, the server can attach RetryInfo to suggest a wait duration. This is a standard status detail in the Google RPC error model; clients can only use it when both sides support status details.

Example of creating a status detail:

```java
RetryInfo retryInfo = RetryInfo.newBuilder()
        .setRetryDelay(
                com.google.protobuf.Duration.newBuilder()
                        .setSeconds(2)
                        .build())
        .build();

com.google.rpc.Status rpcStatus =
        com.google.rpc.Status.newBuilder()
                .setCode(Code.RESOURCE_EXHAUSTED.getNumber())
                .setMessage("Temporary capacity limit reached")
                .addDetails(Any.pack(retryInfo))
                .build();

observer.onError(
        StatusProto.toStatusRuntimeException(rpcStatus));
```

This requires compatible googleapis common protos and grpc-protobuf dependencies. Not every client language or proxy exposes status details identically; always have a safe fallback if the client cannot read RetryInfo.

Do not send RetryInfo for quota exhaustion if retrying after two seconds is still guaranteed to fail. For quotas, useful information may be a contract-defined reset time or QuotaFailure detail; avoid letting clients misinterpret every RESOURCE_EXHAUSTED as transient.

### 6.1. Client reading RetryInfo

Clients can extract google.rpc.Status from a throwable:

```java
com.google.rpc.Status details = StatusProto.fromThrowable(error);

if (details != null) {
    for (Any detail : details.getDetailsList()) {
        if (detail.is(RetryInfo.class)) {
            RetryInfo retryInfo = detail.unpack(RetryInfo.class);
            Duration delay = retryInfo.getRetryDelay();
            // Pass delay into a bounded retry policy.
        }
    }
}
```

Handle InvalidProtocolBufferException when unpacking details. Do not blindly trust wait times from the server: apply minimum/maximum bounds, remaining deadline, and client retry budgets. If details are missing or malformed, fall back to a bounded default policy or return the error to the caller.

## 7. Controlled client-side retries

RESOURCE_EXHAUSTED does not automatically mean retrying is safe. Before retrying, the client must know:

- Is the operation idempotent?
- Is the error temporary capacity or a fixed quota/payload limit?
- Does enough deadline remain?
- Did the server provide RetryInfo?
- Are attempts still within the retry budget?
- Is a circuit breaker or rate limiter open?

A common policy for temporary capacity:

1. Respect RetryInfo if present, after clamping to min/max bounds.
2. If no hint is present, use exponential backoff with full jitter.
3. Bound max attempts and total retry time.
4. Do not retry when the deadline is nearly exhausted.
5. Do not retry non-idempotent operations without an idempotency key/deduplication.
6. Upon quota exhaustion, wait for quota reset or propagate the error to the caller.
7. When payload is too large, require the client to shrink the payload; never retry the same payload.

Bounded backoff formula:

```text
delay(attempt) = random(0, min(maxDelay, baseDelay × 2^attempt))
```

Jitter prevents multiple clients from retrying at the exact same instant. A retry storm can immediately exhaust newly recovered capacity. Clients should coordinate retry budgets, rate limits, and circuit breakers.

### 7.1. Avoid retrying at multiple layers simultaneously

If gRPC service config, an application gateway, and the business client all retry, total requests can multiply. Choose one layer to own the retry policy for each downstream operation; other layers must respect deadlines and avoid hidden duplicate retries.

Include retry counts in low-cardinality metrics/trace attributes. Never log the full request on every retry.

## 8. Streaming RPCs and backpressure

gRPC flow control helps receivers throttle how many messages senders may transmit. It differs from RESOURCE_EXHAUSTED:

- **Backpressure/flow control:** the receiver is temporarily unready for more messages; the sender slows down per protocol.
- **RESOURCE_EXHAUSTED:** the application or transport has hit a limit and cannot accept more resources/work.
- **Quota exhaustion:** the caller has exceeded its granted budget; slowing down for a few milliseconds may not resolve it.

With async streaming, request additional messages only when application capacity allows. On the server response stream, check readiness and emit next responses when the observer signals ready via the appropriate API. Never accumulate an entire stream in an unbounded queue.

Limits:

- Concurrent in-flight messages being processed.
- Messages/bytes waiting in buffers.
- Total bytes of the stream if the contract requires bounding.
- Stream duration and idle timeout.
- Concurrent streams per client/tenant.

When a stream violates policy, return the appropriate status and terminate the stream cleanly. Never use RESOURCE_EXHAUSTED to signal a normal flow-control pause.

## 9. Quotas per tenant or caller

Quotas must clearly define dimensions and measurement windows:

- Requests per second/minute.
- Concurrent RPCs.
- Bytes uploaded/downloaded.
- Records or operations consumed.
- Quotas by API key, tenant, project, or plan.

Quota enforcement must rely on authenticated identity, never on an arbitrary tenant ID in metadata. For distributed services, quota stores must handle concurrency/atomicity; local caches can reduce latency, yet you must understand error margins and consistency trade-offs.

When quota is exceeded:

- Return RESOURCE_EXHAUSTED.
- Optionally attach quota reason/reset guidance per contract.
- Do not retry rapidly before quota resets.
- Never expose another tenant's quota.
- Record metrics by quota class or policy name with finite cardinality.

Never place tenant IDs, user IDs, or API keys into metric labels. When investigating a specific tenant, use logs/traces with appropriate access controls and retention.

## 10. Mapping internal errors to gRPC statuses

Centralize capacity/quota error mapping at the service boundary:

| Internal error | gRPC status | Notes |
| --- | --- | --- |
| Admission permit unavailable | RESOURCE_EXHAUSTED | Temporary capacity |
| Bounded executor rejected task | RESOURCE_EXHAUSTED | Only when truly capacity exhaustion |
| Quota exceeded | RESOURCE_EXHAUSTED | Usually do not retry before reset |
| Message exceeds transport limit | RESOURCE_EXHAUSTED or transport-specific status | May be rejected before service |
| Invalid request field/format | INVALID_ARGUMENT | Client must fix request |
| Missing permission | PERMISSION_DENIED | Do not retry |
| Dependency temporarily unavailable | UNAVAILABLE | Retry only when policy allows |
| Deadline expired | DEADLINE_EXCEEDED | Check time budget |
| Unexpected error | INTERNAL | Do not mask with RESOURCE_EXHAUSTED |

Never expose stack traces or internal class names in Status descriptions. Detailed exceptions can be recorded in redacted logs alongside trace IDs; clients receive stable, non-sensitive messages.

## 11. Metrics and alerts for resource exhaustion

Track at minimum:

| Metric | Purpose |
| --- | --- |
| RPC count by status | Rate of RESOURCE_EXHAUSTED |
| Admission rejected count | Requests rejected before processing |
| Active permits / concurrency | Utilization of concurrency limits |
| Executor active threads | Worker pool utilization |
| Queue size / wait duration | Backlog and waiting time |
| Rejected task count | Executor saturation level |
| Message size distribution | Detecting near-threshold payloads |
| Quota exceeded count | Separating quota from capacity |
| Retry attempts / retry delay | Detecting retry storms |
| Downstream pool utilization | Pinpointing dependency bottlenecks |

Metric labels should be service, method, status, and reason class with a finite set of values. Never attach request IDs, user IDs, tenant IDs, or raw targets as metric labels.

Alerts should be based on rates and sustained duration, not a single isolated error. Some RESOURCE_EXHAUSTED responses may show admission control protecting the system properly; a sudden spike accompanied by rising latency, queue wait, or downstream saturation signals a need to investigate capacity.

## 12. Testing saturation and recovery

Tests must reproduce capacity exhaustion deterministically. Use small semaphores, executors with one worker/small queue, CountDownLatch, and timeouts; avoid long sleeps.

Cases to include:

1. **Admission full:** exhaust all permits then send another RPC; the new request receives RESOURCE_EXHAUSTED.
2. **Permit release:** complete/cancel a request; the permit is returned and a new RPC can run.
3. **Executor rejection:** hold the worker busy and fill the queue; rejection maps to the right status.
4. **No task loss:** no task is silently discarded or leaves an RPC hanging.
5. **RetryInfo:** server returns RetryInfo; client reads delay and applies bounds.
6. **Quota:** exceed quota; client does not retry rapidly before reset.
7. **Payload limit:** oversized request rejected; client does not repeat the exact same payload.
8. **Deadline:** retry budget does not exceed total deadline.
9. **Idempotency:** non-idempotent operations are not blindly retried.
10. **Streaming:** buffers/in-flight work are bounded; flow control prevents unbounded queues.
11. **Recovery:** after load drops, permits/queues return to normal and RPCs succeed.
12. **Concurrency:** concurrent requests do not leak permits or send terminal callbacks twice.

### 12.1. Admission control test example

Create a test service with one permit. The first request holds the permit using a latch; the second request must receive RESOURCE_EXHAUSTED; after releasing the latch, the third request must succeed. Assert that the final permit count returns to its initial value.

Avoid overly tight absolute timing assertions because schedulers vary; use latches for synchronization and timeouts so tests never hang.

## 13. Common pitfalls and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Client retries continuously and load climbs | Retrying every RESOURCE_EXHAUSTED blindly | Distinguish capacity, quota, and payload; backoff/jitter/budget |
| Server out of permits even after load drops | Permits not released on exception/cancel paths | Manage lifecycle and release exactly once |
| RPC hangs when executor is full | Rejection swallowed or task discarded | Use explicit rejection policy and return status |
| Queue grows without throughput rising | Slow downstream or queue too large | Limit queue, measure queue wait and dependency capacity |
| Payload valid on client but fails on server | Mismatched message size limits | Align limits and check proxies/transports |
| RESOURCE_EXHAUSTED used for validation | Status mapping too broad | Use INVALID_ARGUMENT for bad requests |
| Client retries quota errors before reset | Not distinguishing quota from overload | Communicate quota guidance and avoid early retries |
| Streaming memory grows steadily | Unbounded buffer/queue or unthrottled messages | Apply flow control and limit in-flight work |
| Retries exceed deadline | Each attempt uses a fresh timeout ignoring parent deadline | Compute remaining budget and stop retrying |
| Multiple layers retrying together | Retry policies multiply | Pick one layer to own retries |
| Dashboard fails to separate causes | Only counting total status | Add low-cardinality reason class |
| Recovery still returns RESOURCE_EXHAUSTED | Worker/permit leak or downstream still unhealthy | Inspect active counts, queues, permits, and dependencies |

## 14. Hands-on exercises

1. Create a bounded business executor with finite core/max threads and finite queue.
2. Add admission control limiting concurrent in-flight RPCs.
3. Map permit exhaustion and executor rejection to RESOURCE_EXHAUSTED.
4. Ensure permits release on success, exception, and cancellation.
5. Configure inbound message size and test over-threshold payloads.
6. Build google.rpc.RetryInfo for recoverable capacity exhaustion.
7. Write a client parser reading RetryInfo and applying exponential backoff with jitter, max attempts, and deadline budget.
8. Create a quota policy keyed by authenticated principal; verify quotas do not rely on untrusted metadata.
9. Build a streaming workload with bounded buffers and flow control.
10. Record metrics separating capacity, quota, and payload limits.
11. Write a saturation test with a small semaphore/executor and verify recovery.
12. Test retry storms, idempotency, and cancellation before rolling policies to production.

### Self-check questions

- Is RESOURCE_EXHAUSTED always a transient error?
- How does capacity exhaustion differ from quota exhaustion and payload limits?
- Why should admission control reject early before submitting tasks?
- When must a permit be released in an async RPC?
- Why can CallerRunsPolicy stall gRPC callback threads?
- How does RetryInfo help clients adjust retries?
- Why should quota exhaustion usually not be retried immediately?
- How do exponential backoff and jitter help prevent retry storms?
- When is an RPC unsafe to retry?
- How does flow control differ from RESOURCE_EXHAUSTED?
- Why can message size be rejected before the service method executes?
- Which metrics distinguish capacity bottlenecks from quotas?
- How do you test permit leaks and recovery?

## References

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/): semantics of RESOURCE_EXHAUSTED and other statuses.
- [gRPC — Error Handling](https://grpc.io/docs/guides/error/): propagating errors and status details.
- [gRPC — Retry](https://grpc.io/docs/guides/retry/): retry policies, attempts, and backoff.
- [gRPC — Flow Control](https://grpc.io/docs/guides/flow-control/): throttling streaming messages.
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): server configuration and inbound message size.
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html): status codes and RuntimeException mapping.
- [Google RPC — Error Details](https://cloud.google.com/apis/design/errors): google.rpc.Status and error details such as RetryInfo/QuotaFailure.
- [Spring Framework — Task Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): ThreadPoolTaskExecutor and task rejection.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): monitoring saturation, latency, and error rates.

**Expected outcome:** Learners handle RESOURCE_EXHAUSTED consistently in Spring gRPC services, distinguish capacity/quota/payload limits, bound concurrency and queues, convey appropriate retry guidance, prevent retry storms, apply backpressure to streaming, and measure and test saturation, permit cleanup, and recovery.
