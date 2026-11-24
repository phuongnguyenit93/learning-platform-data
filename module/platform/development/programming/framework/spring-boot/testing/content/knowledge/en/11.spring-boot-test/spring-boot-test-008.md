# Choosing classes, properties, and startup options to verify with @SpringBootTest

## 1. Goal: know precisely which ApplicationContext has started

In Spring Boot testing, merely writing `@SpringBootTest` and checking `contextLoads()` is not enough to prove the application started with the **right configuration**. A context might load with default settings yet fail to load the QA profile, skip customizations in `main()`, miss beans gated by a feature flag, or lack an HTTP listener even though the test assumes it is testing real networking. Conversely, a test needing only a few beans might accidentally load all of JDBC, Kafka, Redis, schedulers, and exporters, failing on infrastructure unrelated to its goal.

`@SpringBootTest` provides **five option groups you need to understand clearly**:

1. `classes`: which classes serve as the **configuration sources** to build the context.
2. `properties`/`value`: which key-value pairs are injected into the Spring `Environment` before startup.
3. `args`: which command-line arguments are passed to `SpringApplication` and `ApplicationArguments`.
4. `webEnvironment`: whether to create a mock web context, a non-web context, or an embedded HTTP server.
5. `useMainMethod`: whether to invoke the `main(String[])` method and its customizations.

In addition, `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, `@TestConfiguration`, `@Import`, context caching, and bean conditions all shape the final behavior.

The goal after this lesson is for learners to **select configurations with clear reasoning** and write assertions for actual effects: values bound into `@ConfigurationProperties`, bean presence/absence, active profiles, CLI options, and server ports/HTTP responses. This is a standalone Knowledge lesson for the **`@SpringBootTest`** parent menu in Spring Boot testing, using **Java 17+, Spring Boot 3.5.x**, Gradle Groovy DSL, and JUnit Jupiter.

## 2. Attribute reference table

| Attribute | Type | Default | Meaning |
|---|---|---|---|
| `classes` | `Class<?>[]` | Empty | Configuration sources to build the ApplicationContext; if omitted, uses configuration discovery |
| `properties` | `String[]` | Empty | Adds test properties `key=value` to the Environment |
| `value` | `String[]` | Empty | **Alias of `properties`**, not an alias of `classes` |
| `args` | `String[]` | Empty | Arguments passed to SpringApplication |
| `webEnvironment` | `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE` | `MOCK` | Whether to start a real HTTP server |
| `useMainMethod` | `NEVER`, `WHEN_AVAILABLE`, `ALWAYS` | `NEVER` | Policy for calling the application's `main` method |

Illustrative syntax:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    properties = {
        "demo.region=lab",
        "demo.batch-size=3"
    },
    args = {
        "--job.mode=validate",
        "input.csv"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER)
class ConfigurationExampleTest {
    // Fragment only; full tests are in the hands-on section.
}
```

You do not need to specify every attribute in every test. Start from the question “what **startup configuration and behavior** am I trying to prove?” and pick the minimal options needed.

```text
                           JUnit Jupiter
                                |
                        @SpringBootTest
                                |
             +------------------+------------------+
             |                  |                  |
         classes           properties,args       webEnvironment
             |                  |                  |
     Root configuration     Environment,       NONE / MOCK /
     and component scan   ApplicationArguments  RANDOM_PORT
             |                  |                  |
             +------------------+------------------+
                                |
                          SpringApplication
                       useMainMethod policy
                                |
                       ApplicationContext
                                |
            assertions on beans, effective properties,
              profiles, CLI args, port, and HTTP
```

## 3. `classes`: initialization configuration, not a list of beans to assert

When `classes` is omitted, Spring Boot first looks for an eligible nested `@Configuration`, then searches upward through the package hierarchy from the test package for `@SpringBootConfiguration` or `@SpringBootApplication`. A project with the app at `com.example.bootlab.DemoApplication` and tests under `com.example.bootlab` normally gets configuration auto-discovered.

### 3.1. Explicitly selecting the application root

```java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class FullBootConfigTest {
}
```

Here `DemoApplication` carries `@SpringBootApplication`, so Boot can still **component-scan the application's entire base package**. `classes=DemoApplication.class` does not mean the context contains only one class or a single bean; it simply specifies the root configuration source.

### 3.2. Choosing a truly minimal context

```java
@SpringBootTest(
    classes = MinimalRoot.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MinimalContextTest {
    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class MinimalRoot {
        @Bean Marker marker() {
            return new Marker("test-only");
        }
    }
}
```

This fragment requires declaring `Marker` and imports; the complete version is in the hands-on section. `MinimalRoot` has no `@ComponentScan`, so application `@Service` beans are not pulled in automatically. However, it has `@EnableAutoConfiguration`, so **Boot infrastructure beans still exist** matching the classpath; do not claim the context has only a single bean.

If a test only needs a tiny `@Configuration` without Boot semantics, `@ContextConfiguration` or `ApplicationContextRunner` can be lighter.

### 3.3. `classes` and `@ContextConfiguration`

Spring TestContext allows `@ContextConfiguration(classes=...)`; `@SpringBootTest(classes=...)` offers a shorter declaration with the same goal of selecting configuration sources under Boot's test loader. Do not declare two conflicting sets of classes expecting the framework to “merge everything” in your imagined order. For tests with strict requirements, pick one clear configuration path and inspect the actual bean graph.

### 3.4. Nested @Configuration and @TestConfiguration differ

A nested `@Configuration` can be used **instead of** the primary application configuration when the test omits `classes`. By contrast, a nested `@TestConfiguration` typically **supplements** the Boot application. Top-level `@TestConfiguration` is not auto-scanned like production `@Configuration`; you can use `@Import` to include it explicitly.

When you only need to add a test bean (a fake clock, diagnostic marker), use `@TestConfiguration` + `@Import` — **do not** modify `@SpringBootApplication` or scan the entire test folder. If you plan to override a real bean, use the `@MockitoBean`/`@TestBean` policy and follow bean-overriding rules rather than creating a duplicate bean name and assuming it replaces the original.

## 4. `properties` and its `value` alias: configuration injected before startup

```java
@SpringBootTest(properties = {
    "demo.region=inline",
    "demo.batch-size=3",
    "demo.enabled=false"
})
```

supplies `key=value` pairs to the context. `value` is an alias:

```java
@SpringBootTest(value = "demo.region=alias")
```

which is equivalent to:

```java
@SpringBootTest(properties = "demo.region=alias")
```

These two annotation snippets are simply **alternative forms**. Prefer `properties` when passing multiple keys to make it obvious these are not `classes`.

### 4.1. Property strings differ from bound beans

Suppose the application config has:

```properties
demo.region=base
demo.batch-size=8
demo.enabled=true
demo.feature.enabled=false
```

If a `@ConfigurationProperties(prefix="demo")` Java record has fields `region`, `batchSize`, and `enabled`, good tests should check:
- `Environment.getProperty("demo.region")` is `inline`.
- `RuntimeSettings.region()` is also `inline`.
- `RuntimeSettings.batchSize() == 3`, `enabled() == false`.
- Conditional beans depending on `demo.feature.enabled` are present or absent per startup config.

Asserting only that the `Environment` key has a value does not prove `@ConfigurationProperties` was registered/bound or that application beans actually use that value. A mistyped property can make the context **fail before the `@Test` method runs**, when the binder fails to convert a string to `int`/Duration/enum.

### 4.2. Options with early startup impact

- `spring.main.web-application-type=none`: requests a non-web application type.
- `spring.main.web-application-type=reactive`: useful if both MVC and WebFlux are on the classpath yet the test wants reactive.
- `spring.main.lazy-initialization=true`: defers some bean creation; can **mask failures** if you only assert context load without accessing beans.
- `spring.autoconfigure.exclude=...`: excludes an auto-configuration; be clear that this creates **a different startup mode** from production.
- `server.port=0`: asks the server to bind a random port **when running a real server**.
- `logging.level...=DEBUG`: enables diagnostics; does not replace business assertions.

Do not call `environment.getPropertySources().addFirst(...)` after context refresh expecting `@ConditionalOnProperty` to re-evaluate. The bean graph is decided during startup; changing configuration requires a fresh context run.

## 5. Property source ordering and key collision scenarios

Spring Boot loads Config Data from `application.properties`/`application.yaml`, OS environment variables, JVM system properties, command-line options, test inline properties, and Spring TestContext sources.

Verifiable principles:
- Test-inline `@SpringBootTest(properties=...)` overrides application defaults in this lesson's samples.
- `@TestPropertySource(properties=...)` takes precedence over **`@TestPropertySource(locations=...)`** for the same key.
- `@DynamicPropertySource` registers suppliers for runtime values, ideal for Testcontainers and mock server URLs/ports.
- `args="--demo.region=cli"` typically adds a command-line property into `Environment`, while also appearing in `ApplicationArguments`.
- `application-qa.properties` only takes effect when the `qa` profile is active.
- When multiple test-specific property layers define the **same key**, verify the exact effective value on your Boot/Spring Framework version; documentation describes property source precedence at varying abstraction levels. The easiest thing to review is avoiding unnecessary key collisions.

**Avoid** calling `System.setProperty("demo.region", "...")` in one test and forgetting to restore it, as that mutates JVM-global state and causes flakiness under parallel runs. Use per-test-configuration annotations, property registries, or explicit property injection.

### 5.1. `@TestPropertySource` files and inline values

```java
@SpringBootTest(properties = "demo.batch-size=2")
@TestPropertySource(
    locations = "classpath:custom-test.properties",
    properties = "demo.region=test-inline")
class SourceExample {
}
```

The file `custom-test.properties` has `demo.region=file-value`, `demo.enabled=false`; the inline test property overrides `region` from the file; `demo.batch-size` is supplied via `@SpringBootTest` under a **different key**, avoiding reliance on precedence between the two annotation mechanisms for the same key.

`@TestPropertySource` reads properties resources via TestContext and **does not directly parse YAML** like Boot Config Data. If you need multi-profile YAML configs, use `application-qa.yaml` + `@ActiveProfiles("qa")` or explicit `spring.config.import` mechanisms.

An empty `@TestPropertySource` uses a default naming convention based on the test class/package; it does **not** automatically pick `application-test.properties`. For clarity, specify `locations` explicitly or use `@ActiveProfiles`.

### 5.2. `@DynamicPropertySource` for test-created configuration

```java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    registry.add("demo.external-uri",
            () -> "stub://local-service");
}
```

The static method above registers a supplier, not a plain constant string. With Testcontainers, the supplier can invoke `postgres::getJdbcUrl`, `getMappedPort(5432)`, or a mock HTTP server's address after the resource starts. Manage the lifecycle of real resources; **never** reuse an old endpoint from another run. The `stub://` value here only illustrates reading from Environment and opens no network connection.

If multiple test classes/subclasses share a cached context yet dynamic property suppliers ultimately return different values, you may need context isolation or `@DirtiesContext`; do not assume changing a static value rebuilds already-instantiated beans.

## 6. `@ActiveProfiles`: profiles load profile-specific Config Data

```java
@ActiveProfiles("qa")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QaProfileTest {
}
```

When the `qa` profile is active, Boot loads `application-qa.properties` alongside application defaults. For instance:
- `application.properties`: `demo.region=base`, `demo.batch-size=8`, `demo.enabled=true`.
- `application-qa.properties`: `demo.region=qa-profile`, `demo.batch-size=12`.
- The bound record has `region=qa-profile`, `batchSize=12`, `enabled=true`.

Do not just assert `environment.getActiveProfiles()` contains `qa`; assert that the **bound bean** reflects QA values. Never activate a production profile on CI if that profile turns on live remote services or production credentials.

If a test combines `@ActiveProfiles("qa")` with `properties="demo.region=inline"`, verify which source represents the contract under test. Do not assume that merely activating a profile makes every property in the profile file beat inline test overrides.

## 7. `args`: CLI startup contract, not an alias for `properties`

```java
@SpringBootTest(
    args = {
        "--job.mode=dry-run",
        "input.csv",
        "--demo.region=from-cli"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CommandLineArgumentsTest {
}
```

With `ApplicationArguments`:
- `getOptionNames()` contains `job.mode` and `demo.region`.
- `getOptionValues("job.mode")` returns `["dry-run"]`.
- `getNonOptionArgs()` contains `input.csv`.
- By default, `--demo.region=from-cli` is also exposed into `Environment` by `SpringApplication`.

| Declaration | Environment | ApplicationArguments |
|---|---|---|
| `properties="job.mode=dry-run"` | Present | Does not create an option |
| `args="--job.mode=dry-run"` | Present, per default CLI mechanism | Has option `job.mode` |
| `args="input.csv"` | Does not create property `input.csv` | Has non-option argument |
| `@ActiveProfiles("qa")` | Active profile and profile config | Does not add a CLI argument |

If the application has an `ApplicationRunner` or `CommandLineRunner` handling flags like `--dry-run`, use `args` to test CLI integration. However, real runners can publish messages or mutate DBs; supply appropriate fake/local dependencies. The mere presence of an option **does not prove the runner executed the right side effect**.

## 8. `webEnvironment`: the exact web tier the specification requires

| Mode | Starts server? | What to assert? | Best suited for |
|---|---|---|---|
| `MOCK` (default) | Binds no socket; mock web context if web stack is on classpath | MVC mappings/filters via MockMvc when `@AutoConfigureMockMvc` is enabled | HTTP contract through Spring MVC without TCP |
| `NONE` | No web environment | Context beans, profiles, binding, startup options | Services/configs/CLI |
| `RANDOM_PORT` | **Yes**, OS assigns random port | `@LocalServerPort`, real HTTP client responses | Servlet/Netty server integration |
| `DEFINED_PORT` | **Yes**, `server.port` or default 8080 | Fixed-port server startup | Rarely used in parallel CI due to port collisions |

**Crucial distinction:** `MOCK` does not mean repositories/services are mocked. `@SpringBootTest(MOCK)` is a **full application context** with a simulated web environment; to mock a service, override it explicitly. With Servlet MVC, `@AutoConfigureMockMvc` is needed to inject `MockMvc`; `@WebMvcTest` is a different slice annotation that already auto-configures MockMvc.

`RANDOM_PORT` starts a real HTTP server, and tests can use `@LocalServerPort` and `TestRestTemplate` when on the Boot test classpath. `server.port=0` is just the bind directive; the **actual port** is known after startup. `DEFINED_PORT` risks `BindException` when multiple CI workers run the same project on a host; the lab avoids fixed ports.

With `@SpringBootTest(RANDOM_PORT)`, client and servlet server run on **different threads**. JUnit test-thread `@Transactional` rolls back the transaction managed on that thread by default; HTTP server requests have their own transactions and can commit. When a DB is involved, use explicit cleanup/data isolation instead of assuming `@Transactional` rolls back HTTP writes.

If both Spring MVC and WebFlux are on the classpath, Boot usually favors MVC. To test a reactive app, set `spring.main.web-application-type=reactive` where appropriate and use `WebTestClient`; do not treat every `@SpringBootTest(MOCK)` as a reactive context.

## 9. `useMainMethod`: does `main()` contain customizations?

By default, `@SpringBootTest(useMainMethod=NEVER)` **does not invoke the main method**, bootstrapping instead via `SpringApplication` with the selected configuration source. This is usually equivalent when `main` only has:

```java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);
}
```

However, if `main` configures banners, additional profiles, application listeners, or key attributes, a test might miss those customizations.

```java
public static void main(String[] args) {
    SpringApplication app =
            new SpringApplication(DemoApplication.class);
    app.setAdditionalProfiles("main-mode");
    app.run(args);
}
```

In that case:
- `UseMainMethod.NEVER` (**default**): skips the customization above.
- `UseMainMethod.WHEN_AVAILABLE`: calls `main` when present, otherwise falls back normally.
- `UseMainMethod.ALWAYS`: requires and invokes `main`, failing startup if none is found.

An `ALWAYS` test should assert **real consequences**, such as the `main-mode` profile being active and properties from `application-main-mode.properties` being bound. If the test also puts `@ActiveProfiles("main-mode")` on itself, it can pass even when `main` never ran — defeating the purpose. The sample code below avoids that mistake.

Never use `main` to call unintended production systems or `System.exit` during tests; keep side effects in runners/beans controllable via profiles.

## 10. Runnable project: Gradle + Java 17 + Spring Boot 3.5.8

The project is intentionally small, with no DB/Docker/brokers. The tests differ in **boot configuration**, not business logic.

```text
settings.gradle
build.gradle
src/main/java/com/example/bootlab/
    DemoApplication.java
    RuntimeSettings.java
    SettingsReporter.java
    FeatureFlagService.java
    ProbeController.java
src/main/resources/
    application.properties
src/test/resources/
    application-qa.properties
    application-main-mode.properties
    custom-test.properties
src/test/java/com/example/bootlab/
    DefaultConfigurationTest.java
    ExplicitConfigurationTest.java
    InlinePropertiesTest.java
    AliasPropertyTest.java
    QaProfileTest.java
    CommandLineArgumentsTest.java
    TestPropertySourceTest.java
    DynamicPropertySourceTest.java
    AdditionalTestConfigurationTest.java
    MainNeverTest.java
    MainAlwaysTest.java
    MockWebEnvironmentTest.java
    RandomPortEnvironmentTest.java
    NoneWebEnvironmentTest.java
    StartupFailureRunnerTest.java
```

### 10.1. settings.gradle

```groovy
rootProject.name = 'boot-startup-config-lab'
```

### 10.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

Spring Boot dependency management aligns Spring Framework/JUnit/Mockito and Jackson. The project needs a compatible Gradle wrapper or installed Gradle; `build.gradle` does not generate `gradlew` itself.

### 10.3. application.properties

File `src/main/resources/application.properties`:

```properties
demo.region=base
demo.batch-size=8
demo.enabled=true
demo.feature.enabled=false
```

### 10.4. DemoApplication.java

```java
package com.example.bootlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(RuntimeSettings.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);
        application.setAdditionalProfiles("main-mode");
        application.run(args);
    }
}
```

`main` adds the profile only when invoked. Do not put `System.setProperty` or mutable global singletons in `main` to prevent state leaking across test classes. `@EnableConfigurationProperties` registers the immutable record below.

### 10.5. RuntimeSettings.java

```java
package com.example.bootlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record RuntimeSettings(
        String region,
        int batchSize,
        boolean enabled) {
}
```

The record uses Spring Boot constructor binding, needing no setters. Do not also annotate it with `@Component` expecting Boot to process constructor binding the same way; `@EnableConfigurationProperties` on `DemoApplication` registers the bean.

### 10.6. SettingsReporter.java

```java
package com.example.bootlab;

import org.springframework.stereotype.Service;

@Service
public class SettingsReporter {

    private final RuntimeSettings settings;

    public SettingsReporter(RuntimeSettings settings) {
        this.settings = settings;
    }

    public RuntimeSettings settings() {
        return settings;
    }

    public String summary() {
        return settings.region() + "|"
                + settings.batchSize() + "|"
                + settings.enabled();
    }
}
```

With default properties, `summary()` returns `base|8|true`. With inline overrides, it becomes `inline|3|false`. This is **bean-level proof** that config was bound and consumed.

### 10.7. FeatureFlagService.java

```java
package com.example.bootlab;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true")
public class FeatureFlagService {

    public String status() {
        return "feature-enabled";
    }
}
```

With `demo.feature.enabled=false`, Spring skips creating this bean. When a test sets `true` **before startup**, the bean exists. This distinguishes raw property lookup from **conditional bean graph** behavior.

### 10.8. ProbeController.java

```java
package com.example.bootlab;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final SettingsReporter reporter;

    public ProbeController(SettingsReporter reporter) {
        this.reporter = reporter;
    }

    @GetMapping(
        path = "/probe",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return reporter.summary();
    }
}
```

A single plain-text endpoint suffices for both `MOCK` and `RANDOM_PORT` modes. In non-web tests, the Controller bean can still be created via component scan, yet there is **no HTTP listener**, so `/probe` cannot be called.

### 10.9. Test resource files

File `src/test/resources/application-qa.properties`:

```properties
demo.region=qa-profile
demo.batch-size=12
```

File `src/test/resources/application-main-mode.properties`:

```properties
demo.region=from-main-profile
```

File `src/test/resources/custom-test.properties`:

```properties
demo.region=from-custom-file
demo.enabled=false
```

These files serve distinct purposes:
- `qa` is activated by `@ActiveProfiles("qa")`.
- `main-mode` is added by `DemoApplication.main` **only under the matching `useMainMethod`**.
- `custom-test.properties` is loaded explicitly via `@TestPropertySource`.

Do not put `spring.profiles.active=qa` in main resources forcing all tests onto QA; each test should state its own policy.

## 11. JUnit verification classes: auto-discovery and minimal roots

### 11.1. DefaultConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DefaultConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    SettingsReporter reporter;

    @Test
    void discoversAppAndBindsDefaults() {
        assertThat(context.getBean(DemoApplication.class))
                .isNotNull();
        assertThat(reporter.summary())
                .isEqualTo("base|8|true");
    }

    @Test
    void disabledFlagDoesNotCreateFeatureBean() {
        assertThat(context.getBeanNamesForType(
                FeatureFlagService.class))
                .isEmpty();
    }
}
```

The first two tests use package-based discovery. They assert `DemoApplication` and `SettingsReporter` exist with default values, and assert the conditional feature bean does **not** exist.

### 11.2. ExplicitConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ExplicitConfigurationTest.MinimalRoot.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ExplicitConfigurationTest {

    record Marker(String value) {}

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class MinimalRoot {
        @Bean
        Marker marker() {
            return new Marker("minimal");
        }
    }

    @Autowired
    ApplicationContext context;

    @Test
    void usesSelectedConfigurationRoot() {
        assertThat(context.getBean(Marker.class).value())
                .isEqualTo("minimal");
    }

    @Test
    void doesNotScanFullApplicationServices() {
        assertThat(context.getBeanNamesForType(
                SettingsReporter.class))
                .isEmpty();
    }
}
```

Both tests verify `classes` genuinely restricts the configuration source. `MinimalRoot` has no component scan, so `SettingsReporter` is absent even though the code sits in the same package. This is a **narrow Boot context** example, not full application integration.

## 12. JUnit verifying properties, value alias, and feature flags

### 12.1. InlinePropertiesTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "demo.region=inline",
        "demo.batch-size=3",
        "demo.enabled=false",
        "demo.feature.enabled=true"
    })
class InlinePropertiesTest {

    @Autowired
    SettingsReporter reporter;

    @Autowired
    ApplicationContext context;

    @Test
    void inlinePropertiesChangeBoundSettings() {
        assertThat(reporter.summary())
                .isEqualTo("inline|3|false");
        assertThat(reporter.settings().batchSize())
                .isEqualTo(3);
    }

    @Test
    void flagEnablesConditionalBeanAtStartup() {
        assertThat(context.getBean(
                FeatureFlagService.class).status())
                .isEqualTo("feature-enabled");
    }
}
```

Both tests assert the **consequences** of properties: record binding and conditional bean registration. This uses a separate context from the defaults test; Spring TestContext does not “hot-swap properties” on an old context.

### 12.2. AliasPropertyTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    value = "demo.region=alias",
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AliasPropertyTest {

    @Autowired
    RuntimeSettings settings;

    @Test
    void valueMeansPropertiesNotClasses() {
        assertThat(settings.region()).isEqualTo("alias");
        assertThat(settings.batchSize()).isEqualTo(8);
    }
}
```

This test demonstrates the `value` alias. When a reviewer sees `@SpringBootTest(value=...)`, they must understand it is a **property override**, not an entry-point configuration class.

## 13. JUnit verifying profiles and command-line arguments

### 13.1. QaProfileTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@ActiveProfiles("qa")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class QaProfileTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void profileSpecificConfigDataIsBound() {
        assertThat(environment.getActiveProfiles())
                .contains("qa");

        assertThat(settings.region())
                .isEqualTo("qa-profile");
        assertThat(settings.batchSize()).isEqualTo(12);
        assertThat(settings.enabled()).isTrue();
    }
}
```

The test checks not only active profiles, but also asserts `application-qa.properties` updated the bound properties. `contains("qa")` is better than `containsExactly("qa")` when the environment intentionally carries additional profiles.

### 13.2. CommandLineArgumentsTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    args = {
        "--job.mode=dry-run",
        "input.csv",
        "--demo.region=from-cli"
    },
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CommandLineArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void exposesOptionsAndNonOptions() {
        assertThat(arguments.getOptionNames())
                .contains("job.mode", "demo.region");
        assertThat(arguments.getOptionValues("job.mode"))
                .containsExactly("dry-run");
        assertThat(arguments.getNonOptionArgs())
                .containsExactly("input.csv");
    }

    @Test
    void cliPropertyOverridesBaseConfig() {
        assertThat(environment.getProperty("demo.region"))
                .isEqualTo("from-cli");
        assertThat(settings.region())
                .isEqualTo("from-cli");
    }
}
```

Both tests verify `ApplicationArguments` and bound properties. If a test only sets `properties="job.mode=dry-run"`, `ApplicationArguments` will **not** automatically contain option `job.mode`. Avoid mixing `args` and `properties` for the **same key** just to “see which wins”; the sample keeps goals separate.

## 14. JUnit: @TestPropertySource and @DynamicPropertySource

### 14.1. TestPropertySourceTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "demo.batch-size=2")
@TestPropertySource(
    locations = "classpath:custom-test.properties",
    properties = "demo.region=from-test-inline")
class TestPropertySourceTest {

    @Autowired
    RuntimeSettings settings;

    @Test
    void fileAndInlineTestSourcesAreApplied() {
        assertThat(settings.region())
                .isEqualTo("from-test-inline");
        assertThat(settings.batchSize()).isEqualTo(2);
        assertThat(settings.enabled()).isFalse();
    }
}
```

This test proves the custom file provides `demo.enabled=false`, inline `@TestPropertySource` overrides `demo.region` from the file, and `@SpringBootTest` supplies a **different key** `demo.batch-size=2`.

### 14.2. DynamicPropertySourceTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DynamicPropertySourceTest {

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("demo.external-uri",
            () -> "stub://local-service");
    }

    @Autowired
    Environment environment;

    @Test
    void readsValueFromRegisteredSupplier() {
        assertThat(environment.getProperty(
                "demo.external-uri"))
                .isEqualTo("stub://local-service");
    }
}
```

This test confirms a property supplier is registered before the context consumes it. The `stub://local-service` URI is only an **illustrative value**; no remote service is opened or called. With Testcontainers, the supplier can use `container::getJdbcUrl`; do not assume a static container in one JVM is shared across multiple Gradle forks.

## 15. JUnit: @TestConfiguration supplements rather than replaces the application

### AdditionalTestConfigurationTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(AdditionalTestConfigurationTest.Extras.class)
class AdditionalTestConfigurationTest {

    record TestMarker(String text) {}

    @TestConfiguration(proxyBeanMethods = false)
    static class Extras {
        @Bean
        TestMarker marker() {
            return new TestMarker("additional");
        }
    }

    @Autowired
    TestMarker marker;

    @Autowired
    SettingsReporter reporter;

    @Test
    void addsTestBeanAndKeepsProductionWiring() {
        assertThat(marker.text()).isEqualTo("additional");
        assertThat(reporter.summary())
                .isEqualTo("base|8|true");
    }
}
```

This test demonstrates supplementary configuration explicitly imported via `@Import`. The context still retains the full app's `SettingsReporter`. Compare with `ExplicitConfigurationTest`: there the selected root **does not scan app services**; the two scenarios must not be confused.

## 16. JUnit: useMainMethod NEVER vs ALWAYS

### 16.1. MainNeverTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    properties = "demo.test-marker=never",
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.NEVER)
class MainNeverTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void skipsMainCustomization() {
        assertThat(settings.region()).isEqualTo("base");
        assertThat(environment.getActiveProfiles())
                .doesNotContain("main-mode");
    }
}
```

This test covers the default `NEVER` policy. `demo.test-marker` simply separates the cache key cleanly from the `ALWAYS` test; it does not affect app logic. The test assumes CI does not externally activate `main-mode`; in real projects, control active profiles carefully.

### 16.2. MainAlwaysTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = DemoApplication.class,
    properties = "demo.test-marker=always",
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class MainAlwaysTest {

    @Autowired
    Environment environment;

    @Autowired
    RuntimeSettings settings;

    @Test
    void mainAddsProfileAndLoadsItsSettings() {
        assertThat(environment.getActiveProfiles())
                .contains("main-mode");
        assertThat(settings.region())
                .isEqualTo("from-main-profile");
        assertThat(settings.batchSize()).isEqualTo(8);
    }
}
```

This test requires calling the main method; `main` adds `main-mode`, Config Data loads the profile file, and the record binds. If `MainAlwaysTest` also added `@ActiveProfiles("main-mode")`, it could pass even if `main` did not run; the sample **avoids that**. `WHEN_AVAILABLE` can be tested separately with the same pattern if you want to verify fallback when no suitable main method exists.

## 17. JUnit: choosing the web environment

### 17.1. MockWebEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = "demo.region=mock")
@AutoConfigureMockMvc
class MockWebEnvironmentTest {

    @Autowired
    MockMvc mvc;

    @Test
    void checksMvcWiringWithoutTcpPort() throws Exception {
        mvc.perform(get("/probe"))
            .andExpect(status().isOk())
            .andExpect(content().string("mock|8|true"));
    }
}
```

This is a **full application context test using mock Servlet requests**. It tests real mappings/controller/service **without** embedded Tomcat binding a socket. Do not confuse with `@WebMvcTest`: that annotation loads a web slice and typically mocks services.

### 17.2. RandomPortEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "demo.region=socket")
class RandomPortEnvironmentTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Test
    void realServerBindsRandomPortAndResponds() {
        assertThat(port).isGreaterThan(0);
        assertThat(client.getForObject(
                "/probe", String.class))
                .isEqualTo("socket|8|true");
    }
}
```

`TestRestTemplate` configured by Boot for `RANDOM_PORT` sets its root URI to the local server; `getForObject("/probe", ...)` resolves to the test's port. Never hardcode port 8080. This is a real HTTP test over loopback, **not** an external service.

### 17.3. NoneWebEnvironmentTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class NoneWebEnvironmentTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    RuntimeSettings settings;

    @Test
    void hasBeansButNoServletWebServerContext() {
        assertThat(context).isNotInstanceOf(
                ServletWebServerApplicationContext.class);
        assertThat(settings.region()).isEqualTo("base");
    }
}
```

`NONE` creates a non-web context while still binding business/configuration beans. Do not use `@LocalServerPort` in this mode. `DEFINED_PORT` has no separate runnable test here to avoid occupying a fixed port when parallel CI jobs run; if you must test an exact port, provision an exclusive environment/port lease.

## 18. Startup failure is a negative contract that needs separate testing

Invalid configuration (missing required property, duplicate bean, unparseable integer) can cause `@SpringBootTest` to fail **before JUnit `@Test` methods run**. To test “the context must fail on invalid configuration” while still letting the main suite complete, use `ApplicationContextRunner` to test each configuration independently.

### StartupFailureRunnerTest.java

```java
package com.example.bootlab;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

class StartupFailureRunnerTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GuardConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    static class GuardConfiguration {
        @Bean
        String startupGuard(Environment env) {
            boolean shouldFail = env.getProperty(
                "demo.force-startup-failure",
                Boolean.class, false);

            if (shouldFail) {
                throw new IllegalStateException(
                    "intentional test-only failure");
            }
            return "ready";
        }
    }

    @Test
    void validSettingsAllowBeanCreation() {
        runner.withPropertyValues(
                "demo.force-startup-failure=false")
            .run(ctx -> {
                assertThat(ctx).hasNotFailed();
                assertThat(ctx).hasBean("startupGuard");
                assertThat(ctx.getBean("startupGuard"))
                    .isEqualTo("ready");
            });
    }

    @Test
    void invalidSettingsFailStartupAsExpected() {
        runner.withPropertyValues(
                "demo.force-startup-failure=true")
            .run(ctx -> {
                assertThat(ctx).hasFailed();
                assertThat(ctx.getStartupFailure())
                    .isNotNull();
            });
    }
}
```

These two tests only verify the tiny **GuardConfiguration** inside `ApplicationContextRunner`, without starting the full Boot app or a web server. The positive run has the bean; the negative run records startup failure. Do not use `ApplicationContextRunner` and then claim you tested TCP ports, full JPA auto-configuration, or main method customization; those contracts belong to `@SpringBootTest` in the right mode.

## 19. Test count and scope matrix

| JUnit class | What is verified | `@Test` |
|---|---|---:|
| DefaultConfigurationTest | Boot root detection, defaults, feature absent | 2 |
| ExplicitConfigurationTest | Narrow configuration classes, no component scan | 2 |
| InlinePropertiesTest | Bound record, conditional bean | 2 |
| AliasPropertyTest | `value` alias for properties | 1 |
| QaProfileTest | Active profile and QA file | 1 |
| CommandLineArgumentsTest | CLI options/non-options, CLI property | 2 |
| TestPropertySourceTest | Inline properties override file in same annotation | 1 |
| DynamicPropertySourceTest | Dynamic supplier property | 1 |
| AdditionalTestConfigurationTest | Test-only bean added to full config | 1 |
| MainNeverTest | Skips main | 1 |
| MainAlwaysTest | Main adds profile | 1 |
| MockWebEnvironmentTest | MockMvc without opening TCP socket | 1 |
| RandomPortEnvironmentTest | Real HTTP on dynamic port | 1 |
| NoneWebEnvironmentTest | Non-web context | 1 |
| StartupFailureRunnerTest | Positive + negative config startup | 2 |
| **Total** | **15 classes** | **20 methods** |

These counts are **written/expected discovery counts from source**, not runtime test results. The project was not run through Gradle/JUnit at authoring time. When executing, inspect reports and task state to determine executed, failed, skipped, or cached tests.

## 20. Running the right Gradle task and reading results properly

With the Gradle wrapper present in the project:

```bash
./gradlew test
./gradlew test --tests "com.example.bootlab.DefaultConfigurationTest"
./gradlew test --tests "com.example.bootlab.ExplicitConfigurationTest"
./gradlew test --tests "com.example.bootlab.InlinePropertiesTest"
./gradlew test --tests "com.example.bootlab.CommandLineArgumentsTest"
./gradlew test --tests "com.example.bootlab.MainAlwaysTest"
./gradlew test --tests "com.example.bootlab.RandomPortEnvironmentTest"
./gradlew test --tests "com.example.bootlab.StartupFailureRunnerTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.bootlab.InlinePropertiesTest"
.\gradlew.bat test --tests "com.example.bootlab.RandomPortEnvironmentTest"
```

Gradle `--tests` filters class/method names; it **does not** decide `@SpringBootTest` classes/properties. Annotations still govern context startup for the selected tests.

Inspect reports:
- `build/reports/tests/test/index.html`: HTML report.
- `build/test-results/test/`: JUnit XML.
- Console `--info` and root exceptions for context startup issues.
- Statuses `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, or `SKIPPED`.
- When you need certainty that tests ran fresh, use `--rerun-tasks` and inspect the report.

If you run `./gradlew test --tests "com.example.bootlab.MainAlwaysTest"`, JUnit runs only the selected class; **main method policy** is still applied by Boot to the context. `BUILD SUCCESSFUL` with cached tasks is not proof that every method actually re-executed during the current build.

### 20.1. Expectations derived from code, not measured stdout

| Startup scenario | Designed outcome |
|---|---|
| Default NONE | `base|8|true` |
| Inline properties | `inline|3|false` |
| Feature default | `FeatureFlagService` does not exist |
| Feature enabled inline | `FeatureFlagService` exists |
| Alias `value` | region `alias` |
| `@ActiveProfiles("qa")` | region `qa-profile`, batchSize 12 |
| Args `--demo.region=from-cli` | bound region `from-cli` |
| `@TestPropertySource` | region `from-test-inline`, enabled false |
| Dynamic source | `demo.external-uri=stub://local-service` |
| `UseMainMethod.NEVER` | region `base` |
| `UseMainMethod.ALWAYS` | region `from-main-profile` |
| MOCK MVC | GET /probe body `mock|8|true` |
| RANDOM_PORT | GET /probe body `socket|8|true` |
| NONE | No ServletWebServerApplicationContext |
| ContextRunner invalid | `hasFailed()` |

If an expected value differs during actual execution, check external profiles/CI variables, property-source ordering, and context caching instead of tweaking assertions arbitrarily.

## 21. Context caching, parallelism, and startup cost

Spring TestContext caches `ApplicationContext` when the context key matches: configuration classes, property sources, active profiles, context customizers (including `@DynamicPropertySource`, bean overrides), context loaders, and related factors. The tests in this article intentionally use multiple context variants to demonstrate how `classes/properties/webEnvironment` change startup outcomes.

Operational consequences:
- A cached context **does not automatically rebind** singleton properties or re-evaluate conditional beans if you mutate `Environment` after startup.
- `@DirtiesContext` can evict a context from cache; use it only when shared state genuinely needs resetting, since it adds bootstrap cost and can affect concurrent tests.
- Gradle `maxParallelForks>1` spawns separate JVM test processes; the context cache is **not shared across JVMs**, yet external DB/Redis/file paths may still be shared.
- `@MockitoBean` in a concurrently used context can suffer races when multiple tests stub/reset the same mock.
- `webEnvironment=RANDOM_PORT` starts an embedded server and can use more resources than `NONE`; multiple forks increase CPU/RAM/network usage.
- Enabling `spring.main.lazy-initialization=true` can defer bean failures, so do not use it as a “fix” for `contextLoads` when verifying full Boot startup.

An optimized test suite does not boot a full context for every calculation. For pure service methods without Spring dependencies, use plain JUnit. For web mapping, `@WebMvcTest`; for conditional auto-config, `ApplicationContextRunner`; for full Boot wiring and servers, `@SpringBootTest` with the right options.

## 22. Diagnosing when the Spring context fails to load

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| `Unable to find a @SpringBootConfiguration` | Test outside package tree or missing root | Specify `classes=DemoApplication.class`, fix package structure |
| Multiple Boot configuration candidates | Multiple main classes | Pick explicit source |
| App beans missing | Nested `@Configuration` replaced root, or `classes` too narrow | Use full root or `@TestConfiguration` to supplement |
| NoSuchBeanDefinitionException RuntimeSettings | Configuration properties binding not enabled | Check `@EnableConfigurationProperties`/`@ConfigurationPropertiesScan` |
| Binding error on batchSize | Property cannot convert to int | Fix key/value, assert negative startup separately |
| Conditional bean missing | Feature off, missing scan, other conditions | Check effective config and `ConditionEvaluationReport` |
| `application-qa.properties` has no effect | QA not active | `@ActiveProfiles("qa")` |
| Main policy test doesn't see main-mode | `useMainMethod=NEVER` | Choose `ALWAYS` if testing main is truly needed |
| `ALWAYS` fails startup | No matching main found | Fix entry point or refactor startup |
| AppArgs empty | Used `properties` instead of `args` | Set `args={"--key=value"}` |
| `@TestPropertySource` file not found | Wrong path | Use explicit resource path |
| Dynamic URL has wrong port | Resource not ready, supplier reads stale endpoint | Manage startup/lifecycle |
| MockMvc not injected | `@SpringBootTest` missing `@AutoConfigureMockMvc` | Enable MockMvc for mock web mode |
| `@LocalServerPort` missing | MOCK/NONE binds no server | Use RANDOM_PORT when networking is needed |
| `BindException` on HTTP port | Used DEFINED_PORT/fixed port | Use RANDOM_PORT or allocate exclusive port |
| `@Transactional` test doesn't roll back HTTP writes | HTTP server thread differs from JUnit test thread | Explicit cleanup/data isolation |
| Test runs too slowly | Full context loads external dependencies | Use suitable slices/runners/fakes |
| Fails before `@Test` method | Bean startup/condition/binding failure | Read full root cause, test negatives with runner |
| Fails only in parallel | Shared context/mock/static/resource state | Reduce concurrency to isolate races, separate resources |
| Context cache uses wrong config | Profiles/customizers not as expected | Check context key, avoid shared mutable state |
| Gradle reports success yet 0 tests | Test discovery/filter/cache | Check task status and HTML/XML reports |

### 22.1. Evidence-based investigation order

1. Extract the **root cause** beneath `Failed to load ApplicationContext`.
2. Record the exact test class and annotations: `classes`, `webEnvironment`, `useMainMethod`, `args`, `properties`.
3. Identify active profiles and the source of any unexpected value.
4. If a bean is missing, inspect component scanning and condition evaluation.
5. Inspect actual bound `RuntimeSettings`, not just the `application.properties` file.
6. If random port, inspect `@LocalServerPort`; if fixed port fails, check what other process holds the port.
7. If tests involve DB/HTTP threads, determine transaction ownership and rollback/cleanup.
8. If failures occur only on CI, inspect environment variables, Java/Gradle versions, forks, and remote services.
9. Isolate a minimal context or use `ApplicationContextRunner` to reproduce a property condition.
10. Fix the root cause, rerun the exact Test task, and verify reports.

## 23. QA checklist for this lab

- [ ] Understand `classes` specifies configuration sources, not a fixed list of the only beans.
- [ ] Understand how Boot discovers `@SpringBootConfiguration`/`@SpringBootApplication`.
- [ ] Avoid letting nested `@Configuration` accidentally replace the root.
- [ ] Use `@TestConfiguration` + `@Import` when adding beans.
- [ ] Use `properties`/`value` with the right alias and keys.
- [ ] Check bound `@ConfigurationProperties` alongside the actual bean graph.
- [ ] Verify `@ConditionalOnProperty` via bean presence/absence.
- [ ] Use `@ActiveProfiles` when profile-specific config is needed.
- [ ] Ensure tests do not hit production endpoints/credentials.
- [ ] Verify `@TestPropertySource` file and inline value precedence.
- [ ] Ensure `@DynamicPropertySource` fetches resource endpoints with proper lifecycle.
- [ ] Use `args` to test `ApplicationArguments`, without confusing it with `properties`.
- [ ] Avoid pointless same-key collisions across multiple property sources.
- [ ] Choose `webEnvironment=NONE` for non-web startup.
- [ ] Choose `MOCK` + MockMvc for full MVC mock exchanges.
- [ ] Choose `RANDOM_PORT` when a real embedded server is needed.
- [ ] Avoid `DEFINED_PORT` in parallel CI without a port lease.
- [ ] Understand test-thread `@Transactional` does not roll back HTTP server-thread writes.
- [ ] Choose `useMainMethod=ALWAYS` when testing `main` customization; assert real effects.
- [ ] Avoid putting `@ActiveProfiles` matching the main-activated profile inside main-policy tests.
- [ ] Use `ApplicationContextRunner` for intentional startup failures.
- [ ] Keep context caching, `@DirtiesContext`, Mockito mocks, and Gradle forks under control.
- [ ] Never treat `contextLoads()` as sufficient verification of startup options.
- [ ] Confirm Gradle/JUnit reports show tests executed before reporting runtime PASS.

## 24. Official reference documentation

- [Spring Boot 3.5 — SpringBootTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html): `classes`, `properties`, `args`, `webEnvironment`, `useMainMethod`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): Boot context discovery, main, arguments, and web modes.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): property source ordering, profile files, and type-safe binding.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `ApplicationArguments` and startup features.
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html): conditional bean report.
- [Spring Framework — @TestPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): test property locations/inline syntax.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html): dynamically registered property suppliers.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context cache keys, reuse, isolation.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, reports, and test filtering.

**Conclusion:** `@SpringBootTest` does more than check whether a context loads. `classes` selects the **bean graph** that can form; `properties`, `@ActiveProfiles`, and dynamic test sources select **configuration**; `args` verifies **CLI behavior**; `webEnvironment` determines **mock vs. real HTTP server**; `useMainMethod` verifies **customizations in `main()`**. A good test observes real post-startup consequences — bound settings, conditional beans, active profiles, arguments, ports, HTTP responses — with isolated data and resources, rather than dropping in an annotation and hoping bootstrap behaves right.
