# Dedicated Named or Keyed Data for Each Test Suite

## Why Does Each Test Suite Need Its Own Namespace?

Spring integration tests often use stateful services: databases, Redis, message brokers, object storage, or a shared HTTP service. Multiple tests may run concurrently against the same container or CI environment. If all of them write to the same table names, keys, queues, or buckets, one test's data can interfere with another test.

An effective isolation technique is assigning each test suite a **dedicated namespace**. A namespace is a prefix or identifier scope that identifies which suite owns a piece of data. From that namespace, tests build dedicated names or keys for the resources they use.

Example:

~~~text
suite namespace: it_a81f2c9d

database schema: it_a81f2c9d
redis key:       it_a81f2c9d:orders:42
queue:           it_a81f2c9d-order-events
object key:      it_a81f2c9d/reports/42.json
tenant id:       it_a81f2c9d
~~~

When another suite runs in parallel, it has a different namespace and can create data of the same kind without overwriting the first suite's data.

A namespace does not replace assertions or cleanup. It establishes data ownership boundaries; tests still must verify their outcomes and clean up the resources they created. Also distinguish container names from data namespaces: a single database container can be shared across multiple suites, yet each suite should still have its own schema, tenant, or key prefix.

## Distinguishing a Suite Namespace from Individual Test Keys

Two levels of identifiers are often helpful:

- A **suite namespace** persists for the entire lifecycle of one test suite. It is used for schemas, queues, topics, tenants, or shared prefixes.
- A **test key** distinguishes data created by individual test methods within the suite's namespace. It is used for individual orders, users, messages, or objects.

Example:

~~~text
it_a81f2c9d:orders:test_creates_order
it_a81f2c9d:orders:test_cancels_order
it_a81f2c9d:users:test_registers_user
~~~

If tests within the same suite run sequentially and data is properly reset, the suite namespace alone may be enough. If test methods run in parallel, or multiple tests in the suite can access the same resource, add dedicated test keys to avoid internal collisions.

Do not generate a new UUID every time a getter is called. Every component within the same suite must use the same namespace throughout the suite's lifecycle. Generate the value once in the fixture or test configuration and pass it to the components that need it.

## Choosing Stable and Unique Identifiers

A namespace should satisfy three properties:

1. **No collisions across concurrently running suites.** You can use a UUID, a build ID combined with a job ID, or a random run ID.
2. **Stable within a single suite.** Generate once and share across the test context and related fixtures.
3. **Compliant with the service's naming rules.** Some backends restrict length, allowed characters, or case sensitivity.

Example generating a short token from a UUID:

~~~java
import java.util.UUID;

final class TestNamespace {

    private TestNamespace() {
    }

    static String newSuiteId() {
        return "it_" + UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);
    }
}
~~~

A suite can store this value in a `static final` field:

~~~java
static final String SUITE_ID = TestNamespace.newSuiteId();
~~~

If the CI system already provides a unique build ID or job ID, you can use it instead of a UUID or combine it with a UUID. A build ID helps trace resources in logs; a UUID avoids collisions when one build runs multiple jobs or retries simultaneously.

Do not put emails, usernames, access tokens, or sensitive data into resource names. Namespaces often appear in logs, dashboards, or queue names; use only technical identifiers containing no secrets.

### Normalizing Names per Backend

Not every backend accepts the same format:

| Backend | What to watch when generating names |
| --- | --- |
| PostgreSQL schema/table | Follow valid SQL identifier rules; avoid overly long names and SQL keywords |
| Redis key | Colons can express logical hierarchy; standardize encoding and prefixes |
| RabbitMQ queue/exchange | Check broker naming rules and length limits; avoid names with operational meaning |
| Kafka topic | Use supported characters and obey broker length limits |
| S3-compatible object storage | Prefixes work in object keys; bucket names follow stricter rules |
| Filesystem | Avoid path separators, forbidden characters, and paths escaping the test directory |

For length-limited names, shorten the token while retaining sufficient entropy or add a hash. Do not arbitrarily truncate a UUID to the point where concurrent jobs are likely to produce colliding names.

## Passing the Namespace into the Spring ApplicationContext

In Spring integration tests, a convenient place to expose the namespace is a test property. Beans can receive the property via constructor injection or configuration properties and use it to build resource names.

Example using `DynamicPropertySource`:

~~~java
import java.util.UUID;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class OrderIntegrationTest {

    static final String SUITE_ID = "it_" + UUID.randomUUID()
            .toString()
            .replace("-", "")
            .substring(0, 12);

    @DynamicPropertySource
    static void registerTestNamespace(DynamicPropertyRegistry registry) {
        registry.add("app.test.namespace", () -> SUITE_ID);
    }
}
~~~

The value is registered as a supplier and Spring can read it when building the `Environment`. Configuration beans can bind this property:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.test")
public record TestNamespaceProperties(String namespace) {
}
~~~

A factory using the namespace to build keys:

~~~java
class TestResourceNames {

    private final TestNamespaceProperties properties;

    TestResourceNames(TestNamespaceProperties properties) {
        this.properties = properties;
    }

    String redisOrderKey(long orderId) {
        return properties.namespace() + ":orders:" + orderId;
    }

    String queueName(String purpose) {
        return properties.namespace() + "-" + purpose;
    }
}
~~~

In a real application, register `TestNamespaceProperties` via `EnableConfigurationProperties` or your active configuration properties scanning mechanism. The example only illustrates passing a value from a test into a bean; it does not require production to always enable test namespaces.

### Note on the Spring TestContext Cache

The Spring TestContext Framework can cache an `ApplicationContext` and reuse it across test classes with the same configuration. Therefore, a namespace bound into singleton beans must stay stable for the entire lifetime of that context.

Do not mutate a static namespace after the context is created and expect singleton beans to pick up the new value automatically. Beans may already hold the old value. If two suites need different namespaces, create contexts with distinct configurations or pass namespaces at the request/test level instead of mutating a cached singleton's property.

`DynamicPropertySource` fits when a group of tests shares one configuration and one stable namespace. If sharing the same context across multiple classes while each class wants its own namespace, design context boundaries intentionally or pass test keys per operation. Do not let the context cache silently cause two suites to share a namespace unknowingly.

## Databases: Dedicated Schemas, Tenants, or Data Keys

Databases typically offer several isolation options:

- A dedicated database per suite.
- A dedicated schema per suite within the same database.
- A tenant ID or suite ID column in every row.
- Dedicated primary keys for test data combined with filtered queries.

Choose the level matching resource creation cost and how the application queries data. Dedicated schemas are useful when reusing one PostgreSQL container while avoiding table collisions across suites. Tenant keys fit applications that already support multi-tenancy.

### Dedicated Schemas in PostgreSQL

A suite can create a schema named after its namespace and configure connections to query within that schema. Schema names must be strictly controlled, containing only test-generated characters and never concatenating raw user input directly into SQL identifiers.

Conceptual example:

~~~sql
CREATE SCHEMA it_a81f2c9d;
~~~

After creating the schema, configure the datasource to use that schema, or set `search_path` on connections in a way compatible with your driver and pool. Migrations must target the suite's schema; if migrations still write to the default schema, the namespace does not isolate tables.

When the suite finishes, drop only the owned schema:

~~~sql
DROP SCHEMA it_a81f2c9d CASCADE;
~~~

Only execute `DROP` on schemas created by the current suite itself. Never drop the default schema or shared schemas of the test environment.

### Tenant ID or Suite ID in Data

If the application has a tenant column, the namespace can serve as the tenant ID:

~~~java
String tenantId = suiteNamespace;

Order order = new Order(
        tenantId,
        "order-" + testCaseId,
        OrderStatus.NEW
);
orderRepository.save(order);
~~~

Queries must always scope by tenant:

~~~java
List<Order> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status);
~~~

Only add a tenant ID when the schema and application logic genuinely support tenant isolation. If repositories still issue global queries, attaching a tenant ID to rows does not isolate tests on its own.

### Using Dedicated Keys Instead of Wiping the Entire Database

Avoid running full-table deletes or truncating shared schemas when multiple suites run in parallel. One suite could wipe data that another suite is asserting against.

Without a dedicated schema or tenant, generate unique IDs for test records and clean up only the records created by the test. You can use repository delete methods by ID or suite ID; avoid overly broad delete predicates.

## Redis: Dedicated Key Prefixes

Redis is often shared across many tests because an instance is lightweight and starts quickly. Using suite-based prefixes avoids collisions:

~~~java
class RedisTestKeys {

    private final String namespace;

    RedisTestKeys(String namespace) {
        this.namespace = namespace;
    }

    String order(long id) {
        return namespace + ":orders:" + id;
    }

    String session(String sessionId) {
        return namespace + ":sessions:" + sessionId;
    }
}
~~~

Tests write and read the exact key:

~~~java
String key = keys.order(42L);

redisTemplate.opsForValue().set(key, "created");

assertThat(redisTemplate.opsForValue().get(key))
        .isEqualTo("created");
~~~

During cleanup, delete only keys bearing the suite's prefix. With Redis, do not run `FLUSHALL` or `FLUSHDB` on a shared instance because they erase data belonging to other suites.

If you need to find all keys in a namespace, prefer `SCAN` with a pattern and delete in batches rather than `KEYS` in large datasets. `SCAN` avoids blocking Redis for long periods like a full keyspace scan; however, cleanup must still enforce an exact prefix and account for keys potentially created during scanning.

## Message Brokers: Dedicated Queue and Topic Names

Message brokers hold state that is difficult to roll back with standard test transactions. A published message may remain in a queue after the test ends. If multiple suites share a queue, one suite's consumer can receive messages sent by another suite.

Create queues or topics scoped by namespace:

~~~java
String queueName = suiteNamespace + "-order-events";
String topicName = suiteNamespace + "-payment-events";
~~~

Pass resource names into both consumer and producer configuration for the suite. Both must use the exact same namespace; if the producer publishes to queue A while the consumer listens on queue B, the test will hang until timeout even though the message was sent.

With Kafka, dedicated topic names avoid another suite's consumer groups and retained records. With RabbitMQ, dedicated queues/exchanges scope messages and bindings per suite. Check broker naming rules, length limits, and resource creation permissions.

Cleanup should delete queues/topics or purge only resources owned by the suite. If the broker deletes resources asynchronously or consumers are still connected, wait for cleanup to complete before ending the suite or reusing names.

Do not share a single fixed queue name across concurrent pipelines without message partitioning. Only one consumer might receive a message another test is waiting for, causing non-deterministic results.

## Object Storage and Filesystem

With S3-compatible storage, buckets have strict naming rules and creating buckets arbitrarily per test method may not be allowed. A common approach is a dedicated bucket per suite or prefixed object keys:

~~~text
bucket: integration-test-artifacts
object key:
  it_a81f2c9d/reports/42.json
  it_a81f2c9d/uploads/avatar.png
~~~

During cleanup, list and delete objects under the suite's prefix, then delete the bucket if the suite created it. Ensure objects belonging to other prefixes are never deleted.

With the filesystem, create a dedicated temporary directory per suite or test:

~~~java
Path suiteDirectory = Files.createTempDirectory("it-a81f2c9d-");
Path report = suiteDirectory.resolve("reports/report.json");
~~~

Using temporary directories prevents filename collisions across tests and allows cleanup under a specific root. When tests use JUnit Jupiter `TempDir`, the framework manages the temporary directory lifecycle for the declared scope; still verify that tests do not write files outside that directory.

## Namespace-Scoped Cleanup at the Right Lifecycle

Namespaces identify which suite owns which data, enabling targeted cleanup. Choose one of the following points:

- After each test method if data belongs solely to that method.
- After each test class if methods in the class share fixtures.
- After the entire suite if the namespace represents a test group or an application context.

Cleanup must run even when assertions fail. JUnit Jupiter provides `AfterEach` and `AfterAll`; resources can be managed by an extension or an `AutoCloseable` fixture to close in the proper lifecycle.

Example:

~~~java
class NamespacedRedisTests {

    static final String SUITE_ID = TestNamespace.newSuiteId();
    RedisTestKeys keys = new RedisTestKeys(SUITE_ID);

    @AfterAll
    static void cleanSuiteData() {
        redisCleanup.deleteByPrefix(SUITE_ID + ":");
    }
}
~~~

This illustrates where cleanup belongs; in real tests, cleanup dependencies must be injected or accessed through an appropriate fixture. Avoid `static` methods if dependencies lack static lifecycles; in that case use `TestInstance(PER_CLASS)`, an extension, or a resource manager closed in `AfterAll`.

If cleanup is asynchronous, do not exit the test immediately after issuing a delete command. Wait for a completion signal or verify the resource is gone within a finite timeout. If the next suite could reuse names, incomplete cleanup will cause conflicts.

### Cleanup Failures Must Not Mask Test Failures

If a test assertion already failed and cleanup also throws an exception, the final report might show only the cleanup error and hide the primary cause. Log cleanup errors and attach them as suppressed exceptions, or use a lifecycle helper that reports errors clearly. Do not silently ignore cleanup errors, as leftover resources can affect subsequent runs.

## Namespaces in Parallel Tests

A suite namespace only isolates suites from each other. If multiple test methods within the same suite run concurrently, they can still collide on keys if they share a fixed ID.

You can generate test-level keys:

~~~java
String testKey = suiteNamespace + ":"
        + testInfo.getTestMethod().orElseThrow().getName()
        + ":"
        + UUID.randomUUID();
~~~

JUnit Jupiter can inject `TestInfo` into lifecycle methods or test methods. Combining the method name with a UUID keeps logs readable while reducing collision risk. If you want to rerun a test with the same data for debugging, use the test method name plus a run ID that stays stable within that run.

Do not use the method name alone as a unique key if the test is parameterized, repeated, or has multiple concurrent invocations. Invocations can share the same method name; append an invocation index or token when distinction is needed.

Another option is a dedicated fixture per method, such as creating a fresh key prefix in `BeforeEach` and deleting it in `AfterEach`. Ensure the code under test receives that exact prefix via dependency injection or parameters; never rely on mutable global variables that another test can overwrite.

## Do Not Confuse Data Namespaces with Transaction Isolation

Spring tests can run test methods inside a transaction and roll back after completion. This works well for database rows written within the same transaction managed by the test. However, rollback does not automatically clean up all resource types:

- Messages already published to a broker may already have been consumed elsewhere.
- Redis commands take effect independently of database transactions.
- Files or objects written to storage remain in place.
- An external HTTP service may already have processed the request and persisted side effects.
- Async tasks may continue running after the test transaction rolls back.

A dedicated namespace provides a useful isolation layer for these resources. Transaction rollback and namespaces solve two different problems: rollback undoes changes inside a transaction; namespaces partition data and resources across systems with independent lifecycles.

If the application uses a transactional outbox, one test can inspect the outbox row inside a transaction while another test verifies the publisher/consumer. When end-to-end tests publish real messages, use dedicated topics/queues and clean up messages/resources by namespace.

## Common Mistakes

### Using One Fixed Name for Every Suite

Two pipelines creating the same queue or key can overwrite, consume, or delete each other's data. Generate a unique namespace for each suite or build.

### Generating a New Namespace on Every Read

Producers, consumers, and cleanup may receive three different namespaces. Generate the token once and share it via fixtures and Spring properties.

### Using Only a Suite ID When Methods Run in Parallel

Methods in the same suite can still write to the same key. Add test keys or per-invocation fixtures.

### Using UUIDs Unnecessarily for Every Business ID

Test data becomes hard to read and reproduce. Keep business IDs readable inside a dedicated namespace, such as `suite:orders:42`; only the namespace token needs to be unique.

### Cleaning Up with Global Wipe Commands

`FLUSHDB`, truncating shared schemas, or purging shared queues can destroy another suite's data. Delete by prefix, schema, tenant, or resources owned by the suite.

### Thinking Database Rollback Cleans Up Brokers or Storage

Database transactions do not cover message brokers, Redis, the filesystem, or object storage. These resources need their own namespaces and cleanup.

### Changing the Namespace After the Spring Context Is Cached

Singleton beans may continue using the old property. Fix the namespace per context lifecycle or create a new context when a different namespace is required.

### Creating Names That Violate Service Rules

Overly long names or invalid characters can cause resource creation to fail. Normalize names and check backend limits before use.

## Workflow for Designing Dedicated Data per Suite

1. List all stateful systems used by the suite: databases, caches, brokers, storage, and HTTP services.
2. Choose the isolation scope per system: database/schema/tenant, key prefix, queue/topic, bucket/object prefix, or directory.
3. Generate a unique suite namespace and keep it stable for the suite's lifecycle.
4. Create dedicated test keys if methods or invocations within the suite can run in parallel.
5. Pass the namespace via fixtures or Spring configuration; do not regenerate or re-derive tokens in individual beans.
6. Create namespaced resources and data before tests issue requests or queries.
7. Assert data within the matching namespace, avoiding global queries that could observe another suite's data.
8. Clean up by namespace at the right lifecycle phase and wait for asynchronous cleanup to complete.
9. When running in parallel, do not share mutable resources if one test's reset or cleanup can affect another test.

Dedicated named or keyed data allows multiple test suites to share infrastructure while maintaining clear ownership boundaries. A stable suite namespace, per-test keys when needed, and properly scoped cleanup reduce data collisions, make parallel execution safer, and make CI failures easier to trace.
