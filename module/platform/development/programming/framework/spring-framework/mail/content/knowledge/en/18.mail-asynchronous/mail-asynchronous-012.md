# Ensuring Transactions Are Not Mistakenly Thought to Span Across Tasks

When offloading email sending to an asynchronous task in Spring, a common misconception is thinking the transaction of the method calling `@Async` continues inside the background task, or that a task invoked inside `@Transactional` is guaranteed to start only after the transaction commits.

**Neither assumption is true.** Standard database transactions are bound to the thread's execution context; an `@Async` task runs on a different thread with its own lifecycle. Moreover, a task can begin the moment the executor accepts it, before the business method on the calling thread finishes or commits.

In the **Spring Framework Mail** module, this distinction is critical. If a worker sends an order confirmation email too early, the recipient can receive a notice for an order that later rolls back. If a worker reads data before the originating transaction commits, it may miss recent changes. If the application dies between commit and scheduling the email send, the send request can be lost. The solution is not stretching transactions across SMTP, but **explicitly designing transaction boundaries, when send requests are created, and durable work persistence**.

## 1. Three Concepts to Distinguish

| Concept | Role | What Not to Infer |
| --- | --- | --- |
| `@Transactional` | Defines transaction scope for database operations within the intercepted execution flow | Does not make other threads share the same transaction |
| `@Async` | Offloads method execution to a `TaskExecutor`, typically another thread | Does not wait for the caller's transaction to commit |
| `JavaMailSender.send(...)` | Sends a MIME message over SMTP per transport configuration | Does not participate in database commit/rollback |

A transaction managed by `PlatformTransactionManager` typically binds resources such as a JDBC connection or JPA `EntityManager` to the thread via `TransactionSynchronizationManager`. When the `@Transactional` method finishes, the transaction manager commits or rolls back and cleans up that context.

`@Async` is not a mechanism to transfer an open JDBC transaction from thread A to thread B. If a background task needs to read or update the database, it must work with its own transaction or properly configured database operations on **the task's own thread**.

### Two Independent Axes

Imagine two axes:

- **Transaction axis:** start, perform DB operations, commit/rollback.
- **Asynchronous execution axis:** accept task, queue, run on worker, finish or fail.

No default rule guarantees these two axes finish together.

```text
HTTP Thread                         Mail Executor Thread
    |                                      |
    | BEGIN TX A                           |
    | update order                         |
    | call asyncMailService.send(...)      |
    |---------------- submit task -------->|
    |                                      | start rendering email
    |                                      | may call SMTP
    | COMMIT TX A                          |
    |                                      | task finishes
    | return HTTP response                 |
```

The task submission arrow only means the executor was asked to perform work. It creates no “after commit” relationship between the two threads.

## 2. The Caller's Transaction Does Not Extend to the Worker

Suppose a business method:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AsyncMailService asyncMailService;

    public OrderService(
            OrderRepository orderRepository,
            AsyncMailService asyncMailService
    ) {
        this.orderRepository = orderRepository;
        this.asyncMailService = asyncMailService;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();
        order.confirm();

        asyncMailService.sendConfirmation(order.getId());
    }
}
```

Sending service:

```java
@Service
public class AsyncMailService {

    @Async("mailExecutor")
    public void sendConfirmation(UUID orderId) {
        // Executes on worker thread, not inside confirmOrder()'s TX.
    }
}
```

`confirmOrder()` has transaction **A**; `sendConfirmation()` is run by the executor on another thread. The task does not automatically inherit transaction A, even though it receives the same `orderId` and the call happens before `confirmOrder()` returns.

### What Happens If the Worker Queries the Database?

The worker might perform:

```java
@Async("mailExecutor")
public void sendConfirmation(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();
    // Render email from order.
}
```

If TX A has not committed yet, a query from the worker using its own transaction/connection may:

- Read **stale values** instead of changes just made by TX A.
- Fail to find a record just inserted in TX A.
- Block on locks or throw errors depending on the database, isolation level, and query.
- Read data inconsistent with the snapshot the caller was using.

Never rely on a lucky timing assumption like “SMTP is usually slow so the transaction has probably committed first”. When load shifts, the worker can run immediately and expose the race condition.

## 3. Realistic Timeline: Async Can Run Before Commit

Consider confirming an order:

```text
Time       | HTTP Thread / TX A             | Mail Thread / Task
-----------+--------------------------------+------------------------------
T0         | BEGIN TX A                     |
T1         | UPDATE orders SET confirmed    |
T2         | submit async task              |
T3         |                                | Read order: sees old state
T4         |                                | Send email from read data
T5         | COMMIT TX A                    |
T6         | HTTP response                  | Task finished
```

That is a valid execution schedule. Another schedule is even more dangerous:

```text
T0  BEGIN TX A
T1  update order
T2  submit async mail
T3  worker sends email "Order has been confirmed"
T4  transaction hits constraint check error
T5  ROLLBACK TX A
```

The recipient was told the order was confirmed, yet authoritative data never recorded it. **SMTP is a side effect outside the DB transaction**, so a rollback cannot recall an email already accepted by the mail server.

Rule: if an email describes a business change valid only after commit, the send request must be coordinated with commit, not merely invoked inside a transactional method.

## 4. @Async Does Not Automatically Wait for @Transactional to Finish

A few typical misconceptions:

| Misconception | Reality |
| --- | --- |
| “Calling `@Async` from `@Transactional` makes the worker wait for commit.” | The executor can run the worker before commit. |
| “Passing an entity lets the worker see uncommitted data.” | No; the caller's transaction is not shared by default. |
| “Adding `@Transactional` to the worker extends the old transaction.” | The worker opens an independent transaction scope per proxy/transaction manager mechanics. |
| “`@Transactional(propagation = REQUIRES_NEW)` continues the original TX.” | `REQUIRES_NEW` creates a new transaction; it does not inherit the original one. |
| “An email send failure in the worker rolls back the caller's transaction.” | Once the caller has committed, a later async failure cannot roll it back. |
| “An `@Async` method returning means the email was sent.” | It may merely have been queued into the executor. |
| “`@TransactionalEventListener(AFTER_COMMIT)` persists events durably.” | It only schedules when the listener runs; it does not create a durable queue. |

### Should Transaction Context Be Passed to Tasks?

Normally **no**. Manually passing JDBC connections, `EntityManager` instances, transaction synchronizations, or thread-local transaction state to workers can cause concurrency bugs and break transaction boundaries. These resources are not designed for arbitrary multi-threaded sharing.

If post-commit data is needed, let the task re-query in its own transaction after commit or pass an intentionally prepared snapshot/DTO. If durability is needed, use an outbox.

## 5. What Does @Transactional on the Worker Itself Mean?

An async method can be annotated with `@Transactional`:

```java
@Service
public class AsyncOrderReader {

    private final OrderRepository orderRepository;

    public AsyncOrderReader(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Async("mailExecutor")
    @Transactional(readOnly = true)
    public CompletableFuture<OrderMailData> loadData(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        OrderMailData data = new OrderMailData(
                order.getCustomerEmail(),
                order.getCode(),
                order.getCustomerName()
        );

        return CompletableFuture.completedFuture(data);
    }
}
```

When interception is configured properly, the database read portion runs inside **transaction B on the worker thread**. Transaction B is not the caller's TX A. It has its own start/commit timing and sees data according to the database isolation level.

### Why Not Wrap SMTP Sending in a Long Transaction?

Suppose:

```java
@Async("mailExecutor")
@Transactional
public void sendMailAndUpdateStatus(UUID notificationId) {
    MailNotification n = repository.findById(notificationId)
            .orElseThrow();

    mailSender.send(buildMessage(n)); // Network I/O inside DB transaction.

    n.markSubmitted();
}
```

This code can keep the DB transaction open for the entire SMTP wait. It does not make mail sending rollback-capable and can cause:

- Holding connections and locks for long periods.
- Increased contention across multiple workers.
- Reduced throughput when SMTP is slow.
- Inconsistency between DB status and real sends if the database rolls back after SMTP succeeds.

Instead, **separate a short transaction to claim**, **send SMTP outside transactions**, and use **another short transaction to record the outcome**.

## 6. REQUIRES_NEW Does Not Carry a Transaction Across Task Boundaries

`Propagation.REQUIRES_NEW` instructs Spring to start a new transaction when the method is intercepted in an appropriate execution scope. When a caller is in transaction A and calls a `REQUIRES_NEW` method via proxy on the same thread, Spring can suspend A and run B. However, that does not mean A transfers across threads.

Example:

```java
@Service
public class MailStatusService {

    private final MailStatusRepository repository;

    public MailStatusService(MailStatusRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSubmitted(UUID notificationId) {
        repository.updateStatus(notificationId, "SUBMITTED");
    }
}
```

When the worker calls this method through a Spring bean proxy, it runs in a fresh transaction to update status. It has nothing to do with the already-closed HTTP transaction.

**Distinguish two goals:**

- Wanting to **perform an independent DB write inside the worker**: a new transaction may fit.
- Wanting to **guarantee the email is only sent after business commit**: `REQUIRES_NEW` alone cannot solve this; after-commit coordination or an outbox is still required.

If a class calls its own `@Transactional` method directly, proxies can be bypassed. Place transaction boundaries on separate beans and verify proxy configuration.

## 7. Separating Responsibilities Along Transaction Boundaries

An understandable architecture separates three responsibilities:

1. **Business service:** applies business changes and records the send request in one transaction.
2. **Mail worker:** performs rendering and SMTP I/O outside long transactions.
3. **Mail status service:** updates outcomes in independent short transactions.

Diagram:

```text
Business thread                       Mail worker thread
----------------------------          ----------------------------
BEGIN TX A
  update business data
  insert notification PENDING
COMMIT TX A
         |
         | notification readable after commit
         +----------------------------> BEGIN TX B
                                        claim notification
                                        COMMIT TX B
                                              |
                                              v
                                        render + SMTP send
                                        (not holding DB TX)
                                              |
                                              v
                                        BEGIN TX C
                                        update status
                                        COMMIT TX C
```

This pattern avoids long transactions and clarifies state. Transactions A, B, and C are **distinct transactions** that can run on different threads/processes.

## 8. When Can @TransactionalEventListener(AFTER_COMMIT) Be Used?

If you want to coordinate a task to run **after commit** without building a durable queue, Spring provides `@TransactionalEventListener`:

```java
public record OrderConfirmedEvent(
        UUID orderId,
        String recipient,
        String orderCode
) {}
```

In the business service:

```java
@Service
public class OrderApplicationService {

    private final ApplicationEventPublisher publisher;
    private final OrderRepository orderRepository;

    public OrderApplicationService(
            ApplicationEventPublisher publisher,
            OrderRepository orderRepository
    ) {
        this.publisher = publisher;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void confirm(UUID id) {
        Order order = orderRepository.findById(id).orElseThrow();
        order.confirm();

        publisher.publishEvent(new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCode()
        ));
    }
}
```

Listener receives the event after commit and delegates to an async bean:

```java
@Component
public class OrderMailEventListener {

    private final AsyncMailSender asyncMailSender;

    public OrderMailEventListener(AsyncMailSender asyncMailSender) {
        this.asyncMailSender = asyncMailSender;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        asyncMailSender.sendConfirmation(event);
    }
}
```

Task lives on another bean:

```java
@Service
public class AsyncMailSender {

    private final JavaMailSender mailSender;

    public AsyncMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendConfirmation(OrderConfirmedEvent event) {
        // Render message and send via SMTP.
    }
}
```

With a standard Spring-managed transaction:

- If TX commits, the `AFTER_COMMIT` listener runs.
- If TX rolls back, the `AFTER_COMMIT` listener does not run.
- When the listener calls the async sender, the task can run on a worker thread.
- The worker still does not inherit the committed transaction.

### Important Limitations of AFTER_COMMIT

**After commit does not mean durable.** Standard application events exist in memory. If the process crashes after commit yet before the event is processed or the task executes, the email can be lost.

Additionally:

- Listeners do not automatically guarantee retries if the executor rejects the task.
- An SMTP error occurring after commit cannot roll back the order.
- An event may be published without an active transaction; by default, transaction-bound listeners do not run in that case unless configured with fallback execution.
- Writing to the database directly inside an after-commit callback can cause problems because resources from the old transaction remain bound during completion; if writing new data inside a callback, use an explicit new transaction such as a `REQUIRES_NEW` service.

`AFTER_COMMIT` fits when you only need commit-then-dispatch ordering and can accept potential task loss. Critical emails should consider a transactional outbox.

## 9. Do Not Use After-Commit Callbacks as a New Transaction

Spring provides `TransactionSynchronization` with an `afterCommit()` callback. You can register a post-commit callback:

```java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                asyncMailSender.sendConfirmation(event);
            }
        }
);
```

This is a lower-level mechanism than `@TransactionalEventListener`; it does not automatically persist events to a database. Register it only when transaction synchronization is active and intentional.

Do not treat this callback as a new transaction. The callback phase occurs after the commit decision; if the callback fails, you cannot “go back” and undo the completed database commit.

If new state must be saved after commit, call a `@Transactional(propagation = REQUIRES_NEW)` bean or put the work in a separate worker transaction. For high reliability, the clearer approach remains **writing the mail request to an outbox before commit** rather than issuing work solely from callbacks.

## 10. Transactional Outbox: Bridging the Gap Between Commit and Task

Suppose using an after-commit event:

```text
COMMIT order ----------- [process crash] ----------> submit async
```

If a crash occurs in this gap, the database saved the order yet the mail task is saved nowhere. Graceful shutdown or executor retries cannot recover a task that was never persisted.

A **transactional outbox** uses the same database transaction to persist both business changes and the send request:

```text
BEGIN TX A
  UPDATE orders...
  INSERT mail_notification(status=PENDING)...
COMMIT TX A
       |
       v
Worker reads committed notification
       |
       v
Send SMTP and record result
```

If TX A rolls back, both the order change and the notification roll back. If TX A commits and the process crashes, the notification remains in the database and another worker can resume processing.

### Minimal Schema Example

```sql
CREATE TABLE mail_notification (
    id                 UUID PRIMARY KEY,
    business_event_id  VARCHAR(200) NOT NULL,
    notification_type  VARCHAR(100) NOT NULL,
    recipient          VARCHAR(320) NOT NULL,
    template_key       VARCHAR(150) NOT NULL,
    payload_json       TEXT NOT NULL,
    status             VARCHAR(30) NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMP WITH TIME ZONE,
    claim_token        UUID,
    lease_until        TIMESTAMP WITH TIME ZONE,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_at       TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_mail_event
        UNIQUE (business_event_id, notification_type)
);
```

This table both stores the send request and serves as a database queue. Larger systems may separate outbox events from notification records, yet the principle remains writing them in the same transaction as business logic.

A unique constraint on the business event prevents duplicate invocations from creating two notifications for the same event when policy allows one email per event.

### Example Writing Notification Alongside Business Logic

```java
@Service
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final MailNotificationRepository notificationRepository;

    public OrderConfirmationService(
            OrderRepository orderRepository,
            MailNotificationRepository notificationRepository
    ) {
        this.orderRepository = orderRepository;
        this.notificationRepository = notificationRepository;
    }

    @Transactional
    public UUID confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.confirm();

        UUID notificationId = UUID.randomUUID();
        notificationRepository.insertPending(
                notificationId,
                order.getId().toString(),
                "ORDER_CONFIRMED",
                order.getCustomerEmail(),
                "order-confirmation",
                createMailPayload(order)
        );

        return notificationId;
    }
}
```

`insertPending(...)` is an application-implemented repository method. In production, handle duplicate requests/events with atomic insert/upsert and re-read existing notifications. Do not simply check existence then insert while ignoring race conditions.

## 11. Which Transactions Should the Worker Use?

A worker picks up a committed notification, builds the email, and sends via SMTP. Separate three phases:

1. **Claim:** short transaction A/B to acquire a notification and mark `PROCESSING`.
2. **Send:** SMTP I/O outside DB transactions.
3. **Record:** another short transaction to record `SUBMITTED`, `RETRY_WAIT`, `FAILED`, or `UNKNOWN`.

```text
Worker                    Database                       SMTP
  |                           |                            |
  |-- BEGIN TX claim -------->|                            |
  |-- lock + mark PROCESSING->|                            |
  |-- COMMIT claim ---------->|                            |
  |                           |                            |
  |-- render MIME ------------------------------------------|
  |-- send ------------------------------------------------>|
  |<----------------------------- accepted / rejected / ? --|
  |                           |                            |
  |-- BEGIN TX status ------->|                            |
  |-- mark outcome ---------->|                            |
  |-- COMMIT status --------->|                            |
```

Do not hold the claim transaction open while SMTP responds. If a worker dies, leases are needed to detect expired claims alongside an explicit recovery policy.

### Atomic Claiming with PostgreSQL

An example using `FOR UPDATE SKIP LOCKED` inside a short transaction:

```sql
BEGIN;

SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Mark those exact selected rows as PROCESSING,
-- generate claim_token/lease_until and fetch payload to process.
COMMIT;
```

In production code, selection and updating must happen **in the same transaction**, or via an equivalent atomic claim statement. Workers only process rows they successfully claimed.

With multiple instances, each instance can claim distinct rows instead of sending the same email concurrently. When updating status, check `claim_token` to prevent an old worker from overwriting outcomes after the lease has transferred.

## 12. Example Splitting into Beans with Clear Transaction Boundaries

Three illustrative beans:

```java
@Service
public class MailClaimService {

    private final MailNotificationRepository repository;

    public MailClaimService(MailNotificationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(int batchSize) {
        return repository.claimPending(batchSize);
    }
}
```

```java
@Service
public class MailOutcomeService {

    private final MailNotificationRepository repository;

    public MailOutcomeService(MailNotificationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void submitted(UUID id, UUID claimToken) {
        repository.markSubmittedIfClaimMatches(id, claimToken);
    }

    @Transactional
    public void failure(
            UUID id,
            UUID claimToken,
            MailFailureKind kind
    ) {
        repository.recordFailureIfClaimMatches(id, claimToken, kind);
    }
}
```

Worker bean:

```java
@Component
public class MailPollingWorker {

    private final MailClaimService claimService;
    private final MailOutcomeService outcomeService;
    private final MailComposer composer;
    private final JavaMailSender mailSender;

    public MailPollingWorker(
            MailClaimService claimService,
            MailOutcomeService outcomeService,
            MailComposer composer,
            JavaMailSender mailSender
    ) {
        this.claimService = claimService;
        this.outcomeService = outcomeService;
        this.composer = composer;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "5000")
    public void poll() {
        List<ClaimedMail> batch = claimService.claimBatch(10);
        for (ClaimedMail item : batch) {
            sendOne(item);
        }
    }

    private void sendOne(ClaimedMail item) {
        try {
            MimeMessage mimeMessage = composer.compose(item);
            mailSender.send(mimeMessage); // Not inside the claim DB transaction.
            outcomeService.submitted(item.id(), item.claimToken());
        } catch (MailException ex) {
            outcomeService.failure(
                    item.id(),
                    item.claimToken(),
                    classifySendFailure(ex)
            );
        } catch (MessagingException ex) {
            outcomeService.failure(
                    item.id(),
                    item.claimToken(),
                    MailFailureKind.MESSAGE_BUILD_ERROR
            );
        }
    }
}
```

Types `ClaimedMail`, `MailComposer`, `MailFailureKind`, and repository methods are architectural illustrations. `classifySendFailure` must classify carefully based on SMTP stage and available evidence, rather than assuming every exception is safe to retry.

**Why separate beans?** `claimBatch()` and `submitted()` are called through Spring bean proxies, making transaction annotation boundaries clearly observable. The worker is not wrapped in a single `@Transactional` spanning the SMTP call.

## 13. A Task Can Fail After the Business Transaction Has Committed

Once the business TX commits, the mail-sending task can:

- Encounter a template error.
- Fail to read an attachment.
- Time out on SMTP.
- Be rejected by SMTP due to sender/recipient.
- Be rejected by the executor because the queue is full.
- Experience a process crash.

These errors **do not roll back the already-committed business transaction**. Express application outcomes accurately:

| Outcome | What Happened | Appropriate Behavior |
| --- | --- | --- |
| Business commit succeeds, task not yet run | Business state saved; mail waiting | Return `PENDING` receipt/status |
| Business commit succeeds, SMTP accepts | Business state saved; mail accepted for relay | Record `SUBMITTED` |
| Business commit succeeds, SMTP clearly rejects | Business state still saved; mail failed | `RETRY_WAIT` or `FAILED` by error type |
| Business commit succeeds, SMTP outcome unclear | Unknown whether server received mail | `UNKNOWN` and reconciliation |
| Business transaction rolls back | Business change not committed | Do not emit an effective notification |

Do not return “email delivered successfully” the moment an `@Async` method is called. For async APIs, `202 Accepted` usually fits once the send request **has been durably recorded**; delivery status must be queried separately.

## 14. SMTP Does Not Participate in Database Transactions

Sending mail and writing to a database are two side effects on two separate systems. There is no shared ACID transaction spanning a database commit and standard SMTP submission.

Consider this scenario:

```text
Worker               SMTP server                Database
  |                        |                         |
  |---- send message ----->|                         |
  |<--- 250 accepted ------|                         |
  |                        |                         |
  X crash before DB write  |                         |
  |                        |                  status=PROCESSING
```

The database does not yet know SMTP accepted the message. Restarting and immediately resending can send duplicates to the recipient.

Conversely, updating `SUBMITTED` **before** sending SMTP and crashing afterward can leave the system claiming sent when no email was ever sent.

Therefore:

- `SUBMITTED` only reflects observed SMTP/provider response, not guaranteed Inbox delivery.
- When outcomes are ambiguous, use `UNKNOWN` status and reconciliation workflows.
- Automatic retries should only run for appropriately classified errors.
- If the provider offers an idempotency API, use it per provider contract; plain SMTP has no universal idempotency key across all servers.

An outbox prevents losing **send requests** after commit, yet does not turn SMTP into exactly-once delivery.

## 15. Task Exceptions Do Not Roll Back the Caller

Example:

```java
@Transactional
public void updateAccount(Account account) {
    accountRepository.save(account);
    asyncMailService.sendWelcome(account.getEmail());
}
```

If `sendWelcome` truly runs asynchronously, the caller has usually already moved on without knowing whether SMTP failed. Worker errors after commit cannot roll back `updateAccount()`'s transaction.

For methods returning `void`, an `AsyncUncaughtExceptionHandler` helps observe errors:

```java
@Configuration
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            // Log by notification ID/correlation ID, do not log PII.
        };
    }
}
```

For methods returning `CompletableFuture`, callers can register exception-handling callbacks:

```java
CompletableFuture<Void> future =
        asyncMailService.sendWelcome(data);

future.whenComplete((result, error) -> {
    if (error != null) {
        // Record error or trigger handling workflow.
    }
});
```

Yet `CompletableFuture` only holds results in process memory; it does not replace durable notification/outbox records. Do not wait on `future.join()` directly inside an HTTP request if the goal is reducing response times.

### Distinguishing Two Exception Types

- **Dispatch exception:** executor rejects the task; can surface in the caller immediately upon submission.
- **Execution exception:** error occurring while the worker runs; usually handled via futures/handlers or notification statuses.

The two error types have different timings and transaction impacts. If the business transaction already committed and the executor rejects dispatch in an after-commit callback, there is no automatic rollback; this is why critical emails need a durable outbox.

## 16. Do Not Pass Managed Entities Across Threads

Another bug comes from JPA rather than SMTP:

```java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.confirm();
    asyncMailService.sendConfirmation(order);
}
```

Inside the worker:

```java
@Async("mailExecutor")
public void sendConfirmation(Order order) {
    String name = order.getCustomer().getDisplayName();
    // Lazy relation may no longer have a valid persistence context.
}
```

Do not pass a JPA entity still tied to the calling thread's persistence context to a worker. Risks include:

- `LazyInitializationException` when accessing lazy data.
- Worker seeing uncommitted in-memory object state.
- Mutable objects changing while the worker reads them.
- Mistakenly assuming the entity remains managed by the caller's transaction.

Two clearer choices:

1. Build an **immutable DTO** containing required fields while inside the business transaction, and store the DTO/snapshot in the outbox.
2. Pass an **ID** and let the worker re-query in its own read transaction **after data has committed**.

### Immutable DTO Example

```java
public record OrderConfirmedMailData(
        UUID orderId,
        String recipient,
        String recipientName,
        String orderCode,
        String amountLabel
) {}
```

The DTO describes data crossing the thread boundary. If underlying data can change after commit, decide whether the email must reflect the **snapshot at the business event time** or the **latest state** when the worker runs.

For example, price confirmation emails should usually use the committed snapshot matching the event rather than reading a total that may have changed while waiting.

## 17. Context Propagation Is Not Transaction Propagation

An application may need to carry across to workers:

- Correlation IDs and MDC for logging.
- Tenant IDs.
- Locales and timezones.
- Trace/span contexts.
- Controlled security metadata.

These contexts can be propagated via DTOs, `TaskDecorator`, or appropriate context propagation integrations. However, **never confuse propagating MDC/SecurityContext with propagating a transaction**.

Example `TaskDecorator` for MDC:

```java
public final class MailMdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
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
```

Register with the executor:

```java
executor.setTaskDecorator(new MailMdcTaskDecorator());
```

This decorator aids log correlation; it **does not** move transactions/JDBC connections from the HTTP thread to the mail worker.

For business emails, do not rely on request-scoped objects or live SecurityContexts on other threads. Verify permissions when creating the notification and persist required values; workers process under established authorization and their own policies.

## 18. Executor Configuration and When Tasks Start

A dedicated executor caps concurrent sending tasks:

```java
@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

`@Async("mailExecutor")` selects the executor. Yet even with a queue, **you cannot rely on queue wait times to guarantee the caller's transaction committed**. If the executor is idle at that moment, the task can run immediately; if overloaded, it can run late or be rejected.

If the queue is full:

- `AbortPolicy` throws when rejecting the task.
- `CallerRunsPolicy` can run the task right on the calling thread, making requests wait and breaking the “always runs on another thread” assumption under overload.
- Discard policies can silently drop emails undetected.

For critical notifications, save work to the database **before** handing off to the executor. The executor is an execution tool, not a reliable data store for recovering tasks.

## 19. When Multiple Instances or Multiple Workers Exist

A database outbox can be read by multiple workers concurrently. If workers A and B both grab a `PENDING` notification and send it, duplicate emails can be sent.

Therefore you need:

- Atomic claiming via row locks/conditional updates.
- Leases to track worker ownership.
- Claim tokens or fencing tokens when recording outcomes.
- Never holding DB locks across SMTP I/O.
- Careful handling of expired `PROCESSING` notifications, because SMTP may have accepted the message before the worker died.

```text
Worker A -> claims notification N-123, token T1
Worker B -> cannot claim N-123

If A dies:
  lease expires -> reconciliation / recovery policy
  new worker can acquire token T2

When A is alive yet slow:
  update with T1 must be rejected if current token is already T2
```

This reduces state contention. It still does not eliminate the possibility that SMTP already received the message before the worker died.

## 20. Designing Retries and Idempotency in Async Mail

Reprocessing a notification can occur due to:

- Clients resending HTTP requests.
- Event brokers redelivering messages.
- Workers retrying after transient failures.
- Process restarts after sending mail yet before saving status.

To minimize duplicates:

1. Assign a stable `notificationId` per send event.
2. Enforce a unique constraint by business event when policy allows one notification per event.
3. Never create a new notification on each worker retry.
4. Use claims/leases so multiple workers do not send concurrently.
5. Persist attempt counts and send statuses.
6. For ambiguous outcomes, handle `UNKNOWN` and reconciliation rather than blind retries.

MIME **`Message-ID`** is not an idempotency key honored by every SMTP server to prevent duplicates. If the provider offers an official idempotency API, supply a notification key per the provider's contract.

### Distinguishing Retry and Resend

- **Retry:** re-attempting an existing notification, usually due to technical errors.
- **Resend:** an intentional new business action, such as a user requesting an invoice again.

A resend can create a new notification linked to the original one, but must not be conflated with technical retries.

## 21. What Should Notification Statuses Represent?

A minimal state machine:

```text
PENDING
   |
   v
PROCESSING
   |
   +-- accepted ----------> SUBMITTED
   |
   +-- retryable error ---> RETRY_WAIT ---> PROCESSING
   |
   +-- permanent error --> FAILED
   |
   +-- ambiguous result -> UNKNOWN
                              |
                              v
                         reconcile
```

| Status | Meaning |
| --- | --- |
| `PENDING` | Notification committed, waiting for a worker |
| `PROCESSING` | Claimed by a worker and currently processing |
| `SUBMITTED` | SMTP/provider accepted the message per observed response |
| `RETRY_WAIT` | Waiting for next retry timestamp after eligible failure |
| `FAILED` | No further sending per policy or permanent error |
| `UNKNOWN` | Uncertain whether SMTP/provider received the message |

Do not name `SUBMITTED` as `DELIVERED` solely from a successful `JavaMailSender.send(...)` call. Delivery, bounces, or spam filtering can occur afterward and are tracked via provider events when available.

## 22. Spring Mail Example Sending Messages Outside DB Transactions

The mail composer only builds the message; it does not need to open a DB transaction to call SMTP:

```java
@Component
public class MailComposer {

    private final JavaMailSender mailSender;

    public MailComposer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage compose(ClaimedMail item)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(item.recipient());
        helper.setSubject("Order confirmation " + item.orderCode());

        String plain = "Order " + item.orderCode()
                + " has been confirmed.";
        String html = "<p>Order <strong>"
                + escapeHtml(item.orderCode())
                + "</strong> has been confirmed.</p>";

        helper.setText(plain, html);
        return message;
    }
}
```

`escapeHtml(...)` in the example represents application-provided HTML escaping. In real applications, use a template engine such as Thymeleaf and `th:text` for dynamic data. The From address must belong to a domain authorized by the provider.

A worker calls the composer and sender **after claiming the notification**, yet outside the claim transaction:

```java
ClaimedMail item = claimService.claimOne();
if (item != null) {
    MimeMessage message = composer.compose(item);
    mailSender.send(message);
    outcomeService.submitted(item.id(), item.claimToken());
}
```

This short snippet only illustrates boundaries; production implementations must catch render/SMTP errors, persist status, and handle ambiguous outcomes. Never add `@Transactional` around the whole block just for convenience updating status.

## 23. Testing Transaction and Task Boundaries

To validate the design, test out-of-order schedules and real failure scenarios.

### Test A — Task Starts Before Commit

Keep a transaction open; let the worker run immediately and attempt to read new data. Verify the design does not depend on workers seeing uncommitted data. If committed data is needed, use after-commit coordination or an outbox.

### Test B — Business Rollback

In the business service, throw an exception causing TX rollback after scheduling an email intent.

**Expected with outbox:** no notification commits and no worker processes an email for the rolled-back event.

### Test C — Business Commit Followed by Application Crash

After committing the outbox, stop the process before the worker processes it.

**Expected:** the notification remains in the database; when workers restart, work can be claimed and sent per policy.

### Test D — Email Sent Yet Status Update Fails

Simulate SMTP accepting the message while the worker fails to record `SUBMITTED`.

**Expected:** the system does not assume with certainty the email was not sent. Record/recover `UNKNOWN` outcome or reconcile with the provider before retrying.

### Test E — Two Workers Running Concurrently

Have two workers claim the same notification simultaneously.

**Expected:** only one worker acquires a valid claim at a time; status updates must verify the claim token.

### Test F — Self-Invocation

Call an `@Async` method from another method on the same object rather than through a Spring proxy.

**Expected:** confirm the annotation is not intercepted under default proxy mode; fix architecture by calling through a separate bean.

### Test G — AFTER_COMMIT Without a Transaction

Publish an event when no transaction is active while using `@TransactionalEventListener` with default settings.

**Expected:** the transaction-bound listener is not invoked; explicitly define policy rather than assuming emails will always be sent.

### Test H — Executor Rejects Task

Fill the thread pool and queue, then dispatch mail.

**Expected:** error logs/status appear or the outbox preserves the work; notifications are never silently lost.

## 24. How to Investigate When Logs Show “Transaction Still Active”

Sometimes logs mislead developers into thinking tasks share the same transaction because:

- Both threads print the same business ID or trace ID.
- The worker started while the caller had not yet committed.
- Both methods carry `@Transactional`.
- Logs show “transaction active” on the worker.
- An in-memory entity still holds newly modified values.

None of these prove two threads share **the same database transaction**.

When investigating, log:

| Information | Purpose |
| --- | --- |
| Thread name/ID | Identify which thread ran the call |
| Notification ID | Link business event to worker |
| Transaction start/commit/rollback | Determine ordering between caller and worker |
| Order/business ID | Correlate data |
| Timestamp/attempt | Distinguish processing attempts |
| Worker claim token | Verify authority to update status |
| Provider message ID | Reconcile with SMTP/provider if available |

In applications using imperative transaction managers, `TransactionSynchronizationManager.isActualTransactionActive()` indicates whether the current thread has an active Spring-managed transaction. Yet returning `true` on a worker only shows **the worker has a transaction**, not that it is the caller's transaction.

Do not use thread-local status checks as a synchronization mechanism in place of outbox/after-commit logic.

## 25. Comparing Implementation Approaches

| Approach | Guaranteed Post-Commit Run? | Survives Crashes? | Suitability |
| --- | --- | --- | --- |
| Calling `@Async` directly inside `@Transactional` | No | No, if only in executor memory | Avoid for commit-dependent emails |
| `@TransactionalEventListener(AFTER_COMMIT)` then `@Async` | Yes, when event is transaction-bound and listener runs | Not automatically guaranteed | Low-importance notices where task loss is acceptable |
| Writing notification in business TX, polling worker | Worker sees only committed rows with proper DB reads | Yes, if database is durable | Transactional emails needing reliability |
| Transactional outbox + message broker | Yes, if publisher reads only committed outbox rows | Per storage/broker configuration | Multi-service systems, high throughput |
| Sending SMTP directly inside `@Transactional` | Not decoupled from request; SMTP does not roll back with DB | Does not solve atomicity | Only when explicit limits are acceptable |

**Selection rule:** transaction boundaries are dictated by business consistency requirements; task boundaries are dictated by latency, concurrency, and durability. Never use `@Async` to solve requirements that actually call for an outbox.

## 26. Common Mistakes and Fixes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Worker cannot find newly inserted order | Caller TX not committed yet | Wait until after commit or read notification from outbox |
| Email sent despite business rollback | Task dispatched before commit | Write send request in same DB transaction |
| `@Async` runs synchronously | Self-invocation or async not enabled | Call via separate bean/proxy, configure `@EnableAsync` |
| Worker has a transaction yet reads stale data | Separate TX with different timing/isolation | Review commit timing and input data |
| Mail failure does not roll back API | Task failed after business commit | Record separate status, retry/reconcile |
| `AFTER_COMMIT` listener never runs | Event published outside TX or listener/config mismatch | Verify transaction-bound events and fallback policy |
| DB write inside `AFTER_COMMIT` not persisted as expected | Used closing transaction resources without a new TX | Call `REQUIRES_NEW` service or use outbox |
| Mail lost after restart | Work lived only in executor memory | Persistent notification/outbox/broker |
| Multiple workers send duplicates | Non-atomic claim or improper lease handling | Row locks/atomic claims, fencing tokens, idempotency |
| SMTP timeout then duplicate sends | Blind retries on ambiguous outcomes | `UNKNOWN` and provider reconciliation |
| DB locks held too long | Wrapping SMTP I/O in `@Transactional` | Split claim/send/status into separate steps |
| API reports `SENT` right after submitting task | Confusing executor acceptance with SMTP submission | Return `PENDING` and track outcomes |
| Task fails reading lazy JPA relations | Entity/persistence context no longer valid | Pass DTO snapshot or re-query after commit |
| Same trace ID mistaken for same TX | Correlation ID propagated | Distinguish trace context from transaction context |

## 27. Practice Scenarios

### Scenario 1 — Welcome Email from Account Creation Service

`createAccount()` is marked `@Transactional`. Right after `repository.save(account)`, the service calls `@Async sendWelcome(account.getId())`. Occasionally the worker cannot find the newly created account.

**Explanation:** the worker queries using its own transaction/connection before the account-creation TX commits. There is no guarantee a worker sees uncommitted data.

**Resolution:** use an after-commit event if task loss is acceptable, or persist a welcome notification/outbox row in the same transaction for the worker to process after commit.

### Scenario 2 — SMTP Reports Success Then Database Rolls Back

`confirmOrder()` calls synchronous mail sending inside the transaction, then a subsequent database statement fails. The mail server already accepted the email yet the TX rolls back.

**Explanation:** SMTP does not participate in database transactions. Rollback does not recall messages.

**Resolution:** write the send request to an outbox in the business TX and send after commit.

### Scenario 3 — Adding @Transactional to sendAsync()

A developer adds `@Transactional` to an `@Async` method assuming the worker will use the request's transaction.

**Explanation:** the task executes on a separate thread; transaction annotations applied inside the worker create/manage a separate transaction rather than “continuing” the caller's TX.

**Resolution:** decide what the worker transaction should do (read/write DB), never using it to replace after-commit/outbox coordination.

### Scenario 4 — Using AFTER_COMMIT Yet Still Losing Mail

Database commit succeeds. The process crashes right before the listener dispatches the task.

**Explanation:** application events and executors do not automatically create persistent records.

**Resolution:** transactional outbox with committed `PENDING` notifications.

### Scenario 5 — Resending After SMTP Timeout

The worker sent the message yet lost the connection before receiving the final SMTP response. The worker does not know if the server received it.

**Explanation:** transport outcome can be ambiguous and is unrelated to the caller's DB transaction.

**Resolution:** record `UNKNOWN`, reconcile with the provider if available, then apply a retry policy weighing duplicate risk.

### Scenario 6 — Three Instances All Running Mail Schedulers

Each instance reads `PENDING` notifications from the same database and sends them.

**Explanation:** multiple independent workers exist; each worker's separate transaction does not prevent duplicates if they read the same row.

**Resolution:** atomic claims with row locks/unique status transitions and claim tokens, without holding transactions open while sending via SMTP.

## 28. Principles to Remember

1. **Transactions belong to managed execution scopes, not automatically to “business intent”.**
2. **`@Async` does not wait for commit and does not inherit the caller's imperative transaction.**
3. **`@Transactional` on a worker creates a separate transaction scope; `REQUIRES_NEW` does not carry the old TX across threads either.**
4. **SMTP does not roll back with the database.** Sending email inside a transaction does not create cross-system atomicity.
5. **Separate claim, send, and status update.** Keep DB transactions short; never wrap long network I/O.
6. **Use `AFTER_COMMIT` when only timing matters and in-memory event limits are acceptable.**
7. **Use a transactional outbox when send requests must never be lost after commit.**
8. **Never pass JPA entities or transaction contexts across workers;** prefer DTO snapshots or IDs with separate read transactions.
9. **Record statuses honestly:** `PENDING` differs from `SUBMITTED`, `SUBMITTED` differs from `DELIVERED`, and timeouts may be `UNKNOWN`.
10. **Test varying execution schedules and failure points** to avoid relying on lucky timing.

## 29. Conclusion

When email sending is offloaded to an asynchronous task, the business thread's transaction **does not extend across the task**. Workers have their own execution lifecycles and database transactions; they can start before the caller commits. Consequently, merely adding `@Async` or `@Transactional` is insufficient to guarantee emails are sent after commit without getting lost.

For low-importance notifications, `@TransactionalEventListener(AFTER_COMMIT)` combined with an `@Async` service can be a clean solution if in-memory task risks are acceptable. For emails tied to critical business flows, persist the notification/outbox row in the same transaction as the data change, and let workers read committed work. Workers claim in a short transaction, send over SMTP outside transactions, and record outcomes in another transaction. This design clarifies commit boundaries, avoids mistaking transactions as bridging threads, and enables controlled recovery, retries, and investigation of email-sending errors.
