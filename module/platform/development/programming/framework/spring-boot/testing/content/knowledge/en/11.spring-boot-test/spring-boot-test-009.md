# `ApplicationRunner`, `CommandLineRunner`, and their impact when `@SpringBootTest` loads an application

## 1. Real-world problem

A test only intends to verify a service or repository:

```java
@SpringBootTest
class OrderServiceTest {
    @Autowired OrderService service;

    @Test
    void calculatesTotal() {
        // Test order logic.
    }
}
```

Yet when the test starts up, the program may automatically run **data seeding**, **catalog sync**, **scheduled/startup jobs**, **API calls**, **cache clearing**, or **sending emails** before the `@Test` body even begins. The culprit can be a bean implementing `ApplicationRunner` or `CommandLineRunner`.

Here is the key point: **`@SpringBootTest` creates the `ApplicationContext` using `SpringApplication`. If a runner is a bean in that context and is not disabled, Spring Boot calls its `run(...)` method during startup — before test methods begin.** `webEnvironment = NONE` only disables the web environment; it **does not automatically disable startup runners**.

With production code having side effects, this can cause:

- Writing or deleting data outside test fixtures; seed data running multiple times.
- Calling HTTP partners, message brokers, or databases unavailable in CI.
- Tests failing at `Failed to load ApplicationContext`, before a single assertion executes.
- Slow suites due to data imports, index rebuilds, or warm-ups executing during context creation.
- Unstable test results because Spring TestContext **caches contexts**, not re-running runners before every test method.
- Data written at startup not being rolled back by `@Transactional` on test methods.

This lesson explains when and how runners are invoked, the differences between the two interfaces, how to test their real behavior, how to disable side effects intentionally, and safe design choices for Spring Boot.

## 2. Learning objectives

After this lesson, you will be able to:

1. Implement `ApplicationRunner`/`CommandLineRunner` using the right APIs, knowing they are **beans** discovered and invoked by Spring Boot.
2. Distinguish `ApplicationArguments` with parsed options from raw `String... args`.
3. Pinpoint the key sequence: **context refresh → `ApplicationStartedEvent` → runners → `ApplicationReadyEvent`**.
4. Explain why `@SpringBootTest` can execute startup code before `@BeforeEach` or `@Test`, even without calling the application's `main`.
5. Control runners with `@ConditionalOnProperty`, `@Profile`, or intentional `@Bean`/port design rather than brittle test hacks.
6. Unit-test a runner in isolation as a Java component and integration-test it when real `SpringApplication` starts up.
7. Recognize risks involving transactions, context caching, databases, HTTP, message brokers, ordering, retries/idempotency, and startup failures.
8. Build a Java 17 + Spring Boot 3.3 + JUnit Jupiter sample covering both **runners enabled** and **runners disabled**.

## 3. The two interfaces: similarities and differences

Both belong to package `org.springframework.boot` and define a single `run` method:

```java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}

public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

These are **simplified API signatures for explanation**, not interfaces you define yourself in the project. The real interfaces are provided by Spring Boot.

| Feature | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Signature | `run(ApplicationArguments args)` | `run(String... args)` |
| Input passed | Object holding raw args and parsed groups | Raw string array of arguments |
| Reading `--mode=verify` | `args.getOptionValues("mode")` | Parse strings manually or pass to a custom parser |
| Reading non-option `seed.csv` | `args.getNonOptionArgs()` | Scan `String[]` per program syntax |
| When to use | When option/non-option separation is needed clearly | Simple CLI handling or raw argument processing |
| How invoked | Spring Boot invokes bean at startup | Spring Boot invokes bean at startup |
| Ordering | `@Order` or `Ordered` | `@Order` or `Ordered` |
| Return/outcome | `void`, may throw exceptions | `void`, may throw exceptions |

Key methods of `ApplicationArguments`:

- `getSourceArgs()`: raw argument array passed to `SpringApplication.run`.
- `containsOption("mode")`: whether an option named `mode` exists.
- `getOptionValues("mode")`: list of values for the option; may return `null` when absent — check before using.
- `getOptionNames()`: set of option names.
- `getNonOptionArgs()`: list of non-option arguments.

For example, given `{"--mode=verify", "seed.csv"}`, option `mode` has value `verify`, while the non-option arg is `seed.csv`. `CommandLineRunner` receives `"--mode=verify"` and `"seed.csv"` sequentially. Do not confuse raw arguments with property values; `SpringApplication` can expose command-line options as a property source in `Environment`, but that is a related mechanism, not the definition of a runner.

### 3.1. Declaring a runner as a Spring bean

Two common ways:

**Approach A — `@Component` class:**

```java
@Component
class StartupReporter implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Startup reporter called");
    }
}
```

**Approach B — bean factory method:**

```java
@Configuration(proxyBeanMethods = false)
class RunnerConfiguration {
    @Bean
    CommandLineRunner reportOnStartup() {
        return args -> System.out.println("Startup command called");
    }
}
```

These two snippets are **standalone illustrations**; running them requires appropriate Spring imports and placement inside a scanned/imported context. With Approach B, the runner is a **bean returned from `@Bean`**, needing no `@Component` on the lambda.

If you merely instantiate `new StartupReporter()` outside Spring without registering it as a bean, Spring Boot **will not discover** that object to call `run`. Conversely, if you manually call `new AnnotationConfigApplicationContext(...)` in plain Spring Framework, having a bean implement a runner **does not mean** that context loader will call it; runner invocation lives inside `SpringApplication`.

## 4. Startup timeline: when are runners invoked?

In a standard `SpringApplication.run(...)` flow:

```text
SpringApplication.run(...)
     |
     +--> prepares Environment, reads args / profiles / properties
     |
     +--> creates and refreshes ApplicationContext
     |      +--> bean definitions / DI
     |      +--> @PostConstruct, bean init callbacks
     |      +--> @EventListener(ContextRefreshedEvent)
     |
     +--> ApplicationStartedEvent
     |      +--> LivenessState.CORRECT
     |
     +--> CALL RUNNERS
     |      +--> ApplicationRunner.run(ApplicationArguments)
     |      +--> CommandLineRunner.run(String...)
     |      +--> called per Ordered/@Order when specified
     |
     +--> ApplicationReadyEvent
     |      +--> ReadinessState.ACCEPTING_TRAFFIC
     |
     +--> SpringApplication.run(...) completes
```

This sequence lists key milestones per Spring Boot documentation, not every internal event/listener. A web server may **already be created/listening on its port** during refresh before `ApplicationReadyEvent`; do not interpret “ready event hasn't fired” as “no TCP request can arrive”. In deployment, configure readiness probes and external ports deliberately.

**Comparison with other extension points:**

| Extension Point | Execution Milestone | Meaning |
| --- | --- | --- |
| Singleton constructor/`@PostConstruct` | During bean creation, typically in refresh | Bean-internal initialization, not ideal for long network jobs |
| `ApplicationStartedEvent` | After refresh, before runners | Context is refreshed, runners have not run yet |
| `ApplicationRunner`/`CommandLineRunner` | After started, before ready | Startup tasks can use initialized beans |
| `ApplicationReadyEvent` | After runners finish | Signals Boot completed startup tasks successfully |
| JUnit `@BeforeEach` | Before each test method | With `@SpringBootTest`, typically **after** context startup runners |
| `@Test` | Executes test assertions/flow | Not the point where runners start |

If a runner **throws an unhandled exception** during this stage, `SpringApplication` can report startup failure, publish `ApplicationFailedEvent`, and `@SpringBootTest` fails during context creation. `ApplicationReadyEvent` is not published as a successful startup.

### 4.1. Do the two runner types run in two separate batches?

Do not assume Spring Boot **always invokes every `ApplicationRunner` first and then every `CommandLineRunner`**. The framework collects runner beans and applies ordering across objects implementing either interface. Use `@Order` or `Ordered` to enforce a specific order; if two runners have no declared order, never rely on class names, package scan order, or file appearance order.

```java
@Order(10)
@Component
class FirstRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // runs before @Order(20) runner if both are present.
    }
}

@Order(20)
@Component
class SecondRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // runs after FirstRunner.
    }
}
```

This is an **illustrative snippet**, not two runners to copy into the sample in section 6. If two tasks have a strict business dependency, consider coordinating them via **a single orchestrator** or explicit dependencies; relying solely on `@Order` numbers can become brittle to maintain.

## 5. Why can `@SpringBootTest` trigger runners?

`@SpringBootTest` uses Boot's test bootstrapper to create the context via `SpringApplication`. When `SpringApplication` runs, it gathers beans implementing `ApplicationRunner`/`CommandLineRunner` and invokes them during normal startup.

**Consequence:** a test needing only a Spring context can inadvertently:

- Run seed data before `@Test` begins.
- Hit the test database from repositories at startup.
- Fire outbound HTTP requests from startup jobs.
- Trigger multiple workflows unrequested by the test case.
- Fail before JUnit prepares fixtures in `@BeforeEach`.

Mechanically, this remains true even if you specify:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ServiceContextTest {
}
```

`NONE` **does not disable `SpringApplication`**; it disables the web environment. Therefore, never use `webEnvironment=NONE` as a “kill switch for all startup side effects”.

### 5.1. `useMainMethod = NEVER` does not disable runners

By default in Spring Boot 3.3, `@SpringBootTest` **does not directly call the application class's `public static void main(String[] args)` method**. It uses the configuration class to create the context via `SpringApplication`. This is the default `useMainMethod = NEVER`.

```java
@SpringBootTest(
    classes = DemoApplication.class,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER
)
class BootstrapTest {
}
```

Even though `main` is not called, **`SpringApplication` still runs to build the context, and eligible runner beans are still invoked**. If production `main` applies critical customizations like setting additional profiles/banners, you can pick `useMainMethod=WHEN_AVAILABLE` or `ALWAYS` per documentation, though that controls running custom `main` — **not** toggling runners.

| Setting | Calls `main`? | Context runners? |
| --- | --- | --- |
| Default `@SpringBootTest` | Does not call `main` directly | Yes, if beans match conditions and bootstrap succeeds |
| `useMainMethod=ALWAYS` | Requires `main` method and invokes it | Yes, during normal run |
| `webEnvironment=NONE` | Does not govern `main` | Still run, without a web environment |
| `@ContextConfiguration` with plain Spring Framework loader | Does not call Boot `main` | No `SpringApplication.callRunners` mechanism |
| `@WebMvcTest` | Loads MVC slice, not full Boot startup | Runners usually outside slice unless imported/registered specially |

**Note on slice tests:** Never assume `@WebMvcTest` guarantees runners can never be present. If you `@Import` a configuration containing a runner or widen component scanning, results depend on the context loader and exact scope. Keep runners out of slices that do not need them and verify loaded configurations.

### 5.2. `@Test` must not assume startup just occurred

TestContext caching reuses the same `ApplicationContext` across multiple classes/methods sharing configuration. Runners execute when **`SpringApplication` builds a new context**, not every time JUnit starts a test method.

Consequently:

- On a context cache hit, runners may **have already run for an earlier test class**.
- On a different cache key due to profiles/properties/mocks, a new context starts and runners **run again**.
- With `@DirtiesContext` or another JVM fork, the context may reload.
- Having `@Transactional` on a test does not automatically wrap startup runners in a transaction just because the test is called an integration test.

Never write tests assuming “runners ran exactly once for the whole suite”. Design runners to be **idempotent** if side effects must be unique, and use isolated test data.

## 6. Complete example: Java 17, Spring Boot 3.3.0, JUnit Jupiter

This example focuses on **startup runners and their impact when loading the application**. Two runners call neither a database nor a network; they record into an in-memory audit bean so tests can observe order and arguments. All runners are **property-gated**; when disabled, they are not registered as beans.

**Safe design choice:** `app.startup.enabled` must be `true` for both runners to exist. If the property is absent, they do not run. This prevents accidentally triggering tasks in CI or local tests unless explicitly enabled.

### 6.1. File structure

```text
runner-test-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── RunnerDemoApplication.java
    │   ├── StartupAudit.java
    │   ├── ArgsStartupRunner.java
    │   └── CliStartupRunner.java
    └── test/java/example/
        ├── ArgsStartupRunnerUnitTest.java
        ├── CliStartupRunnerUnitTest.java
        ├── RunnersEnabledBootTest.java
        └── RunnersDisabledBootTest.java
```

### 6.2. Gradle build

**`settings.gradle`:**

```groovy
rootProject.name = 'runner-test-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a complete build for the example. Spring Boot 3.3.0 is a fixed baseline to avoid mixing APIs across lines. In real projects, use an approved Spring Boot patch release and compatible Gradle wrapper. No `spring-boot-starter-web`, H2, database, or Docker is needed.

### 6.3. Main application

**`src/main/java/example/RunnerDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RunnerDemoApplication.class, args);
    }
}
```

`main` starts the app via `SpringApplication.run`. The Spring Boot tests below do not necessarily invoke `main`, yet still use `SpringApplication` to create the context.

### 6.4. Bean to safely record ordering

**`src/main/java/example/StartupAudit.java`:**

```java
package example;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class StartupAudit {
    private final CopyOnWriteArrayList<String> events =
            new CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
```

Audit events reside in memory per context, without writing files/DBs or calling external services. `CopyOnWriteArrayList` keeps recording and taking snapshots stable in the demo; it is not a replacement for transactional/outbox logging in production apps.

### 6.5. `ApplicationRunner` reading parsed arguments

**`src/main/java/example/ArgsStartupRunner.java`:**

```java
package example;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
@ConditionalOnProperty(
        prefix = "app.startup",
        name = "enabled",
        havingValue = "true"
)
public class ArgsStartupRunner implements ApplicationRunner {
    private final StartupAudit audit;

    public ArgsStartupRunner(StartupAudit audit) {
        this.audit = audit;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> values = args.getOptionValues("mode");
        String mode = values == null || values.isEmpty()
                ? "none" : values.get(0);

        String files = String.join(",", args.getNonOptionArgs());
        audit.record("application:mode=" + mode + ";files=" + files);
    }
}
```

When Spring receives `--mode=verify seed.csv`, `ApplicationArguments` parses:

- `getOptionValues("mode")` → list containing `"verify"`.
- `getNonOptionArgs()` → `["seed.csv"]`.
- Audit records `application:mode=verify;files=seed.csv`.

Because `matchIfMissing=true` is not set, an absent property **does not satisfy** `havingValue="true"`. This is **opt-in**: startup tasks only run when explicitly enabled.

### 6.6. `CommandLineRunner` receiving raw args

**`src/main/java/example/CliStartupRunner.java`:**

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
@ConditionalOnProperty(
        prefix = "app.startup",
        name = "enabled",
        havingValue = "true"
)
public class CliStartupRunner implements CommandLineRunner {
    private final StartupAudit audit;

    public CliStartupRunner(StartupAudit audit) {
        this.audit = audit;
    }

    @Override
    public void run(String... args) {
        audit.record("command:args=" + String.join("|", args));
    }
}
```

With the same args, audit records `command:args=--mode=verify|seed.csv`. `@Order(20)` paired with `@Order(10)` on the earlier runner gives assertions a deterministic order. **Both runner types are sorted together by Spring Boot's ordering**, not because `ApplicationRunner` always precedes `CommandLineRunner`.

### 6.7. Unit test: invoking `ApplicationRunner.run` without Spring

**`src/test/java/example/ArgsStartupRunnerUnitTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ArgsStartupRunnerUnitTest {
    @Test
    void parsesOptionAndNonOptionArgs() {
        StartupAudit audit = new StartupAudit();
        ArgsStartupRunner runner = new ArgsStartupRunner(audit);

        runner.run(new DefaultApplicationArguments(
                "--mode=verify", "seed.csv"));

        assertEquals(
                List.of("application:mode=verify;files=seed.csv"),
                audit.snapshot());
    }
}
```

Here `new` instantiates the runner and audit; **no `@SpringBootTest`, no IoC container, no auto-startup**. The test invokes `runner.run` explicitly; it proves argument parsing and audit output of the runner, yet **does not** prove `SpringApplication` invokes the runner during bootstrap.

### 6.8. Unit test: checking raw arguments

**`src/test/java/example/CliStartupRunnerUnitTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CliStartupRunnerUnitTest {
    @Test
    void receivesRawCommandLineArguments() {
        StartupAudit audit = new StartupAudit();
        CliStartupRunner runner = new CliStartupRunner(audit);

        runner.run("--mode=verify", "seed.csv");

        assertEquals(
                List.of("command:args=--mode=verify|seed.csv"),
                audit.snapshot());
    }
}
```

This pure test does not care whether Spring discovers `@Component` or whether the property toggles it on/off; it solely verifies the code inside `run`. That is a different layer of evidence from the integration tests below.

### 6.9. `@SpringBootTest` with runners enabled

**`src/test/java/example/RunnersEnabledBootTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = RunnerDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.startup.enabled=true",
        args = {"--mode=verify", "seed.csv"}
)
class RunnersEnabledBootTest {
    @Autowired
    StartupAudit audit;

    @Test
    void executesBothRunnersDuringContextStartupInOrder() {
        assertEquals(
                List.of(
                        "application:mode=verify;files=seed.csv",
                        "command:args=--mode=verify|seed.csv"
                ),
                audit.snapshot());
    }
}
```

This is the centerpiece test for the topic:

1. When JUnit prepares the Spring test context, Boot uses `SpringApplication`.
2. Property `app.startup.enabled=true` enables both runner beans.
3. Boot invokes the runners during startup, in order 10 then 20.
4. By the time `@Test` begins, `audit` **already holds both records**.
5. The assertion verifies observed side effects directly, **without calling `runner.run(...)` a second time inside the test**.

This test opens no HTTP port because `webEnvironment=NONE`. If someone thought `NONE` disables runners, this test corrects that misconception.

### 6.10. `@SpringBootTest` with runners disabled

**`src/test/java/example/RunnersDisabledBootTest.java`:**

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(
        classes = RunnerDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "app.startup.enabled=false",
        args = {"--mode=verify", "seed.csv"}
)
class RunnersDisabledBootTest {
    @Autowired
    StartupAudit audit;

    @Autowired
    ApplicationContext context;

    @Test
    void doesNotCreateOrRunDisabledRunnerBeans() {
        assertEquals(List.of(), audit.snapshot());
        assertFalse(context.containsBean("argsStartupRunner"));
        assertFalse(context.containsBean("cliStartupRunner"));
    }
}
```

When the property equals false, `@ConditionalOnProperty` **skips registering the runner beans**. Therefore `SpringApplication` finds neither runner to invoke. The test proves no startup side effects landed in `StartupAudit` and the corresponding bean names do not exist in the context.

Note the differences among:

- **Not creating the runner bean** via condition/profile: `SpringApplication` cannot call it.
- **Creating the runner yet returning early inside `run`**: the bean is still created and `run` is still called, merely skipping its body's work.
- **Mocking the runner bean**: `SpringApplication` can still call `run` on the mock (no-op) at startup, depending on the bean override; not the same as conditional bean exclusion.

### 6.11. Running the example

Once you have a Gradle Wrapper compatible with Boot 3.3 and Java 17:

```bash
./gradlew test
./gradlew test --tests example.ArgsStartupRunnerUnitTest
./gradlew test --tests example.CliStartupRunnerUnitTest
./gradlew test --tests example.RunnersEnabledBootTest
./gradlew test --tests example.RunnersDisabledBootTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.RunnersEnabledBootTest
```

Expected outcome: **4 test methods pass**, consisting of 2 unit tests and 2 Boot integration tests. The build tool prints `BUILD SUCCESSFUL` when no tasks fail; there is no business-generated stdout (audits stay in memory), though Spring Boot prints startup logs per configuration.

**Cache note:** Both Boot tests set different `app.startup.enabled` values, so they produce different context configs and do not share the same cache key. Consequently, the enabled test observes both startup events and the disabled test sees an empty audit regardless of class execution order.

## 7. Ways to control runners in tests

### 7.1. Preferred approach for heavy side effects: opt-in property

If a runner writes data or calls external services, gate its activation **explicitly**:

```java
@Component
@ConditionalOnProperty(
        prefix = "app.import",
        name = "enabled",
        havingValue = "true"
)
class CatalogImportRunner implements ApplicationRunner {
    // Only registered if app.import.enabled=true.
}
```

In production deployments intending to run the job, set `app.import.enabled=true`. In tests that do not need the job, leave it absent/false or set explicitly:

```java
@SpringBootTest(
        properties = "app.import.enabled=false"
)
class CatalogServiceTest {
    // ...
}
```

If production must enable it by default for operational requirements, you could use `matchIfMissing=true`, though then **every test omitting the flag risks running the runner**. The production/test contract must be chosen deliberately rather than applying one setting blindly to all projects.

### 7.2. Using profiles when test environments are standardized

```java
@Component
@Profile("!test")
class StartupJob implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Task runs only when the test profile is inactive.
    }
}
```

And in tests:

```java
@SpringBootTest
@ActiveProfiles("test")
class ServiceTest {
}
```

These are **two illustrative config fragments**. `@Profile("!test")` only evaluates **active profiles**; it does not know whether code is executed by JUnit or CI. If a test forgets `@ActiveProfiles("test")`, the runner still executes; if production accidentally activates profile `test`, the runner vanishes. Specialized tests aiming to **test the runner itself** must enable conditions via another configuration.

**When to choose properties vs. profiles?**

| Situation | Common Choice |
| --- | --- |
| Individual job toggled independently | `@ConditionalOnProperty` |
| Group of components belonging to specific environments | `@Profile` |
| Test needs to explicitly enable a runner | Explicit test properties |
| Runner dangerous if triggered unintentionally | Opt-in flag plus deployment check |
| Need to test runner without loading Spring | Unit test calling `run` manually |
| Need to prove Boot invokes the runner | `@SpringBootTest` enabling flag and observing effect |

### 7.3. Conditioning directly on `@Bean`

A runner can also be supplied via a configuration factory method:

```java
@Configuration(proxyBeanMethods = false)
class JobConfiguration {
    @Bean
    @ConditionalOnProperty(
            name = "app.jobs.rebuild-index",
            havingValue = "true"
    )
    ApplicationRunner rebuildIndex(IndexService service) {
        return args -> service.rebuild();
    }
}
```

This is an **illustrative snippet**, requiring `IndexService` and imports. Putting the condition directly on the **bean definition** avoids running side effects in a runner constructor. If `IndexService` itself has startup side effects in its constructor/`@PostConstruct`, disabling the runner alone may not stop the other bean from being instantiated; guard the actual site of the side effect.

### 7.4. Guard inside `run`: usable yet distinct from disabling the bean

Another option is injecting a property and returning early:

```java
@Override
public void run(ApplicationArguments args) {
    if (!enabled) {
        return;
    }
    performJob();
}
```

This is only an **abbreviated illustrative snippet**, requiring field `enabled` and `performJob()`. The bean is still instantiated and `run` is still called; if constructors or init callbacks do risky work, the guard runs too late. For tasks unneeded in tests, excluding the bean via condition/profile is usually cleaner.

### 7.5. Does mocking a runner stop it from running?

In Spring Boot 3.x, you may see tests using `@MockBean` to swap a concrete runner for a mock. That can make the mock's `run` a no-op, with caveats:

- Which bean gets replaced depends on type/name/qualifier; if multiple runners exist, others still run.
- `SpringApplication` can still **invoke the mocked runner**; the mock merely skips original code.
- Adding mocks/spies alters the Spring TestContext cache key and can spawn extra contexts.
- Stubbing in `@BeforeEach` or `@Test` runs **after** startup runners were already called; you cannot retroactively control calls that already happened.
- Spring Boot 3.4+ favors Framework's `@MockitoBean` over the legacy annotation, and Boot 4 drops the legacy API.

Therefore, **do not treat bean mocking as a global switch for turning off startup jobs**. Properties, profiles, and dedicated startup job design are clearer and more reliable.

## 8. Testing runners across three levels

### 8.1. Unit-testing `run` logic

Construct the runner manually, inject fake dependencies, and call `run`:

```java
StartupAudit audit = new StartupAudit();
ApplicationRunner runner = new ArgsStartupRunner(audit);

runner.run(new DefaultApplicationArguments(
        "--mode=verify", "seed.csv"));

assertEquals(
        List.of("application:mode=verify;files=seed.csv"),
        audit.snapshot());
```

Class definitions for this snippet are complete in section 6; in a project you need JUnit/Boot imports. It tests **parsing logic and runner outcomes**, without verifying whether `SpringApplication` discovers the bean.

### 8.2. Boot integration test for startup

Use `@SpringBootTest` with the enabled flag and an independent audit bean like `RunnersEnabledBootTest`. The test must assert effects that **occurred during bootstrap**. Never call `run` again in the Act section — calling it again tests something else and can cause double side effects.

### 8.3. Integration tests with databases/message brokers

If a real runner imports data into a DB or publishes events, an in-memory audit is **insufficient**. Depending on the contract, use:

- Testcontainers with the same database engine as production to assert records/constraints/transactions.
- Embedded/test brokers or containerized brokers to assert events/payloads and idempotency.
- HTTP mock servers for outbound requests to verify methods/paths/headers/bodies.
- Fake ports in unit tests to verify outgoing commands, paired with integration tests at protocol boundaries where needed.

Mind setup order: seeding data via `@BeforeEach`, default `@Sql` before-test-method scripts, or stubs inside `@Test` all run **too late** for a runner executing during **context bootstrap**. Prepare data needed by startup runners **before context load** using migrations, test configurations, container initialization, or appropriate fixture setup.

## 9. Multiple runners: ordering and real dependencies

Spring Boot supports `@Order` and `Ordered`. If you want to run sequentially:

1. Load reference data.
2. Build search index.
3. Publish ready report.

You could write three runners with distinct orders, yet consider:

- What should happen if the first runner fails? Later runners cannot blindly assume data exists.
- With retries or multiple replicas, in-process ordering does not guarantee system-wide single execution.
- `@Order` only specifies **invocation order inside one startup process**, not transactions or distributed coordination.
- When you need an atomic business sequence or checkpoints, a **single orchestrator runner** calling explicit steps is easier to test.
- Never rely on ordering between two beans with equal `@Order`; assign distinct orders or treat order as non-contractual.
- `@DependsOn` governs **bean initialization order**, not a general substitute for `@Order` ordering runner callbacks.

A clear representation:

```java
@Component
class StartupOrchestrator implements ApplicationRunner {
    private final ReferenceLoader loader;
    private final IndexBuilder index;
    private final StartupPublisher publisher;

    StartupOrchestrator(
            ReferenceLoader loader,
            IndexBuilder index,
            StartupPublisher publisher) {
        this.loader = loader;
        this.index = index;
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        loader.load();
        index.rebuild();
        publisher.published();
    }
}
```

This is an **illustrative skeleton**, needing matching interfaces and beans; it is not part of the runnable project in section 6. Orchestration tests can mock/fake the ports to assert call order and outcomes, while Boot integration tests verify the orchestrator runs at startup.

## 10. Context caching: why do runners sometimes run once, sometimes multiple times?

Spring TestContext maintains a **JVM-static context cache**. When two tests share identical configuration, Spring can reuse `ApplicationContext`. Then runners are **not re-invoked by `SpringApplication` merely because JUnit begins a new class or method**.

Illustration:

```text
Test A: @SpringBootTest(properties="app.startup.enabled=true")
     |
     +--> cache miss -> builds context A -> runners execute

Test B: @SpringBootTest(properties="app.startup.enabled=true")
     |
     +--> cache hit  -> reuses context A -> runners do not re-run

Test C: @SpringBootTest(properties="app.startup.enabled=false")
     |
     +--> different cache key -> builds context B -> runners absent

Test D: @DirtiesContext or different JVM fork
     |
     +--> may build new context -> enabled runners execute again
```

Factors that change cache keys include: application/configuration classes, active profiles, inline properties, context customizers (mocks/dynamic properties), initializers, context loaders, and context hierarchies.

**Never deduce runner invocation count from `@Test` method count.** In large suites, runners can execute multiple times across distinct context keys. When side effects touch shared data, this causes duplicate rows, duplicate events, or double charges if code lacks idempotency.

### 10.1. Passes alone, fails in the suite

Typical scenario:

- Test A builds the context; runner imports data.
- Test B reuses the context assuming the runner just executed, yet Test A deleted that state.
- Test C sets another property, builds a new context, and re-imports data into the shared DB.
- Test D runs in another JVM fork without sharing the cache, so the runner executes again.

Fix: use isolated test fixtures, idempotent jobs, separate DBs/schemas, explicit property guards, and scoped assertions. Do not “fix” this by slapping `@DirtiesContext` on every test, which makes runners fire **even more often**.

### 10.2. `@DirtiesContext` is not a rollback command

`@DirtiesContext` closes/evicts the context from cache. It does not delete rows committed to a database or undo emails/events already sent. For runners with side effects, overusing this annotation increases the risk of jobs re-executing as contexts recreate.

## 11. Transactions and data modified before tests

`@Transactional` on a `@SpringBootTest` usually opens a **test-managed transaction** around the test method with a matching transaction manager; by default it rolls back. Yet runners execute during `SpringApplication` startup, **before any test-method transaction opens**.

False assumption example:

```java
@SpringBootTest
@Transactional
class ImportJobTest {
    @Test
    void testImport() {
        // Cannot assume startup import work
        // will roll back with this method's transaction.
    }
}
```

This is an **illustrative snippet**, requiring an app with a transaction manager and imports. If the runner calls a service/repository with its own `@Transactional`, writes commit inside the startup operation's transaction. Rolling back the test method **does not undo** that commit.

Similarly, under `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the HTTP server runs on a different thread/transaction. Even when the test method rolls back, server-side transactions do not roll back automatically.

**Practical solutions:**

1. Runners must never write to a production DB from tests: use separate test profiles/properties and datasources.
2. When verifying a runner's DB writes, provision an ephemeral DB, execute startup once in a fresh context, and assert rows.
3. Use idempotency keys, unique constraints, or business upserts to prevent duplicates across reruns.
4. Clean up deliberately with transactions/scripts; never assume test-managed rollback covers startup.
5. Never run such tests in parallel against shared databases/resources without explicit isolation.

### 11.1. `@Sql` arrives too late

`@Sql` can set up fixtures before test methods. However, a runner reading the DB during context bootstrap executes before those fixtures exist. Design pre-startup data preparation at the right milestone: migrations, database image/init scripts, Testcontainers setup, or properly ordered bean test configuration. Do not put a SQL script on `@BeforeEach` expecting a startup runner that already ran to see it.

## 12. Mocks and stubbing: distinguish setup time from startup time

A classic failure when startup runners use remote gateways:

```java
@SpringBootTest
class StartupTest {
    @MockBean RemoteGateway gateway;

    @BeforeEach
    void stub() {
        when(gateway.fetch()).thenReturn("ok");
    }
}
```

This is an **illustrative skeleton for Spring Boot 3.x**, omitting `RemoteGateway` and `@Test`. If the runner calls `gateway.fetch()` **during startup**, stubbing inside `@BeforeEach` runs **after** startup and has no effect on the call that already occurred. The Mockito mock may return `null` by default and crash context startup.

The same applies to `@MockitoBean` in newer Framework lines: the bean is swapped before tests run, yet **stubbing inside test methods cannot turn back time**.

Proper approaches depend on your goal:

- If you do not need the runner: **exclude the runner from the context** via properties/`@Profile`.
- If you want to test the runner: **unit-test** `run(...)` with fakes/mocks configured before invoking it.
- If you must verify bootstrap against a remote stub: supply a test bean/mock **already configured before context refresh/run**, or an HTTP mock server started with its endpoint registered early; watch initialization ordering carefully.
- If the runner invokes external services in constructors/`@PostConstruct`: gating the runner alone may not suffice if side effects reside in another initialized bean.

**Never use `Thread.sleep(...)` in tests to work around “stubbed too late”.** That is a lifecycle boundary error, not system latency.

## 13. Reading errors when `@SpringBootTest` fails due to a runner

If `ApplicationRunner.run(...)` throws an exception, console logs may show:

```text
Failed to load ApplicationContext
...
Caused by: java.lang.IllegalStateException: import failed
    at ...StartupRunner.run(...)
```

This is an **illustrative log structure**; actual stack traces depend on the application. Investigation steps:

1. Find the **first root cause** at the bottom of the `Caused by` chain, not just `Failed to load ApplicationContext`.
2. Check the call stack for `SpringApplication.callRunners`, `ApplicationRunner.run`, or `CommandLineRunner.run`.
3. Inspect which runner beans are registered: `@Component`/`@Bean`, `@ConditionalOnProperty`, `@Profile`, and test properties.
4. Confirm the runner ran during startup rather than a call inside `@Test`.
5. Look for real external dependencies: DB URLs, credentials, network, message brokers, file paths, or API clients.
6. If the runner must run, fix side effects in the test environment and test idempotency; if out of scope, disable it via the right condition.
7. Rerun **one small test class** to isolate the root cause, then rerun the suite to catch caching and shared-data issues.

| Symptom | Hypothesis | What to check |
| --- | --- | --- |
| Test fails before `@Test` | Startup runner threw an exception | Stack trace `run(...)` and external dependencies |
| Startup makes real HTTP calls | Unguarded runner, or client init side effect | Bean conditions and test profile |
| `@BeforeEach` stub has no effect | Runner executed before callback | Move stub earlier or disable runner |
| Passes alone, fails in suite | Cache/context reload or shared DB state | Cache keys, idempotency, cleanup |
| Startup import runs repeatedly | Each new context invokes runners | `@DirtiesContext`, properties, JVM forks, retries |
| `webEnvironment=NONE` still seeds DB | `NONE` does not disable `SpringApplication` runners | Property condition/profile |
| `@Transactional` does not roll back seed | Runner ran outside test transaction | Transaction boundaries and dedicated DB |
| Runner order shifts | No explicit `@Order`/`Ordered` | Assign order or build an orchestrator |
| Test “never sees runner execute” | Cache hit, condition off, slice omits runner | Bean presence and cache configuration |
| `ApplicationReadyEvent` never arrives | Runner stuck or failed | Startup logs, exceptions, task duration |
| Boot test differs from real app | Test skips custom `main` by default | `useMainMethod` and configuration |

### 13.1. Context failure threshold

Starting in Spring Framework 6.1, once a context cache key fails to load, subsequent attempts to load it may be aborted according to the **failure threshold** (default 1). Later tests may only print the threshold error rather than repeating the original runner failure. Always track down the **very first failure**, instead of treating subsequent threshold messages as independent bugs.

## 14. Exactly-once execution and idempotency

A runner should never be treated as a guarantee of **“running only once across the entire system”**. It executes **once per `SpringApplication` process startup** for the beans registered in that process. In production with multiple replicas, pod restarts, crash recoveries, or blue-green deployments, the same job can run multiple times; test context reloads behave similarly.

Options when side effects need control:

- **Idempotent data seeding:** use upserts/unique keys and applied-state tracking rather than blind inserts on every startup.
- **Distributed locks/leader election:** when strictly one replica may perform the task.
- **Migration tools:** for schema changes, use Flyway/Liquibase properly instead of ad hoc runners.
- **Dedicated batch/schedulers:** long or periodic jobs suit Spring Batch, scheduled jobs, or deployment jobs without blocking every service instance's startup.
- **Outbox/idempotency keys:** when runners emit events or call retryable APIs.
- **Startup flags:** enable jobs explicitly, with isolated test environments.
- **Observability:** log job ID, duration, processed counts, outcome, and failure cause (without logging secrets).

**Transactions do not replace idempotency.** Even if each run executes inside a transaction, a committed transaction can still insert duplicate rows on the next startup unless business constraints prevent it.

## 15. Performance, readiness, and long-running tasks

Because runners execute **before `ApplicationReadyEvent`**, a slow runner prolongs startup. In orchestrator environments, readiness probes typically route traffic only after the app reports ready.

Still, distinguish carefully:

- `ApplicationStartedEvent`: context refreshed, runners have not run yet.
- Web server sockets may already be listening before ready; never assume network requests cannot arrive yet.
- `ApplicationReadyEvent`: runners finished successfully and Boot signals the readiness transition.
- With async runners, if `run` submits background work and returns immediately, `ApplicationReadyEvent` may arrive **before the background task completes**.

If startup work is **mandatory before the service operates properly**, establish clear synchronization/readiness semantics. If long-running work is not a readiness prerequisite, split it into a monitored async/batch workflow; never spawn unmanaged threads and call it “safe”.

In CI, a heavy runner can stretch context startup from a couple of seconds to minutes even for a test with a single assertion. Disabling out-of-scope startup work yields far greater gains than micro-optimizing assertions.

## 16. Differences to note across Spring Boot versions

The sample uses Spring Boot 3.3.0. `ApplicationRunner`, `CommandLineRunner`, `ApplicationArguments`, `@Order`, and `@ConditionalOnProperty` are long-standing Boot APIs; nonetheless, **starter organization, test packages, and bean-mocking annotations vary across lines**.

| Feature | Spring Boot 2.x | Spring Boot 3.0–3.3 | Spring Boot 3.4–3.5 / 4.x |
| --- | --- | --- | --- |
| Startup runners | Yes | Yes | Yes |
| Boot tests create context via `SpringApplication` | Yes | Yes | Yes |
| `@SpringBootTest(args=...)` | Yes in 2.x lines supporting it | Yes | Yes, verify exact minor API |
| `@SpringBootTest(useMainMethod=...)` | Check specific 2.x version | Yes | Yes in documented lines |
| Mocking beans in tests | Legacy `@MockBean` | Legacy `@MockBean` | Boot 3.4+ offers `@MockitoBean`; Boot 4 removes legacy |
| Controlling runners | Properties, profiles, bean definitions | Similar | Similar, with version-specific test imports |

**Never conclude runners are skipped just because `@MockBean` changed.** `SpringApplication`'s startup runner mechanism does not depend on Mockito. When upgrading major versions, inspect test starters, imports, and Boot test bootstrap, then use enabled/disabled tests like section 6 to verify real behavior.

### 16.1. Tests do not call custom `main` by default

If production `main` configures:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(RunnerDemoApplication.class);
    application.setAdditionalProfiles("production-setup");
    application.run(args);
}
```

and tests use default `@SpringBootTest`, the custom code inside `main` is not called directly. Runners may still be invoked by the test's `SpringApplication`, **yet receive different profile settings than production**.

If the goal is to verify those exact `main` customizations, use `useMainMethod = ALWAYS`/`WHEN_AVAILABLE` per version docs while keeping the test environment safe. Otherwise, keep startup configuration in beans/extensions under test control rather than hiding it inside `main`.

## 17. Checklist for designing and testing startup runners

- [ ] I know all beans implementing `ApplicationRunner`/`CommandLineRunner` imported into the context under test.
- [ ] I understand `@SpringBootTest` can invoke them right when loading the context.
- [ ] I know `webEnvironment=NONE` does not disable runners.
- [ ] I distinguish skipping `main` directly from skipping `SpringApplication`.
- [ ] Runners with external side effects are gated behind explicit flags/profiles and enabled only where needed.
- [ ] When using `@ConditionalOnProperty`, I checked `havingValue` and `matchIfMissing` produce the intended state.
- [ ] I do not expect `@BeforeEach` stubs to affect runner calls that already ran during bootstrap.
- [ ] Unit tests invoke `run` to verify logic; Boot tests load the context to confirm automatic runner invocation.
- [ ] I do not re-invoke `run` manually inside Boot tests verifying startup execution.
- [ ] Disabled tests prove runners are absent or produce no side effects per contract.
- [ ] Runners declare explicit `@Order`/`Ordered` if execution order matters.
- [ ] I do not use `@DependsOn` instead of ordering startup runner callbacks.
- [ ] DB/event side effects are idempotent across restarts and multiple replicas.
- [ ] Data written by startup runners is never assumed to roll back with test-method transactions.
- [ ] Test fixtures needed by runners are prepared before context load.
- [ ] I understand context cache hits, `@DirtiesContext`, and JVM forks can alter invocation counts.
- [ ] Long-running/async runners do not misrepresent readiness state.
- [ ] When encountering `Failed to load ApplicationContext`, I inspect the root cause and `run(...)` stack trace.

## 18. Practice exercises with guided answers

### Exercise 1 — Prove `NONE` does not disable runners

Run `RunnersEnabledBootTest` from section 6. The test uses `webEnvironment=NONE` yet `audit` already holds both events. Explanation: the Boot context builds via `SpringApplication`, the runners have their property enabled, and they execute before `@Test`. Switching `NONE` to another web mode is not the way to disable runners.

### Exercise 2 — Change order and observe assertions

Change `@Order(10)` on `ArgsStartupRunner` to `@Order(30)`, keeping the CLI runner at order 20. Run the enabled test. Audit order flips and `List.of(...)` fails. Restore the order. Takeaway: only assert order if ordering is part of the contract.

### Exercise 3 — Disable runners via property

Set `app.startup.enabled=false` in the enabled test (temporarily on a scratch branch). The context skips registering runners and `audit` stays empty; the assertion expecting two events fails. Restore `true`. Explain the difference between **beans excluded by conditions** and **runners existing yet returning early**.

### Exercise 4 — Distinguish startup from test methods

In a test copy, add `new ArgsStartupRunner(audit).run(...)` inside `@Test`. `audit` now gains an extra event; the test no longer purely verifies bootstrap. Remove the line. Answer: why shouldn't runners be called manually in bootstrap integration tests?

### Exercise 5 — Data and rollback

Design a dummy `ApplicationRunner` writing a row into a test database. Annotate the test class with `@Transactional` and query the row back. Prediction: if the startup operation committed in its own transaction, rolling back after the test method **does not delete** that row. Use a dedicated test DB and intentional cleanup/transactions/idempotency.

### Exercise 6 — Cache and duplicate effects

Two test classes both use `@SpringBootTest(properties="app.startup.enabled=true")`. On a cache hit, runners only execute during the first context load. Add a different inline property on the second class or mark the context dirty in a sandbox: a new context starts and runners execute again. Design a “no duplicate rows” invariant to catch repeated-startup bugs.

### Exercise 7 — Stubbing too late

Suppose a runner calls `RemoteGateway.fetch()` at startup. The test has `@MockBean RemoteGateway` and `when(...).thenReturn(...)` in `@BeforeEach`. Explain why the stub arrives too late, then design either approach: disable the runner for regular service tests, or supply a fake configured **before context load** to test the startup flow specifically.

### Exercise 8 — Choosing the right arguments API

Given arguments `--mode=verify seed.csv`, write expected values:

- `ApplicationArguments.getOptionValues("mode")` → `["verify"]`.
- `ApplicationArguments.getNonOptionArgs()` → `["seed.csv"]`.
- `CommandLineRunner.run(String... args)` → `["--mode=verify", "seed.csv"]`.

Verify using the unit tests from section 6 without loading Spring.

## 19. Summary

`ApplicationRunner` and `CommandLineRunner` are **entry points that run after `SpringApplication` refreshes the context and before the application is announced ready**. They differ in how arguments are passed; execution order can be defined via `@Order`/`Ordered`. They are invoked by Spring Boot **because they are beans in the context**, not because JUnit calls `run` directly.

With `@SpringBootTest`, the biggest hazard is **side effects occurring before test methods**: stubbing and fixtures prepared in `@BeforeEach` may arrive too late; test transactions do not automatically roll back startup writes; context caching and multiple JVMs/restarts can cause runners to execute a different number of times than expected.

Reliable strategy: **make startup jobs opt-in**, make side effects idempotent, unit-test `run` logic, and keep a focused Boot integration test verifying runner invocation during bootstrap. That keeps tests fast, safe, and faithful to the startup contract.

## 20. Official version-specific documentation

- Spring Boot — SpringApplication: runners, ordering, startup events: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — `ApplicationRunner` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot — `CommandLineRunner` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/CommandLineRunner.html
- Spring Boot — `ApplicationArguments` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot — `ConditionalOnProperty` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework — TestContext context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test-managed transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- JUnit Jupiter — Test lifecycle and assertions: https://docs.junit.org/current/user-guide/
