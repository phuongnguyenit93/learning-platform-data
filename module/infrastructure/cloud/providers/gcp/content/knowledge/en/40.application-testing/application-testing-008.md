# Test Fixtures, Test Data, and Automated Resource Cleanup

A test for a Java application on Google Cloud may need users, orders, Pub/Sub messages, Firestore documents, Cloud Storage objects, or a database with an initialized schema. If these data fixtures must be created manually for every run, testing becomes slow, inconsistent, and hard to reproduce. Conversely, if tests create resources without cleaning them up, subsequent runs break, shared resources risk accidental deletion, and cloud bills creep upward.

A **test fixture** is the intentional input state prepared to test a behavior. A sound fixture workflow makes clear: where data is created, who owns it, how long it lives, how results are verified, and how resources are cleaned up afterward. For Google Cloud services, you must add project isolation, IAM boundaries, and a fallback mechanism to reclaim orphaned resources when a runner disconnects.

This lesson belongs to the **GCP Application Testing** chapter of the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; learners practice choosing services, securing resources, automating releases, and tracking reliability and cost. Here, we apply those principles to design reliable test fixtures, test data, and cleanup mechanisms for Java/Spring applications.

## Objectives

After this lesson, you will be able to:

- Distinguish fixtures, seed data, test factories, test doubles, teardown, and test environments.
- Choose the right execution target among unit tests, local containers, emulators, and dedicated GCP test projects.
- Generate deterministic, isolated test data containing zero real user data.
- Use JUnit 5, Spring Boot, and Testcontainers to prepare and clean up local resources.
- Create test resources in Cloud Storage under a unique prefix and clean up only owned resources.
- Design safe cleanup for Pub/Sub, Firestore, and other GCP resources.
- Handle killed runners, failed cleanups, parallel execution, and orphaned resources.
- Combine cleanup with least-privilege IAM, data retention limits, budgets, and CI/CD.

## 1. What Is a Test Fixture?

A fixture can be data, infrastructure resources, or state required before executing assertions. For example, to test an invoice-generation API, a test might need an active customer, an order with three items, and a tax configuration.

| Term | Meaning | Example |
|---|---|---|
| Fixture | Precondition state serving a test | Order in `PENDING` status |
| Seed data | Baseline data loaded into a test environment | Product catalog, region codes, and currencies |
| Test data factory / builder | Parameterized helper generating test data | `OrderFixtures.pendingOrder(customerId)` |
| Test double | Component substituting for a dependency | Fake payment gateway or mock HTTP client |
| Setup | Preparing preconditions before a test | Creating a bucket object or customer record |
| Teardown / cleanup | Returning resources to a state that does not affect other tests | Deleting test objects or stopping containers |
| Ephemeral environment | Environment existing for a single run | PostgreSQL container managed by Testcontainers |

A fixture does not have to be a static JSON file. It can be a factory generating records per test, a simulated environment, or temporary live resources on Google Cloud. What matters is that the test owns the lifecycle and can be re-run cleanly.

### Ideal Fixture Lifecycle

~~~mermaid
flowchart LR
    A["Create run ID and ownership scope"] --> B["Provision resources"]
    B --> C["Seed controlled data"]
    C --> D["Execute behavior under test"]
    D --> E["Assert results"]
    E --> F["Cleanup in dependency order"]
    F --> G["Verify no temporary resources remain"]
~~~

Cleanup must execute even when assertions fail. Beyond in-place cleanup, you need a fallback sweeper because a process can be killed, a CI machine can lose connectivity, or quotas can abort a test before teardown runs.

## 2. Choosing the Right Testing Tier

Do not use live GCP resources for every test. Different testing tiers carry different costs and fidelity levels.

| Tier | Example | Pros | Limitations |
|---|---|---|---|
| Unit test | JUnit and fake repository | Fast, deterministic, no network needed | Does not verify real APIs or permissions |
| Local integration | Testcontainers with PostgreSQL | Tests realistic SQL, migrations, and transactions | Requires a container runtime |
| Emulator | Firestore or Pub/Sub emulator | Creates no live cloud resources, CI-friendly | Does not emulate every feature, IAM, or production behavior |
| GCP integration | Live Object Storage, Pub/Sub, Firestore in a test project | Tests real APIs, IAM, and quotas | Slower, incurs cost, requires cleanup |
| End-to-end | Cloud Run/GKE with test dependencies | Tests cross-system business journeys | Expensive, sensitive to network and shared state |

A practical strategy keeps most tests at the unit/local level, reserves a small set for real cloud APIs, and runs a focused E2E suite for critical paths. Use emulators to test integration logic, while keeping targeted tests against live services whenever correctness depends on IAM, transactions, indexes, consistency, or runtime configuration.

### Selection Rules

- If you only need to prove data-processing logic is right, use unit tests and factories.
- If you need to verify SQL/migrations, use an appropriate database container.
- If you need to test Pub/Sub or Firestore APIs without verifying IAM, consider an emulator.
- If you need to test service accounts, networking, or live GCP behaviors, run integration tests in a dedicated test project.
- If you need to verify the full user → API → queue → database journey, use E2E with bounded scope and clear recovery.

Never treat an emulator as sufficient proof of IAM policies or production load capacity; fidelity varies by emulator.

## 3. Five Properties of a Good Fixture

**Deterministic:** identical inputs and preconditions yield the same expected outcomes. Use fixed timestamps and explicit payload contents rather than depending on the current date or pre-existing records.

**Isolated:** one test never reads or deletes another test's data. Use separate databases/schemas, namespaced IDs, or unique object prefixes per run.

**Minimal:** create only the records needed to verify the behavior under test. Oversized fixtures slow down tests and obscure failure root causes.

**Repeatable:** tests run reliably across laptops, CI runners, and test environments; prior data never causes collisions.

**Clear lifecycle:** resources are tracked upon creation, have an explicit owner, clean up in `finally`/`AfterEach`, and have a fallback reaper.

An important distinction: **fixture contents should be deterministic**, while **resource names must be unique** so concurrent runners do not collide. For example, an order always has three items with known prices, while the Cloud Storage object key embeds a random run ID or CI job ID.

## 4. Designing Test Data Independent of Production

Never casually copy real customer data into test environments. Test data should be synthetically generated, small, structurally aligned with domain rules, and free of sensitive data.

| Data Type | Good Example | Avoid |
|---|---|---|
| User | `test-user-001@example.invalid` | Real customer emails/phone numbers |
| Order | `order-001`, fixed quantities | Live IDs or payloads from production |
| Time | Fixed `2026-01-15T10:00:00Z` | `Instant.now()` inside time-sensitive assertions |
| Token | Dummy token for fake gateway | Production API tokens |
| Files | Small test-generated JSON | Files containing sensitive internal data |
| Errors | Simulated error codes from fakes | Triggering faults on production services |

### Using a Fixed `Clock`

Java provides `Clock` to substitute system time in tests. Example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public final class TestClocks {
    public static final Clock FIXED = Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC);

    private TestClocks() {
    }
}
~~~

Business code should accept `Clock` via constructor or bean injection. In production, use `Clock.systemUTC()`; in tests, use `TestClocks.FIXED`. That ensures expiration math, order timestamps, and time windows never depend on CI runner speed.

### Using Factories for Meaningful Data

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;

public record OrderFixture(
        String orderId,
        String customerId,
        BigDecimal total,
        String status,
        Instant createdAt) {
}

public final class OrderFixtures {
    private OrderFixtures() {
    }

    public static OrderFixture pending(
            String orderId,
            Clock clock) {
        return new OrderFixture(
                orderId,
                "test-customer-001",
                new BigDecimal("125000.00"),
                "PENDING",
                Instant.now(clock));
    }
}
~~~

Tests can call `OrderFixtures.pending("order-001", TestClocks.FIXED)`. When a new scenario arises, add a descriptive factory method or parameter such as `expiredOrder` or `paidOrder` instead of copying large JSON files and hand-editing them.

### Boundary Data

Do not test only the happy path. An effective fixture set covers:

- Empty orders and moderately large orders.
- Null fields, Unicode strings, special characters, and length boundaries.
- Duplicate key records or redelivered messages.
- Timestamps immediately before and after expiration boundaries.
- Pagination with datasets one element larger than page size.
- Dependencies returning timeouts or retryable errors via fakes/stubs.

Each fixture should make clear why it exists and which assertion verifies that behavior.

## 5. Naming, Labeling, and Assigning Ownership to Test Resources

In a GCP project used for integration testing, **never clean up by generic service name or delete every resource in the project**. Every run must own a distinct namespace and each resource must carry ownership metadata.

Example namespace:

~~~text
it/orders-api/run-6241/test-create-order/
~~~

With Cloud Storage, objects can be created under:

~~~text
it/orders-api/run-6241/test-create-order/input.json
~~~

Some GCP resources impose length and character constraints on names. Generate short run IDs with valid characters and obey each service's naming rules. Never embed long Git branch names or user data directly into resource names.

### Recommended Metadata

| Field | Purpose |
|---|---|
| `run_id` | Groups resources belonging to one CI/test execution |
| `test_id` | Links a resource to a specific test case |
| `owner` | Responsible team or service |
| `created_at` | Helps identify expired resources |
| `expires_at` | Suggested expiration timestamp for sweepers |
| `environment` | Distinguishes test, staging, and production |

Attach labels where the service supports them; when resource-level labels are unavailable, record the mapping in a run fixture registry or appropriate metadata store. Labels and `expires_at` are **discovery metadata**, not automatic deletion triggers. Actual expiration requires lifecycle policies, service TTL features, or a dedicated cleanup job.

### Safety Rules

1. Create/delete resources only in projects or tenants approved for integration tests.
2. Validate the project ID and environment markers before provisioning or cleanup.
3. Generate unique IDs per run and track explicit ownership per resource.
4. Never let cleanup delete shared buckets, databases, topics, or namespaces just because fixtures live inside them.
5. Scope IAM so CI operates only on required resources where the service supports it.
6. Never delete resources using overly broad prefixes such as `prod/`, `orders/`, or an empty string.

## 6. JUnit 5: Controlled Setup and Teardown

JUnit 5 provides callbacks including `BeforeEach`, `AfterEach`, `BeforeAll`, and `AfterAll`. Choose the right fixture scope:

| Scope | When to Use | Note |
|---|---|---|
| Per test | Tests mutating state | High isolation, higher setup cost |
| Per class | Shared container/database across test methods | Must clean up data between methods |
| Per test suite/run | Shared emulators or integration environments | Needs isolated namespaces and concurrency control |

`AfterEach` normally runs after a test even when an assertion fails. However, callbacks do not run when a process is killed or a CI runner drops offline. Therefore, pipelines managing cloud resources need both in-place cleanup and a fallback sweeper.

### Cleaning Up Immediately in `finally`

When a test creates a temporary resource via an API:

~~~java
String resourceId = createTestResource();
try {
    assertExpectedBehavior(resourceId);
} finally {
    deleteTestResource(resourceId);
}
~~~

`finally` executes cleanup when a test throws standard exceptions. If cleanup also throws, it risks masking the original test failure; when managing multiple resources, a fixture scope helper can collect failures and use `try-with-resources` to attach cleanup errors as suppressed exceptions.

### Managing Multiple Cleanup Actions in Reverse Order

Standalone Java example with no Google Cloud SDK dependency:

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public final class FixtureScope implements AutoCloseable {
    private final Deque<AutoCloseable> cleanup = new ArrayDeque<>();

    public void register(AutoCloseable action) {
        cleanup.push(action);
    }

    @Override
    public void close() throws Exception {
        Exception first = null;
        while (!cleanup.isEmpty()) {
            try {
                cleanup.pop().close();
            } catch (Exception error) {
                if (first == null) {
                    first = error;
                } else {
                    first.addSuppressed(error);
                }
            }
        }
        if (first != null) {
            throw first;
        }
    }
}
~~~

Cleanup actions execute in LIFO order: resources created last are cleaned up first. This fits cases where a subscription depends on a topic, or child records depend on parent records. In a test:

~~~java
try (FixtureScope fixtures = new FixtureScope()) {
    String topicId = createTopicForTest();
    fixtures.register(() -> deleteTopicIfExists(topicId));

    String subscriptionId = createSubscriptionForTest(topicId);
    fixtures.register(() -> deleteSubscriptionIfExists(subscriptionId));

    // Run assertions against the newly created topic and subscription.
    assertMessagingBehavior(subscriptionId);
}
~~~

The two `delete...IfExists` helpers are placeholders to implement against the service SDK. They should treat a missing resource as a valid cleanup outcome. If creation fails before registering cleanup, check whether the resource was partially created; over networks, a request timeout does not guarantee the server failed to create the resource.

For resources that can be created with client-assigned IDs, you can register cleanup for the known ID **before** calling create if `deleteIfExists` is safe. That reduces resource leaks when creation succeeds on the server but the response is lost.

## 7. Java/Spring Example: PostgreSQL Fixture with Testcontainers

Testcontainers runs real PostgreSQL inside a container and manages the test container lifecycle automatically. It is well suited for testing SQL, transactions, schema migrations, or JPA mappings without hitting a shared GCP database.

Add the appropriate dependencies in Maven test scope, such as JUnit Jupiter, Testcontainers JUnit Jupiter, and the PostgreSQL module. Manage versions with a project-compatible Testcontainers BOM. The application also needs the PostgreSQL JDBC driver and Spring JDBC or Spring Data JPA as chosen.

### Launching the Database Container and Wiring Spring

~~~java
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class OrderDatabaseFixtureTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16.4")
                    .withDatabaseName("orders_it")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    private String runId;
    private String orderId;

    @BeforeEach
    void seedOrder() {
        runId = "it-" + UUID.randomUUID();
        orderId = runId + "-order";

        jdbc.update(
                "INSERT INTO orders (id, status, test_run_id) "
                        + "VALUES (?, ?, ?)",
                orderId, "PENDING", runId);
    }

    @Test
    void fixtureIsAvailableToTheTest() {
        String status = jdbc.queryForObject(
                "SELECT status FROM orders WHERE id = ?",
                String.class,
                orderId);
        assertEquals("PENDING", status);
    }

    @AfterEach
    void removeSeedData() {
        if (runId != null) {
            jdbc.update(
                    "DELETE FROM orders WHERE test_run_id = ?",
                    runId);
        }
    }
}
~~~

This example assumes project migrations created the `orders` table with columns `id`, `status`, and `test_run_id`. Testcontainers only supplies PostgreSQL; schemas must still be created by Flyway, Liquibase, or appropriate test schema initialization. Test passwords in the example apply only to ephemeral local/CI containers, **never production credentials**.

Key notes:

1. The container is shared per class to cut startup time; per-method data still uses a distinct `runId`.
2. `DynamicPropertySource` injects the JDBC URL and credentials into Spring before creating the `DataSource`.
3. `BeforeEach` seeds the exact record needed; `AfterEach` deletes records matching `test_run_id`.
4. With foreign keys, cleanup must delete child rows before parent rows or use an appropriate transaction.
5. In real applications, invoke the business repository/service and assert database state rather than only verifying the row just inserted.

### Can `@Transactional` Handle Rollback?

In Spring Test, a test method running inside a framework-managed transaction rolls back upon completion. This works well when every operation under test executes within the test's transaction context.

However, test rollback **does not undo** work performed by an HTTP server in another thread/process, a message consumer, a scheduler, or services outside the database. Therefore, integration/E2E tests involving async tasks must still use run IDs and explicit cleanup. Never assume `@Transactional` cleans up Cloud Storage objects, Pub/Sub messages, or cross-system side effects.

### Reusing Containers

Testcontainers supports reusing containers across runs when explicitly configured. While this speeds up iteration, it retains state and data. For CI pipelines requiring strict independence, prefer ephemeral containers tied to the test run, and enable reuse only with an explicit data-reset strategy.

## 8. Emulators: Fixtures Without Live GCP Resources

Google Cloud provides emulators for certain services such as Firestore and Pub/Sub. They suit testing integration logic and data pipelines without provisioning live resources.

### Firestore Emulator

Example launching the emulator in a development environment with Google Cloud CLI:

~~~bash
gcloud beta emulators firestore start \
  --host-port=127.0.0.1:8081
~~~

In another terminal, export environment variables for the test process:

~~~bash
export FIRESTORE_EMULATOR_HOST="127.0.0.1:8081"
export GOOGLE_CLOUD_PROJECT="demo-orders-test"
~~~

The Google Cloud Firestore Java client supports connecting to the emulator via library configuration. Verify your client version and test environment to ensure requests hit the emulator rather than accidentally targeting production. Use a dummy or dedicated test project ID; never use a production project for local tests.

Fixtures can write documents inside a run-scoped collection:

~~~text
test-runs/run-6241/orders/order-001
~~~

After tests, delete created documents. Firestore does not automatically delete subcollections when deleting a parent document. If fixtures create nested documents, cleanup must traverse or record child paths and delete them properly.

### Pub/Sub Emulator

~~~bash
gcloud beta emulators pubsub start \
  --project="demo-orders-test" \
  --host-port=127.0.0.1:8085
~~~

In the test process:

~~~bash
export PUBSUB_EMULATOR_HOST="127.0.0.1:8085"
export PUBSUB_PROJECT_ID="demo-orders-test"
~~~

Depending on the Java client library, you must configure the emulator channel and a credentials provider that avoids live cloud credentials. Never assume every library or Spring framework automatically detects the emulator solely from environment variables; verify connection, port, and client injection.

A Pub/Sub fixture can create a topic and subscription with a unique run ID, publish a message, and assert consumer handling. On cleanup:

1. Stop the publisher and subscriber, waiting up to a deadline for in-flight work.
2. Delete the test-created subscription.
3. Delete the test-created topic.
4. Ensure clients and channels are closed.

Never use production topics or subscriptions in emulator tests. Emulators also do not replicate full IAM, quotas, retention, or live Pub/Sub timing behaviors; those cases require dedicated integration tests on GCP.

## 9. Integration Fixtures on Real Cloud Storage

Some tests must verify real IAM, SDK behavior, and object metadata. In those cases, use a **pre-provisioned managed test bucket** while each test writes objects under a unique prefix. This is usually safer and faster than creating and deleting a new bucket per test.

### Pre-Run Rules

- Use a project/bucket dedicated to integration tests whose name is in CI's allowlist.
- Use a service account permitted only to create/read/delete objects within the allowed test scope.
- Never use buckets holding business data or production backups.
- Assign each run a unique prefix, e.g., `integration/orders-api/ci-6241/`.
- Cleanup may delete only objects it created; never delete the bucket.
- Record object names and generations for exact cleanup.

### Java SDK: Creating and Deleting Exact Objects

Example using JUnit 5 and the Google Cloud Storage client library. The test runs only when `RUN_GCP_IT` is explicitly enabled and `GCP_IT_PROJECT`/`GCP_IT_BUCKET` are set:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@EnabledIfEnvironmentVariable(
        named = "RUN_GCP_IT",
        matches = "true")
class CloudStorageFixtureTest {

    @Test
    void readsTheObjectCreatedByThisTest() {
        String projectId = requiredEnv("GCP_IT_PROJECT");
        String bucket = requiredEnv("GCP_IT_BUCKET");
        String runId = UUID.randomUUID().toString();
        String objectName =
                "integration/orders-api/" + runId + "/input.json";

        Storage storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .build()
                .getService();

        byte[] payload = "{\"orderId\":\"order-001\"}"
                .getBytes(StandardCharsets.UTF_8);
        BlobId plannedId = BlobId.of(bucket, objectName);
        Blob created = null;

        try {
            created = storage.create(
                    BlobInfo.newBuilder(plannedId)
                            .setContentType("application/json")
                            .build(),
                    payload);

            Blob loaded = storage.get(created.getBlobId());
            assertNotNull(loaded);
            assertArrayEquals(payload, loaded.getContent());
        } finally {
            if (created != null) {
                // BlobId contains the generation of the newly created object.
                storage.delete(created.getBlobId());
            }
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required test configuration: " + name);
        }
        return value;
    }
}
~~~

Crucially, the test writes the object under a unique prefix, uses the created object's `BlobId`, and never deletes the bucket. Including the generation in `BlobId` targets the exact object generation under versioning or concurrent overwrites. If creation succeeds on the server but the response times out, `created` may remain `null` and in-place cleanup will lack the generation; a fallback sweeper reclaims objects under the run prefix after expiration.

The sample verifies basic create/read/delete mechanics. In real application tests, replace direct creation with calling the application's upload API, then assert the object lands in the test bucket; cleanup still keys off controlled run IDs, object IDs, or metadata.

### When a Test Creates Multiple Objects

Record each created object in a fixture registry and delete them individually in `finally`/`AfterEach`. Listing by prefix is acceptable only when the prefix **belongs exclusively to the current run and is non-empty**. On versioned buckets, account for noncurrent versions if test policy requires full removal; version-deletion permissions and mechanisms must be tightly controlled.

Never run a generic script that lists and deletes every object in a bucket merely because its name includes "test." Multiple pipelines or teams may share that test bucket concurrently.

## 10. Service-Specific Cleanup Across GCP

No single generic deletion strategy is safe for every GCP service. Cleanup must respect dependency order, access controls, and each resource type's deletion semantics.

| Service | Typical Fixtures | Cleanup Strategy | Notes |
|---|---|---|---|
| Cloud Storage | Objects in test bucket | Delete exact object/generation or run prefix | Never delete a shared bucket |
| Pub/Sub | Topics, subscriptions, messages | Stop subscriber, delete subscription then test topic | Never delete a shared topic |
| Firestore | Documents in test collections | Delete recorded documents/subcollections | Deleting parent does not auto-delete subcollections |
| Bigtable | Rows with unique prefix | Delete exact rows matching test prefix | Never delete shared tables/instances |
| Spanner | Records in test database | Transactionally delete by key/test ID | Respect foreign keys and transaction limits |
| BigQuery | Temporary datasets/tables or test rows | Use per-run dataset or delete explicit table IDs | Active query jobs and resources may still run |
| Cloud SQL | Test databases/schemas or rows | Rollback or delete by `test_run_id` | Avoid deleting shared instances |
| Cloud Run | Test services/revisions | Delete only services provisioned exclusively for the run | Never touch shared staging/production services |
| GKE | Test Pods/Jobs/namespaces | Delete by name/label in dedicated test namespace | Check owners, finalizers, and `Terminating` state |

For example, if a Pub/Sub test uses a shared topic and creates an ephemeral subscription, cleanup must delete only that subscription; deleting the topic breaks concurrent tests. If a Firestore test creates nested documents and subcollections, track all created paths and clean up child documents rather than only the parent.

### Rules for Dependent Resources

- Delete child resources or consumers before deleting parent resources they depend on.
- Wait for async tasks to finish or cancel within a deadline before deleting upstream sources.
- If a resource is already absent, cleanup should succeed idempotently.
- On permission errors during deletion, raise an alert and preserve resource IDs for a sweeper or operator.
- On shared resources, delete only records tagged with the run ID; never drop baseline infrastructure.
- For sensitive data, never execute bulk delete commands relying on default CLI context alone.

## 11. Reclaiming Resources When Tests or CI Abort

`AfterEach`, `AfterAll`, and `finally` do not run in every failure mode. Runners lose network connectivity, containers get OOM-killed, VMs terminate, or jobs time out. GCP test resources can linger after CI exits. Therefore, reliable cleanup has **two tiers**:

1. **Primary cleanup:** executed immediately by the test on completion or failure.
2. **Fallback cleanup:** an independent job locating and deleting expired test resources with ownership checks.

### Designing a Fallback Sweeper

You can use Cloud Scheduler to trigger a Cloud Run Job or equivalent periodic workflow. The sweeper should:

- Operate only on test projects listed in an explicit allowlist.
- Target only resources marked as automation-created, e.g., `owner=integration-tests` and a specific `run_id`.
- Check `created_at`/`expires_at` or minimum age before deleting.
- Skip runs that are still active or hold a valid lease.
- Log candidate deletions in dry-run mode before enabling live deletion.
- Cap the number of deletions per execution and alert if exceeded.
- Delete in dependency order using bounded retries on transient errors.
- Log resource IDs, types, cleanup outcomes, and skip reasons; never log secrets.
- Retain audit logs and alert when the sweeper encounters permission errors or cannot complete.

Two-tier diagram:

~~~mermaid
flowchart TD
    A["CI runs integration tests"]
    B["Create resources scoped by run_id"]
    C{"Runner still alive?"}
    D["finally / AfterEach cleanup"]
    E["Scheduled sweeper job"]
    F{"Matches project + owner + expired?"}
    G["Delete exact test resource and log audit"]
    H["Skip, retain data for inspection"]
    A --> B --> C
    C -->|"Yes"| D
    C -->|"No"| E
    E --> F
    F -->|"Yes"| G
    F -->|"No"| H
~~~

Labels and TTL metadata do not run a sweeper automatically. When relying on native TTL or lifecycle features, verify scope, actual deletion latency, and impact on shared resources. For instance, a bucket lifecycle rule fits a dedicated test bucket, whereas applying a broad deletion rule to a shared bucket risks wiping other data.

### Using Leases or Run-State Tracking

If an integration test runs long, checking `created_at` alone could cause a sweeper to delete active resources. Store run state with `owner`, `started_at`, `heartbeat_at`, and `expires_at` in a coordination store. When the sweeper runs, it checks whether the run is still active and deletes only once the lease expires, a safety margin passes, and the resource is allowlisted.

When manual override is required, require explicit run IDs and resource lists to prevent accidentally wiping an active suite.

## 12. Idempotent Cleanup, Retries, and Error Handling

Cleanup should be idempotent: calling it repeatedly produces the same safe outcome. If a resource was already deleted by the test or sweeper, a subsequent cleanup pass must not harm unrelated resources.

Example object deletion helper:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public final class StorageCleanup {
    private StorageCleanup() {
    }

    public static void deleteIfExists(
            Storage storage,
            BlobId ownedBlobId) {
        // false means the object is already gone; this is a valid cleanup outcome.
        storage.delete(ownedBlobId);
    }
}
~~~

This helper is safe only if `ownedBlobId` was constructed within test scope and validated prior to invocation. Never let arbitrary user-supplied paths construct a `BlobId` for deletion.

### Error Classification

| Scenario | Handling |
|---|---|
| Resource no longer exists | Treat cleanup as succeeded |
| Transient `429`/quota or `503` | Retry with exponential backoff, jitter, and deadline |
| `403 PermissionDenied` | Stop pointless retries; log missing permission and raise blocker |
| Precondition failed / generation mismatch | Do not delete another generation; log the concurrent change |
| Delete timeout | Query state and retry idempotently if safe |
| Resource currently in use | Stop consumers/jobs, wait up to deadline, and retry appropriately |
| Cleanup raises a new error | Preserve the primary test error and record the cleanup failure |

Avoid infinite retries. If a test completes and cleanup repeatedly hits 403, the problem is IAM or scope, not network latency. Cap retry attempts, log resource IDs, and hand off to fallback remediation.

### Preserving Root Test Failures

When both a test and its cleanup fail, report both events. `try-with-resources` preserves the exception thrown inside the `try` block as the primary failure while attaching `close()` errors as suppressed exceptions. The `FixtureScope` helper shown earlier preserves cleanup failures across multiple resources.

In CI, a cleanup failure may mark a build as failed even when assertions passed if it leaves costly or risky resources behind. Still, reports must clearly separate whether test logic passed/failed and whether cleanup passed/failed rather than lumping them into one vague message.

## 13. Running Parallel Tests Without Collisions

CI commonly runs multiple workers, shards, or pull requests concurrently. Tests writing to the same key such as `test-order-001` will overwrite or delete each other's data.

### Isolation Strategies

- **Per run:** incorporate CI build ID plus retry attempt or UUID across all resources in a run.
- **Per test:** append a test case ID or stable hash to isolate per-method data.
- **Per worker:** include a worker/shard ID if multiple processes generate data within one run.
- **Per resource type:** obey each service's naming constraints rather than cramming every component into a name if length limits apply.
- **Per environment:** keep production, staging, and integration on strictly separate resources.

Example:

~~~text
it/orders-api/run-6241/shard-02/create-order/order-001.json
it/orders-api/run-6241/shard-03/cancel-order/order-001.json
~~~

Two tests can share the same `order-001` payload content while living in separate namespaces. When an API assigns global IDs, factories must generate unique IDs while keeping asserted business fields deterministic.

### Avoid Static Mutable Fixtures

Never let parallel tests mutate a shared stateful singleton or static collection. Use immutable data and per-method factories, or lock resources only when forced to share an un-isolatable system. Locking slows suites down and can mask race conditions, so favor independent fixtures.

### Testing Asynchronous Messages

With Pub/Sub or background workers, tests must not rely on a fixed `Thread.sleep` assuming data is ready. Instead:

1. Publish a message carrying the run's correlation ID.
2. Poll processing state up to an explicit deadline.
3. Assert the exact event/result matching that correlation ID.
4. Stop the consumer or wait for tasks to settle.
5. Clean up message-related resources and test data.

If the deadline expires without meeting the assertion, log logs, request IDs, and resource IDs for investigation. Space out poll intervals sensibly to avoid tight loops that spike load.

## 14. IAM Permissions and Blast-Radius Limits for Fixtures

The CI runtime identity should hold only the permissions needed to create, read, and delete allowed test resources. Keep test and production permissions strictly separate.

Example:

| Component | Permissions to Consider | Boundary |
|---|---|---|
| Object read/write tests | Storage object permissions | Specific test bucket where possible |
| Pub/Sub tests | Topic/subscription permissions | Topics and subscriptions in test project |
| Firestore tests | Appropriate document/database roles | Dedicated test database |
| Cloud Build test runner | Required test API permissions | Dedicated integration service account |
| Cleanup sweeper | List/delete permissions on test resources | Test project and resource allowlist |
| Application runtime | Business access permissions | Never granted arbitrary fixture admin roles |

Never store service account JSON keys in repositories, fixture files, or images. On Cloud Build, Cloud Run, and GKE, prefer workload identities; for external CI outside Google Cloud, use Workload Identity Federation.

Some APIs cannot enforce fine-grained IAM down to an exact object prefix or label in every operation. Whenever IAM cannot be narrowed further, rely on a **dedicated integration-test bucket, database, or project** rather than expecting cleanup code alone to enforce security boundaries.

### Protecting Test Data

- Never place real user data or production credentials in fixtures.
- Set appropriate retention policies so test data never persists indefinitely.
- Encrypt and restrict access per organizational security policies.
- Never print secret payloads in test failure logs or snapshot assertions.
- If production data is ever needed for failure analysis, follow formal approval, anonymization, and data-handling procedures; never auto-copy into test projects.

## 15. Fixtures in CI/CD with Cloud Build

A pipeline can separate unit tests and integration tests into distinct steps. Integration steps activate only when the test project, runner identity, and dependencies are ready.

Illustrative configuration example:

~~~yaml
substitutions:
  _TEST_PROJECT: example-integration-project

steps:
  - id: unit-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test

  - id: cloud-integration-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -ceu
      - |
        export RUN_GCP_IT=true
        export GCP_IT_PROJECT="$_TEST_PROJECT"
        export TEST_RUN_ID="$BUILD_ID"
        mvn -B -Pintegration verify
    waitFor:
      - unit-tests

options:
  logging: CLOUD_LOGGING_ONLY
timeout: 1200s
~~~

This example assumes the project defines the `integration` Maven profile, required libraries, and test bucket configuration. `RUN_GCP_IT` toggles cloud integration tests; `GCP_IT_PROJECT` selects the project; `TEST_RUN_ID` provides namespace isolation and log correlation. Grant the build identity appropriate permissions on the test project. To run the Storage test from earlier, also pass `GCP_IT_BUCKET` via test-environment CI configuration.

In real pipelines, build steps may share a workspace while running in different containers. Ensure test flags and credentials exist only in steps that require them. For E2E tests spinning up ephemeral clusters or services, isolate them in dedicated jobs/stages with explicit timeouts and independent cleanup.

### Behavior When a Test Step Fails

When an assertion fails, JUnit runs `AfterEach` and `try-with-resources`, yet Cloud Build may skip subsequent dependent steps. Never rely on a separate trailing cleanup step after a failing step without verifying pipeline execution semantics.

You can wrap setup/test/cleanup in a single script using `trap` or `finally`, or run an independent sweeper job keyed by run ID. Either way, ensure a fallback covers cases where a process is killed before `trap` executes.

### Capturing Test Artifacts

Retain JUnit/Surefire reports, exit codes, test names, run IDs, resource names, and Logs Explorer links per policy. Avoid capturing sensitive data snapshots in artifacts. When retaining fixtures for debugging, require controlled opt-in, an expiration deadline, and an assigned owner; never retain failed-test resources indefinitely by default.

## 16. Real-World Scenario: Testing an Order-Creation Flow

Suppose an Orders system comprises a Spring Boot API on Cloud Run, PostgreSQL, Pub/Sub, and a worker writing receipts to Cloud Storage. The team needs to verify that a valid order request leads to a published message and a generated receipt file.

### Fixture Design

| Step | Fixture | Ownership | Cleanup |
|---|---|---|---|
| Prepare database | Test customer and product, existing schema | `test_run_id` | Delete order, items, customer in dependency order |
| Message topic | Run-specific topic or shared test topic | Delete only if run-specific | Delete test subscription before topic |
| Create subscription | Subscription embedding run ID | Run-specific subscription | Stop subscriber, delete subscription |
| Storage output | Unique prefix in test bucket | `run_id` and object ID | Delete objects created by the run |
| Business trigger | HTTP request with correlation ID | `run_id` | Wait for side effects to settle |
| Assertions | Order status, event ID, object payload | Creates no extra resources | Not applicable |

If using a shared test topic, tests **should create only a dedicated subscription** to receive messages and filter by the matching correlation ID. However, other system subscribers may also receive messages; understand Pub/Sub fan-out semantics and avoid assuming every message routes exclusively to your test.

### Recommended Workflow

1. Generate a unique run ID and correlation ID.
2. Verify execution targets the test project, not production.
3. Create or select fixtures in the test database; record every ID.
4. Create the test subscription and start the consumer.
5. Send the order-creation HTTP request with synthetic data.
6. Wait up to a deadline to observe the message and object under the unique prefix.
7. Assert the exact customer ID, order total, event type, and required object metadata.
8. Stop the consumer and delete the subscription; then delete the topic if run-owned.
9. Delete objects in the test bucket and database rows matching `test_run_id`.
10. Verify cleanup and record PASS/FAIL status per item.

To prevent flaky tests, assert on observable terminal conditions rather than fixed sleeps. For example, poll until the object appears or 30 seconds elapse, then report a timeout with the correlation ID for diagnosis. Base timeouts on test-environment characteristics rather than arbitrary production assumptions.

### When a Test Fails Mid-Flight

Suppose the API created the order, but the worker failed to generate the receipt. The test fails because no object appears before the deadline. Cleanup must still delete the test subscription and test database records. If logs or traces are needed for investigation, log resource names and correlation IDs in the report; **never keep paid resources alive indefinitely just because a test failed**.

If a cleanup call hits a transient error, retry within a deadline. If it still fails, record the resource in a pending-cleanup list for the sweeper and notify the owning team.

## 17. Common Fixture Design Mistakes

| Practice | Risk | Improvement |
|---|---|---|
| Using the same `orderId` on every run | Key collisions and cross-test interference | Generate unique namespace/run IDs |
| Relying on pre-existing environment data | Tests break whenever shared data changes | Self-seed minimal fixtures |
| Calling production for test data | Data leakage and production impact | Generate synthetic data or use mocks/emulators |
| Sharing one test bucket and wiping it after each test | Deletes another run's data | Delete only objects under exact run prefix |
| Deleting a Firestore parent and assuming it's clean | Subcollections remain behind | Explicitly clean up child documents |
| Cleaning up only in `AfterAll` | Killed runners leave resources behind | Add a fallback sweeper |
| Fixed `Thread.sleep` for async messages | Flaky tests when system slows down | Poll for conditions with a deadline |
| Granting Editor/Owner to CI | Risks mutating non-test resources | Least-privilege IAM and dedicated test project |
| Dumping full fixtures on test failure | Risks exposing tokens or sensitive data | Log IDs and non-sensitive fields |
| Keeping resources indefinitely for debugging | Higher costs and future collisions | Enforce TTL, owner, and resolution deadline |
| Infinite cleanup retries | Hangs CI or amplifies API load | Bounded backoff and clear failure reporting |
| Treating emulators as 100% identical to production | Misses IAM or semantic differences | Maintain integration tests on real services |

## 18. Hands-On Exercise

Design and implement an integration test suite for an **orders-api** application using PostgreSQL and Cloud Storage. The goal is for tests to run concurrently in CI, fail accurately on bugs, and leave no expired cloud data behind.

### Part A: Data and Database

1. Build an `OrderFixtures` factory for `PENDING` and `PAID` states using a fixed `Clock`.
2. Spin up a PostgreSQL container with Testcontainers and wire it via `DynamicPropertySource`.
3. Initialize the test schema using the application's migrations.
4. Seed one customer and one order carrying `test_run_id`.
5. Call the business service to transition order status, then assert the result.
6. Clean up records in proper dependency order.

### Part B: Cloud Storage Integration

1. Provision an approved test bucket or obtain an existing one from your platform team.
2. Use a service account permitted to read/write/delete objects within test scope.
3. Generate a unique prefix `integration/orders-api/RUN_ID/` per run.
4. Upload a small deterministic JSON file and verify its contents and content type.
5. Delete the newly created object using its generation-pinned `BlobId`.
6. Run the test twice and confirm the second run is unaffected by the first.
7. Run two jobs in parallel to verify zero data collisions.

### Part C: Interrupted Cleanup

1. Create a test fixture in the sandbox project carrying `owner`/`run ID`/`createdAt` metadata.
2. Simulate an interrupted runner **in the test environment** before cleanup runs.
3. Run the sweeper in dry-run mode and confirm it lists only resources from the expired run.
4. Verify project allowlist, non-empty prefix check, deletion caps, and lease checks.
5. Enable live cleanup for that scoped run, then verify resources are gone.
6. Save a create/delete resource report with success or error status.

### Completion Criteria

- Test data is synthetic, deterministic, and contains no real credentials.
- Every test and run uses independent resource names.
- Test logic and cleanup each have dedicated assertions or verification evidence.
- Failing tests still trigger in-place cleanup while the runner is alive.
- The sweeper targets only expired test resources and never touches shared infrastructure.
- IAM, deadlines, retries, and deletion caps are verified.
- Sequential runs and parallel runs never interfere with one another.

## 19. Pre-Execution Checklist for GCP Integration Tests

- [ ] Tests use a project and service account dedicated to the test environment.
- [ ] Fixtures create required data themselves without depending on pre-existing records.
- [ ] Data contents are deterministic, with `Clock` controlled where needed.
- [ ] Resource names include a unique run ID/test ID and obey naming rules.
- [ ] Tests never use real user data or production tokens.
- [ ] Teardown lives in appropriate `finally`/`AfterEach`/`try-with-resources` blocks.
- [ ] Cleanup targets only resources or data owned by the test.
- [ ] Cleanup tolerates repeated runs and already-deleted resources.
- [ ] Dependencies are cleaned up in safe reverse order.
- [ ] Cleanup errors never mask primary assertion failures.
- [ ] Async tests use deadline-bounded polling instead of arbitrary sleeps.
- [ ] CI enforces timeouts and runs an orphaned-resource reaper.
- [ ] Sweepers enforce allowlists, owner/age/lease checks, and dry-run capability.
- [ ] IAM permissions for test runners and sweepers follow least privilege.
- [ ] Logs record run IDs/resource IDs without sensitive data.
- [ ] Tests can run repeatedly and concurrently without collisions.
- [ ] Resource creation rates, quotas, and budgets are accounted for.

## Self-Check Questions

**1. How do fixtures differ from seed data?**

A fixture is the full precondition state or resources required for a test; seed data is baseline input data loaded into the system. A fixture can include database containers, mock dependencies, and cleanup mechanisms.

**2. Why should fixture data be deterministic while resource names must be unique?**

Deterministic contents make assertions repeatable and reliable. Unique names keep parallel tests and runners from overwriting or deleting each other's resources.

**3. Does `@AfterEach` guarantee cleaning up all cloud resources?**

No. Callbacks do not execute if the runner is killed or CI loses connectivity. Fallback cleanup such as a controlled sweeper is required.

**4. Why shouldn't you delete a shared bucket or topic after a test?**

Because shared resources may hold data or dependencies for other tests. Cleanup must stay scoped to objects, subscriptions, or records owned by the current run.

**5. When should you use Testcontainers instead of an emulator?**

Testcontainers fits services with real container images such as PostgreSQL when you need to test real database behavior. Emulators fit GCP services providing simulators like Firestore/Pub/Sub when full live cloud semantics are not required.

**6. If you delete a parent Firestore document, do its subcollections disappear automatically?**

No. You must design cleanup for child documents or use recursive deletion scoped to permitted paths.

**7. What should happen if cleanup encounters `403 PermissionDenied`?**

Do not retry indefinitely. Report the permission failure, log the resource ID, and hand off to a sweeper or operator with proper permissions; never grant Owner to the runner as a quick fix.

**8. Why shouldn't integration tests run under the same service account as production runtime?**

Tests need permissions to create and delete test data, whereas production runtimes typically need only operational business permissions. Separating identities lowers the risk of tests mutating production and keeps audit logs clear.

## References

- [JUnit 5 User Guide – Test Lifecycle](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers Java](https://java.testcontainers.org/)
- [Spring Boot Testing – Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Framework – DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Google Cloud Firestore emulator](https://cloud.google.com/firestore/native/docs/emulator)
- [Google Cloud Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Cloud Storage Java client libraries](https://cloud.google.com/storage/docs/reference/libraries)
- [Cloud Storage object versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Cloud Scheduler documentation](https://cloud.google.com/scheduler/docs)
- [IAM best practices](https://cloud.google.com/iam/docs/using-iam-securely)

## Conclusion

Test fixtures give Java applications clear input data and state for repeatable testing. On Google Cloud, fixture design must also cover resource ownership, unique per-run naming, IAM, cost, and cleanup. Testcontainers and emulators enable integration testing without provisioning every cloud resource; behaviors requiring live verification should run in a controlled test project. A dependable suite always combines in-place cleanup, idempotent error handling, and a fallback sweeper for orphaned resources. Together, these mechanisms let teams increase CI/CD cadence while keeping flaky tests, data leaks, and abandoned test resources in check.
