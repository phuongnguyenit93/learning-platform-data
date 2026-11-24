# Failed to Load ApplicationContext and Tracing the First Error

## 1. Starting from a Misleading Message

When writing Spring Boot integration tests, an entire JUnit test class can sometimes turn red before any business assertion runs:

~~~text
java.lang.IllegalStateException:
  Failed to load ApplicationContext for
  [WebMergedContextConfiguration@... testClass=...]
~~~

Subsequent tests may display a different message:

~~~text
java.lang.IllegalStateException:
  ApplicationContext failure threshold (1) exceeded:
  skipping repeated attempt to load context for [...]
~~~

If you only read the last line in your IDE, it is very easy to jump to the wrong conclusion that the Spring TestContext cache is corrupted, or that increasing a timeout/resetting the cache is the fix. In reality, `Failed to load ApplicationContext` is usually a **wrapper** around an error that occurred **while building the context**: a missing bean, misbound configuration properties, unreachable database, exception thrown by a bean factory, missing profile, failed migration, incomplete web slice configuration, or unready Testcontainers.

Starting in **Spring Framework 6.1**, TestContext applies a **context failure threshold** policy. The default threshold is **1**: for a given **context cache key**, the first failed load is recorded; subsequent load attempts may be **intentionally skipped** and report only threshold exceeded. The "skipping repeated attempt" line is a **consequence of the earlier failure**, not the root cause. Spring Framework 6.2—the foundation of Spring Boot 3.5—exhibits this same behavior.

**Most important rule:** Find the **chronologically first failed context initialization for the cache key in question**, read the entire `Caused by` exception chain of that attempt, and then verify with an experiment changing **one specific cause**. Do not treat the threshold error on the 10th test as the root cause.

This lesson belongs to **Test Troubleshooting** and focuses specifically on **"Failed to load ApplicationContext and tracing the first error."** The example uses a **Java 17 / Spring Boot 3.5.16 / Maven / JUnit 5** project with:
- Normal tests proving the context and web slice work.
- `*ReproducerIT` tests that intentionally break context startup, **not executed by Surefire by default**.
- A test using `ApplicationContextRunner` that captures startup failure **as data to assert**, without making the test suite red.
- A guide to reading stack traces, condition evaluation reports, Spring profiles/configuration, bean injection, Testcontainers, SQL migrations, and Spring TestContext cache boundaries.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **test assertion** failures, **JUnit test instance creation** failures, **Spring TestContext bootstrap** failures, and **Spring ApplicationContext refresh** failures.
2. Recognize `IllegalStateException: Failed to load ApplicationContext` as a wrapper rather than the underlying fault category.
3. Identify the **first failing test/context cache key** rather than looking only at whichever test appears first in the red list.
4. Follow the chain `BeanCreationException` -> `UnsatisfiedDependencyException` -> `NoSuchBeanDefinitionException` or other causes accurately.
5. Understand why `ApplicationContext failure threshold (1) exceeded` does not contain enough information to fix the bug.
6. Enable `debug=true` or `ConditionEvaluationReportLoggingListener` logs when the auto-configuration report adds diagnostic value.
7. Verify `@SpringBootTest`, `@WebMvcTest`, `@ActiveProfiles`, `@TestConfiguration`, `@MockitoBean`, and property binding.
8. Distinguish a genuinely missing bean from a bean excluded by a test slice, profile/conditional annotation, or missing auto-configuration.
9. Diagnose DataSource, Flyway/Liquibase, Testcontainers, HTTP server, port, and logging initialization failures.
10. Use `ApplicationContextRunner`/`getStartupFailure()` to write regression tests for auto-configuration and startup failures.
11. Run a single reproducer with Maven Surefire and read `target/surefire-reports` without masking errors using failure reruns.
12. Know when to fix configuration, when to widen test scope, when to mock, and when to verify an actual external dependency.
13. Avoid risky workarounds such as setting a huge failure threshold permanently, enabling lazy initialization to hide errors, deleting all tests, or disabling security/transactions.
14. Write a bug report with **symptom, root cause, evidence, fix, and verification check**.

## 2. The Context Is Created Before the Test Method

### 2.1. Spring Boot Test Startup Flow

A JUnit Jupiter class:

~~~java
@SpringBootTest
class OrdersIntegrationTest {

    @Autowired
    OrderService service;

    @Test
    void processesOrder() {
        // ...
    }
}
~~~

can fail **before entering `processesOrder()`**, because `SpringExtension`/TestContext must bootstrap and inject the test instance. Simplified diagram:

~~~text
JUnit Jupiter discovers test
    |
    v
SpringExtension / TestContextManager
    |
    +-- resolve test configuration and cache key
    +-- look up cached ApplicationContext
    |
    +-- cache MISS:
    |       |
    |       v
    |   SpringBootContextLoader / SpringApplication
    |       |
    |       +-- prepare Environment / active profiles
    |       +-- process @Configuration / auto-config conditions
    |       +-- register bean definitions
    |       +-- instantiate non-lazy singleton beans
    |       +-- create datasource/listeners/clients/web infrastructure
    |       +-- bind and validate configuration properties
    |       +-- invoke bean initializers/migrations
    |       +-- finish context refresh
    |
    +-- cache HIT -> use existing context
    |
    v
Dependency injection into test instance
    |
    v
@BeforeEach
    |
    v
@Test method + assertions
~~~

An error at any step of `SpringApplication`/context refresh can prevent the test method from **ever starting**. Because of this, an assertion inside `@Test` cannot catch that bootstrap error using `assertThrows(...)`: JUnit never enters the test body. To test a startup failure as a value, use `ApplicationContextRunner` (section 10) or construct a controlled context programmatically.

### 2.2. Distinguishing Four Failure Layers

| Symptom | Failure Boundary | First Direction |
| --- | --- | --- |
| `AssertionFailedError: expected...` | Test body executed but assertion failed | Check actual/expected and fixture |
| `ParameterResolutionException` or JUnit extension error | JUnit / test instance / test parameter | Check parameter resolver and extension |
| `Failed to load ApplicationContext` | Spring TestContext could not build context | Find first startup failure + `Caused by` |
| `ApplicationContext failure threshold exceeded` | Spring TestContext already recorded failure for same key | Find the **earlier** failure in logs/reports |
| `No qualifying bean of type ...` | Bean injection/autowiring | Scan/slice/profile/conditional/qualifier |
| `BindException` / `ConfigurationPropertiesBindException` | Environment -> typed config | Property source/value/validation |
| `Unable to open JDBC Connection` | External DB / pool / network | JDBC URL, credentials, DB readiness |
| `FlywayException` / SQL syntax | Schema migration/init | Migration version, dialect, permissions |
| `WebServerException` / Port in use | Embedded server startup | Port/`webEnvironment` |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath/version | Dependencies/test scope/binary compatibility |
| `BeanCurrentlyInCreationException` | Bean creation cycle | Dependency graph/refactor |
| `NoSuchMethodError` / `AbstractMethodError` | Binary incompatibility | BOM alignment, dependency tree |

This table is a **starting orientation**, not a substitute for reading the actual stack trace. Exception wrappers can nest across multiple layers, and ordering/messages vary by version.

### 2.3. The Outermost Exception Name Is Not Enough

A stack trace might look like:

~~~text
IllegalStateException: Failed to load ApplicationContext
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'auditController'
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'auditService'
  Caused by: NoSuchBeanDefinitionException:
    No qualifying bean of type 'AuditSink'
~~~

The actionable issue usually lies in **`AuditSink` having no valid bean in this context**, rather than `auditController` needing "a longer timeout." Even then, adding `@Component` is not necessarily the right fix: the bean might be excluded by a slice or active profile, lack an implementation, or a mock might be replacing the wrong type.

### 2.4. "First Error" Has Two Meanings

**Chronological:** The first bootstrap attempt for a context cache key in the suite, before the threshold suppresses subsequent attempts. This is mandatory to locate when many tests fail together.

**Causal:** The outer exception leading into `Caused by`, ending at the deepest cause. The "deepest cause" is often closest to the direct technical fault (e.g., `ConnectException: Connection refused`), while the "reason to fix" may sit higher up (e.g., wrong URL loaded from a profile). Do not just chop off the final `Caused by` line and blame the network.

The right reasoning order is:
1. **First failing startup attempt** (from the suite log).
2. **Exception chain** of that attempt.
3. **First actionable misconfiguration** consistent with the evidence.
4. **Reproduction/fix verification**.

### 2.5. Do Not Ignore APPLICATION FAILED TO START

Spring Boot includes `FailureAnalyzer` components for certain startup errors, printing blocks like:

~~~text
***************************
APPLICATION FAILED TO START
***************************

Description:
Parameter 0 of constructor in ... required a bean of type
'com.example.AuditSink' that could not be found.

Action:
Consider defining a bean of type 'com.example.AuditSink'
in your configuration.
~~~

This is an **illustration**, not fixed output from this project. Boot renders different analyzers depending on the exception. Read `Description` and `Action`, but still cross-check the stack trace and actual configuration; the analyzer cannot decide for you whether to use `@MockitoBean`, `@Import`, or fix component scanning.

## 3. Context Failure Threshold: Source of the Noisy "Second Error"

### 3.1. Policy Since Spring Framework 6.1

In Spring Framework 6.1 and 6.2:
- TestContext caches an `ApplicationContext` for tests sharing the same configuration cache key.
- If loading for that key fails, the framework increments a failure counter.
- `spring.test.context.failure.threshold` defaults to **1**.
- A subsequent attempt with the **same cache key** can be **skipped immediately** because the threshold has been reached.
- The exception thrown when skipping is typically `IllegalStateException` with `ApplicationContext failure threshold (1) exceeded`.
- Purpose: avoid wasting time restarting a context that is guaranteed to fail due to broken configuration or unavailable external resources during the test run.

The skip message does not contain the full exception chain of the first bootstrap. If an IDE only shows the tab for the last failing class, learners easily miss the root error.

### 3.2. Cache Keys Are More Than Just the Test Class

Spring TestContext derives a unique context configuration key from attributes such as:
- `@ContextConfiguration` classes/locations/initializers/loader.
- `@ActiveProfiles`.
- `@TestPropertySource` properties/files.
- `@DynamicPropertySource` methods.
- `contextCustomizers` (including Spring Boot test features and `@MockitoBean`/`@MockitoSpyBean` overrides).
- Parent context and web resource base path.
- Web environment and related test configuration properties.

Two classes with identical annotations/configurations can reuse a single context key. A class adding `@MockitoBean` or its own test property forms a different cache key, even with the same main application class. Therefore:
- Do not automatically conclude "class B hit class A's threshold" just because they share a package.
- Do not assume "every class gets its own first failure."
- Inspect the configuration logged in `MergedContextConfiguration` and TestContext cache `DEBUG` logs.

### 3.3. Timeline Illustration

~~~text
09:00:00 Test A loads key K
        -> bean creation fails (AuditSink missing)
        -> startup failure count(K)=1
        -> full BeanCreationException/NoSuchBeanDefinitionException log

09:00:01 Test B asks for same key K
        -> failure threshold(1) exceeded
        -> no second full bootstrap attempt
        -> quick IllegalStateException explaining skip

09:00:02 Test C asks for different key K2
        -> framework may actually attempt another bootstrap
        -> error chain may differ, depending configuration
~~~

Do not label Test B "broken by cache" and sprinkle `@DirtiesContext` everywhere. It usually just indicates Test A failed earlier.

### 3.4. Changing the Threshold Is for Diagnosis, Not a Fix

You can run once with:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -Dspring.test.context.failure.threshold=1000000 test
~~~

This is a diagnostic command: raising the threshold very high forces Spring to attempt reloading a failed cache key rather than skipping early. **It does not fix a missing bean, invalid property, or DB downtime.** It slows down the test suite, repeats huge startup logs, wastes resources, and can overload Docker/DB instances.

Nor should you set the threshold to 0: the official documentation requires a **positive integer**. The default of 1 is appropriate for most builds. After identifying the cause, return the configuration to the default.

### 3.5. Why Does Rerunning a Single Test Often Help?

Running a single failing class/method in a **fresh test JVM run**:
- Starts with a fresh static Spring TestContext cache.
- Has zero prior failures recorded for that key.
- Makes the **full first startup exception** easy to see.

For example:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT test
~~~

If the build tool reuses forks or keeps a JVM test runner alive, revisit the reset assumption. When a test only fails in the full suite, running it in isolation may PASS because order dependency is gone; in that case, reproduce with the relevant group of tests and order/parallel conditions rather than a single class.

### 3.6. Maximum 32 Cached Contexts and LRU

Spring Framework 6.2 caches up to **32 contexts** by default, using LRU eviction. You can enable:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

or configure the logger in the test runtime. `DEBUG` logs reveal hits, misses, and cache size, though **a cache hit does not mean context startup never failed under another configuration**; and the same class across two JVM forks does not share a static cache.

Do not change `spring.test.context.cache.maxSize` merely to avoid reading the root cause. Cache size manages performance and context lifecycle, not bean dependencies.

## 4. A 10-Step Process for Tracing the First Error

### Step 1 — Save the Complete Log of the Failing Run

Do not screenshot only the last 10 lines. Save:
- Full stdout/stderr of the test process.
- Maven Surefire XML/TXT reports.
- The Spring Boot startup `APPLICATION FAILED TO START` block if present.
- The first `Failed to load ApplicationContext` block.
- The full `Caused by` chain.
- Build command, JDK, Boot version, active profiles, and test class set.
- Context cache/threshold messages if the suite has multiple failures.

If logs are huge, save CI artifacts and filter against the **preserved original** rather than discarding raw logs upfront.

### Step 2 — Separate Test Startup Failures from Assertions

If the `@Test` body was never invoked, do not tweak Mockito verifications or AssertJ expectations. Investigate context lifecycle/setup. If `@Test` ran and failed an assertion, it is a different problem (unless the test body itself launches `SpringApplication`/refreshes a context).

### Step 3 — Find the Chronologically First Attempt

Search for the **first** occurrence of:
- `Error creating bean with name ...`.
- `APPLICATION FAILED TO START`.
- `Failed to load ApplicationContext` **that is not a threshold skip**.
- `Exception encountered during context initialization`.
- DataSource/JPA/Flyway/Testcontainers startup exceptions.

In parallel suites, log lines from different contexts can interleave. Filter by test name, logger thread, `MergedContextConfiguration`, or unique context config; the "first line in the entire file" may belong to an unrelated context key.

### Step 4 — Read from Outside In

Write down the tree:

~~~text
OUTER:
  IllegalStateException: Failed to load ApplicationContext
CAUSE:
  UnsatisfiedDependencyException: auditController
CAUSE:
  UnsatisfiedDependencyException: auditService
ROOT TECHNICAL:
  NoSuchBeanDefinitionException: AuditSink
ACTIONABLE:
  @WebMvcTest loads only the controller, missing the service collaborator;
  the test should @MockitoBean AuditService or import the proper configuration.
~~~

Do not blindly add mocks to a full application integration test if the goal is testing real services. Base the fix on test scope.

### Step 5 — Verify Active Profiles and Property Sources

Check:
- Is `@ActiveProfiles` spelled correctly?
- Were `application-test.yml`/`application-integration.properties` actually loaded?
- Does `@SpringBootTest(properties=...)` override values?
- Are environment variables/CI secrets missing?
- Does `@TestPropertySource` diverge from local config?
- Does a `@DynamicPropertySource` supplier return an unready endpoint?
- Are `@Profile`/`@ConditionalOnProperty` beans active?

An empty or mistyped property can make the Boot binder fail while constructing beans; inspect **property name, rejected value, and origin** in the bind error, redacting any secrets.

### Step 6 — Separate Test Slices from Full Context

`@WebMvcTest` loads MVC infrastructure + controllers and select MVC-related beans, without automatically scanning every `@Service`/`@Repository`. A controller constructor requiring a service can throw `NoSuchBeanDefinitionException`. For controller unit/slice tests, `@MockitoBean` is appropriate. For integration tests needing real services, use `@SpringBootTest` + `@AutoConfigureMockMvc` or `@Import` the specific collaborator—do not force a slice to load the entire application unnecessarily.

### Step 7 — Check External Dependencies

If the deepest cause is network/JDBC:
- Has the container started and become **ready**?
- What are the actual Testcontainers mapped host/port?
- Is a DataSource client holding a stale port from a cached context?
- Are JDBC URL, schema, username, password, and driver correct?
- Do Flyway/Liquibase migrations have valid permissions and SQL compatibility?
- Is an in-memory H2 database properly seeded/initialized?
- Is the test broker/Redis/S3 endpoint running?

If an external service is not ready yet, use a readiness/wait strategy instead of an unconditional `Thread.sleep(10000)`.

### Step 8 — Enable Condition Reports Purposefully

Spring Boot provides `FailureAnalyzer` and `ConditionEvaluationReport` to explain auto-configuration matches and non-matches. Enable `debug=true` or:

~~~properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
~~~

If running the app directly:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

When tests rather than the main app fail, apply debug logging to the **corresponding test environment** (e.g., `@SpringBootTest(properties = "debug=true")` in a temporary diagnostic run or system/test properties). Note that adding a new test property changes the **context cache key**, so do not use that run alone to infer the original suite's threshold behavior.

**Do not** assume "Negative matches" in the condition report are automatically bugs. Most auto-configurations intentionally do not match. Focus on entries directly tied to the missing bean.

### Step 9 — Change One Variable and Re-Verify

For example:
- Add only `@MockitoBean AuditService` in the MVC slice rather than editing 10 dependencies.
- Fix `demo.client.attempts=0` to a valid value.
- Register `AuditSink` under the proper component scan.
- Align `@ServiceConnection` container ownership/lifetime.
- Fix one broken migration script.

Run a narrow test to prove the cause disappears; then run the failing class/suite.

### Step 10 — Ensure No False Green

Verify:
- Number of **executed** tests, not just Maven's exit code.
- No `@Disabled`/conditional skips hiding missing tests.
- No `rerunFailingTestsCount` masking initial failures.
- No disabling of validation/auto-config/security just to start the context if it breaks the contract.
- No permanently inflated failure threshold.
- When changing profiles/test slices, the intended layer is still tested.
- Regression tests assert **real behavior after context startup**.

## 5. Reading Stack Traces to Reach an Actionable Root Cause

### 5.1. BeanCreationException vs UnsatisfiedDependencyException

`BeanCreationException` means Spring failed to finish creating a bean. Causes include:
- Constructor threw an exception.
- `@Bean` method threw.
- Dependency injection could not be resolved.
- `@PostConstruct`/`InitializingBean` failed.
- Configuration binding/validation failed.
- Database migration/connection failed in an initializer.

`UnsatisfiedDependencyException` is a specific subtype raised when a dependency cannot be resolved. It typically includes parameter index/type and the bean chain.

Do not try to patch every bean up the chain: one missing dependency at the bottom can trigger 10 bean creation failures above it.

### 5.2. NoSuchBeanDefinitionException

Example:

~~~text
No qualifying bean of type
'com.example.diagnostics.AuditSink' available:
expected at least 1 bean which qualifies as autowire candidate
~~~

Checklist:
- Does the implementation have `@Component`/`@Service`/`@Repository` or a `@Bean` method?
- Is the class **under the package scan** of `@SpringBootApplication`?
- Is the test a `@WebMvcTest`/`@DataJpaTest`/`@JsonTest` slice?
- Is the bean active only under a disabled profile?
- Did `@ConditionalOnProperty`/`@ConditionalOnClass` fail to match?
- Was the bean excluded/overridden?
- Does the bean have a compatible scope/lifecycle?
- Should the dependency actually be mocked in a slice?

Distinguish **"absent in this test context"** from **"absent in the production application."**

### 5.3. NoUniqueBeanDefinitionException

Example:

~~~text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2: stripeGateway,fakeGateway
~~~

This is not a missing bean. Choose explicitly via `@Qualifier`, `@Primary`, profile/conditional registration, or collection injection. Do not blindly add `@MockitoBean`, which can worsen candidate ambiguity.

### 5.4. BeanCurrentlyInCreationException

Often points to a circular dependency:

~~~text
ServiceA -> ServiceB -> ServiceA
~~~

Spring Boot discourages/disallows circular dependencies by default. Fix by splitting responsibilities, introducing event-driven boundaries, or using lazy providers only when genuinely justified; do not enable `spring.main.allow-circular-references=true` just to make tests green without understanding the cycle.

### 5.5. ConfigurationPropertiesBindException

Example:

~~~text
Failed to bind properties under 'demo.client'
to com.example.diagnostics.ClientProperties

Property: demo.client.attempts
Value: "0"
Reason: must be greater than or equal to 1
~~~

This is an **illustrative shape**, not verbatim output from a run. The root issue lies in the **rejected property** and constraint. Check:
- Which property source won by precedence?
- Did a profile/test annotation or CI env var override it?
- Is kebab-case/camelCase binding correct?
- Is the numeric/duration/URL/enum value valid?
- Is a Bean Validation provider on the classpath?
- Is the config class registered via `@EnableConfigurationProperties`/`@ConfigurationPropertiesScan`?
- Is a custom converter loaded in the context?

### 5.6. NoClassDefFoundError and NoSuchMethodError

A dependency can compile yet fail on a different runtime test classpath:
- Incorrect `test` vs `runtime`/`provided` scope.
- Spring Boot BOM overridden by incompatible Spring Framework/Mockito/Jackson versions.
- Transitive dependency excluded.
- Java bytecode version newer than the running JDK.
- Shaded jars or classloader differences.

Use:

~~~bash
mvn dependency:tree
mvn -version
java -version
~~~

Do not fix by copying a random jar onto the classpath or arbitrarily downgrading individual Spring modules. Let the Boot BOM manage aligned versions whenever possible.

### 5.7. Exceptions on the Test Instance Are Not Context Refresh

When an `@Autowired` field on the test class fails to inject, the failure can happen when Spring TestContext post-processes the test instance **after the ApplicationContext loads**. The stack trace may show `UnsatisfiedDependencyException` referencing the test class without an outer `Failed to load ApplicationContext`. Identify the stage before editing configuration, and do not lump every test injection issue into context failure thresholds.

## 6. Java 17 / Spring Boot 3.5.16 Project to Reproduce and Fix Failures

### 6.1. Design Goals

A simple audit application:
- `AuditController` exposes `GET /audit/{id}`.
- `AuditService` requires an `AuditSink`.
- `ConsoleAuditSink` is the default Spring component and merely logs a synthetic event without calling external services.
- `ClientProperties` holds `demo.client.endpoint` and `demo.client.attempts`, bound and validated.
- The main Spring Boot app is configured properly so **healthy tests PASS**.

Deliberate failures:
1. `MissingSinkFirstReproducerIT`/`MissingSinkSecondReproducerIT` both specify an **isolated Spring Boot config lacking `AuditSink`**. When run together under the same TestContext cache key, the first class reports the failure chain while the second can report threshold exceeded.
2. `BadBindingReproducerIT` overrides `demo.client.endpoint` to blank and `attempts=0`, triggering bind validation failure.
3. `MissingMvcDependencyReproducerIT` uses `@WebMvcTest` without mocking collaborator `AuditService`, leaving the MVC slice missing a bean.

These `*ReproducerIT` classes **fail intentionally**. Maven Surefire by default typically detects patterns like `*Test`/`*Tests`/`Test*`/`*TestCase`, **not `*IT`**. The `-Dtest=...` commands below target a specific reproducer to inspect the root cause. Do not name deliberate failures `*Test` and break default `mvn test` for the whole lesson.

### 6.2. File Tree

~~~text
first-context-failure-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/diagnostics/
│   │   ├── DiagnosticsApplication.java
│   │   ├── ClientProperties.java
│   │   ├── AuditSink.java
│   │   ├── ConsoleAuditSink.java
│   │   ├── AuditService.java
│   │   └── AuditController.java
│   └── resources/application.properties
└── src/test/java/com/example/diagnostics/
    ├── FullContextHealthyTest.java
    ├── MvcSliceHealthyTest.java
    ├── PropertiesOverrideHealthyTest.java
    ├── ContextRunnerFailureInspectionTest.java
    ├── PlainAuditServiceTest.java
    ├── IsolatedMissingSinkConfiguration.java
    ├── MissingSinkFirstReproducerIT.java
    ├── MissingSinkSecondReproducerIT.java
    ├── BadBindingReproducerIT.java
    └── MissingMvcDependencyReproducerIT.java
~~~

No Docker or DB is required for the main runnable sample. External DB, Testcontainers, and Flyway failure types are analyzed via **separate diagnostic patterns** to avoid forcing 10 external dependencies into a small lab just to trigger startup errors.

### 6.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>first-context-failure-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Explanation:
- `spring-boot-starter-web` provides Spring MVC, Jackson, and web auto-configuration for controllers and slices.
- `spring-boot-starter-validation` provides a Jakarta Bean Validation implementation (typically Hibernate Validator).
- `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, Mockito, Spring Test, and Spring Boot `ApplicationContextRunner`.
- The Boot BOM (parent) manages versions; do not pin a separate Spring Framework major version.
- Java 17 is supported by Spring Boot 3.5.
- `@MockitoBean` is the Spring Framework 6.2 API in `org.springframework.test.context.bean.override.mockito`; legacy `@MockBean` is not used in this 3.5 example.

### 6.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=first-context-failure-lab

demo.client.endpoint=https://example.invalid/api
demo.client.attempts=3

# For running the demo application only; unit/slice tests do not need port 8080.
server.port=0
~~~

`example.invalid` is an example-only URL; no real network calls are made. `server.port=0` picks a random local port **if** the application starts with an embedded server. `@SpringBootTest(webEnvironment=NONE)` does not open a server despite this property. It is unrelated to the context failure threshold.

### 6.5. DiagnosticsApplication.java

`src/main/java/com/example/diagnostics/DiagnosticsApplication.java`:

~~~java
package com.example.diagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DiagnosticsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scans package `com.example.diagnostics` and subpackages. `@EnableConfigurationProperties(ClientProperties.class)` registers the typed configuration bean. Placing the main class at the proper root package lets Spring Boot tests locate the primary configuration via upward package search.

### 6.6. ClientProperties.java

`src/main/java/com/example/diagnostics/ClientProperties.java`:

~~~java
package com.example.diagnostics;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ClientProperties {

    @NotBlank
    private String endpoint;

    @Min(1)
    private int attempts;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getAttempts() {
        return attempts;
    }

    public void setAttempts(int attempts) {
        this.attempts = attempts;
    }
}
~~~

With a valid `demo.client.endpoint` and `attempts=3`, the bean binds and validates normally. With a blank endpoint or `attempts` 0, Bean Validation rejects it at startup. Because the failure belongs to typed config binding, Boot may show `ConfigurationPropertiesBindException`/`BindValidationException` or an analyzer description; rely on the actual stack trace rather than hardcoding a single wrapper type across environments.

### 6.7. AuditSink.java

`src/main/java/com/example/diagnostics/AuditSink.java`:

~~~java
package com.example.diagnostics;

public interface AuditSink {

    void publish(String id);
}
~~~

This interface is a required dependency of `AuditService`. Without an implementation bean or mock in the test context, Spring cannot create the service. In this project, a production-like implementation in the next file is registered; the deliberate isolated reproducer intentionally **omits it**.

### 6.8. ConsoleAuditSink.java

`src/main/java/com/example/diagnostics/ConsoleAuditSink.java`:

~~~java
package com.example.diagnostics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ConsoleAuditSink implements AuditSink {

    private static final Logger log =
            LoggerFactory.getLogger(ConsoleAuditSink.class);

    @Override
    public void publish(String id) {
        log.info("event=audit_requested id={}", id);
    }
}
~~~

Logging here is a simulated side effect, not a durable audit store or Kafka producer. Tests should not claim "audit permanently persisted" simply because the logger ran. For this lesson, the goal is context wiring and bean discovery.

### 6.9. AuditService.java

`src/main/java/com/example/diagnostics/AuditService.java`:

~~~java
package com.example.diagnostics;

import org.springframework.stereotype.Service;

@Service
public class AuditService {

    private final AuditSink sink;

    public AuditService(AuditSink sink) {
        this.sink = sink;
    }

    public String record(String id) {
        sink.publish(id);
        return "recorded:" + id;
    }
}
~~~

Constructor injection makes the dependency graph explicit: `AuditController -> AuditService -> AuditSink`. When `AuditSink` is absent in an isolated context, the fault is easy to pinpoint. In the full app, `ConsoleAuditSink` is a valid component, so the chain resolves.

### 6.10. AuditController.java

`src/main/java/com/example/diagnostics/AuditController.java`:

~~~java
package com.example.diagnostics;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/audit")
public class AuditController {

    private final AuditService service;

    public AuditController(AuditService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Map<String, String> get(@PathVariable String id) {
        return Map.of(
                "status", service.record(id));
    }
}
~~~

In a **full `@SpringBootTest`**, Spring scans controller, service, and sink. In **`@WebMvcTest(AuditController.class)`**, Spring Boot restricts the context to the MVC slice so `AuditService` is normally **not scanned**. That is an intentional difference, not "Spring forgetting to run `@Service`."

## 7. Healthy Tests That Must PASS

### 7.1. FullContextHealthyTest.java

`src/test/java/com/example/diagnostics/FullContextHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullContextHealthyTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    AuditService service;

    @Autowired
    ClientProperties properties;

    @Test
    void loadsAllRequiredBeansWithValidProperties() {
        assertThat(context.containsBean("auditService"))
                .isTrue();
        assertThat(context.containsBean("consoleAuditSink"))
                .isTrue();
        assertThat(properties.getEndpoint())
                .isEqualTo("https://example.invalid/api");
        assertThat(properties.getAttempts())
                .isEqualTo(3);
    }

    @Test
    void realServiceDependencyChainWorks() {
        assertThat(service.record("healthy_441"))
                .isEqualTo("recorded:healthy_441");
    }
}
~~~

Both methods share the Spring context; if setup breaks, they fail before the body. When the context loads cleanly, they verify bean wiring, config, and real behavior. `webEnvironment=NONE` ensures the demo does not start an embedded servlet server; `@SpringBootTest` does not always open a port.

### 7.2. MvcSliceHealthyTest.java

`src/test/java/com/example/diagnostics/MvcSliceHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AuditController.class)
class MvcSliceHealthyTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    AuditService service;

    @Test
    void returnsAStubbedAuditResult() throws Exception {
        given(service.record("mvc_441"))
                .willReturn("recorded:mvc_441");

        mvc.perform(get("/audit/mvc_441"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.status")
                                .value("recorded:mvc_441"));

        verify(service).record("mvc_441");
    }

    @Test
    void usesItsOwnMockBehaviorForAnotherRequest()
            throws Exception {
        given(service.record("other_441"))
                .willReturn("recorded:other_441");

        mvc.perform(get("/audit/other_441"))
                .andExpect(status().isOk())
                .andExpect(
                        jsonPath("$.status")
                                .value("recorded:other_441"));

        verify(service).record("other_441");
    }
}
~~~

**This is the proper fix for the MVC slice reproducer:** `@MockitoBean AuditService` supplies the collaborator in the web slice. The test verifies controller mapping, JSON, and MVC, **without** claiming real `service -> sink` integration was tested. For full service integration, use `@SpringBootTest` or import the appropriate dependencies.

### 7.3. PropertiesOverrideHealthyTest.java

`src/test/java/com/example/diagnostics/PropertiesOverrideHealthyTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.client.endpoint=https://fixed.invalid/api",
                "demo.client.attempts=5"
        })
class PropertiesOverrideHealthyTest {

    @Autowired
    ClientProperties properties;

    @Test
    void bindsOverriddenValidValues() {
        assertThat(properties.getEndpoint())
                .isEqualTo("https://fixed.invalid/api");
        assertThat(properties.getAttempts())
                .isEqualTo(5);
    }
}
~~~

This class creates a different test config/property set from `FullContextHealthyTest`, so its **context cache key can differ**. That is not abnormal cache fragmentation: it is testing a real configuration variant. It proves the binding contract is fixed rather than simply disabling `@Validated`.

### 7.4. PlainAuditServiceTest.java

`src/test/java/com/example/diagnostics/PlainAuditServiceTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class PlainAuditServiceTest {

    @Test
    void verifiesPureJavaWiringWithoutSpringContext() {
        AuditSink sink = mock(AuditSink.class);
        AuditService service = new AuditService(sink);

        assertThat(service.record("unit_441"))
                .isEqualTo("recorded:unit_441");

        verify(sink).publish("unit_441");
    }
}
~~~

A plain unit test **does not create a Spring ApplicationContext**, so neither failure threshold nor Boot startup applies. It is ideal for testing isolated Java logic, though it **does not prove production bean scanning, profiles, configuration binding, or the web layer**.

## 8. Intentionally Failing Reproducers: Kept Out of Default Maven Tests

### 8.1. IsolatedMissingSinkConfiguration.java

`src/test/java/com/example/diagnostics/IsolatedMissingSinkConfiguration.java`:

~~~java
package com.example.diagnostics;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
@EnableAutoConfiguration
public class IsolatedMissingSinkConfiguration {

    @Bean
    AuditService isolatedAuditService(AuditSink sink) {
        return new AuditService(sink);
    }
}
~~~

This is an **isolated Boot configuration** with no `@ComponentScan`, so it does not register `ConsoleAuditSink`. `@EnableAutoConfiguration` enables Boot infrastructure, but does not invent a domain implementation of `AuditSink`. The bean factory method requires an `AuditSink` that is absent from the context -> startup fails.

**Subtle detail easily missed:** This file lives in the test classpath in the same package as the main app. When `@SpringBootTest(classes=IsolatedMissingSinkConfiguration.class)` is specified **explicitly**, Boot uses this separate configuration. In the healthy tests that do not specify it, Boot finds `DiagnosticsApplication` via primary configuration discovery. Because `@SpringBootConfiguration` is not automatically component-scanned like an ordinary `@Component`, the repro config is not pulled as a bean into the full app merely by sitting in the same package.

### 8.2. MissingSinkFirstReproducerIT.java

`src/test/java/com/example/diagnostics/MissingSinkFirstReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = IsolatedMissingSinkConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MissingSinkFirstReproducerIT {

    @Test
    void contextCannotStartWithoutAnAuditSink() {
        // JUnit does not enter the method because context refresh already FAILED.
    }
}
~~~

Run separately:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT test
~~~

**The expected outcome is a non-zero exit code** and a full startup failure stack trace. Do not rename it to `*Test` in a normal CI suite. An intentional-failure reproduction is not a green regression test; its sole purpose is inspecting the exact failure path.

### 8.3. MissingSinkSecondReproducerIT.java

`src/test/java/com/example/diagnostics/MissingSinkSecondReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        classes = IsolatedMissingSinkConfiguration.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MissingSinkSecondReproducerIT {

    @Test
    void sameContextKeyMayBeSkippedAfterFirstFailure() {
        // May report failure threshold exceeded.
    }
}
~~~

Both classes share the same explicit `classes`, web environment, and no distinct test properties or bean overrides. When run in the **same test JVM/cache**, they typically share a Spring context cache key. Depending on test execution order, whichever loads first shows the full first failure, while the second can show a threshold skip. **Do not** assume classes literally run in order of names "First"/"Second"; identify the first failure from the log.

Run:

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -DtrimStackTrace=false test
~~~

Specify both classes in a single Maven invocation to observe threshold/cache reuse; do not run two separate shell commands and expect the cache to persist across processes.

### 8.4. BadBindingReproducerIT.java

`src/test/java/com/example/diagnostics/BadBindingReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
                "demo.client.endpoint=",
                "demo.client.attempts=0"
        })
class BadBindingReproducerIT {

    @Test
    void invalidConfigCannotBeValidated() {
        // Test body does not run; properties validation FAILS.
    }
}
~~~

In `ClientProperties`, `endpoint` has `@NotBlank` and `attempts` has `@Min(1)`. Boot config binding fails on invalid values. This is a **different root fault from a missing bean**: do not add `AuditSink` or `@MockitoBean` to fix a binding issue.

Command:

~~~bash
mvn -Dtest=BadBindingReproducerIT test
~~~

During analysis, look for `demo.client.endpoint`/`demo.client.attempts`, rejected values, constraint reasons, and property origins. A `BindValidationException` in the chain diagnoses invalid values much better than 20 lines of outer bean wrappers.

### 8.5. MissingMvcDependencyReproducerIT.java

`src/test/java/com/example/diagnostics/MissingMvcDependencyReproducerIT.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;

@WebMvcTest(AuditController.class)
class MissingMvcDependencyReproducerIT {

    @Test
    void mvcSliceCannotConstructControllerWithoutService() {
        // Web slice is missing the AuditService bean.
    }
}
~~~

Command:

~~~bash
mvn -Dtest=MissingMvcDependencyReproducerIT test
~~~

This is a **test-slice wiring** error, not necessarily a production misconfiguration. Fix it with `@MockitoBean AuditService` (see `MvcSliceHealthyTest`) when testing the controller contract. Do not switch the whole project from `@WebMvcTest` to `@SpringBootTest` just to pull in all collaborators without weighing test cost and scope.

### 8.6. Why Not Assert the Error Inside the @SpringBootTest Reproducers?

Code like:

~~~java
@Test
void expectsStartupError() {
    assertThatThrownBy(() -> doSomething())
            .isInstanceOf(IllegalStateException.class);
}
~~~

will **never execute** if Spring TestContext fails to load before the test body. `@SpringBootTest` does not turn a startup failure into an exception catchable inside the method. To assert "when a bean is missing, the context failure has the right root cause" while keeping the test green, use `ApplicationContextRunner` as shown next.

## 9. ApplicationContextRunner: Capturing Startup Exceptions in a Green JUnit Test

### 9.1. Why Is ApplicationContextRunner Appropriate?

`ApplicationContextRunner` in `spring-boot-test` builds a **small, isolated context** with user configuration and lets you inspect:
- Did startup succeed?
- Which beans exist or do not exist?
- What exception caused startup failure?
- What is the deepest cause exception?
- How do properties or auto-configuration conditions change behavior?

It does not use `@SpringBootTest` to initialize a context before the test instance. Hence, a test can **expect the context to fail** and assert the failure **while JUnit itself PASSES**. Note that it does not use Spring TestContext's failure threshold/cache mechanism the way `@SpringBootTest` does; do not cite runner results as proof of `threshold = 1`.

### 9.2. ContextRunnerFailureInspectionTest.java

`src/test/java/com/example/diagnostics/ContextRunnerFailureInspectionTest.java`:

~~~java
package com.example.diagnostics;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ContextRunnerFailureInspectionTest {

    @Configuration(proxyBeanMethods = false)
    static class MissingSinkConfig {

        @Bean
        AuditService auditService(AuditSink sink) {
            return new AuditService(sink);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class ExplodingBeanConfig {

        @Bean
        String simulatedDependency() {
            throw new IllegalStateException(
                    "CONFIG_FAULT_DEMO_441");
        }
    }

    private static Throwable deepestCause(Throwable failure) {
        Throwable current = failure;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }

    @Test
    void reportsMissingBeanAsRootCauseWithoutFailingJunit() {
        new ApplicationContextRunner()
                .withUserConfiguration(MissingSinkConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    Throwable failure =
                            context.getStartupFailure();

                    assertThat(failure).isNotNull();

                    Throwable root = deepestCause(failure);

                    assertThat(root).isInstanceOf(
                            NoSuchBeanDefinitionException.class);

                    assertThat(root.getMessage())
                            .contains(AuditSink.class.getName());
                });
    }

    @Test
    void reportsThrownInitializerCauseWithoutFullBootTest() {
        new ApplicationContextRunner()
                .withUserConfiguration(ExplodingBeanConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    Throwable failure =
                            context.getStartupFailure();

                    assertThat(failure).isNotNull();

                    Throwable root = deepestCause(failure);

                    assertThat(root)
                            .isInstanceOf(
                                    IllegalStateException.class)
                            .hasMessage(
                                    "CONFIG_FAULT_DEMO_441");
                });
    }
}
~~~

### 9.3. What Do These Assertions Prove?

**MissingSinkConfig test:**
- Attempts to create `AuditService` without an `AuditSink`.
- Context runner reports a startup failure.
- Deepest cause is `NoSuchBeanDefinitionException` mentioning the missing type.
- The JUnit test PASSES because **startup failure is the expected outcome** in the context runner.

**ExplodingBeanConfig test:**
- A `@Bean` factory method intentionally throws `IllegalStateException`.
- Spring wraps it in a bean creation exception.
- The root throwable retains the deterministic marker, so the test does not rely solely on outer `BeanCreationException` text.

**Limitation:** `deepestCause(...)` is a helper for locating the deepest cause, not a general analyzer for every multi-cause exception (suppressed exceptions, composite errors, or cycles that do not reduce to a single leaf). For real failures, inspect the entire chain and property/configuration context. A `ConnectException` at the bottom does not tell you which profile supplied the URL.

### 9.4. Why Not Use ApplicationContextRunner for Every @SpringBootTest?

The runner excels at **auto-configuration branches and small wiring graphs**. When you need to test:
- Real Web MVC filter chains;
- Database transactions;
- A Kafka broker;
- Security filters;
- JPA repositories;
- Multi-module component scanning;
- Full production-style `SpringApplication` startup;

you still need appropriate slice or full integration tests. `ApplicationContextRunner` does not construct a full Spring Boot environment with all auto-configurations and resources unless you explicitly register them.

## 10. Running the Project Properly and Reading Results

### 10.1. Default Test Suite (Excluding Deliberate Failures)

~~~bash
mvn -q clean test
~~~

`*Test` classes designed to PASS:
- `FullContextHealthyTest`: **2** JUnit methods.
- `MvcSliceHealthyTest`: **2** methods.
- `PropertiesOverrideHealthyTest`: **1** method.
- `PlainAuditServiceTest`: **1** method.
- `ContextRunnerFailureInspectionTest`: **2** methods.

Total **8 JUnit methods expected** under default Surefire discovery/configuration without skips. The `*ReproducerIT` classes fall outside Surefire's default include patterns. **Maven was not run while authoring this lesson**, so "8 methods expected" is not a measured test report.

### 10.2. Reproducing Missing Bean and Failure Threshold

~~~bash
mvn -Dtest=MissingSinkFirstReproducerIT,MissingSinkSecondReproducerIT \
    -DtrimStackTrace=false test
~~~

**Expectation:** Maven reporting FAIL is the exact purpose of the reproducer. Look at the first full exception before any threshold-skip exception on the same cache key. If Surefire forks separate JVMs per test, they will not share the context failure count; check fork configuration or run in one JVM to observe the mechanism.

### 10.3. Reproducing Property Binding

~~~bash
mvn -Dtest=BadBindingReproducerIT \
    -DtrimStackTrace=false test
~~~

Look for:
- `ClientProperties`.
- `demo.client.endpoint`, `demo.client.attempts`.
- `must not be blank` / `must be greater than or equal to 1`.
- Property origin if printed by the Boot binder.
- Do not get distracted by outer `BeanCreationException` wrappers.

### 10.4. Reproducing Web Slice Missing Dependency

~~~bash
mvn -Dtest=MissingMvcDependencyReproducerIT \
    -DtrimStackTrace=false test
~~~

Compare with:

~~~bash
mvn -Dtest=MvcSliceHealthyTest test
~~~

The essential difference is `@MockitoBean AuditService` in the proper slice test, not adding networking or timeouts.

### 10.5. Reading Surefire Reports

After `mvn test`, inspect:

~~~text
target/surefire-reports/
    com.example.diagnostics.FullContextHealthyTest.txt
    TEST-com.example.diagnostics.FullContextHealthyTest.xml
    ...
~~~

File names/formats vary by Surefire provider/version/config. A test context failure usually appears as a testcase error **before the test body**. Inspect the full report of the **class containing the first context startup failure**.

On Bash/Linux/macOS:

~~~bash
grep -R -n -E "Failed to load ApplicationContext|failure threshold|Caused by:|APPLICATION FAILED" target/surefire-reports
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem target/surefire-reports -File |
  Select-String -Pattern 'Failed to load ApplicationContext',
                         'failure threshold',
                         'Caused by:',
                         'APPLICATION FAILED'
~~~

**Do not just grab the matching line and discard the surrounding stack trace.** Open the corresponding report and read 20–100 lines around it. When tests run in parallel, markers in the same log do not prove they belong to the same context key.

### 10.6. Recommended Log Reading Path

~~~text
1. Build/test command, Java/Boot version
2. First startup error chronologically for target context key
3. Spring Boot "APPLICATION FAILED TO START" Description + Action
4. First "Error creating bean with name..."
5. Caused-by chain until actionable reason
6. Condition evaluation report only for relevant auto-config
7. Active profiles/property origin and classpath
8. Candidate fix and narrow regression test
9. Full affected suite; verify executed vs skipped/flaky
~~~

Do not jump straight to step 9 just because a fix made a single test method PASS. An implementation might still lack a collaborator under another profile or slice.

## 11. Missing Bean Failures and Choosing the Right Fix

### 11.1. Missing Component Scan

A main class:

~~~java
@SpringBootApplication
public class ShopApplication { }
~~~

in package `com.example.shop` defaults component scanning to that package and below. A service implementation in `com.other.module` may not be discovered. Move the main class to a common root package, add intentional `@Import`/`@ComponentScan`, or provide explicit bean configuration—rather than slapping on `@Autowired(required=false)` to paper over the gap.

### 11.2. @Profile

~~~java
@Profile("integration")
@Component
class RealAuditSink implements AuditSink {
    // ...
}
~~~

If `@ActiveProfiles("test")` is active while only an `integration` bean exists, the missing dependency matches the configuration. Fix by:
- Selecting the intended profile for the test;
- Providing a test fake bean;
- Or defining an appropriate default strategy matching product behavior.

Do not activate every profile simultaneously to dodge errors; that can create duplicate candidates, security/provider conflicts, or unintended external calls.

### 11.3. @ConditionalOnProperty

~~~java
@ConditionalOnProperty(
    prefix = "feature.audit",
    name = "enabled",
    havingValue = "true")
@Bean
AuditSink auditSink() {
    // ...
}
~~~

If the test omits the property, the bean is intentionally excluded. The condition report reveals the missing/non-matching property. Check `matchIfMissing`, `havingValue`, and property origin before assuming Spring skipped scanning.

### 11.4. @MockitoBean

Spring Framework 6.2 `@MockitoBean` can replace or create a mock bean in the test context. In an MVC slice, mocking a controller dependency is appropriate; in a full integration test, mocking repositories/services can defeat the wiring and transaction behavior you meant to verify.

**Do not fix everything by mocking every bean** when the root cause is a missing production configuration. Use mocks only at boundaries where test substitution is intended.

### 11.5. @TestConfiguration vs Nested @Configuration in Tests

In Spring Boot:
- Nested `@TestConfiguration` typically **adds to** the primary application configuration.
- Nested `@Configuration` inside a test can be used **instead of** the primary config when the test loader resolves configuration.
- `@Import(MyTestConfig.class)` explicitly loads test collaborators.
- `@SpringBootTest(classes=...)` explicitly selects app/config classes.

A class suddenly "losing all services" after adding a nested configuration often happens because the test replaced its bootstrap source. Distinguish intentional config overrides from accidentally replacing the main app config.

### 11.6. Bean Name/Qualifier Mismatch

When multiple implementations exist:
- Use `@Qualifier("...")` per contract.
- Use `@Primary` when there is a true default.
- Inject `List<AuditSink>`/`Map<String, AuditSink>` when business logic needs all of them.
- Clarify bean definitions rather than letting Mockito pick "any bean."

## 12. Configuration Binding: Prominent Startup Failures

### 12.1. Property Source Precedence

A config value can come from:
- `application.properties`/YAML.
- Profile-specific configs.
- JVM system properties.
- Environment variables.
- `@TestPropertySource`.
- `@SpringBootTest(properties=...)`.
- `@DynamicPropertySource`.
- ConfigData imports/external secrets.
- Command-line application arguments.

When binding fails, ask **which value won**, not just "my file looks right." A CI environment variable can override local config, or an unavailable secret provider can leave a placeholder unresolved.

### 12.2. @ConfigurationProperties + @Validated

With a Bean Validation provider:
- `@NotBlank` rejects null, empty, and whitespace-only strings.
- `@Min(1)` rejects 0 and negative integers.
- `@NotNull` is required on object references to forbid null.
- `@Valid` is needed for cascaded validation on nested objects.
- Type conversion during binding can fail **before** validation (e.g., letters in an integer field).

Do not remove `@Validated` just to start the context if failing fast on invalid config is a requirement. Fix the property value or constraints per business contract.

### 12.3. Missing @ConfigurationProperties Registration

A class annotated solely with `@ConfigurationProperties` is not automatically a Spring bean. It must be registered via `@EnableConfigurationProperties`, `@ConfigurationPropertiesScan`, or an explicit bean definition. Without registration, injection fails with a missing bean error—different from a validation failure on an **existing bean**.

### 12.4. Duration/URL/Type Parsing

Example:

~~~properties
demo.connect-timeout=not-a-duration
demo.max-attempts=not-a-number
~~~

If the properties class expects `Duration` or `int`, the binder throws a conversion/binding exception. Do not confuse this with a network timeout: the app failed **before any network call**.

### 12.5. Redacting Configuration in Logs

Bind errors can include rejected property values. When a property holds a password or token, redact it in logs and CI artifacts. Never paste live credentials or JDBC URLs containing passwords into bug reports. `/actuator/env` (if enabled) also requires security and value sanitization.

## 13. DataSource, JPA, Migrations, and Testcontainers

### 13.1. Missing JDBC URL or Driver

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource
could be configured
~~~

This diagnostic shape appears when a JDBC/JPA starter is present without suitable DataSource configuration. Check:
- Does this test actually need a database?
- Is H2/HSQL/Derby test dependency present if embedded DB is intended?
- Are production-like DB profile properties active?
- Is the matching driver on the test runtime classpath?
- Did `@AutoConfigureTestDatabase` swap in an embedded DB?
- Is `@ServiceConnection` or `@DynamicPropertySource` configured when using Testcontainers?
- Is there one DataSource or multiple requiring qualifiers?

Do not add H2 to a test just to turn the context green if the test must verify PostgreSQL-specific SQL, locks, or migrations.

### 13.2. JDBC Connect Refused

~~~text
org.postgresql.util.PSQLException:
  Connection to localhost:5432 refused

Caused by: java.net.ConnectException:
  Connection refused
~~~

Possible causes:
- DB container has not started or become ready.
- Wrong host or port.
- Docker mapped port is dynamic, not host 5432.
- Test profile points to an unintended dev/production DB.
- CI network/TLS/firewall issue.
- Connection pool still holds an old URL from a cached context.
- Container was stopped by JUnit `@Container` while the Spring context remained cached.

The **actionable cause** may be wrong Testcontainers lifecycle ownership rather than a missing `Thread.sleep`.

### 13.3. @Container Lifetime vs Cached Context

With the Testcontainers JUnit 5 extension:
- `@Testcontainers` + static `@Container` is scoped to the **test class**.
- Spring's `ApplicationContext` can be cached **across multiple test classes**.
- After class A finishes, JUnit can stop the container; class B reuses the cached context/DataSource pointing to the dead mapped port.
- Class B may fail with `Failed to load ApplicationContext` or on its first query depending on startup timing and cache paths.

In Spring Boot 3.5, use a **Spring-managed container bean** via `@TestConfiguration @Bean @ServiceConnection` when container lifetime should match the context, or a JVM-wide singleton container without JUnit `@Container` with clear ownership and cleanup.

**Do not assume** a connection error in a test method is always `Failed to load ApplicationContext`; if the context loaded and the DB died afterward, the error occurs during runtime querying.

### 13.4. Flyway/Liquibase Migrations

A startup failure might look like:

~~~text
BeanCreationException: Error creating bean 'flywayInitializer'
Caused by: FlywayMigrateException:
  Migration V7__orders.sql failed
Caused by: SQLException:
  relation already exists / invalid SQL syntax
~~~

This is illustrative. Check:
- Migration version and history.
- SQL dialect and DB version.
- Table/schema creation permissions.
- Leftover data from previous tests.
- Migration ordering and baseline.
- Parallel migrations hitting the same database/schema.
- Migration transaction support.
- H2 compatibility mode differing from production PostgreSQL.

Do not disable Flyway just to make tests pass if the goal is verifying production schema initialization. For controller slices that need no DB, avoid pulling in database infrastructure altogether.

### 13.5. JPA/Hibernate Mapping Errors

Common causes:
- Duplicate entity mapping, table, or column names.
- Invalid `mappedBy` or relationship annotations.
- Hibernate schema validation mismatch.
- Named query parse errors.
- Unscanned attribute converters.
- Entity package outside scan scope.
- Database dialect/driver mismatch.

JPA `EntityManagerFactory` startup exceptions are typically wrapped in `BeanCreationException`. Read the Hibernate exception in the cause chain to pinpoint the mapping issue; raising the TestContext failure threshold will not fix a mapping bug.

### 13.6. Broker/Redis Startup

Kafka/Rabbit/Redis failures can cause:
- Producer factory bean initialization failures.
- Listener container failures/timeouts.
- Connection factory exceptions.
- Wrong bootstrap servers or network settings.
- `@PostConstruct` calling an external dependency prematurely.
- Testcontainers image not yet ready.

Verify whether the test truly needs a live broker to verify business logic. When it does, use an integration test with a properly scoped container and readiness wait; when it does not, mock the adapter or use a clean unit/slice boundary.

## 14. ConditionEvaluationReport: Read Accurately, Do Not Guess

### 14.1. The Report Records Auto-Config Conditions

`ConditionEvaluationReport` lists positive/negative condition matches, exclusions, and unconditional classes. It helps answer:
- Why did `DataSourceAutoConfiguration` activate?
- Why did `MongoAutoConfiguration` not match?
- Why was a conditional bean skipped?
- Why were Security/Web MVC/JPA configs loaded?
- Which config classes matched or did not match conditions?

**A "Negative match" does not mean an error.** Most unrelated auto-configurations validly do not match.

### 14.2. Enabling Debug in the Matching Test Environment

For the main app:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

For `@SpringBootTest`:

~~~java
@SpringBootTest(properties = "debug=true")
class ContextDiagnosisTest {
}
~~~

This is a snippet, not a file in the runnable lab. Adding test properties can change the context cache key; use it to diagnose **auto-configuration branches**, then revert to the exact original test configuration to confirm the root cause. If CI logs get too big, enable debug only in a dedicated diagnostic run.

### 14.3. When the Report Helps Most

The report is most valuable for **conditional wiring** problems: beans or auto-configs missing or active due to classpath, properties, or web environment. For `NoClassDefFoundError` or JDK incompatibility, the report might not even finish building; inspect the dependency tree and full exception stack first.

### 14.4. Do Not Confuse FailureAnalyzer with JUnit Reports

Boot's `FailureAnalyzer` prints "Description/Action." JUnit `test reports` classify errors/failures/skips. A `FailureAnalyzer` message is **startup troubleshooting help**, not an assertion result, and custom exceptions may not have a dedicated analyzer.

## 15. Test Slices: Frequently Misunderstood Causes

### 15.1. @WebMvcTest

Loads MVC scope without scanning all `@Service` beans. If a controller constructor requires a service:
- `@MockitoBean` is ideal for testing HTTP mapping/validation/JSON.
- `@Import(Service.class)` only if you want the real service with all its collaborators.
- `@SpringBootTest + @AutoConfigureMockMvc` if you need the full context and accept the cost.
- Do not add a broad `@ComponentScan` to a test just to fix one missing bean, as it breaks slice boundaries.

### 15.2. @DataJpaTest

Focuses on JPA entities/repositories, typically with an embedded test DB (depending on configuration/test auto-configuration). It does not load the full service/web stack. A repository test injecting a controller fails because the test scope is wrong; fix by using the right slice or a full test.

### 15.3. @JsonTest

Loads JSON serializers/converters without scanning service dependencies. If a custom Jackson `Module` is missing, check `@Import`/test config and slice include rules. You do not need a full Boot context for pure DTO mapping.

### 15.4. @WebFluxTest

The WebFlux slice also restricts bean scope. Provide reactive controller collaborators via `@MockitoBean`/`@Import`, and use `WebTestClient`. Do not copy `@WebMvcTest` imports or `MockMvc` straight into WebFlux and wonder why types fail.

### 15.5. @SpringBootTest

Loads far more auto-configurations and Spring beans, so DB, external client, migration, or security configuration failures surface earlier. Sometimes a failure appearing only in full context is **expected**, because that test covers a broader integration boundary.

### 15.6. Controller Is Not a Bean?

If the test targets the wrong class/package, `@WebMvcTest` may miss the controller you expected. Check:
- Is the class under component scan?
- Is it annotated with `@RestController`/`@Controller`?
- Is explicit `controllers = SomeController.class` correct?
- Is an inner configuration replacing the main source?
- Are mappers/filters/advice included?

Do not fix this by mocking the controller; that defeats what you are trying to test.

## 16. ApplicationContext and TestContext Cache: Avoid Fixing in the Wrong Place

### 16.1. @DirtiesContext Is Not a Cure-All

`@DirtiesContext` marks a cached context so it is not reused. It helps when a test mutates singleton/`ApplicationContext` state. For a missing bean or invalid property, forcing a reload just reproduces the **exact same error** and slows down the suite. For failure thresholds, the context never loaded successfully in the first place; creating a fresh context key will not conjure up a missing dependency.

### 16.2. @MockitoBean Changes the Cache Key

A `@MockitoBean` override acts as a context customizer, meaning classes with different test configs will not share the same cached context. Do not compare threshold messages between two test classes with different bean overrides and conclude the framework is inconsistent.

### 16.3. @DynamicPropertySource and Stale Endpoints

A Testcontainers dynamic URL can change if a container restarts. `@DynamicPropertySource` suppliers are evaluated when the config is built; a `DataSource` inside a cached context does not re-initialize automatically every time a port changes. If tests fail across a class boundary, inspect container ownership and context lifetime rather than just DB credentials.

### 16.4. Forked JVMs Reset the Static Cache

The Spring TestContext cache is process-local static. Maven Surefire `forkCount`, `reuseForks`, and separate IDE processes affect reuse. Running two classes in two separate Maven commands usually will not reproduce threshold skips across runs. To observe threshold behavior, you need the same cache key in the **same JVM**.

### 16.5. Interleaved Parallel Test Logs

When classes run in parallel, the "first failure in the whole log file" may belong to a different context key. Group by:
- Config class/test class.
- Active profile.
- Properties/bean overrides.
- Exception stack trace.
- Thread/log timestamp.
- Context cache `DEBUG` statistics.

Then find the first failure **within that specific key group**, rather than guessing from arbitrary log order.

## 17. Reading Maven/Surefire/JUnit Results Properly

### 17.1. Error vs Failure

A JUnit **error** typically denotes an unexpected exception outside an assertion, such as failed context setup. An assertion expected/actual mismatch is typically reported as a **failure**. Surefire XML schema/runner details vary, so always read the exception type, message, and test stage instead of relying solely on error/failure counts.

### 17.2. Extracting Useful Evidence

Capture:
- `mvn -version`.
- Parent/BOM version.
- `-Dtest=...` selection.
- `-DtrimStackTrace=false` when full causes are needed.
- Full root cause and bean name.
- Context cache config/logs.
- Executed/skipped test counts.

Do not paste raw full `application.properties` if it holds secrets; redacted values suffice to diagnose precedence and config.

### 17.3. RerunFailures Does Not Cure Context Startup

Surefire `rerunFailingTestsCount` can retry failures, but for a missing bean every attempt still fails or generates more threshold messages. If an external service is flaky, a passing rerun can mask a readiness/timeout bug. Preserve the initial error in reports and investigate it.

### 17.4. Passing in Isolation Does Not Prove the Suite Is Fixed

Failures can depend on:
- Test execution order.
- Shared `ContextCache`.
- Static beans.
- Class-level Testcontainers lifetimes.
- External DB state.
- Parallel mocks.
- CI env vars.
- Dynamic ports.
- Scheduled/asynchronous startup tasks.

After fixing, run the exact failing suite (same test scope, profile, and fork settings) and then the broader suite. If only a narrow test passed, state that exact scope clearly.

### 17.5. Keep Deliberate Repro Tests Out of Default CI

An intentional-failure `*ReproducerIT` should:
- Have a clear name/README noting "expected startup failure."
- Be run via `-Dtest` only when needed.
- Stay outside Surefire default includes.
- Not accidentally be picked up by Failsafe `integration-test/verify` if CI configures `*IT` patterns—unless that job specifically **expects a non-zero exit code**.
- If a green CI regression test for a failure path is wanted, convert it to `ApplicationContextRunner` with programmatic assertions.

## 18. Common Root Cause Map

| Root Signal | Underlying Branch to Investigate | Best Verification |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Scan/profile/slice/conditional/import | Check actual bean definitions; add proper mock/import |
| `NoUniqueBeanDefinitionException` | Multiple candidates | `@Qualifier`/`@Primary`/conditional |
| `BeanCurrentlyInCreationException` | Circular dependency | Draw graph/refactor |
| `ConfigurationPropertiesBindException` | Invalid value/format/validation | Property origin/rejected key |
| `Could not resolve placeholder` | Missing property/secret | Test profile/config data |
| `Failed to configure a DataSource` | Missing URL/embedded DB/driver | Datasource auto-config/driver |
| `Communications link failure` / `Connection refused` | DB/network/container not ready | URL/host/mapped port/readiness |
| `FlywayMigrateException` | Migration/schema SQL | Migration history/first failed script |
| `BeanCreationException: entityManagerFactory` | ORM mapping/schema/dialect | Hibernate root exception |
| `WebServerException: Port already in use` | Server config | `RANDOM_PORT`/`NONE` or free port |
| `ClassNotFoundException` | Missing from classpath | Dependency scope/tree |
| `NoSuchMethodError` | Dependency binary mismatch | BOM/dependency tree |
| `APPLICATION FAILED TO START` | Boot analyzer output | Read Description/Action + causes |
| `failure threshold exceeded` | Earlier load failed for same key | Find first full attempt |
| `Context is no longer active` | Context closed/dirty while in use | `@DirtiesContext`/parallel tests |
| `Docker environment not found` | Testcontainers runtime | Docker daemon/CI permissions |
| `Port 0?`/request errors after startup | Context may be fine; request layer | HTTP config/MockMvc/`webEnvironment` |
| `OutOfMemoryError` at boot | Resource pressure | Heap/memory leak/context count |

For every signal, record the exact **class name, bean name, or property key**. Never apply the fix for error A blindly to every failure wrapped in `Failed to load ApplicationContext`.

## 19. Diagnostic Anti-Patterns

### 19.1. Inspecting Only the Last Test's Exception

The last test may simply show `failure threshold exceeded`. Trace back to the first attempt for that context key instead of treating the skip message as the root cause.

### 19.2. Grabbing the Last "Caused by" and Ignoring the Rest of the Chain

The deepest `ConnectException` tells you the connection was refused, yet the wrong URL may have come from a higher-level profile override. Keep the whole chain and property origin.

### 19.3. Disabling Every @AutoConfiguration Just to Start the Context

Excluding `DataSourceAutoConfiguration`, Security auto-config, or Flyway can turn tests green while diverging from production behavior. Only exclude them in slices that **intentionally do not need** that integration.

### 19.4. Enabling Lazy Initialization to Hide Errors

`spring.main.lazy-initialization=true` defers creating broken beans until the first request/call. It does not fix missing dependencies or bad config, and a passing context load becomes false confidence. When fail-fast startup is required, keep eager init and validation.

### 19.5. Mocking Every Collaborator

A full integration test that mocks away missing services, repositories, or DB clients stops testing the broken configuration. Mock only at accepted boundaries; keep real adapters when testing integration startup.

### 19.6. @DirtiesContext on Every Class

It destroys cache reuse, slows the suite down, and does not fix a missing bean or bad property. Use it only when context state genuinely gets dirtied.

### 19.7. Setting a Huge Failure Threshold Permanently in CI

This forces Spring to repeatedly attempt loading a broken context. Startup logs bloat while the bug remains, slowing the suite and hammering external resources.

### 19.8. Increasing Timeouts Regardless of Root Cause

A database port that is not listening will not be fixed by a 120-second timeout, nor will a missing bean. Tune timeouts only when evidence shows slow backend readiness or CI resource contention.

### 19.9. Copying application-prod.yml into Tests Unchecked

It can point tests at production DBs/brokers, leak credentials, or trigger scheduled jobs. Test configs must isolate external resources and follow secret management rules.

### 19.10. Running Intentional-Failure Reproducers in the Default Suite

If `*ReproducerIT` gets picked up by Failsafe discovery, CI turns red unexpectedly. Keep green integration tests separate from manual red reproducers, and use `ApplicationContextRunner` for regression tests.

### 19.11. Using Random Dependency Versions

The Spring Boot BOM aligns Spring Framework, Spring Test, Jackson, and Mockito. Arbitrary overrides can introduce `NoSuchMethodError` and trigger context failures far from the real cause.

### 19.12. Checking Only Maven's Exit Code

A build can pass because tests were skipped, disabled, or rerun. Inspect executed counts, failures/errors/skips, and Surefire reports.

### 19.13. Changing Properties That Alter the Cache Key Before Comparing Thresholds

Adding `debug=true` can create a different cache key; you just changed the experiment. Use it to inspect conditions, then switch back to the exact original config to confirm the failure.

### 19.14. Deleting All of ~/.m2

Unless you have evidence of dependency corruption such as checksum or download errors, wiping the Maven cache on a slice `NoSuchBeanDefinitionException` wastes time and accomplishes nothing.

### 19.15. Calling Any "Connection refused" a Network Outage

With Testcontainers, a per-class `@Container` might have stopped while the Spring context remained cached—a lifecycle mismatch. Check container ID, mapped port, and client lifecycle before blaming the CI network.

### 19.16. Wiping the Test Database Immediately After a Context Failure

The database may hold state needed for investigation, and global cleanup can break concurrent tests. Use isolated test schemas, targeted cleanup, and sanitized logs.

### 19.17. Patching Code with @Autowired(required=false)

Making a required dependency nullable lets the bean construct, only to cause NPEs or silent bugs after startup. Use optional dependencies only when fallback behavior is designed and tested.

### 19.18. Guessing the Root Cause from Alphabetical Class Names

`FirstReproducerIT` is not guaranteed to run before `SecondReproducerIT`. Surefire/JUnit execution order can vary. Rely on logs, not names.

### 19.19. Adding Test-Level @Transactional to Fix Startup Errors

Method-level transactions on JUnit tests are not active during context bootstrap. They cannot fix `BeanCreationException` or DataSource config errors. Diagnose runtime DB/rollback issues separately.

### 19.20. Skipping the Full Suite After a Fix

Fixing an MVC slice might turn one test green while a full-context integration profile is still missing `AuditSink`. Fix and verify each relevant scope responsibly.

## 20. Checklist When Receiving a "Failed to load ApplicationContext" Ticket

- [ ] Recorded the exact test class/method and test command?
- [ ] Identified whether failure occurs before or inside the test body?
- [ ] Collected full stdout/stderr and Surefire reports?
- [ ] Identified the exact failing Spring context cache key?
- [ ] Located the **first startup attempt** for that key?
- [ ] Checked for threshold exceeded messages and skipped past them to the real root cause?
- [ ] Read the entire `Caused by` chain?
- [ ] Identified the **actionable cause**, not just the deepest technical exception?
- [ ] Checked whether Spring Boot `FailureAnalyzer` Description/Action applies?
- [ ] Checked active profiles, test properties, and `Environment` precedence?
- [ ] Confirmed test scope: `@SpringBootTest` vs slice?
- [ ] Verified whether a bean is truly missing vs excluded by slice/conditional/profile?
- [ ] Distinguished `NoSuchBean` from `NoUniqueBean`?
- [ ] Checked for bean cycles or unintended configuration overrides?
- [ ] Verified `@ConfigurationProperties` registration, binding, and validation?
- [ ] Checked classpath, BOM alignment, and JDK versions?
- [ ] For DB errors, checked URL, driver, redacted credentials, and readiness?
- [ ] For Testcontainers, aligned container lifetime with context cache?
- [ ] For Flyway/Liquibase errors, read the first failing migration?
- [ ] Used `DEBUG` condition evaluation reports selectively when helpful?
- [ ] Avoided treating all negative condition matches as errors?
- [ ] Run a narrow reproducer with full stack trace?
- [ ] Avoided changing 5 settings simultaneously?
- [ ] Fixed the right layer instead of mocking/disabling everything?
- [ ] Added a green regression test covering the root cause?
- [ ] Kept intentional-failure repros out of default tests?
- [ ] Refused to raise the failure threshold as a permanent workaround?
- [ ] Refused to enable lazy initialization to mask startup bugs?
- [ ] Re-run the **failing suite** and verified executed/skipped/flaky counts?
- [ ] Ensured CI artifacts do not leak credentials or PII?
- [ ] Written a conclusion backed by evidence and remaining limitations?

## 21. Hands-On Exercises

1. Run `mvn clean test` on the lab, note the 8 expected methods, and remember this is an expectation rather than an observed run in this document.
2. Run `MissingSinkFirstReproducerIT` and locate the outer `Failed to load ApplicationContext`.
3. Trace down to `NoSuchBeanDefinitionException: AuditSink` in the reproducer.
4. Run both `MissingSink*IT` classes in one Maven invocation; identify which class/attempt logged the first full failure and which hit the threshold skip.
5. Set `spring.test.context.failure.threshold=1000000` once; contrast repeated startup attempts with an actual fix.
6. Restore the threshold to default; explain why fail-fast policy helps.
7. Run `BadBindingReproducerIT`, recording the rejected property names and validation constraints.
8. Fix endpoint/attempts to run `PropertiesOverrideHealthyTest` without disabling `@Validated`.
9. Run `MissingMvcDependencyReproducerIT` and then `MvcSliceHealthyTest`; explain `@MockitoBean`.
10. Temporarily remove `@MockitoBean` from the healthy MVC test on a study branch to confirm the failure returns.
11. Add `@Profile("integration")` to `ConsoleAuditSink` and run under profile `test`; diagnose the new missing bean.
12. Add `@ConditionalOnProperty` to the sink and use the condition report to locate the negative match.
13. Create two `AuditSink` implementations and distinguish `NoUniqueBeanDefinitionException` from a missing bean.
14. Add a nested `@Configuration` to a test and observe how it can accidentally replace the application config.
15. Compare nested `@TestConfiguration` and `@Import` for adding collaborators.
16. Use `ApplicationContextRunner` to build a context missing a bean and assert the root cause while JUnit PASSES.
17. Use the runner with a bean factory throwing `IllegalStateException`; verify the marker in the deepest cause.
18. Run diagnostics with `debug=true` and locate relevant entries in `ConditionEvaluationReport`.
19. Set `demo.client.attempts` to an unparseable string; distinguish conversion errors from Bean Validation.
20. Add a `@ConfigurationProperties` class without registering it, and confirm it is not a bind validation failure.
21. Create a `@SpringBootTest(webEnvironment=RANDOM_PORT)` test with the valid main app; distinguish port startup from `MOCK`/`NONE`.
22. Start a server on a fixed port already in use; inspect the Boot `FailureAnalyzer` and fix with random port where appropriate.
23. Add a JDBC starter without URL/driver in a scratch module and inspect the DataSource failure analyzer.
24. Write a Spring Boot Testcontainers variant with a PostgreSQL service connection; induce a failure when Docker is unavailable and classify it.
25. Create a broken SQL migration in a dedicated test DB; locate the first failing migration without disabling Flyway.
26. Have test A stop a per-class `@Container` while test B reuses the cached context, observe the stale endpoint, and refactor to a managed container bean.
27. Run in CI with 2 Surefire forks; explain why failure counts/caches are not shared across JVMs.
28. Enable parallel classes and filter startup logs by context key instead of the first line in the file.
29. Induce a `NoSuchMethodError` by overriding a Spring module version, then restore BOM dependency alignment.
30. Write a one-page bug report containing startup attempt, `BeanCreationException` chain, root reason, fix, and regression test evidence.

## 22. Quick Decision Table

| Question | If Yes | Action |
| --- | --- | --- |
| Is `failure threshold exceeded` present? | Yes | Find the first startup exception for the same cache key |
| Did the test method body run? | No | Focus on TestContext/beans/env/bootstrap |
| Is the deepest cause a missing bean? | Yes | Determine if excluded vs unregistered |
| Is the test using an MVC/JPA slice? | Yes | Fix collaborator via slice/mock/targeted import |
| Is there a property bind/validation error? | Yes | Find source/value/reason and fix config |
| Is DB/broker connection refused? | Yes | Check endpoint, readiness, container lifecycle |
| Is there a Flyway/Hibernate failure? | Yes | Check first failing migration/mapping/schema |
| Is there a `ClassNotFound`/`NoSuchMethod`? | Yes | Inspect dependency tree/BOM/JDK |
| Does it fail only in the full suite? | Yes | Check cache key, order/parallelism, shared state |
| Does it fail only after class A? | Yes | Check `@DirtiesContext`, container stop, mock reset |
| Did `ApplicationContextRunner` pass? | Yes | It proves a narrow failure branch, not the full app |
| Did one test PASS after fixing? | Yes | Re-run the exact failing suite and verify reports |
| Did a debug property change the cache key? | Yes | Re-verify on the original config |
| Is the build green only via skipped tests? | Yes | Reject as a QA pass |

## 23. Team Diagnostic Report Template

A useful report documents both evidence and boundaries:

~~~text
Symptom:
  SpringBootTest fails before @Test body.
  Several subsequent classes show failure threshold exceeded.

First failing context key:
  classes=[...], activeProfiles=[test], customizers=[...]
  first startup failure was in ...Test at ...

Exception chain:
  IllegalStateException Failed to load ApplicationContext
    -> UnsatisfiedDependencyException auditService
      -> NoSuchBeanDefinitionException AuditSink

Root diagnosis:
  @WebMvcTest was limited to MVC beans and did not provide AuditService.
  The production full application has a valid AuditSink bean;
  the defect was the test slice wiring, not a production dependency.

Fix:
  Add @MockitoBean AuditService in the MVC slice.
  Keep full-context integration test for real AuditService -> AuditSink.

Validation:
  Run narrow MvcSliceHealthyTest, then full affected suite.
  Record executed/failed/skipped/flaky counts and context cache data.

Caveat:
  Mockito collaborator proves controller contract only, not real sink delivery.
~~~

This is a **formatting template**, not output from an actual CI run. Never include usernames, passwords, tokens, or sensitive JDBC connection strings in reports.

## 24. Conclusion

`Failed to load ApplicationContext` is the **starting point of an investigation**, not an explanation of the root cause. In Spring Framework 6.2, an initial failure can be hidden behind **context failure threshold (1) exceeded** messages on subsequent tests sharing the same cache key. To diagnose accurately, locate the **chronologically first attempt**, follow `Caused by`, pinpoint the broken bean, property, or external resource, and separate **test scope** errors from **production application** bugs.

Use `FailureAnalyzer`, `ConditionEvaluationReport`, targeted Maven `-Dtest` runs, and `ApplicationContextRunner` to gather evidence. Never inflate timeouts or thresholds, sprinkle `@DirtiesContext`, mock every dependency, or enable lazy initialization just to hide failures. A trustworthy fix modifies the **specific root cause**, re-runs the original failing test and suite, verifies actual JUnit executed counts, and adds a regression test at the right boundary.

## 25. Official Documentation

- Spring Framework 6.2 — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework 6.2 — Context Caching (cache keys, max size 32, LRU, JVM forks): https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.2 — TestContext Framework key abstractions: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/key-abstractions.html
- Spring Framework 6.2 — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework 6.2 — TestContext Parallel Test Execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.5.16 — SpringApplication Startup Failure / FailureAnalyzer / Debug Conditions: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5.16 — Testing Spring Boot Applications / @WebMvcTest / @MockitoBean: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 — ApplicationContextRunner / Auto-configuration tests: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5.16 — @ConfigurationProperties Validation / Externalized Config: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5.16 — Testcontainers and Service Connections: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Spring Boot 3.5.16 — Database Initialization: https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html
- Spring Boot 3.5.16 — Flyway/Liquibase and SQL databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Framework 6.2 — MockitoBean/MockitoSpyBean Test Bean Overrides: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Maven Surefire — Selecting Tests with -Dtest: https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html
- Maven Surefire — Understanding report files and test results: https://maven.apache.org/surefire/maven-surefire-plugin/examples/reporting.html
