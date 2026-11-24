# @ContextConfiguration and Declaring Minimal Configuration in Spring TestContext

## 1. Problem to Solve

When testing a Spring Boot application, some behaviors require **Spring to actually create beans and inject dependencies**, without launching the entire application, connecting to a database, starting a web server, or loading a mass of auto-configuration. For example: a service depends on a `Clock` declared with `@Bean`, and you need to confirm that the service can be created by Spring with a fixed clock and accurately compute deadlines.

`@ContextConfiguration` is an annotation in the **Spring TestContext Framework** used to specify how to build the `ApplicationContext` for a test: Java configuration classes, configuration resource locations, or appropriate `ApplicationContextInitializer` classes. Combined with test runner integration, Spring builds the context, manages lifecycle/caching, and supports `@Autowired` on the test object.

A minimal configuration is **the set of beans sufficient for the behavior under test**, including only the dependencies and infrastructure truly required—not a mechanical miniature copy of the entire production configuration. It helps:

- Verify **wiring and bean creation** for a focused group of real components instead of calling constructors manually.
- Isolate configuration errors such as missing beans, wrong qualifiers, properties, or profiles within an understandable scope.
- Control external dependencies using explicitly registered fake/stub beans or mocks.
- Reduce startup time, environment variables, and stack trace noise compared to a full application context in suitable scenarios.
- Keep tests close enough to Spring's Dependency Injection mechanism while remaining repeatable.

**Key distinction:** `@ContextConfiguration` **does not automatically enable Spring Boot auto-configuration** and does not start a server by default. If a test needs auto-configuration behavior, a Security filter chain, the MVC stack, JPA mappings, or a real deployment flow, choose the corresponding test slice or integration test.

## 2. What Does @ContextConfiguration Actually Do?

Basic syntax example:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = MyTestConfig.class)
class SomeServiceTest {
    @Autowired
    SomeService service;
}
```

The snippet above is an **annotation pattern**: `MyTestConfig` and `SomeService` are types that must be defined in the project, not a standalone Java file. Meaning of each part:

1. `@ExtendWith(SpringExtension.class)` connects **JUnit Jupiter** with Spring TestContext. The extension supports test instance preparation, dependency injection, lifecycle callbacks, and access to `ApplicationContext`.
2. `@ContextConfiguration(classes = MyTestConfig.class)` tells Spring **which configuration to use** to build the context. With Java config, Spring registers the beans defined in the configuration class and any configurations it intentionally imports or scans.
3. `@Autowired` injects beans from the context into test fields (or parameters/constructors under the corresponding injection mechanism). If no matching bean exists, the test can fail **before executing the `@Test` method body**.
4. Spring TestContext can **cache the `ApplicationContext`** across tests with equivalent configurations. The context is not necessarily recreated for every test method.

With legacy JUnit 4, integration could use `@RunWith(SpringRunner.class)`. Examples in this lesson use **JUnit Jupiter (JUnit 5+)**; do not mix `@RunWith` and `@ExtendWith` as if they were a single mechanism.

`@ContextConfiguration` can specify:

| Attribute | Effect | When Appropriate |
|---|---|---|
| `classes` | One or more configuration/component classes registered in the context | Java-based config, e.g., `@Configuration` with `@Bean` |
| `locations` | Resource paths processed by the corresponding `ContextLoader` | Projects still using XML or other resource-based configs |
| `initializers` | `ApplicationContextInitializer` classes participating in context preparation | Need to customize the context before refresh |
| `loader` | Selects a `ContextLoader` instead of the default loader | Specialized needs, rarely required for basic tests |
| `inheritLocations`, `inheritInitializers` | Controls inheritance of locations/initializers from a parent test class | Test suites sharing common configuration in a superclass |

For a standard Java 17+ lesson, **`classes = ...` with `@Configuration`/`@Bean` is the clearest starting point**. There is no need to use advanced attributes just to load two beans.

## 3. Choosing the Right Test Level Before Creating a Context

| Question to Verify | Usually Suitable Tool | Loads a Spring Context? |
|---|---|---|
| Is a pure Java calculation or rule correct? | JUnit, instantiate with `new`; Mockito if needed | No |
| Are two or a few beans wired and collaborating properly via Spring? | `@ContextConfiguration` + `SpringExtension` | Yes, a small explicitly declared context |
| Does a service work with real Boot configuration/auto-configuration? | `@SpringBootTest` with an appropriate scope | Yes, typically broader |
| MVC mappings, controller validation, JSON, filters in a web slice? | `@WebMvcTest` + `MockMvc` or suitable web test | Yes, MVC slice context |
| Are repository/JPA queries or entity mappings accurate? | `@DataJpaTest` or database integration test | Yes, persistence slice context |
| Does a real endpoint require a running HTTP server? | Integration test with `webEnvironment = RANDOM_PORT` | Yes, plus an HTTP server |

`@ContextConfiguration` is not the default choice for every test: if a pure Java method can be verified with `new Service(fakeDependency)`, a direct unit test is usually simpler. Conversely, if the risk under verification is **Spring bean wiring**, plain Java tests cannot catch configuration mistakes; a targeted minimal context is valuable.

Do not use `@ContextConfiguration` to replace `@SpringBootTest` for a test that depends on Boot auto-configured beans: those beans do not appear automatically in a minimal context. A test loading only two beans cannot prove that the full Boot application starts successfully.

## 4. Complete Java 17+ Example: Loading Only the Two Needed Business Beans

### 4.1. Requirements

A service determines whether a request qualifies for a processing batch before a cutoff time. Rule: **accepted only when the current time is strictly before the deadline** (`now < deadline`); at the exact deadline and after the deadline must be rejected.

The service receives `Clock` via its constructor. In tests, `Clock` is created by Spring with a **fixed** instant, independent of the real-world clock. The configuration declares only:

- One fixed `Clock` bean.
- One `DeadlinePolicy` bean using that exact `Clock`.

No database, repository, web server, `@SpringBootApplication`, or broad component scan is required.

### 4.2. Production Code

File `src/main/java/com/example/testing/DeadlinePolicy.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class DeadlinePolicy {
    private final Clock clock;

    public DeadlinePolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public boolean acceptsBefore(Instant deadline) {
        Objects.requireNonNull(deadline, "deadline");
        return clock.instant().isBefore(deadline);
    }
}
```

This is a standalone Java class with no Spring annotations. This illustrates that **Spring can manage an object created via `@Bean` without requiring the class itself to carry `@Service`**. With `isBefore` logic, when `now == deadline` the result is `false`.

### 4.3. Test Class and Minimal @Configuration

File `src/test/java/com/example/testing/DeadlinePolicyTest.java`:

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {

    private static final Instant NOW =
            Instant.parse("2026-03-01T10:00:00Z");

    @Configuration(proxyBeanMethods = false)
    static class MinimalConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }

        @Bean
        DeadlinePolicy deadlinePolicy(Clock clock) {
            return new DeadlinePolicy(clock);
        }
    }

    @Autowired
    DeadlinePolicy policy;

    @Autowired
    ApplicationContext context;

    @Test
    void acceptsWhenDeadlineIsInTheFuture() {
        assertTrue(policy.acceptsBefore(NOW.plusMillis(1)));
    }

    @Test
    void rejectsAtExactDeadline() {
        assertFalse(policy.acceptsBefore(NOW));
    }

    @Test
    void rejectsAfterDeadline() {
        assertFalse(policy.acceptsBefore(NOW.minusMillis(1)));
    }

    @Test
    void rejectsNullDeadline() {
        assertThrows(NullPointerException.class,
                () -> policy.acceptsBefore(null));
    }

    @Test
    void injectsExactlyTheExpectedBusinessBeans() {
        assertNotNull(policy);
        assertSame(context.getBean(DeadlinePolicy.class), policy);
        assertEquals(1, context.getBeansOfType(Clock.class).size());
        assertEquals(1, context.getBeansOfType(DeadlinePolicy.class).size());
        assertFalse(context.containsBean("dataSource"));
    }
}
```

### 4.4. Reading the Mechanism in the Example Accurately

- `MinimalConfig` is a **static nested configuration class**, explicitly referenced via `DeadlinePolicyTest.MinimalConfig.class`. Using a nested class scopes the configuration to this test group.
- `@Configuration(proxyBeanMethods = false)` tells Spring to treat `@Bean` methods as factory methods without proxying inter-bean method calls as with `proxyBeanMethods=true`. Because the `deadlinePolicy` bean **receives `Clock` as a parameter** rather than calling `clock()` directly, Spring injects the managed singleton.
- `@Bean Clock clock()` creates a fixed clock at `NOW`, so the before/at/after-deadline cases are deterministic and require no `Thread.sleep`.
- `@Bean DeadlinePolicy deadlinePolicy(Clock clock)` instructs Spring to locate a matching `Clock` bean and pass it to the constructor. A missing bean or multiple ambiguous `Clock` beans will fail context creation.
- `@Autowired DeadlinePolicy policy` proves the test receives the bean from **`ApplicationContext`**, rather than calling `new` inside the test.
- `getBeansOfType` checks **beans of the expected types**. Do not claim the context contains only two beans total, because Spring also registers internal infrastructure beans.
- `containsBean("dataSource")` proves the example configuration **does not automatically load a `DataSource` bean under that name**. This observes the boundaries of the declared context, not a database integration test.

With these two files and proper dependencies, **all five tests are designed to pass**. They have no `System.out.println` statements, so there is no fixed business stdout to copy. Output formatting depends on the Gradle/Maven, JUnit Platform, and reporting configuration. In a real application, only report passing after running the tests and checking the report.

### 4.5. Running the Test in a Spring Boot Project

The project requires Java 17+ and test dependencies containing Spring TestContext, JUnit Jupiter (and the Jupiter runner). In many Spring Boot projects, `spring-boot-starter-test` supplies the core libraries. Configure Gradle/Maven for your project version; Gradle typically declares `useJUnitPlatform()` on the test task.

Gradle wrapper on Linux/macOS:

```bash
./gradlew test --tests "com.example.testing.DeadlinePolicyTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.DeadlinePolicyTest"
```

Maven wrapper on Linux/macOS:

```bash
./mvnw -Dtest=DeadlinePolicyTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=DeadlinePolicyTest test
```

By common convention, Gradle writes the HTML report at `build/reports/tests/test/index.html`; Maven Surefire writes results under `target/surefire-reports/`. In multi-module projects or builds with custom test tasks, inspect the report for the specific task/module executed.

## 5. Minimal Configuration: What to Declare and What to Avoid

Before writing `@Configuration`, sketch the dependency graph of the behavior under test, for example:

```text
DeadlinePolicyTest
  └── DeadlinePolicy (real bean)
        └── Clock (fixed bean used in test)
```

Only two business beans are involved. Add more beans only when there is a specific verification reason—for instance, if a service requires an `ExchangeRatePort` interface, you can declare a fake bean for that interface. Do not add `@ComponentScan("com.example")` just to avoid writing two factory methods: broad scanning can unintentionally load controllers, schedulers, repositories, conditional beans, or components needing external infrastructure.

### 5.1. @Configuration with @Bean

Use `@Configuration` and `@Bean` when you want to know the exact beans registered. It is a simple and stable way to supply:
- A fixed configuration value such as `Clock.fixed(...)`, a test policy, or a fake gateway.
- A real service with explicitly declared dependencies.
- Supporting beans needed by the test (validators, formatters, mappers) if the behavior genuinely depends on them.

Avoid calling `@Bean` methods directly from inside one another. With `proxyBeanMethods=false`, calling `deadlinePolicy(clock())` in plain Java invokes a regular method and creates a separate object that differs from the Spring-managed bean. **Prefer injecting dependencies via `@Bean` method parameters**, such as `deadlinePolicy(Clock clock)`.

### 5.2. @Import for Selective Configuration Composition

If you already have a small, self-contained production configuration, you can use `@Import` in a test config to register it alongside extra beans. Syntax illustration:

```java
@Configuration(proxyBeanMethods = false)
@Import(SharedDomainConfiguration.class)
class TargetedTestConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

This snippet **is not a standalone Java file**: `SharedDomainConfiguration` and imports must be defined in the project. Even with `@Import`, verify whether the imported configuration drags in component scanning, auto-configuration, or unexpected dependencies. The goal is to load **only the required beans**, not pull the entire application into the test indirectly.

### 5.3. Loading Multiple Configurations via `classes`

`@ContextConfiguration(classes = {DomainConfig.class, TestClockConfig.class})` can load two explicitly chosen configurations. If `DomainConfig` already declares another `Clock` bean, the context may contain multiple beans of the same type; resolve this with `@Primary`, `@Qualifier`, or by adjusting test configuration per the contract. Do not rely on Spring arbitrarily picking one bean.

### 5.4. What Does Not Appear Automatically?

A context declaring only `MinimalConfig` does not automatically have:
- Auto-configured `DataSource`, JPA repositories, or a transaction manager.
- MVC controllers, `DispatcherServlet`, an embedded HTTP server, or a Security filter chain.
- `@Service` classes in the package unless explicitly registered/imported/scanned.
- Boot application beans driven by `@SpringBootApplication` if that configuration is not loaded.
- Boot-specific properties and startup environment setup.

This is a **desirable characteristic** of minimal configuration. If a test fails because one of the components above is missing, first determine whether the test truly needs it. If so, declare the right bean or switch to the appropriate test type instead of expanding the context uncontrollably.

## 6. @SpringJUnitConfig: Concise Equivalent for JUnit Jupiter

Spring provides `@SpringJUnitConfig`, a composed annotation combining `SpringExtension` integration with `@ContextConfiguration`. Thus, for the example's Java config, you can replace:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {
    // ...
}
```

with:

```java
@SpringJUnitConfig(classes = DeadlinePolicyTest.MinimalConfig.class)
class DeadlinePolicyTest {
    // ...
}
```

Both snippets are **illustrative annotation patterns** with the class body omitted; import `org.springframework.test.context.junit.jupiter.SpringJUnitConfig`. When using `@SpringJUnitConfig`, there is no need to add `@ExtendWith(SpringExtension.class)` just to enable the same extension.

Do not confuse `@SpringJUnitConfig` with `@SpringBootTest`: the former is a shorthand for Spring TestContext Java config, while the latter starts a test context using **Spring Boot**'s mechanism, typically including auto-configuration according to the chosen scope.

## 7. Configuring Properties and Profiles in a Minimal Context

Some beans depend on properties or `@Profile`. Spring TestContext offers dedicated annotations to control these inputs:

- `@ActiveProfiles("test")`: activates profiles in the loaded context, affecting beans or configurations conditional on profiles.
- `@TestPropertySource(properties = "feature.mode=sandbox")`: adds a dedicated test property source, useful when a bean reads via `Environment` or `@Value`.
- `@DynamicPropertySource`: registers dynamic properties for scenarios such as ports or URLs generated at test runtime; suitable for dynamic sources.
- `@ContextConfiguration(initializers = ...)`: custom initializer when a test genuinely needs to prepare the context before refresh.

The following annotation example is **an illustration placed on a test class**, not a complete file:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = FeatureTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.mode=sandbox")
class FeaturePolicyTest {
    // ...
}
```

Here `FeatureTestConfig` must be a real configuration reading `feature.mode`, and the necessary imports must exist in the project. `@TestPropertySource` does not automatically turn arbitrary strings into business beans. Read values from `Environment` or a properly configured binding mechanism; if code uses Boot's `@ConfigurationProperties`, a minimal context usually needs to register/enable that binding support explicitly.

**Distinction from `application.yml`:** A minimal context using Spring TestContext directly does not automatically execute Spring Boot's external config loading pipeline and auto-configuration. If a test needs to verify how Boot loads `application.yml`, profile-specific files, configuration properties, or conditional auto-configuration, `@SpringBootTest` or a Boot test slice may be more suitable.

## 8. Adding Mocks or Fakes Properly to a Small Context

A service may depend on a repository or an external client. In a minimal context test, replace the dependency with a **deterministic fake**, or register a Mockito mock as a bean.

Illustrated inside a test config when `RateGateway` and `PricingService` are already defined:

```java
@Configuration(proxyBeanMethods = false)
static class PricingTestConfig {
    @Bean
    RateGateway rateGateway() {
        return org.mockito.Mockito.mock(RateGateway.class);
    }

    @Bean
    PricingService pricingService(RateGateway gateway) {
        return new PricingService(gateway);
    }
}
```

This is an illustrative snippet, **not a standalone program**. A test with `@Autowired RateGateway gateway` and `@Autowired PricingService service` can stub `when(gateway.findRate(...)).thenReturn(...)`, call the real service, and assert the result. If no Spring container is needed, constructing the service directly with a mock is cleaner.

**Note on mock lifecycle:** Spring TestContext can cache contexts containing the same mock instance across multiple test methods/classes. When a mock is a manually declared bean, interactions and stubbings can persist beyond a single method unless resets are managed. Use an appropriate reset mechanism/configuration or create stateless fakes; if you need `Mockito.reset(mock)` in `@BeforeEach`, do so intentionally and avoid wiping configuration needed by other tests. Do not rely on caching to share results across tests.

In supported versions of Spring Framework/Spring Boot, `@MockitoBean` or corresponding mock-bean mechanisms can replace beans in the context and manage lifecycle via the framework integration. Exact annotation details depend on the project's library version. A standalone `@Mock` field on a test class **does not automatically become a bean** injected into `@Autowired` services inside the Spring context.

With a real repository, `@ContextConfiguration` + a mocked repository only proves that **the service invokes the interface and data correctly**. To verify JPA queries, mappings, SQL dialects, transactions, or commits, you need repository/integration tests with an appropriate database.

## 9. Context Cache, Shared State, and @DirtiesContext

Spring TestContext caches `ApplicationContext` instances so it does not have to rebuild identical configurations for every test. When multiple classes share the same configuration, profiles, properties, and other cache-key factors, they can reuse a context within the same test process.

This improves speed but has an important consequence: **mutable singleton beans can retain state across tests**, such as an in-memory fake repository, counters, business caches, or mocks recording invocation history. A test might pass when run alone yet fail when run as part of the full suite.

To prevent order dependency:
1. Use immutable data or stateless beans where appropriate.
2. Prepare/reset fake data for each test via `@BeforeEach`/`@AfterEach`, transactions, or controlled test fixtures.
3. Do not mutate configuration or shared singletons in one test and expect another test to receive initial values.
4. Use `@DirtiesContext` when a test **truly dirties the context** and needs it evicted from the cache, because it forces Spring to rebuild the context and increases runtime.

Do not put `@DirtiesContext` on every test just to avoid thinking about isolation. In `DeadlinePolicyTest`, `Clock.fixed` and `DeadlinePolicy` hold no mutable state, so there is no need to dirty the context after each method.

The context cache is not a guarantee that the same instance survives across Maven/Gradle invocations or separate JVM processes. Always rely on actual test results and the active runner configuration.

## 10. Reading Errors When Minimal Configuration Is Missing or Wrong

Because the context is usually loaded **before the test method body**, configuration errors can cause every test in the class to fail during setup. When you see `Failed to load ApplicationContext`, read the `Caused by` chain to pinpoint the offending bean or configuration.

| Symptom | Common Cause | How to Check |
|---|---|---|
| `NoSuchBeanDefinitionException` | Missing bean dependency for a `@Bean` method/constructor, or no bean of that type | List declared configs and dependency paths; add the needed bean/fake |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type without a qualifier or primary candidate | Choose `@Qualifier`, `@Primary`, or trim the configuration |
| `BeanCreationException` | Factory method throws an exception, missing property, or dependency init fails | Look deeper into `Caused by` and the `@Bean` method |
| `UnsatisfiedDependencyException` | Spring cannot resolve a parameter/constructor | Check bean types, generics, qualifiers, and profiles |
| `@Autowired` test field is `null` | SpringExtension/test runner not activated or test instance not prepared by TestContext | Verify JUnit Jupiter annotations and imports |
| Spring context loads but lacks Boot-specific behavior | Test loads only minimal Java config without Boot auto-configuration | Use the proper test slice or `@SpringBootTest` if that behavior is in scope |
| Test passes alone, fails in suite | Mutable singletons, mock state, or context mutations across tests | Clean fixtures, manage state and cache |
| Loads too many beans or hits external DB error | Imports/scanning too broad, accidentally pulling infrastructure dependencies | Trim down to minimal `@Bean` definitions or use an integration test with proper infrastructure |

For example, if `DeadlinePolicy` is declared as a bean but `Clock` is removed from `MinimalConfig`, Spring cannot inject `Clock` into `deadlinePolicy(Clock clock)`. The error message will point to the unresolved dependency, **not evidence that `acceptsBefore` calculates incorrectly**, since the method may never have been called.

Do not start fixing every missing-bean error by adding `@SpringBootTest`. Determine whether the test verifies DI for a small subset or the real Boot system, then declare the matching configuration.

## 11. Optimizing Scope in Large Projects

In a multi-module system, a minimal configuration should easily answer:
- Which beans must be **real implementations** to prove the contract?
- Which dependencies only need fakes/mocks to reproduce inputs?
- Are AOP, method-level validation, transactions, cache advice, or security proxies needed? If **those mechanisms must be tested**, load the relevant infrastructure configuration or use an integration test.
- Which properties/profiles affect business decisions? Are they explicitly declared in the test?
- Does the service spawn threads, make network calls, read files, or hit a database inside its constructor or `@PostConstruct`? If so, reconsider using the real implementation in a minimal context.
- Does it need comparison against actual Boot configuration? If so, do not treat a minimal context as sufficient proof.

A passing `@ContextConfiguration` test proves **that the declared beans can be created and collaborate according to the test's assertions**. It does not prove that configurations excluded from the context work properly. To avoid overclaiming, state the scope clearly, for example:

> The test with `DeadlinePolicyTest.MinimalConfig` loads a fixed `Clock` bean and a `DeadlinePolicy`. Assertions before/at/after the deadline pass. The test does not load JPA, MVC, or application auto-configuration.

This is a template for presenting verified results; real reports must be based on logs/test reports from the actual run.

## 12. Checklist Before Finishing a Test Using @ContextConfiguration

- [ ] Identified a genuine reason to need a Spring context instead of a plain Java unit test.
- [ ] Selected `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration` or the equivalent `@SpringJUnitConfig` in JUnit Jupiter.
- [ ] `classes` points to the right configuration class; `@Configuration` declares the minimum required real beans and fakes/mocks.
- [ ] `@Bean` dependencies are injected by type/qualifier without accidentally creating duplicate objects via direct `@Bean` method calls under `proxyBeanMethods=false`.
- [ ] Did not enable application-wide component scanning or broad auto-configuration unnecessarily.
- [ ] The test uses `@Autowired` and assertions that verify **real behavior**, not merely `assertNotNull`.
- [ ] Volatile inputs like time are fixed or controlled via test fixtures.
- [ ] Important profiles/properties are declared explicitly, without relying accidentally on the local machine environment.
- [ ] Mutable singleton beans/mocks do not leak state across tests; cache/`@DirtiesContext` are used appropriately.
- [ ] Distinguished minimal wiring evidence from integration tests of MVC, Security, JPA, and Boot auto-configuration.
- [ ] Ran the right build task and inspected the report and stack traces before declaring the actual result PASS.

**Conclusion:** `@ContextConfiguration` lets you test Spring's Dependency Injection mechanism using **an intentionally declared ApplicationContext**. With `SpringExtension`, a small `@Configuration` class, and a few required `@Bean` definitions, tests can verify both wiring and business rules deterministically and diagnosably. Minimal configuration is valuable when it is just enough to prove the chosen behavior; when real Boot infrastructure, MVC, or a database is required, expand the scope using the corresponding test type and state clearly what was verified.
