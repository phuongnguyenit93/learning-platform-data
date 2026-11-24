# Testing Behavior When a Database, Broker, or External Service Is Temporarily Unavailable

> **Module:** Spring Boot – testing  
> **Group:** Contracts and Resilience  
> **Topic:** Testing behavior when a database, broker, or external service is temporarily unavailable  
> **Goal:** Create and verify controlled failure modes for JDBC/databases, AMQP brokers, and downstream HTTP services; distinguish transient errors, permanent errors, and uncertain outcomes; verify timeouts, retries, transactions, outboxes, broker confirms, idempotency, and post-outage recovery. Examples use Java 17, Spring Boot 3.5.0, Maven/JUnit 5, Mockito, PostgreSQL and RabbitMQ Testcontainers, plus a JDK 17 stub HTTP server.

## 1. “Temporary outage” is not a single failure mode

A single application request may touch three dependencies:

```text
Client
  │
  ▼
CheckoutWorkflow
  ├── HTTP partner: external decision / information check
  │        └── timeout, 429, 503, connection reset, 400
  ├── PostgreSQL: write request + outbox in one transaction
  │        └── lost connection, lock timeout, deadlock, read-only, schema error
  └── RabbitMQ: publish outbox message
           └── broker offline, publish timeout, unroutable, publisher NACK

          Outcomes must be explicit:
  • REJECTED                       → business decline
  • UPSTREAM_UNAVAILABLE           → no durable changes yet
  • DATABASE_UNAVAILABLE           → no message published
  • PENDING_DELIVERY               → saved in outbox, will replay later
  • BROKER_CONFIRMED               → broker ACKed publication, not yet consumer-processed
```

**The goal of resilience testing is not to prove “everything still succeeds when dependencies die”.** Often the right contract is to *fail fast*, return a retryable status, persist work durably, or avoid invalid side effects.

### 1.1. Contracts to define before writing tests

1. **No lost data:** Once reported as accepted, what data must be durably persisted?
2. **No bogus side effects:** If the HTTP partner fails to answer, may an order be saved or an event emitted?
3. **No duplicate business actions:** If the HTTP client retries after a timeout, does the same idempotency key create two orders?
4. **Bounded latency:** When a dependency hangs, requests must terminate within a finite deadline.
5. **Failure isolation:** A dead broker must not lose committed records; a dead database must not emit phantom events.
6. **Recovery:** Once the dependency recovers, does a retry/replay drain the backlog cleanly?
7. **Observability:** Metrics/logs/traces separate 503, timeouts, connection refused, retry exhaustion, and pending outbox items.
8. **Safety:** Tests never shut down shared databases/brokers or corrupt other CI jobs' data.

### 1.2. Error classification: differing retryability

| Symptom | Typical category | Suggested policy | Caution |
| --- | --- | --- | --- |
| HTTP 200 + `APPROVED` | Success | Proceed | Validate body/schema |
| HTTP 400/401/403 | Usually permanent/auth | Do not retry blindly | Do not turn 401 into 503 |
| HTTP 404 | Resource may not exist | Per domain contract | Do not cache “not found” forever |
| HTTP 408/429 | Usually transient | Bounded retry, honor `Retry-After` if present | Do not create a retry storm |
| HTTP 500/502/503/504 | Usually transient | Timeouts + backoff/jitter/circuit breaker as appropriate | Server may already have executed POST |
| TCP refused/reset | Transport | Bounded retry for safe operations | Wrong endpoints produce similar errors |
| HTTP read timeout | **Uncertain** outcome | Idempotency key + reconciliation | Server may already have processed it |
| JDBC connection unavailable | Infrastructure | Fail fast or safely retry transaction | Never assume the prior transaction rolled back |
| SQL deadlock/serialization | Transaction retryable | Bounded retry of full unit of work | Must be idempotent |
| Unique violation/bad SQL | Usually logic/input error | Skip transient retry policy | Do not catch all `DataAccessException`s |
| RabbitMQ connection refused | Broker unavailable | Keep outbox `PENDING` | Never mark `DELIVERED` |
| AMQP unroutable key | Topology/contract error | Publisher return, fix routing | Confirm ACK may still arrive |
| Broker publisher confirm timeout | Uncertain outcome | Keep outbox, idempotent replay | Broker may have received the message |
| Consumer processes then crashes before ACK | Redelivery | Idempotent consumer | No automatic exactly-once |

**Key idea:** “retryable” is an *operation-level* decision, not a blanket label for every HTTP 5xx or SQL exception. Read-only GETs are far safer to retry than a mutating POST without an idempotency key.

## 2. Test layers and what each proves

| Layer | Tooling | Verifies well | Does not prove |
| --- | --- | --- | --- |
| Unit/business | JUnit + Mockito gateways | States, error branches, zero side effects | Real network/protocol |
| HTTP adapter | Local `HttpServer`/WireMock/MockWebServer | 200/400/503/read timeouts/bad bodies | Production DNS/TLS/proxy |
| Database integration | PostgreSQL Testcontainers | Transactions, constraints, rollbacks, SQL | Multi-node HA failover |
| Broker integration | RabbitMQ Testcontainers | Exchanges/bindings, confirms/returns, routing | Consumer commits if no consumer runs |
| Network fault | Toxiproxy between JVM and container | Latency, connection cuts, recovery | Full cluster quorum/election |
| Full system | Production-like staging topology | Node loss, retry storms, alerting, failover | All future failures |
| Contract tests | Provider/consumer schema & status policies | Valid messages/statuses/bodies | Dependency availability |

A Mockito test can confirm “if the publisher throws, outbox stays PENDING”, yet **does not prove the broker truly disconnected**. A RabbitMQ container test verifies real confirms/returns, yet does not verify network-partition recovery without injecting network faults.

### 2.1. Never confuse negative tests with missing infrastructure

If CI lacks a Docker daemon, a setup failure is not “database outage handled PASS”. If `@RabbitAvailable` skips due to a missing broker, a mandatory integration suite must not report green. Fault injection must happen **after the test environment is healthy**, and tests should verify the fault actually took effect.

### 2.2. Healthy baseline before fault

A proper resilience test follows this sequence:

```text
[1] Start test-only provider → HEALTHY
[2] Run baseline and verify success
[3] Inject fault (HTTP 503 / TCP cut / latency)
[4] Confirm fault genuinely hits the target client
[5] Run the same workflow and assert failure contract
[6] Remove fault / restore provider
[7] Replay/retry with idempotency and bounded deadline
[8] Verify data/messages are accurate with zero duplicates
[9] Clean up test-owned resources without touching other systems
```

Never just stop a container, see an exception, and declare the system resilient. The critical part is **post-failure invariants** and **recovery**.

## 3. Business design: transactional outbox before broker publish

A dangerous flow:

```text
BEGIN TRANSACTION
INSERT order
rabbitTemplate.convertAndSend(...)
COMMIT DB
```

If the DB rolls back after the broker accepted the event, consumers see “order created” for a nonexistent order. If the DB commits and the broker goes offline, the event is lost. A DB transaction and a RabbitMQ ACK are **not an atomic distributed transaction** by default.

**Safer pattern for many workflows:** Inside **one DB transaction**, insert the business record + a `PENDING` outbox row. After commit, a dispatcher publishes the event to the broker. Only upon receiving publisher confirm ACK **and no mandatory return** is the outbox marked sent. On failure or timeout, leave it `PENDING` for replay.

```text
HTTP partner result
       |
       v
DB transaction:
    INSERT placed_order
    INSERT outbox_event (PENDING)
       |
     COMMIT
       |
       v
Outbox publisher
       ├── broker confirmed + routable → mark SENT
       └── fail/timeout/uncertain      → keep PENDING
                                              |
                                        retry/replay later
```

**Important:** An outbox reduces event loss yet **does not guarantee exactly-once delivery**. If the broker receives the event and the app crashes before marking `SENT`, replay emits a duplicate. Consumers need idempotency keys, dedup inboxes, or unique business constraints.

### 3.1. Distinguishing “broker confirmed” from “consumer processed”

- `RabbitTemplate.convertAndSend` does not throw: the Java send API succeeded asynchronously—**insufficient**.
- Publisher confirm ACK: the RabbitMQ broker acknowledged receipt under the confirm protocol.
- Mandatory return: the message could not route to any queue; this can arrive **alongside** a confirm ACK.
- Message in queue: routed to a test destination; does not mean a consumer processed it.
- Consumer ACK: broker logged delivery acknowledgement; does not prove downstream DB commit unless guaranteed by design.
- Business effect: querying DB/HTTP state provides independent proof.

Spring AMQP exposes `CorrelationData.getFuture()` and `CorrelationData.getReturned()` when confirms and returns are enabled. The sample checks both before marking an outbox row `SENT`.

## 4. PostgreSQL/database outages: what to test?

### 4.1. Separating “unreachable” from “bad SQL”

`DataAccessResourceFailureException`, `CannotGetJdbcConnectionException`, or specific `TransientDataAccessException` subclasses can signal temporary infrastructure outages. `BadSqlGrammarException`, `DuplicateKeyException`, and validation errors should normally **not** be retried blindly.

Services should catch **specific** transient exception groups allowed by policy, letting other errors surface to monitoring and developers. A blanket `catch (DataAccessException ex) { return 503; }` can hide broken migrations that should fail CI.

### 4.2. Transaction rollback across multiple tables

If inserting into `placed_orders` succeeds yet inserting into `outbox_events` fails, the entire unit of work must roll back. Verify this against real PostgreSQL: deliberately trigger a unique-key collision in the outbox, call `savePending` through the Spring transactional bean, and assert `placed_orders` contains no row for that request.

**Do not** merely verify repository `save` was invoked twice. Query the database after the failure to prove real transaction behavior.

### 4.3. Connection loss mid-transaction: outcomes can be uncertain

If TCP drops while the client awaits `COMMIT`, the server may have committed while the client never received the reply. Retrying a non-idempotent `INSERT` can duplicate data or hit a unique conflict. Prevent this via client-generated request IDs, unique constraints, idempotent upserts/lookups, and reconciliation.

Tests should explicitly model “commit outcome unknown” where required by business logic; never assume an exception guarantees rollback.

### 4.4. Connection pools and recovery

HikariCP enforces acquisition timeouts, connection validation, minimum idle counts, and pool health. When Postgres is offline, new acquisitions must fail within bounded time; when the DB returns, the pool must recreate/revalidate connections properly. In fault-injection tests, cached idle connections can mask a network cut for a couple of calls.

Never mock `JdbcTemplate` and call it a network failover test; mocks test control flow only. Never stop a shared PostgreSQL container across parallel test classes or force `stop/start` assuming mapped host ports stay identical.

## 5. Broker outages: timeouts, confirms, and outbox

### 5.1. Why not just assert `convertAndSend` didn't throw?

AMQP publishing is asynchronous. With no matching queue binding, messages can be silently dropped unless mandatory returns are enabled; if the exchange does not exist, the channel closes asynchronously.

To test properly:

```properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
```

Then publish with `CorrelationData` and await a bounded publisher confirm; if `getReturned() != null`, **never mark `SENT`**, even when `confirm.isAck()` is true.

### 5.2. Confirm timeouts mean “unknown”, not “unsent”

An expired publisher confirm future may stem from an unreachable broker, network jitter, delayed callbacks, or an ACK lost after broker persistence. Leave the outbox `PENDING` and replay with the same event ID. Consumers use an inbox/unique constraint to prevent duplicate side effects.

### 5.3. When the broker returns

A valuable test confirms:

1. An outbox row stays `PENDING` after the fault.
2. While the broker is “offline” (real or fault seam), it is never marked `SENT`.
3. After recovery, the dispatcher reads pending rows and publishes.
4. Messages land in the expected queue/exchange with confirms received.
5. Outbox flips to `SENT`.
6. Running replay again does not re-send already-sent items.
7. If a crash causes redelivery, consumers handle duplicates idempotently.

Testing real broker outages requires Toxiproxy; a unit test throwing from `BrokerGateway` guards only the business branch (section 10).

## 6. Downstream HTTP outages: 503, timeouts, 4xx, and fallbacks

### 6.1. Test policy

For an HTTP GET decision check:

- `200 APPROVED`: continue workflow.
- `200 DECLINED`: business decline, create no pending order.
- `503`: dependency temporarily unavailable, write no DB row or event.
- `400`: invalid request/contract error; **never** return a retryable status like 503.
- Read timeout: uncertain outcome; read-only GETs may retry within a bounded policy if allowed by contract.
- Body other than `APPROVED`/`DECLINED`: contract error, never silently treat as approved.
- 429/408: may retry per quota/`Retry-After`/policy within budget.
- Mutating POST: timeouts can happen **after** server execution, requiring idempotency keys and reconciliation.

### 6.2. Distinguishing timeout settings

- **Connect timeout:** TCP handshake bound; does not cover all DNS/TLS/proxy edge cases.
- **Read/response timeout:** bound waiting for network response/data; may not span the full deadline across multiple chunks.
- **Total deadline:** end-to-end budget covering connection, backoff, attempts, queueing, and processing.
- **Retry delay/backoff:** adds latency and must fit inside the total deadline.
- **Bulkhead:** limits concurrent requests and threads/blocking connections.
- **Circuit breaker:** pauses repeated calls to a failing provider; test thresholds and reset rules.

Setting timeouts is a **business decision**. Never shrink timeouts absurdly just to pass tests; tests may use shorter values than production while preserving realistic semantics.

## 7. Hands-on project: Java 17 + Spring Boot 3.5

The project illustrates **three gateways**: `PartnerGateway` (HTTP), `OrderStore` (JDBC/Postgres), and `BrokerGateway` (RabbitMQ). The workflow yields clear outcomes when each dependency fails. It writes DB + outbox atomically, then publishes to RabbitMQ with confirms/returns. A dispatcher replays `PENDING` items once the broker recovers.

There are **14 JUnit `@Test` methods**:

- 6 unit tests verifying workflow branches and zero-side-effect assertions.
- 4 HTTP adapter tests using JDK `HttpServer` returning 200/400/503 and slow responses causing real read timeouts.
- 4 Postgres/RabbitMQ integration tests: happy path, broker-fault seam → real recovery, unroutable returns, and atomic DB rollback.

**Scope:** The broker-fault seam tests policy when publishing throws; the return test uses real RabbitMQ. Real TCP cuts to **Postgres/RabbitMQ** are detailed in the Toxiproxy extension section rather than claiming full physical outage coverage within these 14 tests.

### 7.1. Directory tree

```text
resilience-test-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/resilience/
    │   │   ├── ResilienceApplication.java
    │   │   ├── Ports.java
    │   │   ├── GatewayFailures.java
    │   │   ├── WorkflowService.java
    │   │   ├── JdbcOrderStore.java
    │   │   ├── HttpPartnerGateway.java
    │   │   ├── RabbitTopology.java
    │   │   ├── RabbitConfirmedPublisher.java
    │   │   └── OutboxDispatcher.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/resilience/
        ├── WorkflowServiceUnitTest.java
        ├── HttpPartnerGatewayTest.java
        └── OutageIntegrationTest.java
```

All Java files use package `com.example.resilience`. `Ports.java` and `GatewayFailures.java` declare package-private types without public top-level types, allowing multiple types in one file.

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>resilience-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>rabbitmq</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot 3.5 parent manages compatible Spring Framework, Spring AMQP, and Testcontainers versions. With Testcontainers 1.x managed by Boot 3.5, `org.testcontainers.containers.PostgreSQLContainer` and `org.testcontainers.containers.RabbitMQContainer` imports apply. **Do not mix Testcontainers 2.x imports/artifacts without upgrading the BOM consistently.**

### 7.3. `application.properties`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always

spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true

# Default address is just a safe lab placeholder.
# Outside tests, configure a real URL and test-only credentials.
app.partner.base-url=http://127.0.0.1:9
```

By default Spring Boot runs `schema.sql` only on embedded databases; `spring.sql.init.mode=always` runs it on the PostgreSQL container too. Real projects should use Flyway/Liquibase with migration policies rather than auto-running `schema.sql` on production DBs. Port 9 is a local placeholder with no real downstream; HTTP unit tests supply dynamic URLs and full integration mocks `PartnerGateway`.

### 7.4. `schema.sql`

```sql
-- src/main/resources/schema.sql
CREATE TABLE placed_orders (
    order_id VARCHAR(64) PRIMARY KEY
);

CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    payload VARCHAR(255) NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE
);
```

Both tables enforce unique primary keys on order/event IDs. This forms the basis for **idempotency**, though the sample does not implement full idempotent request replay: calling `savePending` with a duplicate ID raises a constraint error. Production must handle duplicate requests via lookup/payload-comparison/validated upserts and safe “already processed” states.

### 7.5. `ResilienceApplication.java`

```java
// src/main/java/com/example/resilience/ResilienceApplication.java
package com.example.resilience;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResilienceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResilienceApplication.class, args);
    }
}
```

### 7.6. `Ports.java` and workflow outcomes

```java
// src/main/java/com/example/resilience/Ports.java
package com.example.resilience;

import java.util.List;

interface PartnerGateway {
    boolean approved(String orderId);
}

interface OrderStore {
    void savePending(String orderId);
    void markSent(String orderId);
    boolean isPending(String orderId);
    List<String> pendingIds();
}

interface BrokerGateway {
    void publishConfirmed(String orderId);
}

enum Outcome {
    BROKER_CONFIRMED,
    PENDING_DELIVERY,
    UPSTREAM_UNAVAILABLE,
    DATABASE_UNAVAILABLE,
    DECLINED
}
```

Interface seams let Mockito inject failures at exact boundaries during unit tests, while production adapters use real HTTP/JDBC/RabbitMQ. `BROKER_CONFIRMED` is deliberately **not named `DELIVERED` or `CONSUMED`** because the tests include no business event consumer.

### 7.7. `GatewayFailures.java`

```java
// src/main/java/com/example/resilience/GatewayFailures.java
package com.example.resilience;

class PartnerUnavailableException extends RuntimeException {
    PartnerUnavailableException(String message) {
        super(message);
    }

    PartnerUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

class BrokerUnavailableException extends RuntimeException {
    BrokerUnavailableException(String message) {
        super(message);
    }

    BrokerUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

These are **application exceptions**, not built-in Spring exceptions. Their adapters define their semantics: temporary partner failures or uncertain broker publish routing. An HTTP 400 from the partner is classified by the adapter as a permanent client error rather than throwing `PartnerUnavailableException`.

### 7.8. `WorkflowService.java`

```java
// src/main/java/com/example/resilience/WorkflowService.java
package com.example.resilience;

import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class WorkflowService {

    private final PartnerGateway partner;
    private final OrderStore store;
    private final BrokerGateway broker;

    public WorkflowService(
            PartnerGateway partner,
            OrderStore store,
            BrokerGateway broker) {
        this.partner = partner;
        this.store = store;
        this.broker = broker;
    }

    public Outcome submit(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        final boolean approved;
        try {
            approved = partner.approved(orderId);
        }
        catch (PartnerUnavailableException ex) {
            return Outcome.UPSTREAM_UNAVAILABLE;
        }

        if (!approved) {
            return Outcome.DECLINED;
        }

        try {
            store.savePending(orderId);
        }
        catch (TransientDataAccessException
                | DataAccessResourceFailureException ex) {
            return Outcome.DATABASE_UNAVAILABLE;
        }

        try {
            broker.publishConfirmed(orderId);
        }
        catch (BrokerUnavailableException ex) {
            return Outcome.PENDING_DELIVERY;
        }

        try {
            store.markSent(orderId);
        }
        catch (TransientDataAccessException
                | DataAccessResourceFailureException ex) {
            // Broker ACK received, yet DB mark SENT is uncertain.
            // Replay may re-send: consumers must be idempotent.
            return Outcome.PENDING_DELIVERY;
        }

        return Outcome.BROKER_CONFIRMED;
    }
}
```

Key takeaways:

- **HTTP fails before DB:** never calls store/broker, avoiding meaningless pending outbox rows.
- **Database fails:** skips broker publish, preventing events for unsaved orders.
- **Broker fails / confirm uncertain:** DB has saved `PENDING` outbox for later replay.
- **Mark `SENT` fails:** broker confirmed publication, yet DB metadata update is uncertain. Conservatively returns `PENDING_DELIVERY`; replay requires idempotent consumers.
- **Non-transient SQL errors:** errors such as `DuplicateKeyException` are not caught so they surface to tests/monitoring instead of turning bugs into 503.
- **Transaction boundary:** this method does not wrap the entire workflow in `@Transactional`. The transaction sits inside `OrderStore.savePending` so DB commit completes **before** publishing to the broker.

Production workflows need error response mapping, idempotency, request budgets, cancellation, metrics, and often a dedicated durable dispatcher. This sample isolates the core invariant without claiming to be a complete payments implementation.

### 7.9. `JdbcOrderStore.java`

```java
// src/main/java/com/example/resilience/JdbcOrderStore.java
package com.example.resilience;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class JdbcOrderStore implements OrderStore {

    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public void savePending(String orderId) {
        jdbc.update(
                "INSERT INTO placed_orders(order_id) VALUES (?)",
                orderId);

        jdbc.update(
                "INSERT INTO outbox_events(event_id, payload, sent) "
                        + "VALUES (?, ?, FALSE)",
                orderId,
                "ORDER:" + orderId);
    }

    @Override
    public void markSent(String orderId) {
        int changed = jdbc.update(
                "UPDATE outbox_events SET sent = TRUE "
                        + "WHERE event_id = ?",
                orderId);

        if (changed != 1) {
            throw new IllegalStateException(
                    "Missing outbox for " + orderId);
        }
    }

    @Override
    public boolean isPending(String orderId) {
        Boolean sent = jdbc.queryForObject(
                "SELECT sent FROM outbox_events "
                        + "WHERE event_id = ?",
                Boolean.class,
                orderId);

        return Boolean.FALSE.equals(sent);
    }

    @Override
    public List<String> pendingIds() {
        return jdbc.queryForList(
                "SELECT event_id FROM outbox_events "
                        + "WHERE sent = FALSE ORDER BY event_id",
                String.class);
    }
}
```

`@Transactional` applies because the workflow invokes `store.savePending` across a separate Spring bean proxy. Self-invocation via `this.savePending()` inside the same bean bypasses transaction advice.

Ensure both `INSERT`s share the **same DataSource and transaction manager**. The rollback test in section 10 verifies real behavior on PostgreSQL.

### 7.10. `HttpPartnerGateway.java`

```java
// src/main/java/com/example/resilience/HttpPartnerGateway.java
package com.example.resilience;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

@Component
public class HttpPartnerGateway implements PartnerGateway {

    private final RestClient client;

    public HttpPartnerGateway(
            RestClient.Builder builder,
            @Value("${app.partner.base-url}") String baseUrl) {

        SimpleClientHttpRequestFactory requests =
                new SimpleClientHttpRequestFactory();
        requests.setConnectTimeout(Duration.ofMillis(200));
        requests.setReadTimeout(Duration.ofMillis(250));

        this.client = builder
                .baseUrl(baseUrl)
                .requestFactory(requests)
                .build();
    }

    @Override
    public boolean approved(String orderId) {
        try {
            String value = client.get()
                    .uri("/decision/{id}", orderId)
                    .retrieve()
                    .body(String.class);

            if ("APPROVED".equals(value)) {
                return true;
            }
            if ("DECLINED".equals(value)) {
                return false;
            }
            throw new IllegalStateException(
                    "Unexpected partner response");
        }
        catch (HttpServerErrorException ex) {
            throw new PartnerUnavailableException(
                    "Partner 5xx", ex);
        }
        catch (HttpClientErrorException ex) {
            int status = ex.getStatusCode().value();
            if (status == 408 || status == 429) {
                throw new PartnerUnavailableException(
                        "Partner temporarily throttled", ex);
            }
            throw new IllegalArgumentException(
                    "Partner request rejected", ex);
        }
        catch (ResourceAccessException ex) {
            throw new PartnerUnavailableException(
                    "Partner connection/timeout", ex);
        }
    }
}
```

Uses JDK-based `SimpleClientHttpRequestFactory` to keep dependencies minimal. From Spring Framework 6.1+, `setConnectTimeout(Duration)` and `setReadTimeout(Duration)` match Boot 3.5 APIs. These bound the adapter only, **not** an end-to-end deadline across the whole workflow.

`RestClient.retrieve()` throws subclasses of `RestClientException` on HTTP 4xx/5xx by default. The adapter separates 5xx/408/429 (transient), 400/401/403 and other 4xx (permanent), and TCP/read timeouts (transient). Contract violations (bodies other than `APPROVED`/`DECLINED`) raise errors rather than silently approving.

### 7.11. `RabbitTopology.java`

```java
// src/main/java/com/example/resilience/RabbitTopology.java
package com.example.resilience;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RabbitTopology {

    public static final String EXCHANGE = "lab.events";
    public static final String QUEUE = "lab.orders";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange eventsExchange() {
        return new DirectExchange(EXCHANGE, false, false);
    }

    @Bean
    Queue ordersQueue() {
        return new Queue(QUEUE, false);
    }

    @Bean
    Binding ordersBinding(
            Queue ordersQueue, DirectExchange eventsExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(eventsExchange).with(ROUTING_KEY);
    }
}
```

Non-durable exchanges and queues are strictly for **ephemeral broker tests**. Production requires evaluating durable queues/exchanges, persistent messages, quorum/HA policies, and replay contracts. `RabbitAdmin` declares `Exchange`/`Queue`/`Binding` beans on the broker when the AMQP connection opens; integration tests run against the real broker rather than just checking bean names.

### 7.12. `RabbitConfirmedPublisher.java`

```java
// src/main/java/com/example/resilience/RabbitConfirmedPublisher.java
package com.example.resilience;

import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.AmqpException;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class RabbitConfirmedPublisher implements BrokerGateway {

    private final RabbitTemplate template;

    public RabbitConfirmedPublisher(RabbitTemplate template) {
        this.template = template;
    }

    @Override
    public void publishConfirmed(String orderId) {
        publishTo(RabbitTopology.ROUTING_KEY, orderId);
    }

    // Public so integration tests can exercise unroutable cases.
    public void publishTo(String routingKey, String orderId) {
        CorrelationData correlation =
                new CorrelationData(UUID.randomUUID().toString());

        try {
            template.convertAndSend(
                    RabbitTopology.EXCHANGE,
                    routingKey,
                    "ORDER:" + orderId,
                    correlation);

            CorrelationData.Confirm confirm =
                    correlation.getFuture()
                            .get(4, TimeUnit.SECONDS);

            if (!confirm.isAck()) {
                throw new BrokerUnavailableException(
                        "Publisher NACK");
            }

            if (correlation.getReturned() != null) {
                throw new BrokerUnavailableException(
                        "Message not routed");
            }
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new BrokerUnavailableException(
                    "Interrupted waiting for confirm", ex);
        }
        catch (ExecutionException | TimeoutException
                | AmqpException ex) {
            throw new BrokerUnavailableException(
                    "Broker publish not confirmed", ex);
        }
    }
}
```

Key points:

- `CorrelationData` carries a unique ID to correlate confirms/returns with each publication.
- `getFuture().get(4, TimeUnit.SECONDS)` waits for a bounded broker ACK/NACK.
- Both `confirm.isAck()` and `correlation.getReturned()==null` must hold.
- An unroutable message can still receive a publisher ACK; never mark outbox `SENT` based on ACK alone.
- On timeout, the final state is uncertain; leave the outbox `PENDING`.
- On thread interruption, the code restores the interrupted flag.
- No `Thread.sleep` is needed to await AMQP callbacks.
- This proves **broker publication**, not consumer processing or downstream DB commits.

### 7.13. `OutboxDispatcher.java`

```java
// src/main/java/com/example/resilience/OutboxDispatcher.java
package com.example.resilience;

import org.springframework.stereotype.Service;

@Service
public class OutboxDispatcher {

    private final OrderStore store;
    private final BrokerGateway broker;

    public OutboxDispatcher(
            OrderStore store, BrokerGateway broker) {
        this.store = store;
        this.broker = broker;
    }

    public int replayPending() {
        int sent = 0;

        for (String id : store.pendingIds()) {
            try {
                broker.publishConfirmed(id);
                store.markSent(id);
                sent++;
            }
            catch (BrokerUnavailableException ex) {
                // Keep PENDING for the next replay pass.
                // Production needs logging/metrics, retry budgets, and alerts.
            }
        }

        return sent;
    }
}
```

The demo dispatcher is invoked **explicitly** without `@Scheduled` so tests avoid background races. Production needs managed scheduling/runners, retry/backoff, worker claim/lease coordination, dead-letter/quarantine handling for poison payloads, and protection against duplicate concurrent dispatchers.

If `store.pendingIds()` or `store.markSent()` fails because the database is offline, the exception propagates so the job knows the DB failed instead of silently reporting “replayed 0”. When the publisher fails, the row stays `PENDING` and the loop continues to other items. Outbox payloads/headers need stable event IDs for consumer dedup; the demo uses `ORDER:orderId` and a unique outbox event ID.

## 8. Unit tests: six Mockito failure-policy assertions

Unit tests run without Spring, PostgreSQL, RabbitMQ, or an HTTP server. They inject exceptions at exact ports and verify consequences.

### 8.1. `WorkflowServiceUnitTest.java`

```java
// src/test/java/com/example/resilience/WorkflowServiceUnitTest.java
package com.example.resilience;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

class WorkflowServiceUnitTest {

    PartnerGateway partner;
    OrderStore store;
    BrokerGateway broker;
    WorkflowService workflow;

    @BeforeEach
    void setup() {
        partner = mock(PartnerGateway.class);
        store = mock(OrderStore.class);
        broker = mock(BrokerGateway.class);
        workflow = new WorkflowService(partner, store, broker);
    }

    @Test
    void happyPathPersistsPublishesAndMarksSent() {
        when(partner.approved("o1")).thenReturn(true);

        assertThat(workflow.submit("o1"))
                .isEqualTo(Outcome.BROKER_CONFIRMED);

        verify(store).savePending("o1");
        verify(broker).publishConfirmed("o1");
        verify(store).markSent("o1");
    }

    @Test
    void businessDeclineDoesNotWriteOrPublish() {
        when(partner.approved("o2")).thenReturn(false);

        assertThat(workflow.submit("o2"))
                .isEqualTo(Outcome.DECLINED);

        verifyNoInteractions(store, broker);
    }

    @Test
    void upstreamUnavailableDoesNotCreateOrder() {
        when(partner.approved("o3"))
                .thenThrow(new PartnerUnavailableException("503"));

        assertThat(workflow.submit("o3"))
                .isEqualTo(Outcome.UPSTREAM_UNAVAILABLE);

        verifyNoInteractions(store, broker);
    }

    @Test
    void databaseUnavailablePreventsBrokerPublish() {
        when(partner.approved("o4")).thenReturn(true);
        doThrow(new DataAccessResourceFailureException("db down"))
                .when(store).savePending("o4");

        assertThat(workflow.submit("o4"))
                .isEqualTo(Outcome.DATABASE_UNAVAILABLE);

        verify(broker, never()).publishConfirmed("o4");
        verify(store, never()).markSent("o4");
    }

    @Test
    void brokerUnavailableLeavesOutboxPending() {
        when(partner.approved("o5")).thenReturn(true);
        doThrow(new BrokerUnavailableException("broker down"))
                .when(broker).publishConfirmed("o5");

        assertThat(workflow.submit("o5"))
                .isEqualTo(Outcome.PENDING_DELIVERY);

        verify(store).savePending("o5");
        verify(store, never()).markSent("o5");
    }

    @Test
    void invalidRequestNeverCallsDependencies() {
        assertThatThrownBy(() -> workflow.submit(" "))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(partner, store, broker);
    }
}
```

**Six tests** verify the logic and zero-side-effect contracts. They **do not** prove real connection timeouts or broker disconnects because all gateways are mocks. That is why we add the HTTP adapter test and Postgres/Rabbit integration suite next.

Mockito `verifyNoInteractions` is particularly valuable in fault tests: a method might return the right error outcome while accidentally firing an unwanted side effect beforehand.

## 9. HTTP test with a real loopback server: 200/400/503/timeout

### 9.1. `HttpPartnerGatewayTest.java`

Java 17 bundles `com.sun.net.httpserver.HttpServer` in the JDK. Each test starts a fresh server on ephemeral port 0 without external networks or WireMock dependencies, exercising `RestClient` over a real HTTP connection.

```java
// src/test/java/example/resilience/HttpPartnerGatewayTest.java
package example.resilience;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class HttpPartnerGatewayTest {

    private HttpServer server;
    private HttpPartnerGateway gateway;
    private final AtomicInteger statusCode = new AtomicInteger(200);
    private final AtomicInteger delayMs = new AtomicInteger();

    @BeforeEach
    void start() throws IOException {
        statusCode.set(200);
        delayMs.set(0);

        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/decision", exchange -> {
            try {
                int delay = delayMs.get();
                if (delay > 0) {
                    Thread.sleep(delay);
                }

                int status = statusCode.get();
                String response =
                        status == 200 ? "APPROVED" : "TEMPORARY";
                byte[] body = response.getBytes(
                        StandardCharsets.UTF_8);

                exchange.sendResponseHeaders(status, body.length);
                try (var output = exchange.getResponseBody()) {
                    output.write(body);
                }
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
            catch (IOException ignored) {
                // Client may have timed out and closed the socket.
            }
            finally {
                exchange.close();
            }
        });

        server.start();
        String baseUrl = "http://127.0.0.1:"
                + server.getAddress().getPort();

        gateway = new HttpPartnerGateway(
                RestClient.builder(), baseUrl);
    }

    @AfterEach
    void stop() {
        server.stop(0);
    }

    @Test
    void okResponseIsApproved() {
        assertThat(gateway.approved("o1")).isTrue();
    }

    @Test
    void http503IsClassifiedAsTemporaryFailure() {
        statusCode.set(503);

        assertThatThrownBy(() -> gateway.approved("o2"))
                .isInstanceOf(PartnerUnavailableException.class);
    }

    @Test
    void http400IsNotMisclassifiedAsTransient() {
        statusCode.set(400);

        assertThatThrownBy(() -> gateway.approved("o3"))
                .isInstanceOf(IllegalArgumentException.class)
                .isNotInstanceOf(
                        PartnerUnavailableException.class);
    }

    @Test
    void slowResponseFailsWithinReadTimeoutBudget() {
        delayMs.set(1_000);

        assertThatThrownBy(() -> gateway.approved("o4"))
                .isInstanceOf(PartnerUnavailableException.class);
    }
}
```

**Four HTTP tests.** `HttpServer` runs inside the test process yet requests still cross TCP loopback, unlike direct Mockito stubs. The 503/400 tests verify HTTP status mapping, and the 1000 ms delay vs. 250 ms read timeout verifies the adapter detects expiration.

**Never assert rigid timings such as “exactly 250 ms”.** HTTP connection setup, OS scheduling, GC, and CI load vary; for SLAs, measure elapsed bounds with wide margins in isolated tests. The server stops in `@AfterEach` and uses neither fixed ports nor external endpoints.

**Limitations:** this is a local HTTP fault test and does not cover DNS failures, TLS handshakes, proxy buffering, connection pool exhaustion, HTTP/2 multiplexing, or distributed tracing. For richer APIs, WireMock/MockWebServer/Pact may fit; always keep transport tests separate from business policy tests.

## 10. Integration tests with real PostgreSQL and RabbitMQ

### 10.1. `@ServiceConnection` for both containers

Spring Boot 3.5 provides `JdbcConnectionDetails` for `PostgreSQLContainer` and `RabbitConnectionDetails` for `RabbitMQContainer`. Annotating typed static containers with `@ServiceConnection` lets Spring Boot auto-wire mapped host/port/credentials without hardcoding `localhost:5432` or `localhost:5672`.

The Testcontainers JUnit extension uses `@Container` to start/stop containers per test class. Spring TestContext may cache contexts longer than a single class; the demo adds `@DirtiesContext(AFTER_CLASS)` so no subsequent test reuses a context pointing at stopped containers.

### 10.2. `OutageIntegrationTest.java`

```java
// src/test/java/com/example/resilience/OutageIntegrationTest.java
package com.example.resilience;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.rabbitmq.publisher-confirm-type=correlated",
        "spring.rabbitmq.publisher-returns=true",
        "spring.rabbitmq.template.mandatory=true"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class OutageIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    @ServiceConnection
    static RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:4.1.8-management");

    @MockitoBean
    PartnerGateway partner;

    @Autowired
    WorkflowService workflow;

    @Autowired
    OrderStore store;

    @Autowired
    OutboxDispatcher dispatcher;

    @Autowired
    RabbitConfirmedPublisher publisher;

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void cleanTestOwnedRows() {
        jdbc.update("DELETE FROM outbox_events");
        jdbc.update("DELETE FROM placed_orders");
    }

    @Test
    void happyPathCommitsDbAndConfirmsBrokerPublish() {
        String id = "i-" + UUID.randomUUID();
        given(partner.approved(id)).willReturn(true);

        assertThat(workflow.submit(id))
                .isEqualTo(Outcome.BROKER_CONFIRMED);
        assertThat(store.isPending(id)).isFalse();

        assertThat(rabbitTemplate.receiveAndConvert(
                RabbitTopology.QUEUE, 5_000))
                .isEqualTo("ORDER:" + id);
    }

    @Test
    void simulatedBrokerFaultKeepsOutboxForRealReplay() {
        String id = "i-" + UUID.randomUUID();
        given(partner.approved(id)).willReturn(true);

        BrokerGateway offline = orderId -> {
            throw new BrokerUnavailableException(
                    "injected broker outage");
        };

        WorkflowService testWorkflow =
                new WorkflowService(partner, store, offline);

        assertThat(testWorkflow.submit(id))
                .isEqualTo(Outcome.PENDING_DELIVERY);
        assertThat(store.isPending(id)).isTrue();

        // Once the fault is removed, the dispatcher uses the real broker.
        assertThat(dispatcher.replayPending()).isEqualTo(1);
        assertThat(store.isPending(id)).isFalse();

        assertThat(rabbitTemplate.receiveAndConvert(
                RabbitTopology.QUEUE, 5_000))
                .isEqualTo("ORDER:" + id);

        assertThat(dispatcher.replayPending()).isZero();
    }

    @Test
    void unroutableMessageCannotBeMarkedAsDelivered() {
        String id = "i-" + UUID.randomUUID();

        assertThatThrownBy(() ->
                publisher.publishTo("no.such.route", id))
                .isInstanceOf(BrokerUnavailableException.class)
                .hasMessage("Message not routed");
    }

    @Test
    void secondInsertFailureRollsBackWholeDbUnit() {
        String id = "i-" + UUID.randomUUID();

        jdbc.update(
                "INSERT INTO outbox_events(event_id,payload,sent) "
                        + "VALUES (?, ?, FALSE)",
                id, "preexisting");

        assertThatThrownBy(() -> store.savePending(id))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        Integer orders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM placed_orders "
                        + "WHERE order_id = ?",
                Integer.class,
                id);
        assertThat(orders).isZero();
        assertThat(store.isPending(id)).isTrue();
    }
}
```

**Four integration tests — exact scope:**

- `happyPath...`: real Postgres persists order/outbox, real RabbitMQ ACKs publication, message lands in queue, outbox turns sent.
- `simulatedBrokerFault...`: uses a fault-injecting gateway throw, **without actually severing the broker network**. Verifies the DB outbox stays `PENDING` and the dispatcher then uses the **real broker** to replay. This is a policy + recovery integration test, not a physical outage test.
- `unroutable...`: hits **real RabbitMQ** with an unbound routing key. A publisher confirm ACK may arrive, yet the mandatory return triggers failure. It does not prove RabbitMQ is offline.
- `secondInsertFailure...`: creates a unique-constraint collision on the outbox in **real Postgres**, confirming rollback of the preceding order `INSERT`. This is a **DB transaction failure**, not a TCP connection drop.

Tests generate UUIDs to avoid business ID collisions and wipe only **test-owned database tables**; they never touch production databases. Do not enable parallel test methods sharing the same context/data without key namespacing and isolated cleanup. The RabbitMQ queue belongs to the test class container; each test consumes its own message rather than touching a shared production queue.

### 10.3. Why not stop/start containers mid-test?

Calling `postgres.stop()` then `postgres.start()` between tests can change mapped ports, connection details, or database data lifecycle. Spring `ApplicationContext` and HikariCP may cling to old `DataSource` settings, causing test-harness failures rather than testing resilience logic. On brokers, open AMQP channels may not detect dead sockets immediately.

**To simulate connection drops while keeping server/data/ports stable, use a TCP proxy such as Toxiproxy** (section 11). Never stop shared databases or brokers in multi-worker CI.

## 11. Toxiproxy: fault injection on real DB or broker connections

Testcontainers provides a Toxiproxy module allowing you to block traffic or inject latency/bandwidth limits between the JVM and a container on the Docker network. This is far closer to “dependency temporarily unreachable” than Mockito, as traffic truly traverses the JDBC/AMQP client stack.

### 11.1. Diagram

```text
JUnit JVM
   |
   |  JDBC / AMQP client
   v
Toxiproxy (stable mapped host port)
   |
   |  Docker network
   v
PostgreSQL container / RabbitMQ container

Healthy: proxy forwards traffic
Fault:   latency toxic / upstream-downstream cut
Recover: remove toxic, traffic resumes
```

Keep backend containers alive throughout the fault; toggle only the network proxy state. That preserves the database, broker queues, and proxy address so recovery can be verified cleanly.

### 11.2. Dependency and version

For Testcontainers **1.x** managed by Boot 3.5's BOM, the artifact is `org.testcontainers:toxiproxy`. Testcontainers **2.x** examples may use different coordinates/Java packages (e.g., `testcontainers-toxiproxy`). Never mix 2.x modules into a 1.x project.

```xml
<!-- Add when implementing the extension exercise with Testcontainers 1.x -->
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>toxiproxy</artifactId>
    <scope>test</scope>
</dependency>
```

**Important:** The code below is an **extension blueprint**, not a fourth runnable file in the starter project. You must attach Postgres, RabbitMQ, and Toxiproxy to the same Docker `Network`, expose proxy ports, and route JDBC/AMQP clients through the proxy rather than `@ServiceConnection`'s direct container address.

### 11.3. Avoid a very common bug: `@ServiceConnection` bypassing the proxy

Leaving `@ServiceConnection` directly on `PostgreSQLContainer`/`RabbitMQContainer` lets Boot wire `JdbcConnectionDetails`/`RabbitConnectionDetails` straight to the containers. Enabling a toxic on Toxiproxy while the app connects directly yields false-green tests.

In a dedicated fault-injection suite:

- Use `@DynamicPropertySource` manually to point JDBC URL/username/password at the **proxy endpoint**.
- For AMQP, point `spring.rabbitmq.host/port` at the proxy endpoint.
- Ensure no other service connection takes higher precedence and overrides those properties.
- Distinguish container network aliases on the proxy's upstream side from the mapped host/port used by the JVM.
- Verify baseline traffic actually passes through the proxy using a temporary toxic plus a query/publish round trip.
- A fault-injection test must fail if the proxy is not genuinely in the network path.

### 11.4. Database network-cut scenario

1. Start PostgreSQL and the proxy, initializing the schema via a connection routed through the proxy.
2. Baseline: `SELECT 1` and `savePending` with a test-only ID succeed.
3. Inject a Toxiproxy network cut in both directions or add latency exceeding the JDBC/query timeout.
4. If Hikari holds idle connections, ensure the fault affects existing paths; soft-evict connections or await bounded validation depending on adapter.
5. Execute a new transaction and wait up to the designed deadline.
6. Assert the exception matches the expected failure category, **never** turning into `BROKER_CONFIRMED`.
7. Assert the database holds no half-written order/outbox transaction; on unknown commit outcomes, look up by request ID after recovery.
8. Remove the toxic.
9. Wait within a bounded window until the connection pool/queries recover.
10. Safely retry/reconcile per idempotency policy.

### 11.5. RabbitMQ network-cut scenario

1. Start RabbitMQ and the proxy, declaring exchange/queue/binding.
2. Baseline: publish + confirm + receive on a test-only queue.
3. Inject cuts in upstream/downstream directions (publisher→broker and broker→publisher).
4. Call publish with `CorrelationData` and a bounded confirm timeout.
5. On failure, never mark the outbox `SENT`; verify `PENDING` in Postgres.
6. Remove the toxic, ensuring the channel/connection factory can reconnect.
7. Dispatcher replays pending rows; assert broker message delivery and outbox state.
8. Rely on stable event IDs / consumer idempotency to handle duplicates if the broker received the first attempt before the confirm dropped.

**Never assert that the broker definitely “did not receive the event” on a confirm timeout.** Assert instead that the system loses no work and handles duplicates safely.

### 11.6. Fault type example (API illustration)

Testcontainers Toxiproxy docs support creating a `ContainerProxy` and latency/bandwidth toxics:

```java
// PSEUDOCODE/SCHEMATIC, not a standalone test class.
var proxy = toxiproxy.getProxy(postgres, 5432);
proxy.toxics()
        .latency("db-latency", ToxicDirection.DOWNSTREAM, 1_500);

// Execute JDBC with read/query timeout < latency.
// Assert timeout/failure outcome while preserving data invariants.
// After the test, remove the toxic (or drop proxy) in finally.
proxy.toxics().get("db-latency").remove();
```

For “connection drop”, use zero-bandwidth toxics downstream/upstream or connection-reset toxics depending on Toxiproxy version. Method names, enums, constructors, and container images depend on pinned Testcontainers/Toxiproxy versions—check the API docs of **your exact pinned dependencies** before turning the snippet into runnable code.

**Always clean up faults in `finally`** and never point a proxy at production databases or brokers.

## 12. Retries, exponential backoff, jitter, and timeout budgets

### 12.1. Never retry infinitely

A retry policy can be expressed as:

```text
Total request budget: 2.0s
First attempt timeout: 300ms
Backoff between attempts: 100ms, 200ms (with jitter)
Max attempts: 3
Stop when deadline exhausted
Return explicit UPSTREAM_UNAVAILABLE or PENDING_DELIVERY
```

This is a **design example**, not auto-configuration from the sample project. It does not automatically guarantee every execution path finishes under 2 seconds; account for connection queueing, DNS, TLS, scheduler delays, and callback timing.

### 12.2. Retrying by exception/HTTP status

- GET/idempotent operations: retry 408/429/502/503/504 within budget and honor `Retry-After` if present.
- Mutating POSTs for payments/orders: retry only with idempotency keys backed by server contract, or reconcile after timeouts.
- DB transactions: perform controlled retries on deadlocks/serialization failures, never on all `SQLException`s.
- Broker publishing: retry via durable outboxes without assuming prior attempts failed to land.
- 400/401/403/validation/schema errors: fix input or permissions; never exponentially retry.
- Half-open circuit breakers: test probes, concurrency, and metrics explicitly when using Resilience4j/Spring Cloud CircuitBreaker.

### 12.3. Retry storms and thundering herds

If 1,000 requests each retry 5 times during a downstream outage, the system amplifies load just as the provider is weakest. Apply rate limits, concurrency bulkheads, jitter, retry budgets, and circuit breakers. Tests should verify **maximum call counts**, deadlines, and recovery behavior.

### 12.4. Business-meaningful fallbacks

Fallbacks do not always mean “return success with fake data”:

- Read-only catalog: may serve stale cached values within a permitted freshness window.
- Payment authorization: must never auto-approve on gateway timeout.
- Event publishing: persist pending outbox and return an in-progress status.
- Inventory: if stock cannot be verified, mark `CHECKING` rather than falsely claiming `CONFIRMED`.
- Security service: fail closed when permissions cannot be verified; never grant default access.

Fallback tests must prove **business and security contracts are never breached**.

## 13. Idempotency, duplicate delivery, and database uncertainty

### 13.1. No automatic end-to-end exactly-once

A multi-boundary flow:

```text
Client -> HTTP partner -> DB commit -> broker confirm
                              |            |
                   commit outcome?    confirm outcome?
                              |            |
                           uncertain    uncertain
```

After a timeout, retries can create duplicates on either side. An outbox improves reliability yet the publisher can still re-emit an event.

### 13.2. Idempotency test plan for production

Business requests should carry a stable `requestId`/`eventId` assigned by the client/gateway. Tests should cover:

1. Submit the same ID twice (identical payload) → one business record, one logical event.
2. Submit the same ID with a different payload → explicit conflict, never silently overwrite.
3. Broker delivers duplicate events → consumer commits the business effect only once.
4. Marking `SENT` fails after publish succeeds → replay creates zero duplicate effects.
5. Two dispatchers claim the same outbox row → locking/lease/unique logic holds.
6. Client times out after commit → retry looks up status by request ID rather than creating anew.
7. DLQ/exhausted retries → evidence preserved with an operator remediation path.

**The runnable sample above uses only a primary key as a final guardrail**, without implementing a full API idempotency state machine. Never equate a single unique constraint with a complete exactly-once guarantee.

### 13.3. “At-least-once” is the practical reality with replays

When an outbox replays after confirm uncertainty, embrace at-least-once publication paired with idempotent consumers. Never promise exactly-once across database + broker without an explicit, proven coordination/transaction protocol.

## 14. Tests that pass falsely

| Anti-pattern | Why it's wrong | Replace with |
| --- | --- | --- |
| Mockito throw labeled “Postgres outage integration” | Uses no real JDBC/socket | Label as unit-policy test; add proxy fault test |
| Stopping container causes startup failure | Fault happens before baseline, misses recovery | Start healthy, inject fault once app is ready |
| Broker `convertAndSend` didn't throw → `DELIVERED` | Publishing is asynchronous | Check confirms + returns + real queue/consumer |
| Confirm ACK → consumer DB committed | ACK is publisher-level only | Consumer business side-effect/ACK tests |
| `Thread.sleep(5000)` then assert | Flaky and slow | Bounded conditions/latches/await |
| `@Transactional` on test method expecting listener rollback | Transactions are thread-local | Isolated test DB/schema with explicit cleanup |
| Catching all `DataAccessException` → 503 | Masks schema/constraint bugs | Catch only policy-approved transient exceptions |
| Retrying every 4xx/5xx | Fuels storms or retries permanent failures | Classify by status/code/operation |
| Timeout → assume server did nothing | Response may drop after commit | Idempotency keys and reconciliation |
| Stopping shared RabbitMQ broker on CI | Breaks other tests | Dedicated container/Toxiproxy |
| Direct `@ServiceConnection` + fault proxy | App bypasses the proxy | Inject connection details pointing to the proxy |
| Fake HTTP server on fixed port | CI port conflicts | Port 0 and dynamic base URL |
| Forgetting to remove toxics after test | Leaks faults to later tests | `try/finally` cleanup |
| Queue depth 0 → job processed | Message may be delivered/unacked/misrouted | Assert business state |
| Ignoring logs/metrics | Blind to failure causes | Error categories + retry/pending metrics |
| Testing failure without recovery | Does not prove resilience | Baseline → fault → restore → replay |
| Testing recovery without duplicates | Replay may apply twice | Idempotent consumer tests |

## 15. Test plan by failure matrix

### 15.1. Database

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| Pool acquisition failure | Gateway mock + Testcontainers/Toxiproxy | `DATABASE_UNAVAILABLE`, broker not called | Reconnect and retry |
| Mid-transaction SQL error | PostgreSQL unique collision | Order insert rolled back | Fix data/constraint, do not blindly retry |
| DB restart/network cut | Toxiproxy/postgres isolation | Bounded timeout, no corrupted state | Pool recovers, query by `requestId` |
| Commit response lost | Proxy cut near commit (hard to time) | Uncertain state, reconcile before retry | Query stable ID |
| Deadlock/serialization failure | Two transactions with lock contention | Bounded full-transaction retry | Zero duplicates |
| Read-only replica or permissions | Test-only user/DB role | Writes fail safely | Route to writer / fix permissions |

### 15.2. RabbitMQ

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| Broker unreachable | `BrokerGateway` mock / Toxiproxy cut | `PENDING`, never marked `SENT` | Replay pending |
| Unbound routing key | Real broker + mandatory return | Exception, never marked `SENT` | Fix binding, then replay |
| Missing exchange | Real broker, channel error | Never treated as send success | Fix topology |
| Confirm timeout | Proxy drops downstream ACK | Pending, outcome unknown | Idempotent replay |
| Consumer throws exception | Test listener + DLQ policy | Bounded retries / no endless requeue | DLQ/reprocess |
| Consumer crashes after DB commit before ACK | Test consumer recovery | No duplicate business effect | Dedup/inbox |

### 15.3. External HTTP service

| Fault | Injection | Assertion | Recovery |
| --- | --- | --- | --- |
| HTTP 503 | `HttpServer`/WireMock | `UPSTREAM_UNAVAILABLE`, no DB writes | Bounded retry |
| Read timeout | Response delay > client timeout | Timeout exception classified properly | Idempotency / safe GET retry |
| HTTP 400 | Server stub | Permanent error, zero retries | Fix request |
| HTTP 429 | Server stub + `Retry-After` | Rate-limit budget | Retry at proper pace |
| Invalid JSON/schema | Malformed stub body | Contract error | Versioned contract tests |
| TCP reset | TCP fault injection | Bounded transport failure | Reconnect |
| Slow partial response | Streaming/HTTP stub | Read timeout/deadline | Never block threads forever |
| Auth failure 401/403 | Provider stub | Fail closed, no unsafe fallback | Re-auth / fix permissions |

## 16. Logging, tracing, and metrics for resilience

### 16.1. Minimum observability signals

- `dependency=postgres|rabbitmq|partner-http`.
- `outcome=success|temporary_failure|permanent_failure|unknown`.
- `retry.attempt`, `retry.exhausted`, `circuit.state`, `bulkhead.rejected`.
- `outbox.pending.count` and age of the oldest pending event.
- `publisher.confirm.ack` / `nack` / `returned`.
- HTTP status categories, timeout types, and latency histograms.
- Pool idle/active/pending metrics; AMQP connections/channels.
- DLQ item count and poison/replay attempts.
- Incident correlation IDs/event IDs in logs/traces per data policy.

Never put raw user IDs or order IDs into **low-cardinality metric tags**, risking cardinality explosions. Keep credentials, tokens, and PII out of test logs. Use stable structured error codes instead of grepping raw strings like “connection refused”.

### 16.2. Recovery evidence

Observability assertions should verify metrics/log events match *each state*:

```text
upstream_down → request rejected as retryable
db_down       → outbox not newly created, broker not called
broker_down   → pending_count increases
broker_up     → replay_count increases, pending_count decreases
replay_twice  → no extra pending work; downstream idempotent
```

If metrics exporters are disabled in tests, use an in-memory `MeterRegistry` or fake tracer instead of sending to production monitoring. End-to-end external metrics export belongs in its own test suite.

## 17. CI/CD: separating unit, integration, and chaos/fault suites

### 17.1. Running the sample project

```bash
java -version
mvn -version

# Six unit tests (no Docker):
mvn -B -ntp -Dtest=WorkflowServiceUnitTest test

# Four loopback HTTP tests:
mvn -B -ntp -Dtest=HttpPartnerGatewayTest test

# Four integration tests (requires Docker daemon):
docker version
docker info
mvn -B -ntp -Dtest=OutageIntegrationTest test

# All 14 methods:
mvn -B -ntp test
```

| Class | `@Test` count | Real dependencies |
| --- | ---: | --- |
| `WorkflowServiceUnitTest` | 6 | Mockito gateways |
| `HttpPartnerGatewayTest` | 4 | Local JDK `HttpServer` |
| `OutageIntegrationTest` | 4 | PostgreSQL + RabbitMQ containers |
| **Total** | **14** | Docker required for full suite |

Maven commands are instructions for learners to run the source themselves. **Do not claim this project was compiled or executed while authoring this text**; stdout, startup timings, and Docker mapped ports depend on the environment.

### 17.2. Illustrative GitHub Actions workflow

```yaml
name: Resilience contract tests

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Docker preflight
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Maven tests
        run: mvn -B -ntp test
      - name: Publish Surefire reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: resilience-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

This CI runs unit, loopback HTTP, and container integration tests in one Maven phase. Advanced Toxiproxy suites can run in a separate profile/matrix once real fault-injection code is added.

**Environment prerequisites:** Docker-compatible daemon, permission to create containers, ability to pull PostgreSQL/RabbitMQ images, reachable mapped host ports, and enough CPU/RAM/disk for JVM + Erlang VM + PostgreSQL. Never hardcode `localhost:5432` or `localhost:5672` in integration tests.

### 17.3. Runner safety

- Never mount a shared privileged runner's Docker socket into untrusted PR jobs without isolation policies.
- Never run `docker system prune`/`FLUSHALL`/`DROP DATABASE` on shared resources.
- Never hit production endpoints to “test a network outage”.
- Pin reviewed image versions/digests; avoid `latest`.
- Never use `mvn test || true`; mandatory integration tests missing Docker must report an environment failure.
- Retain bounded logs/container logs with secrets redacted.
- Distinguish `UNIT PASS`, `HTTP ADAPTER PASS`, `DB/BROKER PASS`, and `CHAOS PASS`; an unexecuted suite must never count as passing.

## 18. Practice exercises

**Exercise 1 — Honest HTTP fallback.** Switch HTTP 503 to 429, read `Retry-After`, set `maxAttempts=2` for read-only GETs. Assert call counts and bounded total deadlines; forbid retries on 400/401.

**Exercise 2 — Uncertain POST timeout.** Simulate a partner committing a side effect and then delaying the response past client timeout. Design a request ID and status/reconciliation lookup. Never retry a non-idempotent POST in a blind while-loop.

**Exercise 3 — Database outage.** Add Testcontainers Toxiproxy 1.x; route JDBC traffic through the proxy. Run a baseline query, inject a cut, assert `DATABASE_UNAVAILABLE` or the right exception category, remove the fault, wait for the pool to recover, and retry.

**Exercise 4 — Atomic rollback.** In `OutageIntegrationTest`, make the second `INSERT` fail and verify the first `INSERT` rolls back. Temporarily remove `@Transactional` from `JdbcOrderStore.savePending` on a scratch branch, observe the difference, then restore it.

**Exercise 5 — Broker routing bug.** Change the routing key in `RabbitConfirmedPublisher` to `no.such.route`. Observe publisher confirms vs. mandatory returns; fix the binding and re-run.

**Exercise 6 — Broker network cut.** Route AMQP through Toxiproxy and inject a downstream cut causing confirm timeout. Assert the outbox stays `PENDING`; recover and replay. Never assert the prior message definitely wasn't stored.

**Exercise 7 — Crash after confirm before `markSent`.** Simulate `OrderStore.markSent` throwing after broker ACK. Replay emits duplicates; implement an idempotent consumer keyed by event ID/DB unique constraint and assert the effect runs once.

**Exercise 8 — Multiple dispatchers.** Run two workers scanning pending IDs concurrently. Design claims/leases/`SKIP LOCKED` or retry queues to prevent unnecessary double work.

**Exercise 9 — Deadline budget.** Chain three HTTP failures with backoff and compute the total budget. Verify the result returns before the deadline without blocking request threads indefinitely when providers vanish.

**Exercise 10 — Separate chaos suite.** Compare unit gateway faults, Testcontainers network cuts, and staging multi-node failovers. Document what each layer proves and what it leaves unproven.

## 19. Self-check questions

**1.** Does Mockito throwing `DataAccessResourceFailureException` prove a Postgres TCP outage?  
**Answer:** No; it checks a policy branch. Network checks require a real provider/proxy.

**2.** Does an HTTP client timeout guarantee the downstream never processed the request?  
**Answer:** No. The response may have dropped after the server committed; use idempotency/reconciliation.

**3.** If the database fails to save an order, should an order-created event be published?  
**Answer:** Usually no under this sample contract; never emit events for uncommitted state.

**4.** Does `convertAndSend` returning without throwing prove a queue received the message?  
**Answer:** No; verify publisher confirms/returns or real routing.

**5.** Does a publisher confirm ACK prove a consumer committed to its DB?  
**Answer:** No; the ACK is publication/broker-level, not consumer business processing.

**6.** Can a message receive a confirm ACK yet remain unrouted?  
**Answer:** Yes. Mandatory returns catch unroutable messages.

**7.** Can a `PENDING` outbox after timeout produce duplicates on replay?  
**Answer:** Yes, because the first attempt may have reached the broker. Consumers must be idempotent.

**8.** Does `@Transactional` on a test method roll back listener/dispatcher threads too?  
**Answer:** Not automatically; transactions are normally thread-bound.

**9.** Why use Toxiproxy instead of stopping/starting a shared container?  
**Answer:** To control network faults while preserving provider state, data, and stable ports without disrupting other tests.

**10.** What is the risk of leaving `@ServiceConnection` directly on containers when routing through a proxy?  
**Answer:** The app may bypass the proxy, causing toxics to have no effect and tests to pass falsely.

**11.** Should HTTP 400 be retried with exponential backoff like 503?  
**Answer:** Usually no; it is a permanent client/contract error, governed per operation policy.

**12.** What matters more than returning a `PENDING_DELIVERY` status?  
**Answer:** Having a real durable outbox that replays reliably without losing work and safely tolerates duplicates.

**13.** Why run a baseline before injecting faults?  
**Answer:** To distinguish pre-existing test harness failures from intentionally injected faults.

**14.** After restoring a dependency, what should you assert?  
**Answer:** Bounded recovery, accurate statuses, data/message consistency, and zero duplicate business effects.

## 20. QA checklist for resilience testing

- [ ] Failure modes split across database, broker, and HTTP, with healthy baselines?
- [ ] Each fault states its injection method and evidence scope (mock vs. network)?
- [ ] Transient errors separated from logic/schema/authorization errors?
- [ ] HTTP connect/read timeouts and total deadlines bounded finitely?
- [ ] Retries restricted to safe/idempotent operations with max attempts/backoff/jitter?
- [ ] 429/503/408 handled differently from 400/401/403?
- [ ] Upstream failures create no bogus orders or broker events?
- [ ] DB failures publish no events for uncommitted state?
- [ ] Transaction rollbacks verified against a real database?
- [ ] Uncertain commit outcomes have request IDs and reconciliation plans?
- [ ] Business state and outbox events commit in the same transaction?
- [ ] Publisher confirms and mandatory returns enabled and tested independently?
- [ ] Broker timeouts never treated as proof of non-delivery?
- [ ] `PENDING` outbox rows replayed after recovery?
- [ ] Consumer idempotency handles redeliveries and duplicates?
- [ ] Connection pool recovery verified during physical outages?
- [ ] Context caching/container lifecycles never reuse stopped endpoints?
- [ ] Fault toxics cleaned up in `finally`?
- [ ] Never stop shared DBs/brokers or use production credentials?
- [ ] Avoided fixed sleeps and unbounded timeouts?
- [ ] CI separates skipped tests, environment failures, and passing resilience checks?
- [ ] Logs/metrics/traces record failure reasons, pending counts, and retry exhaustion with redaction?
- [ ] Avoided claiming exactly-once without full tests and evidence?

## 21. Official references

- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): typed `PostgreSQLContainer`/`RabbitMQContainer`, `@ServiceConnection`, and dynamic connection details.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `spring.sql.init.mode=always` and schema scripts.
- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): auto-configured `RestClient.Builder`.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): `RestClient` status handlers and error mapping.
- [Spring Framework 6.2 — SimpleClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html): `setConnectTimeout(Duration)`, `setReadTimeout(Duration)`.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, rollback boundaries.
- [Spring Framework — DataAccessException hierarchy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/DataAccessException.html): transient vs. non-transient database errors.
- [Spring AMQP — RabbitTemplate, Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): `CorrelationData` futures, confirms, returns, mandatory routing.
- [Spring AMQP — CorrelationData Javadoc](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/connection/CorrelationData.html): `getFuture()`/`getReturned()`.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): broker confirms and consumer ACKs are separate contracts.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): poison messages, requeue, DLQ.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): Postgres container tests.
- [Testcontainers Java — RabbitMQ Module](https://java.testcontainers.org/modules/rabbitmq/): broker integration tests.
- [Testcontainers Java — Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): injecting latency, connection cuts, and bandwidth faults.
- [Testcontainers Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): container lifecycle.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation, retries, and commit behavior.
- [Resilience4j — Documentation](https://resilience4j.readme.io/docs): optional circuit breaker, retry, bulkhead; align versions when adding the library.

**Conclusion:** Testing “stays reliable when a database, broker, or HTTP downstream is temporarily unavailable” requires asserting **business invariants** rather than just catching exceptions. When HTTP fails, fail cleanly; when the DB fails, never emit bogus events; when the broker fails, keep committed work in an outbox for replay. Mockito protects control branches, loopback HTTP and real Testcontainers protect protocols and transactions, and Toxiproxy tests real network failure and recovery. Never mistake a non-throwing publish for delivery, never equate a timeout with non-execution, and never claim exactly-once when replay/duplicate risks remain.
