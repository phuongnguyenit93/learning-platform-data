# Before, after, and exception advice in Spring Integration

## 1. Why wrap a message handler with advice?

In the **SPRING_INTEGRATION_RUNTIME** module, messages move across channels to a consumer endpoint, and the endpoint invokes a business handler. In practice, beyond processing the payload, each handler also needs logging, timing, precondition checks, auditing, error classification, metrics, transactions, and sometimes retries. Putting all of this logic inside every order-processing or API-calling method duplicates code and makes execution ordering hard to control.

The topic **Advice chain → Before, after, and exception advice** focuses on injecting behavior **before**, **after success**, and **when the handler throws an exception** without modifying the handler's business logic.

Example:

~~~mermaid
flowchart LR
    I["Input message"] --> E["Consumer endpoint"]
    E --> B["BEFORE: log / timer / audit"]
    B --> H["Handler: call shipping API"]
    H -->|Success| S["AFTER SUCCESS: metric / audit"]
    H -->|Exception| X["ON ERROR: log / classify"]
    S --> O["Reply / finish"]
    X --> D{"Propagate error outward?"}
    D -->|Yes| F["error flow / caller / broker"]
    D -->|No, intentionally| R["Fallback / finish per contract"]
~~~

**Key point:** in Spring Integration, most handler advice is **around advice**: a single interceptor can implement the before, after, and exception paths using `try/catch/finally`. They are not three separate Spring Integration annotations. Exact behavior depends on the advice class, advice order in the chain, handler type, and the flow's thread/transaction boundaries.

## 2. Execution model: advice wrapping handler invocation

A `MessageChannel` transports messages. A `MessageHandler` receives and processes messages. A consumer endpoint (such as a service activator) connects a channel to a handler and can install an **advice chain** on that handler.

Suppose we have two advice instances:

~~~text
adviceChain = [A, B]

A.before
  B.before
    handler()
  B.afterSuccess or B.onException
A.afterSuccess or A.onException
~~~

The first advice is **outermost**, while the last advice sits closest to the handler. This is a *nested* order, not A.before → B.before → handler → A.after → B.after.

~~~mermaid
sequenceDiagram
    participant C as Consumer endpoint
    participant A as Advice A (outer)
    participant B as Advice B (inner)
    participant H as Handler
    C->>A: invoke(message)
    A->>A: before A
    A->>B: proceed()
    B->>B: before B
    B->>H: proceed()
    alt Success
        H-->>B: result
        B->>B: afterSuccess B
        B-->>A: result
        A->>A: afterSuccess A
        A-->>C: result
    else Exception
        H--xB: exception
        B->>B: onException B
        B--xA: propagate
        A->>A: onException A
        A--xC: propagate
    end
~~~

If B **catches and swallows an exception**, A may see B's call as a success and run its after-success branch. If A throws in `before`, B and the handler are never called. If B throws inside `afterSuccess` itself, A enters its exception branch. Therefore, describe "success" as **success within the advice's observed scope**, not a guarantee that the whole flow committed.

### Three phases commonly referenced in programming

| Phase | Timing | Typical tasks | Things to watch |
| --- | --- | --- | --- |
| **Before** | Before calling the handler / inner advice | Check headers, start timer, log request ID, enforce policy | If `before` throws, the handler does not run |
| **After success** | Handler / inner advice returns normally | Record success metric, publish audit, inspect result | Does not run on unhandled exceptions; reply may not have reached downstream yet |
| **On exception** | Handler / inner advice throws an exception | Record failure metric, enrich context, rethrow, recover | Swallowing errors alters ack/transaction/retry semantics |
| **Finally / after completion** | On return **or** on throw | Stop timer, release resources | Runs even on failure; exceptions in `finally` can mask the original error |

A method returning `null` normally **is not equivalent to an exception**. If the endpoint allows no reply, after-success can still run; if a reply is required, the reply-check exception may occur *outside* the scope of a standard request-handler advice.

## 3. Distinguishing request-handler advice, handle-message advice, and poller advice

Not every advice wraps the same segment of a message flow.

| Mechanism | Typical scope | Primary use |
| --- | --- | --- |
| `AbstractRequestHandlerAdvice` / `MethodInterceptor` in an endpoint advice chain | That endpoint's handler; for reply-producing handlers, usually `handleRequestMessage()` | Logging, auditing, retries, timing, circuit breaking for a specific operation |
| `HandleMessageAdvice` or `HandleMessageAdviceAdapter` | `MessageHandler.handleMessage()`, wrapping reply handling and synchronous downstream steps in the current structure | Observing or controlling full `handleMessage` execution |
| **Poller advice** | The poll/dispatch cycle from a pollable channel or inbound adapter | Transactions/retries and controlling polling behavior |
| `ChannelInterceptor` | `preSend`, `postSend`, `afterSendCompletion`, `preReceive`, etc. on a channel | Observing/intercepting channel send/receive operations regardless of downstream handlers |

Reply-producing endpoints like `@ServiceActivator` or outbound gateways typically extend `AbstractReplyProducingMessageHandler`. For them, **request-handler advice** applies to `handleRequestMessage()`, while sending the reply and downstream consumers sit outside this advice's scope. For non-reply-producing handlers, advice may wrap `handleMessage()`.

For example, `input → @Transformer → DirectChannel → @ServiceActivator`: if advice is attached to the transformer and the downstream service activator fails, request-handler advice on the transformer will not necessarily catch that error, because dispatching the reply downstream happens after `handleRequestMessage()`. This is a crucial distinction when implementing exception handling and transactions.

**Ordering exception:** implementations of `HandleMessageAdvice` can be separated from the request-handler advice chain and applied at the `handleMessage()` level. On reply-producing handlers, configuration order in a single list does not guarantee the combined execution order when mixing both advice kinds. Design scopes clearly and verify with logs.

## 4. How to write custom advice with before, after, and exception hooks

Spring Integration recommends extending `org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice` when you need behavior tied to message handlers. Instead of working directly with `MethodInvocation` and AOP proxies, the class provides:

~~~java
protected Object doInvoke(
        ExecutionCallback callback,
        Object target,
        Message<?> message) throws Exception
~~~

- `callback.execute()` invokes the handler (or inner advice) **once** and returns the result.
- `target` is the target handler, useful for attaching per-handler state/metrics if the advice is reused across endpoints.
- `message` is the input message **before handler processing**, giving access to headers, correlation, and payload for auditing.
- The return value from `doInvoke()` is passed back to the endpoint's processing. Do not arbitrarily replace the result with `null` or another type without a fallback contract.

### Example: timing and recording status

~~~java
import org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice;
import org.springframework.messaging.Message;

public final class TimingAuditAdvice extends AbstractRequestHandlerAdvice {

    @Override
    protected Object doInvoke(
            ExecutionCallback callback,
            Object target,
            Message<?> message) throws Exception {

        long startedAt = System.nanoTime();
        Object trace = message.getHeaders().get("traceId");
        System.out.println("BEFORE trace=" + trace);

        try {
            Object result = callback.execute(); // Once; does not retry by itself.
            System.out.println("AFTER_SUCCESS trace=" + trace);
            return result;
        }
        catch (Exception ex) {
            System.err.println("ON_EXCEPTION trace=" + trace
                    + " type=" + ex.getClass().getSimpleName());
            throw ex; // Preserve the handler's error semantics.
        }
        finally {
            long elapsed = System.nanoTime() - startedAt;
            System.out.println("AFTER_COMPLETION nanos=" + elapsed);
        }
    }
}
~~~

In this code, `AFTER_COMPLETION` always runs after `callback.execute()` returns or throws. It measures the duration of **the scope wrapped by the advice**, not total latency from producer to destination system.

In real applications, use structured logging and metrics (success/error counters, latency histograms), avoid `System.out`/`System.err`, and avoid logging sensitive payloads. If the advice holds state, use thread-safe structures or local variables like `startedAt` rather than shared mutable fields across messages.

**Never call `callback.execute()` twice to simulate a retry.** When an advice must repeat an invocation, it must use `callback.cloneAndExecute()` to reset AOP progression before each call; Spring Integration already provides `RequestHandlerRetryAdvice`, so prefer using it and tuning its retry policy over hand-rolling a loop.

### Wrapping and rethrowing exceptions

If you want to add error context:

~~~java
catch (Exception ex) {
    // Log with context and preserve the original cause.
    logger.error("Handler failed, traceId={}", traceId, ex);
    throw ex;
}
~~~

Never construct a new exception that drops the cause or failed message; doing so discards `MessagingException` / `MessageHandlingException` details. If you intentionally translate an exception into another business error, document the contract, preserve `cause`, and update retry/recovery rules for the new error type.

## 5. Built-in advice for after-success and after-failure

Spring Integration provides `ExpressionEvaluatingRequestHandlerAdvice` to evaluate two separate SpEL expressions corresponding to success and failure of **the handler within the advice scope**.

Common properties:

| Property | Meaning |
| --- | --- |
| `setOnSuccessExpressionString(...)` | Expression evaluated on handler success, rooted on the input message |
| `setSuccessChannel(...)` / `setSuccessChannelName(...)` | Destination for the success expression result |
| `setOnFailureExpressionString(...)` | Expression evaluated on handler failure; exposes `#exception` |
| `setFailureChannel(...)` / `setFailureChannelName(...)` | Destination for failure information |
| `setTrapException(true)` | Catches and **does not rethrow** the handler exception, changing endpoint error behavior |
| `setReturnFailureExpressionResult(true)` | Uses the failure expression result as the reply-producing handler's return value in supported cases |
| `setPropagateEvaluationFailures(true)` | Allows exceptions from the success expression to propagate to the caller, rather than ignoring success expression evaluation errors by default |

Registration example:

~~~java
@Bean("outcomeAdvice")
ExpressionEvaluatingRequestHandlerAdvice outcomeAdvice() {
    ExpressionEvaluatingRequestHandlerAdvice advice =
            new ExpressionEvaluatingRequestHandlerAdvice();

    advice.setSuccessChannelName("auditSuccess");
    advice.setOnSuccessExpressionString("payload");

    advice.setFailureChannelName("auditFailure");
    advice.setOnFailureExpressionString("payload");

    advice.setTrapException(false); // Handler exceptions still propagate to caller.
    return advice;
}
~~~

This configuration creates **two side audit branches** without altering the handler's normal reply.

### What message does the success branch emit?

When the handler succeeds, the advice can send an `AdviceMessage<?>` to `auditSuccess`:

- `payload` is **the expression result**, such as `"ORDER-42"` if the expression is `payload`.
- `inputMessage` holds **the original message that entered the endpoint**, not the reply object returned by the handler.
- The audit message is a side event; the handler's output continues according to the endpoint contract.

Because the expression evaluates against **the input message**, `onSuccessExpression = "payload"` typically returns the original payload. If a transformer converts `" abc "` into `"ABC"`, the success event can still carry `" abc "`; do not expect it to hold the transformed value automatically.

### What message does the failure branch emit?

When the handler throws an exception, the advice can send an `ErrorMessage` to `auditFailure` with:

- `payload` as `MessageHandlingExpressionEvaluatingAdviceException` (the advice's exception class).
- `cause` as the exception thrown by the handler or an appropriate wrapper.
- `failedMessage` pointing to the failed message for diagnostics.
- `evaluationResult` as the value of `onFailureExpression`, e.g., an ID from the input payload.

By default, after emitting the failure event, **the original exception still propagates outward**. With `trapException = true`, the call may finish normally and return `null`; if the endpoint sets `requiresReply`, another error can occur due to the missing reply. Never use `trapException` just to make the system "stop logging errors": upstream may ack the message or commit a transaction as if it succeeded.

If a channel is set without an expression, the advice defaults to `payload`. An error while evaluating the success expression does not automatically trigger the failure expression; use `propagateEvaluationFailures` when audit expression failures must be treated as critical errors.

## 6. Complete example: two advice instances and two audit branches

The example below uses **Spring Boot + Spring Integration**, Java 17+, and package `demo.integration`. Put all code into a single `AdviceChainDemoApplication.java` file; the only `public` class is the application class. Channels are `DirectChannel` so synchronous invocation ordering can be observed.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.handler.advice.AbstractRequestHandlerAdvice;
import org.springframework.integration.handler.advice.ExpressionEvaluatingRequestHandlerAdvice;
import org.springframework.integration.message.AdviceMessage;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class AdviceChainDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AdviceChainDemoApplication.class, args);
    }

    @Bean("requests")
    MessageChannel requests() {
        return new DirectChannel();
    }

    @Bean("results")
    MessageChannel results() {
        return new DirectChannel();
    }

    @Bean("auditSuccess")
    MessageChannel auditSuccess() {
        return new DirectChannel();
    }

    @Bean("auditFailure")
    MessageChannel auditFailure() {
        return new DirectChannel();
    }

    @Bean("timingAdvice")
    TimingAdvice timingAdvice() {
        return new TimingAdvice();
    }

    @Bean("outcomeAdvice")
    ExpressionEvaluatingRequestHandlerAdvice outcomeAdvice() {
        ExpressionEvaluatingRequestHandlerAdvice advice =
                new ExpressionEvaluatingRequestHandlerAdvice();

        advice.setSuccessChannelName("auditSuccess");
        advice.setOnSuccessExpressionString("payload");
        advice.setFailureChannelName("auditFailure");
        advice.setOnFailureExpressionString("payload");
        advice.setTrapException(false); // Default: still throw error to caller.
        return advice;
    }

    @Bean
    ApplicationRunner sample(@Qualifier("requests") MessageChannel input) {
        return args -> {
            input.send(MessageBuilder.withPayload("ok")
                    .setHeader("traceId", "trace-001").build());

            try {
                input.send(MessageBuilder.withPayload("fail")
                        .setHeader("traceId", "trace-002").build());
            }
            catch (RuntimeException ex) {
                System.out.println("UPSTREAM_CAUGHT "
                        + ex.getClass().getSimpleName());
            }
        };
    }
}

// Spring-managed advice bean reusable across multiple endpoints.
class TimingAdvice extends AbstractRequestHandlerAdvice {

    @Override
    protected Object doInvoke(
            ExecutionCallback callback,
            Object target,
            Message<?> input) throws Exception {

        long started = System.nanoTime();
        Object traceId = input.getHeaders().get("traceId");
        System.out.println("BEFORE " + traceId);

        try {
            Object reply = callback.execute();
            System.out.println("AFTER_SUCCESS " + traceId);
            return reply;
        }
        catch (Exception ex) {
            System.out.println("ON_EXCEPTION " + traceId);
            throw ex;
        }
        finally {
            System.out.println("AFTER_COMPLETION " + traceId
                    + " tookNs=" + (System.nanoTime() - started));
        }
    }
}

@MessageEndpoint
class AdviceDemoEndpoints {

    @ServiceActivator(
            inputChannel = "requests",
            outputChannel = "results",
            adviceChain = {"timingAdvice", "outcomeAdvice"})
    public String handle(String payload) {
        if ("fail".equals(payload)) {
            throw new IllegalStateException("Simulated handler failure");
        }
        return "processed:" + payload;
    }

    @ServiceActivator(inputChannel = "results")
    public void onResult(String result) {
        System.out.println("RESULT " + result);
    }

    @ServiceActivator(inputChannel = "auditSuccess")
    public void onSuccess(AdviceMessage<?> audit) {
        System.out.println("AUDIT_SUCCESS payload=" + audit.getPayload()
                + " original=" + audit.getInputMessage().getPayload());
    }

    @ServiceActivator(inputChannel = "auditFailure")
    public void onFailure(ErrorMessage error) {
        Throwable exception = error.getPayload();
        Object evaluated = "unknown";

        if (exception instanceof
                ExpressionEvaluatingRequestHandlerAdvice
                        .MessageHandlingExpressionEvaluatingAdviceException ex) {
            evaluated = ex.getEvaluationResult();
        }
        System.out.println("AUDIT_FAILURE evaluation=" + evaluated
                + " exception=" + exception.getClass().getSimpleName());
    }
}
~~~

> The demo requires the Spring Integration Core dependency (or Spring Boot Integration starter) matching your Boot version. When integrating into a real project, register channels/advice in the same application context and ensure the package is component-scanned. `System.out` is for experimentation only.

### Expected observations

For message `"ok"`:

~~~text
BEFORE trace-001
AUDIT_SUCCESS payload=ok original=ok
AFTER_SUCCESS trace-001
AFTER_COMPLETION trace-001 tookNs=...
RESULT processed:ok
~~~

For message `"fail"`:

~~~text
BEFORE trace-002
AUDIT_FAILURE evaluation=fail exception=MessageHandlingExpressionEvaluatingAdviceException
ON_EXCEPTION trace-002
AFTER_COMPLETION trace-002 tookNs=...
UPSTREAM_CAUGHT ...
~~~

The exception name printed at `UPSTREAM_CAUGHT` depends on Spring Integration's wrapper classes; do not write business code relying on that log string. `tookNs` varies by environment. The logs above reflect the synchronous order in this example, not an ordering guarantee across executors, brokers, or parallel message flows.

Because `outcomeAdvice` is the innermost advice, it emits its audit before `timingAdvice` runs after-success/on-exception. Dispatching the reply to `results` occurs after the advised handler section, so `RESULT` can appear **after** `AFTER_COMPLETION`. This illustrates the advice boundary of a reply-producing handler.

## 7. What changes when you reorder the chain?

When configured as:

~~~java
@ServiceActivator(
    inputChannel = "requests",
    outputChannel = "results",
    adviceChain = {"timingAdvice", "outcomeAdvice"})
~~~

`timingAdvice` is the outermost layer. If changed to `{"outcomeAdvice", "timingAdvice"}`, the call order becomes:

~~~text
outcomeAdvice
    timingAdvice
        handler
    timingAdvice (after / exception)
outcomeAdvice (publish audit)
~~~

This affects: log order, whether measured duration includes publishing the audit, which advice sees exceptions, and which advice is considered successful.

### Example combining retry and audit

Suppose the chain uses `{"auditAdvice", "retryAdvice"}` and the handler fails twice before succeeding on the third attempt:

~~~text
audit.before
    retry attempt #1 -> exception
    retry attempt #2 -> exception
    retry attempt #3 -> success
audit.afterSuccess  (once)
~~~

If the chain is `{"retryAdvice", "auditAdvice"}`:

~~~text
retry attempt #1 -> audit.before -> handler exception -> audit.onException
retry attempt #2 -> audit.before -> handler exception -> audit.onException
retry attempt #3 -> audit.before -> handler success   -> audit.afterSuccess
~~~

Both are valid, but they produce completely different metrics:

- **Audit outside retry:** one event per logical message, recording success only after the entire retry cycle succeeds; if retries are exhausted, one failure event is recorded.
- **Audit inside retry:** one event per **attempt**, suited for counting API calls and analyzing per-attempt errors; never confuse attempt events with logical business messages.

When an advice with `trapException(true)` sits inside retry, the outer retry will not see the swallowed error. This is a common ordering bug: retries never run even though the handler throws exceptions.

### Example combining transactions

~~~text
retryAdvice -> transactionAdvice -> handler
  Each attempt passes through transactionAdvice.

transactionAdvice -> retryAdvice -> handler
  All attempts sit inside the outer transactionAdvice scope.
~~~

If the transaction advice genuinely starts a new transaction per invocation, the first option can give each attempt its own transaction. The second can run the entire retry loop in one shared transaction, easily hitting `rollbackOnly` after a failed attempt. However, propagation, an existing transaction from a poller, and executor handoffs determine the final outcome; **advice order alone does not guarantee a fresh transaction**.

## 8. Filters, discard behavior, and after advice

`@Filter` is a notable case: a predicate method returning `false` means **rejecting the message**, not necessarily an exception. It can be paired with `discardChannel` to route rejected messages to another branch.

By default, filter discard logic can execute **within the advice scope**. With `discardWithinAdvice = "false"`, discarding (or the rejection exception) is handled **after** the chain completes.

~~~java
@Filter(
    inputChannel = "validate",
    outputChannel = "accepted",
    discardChannel = "rejected",
    discardWithinAdvice = "false",
    adviceChain = {"timingAdvice"})
public boolean valid(Order order) {
    return order.amount() > 0;
}
~~~

Consequences of choosing scope:

| Configuration | What can the advice observe? | Risk |
| --- | --- | --- |
| Discard inside advice | Can include discard logic and synchronous downstream consumers on the discard channel | An error in the reject branch might trigger retries on the filter |
| `discardWithinAdvice = "false"` | Advice focuses on the predicate/filter handler; discard runs outside the scope | Advice after-success does not indicate the reject branch processed successfully |

Do not use after-success to count `accepted` messages if the filter returns `false` without throwing. Count accepted states using metrics/flows on the respective branches or an appropriate observation mechanism.

## 9. How should exception advice handle errors?

There are three ways to handle exceptions, each with very different semantics:

| Strategy | Implementation | Upstream behavior |
| --- | --- | --- |
| **Observe and rethrow** | Log/audit, `throw ex` | Caller, poller, or error flow still sees the error |
| **Intentional recovery** | Durably store failure record, produce fallback/recovery result per contract | May finish normally and allow upstream ack |
| **Unplanned error swallowing** | Catch and return `null`/default value to ignore | Easily causes data loss and "false success" signals |

For `ExpressionEvaluatingRequestHandlerAdvice`, `failureChannel` is used to **emit an error event**; it does not mean the error has been recovered. `trapException = false` is the right default when you want outer transactions, retries, and error channels to keep seeing the exception.

When you genuinely need `trapException = true`, verify:

1. Should the message be acknowledged/committed immediately?
2. Did the recovery flow persist the error to a reliable store, or only log it?
3. Does the reply-producing endpoint require a reply? Will `null` trigger a `requiresReply` error?
4. Could duplicates arise under consumer retries or broker redelivery?
5. Does monitoring distinguish "recovered" from "business succeeded"?

If the error is just a transient HTTP timeout, consider `RequestHandlerRetryAdvice` with bounded attempts, backoff, and an appropriate recovery callback. If it is a schema error or invalid business data, retrying the exact same payload usually does not help.

## 10. Threading, pollers, errorChannel, and message stores

Advice executes **when the handler is invoked**. The thread executing the advice depends on the channel and endpoint:

| Dispatching | When advice runs | Where exceptions are seen |
| --- | --- | --- |
| `DirectChannel` + synchronous handler | On the thread calling `send()` | Usually propagates back through `send()` unless trapped/recovered |
| `ExecutorChannel` | On a `TaskExecutor` worker thread | Error handler/error flow of the async boundary; not necessarily catchable by sender |
| `QueueChannel` + polling consumer | When the poller fetches and dispatches a message | Poller error handler or corresponding transaction/retry |
| Inbound JMS/AMQP/Kafka adapter | On listener thread or adapter-configured worker | Adapter's ack/redelivery/error channel rules |
| Reactive/async handler | Depends on subscription/completion timing | Errors after return can occur outside synchronous advice |

**An advice seeing a handler return normally does not know whether a `Future`/reactive publisher will fail later.** For async handlers, use completion tracking or retry mechanisms compatible with the async abstraction.

### Transactions

Transactions are typically bound to threads. When advice wraps transaction advice, actual coverage depends on transaction propagation and where the transaction begins. `ExecutorChannel` crosses a thread boundary; transaction context does not automatically propagate to workers. If an after-success audit calls a separate database, determine whether it runs inside or outside the transaction; emitting an audit before commit can record "success" before the business transaction rolls back.

For strict requirements (such as requiring every DB-persisted order to have an audit event), consider the outbox pattern or proper after-commit event publishing rather than treating `afterSuccess` as equivalent to `afterCommit`.

### Retries

`RequestHandlerRetryAdvice` can retry the handler if exceptions propagate outward. Placing `ExpressionEvaluatingRequestHandlerAdvice` inside retry with `trapException(true)` can block retries. If a recovery callback finishes and returns normally, outer advice may count "success," even though business execution shifted to recovery.

### Message stores and correlation

Sending an `AdviceMessage`/`ErrorMessage` to an audit channel does not automatically guarantee durable persistence. When audits must survive restarts or support replay, route messages to a properly configured message store/broker/DB. Choose stable `eventId`/`correlationId` and `traceId` values, especially with retries and fan-out; a reprocessed message can emit multiple audit events.

Avoid using payloads as metric keys or tags because of high cardinality and sensitive data; use endpoint name, advice type, exception class, outcome, and controlled trace logs.

## 11. Endpoint lifecycle and advice chains

Advice beans are registered in the `ApplicationContext` and referenced by endpoints. If a consumer is not started, is stopped, or has no subscriber, sending messages can fail or never reach the advice. Check endpoint lifecycle and channel readiness.

With dynamic `IntegrationFlow` registrations via `IntegrationFlowContext`, distinguish the lifecycle of the **flow registration** from shared advice beans. Stopping/removing a flow affects endpoints in that flow; it does not automatically destroy shared advice beans in the root context. Stateful advice such as circuit breakers, rate limiters, or custom counters must be managed per target and lifecycle.

If an advice performs synchronous retry/backoff on the consumer thread, a running endpoint may still stall throughput because workers are blocked waiting. Check active threads, queue backlogs, and error rates before increasing concurrency.

## 12. Diagnosing tricky scenarios

| Runtime symptom | Common cause | How to investigate |
| --- | --- | --- |
| No BEFORE log | Advice not attached with right bean name, endpoint not scanned/started, or message never arrived | Check `adviceChain`, channel, endpoint lifecycle |
| BEFORE appears but no AFTER_SUCCESS | Handler/inner advice threw, or inner after-success threw | Inspect ON_EXCEPTION and root cause exception |
| AFTER_SUCCESS appears even though handler failed | Inner retry recovered successfully, or exception was trapped | Check advice order, `trapException`, recovery |
| No ON_EXCEPTION even though business rejected the request | Filter returned `false` normally; failure return code is not an exception | Add dedicated rejection metrics |
| Success audit appears before RESULT, yet RESULT consumer fails | Request-handler advice does not wrap downstream reply dispatch | Distinguish `handleRequestMessage` vs. `handleMessage` |
| Outer advice does not run in configured order | Mixed `HandleMessageAdvice` with request-handler advice on a reply-producing endpoint | Check advice types and actual scope |
| Failure audit sent yet upstream still gets exception | `failureChannel` only records errors; `trapException` defaults to false | Review rethrow/recovery decision |
| Switching `DirectChannel` to `ExecutorChannel` stops sender from catching errors | Error happens after async boundary | Configure error flow, log threads and traces |
| Retries do not run | Inner advice swallowed exception, handler caught error, or retry is outside error scope | Test with fault injection per handler |
| Transaction rolls back yet audit reports success | Audit ran after handler, before transaction commit | Use after-commit/outbox if commit semantics are needed |

### Technical checklist

- Identify **which handler** the advice wraps, whether it produces a reply, and where reply dispatch occurs.
- Specify chain order according to intent: per-message vs. per-attempt, transactions, and retries.
- In custom advice, call `callback.execute()` once; use `cloneAndExecute()` only if intentionally implementing repeated invocation.
- Preserve root causes when rethrowing exceptions; never trap errors without an explicit recovery contract.
- Distinguish a successful audit event from **transaction commit** or downstream completion.
- Keep bean names, channels, and consumers aligned for success/failure audits.
- Verify threads, queues, `errorChannel`, message stores, correlation, and retries in async deployments.
- Emit logs/metrics with endpoint, outcome, duration, and correlation; limit sensitive payload exposure.

## 13. Hands-on exercises

1. **Advice order:** run the Section 6 example with `"ok"` and `"fail"`; capture logs. Change `adviceChain` to `{"outcomeAdvice", "timingAdvice"}` and observe how the order shifts.
2. **Before throws:** add validation in `TimingAdvice` that throws when `traceId` is missing; confirm the handler never runs.
3. **Distinguish success/failure:** make the handler return `null` on an endpoint where reply is optional, then require a reply. Observe which errors occur inside vs. outside the advice scope.
4. **Trap exception:** enable `setTrapException(true)` in a test environment; observe whether `send()` still throws. Disable it again and explain the risk of accidental acks.
5. **Test retry order:** add a version-appropriate `RequestHandlerRetryAdvice` before and after `TimingAdvice`; record per-message and per-attempt metrics.
6. **Async boundary:** replace `requests` with a bounded `ExecutorChannel`; log threads for sender, advice, and handler; move error observation to an error flow.
7. **Downstream exceptions:** make the `results` consumer throw; verify whether request-handler advice on the reply-producing handler catches downstream errors.
8. **Preserving audits:** simulate a crash after the handler succeeds but before commit, and analyze why a plain `AdviceMessage` cannot replace an outbox/message store.

## 14. Official references

- [Spring Integration — Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/handler-advice.html): handler advice scope, poller advice, chains.
- [Spring Integration — Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): outer/inner advice and transactions vs. retries.
- [Spring Integration — Custom Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/custom.html): `AbstractRequestHandlerAdvice` and `ExecutionCallback`.
- [Spring Integration — Provided Advice Classes](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html): `ExpressionEvaluatingRequestHandlerAdvice` and success/failure channels.
- [Spring Integration — Handling Message Advice](https://docs.spring.io/spring-integration/reference/handler-advice/handle-message.html): `HandleMessageAdvice`, ordering, and `handleMessage` scope.
- [Spring Integration — Advising Endpoints Using Annotations](https://docs.spring.io/spring-integration/reference/handler-advice/advising-with-annotations.html): `adviceChain` on `@ServiceActivator`, `@Transformer`, `@Filter`, and `@Splitter`.
- [Spring Integration API — AdviceMessage](https://docs.spring.io/spring-integration/api/org/springframework/integration/message/AdviceMessage.html), [ExpressionEvaluatingRequestHandlerAdvice](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/ExpressionEvaluatingRequestHandlerAdvice.html): message types and advice properties.
