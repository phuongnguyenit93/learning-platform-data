# Handling Exceptions in Asynchronous Tasks

## 1. Why Are Exceptions in Asynchronous Mail-Sending Tasks Harder to Handle?

In **Spring Framework Mail** applications, sending email via SMTP is an I/O operation that can take time because it must open a connection, authenticate, exchange data, and wait for a response from the mail server. Rather than forcing an HTTP request or business thread to wait for the send operation to finish, applications commonly use `@Async`, `CompletableFuture`, an executor, or a queue to process emails outside the main calling flow.

However, **asynchrony does not make exceptions disappear**; it only shifts where and when exceptions surface:

~~~text
HTTP request / business thread
           |
           | submit task
           v
      Async executor
           |
           v
   Prepare MIME message
           |
           v
   JavaMailSender.send(...)
           |
       +---+---+
       |       |
       v       v
    Success  Exception
       |       |
       v       v
   completion  CompletableFuture/handler/
               retry state/monitoring
~~~

For example, a controller may have already returned HTTP `202 Accepted`, yet a few seconds later SMTP rejects the recipient address. The exception occurs on an executor thread and **cannot automatically propagate back to an already-sent HTTP response**. Without a mechanism to receive and persist processing outcomes, the application could report “sent” even though SMTP never accepted the email.

An asynchronous mail-sending system must be able to answer:

1. Where is the exception delivered: caller, `Future`, `CompletableFuture`, or a handler?
2. Did the error occur while **submitting the task**, **building MIME**, or **sending via SMTP**?
3. Can the error be retried or must it stop?
4. Who saves the state so subsequent processing does not lose it?
5. If the SMTP outcome is ambiguous, does retrying risk sending duplicates?

> **Rule:** Do not treat “accepted the email send job” as “email sent successfully”. Clearly separate `QUEUED/SUBMITTED`, `SMTP_ACCEPTED`, `RETRY`, and `FAILED` according to the application's operational model.

## 2. Two Exception Boundaries in @Async

An `@Async` invocation has two distinct error boundaries:

**Boundary 1 — submitting the task on the caller thread:** The executor may reject immediately when the queue is full or during shutdown. For example, Spring's `TaskRejectedException` can be thrown when invoking the proxy. At that point, the task **has not been queued**.

**Boundary 2 — executing the task on the worker thread:** Exceptions can occur while rendering templates, building `MimeMessage`, connecting to SMTP, or sending mail. These exceptions happen **after** the async method was submitted and must be observed through a separate result channel.

| Timing | Example | Where to Handle |
| --- | --- | --- |
| Before executor accepts task | `TaskRejectedException` | Caller at the async invocation site |
| While building content | Missing template, missing data, `MessagingException` | Worker; convert to failed future or error status |
| While sending | `MailAuthenticationException`, `MailSendException`, network error | Worker; classify, save retry/failure |
| After successful send | Database fails to record `SENT` | Status-updating component; alert since SMTP may have accepted the mail |
| While reading result | `ExecutionException` or `CompletionException` | Caller/consumer awaiting Future |

This explains why a `try/catch` block placed solely around `asyncService.send(...)` **cannot catch every error arising inside the executor thread**.

## 3. How Spring @Async Operates

Spring allows annotating methods with `@Async` and enabling async support with `@EnableAsync`. A basic configuration:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean(name = "mailExecutor")
    public TaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("mail-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

A service can then select the executor by name:

~~~java
@Async("mailExecutor")
public CompletableFuture<MailSubmission> submit(MailCommand command) {
    // Code runs on an executor thread when called via Spring proxy.
}
~~~

The values 4/8 threads and queue capacity 200 are only examples. Pool sizing must depend on SMTP timeouts, connection/provider limits, and actual mail load. An executor with a bounded queue surfaces overload rather than accumulating unboundedly.

### 3.1. @Async Runs Through a Spring Proxy

In standard proxy mode, the call must pass through a Spring-managed bean:

~~~java
@Service
public class OrderService {
    private final AsyncMailService asyncMailService;

    public OrderService(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    public void onOrderConfirmed(MailCommand command) {
        asyncMailService.submit(command);
    }
}
~~~

If a method in the same class calls an `@Async` method via `this.submit(...)`, the internal call may **bypass the proxy** and run synchronously. Likewise, manually constructing an object with `new AsyncMailService(...)` does not trigger `@Async`. Therefore, separate the coordinating service and the async-executing service into distinct Spring beans.

### 3.2. @Async Does Not Automatically Create Transactions or Propagate Thread Context

The executor thread is a different execution context. JDBC/JPA transactions bound to the original calling thread do not automatically follow the worker; `ThreadLocal`-based data such as MDC, security context, and locale context are also not carried over by default under all configurations.

When business data is needed, pass an **explicit DTO/snapshot**; if the worker needs a database transaction, open a separate transaction. Do not pass an uninitialized lazy JPA entity to an async method assuming the request's persistence context is still open.

## 4. Three Return Types and How Exceptions Are Received

Spring `@Async` is commonly used with methods returning `void`, `Future<T>`, or `CompletableFuture<T>`. Error channels differ:

| Return Type | Outcome When Worker Throws Exception | How Errors Are Received |
| --- | --- | --- |
| `void` | No result object for the caller to track | `AsyncUncaughtExceptionHandler` for uncaught exceptions, and/or handle inside the worker |
| `Future<T>` | Future completes with error | `future.get()` throws `ExecutionException`, whose cause is the root error |
| `CompletableFuture<T>` | Future completes exceptionally | `whenComplete`, `handle`, `exceptionally`, `join`, or `get` |

For email sending that requires outcome tracking, **`CompletableFuture<T>` is usually easier to coordinate than `void`**. Yet an in-memory Future does not replace a durable outbox/queue if the application must guarantee recovery after restarts.

### 4.1. Why Can @Async void Easily Lose Error Signals?

Example:

~~~java
@Async("mailExecutor")
public void sendLater(MimeMessage message) {
    mailSender.send(message);
}
~~~

The caller has no `Future` to observe. Uncaught exceptions from `void` methods are routed to Spring's `AsyncUncaughtExceptionHandler`. If the handler only logs and nothing else persists outcomes, the application does not know which sends need retrying.

This fits auxiliary, non-critical work or cases where **the worker itself manages durable state**. For transactional emails, do not rely solely on handler logs.

### 4.2. Exceptions in a Future Do Not Automatically Surface at the Caller

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command);

// future may still be running. The call above has usually already returned.
~~~

If the worker throws an exception later, it is represented as an **exceptionally completed future**. Having only a `try/catch` around `submit(...)` is insufficient to capture that error; you must observe the Future.

## 5. Complete Example: Sending HTML and Plain Text with CompletableFuture

Define command and outcome:

~~~java
package com.example.mail;

import java.time.Instant;
import java.util.UUID;

public record MailCommand(
        UUID deliveryId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}

public record MailSubmission(
        UUID deliveryId,
        Instant smtpAcceptedAt) {
}
~~~

`deliveryId` is the correlation key for a single send attempt; never use recipient email addresses or sensitive tokens as correlation IDs. The command has already been prepared/validated by the application layer before submission.

Sending service via Spring Mail:

~~~java
package com.example.mail;

import java.time.Instant;
import java.util.concurrent.CompletableFuture;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public CompletableFuture<MailSubmission> submit(MailCommand command) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom("notifications@example.com");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(command.plainText(), command.htmlText());

            // This is a synchronous I/O call, but runs on mailExecutor.
            mailSender.send(message);

            return CompletableFuture.completedFuture(
                    new MailSubmission(
                            command.deliveryId(), Instant.now()));
        } catch (MessagingException ex) {
            // MIME creation failure is a checked exception; wrap into
            // a domain exception so the Future completes exceptionally.
            throw new MailContentBuildException(
                    command.deliveryId(), ex);
        }
        // Unchecked MailException from JavaMailSender propagates out,
        // so the @Async proxy can complete the Future exceptionally.
    }
}
~~~

Application exception:

~~~java
package com.example.mail;

import java.util.UUID;

public class MailContentBuildException extends RuntimeException {
    private final UUID deliveryId;

    public MailContentBuildException(UUID deliveryId, Throwable cause) {
        super("Cannot prepare MIME message", cause);
        this.deliveryId = deliveryId;
    }

    public UUID deliveryId() {
        return deliveryId;
    }
}
~~~

Key points to understand:

1. `@Async("mailExecutor")` offloads method execution to the thread pool when invoked through a Spring proxy.
2. `JavaMailSender.createMimeMessage()` and `MimeMessageHelper` construct the MIME message.
3. `setText(plainText, htmlText)` produces a text/HTML alternative representation.
4. `mailSender.send(message)` remains blocking I/O, yet does not tie up the request thread.
5. Only after `send` completes normally does the service construct `MailSubmission`.
6. If `MessagingException` occurs while building the message, the worker throws `MailContentBuildException`; if the transport throws `MailException`, that error also completes the Future exceptionally.

**Important:** A successful outcome here means the transport send method completed, not that the email reached the inbox. The SMTP server may accept the message and still later bounce it, filter it as spam, or the recipient may never open it.

### 5.1. Why Does an @Async Method Return completedFuture?

Inside a method annotated with `@Async`, the code actually executes on a worker thread. The implementation can return `CompletableFuture.completedFuture(result)` as an internal value; **Spring's proxy** returns a Future to the caller representing the asynchronous execution.

There is no need to manually call `CompletableFuture.supplyAsync(...)` inside an `@Async` method. Doing so without specifying an executor may run the extra task on `ForkJoinPool.commonPool`, fragmenting thread and exception management.

## 6. Caller Observing Results and Exceptions

The caller should register a callback or integrate the Future into a stateful orchestration flow:

~~~java
try {
    CompletableFuture<MailSubmission> future =
            asyncMailService.submit(command);

    CompletableFuture<Void> observed = future.whenComplete(
            (submission, failure) -> {
                if (failure == null) {
                    logger.info(
                            "Mail submitted to SMTP deliveryId={}",
                            submission.deliveryId());
                } else {
                    Throwable root = unwrapCompletionException(failure);
                    logger.warn(
                            "Async mail failed deliveryId={} errorType={}",
                            command.deliveryId(),
                            root.getClass().getSimpleName());
                }
            }).thenApply(ignored -> null);

    // If coordinating multiple tasks, retain and observe 'observed'.
} catch (org.springframework.core.task.TaskRejectedException rejected) {
    // Executor did not accept task; persist state or enqueue.
    logger.warn(
            "Mail executor rejected deliveryId={}",
            command.deliveryId());
}
~~~

Wrapper unwrapping helper:

~~~java
static Throwable unwrapCompletionException(Throwable failure) {
    Throwable cause = failure;
    while ((cause instanceof java.util.concurrent.CompletionException
            || cause instanceof java.util.concurrent.ExecutionException)
            && cause.getCause() != null) {
        cause = cause.getCause();
    }
    return cause;
}
~~~

In practice you can omit the `observed` variable if only logging, yet when updating database state inside a callback you must **observe the state update outcome as well**. If the callback throws an exception and the dependent Future is discarded, state-update failures can go unhandled. A dispatcher backed by a durable outbox is more reliable than pure request-level callbacks.

### 6.1. Distinguishing whenComplete, exceptionally, and handle

| Method | Role | Caveat |
| --- | --- | --- |
| `whenComplete((result, error) -> ...)` | Observes success/failure while typically preserving original outcome | If callback throws, dependent Future can fail |
| `exceptionally(error -> fallback)` | Recovers with a fallback value on failure | Easy to mask errors accidentally by returning a “false success” |
| `handle((result, error) -> value)` | Transforms outcome of both branches | Useful for typed unified results |
| `thenCompose(...)` | Chains another async task | Failures propagate down unless recovered |
| `allOf(...)` | Awaits a group of Futures | Must inspect per-message outcomes, not just aggregate status |

**Never use `exceptionally(ex -> null)` solely to make exceptions disappear**. For transactional emails, persist failures into tracking or an outbox to decide on retries.

### 6.2. How Do get() and join() Differ?

~~~java
try {
    MailSubmission submission = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted while waiting", ex);
} catch (ExecutionException ex) {
    Throwable root = ex.getCause();
    // Handle root error.
}
~~~

`Future.get()` waits for completion and can throw `InterruptedException` / `ExecutionException`. `CompletableFuture.join()` also waits yet wraps errors in an unchecked `CompletionException`. Both **block the calling thread**. If an HTTP request calls `get()` right after submission, the response-time benefit of async can be lost.

Use callbacks, events, or outbox workers when waiting is unnecessary; await Futures only at boundaries that genuinely need the result.

## 7. AsyncUncaughtExceptionHandler for @Async void

When an `@Async` method returns `void` and throws an unhandled exception, Spring can route the error to `AsyncUncaughtExceptionHandler`. You can customize the handler via `AsyncConfigurer`.

~~~java
import java.lang.reflect.Method;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.stereotype.Component;

@Component
public class MailAsyncExceptionHandler
        implements AsyncUncaughtExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(MailAsyncExceptionHandler.class);

    @Override
    public void handleUncaughtException(
            Throwable ex,
            Method method,
            Object... params) {

        log.error(
                "Unhandled async exception method={} type={}",
                method.getName(),
                ex.getClass().getSimpleName());
        // Can increment counters/alerts; do not log full params
        // as they may contain emails, tokens, or personal data.
    }
}
~~~

Registering the handler:

~~~java
import java.util.concurrent.Executor;

import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncHandlerConfig implements AsyncConfigurer {

    private final MailAsyncExceptionHandler handler;

    public AsyncHandlerConfig(MailAsyncExceptionHandler handler) {
        this.handler = handler;
    }

    @Override
    public AsyncUncaughtExceptionHandler
            getAsyncUncaughtExceptionHandler() {
        return handler;
    }
}
~~~

This example configures the handler separately from the executor configuration above. In a real application, organize `@EnableAsync` and configuration beans cleanly, avoiding unnecessary duplicate configurations.

**Important limitation:** This handler primarily processes uncaught exceptions from `@Async void` methods. If a method returns `Future` or `CompletableFuture`, errors are normally held in the result object; observe the Future rather than expecting the handler to receive every error.

Moreover, `AsyncUncaughtExceptionHandler` does not automatically create retries, update an outbox, or guarantee exceptions are durably stored. The handler suits logging/alerting or dispatching to a controlled error-management mechanism.

## 8. Exceptions When the Executor Rejects Tasks

If the thread pool is busy and the queue reaches its limit, the executor can reject work. With `ThreadPoolTaskExecutor`, callers typically receive `TaskRejectedException` when invoking the `@Async` method:

~~~java
try {
    asyncMailService.submit(command);
} catch (TaskRejectedException ex) {
    // No evidence the task was accepted by the executor.
    // Update PENDING/RETRY or return an appropriate error.
    handleSubmissionFailure(command.deliveryId(), ex);
}
~~~

Do not confuse this with `MailSendException`: when a task is rejected, `JavaMailSender.send` **has not run**. This is an application capacity/backpressure issue.

### 8.1. Overload Strategies

- **Durable outbox/queue:** keep events in pending state so workers pick them up when capacity frees. Usually best for business emails.
- **Controlled rejection:** return a temporary overload error or explicit retry schedule if able to respond to the caller.
- **Rate-limit job production:** shrink batches, cap concurrently submitted jobs.
- **Measured capacity increase:** tune pool/queue against SMTP latency and provider quotas.

Do not use an unbounded queue just to avoid exceptions. If SMTP stays slow for long, memory and latency can grow uncontrollably. Policies like `CallerRunsPolicy` can execute tasks directly on the calling thread, blocking requests and altering async assumptions; use only as intentional backpressure.

### 8.2. Submission Errors Do Not Replace Execution Errors

With Futures, you must still handle **both**:

~~~text
asyncService.submit(...)
        |
        +--> TaskRejectedException (caller)
        |
        +--> accepted by executor
                   |
                   +--> successful completion
                   |
                   +--> exceptional completion (worker)
~~~

Catching only `TaskRejectedException` does not observe SMTP failures; registering only `whenComplete` is insufficient if submission is rejected before returning a Future.

## 9. Identifying Exception Categories When Sending Email

An email task involves multiple stages; identify where an error occurred before deciding to retry:

| Stage | Potential Exceptions/Issues | Initial Assessment |
| --- | --- | --- |
| Model creation and template rendering | Missing required data, template not found, invalid data | Usually needs data or code fixes; retrying as-is rarely helps |
| MIME creation via Jakarta Mail | `MessagingException`, invalid address, or malformed MIME structure | Inspect cause; usually preparation stage |
| SMTP authentication | `MailAuthenticationException` | Usually credentials/configuration or provider policy |
| Sending over SMTP | `MailSendException`, connection error, or SMTP response | May be transient, permanent, or ambiguous outcome |
| General Spring Mail handling | `MailException` | Base class only; insufficient alone for classification |
| Executor | `TaskRejectedException` | Task not accepted; capacity issue |
| Updating result state | Database error, optimistic lock conflict | Does not mean SMTP send failed |

### 9.1. Checked MessagingException vs. Runtime MailException

`jakarta.mail.MessagingException` is a checked exception commonly encountered while building MIME messages or calling Jakarta Mail APIs directly. `MimeMessageHelper` declares this checked exception on many methods.

By contrast, Spring's `JavaMailSender.send(...)` API uses the runtime `org.springframework.mail.MailException` hierarchy. Common subclasses:

- `MailAuthenticationException`: mail server authentication failure.
- `MailSendException`: failure sending one or more messages; may contain per-message details.
- `MailPreparationException`: error preparing content/message within a message-building workflow.
- `MailParseException`: mail parsing error, such as invalid addresses/syntax in the given context.

Do not write `catch (Exception ex) { return completedFuture(success); }` just to keep the application “running smoothly”. An unsent email must be reflected by an explicit failure status.

### 9.2. SMTP 4xx, 5xx Errors and Ambiguous Outcomes

4xx-series SMTP responses generally indicate temporary errors; 5xx responses usually indicate permanently rejected requests. Yet application-level classification also depends on which SMTP command failed, provider policies, and detailed error messages.

Examples:

- Connection cannot open because the provider is down: can retry.
- Queue or sending quota temporarily throttled: wait according to provider guidance.
- Recipient does not exist or sender is unauthorized: retrying identical data rarely helps.
- SMTP authentication failure: fix credentials/config; do not hammer with retries.
- Connection timeout **after sending DATA**, before receiving the final response: uncertain whether the server accepted the message.

The last point is crucial: an exception **does not always prove the email was not sent**. Workers should classify ambiguous outcomes as `UNKNOWN` or apply conservative duplicate-aware retry policies.

### 9.3. Classifying by Cause Rather Than a Single Class

Illustrative abstraction:

~~~java
public enum FailureKind {
    RETRYABLE,
    PERMANENT,
    UNKNOWN
}

public record FailureDecision(
        FailureKind kind,
        String errorCode) {
}
~~~

Application-layer classifier:

~~~java
public class MailFailureClassifier {

    public FailureDecision classify(Throwable error) {
        Throwable cause = unwrapCompletionException(error);

        if (cause instanceof MailContentBuildException) {
            return new FailureDecision(
                    FailureKind.PERMANENT, "MIME_PREPARATION");
        }

        if (cause instanceof MailAuthenticationException) {
            return new FailureDecision(
                    FailureKind.PERMANENT, "SMTP_AUTH");
        }

        if (cause instanceof TaskRejectedException) {
            return new FailureDecision(
                    FailureKind.RETRYABLE, "EXECUTOR_REJECTED");
        }

        // MailSendException can wrap multiple root causes.
        // Inspect cause, SMTP codes, and server exchange stage.
        return new FailureDecision(
                FailureKind.UNKNOWN, "SMTP_UNCLASSIFIED");
    }
}
~~~

This illustrates a **conservative** policy, not a complete production classifier. Auth errors are marked permanent for the current send attempt yet can be redriven after fixing configuration. For `MailSendException`, add SMTP/provider response analysis rather than concluding every case is retryable.

**Classifying as UNKNOWN is valid.** Recording uncertainty for reconciliation is better than asserting the email was never sent and retrying endlessly.

## 10. Controlled Retries Instead of Swallowing Exceptions

A useful retry strategy must define:

1. **Retry condition:** which errors are transient and stand a chance on retry?
2. **Limits:** maximum attempts or deadline?
3. **Backoff:** how long to wait between attempts?
4. **Jitter:** staggering retry times across workers to avoid thundering herds.
5. **Durable state:** where are current attempt counts and next attempt times persisted?
6. **Duplicate policy:** if SMTP received the message while result persistence failed, does retrying accept re-sending?

### 10.1. Exponential Backoff

A basic model:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where `d_0` is the initial wait, `n` is the failed attempt number, and `d_{\max}` is the wait cap. Adding random jitter helps prevent multiple workers retrying simultaneously.

Illustrative retry schedule:

| Failed Attempt | Base Delay |
| --- | --- |
| 1 | 30 seconds |
| 2 | 1 minute |
| 3 | 2 minutes |
| 4 | 4 minutes |
| 5 | 8 minutes |
| Beyond limit | Move to terminal status or await redrive |

This is only an example policy. Short-lived emails (like verification codes) should not be retried after token expiration; periodic reports may have longer retry windows.

### 10.2. Do Not Retry with an Infinite Loop in the Same Worker

Avoid:

~~~java
while (true) {
    try {
        mailSender.send(message);
        break;
    } catch (MailException ex) {
        // No delay, no limit, and no classification.
    }
}
~~~

This loop ties up a worker thread, increases SMTP load, and can spam recipients if the server accepted some sends before timing out. Instead, update status to `RETRY` with `nextAttemptAt` and free the worker for other tasks.

### 10.3. Short In-Memory Retries vs. Durable Retries

Short retries can be used for clear errors occurring before sending the message, yet **in-memory retries must not be the sole recovery mechanism**. If the JVM stops, all in-memory Futures and pending retries are lost.

For transactional emails, prefer:

~~~text
Outbox row
  attempt_count = 2
  status = RETRY
  next_attempt_at = 2026-11-12T10:30:00Z
        |
        v
Scheduler/worker claims when due
        |
        v
Send mail or update RETRY/FAILED/SENT
~~~

Timestamps in the diagram are illustrative. Workers only re-pick records after `next_attempt_at`, with attempt caps and ambiguous-outcome policies.

## 11. Outbox and Durable Error States

`@Async` moves tasks to another thread, yet **does not automatically create a durable queue**. If the application stops after returning an HTTP response but before the worker finishes sending, work in the executor can be lost.

A transactional outbox ties recording the email send intent to the business transaction:

~~~text
Business transaction
   ├── Update order/payment
   └── Insert mail_outbox(status=PENDING)
              |
            COMMIT
              |
              v
      Outbox worker claims row
              |
              v
       Send via SMTP
          /       \
         /         \
     success       error
        |            |
        v            v
      SENT        RETRY / FAILED
~~~

Typical statuses:

| Status | Meaning |
| --- | --- |
| `PENDING` | Send intent saved, awaiting worker |
| `PROCESSING` | Worker is processing and holds a lease |
| `RETRY` | Send failed and can be retried after a time |
| `SENT` | SMTP send call completed successfully |
| `FAILED` | Automatic retries stopped or unrecoverable error per policy |
| `UNKNOWN` (if used) | Send outcome unclear, needs cautious retry or reconciliation |

### 11.1. Updating Status After Send

A worker sends the email outside a database transaction, then updates status in a short transaction:

~~~java
try {
    MimeMessage message = mailMessageFactory.create(claimed);
    mailSender.send(message);

    // Separate transaction with owner/version condition.
    boolean marked = stateService.markSent(claimed);

    if (!marked) {
        reportStateConflict(claimed.deliveryId());
    }
} catch (MailException ex) {
    FailureDecision decision = classifier.classify(ex);
    stateService.markFailure(claimed, decision);
}
~~~

This is illustrative pseudocode. A real implementation must separate exceptions thrown by `send` from exceptions thrown by `markSent`. **Do not wrap post-send database updates in the same `catch (MailException)` and blindly retry SMTP**. A state-update error does not mean sending failed; retrying can create duplicates.

### 11.2. Crash Window and Exactly-Once Limits

There is no shared transaction between SMTP and the database:

~~~text
Worker calls JavaMailSender.send(message)
             |
             v
SMTP accepts message
             |
             v
Worker crashes before markSent()
             |
             v
Outbox still PROCESSING / lease expires
             |
             v
Another worker retries -> email may duplicate
~~~

Consequently, **transactional outbox + SMTP generally has at-least-once semantics, not exactly-once delivery**. Marking `SENT` before sending risks losing emails; marking after sending risks duplicates if status update fails.

A stable `Message-ID` helps correlation yet does not guarantee every SMTP server/mail client deduplicates. If a provider has a dedicated API supporting idempotency keys, leverage it per provider contract; plain SMTP has no universal exactly-once mechanism.

### 11.3. Leases and Concurrent Workers

If multiple workers poll the same table, atomic claiming and lease/owner or fencing tokens are required. A worker whose lease expired must not update `SENT`, `RETRY`, or `FAILED` on a row already reclaimed by another worker.

Example conditional update:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    sent_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id
  AND version = :claimed_version;
~~~

You must check the **number of updated rows**. If zero, the worker may no longer hold the lease or the version changed. If the earlier SMTP send succeeded, record this situation for reconciliation rather than simply reporting “email not sent”.

## 12. Transactions and Post-Commit Events

In many business flows, emails must only be sent when the database transaction commits. If calling `@Async` inside a transaction:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    repository.confirm(orderId);
    asyncMailService.submit(buildCommand(orderId));
}
~~~

the worker may start running **before the transaction commits**. It may fail to read new data or send an email for a transaction that ultimately rolls back.

### 12.1. @TransactionalEventListener AFTER_COMMIT

An option for tasks not requiring high durability is listening to events after commit:

~~~java
public record OrderConfirmedEvent(
        String publicOrderId,
        String recipientEmail) {
}
~~~

Publisher:

~~~java
@Transactional
public void confirmOrder(String id) {
    orderRepository.confirm(id);
    eventPublisher.publishEvent(
            new OrderConfirmedEvent(id, recipientEmail));
}
~~~

Listener:

~~~java
@Component
public class OrderMailListener {

    private final AsyncMailService mailService;

    public OrderMailListener(AsyncMailService mailService) {
        this.mailService = mailService;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        MailCommand command = makeCommand(event);
        mailService.submit(command);
    }
}
~~~

`AFTER_COMMIT` ensures the listener only runs after the transaction commits. However, the listener/future still depends on the running process. If the JVM dies after commit before the task is submitted, or the executor is overloaded, the email can still be lost. For critical emails, **an outbox written inside the business transaction** is a stronger solution.

### 12.2. @Async and @Transactional Do Not Share the Originating Transaction

If an `@Async` method has `@Transactional`, that transaction starts on the worker thread via the Spring proxy, **not the caller's transaction**. Do not rely on request lazy entities remaining attached to a persistence context in the worker.

When using an outbox, split into:

1. Short transaction to claim work.
2. SMTP send outside database transactions.
3. Short transaction to persist outcome.

Do not hold row locks or JDBC connections across an SMTP operation that can take seconds or minutes.

## 13. Timeouts, Cancellation, and Interruption

A mail-sending task running on an executor still performs network I/O. Without configured timeouts, workers can stay blocked too long when SMTP servers respond slowly.

Spring Boot configuration example:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Values are in milliseconds and purely illustrative:

- `mail.smtp.connectiontimeout`: limit for opening a connection.
- `mail.smtp.timeout`: limit for waiting to read data from the SMTP server.
- `mail.smtp.writetimeout`: write timeout when the transport supports this setting.

Timeouts prevent holding threads indefinitely and support outbox lease timeouts. Yet a timeout exception **does not prove the server never received the message**: inspect whether it occurred before or after DATA was transferred to SMTP.

### 13.1. CompletableFuture.orTimeout Does Not Guarantee Canceling SMTP Sends

Example:

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command)
                .orTimeout(15, TimeUnit.SECONDS);
~~~

`orTimeout` causes the Future to complete exceptionally with `TimeoutException` if exceeded, yet **does not guarantee** stopping the thread or aborting the SMTP request running in the background. The server may still accept the message after the caller treats the Future as timed out.

Therefore, do not use a Future timeout as proof to immediately resend. Configure transport timeouts, leases, and policies for handling uncertain outcomes.

### 13.2. Do Not Swallow InterruptedException

If a worker performs waits, sleeps, or `Future.get`, handle interruption properly:

~~~java
try {
    MailSubmission result = future.get(20, TimeUnit.SECONDS);
    recordSuccess(result);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Interrupted while waiting for mail task", ex);
} catch (TimeoutException ex) {
    recordUnknownResult(command.deliveryId());
} catch (ExecutionException ex) {
    recordFailure(
            command.deliveryId(), ex.getCause());
}
~~~

Restoring the interrupt flag with `Thread.currentThread().interrupt()` lets coordinating layers keep handling shutdown/cancellation signals. Recording `UNKNOWN` on timeout illustrates a conservative policy; if the application knows for sure it never connected to SMTP, policy may choose to retry.

### 13.3. Shutdown Does Not Guarantee All Futures Finish

When the application shuts down or deploys a new version, the executor may still have queued tasks. Define a shutdown policy:

- Stop accepting new tasks.
- Let running tasks finish within a time limit.
- Set reasonable SMTP timeouts.
- If using an outbox, allow rows not yet confirmed `SENT` to be reclaimed after lease expiration.

`ThreadPoolTaskExecutor` options such as `setWaitForTasksToCompleteOnShutdown` and `setAwaitTerminationSeconds` must be chosen per deployment needs. Waiting for the executor to finish only assists graceful shutdown; **it does not turn in-memory tasks into durable data** if the process is killed abruptly.

## 14. Safely Passing Context and Data to Workers

Every thread has its own state. Never assume HTTP request or business transaction context transfers intact to an async worker.

### 14.1. Pass a Snapshot Instead of Accessing Request/Session

Avoid:

~~~java
@Async("mailExecutor")
public void sendLater(HttpServletRequest request, OrderEntity order) {
    String recipient = request.getUserPrincipal().getName();
    String orderNumber = order.getOrderNumber();
    // order may already be detached and request may have ended.
}
~~~

Replace with a DTO containing all needed data:

~~~java
public record MailCommand(
        UUID deliveryId,
        String recipient,
        String subject,
        String plainText,
        String htmlText) {
}
~~~

The application service selects a valid recipient and builds a snapshot within the appropriate transaction boundary, then submits the immutable command. For jobs requiring durable storage, serialize only permitted fields into the outbox/queue.

### 14.2. Logging Context with MDC

`MDC` typically uses `ThreadLocal`, so the request thread's correlation ID may not automatically appear on executor threads. You can:

- Pass `deliveryId` as a command field and log it explicitly.
- Use a Spring `TaskDecorator` to copy MDC if required by the system.
- Use the application's chosen context propagation mechanism to carry traces/spans per observability standards.

Illustrative TaskDecorator example:

~~~java
executor.setTaskDecorator(runnable -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }

            runnable.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

This belongs in the executor configuration method before starting the thread pool, with `java.util.Map` and `org.slf4j.MDC` imports. Restore/clear MDC in `finally` because thread pools reuse threads. Without cleanup, log data from an earlier recipient could leak onto a later email.

### 14.3. SecurityContext and LocaleContext

If the task needs to know which user requested the send, pass an explicit identifier or verified permissions rather than reading `SecurityContextHolder` from the worker and assuming it matches the request thread. Spring Security provides executor wrappers to propagate security context when needed, yet least privilege and avoiding expired contexts must be considered.

Similarly, multilingual templates should receive `Locale` or a locale code from the command/mail model. Do not rely on the HTTP request's `LocaleContextHolder` in background threads without a controlled context-propagation mechanism.

## 15. Logging, Metrics, and Error Reporting Without Leaking Data

Mail-sending errors may contain recipient addresses, subjects, hostnames, message bodies, or credentials inside nested causes. Thus, error observability must be informative while avoiding logging sensitive data.

What to log/measure:

| Field | Purpose |
| --- | --- |
| `deliveryId` / `outboxId` | Correlation |
| `templateName` | Identify which notification type is failing |
| `attemptCount` | Number of send attempts tried |
| `failureKind` | RETRYABLE / PERMANENT / UNKNOWN |
| `errorCode` | Standardized error code |
| `executorName` | Identify thread pool |
| `duration` | Processing time from claim to outcome |
| `nextAttemptAt` | Next retry schedule |

Do not log raw:

- HTML/plain-text email bodies.
- Password reset/verification tokens or URLs containing tokens.
- SMTP passwords, credentials, authorization headers.
- Full `@Async` method arguments or outbox payloads.
- `Throwable.getMessage()` when it is unknown whether the message contains PII.

Normalized event log example:

~~~text
deliveryId=9c...
template=order-confirmation
attempt=3
result=RETRY
errorCode=SMTP_TEMPORARY
nextAttemptAt=...
~~~

Some useful metrics:

- `mail_async_submitted_total` and `mail_async_rejected_total`.
- `mail_smtp_accepted_total`, `mail_smtp_failed_total`.
- `mail_async_duration_seconds`.
- `mail_executor_active_threads` and `mail_executor_queue_depth`.
- `mail_outbox_pending_age_seconds`.
- `mail_outbox_retry_total`, `mail_outbox_failed_total`.
- `mail_outbox_state_conflict_total`.

Do not use email addresses or delivery IDs as metric labels because doing so can expose data and create huge cardinality. Use template, provider, error category, and environment as appropriate dimensions.

### 15.1. What Should the HTTP Response Convey?

If the request only creates an async job, an “accepted” response is more accurate than “sent successfully”. Example:

~~~json
{
  "requestId": "generated-delivery-id",
  "status": "QUEUED"
}
~~~

`QUEUED` should only be used when work has genuinely been accepted into a queue or outbox per system contract. If only submitting an in-memory task, remember work can be lost after restarts. A `202 Accepted` response does not itself create durability or retries.

If users need to check progress, provide a status endpoint based on an ID that reveals no sensitive data and enforces proper access control. Do not expose email addresses or raw SMTP error details to public clients.

## 16. Testing Asynchronous Exception Handling

With `@Async`, testing should verify not only that the method calls `JavaMailSender.send`, but also the proper **error channel** and post-error state.

### 16.1. Testing When the Transport Returns an Error

A small integration test through a Spring context can mock the mail sender and call the real `@Async` bean:

~~~java
@SpringBootTest
class AsyncMailServiceTest {

    @Autowired
    private AsyncMailService asyncMailService;

    @MockBean
    private JavaMailSender mailSender;

    @Test
    void failedMailSendCompletesFutureExceptionally() throws Exception {
        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties()));

        when(mailSender.createMimeMessage()).thenReturn(message);
        doThrow(new MailSendException("SMTP unavailable"))
                .when(mailSender).send(any(MimeMessage.class));

        CompletableFuture<MailSubmission> future =
                asyncMailService.submit(sampleCommand());

        ExecutionException exception = assertThrows(
                ExecutionException.class,
                () -> future.get(5, TimeUnit.SECONDS));

        assertThat(exception.getCause())
                .isInstanceOf(MailSendException.class);
    }
}
~~~

This is illustrative test code using JUnit 5, Mockito, AssertJ, and Spring Boot test support; add imports, test configuration, and `sampleCommand()` for your project. Depending on the Spring Boot version, the mock-bean annotation may use the corresponding API recommended by the framework. The goal is **obtaining the error from the Future through the real proxy**, not directly calling an instance created with `new`.

### 16.2. Testing Submission-Time Errors

An executor configured with a tiny queue and intentionally saturated can trigger `TaskRejectedException`. Tests should verify the caller catches the error and the system does not claim the job was accepted.

For deterministic tests, you can use a fake `Executor` that always rejects or a test `TaskExecutor` with deterministic rejection behavior, rather than relying on race conditions in a real thread pool.

### 16.3. Testing AsyncUncaughtExceptionHandler

For `@Async void` methods, tests should:

1. Call through the Spring proxy.
2. Have the method throw a controlled exception.
3. Verify the handler is invoked with the corresponding method and error type.
4. Confirm there is no assumption that the caller receives the exception directly.

Do not use fixed `Thread.sleep(...)` as proof the handler ran; use `CountDownLatch` or test synchronization utilities with appropriate timeouts.

### 16.4. Testing Outbox States and Crash Windows

For high-reliability flows, add cases covering:

| Scenario | Outcome to Verify |
| --- | --- |
| Worker sends successfully | Updates `SENT` after send |
| SMTP returns transient error | `RETRY`, `attemptCount`, and `nextAttemptAt` updated |
| Permanent data/template error | `FAILED`, no infinite retries |
| Executor rejects task | Work stays `PENDING` or is rescheduled |
| Worker dies while PROCESSING | Lease expires, row is reclaimed |
| SMTP succeeds, DB markSent fails | Duplicate-risk alert emitted, does not report definite send failure |
| Two workers poll simultaneously | Atomic claim prevents double claiming at once |
| Worker loses lease | Conditional update by owner/version does not overwrite |
| Request transaction rolls back | No committed outbox row created |

Repository/concurrency tests should run against a production-equivalent database (such as Testcontainers PostgreSQL when using `SKIP LOCKED`), because H2 or mock repositories may not fully reproduce locking semantics.

### 16.5. SMTP Sink in Integration Tests

Mailpit or MailHog can receive emails in test environments to inspect sent messages. For asynchronous systems, verify:

- Workers actually process the created jobs.
- HTML and plain text are rendered properly.
- Exceptions/results are reflected in outbox status.
- Attachments, if any, are not lost.
- Test emails are never sent to real customer addresses.

An SMTP sink does not prove the production provider will deliver emails successfully or avoid spam filtering. It tests the sending pipeline, not inbox delivery.

## 17. Sending Multiple Emails: Partial Failures and Aggregate Exceptions

When one job sends multiple messages, some messages may succeed while others fail. Returning a single boolean `success` for the entire batch makes it hard for the application to know which messages need retrying.

Example:

~~~text
Batch of 3 emails
├── delivery A -> SMTP accepted
├── delivery B -> SMTP rejected
└── delivery C -> SMTP accepted
~~~

Retrying the whole batch could send duplicates to recipients A and C. Thus, for transactional emails, consider **one delivery ID and one outbox record per recipient/message**.

`MailSendException` may provide details on failed messages depending on how sending is invoked and the transport implementation. Analyze at the message level when dispatching batches; do not assume all emails in a batch fail or succeed together.

### 17.1. CompletableFuture.allOf Does Not Replace Per-Email Status

Example:

~~~java
List<CompletableFuture<MailSubmission>> futures =
        commands.stream()
                .map(asyncMailService::submit)
                .toList();

CompletableFuture<Void> all = CompletableFuture.allOf(
        futures.toArray(new CompletableFuture[0]));
~~~

If one Future fails, `allOf` can complete exceptionally. Yet the aggregate result does not directly indicate which delivery succeeded or failed. Keep a mapping between `deliveryId` and each Future to update individual outcomes.

In addition, `stream().map(asyncMailService::submit)` can stop early if the executor rejects one call. For business batches, actively manage per-item submission and keep unaccepted items in `PENDING`.

### 17.2. Exceptions in Downstream Callbacks

Suppose:

~~~java
CompletableFuture<MailSubmission> f =
        asyncMailService.submit(command);

CompletableFuture<MailSubmission> tracked = f.whenComplete(
        (submission, error) -> stateRepository.updateState(
                command.deliveryId(), submission, error));
~~~

If SMTP succeeds yet `stateRepository.updateState` throws an exception, the dependent Future `tracked` may fail. Do not interpret that failure as “SMTP did not send”; the cause lies in persisting state.

Distinguish two outcomes:

- **Dispatch result**: did SMTP accept the message?
- **Persistence result**: was that status saved successfully?

A dispatcher/outbox worker with clear boundaries separates these two steps better than attaching an unmonitored callback to a Future.

## 18. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `try/catch` around async call thinking all errors are caught | Misses worker-thread exceptions | Observe Future or use handler for `void` |
| `@Async void` method only logs errors | No durable outcome for retries | Return Future for coordination, or persist outbox state |
| Calling `this.sendAsync()` in the same class | Bypasses proxy; method may run synchronously | Call through a Spring bean/proxy |
| Catching all `Exception` and returning success | Masks failures | Complete exceptionally or record error status |
| Using `exceptionally(ex -> null)` without persisting error | Failure vanishes in Future chain | Record outcome before deciding recovery |
| Calling `future.get()` directly inside HTTP request | Caller blocks | Use callbacks/events/outbox if waiting is unnecessary |
| `CompletableFuture.supplyAsync` without specifying executor | Runs on unconfigured common pool | Use Spring executor or named `@Async` |
| Unbounded queue | Memory/backlog grows endlessly when SMTP slows | Bounded queue, backpressure, or outbox |
| Retrying all errors immediately | Overloads SMTP and risks duplicates | Classify errors, backoff, jitter, max attempts |
| Assuming timeouts definitely mean unsent | Retries can produce duplicate emails | Check SMTP stage, support unknown status |
| `@Async` runs before transaction commits | May send emails for rolled-back data | `AFTER_COMMIT` or transactional outbox |
| Passing lazy JPA entities to workers | `LazyInitializationException`, stale data | Use DTOs/snapshots |
| Holding DB transaction while calling SMTP | Holds locks/connections too long | Separate claim, send, and state update |
| Marking `SENT` before sending | Process crash can lose emails | Send first then update with duplicate policy |
| Ignoring state-update conflicts | Old worker overwrites or loses history | Lease owner/version/fencing tokens |
| Sharing a `MimeMessage` across workers | Mixed content/recipients and race conditions | Create a fresh message per delivery |
| Logging raw params or exception messages | Leaks PII/tokens | Log IDs, error class, and normalized codes |
| Assuming HTTP 202 means SMTP accepted | Misleads users | Distinguish `QUEUED` and `SMTP_ACCEPTED` |

## 19. Choosing Architecture by Criticality

Not every email needs the same level of guarantee. Choose according to requirements:

| Level | Example | Exception-Handling Mechanism to Consider |
| --- | --- | --- |
| Best-effort | Auxiliary notices, no audit needed | `@Async CompletableFuture` + error observability/logging and backpressure |
| Session-level result needed | Admin task sending a one-off notice | Future + persisted send status, bounded retries |
| Critical transactional email | Invoices, transaction confirmations, security alerts | Transactional outbox + worker + retry/backoff + audit |
| High-volume sending | Bulk notifications to many recipients | Durable queue, per-delivery processing, rate limits, and provider monitoring |

**`@Async` is an asynchronous execution tool, not an email delivery guarantee.** When durability, at-least-once semantics, auditing, and post-restart retries are needed, use an outbox or message broker with proper acks/retries.

### 19.1. Recommended Flow for Transactional Emails

~~~text
Business service
  |
  | @Transactional
  +--> Save business state
  +--> Save mail outbox (PENDING)
  |
  v
COMMIT
  |
  v
Outbox polling worker / durable consumer
  |
  +--> Claim delivery atomically (PROCESSING + lease)
  |
  +--> Build MimeMessage
  |
  +--> JavaMailSender.send
  |       |
  |       +--> successful return: mark SENT
  |       |
  |       +--> exception: classify
  |                       |
  |                       +--> RETRY with nextAttemptAt
  |                       +--> FAILED
  |                       +--> UNKNOWN / reconciliation
  |
  v
Metrics, audit, alerts
~~~

If parallelizing multiple deliveries is needed, a bounded executor can be used on the worker side. Yet the source of truth remains the outbox record, not an in-memory `CompletableFuture`. After restarts, leases/retries resume processing rows not yet in terminal states.

## 20. Frequently Asked Questions

**“Why don't exceptions in @Async hit the catch block in the controller?”**  
Because the worker runs on another thread after the task was submitted. The controller can only catch synchronous submission errors (such as executor rejection); errors during worker execution must be received via a Future or handler.

**“When using @Async void, where do exceptions go?”**  
Uncaught exceptions are normally routed to `AsyncUncaughtExceptionHandler`. The caller has no Future to retrieve the exception. The handler should serve observability, not act as the sole durable retry mechanism.

**“How do CompletableFuture.failedFuture and throwing an exception differ?”**  
Both can complete the async result exceptionally when used appropriately. Inside an `@Async` method, you can throw a runtime exception for the Spring proxy to complete the Future exceptionally, or return an appropriate failed future. What matters is not turning a failure into a false success.

**“Why doesn't the caller get the result immediately when an @Async method returns completedFuture?”**  
The `completedFuture` value is constructed inside the method once it has run on the worker thread. The Spring proxy returns a Future representing the async execution; the caller receives the result after the worker finishes.

**“Should MailException be caught directly inside an @Async method?”**  
Not required if the Future is observed and the coordinating layer has an error-handling policy. Catch when you need to classify, add correlation, or update status; do not catch just to log and ignore.

**“Does TaskRejectedException mean SMTP sending failed?”**  
No. It usually means the executor did not accept the task. That is a submission/capacity error occurring before SMTP sending ever executes.

**“Should we retry immediately on MailSendException?”**  
Not by default. Analyze the cause and SMTP response. If the message may have been accepted prior to a timeout, retrying risks sending duplicates.

**“Does a CompletableFuture timeout cancel SMTP?”**  
Not guaranteed. The Future may report a timeout while the SMTP operation keeps running. Configure transport timeouts, leases, and an `UNKNOWN` status policy when outcomes are unclear.

**“Can @Transactional be used inside @Async?”**  
It can create a separate transaction on the worker via a Spring proxy, yet the caller's original transaction is not carried across threads. Avoid keeping transactions open while waiting on SMTP.

**“Is an AFTER_COMMIT listener reliable enough?”**  
It prevents sending before commit, yet does not create a durable queue. If the process dies after commit, events/tasks not written to an outbox can be lost.

**“Does an outbox guarantee no duplicate sends?”**  
Not completely. It supports at-least-once; if SMTP accepted the email but the worker died before recording `SENT`, a retry may produce a duplicate.

**“Should full exceptions be logged?”**  
Provide enough operational detail while controlling sensitive data. Use delivery IDs, error codes, and exception types, and configure logging to comply with security policies.

**“When should HTTP 202 be returned?”**  
When the application has accepted the request for subsequent processing per API contract. For high-reliability flows, persist a durable job before returning `QUEUED`. Never describe this status as having delivered the email to the inbox.

## 21. Key Takeaways for Exception Handling in Asynchronous Tasks

Mental model:

~~~text
Call @Async method
       |
       +--> Rejected immediately?
       |       |
       |       +--> TaskRejectedException: handle in caller
       |
       +--> Executor accepts task
               |
               +--> MIME/template error
               |       |
               |       +--> Future exceptionally / FAILED
               |
               +--> SMTP send error
               |       |
               |       +--> Classify RETRYABLE / PERMANENT / UNKNOWN
               |       +--> Persist result, backoff, retry limit
               |
               +--> SMTP send succeeds
                       |
                       +--> Record SMTP_ACCEPTED/SENT
                       +--> Handle if state update fails
~~~

When using Spring Framework Mail:

1. Identify whether exceptions occur at the **caller on submission** or at the **worker on execution**.
2. For `@Async void`, configure `AsyncUncaughtExceptionHandler`; for `Future/CompletableFuture`, always observe completion.
3. Distinguish MIME building, SMTP auth, transport, executor, and database state-update errors.
4. Retry with caps, backoff, and ambiguous-outcome policies; never retry infinitely.
5. Configure reasonable SMTP timeouts, executor capacity, and shutdown behavior.
6. Pass explicit DTOs/snapshots, correlation IDs, and locales across thread boundaries.
7. For transactional emails, persist an outbox row in the business transaction and update `SENT/RETRY/FAILED` in a separate transaction with owner/version conditions.
8. Never confuse “SMTP accepted” with “reached inbox”, and never claim exactly-once delivery based solely on `@Async` or an outbox.

**Conclusion:** Handling exceptions in asynchronous mail sending is more than adding `try/catch`. You must design result channels, error classification, retry limits, sensitive-data protection, and durable progress persistence when business logic requires it. Clarifying these boundaries keeps the application from silently dropping errors, reporting false successes, and enables controlled recovery when SMTP or workers fail.
