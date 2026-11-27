# Cleaning Up Resources and Preventing Test Data Pollution Across Runs

Service discovery tests often start multiple resources outside the test process: registries, mock providers, databases, message brokers, containers, Kubernetes namespaces, and HTTP connections. If you only verify assertions without managing the lifecycle of these resources, subsequent runs may read stale registrations, reuse instance IDs, hit occupied ports, or receive data created by another test.

The problem intensifies when running tests in parallel on developer machines and in CI. Two tests might register `inventory-service` simultaneously, share a single Consul catalog, or delete the same znode. As a result, tests become flaky, hard to reproduce, and leave leftover data in shared environments.

This lesson explains how to structure setup/teardown, isolate registries and test data, manage Testcontainers and Spring ApplicationContexts, handle provider-specific registrations, and apply principles so tests remain repeatable and safe in parallel.

## 1. Which resources need management?

A service discovery test can create many kinds of resources:

| Resource | Example | Risk if not cleaned up |
| --- | --- | --- |
| Registry server/container | Consul, Eureka, ZooKeeper | Container/process stays running, holding ports and memory |
| Service registration | `inventory-service` instance `test-1` | Subsequent consumer tests see stale instances |
| Discovery cache/watch | Curator `ServiceCache`, Kubernetes informer | Listeners/threads hold stale references or snapshots |
| HTTP client/connection pool | WebClient, Reactor Netty | Sockets, event loops, and connections remain open |
| Spring ApplicationContext | Beans, schedulers, listeners, clients | Context keeps connections to a stopped container |
| Database/test data | Rows, schemas, collections | Subsequent tests read data from earlier runs |
| Message broker | Topics, queues, consumer groups | Old messages are consumed in new tests |
| Temp files and directories | Logs, configs, snapshots | Stale files affect assertions or leak data |
| Kubernetes resources | Namespaces, Services, ConfigMaps, Secrets | Resources linger after tests finish |

Every resource needs an owner, creation time, usage scope, and a close/delete mechanism. Without clear ownership, it is easy to accidentally delete resources belonging to another test or a developer environment.

## 2. Principles for designing cleanup

A solid test workflow should follow these principles:

1. **Create resources in the narrowest scope:** method, class, suite, or full test run depending on startup cost.
2. **Assign unique identities:** service ID, instance ID, namespace, topic, and schema must be distinct across tests/runs.
3. **Register cleanup immediately upon creation:** if a subsequent setup step fails, already-created resources must still be cleaned up.
4. **Clean up strictly by ownership:** delete only registrations/resources created by the current test.
5. **Close in reverse dependency order:** stop consumers/clients before the registries/containers they connect to.
6. **Avoid test order dependencies:** each test creates its own required data without relying on an earlier test.
7. **Make cleanup idempotent:** running it twice must not corrupt state or delete unrelated data.
8. **Do not mask test failures with teardown errors:** preserve both the primary failure and cleanup errors for diagnosis.

A useful convention is giving each test run a `runId` and each test case a `caseId`, embedding them into every nameable resource:

```text
runId  = ci-4821-7f2a
caseId = register-two-instances

serviceId  = inventory-test-ci-4821-7f2a-register-two-instances
instanceId = inventory-ci-4821-7f2a-register-two-instances-01
namespace  = sd-ci-4821-7f2a-register-two-instances
```

Example names must be shortened and normalized according to provider constraints. Never use a fixed ID such as `test-service` when multiple tests may run concurrently.

## 3. Choosing lifecycle scope: method, class, or suite

Not every resource needs to be created and destroyed per test method. Creating too many registry containers slows down the suite; sharing one registry without data isolation causes cross-test pollution.

| Scope | How to manage | When suitable |
| --- | --- | --- |
| Method | `@BeforeEach` / `@AfterEach`, try-with-resources | Cheap resources, data must be completely clean per case |
| Class | `@BeforeAll` / `@AfterAll`, static Testcontainer | Multiple methods share a registry/container while registrations stay isolated |
| Suite | Singleton container or suite fixture | Heavy containers, multiple classes need the same registry server |
| Test run/CI job | Ephemeral job infrastructure, dedicated namespace or project | Multi-service integration tests and large datasets |

A resource may be shared at the server layer while data inside it remains isolated per test. For example, a Consul container shared across a class can serve multiple methods; each method must use its own service ID/instance ID and deregister afterward.

Do not pick a broader scope solely to cut startup time unless reliable data isolation and cleanup mechanisms are in place.

## 4. Using JUnit 5 to close resources reliably

For resources implementing `AutoCloseable`, prefer try-with-resources. Java invokes `close()` even when intermediate assertions or operations throw exceptions:

```java
@Test
void readsServiceInstances() throws Exception {
    try (TestingServer server = new TestingServer()) {
        // Create Curator client, register service, and run assertions.
    }
}
```

For resources spanning multiple methods, use `@BeforeAll`/`@AfterAll` or a JUnit extension. Place per-test cleanup in `@AfterEach` so it runs after every test even if an assertion fails:

```java
class DiscoveryRegistrationTest {

    private RegistryFixture registry;
    private String serviceId;
    private String instanceId;

    @BeforeEach
    void setUp() {
        registry = RegistryFixture.start();
        serviceId = "inventory-test-" + UUID.randomUUID();
        instanceId = serviceId + "-instance-1";
    }

    @AfterEach
    void tearDown() {
        if (registry != null) {
            registry.deregister(serviceId, instanceId);
            registry.close();
        }
    }
}
```

The snippet above illustrates the pattern; `RegistryFixture` is a helper defined by your test suite. If `deregister` can throw an exception, ensure `close()` still executes using `try/finally` or let the fixture manage both operations internally.

A safer teardown pattern:

```java
@AfterEach
void tearDown() {
    try {
        if (registry != null) {
            registry.deregister(serviceId, instanceId);
        }
    } finally {
        if (registry != null) {
            registry.close();
        }
    }
}
```

When multiple resources depend on one another, close them in reverse creation order. For example: stop the service cache/listeners, close the Curator client, and only then stop the ZooKeeper server.

## 5. Testcontainers for real registries

Mocks make consumer logic tests fast, but certain bugs only appear when talking to a real registry: protocols, health APIs, ACLs, sessions, registration lifecycles, and networking. Testcontainers can start registries inside isolated containers.

Example running a Consul agent in development mode for integration tests:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ConsulDiscoveryIntegrationTest {

    @Container
    static final GenericContainer<?> consul =
            new GenericContainer<>(DockerImageName.parse("hashicorp/consul:1.20"))
                    .withCommand("agent", "-dev", "-client=0.0.0.0")
                    .withExposedPorts(8500);

    @DynamicPropertySource
    static void consulProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.consul.host", consul::getHost);
        registry.add("spring.cloud.consul.port",
                () -> consul.getMappedPort(8500));
    }

    @Test
    void registersAndDiscoversService() {
        // Start application context and verify registration.
    }
}
```

This is a test configuration example; pin the image tag to a version verified by your project. Never use Consul `-dev` for production or security tests because it does not fully simulate ACL, TLS, and quorum configurations.

A static `@Container` keeps the container at class scope. If sharing a container across multiple classes, use a suite-level singleton fixture or an equivalent lifecycle manager. Never enable reusable containers arbitrarily in CI: reused containers can retain catalogs, tokens, configs, and data from prior runs.

### Note on Spring TestContext caching

Spring TestContext can cache `ApplicationContext` instances across test classes. If a container stops after the first class while the context stays cached and reused, HTTP client/discovery client beans may keep pointing at the stopped container.

There are two approaches:

- Give the container a lifecycle at least as long as all `ApplicationContext` instances referencing it.
- Mark the context to close after the class with `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)` when a fixture truly requires its own context.

`@DirtiesContext` closes the context; it does not automatically delete registrations, topics, database rows, or resources created on external systems. That external data still requires explicit cleanup.

## 6. Dynamic properties and random ports

Never hard-code test registry ports. Testcontainers maps ports dynamically on the host; `@DynamicPropertySource` passes the actual address into the Spring context:

```java
@DynamicPropertySource
static void registryProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cloud.consul.host", consul::getHost);
    registry.add("spring.cloud.consul.port", () -> consul.getMappedPort(8500));
}
```

For Eureka or mock service providers, apply the same principle: the server listens on a random port, and the test reads the active port and injects it into configuration. This avoids conflicts when multiple tests run concurrently or when a developer machine already has a service occupying the default port.

Never write dynamic endpoints into shared repository config files. Pass them through test-scoped property sources and close contexts/clients when done.

## 7. Isolating service IDs and instance IDs

A registry is stateful outside the ApplicationContext. Two tests registering the same service ID can see each other's registrations even when each test creates its own Spring context.

Generate unique identities per test:

```java
class TestIdentity {
    static String newServiceId(String base) {
        return base + "-test-" + UUID.randomUUID();
    }

    static String newInstanceId(String serviceId) {
        return serviceId + "-" + UUID.randomUUID();
    }
}
```

If a provider restricts service IDs to a specific format, normalize the string before registering:

- Convert to lowercase if the provider is case-sensitive.
- Replace disallowed characters with hyphens.
- Enforce length limits per provider rules.
- Avoid embedding emails, usernames, or personal data in IDs.
- Keep `runId` for traceability, but never use random IDs as metric labels.

Do not make only the instance ID unique while forgetting the service ID. Consumers query by service ID; if two tests both use `inventory-service`, each test may observe the other's instances.

## 8. Cleaning up registrations in Consul

Consul exposes a service catalog and an agent API. When tests register services directly, deregister the exact `serviceId` owned by the test. If Spring Cloud Consul registers automatically, understand the deregistration lifecycle of your version and still add fallback cleanup in case a test terminates abnormally.

Example calling the agent API to deregister a test-created service ID:

```java
void deregisterConsulService(RestClient client, String serviceId) {
    client.delete()
            .uri("/v1/agent/service/deregister/{id}", serviceId)
            .retrieve()
            .toBodilessEntity();
}
```

`RestClient` should be configured with a base URL pointing to the test's Consul agent. When ACLs are enabled, the client needs an appropriately scoped token; never log tokens. Only invoke the endpoint with IDs created by the current test.

Key reminders:

- Deregistering via the agent API is not the same as wiping the entire service catalog.
- Never call `DELETE /v1/agent/service/deregister/<id>` with an ID shared by a developer environment.
- When using Spring Cloud auto-registration, close the application context properly so the framework deregisters the registration.
- If the agent/registry container stops immediately afterward, deregistering may be moot; still close clients cleanly and wait for the container to stop.
- For parallel tests, each method needs its own ID and must clean up only its own ID.

## 9. Cleaning up registrations in Eureka

Eureka clients register instances and typically deregister during application shutdown per client lifecycle. Tests must close Spring contexts/clients before stopping the Eureka server.

If tests invoke the Eureka REST API directly, delete only the specific test instance by its created application name and instance ID. Never delete the entire application name if other tests share the same registry.

With a suite-shared Eureka server:

1. Generate a distinct application/service ID per test run when suitable for the test goal.
2. Generate a unique instance ID per instance.
3. Wait for the registration to appear before running assertions.
4. Close the client/context or deregister the specific instance.
5. Wait for the registry to reflect removal if subsequent tests depend on that outcome.

Eureka has caching and propagation delays; do not assume an instance disappears instantly from every consumer after one deregister call. Use Awaitility with a bounded timeout to wait for convergence instead of a fixed `Thread.sleep()`.

## 10. Cleaning up znodes and Curator

For ZooKeeper, give each test its own root path, for example:

```text
/tests/<runId>/<caseId>/services/inventory-service/<instanceId>
```

When using ephemeral znodes, closing the session/client removes ephemeral nodes tied to that session. However, persistent parent/root paths may remain and need cleanup if the test created them.

Example deleting only the test root:

```java
void deleteTestRoot(CuratorFramework client, String testRoot) throws Exception {
    if (client.checkExists().forPath(testRoot) != null) {
        client.delete()
                .guaranteed()
                .deletingChildrenIfNeeded()
                .forPath(testRoot);
    }
}
```

Only pass a `testRoot` owned by the current test. Never run recursive deletes on `/services`, `/`, or shared parent paths. When tests run in parallel, separate root paths prevent one test from deleting another test's znodes.

Close in order:

1. Close `ServiceCache`/`CuratorCache` and listeners.
2. Delete the persistent test root if needed.
3. Close the `CuratorFramework` client so the session and ephemeral nodes are released.
4. Stop `TestingServer` or the ZooKeeper container.

If a test is verifying session expiration, do not delete ephemeral nodes before asserting; let the server/session behavior run first, then clean up the persistent root afterward.

## 11. Cleaning up Kubernetes resources

For Kubernetes integration tests, create a dedicated namespace per test class or test run:

```text
sd-test-<runId>-<caseId>
```

Place Services, Deployments, ConfigMaps, Secrets, and other namespaced resources inside that namespace. When the test finishes, delete the namespace and wait for `Terminating` to complete before reusing the name.

Principles:

- Use a dedicated namespace instead of deleting Services/Pods by broad labels in a shared namespace.
- Label resources with `test-run-id` and `test-case-id` for traceability.
- Avoid creating ClusterRoles, CRDs, or cluster-scoped resources unless required; those are not deleted when a namespace is removed.
- Never delete developer namespaces or the `default` namespace.
- If the API server fails transiently, cleanup should retry with bounds and clearly report remaining resources.
- When testing ServiceAccounts/RBAC, grant least privilege and delete test-created ServiceAccounts/RoleBindings.

If sharing one namespace across an entire suite, isolate resource names and clean up by test UID/labels. A namespace per run is usually easier to debug and safer during parallel CI runs.

## 12. Using Awaitility instead of fixed sleeps

Registries typically update asynchronously. After registration, deregistration, or watch reconnects, immediate assertions may run before state converges.

Example waiting for a service to appear:

```java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);
            assertThat(instances).hasSize(1);
        });
```

Example waiting for an instance to disappear after deregistration:

```java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(discoveryClient.getInstances(serviceId)).isEmpty());
```

Awaitility requires a bounded timeout and helpful failure messages. Do not set excessively long wait times that hide registration bugs; on timeout, print the service ID, instance ID, provider, and observed registry state.

`Thread.sleep()` can be used in tests specifically verifying timing/leases for an explicit reason, but never use it to guess when a registry has updated.

## 13. Cleaning up HTTP clients, schedulers, and listeners

Tests may create `WebClient` instances, Reactor Netty `ConnectionProvider`s, schedulers, executors, watch listeners, or event listeners. Close these resources according to ownership.

- Use Spring-managed beans if the client belongs to an ApplicationContext.
- Use `@PreDestroy`, `DisposableBean`, or `destroyMethod` for resource beans that have `close`/`dispose`.
- Close `ServiceCache`/`CuratorCache` before the Curator client.
- Dispose test-created `ConnectionProvider`s; never dispose global shared Reactor Netty resources that the test does not own.
- Shut down test-created schedulers/executors and await task termination with a timeout.
- Cancel subscriptions/listeners before stopping the registry.

Example managing a self-created Reactor Netty resource:

```java
@Test
void usesDedicatedConnectionPool() {
    ConnectionProvider provider = ConnectionProvider.create("test-pool", 10);
    try {
        HttpClient client = HttpClient.create(provider);
        // Send requests and run assertions.
    } finally {
        provider.dispose();
    }
}
```

Never call `dispose()` on shared framework-managed resources. Before closing anything, establish who created it and who owns its lifecycle.

## 14. Isolating databases, message brokers, and the filesystem

Service discovery tests often involve test data in business dependencies. Cleaning up the registry alone is insufficient if later tests read database rows or messages left by earlier tests.

### Database

- Use a separate database/schema per test run whenever possible.
- For test methods, transaction rollback works for synchronous operations on the same transaction.
- Transaction rollback does not undo side effects committed on another thread, message broker, or external service.
- For async integration tests, use unique fixture IDs and clean up by fixture ID.
- Never `TRUNCATE` a shared table while another test is running.

### Message broker

- Use uniquely named topics, queues, and consumer groups.
- Drain or purge messages only within topics/queues owned by the test.
- Stop consumers and wait for workers to finish before deleting resources.
- Never share a consumer group across parallel tests if each test expects to receive every message independently.

### Filesystem

- Use JUnit's `@TempDir` for temporary files.
- Never write test artifacts into shared developer working directories.
- Never use fixed filenames when tests run in parallel.
- Ensure streams/file handles are closed before directories are deleted.

JUnit example:

```java
@Test
void writesDiscoverySnapshot(@TempDir Path tempDir) throws IOException {
    Path snapshot = tempDir.resolve("registry-snapshot.json");
    Files.writeString(snapshot, "{}", StandardCharsets.UTF_8);
    assertThat(Files.exists(snapshot)).isTrue();
}
```

JUnit deletes the temporary directory automatically after the test. Do not create a fixed directory under `target/test-data` and leave stale data across runs without a reset mechanism.

## 15. Preventing data collisions in parallel runs

Parallel-safe tests must be independent in both data and resources. Using a `UUID` for service IDs while still sharing a znode root or mutable Consul token is not enough.

Checklist for parallel tests:

- Each test has its own run ID/case ID.
- Service IDs and instance IDs never collide.
- Namespaces, znode roots, topics, queues, schemas, and temp directories are separate.
- Never mutate a shared registry configuration while another test is running.
- Never delete resources via broad selectors like `app=inventory-service` if other tests share that label.
- Never store registration state in mutable static fields across tests.
- Never depend on test order or cleanup order.
- Use locks only when truly forced to share an un-isolatable resource; locks must have timeouts and clear scope.

If a test cannot run safely in parallel, mark it clearly and configure JUnit/Surefire to restrict concurrency for that group. That is a deliberate choice; avoid disabling parallel execution for the entire suite just because one shared fixture was poorly designed.

## 16. Context caching and `@DirtiesContext`

Spring TestContext caches ApplicationContexts by test configuration. This cuts startup overhead, yet state inside singleton beans can persist across methods/classes.

For instance, a bean holding a registration list or mock state can expose prior test data to a later test even while the registry container keeps running.

Best practices:

- Reset bean/spy/mock state per test when needed.
- Never store instance lists in static fields.
- Generate separate service IDs per test.
- Use `@DirtiesContext` when a test mutates singleton configuration or resources that cannot be reset safely.
- Never treat `@DirtiesContext` as a way to wipe external data; it only manages the Spring context.
- Ensure containers/registries outlive any cached context referencing them.

`@DirtiesContext` reduces context reuse and can slow down suites. Use it only when a test genuinely dirties the ApplicationContext or when closing the context is needed to trigger lifecycle cleanup.

## 17. Cleaning up when setup fails mid-way

Multi-step setup can fail at step 4 after already starting a registry, registering a service, and opening a client. If cleanup only sits at the end of the test body, execution may never reach it.

Register cleanup immediately as each resource is created:

```java
List<AutoCloseable> resources = new ArrayList<>();

try {
    TestingServer server = new TestingServer();
    resources.add(server);

    CuratorFramework client = createClient(server.getConnectString());
    client.start();
    resources.add(client);

    ServiceCache cache = createServiceCache(client);
    cache.start();
    resources.add(cache);

    // Run assertions.
} finally {
    for (int i = resources.size() - 1; i >= 0; i--) {
        try {
            resources.get(i).close();
        } catch (Exception cleanupError) {
            // Record cleanup failure; do not silently ignore.
        }
    }
}
```

In production test code, use a helper/fixture that retains and reports cleanup exceptions. The compact snippet above illustrates registering resources right after creation and closing them in reverse order. Never leave empty `catch` blocks in real test suites; attach cleanup errors to test results or log them clearly.

If setup fails before cleanup is registered, resources can leak. Therefore, factories/fixtures should create a resource and register its close action in one atomic step.

## 18. Making cleanup idempotent and observable

Cleanup sometimes runs after a resource has already expired or its container has stopped. Deleting an already-gone resource should be handled safely per provider semantics.

Examples:

- Deregistering an instance that already vanished: treat as already clean if the provider returns not-found per expected semantics.
- Deleting a non-existent test root: complete normally.
- Closing an already-closed client: do not break test teardown.
- Deleting a terminating namespace: wait for final state with a timeout; if it times out, report remaining resources.

Log cleanup failures with `runId`, `caseId`, resource type, and resource ID. Never log secrets/tokens. A passing test that leaves behind stale registrations is still a broken test.

## 19. Comprehensive fixture example for registry tests

A fixture can bundle test identity, registration, and cleanup in one place:

```java
public final class DiscoveryTestFixture implements AutoCloseable {

    private final RegistryAdmin registry;
    private final String serviceId;
    private final String instanceId;
    private boolean registered;

    public DiscoveryTestFixture(RegistryAdmin registry, String baseName) {
        this.registry = registry;
        String suffix = UUID.randomUUID().toString().replace("-", "");
        this.serviceId = baseName + "-test-" + suffix;
        this.instanceId = serviceId + "-instance-1";
    }

    public void register(ServiceInstanceData instance) {
        registry.register(serviceId, instanceId, instance);
        registered = true;
    }

    public String serviceId() {
        return serviceId;
    }

    public String instanceId() {
        return instanceId;
    }

    @Override
    public void close() {
        if (registered) {
            registry.deregister(serviceId, instanceId);
            registered = false;
        }
    }
}
```

`RegistryAdmin` and `ServiceInstanceData` are test-suite-defined abstractions, not built-in Spring Cloud classes. The fixture deletes only the exact service/instance it registered. When providers have eventual consistency, tests still need to wait for the discovery view to update after `close()`.

You can use the fixture with try-with-resources:

```java
try (DiscoveryTestFixture fixture =
             new DiscoveryTestFixture(registryAdmin, "inventory")) {
    fixture.register(instanceData);
    await().untilAsserted(() ->
            assertThat(discoveryClient.getInstances(fixture.serviceId()))
                    .hasSize(1));
}
```

## 20. Repeatable test workflow in CI

A CI job can follow this sequence:

1. Generate a unique `runId` from the job/build ID.
2. Start registries/databases/brokers via Testcontainers or ephemeral job infrastructure.
3. Wait for container health endpoints to become ready.
4. Inject endpoints/ports into the Spring context via `@DynamicPropertySource`.
5. Have each test create its own service ID, instance ID, and test data.
6. Wait for registration/discovery convergence using bounded polling.
7. Run assertions and capture logs/metrics on failure.
8. Deregister test registrations, delete test data, and close clients/listeners.
9. Close the Spring context if required by the fixture, then stop containers in order.
10. Check for leftover resources by run ID and fail if any remain.

If tests fail, CI should capture registry/container logs before stopping them to aid investigation. Retaining log artifacts is fine, but never retain stale registrations or secrets from previous runs.

## 21. Common issues

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Next test sees previous test's instance | Missing deregistration or shared service ID | Use unique IDs and clean up by ownership |
| Passes alone, fails in parallel | Shared namespace/znode/topic/ID | Isolate all external resources per run/case |
| `Connection refused` in a later test class | Container stopped while Spring context remained cached | Adjust container scope or add `@DirtiesContext` |
| Port already in use | Hard-coded port or lingering process | Use random port mapping and clean up processes/containers |
| Flaky test right after registration | Assertion ran before registry converged | Use Awaitility with a bounded timeout |
| Znode lingers after test | Persistent parent/root was not deleted | Use a dedicated test root and delete only that root recursively |
| Consul catalog holds stale services | Missing deregistration or client stopped while agent kept state | Deregister test service ID and verify catalog |
| Kubernetes namespace stuck `Terminating` | Finalizers or unremoved resources | Wait with timeout, inspect finalizers, and report leftover resources |
| Database test reads stale rows | Rollback did not cover external/async commits | Use separate schemas/fixture IDs and explicit cleanup |
| Reactor threads stay alive after test | ConnectionProvider/scheduler/listener undisposed | Close test-owned resources in proper order |
| Cleanup deletes another test's data | Overly broad selector or parent path | Delete by test-specific resource ID/root |
| CI tests depend on prior runs | Reusable containers or stateful volumes | Use ephemeral containers and reset data |

## 22. Pre-completion test checklist

- [ ] Every container, server, client, listener, and executor has an owner.
- [ ] Resources are created in the appropriate method/class/suite scope.
- [ ] Containers outlive any Spring ApplicationContexts referencing them.
- [ ] Every test/run has a distinct service ID and instance ID.
- [ ] Registry registrations are deregistered for the exact test-created instances.
- [ ] ZooKeeper persistent test roots or Kubernetes namespaces are cleaned up.
- [ ] Database, broker, and filesystem test data are isolated.
- [ ] Cleanup runs even when assertions or setup fail.
- [ ] Resources close in reverse dependency order.
- [ ] Cleanup is idempotent and reports any leftover resources.
- [ ] Awaitility uses bounded timeouts for asynchronous state.
- [ ] Parallel tests share no mutable state or resource names.
- [ ] `@DirtiesContext` is used only when closing/resetting the ApplicationContext is needed.
- [ ] CI uses ephemeral registries/containers or a verified reset strategy.
- [ ] Error logs retain `runId`/`caseId` without exposing tokens or secrets.

Service discovery tests are only trustworthy when every run starts from a known state and ends by releasing all resources it created. Isolate service IDs, instance IDs, and external test data; manage the lifecycles of containers, Spring contexts, clients, and listeners according to dependencies; wait for registry convergence via bounded polling; and verify cleanup completed. These rules keep tests repeatable, support parallel execution, and prevent data from previous runs from corrupting subsequent results.
