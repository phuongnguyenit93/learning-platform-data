# Testing Reply Timeout and Late Reply in Spring Integration

## 1. Objectives and Context

In a **request–reply** flow, the sender dispatches a request and waits for a result from another processing branch. Typical participants include **Gateway**, **Message Channel**, **Service Activator**, **Router**, **Transformer**, and asynchronous processing steps. If a reply does not arrive on time, the Gateway must have a way to stop waiting. However, the dispatched request may **still be executing**, and the reply may arrive **after the caller has already timed out**.

Those are two separate concerns to test independently:

1. **Reply timeout:** The caller stops waiting according to policy when no reply arrives before the deadline.
2. **Late reply:** A late result must not be mistaken for a new request's reply, must not retroactively turn a timed-out request into a success, and must be handled/observed according to business policy.

The lesson **"Testing Reply Timeout and Late Reply"** belongs to the **Pattern Testing** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows—combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation—while testing and tracing each processing branch.

After this lesson, you will be able to:

- Distinguish \`requestTimeout\` from \`replyTimeout\` and business/HTTP-layer timeouts.
- Understand why an **asynchronous boundary** is needed to bound a Gateway's wait time when a handler runs slowly.
- Write deterministic tests for on-time replies, missing replies, and late replies.
- Use \`requestId\` or a correlation key to prevent matching a reply to the wrong request.
- Define policies for late results, retries, side effects, downstream errors, and timeouts.
- Test using finite timeouts, synchronization signals, and isolation rather than arbitrary \`Thread.sleep\` calls.

## 2. Request–Reply Lifecycle Diagram

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant Q as Request Channel
    participant W as Worker
    C->>G: request(id=A)
    G->>Q: send request(A)
    Q-->>W: deliver request(A)
    Note over G: Wait for reply within deadline
    alt Reply arrives on time
        W-->>G: reply(A)
        G-->>C: result A
    else replyTimeout expires before reply arrives
        G-->>C: null / timeout error per config
        Note over W: Worker may still be running
        W-->>G: late reply(A)
        Note over G,W: Do not turn a timed-out result into success
    end
~~~

Timeline markers:

~~~text
t0: Caller invokes Gateway with request A
t1: Request is accepted into the channel
t2: Gateway begins waiting for a reply (after send/handoff returns)
t3: replyTimeout expires => caller stops waiting
t4: Downstream produces reply A, but A has already timed out

If t4 < t3: on-time reply.
If t4 > t3: late reply.
If t4 is near t3: outcome may depend on actual runtime race ordering.
~~~

**Do not define "late" solely by worker execution duration.** When waiting starts, queue latency, thread scheduling, network, broker, and reply transmission time can all affect whether the result reaches the caller in time.

## 3. Distinguishing Request Timeout and Reply Timeout

Spring Integration Gateways have two key timeout settings:

| Property | Which Phase It Protects | Common Case |
| --- | --- | --- |
| \`requestTimeout\` | Wait time when **sending a request** to a potentially blocking channel | A bounded \`QueueChannel\` is full |
| \`replyTimeout\` | Time the Gateway **waits for a reply** after send/handoff returns control | Downstream has not produced a reply or no branch returns one |

Gateway interface example, Java 17 with Spring Integration 6.2+:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway(
        defaultRequestChannel = "orders.requests",
        defaultRequestTimeout = "200",
        defaultReplyTimeout = "500")
public interface OrderGateway {

    String submit(String orderId);

    // Can override for a specific method.
    @Gateway(requestTimeout = 100, replyTimeout = 1000)
    String submitSlowAllowed(String orderId);
}
~~~

The numbers above are in **milliseconds** and are illustrative only. With annotation-based configuration, enable \`@IntegrationComponentScan\` in your Spring configuration to discover \`@MessagingGateway\` interfaces; standard \`@ComponentScan\` does not fully replace this scan.

**Key takeaway:** \`requestTimeout=200\` does not mean downstream must finish within 200 ms. If sending into the channel succeeds immediately, request timeout has virtually no effect on how long the caller waits for a result. Conversely, \`replyTimeout=500\` does not guarantee the request is cancelled once the caller stops waiting.

### Default Timeouts Should Not Be Used as an Implicit Contract

Default values depend on the Spring Integration version, Gateway type, and endpoint configuration. For example, 6.x API releases have historical differences in \`defaultReplyTimeout\` defaults; inbound HTTP/JMS Gateways also have their own specifics. Always **configure explicit timeouts** on flows or gateways with SLAs, and test those exact values.

## 4. Why replyTimeout May Fail to Cut Off a Slow Handler

A common misconception is setting \`replyTimeout=100\` and expecting the Gateway to return after 100 ms even when a synchronous Service Activator takes 2 seconds.

### Synchronous Flow on a DirectChannel

~~~mermaid
flowchart LR
    G["Gateway / caller thread"] --> D["DirectChannel"]
    D --> H["Service Activator\nslow processing"]
    H --> R["Reply"]
~~~

With \`DirectChannel\`, the handler typically runs **on the exact thread calling send**. The Gateway must wait for \`send()\` to complete before entering the reply-wait phase. If downstream blocks inside the handler, \`replyTimeout\` **does not interrupt or cancel** that execution.

### With an Asynchronous Boundary

~~~mermaid
flowchart LR
    G["Gateway"] --> Q["QueueChannel"]
    Q --> W["Worker / Poller"]
    W --> R["Reply Channel"]
    R --> G
~~~

When the request is enqueued quickly and a worker processes it **on another thread**, the caller can wait up to \`replyTimeout\` on the Gateway side. An equivalent boundary can be created with \`ExecutorChannel\` or an adapter/broker, depending on the flow.

Remember that a Gateway timeout is **not a worker cancellation command**. Even after the caller receives a timeout, the worker can still:

- Write data to a database.
- Call an external service.
- Retry transient failures.
- Send a late reply.
- Send an exception to an error channel after the deadline has passed.

Tests must verify these side effects whenever they are part of the business contract.

## 5. Defining the Test Contract Before Writing Code

Suppose an application processes requests with \`requestId\` and expects a reply within a 200 ms deadline:

| Case | Condition | Expected Outcome at Caller | What to Observe Downstream |
| --- | --- | --- | --- |
| On-time reply | Worker sends reply before deadline | Caller receives reply for matching request | One reply, valid payload/headers |
| No reply | Worker emits nothing | Gateway stops waiting per timeout policy | Request may still exist |
| Late reply | Worker replies after caller timeout | Caller is not updated to success | Late reply is classified/recorded |
| Two independent requests | A times out, B replies on time | B receives only reply B | No mixing of A/B correlation |
| Slow synchronous handler | Handler blocks caller thread | Reply timeout does not guarantee interrupting handler | Thread boundary clearly visible |
| Bounded request queue full | \`send\` cannot enqueue | Send failure handled per requestTimeout | Request not treated as processed |
| Downstream failure | Handler throws exception | Error policy instead of silent waiting | Exception/error channel has context |
| Retry after timeout | Caller resends same request | No unintended duplicate side effects | Proper idempotency or deduplication |

A good test typically requires **two kinds of assertions**:

1. **Caller-facing:** Caller receives the payload, \`null\`, or an exception per configured policy.
2. **System-facing:** The request may still be running; late results are never misattributed, and side effects are never duplicated.

Never assert only \`null\` and conclude that the entire business operation failed or rolled back.

## 6. Setting Up a Brokerless Test Environment

We can test timeout logic at the messaging level using:

- \`QueueChannel requests\`: stores requests, decoupling caller and worker threads.
- \`MessagingTemplate\`: performs \`sendAndReceive\` with an **explicit receive timeout**, mirroring the Gateway's request–reply concept.
- \`ExecutorService\`: runs callers on separate threads so the test actively observes requests.
- \`replyChannel\` header: temporary channel attached by \`MessagingTemplate\` to the request message to receive replies.
- \`requestId\` header: business identifier indicating which request is being processed.

Unlike a sleep-based timing test, this test precisely controls **when a reply is sent**. When verifying that the caller has timed out, the test waits for the \`Future\` to finish before sending the late reply.

With Spring Boot, compatible dependencies typically include:

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
</dependencies>
~~~

The following examples target Spring Integration 6.x, Java 17, JUnit 5, and AssertJ. They demonstrate **MessagingTemplate request–reply** semantics; for \`@MessagingGateway\` proxies, add dedicated integration tests covering the proxy and \`errorOnTimeout\` for your specific version.

## 7. Complete Java Example: On-Time, Timeout, Late Reply, and Correlation

Create class \`src/test/java/example/ReplyTimeoutAndLateReplyTest.java\`:

~~~java
package example;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

class ReplyTimeoutAndLateReplyTest {

    private final ExecutorService callers =
            Executors.newFixedThreadPool(2);
    private final QueueChannel requests = new QueueChannel();

    @AfterEach
    void shutdown() {
        callers.shutdownNow();
    }

    private Future<Message<?>> startCall(
            String requestId, long replyTimeoutMs) {
        return callers.submit(() -> {
            MessagingTemplate template = new MessagingTemplate();
            template.setSendTimeout(500);
            template.setReceiveTimeout(replyTimeoutMs);
            Message<String> message = MessageBuilder
                    .withPayload("payload-" + requestId)
                    .setHeader("requestId", requestId)
                    .build();
            return template.sendAndReceive(requests, message);
        });
    }

    private Message<?> nextRequest() {
        Message<?> request = requests.receive(1_000);
        assertThat(request).isNotNull();
        return request;
    }

    private static MessageChannel replyTo(Message<?> request) {
        Object destination = request.getHeaders().getReplyChannel();
        assertThat(destination)
                .as("Gateway-style request needs a replyChannel")
                .isInstanceOf(MessageChannel.class);
        return (MessageChannel) destination;
    }

    private static void sendReply(
            Message<?> request, String payload) {
        Message<String> reply = MessageBuilder.withPayload(payload)
                .setHeader(
                        "requestId",
                        request.getHeaders().get("requestId"))
                .build();
        assertThat(replyTo(request).send(reply)).isTrue();
    }

    @Test
    void reply_before_timeout_is_returned_to_caller()
            throws Exception {
        Future<Message<?>> call = startCall("A", 1_000);
        Message<?> incoming = nextRequest();

        assertThat(incoming.getHeaders().get("requestId"))
                .isEqualTo("A");
        sendReply(incoming, "accepted-A");

        Message<?> reply = call.get(2, TimeUnit.SECONDS);
        assertThat(reply).isNotNull();
        assertThat(reply.getPayload()).isEqualTo("accepted-A");
        assertThat(reply.getHeaders().get("requestId")).isEqualTo("A");
        assertThat(requests.receive(0)).isNull();
    }

    @Test
    void missing_reply_causes_receive_timeout()
            throws Exception {
        Future<Message<?>> call = startCall("NO-REPLY", 150);
        Message<?> incoming = nextRequest();
        assertThat(incoming.getHeaders().get("requestId"))
                .isEqualTo("NO-REPLY");

        // Send no reply. Caller stops waiting.
        assertThat(call.get(2, TimeUnit.SECONDS)).isNull();
        assertThat(requests.receive(0)).isNull();

        // Timing out does not mean the worker was cancelled:
        // the incoming variable still represents the dequeued request.
        assertThat(incoming.getPayload()).isEqualTo("payload-NO-REPLY");
    }

    @Test
    void late_reply_does_not_turn_timed_out_call_into_success()
            throws Exception {
        Future<Message<?>> callA = startCall("A", 150);
        Message<?> requestA = nextRequest();

        // Prove A timed out BEFORE sending the late reply.
        assertThat(callA.get(2, TimeUnit.SECONDS)).isNull();

        Message<String> lateA = MessageBuilder
                .withPayload("late-result-A")
                .setHeader("requestId", "A")
                .build();

        // The temporary reply destination may accept, reject, or fail
        // after the caller stops waiting, depending on endpoint/version.
        try {
            replyTo(requestA).send(lateA);
        } catch (MessagingException expiredReplyDestination) {
            // Expected possible outcome for an expired reply.
        }

        // B is a separate request with B's own replyChannel.
        Future<Message<?>> callB = startCall("B", 1_000);
        Message<?> requestB = nextRequest();
        assertThat(requestB.getHeaders().get("requestId"))
                .isEqualTo("B");
        sendReply(requestB, "accepted-B");

        Message<?> resultB = callB.get(2, TimeUnit.SECONDS);
        assertThat(resultB).isNotNull();
        assertThat(resultB.getPayload()).isEqualTo("accepted-B");
        assertThat(resultB.getHeaders().get("requestId"))
                .isEqualTo("B");
        assertThat(requests.receive(0)).isNull();
    }
}
~~~

### Interpreting the Assertions Accurately

**Test 1 — On-time reply:** The caller receives \`accepted-A\` because the test sent the reply to request A's temporary channel before the deadline expired.

**Test 2 — Missing reply:** \`MessagingTemplate\` returns \`null\` when \`receiveTimeout\` expires. The dequeued request still exists as work that downstream may continue executing.

**Test 3 — Late reply:** The test sends \`late-result-A\` only **after A's Future has returned \`null\`**, eliminating any race over whether reply A arrived before or after the deadline. Next, B has an independent request/reply and receives \`accepted-B\`, not \`late-result-A\`.

Do not assert that **every** temporary reply destination will always throw an exception or always accept expired replies. That detail depends on the channel, version, and reply path configuration. What must be verified at the business boundary is: **a late result neither turns timed-out call A into a success nor appears as B's reply**.

**Scope limitation:** This is an actual test of \`MessagingTemplate\`, not a test of the \`@MessagingGateway\` proxy. It verifies the underlying request–reply operation that Gateways use. When deploying \`@MessagingGateway\`, add dedicated tests for method return types, timeout annotations, and exception policies.

## 8. Writing Tests Directly for @MessagingGateway

A Gateway proxy can be declared as:

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway(
        defaultRequestChannel = "checkout.requests",
        defaultReplyTimeout = "200")
public interface CheckoutGateway {

    String checkout(String orderId);

    @Gateway(replyTimeout = 500)
    String checkoutWithLongerWait(String orderId);
}
~~~

To use this interface in a Spring context, you can configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = CheckoutGateway.class)
class CheckoutTestConfiguration {

    @Bean("checkout.requests")
    QueueChannel requests() {
        return new QueueChannel();
    }
}
~~~

With an input \`QueueChannel\` and no consumer configured in the test, a thread calling \`gateway.checkout("order-1")\` enqueues the request and waits for a reply. Tests can invoke the gateway via \`ExecutorService\`, pull the request from the \`checkout.requests\` bean, read the \`replyChannel\` header, and either send an on-time reply or intentionally withhold it to observe the timeout.

**When testing a Gateway proxy directly**, verify:

1. The method return value matches the reply payload when a result arrives.
2. Under the default policy, the method may return \`null\` on timeout.
3. With \`errorOnTimeout=true\` (Spring Integration 6.2+), a \`MessageTimeoutException\` is thrown if no suitable error channel exists, or handled by the error channel if configured.
4. Two methods with different \`replyTimeout\` values honor their declared timeouts.
5. No reply is ever mismatched across concurrent calls.

Do not write assertions like "must finish in exactly 200 ms". Schedulers, CI load, and thread startup cause real-time variance; use finite timeouts to keep tests from hanging, and verify configured timeout values independently.

## 9. errorOnTimeout, null, and Downstream Errors Are Three Different Cases

In Spring Integration 6.2+, \`@MessagingGateway\` provides \`errorOnTimeout\`:

~~~java
@MessagingGateway(
        defaultRequestChannel = "checkout.requests",
        defaultReplyTimeout = "200",
        errorOnTimeout = true)
public interface StrictCheckoutGateway {
    String checkout(String orderId);
}
~~~

If the gateway times out waiting for a reply, depending on error-channel configuration, the timeout error may be sent there or thrown as a \`MessageTimeoutException\`. Not every exception from downstream is a timeout.

| Case | How to Identify | What to Test |
| --- | --- | --- |
| Gateway reply wait timed out | No reply before deadline | \`null\` or \`MessageTimeoutException\` per policy |
| Service Activator throws exception | Execution failure occurred | Root cause exception / error message / matching correlation |
| Filter rejects message | No reply produced | Explicit discard / exception / requires-reply |
| Router finds no route | No destination or invalid route | \`resolutionRequired\` or fallback per contract |
| Handler returns \`null\` | No reply message | \`requiresReply\` if the flow mandates a reply |
| Request channel full | Sending request fails | \`requestTimeout\`/send failure, not conflated with reply timeout |

Using \`requiresReply\` on an endpoint or \`throwExceptionOnRejection\` on a Filter allows missing-reply conditions to surface as clearer exceptions instead of waiting until timeout. This improves diagnostics, though it does not replace the Gateway's timeout contract.

## 10. Late Replies Must Be Handled as a Business State

A late reply is not necessarily useless. For example, a shipping system might have successfully created a shipping label even though an HTTP Gateway timed out. If the caller retries immediately and the system creates a second label, the bug comes from **duplicated side effects**, not just return values.

Therefore, define a clear policy:

| Policy | Example | How to Test |
| --- | --- | --- |
| **Drop expired reply** | Real-time data is no longer valuable | Counter/trace increments for late reply, new request not updated |
| **Store result asynchronously** | User can poll status later | Querying by \`requestId\` shows final result |
| **Publish completion event** | Order transitions state after timeout | Event has correlation key and duplicate protection |
| **Route to late-reply channel** | Operations need reconciliation | Message is routed to the right channel per policy |
| **Compensate** | Side effect must be undone after timeout | Conditional compensation step tested for idempotency |

These are **application policies**: Spring Integration does not automatically dead-letter every late reply or roll back downstream work by default. Do not draw a \`lateReplyChannel\` on a diagram and assume the Gateway routes there automatically; you must implement actual detection and routing logic.

### A requestId-Based Late Reply Classifier

To tell whether a reply is still valid, applications often store pending requests and their deadlines:

~~~text
Pending requests:
  A -> waiting until t=200
  B -> waiting until t=400

When reply(A) arrives at t=250:
  A is past deadline -> classify as LATE

When reply(B) arrives at t=300:
  B is within deadline -> classify as ON_TIME
~~~

Do not rely solely on \`replyChannel\` to identify requests. In many flows, \`replyChannel\` is a temporary channel scoped to a single invocation. When reconciliation is needed after the caller finishes, use a durable business key such as \`tenantId + requestId + attemptId\` backed by a state-tracking store.

## 11. Testing Late-Reply Classification Logic Without Real Clocks

Separating business logic from the messaging infrastructure keeps tests independent of schedulers. Example classifier function:

~~~java
import java.time.Instant;

enum ReplyStatus {
    ON_TIME, LATE, UNKNOWN
}

static ReplyStatus classify(
        Instant deadline, Instant receivedAt) {
    if (deadline == null) {
        return ReplyStatus.UNKNOWN;
    }
    return receivedAt.isAfter(deadline)
            ? ReplyStatus.LATE
            : ReplyStatus.ON_TIME;
}
~~~

And assertions driven by **supplied timestamps**, not \`System.currentTimeMillis()\`:

~~~java
@Test
void classifies_reply_using_explicit_deadline() {
    Instant deadline = Instant.parse("2026-11-21T08:00:00Z");

    assertThat(classify(
            deadline, deadline.minusMillis(1)))
            .isEqualTo(ReplyStatus.ON_TIME);

    assertThat(classify(deadline, deadline))
            .isEqualTo(ReplyStatus.ON_TIME);

    assertThat(classify(
            deadline, deadline.plusMillis(1)))
            .isEqualTo(ReplyStatus.LATE);

    assertThat(classify(
            null, deadline.plusMillis(1)))
            .isEqualTo(ReplyStatus.UNKNOWN);
}
~~~

This is an **illustration of a business rule**. In real systems, agree on where the deadline is measured, whether transit/buffer time is included, and whether clocks across components are synchronized.

In particular, the \`receivedAt == deadline\` boundary rule must be explicit. The example above treats exact equality as still valid; another system might use \`>=\` to treat it as timed out. What matters is that tests verify the **chosen policy** rather than assuming one universal rule across all services.

## 12. Correlation and Preventing Reply Mismatches

A request–reply Gateway normally uses an internal reply channel/correlation to match replies to invocations. However, when a flow crosses brokers, adapters, or shares a common reply channel, the application must ensure end-to-end correlation.

~~~mermaid
flowchart TD
    A["Request A / requestId=A"] --> Q["Async requests"]
    B["Request B / requestId=B"] --> Q
    Q --> W["Worker"]
    W --> RA["Reply A / requestId=A"]
    W --> RB["Reply B / requestId=B"]
    RA --> CA{"Check correlation + deadline"}
    RB --> CA
    CA -->|"Pending with matching key"| OK["Deliver to right caller"]
    CA -->|"Expired / missing key"| LATE["Late / Orphan handling"]
~~~

Scenarios that must be tested:

1. A and B are sent together, B finishes before A: each caller still receives its own reply.
2. A has timed out; reply A arrives later while B is still waiting: B **must not** receive reply A.
3. Reply carries a nonexistent \`requestId\`: must not be delivered to the nearest waiting request.
4. Reply shares the same \`requestId\` but has a different tenant: no data mixing.
5. Retry creates a new attempt: distinguish business \`requestId\` from per-attempt \`attemptId\`.
6. Duplicate reply: must not trigger two business state transitions if the contract allows only one outcome.

**Never share a single reply QueueChannel without an explicit correlation strategy.** If multiple requests read from one queue without distinguishing IDs, asynchronous arrival order can let waiter B steal reply A.

## 13. Retry After Timeout: A Scenario That Can Duplicate Side Effects

Suppose A requests order creation; the Gateway times out at 200 ms, yet the worker finishes saving to the database at 300 ms. The caller retries request A and a second worker also saves the order.

~~~text
t=0    Request A attempt=1
t=200  Caller times out; worker 1 still running
t=210  Caller retries attempt=2
t=300  Worker 1 commits successfully
t=350  Worker 2 tries to commit again
~~~

When testing this scenario, assert:

- Both attempts are recorded with clear identifiers.
- The business side effect occurs only the policy-defined number of times (typically once if idempotent).
- Late reply from attempt 1 cannot falsely complete attempt 2.
- Retries have bounded attempts, backoff, and status-check mechanisms if needed.
- Error channel and audit logs distinguish timeouts from business processing failures.

A common pattern is using an **idempotency key** and storing outcome state under a business key such as \`tenantId + orderId\`. If a caller times out, querying the previous outcome can be safer than firing an unprotected create operation.

Do not treat \`requestTimeout\`, \`replyTimeout\`, or \`errorOnTimeout\` as an exactly-once mechanism. They control how the caller sends, waits, and reports errors—they do **not** automatically make downstream side effects non-repeatable.

## 14. Notes on Testing Asynchronous Behavior

### Avoid Tests Based on Thread.sleep

Tests like the following are prone to flakiness:

~~~java
// Do not use this as the primary assertion for late reply:
Thread.sleep(250);
assertThat(gateway.checkout("A")).isNull();
~~~

It cannot precisely control when the request is dequeued or when the reply is emitted. In CI, thread startup and machine load vary.

Instead:

- Use \`QueueChannel\` to pause automatic processing and pull requests explicitly.
- Send the reply **before** the Future completes to test the happy path.
- Wait for the Future to confirm timeout, **then** send the reply to test the late path.
- Use \`CountDownLatch\`, barriers, or controlled executors to coordinate threads when needed.
- Set finite timeouts on \`Future.get\` and \`QueueChannel.receive\` so tests never hang.
- Separate deadline business-rule tests from real clock or thread tests.

### Races Right at the Deadline Are Legitimate Races

When a reply arrives right next to the deadline, the outcome can flip based on thread scheduling. Do not write a flaky test and treat every alternating outcome as a bug. Pick two clear scenarios—**before deadline** and **after confirmed expiry**—and test boundary races with dedicated tests only if the product truly needs specific boundary semantics.

### Isolating Test Cases

If multiple tests share a reply channel, worker pool, message store, or pending-request registry, late messages from a prior test can affect the next test. Each test should:

1. Use a unique \`requestId\` or dedicated namespace.
2. Consume/clean up all related requests and replies.
3. Shut down executors properly.
4. Never send to channels of an already-closed Spring context.
5. Verify no pending requests remain after timeout/completion if the application manages a registry.

## 15. Interactions with Router, Filter, Aggregator, and Error Channel

Patterns downstream of a Gateway can prolong reply waiting or prevent any reply from arriving:

| Pattern / Endpoint | Scenario Prone to Timeout | How to Test |
| --- | --- | --- |
| **Router** | No valid route or reply goes to wrong branch | Test each route and default/error policy |
| **Filter** | Message is dropped while Gateway still waits | Test discard channel or throwing exception per policy |
| **Transformer** | Transform fails or drops/alters headers | Verify payload and correlation are preserved |
| **Splitter/Aggregator** | Missing fragment prevents Aggregator release | Send complete/incomplete fragments, test group timeout |
| **Nested Gateways** | Outer timeout shorter than sum of inner waits | Test timeout budgets and propagation |
| **Retry** | Backoff pushes reply past deadline | Test attempts, recovery, and idempotency |
| **Error channel** | Exception occurs but caller never observes it | Verify error route, cause, and requestId |
| **ExecutorChannel/Broker** | Queueing or scheduling slows downstream | Test async handoff, timeout, and late-result policy |

If an Aggregator's \`groupTimeout\` exceeds the Gateway's \`replyTimeout\`, the caller may time out before the group completes. That is not necessarily an Aggregator bug, but it is a **time-budget mismatch** if the application promises a synchronous reply.

## 16. Observing Timeouts and Late Replies in Operations

In production, counting total timeouts is not enough. Distinguish:

| Metric / Log | Meaning | Suggested Labels |
| --- | --- | --- |
| \`gateway_request_timeout_total\` | Failed to send request within limit | Gateway, route, error type |
| \`gateway_reply_timeout_total\` | Caller timed out waiting for reply | Gateway, service, class |
| \`reply_latency_seconds\` | Time from starting wait until reply received | Handler/service; p50/p95/p99 |
| \`late_reply_total\` | Reply arrived after application deadline | Processing branch, request group |
| \`orphan_reply_total\` | No matching pending request remains | Adapter/service |
| \`pending_requests\` | Number of requests still waiting | Gateway/class |
| \`handler_duration_seconds\` | Downstream execution time | Handler/class |
| \`retry_attempts_total\` | Number of retries | Route/error class |

Include \`requestId\` and \`correlationId\` in tracing and structured logs, but do **not** use high-cardinality per-request IDs as metric labels. Never log tokens, sensitive data, or full payloads just to diagnose timeouts.

Set alerts on **reply timeout rate**, **pending request age**, and **abnormal late reply spikes**. If late replies rise while handlers still succeed, inspect queue wait times, timeout budgets, or slow processing rather than assuming all requests failed.

## 17. Recommended Test Matrix

| Scenario | Input / Control | Main Assertion |
| --- | --- | --- |
| On-time reply | Dequeue request then send reply immediately | Caller receives right payload |
| No reply | Send nothing to \`replyChannel\` | Caller finishes per timeout policy |
| Expired reply | Wait for caller timeout then reply | Does not revive finished call |
| Replies A, B out of order | Two requests with distinct IDs | No cross-delivery |
| Late A while B pending | Time out A then start B | B receives only reply B |
| Slow DirectChannel handler | Synchronous handler | Do not assume reply timeout interrupts handler |
| Full input queue | Bounded channel rejects further sends | Request timeout/send error per policy |
| Filter drops message | No normal reply | Discard/error policy respected |
| Aggregator missing element | Incomplete group | Gateway times out while group is not marked complete |
| Retry after timeout | Attempt 2 while attempt 1 still running | Side effects not duplicated against contract |
| Duplicate late reply | Two replies for an expired request | Does not create two success states |
| Missing correlation | Reply cannot identify request | Not assigned to an arbitrary caller |
| Downstream exception | Worker throws exception | Error/error channel reflects real root cause |
| Boundary race | Explicit scheduling control | Do not expect unguaranteed ordering |

## 18. Practice Exercises

### Exercise A — Testing Reply Timeout on a Gateway Proxy

Create \`@MessagingGateway(defaultRequestChannel="requests", defaultReplyTimeout="200")\` and a \`QueueChannel\` named \`requests\`. Call the Gateway method from a separate thread. Dequeue the request and do **not** send a reply. Verify the method returns \`null\` per policy without hanging indefinitely. Then enable \`errorOnTimeout=true\` on Spring Integration 6.2+ and test exception/error channel behavior per configuration.

### Exercise B — Proving replyTimeout Does Not Interrupt Synchronous DirectChannel

Create a synchronous flow with a Service Activator that runs longer than the Gateway's \`replyTimeout\`. Observe that the caller is not cut off by reply timeout alone while the handler occupies the sending thread. Then replace it with a \`QueueChannel\` and a separate poller/worker, and verify the caller stops waiting upon expiry.

### Exercise C — Late Reply and a New Request

Use the \`ReplyTimeoutAndLateReplyTest\` example to let A time out, then send A's late reply. Start B and send B's reply on time. Verify B does not mistakenly receive A's result. Discuss why you must never rely on a shared reply queue lacking correlation.

### Exercise D — Retry and Idempotency

Simulate a worker finishing order creation **after** the Gateway returns a timeout. The caller retries with the same \`orderId\`. Design an idempotency key and assert only one order is created despite two attempts. Record the first attempt's late reply without falsely updating the later attempt's state.

### Exercise E — Timeout Budget for an Aggregator

Build a Splitter → Aggregator flow with a three-message group. Deliver the final element after the Gateway's \`replyTimeout\`. Verify the caller times out per policy, the Aggregator retains appropriate group state, and the late result is classified by \`correlationId\`. Explicitly define whether the group will continue to completion or expire.

## 19. Checklist Before Concluding Tests Pass

1. Have you clearly distinguished **send/request timeout** from **reply/receive timeout**?
2. Is there an asynchronous boundary whenever you expect timeout to cut off caller waiting for a slow handler?
3. Do tests cover on-time reply, no reply, and late reply using **deterministic signals**?
4. Have you avoided asserting exact millisecond completion times in CI?
5. If timeout returns \`null\`, can the business layer distinguish it from a valid empty result?
6. If using \`errorOnTimeout\`, have you tested exception/error-channel behavior for your Spring Integration version?
7. Are late replies classified by request/attempt and prevented from matching a new caller?
8. Does retry after timeout include idempotency or reconciliation to prevent duplicate side effects?
9. Are downstream errors, Filter/Router discards, and genuine timeouts separated into distinct test scenarios?
10. Are pending requests, reply latency, timeout rate, and late replies measured across key branches?
11. Do tests bound \`Future.get\` and \`receive\` waits and clean up workers/threads after every case?
12. Is there an explicit policy for when expired replies are dropped, stored, routed to an error/late channel, or emit events?

**Conclusion:** Reply timeout only ends **the caller's wait** as configured; it does not guarantee cancelling dispatched work. Good testing must prove on-time request–reply, bounded caller waiting on expiry, safe handling of late responses, and strict correlation isolation across calls. Combining these checks with idempotency, error channels, retries, and asynchronous observability lets a Spring Integration system respond predictably without losing track of work still running after a timeout.

### References

- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): distinguishing request/reply timeouts, synchronous DirectChannel vs. multi-threaded flows, \`errorOnTimeout\`.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): registering \`@MessagingGateway\` interfaces via \`@IntegrationComponentScan\`.
- [Spring Integration API — MessagingGateway 6.4.2](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/annotation/MessagingGateway.html): \`defaultRequestTimeout\`, \`defaultReplyTimeout\`, \`errorOnTimeout\`.
