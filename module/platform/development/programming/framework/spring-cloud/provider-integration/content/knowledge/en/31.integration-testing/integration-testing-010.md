# Creating Isolated Test Resources and Cleaning Up After Each Run

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services across **AWS, Azure, and Google Cloud** via Spring Cloud and their corresponding client libraries. An integration test may create buckets, queues, topics, tables, databases, secrets, or containers to verify application flows. If tests share resources and data, outcomes become order-dependent, parallel tests overwrite each other, and forgotten cloud resources continue incurring costs.

Reliable testing requires two properties:

- **Isolation:** each test or test run operates solely on resources and data within its own scope.
- **Cleanup:** created resources are deleted after the test completes, even if assertions fail or setup finishes only partially.

Emulator containers such as LocalStack, the Pub/Sub emulator, or Azurite help isolate infrastructure processes. However, stopping a container does not delete buckets, queues, or databases that tests created in the real cloud. Container lifecycles and cloud resource lifecycles must be managed separately.

After this lesson, you will be able to:

- Choose isolation scopes per test method, class, suite, or CI run.
- Generate unique, traceable resource names complying with each provider's naming rules.
- Manage cleanup with JUnit lifecycles, `AutoCloseable`, and registries.
- Delete resources in reverse dependency order and verify deletion completes.
- Isolate data when sharing buckets, databases, emulators, or containers.
- Handle parallel tests and multiple CI workers.
- Design safe cleanup across AWS, Azure, and Google Cloud.
- Reclaim orphaned resources when CI is cancelled or a JVM is killed.

## 2. Resource Isolation Differs from Container Isolation

There are two lifecycle layers:

1. **Infrastructure lifecycle:** Docker/Testcontainers/emulators starting and stopping.
2. **Test resource lifecycle:** buckets, queues, topics, tables, databases, objects, documents, or records created by tests.

For example, a single LocalStack container may be shared across an entire test class. Each test still needs its own bucket and queue, or an isolated namespace inside a shared resource. Stopping the LocalStack container is not a cleanup strategy for real AWS resources.

~~~mermaid
flowchart TD
    R[CI test run] --> C[Shared emulator/container]
    R --> T1[Test method A]
    R --> T2[Test method B]
    R --> T3[Test method C]
    T1 --> A1[Resource namespace A]
    T2 --> A2[Resource namespace B]
    T3 --> A3[Resource namespace C]
    A1 --> X[Cleanup registry]
    A2 --> X
    A3 --> X
    X --> D[Delete and verify]
    C --> S[Stop after suite/class]
~~~

Containers can be shared to save startup time. Test data must still remain independent so tests can execute in any order.

## 3. Choosing the Isolation Scope

Not every resource needs to be created fresh per test method. Choose scope based on provisioning cost, shared state risk, and safe deletion capability:

| Scope | Example | When Appropriate |
|---|---|---|
| Per assertion | Dedicated object or record | Small tests with cheap data creation/deletion |
| Per test method | Dedicated queue, topic, bucket, or database | Parallel-capable tests needing strong isolation |
| Per test class | One emulator/container or database schema | Multiple tests sharing infrastructure with per-method data resets |
| Per test suite | One container or namespace | High startup cost, test data separated by prefix |
| Per CI run | Dedicated project/resource group/namespace | Concurrent test classes or workers |
| Shared environment | Dedicated test project/subscription/account | Only with strict ownership, naming, and cleanup rules |

By default, create **separate data per test method**. You can share an emulator, database server, or cloud account; however, bucket prefixes, queues, tables, tenant keys, or record IDs must remain distinct.

If provisioning separate databases or cloud resources is too expensive, share a database/container and partition data by run ID. In that model, each test may read/delete only its own partition and never call `deleteAll()` on shared resources.

## 4. Generating Run IDs and Unique Resource Names

Resource names should answer:

- Which CI run owns the resource?
- Which test class/method created it?
- Which application or team created it?
- How can it be found and cleaned up?

A traceable format:

~~~text
<service>-<purpose>-<ci-run>-<test-id>-<random-suffix>
~~~

Examples:

~~~text
provider-it-documents-run842-preview-7f29c1a4
provider-it-events-run842-queue-8a31d902
provider-it-storage-run842-6b3e18f1
~~~

Do not rely solely on second-level timestamps because multiple workers can create resources simultaneously. Append a UUID/random suffix to prevent collisions. Keep names concise because each provider enforces different length limits, allowed characters, casing rules, and global uniqueness constraints.

Example Java helper:

~~~java
import java.util.Locale;
import java.util.UUID;

public final class TestResourceNames {
    private TestResourceNames() {}

    public static String unique(String prefix, int maxLength) {
        String safePrefix = prefix.toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9-]", "-")
                .replaceAll("-+", "-")
                .replaceAll("^-|-$", "");
        if (safePrefix.isBlank()) {
            throw new IllegalArgumentException("prefix must contain a letter or digit");
        }

        String suffix = UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);

        String candidate = safePrefix + "-" + suffix;
        if (candidate.length() <= maxLength) {
            return candidate;
        }
        int prefixLength = maxLength - suffix.length() - 1;
        if (prefixLength < 1) {
            throw new IllegalArgumentException("maxLength is too small");
        }
        return safePrefix.substring(0, Math.min(prefixLength, safePrefix.length()))
                + "-" + suffix;
    }
}
~~~

This helper illustrates generating lowercase alphanumeric names with hyphens. Check the actual rules for each resource type: S3 and GCS bucket names share global namespaces; Azure containers have specific constraints; Service Bus entities, DynamoDB tables, and Pub/Sub topics have distinct limits. Never apply one universal length limit across every service.

## 5. Attaching Ownership Metadata to Resources

Unique names prevent collisions; metadata enables tracking and cleaning up orphaned resources.

When a service supports tags or labels, attach these attributes:

| Tag/Label | Example | Purpose |
|---|---|---|
| `managed-by` | `integration-tests` | Distinguishes test-created resources |
| `test-run-id` | `run-842` | Groups resources by CI run |
| `test-class` | `PreviewQueueIT` | Identifies creation source |
| `test-method` | `publishesPreview` | Investigates specific tests |
| `created-at` | ISO-8601 UTC | Computes resource age |
| `expires-at` | ISO-8601 UTC | Supports orphan janitor sweeps |
| `owner-team` | `document-platform` | Identifies responsible team |

Never place secrets, tokens, customer data, or PII in resource names, tags, or labels. Some resources do not support resource-level tags/labels; use naming conventions and an external cleanup registry to track ownership.

Before deleting, verify ownership metadata and target project/account/subscription. Never delete solely because a name starts with a prefix if tests might run in a shared environment.

## 6. Resource Registries and Reverse-Order Cleanup

A test may create multiple dependent resources: a bucket, objects, notifications, and a queue receiving events. During cleanup, delete in reverse order: subscriptions/notifications first, objects before buckets, and queues after stopping consumers. This follows the **last created, first deleted (LIFO)** principle.

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public final class TestResourceScope implements AutoCloseable {
    @FunctionalInterface
    public interface CleanupAction {
        void run() throws Exception;
    }

    private final Deque<CleanupAction> actions = new ArrayDeque<>();
    private boolean closed;

    public synchronized void onClose(CleanupAction action) {
        if (closed) {
            throw new IllegalStateException("Resource scope is already closed");
        }
        actions.push(action);
    }

    @Override
    public void close() throws Exception {
        Exception failure = null;
        synchronized (this) {
            if (closed) return;
            closed = true;
        }
        while (true) {
            CleanupAction action;
            synchronized (this) {
                action = actions.poll();
            }
            if (action == null) break;
            try {
                action.run();
            } catch (Exception ex) {
                if (failure == null) {
                    failure = new Exception("One or more test resources failed to clean up");
                }
                failure.addSuppressed(ex);
            }
        }
        if (failure != null) throw failure;
    }
}
~~~

Register cleanup immediately after each resource is created:

~~~java
try (TestResourceScope scope = new TestResourceScope()) {
    String bucket = createBucket();
    scope.onClose(() -> deleteBucketIfOwned(bucket));
    String objectKey = uploadObject(bucket);
    scope.onClose(() -> deleteObjectIfOwned(bucket, objectKey));
    assertObjectCanBeDownloaded(bucket, objectKey);
}
~~~

Because the registry uses a stack, the object is deleted before the bucket. If upload fails after the bucket was created, bucket cleanup still executes. Cleanup actions must be idempotent or handle NotFound errors explicitly so repeated runs do not cause noise.

## 7. Using JUnit Lifecycles Properly

JUnit Jupiter provides `@BeforeEach`, `@AfterEach`, `@BeforeAll`, and `@AfterAll`:

- `@BeforeEach`: create dedicated data for a test method.
- `@AfterEach`: delete that test method's data.
- `@BeforeAll`: initialize shared class-level infrastructure.
- `@AfterAll`: shut down shared class-level infrastructure.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class QueueIntegrationTest {
    private TestResourceScope resources;
    private String queueName;

    @BeforeEach
    void createIsolatedResources() {
        resources = new TestResourceScope();
        queueName = TestResourceNames.unique("provider-it-queue", 80);
        createQueue(queueName);
        resources.onClose(() -> deleteQueueIfOwned(queueName));
    }

    @AfterEach
    void cleanupResources() throws Exception {
        if (resources != null) resources.close();
    }

    @Test
    void sendsMessageToItsOwnQueue() {
        sendMessage(queueName, "test-payload");
        assertMessageAvailable(queueName);
    }
}
~~~

If setup creates multiple resources and can fail midway, register cleanup after each creation step. For complex setup, wrap `@BeforeEach` in `try/catch` to invoke cleanup before rethrowing; do not assume every teardown callback handles a partially failed setup. Using `try-with-resources` directly inside the test method also guarantees `close()` runs whether the test exits normally or throws.

## 8. Testcontainers: Sharing Containers While Isolating Data

With Testcontainers JUnit 5:

- A static `@Container` starts once before the class's test methods and stops after the class.
- An instance `@Container` starts and stops per test method; this costs more time and resources.
- The JUnit extension is documented by Testcontainers as tested with sequential execution; parallel execution can cause unexpected side effects.

In many suites, it is better to share one emulator/container and create distinct resource/data namespaces per test. You do not need to recreate the entire container just to get a fresh bucket or queue.

~~~java
@Testcontainers
class StorageIntegrationTest {
    @Container
    static final LocalStackContainer LOCALSTACK =
            new LocalStackContainer(
                    DockerImageName.parse("localstack/localstack:stable"))
                    .withServices("s3");

    @Test
    void uploadsFirstDocument() {
        String bucket = TestResourceNames.unique("it-docs", 63);
        // Create bucket, test, then delete only this bucket.
    }
}
~~~

Pin images to a tested version/digest; the `stable` tag is illustrative only. Retrieve endpoints/ports from the container rather than hardcoding host ports.

Spring TestContext can cache an `ApplicationContext` across test classes. If the Testcontainers JUnit extension stops a static container at the end of a class while Spring reuses a cached context holding clients pointing to that container, the next test class will hit a stopped endpoint. When a singleton container is needed across multiple classes, manage it with a matching lifecycle, retain per-method resource cleanup, and manage context cache keys carefully.

## 9. Isolation Under Parallel Test Execution

Parallel tests expose hidden assumptions about shared data. Two concurrent tests might:

- Delete a queue while the other is receiving messages from it.
- Write to the same object key.
- Truncate/reset a database table.
- Drop a collection that another test is querying.
- Create same-named resources in the same project.

Principles:

1. Generate distinct resource names per test ID.
2. Scope data inside shared resources by partition key, tenant, or run ID.
3. Never call `deleteAll()` on shared databases, tables, or queues.
4. Never assume tests run in declaration order.
5. Never share mutable fixtures across test threads.
6. Bound concurrency when emulators or cloud quotas cannot sustain the load.
7. Include CI run ID and worker ID to separate concurrent processes.

If sharing a bucket, restrict prefixes by test run, such as `runs/<run-id>/<test-id>/`. Cleanup lists and deletes only that prefix. Never use broad wildcards or delete the entire shared bucket.

## 10. AWS: S3, SQS, SNS, and DynamoDB

### 10.1. S3

Create a dedicated test bucket when verifying bucket policies, versioning, or lifecycles. If only testing upload/download, you can share a bucket and isolate object keys by run/test prefix.

Cleanup order:

1. Stop producers, consumers, or notification tests.
2. Delete objects created by the test.
3. If versioning is enabled, delete all object versions and delete markers.
4. Abort incomplete multipart uploads.
5. Delete the bucket once it is empty.

S3 refuses to delete a bucket containing objects or versions. On versioned buckets, deleting the current object via `DeleteObject` may simply insert a delete marker; list and delete all versions and delete markers to empty the bucket.

### 10.2. SQS and SNS

- Create queues with unique names per test.
- Stop listeners before deleting queues.
- Drain/clean messages per fixture; avoid letting other consumers pick up test messages.
- Delete subscriptions and topics created by the test.
- Never delete shared queues/topics belonging to other environments.

For SNS fan-out to SQS, clean up subscriptions and queues first, then delete the topic. Store the ARNs/URLs returned by APIs rather than manually concatenating endpoint strings.

### 10.3. DynamoDB

You can create a dedicated test table or share a table using a partition key containing the run ID. Dedicated tables let you verify schema/index/TTL configs; isolated partitions are cheaper, though cleanup must query the exact partition and delete items individually.

When deleting a table, wait until it reaches the non-existent state before reusing the same name. Never rely on fixed table names when multiple CI workers run in parallel.

## 11. Azure: Blob Storage, Service Bus, and Cosmos DB

### 11.1. Blob Storage

Create a dedicated container per test or use prefixes inside a dedicated test container. Cleanup must remove blobs/snapshots/versions created by the test and then delete the container if owned by the test.

Azure Blob containers can take time to finish deleting. After deletion is accepted, creating a container with the same name may fail for at least ~30 seconds, and operations against blobs may briefly continue succeeding. Always use unique names rather than deleting and immediately recreating the same name in tests.

If soft delete or versioning is enabled, deleted data may remain retained during the retention period. This affects capacity/cost and recoverability even though the resource no longer appears as live data.

### 11.2. Service Bus

Use `ServiceBusAdministrationClient` to create/delete queues, topics, and subscriptions inside a test namespace:

~~~java
ServiceBusAdministrationClient admin = new ServiceBusClientBuilder()
        .connectionString(testNamespaceConnectionString)
        .buildAdministrationClient();

String queueName = TestResourceNames.unique("it-queue", 50);
admin.createQueue(queueName);

try {
    // Send and receive messages using the test queue.
} finally {
    admin.deleteQueue(queueName);
}
~~~

If a test creates topics/subscriptions/rules, delete rules and subscriptions before deleting the topic. Namespaces are usually shared infrastructure; never delete the namespace in `@AfterEach` if multiple tests share it.

### 11.3. Cosmos DB

You can use a dedicated database/container per test method or an isolated partition key inside a shared container. Delete only the database/container created by the test; if creating items inside a shared container, delete items by ID and partition key. Never scan and wipe the entire container during cleanup.

## 12. Google Cloud: Pub/Sub, Cloud Storage, Firestore, and Spanner

### 12.1. Pub/Sub

Create topics and subscriptions with unique names. During cleanup:

1. Stop subscribers/pull workers.
2. Delete subscriptions.
3. Delete topics.

Deleting a topic **does not automatically delete subscriptions** attached to it. After a topic is deleted, its name may remain unavailable for reuse briefly. Always use unique names per run/test and retain exact resource names.

### 12.2. Cloud Storage

Buckets must be empty before deletion. Delete test-created objects before deleting the bucket; if versioning is active, handle noncurrent versions per policy. When sharing a bucket, delete only your test run's prefix, leaving other objects untouched.

Soft delete/retention policies can preserve data after deletion completes. Distinguish objects that are no longer live from soft-deleted objects still within their retention window.

### 12.3. Firestore

Deleting a parent document does not automatically delete all subcollections. Collection cleanup must traverse and delete documents/subcollections recursively or use an appropriate server-side tool. In tests, prefer placing root paths under the run ID so the entire namespace can be enumerated and cleaned up accurately.

### 12.4. Spanner and Bigtable

- Create dedicated databases/tables when tests require schema isolation.
- When sharing a database, include the test run ID in primary keys or data namespaces.
- Delete test-created rows/records before dropping tables/databases.
- Wait for drop/delete operations to complete before reusing names.

Never delete a shared instance, cluster, or project just to clean up a single test method.

## 13. S3 Cleanup Example with try-with-resources

The following example creates a bucket and registers cleanup immediately afterward. The helper deletes the object before the bucket:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteBucketRequest;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;

@SpringBootTest
class S3ResourceLifecycleIT {
    @Autowired
    S3Client s3;

    @Test
    void createsAndRemovesIsolatedBucket() throws Exception {
        try (TestResourceScope scope = new TestResourceScope()) {
            String bucket = "it-" + UUID.randomUUID()
                    .toString().replace("-", "").substring(0, 16);
            s3.createBucket(CreateBucketRequest.builder()
                    .bucket(bucket)
                    .build());

            scope.onClose(() -> {
                // This example assumes an unversioned test bucket.
                s3.deleteObject(DeleteObjectRequest.builder()
                        .bucket(bucket)
                        .key("fixture.txt")
                        .build());
                s3.deleteBucket(DeleteBucketRequest.builder()
                        .bucket(bucket)
                        .build());
            });

            uploadFixture(s3, bucket, "fixture.txt");
            assertFixtureCanBeRead(s3, bucket, "fixture.txt");
        }
    }
}
~~~

This example assumes an unversioned test bucket with a single fixture object. Helpers for versioned buckets must remove all versions/delete markers and abort multipart uploads before calling `DeleteBucket`. In production-grade tests, register object cleanup immediately after upload succeeds so the registry accurately reflects created resources.

## 14. Safe Cleanup When Setup Fails

Setup can fail partway through after creating some resources. For example, a bucket was created but fixture upload failed; a topic was created before subscription creation failed. If cleanup runs only at the end of the test body, those resources leak.

Safe sequence:

1. Create one resource.
2. Record the exact ID/name/ARN/URL returned by the provider.
3. Attach ownership metadata.
4. Register the cleanup action immediately.
5. Create the next dependent resource.
6. When the test ends, run cleanup in LIFO order.
7. Capture all cleanup errors instead of aborting on the first failure.

Never register a blanket "delete everything matching prefix" action if other tests could create resources under that prefix. The registry should record specific resource IDs.

## 15. Idempotent Cleanup and Dependency Ordering

Cleanup should tolerate repeated execution without throwing confusing errors:

- Resource already absent: treat as clean if the API returns NotFound.
- Resource currently deleting: poll for terminal state within a deadline.
- Dependency never created: do not attempt deletion with an unset ID.
- One cleanup action fails: continue running remaining actions, then report an aggregated failure.

Typical cleanup order follows reverse dependencies:

| Creation Order | Resource | Deletion Order |
|---:|---|---:|
| 1 | Parent bucket/topic/database | Last |
| 2 | Object/subscription/table | Before parent resource |
| 3 | Event/message/record | Before object or subscription |
| 4 | Running listener/consumer | Stop before deleting queue/subscription |

Not every provider permits deletion in the exact same order. Check the resource's API docs and handle dependencies such as subscriptions, object versions, child collections, or active consumers.

## 16. Verifying Cleanup Has Completed

An accepted delete request does not guarantee the resource vanished immediately. Some services enter a deleting/deprovisioning state or have consistency delays.

After calling delete:

- Poll get/describe/list APIs with a finite deadline.
- Verify the resource no longer exists or has reached a terminal state.
- For containers/blobs, verify no child objects remain before deleting the parent.
- For queues/topics, stop consumers and confirm no unwanted subscriptions remain.
- For databases, wait for the deleted state before reusing the name.

Example polling for resource absence using Awaitility:

~~~java
await()
        .alias("test queue deleted")
        .pollInterval(Duration.ofMillis(250))
        .atMost(Duration.ofSeconds(30))
        .until(() -> !queueExists(queueName));
~~~

Never use polling to mask permission or network errors. If the API returns an error other than transient or NotFound, report cleanup failure and log the resource ID for investigation.

## 17. CI Cancellation, Orphan Resources, and Janitors

`@AfterEach` and `finally` cannot guarantee execution when a process receives `kill -9`, a runner machine drops, the JVM crashes, or a job is cancelled abruptly. Cloud resources can remain behind after the pipeline exits.

Design two layers of protection:

1. **Immediate cleanup:** JUnit callbacks/try-with-resources delete resources during normal execution.
2. **Orphan janitor:** a scheduled job finds expired test resources and deletes them by ownership metadata.

A janitor should:

- Scan only accounts/projects/subscriptions dedicated to testing.
- Delete only resources carrying `managed-by=integration-tests` or valid registry ownership.
- Verify `expires-at` has passed and the resource has not been renewed.
- Support a dry-run mode and thorough logging before enabling live deletes.
- Delete in dependency order with bounded concurrency.
- Report resources that fail deletion so owners can investigate.

TTL tags/labels do not trigger automatic deletion on every provider/service. A scheduled cleanup process or explicit lifecycle policy is required. Never apply a TTL tag and assume the cloud deletes the resource automatically if the resource type does not support it.

## 18. Security, Cost, and Resource Limits

Test resources are still real cloud resources that can incur charges or expose access. Apply these safeguards:

- Use dedicated accounts/projects/subscriptions for integration tests whenever possible.
- Use roles/service principals/service accounts scoped to creating and deleting only the target test resource types.
- Never grant CI permissions to delete production resources.
- Use network boundaries and secret stores for credentials.
- Never store production data or PII in test fixtures.
- Set quotas/concurrency caps so parallel tests cannot spawn thousands of resources simultaneously.
- Attach expiration metadata and run orphan cleanup.
- Monitor spend and leftover resource counts after every CI run.

If tests must verify IAM/policies, use a dedicated test account/project with isolated policies and test both positive and negative permissions. The cleanup identity needs sufficient permission to delete test resources, yet should not hold subscription/account-wide administrative privileges.

## 19. Troubleshooting and Practice Exercises

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Passes alone, fails in suite | Shared resource names or data | Use unique run/test IDs and per-method cleanup |
| Duplicate resource names in CI | Multiple workers sharing a fixed prefix | Add run ID, worker ID, and random suffix |
| S3 bucket cannot be deleted | Remaining objects, versions, delete markers, or multipart uploads | Clean up child resources before the bucket |
| Recreating Azure container returns 409 | Deletion incomplete or name in cooldown | Use unique names and poll status |
| Pub/Sub topic deleted but subscription remains | Deleting a topic does not delete subscriptions | Delete subscriptions independently before the topic |
| GCS bucket delete fails | Bucket still holds live/noncurrent objects | List and delete objects/versions under prefix |
| Firestore parent document deleted but data remains | Subcollections are not deleted with parent documents | Recursively clean up subcollections |
| Cleanup failure hides original assertion error | Teardown throws an exception replacing the test failure | Attach cleanup errors as suppressed exceptions and log |
| Resources left behind after CI cancellation | Lifecycle callbacks did not run | Use `expires-at` tags/labels and an orphan janitor |
| Testcontainers stops between classes | Extension stops container while Spring context is cached | Use an appropriate singleton lifecycle or separate contexts |
| Parallel test deletes wrong resource | Cleanup uses a broad prefix/wildcard | Store exact resource IDs and verify ownership |

### Exercise A — Resource Naming

Write a helper that builds bucket/container/queue names from CI run ID, test method, and UUID. Validate output names against S3, Azure Blob Container, and Pub/Sub topic rules.

### Exercise B — Cleanup Registry

Implement `TestResourceScope` supporting cleanup action registration, LIFO execution, and aggregating failures as suppressed exceptions. Verify remaining cleanup actions still run when one fails.

### Exercise C — S3

Create a dedicated bucket, upload multiple objects, verify contents, and clean up. Add a versioning case that deletes all object versions and delete markers before deleting the bucket.

### Exercise D — Messaging

Create an SQS queue or Pub/Sub topic/subscription. Stop the consumer, delete subscriptions/queues in dependency order, and verify the resources no longer exist.

### Exercise E — Azure

Create a dedicated Blob container and Service Bus queue. Clean up the container/queue after the test; observe behavior when recreating a Blob container with the same name while deletion is still processing.

### Exercise F — Orphan Janitor

Create resources tagged with `managed-by`, `test-run-id`, and `expires-at`. Implement a dry-run mode listing expired resources, then add deletion gated by a project/account allowlist.

### Self-Check Questions

1. **Does container lifecycle replace cloud resource cleanup?** No; containers and cloud resources have independent lifecycles.
2. **Why do resources need unique names?** To prevent collisions and enable traceability across tests and CI workers.
3. **Why should cleanup execute in LIFO order?** Child resources typically depend on parent resources; deleting children first avoids dependency errors.
4. **When is a static `@Container` appropriate?** When infrastructure can be shared across a test class while test data stays isolated.
5. **Does Testcontainers JUnit 5 guarantee parallel execution?** Current documentation notes the extension is tested with sequential execution; parallel runs can cause side effects.
6. **Can an S3 bucket be deleted while containing objects?** No; objects and all versions/delete markers must be deleted first.
7. **Does deleting a Pub/Sub topic delete its subscriptions?** No; subscriptions must be deleted separately.
8. **What condition must a GCS bucket meet before deletion?** The bucket must be empty of live/noncurrent objects per the delete API.
9. **Why is `@AfterEach` alone insufficient?** Processes can be killed or runners lost before the callback executes.
10. **What should an orphan janitor verify before deleting?** Ownership, project/account allowlist, expiration, and dependencies before deletion.
11. **How do you avoid cleaning up another test's resources?** Track exact IDs, check ownership tags/labels, and restrict account/project scope.
12. **Why verify after deletion?** Some services delete asynchronously or have propagation delays before a resource disappears.

## 20. Summary

Creating isolated resources and performing controlled cleanup enables integration tests to run repeatably, concurrently, and in CI without interfering with each other. Select an appropriate isolation scope, derive resource names from run/test IDs, attach ownership metadata, and register cleanup immediately after creating each resource.

JUnit lifecycles and Testcontainers manage test and container lifecycles; an `AutoCloseable` registry runs cleanup in LIFO order while ensuring remaining actions still execute on errors. On AWS, delete objects/versions before buckets; on Azure, handle blobs/containers and Service Bus entities in dependency order; on Google Cloud, delete subscriptions before topics, empty buckets, and recursively clean up documents/subcollections.

Immediate cleanup must be paired with an orphan janitor because processes can terminate abruptly. Delete only resources owned by test runs, verify target accounts/projects/subscriptions, confirm deletion completes, and use least-privilege permissions. This keeps test data independent, curbs forgotten resource costs, and makes test results more trustworthy.

### Official References

- [Testcontainers for Java — JUnit 5 lifecycle](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [JUnit 5 — BeforeEach](https://docs.junit.org/5.11.4/api/org.junit.jupiter.api/org/junit/jupiter/api/BeforeEach.html)
- [AWS SDK for Java 2.x — S3 delete bucket behavior](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/s3/S3AsyncClient.html)
- [AWS SDK for Java 2.x — SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html)
- [Microsoft Learn — Azure Blob Storage Java quickstart](https://learn.microsoft.com/en-us/azure/storage/storage-java-how-to-use-blob-storage)
- [Microsoft Learn — Delete Blob Container](https://learn.microsoft.com/en-us/rest/api/storageservices/delete-container)
- [Azure SDK for Java — Service Bus administration client](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.administration?view=azure-java-stable)
- [Google Cloud — Delete Pub/Sub subscriptions](https://docs.cloud.google.com/pubsub/docs/delete-subscriptions)
- [Google Cloud — Delete Pub/Sub topics](https://docs.cloud.google.com/pubsub/docs/delete-topic)
- [Google Cloud — Delete Cloud Storage buckets](https://docs.cloud.google.com/storage/docs/deleting-buckets)
- [Google Cloud — Delete Cloud Storage objects](https://docs.cloud.google.com/storage/docs/deleting-objects)
- [Firebase — Delete Cloud Firestore data](https://firebase.google.com/docs/firestore/manage-data/delete-data)

