# Integration Testing on a Dedicated GCP Project

Unit tests verify business logic while replacing dependencies with mocks or fakes. Integration testing verifies whether Java/Spring components actually work with live Google Cloud APIs, authentication, data stores, networking, and service behavior. A unit test can stub a successful object write, yet only testing against real Cloud Storage reveals a missing service account permission, an incorrect bucket, or a Java client picking up the wrong credentials.

In the **GCP Application Testing** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson guides you through building an integration testing environment using a **dedicated Google Cloud project for testing**, isolated from staging and production. The workflow combines project organization, IAM, VPC networking, storage/database services, CI/CD, Cloud Logging, and Cloud Monitoring. The goal is testing that reflects live behavior, is reproducible and observable, and never touches production resources.

After this lesson, learners will be able to:

- Distinguish mocks/emulators, component tests, integration tests against real GCP resources, and end-to-end tests.
- Design a dedicated test project with clear IAM, data, network, quota, and cost boundaries.
- Validate the target project and resources before running tests to prevent accidental writes to production.
- Choose Application Default Credentials (ADC) and apply least-privilege permissions for local/CI test runners.
- Write integration tests with JUnit 5, Spring Boot, and Google Cloud Java SDKs.
- Test Cloud Storage, Pub/Sub, Cloud SQL, and Cloud Run applications.
- Isolate fixtures and test runs, prevent resource contention, handle asynchronous workflows, and perform safe cleanup.
- Integrate with Cloud Build or external CI; diagnose failures and preserve test evidence.

## 1. Integration Testing in the Testing Strategy

Each testing tier has its own purpose, speed, cost, and fidelity.

| Tier | Scope | Dependencies | Primary Value |
|---|---|---|---|
| Unit | Functions/classes, rules, and validation | Mocks/fakes | Fast feedback, pinpoints logic bugs |
| Component | Spring context, repositories, controllers | In-memory DB, Testcontainers, emulators | Verifies wiring and internal contracts |
| GCP Integration | Java SDKs, IAM, networking, live APIs | Dedicated GCP test project | Confirms cloud service interactions |
| Contract | API/event schemas and compatibility | Stubs or provider contracts | Catches contract drift |
| End-to-end | Full flow from HTTP request to final outcome | Multiple services in one environment | Proves end-to-end business journeys |
| Load/resilience | Performance and failure behavior | Controlled environment | Evaluates SLOs and capacity limits |

For example, a document-upload API might have these tests:

1. Unit tests check filename validity and size limits.
2. Component tests confirm the service passes expected bytes to the storage adapter.
3. Integration tests write and read back an object in a test project's Cloud Storage bucket.
4. End-to-end tests send an HTTP request to Cloud Run and verify metadata in the database plus the object in the bucket.

Integration tests catch issues that mocks rarely cover adequately: IAM permissions, API enablement, SDK request syntax, networking, quotas, and timeouts. However, live cloud tests are slower and costlier; select high-value integration paths rather than pushing every business rule onto the cloud.

### 1.1. Emulators vs. Live Services

The Pub/Sub emulator, Firestore emulator, or Testcontainers run fast on developer laptops and CI runners. They work well for verifying serialization, transactions, and basic workflows, though they do not necessarily reproduce real GCP IAM, VPCs, Cloud Logging, organization policies, retry behaviors, or quotas.

A balanced strategy:

- On every pull request: run unit, component, Testcontainers, and emulator tests.
- On merge to main: run a short, controlled GCP integration test suite.
- On schedule or pre-release: run cross-service flows and deeper verification.
- Heavy load tests: run only with planned quotas, budgets, and cleanup conditions.

## 2. Architecture of a Dedicated GCP Test Project

A Google Cloud project provides a clean administrative boundary for IAM, APIs, billing, quotas, logs, and resources. Never reuse a production project simply for convenience because a bucket or database already exists there.

~~~mermaid
flowchart LR
    Dev[Developer] -->|ADC| Runner[Test runner identity]
    CI[Cloud Build / CI] -->|Service account / WIF| Runner
    Runner --> Test[GCP integration-test project]
    Test --> GCS[Cloud Storage test bucket]
    Test --> Pub[Pub/Sub test topic/subscription]
    Test --> SQL[Cloud SQL test database]
    Test --> Ops[Cloud Logging + Monitoring]
    Test --> Clean[Scoped cleanup + TTL]
    Prod[Production project] -.No test-runner permissions.-> Runner
~~~

| Example Project | Purpose | Identities Permitted to Write |
|---|---|---|
| app-dev | Manual development | Developers |
| app-it | Integration testing with real GCP | CI/test runner |
| app-staging | Release candidate validation | Staging pipeline |
| app-prod | Serving end users | Production workloads |

Project naming is the first step, but **IAM is what truly bounds blast radius**. If the identity running tests still holds write permissions in production, a misconfigured Java client can impact production even when a test project exists.

### 2.1. Boundaries to Separate

- **IAM:** runners only hold required permissions on the test project or specific resources.
- **Data:** synthetic, dummy, or anonymized data; never use real customer data without strict justification.
- **Networking:** tests must never accidentally point to internal production endpoints.
- **Secrets:** test and production secrets remain strictly separated with distinct lifecycles and read permissions.
- **Billing/quotas:** separate budgets and alerts; cap high-cost resources.
- **Logging:** traces, metrics, and logs stay in the test project for traceability and retention control.
- **Release flow:** passing tests serve as quality evidence, never implicit authorization to deploy to production.

### 2.2. Shared Test Project vs. Ephemeral Per-Run Projects?

**Single shared test project:** Provision buckets, topics, and Cloud SQL instances once, then partition object prefixes, subscriptions, schemas, and databases by run ID. Fits frequent testing with low infrastructure creation overhead. In return, you must prevent collisions and clean up orphaned resources.

**Ephemeral project per pipeline/branch:** Strong isolation allowing full project teardown after tests. In return, project creation, billing linking, organization policies, API enablement, and quota provisioning are complex, slow, and require high privileges.

For daily CI runs, a dedicated test project combined with run-ID-partitioned resources is usually the right starting point. For destructive infrastructure or IAM experiments, provision a separate ephemeral project to protect other test suites.

## 3. Preparing the Test Project

An administrator or provisioning pipeline creates the project, links billing, enables APIs, and provisions baseline resources; normal test runners should not need project-creation permissions.

### 3.1. Naming and Metadata

Choose a project name indicating integration-test, owner, contact group, and labels such as `environment=integration`, `application=orders`, and `cost_center=engineering`. Document lifetime expectations, retention policies, quotas, budgets, and orphan cleanup procedures. Labels aid lookup and cost attribution, **but do not automatically delete resources**.

### 3.2. Named Configuration in `gcloud`

~~~bash
gcloud config configurations create integration-tests
gcloud config set project "$GCP_TEST_PROJECT_ID"
gcloud config get-value project
gcloud projects describe "$GCP_TEST_PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"
~~~

`GCP_TEST_PROJECT_ID` must come from a controlled environment configuration. The commands above illustrate local administrative setup; in CI, pass `--project` explicitly on each command.

Note: the project in `gcloud` configuration and the project used by a Java client **can differ**. Java SDKs typically resolve credentials via ADC, and some clients infer a project from environment metadata. Pass the test project ID and resource names explicitly, then verify via IAM/preflight checks.

### 3.3. Enabling APIs

Example for Cloud Storage and Pub/Sub integration tests:

~~~bash
gcloud services enable \
  storage.googleapis.com \
  pubsub.googleapis.com \
  --project="$GCP_TEST_PROJECT_ID"
~~~

If tests use Cloud SQL, Cloud Run, Secret Manager, or Cloud Build, enable those APIs as well. Enabling APIs requires Service Usage permissions; execute this during provisioning rather than granting those permissions permanently to every test runner.

### 3.4. Provisioning Baseline Resources

~~~bash
gcloud storage buckets create "gs://$GCP_TEST_BUCKET" \
  --project="$GCP_TEST_PROJECT_ID" \
  --location=asia-southeast1 \
  --uniform-bucket-level-access

gcloud pubsub topics create "$GCP_TEST_TOPIC" \
  --project="$GCP_TEST_PROJECT_ID"

gcloud pubsub subscriptions create "$GCP_TEST_SUBSCRIPTION" \
  --topic="$GCP_TEST_TOPIC" \
  --project="$GCP_TEST_PROJECT_ID"
~~~

Bucket names are globally scoped, so they must be unique and contain no sensitive data. Provisioning scripts should be idempotent: if a resource already exists, verify its project, labels, and settings before use. Manage them with Terraform or your organization's IaC for auditability and reproducibility.

### 3.5. Budgets and Quotas

Tests can incur charges from idle Cloud SQL instances, Cloud Run minimum instances, storage, Pub/Sub backlogs, network egress, Cloud Build minutes, and log ingestion. Configure Cloud Billing budgets, alerts, and monitoring owners; **budget alerts are not hard caps** and do not automatically halt services.

Quotas apply per project, region, or API. When multiple suites run concurrently, bound concurrency and watch for `429/RESOURCE_EXHAUSTED` errors before requesting quota increases. Avoid spinning up expensive resources inside individual test methods.

## 4. ADC, Service Accounts, and Least-Privilege IAM

Never store production JSON keys in source code, JARs, container images, or CI secrets when short-lived identities are available.

| Environment | Recommended Identity | Mechanism |
|---|---|---|
| Local | Developer ADC or impersonated test service account | `gcloud auth application-default` |
| Cloud Build | User-managed CI/test service account | Build identity attached to trigger |
| GitHub Actions / External CI | Federated identity to test service account | Workload Identity Federation (OIDC) |
| GKE test runner | Kubernetes ServiceAccount | Workload Identity Federation for GKE |
| Compute Engine runner | VM service account | Metadata server / ADC |

### 4.1. ADC for Local Runs

~~~bash
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GCP_TEST_PROJECT_ID"
~~~

`gcloud` CLI credentials and ADC are not always identical; `auth application-default` specifically targets client libraries. Callers may need Service Usage Consumer on the quota project. If your organization mandates service account impersonation, follow policy to obtain short-lived credentials and restrict impersonation permissions.

### 4.2. IAM Roles by Operation

| Operation | Common Role | Scope |
|---|---|---|
| Upload/read/delete test objects | `roles/storage.objectUser` | Single test bucket |
| Publish test messages | `roles/pubsub.publisher` | Test topic |
| Pull/ack test messages | `roles/pubsub.subscriber` | Test subscription |
| Create Pub/Sub resources during provisioning | `roles/pubsub.editor` or custom role | Test project, provisioner only |
| Connect via Cloud SQL connector | `roles/cloudsql.client` | Test project/instance |
| Read test secret | `roles/secretmanager.secretAccessor` | Single test secret |
| Write build logs when needed | `roles/logging.logWriter` | Log project |

Cloud SQL Client permits connecting via the connector/Auth Proxy, but does not grant SQL privileges inside the database; database user/password or IAM database authentication must still be configured separately. A runner holding Storage Object User does not need permission to delete the bucket.

Separate **provisioner**, **runner**, and if needed **cleanup identities**. The provisioner creates infrastructure; the runner only exercises data paths; cleanup deletes approved run-scoped resources. Never grant Owner/Editor to runners merely to silence permission errors.

### 4.3. Preflight Guardrails Against Environment Mix-Ups

Before executing tests, verify:

1. `GCP_TEST_PROJECT_ID` is provided and belongs to the test project allowlist.
2. The project does not match protected production/staging projects.
3. The bucket, topic, instance, and endpoints belong to the provisioned inventory.
4. The active identity holds restricted permissions scoped to the test environment.
5. No production secrets or endpoints exist in the test profile.

Simple guardrail example:

~~~bash
set -euo pipefail
test -n "$GCP_TEST_PROJECT_ID" || exit 2
test -n "$GCP_TEST_BUCKET" || exit 2
test -n "$PROD_PROJECT_ID" || exit 2
if [ "$GCP_TEST_PROJECT_ID" = "$PROD_PROJECT_ID" ]; then
  echo "Refusing to run tests against production" >&2
  exit 2
fi
gcloud projects describe "$GCP_TEST_PROJECT_ID" \
  --format="value(projectId)"
~~~

Comparing against a single project ID is only a baseline check; real environments should enforce allowlists and resource manifests maintained by the platform team. IAM remains the ultimate enforcement boundary.

## 5. Creating Fixtures and Test-Run IDs

In a shared test project, two pipelines may run simultaneously. If they share object keys, database rows, or Pub/Sub subscriptions, one test can overwrite or consume another test's data.

Assign each run a unique ID: CI `BUILD_ID`, commit SHA plus run number, or a UUID locally. Embed that ID into object prefixes, databases/schemas, or message attributes.

| Resource | Lifecycle | Isolation Mechanism |
|---|---|---|
| Baseline bucket | Shared | Prefix `it/orders/<run-id>/` |
| Object | Per test | UUID, overwrite-prevention precondition |
| Baseline Pub/Sub topic | Shared or per suite | Message attributes + dedicated subscription |
| Subscription | Per suite/run | Unique name to avoid message stealing |
| Cloud SQL instance | Can be shared | Separate database/schema or data namespace |
| Cloud Run test service | Per deployment | Clear URL/identity/traffic routing |
| Test secret | Managed by provisioner | Never mutate shared secrets mid-test |

Fixtures must be self-creating and independent of execution order or leftover data from earlier runs. For asynchronous flows, define deadlines and polling strategies instead of fixed sleeps.

## 6. Java and JUnit 5 Example with Real Cloud Storage

Suppose a Spring Boot application stores invoices in Cloud Storage. Integration test goal: the Java SDK writes an object to the test bucket, reads back the exact bytes, and deletes only the object it created.

### 6.1. Dependencies

Use the Google Cloud Libraries BOM to keep client library versions aligned. Maven example:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>26.70.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

The BOM version here is illustrative; select a version approved and supported by your organization at execution time. Configure JUnit Jupiter through Maven Surefire/Failsafe or an appropriate Gradle test task.

### 6.2. Round-Trip Test

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("gcp-integration")
class CloudStorageRoundTripIT {
    private static String projectId;
    private static String bucket;
    private static Storage storage;
    private final List<BlobId> createdObjects = new ArrayList<>();

    @BeforeAll
    static void prepare() {
        projectId = requiredEnv("GCP_TEST_PROJECT_ID");
        bucket = requiredEnv("GCP_TEST_BUCKET");

        // CI preflight verifies project and bucket allowlists.
        storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .build()
                .getService();
        // Provisioner already verified the bucket; runner only needs object permissions.
    }

    @Test
    void canWriteAndReadObject() {
        String name = "it/orders/" + UUID.randomUUID() + "/invoice.txt";
        byte[] expected = "integration-ok".getBytes(StandardCharsets.UTF_8);
        BlobInfo info = BlobInfo.newBuilder(BlobId.of(bucket, name)).build();

        Blob created = storage.create(
                info, expected, Storage.BlobTargetOption.doesNotExist());
        createdObjects.add(created.getBlobId());

        byte[] actual = storage.readAllBytes(created.getBlobId());
        assertArrayEquals(expected, actual);
    }

    @AfterEach
    void cleanObjects() {
        for (BlobId id : createdObjects) {
            storage.delete(id);
        }
        createdObjects.clear();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing env: " + name);
        }
        return value;
    }
}
~~~

This test includes several safeguards:

- Explicitly requires project and bucket names.
- Random object keys prevent runs from overwriting one another.
- `doesNotExist` precondition prevents overwriting an existing object.
- `AfterEach` deletes only the test objects created, never the bucket.
- If the process crashes before `AfterEach`, objects may remain; environment-level cleanup handles leftovers by run ID or TTL.

Cloud Storage bucket names are global. Passing `projectId` to `StorageOptions` **does not automatically prove the bucket belongs to that project**. Provisioning manifests, bucket allowlists, and bucket-scoped IAM on the test bucket are essential controls. When generation-level protection is required, use Storage API generation preconditions.

### 6.3. Spring Boot Integration Profile

~~~java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("integration")
@Tag("gcp-integration")
class OrderStorageIntegrationIT {
    @Test
    void contextLoadsWithTestProfile() {
        // Configuration check only; does not prove I/O behavior.
    }
}
~~~

In `application-integration.yaml`, store only non-sensitive project, endpoint, and configuration values. Retrieve secrets from Secret Manager or controlled CI environment variables. Use `@DynamicPropertySource` when injecting dynamically provisioned endpoints or database names.

A `contextLoads` test only confirms the Spring context boots. True integration tests must perform real reads/writes or publish/consume operations and assert concrete outcomes.

## 7. Testing Pub/Sub

Because Pub/Sub is asynchronous, tests must verify serialization, message attributes, retries, ack/nack, idempotency, and deadlines.

### 7.1. `OrderCreated` Scenario

1. Test generates a unique run ID and order ID.
2. Publish `OrderCreated` to the **test topic**, attaching message attribute `testRunId`.
3. The application consumer in the test environment receives the message from the **test subscription**.
4. The consumer writes the outcome to the test database or test bucket.
5. JUnit polls for the outcome until an explicit deadline and asserts the content.
6. Clean up the subscription/object/row scoped to the run ID.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant P as Pub/Sub topic
    participant S as Test subscription
    participant W as Spring consumer
    participant D as Test database
    T->>P: Publish OrderCreated + testRunId
    P-->>S: Deliver
    S-->>W: Receive
    W->>D: Persist result
    W-->>S: Ack
    loop Poll until deadline
      T->>D: Query by testRunId + orderId
    end
    D-->>T: Expected result
~~~

In standard configurations, Pub/Sub may deliver a message more than once. Consumers must be idempotent by event ID or business key. Tests must not assert that a message is processed strictly once when the underlying system does not guarantee it.

### 7.2. Shared Subscriptions Can Cause Contention

If two runners pull from the same subscription simultaneously, messages can be delivered to the wrong runner. A `testRunId` attribute helps logical filtering, but **does not prevent another subscriber from receiving the message** on a shared subscription. Create a per-suite/per-run subscription or design an isolated topology.

Never rely on fixed `Thread.sleep` calls for synchronization. Use bounded polling with timeouts (e.g., a 30-second deadline per SLO), sensible backoff, and log the message ID, subscription, and `testRunId` on failure.

### 7.3. Failure Cases to Include

- Payload missing required fields or carrying an unsupported schema version.
- Consumer fails and the message is retried.
- Duplicate message arrives yet the database creates no duplicate record.
- Messages arrive out of order; system still handles state correctly.
- Subscription backlog causes latency beyond acceptable thresholds.
- Publisher holds permissions while subscriber lacks pull/ack permissions.

## 8. Testing Cloud SQL and Stateful Data

Cloud SQL integration tests verify real connectivity, migrations, constraints, transactions, and queries against a live database.

### 8.1. Data Separation

- Use only a dedicated Cloud SQL instance/database for testing.
- Grant the database user least privilege on the test schema/database.
- Use per-run schemas or databases when parallel execution is required.
- Use the Cloud SQL connector/Auth Proxy or appropriate network path, verifying private IP, firewall rules, and DNS.
- Run Flyway/Liquibase migrations in the test environment matching the application version.
- Bound HikariCP pool sizes and concurrent runs within `max_connections`.

The `roles/cloudsql.client` role is required for Cloud SQL connector/Auth Proxy mechanisms, but does not replace database user/password or IAM database authentication and in-database SQL grants.

### 8.2. Limitations of Transaction Rollback

Spring Test with `@Transactional` can roll back work inside the test method's own transaction. It does **not** roll back data:

- Written by another process or service.
- Written by an asynchronous Pub/Sub consumer.
- Written via an HTTP call to Cloud Run.
- Published to Pub/Sub or written to Cloud Storage.

For cross-service flows, cleanup must rely on run IDs/ownership or ephemeral databases/schemas dropped after the suite.

### 8.3. Testcontainers vs. Real Cloud SQL

Testcontainers running PostgreSQL/MySQL is excellent for verifying schemas, SQL queries, and transactions quickly. However, it does not test Cloud SQL IAM, connectors, networking, instance settings, failover, or quotas. Combine Testcontainers on PRs with a small, high-value Cloud SQL integration suite in the test project.

## 9. Testing Cloud Run, IAM, and Networking

When deploying the Java/Spring app to Cloud Run in the test project, test HTTP endpoints using tokens belonging to a test identity.

Valuable assertions:

- Service returns the expected response and schema.
- Authenticated endpoints reject requests without tokens.
- Authorized test runner can invoke; unauthorized identities are rejected.
- Runtime identity successfully connects to test Cloud SQL, Storage, and Pub/Sub.
- Timeouts, retries, and error responses honor API contracts.
- Logs contain correlation/trace IDs without leaking secrets.

If Cloud Run ingress allows internal traffic only, the test runner must sit on an authorized network path. HTTP 403 may indicate IAM/token issues, 404 may indicate URL/ingress issues, and 503 may indicate startup/instance/dependency failures; inspect request logs and application logs before guessing.

Never make a service public solely to make tests pass. Use the proper token audience, `roles/run.invoker`, ingress rules, and CI identity.

### 9.1. Negative IAM Tests

Use a separate test identity lacking Storage Object User or Cloud Run Invoker and verify the API denies the call. Never mutate the IAM policy of a runner shared by concurrent tests, as doing so causes race conditions. Never strip production policies to test permissions.

## 10. Organizing Tests with JUnit/Maven/Gradle

Separating integration tests from unit tests lets CI select the right timing and credentials for each tier.

### 10.1. Tags and Naming Conventions

~~~java
@Tag("gcp-integration")
@Tag("storage")
class StorageRoundTripIT {
    // Calls a real, dedicated Google Cloud test bucket.
}
~~~

JUnit tags only take effect if the build tool is configured to include/exclude them. Maven Failsafe typically picks up `*IT` classes during `integration-test`/`verify` phases; Gradle supports dedicated test suites or tasks.

### 10.2. Maven Failsafe

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-failsafe-plugin</artifactId>
  <version>3.5.4</version>
  <executions>
    <execution>
      <goals>
        <goal>integration-test</goal>
        <goal>verify</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <includes>
      <include>**/*IT.java</include>
    </includes>
    <groups>gcp-integration</groups>
  </configuration>
</plugin>
~~~

The plugin version is illustrative; pick a version compatible with your project toolchain. Run Maven's `verify` phase so Failsafe evaluates results and exits non-zero on failure, rather than running `integration-test` alone and skipping `verify`.

With Gradle, filter JUnit Platform tags inside a separate task/suite isolated from the unit test task. Ensure CI does not silently skip the entire integration group when profiles or build configurations change.

## 11. Cloud Build and Integration Test Pipelines

~~~mermaid
flowchart LR
    PR[Pull request] --> Unit[Unit + emulator tests]
    Unit --> Merge[Merge main / schedule]
    Merge --> Prep[Preflight project + resources]
    Prep --> IT[GCP integration suite]
    IT --> Report[Assertions + JUnit XML]
    Report --> Clean[Scoped cleanup]
    Clean --> Done[Build result + evidence]
~~~

One operational cadence:

- PR: unit/component tests with zero production secrets.
- Main: GCP integration tests in the dedicated test project.
- Scheduled: slower cross-service, quota, and controlled resilience tests.
- Pre-release: smoke tests on the selected artifact and runtime.

### 11.1. Dedicated Service Accounts

Cloud Build triggers should use a test service account granted permissions only on test resources. If the project hosting Cloud Build differs from the project hosting test resources, grant explicit narrowly scoped cross-project IAM. Avoid granting Editor by default and never reuse production runtime identities.

For GitHub Actions or external CI, use Workload Identity Federation with OIDC and a test service account. Restrict trust conditions by repository, branch, workflow, and audience; never allow pull requests from untrusted forks to obtain cloud-writing credentials.

### 11.2. `cloudbuild.yaml` Example

~~~yaml
steps:
  - name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -euc
      - |
        mvn -B -Pcloud-integration verify
    env:
      - GCP_TEST_PROJECT_ID=$_TEST_PROJECT_ID
      - GCP_TEST_BUCKET=$_TEST_BUCKET

substitutions:
  _TEST_PROJECT_ID: myapp-it
  _TEST_BUCKET: myapp-it-bucket-example

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

This is a skeleton: the `cloud-integration` profile and test dependencies must exist in the repository. The Java SDK inside the build step must obtain ADC from the Cloud Build environment/service account configured by your organization. Verify permissions and ADC availability inside the chosen worker image; never put JSON keys or passwords into substitutions.

### 11.3. Evidence and Auditing

Each test run should record commit SHA, build ID, test project ID, run ID, test group/version, JUnit reports, error logs, trace IDs, and cleanup outcomes. Never store tokens, password-bearing connection strings, or sensitive payloads in artifacts or logs. Linking build failures directly to run-scoped GCP resources speeds up investigation.

## 12. Controlling Flaky Tests and Concurrency

| Symptom | Possible Cause | Mitigation |
|---|---|---|
| Test A reads Test B's message | Shared subscription | Per-run subscription |
| Object overwritten | Name collision | UUID/prefix and preconditions |
| Duplicate primary key | Bad fixture or cleanup | Unique keys, isolated schema |
| 429 / quota exceeded | Too many parallel suites | Cap concurrency, apply backoff |
| Provisioning timeout | Resource not ready yet | Poll readiness with deadline |
| Passes locally, fails in CI | Different ADC/network/IAM | Preflight checks and clear roles |
| Intermittent failures | Async outcome not settled | Condition polling instead of sleep |
| Rising costs | Orphaned resources | Inventory, TTL, cleanup job |

### 12.1. Timeouts and Retries

Configure client API timeouts, test-level deadlines, and bounded polling/backoff. Distinguish transient errors like `UNAVAILABLE`/429 from persistent configuration errors like `PERMISSION_DENIED`. Never retry indefinitely; requests with side effects must carry idempotency keys or duplicate-prevention guards.

### 12.2. Do Not Blame Every Bug on Eventual Consistency

Cloud Storage provides strong consistency for many object and listing operations as documented by Google Cloud. If you write an object and immediately fail to read it back, check the bucket, object key, generation, credentials, and response errors before adding a sleep. By contrast, a Pub/Sub consumer runs asynchronously, so waiting for downstream side effects requires polling with a deadline.

## 13. Two-Tier Cleanup

**Method/run level:** use `try/finally`, `@AfterEach`, or `@AfterAll` to delete temporary objects, rows, and subscriptions/databases created by the run itself. Never delete baseline buckets, topics, or projects from normal test teardown.

**Environment level:** scheduled cleanup workflows sweep orphaned resources by run ID, labels, inventory, and TTL—handling leftovers when runners crash, CI jobs are cancelled, or networks drop. Cleanup identities can remain separate from runner identities.

Pre-deletion checks:

1. Project ID is on the test allowlist.
2. Resource owner/run ID matches.
3. Scope cannot sweep another active run's resources.
4. Run inventory checks or dry-runs when supported by tooling.
5. Delete in proper dependency order.
6. Confirm deletion succeeded and update inventory.
7. Retain required audit logs per retention policy.

If cleanup fails, report both the original test failure and the cleanup failure alongside leftover resource IDs. Never silently mark a cleanup failure as PASS if it introduces cost risk or breaks future runs.

## 14. Comprehensive Practice: Java Orders API

Suppose a Spring Boot API accepts orders, persists to Cloud SQL, and emits `OrderCreated` to Pub/Sub; a consumer generates a PDF invoice in Cloud Storage.

**Goal:** verify the HTTP API, database, publish/consume pipeline, and object storage on a dedicated GCP test project.

### Step 1. Provision

Create the test project with Cloud SQL, Pub/Sub, Cloud Storage, Cloud Run test service, and service accounts. Configure IAM, VPC/private connectivity, budget alerts, and retention. Record the provisioned resource inventory.

### Step 2. Seed Fixtures

Generate a run ID, order ID, and synthetic customer data. Provision a run-scoped schema/database or object prefix if running in parallel. Verify every endpoint and secret belongs to the test environment.

### Step 3. Execute

1. Send HTTP POST to `TEST_BASE_URL` with a randomized order ID.
2. Assert HTTP status, response schema, and correlation ID.
3. Poll the database to verify the order persisted accurately.
4. Poll consumer outputs to verify invoice creation.
5. Read the object from the Cloud Storage test bucket and verify metadata/contents.
6. Inspect logs/traces in the test project on any failure.

### Step 4. Negative Paths

Test missing fields, duplicate idempotency keys, message redelivery, invalid caller permissions, and controlled dependency timeouts. Outcomes must be unambiguous and leave no uncollectible data behind.

### Step 5. Cleanup and Reporting

Delete run-scoped data and verify zero orphaned resources remain. Save a report with commit SHA, build ID, run ID, project ID, assertion outcomes, and cleanup status. If cleanup fails, raise an incident/task with an explicit owner and resource IDs.

## 15. Symptom-Based Troubleshooting

**Could not find default credentials.** ADC is unconfigured or the runner lacks the right runtime identity. Check local `gcloud auth application-default`, Cloud Build service account, or external CI WIF.

**403 PERMISSION_DENIED.** Inspect the actual identity, resource-level roles, IAM conditions, org policies, Service Usage, and API enablement. Never "fix" by granting Owner.

**404 resource not found.** Check project ID, global bucket name, full topic/subscription path, database, region, and provisioning state. Never auto-create resources in production when lookup fails.

**429 RESOURCE_EXHAUSTED.** Review project/region quotas and concurrency across test suites and other pipelines; reduce parallelism and add backoff before requesting quota increases.

**Cloud SQL timeout.** Inspect instance state, private/public IP, VPC egress, firewall rules, DNS, connector setup, database auth, and connection counts.

**Pub/Sub event not received.** Check subscription existence, publisher logs, filters, ack state, permissions, and whether another consumer is competing for messages.

**Cloud Run 401/403.** Check ID token audience, Invoker role, ingress settings, and target URL. Never open public access just to pass tests.

**Passes locally, fails in CI.** Compare JDK versions, build tools, ADC, regions, networking, test environment variables, and execution identities.

**Tests fail randomly in parallel.** Check object keys, DB fixtures, subscriptions, shared state, and cleanup; isolate state rather than adding sleeps.

**Cleanup fails.** Report leftover resources, check cleanup identity permissions and TTLs; never mask the original test failure.

## 16. Implementation and Operations Checklist

### Project and Security

- [ ] Test project is isolated from production/staging.
- [ ] Owner, billing, budget alerts, labels, and retention policies are defined.
- [ ] APIs are enabled by the provisioner.
- [ ] Test runners have zero write permissions in production.
- [ ] ADC/WIF is used without static JSON keys.
- [ ] IAM is scoped per bucket/topic/subscription/secret wherever possible.
- [ ] Preflight checks enforce project/resource allowlists.

### Data and Test Design

- [ ] Tests use synthetic data without exposing sensitive records.
- [ ] Each run has a unique ID.
- [ ] Objects, rows, and subscriptions/schemas are isolated.
- [ ] Assertions validate real behavior, not just `contextLoads`.
- [ ] Async workflows have deadlines, bounded retries/backoff, and idempotency.
- [ ] Tests are independent of prior runs and execution order.
- [ ] Unit/component tests remain the fast feedback loop.

### CI and Operations

- [ ] Cloud integration tests have dedicated triggers and identities.
- [ ] JUnit reports, build IDs, commit SHAs, and correlation IDs are retained.
- [ ] Quotas, concurrency, and costs are monitored.
- [ ] Post-test cleanup and TTL-based orphan sweeping are active.
- [ ] Cleanup failures have assigned owners.
- [ ] Test infrastructure can be rebuilt reproducibly from IaC.

## 17. Official Documentation

- [Google Cloud project overview](https://cloud.google.com/resource-manager/docs/creating-managing-projects)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [ADC for local development](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Cloud Build service account](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Quotas and limits](https://cloud.google.com/docs/quotas/view-manage)
- [Cloud Storage Java SDK](https://cloud.google.com/storage/docs/reference/libraries)
- [Cloud Storage consistency](https://cloud.google.com/storage/docs/consistency)
- [Pub/Sub emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Pub/Sub subscriber guide](https://cloud.google.com/pubsub/docs/subscriber)
- [Cloud SQL Java connectors](https://cloud.google.com/sql/docs/mysql/connect-connectors)
- [Cloud Run authentication](https://cloud.google.com/run/docs/authenticating/overview)
- [Spring Boot testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)

Integration testing on a dedicated GCP project provides concrete evidence that Java/Spring applications work with real cloud services while preserving strict environmental boundaries. Beyond passing assertions, a mature process validates the exact target project and identity, isolates test data, retains audit evidence, caps cost and duration, and safely reclaims resources after every run.
