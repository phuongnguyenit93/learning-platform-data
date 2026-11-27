# RecoveryCallback

## 1. Objectives and Context

In the **Advice and Retries** chapter of the **SPRING_INTEGRATION_CORE** module, `RecoveryCallback` defines how an endpoint concludes when the retried operation still fails. This knowledge connects `Message`, `MessageChannel`, endpoints, and gateways into a flow with well-defined behavior for both success and error cases.

After this lesson, you will be able to:

- Distinguish the responsibilities of a retry policy and a recovery callback.
- Retrieve the message associated with an error to build a fallback result or a record for later reprocessing.
- Attach recovery to `RequestHandlerRetryAdvice` using Java DSL.
- Choose between replying to a gateway, routing errors to a recovery channel, and continuing to propagate the failure.
- Identify what to test regarding invocation counts, response types, and error routing.

**Version scope:** the main examples use **Spring Integration 7.0 and Spring Framework 7.0, Java 17 or later**. Section 10 presents the API for **Spring Integration 6.x combined with Spring Retry 2.x**. Starting in Spring Integration 7.0, retry moves to Spring Framework Core; `RecoveryCallback` also changed package and signature. Do not mix imports from both branches in the same configuration. [What's New in Spring Integration 7.0](https://docs.spring.io/spring-integration/reference/7.0/whats-new.html).

## 2. Once Retries Stop, Where Does the Message Go?

Suppose the system receives a quote request from a partner. The endpoint calls the partner service, which is temporarily unavailable. With one initial call and two retries, there are two ways it can end:

1. One attempt succeeds: the endpoint returns the received quote; recovery does not run.
2. No further attempts are allowed under the policy: the system must decide whether to return an unavailable status, route the error for later processing, or report failure to the caller.

`RecoveryCallback` represents the decision in the second step. This callback does not make the original business operation succeed on its own. It performs a different, pre-designed action.

~~~mermaid
flowchart TD
    A["Input Message"] --> B["Endpoint with retry advice"]
    B --> C["Invoke handler"]
    C -->|Success| D["Business result"]
    C -->|Failure| E{"Policy allows more retries?"}
    E -->|Yes| F["Backoff if configured"]
    F --> C
    E -->|No| G{"Recovery callback present?"}
    G -->|No| H["Error propagates out of advice"]
    G -->|Yes| I["RecoveryCallback"]
    I --> J["Return fallback result"]
    I --> K["Send ErrorMessage and finish"]
    I --> L["Rethrow error"]
~~~

This is the model for **stateless retry** in this lesson. With **stateful retry**, attempts can span multiple message redeliveries; recovery does not necessarily occur during the first delivery. `RequestHandlerRetryAdvice` supports both modes, though the examples below do not enable stateful retry. [Spring Integration Retry Advice](https://docs.spring.io/spring-integration/reference/7.0/handler-advice/classes.html).

### 2.1. Components with Distinct Responsibilities

| Component | Question It Answers |
|---|---|
| Retry policy | Which errors are retried and how many times can they be retried? |
| Backoff | How long to wait before the next attempt? |
| `RecoveryCallback` | What to do when retry ends with an error? |
| `RetryListener` | Which events are observed during the retry loop? |
| Error flow | How is the `ErrorMessage` sent to a channel handled? |

A recovery callback does not replace a router, filter, or transformer. However, a recovery result can be routed by a router, and an error sent to a recovery channel can be transformed into an incident record.

### 2.2. Recovery Does Not Always Mean All Attempts Ran

A policy can refuse retry right after the first failure because that exception is not in the permitted list. With stateless retry in Spring Integration 7.0, when `RetryTemplate` terminates with `RetryException`, the advice invokes recovery if one is configured.

Therefore, the callback must not assume "since recovery was called, three attempts definitely ran" or "this is definitely a transient error." The callback itself should classify the error before deciding to return a fallback. [RetryTemplate 7.0 source](https://github.com/spring-projects/spring-framework/blob/v7.0.0/spring-core/src/main/java/org/springframework/core/retry/RetryTemplate.java).

## 3. RecoveryCallback Contract in Spring Integration 7.0

Abbreviated form of the interface:

~~~java
package org.springframework.integration.core;

public interface RecoveryCallback<T> {
    T recover(
            org.springframework.core.AttributeAccessor context,
            Throwable cause);
}
~~~

The two parameters mean:

- `context` holds attributes related to the failed processing attempt, such as the input message.
- `cause` is the error passed by the advice to the callback. Do not assume this is the innermost business exception.

The return value can substitute for the result of the failed operation. That is why the callback can produce a reply for a gateway. This interface is not Spring Retry's `org.springframework.retry.RecoveryCallback`. [RecoveryCallback 7.0 Javadoc](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/core/RecoveryCallback.html).

### 3.1. Retrieving the Message from Context

When used with `RequestHandlerRetryAdvice` 7.0, you can retrieve the message using the framework constant:

~~~java
Object candidate = context.getAttribute(
        ErrorMessageUtils.FAILED_MESSAGE_CONTEXT_KEY);

if (!(candidate instanceof Message<?> failedMessage)) {
    throw new IllegalStateException(
            "Recovery is missing the message to process", cause);
}
~~~

Required imports:

~~~java
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
~~~

Use the constant instead of hardcoding the string `"message"`. `INPUT_MESSAGE_CONTEXT_KEY` and `FAILED_MESSAGE_CONTEXT_KEY` have distinct roles; in the 7.0 advice, the context is populated from the message currently handled by the advice for both keys. "Input message" here means the input to that endpoint, not necessarily the message at the very start of the pipeline before transformers or splitters. [ErrorMessageUtils source](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/support/ErrorMessageUtils.java), [RequestHandlerRetryAdvice source](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

### 3.2. Inspecting the Cause While Preserving Error Details

In the 7.0 advice, the callback receives `RetryException` when the retry template terminates with an error. That exception can hold the last exception and an underlying cause chain; the handler may also have wrapped a business error inside `MessagingException`.

When classifying errors, inspect the cause chain. When storing or forwarding errors, keep the received exception rather than only keeping the `getMessage()` string, so stack trace and context remain intact. Do not cast `cause` directly to a business exception.

## 4. Choosing the Recovery Result According to Flow Contracts

| How the Callback Ends | Behavior to Understand | Suitable Scenario |
|---|---|---|
| Returns a non-`null` object | The object becomes the result of the advised handler call | Gateway requires a typed business response |
| Returns a `Message<?>` | Can explicitly set payload and required headers | Flow needs markers such as `recovered=true` |
| Returns `null` | Emits no reply from this endpoint | One-way flow or flow intentionally ending here |
| Throws a runtime exception | Recovery also failed; error continues propagating outward | No valid fallback exists or recovery record could not be saved |

For a reply-producing endpoint, a non-`null` result is sent to the configured output channel or the request's `replyChannel`. Returning `null` can stop the flow; if the endpoint requires a reply, `ReplyRequiredException` may be thrown. [Service Activator behavior](https://docs.spring.io/spring-integration/reference/7.0/service-activator.html).

### 4.1. Fallbacks Must Reflect the True Business State

A quote API may return:

~~~json
{
  "requestId": "quote-001",
  "state": "UNAVAILABLE",
  "price": null
}
~~~

This status indicates the system could not obtain a price. Do not use a price of `0` or an `OK` status to hide an error. If returning a cached price, distinguish cached results from fresh partner quotes.

If an aggregator flow is waiting for replies from each item after a splitter, a clearly typed fallback ensures every item has a result to aggregate. Returning `null` for one item may leave the group waiting until timeout. When building a new `Message` manually, be sure to preserve correlation headers, sequence details, and required reply information.

### 4.2. Sending an Error Does Not Mean Replying to the Gateway

`ErrorMessageSendingRecoverer` sends the error and returns `null` when sending finishes. It does not synthesize a `QuoteResult` or any other response matching a gateway's return type. [ErrorMessageSendingRecoverer 7.0 source](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/ErrorMessageSendingRecoverer.java).

For a gateway expecting a response, choose explicitly: return an appropriately typed fallback, rethrow the error, or design an error flow with its own reply mechanism. Without a reply, the gateway may wait until `replyTimeout` expires.

`replyTimeout` is also not an overall timeout for work running synchronously over a `DirectChannel`: it does not interrupt an HTTP call or backoff holding the same thread. The partner service call still needs its own connect/read timeouts. [Gateway timeouts and no-reply scenarios](https://docs.spring.io/spring-integration/reference/7.0/gateway.html#gateway-timeouts).

## 5. Complete Example: Gateway Receiving a Typed Fallback

### 5.1. Problem Statement and Lab Conditions

A gateway receives quote requests. If the partner is unavailable, retry up to two times; if it still fails, return `UNAVAILABLE`. Data errors or programming errors must continue propagating outward.

The example uses:

- Java 17 or later.
- `spring-integration-core` 7.0.x and compatible Spring Framework 7.0.x dependencies, managed uniformly by the application's BOM or dependency management.
- Annotation configuration and Java DSL.
- A simulated partner service that always fails so we can observe the recovery path without network connectivity.

The entire class below lives in a dedicated package for the example, such as `example.recovery`. `@IntegrationComponentScan` scans for the gateway interface in that package.

~~~java
package example.recovery;

import java.math.BigDecimal;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.AttributeAccessor;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.RecoveryCallback;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.integration.support.ErrorMessageUtils;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteRecoveryConfig.class)
public class QuoteRecoveryConfig {

    public record QuoteRequest(String requestId, String sku) {
    }

    public record QuoteResult(
            String requestId,
            String state,
            BigDecimal price) {
    }

    public interface PartnerClient {
        QuoteResult fetch(QuoteRequest request);
    }

    public static class PartnerUnavailableException
            extends RuntimeException {

        public PartnerUnavailableException(String message) {
            super(message);
        }
    }

    @MessagingGateway(
            defaultRequestChannel = "quoteRequests",
            defaultReplyTimeout = "2000")
    public interface QuoteGateway {
        QuoteResult quote(QuoteRequest request);
    }

    @Bean
    public DirectChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public PartnerClient partnerClient() {
        // Demo bean: replace with a real client in your application.
        return request -> {
            throw new PartnerUnavailableException(
                    "Partner is temporarily unavailable");
        };
    }

    @Bean
    public RecoveryCallback<Object> quoteRecovery() {
        return (context, cause) -> {
            Message<?> failedMessage = requireFailedMessage(context, cause);

            if (!(failedMessage.getPayload()
                    instanceof QuoteRequest request)) {
                throw new MessageHandlingException(
                        failedMessage,
                        "Payload is not suitable for recovery",
                        cause);
            }

            if (!containsCause(
                    cause, PartnerUnavailableException.class)) {
                throw new MessageHandlingException(
                        failedMessage,
                        "Error has no business fallback",
                        cause);
            }

            return new QuoteResult(
                    request.requestId(), "UNAVAILABLE", null);
        };
    }

    @Bean
    public RequestHandlerRetryAdvice quoteRetryAdvice(
            RecoveryCallback<Object> quoteRecovery) {

        RetryPolicy policy = RetryPolicy.builder()
                .maxRetries(2)
                .delay(Duration.ofMillis(100))
                .includes(PartnerUnavailableException.class)
                .build();

        RequestHandlerRetryAdvice advice =
                new RequestHandlerRetryAdvice();
        advice.setRetryPolicy(policy);
        advice.setRecoveryCallback(quoteRecovery);
        return advice;
    }

    @Bean
    public IntegrationFlow quoteFlow(
            PartnerClient partnerClient,
            RequestHandlerRetryAdvice quoteRetryAdvice) {

        return IntegrationFlow.from("quoteRequests")
                .handle(partnerClient, "fetch",
                        endpoint -> endpoint
                                .requiresReply(true)
                                .advice(quoteRetryAdvice))
                .get();
    }

    private static Message<?> requireFailedMessage(
            AttributeAccessor context, Throwable cause) {

        Object candidate = context.getAttribute(
                ErrorMessageUtils.FAILED_MESSAGE_CONTEXT_KEY);

        if (candidate instanceof Message<?> message) {
            return message;
        }

        throw new IllegalStateException(
                "Recovery is missing the message to process", cause);
    }

    private static boolean containsCause(
            Throwable failure,
            Class<? extends Throwable> expectedType) {

        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }

        return false;
    }
}
~~~

Here `maxRetries(2)` means **at most three handler invocations**: one initial attempt and two retries. Spring Framework's builder inspects both the direct exception and causes when applying `includes(...)`. This fits cases where an endpoint wraps a business exception. [RetryPolicy.Builder 7.0 Javadoc](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html).

### 5.2. Calling the Gateway and Observing the Result

The snippet below initializes the context directly without Spring Boot:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import example.recovery.QuoteRecoveryConfig;
import example.recovery.QuoteRecoveryConfig.QuoteGateway;
import example.recovery.QuoteRecoveryConfig.QuoteRequest;

public class RecoveryDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                QuoteRecoveryConfig.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);

            var result = gateway.quote(
                    new QuoteRequest("quote-001", "SKU-001"));

            System.out.println(result);
        }
    }
}
~~~

Expected output:

~~~text
QuoteResult[requestId=quote-001, state=UNAVAILABLE, price=null]
~~~

The simulated service is called three times; the two configured backoff delays are `100 ms` each. After the final failure, the callback returns `QuoteResult`. Total elapsed time also includes each call's execution time and framework overhead.

When replacing the simulated client with a real one:

- If it succeeds on the first attempt or a retry, the client's result is returned; the callback does not run.
- If `PartnerUnavailableException` occurs repeatedly, the fallback is returned.
- If a different error occurs, the policy stops retrying and the callback declines fallback by rethrowing the error.

Checking the exception type in the callback is still necessary even though the policy specifies `includes(...)`: the policy decides whether to retry; the callback decides whether the final error should be converted into a fallback result.

## 6. Routing Errors to a Recovery Channel with ErrorMessageSendingRecoverer

A second approach suits one-way flows: after retries fail, send an `ErrorMessage` to a dedicated branch for recording or reprocessing.

This is an **alternative configuration** to the fallback strategy in Section 5. Do not attach both advices to the same handler just to run both recovery styles.

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.advice.ErrorMessageSendingRecoverer;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.core.retry.RetryPolicy;

// Place these methods inside a @Configuration class.
@Bean
public QueueChannel recoveryChannel() {
    return new QueueChannel(100);
}

@Bean
public ErrorMessageSendingRecoverer errorRecoverer(
        QueueChannel recoveryChannel) {

    ErrorMessageSendingRecoverer recoverer =
            new ErrorMessageSendingRecoverer(recoveryChannel);
    recoverer.setSendTimeout(1000);
    return recoverer;
}

@Bean
public RequestHandlerRetryAdvice recoveryPublishingAdvice(
        ErrorMessageSendingRecoverer errorRecoverer) {

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryPolicy(RetryPolicy.builder()
            .maxRetries(2)
            .delay(Duration.ofMillis(100))
            .build());
    advice.setRecoveryCallback(errorRecoverer);
    return advice;
}
~~~

The policy in this snippet retries all exception types by builder default to keep the example focused on sending errors. In a real application, restrict retryable exceptions based on business semantics.

`QueueChannel(100)` is only an in-memory buffer with bounded capacity. It decouples error publishing from consumers in the example; it is not a broker, not a durable error store, and does not come with a consumer. `setSendTimeout(1000)` bounds how long sending waits if the channel can block, such as when the queue is full. [Error publishing in ErrorMessagePublisher](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/core/ErrorMessagePublisher.java).

If applying this advice to a one-way service activator, do not set `requiresReply(true)` and do not use a gateway expecting `QuoteResult` as in Section 5 unless a dedicated reply mechanism is added.

### 6.1. Reading ErrorMessage in the Example

You can read the queue with the following observation snippet:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

Message<?> received = recoveryChannel.receive(1000);

if (!(received instanceof ErrorMessage errorMessage)) {
    throw new IllegalStateException("No ErrorMessage received");
}

Throwable failure = errorMessage.getPayload();
Message<?> original = errorMessage.getOriginalMessage();

if (original != null) {
    Object payloadToInspect = original.getPayload();
    Object correlationId = original.getHeaders().get("correlationId");
    // Use the needed details to build the application's error record.
}
~~~

The payload of `ErrorMessage` is a `Throwable`, not the original business payload. With the 7.0 advice and default strategy in the example, `originalMessage` is populated from the input message in context. With other error sources or strategies, this property may not be present. [DefaultErrorMessageStrategy 7.0](https://github.com/spring-projects/spring-integration/blob/v7.0.0/spring-integration-core/src/main/java/org/springframework/integration/support/DefaultErrorMessageStrategy.java).

In other APIs and versions, the failed message may instead reside in `MessagingException.getFailedMessage()` along the cause chain. Do not assume every `Throwable` has a `getFailedMessage()` method.

### 6.2. What Does the Recovery Channel Consumer Do?

A real consumer can convert the error into a record containing:

| Field | Purpose |
|---|---|
| `requestId` or business key | Lookup and deduplication |
| Endpoint or operation name | Identify where failure occurred |
| Error type and diagnostic info | Support investigation |
| Failure timestamp | Track backlog age |
| Minimal data to reconstruct the request | Support reprocessing |
| Processing status | Distinguish pending, resolved, and needs intervention |

Avoid dumping the raw exception object or every header into JSON indiscriminately. Some headers contain in-memory channel references, payloads may be sensitive, and stack traces are not business replay data. Define a stable error record schema that can be persisted and read reliably.

## 7. RecoveryCallback and errorChannel Are Not the Same Mechanism

Both participate in error handling, but they trigger at different points:

| Mechanism | When or Where It Participates | What Must Be Controlled |
|---|---|---|
| `RecoveryCallback` | Inside the retry advice when the retry loop ends in failure | Whether to return a result, send an error, or rethrow |
| `ErrorMessageSendingRecoverer` | An implementation of recovery callback | Sends to the chosen channel and returns `null` |
| Source or gateway `errorChannel` | When that component's error-handling mechanism receives an error | Which component publishes `ErrorMessage`, and whether that branch replies |
| Exception on `DirectChannel` | Can propagate back on the same call stack | How the caller or gateway handles it |

Do not treat setting an `errorChannel` header as a catch-all for every exception in every flow. For normal synchronous calls, exceptions can propagate directly to the sender; converting an exception into an `ErrorMessage` depends on the component orchestrating error handling. [Spring Integration Error Handling](https://docs.spring.io/spring-integration/reference/7.0/error-handling.html).

The examples in this lesson pass the recovery channel directly to `ErrorMessageSendingRecoverer`. This makes the error destination explicit instead of relying on default channel names or expecting every component to interpret a header identically.

If the callback already returned a fallback or sent the error and returned `null`, the handler failure has been handled at that advice boundary. Do not expect an outer error flow to receive the same failure a second time. Conversely, if the callback throws an exception, outer components can handle that new exception according to their configuration.

## 8. What Happens If Recovery Also Fails?

Recovery still performs I/O and can still fail:

- The database storing error records is down.
- The recovery queue is full and send times out.
- The channel has no suitable subscriber.
- A synchronous consumer on the recovery channel throws an exception.
- The callback receives an unexpected payload type.

In such cases, do not log and return success if business requirements demand persisting the work for later processing. The callback can throw an exception carrying the cause; this failure must be handled by the caller or message-receiving mechanism.

An error occurring inside the callback is not automatically retried by the handler's retry loop. The advice has already moved into the recovery phase. If persisting the error record needs its own retry, configure a separate bound and control total duration.

### 8.1. Avoid Creating a Recovery Loop

Do not route the error straight back into the channel feeding the same handler without a deduplication key, counter, and timing policy. If the handler keeps failing, the system can create a loop:

~~~text
handler fails -> recovery -> resend to same channel -> handler fails -> ...
~~~

Separating the error channel from the primary processing channel keeps routing under control. If reprocessing is needed, design it as a scheduled job with its own limits and state.

### 8.2. Relationship with Transactions and Redelivery

Suppose a consumer receives a message from a broker inside a transaction and the retry advice sits inside that transaction:

- If the handler throws an error outward, the transaction may roll back and the broker may redeliver the message per configuration.
- If the callback handles the error and returns normally, the outer transaction may see a normally completed call; that exception is no longer present to trigger rollback.
- Even then, if the handler or a resource already marked the transaction rollback-only, commit can still fail.

These are consequences to verify on your specific transaction boundary; they are not a guarantee that "successful recovery always acks" or "throwing an error always triggers broker redelivery."

If you must persist an error record before acknowledging processing, ensure consistency between error persistence and ack/commit. Sending to an in-memory `QueueChannel` does not provide that consistency. One design option is persisting the work for later handling alongside business data in an appropriate transaction and letting a separate publisher dispatch it; other options depend on the broker's and application's transactional capabilities.

### 8.3. Stateful Retry Needs a Stable Key

With stateful retry, the advice retains state across redeliveries. The key must represent the same business request upon redelivery, such as the `requestId` originally generated by the system.

Do not use a fresh `MessageHeaders.ID` generated on every message reconstruction as a default key in all cases. When the key changes, the system may treat each redelivery as a brand-new request and never reach the intended recovery condition.

In Spring Integration 7.0, stateful retry is configured with `setStateKeyFunction(...)`; in 6.x, with `RetryStateGenerator`. The lesson's examples leave them disabled so attempt counting and callback observation happen within a single send. [Stateless and stateful retry configuration](https://docs.spring.io/spring-integration/docs/7.0.0/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 9. Testing Observable Behavior

Tests must distinguish business results, service call counts, and error routing.

### 9.1. Scenarios to Cover

With the `maxRetries(2)` policy in Section 5:

| Scenario | Expected Client Calls | What to Verify |
|---|---:|---|
| Succeeds immediately | 1 | Real result, no fallback |
| Transient failure then succeeds on second call | 2 | Real result |
| Continuous transient failure | 3 | `UNAVAILABLE` with matching `requestId` |
| Non-retryable error | 1 | Exception continues propagating outward |
| Recovery cannot extract valid message | Per prior failure | Does not return invalid fallback |
| Recoverer sends error successfully | Per endpoint policy | One `ErrorMessage` on recovery channel |
| Recovery channel full | Per endpoint policy | Send failure is not masked as success |

Do not assert exact execution durations using tight bounds like `200 ms` and `201 ms`. Schedulers, CI runners, and mock clocks can all cause timing jitter. Call counts and response contents reflect the lesson's goals far better.

### 9.2. JUnit Example for the Fallback Configuration

The test below uses the Section 5 configuration, `spring-test` 7.0.x, JUnit Jupiter, and Mockito. `@MockitoBean` replaces the client bean with a mock so each invocation can be controlled explicitly. [MockitoBean Javadoc](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html).

~~~java
package example.recovery;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.recovery.QuoteRecoveryConfig.PartnerClient;
import example.recovery.QuoteRecoveryConfig.PartnerUnavailableException;
import example.recovery.QuoteRecoveryConfig.QuoteGateway;
import example.recovery.QuoteRecoveryConfig.QuoteRequest;
import example.recovery.QuoteRecoveryConfig.QuoteResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringJUnitConfig(QuoteRecoveryConfig.class)
class QuoteRecoveryTest {

    @Autowired
    QuoteGateway gateway;

    @MockitoBean(enforceOverride = true)
    PartnerClient partnerClient;

    @Test
    void returnsActualQuoteWhenFirstAttemptSucceeds() {
        QuoteRequest request = new QuoteRequest("q-1", "SKU-001");
        QuoteResult actualQuote = new QuoteResult(
                "q-1", "OK", new BigDecimal("125000"));

        when(partnerClient.fetch(request)).thenReturn(actualQuote);

        assertEquals(actualQuote, gateway.quote(request));
        verify(partnerClient, times(1)).fetch(request);
    }

    @Test
    void returnsActualQuoteAfterOneTransientFailure() {
        QuoteRequest request = new QuoteRequest("q-2", "SKU-001");
        QuoteResult actualQuote = new QuoteResult(
                "q-2", "OK", new BigDecimal("125000"));

        when(partnerClient.fetch(request))
                .thenThrow(new PartnerUnavailableException("Temporary error"))
                .thenReturn(actualQuote);

        assertEquals(actualQuote, gateway.quote(request));
        verify(partnerClient, times(2)).fetch(request);
    }

    @Test
    void returnsUnavailableAfterRetryLimit() {
        QuoteRequest request = new QuoteRequest("q-3", "SKU-001");

        when(partnerClient.fetch(request))
                .thenThrow(new PartnerUnavailableException("Still failing"));

        QuoteResult result = gateway.quote(request);

        assertAll(
                () -> assertEquals("q-3", result.requestId()),
                () -> assertEquals("UNAVAILABLE", result.state()),
                () -> assertNull(result.price()));
        verify(partnerClient, times(3)).fetch(request);
    }

    @Test
    void propagatesFailureWithoutBusinessFallback() {
        QuoteRequest request = new QuoteRequest("q-4", "SKU-INVALID");

        when(partnerClient.fetch(request))
                .thenThrow(new IllegalArgumentException("Invalid SKU"));

        assertThrows(
                MessagingException.class,
                () -> gateway.quote(request));
        verify(partnerClient, times(1)).fetch(request);
    }
}
~~~

For the error-publishing strategy, use a fresh recovery channel per test, receive with a bounded timeout, verify the `ErrorMessage` type and original request details, and assert there is no unexpected second error message. A test that only checks "no exception thrown" does not prove the failed work was persisted or routed to the right place.

The test snippets in this lesson are practice material; place them in a project with the matching dependencies to compile and run.

## 10. When a Project Uses Spring Integration 6.x and Spring Retry 2.x

### 10.1. Key Differences to Remember

| Topic | Spring Integration 6.x | Spring Integration 7.0 |
|---|---|---|
| Recovery callback | `org.springframework.retry.RecoveryCallback<T>` | `org.springframework.integration.core.RecoveryCallback<T>` |
| Callback signature | `recover(RetryContext context) throws Exception` | `recover(AttributeAccessor context, Throwable cause)` |
| Source of exception | `context.getLastThrowable()` | `cause` parameter |
| Retry config on advice | `setRetryTemplate(...)` | `setRetryPolicy(...)` |
| Attempt count in examples | `maxAttempts(3)` or `SimpleRetryPolicy(3, ...)`: 3 total | `maxRetries(2)`: 1 initial + 2 retries |
| State across redeliveries | `RetryStateGenerator` | `setStateKeyFunction(...)` |

This is an API change, not just an import rename. Spring Retry's single-parameter callback cannot be passed verbatim to Spring Integration 7.0's setter expecting a two-parameter callback. [Spring Retry 2.x RecoveryCallback](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RecoveryCallback.html), [Spring Integration 6.x to 7.0 Migration Guide](https://github.com/spring-projects/spring-integration/wiki/Spring-Integration-6.x-to-7.0-Migration-Guide).

### 10.2. Equivalent Configuration for 6.x

The snippet below **replaces** the recovery and retry beans from Section 5 when running on 6.x. The business types and `containsCause(...)` / `requireFailedMessage(...)` helpers remain the same as explained earlier. Add a `spring-retry` 2.x dependency compatible with your project's dependency management.

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandlingException;
import org.springframework.retry.RecoveryCallback;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

// Place in QuoteRecoveryConfig instead of the corresponding 7.0 beans.
@Bean
public RequestHandlerRetryAdvice quoteRetryAdvice() {
    Map<Class<? extends Throwable>, Boolean> retryable =
            Map.of(PartnerUnavailableException.class, true);

    // 3 is total invocations; true enables cause traversal.
    SimpleRetryPolicy policy =
            new SimpleRetryPolicy(3, retryable, true);

    FixedBackOffPolicy backOff = new FixedBackOffPolicy();
    backOff.setBackOffPeriod(100);

    RetryTemplate template = new RetryTemplate();
    template.setRetryPolicy(policy);
    template.setBackOffPolicy(backOff);

    RecoveryCallback<Object> recovery = context -> {
        Throwable cause = context.getLastThrowable();
        Message<?> message = requireFailedMessage(context, cause);

        if (!(message.getPayload() instanceof QuoteRequest request)) {
            throw new MessageHandlingException(
                    message, "Payload is not suitable for recovery", cause);
        }

        if (!containsCause(cause, PartnerUnavailableException.class)) {
            throw new MessageHandlingException(
                    message, "Error has no business fallback", cause);
        }

        return new QuoteResult(
                request.requestId(), "UNAVAILABLE", null);
    };

    RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
    advice.setRetryTemplate(template);
    advice.setRecoveryCallback(recovery);
    return advice;
}
~~~

Spring Retry's `RetryContext` is an `AttributeAccessor`, so the message-reading helper accepts it directly. The 6.x advice attaches the current message under `FAILED_MESSAGE_CONTEXT_KEY`. [RetryContext Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryContext.html), [6.5 advice source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.java).

`SimpleRetryPolicy` counts the initial call inside `maxAttempts`. Enabling `traverseCauses` helps the policy detect business exceptions wrapped inside messaging exceptions. In addition, Spring Retry 2.x can mark certain errors as non-recoverable; thus, "do not retry" and "do not recover" are two distinct decisions. [SimpleRetryPolicy Javadoc](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

### 10.3. RecoveryCallback Is Different from @Recover

`RecoveryCallback` is a callback explicitly configured on a retry template or advice matching the framework version. `@Recover` belongs to using Spring Retry via annotations and proxies.

Simply adding a `@Recover` method to a service does not mean `RequestHandlerRetryAdvice` will automatically find and invoke that method. With the advice setup in this lesson, the recovery path is specified via `setRecoveryCallback(...)`.

## 11. Design Decisions Before Going to Production

### 11.1. Error Classification and Action Selection

| Error Type | Direction to Consider |
|---|---|
| Partner service temporarily down | Bounded retry; fallback if business accepts it |
| Malformed request | Reject early; do not retry unchanged invalid data |
| Insufficient access permissions | Report configuration or authorization error; avoid burst retries |
| Operation may have executed but response was lost | Query status via idempotency key before re-executing |
| Mandatory recovery record fails to save | Preserve failure status by propagating error outward |

This table is a design guide; concrete classification must follow the partner service contract. An HTTP status code or a timeout does not by itself prove no side effects occurred.

### 11.2. Both Retry and Recovery Require Idempotency

Fetching a quote is a read operation, making it easy to illustrate. For payments or order creation, the first call may have succeeded externally while the response was lost. Blind retries can create duplicate transactions.

Use a stable idempotency key, status lookup, and compensation rules where applicable. Callbacks that send notifications, write error records, or enqueue reprocessing tasks must also deduplicate when a broker redelivers after an error or when a process restarts.

Do not use a fallback like "paid" simply because the system did not receive a response. Recovery must preserve the business meaning of an unknown state.

### 11.3. Time Limits and Retry Layering

The time budget of one processing cycle can be estimated as:

~~~text
Total time ≈
    sum of handler invocation durations
    + sum of backoff intervals
    + recovery execution duration
~~~

If the HTTP client retries on its own, the endpoint has retry advice, and the broker also redelivers, actual invocations can spike sharply. Designate one primary owner for each error category and track total attempts per business key.

### 11.4. Observing the Right States

Distinguish these metrics:

- Handler succeeded without retry.
- Handler succeeded after retry.
- Retry cycle ended in error.
- Callback returned a fallback.
- Callback published an error successfully.
- Callback also failed.

A gateway receiving a valid object via fallback does not mean the partner service is healthy. Track fallback rates separately along with backlog age in the error store. Logs should include request IDs or correlation keys while limiting sensitive data and large payloads.

## 12. Common Pitfalls and How to Spot Them

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Callback fails to compile after upgrade | Using single-param callback or Spring Retry imports in a 7.0 config | Check packages, signatures, and setters |
| Service called more times than expected | Confusing `maxRetries` with `maxAttempts`, or multiple retry layers | Count client calls per request ID |
| Data errors also turn into fallbacks | Callback does not classify the final error | Test with an exception outside the retryable set |
| Gateway waits even though error was sent | Recoverer returns `null`, no reply matching the contract | Check reply channel and return type |
| Errors are logged but no work is queued for retry | Only logging or sending to an in-memory queue | Check durable store and consumers |
| Duplicate error notifications | Recovery publishes an error and also rethrows into another handler | Trace the actual path and count messages |
| Recovery never triggers across redeliveries | Stateful key changes between deliveries | Compare the business key on each delivery |
| Correlation lost after recovery | Built a new message missing required headers | Inspect headers before aggregator or gateway |

## 13. Self-Verification Exercises

1. Run the Section 5 example with the simulated client always failing. Verify the gateway receives `UNAVAILABLE` with the matching request ID.
2. Use a mock to make the client fail once and then succeed. Verify the result is the real quote and total calls equal two.
3. Have the client throw `IllegalArgumentException`. Verify it is not converted into `UNAVAILABLE`.
4. Build a separate one-way flow using the Section 6 configuration. Send one message and read exactly one `ErrorMessage` from the recovery channel.
5. Limit the recovery queue to one item, run no consumer, and send enough messages to fill the queue. Observe the send failure upon timeout.
6. Replace the in-memory queue with an error store suited to your application. Define the condition under which the initial consumer is allowed to acknowledge processing.
7. If you add a splitter and aggregator, decide whether each failed item produces a fallback or routes separately to an error flow; then verify group completion conditions.

Your completion criterion is being able to explain **who receives the result**, **where error messages go**, **when the system still reports failure**, and **what is guaranteed after recovery returns** for each chosen configuration.
