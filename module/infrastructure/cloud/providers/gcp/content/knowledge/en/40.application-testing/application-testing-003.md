# Emulators for Pub/Sub, Firestore, Bigtable, and Spanner

Applications on Google Cloud often emit events via Pub/Sub while persisting data in Firestore, Bigtable, or Spanner. If every test run required connecting to live services, the development team would depend on networking, IAM, quotas, shared resource state, and cost. A test could fail because a project is temporarily unreachable, or worse, write test data into a production environment.

An **emulator** is a process that simulates a subset of a Google Cloud service's APIs and behaviors right on a developer machine or in a CI environment. Emulators for Pub/Sub, Firestore, Bigtable, and Spanner let Java/Spring applications run core integration tests without provisioning real cloud resources. They are especially useful for verifying data mapping, queries, message publishing/consumption, and transaction logic.

An emulator is not a full-fidelity miniature replica of production. Certain limits around IAM, indexes, transactions, performance, quotas, or advanced features are not simulated. Therefore, effective testing usually combines unit tests, emulator integration tests, and a controlled suite against live services.

Within the CLOUD_PROVIDERS_GCP module, this topic connects Java/Spring development with GCP data and messaging services alongside knowledge of projects, IAM, CI/CD, operations, and reliability. This lesson focuses on how to start, connect to, and structure tests across the four emulators, while highlighting behaviors that must still be verified in a live Google Cloud environment.

After this lesson, you will be able to:

- Select the right emulator for a test type and understand each service's limitations.
- Run Pub/Sub, Firestore, Bigtable, and Spanner emulators using the Google Cloud CLI.
- Connect Java Cloud Client Libraries via environment variables or gRPC configuration.
- Seed test data, execute read/write operations, and assert results.
- Design independent, repeatable tests suited to JUnit/Spring Boot.
- Run emulators in Docker or CI while controlling ports, state, and lifecycle.
- Distinguish emulator defects from issues that only occur in production.

## 1. Where Do Emulators Fit in the Testing Strategy?

Three testing levels typically work together:

| Level | Dependencies | Primary Value | Limitations |
|---|---|---|---|
| Unit tests with mocks/fakes | No network or server needed | Fast; tests logic branches and specific error handling | Does not test real client API calls or response decoding |
| Integration tests with emulators | Emulator process on localhost or test network | Tests API interactions and test data close to the real service | Does not guarantee production-like behavior, quotas, or security |
| Integration/E2E on real GCP | Real project, APIs, IAM, network, and resources | Verifies integration, security policies, features, and real limits | Slower, incurs cost, and requires resource management |

Emulators best answer questions such as: does the application create the right document, does the consumer process and acknowledge messages, is the Bigtable row key written properly, and does a Spanner transaction update multiple records as expected. Questions about IAM, real latency, scalability, or production index rules must be verified by other means.

~~~mermaid
flowchart LR
    A[JUnit / Spring test runner] --> B[Application and Cloud Client Libraries]
    B --> P[Pub/Sub emulator]
    B --> F[Firestore emulator]
    B --> T[Bigtable emulator]
    B --> S[Spanner emulator]
    C[CI pipeline] --> A
    D[Real GCP staging] --> E[Test IAM / quota / indexing / performance]
~~~

All emulators run in an environment you manage and never create real projects or billing accounts. Use a test project ID such as `local-demo-project` to namespace resources; this is a logical namespace inside the emulator and does not need to exist on Google Cloud, except where specific CLI or SDK operations note otherwise.

## 2. Quick Comparison of the Four Emulators

| Service | Start Command | Default Endpoint | Environment Variable | Key Note |
|---|---|---|---|---|
| Pub/Sub | gcloud beta emulators pubsub start | Port 8085 (typically IPv6 localhost) | PUBSUB_EMULATOR_HOST | **Java requires explicit gRPC channel and no-credentials configuration in code** |
| Firestore | gcloud emulators firestore start | 127.0.0.1:8080 | FIRESTORE_EMULATOR_HOST | Java server library picks up the environment variable automatically |
| Bigtable | gcloud beta emulators bigtable start | localhost:8086 | BIGTABLE_EMULATOR_HOST | Java client picks it up automatically; no instance/cluster admin API |
| Spanner | gcloud emulators spanner start | gRPC 9010; REST 9020 | SPANNER_EMULATOR_HOST | Java client picks it up automatically; gcloud CLI uses REST endpoint override |

When using the examples below, specify host-port explicitly to avoid port conflicts and make CI wiring predictable. The localhost value is resolved from the application process's perspective. If the application runs in another container, localhost points to the application container itself, not the emulator container.

### Preparing the Environment

You need Google Cloud CLI with permission to install components, a JDK compatible with the emulator versions and Java Cloud Client Libraries in use, and Maven or Gradle to run tests. Newer Firestore emulator versions have specific Java runtime requirements; check Google Cloud CLI release notes and install a supported JDK. Google Cloud CLI provides gcloud commands, while Java apps connect through Cloud Client Libraries.

Example component installation:

~~~bash
gcloud components update
gcloud components install pubsub-emulator
gcloud components install cloud-spanner-emulator
~~~

The Bigtable emulator is usually downloaded on the first `start` invocation if the component is not installed yet. The Firestore emulator ships with an appropriate CLI update. If installing the CLI via a package manager disables `components` commands, follow the installation and update method supported by Google Cloud documentation for that platform.

In your Java project, include dependencies for the services under test:

- Pub/Sub: com.google.cloud:google-cloud-pubsub
- Firestore: com.google.cloud:google-cloud-firestore
- Bigtable: com.google.cloud:google-cloud-bigtable
- Spanner: com.google.cloud:google-cloud-spanner

Use the Google Cloud Libraries BOM to keep library versions aligned, choosing a current version already verified in the project. Do not hard-code an outdated version solely because an emulator happens to run.

## 3. Running the Four Emulators Locally

Open four separate terminals, each keeping one emulator process running.

### Terminal 1: Pub/Sub

~~~bash
gcloud beta emulators pubsub start \
  --project=local-demo-project \
  --host-port=127.0.0.1:8085
~~~

### Terminal 2: Firestore

~~~bash
gcloud emulators firestore start \
  --host-port=127.0.0.1:8080
~~~

### Terminal 3: Bigtable

~~~bash
gcloud beta emulators bigtable start \
  --host-port=127.0.0.1:8086
~~~

### Terminal 4: Spanner

~~~bash
gcloud emulators spanner start
~~~

Spanner listens on gRPC localhost:9010 and REST localhost:9020 by default. These separate ports serve different clients: the Java Cloud Spanner client connects via gRPC 9010, whereas gcloud CLI uses REST endpoint 9020 when configured.

Wait for the log message confirming each emulator is listening before running tests. Stop with Ctrl+C. Most emulator data resides in memory and disappears when the process exits; Pub/Sub also retains resources and messages for the lifetime of the emulator session. Create fixtures at the start of each suite rather than relying on leftover state from prior runs.

### Setting Environment Variables for the Application

On Linux/macOS:

~~~bash
export PUBSUB_EMULATOR_HOST=127.0.0.1:8085
export PUBSUB_PROJECT_ID=local-demo-project
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
export BIGTABLE_EMULATOR_HOST=127.0.0.1:8086
export SPANNER_EMULATOR_HOST=127.0.0.1:9010
~~~

On Windows PowerShell:

~~~powershell
$env:PUBSUB_EMULATOR_HOST = "127.0.0.1:8085"
$env:PUBSUB_PROJECT_ID = "local-demo-project"
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8080"
$env:BIGTABLE_EMULATOR_HOST = "127.0.0.1:8086"
$env:SPANNER_EMULATOR_HOST = "127.0.0.1:9010"
~~~

Environment variables must be present in the Java process environment **before** initializing any Cloud Client Library. When running inside an IDE or Gradle/Maven, configure environment variables on the test runner itself. If tests run inside a Docker container, replace 127.0.0.1 with the emulator service hostname on the shared Docker network.

Do not include `http://` or `https://` in the HOST variables above. Each emulator expects a `host:port` address. Match each variable name to its service; setting `FIRESTORE_EMULATOR_HOST` will not redirect Pub/Sub.

## 4. Pub/Sub Emulator: Testing Publish, Pull, and Ack

Pub/Sub is an asynchronous messaging service. An integration test typically verifies whether the application creates a topic/subscription, publishes a message, receives the message with accurate data in the consumer, and calls acknowledge. You can extend tests to nack, redelivery, ordering keys, filters, or dead-letter topics within the bounds supported by the emulator.

### Java-Specific Note

**The Pub/Sub Java client does not automatically switch to the emulator solely from PUBSUB_EMULATOR_HOST.** You must construct a plaintext gRPC channel to the emulator and supply `NoCredentialsProvider` to test clients. If you omit this configuration, the Java client may attempt to reach the live Pub/Sub endpoint and demand Google Cloud credentials.

Example configuring `TopicAdminClient` and creating a topic:

~~~java
import com.google.api.gax.core.NoCredentialsProvider;
import com.google.api.gax.grpc.GrpcTransportChannel;
import com.google.api.gax.rpc.FixedTransportChannelProvider;
import com.google.api.gax.rpc.TransportChannelProvider;
import com.google.cloud.pubsub.v1.TopicAdminClient;
import com.google.cloud.pubsub.v1.TopicAdminSettings;
import com.google.pubsub.v1.TopicName;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;

String host = System.getenv("PUBSUB_EMULATOR_HOST");
if (host == null || host.isBlank()) {
    throw new IllegalStateException("PUBSUB_EMULATOR_HOST is required for this test");
}

ManagedChannel channel =
    ManagedChannelBuilder.forTarget(host).usePlaintext().build();
try {
    TransportChannelProvider provider =
        FixedTransportChannelProvider.create(
            GrpcTransportChannel.create(channel));

    TopicAdminSettings settings = TopicAdminSettings.newBuilder()
        .setTransportChannelProvider(provider)
        .setCredentialsProvider(NoCredentialsProvider.create())
        .build();

    try (TopicAdminClient topics = TopicAdminClient.create(settings)) {
        TopicName topic = TopicName.of("local-demo-project", "orders-test");
        topics.createTopic(topic);
    }
} finally {
    channel.shutdownNow();
    channel.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

To test publish/subscribe, pass the same `TransportChannelProvider` and `NoCredentialsProvider` when constructing `Publisher`, `Subscriber`, or `SubscriptionAdminClient`. Creating a topic alone does not prove consumer processing succeeds; a complete test must publish a message, receive it, verify the payload, and ack it.

### Recommended Integration Test Scenario

1. Create topic `orders-test` and pull subscription `orders-test-sub` in the emulator.
2. Start the subscriber or invoke the Pull API.
3. Publish a message with a dummy `orderId` and `eventType` `ORDER_CREATED`.
4. Await the message with a bounded timeout.
5. Verify message attributes and payload after deserialization.
6. Acknowledge the message, then assert the application's processed state.
7. Clean up the topic and subscription or terminate the emulator session.

Generate unique IDs per test to prevent name collisions and cross-test interference. Avoid assertions overly sensitive to message delivery speed; use reasonable wait bounds rather than long fixed sleeps in place of completion conditions.

### Key Differences to Remember

The Pub/Sub emulator supports common features such as publish/receive, ordering, replay, filters, and certain retry policies, but does not support IAM operations. Not all schema types and resource updates are supported; some features such as BigQuery subscriptions can be created without actually forwarding messages to BigQuery. Retention in the emulator also differs from the live service.

Push subscriptions can call unencrypted HTTP endpoints locally, whereas production requires HTTPS. Therefore, push emulator tests do not replace verification of authentication, TLS, and real endpoint policies.

## 5. Firestore Emulator: Documents, Queries, and Transactions

The Firestore emulator simulates a document database. It is well suited for testing the Spring Boot repository layer: Java object mapping, document creation, collection queries, field updates, batch writes, and standard transaction logic.

### Automatic Java Connection via Environment Variable

With the Java server client library, when `FIRESTORE_EMULATOR_HOST` is set before client creation, the library automatically connects to the emulator. You can instantiate a Firestore client using a test project ID:

~~~java
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;

try (Firestore firestore = FirestoreOptions.newBuilder()
        .setProjectId("local-demo-project")
        .build()
        .getService()) {

    DocumentReference order = firestore
        .collection("orders")
        .document("order-001");

    order.set(Map.of("status", "CREATED", "total", 1250)).get();

    DocumentSnapshot snapshot = order.get().get();
    if (!snapshot.exists()) {
        throw new AssertionError("Order document is missing");
    }
    if (!"CREATED".equals(snapshot.getString("status"))) {
        throw new AssertionError("Unexpected order status");
    }
}
~~~

This serves as a smoke test for the client and repository; in actual JUnit tests, use JUnit/AssertJ assertions rather than manually throwing `AssertionError`.

### Isolating Data

Because data lives in emulator memory, tests run fast without production quota limits. However, if multiple tests share the same emulator process and collection, data from an earlier test remains visible to later tests.

Ways to isolate:

- Use a unique collection prefix or document ID per test.
- Delete created fixtures in `afterEach`/`afterAll`.
- Run a dedicated emulator per test suite when stronger isolation is required.
- Never rely on test execution order or data from another suite.

### Notable Limitations

- The emulator does not enforce composite indexes like production. A query that passes locally may require creating a composite index in live environments.
- Transactions do not fully emulate production concurrency modes, locking, and timeouts; contending writes to the same document may block longer.
- Certain size or resource limits are not enforced identically to the live service.
- Some features, such as the `search(...)` text search stage, may not be supported yet.

Include a test step against real Firestore to verify indexes, security rules or IAM appropriate to your client type, transaction contention, and product limits.

## 6. Bigtable Emulator: Row Keys, Column Families, and Filters

Bigtable is a wide-column database suited for high-throughput workloads, structured row keys, and key/range queries. The emulator lets you test table schemas, row-key encoding, cell writes, row reads, and filters without provisioning a live Bigtable instance.

### Initializing Tables and Column Families

The Bigtable emulator **does not support instance and cluster administration APIs**; you do not create a real instance in a project. You can still use dummy project and instance names to create tables and read/write data with the client library.

Java example:

~~~java
import com.google.cloud.bigtable.admin.v2.BigtableTableAdminClient;
import com.google.cloud.bigtable.admin.v2.BigtableTableAdminSettings;
import com.google.cloud.bigtable.admin.v2.models.CreateTableRequest;

BigtableTableAdminSettings adminSettings =
    BigtableTableAdminSettings.newBuilder()
        .setProjectId("local-demo-project")
        .setInstanceId("local-instance")
        .build();

try (BigtableTableAdminClient admin =
         BigtableTableAdminClient.create(adminSettings)) {
    if (!admin.exists("order-events")) {
        admin.createTable(
            CreateTableRequest.of("order-events").addFamily("event"));
    }
}
~~~

`BIGTABLE_EMULATOR_HOST` is automatically detected by the Java Cloud Bigtable client. No service account or live cloud instance is required for this emulator example.

### Writing and Reading a Row

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;
import com.google.cloud.bigtable.data.v2.models.Row;
import com.google.cloud.bigtable.data.v2.models.RowMutation;

BigtableDataSettings dataSettings = BigtableDataSettings.newBuilder()
    .setProjectId("local-demo-project")
    .setInstanceId("local-instance")
    .build();

try (BigtableDataClient data = BigtableDataClient.create(dataSettings)) {
    RowMutation mutation = RowMutation.create("order-events", "order#001")
        .setCell("event", "type", "ORDER_CREATED");

    data.mutateRow(mutation);
    Row row = data.readRow("order-events", "order#001");
    if (row == null) {
        throw new AssertionError("Missing Bigtable row");
    }
}
~~~

In real tests, assert cell values and timestamps if the application depends on them. Also verify how row keys are structured because row-key design governs range scans and directly impacts production performance.

### Notable Limitations

- The emulator is in-memory and does not persist data across restarts.
- Creating or managing instances and clusters is not supported.
- It does not use TLS-secured connections like the live service.
- Many common filters are supported, but some filters such as the Sink limiting filter are unsupported.
- It does not accurately reflect production latency, partitioning, throughput, replication, or cost.

Do not use the Bigtable emulator for performance benchmarks or capacity testing. Those checks must use representative workloads against real Bigtable with an appropriately sized instance/cluster configuration.

## 7. Spanner Emulator: Schema, SQL, and Transactions

Spanner provides SQL, transactions, and scalability for relational workloads. The emulator supports functional testing of GoogleSQL or PostgreSQL dialect queries, data mutations, and transactions.

### Two Endpoints of the Spanner Emulator

- `localhost:9010`: gRPC endpoint for the Java Cloud Spanner client.
- `localhost:9020`: REST endpoint for gcloud CLI and REST clients.

Set `SPANNER_EMULATOR_HOST=127.0.0.1:9010` for the Java process. The Cloud Spanner Java client automatically uses the emulator when this variable is set.

### Creating a Separate gcloud Configuration for the Spanner Emulator

If you want to run gcloud spanner commands against the emulator, create a dedicated configuration to avoid sending commands to a real project:

~~~bash
gcloud config configurations create spanner-local
gcloud config set auth/disable_credentials true
gcloud config set project local-demo-project
gcloud config set api_endpoint_overrides/spanner http://localhost:9020/
~~~

Then create an instance and database inside the emulator:

~~~bash
gcloud spanner instances create local-instance \
  --config=emulator-config \
  --description="Local integration test" \
  --nodes=1

gcloud spanner databases create local-db \
  --instance=local-instance \
  --ddl="CREATE TABLE Orders (Id STRING(36) NOT NULL, Status STRING(20)) PRIMARY KEY (Id)"
~~~

These resources live inside the Spanner emulator. Under any other gcloud configuration (especially `default`), the same commands may affect live services. After testing, switch back to your normal configuration via `gcloud config configurations activate default` if that was your active configuration beforehand.

### Connecting with the Java Cloud Spanner Client

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Mutation;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;
import java.util.List;

try (Spanner spanner = SpannerOptions.newBuilder()
        .setProjectId("local-demo-project")
        .build()
        .getService()) {

    DatabaseId databaseId =
        DatabaseId.of("local-demo-project", "local-instance", "local-db");
    DatabaseClient database = spanner.getDatabaseClient(databaseId);

    database.write(List.of(
        Mutation.newInsertBuilder("Orders")
            .set("Id").to("order-001")
            .set("Status").to("CREATED")
            .build()));

    try (ResultSet results = database.singleUse()
            .executeQuery(Statement.of(
                "SELECT Status FROM Orders WHERE Id = 'order-001'"))) {
        if (!results.next()
                || !"CREATED".equals(results.getString("Status"))) {
            throw new AssertionError("Unexpected Spanner result");
        }
    }
}
~~~

This example assumes the GoogleSQL DDL was applied via gcloud in the preceding step. For the PostgreSQL dialect, DDL syntax and some SQL constructs differ; choose the target dialect upfront and test against the application contract.

### Major Differences from Production

- The emulator does not support TLS/HTTPS, authentication, IAM, permissions, or roles.
- There is no audit logging or monitoring like the live service.
- Query `PLAN`/`PROFILE` returns empty plans; `ANALYZE` is accepted without performing real analysis.
- Read-write transactions and schema changes lock the entire database, differing from production concurrency control.
- Partitioned DML or `partitionQuery` may succeed in the emulator even when rejected on the live service as non-partitionable.
- It does not reflect real throughput, latency, or scalability.

Thus, the emulator is suited for query correctness and basic transaction logic; do not rely on it to validate isolation/contention, query plans, the optimizer, IAM, or production Spanner reliability.

## 8. Designing Integration Tests with Java, JUnit, and Spring Boot

### Separating Environment Configuration

A key principle is that tests must enable emulators explicitly. You can use a `test-emulator` Spring profile and require the environment variables to be present before creating beans:

~~~java
import java.util.Map;

class EmulatorEnvironment {
    static void verifyRequiredHosts() {
        for (String name : new String[] {
                "PUBSUB_EMULATOR_HOST",
                "FIRESTORE_EMULATOR_HOST",
                "BIGTABLE_EMULATOR_HOST",
                "SPANNER_EMULATOR_HOST"
        }) {
            if (System.getenv(name) == null || System.getenv(name).isBlank()) {
                throw new IllegalStateException(
                    "Emulator environment is missing: " + name);
            }
        }
    }
}
~~~

For tests using only one or two services, validate only those services' variables. With Spring Boot, place the check in test setup or a bean scoped to the `test-emulator` profile. Never use emulator defaults inside the production profile.

### Fixtures and Lifecycle

A test suite can:

1. Wait for the emulator to become ready.
2. Create topics/subscriptions, collections/documents, Bigtable tables, or Spanner schemas.
3. Assign unique test IDs and insert fixture data.
4. Boot the Spring application with the emulator environment variables.
5. Invoke the use case and assert output data.
6. Clean up fixtures and close clients.
7. Stop the emulator once the entire suite completes.

JUnit 5 example for a Firestore repository:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import java.util.Map;
import org.junit.jupiter.api.Test;

class OrderRepositoryIntegrationTest {

    @Test
    void canPersistAndLoadOrder() throws Exception {
        String host = System.getenv("FIRESTORE_EMULATOR_HOST");
        assertTrue(host != null && !host.isBlank(),
            "This test must use Firestore emulator");

        try (Firestore db = FirestoreOptions.newBuilder()
                .setProjectId("local-demo-project")
                .build()
                .getService()) {
            String id = "order-" + java.util.UUID.randomUUID();
            DocumentReference ref = db.collection("orders").document(id);
            ref.set(Map.of("status", "CREATED")).get();
            DocumentSnapshot saved = ref.get().get();

            assertTrue(saved.exists());
            assertEquals("CREATED", saved.getString("status"));
            ref.delete().get();
        }
    }
}
~~~

This test still requires a running Firestore emulator at `FIRESTORE_EMULATOR_HOST`. In CI, place emulator startup and readiness waiting ahead of the test execution step.

### Testing Behavior Instead of Implementation

Assert business-meaningful outcomes: number of messages processed, document persisted accurately, row key written, transaction updating expected records. Avoid tests that merely assert client methods were invoked, since mocks do that better without needing an emulator.

### Timeouts and Stability

Emulators still communicate over local networking; a freshly launched process may not be ready immediately. Use a readiness check with a finite timeout. For asynchronous messages, wait on conditions via short bounded polling with a deadline instead of sleeping a fixed number of seconds for every test.

When running tests in parallel, give each test its own namespace or give each worker its own emulator. Shared data and fixed ports are frequent sources of flaky tests.

## 9. Docker and CI Pipelines

Emulators can run directly on the host, inside Docker, or as CI service containers. Containers provide consistent environments that can be spun up fresh and torn down after every job. However, network configuration must be exact.

### When the Application and Emulator Share a Container or Host

Use `127.0.0.1:PORT` if the application shares the network namespace with the emulator. If the application runs in a separate container, use the service hostname, such as `pubsub:8085` or `firestore:8080`. A `PUBSUB_EMULATOR_HOST` pointing to localhost inside the application container causes connection refused if Pub/Sub runs in a different container.

### Conceptual Docker Compose Example

~~~yaml
services:
  pubsub:
    image: gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators
    command:
      - gcloud
      - beta
      - emulators
      - pubsub
      - start
      - --project=local-demo-project
      - --host-port=0.0.0.0:8085
    ports:
      - "127.0.0.1:8085:8085"

  firestore:
    image: gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators
    command:
      - gcloud
      - emulators
      - firestore
      - start
      - --host-port=0.0.0.0:8080
    ports:
      - "127.0.0.1:8080:8080"
~~~

This example illustrates two services; verify image tags and bundled emulator components at implementation time. Other emulators may require separate images or extra component installations. Never assume a running container means the service is ready; add an appropriate health/readiness check before running tests.

When Java tests run inside the same Compose network, configure:

~~~text
PUBSUB_EMULATOR_HOST=pubsub:8085
FIRESTORE_EMULATOR_HOST=firestore:8080
~~~

If tests run on the host, use `127.0.0.1:8085` and `127.0.0.1:8080` as published ports.

### How CI Runs Emulators

A CI job typically includes these steps:

1. Install the JDK, Java build tool, and emulator binaries, or start service containers.
2. Start emulators on dedicated ports exposed only within the test network.
3. Wait for readiness by checking port/API responses.
4. Export environment variables for the test runner.
5. Create fixtures using client libraries.
6. Run integration tests.
7. Collect emulator logs and test reports on failure.
8. Stop processes/containers and delete temporary test resources and credentials.

Never place production service account credentials in CI jobs that only run emulators. Emulators need no access to production projects for local checks. If the same job also runs staging tests, keep profiles, environment variables, and identities strictly separated.

## 10. Distinguishing Emulators from Staging Environments

Do not use emulators to conclude an application satisfies every GCP rule. The table below suggests where to test each concern:

| Scenario | Emulator | Real GCP Staging |
|---|---|---|
| Data mapping, encode/decode | Suitable | Optional supplemental check |
| Basic publish/subscribe and message handling | Suitable | Verifies delivery, IAM, and quotas |
| Firestore query and transaction logic | Suitable | Verifies composite indexes, security/IAM, transaction limits |
| Bigtable row keys, cells, and standard filters | Suitable | Verifies performance, cluster replication, quotas, IAM |
| Spanner SQL and functional transactions | Suitable | Verifies query plans, concurrency, IAM, latency |
| Service accounts, IAM, VPC, firewalls | Cannot verify | Mandatory |
| Load testing and capacity planning | Unsuitable | Mandatory on a representative-scale environment |
| Operating cost | Does not reflect | Estimate and verify on GCP |

A balanced pipeline can run unit tests and emulator tests on every pull request, and run staging tests for new features, schema changes, or significant integration updates. For sensitive systems, add contract tests and failure-mode tests against live services.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Java Pub/Sub client still asks for credentials | Set PUBSUB_EMULATOR_HOST without configuring channel/NoCredentialsProvider | Use FixedTransportChannelProvider, plaintext gRPC, and NoCredentialsProvider |
| Connection refused on localhost | Emulator not running, wrong port, or Java in a different container | Check process, port, Docker hostname, and readiness |
| Tests accidentally hit real Google Cloud | Environment variable not passed to runner or wrong test profile | Fail fast when variable is missing; inspect endpoint, isolate prod config |
| Firestore tests pass locally but fail in prod for missing index | Emulator does not track composite indexes like production | Add staging tests and manage index definitions |
| Firestore transactions stall for a long time | Coarse emulator locking | Reduce contention in tests or adjust local deadlines |
| Bigtable reports instance creation unsupported | Emulator only implements table/data APIs | Use dummy instance ID; create tables and column families directly |
| Bigtable tests lose data after restart | Data stored in memory | Recreate fixtures on each suite run |
| Spanner Java connection to port 9020 fails | Using REST port for gRPC client | Point SPANNER_EMULATOR_HOST to 9010 |
| Spanner gcloud commands affect real project | Endpoint not overridden or wrong active gcloud configuration | Create an isolated emulator configuration and check active config |
| Tests pass locally but fail IAM/TLS on deploy | Emulator skips full security enforcement | Run staging tests with real IAM and endpoints |
| Parallel tests fail with duplicate data errors | Shared project ID, table, topic, or document ID | Use unique namespaces, cleanup, or per-worker emulators |

## 12. Comprehensive Hands-On Exercise

Suppose a Spring application processes orders using an event-driven architecture:

1. The API receives an order and writes it to Firestore or Spanner.
2. The application emits `ORDER_CREATED` to Pub/Sub.
3. A consumer reads the message and writes an event-log row into Bigtable.
4. An endpoint checks order status.

Integration test scenario using all four emulators:

- Create the database/table/topic/subscription before running tests.
- Submit an order-creation request with synthetic data and an idempotency key.
- Verify the order is written accurately to Firestore or Spanner.
- Wait with a timeout for the Pub/Sub consumer to process the message.
- Verify the corresponding row appears in Bigtable.
- Resubmit the same idempotency key and ensure no duplicate business record is created.
- Test retries or redelivery by making the consumer fail once in a controlled manner.
- Clean up fixtures so other tests remain independent.

This validates the **functional flow**. After passing, you still need staging tests to verify service account IAM, Pub/Sub quotas, Firestore indexing, Bigtable performance, and Spanner transaction behavior under real load.

## 13. Pre-CI Checklist for Emulator Tests

- [ ] Selected emulators match target services and required CLI/Java versions are verified.
- [ ] Ports are explicitly configured without colliding with other services.
- [ ] Java test runner receives the proper `EMULATOR_HOST` variables.
- [ ] Pub/Sub Java client uses an explicit gRPC channel and `NoCredentialsProvider`.
- [ ] Firestore, Bigtable, and Spanner clients are initialized after setting environment variables.
- [ ] Tests never load production credentials or hit production endpoints.
- [ ] Readiness checks and reasonable timeouts run before tests execute.
- [ ] Fixtures are explicitly created and cleaned up; tests are order-independent.
- [ ] Parallel tests use separate namespaces or dedicated emulators.
- [ ] Assertions cover data and business side effects sufficiently.
- [ ] Logs and test reports are captured for failure investigation.
- [ ] Features missing from emulators have supplemental tests in staging.

## 14. Conclusion

The Pub/Sub, Firestore, Bigtable, and Spanner emulators make GCP application integration testing faster and more independent. They support key portions of the data and messaging APIs, while differing in how clients connect: Pub/Sub Java requires declaring a credential-free gRPC channel, whereas Java server clients for Firestore, Bigtable, and Spanner detect emulator addresses automatically from environment variables.

For reliable tests, manage emulator lifecycles explicitly, create isolated test fixtures, enforce fail-fast endpoint validation, and avoid execution-order dependencies. Then use real GCP staging to verify IAM, indexes, concurrency, quotas, performance, and unemulated features. Combining both lets Java/Spring teams catch integration bugs early while keeping deployment risks under control.

## References

- [Pub/Sub: Testing apps locally with the emulator](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Firestore: Use Firestore emulator locally](https://docs.cloud.google.com/firestore/native/docs/emulator)
- [Firebase Local Emulator Suite: Connect to Firestore emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)
- [Bigtable: Test using the emulator](https://docs.cloud.google.com/bigtable/docs/emulator)
- [Spanner: Emulate Spanner locally](https://docs.cloud.google.com/spanner/docs/emulator)
- [Spanner: Create and manage databases](https://docs.cloud.google.com/spanner/docs/create-manage-databases)
- [Google Cloud Client Libraries for Java](https://cloud.google.com/java/docs/reference)
- [Firebase Local Emulator Suite](https://firebase.google.com/docs/emulator-suite)
