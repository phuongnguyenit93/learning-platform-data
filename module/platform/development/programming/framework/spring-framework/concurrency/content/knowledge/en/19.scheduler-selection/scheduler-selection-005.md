# DefaultManagedTaskScheduler in Jakarta EE Environments

In Spring Framework, periodic execution or single-run delayed execution is represented through the `TaskScheduler` interface. When an application runs standalone with Spring Boot or inside a servlet container that permits self-managed threads, developers typically use `ThreadPoolTaskScheduler`. However, in a **managed Jakarta EE application server environment**, having the application create and own threads directly may conflict with container policies. Spring provides **`DefaultManagedTaskScheduler`** to use a schedule executor **managed by the application server** instead of spinning up a separate pool.

`DefaultManagedTaskScheduler` resides in `org.springframework.scheduling.concurrent`. It is a JNDI-based subclass of `ConcurrentTaskScheduler`; by default it looks up `java:comp/DefaultManagedScheduledExecutorService` and delegates scheduling to the `jakarta.enterprise.concurrent.ManagedScheduledExecutorService` supplied by the Jakarta EE container. This is the right choice when the system already provides a managed scheduling resource and you want to follow the application server's thread management, lifecycle, and component context propagation.

**Focus:** this class is a **Spring adapter**, not a durable cross-server scheduling service; it does not create a Jakarta EE container, does not create JNDI resources on its own, does not replace `@EnableScheduling`, and does not make scheduled jobs survive a JVM restart.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `TaskScheduler` from `TaskExecutor` and know when to pick `DefaultManagedTaskScheduler`.
- Understand `ManagedScheduledExecutorService` from Jakarta Concurrency/JSR-236 and the default JNDI name `java:comp/DefaultManagedScheduledExecutorService`.
- Configure a Spring `TaskScheduler` bean backed by a managed resource; use `@EnableScheduling` and `@Scheduled` or invoke `TaskScheduler` directly.
- Know how to customize `jndiName` when a container exposes a dedicated resource and verify the lookup at bean initialization time.
- Distinguish a managed scheduler from `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler`, and `DefaultManagedTaskExecutor`.
- Understand that lifecycle, thread/component context, transactions, and execution policies are the responsibility of the Jakarta EE server.
- Know why you must never call `shutdown()` yourself or attempt to tune core/max pool sizes via the Spring wrapper API.
- Test scheduling modes: one-shot, fixed-rate, fixed-delay, and Spring `Trigger`/cron; observe errors, delays, schedule drift, and overload.
- Spot common pitfalls: missing JNDI in local tests, multiple replicas running `@Scheduled` simultaneously, lost jobs on restart, and false assumptions about transaction/security context.
- Run a standalone Java 17+ example to practice the `ScheduledExecutorService` API and test cancellation, clearly understanding that this example **does not simulate a Jakarta EE container**.

## 2. Distinguishing TaskScheduler and TaskExecutor

Spring has two families of abstractions that are easy to confuse:

| Interface | Responsibility | Examples |
| --- | --- | --- |
| `TaskExecutor` | Executes tasks upon submission; not necessarily scheduled for the future | `ThreadPoolTaskExecutor`, `DefaultManagedTaskExecutor` |
| `TaskScheduler` | Schedules tasks to run at a specific time or repeatedly via period/trigger | `ThreadPoolTaskScheduler`, `ConcurrentTaskScheduler`, `DefaultManagedTaskScheduler` |
| JDK `ScheduledExecutorService` | Lower-level API supporting `schedule`, `scheduleAtFixedRate`, `scheduleWithFixedDelay` | `ScheduledThreadPoolExecutor` |
| Jakarta `ManagedScheduledExecutorService` | Extends scheduled executor API with container-managed/context semantics | Resource provided by the Jakarta EE server via JNDI/injection |

`@Async` is a mechanism that offloads a **method invocation** to an executor; `@Scheduled` marks a method so Spring's scheduling infrastructure **registers a schedule**. Both needs can coexist, yet neither configuration replaces the other. `@EnableScheduling` enables `@Scheduled` discovery; `@EnableAsync` enables `@Async` processing and is not required to run scheduled methods.

## 3. Why Does Jakarta EE Need a Managed Scheduler?

A Jakarta EE application server manages resources for components: threads, classloaders, naming contexts, security, and administrative policies. Directly calling:

~~~java
Executors.newScheduledThreadPool(5)
~~~

inside an application bean can cause issues if the runtime restricts unmanaged thread creation, cannot govern or bound the pool from the application server, or fails to clean up tasks on redeploy. This is an **illustrative Java SE expression**, not a recommended approach in strict container-managed environments.

Jakarta Concurrency defines the `ManagedScheduledExecutorService` resource so applications can submit tasks to run after a delay, periodically, or via Jakarta-supported triggers. The resource is **created and managed by the container**, while application code merely consumes it.

Diagram:

~~~text
Spring application component
  |
  | @Scheduled / TaskScheduler.schedule(...)
  v
Spring DefaultManagedTaskScheduler
  |
  | JNDI lookup during bean initialization
  v
java:comp/DefaultManagedScheduledExecutorService
  |
  v
Jakarta EE ManagedScheduledExecutorService
  |
  +-- container manages thread pool, component context, policy
  |
  +-- executes Runnable/Callable on schedule
~~~

This illustrates **separation of concerns**:

- Spring: provides scheduling APIs and `@Scheduled`/`Trigger` mapping.
- Jakarta EE server: supplies the managed executor resource, thread governance, operational configuration, lifecycle, and context per specification.
- Application: defines the work, schedule, error handling, and business safety (idempotency, transactions, retries, etc.).

## 4. What Exactly Is DefaultManagedTaskScheduler?

The Spring Framework Javadoc describes:

- Full name: `org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler`.
- Superclass: `ConcurrentTaskScheduler`.
- Implements: `InitializingBean`, in addition to the scheduler/executor interfaces from its superclass.
- Does not create a pool of its own upon construction.
- By default looks up the JNDI resource named `java:comp/DefaultManagedScheduledExecutorService`.
- The JNDI lookup runs in `afterPropertiesSet()` when Spring's `BeanFactory` initializes the bean. For a standard Spring bean, you **do not call `afterPropertiesSet()` manually**.
- Exposes properties such as `setJndiName`, `setJndiEnvironment`, `setJndiTemplate`, and `setResourceRef` to tailor lookup to the environment.

An often overlooked point: **merely instantiating `new DefaultManagedTaskScheduler()` in plain Java does not produce a working scheduled executor**. During bean initialization, the class requires a valid JNDI resource; running outside a naming environment with that resource bound (such as Jakarta EE) causes the lookup to fail.

### Standard JNDI Name

Per Jakarta Concurrency, a compliant Jakarta EE environment provides the default resource at:

~~~text
java:comp/DefaultManagedScheduledExecutorService
~~~

Do not confuse it with:

~~~text
java:comp/DefaultManagedExecutorService
~~~

The second name is for `ManagedExecutorService`, intended for work that does not require a scheduling API. Pointing `DefaultManagedTaskScheduler` at a managed executor **that does not implement `ScheduledExecutorService`** breaks the initialization/usage contract.

### JSR-236 and Jakarta Packages

Spring documentation still frequently refers to "JSR-236" for the origin of Java EE Concurrency Utilities. In modern Jakarta EE, the API lives in `jakarta.enterprise.concurrent.ManagedScheduledExecutorService`. In legacy Java EE/Jakarta EE systems, you may encounter `javax.enterprise.concurrent.*`. **Never assume `javax` and `jakarta` packages are binary-compatible.**

When using Spring Framework 6.x, check the Jakarta EE runtime and compatible Jakarta Concurrency version; an older application server supporting only `javax` cannot satisfy Spring 6's `jakarta`-based expectations. Changing Maven dependencies alone without upgrading the server will not fix the namespace or provide the resource.

## 5. Configuring Spring to Use the Default Managed Scheduler

In a Spring application deployed to a Jakarta EE application server providing the managed resource at the default JNDI name:

File **ManagedSchedulingConfig.java**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler;

@Configuration
@EnableScheduling
public class ManagedSchedulingConfig {

    @Bean(name = "taskScheduler")
    public TaskScheduler taskScheduler() {
        return new DefaultManagedTaskScheduler();
    }
}
~~~

This is **a Spring configuration class**, requiring `spring-context`, the JNDI resource provided by the Jakarta EE server, and an appropriate Spring `ApplicationContext`. It cannot be run standalone with `javac`/`java` without those libraries and the container.

Explanation:

1. `@EnableScheduling` turns on infrastructure that detects `@Scheduled` methods in the Spring context.
2. Naming the bean `taskScheduler` with type `TaskScheduler` gives Spring a clear scheduler choice rather than falling back to a default scheduler.
3. `new DefaultManagedTaskScheduler()` only declares the Spring wrapper; when `BeanFactory` initializes the bean and calls `afterPropertiesSet()`, the wrapper looks up the default JNDI resource.
4. After lookup, Spring delegates scheduling to the managed scheduled executor without owning its thread pool.
5. If the JNDI resource is missing or incompatible, the application fails during bean startup. This is helpful for catching missing configuration early instead of silently falling back to an unmanaged pool.

**Important:** never register multiple competing `TaskScheduler` beans and expect Spring to always pick the intended one automatically. The name `taskScheduler` is Spring's lookup convention; alternatively use `SchedulingConfigurer` for explicit routing.

### A Scheduled Method

File **PeriodicCleanupJob.java**:

~~~java
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PeriodicCleanupJob {

    @Scheduled(fixedDelay = 60000)
    public void cleanExpiredEntries() {
        // Perform time-bounded, idempotent cleanup.
        System.out.println("cleanup requested at " + Instant.now());
    }
}
~~~

This is a **Spring component class**; because timestamp output varies, there is **no fixed stdout**. `fixedDelay=60000` means 60,000 milliseconds measured from when one execution completes until the next is scheduled to run. Production code must include exception handling, timeouts, transactions, and safeguards against unbounded runtime.

If the application server does not expose the required JNDI resource, merely having `@Scheduled` and `@EnableScheduling` will not cause `DefaultManagedTaskScheduler` to create a new managed resource.

## 6. Custom JNDI Names

On some Jakarta EE servers, administrators can declare a dedicated `ManagedScheduledExecutorService` with custom resource limits or monitoring and expose it under a verified JNDI name. Spring supports overriding it:

~~~java
@Bean(name = "taskScheduler")
public TaskScheduler taskScheduler() {
    DefaultManagedTaskScheduler scheduler = new DefaultManagedTaskScheduler();
    scheduler.setJndiName("java:comp/env/concurrent/ReportsScheduler");
    return scheduler;
}
~~~

This is **an illustrative Spring bean method**, requiring imports as in `ManagedSchedulingConfig`. The name `java:comp/env/concurrent/ReportsScheduler` is merely an example of an admin-configured binding, **not a JNDI resource guaranteed to exist on every server**. You must configure the real resource/ref in the deployment descriptor or application server and ensure the resolved resource implements `ScheduledExecutorService`.

Other setters:

- `setJndiEnvironment(Properties)`: sets JNDI environment properties if required by the runtime.
- `setJndiTemplate(JndiTemplate)`: overrides the JNDI template for integration or custom configuration.
- `setResourceRef(boolean)`: affects relative-name resolution against the `java:comp/env/` environment naming context.
- `setJndiName(String)`: overrides the default lookup name.

Prefer **full names** to avoid prefix-resolution confusion. When a name already begins with `java:`, `java:comp/env/` is not prepended automatically. Never change the name at runtime after the bean has completed lookup expecting existing tasks to migrate automatically to a new resource.

### When Does the Lookup Run?

`DefaultManagedTaskScheduler` is a Spring `InitializingBean`. Within a Spring-managed bean's lifecycle, `afterPropertiesSet()` runs after property setters to perform the lookup. Hence:

~~~text
Spring creates bean
  -> optional setJndiName / other setters
  -> BeanFactory invokes afterPropertiesSet()
  -> JNDI lookup resolves managed scheduler
  -> bean ready for schedule() / @Scheduled
~~~

If you instantiate the wrapper with `new` **outside Spring**, you must manage initialization and dependencies manually; that is not the primary pattern of this lesson. **Do not call `afterPropertiesSet` manually inside a Spring-managed `@Bean` method**; doing so can trigger duplicate lookups or confusing lifecycle errors.

## 7. @EnableScheduling, @Scheduled, and the taskScheduler Bean Name

In Spring 6.x, `@Scheduled` registration infrastructure looks up a scheduler from the context according to documented rules: it can pick a unique `TaskScheduler` bean, or a bean named `taskScheduler`, or fall back to looking up a `ScheduledExecutorService` if applicable. When none resolves, Spring may create a default local single-threaded scheduler.

This creates a subtle trap: **seeing `@Scheduled` run does not prove the application is using the Jakarta managed scheduler**. If your config wasn't imported or the bean wasn't selected, Spring may be running on a fallback scheduler.

Verify in three ways:

1. Does the Spring context contain a `taskScheduler` bean of type `DefaultManagedTaskScheduler`?
2. Did the bean's JNDI lookup succeed, with its delegate pointing to the expected managed resource?
3. In an integration test on the **real server**, do tasks run under the managed executor's policies/threads, and do server metrics reflect activity?

### Explicit Scheduler Selection via SchedulingConfigurer

When an application defines multiple schedulers:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.annotation.SchedulingConfigurer;
import org.springframework.scheduling.config.ScheduledTaskRegistrar;

@Configuration
public class ExplicitSchedulingSelection implements SchedulingConfigurer {
    private final TaskScheduler managedScheduler;

    public ExplicitSchedulingSelection(
            @Qualifier("taskScheduler") TaskScheduler managedScheduler) {
        this.managedScheduler = managedScheduler;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar registrar) {
        registrar.setTaskScheduler(managedScheduler);
    }
}
~~~

This is a **Spring configuration class** used alongside `@EnableScheduling` in the right config. It explicitly binds tasks managed by the registrar to the `taskScheduler` bean, reducing the risk of picking the wrong scheduler when new beans are added.

If you explicitly use `@Scheduled(scheduler = "beanName")` in a Spring version supporting scheduler qualifiers, verify the exact bean name/qualifier and how it interacts with `SchedulingConfigurer`; never rely on defaults when multiple candidates exist.

## 8. TaskScheduler APIs Provided by DefaultManagedTaskScheduler

`DefaultManagedTaskScheduler` inherits from `ConcurrentTaskScheduler` and implements Spring's `TaskScheduler`:

| API | Meaning |
| --- | --- |
| `schedule(Runnable, Instant)` | Schedules a one-shot run at the point in time represented by `Instant` |
| `schedule(Runnable, Trigger)` | Schedules via a Spring `Trigger`, such as cron or a custom trigger |
| `scheduleAtFixedRate(Runnable, Duration)` | Repeats at a fixed period from a default start |
| `scheduleAtFixedRate(Runnable, Instant, Duration)` | Repeats at a fixed rate starting from the specified timestamp |
| `scheduleWithFixedDelay(Runnable, Duration)` | Repeats after a delay measured from completion of the prior run |
| `scheduleWithFixedDelay(Runnable, Instant, Duration)` | Repeats with fixed delay starting from an initial timestamp |
| `getClock()` | Clock used to compute scheduling times, implementation-dependent |

Each method returns a `ScheduledFuture<?>` (though `schedule(Trigger)` may return `null` if the trigger provides no next run), allowing callers to track or cancel the schedule within executor semantics. Long periodic callbacks, exceptions, and cancellations must be handled deliberately.

### Programmatic Scheduling with an Instant

File **ReportSchedulingService.java**:

~~~java
import java.time.Instant;
import java.util.concurrent.ScheduledFuture;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.stereotype.Service;

@Service
public class ReportSchedulingService {
    private final TaskScheduler scheduler;

    public ReportSchedulingService(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    public ScheduledFuture<?> requestReportOnce(
            String reportId, Instant at) {
        return scheduler.schedule(
                () -> generateReport(reportId), at);
    }

    private void generateReport(String id) {
        System.out.println("Generating report " + id);
    }
}
~~~

This is a **Spring-managed service** requiring a `TaskScheduler` bean. It schedules a one-shot run at `at`. The `ScheduledFuture` return value is an in-JVM handle for tracking/cancelling the schedule; it is **not a durable job ID** to persist across deployments. In multi-replica deployments, each instance receiving `requestReportOnce` and holding handles in RAM has no cluster-wide job coordination.

### Using CronTrigger

~~~java
import java.time.ZoneId;
import org.springframework.scheduling.support.CronTrigger;

scheduler.schedule(
        () -> recalculateDailyStats(),
        CronTrigger.forFixedExecution("0 0 2 * * *"));
~~~

This is an **integration snippet requiring `scheduler` and `recalculateDailyStats`** supplied by the application. Spring cron expressions contain six fields, including **seconds**. To specify a time zone, use the `CronTrigger` API appropriate for your Spring version or `@Scheduled(cron = ..., zone = ...)`. The example above runs at 02:00 in the trigger's default clock/time zone; never assume it means "02:00 Vietnam time" without setting a zone.

**Spring version note:** the `CronTrigger.forFixedExecution(String)` factory exists in Spring 6.1.3+; on older versions, use the constructor/factory documented for that release. If your goal is simply an annotated method, `@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")` is clearer.

## 9. How Do Spring Trigger and Jakarta Trigger Differ?

Spring defines `org.springframework.scheduling.Trigger` and `CronTrigger`. Jakarta Concurrency defines `jakarta.enterprise.concurrent.Trigger` and `ManagedScheduledExecutorService.schedule(Runnable, Trigger)`. These are **two distinct interfaces** and cannot be cast interchangeably.

Spring's `ConcurrentTaskScheduler` recognizes a delegate of type `ManagedScheduledExecutorService` and adapts a `Spring Trigger` using Jakarta's trigger mechanism when appropriate. As a result, a Spring service can call `scheduler.schedule(runnable, springTrigger)` without manually implementing `jakarta.enterprise.concurrent.Trigger`.

~~~text
Spring CronTrigger
       |
       v
Spring TaskScheduler.schedule(Runnable, Spring Trigger)
       |
       v
ConcurrentTaskScheduler adapter
       |
       +-- is delegate a ManagedScheduledExecutorService?
             |
             +-- Yes: use Jakarta Trigger adapter when appropriate
             |
             +-- No: fall back to JDK delay-based scheduling
~~~

This does not mean every implementation shares identical scheduling details. Run integration tests especially for cron, time zones, DST, misfires, skipped runs, and custom triggers. Server policies still govern actual execution timing.

## 10. Fixed-Rate, Fixed-Delay, and Cron: Do Not Choose by Name Alone

Three strategies to understand:

### Fixed-rate

`scheduleAtFixedRate` expresses a cadence anchored to start timestamps. If a task runs long or the executor is overloaded, actual start times can drift from the schedule. Under the standard `ScheduledThreadPoolExecutor` contract, periodic runs of **the same periodic task** do not execute concurrently; if one run exceeds the period, the next run may start late.

Do not generalize every detail to every vendor implementation of `ManagedScheduledExecutorService`, especially extended trigger features or clustered environments. Test and consult the server documentation.

### Fixed-delay

`scheduleWithFixedDelay` waits a fixed interval after the previous run **completes** before running the next one. Often ideal when you want to prevent data-processing runs from piling up, especially for tasks with variable runtimes.

### Cron/Trigger

`CronTrigger` relies on calendar fields (hour, day, weekday, month) or Spring's `TriggerContext`. Real-world outcomes are influenced by time zones, system clocks, daylight saving time, prior task completion time, and trigger semantics. For "daily at 02:00," always specify a zone and handle DST skipped/repeated hours. For financial or SLA-bound integrations, add idempotency and verify actual run times.

### Selection Table

| Goal | Suitable API / annotation | Notes |
| --- | --- | --- |
| Once after 10 seconds | `TaskScheduler.schedule(task, Instant)` | Not durable across JVM restarts |
| Aim to start every 60 seconds | `scheduleAtFixedRate(..., Duration.ofSeconds(60))` | Slow tasks or overload can drift the cadence |
| Wait 60 seconds after previous run finishes | `scheduleWithFixedDelay(..., Duration.ofSeconds(60))` | Actual start-to-start interval exceeds the duration |
| Daily at a specific clock time | `@Scheduled(cron=..., zone=...)` or `CronTrigger` | Understand time zones/DST and cron syntax |
| Based on completion/actual times | Custom Spring `Trigger` | Test trigger behavior against `TriggerContext` |
| Recover schedules after server restart | Persistent job store / enterprise scheduler | Not just `DefaultManagedTaskScheduler` |

## 11. How Much Managed Context Does the Container Propagate?

Jakarta Concurrency specifies that the default `ManagedScheduledExecutorService` must support certain component contexts. Per the specification, mandatory context for the default managed scheduled executor includes the **naming context**, **classloader**, and **security information** associated with the submitting component.

This does **not** mean:

- Every custom request `ThreadLocal` is copied automatically.
- All MDC or tracing values appear automatically on the worker.
- An active transaction on the submitting thread propagates to the execution thread.
- `@RequestScoped` beans behave identically to executing inside an active HTTP request.
- A scheduled job's output automatically streams back to a client under a request/response contract.

The managed executor spec states explicitly that tasks run **outside the submitting thread's transaction**. If a task requires a transaction, define a transaction boundary for execution—such as calling a separate Spring `@Transactional` service through its proxy with a suitable transaction manager; Jakarta also offers `UserTransaction` where permitted.

### Separate Transactional Spring Service Example

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryRefreshService {
    private final InventoryRepository repository;

    public InventoryRefreshService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void refreshInventory() {
        repository.refreshCachedInventory();
    }
}
~~~

This is an **illustrative Spring bean** using an application-owned `InventoryRepository`. The scheduled method lives in another bean:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InventoryRefreshSchedule {
    private final InventoryRefreshService service;

    public InventoryRefreshSchedule(InventoryRefreshService service) {
        this.service = service;
    }

    @Scheduled(fixedDelay = 60000)
    public void refresh() {
        service.refreshInventory();
    }
}
~~~

This is a **separate Spring component**, calling through `InventoryRefreshService`'s bean proxy so the transaction starts on the worker. Never call `this.refreshInventory()` inside the same service expecting proxy-mode `@Transactional` to take effect. Transaction manager configuration must match the real Jakarta EE/JTA/JDBC resources.

If the application needs MDC/tracing propagation, use context propagation supported by the framework/container or pass required values explicitly via payloads/IDs; avoid relying on thread names or implicit `ThreadLocal`s.

## 12. Lifecycle Belongs to the Jakarta EE Server, Not the Spring Bean

This is a major difference from `ThreadPoolTaskScheduler` creating a local executor.

`ManagedScheduledExecutorService` is managed by the application server and may be shared across components. Jakarta Concurrency stipulates that applications **must not attempt to control the shared lifecycle** of a managed executor via `shutdown()`/`shutdownNow()`; those lifecycle operations are specified to throw `IllegalStateException` when called by application code.

Therefore:

- Never call `shutdown()` on a JNDI-retrieved managed resource when a Spring bean is destroyed.
- Never configure `ThreadPoolTaskScheduler.setPoolSize()` expecting it to resize an administrator-created pool.
- Never extract a `ScheduledThreadPoolExecutor` from the Spring wrapper to tune core threads: the real delegate may be a container-managed object that does not even expose that API.
- On redeploy/shutdown, the server has authority to suspend, stop, or cancel tasks per policy; applications need idempotency and durable state for critical work.
- Tasks run within the component's context; once the component is no longer started, the spec prohibits its tasks from continuing normal active execution.

**Wrapper lifecycle and managed delegate lifecycle are two separate things.** Spring can create and destroy the application's `DefaultManagedTaskScheduler` bean, but it has no authority to shut down the Jakarta EE server's shared resource.

### In-App Cancellation

A `ScheduledFuture<?>` returned by the scheduler can be used to request cancelling a **specific schedule**, subject to the executor's contract. This is not a shutdown command for the entire managed scheduler. For periodic jobs, keep the handle if you need to disable a schedule in one instance; across multiple instances or restarts, an in-RAM handle cannot serve as a durable job identity.

## 13. DefaultManagedTaskScheduler vs. Other Options

| Class | Underlying executor | Who owns threads/lifecycle? | Typical environment |
| --- | --- | --- | --- |
| `DefaultManagedTaskScheduler` | JNDI `ManagedScheduledExecutorService` or compatible `ScheduledExecutorService` | Container/owner of the JNDI resource | Jakarta EE application server |
| `ConcurrentTaskScheduler` | Supplied or configured `ScheduledExecutorService` | Whoever created/passed the executor | Adapter for an existing executor |
| `ThreadPoolTaskScheduler` | Local `ScheduledThreadPoolExecutor` | Spring bean/app | Standalone Spring Boot, environments permitting self-managed threads |
| `DefaultManagedTaskExecutor` | JNDI `ManagedExecutorService` | Jakarta EE container | Task dispatch not needing scheduling |
| `ThreadPoolTaskExecutor` | Local `ThreadPoolExecutor` | Spring bean/app | `@Async` or general task queues |

### Why Not Use DefaultManagedTaskExecutor for Scheduling?

`DefaultManagedTaskExecutor` looks up the default `java:comp/DefaultManagedExecutorService`, not the default scheduled executor. It suits `execute/submit` for tasks without `schedule`/`fixedRate`/`Trigger`. When scheduling is needed in Jakarta EE, **`DefaultManagedTaskScheduler`** is the proper adapter.

### Why Not Always Use ThreadPoolTaskScheduler?

`ThreadPoolTaskScheduler` makes total sense in standalone applications. It lets you configure pool size, thread-name prefix, error handler, and shutdown behavior via bean properties. However, it owns a local pool and may violate threading policies on a strict Jakarta EE server. The Spring reference recommends a managed scheduler when applications should not create threads themselves inside an application server.

### Does an Embedded Servlet Container Mean a Full Jakarta EE Runtime?

No. A Spring Boot application running with embedded Tomcat/Jetty typically **does not have** a Jakarta Concurrency default managed scheduled executor bound at `java:comp/DefaultManagedScheduledExecutorService` simply because it uses the `jakarta.servlet.*` API. Without JNDI resource infrastructure, `DefaultManagedTaskScheduler` is the wrong fit; use `ThreadPoolTaskScheduler` or an explicitly configured executor adapter.

Conversely, on a full Jakarta EE application server, do not spin up an unmanaged pool just to skip JNDI verification because it happened to run locally.

## 14. Standalone Java 17+ Example to Exercise the Scheduled Executor API

`DefaultManagedTaskScheduler` **cannot be proved valid for a Jakarta EE environment** with a plain JDK program alone. For a runnable and verifiable exercise, this section uses a **local `ScheduledExecutorService`**—the exact API extended by `ManagedScheduledExecutorService`. The demo practices one-shot execution, cancellation before start, and periodic scheduling; afterward, test the managed scheduler bean separately on a real server.

File **ScheduledExecutorContractDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class ScheduledExecutorContractDemo {

    private static void ensure(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch release = new CountDownLatch(1);

        try {
            AtomicBoolean oneShotRan = new AtomicBoolean();
            ScheduledFuture<?> oneShot = scheduler.schedule(
                    () -> oneShotRan.set(true),
                    0, TimeUnit.MILLISECONDS);
            oneShot.get(5, TimeUnit.SECONDS);
            System.out.println("oneShot=" + oneShotRan.get());

            CountDownLatch blockerStarted = new CountDownLatch(1);
            Future<?> blocker = scheduler.submit(() -> {
                blockerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            ensure(blockerStarted.await(5, TimeUnit.SECONDS),
                    "Blocker did not start");

            AtomicBoolean cancelledBodyRan = new AtomicBoolean();
            ScheduledFuture<?> queued = scheduler.schedule(
                    () -> cancelledBodyRan.set(true),
                    0, TimeUnit.MILLISECONDS);

            boolean cancelled = queued.cancel(false);
            release.countDown();

            blocker.get(5, TimeUnit.SECONDS);
            scheduler.schedule(() -> {},
                    0, TimeUnit.MILLISECONDS).get(5, TimeUnit.SECONDS);

            System.out.println("cancelBeforeStart=" + cancelled);
            System.out.println("cancelledBodyRan=" + cancelledBodyRan.get());

            AtomicInteger count = new AtomicInteger();
            CountDownLatch thirdRun = new CountDownLatch(3);

            ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
                    () -> {
                        int current = count.incrementAndGet();
                        if (current <= 3) {
                            thirdRun.countDown();
                        }
                    },
                    0, 10, TimeUnit.MILLISECONDS);

            ensure(thirdRun.await(5, TimeUnit.SECONDS),
                    "Periodic task did not run three times");

            boolean cancelledPeriodic = periodic.cancel(false);
            System.out.println("periodicAtLeastThree=" + (count.get() >= 3));
            System.out.println("periodicCancelled=" + cancelledPeriodic);
        } finally {
            release.countDown();
            scheduler.shutdownNow();
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run:

~~~bash
javac ScheduledExecutorContractDemo.java
java ScheduledExecutorContractDemo
~~~

Stdout controlled via latches/Futures:

~~~text
oneShot=true
cancelBeforeStart=true
cancelledBodyRan=false
periodicAtLeastThree=true
periodicCancelled=true
~~~

**Why is the output deterministic?**

1. `oneShot.get(timeout)` returns only after the first runnable completes, so `oneShot=true`.
2. `blockerStarted.await` proves the single worker is occupied; the queued task has no thread yet, so `cancel(false)` succeeds. The marker task confirms the worker drained past that queue entry; the cancelled body never executed.
3. `thirdRun` counts at least three executions of the periodic task; the exact count is not printed to avoid depending on whether the scheduler outruns `main`. `cancel(false)` terminates an uncompleted periodic Future; it can stop future runs, though it does not guarantee interrupting a currently executing body.
4. `finally` shuts down **the local executor created by the demo itself**. In a real Jakarta EE application, **never copy `shutdownNow()` to call on the server's managed scheduled executor**.

This demo illustrates the **JDK contract**; it does not simulate JNDI, security/context propagation, Jakarta scheduling `Trigger`s, or application server policies.

## 15. Mandatory Integration Testing on the Jakarta EE Server

To prove `DefaultManagedTaskScheduler` works in reality, tests must run inside or integrate with the **target Jakarta EE runtime**, not just a local Spring Boot unit test.

### Checklist

1. **JNDI resource:** verify the server exposes `java:comp/DefaultManagedScheduledExecutorService` or the administrator-supplied name; verify it actually implements a compatible `ManagedScheduledExecutorService`.
2. **Bean lookup:** start the Spring context with `DefaultManagedTaskScheduler`; startup must not throw `NamingException`/`BeanCreationException`.
3. **Selected scheduler:** confirm `@EnableScheduling` uses the `taskScheduler` bean or the right `SchedulingConfigurer` setup rather than a local fallback.
4. **One-shot:** schedule a one-time task and use `CountDownLatch` plus `ScheduledFuture.get(timeout)` to confirm execution.
5. **Fixed-rate/fixed-delay:** schedule a short task with a small period/delay in the test environment and cancel the future in `finally`; avoid arbitrary sleeps.
6. **Cron/Trigger:** test time zones and triggers; test the Spring-to-Jakarta trigger adapter on the real server/version.
7. **Component context:** inside the task, verify naming/classloader/security per server contract; do not assume MDC/transactions inherit automatically.
8. **Transactions:** verify the task does not join the submitting thread's transaction, and a separate transactional service can open a transaction via Spring/JTA.
9. **Error paths:** throw a controlled exception and verify the container's error handler/logging and periodic continuation policy, rather than assuming local executor behavior.
10. **Overload/rejection:** use a quota-limited test resource to observe how the server responds; do not fabricate max pool or queue numbers.
11. **Redeploy/shutdown:** verify how tasks from an older application component are handled; prevent old jobs from touching an unloaded classloader.
12. **Multi-instance:** deploy multiple replicas/nodes if required by the environment, verifying whether each instance schedules independently or the app server provides cluster coordination.

### A Latch-Based Test

Assuming `TaskScheduler scheduler` is injected by Spring:

~~~java
CountDownLatch received = new CountDownLatch(1);
ScheduledFuture<?> future = scheduler.schedule(
        received::countDown,
        java.time.Instant.now().plusSeconds(1));

try {
    if (!received.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Managed task did not execute");
    }
} finally {
    if (future != null) {
        future.cancel(false);
    }
}
~~~

This is an **integration test fragment**, requiring `CountDownLatch`, `ScheduledFuture`, `TimeUnit`, and a configured context/container. It only confirms execution occurred; to prove **managed context**, inspect context/JNDI attributes and server-side evidence. Never call `Thread.sleep(1000)` and guess the worker ran.

### Do Not "Fake" a Managed Scheduler with Local Startup

A unit test can inject a stub/mock `TaskScheduler` to test business logic, or use `ThreadPoolTaskScheduler` under a local profile for fast feedback. Yet those tests **prove nothing about** JNDI lookup, server lifecycle, or Jakarta EE context. Separate:

- **Unit tests:** task logic, idempotency, exception handling, cron expression validation.
- **Integration tests:** JNDI lookup, real managed executor, server lifecycle, context propagation, and scheduler selection.

This is a core part of choosing a scheduler based on **deployment environment**, not unit-test convenience.

## 16. Errors, Exceptions, and Scheduling Incidents

### Errors at Bean Startup

If the default JNDI name is absent, `DefaultManagedTaskScheduler.afterPropertiesSet` may throw `NamingException`; during Spring bean creation, this becomes a startup failure. Resolve by:

- Verifying the app runs on a Jakarta EE runtime providing a compatible resource.
- Checking the JNDI naming tree/descriptors against `setJndiName`.
- Checking JNDI resource permissions, deployment context, and classloader.
- Verifying `javax`/`jakarta` namespaces and Spring/Jakarta EE versions.
- If running standalone Spring Boot without the resource, pick a local scheduler explicitly instead of mocking up JNDI just to pass startup.

### Errors Inside Tasks

Periodic tasks can throw exceptions. Spring's scheduler has an error-handler mechanism, while the managed delegate and server have their own exception policies. Never assume an exception is thrown back to the caller that registered the schedule; the caller may have returned long ago.

Design for:

- Logs/metrics with correlation/job IDs, omitting sensitive payloads.
- Explicit error policy: log, stop schedule, retry, dead-letter, or update job-store state.
- I/O timeouts so a hung run cannot occupy a managed worker indefinitely.
- Calling `ScheduledFuture.get()` only for one-shot tasks or after a periodic task finishes/is cancelled; calling `get()` on an active periodic task usually blocks forever.

`ConcurrentTaskScheduler` provides `setErrorHandler(ErrorHandler)` on the Spring adapter; when using it, test its actual impact with periodic scheduling and the managed delegate. Never swallow exceptions so failures repeat endlessly without visibility.

### Rejection and Quotas

The container can enforce capacity limits, policies, and lifecycle rules. When the resource refuses a task, the schedule call can fail. Spring does not durably retry automatically. For critical schedules, persist requests/jobs and implement replay; never assume a task was accepted if `schedule` threw an exception.

### Clocks and Time Zones

One-shot runs use `Instant`, while cron uses calendar/time zones. JVM clock shifts, time zones/DST, or server clock policies can affect execution timing. Log **scheduled time**, **actual start time**, and **completion time** to diagnose drift rather than comparing only total run counts.

## 17. Multiple Replicas, Exactly-Once, and Durability

`DefaultManagedTaskScheduler` **is not a clustered persistent scheduler**. Each Spring application context/instance typically registers its own schedules. If the same app runs on three nodes and each has `@Scheduled` beans, all three nodes will likely run the job unless the server/app infrastructure enforces explicit cluster coordination.

Do not infer that "managed by Jakarta EE" means the scheduler **runs once across the whole cluster**. Jakarta Concurrency specifies at-most-once quality-of-service per **task submission** within the managed executor, and tasks are **transient** by default and do not survive process restarts. That does **not** mean global exactly-once execution of a business job across replicas.

If a job must run only once cluster-wide:

- Use a distributed lock/lease with expiration and fencing tokens where appropriate.
- Use a database job table with atomic claiming and retries/idempotency.
- Use Quartz with a persistent `JobStore`/cluster mode if warranted.
- Use a message broker/job queue with consumer coordination when the task is really distributed work.
- Define idempotency keys so re-runs do not cause double charges or duplicate notifications.

An **on-time** schedule also does not guarantee side effects succeeded: a job can fail, time out, or crash. Measure completion outcomes separately from trigger counts.

### Restarts and Lost Schedules

In-memory scheduled tasks do not automatically recover across shutdowns or redeploys. If a one-shot task is scheduled for 23:00 and the server restarts at 22:59 without a durable job store, that schedule can be lost. For periodic `@Scheduled` methods, each fresh context re-registers schedules, yet that is a fresh startup registration—not transaction recovery or "missed execution" replay per a business contract.

## 18. Focused Operational Observability

In Jakarta EE, capacity and quotas are managed by administrators, so metrics from the application server are critical. The application should also measure:

| Metric | Question answered |
| --- | --- |
| `scheduled_jobs_registered` | How many schedules are registered? |
| `scheduled_task_started_total` | How many runs actually started? |
| `scheduled_task_completed_total` | How many runs completed successfully? |
| `scheduled_task_failed_total` | How many runs failed? |
| `scheduler_rejected_total` | How many times did the container reject new schedules? |
| `schedule_start_delay` | How late did it start relative to the expected time? |
| `task_execution_duration` | How long did each run occupy a worker? |
| `cancel_requested_total` | How many schedules/tasks were requested to cancel? |
| `managed_executor_active_threads` | How many workers is the container allocating (if vendor exposes metrics)? |
| `missed_business_deadline_total` | How many jobs missed business SLAs? |

Never invent thread-pool metrics if the vendor does not expose them or the wrapper provides no corresponding API. Inspect the application server's JMX/management APIs. Use sensible tag cardinality (job type, node, outcome), avoiding high-cardinality labels like unique `jobId`s.

### Measuring the Right Three Timestamps

~~~text
scheduled timestamp ------ actual start ------- actual completion
               drift                     processing duration
~~~

If an app only logs "job finished at 10:05," it is hard to distinguish whether the scheduler triggered late or the job ran slowly. Because `DefaultManagedTaskScheduler` does not persist execution history, telemetry must be part of the design from day one.

## 19. Common Mistakes to Avoid

1. **Running `DefaultManagedTaskScheduler` in Java SE/standalone Spring Boot** expecting standard Jakarta EE JNDI resources.
2. **Confusing `DefaultManagedTaskScheduler` with `DefaultManagedTaskExecutor`.** The default JNDI names differ; a scheduler needs a scheduled executor.
3. **Enabling only `@EnableAsync` to run `@Scheduled`.** Scheduling requires `@EnableScheduling` or an equivalent mechanism.
4. **Having multiple `TaskScheduler` beans without specifying which to use.** Spring may pick the wrong one or fall back locally.
5. **Calling the constructor thinking the adapter creates a thread pool.** It looks up the executor via JNDI at bean init.
6. **Calling `afterPropertiesSet()` manually inside a `@Bean` method.** `BeanFactory` already invokes the lifecycle hook.
7. **Setting `setJndiName` wrongly or using an unbound JNDI name.** Bean startup can fail.
8. **Catching `NamingException` and silently falling back to a local pool in Jakarta EE production** without an architectural decision on thread governance.
9. **Using `javax.enterprise.concurrent.*` with Spring 6/modern Jakarta without checking compatibility.** The API namespaces are not equivalent.
10. **Calling `shutdown`/`shutdownNow` on a managed executor.** Lifecycle belongs to the server; applications have no authority to shut it down.
11. **Trying to call `setPoolSize` on `DefaultManagedTaskScheduler`.** The wrapper does not own a pool like `ThreadPoolTaskScheduler`.
12. **Assuming the default managed scheduled service guarantees durability.** Jakarta Concurrency tasks are normally transient.
13. **Equating "at-most-once" with cluster-wide exactly-once.** No such guarantee exists.
14. **Assuming a managed thread carries the request's transaction.** Tasks run outside the submitter's transaction.
15. **Assuming arbitrary `MDC`/`ThreadLocal` values propagate automatically.** The spec covers only specific contexts; others require explicit support.
16. **Using `@Scheduled` for critical emails/billing without idempotency.** Node restarts and multi-replica deployments can drop or duplicate runs.
17. **Using `fixedRate` for long tasks without measuring drift.** Tasks cannot guarantee on-time starts under overload.
18. **Confusing `fixedDelay` with `fixedRate`.** One measures from completion, the other from cadence timestamps.
19. **Choosing cron while forgetting time zones/DST.** Execution times shift unexpectedly across time-zone transitions.
20. **Assuming `@Scheduled` always runs on threads separate from the application.** It depends on the adapter/executor and actual config.
21. **Unit testing only with a local `ScheduledExecutorService` and declaring Jakarta JNDI verified.** Integration testing on the real runtime is required.
22. **Ignoring task exceptions or rejections.** Subsequent runs can be affected by implementation/policy.
23. **Calling `ScheduledFuture.get()` immediately on a periodic schedule and blocking forever.** A periodic future does not complete normally per run.
24. **Failing to clean up app schedules on lifecycle exit** while trying to shut down the shared managed resource. Distinguish cancelling your own tasks from shutting down the executor.
25. **Ignoring task cancellation/execution across redeploys.** Old code must not keep running after its component stops.
26. **Reading local thread counts to administer the server's managed executor.** Capacity policy belongs to the server.
27. **Letting multiple application contexts register duplicate `@Scheduled` methods.** This can multiply runs unexpectedly.
28. **Assuming Docker/Kubernetes automatically provisions Jakarta managed resources.** Container orchestration infrastructure is not a Jakarta EE application server.
29. **Treating `TaskScheduler` as a durable job scheduler.** `TaskScheduler` is primarily an in-process scheduling API.
30. **Silently falling back when JNDI fails without approval.** Masks deployment/admin errors and violates thread policies.

## 20. Process for Choosing a Scheduler for Your Environment

Decide based on operational conditions:

1. **What is the runtime?** A Jakarta EE application server with a managed scheduled executor, or standalone Spring Boot / embedded servlet?
2. **Who has authority to manage threads?** If the application server mandates managed threads, choose the managed resource matching the contract.
3. **What does the scheduler need?** `@Scheduled`, cron, fixed-delay, dynamic scheduling, cancellation; do you need custom pool/queue tuning?
4. **Which JNDI name actually exists?** The standard default or an administrator-provisioned resource? Read deployment docs for the exact server/version.
5. **Which bean does Spring select?** Register `taskScheduler` or `SchedulingConfigurer` explicitly; avoid ambiguous fallback paths.
6. **What transaction/security context is needed?** Managed executors propagate component context, not caller transactions; design a separate transactional bean.
7. **Are durability/clustering required?** If yes, move to a job store/Quartz/message queue rather than relying solely on the scheduler.
8. **Where is it tested?** Unit test business logic with local/mocks; integration test JNDI and managed execution on the real server.
9. **How is it observed?** Log run ID, planned/actual timestamps, outcome, duration, rejections, and JVM/node.
10. **What is the rollback plan for misconfiguration?** Prepare deployment config/health checks; never silently revert to unmanaged threads.

### Quick Decision Table

| Context | Starting choice |
| --- | --- |
| Jakarta EE application server with JSR-236/Jakarta managed scheduled executor | **`DefaultManagedTaskScheduler`** |
| Standalone Spring Boot without JNDI managed resources | **`ThreadPoolTaskScheduler`** |
| Existing `ScheduledExecutorService` created and owned elsewhere | **`ConcurrentTaskScheduler`** |
| Only need submit/execute via managed executor | **`DefaultManagedTaskExecutor`** |
| Need durable schedules/clustering/misfire recovery | **Persistent scheduler/job store**, potentially Quartz |
| Multiple schedulers in one context | **Explicit bean names/qualifiers and `SchedulingConfigurer`** |
| Requirement not to spawn threads manually in an app server | **Avoid local pools; prefer managed resources** |

## 21. Self-Check Questions

1. Which class does `DefaultManagedTaskScheduler` extend, and what problem does Spring use it to solve?
2. What is its default JNDI name? How does it differ from `java:comp/DefaultManagedExecutorService`?
3. When does `afterPropertiesSet()` look up the resource? Why should you not call it manually inside a Spring-managed `@Bean`?
4. How does `@EnableScheduling` differ from `@EnableAsync`?
5. When should you name a bean `taskScheduler` or use `SchedulingConfigurer`?
6. Why does Spring Boot with embedded Tomcat not necessarily have a default Jakarta Concurrency resource?
7. Distinguish `fixed-rate`, `fixed-delay`, and `cron` for a task running longer than its period.
8. Are `Spring Trigger` and `jakarta.enterprise.concurrent.Trigger` the same interface?
9. Which types of component context are supported by the Jakarta Concurrency default managed scheduled executor?
10. Why doesn't a worker inherit the submitting thread's transaction? If a job needs a DB transaction, how should you structure Spring services?
11. Who owns the lifecycle of `ManagedScheduledExecutorService`? May the application call `shutdownNow()`?
12. Why is `@Scheduled` running not enough proof that Spring is using `DefaultManagedTaskScheduler`?
13. Is a `ScheduledFuture` a durable job identifier across redeploys?
14. When deploying an application across three nodes, does a managed scheduler automatically guarantee cluster-wide single execution?
15. Why must you test JNDI resources in a real Jakarta EE server instead of only mocking a scheduler locally?
16. Should a financial transaction that must run exactly once and survive restarts rely solely on `DefaultManagedTaskScheduler`?
17. If `schedule` is rejected when the server is overloaded, what error reporting/recording steps should the system take?
18. Why should you not silently fall back to `Executors.newScheduledThreadPool` on Jakarta EE when JNDI lookup fails?

## 22. Official Documentation

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — DefaultManagedTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/DefaultManagedTaskScheduler.html)
- [Spring Framework 6.2 — ConcurrentTaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskScheduler.html)
- [Spring Framework — @EnableScheduling Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html)
- [Spring Framework — TaskScheduler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — SchedulingConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/SchedulingConfigurer.html)
- [Jakarta Concurrency Specification 3.1](https://jakarta.ee/specifications/concurrency/3.1/jakarta-concurrency-spec-3.1)
- [Jakarta EE — Concurrency Explained](https://jakarta.ee/learn/specification-guides/concurrency-explained/)
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [Java SE 17 — ScheduledFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

**Takeaway:** `DefaultManagedTaskScheduler` is a **JNDI-backed Spring `TaskScheduler` adapter**, defaulting to Jakarta EE's `java:comp/DefaultManagedScheduledExecutorService`. Choose it when the application server **owns threads and lifecycle**; for `@Scheduled` to use it, configure the Spring bean and `@EnableScheduling` properly. Never call shutdown on the managed executor, never assume transactions propagate automatically, and never confuse in-RAM scheduled tasks with a **persistent/clustered job scheduler**. When running standalone without JNDI, pick an explicitly managed local scheduler instead of assuming a Jakarta EE environment.