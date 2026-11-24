# Separating the Mail Service from the Controller or Domain Service

## 1. Why does sending email need its own boundary?

In **Spring Framework Mail**, the simplest way to send an email is to create a **SimpleMailMessage** and then call **JavaMailSender.send(...)**. The concise API makes it tempting for developers to write SMTP code directly in a controller or domain service. That approach may work when an application is small, but when you need testing, changing SMTP providers, sending multiple notification types, or handling network failures, business code becomes tightly coupled to email infrastructure.

For example, an account registration operation consists of distinct responsibilities:

1. **HTTP controller** receives the request, validates input data, and calls the use case.
2. **Application service** coordinates account registration, the repository, and the notification request.
3. **Domain model/domain service** enforces registration rules, state, and invariants.
4. **Mail service/adapter** builds the email and interacts with JavaMailSender and the SMTP server.

**Separating the mail service** means moving email composition/sending into a dedicated component so the controller does not need to know SMTP and the domain does not need to know MimeMessage, host, port, username, retry, or the Jakarta Mail library.

~~~mermaid
flowchart LR
    C[REST Controller] --> A[Application Service / Use Case]
    A --> D[Domain Model / Domain Service]
    A --> P[Mail Port / Notification Interface]
    P --> M[Spring Mail Adapter]
    M --> J[JavaMailSender]
    J --> S[SMTP Server]
~~~

This boundary keeps the **dependency direction** clear: the controller depends on the use case; the domain holds business rules; the application layer decides whether to request a send; the mail adapter decides how to communicate over SMTP.

This is a way to organize responsibilities, not a strict rule that every Spring application must use multi-module Clean Architecture. For a small application, a dedicated Spring service for sending mail is already a helpful improvement.

## 2. Anti-pattern: sending directly from the controller

A controller might be written as:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {
    private final JavaMailSender mailSender;

    public AccountController(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @PostMapping("/welcome")
    public void welcome(@RequestParam String email) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("noreply@example.com");
        message.setTo(email);
        message.setSubject("Welcome!");
        message.setText("Thanks for joining.");
        mailSender.send(message);
    }
}
~~~

This code **can send an email**, yet the controller is handling too many things:

- Both interpreting the HTTP request and directly driving SMTP.
- Holding the email content itself (From, Subject, Text), making it hard to reuse when registering from a CLI, batch job, or message consumer.
- Depending on SimpleMailMessage and JavaMailSender; controller tests struggle to focus on HTTP behavior.
- Making HTTP response time depend on network, TLS, SMTP AUTH, and SMTP server speed.
- Easily turning SMTP errors into HTTP 500 even when the business operation may have succeeded.
- Growing bloated as HTML, locales, templates, unsubscribe, or other providers are added.

Another risk: if the controller writes to the database and then sends mail, an exception thrown by `send` can make the client think the whole request failed even though the record was already saved. If mail is sent before the database commits, users may receive a notification about data that just rolled back.

**Solution:** the controller should only call an application service. Sending mail crosses a separate boundary, and the sending timing must be defined by the business contract.

## 3. Anti-pattern: domain service depending on SMTP

A domain service should answer the question **whether business rules are valid**, not **which port SMTP is using**. An inappropriate example:

~~~java
@Service
public class OrderDomainService {
    private final JavaMailSender mailSender;

    public OrderDomainService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void confirm(Order order) {
        order.confirm();
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo(order.customerEmail());
        message.setSubject("Order confirmed");
        message.setText("Your order was confirmed.");
        mailSender.send(message);
    }
}
~~~

This is **unwanted coupling**: order confirmation depends on the network connection and SMTP configuration. Domain tests can fail because of email rather than Order rules. When changing notification channels, the domain must change even though order confirmation logic stayed the same.

In DDD design, the domain can emit a **domain event** such as OrderConfirmed to represent a business event that occurred; a handler at the application or infrastructure layer decides to send the email. You do not have to adopt full DDD to apply the principle: **do not let pure business rules depend on infrastructure adapters**.

## 4. Responsibility boundaries of the layers

| Component | What it should do | What it should not do |
|---|---|---|
| **Controller/HTTP adapter** | Parse requests, validate, call use cases, return HTTP status | Create SimpleMailMessage, hold SMTP secrets, retry transport |
| **Application service** | Coordinate use cases, transactions, repositories, and notification policy | Encode MIME/Base64 itself, manage SMTP sockets |
| **Domain model/service** | Invariants, state, and business rules | Import Spring Mail/Jakarta Mail, read HTTP headers |
| **Mail port** | Express send requests in application language | Expose transport specifics unnecessarily |
| **Mail adapter** | Build content, set headers, call JavaMailSender, map infrastructure errors | Re-decide registration/ordering rules |
| **Queue/outbox worker** | Persist and run send requests, controlled retry, record state | Assume SMTP can roll back with a DB transaction |

Distinguishing **"when is a notification needed?"** from **"how is it sent over SMTP?"** prevents a class from doing both business logic and transport control.

## 5. The simple way: a dedicated MailService

For a small Spring Boot project, you can move all SimpleMailMessage creation code into a dedicated service:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.com");
        message.setTo(recipient);
        message.setSubject("Welcome to our service");
        message.setText("Hello " + displayName + ", welcome!");
        mailSender.send(message);
    }
}
~~~

The application service only calls a method with business meaning:

~~~java
import org.springframework.stereotype.Service;

@Service
public class RegistrationApplicationService {
    private final AccountRepository accounts;
    private final WelcomeMailService welcomeMail;

    public RegistrationApplicationService(
            AccountRepository accounts,
            WelcomeMailService welcomeMail) {
        this.accounts = accounts;
        this.welcomeMail = welcomeMail;
    }

    public void register(String email, String displayName) {
        accounts.create(email, displayName);
        welcomeMail.sendWelcome(email, displayName);
    }
}
~~~

**AccountRepository** in the example is a contract defined by the application itself. The code illustrates separating responsibilities, **not yet solving the DB–SMTP transaction boundary**: if the DB commits yet mail fails, registration can partially succeed. Later sections show better approaches when notifications are critical.

The controller becomes concise:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {
    private final RegistrationApplicationService registrations;

    public RegistrationController(
            RegistrationApplicationService registrations) {
        this.registrations = registrations;
    }

    @PostMapping
    public ResponseEntity<Void> register(
            @RequestBody RegistrationRequest request) {
        registrations.register(request.email(), request.displayName());
        return ResponseEntity.noContent().build();
    }

    public record RegistrationRequest(String email, String displayName) {
    }
}
~~~

The example returns **204 No Content** after a synchronous use case; the specific HTTP status must follow the API contract. A real account-creation API might return **201 Created**. If it only enqueues a mail job to process later, **202 Accepted** can reflect that the request was accepted. No HTTP status code by itself proves the recipient read the email.

The immediate benefits are having one place to update From/subject/content, reusing from multiple use cases, mocking the service in tests, and changing mail content without editing the controller. There is no need to create an interface just to feel "architecturally pure"; pick just enough complexity.

## 6. Using an interface: MailPort and SMTP adapter

When the application layer needs to avoid importing Spring Mail, define a **mail port** with simple data types:

~~~java
public record OutgoingMail(
        String recipient,
        String subject,
        String body) {
}

public interface MailPort {
    void send(OutgoingMail mail);
}
~~~

The adapter uses JavaMailSender:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class SmtpMailAdapter implements MailPort {
    private final JavaMailSender sender;

    public SmtpMailAdapter(JavaMailSender sender) {
        this.sender = sender;
    }

    @Override
    public void send(OutgoingMail mail) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.com");
        message.setTo(mail.recipient());
        message.setSubject(mail.subject());
        message.setText(mail.body());
        sender.send(message);
    }
}
~~~

The application service depends on the contract:

~~~java
public class PasswordResetApplicationService {
    private final ResetTokenService tokens;
    private final MailPort mailPort;

    public PasswordResetApplicationService(
            ResetTokenService tokens,
            MailPort mailPort) {
        this.tokens = tokens;
        this.mailPort = mailPort;
    }

    public void requestReset(String email) {
        String link = tokens.createResetLink(email);
        mailPort.send(new OutgoingMail(
                email,
                "Reset your password",
                "Use this link to reset your password: " + link));
    }
}
~~~

**ResetTokenService** is an illustrative contract. A real system must protect tokens, enforce expiration, prevent abuse/rate-limit, and avoid responding in a way that reveals whether an account exists. The purpose of the snippet is to show that the application service only requests **sending an email**, without needing to understand SMTP.

~~~mermaid
flowchart TD
    REST[REST Controller] --> APP[Application Service]
    APP --> DOMAIN[Domain Rules]
    APP --> PORT[MailPort]
    SMTP[Spring SMTP Adapter] -.implements.-> PORT
    SMTP --> JMS[JavaMailSender]
    JMS --> PROVIDER[SMTP Provider]
~~~

To switch transport, you can build an HTTP email API adapter or an in-memory fake in tests without changing the domain. Still, the contract needs to represent enough important information: locale, template ID, attachments, business headers, or metadata if the application genuinely needs them.

## 7. Choosing a contract at the right level

Not every use case should assemble subjects and bodies itself. For emails using dedicated templates, locales, or branding, a business-level contract is easier to maintain:

~~~java
public interface AccountNotificationService {
    void welcomeAccount(String accountId, String recipient);
    void passwordChanged(String accountId, String recipient);
}
~~~

The implementation picks the template/language and then calls the shared MailPort:

~~~text
AccountApplicationService
          |
          v
AccountNotificationService
          |
          v
Template Renderer + MailPort
          |
          v
Spring SMTP Adapter
          |
          v
JavaMailSender
~~~

In this structure, the application service asks for **welcomeAccount**, the notification service chooses the content/template, and the SMTP adapter performs only the transport. If the application only has two text emails, a simple WelcomeMailService may fit better than many intermediate layers. The goal is **meaningful decoupling**.

### Do not pass persistence entities directly into the mail adapter

Avoid designing **sendWelcome(UserEntity user)** and letting the mail adapter depend on a JPA entity. That forces the mail layer to know the database schema and easily runs into lazy loading and mutating data during asynchronous sending.

Replace with a snapshot DTO:

~~~java
public record WelcomeNotice(
        String accountId,
        String recipientEmail,
        String displayName,
        String localeTag) {
}
~~~

The DTO should hold **only the data that needs to be sent**. For password reset tokens or other sensitive information, enforce expiration, protect storage/queues, and never log tokens.
## 8. When to send email relative to a transaction?

Separating the mail-sending class is **not enough** if the application service calls SMTP at an inappropriate time. For example, an order is saved in a transaction, and then Spring Mail sends a notification. The database can roll back, whereas an SMTP server cannot "roll back" a message it already accepted.

An SMTP call is an **external side effect**. It does not participate in the database's ACID transaction without a special mechanism; JavaMailSender does not provide two-phase commit with a database.

### Scenario 1: sending while the database transaction has not committed

~~~mermaid
sequenceDiagram
    participant A as Application service
    participant D as Database
    participant M as SMTP server
    A->>D: BEGIN; save order
    A->>M: JavaMailSender.send()
    M-->>A: 250 accepted
    A->>D: COMMIT
    D-->>A: Commit fails, rollback
    Note over M: Email may already be in the SMTP queue
    Note over D: Order does not exist
~~~

The customer may receive an "order confirmed" email for an order that was never committed. Even when **MailService** lives in its own class, the application service still has to choose the **timing** of the send.

### Scenario 2: commit succeeds but SMTP fails

~~~mermaid
sequenceDiagram
    participant A as Application service
    participant D as Database
    participant M as SMTP server
    A->>D: Save order
    D-->>A: COMMIT succeeds
    A->>M: JavaMailSender.send()
    M-->>A: Connection error / rejection
    Note over D: Order has been saved
    Note over A: Cannot roll back commit just because email failed
~~~

If the HTTP controller turns every exception into an "order placement failed" error, the client may resend the request and create duplicate orders. You need to define **business success** (order recorded) separately from **notification send status**.

### Three common approaches

| Coordination approach | Complexity | Pros | Risks and limitations |
|---|---|---|---|
| **Synchronous send after DB op** | Low | Simple, send result returned in the same flow | Crash gap exists; SMTP affects latency and response |
| **Spring event with AFTER_COMMIT** | Medium | Avoids sending before commit, reduces coupling between use case and listener | In-memory event is not durable; crash after commit still loses request |
| **Transactional outbox + worker** | Higher | Stores send intent in the same transaction; stateful retry | Needs table/job store, worker, claim, retry, reconciliation, and deduplication |

There is no single mandatory choice for every application. Test emails or non-critical notifications can accept the simple approach. Emails involving payments, orders, access rights, or audit requirements usually need a more durable mechanism.

## 9. Using after-commit events so you do not send before a transaction completes

For emails where loss on process crash between commit and listener is acceptable, **@TransactionalEventListener** is a clean way to decouple the application and adapter.

A use case can publish an event after executing business rules:

~~~java
public record AccountRegisteredEvent(
        String accountId,
        String email) {
}
~~~

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegisterAccountUseCase {
    private final AccountRepository repository;
    private final ApplicationEventPublisher events;

    public RegisterAccountUseCase(
            AccountRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public String register(String email, String displayName) {
        Account account = repository.create(email, displayName);

        events.publishEvent(new AccountRegisteredEvent(
                account.id(),
                account.email()));

        return account.id();
    }
}
~~~

**AccountRepository** and **Account** are illustrative contracts/models of the business system. In practice, validate the email and apply registration rules before saving.

The listener handles the send request after commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class WelcomeEmailListener {
    private final AccountNotificationService notifications;

    public WelcomeEmailListener(AccountNotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterAccountRegistered(AccountRegisteredEvent event) {
        notifications.welcomeAccount(
                event.accountId(), event.email());
    }
}
~~~

**Important point:** the listener is invoked when the associated transaction has committed successfully. By default, if there is no active transaction, events for @TransactionalEventListener are usually **not processed** unless **fallbackExecution** is configured. Make sure the event is published within a real transaction boundary, for example a call passing through a Spring transactional proxy rather than an internal self-invocation bypassing the proxy.

This kind of Spring event usually lives in process memory. It is **not a durable queue**. The application can crash after the database commit yet before sending mail; the notification request is lost. Also, if a synchronous listener throws an error after commit, the caller may receive an exception even though the business data was already committed; do not treat that exception as proof the database rolled back.

**AFTER_COMMIT solves send timing; it does not by itself solve durability, retry, or exactly-once.**

### Does a domain event need to know MailService?

No. Events should describe **what happened in the business**, such as AccountRegisteredEvent or OrderConfirmedEvent. Events should not contain JavaMailSender or SMTP transport data.

~~~text
Domain/Application:
  AccountRegisteredEvent(accountId, email)
                         |
                         v
  Notification listener / application handler
                         |
                         v
  AccountNotificationService
                         |
                         v
  MailPort -> SMTP adapter
~~~

Sometimes an event contains only **accountId**, and the handler queries the latest data; sometimes the event carries the necessary email snapshot. Choose based on data consistency and asynchronous processing needs. If the user's email can change between emitting the event and sending, use a snapshot or explicitly accept reading the new address per policy.

## 10. Transactional outbox for reliable send requests

For critical notifications, you need to avoid the gap **"database committed yet failed to emit the email job in time"**. The **transactional outbox** pattern solves this by writing both business data and the send request in the same database transaction.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Application Service
    participant D as Database + Outbox
    participant W as Mail Worker
    participant S as SMTP Server
    U->>A: Register / place order
    A->>D: BEGIN, save business data
    A->>D: Insert outbox mail job
    D-->>A: COMMIT
    A-->>U: Return business result
    W->>D: Claim PENDING job
    W->>W: Build mail content
    W->>S: JavaMailSender.send()
    S-->>W: SMTP accepted or error
    W->>D: Save status / retry metadata
~~~

The application service records the **notification intent** instead of sending SMTP inside the transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderUseCase {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public PlaceOrderUseCase(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public String placeOrder(PlaceOrderCommand command) {
        Order order = orders.place(command);

        outbox.enqueueOrderConfirmation(
                order.id(),
                order.customerEmail());

        return order.id();
    }
}
~~~

**OrderRepository**, **MailOutboxRepository**, **PlaceOrderCommand**, and **Order** are illustrative abstractions, not built-in Spring Mail APIs. The necessary condition is that both saving the order and writing to the outbox participate in the **same database transaction**. If the outbox lives in a different DB, merely putting both calls inside a @Transactional method does not automatically make them atomic.

Later, a worker reads the outbox, builds a SimpleMailMessage or MimeMessage, and calls the mail adapter:

~~~text
mail_outbox (illustrative model)
  id
  business_key
  message_type
  recipient
  payload_ref / serialized_payload
  status             PENDING / CLAIMED / SMTP_ACCEPTED / FAILED / UNKNOWN
  attempt_count
  next_attempt_at
  last_error_code
  created_at
  updated_at
~~~

You do not have to store all email content as plaintext. You can store a reference to protected data or a payload whose information is limited by policy. The system must control queue read permissions, data retention periods, and remove sensitive tokens when they expire.

### Outbox does not guarantee exactly-once

~~~text
Worker picks up job
      |
      v
SMTP send succeeds, server returns 250
      |
      v
Worker crashes before updating outbox
      |
      v
Job reappears after lease expires
      |
      v
Worker may resend the same email
~~~

Therefore, an outbox usually gets you closer to **at-least-once processing of send requests**, rather than promising an email is delivered exactly once. Duplicates can be reduced with a business key, per-recipient status, retry control, looking up provider events, and an idempotency key if the provider supports it. **Standard SMTP has no universal idempotency key** for the receiving side to always deduplicate copies.

If the worker loses the connection after transmitting all data yet before reading the response, you need a **SUBMISSION_UNKNOWN** status or equivalent. Retrying at this point risks sending duplicates; handling depends on the importance of the email and reconciliation capabilities with the provider.

## 11. Synchronous and asynchronous sending: choose by business requirements

A separated MailService can be called **synchronously** or through a **worker**. Separating the class does not automatically make mail sending run in the background.

### Synchronous

~~~text
HTTP Request
  -> Controller
  -> Application Service
  -> MailPort / MailService
  -> JavaMailSender
  -> SMTP Server
  <- SMTP response
  <- HTTP response
~~~

The advantage is simplicity and the ability to report submission errors right inside the request. The downside is that SMTP latency slows requests, timeouts can drag on, and it is not easy to ensure resends when the process stops. Suitable for small tasks whose contract accepts depending on a successful SMTP call.

### Asynchronous via @Async

Spring can run a method through a task executor:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncNotificationDispatcher {
    private final MailPort mailPort;

    public AsyncNotificationDispatcher(MailPort mailPort) {
        this.mailPort = mailPort;
    }

    @Async("mailTaskExecutor")
    public void sendLater(OutgoingMail mail) {
        mailPort.send(mail);
    }
}
~~~

To use @Async, the application must configure **@EnableAsync** and a matching executor named **mailTaskExecutor** or the corresponding task execution configuration. Calls must go through the **Spring proxy**; internal calls from another method of the same bean usually do not trigger proxy-based async. With a void-returning @Async method, errors on the worker thread do not automatically become exceptions in the HTTP caller, so you must have an error-logging and observability strategy; you can use an appropriate return type or persist status in a job store.

**@Async is not a durable queue.** When a process restarts/crashes, tasks sitting only in memory/executor can be lost. For notifications that must guarantee send requests are not lost, use a durable queue/outbox and let a worker process it, instead of treating @Async as sufficient.

### Asynchronous via database/broker

With an outbox or message broker, the HTTP request finishes after the **send request has been durably persisted**. A worker picks up and sends the mail later. When returning **202 Accepted**, the response should make clear that **the request was accepted for processing**; it does not assert that the SMTP server or mailbox received the message.

| Requirement | Direct synchronous | Simple @Async | Durable outbox/queue |
|---|---|---|---|
| HTTP must wait for SMTP | Yes | No, if task dispatch succeeds | No |
| Survives process restart | Not out of the box | Not out of the box | Yes, if implemented properly |
| Needs dedicated worker/rate limit | Not mandatory | Can configure executor | Clearer design |
| Supports stateful retry | Must build yourself | Must build yourself | More convenient with job metadata |
| Prevents losing request between commit and send | Not guaranteed | Not guaranteed | Can be guaranteed at DB/outbox boundary |
| Exactly-once delivery over SMTP | No | No | Still not guaranteed on its own |

Separating MailService from the controller lets you **swap dispatch strategies** without changing the HTTP contract and domain logic, as long as the application contract describes the commitment accurately.
## 12. Testing each layer without depending on real SMTP

A major benefit of separating the mail layer is **testing at the right boundary**. Each kind of test only needs to check what its corresponding layer promises, instead of every business test opening an SMTP socket.

### Testing the application service with a mock MailPort

For **PasswordResetApplicationService** in the earlier example, you can use JUnit Jupiter and Mockito:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PasswordResetApplicationServiceTest {
    @Mock
    ResetTokenService tokens;

    @Mock
    MailPort mailPort;

    private PasswordResetApplicationService service;

    @BeforeEach
    void setUp() {
        service = new PasswordResetApplicationService(tokens, mailPort);
    }

    @Test
    void sendsResetMessageThroughPort() {
        when(tokens.createResetLink("alice@example.test"))
                .thenReturn("https://example.test/reset/token-example");

        service.requestReset("alice@example.test");

        verify(mailPort).send(new OutgoingMail(
                "alice@example.test",
                "Reset your password",
                "Use this link to reset your password: "
                        + "https://example.test/reset/token-example"));
    }
}
~~~

This test does not depend on Spring ApplicationContext, JavaMailSender, SMTP credentials, or the network. It proves **the use case requested sending the notification with the right data** through the port. It does not prove valid MIME or SMTP acceptance, because that is not the responsibility of the layer under test.

### Testing the SMTP adapter with a mock JavaMailSender

You can verify the adapter builds the expected SimpleMailMessage:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class SmtpMailAdapterTest {
    @Mock
    JavaMailSender sender;

    @InjectMocks
    SmtpMailAdapter adapter;

    @Test
    void createsExpectedSimpleMessage() {
        adapter.send(new OutgoingMail(
                "alice@example.test",
                "Status",
                "Your status has changed."));

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertArrayEquals(
                new String[] {"alice@example.test"},
                message.getTo());
        assertEquals("notifications@example.com", message.getFrom());
        assertEquals("Status", message.getSubject());
        assertEquals("Your status has changed.", message.getText());
    }
}
~~~

This test checks only **DTO → SimpleMailMessage mapping**. No SMTP connection is opened because JavaMailSender is mocked. If the adapter supports HTML, attachments, or MIME alternative, you can test **MimeMessage** with an appropriate mail sender/factory and inspect the parts, or use an SMTP test server to capture the real message.

### Testing the HTTP controller separately

With **@WebMvcTest**, controller tests should mock the application service or a use-case interface. The goal is to test validation, JSON binding, HTTP status codes, exception mapping, authentication/authorization, and the response contract. You should not force a controller test to load SMTP transport just because the controller directly injects JavaMailSender.

With Spring Boot 3.3, you can use **@MockBean** for the application service in MVC tests. Newer Spring/Boot versions may use a different mock bean mechanism; choose according to the project's actual dependency.

### When to run SMTP integration tests?

When you need to test **real SMTP protocol and MIME**, use an SMTP sink/test server in a test environment, not the production provider. You can observe:

- Sender/recipient envelope and headers.
- Plain text content, UTF-8 charset, HTML, and attachments.
- Effects of host, port, timeout, and TLS/AUTH configuration if supported by the test server.
- How the adapter reacts to SMTP error responses.

| Layer to verify | Suitable test type | Real SMTP server needed? |
|---|---|---|
| Domain invariants | Plain JUnit test | No |
| Application service orchestration | Mock MailPort | No |
| SMTP adapter mapping | Mock JavaMailSender/MimeMessage test | Not mandatory |
| Controller HTTP contract | MVC slice + mock use case | No |
| SMTP protocol/transport integration | SMTP sink/test server | Needs test server, not production provider |
| Production delivery | Metrics/DSN/provider events | Needs production infrastructure and observability policy |

Mocking JavaMailSender alone cannot prove SMTP AUTH, STARTTLS, or deliverability. Conversely, you do not need an SMTP integration test for every business-rule variant.

## 13. Standardizing error handling at the mail boundary

Spring Mail can throw exceptions from the **MailException** family, such as **MailAuthenticationException** when SMTP authentication fails, **MailSendException** when one or more messages fail to send, or **MailPreparationException** when preparing MIME fails.

Not every error carries the same meaning:

| Situation | Observation scope | How to handle |
|---|---|---|
| Wrong credentials or SMTP AUTH rejected | No valid sending session under current config | Alert on configuration, do not aggressively retry with the same secret |
| Connection cannot be opened | No proof of successful submission | Bounded retry, backoff, monitor provider |
| Server returns permanent error for recipient | Corresponding delivery part rejected | Record error per recipient, fix address or policy |
| SMTP accepts message | Submission succeeded at current hop | Track delivery separately, do not mark as read |
| Timeout after client transmits DATA | Server may have received it yet response was lost | Store uncertain status, weigh duplicate risk before retrying |
| Missing template data | Message preparation error in application | Fix data or template, avoid pointless SMTP retries |

The application may want to hide framework details behind an exception at the application boundary:

~~~java
public class NotificationSubmissionException
        extends RuntimeException {

    public NotificationSubmissionException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Example of an error-translating adapter:

~~~java
import org.springframework.mail.MailException;

public void sendSafely(OutgoingMail mail) {
    try {
        send(mail);
    } catch (MailException ex) {
        throw new NotificationSubmissionException(
                "SMTP submission failed for mail request", ex);
    }
}
~~~

The **sendSafely** example only illustrates the error boundary, not a method generated automatically by Spring. When the system needs to distinguish temporary/permanent errors, preserve the **root cause error type, SMTP code, and per-recipient status** in a handleable result/exception structure. If everything is wrapped into one RuntimeException discarding the cause, accurate retry capability degrades.

### Best-effort differs from mandatory delivery

A marketing email or non-essential notification can be **best effort**: the application service completes the business work and records the email request/error to handle later. A confirmation email used to grant access may require a stronger contract, yet SMTP still cannot be brought into the same transaction as the database like a simple internal operation.

Do not catch every MailException and silently ignore it, replying "sent successfully" with no evidence. If you intentionally do not let an email failure affect the business result, express the status clearly in jobs/events/metrics and handling procedures. If the business must wait for SMTP accepted, make clear that the HTTP response confirms only **SMTP submission**, not that the inbox received the message.

## 14. Mail configuration must not leak into controllers or the domain

Properties such as SMTP host, port, username, password, STARTTLS, timeouts, and From address belong in **infrastructure configuration** or the mail adapter, not the controller/domain service.

Example Spring Boot configuration with placeholders:

~~~yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: SMTP_USER_FROM_ENVIRONMENT
    password: SMTP_SECRET_FROM_SECRET_STORE
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

**The two username/password values above are illustrative placeholders only**, not real credentials. In real deployments, inject them from environment variables or a managed secret store. The timeouts are examples in milliseconds.

In local/test, you can replace the sender with a mock, fake, or point the SMTP host to **Mailpit**, **MailHog**, or an equivalent SMTP sink. Staging uses a sandbox, dedicated credentials, and a recipient allowlist; production uses a real SMTP provider with TLS, secrets, and monitoring. The controller still calls the same use case and must not contain branches like "if dev profile, send to address A".

### Using @ConfigurationProperties for sender identity

From address, reply-to, or display name can be grouped into dedicated configuration:

~~~yaml
app:
  notification:
    from-address: notifications@example.com
    reply-to-address: support@example.com
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notification")
public record NotificationMailProperties(
        String fromAddress,
        String replyToAddress) {
}
~~~

Spring Boot must **register configuration properties** via @ConfigurationPropertiesScan or @EnableConfigurationProperties, depending on application architecture. The mail adapter injects these properties instead of hard-coding From and Reply-To across many controllers.

The From address must fall within what the **account/SMTP provider is allowed to send from**. JavaMailSender authenticating successfully does not by itself guarantee every From address will be accepted.

## 15. Separating responsibilities does not mean ignoring security and privacy

The mail adapter is a **sensitive infrastructure boundary** because it can send data outward. Clearly specify what data may be placed into emails:

- **Recipient validation:** syntactically valid address, recipient has permission to receive that type of notification; do not trust all input from HTTP requests.
- **Authorization:** controller/use case lets users trigger emails only when matching their permissions and business state.
- **Do not expose recipients:** do not group private lists into To/Cc if each person needs an independent email; Bcc has a different purpose from personalization.
- **Template encoding:** for HTML emails, escape user-supplied data in the proper context rather than concatenating HTML arbitrarily and assuming Spring Mail blocks all content injection.
- **Sensitive data:** restrict emails from containing secrets, tokens, or personal profiles. When a token must be sent, apply short lifetimes and proper access policies.
- **Log management:** use request IDs, message IDs, statuses, and sanitized errors. Do not print SMTP passwords, OAuth bearer tokens, or full MIME bodies.
- **Send over protected channels:** SMTP submission with properly configured TLS and server identity verification per provider requirements.
- **Rate limiting:** restrict APIs that can trigger mail to prevent spam, system abuse, or getting the account locked by the provider.

Separating the mail service centralizes email-sending rules in one place, yet **does not replace** permission checks at the application layer. For example, the mail adapter lacks enough context to decide whether one user is allowed to request a password reset for another account; that is the use case's responsibility.

## 16. Package organization in a Spring Boot application

A readable structure without needing many Gradle modules:

~~~text
com.example.account
├── web
│   ├── RegistrationController.java
│   └── RegistrationRequest.java
├── application
│   ├── RegisterAccountUseCase.java
│   ├── AccountNotificationService.java
│   └── AccountRegisteredEvent.java
├── domain
│   ├── Account.java
│   └── AccountRules.java
├── persistence
│   └── JpaAccountRepository.java
└── infrastructure
    └── mail
        ├── SmtpMailAdapter.java
        ├── MailTemplateRenderer.java
        └── NotificationMailProperties.java
~~~

Or in a small application:

~~~text
com.example.app
├── controller/RegistrationController.java
├── service/RegistrationService.java
├── service/WelcomeMailService.java
└── repository/AccountRepository.java
~~~

There is no single mandatory package naming convention. What matters is keeping a **clear path from business logic to infrastructure**, and avoiding circular dependencies among controller, domain, persistence, and mail. The more notification types, templates, or SMTP transports you have, the more beneficial separating interfaces/adapters becomes.

### When is MailPort not needed yet?

If an application only sends one kind of text email through one SMTP provider, a dedicated mail service injecting JavaMailSender may suffice. Adding MailPort just to wrap two lines calling `send` with no additional testing/layering need can add extra files and indirection. When the application module needs infrastructure independence, wants to use fakes without starting Spring, or anticipates multiple transports, **MailPort** brings clear value.
## 17. Refactoring roadmap from a controller that sends directly

Suppose a project already has controllers calling JavaMailSender. There is no need to jump to a multi-module architecture immediately. You can refactor in small steps while keeping external behavior stable.

### Step 1: identify current mail-sending sites

Find places calling JavaMailSender, MailSender, or creating SimpleMailMessage or MimeMessage; controllers, scheduled jobs, listeners, and domain services may all be sending. Identify the **email type**, **trigger**, **recipient info**, **content**, **sending conditions**, and **timing relative to transactions**.

Example classification table before refactoring:

| Trigger | Email | Current location | Target location |
|---|---|---|---|
| Account registration succeeds | Welcome | RegistrationController | RegisterAccountUseCase → WelcomeMailService |
| Password changed | Security alert | AccountService | AccountNotificationService → MailPort |
| Order committed | Order confirmation | OrderDomainService | Domain event/outbox → mail worker |
| Periodic report | Report with attachment | Scheduled job | ReportApplicationService → mail adapter |

### Step 2: extract MailService without changing dispatch yet

Move the **setFrom, setTo, setSubject, setText, send** logic into MailService. Switch the controller to calling the application service. This step separates transport from HTTP without altering synchronous vs asynchronous execution, making the scope of change easier to control.

### Step 3: separate contracts if needed

When multiple use cases need to send the same kind of email, choose a meaningful API:

~~~java
public interface OrderNotificationPort {
    void sendOrderConfirmation(
            String orderId,
            String recipientEmail);
}
~~~

With diverse email types, you can use a shared DTO with template/locale; for small applications, dedicated methods are usually easier to understand than a generic API packed with optional parameters.

### Step 4: decide transaction boundaries

If an email represents a committed event, do not send while data can still roll back. You can use an AFTER_COMMIT event for best effort or an outbox when durability is required. **Do not accidentally alter the HTTP contract** simply by moving the `send` line to another file: determine when the application considers the use case successful.

### Step 5: add tests at the right layers

Verify the controller calls the application service, the application service requests sending via the mail port, and the adapter builds the message in the right format. Use an SMTP test server only in tests that genuinely need to check the protocol. For critical business flows, also test database rollback, commit success with mail failure, timeouts, and duplicate-causing retries.

### Step 6: add observability and operational policies

Record request ID/job ID, email type, recipient per privacy policy, submission result, and timestamp. Set timeouts, rate limits, batch sizes, and retries according to provider capacity. Avoid using an "Email sent successfully" log as proof the email was delivered to the Inbox.

## 18. Common mistakes when separating the mail service

**1. Only renaming classes while business logic still depends on SMTP APIs.** If a controller no longer calls `send` yet the application service has to build MimeMessage, understand MIME boundaries, and diagnose SMTP codes, infrastructure responsibility still has not been properly separated. Move email-building details into the adapter.

**2. Letting the domain service call MailPort directly inside a transaction.** Even if importing an interface instead of JavaMailSender, it can still send before the transaction commits. A contract inverts dependencies, yet **does not by itself solve timing and durability** of side effects.

**3. Silently swallowing exceptions in MailService.** Catching all exceptions and ignoring them can mislead use cases or monitoring systems into thinking emails were sent. If best effort, maintain clear statuses and metrics; if submission is mandatory, propagate an appropriate status to the caller.

**4. Calling @Async and assuming jobs cannot be lost.** In-memory task executors can lose work when a process crashes; a durable outbox/queue needs job persistence and recovery mechanisms. @Async also does not automatically preserve transaction context or guarantee send ordering.

**5. Sharing a mutable SimpleMailMessage across multiple requests.** A MailService Spring bean is usually a singleton, yet each send must create a separate message object. If you store SimpleMailMessage as a field and mutate To/Subject per request, threads can overwrite each other's data.

Example not to write:

~~~java
@Service
public class UnsafeMailService {
    private final JavaMailSender sender;
    private final SimpleMailMessage shared = new SimpleMailMessage();

    public UnsafeMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient) {
        shared.setTo(recipient); // Shared mutable state.
        shared.setSubject("Hello");
        sender.send(shared);
    }
}
~~~

A proper implementation creates **new SimpleMailMessage()** inside each send; reuse only the stably configured JavaMailSender bean.

**6. Trying to use a one-size-fits-all DTO containing every detail.** A class with dozens of nullable fields (recipient, cc, html, attachment, passwordResetToken, providerSpecificId...) makes the contract hard to use correctly. Separate business requirements from transport requirements when needed, avoiding leaking provider specifics into the domain.

**7. Mocking JavaMailSender in every test.** If a use case only needs to know it requested sending a welcome email, mocking MailPort/AccountNotificationService is enough; do not tie business tests to MIME content. Test MIME mapping in dedicated adapter tests.

**8. Believing SMTP accepted equals mailbox delivered.** A successful `JavaMailSender.send()` usually corresponds to the submission server accepting the message; relaying, mailbox delivery, spam filtering, and recipient reading are distinct steps. If the system needs to know delivery results, integrate reliable event sources in the mail infrastructure.

**9. Moving all mail-sending logic into a static controller helper.** A static helper still couples HTTP and business layers to transport, is hard to inject, hard to mock, and hard to reconfigure per profile. A Spring service or a port/adapter with clear responsibilities is much easier to control.

## 19. Choosing the right level of separation

| Scale/context | Suitable design | What to prioritize |
|---|---|---|
| Small app, a few text emails | A WelcomeMailService/NotificationMailService injecting JavaMailSender | Never call SMTP from controllers or domain models |
| Multiple use cases, needs independent tests | MailPort interface + SmtpMailAdapter | Application layer depends on contract; tests mock the port |
| HTML emails, multilingual, templates | Notification service + template renderer + adapter | Separate notification decision from formatting and transport |
| Email after DB transaction | AFTER_COMMIT listener, if in-memory trade-off is acceptable | Never send while DB can still roll back |
| Critical emails needing survival across restarts | Transactional outbox + worker + mail adapter | Persist send requests durably and perform stateful retries |
| Multiple providers/notification channels | Policy-routed port/gateway | Keep domain independent of providers and limit secret exposure |

In **Spring Framework Mail**, **SimpleMailMessage** and **JavaMailSender** are suitable tools for building a simple email-sending adapter. They should not become mandatory dependencies of HTTP controllers or domain services. The application layer should decide **when a notification is needed**, the mail service decides **content and how to send**, and any queue/outbox is responsible for **persisting send jobs and execution state**.

**Conclusion:** Start by moving mail-sending calls out of controllers/domain services, create independent messages inside the mail service, and use dependency injection. As needs grow, add MailPort, notification abstractions, after-commit events, or a transactional outbox according to the required reliability level. Whichever option you choose, always keep a clear distinction between **business work completed**, **SMTP accepted the message**, and **the recipient actually received/read the email**.
