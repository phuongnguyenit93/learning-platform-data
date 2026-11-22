# Comparing Quarkus and Micronaut Integration with the Common CRaC Model

Quarkus and Micronaut can both run Java applications from a CRaC checkpoint, though the ways they bring CRaC into the framework lifecycle have different levels of integration. Quarkus has basic CRaC support in the framework since version 2.10.0; applications can register resources using the CRaC API and must check the compatibility of underlying extensions and libraries. Micronaut provides a dedicated module io.micronaut.crac:micronaut-crac, automatically discovers beans implementing OrderedResource, coordinates callback order, and includes built-in integrations for some resources such as Hikari DataSource and Redis.

What both share is the CRaC model: before checkpoint, the application must bring resources into a snapshot-ready state; after restore, the application must recreate or verify resources that have become invalid. The framework can automatically coordinate certain components, but cannot automatically understand all business rules, tokens, leases, custom connections, or third-party libraries of an application.

## 1. The Common CRaC Model

CRaC (Coordinated Restore at Checkpoint) allows saving the state of a running Java process and restoring the process from the saved image. The image can retain much of the JVM state such as loaded classes, heap objects, and warm-up results. After restore, the process resumes from the checkpoint state instead of starting everything from scratch.

A server process typically holds resources that a checkpoint image cannot simply keep using as before:

- TCP sockets, HTTP connections, JDBC connections, and message brokers.
- File descriptors, writers, file locks, and files being written.
- Connection pools, selectors, event loops, and threads waiting on I/O.
- Tokens, sessions, leases, distributed locks, and time-limited leadership.
- Native resources or resources managed by third-party libraries.

CRaC provides an API for the application to receive notifications before checkpoint and after restore. With the org.crac compatibility API, a resource implements two callbacks:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class ClientResource implements Resource {

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Stop accepting work, drain, and release resources.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Recreate resources and verify dependencies.
    }
}
~~~

The application registers the resource with the CRaC context so the runtime invokes the callbacks:

~~~java
Core.getGlobalContext().register(clientResource);
~~~

beforeCheckpoint() is where incoming work is stopped, transactions are completed or rolled back, data is flushed, and connections are closed. afterRestore() is where new connections are created, authentication is refreshed, subscriptions are re-registered, and readiness is checked. Registering a resource does not automatically close or reopen resources; that logic must still be implemented by the application or library integration.

### 1.1. Boundary Between the CRaC API and Frameworks

Integration can be divided into three layers:

| Layer | Responsibility |
|---|---|
| CRaC runtime and API | Create checkpoint/restore, invoke callbacks, manage context, and report errors for uncheckpointable resources |
| Framework integration | Auto-register resources, coordinate bean lifecycles, manage resources the framework knows well |
| Application and business libraries | Manage custom resources, transactions, credentials, business caches, leases, idempotency, and readiness |

Framework integration reduces boilerplate code, but does not mean every library on the classpath is CRaC-aware. An extension may create internal sockets or threads without knowing when checkpoint occurs. In that case, checkpoint may fail, or restore may finish while subsequent operations still use closed connections.

## 2. Quarkus: Basic CRaC Support in the Framework

CRaC notes that Quarkus has basic CRaC support starting from Quarkus 2.10.0. Quarkus applications can run on a CRaC-supporting JDK, be warmed up, checkpointed, and restored using runtime options. The common integration model is creating a CDI bean that owns the resource, implementing org.crac.Resource, and registering that bean with the global context.

### 2.1. Registering a Resource with a CDI Bean

With Quarkus, you can use @ApplicationScoped to declare an application-wide bean, @Startup to force the bean to be initialized during startup, and @PostConstruct to register the resource after dependency injection completes.

Example:

~~~java
package example.crac;

import jakarta.annotation.PostConstruct;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;

import io.quarkus.runtime.Startup;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

@Startup
@ApplicationScoped
public class SearchClientResource implements Resource {

    @Inject
    SearchClient searchClient;

    @PostConstruct
    void registerResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        searchClient.stopAcceptingRequests();
        searchClient.drainRequests();
        searchClient.closeConnections();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        searchClient.reconnect();
        searchClient.verifyConnection();
    }
}
~~~

SearchClient is an application-defined type illustrating a client with a lifecycle. In a real application, call the official API of the HTTP client, JDBC pool, or SDK. Do not manually close internal sockets while the library still manages those sockets.

Each annotation has a specific role:

- @ApplicationScoped defines a CDI bean with application-wide scope.
- @Startup instructs Quarkus to initialize the bean during startup instead of waiting for the first time the bean is accessed.
- @PostConstruct runs after the bean and its dependencies are initialized; this is the appropriate place to register the resource.
- implements Resource brings preparation and recovery logic into the common CRaC contract.

If the bean is not initialized before checkpoint, its resource is not yet registered either. Therefore, for mandatory resources, ensure the bean is created during startup and check dependency initialization order.

### 2.2. Dependencies and Runtime

The application needs the CRaC API to compile classes implementing Resource. A typical Maven dependency:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
</dependency>
~~~

If the Quarkus BOM or project dependency management does not manage the version, declare an org.crac:crac version compatible with the CRaC JDK and framework version in use. Do not pick a random version just to get past compilation.

Run the application in JVM mode using a JDK/runtime with CRaC support. For a Quarkus application packaged as fast-jar, the command may look like:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/app/checkpoint \
     -jar target/quarkus-app/quarkus-run.jar
~~~

After the application starts and completes warm-up, a checkpoint can be requested using the JDK tool:

~~~bash
jcmd <PID> JDK.checkpoint
~~~

Restore from the image:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/app/checkpoint
~~~

This is an illustrative operational flow. Paths, OS permissions, kernel, container runtime, checkpoint engine, and compatibility limits must follow the documentation of the deployed CRaC JDK. Quarkus does not replace runtime requirements.

### 2.3. Checking Extension and Library Compatibility

A key consideration when using Quarkus is that an application often has many components integrated via extensions:

- Vert.x-based HTTP server and client.
- Database pools such as Agroal or Hikari.
- Hibernate ORM and JDBC drivers.
- Kafka clients, reactive messaging, and connectors.
- Redis clients, schedulers, telemetry agents, and native libraries.

Each component may own its own sockets, selectors, event loops, threads, or file descriptors. The fact that Quarkus has basic CRaC support does not prove that every version of these dependencies handles checkpoint/restore properly.

The CRaC guide for the Quarkus Super Heroes application illustrates a practical case: initial checkpointing encountered open sockets to PostgreSQL and Kafka, Vert.x selectors/eventfds, and other resources. The guide used CRaC-adjusted dependencies for certain Vert.x and Agroal components. The replacement coordinates in the example belong to an older workshop version set; do not copy them into a current Quarkus project. Use an appropriate Quarkus platform BOM, inspect the dependency tree, and test the exact deployed versions.

Another issue that can appear after checkpoint succeeds: the application closes the pool in beforeCheckpoint(), yet the pool does not automatically reopen after restore. In that case, the callback must call the appropriate lifecycle API or recreate the pool/client per the library version's guide. Closing resources is half the process; restoring resources is the other half.

### 2.4. Testing Quarkus

With Quarkus, test at two levels:

**Testing resource and CDI lifecycle**

- Confirm the resource bean is initialized at application startup.
- Confirm Core.getGlobalContext().register() is called.
- Test that beforeCheckpoint() stops accepting requests, drains, and closes resources.
- Test that afterRestore() creates new connections and checks dependencies.
- Test that errors and timeouts are propagated to the lifecycle instead of being ignored.

**Testing real checkpoint/restore**

- Run with a CRaC-enabled JDK on a suitable Linux environment.
- Warm up endpoints or business paths to optimize.
- Request a checkpoint using jcmd.
- Confirm the image is created and no invalid resources remain.
- Restore from the image and send requests to dependencies.
- Check databases, brokers, files, schedulers, tokens, and readiness.

Do not use a callback unit test to conclude the entire application can be checkpointed. Only running on a real runtime tests the limits of sockets, selectors, file descriptors, native libraries, and containers.

## 3. Micronaut: Dedicated CRaC Module

Micronaut provides the io.micronaut.crac:micronaut-crac module to integrate CRaC with BeanContext and the framework lifecycle. This module transitively depends on org.crac:crac, automatically registers beans implementing OrderedResource with the CRaC context, and provides several integrations for common resources.

Gradle dependency:

~~~kotlin
dependencies {
    implementation("io.micronaut.crac:micronaut-crac")
}
~~~

Maven dependency:

~~~xml
<dependency>
    <groupId>io.micronaut.crac</groupId>
    <artifactId>micronaut-crac</artifactId>
</dependency>
~~~

If the project does not use a BOM or matching dependency management, choose a module version compatible with Micronaut Framework and the CRaC JDK. Module documentation and release notes are the source for confirming APIs by version.

### 3.1. OrderedResource and Automatic Bean Registration

Micronaut CRaC defines OrderedResource, an interface extending org.crac.Resource and io.micronaut.core.order.Ordered:

~~~java
public interface OrderedResource
        extends org.crac.Resource,
                io.micronaut.core.order.Ordered {
}
~~~

The Micronaut CRaC module automatically discovers and registers beans of type OrderedResource with the CRaC context. The application focuses on writing callbacks and specifying order when dependencies exist.

Example:

~~~java
package example.micronaut;

import io.micronaut.crac.OrderedResource;
import jakarta.inject.Singleton;
import org.crac.Context;
import org.crac.Resource;

@Singleton
public class SearchClientResource implements OrderedResource {

    private final SearchClient searchClient;

    public SearchClientResource(SearchClient searchClient) {
        this.searchClient = searchClient;
    }

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        searchClient.stopAcceptingRequests();
        searchClient.drainRequests();
        searchClient.closeConnections();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        searchClient.reconnect();
        searchClient.verifyConnection();
    }
}
~~~

SearchClient is also an illustrative application-defined type. There is no need to call Core.getGlobalContext().register(this) inside this bean because Micronaut CRaC automatically registers OrderedResource.

An important distinction is that the registration mechanism is tied to BeanContext. If the application only implements org.crac.Resource without implementing OrderedResource, do not assume the module will automatically discover that bean via the default mechanism. For custom resources, implement the exact interface required by the module.

For a resource to be registered, the bean must be created before checkpoint. If the application changes singleton initialization settings or uses lazy beans, ensure the resource is materialized during startup. An eager-initialization scope suitable for the application, such as @Context, can be used if a specific bean must be forced to be created when the context starts.

### 3.2. Controlling Resource Order

When multiple resources depend on one another, Micronaut CRaC lets you use OrderedResource.getOrder() to control registration order.

For example, OrderConsumer uses DatabasePool:

- Before checkpoint, the consumer must stop before the pool is closed.
- After restore, the pool must be ready before the consumer restarts.

Arrange order according to the module's registration rules and confirm actual callback order in tests. In the standard CRaC Context model, beforeCheckpoint() runs in reverse registration order, while afterRestore() runs in registration order. Therefore, registration order should reflect the dependency graph rather than just the alphabetical order of bean names.

Do not let two resources both own and close the same client. If a pool is already managed by the module, do not create an additional separate resource closing that same pool unless coordination is explicitly defined.

### 3.3. Hikari DataSource Support

Micronaut CRaC has integration for Hikari DataSource when the pool is configured to allow suspension:

~~~yaml
datasources:
  default:
    allow-pool-suspension: true
~~~

At checkpoint, the pool is suspended and connections are closed. After restore, the pool is resumed and connections are re-established. This mechanism saves the application from writing callbacks to manage individual JDBC connections.

The condition is that the DataSource actually uses Hikari and a compatible version/configuration. If the application uses another pool or a driver with its own lifecycle, check corresponding integrations or write a custom resource.

### 3.4. Redis Support and Refresh Scope

The Micronaut CRaC module also includes integration for several Redis beans such as:

- RedisClient
- RedisCache
- StatefulRedisConnection

According to module documentation, supported beans are destroyed at checkpoint and recreated after restore. Application beans holding references to these clients/caches need to be in @Refreshable scope to receive the new instance after refresh.

Example:

~~~java
import io.micronaut.runtime.context.scope.Refreshable;

@Refreshable
public class ProductCacheService {

    private final RedisClient redisClient;

    public ProductCacheService(RedisClient redisClient) {
        this.redisClient = redisClient;
    }
}
~~~

The Redis types in the example must be imported from the project's actual Redis library. The key point is that services holding references to recreated beans must participate in refresh scope, otherwise they may continue using old references.

Micronaut CRaC emits a RefreshEvent before checkpoint to invalidate beans in @Refreshable scope. This behavior can be disabled with:

~~~yaml
crac:
  refresh-beans: false
~~~

Disable this only when the application has a replacement mechanism and you have verified no refreshable beans remain that need recreation. If default refresh is disabled while references to old clients are retained, restore may succeed but subsequent Redis operations will fail.

Redis integrations can be enabled/disabled by group or bean type using properties provided by the module, such as crac.redis.enabled, crac.redis.client-enabled, crac.redis.cache-enabled, and crac.redis.connection-enabled. Check documentation for the exact version before using these properties because the module may change property names or configuration scope across releases.

### 3.5. Events and Context Provider

Micronaut CRaC publishes the events:

- BeforeCheckpointEvent
- AfterRestoreEvent

Events contain the completion timestamp, execution duration in nanoseconds, and the processed resource. Applications can use them to log lifecycle activity, collect metrics, or trigger appropriate observability actions.

The module also provides CracContextProvider; the default implementation GlobalCracContextProvider returns the global context. Applications can replace the provider if a custom CRaC context is needed for the integration architecture.

Do not use observation events to replace resource callbacks. Events indicate that a lifecycle operation occurred; the resource remains the place that performs closing, opening, and verifying resources.

### 3.6. CheckpointSimulator and Testing

Micronaut CRaC provides CheckpointSimulator to simulate invoking callbacks before checkpoint and after restore in tests. Example:

~~~java
@Inject
BeanContext beanContext;

@Test
void resourceIsStoppedAndStartedAgain() {
    ResourceBean resource =
            beanContext.getBean(ResourceBean.class);
    CheckpointSimulator simulator =
            beanContext.getBean(CheckpointSimulator.class);

    assertTrue(resource.isRunning());

    simulator.runBeforeCheckpoint();
    assertFalse(resource.isRunning());

    simulator.runAfterRestore();
    assertTrue(resource.isRunning());
}
~~~

This example tests callback logic and bean state. CheckpointSimulator does not create a real process image, does not invoke CRIU, and does not prove all OS file descriptors or sockets can be checkpointed. An integration test with a CRaC-enabled JDK is still required to test the runtime.

Micronaut CRaC documentation also notes eager singleton initialization in applications and tests. If a test injects a bean causing a client to initialize too early, it may be necessary to disable eager initialization in tests or create the client bean lazily as appropriate. This is a distinction to watch for when designing tests for resources and HTTP clients.

### 3.7. Docker Image Build Support

Micronaut has Gradle and Maven plugins supporting building images with a CRaC JDK and a warmed-up/checkpointed application. With Gradle, plugin documentation describes the dockerBuildCrac task, which can:

1. Create a base image containing a CRaC-supporting JDK and the application.
2. Start the application.
3. Run a warm-up script.
4. Take a checkpoint.
5. Package the checkpoint together with the runtime and application into a new image.

Current plugin documentation warns of experimental status for the CRaC plugin. Check the version, tested OS, and support status before using it in a production pipeline. The plugin only assists the packaging process; it cannot fix a faulty resource callback or make an incompatible dependency safe.

## 4. Direct Comparison of Quarkus and Micronaut

| Aspect | Quarkus | Micronaut |
|---|---|---|
| Integration approach | Basic CRaC support in the framework | Dedicated CRaC module |
| Announced support milestone | Basic CRaC support from Quarkus 2.10.0 | Module io.micronaut.crac:micronaut-crac |
| Underlying API | org.crac | org.crac via the Micronaut module |
| Custom resource registration | CDI/bean implementing Resource, typically self-registering via Core.getGlobalContext() | Bean implementing OrderedResource; module auto-registers |
| Order management | By CRaC context registration order; application must organize resources | OrderedResource integrates Ordered, controllable via getOrder() |
| DataSource integration | Must verify extension, pool, and driver support; may need custom resource | Supports Hikari DataSource suspension when allow-pool-suspension is enabled |
| Redis | Check extension/client lifecycle and coordinate yourself if needed | Includes integration for RedisClient, RedisCache, and StatefulRedisConnection |
| Bean recreation | Uses CDI lifecycle and application logic; must determine how references are updated | Has @Refreshable scope and RefreshEvent to invalidate managed beans |
| Observation events | Uses CRaC callbacks and Quarkus event/observer mechanism | Has module BeforeCheckpointEvent and AfterRestoreEvent |
| Lifecycle testing | Resource/CDI tests and real checkpoint testing | Has CheckpointSimulator alongside real CRaC tests |
| Image packaging | Uses build/container pipeline and suitable CRaC JDK | Has Gradle/Maven plugin supporting checkpoint images; plugin status must be checked by version |
| Primary risk | Compatibility of extensions and dependencies in the stack | Bean references, refresh scope, and scope of module integrations |

### 4.1. Differences in Registration

Quarkus typically has beans self-register:

~~~java
@Startup
@ApplicationScoped
public class QuarkusResource implements Resource {

    @PostConstruct
    void register() {
        Core.getGlobalContext().register(this);
    }

    // beforeCheckpoint() and afterRestore()
}
~~~

Micronaut CRaC uses a bean type with a dedicated interface:

~~~java
@Singleton
public class MicronautResource implements OrderedResource {

    @Override
    public int getOrder() {
        return 100;
    }

    // beforeCheckpoint() and afterRestore()
}
~~~

This difference affects code organization. With Quarkus, the author must actively register the resource and ensure the bean is created. With Micronaut, the module handles finding and registering OrderedResource beans; the author focuses on callbacks and ordering.

### 4.2. Differences in Framework-Managed Resources

Micronaut CRaC has a list of integrations published by the module, such as Hikari and Redis. These integrations reduce the need to write callbacks for supported bean types.

Quarkus has many extensions and dependencies beneath the same application. CRaC documentation describes basic support in the framework, yet each extension/version must be checked to know which resources are already coordinated. The Super Heroes example shows that Vert.x, Agroal, and Kafka can create sockets, selectors, or connections that cause checkpoint errors if the versions in use are not yet compatible.

Do not infer that Quarkus cannot manage pools or Redis. The correct understanding is to check the specific integration of the Quarkus platform and library versions. Similarly, do not assume every Redis client or every pool in Micronaut is automatically handled by the module just because some types have integrations.

### 4.3. Differences in Testing

Micronaut has CheckpointSimulator to invoke callbacks and verify order and bean state in tests. This is convenient for fast testing of beforeCheckpoint()/afterRestore() logic.

Quarkus can test resources with JUnit and the Quarkus test lifecycle, though you must organize how callbacks are invoked or beans checked yourself. For both frameworks, simulators or unit tests only verify application logic. Only a real checkpoint/restore uncovers errors from the CRaC runtime, kernel, sockets, selectors, file descriptors, and native libraries.

## 5. Common Deployment Model for Both Frameworks

Whether choosing Quarkus or Micronaut, the same design process can be used.

### 5.1. Before Checkpoint

1. Stop accepting new requests and messages.
2. Drain running requests and internal queues.
3. Commit or roll back transactions according to business rules.
4. Stop consumers, schedulers, and workers that need to be recreated.
5. Flush file writers and close OS resources that cannot continue being used.
6. Close or suspend connection pools/clients per official API.
7. Release leases/locks if the protocol requires it.
8. Report an error if a resource cannot reach a safe state within the allowed deadline.

### 5.2. After Restore

1. Re-read configuration and metadata of the current environment.
2. Recreate sockets, connection pools, and clients.
3. Reload truststores, certificates, tokens, or secrets if they may change.
4. Recreate workers, schedulers, and consumers.
5. Rejoin broker groups or service registries.
6. Acquire new leases/locks and verify ownership using fencing tokens when needed.
7. Refresh caches that may have become stale.
8. Open readiness only after mandatory dependencies are ready.

Overall flow:

~~~mermaid
flowchart TD
    A[Framework starts application] --> B[Initialize beans and dependencies]
    B --> C[Warm up reusable state]
    C --> D[Register CRaC resources]
    D --> E[Application serves]
    E --> F[beforeCheckpoint]
    F --> G[Quiesce, drain, and close resources]
    G --> H[CRaC checkpoint]
    H --> I[CRaC restore]
    I --> J[afterRestore]
    J --> K[Recreate connections and verify state]
    K --> L[Readiness]
    L --> M[Resume serving]
~~~

Not all resources have to be recreated in the same order. If resource B depends on resource A, A must be restored before B and B must be stopped before A. Use registration order appropriate to the CRaC context or Micronaut's OrderedResource.

## 6. Managing Data and Time-Bounded State

The framework lifecycle does not replace distributed system consistency rules.

### 6.1. Cache

Caches warmed up before checkpoint can reduce startup time. However, while the JVM is stopped, source data may change or TTLs may expire. Classify them:

- Immutable or fixed-version caches: can be kept if still appropriate.
- Mutable business data caches: refresh or check versions after restore.
- Caches tied to replica identity: create a separate namespace for the current replica.
- Caches holding tokens/sessions: refresh per authentication policy.

### 6.2. IDs and Replica Identity

If the same checkpoint is used to create multiple replicas, values in the heap may be cloned. Generate or query the instance ID after restore. Do not use a static UUID generated before checkpoint as the unique ID for all replicas.

Service identity may be shared; replica identity and process incarnation ID must be distinct. Consumer member IDs, socket paths, temporary files, and lease tokens need to be reissued per ownership scope.

### 6.3. Tokens and Certificates

Access tokens, refresh tokens, client certificates, and private keys may expire or rotate while the process is stopped. After restore, fetch credentials from the identity provider or secret manager per the current workload. Do not assume a credential object in the heap is still valid.

### 6.4. Leases and Leadership

Do not keep leader=true or lock state from the checkpoint as proof of current ownership. The lease may have expired and been granted to another replica. After restore, re-register with the coordinator and use a fencing token verified at the write site.

## 7. Common Errors During Comparison and Implementation

| Symptom | Possible cause | Resolution |
|---|---|---|
| Quarkus checkpoint fails due to open socket | Extension or dependency holds unclosed socket | Identify socket owner, upgrade to compatible version, or write integration |
| Quarkus restore finishes but database unreachable | Pool closed without being recreated/resumed | Use the pool's lifecycle API or create a new pool in callback |
| Quarkus resource bean is not invoked | Bean not initialized or not registered | Use a startup bean and confirm registration completed |
| Micronaut does not invoke custom resource | Bean only implements Resource instead of OrderedResource, or bean not created | Implement OrderedResource and ensure the bean is materialized |
| Micronaut Redis service still uses old client | Bean holding reference is not in refresh scope | Place appropriate bean in @Refreshable or manage new references |
| Hikari pool does not resume | Pool does not enable suspension or unsupported config/version | Enable allow-pool-suspension and check integration |
| Callbacks run in wrong order | Resources have dependencies but registration order is incorrect | Order context registration or getOrder |
| Restore succeeds but first request fails | Readiness opened before dependencies are ready | Health check connections and only open readiness after bootstrap |
| Simulator test passes but real CRaC fails | Simulator does not create a process image and does not check OS files/sockets | Add integration tests with a CRaC JDK on Linux |
| Multiple replicas share consumer/lease identity | ID or ownership was snapshotted and cloned | Generate separate identity and acquire new leases after restore |
| Checkpoint waits indefinitely | Drain or I/O callback has no deadline | Set timeouts and a checkpoint cancellation policy |

## 8. Choosing a Framework Based on Integration Needs

Quarkus fits when the project already uses the Quarkus extension ecosystem and the team can clearly manage the dependency tree and client lifecycles. Effort must be spent checking CRaC compatibility for each extension and writing CDI resources for application-specific resources. If the application has many Vert.x, Kafka, database, or native dependencies, test checkpointing early in development.

Micronaut fits when you want to use a dedicated CRaC module tied to BeanContext, auto-registering OrderedResource, and integrations already supported by the module. Hikari/Redis support, refresh scope, events, and simulator can reduce the amount of lifecycle code to write. However, confirm exact module versions, supported client types, and scopes of beans holding references to recreated resources.

Do not choose solely based on how many lines of callback code must be written. Evaluate:

- Are the framework version and CRaC runtime supported in the target environment?
- Do the database pool, HTTP client, Redis, Kafka, and telemetry stack have appropriate integrations?
- Does the application have many custom or native resources?
- Can callbacks be tested in unit tests and real checkpoint/restore in CI?
- Do the image build pipeline and checkpoint operations fit your infrastructure?
- Can the team track versions, dependency compatibility, and lifecycle changes when upgrading the framework?

## 9. Shared Implementation Checklist

### Framework and Build

- Confirm the Quarkus or Micronaut version in use has CRaC support.
- Use the org.crac API compatible with the JDK/runtime.
- Inspect the dependency tree and extensions that create sockets, files, threads, or native resources.
- Do not copy CRaC-patched dependency versions from an old example without checking compatibility.

### Resource Lifecycle

- Each resource has a clear lifecycle owner.
- Resources are registered before checkpoint begins.
- Before-checkpoint callbacks have clear draining, timeouts, and cleanup.
- After-restore callbacks recreate connections and verify dependencies.
- Callback order reflects dependency relationships.
- Do not let two resources close the same resource.

### Application State

- Caches have a freshness policy.
- Tokens and certificates are refreshed when needed.
- Replica identity is regenerated or queried again.
- Leases and leadership are re-acquired.
- Consumers, schedulers, and workers are started exactly once.
- Readiness opens only when the application can genuinely serve.

### Testing and Operations

- Unit test each resource.
- With Micronaut, use CheckpointSimulator to test callbacks.
- Run real checkpoint/restore using a CRaC JDK in a compatible environment.
- Test error cases when databases, brokers, or secret services are unavailable.
- Restore multiple replicas from the same image if the environment scales out.
- Monitor checkpoint, restore, callback, and readiness durations.
- Protect the checkpoint image because the heap may contain tokens, passwords, and private keys.

## 10. References

- [CRaC — Quarkus integration](https://crac.org/frameworks/quarkus/): notes basic CRaC support in Quarkus starting from version 2.10.0.
- [CRaC — Micronaut integration](https://micronaut-projects.github.io/micronaut-crac/snapshot/guide/): dependencies, OrderedResource, Hikari, Redis, refresh scope, events, context provider, and CheckpointSimulator.
- [Micronaut Guide — CRaC](https://guides.micronaut.io/latest/micronaut-crac-helloworld-gradle-java.html): example Micronaut application using the CRaC module.
- [CRaC documentation — Running Quarkus Super Heroes with CRaC](https://github.com/CRaC/docs/blob/master/super-heroes.md): practical example of incompatible dependencies, sockets, selectors, and dependency replacement in a Quarkus application.
- [CRaC — What is CRaC?](https://crac.org/about/about-crac/): checkpoint/restore model and resource coordination responsibilities.
- [Quarkus — AWS Lambda SnapStart guide](https://quarkus.io/version/3.33/guides/aws-lambda-snapstart/): example of a Quarkus CDI bean implementing org.crac.Resource; this is a Lambda SnapStart integration, so Lambda's lifecycle must be distinguished from a standalone CRaC workflow.

Framework and module documentation changes across versions. When applying to a real project, prioritize documentation for the exact versions of Quarkus, Micronaut, the CRaC runtime, and the extensions in use.

## 11. Conclusion

Quarkus provides basic CRaC support in the framework and allows applications to register resources via CDI alongside the org.crac API. The area requiring attention is the compatibility of all extensions/dependencies and how each client is recreated after restore. Micronaut has a dedicated CRaC module, auto-registers OrderedResource, manages order, and provides integrations for several common resources along with a simulator tool for callbacks in tests.

Both follow the common CRaC model: prepare resources before checkpoint, restore resources after restore, and serve only when dependencies are ready. The difference lies in how much the framework automates lifecycle and built-in integrations; the application still bears responsibility for business state, credentials, identity, leases, and libraries not yet managed by the framework.
