# Bounded Retries, Backoff, and Avoiding Duplicate Business Execution

## 1. When a timeout does not mean the business action failed to complete

In the **Spring Boot - testing** module under **Contracts and Resilience**, a system often calls a payment service, order service, inventory reservation, message broker, or remote state store. On HTTP 503, 429, connection errors, or timeouts, we want to **retry** to recover. However, if the upstream **already committed** the transaction before the client lost the response, resending the command can **charge twice**.

~~~text
Client                     Payment service                 Database
   | POST /payments, key=K     |                             |
   |------------------------->| INSERT inbox K + charge ---->|
   |                          |<------------ COMMIT ---------|
   |  timeout / lost response |                             |
   X                          |                             |
   | POST /payments, key=K     |                             |
   |------------------------->| sees committed marker K     |
   |                          | skips second UPDATE         |
   |<--------- receipt -------|                             |
~~~

**The solution requires two independent responsibilities:** the client performs bounded retries with backoff/time budgets, while the server protects business side effects with a **stable idempotency key + persisted state/unique constraint + transaction**. No retry annotation turns an arbitrary POST into exactly-once. Conversely, an idempotent API with unbounded retries can still exhaust CPU, network, or thread pools.

This lesson uses **Java 17, Spring Boot 3.5.16, Spring Retry 2.x, Spring JDBC, H2, and JUnit Jupiter**. It includes a runnable project with two transaction layers handling duplicate keys properly, simulated 503 tests, response-lost-after-commit, payload conflicts, exhausted attempts, marker rollback, exponential backoff, and a fake sleeper **without `Thread.sleep`**. Extended sections cover HTTP retries, `Retry-After`, messaging, outbox, overall deadlines, and multi-worker races.

## 2. Retry, backoff, timeout, and idempotency are distinct layers

| Concept | Purpose | Does not guarantee |
| --- | --- | --- |
| Timeout per attempt | Avoid waiting forever on a socket/DB call | That the upstream did not commit before client timeout |
| Retry | Re-attempt an operation on errors classified as transient | That the operation will not duplicate side effects |
| Backoff | Space out retries to give upstream time to recover | That upstream will recover on the next attempt |
| Jitter | Randomize delays to prevent thousands of clients retrying in lockstep | Correct business state |
| Retry budget | Limit attempts, time, traffic, and concurrency | That every failure recovers |
| Circuit breaker | Pause calls to a consistently failing dependency | Whether a prior command committed or not |
| Idempotency | Repeating the same logical action causes no extra effect after the first | Solving connection drops |
| Transactional outbox | Record business state and publish intent in one DB commit | That relay/downstream never sees duplicate messages |
| Reconciliation | Query and resolve outcomes in unknown states | Immediately eliminating all transient errors |

With **`maxAttempts=3`**, Spring Retry counts **the first attempt plus at most two retries**, not three retries on top of the initial attempt. Thus there are at most **two backoffs** in a three-attempt operation. If the first attempt succeeds, no backoff occurs; if a non-retryable exception occurs, there is no second attempt.

### Defining a logical action

Two requests carrying identical JSON that represent **two legitimate transactions** must carry **two distinct idempotency keys**. Conversely, a single logical transaction being re-sent must **keep the exact same key**, even across different connections or after a restart.

An idempotency key should not be a thread ID, Kafka partition-offset, random value generated inside a retry callback, or an uncontracted tracing correlation ID. In multi-tenant systems, scope can be `(tenantId, operationType, key)`. The demo uses a DB-wide unique key for simplicity.

## 3. Distinguishing retryable vs. non-retryable errors

| Signal | Retry? | Notes |
| --- | --- | --- |
| HTTP 503 | Usually yes | May include `Retry-After`; bounded, with deadline |
| HTTP 429 | Conditionally | Respect quota/`Retry-After` and budget |
| 502, 504 | Conditionally | Request may already have reached upstream |
| Read timeout/connection reset | Conditionally | **Ambiguous outcome**: requires idempotency |
| HTTP 500 | Per contract | Never assume all 500s are transient |
| HTTP 400 malformed/validation | No | Resending the exact payload will not fix the error |
| HTTP 401/403 | Not blindly | Requires auth/permission handling |
| HTTP 404 | Per domain | Could be eventual consistency or permanent |
| HTTP 409 idempotency conflict | No | Same key + different payload requires investigation |
| DB deadlock/serialization failure | Possible | Retry the **entire transaction** after rollback |
| Broken application invariant | No | Never retry `NullPointerException` or permanent validation |
| Interrupted/cancelled | Do not swallow to retry | Honor cancellation, restore interrupt |
| Kafka/Nack redelivery | Broker-level retry | Consumer still needs deduplication |

**Never catch every `RuntimeException` and wrap it in a transient exception.** Doing so causes code bugs or business conflicts to be replayed multiple times, potentially multiplying damage. Select a small, intentional set of retryable exceptions.

### HTTP semantics

RFC 9110 defines GET/HEAD as safe, and GET/HEAD/PUT/DELETE as idempotent in their *intended effect* under HTTP semantics. **POST is never assumed idempotent by default.** A POST may be retried safely **only if the API contracts idempotency**, such as `Idempotency-Key` backed by a server-side unique marker; never assume sending the header alone suffices if the server ignores it.

## 4. Max attempts, backoff, and total duration

Spring Retry 2.x supports:

~~~java
RetryTemplate retry = RetryTemplate.builder()
        .maxAttempts(3)
        .retryOn(TemporaryGatewayFailure.class)
        .exponentialBackoff(100, 2.0, 800)
        .build();
~~~

This is a snippet; the exception class is defined in the complete code below. This policy allows three attempts with expected delays of 100 ms and 200 ms if the first two attempts fail. For jitter, Spring Retry offers `exponentialBackoff(100, 2.0, 800, true)`; randomized delays cannot be asserted down to exact milliseconds like the deterministic variant.

Capped exponential backoff formula:

\[
d_k = \min(d_{\max}, d_0\cdot m^{k-1})
\]

With `d0=100 ms`, `m=2`, `dmax=250 ms`, and 5 attempts:

| Retry # | Delay |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 250 ms |
| 4 | 250 ms |

The 800 ms total is **only wait time**, excluding network/DB/GC overhead and the attempts themselves. Three attempts each with a 3-second timeout plus 100 + 200 ms backoff can take roughly **9.3 seconds** or more, violating a 2-second request SLO. Design an **overall deadline** and shrink per-attempt timeouts to fit the remaining budget.

`RetryTemplate` executes synchronously in this example: real backoff blocks the calling thread. High-QPS systems must weigh concurrency limits, circuit breakers, async/non-blocking retries, or queues rather than sleeping many request threads.

## 5. `Retry-After` is not automatically understood by `exponentialBackoff`

HTTP `Retry-After` can be a number of seconds or an HTTP-date (RFC 9110). Example:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 3
~~~

HTTP 429 from RFC 6585 can also include `Retry-After`. Calling `.exponentialBackoff(100,2.0,800)` **does not read headers** and will not wait 3 seconds automatically. To honor the header, the adapter/policy must:

1. Parse formats, timezones/dates, and validate properly.
2. Compute delay, optionally combining with exponential policy.
3. Avoid retrying earlier than requested when required by contract.
4. Never sleep unboundedly on untrusted headers; clamp to SLO/deadline.
5. If waiting exceeds the deadline, **do not retry**—return status or enqueue for later.
6. Record rate-limit and retry-exhaustion metrics without logging secrets.

Likewise, increasing the delay from 100 ms to 10 seconds does not fix a **non-idempotent** request. Idempotency governs business safety; backoff governs retry timing.

## 6. Nested retries multiply attempt counts

A Spring service with an outer retry of 3 attempts, an HTTP SDK internally retrying 3 attempts, and a reverse proxy retrying 2 times can emit **3 × 3 × 2 = 18** sends upstream, depending on configuration and failure point.

~~~text
Outer Spring Retry maxAttempts = 3
   HTTP SDK implicit attempts = 3
      Proxy retry attempts = 2
          -> worst-case 18 physical requests
~~~

This is a **theoretical upper bound**, not a claim every failing request hits 18 sends. Audit retry layers across network clients, gateways, load balancers, DB drivers, Kafka producers, and queue workers. Retry amplification can turn an outage into a traffic storm. Metrics should distinguish **logical operations, client attempts, and physical sends**.

## 7. Demo architecture and transaction boundaries

The sample project splits responsibilities:

~~~text
PaymentCommand(key=K, accountId=A, amountCents=250)
      |
      v
RetryingPaymentClient
    RetryTemplate(maxAttempts=3, retryOn transient)
      |
      v
ChargeGateway           (HTTP adapter in production)
      |
      v
PaymentProcessor
      |
      +--> PaymentWriteTransaction.applyOnce()
      |        @Transactional
      |        INSERT payment_inbox (unique key K)
      |        UPDATE account_balances +250
      |        COMMIT
      |
      +--> On duplicate-key exception:
               failed transaction already ROLLED BACK
               SELECT committed marker K
               same account/amount? -> return existing receipt
               changed payload?    -> conflict, no retry
~~~

In the **runnable test suite**, the gateway is a Java lambda that can throw before or after `PaymentProcessor`. It simulates lost responses without **opening an HTTP socket**, making these boundary + DB integration tests rather than HTTP end-to-end tests. Later sections describe extending with `RestClient` and WireMock.

**Core principle:** retry lives on the caller side; transaction/idempotency lives on the service authorized to mutate business state. Clients cannot rely on an in-memory Map to prevent double charges across restarts or multiple pods.

## 8. File layout: Java 17 + Spring Boot 3.5

~~~text
settings.gradle
build.gradle
src/main/java/com/example/retrysafety/
  RetrySafetyApplication.java
  PaymentCommand.java
  PaymentReceipt.java
  TemporaryGatewayFailure.java
  IdempotencyConflictException.java
  ChargeGateway.java
  PaymentWriteTransaction.java
  PaymentProcessor.java
  RetryingPaymentClient.java
  RetryConfiguration.java
src/main/resources/
  application.properties
  schema.sql
src/test/java/com/example/retrysafety/
  RetryingPaymentClientTest.java
  BackoffPolicyTest.java
~~~

All Java classes live in package `com.example.retrysafety`. The lesson runs offline once dependencies are cached, needing no Docker, Kafka, or API keys. H2 demonstrates basic unique keys and transactions, yet does not replace PostgreSQL/MySQL Testcontainers for production lock and race semantics.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'retry-safety-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.retry:spring-retry'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
}
~~~

The Spring Boot 3.5 BOM manages compatible versions of Spring Retry and H2. The sample uses **programmatic `RetryTemplate`**, so no AOP dependency is needed to enable `@Retryable`. Switching to annotation-based retries requires Spring AOP and `@EnableRetry`.

## 9. Schema: unique marker must commit with the business effect

**`src/main/resources/schema.sql`:**

~~~sql
CREATE TABLE IF NOT EXISTS account_balances (
    account_id VARCHAR(80) PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_inbox (
    idempotency_key VARCHAR(100) PRIMARY KEY,
    account_id VARCHAR(80) NOT NULL,
    amount_cents BIGINT NOT NULL
);
~~~

**`src/main/resources/application.properties`:**

~~~properties
spring.datasource.url=jdbc:h2:mem:retry_safety;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
spring.datasource.hikari.maximum-pool-size=6
~~~

A DB unique key prevents two workers from committing the same marker `K`. Yet **a unique marker alone is not enough** if `INSERT marker` commits in one transaction and `UPDATE balance` runs in another: the marker could commit while the business update rolls back, causing subsequent replays to skip erroneously.

The demo stores account/amount alongside the marker to distinguish same-key + same-payload from same-key + **changed business payload**. Production systems should also store tenant, currency, operation type, canonical payload digest, response, status, timestamps, and retention policies.

## 10. Application, `PaymentCommand`, and `PaymentReceipt`

**`src/main/java/com/example/retrysafety/RetrySafetyApplication.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RetrySafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RetrySafetyApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/retrysafety/PaymentCommand.java`:**

~~~java
package com.example.retrysafety;

public record PaymentCommand(
        String idempotencyKey,
        String accountId,
        long amountCents
) {
}
~~~

**`src/main/java/com/example/retrysafety/PaymentReceipt.java`:**

~~~java
package com.example.retrysafety;

public record PaymentReceipt(
        String idempotencyKey,
        String accountId,
        long amountCents
) {
}
~~~

The command is constructed **before** the retry loop; the idempotency key represents **one logical payment intent**. Never call `UUID.randomUUID()` inside the `RetryTemplate` callback. For money, `long cents` avoids `double` floating-point inaccuracies; production still needs overflow protection, currencies, amount limits, account ownership, and settlement semantics.

## 11. Transient exception and idempotency conflict

**`src/main/java/com/example/retrysafety/TemporaryGatewayFailure.java`:**

~~~java
package com.example.retrysafety;

public final class TemporaryGatewayFailure
        extends RuntimeException {

    public TemporaryGatewayFailure(String message) {
        super(message);
    }

    public TemporaryGatewayFailure(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
~~~

**`src/main/java/com/example/retrysafety/IdempotencyConflictException.java`:**

~~~java
package com.example.retrysafety;

public final class IdempotencyConflictException
        extends RuntimeException {

    public IdempotencyConflictException(String message) {
        super(message);
    }
}
~~~

`TemporaryGatewayFailure` represents a transient failure permitted by the retry policy; `IdempotencyConflictException` represents **the same key with conflicting payload**. The two intentionally do not share a retryable superclass.

When an HTTP adapter encounters HTTP 429 or 503, it can map them to `TemporaryGatewayFailure`. Never wrap all 4xx/5xx errors or `RuntimeException` as transient because contract, authorization, and validation errors cannot be fixed by resending the same request.

## 12. Transaction: INSERT marker first, then atomic UPDATE

**`src/main/java/com/example/retrysafety/PaymentWriteTransaction.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentWriteTransaction {

    private final JdbcTemplate jdbc;

    public PaymentWriteTransaction(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public PaymentReceipt applyOnce(PaymentCommand command) {
        if (command == null
                || command.idempotencyKey() == null
                || command.idempotencyKey().isBlank()
                || command.accountId() == null
                || command.accountId().isBlank()
                || command.amountCents() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid payment command"
            );
        }

        jdbc.update(
                """
                INSERT INTO payment_inbox
                  (idempotency_key, account_id, amount_cents)
                VALUES (?, ?, ?)
                """,
                command.idempotencyKey(),
                command.accountId(),
                command.amountCents()
        );

        int updated = jdbc.update(
                """
                UPDATE account_balances
                   SET balance_cents = balance_cents + ?
                 WHERE account_id = ?
                """,
                command.amountCents(),
                command.accountId()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Unknown account: " + command.accountId()
            );
        }

        return new PaymentReceipt(
                command.idempotencyKey(),
                command.accountId(),
                command.amountCents()
        );
    }
}
~~~

**One database transaction covers both the marker and the business effect.** If the account does not exist, the unchecked exception makes Spring roll back the marker too, allowing replay once fixed. Once the marker commits, the unique constraint rejects duplicate inserts before the balance can be credited again.

`UPDATE balance_cents = balance_cents + ?` is an atomic SQL increment, avoiding Java read-modify-write lost updates when two events with **different keys** run concurrently. H2 does not prove production DB locking and isolation semantics completely.

**Major pitfall:** catching `DuplicateKeyException` **inside** the `@Transactional` method and continuing to query/update. In PostgreSQL, a unique violation puts the transaction into an aborted state. Let the exception exit the transaction interceptor to roll back first, then handle duplicates in an outer bean.

## 13. `PaymentProcessor`: rolled-back duplicate and payload comparison

**`src/main/java/com/example/retrysafety/PaymentProcessor.java`:**

~~~java
package com.example.retrysafety;

import java.util.List;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class PaymentProcessor {

    private final PaymentWriteTransaction transactions;
    private final JdbcTemplate jdbc;

    public PaymentProcessor(
            PaymentWriteTransaction transactions,
            JdbcTemplate jdbc
    ) {
        this.transactions = transactions;
        this.jdbc = jdbc;
    }

    public PaymentReceipt charge(PaymentCommand command) {
        try {
            return transactions.applyOnce(command);
        } catch (DuplicateKeyException duplicate) {
            // applyOnce transaction has already ROLLED BACK.
            List<PaymentReceipt> existing = jdbc.query(
                    """
                    SELECT idempotency_key, account_id, amount_cents
                    FROM payment_inbox
                    WHERE idempotency_key = ?
                    """,
                    (rs, rowNum) -> new PaymentReceipt(
                            rs.getString("idempotency_key"),
                            rs.getString("account_id"),
                            rs.getLong("amount_cents")
                    ),
                    command.idempotencyKey()
            );

            if (existing.size() != 1) {
                throw new IdempotencyConflictException(
                        "Idempotency key not resolvable: "
                                + command.idempotencyKey()
                );
            }

            PaymentReceipt receipt = existing.get(0);
            if (!receipt.accountId().equals(command.accountId())
                    || receipt.amountCents()
                            != command.amountCents()) {
                throw new IdempotencyConflictException(
                        "Conflicting idempotency key: "
                                + command.idempotencyKey()
                );
            }

            return receipt;
        }
    }
}
~~~

This pattern guarantees:

1. **New key** → transaction writes marker + updates balance, then returns receipt.
2. **Existing key + same payload** → duplicate insert rolls back, committed marker is queried, old receipt is returned, **no second UPDATE runs**.
3. **Existing key + different payload** → throws `IdempotencyConflictException`, no retry.
4. **Business update fails before commit** → marker rolls back; later execution is not falsely skipped.

`transactions.applyOnce` is a call from one Spring bean to **another bean**, passing through the `@Transactional` proxy. Calling `this.applyOnce(...)` on the same object bypasses the proxy via self-invocation. Placing the marker in `REQUIRES_NEW` while the business update uses another transaction also breaks atomicity.

**Limitation:** production systems must also handle **in-flight** duplicates, payload canonicalization, per-tenant keys, retention, failover, and API state reconciliation; this demo protects a single DB effect.

## 14. `RetryingPaymentClient` preserves the same command across all attempts

**`src/main/java/com/example/retrysafety/ChargeGateway.java`:**

~~~java
package com.example.retrysafety;

@FunctionalInterface
public interface ChargeGateway {
    PaymentReceipt charge(PaymentCommand command);
}
~~~

**`src/main/java/com/example/retrysafety/RetryingPaymentClient.java`:**

~~~java
package com.example.retrysafety;

import java.util.Objects;
import org.springframework.retry.support.RetryTemplate;

public class RetryingPaymentClient {

    private final ChargeGateway gateway;
    private final RetryTemplate retries;

    public RetryingPaymentClient(
            ChargeGateway gateway,
            RetryTemplate retries
    ) {
        this.gateway = Objects.requireNonNull(
                gateway, "gateway"
        );
        this.retries = Objects.requireNonNull(
                retries, "retries"
        );
    }

    public PaymentReceipt charge(PaymentCommand command) {
        Objects.requireNonNull(command, "command");

        return retries.execute(context ->
                gateway.charge(command)
        );
    }
}
~~~

`RetryTemplate.execute` can invoke the callback multiple times on retryable errors, and the callback **sees the same `PaymentCommand` instance**. If a timeout occurs after commit, retries send the **same key**. Business logic does not increment balances inside the callback; business mutations belong to the server-side processor.

**`src/main/java/com/example/retrysafety/RetryConfiguration.java`:**

~~~java
package com.example.retrysafety;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;

@Configuration(proxyBeanMethods = false)
public class RetryConfiguration {

    @Bean
    RetryTemplate paymentRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TemporaryGatewayFailure.class)
                .exponentialBackoff(100, 2.0, 800)
                .build();
    }

    @Bean
    ChargeGateway localChargeGateway(
            PaymentProcessor processor
    ) {
        // Offline demo adapter; sends no real HTTP traffic.
        return processor::charge;
    }

    @Bean
    RetryingPaymentClient retryingPaymentClient(
            ChargeGateway gateway,
            RetryTemplate paymentRetryTemplate
    ) {
        return new RetryingPaymentClient(
                gateway, paymentRetryTemplate
        );
    }
}
~~~

The integration test constructs a **noBackoff** retry template to verify attempt counts without sleeping. A separate test wires `ExponentialBackOffPolicy` with a fake sleeper to verify exact delays. For a production HTTP adapter, **replace** the `localChargeGateway` bean or separate via profiles/qualifiers so two candidates of the same type do not collide.

## 15. Integration tests: eight concrete scenarios

**`src/test/java/com/example/retrysafety/RetryingPaymentClientTest.java`:**

~~~java
package com.example.retrysafety;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.retry.support.RetryTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = RetrySafetyApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class RetryingPaymentClientTest {

    @Autowired PaymentProcessor processor;
    @Autowired JdbcTemplate jdbc;

    private String account;

    @BeforeEach
    void setUpOwnAccount() {
        account = "wallet-" + UUID.randomUUID();
        jdbc.update(
                """
                INSERT INTO account_balances
                  (account_id, balance_cents)
                VALUES (?, ?)
                """,
                account, 1_000L
        );
    }

    @AfterEach
    void cleanOnlyThisTestsRows() {
        jdbc.update(
                """
                DELETE FROM payment_inbox
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
        jdbc.update(
                """
                DELETE FROM account_balances
                WHERE account_id IN (?, ?)
                """,
                account, account + "-missing"
        );
    }

    private RetryingPaymentClient client(ChargeGateway gateway) {
        RetryTemplate testRetries = RetryTemplate.builder()
                .maxAttempts(3)
                .retryOn(TemporaryGatewayFailure.class)
                .noBackoff()
                .build();
        return new RetryingPaymentClient(gateway, testRetries);
    }

    private PaymentCommand command(long cents) {
        return new PaymentCommand(
                UUID.randomUUID().toString(), account, cents
        );
    }

    private long balance(String accountId) {
        Long found = jdbc.queryForObject(
                """
                SELECT balance_cents
                FROM account_balances
                WHERE account_id = ?
                """,
                Long.class, accountId
        );
        return found.longValue();
    }

    private int markerCount(String key) {
        Integer found = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM payment_inbox
                WHERE idempotency_key = ?
                """,
                Integer.class, key
        );
        return found.intValue();
    }

    @Test
    void successfulFirstAttemptDoesNotRetry() {
        AtomicInteger sends = new AtomicInteger();
        PaymentCommand request = command(250);

        ChargeGateway gateway = cmd -> {
            sends.incrementAndGet();
            return processor.charge(cmd);
        };
        PaymentReceipt receipt =
                client(gateway).charge(request);

        assertThat(receipt.idempotencyKey())
                .isEqualTo(request.idempotencyKey());
        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_250L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void twoTransientFailuresThenSuccessMeanThreeAttempts() {
        AtomicInteger sends = new AtomicInteger();
        List<String> keysSeen = new ArrayList<>();
        PaymentCommand request = command(150);

        ChargeGateway gateway = cmd -> {
            keysSeen.add(cmd.idempotencyKey());
            if (sends.incrementAndGet() <= 2) {
                throw new TemporaryGatewayFailure("simulated 503");
            }
            return processor.charge(cmd);
        };
        PaymentReceipt receipt =
                client(gateway).charge(request);

        assertThat(receipt.amountCents()).isEqualTo(150L);
        assertThat(sends.get()).isEqualTo(3);
        assertThat(keysSeen).containsExactly(
                request.idempotencyKey(),
                request.idempotencyKey(),
                request.idempotencyKey()
        );
        assertThat(balance(account)).isEqualTo(1_150L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void exhaustedRetriesStopAfterExactlyThreeAttempts() {
        AtomicInteger sends = new AtomicInteger();
        PaymentCommand request = command(200);

        ChargeGateway unavailable = cmd -> {
            sends.incrementAndGet();
            throw new TemporaryGatewayFailure(
                    "partner still down"
            );
        };

        assertThatThrownBy(
                () -> client(unavailable).charge(request)
        ).isInstanceOf(TemporaryGatewayFailure.class)
         .hasMessageContaining("partner still down");

        assertThat(sends.get()).isEqualTo(3);
        assertThat(balance(account)).isEqualTo(1_000L);
        assertThat(markerCount(request.idempotencyKey()))
                .isZero();
    }

    @Test
    void nonRetryableValidationErrorIsSentOnlyOnce() {
        AtomicInteger sends = new AtomicInteger();

        ChargeGateway rejected = cmd -> {
            sends.incrementAndGet();
            throw new IllegalArgumentException(
                    "invalid customer data"
            );
        };

        assertThatThrownBy(
                () -> client(rejected).charge(command(100))
        ).isInstanceOf(IllegalArgumentException.class);

        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_000L);
    }

    @Test
    void lostResponseAfterDbCommitDoesNotChargeTwice() {
        AtomicInteger sends = new AtomicInteger();
        List<String> keysSeen = new ArrayList<>();
        PaymentCommand request = command(300);

        ChargeGateway responseMayBeLost = cmd -> {
            keysSeen.add(cmd.idempotencyKey());
            int attempt = sends.incrementAndGet();

            // Upstream already committed, yet client may miss it.
            PaymentReceipt committed = processor.charge(cmd);
            if (attempt == 1) {
                throw new TemporaryGatewayFailure(
                        "response lost after commit"
                );
            }
            return committed;
        };

        PaymentReceipt receipt =
                client(responseMayBeLost).charge(request);

        assertThat(receipt.amountCents()).isEqualTo(300L);
        assertThat(sends.get()).isEqualTo(2);
        assertThat(keysSeen).containsExactly(
                request.idempotencyKey(),
                request.idempotencyKey()
        );
        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void sameKeyWithChangedPayloadIsConflictNotRetry() {
        PaymentCommand first = command(200);
        processor.charge(first);

        AtomicInteger sends = new AtomicInteger();
        ChargeGateway gateway = cmd -> {
            sends.incrementAndGet();
            return processor.charge(cmd);
        };
        PaymentCommand changed = new PaymentCommand(
                first.idempotencyKey(), account, 999L
        );

        assertThatThrownBy(
                () -> client(gateway).charge(changed)
        ).isInstanceOf(IdempotencyConflictException.class)
         .hasMessageContaining("Conflicting idempotency key");

        assertThat(sends.get()).isEqualTo(1);
        assertThat(balance(account)).isEqualTo(1_200L);
        assertThat(markerCount(first.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void distinctKeysWithSameAmountAreTwoRealPayments() {
        PaymentCommand first = command(150);
        PaymentCommand second = command(150);

        RetryingPaymentClient payments =
                client(processor::charge);
        payments.charge(first);
        payments.charge(second);

        assertThat(first.idempotencyKey())
                .isNotEqualTo(second.idempotencyKey());
        assertThat(balance(account)).isEqualTo(1_300L);
        assertThat(markerCount(first.idempotencyKey()))
                .isEqualTo(1);
        assertThat(markerCount(second.idempotencyKey()))
                .isEqualTo(1);
    }

    @Test
    void failedDbMutationRollsBackMarkerSoLaterReplayWorks() {
        String missing = account + "-missing";
        PaymentCommand request = new PaymentCommand(
                UUID.randomUUID().toString(), missing, 700L
        );
        RetryingPaymentClient payments =
                client(processor::charge);

        assertThatThrownBy(
                () -> payments.charge(request)
        ).isInstanceOf(IllegalStateException.class)
         .hasMessageContaining("Unknown account");

        assertThat(markerCount(request.idempotencyKey()))
                .isZero();

        // Fix the business condition, then replay the SAME key.
        jdbc.update(
                """
                INSERT INTO account_balances
                  (account_id, balance_cents)
                VALUES (?, ?)
                """,
                missing, 0L
        );

        PaymentReceipt recovered = payments.charge(request);
        assertThat(recovered.amountCents()).isEqualTo(700L);
        assertThat(balance(missing)).isEqualTo(700L);
        assertThat(markerCount(request.idempotencyKey()))
                .isEqualTo(1);
    }
}
~~~

### Purpose of each test group

- **Success first try**: does not inflate attempt count unnecessarily.
- **Simulated transient 503**: two failures then success → exactly three sends; same key; balance rises only by 150.
- **Exhaustion**: three attempts then exception; zero marker or balance effect.
- **Terminal validation**: no retry; sends equals 1.
- **Lost response after DB commit**: sends equals 2 yet single marker and balance increases by 300, **not 600**.
- **Same key + changed payload**: conflict, no retry; balance from initial attempt remains intact.
- **Different keys, identical amount**: two distinct logical actions, both applied.
- **Business failure rollback**: marker is absent after error; once the account is created, replaying the same key succeeds.

There is no `@Transactional` on the test class: each call to `PaymentWriteTransaction` needs its own real transaction to commit/roll back properly without an outer Spring test-managed transaction distorting semantics. `@BeforeEach` uses a unique account and `@AfterEach` deletes only this test's account/marker rows instead of truncating the whole table.

## 16. `ExponentialBackOffPolicy` and fake sleeper

Spring Retry provides `ExponentialBackOffPolicy.setSleeper(Sleeper)` to swap real wall-clock sleeping for a test-supplied strategy. Assert exact delays and attempt counts **without calling `Thread.sleep()`**.

**`src/test/java/com/example/retrysafety/BackoffPolicyTest.java`:**

~~~java
package com.example.retrysafety;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.support.RetryTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BackoffPolicyTest {

    private RetryTemplate template(
            int maxAttempts,
            ExponentialBackOffPolicy backoff
    ) {
        RetryTemplate retries = RetryTemplate.builder()
                .maxAttempts(maxAttempts)
                .retryOn(TemporaryGatewayFailure.class)
                .build();
        retries.setBackOffPolicy(backoff);
        return retries;
    }

    @Test
    void exponentialBackoffUses100200AndCapped250() {
        List<Long> waits = new ArrayList<>();
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();

        policy.setInitialInterval(100);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(250);
        policy.setSleeper(millis -> {
            waits.add(millis);
        });

        AtomicInteger attempts = new AtomicInteger();
        assertThatThrownBy(() ->
                template(5, policy).execute(context -> {
                    attempts.incrementAndGet();
                    throw new TemporaryGatewayFailure("offline");
                })
        ).isInstanceOf(TemporaryGatewayFailure.class);

        assertThat(attempts.get()).isEqualTo(5);
        assertThat(waits).containsExactly(
                100L, 200L, 250L, 250L
        );
    }

    @Test
    void threeAttemptsProduceExactlyTwoBackoffIntervals() {
        List<Long> waits = new ArrayList<>();
        ExponentialBackOffPolicy policy =
                new ExponentialBackOffPolicy();

        policy.setInitialInterval(50);
        policy.setMultiplier(2.0);
        policy.setMaxInterval(500);
        policy.setSleeper(millis -> {
            waits.add(millis);
        });

        AtomicInteger attempts = new AtomicInteger();
        assertThatThrownBy(() ->
                template(3, policy).execute(context -> {
                    attempts.incrementAndGet();
                    throw new TemporaryGatewayFailure("transient");
                })
        ).isInstanceOf(TemporaryGatewayFailure.class);

        assertThat(attempts.get()).isEqualTo(3);
        assertThat(waits).containsExactly(50L, 100L);
    }
}
~~~

Neither test measures elapsed wall-clock time; both verify the policy calls `Sleeper` with exact intervals and inserts no sleep after the final attempt. When testing jitter, never assert exact random millisecond values: inject deterministic randomness if supported by the API or test upper/lower bounds and probabilistic behavior without creating flaky tests. Real HTTP latency requires a dedicated integration test with appropriate tolerances.

**Total: 10 JUnit methods** across both test classes; eight verify business effects and retry orchestration, and two verify exponential backoff. The sample code has no fixed stdout.

## 17. Illustrative HTTP adapter using `RestClient`

In a real system, the gateway sends the idempotency key to the server via an HTTP header. The snippet below is an **additional illustrative file** outside the default runnable project; using it requires `spring-boot-starter-web`, a configured base URL, proper timeouts, and **replacing** `localChargeGateway` so there are not two candidate beans.

~~~java
package com.example.retrysafety;

import org.springframework.http.HttpHeaders;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestClient;

public final class HttpChargeGateway implements ChargeGateway {
    private final RestClient http;

    public HttpChargeGateway(
            RestClient.Builder builder,
            String baseUrl
    ) {
        this.http = builder.baseUrl(baseUrl).build();
    }

    @Override
    public PaymentReceipt charge(PaymentCommand command) {
        try {
            PaymentReceipt receipt = http.post()
                    .uri("/api/payments")
                    .header("Idempotency-Key",
                            command.idempotencyKey())
                    .header(HttpHeaders.ACCEPT, "application/json")
                    .body(command)
                    .retrieve()
                    .body(PaymentReceipt.class);

            if (receipt == null) {
                throw new IllegalStateException(
                        "Empty payment response"
                );
            }
            return receipt;
        } catch (HttpServerErrorException.ServiceUnavailable
                 | HttpClientErrorException.TooManyRequests e) {
            throw new TemporaryGatewayFailure(
                    "Partner temporary failure", e
            );
        }
    }
}
~~~

This snippet illustrates **503/429 mapping**; it does not map 502/504 or `ResourceAccessException` (read timeout/reset). Add those mappings **only if** the partner API provides a strong server-side idempotency contract. HTTP 400/409 from `retrieve()` remain distinct exceptions, and `RetryTemplate` retries only `TemporaryGatewayFailure`.

Additional HTTP contract tests using WireMock/MockWebServer on an ephemeral port should verify:

- First attempt 503, second attempt 200 → exactly two HTTP requests with the **same `Idempotency-Key` header**.
- HTTP 400 and 409 → one request, zero retries.
- 429 with `Retry-After` → policy stays within server limits and SLOs.
- Timeout after **server commit** → two attempts, yet server ledger applies only one effect.
- Body/status/headers decode properly; not just Mockito verifying method invocation.
- Dynamic baseURL never points to production during test runs.

Because the primary demo uses a scripted Java gateway, it **does not claim** to test real TCP/HTTP/SSL. HTTP tests are an essential extra layer when calling external APIs.

## 18. `@Retryable`, `@Recover`, and AOP self-invocation

Spring Retry also supports annotations:

~~~java
@EnableRetry
@Configuration
class RetryAnnotationsConfiguration {
}
~~~

~~~java
@Service
class AnnotatedPartnerService {
    @Retryable(
            retryFor = TemporaryGatewayFailure.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 100,
                    multiplier = 2.0,
                    maxDelay = 800
            )
    )
    PaymentReceipt charge(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

These two snippets are **skeletons** without imports/gateway definitions and **are not part of the runnable demo**. They require Spring Retry plus AOP proxy infrastructure (e.g., `spring-boot-starter-aop`), `@EnableRetry`, and a Spring-managed bean. `@Retryable.maxAttempts` **includes the initial attempt**; `@Recover` provides a recovery hook after attempts are exhausted when signature and return type match.

**Self-invocation:** a method inside the bean calling `this.charge(...)` normally **bypasses the Spring AOP proxy**, so `@Retryable` does not run. If a test only asserts output, it may still PASS when the method succeeds on the first call. Always test attempt counts and exceptions through the Spring bean proxy. Programmatic `RetryTemplate` in the main project does not rely on proxies for retries.

**Retry transaction boundaries:** Placing `@Transactional` and `@Retryable` on the same method can create subtle interactions between AOP advice ordering and rollback-only state. The clean pattern puts retry orchestration **on the outside**, with each attempt calling a `@Transactional` method on **another bean** so rollback/commit finishes before the next retry starts.

Recovery must never fabricate a “successful” `PaymentReceipt` when it is unknown whether the upstream committed. On ambiguous outcomes, returning PENDING/UNKNOWN and reconciling is far safer than faking success.

## 19. Never retry an entire non-idempotent workflow

Anti-pattern:

~~~java
@Retryable(retryFor = Exception.class, maxAttempts = 3)
public void placeOrder(Order order) {
    reserveInventory(order); // committed on attempt 1
    chargePayment(order);    // response lost
    sendEmail(order);        // may send multiple times
}
~~~

This is a skeleton/anti-pattern, not runnable source. Retrying all of `placeOrder` can repeat `reserveInventory` even when the payment service uses an idempotency key properly.

Safer design:

1. Split each step into a **state transition with an ID/unique contract**.
2. Narrow retry boundaries, e.g., `chargePayment(paymentIdempotencyKey=K)`.
3. Enforce inventory reservation uniqueness per order/line-item/attempt semantics.
4. Pass stable provider keys on external payment calls with reconciliation states.
5. Emit emails/events via a **transactional outbox** rather than sending mid-DB-transaction and hoping emails roll back.
6. Use a saga/workflow state machine across multiple services with explicit compensation rather than re-running from the start.

**No Java retry annotation creates an ACID transaction spanning a database, payment provider, email, and Kafka.**

## 20. Transactional outbox and side effects outside the database

In the demo, `payment_inbox` and the balance update share **one database transaction**. Sending an email or publishing a Kafka event **after** commit can lose the event if the JVM crashes before sending. Sending **before** commit can duplicate it if the DB rolls back and retries.

Transactional outbox:

~~~text
Same DB transaction:
  INSERT payment_inbox K
  UPDATE account_balances
  INSERT outbox(PaymentAccepted event E)
  COMMIT

Relay afterward:
  READ pending outbox E
  PUBLISH E
  MARK sent (may crash after publish)
~~~

The outbox guarantees **publish intent commits atomically with DB state**, yet the relay can still publish twice if it crashes between broker ACK and marking sent. Downstream consumers need their own **idempotent inbox**. Payment providers may offer idempotency-key APIs; read their contract on response replay, concurrent requests, retention, and status queries rather than guessing from header names.

When an external system's response drops after commit, never issue a new payment action with a fresh key just because of a timeout. Instead, **replay the exact same key** if permitted by contract, or query/reconcile by key/transaction ID.

## 21. Messaging, Kafka, and RabbitMQ: redelivery is normal

| Environment | Why retry/redelivery happens | How to prevent duplicate side effects |
| --- | --- | --- |
| HTTP client | 429/503/timeouts/proxy retries | Stable idempotency key + atomic server effect |
| Kafka consumer | Uncommitted offset, rebalance, replay, DLT | Inbox key per consumer/tenant/event + DB transaction |
| RabbitMQ consumer | Lost ACK, NACK/requeue, channel restart | Business-level message ID + inbox/dedup |
| Scheduled worker | Worker crashes after commit before updating job status | Unique job/operation ID and reconciliation |
| Outbox relay | Publish succeeds yet mark-sent fails | Downstream consumer idempotency |
| Payment provider | Client missed response after server charged | Provider-side idempotency key/transaction lookup |

Kafka exactly-once semantics within a supported Kafka topology **do not protect** emails, external APIs, or external databases outside the Kafka transaction. Spring Kafka blocking retry, non-blocking retry, and DLT have version-specific constraints regarding record ordering and transactions. Never stack multiple retry layers assuming “total attempts is still three”.

When replaying a DLT, **preserve the logical event ID/idempotency key**; assigning a new key tricks consumers into treating an old event as a brand-new action. Pruning marker rows before the replay window closes likewise lets old events apply a second time.

## 22. Concurrency and in-flight keys

A table primary key blocks two transactions from committing the same marker, yet two concurrent requests with the same key can race:

~~~text
A: BEGIN -> INSERT K -> UPDATE account
B: BEGIN -> INSERT K -> waits on unique index/lock
A: COMMIT
B: duplicate key -> ROLLBACK -> read K -> no-op
~~~

If A rolls back, B can proceed as the first successful attempt. Concurrency tests need a real DB backend, `CountDownLatch`/`CyclicBarrier` to force interleaving, and bounded timeouts—never guessing with `Thread.sleep`.

**H2 limitation:** it demonstrates atomic unique constraints and rollbacks, yet cannot substitute for PostgreSQL/MySQL Testcontainers when testing lock waits, deadlocks, isolation levels, or error translation under load. In production, if a duplicate arrives while the first is still **IN_PROGRESS** (uncommitted), the server needs a pending-result policy, per-key coordination, and conflict semantics; querying only committed markers does not cover every case.

`synchronized` or an in-memory Cache Map works only inside one JVM, vanishes on restart, and cannot coordinate across three Kubernetes pods. A **DB unique constraint** is far more durable, provided tenant scope and transaction semantics are right.

## 23. Retry deadlines, cancellation, and unknown outcomes

A client timeout does not mean the previous attempt stopped running. `Future.get(2, TimeUnit.SECONDS)` can time out while the worker/network request continues running; if the client immediately fires a new attempt, **two requests with the same key can run concurrently in-flight**.

Required safeguards:

- Per-attempt connect and read timeouts.
- Overall deadline or retry budget.
- Proper cancellation/interrupt propagation.
- Skip new retries if insufficient remaining time exists.
- Avoid retry storms under overload; cap concurrency and pair with circuit breakers.
- On unknown outcomes, record `PENDING/UNKNOWN` and reconcile using stable transaction IDs.
- Never hold DB transactions open across backoff/network waits.
- Never swallow all exceptions and return business success.

When an HTTP timeout occurs **after commit**, server-side deduplication makes retries safe. If a provider lacks an idempotency API or status query, the right policy may be **not auto-retrying POST**, creating a reconciliation workflow or manual review instead.

## 24. Jitter and thundering herd

When many clients experience the same outage, deterministic backoff like `100, 200, 400 ms` makes thousands of clients retry in lockstep. Jitter spreads attempts out, dampening thundering herds.

Common strategies:

- Fixed backoff: simple, prone to synchronization.
- Capped exponential: eases hammering, requires a max interval.
- Exponential with randomness: spreads load across many clients.
- Server-directed delay: `Retry-After`, bounded by deadline.
- Retry token budget: caps total retry traffic.
- Delayed queue/topic: for async jobs so listener threads stay unblocked.

Spring Retry `exponentialBackoff(..., true)` uses an exponential random policy per the 2.x API. **Do not assume it matches every “full jitter” or “equal jitter” formula** described elsewhere without checking the exact API/version. Test deterministic exponential backoff with a fake sleeper, and test jitter using bounds, cancellation, or a controlled randomness source if the framework exposes one. Never assert exact fixed millisecond waits on randomized policies.

## 25. Failure injection needed in CI

The demo's ten tests focus on business invariants, while production warrants a deeper matrix:

| Failure window | Invariant to prove |
| --- | --- |
| Before reaching server | Transient errors retry without unintended effects |
| After INSERT marker, before balance UPDATE | Marker rolls back; replay succeeds |
| After UPDATE, before COMMIT | Both marker and effect roll back |
| **After COMMIT, before HTTP response** | Retry with same key causes zero double effect |
| Two identical keys in concurrent transactions | At most one effect commits |
| Two distinct keys on the same account | Both effects commit without lost updates |
| Same key + changed payload | Conflict; never silently skipped |
| 503 first, then 200 | Exact attempt count; unchanged key/headers |
| 429 + `Retry-After` | Retry timing honors contract and deadline |
| 400/401/403/409 | Zero pointless retries |
| HTTP SDK with internal retries | Total physical sends stay within budget |
| Outbox publish then crash before mark-sent | Downstream deduplicates |
| DLT replay days later | Marker retention spans full replay window |
| Provider timeout while attempt is in-flight | No duplicate effect when subsequent attempt lands |
| Multi-worker CI and multiple pods | Tenant/test-scoped data, safe cleanup |

An HTTP test that only checks `Mockito.verify(gateway, times(2))` **is insufficient**. Assert the database ledger/business state, unique marker count, and receipts—especially for lost responses. Process-kill and real network fault injection need Testcontainers, embedded servers, or a dedicated chaos harness.

## 26. Observability: counting attempts vs. applied effects

A single logical payment sent twice after a lost response might emit metrics like:

~~~text
logical operations         = 1
HTTP attempts              = 2
client retries             = 1
server requests received   = 2
idempotency duplicate noops= 1
business effects applied   = 1
~~~

This is a scenario-based calculation, not captured stdout. If `business effects applied` becomes 2, the idempotency contract broke even if the client ultimately received a valid receipt.

Track retry rates, error categories (503/429/timeout/conflict), exhausted attempts, backoff histograms, p95/p99 latency, active requests, DB unique conflicts, idempotency duplicates, pending outbox counts, and reconciliation queues. Log correlation IDs, stable keys (redacted/hashed if sensitive), attempt indices, and remaining deadlines. Never log card data, raw credentials, or PII on every retry.

**Do not assume rising duplicate counts are always bugs:** after outages or rebalances, valid redeliveries naturally rise. However, same-key **payload conflicts** usually warrant alerts for producer bugs or improper key reuse.

## 27. Common mistakes when designing retries

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reading `maxAttempts=3` as 4 calls | Exceeds budget | Remember the initial attempt is inside the 3 |
| Retrying every `Exception` | Resends 400s/conflicts | Narrowly classify transient errors |
| Retrying mutating POST without dedup | Double charges/duplicate orders | Stable keys + server unique constraints/transactions |
| Generating UUID inside retry callback | Each attempt becomes a new action | Generate key once before retry loop |
| Marker commits before business mutation | Failure + retry skips action | Keep in the same transaction |
| Catching unique violation inside PostgreSQL tx | Transaction enters aborted state | Catch outside transactional proxy |
| Treating same-key changed payload as no-op | Drops legitimate transaction or hides bug | Compare canonical payload and conflict |
| Checking only exception/no exception | Unaware of duplicated DB effects | Assert ledger and markers |
| No backoff/jitter at high QPS | Retry storm | Capped exponential + jitter/budget |
| Infinite backoff sleep on HTTP threads | Thread pool exhaustion | Deadlines, async/queues/bulkheads |
| Ignoring `Retry-After` header | Exceeds rate limits | Parse header and honor budget |
| 3 stacked retry layers multiplying | Far more sends than intended | Audit the full dependency chain |
| Tests using `Thread.sleep` | Slow and flaky | Fake sleeper or `noBackoff` |
| `@Transactional` wrapping processor in tests | Distorts transaction boundaries | Test real commits/rollbacks |
| `@Retryable` self-invocation | Retries silently skipped | Call via Spring bean proxy or `RetryTemplate` |
| `@Transactional` self-invocation | Marker and effect not atomic | Separate beans |
| Treating H2 tests as proof for PostgreSQL | Misses lock/deadlock differences | PostgreSQL Testcontainers |
| External email/Kafka inside/around DB tx | Duplicate or lost events | Outbox + downstream dedup |
| Assuming timeout means server did not commit | Creates duplicate action | Reconcile with the same key |
| Changing event ID during DLT replay | Consumer re-applies effect | Preserve logical event ID |
| Idempotency marker TTL too short | Late replays re-apply effects | Match retention to business contract |
| Returning fake success when retries exhaust | Masks uncertain outcomes | Return error/PENDING and reconcile |
| Using `@Primary` to mask dual gateway beans | Unclear which adapter runs | Register one gateway per profile/qualifier |

## 28. Pre-finalization QA checklist for resilience tests

- [ ] Clearly defined the **logical business action** and stable idempotency key?
- [ ] Distinguished replaying the same event/key from two legitimate actions with identical payloads?
- [ ] Classified transient vs. permanent vs. ambiguous outcomes?
- [ ] Bounded `maxAttempts` and verified both initial attempt and retry counts?
- [ ] Configured backoff with initial/multiplier/max, plus jitter for multi-client setups?
- [ ] Set per-attempt timeouts, overall deadlines, and retry budgets?
- [ ] Audited all nested retries across SDKs, proxies, and consumers?
- [ ] Ensured mutating POSTs auto-retry only when server/provider guarantees idempotency?
- [ ] Enforced server-side uniqueness in the **database** at the proper scope?
- [ ] Committed/rolled back marker and business effect within the same transaction?
- [ ] Verified same key + changed payload triggers conflict/alerts?
- [ ] Verified existing same key + same payload returns old receipt/no-op?
- [ ] Verified pre-commit failures leave no dangling marker?
- [ ] Tested **commit followed by lost response** and confirmed balance does not double?
- [ ] Verified two distinct keys apply independently even with identical amounts?
- [ ] Tested that permanent 400/validation/conflict errors do not retry?
- [ ] Tested retry exhaustion and exact send counts?
- [ ] Verified delays with a fake sleeper without wall-clock sleeping?
- [ ] Honored server `Retry-After` within remaining deadline where applicable?
- [ ] Built reconciliation/status queries for uncertain retry states?
- [ ] Verified `@Transactional` and `@Retryable` are not bypassed by self-invocation?
- [ ] Protected non-DB side effects with outboxes, provider keys, or compensation?
- [ ] Preserved logical IDs and sufficient marker retention for Kafka/Rabbit replays?
- [ ] Added separate concurrency stress/fault tests against the production DB engine?
- [ ] Confirmed tests never hit production/staging payment endpoints?
- [ ] Separated metrics for logical operations, physical attempts, and applied effects?
- [ ] Explicitly marked unexecuted build outcomes as expected rather than claiming PASS?

## 29. Run commands, expected results, and limitations

With JDK 17+, Gradle Wrapper, and dependencies:

~~~bash
./gradlew test --tests "com.example.retrysafety.RetryingPaymentClientTest"
./gradlew test --tests "com.example.retrysafety.BackoffPolicyTest"
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.retrysafety.RetryingPaymentClientTest"
.\gradlew.bat test --tests "com.example.retrysafety.BackoffPolicyTest"
.\gradlew.bat test
~~~

**Ten JUnit methods** comprise eight Spring/JDBC integration tests and two backoff unit tests. Expected outcomes:

| Test | Expectation |
| --- | --- |
| `successfulFirstAttemptDoesNotRetry` | 1 send, balance 1250, marker 1 |
| `twoTransientFailuresThenSuccessMeanThreeAttempts` | 3 sends, same key, balance 1150 |
| `exhaustedRetriesStopAfterExactlyThreeAttempts` | 3 sends then transient exception, balance 1000 |
| `nonRetryableValidationErrorIsSentOnlyOnce` | 1 send, zero business effect |
| `lostResponseAfterDbCommitDoesNotChargeTwice` | 2 sends, yet balance only 1300, marker 1 |
| `sameKeyWithChangedPayloadIsConflictNotRetry` | Conflict, no retry, balance 1200 |
| `distinctKeysWithSameAmountAreTwoRealPayments` | Two keys, balance 1300 |
| `failedDbMutationRollsBackMarkerSoLaterReplayWorks` | First run rolls back marker, replay succeeds to 700 |
| `exponentialBackoffUses100200AndCapped250` | 5 attempts; waits [100,200,250,250] |
| `threeAttemptsProduceExactlyTwoBackoffIntervals` | 3 attempts; waits [50,100] |

**These are expected outcomes derived from the code, not observed Gradle/JUnit/H2 output.** APIs and semantics were checked against documentation, though the suite was not compiled or executed during authoring. The demo calls no `System.out.println`, so there is no fixed stdout.

**Conclusion:** Retries must be **bounded, strictly classified by error type, and governed by backoff/jitter and deadlines**; yet preventing duplicate business execution also requires a **stable idempotency key + atomic server-side business transaction**. The highest-risk scenario is **server commits, client misses the response**: replaying with the **same key** must return the previous receipt without repeating the side effect. Across multiple systems beyond one DB, extend with outboxes, provider idempotency, and reconciliation—never claim exactly-once from a retry annotation alone.

### Official references

- [RFC 9110 — HTTP semantics, idempotence and Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html)
- [Spring Retry 2.x — RetryTemplateBuilder Javadoc](https://docs.spring.io/spring-retry/docs/2.0.x/apidocs/spring.retry/org/springframework/retry/support/RetryTemplateBuilder.html)
- [Spring Retry 2.x — ExponentialBackOffPolicy, Sleeper](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/backoff/ExponentialBackOffPolicy.html)
- [Spring Retry 2.x — @Retryable maxAttempts](https://docs.spring.io/spring-retry/docs/current/apidocs/spring.retry/org/springframework/retry/annotation/Retryable.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
