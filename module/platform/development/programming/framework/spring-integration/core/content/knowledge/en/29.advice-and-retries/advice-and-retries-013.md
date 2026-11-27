# Retrying Per Handler vs. Retrying the Entire Flow

In the **Advice and Retries** chapter of **SPRING_INTEGRATION_CORE**, a key decision is choosing which unit of work is re-executed after an error. A single service call, an endpoint, and an entire business process can have completely different boundaries.

Suppose an ordering flow has three steps:

~~~text
A: Validate order → B: Reserve inventory → C: Save result
~~~

If B hits a transient error, re-calling B alone may suffice. If you need to re-read data and recompute a decision before reserving inventory, you may need to re-run A and B. If C fails after B already reserved inventory successfully, re-running the whole flow could reserve inventory a second time.

**Retry must wrap a unit of work that can be safely repeated and whose success or failure can be observed.** Attempt counts and backoff only make sense once this boundary is clear.

## 1. Objectives and Example Scope

After this lesson, you will be able to:

- Distinguish local handler retry from replaying the input of a flow segment.
- Explain why a downstream failure does not automatically re-run an earlier handler.
- Use Java DSL to place `RequestHandlerRetryAdvice` on an endpoint or on a gateway calling a subflow.
- Recognize how channels, recovery, transactions, and side effects impact retry.
- Design tests that count invocations instead of checking only the final result.

The Java examples use **Spring Integration 6.5.x, Spring Retry 2.x, and Java 17 or later**. Retry classes come from `org.springframework.retry.*`. This version baseline is chosen to present one consistent configuration.

Spring Integration 7.x moves retry advice to Spring Framework's retry support; configuration differs, such as `setRetryPolicy(...)` instead of `setRetryTemplate(...)`. When applying this to a 7.x project, translate the configuration to that version's API; the principles for choosing processing boundaries remain the same. See [6.5 retry advice](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html) and [7.0 retry advice](https://docs.spring.io/spring-integration/reference/7.0/handler-advice/classes.html).

## 2. Distinguishing Attempts, Retries, and Replay

An **attempt** is one execution of the protected unit. A **retry** is an additional attempt following a prior failure.

With Spring Retry's `SimpleRetryPolicy(3)`, there are at most **three total attempts**: the initial call and two retries. It is not the initial call plus three retries. This convention is documented in [SimpleRetryPolicy Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

In this lesson, **flow replay** means re-sending the input to a selected flow segment. It is an application orchestration pattern, not an automatic ability to roll every endpoint back to its initial state.

| Concept | Re-executed Unit | Input to the Next Attempt |
| --- | --- | --- |
| Handler retry | Work inside the advised handler | The message currently handled by that handler |
| Segment retry via gateway | Request–reply exchange with the invoked subflow | The request at the gateway boundary |
| Broker redelivery | Processing starting from the consumer receiving the message again | The message redelivered by the broker |
| Resume from checkpoint | Remaining steps per saved business state | A command or data reconstructed from the checkpoint |

The phrase "retrying per handler" here refers to retrying a single handler invocation. It does not imply a single-message system, nor does it prescribe stateless or stateful mode.

### Invocation Count Example

Suppose B fails twice and then succeeds; A and C always succeed.

~~~text
Retry at B:
A → B fails → B fails → B succeeds → C

Retry across A–B–C:
A → B fails
A → B fails
A → B succeeds → C
~~~

| Retry Boundary | A Called | B Called | C Called |
| --- | ---: | ---: | ---: |
| B only | 1 | 3 | 1 |
| A–B–C | 3 | 3 | 1 |

C runs only after B succeeds, so it did not repeat in this example. If an error occurs in C, replaying the whole segment invokes both A and B again even though both steps had already completed.

## 3. Boundary of RequestHandlerRetryAdvice

For a typical reply-producing endpoint, `RequestHandlerRetryAdvice` wraps the handler's request processing. Once the handler returns successfully, sending the output to downstream endpoints lies outside this local retry scope. [Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/6.5/handler-advice.html) clearly documents that boundary.

~~~mermaid
flowchart LR
    A["A: validate order"] --> B
    subgraph R["Local retry"]
        B["B: reserve inventory"]
        B -. "transient error" .-> B
    end
    B --> C["C: save result"]
~~~

Example:

~~~java
.handle(orderService, "reserve",
        endpoint -> endpoint.advice(reserveRetry))
.handle(orderService, "persist")
~~~

If `reserve` fails with an exception permitted by the policy, the advice re-invokes `reserve`. If `reserve` already returned and `persist` throws, the advice on `reserve` does not automatically re-invoke `reserve`.

This remains true even when endpoints are connected by a `DirectChannel`. Sharing a thread lets exceptions unwind up the call stack; the method boundary wrapped by the advice decides whether an exception triggers retry.

Look inside the handler body as well:

~~~java
public OrderResult process(OrderRequest request) {
    OrderRequest validated = validate(request);
    OrderRequest reserved = reserve(validated);
    return persist(reserved);
}
~~~

If you advise the `process` method, all three calls inside it belong to a single attempt. "One handler" can still contain multiple operations and multiple side effects. Inspect the actual work wrapped rather than merely counting DSL lines.

### What Local Retry Does Not Provide Automatically

Retry advice does not automatically:

- Re-send a message to the start of the flow.
- Undo HTTP calls, emails, or external system mutations.
- Start a fresh transaction per attempt.
- Checkpoint already-succeeded endpoints.
- Retry an error that occurs after a method returns a `Future` or reactive publisher.

If a handler returns an asynchronous task waiting to finish, synchronous retry may already have exited before that task reports failure. With reactive processing, place retry inside the publisher lifecycle or use an appropriate advice mechanism.

## 4. When Is Per-Handler Retry Appropriate?

Local retry usually fits when a single operation fails transiently and can be re-invoked with its current input.

Examples:

- Calling a lookup service that occasionally fails due to connectivity.
- Reserving inventory via an API supporting an idempotency key.
- Writing a record via an upsert with an appropriate unique constraint.
- Calling a transactional service where each call can restart the needed unit of work cleanly.

Check four questions:

1. **Is the error likely to clear?** A malformed payload rarely becomes valid 200 ms later.
2. **Is the input still valid?** Changing prices or stock may require recomputing from an earlier step.
3. **Are you certain the previous call had no effect?** Timeouts often leave remote state unknown.
4. **Can the operation repeat safely?** Local retry can still cause duplicate side effects.

Suppose the reservation step receives `idempotencyKey = "reserve:O-42"`. Every attempt for the same operation must keep that exact key. If each retry generated a new UUID, the external service could treat them as distinct reservation requests.

An idempotency key is part of the processing contract: the receiver must store and check the key atomically, handle concurrent requests, and return the matching result. Adding a header on the sender side alone is not enough to guarantee deduplication.

## 5. Using a Gateway to Set a Replay Boundary for a Flow Segment

When multiple endpoints must be re-executed together, extract that segment into a request–reply subflow and have a gateway invoke it. Placing retry advice on the gateway makes **invoking the flow segment** the retry unit.

~~~mermaid
flowchart LR
    IN["Input"] --> PRE["Prepare request"]
    PRE --> G
    subgraph R["Retry at gateway"]
        G["Gateway calls subflow"] --> A["A: validate"]
        A --> B["B: reserve"]
        B --> C["C: save"]
        C --> REPLY["Reply"]
        REPLY --> G
    end
    G --> OUT["Post-gateway processing"]
~~~

On each attempt, the gateway sends the request to the start of the subflow and waits for the result. If an error from the subflow propagates back to the gateway as an exception matching the policy, the subflow call can be re-executed.

`GatewayEndpointSpec` supports configuring advice, reply timeout, and `errorOnTimeout`; see [GatewayEndpointSpec 6.5 Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/GatewayEndpointSpec.html).

For this pattern to match intent, specify:

- **Starting point:** which channel receives the re-sent message.
- **Ending point:** which reply signals the segment finished.
- **Error path:** failures must reach the waiting gateway.
- **Input state:** the reused request must hold sufficient data and clear semantics.
- **Repeatable effects:** any step that may have succeeded in an earlier attempt.

Steps before and after the gateway sit outside the replayed segment. If a value needs recomputing, move that computation into the subflow. A value already computed and packaged before the gateway will not recompute automatically.

### Reusing Requests Does Not Deep-Copy Mutable Payloads

`Message` forbids arbitrary header mutation, yet the payload may be a mutable object. If the first attempt mutates that object in place and then fails, the next attempt may see the mutated state.

Examples use immutable `record` payloads to avoid this issue. For complex payloads, prefer transformations producing new objects or reconstructing commands from controlled original data. Do not assume a gateway restores objects to their pre-attempt state.

## 6. Java DSL Example: Comparing Both Boundaries with Counters

The example below exposes two independent entry channels:

- `endpointRetry.input`: retries only the reservation step.
- `flowRetry.input`: retries the gateway invoking all three steps.

The simulated service fails the reservation step on the first two calls. Each fresh application context has fresh counters and failure state. This example observes retry boundaries; it does not simulate durable persistence or a real reservation API.

Requires `spring-integration-core`, `spring-retry`, and compatible Spring dependencies. The tests later use JUnit Jupiter. `@EnableRetry` is not needed for this example because the advice is attached directly to endpoints.

### 6.1. Configuration and Simulated Service

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class RetryScopeConfiguration {

    public record OrderRequest(String orderId) {
    }

    public record OrderResult(String orderId, String status) {
    }

    public static class TemporaryInventoryException extends RuntimeException {
        public TemporaryInventoryException(String message) {
            super(message);
        }
    }

    public static class DemoOrderService {
        private final AtomicInteger validationCalls = new AtomicInteger();
        private final AtomicInteger reservationCalls = new AtomicInteger();
        private final AtomicInteger persistenceCalls = new AtomicInteger();
        private final AtomicInteger failuresRemaining = new AtomicInteger(2);

        public OrderRequest validate(OrderRequest request) {
            validationCalls.incrementAndGet();
            if (request.orderId() == null || request.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId must not be blank");
            }
            return request;
        }

        public OrderRequest reserve(OrderRequest request) {
            reservationCalls.incrementAndGet();
            int remaining = failuresRemaining.getAndUpdate(
                    value -> Math.max(0, value - 1));

            if (remaining > 0) {
                // Simulated error before the inventory reservation side effect.
                throw new TemporaryInventoryException(
                        "Inventory temporarily unavailable");
            }
            return request;
        }

        public OrderResult persist(OrderRequest request) {
            persistenceCalls.incrementAndGet();
            return new OrderResult(request.orderId(), "ACCEPTED");
        }

        public int validationCalls() {
            return validationCalls.get();
        }

        public int reservationCalls() {
            return reservationCalls.get();
        }

        public int persistenceCalls() {
            return persistenceCalls.get();
        }
    }

    @Bean
    DemoOrderService orderService() {
        return new DemoOrderService();
    }

    @Bean
    RequestHandlerRetryAdvice reserveRetry() {
        return newRetryAdvice();
    }

    @Bean
    RequestHandlerRetryAdvice flowRetry() {
        return newRetryAdvice();
    }

    private static RequestHandlerRetryAdvice newRetryAdvice() {
        Map<Class<? extends Throwable>, Boolean> retryable = Map.of(
                TemporaryInventoryException.class, true);

        SimpleRetryPolicy policy = new SimpleRetryPolicy(
                3, retryable, true, false);

        ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
        backOff.setInitialInterval(100L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(1_000L);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backOff);

        RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow endpointRetryFlow(
            DemoOrderService service,
            @Qualifier("reserveRetry") RequestHandlerRetryAdvice retry) {

        return IntegrationFlow.from("endpointRetry.input")
                .handle(service, "validate")
                .handle(service, "reserve", endpoint -> endpoint.advice(retry))
                .handle(service, "persist")
                .get();
    }

    @Bean
    IntegrationFlow replayBodyFlow(DemoOrderService service) {
        return IntegrationFlow.from("replayBody.input")
                .handle(service, "validate")
                .handle(service, "reserve")
                .handle(service, "persist")
                .get();
    }

    @Bean
    IntegrationFlow flowRetryFlow(
            @Qualifier("flowRetry") RequestHandlerRetryAdvice retry) {

        return IntegrationFlow.from("flowRetry.input")
                .gateway("replayBody.input", gateway -> gateway
                        .advice(retry)
                        .replyTimeout(5_000L)
                        .errorOnTimeout(true))
                .get();
    }
}
~~~

Channels created by DSL in this example are default synchronous channels; there are no queues, executors, or parallel branches. `persist` returns `OrderResult`, so the subflow invoked via the gateway produces a reply.

The two advices have separate policy instances so the two setups stay distinct. There is no local retry inside `replayBodyFlow`; thus invocation counts on the replay path are not multiplied by nested retries.

### 6.2. Reading the Policy Configuration

For the constructor:

~~~java
new SimpleRetryPolicy(3, retryable, true, false)
~~~

The meanings in order are:

| Parameter | Meaning in the Example |
| --- | --- |
| `3` | Maximum of three total attempts |
| `retryable` | Allows retrying `TemporaryInventoryException` and its subclasses |
| `true` | Searches for matching exceptions in the cause chain |
| `false` | Unmatched exceptions are not retried by default |

Cause traversal is needed because business exceptions may be wrapped in `MessagingException`. `RequestHandlerRetryAdvice` also mentions this in [setRetryTemplate Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

In the example, waits before the two retries are 100 ms and 200 ms. This backoff holds the processing thread while waiting. In production deployments, set a time budget and consider jitter so requests do not retry in lockstep.

The policy does not retry `IllegalArgumentException`. If `orderId` is blank, the validation error ends processing without replaying the flow segment.

### 6.3. Testing Invocation Counts

Place the test in the same package as the configuration. Each test creates a fresh context so the two initial simulated failures are not consumed by another test.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class RetryScopeTest {

    @Test
    void endpointRetryRepeatsOnlyReservation() {
        assertCounts("endpointRetry.input", 1, 3, 1);
    }

    @Test
    void gatewayRetryReplaysTheSelectedFlow() {
        assertCounts("flowRetry.input", 3, 3, 1);
    }

    private void assertCounts(
            String channelName, int validation, int reservation, int persistence) {

        try (var context = new AnnotationConfigApplicationContext(
                RetryScopeConfiguration.class)) {

            MessagingTemplate template = new MessagingTemplate();
            template.setReceiveTimeout(5_000L);

            Message<?> reply = template.sendAndReceive(
                    context.getBean(channelName, MessageChannel.class),
                    MessageBuilder.withPayload(
                            new RetryScopeConfiguration.OrderRequest("O-42"))
                            .build());

            assertNotNull(reply);
            assertEquals(
                    new RetryScopeConfiguration.OrderResult("O-42", "ACCEPTED"),
                    reply.getPayload());

            var service = context.getBean(
                    RetryScopeConfiguration.DemoOrderService.class);
            assertEquals(validation, service.validationCalls());
            assertEquals(reservation, service.reservationCalls());
            assertEquals(persistence, service.persistenceCalls());
        }
    }
}
~~~

Expected results:

~~~text
endpointRetry.input: validation=1, reservation=3, persistence=1
flowRetry.input:     validation=3, reservation=3, persistence=1
~~~

Counting invocations catches replaying an already-succeeded step. Asserting only `OrderResult("O-42", "ACCEPTED")` would not distinguish the two strategies.

These snippets are practice material with expected outcomes; this lesson does not claim they have been executed in the reader's project environment.

## 7. Channels and Error Routing Determine Whether Retry Sees Failures

A retry can react only to failures it observes while the unit of work is still executing.

### 7.1. DirectChannel

`DirectChannel` passes messages to handlers on the sending thread. A synchronous call to a subflow can span all downstream handlers until a reply or exception returns. That is the basis of the gateway example above. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

Even so, sharing a thread does not automatically extend the scope of `RequestHandlerRetryAdvice` placed on an ordinary handler. To retry multiple steps, the example used a gateway as the invocation unit wrapping those steps.

### 7.2. QueueChannel and ExecutorChannel

Consider:

~~~text
Producer → QueueChannel → Worker processes → Write data
~~~

If the producer sends one-way, `send(...)` succeeding may only mean the message was placed on the queue. A worker failing later does not retroactively turn that earlier send into a failure.

With processing on another thread, errors usually travel as an `ErrorMessage` to a configured error channel. You cannot rely on a Java exception unwinding back to a producer whose send call has already returned. This difference is explained in [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

Two common patterns are:

- Retry directly at the worker where the actual operation executes.
- Maintain a request–reply contract so the gateway waits and receives worker errors through the corresponding error-forwarding mechanism.

Thus, having an asynchronous channel does not mean a gateway can never see errors. What must be verified is whether the gateway is still waiting, whether the error channel returns errors to the right call, and whether any component turns errors into normal results.

Do not rely on retrying a one-way producer send to guarantee worker completion. When long retry delays or survival across restarts are needed, design durable persistence and redelivery rather than blocking threads with backoff.

### 7.3. Timeouts Do Not Prove the Operation Failed to Complete

On a gateway, `replyTimeout` limits how long to wait for a reply in applicable scenarios. It is not a timeout that interrupts a synchronous handler running on the same thread. Configure separate timeouts on HTTP clients, JDBC, or operations inside the handler. See [Gateway Behavior When No Response Arrives](https://docs.spring.io/spring-integration/reference/6.5/gateway.html#gateway-behavior-no-response).

In the example:

~~~java
.replyTimeout(5_000L)
.errorOnTimeout(true)
~~~

`errorOnTimeout(true)` turns a missing reply into an error rather than a `null` result. The sample policy retries only `TemporaryInventoryException`, so this setting **does not automatically retry timeout errors**.

To retry timeouts, add matching exception classification and evaluate side effects first. A worker may have already written data while the reply arrived late; a new attempt could run while the old attempt is still in flight. Timeouts do not cancel prior work or trigger rollbacks on external systems.

## 8. Recovery Can Terminate Retry at an Outer Boundary

Consider a two-level structure:

~~~text
Outer retry → Gateway → Handler with inner retry → Recovery
~~~

If the inner retry exhausts its attempts and recovery returns a valid fallback value, the gateway may treat that as a successful reply. The outer retry sees no exception and therefore has no reason to retry.

Similarly, a gateway's error flow can convert an exception into a normal response. Converting errors into replies is supported by [Messaging Gateways — Error Handling](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

When designing multi-level retry, decide explicitly on one of these outcomes:

| Outcome After Local Retry Ends | Observed by Outer Level | Consequence |
| --- | --- | --- |
| Exception continues propagating | Failure | Can be retried if outer policy permits |
| Valid fallback returned | Normal reply | Does not trigger exception-based retry |
| Error routed elsewhere, no reply produced | Missing reply | May wait until timeout |
| Business result such as `REJECTED` | Normal reply | Application must handle per business contract |

A payload with `status = "FAILED"` is not automatically treated as an exception. To retry based on result contents, design an explicit result-checking mechanism.

Sending an `ErrorMessage` for tracing also does not guarantee request–reply received a properly typed final response. Distinguish the operational error-reporting path from the response the caller is awaiting.

## 9. Retry, Transactions, and Redelivery Are Three Separate Concerns

### 9.1. Retry Does Not Mean Rollback

Suppose the first attempt performs:

~~~text
Reserve inventory via HTTP succeeds
→ Database write fails
→ Replay whole segment
~~~

A database rollback does not release inventory reserved over HTTP. If the entire segment replays, the reservation operation needs idempotency or an appropriate compensation process.

Across multiple independent systems, you may need persisted business state, an outbox, or a saga to coordinate continuation and compensation. Retry is only one tool within that design.

### 9.2. Which Transaction Covers Each Attempt?

The two structures below mean different things:

~~~text
Retry outermost:
Retry → New transaction for attempt → Work → commit or roll back

Transaction outermost:
Shared transaction → Retry → multiple attempts inside that transaction
~~~

In the second structure, a failure can mark the transaction `rollback-only`. A subsequent attempt returning normally does not clear that flag; a commit-time failure can still occur after the inner retry finishes.

If each attempt needs an independent transaction, route the call through a Spring-proxied service or `TransactionTemplate` with appropriate propagation. Check interceptor order and any existing caller transaction; simply adding `@Transactional` does not guarantee a fresh transaction is always created.

Standard transaction context is thread-bound. Switching to an executor or queue does not carry that transaction to the worker. Refer to [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

### 9.3. Stateless, Stateful, and Replay Scope

| Design Dimension | Question to Answer |
| --- | --- |
| Retry scope | Re-invoking one handler or multiple steps? |
| Stateless or stateful | Do attempts run inside one call or across redeliveries? |
| Transactions | Which operations commit or roll back together? |
| Delivery | Who holds the message and decides redelivery? |
| Business recovery | Does it resume from persisted state? |

The main example uses stateless retry: the advice retries within the current invocation.

Stateful retry preserves retry state across redeliveries and can throw errors so the message source performs redelivery. It does not automatically checkpoint individual endpoints. In Spring Integration 6.5, stateful configuration uses `RetryStateGenerator`; see [RequestHandlerRetryAdvice](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

Broker redelivery usually re-runs the consumer from the start of the message-consumption boundary. If the consumer executes A–B–C, A and B can still be invoked again. To resume from C, the application must actively save and check state.

An in-memory `QueueChannel` under default configuration does not provide redelivery and durability semantics equivalent to a durable broker.

## 10. Side Effects and Nested Retries

### 10.1. Key Operations by Business Intent

For order `O-42`, distinct operations might use:

~~~text
reserve:O-42:v1
persist:O-42:v1
notify:O-42:accepted:v1
~~~

A key must remain stable across attempts of the same operation. When business request content genuinely changes, apply versioning rules or a new command rather than reusing old keys arbitrarily.

Do not default to `MessageHeaders.ID` as a system-wide idempotency key: when constructing a new message or crossing transports, the ID may change. A business command ID or operation ID expresses deduplication intent far more reliably.

For database writes, a separate `exists` check followed by `insert` still has a race condition. Unique constraints, transactions, and returning prior outcomes must work together to protect deduplication semantics.

### 10.2. Multi-Layer Retries Can Multiply Calls

Suppose:

- Outer gateway performs up to 3 attempts.
- Inner reservation handler performs up to 3 attempts per gateway call.
- Each time the handler runs, the HTTP client also tries up to 2 times.

If errors persist long enough and every layer allows retries, HTTP requests can reach:

~~~text
3 × 3 × 2 = 18
~~~

This is the limit under those assumptions; actual outcomes depend on where errors happen, recovery, and which layer stops first.

Furthermore, a broker may redeliver the message after this entire flow fails. Therefore, designate a primary retry owner for each error category.

You can use short retries on remote calls and delayed redelivery at the message level for prolonged outages. Total invocations, wait durations, and load limits must still be calculated across all layers combined.

### 10.3. Calculating Time Budgets for the Retried Unit

If one attempt of **the protected unit** takes at most 800 ms, with three attempts and two backoffs of 100 ms and 200 ms:

~~~text
Approximate max duration = 3 × 800 + 100 + 200 = 2,700 ms
~~~

If the unit is the entire flow, 800 ms must cover the work across that entire segment. Do not substitute B's timeout alone as the maximum duration of A–B–C.

This is a budget estimate under assumptions, excluding queuing, scheduling, serialization, recovery, or nested retries. Without effective per-call timeouts, you cannot bound total duration from `maxAttempts` alone.

## 11. Choosing Boundaries in Real Scenarios

The table below suggests starting designs derived from the boundaries analyzed; each choice still depends on the contracts of participating systems.

| Scenario | Initial Handling Approach | Conditions to Verify |
| --- | --- | --- |
| Lookup API hits brief connection errors | Retry the API-calling handler | Effective timeouts and load limits |
| Inventory reservation via idempotent API | Retry the reservation handler | Stable key and receiver semantics |
| Compute decision then write data, needs recompute on conflict | Retry the read–compute–write unit together | Each attempt has clean state and transaction |
| Payment captured, notification step fails | Retry notification step or resume from saved state | Never accidentally charge twice |
| Message queued, worker fails later | Retry at worker or via redelivery | Ack, error path, and durability |
| Input data validation error | Return error or route to invalid-data flow | Retrying cannot fix input content |
| Flow with splitter and aggregator | Retry individual branches or design controlled replay | Duplicate items, correlation, release, and group state |
| Outage lasting several minutes | Delayed redelivery or durable scheduling mechanism | Attempt limits, dead-letter path, and operations |

With splitter–aggregator flows, replaying the request can emit additional items while the previous attempt's group has not expired. Do not scale a linear example into branching flow replay without designing isolation or deduplication across attempts.

A good starting point is placing retry close to the operation that can fail independently. Widen it to multiple steps only when business rules genuinely require recomputing or re-running that unit and its side effects are controlled.

## 12. Extending Practice to Catch Wrong Scope Choices

After comparing the two sample tests, extend the simulated service with the scenarios below. Each test should create isolated input state and verify both invocation counts and business results.

| Test Scenario | Observation Required |
| --- | --- |
| B fails twice then succeeds, retry at B | A=1, B=3, C=1 |
| B fails twice then succeeds, retry at gateway | A=3, B=3, C=1 |
| B always fails, 3-attempt budget | C is not called; final error reaches caller if no recovery |
| A detects invalid data | No replay under sample policy; B and C are not called |
| B succeeds, C fails transiently; only B has advice | B does not re-run just because C failed |
| B succeeds, C fails once; gateway retry permits that error | A, B, and C may all run twice |
| B completes side effect yet caller loses reply | Multiple calls create only one business effect via idempotency |
| Inner recovery returns fallback | Outer retry does not re-run on exception |
| Payload is mutated in first attempt | Detect subsequent attempt receiving altered data |
| Worker still running after gateway timeout | Verify behavior when old and new attempts overlap |

For idempotency, keep two assertions distinct:

~~~text
reserve call count = 3
effective reservations = 1
~~~

A method-call counter cannot prove by itself that a side effect occurred only once. You need a simulated store keyed by operation ID or integration with the receiver to verify actual effect.

When observing the system, record operation ID, endpoint, retry scope, attempt count, final exception, and elapsed time. Operation IDs and correlation IDs link attempts together; avoid turning high-cardinality IDs into metric labels.

If you ever observe a payment step re-running after an email-sending error, trace back to the gateway, listener, poller, or outer caller replaying the entire workflow. Increasing backoff will not fix a wrong retry boundary.