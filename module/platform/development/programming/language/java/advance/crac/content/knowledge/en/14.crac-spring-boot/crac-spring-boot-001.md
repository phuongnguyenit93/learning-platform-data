# Requirements for Integrating Spring Framework, Spring Boot, and org.crac

Spring Framework and Spring Boot provide application structure, dependency injection, bean management, transactions, web servers, and many background components. CRaC (Coordinated Restore at Checkpoint) adds the ability to save the state of a running process and then restore that process from the checkpoint. To combine both technologies, the application must simultaneously satisfy the requirements of the CRaC JDK/runtime, the org.crac API library, the Spring version in use, and the lifecycle of Spring-managed resources.

Adding the org.crac dependency to a project only lets source code reference the CRaC API. It does not turn a regular JDK into a checkpoint/restore-capable runtime, nor does it guarantee that every bean, connection pool, web server, or thread pool in a Spring application is properly prepared. Similarly, a JDK build supporting CRaC does not automatically make every third-party library checkpoint-compatible.

Proper integration requires clearly identifying which layer provides the API, which layer performs checkpoint/restore, which component owns each resource, and who coordinates the application to stop work before checkpoint and recover after restore. This lesson presents the prerequisites to check, how to organize resources in Spring, integration examples, and a verification procedure on a real runtime.

## 1. Layers Required for Integration to Work

Integration can be viewed across four layers:

1. **Runtime and platform:** The JDK build must support CRaC; the operating system, kernel, container runtime, and checkpoint/restore tool must be compatible.
2. **CRaC API:** The application needs APIs such as Resource, Context, and Core to register resource management callbacks.
3. **Spring integration:** The Spring Framework/Spring Boot version and related libraries need a suitable way to coordinate lifecycles, via official integration or application-managed resources.
4. **Application and dependencies:** Beans, connections, threads, schedulers, caches, files, clients, and environment-dependent state must have a plan before checkpoint and after restore.

~~~text
Spring Boot Application
  |-- Controller / Service / Repository
  |-- Spring ApplicationContext and Bean lifecycle
  |-- DataSource, HTTP client, cache, scheduler, executor
  |
  +---- Spring integration or application-registered Resource
                  |
                  v
             CRaC API (org.crac)
                  |
                  v
          CRaC-enabled JDK runtime
                  |
                  v
      Operating system and checkpoint/restore mechanism
~~~

If any layer is missing, the application may build successfully yet fail to checkpoint, restore, or serve requests properly. For example, source code may compile because the org.crac dependency is on the classpath, yet the checkpoint command still fails if the running JVM is a JDK without CRaC support. Another case is a process that restores successfully while the connection pool still holds stale sockets and every database request fails.

## 2. Requirements at the JDK and Runtime Level

The first requirement is that the Java runtime actually executing the application must be a build with CRaC support. Distinguish the JDK used to compile from the JDK used to run:

- The build JDK may only need to be compatible with the source level and APIs the project uses.
- The runtime JDK must have CRaC integration to perform checkpoint and restore.
- The checkpoint creation environment and restore environment must satisfy the vendor's compatibility matrix.
- Native libraries, filesystems, networking, kernel, and container runtime must suit the checkpoint/restore mechanism.

You cannot conclude CRaC support solely from the Java version number. Two JDK builds both labeled Java 21 can still differ in vendor, build, patches, and integrated features. Verify the exact running binary using java -version, java.home, java.vendor, and the distribution's documentation.

Example inspection commands:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

In the output, record at least:

| Information | Purpose |
|---|---|
| java.vendor | Identifies the runtime vendor |
| java.version | Identifies the Java release line |
| java.home | Identifies the actual JDK/JRE being used |
| java.vm.name and java.vm.version | Identifies the JVM and build |
| os.name and os.arch | Identifies the operating system and architecture |
| Kernel and container runtime | Cross-checks platform checkpoint/restore requirements |

Inspect the IDE runtime environment, Gradle/Maven execution environment, container image, and production. A machine with multiple JDKs might use one build for compiling while the java command inside the container points to another.

Beyond the binary, check vendor requirements regarding OS, kernel, CRIU or equivalent tool, container permissions, mounts, namespaces, and how checkpoints are stored. A checkpoint is not a standalone JAR file that can be moved freely across arbitrary machines. It is tied to the runtime state and the environment that produced it.

## 3. Requirements for the org.crac Dependency

org.crac provides APIs for applications to register and implement resource lifecycles. Common types include:

- Resource: interface describing a resource needing preparation before checkpoint and recovery after restore.
- Context: context passed to callbacks.
- Core: entry point to the CRaC context, usually used to register resources into the global context.

Illustrative Gradle dependency example:

~~~groovy
dependencies {
    implementation("org.crac:crac:<compatible-version>")
}
~~~

Maven example:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version><crac-version></version>
</dependency>
~~~

The illustrative placeholder versions must be replaced with a version compatible with the CRaC JDK, Spring integration, and actual dependencies. Do not pick a version merely because it is the newest or copy one from a project using another JDK.

Some things to check:

- Is the dependency placed on the compile classpath so code can import org.crac?
- Is the API version compatible with the deployed CRaC JDK?
- Does the runtime provide or require the API under a specific packaging scheme?
- Are multiple org.crac versions pulled in via transitive dependencies?
- Was the dependency accidentally declared compileOnly or provided while runtime requires it?
- Does framework integration pull in a different API version?

Do not add multiple API versions to the classpath to test randomly. Inspect the dependency tree and vendor documentation. If the JDK distribution specifies its own way of consuming the API, follow that guidance to avoid class conflicts or inconsistent behavior.

## 4. The org.crac API and JVM Capability Are Two Different Things

org.crac is the API contract on the application side. The CRaC JVM is the runtime executing the checkpoint/restore lifecycle. The two parts are related yet do not replace each other.

For example, the following code can compile when the API dependency is present:

~~~java
import org.crac.Context;
import org.crac.Resource;

public final class ExampleResource implements Resource {
    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        // Prepare the resource.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        // Restore the resource.
    }
}
~~~

Yet compiling cleanly does not prove the JVM can checkpoint the process or will invoke callbacks. You must run the application on a supported runtime and execute a real checkpoint/restore test.

Similarly, an application may run normally on a JDK without CRaC support if libraries and the integration allow that execution mode. However, checkpoint requests will not work if the runtime lacks the required capability. Behavior when running without CRaC depends on the API, framework, and version; consult documentation rather than assuming callbacks are always no-ops.

## 5. Requirements for Spring Framework and Spring Boot Versions

Spring Framework manages ApplicationContext, bean lifecycles, dependency injection, events, transaction abstractions, and many other resources. Spring Boot adds auto-configuration, an embedded web server, startup runners, actuators, and deployment configuration. When using CRaC, determine whether the version in use has official CRaC integration support or requires the application to register Resources manually.

Do not merely look at the name Spring Boot 3 or Spring Framework 6 and conclude every component already supports CRaC. Check documentation for the exact version and exact artifacts:

- Actual Spring Boot version and Spring Framework version in the dependency tree.
- Whether an official CRaC module or integration is provided for that version.
- How to enable the integration and required properties.
- Which types of beans/resources the integration manages automatically.
- Which libraries outside Spring the integration does not cover.
- Callback rules, lifecycle order, and behavior when callbacks fail.
- Limitations by JDK, OS, and container runtime.

If Spring Boot provides CRaC integration for the version in use, follow that integration's documentation first. Avoid registering an additional self-managed Resource for the same resource already managed by the integration, because two callbacks could both close or open the same client and create a race condition.

If the version lacks a suitable integration, the application can implement its own Resources for resources it owns. Maintain a clear boundary between resources managed by Spring/the container, resources managed by libraries, and resources created manually by the application.

## 6. Spring Beans Do Not Automatically Become CRaC Resources

A Spring-managed bean has its own lifecycle such as instantiation, dependency injection, initialization callbacks, start/stop, and destruction. A CRaC Resource has two specialized callbacks:

- beforeCheckpoint(...): prepare the resource before saving process state.
- afterRestore(...): recreate or verify the resource after restoration.

A bean having @PreDestroy, DisposableBean, SmartLifecycle, or a close() method does not automatically prove that method will be called at checkpoint time. Shutdown lifecycle and checkpoint lifecycle are two different events.

There are three common ways to organize this:

1. Use Spring/Boot's official integration if the version supports it and the resource falls within integration scope.
2. Create a Spring bean implementing org.crac.Resource for application-owned resources.
3. Create a coordinator Resource orchestrating multiple owners, while each component remains responsible for closing/opening its own resources.

Do not arbitrarily close the entire ApplicationContext inside beforeCheckpoint(). Closing the context can destroy beans, stop the server, and leave the process unable to continue under the lifecycle expected by the platform. Follow the supported integration approach; if a component needs to be stopped, invoke that component's specific lifecycle API.

## 7. Registering a Resource as a Spring Bean

For applications managing resources manually, an easy-to-follow organization is creating a singleton bean implementing Resource and registering it after the bean is initialized.

Example:

~~~java
import jakarta.annotation.PostConstruct;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class CacheClientCracResource implements Resource {
    private final CacheClientLifecycle cacheClient;

    public CacheClientCracResource(CacheClientLifecycle cacheClient) {
        this.cacheClient = cacheClient;
    }

    @PostConstruct
    public void registerWithCrac() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        cacheClient.stopNewOperations();
        cacheClient.awaitOperationsToFinish();
        cacheClient.closeConnections();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        cacheClient.reconnect();
        cacheClient.verifyConnection();
    }
}
~~~

CacheClientLifecycle is an application-defined abstraction, not a Spring or CRaC API. It represents the actual owner of the cache client.

This approach has several requirements:

- The bean must be created exactly once per process.
- The Resource must be registered only once, avoiding duplicate registration on repeated context initialization.
- Injected dependencies must be ready when callbacks are invoked.
- The component must be able to stop running operations before closing connections.
- afterRestore completes only when the new client is operational and verified.
- If a callback fails, the application must report an error and not accept traffic depending on that client.

If using a Spring version older than the Jakarta namespace, initialization annotations may reside in javax.annotation instead of jakarta.annotation. Use the namespace appropriate for the project's Spring and JDK versions. Other Spring lifecycle callbacks may also be used if better suited to the application structure.

Do not register a Resource in the constructor if the constructor runs before required dependencies or state are initialized. Registering after the bean is ready reduces the risk of callbacks being invoked on a half-configured object.

## 8. Organizing a Coordinator for Multiple Beans

A Spring Boot application often has many resource groups: HTTP server, DataSource, Redis, HTTP clients, Kafka consumers, schedulers, and executors. If each bean stops independently in an unclear order, one component can close a dependency while another component is still using it.

You can organize a coordinator to execute an overall sequence:

1. Stop accepting new work.
2. Wait for running requests, message handlers, and scheduled jobs to complete.
3. Stop producers/consumers or workers per policy.
4. Ask each resource's owner to flush, close, or prepare.
5. Verify components have reached a safe state.
6. Allow checkpointing.

After restore, the order usually follows the dependency direction:

1. Reload per-instance identity and configuration.
2. Create connections, clients, and pools.
3. Verify database, cache, broker, and external services.
4. Start workers/schedulers.
5. Reopen ingress and report readiness.

Coordinator example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class ApplicationCheckpointCoordinator implements Resource {
    private final IngressLifecycle ingress;
    private final BackgroundWorkLifecycle backgroundWork;
    private final DataAccessLifecycle dataAccess;
    private final ExternalClientLifecycle externalClients;

    public ApplicationCheckpointCoordinator(
            IngressLifecycle ingress,
            BackgroundWorkLifecycle backgroundWork,
            DataAccessLifecycle dataAccess,
            ExternalClientLifecycle externalClients) {
        this.ingress = ingress;
        this.backgroundWork = backgroundWork;
        this.dataAccess = dataAccess;
        this.externalClients = externalClients;
    }

    @PostConstruct
    public void register() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        ingress.stopAcceptingNewWork();
        backgroundWork.stopSchedulingNewWork();
        ingress.awaitRequestsToFinish();
        backgroundWork.awaitInFlightWorkToFinish();
        dataAccess.prepareForCheckpoint();
        externalClients.prepareForCheckpoint();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        externalClients.restoreAndValidate();
        dataAccess.restoreAndValidate();
        backgroundWork.restoreInPausedState();
        ingress.verifyReady();
        backgroundWork.allowNewWork();
        ingress.allowNewWork();
    }

    public interface IngressLifecycle {
        void stopAcceptingNewWork() throws Exception;
        void awaitRequestsToFinish() throws Exception;
        void verifyReady() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface BackgroundWorkLifecycle {
        void stopSchedulingNewWork() throws Exception;
        void awaitInFlightWorkToFinish() throws Exception;
        void restoreInPausedState() throws Exception;
        void allowNewWork() throws Exception;
    }

    public interface DataAccessLifecycle {
        void prepareForCheckpoint() throws Exception;
        void restoreAndValidate() throws Exception;
    }

    public interface ExternalClientLifecycle {
        void prepareForCheckpoint() throws Exception;
        void restoreAndValidate() throws Exception;
    }
}
~~~

This is an architectural pattern. The lifecycle interfaces are application-defined contracts. Not every application needs a central coordinator; framework integrations or multiple independent Resources can be used. If using a coordinator, ensure no other Resource reopens ingress before the coordinator confirms all dependencies are ready.

Do not rely on Resource registration order if the API or JDK version does not guarantee callback ordering. When ordering matters, coordinate explicitly through a component with overall responsibility and test that order on a real runtime.

## 9. Integrating with DataSource and Connection Pools

Spring Boot usually creates a DataSource via auto-configuration or custom configuration. JPA providers, JdbcTemplate, and repositories may share that DataSource. Connection pools typically hold sockets to the database and have dedicated management threads.

Before checkpoint, you should:

- Stop accepting new requests and jobs that may access the database.
- Wait for running transactions to commit or roll back per policy.
- Leave no EntityManager/Session, JDBC Connection, Statement, or ResultSet mid-operation.
- Use the connection pool's CRaC integration if available.
- If the pool needs closing, perform it at the owner managing the DataSource.
- Do not let multiple beans close the same pool.

After restore, you should:

- Recreate or verify the pool according to the library's integration.
- Check connectivity to the database.
- Refresh secrets, DNS, or endpoints if they can change.
- Open requests needing the database only once the pool is operational.

Not every DataSource needs to be closed and recreated the exact same way. Some pools or drivers have CRaC integration; some need adapters; some can retain pool structure yet must discard old physical connections. Check documentation for the exact pool and driver versions.

## 10. Integrating with Web Servers and Request Lifecycles

Spring Boot can run an embedded web server. The server owns listening sockets, event loops, worker threads, and internal buffers. The application needs to identify the CRaC integration of the web server and Spring Boot version in use.

Before checkpoint, the system needs to stop accepting new requests and drain running requests. This helps:

- Complete transactions and responses.
- Run finally blocks and request context cleanup.
- Close streams or files opened per request.
- Avoid checkpointing while threads hold locks or are mid-processing.
- Set readiness to stop receiving traffic if deployment mechanisms require.

After restore, the server must be in a state capable of accepting connections. If listening sockets must be recreated, this must be performed by the server's integration or owner. Do not manually close internal sockets using reflection or by accessing private server fields.

If using a reverse proxy or load balancer, coordinate traffic draining at the orchestration layer. An instance should not report ready before the web server and essential dependencies are ready.

## 11. Integrating with Schedulers and Executors

Beans such as TaskScheduler, ScheduledExecutorService, ThreadPoolTaskExecutor, or custom executors can continue holding threads and task queues. A task may be running, pending, or scheduled in the future.

Before checkpoint:

- Stop scheduling new tasks.
- Wait for running tasks to complete or stop at batch boundaries.
- Save progress durably if tasks process data.
- Handle leases and distributed locks if tasks hold exclusive ownership.
- Do not leave tasks holding unfinished transactions, locks, or resources.

After restore:

- Recreate executors if required by the library's lifecycle.
- Recalculate schedules based on current time.
- Avoid unintentionally running expired tasks multiple times in catch-up bursts.
- Acquire new leases before running exclusive work.
- Open schedulers once dependencies and readiness are complete.

Just because you see an executor in the Spring context does not mean you must shut it down inside callbacks. If an executor is managed by the container or integration, follow the supported lifecycle. Closing an executor at the wrong moment can prevent the application from continuing after checkpoint.

## 12. Integrating with HTTP Clients, Redis, Messaging, and External Libraries

Client libraries typically hold sockets, connection pools, background threads, timers, DNS caches, TLS sessions, and buffers. A Spring bean merely injecting a client does not mean it owns all internal resources.

For each dependency, check:

- Does the version in use have official CRaC support?
- How does the library require pausing, closing, reconnecting, or reinitializing?
- Which callbacks are registered automatically?
- Does the client need to be recreated after restore?
- Which state needs refreshing: tokens, DNS, TLS, endpoints, consumer IDs, or subscriptions?
- Is any resource managed jointly by both the framework and the application?

Example:

| Component | Before checkpoint | After restore |
|---|---|---|
| HTTP client | Finish/cancel running requests, close connections if integration requires | Create or validate new connections |
| Redis client | Stop new operations, wait for running commands, handle connections | Reconnect, verify cluster and auth |
| Kafka/message consumer | Pause, handle in-flight messages, commit per policy, close client if needed | Create new consumer, rejoin group, and verify assignment |
| Scheduler | Stop new triggers and drain jobs | Recalculate schedules, acquire new lease if needed |
| Secret provider | Do not assume tokens remain valid | Refresh secrets/tokens when needed |
| Cache | Identify data that can stay vs data needing invalidation | Reconnect or refresh expired data |

Do not write a generic Resource that calls close() on every bean having a close method. Some beans are proxies, some have shared lifecycles, and some are already self-registered by libraries. Manage by owner and each library's contract.

## 13. Spring Boot Configuration and Environment-Dependent Data

An application may read configuration when ApplicationContext initializes and store results in beans or static fields. After a checkpoint is created, the restore environment may differ in hostname, IP, port, secrets, credentials, or endpoints.

Values to classify:

- **Static baseline configuration:** Business rules, mappings, immutable metadata, and configuration safe to share.
- **Per-instance configuration:** Instance ID, hostname, IP, port, pod name, and node identity.
- **Time-limited information:** Tokens, certificates, secrets, signed URLs, leases, and short-lived credentials.
- **Mutable information:** DNS, service endpoints, feature flags, and centralized configuration.

Do not embed the checkpoint-creating process's unique identity into an image shared across multiple replicas. After restore, retrieve instance info from the current environment or orchestration system. If values were cached in beans, provide a way to update or recreate beans/clients depending on those values.

Hooks such as ApplicationRunner or CommandLineRunner normally run during application startup. They can be useful for preparation or warm-up prior to checkpoint, yet do not assume they automatically re-run after every restore. Restore resumes from the saved process state, and CRaC callbacks are a separate coordination point. Put work needed after restore into the appropriate lifecycle instead of relying on booting Spring Boot from scratch.

## 14. Warm-Up and When to Create a Checkpoint

A common goal is creating a checkpoint after Spring ApplicationContext has initialized and the application has warmed up. This can preserve metadata, cache structures, and prepared JVM state.

A typical preparation workflow consists of:

1. Launch with a compatible CRaC JDK.
2. Let Spring build ApplicationContext and complete bean initialization.
3. Wait for foundational dependencies to be ready.
4. Run a representative warm-up workload, avoiding business side effects.
5. Confirm caches or baseline metadata are loaded.
6. Stop ingress and background work.
7. Prepare resources following the Resource lifecycle.
8. Create the checkpoint.

Do not checkpoint while warm-up still performs real transactions, sends emails, creates orders, or emits business messages. Use test data and safe, repeatable operations.

If a bean initializes lazily, warm-up needs to exercise the right critical business paths. A single call to a health endpoint does not guarantee all application paths have warmed up.

## 15. Managing Transactions and Persistence Context

Spring transaction management can bind transactions to the current thread and manage EntityManager/JDBC connections per transaction scope. When checkpointing, never leave active transactions or half-finished persistence contexts.

Ensure:

- Ingress and schedulers have stopped generating new work.
- In-flight requests have drained.
- Transactions have committed or rolled back.
- Application-managed EntityManager/Sessions are closed.
- Cursors, ResultSets, and query streams have finished.
- Connection pools are handled per the driver/pool integration.
- After restore, new requests create new transactions and persistence contexts.

Do not call flush() and assume the transaction has committed. Flush only synchronizes persistence context changes down to the database; the transaction can still roll back. Let the transaction manager finish transactions at business boundaries.

## 16. Handling Callback Failures and Readiness

CRaC callbacks can fail. For example, the database cannot reconnect, a secret provider times out, the Redis cluster is unavailable, or a file no longer exists.

A good application must define behavior when callbacks fail:

- Do not swallow exceptions and report restore succeeded.
- Log with resource ID, operation, and cause; avoid logging secrets.
- Use bounded timeouts and retries per policy.
- Distinguish retryable errors from configuration or incompatibility errors.
- Do not open ingress if essential dependencies are not ready.
- Allow the orchestrator to keep the instance unready or replace the failing instance.
- Avoid producing business side effects inside recovery callbacks.

Readiness must reflect actual serving capability. A process may exist yet lack database connections, consumers may not have joined groups, or the HTTP server may not have finished binding. Liveness and readiness serve different purposes; do not conflate the two signals.

## 17. Requirements When Using Official Spring Boot Integration

If the Spring Boot version provides an official CRaC module or integration, verify the following details in that exact version's documentation:

1. Which artifact must be added to the build.
2. Whether the org.crac API must be added separately or the integration declares it as a transitive dependency.
3. How to configure SpringApplication or ApplicationContext to participate in checkpoint/restore.
4. Which beans or resource types are integrated automatically.
5. Which resources the application still must register manually.
6. How the integration coordinates the web server, lifecycle, shutdown, and restore.
7. How callback failures and readiness are handled.
8. Limitations regarding JDK distribution, OS, and containers.

Do not guess artifact names or properties based on another version. Check dependency metadata and reference documentation of the exact Spring Boot release in use.

If the integration automatically manages a component, do not create an extra Resource to close/open the same resource. If the integration manages only part of it, write an adapter for the remaining part and clearly document ownership boundaries.

## 18. Requirements When Integrating Manually with org.crac

If the project lacks a suitable Spring/Boot integration, you can implement custom Resources. Before doing so, create an inventory:

| Group | Questions to answer |
|---|---|
| Web server | Who stops accepting requests and drains requests? |
| Transaction | Who confirms no active transactions remain? |
| DataSource | Who manages the pool and physical connections? |
| HTTP/Redis/Messaging | Does the library have CRaC support, and who recreates clients? |
| Executor | Who stops tasks and restarts workers? |
| Scheduler | How to avoid duplicate runs and reacquire leases? |
| File/native | Which handles need closing, flushing, or reopening? |
| Configuration | Which values must be re-read after restore? |
| Cache | Which caches can stay, and which caches need invalidation? |

Then:

- Create one Resource per owner or one coordinator responsible for orchestration.
- Register Resources exactly once per process.
- Use callbacks to execute explicit lifecycles.
- Do not use reflection into Spring or library internals to close resources.
- Test checkpoint/restore with the exact JDK and dependencies.
- Verify readiness after restore before accepting traffic.

## 19. Checking the Dependency Tree and Classpath

Spring Boot applications often have many transitive dependencies. A library may pull in a version of the org.crac API or Spring integration different from what the team thinks is in use.

With Gradle, you can inspect the dependency tree using:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency crac --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree
~~~

Check:

- Are Spring Boot plugin/BOM and Spring Framework versions aligned?
- Are there multiple versions of org.crac or CRaC integration?
- Are driver, pool, cache provider, and messaging client versions compatible?
- Is a runtime-required dependency excluded from the runtime classpath?
- Does the container image use the exact JDK runtime chosen by build/deploy?

The dependency tree only shows which libraries are on the classpath. It does not prove the runtime supports checkpointing or that libraries handle resources properly. You still must test on a real CRaC runtime.

## 20. Verification Procedure from Build to Restore

A verification workflow can be split into layers:

### Step 1: Verify the runtime

Record vendor, version, build, java.home, OS, architecture, kernel, and checkpoint/restore tool. Cross-check against vendor documentation.

### Step 2: Verify the API

Check that org.crac is present on compile and runtime classpaths under the supported packaging approach. Confirm code can import Resource, Context, and Core.

### Step 3: Verify Spring integration

Determine actual Spring Boot/Spring Framework versions. Check whether official CRaC integration exists, which artifacts and properties are needed, and which resources are managed automatically.

### Step 4: Verify resource registration

Run the application and confirm Resources are registered exactly once. Use safe logging to verify callbacks are invoked. Do not rely solely on the bean existing in ApplicationContext.

### Step 5: Verify pre-checkpoint state

Send representative requests and tasks, then request quiesce. Confirm requests drained, transactions finished, workers stopped, buffers were handled, and resource owners reported ready.

### Step 6: Create checkpoint and restore

Execute using the mechanism specified by the JDK/platform. Observe logs, callbacks, and resource state after restore.

### Step 7: Verify the application

Send new requests, run database queries, call external services, and check caches, message consumers, and schedulers. Mark readiness only once essential capabilities work.

### Step 8: Verify failure handling

Test unavailable databases, expired tokens, callback timeouts, changed endpoints, and restoring on incompatible environments. Confirm the application does not falsely report ready and does not produce duplicate side effects.

## 21. Example Project Structure

A structure can separate CRaC integration from business logic:

~~~text
src/main/java/com/example/app/
  Application.java
  config/
    CracConfiguration.java
    DataSourceConfiguration.java
  crac/
    ApplicationCheckpointCoordinator.java
    DatabaseCracResource.java
    ExternalClientCracResource.java
  lifecycle/
    IngressLifecycle.java
    WorkerLifecycle.java
    DataAccessLifecycle.java
  service/
    OrderService.java
  repository/
    OrderRepository.java
~~~

Where:

- Application.java boots Spring Boot.
- CracConfiguration.java creates and configures lifecycle beans.
- ApplicationCheckpointCoordinator coordinates quiesce and restore.
- DatabaseCracResource manages the database part the application genuinely owns.
- ExternalClientCracResource manages external clients if the library lacks integration.
- Lifecycle interfaces decouple coordination from driver or framework details.

You do not have to create these exact classes. For small applications, one Resource may suffice. For large applications, splitting by owner avoids one giant callback knowing too many internal details.

## 22. Common Integration Mistakes

**Only adding the org.crac dependency and running on a regular JDK.** Code may compile, yet runtime lacks checkpoint/restore capability. Verify the actual binary.

**Confusing Spring bean lifecycle with CRaC lifecycle.** @PreDestroy or close() is not automatically a pre-checkpoint callback. Use integration or an explicitly registered Resource.

**Assuming Spring Boot manages every dependency automatically.** The framework cannot automatically know every socket, native handle, and custom state inside third-party libraries. Check integration scope and inventory.

**Duplicate Resource registration.** Both Spring integration and the application close the same client. Assign one lifecycle owner and avoid overlapping callbacks.

**Closing ApplicationContext inside beforeCheckpoint.** This can destroy beans and prevent the process from continuing. Follow only supported lifecycles.

**Checkpointing while requests or transactions are still running.** Business state may be half-finished and connections become invalid. Drain requests and complete transactions.

**Using restore callbacks to run real business logic.** Restore can happen multiple times; side effects such as creating orders or sending emails may repeat. Callbacks should focus on restoring resources and runtime state.

**Opening readiness too early.** Process existence does not mean databases, brokers, or web servers are ready. Readiness must wait for essential dependencies.

**Failing to refresh per-instance configuration.** Checkpoints may hold stale hostnames, tokens, or endpoints. Re-read environment-dependent data after restore.

**Relying on unguaranteed callback order.** If the database must be ready before workers, coordinate order explicitly and test rather than assuming registration order.

**Not checking runtimeClasspath.** APIs or integrations may appear only at compile time, or conflicting versions may exist. Inspect the dependency tree and container image.

## 23. Checklist for Integrating Spring, Spring Boot, and org.crac

- [ ] Identified the exact JDK binary running the application and confirmed the build supports CRaC?
- [ ] Are the JDK, kernel, OS, container runtime, and checkpoint/restore tool compatible?
- [ ] Is the org.crac API the right version and present on the runtime classpath?
- [ ] Checked the dependency tree to avoid multiple API/integration versions?
- [ ] Identified exact Spring Boot and Spring Framework versions?
- [ ] Does the exact release's documentation confirm CRaC integration and how to configure it?
- [ ] Identified which resources the integration manages automatically and which it skips?
- [ ] Does each resource have an owner and coordination plan before checkpoint/after restore?
- [ ] Are Resource beans registered exactly once?
- [ ] Are there no duplicate callbacks managing the same pool or client?
- [ ] Are ingress, transactions, schedulers, and executors drained before checkpoint?
- [ ] Are databases, HTTP clients, caches, and messaging restored per their libraries?
- [ ] Are instance-dependent identity, tokens, DNS, and configuration refreshed when needed?
- [ ] Do failed callbacks prevent the application from reporting ready or accepting traffic?
- [ ] Tested checkpoint and restore using the exact deployment runtime and image?
- [ ] Tested requests, transactions, background tasks, and side effects after restore?

## Conclusion

To integrate Spring Framework, Spring Boot, and org.crac, you must simultaneously satisfy the requirements of the CRaC runtime, API, Spring version, and dependencies used by the application. The org.crac dependency only provides the API contract; a CRaC-supporting JDK provides checkpoint/restore capabilities at the runtime level. Spring integration can assist lifecycle coordination, yet the scope of managed resources depends on version and configuration.

Identify the owner of each resource, use official integration when available, and register custom Resources for what the application genuinely owns. Before checkpoint, stop ingress, drain requests and transactions, and bring clients, pools, workers, and schedulers to a safe state. After restore, refresh instance-dependent configuration, restore dependencies, verify functionality, and open readiness only once the application can serve. Finally, testing with the exact JDK, Spring release, container image, and deployment platform distinguishes dependency errors, runtime errors, and application lifecycle bugs.