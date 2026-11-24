# TaskExecutor and Thread Pools for Mail in Spring Framework Mail

Sending email over SMTP is an I/O operation: the application must connect to a mail server, transmit MIME data, and wait for a network response. If executed directly on the thread handling an HTTP request, SMTP wait time can slow down responses, tie up web server threads, and reduce the capacity to serve other requests. Spring provides `TaskExecutor` along with thread pool implementations to offload mail-sending work to separately managed threads.

A thread pool helps control concurrent tasks, the queue of waiting jobs, overload behavior, and thread lifecycle during application shutdown. However, **asynchronous does not mean durable**. Tasks queued in memory can be lost if the process stops abruptly. For critical transactional emails, a thread pool is usually the worker execution mechanism; a transactional outbox or message broker is what stores send requests durably.

This lesson explains how to configure `ThreadPoolTaskExecutor`, size the pool, use `@Async` with a mail service, handle queues and rejections, propagate context, manage shutdown, monitor load, and combine an executor with an outbox.

## 1. Why Does Mail Sending Need a Thread Pool?

An order confirmation request might perform:

1. Read and update the order in the database.
2. Build the email content.
3. Build the MIME message.
4. Connect to SMTP, transfer the message, and wait for the server response.
5. Return the HTTP response.

If step 4 takes several seconds, the request-handling thread is held for that entire duration. When many requests send mail simultaneously, the number of busy web server threads can climb even while CPU usage remains low.

Example:

~~~text
Without a dedicated executor

HTTP request thread
      |
      +--> update database
      |
      +--> build email
      |
      +--> wait for SMTP response
      |
      +--> return HTTP response
~~~

When offloading sending to an executor:

~~~text
HTTP request thread
      |
      +--> update database
      |
      +--> submit mail task
      |
      +--> return HTTP response
                  |
                  v
             Mail thread pool
                  |
                  +--> build MIME
                  +--> call JavaMailSender
                  +--> record outcome
~~~

The request thread only needs to submit the task and continue. Threads in the pool perform sending and wait on SMTP independently.

Benefits:

- Does not hold web request threads while waiting on SMTP.
- Limits the number of emails sent concurrently.
- Throttles load sent to the SMTP provider.
- Isolates mail resources from other background tasks.
- Allows naming threads, configuring shutdown, and monitoring the queue.
- Enables backpressure when the system receives requests faster than it can send.

However, an executor does not by itself solve transaction consistency, durable retries, or exactly-once delivery. Those concerns require design at the application and persistence layers.

## 2. What Is TaskExecutor?

`TaskExecutor` is Spring's abstraction for executing a `Runnable`. It is similar to Java's `Executor` but belongs to the Spring ecosystem and has implementations integrated with lifecycle, async processing, and application configuration.

Simple contract example:

~~~java
public interface TaskExecutor extends Executor {
    void execute(Runnable task);
}
~~~

An application can depend on `TaskExecutor` instead of creating threads manually with `new Thread(...)`.

Spring provides common implementations:

| Implementation | Characteristics | Use Case |
| --- | --- | --- |
| `SyncTaskExecutor` | Runs the task immediately on the calling thread | Tests or synchronous execution |
| `SimpleAsyncTaskExecutor` | Creates a new thread per task, not a traditional reusable pool | Low-volume tasks, unsuitable as a load-bounded pool |
| `ThreadPoolTaskExecutor` | Wraps Java's `ThreadPoolExecutor`, configures core/max/queue | Mail workloads requiring concurrency limits |
| `ConcurrentTaskExecutor` | Adapter for an existing Java Executor | Integrating an executor created elsewhere |
| `TaskExecutorAdapter` | Adapter from a Java Executor to Spring's abstraction | Bridging Java concurrency code with Spring |

For mail sending, `ThreadPoolTaskExecutor` is usually the right choice because it can bound threads and the queue. Do not spawn a new thread for every email; when traffic spikes, unbounded threads can exhaust OS resources, connections, and SMTP quotas.

### TaskExecutor Is Not a Durable Message Queue

`ThreadPoolTaskExecutor` keeps its queue in the process's memory. When the application is killed, restarted, or the machine fails, unexecuted tasks in the queue can be lost. An executor's queue only coordinates work while the process is running.

| Component | Role |
| --- | --- |
| TaskExecutor | Selects threads to execute tasks and regulates concurrency |
| In-memory task queue | Holds waiting tasks inside the process |
| Database outbox | Persists send requests durably alongside the business transaction |
| Message broker | Stores/routes messages across processes per broker durability and delivery semantics |
| SMTP provider | Accepts emails and handles further delivery |

If emails are best-effort notifications, an in-memory executor may suffice. If emails confirm transactions, invoices, or notifications requiring retries after restarts, store requests in an outbox/broker and use an executor to run workers.

## 3. How Does a Thread Pool Work?

A thread pool typically has three parts:

- **Worker threads**: threads currently executing tasks.
- **Task queue**: tasks waiting for their turn to run.
- **Rejection policy**: how to handle tasks when the pool cannot accept more.

With `ThreadPoolExecutor`, the submission processing order is essentially:

1. If running workers are fewer than core pool size, create a worker to run the task.
2. If core pool size has been reached, attempt to place the task in the queue.
3. If the queue cannot accept more tasks, create additional workers up to maximum pool size.
4. If maximum size is reached and the queue is also full, invoke the rejection handler.

Diagram:

~~~text
Submit task
    |
    v
Worker count < corePoolSize?
    |
   Yes -----------------> Create worker to run task
    |
   No
    |
    v
Space in queue?
    |
   Yes -----------------> Put task in queue
    |
   No
    |
    v
Worker count < maxPoolSize?
    |
   Yes -----------------> Create additional worker
    |
   No
    |
    v
Rejection policy
~~~

An important point: while space remains in the queue, the pool usually prefers queuing over growing threads past core size. Therefore, if the queue is too large or unbounded, `maxPoolSize` may rarely be used. Raising max size while keeping an unbounded queue generally will not clear a backlog.

## 4. Three Key Parameters of ThreadPoolTaskExecutor

### corePoolSize

The baseline number of workers the pool tries to maintain. Core threads are normally kept alive to process subsequent tasks, depending on `allowCoreThreadTimeOut`.

For example, a core size of 4 means the pool can run at least around four concurrent tasks under steady load.

### maxPoolSize

The upper limit on the number of workers. Once the queue is full, the executor can create extra workers up to this limit.

Do not set max too high just to drain a backlog. For mail, each worker may hold an open connection or an in-flight SMTP operation. Too many concurrent connections can exceed provider quotas or increase rate-limit errors.

### queueCapacity

The maximum number of tasks that can wait in `ThreadPoolTaskExecutor`'s queue. A bounded queue gives the application an explicit cap on pending work.

If queue capacity is 100, the pool can hold up to 100 waiting tasks in that queue configuration, in addition to running tasks. When the queue is full and workers reach max, new tasks are handled by the rejection policy.

### keepAliveSeconds

How long workers above core size can remain idle before being reclaimed. This is useful when load spikes and then subsides.

### Configuration Example

~~~java
@Configuration
@EnableAsync
public class MailAsyncConfiguration {

    @Bean(name = "mailTaskExecutor")
    public ThreadPoolTaskExecutor mailTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("mail-");

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy()
        );

        return executor;
    }
}
~~~

Spring manages the bean's lifecycle and initializes the executor. There is no need to call `initialize()` manually when the bean is registered normally.

The numbers 4, 8, and 100 are only examples. Production configuration must be based on target throughput, SMTP latency, provider quotas, machine resources, and acceptable backlog levels.

## 5. Bounded Queues and Why Unbounded Queues Should Be Avoided

An unbounded queue may seem to avoid ever rejecting tasks, but it can hide the fact that the system is accepting work faster than it can send.

Suppose:

- The application receives 100 email requests per second.
- SMTP workers can only send 20 emails per second.
- A difference of 80 tasks per second accumulates in the queue.

After one minute, the backlog can grow by about 4,800 tasks. The longer the queue gets, the more delayed emails become and the more memory is consumed.

~~~text
Arrival rate: 100 emails/sec
Send rate:     20 emails/sec
Difference:    80 emails/sec

After 60 seconds:
  backlog grows by ~4,800 emails
~~~

A bounded queue establishes a clear overload point. When the limit is reached, the application must choose explicit behavior: reject for later retry, run the task on the caller thread to apply backpressure under suitable conditions, or route requests to a durable queue/outbox.

### Queue Capacity Affects Latency

A large queue can reduce short-term rejections but increases wait time. For OTP emails or time-sensitive notifications, a task sitting in a queue for several minutes may already be useless.

Choose capacity based on:

- Maximum wait time acceptable to the business.
- Task submission rate.
- Actual worker throughput.
- Heap memory capacity.
- Provider rate/concurrent connection limits.
- Retry mechanism when the executor rejects.

Do not assume a larger queue is always better.

## 6. Choosing a Rejection Policy When the Pool Is Overloaded

When the queue is full and workers have reached max, the Java thread pool must decide how to handle new tasks.

| Policy | Behavior | Mail Sending Notes |
| --- | --- | --- |
| `AbortPolicy` | Throws an exception when a task cannot be accepted | Easy to detect overload; caller must handle and persist/retry the request |
| `CallerRunsPolicy` | Submitting thread runs the task itself if the executor is still active | Applies backpressure, but can cause HTTP request threads to send mail synchronously |
| `DiscardPolicy` | Drops the new task without reporting an error | Very dangerous for email because requests can vanish silently |
| `DiscardOldestPolicy` | Drops the oldest task in the queue and retries submitting the new one | Can lose older notifications; rarely suitable for transactional mail |

### AbortPolicy

This is usually the most observable choice for mail workloads:

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

When a task cannot be accepted, the submit/async call can fail with a rejection exception. The application boundary must catch that error or let it reach a place where it can be recorded, then decide to retry or persist the request.

If the send request exists only in the current request, rejection can lose the send intent if the caller does not handle it. With an outbox, the worker can keep the record in pending/retry status to try again later.

### CallerRunsPolicy

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy()
);
~~~

This policy runs the task on the submitting thread while the executor is running. It slows down the producer and creates natural backpressure. However:

- HTTP request threads may end up waiting on SMTP.
- A task submitted from a transaction thread may run mail sending directly on that thread.
- Response times can spike sharply while the pool is overloaded.
- Once the executor has shut down, `CallerRunsPolicy`'s behavior does not guarantee the task runs; the task may not execute.

Therefore, do not use `CallerRunsPolicy` assuming the task will definitely be sent on another thread or always executed. Understand the submission source and lifecycle.

### Do Not Use Discard Policies for Important Mail

Discard policies can make tasks disappear without an obvious exception. For transaction confirmations, invoices, or password resets, this creates hard-to-trace bugs. Consider dropping only if the business truly allows discarding notifications and metrics exist to observe it.

## 7. Using @Async with a Named Executor

Spring supports the `@Async` annotation to run methods on an executor. Enable the feature with `@EnableAsync`:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Declare a named executor:

~~~java
@Bean(name = "mailTaskExecutor")
public ThreadPoolTaskExecutor mailTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("mail-");
    return executor;
}
~~~

Mail-sending service:

~~~java
@Service
public class AsyncMailService {

    private final JavaMailSender mailSender;

    public AsyncMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailTaskExecutor")
    public void send(String recipient, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(body);

        mailSender.send(message);
    }
}
~~~

When another bean calls `send` through a Spring proxy, the call is dispatched to the executor named `mailTaskExecutor`.

### Why Name Executors?

An application may have multiple types of asynchronous work:

- Sending emails.
- Generating reports.
- Processing images.
- Syncing data.
- Sending webhooks.

If all share one pool, heavy report generation tasks can consume all threads and delay mail. Naming dedicated executors lets you manage concurrency, queues, and rejections per workload.

~~~text
Application
    |
    +--> @Async("mailTaskExecutor")
    |        +--> mail-1
    |        +--> mail-2
    |        +--> mail-3
    |
    +--> @Async("reportTaskExecutor")
             +--> report-1
             +--> report-2
~~~

You do not need a separate pool for every method. Split pools when workloads have different characteristics or SLAs.

## 8. Important Limitations of @Async

`@Async` works through a Spring proxy in default mode. Consequently, how a method is called directly determines whether the task actually runs asynchronously.

### Methods Must Be Called Through a Proxy

Misleading example:

~~~java
@Service
public class MailService {

    public void confirmOrder() {
        sendAsync(); // self-invocation
    }

    @Async("mailTaskExecutor")
    public void sendAsync() {
        // Send email.
    }
}
~~~

An internal call from one method to another on the same instance does not pass through the Spring proxy in default proxy mode. Therefore, the annotation may not produce the expected async behavior.

Move the async method into a separate bean:

~~~java
@Service
public class MailAsyncDispatcher {

    @Async("mailTaskExecutor")
    public void sendAsync(OutgoingMail mail) {
        // Send email.
    }
}
~~~

Business beans inject and call `MailAsyncDispatcher` through Spring.

### Do Not Call Async Methods on Manually Instantiated Objects

The following bypasses the Spring container:

~~~java
MailAsyncDispatcher dispatcher = new MailAsyncDispatcher(...);
dispatcher.sendAsync(mail);
~~~

Inject Spring-managed beans instead. If you instantiate objects with `new`, annotations are not applied by a proxy.

### Do Not Assume Transactions Propagate to Other Threads

Spring's transaction context is normally bound to the current thread. When `@Async` switches a method to another thread, the caller's transaction does not automatically carry over to the worker.

Example:

~~~java
@Transactional
public void updateOrderAndSend(Long orderId) {
    updateOrder(orderId);
    asyncMailDispatcher.sendAsync(...);
}
~~~

The mail task can start before the caller's transaction commits. Do not use async dispatch as a way to guarantee post-commit sending. If waiting for commit is required, use an appropriate transaction event or, better yet, an outbox for durable requirements.

## 9. Choosing a Return Type for @Async

There are two common patterns: methods returning `void` or `Future`/`CompletableFuture`.

### Methods Returning void

~~~java
@Async("mailTaskExecutor")
public void send(OutgoingMail mail) {
    mailDeliveryPort.send(mail);
}
~~~

The caller does not directly receive completion results. Exceptions thrown in the method cannot be thrown back onto the request thread after the request has already continued.

For void methods, you can configure `AsyncUncaughtExceptionHandler` to record exceptions:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    private final Executor mailTaskExecutor;

    public AsyncConfiguration(
            @Qualifier("mailTaskExecutor") Executor mailTaskExecutor) {
        this.mailTaskExecutor = mailTaskExecutor;
    }

    @Override
    public Executor getAsyncExecutor() {
        return mailTaskExecutor;
    }

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, parameters) -> {
            // Log/metrics with method and correlation ID.
        };
    }
}
~~~

This is a handler for exceptions from void async methods. It does not replace state persistence, retries, or business-level handling.

### Methods Returning CompletableFuture

When the caller needs to observe the outcome, return `CompletableFuture`:

~~~java
@Async("mailTaskExecutor")
public CompletableFuture<Void> send(OutgoingMail mail) {
    mailDeliveryPort.send(mail);
    return CompletableFuture.completedFuture(null);
}
~~~

Caller:

~~~java
CompletableFuture<Void> result = asyncMailService.send(mail);

result.whenComplete((ignored, exception) -> {
    if (exception != null) {
        // Record error or emit appropriate handling signal.
    }
});
~~~

If the method throws an exception, the future completes in an exceptional state. The caller can use `whenComplete`, `handle`, or `exceptionally` to observe it.

Do not call `get()` or `join()` immediately after submitting if the goal is not to wait for the task; doing so makes the calling flow synchronous in terms of wait time.

### Future Is Not a Durable Record

`CompletableFuture` allows observing results within the process lifecycle. It does not persist tasks to a database and does not recover work after a process crash. If send outcomes must be tracked long-term, persist status using an outbox or notification table.

## 10. Do Not Share a Default Pool for Everything

If no executor is specified, Spring must choose an executor according to async configuration. In an application with multiple workloads, relying on the default executor makes behavior depend on auto-configuration or `AsyncConfigurer`.

For mail, specify it explicitly:

~~~java
@Async("mailTaskExecutor")
public void send(OutgoingMail mail) {
    // ...
}
~~~

This makes it obvious to readers which pool the task belongs to and avoids accidentally running mail on an executor meant for other work.

A default bean can be configured via `AsyncConfigurer`, but annotations with explicit qualifiers are usually clearer when an application has multiple pools.

Do not use `ForkJoinPool.commonPool()` for SMTP just because it exists. The common pool is designed for certain parallel computations; long blocking I/O can occupy workers and affect other tasks sharing that pool.

## 11. Sizing the Thread Pool for Mail

There is no single fixed formula that applies to every SMTP provider. Email sending is usually I/O-bound: threads spend most of their time waiting on connections, writing data, and awaiting responses. That can allow higher concurrency than CPU-bound tasks, yet thread count is still bounded by:

- How many concurrent connections the SMTP provider allows.
- Rate limits per account, sender, or domain.
- Time to connect and send messages.
- Email and attachment sizes.
- Connection timeout, read timeout, and write timeout.
- CPU, heap, file descriptor, and network resources.
- Email criticality and maximum latency.

### Estimating Throughput

If one worker takes an average of 2 seconds per email and 4 workers run concurrently, theoretical steady-state throughput is roughly:

~~~text
4 workers / 2 seconds per email
= 2 emails per second
~~~

This is only an illustrative calculation. Actual throughput also depends on provider latency, rate limits, retries, message size, and template rendering time.

Increasing to 20 workers does not necessarily increase throughput fivefold. The provider may throttle, reject connections, or cap sessions. A larger pool may simply increase errors and downstream queuing.

### Reference Formula for I/O-Bound Workloads

A starting-point estimate in general thread pool sizing is:

~~~text
threads ≈ CPU cores × target CPU utilization
           × (1 + wait time / compute time)
~~~

This formula is only a heuristic for mixed workloads, not a rule for choosing SMTP thread counts. Mail providers typically have their own quotas, so cap concurrency to permitted limits and then measure real latency and throughput.

### Practical Selection Steps

1. Start with a small core size.
2. Set max size according to provider connection/rate limits and application resources.
3. Use a bounded queue aligned with your latency budget.
4. Run load tests with representative email sizes.
5. Monitor active threads, queue depth, task wait time, and SMTP errors.
6. Tune one parameter at a time.
7. Test both peak hours and when the provider is slow.

An example pool of 4 core, 8 max, queue 100 is a starting point for experimentation, not a standard setting for every application.

## 12. Splitting Pools by Email Type and SLA

An application may send several kinds of email:

| Email Type | Characteristics | Prioritization |
| --- | --- | --- |
| OTP/password reset | Time-sensitive, short content | Dedicated pool or priority quota, small queue |
| Order confirmation | Important, needs retry | Outbox and monitored workers |
| Invoices/attachments | Potentially large, long transfer time | Lower concurrency, size limits |
| Newsletter | High volume, rate-limited | Separate campaign queue and batch throttling |
| Periodic reports | Content generation may be CPU-heavy | Separate report rendering from mail delivery |

If newsletters push thousands of tasks into the same pool as OTPs, they can fill the queue and delay OTPs. Split workloads by SLA or use a scheduler/dispatcher with explicit priority.

Do not create too many tiny pools that fragment threads. Split only when justified by latency, quota, priority, or resource isolation.

## 13. Rate Limiting Mail Alongside the Thread Pool

A thread pool limits how many tasks run concurrently, but it does not directly cap emails per second.

For example, a 5-thread pool can send very fast if the provider responds in 50 ms; concurrency of 5 can still generate high throughput. If the provider allows 10 emails/second, the application needs a rate limiter or throttling dispatcher.

Distinguish:

- **Concurrency limit**: maximum number of emails being sent simultaneously.
- **Rate limit**: maximum number of emails submitted per unit of time.
- **Queue capacity**: maximum number of tasks waiting in-process.
- **Provider quota**: limits enforced by the provider per account/domain/API plan.

A rate limiter can be used in the worker before calling the adapter. With multiple application instances, rate limiting must be coordinated system-wide; a local per-JVM limiter can allow total throughput to exceed quotas.

## 14. Avoid Holding Database Transactions in Mail Workers

Mail-sending workers should read/claim data in a short transaction, then close the transaction before calling SMTP.

Avoid:

~~~java
@Transactional
public void processMail(OutboxMessage message) {
    message.markProcessing();
    outboxRepository.save(message);

    mailDeliveryPort.send(buildMail(message));

    message.markSubmitted();
}
~~~

In this example, the transaction can hold connections and locks throughout the entire SMTP operation.

Cleaner separation:

~~~text
Transaction A:
  claim outbox row
  set PROCESSING + lease
  COMMIT

No DB transaction:
  build MIME
  call JavaMailSender
  wait for SMTP response

Transaction B:
  set SUBMITTED or RETRY_WAIT/FAILED
  COMMIT
~~~

A thread pool only provides threads to run workers. Transaction boundaries must still be designed separately.

If a worker uses `@Async`, transactions are not automatically inherited from the submitting thread. If status updates are needed, call another service with explicit transactions.

## 15. Combining @TransactionalEventListener and @Async

For best-effort notifications, you can run a listener after commit and hand off sending to an executor:

~~~java
@Component
public class OrderMailListener {

    private final AsyncMailService asyncMailService;

    public OrderMailListener(AsyncMailService asyncMailService) {
        this.asyncMailService = asyncMailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        OutgoingMail mail = buildMail(event);
        asyncMailService.send(mail);
    }
}
~~~

Depending on the design, you can place `@Async` only on the listener or simply call an async dispatcher. Avoid stacking unnecessary async layers, as it makes it harder to determine which queue, exception handler, and executor actually run the task.

Another option is having an `AFTER_COMMIT` listener call the adapter directly on the listener's thread; if the listener method has `@Async`, sending already runs on that executor.

Keep in mind:

- Events reside in memory by default and can be lost on process crash.
- Executor queues also reside in memory and can be lost on process crash.
- If the pool is full, submission can be rejected.
- SMTP errors must be observed and handled.
- `AFTER_COMMIT` does not automatically provide durable retries.

For critical emails, insert an outbox row inside the transaction and have workers read the outbox. Events can be used merely to wake workers early, while polling/recovery must still exist.

## 16. Thread Pools and the Transactional Outbox

The outbox stores send requests durably; the executor runs tasks fetched from the outbox. The two components solve two different problems.

~~~text
Business transaction
      |
      +--> Update order
      +--> Insert mail_outbox
      |
      v
COMMIT
      |
      v
Outbox poller / dispatcher
      |
      v
Claim bounded batch
      |
      v
Mail TaskExecutor
   |       |       |
   v       v       v
 worker  worker  worker
   |       |       |
   +-------+-------+
           |
           v
    MailDeliveryPort
           |
           v
    JavaMailSender
           |
           v
    Update outbox result
~~~

A practical design:

1. The business transaction inserts an outbox row.
2. The poller claims a small batch, sets a lease, and commits.
3. The dispatcher submits records to the mail executor.
4. Workers render messages and send via the mail adapter.
5. Workers update status in a short transaction.
6. Transient errors are scheduled for retry.
7. Records with expired leases are reclaimed if a worker dies.

### Do Not Claim More Tasks Than the Pool Can Handle

If a poller claims 1,000 records while there are only 4 workers and queue capacity 100, some records may sit in `PROCESSING` too long before executing. Leases can expire before tasks start, causing other workers to reclaim them and creating contention.

Limit batches according to active + queue capacity of the executor, or design leases to start when a worker actually claims/picks up the task. Do not transition records to `PROCESSING` too early while they are merely sitting in a queue.

A safer approach is:

- Claim batches sized to execution capacity.
- Submit only when appropriate slots/queue capacity remain.
- If submission is rejected, return the record to retry/pending state in a transaction.
- Set leases long enough for queue wait + send time, or renew leases.
- Do not hold DB locks while waiting on the executor.

## 17. Handling Rejections When Using an Outbox

When the executor rejects a task, the outbox record must still be kept for reprocessing. Do not mark it `SUBMITTED` or delete the record.

Conceptual dispatcher logic example:

~~~java
try {
    mailTaskExecutor.execute(() -> mailWorker.process(outboxId));
} catch (TaskRejectedException exception) {
    outboxResultService.releaseForRetry(
        outboxId,
        "Mail executor is saturated"
    );
}
~~~

Depending on the executor type and submission API, the exception may be Spring's `TaskRejectedException` or a wrapped rejection exception. Handle the actual exception thrown by the implementation and avoid catching too broadly and treating every error as overload.

If a record was already claimed and marked `PROCESSING` before submission, a failed submission must update the status/lease so the record does not get stuck. If using a transaction for claiming/dispatching, remember that submitting a task is an external side effect outside the transaction; a database rollback cannot recall a task already accepted by the executor.

Outbox workers need a strategy to reconcile abandoned `PROCESSING` records rather than relying solely on the dispatcher's catch block.

## 18. Propagating Context Through a Thread Pool

Thread pools reuse threads. Thread-local data from a previous task can persist if code does not clean up properly. At the same time, request-thread context does not automatically appear on worker threads.

Common contexts:

- MDC logging: correlation ID, trace ID, tenant ID.
- SecurityContext: authentication/authorization info.
- Locale or language info.
- Tracing context from Micrometer/OpenTelemetry.
- Request metadata needed for logging.

Do not pass the entire HTTP request object or transaction context to workers. Pass required values in commands/events or use managed context propagation mechanisms.

### Using TaskDecorator for MDC

Example decorator that captures MDC context at submission time and restores prior context after the task finishes:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> submittedContext =
            MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext =
                MDC.getCopyOfContextMap();

            try {
                if (submittedContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(submittedContext);
                }

                task.run();
            } finally {
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Attach to the executor:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

Import the MDC/TaskDecorator classes matching your logging framework. If using Logback, MDC typically comes from the SLF4J API.

The decorator must restore or clear context in `finally` so context does not leak between tasks on the same thread. Do not retain old context indefinitely.

### Security Context

If a worker needs permissions or identity to access storage, do not propagate the entire security context by default. You can pass the required user ID/tenant ID and verify permissions in the worker. If Spring Security context propagation is required, use an appropriate executor wrapper such as `DelegatingSecurityContextAsyncTaskExecutor` and clearly define authentication lifecycle.

Transaction context should not be passed to workers; workers need fresh transactions for their own database operations.

## 19. Graceful Shutdown and Executor Lifecycle

When an application shuts down, the Spring container destroys executor beans. Without explicit configuration, waiting or running tasks may not finish as desired.

Common properties:

- `setWaitForTasksToCompleteOnShutdown(true)`: instructs the executor to wait for accepted tasks to finish during shutdown.
- `setAwaitTerminationSeconds(...)`: maximum time to wait for termination.
- `setThreadNamePrefix(...)`: helps identify threads in logs and thread dumps.

Example:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
executor.setThreadNamePrefix("mail-");
~~~

Graceful shutdown still has limits:

- Containers/orchestrators may send SIGKILL after the grace period.
- SMTP tasks can hang until timeout.
- Large queues may not finish draining before the shutdown deadline.
- Process crashes or host loss cannot run shutdown hooks.
- Tasks in an in-memory queue are not recovered after restart.

With an outbox, unfinished tasks can still be picked up by another worker after leases expire or the application restarts. Thus, graceful shutdown complements an outbox rather than replacing durability.

### Aligning Timeouts

SMTP connection/read/write timeouts should fit within the worker processing and shutdown time budget. If SMTP timeouts are much longer than the termination grace period, the application may be killed while workers are still sending.

Plan timing as:

~~~text
SMTP connect timeout
+ SMTP read/write timeout
+ status update
< worker lease / shutdown budget (with margin)
~~~

This is a planning relationship, not a mandatory formula. Actual timings must be measured and account for provider behavior.

## 20. Monitoring the Thread Pool

A production thread pool needs metrics and alerts. Watching exception logs alone is insufficient because backlogs can grow long before errors appear.

Key measurements:

| Metric | Meaning |
| --- | --- |
| Pool size | Current number of workers |
| Active count | Number of workers currently running tasks |
| Core/max size | Configured limits |
| Queue size | Number of waiting tasks |
| Queue remaining capacity | Remaining queue slots |
| Completed task count | Number of completed tasks |
| Rejected task count | Number of rejected tasks |
| Task execution duration | Execution time |
| Queue wait duration | Time from submission to start |
| SMTP failure/timeout rate | Transport quality |
| Outbox oldest age | Age of the oldest unprocessed record |

Some information can be read directly from `ThreadPoolTaskExecutor` after initialization:

~~~java
int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queueSize = executor.getThreadPoolExecutor()
    .getQueue()
    .size();
long completed = executor.getThreadPoolExecutor()
    .getCompletedTaskCount();
~~~

Do not call these accessors before the executor is initialized. Numbers are snapshots and can change immediately after reading; use metrics to track trends rather than treating a single read as absolute state.

### Metrics and Alerts

You can set alerts when:

- The queue is consistently near full.
- Active count frequently equals max size.
- Rejections increase.
- Queue wait exceeds email SLAs.
- SMTP timeout/error rates rise.
- Outbox pending age grows.
- Expired-lease `PROCESSING` records increase.

Spring Boot Actuator/Micrometer can expose executor metrics depending on version and registration setup. If instrumenting manually, keep tags bounded such as executor name, provider, or mail category; avoid tagging recipient/email IDs that cause high cardinality and expose personal data.

## 21. Configuring the Pool via Spring Boot Properties

In Spring Boot applications, you can configure the default executor using the task execution properties of the version in use. However, if mail needs its own pool, an explicitly named bean is usually easier to control.

Example custom configuration with `@ConfigurationProperties`:

~~~yaml
app:
  mail:
    executor:
      core-pool-size: 4
      max-pool-size: 8
      queue-capacity: 100
      keep-alive-seconds: 60
      await-termination-seconds: 30
~~~

Properties class:

~~~java
@ConfigurationProperties(prefix = "app.mail.executor")
public record MailExecutorProperties(
    int corePoolSize,
    int maxPoolSize,
    int queueCapacity,
    int keepAliveSeconds,
    int awaitTerminationSeconds
) {}
~~~

Executor bean:

~~~java
@Bean(name = "mailTaskExecutor")
public ThreadPoolTaskExecutor mailTaskExecutor(
        MailExecutorProperties properties) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(properties.corePoolSize());
    executor.setMaxPoolSize(properties.maxPoolSize());
    executor.setQueueCapacity(properties.queueCapacity());
    executor.setKeepAliveSeconds(properties.keepAliveSeconds());
    executor.setThreadNamePrefix("mail-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(
        properties.awaitTerminationSeconds()
    );

    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
    );

    return executor;
}
~~~

Register the properties using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. You can add validation to ensure core size is positive, max is not less than core, queue capacity is non-negative, and timeouts are reasonable.

The example above configures a separate pool without depending on the defaults of the auto-configured application executor.

## 22. Testing Async Mail Services

Unit tests should not have to wait for real SMTP. You can mock the mail adapter or use a fake implementation, then verify the method was called.

Example service depending on a port:

~~~java
@Service
public class AsyncMailDispatcher {

    private final MailDeliveryPort mailDeliveryPort;

    public AsyncMailDispatcher(MailDeliveryPort mailDeliveryPort) {
        this.mailDeliveryPort = mailDeliveryPort;
    }

    @Async("mailTaskExecutor")
    public CompletableFuture<Void> send(OutgoingMail mail) {
        mailDeliveryPort.send(mail);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

An integration test with a Spring context can invoke the method and wait on the future:

~~~java
@Test
void sendsMailOnConfiguredExecutor() throws Exception {
    OutgoingMail mail = new OutgoingMail(
        "customer@example.com",
        "Order confirmed",
        "Your order is confirmed.",
        "<p>Your order is confirmed.</p>"
    );

    CompletableFuture<Void> future = dispatcher.send(mail);

    future.get(5, TimeUnit.SECONDS);

    verify(mailDeliveryPort).send(mail);
}
~~~

This test verifies the method completes and the port is called. It does not yet prove the SMTP provider received the message.

### Testing Executor Rejection

You can configure a very small pool and low queue capacity in tests to simulate overload. Verify that rejection is observed and the outbox record is not marked successful.

Do not use fixed sleeps for timing when synchronization via latches/futures is possible. Concurrency tests should check meaningful behavior such as maximum concurrent tasks running, not just thread names.

### Testing Errors in CompletableFuture

If the mail adapter throws an exception, the future should complete exceptionally:

~~~java
CompletableFuture<Void> future = dispatcher.send(mail);

assertThrows(
    ExecutionException.class,
    () -> future.get(5, TimeUnit.SECONDS)
);
~~~

Configure the fake/mock to throw an exception before asserting. For void-returning methods, verify via `AsyncUncaughtExceptionHandler` or an error recorder.

## 23. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Creating a new thread per email | Unbounded thread growth during bursts | Use a bounded `ThreadPoolTaskExecutor` |
| Unbounded queue | Backlog and memory grow indefinitely, latency hard to control | Use a bounded queue |
| Raising only `maxPoolSize` with a huge queue | Pool does not expand as expected | Understand queue/core/max ordering |
| Sharing a pool for mail and CPU-heavy tasks | One workload stalls the other | Split pools by SLA/resources |
| Using the common pool for blocking SMTP | Occupies shared workers | Use a dedicated executor |
| Using `@Async` and calling a method in the same class | Proxy is bypassed, task stays synchronous | Extract to a bean and call via Spring proxy |
| Manually calling `new` on an `@Async` service | Annotation is not managed by a Spring proxy | Inject bean from container |
| Expecting void async exceptions to reach the caller | Errors go unnoticed | `AsyncUncaughtExceptionHandler` or `CompletableFuture` |
| Calling `future.get()` right after submit | Caller still waits on the task | Handle callbacks or return appropriate response |
| Assuming `@Async` propagates transactions to workers | Worker runs outside caller's transaction | Design separate transactions |
| Using `CallerRuns` without knowing callers | HTTP requests may send mail synchronously | Pick rejection policy based on submission source |
| Using `DiscardPolicy` | Emails vanish silently | Abort/retry via outbox |
| Claiming more outbox rows than pool capacity | `PROCESSING` records wait too long, leases expire | Size batches to capacity and manage leases |
| Sending SMTP inside a DB transaction | Holds connections/locks during network waits | Claim/commit, send outside transaction |
| Assuming the executor queue is durable | Process crash loses tasks | Outbox or broker |
| No graceful shutdown | In-flight tasks may be terminated during deploy | Configure termination and timeouts |
| Not monitoring queue depth/rejections | Outages only noticed when users complain | Metrics, logs, and alerts |

## 24. Process for Implementing TaskExecutor for Mail

A practical rollout roadmap:

1. **Measure current workload**: emails/second, SMTP latency, message sizes, and provider quotas.
2. **Separate a mail dispatcher** from controllers/use cases for a clear execution boundary.
3. **Register a dedicated `ThreadPoolTaskExecutor`** with bounded core/max/queue and a thread prefix.
4. **Use `@Async("mailTaskExecutor")`** or call `TaskExecutor` directly; do not mix both unnecessarily.
5. **Choose a rejection policy** based on submission sources and ability to persist/retry tasks.
6. **Configure SMTP timeouts** and an appropriate shutdown budget.
7. **Limit rate/concurrency** per provider, not just CPU count.
8. **Propagate correlation context safely** and never propagate transaction thread-locals.
9. **Instrument the pool**: active, queue, rejected, wait time, execution duration, and SMTP errors.
10. **For critical emails, use an outbox** to store requests durably; the executor only runs workers pulling from the outbox.
11. **Test saturation, rejection, exceptions, shutdown, and process restarts** in an appropriate environment.

Architecture diagram:

~~~text
Business transaction
       |
       v
Insert mail_outbox
       |
       v
COMMIT
       |
       v
Outbox dispatcher
       |
       v
Bounded TaskExecutor
   |       |       |
   v       v       v
mail-1  mail-2  mail-3
   |       |       |
   +-------+-------+
           |
           v
    MailDeliveryPort
           |
           v
     JavaMailSender
           |
           v
      SMTP provider
           |
           v
Update outbox result
~~~

## 25. Key Takeaways

`TaskExecutor` and thread pools help control how an application executes asynchronous mail-sending tasks:

- `TaskExecutor` is Spring's abstraction for task execution.
- `ThreadPoolTaskExecutor` fits when threads and queues must be bounded.
- Core size, max size, and queue capacity interact; large queues can leave max size rarely used.
- Bounded queues cap backlogs and surface overload conditions.
- Rejection policies must fit the business; avoid silently dropping mail tasks.
- Use `@Async("mailTaskExecutor")` to select the pool explicitly.
- `@Async` works via Spring proxies; self-invocation and manually constructed objects bypass the default proxy.
- Use `CompletableFuture` when callers need to observe results; void methods require an exception handler.
- Transaction contexts do not automatically propagate to other threads.
- Size pools based on SMTP latency, provider quotas, message sizes, and real throughput, not CPU cores alone.
- Thread pools cap concurrency; rate limiters regulate emails per second.
- Configure graceful shutdown and timeouts so tasks have a chance to finish during deploys.
- Use `TaskDecorator` or context propagation for MDC/tracing/security when needed; never let `ThreadLocal` leak across tasks.
- Executor queues live in memory, not in a durable queue.
- For critical transactional emails, persist requests via a transactional outbox; workers use thread pools to process and retry.
- Monitor active threads, queue depth, rejections, wait times, SMTP errors, and outbox age.

A thread pool is an execution-resource coordinator. It keeps mail workloads bounded and off request-handling threads, yet notification reliability still depends on how requests are persisted, transaction boundaries, retries, and crash recovery. Combining a bounded `ThreadPoolTaskExecutor` with an outbox worker gives the application both SMTP concurrency control and durability across process restarts.
