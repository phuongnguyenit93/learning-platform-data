# Duplicate Triggers and Duplicate Barriers in Spring Integration

## 1. Problem: One Event Sent Twice

In an integration system, the event that **wakes up a waiting flow** can appear multiple times: the broker redelivers after a lost acknowledgment, an adapter retries, a producer resends due to a timeout, or two listeners receive the same event. Without clear design, a **duplicate trigger** can be interpreted as a completion signal for another execution. Likewise, two concurrent requests entering **the same barrier with the same correlation** create a conflict: both try to claim the waiting slot for a single key.

The lesson **"Duplicate Triggers and Duplicate Barriers"** belongs to the **Barrier** chapter of the **SPRING_INTEGRATION_PATTERN** module. This module teaches how to implement Enterprise Integration Patterns with Spring Integration, combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation to build loosely coupled, extensible, testable, and observable message flows. Here we specifically examine **Thread Barrier** and how to guard against the effects of duplicate messages.

After this lesson, you will be able to:

1. Explain how `BarrierMessageHandler` pairs requests and triggers by correlation.
2. Distinguish **duplicate request**, **duplicate trigger**, and **duplicate barrier endpoint**.
3. Understand the "one waiting request per correlation key at a time" constraint.
4. Analyze early triggers, late triggers, timeouts, and correlation key reuse.
5. Write tests using Java, JUnit 5, `ExecutorService`, and in-memory channels.
6. Design deduplication, `attemptId`, idempotency, and outcome tracking without mistaking them for built-in Barrier capabilities.

## 2. How Does Thread Barrier Work?

In Spring Integration, **`BarrierMessageHandler`** is a `MessageHandler` that also implements **`MessageTriggerAction`**. When a request enters the barrier, the request-processing thread can be suspended to wait for a trigger with a **matching correlation key**. When the trigger arrives and pairing succeeds, the barrier lets the thread continue and produces an output.

~~~mermaid
sequenceDiagram
    participant R as Request thread
    participant B as BarrierMessageHandler
    participant T as Trigger thread
    participant O as Output
    R->>B: request(correlation=A)
    Note over R,B: Request waits up to requestTimeout
    T->>B: trigger(correlation=A)
    B-->>R: release request A
    B-->>O: paired request + trigger result
~~~

Components to understand:

| Component | Function | What to test |
| --- | --- | --- |
| Request input | Flow needing to wait for an external condition | Is it waiting on the right correlation? |
| `BarrierMessageHandler` | Pairs request–trigger and wakes the flow | Does it release only when keys match? |
| Trigger input | Completion/acknowledgment signal | Can be duplicated, early, or late |
| `CorrelationStrategy` | Extracts the key from a message | Do request and trigger produce the same key? |
| `requestTimeout` | How long the request waits for a trigger | Handled per policy on expiration |
| `triggerTimeout` | How long the trigger waits for a request | Does not hold trigger thread forever |
| Discard channel | Receives expired triggers or triggers whose request never arrived in time, if configured | Are late/orphan triggers recorded? |
| Output processor | Builds the result after pairing | Does it contain the right data from request and trigger? |

**By default**, correlation is determined via the `IntegrationMessageHeaderAccessor.CORRELATION_ID` header. If you use a different business header name, configure an appropriate `CorrelationStrategy` for **both request and trigger**.

According to Spring Integration documentation, the default output payload is a **collection containing the request payload and the trigger payload**, with headers merged via `DefaultAggregatingMessageGroupProcessor`. This pairs **one request with one trigger**, not an Aggregator combining an arbitrary number of fragments.

## 3. Three Kinds of Duplicates to Separate

~~~mermaid
flowchart TD
    IN["Repeated event"] --> D{"What kind of repetition?"}
    D -->|"Repeated request with same correlation"| R["Duplicate request / pending barrier"]
    D -->|"Repeated ACK/trigger"| T["Duplicate trigger"]
    D -->|"Two independent Barrier endpoints"| B["Duplicate barrier instance"]
    R --> ER["Conflict on single waiting slot"]
    T --> ET["May become an orphan/late trigger"]
    B --> EB["Double release or side effects in two flows"]
~~~

### A. Duplicate Request Entering the Same Barrier

~~~text
Thread-1: request(key=order-7) -> already in barrier, waiting.
Thread-2: request(key=order-7) -> also tries to enter barrier.

Barrier allows only one waiting request for the same key.
The second request is rejected with an exception on concurrent correlation collision.
~~~

**This is documented Spring Integration behavior:** only one thread may be suspended for a given correlation at a time; another concurrent request using the same key raises an exception. That correlation **can be reused later**, once no request is waiting on it. Therefore, this limit **is not permanent idempotency**.

### B. Duplicate Trigger for One Request

~~~text
Request A is waiting.
Trigger A (1st time) -> releases Request A.
Trigger A (2nd time) -> Request A is no longer there to release.
~~~

Do not assume the second trigger will automatically be recognized as a duplicate. It may fall into the **early trigger** branch of a new pairing round, wait up to `triggerTimeout`, or be routed to the discard channel depending on configuration and timing. By default, a barrier **does not replace** a system tracking already-processed business ACKs.

### C. Two Barrier Instances or Two Flows Handling the Same Request

~~~text
Barrier instance A receives request order-7 and trigger order-7.
Barrier instance B receives the same request order-7 and trigger order-7.

If both flows operate independently, both can emit output.
~~~

The single-pending-correlation limit belongs to **each handler's state management**; it does not automatically guarantee "single execution" across **the entire application, all replicas, and all broker consumers**. When deploying multiple instances, you need a clear owner, key-based partitioning, or idempotency at side-effect boundaries.

## 4. Behavior Matrix and Expected Contracts

| Scenario | Event sequence | What to observe |
| --- | --- | --- |
| Normal | Request A → Trigger A | One result for A |
| Non-matching trigger | Request A → Trigger B | A is not released by B |
| Concurrent duplicate request | Request A → Another Request A | One pending A; duplicate request errors out |
| Duplicate trigger after completion | Request A → Trigger A → Second Trigger A | No second business output for A |
| Trigger arrives first | Trigger A → Request A | Can pair if request arrives within `triggerTimeout` |
| Early trigger with no request | Trigger A → `triggerTimeout` expires | Trigger handled as expired/discarded per config |
| Request times out before trigger | Request A → `requestTimeout` expires → Trigger A | Timed-out A does not revive into success |
| Reusing correlation for new attempt | A/attempt-1 finishes → A/attempt-2 | Old trigger must not wrongly open new attempt |
| Two barrier instances | A and B both receive same request/trigger | No double side effects outside policy |
| Retry/redelivery | ACK is redelivered | Deduplication or idempotency takes effect |

Distinguish **framework behavior** from **business requirements**: by default Barrier manages pairing within a wait window; guaranteeing that an order is processed only once requires additional design.

## 5. Two Independent Timeouts and a Subtle Risk

Since Spring Integration 5.4, Barrier supports separate **`requestTimeout`** and **`triggerTimeout`**:

- `requestTimeout`: how long the request thread waits for a trigger.
- `triggerTimeout`: how long the trigger thread waits for a request if the trigger arrives early or arrives after the request already timed out.

~~~mermaid
sequenceDiagram
    participant T as Trigger thread
    participant B as Barrier
    participant R as Request thread
    T->>B: trigger(A)
    Note over T,B: Wait up to triggerTimeout
    alt Request A arrives in time
        R->>B: request(A)
        B-->>R: release
    else No request arrives
        Note over T,B: triggerTimeout expires
        B-->>T: stop waiting
        Note over B: discard trigger if discard channel configured
    end
~~~

**Subtle hazard:** A leftover trigger from an old attempt may still be waiting. If a new attempt uses the **same correlation** before the old trigger expires, there is a risk of mis-pairing. A safer approach is keying by **each attempt** or **each operation**:

~~~text
Not safe enough on retries:
  correlationId = "tenant-a:order-7"

Distinguish each attempt:
  correlationId = "tenant-a:order-7:attempt-1"
  correlationId = "tenant-a:order-7:attempt-2"
~~~

When using `attemptId`, the request and trigger of the **same attempt** must use the same key; triggers from an old attempt must not produce output for a new attempt. At the same time, you still need an independent **business idempotency key** (for example `tenantId + orderId`) to avoid creating an order twice across attempts.

## 6. Configuring Barrier with Separate Request and Trigger Paths

The following example uses **Spring Integration 6.x**, Java 17, and in-memory channels. The request and trigger paths are configured separately yet share **a single `BarrierMessageHandler`**.

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.aggregator.BarrierMessageHandler;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageHandler;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
@EnableIntegration
public class BarrierConfiguration {

    @Bean("barrier.requests")
    DirectChannel requestChannel() {
        return new DirectChannel();
    }

    @Bean("barrier.triggers")
    DirectChannel triggerChannel() {
        return new DirectChannel();
    }

    @Bean("barrier.released")
    QueueChannel releasedChannel() {
        return new QueueChannel();
    }

    @Bean("barrier.discard")
    QueueChannel discardedTriggers() {
        return new QueueChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "barrier.requests")
    BarrierMessageHandler barrierHandler(
            @Qualifier("barrier.released") QueueChannel released,
            @Qualifier("barrier.discard") QueueChannel discarded) {
        // Request waits at most 3 seconds; early trigger waits 250 ms.
        BarrierMessageHandler barrier =
                new BarrierMessageHandler(3_000L, 250L);
        barrier.setOutputChannel(released);
        barrier.setDiscardChannel(discarded);
        return barrier;
    }

    @Bean
    @ServiceActivator(inputChannel = "barrier.triggers")
    MessageHandler triggerHandler(BarrierMessageHandler barrierHandler) {
        return barrierHandler::trigger;
    }
}
~~~

When calling `send()` on `barrier.requests`, **the sending thread may block** until a matching trigger arrives or `requestTimeout` expires. Therefore, never write a test that calls `requests.send(...)` on the JUnit thread and then calls `triggers.send(...)` on the **same thread**: the test will get stuck at the request and never reach the trigger statement. You must use different threads or an appropriate asynchronous structure.

If you prefer XML, the equivalent configuration looks like:

~~~xml
<int:barrier id="myBarrier"
             input-channel="barrierRequests"
             output-channel="barrierReleased"
             correlation-strategy-expression="headers['correlationId']"
             discard-channel="barrierDiscard"
             request-timeout="3000"
             trigger-timeout="250"/>

<int:outbound-channel-adapter input-channel="barrierTriggers"
                              ref="myBarrier.handler"
                              method="trigger"/>
~~~

This is an **illustrative XML configuration sketch**; when using real XML, include the namespaces/schemas and verify that the timeout attributes match your project's Spring Integration version. With the Java configuration above, the default key uses `IntegrationMessageHeaderAccessor.CORRELATION_ID`.

## 7. Attaching Correlation and Creating Minimal Messages

Two messages with different payloads but the same correlation:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

static Message<String> request(String key) {
    return MessageBuilder.withPayload("work:" + key)
            .setHeader(
                    IntegrationMessageHeaderAccessor.CORRELATION_ID, key)
            .setHeader("requestId", key)
            .build();
}

static Message<String> trigger(String key) {
    return MessageBuilder.withPayload("ack:" + key)
            .setHeader(
                    IntegrationMessageHeaderAccessor.CORRELATION_ID, key)
            .setHeader("eventType", "ACK")
            .build();
}
~~~

`requestId` is a business tracking header; `correlationId` is the key the Barrier uses for pairing. In this example, we intentionally give them the same value for readability, but **they do not have to be identical**.

If you embed `tenantId` or `attemptId` into the key, do so consistently on both request and trigger. Avoid cases where the request carries String `"7"` while the trigger carries Integer `7`: they may look identical in logs, yet the two keys will not compare equal.

## 8. JUnit 5 Example: Testing Duplicate Requests and Duplicate Triggers

The tests below spin up a real **Spring context**, send requests through `DirectChannel`, and read results from `QueueChannel`. You can use these dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

In a real project, place `BarrierConfiguration` from section 6 in an appropriate package and create `BarrierDuplicateTest`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(BarrierConfiguration.class)
class BarrierDuplicateTest {

    @Autowired
    @Qualifier("barrier.requests")
    MessageChannel requests;

    @Autowired
    @Qualifier("barrier.triggers")
    MessageChannel triggers;

    @Autowired
    @Qualifier("barrier.released")
    QueueChannel released;

    @Autowired
    @Qualifier("barrier.discard")
    QueueChannel discard;

    private final ExecutorService workers =
            Executors.newFixedThreadPool(3);

    @AfterEach
    void shutdown() {
        workers.shutdownNow();
    }

    static Message<String> msg(String payload, String correlation) {
        return MessageBuilder.withPayload(payload)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        correlation)
                .build();
    }

    @Test
    void one_request_and_one_trigger_produce_one_result()
            throws Exception {
        Future<Boolean> pending = workers.submit(() ->
                requests.send(msg("work-A", "job-A")));

        // Trigger may arrive before the request actually suspends;
        // triggerTimeout lets both sides meet within the window.
        assertThat(triggers.send(msg("ack-A", "job-A"))).isTrue();
        assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();

        Message<?> output = released.receive(1_000);
        assertThat(output).isNotNull();
        assertThat(output.getPayload()).isInstanceOf(Collection.class);
        assertThat(((Collection<?>) output.getPayload()).stream()
                .map(Object::toString).toList())
                .contains("work-A", "ack-A");
        assertThat(released.receive(0)).isNull();
        assertThat(discard.receive(0)).isNull();
    }

    @Test
    void duplicate_trigger_after_completion_does_not_release_again()
            throws Exception {
        Future<Boolean> pending = workers.submit(() ->
                requests.send(msg("work-D", "job-D")));
        assertThat(triggers.send(msg("ack-D", "job-D"))).isTrue();
        assertThat(pending.get(2, TimeUnit.SECONDS)).isTrue();

        assertThat(released.receive(1_000)).isNotNull();
        // No request D is waiting anymore; the second trigger is not
        // a new completion event for the already-finished request.
        triggers.send(msg("ack-D-again", "job-D"));

        // Configuration has a discard channel and finite triggerTimeout.
        Message<?> discarded = discard.receive(1_000);
        assertThat(discarded).isNotNull();
        assertThat(discarded.getPayload()).isEqualTo("ack-D-again");
        assertThat(released.receive(0)).isNull();
    }

    @Test
    void simultaneous_duplicate_requests_cannot_both_wait()
            throws Exception {
        ExecutorCompletionService<Throwable> completions =
                new ExecutorCompletionService<>(workers);
        CountDownLatch start = new CountDownLatch(1);

        for (int i = 0; i < 2; i++) {
            completions.submit(() -> {
                start.await();
                try {
                    requests.send(msg("work-X", "job-X"));
                    return null;
                } catch (RuntimeException failure) {
                    return failure;
                }
            });
        }

        start.countDown();
        // One of the two calls finishes before any trigger arrives.
        // Per the Barrier contract, this call must report a duplicate-key error.
        Future<Throwable> first = completions.poll(
                1_500, TimeUnit.MILLISECONDS);
        assertThat(first).isNotNull();
        assertThat(first.get()).isNotNull();

        // Release the valid request that is still waiting.
        assertThat(triggers.send(msg("ack-X", "job-X"))).isTrue();
        Future<Throwable> second = completions.poll(
                2, TimeUnit.SECONDS);
        assertThat(second).isNotNull();
        assertThat(second.get()).isNull();
        assertThat(released.receive(1_000)).isNotNull();
        assertThat(released.receive(0)).isNull();
    }
}
~~~

### Interpreting the Tests

- **Happy path:** One request and one trigger sharing a correlation key produce one output. The test checks both request and trigger payloads without constraining collection element order unless that is part of the business contract.
- **Duplicate trigger:** Sends the second trigger only after the first request has completed. With `discardChannel` and `triggerTimeout` configured, the test observes it on the discard path and ensures no second release occurs.
- **Duplicate request:** Two requests are launched concurrently with the same correlation; one fails due to the single-pending-thread limit, and then a trigger releases the remaining request.

**Test limitations:** This example uses timeouts short enough to run quickly in tests, which may still be affected by overloaded CI machines or library versions. Avoid asserting **exact exception message text**; prefer asserting state, total output count, and error types where the contract is known. If concurrency tests are timing-sensitive, add a hook controlling when the request enters the handler before asserting the exception.

## 9. Testing Correlation and Early Triggers

Not all duplicates have the same timing implications. Consider two cases:

### Trigger with Wrong Correlation

~~~text
Request: correlation=order-11:attempt-1
Trigger: correlation=order-12:attempt-1

Expectation: trigger for order-12 does not release request order-11.
~~~

In tests, send request A on one thread and trigger B on another. Trigger B can wait until `triggerTimeout` and go to the discard channel, while A keeps waiting. Then send trigger A and verify A produces output. Never use `receive(0) == null` alone as final proof while both sides are running asynchronously; wait for controlled processing checkpoints.

### Trigger Arrives Before Request

~~~text
t0: Trigger A arrives first, begins waiting up to triggerTimeout.
t1: Request A arrives within the limit.
t2: Both sides pair and the request is released.
~~~

An early trigger can be **valid** if the protocol permits it. However, in systems where triggers represent ACKs after a request is sent, an early trigger is sometimes a sign of an old or duplicate message. In that case, policy may **reject early triggers** instead of letting the Barrier hold them, or accept them only if a valid registered request state exists.

## 10. Why Relying on `correlationId` Alone Is Not Enough

Here is a scenario that easily causes subtle bugs:

~~~mermaid
sequenceDiagram
    participant R as Request flow
    participant B as Barrier
    participant T as Trigger source
    R->>B: order-7, attempt=1
    T->>B: ACK attempt=1
    B-->>R: release attempt=1
    T->>B: ACK attempt=1 is resent
    Note over T,B: Leftover trigger waits for some time
    R->>B: order-7, attempt=2 (reuses old key)
    Note over B: Risk of pairing old trigger with new request
~~~

The solution is not merely increasing `requestTimeout`. Define two categories of keys:

| Key | Scope | Purpose |
| --- | --- | --- |
| `operationKey` | One business operation across retries | Idempotency, preventing repeated side effects |
| `correlationId` | One specific request/trigger exchange | Pairing the exact request and ACK |
| `attemptId` | One attempt within an operation | Preventing old triggers from pairing with new attempts |
| `eventId` | One logical ACK event | Detecting redeliveries of the same ACK |

Example:

~~~text
operationKey  = tenant-a/order-7
attemptId     = 2
correlationId = tenant-a/order-7/attempt-2
eventId       = broker-ack-event-813
~~~

On retry, **operationKey stays the same**, while **correlationId changes** per attempt if the protocol emits per-attempt ACKs. The system must know that an ACK for `attempt-1` is ineligible to open `attempt-2`.

Spring Integration does not automatically invent conventions for these keys. Producers, adapters, Routers/Transformers, and consumers must agree on them and propagate all headers intact.

## 11. Blocking Duplicate Triggers Before the Barrier

**Idempotent Receiver** is an Enterprise Integration Pattern for cases where messages are redelivered. Spring Integration provides mechanisms such as `IdempotentReceiverInterceptor`, `MetadataStoreSelector`, and `ConcurrentMetadataStore` to filter out already-seen messages.

For ACKs/triggers, a suitable deduplication key is often:

~~~text
tenantId + operationKey + attemptId + logicalAckType
~~~

Do not pick **the random message ID of each redelivery** if the broker generates a new message per retry: two copies of the same business ACK will get different IDs and fail to be recognized as duplicates.

Example of a plain Java gate checking ACKs before forwarding to the trigger channel:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

final class AckAdmission {

    private final Set<String> accepted =
            ConcurrentHashMap.newKeySet();

    boolean accept(
            String tenantId,
            String operationId,
            int attemptId,
            String ackType) {
        String key = tenantId + "/" + operationId + "/"
                + attemptId + "/" + ackType;
        return accepted.add(key);
    }
}
~~~

And a unit test:

~~~java
@Test
void duplicate_ack_for_same_attempt_is_rejected() {
    AckAdmission admission = new AckAdmission();

    assertThat(admission.accept("t1", "order-7", 1, "BROKER_ACK"))
            .isTrue();
    assertThat(admission.accept("t1", "order-7", 1, "BROKER_ACK"))
            .isFalse();
    assertThat(admission.accept("t1", "order-7", 2, "BROKER_ACK"))
            .isTrue();
}
~~~

**Very important:** This is only a **single-JVM dedup model**, not a complete production solution. It has limitations:

1. Does not share state across multiple replicas or across restarts.
2. Has no TTL, causing the `accepted` set to grow unboundedly.
3. Marking as seen **before calling `trigger()`** can lose retry opportunities if the trigger fails or hits `triggerTimeout`.
4. Has no states distinguishing `RECEIVED`, `MATCHED`, `COMPLETED`, `EXPIRED`.
5. Joining keys with `/` can cause collisions if component values are unnormalized; use a typed key structure or safe encoding.

In real production systems, define **when dedup state commits** and its atomicity with side effects. Depending on infrastructure, use a durable metadata store, transactions, outbox/inbox, or an explicit state machine. A dedup record before the barrier might only be `RECEIVED`, transitioning to `COMPLETED` once the Barrier pairs successfully. Error/timeout handling must provide a recovery path instead of locking the key forever.

## 12. Two Independent Barrier Instances: Another Kind of Duplicate

Suppose two service replicas both consume messages from publish-subscribe:

~~~mermaid
flowchart TD
    REQ["Request order-7"] --> A["Barrier A"]
    REQ --> B["Barrier B"]
    ACK["ACK order-7"] --> A
    ACK --> B
    A --> OA["Release A"]
    B --> OB["Release B"]
    OA --> E["Side effect"]
    OB --> E
~~~

Each Barrier can independently pair its own request and trigger. **There is no global once-only guarantee merely because correlation IDs match.** Depending on requirements, you can:

- Elect **a single owner** per operation/correlation.
- Partition by correlation so all messages for the same operation reach the appropriate single consumer.
- Use competing consumers to distribute work, rather than broadcasting the same work to every instance.
- Persist business state with a unique constraint and check idempotency before executing side effects.
- Test when scaling from one to multiple replicas, during failover, and under redelivery.

A misconception to avoid: a **duplicate barrier instance** does not necessarily mean "calling the same `BarrierMessageHandler` twice." It can be two separate handlers in two Spring contexts or a flow accidentally registering an equivalent endpoint twice. Inspect both wiring and subscriber counts, not just a single bean test.

## 13. Retries, Timeouts, and Error Paths

A Barrier can stop waiting either due to a timeout or due to a trigger. Per documentation, the `requiresReply` property governs behavior on **request timeout**:

- `requiresReply=false` (default): the handler produces no reply and the flow stops there.
- `requiresReply=true`: throws `ReplyRequiredException`.

A trigger arriving too late can be routed to the **discard channel** if configured. However, discarding does not mean the message was durably persisted or handled by business logic. If the discard channel itself fails, you need a separate policy.

~~~text
Request A -> Barrier -> timeout
                         |
                         +--> no reply or exception depending on requiresReply

Trigger A arrives later -> waits triggerTimeout if no request exists
                         |
                         +--> discard channel if configured
~~~

Note that **a Barrier timeout differs from a Gateway's `replyTimeout`**. The Gateway may time out first while the Barrier's request thread keeps waiting; or the Barrier may time out and the Gateway receives no reply. Tests must verify the end-to-end timeout budget and late-result policy rather than equating the two thresholds.

### Retrying After the Barrier Has Already Released

A duplicate trigger does not necessarily produce a second output from **the same completed request**. However, if a retry creates a new request with the same correlation, a leftover or redelivered trigger can pair with the new request. Therefore:

1. Separate `operationId` and `attemptId`.
2. Deduplicate logical ACKs per attempt or defined event.
3. Maintain explicit terminal states for operations.
4. Ensure side effects are idempotent even if Gateways or workers retry.
5. Add metrics and logs for duplicate/late/orphan triggers.

## 14. Concurrency and Testing Pitfalls

| Mistake | Why it is dangerous | How to test/fix |
| --- | --- | --- |
| Sending request then trigger sequentially on the same DirectChannel thread | Thread blocks at Barrier and never reaches trigger | Send from a separate thread |
| Using `Thread.sleep` to guess when a request entered the barrier | Test becomes scheduler-dependent | Use latches, controllable channels, finite timeouts |
| Assuming duplicate triggers are silently ignored | May wait or collide with a new attempt's request | Deduplicate and correlate by attempt |
| Testing only one happy-path request/trigger | Misses duplicates and cross-correlation | Test double trigger / double request |
| Comparing all output headers against request headers | Framework merges metadata | Assert required business keys and payloads |
| Using orderId alone as correlation across retries | Old trigger can affect new retry | Include attempt/version in correlation |
| Relying on one handler to guarantee exactly-once | Multiple instances still have separate state | Idempotent side effects and clear ownership |
| Ignoring `triggerTimeout` | Early triggers can hold threads | Set dedicated timeout, bounded worker pool |
| Tracking only success counts | Hides duplicates/orphans | Add metrics and discard channel |
| Failing to clean up executors and pending state | Subsequent tests get polluted | `shutdownNow()`, unique correlations, cleanup |

## 15. Metrics and Traces to Add

Useful indicators:

| Metric | Meaning | Usage |
| --- | --- | --- |
| `barriers_waiting` | Number of requests waiting for a trigger | Alert on backlog / blocked threads |
| `barrier_request_timeout_total` | Requests exceeding deadline | Break down by flow and business group |
| `barrier_trigger_timeout_total` | Triggers that failed to meet a request in time | Detect stale/orphan triggers |
| `barrier_duplicate_request_total` | Concurrent requests arriving with same key | Detect producer retries/races |
| `barrier_duplicate_trigger_total` | Redelivered ACKs | Inspect broker, retries, adapters |
| `barrier_late_trigger_total` | Expired/discarded triggers | Reconcile wait windows |
| `barrier_release_total` | Successful barrier pairings | Track completion rate |
| `barrier_wait_seconds` | Release wait latency | Evaluate SLA and thread utilization |

These are **suggested metric names**, not claims that Spring Integration emits these exact names out of the box. Label by endpoint/route/error type with reasonable cardinality; never use per-event `requestId` or `correlationId` as metric labels. Instead, record these keys in **structured logs/traces** for investigation.

For error logs, include `operationId`, `attemptId`, `correlationId`, status, and cause; avoid logging sensitive payloads or tokens.

## 16. Practice Exercises

### Exercise A — Reproducing Duplicate Triggers

Create a Barrier with `requestTimeout=3_000`, `triggerTimeout=250`, and a discard channel. Send request A and trigger A, confirming exactly one output. After the request finishes, resend trigger A. Verify no second output is emitted and the extra trigger is observed according to your actual discard/error policy.

### Exercise B — Two Concurrent Requests with the Same Correlation

Create two producer threads that both send requests with correlation `"job-17"` to the same handler. The test must show that only one request suspends; the other fails per the Barrier's limit. Send a single trigger to release the valid request. Apply finite timeouts to all futures.

### Exercise C — Old Trigger and New Retry Attempt

For operation `order-7`, model attempt 1 and attempt 2. After attempt 1 completes, resend the attempt-1 ACK; then start the attempt-2 request. Design correlation to include the attempt ID, confirming the old ACK does not release attempt 2. Only the attempt-2 ACK produces valid output.

### Exercise D — Early Trigger

Send trigger `"job-21"` before the request. With a finite `triggerTimeout`, test two cases: the request arrives in time and both sides pair; the request never arrives, causing the trigger to enter the discard channel or corresponding expiration path.

### Exercise E — Duplicated Barrier Across Two Instances

Set up two independent Barrier configurations, simulating the same request/ACK broadcast to both. Verify that both can release without global ownership/idempotency. Then add operation ownership or side-effect deduplication so total business executions match the contract.

### Exercise F — Durable Deduplication

Pass ACKs through a `MetadataStoreSelector` or durable inbox keyed by `tenant + operation + attempt + ACK type`. Test redelivery of the same ACK, retries while incomplete, and pruning expired records without allowing an old trigger to open a new attempt.

## 17. Completion Criteria

A Barrier flow is thoroughly tested for duplicates when it can prove:

1. Request and trigger with matching correlation pair into **one valid result**.
2. A trigger with a different correlation never mistakenly releases a request.
3. Two concurrent requests with the same correlation cannot both occupy the waiting state.
4. Duplicate triggers do not produce extra business outputs violating the contract.
5. Early or expired triggers are handled according to `triggerTimeout`/discard policy.
6. Retries use attempt/version so old triggers cannot mistakenly open new requests.
7. Two handlers/replicas do not cause duplicate side effects when the business requires application-level exactly-once.
8. Tests use finite timeouts, proper thread management, and logs/metrics for tracing duplicates.

**Conclusion:** `BarrierMessageHandler` manages correlation-based pairing and signal waiting; it **does not automatically become a distributed deduplicator**. Distinguishing between duplicate waiting requests, duplicate triggers after completion, and duplicate barrier instances dictates the right solution. By adding per-attempt correlation, stateful deduplication, idempotent side effects, clear timeouts/discards, and concurrency tests, a Spring Integration flow can continue safely even when brokers, Gateways, or adapters redeliver messages.

### References

- [Spring Integration Reference — Thread Barrier](https://docs.spring.io/spring-integration/reference/6.5/barrier.html): request/trigger mechanism, correlation, timeouts, discard, and the single-pending-request-per-correlation limit.
- [Spring Integration API — BarrierMessageHandler (6.4.x)](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/aggregator/BarrierMessageHandler.html): constructors, `trigger()`, `setDiscardChannel()`, and output processor.
- [Spring Integration API — MessageTriggerAction](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/handler/MessageTriggerAction.html): trigger interface.
