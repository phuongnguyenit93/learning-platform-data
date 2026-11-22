# Comparing Spring Boot onRefresh with Post-Warm-Up Checkpoint

Spring Boot can use CRaC to create a checkpoint at two very different points in time. The first approach is an automatic checkpoint at the Spring context refresh phase using the JVM property `-Dspring.context.checkpoint=onRefresh`. The second approach is to let the application start up completely, run a warm-up workload, and then request a checkpoint externally, typically using the jcmd command.

Both approaches save JVM state for later restoration, but the different capture points determine how much work has been completed, what state is retained, and the level of operational complexity. onRefresh creates an early image: non-lazy singletons have been instantiated and initialization callbacks have run, but lifecycle beans have not started and Spring has not published ContextRefreshedEvent. A post-warm-up checkpoint is created later, when the web server is already running, the application has gone through startup runners, and may have processed representative requests. This image can retain caches, loaded classes, and optimized JIT code.

This practice exercise uses the same Spring Boot application to compare cold start, onRefresh checkpoint, and manual post-warm-up checkpoint. The goal is to understand the exact timing of the checkpoint, how to create and restore each type of image, how to measure time to readiness, and the risks that must be controlled when retaining running application state.

## 1. Practice Objectives

After this exercise, you can:

- Describe the position of LifecycleProcessor.onRefresh in the Spring startup process.
- Explain what has and has not happened when an onRefresh checkpoint is created.
- Create an automatic checkpoint using spring.context.checkpoint=onRefresh.
- Use spring.context.exit=onRefresh to inspect the same lifecycle milestone without a CRaC runtime.
- Start the application completely, send a warm-up workload, and create a manual checkpoint.
- Restore both types of checkpoints using a CRaC-enabled JDK.
- Compare restore-to-ready time, first-request time, image size, and image creation cost.
- Choose a strategy suited to startup goals and operational requirements.

Throughout the entire practice exercise, use the same CRaC JDK build, application build, container image, and resource limits. If multiple factors change at the same time, the comparison results will no longer be reliable.

## 2. Environment Preparation

Spring Framework integrates CRaC starting from version 6.1; Spring Boot supports this integration starting from version 3.2. You should verify the actual version of Spring Framework managed by the Spring Boot BOM, rather than only looking at the build plugin version.

Basic prerequisites:

1. A Linux environment with checkpoint/restore support according to the JDK distribution being used.
2. A JDK build with CRaC support.
3. The org.crac:crac dependency on the runtime classpath; current Spring documentation supports version 1.4.0 and above.
4. The runtime and checkpoint engine configured according to the vendor's instructions.
5. Permissions to create checkpoints, write to the checkpoint directory, and perform restores.
6. Sufficient CPU, memory, disk, and OS permissions for both runs.

Example Gradle configuration:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.crac:crac:1.4.0")
}
~~~

Version 1.4.0 here is the minimum compatibility baseline stated in the Spring documentation, not a recommendation to bypass dependency management. For real projects, choose a version verified with your CRaC JDK and the application's dependency graph.

You can check the runtime before running:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Record the vendor, version, VM build, java.home, OS, and architecture. Do not use a regular JDK to create a checkpoint and assume it can be restored with a different CRaC JDK.

## 3. Understanding the Position of onRefresh in Spring Startup

Spring creates the ApplicationContext, registers bean definitions, performs dependency injection, and instantiates eager singletons. Then the context goes through the refresh completion phase. During that process, LifecycleProcessor.onRefresh() is called to start beans implementing Lifecycle/SmartLifecycle. Once this phase completes, Spring publishes ContextRefreshedEvent.

When the spring.context.checkpoint property is set to onRefresh, Spring Framework creates a checkpoint right inside LifecycleProcessor.onRefresh(). This timing has specific implications:

**Already completed before the checkpoint:**

- ApplicationContext has been created and configured.
- Bean definitions have been registered.
- Non-lazy singletons have been instantiated.
- Dependency injection has completed for those beans.
- Initialization callbacks such as InitializingBean.afterPropertiesSet() have run.
- Standard bean initialization steps, including @PostConstruct, have run for the corresponding beans.

**Not yet completed at the time of the checkpoint:**

- LifecycleProcessor has not started Lifecycle/SmartLifecycle beans.
- ContextRefreshedEvent has not been published.
- ApplicationRunner and CommandLineRunner have not run.
- ApplicationReadyEvent has not been published.
- The application has not reached the ready state according to the Spring Boot startup flow.
- Real HTTP workloads have not been used to warm up the application.
- Lazy beans have not been created if no code path has requested them yet.

Therefore, onRefresh is an early checkpoint in startup. It retains the results of context creation and eager singleton initialization, but does not retain an application that has already run through representative requests.

~~~text
SpringApplication.run()
        |
        v
Create Environment and ApplicationContext
        |
        v
Load bean definitions
        |
        v
Instantiate non-lazy singletons
        |
        v
@PostConstruct / afterPropertiesSet
        |
        v
LifecycleProcessor.onRefresh()
        |
        +---- spring.context.checkpoint=onRefresh?
        |               |
        |              Yes
        |               |
        |               v
        |         CRaC checkpoint
        |               |
        |         process saves image
        |         and ends creation run
        |
        v
Start Lifecycle / SmartLifecycle beans
        |
        v
Publish ContextRefreshedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
Application is ready and accepts requests
~~~

The diagram illustrates the lifecycle flow at a conceptual level. Internal details may vary by Spring version, but the onRefresh boundary is clearly defined by Spring documentation: the checkpoint occurs before lifecycle start and before ContextRefreshedEvent.

## 4. When Does a Post-Warm-Up Checkpoint Occur?

A manual post-warm-up checkpoint is created after the application has fully started. The typical workflow:

1. Launch Spring Boot using a CRaC JDK and configure the checkpoint directory.
2. Wait for the application to reach readiness.
3. Send requests or run safe warm-up tasks.
4. Confirm that caches and dependencies are ready.
5. Request a checkpoint from outside the application.
6. Spring stops running Lifecycle beans to prepare for the checkpoint.
7. CRaC saves the process state.
8. Upon restore, recovery callbacks run and Spring restarts the Lifecycle beans.

This checkpoint can additionally retain:

- Lazy beans created by the workload.
- Loaded classes and code paths.
- Accumulated JIT compilation and profiling state.
- Populated application caches.
- Warmed-up metadata or reference data.
- Internal library state retained in the JVM image.
- Application components that have run after ApplicationReadyEvent.

This is why a post-warm-up checkpoint is often better able to reduce first-request latency and time to steady-state performance. However, it also carries more mutable state, environment dependencies, and may contain user data or credentials.

## 5. Creating a Sample Application for Both Approaches

Use a small application with a service that performs CPU-bound work and caches results. The same endpoint will be called during the warm-up of the manual approach. In the onRefresh approach, the endpoint has not been called before the checkpoint.

Example service:

~~~java
package com.example.cracdemo;

import org.springframework.stereotype.Service;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class CatalogService {

    private final Map<Integer, String> cache = new ConcurrentHashMap<>();

    public String lookup(int id) {
        return cache.computeIfAbsent(id, this::loadAndTransform);
    }

    private String loadAndTransform(int id) {
        long value = id;

        for (int i = 0; i < 100_000; i++) {
            value = (value * 31 + i) % 1_000_000_007L;
        }

        return "catalog-" + id + "-" + value;
    }

    public int cachedEntries() {
        return cache.size();
    }
}
~~~

Example controller:

~~~java
package com.example.cracdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @GetMapping("/catalog/{id}")
    public Map<String, Object> lookup(@PathVariable int id) {
        long started = System.nanoTime();
        String value = catalogService.lookup(id);
        long elapsedNanos = System.nanoTime() - started;

        return Map.of(
                "id", id,
                "value", value,
                "elapsedMicros", elapsedNanos / 1_000,
                "cacheEntries", catalogService.cachedEntries());
    }

    @GetMapping("/ready-info")
    public Map<String, Object> readyInfo() {
        return Map.of(
                "status", "UP",
                "cacheEntries", catalogService.cachedEntries());
    }
}
~~~

Application class:

~~~java
package com.example.cracdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CracDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CracDemoApplication.class, args);
    }
}
~~~

This is an illustrative workload to observe the difference between bean initialization, cache warm-up, and executed code paths. A realistic benchmark should use a workload representative of the real service, such as deserializing payloads, serializing responses, querying repositories, calling clients, or running critical business logic.

## 6. Observing Lifecycle Milestones

To see which phases the onRefresh checkpoint precedes, you can add a bean implementing SmartLifecycle and a listener for ContextRefreshedEvent.

~~~java
package com.example.cracdemo;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class LifecycleMarker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("MARKER: SmartLifecycle.start");
    }

    @Override
    public void stop() {
        running = false;
        System.out.println("MARKER: SmartLifecycle.stop");
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Listener:

~~~java
package com.example.cracdemo;

import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshEventMarker {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println("MARKER: ContextRefreshedEvent");
    }
}
~~~

You can add an InitializingBean to observe the initialization callback:

~~~java
package com.example.cracdemo;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
public class InitializationMarker implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("MARKER: afterPropertiesSet");
    }
}
~~~

When running with onRefresh, the afterPropertiesSet log appears before the checkpoint. The SmartLifecycle.start and ContextRefreshedEvent logs do not appear during the checkpoint creation run because the checkpoint is taken before those two milestones. Upon restore, the process continues after the checkpoint point and Spring completes the remaining startup.

When running a normal cold start, the markers appear according to the normal startup lifecycle. When creating a manual checkpoint after the application is ready, all markers have already appeared before the checkpoint; at checkpoint time, SmartLifecycle.stop is called, and after restore the beans are started again.

Do not use log markers as the primary performance measurement. Logging has overhead and time resolution that is unsuitable as a replacement for metrics. They only help observe lifecycle ordering.

## 7. Practice A: Inspecting onRefresh Without Needing CRaC

Spring provides the spring.context.exit=onRefresh property for inspection purposes. It causes the application to exit at the same LifecycleProcessor.onRefresh phase without creating a checkpoint. You can use it to see how far startup has progressed and detect which bean initialization depends on external services before lifecycle start.

Run:

~~~bash
java -Dspring.context.exit=onRefresh -jar build/libs/crac-demo.jar
~~~

Observations:

- afterPropertiesSet has run.
- SmartLifecycle.start has not run.
- ContextRefreshedEvent has not been published.
- ApplicationRunner and ApplicationReadyEvent have not occurred.
- The process terminates at the onRefresh milestone.

This property is useful when the application has beans that initialize connections to a database or external service directly in the constructor, @PostConstruct, or afterPropertiesSet. If those connections are not needed to create an early checkpoint, consider lazy initialization, deferring connection opening until lifecycle start, or designing the bean to only hold configuration during initialization.

spring.context.exit=onRefresh is a phase inspection tool, not a replacement for CRaC testing. It does not prove checkpoint/restore success and does not execute CRaC callbacks.

## 8. Practice B: Creating an Automatic Checkpoint with onRefresh

First, ensure the checkpoint directory does not contain artifacts from another run. Use a separate directory for each approach.

Launch the application:

~~~bash
java \
  -Dspring.context.checkpoint=onRefresh \
  -XX:CRaCCheckpointTo=./checkpoint-on-refresh \
  -jar build/libs/crac-demo.jar
~~~

Spring Framework recognizes the spring.context.checkpoint=onRefresh property and requests CRaC to create a checkpoint during the LifecycleProcessor.onRefresh phase.

Expected results:

1. Spring initializes the ApplicationContext.
2. Eager singletons and initialization callbacks complete.
3. Spring requests a CRaC checkpoint.
4. The runtime writes the checkpoint to checkpoint-on-refresh.
5. The checkpoint creation run terminates according to the CRaC runtime's behavior.
6. Upon restore, the JVM resumes startup after the checkpoint point; Spring starts lifecycle beans, publishes ContextRefreshedEvent, and completes Spring Boot startup.

Restore using the same compatible CRaC JDK:

~~~bash
java -XX:CRaCRestoreFrom=./checkpoint-on-refresh
~~~

The exact syntax and how additional parameters are passed during restore may vary by JDK vendor. Follow the exact instructions of the distribution that created the checkpoint. Do not add another JAR or run a different application build unless required by the runtime.

After restore, wait for the readiness endpoint:

~~~bash
curl http://localhost:8080/ready-info
~~~

Call the catalog endpoint and record the first-request time. In the onRefresh checkpoint, the catalog cache has not been warmed up by the endpoint before the checkpoint, so the first request will execute loadAndTransform.

## 9. Practice C: Creating a Checkpoint After Warm-Up

Use a separate checkpoint directory. This time do not enable spring.context.checkpoint=onRefresh.

Launch the application with the CRaC checkpoint destination option:

~~~bash
java \
  -XX:CRaCCheckpointTo=./checkpoint-warmed \
  -jar build/libs/crac-demo.jar
~~~

Wait for the application to reach readiness:

~~~bash
curl http://localhost:8080/ready-info
~~~

Send representative warm-up requests. For example:

~~~bash
for id in 1 2 3 4 5 6 7 8 9 10; do
  curl "http://localhost:8080/catalog/$id"
done
~~~

Call the same set of IDs repeatedly to generate cache hits. For real applications, warm-up needs to exercise critical code paths, not just call a health endpoint. Consider warming up serialization, validation, repository queries, mapping, templates, or client calls according to the real workload.

Once the application is warmed up and no requests are in flight, open a second terminal and find the PID or command target of the JVM. Create the checkpoint:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Some JDKs or vendor guides allow using the process/JAR name instead of the PID. Check jcmd -l to identify the target and use the syntax supported by the runtime.

With an on-demand checkpoint, Spring stops running beans that implement Lifecycle so they have an opportunity to close resources. CRaC saves the JVM state. After restore, Spring restarts those beans. Libraries not integrated with Spring may require their own org.crac.Resource to close/open resources properly across the lifecycle.

Restore:

~~~bash
java -XX:CRaCRestoreFrom=./checkpoint-warmed
~~~

Wait for readiness and then call the warmed-up IDs again. If the cache resides in the heap and is retained in the checkpoint, requests can become cache hits immediately after restore. However, this result only holds for caches that can be retained across a checkpoint; caches based on TTL, remote state, or per-instance identity may need to be invalidated or refreshed.

## 10. Differences in Timing and Retained State

The following table summarizes the key milestones:

| Component/State | onRefresh | Post-Warm-Up |
|---|---|---|
| ApplicationContext | Created | Created |
| Non-lazy singletons | Instantiated | Instantiated |
| afterPropertiesSet / @PostConstruct | Run for instantiated beans | Run |
| Unaccessed lazy beans | Not yet instantiated | May be instantiated if used by warm-up |
| SmartLifecycle.start | Not yet run at checkpoint | Already run before checkpoint |
| ContextRefreshedEvent | Not yet published at checkpoint | Already published |
| ApplicationRunner / CommandLineRunner | Not yet run at checkpoint | Already run |
| ApplicationReadyEvent | Not yet published at checkpoint | Already published |
| HTTP request workload | Not yet run | May have run |
| Application cache | Mostly initial state | May be warmed up |
| JIT compilation | Mostly early startup level | May be optimized by workload |
| Web server lifecycle | Not yet started at checkpoint | Already started; Spring needs to handle lifecycle at checkpoint |
| Dependency connections | May not be open yet if opened at lifecycle start; connections opened early must be handled | May be active and must be closed/reconnected properly |

Not every application has all of these components. The table indicates relative positions in the lifecycle, not a guarantee that a specific bean is always created or retained.

## 11. Comparing Advantages and Limitations

### onRefresh

Advantages:

- Creates the checkpoint automatically during startup, with little need for a separate warm-up step.
- Easy to standardize in a build pipeline or image preparation.
- Retains the results of ApplicationContext initialization and eager singletons.
- Does not require waiting for the application to receive real traffic before creating a checkpoint.
- Suitable when the goal is to skip most of the bean creation and context configuration cost.

Limitations:

- Has not run Lifecycle.start at the checkpoint point.
- Has not published ContextRefreshedEvent.
- Has not run ApplicationRunner/CommandLineRunner.
- Has not processed requests to warm up application code or JIT.
- Lazy beans have not been initialized if not yet accessed.
- Does not provide the full benefits of a JVM that has run through a representative workload.
- Bean initialization may still access remote services or retain credentials in the checkpoint.

### Post-Warm-Up Checkpoint

Advantages:

- Can retain populated caches and reference data.
- Can retain loaded classes and JIT-optimized code paths.
- The application can achieve better request performance immediately after restore.
- Can warm up specific business paths rather than only framework initialization.
- Useful when cold-start or first-request latency is a critical requirement.

Limitations:

- Requires running the application and warming it up before creating the image.
- Usually requires access to dependencies from the checkpoint creation environment.
- Requires controlling in-flight requests, schedulers, transactions, and message consumers.
- Requires handling sockets, files, connection pools, and external resources.
- May carry caches, tokens, or sensitive data in the heap.
- Requires identifying which state must be invalidated or refreshed after restore.
- The checkpoint may depend more tightly on the host, network, and runtime profile.

## 12. Impact on Startup Latency and First-Request Latency

Do not measure only the time until the process appears. At least three quantities need to be distinguished:

- **Restore-to-ready:** From the time restore is requested until the application reaches readiness.
- **First-request latency:** The latency of the first request after readiness succeeds.
- **Steady-state latency:** The latency after the application has processed a steady workload.

onRefresh can shorten restore-to-ready because Spring does not have to recreate the entire ApplicationContext and eager singletons. However, business code paths have not been warmed up; the first request may still pay the cost of class loading, JIT compilation, cache misses, or lazy bean initialization.

A post-warm-up checkpoint can increase artifact preparation time, but reduces first-request latency and brings the application closer to steady-state. Actual results depend on the workload, the number of warmed-up code paths, cache policies, and how the JVM handles JIT state.

An illustrative example:

~~~text
Cold start:
  JVM startup
  + Spring context refresh
  + lifecycle start
  + runners
  + readiness
  + first request warm-up

onRefresh restore:
  JVM restore
  + Spring lifecycle start
  + ContextRefreshedEvent
  + runners
  + readiness
  + first request warm-up

Warm checkpoint restore:
  JVM restore
  + resource recovery
  + lifecycle restart
  + readiness
  + request on warmed-up code path
~~~

The diagram is not a guarantee of timing or the complete internal order of every application. It only shows which portions of work can be shifted before the checkpoint point.

## 13. Designing a Meaningful Warm-Up

A good warm-up must represent the production workload without causing unwanted side effects.

Should prioritize:

- Data read requests or idempotent operations.
- Payloads representative of common sizes and structures.
- High-frequency code paths.
- Serialization/deserialization, validation, and mapping.
- Queries that can safely run against test data or read replicas.
- Populating shareable reference data caches.
- Initializing clients in a way that can be refreshed after restore.

Should avoid:

- Creating real orders, payments, or transactions.
- Sending emails, SMS, or business messages.
- Creating accounts or shared data without cleanup.
- Retaining real user sessions or credentials in the image.
- Warming up with a tenant or identity unsuitable for the restore target.
- Creating caches tied to an old node/hostname and reusing them on a new node.
- Creating background jobs that run continuously while preparing the checkpoint.

If warm-up requires remote services, determine whether the data and identity used to create the checkpoint can be safely shared. For environment-dependent data, consider refreshing it after restore instead of snapshotting it.

## 14. Resource Lifecycle in a Post-Warm-Up Checkpoint

At the time of a post-warm-up checkpoint, the application may already have open sockets, HTTP connection pools, database pools, message consumers, and schedulers. These resources are not necessarily still valid when the process is restored at a different time or on a different machine.

Spring Framework coordinates checkpoint/restore with the Lifecycle contract. During an on-demand checkpoint, Spring stops running Lifecycle beans so they have a chance to close resources; after restore, Spring starts them again. For libraries not integrated with Spring, you can implement org.crac.Resource and register the resource with the CRaC context.

Items to check:

- The web server stops accepting new requests and drains in-flight requests.
- Database transactions are committed or rolled back.
- Connection pools close/recreate or revalidate properly.
- HTTP clients discard stale connections.
- Message consumers pause, commit, and rejoin the group after restore.
- Schedulers do not execute unintended catch-up tasks.
- Executors stop tasks and restart with appropriate configurations.
- File watchers or file handles are reopened.
- Credential providers refresh tokens and identity according to the new environment.

Spring Boot manages the lifecycle of certain resources such as sockets, files, and thread pools to a certain extent; do not assume that every third-party library is automatically supported. Check the dependency's documentation and write a CRaC adapter if needed.

## 15. Notes on @Scheduled When Using On-Demand Checkpoints

For periodic tasks using fixedRate, the time the process is paused between checkpoint and restore can cause missed executions to run in a catch-up burst after restore. For example, if a task is declared with a 5-second fixedRate, but the checkpoint is stored for 10 minutes, multiple executions may have become due during that interval.

If catch-up behavior is not desired, Spring documentation recommends considering fixedDelay or a cron expression. fixedDelay calculates the wait time after each task execution; cron is recalculated according to the schedule. Regardless of the choice, tasks still need idempotency and a lease mechanism if multiple replicas can run concurrently.

In the practice exercise, if the application has a scheduler, record its behavior before and after restore. Do not use a scheduler that executes real side effects during a warm-up benchmark.

## 16. Security of Post-Warm-Up Checkpoints

A post-warm-up checkpoint can contain more sensitive state than an onRefresh checkpoint:

- Resolved tokens.
- Connection configurations and endpoints.
- Caches containing application data.
- Request or response buffers.
- Recently warmed-up business data.
- Instance identity information.
- Client and library state.

An onRefresh checkpoint can also contain secrets read during bean initialization. Therefore, neither approach is inherently safe simply because the checkpoint is created early.

You must protect the checkpoint directory, artifact storage, and transfer channels; restrict read/restore permissions; use encryption at rest and TLS; manage retention; avoid baking long-lived secrets into the image; and refresh credentials according to the instance's identity after restore. If a checkpoint is placed into a container image, treat that image as an artifact that may contain data from application memory.

## 17. Fair Measurement Across the Three Approaches

Use three scenarios:

1. Normal cold start, without a checkpoint.
2. Automatic checkpoint at onRefresh.
3. Manual checkpoint after warm-up.

Measure the metrics:

| Metric | Cold start | onRefresh | Post-Warm-Up |
|---|---|---|---|
| JVM process launch to readiness | Yes | Measured on restore | Measured on restore |
| Checkpoint creation time | N/A | Yes | Yes |
| Context preparation time | Full | Saved pre-onRefresh portion | Saved most of startup |
| Warm-up time before checkpoint | N/A | No warm-up requests | Yes |
| Restore-to-ready | N/A | Yes | Yes |
| First-request latency | Yes | Yes | Yes |
| Steady-state latency | Yes | Yes | Yes |
| Artifact size | N/A | Yes | Yes |
| CPU/memory during image creation | N/A | Yes | Yes |
| Dependencies needed at image creation | Startup dependencies | Bean initialization dependencies | Warm-up dependencies |

Measure at least:

- From process invocation to readiness.
- Checkpoint creation time.
- Time from checkpoint request to artifact-ready.
- First-request latency.
- p50/p95/p99 of a representative workload.
- Artifact size before and after compression, if applicable.
- CPU-seconds, peak memory, and I/O bytes.
- Checkpoint/restore success rate.

Do not add warm-up time to the restore-to-ready time of a manual checkpoint and compare it against onRefresh restore. Report both the checkpoint preparation cost and the restore benefit separately. If a checkpoint is used for multiple replicas, you can amortize the image creation cost across the number of restores in a cost model, but you must still report per-phase latency.

## 18. Setting Up a Repeatable Experiment

For comparable results:

1. Use the same application build.
2. Use the same JDK vendor, version, and build.
3. Use the same container image, CPU/memory limits, and kernel.
4. Use the same storage class or same local disk type.
5. Reset the checkpoint directory before each new creation.
6. Keep the warm-up workload consistent.
7. Use the same dependency state or explicitly document differences.
8. Run multiple iterations; do not draw conclusions from a single sample.
9. Report median and p95, along with min/max or dispersion.
10. Restore the newly created artifact and verify readiness/functionality.

With onRefresh, inspect the checkpoint directory after the image creation run and then restore. With manual warm-up, create the image after the same warm-up workload completes. Do not use an artifact from an old build for one scenario and a new build for the other.

If you want to measure JIT benefits, run enough workload so that code paths have a chance to be compiled. A few isolated requests may only warm the cache without being enough to optimize the code. Do not set a fixed number of requests for all applications; determine it from profiling or realistic workloads.

## 19. Results Recording Table

Use the following table to record the results of each run:

| Field | Cold start | onRefresh | Post-Warm-Up |
|---|---:|---:|---:|
| JDK build | | | |
| Spring Boot / Framework | | | |
| CPU limit / memory limit | | | |
| Process launch to readiness (ms) | | | |
| Checkpoint preparation (ms) | N/A | | |
| Artifact-ready (ms) | N/A | | |
| Artifact size (MiB) | N/A | | |
| Restore-to-ready (ms) | N/A | | |
| First request (ms) | | | |
| Steady-state p95 (ms) | | | |
| CPU-seconds during image creation | N/A | | |
| Peak memory during image creation (MiB) | N/A | | |
| Restore success | N/A | | |

Do not fill in estimated numbers. Clearly record the measurement method, number of runs, and percentiles. If phases overlap, measure end-to-end separately instead of summing phase durations.

## 20. Interpreting Results

Some common result patterns:

**onRefresh restore is faster than cold start, but the first request is still slow.** This aligns with the fact that the context and eager singletons have been initialized, while business code paths have not been warmed up.

**Warm checkpoint has restore-to-ready comparable to onRefresh, but the first request is faster.** The benefit may lie in retained caches, class loading, or JIT state, not necessarily at the readiness point.

**Warm checkpoint restore-to-ready is slower than onRefresh.** A larger image or more resources needing stop/restart can increase restore cost. Check callbacks, resource recovery, and image size.

**Warm checkpoint takes longer to create the image.** The application has additional caches, heap pages, and runtime state; callbacks must also stop more components. In return, multiple restores can benefit from the warmed-up state.

**onRefresh checkpoint fails due to a remote connection.** A bean may be opening a connection in its constructor or initialization callback before Lifecycle.start. Use spring.context.exit=onRefresh to inspect, then defer the connection to lifecycle start if the architecture allows.

**Warm checkpoint restore fails due to a stale resource.** You need to fix the lifecycle of the client, pool, socket, scheduler, or file watcher. Do not conclude that the warm checkpoint approach is unsuitable before identifying the failing resource.

## 21. Which Approach to Choose?

Choose onRefresh when:

- The goal is to reduce ApplicationContext creation and eager singleton instantiation time.
- You want to create checkpoints automatically in a build pipeline.
- There is no need to retain business caches or JIT warm-up.
- You want to reduce dependency on remote workloads during image creation.
- The application can start Lifecycle beans and run runners after restore within an acceptable time.

Choose a post-warm-up checkpoint when:

- First-request latency and time to steady-state performance are critical.
- A representative and safe warm-up workload can be run.
- Warmed-up caches or code paths are valuable after restore.
- The platform can provide the dependencies needed for warm-up.
- The lifecycle of sockets, pools, schedulers, consumers, and credentials can be managed.
- The checkpoint artifact is protected and has a clear compatibility profile.

Both can be used during experimentation to find the balance point. However, a production pipeline should have a clearly defined image creation process, rather than randomly choosing between checkpoints with different states and conditions.

## 22. Common Mistakes in the Practice Exercise

**Thinking that onRefresh means the application is already ready.** The checkpoint occurs before Lifecycle.start and ContextRefreshedEvent. Runners and ApplicationReadyEvent have not run yet.

**Assuming onRefresh has warmed up JIT.** Bean initialization is not equivalent to executing a representative workload. Code paths that have not run may not be optimized yet.

**Using ApplicationRunner to warm up for onRefresh.** Runners execute after refresh, so they cannot warm up before the onRefresh checkpoint. Use a manual checkpoint after runners and the workload have completed.

**Forgetting lazy beans.** Unaccessed beans may not have been created at onRefresh. Identify which lazy beans are needed and warm them up if choosing a manual checkpoint.

**Creating a manual checkpoint while requests are still in flight.** In-flight requests may hold transactions, streams, or sockets. Drain work and use the appropriate lifecycle.

**Assuming Spring manages every dependency.** Spring supports certain resources to a limited extent. Check external libraries and add org.crac.Resource when needed.

**Comparing times at different milestones.** Startup-to-ready, checkpoint creation, and restore-to-ready are different metrics. Record each type separately.

**Warm-up causing side effects.** Benchmark requests might send messages or write real data. Use idempotent operations and test data.

**Not checking the scheduler after restore.** fixedRate may run catch-up executions for missed intervals. Choose fixedDelay/cron or an appropriate policy.

**Using a checkpoint with old dependencies or credentials.** Refresh identity and connections according to the restore environment; protect the artifact as sensitive data.

**Only checking that restore succeeded without sending requests.** The process existing does not prove that caches, dependencies, and code paths work. Verify readiness and workload after restore.

## 23. Completion Checklist

- [ ] Confirmed Spring Framework 6.1+ and Spring Boot 3.2+ or corresponding supported versions?
- [ ] Run with a compatible CRaC JDK and org.crac dependency?
- [ ] Observed afterPropertiesSet, Lifecycle.start, and ContextRefreshedEvent?
- [ ] Confirmed that the onRefresh checkpoint occurs before Lifecycle.start and ContextRefreshedEvent?
- [ ] Tried spring.context.exit=onRefresh to inspect the startup phase?
- [ ] Created and restored an onRefresh checkpoint?
- [ ] Waited for the application to be ready and then ran a warm-up workload?
- [ ] Created a manual checkpoint using a mechanism supported by the JDK?
- [ ] Confirmed that Lifecycle beans stop/restart properly?
- [ ] Handled non-Spring resources and credentials according to the lifecycle?
- [ ] Checked caches, lazy beans, and first-request behavior after restore?
- [ ] Measured cold start, onRefresh restore, and warm restore using the same resource profile?
- [ ] Measured checkpoint preparation, artifact size, restore-to-ready, and first-request latency separately?
- [ ] Run multiple iterations and recorded median/p95?
- [ ] Checked schedulers, transactions, and side effects after restore?
- [ ] Protected the checkpoint artifact and sensitive data?
- [ ] Chosen a strategy based on metrics and operational requirements?

## Conclusion

spring.context.checkpoint=onRefresh creates an early checkpoint in LifecycleProcessor.onRefresh. At that point, non-lazy singletons have been instantiated and afterPropertiesSet callbacks have run, but Lifecycle beans have not started, ContextRefreshedEvent has not been published, and application workloads have not been used for warm-up. This approach is suitable when you want to save Spring initialization state and shorten the initial part of startup.

A post-warm-up checkpoint is created when the application is fully running and has executed a representative workload. The image can retain caches, loaded code paths, and accumulated JIT state, helping reduce first-request latency and bring the instance closer to steady-state. In return, you must control resource lifecycles, in-flight requests, dependencies, schedulers, credentials, and sensitive data in the checkpoint.

Use the same application to measure cold start, onRefresh, and manual warm checkpoint. Separate image creation time from restore-to-ready and first-request latency, test resource recovery on the exact CRaC JDK, and then choose an approach based on the metrics. onRefresh optimizes the starting point of the Spring context; a post-warm-up checkpoint optimizes the state of an application that has actually run.

## References

- Spring Framework Reference — JVM Checkpoint Restore: https://docs.spring.io/spring-framework/reference/integration/checkpoint-restore.html
- Spring Boot Reference — Checkpoint and Restore With the JVM: https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html
- Azul CRaC — Frameworks With CRaC Support, Spring and Spring Boot section: https://docs.azul.com/crac/usage/frameworks