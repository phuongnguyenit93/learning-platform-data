# Sending Queued Emails with Result Tracking and Duplicate Prevention

## 1. Practice Problem and Objectives

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes integrations through HTTP clients, databases, caches, message brokers, and Spring Integration adapters. The module emphasizes configuration management, data contracts, transactions, errors, duplicate handling, testing, and observability in real integration flows. This practice belongs to the **Comprehensive Practice** chapter, tackling **queued email delivery, result tracking, and duplicate prevention**.

Scenario: after an order is confirmed, the system must send a notification email. The API must return quickly, while SMTP/email providers can occasionally be slow, overloaded, or unavailable. Clients may retry requests after timeouts; RabbitMQ may redeliver messages when a worker crashes; two workers may pick up two copies of the same task. Meanwhile, operations must know which requests were accepted, are currently sending, were accepted by SMTP, failed, or require reconciliation.

**Objective:** build a reference flow using **Spring Boot + PostgreSQL/JDBC + RabbitMQ/Spring AMQP + JavaMailSender** with these capabilities:

1. Accept requests by stable **idempotency key**, returning the same delivery ID on repeated requests.
2. Use a **transactional outbox** to eliminate the gap between database commit and broker publish.
3. Have workers receive jobs, perform an **atomic claim** in the database, and allow only one attempt to send at a time.
4. Send via SMTP with timeouts, error classification, status tracking, retries, and history.
5. Query results via REST API and observe via metrics/logs/traces.
6. Handle duplicate messages, crashes after SMTP send, lost broker ACKs, invalid data, and DLQs.
7. Maintain an integration test suite proving transactions, idempotency, and post-failure states.

**Guarantee boundaries:** It is impossible to promise **exactly-once email delivery** using SMTP alone. A provider may accept a command while the client times out before receiving the reply. Thus, preventing duplicate requests and concurrent worker sends is **distinct** from proving the recipient received exactly one email. This lesson adopts a conservative policy: when the send outcome is uncertain, record **UNKNOWN** and reconcile before automatically resending.

## 2. Understanding "Sent Successfully" and the State Machine

| Milestone | State/Signal | What Is Proven | What Is Not Proven |
| --- | --- | --- | --- |
| API commits database | **PENDING** | Delivery and outbox are durably persisted | RabbitMQ/SMTP received it |
| Relay receives publisher confirm | Outbox **published_at** | Broker confirmed publish; unroutable returns checked | Worker processed it |
| Worker acquires send right | **SENDING** | DB claim succeeded | Provider accepted it |
| JavaMailSender returns normally | **ACCEPTED_BY_SMTP** | SMTP/provider accepted command per contract | Inbox received it, no bounce |
| Authenticated provider feedback | **DELIVERED/BOUNCED** if supported | Feedback came from provider per event semantics | User read it |
| Provider temporarily rejects, confirmed not received | **RETRY_WAIT** | Safe to schedule retry per policy | Not every SMTP exception is safe to retry |
| Bad recipient/policy violation | **FAILED_PERMANENT** | Automated retries stop in this state | Data cannot be fixed and re-submitted |
| Timeout/crash with unclear SMTP outcome | **UNKNOWN** | Insufficient proof of send outcome | Resending won't duplicate |

**ACCEPTED_BY_SMTP does not mean DELIVERED.** A message can bounce, hit spam filters, or fail at a downstream mail server. Knowing whether delivery succeeded requires reliable webhooks or bounce processing; a standard SMTP response does not provide that.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: HTTP transaction creates delivery + outbox
    PENDING --> SENDING: Worker atomic claim
    SENDING --> ACCEPTED_BY_SMTP: SMTP accepts and DB commits
    SENDING --> RETRY_WAIT: Confirmed temporary rejection
    RETRY_WAIT --> PENDING: Scheduler creates new outbox dispatch
    SENDING --> FAILED_PERMANENT: Invalid data or permanent rejection
    SENDING --> UNKNOWN: Uncertain outcome / lease expired
    ACCEPTED_BY_SMTP --> DELIVERED: Verified provider feedback
    ACCEPTED_BY_SMTP --> BOUNCED: Verified provider bounce
    UNKNOWN --> ACCEPTED_BY_SMTP: Reconciliation finds it was accepted
    UNKNOWN --> RETRY_WAIT: Operator permits retry with logged risk
    UNKNOWN --> FAILED_PERMANENT: Stop decision after investigation
~~~

Never automatically return **UNKNOWN** to `PENDING` solely because a lease expired: the worker may have sent the email before failing to update the DB. A policy prioritizing *no duplicate emails* reconciles or requires operator approval before retrying. A policy prioritizing *deliver at all costs* may accept duplicate risk, provided it is explicitly documented in the contract.

## 3. Architecture: HTTP → DB Outbox → RabbitMQ → SMTP

~~~mermaid
flowchart TD
    A["Order service / HTTP caller"] -->|"POST + Idempotency-Key"| B["Email Request API"]
    B --> C["PostgreSQL transaction"]
    C --> D["email_delivery PENDING"]
    C --> E["email_outbox EmailSendRequested"]
    B -->|"202 + deliveryId"| F["GET status API"]
    D --> F
    E --> G["Outbox relay"]
    G -->|"Publisher confirm + routing"| H["RabbitMQ durable queue"]
    H --> I["Mail worker"]
    I -->|"Atomic claim / attempt token"| D
    I --> J["Template renderer"]
    J --> K["JavaMailSender / SMTP"]
    K -->|"Success/failure/unknown"| D
    I -->|"ACK after durable outcome"| H
    D --> L["Retry scheduler / reconciler"]
    L -->|"Due RETRY_WAIT"| E
    L -->|"Expired SENDING → UNKNOWN"| D
    H -->|"Malformed message"| M["Dead-letter/quarantine"]
~~~

**The database holds the source-of-truth state**; RabbitMQ transports work items rather than guaranteeing email uniqueness. HTTP does not wait for SMTP and responds right after DB commit. The relay may publish duplicates if the broker accepts a message while the DB fails to mark published; hence workers always check DB state and claim rather than assuming every message is fresh.

A minimal work message:

~~~json
{
  "eventId": "8fd73fc8-c870-4ef9-aa22-2b85c3190b36",
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "schemaVersion": 1
}
~~~

Workers fetch the recipient, template, and variables from the DB; avoid stuffing full HTML, email addresses, or PII into the queue. **`eventId`** identifies a single broker dispatch, while **`deliveryId`** identifies a logical send request. Neither automatically guarantees SMTP idempotency.

## 4. Dependencies and Connection Configuration

Example Maven with Spring Boot parent/BOM version management, Java 17+:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

The snippets use Spring Boot 3.x APIs (`jakarta.mail`, `jakarta.validation`, `@RabbitListener`); for Spring Boot 4.x, check starters/modules and packages for your version. Use a migration tool like Flyway/Liquibase if schema migrations are standardized.

### 4.1. application.yml Without Real Secrets

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
  rabbitmq:
    addresses: ${RABBITMQ_ADDRESSES}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        prefetch: 5
        concurrency: 2
        max-concurrency: 6
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  email:
    from-address: ${EMAIL_FROM_ADDRESS}
    work-queue: email.send.work
    work-exchange: email.work.exchange
    work-routing-key: email.send
    max-attempts: 5
    sending-lease: 2m
~~~

JavaMail/Jakarta Mail specifies SMTP timeouts in **milliseconds**. If omitted, some timeouts default to infinite and tie up workers indefinitely. Verify STARTTLS, TLS certificate/hostname validation, port 465/587, sender domain, permissions, and provider rate limits; never disable TLS verification to "test things" in production. Supply URLs and credentials from runtime/secret managers, never committing or logging them.

### 4.2. RabbitMQ Topology

~~~text
Direct exchange: email.work.exchange (durable)
    routing key: email.send
        → durable queue: email.send.work
             → workers

Dead-letter exchange: email.work.dlx
    → durable quarantine queue: email.send.dlq
~~~

The broker must have matching exchanges, bindings, durable queues, and DLX policies. Publishers send **persistent messages** with **publisher confirms + returns/mandatory** to distinguish broker acceptance from unroutable returns. An `ack=true` confirm alone does not prove the routing key delivered the message to a queue without checking returns. DLQs are for unprocessable work messages; **SMTP failures for valid deliveries are tracked primarily in the DB**, never solely by inspecting the DLQ.

## 5. PostgreSQL Schema Design

~~~sql
CREATE TABLE email_delivery (
    id                   UUID PRIMARY KEY,
    tenant_id            VARCHAR(80) NOT NULL,
    idempotency_key      VARCHAR(180) NOT NULL,
    request_fingerprint  CHAR(64) NOT NULL,
    recipient_address    TEXT NOT NULL,
    template_key         VARCHAR(100) NOT NULL,
    template_version     INTEGER NOT NULL,
    variables_json       JSONB NOT NULL,
    status               VARCHAR(32) NOT NULL,
    attempt_count        INTEGER NOT NULL DEFAULT 0,
    attempt_token        UUID,
    lease_until          TIMESTAMPTZ,
    next_attempt_at      TIMESTAMPTZ,
    last_error_kind      VARCHAR(60),
    smtp_accepted_at     TIMESTAMPTZ,
    provider_message_id  TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_email_idempotency
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ck_email_status CHECK (status IN (
        'PENDING', 'SENDING', 'RETRY_WAIT',
        'ACCEPTED_BY_SMTP', 'FAILED_PERMANENT',
        'UNKNOWN', 'DELIVERED', 'BOUNCED'
    )),
    CONSTRAINT ck_email_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX ix_email_retry_due
    ON email_delivery (status, next_attempt_at);
CREATE INDEX ix_email_sending_lease
    ON email_delivery (status, lease_until);

CREATE TABLE email_outbox (
    id                UUID PRIMARY KEY,
    delivery_id       UUID NOT NULL REFERENCES email_delivery(id),
    dispatch_no       INTEGER NOT NULL,
    event_type        VARCHAR(50) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at      TIMESTAMPTZ,
    claim_token       UUID,
    claim_until       TIMESTAMPTZ,
    publish_attempts  INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_email_dispatch UNIQUE (delivery_id, dispatch_no)
);

CREATE INDEX ix_email_outbox_pending
    ON email_outbox (published_at, claim_until, created_at);

CREATE TABLE email_delivery_history (
    id             BIGSERIAL PRIMARY KEY,
    delivery_id    UUID NOT NULL REFERENCES email_delivery(id),
    from_status    VARCHAR(32),
    to_status      VARCHAR(32) NOT NULL,
    error_kind     VARCHAR(60),
    actor          VARCHAR(40) NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Explanation:

- `email_delivery` holds the **current send state**, validated payload, and duplicate-request lock.
- `request_fingerprint` catches reuse of an idempotency key with a different payload; computed from normalized data, never `Map.toString()`.
- `email_outbox` stores **publish intent** committed alongside the delivery; `dispatch_no=0` for the first dispatch, `1...` for intentional requeues.
- `email_delivery_history` records state transitions (without raw bodies or passwords) for auditing.
- `attempt_token` ties result-update rights to a single claim; `lease_until` detects dead workers. **Lease expiration does not prove the email was not sent.**

Verify schemas, indexes, and permissions with migrations; never create tables dynamically per message. For personal data, enforce encryption, access controls, retention, backups, and deletion per policy. Never write raw recipients, bodies, or tokens to metrics or logs.

### 5.1. Properly Scoped Idempotency Keys

A key should identify **one intentional email**: tenant + business event + purpose/template + logical recipient + version if versions alter content.

~~~text
tenant = shop-east
event = order-confirmed:O-204:v3
recipientRole = primary-customer
purpose = order-confirmation
templateVersion = 2

Idempotency-Key =
order-confirmed:O-204:v3:primary-customer:order-confirmation:v2
~~~

Never use RabbitMQ `deliveryTag`/`JMSMessageID`, a fresh UUID per HTTP retry, or the current timestamp as a **business idempotency key**. If one event emails two recipients, represent them as **two distinct deliveries**. Avoid embedding raw email addresses in keys/logs; also do not strip dots, `+tags`, or lowercase local-parts globally based on one provider's rules.

### 5.2. Request Fingerprinting

Compute the fingerprint from **recipient, templateKey, templateVersion, and variables** after canonical JSON serialization with deterministic key ordering and published normalization rules. Same key + same fingerprint → return existing delivery. Same key + different fingerprint → **409 Conflict**; never mutate an in-flight request.

If a fingerprint could expose PII via brute-force guessing, use HMAC with a managed secret key. Never log raw fingerprints alongside all email variables.

## 6. HTTP API Accepting Send Requests

### 6.1. REST Contract

~~~http
POST /api/email-deliveries
Idempotency-Key: order-confirmed:O-204:v3:primary-customer:v2
Content-Type: application/json

{
  "recipient": "customer@example.invalid",
  "templateKey": "order-confirmation",
  "templateVersion": 2,
  "variables": {
    "orderCode": "O-204",
    "customerDisplayName": "Customer"
  }
}
~~~

The API responds only after a successful DB commit:

~~~http
HTTP/1.1 202 Accepted
Location: /api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f
Content-Type: application/json

{
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "status": "PENDING",
  "statusUrl": "/api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f"
}
~~~

**202 Accepted does not mean the email has been sent.** HTTP callers must poll GET status or use verified callbacks to track progress. Authenticate tenants, enforce rate limits, and validate allowed templates and recipient addresses to prevent the API from becoming an **open mail relay**.

### 6.2. Request DTOs

~~~java
public record SendEmailRequest(
        @NotBlank String recipient,
        @NotBlank String templateKey,
        @Min(1) int templateVersion,
        @NotNull Map<String, String> variables) {
}

public record EmailAccepted(
        UUID deliveryId, String status, URI statusUrl) {
}
~~~

Bean Validation annotations do not replace validating sender/recipient domains, JSON size, template authorization, HTML safety, or required template variables. Idempotency keys need length/format bounds and must remain identical across caller HTTP retries.

### 6.3. Creating Delivery and Outbox in One Transaction

~~~java
@Service
public class EmailRequestService {
    private final JdbcTemplate jdbc;
    private final EmailRequestFingerprint fingerprintService;

    public EmailRequestService(
            JdbcTemplate jdbc,
            EmailRequestFingerprint fingerprintService) {
        this.jdbc = jdbc;
        this.fingerprintService = fingerprintService;
    }

    @Transactional
    public UUID accept(
            String authenticatedTenant,
            String key,
            SendEmailRequest request) {

        validateCommand(authenticatedTenant, key, request);
        String fingerprint =
                fingerprintService.sha256Canonical(request);
        UUID newId = UUID.randomUUID();

        int inserted = jdbc.update("""
            INSERT INTO email_delivery (
                id, tenant_id, idempotency_key,
                request_fingerprint, recipient_address,
                template_key, template_version,
                variables_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?::jsonb, 'PENDING')
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            """,
            newId, authenticatedTenant, key,
            fingerprint, request.recipient(),
            request.templateKey(), request.templateVersion(),
            fingerprintService.toCanonicalJson(request.variables()));

        if (inserted == 1) {
            jdbc.update("""
                INSERT INTO email_outbox (
                    id, delivery_id, dispatch_no, event_type)
                VALUES (?, ?, 0, 'EmailSendRequested')
                """, UUID.randomUUID(), newId);
            return newId;
        }

        ExistingRequest previous = jdbc.queryForObject("""
            SELECT id, request_fingerprint
            FROM email_delivery
            WHERE tenant_id = ? AND idempotency_key = ?
            """,
            (rs, index) -> new ExistingRequest(
                    rs.getObject("id", UUID.class),
                    rs.getString("request_fingerprint")),
            authenticatedTenant, key);

        if (previous == null
                || !previous.fingerprint().equals(fingerprint)) {
            throw new IdempotencyConflictException(
                    "Key already used for different email contents");
        }
        return previous.id();
    }

    private record ExistingRequest(UUID id, String fingerprint) {}

    private void validateCommand(
            String tenant, String key, SendEmailRequest request) {
        // Validate tenant authorization, key length and format,
        // approved template, recipient syntax and payload size.
    }
}
~~~

**`EmailRequestFingerprint`** and **`IdempotencyConflictException`** are application-provided types; completing `validateCommand` is mandatory before production. PostgreSQL unique `(tenant_id,idempotency_key)` provides real concurrency protection: two parallel requests with the same key cannot both create records. Under `READ COMMITTED`, the second transaction waits for the first and then reads the committed request to compare fingerprints.

If inserting the outbox fails, the transaction rolls back the delivery too. If the HTTP response is lost after commit, retrying with the same key returns the existing ID. On fingerprint mismatch, map the exception to **HTTP 409 Conflict** rather than silently altering the recipient or template of a pending delivery.

### 6.4. Controller and Tenant Boundary

~~~java
@RestController
@RequestMapping("/api/email-deliveries")
public class EmailDeliveryController {
    private final EmailRequestService requests;
    private final EmailDeliveryQuery queries;

    public EmailDeliveryController(
            EmailRequestService requests,
            EmailDeliveryQuery queries) {
        this.requests = requests;
        this.queries = queries;
    }

    @PostMapping
    ResponseEntity<EmailAccepted> accept(
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody SendEmailRequest command,
            Authentication authentication) {
        String tenant = authenticatedTenant(authentication);
        UUID id = requests.accept(tenant, key, command);
        URI location = URI.create("/api/email-deliveries/" + id);
        return ResponseEntity.accepted()
                .location(location)
                .body(new EmailAccepted(
                        id, queries.status(tenant, id), location));
    }
}
~~~

**`EmailDeliveryQuery`** and **`authenticatedTenant(Authentication)`** are illustrative abstractions implemented by the application. Always extract the tenant from the verified authenticated identity; never trust a client-supplied `X-Tenant-Id` header. Returning `PENDING` directly from the service can save a query; this snippet demonstrates the REST contract. Never publish to RabbitMQ or call SMTP from the HTTP controller before DB commit.

## 7. Outbox Relay: Confirmed RabbitMQ Publishing

The outbox relay polls unpublished `email_outbox` rows, publishes `EmailWorkMessage` to RabbitMQ, and updates status once valid publish proof arrives.

~~~text
HTTP DB transaction
  └── INSERT email_delivery + email_outbox
       └── COMMIT
            └── Outbox relay claims pending rows
                 └── RabbitTemplate publishes persistent message
                      └── Publisher confirm + mandatory return check
                           └── Mark email_outbox.published_at
~~~

### 7.1. Short Outbox Claims Without Holding Transactions Across Broker Calls

Across multiple relay instances, claim batches in PostgreSQL:

~~~sql
WITH due AS (
    SELECT id
    FROM email_outbox
    WHERE published_at IS NULL
      AND (claim_until IS NULL OR claim_until < now())
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE email_outbox o
SET claim_token = :relay_token,
    claim_until = now() + interval '30 seconds',
    publish_attempts = publish_attempts + 1
FROM due
WHERE o.id = due.id
RETURNING o.id, o.delivery_id, o.dispatch_no, o.claim_token;
~~~

This is reference PostgreSQL SQL with repository-bound named parameters. The transaction covers only **claiming and committing immediately**, then calls the broker outside DB transactions. When publish succeeds and the token still matches:

~~~sql
UPDATE email_outbox
SET published_at = now(),
    claim_token = NULL,
    claim_until = NULL
WHERE id = :event_id
  AND claim_token = :relay_token
  AND published_at IS NULL;
~~~

If the relay crashes **after RabbitMQ accepts the message but before the DB records `published_at`**, the outbox row will be republished. A standard DB transaction cannot eliminate that two-system commit gap. **Workers must be idempotent by `deliveryId` and DB state**, never relying solely on broker message IDs to drop duplicates.

### 7.2. Publisher Confirms and Unroutable Returns

Spring AMQP's `RabbitTemplate` uses `CorrelationData` to observe confirms and returns. Example for Spring AMQP 3.x:

~~~java
public record EmailWorkMessage(
        UUID eventId, UUID deliveryId, int schemaVersion) {
}

@Component
public class ConfirmingWorkPublisher {
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;

    public ConfirmingWorkPublisher(
            RabbitTemplate rabbit, ObjectMapper mapper) {
        this.rabbit = rabbit;
        this.mapper = mapper;
    }

    public void publish(UUID eventId, UUID deliveryId) {
        try {
            String json = mapper.writeValueAsString(
                    new EmailWorkMessage(eventId, deliveryId, 1));
            CorrelationData correlation =
                    new CorrelationData(eventId.toString());

            rabbit.convertAndSend(
                    "email.work.exchange", "email.send", json,
                    message -> {
                        message.getMessageProperties()
                                .setMessageId(eventId.toString());
                        message.getMessageProperties()
                                .setDeliveryMode(
                                        MessageDeliveryMode.PERSISTENT);
                        return message;
                    },
                    correlation);

            CorrelationData.Confirm confirmed =
                    correlation.getFuture().get(5, TimeUnit.SECONDS);
            if (!confirmed.isAck()
                    || correlation.getReturn() != null) {
                throw new IllegalStateException(
                        "Broker did not confirm routable work");
            }
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Invalid email work payload", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted waiting for broker confirm", ex);
        } catch (ExecutionException | TimeoutException ex) {
            throw new IllegalStateException(
                    "Publisher outcome uncertain; keep outbox", ex);
        }
    }
}
~~~

Main imports include `RabbitTemplate`, `CorrelationData`, `MessageDeliveryMode`, `ObjectMapper`, `JsonProcessingException`, `TimeUnit`, `ExecutionException`, and `TimeoutException`. Waiting on the confirm future is **blocking**, so run it in an outbox relay worker, never on a Reactor event loop. Verify API signatures against your Spring AMQP version and confirm that publisher confirms + returns are genuinely enabled.

**Confirm ACK is not "email sent."** It only proves the broker acknowledged publishing at the protocol level; without checking returns, a message could even be unroutable. A timeout waiting for confirm represents an **uncertain publish outcome**: keep the outbox row to retry, accepting the possibility of duplicate publishing.

## 8. Atomic Claim: Guarding Against Concurrent Workers and Redeliveries

A RabbitMQ queue may redeliver after a lost ACK or receive duplicate events from relay retries. In-process Java locks do not span multiple application instances. Every send attempt must acquire an **atomic compare-and-set** claim in PostgreSQL:

~~~sql
UPDATE email_delivery
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    attempt_token = :new_attempt_token,
    lease_until = now() + interval '2 minutes',
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'PENDING'
RETURNING
    id, tenant_id, recipient_address,
    template_key, template_version,
    variables_json, attempt_count, attempt_token;
~~~

If worker A claims successfully, worker B updates **0 rows** and **must not call SMTP**. If a message arrives while the delivery is `SENDING`, `RETRY_WAIT`, `UNKNOWN`, or already in a terminal state, the worker skips it according to the state machine.

### 8.1. Three Real Boundaries

~~~text
DB Transaction #1: claim → SENDING + attemptToken → COMMIT
       ↓
SMTP network operation (outside DB transactions)
       ↓
DB Transaction #2: record outcome by attemptToken → COMMIT
       ↓
RabbitMQ ACK of delivery
~~~

Never hold a DB transaction open while waiting on SMTP: rolling back PostgreSQL cannot unsend an email already accepted by a mail server. Holding transactions across network calls also causes long locks, holds connections, and drives up latency.

### 8.2. Recording Results with a Fencing Token

Once SMTP returns success:

~~~sql
UPDATE email_delivery
SET status = 'ACCEPTED_BY_SMTP',
    smtp_accepted_at = now(),
    attempt_token = NULL,
    lease_until = NULL,
    last_error_kind = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'SENDING'
  AND attempt_token = :attempt_token;
~~~

**You must verify updated row count = 1** and write the transition history in the same transaction. If the token no longer matches, never overwrite the state or claim "sent"; the lease may have expired and the reconciler transitioned to `UNKNOWN`. `attempt_token` acts as a fencing token preventing late updates from clobbering newer outcomes.

### 8.3. Lease Expiration Does Not Prove No Email Was Sent

~~~sql
UPDATE email_delivery
SET status = 'UNKNOWN',
    last_error_kind = 'worker_lease_expired',
    updated_at = now()
WHERE status = 'SENDING'
  AND lease_until < now()
RETURNING id, attempt_token;
~~~

The reconciler transaction must record history/audit entries and alert on rows transitioning to `UNKNOWN`. **Never automatically reset back to `PENDING` to resend.** The worker may have crashed before calling SMTP, or it may have sent successfully and crashed before updating the DB. Only provider reconciliation or an explicit duplicate-tolerant policy should authorize retrying.

Leases must exceed total SMTP timeouts + rendering + DB update margin; under high latency variance, consider worker heartbeats/monitoring, though heartbeats still cannot reveal an SMTP outcome after a crash.

### 8.4. Duplicate Message Handling Matrix

| DB State When Worker Receives Message | Call SMTP? | Decision |
| --- | --- | --- |
| `PENDING` and claim succeeds | **Yes** | Start new attempt |
| `PENDING` and claim loses | **No** | ACK duplicate after verifying state |
| `SENDING` | **No** | ACK duplicate; reconciler monitors lease |
| `RETRY_WAIT` | **No** | ACK early message; scheduler owns next trigger |
| `ACCEPTED_BY_SMTP`, `DELIVERED`, `BOUNCED` | **No** | ACK duplicate |
| `FAILED_PERMANENT` | **No** | ACK duplicate, retain error state |
| `UNKNOWN` | **No** | ACK duplicate, await reconciliation |
| Missing delivery / invalid schema | **No** | Controlled quarantine/DLQ |

## 9. JavaMailSender: Templates, Transport, and Payload Safety

Never accept arbitrary HTML/subjects or unvalidated `From` addresses from callers. Use approved, versioned, auto-escaping templates:

~~~java
public record RenderedEmail(
        String subject, String html, String plainText) {
}

public interface EmailTemplateRenderer {
    RenderedEmail render(
            String templateKey,
            int templateVersion,
            Map<String, String> variables);
}
~~~

An implementation can use Thymeleaf or an equivalent engine with a template-key allowlist, variable validation, HTML escaping, body size caps, and header CRLF-injection protection. **Template version must stay fixed across retries**; never silently change the content of an already-accepted delivery.

~~~java
@Component
public class SmtpEmailTransport {
    private final JavaMailSender mailSender;
    private final EmailTemplateRenderer renderer;
    private final String from;

    public SmtpEmailTransport(
            JavaMailSender mailSender,
            EmailTemplateRenderer renderer,
            @Value("${app.email.from-address}") String from) {
        this.mailSender = mailSender;
        this.renderer = renderer;
        this.from = from;
    }

    public void send(ClaimedDelivery claim)
            throws MessagingException {
        RenderedEmail content = renderer.render(
                claim.templateKey(), claim.templateVersion(),
                claim.variables());

        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                mime, true, StandardCharsets.UTF_8.name());
        helper.setFrom(from);
        helper.setTo(claim.recipient());
        helper.setSubject(content.subject());
        helper.setText(
                content.plainText(), content.html());

        // Correlation header only; does NOT deduplicate at SMTP.
        mime.setHeader(
                "X-Email-Delivery-Id", claim.id().toString());
        mailSender.send(mime);
    }
}
~~~

`ClaimedDelivery` is the DTO constructed by the repository from the claimed row; main imports are `JavaMailSender`, `MimeMessageHelper`, `jakarta.mail.internet.MimeMessage`, `jakarta.mail.MessagingException`, `StandardCharsets`, and `@Value`. `setText(plain,html)` generates multipart alternative content so mail clients can choose their rendering format.

### 9.1. SMTP Returning Success Does Not Prove Inbox Delivery

- `JavaMailSender` returning normally only proves the **SMTP handoff** succeeded per the provider's response at that moment.
- `Message-ID` or custom headers **do not** compel an SMTP provider to perform idempotency.
- A message can still bounce or hit spam filtering after server acceptance.
- When using a provider HTTP API with documented idempotency keys, verify exact key retention windows and per-endpoint semantics; **never extrapolate that from `Message-ID` headers**.
- Send **one recipient per delivery** so partial failures and duplicate prevention stay clean instead of bundling multiple recipients into one email.

### 9.2. Conservative SMTP Error Classification

| Failure | Evidence | Recommended Decision |
| --- | --- | --- |
| Invalid template or malformed address pre-send | Invalid request | `FAILED_PERMANENT` |
| Server returns clear rejection proving message was not accepted | Definitive phase-specific response | `RETRY_WAIT` for retryable 4xx, permanent for appropriate 5xx |
| Auth failure / permission blocked | Configuration or credential issue | Alert; do not hot-retry |
| Socket timeout / connection drop around DATA/ACK | Uncertain whether server accepted | **`UNKNOWN`**, reconcile before retrying |
| `JavaMailSender.send` returns normally | SMTP handoff succeeded | `ACCEPTED_BY_SMTP` |
| DB write fails after SMTP send | Email may already be accepted | Never falsely ACK; reconciler handles `UNKNOWN` |

Classifying **`MailException`** solely by Java class is rarely enough: Spring Mail wraps many errors, and an `IOException` can occur **after** SMTP already accepted `DATA`. Default to **`UNKNOWN`** whenever server rejection cannot be proven. Even for confirmed temporary errors, once the retry budget runs out, stop automated retries or escalate per policy instead of looping forever.

## 10. RabbitMQ Listener: ACK Only After Durable Outcome Persistence

In Spring AMQP, `@RabbitListener(ackMode="MANUAL")` with `Channel.basicAck` lets you ACK **after** the worker commits its status update in PostgreSQL:

~~~java
@Component
public class EmailWorkListener {
    private final ObjectMapper mapper;
    private final EmailDeliveryProcessor processor;

    public EmailWorkListener(
            ObjectMapper mapper,
            EmailDeliveryProcessor processor) {
        this.mapper = mapper;
        this.processor = processor;
    }

    @RabbitListener(
            queues = "${app.email.work-queue}",
            ackMode = "MANUAL")
    public void consume(
            String raw,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long tag)
            throws IOException {

        final EmailWorkMessage work;
        try {
            work = mapper.readValue(raw, EmailWorkMessage.class);
            if (work.eventId() == null
                    || work.deliveryId() == null
                    || work.schemaVersion() != 1) {
                throw new IllegalArgumentException(
                        "Unsupported work message");
            }
        } catch (JsonProcessingException | IllegalArgumentException ex) {
            // Only when DLX/quarantine queue is configured and tested.
            channel.basicReject(tag, false);
            return;
        }

        try {
            processor.process(work);
            channel.basicAck(tag, false);
        } catch (UnknownDeliveryException invalidReference) {
            channel.basicReject(tag, false);
        } catch (DataAccessException databaseUnavailable) {
            // Must have backoff/delayed-requeue/pause policy on broker.
            channel.basicNack(tag, false, true);
        }
    }
}
~~~

Imports include Spring AMQP `@RabbitListener` and `AmqpHeaders`, RabbitMQ `com.rabbitmq.client.Channel`, Spring Messaging `@Header`, Jackson `ObjectMapper`, Spring DAO `DataAccessException`, and Java `IOException`. Domain exceptions in the example are application-defined.

**Caution:** `basicNack(...,requeue=true)` can cause a **hot requeue loop** when the database is unreachable; production needs broker-delayed retries, consumer pause/backoff, quorum delivery limits, or a strategy to halt consumers and alert. If durable state cannot be persisted, **never ACK as success**.

`basicReject(requeue=false)` **does not automatically verify** the message landed in the DLQ if DLX/routing is broken or broker limits block it. Test DLQ ingress, queue depth, and recovery paths; never use `nullChannel` or log-only recovery as durable storage.

### 10.1. Processor: Claim, Send, Record Outcome

Repository abstraction:

~~~java
public interface EmailDeliveryRepository {
    ClaimDecision claim(UUID id, UUID newAttemptToken);
    void markAccepted(UUID id, UUID attemptToken);
    void markPermanent(
            UUID id, UUID attemptToken, String errorKind);
    void markRetryWait(
            UUID id, UUID attemptToken,
            String errorKind, Instant nextAttempt);
    void markUnknown(
            UUID id, UUID attemptToken, String errorKind);
}

public sealed interface ClaimDecision
        permits ClaimDecision.Acquired,
                ClaimDecision.Skip, ClaimDecision.Missing {

    record Acquired(ClaimedDelivery delivery)
            implements ClaimDecision {}
    record Skip(String reason) implements ClaimDecision {}
    record Missing() implements ClaimDecision {}
}

public enum SmtpFailureKind {
    KNOWN_TEMPORARY,
    KNOWN_PERMANENT,
    UNCERTAIN
}

public interface SmtpErrorClassifier {
    SmtpFailureKind classify(Throwable error);
}
~~~

`ClaimedDelivery` is the DTO returned by the SQL claim (ID, recipient, template, variables, attemptCount, attemptToken). The repository must implement methods via **short transactions** and **fencing updates** `WHERE status='SENDING' AND attempt_token=?`. All state transitions and history rows commit in the same DB transaction. If 0 rows are updated, never return success.

Orchestration:

~~~java
@Service
public class EmailDeliveryProcessor {
    private static final int MAX_ATTEMPTS = 5;

    private final EmailDeliveryRepository repository;
    private final SmtpEmailTransport smtp;
    private final SmtpErrorClassifier classifier;

    public EmailDeliveryProcessor(
            EmailDeliveryRepository repository,
            SmtpEmailTransport smtp,
            SmtpErrorClassifier classifier) {
        this.repository = repository;
        this.smtp = smtp;
        this.classifier = classifier;
    }

    public void process(EmailWorkMessage work) {
        UUID token = UUID.randomUUID();
        ClaimDecision decision =
                repository.claim(work.deliveryId(), token);

        if (decision instanceof ClaimDecision.Missing) {
            throw new UnknownDeliveryException(work.deliveryId());
        }
        if (decision instanceof ClaimDecision.Skip) {
            return;  // Skip SMTP if terminal/in-flight/not-due.
        }

        ClaimedDelivery claim =
                ((ClaimDecision.Acquired) decision).delivery();

        try {
            smtp.send(claim);
        } catch (InvalidEmailInputException | EmailTemplateContractException ex) {
            repository.markPermanent(
                    claim.id(), token, "invalid_email_or_template");
            return;
        } catch (MailException | MessagingException ex) {
            SmtpFailureKind kind = classifier.classify(ex);
            if (kind == SmtpFailureKind.KNOWN_PERMANENT) {
                repository.markPermanent(
                        claim.id(), token, "smtp_permanent_rejection");
            } else if (kind == SmtpFailureKind.KNOWN_TEMPORARY
                    && claim.attemptCount() < MAX_ATTEMPTS) {
                repository.markRetryWait(
                        claim.id(), token, "smtp_temporary_rejection",
                        nextAttemptAt(claim.attemptCount()));
            } else if (kind == SmtpFailureKind.KNOWN_TEMPORARY) {
                repository.markPermanent(
                        claim.id(), token, "retry_budget_exhausted");
            } else {
                repository.markUnknown(
                        claim.id(), token, "uncertain_smtp_result");
            }
            return;
        }

        repository.markAccepted(claim.id(), token);
        // Return only after DB outcome commits successfully.
    }

    private Instant nextAttemptAt(int attemptNumber) {
        long base = Math.min(900L,
                30L << Math.min(attemptNumber - 1, 5));
        long jitter =
                ThreadLocalRandom.current().nextLong(0L, 15L);
        return Instant.now().plusSeconds(base + jitter);
    }
}
~~~

**`InvalidEmailInputException`, `EmailTemplateContractException`, `UnknownDeliveryException`, `ClaimedDelivery`**, and repository implementations belong to application code, not Spring APIs. `MAX_ATTEMPTS=5` and backoff are examples: production should bind them via `@ConfigurationProperties`, validate positive bounds, and honor provider rate limits/`Retry-After`. Code must handle **template rendering errors** under the taxonomy: missing templates or invalid variables become permanent errors with persisted status rather than throwing `RuntimeException` and requeuing forever.

`MailException | MessagingException` catches only anticipated send errors. Programming bugs, misconfigured beans, or dropped database connections must **not** be swallowed under "retry SMTP"; unexpected failures must route to the proper error/alert layer.

### 10.2. Crashes and ACK Ordering

| Crash Point | DB State | RabbitMQ | Consequence and Handling |
| --- | --- | --- | --- |
| Before claim | `PENDING` | Redelivers if unacked | Subsequent worker can claim |
| After claim, before SMTP | `SENDING` | May redeliver | No duplicate send; lease expiry → `UNKNOWN`, requires verification |
| After SMTP accepted, before DB mark | `SENDING` | May redeliver | **`UNKNOWN`** after lease, no automatic resend |
| After DB marks `ACCEPTED_BY_SMTP`, before ACK | `ACCEPTED_BY_SMTP` | May redeliver | Worker sees terminal state and ACKs without re-sending SMTP |
| ACK sent yet broker connection drops | Durable state | Broker may redeliver | Deduplicate via `deliveryId`/status |
| In `RETRY_WAIT` when stale message arrives | `RETRY_WAIT` | Redelivery | ACK old message; scheduler emits new dispatch when due |

**This is at-least-once message processing with best-effort duplicate prevention**, not exactly-once SMTP. Crashing before SMTP and landing in `UNKNOWN` can leave an email unsent without reconciliation; this is an explicit trade-off of preferring no duplicate sends.

## 11. Scheduled Retries and Handling UNKNOWN Jobs

### 11.1. Never Use Hot Requeues for Temporary SMTP Errors

When the provider **definitively rejects temporarily** and attempts remain, the worker persists:

~~~sql
UPDATE email_delivery
SET status = 'RETRY_WAIT',
    next_attempt_at = :scheduled_at,
    last_error_kind = :error_kind,
    attempt_token = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'SENDING'
  AND attempt_token = :attempt_token;
~~~

After committing **`RETRY_WAIT`** and history to the DB, ACK the old work message. A scheduler polls due rows:

~~~sql
SELECT id, attempt_count
FROM email_delivery
WHERE status = 'RETRY_WAIT'
  AND next_attempt_at <= now()
ORDER BY next_attempt_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Within **the same scheduler transaction**, for each locked row: set status back to `PENDING`, clear `next_attempt_at`, and insert a new outbox event with `dispatch_no = attempt_count` and a fresh event UUID; `UNIQUE (delivery_id,dispatch_no)` prevents duplicate dispatches. **Never commit `PENDING` before inserting the outbox row.**

~~~text
RETRY_WAIT + next_attempt_at due
     → DB transaction:
          UPDATE delivery SET status=PENDING
          INSERT outbox(dispatch_no=attempt_count)
       COMMIT
     → Outbox relay publishes
     → Worker claims next attempt
~~~

For attempts `1,2,...`, `dispatch_no=1,2,...` suffices when each attempt schedules at most one retry. If operators can also trigger manual retries or redrives independent of attempt count, add a dedicated incrementing **dispatch sequence** updated transactionally to avoid unique-key collisions.

### 11.2. Budgets and Error Classification

The retry policy requires:

- Bounded **maximum attempts**, never multiplying infinitely across SMTP client, RabbitMQ, and HTTP caller retries.
- **Exponential backoff + jitter** honoring `Retry-After` and provider quotas when present.
- Separating permanent errors (invalid recipient, missing template) from transient ones (verified SMTP 4xx).
- **Never auto-retrying `UNKNOWN`** unless the provider offers lookup/idempotency or an operator explicitly accepts duplicate risk.
- Bounding concurrent sends/prefetch to avoid exhausting connections, hitting rate limits, or harming sender reputation.

### 11.3. Reconciling UNKNOWN Deliveries

A periodic reconciler scans `UNKNOWN` deliveries, retaining full **attempt token, correlation, Message-ID/provider ID, and timestamps** in a safe audit log. Workflow:

1. If the provider exposes a transaction lookup API by key/message ID, query real status using least-privilege credentials.
2. If confirmed accepted, transition to `ACCEPTED_BY_SMTP` (do not assume `DELIVERED`).
3. If proven **not** accepted and business policy permits, move to `RETRY_WAIT` via an audited transition and new dispatch.
4. If the provider does not support verification, keep `UNKNOWN`, alert operations, or record an explicit **accept duplicate risk** retry decision.
5. Never let `UNKNOWN` disappear from dashboards or get purged by overly short retention.

**Plain SMTP provides no universal reconciliation API.** `Message-ID` headers can help search provider logs, though providers are not obligated to expose lookup endpoints. In that case, "do not auto-resend on `UNKNOWN`" acts as a *duplicate-reduction safeguard*, not a guarantee every request gets delivered.

## 12. Tracking Results via API, Not Queue Depth

Authenticated, authorized status lookup endpoint:

~~~http
GET /api/email-deliveries/73de4c12-7a47-4566-b810-d92b18cab27f
Authorization: Bearer ...
~~~

Example response:

~~~json
{
  "deliveryId": "73de4c12-7a47-4566-b810-d92b18cab27f",
  "status": "RETRY_WAIT",
  "attemptCount": 2,
  "nextAttemptAt": "2026-11-21T10:10:00Z",
  "smtpAcceptedAt": null,
  "lastErrorKind": "smtp_temporary_rejection",
  "updatedAt": "2026-11-21T10:08:00Z"
}
~~~

The API returns only deliveries owned by tenants the principal is authorized to read. Queries must include both `delivery_id` **and** `tenant_id`, e.g.:

~~~sql
SELECT id, status, attempt_count,
       next_attempt_at, smtp_accepted_at,
       last_error_kind, updated_at
FROM email_delivery
WHERE id = :delivery_id
  AND tenant_id = :authenticated_tenant;
~~~

If not found, return 404 or a uniform error response per anti-enumeration policy. Never expose recipients/bodies, SMTP credentials, stack traces, or raw provider responses to ordinary callers. An admin endpoint for inspecting history can be provided with separate authorization and access auditing.

### 12.1. Never Label SMTP Success as "Delivered"

With `JavaMailSender` + SMTP alone, clients should see **`ACCEPTED_BY_SMTP`**. When integrating provider webhooks/bounces:

- Verify signatures, timestamps/replay protection, and webhook sender authenticity.
- Extract a unique **provider event ID** and persist it to deduplicate repeated webhooks.
- Match `provider_message_id`/correlation to the delivery ID; never trust unverified event IDs from requests.
- Tolerate delayed or out-of-order events; prevent older status events from overwriting newer states against policy.
- `BOUNCED`, `COMPLAINED`, and `DELIVERED` are distinct signals; never infer the recipient opened the email from `DELIVERED`.

Dashboards should track **SMTP accepted** separately from **provider delivered**, alongside bounce rates and time from request to confirmation.

### 12.2. Outbox Status Differs from Email Status

`published_at` means **the broker confirmed the work message**; it does not mean SMTP succeeded. One outbox event may be published multiple times while the delivery is claimed once; conversely, one delivery may have multiple outbox events across scheduled retries. **Queue depth** is a gauge of pending work messages, not total emails sent.

## 13. Failure States and Recovery Procedures

A reliable email system needs a unified **error taxonomy** across the request API, outbox relay, RabbitMQ consumer, renderer, SMTP, and callbacks:

| Failure Location | Example | Responsible Owner | Recovery |
| --- | --- | --- | --- |
| HTTP request validation | Missing recipient/template | HTTP caller | `400`; no delivery created |
| Reused idempotency key with wrong payload | Same key, different recipient | HTTP caller | `409`; old delivery unchanged |
| PostgreSQL fails to commit on accept | DB outage | HTTP caller | `503/5xx`; retry with same idempotency key |
| Outbox relay hits broker outage | No publisher confirm | Durable outbox | Retry publish with backoff; queue duplicates possible |
| Unroutable message | Unroutable return | Outbox relay | Fix exchange/binding; do not mark published |
| Bad work payload/schema | Invalid JSON/unsupported `schemaVersion` | Quarantine queue | Isolate + alert; do not call SMTP |
| Missing delivery ID | Data/outbox inconsistency | Quarantine and investigate | Never synthesize a delivery from broker payload |
| Worker cannot reach DB | DB timeout before/during claim | Unacked broker work | Bounded backoff/pause/requeue |
| Definitive temporary SMTP rejection | Verified provider 4xx | `email_delivery` `RETRY_WAIT` | Scheduler emits next outbox dispatch |
| Permanent SMTP rejection | Invalid recipient, permanent 5xx | `FAILED_PERMANENT` | Fix data/operator review; no infinite retries |
| SMTP timeout after starting send | Uncertain outcome | `UNKNOWN` | Look up/reconcile; never auto-resend |
| SMTP succeeds, DB outcome update fails | Email may have gone out | `SENDING → UNKNOWN` | Reconcile; prevent duplicate sends |
| Rabbit ACK fails | DB already terminal | Broker may redeliver | Worker skips SMTP and ACKs copy |
| Provider reports bounce | Mailbox rejected | Feedback history | Apply bounce policy/suppress future sends per rules |

**DLQs do not replace the delivery status table.** `FAILED_PERMANENT` email is a business result visible through the status API, whereas malformed JSON on a work queue is an infrastructure fault for quarantine. Routing all SMTP failures to a DLQ without updating `email_delivery` leaves users stuck seeing `PENDING` forever.

### 13.1. Alerts When Processing Ownership Could Be Lost

Alert immediately when:

- A committed `PENDING` delivery lacks a matching **outbox** row: transaction invariant breach.
- Outbox `published_at IS NULL` ages too long, relay fails to send, or claims stick on leases.
- `PENDING` work is published yet the queue lacks consumers and request age climbs.
- `SENDING` exceeds leases and `UNKNOWN` climbs; never resend silently.
- `RETRY_WAIT` passes `next_attempt_at` without the scheduler creating new dispatches.
- DLQ ingress increases, especially `schemaVersion` errors or missing delivery IDs.
- `ACCEPTED_BY_SMTP` climbs alongside bounce/complaint rates, indicating address/template quality issues.

## 14. Observability: Metrics, Logs, Traces, and SLOs

Design metrics around **unit of measurement and exact recording moment** instead of lumping everything into `email_errors`:

| Proposed Metric (Micrometer Name) | Type | When Recorded |
| --- | --- | --- |
| `app.email.request.accepted` | Counter | Accept email + outbox transaction commits |
| `app.email.request.idempotency_reused` | Counter | Same key/fingerprint returns existing ID |
| `app.email.request.idempotency_conflict` | Counter | Same key with different fingerprint returns 409 |
| `app.email.outbox.publish_attempts` | Counter | Relay actually initiates a publish |
| `app.email.outbox.publish_confirmed` | Counter | Confirm ACK received with no unroutable return |
| `app.email.outbox.pending` | Gauge | Count of unpublished outbox rows |
| `app.email.outbox.oldest_age` | Gauge | Age of oldest unpublished outbox row |
| `app.email.work.received` | Counter | RabbitMQ delivery enters worker, including redeliveries |
| `app.email.work.claimed` | Counter | DB claim returns 1 row and an attempt starts |
| `app.email.work.duplicate_skipped` | Counter | Work message skipped due to current state |
| `app.email.send.attempt.duration` | Timer | Render + SMTP duration for one attempt |
| `app.email.smtp.accepted` | Counter | `JavaMailSender` succeeds and DB commits outcome |
| `app.email.retry.scheduled` | Counter | `RETRY_WAIT` transition committed |
| `app.email.unknown` | Counter | Transition into `UNKNOWN` |
| `app.email.delivery.status` | Gauge | Delivery count per status |
| `app.email.feedback.bounced` | Counter | Verified bounce event, excluding duplicate webhooks |
| `app.email.quarantine.received` | Counter | Message observed entering DLQ/quarantine |

These names are **proposed application conventions**, not built-in Spring Boot/Spring AMQP metrics. Process counters reset on restarts. In Prometheus, use `rate()`/`increase()` properly; gauges show instantaneous values, never sum queue depth as a historical event total.

### 14.1. Tags and Cardinality

Tags should come from a small bounded set:

~~~text
template=order-confirmation | shipment-update
provider=primary-smtp | backup-smtp
error_kind=timeout | temporary_reject | invalid_recipient | unknown
status=PENDING | SENDING | RETRY_WAIT | ACCEPTED_BY_SMTP | UNKNOWN
result=success | failure
~~~

**Never** use `deliveryId`, idempotency key, email address, raw `tenantId`, subject, message body, or provider tokens as metric labels. They explode cardinality and leak PII or credentials. Business correlation IDs belong in **access-controlled logs/traces with appropriate retention** after applying data governance policies.

### 14.2. Tracing Across Three Systems

~~~text
HTTP POST (requestId)
  → DB transaction accept:
       deliveryId = 73de...
       outboxEventId = 8fd...
  → outbox relay:
       Rabbit publish / confirm
  → Rabbit worker:
       deliveryId = 73de...
       attemptToken = ...
       DB claim
       SMTP send
       DB outcome
       Rabbit ACK
  → GET status / feedback event
~~~

Trace context across HTTP, outbox, and RabbitMQ must be propagated intentionally; neither broker nor worker stitches spans automatically merely because a header contains a UUID. Never log SMTP passwords or Authorization headers. If email variables/bodies contain PII, never put them into trace baggage.

### 14.3. SLOs and Dashboards

An operations dashboard should show:

- **Acceptance latency**: time from POST to DB commit/202.
- **Queue-to-start latency**: from `created_at` to first claim.
- **Time-to-SMTP-accept**: from request to `smtp_accepted_at`, only for confirmed states.
- **Retry rate**, **UNKNOWN rate**, **permanent failure rate**, and current `RETRY_WAIT` count.
- **Outbox oldest age**, queue ready/unacked depth, worker concurrency, and DB pool saturation.
- **Provider rejections/timeouts**, **bounces/complaints**, and feedback latency if available.

Never define a "100% delivered" SLO when only SMTP acceptance is observable. Track **"SMTP accepted within 5 minutes"** separately from **"confirmed delivered"** when provider webhooks exist, while monitoring overdue `UNKNOWN`/`PENDING` items independently.

## 15. Security, Sending Authorization, and Personal Data

An email API can easily be abused as an **open relay** without strict controls. Enforce:

1. **Authentication and authorization**: callers may only send for their tenant's authorized purposes/templates/recipients, never choosing `From` arbitrarily.
2. **Template allowlist/versioning**: disallow arbitrary content and template injection; HTML-escape variables and block control characters/header injection.
3. **Rate limits/quotas**: cap requests per tenant/purpose/domain and concurrent SMTP sends; stay within provider limits.
4. **Email validation**: check syntax, verified inputs, suppression lists/bounces/unsubscribes; avoid aggressively rewriting addresses per one provider's quirks.
5. **Legal/compliance**: separate transactional emails from marketing, honoring consent/unsubscribe, retention, and data minimization policies.
6. **Transport security**: SMTP TLS/STARTTLS with certificate validation; protect passwords/OAuth tokens via secret managers and rotation.
7. **Domain reputation**: configure SPF, DKIM, and DMARC for sending domains and act on bounces/complaints; never equate provider acceptance with inbox placement.
8. **Privacy**: encrypt/protect email addresses, variables, logs, and backups; GET APIs enforce tenant authorization and hide bodies from unauthorized callers.
9. **Replay/abuse protection**: scope idempotency keys, enforce business-aligned TTL/retention, and limit arbitrary key creation per actor.
10. **Template rollouts**: deploy new versions cleanly; never re-render an existing delivery using a different template during retries.

No deduplication design protects against a caller deliberately minting a **new idempotency key for the same event**. Upstream event producers must enforce strict key contracts on replay.

## 16. Integration Testing: Proving Crash Points Too

Unit tests for services/mappers only verify Java logic. Queue + transaction + SMTP workflows need integration tests running **real PostgreSQL, real RabbitMQ, and an SMTP test server** (such as GreenMail, MailHog, or a controllable SMTP stub).

### 16.1. Testcontainers for PostgreSQL and RabbitMQ

Example JUnit 5 skeleton:

~~~java
@Testcontainers
@SpringBootTest
class EmailDeliveryIntegrationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @Container
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4-management");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry props) {
        props.add("spring.datasource.url",
                postgres::getJdbcUrl);
        props.add("spring.datasource.username",
                postgres::getUsername);
        props.add("spring.datasource.password",
                postgres::getPassword);
        props.add("spring.rabbitmq.host", rabbit::getHost);
        props.add("spring.rabbitmq.port", rabbit::getAmqpPort);
    }

    // Configure fake SMTP host/port via test properties,
    // run migrations, start relay/worker, and assert DB,
    // RabbitMQ queue/DLQ, and SMTP messages.
}
~~~

Declare Testcontainers `postgresql`, `rabbitmq`, JUnit 5 module, matching JDBC driver, and SMTP test stub dependencies. Image tags are illustrative; pin and maintain them in CI. If tests require custom RabbitMQ auth, configure test credentials separately—never use production secrets.

### 16.2. Required Test Matrix

| Scenario | Mandatory Outcome |
| --- | --- |
| Valid POST | One `email_delivery` + one `email_outbox`, HTTP 202 |
| Repeated POST with same key/payload | Same `deliveryId`, no extra outbox |
| POST with same key, different recipient/template | HTTP 409, original request untouched |
| Two concurrent POSTs with same key | Unique constraint protects; only one delivery created |
| DB commit fails on outbox insert | Rolls back delivery too; no orphan request |
| Relay dies before publish | Outbox remains pending; restart publishes it |
| Relay publishes then crashes before marking | Two queue messages possible; only one worker claims |
| Broker publisher confirm NACK/unroutable | Does not mark published; retries per policy |
| Two workers receive duplicate message | Only one atomic claim wins; no parallel sends |
| SMTP accepts, DB marks done, broker ACK lost | Redelivery skips SMTP, preserves `ACCEPTED_BY_SMTP` |
| SMTP accepts then worker crashes before DB mark | `SENDING` lease expires → `UNKNOWN`, **no auto-resend** |
| SMTP 4xx confirmed unaccepted | `RETRY_WAIT` with `nextAttemptAt`; scheduler creates new dispatch |
| Retries reach max attempts | `FAILED_PERMANENT` or manual review per policy, no loop |
| Uncertain SMTP outcome | `UNKNOWN` and reconciliation; no auto-retry |
| Invalid template/recipient | `FAILED_PERMANENT`, never sent |
| Work message invalid JSON/unknown `schemaVersion` | Quarantine/DLQ; no email delivery modified |
| DB outage in listener | Never ACKs as success; bounded requeue/backoff/pause |
| Another tenant's `deliveryId` | GET API leaks neither status nor data |
| Provider sends duplicate bounce webhook | One transition/logical event recorded; metrics not doubled |
| Traffic burst | Rate limits and queue/pool saturation thresholds alert cleanly |

### 16.3. The Most Important Fault Injection

To verify "SMTP accepted yet DB failed to record," a fake SMTP server can **record receipt of `DATA`**, while the test stops the worker or injects a fault right at `markAccepted`. Then:

~~~text
1. Worker claims → SENDING, attempt_count=1.
2. Fake SMTP records one message.
3. Inject crash/DB failure before markAccepted.
4. Broker redelivers (or relay sends duplicate).
5. New worker sees SENDING and does not send again.
6. Lease expires; reconciler moves to UNKNOWN.
7. Assert fake SMTP still holds exactly one message.
8. Operator/reconciler resolves UNKNOWN per explicit policy.
~~~

This test proves the policy of **not auto-resending when outcomes are uncertain**, not inbox delivery. Also test crashing **before the SMTP call**: state can likewise end in `UNKNOWN`, highlighting the trade-off between avoiding duplicates and risking missed sends without reconciliation.

### 16.4. Testing Transactions and Asserting the Right Units

Never assert merely that "the listener was called once": RabbitMQ may deliver twice while the system remains correct if **one claim wins and zero duplicate side effects happen**. Assert:

- Row counts in `email_delivery` and `email_outbox` per business key.
- Attempt counts and exact states after each fault.
- Count of emails the fake SMTP server **actually received**.
- After relay/worker restarts, persisted state survives and schedulers recover.
- No fake terminal success when SMTP outcome was uncertain.

Avoid long fixed `Thread.sleep` calls when Awaitility/polling with clear deadlines and conditions works. Clean up test data, queues, and SMTP stubs and isolate parallel tests so concurrent suites never compete on the same queue.

## 17. Operations and Reconciliation Runbook

~~~mermaid
flowchart TD
    A["Alert: email backlog/unknown rising"] --> B{"Where is the bottleneck?"}
    B -->|"Unpublished outbox"| C["Check RabbitMQ confirms, returns, bindings"]
    B -->|"Queue backing up"| D["Check workers, DB pool, prefetch, rate limits"]
    B -->|"SMTP rejects/timeouts"| E["Check provider health, quota, TLS, and auth"]
    B -->|"UNKNOWN"| F["Reconcile with provider; do not auto-resend"]
    C --> G["Recover and monitor outbox oldest age"]
    D --> G
    E --> G
    F --> H["Record accepted/retry/manual review decision"]
    G --> I["Verify API statuses + audit + recipient suppression"]
    H --> I
~~~

Triage sequence:

1. Identify whether the failure is in **DB, broker, worker, or SMTP** via metrics and traces rather than blaming SMTP for everything.
2. If outbox pending grows, inspect confirms/unroutable returns, DLX/queue configuration, and relay leases.
3. If queue ready/unacked grows, inspect worker concurrency, SMTP timeouts, provider quotas, DB pool, and hot redelivery loops.
4. If overdue `RETRY_WAIT` grows, check the scheduler; never resend via manual scripts bypassing idempotency.
5. If `UNKNOWN` grows, export an audited list and reconcile via authorized provider APIs/logs; explicitly log every retry decision.
6. On `BOUNCED`/`COMPLAINED`, update suppression lists and notify business workflows; stop sending repeatedly to rejected addresses.
7. During recovery, cross-check accepted requests, published outbox rows, attempts, SMTP accepted, `UNKNOWN`, and feedback rather than trusting a single metric.

**Operator redrive** must be an authenticated, audited business command checking expected state and idempotency—never simply "copy messages from DLQ back to work queue" if the DB already shows `ACCEPTED_BY_SMTP` or `UNKNOWN`.

### 17.1. When Using Spring Integration DSL

This architecture can also use **Spring Integration AMQP inbound/outbound adapters**, `IntegrationFlow`, channels, and service activators instead of the `@RabbitListener`/relay classes shown here. Keep the same core boundaries:

- API writes **`email_delivery` + outbox** inside the DB transaction; never send mail directly on the HTTP thread.
- AMQP inbound flows must invoke a service performing **atomic claim → SMTP → durable outcome**, rather than piping payloads straight into a mail outbound adapter assuming exactly-once behavior.
- `errorChannel`, `RequestHandlerRetryAdvice`, or `ErrorMessageSendingRecoverer` only coordinate error routing; they **do not prove** messages were durably stored or emails were sent.
- Protect source `ACK/NACK` semantics according to your inbound adapter, listener container, transaction, and recoverer. An error flow that logs and returns normally can accidentally ACK the source message.
- Propagate correlation ID, `deliveryId`, and `eventId` cleanly across adapters; avoid scattering email addresses or SMTP tokens into unnecessary headers.

Even when using Spring Integration's **`MailSendingMessageHandler`** for SMTP, wrap it in the same status/attempt-token policy and `UNKNOWN` handling. Renaming the adapter does not eliminate the non-atomic gap between SMTP acceptance and DB commit.

## 18. Misconceptions to Avoid

**"Publishing to RabbitMQ means the email was sent."** False: the task was only queued; workers and SMTP have not run yet.

**"Publisher confirm ACK means the recipient got the email."** Wrong: confirms reflect broker acceptance, not SMTP or the recipient's inbox.

**"`JavaMailSender.send` returning means the email is definitely delivered."** It only proves SMTP/provider acceptance for that handoff, excluding bounces and spam filters.

**"`Message-ID` prevents duplicate emails."** It is a correlation header, not an exactly-once SMTP protocol.

**"Putting `@Transactional` around SMTP send rolls it back."** Database transactions cannot recall an email already accepted by a mail server.

**"Retry immediately on any `MailException`."** Timeouts around SMTP DATA/ACK leave uncertain outcomes; resending can duplicate emails.

**"RabbitMQ automatically deduplicates messages with the same `eventId`."** Not by default; rely on DB state, claims, and unique keys.

**"Redis `SETNX` or an in-RAM lock is enough."** Ephemeral locks cannot replace unique constraints, durable outcomes, and crash recovery.

**"ACKing before committing the outcome makes the system faster."** You risk losing recovery capability if the process crashes before saving the result.

**"Swallowing certain SMTP errors and returning success avoids redeliveries."** That hides failures and lies via the tracking API; ACK only after durably saving the transition or recovery decision.

**"An expired lease proves the email was not sent."** No; the worker could have sent it and crashed right before updating the DB.

**"Checking the DLQ shows all failed emails."** The DLQ tracks transport/poison work messages; the delivery table tracks business states like `RETRY_WAIT`, `UNKNOWN`, SMTP accepted, and bounced.

**"One idempotency key works for all recipients."** Scope keys to one logical send unit including recipient and purpose; otherwise valid emails get suppressed.

**"Reusing a key with a new request should just send the new request."** Return 409; never mutate an already-accepted delivery.

## 19. Pre-Production Deployment Checklist

1. Lock down contracts for `202 Accepted`, the GET status endpoint, and `ACCEPTED_BY_SMTP` vs. `DELIVERED`.
2. Define idempotency keys by tenant, event, purpose/template, and recipient; return 409 on payload mismatch.
3. Commit `email_delivery` + outbox inside **one PostgreSQL transaction**.
4. Outbox relay uses leases/claims, publisher confirms, mandatory returns, and safe handling for uncertain publish outcomes.
5. Durable queues, persistent messages, and DLX/quarantine are tested; never use queue depth as sent-email count.
6. Workers use atomic DB claims/fencing tokens; never send when status is terminal, `SENDING`, or `UNKNOWN`.
7. SMTP sends enforce timeouts, STARTTLS/TLS, sender allowlists, template escaping, and provider rate limits.
8. Broker ACKs occur only after durable DB state/decisions; DB outages trigger safe requeue/backoff/pausing.
9. Retry only errors **proven not accepted**, with max attempts and backoff/jitter; uncertain timeouts → `UNKNOWN`.
10. Retry scheduler emits via outbox inside transactions; expired `SENDING` → `UNKNOWN`, never auto-resending.
11. Reconciliation and operator redrives require authorization, auditing, and duplicate safeguards.
12. Protect recipients/variables, suppression lists, consent, retention, SPF/DKIM/DMARC, and credentials.
13. Metrics/traces separate accepted requests, published work, claims, SMTP acceptance, unknowns, and feedback.
14. Test with PostgreSQL + RabbitMQ + fake SMTP, covering concurrent duplicates, crashes after SMTP success, lost ACKs, and DLQs.
15. Maintain runbooks for outbox backlogs, overdue retries, rising `UNKNOWN`, and provider bounces.

**Conclusion:** Queued email delivery is not "drop `JavaMailSender.send()` into a listener." A trustworthy design combines a **DB outbox to preserve send intent, unique idempotency keys to reject duplicate requests, atomic claims to prevent worker races, a state machine to track outcomes, and honest handling of `UNKNOWN`**. The system can guarantee **durable acceptance and work orchestration** within its designed boundaries, while never falsely promising exactly-once delivery over plain SMTP.

## References

- [Spring Boot Reference — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): `JavaMailSender`, mail starter, SMTP configuration, and timeouts.
- [Spring Framework — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): `MimeMessageHelper`, HTML/plain content, and mail sender interfaces.
- [Spring AMQP — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable.html): `@RabbitListener`, `ackMode` MANUAL, and listener containers.
- [Spring AMQP — RabbitTemplate/Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData`, publisher confirms, and mandatory returns.
- [Spring AMQP — Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): acknowledge modes, concurrency, prefetch, and container settings.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): boundaries between consumer ACK and producer confirms.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): reject/nack, routing, and dead-lettering.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional` boundaries and commit/rollback.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): unique constraints and idempotent inserts.
- [PostgreSQL — SELECT / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): worker contention and outbox claiming.
- [Testcontainers — Modules](https://java.testcontainers.org/modules/): PostgreSQL, RabbitMQ, and integration test environments.
