# Building an Outbox for Emails After Transaction Commit

In a Spring Framework Mail project, a seemingly simple requirement is: **when an order is confirmed, send a notification email to the customer**. However, calling `JavaMailSender` directly inside a `@Transactional` method introduces the **dual-write** problem between the database and the SMTP server.

This practice project builds a lightweight **transactional outbox** with **Spring Boot, Spring JDBC, PostgreSQL, Spring Mail, and Mailpit**. When the application creates an order, it persists **both the order and the email send intent in the same transaction**. Only after the transaction commits can a worker see the outbox job, claim ownership, send over SMTP, and record the outcome. When SMTP fails, the job is scheduled for retry; when a worker crashes, its lease expires so another worker can pick it up.

The key principle to understand right away:

> **The outbox row must be INSERTed inside the business transaction, not after commit. Actually SENDING the email happens after the transaction commits.**

If you wait until after the database commits to INSERT into the outbox, the app can crash between those two steps and lose the send intent completely. If you send via SMTP before committing, the relay can accept the email while the business transaction later rolls back. A transactional outbox eliminates the **gap between the business write and the mail intent**, rather than creating a distributed transaction with SMTP.

~~~mermaid
flowchart TD
    A["POST /api/orders"] --> B["BEGIN database transaction"]
    B --> C["INSERT app_order"]
    B --> D["INSERT mail_outbox PENDING"]
    C --> E["COMMIT atomically"]
    D --> E
    E --> F["Worker poll committed jobs"]
    F --> G["Claim job + lease"]
    G --> H["COMMIT claim"]
    H --> I["Compose MIME + JavaMailSender.send"]
    I --> J{"SMTP submission"}
    J -->|"Accepted"| K["Mark SENT"]
    J -->|"Temporary error"| L["RETRY + next_attempt_at"]
    J -->|"Permanent error"| M["DEAD / manual action"]
    L --> F
~~~

After this practice project, you will have an order-creation API, a durable outbox table, a claim/lease dispatcher, basic retry handling, test SMTP configuration, and a set of test scenarios covering commits, rollbacks, restarts, and duplicates. This is a **practice foundation**, not a full production email platform covering domain setup, consent, DKIM, quotas, or delivery feedback.

## 1. Expected Outcomes

Happy path:

~~~text
Client POST /api/orders
  -> OrderApplicationService
       BEGIN
       INSERT app_order
       INSERT mail_outbox(status=PENDING)
       COMMIT
  <- HTTP 201 Created + orderId

Outbox worker
  -> SELECT committed job
  -> claim: PENDING -> SENDING
  -> JavaMailSender.send(...)
  -> local Mailpit SMTP accepts
  -> update status=SENT

Mailpit UI
  -> displays confirmation email
~~~

Rollback path:

~~~text
OrderApplicationService
  BEGIN
  INSERT app_order
  INSERT mail_outbox
  throw RuntimeException
  ROLLBACK

Result:
  No new order.
  No mail_outbox job.
  Worker has nothing to send.
~~~

Temporary failure path:

~~~text
SMTP is down
  -> worker send fails
  -> status RETRY
  -> next_attempt_at = future timestamp

SMTP comes back up
  -> worker claims when due
  -> retries send
  -> status SENT
~~~

And the limitation we must accept:

~~~text
SMTP accepted the message
worker crashes before recording SENT
lease expires
new worker may send again
=> Duplicate email risk exists.
~~~

The goal is **never losing send requests after commit**, recovering cleanly from failures, and understanding the exact guarantee boundaries of the system.

## 2. Mini-Project Architecture

Components:

| Component | Responsibility |
| --- | --- |
| `OrderController` | Accepts HTTP requests, returns order ID |
| `OrderApplicationService` | Opens the business transaction |
| `OrderRepository` | Reads and writes orders |
| `MailOutboxWriter` | INSERTs send intent with a unique idempotency key |
| `MailOutboxClaimer` | Claims due jobs in a short transaction |
| `OutboxPollingWorker` | Polls and orchestrates processing |
| `OutboxEmailProcessor` | Reads payload, builds MIME, sends via SMTP |
| `MailOutboxResultWriter` | Records `SENT`, `RETRY`, or `DEAD` guarded by lease token |
| PostgreSQL | Source of truth for orders and outbox |
| Mailpit | Test SMTP server/UI, sends nothing to the Internet |
| `JavaMailSender` | Spring API submitting MIME over SMTP |

Reference layout:

~~~text
src/main/java/com/example/mailoutbox/
  MailOutboxApplication.java
  order/
    CreateOrderRequest.java
    CreateOrderResponse.java
    OrderRow.java
    OrderRepository.java
    OrderApplicationService.java
    OrderController.java
  mail/
    OrderMailPayload.java
    MailOutboxWriter.java
    ClaimedMailJob.java
    MailOutboxClaimer.java
    MailOutboxResultWriter.java
    OutboxEmailProcessor.java
    OutboxPollingWorker.java
src/main/resources/
  application.yml
  db/migration/V1__create_orders_and_mail_outbox.sql
compose.yml
~~~

Package and class names are illustrative. To make transaction boundaries explicit, the example uses **Spring JDBC** with raw SQL; you can swap in Spring Data JPA as long as you preserve identical semantics.

## 3. Tech Stack and Prerequisites

Example environment:

- Java 17 or later.
- Spring Boot 3.x with Jakarta Mail.
- Spring Web and Validation for the HTTP API.
- Spring JDBC and PostgreSQL.
- Flyway for migrations.
- Spring Boot Mail / `JavaMailSender`.
- Docker Compose to run PostgreSQL and Mailpit.
- Spring Test with an appropriate test database/SMTP setup for integration tests.

Illustrative Gradle dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.postgresql:postgresql'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Flyway module artifacts may vary depending on your managed Spring Boot/Flyway versions; this example assumes a version supporting the PostgreSQL module. Never add arbitrary versions that duplicate or conflict with your project's dependency management.

In this lesson, **`@EnableAsync` is not needed**: the worker runs via `@Scheduled`, and work items live in PostgreSQL rather than an in-memory queue.

## 4. Running PostgreSQL and Mailpit Locally

Reference `compose.yml`:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: mail_demo
      POSTGRES_USER: mail_demo
      POSTGRES_PASSWORD: mail_demo
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mail_demo -d mail_demo"]
      interval: 5s
      timeout: 3s
      retries: 10

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"
      - "8025:8025"

volumes:
  postgres_data:
~~~

Start in the practice environment:

~~~bash
docker compose up -d
~~~

Mailpit listens for SMTP at `localhost:1025` and exposes its web UI at `http://localhost:8025` when the app runs on the host machine. Credentials and settings here are strictly for **local development**; never reuse them directly in production.

### Why Use Mailpit?

Mailpit captures SMTP submissions so learners can inspect emails in the UI without sending real mail onto the Internet. The `SENT` status in the database should be understood as **the test SMTP relay accepted the submission**, not proof of delivery to a real inbox.

## 5. Spring Boot Configuration

Reference `application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mail_demo
    username: mail_demo
    password: mail_demo

  flyway:
    enabled: true

  mail:
    host: localhost
    port: 1025
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000

app:
  mail:
    from: no-reply@example.test
    outbox:
      poll-ms: 1000
~~~

`app.mail.*` properties are application-defined, not built-in Spring Mail properties. Local Mailpit typically requires no SMTP AUTH/TLS; **production must enforce the TLS/auth policy required by your provider**, never copying `auth: false` or disabled STARTTLS to public relays.

Timeouts are vital so a worker never hangs indefinitely on an SMTP call. If a send attempt can outlast the lease duration, another worker risks reclaiming and duplicating the job.

## 6. Enabling Scheduling

~~~java
package com.example.mailoutbox;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class MailOutboxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                MailOutboxApplication.class,
                args
        );
    }
}
~~~

`@EnableScheduling` triggers `@Scheduled` methods periodically. **Scheduling does not replace transactions**: the poller must read committed rows from the database, and each claim requires an atomic database operation.

## 7. Migration: Creating the Orders Table

In `V1__create_orders_and_mail_outbox.sql`, create the table:

~~~sql
CREATE TABLE app_order (
    id UUID PRIMARY KEY,
    request_key VARCHAR(160) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_order_request_key
        UNIQUE (request_key),

    CONSTRAINT chk_order_positive_amount
        CHECK (total_amount > 0),

    CONSTRAINT chk_order_status
        CHECK (status IN ('CONFIRMED'))
);
~~~

In this demo, a request creates a `CONFIRMED` order immediately; real projects separate `DRAFT`, `PAID`, `CANCELED`, and dedicated payment flows.

`request_key` is the idempotency key at the **HTTP order-creation** layer. Resending the same request must not create a second order. It differs from the email's `idempotency_key`, though the two are related.

Never store bank card details, access tokens, or unnecessary sensitive data in this table.

## 8. Migration: The mail_outbox Table

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES app_order(id),
    event_type VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(320) NOT NULL,
    recipient_email VARCHAR(320) NOT NULL,
    payload_json JSONB NOT NULL,

    status VARCHAR(24) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    claim_owner VARCHAR(160),
    claim_token UUID,
    claim_until TIMESTAMPTZ,

    last_error_code VARCHAR(80),
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_mail_outbox_idempotency
        UNIQUE (idempotency_key),

    CONSTRAINT chk_mail_outbox_status
        CHECK (status IN (
            'PENDING', 'SENDING', 'RETRY', 'SENT', 'DEAD'
        )),

    CONSTRAINT chk_mail_outbox_attempts
        CHECK (
            attempt_count >= 0
            AND max_attempts > 0
        )
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (
        status,
        next_attempt_at,
        created_at
    );

CREATE INDEX idx_mail_outbox_expired_claim
    ON mail_outbox (
        claim_until
    )
    WHERE status = 'SENDING';
~~~

This is PostgreSQL SQL. In production, you may add tenant IDs, priorities, purposes, sender profiles, template versions, retention, and partitioning; this practice project keeps the schema focused.

### Column Meanings

| Column | Purpose |
| --- | --- |
| `id` | Unique job ID |
| `order_id` | Business entity reference |
| `event_type` | Event/email kind to send |
| `idempotency_key` | Prevents enqueuing the same mail intent twice |
| `recipient_email` | Demo recipient snapshot |
| `payload_json` | Data needed to compose the email |
| `status` | Processing state |
| `attempt_count` | Number of send claims attempted |
| `max_attempts` | Auto-retry cap |
| `next_attempt_at` | Next eligible retry timestamp |
| `claim_owner` | Worker instance holding the claim |
| `claim_token` | Fencing token for the current claim |
| `claim_until` | Lease deadline for crash recovery |
| `last_error_code` | Log/DB-safe error category |
| `submitted_at` | Timestamp when SMTP relay accepted |
| `created_at`, `updated_at` | Auditing and scheduling |

**`SENT` in this demo means submitted/accepted by the SMTP transport**, not delivered. You can rename it to `SUBMITTED` in production to eliminate ambiguity.

## 9. States and Transition Rules

~~~mermaid
flowchart TD
    A["PENDING"] --> B["SENDING"]
    B -->|"send() success"| C["SENT"]
    B -->|"retryable error"| D["RETRY"]
    B -->|"permanent error"| E["DEAD"]
    D --> B
    B -->|"lease expired"| F["Reclaim"]
    F --> B
    F -->|"attempts exhausted"| E
~~~

Rules:

- `PENDING`: record committed, not yet claimed.
- `SENDING`: worker holds the lease; an SMTP attempt may be in flight.
- `RETRY`: failed, waiting for `next_attempt_at`.
- `SENT`: `JavaMailSender.send` returned normally and the worker saved the outcome.
- `DEAD`: no further automatic retries; requires review, repair, or authorized replay.
- Lease expiration does not prove SMTP never accepted the job.
- There is no shared ACID transaction between updating `SENT` and the SMTP relay.

This demo uses `DEAD` for both config failures and exhausted attempts; real operations should clearly separate **permanent failures**, **unknown outcomes**, and **manual interventions**.

## 10. Request Model and Email Snapshot

An API request:

~~~java
package com.example.mailoutbox.order;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

public record CreateOrderRequest(
        @NotBlank String requestKey,
        @Email @NotBlank String recipientEmail,
        @NotNull @DecimalMin("0.01")
        BigDecimal totalAmount,
        @NotBlank String currency
) {
}
~~~

Response:

~~~java
package com.example.mailoutbox.order;

import java.util.UUID;

public record CreateOrderResponse(
        UUID orderId,
        String emailStatus
) {
}
~~~

Mail snapshot:

~~~java
package com.example.mailoutbox.mail;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderMailPayload(
        UUID orderId,
        String recipientEmail,
        BigDecimal totalAmount,
        String currency
) {
}
~~~

`payload_json` captures the data needed to render an order confirmation email without relying solely on domain records that could mutate after commit. In production, limit sensitive fields, pin template versions if using a template engine, and check recipient consent per purpose.

### Why Require `requestKey`?

An HTTP client may time out after the server commits and resend the request. If every request generates a fresh order UUID without checking a key, the system creates **two orders and two mail intents**. Unique `request_key` deduplicates at the order layer; unique `mail_outbox.idempotency_key` deduplicates at the mail layer.

When the same key arrives with a different payload, treat it as a **conflict** rather than silently returning the old order with mismatched data.


## 11. Order Repository: Idempotent Insert

Database read model:

~~~java
package com.example.mailoutbox.order;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderRow(
        UUID id,
        String requestKey,
        String recipientEmail,
        BigDecimal totalAmount,
        String currency,
        String status
) {
}
~~~

Repository using `JdbcTemplate`:

~~~java
package com.example.mailoutbox.order;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public class OrderRepository {

    private final JdbcTemplate jdbc;

    public OrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public OrderRow insertOrRead(
            CreateOrderRequest request) {

        UUID proposedId = UUID.randomUUID();

        jdbc.update(
            """
            INSERT INTO app_order (
                id, request_key, recipient_email,
                total_amount, currency, status
            )
            VALUES (?, ?, ?, ?, ?, 'CONFIRMED')
            ON CONFLICT (request_key) DO NOTHING
            """,
            proposedId,
            request.requestKey(),
            request.recipientEmail(),
            request.totalAmount(),
            request.currency()
        );

        return jdbc.query(
            """
            SELECT id, request_key, recipient_email,
                   total_amount, currency, status
            FROM app_order
            WHERE request_key = ?
            """,
            (rs, rowNum) -> new OrderRow(
                    rs.getObject("id", UUID.class),
                    rs.getString("request_key"),
                    rs.getString("recipient_email"),
                    rs.getBigDecimal("total_amount"),
                    rs.getString("currency"),
                    rs.getString("status")
            ),
            request.requestKey()
        ).stream().findFirst().orElseThrow();
    }
}
~~~

In PostgreSQL under standard `READ COMMITTED` isolation:

- The first insert for a `request_key` creates a new order.
- Subsequent retries with the same key hit `ON CONFLICT DO NOTHING` and insert no extra row.
- The query reads back the order by key to return the exact same order ID.
- Under concurrent races for the same key, the unique constraint provides the final guarantee.

Under stricter isolation levels or serialization failures, the app may need transaction retries per policy. Never rely on a `SELECT exists` followed by `INSERT` without a backing unique constraint.

### Same `requestKey`, Different Payload

Verify that the persisted data matches the request:

~~~java
private void requireSameRequest(
        OrderRow order,
        CreateOrderRequest request) {

    boolean same =
            order.recipientEmail()
                    .equals(request.recipientEmail())
            && order.totalAmount()
                    .compareTo(request.totalAmount()) == 0
            && order.currency()
                    .equals(request.currency());

    if (!same) {
        throw new IllegalArgumentException(
                "requestKey was reused with different data"
        );
    }
}
~~~

This helper lives in the application service below. Production must also normalize inputs, enforce tenant scope, authentication, anti-abuse limits, and return HTTP `409 Conflict` when a key is reused with differing data.

## 12. Outbox Writer: Recording Mail Intent in the Same Transaction

~~~java
package com.example.mailoutbox.mail;

import com.example.mailoutbox.order.OrderRow;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public class MailOutboxWriter {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public MailOutboxWriter(
            JdbcTemplate jdbc,
            ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    public void enqueueOrderConfirmation(
            OrderRow order) {

        OrderMailPayload payload =
                new OrderMailPayload(
                        order.id(),
                        order.recipientEmail(),
                        order.totalAmount(),
                        order.currency()
                );

        String json;

        try {
            json = objectMapper.writeValueAsString(
                    payload
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize order mail intent",
                    ex
            );
        }

        String idempotencyKey =
                "order-confirmation:" + order.id();

        jdbc.update(
            """
            INSERT INTO mail_outbox (
                id, order_id, event_type,
                idempotency_key,
                recipient_email,
                payload_json, status,
                next_attempt_at
            )
            VALUES (
                ?, ?, 'ORDER_CONFIRMED',
                ?, ?,
                CAST(? AS jsonb),
                'PENDING', now()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            UUID.randomUUID(),
            order.id(),
            idempotencyKey,
            order.recipientEmail(),
            json
        );
    }
}
~~~

`ON CONFLICT DO NOTHING` makes enqueuing idempotent per event/recipient intent. It does not eliminate every duplicate at the SMTP boundary; it prevents creating **multiple logical jobs** for the same order confirmation.

### Key Takeaway

This repository uses **no** `@Async`, `mailSender.send(...)`, or external API calls. It is a plain database write so the application service can combine it into a single transaction.

If JSON serialization fails, the exception propagates and the application service's transaction rolls back under default runtime-exception rules.

## 13. Application Service: Committing Both Order and Outbox

~~~java
package com.example.mailoutbox.order;

import com.example.mailoutbox.mail.MailOutboxWriter;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxWriter outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxWriter outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID placeOrder(
            CreateOrderRequest request) {

        OrderRow order =
                orders.insertOrRead(request);

        requireSameRequest(order, request);

        outbox.enqueueOrderConfirmation(order);

        return order.id();
    }

    private void requireSameRequest(
            OrderRow order,
            CreateOrderRequest request) {

        boolean same =
                order.recipientEmail()
                        .equals(request.recipientEmail())
                && order.totalAmount()
                        .compareTo(
                                request.totalAmount()
                        ) == 0
                && order.currency()
                        .equals(request.currency());

        if (!same) {
            throw new IllegalArgumentException(
                    "requestKey was reused with different data"
            );
        }
    }
}
~~~

When `placeOrder` runs through Spring's transaction proxy, both `orders.insertOrRead(...)` and `outbox.enqueueOrderConfirmation(...)` share **the same datasource and transaction manager**. Any error before commit rolls back both writes.

This is the **atomic guarantee**:

~~~text
BEGIN

INSERT app_order
INSERT mail_outbox (PENDING)

COMMIT
~~~

If you instead insert into the outbox inside an `AFTER_COMMIT` callback, you reintroduce a crash window:

~~~text
COMMIT app_order
JVM crashes before INSERT mail_outbox
=> order exists, send request is lost
~~~

If you use `@TransactionalEventListener(AFTER_COMMIT)`, use it **solely to wake up the poller** after the outbox row was already written inside the transaction, never as a substitute for writing the row.

## 14. HTTP Controller: Returning the Right Status

~~~java
package com.example.mailoutbox.order;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderApplicationService service;

    public OrderController(
            OrderApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CreateOrderResponse> create(
            @Valid @RequestBody
            CreateOrderRequest request) {

        UUID id = service.placeOrder(request);

        return ResponseEntity.ok(
                new CreateOrderResponse(
                        id,
                        "MAIL_INTENT_RECORDED"
                )
        );
    }
}
~~~

In this example, `200 OK` works cleanly for both the initial request and retries with the same idempotency key; if an API must distinguish newly created resources from replays, return `201 Created` initially and `200 OK` on repeats. Production endpoints also require authentication, tenant scoping, and `409` mapping on key conflicts.

**`MAIL_INTENT_RECORDED` does not mean SMTP has sent.** It means only that the transaction committed with the outbox intent persisted.

### Trying the API

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "checkout-req-001",
    "recipientEmail": "buyer@example.test",
    "totalAmount": 250000.00,
    "currency": "VND"
  }'
~~~

Illustrative response:

~~~json
{
  "orderId": "5c5b0d1d-b4e7-4ee6-a8ce-7cc398a92011",
  "emailStatus": "MAIL_INTENT_RECORDED"
}
~~~

The UUID is illustrative. Calling again with the **same `requestKey` and same payload** returns the same order ID and creates no extra mail intent thanks to the two unique constraints.

## 15. Inspecting Transaction Commits in PostgreSQL

After calling the API, query:

~~~sql
SELECT id, request_key, recipient_email, status
FROM app_order
ORDER BY created_at DESC
LIMIT 5;
~~~

And:

~~~sql
SELECT id, order_id, event_type,
       status, attempt_count,
       next_attempt_at, submitted_at
FROM mail_outbox
ORDER BY created_at DESC
LIMIT 5;
~~~

If the worker runs quickly, the status may already be `SENT` instead of `PENDING` when you inspect it. To observe the initial state, you can temporarily pause the worker in your **demo environment** or increase the poll interval before calling the API.

Never use the `mail_outbox` status as proof that an email was delivered; this setup only performs local Mailpit SMTP submission.

## 16. Why Does the Worker See PENDING Rows Only After Commit?

In PostgreSQL under standard `READ COMMITTED` isolation, other transactions can only see committed rows.

~~~text
HTTP transaction:
  BEGIN
  INSERT app_order
  INSERT mail_outbox PENDING
  ... not yet committed

Worker transaction:
  SELECT ... WHERE status='PENDING'
  => uncommitted row is invisible

HTTP transaction:
  COMMIT

Worker transaction:
  SELECT ...
  => sees the row and can claim it
~~~

This is why **you do not need to send SMTP inside the HTTP transaction**. The poller can run continuously, yet it picks up only durable outbox rows.

Note: if you emit a local event to wake the worker too early, the worker might query before the transaction commits. Never make event timing a correctness requirement; the database outbox is the source of truth.

## 17. Failure Guardrail on Transaction Rollback

Suppose a business validation fails after both INSERTs were executed:

~~~java
@Transactional
public UUID placeOrderAndFail(
        CreateOrderRequest request) {

    OrderRow order =
            orders.insertOrRead(request);

    outbox.enqueueOrderConfirmation(order);

    throw new IllegalStateException(
            "Simulated failure"
    );
}
~~~

This is an **illustrative test seam** inside a bean invoked externally through a Spring proxy; it is not a method for production APIs. Because the runtime exception exits the transaction:

~~~text
ROLLBACK:
  app_order INSERT is rolled back
  mail_outbox INSERT is rolled back
  worker sees no job
~~~

If you put a `@Transactional` method in a class and call `this.placeOrderAndFail(...)` internally, proxy-based transactions will not intercept as expected. Test transaction boundaries through real external bean/service calls or `TransactionTemplate`.

### Why Not Use `REQUIRES_NEW` for the Outbox?

If the outbox writer uses `REQUIRES_NEW`:

~~~text
Outer business transaction not yet committed
  -> inner outbox transaction commits
  -> outer business transaction rolls back
~~~

the worker can receive a mail intent for an order that does not exist. **The outbox must share the same transaction**, never committing independently of business state.


## 18. Job Model Received by the Worker

The worker should never hold an open `ResultSet` or a mutable transaction-bound entity while sending mail. Map the required fields to an immutable record:

~~~java
package com.example.mailoutbox.mail;

import java.util.UUID;

public record ClaimedMailJob(
        UUID id,
        UUID orderId,
        String recipientEmail,
        String payloadJson,
        UUID claimToken,
        int attemptCount,
        int maxAttempts
) {
}
~~~

This job carries a `claimToken` tied to the **current claim**. It differs from `idempotencyKey`:

- `idempotencyKey` stays constant across requests and retries for the same intent.
- `claimToken` must change every time a worker claims or reclaims the job.
- `attemptCount` increments when starting a claim/attempt per the demo contract.
- `maxAttempts` caps automatic retries; it does not prove whether an email was sent.

Never embed full MIME bytes or large attachments inside in-memory queued objects to avoid bloating worker heap.

## 19. Claiming Jobs Safely Across Multiple Workers

If you merely write:

~~~java
List<Job> jobs =
        repository.findByStatus("PENDING");

for (Job job : jobs) {
    mailSender.send(...);
}
~~~

two JVMs can read the same row and both send. You need an **atomic claim** via transaction, locking, or conditional update.

In PostgreSQL, `FOR UPDATE SKIP LOCKED` lets a worker grab a job not locked by another worker:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        (
            status IN ('PENDING', 'RETRY')
            AND next_attempt_at <= now()
        )
        OR (
            status = 'SENDING'
            AND claim_until < now()
        )
    )
      AND attempt_count < max_attempts
    ORDER BY next_attempt_at, created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_outbox AS o
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    claim_owner = :worker_id,
    claim_token = :token,
    claim_until = now() + interval '2 minutes',
    updated_at = now()
FROM picked
WHERE o.id = picked.id
RETURNING
    o.id, o.order_id, o.recipient_email,
    o.payload_json::text AS payload_json,
    o.claim_token, o.attempt_count, o.max_attempts;
~~~

**Meaning:**

1. Pick one due job or a `SENDING` job whose lease expired.
2. Skip rows currently locked by another transaction.
3. Increment attempt count and assign a new owner, token, and lease.
4. Return the newly claimed job's data.
5. Commit the claim before sending over SMTP.

`SKIP LOCKED` is SQL-dialect-specific and not automatically portable across every database. On MySQL, SQL Server, or other engines, adapt the claim mechanism appropriately.

### Why Is a Lease Needed?

If a worker dies after claiming but before recording the outcome:

~~~text
Worker A claims job, status=SENDING
Worker A crashes
Without a lease:
  job stays stuck in SENDING forever

With a lease:
  after claim_until, Worker B can reclaim
~~~

However, leases do not eliminate double sends completely: the old worker might pause and wake up after its lease expired; if it already submitted over SMTP, the external side effect occurred even though DB fencing blocks its row update.

## 20. Claim Repository in a Short Transaction

~~~java
package com.example.mailoutbox.mail;

import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Repository
public class MailOutboxClaimer {

    private final NamedParameterJdbcTemplate jdbc;

    public MailOutboxClaimer(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public Optional<ClaimedMailJob> claimOne(
            String workerId) {

        UUID token = UUID.randomUUID();

        String sql = """
            WITH picked AS (
                SELECT id
                FROM mail_outbox
                WHERE (
                    (
                        status IN ('PENDING', 'RETRY')
                        AND next_attempt_at <= now()
                    )
                    OR (
                        status = 'SENDING'
                        AND claim_until < now()
                    )
                )
                  AND attempt_count < max_attempts
                ORDER BY next_attempt_at, created_at, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE mail_outbox AS o
            SET status = 'SENDING',
                attempt_count = attempt_count + 1,
                claim_owner = :workerId,
                claim_token = :token,
                claim_until =
                    now() + interval '2 minutes',
                updated_at = now()
            FROM picked
            WHERE o.id = picked.id
            RETURNING
                o.id, o.order_id, o.recipient_email,
                o.payload_json::text AS payload_json,
                o.claim_token, o.attempt_count,
                o.max_attempts
            """;

        List<ClaimedMailJob> rows =
                jdbc.query(
                    sql,
                    Map.of(
                        "workerId", workerId,
                        "token", token
                    ),
                    (rs, index) ->
                        new ClaimedMailJob(
                            rs.getObject(
                                "id", UUID.class
                            ),
                            rs.getObject(
                                "order_id", UUID.class
                            ),
                            rs.getString(
                                "recipient_email"
                            ),
                            rs.getString(
                                "payload_json"
                            ),
                            rs.getObject(
                                "claim_token", UUID.class
                            ),
                            rs.getInt(
                                "attempt_count"
                            ),
                            rs.getInt(
                                "max_attempts"
                            )
                        )
                );

        return rows.stream().findFirst();
    }
}
~~~

### Transaction Boundaries Must Be Exact

`claimOne` runs through a Spring bean proxy with `@Transactional`. The SQL update and row lock live inside a short DB transaction. Only after the method returns and commits does the worker begin network I/O.

**Never** write:

~~~java
@Transactional
public void claimAndSend() {
    Job job = claimOne();
    mailSender.send(...);
    markSent(...);
}
~~~

That holds transactions and locks across the SMTP call without making SMTP rollback-capable. If the network stalls, the database suffers contention and timeouts.

### Why Claim One Job at a Time?

The demo claims one job at a time so `claim_until` starts right before sending, avoiding claiming a large batch whose queued items expire their leases while sitting in RAM. When scaling, claim bounded batches sized to available worker capacity—never unbounded batches.

## 21. Fencing Tokens When Recording Outcomes

Once the worker finishes sending, never update status by `id` alone:

~~~sql
UPDATE mail_outbox
SET status = 'SENT'
WHERE id = :job_id;
~~~

Because Worker A may have lost its lease and Worker B just reclaimed the same job. Worker A waking up late would overwrite Worker B's state.

Match **job ID + current claim token + status `SENDING`**:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    submitted_at = now(),
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now(),
    last_error_code = NULL
WHERE id = :job_id
  AND claim_token = :token
  AND status = 'SENDING';
~~~

If the updated row count is 0, the worker no longer owns the active claim or the state already changed.

**Fencing only blocks stale DB updates**; it cannot "unsend" an email that Worker A already submitted via SMTP. That is an inherent boundary between databases and external side effects.

## 22. Result Writer: SENT, RETRY, and DEAD

~~~java
package com.example.mailoutbox.mail;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;
import java.util.UUID;

@Service
public class MailOutboxResultWriter {

    private final JdbcTemplate jdbc;

    public MailOutboxResultWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean markSent(ClaimedMailJob job) {

        int updated = jdbc.update(
            """
            UPDATE mail_outbox
            SET status = 'SENT',
                submitted_at = now(),
                claim_owner = NULL,
                claim_token = NULL,
                claim_until = NULL,
                last_error_code = NULL,
                updated_at = now()
            WHERE id = ?
              AND claim_token = ?
              AND status = 'SENDING'
            """,
            job.id(),
            job.claimToken()
        );

        return updated == 1;
    }

    @Transactional
    public boolean markFailed(
            ClaimedMailJob job,
            String safeErrorCode,
            boolean permanent) {

        boolean exhausted =
                job.attemptCount()
                        >= job.maxAttempts();

        String nextStatus =
                permanent || exhausted
                        ? "DEAD"
                        : "RETRY";

        Instant nextAttempt =
                Instant.now()
                        .plusSeconds(
                                backoffSeconds(
                                    job.attemptCount()
                                )
                        );

        int updated = jdbc.update(
            """
            UPDATE mail_outbox
            SET status = ?,
                next_attempt_at = ?,
                last_error_code = ?,
                claim_owner = NULL,
                claim_token = NULL,
                claim_until = NULL,
                updated_at = now()
            WHERE id = ?
              AND claim_token = ?
              AND status = 'SENDING'
            """,
            nextStatus,
            Timestamp.from(nextAttempt),
            safeErrorCode,
            job.id(),
            job.claimToken()
        );

        return updated == 1;
    }

    private long backoffSeconds(
            int attemptCount) {

        int exponent =
                Math.min(
                    Math.max(attemptCount - 1, 0),
                    6
                );

        long base =
                Math.min(
                    30L * (1L << exponent),
                    1800L
                );

        long jitter =
                ThreadLocalRandom.current()
                        .nextLong(0L, 16L);

        return base + jitter;
    }
}
~~~

In the demo, `markFailed` chooses `RETRY` or `DEAD` based on `permanent` and attempt count. `next_attempt_at` for `DEAD` is unused; production can null it out or separate columns per state contract.

`safeErrorCode` must be a controlled category such as `SMTP_TEMPORARY`, `SMTP_AUTH`, or `INVALID_PAYLOAD`. Never write full exception messages, email bodies, or credentials into the DB where sensitive data could leak.

### Result Writer Failure

If SMTP accepted the message but `markSent` fails to commit due to a DB outage:

~~~text
SMTP accepted
DB unavailable during markSent
lease expires
worker retries
=> Duplicate send may occur
~~~

You cannot fix this by simply "calling `markSent` before `send`", because reversing the order risks losing emails. An outbox provides strong durability and recovery, not exactly-once SMTP.

## 23. Workers Must Classify Errors Rather Than Retrying Everything

With Spring Mail:

| Failure | Practice Handling | Production Note |
| --- | --- | --- |
| Temporary SMTP failure | `RETRY` + backoff | Inspect SMTP reply / enhanced status |
| `MailAuthenticationException` | `DEAD`/hold and alert | Never hot-retry bad credentials |
| `MailSendException` | May retry, log diagnostics | Outcome may be uncertain after `DATA` |
| MIME preparation failure | `DEAD`/repair payload | Likely never touched SMTP |
| Unparseable JSON payload | `DEAD`/manual repair | Never send malformed content |
| Attachment temporarily unavailable | `RETRY` if within TTL | Avoid losing files before retries |
| Permanently invalid recipient | `DEAD`/suppression | Classify per provider rules |
| SMTP accepted, result DB update fails | Lease/retry; possible duplicate | Audit unknown outcomes |

`MailSendException#getFailedMessages()` may contain a message-to-exception map, yet it is not a delivery receipt; an empty map does not imply zero errors. A timeout after sending SMTP `DATA` can be an **unknown outcome** where the relay may have accepted the message.

The demo below treats most `MailException` errors as retryable so you can observe recovery, whereas production needs a dedicated classifier aligned to error codes, per-recipient results, and provider contracts rather than mapping every exception to one state.

## 24. Processor: Building MIME and Sending Outside the Claim Transaction

~~~java
package com.example.mailoutbox.mail;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OutboxEmailProcessor {

    private static final Logger log =
            LoggerFactory.getLogger(
                    OutboxEmailProcessor.class
            );

    private final ObjectMapper mapper;
    private final JavaMailSender sender;
    private final MailOutboxResultWriter results;
    private final String fromAddress;

    public OutboxEmailProcessor(
            ObjectMapper mapper,
            JavaMailSender sender,
            MailOutboxResultWriter results,
            @Value("${app.mail.from}")
            String fromAddress) {

        this.mapper = mapper;
        this.sender = sender;
        this.results = results;
        this.fromAddress = fromAddress;
    }

    public void process(ClaimedMailJob job) {

        OrderMailPayload payload;

        try {
            payload = mapper.readValue(
                    job.payloadJson(),
                    OrderMailPayload.class
            );
        } catch (JsonProcessingException ex) {
            results.markFailed(
                    job,
                    "INVALID_PAYLOAD",
                    true
            );
            return;
        }

        try {
            MimeMessage message =
                    composeMessage(job, payload);

            sender.send(message);

        } catch (MailAuthenticationException ex) {
            results.markFailed(
                    job,
                    "SMTP_AUTH",
                    true
            );
            return;

        } catch (MailSendException ex) {
            log.warn(
                    "Mail job {} submission failed; " +
                    "failedMessages={}",
                    job.id(),
                    ex.getFailedMessages().size()
            );

            results.markFailed(
                    job,
                    "SMTP_SEND_OR_UNKNOWN",
                    false
            );
            return;

        } catch (MailException ex) {
            results.markFailed(
                    job,
                    "SMTP_TRANSPORT",
                    false
            );
            return;

        } catch (MessagingException ex) {
            results.markFailed(
                    job,
                    "MIME_PREPARATION",
                    true
            );
            return;
        }

        boolean saved = results.markSent(job);

        if (!saved) {
            log.warn(
                    "SMTP accepted but claim no longer " +
                    "matches; jobId={}",
                    job.id()
            );
        }
    }

    private MimeMessage composeMessage(
            ClaimedMailJob job,
            OrderMailPayload payload)
            throws MessagingException {

        MimeMessage mime =
                sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(
                        mime,
                        false,
                        "UTF-8"
                );

        helper.setFrom(fromAddress);
        helper.setTo(payload.recipientEmail());

        helper.setSubject(
                "Order confirmation "
                + payload.orderId()
        );

        helper.setText(
                "Order " + payload.orderId()
                + " has been confirmed. Total: "
                + payload.totalAmount()
                + " " + payload.currency(),
                false
        );

        mime.setHeader(
                "X-Mail-Job-Id",
                job.id().toString()
        );

        return mime;
    }
}
~~~

This is a **bounded sample implementation**. Production needs full payload/recipient validation before `sender.send`, a dedicated error classifier, per-tenant sender policies, size/MIME controls, properly escaped HTML, and explicit `UNKNOWN_OUTCOME` handling.

### Why Not Annotate `process()` with `@Transactional`?

`process` performs network I/O. Wrapping the whole method in `@Transactional` keeps transactions open while SMTP is slow. Transactions should stay short around **claiming** and **recording outcomes**.

`MailOutboxResultWriter` is a separate bean so `@Transactional` applies through Spring's proxy. Never call a transactional method via `this.method()` expecting proxy-based transactions to start.

## 25. Scheduled Worker: Polling Committed Jobs

~~~java
package com.example.mailoutbox.mail;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.UUID;

@Component
public class OutboxPollingWorker {

    private final MailOutboxClaimer claimer;
    private final OutboxEmailProcessor processor;
    private final MailOutboxResultWriter results;

    private final String workerId =
            UUID.randomUUID().toString();

    public OutboxPollingWorker(
            MailOutboxClaimer claimer,
            OutboxEmailProcessor processor,
            MailOutboxResultWriter results) {

        this.claimer = claimer;
        this.processor = processor;
        this.results = results;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.outbox.poll-ms:1000}"
    )
    public void poll() {

        results.reapExhaustedClaims();

        for (int index = 0; index < 10; index++) {

            Optional<ClaimedMailJob> next =
                    claimer.claimOne(workerId);

            if (next.isEmpty()) {
                return;
            }

            processor.process(next.get());
        }
    }
}
~~~

`workerId` identifies the process instance in the demo. In production, use an instance ID traceable to the pod/deployment rather than sharing one owner ID across unrelated JVMs.

The loop claims **one job at a time** and processes it immediately, avoiding holding leases on a large backlog. There is no large in-memory queue; the DB holds unclaimed work.

`reapExhaustedClaims()` is added in the next step to handle a worker crashing on its final attempt.


## 26. Reaper: Handling Expired Leases on the Final Attempt

The claim SQL checks `attempt_count < max_attempts`. Suppose a worker claims the fifth of five attempts and crashes before recording the outcome. Once the lease expires:

~~~text
status = SENDING
attempt_count = 5
max_attempts = 5
claim_until < now()
~~~

The job is no longer eligible to be claimed and would stay stuck forever without a reaper. Add this method to `MailOutboxResultWriter`:

~~~java
@Transactional
public int reapExhaustedClaims() {

    return jdbc.update(
        """
        UPDATE mail_outbox
        SET status = 'DEAD',
            last_error_code =
                'LEASE_EXPIRED_AT_MAX_ATTEMPTS',
            claim_owner = NULL,
            claim_token = NULL,
            claim_until = NULL,
            updated_at = now()
        WHERE status = 'SENDING'
          AND claim_until < now()
          AND attempt_count >= max_attempts
        """
    );
}
~~~

**Crucial distinction:** `DEAD` here means **automatic retry policy is exhausted**, not proof that the email was definitely never sent. The worker may have submitted to the SMTP relay and crashed right before updating the DB. Route this case to a reconciliation queue or manual dashboard; production systems often use a dedicated `UNKNOWN_OUTCOME` status.

If the reaper runs every second across multiple replicas, limit batch sizes/rates and monitor lock contention at high volume. The demo uses a single simple update to show the semantics.

## 27. Step-by-Step Practice Sequence

With the files above in place:

1. Start PostgreSQL and Mailpit with Docker Compose.
2. Start the Spring Boot app so Flyway runs migrations and the worker begins polling.
3. Send a POST request to create an order.
4. Query the rows in PostgreSQL.
5. Inspect the email in the Mailpit UI.
6. Resend the same request key.
7. Simulate SMTP offline and retry recovery.
8. Test rollback using a test seam.
9. Observe leases when stopping a worker mid-flight.
10. Verify zero mail intents remain after a rolled-back transaction.

Command to start the local environment:

~~~bash
docker compose up -d
~~~

Start Spring Boot using your project's build tool (e.g., from your IDE or project run task). These are **learner instructions**, not commands dependent on this article's environment.

### Calling the API

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-demo-476",
    "recipientEmail": "learner@example.test",
    "totalAmount": 125000,
    "currency": "VND"
  }'
~~~

When both the app and Mailpit are running, an order confirmation message appears in the Mailpit UI at `http://localhost:8025`.

### Querying the Database

~~~sql
SELECT
    o.id AS order_id,
    o.request_key,
    o.status AS order_status,
    m.id AS mail_job_id,
    m.status AS mail_status,
    m.attempt_count,
    m.last_error_code,
    m.submitted_at
FROM app_order AS o
JOIN mail_outbox AS m
    ON m.order_id = o.id
WHERE o.request_key = 'order-demo-476';
~~~

Expected state after Mailpit accepts and the result writer commits:

~~~text
order_status: CONFIRMED
mail_status: SENT
attempt_count: 1
last_error_code: null
submitted_at: timestamp
~~~

If the worker has not run yet, the initial status may be `PENDING`. If SMTP is offline, it may be `RETRY`. Both are valid depending on observation timing.

## 28. Retrying with the Same requestKey

Resend the exact same request:

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-demo-476",
    "recipientEmail": "learner@example.test",
    "totalAmount": 125000,
    "currency": "VND"
  }'
~~~

Expected behavior:

- No new order created.
- Returns the exact same order ID.
- No new outbox job created.
- No "brand-new email solely because the HTTP client retried", unless the existing job is still running or retrying per policy.

Verify:

~~~sql
SELECT COUNT(*)
FROM app_order
WHERE request_key = 'order-demo-476';
~~~

Expected result: `1`.

~~~sql
SELECT COUNT(*)
FROM mail_outbox
WHERE order_id = (
    SELECT id
    FROM app_order
    WHERE request_key = 'order-demo-476'
);
~~~

Expected result is also `1`.

### Same Key, Different Payload

Resending `order-demo-476` with a different `totalAmount` or `recipientEmail` must be rejected. The example throws `IllegalArgumentException`. In a production API, throw a dedicated `IdempotencyKeyConflictException` mapped to HTTP `409 Conflict` rather than silently returning the old order.

Keys must be scoped per actor/tenant in multi-customer apps so Tenant B cannot guess a `requestKey` and access Tenant A's order.

## 29. Testing SMTP Offline: The Outbox Remains Durable

In the local demo, stop Mailpit:

~~~bash
docker compose stop mailpit
~~~

Send a **new request with a new `requestKey`**:

~~~bash
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "requestKey": "order-smtp-offline",
    "recipientEmail": "offline@example.test",
    "totalAmount": 90000,
    "currency": "VND"
  }'
~~~

Even with the test SMTP server down, the order/outbox transaction commits:

~~~sql
SELECT
    o.request_key,
    m.status,
    m.attempt_count,
    m.next_attempt_at,
    m.last_error_code
FROM app_order AS o
JOIN mail_outbox AS m
    ON m.order_id = o.id
WHERE o.request_key = 'order-smtp-offline';
~~~

After the worker's send attempt fails, you will see:

~~~text
request_key       = order-smtp-offline
status            = RETRY
attempt_count     = 1
next_attempt_at   = future timestamp
last_error_code   = SMTP_SEND_OR_UNKNOWN
                 or SMTP_TRANSPORT
~~~

The HTTP service does not depend on SMTP availability to persist business state. That is a major advantage of an outbox over calling `send(...)` directly inside the request.

Restart Mailpit:

~~~bash
docker compose start mailpit
~~~

Once `next_attempt_at` becomes due, the worker reclaims and retries. When accepted by the relay, status transitions to `SENT`.

**Note:** do not leave SMTP stopped so long that the job exceeds `max_attempts` and transitions to `DEAD`. Once `DEAD`, recovery requires controlled manual replay rather than waiting for automatic retries.

## 30. Testing Rollback: Zero Mail Intent

Add a test seam or fault-injection hook in your test environment to throw a runtime exception **before commit**, after both the order and outbox inserts execute inside the transaction.

Then inspect:

~~~sql
SELECT COUNT(*)
FROM app_order
WHERE request_key = 'order-force-rollback';
~~~

Expected: `0`.

~~~sql
SELECT COUNT(*)
FROM mail_outbox
WHERE idempotency_key LIKE 'order-confirmation:%';
~~~

Never rely on a full-table count to verify rollback if earlier mail jobs already exist. Track the exact test job/request specifically—for example, using a fixture that knows the expected order ID or running against a clean test database.

### Why Is a Rollback Test Stronger Than Checking an HTTP 500?

An HTTP 500 only shows the request failed at the application layer. It does not prove:

- That the database rolled back.
- That the outbox row also rolled back.
- That no worker already sent an email.
- That no mail intent committed in a separate transaction.

Integration tests must query **both business state and outbox state** from the real database after the transaction ends.

## 31. Testing a Worker Crash After Claim

Practice scenario:

~~~text
1. Mail job is PENDING.
2. Worker claims -> SENDING.
3. Worker terminates abruptly before sending or saving outcome.
4. Database still shows status SENDING.
5. claim_until elapses.
6. Another worker starts and reclaims the job.
~~~

Inspect:

~~~sql
SELECT
    id,
    status,
    attempt_count,
    claim_owner,
    claim_token,
    claim_until
FROM mail_outbox
ORDER BY created_at DESC
LIMIT 10;
~~~

If the worker is killed right after the SMTP relay accepts but before `markSent`, the job may be resent after the lease expires. That is an **expected limitation** to accept and monitor.

Never run crash/kill experiments on real customer data. Use test SMTP and isolated databases to prevent duplicate production emails.

## 32. Why Shouldn't the Worker Hold a DB Transaction During SMTP Send?

Suppose an SMTP call takes 20 seconds. If the entire send sits inside one transaction:

~~~text
BEGIN
SELECT/UPDATE outbox row
mailSender.send(...) takes 20 seconds
UPDATE outbox result
COMMIT
~~~

the transaction holds row locks and DB connections far too long. Meanwhile, other workers struggle to claim batches and the app suffers lock contention.

Better design:

~~~text
Transaction A:
  claim row + token
  COMMIT

Outside DB transaction:
  compose/send via SMTP

Transaction B:
  update result WHERE id AND claim_token
  COMMIT
~~~

This boundary makes failures clear: crashing between A and B leaves a recoverable lease. There is no distributed transaction with SMTP, so workers must accept retries and the duplicate window.

## 33. Outbox Idempotency vs. SMTP Exactly-Once

Distinguish three classes of identifiers:

| ID | Purpose |
| --- | --- |
| `request_key` | Prevents creating duplicate orders on HTTP retries |
| `mail_outbox.idempotency_key` | Prevents enqueuing duplicate mail jobs for one intent |
| `claim_token` | Blocks stale workers from overwriting DB state |
| `mail_outbox.id` | Tracing the mail job |
| `Message-ID` / correlation header | Finding messages in logs/providers |
| Provider message ID | Reconciling submission/delivery feedback |

Unique constraints solve duplicate **enqueueing**. Lease tokens solve stale **DB updates**. Neither mechanism forces an SMTP relay to reject duplicate messages.

Crash window:

~~~text
JavaMailSender.send returns success
  -> SMTP has accepted
  -> JVM crashes
  -> SENT update not persisted
  -> worker reclaims
  -> SMTP receives another submission
~~~

Reversing the order to mark `SENT` before sending introduces the risk of **losing emails** if a crash happens after marking but before submission.

Therefore, the honest guarantee is **durable intent + at-least-once submission attempts when retries are permitted**, not "guaranteed exactly-once inbox delivery". Recipients may receive duplicates, providers may defer or bounce emails, and delivery must be tracked separately.

## 34. Unknown Outcome After SMTP DATA

SMTP may accept the full message and respond successfully while the response never reaches the client:

~~~text
Client sends DATA
Relay accepts message
Network disconnects
Client observes timeout
~~~

There is not enough evidence to conclude the relay did not accept the message. Retrying risks duplicates; skipping retries risks dropping an unsent message.

Production systems should define an `UNKNOWN_OUTCOME` state or failure category, reconcile via provider APIs/message IDs when available, and apply purpose-specific policies:

- OTPs: never send expired tokens.
- Receipts: may allow retries and audited "resend" actions.
- Marketing: re-check consent/suppression before retrying.
- Security alerts: may require fallback channels or escalation.
- Internal notices: may tolerate duplicates if content is idempotent.

In the demo, `SMTP_SEND_OR_UNKNOWN` intentionally acknowledges uncertainty; when scaling, build a finer-grained classifier rather than treating every `MailSendException` as transient.

## 35. Why Do Retries Need Backoff?

If a provider is offline and 5,000 workers retry continuously, the system can:

- Cause a network connection storm.
- Flood logs and DB writes.
- Exhaust SMTP provider quotas.
- Hit the provider with a massive burst on recovery.
- Get the account throttled or locked.
- Starve other jobs.

`MailOutboxResultWriter` uses exponential backoff plus jitter. Example schedule:

~~~text
attempt 1 -> retry in ~30-45 seconds
attempt 2 -> retry in ~60-75 seconds
attempt 3 -> retry in ~120-135 seconds
attempt 4 -> retry in ~240-255 seconds
...
~~~

Jitter spreads retry timestamps across jobs. In production, also enforce:

- Per-SMTP-account/provider rate limits.
- `Retry-After` honoring when supported by the provider contract.
- Hard cutoffs by attempt count or job age.
- Content/token TTLs.
- Permanent, temporary, and unknown error categories.
- Fair scheduling across tenants and purposes.
- Circuit breakers or account holds on widespread AUTH errors.

Never run a tight `while(true)` loop calling `mailSender.send` immediately after every exception.

## 36. Why Split into Per-Recipient Jobs?

The demo creates **one order → one outbox job → one recipient**. That choice is intentional.

If a single `MimeMessage` addresses A, B, and C, SMTP may accept some recipients and reject others. Retrying the whole message risks duplicating emails to already-accepted recipients.

One job per recipient provides:

- Clear idempotency keys per order, event, and recipient.
- Independent attempt tracking.
- No leakage of other recipients via `To`/`Cc`.
- Individual unsubscribe and suppression checks.
- Isolated quotas and retries.
- Clean reconciliation with provider delivery feedback.

For multi-recipient emails, design recipient-level outcomes and SMTP partial-send semantics. Never treat `MailSendException#getFailedMessages()` as a per-recipient delivery confirmation list.

## 37. Multiple Replicas Running Concurrently

When scaling from one process to three replicas:

~~~text
Worker A  -> database
Worker B  -> database
Worker C  -> database
~~~

All replicas can poll the same table, while atomic claims + `SKIP LOCKED` give each row a single current DB owner/lease during the claim.

Keep in mind:

- `workerId` must distinguish instances.
- Claim batches must not exceed available executor capacity.
- Lease timeouts must exceed expected processing time, with heartbeats for long-running jobs.
- Completion updates must always check the claim token.
- Expired leases are reclaimed.
- The reaper handles jobs that hit max attempts.
- Multi-tenant quotas must be enforced **cluster-wide**, not per JVM.
- Workers crashing between SMTP and DB updates still carry double-send risk.

For very high throughput, you can add outbox CDC or a broker relay, yet **business state and outbox intent must still be written atomically**.

## 38. When to Use an AFTER_COMMIT Event Listener?

A post-commit event listener can wake up the worker immediately:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void onOrderCommitted(
        OrderCommittedEvent event) {

    localDispatcherSignal.wakeUp();
}
~~~

This illustrates an application-provided API and wake-up signal. Prerequisite: **the `mail_outbox` row was already INSERTed in the preceding transaction**.

If the process crashes after commit before the listener fires, periodic polling still picks up the job. The listener only reduces latency; it is not the source of truth.

Never write:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void sendMailAfterCommit(...) {
    mailSender.send(...);
}
~~~

and call that a transactional outbox. Without a durable mail intent, crashing between commit and listener execution loses the email.

## 39. Never Send to Production Providers from Practice Exercises

Use Mailpit to test email formatting and SMTP submission. Before connecting to a real provider, add:

- Domain and `From` identity verification.
- SMTP AUTH and TLS trust/hostname verification.
- Secret manager integration and credential rotation.
- Per-account throttling and quotas.
- MIME/HTML escaping and size limits.
- SPF, DKIM, and DMARC for sending domains.
- Bounce/complaint handling and provider feedback.
- Suppression and consent policies where required.
- Safe logging without leaking recipients or tokens.
- Monitoring for oldest pending age and deliverability.
- Multi-tenant sender routing.
- Alerts on `DEAD` jobs or unknown outcomes.
- Graceful shutdown and lease tuning.

Mailpit accepting an email does not prove it will pass Gmail, Outlook, or production SMTP relay policies. Never copy unauthenticated/no-TLS local config onto public networks.


## 40. Testing Real Transaction Commits

Tests should prove that **order and outbox intent commit together**, not merely verify that `OrderApplicationService` called two repository methods.

Example using Spring Boot tests with an isolated PostgreSQL test database:

~~~java
@SpringBootTest
class OrderOutboxIntegrationTest {

    @Autowired
    OrderApplicationService service;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void createsOrderAndMailIntentTogether() {

        String key =
                "integration-" + UUID.randomUUID();

        CreateOrderRequest request =
                new CreateOrderRequest(
                        key,
                        "buyer@example.test",
                        new BigDecimal("125000.00"),
                        "VND"
                );

        UUID orderId =
                service.placeOrder(request);

        Integer orderCount =
                jdbc.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM app_order
                    WHERE id = ?
                    """,
                    Integer.class,
                    orderId
                );

        Integer mailCount =
                jdbc.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM mail_outbox
                    WHERE order_id = ?
                    """,
                    Integer.class,
                    orderId
                );

        assertEquals(1, orderCount);
        assertEquals(1, mailCount);
    }
}
~~~

Required test imports include JUnit 5, `@SpringBootTest`, Spring `@Autowired`, `JdbcTemplate`, and Java `UUID`/`BigDecimal`. The example focuses on the business transaction invariant; real tests must isolate data and worker scheduling so other tests do not alter states or counts.

If a test method is annotated with `@Transactional`, Spring rolls it back at the end; when verifying a **real commit visible to a worker on another thread**, configure test transaction boundaries appropriately instead of leaving the whole fixture uncommitted.

### Do Not Rely Only on Mocked Repositories

A mock can verify:

~~~text
verify(orderRepository).insert(...)
verify(outboxRepository).enqueue(...)
~~~

yet it cannot prove both operations share the same datasource and transaction manager or commit/roll back atomically. Include at least one integration test using real database transactions.

## 41. Testing Rollback in the Database

Use `TransactionTemplate` to trigger a transaction that fails intentionally after both writes:

~~~java
@Test
void rollbackRemovesBothWrites() {

    String key =
            "rollback-" + UUID.randomUUID();

    CreateOrderRequest request =
            new CreateOrderRequest(
                    key,
                    "rollback@example.test",
                    new BigDecimal("99000.00"),
                    "VND"
            );

    assertThrows(
            IllegalStateException.class,
            () -> transactionTemplate
                    .executeWithoutResult(status -> {

                        OrderRow order =
                                orders.insertOrRead(
                                        request
                                );

                        outbox.enqueueOrderConfirmation(
                                order
                        );

                        throw new IllegalStateException(
                                "Simulated rollback"
                        );
                    })
    );

    Integer ordersAfter =
            jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM app_order
                WHERE request_key = ?
                """,
                Integer.class,
                key
            );

    assertEquals(0, ordersAfter);
}
~~~

In the test fixture, `transactionTemplate`, `orders`, `outbox`, and `jdbc` are injected beans. To check both sides, retain the generated ID in the fixture or query `mail_outbox` by test event/reference; ensure workers cannot pick up uncommitted data and isolate by `requestKey`.

A rollback test must assert that **no matching outbox row remains**, not just the order count. When a unique constraint or serialization error fires, the entire transaction must roll back consistently too.

## 42. Testing Idempotency Across HTTP Retries

~~~java
@Test
void sameRequestKeyCreatesOneOrderAndJob() {

    String key =
            "duplicate-" + UUID.randomUUID();

    CreateOrderRequest request =
            new CreateOrderRequest(
                    key,
                    "same@example.test",
                    new BigDecimal("75000.00"),
                    "VND"
            );

    UUID first =
            service.placeOrder(request);

    UUID second =
            service.placeOrder(request);

    assertEquals(first, second);

    Integer count =
            jdbc.queryForObject(
                """
                SELECT COUNT(*)
                FROM mail_outbox
                WHERE order_id = ?
                """,
                Integer.class,
                first
            );

    assertEquals(1, count);
}
~~~

Add tests for **same key with different payload** to verify conflict rejection, plus concurrency tests sending parallel requests with the same key. Sequential tests alone miss race conditions between concurrent HTTP threads.

In production, scope `requestKey` by tenant, store a request fingerprint or fields to compare, and return explicit HTTP conflict semantics.

## 43. Testing Claim Concurrency

A concurrency test requires a **real database with production locking semantics**. Structure it as:

~~~text
Given:
  20 committed PENDING outbox jobs

Run concurrently:
  Worker A claimOne(...)
  Worker B claimOne(...)

Assert:
  No job ID was claimed by both A and B
  Each claim's claimToken is non-null
  Matching row count transitioned to SENDING
  attemptCount incremented once per claim
~~~

Then:

~~~text
Expire one lease in the test DB.
Worker C reclaims it.
New token differs from old token.

Old worker:
  markSent(jobId, oldToken)
  => updated row count = 0

New worker:
  markSent(jobId, newToken)
  => updated row count = 1
~~~

This verifies **DB fencing**. It does not prove the SMTP provider won't receive a duplicate if the old worker already sent before losing its lease.

You do not need real wall-clock waits for every test: update `claim_until` in the test database or inject a time abstraction. Concurrency tests mocking `JdbcTemplate` never prove `SKIP LOCKED` works under real contention.

## 44. Testing SMTP Success with Mailpit

An integration test or manual run can execute:

~~~text
1. Insert committed mail_outbox PENDING.
2. Worker claims it.
3. Build MimeMessage.
4. JavaMailSender.send to Mailpit.
5. Assert Mailpit accepted/captured the message.
6. Assert job status is SENT.
7. Next poll: SENT job is not claimed again.
~~~

Match using `X-Mail-Job-Id` or a correlation ID rather than grabbing "the latest email" from a mailbox shared by multiple tests.

With GreenMail or another SMTP test server, you can assert recipients, Subject, and body without touching the Internet.

When tests poll asynchronously, wait on a condition with a deadline rather than a fixed `Thread.sleep`:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {

        assertEquals(
                "SENT",
                readOutboxStatus(mailJobId)
        );
    });
~~~

`await()` represents an Awaitility-style API if your project uses that test dependency; `readOutboxStatus` is a test helper. Do not assume this snippet runs standalone without configured test SMTP and database fixtures.

## 45. Testing SMTP Failures and Retries

Create a new job while Mailpit is stopped, or use a fake sender throwing a suitable `MailException`.

Expected progression:

~~~text
PENDING
 -> SENDING (attempt_count = 1)
 -> RETRY (next_attempt_at > now())

After delay:
 -> SENDING (attempt_count = 2)
 -> SENT once SMTP accepts
~~~

Assertions:

- Order remains `CONFIRMED` even when SMTP fails.
- Mail intent never disappears.
- Retry does not execute before its deadline.
- `last_error_code` holds a safe category.
- A job is never sent concurrently under two active claims.
- On the final failed attempt, status transitions to `DEAD`.
- If the worker dies on the final attempt, the reaper releases the claim into a reviewable state.
- Sensitive payload contents are never logged.

Never check only how many times an exception was thrown; verify database state after every transaction.

## 46. Testing a Crash After SMTP Acceptance

This scenario is decisive for understanding outbox limits:

~~~text
Fake SMTP sender:
  records accepted submission
  returns success

Result writer:
  simulates database failure
  fails to save SENT

Lease:
  expires

Next worker:
  reclaims job
  submits again
~~~

The result can be **two submissions for the same outbox job**.

Tests should verify:

- The job still recovers cleanly.
- Exactly-once SMTP is never claimed.
- Attempt and correlation IDs are recorded for investigation.
- When an old token is stale, the old worker's update does not overwrite the DB.
- The retry policy accounts for unknown outcomes.
- Content renders consistently on retry, while non-SMTP business side effects stay idempotent.

If a provider offers a documented idempotency API or token, apply it per that provider's contract; plain SMTP has no cross-network idempotency key.

## 47. Basic Monitoring for the Project

When moving toward production, measure:

| Metric | Meaning |
| --- | --- |
| `mail_outbox_pending_count` | Unsent jobs |
| `mail_outbox_retry_count` | Jobs awaiting retry |
| `mail_outbox_oldest_pending_age_seconds` | Backlog latency |
| `mail_outbox_sending_count` | Active leases |
| `mail_outbox_expired_lease_total` | Worker crashes / timeouts |
| `mail_outbox_send_attempt_total` | Submission attempts |
| `mail_outbox_send_duration_seconds` | SMTP call duration |
| `mail_outbox_failed_total` | Failures by category |
| `mail_outbox_dead_count` | Jobs requiring manual action |
| `mail_outbox_unknown_outcome_total` | Potential ambiguous submissions |
| `mail_outbox_duplicate_intent_total` | Blocked duplicate enqueues |
| `mail_outbox_reaper_total` | Expired final-claim cleanups |

Log by `mailJobId`, `orderId`, attempt, and provider route. Never put recipient addresses, bodies, tokens, or PII-bearing error text into metric labels.

### When to Alert

- `PENDING` jobs older than SLA.
- Continuous SMTP AUTH or TLS failures.
- Rising `DEAD` counts.
- Growing retry backlog that never drains.
- Spike in lease expirations after a deployment.
- Workers failing to poll or claim jobs.
- Spikes in unknown outcomes during network/provider incidents.
- Security/OTP jobs delayed past content expiration.

In production, when a job is marked `DEAD`, maintain a review workflow and controlled replay capability rather than deleting rows and losing audit history.

## 48. Demo Limitations Before Scaling

This practice project intentionally leaves out:

- Multi-tenant authorization and sender registries.
- Granular SMTP 4xx/5xx reply-code classification.
- Per-recipient partial-send handling for multi-recipient MIME messages.
- Template engines, HTML escaping, and attachments.
- Per-purpose/tenant retry strategies.
- Distributed quotas and rate limiting.
- Priority and fair scheduling.
- Heartbeat lease renewal for long-running jobs.
- Provider delivery and webhook feedback.
- Batch claiming matched to executor pool capacity.
- Payload schema versioning and immutable attachment storage.
- Reconciliation of unknown outcomes.
- Data retention, legal hold, and GDPR/PII policies.
- Access-controlled alerting and metrics.
- UIs for managing dead-letter queues and manual replays.

Those belong to production scale depending on your needs. The goal of Row 476 is **nailing transaction boundaries and building a durable mail outbox that sends after commit**.

## 49. Common Implementation Mistakes

### 49.1. INSERTing Outbox After Transaction Commit

This is **not** an atomic transactional outbox. Crashing between committing the order and inserting into the outbox loses the send intent.

### 49.2. Sending SMTP Inside `@Transactional`

SMTP never rolls back with the DB. If the DB rolls back after relay acceptance, the customer still receives the email.

### 49.3. Sending Only Inside an `AFTER_COMMIT` Listener

Without a committed outbox row, listener tasks are lost if the process crashes.

### 49.4. Wrapping `mailSender.send` in `@Async` and Calling It Done

In-memory executor queues do not survive restarts and cannot replace a persistent DB job store.

### 49.5. Outbox Using a Separate `REQUIRES_NEW` Transaction

The mail intent can commit even when the business transaction rolls back.

### 49.6. Missing Unique Idempotency Key

HTTP retries and duplicate webhooks create multiple mail jobs.

### 49.7. Generating a New UUID Request Key on Every Retry

Defeats duplicate detection for the same business intent.

### 49.8. SELECT and SEND Without Claiming

Two workers read the same job and send duplicates.

### 49.9. Holding a DB Transaction Open Across SMTP

Lock contention and network timeouts stall transactions.

### 49.10. No Lease Expiration

Crashing in `SENDING` leaves the job stuck forever.

### 49.11. No Fencing Token

A stale worker waking up late overwrites DB state after reclamation.

### 49.12. Lease Shorter Than SMTP Timeout

Two workers can send the same job simultaneously.

### 49.13. Ignoring Expired Leases on the Final Attempt

A `SENDING` job at `max_attempts` stays stuck forever.

### 49.14. Treating `SENT` as Delivered

SMTP acceptance proves neither Inbox placement nor user reads.

### 49.15. Assuming an Outbox Gives Exactly-Once SMTP

Crashing after relay acceptance before the DB update still causes duplicate sends.

### 49.16. Immediately Retrying Every Exception

Causes retry storms; hard errors and AUTH failures need distinct policies.

### 49.17. Skipping Token/Consent Checks at Send Time

Workers may send expired content or email recipients who opted out.

### 49.18. Storing Large Attachments in JSONB Outbox Columns

Bloats the database and worker heap; use immutable object-storage references for large files.

### 49.19. Claiming Too Many Jobs Before Executor Capacity Exists

Leases on queued tasks expire before workers even process them.

### 49.20. Missing Oldest-Pending Age Alerts

The outbox can back up for hours while the API keeps returning success.

### 49.21. Skipping Real DB Tests for Rollback and Concurrency

Mocks prove neither ACID atomicity nor `SKIP LOCKED` behavior under contention.

### 49.22. Using Production SMTP for Practice Exercises

Risks spam, leaking test data, and harming provider reputation. Use Mailpit or isolated test servers.

## 50. Scenario Q&A

**Q1.** Is the outbox row created before or after transaction commit?

It must be **INSERTed inside the same business transaction**. Workers process rows only after commit.

**Q2.** If the business transaction rolls back, does the worker send an email?

No durable outbox row exists from that transaction, so the worker has no job to send.

**Q3.** If SMTP is offline, should order creation still succeed?

Usually yes—commit the order and outbox, letting the worker retry per policy. That depends on the use case, yet business DB transactions should not block on SMTP.

**Q4.** Why not use `@TransactionalEventListener(AFTER_COMMIT)` to call SMTP directly?

A crash after commit before the listener fires loses the send intent if no durable outbox row exists.

**Q5.** Why separate `requestKey` and `idempotencyKey`?

They guard two layers: duplicate HTTP order creation and duplicate mail-intent enqueuing.

**Q6.** Why must claiming happen inside a short transaction?

So multiple workers coordinate safely without holding DB locks during slow SMTP I/O.

**Q7.** Does `SKIP LOCKED` guarantee zero duplicate sends?

No. It coordinates claims and row locking; it cannot prevent duplicates caused by lease expiration or crashes.

**Q8.** Does `claimToken` replace the idempotency key?

No. The token changes on every attempt, whereas the idempotency key stays fixed per intent.

**Q9.** What happens if a worker crashes after SMTP acceptance but before `markSent`?

The job can be retried and sent twice; there is no exactly-once SMTP.

**Q10.** Why is a reaper needed for the final attempt?

If a worker dies when `attempt_count = max_attempts`, the claim query skips the job; the reaper moves it out of stuck `SENDING` into a state for manual action.

**Q11.** Does `SENT` mean the user sees the email in Gmail?

No. In this demo it means the SMTP relay accepted submission, not delivery.

**Q12.** Why use backoff and jitter?

To avoid retry storms during temporary provider outages and spread traffic once service recovers.

**Q13.** Does a timeout exception after SMTP `DATA` mean the email wasn't sent?

No. The relay may have accepted it while the client missed the reply, leaving an uncertain outcome.

**Q14.** What if two HTTP requests reuse a `requestKey` with different recipient emails?

Reject as a conflict rather than silently creating another intent; unique keys need explicit rules.

**Q15.** Why send to one recipient per job in the demo?

It simplifies idempotency, retries, privacy, and outcome tracking while avoiding partial-recipient complexity.

**Q16.** What if a mail job stores an attachment in local `/tmp` and the worker restarts on another pod?

The file is lost; production must store content durably for the full retry window.

**Q17.** When should an endpoint return `202 Accepted`?

When the API accepts work for asynchronous processing; make clear that mail intent was persisted, not delivered.

**Q18.** How do you prove transaction atomicity?

Write integration tests for both commits and rollbacks against a real database, checking both business rows and outbox rows instead of only mocking method calls.

## 51. Mental Model

~~~mermaid
flowchart TD
    A["Create order HTTP request"] --> B["Validate requestKey + tenant"]
    B --> C["BEGIN database transaction"]
    C --> D["Insert/find order"]
    C --> E["INSERT outbox PENDING unique intent"]
    D --> F["COMMIT"]
    E --> F
    F --> G["Scheduled worker"]
    G --> H["Claim due row with SKIP LOCKED"]
    H --> I["COMMIT claim + lease token"]
    I --> J["Compose MIME"]
    J --> K["JavaMailSender.send"]
    K --> L{"Outcome"}
    L -->|"Accepted"| M["Mark SENT with token"]
    L -->|"Temporary"| N["RETRY + backoff"]
    L -->|"Permanent"| O["DEAD / review"]
    L -->|"Unknown"| P["Reconcile / retry policy"]
    N --> G
    P --> G
    M --> Q["Provider feedback if available"]
~~~

Core principles to remember:

1. **Write the outbox inside the same business transaction**, never INSERT after commit.
2. **Workers send mail after commit**, reading only durable rows.
3. **SMTP never participates in the database's ACID transaction**; never send inside `@Transactional` expecting rollback to unsend mail.
4. **`@Async` and `AFTER_COMMIT` do not replace a durable outbox**; they only supplement scheduling or wake-ups.
5. **Unique request keys and unique mail idempotency keys guard two distinct duplicate boundaries**.
6. **Claims use short transactions and row locking / conditional updates**, never holding DB locks across network I/O.
7. **Leases need expirations and fencing tokens**, plus a reaper for expired final attempts.
8. **`SENT` means submitted to the relay**; delivered and bounced belong to downstream workflows.
9. **Unknown SMTP outcomes can cause duplicates on retry**; an outbox never promises exactly-once delivery.
10. **Retries need backoff, jitter, and failure classification**, never infinite blind retries on every exception.
11. **One job per recipient avoids partial-send complexity** and simplifies per-recipient quotas and consent.
12. **Payloads must be stable enough to build emails across restarts**, pinning templates, snapshots, and attachment versions where needed.
13. **Production requires securing senders, recipients, tokens, and attachments**, alongside quotas, monitoring, and retention.
14. **Monitor backlog age, dead jobs, lease expirations, and unknown outcomes** to catch incidents early.
15. **Test commits, rollbacks, concurrency, SMTP failures, and crash windows** using isolated test databases and SMTP servers.

In this Spring Framework Mail project, the decisive step is not adding `@Scheduled` or a retry loop, but **getting the transaction boundary right**: business updates and send intent commit atomically, while SMTP submission occurs after commit via a worker backed by durable jobs. With this schema, idempotency, claim/lease mechanics, retries, and hands-on tests, the application recovers cleanly from SMTP outages and restarts without hiding duplicate risks at the external transport boundary.





