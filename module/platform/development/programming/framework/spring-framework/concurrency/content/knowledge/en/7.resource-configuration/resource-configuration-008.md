# Externalizing Thread Pool Parameters and Rejecting Invalid Values

In Spring Framework, resource configuration for `ThreadPoolTaskExecutor` governs how an application accepts and processes tasks: core workers, worker limits, queue capacity, idle worker retention time, and overload behavior. These values often need to change across development machines, test environments, and production. If they are hardcoded across Java classes, tuning easily drifts and becomes hard to trace.

This lesson covers two related goals:

1. **Externalize configuration**: store values outside executor-creation logic; read them via Spring's configuration mechanisms instead of editing source code whenever tuning resources.
2. **Validate before use**: check types, value ranges, cross-field conditions, and operational sense; if misconfigured, fail clearly at startup instead of running with nonsensical parameters.

The main examples use **Java 17+, Spring Framework 6.x, and Spring Boot 3.x**. `@ConfigurationProperties` belongs to **Spring Boot**, not a feature automatically available in every plain Spring Framework app. A later section includes an `Environment`/`@PropertySource` example for non-Boot Spring Framework.

## 1. Why Externalize Executor Parameters?

Consider hardcoded configuration:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(64);
executor.setKeepAliveSeconds(60);
~~~

This is an **illustrative snippet**, not a complete Spring program. It works, yet you cannot change profiles or deployment settings without modifying bean-creation code. Worse, if each executor reads its own values in inconsistent ways, keeping settings aligned across the app becomes difficult.

A clearer model:

~~~text
application.yml / external file / environment variables / CLI
                         |
                         v
                Spring Environment
                         |
                         v
               Bind to PoolProperties
                         |
                         v
                Validate types + bounds
                         |
           +-------------+-------------+
           |                           |
         valid                      invalid
           |                           |
           v                           v
     Create executor          Fail startup with error
           |
           v
     @Async / TaskExecutor
~~~

**Externalized configuration does not mean hot reload.** In the examples below, values are read when the bean is created. Editing a file or environment variable after the app starts **does not automatically** alter the existing pool. Dynamic updates require a dedicated reload mechanism, re-validation, and knowing which parameters can even change once an executor is initialized.

## 2. Identifying Exactly Which Parameters Need Validation

| Property | Meaning | Example Application Rule |
| --- | --- | --- |
| `corePoolSize` | Core worker count; the pool usually prefers creating workers up to this threshold on incoming tasks | Integer from 1 to 32 |
| `maxPoolSize` | Maximum workers when expansion is needed | Integer from 1 to 64 **and not less than core** |
| `queueCapacity` | Waiting tasks held before scaling additional workers | Integer from 0 to 2,000 |
| `keepAliveSeconds` | Idle time for workers above core before reclamation | Integer from 1 to 600 |
| `threadNamePrefix` | Worker name prefix for readability in thread dumps/logs | Non-empty string, not whitespace-only |
| `RejectedExecutionHandler` | Handling when the pool can no longer accept tasks | Choose an intentional policy; avoid arbitrary class names from strings |

**The thresholds 32, 64, 2,000, and 600 are example policies, not standard Spring or JVM limits.** Real projects choose them from CPU quotas, memory, task speed, dependency latency, and operational requirements.

At least three validation layers should be distinguished:

- **Type validity:** `corePoolSize: abc` cannot convert to an integer; `queueCapacity: 999999999999999999` overflows `int`.
- **Range and relational validity:** `corePoolSize=0` is forbidden by the example policy; `maxPoolSize < corePoolSize` is contradictory; `queueCapacity < 0` is rejected by this app.
- **Operational capacity soundness:** `maxPoolSize=64` may satisfy annotations yet still be far too high for a 10-connection database pool. Static validation **does not replace load testing and capacity planning**.

API-level note: for `ThreadPoolTaskExecutor`, `queueCapacity > 0` creates a `LinkedBlockingQueue`; `0` creates a `SynchronousQueue`, meaning direct handoff with **no task buffering in a queue**. Thus forbidding `queueCapacity=0` is a product decision, not a mandatory Spring rule.

## 3. Recommended Approach in Spring Boot: `@ConfigurationProperties`

`@ConfigurationProperties` groups keys sharing a prefix into a strongly typed Java object. Spring Boot binds data from `Environment` and, when the bean is annotated with `@Validated` and a Bean Validation provider is present, checks `jakarta.validation` constraints.

Advantages over scattered `@Value` fields: one place describes all properties, easy reuse, easy testing of invalid configs, relaxed binding support, and IDE metadata.

### 3.1. Step 1 — Declare `application.yml`

Example `src/main/resources/application.yml`:

~~~yaml
app:
  executor:
    io:
      core-pool-size: ${APP_IO_CORE_POOL_SIZE:4}
      max-pool-size: ${APP_IO_MAX_POOL_SIZE:8}
      queue-capacity: ${APP_IO_QUEUE_CAPACITY:64}
      keep-alive-seconds: ${APP_IO_KEEP_ALIVE_SECONDS:60}
      thread-name-prefix: ${APP_IO_THREAD_NAME_PREFIX:io-}
~~~

The `${ENV_NAME:default}` syntax means: use the variable or property `ENV_NAME` in `Environment` if found, otherwise use the value after `:`. Sample defaults sit in YAML so the app still has explicit settings when running locally.

We intentionally picked explicit environment variable names such as `APP_IO_CORE_POOL_SIZE`. **Do not confuse these placeholder names with Boot's automatic relaxed-binding transformation**. In direct relaxed binding, the canonical key `app.executor.io.core-pool-size` maps to an environment variable by replacing dots with underscores, **removing hyphens**, and uppercasing, i.e., `APP_EXECUTOR_IO_COREPOOLSIZE`. With YAML placeholders, you may use your own naming consistently.

Example run on a Unix shell:

~~~bash
APP_IO_CORE_POOL_SIZE=6 APP_IO_MAX_POOL_SIZE=12 java -jar app.jar
~~~

Or pass Spring Boot properties directly:

~~~bash
java -jar app.jar --app.executor.io.core-pool-size=6 --app.executor.io.max-pool-size=12
~~~

On Windows PowerShell, you can set environment variables for the current shell process via `$env:APP_IO_CORE_POOL_SIZE = "6"` and `$env:APP_IO_MAX_POOL_SIZE = "12"` and then run `java -jar app.jar`.

These command examples assume `app.jar` is a built Spring Boot executable JAR; it is not a fixed JAR filename across all projects.

### 3.2. Step 2 — Ensure a Bean Validation Provider Is on the Classpath

In a Spring Boot 3.x Gradle project, you need a Jakarta Bean Validation implementation, typically provided by the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

This is an **illustrative `build.gradle` snippet**: the project must already use Spring Boot-compatible dependency/version management. If you add `@Validated` without an appropriate validator, never assume `@Min`, `@Max`, and `@AssertTrue` annotations will execute as expected. Verify both the dependency and behavior with an invalid-config test case.

### 3.3. Step 3 — Define a Record Holding Configuration and Validation

File `IoExecutorProperties.java`:

~~~java
package example.concurrency;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "app.executor.io",
        ignoreUnknownFields = false
)
public record IoExecutorProperties(
        @Min(1) @Max(32) int corePoolSize,
        @Min(1) @Max(64) int maxPoolSize,
        @Min(0) @Max(2000) int queueCapacity,
        @Min(1) @Max(600) int keepAliveSeconds,
        @NotBlank String threadNamePrefix
) {
    @AssertTrue(message = "max-pool-size must be >= core-pool-size")
    public boolean isMaxAtLeastCore() {
        return maxPoolSize >= corePoolSize;
    }
}
~~~

This is **Spring Boot 3.x integration code**, requiring Spring Boot and Jakarta Validation dependencies. A Java record enables constructor binding by component without declaring setters. Spring Boot accepts kebab-case keys like `max-pool-size` and maps them to `maxPoolSize`.

What do these constraints do?

- `@Min`/`@Max`: check that bound values fall within the example's supported range. For missing primitive `int` fields, the default `0` is caught by `@Min(1)` on fields requiring at least 1. Better yet, enforce required keys or explicit defaults.
- `@NotBlank`: rejects `null`, empty, or whitespace-only thread name prefixes.
- `@AssertTrue` on Boolean getter `isMaxAtLeastCore()`: enforces **cross-field** conditions that individual field annotations cannot express.
- `ignoreUnknownFields=false`: tells the binder to error if unknown properties appear under the bound prefix, helpful for catching typos. Still test to catch properties placed under the wrong prefix altogether or unread config sources.

`@Validated` comes from Spring (`org.springframework.validation.annotation.Validated`). The constraints come from `jakarta.validation.constraints`, not `javax.validation` from older Spring Boot generations.

In real apps, choose property names and groups by workload such as `io`, `cpu`, `reports`, but only create multiple pools when separate resource boundaries justify it; too many executors make tuning and monitoring harder.

### 3.4. Step 4 — Build `ThreadPoolTaskExecutor` Using Bound Values

File `ExecutorConfiguration.java`:

~~~java
package example.concurrency;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
@EnableConfigurationProperties(IoExecutorProperties.class)
public class ExecutorConfiguration {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor(IoExecutorProperties properties) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(properties.corePoolSize());
        executor.setMaxPoolSize(properties.maxPoolSize());
        executor.setQueueCapacity(properties.queueCapacity());
        executor.setKeepAliveSeconds(properties.keepAliveSeconds());
        executor.setThreadNamePrefix(properties.threadNamePrefix());
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

This is a **Spring bean**, not a standalone program runnable with `javac`. `@EnableConfigurationProperties(IoExecutorProperties.class)` registers the properties record for Boot binding/validation; `@EnableAsync` activates `@Async`. The `ThreadPoolTaskExecutor` bean is managed by Spring, including lifecycle initialization. Hence the example does not call `initialize()` manually inside the factory method.

`AbortPolicy` was chosen deliberately so overload raises an explicit rejection signal. It is **not the only safe policy**; others can be used once you evaluate effects on calling threads, retries, and no-loss guarantees. If the policy must be externalized, bind an **enum with an allowed set of values**, then map that enum to a controlled set of `RejectedExecutionHandler`s; never accept arbitrary class names from config to instantiate via reflection.

### 3.5. Step 5 — Use the Right Executor for `@Async`

File `FileExportService.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class FileExportService {

    @Async("ioExecutor")
    public CompletableFuture<String> export(String fileId) {
        // Illustrative work; real I/O requires timeouts and error handling.
        return CompletableFuture.completedFuture("exported:" + fileId);
    }
}
~~~

Another bean calling `fileExportService.export("file-7")` through the Spring proxy submits work to `ioExecutor`. Parameters were loaded from the properties record when creating the executor. Self-invocation inside the same instance (`this.export(...)`) normally **bypasses the proxy** in default `@Async` mode, failing to dispatch to the expected pool.

If the executor is full, an error can occur immediately at **submission**; if the task is accepted yet fails during execution, the corresponding result may complete exceptionally. Callers must distinguish both failure modes. Never assume returning `CompletableFuture` guarantees task submission always succeeds.

## 4. When Does Validation Run?

With the design in Section 3, the usual sequence is:

~~~text
Start ApplicationContext
          |
      Collect config
          |
      Bind typed values
          |
      Run Bean Validation
          |
  +-------+-------------+
  |                     |
 Valid                Invalid / unbindable
  |                     |
  v                     v
 Create executor bean  Startup fails
  |
  v
 Start accepting tasks
~~~

With `max-pool-size: 3` and `core-pool-size: 8`, each field individually lies in range, yet **the relationship between them is invalid**; `@AssertTrue` reports which condition failed. If `core-pool-size` is set to `"many"`, binding to `int` fails at the type-conversion layer **before or during binding**, without even reaching `@Min`.

Exact error messages, exception classes, and detail ordering vary by Boot version, Validation provider, and bean initialization path. **Never catch/swallow validation errors and substitute random numbers** just to force startup. With invalid resource settings, failing fast prevents hard-to-diagnose runtime incidents.

### 4.1. Valid and Invalid Case Matrix

Assume `queueCapacity=64`, `keepAliveSeconds=60`, `threadNamePrefix=io-` unless noted otherwise:

| Input | Expected | Reason |
| --- | --- | --- |
| core=4, max=8 | **PASS** | Both within bounds and max ≥ core |
| core=0, max=8 | **FAIL** | Violates `@Min(1)` on core |
| core=12, max=8 | **FAIL** | Violates `max ≥ core` |
| core=4, max=0 | **FAIL** | `@Min(1)` on max; also max < core |
| queue=-1 | **FAIL** | Example policy requires queue ≥ 0 |
| queue=0 | **PASS** | Direct handoff configuration using `SynchronousQueue` |
| queue=5000 | **FAIL** | Exceeds example's `@Max(2000)` |
| keep-alive-seconds=0 | **FAIL** | Example requires ≥ 1 second |
| thread-name-prefix whitespace only | **FAIL** | `@NotBlank` |
| core=abc | **FAIL** | Cannot bind string to `int` |
| core omitted in all sources and no default | **FAIL in this model** | Primitive `int` receives 0, violating `@Min(1)` |

Understand the no-default case properly: if `application.yml` still carries defaults from Section 3, **omitting an environment variable** causes no error because the binder reads the file default. To require an explicit deployment value, omit the default in config, use a type that clearly represents absence with matching validation, and test startup without the env var.

### 4.2. Cross-Field Validation with `@AssertTrue` and Alternatives

Per-field annotations only verify each value individually stays in range. They do not automatically understand `maxPoolSize ≥ corePoolSize`. For simple relationships, an `@AssertTrue` boolean getter `isMaxAtLeastCore()` is readable enough.

When multiple complex rules exist — such as a combined budget across pools or environment-dependent constraints — use a class-level custom constraint/validator or a centralized validation method before creating the bean. The goal is errors **naming the exact parameter and violated condition**, rather than scattered unmaintainable checks.

Do not hardcode every operational rule into immutable `@Max` bounds: workload thresholds can evolve with larger CPU quotas, DB capacity, and SLAs. Keep safety guardrails in properties while choosing concrete production values from measurements.

## 5. Standalone Java 17: Validating Configuration Without Booting Spring

The following example simulates the **parse and consistency-check steps** using a Java 17 record. It does not replace Spring Boot Bean Validation, yet shows why both type checking and cross-parameter validation are needed.

Create `PoolSettingsValidationDemo.java`:

~~~java
public class PoolSettingsValidationDemo {
    record PoolSettings(int core, int max, int queue) {
        public PoolSettings {
            if (core < 1) {
                throw new IllegalArgumentException("core must be >= 1");
            }
            if (max < core) {
                throw new IllegalArgumentException("max must be >= core");
            }
            if (queue < 0) {
                throw new IllegalArgumentException("queue must be >= 0");
            }
        }
    }

    static void check(String core, String max, String queue) {
        try {
            PoolSettings settings = new PoolSettings(
                    Integer.parseInt(core),
                    Integer.parseInt(max),
                    Integer.parseInt(queue));

            System.out.printf("VALID core=%d max=%d queue=%d%n",
                    settings.core(), settings.max(), settings.queue());
        } catch (NumberFormatException e) {
            System.out.println("INVALID: value must be integer");
        } catch (IllegalArgumentException e) {
            System.out.println("INVALID: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        check("4", "8", "64");
        check("0", "8", "64");
        check("12", "8", "64");
        check("4", "8", "-1");
        check("x", "8", "64");
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 PoolSettingsValidationDemo.java
java PoolSettingsValidationDemo
~~~

Deterministic output:

~~~text
VALID core=4 max=8 queue=64
INVALID: core must be >= 1
INVALID: max must be >= core
INVALID: queue must be >= 0
INVALID: value must be integer
~~~

Explanation: `Integer.parseInt(...)` catches type errors first; the `record` compact constructor checks bounds and relationships before producing a valid configuration object. `NumberFormatException` is a subclass of `IllegalArgumentException`, so its catch block must come **before** the broader catch block. All cases are verified on any JDK supporting records; the Spring approach in Section 3 is conceptually equivalent while using the binder and Jakarta Bean Validation instead of manual string parsing.

If an input like `" 4 "` is unnormalized, plain Java `Integer.parseInt` throws instead of trimming. Spring Boot's binder has its own conversion rules, so do not extrapolate plain Java whitespace behavior to all property sources.

## 6. Plain Spring Framework: Reading `Environment` and Manual Validation

Without Spring Boot, you **do not automatically get `application.yml` auto-loading and `@ConfigurationProperties` binding as in Section 3**. Core Spring Framework still offers `Environment`, `@PropertySource`, `@Value`, and validation facilities, though the application must configure property sources and validation steps itself.

Create `executor.properties` on the classpath:

~~~properties
app.executor.core=4
app.executor.max=8
app.executor.queue=64
app.executor.keep-alive=60
~~~

Example Spring Framework integration class:

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@PropertySource("classpath:executor.properties")
public class PlainSpringExecutorConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor(Environment environment) {
        int core = environment.getRequiredProperty(
                "app.executor.core", Integer.class);
        int max = environment.getRequiredProperty(
                "app.executor.max", Integer.class);
        int queue = environment.getRequiredProperty(
                "app.executor.queue", Integer.class);
        int keepAlive = environment.getRequiredProperty(
                "app.executor.keep-alive", Integer.class);

        if (core < 1 || max < core || queue < 0 || keepAlive < 1) {
            throw new IllegalArgumentException(
                    "Invalid executor config: require core >= 1, " +
                    "max >= core, queue >= 0, keepAlive >= 1");
        }

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(core);
        executor.setMaxPoolSize(max);
        executor.setQueueCapacity(queue);
        executor.setKeepAliveSeconds(keepAlive);
        executor.setThreadNamePrefix("io-");
        return executor;
    }
}
~~~

This is **integration code**: it requires a Spring Context, config registration/scanning, and the `executor.properties` resource; it does not run with `javac` alone. If a key is missing, `getRequiredProperty` fails; if conversion to integer fails, conversion throws; if relationships fail, the `@Bean` method throws `IllegalArgumentException`, preventing bean creation.

The example highlights two layers:

- **Core Spring Framework:** provides property source and environment abstractions so the app reads values, builds beans, and decides how to validate.
- **Spring Boot:** builds on those foundations with config data, relaxed binding, `@ConfigurationProperties`, integrated validation, and override precedence to standardize the workflow.

Not every Spring Framework application uses Spring Boot. Documentation, code, and configuration styles should clearly state which layer they rely on.

## 7. Property Source Precedence and Profiles

### 7.1. Configuration Sources Can Override Each Other

In Spring Boot, `application.yml` inside the JAR, `application-{profile}.yml`, external config files, environment variables, system properties, and command-line arguments can all supply values. Boot defines a **PropertySource precedence order**, so two sources declaring the same key do not both take effect.

Before concluding the app "ignored my config," verify the **final effective value** and which source won. For instance, CLI `--app.executor.io.max-pool-size=12` overrides `application.yml` under Boot's default order. Do not assume one universal precedence order across projects that customize `PropertySources` or disable command-line properties.

### 7.2. Profiles Change Values, Not Validation Rules

Example profile file `application-prod.yml`:

~~~yaml
app:
  executor:
    io:
      core-pool-size: 8
      max-pool-size: 16
      queue-capacity: 128
~~~

Other keys still fall back to the base configuration unless overridden by a higher-precedence source. `IoExecutorProperties` constraints **still apply** after binding the final values; profiles are never a reason to skip validation.

Ensure profile activation via `spring.profiles.active=prod`, environment variables, or CLI flags matches your deployment mechanism; never assume `application-prod.yml` is loaded unless the `prod` profile is actually active.

### 7.3. Keep Configuration Observable Without Leaking Secrets

Core/max/queue parameters are normally non-sensitive, so you can log **validated effective values** at an appropriate level or expose config gauges. However, never dump the entire `Environment`, as the same sources can hold tokens, passwords, or credentials. When exposing Actuator `/actuator/configprops`, restrict access and use built-in sanitization; it helps inspect bean config without replacing purposeful logging and metrics.

## 8. Practical Testing: Invalid Configs Must Fail Normal Startup

A valuable test is running isolated config scenarios (locally or via integration tests) and inspecting the Spring `ApplicationContext`.

| Scenario | Sample Input | Expectation |
| --- | --- | --- |
| Valid | `core=4,max=8,queue=64` | Context creates `ioExecutor` with matching settings |
| Wrong type | `core=abc` | Binding fails; executor does not initialize normally |
| Out of range | `queue=-1` | Bean Validation rejects |
| Invalid relation | `core=12,max=8` | `isMaxAtLeastCore()` returns false; validation rejects |
| Blank prefix | `thread-name-prefix="   "` | `@NotBlank` rejects |
| Boundary values | `queue=0`, `core=max=1` | Valid per constraints; queue is `SynchronousQueue` |
| Upper bound | `max=65` | `@Max(64)` constraint rejects |
| Typo under prefix | `max-pool-szie=8` | With `ignoreUnknownFields=false`, expected bind failure for unknown property; verify the source containing the key was loaded |

Use dedicated env vars/CLI overrides per case rather than altering production config just to test failure. In integration tests, ensure you do not reuse a singleton executor from an already-succeeded context, which would hide a fresh binding pass. For pure validation unit tests, you can invoke a `Validator` via `validate(properties)`, yet real startup tests also exercise source loading, type conversion, bean registration, and lifecycle.

**Do not write a test that only asserts `isMaxAtLeastCore()` returns false** and conclude Boot validation works end-to-end; test that an actually invalid config causes context startup to fail.

## 9. Common Mistakes and Fixes

### 9.1. Externalizing Config While Leaving Conflicting Hardcodes

If YAML defines `core=4` while the `@Bean` method still calls `setCorePoolSize(16)` after reading properties, external config is no longer authoritative. Use only the final bound/validated values. If fallbacks are needed, put them in the config layer or documented defaults rather than conflicting layers.

### 9.2. Using `@Value` for Many Fields and Forgetting Cross-Field Checks

`@Value("${app.executor.io.core-pool-size}")` fits injecting a single scalar, yet does not enforce `max >= core` or represent cohesive groups cleanly. For a group of pool settings, `@ConfigurationProperties` is usually clearer. If `@Value` is mandatory, add a centralized validation step before building the executor.

### 9.3. Validating Positive Numbers Only, Missing `max >= core`

`@Min(1)` on both core and max **does not prove max is at least core**. `core=16,max=8` passes individual field checks if within bounds. A cross-field constraint or factory-method check is essential.

### 9.4. Mistaking `queue=0` for an Error

`queueCapacity=0` is valid in Spring's `ThreadPoolTaskExecutor`: `SynchronousQueue` holds no waiting tasks, forcing direct handoff/worker scaling up to max and rejecting when saturated. If a workload should not do that, app policy can forbid it via `@Min(1)`, while documenting that choice explicitly.

### 9.5. Assuming Raising `maxPoolSize` Immediately Increases Concurrency

After reaching core, `ThreadPoolExecutor` normally prefers the queue. While the queue still accepts tasks, the pool **has no need** to spawn workers up to max. You may observe long queues with `poolSize` stuck at core despite a high max. Setting a high max with a nearly unbounded queue will not produce expected concurrency.

### 9.6. Constraints Too Loose or Too Tight

Zero validation lets bad values reach the executor/JVM with cryptic errors. Conversely, a 32-thread cap may suit one workload yet be too low for another blocking I/O workload. Record bounds should be deliberate: block clearly dangerous values while relying on load tests and downstream limits for capacity tuning.

### 9.7. Thinking Editing YAML Updates a Running Pool Immediately

While the application is running, `IoExecutorProperties` is already bound and the executor initialized. Although some `ThreadPoolTaskExecutor` setters support runtime updates, the example above **has no hot-reload logic**. Queue type/capacity is decided at initialization and does not auto-change when a file changes. For deploying new config, a controlled restart/rolling rollout is simpler and safer.

### 9.8. Hiding Missing Config Behind Silent Defaults

If production omits a critical key yet a hidden default lets the app boot with `core=1`, problems may surface only under load. Classify which keys may have defaults and which must be provided on deploy. For required keys, make missing config an explicit startup failure via binding/validation.

### 9.9. Confusing Startup Config Errors with Runtime Overload

Wrong types, out-of-range values, and broken relations are **configuration errors**; catch them before serving traffic. Pool saturation/rejections happen **at runtime even with valid configs** when load exceeds capacity. Monitor `getActiveCount()`, `getPoolSize()`, queue depth, task duration, rejections, timeouts, and downstream resources. Annotation validation cannot guarantee zero rejections under load.

## 10. Process for Promoting Executor Configuration to Production

1. **Identify the workload:** CPU-bound or blocking I/O; measure tasks/second, worker hold time, queue latency, CPU, memory, and database/network limits.
2. **Choose property groups:** standardize prefixes, env var names, defaults, units, and rationale per value. For durations, prefer explicit duration formats in new schemas; here `keepAliveSeconds` matches Spring's API.
3. **Bind once into typed objects:** Boot uses `@ConfigurationProperties` records; plain Framework uses `Environment` plus app-managed mapping/validation.
4. **Validate at two levels:** per-field and cross-field; handle missing/unknown/non-integer values; fail immediately at bootstrap.
5. **Route to the right bean:** `@Async("ioExecutor")` or qualified injection so each workload uses its configured pool.
6. **Verify in deployment environments:** run invalid-config cases in test/staging to confirm startup fails; verify profile/env/CLI overrides behave as intended.
7. **Deploy and observe:** log non-sensitive effective config, monitor active workers, queues, rejections, p95/p99, and downstreams.
8. **Change under control:** adjust core/max/queue only with evidence; verify post-rollout metrics and avoid changing many variables at once.

## 11. Self-Check Questions

**1. Why does `@ConfigurationProperties` fit executor parameter groups better than scattered `@Value` fields?**

Because it groups parameters into a typed object supporting relaxed binding, metadata, injection, and centralized validation—especially giving a clear place for cross-field rules.

**2. Is `@Min(1)` on `corePoolSize` and `maxPoolSize` enough?**

No. `core=12,max=8` still satisfies `@Min(1)` on each field yet breaks their relationship. You need `@AssertTrue`, a custom constraint, or validation at executor creation.

**3. Will Spring Boot automatically enforce `@Validated` on a properties record without a Bean Validation provider?**

Do not assume so. A compatible Jakarta Bean Validation implementation is required—typically via `spring-boot-starter-validation`—and should be verified with an invalid-config startup test.

**4. Is `queueCapacity=0` always invalid?**

No. It selects `SynchronousQueue` in `ThreadPoolTaskExecutor`. Suitability depends on admission strategy and load; this lesson's example allows 0 and forbids negative numbers.

**5. Why might a configuration with max=64 still stay at only 4 workers?**

Because after reaching core, tasks typically enter the queue first. As long as the queue accepts them, the executor does not grow toward max. Inspect core, queue, `activeCount`, and downstream state together.

**6. If an environment variable changes while the JVM is running, will the executor pick up the new number?**

Not automatically in this design. Config is bound at context startup; runtime changes require an explicit thread-safe reload mechanism or a rolling restart.

**7. If validation PASSES, can you skip monitoring rejections and latency?**

No. Validation only blocks configs violating declared rules. A valid pool can still overload, block on I/O, exhaust connections, or build huge queue waits.

## 12. Official References

- Spring Boot 3.3 — Externalized Configuration, property sources, relaxed binding, and `@ConfigurationProperties` Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework 6.x — `ThreadPoolTaskExecutor` API (core/max/queue/keep-alive): https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 — `ThreadPoolExecutor` and `RejectedExecutionHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Jakarta Bean Validation — javax/jakarta constraints (`@Min`, `@Max`, `@NotBlank`, `@AssertTrue`): https://jakarta.ee/specifications/bean-validation/
