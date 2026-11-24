# `@Import` to Supplement Configuration or Beans Needed for the Spring Boot Test Environment

## Objectives

When writing Spring Boot tests, there are times when the application needs a bean or a group of configurations **solely for the test**: a fixed clock, a mock/fake adapter for an external service, a JSON converter with specialized settings, a policy for a specific test case, or a controller collaborator in an MVC slice. The `@Import` annotation lets you **bring a configuration class or Spring-managed class into the test's ApplicationContext** explicitly, rather than arbitrarily widening component scanning or altering production configuration just to make tests run.

After this lesson, you can:

- Understand what `@Import` adds to the Spring context and distinguish **adding a bean definition**, **selecting a bean during injection**, and **replacing a bean**.
- Combine `@Import` with `@TestConfiguration` and `@SpringBootTest` or an appropriate test slice.
- Write a **runnable** Java 17 + Spring Boot + JUnit Jupiter example: keep the production `Clock` bean, import a fixed `Clock` for tests, and use `@Primary` to select the test bean.
- Distinguish `@Import`, `@ContextConfiguration`, `@TestPropertySource`, `@ActiveProfiles`, component scanning, and test mocks.
- Diagnose `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, duplicate bean name errors, misconfigured contexts, or tests using the wrong configuration.
- Keep tests small and reproducible, avoiding leaking test beans into production or accidentally turning a test slice into nearly a full application.

This lesson focuses on **configuring the test environment with `@Import`**. It is not intended to replace a full guide on Spring configuration, dependency injection, or other types of integration tests.

## 1. Problem: a test is missing a bean or needs a different configuration

Suppose a service checks deadlines using `Instant.now()`. Calling the system clock directly makes the test depend on real time, making exact boundary cases like "just expired" hard to verify. A testable design is to **inject `java.time.Clock` into the service**:

~~~java
@Service
public class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !clock.instant().isBefore(deadline);
    }
}
~~~

This is an **abbreviated illustration snippet**, missing full imports and input handling; the runnable version is in Section 4. For production, the application can configure `Clock.systemUTC()`. In tests, we want `Clock.fixed(...)` at a known instant. The question is not "how do we fake `Instant.now()`?", but "how do we get **the test's Spring container to choose the fixed Clock**?".

An easy-to-follow approach is:

~~~text
Spring Boot application context for the test
    |
    +-- @SpringBootApplication and production @Beans
    |       +-- systemClock : Clock
    |       +-- deadlineService : DeadlineService
    |
    +-- @Import(FixedClockTestConfig.class)
    |       +-- fixedTestClock : Clock (@Primary)
    |
    +-- autowire DeadlineService(Clock)
            |
            v
      fixedTestClock is selected because of @Primary
            |
            v
      Assertions at a fixed instant, independent of the real clock
~~~

`@Import` **brings configuration/bean definitions into the context**. `@Primary` **resolves bean selection when multiple candidates of the same type exist**. The two annotations serve two distinct jobs and must be understood separately.

## 2. What is `@Import` actually?

`@Import` belongs to Spring Framework and is imported with:

~~~java
import org.springframework.context.annotation.Import;
~~~

It can reference one or more classes, for example:

~~~java
@Import({FixedClockTestConfig.class, StubExternalServiceConfig.class})
class SomeSpringTest {
    // Imported classes contribute configuration/beans to the context.
}
~~~

The snippet above **only illustrates syntax**, not a standalone runnable class, because the referenced classes and Spring test setup are not defined.

In terms of semantics:

- If a class is `@Configuration`, Spring processes the `@Bean`s, `@Import`s, and configuration declarations inside that class.
- Spring also supports importing certain regular classes as components, as well as advanced mechanisms like `ImportSelector` and `ImportBeanDefinitionRegistrar`. When learning to add test beans, most cases only need **importing an explicit `@Configuration`/`@TestConfiguration`**.
- `@Import` can be placed on a configuration class, or on a test class in appropriately bootstrapped Spring Boot tests.
- `@Import` is not a JUnit annotation; placing it on a plain Java class **does not automatically create a Spring context**. A test bootstrap mechanism is required, such as `@SpringBootTest`, `@WebMvcTest`, or an appropriate Spring TestContext setup.

### What `@Import` does not do

1. **It does not automatically add dependencies to the Gradle classpath.** If a bean needs an external library, you still have to declare the appropriate dependency.
2. **It does not start a Spring Boot application on its own.** That is the job of the test bootstrap annotation/framework.
3. **It does not mean overriding an existing bean.** If you import a bean of the same type, the context can end up with **two candidates** and injection becomes ambiguous; if it has the same **bean name**, a bean-definition override error can occur.
4. **It does not automatically mock dependencies.** Imported beans are real beans by default (or test doubles you create inside the config).
5. **It does not guarantee small, fast tests.** An imported config can drag in many beans, broad `@ComponentScan`, listeners, and external infrastructure.
6. **It does not automatically apply `application-test.yml`** just because the class name contains "test"; profiles and property sources must be configured per the setup in use.

## 3. Tools commonly paired with `@Import`

| Tool | What does it do? | Best suited when |
| --- | --- | --- |
| `@Import(TestConfig.class)` | Brings specified config/bean definitions into the context | A test needs to add a bean or group of beans |
| `@TestConfiguration` (Spring Boot) | Marks configuration dedicated to tests | Holding `@Bean` methods for test Clock/fakes/adapters |
| `@Configuration` | Declares standard Spring configuration | Shared production configuration or Spring module config |
| `@Primary` | Prioritizes a bean when type-based injection finds multiple candidates | A test bean should be chosen instead of the production bean |
| `@Qualifier("...")` | Selects a specific candidate at an injection point | A specific bean name is needed without changing context-wide priority |
| `@TestPropertySource` | Adds property values/files to Spring TestContext | Overriding properties within test scope |
| `@ActiveProfiles("test")` | Activates a Spring profile in tests | Enabling profile-conditional beans/properties |
| `@SpringBootTest` | Bootstraps the Spring Boot application context | Testing collaboration across beans and Boot config |
| `@WebMvcTest` | Bootstraps an MVC slice in Boot | Testing controllers/requests/JSON without starting the whole app |
| Appropriate test mock/fake | Replaces a collaborator that should not run for real | Isolating network calls, email, message brokers, DB |

**Three separate questions:**

- *Is the bean registered?* → check `@Import`, `@Bean`, component scan, or `@MockBean`/version-appropriate mock mechanism.
- *Which bean gets selected for injection?* → check type, `@Primary`, `@Qualifier`, and dependency conditions/config.
- *Does Boot need to start up?* → check `@SpringBootTest`, test slices, or plain Spring Framework TestContext.

For instance, a service taking `Clock` via its constructor does not care which `@Bean` produced the `Clock`; it only asks for a matching bean. The **composition** lives in Spring configuration. This keeps service logic easy to unit test and lets tests swap dependency choices without modifying business code.

## 4. Runnable Java 17/Spring Boot example: importing a test Clock with `@TestConfiguration`

This example uses **Spring Boot 3.3.5**, Gradle Groovy DSL, and Java 17. These versions are illustrative for building a standalone runnable project; in a repository using a different Spring Boot version, follow the project's BOM and Gradle/dependency policy. The goal is to clearly show `@Import` adding a bean, `@Primary` selecting it, and the test producing deterministic results.

### 4.1. Business contract

The `DeadlineService` checks a deadline:

- For a `deadline` before the current instant, `expired(deadline)` returns `true`.
- For a `deadline` **equal to** the current instant, it also returns `true`.
- For a `deadline` in the future, it returns `false`.
- `reminderAfter(delay)` returns the current instant plus a non-negative `Duration`.
- A negative or `null` `delay` is rejected with `IllegalArgumentException`.

Assume the test clock is fixed at **2025-03-01T10:15:30Z**. Thus a deadline of `2025-03-01T10:15:30Z` must be treated as expired, and a reminder after 15 minutes must be **2025-03-01T10:30:30Z**. These expected values come from the requirements, not by computing expected values with the service under test.

### 4.2. Project structure

~~~text
import-test-clock-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/
    │   ├── DemoApplication.java
    │   └── DeadlineService.java
    └── test/java/com/example/testing/
        ├── FixedClockTestConfig.java
        └── DeadlineServiceImportTest.java
~~~

Gradle Wrapper scripts/files are generated by Gradle or taken from an already configured project; do not hand-write the binary `gradle-wrapper.jar`.

**`settings.gradle`**

~~~groovy
rootProject.name = 'import-test-clock-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `spring-boot-starter` provides the core container, Boot auto-configuration, and logging; **`spring-boot-starter-web` is not needed** because the example does not test HTTP.
- `spring-boot-starter-test` provides Spring TestContext, JUnit Jupiter, and related testing libraries.
- `junit-platform-launcher` supports the Gradle/JUnit Platform runtime. Dependency versions are managed by Spring Boot's BOM/dependency management in this example.
- `useJUnitPlatform()` tells Gradle's test task to discover and run `org.junit.jupiter.api.Test` methods.
- The Java 17 toolchain requires JDK 17 to be available or configured via toolchain provisioning; the Wrapper **does not install the JDK by itself**.

### 4.3. Production application with a real Clock

**`src/main/java/com/example/testing/DemoApplication.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    @Bean
    public Clock systemClock() {
        return Clock.systemUTC();
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@Bean systemClock()` creates the production `Clock` using real UTC time. Placing this bean in `DemoApplication` keeps the example brief; in a larger application, it can be moved into a separate `TimeConfiguration` for organization.

Important: **production still has a valid Clock**, so the application does not depend on importing a test config to start. The test will **add** a fixed `Clock` bean and instruct Spring to prefer it. Do not modify `systemClock()` in production just because tests want fake time.

**`src/main/java/com/example/testing/DeadlineService.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public final class DeadlineService {

    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean expired(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return !clock.instant().isBefore(deadline);
    }

    public Instant reminderAfter(Duration delay) {
        if (delay == null || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "delay must be non-negative");
        }
        return clock.instant().plus(delay);
    }
}
~~~

The service uses **constructor injection**: Spring picks a `Clock` and passes it into `DeadlineService` when creating the bean. Aside from `@Service`, the service code is plain Java with **no direct `Instant.now()` calls**, allowing us to test it with a fixed `Clock`.

The expression `!clock.instant().isBefore(deadline)` means "the current instant is no longer before the deadline," i.e., **now >= deadline**. This is an important boundary: when both `Instant`s are equal, the method returns `true`.

### 4.4. Test-only configuration

**`src/test/java/com/example/testing/FixedClockTestConfig.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfig {

    @Bean
    @Primary
    public Clock fixedTestClock() {
        return Clock.fixed(
                Instant.parse("2025-03-01T10:15:30Z"),
                ZoneOffset.UTC);
    }
}
~~~

Three parts play distinct roles:

- **`@TestConfiguration`** marks a configuration class used for Spring Boot testing. A top-level `@TestConfiguration` class under `src/test/java` is not picked up automatically by Boot's default component scan; here we **explicitly import it**.
- **`@Bean`** registers a `Clock` bean named `fixedTestClock` with a fixed instant.
- **`@Primary`** gives that bean priority when Spring needs to inject a `Clock` by type, while the production `systemClock` bean still exists.

Note that `@Primary` **does not replace/mutate the `systemClock` bean**. If code uses `@Qualifier("systemClock")` or requests the bean named `systemClock`, it still gets the real `Clock`. In an application with multiple qualifiers or complex conditions, inspect the exact injection point rather than treating `@Primary` as a global override.

`proxyBeanMethods = false` fits well here because the test config does not call `@Bean` methods from one another relying on proxying. When `@Bean` methods call each other directly and you rely on singleton interception, understand the proxy mechanism rather than copying this attribute blindly.

### 4.5. Test importing the config and asserting behavior

**`src/test/java/com/example/testing/DeadlineServiceImportTest.java`**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(FixedClockTestConfig.class)
class DeadlineServiceImportTest {

    private static final Instant FIXED_NOW =
            Instant.parse("2025-03-01T10:15:30Z");

    @Autowired
    private DeadlineService service;

    @Autowired
    private Clock chosenClock;

    @Autowired
    private ApplicationContext context;

    @Test
    void importedPrimaryClockIsSelected() {
        // Both Clock beans are present, but type-based injection picks @Primary.
        assertTrue(context.containsBean("systemClock"));
        assertTrue(context.containsBean("fixedTestClock"));

        assertEquals(FIXED_NOW, chosenClock.instant());
        assertSame(context.getBean(DeadlineService.class), service);
    }

    @Test
    void deadlineBeforeCurrentTimeIsExpired() {
        Instant earlier = Instant.parse("2025-03-01T10:15:29Z");

        assertTrue(service.expired(earlier));
    }

    @Test
    void deadlineEqualToCurrentTimeIsExpired() {
        assertTrue(service.expired(FIXED_NOW));
    }

    @Test
    void futureDeadlineIsNotExpired() {
        Instant later = Instant.parse("2025-03-01T10:15:31Z");

        assertFalse(service.expired(later));
    }

    @Test
    void reminderAfterFifteenMinutesIsDeterministic() {
        Instant actual = service.reminderAfter(
                Duration.ofMinutes(15));

        assertEquals(
                Instant.parse("2025-03-01T10:30:30Z"),
                actual);
    }

    @Test
    void negativeDurationIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.reminderAfter(Duration.ofMinutes(-1)));
    }

    @Test
    void nullDurationIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.reminderAfter(null));
    }
}
~~~

**What the test proves:**

1. The context **contains both `systemClock` and `fixedTestClock`**, so this is a case of *adding a bean* rather than overriding a bean by name.
2. `chosenClock.instant()` equals `FIXED_NOW`, proving the type-injected candidate is the test `Clock` (via `@Primary`).
3. `DeadlineService` is a Spring-created bean; `assertSame` verifies that the injected instance and the one retrieved from `ApplicationContext` are the same singleton bean.
4. Three deadline tests protect before, equal to, and after the cutoff instant.
5. The reminder test protects `Duration` addition from the fixed instant.
6. Two error tests protect rejection of negative or null delays.

**Why use `@SpringBootTest`?** We want to verify **application context configuration and Boot dependency injection** when combining production config with test config. `@SpringBootTest(webEnvironment = NONE)` avoids starting an HTTP server. If you only want to test `DeadlineService`'s algorithm in isolation, you can construct `new DeadlineService(Clock.fixed(...))` in a plain Java unit test **without needing a Spring context**.

### 4.6. Running and checking results

From the project directory with Gradle Wrapper:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Run just the class:

~~~bash
./gradlew test --tests 'com.example.testing.DeadlineServiceImportTest'
~~~

With the code and configuration above, there are **7 `@Test` methods**, each running once; **7 passing tests** are expected. There is no `System.out.println` in the tests, so **there are no fixed business stdout lines**. Gradle can report `BUILD SUCCESSFUL` when all tasks succeed or `UP-TO-DATE` when reusing prior results. Verify the executed test count from:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    └── TEST-com.example.testing.DeadlineServiceImportTest.xml
~~~

If you need to re-run due to caching concerns, use `./gradlew test --rerun-tasks`. In a multi-project repo, the build report path is under **the module containing the test**.

To create the Wrapper for a new project, you need an installed compatible Gradle binary to bootstrap it, for example:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Then commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and `gradle/wrapper/gradle-wrapper.properties` into the repository. Version 8.8 is merely a compatible example for the Java 17/Boot 3.3.x demo; in a real project, follow the Gradle Wrapper and compatibility matrix used by your team.

## 5. Distinguishing importing **an extra bean**, **changing selection**, and **replacing an implementation**

This is the most easily misunderstood part of the topic.

### 5.1. Adding a bean that does not exist yet

If a `PaymentGateway` interface has no bean in a test context, you can import a configuration that creates a fake:

~~~java
@TestConfiguration
class FakePaymentGatewayConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
~~~

and place `@Import(FakePaymentGatewayConfig.class)` on the test. This snippet **only illustrates the declaration style**; `PaymentGateway`/`InMemoryPaymentGateway` must be defined in the codebase. It fits when the test only needs to verify a use case interacting with a fake gateway without making external network calls.

If the **production application genuinely needs a PaymentGateway** yet lacks a production bean, getting the test to pass by importing a fake **does not prove** the application will start in a real environment. You must have other tests/integration checks verifying real adapter wiring when that is required.

### 5.2. Having multiple beans of the same type

In the runnable example, `Clock` has two beans:

~~~text
Clock
  ├── systemClock     (production @Bean)
  └── fixedTestClock  (@Bean @Primary from @Import)
~~~

When Spring needs to inject `Clock` without a qualifier, it chooses the `@Primary` bean. If **there is no** `@Primary` or appropriate resolution rule, Spring may fail with `NoUniqueBeanDefinitionException` because it does not know which `Clock` to choose.

Another option is using `@Qualifier` at the injection point when requesting a **specific bean**, for example:

~~~java
public SomeService(@Qualifier("systemClock") Clock clock) {
    this.clock = clock;
}
~~~

The snippet above is not a standalone runnable class. `@Qualifier` differs from `@Primary`: it **attaches a requirement to a specific injection point**, whereas `@Primary` sets a bean's priority when resolving multiple candidates by type. Do not sprinkle `@Primary` onto multiple beans of the same type; selection can become ambiguous again.

### 5.3. Duplicate *bean name* is not duplicate *bean type*

Do not create two `@Bean` methods with the same name `clock` in the same application context and expect `@Primary` to resolve them. Duplicate bean definition names involve **bean overriding**, which Spring Boot disables by default; it can fail with an error like `BeanDefinitionOverrideException`.

The preferred solution is **giving distinct names** (`systemClock`/`fixedTestClock`) and using `@Primary` or `@Qualifier`, or substituting via a test mock or conditional configuration mechanism suited to your design. Do not enable `spring.main.allow-bean-definition-overriding=true` just to push tests past configuration errors without understanding the consequences.

### 5.4. When you want to "override" a dependency with a mock

If the test goal does not require running a collaborator's logic and instead just needs to dictate its return values, a test mock sometimes fits better than a real bean:

- With Spring Boot 3.3.x, projects can use `@MockBean` per that version's API.
- Newer Spring Framework/Spring Boot versions have different mock annotation mechanisms; follow your project's dependencies and APIs rather than mixing annotations across versions.
- `@Import`ing a fake bean is useful when the fake has real, stable behavior reused across many tests; it **differs** from automatically creating a Mockito mock.

Choose the tool based on **what needs to be proved**. `Clock.fixed` is a real Java object with deterministic behavior, so importing a `@Primary` bean is usually cleaner than mocking static `Instant.now()`. A payment gateway with dozens of failure modes may fit a Mockito stub at the boundary, or a well-designed stateful fake API.

## 6. `@TestConfiguration`: nested and top-level

Spring Boot provides `org.springframework.boot.test.context.TestConfiguration` to declare configurations dedicated to tests.

**Top-level `@TestConfiguration`**, such as `FixedClockTestConfig`, lives in `src/test/java` and **is not automatically pulled into all test contexts by default component scanning**. To use it in a specific test, explicitly import it: `@Import(FixedClockTestConfig.class)`. This lets test A use fixed Clock A and test B use a different configuration without leaking beans globally.

**Nested static `@TestConfiguration`** can also be used inside a test class, for example:

~~~java
@SpringBootTest
class SomeBootTest {

    @TestConfiguration
    static class ExtraTestBeans {
        @Bean
        FeatureFlagClient featureFlagClient() {
            return new FixedFeatureFlagClient(true);
        }
    }
}
~~~

This is an **illustrative snippet**; `FeatureFlagClient`, `FixedFeatureFlagClient`, and test setup are not provided. Under Spring Boot's test bootstrap, nested `@TestConfiguration` is normally added alongside the primary application configuration; when you want explicit scope and reuse across multiple classes, top-level `@TestConfiguration` plus `@Import` is clearer.

Do not confuse this with a regular nested `@Configuration`: Spring Boot's test bootstrap may treat a nested `@Configuration` as a replacement for the auto-discovered primary application configuration. Therefore, when you only want to **add** test beans while keeping application config, prefer `@TestConfiguration` or explicitly list the required classes.

**Do not put `@TestConfiguration` in `src/main/java`** to "share" with production. Keeping test-only config in the test source set and limiting imports prevents fake adapters or test data from appearing in real application artifacts.

## 7. `@Import` with different Spring Boot test types

### 7.1. `@SpringBootTest`: testing bean wiring/behavior with a Boot context

The runnable example in Section 4 uses:

~~~java
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(FixedClockTestConfig.class)
class DeadlineServiceImportTest {
    // ...
}
~~~

This loads the app context from `DemoApplication`, then adds test beans from the imported config. It fits when proving bean DI collaboration in a fairly complete Spring Boot environment. However, if the application has JPA, message brokers, and external services, loading the full context can be slow or require heavy setup; do not choose `@SpringBootTest` just to add a simple `Clock` if the goal does not require a Boot context.

### 7.2. `@WebMvcTest`: adding beans to an MVC slice

If only testing a controller, `@WebMvcTest(InvoiceController.class)` typically loads only filtered MVC components. If the controller or MVC layer needs a specific bean, import an appropriate test config:

~~~java
@WebMvcTest(InvoiceController.class)
@Import(InvoiceWebTestConfig.class)
class InvoiceControllerTest {
    // @Autowired MockMvc; @Test...
}
~~~

This snippet is **illustrative only**, not standalone code since the controller/config are undefined. Importing a test config lets you supply a dependency or custom MVC component **intentionally**. It **does not** magically turn the test into a full integration test verifying every service, repository, database, and application workflow.

If you import a `@Configuration` carrying a `@ComponentScan` covering the whole application package, you can accidentally pull in many beans and defeat the purpose of the MVC slice. Choose a small config class rather than importing the entire application configuration indiscriminately. If Spring Security is active, `MockMvc` may need a mock user or proper security test setup; do not disable security just because a status returns 401/403.

### 7.3. `@DataJpaTest`: adding small configuration while preserving slice goals

If a repository test needs an entity listener, converter, or small config, `@Import` can add the appropriate bean. Yet it does not replace configuring a `DataSource`, transactions, and real persistence mechanics. For JPA, tests proving mappings/queries/constraints must run against the proper data stack; do not import a mock repository and conclude that SQL works.

### 7.4. Plain Spring Framework TestContext, without Boot

If a module does not use Boot, you can write a root config that imports supporting configs:

~~~java
@Configuration
@Import(SharedTestBeans.class)
class RootSpringTestConfig {
}

@SpringJUnitConfig(RootSpringTestConfig.class)
class PureSpringWiringTest {
    // @Autowired ...; @Test ...
}
~~~

This is an illustrative configuration snippet requiring `SharedTestBeans` and imports to be defined. Here `@SpringJUnitConfig` activates `SpringExtension` and builds the context from `RootSpringTestConfig`, while `@Import` is processed as Spring registers bean definitions from the root config. Unlike `@SpringBootTest`, you **do not** automatically receive Boot auto-configuration. Pick the right bootstrap mechanism first, then supplement beans.

## 8. `@Import` vs. properties/profiles: not the same thing

Some tests only need to change a configuration value, **not add a new bean**. For example, to test a 10% discount rate instead of 20%, you can use `@TestPropertySource(properties = "pricing.discount=0.10")`, or `@SpringBootTest(properties = "...")` in a Boot test, depending on the scenario. A bean reading `Environment`/properties will receive the corresponding value.

If production defines two implementations using `@Profile("prod")` and `@Profile("test")`, you can use `@ActiveProfiles("test")` to enable the matching implementation without necessarily importing another config. Still, profiles do not replace bean registration: if a bean is not declared anywhere in the loaded context scope, `@ActiveProfiles("test")` will not conjure it up.

| Need | What to try first |
| --- | --- |
| Change a property value already read by a bean | `@TestPropertySource` or Spring Boot test properties |
| Select a bean already declared under a profile | `@ActiveProfiles` |
| Add a bean missing from the test context | `@Import(TestConfig.class)` |
| Add a test bean of the same type and prefer the test bean | `@Import` + `@Primary`, or an appropriate mock mechanism |
| Force a specific bean at a single constructor | `@Qualifier` on the injection point |
| Verify real wiring of the entire application | Appropriate Boot integration test |
| Test pure Java logic only | Instantiate objects directly without opening a Spring context |

**Do not overuse `@Import` just to avoid understanding how current configuration works.** Additional test configs should be named and commented clearly so reviewers can tell which beans are production and which exist only in tests.

## 9. TestContext caching, context pollution, and data independence

Spring TestContext can cache the `ApplicationContext` across test classes sharing an equivalent configuration set to reduce startup cost. Differences such as imported configurations, profiles, properties, or test context customizers **can produce different cache keys**, causing extra contexts to load.

This has two consequences:

1. **Performance:** importing dozens of distinct configs per test creates many contexts across the suite and increases runtime. Group tests with matching configuration needs when sensible, without sacrificing test isolation purely for cache hits.
2. **Independence:** a mutable stateful singleton fake created inside a cached context can outlive individual tests and leak data. Design fakes with reset mechanisms, separate fixtures, or appropriate scope; only use `@DirtiesContext` when a polluted context truly must be discarded.

For example, `Clock.fixed` in the runnable project is **stateless and immutable**, so sharing the context does not make tests order-dependent. If you import an `InMemoryOrderRepository` holding a mutable list, test A adding an order followed by test B expecting an empty list can fail when running the whole suite; clean up fixture data rather than treating Spring context caching as a bug.

Another risk is **context pollution**: a test intending only to check MVC imports a broad shared config pulling in out-of-scope beans, creating profile/transaction/security conflicts. One giant `TestConfig` containing every fake in the system may seem convenient at first, yet makes it hard for tests to tell what is real versus fake. Usually it is better to split configs by responsibility—`FixedClockTestConfig`, `FakeMailGatewayConfig`, `TestJsonConfig`, etc.—and import only what is needed.

## 10. Common errors and how to fix them

| Symptom | Common cause | Diagnosis / fix |
| --- | --- | --- |
| `No qualifying bean of type…` | Bean not created or config not imported | Check `@Import`, `@Bean`, package/config class, conditions/profiles |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type with no unique selection | Use `@Primary`/`@Qualifier` intentionally; avoid importing extra beans |
| `BeanDefinitionOverrideException` | New config declares a bean with the same **name** as an existing one | Rename the bean or use an appropriate replacement mechanism; do not enable overriding blindly |
| Test uses real Clock by mistake and becomes flaky | Test Clock not injected, wrong `@Primary`/qualifier | Check selected candidate; assert `clock.instant()` in the test |
| `@Import` seems to have no effect | Test does not bootstrap a Spring context or imported wrong class | Put the annotation on a Spring Boot/TestContext test, inspect root cause |
| `Failed to load ApplicationContext` | Bean constructor failure, missing dependency, overly broad imported config | Read the root cause in the stack trace; narrow imports |
| Test bean "leaks" into other tests | Config broadly scanned or imported in too many places | Use test-only top-level `@TestConfiguration`, import explicitly |
| MVC slice loads too many beans | Imported config with broad component scan | Narrow config and keep controller wiring scoped |
| Test still fails after adding `@Primary` | Multiple primary candidates or `@Qualifier` still points elsewhere | Check how Spring resolves the bean at the injection point |
| Context slow across the full suite | Many combinations of imports/profiles/properties or unnecessary `SpringBootTest` | Reduce context variants, use unit/slice tests where appropriate |
| Spring Boot test passes but production fails | Test imported a fake hiding missing production wiring | Add a smoke/integration test booting production configuration |
| `@TestConfiguration` not discovered | Used top-level test config but forgot `@Import` | Explicitly `@Import` it from the test |
| JUnit reports 0 tests or `NO-SOURCE` | Test class outside source set or missing engine/`useJUnitPlatform()` | Check path, JUnit Jupiter imports, and Gradle test task |
| Test uses Boot-only annotation in a plain Spring module | `spring-boot-test` not on classpath or module does not use Boot | Use `@SpringJUnitConfig`/`@ContextConfiguration` and import config into Spring root |

### Quick isolation steps when failing

- **Step 1:** Confirm whether JUnit even reached the test. If not, check Gradle/JUnit Platform/imports first before adding Spring config.
- **Step 2:** If the context failed to load, read the deepest root cause inside `Failed to load ApplicationContext`.
- **Step 3:** If a bean is missing, check whether the **bean definition exists in the current context**; for slice tests, do not assume full-application scanning.
- **Step 4:** If there are two beans of the same type, distinguish a **bean selection** error from a **duplicate bean name** error.
- **Step 5:** If an assertion is wrong, inspect the selected bean and output; do not add `@DirtiesContext` or disable security/auto-config as a universal fix.

## 11. Designing clean and safe tests when importing beans

A test can use `@Import` with valid syntax and still create false confidence. Follow these principles:

**Test the contract, not just that "the context starts."** For example, `assertNotNull(service)` is very weak when the goal is accurate deadline calculation. In the runnable example, assertions before/at/after the cutoff provide independent evidence of behavior, while the Clock check protects wiring.

**Do not replace the logic under test.** If you want to verify `DeadlineService` calculates deadlines, run the **real service** with a real-behaving fixed `Clock`; do not mock the service itself to return expected values and conclude the business logic works.

**Separate "test-only bean" from "production fallback."** A fake Gateway must not hide missing production bean configuration. Have dedicated tests ensuring production config supplies real adapters where it matters.

**Do not keep real secrets in test config.** Real accounts, tokens, and passwords must never live in `@TestConfiguration`, `@TestPropertySource`, or CI logs. Use controlled test credentials/placeholders and fake endpoints where appropriate.

**Constrain the classpath of test beans.** Keep them under `src/test/java` and import only when tests need them; never move a class into `src/main/java` just to bypass test discovery errors. If shared across multiple modules, design dedicated test fixtures/Gradle test fixtures rather than leaking test config into production artifacts.

**Distinguish bean substitution from integration coverage.** A test with a fake external client proves your logic uses the client interface when the fake responds as expected; it does not prove protocol, auth, or network behavior of the production adapter. Add adapter contract tests or appropriate integration tests.

## 12. Practice exercises

**Exercise A — observe the effect of `@Import`:** Remove `@Import(FixedClockTestConfig.class)` from `DeadlineServiceImportTest` while keeping the expectations. The test checking `fixedTestClock` will fail because that bean does not exist; tests relying on fixed time will also become unreliable because `systemClock` is selected. Restore the annotation after observing.

**Exercise B — see the role of `@Primary`:** Keep `@Import` but temporarily remove `@Primary` from `fixedTestClock`. When Spring needs a `Clock` by type for `DeadlineService` and the test field, two beans of the same type prevent the context from picking one unambiguously. Restore `@Primary` and explain the difference between *bean registration* and *bean resolution*.

**Exercise C — check boundary values:** Change `deadlineEqualToCurrentTimeIsExpired` to expect `false` on a local branch. The test should fail because the contract states that an instant **equal to the deadline is already expired**. Revert so the test passes.

**Exercise D — limit scope:** Write a `@WebMvcTest` for a simple controller that has a dependency to fake; `@Import` a config providing only that dependency. Compare bean count and startup time against importing the whole application config, without dropping status/JSON checks.

**Exercise E — protect test config from environment leakage:** Create a fake gateway with an internal `List`, and have two tests both add items. If sharing a context, add a fixture reset before each test and verify order independence. Do not reach for `@DirtiesContext` first when a simple reset works.

**Exercise F — properties instead of import:** Pick a bean reading `pricing.rate` from Spring `Environment`. Override its value in a test via `@TestPropertySource` and assert the output without creating a new bean unnecessarily. Explain when `@Import` is still required if a bean does not exist at all.

## 13. Checklist when using `@Import` in Spring Boot tests

- [ ] Does the behavior under test genuinely require a Spring context? If it is pure Java logic, a unit test can be simpler.
- [ ] Do I know exactly **which bean/config** is imported and **why** the test needs it?
- [ ] Does the test config live on the test source set, absent from production artifacts?
- [ ] Is `@Import` placed on an appropriate test/bootstrap config (`@SpringBootTest`, slice, or root Spring configuration)?
- [ ] If two beans share a type, is the bean selection mechanism (`@Primary`, `@Qualifier`, conditional config) transparent?
- [ ] Have I distinguished duplicate bean *type* from duplicate bean *name* without disabling overriding checks recklessly?
- [ ] Does the import keep test scope narrow without accidentally opening a broad component scan?
- [ ] Does the test assert contract outputs/side effects rather than only "bean was created"?
- [ ] Are context and stateful singleton fakes reset/controlled between tests?
- [ ] Are tests using fakes/mocks complemented by integration/contract tests for real adapters when needed?
- [ ] Does Gradle run JUnit Platform with the right wrapper/JDK, and do reports confirm the actual number of tests run?

**Remember:** `@Import` **adds configuration or beans into the test's Spring context**; it does not create a context by itself, does not auto-mock dependencies, and does not mean replacing old beans. With Spring Boot, the **`@TestConfiguration` + `@Import`** combination declares test beans explicitly, while **`@Primary` or `@Qualifier`** decides which candidate gets injected. Importing only what is needed and verifying business outputs independently yields tests that are both stable and trustworthy.