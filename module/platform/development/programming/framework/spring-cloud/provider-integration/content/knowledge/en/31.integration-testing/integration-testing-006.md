# Google Cloud Emulators and Per-Service Endpoint Configuration

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services across **AWS, Azure, and Google Cloud** via Spring Cloud libraries and their corresponding client libraries. When testing a Spring Boot application that uses Pub/Sub, Firestore, Bigtable, Spanner, or Cloud Storage, you do not always need to call production services. Some Google Cloud services offer locally runnable emulators; others have test servers or community-provided simulation tools.

Unlike a single shared emulator for an entire cloud, Google Cloud typically uses **per-service endpoints**. Pub/Sub, Firestore, Bigtable, and Spanner have distinct emulators and configuration mechanisms. Cloud Storage has no official Google Cloud CLI emulator; you must choose an alternative test server or use a test bucket on the real cloud.

This lesson helps you:

- Distinguish official emulators, Firebase Emulator Suite, and third-party test servers.
- Select the right emulator for the API operations your application actually invokes.
- Configure per-service endpoints for Pub/Sub, Firestore, Datastore, Bigtable, and Spanner.
- Connect Spring Boot via Spring Framework on Google Cloud or Google Cloud Java Client Libraries.
- Manage dynamic endpoints with Testcontainers.
- Separate project IDs, credentials, and emulator settings from production.
- Understand limitations regarding IAM, TLS, consistency, indexes, transactions, and performance.
- Design local integration tests and smoke tests on real Google Cloud.

## 2. What Is a Google Cloud Emulator?

An emulator is a process simulating a subset of a cloud service's API. The application still calls the corresponding client library, but the client is configured to route requests to a local address rather than production endpoints.

Example:

~~~mermaid
flowchart LR
    T[JUnit integration test] --> A[Spring Boot]
    A --> C[Google Cloud Java client]
    C --> R{Service endpoint}
    R --> P[Pub/Sub emulator]
    R --> F[Firestore emulator]
    R --> B[Bigtable emulator]
    R --> S[Spanner emulator]
    R --> G[Storage test server]
~~~

Emulators are suitable for verifying:

- Clients are initialized with the expected project, host, port, and credentials.
- Request/response mapping, serialization, and error handling.
- Publish/subscribe flows, or reading/writing documents, rows, or records.
- Spring auto-configuration and application adapters.
- Basic API operations supported by the emulator.

An emulator is not a complete replica of the managed service. It may skip IAM, TLS, quotas, size limits, transaction concurrency, indexes, or distributed behaviors. Therefore, a green integration test on an emulator only proves the tested API flow works within the simulated scope.

## 3. Emulator and Endpoint Map by Service

| Service | Local Tool | Common Default Endpoint | How Java Clients Receive the Endpoint |
|---|---|---|---|
| Pub/Sub | Google Cloud CLI Pub/Sub emulator | localhost:8085 | Spring property or manual gRPC channel |
| Firestore Native mode | Firestore emulator / Firebase Local Emulator Suite | 127.0.0.1:8080 | `FIRESTORE_EMULATOR_HOST` or Spring property |
| Firestore Datastore mode | Firestore emulator with `datastore-mode` | 127.0.0.1:8080 | `DATASTORE_EMULATOR_HOST` or Spring Datastore property |
| Bigtable | Bigtable emulator | localhost:8086 | `BIGTABLE_EMULATOR_HOST` |
| Spanner | Spanner emulator | localhost:9010 gRPC, localhost:9020 REST | `SPANNER_EMULATOR_HOST` or Spring property |
| Cloud Storage | No official Google Cloud CLI emulator | Depends on test server | `StorageOptions.setHost` or custom endpoint |

The ports above are common defaults, not mandatory values. When running emulators in containers, Testcontainers may map dynamic ports. Always read the endpoint from the container rather than assuming localhost and default ports.

## 4. Choosing the Right Emulator Before Writing Tests

Before selecting a tool, determine:

1. Which API the application uses: Pub/Sub, Firestore Native, Firestore Datastore mode, Bigtable, Spanner, or Cloud Storage.
2. Which client library creates requests: Spring starter, Google Cloud Java client, or Firebase SDK.
3. Which operations are actually invoked: publish, pull, transaction, query, batch write, object upload, signed URL, etc.
4. Whether the test aims to verify business flow, wiring, IAM, encryption, consistency, or performance.
5. Whether the emulator models the behavior under test or only happy-path operations.

Do not use the Firestore Native emulator to simulate a Datastore API merely because both share the Firestore emulator binary. Enable the right database mode. Similarly, Firebase Storage Emulator belongs to Firebase Local Emulator Suite; it is not an official emulator of the Cloud Storage JSON API for arbitrary server-side clients.

## 5. Installing Google Cloud CLI and Java Version Notes

Official emulators are installed and started using the Google Cloud CLI. Example:

~~~bash
gcloud components update
gcloud components install pubsub-emulator
gcloud components install cloud-spanner-emulator
~~~

Some emulators download automatically on start or ship with Cloud SDK components. Check the installation guide for each service rather than assuming every emulator installs identically.

**Version note as of 24-11-2026:** Google Cloud CLI 592.0.0 released on 03-11-2026 requires Java 25 or higher for the Firestore emulator and Datastore emulator. If a development environment only has Java 21 installed, the emulator may fail to start with the latest CLI. There are two options:

- Upgrade the JRE used to run the emulator to Java 25.
- Pin an older Cloud CLI/emulator version verified and approved by the project.

The emulator's Java requirement does not mean the Spring Boot application must change its JDK. You can run the application on its supported JDK while running the emulator in a container with the required JRE.

## 6. Starting Emulators from the Google Cloud CLI

### 6.1. Pub/Sub

Start:

~~~bash
gcloud beta emulators pubsub start --project=local-test-project --host-port=0.0.0.0:8085
~~~

The emulator typically listens on port 8085. You can inspect the address chosen by the emulator with:

~~~bash
gcloud beta emulators pubsub env-init
~~~

Creating topics, subscriptions, and publishing/receiving all happen within the emulator session. Resources exist only for the lifetime of the emulator process.

### 6.2. Firestore Native Mode

Start:

~~~bash
gcloud emulators firestore start --host-port=0.0.0.0:8080
~~~

By default the Firestore emulator uses host `127.0.0.1` and port `8080`. Change host/port as needed to avoid conflicts with the Spring Boot app or another emulator.

If testing Firestore Enterprise edition, the CLI supports the edition flag:

~~~bash
gcloud emulators firestore start --edition=enterprise --host-port=0.0.0.0:8080
~~~

### 6.3. Firestore in Datastore Mode

Use the same Firestore emulator with database mode enabled:

~~~bash
gcloud emulators firestore start --database-mode=datastore-mode --host-port=0.0.0.0:8080
~~~

Datastore clients connect via `DATASTORE_EMULATOR_HOST`. This is the recommended approach when testing applications using Firestore in Datastore mode; do not confuse it with the legacy Datastore emulator.

### 6.4. Bigtable

Start:

~~~bash
gcloud beta emulators bigtable start --host-port=0.0.0.0:8086
~~~

The Bigtable emulator defaults to `localhost:8086`. If running multiple emulators or containers concurrently, specify host/port explicitly to avoid collisions.

### 6.5. Spanner

Start:

~~~bash
gcloud emulators spanner start
~~~

The Spanner emulator exposes two endpoints:

- `localhost:9010` for gRPC.
- `localhost:9020` for REST.

The Java Cloud Spanner client library uses gRPC endpoint `9010` when `SPANNER_EMULATOR_HOST` is set.

## 7. Environment Variables and Endpoint Rules

Client libraries recognize specific environment variable names:

| Environment Variable | Example Value | Notes |
|---|---|---|
| `PUBSUB_EMULATOR_HOST` | localhost:8085 | Pub/Sub Java requires explicit channel configuration |
| `PUBSUB_PROJECT_ID` | local-test-project | Optional simulated project ID for Pub/Sub |
| `FIRESTORE_EMULATOR_HOST` | localhost:8080 | Automatically recognized by Firestore server client libraries |
| `DATASTORE_EMULATOR_HOST` | localhost:8080 | Automatically recognized by Datastore client libraries |
| `BIGTABLE_EMULATOR_HOST` | localhost:8086 | Automatically recognized by Bigtable client libraries |
| `SPANNER_EMULATOR_HOST` | localhost:9010 | Automatically recognized by Spanner client libraries |
| `STORAGE_EMULATOR_HOST` | localhost:4443 | Not an official Google Cloud Java SDK emulator mechanism; use custom endpoint for Java |

For gRPC, many variables accept only `host:port` without a scheme—for example `localhost:9010`, not `http://localhost:9010`. For HTTP APIs such as a Cloud Storage test server, the endpoint is typically a URL with a scheme, such as `http://localhost:4443`.

If the emulator and application run in two separate containers, `localhost` inside the application container points to the application container itself. Use a Docker network alias or the endpoint returned by Testcontainers. Do not pass a host-mapped endpoint into another container if that container cannot route to the host.

## 8. Configuring Pub/Sub in Spring Boot

Spring Framework on Google Cloud provides the Pub/Sub starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
~~~

Use the Spring Framework on Google Cloud BOM to manage versions. In an emulator profile:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      pubsub:
        emulator-host: localhost:8085
~~~

When `spring.cloud.gcp.pubsub.emulator-host` is set, auto-configuration creates a plaintext transport channel and disables credentials so the client targets the emulator. If using the Spring Cloud Stream Pub/Sub binder, configure the host/port using this property as well.

### 8.1. Plain Pub/Sub Java Client

There is an important distinction: the Google Pub/Sub emulator guide tells you to set `PUBSUB_EMULATOR_HOST`, but the Java Cloud Client Library does not automatically redirect endpoints from that variable alone. Your code must construct a plaintext gRPC channel and `NoCredentialsProvider`:

~~~java
import com.google.api.gax.core.NoCredentialsProvider;
import com.google.api.gax.grpc.GrpcTransportChannel;
import com.google.api.gax.rpc.FixedTransportChannelProvider;
import com.google.cloud.pubsub.v1.TopicAdminClient;
import com.google.cloud.pubsub.v1.TopicAdminSettings;
import com.google.pubsub.v1.TopicName;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

String host = System.getenv("PUBSUB_EMULATOR_HOST");
if (host == null || host.isBlank()) {
    throw new IllegalStateException("PUBSUB_EMULATOR_HOST is required");
}

ManagedChannel channel = ManagedChannelBuilder.forTarget(host)
        .usePlaintext()
        .build();

var transport = FixedTransportChannelProvider.create(
        GrpcTransportChannel.create(channel));

var credentials = NoCredentialsProvider.create();

TopicAdminSettings settings = TopicAdminSettings.newBuilder()
        .setTransportChannelProvider(transport)
        .setCredentialsProvider(credentials)
        .build();

try (TopicAdminClient client = TopicAdminClient.create(settings)) {
    TopicName topicName = TopicName.of("local-test-project", "documents");
    client.createTopic(topicName);
} finally {
    channel.shutdown();
}
~~~

When creating `Publisher`, `Subscriber`, or `SubscriptionAdminClient`, supply the same transport and credentials provider. In Spring applications, prefer letting the Spring starter manage channels and lifecycles if auto-configuration is already in use.

## 9. Configuring Firestore in Spring Boot

Spring Framework on Google Cloud provides the Spring Data Firestore starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
</dependency>
~~~

Emulator profile configuration:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

`spring.cloud.gcp.firestore.emulator.enabled` turns on emulator mode; `host-port` points to the Firestore emulator host/port. With Spring Cloud GCP, this is a clean configuration that easily stays separated from production.

### 9.1. Firestore Java Client

Firestore server client libraries also recognize `FIRESTORE_EMULATOR_HOST`:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;

Firestore firestore = FirestoreOptions.getDefaultInstance()
        .toBuilder()
        .setProjectId("local-test-project")
        .setHost("localhost:8080")
        .setCredentials(NoCredentials.getInstance())
        .build()
        .getService();
~~~

Setting the endpoint and `NoCredentials` explicitly in tests prevents clients from accidentally falling back to Application Default Credentials. If relying on `FIRESTORE_EMULATOR_HOST`, set the variable before instantiating the client.

The Firestore emulator discards data by default when the process stops. It exposes a REST endpoint to clear data per project/database between tests; await completion of the delete response before continuing.

## 10. Configuring Datastore and Firestore Datastore Mode

Spring Framework on Google Cloud offers a Datastore starter:

~~~xml
<dependency>
    <group>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

If the emulator is already started externally, set the host:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      datastore:
        host: localhost:8080
~~~

Spring Framework on Google Cloud can also auto-start the Datastore emulator during integration tests:

~~~yaml
spring:
  cloud:
    gcp:
      datastore:
        emulator:
          enabled: true
          port: 8081
          firestore-in-datastore-mode: true
~~~

When auto-start is enabled, the `host` property is ignored because auto-configuration connects directly to the Spring-managed emulator. Data can be persisted on disk using `store-on-disk` and `data-dir` properties if supported by the emulator mode/version.

When testing Firestore in Datastore mode, use the Firestore emulator with `--database-mode=datastore-mode`. The legacy Datastore emulator exhibits behaviors different from production, such as default eventual consistency and query limitations. Do not use a legacy emulator to conclude Firestore Datastore mode has been thoroughly tested.

## 11. Configuring Bigtable

The Google Cloud Bigtable Java client library recognizes `BIGTABLE_EMULATOR_HOST`. Example:

~~~powershell
$env:BIGTABLE_EMULATOR_HOST = "localhost:8086"
~~~

When the application constructs a Bigtable client, the library uses the emulator endpoint. You can also configure it directly via builder:

~~~java
import com.google.cloud.bigtable.data.v2.BigtableDataClient;
import com.google.cloud.bigtable.data.v2.BigtableDataSettings;

BigtableDataSettings settings =
        BigtableDataSettings.newBuilderForEmulator("localhost", 8086)
                .setProjectId("local-test-project")
                .setInstanceId("local-instance")
                .build();

BigtableDataClient client = BigtableDataClient.create(settings);
~~~

The Bigtable emulator lacks administrative APIs to create or manage instances/clusters. Tests can supply arbitrary project and instance names, create tables, and read/write rows. You do not need to provision a Bigtable instance on Google Cloud just to run emulator tests.

Spring Framework on Google Cloud does not provide the same style of Bigtable auto-configuration starter as Pub/Sub, Firestore, and Spanner discussed in this lesson. For Bigtable, you typically configure the Google Cloud Java client directly inside a `@Configuration` class and inject it into adapters.

## 12. Configuring Spanner

Spring Framework on Google Cloud provides the Spring Data Spanner starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-spanner</artifactId>
</dependency>
~~~

Emulator configuration:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: local-test-project
      spanner:
        instance-id: local-instance
        database: local-database
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

`spring.cloud.gcp.spanner.emulator.enabled` turns on emulator mode. `emulator-host` points to the gRPC endpoint. The REST endpoint `9020` is for REST clients or `gcloud` CLI; the Java Spanner client library uses gRPC `9010`.

### 12.1. Spanner Java Client

You can use `SPANNER_EMULATOR_HOST` or configure it directly:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;

SpannerOptions options = SpannerOptions.newBuilder()
        .setProjectId("local-test-project")
        .setEmulatorHost("localhost:9010")
        .setCredentials(NoCredentials.getInstance())
        .build();

Spanner spanner = options.getService();
~~~

The Spanner emulator supports both GoogleSQL and PostgreSQL dialects. Data, schemas, and configurations are lost when the emulator restarts. Tests should create isolated instances/databases/tables per run or execute repeatable schema initialization scripts.

## 13. Cloud Storage: Choosing an Alternative Test Server

The Google Cloud CLI does not currently offer an official emulator for Cloud Storage. Several options exist:

| Tool | Scope | Suitable Use Case |
|---|---|---|
| `fake-gcs-server` | Third-party server simulating a subset of the Cloud Storage JSON API | Testing upload/download/list and adapters |
| `storage-testbench` | Googleapis testbench for Cloud Storage client libraries | Testing client behavior and specialized request/error scenarios |
| Firebase Storage Emulator | Emulator in Firebase Local Emulator Suite | Testing apps using Firebase Storage SDK and Firebase rules |
| Test bucket on Google Cloud | Real Cloud Storage service | Smoke testing IAM, signed URLs, lifecycles, versioning, and production behavior |

Do not refer to `fake-gcs-server` or Firebase Storage Emulator as the official Google Cloud Storage emulator. Each tool has distinct API coverage and semantics.

### 13.1. Running fake-gcs-server

Docker example:

~~~bash
docker run --rm -p 4443:4443 fsouza/fake-gcs-server -scheme http
~~~

The server defaults to HTTPS on port 4443; the `-scheme http` flag enables plain HTTP for simple local tests. Pin a tested image version/digest in CI rather than relying on mutable tags.

### 13.2. Configuring the Cloud Storage Java Client

The Cloud Storage Java client supports custom endpoints via `StorageOptions.Builder.setHost`:

~~~java
import com.google.auth.oauth2.NoCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

Storage storage = StorageOptions.newBuilder()
        .setProjectId("local-test-project")
        .setHost("http://localhost:4443")
        .setCredentials(NoCredentials.getInstance())
        .build()
        .getService();
~~~

If the server runs in another container, replace `localhost` with the Docker network hostname or endpoint returned by Testcontainers. Do not assume `STORAGE_EMULATOR_HOST` is handled automatically by the Google Cloud Java Storage client the way some Go clients handle it.

## 14. Configuring Endpoints per Spring Profile

Never place emulator endpoints in the shared production `application.yml`. Create a local or `integration-test` profile:

~~~yaml
# application-integration-test.yml
spring:
  config:
    activate:
      on-profile: integration-test
  cloud:
    gcp:
      project-id: local-test-project
      pubsub:
        emulator-host: localhost:8085
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
      spanner:
        instance-id: local-instance
        database: local-database
        emulator:
          enabled: true
        emulator-host: localhost:9010
~~~

Datastore, Bigtable, and Storage may require client/adapter-specific configuration. If Spring Cloud GCP auto-starts the Datastore emulator, enable `emulator.enabled` and set an appropriate port/`data-dir`. For Bigtable, build the client from `BIGTABLE_EMULATOR_HOST` or `BigtableDataSettings.newBuilderForEmulator`. For a Storage test server, build the `Storage` bean with `setHost`.

In production, never activate the `integration-test` profile. Do not allow local endpoints to be overridden via uncontrolled environment variables.

## 15. Testcontainers GCloud Module

Testcontainers for Java provides a GCloud module to run emulators for BigQuery, Bigtable, Datastore, Firestore, Spanner, and Pub/Sub. The module is currently marked **INCUBATING**, so APIs and packages may change between releases.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-gcloud</artifactId>
    <version>2.0.5</version>
    <scope>test</scope>
</dependency>
~~~

Pin the Testcontainers version via your project BOM. For the Google Cloud CLI image, pin a verified tag/digest. The Firestore and Datastore emulators in Cloud CLI 592 require Java 25; the container image must include the matching JRE.

### 15.1. Pub/Sub Emulator Container Example

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.gcloud.PubSubEmulatorContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class PubSubIntegrationTest {
    @Container
    static final PubSubEmulatorContainer PUBSUB =
            new PubSubEmulatorContainer(
                    DockerImageName.parse(
                            System.getProperty(
                                    "gcloud.emulator.image",
                                    "gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators")));

    @DynamicPropertySource
    static void emulatorProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.gcp.pubsub.emulator-host",
                PUBSUB::getEmulatorEndpoint);
        registry.add(
                "spring.cloud.gcp.pubsub.project-id",
                () -> "local-test-project");
    }

    @Test
    void applicationCanUsePubSubEmulator() {
        // Exercise the application's Pub/Sub adapter or PubSubTemplate.
    }
}
~~~

Set the `gcloud.emulator.image` system property in your build to pin a tested tag/digest; the illustrative default uses the `emulators` tag. `@Testcontainers`/`@Container` instructs JUnit to start and stop the container with the test class lifecycle. If using Spring context caching, ensure the container outlives any cached `ApplicationContext` holding the client.

For `FirestoreEmulatorContainer`, Testcontainers exposes the endpoint via `getEmulatorEndpoint()`; configure `FirestoreOptions.setHost` or Spring property `host-port` with that value. `SpannerEmulatorContainer` exposes the gRPC endpoint for `SpannerOptions.setEmulatorHost`. `BigtableEmulatorContainer` exposes host/port for `BigtableDataSettings.newBuilderForEmulator`.

## 16. Project IDs, Credentials, and Security Boundaries

Emulators generally do not enforce full production IAM or authentication. Therefore:

- Use a dedicated simulated project ID, such as `local-test-project`.
- Use `NoCredentials` or an unauthenticated credentials provider as required by the emulator.
- Never use production service account JSON in local tests.
- Never allow test containers to access a developer's ADC unless explicitly needed.
- Never include emulator endpoints in production profiles.
- Never feed production data or real secrets into emulator fixtures.
- Ensure emulator hosts/ports are reachable only from the local machine or dedicated test Docker network.

For Pub/Sub Java in particular, configuring a plaintext channel and `NoCredentialsProvider` is part of emulator setup. The Spanner emulator does not support authentication, IAM, permissions, or TLS. The Bigtable emulator likewise does not support secure connections. These tests cannot validate IAM roles, service account permissions, TLS certificates, or VPC Service Controls.

## 17. Limitations and Differences Compared to Real Google Cloud

| Service | Notable Limitations | When Real Cloud Tests Are Needed |
|---|---|---|
| Pub/Sub | No IAM operations; configurable message retention unsupported; subscriptions do not expire; certain RPCs/SMT/BigQuery subscriptions limited | Verifying IAM, retention, protobuf schemas, BigQuery subscriptions, seek, or production retry semantics |
| Firestore | Transaction concurrency differs from production; composite indexes not enforced; limits not fully enforced; search stage unsupported | Verifying transaction contention, index deployment, query limits, text search, or production limits |
| Datastore mode | Legacy emulator behaves differently from Firestore Datastore mode; query operators/aggregations and consistency vary by mode | Verifying consistency, transactions, queries/indexes, and exact database mode behavior |
| Bigtable | In-memory; no admin APIs to create/manage instances/clusters; no TLS support | Verifying instance topology, IAM, TLS, replication, performance, and cluster behavior |
| Spanner | In-memory; no TLS, auth, IAM, permissions, or audit/monitoring; transactions/schema changes lock database more broadly than production | Verifying IAM, query plans, transaction concurrency, partitionability, latency, and performance |
| Cloud Storage test server | API coverage and behavior depend on third-party project; does not reflect full IAM, retention, lifecycle, or versioning | Verifying signed URLs, IAM, retention, lifecycles, versioning, object holds, and consistency |

### 17.1. Pub/Sub

The Pub/Sub emulator supports publishing, pull/push delivery, ordering, replay, dead-letter forwarding, retry policies, Avro schemas, and filtering. Limitations include: IAM operations are unsupported; configurable retention does not operate and messages persist for the emulator session; subscription expiration is not modeled; certain RPCs such as `UpdateTopic`/`UpdateSnapshot` are unsupported; BigQuery subscriptions can be created but do not write messages to BigQuery.

### 17.2. Firestore

The Firestore emulator stores data in memory and discards it upon shutdown. Transactions use simplified locking rather than modeling full production concurrency modes. The emulator does not validate composite indexes or enforce all production limits. Consequently, a query may pass in the emulator yet fail on real Firestore due to a missing index.

### 17.3. Bigtable and Spanner

The Bigtable emulator lacks instance/cluster admin APIs; you can create tables and read/write rows under arbitrary project/instance names. The Spanner emulator supports GoogleSQL and PostgreSQL dialects, but omits TLS, IAM, authentication, and monitoring/audit tools. Emulator performance and scalability cannot represent production.

## 18. Data Management, Cleanup, and CI

Emulators have varying data lifecycles:

- Pub/Sub: resources and messages exist for the emulator session.
- Firestore Native mode: data is lost when the emulator stops; a REST endpoint clears databases between tests.
- Bigtable: data lives in memory and is lost when the emulator stops.
- Spanner: data, schemas, and configuration are lost when the emulator restarts.
- Datastore: persistence depends on emulator mode and `store-on-disk` configuration.
- `fake-gcs-server`: persistence depends on the configured backend/volume.

Guiding principles:

1. Create topics, subscriptions, collections, tables, databases, and buckets with names unique to the test run.
2. Seed schemas/data using idempotent scripts.
3. Clear data or use dedicated projects/namespaces after each test suite.
4. Do not allow tests to depend on execution order.
5. Use dynamic ports and endpoints from Testcontainers.
6. Pin Cloud CLI images, Testcontainers modules, and client libraries.
7. Archive container logs on test failure.
8. Never expose production credentials in CI jobs running emulators.

Pipelines can be structured into unit tests, emulator integration tests, and smoke tests on a Google Cloud test account. Smoke tests should scope down projects, quotas, service accounts, and resources, and clean up resources after execution.

## 19. Troubleshooting and Practice Exercises

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Client still calls production endpoint | Env var/property not loaded before client creation | Check profile, host/port, and bean initialization order |
| Pub/Sub Java throws auth/channel error | Set `PUBSUB_EMULATOR_HOST` without plaintext channel | Use Spring `emulator-host` or channel provider + `NoCredentialsProvider` |
| Firestore fails to connect | Missing `FIRESTORE_EMULATOR_HOST` or wrong `host-port` | Verify endpoint and database mode |
| Firestore query passes locally but fails in cloud | Composite index not created or limit differences | Deploy indexes and run real smoke tests |
| Spanner client reports TLS/auth error | Wrong emulator endpoint or client credentials | Use `SPANNER_EMULATOR_HOST`, emulator mode, and `NoCredentials` |
| Bigtable admin operations fail | Emulator does not provide instance/cluster admin APIs | Use dummy project/instance IDs and create only tables/data |
| Emulator runs but app container cannot connect | Using `localhost` from inside another container | Use Docker network alias or Testcontainers endpoint |
| Firestore/Datastore emulator fails to start | Cloud CLI 592 requires Java 25 | Upgrade emulator JRE or pin an older verified CLI |
| Storage test server returns 404 | Endpoint scheme/path or API behavior mismatch | Check `setHost`, scheme, port, and test server choice |
| Test passes alone but fails in full suite | Shared emulator state or colliding resource names | Isolate projects/resources and clean up |

### Exercise A — Pub/Sub

Start the emulator, create a topic/subscription, publish a message, and pull the message. Run the same test via the Spring Pub/Sub starter using `emulator-host`, then run a plain Java client with a plaintext channel and `NoCredentialsProvider`.

### Exercise B — Firestore

Start the Firestore emulator, configure Spring Data Firestore, write and query documents. Write a query requiring a composite index and compare emulator behavior against a real test database.

### Exercise C — Datastore Mode

Start the Firestore emulator with `--database-mode=datastore-mode`. Configure `DATASTORE_EMULATOR_HOST` and test a Spring Data Datastore repository. Confirm the test runs in the expected mode.

### Exercise D — Bigtable

Start the Bigtable emulator, create a table/column family, write a row, and read back the cell. Document why this test does not verify instance/cluster creation or IAM.

### Exercise E — Spanner

Start the Spanner emulator, create an instance/database/table, and insert/query data using `SpannerTemplate` or `DatabaseClient`. Add a smoke test to verify IAM and transaction behavior on a test account.

### Exercise F — Cloud Storage

Run `fake-gcs-server`, configure `StorageOptions.setHost`, and test upload/download. Then run a smoke test against a real test bucket to verify IAM, signed URLs, and lifecycles.

### Self-Check Questions

1. **Why does Google Cloud use per-service endpoints?** Each client library targets its own API endpoint, and emulators have distinct hosts, ports, and protocols.
2. **Does Pub/Sub Java automatically use `PUBSUB_EMULATOR_HOST`?** No; you must configure a plaintext channel and `NoCredentialsProvider` or use Spring's `emulator-host`.
3. **Which variable do Firestore server clients use?** `FIRESTORE_EMULATOR_HOST`.
4. **Which variable does Datastore mode use?** `DATASTORE_EMULATOR_HOST`; you can run the Firestore emulator in `datastore-mode`.
5. **Which variable does the Bigtable emulator use?** `BIGTABLE_EMULATOR_HOST`.
6. **What are the default Spanner Java emulator endpoints?** `localhost:9010` for gRPC; `9020` for REST.
7. **Does Cloud Storage have an official `gcloud` CLI emulator?** No; you need an alternative test server or a real test bucket.
8. **Which emulators does the Testcontainers GCloud module support?** BigQuery, Bigtable, Datastore, Firestore, Spanner, and Pub/Sub; the module is incubating.
9. **Why is Java 25 needed for the latest Firestore/Datastore emulators?** Google Cloud CLI 592.0.0 requires Java 25 for these emulators.
10. **Does the Firestore emulator enforce production composite indexes?** No; indexes must be tested against real Firestore.
11. **Does the Spanner emulator verify IAM/TLS?** No; smoke tests on the real cloud are required.
12. **Why avoid `localhost` when the app runs in another container?** `localhost` resolves to the application container itself, not the emulator container.

## 20. Summary

Emulators make Google Cloud integration testing fast and repeatable, but endpoints and behavior must be configured per service. Pub/Sub uses `PUBSUB_EMULATOR_HOST` or Spring `emulator-host`; Firestore uses `FIRESTORE_EMULATOR_HOST` or `host-port`; Datastore uses `DATASTORE_EMULATOR_HOST`; Bigtable uses `BIGTABLE_EMULATOR_HOST`; Spanner uses `SPANNER_EMULATOR_HOST` on gRPC port `9010`. Cloud Storage has no official Google Cloud CLI emulator, requiring an alternative test server or a real test bucket.

In Spring Boot, Spring Framework on Google Cloud provides dedicated properties for Pub/Sub, Firestore, Datastore, and Spanner. Bigtable typically uses the Google Cloud Java client directly; Storage can use `StorageOptions.setHost` when connecting to a test server. The Testcontainers GCloud module helps manage emulator lifecycles, though it is incubating and images must be pinned to appropriate versions.

Never treat emulators as proof of production IAM, TLS, quotas, consistency, indexes, transaction concurrency, or performance. Combine unit tests, emulator integration tests, and smoke tests on a Google Cloud test account to cover both application wiring and behaviors emulators do not simulate.

### Official References

- [Google Cloud — Pub/Sub emulator](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Google Cloud — Firestore emulator](https://docs.cloud.google.com/firestore/native/docs/emulator)
- [Google Cloud — Firestore in Datastore mode emulator](https://docs.cloud.google.com/datastore/docs/emulator)
- [Google Cloud — Bigtable emulator](https://docs.cloud.google.com/bigtable/docs/emulator)
- [Google Cloud — Spanner emulator](https://docs.cloud.google.com/spanner/docs/emulator)
- [Google Cloud — Java client library endpoints](https://docs.cloud.google.com/java/docs/endpoints)
- [Google Cloud — Cloud Storage request endpoints](https://docs.cloud.google.com/storage/docs/request-endpoints)
- [Google Cloud CLI — Release notes](https://docs.cloud.google.com/sdk/docs/release-notes)
- [Spring Framework on Google Cloud — Reference](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
- [Testcontainers for Java — GCloud module](https://java.testcontainers.org/modules/gcloud/)
- [fake-gcs-server — project documentation](https://github.com/fsouza/fake-gcs-server)
- [Googleapis — Cloud Storage testbench](https://github.com/googleapis/storage-testbench)
