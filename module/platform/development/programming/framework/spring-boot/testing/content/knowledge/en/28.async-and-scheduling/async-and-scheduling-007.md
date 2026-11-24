# Controlling Automatic Scheduler Execution on Test Context Startup in Spring Boot

> **Module:** Spring Boot – testing  
> **Group:** Async and Scheduling  
> **Topic:** Controlling automatic scheduler execution on test context startup  
> **Goal:** Prevent `@Scheduled` from executing unintentionally when `@SpringBootTest` initializes the context; distinguish annotation processing, cron, executor pools, and business handlers; design conditional configuration and properly test scheduler-off, cron-off, and scheduler-on using Java 17, Spring Boot 3.5, and JUnit Jupiter.

## 1. Real-world problem

An application has jobs that clean up transaction history, compute invoices, sync external APIs, or send periodic emails. A test may only aim to check a service, repository, or REST controller, yet `@SpringBootTest` loads an almost full Spring `ApplicationContext`.

If `@EnableScheduling` configuration is loaded, Spring registers `@Scheduled` methods once context refresh completes. A job can run automatically on a scheduler thread **before a single JUnit assertion begins**, without the test ever calling that method directly.

Consequences:

- Background jobs delete or modify fixtures being used in the test.
- Tests pass when run individually, fail when run in the full suite or in parallel.
- Accidental calls to real mail/APIs/Redis/Kafka/databases because the test has not overridden connection details yet.
- The scheduler runs on another thread and therefore does not roll back with the test method's `@Transactional`.
- Mock HTTP clients are declared, yet the job ticks before the test stubs behavior.
- `ApplicationContext` is cached across test classes, keeping the scheduler active while other classes run.
- Too-short cron intervals cause redundant requests, duplicates, or lock contention.
- CI load differs from developer machines, making tick timing non-deterministic and creating flaky tests.
- A test JVM runs schedulers even though the test case is unrelated to scheduling.
- Multi-replica applications can trigger the same cron across multiple instances.

**Rule:** Tests that do not need cron must disable scheduling registration **before** context refresh. Only tests targeting scheduling enable that mechanism, using bounded observation with timeouts and isolated external resources.

### 1.1. Scheduling annotation processing flow

```text
@SpringBootTest starts ApplicationContext
                |
                v
       Configuration imported
                |
         @EnableScheduling?
            /       \
          no         yes
          |           |
          v           v
@Scheduled not    ScheduledAnnotationBeanPostProcessor
activated         scans managed @Scheduled beans
                      |
                 registers triggers
                      |
                   TaskScheduler
                      |
                 background thread
                      |
                job/adapter method
                      |
                business service
                      |
             database/API/queue effects
```

`@Scheduled` only describes a trigger. `@EnableScheduling` (or equivalent registration) turns on detection and registration of annotated methods. A `TaskScheduler` bean by itself does not prove `@Scheduled` methods were registered; conversely, Spring can create a local fallback scheduler when the processor has registered tasks without finding a matching `TaskScheduler` bean.

### 1.2. Things that must be distinguished

| Component | Effect | How to disable |
| --- | --- | --- |
| `@EnableScheduling` | Enables processing of `@Scheduled` | Do not import config with the annotation in tests |
| `ScheduledAnnotationBeanPostProcessor` | Registers methods by trigger | Exclude scheduling infrastructure before refresh |
| `@Scheduled(cron=...)` | Schedule by cron expression | Cron property set to `-` |
| `@Scheduled(fixedRate=...)` | Schedule by interval between start times | Conditionally register config/bean, do not use `-` |
| `@Scheduled(fixedDelay=...)` | Wait after previous execution completes | Conditionally register config/bean, do not use `-` |
| `TaskScheduler` | Executor running registered tasks | Pool config does not disable registration |
| Business service | Executes domain logic | Invoke directly without a scheduler |
| Quartz | Quartz's own scheduler | Quartz-specific configuration |
| `@Async` | Asynchronous method execution | Separate `@EnableAsync`/Executor configuration |

## 2. Spring Framework: `@EnableScheduling` and `@Scheduled`

A minimal configuration:

```java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
```

This is a Java snippet, not a complete file. When imported into a Spring context, `@EnableScheduling` enables `ScheduledAnnotationBeanPostProcessor`; the processor scans `@Scheduled` beans and registers their corresponding tasks.

### 2.1. Trigger types

```java
@Scheduled(
        fixedDelay = 5,
        timeUnit = TimeUnit.SECONDS)
public void reconcile() { /* ... */ }

@Scheduled(
        fixedRate = 5,
        timeUnit = TimeUnit.SECONDS)
public void refresh() { /* ... */ }

@Scheduled(
        cron = "0 */5 * * * *",
        zone = "UTC")
public void aggregate() { /* ... */ }
```

- **fixedDelay:** waits between when a task finishes and when the next begins.
- **fixedRate:** schedules by interval between start times; behavior when work runs long depends on scheduler/concurrency.
- **initialDelay:** delays the first launch of the trigger, but is not a disable switch.
- **cron:** Spring uses six fields: second, minute, hour, day of month, month, day of week.
- `@Scheduled` can repeat on a single method, creating multiple independent triggers.

Do not mistake Spring cron for five-field OS cron. For example, `*/1 * * * * *` runs once every second and should only be used in test sandboxes with clear observability.

### 2.2. CRON_DISABLED = `-`

Spring Framework supports `Scheduled.CRON_DISABLED` (also referenced in `ScheduledTaskRegistrar`) with the exact value **a single hyphen**. It is useful when the cron expression comes from a property:

```java
@Scheduled(cron = "${app.jobs.cleanup.cron:-}")
public void cleanup() {
    // ...
}
```

```properties
# application-test.properties
app.jobs.cleanup.cron=-
```

Spring does not register a cron trigger that resolves to `-`. The method remains a normal Java method and can still be called manually or from elsewhere. **The cron sentinel does not disable fixedRate/fixedDelay** and does not remove other `@Scheduled` triggers on the same bean.

Invalid example:

```java
@Scheduled(fixedDelayString = "${app.jobs.delay:-}")
public void run() {
}
```

If `app.jobs.delay` resolves to `-`, there is no Spring Framework contract saying fixed delay is disabled. Choose conditional registration or a cron trigger with the disabled sentinel instead of treating a hyphen as a duration.

### 2.3. Properties are needed before Spring registers tasks

Settings like `app.jobs.cleanup.cron` are resolved when Spring initializes the context and registers schedules. Changing a `System.setProperty` or static flag inside `@BeforeEach` **after context refresh** neither cancels already-registered schedules nor guarantees triggers are recreated.

Similarly, a job might be invoked by `@PostConstruct` or `ApplicationRunner` before `@BeforeEach`. Disabling cron only controls cron registration; it does not stop those lifecycle callbacks.

## 3. Do not confuse Boot scheduler pool config with a schedule off-switch

Spring Boot 3.5 documents these properties:

```properties
spring.task.scheduling.pool.size=2
spring.task.scheduling.thread-name-prefix=scheduling-
spring.task.scheduling.shutdown.await-termination=false
```

These configure the **`TaskScheduler` implementation**, not a feature toggle for `@EnableScheduling`. `pool.size=1` does not prevent a job from running or limit it to running once. Setting pool size to 0 is not a supported disable mechanism.

**Common trap:** `spring.task.scheduling.enabled=false` is not a universal built-in flag guaranteed by Spring Boot 3.5 documentation to disable all `@Scheduled` tasks. If a project has custom logic using a property with that name, verify that code. If you merely add the property hoping the framework applies it automatically, tests can pass falsely.

The durable solution is **defining your own feature switch** such as `app.scheduling.enabled` and placing `@ConditionalOnProperty` on the configuration containing `@EnableScheduling`.

### 3.1. Why not mock `TaskScheduler`?

If the annotation processor is present, it can register tasks with a provided scheduler or a fallback scheduler. A Mockito mock `TaskScheduler` might stop tasks from running because the mock doesn't actually schedule, yet that does not prove the application disabled schedules in a production-like context. A mock may also fail to return a meaningful `ScheduledFuture`.

Disabling scheduling registration via configuration is a much clearer model. For positive tests, use a real scheduler and bounded waiting.

### 3.2. Why is `@DirtiesContext` not enough?

`@DirtiesContext` controls evicting/closing the `ApplicationContext` from cache. It does not prevent scheduled tasks from ticking **while the context is alive**, before the test class ends. Use it when a test needs the scheduler on and must close it after the class, not as a scheduler-off switch.

### 3.3. Why is `@Transactional` not enough?

A JUnit test method's transaction is usually bound to the **test thread**. A scheduler thread using a different DataSource/transaction can write and commit to the DB regardless of the test's rollback. If a test does not need the scheduler, disable it. If it does need the scheduler, use a test-only DB, isolate fixtures, and manage commits/retries/cleanup.

## 4. Recommended design: separating business service from scheduled adapter

```text
BatchService
   └── business method runOnce()
            ▲
            │
BatchScheduleAdapter
   └── @Scheduled(cron=...)
            ▲
            │
SchedulingConfiguration
   └── @EnableScheduling (conditional)
```

Reasons:

- The service can be tested with pure JUnit/Mockito without clocks or thread pools.
- The adapter can be called directly without Spring scheduling.
- Context-off tests still have the business service and adapter, only lacking the annotation processor.
- Cron-off tests can verify scheduling infrastructure exists while a specific job's trigger is disabled.
- Context-on tests verify task registration and at least one real execution.
- Service external dependencies are easy to replace with appropriate fakes/mocks in integration tests.

## 5. Runnable Java 17 + Spring Boot 3.5.0 project

The example below uses no DB, email, queue, or HTTP. A service counts executions with `AtomicInteger` and pushes signals into a `BlockingQueue` so tests can await scheduler execution.

There are **6 JUnit `@Test` methods**: 2 unit, 2 context-off, 1 cron-off, 1 context-on.

### 5.1. Structure

```text
scheduler-startup-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/schedulelab/
    │   ├── ScheduleLabApplication.java
    │   ├── SchedulingConfiguration.java
    │   ├── BatchService.java
    │   └── BatchScheduleAdapter.java
    └── test/java/com/example/schedulelab/
        ├── BatchServiceUnitTest.java
        ├── SchedulingOffContextTest.java
        ├── CronOffContextTest.java
        └── SchedulingOnContextTest.java
```

Every public Java class lives in a file of the same name under package `com.example.schedulelab`.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>scheduler-startup-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent manages dependency versions, JUnit Jupiter, and AssertJ. No Docker is needed to run this example.

### 5.3. `ScheduleLabApplication.java`

```java
// src/main/java/com/example/schedulelab/ScheduleLabApplication.java
package com.example.schedulelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScheduleLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScheduleLabApplication.class, args);
    }
}
```

**`@EnableScheduling` is intentionally omitted from the application root.** Putting it directly on `@SpringBootApplication` would cause any `@SpringBootTest` loading root config to enable scheduling outside the control of custom test properties.

### 5.4. `SchedulingConfiguration.java`

```java
// src/main/java/com/example/schedulelab/SchedulingConfiguration.java
package com.example.schedulelab;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        name = "app.scheduling.enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableScheduling
public class SchedulingConfiguration {
}
```

- `app.scheduling.enabled=true`: loads config and enables annotation scheduling.
- `app.scheduling.enabled=false`: excludes config and registers no processor from this config.
- `matchIfMissing=true`: production/normal app enables it by default when the property is absent. If you want opt-in across all environments, change the default policy accordingly.
- `app.scheduling.enabled` is an **application-defined** property, not a built-in universal Spring Boot switch.
- If a second config class also has `@EnableScheduling`, it can still activate the processor. Inventory all sources when applying to a real project.

### 5.5. `BatchService.java`

```java
// src/main/java/com/example/schedulelab/BatchService.java
package com.example.schedulelab;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class BatchService {

    private final AtomicInteger completed = new AtomicInteger();
    private final BlockingQueue<Integer> signals =
            new LinkedBlockingQueue<>();

    public int runOnce() {
        int n = completed.incrementAndGet();
        signals.offer(n);
        return n;
    }

    public int count() {
        return completed.get();
    }

    public Integer awaitRun(Duration timeout)
            throws InterruptedException {
        return signals.poll(
                timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
```

`AtomicInteger` and `BlockingQueue` allow the test thread to observe signals from the scheduler thread. This is demo in-memory state; if real business logic writes to a DB or sends emails, use test-only connections/mocks and assert the corresponding side effects.

### 5.6. `BatchScheduleAdapter.java`

```java
// src/main/java/com/example/schedulelab/BatchScheduleAdapter.java
package com.example.schedulelab;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class BatchScheduleAdapter {

    private final BatchService service;

    public BatchScheduleAdapter(BatchService service) {
        this.service = service;
    }

    @Scheduled(
            cron = "${app.batch.cron:*/2 * * * * *}",
            zone = "${app.batch.zone:UTC}")
    public void tick() {
        service.runOnce();
    }
}
```

- `app.scheduling.enabled=false` prevents annotation processing; the bean and method remain present.
- `app.batch.cron=-` disables the adapter's **cron trigger**.
- `app.scheduling.enabled=true` with a valid cron lets Spring register and call `tick()`.
- `*/2 * * * * *` runs every two seconds in the demo; do not carry this setting into production jobs with external side effects.
- `zone=UTC` avoids accidental hour shifts between local and CI. Jobs on daily/weekly schedules must still have dedicated calendar and DST tests.

## 6. Unit tests: no Spring context

### 6.1. `BatchServiceUnitTest.java`

```java
// src/test/java/com/example/schedulelab/BatchServiceUnitTest.java
package com.example.schedulelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class BatchServiceUnitTest {

    @Test
    void incrementsAndSignalsCompletion() throws Exception {
        BatchService service = new BatchService();

        assertThat(service.count()).isZero();
        assertThat(service.runOnce()).isEqualTo(1);
        assertThat(service.awaitRun(
                Duration.ofMillis(100))).isEqualTo(1);
        assertThat(service.count()).isEqualTo(1);
    }

    @Test
    void adapterCanInvokeServiceWithoutScheduler() {
        BatchService service = new BatchService();
        BatchScheduleAdapter adapter =
                new BatchScheduleAdapter(service);

        adapter.tick();

        assertThat(service.count()).isEqualTo(1);
    }
}
```

These two tests check only Java logic; there is no Spring context or scheduling thread. They do not prove Spring registered the cron.

## 7. Context-off: confirming Spring did not register `@Scheduled`

### 7.1. `SchedulingOffContextTest.java`

```java
// src/test/java/com/example/schedulelab/SchedulingOffContextTest.java
package com.example.schedulelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=false",
        "app.batch.cron=*/1 * * * * *"
})
class SchedulingOffContextTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    BatchService service;

    @Autowired
    BatchScheduleAdapter adapter;

    @Test
    void hasNoScheduledAnnotationProcessor() {
        assertThat(context.getBeansOfType(
                ScheduledAnnotationBeanPostProcessor.class))
                .isEmpty();
    }

    @Test
    void jobMethodRemainsCallable() {
        int before = service.count();

        adapter.tick();

        assertThat(service.count())
                .isEqualTo(before + 1);
    }
}
```

The cron property is deliberately set to every second to show that **disabling the infrastructure decides whether tasks register**, not having a slow cron. The first test asserts the absence of the processor. The second proves the adapter/business method remains callable manually.

Do not assert `service.count()==0` in both methods: the Spring context may be cached and JUnit does not guarantee method order. The before/after pattern is order-independent and needs no shared state reset.

In an application with external custom schedulers, the absence of the processor only proves no Spring annotation scheduling within that scope; it **does not** prove the absence of Quartz/`Timer`/`ApplicationRunner`.

## 8. Context cron-off: infrastructure present but one job disabled

### 8.1. `CronOffContextTest.java`

```java
// src/test/java/com/example/schedulelab/CronOffContextTest.java
package com.example.schedulelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=true",
        "app.batch.cron=-"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CronOffContextTest {

    @Autowired
    ScheduledAnnotationBeanPostProcessor processor;

    @Autowired
    BatchService service;

    @Test
    void processorExistsButCronTriggerIsAbsent() {
        assertThat(processor).isNotNull();
        assertThat(processor.getScheduledTasks()).isEmpty();
        assertThat(service.count()).isZero();
    }
}
```

In the demo there is only one `@Scheduled` method; because its trigger is disabled, `getScheduledTasks()` is empty. In an application with many other jobs, the total scheduled task set may still be non-empty. Do not apply this global assertion to infer a specific job is disabled when other jobs remain registered.

### 8.2. Suitable cases for choosing cron-off

- Keeping scheduler infrastructure active while disabling one job with heavy side effects.
- Testing that other scheduled jobs remain active.
- Verifying conditional cron properties without dropping all scheduling config.
- Preventing a cron job from running even while its component bean stays injectable.

**Do not use** the cron disabled sentinel for fixed-delay/rate properties or to stop methods called manually via `@PostConstruct`.

## 9. Context-on: testing one real cron execution

### 9.1. `SchedulingOnContextTest.java`

```java
// src/test/java/com/example/schedulelab/SchedulingOnContextTest.java
package com.example.schedulelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.annotation.ScheduledAnnotationBeanPostProcessor;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "app.scheduling.enabled=true",
        "app.batch.cron=*/1 * * * * *",
        "spring.task.scheduling.pool.size=1"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SchedulingOnContextTest {

    @Autowired
    ScheduledAnnotationBeanPostProcessor processor;

    @Autowired
    BatchService service;

    @Test
    void registersAndExecutesCronTask() throws Exception {
        assertThat(processor.getScheduledTasks())
                .isNotEmpty();

        Integer observed =
                service.awaitRun(Duration.ofSeconds(8));

        assertThat(observed).isNotNull();
        assertThat(observed).isGreaterThan(0);
        assertThat(service.count())
                .isGreaterThanOrEqualTo(observed);
    }
}
```

- `getScheduledTasks().isNotEmpty()` checks registration.
- `BlockingQueue.poll(Duration)` waits for an execution signal without using a fixed sleep.
- If cron ticks before the JUnit method starts, the signal is already in the queue so the test still sees it.
- Do not assert exactly one execution; CI scheduling timing and context startup can vary.
- `@DirtiesContext(AFTER_CLASS)` closes the Spring context when the class ends, preventing the scheduler from continuing to tick out of cache after the test.
- `spring.task.scheduling.pool.size=1` only tunes the thread pool; it does not turn the scheduler on or off.

This test proves the scheduler executes at least once in a simple context. It **does not** prove cluster-wide exactly-once execution, correct DST behavior, or performance under load.

## 10. Running the project and expected outcomes

```bash
java -version
mvn -version

mvn -B -ntp -Dtest=BatchServiceUnitTest test
mvn -B -ntp -Dtest=SchedulingOffContextTest test
mvn -B -ntp -Dtest=CronOffContextTest test
mvn -B -ntp -Dtest=SchedulingOnContextTest test

# All 6 JUnit methods:
mvn -B -ntp test
```

| Test class | Number of `@Test` | Mechanism |
| --- | ---: | --- |
| `BatchServiceUnitTest` | 2 | Business logic, no Spring |
| `SchedulingOffContextTest` | 2 | Scheduled processor absent |
| `CronOffContextTest` | 1 | Processor present, cron disabled |
| `SchedulingOnContextTest` | 1 | Processor present, cron executed |
| **Total** | **6** | Covers both off and on branches |

The Maven commands are reproduction instructions, not an actual recorded run during authoring. Output varies by JDK/Maven/Spring Boot version, and cron ticks at different wall-clock moments on each machine.

## 11. Applying to an app with `@EnableScheduling` on the main application

An anti-pattern:

```java
@SpringBootApplication
@EnableScheduling
public class Application {
}
```

`@SpringBootTest` can load the root application and turn scheduling on automatically. Merely adding `app.scheduling.enabled=false` **has no effect** if `@EnableScheduling` directly on the main class is unconditional.

### 11.1. Recommended refactoring

1. Remove `@EnableScheduling` from the main application class.
2. Create a separate `SchedulingConfiguration` as in Section 5.4.
3. Add `@ConditionalOnProperty` so the feature switch is evaluated at context load time.
4. Set the flag to false on tests unrelated to scheduling.
5. Write one positive scheduler integration test enabling the flag.
6. If multiple `@EnableScheduling` registrations exist in other modules, consolidate them under one consistent control mechanism.

Do not remove `@EnableScheduling` for production and forget to test that scheduling is enabled in the intended deployment mode.

### 11.2. `application-test.properties`

You can use:

```text
src/test/resources/application-test.properties
```

with contents:

```properties
app.scheduling.enabled=false
app.batch.cron=-
```

When a test wants to activate the profile:

```java
@ActiveProfiles("test")
@SpringBootTest
class CustomerControllerTest {
    //...
}
```

This is an annotation snippet; import `org.springframework.test.context.ActiveProfiles`. **Creating `application-test.properties` does not automatically activate the `test` profile.** Use `@ActiveProfiles` or another intentional configuration/environment mechanism. Spring TestContext caches contexts; property configuration and active profiles are part of context identity.

### 11.3. Conditionally enabling a single scheduled bean

If only one job needs to be disabled:

```java
@Component
@ConditionalOnProperty(
        name = "app.jobs.cleanup.enabled",
        havingValue = "true",
        matchIfMissing = true)
class CleanupScheduleAdapter {

    @Scheduled(cron = "${app.jobs.cleanup.cron:0 0 * * * *}")
    void run() {
        // ...
    }
}
```

When the flag is false, the bean does not exist; any classes requiring it by injection will fail. The solution is separating `CleanupService` (business logic) from `CleanupScheduleAdapter` (trigger), and making only the adapter conditional.

### 11.4. `@Profile("!test")`

Configuration:

```java
@Configuration
@Profile("!test")
@EnableScheduling
class ProductionScheduling {
}
```

can suit projects where every test must disable scheduling, but makes it harder to write a scheduler-positive test under the same `test` profile. A property flag is usually more flexible. Never put `@Profile("!test")` on a business service if tests need to call that service.

## 12. Distinguishing Spring scheduling from other background work sources

| Auto-running source | Trigger | Relevant switch |
| --- | --- | --- |
| Spring `@Scheduled` | Scheduled annotation processor | `@EnableScheduling`/cron flag |
| Programmatic `TaskScheduler.schedule` | Code registering `Runnable` | Custom guard/config |
| `@Async` | Proxy async call | `@EnableAsync`/`TaskExecutor` |
| Quartz | Quartz `SchedulerFactoryBean` | `spring.quartz.auto-startup` |
| Spring Batch startup job | `JobLauncherApplicationRunner` | Batch startup config |
| `ApplicationRunner` / `CommandLineRunner` | Spring application lifecycle | Conditional runner |
| `@PostConstruct` | Bean initialization | Conditional bean/callback |
| `ApplicationReadyEvent` | Application event | Conditional listener |
| Kafka/Rabbit listener | Listener containers | Listener auto-startup properties |
| Kubernetes CronJob | External orchestrator | Kubernetes schedule/suspend |

In Spring Boot 3.5, there is a documented property:

```properties
spring.quartz.auto-startup=false
```

It controls the Quartz scheduler, **not** Spring `@Scheduled`. Spring Batch also has its own startup job launching mechanism, independent of the Spring scheduling annotation processor. If an app has multiple trigger mechanisms, map each individually; there is no single magic property that stops every kind of background job.

### 12.1. `@PostConstruct` and `ApplicationRunner` are not disabled

If a scheduled bean has `@PostConstruct` calling a business method, it still runs as soon as the bean initializes even if cron is `-`. Likewise, `ApplicationRunner` can execute business logic when the Spring application becomes ready.

So when a side effect occurs in a test despite disabling the scheduler, inspect the call site/stack trace and lifecycle callbacks. Do not immediately conclude the disabled cron convention failed.

### 12.2. Multi-instance scheduling

Spring `@Scheduled` is **one schedule per application instance**. If three replicas all enable the scheduler, all three can run the job. If the system must run it once globally, use leader election, distributed locks, idempotency, or a centralized scheduler. A local test with one context does not prove cluster uniqueness.

## 13. Stronger verification methods than sleeping

### 13.1. Checking processor absence

```java
assertThat(context.getBeansOfType(
        ScheduledAnnotationBeanPostProcessor.class))
        .isEmpty();
```

Stronger than `Thread.sleep(50)` followed by asserting the counter is still zero, because an active task might simply not have reached its first tick within 50ms.

### 13.2. Checking registered tasks

```java
assertThat(processor.getScheduledTasks()).isNotEmpty();
```

Used for scheduler-on contexts. In the demo cron-off context with only one scheduled method, assert empty. If an app has multiple jobs, verify that the **specific job** is unregistered rather than checking only the aggregate size of all tasks.

### 13.3. Checking execution signals

```java
Integer observed =
        service.awaitRun(Duration.ofSeconds(8));
assertThat(observed).isNotNull();
```

This snippet requires a service with a `BlockingQueue`/latch or test-only observable state. Bounded await returns early on signal and fails with a bound if absent. Do not use a fixed sleep to guess.

### 13.4. Testing calendar/cron separately

You can test `CronExpression.parse` and `next(...)` against a fixed `ZonedDateTime`, rather than waiting for hourly/daily crons in integration tests:

```java
CronExpression cron =
        CronExpression.parse("0 0 9 * * MON-FRI");

ZonedDateTime after =
        ZonedDateTime.of(
                2026, 11, 9, 8, 0, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime next = cron.next(after);
```

This snippet requires imports from `org.springframework.scheduling.support.CronExpression` and `java.time`. Sample data is Monday, 2026-11-09 at 08:00 in `Asia/Ho_Chi_Minh`; cron returns 09:00 (+07:00) on that same day. For DST-observing zones, design tests for skipped or repeated hours.

### 13.5. Context caching

Spring TestContext caches `ApplicationContext` across tests sharing identical configuration. If a scheduler-active context stays in cache, tasks can keep running even after the first class finishes.

- Use distinct test properties for scheduler-on vs off.
- For scheduler-on tests, `@DirtiesContext(AFTER_CLASS)` closes the context promptly.
- Do not overuse `@DirtiesContext` on every class, or the suite slows down.
- Do not expect mutating a static flag in `@BeforeEach` to rebuild an already-cached context.
- If other tests share a DB, scheduler-on contexts must be isolated or stopped before other classes touch the data.
- If running JUnit in parallel, use unique test fixtures and avoid shared mutable state across contexts.

## 14. Common mistakes and diagnostics

### Mistake A — Thinking `spring.task.scheduling.enabled=false` is a built-in universal switch

Spring Boot 3.5 does not document this property as an app-wide toggle to turn off annotation scheduling. Use `@ConditionalOnProperty` on the configuration containing `@EnableScheduling` and assert processor absence.

### Mistake B — Thinking `spring.task.scheduling.pool.size=0` disables schedules

Pool size only tunes the executor, and 0 may be invalid. Do not use it as a feature flag.

### Mistake C — Disabling cron on one job yet the job still runs

Check whether another `@Scheduled(fixedRate...)` exists on the method, or whether `@PostConstruct`/a runner/a controller calls the method directly. Disabling cron does not forbid Java invocation.

### Mistake D — `fixedDelayString="-"` fails context startup

`-` is a sentinel for cron; fixed delay/rate need valid durations. Use conditional registration or bean guards instead.

### Mistake E — Test only asserts `counter=0` after 100ms

The scheduler may simply not have ticked yet, creating a false pass. Assert the absence of the annotation processor or zero task registrations instead of inferring from a short delay.

### Mistake F — Unit test uses `@SpringBootTest` when Spring is unnecessary

Loading the context starts unrelated beans and background processes; pure JUnit + Mockito is usually faster and freer of side effects.

### Mistake G — `@DirtiesContext` sprinkled everywhere

It is slow and does not stop tasks from running while the context is active. Disable registration via config for tests that do not need the scheduler.

### Mistake H — Positive test is flaky on CI

Scheduler ticks are asynchronous; use bounded signals instead of sleep, avoid asserting exact tick counts, and ensure the runner has adequate CPU. If even a generous timeout fails, check logs/config and thread starvation.

### Mistake I — Context-off still has a `TaskScheduler` bean

A `TaskScheduler` bean can come from custom code or auto-config; it is not enough to conclude annotation scheduling is active. Check the post-processor and registered tasks.

### Mistake J — Test rolls back yet the job still mutated the DB

Scheduled threads are outside the test transaction; use a test-only DB or disable the scheduler in unintended suites.

### Mistake K — Spring context cache keeps a job running across classes

Use distinct properties, manage lifecycles, apply `@DirtiesContext` intentionally, and isolate test data.

### Mistake L — Quartz still runs even though Spring cron is disabled

Quartz has its own scheduler and properties; `spring.quartz.auto-startup=false` affects Quartz, not `@Scheduled`.

### Mistake M — Multi-instance jobs run redundantly

Each replica runs its own schedule. Distributed locking/idempotency is an architectural decision, not solved by a single test flag.

## 15. Checklist before merging test changes

- [ ] Does the test target business logic or need a real scheduler?
- [ ] Is `@EnableScheduling` in conditional configuration so it can easily be turned off in tests?
- [ ] Is the custom property actually consumed by `@ConditionalOnProperty`?
- [ ] Is `spring.task.scheduling.pool.size` avoided as a toggle switch?
- [ ] Is `spring.task.scheduling.enabled` not assumed to be a built-in universal flag?
- [ ] Is `-` used only to disable cron, never fixed rate/delay?
- [ ] Are business methods and scheduled adapters cleanly separated?
- [ ] Does the context-off test check for the absence of the scheduled processor?
- [ ] Does the context cron-off test verify the specific trigger is not registered?
- [ ] Does the context-on test verify registered tasks and bounded execution?
- [ ] Are scheduler-on test contexts closed after the class if cached background jobs pose a risk?
- [ ] Are test profiles and property precedence clearly defined?
- [ ] Are production DBs/APIs/emails/queues safe from background tasks in tests?
- [ ] Is test-thread rollback not mistaken for scheduler-thread rollback?
- [ ] Are Quartz, Batch, runners, and message listeners governed by their own controls?
- [ ] When deploying multiple replicas, are idempotency/coordination handled where business requires?
- [ ] Does CI avoid silently skipping scheduler-positive tests or hiding failures behind fixed sleeps?

## 16. Practice exercises

**Exercise 1:** Run `SchedulingOffContextTest` with a one-second cron while the flag is off. Explain why processor absence is more reliable than sleeping a few milliseconds.

**Exercise 2:** Run `CronOffContextTest`. Add a second cron job to see that disabling one job's cron does not stop the processor from handling other jobs.

**Exercise 3:** Run `SchedulingOnContextTest`, change cron from every second to every two seconds. Adjust the bounded timeout and explain why you should not assert an exact number of runs.

**Exercise 4:** Move `@EnableScheduling` onto the main application root while keeping the flag false and observe how context-off assertions can fail. Refactor back to proper conditional configuration.

**Exercise 5:** Try setting `fixedDelayString="-"`, observe the startup failure, and propose a better way to disable the schedule.

**Exercise 6:** Replace `BatchService` with a test-only DB repository, let the background thread write, and demonstrate that `@Transactional` on the JUnit test thread does not cover that transaction.

**Exercise 7:** Boot two enabled Spring application contexts simultaneously and discuss duplicate scheduling, distributed locks, and idempotency.

**Exercise 8:** Compare Quartz's `spring.quartz.auto-startup=false` with the Spring annotation scheduling flag; classify the true trigger source before applying a property.

## 17. Self-check questions

**1.** With only `@Scheduled`, does a method tick automatically? — No under regular annotation scheduling; the processor must be enabled.

**2.** Does `spring.task.scheduling.pool.size=1` disable scheduling? — No.

**3.** What is the value of `CRON_DISABLED`? — `-`, used solely to disable cron triggers.

**4.** Can `fixedDelayString="-"` disable fixed delay? — No, that is not a valid duration for that mechanism.

**5.** Why separate the service from the scheduled adapter? — To unit-test business logic without clocks and conditionally toggle triggers.

**6.** Why doesn't a scheduler thread roll back with a JUnit test transaction? — Because it normally runs on a different thread/transaction.

**7.** Does `@DirtiesContext` disable scheduling from startup? — No.

**8.** Does disabling Spring `@Scheduled` disable Quartz? — No.

**9.** Why do positive tests use `BlockingQueue` instead of sleep? — To capture the exact completion signal with a bounded timeout.

**10.** Do three replicas mean `@Scheduled` runs once cluster-wide? — No; each JVM registers its own trigger.

## 18. Official documentation

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): annotation scheduling, cron, fixed rate/delay, `TaskScheduler`.
- [Spring Framework — Scheduled annotation](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html): `CRON_DISABLED`.
- [Spring Framework — ScheduledTaskRegistrar](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/config/ScheduledTaskRegistrar.html): task registration and `-`.
- [Spring Framework — ScheduledAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html): scanning and registering `@Scheduled` methods.
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html): auto-configured schedulers and pool size.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): scheduling/quartz properties.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, profiles, properties, context caching.
- [Spring Boot 3.5 — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): conditional configuration.
- [Spring Framework — CronExpression](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronExpression.html): computing next cron occurrences.

**Conclusion:** To prevent `@Scheduled` from running automatically on Spring test context startup, control **annotation registration before refresh**, instead of waiting for test methods to start and trying to stop them afterward. Put `@EnableScheduling` in conditional configuration, disable individual crons with `-`, and separate business services from scheduler adapters. Tests should prove both off/on branches using structural assertions and bounded execution signals, paired with lifecycle cleanup and test-only dependencies to avoid unintended side effects.