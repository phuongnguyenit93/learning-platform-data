# Testing Retries and Recoverers in Spring Integration Adapters

Suppose an application consumes orders from Kafka, calls a partner HTTP API, and updates a database. When HTTP returns `503 Service Unavailable`, **retrying** can succeed; when the service returns `400 Bad Request` due to invalid data, retrying repeatedly usually helps nothing; and once attempts are exhausted, the application needs a **recoverer** to record the failure, route the message to a controlled error branch, notify operations, or send it to a dead-letter/quarantine store.

Yet an even more critical question arises: if the first HTTP request **already created the order** and only the response was lost, retrying can **create a duplicate order**. Therefore, retry/recoverer testing cannot stop at `verify(handler, times(3))`; it must also verify **retry scope, retryable exception types, backoff intervals, termination points, data state, idempotency, recovery evidence, and what happens when the recoverer itself fails**.

The **"Testing Retries and Recoverers"** lesson belongs to the **Testing** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. In this module, Spring Integration uses **inbound/outbound adapters, gateways, pollers, and `MessageChannel`s** to connect File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This lesson focuses on testing **endpoint-level retries, Spring Retry and `RequestHandlerRetryAdvice`, recovery callbacks, and error channels**, as well as their interaction with **transport-level redelivery**.

> **Principle:** Retry is the decision to **re-attempt an operation that has not met success criteria**. Recoverer is the decision for **what happens when retrying is no longer appropriate or attempts are exhausted**. Both require clear boundaries, owners, policies, and observation points; neither automatically implies "the business operation completed."

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **internal retries**, **broker redelivery**, **replay**, **recovery callbacks**, **error handlers**, **dead-lettering**, and **compensation**.
2. Classify **transient**, **permanent**, and **unknown-outcome** errors and pick fitting retry policies.
3. Configure and test Spring Retry's `RetryTemplate`, `RetryPolicy`, `BackOffPolicy`, and `RecoveryCallback`.
4. Understand how `RequestHandlerRetryAdvice` wraps Spring Integration endpoints and when the advice sees exceptions.
5. Design tests for success after N attempts, exhaustion, single recoverer execution, non-retryable errors, misconfiguration, and recoverer failures.
6. Use `ErrorMessageSendingRecoverer`/error channels cleanly in **one-way flows**, without mistaking error publishing for business completion.
7. Test **sync/async**, inbound pollers, request-reply gateways, and Kafka/JMS/AMQP listeners at the right acknowledgment boundaries.
8. Inject faults across File, SFTP, HTTP, JDBC, JMS, AMQP, and Kafka and verify **target side effects** via integration tests.
9. Test **idempotency, rollbacks, transactions, retry storms, backoff, post-restart recovery**, and security.
10. Build a **test matrix and acceptance criteria** suitable for CI/CD.

## 2. Shared Vocabulary Before Writing Tests

| Concept | Meaning in This Lesson | Testing Note |
|---|---|---|
| **Attempt** | One execution of the protected operation. | The initial execution is usually counted in `maxAttempts`. |
| **Retry** | Re-executing the operation after an error per policy. | Must prove exactly which operation is re-executed. |
| **Retry policy** | Decides which errors retry, max attempts, and stop conditions. | Never treat all exceptions identically. |
| **Backoff** | Delay between attempts—fixed, exponential, or jittered. | Bounded to avoid retry storms and flaky tests. |
| **Recovery callback** | Invoked when retries exhaust per Spring Retry. | Does not automatically mean the error was fixed. |
| **Recoverer** | Component recording/routing failures or producing a recovery result. | May emit error events, quarantine, DLQ, or return fallback. |
| **Redelivery** | Broker/source re-delivers the same logical message. | Can happen outside the in-process retry loop. |
| **Replay** | Deliberately re-emitting historical events. | Requires business keys, versions, and idempotency. |
| **Dead-letter / quarantine** | Store holding unprocessable messages for investigation/redrive. | Trustworthy only once publish/persistence is verified. |
| **Compensation** | Business action offsetting a side effect that already occurred. | Not an automatic transaction rollback. |
| **Unknown outcome** | Unclear whether the target operation succeeded or not. | Requires readback/idempotency before unsafe retries. |

For example, when a broker delivers a message once, advice may try the handler for **three attempts**; then the listener throws so the broker redelivers a second time. That single business message can trigger **six handler executions**, excluding manual replays. Counting internal retries alone never tells the whole execution story.

## 3. Where Do Retries and Recoverers Sit in a Flow?

~~~mermaid
flowchart TD
    SOURCE["Inbound source / listener"] --> CHANNEL["MessageChannel"]
    CHANNEL --> ADVICE["RequestHandlerRetryAdvice<br/>Retry policy + backoff"]
    ADVICE --> HANDLER["MessageHandler / outbound adapter"]
    HANDLER --> RESULT{"Attempt result"}
    RESULT -- "Success" --> DONE["Downstream success path"]
    RESULT -- "Retryable error" --> LIMIT{"Attempts left?"}
    LIMIT -- "Yes" --> BACK["Backoff then retry handler"]
    BACK --> HANDLER
    LIMIT -- "Exhausted" --> REC["RecoveryCallback / recoverer"]
    RESULT -- "Non-retryable error" --> EXIT["Stop retrying per policy<br/>Recover or propagate"]
    EXIT --> REC
    REC --> NEXT{"Recovery outcome"}
    NEXT -- "Record/route" --> QUAR["Error channel / quarantine"]
    NEXT -- "Rethrow" --> UP["Caller / poller / broker container"]
    NEXT -- "Return fallback" --> FALL["Fallback per contract"]
~~~

This is a **conceptual model**; not every Spring Integration endpoint shares the same error path by default. Whether errors route to an error channel or propagate, which exceptions invoke the recoverer, and whether a recovery return value becomes a reply all depend on **advice, handler, channel, and transaction/transport configurations**.

### 3.1. Protected Operation Scope Matters More Than Retry Count

~~~text
File inbound → parse CSV → call HTTP → save DB
~~~

If retry advice wraps only the **HTTP outbound handler**, each attempt retries HTTP **without re-parsing CSV**. If retry wraps the **entire chain from source**, a retry could re-read/re-download the file and cause different side effects. Document the exact boundary:

- Which handler is retried?
- Which transaction surrounds the handler?
- Is source data consumed/acked before the handler runs?
- Do retries create new message IDs or reuse the existing message?
- Does the target support idempotency keys?

Tests are meaningful only when covering the **exact retried segment**.

## 4. Classifying Errors Before Deciding to Retry

| Error Group | Examples | Typical Behavior to Consider |
|---|---|---|
| **Transient transport** | HTTP 503, connection reset, temporary broker loss | Bounded retry/backoff; observe recovery. |
| **Rate limiting** | HTTP 429, temporary quota exhausted | Honor valid retry delays; avoid flooding. |
| **Potentially transient DB** | Deadlocks, lock timeouts | Retry **the appropriate full transaction** with bounds. |
| **Permanent validation** | Malformed CSV schema, JSON missing required field | Do not retry verbatim; quarantine/alert. |
| **Authorization** | HTTP 401/403, SFTP permission denied | Do not retry endlessly; investigate credentials/policy. |
| **Not found** | 404 for resource | Contract-dependent: permanent, eventual consistency, or not ready yet. |
| **Unknown outcome** | Write request hits read timeout after sending | Readback/idempotency; never assume retrying is safe. |
| **Cancellation/shutdown** | Thread interrupted, endpoint stopping | Respect interruption/lifecycle cleanly; avoid stalling shutdown. |
| **Resource exhaustion** | Full queues, exhausted connection pools | Backpressure, throttle, or pause intake; controlled retries. |
| **Poison message** | Payload makes consumer throw every time | Never trap in infinite loop; isolate and record cause. |

No single **HTTP status → retry** table applies universally to every API. For instance, 409 can mean an unretryable conflict or "already exists" allowing idempotent lookup. Rely on **application and operation contracts**.

### 4.1. Retryable Differs from Idempotent

An error appearing transient **does not automatically make the operation safe to retry**. Especially for creation, payment, authorization, deletion, or notification operations:

1. A client failure can occur **after the server applied the side effect**.
2. Retrying can create a duplicate effect.
3. Requires idempotency keys, target deduplication, readback, or compensating workflows.
4. Tests must assert real target state, not merely method invocation counts.

## 5. Core Building Blocks in Spring Retry

| Component | Responsibility | Required Tests |
|---|---|---|
| `RetryTemplate` | Executes callback under retry and backoff policies. | Attempts, results, exhaustion. |
| `RetryPolicy` | Decides when to retry, max attempts, exception rules. | Transient/permanent, nested causes, bounds. |
| `BackOffPolicy` | Waits between attempts. | Bounded, schedule/tolerance, shutdown. |
| `RetryContext` | State of the active retry loop. | Count/cause/attributes when used. |
| `RetryCallback<T, E>` | Work executed per attempt. | Exact side-effect scope. |
| `RecoveryCallback<T>` | Invoked when template finishes via recovery. | Called once, last cause, result/throw. |
| `RequestHandlerRetryAdvice` | Attaches retries to compatible Spring Integration handlers. | Errors pass through advice; right endpoint wrapped. |
| `ErrorMessageSendingRecoverer` | Recoverer sending an `ErrorMessage` to a configured channel. | Error channel receives event; not confused with business reply. |

### 5.1. Total Attempts vs. Retry Count

Suppose `maxAttempts = 3`:

~~~text
Attempt #1: initial handler invocation
  transient error
Attempt #2: first retry
  transient error
Attempt #3: second retry
  transient error
Exhausted → invoke RecoveryCallback (if configured)
~~~

That is **3 handler calls** total, yet only **2 retries** after the initial attempt. `RetryContext.getRetryCount()` normally starts at 0 on the initial call; in tests, do not confuse the context counter with total invocations without verifying library semantics.

### 5.2. Never Configure Arbitrary Infinite Retries

An unbounded policy in an inbound adapter can:

- Pin the poller/consumer thread and block subsequent messages.
- Stall a Kafka partition or JMS/AMQP queue.
- Trigger a request storm against a struggling API.
- Never invoke the recoverer, leaving poison messages stuck forever.
- Block stop/shutdown or blow past gateway response deadlines.

When business rules require **waiting a long time for source recovery**, use asynchronous retries via durable schedulers/queues or managed redrive rather than blocking one thread indefinitely.

## 6. Dependencies and Test Environment

Maven example for a project managed by a compatible Spring Boot BOM/dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.retry</groupId>
        <artifactId>spring-retry</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")
    implementation("org.springframework.retry:spring-retry")
    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Without a Boot BOM, declare compatible versions of Spring Framework, Spring Retry, Spring Integration, and JUnit. Builder APIs, Java DSL, and advice registration may vary across versions; verify against your active version's API.

`spring-integration-test` helps isolate endpoints, yet **does not bundle brokers, databases, SFTP servers, or HTTP stubs**. Protocol tests require the matching adapter modules and test infrastructure.

## 7. First Example: Testing RetryTemplate Independently

Start with a **unit test for retry semantics** requiring no Spring context or broker. This proves the template retries callbacks and invokes recovery on exhaustion; the next test layer proves the advice is actually wired onto the endpoint.

### 7.1. Succeeding After Two Transient Errors

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class RetryTemplatePolicyTest {

    @Test
    void retriesUntilThirdAttemptSucceeds() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build();

        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger recoveries = new AtomicInteger();

        String response = retry.execute(
                context -> {
                    int call = attempts.incrementAndGet();
                    if (call <= 2) {
                        throw new IllegalStateException("temporary");
                    }
                    return "CONFIRMED";
                },
                context -> {
                    recoveries.incrementAndGet();
                    return "RECOVERED";
                });

        assertEquals("CONFIRMED", response);
        assertEquals(3, attempts.get());
        assertEquals(0, recoveries.get());
    }
}
~~~

**Key assertions:** total attempts equal 3 and **the recoverer does not run** when an attempt succeeds. This tests `RetryTemplate`, not `RequestHandlerRetryAdvice` or a broker.

### 7.2. Exhausting Attempts Then Calling Recovery Once

~~~java
@Test
void invokesRecoveryAfterAllAttemptsFail() {
    RetryTemplate retry = RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .build();

    AtomicInteger attempts = new AtomicInteger();
    AtomicInteger recoveries = new AtomicInteger();

    String result = retry.execute(
            context -> {
                attempts.incrementAndGet();
                throw new IllegalStateException("target unavailable");
            },
            context -> {
                recoveries.incrementAndGet();
                assertInstanceOf(IllegalStateException.class,
                        context.getLastThrowable());
                return "QUARANTINED";
            });

    assertEquals(3, attempts.get());
    assertEquals(1, recoveries.get());
    assertEquals("QUARANTINED", result);
}
~~~

This `@Test` method belongs inside the test class with JUnit, `RetryTemplate`, and `AtomicInteger` imports shown previously. **`"QUARANTINED"` here is only a dummy return value from the callback.** Proving the message was actually quarantined requires **real side effects/persistence** and readback verification.

### 7.3. When No Recovery Is Configured

Without a `RecoveryCallback` or matching recovery handler, exhausted retries typically **throw the last/representative exception per policy**. Tests should assert the exception propagates to the caller or hits the endpoint's error handler if configured; never treat exhausted retries as success.

## 8. Attaching RequestHandlerRetryAdvice to an Endpoint

`RequestHandlerRetryAdvice` wraps retries around a **Spring Integration endpoint's `MessageHandler` invocation**. This differs from retrying an entire inbound polling source or broker listener retries.

Illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.support.RetryTemplate;

import java.util.concurrent.atomic.AtomicInteger;

@Configuration
@EnableIntegration
class RetryFlowTestConfig {

    @Bean
    DirectChannel requests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel successes() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger handlerAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice retryAdvice() {
        RetryTemplate template = RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build();
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryTemplate(template);
        return advice;
    }

    @Bean
    IntegrationFlow retryFlow(DirectChannel requests,
                              QueueChannel successes,
                              AtomicInteger handlerAttempts,
                              RequestHandlerRetryAdvice retryAdvice) {
        MessageHandler handler = message -> {
            int attempt = handlerAttempts.incrementAndGet();
            if (attempt <= 2) {
                throw new IllegalStateException("partner temporarily down");
            }
            successes.send(message);
        };

        return IntegrationFlow.from(requests)
                .handle(handler, endpoint -> endpoint
                        .id("retryProtectedEndpoint")
                        .advice(retryAdvice))
                .get();
    }
}
~~~

Above, `requests` is the **input channel**, and `retryProtectedEndpoint` is the **endpoint ID**. The advice wraps the handler so the same message is attempted up to three times within one execution cycle; `DirectChannel` keeps the boundary synchronous for simplicity.

### 8.1. Testing Advice Wiring, Not Just the Template

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RetryFlowTestConfig.class)
class RequestHandlerRetryAdviceFlowTest {

    @Autowired
    @Qualifier("requests")
    DirectChannel input;

    @Autowired
    @Qualifier("successes")
    QueueChannel output;

    @Autowired
    AtomicInteger handlerAttempts;

    @Test
    void retriesHandlerAndEmitsSuccessOnce() {
        handlerAttempts.set(0);

        assertTrue(input.send(
                MessageBuilder.withPayload("order-9")
                        .setHeader("requestId", "req-9")
                        .build()));

        Message<?> observed = output.receive(1_000);
        assertNotNull(observed);
        assertEquals("order-9", observed.getPayload());
        assertEquals("req-9",
                observed.getHeaders().get("requestId"));
        assertEquals(3, handlerAttempts.get());
        assertNull(output.receive(0));
    }
}
~~~

This test proves **the advice actually wraps the flow's handler**. `AtomicInteger` is context-scoped state, so if multiple tests share the context, reset it explicitly or isolate fixtures; this test assumes a single scenario on that context.

**What remains unproven:** real server/broker side effects; the fake handler only pushes messages into `QueueChannel`. Transport integration tests must cover the rest.

## 9. What Must a Real Recoverer Actually Do?

Once retries exhaust, the recoverer must fulfill an **explicit contract**. Common recovery styles:

| Recovery Outcome | Behavior | Test Observation Point |
|---|---|---|
| **Propagate failure** | Rethrow error to caller/listener/poller. | Exception/error path and redelivery semantics. |
| **Publish `ErrorMessage`** | Push error info to an error channel. | Error message has cause/correlation. |
| **Quarantine/parking lot** | Persist message and reason for later reprocessing. | Record/queue/file actually exists with an owner. |
| **Dead-letter broker message** | Use DLQ/DLT per container/transport. | Target broker readback; not just calling a method. |
| **Fallback response** | Return a contract-permitted fallback value. | Never mislabel fallback as business success. |
| **Compensation workflow** | Trigger compensating action when partial side effects occurred. | Compensation state tracked separately. |
| **Escalation/alert** | Emit operational alert/incident. | Alert carries correlation, recovery retries, and dedup. |

**"Called the recoverer" does not mean "recovered."** A recoverer pushing to a `QueueChannel` proves only that a message reached the test channel; claiming durable DLQ storage requires observing the record on the broker.

### 9.1. Recovery Must Expose Queryable States

A workflow might track:

~~~text
NEW → PROCESSING → RETRYING → SUCCEEDED
                          |
                          +→ EXHAUSTED → QUARANTINED → REDRIVE_PENDING
                                                 |
                                                 +→ RESOLVED
~~~

Never mark `SUCCEEDED` upon merely transitioning to `EXHAUSTED` or `QUARANTINED`. A request/reply gateway might even **time out** after recovery if the recoverer emits no reply—actively test that behavior.

## 10. ErrorMessageSendingRecoverer and Error Channels

Spring Integration provides `ErrorMessageSendingRecoverer` to send an `ErrorMessage` to a configured channel when retry advice enters recovery. This fits **many one-way message flows** where failures must route to a dedicated branch.

Illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

@Bean
QueueChannel failedMessages() {
    return new QueueChannel();
}

@Bean
RequestHandlerRetryAdvice retryWithErrorChannel(
        QueueChannel failedMessages) {
    RequestHandlerRetryAdvice advice =
            new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(RetryTemplate.builder()
            .maxAttempts(3)
            .fixedBackoff(1)
            .build());
    advice.setRecoveryCallback(
            new ErrorMessageSendingRecoverer(failedMessages));
    return advice;
}
~~~

Attach `retryWithErrorChannel` specifically to **the endpoints requiring retries**, rather than assuming every endpoint shares a global retry advice. Tests must verify the `Throwable`-bearing message reaches `failedMessages` with **no false business success**.

### 10.1. Cautions When Using Error Channels

- `ErrorMessage` carries a `Throwable`, yet exact wrappers/causes and original-message linkage depend on where the error occurred.
- Sending to an in-memory `QueueChannel` in tests does not prove durability; restarts lose messages on non-durable channels.
- A recoverer returning normally may signal to upstream layers that the exception was handled; inspect **broker ACK/commit** behavior for JMS/AMQP/Kafka sources.
- If a request/reply gateway expects a response, a **one-way error recoverer** may not return a response to the caller; tests may need explicit error-to-reply mapping.
- If the error channel fills up or the error flow throws, **recovery itself can fail**; test that path too.

### 10.2. Asserting the Error Message

An assertion in a flow test using `failedMessages`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

Message<?> error = failedMessages.receive(1_000);
assertNotNull(error, "Recoverer must emit an error message");
assertInstanceOf(ErrorMessage.class, error);
assertInstanceOf(Throwable.class, error.getPayload());

// Assert cause and correlation per real flow contract.
// Do not assume the original message always lives in the same header
// if error strategies / transports are configured differently.
~~~

Unless the handler is configured to **fail across all attempts**, this test does not prove recovery triggered. Fixtures need a deterministically failing handler, attempt counter, and dedicated error output.

## 11. Minimum Test Cases for Retries and Recoverers

| Scenario | Input / Fixture | Assertion |
|---|---|---|
| **No error** | Handler succeeds immediately. | 1 attempt, 0 recoveries. |
| **One error then success** | Fails 1st, succeeds 2nd. | 2 attempts, 0 recoveries. |
| **Success on final attempt** | Max=3, fails twice. | 3 attempts, 0 recoveries. |
| **All attempts fail** | Fails all three attempts. | 3 attempts, 1 recovery. |
| **Permanent failure** | Validation exception non-retryable per policy. | No pointless repeated attempts. |
| **Recoverer also fails** | Recovery store unavailable. | Error escalated; no false success. |
| **No recoverer configured** | Handler always fails. | Error propagates per advice/endpoint. |
| **Retry interrupted** | Intentional shutdown/cancellation. | Stops cleanly without swallowing interrupts. |
| **Duplicate message** | Same `eventId` arrives again. | No duplicate side effects outside contract. |
| **Restart mid-retry** | Process stops between attempts. | Redelivery/checkpoint semantics and idempotency hold. |

In **unit tests** with `RetryTemplate`, count callbacks via `AtomicInteger`. In **Spring Integration flow tests**, verify the advice bean is actually attached to the endpoint. In **transport tests**, verify side effects and ACK/redelivery at sources/targets.

## 12. Testing Exception Classification: Which Errors Retry?

A policy knowing only **attempt counts** is incomplete. It must distinguish transient faults from data or authorization failures.

### 12.1. Example Using `retryOn` for Transient Exceptions

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class ExceptionClassificationTest {

    static class TemporaryPartnerException extends RuntimeException {
        TemporaryPartnerException(String message) { super(message); }
    }

    static class InvalidOrderException extends RuntimeException {
        InvalidOrderException(String message) { super(message); }
    }

    @Test
    void onlyRetriesTheConfiguredTemporaryException() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(4)
                .retryOn(TemporaryPartnerException.class)
                .fixedBackoff(1)
                .build();

        AtomicInteger calls = new AtomicInteger();

        assertThrows(InvalidOrderException.class,
                () -> retry.execute(context -> {
                    calls.incrementAndGet();
                    throw new InvalidOrderException("missing orderId");
                }));

        assertEquals(1, calls.get(),
                "Invalid data must not be retried four times");
    }
}
~~~

Here, `InvalidOrderException` is not retryable; the template aborts immediately instead of repeating the same failure. For wrapped exceptions (e.g., an HTTP client exception wrapped inside `MessagingException`), the policy must specify whether to inspect the **cause chain**. Tests should intentionally construct **wrapped exceptions** matching production rather than relying solely on unwrapped exceptions.

### 12.2. Classifier Test Matrix

| Input Exception | Retry? | What to Assert |
|---|---|---|
| `TemporaryPartnerException` | Yes, within limit. | Accurate attempt count; stops on success. |
| `InvalidOrderException` | No. | Single attempt; proper rejection/recovery. |
| Exception wrapped in `MessagingException` | Depends on `traverseCauses`/classifier policy. | Exact post-wrap handling path. |
| HTTP 429 with wait hint | Contract-dependent. | No tight immediate retry causing storms. |
| HTTP 401/403 | Usually do not loop with stale credentials. | Alert raised; no wasted retries. |
| `InterruptedException` or interrupted thread | Never retry blindly. | Preserves cancellation/shutdown signal properly. |
| Bad data auto-repairable | Only when transformation is explicitly justified. | Never silently alters user data. |

### 12.3. When Not Retrying, Is the Recoverer Invoked?

This depends on **the configured `RetryTemplate`, classifier, and recovery mechanism**. A "non-retryable" error may jump straight to exhaustion/recovery or propagate per policy. Tests should assert the **desired outcome** instead of assuming "no retry = no recovery." Always verify **no pointless retry loop runs** and **errors are never reported as success**.

## 13. Testing Backoff Without Slow or Flaky Tests

Backoff prevents thousands of consumers from hammering a failing system simultaneously. However, testing via `Thread.sleep(2_000)` and measuring total elapsed wall time easily breaks under CI CPU/GC load.

### 13.1. Testing Backoff Counts with a Fake Policy

Spring Retry lets you plug in a custom `BackOffPolicy` in unit tests:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.RetryContext;
import org.springframework.retry.backoff.BackOffContext;
import org.springframework.retry.backoff.BackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

class BackoffBehaviorTest {

    @Test
    void invokesBackoffBetweenAttempts() {
        AtomicInteger waits = new AtomicInteger();
        AtomicInteger attempts = new AtomicInteger();

        BackOffPolicy fakeBackoff = new BackOffPolicy() {
            @Override
            public BackOffContext start(RetryContext context) {
                return new BackOffContext() {};
            }

            @Override
            public void backOff(BackOffContext context) {
                waits.incrementAndGet(); // Does not actually sleep.
            }
        };

        RetryTemplate retry = new RetryTemplate();
        retry.setRetryPolicy(new SimpleRetryPolicy(3));
        retry.setBackOffPolicy(fakeBackoff);

        String result = retry.execute(context -> {
            if (attempts.incrementAndGet() <= 2) {
                throw new IllegalStateException("temporary");
            }
            return "OK";
        });

        assertEquals("OK", result);
        assertEquals(3, attempts.get());
        assertEquals(2, waits.get(),
                "Three attempts succeeding on the last have two backoff waits");
    }
}
~~~

This **unit tests the backoff hook**, not that real sleeps take exactly 100 ms or follow an exponential curve. For custom capped/exponential delay math, test delay computation separately with a fake clock/strategy, paired with a small integration test using reasonable tolerances to verify real scheduling.

### 13.2. Retry Storms and Jitter

~~~mermaid
flowchart LR
    A["1000 consumers all hit 503"] --> BAD["Immediate synchronized retries<br/>add load onto API"]
    A --> GOOD["Bounded exponential backoff<br/>+ jitter where appropriate"]
    GOOD --> C["Desynchronizes retry waves"]
    BAD --> D["Increases prolonged overload risk"]
~~~

Jitter prevents instances from retrying in lockstep, yet introduces timing variance. Never assert exact random delays. Assert **allowed ranges, max caps, attempt counts, total duration limits, and non-negative delays**; inject a seeded random source in unit tests when determinism is needed.

### 13.3. Total Deadlines and Gateway Timeouts

Suppose a gateway awaits replies for at most 2 seconds, while retry policy permits five attempts with 1-second backoffs. The caller can time out before retries finish, leaving **in-flight work running after the caller gave up**. Test:

1. Request/reply timeouts and per-attempt connect/read timeouts.
2. Total time budget (deadline) for the call.
3. Cancellation/stop conditions once results are no longer needed.
4. Side effects if retries keep running after caller timeout.
5. Attempt/time caps ensuring threads are never pinned indefinitely.

There is no simple rule that attempts times a delay equals total timeout: **execution time per attempt**, backoff, scheduling, and transport latency all consume the budget.

## 14. Recoverers Can Fail Too: Testing the Secondary Failure Path

Suppose a handler fails three times and the recoverer tries writing an error record to a database or publishing a dead-letter message to a broker—yet **the recovery database/broker is also unavailable**.

~~~text
Original request E
  → attempt #1 FAIL
  → attempt #2 FAIL
  → attempt #3 FAIL
  → recoverer publish DLT FAIL
  → ??? (must never default to RESOLVED)
~~~

### 14.1. Testing with a Throwing Recovery Callback

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.support.RetryTemplate;

class RecoveryFailureTest {

    @Test
    void propagatesRecoveryFailureInsteadOfClaimingSuccess() {
        RetryTemplate retry = RetryTemplate.builder()
                .maxAttempts(2)
                .fixedBackoff(1)
                .build();

        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger recovererCalls = new AtomicInteger();

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> retry.execute(
                        context -> {
                            attempts.incrementAndGet();
                            throw new IllegalArgumentException(
                                    "original failure");
                        },
                        context -> {
                            recovererCalls.incrementAndGet();
                            throw new IllegalStateException(
                                    "quarantine unavailable");
                        }));

        assertEquals("quarantine unavailable",
                error.getMessage());
        assertEquals(2, attempts.get());
        assertEquals(1, recovererCalls.get());
    }
}
~~~

This illustrates that **recovery failures must remain observable**. In production apps, preserve both the **original exception** and the **recovery exception** in audit/tracing so root causes aren't lost, alongside an escalation policy when secondary error storage fails.

### 14.2. Designing Secondary Failure Paths

| Where Does the Recoverer Fail? | Behavior to Design and Test |
|---|---|
| Error channel full | Bounded timeout/backpressure; never swallow exceptions. |
| DLT publisher unavailable | Never falsely ACK source; retry/redrive per policy. |
| DB quarantine transaction fails | Roll back or preserve recoverable state. |
| Alert service times out | Never mark business message successful just because alerting was attempted. |
| Payload unserializable for DLT | Persist minimal error/metadata record or escalate safely. |
| Error flow throws exception | Prevent infinite recovery loops and preserve original cause. |

**Never infinitely "retry the recoverer"** when recovery infrastructure itself is down; enforce separate bounds and data-preservation fallbacks.

## 15. Retries in Synchronous vs. Asynchronous Flows

### 15.1. DirectChannel and Synchronous Service Activators

On a `DirectChannel`, the handler usually runs on the sender's thread. When advice does not recover:

- Exceptions can propagate back to `send()`/the gateway.
- Backoff delays block the caller thread.
- `assertThrows` fits when errors propagate without a swallowing handler/wrapper.
- If the recoverer handles the error and returns `null`, the sender may **see no exception** even though business processing failed.

### 15.2. ExecutorChannel and Asynchronous Processing

When the handler runs on another thread:

- `send()` returning does not prove the handler finished.
- Exceptions do not return directly to the caller thread.
- Retry advice may execute on the executor; observe attempts, error channels, and completion signals.
- Tests use `CountDownLatch`, output `QueueChannel`s, or bounded futures.
- Teardown must await/clean up in-flight retries before resetting mocks.

### 15.3. Polling Endpoints

For File/SFTP/JDBC pollers, `RequestHandlerRetryAdvice` around a handler does not necessarily govern **`MessageSource.receive()`** or remote fetch steps. To test source polling failures, test the **poller's advice/error handler** as configured on the endpoint.

An inbound source might emit the same message again on the next tick depending on filters/metadata/transactions. Never assume in-process handler retries guarantee a file/row will be re-read after a restart.

~~~mermaid
flowchart LR
    POLL["Poller"] --> SRC["MessageSource.receive()"]
    SRC --> CHANNEL["MessageChannel"]
    CHANNEL --> RETRY["Handler retry advice"]
    RETRY --> H["MessageHandler"]
    SRC -. "Separate source failure path" .-> ERR["Poller error handling"]
    H -. "Handler failure" .-> REC["RecoveryCallback"]
~~~

## 16. Testing Retries with HTTP Outbound Gateways

HTTP is the classic case combining **transient failures and unknown outcomes**. Separate **error classification logic** from **real server response tests**.

### 16.1. HTTP Matrix

| Server Response | Test Policy | Observation Point |
|---|---|---|
| 200 + valid JSON | No retry. | 1 HTTP request, valid reply DTO. |
| 503 twice then 200 | Bounded retry. | 3 requests, 0 recoveries, 1 business outcome. |
| Continuous 503 | Exhausted. | Exact attempts, 1 recovery, error state. |
| 400 malformed request | No retry with same payload. | 1 request, validation error. |
| 401/403 | Do not spam bad credentials. | 1 request and appropriate alert. |
| 429 + `Retry-After` | Honor policy/client constraints. | Backoff and total duration bounded. |
| Connect timeout | Safer since body wasn't sent, yet verify transport. | Classified accurately. |
| Read timeout after POST | Unknown outcome. | Readback/idempotency before retrying side effects. |
| 200 with broken JSON schema | Contract error. | Never treated as business success. |
| Server handles POST then replies late | Client timeout. | Partner may have created data; avoid duplicates. |

### 16.2. Illustrative HTTP Stub Script

~~~text
Request #1 POST /orders → 503 Service Unavailable
Request #2 POST /orders → 503 Service Unavailable
Request #3 POST /orders → 200 {"orderId":"PO-9","status":"CONFIRMED"}

Assertions:
  - Total HTTP requests = 3
  - Header Idempotency-Key = req-order-9 on all three requests
  - Gateway returns valid OrderReply
  - Recoverer did not run
  - Correlation/logs recorded across all three attempts
~~~

To inspect actual requests, use an **HTTP stub/test server** or HTTP client mock tool matching production clients. A Mockito mock of `MessageHandler` tests only the boundary invocation—not HTTP methods, TLS, timeouts, response mapping, or network side effects.

### 16.3. Retry Only Operations with a Safety Contract

For read-only `GET`/queries, retries carry low duplicate side-effect risk. For state-mutating `POST` calls, require server-validated idempotency keys, operation-status lookups, or compensating workflows. Never rely on HTTP verb alone: real-world endpoints sometimes mutate state even on seemingly read-only routes.

## 17. Testing Retries with File and SFTP Adapters

### 17.1. File Inbound

Errors arise when:

- A file is still being written when the poller reads it.
- A file is locked, unreadable, or deleted between scan and open.
- The parser hits schema-invalid CSV/JSON.
- Filters/metadata mark a file seen before the handler fails.
- The app restarts before writing outputs or cleaning up.

**Never try fixing incomplete files with infinite retries.** Usually you need ready-markers/atomic renames or stability checks alongside filters and error/quarantine paths.

| Test Case | Expectation |
|---|---|
| `*.tmp` file being written | Not read before ready. |
| Valid `*.ready` file | Emitted with exact bytes and metadata. |
| Transient I/O error | Retries/recovers per scope; file stays recoverable. |
| Schema-invalid CSV | Do not retry same file endlessly; quarantine with reason. |
| Handler succeeds, crashes before metadata update | Restart obeys delivery policy; side effects idempotent. |
| Two instances see same file | No duplicate side effects outside policy. |

### 17.2. SFTP Inbound/Outbound

SFTP can fail during **authentication, handshakes, host-key verification, sessions, remote listings, downloads, uploads, and renames**, each with different retryability.

| Failure | Policy to Consider |
|---|---|
| Server unreachable | Retry with backoff/circuit breaker. |
| Session drops mid-transfer | Reconnect; verify partial files and idempotency. |
| Wrong password/host key | Do not mass-retry; handle security alert. |
| Remote directory/permission denied | Usually needs config fix, not retry spam. |
| Upload finishes yet ACK lost | Readback target file; avoid duplicate uploads or bad overwrites. |
| Two files with same name | Explicit naming/versioning/rename policy. |

For SFTP integration tests, use an **isolated test server**, test host keys, and test credentials, verifying files on both remote and local sides. Never disable host-key checks just to simplify tests. Mocking message sources/handlers tests downstream flows, **not sessions or reconnects**.

## 18. Testing Retries with JDBC/Database Adapters

In JDBC polling or outbound gateways, retries easily introduce bugs when **transaction boundaries** are misunderstood.

### 18.1. Where Is the Transaction Retried?

~~~text
BEGIN TRANSACTION
  UPDATE inbox_event SET status='PROCESSING'
  INSERT INTO orders ...
COMMIT
~~~

On deadlocks or serialization failures, you typically must **roll back the entire transaction** and retry from the start, rather than retrying one statement inside an aborted transaction.

| Test | Expectation |
|---|---|
| Transient deadlock | Rolls back and retries at the right transaction boundary. |
| Unique constraint violation from duplicate business key | Do not retry endlessly; return existing/conflict outcome per policy. |
| DB unavailable mid-transaction | State recovers cleanly without false commits. |
| Commit succeeds, client times out | Readback by business key; never insert duplicates. |
| Two pollers claim same row | Proper claiming/locking; idempotent side effects. |
| Exhausted after repeated deadlocks | Quarantined/escalated while row remains recoverable. |
| Recovery insert into error table also fails | Never hides original error or marks row processed. |

### 18.2. H2 Does Not Replace Real DBs When Testing Locking

H2/fake repositories help test service logic, yet **isolation, `SELECT FOR UPDATE`, `SKIP LOCKED`, timestamp precision, and post-deadlock behavior** differ from PostgreSQL/MySQL/SQL Server. When testing multi-poller contention, use a matching DB engine in an isolated environment.

### 18.3. Database + Broker Are Two Transaction Boundaries

If a handler updates a DB and then publishes to Kafka/JMS, rolling back the DB does not automatically roll back the broker message, and vice versa. Test **outbox/inbox, idempotency, or reconciliation** whenever delivery must span both domains. `RetryAdvice` alone does not create a safe distributed transaction.

## 19. Testing Retries and Redelivery with JMS

JMS provides **session acknowledgments/transactions and provider redelivery**. Attaching Spring Retry to the business handler combines **in-process retries** with **post-rollback redelivery**.

~~~mermaid
flowchart TD
    Q["JMS destination"] --> L["Listener receives message"]
    L --> R["Retry advice<br/>maxAttempts = 3"]
    R --> H["Business handler"]
    H --> X{"Success?"}
    X -- "Yes" --> ACK["ACK / commit per session"]
    X -- "No" --> REC["Recover or propagate"]
    REC --> D{"ACK/rollback policy?"}
    D -- "Rollback / recover" --> AGAIN["JMS provider redelivery"]
    AGAIN --> L
    D -- "Handled + commit" --> HANDLED["Safe only if recovery is durable"]
~~~

### 19.1. JMS Cases Requiring a Test Broker

1. Handler fails twice then succeeds: advice attempts match; session commits/acks once per config.
2. Handler always fails: retries exhaust; verify rollback/redelivery or DLT per policy.
3. Recovery persists to DLT: source message is ACKed/committed when contract permits.
4. DLT publish fails: source message is not silently lost.
5. Provider-supplied redelivery count/headers: audits do not confuse them with internal retry counts.
6. Listener restarts mid-attempt: message can redeliver; idempotency still holds.
7. Poison message: does not stall a queue indefinitely.

**Never assume every JMS provider uses identical redelivery headers or behavior.** Check your exact container, session mode, and broker.

## 20. Testing Retries and Recoverers with AMQP

With AMQP (e.g., RabbitMQ), separate **application handler retries** from **consumer ACK/NACK, requeue, DLX/DLQ**, and **publisher confirms**.

| Mechanism | Meaning | Test |
|---|---|---|
| Handler retry | Re-runs business handler in-process. | Attempt counts / recovery callback. |
| Consumer ACK | Consumer signals delivery handled per policy. | Broker stops redelivering unexpectedly. |
| NACK/reject/requeue | Broker may redeliver message. | No infinite hot requeue loop. |
| DLX/DLQ | Routes unprocessable messages. | Real message lands in right queue with metadata/cause. |
| Publisher confirm | Broker confirms publish within scope. | Never equate confirm with business completion. |

### 20.1. Common Pitfall

~~~text
Handler fails
  → Spring Retry exhausted
  → Recoverer logs warning, returns normally
  → Listener container decides delivery handled
  → ACK message
  → Message gone from source, yet never quarantined
~~~

For systems requiring message durability, this causes **silent business data loss**. Tests must prove **quarantine/DLQ persisted** before allowing source ACKs as designed. Without durable evidence, propagate/escalate instead of treating error logging as sufficient recovery.

### 20.2. Redelivery Alone Does Not Solve Poison Messages

Continuous NACK-requeue creates hot loops that overload brokers. Use bounded retries, delayed retry/DLX, or parking lots per broker/container capabilities; test attempt counts, alerts, backlogs, and controlled redrive.

## 21. Testing Retries with Kafka

Kafka carries **consumer group, partition, offset, and commit** semantics, so in-process handler retries differ from Kafka listener redelivery/reprocessing.

### 21.1. Where Does Retry Live?

- `RequestHandlerRetryAdvice` can wrap a handler inside a Spring Integration flow.
- Kafka listener containers have their own error/retry/seek/DLT mechanisms per Spring Kafka configuration.
- `KafkaMessageSource` in a polling flow has a different lifecycle from a message-driven consumer.
- Stacking multiple retry layers multiplies total execution attempts unexpectedly.

| Test | What to Verify |
|---|---|
| In-process 3-attempt retry | Handler runs exactly three times within one logical delivery. |
| Kafka redelivery/reprocessing | Consumer offsets and state obey policy; may re-invoke handler. |
| Poison event | DLT record has right topic/key/headers without blocking partition indefinitely. |
| DLT publish failure | Offset is not committed as processed if dropping data violates contract. |
| Consumer rebalance | Idempotency and in-flight work remain safe. |
| Duplicate event ID | Business side effects do not duplicate. |
| Per-partition ordering | Never claim topic-wide global ordering guarantees. |
| Restart between DB write and offset commit | Readback/dedup preserves integrity. |

### 21.2. Kafka Offset Commit Is Not Business Confirmation

A consumer might commit offsets after the recoverer sends to a DLT. That marks **source handling completion per policy**, not business side-effect success. Dashboards should separate **processed, recovered-to-DLT, and failed-without-durable-recovery**.

### 21.3. Real Test Broker Required

Mockito mocking `KafkaTemplate` tests only that code invoked publish; it does not prove Kafka persisted records, committed offsets, or that the DLT exists. Use an isolated/ephemeral broker to verify schemas, partitions/keys, retries, rebalances, and real DLT records whenever these are test goals.

## 22. Retries on Request-Reply Gateways: Especially Risky

A synchronous gateway like `OrderReply submit(OrderRequest)` blocks the caller **waiting for a reply** while the handler retries per policy.

### 22.1. Three Cases to Separate

1. **Success before reply deadline:** gateway receives valid reply, 0 recoveries.
2. **Handler exhausts and propagates:** caller receives error/timeout per contract.
3. **Handler exhausts and recoverer emits a one-way error event then returns normally:** the gateway may receive **no reply**, triggering a timeout instead of an immediate structured error response.

Never wire a one-way `ErrorMessageSendingRecoverer` and assume the gateway automatically returns a structured error to callers. If the API must return `UPSTREAM_UNAVAILABLE`, build and test an explicit **recovery/error-to-reply mapping** with clear types and statuses.

### 22.2. Total Deadline

A request with a 1.5-second reply timeout paired with a handler retrying 5 times at 500 ms backoff will exceed what the caller tolerates. Tests must verify:

- Bounded attempts and **total elapsed time** across the workflow.
- Deadline propagation across layers where needed.
- No dangerous side effects continuing after the caller gives up.
- Late replies handled without attaching to new requests.
- Unknown outcomes backed by business-key lookup channels.

Never use `Thread.sleep` as primary synchronization; use reply fakes with latches, bounded waits, and clear observation points.

## 23. Circuit Breakers, Rate Limiters, and Backpressure Differ from Retries

Retries should be just **one** resilience mechanism. If an HTTP partner is completely down, per-message retries add **extra load** instead of helping the server recover.

| Mechanism | Question | Test |
|---|---|---|
| **Retry** | Should a single operation be re-attempted? | Attempt counts, error classifier, backoff. |
| **Circuit breaker** | Should calls to a failing upstream pause temporarily? | Open/half-open/closed states, fallback/escalation. |
| **Rate limiter** | Are we exceeding allowed quota/throughput? | Reject/queue when over threshold. |
| **Bulkhead** | Can one slow upstream consume all threads? | Saturation, resource isolation. |
| **Backpressure** | Can consumers keep pace with source rate? | Queue limits, stop/pause/reject. |
| **Timeout** | How long may an attempt/gateway wait? | Deadlines and cleanup. |
| **Recoverer** | Once unprocessable, how are errors and progress preserved? | Error events, DLQ, human review, redrive. |

Not every app needs every mechanism. What matters is **never configuring retries that violate external system limits** or hiding errors behind recoverers to make dashboards look "100% successful."

## 24. Redrive After Recovery: Controlled Reprocessing

When a recoverer routes messages to a **parking lot/DLQ/quarantine**, the design must specify **who** can trigger redrive, **when**, **under what conditions**, and **how duplicate side effects are prevented**.

~~~mermaid
flowchart TD
    A["Failed message"] --> R["Bounded retries"]
    R --> Q["Quarantine / DLT"]
    Q --> REVIEW["Review reason + payload schema<br/>assigned owner"]
    REVIEW --> DECIDE{"Safe to redrive?"}
    DECIDE -- "Not yet" --> HOLD["Keep pending<br/>alert / remediation"]
    DECIDE -- "Yes" --> VALID["Verify version, idempotency<br/>target state, and scope"]
    VALID --> REPLAY["Redrive with audit ID"]
    REPLAY --> PROCESS["Business processing"]
    PROCESS --> VERIFY["Verify outcome"]
    VERIFY --> CLOSE["Resolve quarantine record"]
~~~

### 24.1. Fields Worth Retaining in Quarantine

~~~json
{
  "quarantineId": "q-evt-order-2048",
  "eventId": "evt-order-2048",
  "tenantId": "VN",
  "sourceTransport": "KAFKA",
  "sourceReference": "orders-topic:partition-2:offset-991",
  "handler": "orderPartnerHttpHandler",
  "policyVersion": "retry-policy-v3",
  "attemptCount": 3,
  "failureCategory": "UPSTREAM_503",
  "firstFailedAt": "2026-11-23T09:00:00Z",
  "lastFailedAt": "2026-11-23T09:00:02Z",
  "status": "QUARANTINED",
  "redriveCount": 0,
  "owner": "integration-operations"
}
~~~

This is an **illustrative schema proposed by this lesson**, not a default Spring Integration output. `sourceReference` varies by adapter; never assume File/SFTP/HTTP carry Kafka partitions/offsets.

Quarantine records should reference source payloads **with proper data protection and access control**, avoiding copying raw PII/secrets into error tables or public logs.

### 24.2. Redrive Tests

| Scenario | What to Assert |
|---|---|
| Error fixed, replayed | Event passes handler; record moves to `RESOLVED` only after verified outcome. |
| Message still fails due to system error | Never marked successful merely because Redrive was clicked. |
| Same event ID redriven twice | Idempotency protects business side effects. |
| Payload still schema-invalid | Re-quarantined with reason, no retry storm. |
| Old event version superseded | Does not overwrite newer state. |
| Redrive fails because broker unavailable | Source record retained; not marked replayed. |
| Unauthorized user attempts redrive | Rejected and audited. |
| Payload contains secrets/PII | Never exposed via redrive UI/logs. |

## 25. Stateful vs. Stateless Retries: Picking the Right Mode

A **stateless retry** re-executes the callback within the same call context, fitting handlers needing a few quick retries before failing. A **stateful retry** uses a context/key to track retry history across separate invocations per library/configuration support.

| Criterion | Stateless | Stateful |
|---|---|---|
| Attempt state | Mostly within a single `execute` call. | Linked across multiple calls via key/context. |
| Needs operation identity | Not strictly needed to count within one call. | Critical to avoid mixing distinct operations. |
| Best fit | Single handler call with quick retries. | Transaction rollbacks/redeliveries needing retry history. |
| Risks | Backoff blocks threads; restarts lose local counts. | Cache/key collisions, state leaks/expiry, concurrency. |
| Mandatory tests | Attempts, exhaustion, recovery. | Key uniqueness, context retention/eviction, redelivery, restarts. |

**Never assume stateful retries automatically persist across process restarts.** An in-memory retry cache vanishes when the app dies. If state must survive restarts, design durable persistence and run real restart tests.

### 25.1. Business Keys for State

Distinguish:

- `MessageHeaders.ID`: framework-generated message ID; not guaranteed stable across transforms/replays.
- `eventId`: producer-defined logical event identity.
- `operationId`: business side-effect identity.
- `tenantId`: namespace preventing cross-tenant collisions.

A composite key like `tenantId + operationType + eventId` works well when defined by contract, accounting for versions and legitimate repeated events for the same entity. Never use filenames, JMS message IDs, or Kafka offsets as universal cross-adapter business keys.

## 26. Fault Injection: Reproducing Failures Without Flaky Tests

A good retry test **triggers deterministic failures on exact attempts** rather than depending on flaky external servers.

### 26.1. Handler Fails N Times Then Succeeds

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.messaging.MessageHandler;

AtomicInteger calls = new AtomicInteger();

MessageHandler failFirstTwo = message -> {
    int attempt = calls.incrementAndGet();
    if (attempt <= 2) {
        throw new IllegalStateException("temporary failure");
    }
    // Confirm side effect in fixture when third attempt runs.
};
~~~

When substituting handlers via `MockIntegrationContext`, confirm the advice still **wraps the exact endpoint** per your version's substitution mechanics. Replacing an entire endpoint carelessly can bypass the logic under test; verify **actual attempt counts** rather than assuming advice ran.

### 26.2. Using Latches for Concurrency and Timeouts

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

// Inside fake handler:
//   started.countDown()
//   if (!release.await(2, TimeUnit.SECONDS)) {
//       throw new IllegalStateException("test-controlled timeout");
//   }
//
// Inside test:
//   start handler on executor
//   assertTrue(started.await(1, TimeUnit.SECONDS))
//   inspect pending state then release.countDown()
//   await result/future with bounded timeout
~~~

This is **Java fixture pseudocode**: checked exceptions from `await` must be handled in concrete handler code. The goal is deterministic ordering without `Thread.sleep`. For request-reply gateways, holding replies past timeout must also verify pending correlation cleanup.

### 26.3. Fault Injection on Real Transports

| Transport | Fault Injection | What to Verify |
|---|---|---|
| HTTP | Stub 503/429, server close, delayed response | Method/body/headers, retry/backoff, unknown outcome. |
| SFTP | Server down, wrong host key, mid-upload disconnect | Reconnects, partial files, metadata/readback. |
| File | Permission denied, disappearing file, unready file | Error path, filters, no partial-byte reads. |
| JDBC | Kill connection, deadlock, transaction rollback | Claims/locks, boundary-accurate retries, no duplicates. |
| JMS | Broker restart, session rollback | Provider redelivery, DLQ/acks. |
| AMQP | NACK/requeue, DLX failure, publisher confirm timeout | Durable recovery, no requeue storm. |
| Kafka | Broker unavailable, consumer rebalance, DLT publish error | Offsets/partitions, idempotency, no lost messages. |

Run fault injection strictly in **isolated test environments**. Never accidentally kill production brokers or alter production access controls.

## 27. Counting Attempts, Retries, Deliveries, and Business Operations

If a Kafka record is delivered twice, each delivery triggers three handler attempts, yet the business database writes once:

~~~text
Deliveries = 2
Attempts per delivery = 3
Total handler invocations = 6
Successful business writes = 1
~~~

These numbers **do not contradict each other**. They measure different layers.

### 27.1. Data to Record in Audit/Test Evidence

| Field | Purpose |
|---|---|
| `eventId` / `operationId` | Identifies logical message and side effects. |
| `transportMessageId` | Debugging at specific broker/adapter layer. |
| `deliveryAttempt` | Broker/source redelivery count when reliable data exists. |
| `localRetryAttempt` | Attempt number inside `RetryTemplate`. |
| `policyVersion` | Defines attempt limits and error rules applied. |
| `handlerName` / `endpointId` | Pinpoints the retried segment. |
| `failureCategory` | Transient / permanent / unknown error class. |
| `recoveryOutcome` | Propagated, quarantined, DLT persisted, fallback... |
| `targetEvidenceId` | Evidence of target side effect. |
| `occurredAt` / `processedAt` | Meaningful latency tracking. |

Never log raw tokens, passwords, private keys, or sensitive payloads purely for debugging convenience. Redact sensitive fields or reference access-controlled evidence stores.

## 28. Testing Timeouts, Interruption, and Shutdown

### 28.1. Per-Attempt Timeout Differs from Total Deadline

A policy allowing 2 seconds per HTTP call across 5 attempts with growing backoffs yields a **worst-case total time** exceeding what callers expect. Tests should verify total budgets and stop conditions, not just attempt counts.

### 28.2. Interrupted While Backing Off

During application shutdown, a thread sleeping in backoff can be interrupted. Test that:

1. Retries do not continue endlessly after the endpoint stops.
2. Interruption signals are honored per library/runner conventions.
3. Whether in-flight side effects completed is recorded accurately.
4. Consumer/broker ACKs do not falsely mark success.
5. JUnit teardown leaves no lingering executor threads after tests end.

Never call `Thread.stop()` or kill threads to clean up flaky tests. Use `Future` timeouts/cancellations, lifecycle stops, and clean resource teardown. **Cancelling a future does not undo side effects** already committed in HTTP, DB, or brokers.

### 28.3. Clock for Business Logic, Not Scheduler Assumptions

`Clock.fixed` tests business expiry/deadlines, yet **does not control `Thread.sleep`, Spring Retry backoff, or `TaskScheduler`**. Use fake policies to test backoff hooks, separate trigger/calendar tests for cron, and controlled stub servers for remote timeouts.

## 29. Security of Retries and Recoverers

An unsafe retry pipeline can turn into a credential-spraying tool or self-inflicted DoS against external systems.

| Risk | Security Test |
|---|---|
| **Retrying bad credentials** | Never spam logins with invalid passwords/tokens. |
| **SFTP host-key mismatch** | Never bypass trust verification to enable retries. |
| **HTTP 401/403** | Never repeatedly transmit sensitive auth headers needlessly. |
| **Quarantine payloads containing PII** | Never log raw PII; enforce authorized access. |
| **Cross-tenant DLQ** | Tenant A messages never leak to Tenant B. |
| **Unauthorized redrive** | Unprivileged users rejected and audited. |
| **Replaying privilege/payment requests** | Idempotency and authorization checks stay enforced. |
| **Retry storms** | Rate limits, resource caps, and alerting work. |
| **Error responses** | Leak no stack traces or credentials. |
| **Poison messages** | Safely quarantined without crash loops. |

### 29.1. ErrorMessage Must Not Become an Unprotected Copy of Sensitive Data

`ErrorMessage` can carry causes, failed messages, and context. When routing error flows to logs, monitoring, or DLQs, enforce **data minimization and access control**—especially for invoices, HR records, or integration tokens. Security tests must inspect masked logs/error payloads, not just production code.

## 30. Comprehensive Test Matrix

| # | Scenario | Layer | Primary Assertion |
|---:|---|---|---|
| 1 | Handler succeeds on first try | `RetryTemplate` unit | 1 attempt, 0 recoveries. |
| 2 | Fails once then succeeds | Unit | 2 attempts, 0 recoveries. |
| 3 | Succeeds on final attempt | Unit | Exact `maxAttempts`, no recovery. |
| 4 | All attempts fail | Unit | `maxAttempts` and 1 recovery. |
| 5 | No recoverer configured | Unit/flow | Error propagates per contract. |
| 6 | Permanent validation exception | Unit | No pointless retries. |
| 7 | Wrapped transient exception | Unit | Classifier inspects cause chain properly. |
| 8 | Wrapped permanent exception | Unit | Wrapper does not trigger retry loop. |
| 9 | Recoverer returns fallback | Unit/gateway | Caller sees fallback status; no false success. |
| 10 | Recoverer throws | Unit | Both original and recovery failures observed. |
| 11 | Error channel full | Flow | Errors neither swallowed nor marked successful. |
| 12 | DLT publisher fails | Broker integration | Source preserved if durability required. |
| 13 | Advice missing from endpoint | Flow | Test catches missing retry config. |
| 14 | `RetryAdvice` wired to endpoint ID | Flow | Handler attempts match policy. |
| 15 | Fake handler fails once | Flow | Message succeeds after retry. |
| 16 | Source poll fails | Poller | Separate source error path observed. |
| 17 | Handler fails on `DirectChannel` | Sync flow | Exception/recovery matches config. |
| 18 | Handler fails on `ExecutorChannel` | Async flow | Async/error-channel evidence; bounded wait. |
| 19 | Gateway expects reply, recoverer emits one-way error | Gateway | No-reply/timeout handled deliberately. |
| 20 | Gateway times out before retries finish | Gateway | Deadline and pending operations clear. |
| 21 | Fixed backoff | Unit | Accurate backoff invocation count. |
| 22 | Exponential backoff | Unit | Delays stay within policy bounds. |
| 23 | Jitter | Unit | Values within bounds; deterministic seed where needed. |
| 24 | Interrupted backoff | Lifecycle | No infinite retry on stop. |
| 25 | HTTP 503 → 503 → 200 | HTTP transport | Expected requests, status/body, and outcome. |
| 26 | HTTP 400 | HTTP transport | No retries with same payload. |
| 27 | HTTP 429 | HTTP transport | Backoff honors limits/contract. |
| 28 | HTTP read timeout after POST | HTTP E2E | Readback/idempotency before retry. |
| 29 | SFTP server down then recovers | SFTP integration | Reconnects, intact file, accurate upload count. |
| 30 | SFTP partial transfer | SFTP integration | Never marked complete early. |
| 31 | Unready file | File integration | Partial file ignored. |
| 32 | Poison CSV file | File/flow | Quarantined without infinite loop. |
| 33 | JDBC deadlock | DB integration | Retries full transaction cleanly. |
| 34 | JDBC unique constraint violation | DB integration | No duplicate inserts via retry. |
| 35 | Two pollers compete for row | DB concurrency | Side effects never duplicate. |
| 36 | JMS rollback/redelivery | JMS broker | ACK/commit obeys policy. |
| 37 | JMS DLQ failure | JMS broker | Messages never silently dropped. |
| 38 | AMQP nack/requeue | AMQP broker | No hot loop; messages remain recoverable. |
| 39 | AMQP DLT/DLX publish failure | AMQP broker | Recovery failure surfaced. |
| 40 | Kafka consumer rebalance | Kafka integration | Offsets and idempotency intact. |
| 41 | Kafka DLT persisted | Kafka integration | Target topic has exact record/key. |
| 42 | Kafka DLT publish fails | Kafka integration | No false offset commit. |
| 43 | Duplicate event ID | Domain + DB | Single business side effect within scope. |
| 44 | Replay after restart | E2E | Durable recovery/idempotency verified. |
| 45 | Redrive by unauthorized user | Security | Denied and audited. |
| 46 | Cross-tenant DLQ | Security | Other tenants' payloads never exposed. |
| 47 | Error logging | Security | Zero secrets in logs. |
| 48 | Retry storm across 100 consumers | Resilience | Attempt/concurrency/backoff limits hold. |
| 49 | Recovery alert rate | Operations | Does not flood duplicate alerts per event. |
| 50 | Flow succeeds yet target unconfirmed | E2E | Never falsely reports business completion. |

### Interpreting Test Results

- **Unit PASS:** retry policy/callback works under simulated conditions.
- **Flow PASS:** real advice and channel wiring executed.
- **Transport PASS:** protocol/ACK/recovery verified with test servers/brokers.
- **E2E PASS:** final business side effect observed and matches contract.

Never use a lower-layer pass to claim higher-layer guarantees. A test can be technically valid while **coverage still excludes network failures, crashes, or tenant isolation**.

## 31. Complete Example: Recoverer Sending ErrorMessage to QueueChannel

Goal: test a **one-way flow** where the handler always fails, retries up to three attempts, and finally publishes an `ErrorMessage` to a dedicated channel. This verifies **retry/recovery lifecycles at the Spring Integration layer** without a real broker.

### 31.1. Spring Integration Configuration

~~~java
package example.retry;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class ExhaustedRetryFlowConfig {

    @Bean
    DirectChannel workRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel exhaustedFailures() {
        return new QueueChannel();
    }

    @Bean
    AtomicInteger failedAttempts() {
        return new AtomicInteger();
    }

    @Bean
    RequestHandlerRetryAdvice exhaustedRetryAdvice(
            QueueChannel exhaustedFailures) {
        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();

        advice.setRetryTemplate(RetryTemplate.builder()
                .maxAttempts(3)
                .fixedBackoff(1)
                .build());

        advice.setRecoveryCallback(
                new ErrorMessageSendingRecoverer(exhaustedFailures));
        return advice;
    }

    @Bean
    IntegrationFlow exhaustedRetryFlow(
            DirectChannel workRequests,
            AtomicInteger failedAttempts,
            RequestHandlerRetryAdvice exhaustedRetryAdvice) {

        MessageHandler alwaysFail = message -> {
            failedAttempts.incrementAndGet();
            throw new IllegalStateException("external target unavailable");
        };

        return IntegrationFlow.from(workRequests)
                .handle(alwaysFail,
                        endpoint -> endpoint
                                .id("failingOutboundEndpoint")
                                .advice(exhaustedRetryAdvice))
                .get();
    }
}
~~~

**Contract of the example:** assumes `RequestHandlerRetryAdvice` wraps this `MessageHandler` invocation and the recoverer publishes errors to `QueueChannel`. No HTTP/JMS/Kafka or transactions are tested in this setup.

### 31.2. JUnit Test

~~~java
package example.retry;

import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ExhaustedRetryFlowConfig.class)
class ExhaustedRetryFlowTest {

    @Autowired
    @Qualifier("workRequests")
    DirectChannel input;

    @Autowired
    @Qualifier("exhaustedFailures")
    QueueChannel failures;

    @Autowired
    AtomicInteger failedAttempts;

    @Test
    void retriesThreeTimesThenPublishesOneErrorMessage() {
        failedAttempts.set(0);

        boolean accepted = input.send(
                MessageBuilder.withPayload("order-2048")
                        .setHeader("eventId", "evt-2048")
                        .build());

        // In this synchronous flow, the recoverer handles the exception
        // and publishes an ErrorMessage to the channel.
        assertTrue(accepted);
        assertEquals(3, failedAttempts.get());

        Message<?> error = failures.receive(1_000);
        assertNotNull(error);
        assertInstanceOf(ErrorMessage.class, error);
        assertInstanceOf(Throwable.class, error.getPayload());
        assertNull(failures.receive(0));
    }
}
~~~

### 31.3. Exact Conclusions from the Test

The test proves:

1. The advice is genuinely bound to the endpoint.
2. The failing handler ran exactly three attempts.
3. The recoverer emitted one error event upon exhaustion.
4. The error message arrived on the test channel.
5. The test does not hang indefinitely.

The test **does not prove** error events persist across restarts, broker ACKs, external service behavior, or whether original events can be retried/redelivered from real sources.

If implementing on a release with different APIs, check `ErrorMessageSendingRecoverer`, Java DSL `advice`, and `RetryTemplate` builders against the exact library pinned in your project. The lesson teaches the **structure of retry and recovery testing**, not a mandate for one specific version.

## 32. Case Study: SFTP Inbound → HTTP Outbound → Kafka Result

### 32.1. Problem Statement

A partner uploads `orders-*.ready` files over SFTP. An inbound polling adapter fetches files, parses orders, calls an HTTP service to register orders, and publishes result events to Kafka. Risks include:

- SFTP server unreachable or files still uploading.
- CSV rows malformed or invalid tenant.
- HTTP returns 503 or read timeouts after creating the order.
- Kafka broker temporarily unavailable when publishing results.
- Messages re-read after restarts or redrives.

~~~mermaid
flowchart LR
    SFTP["SFTP inbound<br/>ready files"] --> PARSE["Validate / Parse"]
    PARSE --> HTTP["HTTP outbound gateway<br/>retry policy"]
    HTTP --> KAFKA["Kafka result publisher"]
    PARSE --> BAD["Invalid file quarantine"]
    HTTP --> ERR["Retry exhausted<br/>recovery record"]
    KAFKA --> PUBERR["Publish recovery<br/>outbox / alert"]
~~~

### 32.2. Per-Segment Policies Instead of One Flow-Wide Retry

| Boundary | Error / Condition | Policy to Design |
|---|---|---|
| SFTP list/download | Server disconnects | Source-level retry/backoff; partial-file safety. |
| CSV validation | Missing required column | Reject/quarantine; never retry same bytes. |
| HTTP registration | 503 before response | Bounded retries; idempotency key on request. |
| HTTP registration | Timeout after sending POST | Lookup/readback by order ID; no blind retries. |
| Kafka result publisher | Broker unavailable | Outbox/publish retries; never lose registered status. |
| Source checkpoint | Crash before metadata update | Redelivery/idempotent operation. |
| Recovery storage | DLQ/quarantine write fails | Alert/escalation; never falsely mark handled. |

Wrapping **the entire parser → HTTP → Kafka chain** in one retry advice would cause Kafka failures to **re-invoke HTTP order registration**, even though HTTP already succeeded. Retry policies must constrain **side-effect scope** and persist intermediate states cleanly.

### 32.3. Layered Testing Sequence

**A — Unit tests:** CSV parser, validator, error classifier, idempotency key builder, `OrderRegistrationResult` mapper. No Spring context or broker.

**B — Flow isolation tests:** fake SFTP `MessageSource<File>`, HTTP handler failing twice then succeeding, mocked Kafka outbound boundary. Assert order, attempts, message contract, and headers.

**C — SFTP integration:** test server, ready files, host-key verification, remote disconnects, and metadata across restarts.

**D — HTTP integration:** stub server returning 503/200, 400, 429, timeouts, duplicate request IDs, and readback.

**E — Kafka integration:** test broker, result events with expected key/topic/schema, publish failures, DLT/outbox, and recovery.

**F — End-to-end:** one file yields one order and one final result event; crashing/restarting after HTTP succeeds yet before Kafka publish creates no duplicate orders.

### 32.4. Critical Failure Path

~~~text
1. Receive file orders-500.ready.
2. HTTP POST with Idempotency-Key=order-500 returns 503.
3. Retry #2: HTTP creates order yet response is lost.
4. Attempt #3: server sees same key, returns existing order result.
5. Kafka is down so result publish fails.
6. Outbox retains unpublished result event.
7. Kafka recovers; publisher emits result event once logically.
8. Readback confirms order-500 exists and outbox event was published.
~~~

Tests need **target evidence**, not just a counter of 3 HTTP attempts. If the server lacks idempotency keys, implement readback/status lookups or compensating flows before permitting retries.

### 32.5. Case Study Acceptance Criteria

- Incomplete files are never processed.
- Malformed CSVs never trigger HTTP/Kafka calls.
- Transient HTTP 503s retry boundedly; 400s never retry.
- Post-POST timeouts create no duplicate orders.
- Result events are never lost when Kafka fails.
- Recovery failures are never marked handled.
- Correlation traces cleanly from file/event ID to HTTP order and Kafka event.
- Restarts/redrives produce no duplicate business side effects.

## 33. Sample YAML Test Plan

~~~yaml
# Lesson-proposed test schema, not a Spring Integration application.yml.
retryTestPlan:
  id: sftp-order-http-kafka
  ownerTeam: integration-platform
  language: vi

  flow:
    inbound: SFTP
    outbound:
      - HTTP
      - KAFKA
    businessKey:
      fields: [tenantId, operation, eventId]
    correlationHeader: traceId

  retry:
    protectedEndpointId: orderHttpEndpoint
    policyVersion: retry-policy-v3
    maxAttempts: 3
    backoffType: BOUNDED_EXPONENTIAL
    retryable:
      - TRANSIENT_CONNECTIVITY
      - HTTP_503
      - HTTP_429_WHEN_ALLOWED
    nonRetryable:
      - INVALID_PAYLOAD
      - UNAUTHORIZED
      - HOST_KEY_MISMATCH
    unknownOutcome:
      action: RECONCILE_BEFORE_UNSAFE_RETRY

  recovery:
    failureDestination: durable-quarantine
    preserve:
      - eventId
      - tenantId
      - policyVersion
      - failureCategory
      - lastThrowableType
    acknowledgeSourceOnlyAfterDurableRecovery: true
    redriveRequiresApproval: true

  scenarios:
    - success-first-attempt
    - success-last-attempt
    - exhausted-retry
    - non-retryable-validation
    - HTTP-read-timeout-after-side-effect
    - recovery-publisher-unavailable
    - duplicate-delivery
    - restart-before-checkpoint
    - cross-tenant-quarantine

  evidence:
    - businessEventId
    - retryAttempts
    - sourceDeliveryCount
    - recoveryOutcome
    - targetReadback

  cleanup:
    - stop-endpoints
    - reset-substitutions
    - close-test-clients
    - delete-test-files
    - delete-test-broker-resources
    - remove-test-db-records
~~~

**This is an illustrative test structure.** Never paste these keys into `application.yml` expecting the framework to load them. Real Spring Integration, Spring Retry, Kafka listener, AMQP container, or JDBC transaction configs must be mapped individually from your approved policy.

## 34. Observing and Measuring Retry/Recoverer Quality

Reporting only that a message "was processed" hides retries and recoveries.

| Metric | Definition | Interpretation Risk |
|---|---|---|
| **Local retry attempts** | Total handler retry invocations in scope. | Never sum directly as business events. |
| **Retry success rate** | Messages succeeding after retry / messages needing retry. | Must specify error type and cohort. |
| **Exhaustion rate** | Messages exhausting attempts / evaluated retried messages. | May spike from broad upstream outages, not local bugs. |
| **Recovery publish success** | Target-confirmed recovery records / durable recovery requests. | Calling publisher alone is insufficient. |
| **Recovery failure count** | Times the recoverer itself failed. | Critical if source was ACKed afterward. |
| **Unknown outcome backlog** | Requests uncertain whether target side effects happened. | Never count as permanent failure or success. |
| **Duplicate business side effects** | Side effects exceeding logical operations. | Requires business IDs and target readback. |
| **Oldest quarantine age** | Age of oldest unresolved record. | Useful for prioritizing redrive. |
| **Redrive success rate** | Verified-processed after redrive / redriven records. | Do not count merely clicking Redrive. |
| **P95/P99 handling latency** | Latency of verified messages in scope. | Must pair with pending/overdue counts. |

### 34.1. Labeling and Cardinality Rules

Metric labels should use **adapter type, endpoint ID, exception category, policy version, and result**, avoiding high-cardinality labels like `eventId`/`traceId` on time series. Detailed correlation belongs in access-controlled logs/traces with safe dashboard drill-downs.

### 34.2. Meaningful Alerting

Never page once per retry attempt during a broad upstream outage. Group by **incident/risk/endpoint** and alert on: high exhaustion rates, recovery failures, aging quarantine queues, overdue consumer backlogs, retry storms, or growing unknown-outcome backlogs. Test alert logic and redrive policies per contract to prevent alert floods.

## 35. Running Retry/Recoverer Tests in CI/CD

### 35.1. Suite Tiering

| Suite | When to Run | Resources |
|---|---|---|
| **Unit tests** | Every PR | `RetryTemplate`, fake backoff, mappers, classifiers. |
| **Flow tests** | Every PR | Small Spring context, `DirectChannel`, `QueueChannel`, fake handlers. |
| **Adapter integration** | On adapter/contract changes, or every PR if CI is fast enough | HTTP stubs, SFTP server, Kafka/JMS/AMQP brokers, test DBs. |
| **Recovery/fault injection** | Scheduled or before risky releases | Broker restarts, network faults, crash/replay, concurrency. |
| **End-to-end** | Before major releases or scheduled | Multiple test systems with target readback. |

### 35.2. Stability Principles

1. **Never use `Thread.sleep` as primary synchronization.** Use latches, queues, or readable state.
2. **Never use infinite timeouts.** Every test has time budgets and cleanup.
3. **Never touch production systems.** All URLs, queues, directories, DBs, and credentials must be isolated fixtures.
4. **Never share retry contexts** across tests unless intentionally testing shared state.
5. **Never run parallel tests** against shared mutable endpoints/mocks/contexts without guaranteed isolation.
6. **Reset `MockIntegrationContext`** after substitutions and settle in-flight tasks.
7. **Clean queues, files, DBs, topics, and quarantine fixtures** even when assertions fail.
8. **Include event IDs and correlation in failure reports** without leaking payloads/secrets.
9. **Separate test infrastructure errors from business logic errors** in reports.
10. **Never mark transport tests as passed** when skipped due to missing CI brokers; explicitly report coverage gaps.

### 35.3. Preventing Context-Cache Residue

Spring Test caches `ApplicationContext`s. An `AtomicInteger` attempt counter, stale errors in `QueueChannel`, or unreset mock handlers can make later tests falsely pass or fail. Give each test isolated fixtures, reset counters/state, and stop endpoints with in-flight work before resetting substitutions.

Reserve `@DirtiesContext` for state that cannot be safely restored; never use it to mask missing cleanup.

## 36. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Retrying every exception | Bad CSV / 401 / 403 spammed pointlessly. | Contract-driven exception classifier. |
| Huge or infinite `maxAttempts` | Pins threads; triggers retry storms. | Cap attempts, deadlines, and backoff. |
| Retrying multi-side-effect flow | Duplicates HTTP calls and Kafka publishes. | Retry at exact boundaries; outbox/idempotency. |
| Asserting only mock call counts | Unknown business side effects/target state. | Transport tests and readback. |
| Calling recoverer = marking success | Errors persist while dashboards stay green. | Dedicated recovery status with verified evidence. |
| Recoverer logs, returns normally, source ACKs | Messages lost permanently. | Durable recovery or propagate error. |
| Swallowing DLQ publish failures | Data lost beyond redrive. | Test secondary recovery failures. |
| `ErrorMessageSendingRecoverer` on gateway without reply | Gateway times out; caller misses error contract. | Explicit error-to-reply mapping. |
| Conflating local retries with broker redelivery | Total attempts far exceed expectations. | Track counts per delivery and per operation. |
| Treating HTTP read timeout as server inaction | Retries create duplicates. | Idempotency keys and readback. |
| Deduplicating via framework message IDs | Transforms/replays assign new IDs. | Stable business event/operation IDs. |
| Fixed `Thread.sleep` to test backoff | Flaky under CI load. | Fake `BackOffPolicy` and bounded observation. |
| Testing only first-attempt success | Misses exhaustion and recovery failures. | Happy/negative/recovery test matrix. |
| Running SFTP with host-key check off | Masks security bugs. | Proper test server and keys. |
| Using H2 to prove production locking | Does not reflect real DB behavior. | Equivalent DB engine tests. |
| Mock Kafka DLT call = persisted | Offsets might commit before record exists. | Verify real broker DLT/transactions. |
| Skipping restart tests | Loses retry state or repeats side effects. | Restart/replay integration tests. |
| Uncontrolled redrive permissions | Unauthorized users re-run sensitive ops. | Approvals, audits, and tenant isolation. |
| Logging raw payloads on failure | Leaks PII/tokens. | Redact; log minimal metadata. |

## 37. Practice Exercises

### Exercise 1 — RetryTemplate Succeeding After Failures

Write a callback throwing `TemporaryPartnerException` on calls 1 and 2, returning `"OK"` on call 3.

Requirements:

1. Use `RetryTemplate` with 3 total attempts.
2. Track callback invocations and recovery invocations.
3. Assert result, attempts, and recoveries.
4. Add a non-retryable error case per classifier.
5. Explain how attempt counts differ from retry counts and broker delivery counts.

### Exercise 2 — RequestHandlerRetryAdvice in IntegrationFlow

Create an input `DirectChannel`, a fake `MessageHandler`, and an output `QueueChannel`.

Requirements:

1. Attach `RequestHandlerRetryAdvice` to an explicit endpoint ID.
2. Have the handler fail twice then succeed.
3. Assert payload/headers, total attempts, and a single success output.
4. Remove the advice temporarily to confirm the test catches missing retry config.
5. Separate direct `RetryTemplate` unit tests from flow tests, stating each layer's coverage.

### Exercise 3 — Recoverer, Error Channel, and Secondary Failures

Create an always-failing handler with `maxAttempts=3` and `ErrorMessageSendingRecoverer` targeting a test `QueueChannel`.

Requirements:

1. Assert the recoverer runs only after exhaustion.
2. Assert `ErrorMessage` contains the expected `Throwable`/cause.
3. Confirm no business success message is emitted.
4. Simulate an error-channel/recoverer failure.
5. Define source ACK/rollback policies so messages are never lost.

### Exercise 4 — HTTP Timeout After Server Processing

Using a stateful HTTP test server:

1. First POST with `requestId=R-20` creates the record and **drops the response**.
2. Client times out and marks outcome unknown.
3. Client retries with the same idempotency key or status readback.
4. Server returns the existing record without creating a new one.
5. Assert exactly one side effect and complete attempt history.

### Exercise 5 — Kafka/JMS/AMQP Redelivery

Pick one test broker:

- Configure bounded in-process handler retries.
- Force the handler to fail permanently and verify real DLQ/DLT or rollback/redelivery.
- Simulate recoverer publish failure and verify the source message stays recoverable.
- Restart the consumer and verify idempotency.
- Distinguish delivery counts, attempts, and business operations.

### Exercise 6 — JDBC Transactions and Duplicates

Using a test database matching production's engine:

1. Insert a `READY` inbox event.
2. Have two pollers/workers race to claim it.
3. Simulate a deadlock/rollback on one worker.
4. Retry the transaction cleanly without inserting duplicate business records.
5. Simulate commit succeeding while the caller loses the response.
6. Read back by business key to confirm the outcome.

### Exercise 7 — SFTP/File Retries and Restarts

Using a test directory and isolated SFTP server:

1. Write `*.tmp` then rename to `*.ready`.
2. Drop the session mid-download/upload.
3. Check partial files and retry/reconnect behavior per contract.
4. Stop/restart the app and verify metadata stores/duplicates.
5. Feed a permanently invalid CSV and verify quarantine and alerts.

### Exercise 8 — Test Matrix and Policy Design

Design a retry policy for `SFTP → CSV → HTTP POST → Kafka`. Specify:

- Which boundaries retry and which do not.
- Exception classifier and policy version.
- Max attempts, backoff, deadlines, and circuit-breaker triggers if needed.
- Recoverer outputs, ownership, DLQ durability, and redrive authority.
- Idempotency keys and target readback strategies.
- Ten negative tests, five happy/recovery tests, cleanup, and evidence.
- Metrics for recovery failures, pending items, oldest quarantine age, and duplicate side effects.

## 38. Acceptance Checklist

- [ ] **Retry scope defined**: exact handler, endpoint, transaction, or listener.
- [ ] **Clear error classifier**: transient, permanent, and unknown outcomes.
- [ ] **`maxAttempts` includes initial attempt**—understood and asserted accurately.
- [ ] **First-attempt success, last-attempt success, and exhaustion** have separate tests.
- [ ] **`RecoveryCallback` runs only when warranted**, never on success.
- [ ] **Permanent failures never retry pointlessly**; wrapped exceptions tested too.
- [ ] **Bounded backoff**, avoiding retry storms and arbitrary sleep tests.
- [ ] **`RequestHandlerRetryAdvice` wired to the right endpoint**, verified with flow tests.
- [ ] **Recoverer outputs verified** beyond counting method invocations.
- [ ] **`ErrorMessage` sent to the right error channel** when required by design.
- [ ] **Recoverer self-failure** tested for escalation/propagation.
- [ ] **Never reports business success after merely quarantining**.
- [ ] **Gateway replies/timeouts clear**, never faking one-way recovery as a reply.
- [ ] **Sync/async/pollers tested on accurate threads and lifecycles**.
- [ ] **Kafka/JMS/AMQP redelivery and ACK/offsets** separated from local attempts.
- [ ] **File/SFTP partial transfers and JDBC transactions** tested in fitting environments.
- [ ] **HTTP POST timeouts use idempotency/readback**, never blind retries.
- [ ] **Restarts/redrives/duplicate events** cause zero duplicate side effects.
- [ ] **Quarantine/DLQ has durability and access control** as required.
- [ ] **Bounded timeouts, isolated fixtures, resets, and cleanup** enforced in CI.
- [ ] **Never touches production or leaks secrets** in tests/logs.
- [ ] **QA results layered cleanly**: unit, flow, transport, and E2E never conflated.

## 39. Summary

Testing **retries and recoverers** in Spring Integration is far more than counting how many times an exception re-runs a handler. A sound test suite proves **which errors retry, which segment advice protects, what happens on the final attempt, how the recoverer handles the message, and what evidence confirms the final state**. `RetryTemplate` and `RecoveryCallback` unit-test policies; `RequestHandlerRetryAdvice` and `ErrorMessageSendingRecoverer` verify retry/recovery at message-flow endpoints.

Even so, **File/SFTP, HTTP, JMS, AMQP, Kafka, and JDBC have distinct confirmation, transaction, retry, and redelivery boundaries**. A retry can repeat side effects if the initial attempt succeeded while the response/ACK was lost. Reliable integrations therefore require **idempotency, durable recovery, error classification, bounded backoff, controlled redrive, and real-transport testing** wherever risk demands.

When finished, you should be able to answer: **which logical message arrived, how many handler attempts ran across how many deliveries, which attempt caused side effects, which error stopped retries, where the recoverer persisted the failure, who may redrive it, and what evidence confirms the final outcome**. That foundation lets Spring Integration adapters recover cleanly without hiding errors or creating duplicate data.
