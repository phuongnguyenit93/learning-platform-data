# @ConditionalOnThreading: Configuring Beans According to the Supported Threading Model

## 1. Objectives and Context

Starting from **Spring Boot 3.2.0**, Spring Boot provides the `@ConditionalOnThreading` annotation so an auto-configuration only registers components matching **the active threading model**: `Threading.PLATFORM` or `Threading.VIRTUAL`. This is a type of *environment condition*: it relies on JVM capabilities and the application's environment configuration when Spring creates bean definitions, rather than checking which thread happens to execute an arbitrary method.

A practical example: a starter needs to configure a different `ExecutorService` when the application uses platform threads versus virtual threads (Project Loom). If both executors were registered unconditionally, the application would have duplicate beans for the same role and it would be ambiguous which one gets injected. `@ConditionalOnThreading` lets you put the two configurations into mutually exclusive branches.

**Two key conclusions:**

1. `Threading.VIRTUAL` is considered active only when the application is running on **Java 21 or newer** *and* `spring.threads.virtual.enabled=true` is configured. Having Java 21 alone without enabling the property is not enough.
2. `Threading.PLATFORM` is active when virtual threads are *not* enabled under the rule above. Thus Java 17 can still run Spring Boot 3.2/3.5 with the `PLATFORM` branch; not every application is forced onto Java 21 just because the enum API exists.

The annotation name, enum, and conditions mentioned above must be read against the **Spring Boot version** in use; the API first appeared in 3.2.0 and does not exist in 3.1 or earlier.

## 2. API and Declaration Syntax

In **Spring Boot 3.2–3.5**, import:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
```

Two common places to put the condition:

```java
// Placed on a @Bean method:
@Bean
@ConditionalOnThreading(Threading.VIRTUAL)
MyVirtualComponent virtualComponent() {
    return new MyVirtualComponent();
}
```

```java
// Placed on a configuration class:
@Configuration(proxyBeanMethods = false)
@ConditionalOnThreading(Threading.PLATFORM)
class PlatformOnlyConfiguration {
    // @Beans inside are only evaluated when PLATFORM is active
}
```

The two snippets above are **illustrative code fragments**, compilable only when `MyVirtualComponent` is declared, `@Bean`/`@Configuration` are imported, and they are placed inside a valid Spring configuration. A complete runnable example is in section 5.

This annotation has **one required attribute**, `Threading value()`. The two supported enum values are `Threading.PLATFORM` and `Threading.VIRTUAL`; there is no `Threading.AUTO` or `Threading.BOTH`. Behind the annotation is `OnThreadingCondition`, which evaluates the requested threading enum.

**Note on API change in Spring Boot 4.0:** `ConditionalOnThreading` stays in `org.springframework.boot.autoconfigure.condition`, while the `Threading` enum moves to **`org.springframework.boot.thread.Threading`**. When upgrading, update this import; do not copy an import from a Spring Boot 3.5 example into a Boot 4.0 project and conclude the annotation was removed.

## 3. How PLATFORM vs. VIRTUAL Is Decided

The background information deciding the condition is:

- **Running JVM version**: virtual threads are officially supported by Java starting in Java 21.
- **Configuration property**: `spring.threads.virtual.enabled`, defaulting to `false`.
- **Requested enum**: the value inside `@ConditionalOnThreading(...)`.

Table for Spring Boot 3.2+:

| JVM running application | `spring.threads.virtual.enabled` | `Threading.VIRTUAL` | `Threading.PLATFORM` |
| --- | --- | --- | --- |
| Java 17 | not set | Does not match | Matches |
| Java 17 | `false` | Does not match | Matches |
| Java 17 | `true` | Does not match | Matches |
| Java 21+ | not set | Does not match | Matches |
| Java 21+ | `false` | Does not match | Matches |
| Java 21+ | `true` | Matches | Does not match |

The "Java 17, property true" row shows why you should not replace `@ConditionalOnThreading(Threading.VIRTUAL)` simply with `@ConditionalOnProperty(name="spring.threads.virtual.enabled", havingValue="true")`: the property condition only reads key/value and **does not verify the JVM's virtual threading capability**. When you need to check the active threading model, use the dedicated condition.

The Spring Boot API also provides `Threading.VIRTUAL.isActive(environment)` and `Threading.PLATFORM.isActive(environment)` to evaluate the threading model status from `Environment` with the same semantics. However, when deciding whether to register a bean, using the annotation expresses intent more clearly.

### Distinguishing three questions

1. **Which configuration is activated?** `@ConditionalOnThreading(Threading.VIRTUAL)` answers the question about configuration and JVM capability while Spring builds the context.
2. **Which thread type is an executor bean using?** Inspect the actual bean, such as Spring Boot's auto-configured `AsyncTaskExecutor` or an application-defined `ExecutorService`.
3. **Is the current task running on a virtual thread?** Java 21 has `Thread.currentThread().isVirtual()`, which must be called **inside the running task**. Reading it on a test thread, web request thread, or main thread is no substitute for measuring inside the executor under test.

All three are related yet not identical: you can still manually create a platform-thread executor in an application with virtual threads enabled, or manually use a virtual-thread executor in a context where `Threading.PLATFORM` is still active. The condition does not force every thread in the JVM to switch to the same type.

## 4. Relationship to Spring Boot's Default Configuration

With Java 21+ and:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot can auto-configure built-in components to use virtual threads, depending on the existing bean types:

- When Spring Boot auto-configures an `AsyncTaskExecutor` for task execution and it is not overridden by user configuration, the virtual branch uses a `SimpleAsyncTaskExecutor` configured with virtual threads; the regular branch uses `ThreadPoolTaskExecutor`.
- For task scheduling, the virtual branch uses `SimpleAsyncTaskScheduler` instead of `ThreadPoolTaskScheduler` when the corresponding auto-configuration conditions are satisfied.
- Specific integrations such as certain servlet web servers, `@Async` tasks, or async processing can benefit when they use Boot-configured executors. Do not assume that **every** library, every thread, and every custom executor automatically switches models.

Pool-related properties, such as `spring.task.execution.pool.core-size` or `spring.task.scheduling.pool.size`, **do not apply to executors/schedulers using virtual threads under this mechanism**. Virtual threads are not managed by a conventional fixed-size virtual-thread pool. Do not use pool size as a branching criterion when the virtual model is enabled.

Conversely, `@ConditionalOnThreading` is strictly a **bean-registration condition**: the annotation itself does not create an executor, does not modify application properties, does not enable virtual threads, and does not replace `@EnableAsync`/`@EnableScheduling`.

## 5. Runnable Example with Spring Boot 3.5, Java 21, and Maven

The example uses `@ConditionalOnThreading` to create **exactly one** `ExecutorService`. The `PLATFORM` branch uses a fixed platform-thread pool; the `VIRTUAL` branch uses an executor creating a virtual thread per task. Three tests verify both **bean selection** and **the actual thread type executing tasks**.

This demo uses **Spring Boot 3.5.0** and **JDK 21**. Java 21 is needed to compile `Executors.newVirtualThreadPerTaskExecutor()` and `Thread.isVirtual()`. That is a requirement of **the example**, not meaning every Spring Boot 3.5 application requires Java 21.

Directory structure:

```text
threading-condition-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── ThreadingConditionTest.java
```

### `pom.xml` file

```xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>example</groupId>
    <artifactId>threading-condition-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### `src/test/java/example/ThreadingConditionTest.java` file

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnThreading;
import org.springframework.boot.autoconfigure.thread.Threading;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ThreadingConditionTest {

    @AutoConfiguration
    static class DemoExecutorAutoConfiguration {

        @Bean(destroyMethod = "shutdown")
        @ConditionalOnThreading(Threading.PLATFORM)
        ExecutorService platformExecutor() {
            return Executors.newFixedThreadPool(2);
        }

        @Bean(destroyMethod = "shutdown")
        @ConditionalOnThreading(Threading.VIRTUAL)
        ExecutorService virtualExecutor() {
            return Executors.newVirtualThreadPerTaskExecutor();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DemoExecutorAutoConfiguration.class
                            )
                    );

    @Test
    void missingPropertyUsesPlatformThreads() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ExecutorService.class);
            assertThat(context).hasBean("platformExecutor");
            assertThat(context).doesNotHaveBean("virtualExecutor");

            ExecutorService executor = context.getBean(ExecutorService.class);
            assertThat(isWorkerThreadVirtual(executor)).isFalse();
        });
    }

    @Test
    void explicitFalseUsesPlatformThreads() {
        runner.withPropertyValues("spring.threads.virtual.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ExecutorService.class);
                    assertThat(context).hasBean("platformExecutor");
                    assertThat(context).doesNotHaveBean("virtualExecutor");

                    ExecutorService executor =
                            context.getBean(ExecutorService.class);
                    assertThat(isWorkerThreadVirtual(executor)).isFalse();
                });
    }

    @Test
    void enabledOnJava21UsesVirtualThreads() {
        runner.withPropertyValues("spring.threads.virtual.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ExecutorService.class);
                    assertThat(context).doesNotHaveBean("platformExecutor");
                    assertThat(context).hasBean("virtualExecutor");

                    ExecutorService executor =
                            context.getBean(ExecutorService.class);
                    assertThat(isWorkerThreadVirtual(executor)).isTrue();
                });
    }

    private static boolean isWorkerThreadVirtual(ExecutorService executor) {
        return CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual(),
                executor
        ).join();
    }
}
```

Run in the `threading-condition-demo` directory:

```bash
java -version
mvn test
```

Make sure both `java -version` and the JDK used by Maven are Java 21 or newer. If the environment has multiple JDKs, also check `mvn -version` to confirm Maven's actual Java runtime.

**Expected result:** three JUnit tests pass, Maven ends with `BUILD SUCCESS`. There is no fixed business stdout because the code does not call `System.out.println`. Test reports are in `target/surefire-reports`.

**Why this example is reliable:**

1. The conditions are placed directly on the two `@Bean` methods, each returning `ExecutorService`, yet only one condition is satisfied in a given context.
2. `ApplicationContextRunner` creates isolated contexts. `withPropertyValues(...)` adds properties per scenario without polluting other cases.
3. `hasSingleBean(ExecutorService.class)` verifies both beans are never created simultaneously.
4. `isWorkerThreadVirtual` actually submits a task to **the Spring-registered executor** and queries `Thread.currentThread().isVirtual()` inside the task. It returns `true` only when that task runs on a virtual thread.
5. `destroyMethod = "shutdown"` lets Spring clean up the executor when the test context closes. This avoids leaving behind a fixed pool after tests.

**Distinction from a Java 17 runtime:** you cannot take the file above verbatim and compile it with Java 17, because `newVirtualThreadPerTaskExecutor()` and `Thread.isVirtual()` are Java 21 APIs. To illustrate the `PLATFORM` branch on Java 17, use an example declaring only Java 17 APIs and omit the virtual-thread executor factory method; the `Threading.VIRTUAL` condition itself can still exist in Spring Boot 3.2+.

## 6. How Real Applications Enable or Disable the Model

### 6.1. Enable via application.yml

```yaml
spring:
  threads:
    virtual:
      enabled: true
```

Or in `application.properties`:

```properties
spring.threads.virtual.enabled=true
```

You can override configuration with application launch arguments:

```bash
java -jar app.jar --spring.threads.virtual.enabled=true
```

The `app.jar` example is a hypothetical built Spring Boot application artifact; it is not produced by the test-only project in section 5.

### 6.2. Disable or keep default

```properties
spring.threads.virtual.enabled=false
```

If the property is omitted, the default is `false`; on Java 21, Spring Boot still selects the `PLATFORM` branch. Changing `enabled` from `false` to `true` is a **configuration change at ApplicationContext creation time**. A bean already chosen by the condition in the current context does not morph into another bean when you edit the properties file without re-initializing the context.

### 6.3. Threading model and process liveness

Virtual threads are **daemon threads**. When an application only has daemon threads left, the JVM can exit even if scheduled tasks still need to run. For applications relying primarily on `@Scheduled`, Spring Boot recommends considering:

```properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
```

`spring.main.keep-alive` is a JVM lifecycle decision, **not** a property that helps `@ConditionalOnThreading` match. Do not enable it mechanically if your deployment already manages process lifecycle differently; understand your service's needs before applying it.

## 7. Comparison with Common Conditions

| Annotation / check | Primary check | When to use |
| --- | --- | --- |
| `@ConditionalOnThreading(Threading.VIRTUAL)` | Virtual config is active, including Java 21+ requirement | Register beans by threading model |
| `@ConditionalOnThreading(Threading.PLATFORM)` | Virtual is not active | Fallback configuration for platform threads |
| `@ConditionalOnProperty(name="spring.threads.virtual.enabled", havingValue="true")` | Property value in Environment | When intentionally checking only key/value, not a substitute for JVM capability check |
| `@ConditionalOnJava(JavaVersion.TWENTY_ONE)` | Java runtime meets required threshold | When needing APIs of a specific JVM version, without requiring the virtual property to be enabled |
| `@ConditionalOnBean(ExecutorService.class)` | Bean of the same type is present | When depending on a bean, does not infer what thread type the executor creates |
| `Thread.currentThread().isVirtual()` | Type of the calling thread itself | When inspecting a real task at runtime; not a condition annotation |

**Avoiding auto-configuration bugs:** If you write only `@ConditionalOnJava(JavaVersion.TWENTY_ONE)`, an app running Java 21 without `spring.threads.virtual.enabled` set will still match. If you write only `@ConditionalOnProperty`, Java 17 with the property enabled will still match. `@ConditionalOnThreading` combines both factors accurately for the active threading concept.

## 8. Rules for Designing Auto-Configuration Around Threading Models

1. **Use two mutually exclusive condition branches** for two bean implementations sharing the same responsibility, or use a separate `@Configuration` class per branch.
2. **Distinguish a bean you create from Boot's built-in auto-configuration.** When defining your own `Executor`/`ExecutorService` bean, you can trigger back-off of task execution auto-configuration. If the goal is just to use Boot's default executor, first check whether you even need to define your own bean.
3. **Avoid unintentionally depending on a concrete class.** If the rest of the system only needs `Executor` or `AsyncTaskExecutor`, do not inject `ThreadPoolTaskExecutor` when virtual threads are enabled; in virtual mode, Boot may provide a different implementation.
4. **Treat the condition as a context-creation-time decision.** It does not hot-swap executors at runtime; dynamic reconfiguration requires a dedicated lifecycle management mechanism.
5. **Test the full matrix.** At minimum: property missing, `false`, and `true` on Java 21+; if the project still supports Java 17, test compatible code and fallback handling on that runtime.
6. **Pay attention to real workload characteristics.** Virtual threads are great for I/O-bound tasks under thread-per-request/task models; they do not make CPU execution faster on their own. Blocking/pinning points, connection pools, downstream limits, and backpressure still require control.
7. **Verify resource cleanup.** For self-created executors, use controlled shutdown/close when the context stops; a bean failing the condition will not exist to clean up.
8. **Migrate by version.** When moving from 3.x to 4.0, check the `Threading` enum import, Java version, related auto-configurations, and tests; do not mix Boot 3 code with Boot 4 APIs.

## 9. Common Misconceptions and Fixes

### Mistake 1: “Running Java 21 automatically uses virtual threads”

**No.** Java 21 supports the API, while Spring Boot chooses the virtual model when `spring.threads.virtual.enabled=true`. If the property is missing, `Threading.PLATFORM` is active.

### Mistake 2: “With the property set to true, any JVM uses virtual threads”

**No.** Java 17 does not have standard virtual threads. `Threading.VIRTUAL` requires both JDK 21+ and the property enabled. Always check the actual runtime, not just the config file.

### Mistake 3: “@ConditionalOnThreading automatically converts my thread pool to virtual threads”

**No.** The annotation only decides whether to register a configuration or bean. You still have to create or obtain the right executor. In the example, virtual threads appear because the chosen branch **explicitly calls** `Executors.newVirtualThreadPerTaskExecutor()`.

### Mistake 4: “If I enable virtual threads, every task must have isVirtual() == true”

**No.** Custom executors, libraries not using the default executor, or the main thread can still be platform threads. Check inside the exact task you want to evaluate.

### Mistake 5: “Setting pool size limits virtual threads like a fixed thread pool”

**No.** When Boot selects `SimpleAsyncTaskExecutor` or `SimpleAsyncTaskScheduler` for virtual mode, the corresponding thread pool properties do not behave like they do with `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler`. Use concurrency and resource limits appropriate for your executor, library, and real requirements.

### Mistake 6: “The same Threading import works for all Spring Boot versions”

**No.** Boot 3.2–3.5 uses `org.springframework.boot.autoconfigure.thread.Threading`, whereas Boot 4.0 uses `org.springframework.boot.thread.Threading`. Always cross-check the Javadoc for your exact version.

### Mistake 7: “A bean excluded by the condition can still be injected normally”

**No.** If `@ConditionalOnThreading(Threading.VIRTUAL)` does not match, the bean carrying that condition is not registered via that branch. Any mandatory dependency must have an alternative bean on the platform branch, or the dependency must be made optional.

### Mistake 8: “@ConditionalOnThreading alone is enough to optimize performance”

**No.** Choosing a threading model is a configuration decision, while actual performance depends on workload nature, blocking/pinning sections, bounded resources, and framework support. Measure throughput, latency, and load capacity after deployment.

## 10. Diagnosing Why a Condition Matches or Does Not Match

When an expected bean does not appear, check step by step:

1. **Spring Boot version:** the annotation exists since 3.2; if the build reports `ConditionalOnThreading` cannot be found, check the dependency version.
2. **Correct import:** the `Threading` enum is in different packages between Boot 3.x and 4.x; avoid picking the wrong class via IDE auto-import.
3. **Actual JVM:** `java -version` and `mvn -version` may point to different JDKs. When running in a container or service, check the Java runtime inside the execution environment.
4. **Final property value:** config from profiles, environment variables, CLI arguments, or higher-precedence `PropertySource`s can override default files.
5. **Other conditions on the same bean:** `@ConditionalOnClass`, `@ConditionalOnMissingBean`, auto-configuration ordering, or custom executors can act independently.
6. **Condition report:** run the app with `--debug` to view the condition evaluation report. If using Actuator with the appropriate endpoint enabled, `/actuator/conditions` also shows conditions.
7. **Actual execution path:** use `Thread.currentThread().isVirtual()` inside the task, and inspect the `Executor` type and where it was created; this answers a different question from condition matching.

Diagnostic run example:

```bash
java -jar app.jar --debug --spring.threads.virtual.enabled=true
```

The command above assumes an executable jar application exists. In the test-only project in section 5, use `mvn test` instead.

## 11. Knowledge Self-Check

**Q1.** The application runs on Java 21 without `spring.threads.virtual.enabled`. Which branch matches?  
**Answer:** `Threading.PLATFORM`.

**Q2.** The application runs on Java 17 with `spring.threads.virtual.enabled=true`. Should you use `@ConditionalOnProperty` alone to register a bean calling Java 21 APIs?  
**Answer:** No. Property true does not prove virtual thread APIs are available. `Threading.VIRTUAL` is not active on Java 17; if code must *compile* on Java 17, you still must manage source/bytecode and APIs for the target version.

**Q3.** On Java 21+ with property true, does `@ConditionalOnThreading(Threading.PLATFORM)` match?  
**Answer:** No; the `VIRTUAL` branch is active.

**Q4.** If a bean is only created when `Threading.VIRTUAL` is active, will every method in the application run on a virtual thread?  
**Answer:** No. The annotation controls **bean registration**, not all threads created by the JVM or libraries.

**Q5.** Why should tests submit a task to the executor rather than checking `Thread.currentThread().isVirtual()` directly inside the `@Test` method?  
**Answer:** Because the JUnit test method runs on the test runner's thread, not the thread used by the executor under test.

**Q6.** How must the `Threading` import change when upgrading from Spring Boot 3.5 to 4.0?  
**Answer:** From `org.springframework.boot.autoconfigure.thread.Threading` to `org.springframework.boot.thread.Threading`; the `ConditionalOnThreading` annotation keeps package `org.springframework.boot.autoconfigure.condition`.

## Official Documentation for Reference

- Spring Boot API 3.5 — `@ConditionalOnThreading` (introduced in 3.2.0): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnThreading.html
- Spring Boot API 3.5 — `Threading`, `PLATFORM` and `VIRTUAL` values: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/thread/Threading.html
- Spring Boot 3.5 Reference — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.5 Reference — SpringApplication, Virtual threads: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 4.0 API — `Threading` in new package: https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/thread/Threading.html
- Spring Boot 3.2 Release Notes — Support for Virtual Threads and new annotation: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes

**Takeaway:** `@ConditionalOnThreading` selects configurations according to **Spring Boot's active threading model**, combining JVM support and `spring.threads.virtual.enabled`. It is a tool for registering beans on the right branch; when you need to verify where a real task actually runs, inspect the executor and `Thread.currentThread().isVirtual()` inside the task itself.
