# Timeout When Waiting for a Reply

Request-reply with Kafka lets one service send a request to a topic and wait for another service to process it and send back a reply. In Spring Kafka, ReplyingKafkaTemplate provides the sendAndReceive() API that returns a future representing the corresponding reply. Because requests and replies travel through the broker, completion time depends on the producer, Kafka, the request-handling consumer, the reply-sending producer, and the reply-receiving consumer.

A timeout is the time limit the requester is willing to wait for a result. When time expires, the application can stop waiting and return a timeout status to the caller. That does not prove the request was never sent or the target service never processed it. The request may have been processed successfully while the reply arrived slowly, was lost, or was not yet received by the requester. This is the single most important point when designing request-reply: timeouts produce an indeterminate outcome, so retries must go hand in hand with idempotency.

This lesson focuses on ReplyingKafkaTemplate timeouts, how to configure default and per-request timeouts, distinguishing send failures from reply timeouts, handling late replies, managing correlation IDs, and designing safe retries.

## Learning Objectives

After this lesson, you will be able to:

- Describe the request-reply lifecycle in Spring Kafka.
- Configure ReplyingKafkaTemplate and a reply listener container.
- Set default and per-request reply timeouts.
- Distinguish reply wait timeouts from request send errors and Kafka producer timeouts.
- Explain why a timeout does not cancel processing on the target service.
- Identify replies arriving past the deadline and handle them.
- Design correlation IDs, request IDs, and idempotency keys.
- Choose timeouts based on the end-to-end latency budget.
- Avoid retry storms and duplicate side effects after timeouts.
- Test timely replies, timeouts, late replies, send failures, and reply consumer group configurations.

## 1. How Does Request-Reply Work?

A requester sends a request record to a request topic. The record carries a correlation ID to link the reply with the pending call. The requester also needs a reply topic subscribed to by a reply listener container. The request-handling service produces a reply and sends it to the reply topic along with the matching correlation ID.

General flow:

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant K as Kafka
    participant B as Processing service
    A->>A: Generate correlation ID
    A->>K: Send request + reply topic + correlation ID
    K->>B: Consumer receives request
    B->>B: Execute business logic
    B->>K: Send reply + correlation ID
    K->>A: Reply listener receives reply
    A->>A: Look up future by correlation ID
    A-->>A: Complete future
~~~

ReplyingKafkaTemplate manages pending requests in memory by correlation ID. When the reply listener receives a record, the template finds the matching future and completes it.

Key components:

- Request topic: where the target service receives requests.
- Reply topic: where the requester receives replies.
- Reply listener container: consumer container listening to the reply topic.
- Correlation ID: key pairing a reply with a pending request.
- RequestReplyFuture: future representing the reply result.
- Reply timeout: limit on how long to wait for the reply.

Request-reply over Kafka is an asynchronous protocol that applications can consume in a synchronous-wait style. It offers no response-time guarantees like an in-process function call; the broker, consumer lag, rebalances, and downstream dependencies all affect latency.

## 2. Configuring ReplyingKafkaTemplate

ReplyingKafkaTemplate requires a ProducerFactory to send requests and a reply listener container to receive replies.

Example configuration:

~~~java
@Configuration
public class KafkaRequestReplyConfiguration {

    @Bean
    public ConcurrentMessageListenerContainer<String, OrderReply>
            repliesContainer(
                    ConcurrentKafkaListenerContainerFactory<String, OrderReply>
                            replyListenerFactory) {

        ConcurrentMessageListenerContainer<String, OrderReply> container =
                replyListenerFactory.createContainer("orders.replies");

        container.getContainerProperties().setGroupId(
                "orders-requester-replies"
        );

        return container;
    }

    @Bean
    public ReplyingKafkaTemplate<String, OrderRequest, OrderReply>
            replyingKafkaTemplate(
                    ProducerFactory<String, OrderRequest> producerFactory,
                    ConcurrentMessageListenerContainer<String, OrderReply>
                            repliesContainer) {

        ReplyingKafkaTemplate<String, OrderRequest, OrderReply> template =
                new ReplyingKafkaTemplate<>(
                        producerFactory,
                        repliesContainer
                );

        template.setDefaultReplyTimeout(Duration.ofSeconds(10));

        return template;
    }
}
~~~

This example assumes a ProducerFactory and reply listener factory with appropriate key/value deserializers already exist. The reply container must subscribe to the right reply topic and start alongside the application context.

The request-handling service can return an object; Spring Kafka sends that object to the reply topic specified in the request header:

~~~java
@KafkaListener(
    topics = "orders.requests",
    groupId = "orders-processor"
)
@SendTo
public OrderReply process(OrderRequest request) {
    return orderService.handle(request);
}
~~~

The requester constructs the record and calls the template:

~~~java
ProducerRecord<String, OrderRequest> requestRecord =
        new ProducerRecord<>(
                "orders.requests",
                request.orderId(),
                request
        );

RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(
                requestRecord,
                Duration.ofSeconds(5)
        );
~~~

ReplyingKafkaTemplate adds correlation metadata and reply destination details based on the reply listener container. Since Spring Kafka 2.2, the template can infer the reply topic/partition when the container listens to a single topic or a single TopicPartitionOffset; if the container listens to multiple destinations, the application must provide explicit reply headers. @SendTo without an explicit destination lets the listener use the reply destination in the request header. Both sides must agree on serializers/deserializers and reply types.

You can use a fixed reply topic for the requester or a dedicated reply topic/partition per instance. When multiple requester instances share a reply topic, design consumer groups so replies are delivered to the right requester; this is explained in the section on shared reply topics.

### Waiting for Reply Container Assignment Before Sending

Since Spring Kafka 2.8.8, ReplyingKafkaTemplate provides waitForAssignment(). This is useful when the reply container uses auto.offset.reset=latest, so the requester does not send a request before the reply consumer initializes and miss an early reply:

~~~java
if (!replyingKafkaTemplate.waitForAssignment(Duration.ofSeconds(10))) {
    throw new IllegalStateException(
            "Reply container has not been assigned partitions"
    );
}
~~~

Waiting for assignment is a separate startup step, not a per-request reply timeout. With manual partition assignment without group management, the wait time must exceed the container's pollTimeout because the assignment notification is only emitted after the first poll. If a request is sent before the reply container is ready, the reply may be written to Kafka without the requester receiving it within the expected window.

## 3. Configuring the Default Timeout

ReplyingKafkaTemplate allows setting a default wait duration via setDefaultReplyTimeout().

~~~java
template.setDefaultReplyTimeout(Duration.ofSeconds(10));
~~~

Any request sent via sendAndReceive() without passing a specific timeout (or passing null) uses this default value. Spring Kafka currently defaults the reply timeout to 5 seconds; applications should set an explicit value aligned with SLAs rather than relying on the default.

Always configure an explicit timeout rather than depending on the library version's default. The right timeout depends on the request type, target service SLA, Kafka load, and downstream processing time.

Examples:

| Request Type | Illustrative Timeout |
|---|---:|
| Lightweight status lookup | 2 seconds |
| Standard business calculation | 5 seconds |
| Processing dependent on multiple services | 10–15 seconds |
| Long tasks or reports | Move to an asynchronous job instead of holding request-reply open |

These numbers are only starting points for design. Base your numbers on actual latency percentiles, SLAs, and dependency timeouts.

Too short a timeout increases false timeouts during transient slowdowns. Too long a timeout holds caller request contexts and resources longer, and forces users to wait longer when the target service has already failed.

## 4. Per-Request Timeouts

Different requests may have different SLAs. You can pass a Duration to each sendAndReceive() call instead of using the default timeout.

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(
                requestRecord,
                Duration.ofSeconds(3)
        );
~~~

Example service with two request types:

~~~java
public OrderReply getOrderStatus(OrderRequest request) throws Exception {
    ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>("orders.requests", request.orderId(), request);

    RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(
                    record,
                    Duration.ofSeconds(2)
            );

    return future.get();
}

public OrderReply calculateOrder(OrderRequest request) throws Exception {
    ProducerRecord<String, OrderRequest> record =
            new ProducerRecord<>("orders.requests", request.orderId(), request);

    RequestReplyFuture<String, OrderRequest, OrderReply> future =
            replyingKafkaTemplate.sendAndReceive(
                    record,
                    Duration.ofSeconds(12)
            );

    return future.get();
}
~~~

Per-request timeouts avoid forcing one value across all business operations. However, do not set timeouts arbitrarily everywhere; define a latency budget per use case so services do not call each other with conflicting timeouts.

If your Spring Kafka version does not have the sendAndReceive(record, Duration) overload, use the corresponding API for that version or configure the default reply timeout. Check the Javadoc for your exact dependency.

## 5. RequestReplyFuture and Request Send Outcomes

RequestReplyFuture represents the reply result. It also exposes a send future to track sending the request.

There are two phases to distinguish:

1. The producer sends the request to Kafka.
2. The requester receives a reply matching the correlation ID.

Example:

~~~java
RequestReplyFuture<String, OrderRequest, OrderReply> future =
        replyingKafkaTemplate.sendAndReceive(requestRecord);

future.getSendFuture().whenComplete((sendResult, sendError) -> {
    if (sendError != null) {
        log.error("Failed to send request to Kafka", sendError);
        return;
    }

    log.debug(
            "Request sent: topic={}, partition={}, offset={}",
            sendResult.getRecordMetadata().topic(),
            sendResult.getRecordMetadata().partition(),
            sendResult.getRecordMetadata().offset()
    );
});
~~~

If the send future fails, the request was not acknowledged as sent according to the producer result. If the send future succeeds but the reply future times out, the request was confirmed by the broker, yet the requester did not receive a reply in time.

Do not lump these two cases into the same error message. They lead to different retry decisions and investigations.

In Spring Kafka 3.0 and later, the request-reply future and send future are CompletableFutures. In 2.x versions, the future API may be ListenableFuture; adjust callback registration for the version in use.

## 6. Distinguishing Reply Timeout from Other Timeouts

A request-reply call involves multiple timers. Each must be configured and monitored separately.

| Timeout | Where Applied | Meaning |
|---|---|---|
| Reply timeout | ReplyingKafkaTemplate | How long the requester waits for the matching reply |
| Producer delivery timeout | Kafka producer | Limit on sending a record successfully or reporting failure |
| Request processing timeout | Request-handling service | Limit on business processing time |
| Downstream timeout | HTTP/database/other clients | Limit on waiting for dependencies |
| Caller timeout | External HTTP/gRPC/API | How long the caller waits on the current service |
| Startup assignment timeout | Reply listener container | How long to wait for the reply consumer to receive assignment |

Example producer delivery timeout:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

delivery.timeout.ms is not the reply timeout. A producer may send a request successfully in a few milliseconds while the handling service takes 20 seconds; in that case, a 5-second reply timeout can still fire.

Conversely, the producer might fail to send the request because the broker is unavailable before the reply timeout even matters. Inspect the send future to tell them apart.

## 7. Timeout Does Not Cancel the Request on the Target Service

When ReplyingKafkaTemplate runs out of wait time, the requester receives a TimeoutException or the future completes exceptionally per the template's timeout mechanism. That only ends waiting for the result on the requester.

It does not:

- Delete the request record from Kafka.
- Cancel the consumer processing the request.
- Roll back the target service's database transaction.
- Recall HTTP/API calls already issued by the target service.
- Prevent the target service from publishing a reply afterward.

Example:

~~~text
t=0s   Requester sends request R-100
t=1s   Service B receives request
t=2s   Service B starts updating database
t=5s   Requester hits reply timeout
t=7s   Service B commits database
t=8s   Service B sends reply
~~~

At the 5-second mark, the requester reports a timeout, yet the business operation can still finish at second 7. If the requester immediately sends a new request and Service B processes it again, side effects may be duplicated.

Therefore, timeouts should be represented as an indeterminate outcome or a status requiring lookup, depending on the business domain. Never assume a timeout means the operation failed.

## 8. Late Replies

A reply can arrive after the requester has timed out because:

- The request-handling consumer is lagging.
- The target service is waiting on a database or HTTP dependency.
- The reply producer sends slowly or retries.
- The reply topic has heavy traffic.
- The requester reply container rebalances or loses connection.
- The configured timeout is lower than actual latency.

Once ReplyingKafkaTemplate's internal timeout removes the request from the pending list, a reply arriving afterward no longer has a matching future to complete. The template cannot deliver that result back to the timed-out call; the reply is typically treated as having no pending request and logged.

The application must decide whether late replies should be persisted for lookup. For operations with significant side effects, a late result can still be valuable to update request status in a database or trigger a notification.

Do not increase timeouts indefinitely just to avoid late replies. Choose timeouts based on SLAs while designing business states for in-progress, completed, timed-out awaiting confirmation, and late-arriving results.

## 9. Correlation ID and Request ID Are Two Different Identifiers

The Correlation ID links a reply to a pending future inside the requester. The Request ID identifies a logical business request across multiple sends or retries.

Keep the two purposes separate:

| Identifier | Scope | On Retry |
|---|---|---|
| Correlation ID | One pending request-reply exchange | Can generate a new ID for the new attempt |
| Request ID | One logical business request | Keep unchanged to deduplicate |
| Event ID | One specific event | Keep unchanged when re-emitting the same event |
| Redrive ID | One operational record redrive | Generate anew for each redrive |

For example, a requester sends requestId ORD-100-UPDATE initially with correlationId C-1. The request times out. On retry, the requester can generate correlationId C-2 while keeping requestId ORD-100-UPDATE.

The target service uses requestId to check whether the request has already been processed. If already completed, it can return the stored result instead of executing side effects again.

Do not use the correlation ID as an idempotency key if each retry generates a new correlation ID.

## 10. Designing Idempotency on the Request-Handling Service

If requests may be resent after a timeout, the target service must protect side effects using a stable request ID.

Example:

~~~java
@Transactional
public OrderReply handle(OrderRequest request) {
    Optional<StoredReply> previous =
            requestRepository.findReplyByRequestId(request.requestId());

    if (previous.isPresent()) {
        return previous.get().toOrderReply();
    }

    OrderReply reply = orderService.apply(request);

    requestRepository.save(
            new StoredReply(
                    request.requestId(),
                    reply.status(),
                    reply.orderId()
            )
    );

    return reply;
}
~~~

In production, checking the request ID, executing business logic, and storing the reply must be protected within the same database transaction or an equivalent synchronization mechanism. A unique constraint on requestId guards against concurrent duplicate requests.

If you only check exists before inserting without a unique constraint, two consumer threads can both see the request as non-existent and both execute side effects.

For long-running requests, you can store statuses such as ACCEPTED/PROCESSING/COMPLETED/FAILED. When the requester times out, it queries by requestId to learn whether the work has completed or is still running.

## 11. Configuring Reply Topics and Consumer Groups

The reply listener container must receive replies intended for the right requester. When each requester instance has its own reply topic, routing is straightforward. When multiple requester instances share a single reply topic, pay close attention to consumer groups.

If requester instances share the same group ID on a reply topic, Kafka distributes each reply to one member in the group. A reply may arrive at an instance that does not hold a future for that correlation ID. The instance owning the request never receives the reply and times out.

Example of a broken setup:

~~~text
Requester pod A ----\
                     +---- replies topic, group=reply-consumers
Requester pod B ----/             |
                                   v
                           Kafka distributes the reply
                           to an arbitrary member
~~~

One deployment pattern is giving each requester instance its own group ID when sharing a reply topic. Each group then receives a copy of the reply topic and each instance can find its own correlation IDs. Replies belonging to other instances will not match any future and are ignored by the template's mechanism.

When multiple ReplyingKafkaTemplates share a reply topic, enable sharedReplyTopic to downgrade unmatched reply logs from ERROR to DEBUG:

~~~java
replyingKafkaTemplate.setSharedReplyTopic(true);
~~~

This setting only adjusts how the template handles/logs replies not belonging to the instance; it does not replace the requirement for a separate group ID or separate partition per requester.

The trade-off is that every requester instance reads the entire reply topic, increasing consumer traffic. Under high load, consider per-instance reply topics or partitions and route replies to the right destination.

Never set a single shared fixed group ID across all requester instances if each instance only keeps pending correlations in its own memory.

## 12. Timeouts and Safe Retries

When a reply times out, the requester may retry, but must avoid retry storms and duplicates.

A retry policy typically includes:

- A bounded number of attempts.
- Exponential backoff.
- Jitter so requesters do not retry in lockstep.
- A stable request ID across attempts.
- A distinct correlation ID per exchange.
- Idempotency on the target service.
- An overall deadline for the entire operation.

Example:

~~~java
Duration[] retryDelays = {
        Duration.ofMillis(200),
        Duration.ofMillis(500),
        Duration.ofSeconds(1)
};
~~~

This is only an example backoff schedule. Do not retry validation errors or invalid requests. A timeout yields an indeterminate result, so check status or retry using an idempotent request ID.

If each retry uses a 10-second timeout and there are three sequential attempts, the caller might wait over 30 seconds plus backoff. Set an overall deadline and compute remaining time before each send.

## 13. Using an Overall Deadline Instead of Stacking Timeouts

Suppose an external API has an 8-second SLA. If every layer in a request-reply chain sets its own 8-second timeout, total elapsed time can exceed the SLA.

Example:

~~~text
HTTP caller deadline: 8s
    |
    +-- requester waits for Kafka reply: 7s
            |
            +-- service B calls database: 6s
                    |
                    +-- dependency retry: 4s
~~~

Nested timeouts can push total duration past the external deadline. Propagate or compute remaining deadline rather than resetting full timeouts at each hop.

A rule of thumb:

~~~text
remaining = overallDeadline - currentTime

replyTimeout = min(configuredReplyTimeout, remaining)
dependencyTimeout <= remaining - safetyMargin
~~~

If remaining <= 0, do not send a new request. Return a timeout or pending status per the API contract.

Kafka request-reply has no automatic deadline propagation across all layers. If a business deadline is needed, pass a deadline or expiry timestamp in the payload/header and have the target service check it before starting work.

## 14. Enforcing Timeouts on the Target Service

A requester's reply timeout does not stop the target service from processing an expired request. If a request is no longer useful past its deadline, the target service needs to know the deadline and decide whether to proceed.

Example payload:

~~~java
public record OrderRequest(
        String requestId,
        String orderId,
        Instant deadline,
        String operation
) {}
~~~

Handling service:

~~~java
public OrderReply handle(OrderRequest request) {
    if (Instant.now().isAfter(request.deadline())) {
        return OrderReply.expired(request.requestId());
    }

    return orderService.apply(request);
}
~~~

Check the deadline before starting side effects. For work already in flight, safe cancellation depends on the business domain and transaction boundaries. Do not abort a database operation midway if doing so can leave inconsistent state.

If a request finishes processing but the reply arrives late, store the result by requestId so the requester can query it later.

## 15. Handling Reply Errors Instead of Timing Out

Not every unsuccessful reply is a timeout. The target service can return a reply representing a business error, such as OrderNotFound or ValidationFailed.

Example:

~~~java
public record OrderReply(
        String requestId,
        boolean success,
        String errorCode,
        String message,
        String orderId
) {}
~~~

The requester receives the reply and checks it:

~~~java
OrderReply reply = future.get();

if (!reply.success()) {
    throw new OrderRequestRejectedException(
            reply.errorCode(),
            reply.message()
    );
}
~~~

This is a successful reply at the transport layer representing a business-layer error. Do not retry a validation rejection as if it were a transient timeout.

Spring Kafka also supports a reply error checker on ReplyingKafkaTemplate to convert certain replies carrying an exception header into requester-side exceptions. When using this mechanism, clearly define which headers denote errors and distinguish them from normal business replies.

## 16. Controlling the Pending Requests Size

Each pending request needs a correlation/future entry in the requester's memory. If the target service slows down or the reply timeout is too long, pending requests can accumulate.

Some safeguards:

- Limit concurrent requests with a semaphore or bulkhead.
- Set a bounded timeout for every request.
- Bound the HTTP executor or thread pool queue.
- Monitor pending request count and wait duration.
- Use a circuit breaker when a dependency repeatedly times out.
- Move long-running tasks to asynchronous jobs instead of keeping request-reply open.

Do not open thousands of concurrent requests simply because the API returns a future. Asynchronous does not mean resources are infinite.

On timeout, the template completes the future and cleans up the pending entry per its mechanism. If the caller only uses future.get(timeout, unit) with a Java Future timeout, that is solely a caller wait limit; it does not replace ReplyingKafkaTemplate's internal timeout and does not necessarily clear the pending correlation immediately when get() throws TimeoutException.

Therefore, configure timeouts on ReplyingKafkaTemplate or use a sendAndReceive overload that accepts a timeout. You can use get(timeout) as an extra deadline guard, but do not rely on it as the pending-request cleanup mechanism.

## 17. Observing Timeouts in Production

Track send failures, reply timeouts, and late/unmatched replies separately.

Recommended metrics:

| Metric | Meaning |
|---|---|
| request_send_success_total | Number of requests successfully sent by the producer |
| request_send_failure_total | Number of requests that failed to send |
| request_reply_success_total | Number of requests receiving a reply on time |
| request_reply_timeout_total | Number of requests whose wait time expired |
| request_reply_latency | Time from sending the request to receiving the reply |
| pending_request_count | Number of requests currently awaiting replies |
| unmatched_reply_total | Replies not matching any pending correlation |
| late_reply_total | Replies arriving past deadline, if identified by the app |
| reply_consumer_lag | Lag of the reply listener container |

Include these fields in logs:

- requestId.
- correlationId.
- request topic/partition/offset.
- reply topic/partition/offset.
- target service.
- selected timeout.
- send time, receive time, and total latency.
- attempt number.
- idempotency status.

Do not log full payloads or sensitive data. Use requestId and correlationId to stitch traces across the requester, target service, and reply consumer.

If timeouts rise, inspect in order: send failures, request topic lag, service processing latency, reply publish latency, reply topic lag, and requester assignment/rebalances.

## 18. Testing Timeouts with EmbeddedKafka or Testcontainers

A good test models the moments when a request is sent, a reply is emitted, and the deadline expires.

Scenarios to include:

1. Reply arrives before timeout: future completes normally.
2. No reply: future completes exceptionally due to reply timeout.
3. Service processes slower than timeout: requester times out while server-side side effects may still complete.
4. Reply arrives after timeout: original future is gone; verify logs/metrics and late reply policy.
5. Producer fails to send request: send future reports failure separately from reply timeout.
6. Wrong or missing correlation ID: reply does not match the future.
7. Two concurrent requests: each reply completes the right future.
8. Shared reply topic with two requester instances: verify group IDs prevent replies going to the wrong instance.
9. Reply container not yet assigned: verify the app waits for assignment or fails startup cleanly.
10. Request retried after timeout: same requestId but new correlation ID; side effect runs only once.
11. Target service returns a business error: requester receives the error reply, not classified as a timeout.
12. Reply consumer rebalance: verify pending requests can time out and the cause is recorded.

Use latches, Awaitility, or future completion to synchronize tests. Do not use fixed Thread.sleep and assume the request has been processed. For late reply tests, deliberately delay the reply with a latch or controlled test service.

## 19. Common Pitfalls

**Treating a timeout as a guaranteed request failure.** The request may have been processed while the reply has not arrived. Use an indeterminate status and look up by requestId.

**Using only future.get(timeout).** This is only the caller's wait timeout and does not replace ReplyingKafkaTemplate's internal timeout. Configure default reply timeout or a per-request timeout.

**Using the same reply consumer group across multiple requester instances.** Kafka may deliver a reply to an instance without the matching correlation. Use separate groups or per-instance reply routing.

**Retrying immediately after a timeout without idempotency.** The first request may have already caused side effects. Keep requestId stable and deduplicate on the target service.

**Using one timeout for all request types.** Light lookups and heavy operations have different latencies. Use per-use-case timeouts while keeping an overall deadline.

**Ignoring the send future.** Producer send failures get misread as reply timeouts. Track the send phase separately.

**Not waiting for reply container assignment.** The reply container is not subscribed yet when requests go out. Wait for assignment before accepting traffic.

**Increasing timeouts to hide consumer lag.** Callers wait longer while the root cause persists. Monitor lag and per-hop latency.

**Not handling late replies.** Business outcomes can complete after the caller timed out. Store status by requestId if later queries or notifications are needed.

**Using correlation ID as request ID.** Retries generate new correlation IDs, breaking deduplication. Keep correlation ID separate from request ID.

**Leaving pending requests unbounded.** A slow target service can force the requester to hold too many futures. Bound concurrency and enforce finite timeouts.

## 20. Timeout Design Checklist

- [ ] ReplyingKafkaTemplate uses a reply listener container subscribed to the right topic.
- [ ] The reply container is assigned partitions before the requester accepts traffic.
- [ ] A bounded default timeout is configured.
- [ ] Critical requests can specify per-request timeouts.
- [ ] Send failures and reply timeouts are tracked separately.
- [ ] Timeouts match the latency budget and SLA.
- [ ] Caller timeouts are not confused with the template's internal timeout.
- [ ] Late replies have an observability or state-persistence policy.
- [ ] Request IDs remain stable across retries.
- [ ] Correlation IDs identify each individual request-reply exchange.
- [ ] The target service implements idempotency or an inbox by requestId.
- [ ] Retries are bounded with backoff and jitter.
- [ ] Reply consumer groups are properly designed when sharing a reply topic.
- [ ] Pending requests and reply consumer lag are monitored.
- [ ] Tests cover timely replies, timeouts, late replies, and send failures.

## Conclusion

ReplyingKafkaTemplate's timeout defines how long a requester waits for a reply; it does not cancel already sent requests and does not roll back business work on the target service. Configure a default reply timeout or per-request timeouts, monitor the send future to separate send errors from reply wait errors, and wait for reply container assignment before taking traffic. On timeout, the outcome is indeterminate; keep requestId stable across retries, use a distinct correlation ID per exchange, and protect side effects with idempotency. Combining overall deadlines, bounded retries, proper reply groups, and per-stage metrics keeps request-reply operations under control.

## References

- [Spring Kafka – Request/Reply Messaging](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html#replying-template)
- [Spring Kafka – ReplyingKafkaTemplate API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/ReplyingKafkaTemplate.html)
- [Spring Kafka – RequestReplyFuture API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/requestreply/RequestReplyFuture.html)
- [Apache Kafka – Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)

