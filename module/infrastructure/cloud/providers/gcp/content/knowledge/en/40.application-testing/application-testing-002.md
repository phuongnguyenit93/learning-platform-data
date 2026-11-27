# Decoupling the Google Cloud Access Layer for Testing Java Applications

## 1. Why Decouple the Google Cloud Access Layer?

A Java service running on Cloud Run, GKE, or Compute Engine often needs to access Cloud Storage, Pub/Sub, Secret Manager, Firestore, BigQuery, or Cloud SQL. If the business logic layer directly creates Google Cloud clients, resolves Application Default Credentials (ADC), calls APIs, and interprets error codes, a simple unit test can inadvertently require network access, a project, quota, IAM, or real credentials.

For example, a `ReportService` tasked with creating reports might call `StorageOptions.getDefaultInstance().getService()` directly inside every method. To test the rule "an empty report must be rejected," the test may have to initialize the SDK and depend on the cloud environment. Tests become slow, hard to reproduce, and sometimes write data into a real bucket.

The solution is to **establish a clear boundary between business logic and external services**:

- Business logic knows only application-meaningful operations such as saving a report, finding a report, emitting an event, or reading configuration.
- Google Cloud adapters translate those operations into SDK calls.
- Unit tests replace adapters with in-memory fakes or mocks.
- Integration tests verify the real adapter against emulators when available or against isolated test resources.

Within the scope of `CLOUD_PROVIDERS_GCP`, this mindset helps test Java applications using Storage, IAM, VPC, Compute Engine, GKE, Cloud Run, databases, CI/CD, and reliability requirements. The goal is to have fast tests for business logic while still testing integration risks such as IAM permissions, networking, quotas, serialization, and retries before deployment.

## 2. Design Principle: Ports and Adapters

### 2.1. Desired Dependency Flow

A suitable model is **ports and adapters** (also known as hexagonal architecture). A port is an interface owned by the application. An adapter implements the port using an SDK or specific technology. The application service receives the port via its constructor, so it does not need to know which `Storage` class Cloud Storage uses, which publisher Pub/Sub uses, or whether the database runs on Cloud SQL or locally.

~~~mermaid
flowchart LR
    C[HTTP controller or scheduled job] --> S[Application service]
    S --> P[Port: ReportStore]
    P --> G[GCS adapter]
    G --> SDK[Google Cloud Storage Java SDK]
    SDK --> CLOUD[(Cloud Storage)]

    P -. test wiring .-> F[In-memory fake / Mockito mock]
    F -. no network .-> T[Unit or component test]
~~~

Dependency arrows in source code point from business logic to **interfaces defined by business logic**, while the adapter depends on that interface. The SDK lives in the outer layer. Spring configuration decides which adapter to wire based on the environment.

If Cloud Storage needs to be replaced with another system, the business logic typically does not have to change. If a failure case needs to be tested, the test controls the port's behavior without forcing the SDK to produce a real failure.

### 2.2. What Should and Should Not Cross the Port

| Should Appear in the Port | Should Stay in the Adapter |
|---|---|
| `saveReport(reportId, bytes)` | Bucket name, object path, `BlobInfo` |
| `findReport(reportId)` | `Storage.get(...)`, `Blob.getContent()` |
| `publishOrderCreated(event)` | Pub/Sub topic name, `Publisher`, message attributes |
| `getPaymentConfiguration()` | Secret Manager version path, client call |
| `loadCustomer(customerId)` | SQL query, Firestore document path |
| Business-meaningful exceptions | `StorageException`, `ApiException`, gRPC status |

Do not expose Google Cloud SDK types such as `Blob`, `PubsubMessage`, `DocumentSnapshot`, or `ApiException` in business APIs without a clear reason. If a port returns an SDK type, unit tests still have to understand that SDK and the business layer becomes locked into one provider.

Conversely, do not create an interface for every simple method of a library just to "have an interface." A port should express **business intent**, expose the fewest methods needed to serve the use case, and avoid becoming a generic mirror of the SDK.

## 3. Running Example: Service to Store and Read Reports

Suppose a Spring Boot application generates text reports and stores them in Cloud Storage. The business requirements are:

1. A report ID consists only of letters, digits, hyphens, or underscores; length 1–64 characters.
2. Content after trimming leading and trailing whitespace must not be blank.
3. A report is created once; do not overwrite an existing report with the same ID.
4. A report can be read back by ID; a missing report is translated into a clear business error.

We will separate three parts: `ReportStore`, `ReportService`, and `GcsReportStore`.

### 3.1. Application-Owned Port

~~~java
import java.util.Optional;

public interface ReportStore {
    void create(String reportId, byte[] content);

    Optional<byte[]> find(String reportId);
}
~~~

This interface does not import the Google Cloud SDK. `Optional.empty()` means the report does not exist yet. The contract should be documented clearly: `create` does not overwrite an existing object; `find` returns the report's bytes, not SDK metadata. When the application needs versions or checksums, add an internal model containing only the attributes truly needed.

### 3.2. Business Logic Unaware of Cloud Storage

~~~java
import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;
import java.util.Objects;

public final class ReportService {
    private final ReportStore reports;

    public ReportService(ReportStore reports) {
        this.reports = Objects.requireNonNull(reports);
    }

    public void create(String reportId, String content) {
        validateId(reportId);
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException("Report content is empty");
        }

        reports.create(
            reportId,
            content.strip().getBytes(StandardCharsets.UTF_8)
        );
    }

    public String read(String reportId) {
        validateId(reportId);

        byte[] bytes = reports.find(reportId)
            .orElseThrow(
                () -> new NoSuchElementException("Report not found")
            );

        return new String(bytes, StandardCharsets.UTF_8);
    }

    private static void validateId(String reportId) {
        if (reportId == null ||
            !reportId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid report ID");
        }
    }
}
~~~

`ReportService` contains only ID validation, content normalization, and missing-report handling. It has no dependency on `StorageOptions`, `BlobId`, or ADC. No statement here requires an Internet connection.

In a larger system, you can introduce dedicated exceptions such as `ReportNotFoundException` and `ReportAlreadyExistsException` so controllers map them to HTTP 404 or 409 respectively. This example uses `NoSuchElementException` and `IllegalArgumentException` to keep focus on the test boundary.

### 3.3. Cloud Storage Adapter Implementation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;

import java.util.Objects;
import java.util.Optional;

public final class GcsReportStore implements ReportStore {
    private final Storage storage;
    private final String bucket;

    public GcsReportStore(Storage storage, String bucket) {
        this.storage = Objects.requireNonNull(storage);
        this.bucket = Objects.requireNonNull(bucket);
    }

    @Override
    public void create(String reportId, byte[] content) {
        BlobId id = blobId(reportId);
        BlobInfo info = BlobInfo.newBuilder(id)
            .setContentType("text/plain; charset=utf-8")
            .build();

        storage.create(
            info,
            content,
            Storage.BlobTargetOption.doesNotExist()
        );
    }

    @Override
    public Optional<byte[]> find(String reportId) {
        Blob blob = storage.get(blobId(reportId));
        return blob == null
            ? Optional.empty()
            : Optional.of(blob.getContent());
    }

    private BlobId blobId(String reportId) {
        return BlobId.of(bucket, "reports/" + reportId + ".txt");
    }
}
~~~

Mapping the ID to an object path and `BlobInfo` details stays strictly inside the adapter. The `doesNotExist()` option applies a precondition to prevent overwriting an existing object; this is critical when create operations may be repeated by retries or multiple instances.

In a production application, the adapter should translate Google Cloud `StorageException` into application-defined exceptions. For example:

- `404` on reads is represented by `Optional.empty()` when the SDK returns null.
- `412 Precondition Failed` on creates can map to `ReportAlreadyExistsException`; if a prior response was lost, read the object state before concluding.
- `429`, `503`, or timeouts are transient infrastructure errors; they can map to `ReportStoreUnavailableException` preserving cause and retry classification.

Error mapping should preserve the underlying `cause`, error codes helpful for observability, and retry classification. Never swallow all errors and return `Optional.empty()`: doing so conflates "report does not exist" with "cannot reach Cloud Storage."

## 4. Configuring Dependency Injection in Spring Boot

The adapter should not create `Storage` via a static singleton. Spring configuration can create the client once and pass it into the adapter via constructor injection.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ReportConfiguration {
    @Bean
    @Profile("!test")
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }

    @Bean
    @Profile("!test")
    ReportStore reportStore(
        Storage storage,
        @Value("${app.reports.bucket}") String bucket
    ) {
        return new GcsReportStore(storage, bucket);
    }

    @Bean
    ReportService reportService(ReportStore store) {
        return new ReportService(store);
    }
}
~~~

In production, `StorageOptions` uses ADC to discover environment credentials. When running on Cloud Run or GKE, prefer a workload-attached service account or Workload Identity Federation rather than embedding a JSON key in the image. IAM must grant the right read/write permissions on the bucket.

In tests, the `test` profile skips creating the `Storage` and `GcsReportStore` beans. Tests supply their own fake `ReportStore`. Thus, booting the Spring context for tests does not depend on ADC or a Google Cloud project.

Do not place the entire application under a `test` profile if doing so disables business beans you need to test. Apply profiles or conditional configuration **only to external adapters**. For projects using Spring Cloud GCP auto-configuration, verify which beans are auto-created; disable unnecessary auto-configurations during tests.

## 5. Unit Testing with Mockito: Verifying Business Rules

### 5.1. Purpose of Mocks

Mockito mocks record interactions and can be programmed to return results or throw errors. Mocks are very useful when a test needs to verify:

- Valid data leads to exactly one write call.
- Invalid input is rejected before calling the external service.
- A "not found" result maps to a business error.
- Retries or fallbacks do not invoke extra unexpected dependencies.

In unit tests, you only need to instantiate `ReportService` and mock `ReportStore`; no Spring context, Google Cloud SDK credentials, network, or emulator is required.

### 5.2. Illustrative Unit Tests with JUnit 5 and Mockito

~~~java
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.aryEq;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class ReportServiceTest {

    @Test
    void createStoresUtf8Bytes() {
        ReportStore store = mock(ReportStore.class);
        ReportService service = new ReportService(store);

        service.create("report-17", "  Hello  ");

        verify(store).create(
            eq("report-17"),
            aryEq("Hello".getBytes(StandardCharsets.UTF_8))
        );
        verifyNoMoreInteractions(store);
    }

    @Test
    void invalidIdDoesNotCallStore() {
        ReportStore store = mock(ReportStore.class);
        ReportService service = new ReportService(store);

        assertThrows(
            IllegalArgumentException.class,
            () -> service.create("../secrets", "valid content")
        );

        verifyNoInteractions(store);
    }

    @Test
    void missingReportIsReported() {
        ReportStore store = mock(ReportStore.class);
        when(store.find("missing")).thenReturn(Optional.empty());

        ReportService service = new ReportService(store);

        assertThrows(
            NoSuchElementException.class,
            () -> service.read("missing")
        );

        verify(store).find("missing");
    }
}
~~~

These tests can run on a laptop without `gcloud`, key files, or Google Cloud permissions. They only verify `ReportService` rules and that the port is called according to contract. They do **not** prove the GCS adapter accesses the right bucket, holds IAM permissions, handles 412, or sets the right content type.

If you only assert `verify(store).create(...)`, it is easy to miss final outcomes and integration behavior. Therefore, supplement them with fakes and adapter tests.

## 6. In-Memory Fakes: Testing Behavior Across Multiple Calls

### 6.1. How Do Mocks Differ from Fakes?

Mocks are typically programmed per test and used to verify interactions. A **fake** is a simple implementation with real state, such as an in-memory map standing in for Cloud Storage. Fakes suit component tests or testing chained use cases without stubbing every single call.

A good fake must faithfully model the **core contract** of the port. If production forbids overwrites, the fake must forbid overwrites too. If the application expects byte-array immutability across the boundary, the fake should copy arrays so a caller cannot pass an array and mutate internal state accidentally.

### 6.2. Implementing the Fake

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryReportStore implements ReportStore {
    private final Map<String, byte[]> data = new ConcurrentHashMap<>();

    @Override
    public void create(String reportId, byte[] content) {
        byte[] copy = Arrays.copyOf(content, content.length);
        if (data.putIfAbsent(reportId, copy) != null) {
            throw new IllegalStateException("Report already exists");
        }
    }

    @Override
    public Optional<byte[]> find(String reportId) {
        byte[] value = data.get(reportId);
        return value == null
            ? Optional.empty()
            : Optional.of(Arrays.copyOf(value, value.length));
    }
}
~~~

Because each test should instantiate its own fake, state does not leak between tests. If a fake is shared across tests or held in a singleton Spring context, clear its data or set up isolated fixtures before each test.

### 6.3. Component Testing Through the Service Public API

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ReportComponentTest {

    @Test
    void createThenReadReturnsNormalizedContent() {
        ReportStore fake = new InMemoryReportStore();
        ReportService service = new ReportService(fake);

        service.create("r001", "  Test content  ");

        assertEquals("Test content", service.read("r001"));
        assertThrows(
            IllegalStateException.class,
            () -> service.create("r001", "overwrite")
        );
    }
}
~~~

The test verifies creation, reading, and overwrite protection without caring about SDK classes. If tomorrow the adapter switches from Cloud Storage to Firestore, this business test remains valid.

Fakes should be verified by **contract tests** so they do not drift from the real adapter in critical edge cases.

## 7. Testing the Google Cloud Adapter in Isolation

Even with a clean port, the application must verify that the adapter translates commands accurately: bucket name, object path, content type, preconditions, and not-found handling. You can mock the SDK itself at the adapter layer to check mappings without live API calls.

Example:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class GcsReportStoreTest {

    @Test
    void writesToConfiguredBucketWithCreateOnlyPrecondition() {
        Storage sdk = mock(Storage.class);
        GcsReportStore adapter = new GcsReportStore(sdk, "test-bucket");
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        adapter.create("r001", bytes);

        ArgumentCaptor<BlobInfo> info =
            ArgumentCaptor.forClass(BlobInfo.class);

        verify(sdk).create(
            info.capture(),
            same(bytes),
            any(Storage.BlobTargetOption.class)
        );

        assertEquals(
            BlobId.of("test-bucket", "reports/r001.txt"),
            info.getValue().getBlobId()
        );
        assertEquals(
            "text/plain; charset=utf-8",
            info.getValue().getContentType()
        );
    }

    @Test
    void missingObjectReturnsEmpty() {
        Storage sdk = mock(Storage.class);
        BlobId id = BlobId.of("test-bucket", "reports/r001.txt");

        when(sdk.get(id)).thenReturn(null);

        GcsReportStore adapter = new GcsReportStore(
            sdk, "test-bucket"
        );

        assertTrue(adapter.find("r001").isEmpty());
    }
}
~~~

The test above verifies that the adapter constructs the right path and content type. For preconditions, add an assertion on the option value per contract or an integration test confirming duplicate creation is rejected. Do not treat a Mockito `any(...)` match as proof that the real server enforces the precondition.

When the adapter must map `StorageException`, test 412, 429, 403, and 5xx codes according to policy, preserving error codes or causes as needed. If mocking the SDK becomes overly complex due to nested response objects, prefer testing at the port boundary and covering the remaining SDK behavior with integration tests rather than deeply stubbing library internals.

## 8. Testing the Spring Context Without Initializing Google Cloud Clients

The goal of a Spring component test is to verify bean wiring, configuration, and service/controller invocation flows. You can use a `@TestConfiguration` providing the fake port under the `test` profile.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = {
        ReportConfiguration.class,
        ReportSpringTest.FakeConfiguration.class
    }
)
@ActiveProfiles("test")
class ReportSpringTest {

    @Autowired
    ReportService service;

    @Test
    void applicationServiceUsesInjectedFake() {
        service.create("spring-1", "  test Spring  ");
        assertEquals("test Spring", service.read("spring-1"));
    }

    @TestConfiguration
    static class FakeConfiguration {
        @Bean
        ReportStore reportStore() {
            return new InMemoryReportStore();
        }
    }
}
~~~

Under the `test` profile, the two production beans `Storage` and `GcsReportStore` are not created, so Spring injects only the fake. Verify that the real application configuration has no other cloud beans triggered by auto-configuration that attempt to access ADC unexpectedly.

If a test only exercises `ReportService`, do not boot a Spring context: plain JUnit unit tests are faster. Reserve `@SpringBootTest` for verifying wiring, HTTP validation, security filters, or component-level behavior.

## 9. Choosing the Right Testing Level

No single test type proves everything. Combine levels based on execution speed and environmental fidelity.

| Test Type | Infrastructure Used | What It Verifies | What It Does Not Guarantee |
|---|---|---|---|
| Unit test | Mockito mock or stub | Business rules, validation, retry/fallback decisions | SDK behavior, IAM, and networking |
| Component test | Fake port and Spring context | Bean wiring, HTTP/controller, multi-step flows | Real serialization/SDK behavior |
| Adapter test | Mock SDK or protocol fake | Request/response translation, resource names, preconditions | Real server policies |
| Contract test | Same suite run on fake and adapter | Consistent contract behavior | Full cloud features if run only on fake |
| Emulator integration | Official emulator when available | Partial API, serialization, and client flows | IAM, quotas, VPC, all production behavior |
| Cloud integration | Sandbox project and real services | Real APIs, credentials, IAM, network, and metadata | Production scale and real data |
| End-to-end | Production-like staging environment | User journeys and cross-service interaction | All rare load/failure scenarios |

In practice, run many unit/component tests on every pull request, a set of adapter/contract tests regularly in the pipeline, and cloud integration/E2E tests in staging or controlled jobs.

## 10. Contract Tests: Keeping Fakes and Adapters Aligned

An in-memory fake can accidentally diverge from the cloud adapter. For instance, the fake might allow overwrites while the GCS adapter uses a create-only precondition; the fake returns data immediately while a database or event system may be eventually consistent.

A contract test suite should define shared behaviors:

1. Writing a new report and reading it back returns the exact bytes.
2. Writing a duplicate ID is rejected and leaves prior bytes unchanged.
3. Looking up a nonexistent ID returns `Optional.empty()`.
4. Content containing Unicode characters is preserved intact.
5. On non-not-found errors, the port throws an error rather than returning "does not exist."
6. Keys and IDs have clear constraints; behavior on invalid IDs is consistent.

Run the test suite against `InMemoryReportStore` and against an adapter connected to an integration environment. For backends with versioning, eventual consistency, or transactions, document differences that cannot be trivially simulated; avoid dragging every SDK quirk into the contract unless the business domain actually uses it.

Also note that the example fake throws `IllegalStateException` when a report already exists, whereas the SDK throws `StorageException` 412. **This is not yet a unified contract.** Before going to production, the adapter should translate 412 into `ReportAlreadyExistsException` and the fake should throw the same exception; then the contract test can assert identical behavior.

## 11. When to Use Emulators vs. Real GCP Resources?

Not every Google Cloud service has an official emulator or an emulator covering all APIs.

### 11.1. Suitable Emulators

Useful emulators include:

- **Pub/Sub emulator:** tests local publish/subscribe flows. Java clients typically require explicit endpoint/channel and no-credentials configuration; do not assume every SDK switches to the emulator automatically from a single environment variable.
- **Firestore emulator:** tests document reads/writes, transactions, and the subset of queries supported by the emulator.
- **Bigtable emulator:** exercises table read/write APIs without provisioning production resources.

Running emulators in CI provides fast integration tests and avoids live cloud charges. However, emulators often omit or simplify IAM, VPC, quotas, latency, certain validations, and backend behaviors. Check the service's emulator documentation before relying on a specific feature.

**Cloud Storage does not have an official emulator with full compatibility comparable to some of the services above.** Third-party fake servers exist, but you must verify compatibility with your SDK, generation conditions, metadata, signed URLs, and error responses. A protocol fake is only a supplementary test layer.

### 11.2. Using a Sandbox Project for Integration Checks

The following scenarios should be tested against real GCP services in a sandbox project:

- IAM, service accounts, Workload Identity Federation, and ADC.
- Bucket policies, object generations, preconditions, retention, and encryption.
- API enablement, service agents, quotas, rate limits, regions, and networking.
- Pub/Sub acknowledgments, duplicate delivery, retries, and dead-letter policies.
- Cloud SQL connectivity over private IP, connector, TLS, and failover.
- VPC Service Controls, organization policies, and IAM conditions.

Test projects must have dedicated identities, distinct resource names, billing/quota guardrails, and cleanup mechanisms. Avoid using production projects or real data for tests. Long-lived resources such as Cloud SQL, GKE, or Spanner need explicit teardown plans to avoid lingering costs.

## 12. Designing Tests for Pub/Sub and Asynchronous Flows

Pub/Sub differs fundamentally from CRUD: publishing and message handling can be asynchronous, delivery can repeat, and ack deadlines affect redelivery. Thus, the port should reflect business intent, for example:

~~~java
public interface EventPublisher {
    void publishReportCreated(String reportId);
}
~~~

The Pub/Sub adapter translates the event into a message, attributes, and topic. Business tests can use a fake that records emitted events:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class RecordingPublisher implements EventPublisher {
    private final List<String> events = new ArrayList<>();

    @Override
    public void publishReportCreated(String reportId) {
        events.add(reportId);
    }

    public List<String> events() {
        return List.copyOf(events);
    }
}
~~~

When testing a workflow, verify the event is emitted only after the report save succeeds and carries the right ID. Separate integration tests with the Pub/Sub emulator or a test topic verify serialization and the subscription flow.

Never assume one publish always results in exactly one processing execution. Design idempotent consumers, deduplicate by event ID or business key, and test retries/ack/nack and subscriber restarts. When transactional guarantees between a database and Pub/Sub are needed, consider the outbox pattern instead of publishing messages mid-transaction before commit.

## 13. Decoupling Secret Manager and Configuration

Applications often call Secret Manager for API keys, passwords, or confidential parameters. Avoid letting business services call `SecretManagerServiceClient` directly. A port can define the behavior:

~~~java
public interface PaymentSecrets {
    String paymentGatewayToken();
}
~~~

The production adapter uses Secret Manager with appropriate caching/refresh logic. Unit tests return a dummy token, never a real secret. Never log tokens, secret payloads, or access tokens.

Specific conditions to test:

- Correct secret version, such as a pinned version or approved alias.
- Permission denied on a secret reports a different error from "secret does not exist."
- Secret rotation does not cause the application to cache stale secrets indefinitely.
- The service account holds `roles/secretmanager.secretAccessor` on the exact target secret.
- Tests do not require production environment variables or service account key files.

Never place Secret Manager calls inside static initializers, domain object constructors, or validation methods, because doing so forces business tests to require credentials at instantiation time.

## 14. Decoupling Data Layers for Cloud SQL, Firestore, and BigQuery

How you apply ports depends on the data store:

- **Cloud SQL:** domain services depend on a repository interface; the adapter uses JDBC/JPA or a data-access library. Unit tests use a fake repository; integration tests can use Testcontainers with the matching engine and database version. Real Cloud SQL connectivity still needs separate tests for IAM, Cloud SQL connector/proxy, VPC, and TLS.
- **Firestore:** the port expresses queries in business terms. Use the Firestore emulator to test serialization, transactions, and supported queries; verify indexes, security rules, or IAM in an appropriate environment.
- **BigQuery:** the port represents analytical operations, such as fetching revenue aggregations. Unit tests substitute fixed data; real integration tests verify SQL dialect, schema, partitioning, quotas, and bytes scanned.
- **Spanner or Bigtable:** do not trivially mock transactions, consistency, partitioning, or scans with a map and treat it as equivalent to production.

An overly generic repository interface like `execute(String query)` leaks SQL or backend syntax into business logic. Prefer use-case methods such as `findActiveOrders(customerId)` or `saveInvoice(invoice)`.

## 15. Testing Errors, Retries, Timeouts, and Idempotency

Decoupling ports lets you inject faults intentionally without breaking a live project. Key scenarios:

| Scenario | Simulation in Test | Expected Outcome |
|---|---|---|
| Resource does not exist | Fake returns `Optional.empty()` | Application returns a clear not-found error |
| Insufficient permissions | Adapter/fake throws permission error | Do not retry indefinitely; emit proper telemetry |
| Quota 429 | Stub throws retryable error | Backoff and bounded retry attempts |
| Backend 503 | Stub fails a few times then succeeds | Bounded retry without duplicating side effects |
| Deadline exceeded | Controlled slow fake or virtual clock | Cancel/abort on deadline |
| Create succeeded but response lost | Fake writes then throws error | Read state, avoid duplicate creation |
| Concurrent creates with same ID | Thread-safe fake with put-if-absent | Only one request creates the resource |
| Serialization error | Adapter tested with malformed bytes/encoding | Do not write corrupt object or lose data |

Do not use `Thread.sleep()` in unit tests just to wait out backoff. If writing custom retry logic, inject a `Clock` or `Sleeper/Scheduler` interface and fake time in tests. If using Google Cloud Java clients with built-in retries, verify `RetrySettings` in the adapter and test end-to-end behavior in an appropriate environment without stacking uncontrolled retry layers.

A simple fake does not prove transactional guarantees or exactly-once semantics in the cloud. Scenarios involving side effects, race conditions, or event ordering require dedicated tests.

## 16. Controlling Test Data and Reproducibility

Good tests must be independent of execution order and environment state.

- Each test creates its own data; do not share object names or document IDs across tests.
- Prefix integration resources with a build ID or UUID; delete after tests and maintain fallback TTL/cleanup.
- Do not read system time directly in hard-to-test logic; inject `Clock` and use `Clock.fixed(...)` where needed.
- Do not use uncontrolled randomness in assertions; inject a generator or seed if needed.
- Do not share mutable fake state between tests unless lifecycle cleanup is explicitly managed.
- Do not rely on results from prior tests or pre-existing data in the project.
- Never put PII, tokens, private keys, or customer data into fixtures.
- Never use production resources to test deletions, migrations, or permissions.

For asynchronous tests, wait on a condition with a finite timeout rather than a fixed sleep. When eventual consistency or event pipelines are involved, use bounded polling and assert on final state.

## 17. Running Tests in CI/CD on GCP

A practical pipeline should split work into three tiers:

1. **Fast pull-request checks:** compile, unit tests, component tests, linting, and static analysis. Needs no Google Cloud credentials; must not deploy or modify production resources.
2. **Integration tests:** run emulators/Testcontainers or target a sandbox project. If using a real project, the job uses a dedicated least-privilege identity and runs only on permitted refs/trust levels.
3. **Release validation:** verify artifacts, staging smoke tests, API contracts, and critical flows before production promotion.

Cloud Build can run Maven or Gradle inside containers and store build logs. If CI runs outside Google Cloud, prefer Workload Identity Federation over long-lived JSON keys. The integration-test service account needs permissions only to create/delete/read its own test resources, not Owner.

Reference Maven profile command structure:

~~~text
mvn -B test                     # Unit/component tests, no GCP needed
mvn -B verify -Pintegration     # Project-configured integration tests
~~~

The `integration` profile name is a project-specific convention, not a built-in Maven default profile. Surefire/Failsafe configuration or equivalent tooling must separate tests by tag or class naming. In this STEP 4, the commands are academic examples only; no build or test execution was performed.

CI jobs using real GCP should verify:

- Environment variables point to the right test project, region, and bucket/topic/database.
- ADC or WIF resolves the intended principal; avoid key files in the repository.
- IAM permissions are sufficient and permission-denied paths are also tested.
- Quotas, billing, and concurrency are bounded.
- Every created resource is traceable, cleaned up, and covered by cost alerts.
- Logs and reports contain no secrets or sensitive data.

## 18. Common Design Anti-Patterns

| Practice Making Testing Hard | Impact | Improvement |
|---|---|---|
| Creating SDK clients inside every business method | Unit tests depend on ADC and network | Inject ports via constructor |
| Service returning `Blob` or `DocumentSnapshot` | Domain locked into the SDK | Use DTOs or internal domain models |
| Deeply mocking dozens of SDK classes | Tests break whenever SDK changes | Mock the port, test the adapter separately |
| Every test calling live cloud services | Slow, consumes quota, flaky | Separate unit/component from integration |
| Fake allowing behavior forbidden in production | False green tests | Write contract tests |
| Conflating not-found with 403/503 | Masks auth/infrastructure failures | Classify and map exceptions explicitly |
| Using Owner service account for integration tests | Huge blast radius | Least-privilege IAM and sandbox project |
| Sharing resource names across builds | Tests interfere with each other | Unique prefixes and cleanup |
| Testing retries with long sleeps | Slow and unstable | Inject clock/scheduler, control time |
| Logging keys or tokens for debugging | Credential exposure | Log request ID, operation, status, and trace ID |
| Trusting emulators to prove production IAM | Misses auth/policy bugs | Test IAM on real GCP |
| Exposing interfaces for every SDK API | Bloated, hard-to-maintain abstraction | Design ports around use cases |

## 19. Hands-On Exercise

A Spring Boot application stores product images in Cloud Storage and emits `ProductImageUploaded` events to Pub/Sub. Currently, the application calls `Storage` and `Publisher` directly inside the controller.

Requirements:

1. Draw the dependency diagram after separating into controller, application service, `ImageStore`, and `DomainEventPublisher`.
2. Design ports with business-focused methods that do not return SDK types.
3. Implement separate GCS and Pub/Sub adapters wired via Spring configuration.
4. Write unit tests verifying empty images are rejected and no event is published.
5. Write an in-memory map fake for image storage and a recording publisher; test that a valid image is stored before the event is emitted.
6. Write adapter tests checking object path, metadata, Pub/Sub topic, and serialization.
7. Run integration tests against the Pub/Sub emulator and an isolated Cloud Storage test project.
8. Simulate saving the image succeeded while publishing failed; propose outbox, idempotency, or appropriate compensation mechanisms.
9. Add cleanup and least-privilege IAM constraints for integration tests.
10. Define which criteria suffice for merge approval and which can only be verified in staging.

**Expected outcome:** all unit/component tests run without Google Cloud credentials, adapters have clear contracts, integration tests are isolated, and the pipeline needs cloud permissions only in the specific jobs that require them.

## 20. Self-Check Questions

1. Why does instantiating `StorageOptions` in a domain service constructor make unit testing difficult?
2. How do ports and adapters differ? Which side should own the interface?
3. When should you use a Mockito mock vs. an in-memory fake?
4. Why should contract tests run the exact same suite against both the fake and the adapter?
5. What bug occurs if a fake returns `Optional.empty()` for both 404 and 403?
6. Why is the Pub/Sub emulator insufficient to verify production IAM permissions or quotas?
7. In Spring Boot, how can you swap the GCS adapter for a fake without requiring ADC?
8. How does using a create-only precondition on Cloud Storage affect the contract and the fake?
9. Why must retrying a resource-creation operation be handled differently from retrying a read operation?
10. Which tests belong on pull requests and which belong in a sandbox project?
11. How do you avoid runaway costs or leftover data after cloud integration tests?
12. Why should business unit tests avoid verifying every internal SDK call of a Java library?

## References

- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Storage Java client reference](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Cloud Storage preconditions](https://cloud.google.com/storage/docs/request-preconditions)
- [Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Firestore emulator](https://cloud.google.com/firestore/native/docs/emulator)
- [Bigtable emulator](https://cloud.google.com/bigtable/docs/emulator)
- [Cloud Build overview](https://cloud.google.com/build/docs/overview)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Spring Framework testing](https://docs.spring.io/spring-framework/reference/testing.html)
- [JUnit 5 user guide](https://junit.org/junit5/docs/current/user-guide/)
- [Mockito](https://site.mockito.org/)
- [Testcontainers for Java](https://java.testcontainers.org/)
