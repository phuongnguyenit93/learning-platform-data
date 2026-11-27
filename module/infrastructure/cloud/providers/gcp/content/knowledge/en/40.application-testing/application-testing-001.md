# Unit, Integration, and End-to-End Strategy for GCP Services

A service running on Google Cloud may receive requests via Cloud Run or Google Kubernetes Engine (GKE), write data to Cloud SQL, upload objects to Cloud Storage, and emit events via Pub/Sub. If you only verify that a Java method returns the expected value, the team still does not know whether IAM, networking, the database, or the message queue actually work together. Conversely, if every test deploys to GCP, execution time, cost, and environment coupling increase sharply.

An effective testing strategy separates responsibilities across **unit tests**, **integration tests**, and **end-to-end (E2E) tests**. Unit tests verify business decisions and rules, integration tests verify connection boundaries between components, and E2E tests validate user journeys on an actually deployed system.

This lesson builds a testing strategy for GCP services, using examples with Java/Spring Boot, Cloud Run, GKE, Cloud SQL, Pub/Sub, Cloud Storage, and CI/CD. The focus is on testing at the right level, isolating data, avoiding flaky tests, and using test results to decide whether a release is reliable enough to ship.

## 1. Understanding the Three Testing Levels

The three testing levels answer different questions:

| Level | Primary Question | Resources Needed | Characteristics |
|---|---|---|---|
| Unit | Is the logic of a single unit correct for a given input? | Test process, mocks/fakes, and in-memory data | Fast, deterministic, runs continuously |
| Integration | Do two or more components interact correctly? | Database/container, emulators, or real GCP services | Slower, verifies contracts and connection configuration |
| E2E | Does a business journey complete end-to-end on a deployed system? | API, identity, network, runtime, and production-like dependencies | Higher cost, sensitive to environment conditions |

For example, for an order-placement journey:

- Unit test: total amount is non-negative, a cancelled order cannot be confirmed, retries must honor the idempotency key.
- Integration test: the repository reads/writes Cloud SQL with the right schema; the publisher produces a Pub/Sub message with valid payload and attributes.
- E2E test: call the create-order API on Cloud Run, verify the order is persisted, the event is processed, and the order status transitions to `CONFIRMED`.

~~~mermaid
flowchart TD
    A[Source change] --> B[Unit tests]
    B --> C[Component and integration tests]
    C --> D[Build immutable artifact]
    D --> E[Deploy isolated staging]
    E --> F[E2E critical journeys]
    F --> G{Quality gates passed?}
    G -->|Yes| H[Release approval or promotion]
    G -->|No| I[Inspect failure and fix]
    I --> A
~~~

**Test count is not the ultimate goal.** A short suite that protects critical business risks can be far more valuable than thousands of tests that merely mirror code structure. Choose the lowest level that can detect a defect reliably; use higher levels to verify boundaries that lower levels cannot prove.

## 2. Designing a Risk-Based Strategy

Before writing tests, list the behaviors that cause real damage when wrong: double-charging a payment, dropping messages, granting overly broad permissions, writing data into a production project, or failing to recover after a timeout.

A suitable risk matrix for GCP services:

| Risk | Unit | Integration | E2E |
|---|---|---|---|
| Incorrect billing calculation | Test pricing rules and rounding | Test DB data-type mapping | Test a complete order |
| Duplicate message delivery | Test idempotency decision | Test retry, ack/nack, and consumer | Send the same request twice, verify one business effect |
| Wrong database schema | Test pure mappers | Run migrations against real PostgreSQL | Test deployed API against staging schema |
| Missing IAM permissions | Mock failure to test handling | Call API in sandbox with a real principal | Test actual workload identity in staging |
| Network misconfiguration | Not needed at unit level | Test connectivity between service and dependency | Test journey across VPC/ingress/runtime |
| Incompatible API | Test serialization/validation | Consumer/provider contract tests | Smoke test communication between deployed services |
| Latency exceeding SLO | Test timeout logic | Test timeout/retry with fault controls | Measure end-to-end journey and real operational signals |

Pair each risk with a **meaningful assertion** and an owner. Do not force every test to verify every behavior. For example, a unit test does not need to verify Cloud Storage IAM, because a mock does not enforce real IAM.

### The Testing Pyramid

Typically, you should have many unit tests, fewer integration tests, and a short E2E suite focused on critical journeys. This is a design principle, not a mandatory numeric ratio.

- Unit tests run as developers edit code and on every pull request.
- Integration tests run on pull requests or before merge, depending on cost and container/emulator availability.
- E2E smoke tests run after staging deployment and before production promotion.
- Full E2E, performance, and fault-injection tests can run on a schedule or for high-risk changes.

## 3. Creating Clear Boundaries for Testability

A Java/Spring service should separate business logic from adapters calling Google Cloud. Controllers handle HTTP, application services orchestrate business flows, and repositories or gateways handle communication with Cloud SQL, Pub/Sub, and Cloud Storage.

~~~mermaid
flowchart LR
    A[HTTP Controller] --> B[Application Service]
    B --> C[Domain Rules]
    B --> D[OrderRepository interface]
    B --> E[EventPublisher interface]
    D --> F[Cloud SQL adapter]
    E --> G[Pub/Sub adapter]
    B --> H[AttachmentStore interface]
    H --> I[Cloud Storage adapter]
~~~

Example interface to separate decision logic from the SDK:

~~~java
public interface AttachmentStore {
    boolean exists(String objectName);
}

public final class AttachmentService {
    private final AttachmentStore store;

    public AttachmentService(AttachmentStore store) {
        this.store = store;
    }

    public String status(String objectName) {
        if (objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException("Object name is required");
        }
        return store.exists(objectName) ? "READY" : "MISSING";
    }
}
~~~

The production adapter uses the Google Cloud Storage client; unit tests can use a mock of `AttachmentStore`.

Other testability boundaries include:

- Inject `Clock` into code handling expirations and TTLs instead of calling `Instant.now()` everywhere.
- Inject a UUID generator or ID provider interface into code requiring deterministic results.
- Externalize retry and timeout settings into dedicated configuration that can be overridden in tests.
- Construct Google Cloud clients only in configuration or adapter layers; avoid instantiating clients inside every business method.
- Process Pub/Sub messages through a pure handler before wiring it to the subscriber.
- Separate business decisions from side-effect steps; use the outbox pattern when DB state and events must remain consistent.

Do not mock every line of code. Mocks are for controlling external boundaries; domain rules should run for real in tests.

## 4. Unit Testing with JUnit 5 and Mockito

Unit tests should run fast and have no dependency on the network, ADC, a GCP project, or shared resources. A good unit test has explicit input data and produces deterministic results regardless of when it runs.

Example test for `AttachmentService`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class AttachmentServiceTest {
    @Test
    void returnsMissingWhenObjectDoesNotExist() {
        AttachmentStore store = mock(AttachmentStore.class);
        when(store.exists("orders/42.pdf")).thenReturn(false);

        AttachmentService service = new AttachmentService(store);

        assertEquals("MISSING", service.status("orders/42.pdf"));
        verify(store).exists("orders/42.pdf");
        verifyNoMoreInteractions(store);
    }

    @Test
    void rejectsBlankObjectNameWithoutCloudCall() {
        AttachmentStore store = mock(AttachmentStore.class);
        AttachmentService service = new AttachmentService(store);

        assertThrows(IllegalArgumentException.class,
                () -> service.status("  "));
        verifyNoInteractions(store);
    }
}
~~~

These tests verify two things: the business outcome and that the program does not call the adapter when the input is invalid. They do not need a real Cloud Storage bucket.

Prefer assertions on observable behavior or state. Checking how many times an internal method was called is only useful when the call count itself matters to the requirement, such as preventing duplicate writes or unnecessary API calls.

### Parameterized Tests

For multiple input variants, use JUnit 5 parameterized tests:

~~~java
@ParameterizedTest
@ValueSource(strings = {"", " ", "\t"})
void rejectsInvalidNames(String name) {
    AttachmentService service = new AttachmentService(object -> true);

    assertThrows(IllegalArgumentException.class,
            () -> service.status(name));
}
~~~

This example tests both empty strings and whitespace. When code has many edge cases, parameterized tests are more readable than duplicated test methods.

### Testing Retry and Idempotency Logic

An adapter calling Pub/Sub or Cloud Storage must classify errors: timeouts or transient errors may be retried, whereas authorization errors or invalid requests generally should not be retried indefinitely. In unit tests, simulate failures and use a controlled clock/scheduler to verify:

- Maximum attempt count and wait duration.
- Exponential backoff and jitter within bounds.
- Stopping retries on non-recoverable errors.
- No duplicate records or events created when the same idempotency key appears.
- Retries do not exceed the overall request deadline.

Avoid `Thread.sleep()` in unit tests to wait on schedulers. Use a fake clock, fake scheduler, or component that lets you control time.

## 5. Testing Spring MVC and the HTTP Boundary

A Spring controller also needs tests for status codes, validation, JSON serialization, error responses, and security filters. You can use `@WebMvcTest` for HTTP slice tests without booting the full application context or connecting to GCP.

Example structure:

~~~java
@WebMvcTest(OrdersController.class)
class OrdersControllerWebTest {
    @Autowired MockMvc mvc;

    // Provide a mock for the controller dependency matching the
    // Spring Boot version in use, for example @MockitoBean.

    @Test
    void missingOrderReturns404() throws Exception {
        // Arrange: mock the application service to return not found.
        // Act: mvc.perform(get("/orders/missing-id")).
        // Assert: status, content type, and error response.
    }
}
~~~

This is an illustrative skeleton; add the project's actual controller and corresponding mocks. With Spring Boot 3.4+, you can use Spring Framework's `@MockitoBean`; older versions commonly use `@MockBean`. Choose the annotation that matches the project's Spring Boot/Spring Framework version and do not mix them arbitrarily.

Cases to test:

- Valid requests and missing required fields.
- Malformed JSON and unsupported fields.
- Authentication and authorization rules at the HTTP layer.
- 400/401/403/404/409/429/5xx status codes per the API contract.
- Response schema and error details that do not leak tokens or stack traces.
- Idempotency and correlation ID headers.

**HTTP slice tests do not prove that connections to Cloud SQL or Pub/Sub actually work.** Those boundaries belong to integration tests.

## 6. Integration Testing with a Real Database Using Testcontainers

Cloud SQL for PostgreSQL runs PostgreSQL, so many SQL/schema bugs can be caught early with a local PostgreSQL container. Testcontainers lets each suite spin up a database with a pinned version instead of relying on a shared developer-managed database.

Example integration test with Spring Boot, JUnit 5, and Testcontainers:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.util.AssertionErrors.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.dao.DataIntegrityViolationException;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.util.UUID;

@SpringBootTest
@Testcontainers
class OrderPersistenceIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProps(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void rejectsDuplicateIdempotencyKey() {
        jdbc.update(
                "INSERT INTO order_requests (id, idempotency_key) VALUES (?, ?)",
                UUID.randomUUID(), "request-42");

        assertThrows(DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO order_requests (id, idempotency_key) VALUES (?, ?)",
                        UUID.randomUUID(), "request-42"));
    }
}
~~~

This example assumes the application migrations have created the `order_requests` table and a unique constraint on `idempotency_key`. The test also requires the Spring Boot Test, Testcontainers JUnit Jupiter, Testcontainers PostgreSQL, and PostgreSQL JDBC driver dependencies. It runs on a machine or CI runner with a compatible Docker/container runtime.

A high-quality integration test should:

- Run the same migrations as production rather than creating a fake schema that differs from reality.
- Use a PostgreSQL version compatible with the Cloud SQL instance in use.
- Verify constraints, transactions, indexes, serialization, timezone handling, and isolation levels.
- Clean up data or create a dedicated database/schema per suite.
- Avoid parallel tests mutating the same shared table simultaneously.

**A PostgreSQL container does not emulate Cloud SQL HA, IAM database authentication, VPC networking, the Cloud SQL connector, backups, or failover.** Those aspects must be tested against real GCP services in sandbox/staging.

## 7. Integration Testing with the Pub/Sub Emulator

Pub/Sub provides an emulator for developing and testing certain publish/subscribe behaviors without calling the live service. You can start it via the Google Cloud CLI:

~~~bash
gcloud beta emulators pubsub start \
  --project="orders-test" \
  --host-port="127.0.0.1:8085"
~~~

Then obtain the required environment variables using:

~~~bash
gcloud beta emulators pubsub env-init
~~~

Java configuration must point the Pub/Sub client to the emulator endpoint, use a non-TLS channel for localhost, and use a credentials mechanism that does not require real credentials. **Do not assume every version of the Java Pub/Sub client handles `PUBSUB_EMULATOR_HOST` identically**; configure the endpoint/channel and credentials provider according to the exact library version in use.

An integration test suite can:

1. Create a dedicated topic and subscription for the suite.
2. Publish a message with `eventType=OrderCreated` and a correlation ID.
3. Read the message from the subscription.
4. Verify payload, attributes, event version, and message ordering if required by the logic.
5. Verify ack/nack/retry behavior within what the emulator supports.
6. Shut down the publisher/subscriber and clean up emulator resources.

Do not treat the emulator as proof of the following production properties:

- IAM and service account permissions.
- VPC, Private Service Connect, or VPC Service Controls.
- Real quotas, throughput, and latency.
- All edge cases of ordering, dead-letter topics, or exactly-once delivery.
- Availability characteristics and failure modes of the managed service.

For those properties, you need integration tests against real Pub/Sub in a dedicated project.

### Handling Duplicate Processing

With Pub/Sub, consumers must handle message redelivery. In tests, send the same logical event ID twice and verify that only one business change is committed. Deduplication should rely on durable state, such as a unique constraint in the database or a processed-events table; an in-memory `Set` can be lost when the process restarts.

## 8. Firestore, Cloud Storage, and Other Emulators

Not every service has an official emulator with the same level of fidelity. Choose your test double based on the question you need to answer.

| Service | Fast Testing | Testing Requiring Real GCP |
|---|---|---|
| Firestore | Firestore emulator for basic CRUD/queries | IAM, indexes/config, performance, quotas, and features not fully emulated |
| Pub/Sub | Emulator for publish/subscribe and message handlers | IAM, quotas, throughput, networking, advanced delivery semantics |
| Cloud SQL | Testcontainers with matching PostgreSQL/MySQL/SQL Server | Cloud SQL Auth Proxy/connector, IAM, HA, backups, networking |
| Cloud Storage | Fake adapter or limited third-party emulator | Bucket IAM, signed URLs, retention, versioning, metadata, and real API semantics |
| Spanner/Bigtable | Service-supported emulators for applicable APIs | IAM, service-specific consistency/performance, quotas, and managed operations |
| Secret Manager | Fake adapter/fixture containing no real secrets | Per-version IAM, secret lifecycle, and runtime identity |

Example of starting the Firestore emulator:

~~~bash
gcloud emulators firestore start \
  --host-port="127.0.0.1:8080"
~~~

When running Java tests, configure `FIRESTORE_EMULATOR_HOST` and a test project matching the library. Check how the Java client picks up the emulator endpoint in the version you use; do not configure production ADC for requests sent to the emulator.

For Cloud Storage, fakes or third-party emulators should only be used for integration tests within the scope they support. **Do not treat a fake Cloud Storage as a complete simulation of IAM, retention policies, signed URLs, or production behavior.**

A practical rule is to pick an emulator when you want to catch serialization, API-usage, or handler bugs; pick real GCP when testing permissions, networking, service configuration, or semantics not guaranteed by the emulator.

## 9. Integration Testing Against Real GCP Services

Testcontainers and emulators cannot verify full IAM policies or Cloud Run/GKE configurations. Therefore, a subset of integration tests should run in a sandbox project with real Google Cloud resources.

Examples:

- Cloud Storage: the test service account only reads/writes within a lab bucket prefix; test metadata, generation preconditions, and 403 errors.
- Pub/Sub: publish a message to a lab topic, verify the subscriber processes and acks it; verify the configured dead-letter policy.
- Cloud SQL: connect via the Cloud SQL connector/Auth Proxy using IAM and networking matching staging.
- Secret Manager: verify the workload can read the permitted secret/version and is denied access to other secrets.
- Cloud Run/GKE: verify the service identity has the expected permissions and fails with a clear error when permissions are missing.

### Isolating the Test Project

Name resources using the run ID or commit:

~~~text
environment: test
run-id: pr-1842-a1b2
topic: orders-pr-1842-a1b2
subscription: orders-pr-1842-a1b2-sub
object-prefix: tests/pr-1842-a1b2/
~~~

Best practices:

- Use a dedicated project and quota for integration tests.
- Use a test identity with least privilege.
- Never connect directly to the production database.
- Set quotas/budgets/alerts to prevent runaway costs.
- Enforce resource expiration for automatic cleanup and record the owner.
- Ensure cleanup runs even if tests fail or CI is cancelled.

Cleanup must not delete resources using overly broad prefixes. Record the exact resources created by the test run and delete only those resources.

## 10. End-to-End Testing on Cloud Run and GKE

E2E tests verify the real user path: client → ingress/authentication → application → database/event system → business outcome.

Example journey:

~~~mermaid
sequenceDiagram
    participant T as E2E test client
    participant A as Orders API on Cloud Run
    participant DB as Cloud SQL
    participant P as Pub/Sub
    participant W as Worker on GKE
    T->>A: POST /orders with idempotency key
    A->>DB: Save order and outbox record
    DB-->>A: Commit success
    A-->>T: 202 Accepted and order ID
    A->>P: Publish pending event via outbox relay
    P->>W: OrderCreated message
    W->>DB: Complete workflow and update status
    T->>A: GET /orders/{id}
    A->>DB: Read current status
    A-->>T: CONFIRMED
~~~

E2E tests should verify key behaviors:

1. The API returns the expected status and schema.
2. The authentication token has the right audience and permissions.
3. IDs/traces propagate across the system.
4. Data appears in the database.
5. The message is emitted and processed by the consumer.
6. The final state is correct and free of duplicate processing.
7. Completion time stays within the defined threshold.

For asynchronous systems, E2E tests must poll for completion conditions up to a deadline. Do not simply `sleep(10s)` and assume eventual consistency has settled. A polling loop with a bounded timeout and backoff is much more reliable.

### Choosing the Test Entry Point

- For private Cloud Run services, the client uses a Google-signed ID token with the correct audience for the service URL or configured custom audience.
- For private GKE services, the test runner can run inside the VPC/cluster or go through an endpoint protected as designed.
- Never open public ingress or disable authentication just to make E2E easier to run.
- If Cloud Load Balancing, API Gateway, or Cloud Armor sits on the production path, E2E must decide whether to test through those layers or target the service directly.

An E2E test calling the service directly can pass while ingress/API Gateway is misconfigured. Therefore, include at least one smoke test that traverses the actual access path users take.

## 11. Contract Testing and Asynchronous Event Testing

In a multi-service architecture, changing a JSON field or Pub/Sub attribute can break consumers even when each individual service passes its unit tests.

**Contract testing** verifies that a producer or provider honors the contract required by its consumers.

Common contracts include:

- REST API: path, method, status, required headers, JSON schema.
- Pub/Sub event: event type, schema version, payload, ordering key, attributes, and required fields.
- Database/event schema: backward compatibility when fields change.
- CloudEvents: `id`, `source`, `type`, `time`, and data conforming to the event format.
- gRPC/Protocol Buffers: field numbers, optional fields, and compatibility rules.

Example event:

~~~json
{
  "eventId": "evt-00042",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "ord-00042",
  "totalCents": 4200
}
~~~

Consumer contract tests should confirm that the consumer handles valid events of the current version and previous compatible versions. When adding new fields, do not assume every consumer deploys simultaneously.

### Do Not Rely on E2E to Catch Every Schema Error

Contract tests running early in CI catch breaking changes faster, while E2E ensures the deployed system still exchanges messages properly between services. Both levels complement each other.

### Testing Idempotency and the Outbox Pattern

In a workflow that writes to Cloud SQL and then publishes to Pub/Sub, the two independent operations do not form an automatic distributed transaction. If the DB commit succeeds but publishing fails, events can be lost unless the code includes a reliability mechanism.

The outbox pattern writes business data and an event record in the same database transaction, then a separate relay publishes the event. Tests must verify:

- When the database rolls back, the outbox event is not committed.
- When publishing fails transiently, the event remains for retry.
- When publishing succeeds but ack/mark-complete fails, a redelivery/re-publish may occur.
- The consumer handles duplicates via an idempotency key or event ID.

This business requirement is far more important than mocking the publisher and verifying that `publish()` was called once.

## 12. Test Data, Time, and Environments

Flaky tests usually stem from shared data, race conditions, clocks, and environment differences rather than from the testing framework itself.

### Independent Test Fixtures

- Use a UUID/run ID for every suite and object/message.
- Never assume a fixed execution order between tests.
- Never share a mutable database across multiple CI jobs without isolation.
- Generate minimal data needed for verification; do not copy personal production data.
- If production-like data is required, use synthetic or properly anonymized data following approved processes.
- Verify cleanup using actual resource IDs.

### Timezones and Time

- Use UTC when comparing timestamps across services.
- Unit tests should inject `Clock.fixed(...)` to verify TTL, expiry, and deadlines.
- Async tests must distinguish processing time, event time, and client-supplied timestamps.
- Avoid overly tight deadlines that fail only on slower CI runners than local machines.

### Eventual Consistency and Polling

Event-driven systems may need time for consumers to update state. Instead of asserting immediately after publishing, use a wait loop with an explicit deadline:

~~~java
Instant deadline = Instant.now().plus(Duration.ofSeconds(45));
boolean confirmed = false;

while (Instant.now().isBefore(deadline)) {
    if (orderClient.getStatus(orderId).equals("CONFIRMED")) {
        confirmed = true;
        break;
    }
    Thread.sleep(500);
}

assertTrue(confirmed, "Order did not reach CONFIRMED within deadline");
~~~

This illustrates E2E polling: bounded sleep used only in asynchronous tests. In unit tests, replace it with a fake scheduler or virtual time. Real tests should also handle thread interruption properly, bound the request count, and surface diagnostic context upon timeout.

## 13. Testing Security and Runtime Configuration

Unit tests can verify application authorization rules, but actual IAM and service identities must be verified in a deployed environment.

A minimal security matrix:

| Check | Appropriate Level |
|---|---|
| Validation rejects invalid input | Unit / HTTP slice |
| Endpoint returns 401 when token is missing | HTTP slice and E2E |
| Unauthorized user receives 403 | Integration/E2E with a test principal |
| Cloud Run runtime service account reads permitted bucket | Integration on GCP |
| Same service account is denied on another bucket | Integration on GCP |
| GKE Workload Identity Federation works | Integration on a real cluster |
| Secret Manager only returns secrets granted via IAM | Integration on GCP |
| Network egress/ingress matches VPC policy | Dedicated E2E/network test |

Test both allowed and denied cases. For example, a service account should be able to read the lab bucket while being denied on a bucket outside its permissions.

Do not bake long-lived JSON keys into test containers when you can use a runner-attached service account or Workload Identity Federation. On Cloud Run and GKE, Java clients should use the runtime's Application Default Credentials (ADC). For CI outside GCP, prefer Workload Identity Federation over downloaded keys.

Security tests must never print access tokens, ID tokens, API keys, or secret payloads to logs. For debugging, log policy-compliant non-sensitive principal emails, resources, error codes, and correlation IDs.

## 14. Setting Quality Gates in CI/CD

A pipeline should run tests ordered by cost and defect-detection capability.

~~~mermaid
flowchart TD
    A[Pull request] --> B[Static checks and unit tests]
    B --> C[Contract and container integration tests]
    C --> D{Pass?}
    D -->|No| E[Block merge]
    D -->|Yes| F[Build and scan image]
    F --> G[Deploy isolated staging]
    G --> H[Cloud integration and E2E smoke]
    H --> I{Critical journeys pass?}
    I -->|No| J[Stop promotion and collect diagnostics]
    I -->|Yes| K[Approval and production rollout]
    K --> L[Post-deploy health verification]
~~~

Example with Maven and clearly named test groups:

~~~bash
./mvnw -B test
./mvnw -B verify
~~~

The `test` command typically runs unit tests via Maven Surefire. For `verify` to run integration tests, you must configure Maven Failsafe or an equivalent plugin along with a naming convention such as `*IT`. Merely naming a file `OrderRepositoryIT` does not guarantee Maven runs it if the build is unconfigured.

### Assigning Gates to the Right Stage

| Stage | Recommended Checks | Action on Failure |
|---|---|---|
| Developer/PR | Unit, validation, contract, static security | Block merge |
| Pre-merge/CI | Integration with Testcontainers/emulators | Block build/release |
| Pre-release | Build, scan, provenance, image digest | Block release |
| Staging deploy | GCP integration and critical-path E2E | Block promotion |
| Production deploy | Safe smoke tests, SLI/error rate | Halt rollout, consider rollback |
| Scheduled | Full E2E, load, restore, fault simulation | Create remediation and track |

If using Cloud Build, store test reports (JUnit XML) and artifacts in a location with appropriate access controls. Cloud Deploy can promote the exact same image digest through staging and production; quality gates must bind to the tested release and artifact rather than relying on the `latest` tag.

### Controlling Time and Cost

- Cache Maven/Gradle dependencies according to appropriate policies.
- Run unit tests in parallel when tests share no mutable state.
- Group integration tests by dependency or container to avoid spinning up too many resources.
- Run full E2E only when needed; use a short smoke suite post-deploy.
- Configure timeouts per test, suite, and job.
- Cap the number of concurrent test projects and active resources.

## 15. Observability of Results and Handling Flaky Tests

A failing test is not always a product bug. It can result from CI infrastructure running out of quota, an unready dependency, shared test data, or unstable time-based test logic. However, dismissing every failure as flaky destroys the value of quality gates.

When a test fails, collect:

- Test name, commit SHA, run ID, environment, and UTC timestamp.
- Which assertion failed, inputs used, and expected vs. actual values.
- HTTP status, request ID, trace ID, and sanitized response.
- Corresponding Cloud Logging, Cloud Trace, or Cloud Monitoring entries.
- Pod/revision status, database health, and message backlog.
- Retry count, timeout, and cleanup status.

### Failure Classification

| Category | Examples | Action |
|---|---|---|
| Application bug | Wrong billing calculation, incompatible schema | Fix code and keep gate active |
| Configuration error | Wrong IAM, secret, endpoint, or network | Fix environment configuration |
| Test data issue | Shared fixtures, cleanup did not run | Isolate data |
| Improper test waiting | Premature assertions, fixed sleep | Use bounded polling with deadline |
| Infrastructure/quota | API 429, capacity shortage, CI runner lacks Docker | Adjust quotas, runners, or schedule |
| Unexplained flakiness | Fails intermittently | Quarantine with owner and deadline, investigate and fix |

Retrying tests can help surface intermittency, but do not use infinite retries just to turn a pipeline green. If a critical test becomes persistently flaky, assess the risk before temporarily removing it from a gate and assign an explicit owner to resolve it.

### Coverage and Mutation Testing

Code coverage shows which lines executed during tests, but does not prove assertions are strong enough. For critical business logic, consider adding mutation testing to measure how well tests catch injected faults. Do not inflate coverage with tests that merely invoke getters/setters or mock every dependency only to assert stubbed return values.

## 16. Performance, Resilience, and Fault Testing

E2E tests generally verify journey correctness; load and fault tests verify system behavior under stress or failure. Keep them separate from the standard smoke suite.

### Performance

For Cloud Run/GKE, build benchmarks measuring:

- Throughput, requests/second, and concurrency.
- p50/p95/p99 latency.
- Error rate, timeout rate, and retry rate.
- CPU, memory, autoscaling, and instance/Pod counts.
- Cloud SQL connection pool usage and connection limits.
- Pub/Sub backlog and age of oldest unacked message.

Load tests in isolated environments must use synthetic traffic with capped QPS and duration. Do not allow tests to accidentally incur large costs or exhaust shared project quotas.

### Resilience

Controlled experiments include:

- Terminating a GKE replica while other replicas remain active.
- Pausing a Pub/Sub subscriber and verifying backlog drain upon recovery.
- Injecting timeouts into dependency adapters.
- Verifying retries and circuit breakers do not amplify load.
- Testing Cloud SQL restore from backup/PITR on a separate instance.
- Verifying Cloud Run or Cloud Deploy rollback procedures follow the runbook.

Every experiment needs a hypothesis, scope, stop condition, SLO/RTO/RPO targets, and recovery plan. Never embed fault injection that could impact production into an automated E2E smoke test running on every deploy.

## 17. Practical Scenario: Orders API on GCP

Suppose a system consists of:

- Java/Spring Boot `orders-api` running on Cloud Run.
- Cloud SQL for PostgreSQL storing orders and outbox records.
- Pub/Sub delivering `OrderCreated` events.
- A worker running on GKE processing events.
- Cloud Storage storing invoices.
- Cloud Monitoring/Logging tracking health.

### Phase A — Unit Tests

Test the rules:

1. Orders with a negative total are rejected.
2. Duplicate idempotency keys do not create two orders.
3. Status `CANCELLED` cannot transition to `CONFIRMED`.
4. Transient timeouts are retried within limits.
5. Authorization errors in the adapter map to the appropriate business error.

Use JUnit 5 and Mockito/fakes without creating GCP resources.

### Phase B — Local Integration Tests

- Boot PostgreSQL Testcontainers with real migrations.
- Verify unique constraints and the transaction creating both order + outbox event.
- Use the Pub/Sub emulator to test serialization and handlers.
- Use a fake Cloud Storage adapter to test standard branches.
- Verify tests do not depend on execution order or leftover data from prior runs.

### Phase C — Integration Tests in GCP Sandbox

- Use the test service account to connect to Cloud SQL via the supported connector.
- Publish and consume an event on real Pub/Sub, verifying ack and retry behavior.
- Write/read a temporary object in the lab bucket, verifying generation preconditions.
- Verify the principal can read the permitted bucket and is denied on other buckets.
- Verify Secret Manager access and network configuration required for the workload.

### Phase D — E2E on Staging

1. Deploy the exact same image digest via Cloud Deploy.
2. Create an order with an idempotency key containing the run ID.
3. Verify the HTTP response returns the order ID.
4. Poll status until `CONFIRMED` within the deadline.
5. Verify the invoice is created under the test run's prefix.
6. Resubmit the same idempotency key and verify no duplicate business side effects occur.
7. Inspect logs/traces, latency, and message counts.
8. Clean up the exact order/test resources according to retention policies.

### Phase E — Quality Gates and Reporting

| Check | Passing Criteria |
|---|---|
| Unit | Rules pass, zero GCP dependencies |
| Database integration | Migrations, transactions, and constraints verified |
| Pub/Sub integration | Event schema, ack/retry, and idempotency verified |
| GCP sandbox | IAM and service connectivity verified |
| E2E | Critical order journey completes within deadline |
| Security | No leaked tokens, no over-privileged access |
| CI/CD | Reports and artifacts tied to commit/image digest |

If any critical gate fails, halt promotion and identify the root cause before deploying to production.

## 18. Testing Strategy Design Checklist

### Unit

- [ ] Core business logic is tested with boundary data.
- [ ] Tests never touch the network, GCP, or shared data stores.
- [ ] External dependencies are replaced by fakes/mocks at clean boundaries.
- [ ] Clocks, IDs, and retry schedulers are controllable.
- [ ] Assertions verify protected behavior rather than mirroring implementation.

### Integration

- [ ] Database migrations and constraints run against the target engine.
- [ ] Emulators are used within their fidelity scope, with limitations documented.
- [ ] Real GCP tests cover IAM, networking, and unemulated features.
- [ ] Data/resources are isolated by run ID with safe cleanup.
- [ ] No production credentials or unnecessary long-lived keys are used.
- [ ] Timeouts and diagnostic details are provided when dependencies fail.

### End-to-End

- [ ] Critical journeys traverse production-like ingress and identity.
- [ ] Final business side effects are verified, not just HTTP 200.
- [ ] Asynchronous flows use bounded polling with a deadline.
- [ ] Idempotency and essential failure paths are tested.
- [ ] Smoke suite is short, stable, and never mutates customer data.
- [ ] E2E results are linked to release, commit, and image digest.

### CI/CD and Operations

- [ ] Unit/contract tests run on pull requests.
- [ ] Integration gates run before release.
- [ ] GCP sandbox and E2E run before production promotion.
- [ ] Test reports, logs, and traces are retained per policy.
- [ ] Flaky tests follow a triage process with owner and deadline.
- [ ] Budgets, quotas, and cleanup guardrails exist for test resources.
- [ ] Load and chaos tests have dedicated scopes, guardrails, and schedules.

A strong unit, integration, and end-to-end testing strategy on GCP protects code correctness, inter-service contracts, and post-deployment runtime behavior simultaneously. By assigning clear responsibilities to each level, isolating test data, and enforcing quality gates in CI/CD, teams catch bugs early while still validating risks that only emerge inside the Google Cloud runtime.
