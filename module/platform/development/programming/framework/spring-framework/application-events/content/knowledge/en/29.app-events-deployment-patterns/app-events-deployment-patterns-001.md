# Email Notification After Order Creation with Spring Framework Application Events

## 1. The Problem and Target Outcomes

In the **Deployment Patterns** group of **Spring Framework Application Events**, a common scenario is: a user successfully places an order, and the application needs to send a confirmation email. If email handling is performed directly inside the order placement logic, you can easily end up slowing down the request due to SMTP/HTTP calls, sending an email for an order that was just rolled back, or letting an email failure break the entire workflow that already made other changes.

A sound design must answer **two independent questions**:

1. **When is it allowed to send the email?** Typically, after the order data has been **committed successfully** and the recipient/content has been determined according to policy.
2. **If sending the email can fail, how do we recover?** Can best-effort notification be accepted, or do we need a durable record, retries, duplicate limits, and alerting?

With Spring Application Events, the simple option is to publish an `OrderCreatedEvent` from the order-creation service and handle it via `@TransactionalEventListener(phase = AFTER_COMMIT)`. When requirements are stricter, the same **business fact** should be recorded as a durable outbox/job within the transaction, and a worker handles email delivery with retry/idempotency.

Goals of this guide:
- Build an **order creation → commit → email notification** flow with clear boundaries.
- Understand `@EventListener`, `@TransactionalEventListener`, `@Async`, and the limitations of each mechanism.
- Design an immutable event payload containing only the necessary data.
- Run a Java 17+ example using Spring Context, Spring JDBC, H2, and a fake mail gateway, verifying commit/rollback behavior.
- Learn how to integrate `JavaMailSender`/SMTP in Spring Boot at the integration level.
- Design outbox, idempotency, retry, duplicate prevention, logging, and testing.

**Important note:** "Event published" does not equate to "email sent successfully." Even `@TransactionalEventListener(AFTER_COMMIT)` is **not** a guarantee of durable delivery across crashes/restarts.

## 2. Three States That Must Not Be Equated

Let us distinguish three milestones:

```text
HTTP POST /orders
      |
      v
PlaceOrderService
      |
      +--> Check permissions, inventory, pricing, and customer data
      +--> INSERT orders, order_items inside transaction
      +--> publishEvent(OrderCreatedEvent)
      |
      v
Transaction COMMITS successfully
      |
      v
@TransactionalEventListener(AFTER_COMMIT)
      |
      +--> Prepare email and call mail gateway
      |
      v
Mail provider ACCEPTED / ERROR
      |
      v
Recipient actually receives email (not always immediately observable)
```

There are at least three kinds of "success":

| State | Meaning | Does Not Prove |
| --- | --- | --- |
| **ORDER_COMMITTED** | The order has been saved in the DB by the business transaction | The email has been accepted by the provider |
| **EMAIL_SUBMITTED** | The application has called the sender or placed a job in the queue | SMTP/provider has accepted or sent it out |
| **EMAIL_ACCEPTED** | SMTP/provider reports accepting the send request | The message reached the inbox, was read, or was not filtered as spam |

In real-world systems, **provider accepted** and **delivered** are two different outcomes. An HTTP 202 from an email API usually only means the provider has received the job. If you want to track delivery/bounces, you need a webhook/status API, webhook verification, and a separate lifecycle store.

Do not take `publishEvent()` latency as the email sending duration when the handler runs asynchronously. Do not use a "send requested" log line to claim the user has received the message.

## 3. Order and Event Payload Design

In a business application, placing an order is a **command**, whereas `OrderCreatedEvent` expresses a **fact** accepted by the service:

```java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String recipientEmail,
    String customerDisplayName,
    String correlationId
) {}
```

This is an **illustrative record**, not a standalone file. Fields to consider:

- `eventId`: identifier of a logical event, stable if that exact event is retried/replayed.
- `orderId`: identifier of the order, used to build the email template and link to the order page.
- `recipientEmail`: recipient address selected/verified according to policy; it can be omitted from the event if this data must be queried at send time.
- `customerDisplayName`: minimal display information; no need for the entire `CustomerEntity`.
- `correlationId`: links logs/requests/event flows; do not use it as an idempotency key across multiple events.

**Do not put a JPA managed entity directly into an event**: entities are mutable, have lazy associations, are bound to a persistence context, and can expose sensitive data. A `record` only makes field references immutable; if a field is a mutable `List` or mutable object, you still must copy/snapshot it.

### Should the Email Address Be Snapshotted or Re-Queried?

There are two valid designs, depending on business requirements:

1. **Snapshot in the event/outbox:** the order is confirmed to the email approved by the user at the time of ordering. Useful when consistent history/replay is needed; PII in the payload, outbox, and logs must be protected.
2. **ID-only then reload:** the event carries only `orderId`; the worker queries the current email per policy, suitable if the latest address must be used. However, an order might be modified/deleted or the tenant may have changed; the business contract must be clearly defined.

Do not arbitrarily use an unvalidated email from the request body. The application service must obtain the authenticated principal, verify permissions for the order/tenant, and select a valid recipient address before creating the fact.

### One Event Can Have Multiple Listeners

```text
OrderCreatedEvent
   |
   +--> AuditListener
   +--> InventoryProjectionListener
   +--> EmailConfirmationListener
   +--> AnalyticsListener
```

Each listener has its own responsibility. **A failure in the email-sending listener should not automatically cause duplicate emails because the entire order-creation command is retried.** If the event is retried, other listeners may also be invoked again and need their own idempotency. For critical workflows, track outcomes per consumer/handler or create a separate durable job for email.

## 4. Plain @EventListener vs. @TransactionalEventListener(AFTER_COMMIT)

### 4.1. Synchronous @EventListener: Easy to Send Before Commit

A plain listener:

```java
@Component
public class EmailConfirmationListener {
    private final MailGateway mail;

    public EmailConfirmationListener(MailGateway mail) {
        this.mail = mail;
    }

    @EventListener
    public void on(OrderCreatedEvent event) {
        mail.sendConfirmation(event.orderId(), event.recipientEmail());
    }
}
```

This is **integration code**, requiring `MailGateway`, imports, and other configuration. With the default `SimpleApplicationEventMulticaster`, a synchronous listener runs immediately on the thread calling `publishEvent`. If the publisher is inside `@Transactional`, the email may be sent **before the transaction commits**. Later the database rolls back, yet the email has already gone out, resulting in a confirmation email for a nonexistent order.

External SMTP/providers do not participate in the DB transaction by default. A `@Transactional` around the service cannot "roll back an email."

### 4.2. @TransactionalEventListener(AFTER_COMMIT)

For the email listener, use:

```java
@Component
public class EmailConfirmationListener {
    private final MailGateway mail;

    public EmailConfirmationListener(MailGateway mail) {
        this.mail = mail;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCreatedEvent event) {
        mail.sendConfirmation(event.orderId(), event.recipientEmail());
    }
}
```

This is still **integration code**, not a complete file. The listener is registered to be called back when the current transaction **commits successfully**. As of Spring Framework 6.1, the default phase is `AFTER_COMMIT`; declaring it explicitly improves readability.

| Scenario | Synchronous `@EventListener` | `@TransactionalEventListener(AFTER_COMMIT)` |
| --- | --- | --- |
| Published inside transaction, then committed | Usually handled immediately upon publish | Runs callback after successful commit |
| Published inside transaction, then rolled back | Email may already have been sent | Does not run `AFTER_COMMIT` callback |
| Published outside transaction | Still invoked by multicaster | By default **not invoked** |
| Process crashes right after commit | May or may not have sent | Callback can still be **lost** |
| SMTP/provider error | May affect transaction/publisher depending on timing | Original DB is already committed; email error must be handled independently |
| Event is durably persisted | Not automatic | Not automatic |

**`fallbackExecution=false` is the default.** If there is no corresponding transaction, `@TransactionalEventListener` normally ignores the event. You can enable `fallbackExecution=true`, but doing so changes the "send only after commit" contract; do not enable it just because a test fails to trigger the listener.

### 4.3. AFTER_COMMIT Does Not Automatically Run on Another Thread

The `AFTER_COMMIT` callback may run **on the thread completing the transaction**, because it is a phase callback, not a synonym for async. If you make a blocking SMTP call directly in the callback, the request can still be delayed while the transaction commit returns to the caller.

To decouple I/O wait time, you can offload email processing to an executor or durable worker. However, `@Async` alone only switches threads; it provides no persistence or durable retry. You must weigh speed vs. reliability tradeoffs based on how critical the email is.

### 4.4. The Old Transaction Does Not Serve New Writes After Commit

An `AFTER_COMMIT` callback may be invoked when the previous transaction's resources have not yet been completely cleaned up. If the listener needs to create an `EmailDelivery` record in the DB after commit, it must open an appropriate **new transaction**, for example via a method on a Spring bean proxy annotated with `@Transactional(propagation = REQUIRES_NEW)`. Do not assume DB writes in the callback are committed as part of the source transaction that has already completed.

This is also why the outbox record is inserted **inside the order-creation transaction**, rather than waiting until `AFTER_COMMIT` to write the outbox record: if the process dies between commit and the callback, the intent to send the email may never have been saved.

## 5. Runnable Java 17+ Example: Order Creation, Commit, Rollback, and Fake Email Sender

The following demo verifies precisely:
- There is an in-memory H2 database and an `orders` table.
- `OrderService` uses Spring `TransactionTemplate` to save the order and publish `OrderCreatedEvent` inside the transaction.
- `OrderEmailListener` uses `@TransactionalEventListener(AFTER_COMMIT)`.
- `RecordingMailer` replaces real SMTP with a fake sender; the program **sends no external emails**.
- Order `ORD-1` commits, so one fake email is recorded.
- Order `ORD-2` rolls back, so no email is sent.
- An event published outside a transaction is ignored by the default transaction-bound listener.

The demo does not use Spring Boot or an HTTP server; this lets us focus on Spring Context + Spring Transaction behavior. It **does not prove durable email delivery across restarts**, because the fake mailer uses RAM.

### 5.1. Structure

```text
order-created-email-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/OrderCreatedEmailDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'order-created-email-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.springframework:spring-jdbc:6.1.21'
    implementation 'org.springframework:spring-tx:6.1.21'
    implementation 'com.h2database:h2:2.2.224'
}

application {
    mainClass = 'demo.OrderCreatedEmailDemo'
}
```

Running this requires JDK 17+ and Gradle with access to download dependencies from Maven Central. H2 here is strictly for demo purposes and does not replace a production RDBMS.

### 5.2. Complete Java File

`src/main/java/demo/OrderCreatedEmailDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class OrderCreatedEmailDemo {

    public record OrderCreatedEvent(
            String eventId, String orderId, String recipientEmail) {}

    public static final class RecordingMailer {
        private final List<String> deliveries = new ArrayList<>();

        public void sendConfirmation(
                String orderId, String recipientEmail) {
            deliveries.add(orderId + "|" + recipientEmail);
            System.out.println(
                "EMAIL_SENT order=" + orderId + " to=" + recipientEmail
            );
        }

        public int count() {
            return deliveries.size();
        }
    }

    public static final class OrderService {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transactions;
        private final ApplicationEventPublisher events;

        public OrderService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events) {
            this.jdbc = jdbc;
            this.transactions = transactions;
            this.events = events;
        }

        public void create(
                String orderId, String email, boolean rollback) {
            transactions.executeWithoutResult(status -> {
                jdbc.update(
                    "INSERT INTO orders (id, email) VALUES (?, ?)",
                    orderId, email
                );

                events.publishEvent(new OrderCreatedEvent(
                    "EVT-" + orderId, orderId, email
                ));

                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    public static final class OrderEmailListener {
        private final RecordingMailer mailer;

        public OrderEmailListener(RecordingMailer mailer) {
            this.mailer = mailer;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onOrderCreated(OrderCreatedEvent event) {
            mailer.sendConfirmation(
                event.orderId(), event.recipientEmail()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds =
                new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:orders_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        public RecordingMailer recordingMailer() {
            return new RecordingMailer();
        }

        @Bean
        public OrderEmailListener orderEmailListener(
                RecordingMailer mailer) {
            return new OrderEmailListener(mailer);
        }

        @Bean
        public OrderService orderService(
                JdbcTemplate jdbc,
                TransactionTemplate transactions,
                ApplicationEventPublisher events) {
            return new OrderService(jdbc, transactions, events);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            OrderService orders = context.getBean(OrderService.class);
            RecordingMailer mailer =
                context.getBean(RecordingMailer.class);

            jdbc.execute(
                "CREATE TABLE orders (" +
                "id VARCHAR(40) PRIMARY KEY, " +
                "email VARCHAR(200) NOT NULL)"
            );

            // 1. Commit: AFTER_COMMIT callback runs.
            orders.create("ORD-1", "alice@example.test", false);

            // 2. Rollback: AFTER_COMMIT callback does not run.
            orders.create("ORD-2", "bob@example.test", true);

            // 3. No transaction: fallbackExecution=false.
            context.publishEvent(new OrderCreatedEvent(
                "EVT-ORPHAN", "ORD-X", "nobody@example.test"
            ));

            int persistedOrders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders",
                Integer.class
            );
            System.out.println("ORDERS_COMMITTED=" + persistedOrders);
            System.out.println("EMAILS_SENT=" + mailer.count());
        }
    }
}
```

Run:

```bash
gradle run --quiet
```

**Expected business stdout** (ignore any extra Gradle/logging notices if present):

```text
EMAIL_SENT order=ORD-1 to=alice@example.test
ORDERS_COMMITTED=1
EMAILS_SENT=1
```

### 5.3. Why This Output Is Correct

1. `AnnotationConfigApplicationContext(Config.class)` creates the `TransactionTemplate`, `JdbcTemplate`, `OrderService`, and listener beans. Spring registers `@TransactionalEventListener` through the context's event listener infrastructure.
2. `orders.create("ORD-1", ...)` opens a transaction using `TransactionTemplate`, inserts a row, and publishes `OrderCreatedEvent` while the transaction is active. The transaction-bound callback is registered, **without sending the email immediately at publish time**.
3. The first transaction commits, and then the `AFTER_COMMIT` callback calls `RecordingMailer` synchronously. The fake mailer prints the `EMAIL_SENT` line and records an entry in RAM.
4. `orders.create("ORD-2", ..., true)` inserts and publishes inside the second transaction, then calls `status.setRollbackOnly()`. The DB rolls back, and the `AFTER_COMMIT` listener does not run for the second event.
5. Another `OrderCreatedEvent` is published **outside any transaction**. With the default `fallbackExecution=false`, this listener is not invoked.
6. Querying the `orders` table leaves only `ORD-1`; the fake mailer has only one delivery. The final two lines are `ORDERS_COMMITTED=1` and `EMAILS_SENT=1`.
7. There is no executor; the listener runs synchronously during the commit phase. If the fake mailer were replaced with real SMTP, the commit callback duration could still make the caller wait even though the DB data has already committed.
8. To avoid misinterpreting the name `EMAIL_SENT`, this is merely **the fake mailer's log**. It does not assert that an email reached a real inbox and does not prove crash recovery.

**Why use TransactionTemplate instead of @Transactional in the demo?** It creates a real transaction without relying on AOP method proxies. In typical Spring Boot/service applications, `@Transactional` on a public service method invoked through a Spring proxy is common, but can easily be bypassed due to self-invocation if called internally via `this.method()`. Using the template makes the commit/rollback mechanism explicit and independent of the web layer.

### 5.4. The Program Has No Security or Real Email Yet

The addresses `alice@example.test` and `bob@example.test` are dummy data to avoid accidentally sending to real people. The demo does not authenticate users, verify ownership/order amounts, or send real emails. In production, you must add authorization, input validation, real order/item creation transactions, data classification, template versioning, sender identity, monitoring, and recovery.

`RecordingMailer` uses a non-thread-safe `ArrayList`; this is fine because the demo runs synchronously on a single thread. If you switch to `@Async` or a multi-worker executor, the test fake needs a synchronized collection and a completion signal, rather than reading the count immediately after publish.

## 6. Integrating JavaMailSender or an Email Provider

With **Spring Boot** and SMTP, you typically use `spring-boot-starter-mail` and inject `JavaMailSender`. A simple adapter for plain-text email:

```java
@Component
public final class SmtpOrderMailGateway {
    private final JavaMailSender mailSender;

    public SmtpOrderMailGateway(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String orderId, String recipientEmail) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("orders@example.com");
        message.setTo(recipientEmail);
        message.setSubject("Order confirmation " + orderId);
        message.setText(
            "Order " + orderId +
            " has been recorded. Please view details in your account."
        );
        mailSender.send(message);
    }
}
```

This is an **integration snippet, not a standalone file**. It requires the Spring Boot Mail dependency, imports `org.springframework.mail.javamail.JavaMailSender`, `org.springframework.mail.SimpleMailMessage`, `@Component`, SMTP configuration, and a sender address verified with the email provider. The address `orders@example.com` is illustrative only; do not assume that domain can send mail.

**Reference** configuration example for Spring Boot (never put passwords in source control):

```yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: "orders-service"
    password: "\${SMTP_PASSWORD}"
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
```

This configuration is a **reference template**. The SMTP host/username are infrastructure placeholders, not a working server. In a real application, supply credentials via a secrets manager or environment variables, enable TLS per provider policy, and verify the `From` domain/SMTP relay permissions. Do not log usernames/passwords, full mail bodies, or tokens.

### HTML Email and Templates

If HTML email is needed, use `MimeMessage`, `MimeMessageHelper`, and a configured template engine such as Thymeleaf/Freemarker. HTML email risks unsafe content injection if `customerDisplayName` or user data is placed directly into templates without escaping. You should:
- Escape dynamic data according to HTML context.
- Only use HTTPS links to canonicalized domains; do not build arbitrary links from an untrusted `Host` header.
- Do not include unnecessary sensitive information in the subject/body.
- Define locale, timezone, currency, and template version.
- Test rendering with Unicode characters, long names, and internationalized emails if the product supports them.

If sending via an email provider HTTP API, the adapter makes HTTP calls instead of SMTP, but **ambiguous failures after timeout, retry/idempotency, and accepted/delivered status remain the same problem**.

## 7. Does @Async Solve Slow Email Sending?

Integration configuration example:

```java
@Configuration
@EnableAsync
public class EmailAsyncConfig {
    @Bean(name = "emailExecutor")
    public ThreadPoolTaskExecutor emailExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("email-worker-");
        return executor;
    }
}
```

A method that can execute on the executor:

```java
@Service
public class EmailBackgroundService {
    @Async("emailExecutor")
    public void sendAsync(OrderCreatedEvent event) {
        mailGateway.sendConfirmation(
            event.orderId(), event.recipientEmail()
        );
    }
}
```

These are **two integration snippets**, requiring imports, `@EnableAsync`, the `mailGateway` bean, method execution through a Spring async proxy, and an appropriate error handler. You can have an `AFTER_COMMIT` listener call `EmailBackgroundService.sendAsync(...)`. That moves the blocking SMTP call off the thread completing the transaction, but:

- The executor queue usually lives in RAM; a process crash after commit before the task executes will lose the email.
- `@Async void` exceptions do not propagate back to the publisher automatically; you need `AsyncUncaughtExceptionHandler`, metrics/logging, and policy-driven retries.
- Submitting the task may succeed while the worker fails; "enqueued" is not "sent."
- A bounded queue can fill up, causing rejections. Do not configure an unbounded queue and ignore memory pressure.
- `SecurityContextHolder` and MDC are thread-bound in the imperative stack; context does not automatically propagate across the executor. Use explicit event metadata or properly configured context propagation.
- **Do not combine `@Async` and `@TransactionalEventListener` casually** assuming the transaction is carried over to the worker. The transaction synchronization listener must be registered in the proper context; the async task runs outside the source transaction.

### Solution Levels

| Approach | Avoids Sending Before Rollback? | Request Waits for I/O? | Email Intent Durable Across Restart? |
| --- | --- | --- | --- |
| Synchronous `@EventListener` inside transaction | Not guaranteed | Yes | No |
| Synchronous `@TransactionalEventListener(AFTER_COMMIT)` | Yes, per commit phase | May still wait | No |
| `AFTER_COMMIT` calling `@Async` | Yes, per commit phase | Usually does not wait for SMTP | No |
| Write outbox/job in transaction + worker | Yes | Usually no | **Yes**, if storage/worker/retry are properly designed and operated |

For critical order confirmation emails with a clear SLA where lost notifications are unacceptable, **an outbox or durable job** is the preferred design. A simple `@TransactionalEventListener` is still useful for best-effort tasks or to wake up the worker reading the outbox; the source of truth for what needs to be sent must reside in durable storage, not in an in-memory event object.

## 8. Production Deployment Pattern: Transactional Outbox for Email

### 8.1. The Order Placement Transaction Also Stores Email Intent

Inside the order-creation transaction, write:
1. `orders` and `order_items`.
2. An `outbox_events` or `email_jobs` record with `eventId`/`messageId`, `orderId`, recipient or queryable reference data, template key, and status `PENDING`.
3. Commit both together.

```text
@Transactional PlaceOrderService
      |
      +--> INSERT orders (...)
      +--> INSERT order_items (...)
      +--> INSERT email_jobs (
               job_id, order_id, template_key,
               recipient, payload, status='PENDING'
           )
      +--> COMMIT
               |
               v
      Email worker scans/claims PENDING
               |
               +--> send via provider
               +--> record provider response / status
               +--> ACK: mark SENT or retry
```

If the transaction rolls back, the email job rolls back too. If it commits and the JVM dies immediately, the job record remains in the DB and a worker can continue after restart.

### 8.2. Reference Schema

Conceptually neutral pseudo-SQL, to be adapted to your database:

```sql
CREATE TABLE email_jobs (
    job_id          VARCHAR(80) PRIMARY KEY,
    order_id        VARCHAR(80) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    template_version INTEGER NOT NULL,
    recipient       VARCHAR(320) NOT NULL,
    payload_json    TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error_code VARCHAR(100),
    provider_message_id VARCHAR(160),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
```

In production you will also need indexes on `(status, next_attempt_at)`, tenant scoping, retention, encryption/PII policies, optimistic locking/leases, and audit metadata. Both `recipient` and `payload_json` contain personal data and require appropriate access control and retention.

An important business rule: the same order should not create **two identical confirmation jobs** due to a command retry. You can use a unique constraint on `(order_id, notification_type, template_version)` if the business rule is truly **one confirmation email per version**. However, if an order can legitimately be re-confirmed under another workflow, that key must be redesigned. **Do not generate a new event ID for each retry of the same logical notification.**

### 8.3. Dispatcher Algorithm

Pseudo-code:

```text
loop until stopped:
    claim a bounded batch of due PENDING jobs with a lease
    for each job:
        validate template/schema and recipient policy
        try:
            provider.send(
                idempotencyKey = job.jobId,
                renderedMessage = render(job)
            )
            record provider acknowledgment
            mark job SENT
        catch retryable error:
            attempts += 1
            nextAttemptAt = now + exponentialBackoffWithJitter()
            status = PENDING
        catch permanent error:
            status = FAILED or NEEDS_REVIEW
            emit alert/operational event
    release/renew lease as needed
```

This is an **illustrative algorithm**, not a standalone runnable script. Keep in mind:
- Claim using appropriate row locking/leases, such as `SELECT ... FOR UPDATE SKIP LOCKED` on supported databases.
- Do not hold a DB transaction open across a long SMTP request unless there is a clear reason.
- Leases expire if a worker dies so another instance can pick up the job.
- Retries have capped backoff, jitter, and transient vs. permanent error classification.
- Metrics separate `pending`, `inflight`, `sent`, `failed`, and `oldest pending age`.
- When sending via an API supporting idempotency keys, pass the **same key** across all retries.
- Mark `SENT` only after receiving the designated acknowledgment milestone; if the ACK is lost, the job will be retried.

### 8.4. Why Duplicate Emails Can Still Happen

Failure window:

```text
Worker sends email to provider --> provider accepts
                               |
                               X process crashes before marking SENT
                               |
                               v
                 Another worker sees PENDING and resends
```

The outbox prevents **losing intent**, but the sender may retry **at least once**, leading to duplicates if the provider does not support key-based idempotency. Do not claim "exactly once email" merely because you use an outbox.

Ways to reduce duplicates:
- Provider supports idempotency keys: use a stable `jobId`; understand the provider's TTL/semantics policy.
- When status is unknown (timeout after the provider may have received it), query the provider by external reference if available.
- Put unique constraints in the DB so one command cannot create multiple logical jobs.
- Retain provider message IDs and webhook events for reconciliation.
- For external APIs without reliable deduplication, document the duplicate possibility and have an operational handling procedure.

**Do not mark SENT before calling the provider** just to avoid duplicates: crashing after marking `SENT` but before sending will permanently lose the email. This is a tradeoff between message loss and duplicate delivery that cannot be eliminated with a `try/catch`.

## 9. Email Idempotency Is a Business Question

There are at least three levels of idempotency:

| Level | Problem | Mechanism |
| --- | --- | --- |
| **Order placement command** | Client retries POST creating multiple orders | Command idempotency key, unique business constraint |
| **Email job creation** | Same order spawns multiple identical jobs | Unique notification intent key inside DB transaction |
| **Sending to provider** | Worker retries same job after timeout/crash | Provider idempotency key / reconciliation when supported |

These three levels do not substitute for each other. Creating an order only once does not mean the email is sent only once. Conversely, deduplicating the email does not prove the order-creation command is idempotent.

### Why Not Deduplicate by correlationId?

A single request may emit multiple events—`OrderCreated`, `PaymentConfirmed`, `ShipmentCreated`—and send three different kinds of emails sharing the same correlation ID. If you use correlation ID as the deduplication key, you can mistakenly drop valid notifications. The right key must include the identity of the **logical notification** (e.g., `jobId` or `orderId + notificationType + templateVersion` per policy).

### One Order with Multiple Recipients

If an order needs to send emails to both the customer and internal staff, create **recipient-specific delivery jobs** or a dedicated delivery record per recipient as appropriate. Do not share one marker for two recipients and assume one successful send means the other succeeded as well. Idempotency policy and outcomes must be scoped to the proper unit.

## 10. SMTP/Provider Failures and Exception Handling

Failures can occur at different stages:

- **Before sending:** missing template, invalid recipient, rendering error, invalid authorization.
- **During sending:** DNS, TLS handshake, connection timeout, auth failure, SMTP 4xx/5xx, provider 429/5xx.
- **After provider acceptance:** lost response, network drop, worker crash before persisting state.
- **After provider receipt:** bounce, complaint, unsubscribe, or delivery webhook reporting failure.

Classify errors according to the provider contract rather than forcing all 4xx/5xx into a rigid table. Typically:
- Connection errors or throttling can be retried with backoff.
- Invalid recipients or broken template schemas need fixing/quarantine.
- Invalid provider auth is a configuration error requiring an alert, not a retry storm.
- Timeouts may represent an **unknown outcome** and must be retried with a stable key or reconciled.
- Bounces/complaints need a recipient/consent management workflow rather than infinite retries.

With an `AFTER_COMMIT` callback sending via SMTP directly, if the mailer throws an exception, **the already-committed order cannot be rolled back because of the email failure**. Depending on the callback flow and transaction manager, the exception may propagate back to the commit caller, risking an API error response even though the order was created. Therefore:
- Do not let the result of a best-effort mail send redefine the status of an already-committed order.
- If sending is mandatory, save a durable intent and return the order creation result per the business contract.
- Maintain structured logs/metrics, retries, and a delivery status table separate from order status.
- Do not inadvertently retry the entire `PlaceOrder` command just because the email callback failed.

### A Note on In-JVM Retries

You can add `@Retryable` or a retry loop around the mail gateway for transient errors. However, in-RAM retries cannot survive a process crash. `@Retryable` also requires the corresponding Spring Retry/AOP configuration; `@TransactionalEventListener` itself does not retry automatically. Do not use unbounded retries that cause overload and duplicate sends.

## 11. Transactions and Threads: Key Takeaways

### 11.1. Synchronous Callbacks Do Not Guarantee Low Latency

`AFTER_COMMIT` gets the timing right, but a callback making a blocking SMTP call can prolong response latency. Moving the email into an async executor usually makes the request faster, yet introduces a window for losing jobs on crash. Outbox + worker decouples latency while preserving durable intent.

### 11.2. `@Async` and Proxies

A method annotated with `@Async` requires `@EnableAsync` and must be invoked through a Spring proxy under proper configuration. Calling `this.sendAsync(...)` inside the same bean typically bypasses advice. For transaction-bound listeners, do not offload registration of the synchronization onto an async thread lacking transaction context. In practice, a synchronous `AFTER_COMMIT` listener can **submit a task** to a separate async service, though it remains best-effort without an outbox.

### 11.3. SecurityContext and MDC

Executor workers by default do not have the servlet request's `SecurityContextHolder` or its MDC correlation ID. Pass verified IDs in the event/job, or use properly configured context propagation when needed. Do not pass JWTs/sessions/passwords through events to "preserve permissions"; long-running jobs should use a constrained service identity and consistent policy.

### 11.4. Reactive Transactions

In WebFlux/Reactor, transaction state is bound to the Reactor Context. Spring 6.1 supports transaction-bound events with `TransactionContext` as the event source (typically via `TransactionalEventPublisher`). Do not infer from the imperative `TransactionTemplate` example that reactive subscriptions share the same `ThreadLocal` transaction. If handling reactively, wire lifecycle/transaction and completion properly; fire-and-forget `subscribe()` does not replace a durable job.

## 12. Security and Privacy of Email Events

Email addresses, recipient names, order line items, shipping addresses, and order totals can be **personal data or sensitive business data**. Internal events are not a security boundary. Practices to consider:

1. **Send only minimal information:** the template may only need order ID and display name; do not send full managed entities or payment details.
2. **Authorization at the source:** the service must authenticate the actor/tenant and verify permission to place the order, never trusting a client-supplied `approved=true`.
3. **Email the right recipient:** check the snapshotted email or query the authoritative record per policy; never accept arbitrary addresses from a forged event lacking an approved business fact.
4. **Data in the outbox:** restrict DB permissions, use encryption-at-rest if required, and enforce retention and deletion workflows when policy demands.
5. **Minimal logging:** do not log full bodies, auth headers, tokens, or complete email addresses unnecessarily; mask recipients where appropriate.
6. **Safe links:** use HTTPS and trusted configured hosts; do not build reset/payment links from an untrusted host or unprotected tokens.
7. **HTML escaping:** avoid injecting unescaped content into templates, especially customer names or order notes.
8. **Consent and preferences:** separate transactional emails from marketing emails per product policy and applicable regulations; do not automatically send marketing just because an order event occurred.
9. **Controlled replay:** an admin console or DLQ replay can resend real emails; enforce authorization and audit replay actions.
10. **Provider webhooks:** validate webhook origin/authentication and webhook event idempotency before updating delivery state.

Do not assume that because only internal Spring beans exist, every payload is trusted. If one module can publish a fake `OrderCreatedEvent` and a listener holds credentials to send email, that is a confused-deputy risk. For sensitive side effects, the listener/worker should tie events to records validly written by the application service or enforce clear source and authorization policies.

## 13. Observability: Measuring the Right Units

An illustrative set of metrics:

| Metric | Meaning |
| --- | --- |
| `orders.created.count` | Number of orders created per business transition |
| `email.jobs.pending.count` | Number of pending email jobs |
| `email.jobs.oldest.age` | Age of the oldest incomplete job |
| `email.send.attempts` | Number of send attempts (may exceed number of jobs) |
| `email.send.errors` | Failed send attempts by bounded error category |
| `email.send.duration` | Duration of a single provider call |
| `email.jobs.sent.count` | Jobs marked `SENT` |
| `email.delivery.bounced.count` | Webhooks reporting bounces after provider acceptance |

These metrics **do not appear automatically** just from using Spring Context/Micrometer; they require appropriate instrumentation/binders and exporters. Some orders can have multiple email jobs, and each job can retry multiple times. Do not use attempts as the count of placed orders or users who received mail.

**Do not attach `orderId`, `eventId`, `email`, or `correlationId` to metric tags** due to high cardinality. Use bounded tags such as `template`, `status`, `provider`, and `errorCategory`. Individual IDs belong in access-controlled structured logs/traces; mask email recipients appropriately.

Example logs:

```text
INFO  eventId=EVT-42 orderId=ORD-42 notification=ORDER_CONFIRMATION
      jobId=EMAIL-42 status=PENDING attempt=0
WARN  jobId=EMAIL-42 provider=smtp status=RETRY_SCHEDULED
      errorCategory=TIMEOUT attempt=1
INFO  jobId=EMAIL-42 provider=smtp status=ACCEPTED attempt=2
```

These are **illustrative logs**; they are not the demo's stdout. `status=ACCEPTED` shows the provider accepted the attempt, not proof that the message was received. To know final delivery, you need provider status/webhooks.

### Trace Boundaries

If your system uses Micrometer Tracing/OpenTelemetry, you can create spans for:
- `placeOrder`;
- `persistOutbox`;
- `emailWorker.claim`;
- `renderTemplate`;
- `provider.send`;
- `deliveryWebhook.process`.

For workers running minutes after the request, correlate traces/workflows using policy-governed event IDs/correlation IDs; do not assume the request's thread-local context still exists. Tracing is helpful but does not replace durable state.

## 14. Application Testing: From Happy Path to Crash

### 14.1. Unit Testing Email Content

Use a fake mail gateway and renderer:
- Given an order ID, verify subject/body/template/recipient are correct.
- Unicode/Vietnamese content, long names, amounts/currencies/date formatting are accurate.
- HTML fields are escaped; links point only to valid domains.
- Passwords/tokens/card data are never included in the mail body.
- Template version is recorded on the email job if reproducible replay is required.

### 14.2. Integration Testing Transactions

With H2 or a test database supporting real transactions:
- **Commit:** insert order + publish event inside a transaction; `AFTER_COMMIT` listener is invoked once.
- **Rollback:** insert order then roll back; `AFTER_COMMIT` listener is **not** invoked.
- **Outside transaction:** listener with `fallbackExecution=false` is not invoked.
- **Mail failure after commit:** the database still retains the order; the failure must be observable and handled per policy.
- If using a `@Transactional` test method where the test framework rolls back at the end of the test, commit explicitly using `TransactionTemplate` or `TestTransaction` to verify `AFTER_COMMIT`.

The Section 5 example executes the first three scenarios in a standalone program.

### 14.3. Testing @Async Without Flakiness

Do not write:

```java
publisher.publishEvent(event);
Thread.sleep(500);
verify(mailGateway).sendConfirmation(...);
```

This is an **illustrative anti-pattern**, not runnable code. Instead, use `CountDownLatch`, `CompletableFuture`, or Awaitility with a bounded timeout and a signal emitted **after** the mail gateway reaches the milestone under test. A latch only signaling that the handler enqueued the task is insufficient to assert the provider accepted it.

A test fake interface can return a future keyed by `jobId`; the test registers expectations before publishing, and the worker completes it on send success or exception. If multiple emails run concurrently, use distinct IDs per job rather than a shared static boolean that allows one test to inadvertently pass another.

### 14.4. Testing Outbox and Retries

Exercise the failure windows:

| Failure Point | Expectation |
| --- | --- |
| DB rollback before commit | No order or outbox job committed |
| DB committed, worker has not run yet | `PENDING` job survives restart |
| Transient SMTP failure | Job increments attempt count, retries with backoff |
| Provider accepted, worker crashes before marking `SENT` | Job retries with the **same idempotency key** |
| Duplicate job event | Business job uniqueness/deduplication protects against duplicates |
| Concurrent worker claims | Only one valid claim succeeds, or safe duplicate handling |
| Invalid recipient | Quarantine/`FAILED` and alert, no infinite retry |
| Repeated provider bounce webhook | Idempotent webhook processing |
| Unsubscribe/permission changed | Mail reception policy applied properly at execution time |

**Do not merely mock `emailService.send()`** and conclude retry/durability works. To prove crash recovery, you must use durable storage and test process/worker restarts or fault injection before/after ACK.

### 14.5. End-to-End Email Data Verification

A smoke test against a sandbox SMTP/email provider can verify:
- SMTP connection/TLS credentials are valid and the sender domain is accepted.
- MIME/encoding, subject, HTML/plain-text fallback.
- Safe test recipients to avoid unintended real emails.
- Provider accepted webhook works and is authenticated.
- Bounce/complaint simulation and PII protection in logs/queues.

Use a sandbox or test inbox; never blast real users in automated tests.

## 15. Common Implementation Mistakes

1. **Sending email directly in `@EventListener` before commit:** can send for rolled-back orders.
2. **Using `@TransactionalEventListener` but publishing outside a transaction:** callback never runs because fallback defaults to false.
3. **Assuming AFTER_COMMIT = asynchronous:** the callback can block the commit thread when SMTP is slow.
4. **Assuming AFTER_COMMIT = durable:** a process crash after commit before the callback still loses intent.
5. **Catching mail exceptions and ignoring them:** no retry/alert, customer never notified.
6. **Throwing post-commit email exceptions and retrying the whole PlaceOrder:** creates duplicate orders/fees/events.
7. **Marking email SENT before sending:** crashing before the request loses the notification.
8. **Marking SENT after sending without idempotency:** crashing between the two steps can send duplicate emails.
9. **Using correlation ID as the email dedupe key:** distinct emails in the workflow get mistakenly dropped.
10. **Putting JPA entities in events:** mutable/lazy-loading, stale data, and overexposure.
11. **Emailing raw request input:** wrong recipient risk, missing ownership/tenant validation.
12. **Treating JavaMailSender.send as inbox delivered:** provider acceptance is not delivery.
13. **Reading request SecurityContext in an async worker:** context may be missing or stale.
14. **Adding `@Async` without `@EnableAsync`/proxy:** method may not run asynchronously as expected.
15. **Using an unbounded executor queue:** can exhaust memory when the provider is slow.
16. **Retrying all SMTP 4xx/5xx identically:** classify errors per provider and policy.
17. **Non-idempotent webhook handling:** repeated webhooks corrupt delivery status or double effects.
18. **Not testing rollback and crash windows:** happy-path tests hide design flaws.
19. **Writing full email bodies/recipients into metrics/logs:** PII and cardinality risks.
20. **Not defining business outcomes:** a "sent" dashboard might only reflect accepted, not delivered.

## 16. Choosing an Architecture Based on Requirements

| Requirement | Recommended Solution | Limitations to State Clearly |
| --- | --- | --- |
| Secondary email, occasional loss acceptable | Direct `AFTER_COMMIT` listener | Can be lost on process crash or SMTP error |
| Fast response needed, rare notification loss acceptable | `AFTER_COMMIT` → `@Async` | Executor queue in RAM, requires error handling |
| Critical confirmation email, must retry after restart | Order + email outbox/job in same transaction | Must operate worker, lease, retry, deduplication |
| Multiple services and email providers | Transactional outbox + broker/worker + provider adapter | At-least-once may produce duplicates |
| Need to know mail reached the inbox | Provider delivery webhooks/status tracking | Accepted ≠ delivered; bounce/spam visibility has limits |
| Permissions/consent change while queued | Revalidation in worker per policy | May reject a previously scheduled email |
| Order placement command retries exist | Command-level idempotency + notification intent dedupe | Distinct from provider-level idempotency |

There is no universal rule like "always use async" or "always use Kafka" for every product. Choose based on criticality, consistency, latency, operational resources, and recovery objectives.

### One-Sentence Design Rule

**The order-creation transaction decides the business fact and records the intent to send; the worker is responsible for executing email delivery with retries, idempotency, and monitoring; the email outcome must never pretend to be an atomic part of the order-placement transaction.**

## 17. Production Deployment Checklist

- [ ] Application service checks authentication, ownership/tenant, and business invariants before creating the order.
- [ ] `OrderCreatedEvent` carries IDs and necessary snapshots, without managed JPA entities.
- [ ] Team understands plain `@EventListener` can run before commit.
- [ ] When using `@TransactionalEventListener(AFTER_COMMIT)`, publishing occurs inside a real transaction.
- [ ] Tested that rollback sends no email; outside a transaction, the callback does not run by default.
- [ ] `AFTER_COMMIT` is not confused with async execution or durable delivery.
- [ ] If using `@Async`, executor/`@EnableAsync`/proxies/error handling are configured and tested.
- [ ] For critical emails, durable email job/outbox is persisted **in the same transaction** as the order.
- [ ] Jobs have stable identities, unique constraints per contract, and explicit states.
- [ ] Worker performs safe claiming, retry/backoff/jitter, attempt limits, quarantine, and alerting.
- [ ] On ambiguous provider timeout, retry uses the same idempotency key or reconciliation.
- [ ] Exactly-once email is not promised when the provider lacks deduplication support.
- [ ] Templates use only required data, escape HTML, and leak no secrets.
- [ ] SMTP/provider credentials live in secrets, not in source, events, or logs.
- [ ] Consent/preferences and recipients are selected per business policy.
- [ ] Logs/metrics/traces distinguish order committed, send attempts, accepted, and delivered.
- [ ] Tests cover commit, rollback, async completion, crash windows, duplicates, retries, and provider webhooks.
- [ ] A runbook exists for stuck `PENDING` jobs, configuration errors, bounces, and authorized replays.

**Conclusion:** Spring Framework Application Events are a useful tool for decoupling **email work** from order-creation logic, especially when using `@TransactionalEventListener(AFTER_COMMIT)` to avoid emailing for rolled-back transactions. However, for **reliable** email notifications, in-memory events or `@Async` alone are not enough: you need a **durable intent/outbox**, a worker with retries, idempotency, and observability. The design must clearly distinguish **order committed**, **mail provider accepted**, and **recipient received the email**.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework 6.1.21 — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.1.21 — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html)
- [Spring Framework — Email Integration](https://docs.spring.io/spring-framework/reference/integration/email.html)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
