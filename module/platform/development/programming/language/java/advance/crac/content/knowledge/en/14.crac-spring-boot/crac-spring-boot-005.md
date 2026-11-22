# Automatic Checkpoint at onRefresh Using spring.context.checkpoint

Spring Boot can coordinate with CRaC to create a checkpoint at a milestone during application startup. With the configuration spring.context.checkpoint=onRefresh, Spring Boot requests CRaC to perform a checkpoint when ApplicationContext has completed the refresh phase. As a result, the checkpoint image can contain state created during bean initialization, configuration loading, and running Spring initialization callbacks.

Checkpoint at onRefresh is useful when time-consuming initialization mostly occurs during ApplicationContext creation. The application can restore from the image to reduce startup time for subsequent runs. However, the onRefresh milestone does not mean the application has completed all of startup. Steps such as ApplicationRunner, CommandLineRunner, or warm-up work performed after refresh may not have run at the time the image is created.

To use this mechanism, the application needs a Spring Boot version with CRaC support, a compatible org.crac dependency, and a properly configured CRaC JDK/runtime. The property only specifies when Spring Boot requests a checkpoint; it does not automatically make all connections, threads, sessions, or external resources safe. Resources need to be prepared before checkpoint and recovered after restore according to an appropriate lifecycle.

## 1. CRaC and Checkpoints in the Spring Boot Lifecycle

CRaC (Coordinated Restore at Checkpoint) allows saving the state of a running process and then restoring the process from that state. With Java, a checkpoint can retain JVM state such as loaded classes, objects in the heap, and part of the process/resource state supported by the runtime.

Spring Boot creates an ApplicationContext to manage beans, configuration, dependency injection, event listeners, and the application lifecycle. The startup process typically consists of major steps:

1. Create SpringApplication and prepare the Environment.
2. Create ApplicationContext.
3. Load bean definitions and process configuration.
4. Initialize singleton beans and required dependencies.
5. Complete the ApplicationContext refresh.
6. Run subsequent SpringApplication steps, including ApplicationRunner and CommandLineRunner.
7. Publish the application ready event and begin serving according to configuration.

The spring.context.checkpoint property controls the checkpoint milestone tied to the context lifecycle. When set to onRefresh, Spring Boot requests a checkpoint after ApplicationContext refresh completes.

~~~mermaid
flowchart TD
    A[SpringApplication starts] --> B[Create Environment and ApplicationContext]
    B --> C[Read configuration and create beans]
    C --> D[Initialize singletons and dependencies]
    D --> E[ApplicationContext refresh completes]
    E --> F{spring.context.checkpoint}
    F -->|onRefresh| G[CRaC checkpoint]
    F -->|never| H[Continue startup]
    G --> I[CRaC restore and recovery callbacks]
    I --> J[Continue startup]
    H --> J
    J --> K[ApplicationRunner and CommandLineRunner]
    K --> L[Application ready]
~~~

The diagram shows the general position of the checkpoint in the startup pipeline. Details of events and callbacks may differ by Spring Boot, Spring Framework, and CRaC runtime versions; check the actual version when depending on a specific order.

## 2. The spring.context.checkpoint=onRefresh Property

The onRefresh value asks Spring Boot to perform a checkpoint at the moment ApplicationContext has refreshed. The default value is typically never, meaning Spring Boot does not automatically trigger a checkpoint at the refresh milestone.

In the application.properties file:

~~~properties
spring.context.checkpoint=onRefresh
~~~

Or in application.yml:

~~~yaml
spring:
  context:
    checkpoint: onRefresh
~~~

Once the configuration is loaded, Spring Boot uses the selected checkpoint mode during startup.

### 2.1. Meaning of onRefresh

onRefresh ties the checkpoint request to the event that ApplicationContext has completed refresh. At this point, much of Spring initialization work has already taken place:

- Bean definitions have been registered and processed.
- Singleton beans requiring eager initialization have been created.
- Dependency injection and bean initialization callbacks have been executed.
- Spring lifecycle components have been started according to the corresponding refresh mechanism.
- ApplicationContext listeners have been registered and the context has completed refresh.

Therefore, if startup cost lies in constructors, factory methods, BeanPostProcessors, InitializingBean, @PostConstruct, or singleton creation, the completed state of those steps can be included in the checkpoint.

However, onRefresh is not a signal that all application tasks have completed. Work performed after the refresh phase, such as in ApplicationRunner or CommandLineRunner, may not have run when the checkpoint is created. Tasks launched asynchronously during initialization may also not have completed yet.

### 2.2. Default Value and When to Enable

If the property is not configured, the application should not assume Spring Boot will automatically create a checkpoint. Enable onRefresh when:

- The application runs on a CRaC-supported runtime.
- There is a process for creating and storing checkpoints in the deployment environment.
- The reusable initialization mostly completes before or during refresh.
- External resources have explicit preparation and recovery callbacks.
- The application has been tested with the exact JDK, container, filesystem, and libraries in use.

Do not enable the property in an environment without CRaC support and expect the Maven dependency alone to add checkpoint capability. The org.crac artifact provides the API; checkpoint/restore capability also depends on the JDK/runtime, operating system, and deployment environment.

### 2.3. Do Not Confuse with Periodic Checkpoints

onRefresh is not a periodic checkpoint schedule, nor does it mean the application creates a new image every time a bean changes. It is a trigger point tied to the ApplicationContext refresh process. If the application has multiple contexts or refreshes the context multiple times, inspect the behavior of the version and application structure rather than assuming only a single invocation in all cases.

If a checkpoint is needed after a separate warm-up step or at another operational point, design an intentional trigger according to the API and version in use. Do not assume onRefresh will wait for all background tasks or all runners to finish.

## 3. Preparing Dependencies and Runtime

Spring Boot needs the CRaC API on the classpath and must run on a JDK/runtime supporting checkpoint/restore.

### 3.1. Maven Dependency

If the project uses Spring Boot dependency management and a BOM version managing the corresponding CRaC dependency, you can declare:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
</dependency>
~~~

If the BOM does not manage the version or the project uses its own dependency management, declare an org.crac version compatible with the Spring Boot version and CRaC runtime in use. Do not pick a random version just to make the build compile.

### 3.2. Gradle Dependency

With Gradle:

~~~kotlin
dependencies {
    implementation("org.crac:crac")
}
~~~

Similarly to Maven, if dependency management does not provide the version, specify a version confirmed to be compatible.

### 3.3. Spring Boot Version

Spring Boot provides CRaC integration in versions supporting this feature, starting from the Spring Boot 3.2 line. When deploying, confirm:

- The actual Spring Boot version.
- The bundled Spring Framework version.
- The org.crac API version.
- A JDK distribution with CRaC support.
- Compatible operating system, kernel, and container runtime.
- Whether native libraries, agents, profilers, or third-party clients support checkpoint/restore.

Do not check only the build file to conclude the runtime already supports CRaC. Test checkpoint/restore on the exact target image and environment.

### 3.4. Runtime and Checkpoint Storage Location

A standard JDK may not provide CRaC checkpoint/restore capability. You must use a JDK/runtime built with CRaC support and configure the checkpoint destination according to the distribution's instructions.

Some CRaC runtimes use a JVM option similar to:

~~~text
-XX:CRaCCheckpointTo=/opt/checkpoints/orders
~~~

The path above is only an example. Depending on the JDK and environment, configure write permissions, disk space, volume mounts, ownership, and image protection policies. Do not place checkpoints in a temporary directory that will be deleted before the restore process uses the image.

Creating a checkpoint may require OS privileges, kernel configuration, or container runtime capabilities. Follow the documentation of your CRaC JDK and deployment platform; Spring Boot properties cannot replace these requirements.

## 4. What Is Initialized Before the onRefresh Milestone?

Because the checkpoint point lies after the refresh phase, state created during refresh can be saved into the image. For example:

- Singleton beans and dependencies have been initialized.
- Configuration has been bound into objects.
- Metadata or schemas have been loaded.
- Caches initialized synchronously during bean creation.
- Shared parsers, serializers, or data structures have been created.
- Bean initialization callbacks have run.

This can significantly reduce repeated work when the application is restored.

### 4.1. Constructor and @PostConstruct

Example of a bean preparing immutable data at initialization:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public final class ReferenceData {
    private Map<String, String> values;

    @PostConstruct
    void load() {
        values = Map.of(
                "VN", "Vietnam",
                "SG", "Singapore",
                "JP", "Japan"
        );
    }

    public String find(String code) {
        return values.get(code);
    }
}
~~~

If the bean is initialized during refresh, the data in values can already be in the heap at the onRefresh checkpoint. After restore, the application can use the already created object without redoing the same initialization work.

This example only fits stable, shareable data. If data changes over time, access permissions, or per replica, verify freshness after restore or reload from the authoritative source.

### 4.2. Caches Warmed Up During Refresh

A cache can be initialized before checkpoint if warm-up completes synchronously during a bean initialization callback. However, consider:

- Does cache data change while the JVM is stopped?
- Does the cache contain tokens, sessions, or user-specific data?
- Can the cache be shared across multiple replicas or does it need separate namespaces?
- Can the cache be refreshed incrementally after restore?
- Does simultaneously restoring many replicas create a traffic spike on the data source?

Do not put short-lived data into the image just to avoid a single read if after restore the data may already be stale. Distinguish static initialization caches from business caches needing refresh.

### 4.3. Work That May Not Have Run Yet

In a normal startup pipeline, the following steps occur after ApplicationContext refresh completes:

- ApplicationRunner.
- CommandLineRunner.
- Certain SpringApplication listeners such as ApplicationReadyEvent.
- Warm-up work scheduled asynchronously.
- Tasks started after the server receives its first request.

Therefore, if the application loads large models or performs warm-up inside CommandLineRunner, the checkpoint at onRefresh may be created before that work runs. After restore, the runner continues executing in the startup flow; that warm-up work is not counted as completed inside the image.

If warm-up results need to be included in the checkpoint, consider moving suitable initialization to a stage before refresh completes, or using another checkpoint workflow after warm-up finishes. Changing where warm-up happens must preserve Spring's lifecycle properly and not extend refresh time beyond operational limits.

## 5. onRefresh Does Not Automatically Manage Every Resource

Checkpoint at onRefresh saves process state at that moment. It does not automatically guarantee all external resources can continue working after restore.

Resources to consider:

| Resource | Risk if keeping old state | Preparation needed |
|---|---|---|
| JDBC connection pool | Database or network closed the connection | Drain transactions, close pool, and create a new pool |
| HTTP client | Stale socket, DNS cache, or TLS session | Close client and recreate via library API |
| Message consumer | Heartbeat stopped, member session expired | Stop consumer, handle acknowledgments, and rejoin group |
| Scheduler | Deadlines elapsed while JVM was stopped | Stop scheduler and recalculate schedule after restore |
| File writer | File descriptor still points to a rotated file | Flush/close before checkpoint, reopen path after restore |
| Token/session | Credential expired or revoked | Acquire new token or re-authenticate |
| Lease/distributed lock | Lease may have expired and been granted to another replica | Re-acquire and verify ownership |
| Native resource | Library may not support restore | Verify support, close or recreate |

The Spring Boot property selects the checkpoint milestone. Handling each individual resource requires using CRaC Resource, Spring lifecycle, or the library's official mechanism.

## 6. Registering a Resource to Prepare Before Checkpoint

For resources needing custom handling, the application can implement org.crac.Resource and register with the global context. The beforeCheckpoint() callback prepares the resource before the image is created; afterRestore() restores the resource after the process is restored.

The example below manages a hypothetical client:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class ExternalClientResource implements Resource {
    private final ExternalClientFactory factory;
    private volatile ExternalClient client;

    public ExternalClientResource(ExternalClientFactory factory)
            throws Exception {
        this.factory = factory;
        this.client = factory.create();

        if (Core.isCheckpointSupported()) {
            Core.getGlobalContext().register(this);
        }
    }

    public ExternalClient client() {
        ExternalClient current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "External client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        ExternalClient current = client;
        client = null;
        if (current != null) {
            current.close();
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = factory.create();
    }
}
~~~

ExternalClient and ExternalClientFactory are application-defined types, not Spring Boot or CRaC APIs. The example illustrates how a bean owning a client registers a resource and closes/reopens the client. In a real application, the factory needs to read current configuration, establish new connections, authenticate, and handle timeouts.

If the client library already has CRaC integration or Spring Boot manages that component's lifecycle itself, use the supported mechanism. Avoid closing internal sockets directly while the client still holds references to those sockets. Closing must go through the library's lifecycle API.

### 6.1. When Should a Resource Be Registered?

A Resource must be registered before the checkpoint at onRefresh takes place. Registering in the constructor or bean initialization callback can usually satisfy this condition because singletons are created before refresh completes. However, check how the bean is initialized:

- A lazy bean may not have been created at refresh time.
- A prototype bean has a different lifecycle from a singleton.
- An asynchronously created bean may not have finished registering.
- A resource created late after refresh will not participate in a checkpoint that already occurred earlier.

For lazy or late-created resources, design an explicit registration mechanism and ensure it completes before the corresponding checkpoint. Do not defer registration to a callback that only runs after checkpointing has begun.

### 6.2. Resource Ordering

If resources depend on one another, registration order should reflect the closing and recovery order. For example, a consumer using a database pool:

- Before checkpoint, stop the consumer first and only then close the database pool.
- After restore, create the database pool first and only then start the consumer.

Check the callback ordering rules of CRaC Context in your exact version and register resources in the appropriate order. Do not let two resources simultaneously manage closing the same client or connection pool.

## 7. Spring Lifecycle and Background Tasks

Spring has lifecycle abstractions such as Lifecycle and SmartLifecycle. These components allow Spring to manage start/stop according to ApplicationContext phases. When integrating CRaC, clearly distinguish which components are managed by Spring and which require a separate Resource.

Some questions to answer:

- Does the worker need to run while the checkpoint is being prepared or must it pause?
- Does the scheduler need to cancel schedules and recalculate deadlines after restore?
- Does the consumer need to stop receiving messages and rejoin the group?
- Can the thread pool continue being used after restore or must it be recreated?
- Does the component have official Spring lifecycle or CRaC integration support?

Do not assume every application-created thread automatically stops and restarts properly. Configure SmartLifecycle or appropriate resource callbacks and test on the Spring Boot version in use.

Conceptual example of a lifecycle component:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class BackgroundWorkerLifecycle
        implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }
        running = true;
        // Create or start worker according to application policy.
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }
        running = false;
        // Stop accepting tasks, drain, and stop worker.
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

This is a simplified example of Spring lifecycle. A real worker needs mechanisms to stop, wait for completion, handle interrupts, and recreate the executor if the old executor has shut down. Do not use a plain running boolean alone to prove the worker has stopped completely.

## 8. Environment Configuration and Property Precedence

spring.context.checkpoint is a Spring Boot property, so it can be supplied via application.properties, application.yml, environment variables, or command-line arguments following Spring Boot's externalized configuration rules.

Environment variable example:

~~~text
SPRING_CONTEXT_CHECKPOINT=onRefresh
~~~

Application argument example:

~~~text
--spring.context.checkpoint=onRefresh
~~~

In deployment, checkpoint configuration should be managed by profile or environment:

~~~yaml
spring:
  config:
    activate:
      on-profile: crac
  context:
    checkpoint: onRefresh
~~~

This example illustrates a profile-based configuration. Place it in the right profile configuration file and ensure the crac profile is activated in the environment intended for creating checkpoints.

Do not accidentally enable automatic checkpointing in every environment. Development, integration testing, and production environments may have different runtimes or OS permissions. Control profiles, JVM flags, and image storage locations to avoid creating unwanted checkpoints.

## 9. Checkpoint Creation and Restore Workflow

A general operational flow:

### When Starting Up to Create a Checkpoint

1. Start the application on a CRaC-enabled JDK/runtime.
2. Provide a compatible org.crac dependency.
3. Enable spring.context.checkpoint=onRefresh in the environment where the image should be created.
4. Configure the checkpoint destination and access permissions.
5. Spring Boot creates ApplicationContext and initializes beans.
6. When refresh completes, Spring Boot triggers checkpoint according to configuration.
7. CRaC invokes resource preparation callbacks, creates the image, and performs restore per runtime mechanism.
8. The application resumes startup after restore; post-refresh steps run according to lifecycle.

### When Using a Created Image

1. Supply the checkpoint image to the restore environment.
2. Use the right runtime, native libraries, and conditions compatible with the image.
3. Configure the restore source according to the JDK/runtime instructions.
4. Restore the process.
5. CRaC invokes resource recovery callbacks.
6. The application verifies configuration, credentials, connections, and readiness.
7. Admit the instance to receive traffic once mandatory dependencies are ready.

Diagram:

~~~mermaid
flowchart TD
    A[Build Spring Boot application] --> B[Add org.crac dependency]
    B --> C[Run on CRaC-enabled JDK]
    C --> D[Enable spring.context.checkpoint=onRefresh]
    D --> E[Spring creates ApplicationContext]
    E --> F[Initialize beans and dependencies]
    F --> G[Context refresh completes]
    G --> H[CRaC checkpoint]
    H --> I[Checkpoint image]
    I --> J[Deploy image to restore environment]
    J --> K[CRaC restore]
    K --> L[afterRestore and bootstrap dependencies]
    L --> M[Readiness]
    M --> N[Serve requests]
~~~

Checkpoint images are usually tied to a specific runtime environment. Do not assume you can create an image on one operating system and restore it on any operating system or kernel. Confirm compatibility limits of the CRaC JDK, container runtime, and checkpoint tooling.

## 10. Cases Where onRefresh Is Suitable

onRefresh is suitable when most initialization cost lies in the refresh process and that state can be reused:

- Loading rarely changing metadata or configuration.
- Initializing parsers, serializers, and data structures.
- Creating expensive singleton beans.
- Loading models or reference data if loading completes before refresh.
- Preparing immutable caches or caches with a post-restore freshness verification process.
- Initializing frameworks and internal components that do not hold unrecoverable external resources.

For example, a document processing application can load schemas and create parsers during bean initialization. If these objects do not depend on replica identity or expiring external state, a post-refresh checkpoint can preserve the initialization result.

## 11. Cases Requiring Consideration of Another Milestone

onRefresh may be too early if the application needs post-refresh steps to reach the desired state:

- ApplicationRunner loading business data.
- CommandLineRunner warming up models.
- An asynchronous task populating a cache.
- Connections to external services only established after the server is ready.
- A bootstrap step depending on replica metadata provided after the container begins serving.

In that case, decide which data belongs in the image and which data should be recreated after restore. Do not move all tasks into refresh merely to include them in the checkpoint; doing so can prolong refresh time and cause deployment system timeouts.

If you want to checkpoint after warm-up, trigger when warm-up actually finishes, according to the CRaC API or compatible Spring Boot integration. Avoid invoking checkpoint in multiple places without controlling invocation count, because that can create multiple images or make the startup flow unpredictable.

## 12. Common Errors When Enabling Automatic Checkpointing

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No checkpoint image | Runtime does not support CRaC or checkpoint destination is not configured | Check JDK, runtime options, logs, and write permissions |
| Error during context refresh | Resource callback failed or checkpoint could not be performed | Inspect root cause error, check resources and compatibility |
| Application does not resume startup | Restore or recovery callback failed | Inspect CRaC logs, dependencies, and resource ordering |
| Database connection error after restore | Pool retains old connections or credentials rotated | Close pool before checkpoint and create a new pool |
| Consumer does not receive messages | Member session expired or group not rejoined | Create a new consumer and register subscriptions |
| Cache contains stale data | Cache was snapshotted before data source changed | Refresh or verify TTL/version |
| Warm-up missing from image | Warm-up ran in a Runner or after refresh | Choose a post-warm-up checkpoint milestone or accept post-restore warm-up |
| Appender writes to old file | File rotation happened while JVM was stopped | Close file before checkpoint and reopen active path |
| Multiple replicas share the same identity | Identity was generated before checkpoint and cloned | Generate separate identity after restore |
| Restore incompatible with environment | Different JDK, kernel, native library, or container | Use an environment compatible with the checkpoint image |
| Checkpoint takes too long | Callback waits indefinitely on tasks or I/O | Drain with deadlines, timeouts, and checkpoint cancellation policy |
| Startup triggers checkpoint unexpectedly | Property enabled in an inappropriate profile | Manage properties by profile and deployment config |

## 13. Observability and Diagnostics

To understand whether automatic checkpointing occurs at the right time, record startup and lifecycle milestones:

- Time SpringApplication starts.
- Time ApplicationContext refresh starts and finishes.
- Configured value of spring.context.checkpoint being used.
- Time beforeCheckpoint callbacks start and each resource completes.
- Time the runtime creates the checkpoint and artifact location.
- Time restore starts and finishes.
- Time afterRestore callbacks run.
- Time ApplicationRunner/CommandLineRunner starts and finishes.
- Time readiness transitions to ready.

Logs should include a correlation ID for each startup/restore run, yet must not record tokens, passwords, private keys, or sensitive content into checkpoint logs. With multiple replicas, log an instance ID generated after restore to distinguish copies.

Do not use ApplicationReadyEvent alone as proof that a checkpoint was created. This event indicates the stage where the application is ready per Spring Boot lifecycle; checkpoint status must be verified via CRaC runtime logs and artifacts.

## 14. Testing Checkpoints at onRefresh

Tests need to run on a real CRaC runtime and an environment close to production. A successful startup on a regular JDK does not prove the checkpoint mechanism works.

### 14.1. Basic Testing

1. Enable spring.context.checkpoint=onRefresh.
2. Run the application on a CRaC-enabled JDK and configure the checkpoint destination.
3. Verify Spring creates ApplicationContext and completes refresh.
4. Verify the runtime receives the checkpoint request at the onRefresh milestone.
5. Verify the checkpoint image is created at the expected location.
6. Verify the process resumes startup after restore.
7. Verify Runners and ready events occur in the expected order.
8. Launch from the checkpoint image and verify the application can serve requests.

### 14.2. Resource Testing

- Database restarted while JVM was stopped.
- Broker closed consumer session before restore.
- Token or certificate expired during pause.
- Log rotation happened after the writer was closed.
- Scheduler missed one or more executions.
- A resource callback failed during beforeCheckpoint.
- A dependency was not ready during afterRestore.
- Same image used to create multiple replicas where each replica needs its own identity.

### 14.3. Warm-Up Timing Testing

Create a bean recording initialization time in @PostConstruct and a Runner recording warm-up time. Compare logs against the checkpoint milestone to confirm which work falls before refresh and which runs after restore.

If warm-up must be saved in the image, move reusable parts to a stage before refresh completes or design a post-warm-up trigger. Then verify that warm-up data is actually in the image and still valid upon restore.

### 14.4. Multi-Replica Testing

Create multiple replicas from the same checkpoint image. Verify:

- Immutable beans can be reused.
- Replica identity is freshly generated or queried from current metadata.
- Connection pools and consumers are created separately.
- Leases and leadership are re-acquired.
- Tokens or certificates are issued according to policy.
- Readiness opens only after per-replica bootstrap completes.

## 15. Recommended Configuration Workflow

A deployment workflow can be divided into steps:

1. Select a Spring Boot version with CRaC support.
2. Add a compatible org.crac dependency.
3. Use a CRaC JDK/runtime supported by the deployment platform.
4. Enable spring.context.checkpoint=onRefresh in the checkpoint-creation profile.
5. Configure checkpoint destination, volumes, permissions, and artifact protection.
6. Identify which beans can retain state across checkpoint.
7. Register Resources for connections, workers, and resources needing closing/reopening.
8. Ensure resources are registered before the refresh milestone.
9. Test callback order and startup order.
10. Create the checkpoint image and verify restore on a compatible environment.
11. Verify Runners, readiness, identity, and dependencies after restore.
12. Put the image into the deployment pipeline and monitor actual startup time.

## 16. Key Principles to Remember

- spring.context.checkpoint=onRefresh requests Spring Boot to checkpoint after ApplicationContext refresh completes.
- This property selects the checkpoint milestone in startup; it is not a periodic checkpoint schedule.
- ApplicationRunner and CommandLineRunner normally run after refresh, so do not assume their warm-up results are already inside the image.
- The org.crac dependency only provides the API; the runtime/JDK and environment must genuinely support CRaC.
- Beans created before refresh can be snapshotted, yet caches and expiring data still need verification after restore.
- Connection pools, sockets, consumers, schedulers, file writers, and credentials need their own lifecycle.
- Resources must be registered before checkpoint and callbacks must complete within a controlled deadline.
- Do not add extra checkpoint calls in multiple places without a clear trigger policy.
- Manage properties by profile to avoid enabling checkpointing outside the intended environment.
- Verify checkpoint images and restore with a real runtime; startup logs alone do not prove the artifact was created.

Automatic checkpointing at onRefresh helps Spring Boot save state after the ApplicationContext initialization stage. It is a suitable choice when most preparation work can complete during refresh. To use it safely, understand this exact milestone in the startup pipeline, distinguish it from Runner/ready steps, prepare resources with CRaC callbacks, and test restore on a real deployment environment.