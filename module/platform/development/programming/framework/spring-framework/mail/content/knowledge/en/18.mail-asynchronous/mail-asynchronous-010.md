# Dedicated Executor for Mail and Other Tasks

## 1. The Problem When All Asynchronous Tasks Share One Executor

In **Spring Framework Mail**, sending email via `JavaMailSender` is typically a **thread-blocking I/O operation**. Even when the SMTP server operates normally, every send must establish or reuse a connection, exchange SMTP commands, transfer data, and wait for a response. If the server responds slowly, the mail-sending thread is held for that duration.

A Spring application can also run other work: generating PDF reports, exporting Excel files, updating search indexes, processing images, sending webhooks, syncing data, or running background jobs. If all tasks share one thread pool, they compete for threads and queue capacity:

~~~text
REST request ─────┐
Order event ──────┤      One shared executor
Report request ───┼────► [mail][mail][report][mail][image][mail]...
Image task ───────┤               |
Webhook task ─────┘         Finite worker count
                                  |
                         Tasks wait on each other
~~~

Suppose the SMTP provider responds slowly for several minutes. Many concurrent mail tasks can occupy all workers, forcing report-generation tasks to wait even though reports have nothing to do with SMTP. Conversely, a CPU-heavy report burst can saturate the pool and delay notification emails by minutes.

**The solution is creating separate executors for workload groups with different characteristics and priorities**, for example:

- `mailTaskExecutor` for email sending.
- `reportTaskExecutor` for report generation tasks.
- `integrationTaskExecutor` for sync or webhooks when independent limits are needed.

Separating executors is a form of **bulkhead isolation**: when one group of tasks slows down or saturates, it does not directly exhaust every thread and queue slot of other groups. This limits blast radius across task types within the same application.

## 2. What Does a Dedicated Executor Solve, and What Does It Not?

A Java `Executor` provides a mechanism to accept work and run it on threads it manages. Spring's `ThreadPoolTaskExecutor` adds pool configuration, queues, thread naming, and integration with `@Async` infrastructure.

| Goal | Does a separate executor help? | Limitation |
|---|---|---|
| Slow mail does not take all report threads | Yes | Both pools still share the process's CPU, RAM, and network |
| Limit concurrent mail sends | Yes | Does not automatically cap emails/second to provider quota |
| Cap waiting tasks | Yes, when bounded queue is set | Must handle full-queue rejections |
| Name threads for observability | Yes | Still needs logs/metrics to operate |
| Send SMTP without holding request threads | Possibly, when dispatch is truly async | Submissions can still be rejected; processing cost still exists |
| Guarantee emails are not lost on app restart | No | Tasks in RAM queues can be lost |
| Guarantee exactly-once delivery | No | SMTP acceptance and crashes can cause duplicates |
| Propagate transactions or SecurityContext to new threads | Not automatically | Requires explicit boundary design and context propagation |

Common pitfall: **an executor only manages execution resources inside the process**, not a durable queue. If email send requests must survive process kills, a durable job store such as a transactional outbox or message broker is needed, after which an executor can process claimed jobs.

## 3. Mail Workload Characteristics Differ from Reports and Other Tasks

Do not give every type of work the same thread count and queue size. Look at which resource constrains each task:

| Workload | Typical Characteristics | Primary Constraint |
|---|---|---|
| SMTP sending | Waits on network, provider, and timeouts | SMTP concurrency, connections, provider quota |
| Simple template rendering | Light CPU, short duration | CPU/memory, rarely needs a separate pool |
| Large PDF rendering | Can be CPU- and memory-heavy | CPU cores, heap, file I/O |
| Image compression/resizing | Usually CPU- and memory-heavy | CPU cores, image size |
| Partner API calls | Network I/O can be slow | Timeouts, rate limits, connection count |
| Reading or writing large files | Disk or object storage I/O | Bandwidth, file descriptors, memory |
| Updating search indexes | I/O and batch/network | Downstream throughput |

For example, a pool for SMTP may need more threads than CPU cores because many threads sit waiting on the network. By contrast, a pool running heavy computation should usually not raise thread counts arbitrarily because too many runnable threads cause CPU and heap contention.

**A dedicated executor does not mean every task type needs its own pool.** Split based on significant differences in runtime, priority, SLA, retry behavior, and saturation risk. Creating dozens of unbounded tiny pools can also exhaust process resources.

## 4. Recommended Architecture in Spring

A foundational design:

~~~mermaid
flowchart TB
    API[REST / Application service] --> MAIL[Mail async gateway]
    API --> REPORT[Report async service]
    MAIL --> ME[mailTaskExecutor]
    REPORT --> RE[reportTaskExecutor]
    ME --> MS[Mail sender adapter]
    MS --> SMTP[SMTP server]
    RE --> PDF[PDF/CSV generator]
    SMTP -.-> LIMIT[Provider latency / quota]
    PDF -.-> CPU[CPU / memory]
~~~

Meaning:

1. The application service creates an explicit mail send request containing the data to send.
2. The mail async gateway is dispatched by Spring to the mail executor.
3. The report service is dispatched to the report executor, without sharing a queue with mail.
4. Each executor has its own concurrency, queue, and rejection policies.
5. HTTP- and business-related tasks must still handle exceptions, overload, and transactions appropriately.

Splitting pools **separates execution capacity** without requiring splitting the system into multiple microservices. One Spring Boot process can host multiple named executors.

## 5. Declaring Two ThreadPoolTaskExecutors with Java Configuration

An example for Spring Boot using Java 17+ and Spring Framework 6:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncExecutorConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }

    @Bean(name = "reportTaskExecutor")
    public ThreadPoolTaskExecutor reportTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(40);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
~~~

The numbers **4/8/200** and **2/4/40** are illustrative configurations, not optimal settings for every system. Actual sizes must be determined from SMTP processing times, quotas, traffic, RAM, CPU, and acceptable latency.

### Role of Each Parameter

| Parameter | Role |
|---|---|
| `corePoolSize` | Baseline threads maintained by the pool under normal policy |
| `maxPoolSize` | Maximum thread limit in the pool |
| `queueCapacity` | Maximum tasks waiting in the executor's queue |
| `keepAliveSeconds` | Duration threads above core count stay alive when idle |
| `threadNamePrefix` | Thread name prefix to distinguish logs and thread dumps |
| `RejectedExecutionHandler` | Policy when the pool cannot accept a task |
| `waitForTasksToCompleteOnShutdown` | Controls waiting for queued/active tasks during shutdown |
| `awaitTerminationSeconds` | Maximum lifecycle wait time for executor termination |

Bean names `mailTaskExecutor` and `reportTaskExecutor` are key so methods using `@Async("...")` pick the right executor. Never rename a bean and forget to update qualifiers at usage sites.

### How Spring Uses Core, Queue, and Max

With `ThreadPoolTaskExecutor` backed by `ThreadPoolExecutor`, when `queueCapacity > 0`, a typical execution flow is:

1. If workers are fewer than core size, create a worker to run the task.
2. When all core threads are busy, new tasks are added to the queue.
3. Once the queue is full, the pool can grow workers up to max size.
4. When the queue is full and workers reach max, new tasks are handled by the rejection policy.

Therefore, **`maxPoolSize` does not mean the pool immediately uses maximum threads when busy**. With a large queue, many tasks wait before the pool expands from core to max.

If the queue is unbounded, the pool may keep queuing with little or no expansion past core size. Thus do not merely set `maxPoolSize` and assume the pool will scale to max. Choose queue capacity and concurrency together.

## 6. Specifying the Executor Explicitly with @Async

Spring uses `@EnableAsync` to enable processing `@Async` calls via proxies or corresponding AOP mechanisms. Attach the executor name directly to the method:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportAsyncService {
    private final ReportGenerator reportGenerator;

    public ReportAsyncService(ReportGenerator reportGenerator) {
        this.reportGenerator = reportGenerator;
    }

    @Async("reportTaskExecutor")
    public CompletableFuture<ReportResult> generate(
            ReportRequest request) {
        ReportResult result = reportGenerator.create(request);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

For the mail service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MailAsyncGateway {
    private final MailSubmissionService submissionService;

    public MailAsyncGateway(
            MailSubmissionService submissionService) {
        this.submissionService = submissionService;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<MailSubmissionResult> submit(
            MailCommand command) {
        MailSubmissionResult result =
                submissionService.submitToSmtp(command);
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Here `MailCommand`, `MailSubmissionResult`, `MailSubmissionService`, `ReportRequest`, and `ReportGenerator` are application-defined types. `submitToSmtp` executes the logic to build and send the message with `JavaMailSender` on a mail executor thread.

Application calling the gateway:

~~~java
CompletableFuture<MailSubmissionResult> future =
        mailAsyncGateway.submit(command);

// Call has handed the task to the executor; SMTP result arrives later.
// Only join/get if the caller genuinely wants to wait and handle the result.
~~~

**Do not leave an unqualified `@Async` to accidentally use a default executor when the application has multiple workloads.** Naming the executor right in the annotation makes resource boundaries clear and makes code easier to inspect.

### @Async Does Not Change the Nature of SMTP Sending

`JavaMailSender.send(...)` on a mail executor thread remains a blocking I/O operation. `@Async` only moves that work off the calling thread onto an executor; it does not turn SMTP into non-blocking I/O and does not automatically add retries, idempotency, or a durable queue.

## 7. Example Mail Submission Service Separated from the Async Gateway

A synchronous SMTP-sending service can be invoked from the mail executor:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MailSubmissionService {
    private final JavaMailSender mailSender;

    public MailSubmissionService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MailSubmissionResult submitToSmtp(
            MailCommand command) {
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    false,
                    StandardCharsets.UTF_8.name());
            helper.setFrom("notifications@example.test");
            helper.setTo(command.recipient());
            helper.setSubject(command.subject());
            helper.setText(command.html(), true);

            mailSender.send(message);
            return new MailSubmissionResult(command.id(), "SUBMITTED");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot compose MIME mail", ex);
        }
    }
}

public record MailCommand(
        String id,
        String recipient,
        String subject,
        String html) {
}

public record MailSubmissionResult(
        String id,
        String status) {
}
~~~

This is a class-design illustration, not a single copy-pasteable source file since Java normally requires separate files for top-level public types. `MailCommand` should be an immutable DTO; class names can vary per application.

`mailSender.send(message)` can throw Spring Mail exceptions such as `MailException` (unchecked). In this example, they are not swallowed and instead propagate out to the gateway's `CompletableFuture`. Message-building errors via `MessagingException` are distinguished from SMTP submission errors.

**Status `SUBMITTED` should only mean the SMTP server accepted the send request**, not that the recipient received it in their Inbox or opened the email.

## 8. Bounded Queues and Overload Protection

Splitting pools does not give the system infinite processing capacity. If emails are generated faster than send speed over a sustained period, the mail executor's queue will grow. With an unbounded queue, the process can retain ever more tasks on the heap, increasing latency and eventually causing memory issues.

Example:

~~~text
New incoming rate:    15 emails/sec
Actual SMTP capacity:  5 emails/sec
Difference:           10 emails/sec

After 60 seconds, the queue can grow by ~600 tasks
if there is no bound and traffic does not change.
~~~

This is merely an illustrative calculation assuming steady throughput, not a measurement from a specific SMTP provider.

Therefore, you should:

- Set a bounded `queueCapacity` for executors processing directly in memory.
- Cap thread count/concurrency so you do not overload the SMTP provider.
- Set timeouts so a single task cannot hold a worker forever.
- Have an explicit full-queue handling policy instead of accepting forever.
- Measure time spent in the queue and rejected task counts.
- For critical emails, persist intent durably in an outbox/broker before handing off to an executor.

### Executor Saturation

With configuration `core=4, max=8, queueCapacity=200`:

~~~text
Tasks arrive continuously
        |
        v
Up to 4 core workers
        |
        v
Up to 200 tasks in queue
        |
        v
Pool can expand up to 8 workers
        |
        v
Pool and queue are both full
        |
        v
New tasks rejected per rejection policy
~~~

A rejected task does not mean SMTP tried sending and failed. It means **the executor never accepted the work**. If the caller ignores this event, the email can be completely lost with no SMTP error to investigate.

## 9. Rejection Policy: Explicitly Choosing Behavior When the Pool Is Full

Java's `ThreadPoolExecutor` provides common rejection handlers:

| Handler | When Executor Is Saturated | Consequence for Mail |
|---|---|---|
| `AbortPolicy` | Throws an exception | Caller knows the task was not accepted and can record status/route to outbox |
| `CallerRunsPolicy` | Runs task directly on the calling thread (if executor not shut down) | Request threads or transaction threads may be blocked by SMTP |
| `DiscardPolicy` | Silently drops the task | Unsuitable when you need to know which emails were not sent |
| `DiscardOldestPolicy` | Drops the oldest task in the queue and retries accepting the new one | Can lose a waiting email |

For business-critical emails, `AbortPolicy` is usually easier to control because acceptance failures are reported explicitly. In Spring, rejected submissions can surface as `TaskRejectedException`.

~~~java
import org.springframework.core.task.TaskRejectedException;

try {
    mailAsyncGateway.submit(command);
} catch (TaskRejectedException ex) {
    // Executor did not accept the task.
    // Report a controlled error or ensure intent remains
    // in outbox / durable queue for retry.
    throw ex;
}
~~~

Do not treat `TaskRejectedException` as an SMTP error. If the request has not been durably saved, deciding whether to return an error or persist the request depends on the API contract. With an outbox, a full executor should simply leave the job **in pending state**, never losing the committed record.

### Why Can CallerRunsPolicy Be Dangerous?

Suppose a controller calls `mailAsyncGateway.submit(...)` on a request thread. When the pool runs out of space, `CallerRunsPolicy` can execute the SMTP send directly on the request thread. As a result:

- HTTP requests suddenly slow down by several seconds.
- Web-handling threads are exhausted during peak hours.
- If the caller is inside a transaction, SMTP can occur before commit.
- Original SLAs and bulkhead isolation are broken.

`CallerRunsPolicy` can be helpful for certain workloads needing synchronous backpressure, yet **should not be chosen mechanically for SMTP sending**. For mail, design intentional overload behavior and monitor rejections.

### Never Ignore Failed Futures

An `@Async` method returning `CompletableFuture` can complete in a failed state. A caller that ignores the future and only logs “queued” will miss subsequent SMTP errors.

~~~java
mailAsyncGateway.submit(command)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Record metric and correlation ID.
                // Do not log entire email content.
                return;
            }
            // Record successful SMTP submission.
        });
~~~

This callback serves observability and result handling; **it does not replace persistent state** when retries across restarts are needed. If the callback runs in memory and the process dies, the callback itself is lost.

## 10. Sizing the Mail Executor by I/O Time and Throughput

There is no single core/max configuration that fits every system. One initial estimation approach uses:

- `λ`: average incoming emails per second.
- `W`: time a task holds a worker, in seconds.
- `L`: average concurrent tasks required.

By the approximate relationship of **Little's Law** in a steady system:

\[
L \approx \lambda \times W
\]

For example, if an application needs to handle an average of 6 emails/second and average SMTP submission time is 2 seconds:

\[
L \approx 6 \times 2 = 12
\]

The result suggests around 12 concurrent tasks in flight under ideal conditions. This **is not an automatic formula for `maxPoolSize`** because you must also factor in:

- How many concurrent connections the SMTP provider allows.
- Rate limits per minute or per day.
- P95/p99 latency, not just averages.
- Ability to establish and reuse SMTP connections.
- Sizes of each email and attachment.
- Instance CPU, memory, and network egress.
- Replica count and cluster-wide total concurrency.

For example, if an SMTP provider permits only 5 concurrent submissions, setting 20 workers on a single instance can produce more throttling errors rather than sending emails faster.

### A Dedicated Pool Is Not a Rate Limiter

Limiting threads only caps **how many tasks run concurrently**, not a maximum of N emails/second. If each SMTP call is very fast, a single thread can send many emails in one second. When providers enforce time-window quotas, add a **rate limiter** in the mail dispatcher or provider adapter.

~~~text
Mail queue
    |
    v
Rate limiter (allowed rate)
    |
    v
Mail executor (allowed concurrency)
    |
    v
JavaMailSender / SMTP provider
~~~

If there are 4 replicas and each uses 8 mail threads, the cluster can concurrently run up to 32 SMTP tasks. Local per-replica rate limiters do not automatically enforce cluster-wide caps; when sharing a global quota, coordinate by provider/account or use an appropriate work-distribution mechanism.

### Queue Capacity Should Align with Allowed Wait Latency

If a system steadily processes 4 emails/second and the queue holds 200 tasks, a new task at the tail may wait tens of seconds before processing, depending on concurrency and per-task time. Large queues reduce momentary rejections yet raise latency without increasing real sending capacity.

Define a target: “how quickly should a notification email begin processing?” and then measure **queue wait time**, rather than picking `queueSize` by guesswork.

## 11. SMTP Timeouts Are Part of Executor Design

If an SMTP connection or transfer operation hangs without reasonable timeouts, workers can remain blocked indefinitely. In Spring Boot, Jakarta Mail timeouts can be configured as:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

Timeout values are in milliseconds and illustrative only. `connectiontimeout` caps connection setup wait, `timeout` caps read operations, and `writetimeout` covers write operations. Choose them according to network conditions, provider behavior, and job time limits.

Timeouts do not turn SMTP into exactly-once. If the connection drops after the client sends the message body but before receiving the final reply, whether the server accepted the email may be ambiguous. Workers need appropriate status tracking and retry policies rather than assuming every timeout is safe to resend.

**Never use a huge mail executor to mask missing timeouts.** When the provider has an outage, more threads just leave more threads hung.

## 12. Two Levels of Backpressure: Before and After Accepting Work

Distinguish:

1. **Admission control:** how many new tasks the executor or system accepts.
2. **Dispatch control:** how many messages workers send concurrently or over time.

If tasks are not yet durably saved, admission failures must be returned to the caller or handled by business logic. With an outbox, request acceptance can finish once the outbox record commits, while the dispatcher pulls only as many jobs as the executor has capacity to process:

~~~text
HTTP request
     |
     v
DB transaction: business data + mail outbox
     |
     v
COMMIT succeeds
     |
     v
Outbox records (durable)
     |
     v
Poll/claim based on free capacity
     |
     v
mailTaskExecutor
     |
     v
SMTP submission
~~~

**Do not claim thousands of records and push them into an executor queue with only a few hundred slots.** If a task is rejected after claiming, return the record to pending/due state or let its lease expire per design. A better approach is having the dispatcher calculate available processing slots first, then claim a matching batch.

When both the outbox backlog and SMTP slow down, the system still records send intents in the database (within storage capacity), while workers avoid blowing up the process with unbounded tasks in RAM.

## 13. Conditions for @Async to Actually Run on the Chosen Executor

`@Async` is normally applied by Spring via a proxy. Therefore pay attention to **how methods are called**, not only where the annotation sits.

### Calling Through a Spring-Managed Bean

Correct example:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationFacade {
    private final MailAsyncGateway mailAsyncGateway;

    public OrderNotificationFacade(
            MailAsyncGateway mailAsyncGateway) {
        this.mailAsyncGateway = mailAsyncGateway;
    }

    public void requestWelcomeEmail(MailCommand command) {
        mailAsyncGateway.submit(command);
    }
}
~~~

`OrderNotificationFacade` calls a separate bean, `MailAsyncGateway`, so the call passes through Spring's proxy and is dispatched to `@Async("mailTaskExecutor")`.

**Incorrect** example:

~~~java
@Service
public class WrongMailService {

    public void execute(MailCommand command) {
        sendAsync(command); // self-invocation
    }

    @Async("mailTaskExecutor")
    public void sendAsync(MailCommand command) {
        // May still run directly on caller thread.
    }
}
~~~

In default proxy mode, internal calls within the same object bypass the proxy so the annotation may have no effect. Move the async method to another Spring bean and invoke it through that bean.

### Other Traps

- Do not assume `@Async` on a `private` method will be intercepted by Spring in proxy mode.
- Do not invoke async methods via `new MailAsyncGateway(...)` expecting Spring to inject executors automatically.
- Do not rely on calls inside a constructor assuming AOP proxies are already initialized.
- Do not omit executor qualifiers on `@Async` in apps with multiple executor beans and expect it to pick the right pool automatically.
- Do not pass mutable objects that the caller keeps mutating after submission; mail threads can read them at a different time.
- Do not call `join()` immediately inside an HTTP request if the goal is freeing the request thread; awaiting the future can keep the request blocked.

### Using Executor Directly Instead of @Async

Not every use case needs annotations. You can inject the right executor by qualifier and dispatch explicitly:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Component;

@Component
public class MailTaskDispatcher {
    private final TaskExecutor mailExecutor;
    private final MailSubmissionService submissionService;

    public MailTaskDispatcher(
            @Qualifier("mailTaskExecutor") TaskExecutor mailExecutor,
            MailSubmissionService submissionService) {
        this.mailExecutor = mailExecutor;
        this.submissionService = submissionService;
    }

    public void dispatch(MailCommand command) {
        mailExecutor.execute(
                () -> submissionService.submitToSmtp(command));
    }
}
~~~

This is useful when coordinating batches, claiming outbox rows, or catching submission errors directly. However, when using `execute(Runnable)`, exceptions occurring **after the task starts running** do not return to the caller like synchronous throws. Tasks must have their own error-handling/state-recording mechanism.

## 14. Transaction Boundaries: Do Not Let Async Mail Run Before Commit

A common mistake is calling `@Async` directly inside an `@Transactional` method:

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailAsyncGateway.submit(buildMailCommand(order));
}
~~~

Submission can place the task into the mail executor **before the database transaction commits**. The mail thread may send notifications while data is still uncommitted; if the transaction later rolls back, the recipient receives a confirmation email for a non-existent order.

Additionally, the caller thread's transaction **does not automatically propagate to executor threads**. `@Transactional` uses thread-bound context or corresponding transaction mechanisms. Do not assume mail workers can read the caller's uncommitted data or share its persistence context.

### Option A: Post-Commit Events for Best-Effort Mail

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCommittedMailListener {
    private final MailSubmissionService mailService;

    public OrderCommittedMailListener(
            MailSubmissionService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCommitted(OrderCommitted event) {
        mailService.submitToSmtp(event.mailCommand());
    }
}
~~~

The application service publishes an event while inside the transaction:

~~~java
@Transactional
public UUID placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    eventPublisher.publishEvent(
            new OrderCommitted(buildImmutableMailCommand(order)));
    return order.getId();
}
~~~

The `AFTER_COMMIT` handler triggers after the transaction commits; `@Async` hands execution off to the mail executor. This prevents sending before commit, yet events live only in process memory: the app can crash right after commit, tasks can be rejected, or tasks can be lost on restart. Thus it suits **best-effort**, not durable guarantees.

### Option B: Transactional Outbox for Mail Requiring Durability

~~~text
@Transactional application service
    |
    +--> save order
    |
    +--> insert mail_outbox record
    |
    v
COMMIT
    |
    v
Outbox poller / queue consumer
    |
    v
mailTaskExecutor (concurrency bounded)
    |
    v
JavaMailSender.send
    |
    v
Update outbox state
~~~

In this architecture, **the executor remains useful** for bounding SMTP concurrency, while **the outbox** is what preserves send requests across restarts.

The outbox dispatcher must not claim more jobs than remaining execution capacity. Separate claim transactions from SMTP calls, using leases, timeouts, and explicit state transitions. If the pool rejects a task, keep the job in a retryable state rather than treating it as an SMTP submission failure.

### Do Not Use @Async to “Open” Another Transaction Without Clear Intent

When an `@Async` method carries `@Transactional`, its transaction can start on the worker thread via a Spring proxy. That **does not make it join the caller's transaction**. If an outbox write must be atomic with an order, insert into the outbox inside the original business transaction rather than offloading the insert to an async thread.

## 15. Exception Handling Differs for void and CompletableFuture

An async method can return `void`, `Future`, or `CompletableFuture`. Exception handling differs:

### CompletableFuture

~~~java
CompletableFuture<MailSubmissionResult> submitted =
        mailAsyncGateway.submit(command);

submitted.whenComplete((result, error) -> {
    if (error != null) {
        metrics.recordMailSubmissionFailure();
        return;
    }
    metrics.recordMailSubmissionSuccess();
});
~~~

If the SMTP call fails on the worker, the future can complete exceptionally for the caller to handle. Having a future alone does not mean durable retries; if the process dies, the future dies with it.

### Methods Returning void

~~~java
@Async("mailTaskExecutor")
public void submitWithoutResult(MailCommand command) {
    submissionService.submitToSmtp(command);
}
~~~

The caller receives no future to observe errors. With Spring `@Async`, uncaught exceptions in `void` async methods can be routed to `AsyncUncaughtExceptionHandler`.

You can configure the handler:

~~~java
import java.lang.reflect.Method;
import java.util.concurrent.Executor;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler
    getAsyncUncaughtExceptionHandler() {
        return (throwable, method, params) -> {
            // Record metric, error type, and safe identifier.
            // Do not automatically log full params: may contain PII.
        };
    }
}
~~~

The illustrative handler above does not re-invoke the task. In practice, emit useful logs/metrics; for durable tasks, retry state must be managed via an outbox or job store.

For critical transactions, an explicit return-value contract and state-managed pipeline are usually easier to control than “fire-and-forget” `void @Async`. If choosing `void`, actively design the failure path.

## 16. Context Propagation: MDC, SecurityContext, Locale

Because mail tasks run on another thread, information bound to the calling thread **does not automatically travel with the task**. Examples:

- MDC containing request IDs or correlation IDs.
- Spring SecurityContext containing authentication info.
- LocaleContext or tenant context.
- TransactionSynchronizationManager and persistence context.

Do not rely on HTTP request `ThreadLocal` values when rendering/sending emails on worker threads. The most durable approach is placing required values into an **immutable MailCommand**: recipient, locale, tenant ID, event ID, template ID, and permitted content data.

### TaskDecorator to Propagate MDC for Logging

If the system needs correlation IDs preserved across the executor, use `TaskDecorator`:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcCopyingTaskDecorator
        implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                delegate.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Attach the decorator to the executor before `initialize()`:

~~~java
executor.setTaskDecorator(new MdcCopyingTaskDecorator());
~~~

This copies MDC at submit time, installs it on the worker, and **restores prior state** in `finally`. Restoring is especially important because thread pools reuse threads, preventing a prior task's correlation ID from leaking into the next task.

If security context propagation is needed, consider executor wrappers supporting Spring Security's `DelegatingSecurityContextAsyncTaskExecutor`. However, **do not mechanically propagate full user permissions to background tasks**. Workers should use least-privilege service permissions and verify tenant/authorization at business boundaries. Transaction contexts must not be copied to new threads.

### Tenant and Locale Considerations

In multi-tenant applications, explicitly record tenant ID and locale in the request/outbox payload. Do not depend on request ThreadLocal variables when jobs run minutes later. Workers load the right tenant, template, and sender configuration, and use an explicit `Locale` rather than whatever arbitrary default locale the worker thread has.

## 17. Observing Each Executor Independently

A major benefit of splitting pools is knowing exactly which workload is generating load:

~~~text
mailTaskExecutor
    activeThreads = 8
    poolSize      = 8
    queuedTasks   = 200
    rejectedTasks rising

reportTaskExecutor
    activeThreads = 1
    poolSize      = 2
    queuedTasks   = 0
~~~

In this example, the mail pool is near or at saturation while the report pool still has execution headroom. If only one shared pool existed, dashboards could hardly tell whether mail or reports caused the latency.

### Metrics to Monitor

| Metric | Meaning | Alert Suggestion |
|---|---|---|
| Active threads | Busy workers | Continuously near max pool |
| Pool size | Total created workers | Pool constantly expanding to max |
| Queue size | Waiting tasks | Large and steadily growing queue |
| Queue wait duration | Time from submit to start | p95/p99 exceeds SLA |
| Task execution duration | Time a task holds a thread | Rising SMTP latency |
| Rejection count | Tasks not accepted | Spiking or sustained |
| Submission success/failure | Send outcome | Rising failures per provider |
| SMTP timeout count | Timeout occurrences | Spike after network/provider issues |
| Outbox backlog age | Age of durable waiting jobs | Workers falling behind |

`ThreadPoolTaskExecutor` exposes several runtime values for observation. Example:

~~~java
ThreadPoolTaskExecutor mailExecutor = ...;

int active = mailExecutor.getActiveCount();
int poolSize = mailExecutor.getPoolSize();
int queued = mailExecutor.getThreadPoolExecutor()
        .getQueue()
        .size();
~~~

This is in-code observation; actual metric export can use Micrometer/Actuator or whatever monitoring stack the application uses. Use tags like `executor=mail` and `executor=report`. Avoid tagging by recipient or subject due to high cardinality and data exposure.

### Queue Size Is Not the Entire Backlog

In systems using an outbox, **actual backlog** includes records waiting in the database plus tasks claimed/submitted into the executor. Seeing a queue size of 0 does not prove no emails are waiting: workers might be dead, not polling, or paused.

Observe all of:

~~~text
outbox_pending / outbox_retry
    +
executor_queue
    +
executor_active
    +
smtp_inflight
~~~

Components may overlap depending on claim state and measurement model, so **do not blindly sum metrics and treat the total as unique emails**. Align metric definitions and status lifecycles to avoid double counting.

## 18. Graceful Shutdown Does Not Replace Durable Storage

When the application receives a shutdown signal, Spring can stop executors from accepting new tasks and wait for running tasks or process queued ones according to lifecycle settings.

Two commonly used settings:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Meaning:

- Attempts to let tasks already accepted by the executor finish per shutdown policy.
- Waits at most a configured duration while Spring closes the application context.

**These settings do not guarantee task completion if the process is killed, the host loses power, or the container is force-stopped.** Mail send requests held solely in RAM can be lost. Furthermore, executor wait time must fit within the orchestrator or container runtime's grace period.

With an outbox:

1. Stop claiming new jobs when the application begins shutting down.
2. Let in-flight sends finish within a reasonable grace period.
3. Update database state when results arrive.
4. Incomplete records will be reclaimed by another worker or a new process once leases expire.

If SMTP accepted a message yet the state update did not commit in time, retries can create duplicate emails. Graceful shutdown reduces probability without completely eliminating the crash window.

### Do Not Use Daemon Threads to “Avoid Waiting”

Setting worker threads as daemon threads only lets the JVM exit without waiting for them to finish; that is unsuitable for critical email requests. Manage lifecycles, timeouts, and job persistence properly rather than abandoning task completion.

## 19. Testing Separated Mail and Report Executors

Testing should isolate three goals:

1. **Dispatch to the right executor**: mail runs on threads prefixed with `mail`, reports run on threads prefixed with `report`.
2. **No shared-queue contention**: while the mail pool is busy, reports can still accept tasks in their own pool, provided the process still has resources.
3. **Overload behavior**: a full queue leads to handled rejections without silently losing jobs.

### Testing That @Async Selects the Right Executor

Use Spring Test with a minimal probe:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        AsyncExecutorConfiguration.class,
        AsyncDispatchTest.TestBeans.class
})
class AsyncDispatchTest {
    @Autowired
    private Probe probe;

    @Test
    void runsMailAndReportOnDifferentExecutors() {
        String mailThread = probe.mailThread().join();
        String reportThread = probe.reportThread().join();

        assertThat(mailThread).startsWith("mail-");
        assertThat(reportThread).startsWith("report-");
    }

    @Configuration
    static class TestBeans {
        @Bean
        Probe probe() {
            return new Probe();
        }
    }

    static class Probe {
        @Async("mailTaskExecutor")
        public CompletableFuture<String> mailThread() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }

        @Async("reportTaskExecutor")
        public CompletableFuture<String> reportThread() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }
}
~~~

Tests must run in a Spring context with `@EnableAsync`; here the annotation resides in `AsyncExecutorConfiguration`. Do not call `new Probe()` directly in tests because doing so bypasses proxies. Thread prefixes are easy-to-read signals, though if the application customizes naming, update assertions to match configuration.

### Testing Rejection of an Isolated Executor

Build a small executor with one worker and zero queue slots:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorOverloadTest {
    @Test
    void rejectsWhenSingleWorkerIsBusy() throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(0);
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.initialize();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();

            assertThatThrownBy(() -> pool.execute(() -> {
                // Executor is full: this task is rejected.
            })).isInstanceOf(TaskRejectedException.class);
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
~~~

This test illustrates pool overload behavior **without contacting SMTP**. In real tests, put timeouts on latches so tests never hang forever if a worker fails to run. To verify two executors do not interfere, block a mail task on a latch while submitting a report task to the report pool, then assert the report completes within expected bounds.

### Testing SMTP Send Failures

A mail gateway test can mock `MailSubmissionService` to throw `MailSendException` and assert the `CompletableFuture` completes exceptionally. Verifying mock calls only proves wiring and error propagation, **not real SMTP transactions**. To test the protocol, use an SMTP test server with appropriate local/test configuration.

### Testing Transaction Boundaries

An important test rolls back a transaction after creating an event/send request and confirms no mail is submitted. With an outbox, confirm both business data and the outbox record roll back together. This is a database/transaction-layer integration test; mocking repositories alone is insufficient.

## 20. Configuring via Properties Instead of Hardcoding

When operating multiple environments, place executor parameters in application-specific configuration:

~~~yaml
app:
  async:
    mail:
      core-size: 4
      max-size: 8
      queue-capacity: 200
      shutdown-wait-seconds: 30
    report:
      core-size: 2
      max-size: 4
      queue-capacity: 40
      shutdown-wait-seconds: 30
~~~

This is a **custom-defined configuration namespace**, not properties Spring Boot automatically binds to those two executors just from having the `app.async` prefix. Use `@ConfigurationProperties` or an equivalent binding mechanism to read values and configure the beans.

Example binding with a record in Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.async.mail")
public record MailExecutorProperties(
        int coreSize,
        int maxSize,
        int queueCapacity,
        int shutdownWaitSeconds) {
}
~~~

Then register `@EnableConfigurationProperties(MailExecutorProperties.class)` or configure scanning accordingly and inject properties into the bean factory. Validate that:

- `coreSize` is positive.
- `maxSize >= coreSize`.
- `queueCapacity >= 0`.
- Shutdown wait is non-negative.
- Aggregate concurrency across replicas does not exceed downstream/provider capacity.

Never allow production configs to accidentally set massive queue capacities or excessive `maxPoolSize` without matching memory and connection bounds.

## 21. Separating the Scheduler from the SMTP-Sending Executor

In systems with an outbox, a scheduler typically wakes the dispatcher to fetch jobs from the database:

~~~java
@Scheduled(fixedDelay = 1000)
public void pollMailOutbox() {
    dispatcher.claimAndDispatchReadyMails();
}
~~~

The scheduler **does not have to be the SMTP-sending worker**. It should do brief work: check free capacity, claim a matching number of records, and hand them to the mail executor. If the scheduler sends many emails synchronously, it can be tied up for a long time and delay other scheduled jobs.

~~~text
Scheduler thread
      |
      v
Outbox dispatcher (short claim batch)
      |
      v
mailTaskExecutor
      |
      +-- SMTP task 1
      +-- SMTP task 2
      +-- SMTP task 3

report scheduler
      |
      v
reportTaskExecutor
      |
      +-- Report task 1
~~~

If the application has multiple scheduled tasks requiring isolation, configure a dedicated `TaskScheduler` or appropriate scheduler pool. **`TaskScheduler` and `TaskExecutor` are two different responsibilities**: the scheduler decides *when to run*, while the executor decides *which resources a task runs on*. Do not assume configuring `mailTaskExecutor` automatically replaces the scheduler used by `@Scheduled`.

### Avoid Pollers Generating Too Many Tasks

Even with a bounded mail executor queue, a fast poller can repeatedly claim jobs and fill the queue. Strategies:

- Poll based on observed processing rate, not purely fixed intervals.
- Claim only while the mail executor still has capacity.
- Use small batch sizes and adjust with backlog and SMTP latency.
- When overloaded, pause claiming temporarily instead of flipping records to `CLAIMED` only for leases to expire uselessly.
- Maintain sensible retry state if the executor rejects task submission.

When coordinating claims and executor capacity across multiple replicas, use database/broker-level coordination rather than looking solely at local queues.

## 22. Alternatives to ThreadPoolTaskExecutor

`ThreadPoolTaskExecutor` fits many Spring applications with blocking I/O. However, it is not the only tool.

### Java's ExecutorService

Java's `ExecutorService`, such as `ThreadPoolExecutor`, can be used directly. Spring's `ThreadPoolTaskExecutor` is usually more convenient when bean lifecycle, `TaskDecorator`, `@Async`, and integrated observability are needed.

### Virtual Threads on Java 21+

Java 21 provides **virtual threads**, well suited to lowering the cost of managing many blocking operations compared to holding one platform thread per task. Supported Spring versions can use executors that launch virtual threads.

However:

- Virtual threads do not make SMTP servers accept emails any faster.
- They do not automatically cap total connections or sending rate.
- They are not a durable queue and do not replace a transactional outbox.
- Timeouts, admission control, quotas, and concurrent submission limits are still needed.
- Libraries, resource pinning, and real runtime characteristics must be evaluated.

If choosing virtual threads, separating mail/report workloads at **the level of concurrency policies, queues/dispatchers, rate limits, and observability** remains vital even though the threading model differs from traditional pools. Never allow unlimited concurrent tasks to hammer the same SMTP provider just because virtual threads are cheap.

### Dedicated Broker and Worker Service

For systems with high volume, multi-tenancy, or strict durability needs, the mail dispatcher can be split into a separate process/service reading from an outbox/broker. This provides stronger isolation than thread pools because CPU, heap, and deployments are independent.

On the other hand, adding separate services, brokers, and CI/CD pipelines increases operational cost. For a Spring monolith with moderate traffic, **a dedicated in-process executor + outbox when needed** is usually a sensible starting point.

## 23. Common Anti-Patterns

### Sharing One @Async Executor for Everything

When the SMTP provider slows down, report or image-processing tasks can suffer starvation. Split pools by workload and priority, and monitor each queue individually.

### Creating a New Executor per Email

~~~java
// Do not create a new thread pool per email.
ExecutorService executor = Executors.newFixedThreadPool(4);
executor.submit(() -> mailSender.send(message));
~~~

Every executor has its own threads, queue, and lifecycle. Creating pools per request quickly exhausts resources and complicates shutdown. Use a **Spring singleton bean** managing a shared executor for the mail workload.

### Unqualified @Async in Apps with Multiple Executors

Do not assume Spring always picks the right pool when multiple executor beans exist. Use `@Async("mailTaskExecutor")` or inject `@Qualifier("mailTaskExecutor")` to state intent clearly.

### Unbounded Queues

Task backlogs in RAM can grow indefinitely during an SMTP outage, leading to high latency or OOM. Set bounded queues, backpressure, and persist send intent durably if needed.

### Raising maxPoolSize to “Fix” a Slow Provider

During provider throttling or connection timeouts, more threads can cause more errors. Inspect latency, response codes, provider quotas, connection limits, and rate limiters before increasing concurrency.

### CallerRunsPolicy on HTTP Transaction Threads

A full pool can execute SMTP directly on the calling thread, slowing requests or sending email before database commit. Choose rejection policies by business contract, not merely out of desire to “never drop a task”.

### Ignoring CompletableFuture Failures

A method returning fast is not proof of successful sending. Futures can complete exceptionally or tasks can be rejected at submission. Monitor both admission errors and SMTP runtime errors.

### Relying on @Async to Guarantee Emails Are Never Lost

Queues in RAM are lost when the process crashes. Use an outbox or broker if mail intent must survive restarts.

### Passing Mutable Entities or Request Objects to Workers

JPA entities can lazy-load after the caller's transaction ends; HTTP requests/security contexts also have different lifecycles. Build immutable DTOs containing needed data and safe identifiers.

### Copying Every ThreadLocal Mechanically

Forwarding an entire SecurityContext or tenant context without evaluating permissions creates risk. Pass only needed data into tasks; use controlled context propagation, cleanup, and least privilege.

### Failing to Sum Cluster-Wide Concurrency

Each replica having `maxPoolSize` 8 means 10 replicas can generate up to 80 concurrent submissions. Plan quotas and resources **cluster-wide**, not per JVM.

### Sharing a Pool with Long-Running Scheduled Tasks

A scheduled task generating reports or sending mail synchronously can tie up scheduler threads and delay other schedules. Keep schedulers brief and offload heavy work to appropriate executors.

## 24. Checklist for Implementing a Dedicated Mail Executor

### Design

1. Classify workloads by I/O, CPU, latency, and priority.
2. Decide whether emails must be persisted durably before dispatch.
3. Create at least one dedicated mail executor if SMTP latency can impact other tasks.
4. Use explicit bean names and qualifiers for every `@Async`.
5. Set bounded concurrency/queues; define a rejection policy.
6. Set appropriate SMTP timeouts and provider-aligned rate limits.

### Business Boundaries

7. Never invoke the mail executor before database commit if the email reflects committed transactions.
8. Use `AFTER_COMMIT` for best-effort or an outbox/broker when recovery is needed.
9. Pass immutable DTOs and required metadata such as locale/tenant/event ID.
10. Have policies for exception handling, retries, and ambiguous submission outcomes.

### Operations

11. Monitor queue wait, active threads, rejections, SMTP duration, and backlogs.
12. Configure graceful shutdown without treating it as durable persistence.
13. Measure multi-replica impact on cluster-wide SMTP quotas.
14. Test dispatch through Spring proxies, overload, transaction boundaries, and shutdown/restarts.
15. Increase threads/queues only after checking monitoring data and downstream limits.

## 25. Summary

In Spring Framework Mail, a **dedicated executor for mail** isolates SMTP sending from other workloads such as report generation, image processing, or partner API calls. With `ThreadPoolTaskExecutor`, configure separate beans and use `@Async("mailTaskExecutor")` for mail and `@Async("reportTaskExecutor")` for reports. Pool design must simultaneously consider core threads, max threads, queue capacity, rejection policies, and SMTP timeouts.

What matters is not just running asynchronously, but **controlling admission and processing capacity**:

- Was the mail task accepted by the executor?
- Is the queue growing past target latency?
- Does the SMTP provider enforce concurrency/rate limits?
- How are async errors surfaced to callers, metrics, or job stores?
- Can emails be lost if the process restarts?
- Can sending happen before the transaction commits?

**Split pools to prevent resource contention; apply backpressure to prevent overload; use transactions/outboxes to preserve business correctness and durability.** These three responsibilities complement one another and are not interchangeable.
