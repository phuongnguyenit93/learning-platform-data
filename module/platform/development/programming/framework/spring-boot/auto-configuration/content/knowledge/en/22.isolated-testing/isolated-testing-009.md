# Testing Startup Failures and Root Causes for Invalid Configurations

## 1. Goal: finding why Spring Boot fails to start

A Spring Boot application may halt before accepting requests due to invalid configuration, missing dependencies, beans failing to instantiate, auto-configuration conditions mismatched with the dependency graph, or the embedded server failing to start. Logs typically show multiple nested exception layers. The outermost exception indicates **which phase failed**, while inner causes usually point to **what triggered the error**.

For example:

- `ConfigurationPropertiesBindException` may wrap a property binding or validation error.
- `UnsatisfiedDependencyException` usually shows which bean could not be injected; a deeper cause may be `NoSuchBeanDefinitionException` or a failing bean dependency.
- `BeanCreationException` often wraps an exception thrown by a constructor, factory method, `@PostConstruct`, or bean initialization.
- `ApplicationContextException` may wrap a web server startup failure.
- `NoSuchMethodError` or `NoClassDefFoundError` usually points to classpath/version incompatibilities.
- `PortInUseException` or socket bind failures can indicate the port is occupied by another process.

Goals of this lesson:

1. Distinguish startup phases and their corresponding error groups.
2. Read the exception chain, identify the root cause, and preserve context from outer wrapper exceptions.
3. Use startup logs, `--debug`, and `ConditionEvaluationReport` for their proper purposes.
4. Validate configuration using `@ConfigurationProperties`, validation, and `ApplicationContextRunner`.
5. Build a `FailureAnalyzer` to turn a specific error into a descriptive message with concrete remediation steps.
6. Write tests proving the context starts successfully or fails for the exact expected cause.

Examples use **Java 17+ and Spring Boot 3.3.13**.

## 2. Which phases does startup go through?

Not every error occurring during `SpringApplication.run` shares the same origin. Identifying the phase helps select the right diagnostic tool:

| Phase | What Spring Boot performs | Common errors |
|---|---|---|
| Initial config reading | Reads config data, profiles, imports, environment, and command-line args | Malformed YAML, missing required config file, unresolved placeholders |
| Preparing `Environment` | Loads and merges property sources | Wrong key name, values overridden by profiles or environment variables |
| Loading configuration and auto-configuration | Reads configuration classes, evaluates conditions, registers bean definitions | Classpath conditions not matching, excluded auto-configurations, conditional beans not registered |
| Refreshing `ApplicationContext` | Instantiates singletons, injects dependencies, binds `@ConfigurationProperties`, runs lifecycle callbacks | Binding/validation failures, missing beans, circular dependencies, constructor or factory method exceptions |
| Starting web server | Creates and starts embedded server | Port already in use, invalid TLS/certificate, connector bind failure |
| Running application/command-line runners | Invokes `ApplicationRunner` and `CommandLineRunner` | Startup tasks, migrations, or config checks throwing exceptions |
| Completing startup | Publishes ready event and transitions readiness state | An error before runners finish can leave the application unready |

Some errors happen **before `ApplicationContext` even exists**, such as unreadable config data. In that case, you cannot expect a bean inside the context to handle the error.

Some errors happen during context refresh, such as a missing bean dependency. The error may be wrapped in several exception layers.

Some errors occur after context refresh but before `SpringApplication.run` finishes, such as an `ApplicationRunner` throwing an exception. Consequently, logs may show that the context initialized while the application still reports a startup failure.

## 3. Distinguishing outer exceptions from root causes

### 3.1. Reading from outside in

For example, a bean fails to instantiate:

~~~text
BeanCreationException: Error creating bean with name 'workerPool'
    at ...
Caused by: InvalidPoolConfigurationException:
    app.pool.threads=128 exceeds supported maximum 64
    at ...
~~~

Read in two layers:

- `BeanCreationException` tells you bean `workerPool` failed during creation.
- `InvalidPoolConfigurationException` pinpoints the specific configuration condition that halted the factory method.

If you only look at `BeanCreationException` without finding the inner cause, you do not know whether to change a property, a dependency, or the bean creation code.

Another example:

~~~text
UnsatisfiedDependencyException:
    Error creating bean with name 'auditStartupCheck'
Caused by: NoSuchBeanDefinitionException:
    No qualifying bean of type 'AuditClient' available
~~~

Here, bean `auditStartupCheck` requires `AuditClient`, yet the context has no matching bean. Perhaps a `@ConditionalOnProperty` did not match so `AuditClient` was never registered. The deepest exception only states the bean is missing; you must inspect the condition report and effective properties to find why.

### 3.2. Root cause does not replace context

When investigating, record all of:

- Outermost exception and the bean/resource being processed.
- The cause chain, especially the deepest meaningful exception.
- Message, property key, bean name, profile, and involved classes.
- The first stack frame belonging to your application or library code.
- Any suppressed exceptions if present; composite failures can carry multiple secondary causes.

The last line of a stack trace is not always the full answer. The root cause may be an OS or low-level library error, while the outer wrapper reveals which request, bean, or configuration triggered it.

### 3.3. Quick identification table

| Common exception | What it suggests | What to check next |
|---|---|---|
| `ConfigDataLocationNotFoundException` | Required config location/import does not exist | Paths, filenames, `optional:`, and deployment environment |
| `ConfigurationPropertiesBindException` | Failed to bind a properties bean | Property prefix, data types, conversion, and validation |
| `BindValidationException` | Values bound but failed validation | Constraints, actual values, and property source |
| `UnsatisfiedDependencyException` | Could not inject dependency for a bean | Which bean needs the dependency, conditions, and bean definitions |
| `NoSuchBeanDefinitionException` | No matching bean in context | Component scan, auto-configuration, conditions, profiles, and qualifiers |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist without disambiguation | `@Primary`, `@Qualifier`, and bean design |
| `BeanCreationException` | Bean failed during creation/initialization | Read cause, constructor, factory method, and lifecycle callbacks |
| `BeanCurrentlyInCreationException` | Possible circular dependency | Dependency graph and cyclic design |
| `NoClassDefFoundError` | Required class could not be loaded at runtime | Runtime classpath, scopes, packaging, and classloaders |
| `NoSuchMethodError` | Loaded class lacks a method called by bytecode | Dependency version conflicts and dependency tree |
| `PortInUseException` / bind exception | Server failed to bind address/port | Process holding port, `server.port`, `server.address`, and container mappings |
| Exception from `ApplicationRunner` | Context may have refreshed, yet startup is incomplete | Startup tasks, input data, and dependencies invoked by the runner |

This table is a starting guide. Always confirm via the cause chain and runtime state before changing configurations.

## 4. Reading logs and condition reports properly

### 4.1. Running with `--debug`

With an executable JAR:

~~~bash
java -jar app.jar --debug
~~~

With Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

With Gradle:

~~~bash
./gradlew bootRun --args='--debug'
~~~

`--debug` enables a curated set of Spring Boot diagnostic loggers, including condition evaluation details. It does **not** switch every logger in the application and all libraries to DEBUG.

You can configure specific loggers in `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.context.annotation: DEBUG
~~~

Enable verbose loggers only during investigation when log volume is high. In production environments, avoid writing secrets, tokens, passwords, or personal data to logs.

### 4.2. What is `ConditionEvaluationReport` for?

`ConditionEvaluationReport` records match/no-match results of auto-configuration conditions. The report helps answer:

- Which auto-configurations were applied?
- Which auto-configurations were skipped?
- Which conditions failed to match?
- Was the reason classpath, property, bean, or application type?

For example: `AuditAutoConfiguration#auditClient` did not match because `app.audit.enabled` did not equal `true`. This is evidence of a **bean registration decision**, not a universal root cause for every startup failure.

If no `FailureAnalyzer` handles an exception, Spring Boot can print the condition report when `--debug` is active or when the `ConditionEvaluationReportLoggingListener` logger is at DEBUG level.

### 4.3. When is the condition report insufficient?

The condition report does not replace:

- The cause chain of `BeanCreationException`.
- YAML parsing or config data loading errors.
- Validation details inside `BindValidationException`.
- Classloader or linkage errors like `NoSuchMethodError`.
- Embedded server port bind failures.
- Exceptions thrown by `ApplicationRunner`.

Use the report to understand **why a configuration branch was or was not registered**. Use stack traces, property sources, and component logs to determine **why a specific operation failed**.

If the application has Actuator, the `conditions` endpoint can also expose the condition report as JSON when enabled. This endpoint must be secured because it can reveal classpath and internal configuration details; do not leave it public merely for debugging.

## 5. Checking actual configuration values

### 5.1. Do not only read `application.yml`

Properties can come from many sources: default properties, files inside the JAR, external files, profile-specific configs, config imports, environment variables, system properties, and command-line arguments. Sources have precedence rules; higher-precedence sources override values in YAML.

For example, a file says:

~~~yaml
app:
  pool:
    threads: 8
~~~

Yet the deployment environment sets:

~~~bash
APP_POOL_THREADS=0
~~~

The application can receive `0` instead of `8`. During diagnosis, record the **effective value** and its source, not just file contents.

You can inspect this in a debugger or controlled logging:

~~~java
String threads = environment.getProperty("app.pool.threads");
String activeProfiles = String.join(",", environment.getActiveProfiles());
~~~

Do not dump the entire `Environment` to logs as it may contain secrets. Log only relevant keys, masked values if needed, and the corresponding property source.

### 5.2. Using `@ConfigurationProperties` and validation

For multi-key configurations, use a strongly typed properties class with constraints:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.pool")
@Validated
public class PoolProperties {

    @Min(1)
    private int threads = 8;

    public int getThreads() {
        return threads;
    }

    public void setThreads(int threads) {
        this.threads = threads;
    }
}
~~~

`@Min(1)` requires at least 1 thread. If the property binds to `0`, validation causes context startup to fail. For Jakarta Validation constraints to run, a validation implementation must be on the classpath, typically via `spring-boot-starter-validation`.

Register properties and use them in a bean:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PoolProperties.class)
public class PoolConfiguration {

    @Bean
    WorkerPool workerPool(PoolProperties properties) {
        return new WorkerPool(properties.getThreads());
    }
}
~~~

The example uses `WorkerPool`, an application class whose constructor accepts the thread count. If `app.pool.threads` has the wrong type, the binder reports a conversion/binding error. If the value converts cleanly yet violates a constraint, a validation error appears in the cause chain.

### 5.3. Distinguishing invalid properties from unmatched conditions

Suppose a bean is registered only when:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "app.audit",
    name = "enabled",
    havingValue = "true"
)
AuditClient auditClient() {
    return new AuditClient();
}
~~~

If `app.audit.enabled` is missing or not equal to `true`, `AuditClient` is not registered. An unmatched condition by itself **is not necessarily a startup failure**. The context can still start normally if no bean requires `AuditClient`.

If another bean unconditionally injects `AuditClient`, the context fails with `UnsatisfiedDependencyException` and `NoSuchBeanDefinitionException`. In that case, check the property condition, effective values, `matchIfMissing`, active profiles, and dependent beans.

## 6. `FailureAnalyzer`: turning exceptions into remediation guides

### 6.1. Three components

Spring Boot provides a startup failure analysis mechanism:

- `FailureAnalyzer` receives an exception and returns a `FailureAnalysis`, or `null` if it cannot handle it.
- `FailureAnalysis` holds `description`, `action`, and `cause`.
- `FailureAnalysisReporter` displays the result to the user. The default reporter writes the analysis to logs/console.

An occupied-port error can be formatted cleanly:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:

Embedded servlet container failed to start. Port 8080 was already in use.

Action:

Identify and stop the process that is listening on port 8080
or configure this application to listen on another port.
~~~

This message is more actionable than a long stack trace. It does not auto-fix the configuration; it explains the error and suggests next steps.

### 6.2. When should you write a custom analyzer?

Write a `FailureAnalyzer` when your library/application has a specific exception developers frequently hit and you can provide clear remediation advice. For example:

- A pool configuration limit is exceeded.
- Two mutually exclusive configuration options are set.
- A required file exists but violates an application-specific format.
- An integration requires credentials or an endpoint the application has not supplied.

Do not write an analyzer merely to reword a generic exception. If no more actionable guidance exists, the stack trace and Spring Boot's built-in analyzers may suffice.

### 6.3. Example custom exception

File `src/main/java/com/example/config/InvalidPoolConfigurationException.java`:

~~~java
package com.example.config;

public class InvalidPoolConfigurationException extends RuntimeException {

    private final int requestedThreads;

    public InvalidPoolConfigurationException(int requestedThreads) {
        super("app.pool.threads=" + requestedThreads
                + " exceeds the supported maximum of 64");
        this.requestedThreads = requestedThreads;
    }

    public int getRequestedThreads() {
        return requestedThreads;
    }
}
~~~

The factory method can throw this exception when configuration exceeds operational limits:

~~~java
@Bean
WorkerPool workerPool(PoolProperties properties) {
    int threads = properties.getThreads();

    if (threads > 64) {
        throw new InvalidPoolConfigurationException(threads);
    }

    return new WorkerPool(threads);
}
~~~

This is a configuration error with application-specific semantics. Spring wraps the exception in a bean creation failure, yet an analyzer can locate the specific exception in the cause chain.

### 6.4. Writing `FailureAnalyzer`

File `src/main/java/com/example/config/InvalidPoolConfigurationFailureAnalyzer.java`:

~~~java
package com.example.config;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public class InvalidPoolConfigurationFailureAnalyzer
        extends AbstractFailureAnalyzer<InvalidPoolConfigurationException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            InvalidPoolConfigurationException cause) {

        String description = "The worker pool configuration requests "
                + cause.getRequestedThreads()
                + " threads, but this application supports at most 64.";

        String action = "Set app.pool.threads to a value between 1 and 64, "
                + "then restart the application.";

        return new FailureAnalysis(description, action, cause);
    }
}
~~~

`AbstractFailureAnalyzer<T>` searches the cause chain for an exception of type `T` and calls `analyze(rootFailure, cause)`. If the analyzer cannot handle an exception, the implementation can return `null` so another analyzer gets a chance.

Avoid accessing initializing application beans inside an analyzer. If `Environment` or `BeanFactory` is needed, use the constructor arguments Spring Boot supports for failure analyzers; avoid depending on business beans that have not been created yet.

### 6.5. Registering the analyzer in the artifact

Create the file:

`src/main/resources/META-INF/spring.factories`

Contents:

~~~properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.config.InvalidPoolConfigurationFailureAnalyzer
~~~

Spring Boot 3.3 still uses `META-INF/spring.factories` for the `FailureAnalyzer` SPI. This failure analyzer registration mechanism is **different from** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, which registers auto-configuration candidates.

When packaging the application/library, verify the JAR contains both the analyzer class and the `META-INF/spring.factories` resource. If the resource is missing or the class name is misspelled, Spring Boot will not discover the custom analyzer.

### 6.6. Testing the analyzer's analysis output

You can test the analyzer directly with a unit test:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.BeanCreationException;
import org.springframework.boot.diagnostics.FailureAnalysis;

import static org.assertj.core.api.Assertions.assertThat;

class InvalidPoolConfigurationFailureAnalyzerTests {

    @Test
    void explainsUnsupportedThreadCount() {
        InvalidPoolConfigurationException cause =
                new InvalidPoolConfigurationException(128);

        Throwable startupFailure =
                new BeanCreationException("workerPool", cause);

        FailureAnalysis analysis =
                new InvalidPoolConfigurationFailureAnalyzer()
                        .analyze(startupFailure);

        assertThat(analysis).isNotNull();
        assertThat(analysis.getDescription()).contains("128");
        assertThat(analysis.getAction()).contains("1 and 64");
        assertThat(analysis.getCause()).isSameAs(cause);
    }
}
~~~

This test confirms the analyzer detects the cause inside `BeanCreationException` and produces the expected description/action. It does not verify `SpringApplication` loading the analyzer from a JAR. To verify registration end-to-end, run the real application with `app.pool.threads=128` and inspect the `Description`/`Action` sections in the startup failure output.

## 7. Isolated testing example with `ApplicationContextRunner`

`ApplicationContextRunner` creates a small, independent context for each scenario. It is useful for testing valid configurations, binding/validation failures, bean creation failures, and condition mismatches without running the whole application.

**Note:** `ApplicationContextRunner` does not boot the application via `SpringApplication`, so it does not run the startup `FailureAnalyzer`/`FailureAnalysisReporter` chain. It captures the startup exception for tests to inspect. The analyzer test in the previous section verifies analysis logic; an integration test via `SpringApplication` verifies reporter output.

### 7.1. Test dependencies

With Maven and Spring Boot 3.3.13:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot parent/BOM manages dependency versions. Set `java.version` to `17` in project properties.

### 7.2. Complete test for failure scenarios

File `src/test/java/com/example/config/StartupFailureTests.java`:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class StartupFailureTests {

    private final ApplicationContextRunner poolRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PoolTestConfiguration.class);

    @Test
    void validConfigurationStartsSuccessfully() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=8")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WorkerPool.class);
                    assertThat(context.getBean(WorkerPool.class).threads())
                            .isEqualTo(8);
                });
    }

    @Test
    void validationFailureIdentifiesInvalidProperty() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=0")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    org.springframework.boot.context.properties
                                            .bind.validation.BindValidationException.class);
                });
    }

    @Test
    void applicationSpecificLimitHasItsOwnRootCause() {
        this.poolRunner
                .withPropertyValues("app.pool.threads=128")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    InvalidPoolConfigurationException.class);
                });
    }

    @Test
    void unmatchedConditionCanCauseMissingDependency() {
        new ApplicationContextRunner()
                .withUserConfiguration(AuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    org.springframework.beans.factory
                                            .NoSuchBeanDefinitionException.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PoolProperties.class)
    static class PoolTestConfiguration {

        @Bean
        WorkerPool workerPool(PoolProperties properties) {
            int threads = properties.getThreads();

            if (threads > 64) {
                throw new InvalidPoolConfigurationException(threads);
            }

            return new WorkerPool(threads);
        }
    }

    @ConfigurationProperties(prefix = "app.pool")
    @Validated
    public static class PoolProperties {

        @Min(1)
        private int threads = 8;

        public int getThreads() {
            return threads;
        }

        public void setThreads(int threads) {
            this.threads = threads;
        }
    }

    static class WorkerPool {
        private final int threads;

        WorkerPool(int threads) {
            this.threads = threads;
        }

        int threads() {
            return threads;
        }
    }

    static class AuditClient {
    }

    static class AuditStartupCheck {
        AuditStartupCheck(AuditClient client) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.audit",
                name = "enabled",
                havingValue = "true"
        )
        AuditClient auditClient() {
            return new AuditClient();
        }

        @Bean
        AuditStartupCheck auditStartupCheck(AuditClient client) {
            return new AuditStartupCheck(client);
        }
    }
}
~~~

Four scenarios confirm four distinct outcomes:

| Test | Input | Expected outcome |
|---|---|---|
| `validConfigurationStartsSuccessfully` | `app.pool.threads=8` | Context runs, `WorkerPool` exists |
| `validationFailureIdentifiesInvalidProperty` | `app.pool.threads=0` | Context fails, root cause is `BindValidationException` |
| `applicationSpecificLimitHasItsOwnRootCause` | `app.pool.threads=128` | Context fails, root cause is `InvalidPoolConfigurationException` |
| `unmatchedConditionCanCauseMissingDependency` | `app.audit.enabled` not enabled | `AuditClient` not registered; required dependent bean fails the context |

The last test highlights a key point: an unmatched condition by itself is not necessarily an error. Startup failure occurred because another bean unconditionally required the bean excluded by the condition. If the consuming bean should also be optional, it should use a matching condition or `ObjectProvider` rather than requiring a mandatory dependency.

### 7.3. Running the tests

Maven:

~~~bash
./mvnw -Dtest=StartupFailureTests,InvalidPoolConfigurationFailureAnalyzerTests test
~~~

Gradle:

~~~bash
./gradlew test --tests com.example.config.StartupFailureTests
./gradlew test --tests com.example.config.InvalidPoolConfigurationFailureAnalyzerTests
~~~

Expected result: tests PASS. `ApplicationContextRunner` checks context failure and root cause; the separate unit test checks `FailureAnalysis` contents.

## 8. Investigating configuration failures in a fixed sequence

### Step 1: determine when failure happened

Read the last log lines before `APPLICATION FAILED TO START`. Determine whether the failure occurred while reading config, creating beans, starting the server, or executing runners. If logs show context refresh completed without reaching readiness, inspect runners and lifecycle events.

### Step 2: record the outermost exception

Note the exception name, message, and the bean/property being processed. For example, `Error creating bean with name 'dataSource'` points to the first bean to inspect.

### Step 3: follow the cause chain

Find relevant `Caused by` clauses. Record the meaningful root cause and the first stack frame in application/library code. If suppressed exceptions exist, inspect those branches separately.

### Step 4: verify effective configuration

Record keys, runtime values, property sources, active profiles, and config imports. Compare against `@ConfigurationProperties` defaults and constraints. Keep secrets out of reports.

### Step 5: inspect conditions and the bean graph

If a bean is missing, enable `--debug` and read positive/negative matches, exclusions, and bean methods. Determine whether `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, or `@ConditionalOnMissingBean` matched. Inspect qualifiers, primary candidates, and dependencies of consuming beans.

### Step 6: inspect runtime dependencies

If the cause is `NoClassDefFoundError` or `NoSuchMethodError`, check the runtime dependency tree, version conflicts, classloaders, and packaged artifacts. A passing build does not prove the runtime classpath matches the execution environment.

### Step 7: reproduce with a small test

Use `ApplicationContextRunner` with the exact properties, user configurations, and classpath. Vary one input at a time to confirm hypotheses. If the error occurs only during config data loading or web server startup, use an integration test with `SpringApplication` or `RANDOM_PORT`.

### Step 8: fix the cause, preserve error information

Fix the offending property, dependency, condition, or bean design. Do not catch exceptions only to log a generic message, return `null`, or strip validation so the application boots in an invalid state.

### Step 9: re-verify the startup path

Run related tests, then boot the application with the same profiles and deployment config. Confirm `Started ...` logs, runner completion, the server opening the right port, and readiness transitioning to accept traffic.

## 9. Common configuration failure categories

### 9.1. Invalid YAML or Config Data

Symptoms: YAML parse errors, missing required imported files, or inactive profiles.

Check:

- YAML indentation and data types.
- `spring.config.import`, `spring.config.location`, and relative paths.
- Actual profile names and `application-{profile}.yml` files.
- Whether files are packaged or mounted into containers.
- If a resource is genuinely optional, consider the `optional:` prefix instead of disabling all config checks.

### 9.2. Binding and validation

Symptoms: `ConfigurationPropertiesBindException`, `BindException`, or `BindValidationException`.

Check:

- Prefix and canonical property names.
- Whether data types can be converted.
- Whether actual values violate `@Min`, `@NotNull`, `@NotBlank` constraints.
- Whether the properties bean is registered with `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`.
- Whether a validation implementation is on the classpath.
- Which property source overrode the expected value.

### 9.3. Unmatched conditions

Symptoms: a default bean does not appear or a dependency is missing.

Check:

- Whether the class actually exists on the runtime classpath.
- Whether property conditions have the right `havingValue` and `matchIfMissing`.
- Whether a user bean caused `@ConditionalOnMissingBean` to back off.
- Whether the auto-configuration was excluded.
- Whether bean conditions evaluated after the bean definitions they depend on.
- Whether multiple beans of the same type, wrong qualifiers, or missing `@Primary` exist.

### 9.4. Bean creation and dependency graph

Symptoms: `BeanCreationException`, `UnsatisfiedDependencyException`, circular dependencies.

Check:

- Whether constructors/factory methods throw exceptions.
- Whether `@PostConstruct`, `InitializingBean`, or init methods fail.
- Whether dependencies are created in the right order.
- Whether circular dependencies exist among services/repositories/configurations.
- Whether a bean must initialize eagerly or dependencies can be decoupled.
- Whether lazy initialization is deferring errors until first use.

### 9.5. Classpath and version conflicts

Symptoms: `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, `LinkageError`.

Check:

~~~bash
./mvnw dependency:tree
~~~

Or:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Compare actual versions of Spring Boot, Spring Framework, drivers, and third-party SDKs. Use compatible dependency management/BOMs; do not force an isolated Spring Framework module version without considering the whole graph.

### 9.6. Embedded server and ports

Symptoms: server factory initializes, yet the connector fails to bind.

Check:

- Whether another process is using the port.
- `server.port`, `server.address`, container port mappings, and network policies.
- TLS keystores/certificates, passwords, protocols, and certificate chains.
- Whether server-specific properties match Tomcat/Jetty/Undertow.

### 9.7. Runners and startup tasks

Symptoms: context refreshes, yet `SpringApplication.run` still throws an exception.

Check:

- Which `ApplicationRunner`/`CommandLineRunner` is running.
- Which migration, seed data, cache warm-up, or downstream connection failed.
- Whether tasks are idempotent with sensible timeouts.
- Whether long work is running inside an inappropriate lifecycle callback.

## 10. Common mistakes when handling startup failures

- **Reading only the outermost exception:** wrappers rarely state the specific cause; read the cause chain.
- **Taking only the root cause and discarding the wrapper:** loses which bean, property, or phase failed; preserve both.
- **Confusing condition mismatch with condition error:** an unmatched condition may be intended behavior; it becomes a failure only when a mandatory dependency is missing.
- **Using `--debug` and assuming everything is logged:** debug mode enables only selected diagnostic loggers; enable specific loggers when justified.
- **Using the condition report to find binding errors:** the report explains auto-configuration conditions, not stack traces and validation errors.
- **Checking only YAML:** environment variables, system properties, profiles, and command-line args can override values.
- **Disabling validation so the app boots:** configuration errors may turn into far more dangerous runtime bugs; fix values or constraints.
- **Adding `@Lazy` to hide startup failures:** lazy initialization merely defers failure discovery until first use.
- **Catching `Exception` and ignoring it:** the context may start while beans remain in an invalid state.
- **Using `@Primary` to fix every `NoSuchBeanDefinitionException`:** `@Primary` resolves multiple candidates, not missing beans.
- **Using `@Import` or broad component scanning to bypass wrong conditions:** identify why auto-configuration did not register and fix the condition.
- **Writing overly broad analyzers:** an analyzer catching `RuntimeException` can shadow specialized analyzers; target specific exception types and return `null` when unable to handle.
- **Registering analyzers via `AutoConfiguration.imports`:** analyzers use the `META-INF/spring.factories` SPI; imports are for auto-configurations.
- **Testing an analyzer with `ApplicationContextRunner` and thinking the reporter was tested:** the runner bypasses `SpringApplication` failure handling; unit test the analyzer and integration test startup separately.
- **Testing only successful contexts:** also test invalid values, missing beans, condition mismatches, and expected root causes.
- **Failing to re-verify with deployment profiles:** a test with static properties does not prove production loads the same config.

## 11. Incident investigation checklist

| Question | Evidence to record |
|---|---|
| Which startup phase halted? | Final log lines, events, or bean being created |
| What is the outermost exception? | Class and message |
| What is the meaningful root cause? | Cause chain and relevant stack frames |
| What is the effective property? | Key, masked value, property source, profile |
| Which condition failed to match? | Positive/negative match and message |
| Which bean is missing or failed? | Bean name, type, dependencies, and factory method |
| Are runtime dependencies right? | Maven/Gradle dependency tree and artifact versions |
| Is the failure reproducible standalone? | ApplicationContextRunner or integration test |
| Is a custom FailureAnalyzer needed? | Specific exception, description, and action |
| After fixing, what proves recovery? | Passing tests, startup logs, runner completion, readiness |

## 12. Self-check questions

1. Is `BeanCreationException` always the root cause? **No.** It is usually a wrapper for constructor, factory method, binding, or lifecycle errors.
2. Does an unmatched `@ConditionalOnProperty` always fail the application? **No.** Only when a mandatory dependency is unfulfilled or other logic requires that bean.
3. What does `BindValidationException` indicate? **Values were bound but violated validation constraints** on configuration properties.
4. Why record the property source? **To determine the true runtime value**, not just what appears in YAML.
5. Does `--debug` enable all DEBUG logs? **No.** It enables a curated set of diagnostic loggers and the condition report.
6. Does `ConditionEvaluationReport` replace stack traces? **No.** It explains auto-configuration conditions, not bean/binding failure cause chains.
7. What are the main parts of `FailureAnalysis`? **Description, Action, and Cause.**
8. Which file registers a custom `FailureAnalyzer` in Spring Boot 3.3? **`META-INF/spring.factories`**, under key `org.springframework.boot.diagnostics.FailureAnalyzer`.
9. Does `ApplicationContextRunner` run `FailureAnalysisReporter` like `SpringApplication`? **No.** The runner stores startup failures for tests; the reporter is part of SpringApplication startup failure handling.
10. Which test confirms property validation? **Supply a constraint-violating value and assert the context fails with root cause `BindValidationException`.**
11. When can `NoSuchBeanDefinitionException` stem from a condition? **When a condition excludes a bean yet another bean still requires injecting it.**
12. Why avoid enabling lazy initialization to mask startup failures? **Errors may surface only on first use, pushing incidents into runtime.**
13. What does `NoSuchMethodError` usually require checking? **Dependency version conflicts and the actual loaded classes.**
14. If context refresh succeeds yet a runner throws an exception, can the app report a startup failure? **Yes.** Runners execute before `SpringApplication.run` completes and before readiness transitions.

## 13. Official reference documentation (Spring Boot 3.3.13)

- [SpringApplication — Startup Failure](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): failure analysis, `--debug`, startup lifecycle, and application events.
- [Create Your Own FailureAnalyzer](https://docs.spring.io/spring-boot/3.3/how-to/application.html): writing and registering `FailureAnalyzer` in `META-INF/spring.factories`.
- [FailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html): contract for analyzing exceptions and returning `FailureAnalysis`.
- [AbstractFailureAnalyzer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/AbstractFailureAnalyzer.html): finding causes by exception type and building specialized analyzers.
- [FailureAnalysis API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysis.html): description, action, and cause.
- [FailureAnalysisReporter API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/diagnostics/FailureAnalysisReporter.html): reporting analysis results.
- [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): property source precedence, config data, profiles, binding, and validation.
- [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test contexts, and startup behavior.
- [ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): building small contexts to test conditions and startup failures.
